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
    FREE_BRAIN_IDS, FREE_BRAIN_ID_SET, ALL_BRAIN_IDS, BRAINS, BRAINS_MAP, brain_label,
    TIERS, TIERS_MAP,
    SCORE_S_THRESHOLD, SCORE_A_THRESHOLD, SCORE_B_THRESHOLD, SCORE_C_THRESHOLD,
    SCORE_COLOR_AMBER, MAX_SCORE,
    DEDUCTION_PER_CRITICAL, DEDUCTION_PER_HIGH, DEDUCTION_PER_MEDIUM, DEDUCTION_PER_LOW,
    MAX_DEDUCTION_MEDIUM, MAX_DEDUCTION_LOW,
    DEFAULT_CREDIT_TX_LIMIT,
    DAILY_LIMIT_FREE, DAILY_LIMIT_REGISTERED,
    SUBSCRIPTION_CREDITS, CREDIT_PACKS,
)
from .db import get_db
from .helpers import is_vip_user
# 2026-11-04: 维度「查没查」的判据只有 modules/dimensions.py 一份。
# 试扫页和正式报告页都从这里读，避免同一份台账两套口径。
from .dimensions import (
    engine_ready as _engine_ready,
    coverage_ok as _coverage_ok,
    COVERAGE_CAVEAT as _COVERAGE_CAVEAT,
    NOT_RUN as _DIM_NOT_RUN,
    PARTIAL as _DIM_PARTIAL,
    STATUS_TEXT as _DIM_STATUS_TEXT,
)
# 2026-11-22: 「这条问题我们认不认」只有 report_verdict 一处判据。
# 评分必须用它，否则会出现「报告说这条不成立、分数照扣」。
from .report_verdict import is_review_excluded as _is_review_excluded


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
    """确保 credit_pools 表存在（首次运行时自动创建），并补齐 is_legacy 字段。"""
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
                is_legacy INTEGER NOT NULL DEFAULT 1,
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

    # 幂等迁移：已存在的表补 is_legacy 字段（默认 1=旧价，存量池全按旧价）
    try:
        db.execute('ALTER TABLE credit_pools ADD COLUMN is_legacy INTEGER NOT NULL DEFAULT 1')
        db.commit()
    except sqlite3.OperationalError:
        pass  # 字段已存在


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
           ORDER BY is_legacy DESC, priority ASC, period_end ASC''',
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
           ORDER BY is_legacy DESC, priority ASC, period_end ASC''',
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
                   ORDER BY is_legacy DESC, priority ASC, period_end ASC''',
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

    2026-10-28 治本：对带 ref_id 的支付类发放做幂等防重。
    同一 (ref_type, ref_id) 已发放过积分则直接返回 True（不重复发），
    避免支付回调并发/重复轮询时「UPDATE 与 grant 不在同一事务」的 TOCTOU
    竞态导致同一订单重复发积分。
    """
    if not user_id or amount <= 0:
        return False
    db = get_db()
    _ensure_pool_for_user(db, user_id)

    # 幂等防重：仅对「支付类」发放（有明确 ref_id 作为业务唯一键）做去重。
    # 支付类 ref_type 集合 = 订单发放 + 充值 + 订阅（推荐奖励 ref_id 是订单号，也纳入）。
    _pay_ref_types = ("credit_pack", "topup", "subscription")
    if ref_type in _pay_ref_types and ref_id:
        try:
            dup = db.execute(
                '''SELECT 1 FROM credit_transactions
                   WHERE user_id = ? AND type = 'grant' AND ref_type = ? AND ref_id = ?
                   LIMIT 1''',
                (user_id, ref_type, str(ref_id))
            ).fetchone()
            if dup:
                logger.info(
                    '[积分] 幂等跳过重复发放 user_id=%s ref_type=%s ref_id=%s',
                    user_id, ref_type, ref_id
                )
                return True
        except sqlite3.Error as e:
            # 防重查询失败不阻断发放（fail-open，宁可重复也不漏发），仅告警。
            logger.warning('[积分] 幂等检查失败 user_id=%s: %s', user_id, e)

    # 根据 ref_type 决定写入哪个池，并确定 is_legacy（新旧价标记）
    # is_legacy=1 → 旧价（涨价前存量 / 补偿老用户）；is_legacy=0 → 新价（涨价后付费）。
    meta = {'ref_type': ref_type, 'ref_id': ref_id, 'remark': remark, 'is_legacy': 0}
    if ref_type == 'subscription':
        # 会员续费按新价（is_legacy=0）；已有订阅池复用不改变其原有新旧标记
        return _grant_to_subscription_pool(db, user_id, amount, meta)
    elif ref_type in ('credit_pack', 'topup', 'referral_register', 'referral_recharge', 'referral_first_pay'):
        # 积分包、充值、推荐奖励统一走积分包池，有效期365天，涨价后按新价
        return _grant_to_pack_pool(db, user_id, amount, meta)
    elif ref_type == 'compensation':
        # 版本更新补偿：发给老用户，按旧价（is_legacy=1），走积分包池
        meta['is_legacy'] = 1
        return _grant_to_pack_pool(db, user_id, amount, meta)
    elif ref_type in ("scan_refund", "refund"):
        # 退款回到已有的最大 pack 池，不新建池，防止碎片化；新旧跟随目标池
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
                priority, subscription_plan, is_active, is_legacy)
               VALUES (?, ?, 'subscription', ?, ?, ?, ?, 1, ?, 1, 0)''',
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
    """积分写入积分包池（新池，有效期365天）。
    is_legacy 由 credit_meta 指定：1=旧价（补偿），0=新价（付费充值）。"""
    ref_type = credit_meta.get('ref_type')
    ref_id = credit_meta.get('ref_id')
    remark = credit_meta.get('remark', '')
    is_legacy = credit_meta.get('is_legacy', 0)
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
                    priority, subscription_plan, is_active, is_legacy)
                   VALUES (?, ?, 'pack', ?, ?, ?, ?, ?, NULL, 1, ?)''',
                (pool_id, user_id, amount, amount, now, period_end, priority, is_legacy)
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
                    "INSERT INTO credit_pools (id, user_id, pool_type, balance, total_earned, period_start, period_end, priority, subscription_plan, is_active, is_legacy) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, 1, ?)",
                    (pool_id, user_id, "pack", amount, amount, now, period_end, priority, credit_meta.get("is_legacy", 0))
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

# v7.0 定价调整（2026-10-30）：计费基数 300行->100行，倍率 1/2/4 -> 1/4/10
# 老用户（2026-10-30 前注册）存量积分按旧价锁定，新价只对新用户/新充值生效。
PRICING_CUTOFF_DATE = '2026-10-30'

# 新价：每 100 行的积分
NEW_MODE_RATES = {
    'quick': 1,    # 1积分/100行（基础规则，引流档）
    'smart': 4,    # 4积分/100行（AI语义分析）
    'deep': 10,    # 10积分/100行（AI深度 + PoC实弹验证）
}
# 旧价：每 300 行的积分（老用户存量锁定用）
OLD_MODE_RATES = {
    'quick': 1,
    'smart': 2,
    'deep': 4,
}
OLD_UNIT_LINES = 300   # 旧价计费基数
NEW_UNIT_LINES = 100   # 新价计费基数


def _legacy_credit_balance(user_id):
    """查询用户「旧价积分」余额：is_legacy=1 的活跃池余额之和。
    无池用户回退 user_credits 表存量（都是涨价前存量，视为旧积分）。
    查询失败返回 0（保守，按新价，绝不阻塞扫描主流程）。
    """
    if not user_id:
        return 0
    try:
        db = get_db()
        _ensure_pool_for_user(db, user_id)
        pool_cnt = db.execute(
            'SELECT COUNT(*) AS c FROM credit_pools WHERE user_id = ? AND is_active = 1',
            (user_id,)
        ).fetchone()['c']
        if pool_cnt == 0:
            # 无池：user_credits 存量全算旧积分
            row = db.execute(
                'SELECT balance FROM user_credits WHERE user_id = ?', (user_id,)
            ).fetchone()
            return row['balance'] if row else 0
        row = db.execute(
            'SELECT COALESCE(SUM(balance), 0) AS t FROM credit_pools '
            'WHERE user_id = ? AND is_active = 1 AND is_legacy = 1',
            (user_id,)
        ).fetchone()
        return row['t'] if row else 0
    except Exception:
        return 0


def calculate_scan_cost(total_lines, is_full_scan=None, scan_mode='free',
                        language_type='standard', user_id=None):
    """
    计算扫描消耗积分（按代码行数计费，分段计价）。

    规则（v7.0 定价，2026-10-30）：
    - free：免费，0 积分。
    - quick/smart/deep：见 NEW_MODE_RATES（新价，每100行 1/4/10 倍）或
      OLD_MODE_RATES（旧价，每300行 1/2/4 倍）。

    分段计价（只治本，公平）：
    - 旧积分（涨价前存量 + 补偿，is_legacy=1）优先按旧价抵扣；
    - 旧积分不足以覆盖整单时，剩余行数按新价、用新积分支付；
    - 新用户 / 无旧积分 → 全部按新价。

    兼容旧接口：is_full_scan=True 等价于 scan_mode='quick'。
    """
    if total_lines <= 0:
        return 0

    # 兼容旧接口：如果传了is_full_scan，转换为scan_mode
    if is_full_scan is not None:
        if not is_full_scan:
            return 0
        if scan_mode == 'free':
            scan_mode = 'quick'

    # free模式完全免费
    if scan_mode == 'free':
        return 0

    old_rate = OLD_MODE_RATES.get(scan_mode, 1)
    new_rate = NEW_MODE_RATES.get(scan_mode, 1)

    legacy_bal = _legacy_credit_balance(user_id)

    # 无旧积分：全部新价
    if legacy_bal <= 0:
        return math.ceil(total_lines / NEW_UNIT_LINES) * new_rate

    # 按旧价整单需要的积分
    old_cost = math.ceil(total_lines / OLD_UNIT_LINES) * old_rate
    if legacy_bal >= old_cost:
        # 旧积分足够覆盖整单：全部旧价
        return old_cost

    # 旧积分只够覆盖部分：按完整旧价单位抵扣，剩余行数按新价
    old_units = legacy_bal // old_rate
    covered_lines = old_units * OLD_UNIT_LINES
    remaining_lines = max(0, total_lines - covered_lines)
    new_cost = math.ceil(remaining_lines / NEW_UNIT_LINES) * new_rate
    return (old_units * old_rate) + new_cost


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


# 等级的中文读法。只在这里写一次，试扫页、报告页、导出都用它。
GRADE_TEXT = {
    'SSS': '优秀', 'SS': '优秀', 'S': '优秀',
    'A': '优秀', 'B': '良好', 'C': '及格', 'D': '较差',
    '—': '未完整检测',
}


def grade_of(score, tier_scores=None, is_vip=True):
    """综合等级的唯一出口 —— 先由分数定档，再看三层是否全 S。

    ============================================================
    为什么要这么写（2026-11-22）
    ============================================================

    以前是两套算法各说各话：

      综合得分   calculate_score        对全部告警求和扣分（10/5/3/0.5）
      综合等级   calculate_overall_grade 三层各自算「引擎加权平均」再叠加

    平均法会把问题摊薄，求和法不会。于是同一份报告可以同时写着
    「46 分」和「S 级」。量过全库 441 份完成扫描，76 份（17.2%）
    这两个数打架，最极端那份就是 46 分评 S。

    等级是分数的读法，不是第二套算法。所以：
      * 档位只由 score_to_grade(分数) 决定；
      * SS/SSS 是「已经是 S 之后」的附加荣誉，门槛抬到分数先到 S 线，
        再要求三层都拿到 S。分数不够 S，层再漂亮也不给。

    免费版：等级上限 A（检测维度不全不评 S）。这一条必须在页面上写明，
    否则「100 分却是 A 级」看上去像自相矛盾。
    """
    if score is None:
        return '—'

    # 一层都没查成时不许拿分数说话：0 条问题算出来的 100 分
    # 是「没看」而不是「干净」，给 S 等于把没查的地方当成没问题。
    if tier_scores:
        _graded = [
            v for v in tier_scores.values()
            if not v.get('locked') and v.get('score') is not None
        ]
        if not _graded and any(v.get('incomplete') for v in tier_scores.values()):
            return '—'

    try:
        grade = score_to_grade(int(round(float(score))))
    except (TypeError, ValueError):
        return '—'

    if grade == 'S' and tier_scores:
        # 只数「有成绩且查全」的层：查不全的层不参与 SSS/SS 的叠加，
        # 拿一个「已查部分」的分数去拼 SSS，等于把没查的地方当成干净。
        layers = [
            v for v in tier_scores.values()
            if not v.get('locked') and v.get('score') is not None
            and not v.get('incomplete')
        ]
        if layers and all(v.get('grade') == 'S' for v in layers):
            if len(layers) >= len(TIERS):
                grade = 'SSS'
            elif len(layers) == 2:
                grade = 'SS'

    if not is_vip and grade in ('S', 'SS', 'SSS'):
        grade = 'A'
    return grade


def score_color(score):
    """分数对应颜色"""
    if score >= SCORE_S_THRESHOLD:
        return '#10b981'  # success green
    if score >= SCORE_COLOR_AMBER:
        return '#f59e0b'  # warning amber
    return '#ef4444'  # danger red


def calculate_tier_scores(all_issues, available_brain_ids=None, is_vip=True,
                          engines=None, unsupported=0, trimmed=0, file_count=None):
    """计算三层评分和各自评级
    层内 brain 加权平均（按权重配置），三层之间平权
    免费版：检测维度不全，单层评级上限为 A（保证评分严谨）
    专业版：单层最高 S，三层全 S 即为 SSS

    2026-11-04：加 engines（引擎台账）。原来这一层只看 all_issues，
    引擎崩了/被降级/文件没解析都表现为「没有 issues」，于是照样按 100 分
    算进加权平均——引擎没跑反而最容易拿满分。现在的规则：
      1. 只有台账确认「查全了」的引擎参与打分，缺的那部分权重不许用 100 分顶上；
      2. 层内只要有引擎没查全，这层不给等级（grade='—'），标「未完整检测」。
    engines 为 None（2026-11-04 之前落库的报告）时退回旧行为，老报告不受影响。

    2026-11-22：把「引擎没跑」和「文件没读到」拆开判，判据分别是
    `engine_ready`（真跑了且没报错）和 `coverage_ok`（读到的文件过半数）。
    改之前两者都混在 card_state 的 PARTIAL 里，于是一份 5 文件的项目
    只因为 1 个文件没解析，三层全变成「未检测」——而同一页上明明列着
    14 个查出来的问题。查出问题的报告不能说「没检测」。
    """
    tier_scores = {}
    _cov_ok = _coverage_ok(file_count, unsupported, trimmed)
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
                'issue_count': 0, 'locked': True, 'incomplete': False, 'status_text': '',
            }
            continue

        # 台账里查出这层哪些引擎真跑了（跑了且没报错）。
        if engines:
            ok_brain_ids = [
                bid for bid in tier_brain_ids if _engine_ready(engines, bid)
            ]
        else:
            ok_brain_ids = list(tier_brain_ids)
        missing_brain_ids = [bid for bid in tier_brain_ids if bid not in ok_brain_ids]
        tier_issue_count = sum(1 for i in all_issues if str(i.get('brain_id')) in tier_brain_ids)

        if not ok_brain_ids or not _cov_ok:
            # 这一层一个引擎都没查成，或者读到的文件不够多：没有分数，只有状态。
            # 给 100 分是骗人。
            _why = _DIM_STATUS_TEXT[_DIM_NOT_RUN] if not ok_brain_ids else '覆盖不足'
            tier_scores[tier['key']] = {
                'score': None, 'grade': '—', 'brain_ids': tier_brain_ids,
                'issue_count': tier_issue_count, 'locked': False,
                'incomplete': True, 'status_text': _why,
                'missing_brain_ids': missing_brain_ids,
            }
            continue

        # 层内加权平均——只在查全的引擎里归一化，缺的引擎不占权重
        available_weights = {bid: weights.get(bid, 1.0/len(all_brain_ids)) for bid in ok_brain_ids}
        total_weight = sum(available_weights.values())
        if total_weight > 0:
            normalized_weights = {bid: w/total_weight for bid, w in available_weights.items()}
        else:
            normalized_weights = {bid: 1.0/len(ok_brain_ids) for bid in ok_brain_ids}

        weighted_score = 0
        total_issues = 0
        for bid in ok_brain_ids:
            brain_issues = [i for i in all_issues if str(i.get('brain_id')) == bid]
            brain_score = calculate_dimension_score(brain_issues)
            weighted_score += brain_score * normalized_weights[bid]
            total_issues += len(brain_issues)

        raw_score = int(round(weighted_score))
        grade = score_to_grade(raw_score)

        # 免费版单层上限 A
        if not is_vip and grade == 'S':
            grade = 'A'

        # 查不全就不给等级。分数只是「已查部分」的成绩，不是这一层的结论。
        incomplete = bool(missing_brain_ids)
        if incomplete:
            grade = '—'
        # 成绩可用的前提下，有文件没读进来仍要说一句：这层分只覆盖已解析的代码。
        status_text = ''
        if incomplete:
            status_text = _DIM_STATUS_TEXT[_DIM_PARTIAL]
        elif unsupported or trimmed:
            status_text = _COVERAGE_CAVEAT

        tier_scores[tier['key']] = {
            'score': raw_score,
            'grade': grade,
            'brain_ids': tier_brain_ids,
            'issue_count': total_issues,
            'locked': False,
            'incomplete': incomplete,
            'status_text': status_text,
            'missing_brain_ids': missing_brain_ids,
        }
    return tier_scores


# 2026-11-22 删除 calculate_overall_grade（三层平均法）。
# 它和 calculate_score（求和法）是两套独立算法，同一份报告能同时得出
# 「46 分」和「S 级」。等级改由 grade_of(分数, tier_scores) 一个出口给出：
# 档位看分数，三层全 S 只作为 S 之上的附加值。别再把它加回来。


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


@app.template_filter('brain_label')
def brain_label_filter(brain_id):
    """模板内引擎显示名：{{ issue.brain_id | brain_label }} -> 'E3 性能与可靠性'"""
    return brain_label(brain_id)


def calculate_score(issues, available_brain_ids=None, include_excluded=False):
    """加权扣分制计算综合得分 —— 代码健康分的唯一算法。

    2026-11-22：默认剔除「复核未采纳」的条目。

    改之前，报告页一边列着「复核未采纳 10 条」，一边拿这 10 条扣掉 32 分：
    结论说「只有 2 个问题必须修」，分数说 50 分 C 级。同一页两个说法。

    「复核未采纳」是规则报出来了、但复核判定不成立且把握够（>=80）的条目，
    它们仍然单列在报告里供用户核对，但不能既说「不成立」又拿来扣分。
    判据只有 report_verdict.is_review_excluded 一份，这里不重写。

    include_excluded=True 只留给「想看规则原始严格度」的场合，页面不许用。
    """
    if not include_excluded:
        issues = [i for i in issues if not _is_review_excluded(i)]
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
    # 编号必须是引擎真正产出的那个（`E5-ARCH-BB-00x`），
    # 少 `E5-` 前缀就会全部落空 —— 这张表曾经就是这个错，五维因此永远 100 分。
    'one_module_one_thing': {
        'name': '职责清晰',
        'desc': '每个模块只做一件事，文件不超过300行',
        'rule_ids': ('E5-ARCH-BB-001', 'E5-ARCH-BB-003'),
        # 历史写法：引擎早期出口把 001/002/003 改成了 3S 编号，
        # 2026-11-04 之前的报告里存的是这些；无前缀版是更早的一张错表。
        'legacy_ids': ('E5-ARCH-3S-001', 'E5-ARCH-3S-003',
                       'ARCH-BB-001', 'ARCH-BB-003'),
    },
    'one_func_one_thing': {
        'name': '函数精简',
        'desc': '每个函数简短聚焦，50行以内为优秀',
        'rule_ids': ('E5-ARCH-BB-002',),
        'legacy_ids': ('E5-ARCH-3S-002', 'ARCH-BB-002'),
    },
    'one_module_one_entry': {
        'name': '入口统一',
        'desc': '模块通过统一入口暴露能力，不散乱',
        'rule_ids': ('E5-ARCH-BB-004',),
        'legacy_ids': ('ARCH-BB-004',),
    },
    'one_module_one_test': {
        'name': '测试完备',
        'desc': '每个模块自带测试，改完能自动验证',
        'rule_ids': ('E5-ARCH-BB-006',),
        'legacy_ids': ('ARCH-BB-006',),
    },
    'clean_splicing': {
        'name': '依赖干净',
        'desc': '模块间依赖关系清晰，无循环引用',
        'rule_ids': ('E5-ARCH-BB-005',),
        'legacy_ids': ('ARCH-BB-005',),
    },
}

# 积木五维由 E5（架构与部署引擎）独家负责
_BB_BRAIN_ID = '5'
# 这几个级别一出现，这一维就不该是最高等级
_BB_SEVERE_LEVELS = ('critical', 'blocker', 'high', 'suspicious')


def _bb_issue_ids(issue):
    """一条 issue 身上所有能代表「这条规则报过」的编号。

    cross_engine_dedup 把同一 (file, line, 类别) 的多条问题合成一条，
    被合并的规则不单独出现在 issues[] 里，只挂在幸存那条的
    also_detected_by / root_cause_merged 上。只读 check_id 会漏掉一整半 ——
    实测积木规则里的 BB-003 每次都走这条路。
    """
    ids = set()
    for key in ('check_id', 'rule_id'):
        v = issue.get(key)
        if v:
            ids.add(str(v))
    for key in ('also_detected_by', 'root_cause_merged'):
        for merged in issue.get(key) or []:
            if not isinstance(merged, dict):
                continue
            for k in ('rule_id', 'check_id', 'vuln_category'):
                v = merged.get(k)
                if v:
                    ids.add(str(v))
    return ids


def _bb_engine_checked(engines):
    """积木这一维的引擎到底跑成没有。

    True 跑成了 / False 没跑成或报错 / None 没有台账（老报告）。
    老报告不能判 False —— 那时候根本没记录这个事实，凭空判"没跑"
    等于制造另一种假。历史报告维持原行为，新报告才按台账走。
    """
    if not isinstance(engines, dict) or not engines:
        return None
    st = engines.get(_BB_BRAIN_ID)
    if st is None:
        st = engines.get(int(_BB_BRAIN_ID))
    if st is None:
        # 台账里有别的引擎、独独没有 E5 = 这次根本没请求架构引擎。
        # 这和"整个台账都没有"（老报告）是两件事，不能都当成不确定。
        return False
    if not isinstance(st, dict) or not st:
        return None
    return bool(st.get('executed')) and not bool(st.get('error'))


def calculate_building_block_scores(issues, file_count=0, style_issues=None, engines=None):
    """计算积木架构五维得分（百分制）。

    三个输入缺一不可：

    issues        主结果（含被合并的规则，见 _bb_issue_ids）
    style_issues  AI 复审降级后分流出去的问题。规则确实报了、证据确实在，
                  只是被判"影响有限"。丢掉它们等于"查出来了但装作没看见"，
                  「入口统一」「测试完备」两维会因此永远满分。
    engines       引擎台账。E5 没跑成时显示「未检测」，不是 100 分。
    """
    pool = list(issues or []) + list(style_issues or [])
    engine_checked = _bb_engine_checked(engines)

    result = {}
    for key, dim in _BB_DIMENSION_RULES.items():
        want = set(dim['rule_ids']) | set(dim.get('legacy_ids') or ())
        dim_issues = []
        for iss in pool:
            if not isinstance(iss, dict):
                continue
            # 一条 issue 可能同时代表多条规则（跨引擎去重把同 file/line 的合并了），
            # 每条命中的规则各算一个问题 —— 按 issue 计数会把
            # 「文件太长」和「职责混杂」算成一个，维度和总分都低估。
            for _ in sorted(_bb_issue_ids(iss) & want):
                dim_issues.append(iss)

        if engine_checked is False:
            # 没查过的维度不给分：0 分会混进总分和雷达图，等于拿"没查"当"查了没问题"
            result[key] = {
                'name': dim['name'],
                'desc': dim['desc'],
                'score': None,
                'grade': None,
                'issue_count': len(dim_issues),
                'detected': False,
            }
            continue

        score = calculate_score(dim_issues) if dim_issues else 100
        # low 一档扣 0.5 分，calculate_score 最后 int(round()) 会把它抹回整数：
        # 1 条 low 扣了分、分数却还是 100，页面就成了「满分 + 有问题」。
        # 扣过就必须落到 100 以下。
        if dim_issues and score >= 100:
            score = 99
        grade = score_to_grade(score)
        # S 级阈值 95，一条 high 只扣 5 分 → 95 分仍是 S。
        # 「S 级 + 一条高危」和「安全 100 分 + 越权高危」是同一种自相矛盾：
        # 最高等级的含义就是没有严重缺陷，有高危就不给 S。
        if grade == 'S' and any(
            str(i.get('severity') or '').lower() in _BB_SEVERE_LEVELS
            for i in dim_issues
        ):
            grade = 'A'
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
