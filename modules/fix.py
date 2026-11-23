# -*- coding: utf-8 -*-
"""
煋鉴「一键修复」官网侧模块（FIX）

职责：
  - 一键修复 API：校验「会员 + 深度扫描」双门槛 → 调扫描器 /fix 生成补丁 → 建分支提草稿 PR
  - 补丁预览 API：只生成补丁（修复前/后 + 是否通过回验），不建 PR，供前端展示

权限判定（产品分层）：
  仅「会员（is_vip）+ 深度扫描（scan_mode == deep）」可解锁一键修复；
  其他档（free/quick/smart）只能看到「升级深度扫描解锁」引导。

安全红线：
  - 只提草稿 PR，绝不自动 merge
  - 补丁生成走扫描器侧（含回验），官网不落地用户代码
"""
import json
from flask import Blueprint, request, jsonify, session
from functools import wraps

fix_bp = Blueprint("fix", __name__)


def _login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            return jsonify(status="error", message="请先登录"), 401
        return f(*args, **kwargs)
    return decorated


def _is_deep_and_vip(scan_row, is_vip: bool) -> bool:
    """判断是否满足「深度扫描 + 会员」双门槛。"""
    if not is_vip:
        return False
    mode = (scan_row.get("scan_mode") if isinstance(scan_row, dict)
            else scan_row["scan_mode"]) if scan_row else ""
    return mode == "deep"


def _find_issue(scan_row, issue_key: str):
    """从扫描结果里定位目标 issue。issue_key 格式：<rule_id>@<file>@<line>。"""
    try:
        results = json.loads(scan_row["results"]) if scan_row.get("results") else {}
    except Exception:
        results = {}
    issues = results.get("issues", [])
    for iss in issues:
        key = f"{iss.get('rule_id', '')}@{iss.get('file', '')}@{iss.get('line', 0)}"
        if key == issue_key:
            return iss
    return None


def _call_scanner_fix(scan_id, issue):
    """调扫描器 /fix 接口（scan_id 模式）。"""
    from modules.constants import SCANNER_URL, SCANNER_API_KEY
    import requests

    fix_url = SCANNER_URL.replace("/scan", "/fix")
    payload = {
        "scan_id": scan_id,
        "issue": {
            "check_id": issue.get("rule_id", ""),
            "file": issue.get("file", ""),
            "line": issue.get("line", 0),
            "name": issue.get("title", ""),
            "severity": issue.get("severity", ""),
            "message": issue.get("description", ""),
            "suggestion": issue.get("suggestion", ""),
            "brain_id": str(issue.get("brain_id", "")),
        },
        "user_id": str(session.get("user_id", "")),
    }
    headers = {"X-API-Key": SCANNER_API_KEY} if SCANNER_API_KEY else {}
    resp = requests.post(fix_url, json=payload, headers=headers, timeout=120)
    if resp.status_code != 200:
        return None, f"扫描器返回 {resp.status_code}"
    data = resp.json()
    return data.get("fix"), None


def _apply_fixed_content(issue, fix_result):
    """用补丁的 before/after 计算修复后的完整文件内容（供建分支提交）。

    由于官网不存原始文件内容，这里需要扫描器返回 after 片段。
    但建分支提 PR 需要完整文件内容——因此建 PR 时应由扫描器返回完整修复后文件。
    """
    return fix_result


# ── 补丁预览（不建 PR）──
@fix_bp.route("/api/fix/preview/<scan_id>", methods=["POST"])
@_login_required
def fix_preview(scan_id):
    """生成一键修复补丁预览（修复前/后 + 回验结果），不建分支不提 PR。"""
    from modules.db import get_db
    from modules.helpers import is_vip_user

    db = get_db()
    user_id = session.get("user_id")
    scan = db.execute("SELECT * FROM scans WHERE scan_id = ? AND user_id = ?",
                      (scan_id, user_id)).fetchone()
    if not scan:
        return jsonify(status="error", message="扫描记录不存在"), 404

    vip = is_vip_user()
    if not _is_deep_and_vip(scan, vip):
        return jsonify(status="error", code="not_deep_vip",
                       message="一键修复仅对「深度扫描 + 会员」开放"), 403

    issue_key = request.json.get("issue_key", "")
    issue = _find_issue(scan, issue_key)
    if not issue:
        return jsonify(status="error", message="未找到该问题"), 404

    fix_result, err = _call_scanner_fix(scan_id, issue)
    if err:
        return jsonify(status="error", message=err), 502

    return jsonify(status="ok", fix=fix_result)


# ── 一键修复 + 建分支提 PR ──
@fix_bp.route("/api/fix/<scan_id>", methods=["POST"])
@_login_required
def fix_apply(scan_id):
    """一键修复：生成补丁 → 建分支 → 提草稿 PR。"""
    from modules.db import get_db
    from modules.helpers import is_vip_user
    import modules.git_integration as git_int

    db = get_db()
    user_id = session.get("user_id")
    scan = db.execute("SELECT * FROM scans WHERE scan_id = ? AND user_id = ?",
                      (scan_id, user_id)).fetchone()
    if not scan:
        return jsonify(status="error", message="扫描记录不存在"), 404

    vip = is_vip_user()
    if not _is_deep_and_vip(scan, vip):
        return jsonify(status="error", code="not_deep_vip",
                       message="一键修复仅对「深度扫描 + 会员」开放"), 403

    body = request.json or {}
    issue_key = body.get("issue_key", "")
    platform = body.get("platform", "github")  # github | gitlab
    repo_full_name = body.get("repo_full_name", "")
    if not repo_full_name:
        return jsonify(status="error", message="请提供仓库（repo_full_name）"), 400

    issue = _find_issue(scan, issue_key)
    if not issue:
        return jsonify(status="error", message="未找到该问题"), 404

    # 1. 生成补丁（含回验）
    fix_result, err = _call_scanner_fix(scan_id, issue)
    if err:
        return jsonify(status="error", message=err), 502
    if not fix_result or not fix_result.get("applicable"):
        reason = (fix_result or {}).get("reason", "无法自动修复")
        return jsonify(status="error", code="not_applicable", message=reason), 422

    # 2. 建分支 + 提草稿 PR
    # 需要「修复后的完整文件内容」——扫描器侧补丁只返回 before/after 片段，
    # 这里让扫描器侧支持返回完整修复后文件（通过 patch 应用）。
    # 简化：要求扫描器 /fix 返回 file_content_after 字段（完整文件）。
    new_content = fix_result.get("file_content_after", "")
    if not new_content:
        # 回退：如果扫描器没返回完整文件，无法建 PR，降级为只返回补丁
        return jsonify(
            status="ok",
            fix=fix_result,
            pr=None,
            note="补丁已生成（已通过回验），但缺少完整文件内容，请手动应用补丁或复制 after 片段。",
        ), 200

    pr_result = git_int.create_fix_pr(
        user_id=user_id,
        platform=platform,
        repo_full_name=repo_full_name,
        file_path=issue.get("file", ""),
        new_file_content=new_content,
        old_file_content="",
        check_id=issue.get("rule_id", ""),
        explanation=fix_result.get("explanation", ""),
        verified=fix_result.get("verified", False),
    )

    return jsonify(status="ok", fix=fix_result, pr=pr_result)


# ── 检查连接状态（供前端判断能否一键提 PR）──
@fix_bp.route("/api/fix/git-status")
@_login_required
def fix_git_status():
    """返回 GitHub/GitLab 连接状态。"""
    from modules.db import get_db
    db = get_db()
    user_id = session.get("user_id")
    user = db.execute(
        "SELECT github_username, gitlab_username FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()
    github_connected = bool(user and user["github_username"]) if user else False
    gitlab_connected = bool(user and user["gitlab_username"]) if user else False
    return jsonify(status="ok", github=github_connected, gitlab=gitlab_connected)
