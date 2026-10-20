"""
煋鉴 GitHub OAuth 集成
- 一键授权 GitHub 仓库访问
- 列出用户仓库
- 自动使用已保存的 token 扫描私有仓库
"""
import os
import json
import urllib.request
import urllib.error
from flask import Blueprint, request, redirect, jsonify, session, url_for, flash
from functools import wraps

github_bp = Blueprint("github_oauth", __name__)

GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")
GITHUB_REDIRECT_URI = os.environ.get("GITHUB_REDIRECT_URI", "https://xinpect.xingwangzhineng.com/api/github/callback")
GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_BASE = "https://api.github.com"

def _github_api(url, token=None, method="GET", data=None):
    """调用 GitHub API"""
    headers = {
        "Accept": "application/json",
        "User-Agent": "Xinpect/2.0",
    }
    if token:
        headers["Authorization"] = f"token {token}"
    
    req_data = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
    
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())

def login_required_api(f):
    """API 登录验证装饰器"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            return jsonify(status="error", message="请先登录"), 401
        return f(*args, **kwargs)
    return decorated

# ── 发起 OAuth 授权 ──
@github_bp.route("/api/github/authorize")
@login_required_api
def github_authorize():
    """重定向到 GitHub OAuth 授权页面"""
    if not GITHUB_CLIENT_ID:
        return jsonify(status="error", message="GitHub OAuth 未配置"), 500
    
    # 生成 state 防止 CSRF
    import secrets
    state = secrets.token_urlsafe(16)
    session["github_oauth_state"] = state
    
    params = (
        f"client_id={GITHUB_CLIENT_ID}"
        f"&redirect_uri={GITHUB_REDIRECT_URI}"
        f"&scope=repo"
        f"&state={state}"
    )
    return redirect(f"{GITHUB_AUTH_URL}?{params}")

# ── OAuth 回调 ──
@github_bp.route("/api/github/callback")
def github_callback():
    """处理 GitHub OAuth 回调"""
    code = request.args.get("code", "")
    state = request.args.get("state", "")
    
    # 验证 state
    expected_state = session.pop("github_oauth_state", "")
    if not state or state != expected_state:
        flash("GitHub 授权失败：state 验证不通过", "error")
        return redirect(url_for("dashboard_page"))
    
    if not code:
        flash("GitHub 授权失败：未收到授权码", "error")
        return redirect(url_for("dashboard_page"))
    
    # 用 code 换 access_token
    try:
        token_data = _exchange_code_for_token(code)
        access_token = token_data.get("access_token", "")
        if not access_token:
            raise ValueError(f"No access_token in response: {token_data}")
        
        # 获取 GitHub 用户信息
        gh_user = _github_api(f"{GITHUB_API_BASE}/user", token=access_token)
        github_username = gh_user.get("login", "")
        
        # 保存到数据库
        from modules.db import get_db
        db = get_db()
        user_id = session.get("user_id")
        db.execute(
            "UPDATE users SET github_token = ?, github_username = ? WHERE id = ?",
            (access_token, github_username, user_id)
        )
        db.commit()
        
        flash(f"✅ GitHub 授权成功！已连接 @{github_username}", "success")
        return redirect(url_for("dashboard_page"))
        
    except Exception as e:
        flash(f"GitHub 授权失败：{e}", "error")
        return redirect(url_for("dashboard_page"))

def _exchange_code_for_token(code):
    """用授权码换 access_token"""
    data = json.dumps({
        "client_id": GITHUB_CLIENT_ID,
        "client_secret": GITHUB_CLIENT_SECRET,
        "code": code,
        "redirect_uri": GITHUB_REDIRECT_URI,
    }).encode()
    
    req = urllib.request.Request(
        GITHUB_TOKEN_URL,
        data=data,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Xinpect/2.0",
        }
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())

# ── 列出用户仓库 ──
@github_bp.route("/api/github/repos")
@login_required_api
def github_list_repos():
    """列出用户已授权的 GitHub 仓库"""
    from modules.db import get_db
    db = get_db()
    user_id = session.get("user_id")
    
    user = db.execute(
        "SELECT github_token, github_username FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()
    
    if not user or not user[0]:
        return jsonify(status="error", message="未连接 GitHub，请先授权")
    
    token = user[0]
    
    try:
        # 获取用户的仓库（有访问权限的）
        page = request.args.get("page", "1")
        repos = _github_api(
            f"{GITHUB_API_BASE}/user/repos?sort=updated&per_page=30&page={page}",
            token=token
        )
        
        repo_list = []
        for r in repos:
            repo_list.append({
                "name": r["full_name"],
                "description": (r.get("description") or "")[:100],
                "private": r.get("private", False),
                "language": r.get("language", ""),
                "default_branch": r.get("default_branch", "main"),
                "url": r.get("html_url", ""),
                "updated_at": r.get("updated_at", ""),
            })
        
        return jsonify(status="ok", repos=repo_list)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            # Token 失效，清除
            db.execute("UPDATE users SET github_token = NULL, github_username = NULL WHERE id = ?", (user_id,))
            db.commit()
            return jsonify(status="error", message="GitHub Token 已过期，请重新授权")
        return jsonify(status="error", message=f"GitHub API 错误: {e.code}")
    except Exception as e:
        return jsonify(status="error", message=str(e))

# ── 断开连接 ──
@github_bp.route("/api/github/disconnect", methods=["POST"])
@login_required_api
def github_disconnect():
    """断开 GitHub 连接"""
    from modules.db import get_db
    db = get_db()
    user_id = session.get("user_id")
    db.execute(
        "UPDATE users SET github_token = NULL, github_username = NULL WHERE id = ?",
        (user_id,)
    )
    db.commit()
    return jsonify(status="ok", message="已断开 GitHub 连接")

# ── 检查连接状态 ──
@github_bp.route("/api/github/status")
@login_required_api
def github_status():
    """检查 GitHub 连接状态"""
    from modules.db import get_db
    db = get_db()
    user_id = session.get("user_id")
    user = db.execute(
        "SELECT github_username FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()
    
    if user and user[0]:
        return jsonify(status="ok", connected=True, username=user[0])
    return jsonify(status="ok", connected=False)

# ── 获取用户存储的 token（供 CI 模块使用）──
def get_user_github_token(user_id):
    """获取用户保存的 GitHub Token"""
    from modules.db import get_db
    db = get_db()
    row = db.execute(
        "SELECT github_token FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    return row[0] if row and row[0] else None
