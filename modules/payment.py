"""Xinpect - Payment system (MenFang integration + orders)"""
import hashlib
import json
import os
import threading
import time
import uuid
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify, session

from .constants import (
    app, logger,
    MENFANG_BASE_URL, MENFANG_TIMEOUT_SECONDS, MENFANG_PAY_TIMEOUT_SECONDS,
    SUBSCRIPTION_CREDITS, CREDIT_PACKS, TOPUP_CREDITS_MAP,
    DEFAULT_SUBSCRIPTION_DAYS, DEFAULT_MONTHLY_CREDITS,
    HTTP_OK, HTTP_BAD_REQUEST, HTTP_UNAUTHORIZED, HTTP_NOT_FOUND, HTTP_FORBIDDEN, HTTP_PAYMENT_REQUIRED,
    HTTP_INTERNAL_ERROR,
)
from .db import get_db
from .helpers import login_required, get_current_user, is_vip_user, _safe_http_post, _safe_http_get
from .scoring import get_user_credits, grant_credits, consume_credits
from .referral import process_referral_reward
from .csrf_protection import csrf_required


payment_bp = Blueprint("payment", __name__)


# 2026-10-28 治本：服务间共享密钥，官网后端调门房内网接口时带上。
# 门房订单查询接口（order-status/order）已改为需鉴权，官网带此密钥即放行。
MENFANG_INTERNAL_KEY = os.environ.get("MENFANG_INTERNAL_KEY", "")


# --- MenFang integration ---

def _menfang_ensure_registered(email: str, password_hash: str) -> bool:
    """
    确保用户在门房服务中也注册了（用于支付对接）。
    失败时标记用户需要补同步，不阻塞注册流程。
    """
    try:
        resp = _safe_http_post(
            f'{MENFANG_BASE_URL}/api/auth/register',
            json={'email': email, 'password_hash': password_hash},
            timeout=MENFANG_TIMEOUT_SECONDS
        )
        if resp.status_code in (HTTP_OK, 409):
            # 同步成功，清除补同步标记
            try:
                from modules.auth import get_db
                db = get_db()
                db.execute("UPDATE users SET mf_sync_needed = 0 WHERE email = ?", (email,))
                db.commit()
            except Exception:
                pass
            return True
        logger.warning('门房注册返回 %d for %s', resp.status_code, email)
        _mark_mf_sync_needed(email)
        return False
    except (OSError, ValueError) as e:
        logger.warning('门房同步注册失败: %s', e)
        _mark_mf_sync_needed(email)
        return False

def _mark_mf_sync_needed(email):
    """标记用户需要在支付前补同步门房"""
    try:
        from modules.auth import get_db
        db = get_db()
        # 如果字段不存在则添加
        try:
            db.execute("ALTER TABLE users ADD COLUMN mf_sync_needed INTEGER DEFAULT 0")
            db.commit()
        except Exception:
            pass  # 字段已存在
        db.execute("UPDATE users SET mf_sync_needed = 1 WHERE email = ?", (email,))
        db.commit()
    except Exception as e:
        logger.exception('标记门房同步失败: %s', e)

def _menfang_lazy_sync(email, password_hash):
    """支付前懒同步：检查是否需要补同步门房，需要则先同步再支付"""
    try:
        from modules.auth import get_db
        db = get_db()
        row = db.execute("SELECT mf_sync_needed, mf_password_hash FROM users WHERE email = ?", (email,)).fetchone()
        if row and row[0]:  # mf_sync_needed == 1
            logger.info('Lazy sync menfang for %s before payment', email)
            _menfang_ensure_registered(email, password_hash or row[1] or '')
    except RuntimeError as e:
        logger.debug('HTTP client unavailable for menfang register: %s', e)
        return False
    except Exception as e:
        logger.warning('Lazy sync check failed: %s', e)


def _menfang_login_with_hash(email: str, password_hash: str) -> str:
    """
    用 sha256 密码哈希登录门房获取 token。成功返回 token，失败返回空字符串。
    """
    try:
        resp = _safe_http_post(
            f'{MENFANG_BASE_URL}/api/auth/login',
            json={'email': email, 'password_hash': password_hash},
            timeout=MENFANG_TIMEOUT_SECONDS
        )
        data = resp.json()
        if data.get('success'):
            return data.get('token', '')
    except (OSError, ValueError) as e:
        logger.warning('门房登录失败: %s', e)
    except RuntimeError as e:
        logger.debug('HTTP client unavailable for menfang login: %s', e)
    return ''


def _menfang_create_pay_order_with_token(email: str, token: str, plan: str, amount: int) -> dict:
    """
    用 token 调用门房创建支付订单（推荐方式，避免传递密码）。
    返回: {success, order_id, qr_code_url, amount, message}
    """
    try:
        headers = {}
        if token:
            headers['Authorization'] = f'Bearer {token}'
        resp = _safe_http_post(
            f'{MENFANG_BASE_URL}/api/pay/create',
            json={
                'email': email,
                'plan': plan,
                'amount': amount
            },
            headers=headers,
            timeout=MENFANG_PAY_TIMEOUT_SECONDS
        )
        data = resp.json()
        if data.get('success'):
            return {
                'success': True,
                'order_id': data.get('order_id', ''),
                'qr_code_url': data.get('qr_code_url', ''),
                'amount': data.get('amount', amount)
            }
        return {'success': False, 'message': data.get('message', '创建订单失败')}
    except (OSError, ValueError) as e:
        logger.warning('门房创建支付订单失败: %s', e)
        return {'success': False, 'message': '支付服务暂时不可用，请稍后重试'}
    except RuntimeError as e:
        logger.debug('HTTP client unavailable: %s', e)
        return {'success': False, 'message': '支付服务暂时不可用，请稍后重试'}


def _menfang_create_pay_order_with_hash(email: str, password_hash: str, plan: str, amount: int) -> dict:
    """
    用 password_hash 直接调用门房创建支付订单（兜底方式，token 都不可用时用）。
    返回: {success, order_id, qr_code_url, amount, message}
    """
    try:
        resp = _safe_http_post(
            f'{MENFANG_BASE_URL}/api/pay/create',
            json={
                'email': email,
                'password_hash': password_hash,
                'plan': plan,
                'amount': amount
            },
            timeout=MENFANG_PAY_TIMEOUT_SECONDS
        )
        data = resp.json()
        if data.get('success'):
            return {
                'success': True,
                'order_id': data.get('order_id', ''),
                'qr_code_url': data.get('qr_code_url', ''),
                'amount': data.get('amount', amount)
            }
        else:
            return {'success': False, 'message': data.get('message', '创建订单失败')}
    except (OSError, ValueError) as e:
        logger.warning('门房创建支付订单(hash方式)失败: %s', e)
        return {'success': False, 'message': '支付服务暂时不可用，请稍后重试'}
    except RuntimeError as e:
        logger.debug('HTTP client unavailable: %s', e)
        return {'success': False, 'message': '支付服务暂时不可用，请稍后重试'}


def _menfang_get_order_status(order_id: str) -> dict:
    """
    查询门房订单支付状态。
    返回: {found, status, plan, amount, paid_at}
    """
    try:
        _headers = {}
        if MENFANG_INTERNAL_KEY:
            _headers["X-Internal-Key"] = MENFANG_INTERNAL_KEY
        resp = _safe_http_get(
            f'{MENFANG_BASE_URL}/api/pay/order-status/{order_id}',
            headers=_headers,
            timeout=MENFANG_TIMEOUT_SECONDS
        )
        if resp.status_code == 404:
            return {'found': False, 'status': 'not_found'}
        data = resp.json()
        return {
            'found': True,
            'status': data.get('status', 'unknown'),
            'plan': data.get('plan', ''),
            'amount': data.get('amount', 0),
            'paid_at': data.get('paid_at', '')
        }
    except (OSError, ValueError) as e:
        logger.warning('门房查询订单状态失败 %s: %s', order_id, e)
        return {'found': False, 'status': 'error'}
    except RuntimeError as e:
        logger.debug('HTTP client unavailable: %s', e)
        return {'found': False, 'status': 'error'}




# --- Pay routes ---

def _resolve_pay_plan(order_type, plan_id, subscription_plans, credit_packs, topup_plans):
    """解析支付套餐，返回 plan dict 或 (error_response, status_code) tuple"""
    if order_type == 'credit_pack':
        if not is_vip_user():
            return jsonify({'success': False, 'error': '积分包仅限会员购买，请先开通会员'}), HTTP_FORBIDDEN
        if plan_id not in credit_packs:
            return jsonify({'success': False, 'error': '无效的积分包'}), HTTP_BAD_REQUEST
        return credit_packs[plan_id]
    if order_type == 'topup':
        if not is_vip_user():
            return jsonify({'success': False, 'error': '次卡仅限会员购买，请先开通会员'}), HTTP_FORBIDDEN
        if plan_id not in topup_plans:
            return jsonify({'success': False, 'error': '无效的次卡套餐'}), HTTP_BAD_REQUEST
        return topup_plans[plan_id]
    if plan_id not in subscription_plans:
        import logging as _lg
        logger.warning('pay_plan_fail: plan_id=%s order_type=%s valid=%s', plan_id, order_type, list(subscription_plans.keys()))
        return jsonify({'success': False, 'error': '无效的套餐'}), HTTP_BAD_REQUEST
    return subscription_plans[plan_id]


@app.route('/api/pay/create', methods=['POST'])
@login_required
@csrf_required
def api_pay_create():
    """创建支付订单（对接门房真实微信支付）"""
    data = request.get_json() or {}
    plan_id = data.get('plan_id')
    order_type = data.get('order_type', 'subscription')  # subscription / credit_pack / topup

    # 网站套餐 → 门房套餐映射
    subscription_plans = {
        'monthly':     {'name': '月卡',   'amount': 99,  'mf_plan': 'monthly'},
        'quarterly':   {'name': '季卡',   'amount': 269, 'mf_plan': 'quarterly'},
        'half_year':   {'name': '半年卡', 'amount': 499, 'mf_plan': 'half-year'},
        'yearly':      {'name': '年卡',   'amount': 899, 'mf_plan': 'yearly'},
    }

    # v1.5: 积分包商品
    credit_packs = CREDIT_PACKS

    topup_plans = {
        'topup_1':  {'name': '次卡·1次',  'amount': 2,  'mf_plan': 'addon-1',  'credits': 1},
        'topup_5':  {'name': '次卡·5次',  'amount': 9,  'mf_plan': 'addon-5',  'credits': 5},
        'topup_10': {'name': '次卡·10次', 'amount': 16, 'mf_plan': 'addon-10', 'credits': 10},
    }

    plan = _resolve_pay_plan(order_type, plan_id, subscription_plans, credit_packs, topup_plans)
    if isinstance(plan, tuple):
        return plan  # 错误响应

    user = get_current_user()
    email = user.get('email', '')
    mf_token = session.get('mf_token', '')
    mf_pwd_hash = user.get('mf_password_hash', '') or ''

    # 安全加固：确保金额来自服务端定价
    assert isinstance(plan['amount'], (int, float)) and plan['amount'] > 0, "Invalid plan amount"

    # 懒同步：支付前检查门房注册状态，未同步则先补同步
    _menfang_lazy_sync(email, mf_pwd_hash)

    # 调门房创建真实支付订单（先试 token，失败就用密码哈希重登再试）
    result = _menfang_create_pay_order_with_token(email, mf_token, plan['mf_plan'], plan['amount'])

    # token 失效时用密码哈希重新登录再试
    _msg = result.get('message', '')
    _token_expired = not result['success'] and mf_pwd_hash and (
        '登录已过期' in _msg or '会话' in _msg
    )
    if _token_expired:
        new_token = _menfang_login_with_hash(email, mf_pwd_hash)
        if new_token:
            session['mf_token'] = new_token
            result = _menfang_create_pay_order_with_token(email, new_token, plan['mf_plan'], plan['amount'])

    # 还失败就用密码哈希直接调（最兜底的方式）
    if not result['success'] and mf_pwd_hash:
        result = _menfang_create_pay_order_with_hash(email, mf_pwd_hash, plan['mf_plan'], plan['amount'])

    if not result['success']:
        import logging as _lg
        logger.warning('pay_create_fail: email=%s plan=%s amount=%s reason=%s', email, plan.get('mf_plan','N/A'), plan.get('amount',0), result.get('message','unknown'))
        return jsonify({'success': False, 'error': result.get('message', '创建订单失败')}), HTTP_BAD_REQUEST

    mf_order_id = result['order_id']

    # 存本地订单（用门房的 order_id 作为关联）
    db = get_db()
    db.execute('''
        INSERT INTO orders (order_id, user_id, plan_id, plan_name, order_type, amount, status, mf_order_id)
        VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
    ''', (mf_order_id, user.get('id'), plan_id, plan['name'], order_type, plan['amount'], mf_order_id))
    db.commit()

    return jsonify({
        'success': True,
        'order_id': mf_order_id,
        'amount': plan['amount'],
        'qr_url': result.get('qr_code_url', ''),
    })



def calc_vip_expire(paid_dt, prev_expire_raw, days):
    """算出这次续费后的会员到期日。

    治本（2026-11-14）：续费必须累加，不能吞掉客户没到期的那几天。
    旧实现是 `paid_dt + days`：客户还剩 20 天到期时提前续费，新到期日被
    改写成「今天 + 30 天」，凭空吞掉 20 天——等于少给货。

    起算点取「原到期日」与「本次支付时间」的较晚者：
      还没到期 → 从原到期日往后加，剩余天数原样保留；
      已过期 / 首次开通 / 存量脏数据 → 从支付时间往后加，不倒扣。

    抽成纯函数是为了能被测试直接打靶（tests/test_membership_renewal.py）。
    """
    renew_from = paid_dt
    raw = (prev_expire_raw or '').strip()
    if raw:
        try:
            prev_expire = datetime.strptime(raw, '%Y-%m-%d %H:%M:%S')
            if prev_expire > renew_from:
                renew_from = prev_expire
        except (ValueError, TypeError):
            # 存量脏数据不该阻断开通，按首次开通处理
            pass
    return (renew_from + timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')


def _handle_credit_pack_paid(db, order, order_id, user):
    """处理积分包支付成功：更新订单状态 + 发放积分"""
    pack = CREDIT_PACKS.get(order['plan_id'])
    if not pack:
        # 认不出套餐就不许标记已付：否则订单显示已付、积分没发，
        # 等于把「收钱没给货」写进账里。报错出去让人补定价表。
        logger.error('credit_pack_paid: 订单 %s 的套餐 %r 不在定价表里，拒绝标记已付',
                     order_id, order['plan_id'])
        return jsonify({'status': 'error', 'message': '套餐未识别，请联系客服'}), HTTP_BAD_REQUEST
    credits = pack['credits']
    # 幂等（2026-11-14）：同一笔订单只许发放一次。前端轮询、后台补单、用户刷新
    # 三个来源可能同时打到这儿；无条件 UPDATE 会让积分发两遍。
    # 用「条件更新 + rowcount」当锁——SQLite 单写，这是唯一可靠的判据。
    cur = db.execute(
        "UPDATE orders SET status = 'paid', paid_at = datetime('now', 'localtime')"
        " WHERE order_id = ? AND status <> 'paid'", (order_id,))
    db.commit()
    if cur.rowcount == 0:
        return jsonify({'status': 'paid'})
    if credits > 0:
        grant_credits(user.get('id'), credits,
                      ref_type='credit_pack', ref_id=order_id,
                      remark=f'购买{pack["name"]}积分包')
    return jsonify({'status': 'paid'})



def _handle_topup_paid(db, order, order_id, user):
    """处理次卡支付成功：更新订单 + bonus_credits + 积分系统"""
    credits = TOPUP_CREDITS_MAP.get(order['plan_id'], 1)
    # 幂等（2026-11-14）：同 credit_pack，重复触发会让次卡次数翻倍。
    cur = db.execute(
        "UPDATE orders SET status = 'paid', paid_at = datetime('now', 'localtime')"
        " WHERE order_id = ? AND status <> 'paid'", (order_id,))
    db.commit()
    if cur.rowcount == 0:
        return jsonify({'status': 'paid'})
    db.execute(
        "UPDATE users SET bonus_credits ="
        " COALESCE(bonus_credits, 0) + ? WHERE id = ?",
        (credits, user.get('id')))
    db.commit()
    session['bonus_credits'] = (session.get('bonus_credits') or 0) + credits
    # v1.5: 同时写入积分系统
    grant_credits(user.get('id'), credits,
                  ref_type='topup', ref_id=order_id,
                  remark=f'次卡充值{credits}次')


@app.route('/api/pay/status/<order_id>')
@login_required
def api_pay_status(order_id):
    """查询支付状态（轮询门房真实订单状态）"""
    user = get_current_user()
    db = get_db()

    order = db.execute(
        'SELECT * FROM orders WHERE order_id = ? AND user_id = ?',
        (order_id, user.get('id'))
    ).fetchone()

    if not order:
        return jsonify({'status': 'not_found'}), HTTP_NOT_FOUND

    # 如果本地已是 paid，直接返回
    if order['status'] == 'paid':
        return jsonify({'status': 'paid'})

    # 调门房查真实支付状态
    mf_status = _menfang_get_order_status(order_id)

    if not mf_status['found']:
        return jsonify({'status': order['status']})

    # 支付成功 → 开通权限 / 发放积分
    if mf_status['status'] != 'paid' or order['status'] == 'paid':
        return jsonify({'status': mf_status.get('status', order['status'])})

    if order['order_type'] == 'credit_pack':
        return _handle_credit_pack_paid(db, order, order_id, user)
    if order['order_type'] == 'topup':
        _handle_topup_paid(db, order, order_id, user)
        return jsonify({'status': 'paid'})
    # 订阅卡：开 vip + 发放当月积分（透传门房真实支付时间）
    _handle_subscription_paid(db, order, order_id, user, mf_status.get('paid_at', ''))
    return jsonify({'status': 'paid'})


@app.route("/api/pay/health")
def api_pay_health():
    """支付模块健康检查"""
    try:
        db = get_db()
        db.execute("SELECT 1")
        return jsonify({"service": "pay", "status": "ok", "db": "connected"})
    except Exception as e:
        return jsonify({"service": "pay", "status": "error", "detail": str(e)}), 500


def _handle_subscription_paid(db, order, order_id, user, paid_at=''):
    """处理订阅订单支付成功：开通VIP + 发放积分 + 推荐奖励"""
    plan_info = SUBSCRIPTION_CREDITS.get(order['plan_id'], {})
    days = plan_info.get('days', DEFAULT_SUBSCRIPTION_DAYS)
    monthly_credits = plan_info.get('monthly_credits', DEFAULT_MONTHLY_CREDITS)

    # 治本（2026-10-30）：VIP 到期时间从门房真实支付时间 paid_at 起算，而非服务器
    # 当前时间。旧实现用 datetime.now()，若用户轮询延迟领取，VIP 会凭空少几天。
    # 门房 paid_at 是 ISO 8601 UTC（如 2026-10-30T03:25:00Z），需转本地时间再加 days。
    paid_dt = None
    if paid_at:
        try:
            # 处理带 Z 后缀的 UTC 时间：替换成 +00:00 后 fromisoformat 解析
            norm = paid_at.strip()
            if norm.endswith('Z'):
                norm = norm[:-1] + '+00:00'
            paid_dt = datetime.fromisoformat(norm)
            # 转成本地时间（服务器本地时区 GMT+8）
            if paid_dt.tzinfo is not None:
                paid_dt = paid_dt.astimezone().replace(tzinfo=None)
        except (ValueError, TypeError):
            paid_dt = None
    if paid_dt is None:
        # 门房没返回 paid_at 或解析失败时，退化为当前时间（宁可用 now 也不阻断开通）
        paid_dt = datetime.now()

    # 治本（2026-11-14）：续费累加，不吞剩余天数。算法在 calc_vip_expire 里，
    # 到期日以数据库为准（单一事实来源），不信调用链传进来的 user 字段。
    prev_row = db.execute(
        "SELECT vip_expire_at FROM users WHERE id = ?", (user.get('id'),)
    ).fetchone()
    prev_raw = (prev_row['vip_expire_at'] or '') if prev_row else ''
    vip_expire = calc_vip_expire(paid_dt, prev_raw, days)

    cur = db.execute(
        "UPDATE orders SET status = 'paid',"
        " paid_at = datetime('now', 'localtime')"
        " WHERE order_id = ? AND status <> 'paid'", (order_id,))
    if cur.rowcount == 0:
        # 已经被处理过（前端轮询 / 后台补单先到一步），不许再加一次会员时长。
        db.commit()
        try:
            session['is_vip'] = True
        except RuntimeError:
            pass
        return
    db.execute(
        "UPDATE users SET is_vip = 1,"
        " vip_expire_at = ? WHERE id = ?",
        (vip_expire, user.get('id')))
    db.commit()

    # v1.5: 立即发放当月积分
    grant_credits(user.get('id'), monthly_credits,
                  ref_type='subscription', ref_id=order_id,
                  remark=f'订阅{plan_info.get("name", "会员")}赠送{monthly_credits}积分')

    # v5.9: 推荐奖励 - 首充给推荐人发积分
    process_referral_reward(user.get('id'), order_id, order['plan_id'])

    # 更新 session
    session['is_vip'] = True



# ═══════════════════════════════════════════════════════════════════
# 新增 API 接口（2026-10-13）
# ═══════════════════════════════════════════════════════════════════

@app.route("/api/recharge/packages", methods=["GET"])
def api_recharge_packages():
    """获取充值套餐列表"""
    try:
        from .constants import CREDIT_PACKS
        # CREDIT_PACKS 格式: [{"credits": 100, "price": 9.9, "label": "100积分"}, ...]
        packages = []
        for pack_id, pack in CREDIT_PACKS.items():
            packages.append({
                "credits": pack.get("credits"),
                "price": pack.get("amount"),
                "label": pack.get("label", f"{pack.get("credits")}积分"),
                "original_price": pack.get("original_price"),
                "discount": pack.get("discount"),
            })
        return jsonify({
            "status": "ok",
            "packages": packages
        })
    except Exception as e:
        logger.exception(f"获取充值套餐失败: {e}")
        return jsonify({"status": "error", "message": "获取套餐失败"}), HTTP_INTERNAL_ERROR


@app.route("/api/credits/balance", methods=["GET"])
@login_required
def api_credits_balance():
    """查询用户积分余额"""
    try:
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"status": "error", "message": "未登录"}), HTTP_UNAUTHORIZED
        
        from .scoring import get_user_credits
        balance = get_user_credits(user_id)

        # 修复 2026-10-27：补"本月消耗"真实数据（原前端写死 0，冒充动态值）。
        # 统计本月内 type='consume' 的积分扣除总量（amount 为负，取绝对值求和）。
        monthly_used = 0
        try:
            db = get_db()
            row = db.execute(
                """SELECT COALESCE(SUM(-amount), 0) AS used
                   FROM credit_transactions
                   WHERE user_id = ? AND type = 'consume'
                     AND created_at >= datetime('now', 'localtime', 'start of month')""",
                (user_id,)
            ).fetchone()
            monthly_used = int(row['used']) if row else 0
        except Exception:
            # 统计失败不阻断余额查询
            monthly_used = 0
        
        return jsonify({
            "status": "ok",
            "balance": balance,
            "monthly_used": monthly_used,
            "user_id": user_id
        })
    except Exception as e:
        logger.exception(f"查询积分余额失败: {e}")
        return jsonify({"status": "error", "message": "查询失败"}), HTTP_INTERNAL_ERROR


@app.route("/api/order", methods=["GET"])
@login_required
def api_order_list():
    """获取用户订单列表"""
    try:
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"status": "error", "message": "未登录"}), HTTP_UNAUTHORIZED
        
        db = get_db()
        
        # 查询用户订单，按创建时间倒序
        cursor = db.execute(
            """SELECT order_id, order_type, amount, status,
                      created_at, paid_at, plan_name
               FROM orders
               WHERE user_id = ?
               ORDER BY created_at DESC
               LIMIT 50""",
            (user_id,)
        )
        
        orders = []
        for row in cursor.fetchall():
            orders.append({
                "order_id": row[0],
                "order_type": row[1],
                "amount": row[2],
                "credits": None,
                "status": row[3],
                "created_at": row[4],
                "paid_at": row[5],
                "plan_name": row[6]
            })
        
        return jsonify({
            "status": "ok",
            "orders": orders,
            "total": len(orders)
        })
    except Exception as e:
        logger.exception(f"查询订单列表失败: {e}")
        return jsonify({"status": "error", "message": "查询失败"}), HTTP_INTERNAL_ERROR


@app.route("/api/order/<order_id>", methods=["GET"])
@login_required
def api_order_detail(order_id):
    """获取单个订单详情"""
    try:
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"status": "error", "message": "未登录"}), HTTP_UNAUTHORIZED
        
        db = get_db()
        cursor = db.execute(
            """SELECT order_id, order_type, amount, status,
                      created_at, paid_at, plan_name, pay_method
               FROM orders
               WHERE order_id = ? AND user_id = ?""",
            (order_id, user_id)
        )
        
        row = cursor.fetchone()
        if not row:
            return jsonify({"status": "error", "message": "订单不存在"}), HTTP_NOT_FOUND
        
        order = {
            "order_id": row[0],
            "order_type": row[1],
            "amount": row[2],
            "credits": None,
            "status": row[3],
            "created_at": row[4],
            "paid_at": row[5],
            "plan_name": row[6],
            "payment_method": row[7]
        }
        
        return jsonify({
            "status": "ok",
            "order": order
        })
    except Exception as e:
        logger.exception(f"查询订单详情失败: {e}")
        return jsonify({"status": "error", "message": "查询失败"}), HTTP_INTERNAL_ERROR


# ═══════════════════════════════════════════════════════════════════
# 付款后补单（2026-11-14）
#
# 为什么需要：开通权益这一步是「前端轮询 /api/pay/status」触发的，不是门房回调。
# 客户扫完码把页面一关，轮询就断了——钱在门房已经收了，会员没开、积分没发，
# 而且没有任何人会发现：履约对账只查 status='paid' 的单，pending 的压根不在
# 它的视野里。门房也只在团队版时主动通知官网，普通订阅不会。
#
# 这个补单循环补的就是那一类：定期把「最近两天的 pending 单」拿去问门房，
# 门房说已付就补开通。幂等由 _handle_*_paid 里的条件更新保证，重复跑不会多发。
# ═══════════════════════════════════════════════════════════════════

RECONCILE_MIN_AGE_MINUTES = 2     # 太新的单子先让前端轮询自己领，别抢
RECONCILE_LOOKBACK_HOURS = 48     # 更早的单子门房已置 expired，不必再问
RECONCILE_BATCH = 20

_reconciler_started = False


def reconcile_pending_orders():
    """把「门房已付款、网站还挂着 pending」的订单补开通。

    返回 (补开条数, 本轮检查条数)。
    """
    db = get_db()
    rows = db.execute(
        "SELECT order_id, user_id, order_type FROM orders"
        " WHERE status = 'pending'"
        "   AND created_at > datetime('now', 'localtime', ?)"
        "   AND created_at < datetime('now', 'localtime', ?)"
        " ORDER BY id DESC LIMIT %d" % RECONCILE_BATCH,
        ('-%d hours' % RECONCILE_LOOKBACK_HOURS,
         '-%d minutes' % RECONCILE_MIN_AGE_MINUTES),
    ).fetchall()

    fixed = 0
    for r in rows:
        oid = r['order_id']
        otype = (r['order_type'] or '').strip()
        try:
            st = _menfang_get_order_status(oid)
        except Exception as exc:  # 门房抖动不该影响下一轮
            logger.warning('payment_reconcile: 查门房失败 %s: %s', oid, exc)
            continue
        if not st.get('found') or st.get('status') != 'paid':
            continue

        order = db.execute('SELECT * FROM orders WHERE order_id = ?', (oid,)).fetchone()
        if not order:
            continue
        urow = db.execute('SELECT * FROM users WHERE id = ?', (r['user_id'],)).fetchone()
        if not urow:
            logger.warning('payment_reconcile: 订单 %s 的用户 %s 不存在', oid, r['user_id'])
            continue
        user = dict(urow)

        try:
            if otype == 'credit_pack':
                _handle_credit_pack_paid(db, order, oid, user)
            elif otype == 'topup':
                _handle_topup_paid(db, order, oid, user)
            elif otype == 'subscription':
                _handle_subscription_paid(db, order, oid, user, st.get('paid_at', ''))
            elif otype == 'team':
                # Team purchases had no reconcile rule: a paid team order whose
                # callback was lost was logged and skipped, so the money was taken
                # and the team never opened. _finalize_team_purchase is idempotent
                # (atomic pending->paid claim), so retrying here is safe.
                from modules import team_governance as _tg
                _ok_team, _tid, _msg = _tg._finalize_team_purchase(oid, r['user_id'])
                if not _ok_team:
                    raise RuntimeError('team finalize failed: %s' % _msg)
            else:
                # 没有补开规则的订单类型必须留痕，不能悄悄放过。
                logger.warning('payment_reconcile: 订单 %s 类型 %r 没有补开规则', oid, otype)
                continue
            fixed += 1
            logger.info('payment_reconcile: 已补开 %s（%s）', oid, otype)
        except Exception as exc:
            logger.error('payment_reconcile: 补开 %s 失败: %s', oid, exc)

    return fixed, len(rows)


def start_payment_reconciler(interval_seconds=300):
    """起一个后台循环每 5 分钟补一次单。

    只在 app.py 的 __main__ 里调用——模块导入不许有副作用，否则任何一次
    `import app`（QA、巡检、工具）都会替生产起线程。
    """
    global _reconciler_started
    if _reconciler_started:
        return False

    def _loop():
        while True:
            time.sleep(interval_seconds)
            try:
                with app.app_context():
                    # 借一个空请求上下文：handler 里会写 session，没有上下文会抛异常
                    with app.test_request_context('/'):
                        fixed, checked = reconcile_pending_orders()
                if fixed:
                    logger.info('payment_reconcile: 本轮检查 %d 笔，补开 %d 笔', checked, fixed)
            except Exception as exc:
                logger.warning('payment_reconcile: 本轮失败: %s', exc)

    t = threading.Thread(target=_loop, name='payment-reconciler', daemon=True)
    t.start()
    _reconciler_started = True
    logger.info('payment_reconcile: 补单循环已启动，每 %d 秒一轮', interval_seconds)
    return True

