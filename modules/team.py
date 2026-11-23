# -*- coding: utf-8 -*-
"""
煋鉴 - 团队协作模块
功能：团队创建/管理、成员邀请/管理、团队配额、共享扫描结果
"""
import os
import json
import secrets
import sqlite3
from datetime import datetime, timedelta

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    session, flash, jsonify
)

from .constants import app, logger, DB_PATH, HTTP_OK, HTTP_BAD_REQUEST, HTTP_UNAUTHORIZED
from .db import get_db
from .helpers import login_required, get_current_user
from .dashboard_context import dashboard_context
from .csrf_protection import csrf_required
try:
    from .email_sender import send_team_invitation_email
except ImportError:
    def send_team_invitation_email(*args, **kwargs):
        logger.warning('邮件发送功能未配置')
        return False

team_bp = Blueprint("team", __name__)

# ── 常量 ────────────────────────────────────────────────
MAX_TEAMS_PER_USER = 3          # 每用户最多创建3个团队
INVITATION_EXPIRE_DAYS = 7      # 邀请链接有效期
TEAM_QUOTA_DEFAULT = 100        # 团队每日默认配额
TEAM_ROLE_OWNER = 'owner'
TEAM_ROLE_ADMIN = 'admin'
TEAM_ROLE_MEMBER = 'member'


def _governance():
    """延迟 import 治理模块，避免模块加载顺序/循环依赖。"""
    from . import team_governance
    return team_governance



# ══════════════════════════════════════════════════════════
#  数据库初始化
# ══════════════════════════════════════════════════════════

def init_team_tables():
    """创建团队相关表（幂等）"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                owner_id INTEGER NOT NULL REFERENCES users(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_teams_owner ON teams(owner_id);

            CREATE TABLE IF NOT EXISTS team_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id INTEGER NOT NULL REFERENCES teams(id),
                user_id INTEGER NOT NULL REFERENCES users(id),
                role TEXT NOT NULL DEFAULT 'member',
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(team_id, user_id)
            );
            CREATE INDEX IF NOT EXISTS idx_team_members_team ON team_members(team_id);
            CREATE INDEX IF NOT EXISTS idx_team_members_user ON team_members(user_id);

            CREATE TABLE IF NOT EXISTS team_invitations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id INTEGER NOT NULL REFERENCES teams(id),
                inviter_id INTEGER NOT NULL REFERENCES users(id),
                invitee_email TEXT NOT NULL,
                token TEXT NOT NULL UNIQUE,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_team_invitations_team ON team_invitations(team_id);
            CREATE INDEX IF NOT EXISTS idx_team_invitations_email ON team_invitations(invitee_email);
            CREATE INDEX IF NOT EXISTS idx_team_invitations_token ON team_invitations(token);

            CREATE TABLE IF NOT EXISTS team_quotas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id INTEGER NOT NULL REFERENCES teams(id),
                daily_limit INTEGER NOT NULL DEFAULT 100,
                used_today INTEGER NOT NULL DEFAULT 0,
                reset_date TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(team_id)
            );
        """)

        # scans 表加 team_id 列（结果归属团队；scans 是个人/团队扫描共用的真实结果表）
        cursor = conn.execute("PRAGMA table_info(scans)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'team_id' not in columns:
            conn.execute("ALTER TABLE scans ADD COLUMN team_id INTEGER REFERENCES teams(id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_scans_team ON scans(team_id)")

        conn.commit()
        conn.close()
        logger.info("[团队] 数据表初始化完成")
    except Exception as e:
        logger.error(f"[团队] 数据表初始化失败: {e}")


# ══════════════════════════════════════════════════════════
#  内部工具函数
# ══════════════════════════════════════════════════════════

def _get_user_teams(user_id, db):
    """获取用户所在的所有团队"""
    rows = db.execute("""
        SELECT t.id, t.name, t.description, t.owner_id, t.created_at,
               tm.role,
               (SELECT COUNT(*) FROM team_members WHERE team_id = t.id) as member_count
        FROM teams t
        JOIN team_members tm ON tm.team_id = t.id AND tm.user_id = ?
        ORDER BY t.created_at DESC
    """, (user_id,)).fetchall()
    return [dict(r) for r in rows]


def _get_team_detail(team_id, user_id, db):
    """获取团队详情，含权限校验。返回None表示无权访问"""
    # 检查是否是团队成员
    member = db.execute("""
        SELECT tm.role FROM team_members tm
        WHERE tm.team_id = ? AND tm.user_id = ?
    """, (team_id, user_id)).fetchone()

    if not member:
        return None

    team = db.execute("""
        SELECT t.*, 
               (SELECT COUNT(*) FROM team_members WHERE team_id = t.id) as member_count
        FROM teams t WHERE t.id = ?
    """, (team_id,)).fetchone()

    if not team:
        return None

    result = dict(team)
    result['my_role'] = member['role'] if member else None
    return result


def _is_team_admin(team_id, user_id, db):
    """检查用户是否是团队管理员或所有者"""
    row = db.execute("""
        SELECT role FROM team_members
        WHERE team_id = ? AND user_id = ?
    """, (team_id, user_id)).fetchone()
    return row and row['role'] in (TEAM_ROLE_OWNER, TEAM_ROLE_ADMIN)


def _is_team_owner(team_id, user_id, db):
    """检查用户是否是团队所有者"""
    row = db.execute("""
        SELECT role FROM team_members
        WHERE team_id = ? AND user_id = ?
    """, (team_id, user_id)).fetchone()
    return row and row['role'] == TEAM_ROLE_OWNER


def _get_team_quota(team_id, db):
    """获取团队配额信息，自动重置每日计数"""
    today = datetime.now().strftime('%Y-%m-%d')
    quota = db.execute("""
        SELECT * FROM team_quotas WHERE team_id = ?
    """, (team_id,)).fetchone()

    if not quota:
        # 创建默认配额
        db.execute("""
            INSERT INTO team_quotas (team_id, daily_limit, used_today, reset_date)
            VALUES (?, ?, 0, ?)
        """, (team_id, TEAM_QUOTA_DEFAULT, today))
        db.commit()
        return {'team_id': team_id, 'daily_limit': TEAM_QUOTA_DEFAULT,
                'used_today': 0, 'reset_date': today}

    # 自动重置
    if quota['reset_date'] < today:
        db.execute("""
            UPDATE team_quotas SET used_today = 0, reset_date = ?, updated_at = CURRENT_TIMESTAMP
            WHERE team_id = ?
        """, (today, team_id))
        db.commit()
        return dict(quota, used_today=0, reset_date=today)

    return dict(quota)


def _consume_team_quota(team_id, db):
    """消耗一次团队配额，返回True表示成功，False表示配额不足"""
    quota = _get_team_quota(team_id, db)
    if quota['used_today'] >= quota['daily_limit']:
        return False
    db.execute("""
        UPDATE team_quotas SET used_today = used_today + 1, updated_at = CURRENT_TIMESTAMP
        WHERE team_id = ?
    """, (team_id,))
    db.commit()
    return True


def _release_team_quota(team_id, db):
    """回滚一次团队配额（扫描失败时调用，避免误扣）"""
    try:
        db.execute("""
            UPDATE team_quotas SET used_today = MAX(0, used_today - 1), updated_at = CURRENT_TIMESTAMP
            WHERE team_id = ?
        """, (team_id,))
        db.commit()
    except Exception:
        pass  # 回滚失败不影响主流程


def _generate_invitation_token():
    """生成唯一邀请token"""
    return secrets.token_urlsafe(32)


# ══════════════════════════════════════════════════════════
#  页面路由
# ══════════════════════════════════════════════════════════

@app.route('/dashboard/team')
@login_required
def team_dashboard():
    """团队Dashboard主页"""
    user = get_current_user()
    db = get_db()

    # 获取用户所在团队
    teams = _get_user_teams(user['id'], db)

    # 获取待处理邀请
    pending_invites = db.execute("""
        SELECT ti.*, t.name as team_name, t.id as team_id
        FROM team_invitations ti
        JOIN teams t ON t.id = ti.team_id
        WHERE ti.invitee_email = ? AND ti.status = 'pending'
              AND ti.expires_at > datetime('now')
        ORDER BY ti.created_at DESC
    """, (user['email'],)).fetchall()

    # 团队版套餐（供「购买团队版」独立入口展示，付费后自动建团+设管理员）
    try:
        from . import team_governance as _gov
        team_plans = _gov.TEAM_PLANS
    except Exception:
        team_plans = {}

    # 这 5 个团队页现在都走后台母版（侧栏 / 身份切换 / 未读公告 / 首登引导），
    # 母版要的上下文统一从 dashboard_context 取，page 钉成 team 让侧栏高亮「团队协作」。
    ctx = dashboard_context(user)
    ctx.update({
        'user': user,
        'page': 'team',
        'teams': teams,
        'pending_invites': [dict(i) for i in pending_invites],
        'pending_count': len(pending_invites),
        'team_plans': team_plans,
    })
    return render_template('dashboard/team.html', **ctx)


@app.route('/dashboard/team/<int:team_id>')
@login_required
def team_detail(team_id):
    """团队详情页"""
    user = get_current_user()
    db = get_db()

    team = _get_team_detail(team_id, user['id'], db)
    if not team:
        flash('无权访问该团队', 'error')
        return redirect(url_for('team_dashboard'))

    # 获取成员列表
    members = db.execute("""
        SELECT tm.user_id, tm.role, tm.joined_at, u.email
        FROM team_members tm
        JOIN users u ON u.id = tm.user_id
        WHERE tm.team_id = ?
        ORDER BY
            CASE tm.role WHEN 'owner' THEN 1 WHEN 'admin' THEN 2 ELSE 3 END,
            tm.joined_at ASC
    """, (team_id,)).fetchall()

    # 获取团队配额
    quota = _get_team_quota(team_id, db)

    # 获取待处理邀请
    pending_invites = db.execute("""
        SELECT * FROM team_invitations
        WHERE team_id = ? AND status = 'pending' AND expires_at > datetime('now')
        ORDER BY created_at DESC
    """, (team_id,)).fetchall()

    # 获取团队扫描历史（最近20条）
    recent_scans = db.execute("""
        SELECT s.id, s.title, s.language, s.score, s.issue_count, s.created_at,
               u.email as scanner_email
        FROM scans s
        LEFT JOIN users u ON u.id = s.user_id
        WHERE s.team_id = ?
        ORDER BY s.created_at DESC
        LIMIT 20
    """, (team_id,)).fetchall()

    ctx = dashboard_context(user)
    ctx.update({
        'user': user,
        'page': 'team',
        'team': team,
        'members': [dict(m) for m in members],
        'quota': quota,
        'pending_invites': [dict(i) for i in pending_invites],
        'recent_scans': [dict(s) for s in recent_scans],
    })
    return render_template('dashboard/team_detail.html', **ctx)


@app.route('/dashboard/team/<int:team_id>/settings')
@login_required
def team_settings(team_id):
    """团队设置页"""
    user = get_current_user()
    db = get_db()

    team = _get_team_detail(team_id, user['id'], db)
    if not team:
        flash('无权访问该团队', 'error')
        return redirect(url_for('team_dashboard'))

    if not _is_team_admin(team_id, user['id'], db):
        flash('仅管理员可修改团队设置', 'error')
        return redirect(url_for('team_detail', team_id=team_id))

    members = db.execute("""
        SELECT tm.user_id, tm.role, tm.joined_at, u.email
        FROM team_members tm
        JOIN users u ON u.id = tm.user_id
        WHERE tm.team_id = ?
        ORDER BY
            CASE tm.role WHEN 'owner' THEN 1 WHEN 'admin' THEN 2 ELSE 3 END,
            tm.joined_at ASC
    """, (team_id,)).fetchall()

    invite_links = db.execute("""
        SELECT * FROM team_invitations
        WHERE team_id = ? AND inviter_id = ?
        ORDER BY created_at DESC
        LIMIT 20
    """, (team_id, user['id'])).fetchall()

    ctx = dashboard_context(user)
    ctx.update({
        'user': user,
        'page': 'team',
        'team': team,
        'members': [dict(m) for m in members],
        'invite_links': [dict(l) for l in invite_links],
        'is_owner': team['my_role'] == TEAM_ROLE_OWNER,
    })
    return render_template('dashboard/team_settings.html', **ctx)


@app.route('/team/invite/<token>')
@login_required
def team_invite_accept_page(token):
    """邀请链接页面"""
    user = get_current_user()
    db = get_db()

    invite = db.execute("""
        SELECT ti.*, t.name as team_name
        FROM team_invitations ti
        JOIN teams t ON t.id = ti.team_id
        WHERE ti.token = ? AND ti.status = 'pending'
    """, (token,)).fetchone()

    if not invite:
        flash('邀请链接无效或已过期', 'error')
        return redirect(url_for('team_dashboard'))

    if invite['expires_at'] and invite['expires_at'] < datetime.now().strftime('%Y-%m-%d %H:%M:%S'):
        flash('邀请链接已过期', 'error')
        return redirect(url_for('team_dashboard'))

    # 检查邮箱是否匹配
    if invite['invitee_email'] != user['email']:
        flash(f'该邀请发送给 {invite["invitee_email"]}，请使用对应账号登录', 'error')
        return redirect(url_for('team_dashboard'))

    ctx = dashboard_context(user)
    ctx.update({
        'user': user,
        'page': 'team',
        'invite': dict(invite),
        'token': token,
    })
    return render_template('dashboard/team_invite.html', **ctx)


# ══════════════════════════════════════════════════════════
#  API路由 - 团队CRUD
# ══════════════════════════════════════════════════════════

@app.route('/api/teams', methods=['POST'])
@login_required
def api_create_team():
    """创建团队"""
    user = get_current_user()
    db = get_db()
    data = request.get_json(silent=True) or {}

    name = (data.get('name') or '').strip()
    description = (data.get('description') or '').strip()

    # 校验
    if not name or len(name) < 2:
        return jsonify({'code': -1, 'msg': '团队名称至少2个字符'}), HTTP_BAD_REQUEST
    if len(name) > 100:
        return jsonify({'code': -1, 'msg': '团队名称不超过100个字符'}), HTTP_BAD_REQUEST

    # 检查创建数量限制
    count = db.execute("""
        SELECT COUNT(*) as cnt FROM team_members
        WHERE user_id = ? AND role = ?
    """, (user['id'], TEAM_ROLE_OWNER)).fetchone()
    if count and count['cnt'] >= MAX_TEAMS_PER_USER:
        return jsonify({'code': -1, 'msg': f'最多创建{MAX_TEAMS_PER_USER}个团队'}), HTTP_BAD_REQUEST

    try:
        cursor = db.execute("""
            INSERT INTO teams (name, description, owner_id)
            VALUES (?, ?, ?)
        """, (name, description, user['id']))
        team_id = cursor.lastrowid

        # 创建者自动成为owner
        db.execute("""
            INSERT INTO team_members (team_id, user_id, role)
            VALUES (?, ?, ?)
        """, (team_id, user['id'], TEAM_ROLE_OWNER))

        # 初始化团队配额
        today = datetime.now().strftime('%Y-%m-%d')
        db.execute("""
            INSERT INTO team_quotas (team_id, daily_limit, used_today, reset_date)
            VALUES (?, ?, 0, ?)
        """, (team_id, TEAM_QUOTA_DEFAULT, today))

        db.commit()
        logger.info(f"[团队] 用户{user['id']}创建团队: {name} (ID={team_id})")

        return jsonify({
            'code': 0,
            'msg': '团队创建成功',
            'data': {'team_id': team_id, 'name': name}
        })

    except Exception as e:
        db.rollback()
        logger.error(f"[团队] 创建团队失败: {e}")
        return jsonify({'code': -1, 'msg': '创建失败，请重试'}), HTTP_BAD_REQUEST


@app.route('/api/teams', methods=['GET'])
@login_required
def api_list_teams():
    """获取我的团队列表"""
    user = get_current_user()
    db = get_db()
    teams = _get_user_teams(user['id'], db)
    return jsonify({'code': 0, 'data': teams})


@app.route('/api/teams/<int:team_id>', methods=['GET'])
@login_required
def api_get_team(team_id):
    """获取团队详情"""
    user = get_current_user()
    db = get_db()
    team = _get_team_detail(team_id, user['id'], db)
    if not team:
        return jsonify({'code': -1, 'msg': '无权访问'}), HTTP_UNAUTHORIZED
    quota = _get_team_quota(team_id, db)
    team['quota'] = quota
    return jsonify({'code': 0, 'data': team})


@app.route('/api/teams/<int:team_id>', methods=['PUT'])
@login_required
def api_update_team(team_id):
    """更新团队信息"""
    user = get_current_user()
    db = get_db()

    if not _is_team_admin(team_id, user['id'], db):
        return jsonify({'code': -1, 'msg': '仅管理员可修改'}), HTTP_UNAUTHORIZED

    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    description = (data.get('description') or '').strip()

    if name and (len(name) < 2 or len(name) > 100):
        return jsonify({'code': -1, 'msg': '团队名称2-100个字符'}), HTTP_BAD_REQUEST

    updates = []
    params = []
    if name:
        updates.append('name = ?')
        params.append(name)
    if description is not None:
        updates.append('description = ?')
        params.append(description)

    if updates:
        params.append(team_id)
        db.execute(f"UPDATE teams SET {', '.join(updates)} WHERE id = ?", params)
        db.commit()

    return jsonify({'code': 0, 'msg': '更新成功'})


@app.route('/api/teams/<int:team_id>', methods=['DELETE'])
@login_required
def api_delete_team(team_id):
    """删除团队（仅Owner）"""
    user = get_current_user()
    db = get_db()

    if not _is_team_owner(team_id, user['id'], db):
        return jsonify({'code': -1, 'msg': '仅团队所有者可删除'}), HTTP_UNAUTHORIZED

    try:
        # 删除关联数据
        db.execute("DELETE FROM team_invitations WHERE team_id = ?", (team_id,))
        db.execute("DELETE FROM team_quotas WHERE team_id = ?", (team_id,))
        db.execute("DELETE FROM team_members WHERE team_id = ?", (team_id,))
        # 解除扫描结果的团队关联
        db.execute("UPDATE scans SET team_id = NULL WHERE team_id = ?", (team_id,))
        db.execute("DELETE FROM teams WHERE id = ?", (team_id,))
        db.commit()

        logger.info(f"[团队] 用户{user['id']}删除团队ID={team_id}")
        return jsonify({'code': 0, 'msg': '团队已删除'})

    except Exception as e:
        db.rollback()
        logger.error(f"[团队] 删除团队失败: {e}")
        return jsonify({'code': -1, 'msg': '删除失败'}), HTTP_BAD_REQUEST


# ══════════════════════════════════════════════════════════
#  API路由 - 成员管理
# ══════════════════════════════════════════════════════════

@app.route('/api/teams/<int:team_id>/invitations', methods=['POST'])
@login_required
def api_invite_member(team_id):
    """邀请成员加入团队"""
    user = get_current_user()
    db = get_db()

    if not _is_team_admin(team_id, user['id'], db):
        return jsonify({'code': -1, 'msg': '仅管理员可添加子账号'}), HTTP_UNAUTHORIZED

    data = request.get_json(silent=True) or {}
    invitee_email = (data.get('email') or '').strip().lower()

    if not invitee_email:
        return jsonify({'code': -1, 'msg': '请输入邀请邮箱'}), HTTP_BAD_REQUEST

    # 检查是否已是成员
    existing = db.execute("""
        SELECT 1 FROM team_members tm
        JOIN users u ON u.id = tm.user_id
        WHERE tm.team_id = ? AND u.email = ?
    """, (team_id, invitee_email)).fetchone()
    if existing:
        return jsonify({'code': -1, 'msg': '该用户已是团队子账号'}), HTTP_BAD_REQUEST

    # 检查是否有待处理的邀请
    pending = db.execute("""
        SELECT 1 FROM team_invitations
        WHERE team_id = ? AND invitee_email = ? AND status = 'pending'
              AND expires_at > datetime('now')
    """, (team_id, invitee_email)).fetchone()
    if pending:
        return jsonify({'code': -1, 'msg': '已有待处理的邀请，请勿重复邀请'}), HTTP_BAD_REQUEST

    # 生成邀请
    token = _generate_invitation_token()
    expires_at = (datetime.now() + timedelta(days=INVITATION_EXPIRE_DAYS)).strftime('%Y-%m-%d %H:%M:%S')

    db.execute("""
        INSERT INTO team_invitations (team_id, inviter_id, invitee_email, token, expires_at)
        VALUES (?, ?, ?, ?, ?)
    """, (team_id, user['id'], invitee_email, token, expires_at))
    db.commit()

    # 发送邀请邮件
    team = db.execute("SELECT name FROM teams WHERE id = ?", (team_id,)).fetchone()
    try:
        invite_url = request.host_url.rstrip('/') + f'/team/invite/{token}'
        send_team_invitation_email(
            to_email=invitee_email,
            team_name=team['name'] if team else '团队',
            inviter_email=user['email'],
            invite_url=invite_url,
            expire_days=INVITATION_EXPIRE_DAYS
        )
    except Exception as e:
        logger.warning(f"[团队] 邀请邮件发送失败: {e}")

    return jsonify({
        'code': 0,
        'msg': f'邀请已发送至 {invitee_email}',
        'data': {'token': token, 'expires_at': expires_at}
    })


@app.route('/api/teams/<int:team_id>/members', methods=['GET'])
@login_required
def api_list_members(team_id):
    """获取成员列表"""
    user = get_current_user()
    db = get_db()

    if not _get_team_detail(team_id, user['id'], db):
        return jsonify({'code': -1, 'msg': '无权访问'}), HTTP_UNAUTHORIZED

    members = db.execute("""
        SELECT tm.user_id, tm.role, tm.joined_at, u.email
        FROM team_members tm
        JOIN users u ON u.id = tm.user_id
        WHERE tm.team_id = ?
        ORDER BY
            CASE tm.role WHEN 'owner' THEN 1 WHEN 'admin' THEN 2 ELSE 3 END,
            tm.joined_at ASC
    """, (team_id,)).fetchall()

    return jsonify({'code': 0, 'data': [dict(m) for m in members]})


@app.route('/api/teams/<int:team_id>/members/<int:target_user_id>', methods=['PUT'])
@login_required
def api_update_member_role(team_id, target_user_id):
    """修改成员角色"""
    user = get_current_user()
    db = get_db()

    # 仅owner可修改角色
    if not _is_team_owner(team_id, user['id'], db):
        return jsonify({'code': -1, 'msg': '仅团队所有者可修改子账号角色'}), HTTP_UNAUTHORIZED

    data = request.get_json(silent=True) or {}
    new_role = data.get('role', '')
    if new_role not in (TEAM_ROLE_ADMIN, TEAM_ROLE_MEMBER):
        return jsonify({'code': -1, 'msg': '角色无效，仅支持admin或member'}), HTTP_BAD_REQUEST

    # 不能修改自己的角色
    if target_user_id == user['id']:
        return jsonify({'code': -1, 'msg': '不能修改自己的角色'}), HTTP_BAD_REQUEST

    # 确认目标是团队成员
    target = db.execute("""
        SELECT role FROM team_members WHERE team_id = ? AND user_id = ?
    """, (team_id, target_user_id)).fetchone()
    if not target:
        return jsonify({'code': -1, 'msg': '该用户不是团队子账号'}), HTTP_BAD_REQUEST

    db.execute("""
        UPDATE team_members SET role = ? WHERE team_id = ? AND user_id = ?
    """, (new_role, team_id, target_user_id))
    db.commit()

    return jsonify({'code': 0, 'msg': '角色已更新'})


@app.route('/api/teams/<int:team_id>/members/<int:target_user_id>', methods=['DELETE'])
@login_required
def api_remove_member(team_id, target_user_id):
    """移除成员"""
    user = get_current_user()
    db = get_db()

    if not _is_team_admin(team_id, user['id'], db):
        return jsonify({'code': -1, 'msg': '仅管理员可移除子账号'}), HTTP_UNAUTHORIZED

    # 不能移除owner
    target = db.execute("""
        SELECT role FROM team_members WHERE team_id = ? AND user_id = ?
    """, (team_id, target_user_id)).fetchone()
    if not target:
        return jsonify({'code': -1, 'msg': '该用户不是团队子账号'}), HTTP_BAD_REQUEST
    if target['role'] == TEAM_ROLE_OWNER:
        return jsonify({'code': -1, 'msg': '不能移除团队所有者'}), HTTP_BAD_REQUEST

    # admin不能移除其他admin（仅owner可以）
    if target['role'] == TEAM_ROLE_ADMIN and not _is_team_owner(team_id, user['id'], db):
        return jsonify({'code': -1, 'msg': '仅团队所有者可移除管理员'}), HTTP_UNAUTHORIZED

    db.execute("DELETE FROM team_members WHERE team_id = ? AND user_id = ?",
               (team_id, target_user_id))
    db.commit()

    logger.info(f"[团队] 用户{user['id']}从团队{team_id}移除了成员{target_user_id}")
    return jsonify({'code': 0, 'msg': '子账号已移除'})


@app.route('/api/teams/invitations/<int:invitation_id>/accept', methods=['POST'])
@login_required
def api_accept_invitation(invitation_id):
    """接受邀请"""
    user = get_current_user()
    db = get_db()

    invite = db.execute("""
        SELECT * FROM team_invitations WHERE id = ? AND status = 'pending'
    """, (invitation_id,)).fetchone()

    if not invite:
        return jsonify({'code': -1, 'msg': '邀请不存在或已处理'}), HTTP_BAD_REQUEST

    if invite['invitee_email'] != user['email']:
        return jsonify({'code': -1, 'msg': '邀请邮箱不匹配'}), HTTP_UNAUTHORIZED

    if invite['expires_at'] and invite['expires_at'] < datetime.now().strftime('%Y-%m-%d %H:%M:%S'):
        return jsonify({'code': -1, 'msg': '邀请已过期'}), HTTP_BAD_REQUEST

    team_id = invite['team_id']

    # 检查是否已是成员
    existing = db.execute("""
        SELECT 1 FROM team_members WHERE team_id = ? AND user_id = ?
    """, (team_id, user['id'])).fetchone()
    if existing:
        return jsonify({'code': -1, 'msg': '你已是该团队子账号'}), HTTP_BAD_REQUEST

    # 席位满员校验：当前成员数 >= 团队席位上限时，拒绝加入。
    try:
        gov = _governance()
        member_limit = gov.get_team_member_limit(team_id)
        current_count = db.execute(
            "SELECT COUNT(*) as cnt FROM team_members WHERE team_id = ?",
            (team_id,)
        ).fetchone()
        if current_count and current_count['cnt'] >= member_limit:
            return jsonify({
                'code': -1,
                'msg': f'该团队席位已满（{member_limit} 人），请联系管理员升级团队版或移除成员'
            }), HTTP_BAD_REQUEST
    except Exception as e:
        logger.warning('[团队] 席位校验失败 team_id=%s: %s', team_id, e)

    try:
        # 添加成员
        db.execute("""
            INSERT INTO team_members (team_id, user_id, role)
            VALUES (?, ?, ?)
        """, (team_id, user['id'], TEAM_ROLE_MEMBER))

        # 更新邀请状态
        db.execute("""
            UPDATE team_invitations SET status = 'accepted' WHERE id = ?
        """, (invitation_id,))
        db.commit()

        logger.info(f"[团队] 用户{user['id']}加入团队{team_id}")
        return jsonify({'code': 0, 'msg': '已加入团队'})

    except Exception as e:
        db.rollback()
        logger.error(f"[团队] 加入团队失败: {e}")
        return jsonify({'code': -1, 'msg': '加入失败'}), HTTP_BAD_REQUEST


@app.route('/api/teams/invitations/<int:invitation_id>/reject', methods=['POST'])
@login_required
def api_reject_invitation(invitation_id):
    """拒绝邀请"""
    user = get_current_user()
    db = get_db()

    invite = db.execute("""
        SELECT * FROM team_invitations WHERE id = ? AND status = 'pending'
    """, (invitation_id,)).fetchone()

    if not invite:
        return jsonify({'code': -1, 'msg': '邀请不存在或已处理'}), HTTP_BAD_REQUEST

    if invite['invitee_email'] != user['email']:
        return jsonify({'code': -1, 'msg': '邀请邮箱不匹配'}), HTTP_UNAUTHORIZED

    db.execute("UPDATE team_invitations SET status = 'rejected' WHERE id = ?", (invitation_id,))
    db.commit()

    return jsonify({'code': 0, 'msg': '已拒绝邀请'})


# ══════════════════════════════════════════════════════════
#  API路由 - 团队扫描
# ══════════════════════════════════════════════════════════

def _team_scan_credits(team_id, vip, user_id, total_lines, file_count, scan_mode):
    """团队扫描积分：只扣团队共享积分池，绝不扣个人积分。

    团队身份扫描只认共享池——共享池余额不足就明确报错（提示找管理员充值），
    绝不回退个人积分（谁上班还自己贴钱）。团队无免费档，必然产生积分消耗。

    返回 (credits_cost, error_response, paid_from)。
    paid_from: 'team_pool'
    """
    from .scoring import calculate_scan_cost
    credits_cost = calculate_scan_cost(total_lines, scan_mode=scan_mode, user_id=user_id)

    if credits_cost <= 0:
        # 极端情况（如 0 行代码）不产生费用，但仍走团队路径，不扣个人
        return 0, None, 'team_pool'

    # 只扣团队共享积分池
    try:
        gov = _governance()
        ref_id = f'team:{team_id}:{user_id}:{int(datetime.now().timestamp())}'
        if gov.consume_team_credits(
            team_id, credits_cost, user_id,
            ref_type='team_scan', ref_id=ref_id,
            remark=f'团队扫描：{total_lines}行，{file_count}个文件，{scan_mode}模式'
        ):
            # 共享池扣费成功，credits_cost 传 0 给 _do_async_scan（避免再走个人扣费）
            return 0, None, 'team_pool'

        # 共享池余额不足 → 明确报错，不回退个人积分
        balance = gov.get_team_credit_balance(team_id)
        return 0, (
            jsonify({
                'error': (
                    f'团队共享积分不足，本次扫描需 {credits_cost} 积分，'
                    f'团队共享池当前余额 {balance} 积分。请联系团队管理员充值团队积分。'
                ),
                'credits_needed': credits_cost,
                'team_credit_balance': balance,
                'total_lines': total_lines,
            }), HTTP_BAD_REQUEST
        ), 'team_pool'
    except Exception as e:
        logger.error('[团队扫描] 共享积分池扣费异常 team_id=%s: %s', team_id, e)
        return 0, (
            jsonify({'error': '团队共享积分扣费失败，请稍后重试或联系团队管理员'})
        ), HTTP_BAD_REQUEST


@app.route('/api/teams/<int:team_id>/scan', methods=['POST'])
@login_required
def api_team_scan(team_id):
    """团队扫描（复用个人扫描链路，结果归属到团队 team_id）"""
    user = get_current_user()
    db = get_db()

    # 权限校验
    team = _get_team_detail(team_id, user['id'], db)
    if not team:
        return jsonify({'code': -1, 'msg': '无权访问该团队'}), HTTP_UNAUTHORIZED

    # 检查团队配额
    quota = _get_team_quota(team_id, db)
    if quota['used_today'] >= quota['daily_limit']:
        return jsonify({
            'code': -1,
            'msg': f'团队今日配额已用完（{quota["daily_limit"]}次/天），请使用个人配额扫描'
        }), HTTP_BAD_REQUEST

    # 消耗团队配额
    if not _consume_team_quota(team_id, db):
        return jsonify({'code': -1, 'msg': '配额不足'}), HTTP_BAD_REQUEST

    # ── 复用个人扫描链路 ──
    # 延迟 import 避免模块加载顺序/循环依赖问题
    from .scan import (
        _collect_files_from_request, _brain_ids_for_scan_mode,
        _scan_credits_handling, _do_async_scan, count_total_lines,
    )

    files_dict = _collect_files_from_request()
    if not files_dict:
        # 回收刚才消耗的团队配额（没有代码可扫）
        _release_team_quota(team_id, db)
        return jsonify({'code': -1, 'msg': '请上传文件或粘贴代码'}), HTTP_BAD_REQUEST

    # 大文件前置过滤（与个人扫描一致）
    _max_single = 1024 * 1024
    for _fn in list(files_dict.keys()):
        _fc = files_dict[_fn]
        if isinstance(_fc, str) and len(_fc.encode('utf-8', errors='replace')) > _max_single:
            del files_dict[_fn]
    if not files_dict:
        _release_team_quota(team_id, db)
        return jsonify({'code': -1, 'msg': '请上传文件或粘贴代码'}), HTTP_BAD_REQUEST

    language = request.form.get('language', 'auto')
    user_id = session.get('user_id')

    # ── 档位 = 管理员上限 + 成员自选，与子账号本人是否会员无关 ──
    # 管理员配置的 scan_mode 是「上限」，成员自选不超过上限。
    # 子账号本人会员/个人积分只影响「个人身份」扫描，不影响团队身份。
    gov = _governance()
    req_scan_mode = request.form.get('scan_mode', '')
    actual_scan_mode = gov.resolve_team_scan_mode(team_id, req_scan_mode)
    scan_mode = actual_scan_mode

    # 团队无免费档，只有 quick/smart/deep，必然走引擎能力，故 engine_vip 恒 True
    # （vip 在这里仅代表「引擎可以调 AI/PoC」，档位已经由 scan_mode 单独控制）
    engine_vip = True

    brain_ids = _brain_ids_for_scan_mode(engine_vip, actual_scan_mode)
    file_count = len(files_dict)
    total_lines = count_total_lines(files_dict)

    # ── 团队扫描积分：只扣团队共享积分池，绝不扣个人积分 ──
    credits_cost, err, paid_from = _team_scan_credits(
        team_id, engine_vip, user_id, total_lines, file_count, actual_scan_mode
    )
    if err:
        _release_team_quota(team_id, db)
        return err

    # 提交扫描，结果归属到团队
    scan_id, err_resp, err_code = _do_async_scan(
        files_dict, brain_ids, language, engine_vip, user_id,
        credits_cost, total_lines, scan_mode, 'team', team_id=team_id
    )
    if err_resp:
        _release_team_quota(team_id, db)
        return err_resp, err_code

    return jsonify({
        'code': 0,
        'msg': '团队扫描已提交',
        'data': {
            'team_id': team_id,
            'scan_id': scan_id,
            'report_url': url_for('report_page', scan_id=scan_id),
            'file_count': file_count,
            'total_lines': total_lines,
            'credits_spent': credits_cost if user_id else 0,
            'paid_from': paid_from,
            'quota_used': quota['used_today'] + 1,
            'quota_limit': quota['daily_limit'],
            'quota_remaining': quota['daily_limit'] - quota['used_today'] - 1
        }
    })


@app.route('/api/teams/<int:team_id>/scans', methods=['GET'])
@login_required
def api_team_scans(team_id):
    """获取团队扫描历史"""
    user = get_current_user()
    db = get_db()

    if not _get_team_detail(team_id, user['id'], db):
        return jsonify({'code': -1, 'msg': '无权访问'}), HTTP_UNAUTHORIZED

    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 50)
    offset = (page - 1) * per_page

    total = db.execute("""
        SELECT COUNT(*) as cnt FROM scans WHERE team_id = ?
    """, (team_id,)).fetchone()['cnt']

    scans = db.execute("""
        SELECT s.id, s.title, s.language, s.score, s.issue_count,
               s.created_at, u.email as scanner_email
        FROM scans s
        LEFT JOIN users u ON u.id = s.user_id
        WHERE s.team_id = ?
        ORDER BY s.created_at DESC
        LIMIT ? OFFSET ?
    """, (team_id, per_page, offset)).fetchall()

    return jsonify({
        'code': 0,
        'data': {
            'total': total,
            'page': page,
            'per_page': per_page,
            'scans': [dict(s) for s in scans]
        }
    })


# ══════════════════════════════════════════════════════════
#  API路由 - 转让所有权
# ══════════════════════════════════════════════════════════

@app.route('/api/teams/<int:team_id>/transfer', methods=['POST'])
@login_required
def api_transfer_ownership(team_id):
    """转让团队所有权"""
    user = get_current_user()
    db = get_db()

    if not _is_team_owner(team_id, user['id'], db):
        return jsonify({'code': -1, 'msg': '仅团队所有者可转让'}), HTTP_UNAUTHORIZED

    data = request.get_json(silent=True) or {}
    target_user_id = data.get('user_id')
    if not target_user_id:
        return jsonify({'code': -1, 'msg': '请指定转让目标'}), HTTP_BAD_REQUEST

    target_user_id = int(target_user_id)

    # 目标必须是现有成员
    target = db.execute("""
        SELECT role FROM team_members WHERE team_id = ? AND user_id = ?
    """, (team_id, target_user_id)).fetchone()
    if not target:
        return jsonify({'code': -1, 'msg': '目标用户不是团队子账号'}), HTTP_BAD_REQUEST

    try:
        # 原owner降级为admin
        db.execute("""
            UPDATE team_members SET role = ? WHERE team_id = ? AND user_id = ?
        """, (TEAM_ROLE_ADMIN, team_id, user['id']))
        # 新owner升级
        db.execute("""
            UPDATE team_members SET role = ? WHERE team_id = ? AND user_id = ?
        """, (TEAM_ROLE_OWNER, team_id, target_user_id))
        # 更新teams表的owner_id
        db.execute("UPDATE teams SET owner_id = ? WHERE id = ?", (target_user_id, team_id))
        db.commit()

        logger.info(f"[团队] 用户{user['id']}将团队{team_id}所有权转让给{target_user_id}")
        return jsonify({'code': 0, 'msg': '所有权已转让'})

    except Exception as e:
        db.rollback()
        logger.error(f"[团队] 转让所有权失败: {e}")
        return jsonify({'code': -1, 'msg': '转让失败'}), HTTP_BAD_REQUEST


# ══════════════════════════════════════════════════════════
#  API路由 - 邀请链接管理
# ══════════════════════════════════════════════════════════

@app.route('/api/teams/<int:team_id>/invite-link', methods=['POST'])
@login_required
def api_create_invite_link(team_id):
    """生成邀请链接"""
    user = get_current_user()
    db = get_db()

    if not _is_team_admin(team_id, user['id'], db):
        return jsonify({'code': -1, 'msg': '仅管理员可生成邀请链接'}), HTTP_UNAUTHORIZED

    token = _generate_invitation_token()
    expires_at = (datetime.now() + timedelta(days=INVITATION_EXPIRE_DAYS)).strftime('%Y-%m-%d %H:%M:%S')

    db.execute("""
        INSERT INTO team_invitations (team_id, inviter_id, invitee_email, token, expires_at)
        VALUES (?, ?, ?, ?, ?)
    """, (team_id, user['id'], '__link__', token, expires_at))
    db.commit()

    invite_url = request.host_url.rstrip('/') + f'/team/invite/{token}'

    return jsonify({
        'code': 0,
        'data': {
            'url': invite_url,
            'token': token,
            'expires_at': expires_at
        }
    })


@app.route('/api/teams/invitations/<int:invitation_id>', methods=['DELETE'])
@login_required
def api_cancel_invitation(invitation_id):
    """取消/撤销邀请"""
    user = get_current_user()
    db = get_db()

    invite = db.execute("""
        SELECT * FROM team_invitations WHERE id = ?
    """, (invitation_id,)).fetchone()

    if not invite:
        return jsonify({'code': -1, 'msg': '邀请不存在'}), HTTP_BAD_REQUEST

    if not _is_team_admin(invite['team_id'], user['id'], db):
        return jsonify({'code': -1, 'msg': '无权操作'}), HTTP_UNAUTHORIZED

    db.execute("UPDATE team_invitations SET status = 'expired' WHERE id = ?", (invitation_id,))
    db.commit()

    return jsonify({'code': 0, 'msg': '邀请已取消'})
