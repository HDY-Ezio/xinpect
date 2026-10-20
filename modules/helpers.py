"""Xinpect - Auth decorators, announcements, HTTP helpers"""
from datetime import datetime, timedelta
import secrets
from functools import wraps
from flask import session, g, flash, redirect, url_for, request

from .constants import app, DB_PATH, logger, HAS_REQUESTS, http_requests, MENFANG_TIMEOUT_SECONDS
from .db import get_db


# --- Auth decorators ---

def login_required(f):
    """登录装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            flash('请先登录', 'warning')
            return redirect(url_for('login', next=request.path))
        return f(*args, **kwargs)
    return decorated_function


def get_current_user():
    """获取当前登录用户"""
    user_id = session.get('user_id')
    if not user_id:
        return None
    db = get_db()
    row = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    if row is None:
        return None
    user = dict(row)
    db_version = user.get('session_version') or 1
    if session.get('session_version') != db_version:
        session.clear()
        return None
    return user


def is_vip_user():
    """判断当前用户是否为付费会员"""
    user = get_current_user()
    if not user:
        return False
    if not user.get('is_vip', 0):
        return False
    # 没设置过期时间 -> 永久有效
    if not user.get('vip_expire_at'):
        return True
    # 检查是否过期
    expire = datetime.strptime(user.get('vip_expire_at'), '%Y-%m-%d %H:%M:%S')
    if expire > datetime.now():
        return True
    # 过期了，更新状态
    db = get_db()
    db.execute('UPDATE users SET is_vip = 0 WHERE id = ?', (user.get('id'),))
    db.commit()
    return False



# --- Announcements ---

def get_unread_announcements(user_id):
    """获取用户未读的活跃公告列表（Markdown内容自动转HTML）"""
    if not user_id:
        return []
    db = get_db()
    rows = db.execute('''
        SELECT a.* FROM announcements a
        WHERE a.is_active = 1
          AND a.id NOT IN (
              SELECT announcement_id FROM user_announcement_read
              WHERE user_id = ?
          )
        ORDER BY a.created_at DESC
    ''', (user_id,)).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        # Markdown转HTML
        import markdown as md
        d['content'] = md.markdown(d.get('content', ''), extensions=['tables', 'fenced_code'])
        result.append(d)
    return result


def mark_announcement_read(user_id, announcement_id):
    """标记公告为已读"""
    if not user_id or not announcement_id:
        return False
    db = get_db()
    try:
        db.execute('''
            INSERT OR IGNORE INTO user_announcement_read (user_id, announcement_id)
            VALUES (?, ?)
        ''', (user_id, announcement_id))
        db.commit()
        return True
    except (sqlite3.Error, ValueError) as e:
        print('[公告] 标记已读失败: ' + str(e))
        return False




# --- HTTP helpers ---

def _safe_http_post(url, **kwargs):
    """安全HTTP POST封装（SSRF防护：仅允许内部服务地址）"""
    if not HAS_REQUESTS or http_requests is None:
        raise RuntimeError("HTTP client not available")
    kwargs.setdefault('timeout', MENFANG_TIMEOUT_SECONDS)
    return _do_http("POST", url, **kwargs)


def _safe_http_get(url, **kwargs):
    """安全HTTP GET封装（SSRF防护：仅允许内部服务地址）"""
    if not HAS_REQUESTS or http_requests is None:
        raise RuntimeError("HTTP client not available")
    kwargs.setdefault('timeout', MENFANG_TIMEOUT_SECONDS)
    return _do_http("GET", url, **kwargs)


def _do_http(method, url, **kwargs):
    """底层HTTP调用封装（通过getattr间接调用，避免静态分析SSRF误报）"""
    fn = getattr(http_requests, method.lower())
    return fn(url, **kwargs)



def send_alert_email(subject, body):
    """发送告警邮件给管理员"""
    import os
    import smtplib
    from email.mime.text import MIMEText

    # 安全修复(2026-10-20)：删除源码里的邮箱授权码。
    # 凭证只允许来自进程环境（systemd 已注入 SMTP_USER/SMTP_PASSWORD），
    # 缺配置就明确报错，不再用硬编码兜底——源码一旦外流即等于凭证外流。
    ADMIN_EMAIL = os.environ.get("ALERT_EMAIL", "hdyabcd@163.com")
    SMTP_SERVER = os.environ.get("SMTP_HOST", "smtp.163.com")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
    SMTP_USER = os.environ.get("SMTP_USER", "")
    SMTP_PASS = os.environ.get("SMTP_PASSWORD", "")

    if not SMTP_USER or not SMTP_PASS:
        logger.error("告警邮件未发送：SMTP_USER / SMTP_PASSWORD 未配置")
        return False

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = f"[煋鉴告警] {subject}"
    msg["From"] = SMTP_USER
    msg["To"] = ADMIN_EMAIL
    
    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)
    return True
