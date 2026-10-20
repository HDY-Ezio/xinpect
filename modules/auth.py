"""Xinpect - Authentication, dashboard, referral/announcement APIs"""
import re
import json
import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    session, flash, jsonify, make_response
)
from werkzeug.security import generate_password_hash, check_password_hash

from .constants import (
    app, logger,
    BRAINS, BRAINS_MAP, TIERS,
    MIN_PASSWORD_LENGTH, RESET_CODE_EXPIRY_MINUTES, RESET_CODE_LENGTH,
    RESET_CODE_CHECK_LENGTH,
    REFERRAL_COOKIE_MAX_AGE,
    REFERRAL_REGISTER_CREDITS, REFERRAL_REWARD_RATIO, SUBSCRIPTION_CREDITS,
    DAILY_LIMIT_FREE, DAILY_LIMIT_REGISTERED,
    DEFAULT_CREDIT_TX_LIMIT,
    MENFANG_BASE_URL, MENFANG_TIMEOUT_SECONDS,
    HAS_REQUESTS,
    SUBSCRIPTION_CREDITS, CREDIT_PACKS,
    HTTP_OK, HTTP_BAD_REQUEST, HTTP_UNAUTHORIZED, HTTP_FORBIDDEN,
)
from .db import get_db, is_admin_user
from .helpers import login_required, get_current_user, is_vip_user, get_unread_announcements, mark_announcement_read
from .scoring import get_user_credits, get_credit_pools, get_daily_usage, get_credit_transactions, grant_credits
from .referral import ensure_user_referral_code, get_referral_stats, generate_unique_referral_code
from .payment import _menfang_login_with_hash, _menfang_ensure_registered
from .csrf_protection import csrf_required
from .email_sender import send_reset_code_email
from . import login_guard


auth_bp = Blueprint("auth", __name__)


# --- Auth routes ---

def _safe_local_next(next_url):
    """登录后跳转白名单化：只接受站内绝对路径

    旧写法 `next_url.startswith('/')` 会放行 `//evil.com/x`（协议相对 URL），
    构成开放跳转，可被用来把登录成功的用户导向钓鱼站。
    """
    if not next_url:
        return None
    candidate = next_url.strip()
    if len(candidate) > 200 or '\r' in candidate or '\n' in candidate:
        return None
    if not candidate.startswith('/'):
        return None
    if candidate.startswith('//') or candidate.startswith('/\\'):
        return None
    from urllib.parse import urlsplit
    parts = urlsplit(candidate)
    if parts.scheme or parts.netloc:
        return None
    return candidate


def _complete_login_session(user, email, password, db):
    """登录成功后设置session、同步门房token"""
    # 防会话固定：登录成功后清除旧 session，重建新 session
    session.clear()
    session['user_id'] = user.get('id')
    session['session_version'] = user.get('session_version') or 1
    session['user_email'] = user.get('email', '')
    session['is_vip'] = bool(user.get('is_vip', 0))
    session['bonus_credits'] = user.get('bonus_credits', 0) or 0

    mf_pwd_hash = user.get('mf_password_hash', '') or None
    if not mf_pwd_hash:
        mf_pwd_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
        db.execute('UPDATE users SET mf_password_hash = ? WHERE id = ?', (mf_pwd_hash, user.get('id')))
        db.commit()

    mf_token = _menfang_login_with_hash(email, mf_pwd_hash)
    if not mf_token:
        _menfang_ensure_registered(email, mf_pwd_hash)
        mf_token = _menfang_login_with_hash(email, mf_pwd_hash)
    if mf_token:
        session['mf_token'] = mf_token


@app.route('/login', methods=['GET', 'POST'])
def login():
    """登录"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        errors = {}
        _email_re = r'^[\w\.-]+@[\w\.-]+\.\w+$'
        if not email or not re.match(_email_re, email):
            errors['error_email'] = '请输入有效的邮箱地址'
        if not password:
            errors['error_password'] = '请输入密码'
        if errors:
            return render_template('login.html', email=email, **errors)

        db = get_db()
        _ip = login_guard.client_ip()

        # 限速：同一账号+IP 连续失败达到阈值即拒绝，避免离线字典慢速撞库
        _blocked, _retry = login_guard.check_blocked(db, 'login', email, _ip)
        if _blocked:
            resp = render_template(
                'login.html', email=email,
                error_password=f'尝试次数过多，请 {max(1, _retry // 60)} 分钟后再试')
            resp = make_response(resp, 429)
            resp.headers['Retry-After'] = str(_retry)
            return resp

        user = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        user = dict(user) if user else None

        if not user or not check_password_hash(user.get('password_hash', ''), password):
            login_guard.record_failure(db, 'login', email, _ip)
            errors['error_password'] = '邮箱或密码错误'
            return render_template('login.html', email=email, **errors)

        login_guard.clear_failures(db, 'login', email, _ip)
        login_guard.prune(db)
        _complete_login_session(user, email, password, db)
        flash('登录成功', 'success')
        next_url = _safe_local_next(request.args.get('next'))
        if next_url:
            return redirect(next_url)
        return redirect(url_for('dashboard_page'))

    resp = make_response(render_template('login.html'))
    ref_code = request.args.get('ref', '').strip()
    if ref_code:
        resp.set_cookie('ref_code', ref_code, max_age=REFERRAL_COOKIE_MAX_AGE)
    return resp


def _bind_referral(db, user_id):
    """绑定推荐关系，返回 referrer_id 或 None。
    优先读cookie（链接方式），其次读表单字段（手动输入方式）"""
    ref_code = request.cookies.get('ref_code', '').strip()
    if not ref_code:
        ref_code = request.form.get('ref_code', '').strip()
    if not ref_code:
        return None
    referrer = db.execute(
        'SELECT id FROM users WHERE referral_code = ?', (ref_code,)
    ).fetchone()
    if referrer and referrer['id'] != user_id:
        db.execute('UPDATE users SET referred_by = ? WHERE id = ?', (referrer['id'], user_id))
        db.commit()
        return referrer['id']
    return None


def _grant_referral_register_reward(db, user_id, referrer_id):
    """发放推荐注册奖励：推荐人和被推荐人各得30积分"""
    if REFERRAL_REGISTER_CREDITS <= 0:
        return
    try:
        # 推荐人获得30积分
        db.execute(
            'INSERT INTO referral_rewards '
            '(referrer_user_id, referred_user_id, reward_credits, reward_type) '
            'VALUES (?, ?, ?, ?)',
            (referrer_id, user_id, REFERRAL_REGISTER_CREDITS, 'register_referrer')
        )
        grant_credits(
            referrer_id, REFERRAL_REGISTER_CREDITS,
            ref_type='referral_register', ref_id=user_id,
            remark='推荐好友注册奖励'
        )
        # 被推荐人获得30积分
        db.execute(
            'INSERT INTO referral_rewards '
            '(referrer_user_id, referred_user_id, reward_credits, reward_type) '
            'VALUES (?, ?, ?, ?)',
            (referrer_id, user_id, REFERRAL_REGISTER_CREDITS, 'register_referred')
        )
        grant_credits(
            user_id, REFERRAL_REGISTER_CREDITS,
            ref_type='referral_register', ref_id=user_id,
            remark='新用户注册奖励（好友推荐）'
        )
        db.commit()
    except (sqlite3.Error, ValueError) as e:
        logger.warning('[推荐] 注册奖励发放失败 user_id=%s referrer=%s: %s', user_id, referrer_id, e)


@app.route('/register', methods=['GET', 'POST'])
@csrf_required
def register():
    """注册"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        errors = {}
        _email_re = r'^[\w\.-]+@[\w\.-]+\.\w+$'
        if not email or not re.match(_email_re, email):
            errors['error_email'] = '请输入有效的邮箱地址'
        if len(password) < MIN_PASSWORD_LENGTH:
            errors['error_password'] = '密码至少 6 位字符'
        if password != confirm_password:
            errors['error_confirm'] = '两次输入的密码不一致'
        if errors:
            return render_template('register.html', email=email, **errors)

        db = get_db()
        existing = db.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
        if existing:
            errors['error_email'] = '该邮箱已被注册'
            return render_template('register.html', email=email, **errors)

        password_hash = generate_password_hash(password)
        mf_pwd_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
        cursor = db.execute(
            'INSERT INTO users (email, password_hash, mf_password_hash) VALUES (?, ?, ?)',
            (email, password_hash, mf_pwd_hash)
        )
        db.commit()
        user_id = cursor.lastrowid

        user_ref_code = generate_unique_referral_code(db)
        db.execute('UPDATE users SET referral_code = ? WHERE id = ?', (user_ref_code, user_id))

        referrer_id = _bind_referral(db, user_id)
        if referrer_id:
            _grant_referral_register_reward(db, user_id, referrer_id)

        _menfang_ensure_registered(email, mf_pwd_hash)
        session.clear()  # Prevent session fixation
        session['user_id'] = user_id
        # 必须与 users.session_version 对齐：get_current_user() 会校验该字段，
        # 缺省值时注册完会被立刻判定"登录已过期"踢回登录页。
        session['session_version'] = 1
        session['user_email'] = email
        session['is_vip'] = False
        flash('注册成功，欢迎使用煋鉴！', 'success')
        return redirect(url_for('dashboard_page'))

    resp = make_response(render_template('register.html'))
    ref_code = request.args.get('ref', '').strip()
    if ref_code:
        resp.set_cookie('ref_code', ref_code, max_age=REFERRAL_COOKIE_MAX_AGE)
    return resp


@app.route('/logout')
def logout():
    """登出"""
    session.clear()
    flash('已退出登录', 'info')
    return redirect(url_for('index'))


@app.route('/forgot-password', methods=['GET', 'POST'])
@csrf_required
def forgot_password():
    """忘记密码 - 发送重置验证码"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        _email_re = r'^[\w\.-]+@[\w\.-]+\.\w+$'
        if not email or not re.match(_email_re, email):
            flash('请输入有效的邮箱地址', 'error')
            return render_template('forgot_password.html', step=1, email=email)

        db = get_db()
        user = db.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()

        # 防枚举 + 防邮件轰炸：无论邮箱是否存在，响应与跳转完全一致；
        # 同一邮箱 15 分钟内最多真正发 3 封，超出后仍返回同样的提示。
        _generic = '如果该邮箱已注册，验证码已发送，请查收（15 分钟内有效）'
        if not user:
            flash(_generic, 'info')
            return redirect(url_for('reset_password'))

        _recent = db.execute(
            "SELECT COUNT(*) FROM reset_codes WHERE email = ? "
            "AND created_at > datetime('now','localtime','-15 minutes')",
            (email,)
        ).fetchone()[0]
        if _recent >= 3:
            flash(_generic, 'info')
            return redirect(url_for('reset_password'))

        code = ''.join([str(secrets.randbelow(10)) for _ in range(RESET_CODE_LENGTH)])
        expires_at = (datetime.now() + timedelta(minutes=RESET_CODE_EXPIRY_MINUTES)).strftime('%Y-%m-%d %H:%M:%S')
        db.execute('INSERT INTO reset_codes (email, code, expires_at) VALUES (?, ?, ?)',
                   (email, code, expires_at))
        db.commit()
        session['reset_email'] = email
        session['reset_code'] = code
        # 发送邮件
        mail_ok = send_reset_code_email(email, code, RESET_CODE_EXPIRY_MINUTES)
        if not mail_ok:
            # 对外仍返回同一句话，避免通过"发送失败"反推邮箱是否存在
            logger.error('[密码重置] 邮件发送失败 email=%s', email)
        flash(_generic, 'success')
        return redirect(url_for('reset_password'))

    return render_template('forgot_password.html', step=1)


@app.route('/reset-password', methods=['GET', 'POST'])
@csrf_required
def reset_password():
    """重置密码 - 验证验证码并设置新密码"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        code = request.form.get('code', '').strip()
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        errors = {}
        _email_re = r'^[\w\.-]+@[\w\.-]+\.\w+$'
        if not email or not re.match(_email_re, email):
            errors['error_email'] = '请输入有效的邮箱地址'
        if len(code) != RESET_CODE_CHECK_LENGTH:
            errors['error_code'] = '请输入6位验证码'
        if len(new_password) < MIN_PASSWORD_LENGTH:
            errors['error_password'] = '密码至少6位字符'
        if new_password != confirm_password:
            errors['error_confirm'] = '两次输入的密码不一致'
        if errors:
            return render_template('forgot_password.html', step=2, email=email, code=code, **errors)

        db = get_db()
        _ip = login_guard.client_ip()

        # 6 位验证码可穷举：必须按"邮箱+IP"计失败次数，达到阈值直接拒绝，
        # 否则攻击者可用百万级请求撞开任意账号。
        _blocked, _retry = login_guard.check_blocked(db, 'reset_code', email, _ip)
        if _blocked:
            errors['error_code'] = f'尝试次数过多，请 {max(1, _retry // 60)} 分钟后重新获取验证码'
            return render_template('forgot_password.html', step=2, email=email,
                                   code='', **errors), 429

        reset_record = db.execute(
            'SELECT * FROM reset_codes WHERE email = ? AND code = ? AND used = 0 ORDER BY id DESC LIMIT 1',
            (email, code)
        ).fetchone()
        if not reset_record:
            login_guard.record_failure(db, 'reset_code', email, _ip)
            errors['error_code'] = '验证码错误或已失效'
            return render_template('forgot_password.html', step=2, email=email, code='', **errors)

        try:
            expires_at = datetime.strptime(reset_record['expires_at'], '%Y-%m-%d %H:%M:%S')
            if datetime.now() > expires_at:
                errors['error_code'] = '验证码已过期，请重新获取'
                return render_template('forgot_password.html', step=2, email=email, code=code, **errors)
        except (ValueError, TypeError) as e:
            logger.debug('expiry check failed, proceeding with reset: %s', e)

        password_hash = generate_password_hash(new_password)
        mf_pwd_hash = hashlib.sha256(new_password.encode('utf-8')).hexdigest()
        db.execute('UPDATE users SET password_hash = ?, mf_password_hash = ? WHERE email = ?',
                   (password_hash, mf_pwd_hash, email))
        db.execute('UPDATE reset_codes SET used = 1 WHERE id = ?', (reset_record['id'],))
        # 改密后让所有旧会话立即失效（否则被盗会话在改密后仍然有效）
        db.execute('UPDATE users SET session_version = COALESCE(session_version, 1) + 1 '
                   'WHERE email = ?', (email,))
        db.commit()
        login_guard.clear_failures(db, 'reset_code', email, _ip)

        try:
            if HAS_REQUESTS:
                from .helpers import _safe_http_post
                _safe_http_post(
                    f'{MENFANG_BASE_URL}/api/auth/register',
                    json={'email': email, 'password_hash': mf_pwd_hash},
                    timeout=MENFANG_TIMEOUT_SECONDS
                )
        except (ConnectionError, OSError) as e:
            logger.warning('门房密码同步失败: %s', e)

        session.pop('reset_email', None)
        session.pop('reset_code', None)
        flash('密码重置成功，请用新密码登录', 'success')
        return redirect(url_for('login'))

    email = session.get('reset_email', '')
    return render_template('forgot_password.html', step=2, email=email)


@app.route('/dashboard/account')
@login_required
def account_page():
    """我的账户页面"""
    user = get_current_user()
    db = get_db()
    orders = db.execute(
        'SELECT * FROM orders WHERE user_id = ? ORDER BY id DESC LIMIT 10',
        (user.get('id'),)
    ).fetchall()

    daily = get_daily_usage() if not is_vip_user() else 0
    daily_limit = DAILY_LIMIT_REGISTERED if session.get('user_id') else DAILY_LIMIT_FREE
    vip = is_vip_user()
    credit_balance = get_user_credits(user.get('id')) if vip else 0
    credit_txs = get_credit_transactions(user.get('id'), limit=DEFAULT_CREDIT_TX_LIMIT) if vip else []
    referral_code = ensure_user_referral_code(db, user.get('id'))
    referral_stats = get_referral_stats(user.get('id'))
    unread_announcements = get_unread_announcements(user.get('id'))

    return render_template('dashboard/account.html',
                           user=user, orders=orders, is_vip=vip,
                           daily_usage=daily, daily_limit=daily_limit,
                           credit_balance=credit_balance,
                           credit_transactions=credit_txs,
                           referral_code=referral_code,
                           referral_stats=referral_stats,
                           unread_announcements=unread_announcements,
                           page='account')




@app.route("/api/account/change-password", methods=["POST"])
@login_required
@csrf_required
def api_change_password():
    """修改密码"""
    user = get_current_user()
    db = get_db()

    data = request.get_json() or {}
    current_password = (data.get("current_password") or "").strip()
    new_password = (data.get("new_password") or "").strip()
    confirm_password = (data.get("confirm_password") or "").strip()

    # 验证
    if not current_password:
        return jsonify({"success": False, "error": "请输入当前密码"}), HTTP_BAD_REQUEST
    if len(new_password) < MIN_PASSWORD_LENGTH:
        return jsonify({"success": False, "error": f"新密码至少 {MIN_PASSWORD_LENGTH} 位"}), HTTP_BAD_REQUEST
    if new_password == current_password:
        return jsonify({"success": False, "error": "新密码不能与当前密码相同"}), HTTP_BAD_REQUEST
    if new_password != confirm_password:
        return jsonify({"success": False, "error": "两次输入的新密码不一致"}), HTTP_BAD_REQUEST
    if not check_password_hash(user.get("password_hash", ""), current_password):
        return jsonify({"success": False, "error": "当前密码错误"}), HTTP_UNAUTHORIZED

    # 更新密码
    new_hash = generate_password_hash(new_password)
    new_mf_hash = hashlib.sha256(new_password.encode("utf-8")).hexdigest()
    db.execute(
        "UPDATE users SET password_hash = ?, mf_password_hash = ? WHERE id = ?",
        (new_hash, new_mf_hash, user["id"])
    )
    db.commit()

    # 同步门房
    try:
        from .helpers import _safe_http_post
        _safe_http_post(
            f"{MENFANG_BASE_URL}/api/auth/register",
            json={"email": user["email"], "password_hash": new_mf_hash},
            timeout=MENFANG_TIMEOUT_SECONDS
        )
    except Exception as e:
        logger.warning("门房密码同步失败(非致命): %s", e)

    # 升级 session 版本，所有旧 session 自动失效
    db.execute("UPDATE users SET session_version = COALESCE(session_version, 1) + 1 WHERE id = ?", (user['id'],))
    db.commit()
    session.clear()
    return jsonify({"success": True, "message": "密码修改成功，请重新登录"})




@app.route('/api/account/force-logout', methods=['POST'])
@login_required
@csrf_required
def api_force_logout():
    """强制当前账号所有设备登出：提升 session_version 使所有旧 session 失效"""
    user = get_current_user()
    db = get_db()
    db.execute("UPDATE users SET session_version = COALESCE(session_version, 1) + 1 WHERE id = ?", (user['id'],))
    db.commit()
    session.clear()
    return jsonify({"success": True, "message": "已强制所有设备登出，请重新登录"})

# ============================================================
# Dashboard 拆分
# ============================================================

def _build_base_context(user, vip):
    """构建 dashboard 通用上下文"""
    credit_balance = get_user_credits(user.get('id')) if vip and user else 0
    unread_anns = get_unread_announcements(user.get('id')) if user else []
    credit_info = get_credit_pools(user.get('id')) if vip and user else None

    return {
        'user_email': user.get('email', '') if user else '',
        'is_vip': vip,
        'bonus_credits': user.get('bonus_credits', 0) if user else 0,
        'credit_balance': credit_balance,
        'credit_info': credit_info,
        'unread_announcements': unread_anns,
    }


def _dashboard_overview_data(user, vip, db):
    """构建概览页数据"""
    today = datetime.now().strftime('%Y-%m-%d')
    usage_row = db.execute(
        'SELECT count FROM daily_usage WHERE date = ? AND user_id = ?',
        (today, user.get('id'))
    ).fetchone()
    today_scans = usage_row['count'] if usage_row else 0

    total_scans_row = db.execute(
        'SELECT COUNT(*) as cnt,'
        ' COALESCE(SUM(issue_count), 0) as issues'
        ' FROM scans WHERE user_id = ?',
        (user.get('id'),)
    ).fetchone()

    remaining = max(0, DAILY_LIMIT_REGISTERED - today_scans) if not vip else -1

    vip_expire = ''
    if vip and user.get('vip_expire_at'):
        try:
            vip_expire = user.get('vip_expire_at')
        except (KeyError, TypeError):
            vip_expire = '永久'

    recent = db.execute(
        'SELECT scan_id, title, file_count, issue_count, score, grade, created_at, credits_spent '
        'FROM scans WHERE user_id = ? ORDER BY created_at DESC LIMIT 5',
        (user.get('id'),)
    ).fetchall()

    return {
        'stats': {
            'total_scans': total_scans_row['cnt'],
            'today_scans': today_scans,
            'remaining': remaining,
            'total_issues': total_scans_row['issues'],
        },
        'vip_expire': vip_expire,
        'recent_scans': [dict(r) for r in recent],
    }


# --- Dashboard 入口 ---

@app.route('/dashboard')
@app.route('/dashboard/<page>')
@login_required
def dashboard_page(page='overview'):
    """会员中心各页面"""
    user = get_current_user()
    if user is None:
        session.clear()
        flash('登录已过期，请重新登录', 'warning')
        return redirect(url_for('login', next=request.path))
    vip = is_vip_user()
    db = get_db()

    context = _build_base_context(user, vip)
    context['page'] = page

    if page == 'overview':
        context.update(_dashboard_overview_data(user, vip, db))
        return render_template('dashboard/overview.html', **context)


    if page == 'repos':
        from modules.db import get_db as _gdb
        _db = _gdb()
        _u = _db.execute("SELECT github_username FROM users WHERE id = ?", (user.get('id'),)).fetchone()
        context['gh_connected'] = bool(_u and _u[0])
        context['gh_username'] = _u[0] if _u else ''
        return render_template('dashboard/repos.html', **context)

    if page == 'invoice':
        context.update(_dashboard_invoice_data(user, vip, db))
        return render_template('dashboard/invoice.html', **context)

    # recommend 页需要推荐数据
    if page == 'recommend':
        referral_code = ensure_user_referral_code(db, user.get('id'))
        referral_stats = get_referral_stats(user.get('id'))
        context['referral_code'] = referral_code
        context['referral_stats'] = referral_stats
        return render_template('dashboard/recommend.html', **context)

    simple_pages = {
        'credits': ('dashboard/credits.html', None),
        'scans': ('dashboard/scans.html', _dashboard_scans_data),
        'orders': ('dashboard/orders.html', _dashboard_orders_data),
        'api-keys': ('dashboard/api_keys.html', _dashboard_api_keys_data),
        'recharge': ('dashboard/recharge.html', None),
        'thresholds': ('dashboard/thresholds.html', None),
        'gates': ('dashboard/gates.html', None),
        'trends': ('dashboard/trends.html', None),
        'compare': ('dashboard/compare.html', None),
        'alerts': ('dashboard/alerts.html', None),
        'versions': ('dashboard/versions.html', None),
        'deploy': ('dashboard/deploy.html', None),
        'benchmark': ('dashboard/benchmark.html', None),
    }

    if page in simple_pages:
        template, data_fn = simple_pages[page]
        if data_fn:
            context.update(data_fn(user, vip, db))
        return render_template(template, **context)

    return redirect(url_for('dashboard_page', page='overview'))


def _dashboard_scans_data(user, vip, db):
    """我的检测页数据"""
    scans = db.execute(
        'SELECT scan_id, title, file_count, issue_count, score, grade, created_at '
        'FROM scans WHERE user_id = ? ORDER BY created_at DESC',
        (user.get('id'),)
    ).fetchall()
    return {'scans': [dict(s) for s in scans]}


def _dashboard_orders_data(user, vip, db):
    """订单列表页数据"""
    orders = db.execute(
        'SELECT order_id, plan_id, plan_name, amount, status, created_at '
        'FROM orders WHERE user_id = ? ORDER BY created_at DESC',
        (user.get('id'),)
    ).fetchall()
    return {'orders': [dict(o) for o in orders]}


def _dashboard_invoice_data(user, vip, db):
    """开票页数据：可开票订单 + 开票记录"""
    uid = user.get('id')

    # 查询所有已支付订单
    paid_orders = db.execute(
        'SELECT order_id, plan_name, amount, created_at '
        'FROM orders WHERE user_id = ? AND status = ? ORDER BY created_at DESC',
        (uid, 'paid')
    ).fetchall()

    # 查询所有开票申请中已关联的订单号（pending + completed 的都要排除）
    inv_rows = db.execute(
        'SELECT order_id FROM invoice_requests WHERE user_id = ? AND status IN (?, ?)',
        (uid, 'pending', 'completed')
    ).fetchall()

    locked_ids = set()
    for row in inv_rows:
        for oid in row['order_id'].split(','):
            locked_ids.add(oid.strip())

    available = [dict(o) for o in paid_orders if o['order_id'] not in locked_ids]

    # 开票记录
    invoices = db.execute(
        'SELECT id, order_id, amount, company_name, status, admin_note, created_at, completed_at '
        'FROM invoice_requests WHERE user_id = ? ORDER BY created_at DESC',
        (uid,)
    ).fetchall()

    return {
        'available_orders': available,
        'invoices': [dict(i) for i in invoices],
    }


def _dashboard_api_keys_data(user, vip, db):
    """API密钥管理页数据"""
    keys_rows = db.execute(
        'SELECT id, name, api_key, is_active, created_at, last_used, usage_count '
        'FROM api_keys WHERE user_id = ? ORDER BY created_at DESC',
        (user.get('id'),)
    ).fetchall()
    keys_list = []
    user_api_key = None
    for kr in keys_rows:
        kd = dict(kr)
        fk = kd['api_key']
        if user_api_key is None and kd.get('is_active'):
            user_api_key = fk
        kd['masked_key'] = fk[:8] + '***' if len(fk) > 8 else '***'
        del kd['api_key']
        keys_list.append(kd)
    return {
        'keys': keys_list,
        'user_api_key': user_api_key,
        'credit_balance': get_user_credits(user.get('id')) if vip else 0,
    }


# --- Referral API ---

@app.route('/api/referral/info')
@login_required
def api_referral_info():
    """获取当前用户的推荐信息"""
    user = get_current_user()
    db = get_db()
    code = ensure_user_referral_code(db, user.get('id'))
    stats = get_referral_stats(user.get('id'))
    return jsonify({
        'success': True,
        'referral_code': code,
        'referred_count': stats.get('referred_count', 0),
        'total_reward_credits': stats.get('total_reward_credits', 0),
        'register_reward_credits': REFERRAL_REGISTER_CREDITS,
        'first_pay_rewards': {k: v.get('total_credits', 0) // REFERRAL_REWARD_RATIO for k, v in SUBSCRIPTION_CREDITS.items()},
    })


# --- Announcement API ---

@app.route('/api/announcement/read/<int:announcement_id>', methods=['POST'])
@login_required
@csrf_required
def api_announcement_read(announcement_id):
    """标记公告为已读"""
    user = get_current_user()
    ok = mark_announcement_read(user.get('id'), announcement_id)
    return jsonify({'success': ok})


@app.route('/api/announcements/unread')
@login_required
def api_announcements_unread():
    """获取未读公告列表"""
    user = get_current_user()
    anns = get_unread_announcements(user.get('id'))
    return jsonify({'success': True, 'announcements': anns})


# --- Invoice API ---

@app.route('/api/invoice-request', methods=['POST'])
@login_required
@csrf_required
def api_invoice_request():
    """提交开票申请（支持多订单批量开票）"""
    user = get_current_user()
    db = get_db()
    uid = user.get('id')

    data = request.get_json() or {}
    order_ids = data.get('order_ids', [])
    company_name = (data.get('company_name') or '').strip()
    tax_number = (data.get('tax_number') or '').strip()
    email = (data.get('email') or '').strip()

    # 校验必填字段
    if not order_ids:
        return jsonify({'success': False, 'error': '请选择至少一个订单'}), HTTP_BAD_REQUEST
    if not company_name:
        return jsonify({'success': False, 'error': '请填写公司抬头'}), HTTP_BAD_REQUEST
    if not tax_number:
        return jsonify({'success': False, 'error': '请填写纳税人识别号'}), HTTP_BAD_REQUEST
    if not email:
        return jsonify({'success': False, 'error': '请填写接收邮箱'}), HTTP_BAD_REQUEST

    # 验证订单属于当前用户且已支付
    placeholders = ','.join(['?'] * len(order_ids))
    valid_orders = db.execute(
        f'SELECT order_id, amount FROM orders WHERE user_id = ? AND status = ? AND order_id IN ({placeholders})',
        (uid, 'paid') + tuple(order_ids)
    ).fetchall()

    valid_ids = {o['order_id'] for o in valid_orders}
    invalid_ids = [oid for oid in order_ids if oid not in valid_ids]
    if invalid_ids:
        return jsonify({'success': False, 'error': '以下订单无效或不属于当前用户: ' + ', '.join(invalid_ids)}), HTTP_BAD_REQUEST

    # 检查这些订单是否已有未完成的开票申请
    existing = db.execute(
        'SELECT order_id FROM invoice_requests WHERE user_id = ? AND status IN (?, ?)',
        (uid, 'pending', 'completed')
    ).fetchall()
    locked_ids = set()
    for row in existing:
        for oid in row['order_id'].split(','):
            locked_ids.add(oid.strip())
    conflict = [oid for oid in order_ids if oid in locked_ids]
    if conflict:
        return jsonify({'success': False, 'error': '以下订单已有开票申请: ' + ', '.join(conflict)}), HTTP_BAD_REQUEST

    # 计算合计金额
    total_amount = sum(o['amount'] for o in valid_orders)
    order_ids_str = ','.join(order_ids)

    db.execute(
        'INSERT INTO invoice_requests (user_id, order_id, amount, company_name, tax_number, email) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        (uid, order_ids_str, total_amount, company_name, tax_number, email)
    )
    # 写入管理员通知（用于定期检查和主动通知）
    db.execute(
        "INSERT INTO error_logs (level, source, message, details) VALUES ('warning', 'invoice_request', ?, ?)",
        (f'新开票申请: {company_name} / ¥{total_amount:.2f} / 用户ID={uid}',
         f'订单: {order_ids_str} | 税号: {tax_number} | 邮箱: {email}')
    )
    db.commit()

    return jsonify({'success': True, 'message': f'开票申请已提交，合计金额 ¥{total_amount:.2f}，我们将在3个工作日内为您开具。'})


@app.route('/api/admin/invoice-requests')
@login_required
def api_admin_invoice_requests():
    """管理员查看所有开票申请"""
    user = get_current_user()
    # 此前写死 id != 1，而真实 owner 是 6 → 管理员永远看不到开票申请
    if not is_admin_user(user.get('id')):
        return jsonify({'success': False, 'error': '无权限'}), HTTP_FORBIDDEN

    db = get_db()
    rows = db.execute(
        'SELECT ir.id, ir.user_id, ir.order_id, ir.amount, ir.company_name, ir.tax_number, '
        'ir.email, ir.status, ir.admin_note, ir.created_at, ir.completed_at, u.email as user_email '
        'FROM invoice_requests ir LEFT JOIN users u ON ir.user_id = u.id '
        'ORDER BY ir.created_at DESC'
    ).fetchall()

    return jsonify({
        'success': True,
        'data': [dict(r) for r in rows]
    })
