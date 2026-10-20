"""CSRF Protection Module for Xinpect"""
import secrets
from functools import wraps
from flask import session, request, jsonify


def generate_csrf_token():
    """Generate or return existing CSRF token"""
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return session['_csrf_token']


def validate_csrf_token():
    """Validate CSRF token from request"""
    token = session.get('_csrf_token')
    if not token:
        return False
    # Check form data, headers, and JSON body
    submitted = (
        request.form.get('_csrf_token') or
        request.headers.get('X-CSRF-Token') or
        (request.get_json(silent=True) or {}).get('_csrf_token') or
        ''
    )
    return secrets.compare_digest(submitted, token)


def _same_origin():
    """校验请求确实来自本站（Origin/Referer 主域一致）

    为什么需要这一层：下面保留了 X-Requested-With 这条 AJAX 豁免，而这个
    头是客户端可任意设置的。只靠它等于没有 CSRF 防护——必须独立确认请求
    发起方就是本站，否则跨站页面伪造该头即可绕过。
    """
    from urllib.parse import urlsplit

    def _netloc(value):
        try:
            return (urlsplit(value).netloc or '').lower()
        except ValueError:
            return ''

    host = (request.host or '').lower()
    origin = request.headers.get('Origin')
    if origin:
        return _netloc(origin) == host
    referer = request.headers.get('Referer')
    if referer:
        return _netloc(referer) == host
    # 无 Origin/Referer：服务端/命令行调用，交由 API Key 或 token 判定
    return True


def csrf_required(f):
    """Decorator to require CSRF validation on POST/PUT/DELETE"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method in ('POST', 'PUT', 'DELETE'):
            # 第一道：跨站来源直接拒绝，不依赖客户端可控的头
            if not _same_origin():
                if request.is_json or request.headers.get('Accept', '').startswith('application/json'):
                    return jsonify({'error': 'cross-origin request rejected'}), 403
                return jsonify({'error': 'cross-origin request rejected'}), 403

            # API Key认证豁免CSRF（CI/CD场景）
            api_key = request.headers.get('X-API-Key', '')
            if api_key:
                # 验证API Key是否有效
                from modules.ci import _verify_ci_api_key
                user_id, _ = _verify_ci_api_key(api_key)
                if user_id:
                    return f(*args, **kwargs)
            
            # Accept X-Requested-With for AJAX (browsers block cross-origin header setting)
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return f(*args, **kwargs)
            if not validate_csrf_token():
                if request.is_json or request.headers.get('Accept', '').startswith('application/json'):
                    return jsonify({'error': 'CSRF token missing or invalid'}), 403
                from flask import flash, redirect, url_for
                flash('安全验证失败，请重新操作', 'error')
                return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated
