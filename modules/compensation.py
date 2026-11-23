# -*- coding: utf-8 -*-
"""
版本更新补偿蓝图 —— v7.0 上线期间受影响的用户登录领取 50 积分。

背景（2026-10-30）：v7.0 大版本更新期间有一段时间影响用户正常使用，
老板拍板给「更新前注册的老用户」每人补偿 50 积分，登录后在首页顶部公告条
一键领取。

设计（只治本）：
1. 独立 /claim-compensation 接口，登录后 POST 领取。
2. 资格 = 老用户（users.created_at < 补偿生效日期）且未领取过。
3. 幂等防重：以 credit_transactions 里 (ref_type='compensation', ref_id=补偿标识)
   作为业务唯一键，重复领取直接拒绝，杜绝并发/重复点击重复发积分。
4. 复用 scoring.grant_credits 发放，走既有积分池体系（有池进池、无池回退旧表），
   不另起一套账。
5. Jinja 全局函数 compensation_banner() 供 base.html 判断是否显示公告条，
   避免每个页面路由都手动塞状态。

安全边界：
- 领取接口挂 login_required_api（未登录 401）+ csrf_required（防跨站伪造领取）。
- 领取动作是「只增积分、不可逆」，但幂等键保证每人只发一次，无超发风险。
"""

from flask import Blueprint, request, jsonify, session

from . import app, get_db, logger
from .csrf_protection import csrf_required
from .helpers import login_required  # noqa: F401  （供模板/一致性）
from .scoring import grant_credits

compensation_bp = Blueprint('compensation', __name__)

# 补偿发放标识（单一事实来源：业务唯一键，也是公告条是否显示的依据）
COMPENSATION_REF_ID = 'v7.0_20261030'
COMPENSATION_AMOUNT = 50
# 补偿生效日期：此日期（含）之前注册的用户才算「老用户」
COMPENSATION_CUTOFF_DATE = '2026-10-30'


def _has_claimed(db, user_id):
    """查询该用户是否已领取过本次补偿。"""
    row = db.execute(
        '''SELECT 1 FROM credit_transactions
           WHERE user_id = ? AND type = 'grant'
             AND ref_type = 'compensation' AND ref_id = ?
           LIMIT 1''',
        (user_id, COMPENSATION_REF_ID)
    ).fetchone()
    return row is not None


def _is_old_user(db, user_id):
    """判断是否「更新前注册的老用户」。"""
    row = db.execute(
        'SELECT created_at FROM users WHERE id = ?',
        (user_id,)
    ).fetchone()
    if not row or not row['created_at']:
        return False
    # created_at 格式 'YYYY-MM-DD HH:MM:SS'，比较日期部分即可
    created_date = str(row['created_at'])[:10]
    return created_date < COMPENSATION_CUTOFF_DATE


def get_banner_state(user_id):
    """返回公告条状态：eligible(可领) / claimed(已领) / None(不显示)。
    供 Jinja 全局函数调用，只读、幂等。"""
    if not user_id:
        return None
    db = get_db()
    try:
        if _has_claimed(db, user_id):
            return 'claimed'
        if _is_old_user(db, user_id):
            return 'eligible'
        return None
    except Exception as e:  # noqa: BLE001  —— 公告条状态查询失败不阻断页面渲染
        logger.warning('[补偿] 查询公告条状态失败 user_id=%s: %s', user_id, e)
        return None


@compensation_bp.route('/claim-compensation', methods=['POST'])
@csrf_required
def claim_compensation():
    """领取 50 积分补偿（登录后 POST）。"""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': '未登录'}), 401

    db = get_db()
    try:
        if _has_claimed(db, user_id):
            return jsonify({'ok': False, 'message': '您已领取过本次补偿'}), 200
        if not _is_old_user(db, user_id):
            return jsonify({'ok': False, 'message': '本次补偿仅面向更新前注册的老用户'}), 200

        ok = grant_credits(
            user_id,
            COMPENSATION_AMOUNT,
            ref_type='compensation',
            ref_id=COMPENSATION_REF_ID,
            remark='v7.0 版本更新补偿'
        )
        if not ok:
            logger.warning('[补偿] 发放失败 user_id=%s', user_id)
            return jsonify({'ok': False, 'message': '发放失败，请稍后重试'}), 500

        logger.info('[补偿] 发放成功 user_id=%s amount=%s', user_id, COMPENSATION_AMOUNT)
        return jsonify({'ok': True, 'message': f'已到账 {COMPENSATION_AMOUNT} 积分', 'amount': COMPENSATION_AMOUNT}), 200
    except Exception as e:  # noqa: BLE001
        logger.warning('[补偿] 领取异常 user_id=%s: %s', user_id, e)
        return jsonify({'ok': False, 'message': '领取异常，请稍后重试'}), 500


# 注册 Jinja 全局：base.html 用它判断是否显示补偿公告条
app.jinja_env.globals['compensation_banner'] = get_banner_state
