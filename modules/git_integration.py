# -*- coding: utf-8 -*-
"""
Git 集成模块（一键修复的「建分支 + 提草稿 PR」交付层）

对齐竞品（GitHub Copilot Autofix / Snyk Agent Fix）的交付方式：
  - 只提「草稿 PR」（draft），绝不自动 merge，人 review 后才合并
  - 建独立分支（xinpect-fix-<check_id>-<short_hash>），不碰用户默认分支
  - 补丁以单文件提交，PR 描述带「修复了什么 + 为什么 + 回验结果」

复用现有 GitHub OAuth（modules/github_oauth.py）：
  - get_user_github_token() / _github_api()
GitLab 对称实现，token 存 users.gitlab_token。

安全红线：
  - 绝不写用户默认分支
  - 绝不自动 merge
  - token 只在服务端用，永不回传前端
"""
import os
import json
import hashlib
import urllib.request
import urllib.error
from typing import Optional, Dict

GIT_TIMEOUT_SECONDS = 20

# ---------------------------------------------------------------------------
# GitHub 访问走 SOCKS5 代理（国内服务器直连 github.com 超时，经硅谷跳板转发）
# ---------------------------------------------------------------------------
_GITHUB_PROXY = os.environ.get("GITHUB_PROXY", "http://127.0.0.1:18118")
_git_opener = None


def _get_git_opener():
    """返回带 SOCKS5 代理的 opener（惰性构建，进程内复用）。"""
    global _git_opener
    if _git_opener is None:
        if _GITHUB_PROXY:
            import socks
            from urllib.request import ProxyHandler, build_opener
            proxy_handler = ProxyHandler({
                "http": _GITHUB_PROXY,
                "https": _GITHUB_PROXY,
            })
            _git_opener = build_opener(proxy_handler)
        else:
            _git_opener = urllib.request.build_opener()
    return _git_opener



GITLAB_API_BASE = "https://gitlab.com/api/v4"
GITLAB_CLIENT_ID = os.environ.get("GITLAB_CLIENT_ID", "")
GITLAB_CLIENT_SECRET = os.environ.get("GITLAB_CLIENT_SECRET", "")
GITLAB_REDIRECT_URI = os.environ.get(
    "GITLAB_REDIRECT_URI",
    "https://xinpect.xingwangzhineng.com/api/gitlab/callback",
)


# ---------------------------------------------------------------------------
# 底层 API 调用
# ---------------------------------------------------------------------------
def _http_json(url, method="GET", data=None, token=None, extra_headers=None):
    """通用 HTTP JSON 调用（urllib，避免额外依赖）。"""
    headers = {
        "Accept": "application/json",
        "User-Agent": "Xinpect/2.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if extra_headers:
        headers.update(extra_headers)

    body = json.dumps(data).encode() if data is not None else None
    if body is not None:
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with _get_git_opener().open(req, timeout=GIT_TIMEOUT_SECONDS) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            detail = json.loads(raw) if raw else {}
        except Exception:
            detail = {"message": raw.decode("utf-8", "ignore")[:200]}
        return e.code, detail


def _github_api(token, url, method="GET", data=None):
    """复用 github_oauth 的 _github_api，但这里自实现以支持 PUT/PATCH 等。"""
    return _http_json(url, method=method, data=data, token=token,
                      extra_headers={"Authorization": f"token {token}"})


def _gitlab_api(token, path, method="GET", data=None):
    """调用 GitLab API。"""
    url = f"{GITLAB_API_BASE}{path}"
    return _http_json(url, method=method, data=data, token=token)


# ---------------------------------------------------------------------------
# Token 存取
# ---------------------------------------------------------------------------
def get_user_git_token(user_id: int, platform: str) -> Optional[str]:
    """获取用户某平台的 token。platform: github | gitlab。"""
    from modules.db import get_db
    db = get_db()
    col = "github_token" if platform == "github" else "gitlab_token"
    row = db.execute(
        f"SELECT {col} FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    return row[0] if row and row[0] else None


# ---------------------------------------------------------------------------
# 建分支 + 提草稿 PR
# ---------------------------------------------------------------------------
def create_fix_pr(
    user_id: int,
    platform: str,
    repo_full_name: str,
    file_path: str,
    new_file_content: str,
    old_file_content: str,
    check_id: str,
    explanation: str,
    verified: bool,
) -> Dict:
    """为一键修复创建分支 + 草稿 PR。

    Returns:
        {"ok": bool, "pr_url": str, "branch": str, "error": str}
    """
    token = get_user_git_token(user_id, platform)
    if not token:
        return {"ok": False, "error": f"未连接 {platform}，请先授权"}

    if platform == "github":
        return _create_github_pr(token, repo_full_name, file_path,
                                 new_file_content, check_id, explanation, verified)
    elif platform == "gitlab":
        return _create_gitlab_pr(token, repo_full_name, file_path,
                                 new_file_content, check_id, explanation, verified)
    return {"ok": False, "error": f"不支持的平台: {platform}"}


def _branch_name(check_id: str) -> str:
    """生成安全的分支名。"""
    clean = "".join(c if c.isalnum() else "-" for c in check_id).strip("-")[:20]
    h = hashlib.sha1(f"{check_id}-{os.urandom(8).hex()}".encode()).hexdigest()[:6]
    return f"xinpect-fix-{clean}-{h}" if clean else f"xinpect-fix-{h}"


def _create_github_pr(token, repo_full_name, file_path, new_content,
                      check_id, explanation, verified) -> Dict:
    """GitHub: 建分支 → 提交文件 → 提草稿 PR。"""
    # 1. 获取默认分支
    status, repo = _github_api(token, f"https://api.github.com/repos/{repo_full_name}")
    if status != 200:
        return {"ok": False, "error": f"获取仓库失败: {repo.get('message', status)}"}
    default_branch = repo.get("default_branch", "main")

    # 2. 获取默认分支最新 commit SHA（作为新分支 base）
    status, branch_info = _github_api(
        token, f"https://api.github.com/repos/{repo_full_name}/git/ref/heads/{default_branch}")
    if status != 200:
        return {"ok": False, "error": f"获取分支失败: {branch_info.get('message', status)}"}
    base_sha = branch_info["object"]["sha"]

    # 3. 建新分支
    branch = _branch_name(check_id)
    status, ref = _github_api(
        token,
        f"https://api.github.com/repos/{repo_full_name}/git/refs",
        method="POST",
        data={"ref": f"refs/heads/{branch}", "sha": base_sha},
    )
    if status not in (201, 422):
        return {"ok": False, "error": f"建分支失败: {ref.get('message', status)}"}

    # 4. 提交文件（先查文件 blob sha，存在则带上做更新，否则新建）
    status, existing = _github_api(
        token,
        f"https://api.github.com/repos/{repo_full_name}/contents/{file_path}?ref={branch}",
    )
    blob_sha = existing.get("sha", "") if status == 200 else ""

    commit_data = {
        "message": f"fix: 修复 {check_id}（煋鉴一键修复）",
        "content": _b64(new_content),
        "branch": branch,
    }
    if blob_sha:
        commit_data["sha"] = blob_sha

    status, commit_resp = _github_api(
        token,
        f"https://api.github.com/repos/{repo_full_name}/contents/{file_path}",
        method="PUT",
        data=commit_data,
    )
    if status not in (200, 201):
        return {"ok": False, "error": f"提交文件失败: {commit_resp.get('message', status)}"}

    # 5. 提草稿 PR
    body = _pr_body(check_id, explanation, verified, file_path)
    status, pr = _github_api(
        token,
        f"https://api.github.com/repos/{repo_full_name}/pulls",
        method="POST",
        data={
            "title": f"fix: 修复 {check_id}（煋鉴一键修复）",
            "head": branch,
            "base": default_branch,
            "body": body,
            "draft": True,
        },
    )
    if status not in (200, 201):
        return {"ok": False, "error": f"提 PR 失败: {pr.get('message', status)}"}

    return {"ok": True, "pr_url": pr.get("html_url", ""), "branch": branch}


def _create_gitlab_pr(token, repo_full_name, file_path, new_content,
                      check_id, explanation, verified) -> Dict:
    """GitLab: 建分支 → 提交文件 → 提 MR（draft）。"""
    # GitLab 项目路径需 URL 编码
    import urllib.parse
    project_path = urllib.parse.quote(repo_full_name, safe="")

    # 1. 获取项目默认分支
    status, project = _gitlab_api(token, f"/projects/{project_path}")
    if status != 200:
        return {"ok": False, "error": f"获取项目失败: {project.get('message', status)}"}
    default_branch = project.get("default_branch", "main")
    project_id = project["id"]

    # 2. 建分支
    branch = _branch_name(check_id)
    status, br = _gitlab_api(
        token,
        f"/projects/{project_id}/repository/branches",
        method="POST",
        data={"branch": branch, "ref": default_branch},
    )
    if status not in (200, 201, 400):
        return {"ok": False, "error": f"建分支失败: {br.get('message', status)}"}

    # 3. 提交文件
    import urllib.parse as up
    fpath_enc = up.quote(file_path, safe="")
    commit_data = {
        "branch": branch,
        "commit_message": f"fix: 修复 {check_id}（煋鉴一键修复）",
        "content": new_content,
        "actions": [{
            "action": "update",
            "file_path": file_path,
            "content": new_content,
        }],
    }
    status, commit_resp = _gitlab_api(
        token,
        f"/projects/{project_id}/repository/commits",
        method="POST",
        data=commit_data,
    )
    if status not in (200, 201):
        return {"ok": False, "error": f"提交文件失败: {commit_resp.get('message', status)}"}

    # 4. 提 MR（draft）
    body = _pr_body(check_id, explanation, verified, file_path)
    status, mr = _gitlab_api(
        token,
        f"/projects/{project_id}/merge_requests",
        method="POST",
        data={
            "source_branch": branch,
            "target_branch": default_branch,
            "title": f"fix: 修复 {check_id}（煋鉴一键修复）",
            "description": body,
        },
    )
    if status not in (200, 201):
        return {"ok": False, "error": f"提 MR 失败: {mr.get('message', status)}"}

    # GitLab draft 通过 title 前缀 Draft: 表示
    if mr.get("iid"):
        draft_title = f"Draft: fix: 修复 {check_id}（煋鉴一键修复）"
        _gitlab_api(
            token,
            f"/projects/{project_id}/merge_requests/{mr['iid']}",
            method="PUT",
            data={"title": draft_title},
        )
        mr["title"] = draft_title

    return {"ok": True, "pr_url": mr.get("web_url", ""), "branch": branch}


def _pr_body(check_id, explanation, verified, file_path) -> str:
    """PR/MR 描述正文。"""
    verify_line = "✅ 已通过煋鉴回验（重扫确认漏洞已关闭）" if verified else "⚠️ 未通过回验，请人工复核"
    return (
        f"## 煋鉴一键修复\n\n"
        f"- **漏洞规则**: `{check_id}`\n"
        f"- **修复文件**: `{file_path}`\n"
        f"- **修复说明**: {explanation}\n"
        f"- **验证状态**: {verify_line}\n\n"
        f"> 此 PR 由煋鉴（Xinpect）自动生成，为草稿状态，请 review 后合并。\n"
    )


def _b64(text: str) -> str:
    import base64
    return base64.b64encode(text.encode("utf-8")).decode("utf-8")


# ---------------------------------------------------------------------------
# GitLab OAuth（对称 github_oauth）
# ---------------------------------------------------------------------------
def gitlab_authorize_url(state: str) -> str:
    return (
        f"https://gitlab.com/oauth/authorize"
        f"?client_id={GITLAB_CLIENT_ID}"
        f"&redirect_uri={GITLAB_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=api+write_repository"
        f"&state={state}"
    )


def gitlab_exchange_token(code: str) -> str:
    """用 code 换 GitLab access_token。"""
    status, data = _http_json(
        "https://gitlab.com/oauth/token",
        method="POST",
        data={
            "client_id": GITLAB_CLIENT_ID,
            "client_secret": GITLAB_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": GITLAB_REDIRECT_URI,
        },
    )
    if status != 200:
        raise ValueError(f"GitLab token 交换失败: {data}")
    return data.get("access_token", "")


# ---------------------------------------------------------------------------
# GitLab OAuth blueprint（对称 github_oauth.py 的 authorize/callback/disconnect）
# ---------------------------------------------------------------------------
from flask import Blueprint, request, redirect, jsonify, session, url_for, flash
from functools import wraps

gitlab_bp = Blueprint("gitlab_oauth", __name__)

GITLAB_AUTH_URL = "https://gitlab.com/oauth/authorize"


def _login_required_api(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            return jsonify(status="error", message="请先登录"), 401
        return f(*args, **kwargs)
    return decorated


@gitlab_bp.route("/api/gitlab/authorize")
@_login_required_api
def gitlab_authorize():
    """重定向到 GitLab OAuth 授权页。"""
    if not GITLAB_CLIENT_ID:
        return jsonify(status="error", message="GitLab OAuth 未配置"), 500

    import secrets
    state = secrets.token_urlsafe(16)
    session["gitlab_oauth_state"] = state

    params = (
        f"client_id={GITLAB_CLIENT_ID}"
        f"&redirect_uri={GITLAB_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=api+write_repository"
        f"&state={state}"
    )
    return redirect(f"{GITLAB_AUTH_URL}?{params}")


@gitlab_bp.route("/api/gitlab/callback")
def gitlab_callback():
    """处理 GitLab OAuth 回调。"""
    code = request.args.get("code", "")
    state = request.args.get("state", "")

    expected_state = session.pop("gitlab_oauth_state", "")
    if not state or state != expected_state:
        flash("GitLab 授权失败：state 验证不通过", "error")
        return redirect(url_for("dashboard_page"))

    if not code:
        flash("GitLab 授权失败：未收到授权码", "error")
        return redirect(url_for("dashboard_page"))

    try:
        access_token = gitlab_exchange_token(code)
        if not access_token:
            raise ValueError("未获取到 access_token")

        # 获取 GitLab 用户信息
        status, gl_user = _gitlab_api(access_token, "/user")
        if status != 200:
            raise ValueError(f"获取 GitLab 用户失败: {gl_user}")
        gitlab_username = gl_user.get("username", "")

        from modules.db import get_db
        db = get_db()
        user_id = session.get("user_id")
        db.execute(
            "UPDATE users SET gitlab_token = ?, gitlab_username = ? WHERE id = ?",
            (access_token, gitlab_username, user_id),
        )
        db.commit()

        flash(f"✅ GitLab 授权成功！已连接 @{gitlab_username}", "success")
        return redirect(url_for("dashboard_page"))

    except Exception as e:
        flash(f"GitLab 授权失败：{e}", "error")
        return redirect(url_for("dashboard_page"))


@gitlab_bp.route("/api/gitlab/disconnect", methods=["POST"])
@_login_required_api
def gitlab_disconnect():
    """断开 GitLab 连接。"""
    from modules.db import get_db
    db = get_db()
    user_id = session.get("user_id")
    db.execute(
        "UPDATE users SET gitlab_token = NULL, gitlab_username = NULL WHERE id = ?",
        (user_id,),
    )
    db.commit()
    return jsonify(status="ok", message="已断开 GitLab")


@gitlab_bp.route("/api/gitlab/status")
@_login_required_api
def gitlab_status():
    """返回 GitLab 连接状态。"""
    from modules.db import get_db
    db = get_db()
    user_id = session.get("user_id")
    row = db.execute(
        "SELECT gitlab_username FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    connected = bool(row and row["gitlab_username"])
    return jsonify(status="ok", connected=connected,
                   username=row["gitlab_username"] if row else None)
