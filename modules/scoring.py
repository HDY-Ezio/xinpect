"""Xinpect - Credits, scoring, and grading (分层积分系统 v2)
支持会员积分池（月度刷新）和积分包池（有效期1年）
"""
import math
import sqlite3
import uuid as uuid_mod
from contextlib import contextmanager
from datetime import datetime, timedelta
from flask import session, request

from .constants import (
    app, logger,
    FREE_BRAIN_IDS, FREE_BRAIN_ID_SET, ALL_BRAIN_IDS, BRAINS, BRAINS_MAP,
    TIERS, TIERS_MAP,
    SCORE_S_THRESHOLD, SCORE_A_THRESHOLD, SCORE_B_THRESHOLD, SCORE_C_THRESHOLD,
    SCORE_COLOR_AMBER, MAX_SCORE,
    DEDUCTION_PER_CRITICAL, DEDUCTION_PER_HIGH, DEDUCTION_PER_MEDIUM, DEDUCTION_PER_LOW,
    MAX_DEDUCTION_MEDIUM, MAX_DEDUCTION_LOW,
    DEFAULT_CREDIT_TX_LIMIT,
    SCAN_COST_BASE_FEE, SCAN_COST_PER_100_LINES_BASIC, SCAN_COST_PER_100_LINES_FULL,
    DAILY_LIMIT_FREE, DAILY_LIMIT_REGISTERED,
    SUBSCRIPTION_CREDITS, CREDIT_PACKS,
)
from .db import get_db
from .helpers import is_vip_user


@contextmanager
def _txn(db):
    """积分写入/扣减的唯一事务边界。

    根因：这些函数原先各自 `BEGIN` / `COMMIT`，但它们经常被"已经开着事务"的
    调用方调用（注册发奖励、支付回调、扫描失败退款）。同一连接上二次 BEGIN 会
    抛 `cannot start a transaction within a transaction`，而异常又被 except 吞掉，
    结果就是**积分静默不发放**——账面上看不到任何报错，只看到"奖励为 0"。

    约定：谁开启事务，谁负责提交。若调用方已处于事务中，则用 SAVEPOINT 做嵌套，
    只回滚自己这一段，不打断调用方的整体事务。
    """
    if getattr(db, 'in_transaction', False):
        db.execute('SAVEPOINT credit_sp')
        try:
            yield
        except Exception:
            db.execute('ROLLBACK TO credit_sp')
            db.execute('RELEASE credit_sp')
            raise
        else:
            db.execute('RELEASE credit_sp')
    else:
        db.execute('BEGIN IMMEDIATE')
        try:
            yield
        except Exception:
            db.execute('ROLLBACK')
            raise
        else:
            db.execute('COMMIT')


# ============================================================
# 日期工具
# ============================================================

def _add_months(dt, months):
    """日期加月份，月末自动处理（1.31+1月→2.28/29）"""
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    import calendar
    max_day = calendar.monthrange(year, month)[1]
    day = min(dt.day, max_day)
    return dt.replace(year=year, month=month, day=day)


def _calculate_period_end(plan_key, period_start):
    """根据套餐类型计算会员积分周期结束时间"""
    if plan_key == 'monthly':
        return _add_months(period_start, 1)
    elif plan_key == 'quarterly':
        return _add_months(period_start, 3)
    elif plan_key == 'half_year':
        return _add_months(period_start, 6)
    elif plan_key == 'yearly':
        return _add_months(period_start, 12)
    else:
        days = SUBSCRIPTION_CREDITS.get(plan_key, {}).get('days', 30)
        return period_start + timedelta(days=days)


def _now_str():
    """当前时间的 SQLite 格式字符串"""
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


# ============================================================
# Daily usage（不变）
# ============================================================

def get_daily_usage():
    """获取今日使用次数"""
    db = get_db()
    today = datetime.now().strftime('%Y-%m-%d')
    user_id = session.get('user_id')
    ip = request.remote_addr

    if user_id:
        row = db.execute(
            'SELECT count FROM daily_usage WHERE date = ? AND user_id = ?',
            (today, user_id)
        ).fetchone()
    else:
        row = db.execute(
            'SELECT count FROM daily_usage WHERE date = ? AND ip = ? AND user_id IS NULL',
            (today, ip)
        ).fetchone()

    return row['count'] if row else 0


def check_daily_limit():
    """检查是否超过每日限制，返回 (是否允许, 剩余次数)"""
    if is_vip_user():
        return True, -1  # VIP 无限

    usage = get_daily_usage()
    limit = DAILY_LIMIT_REGISTERED if session.get('user_id') else DAILY_LIMIT_FREE
    remaining = max(0, limit - usage)
    return remaining > 0, remaining


def increment_daily_usage():
    """增加今日使用次数"""
    db = get_db()
    today = datetime.now().strftime('%Y-%m-%d')
    user_id = session.get('user_id')
    ip = request.remote_addr

    if user_id:
        db.execute('''
            INSERT INTO daily_usage (date, user_id, ip, count)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(date, user_id, ip)
            DO UPDATE SET count = count + 1
        ''', (today, user_id, ip))
    else:
        db.execute('''
            INSERT INTO daily_usage (date, user_id, ip, count)
            VALUES (?, NULL, ?, 1)
            ON CONFLICT(date, user_id, ip)
            DO UPDATE SET count = count + 1
        ''', (today, ip))
    db.commit()


# ============================================================
# 积分池核心函数
# ============================================================

def _ensure_credit_account(db, user_id):
    """确保用户有积分账户记录（内部用，不单独提交事务）"""
    existing = db.execute(
        'SELECT id FROM user_credits WHERE user_id = ?',
        (user_id,)
    ).fetchone()
    if not existing:
        db.execute(
            'INSERT INTO user_credits (user_id, balance, total_earned, total_spent) VALUES (?, 0, 0, 0)',
            (user_id,)
        )


def _ensure_pool_for_user(db, user_id):
    """确保 credit_pools 表存在（首次运行时自动创建）"""
    try:
        db.execute('SELECT 1 FROM credit_pools LIMIT 1')
    except sqlite3.OperationalError:
        # 表不存在，创建
        db.execute('''
            CREATE TABLE IF NOT EXISTS credit_pools (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                pool_type TEXT NOT NULL CHECK(pool_type IN ('subscription', 'pack')),
                balance INTEGER NOT NULL DEFAULT 0,
                total_earned INTEGER NOT NULL DEFAULT 0,
                total_spent INTEGER NOT NULL DEFAULT 0,
                period_start TEXT,
                period_end TEXT,
                priority INTEGER NOT NULL DEFAULT 100,
                subscription_plan TEXT DEFAULT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
        ''')
        db.execute('CREATE INDEX IF NOT EXISTS idx_cp_user ON credit_pools(user_id)')
        db.execute('CREATE INDEX IF NOT EXISTS idx_cp_user_active ON credit_pools(user_id, is_active)')
        db.execute('CREATE INDEX IF NOT EXISTS idx_cp_period ON credit_pools(period_end)')
        # 给 credit_transactions 添加 pool_id, pool_type 列
        try:
            db.execute('ALTER TABLE credit_transactions ADD COLUMN pool_id TEXT DEFAULT NULL')
        except sqlite3.OperationalError:
            pass
        try:
            db.execute('ALTER TABLE credit_transactions ADD COLUMN pool_type TEXT DEFAULT NULL')
        except sqlite3.OperationalError:
            pass
        db.commit()


def _pool_count(db, user_id):
    """检查用户是否有积分池记录"""
    _ensure_pool_for_user(db, user_id)
    row = db.execute(
        'SELECT COUNT(*) as cnt FROM credit_pools WHERE user_id = ?',
        (user_id,)
    ).fetchone()
    return row['cnt'] if row else 0


def get_user_credits(user_id):
    """获取用户总可用积分（所有活跃池之和）。无池时回退到 user_credits 表"""
    if not user_id:
        return 0
    db = get_db()
    _ensure_pool_for_user(db, user_id)

    pool_cnt = db.execute(
        'SELECT COUNT(*) as cnt FROM credit_pools WHERE user_id = ? AND is_active = 1',
        (user_id,)
    ).fetchone()

    if pool_cnt and pool_cnt['cnt'] > 0:
        row = db.execute(
            'SELECT COALESCE(SUM(balance), 0) as total FROM credit_pools WHERE user_id = ? AND is_active = 1',
            (user_id,)
        ).fetchone()
        return row['total'] if row else 0

    # 回退到旧表
    row = db.execute(
        'SELECT balance FROM user_credits WHERE user_id = ?',
        (user_id,)
    ).fetchone()
    return row['balance'] if row else 0


def _classify_pools(pools):
    """将积分池分类并汇总统计"""
    subscription_pool = None
    pack_pools = []
    total_balance = 0
    subscription_balance = 0
    pack_balance = 0
    subscription_refresh_at = None
    pack_nearest_expire = None

    for p in pools:
        total_balance += p['balance']
        if p['pool_type'] == 'subscription':
            subscription_pool = p
            subscription_balance += p['balance']
            subscription_refresh_at = p['period_end']
        elif p['pool_type'] == 'pack':
            pack_pools.append(p)
            pack_balance += p['balance']
            if p['period_end']:
                if pack_nearest_expire is None or p['period_end'] < pack_nearest_expire:
                    pack_nearest_expire = p['period_end']

    return {
        'pools': pools,
        'subscription': subscription_pool,
        'packs': pack_pools,
        'total_balance': total_balance,
        'subscription_balance': subscription_balance,
        'pack_balance': pack_balance,
        'subscription_refresh_at': subscription_refresh_at,
        'pack_nearest_expire_at': pack_nearest_expire,
        'legacy': False,
    }


def _get_legacy_pool_balance(db, user_id):
    """获取旧表积分余额"""
    row = db.execute(
        'SELECT balance FROM user_credits WHERE user_id = ?',
        (user_id,)
    ).fetchone()
    return row['balance'] if row else 0


def get_credit_pools(user_id):
    """获取用户所有积分池详情"""
    if not user_id:
        return _empty_pool_result()

    db = get_db()
    _ensure_pool_for_user(db, user_id)
    refresh_subscription_credits(user_id)

    pools = db.execute(
        '''SELECT id, pool_type, balance, total_earned, total_spent,
                  period_start, period_end, priority, subscription_plan,
                  is_active, created_at, updated_at
           FROM credit_pools
           WHERE user_id = ? AND is_active = 1
           ORDER BY priority ASC, period_end ASC''',
        (user_id,)
    ).fetchall()
    pools = [dict(p) for p in pools]

    if not pools:
        result = _empty_pool_result()
        result['total_balance'] = _get_legacy_pool_balance(db, user_id)
        result['pack_balance'] = result['total_balance']
        result['legacy'] = True
        return result

    return _classify_pools(pools)

def _empty_pool_result():
    return {
        'pools': [],
        'subscription': None,
        'packs': [],
        'total_balance': 0,
        'subscription_balance': 0,
        'pack_balance': 0,
        'subscription_refresh_at': None,
        'pack_nearest_expire_at': None,
        'legacy': False,
    }


def _sync_user_credits(db, user_id):
    """同步池总余额到 user_credits 表（保持兼容）"""
    _ensure_credit_account(db, user_id)
    total = db.execute(
        'SELECT COALESCE(SUM(balance), 0) as t FROM credit_pools WHERE user_id = ? AND is_active = 1',
        (user_id,)
    ).fetchone()['t']
    db.execute(
        "UPDATE user_credits SET balance = ?, updated_at = datetime('now', 'localtime') WHERE user_id = ?",
        (total, user_id)
    )


def _fetch_deductible_pools(db, user_id):
    """获取可扣费的积分池列表"""
    refresh_subscription_credits(user_id)
    pools = db.execute(
        '''SELECT id, pool_type, balance, period_end, priority
           FROM credit_pools
           WHERE user_id = ? AND is_active = 1 AND balance > 0
           ORDER BY priority ASC, period_end ASC''',
        (user_id,)
    ).fetchall()
    return [dict(p) for p in pools]


def _deduct_from_pools(db, user_id, amount, credit_meta):
    """从积分池中逐个扣费"""
    ref_type = credit_meta.get('ref_type')
    ref_id = credit_meta.get('ref_id')
    remark = credit_meta.get('remark', '')
    remaining = amount
    for pool in _fetch_deductible_pools(db, user_id):
        if remaining <= 0:
            break
        deduct = min(pool['balance'], remaining)
        if deduct > 0:
            db.execute(
                '''UPDATE credit_pools SET balance = balance - ?,
                   total_spent = total_spent + ?,
                   updated_at = datetime('now', 'localtime')
                   WHERE id = ?''',
                (deduct, deduct, pool['id'])
            )
            db.execute('''
                INSERT INTO credit_transactions
                    (user_id, type, amount, balance_after, ref_type, ref_id, remark, pool_id, pool_type)
                VALUES (?, 'consume', -?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, deduct, pool['balance'] - deduct,
                    ref_type, str(ref_id) if ref_id else None, remark,
                    pool['id'], pool['pool_type']))
            remaining -= deduct
    return remaining


def consume_credits(user_id, amount, ref_type=None, ref_id=None, remark=''):
    """按优先级扣费：先用会员积分，再用积分包（先到期先用）
    
    v5.53 修复竞态：使用 BEGIN IMMEDIATE 立即锁库，余额校验在事务内完成。
    返回 True/False，不再依赖事务外的 check-then-act。
    """
    if not user_id or amount <= 0:
        return False
    db = get_db()
    _ensure_pool_for_user(db, user_id)
    meta = {'ref_type': ref_type, 'ref_id': ref_id, 'remark': remark}

    try:
        # BEGIN IMMEDIATE（或嵌套 SAVEPOINT）由 _txn 统一管理：
        # 余额校验在锁内完成，避免并发超扣。
        with _txn(db):
            pools = db.execute(
                '''SELECT id, pool_type, balance, period_end, priority
                   FROM credit_pools
                   WHERE user_id = ? AND is_active = 1 AND balance > 0
                   ORDER BY priority ASC, period_end ASC''',
                (user_id,)
            ).fetchall()
            pools = [dict(p) for p in pools]

            if not pools:
                # 无池，走 legacy（此处仍在事务内，_txn 会嵌套 SAVEPOINT）
                return _consume_legacy(db, user_id, amount, meta)

            total_available = sum(p['balance'] for p in pools)
            if total_available < amount:
                return False

            _deduct_from_pools(db, user_id, amount, meta)
            _sync_user_credits(db, user_id)
            return True
    except sqlite3.Error as e:
        logger.warning('[积分] consume_credits 失败 user_id=%s amount=%s: %s', user_id, amount, e)
        return False

def _consume_legacy(db, user_id, amount, credit_meta):
    """旧的扣费逻辑（无池时使用）"""
    ref_type = credit_meta.get('ref_type')
    ref_id = credit_meta.get('ref_id')
    remark = credit_meta.get('remark', '')
    try:
        with _txn(db):
            _ensure_credit_account(db, user_id)

            row = db.execute(
                'SELECT balance FROM user_credits WHERE user_id = ?',
                (user_id,)
            ).fetchone()
            current_balance = row['balance'] if row else 0

            if current_balance < amount:
                return False

            db.execute('''
                UPDATE user_credits
                SET balance = balance - ?,
                    total_spent = total_spent + ?,
                    updated_at = datetime('now', 'localtime')
                WHERE user_id = ?
            ''', (amount, amount, user_id))

            balance_after = current_balance - amount
            db.execute('''
                INSERT INTO credit_transactions
                    (user_id, type, amount, balance_after, ref_type, ref_id, remark)
                VALUES (?, 'consume', -?, ?, ?, ?, ?)
            ''', (user_id, amount, balance_after, ref_type, str(ref_id) if ref_id else None, remark))

            return True
    except sqlite3.Error as e:
        logger.warning('[积分] consume_credits(legacy) 失败 user_id=%s amount=%s: %s', user_id, amount, e)
        return False


def grant_credits(user_id, amount, ref_type=None, ref_id=None, remark=''):
    """
    增加积分到对应池。
    ref_type='subscription' → 会员积分池
    ref_type='credit_pack' / 'topup' → 积分包池
    无池时回退到旧 user_credits 表。
    """
    if not user_id or amount <= 0:
        return False
    db = get_db()
    _ensure_pool_for_user(db, user_id)

    # 根据 ref_type 决定写入哪个池
    meta = {'ref_type': ref_type, 'ref_id': ref_id, 'remark': remark}
    if ref_type == 'subscription':
        return _grant_to_subscription_pool(db, user_id, amount, meta)
    elif ref_type in ('credit_pack', 'topup', 'referral_register', 'referral_recharge', 'referral_first_pay'):
        # 积分包、充值、推荐奖励统一走积分包池，有效期365天
        return _grant_to_pack_pool(db, user_id, amount, meta)
    elif ref_type in ("scan_refund", "refund"):
        # 退款回到已有的最大 pack 池，不新建池，防止碎片化
        pool_cnt = _pool_count(db, user_id)
        if pool_cnt > 0:
            return _grant_to_existing_pack_pool(db, user_id, amount, meta)
        return _grant_legacy(db, user_id, amount, meta)
    else:
        pool_cnt = _pool_count(db, user_id)
        if pool_cnt > 0:
            return _grant_to_pack_pool(db, user_id, amount, meta)
        return _grant_legacy(db, user_id, amount, meta)


def _resolve_plan_key(db, ref_id):
    """从订单推断会员套餐类型"""
    if not ref_id:
        return 'monthly'
    order = db.execute(
        'SELECT plan_id FROM orders WHERE order_id = ? LIMIT 1',
        (str(ref_id),)
    ).fetchone()
    if order and order['plan_id'] in SUBSCRIPTION_CREDITS:
        return order['plan_id']
    return 'monthly'


def _find_or_create_sub_pool(db, user_id, amount, plan_key):
    """查找或创建会员积分池"""
    now = _now_str()
    existing = db.execute(
        '''SELECT id FROM credit_pools
           WHERE user_id = ? AND pool_type = 'subscription' AND is_active = 1
           LIMIT 1''',
        (user_id,)
    ).fetchone()
    period_end = _calculate_period_end(plan_key, datetime.now()).strftime('%Y-%m-%d %H:%M:%S')

    if existing:
        pool_id = existing['id']
        db.execute(
            '''UPDATE credit_pools SET balance = balance + ?,
               total_earned = total_earned + ?, period_end = ?,
               subscription_plan = ?, updated_at = datetime('now', 'localtime')
               WHERE id = ?''',
            (amount, amount, period_end, plan_key, pool_id)
        )
    else:
        pool_id = str(uuid_mod.uuid4())
        db.execute(
            '''INSERT INTO credit_pools
               (id, user_id, pool_type, balance, total_earned, period_start, period_end,
                priority, subscription_plan, is_active)
               VALUES (?, ?, 'subscription', ?, ?, ?, ?, 1, ?, 1)''',
            (pool_id, user_id, amount, amount, now, period_end, plan_key)
        )
    return pool_id


def _grant_to_subscription_pool(db, user_id, amount, credit_meta):
    """积分写入会员池"""
    ref_type = credit_meta.get('ref_type')
    ref_id = credit_meta.get('ref_id')
    remark = credit_meta.get('remark', '')
    try:
        with _txn(db):
            plan_key = _resolve_plan_key(db, ref_id)
            pool_id = _find_or_create_sub_pool(db, user_id, amount, plan_key)

            new_balance = db.execute(
                'SELECT COALESCE(SUM(balance), 0) as t FROM credit_pools WHERE user_id = ? AND is_active = 1',
                (user_id,)
            ).fetchone()['t']
            db.execute('''
                INSERT INTO credit_transactions
                    (user_id, type, amount, balance_after, ref_type, ref_id, remark, pool_id, pool_type)
                VALUES (?, 'grant', ?, ?, ?, ?, ?, ?, 'subscription')
            ''', (user_id, amount, new_balance, ref_type,
                  str(ref_id) if ref_id else None, remark, pool_id))

            _sync_user_credits(db, user_id)
            return True
    except sqlite3.Error as e:
        logger.warning('[积分] grant_to_subscription 失败 user_id=%s amount=%s: %s', user_id, amount, e)
        return False

def _grant_to_pack_pool(db, user_id, amount, credit_meta):
    """积分写入积分包池（新池，有效期365天）"""
    ref_type = credit_meta.get('ref_type')
    ref_id = credit_meta.get('ref_id')
    remark = credit_meta.get('remark', '')
    try:
        with _txn(db):
            now = _now_str()
            now_dt = datetime.now()
            period_end = (now_dt + timedelta(days=365)).strftime('%Y-%m-%d %H:%M:%S')

            pool_id = str(uuid_mod.uuid4())
            max_p = db.execute(
                "SELECT COALESCE(MAX(priority), 1) as mp FROM credit_pools WHERE user_id = ? AND pool_type = 'pack'",
                (user_id,)
            ).fetchone()
            priority = (max_p['mp'] if max_p else 1) + 10

            db.execute(
                '''INSERT INTO credit_pools
                   (id, user_id, pool_type, balance, total_earned, period_start, period_end,
                    priority, subscription_plan, is_active)
                   VALUES (?, ?, 'pack', ?, ?, ?, ?, ?, NULL, 1)''',
                (pool_id, user_id, amount, amount, now, period_end, priority)
            )

            new_balance = db.execute(
                'SELECT COALESCE(SUM(balance), 0) as t FROM credit_pools WHERE user_id = ? AND is_active = 1',
                (user_id,)
            ).fetchone()['t']
            db.execute('''
                INSERT INTO credit_transactions
                    (user_id, type, amount, balance_after, ref_type, ref_id, remark, pool_id, pool_type)
                VALUES (?, 'grant', ?, ?, ?, ?, ?, ?, 'pack')
            ''', (user_id, amount, new_balance, ref_type,
                  str(ref_id) if ref_id else None, remark, pool_id))

            _sync_user_credits(db, user_id)
            return True
    except sqlite3.Error as e:
        logger.warning('[积分] grant_to_pack 失败 user_id=%s amount=%s: %s', user_id, amount, e)
        return False


def _grant_to_existing_pack_pool(db, user_id, amount, credit_meta):
    """退款回到用户已有的最大余额 pack 池，避免碎片化"""
    ref_type = credit_meta.get("ref_type")
    ref_id = credit_meta.get("ref_id")
    remark = credit_meta.get("remark", "")
    try:
        with _txn(db):
            pool = db.execute(
                "SELECT id, balance FROM credit_pools WHERE user_id = ? AND pool_type = ? AND is_active = 1 ORDER BY balance DESC LIMIT 1",
                (user_id, "pack")
            ).fetchone()

            if pool and pool["balance"] > 0:
                pool_id = pool["id"]
                db.execute(
                    "UPDATE credit_pools SET balance = balance + ?, total_earned = total_earned + ?, updated_at = datetime('now', 'localtime') WHERE id = ?",
                    (amount, amount, pool_id)
                )
            else:
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                now_dt = datetime.now()
                period_end = (now_dt + timedelta(days=365)).strftime("%Y-%m-%d %H:%M:%S")
                pool_id = str(uuid_mod.uuid4())
                max_p = db.execute(
                    "SELECT COALESCE(MAX(priority), 1) as mp FROM credit_pools WHERE user_id = ? AND pool_type = ?",
                    (user_id, "pack")
                ).fetchone()
                priority = (max_p["mp"] if max_p else 1) + 10
                db.execute(
                    "INSERT INTO credit_pools (id, user_id, pool_type, balance, total_earned, period_start, period_end, priority, subscription_plan, is_active) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, 1)",
                    (pool_id, user_id, "pack", amount, amount, now, period_end, priority)
                )

            new_balance = db.execute(
                "SELECT COALESCE(SUM(balance), 0) as t FROM credit_pools WHERE user_id = ? AND is_active = 1",
                (user_id,)
            ).fetchone()["t"]
            db.execute(
                "INSERT INTO credit_transactions (user_id, type, amount, balance_after, ref_type, ref_id, remark, pool_id, pool_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, "grant", amount, new_balance, ref_type, str(ref_id) if ref_id else None, remark, pool_id, "pack")
            )

            total = db.execute(
                "SELECT COALESCE(SUM(balance), 0) as t FROM credit_pools WHERE user_id = ? AND is_active = 1",
                (user_id,)
            ).fetchone()["t"]
            db.execute(
                "UPDATE user_credits SET balance = ?, updated_at = datetime('now', 'localtime') WHERE user_id = ?",
                (total, user_id)
            )
            return True
    except Exception as e:
        logger.warning("grant_to_existing_pack failed user_id=%s amount=%s: %s", user_id, amount, e)
        return False


def _grant_legacy(db, user_id, amount, credit_meta):
    """旧的发放逻辑（无池时使用）"""
    ref_type = credit_meta.get('ref_type')
    ref_id = credit_meta.get('ref_id')
    remark = credit_meta.get('remark', '')
    try:
        with _txn(db):
            _ensure_credit_account(db, user_id)

            db.execute('''
                UPDATE user_credits
                SET balance = balance + ?,
                    total_earned = total_earned + ?,
                    updated_at = datetime('now', 'localtime')
                WHERE user_id = ?
            ''', (amount, amount, user_id))

            row = db.execute(
                'SELECT balance FROM user_credits WHERE user_id = ?',
                (user_id,)
            ).fetchone()
            balance_after = row['balance'] if row else 0

            db.execute('''
                INSERT INTO credit_transactions
                    (user_id, type, amount, balance_after, ref_type, ref_id, remark)
                VALUES (?, 'grant', ?, ?, ?, ?, ?)
            ''', (user_id, amount, balance_after, ref_type, str(ref_id) if ref_id else None, remark))

            return True
    except sqlite3.Error as e:
        logger.warning('[积分] grant_credits(legacy) 失败 user_id=%s amount=%s: %s', user_id, amount, e)
        return False


def _refresh_single_pool(db, pool, now):
    """刷新单个会员积分池。返回 True 如果刷新了。"""
    pe = pool.get('period_end')
    if not pe:
        return False

    try:
        period_end_dt = datetime.strptime(pe[:19], '%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        return False

    if now < period_end_dt:
        return False

    plan_key = pool.get('subscription_plan')
    if not plan_key or plan_key not in SUBSCRIPTION_CREDITS:
        plan_key = 'monthly'

    refresh_amount = SUBSCRIPTION_CREDITS[plan_key]['monthly_credits']

    # 计算新周期（跳过已过期周期）
    new_start = period_end_dt
    new_end = _calculate_period_end(plan_key, new_start)
    while new_end < now:
        new_start = new_end
        new_end = _calculate_period_end(plan_key, new_start)

    new_end_str = new_end.strftime('%Y-%m-%d %H:%M:%S')
    new_start_str = new_start.strftime('%Y-%m-%d %H:%M:%S')

    db.execute(
        '''UPDATE credit_pools SET balance = ?, period_start = ?,
           period_end = ?, total_earned = total_earned + ?,
           updated_at = datetime('now', 'localtime')
           WHERE id = ?''',
        (refresh_amount, new_start_str, new_end_str, refresh_amount, pool['id'])
    )

    plan_name = SUBSCRIPTION_CREDITS[plan_key]['name']
    db.execute('''
        INSERT INTO credit_transactions
            (user_id, type, amount, balance_after, ref_type, remark, pool_id, pool_type)
        VALUES (?, 'refresh', ?, ?, 'auto_refresh', ?, ?, 'subscription')
    ''', (pool.get('user_id', ''), refresh_amount, refresh_amount,
          f'会员积分刷新({plan_name})', pool['id']))

    logger.info('用户 %s 会员积分已刷新: %d, 新周期: %s ~ %s',
                pool.get('user_id', ''), refresh_amount, new_start_str, new_end_str)
    return True


def refresh_subscription_credits(user_id):
    """懒刷新：检查用户会员积分池是否需要刷新"""
    if not user_id:
        return
    db = get_db()
    try:
        _ensure_pool_for_user(db, user_id)
    except Exception:
        return

    pools = db.execute(
        '''SELECT id, balance, period_end, subscription_plan, user_id
           FROM credit_pools
           WHERE user_id = ? AND pool_type = 'subscription' AND is_active = 1''',
        (user_id,)
    ).fetchall()

    if not pools:
        return

    now = datetime.now()
    needs_sync = False

    for pool in pools:
        pool_dict = dict(pool)
        if _refresh_single_pool(db, pool_dict, now):
            needs_sync = True

    if needs_sync:
        _sync_user_credits(db, user_id)
        db.commit()

def check_credit_sufficient(user_id, estimated_cost):
    """检查积分是否足够，返回 bool"""
    if not user_id:
        return False
    balance = get_user_credits(user_id)
    return balance >= estimated_cost


def get_credit_transactions(user_id, limit=20):
    """获取用户积分流水（最近N条）"""
    if not user_id:
        return []
    db = get_db()
    rows = db.execute('''
        SELECT * FROM credit_transactions
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ?
    ''', (user_id, limit)).fetchall()
    return [dict(r) for r in rows]


# ============================================================
# 评分计算（以下全部不变）
# ============================================================

def calculate_scan_cost(total_lines, is_full_scan=None, scan_mode='free', language_type='standard'):
    """
    计算扫描消耗积分（按代码行数计费）。
    - free：免费检查，0积分
    - quick：快速检查，1积分/300行（基础价）
    - smart：智能检查，2积分/300行（AI语义×2）
    - deep：深度检查，4积分/300行（AI深度×4）
    
    兼容旧接口：is_full_scan=True 等价于 scan_mode='quick'
    """
    if total_lines <= 0:
        return 0
    
    # 兼容旧接口：如果传了is_full_scan，转换为scan_mode
    if is_full_scan is not None:
        if not is_full_scan:
            return 0
        # is_full_scan=True 且没指定scan_mode时，默认quick
        if scan_mode == 'free':
            scan_mode = 'quick'
    
    # free模式完全免费
    if scan_mode == 'free':
        return 0
    
    # 各模式每300行的积分
    mode_rates = {
        'quick': 1,   # 1积分/300行
        'smart': 2,   # 2积分/300行（AI语义）
        'deep': 4,    # 4积分/300行（AI深度）
    }
    
    rate = mode_rates.get(scan_mode, 1)  # 默认按quick算
    units = math.ceil(total_lines / 300)
    return units * rate


def count_total_lines(files_dict):
    """
    统计所有源文件的总有效代码行数（简化版：非空行）。
    files_dict: {path: content} 字典
    返回：总代码行数
    """
    total = 0
    for content in files_dict.values():
        lines = content.split('\n')
        for line in lines:
            if line.strip():  # 非空行
                total += 1
    return total


def score_to_grade(score):
    """分数转等级 - 单层最高只有S
    综合SSS由"三层全S"叠加得出，单层不设SS/SSS
    """
    if score >= SCORE_S_THRESHOLD:
        return 'S'
    if score >= SCORE_A_THRESHOLD:
        return 'A'
    if score >= SCORE_B_THRESHOLD:
        return 'B'
    if score >= SCORE_C_THRESHOLD:
        return 'C'
    return 'D'

def score_color(score):
    """分数对应颜色"""
    if score >= SCORE_S_THRESHOLD:
        return '#10b981'  # success green
    if score >= SCORE_COLOR_AMBER:
        return '#f59e0b'  # warning amber
    return '#ef4444'  # danger red


def calculate_tier_scores(all_issues, available_brain_ids=None, is_vip=True):
    """计算三层评分和各自评级
    层内 brain 加权平均（按权重配置），三层之间平权
    免费版：检测维度不全，单层评级上限为 A（保证评分严谨）
    专业版：单层最高 S，三层全 S 即为 SSS
    """
    tier_scores = {}
    for tier in TIERS:
        all_brain_ids = tier['brain_ids']
        weights = tier.get('weights', {})

        if available_brain_ids:
            tier_brain_ids = [bid for bid in all_brain_ids if bid in available_brain_ids]
        else:
            tier_brain_ids = list(all_brain_ids)

        if not tier_brain_ids:
            tier_scores[tier['key']] = {
                'score': None, 'grade': '🔒', 'brain_ids': tier_brain_ids,
                'issue_count': 0, 'locked': True
            }
            continue

        # 层内加权平均
        available_weights = {bid: weights.get(bid, 1.0/len(all_brain_ids)) for bid in tier_brain_ids}
        total_weight = sum(available_weights.values())
        if total_weight > 0:
            normalized_weights = {bid: w/total_weight for bid, w in available_weights.items()}
        else:
            normalized_weights = {bid: 1.0/len(tier_brain_ids) for bid in tier_brain_ids}

        weighted_score = 0
        total_issues = 0
        for bid in tier_brain_ids:
            brain_issues = [i for i in all_issues if str(i.get('brain_id')) == bid]
            brain_score = calculate_dimension_score(brain_issues)
            weighted_score += brain_score * normalized_weights[bid]
            total_issues += len(brain_issues)

        raw_score = int(round(weighted_score))
        grade = score_to_grade(raw_score)

        # 免费版单层上限 A
        if not is_vip and grade == 'S':
            grade = 'A'

        tier_scores[tier['key']] = {
            'score': raw_score,
            'grade': grade,
            'brain_ids': tier_brain_ids,
            'issue_count': total_issues,
            'locked': False,
        }
    return tier_scores

def calculate_overall_grade(tier_scores):
    """三层综合评级"""
    unlocked = [v for v in tier_scores.values() if not v.get('locked') and v.get('score') is not None]
    if not unlocked:
        return 'S'

    grade_order = {'S': 4, 'A': 3, 'B': 2, 'C': 1, 'D': 0}
    s_count = sum(1 for t in unlocked if t['grade'] == 'S')
    total = len(unlocked)

    if s_count == total:
        if total >= len(TIERS):
            return 'SSS'
        if total == 2:
            return 'SS'
        return 'S'

    if s_count > 0:
        non_s_grades = [t['grade'] for t in unlocked if t['grade'] != 'S']
        worst_non_s = min(non_s_grades, key=lambda g: grade_order.get(g, 99))
        if s_count >= 2:
            return f'SS{worst_non_s}'
        return f'S{worst_non_s}'

    worst = min(unlocked, key=lambda t: grade_order.get(t['grade'], 99))
    return worst['grade']


def get_grade_base(grade_str):
    """从等级字符串中提取基础等级"""
    if not grade_str:
        return 'D'
    grade_str = str(grade_str).strip().upper()
    if len(grade_str) == 1 and grade_str in 'SABCD':
        return grade_str
    if '+' in grade_str:
        first = grade_str[0]
        if first in 'SABCD':
            return first
    order = ['S', 'A', 'B', 'C', 'D']
    worst_rank = -1
    for ch in grade_str:
        if ch in order:
            rank = order.index(ch)
            if rank > worst_rank:
                worst_rank = rank
    if worst_rank >= 0:
        return order[worst_rank]
    return 'D'


@app.template_filter('grade_base')
def grade_base_filter(grade_str):
    return get_grade_base(grade_str)


def calculate_score(issues, available_brain_ids=None):
    """加权扣分制计算综合得分"""
    if available_brain_ids:
        issues = [i for i in issues if str(i.get('brain_id', '')) in available_brain_ids]

    critical_count = sum(1 for i in issues if i.get('severity') == 'critical' or i.get('severity') == 'blocker')
    high_count = sum(1 for i in issues if i.get('severity') in ('high', 'suspicious'))
    medium_count = sum(1 for i in issues if i.get('severity') in ('medium', 'correctness', 'restriction', 'warning'))
    low_count = sum(1 for i in issues if i.get('severity') in ('low', 'style', 'info', 'minor'))

    deduction_critical = critical_count * DEDUCTION_PER_CRITICAL
    deduction_high = high_count * DEDUCTION_PER_HIGH
    deduction_medium = min(medium_count * DEDUCTION_PER_MEDIUM, MAX_DEDUCTION_MEDIUM)
    deduction_low = min(low_count * DEDUCTION_PER_LOW, MAX_DEDUCTION_LOW)

    total_deduction = deduction_critical + deduction_high + deduction_medium + deduction_low
    score = max(0, int(round(MAX_SCORE - total_deduction)))
    return score


def calculate_dimension_score(issues):
    """计算单个维度的得分"""
    return calculate_score(issues)


_BB_DIMENSION_RULES = {
    'one_module_one_thing': {
        'name': '职责清晰',
        'desc': '每个模块只做一件事，文件不超过300行',
        'rule_ids': {'ARCH-BB-001', 'ARCH-BB-003'},
    },
    'one_func_one_thing': {
        'name': '函数精简',
        'desc': '每个函数简短聚焦，50行以内为优秀',
        'rule_ids': {'ARCH-BB-002'},
    },
    'one_module_one_entry': {
        'name': '入口统一',
        'desc': '模块通过统一入口暴露能力，不散乱',
        'rule_ids': {'ARCH-BB-004'},
    },
    'one_module_one_test': {
        'name': '测试完备',
        'desc': '每个模块自带测试，改完能自动验证',
        'rule_ids': {'ARCH-BB-006'},
    },
    'clean_splicing': {
        'name': '依赖干净',
        'desc': '模块间依赖关系清晰，无循环引用',
        'rule_ids': {'ARCH-BB-005'},
    },
}


def calculate_building_block_scores(issues, file_count=0):
    """计算积木架构五维得分（百分制）"""
    has_any_bb = any(
        str(iss.get('check_id') or iss.get('rule_id', '')).startswith('ARCH-BB-')
        for iss in issues
    )

    result = {}
    for key, dim in _BB_DIMENSION_RULES.items():
        dim_issues = [
            iss for iss in issues
            if str(iss.get('check_id') or iss.get('rule_id', '')) in dim['rule_ids']
        ]
        score = calculate_score(dim_issues) if dim_issues else 100
        grade = score_to_grade(score)
        result[key] = {
            'name': dim['name'],
            'desc': dim['desc'],
            'score': score,
            'grade': grade,
            'issue_count': len(dim_issues),
            'detected': True,
        }
    return result

def severity_label(severity):
    """严重程度中文标签"""
    labels = {
        'critical': '严重',
        'high': '高危',
        'medium': '中等',
        'low': '轻微',
    }
    return labels.get(severity, severity)
