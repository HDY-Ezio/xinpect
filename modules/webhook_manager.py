"""
GitHub Webhook 自动扫描模块
- 管理仓库 webhook 的启用/禁用/列表
- 接收 GitHub push/pull_request 事件，异步触发扫描
- webhook 接收端使用 HMAC-SHA256 签名验证，无需 session 认证

依赖：
- modules/github_oauth.py  → get_user_github_token(), _github_api()
- modules/ci.py            → api_scan_github 相关逻辑

部署后在 app.py 中注册：
    from modules.webhook_manager import webhook_bp, init_webhook_tables
    app.register_blueprint(webhook_bp)
    init_webhook_tables()  # 在 app 启动时调用
"""

import hashlib
import hmac
import json
import logging
import os
import secrets
import sqlite3
import threading
import urllib.request
import urllib.error
from datetime import datetime
from functools import wraps

from flask import Blueprint, request, jsonify, session

logger = logging.getLogger(__name__)

# ============================================================
# Blueprint
# ============================================================
webhook_bp = Blueprint("webhook_manager", __name__)

# 数据库路径（与 app.py 一致）
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "xinpect.db")

# 正在扫描中的 repo+branch 集合（防重复扫描），key = "repo_full_name:branch_or_pr"
_scanning_locks = {}
_scanning_locks_mutex = threading.Lock()

# Webhook 回调地址（GitHub 注册时用）
WEBHOOK_CALLBACK_URL = "https://xinpect.xingwangzhineng.com/api/webhook/github"


# ============================================================
# 数据库初始化
# ============================================================
def init_webhook_tables():
    """创建 webhook 相关表，在 app 启动时调用"""
    try:
        db = sqlite3.connect(DB_PATH)
        db.execute("""
            CREATE TABLE IF NOT EXISTS repo_webhooks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                repo_full_name TEXT NOT NULL,
                github_webhook_id INTEGER,
                secret TEXT NOT NULL,
                events TEXT NOT NULL DEFAULT 'push,pull_request',
                active INTEGER NOT NULL DEFAULT 1,
                auto_scan INTEGER NOT NULL DEFAULT 1,
                auto_pr_comment INTEGER NOT NULL DEFAULT 1,
                last_scan_at TEXT,
                scan_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS idx_repo_webhooks_user ON repo_webhooks(user_id)")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_repo_webhooks_repo ON repo_webhooks(repo_full_name)")
        db.commit()
        db.close()
        logger.info("[webhook] repo_webhooks 表初始化完成")
    except Exception as e:
        logger.error("[webhook] 初始化表失败: %s", e)


# ============================================================
# 工具函数
# ============================================================
def _get_db():
    """获取数据库连接（独立连接，不复用 app 的 get_db 避免冲突）"""
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def _require_login(f):
    """登录校验装饰器"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "未登录，请先登录"}), 401
        return f(*args, **kwargs)
    return wrapper


def _github_api_call(url, token, method="GET", data=None):
    """
    调用 GitHub API。
    优先复用 github_oauth 模块的 _github_api，失败则降级为 urllib。
    """
    try:
        from modules.github_oauth import _github_api
        return _github_api(url, token, method=method, data=data)
    except (ImportError, Exception):
        return _github_api_urllib(url, token, method, data)


def _github_api_urllib(url, token, method="GET", data=None):
    """GitHub API 调用的 urllib 实现（降级方案）"""
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Xinpect-Webhook/1.0",
    }
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp_body = resp.read().decode("utf-8")
            if resp_body:
                return json.loads(resp_body)
            return {"status": resp.status}
    except urllib.error.HTTPError as e:
        resp_body = e.read().decode("utf-8", errors="replace")
        logger.error("[webhook] GitHub API 错误 %s: %s %s", e.code, url, resp_body[:300])
        return {"_error": True, "status": e.code, "message": resp_body[:300]}
    except Exception as e:
        logger.error("[webhook] GitHub API 异常: %s %s", url, e)
        return {"_error": True, "message": str(e)}


def _verify_webhook_signature(payload_body, signature_header, secret):
    """
    验证 GitHub Webhook 签名（HMAC-SHA256）。
    signature_header 格式: sha256=<hex_digest>
    返回 True 表示签名合法。
    """
    if not signature_header:
        return False
    if not signature_header.startswith("sha256="):
        return False

    expected_sig = signature_header.split("=", 1)[1]
    computed = hmac.new(secret.encode("utf-8"), payload_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, expected_sig)


def _get_user_github_token(user_id):
    """获取用户的 GitHub token"""
    try:
        from modules.github_oauth import get_user_github_token
        return get_user_github_token(user_id)
    except ImportError:
        db = sqlite3.connect(DB_PATH)
        row = db.execute("SELECT github_token FROM users WHERE id = ?", (user_id,)).fetchone()
        db.close()
        return row[0] if row else None


# ============================================================
# API: 启用仓库自动扫描
# ============================================================
@webhook_bp.route("/api/repos/enable", methods=["POST"])
@_require_login
def enable_repo():
    """
    启用仓库自动扫描。
    入参: {"repo_full_name": "owner/repo"}
    逻辑:
    1. 验证用户已连接 GitHub
    2. 生成 webhook secret
    3. 调用 GitHub API 创建 webhook
    4. 保存 github_webhook_id 到 repo_webhooks 表
    """
    user_id = session.get("user_id")
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "缺少请求体"}), 400

    repo_full_name = data.get("repo_full_name", "").strip()
    if not repo_full_name or "/" not in repo_full_name:
        return jsonify({"error": "repo_full_name 格式错误，应为 owner/repo"}), 400

    # 检查用户是否已连接 GitHub
    github_token = _get_user_github_token(user_id)
    if not github_token:
        return jsonify({"error": "未连接 GitHub，请先授权"}), 400

    db = _get_db()
    try:
        # 检查是否已经启用
        existing = db.execute(
            "SELECT id FROM repo_webhooks WHERE repo_full_name = ?",
            (repo_full_name,),
        ).fetchone()
        if existing:
            return jsonify({"error": "该仓库已启用自动扫描", "webhook_id": existing["id"]}), 409

        # 生成 webhook secret
        secret = secrets.token_hex(32)

        # 调用 GitHub API 创建 webhook
        owner, repo = repo_full_name.split("/", 1)
        api_url = f"https://api.github.com/repos/{owner}/{repo}/hooks"
        hook_config = {
            "name": "web",
            "active": True,
            "events": ["push", "pull_request"],
            "config": {
                "url": WEBHOOK_CALLBACK_URL,
                "content_type": "json",
                "secret": secret,
                "insecure_ssl": "0",
            },
        }

        result = _github_api_call(api_url, github_token, method="POST", data=hook_config)

        # 处理 GitHub API 错误
        if isinstance(result, dict) and result.get("_error"):
            status_code = result.get("status", 500)
            if status_code == 401:
                return jsonify({"error": "GitHub Token 已过期，请重新授权"}), 401
            elif status_code == 404:
                return jsonify({"error": "仓库不存在或无权访问"}), 404
            elif status_code == 422:
                return jsonify({"error": "Webhook 已存在或参数错误"}), 422
            else:
                return jsonify({"error": f"GitHub API 错误: {result.get('message', '未知错误')}"}), 502

        # 提取 GitHub 返回的 webhook id
        github_webhook_id = result.get("id") if isinstance(result, dict) else None

        # 保存到数据库
        cursor = db.execute(
            """INSERT INTO repo_webhooks
               (user_id, repo_full_name, github_webhook_id, secret, events, active, auto_scan, auto_pr_comment)
               VALUES (?, ?, ?, ?, 'push,pull_request', 1, 1, 1)""",
            (user_id, repo_full_name, github_webhook_id, secret),
        )
        db.commit()
        webhook_id = cursor.lastrowid

        logger.info("[webhook] 用户 %s 启用仓库 %s, webhook_id=%s", user_id, repo_full_name, webhook_id)
        return jsonify({
            "status": "ok",
            "webhook_id": webhook_id,
            "repo": repo_full_name,
            "github_webhook_id": github_webhook_id,
            "message": f"已启用 {repo_full_name} 的自动扫描",
        })

    finally:
        db.close()


# ============================================================
# API: 禁用仓库
# ============================================================
@webhook_bp.route("/api/repos/<int:webhook_id>/disable", methods=["POST"])
@_require_login
def disable_repo(webhook_id):
    """
    禁用仓库自动扫描。
    删除 GitHub webhook + 删除 repo_webhooks 记录。
    """
    user_id = session.get("user_id")
    db = _get_db()
    try:
        row = db.execute(
            "SELECT * FROM repo_webhooks WHERE id = ? AND user_id = ?",
            (webhook_id, user_id),
        ).fetchone()
        if not row:
            return jsonify({"error": "记录不存在或无权操作"}), 404

        repo_full_name = row["repo_full_name"]
        gh_webhook_id = row["github_webhook_id"]

        # 删除 GitHub webhook（尽力而为，失败不阻塞）
        github_token = _get_user_github_token(user_id)
        if github_token and gh_webhook_id:
            owner, repo = repo_full_name.split("/", 1)
            del_url = f"https://api.github.com/repos/{owner}/{repo}/hooks/{gh_webhook_id}"
            result = _github_api_call(del_url, github_token, method="DELETE")
            if isinstance(result, dict) and result.get("_error"):
                logger.warning("[webhook] 删除 GitHub webhook 失败: %s", result.get("message"))

        # 删除本地记录
        db.execute("DELETE FROM repo_webhooks WHERE id = ? AND user_id = ?", (webhook_id, user_id))
        db.commit()

        logger.info("[webhook] 用户 %s 禁用仓库 %s", user_id, repo_full_name)
        return jsonify({"status": "ok", "message": f"已禁用 {repo_full_name} 的自动扫描"})

    finally:
        db.close()


# ============================================================
# API: 列出已启用的仓库
# ============================================================
@webhook_bp.route("/api/repos/list", methods=["GET"])
@_require_login
def list_repos():
    """列出当前用户已启用的仓库"""
    user_id = session.get("user_id")
    db = _get_db()
    try:
        rows = db.execute(
            """SELECT id, repo_full_name, events, active, auto_scan, auto_pr_comment,
                      last_scan_at, scan_count, created_at
               FROM repo_webhooks
               WHERE user_id = ?
               ORDER BY created_at DESC""",
            (user_id,),
        ).fetchall()

        repos = []
        for row in rows:
            repos.append({
                "id": row["id"],
                "repo_full_name": row["repo_full_name"],
                "events": row["events"].split(",") if row["events"] else [],
                "active": bool(row["active"]),
                "auto_scan": bool(row["auto_scan"]),
                "auto_pr_comment": bool(row["auto_pr_comment"]),
                "last_scan_at": row["last_scan_at"],
                "scan_count": row["scan_count"] or 0,
                "created_at": row["created_at"],
            })

        return jsonify({"status": "ok", "repos": repos})
    finally:
        db.close()


# ============================================================
# API: 仓库统计
# ============================================================
@webhook_bp.route("/api/repos/stats", methods=["GET"])
@_require_login
def repo_stats():
    """仓库统计：扫描次数、最后扫描时间"""
    user_id = session.get("user_id")
    db = _get_db()
    try:
        rows = db.execute(
            """SELECT id, repo_full_name, scan_count, last_scan_at, created_at
               FROM repo_webhooks
               WHERE user_id = ?
               ORDER BY scan_count DESC""",
            (user_id,),
        ).fetchall()

        stats = []
        for row in rows:
            stats.append({
                "id": row["id"],
                "repo_full_name": row["repo_full_name"],
                "scan_count": row["scan_count"] or 0,
                "last_scan_at": row["last_scan_at"],
                "created_at": row["created_at"],
            })

        return jsonify({"status": "ok", "stats": stats})
    finally:
        db.close()


# ============================================================
# Webhook 接收端（无需 session，签名验证）
# ============================================================
@webhook_bp.route("/api/webhook/github", methods=["POST"])
def receive_github_webhook():
    """
    接收 GitHub Webhook 事件。
    - ping: 直接返回 200
    - push: 验证签名后异步触发扫描
    - pull_request: 验证签名后异步触发扫描+PR评论
    关键：必须在 10 秒内返回 200（GitHub 要求），扫描放后台线程。
    """
    # 读取原始 body（用于签名验证）
    payload_body = request.get_data()
    signature = request.headers.get("X-Hub-Signature-256", "")
    event_type = request.headers.get("X-GitHub-Event", "")
    delivery_id = request.headers.get("X-GitHub-Delivery", "")

    # 解析 JSON payload
    try:
        payload = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "invalid payload"}), 400

    # ---- ping 事件 ----
    if event_type == "ping":
        logger.info("[webhook] ping 事件, delivery=%s", delivery_id)
        return jsonify({"status": "ok", "message": "pong"}), 200

    # ---- 提取仓库名 ----
    repo_data = payload.get("repository", {})
    repo_full_name = repo_data.get("full_name", "")
    if not repo_full_name:
        logger.warning("[webhook] 缺少 repository.full_name, delivery=%s", delivery_id)
        return jsonify({"error": "missing repo"}), 400

    # ---- 查 webhook 配置 ----
    db = _get_db()
    try:
        row = db.execute(
            "SELECT * FROM repo_webhooks WHERE repo_full_name = ? AND active = 1",
            (repo_full_name,),
        ).fetchone()
    finally:
        db.close()

    if not row:
        logger.warning("[webhook] 仓库 %s 未注册, delivery=%s", repo_full_name, delivery_id)
        return jsonify({"status": "ignored", "reason": "repo not registered"}), 200

    webhook_config = dict(row)
    secret = webhook_config["secret"]

    # ---- 签名验证 ----
    if not _verify_webhook_signature(payload_body, signature, secret):
        logger.warning("[webhook] 签名验证失败, repo=%s, delivery=%s", repo_full_name, delivery_id)
        return jsonify({"error": "invalid signature"}), 403

    # ---- 分发事件 ----
    if event_type == "push":
        if webhook_config.get("auto_scan"):
            _handle_push_event(payload, webhook_config, delivery_id)
        return jsonify({"status": "ok", "message": "push received"}), 200

    elif event_type == "pull_request":
        action = payload.get("action", "")
        if action in ("opened", "synchronize") and webhook_config.get("auto_pr_comment"):
            _handle_pr_event(payload, webhook_config, delivery_id)
        return jsonify({"status": "ok", "message": f"pr {action} received"}), 200

    else:
        logger.info("[webhook] 忽略事件: %s, repo=%s", event_type, repo_full_name)
        return jsonify({"status": "ok", "message": "event ignored"}), 200


# ============================================================
# 事件处理（异步线程）
# ============================================================

def _handle_push_event(payload, webhook_config, delivery_id):
    """处理 push 事件：提取信息，异步扫描"""
    repo_full_name = webhook_config["repo_full_name"]
    user_id = webhook_config["user_id"]
    webhook_id = webhook_config["id"]

    # 提取 branch: refs/heads/main → main
    ref = payload.get("ref", "")
    branch = ref.replace("refs/heads/", "") if ref.startswith("refs/heads/") else ref

    # 提取 commit sha
    head_commit = payload.get("head_commit") or {}
    commit_sha = head_commit.get("id", "") or payload.get("after", "")

    # 提取变更文件列表（去重）
    changed_files = set()
    for commit in payload.get("commits", []):
        changed_files.update(commit.get("added", []))
        changed_files.update(commit.get("modified", []))
        changed_files.update(commit.get("removed", []))

    # 防重复扫描
    lock_key = f"{repo_full_name}:{branch}"
    with _scanning_locks_mutex:
        if _scanning_locks.get(lock_key):
            logger.info("[webhook] %s %s 正在扫描中，跳过", repo_full_name, branch)
            return
        _scanning_locks[lock_key] = True

    logger.info(
        "[webhook] push 触发扫描: %s branch=%s sha=%s files=%d delivery=%s",
        repo_full_name, branch, commit_sha[:8], len(changed_files), delivery_id,
    )

    t = threading.Thread(
        target=_run_scan_worker,
        args=(user_id, webhook_id, repo_full_name, branch, commit_sha,
              list(changed_files), None, False),
        daemon=True,
    )
    t.start()


def _handle_pr_event(payload, webhook_config, delivery_id):
    """处理 pull_request 事件：提取信息，异步扫描+评论"""
    repo_full_name = webhook_config["repo_full_name"]
    user_id = webhook_config["user_id"]
    webhook_id = webhook_config["id"]

    pr = payload.get("pull_request", {})
    pr_number = pr.get("number")
    branch = pr.get("head", {}).get("ref", "")
    commit_sha = pr.get("head", {}).get("sha", "")

    # 防重复
    lock_key = f"{repo_full_name}:pr-{pr_number}"
    with _scanning_locks_mutex:
        if _scanning_locks.get(lock_key):
            logger.info("[webhook] PR #%s 正在扫描中，跳过", pr_number)
            return
        _scanning_locks[lock_key] = True

    logger.info(
        "[webhook] PR 触发扫描: %s PR=#%s branch=%s delivery=%s",
        repo_full_name, pr_number, branch, delivery_id,
    )

    t = threading.Thread(
        target=_run_scan_worker,
        args=(user_id, webhook_id, repo_full_name, branch, commit_sha,
              [], pr_number, True),
        daemon=True,
    )
    t.start()


def _run_scan_worker(user_id, webhook_id, repo_full_name, branch, commit_sha,
                     changed_files, pr_number, post_pr_comment):
    """
    后台扫描工作线程（daemon=True）。
    异常安全：任何异常都会被捕获并记录，不会导致线程泄漏。
    """
    lock_key = f"{repo_full_name}:{'pr-' + str(pr_number) if pr_number else branch}"
    try:
        _do_scan(user_id, webhook_id, repo_full_name, branch, commit_sha,
                 changed_files, pr_number, post_pr_comment)
    except Exception as e:
        logger.error("[webhook] 扫描异常: %s %s, error=%s", repo_full_name, branch, e, exc_info=True)
    finally:
        with _scanning_locks_mutex:
            _scanning_locks.pop(lock_key, None)


def _do_scan(user_id, webhook_id, repo_full_name, branch, commit_sha,
             changed_files, pr_number, post_pr_comment):
    """
    执行扫描逻辑，复用 ci.py 的能力。
    流程：clone → 扫描 → 保存结果 → (PR 时)发评论 → 更新统计。
    """
    repo_url = f"https://github.com/{repo_full_name}.git"
    logger.info("[webhook] 开始扫描: %s (branch=%s)", repo_full_name, branch)

    github_token = _get_user_github_token(user_id)

    # 复用 ci.py 的扫描函数
    try:
        from modules.ci import (
            api_scan_github,
            _post_github_pr_comment,
            _build_pr_comment_body,
        )

        scan_result = api_scan_github(
            repo_url=repo_url,
            user_id=user_id,
            github_token=github_token,
            branch=branch,
            is_ci=True,
        )

        if scan_result and isinstance(scan_result, dict):
            scan_id = scan_result.get("scan_id") or scan_result.get("id")
            findings = scan_result.get("findings", [])
            logger.info(
                "[webhook] 扫描完成: %s scan_id=%s issues=%d",
                repo_full_name, scan_id, len(findings),
            )

            # PR 评论
            if post_pr_comment and pr_number and github_token:
                owner, repo = repo_full_name.split("/", 1)
                try:
                    comment_body = _build_pr_comment_body(
                        repo_full_name=repo_full_name,
                        branch=branch,
                        commit_sha=commit_sha,
                        findings=findings,
                        scan_id=scan_id,
                    )
                    _post_github_pr_comment(github_token, owner, repo, pr_number, comment_body)
                    logger.info("[webhook] PR #%s 评论已发送: %s", pr_number, repo_full_name)
                except Exception as e:
                    logger.error("[webhook] PR 评论发送失败: %s", e)
        else:
            logger.warning("[webhook] 扫描返回空结果: %s", repo_full_name)

    except ImportError:
        logger.error("[webhook] ci.py 模块不可用")
    except Exception as e:
        logger.error("[webhook] 调用扫描失败: %s", e, exc_info=True)

    # 更新扫描统计
    try:
        db = sqlite3.connect(DB_PATH)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.execute(
            "UPDATE repo_webhooks SET scan_count = COALESCE(scan_count, 0) + 1, last_scan_at = ? WHERE id = ?",
            (now, webhook_id),
        )
        db.commit()
        db.close()
    except Exception as e:
        logger.error("[webhook] 更新统计失败: %s", e)
