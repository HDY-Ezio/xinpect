# -*- coding: utf-8 -*-
"""
煋鉴排队系统 - Flask API 蓝图（v2 - 集成真实扫描流程）
提供排队提交、状态查询、取消排队等接口
"""

import uuid
import time
import json
import logging
from flask import Blueprint, request, jsonify, render_template, session, g

logger = logging.getLogger("xinpect-queue-api")

queue_bp = Blueprint("queue", __name__, template_folder="templates")


def _get_user_from_request():
    """从请求中提取用户信息（兼容现有认证体系）"""
    user_id = None
    email = ""
    is_vip = False

    # 优先从 Flask session 获取（主应用认证）
    if session:
        user_id = session.get("user_id")
        email = session.get("email", "")

    # 尝试从 Flask g 对象获取（如果中间件已认证）
    if hasattr(g, "current_user") and g.current_user:
        user_id = g.current_user.get("id", user_id)
        email = g.current_user.get("email", email)
        is_vip = g.current_user.get("is_vip", False)

    # 降级到请求头/参数
    if not user_id:
        uid = request.headers.get("X-User-Id") or request.args.get("user_id")
        user_id = int(uid) if uid else None
    if not email:
        email = request.headers.get("X-User-Email") or request.args.get("email", "")
    if not is_vip:
        is_vip = request.headers.get("X-User-Vip", "0") == "1"

    return int(user_id) if user_id else 0, str(email), bool(is_vip)


def _check_vip_status(user_id: int) -> bool:
    """检查用户VIP状态（查数据库）"""
    try:
        import sqlite3
        from modules.constants import DB_PATH
        db = sqlite3.connect(DB_PATH)
        row = db.execute(
            "SELECT is_vip, vip_expire FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        db.close()
        if row and row[0]:
            # 检查VIP是否过期
            if row[1]:
                from datetime import datetime
                try:
                    expire = datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S")
                    if expire > datetime.now():
                        return True
                except (ValueError, TypeError):
                    pass
            else:
                return True
        return False
    except Exception:
        return False


def _collect_files_for_queue() -> dict:
    """从请求中收集代码文件（与主扫描流程一致）"""
    files_dict = {}

    # 从 form files 收集
    if request.files:
        for key in request.files:
            file_storage = request.files[key]
            if file_storage.filename:
                try:
                    content = file_storage.read().decode('utf-8', errors='replace')
                    if content.strip():
                        files_dict[file_storage.filename] = content
                except Exception as e:
                    logger.warning(f"读取文件失败 {file_storage.filename}: {e}")

    # 从 JSON body 收集（粘贴代码场景）
    if not files_dict and request.is_json:
        data = request.get_json(silent=True) or {}
        code_files = data.get("code_files", data.get("files", {}))
        if isinstance(code_files, dict):
            files_dict = code_files
        elif isinstance(code_files, list):
            for i, f in enumerate(code_files):
                if isinstance(f, dict) and "content" in f:
                    name = f.get("name", f"file_{i}.txt")
                    files_dict[name] = f["content"]

    # 从 form text 收集（代码粘贴）
    if not files_dict:
        code_text = request.form.get("code", "")
        if code_text.strip():
            lang = request.form.get("language", "auto")
            ext_map = {"python": ".py", "javascript": ".js", "java": ".java",
                      "go": ".go", "php": ".php", "auto": ".txt"}
            ext = ext_map.get(lang, ".txt")
            files_dict[f"pasted_code{ext}"] = code_text

    return files_dict


@queue_bp.route("/api/queue/submit", methods=["POST"])
def submit_scan():
    """
    提交扫描任务到排队系统
    支持文件上传和JSON格式
    Body: {project_name, scan_mode, files/code_files}
    Response: {success, task_id, position, estimated_wait, status}
    """
    from queue_manager import queue_manager

    if not queue_manager.ping():
        return jsonify({"success": False, "error": "排队服务暂不可用"}), 503

    user_id, email, is_vip = _get_user_from_request()
    if not user_id:
        return jsonify({"success": False, "error": "未登录"}), 401

    # 检查VIP状态
    is_vip = _check_vip_status(user_id) or is_vip

    # 获取项目名称
    if request.is_json:
        data = request.get_json(silent=True) or {}
        project_name = data.get("project_name", "").strip()
        scan_mode = data.get("scan_mode", "smart")
    else:
        project_name = request.form.get("project_name", "").strip()
        scan_mode = request.form.get("scan_mode", "smart")

    if not project_name:
        return jsonify({"success": False, "error": "项目名称不能为空"}), 400

    # 收集代码文件
    files_dict = _collect_files_for_queue()
    if not files_dict:
        return jsonify({"success": False, "error": "请上传代码文件或粘贴代码"}), 400

    # 生成任务ID
    task_id = f"scan_{user_id}_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    file_count = len(files_dict)

    # 将文件数据存入任务extra
    extra = {
        "files_data": json.dumps(files_dict, ensure_ascii=False),
        "language": request.form.get("language", request.args.get("language", "auto")) if not request.is_json else data.get("language", "auto"),
    }

    result = queue_manager.submit_task(
        task_id=task_id,
        user_id=user_id,
        email=email,
        project_name=project_name,
        scan_mode=scan_mode,
        is_vip=is_vip,
        file_count=file_count,
        extra=extra,
    )

    if result["success"]:
        # 同时在scans表中创建记录（状态为pending）
        try:
            import sqlite3
            from modules.constants import DB_PATH
            db = sqlite3.connect(DB_PATH)
            total_lines = sum(len(v.split('\n')) for v in files_dict.values() if isinstance(v, str))
            db.execute("""
                INSERT INTO scans (scan_id, user_id, title, file_count, files_meta, results,
                score, grade, issue_count, language, credits_spent, total_lines, scan_mode,
                source, scan_status, scan_progress, scan_progress_text)
                VALUES (?, ?, ?, ?, ?, '[]', 0, '', 0, ?, 0, ?, ?, 'queue', 'pending', 5, '排队等待中')
            """, (task_id, user_id, project_name, file_count,
                  json.dumps(list(files_dict.keys()), ensure_ascii=False),
                  extra.get("language", "auto"), total_lines, scan_mode))
            db.commit()
            db.close()
        except Exception as e:
            logger.warning(f"创建scan记录失败: {e}")

        # 发送排队开始邮件
        try:
            from queue_emails import send_queue_enter_email
            send_queue_enter_email(email, project_name, result["position"], result["estimated_wait"])
        except Exception as e:
            logger.warning(f"排队邮件发送失败: {e}")

    status_code = 200 if result["success"] else 429
    return jsonify(result), status_code


@queue_bp.route("/api/queue/status", methods=["GET"])
def scan_status():
    """
    查询扫描任务状态（排队系统专用）
    GET /api/queue/status?task_id=xxx
    """
    from queue_manager import queue_manager

    task_id = request.args.get("task_id", "")
    if not task_id:
        return jsonify({"success": False, "error": "缺少task_id"}), 400

    status = queue_manager.get_status(task_id)
    if not status:
        # 降级到scans表查询
        try:
            import sqlite3
            from modules.constants import DB_PATH
            db = sqlite3.connect(DB_PATH)
            row = db.execute(
                "SELECT scan_status, score, grade, issue_count FROM scans WHERE scan_id = ?",
                (task_id,)
            ).fetchone()
            db.close()
            if row:
                return jsonify({
                    "success": True,
                    "task_id": task_id,
                    "status": row[0] or "unknown",
                    "score": row[1],
                    "grade": row[2],
                    "total_issues": row[3],
                })
        except Exception:
            pass
        return jsonify({"success": False, "error": "任务不存在"}), 404

    return jsonify({"success": True, **status})


@queue_bp.route("/api/queue/cancel", methods=["POST"])
def cancel_scan():
    """
    取消排队中的任务
    POST /api/queue/cancel
    Body: {task_id}
    """
    from queue_manager import queue_manager

    user_id, _, _ = _get_user_from_request()
    if not user_id:
        return jsonify({"success": False, "error": "未登录"}), 401

    data = request.get_json(silent=True) or {}
    task_id = data.get("task_id", "")
    if not task_id:
        return jsonify({"success": False, "error": "缺少task_id"}), 400

    result = queue_manager.cancel_task(task_id, user_id)

    # 同步更新DB状态
    if result.get("success"):
        try:
            import sqlite3
            from modules.constants import DB_PATH
            db = sqlite3.connect(DB_PATH)
            db.execute("UPDATE scans SET scan_status='cancelled' WHERE scan_id=?", (task_id,))
            db.commit()
            db.close()
        except Exception:
            pass

    return jsonify(result)


@queue_bp.route("/api/queue/overview", methods=["GET"])
def queue_overview():
    """
    获取队列概览（前端轮询用）
    GET /api/queue/overview
    """
    from queue_manager import queue_manager

    overview = queue_manager.get_queue_overview()
    return jsonify({"success": True, **overview})


@queue_bp.route("/api/queue/upgrade-vip", methods=["POST"])
def upgrade_vip():
    """
    提升任务为VIP优先
    POST /api/queue/upgrade-vip
    Body: {task_id}
    """
    from queue_manager import queue_manager

    user_id, _, _ = _get_user_from_request()
    if not user_id:
        return jsonify({"success": False, "error": "未登录"}), 401

    data = request.get_json(silent=True) or {}
    task_id = data.get("task_id", "")
    if not task_id:
        return jsonify({"success": False, "error": "缺少task_id"}), 400

    result = queue_manager.upgrade_to_vip(task_id, user_id)
    return jsonify(result)


# ── 管理接口 ──────────────────────────────────────────

@queue_bp.route("/api/admin/queue/list", methods=["GET"])
def admin_queue_list():
    """管理员：查看排队列表"""
    from queue_manager import queue_manager

    admin_key = request.headers.get("X-Admin-Key", "")
    import os
    expected_key = os.environ.get("QUEUE_ADMIN_KEY", "xinpect-admin-2026")
    if admin_key != expected_key:
        return jsonify({"success": False, "error": "无权限"}), 403

    limit = request.args.get("limit", 50, type=int)
    queue_list = queue_manager.get_queue_list(limit)
    overview = queue_manager.get_queue_overview()

    return jsonify({"success": True, "overview": overview, "queue": queue_list})


# ── 前端页面路由 ──────────────────────────────────────

@queue_bp.route("/queue/status")
def queue_status_page():
    """排队状态页面"""
    task_id = request.args.get("task_id", "")
    return render_template("queue_status.html", task_id=task_id)


@queue_bp.route("/admin/queue")
def admin_queue_page():
    """管理后台：排队监控面板"""
    return render_template("queue_monitor.html")
