# -*- coding: utf-8 -*-
"""后台母版公共上下文（唯一出口）

所有后台页面都靠 templates/dashboard/base.html 这层母版撑起来，母版需要的东西是固定的：
用户邮箱、会员状态、积分、未读公告、身份切换器（我的团队 / 当前团队）、新用户标记、首登引导开关。

以前这些只在 dashboard_page 一个函数里拼，团队那 5 个页面是独立 HTML，自己画 body 和顶部条，
母版里的身份切换、未读公告、首登引导一个都没有——从概览点进团队就像出了站，还得靠浏览器后退。
现在统一收成这个模块：谁渲染后台母版谁就来取，以后加新页面也不用再抄一遍、也不会漏一块。

依赖方向：本模块只依赖 db / helpers / scoring，不 import auth，避免循环导入。
"""
from datetime import datetime

from flask import session

from .constants import logger
from .db import get_db
from .helpers import get_unread_announcements, is_vip_user
from .scoring import get_user_credits, get_credit_pools


def vip_expire_display(raw):
    """把 users.vip_expire_at 变成页面要显示的两样东西：(日期文字, 剩余天数)。

    为什么要有这个（2026-11-14）：客户点进充值页，页面从不告诉他「你现在是会员、
    哪天到期」。他只能翻邮件自己算——续完费也不知道成没成。
    日期按中文习惯排（2026年12月15日），剩余天数按自然日算（今天到期=0）。
    解析不了的脏数据原样返回、天数给 None，页面就不显示天数，不做猜测。
    """
    raw = (raw or '').strip()
    if not raw:
        return '', None
    try:
        dt = datetime.strptime(raw[:19], '%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        return raw, None
    return '%d年%d月%d日' % (dt.year, dt.month, dt.day), (dt.date() - datetime.now().date()).days


def list_user_teams(user_id):
    """查询用户所属的所有团队（含角色）。用于身份切换器。"""
    if not user_id:
        return []
    try:
        db = get_db()
        rows = db.execute("""
            SELECT tm.team_id, tm.role, t.name
            FROM team_members tm
            JOIN teams t ON t.id = tm.team_id
            WHERE tm.user_id = ?
            ORDER BY tm.team_id ASC
        """, (user_id,)).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        # 团队表可能尚未初始化，静默降级为「无团队」
        logger.warning('[身份] 查询用户团队失败: %s', e)
        return []


def build_base_context(user, vip):
    """构建 dashboard 通用上下文（身份 / 会员 / 积分 / 未读公告）。"""
    credit_balance = get_user_credits(user.get('id')) if vip and user else 0
    unread_anns = get_unread_announcements(user.get('id')) if user else []
    credit_info = get_credit_pools(user.get('id')) if vip and user else None

    # ── 身份切换（个人 / 团队子账号）──
    uid = user.get('id') if user else None
    my_teams = list_user_teams(uid)
    active_team_id = session.get('active_team_id')
    active_team = None
    # 校验 session 里的团队身份仍有效（防止被踢后残留）
    if active_team_id and my_teams:
        for t in my_teams:
            if t['team_id'] == active_team_id:
                active_team = t
                break
    if active_team_id is not None and active_team is None:
        # session 里的团队已失效，回退到个人身份
        session.pop('active_team_id', None)
        active_team_id = None

    # 会员到期信息：充值页要显示「哪天到期、还剩几天」，客户才知道该不该续。
    vip_expire_text, vip_days_left = vip_expire_display(
        user.get('vip_expire_at') if user else '')

    return {
        'user_email': user.get('email', '') if user else '',
        'is_vip': vip,
        'vip_expire_text': vip_expire_text,
        'vip_days_left': vip_days_left,
        'bonus_credits': user.get('bonus_credits', 0) if user else 0,
        'credit_balance': credit_balance,
        'credit_info': credit_info,
        'unread_announcements': unread_anns,
        'my_teams': my_teams,
        'active_team_id': active_team_id,
        'active_team': active_team,
    }


def dashboard_context(user):
    """后台母版完整上下文 = 基础信息 + 新用户判定 + 首登引导开关。

    「新用户」= 一次都没扫过。全后台统一算一次：
    概览页据此切「三步开始」引导态，母版里的推广弹窗也用它让路。
    首登引导 = 没完成引导 且 从未扫描过（两个字段都真实落库）。
    """
    ctx = build_base_context(user, is_vip_user())
    db = get_db()
    has_scanned = db.execute(
        'SELECT 1 FROM scans WHERE user_id = ? LIMIT 1', (user.get('id'),)
    ).fetchone() is not None
    ctx['is_new_user'] = not has_scanned
    ctx['show_onboarding'] = not user.get('onboarding_completed') and not has_scanned
    return ctx
