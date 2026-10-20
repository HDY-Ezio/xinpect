"""Xinpect - Referral system"""
import secrets
import random
from datetime import datetime, timedelta

from .constants import (
    app, logger,
    REFERRAL_REWARD_RATIO,
    MAX_REFERRAL_ATTEMPTS,
    SUBSCRIPTION_CREDITS, CREDIT_PACKS,
    DEFAULT_SUBSCRIPTION_DAYS, DEFAULT_MONTHLY_CREDITS,
)
from .db import get_db
from .scoring import grant_credits


def generate_referral_code(length=6):
    """生成6位随机推荐码（排除易混淆字符）"""
    import string as _string
    chars = _string.ascii_uppercase + _string.digits
    for ch in ['0', 'O', '1', 'I', 'L']:
        chars = chars.replace(ch, '')
    return ''.join(secrets.choice(chars) for _ in range(length))


def generate_unique_referral_code(db, length=6, max_attempts=MAX_REFERRAL_ATTEMPTS):
    """生成唯一推荐码"""
    for _ in range(max_attempts):
        code = generate_referral_code(length)
        row = db.execute('SELECT id FROM users WHERE referral_code = ?', (code,)).fetchone()
        if not row:
            return code
    # 极端情况加长
    return generate_referral_code(length + 1)


def ensure_user_referral_code(db, user_id):
    """确保用户有推荐码，没有则生成"""
    user = db.execute('SELECT referral_code FROM users WHERE id = ?', (user_id,)).fetchone()
    if not user:
        return None
    if dict(user).get('referral_code'):
        return user['referral_code']
    code = generate_unique_referral_code(db)
    db.execute('UPDATE users SET referral_code = ? WHERE id = ?', (code, user_id))
    db.commit()
    return code


def get_referral_stats(user_id):
    """获取用户推荐统计"""
    db = get_db()
    referred_count = db.execute(
        'SELECT COUNT(*) as cnt FROM users WHERE referred_by = ?',
        (user_id,)
    ).fetchone()
    total_reward = db.execute(
        "SELECT COALESCE(SUM(reward_credits), 0) as total FROM referral_rewards "
        "WHERE referrer_user_id = ? AND reward_type = 'recharge_referrer'",
        (user_id,)
    ).fetchone()
    return {
        'referred_count': dict(referred_count).get('cnt', 0) if referred_count else 0,
        'total_reward_credits': dict(total_reward).get('total', 0) if total_reward else 0,
    }


def process_referral_reward(referred_user_id, order_id, plan_id):
    """
    处理推荐奖励：被推荐人充值时，双方各得套餐总积分的1/3作为一次性奖励。
    仅首次充值订阅时触发（一次性奖励）。
    """
    db = get_db()
    try:
        # 检查被推荐用户是否有推荐人
        referred_user = db.execute(
            'SELECT referred_by FROM users WHERE id = ?',
            (referred_user_id,)
        ).fetchone()
        if not referred_user or not dict(referred_user).get('referred_by'):
            return False, None, 0

        referrer_id = dict(referred_user).get('referred_by')

        # 计算奖励：套餐总积分 / 3
        plan_info = SUBSCRIPTION_CREDITS.get(plan_id, {})
        total_credits = plan_info.get('total_credits', 0)
        if total_credits <= 0:
            return False, referrer_id, 0
        bonus = total_credits // REFERRAL_REWARD_RATIO
        plan_name = plan_info.get('name', plan_id)

        if bonus <= 0:
            return False, referrer_id, 0

        # 仅首次充值触发：检查该推荐关系是否已经发放过充值奖励
        existing_reward = db.execute(
            'SELECT COUNT(*) as cnt FROM referral_rewards '
            'WHERE referrer_user_id = ? AND referred_user_id = ? '
            "AND reward_type = 'recharge_referrer'",
            (referrer_id, referred_user_id)
        ).fetchone()
        if existing_reward and dict(existing_reward).get('cnt', 0) > 0:
            return False, referrer_id, 0

        # 给被推荐人(B)发放一次性奖励
        db.execute(
            'INSERT INTO referral_rewards '
            '(referrer_user_id, referred_user_id, order_id, reward_credits, reward_type) '
            'VALUES (?, ?, ?, ?, ?)',
            (referrer_id, referred_user_id, order_id, bonus, 'recharge_referred')
        )
        grant_credits(
            referred_user_id, bonus,
            ref_type='referral_recharge', ref_id=order_id,
            remark=f'推荐充值奖励-被推荐人（{plan_name}）'
        )

        # 给推荐人(A)发放一次性奖励
        db.execute(
            'INSERT INTO referral_rewards '
            '(referrer_user_id, referred_user_id, order_id, reward_credits, reward_type) '
            'VALUES (?, ?, ?, ?, ?)',
            (referrer_id, referred_user_id, order_id, bonus, 'recharge_referrer')
        )
        grant_credits(
            referrer_id, bonus,
            ref_type='referral_recharge', ref_id=order_id,
            remark=f'推荐充值奖励-推荐人（{plan_name}）'
        )

        db.commit()
        return True, referrer_id, bonus

    except (sqlite3.Error, ValueError, TypeError) as e:
        logger.warning('[推荐] 充值奖励发放失败 user_id=%s plan=%s: %s',
                           referred_user_id, plan_id, e)
        return False, None, 0

