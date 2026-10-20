"""
P2-04: License 激活机制（私有化授权管理）

表结构:
  licenses (license_key, org_name, plan_type, max_users, max_scans,
            expires_at, status, server_fingerprint, activated_at, created_at)

API:
  POST /api/v1/license/validate   - 验证 License（Docker 容器启动时调用）
  POST /api/v1/license/activate   - 激活 License（首次绑定服务器指纹）
  GET  /api/admin/licenses        - 管理员查看所有 License
  POST /api/admin/license/create  - 管理员创建新 License
"""
import json
import hashlib
import secrets
import time
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, session as flask_session
from .db import get_db, is_admin_user
from .constants import logger

license_bp = Blueprint('license', __name__)

# ============================================================
# License Key 生成
# ============================================================
def generate_license_key():
    """生成格式: XIN-XXXX-XXXX-XXXX-XXXX"""
    parts = [secrets.token_hex(2).upper() for _ in range(4)]
    return 'XIN-' + '-'.join(parts)


def server_fingerprint():
    """生成服务器指纹（基于机器信息哈希）"""
    import socket
    import os
    info = socket.gethostname() + str(os.getpid()) + str(os.getuid())
    return hashlib.sha256(info.encode()).hexdigest()[:32]


# ============================================================
# 数据库初始化
# ============================================================
def init_license_table():
    """创建 licenses 表（如果不存在）"""
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS licenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_key TEXT UNIQUE NOT NULL,
            org_name TEXT NOT NULL DEFAULT '',
            plan_type TEXT NOT NULL DEFAULT 'pro',
            max_users INTEGER NOT NULL DEFAULT 10,
            max_scans INTEGER NOT NULL DEFAULT 1000,
            expires_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'issued',
            server_fingerprint TEXT DEFAULT '',
            activated_at TEXT DEFAULT '',
            contact_email TEXT DEFAULT '',
            note TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)
    db.commit()


# ============================================================
# 公开 API（Docker 容器调用）
# ============================================================
@license_bp.route('/api/v1/license/validate', methods=['POST'])
def validate_license():
    """
    验证 License 是否有效。
    请求: { "license_key": "XIN-...", "fingerprint": "..." }
    响应: { "valid": true/false, "plan": "...", "limits": {...}, "expires": "..." }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'valid': False, 'error': '缺少请求体'}), 400

    license_key = data.get('license_key', '').strip()
    fingerprint = data.get('fingerprint', '').strip()

    if not license_key:
        return jsonify({'valid': False, 'error': '缺少 license_key'}), 400

    db = get_db()
    row = db.execute(
        "SELECT * FROM licenses WHERE license_key = ?",
        (license_key,)
    ).fetchone()

    if not row:
        return jsonify({'valid': False, 'error': 'License 不存在'}), 404

    # 转为 dict
    lic = dict(row)

    # 检查状态
    if lic['status'] == 'revoked':
        return jsonify({'valid': False, 'error': 'License 已被撤销'})

    if lic['status'] == 'expired':
        return jsonify({'valid': False, 'error': 'License 已过期'})

    # 检查过期时间
    try:
        exp = datetime.strptime(lic['expires_at'], '%Y-%m-%d')
        if exp < datetime.now():
            db.execute("UPDATE licenses SET status='expired' WHERE id=?", (lic['id'],))
            db.commit()
            return jsonify({'valid': False, 'error': 'License 已过期'})
    except ValueError:
        pass

    # 检查指纹绑定
    if lic['server_fingerprint'] and fingerprint:
        if lic['server_fingerprint'] != fingerprint:
            return jsonify({
                'valid': False,
                'error': 'License 已绑定其他服务器',
            })

    # 返回有效信息
    plan_limits = {
        'basic': {'max_users': 5, 'max_scans': 500},
        'pro': {'max_users': 20, 'max_scans': 5000},
        'enterprise': {'max_users': 999, 'max_scans': 99999},
    }
    limits = plan_limits.get(lic['plan_type'], plan_limits['pro'])

    return jsonify({
        'valid': True,
        'org_name': lic['org_name'],
        'plan': lic['plan_type'],
        'limits': {
            'max_users': lic['max_users'] or limits['max_users'],
            'max_scans_per_month': lic['max_scans'] or limits['max_scans'],
        },
        'expires_at': lic['expires_at'],
        'features': ['full_scan', 'api', 'cli_upload', 'webhook'] if lic['plan_type'] != 'basic' else ['basic_scan', 'api'],
    })


@license_bp.route('/api/v1/license/activate', methods=['POST'])
def activate_license():
    """
    激活 License（首次绑定服务器指纹）。
    请求: { "license_key": "XIN-...", "fingerprint": "...", "org_name": "..." }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'status': 'error', 'error': '缺少请求体'}), 400

    license_key = data.get('license_key', '').strip()
    fingerprint = data.get('fingerprint', '').strip()
    org_name = data.get('org_name', '').strip()

    if not license_key or not fingerprint:
        return jsonify({'status': 'error', 'error': '缺少 license_key 或 fingerprint'}), 400

    db = get_db()
    row = db.execute(
        "SELECT * FROM licenses WHERE license_key = ?",
        (license_key,)
    ).fetchone()

    if not row:
        return jsonify({'status': 'error', 'error': 'License 不存在'}), 404

    lic = dict(row)

    if lic['status'] == 'revoked':
        return jsonify({'status': 'error', 'error': 'License 已被撤销'})

    # 检查是否已被其他服务器激活
    if lic['server_fingerprint'] and lic['server_fingerprint'] != fingerprint:
        return jsonify({
            'status': 'error',
            'error': 'License 已绑定其他服务器，请联系管理员解绑',
        })

    # 激活
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    db.execute(
        "UPDATE licenses SET status='active', server_fingerprint=?, "
        "activated_at=COALESCE(activated_at, NULLIF(activated_at,''), ?), "
        "org_name=COALESCE(NULLIF(?, ''), org_name) "
        "WHERE id=?",
        (fingerprint, now, org_name, lic['id'])
    )
    db.commit()

    return jsonify({
        'status': 'ok',
        'message': 'License 激活成功',
        'org_name': org_name or lic['org_name'],
        'plan': lic['plan_type'],
        'expires_at': lic['expires_at'],
    })


# ============================================================
# 管理员 API
# ============================================================
@license_bp.route('/api/admin/licenses', methods=['GET'])
def admin_list_licenses():
    """管理员查看所有 License"""
    if not flask_session.get('user_id'):
        return jsonify({'error': '未登录'}), 401

    # 权限判定统一走 users.is_admin
    # （此前读取不存在的 is_admin 列 → OperationalError → 本接口必定 500）
    if not is_admin_user(flask_session['user_id']):
        return jsonify({'error': '无权限'}), 403

    db = get_db()
    rows = db.execute(
        "SELECT id, license_key, org_name, plan_type, max_users, max_scans, "
        "expires_at, status, server_fingerprint, activated_at, contact_email, created_at "
        "FROM licenses ORDER BY id DESC"
    ).fetchall()

    licenses = [dict(r) for r in rows]
    return jsonify({'status': 'ok', 'licenses': licenses})


@license_bp.route('/api/admin/license/create', methods=['POST'])
def admin_create_license():
    """管理员创建新 License"""
    if not flask_session.get('user_id'):
        return jsonify({'error': '未登录'}), 401

    user_id = flask_session['user_id']
    if not is_admin_user(user_id):
        return jsonify({'error': '无权限'}), 403

    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': '缺少请求体'}), 400

    org_name = data.get('org_name', '').strip()
    plan_type = data.get('plan_type', 'pro').strip()
    max_users = data.get('max_users', 10)
    max_scans = data.get('max_scans', 1000)
    days = data.get('days', 365)
    contact_email = data.get('contact_email', '').strip()
    note = data.get('note', '').strip()

    if plan_type not in ('basic', 'pro', 'enterprise'):
        plan_type = 'pro'

    expires_at = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
    license_key = generate_license_key()

    db = get_db()
    try:
        db.execute(
            "INSERT INTO licenses "
            "(license_key, org_name, plan_type, max_users, max_scans, "
            "expires_at, status, contact_email, note) "
            "VALUES (?, ?, ?, ?, ?, ?, 'issued', ?, ?)",
            (license_key, org_name, plan_type, max_users, max_scans,
             expires_at, contact_email, note)
        )
        db.commit()
    except Exception as e:
        logger.error('Create license error: %s', e)
        return jsonify({'error': '创建失败', 'detail': str(e)}), 500

    return jsonify({
        'status': 'ok',
        'license_key': license_key,
        'org_name': org_name,
        'plan_type': plan_type,
        'expires_at': expires_at,
        'message': 'License 创建成功，请将密钥发送给客户',
    })


@license_bp.route('/api/admin/license/<int:lic_id>/revoke', methods=['POST'])
def admin_revoke_license(lic_id):
    """管理员撤销 License"""
    if not flask_session.get('user_id'):
        return jsonify({'error': '未登录'}), 401

    user_id = flask_session['user_id']
    if not is_admin_user(user_id):
        return jsonify({'error': '无权限'}), 403

    db = get_db()
    db.execute("UPDATE licenses SET status='revoked' WHERE id=?", (lic_id,))
    db.commit()
    return jsonify({'status': 'ok', 'message': 'License 已撤销'})


@license_bp.route('/api/admin/license/<int:lic_id>/extend', methods=['POST'])
def admin_extend_license(lic_id):
    """管理员延长 License 有效期"""
    if not flask_session.get('user_id'):
        return jsonify({'error': '未登录'}), 401

    user_id = flask_session['user_id']
    if not is_admin_user(user_id):
        return jsonify({'error': '无权限'}), 403

    data = request.get_json(silent=True)
    days = data.get('days', 90) if data else 90

    db = get_db()
    row = db.execute("SELECT expires_at FROM licenses WHERE id=?", (lic_id,)).fetchone()
    if not row:
        return jsonify({'error': 'License 不存在'}), 404

    try:
        current_exp = datetime.strptime(row[0], '%Y-%m-%d')
    except ValueError:
        current_exp = datetime.now()

    new_exp = (current_exp + timedelta(days=days)).strftime('%Y-%m-%d')
    db.execute(
        "UPDATE licenses SET expires_at=?, status='active' WHERE id=?",
        (new_exp, lic_id)
    )
    db.commit()

    return jsonify({
        'status': 'ok',
        'new_expires_at': new_exp,
        'message': '已延长 {} 天'.format(days),
    })
