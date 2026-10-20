"""用户反馈模块 - 收集扫描报告质量反馈"""
import json
import sqlite3
import threading
import requests
from flask import Blueprint, request, jsonify, session
from .db import get_db
from .constants import app, logger, DB_PATH, HTTP_OK, HTTP_BAD_REQUEST, HTTP_UNAUTHORIZED
from .csrf_protection import csrf_required

feedback_bp = Blueprint("feedback", __name__)

# 飞书告警 Webhook（留空则不发通知）
FEISHU_WEBHOOK_URL = ""


# ==================== 数据库初始化 ====================

def init_feedback_tables():
    """创建 feedbacks 表（使用 sqlite3 直连，无需 Flask 上下文）"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS feedbacks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_id VARCHAR(100) NOT NULL,
                user_id INTEGER,
                rating INTEGER CHECK (rating >= 1 AND rating <= 5),
                issue_types TEXT,
                feedback_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_feedbacks_scan ON feedbacks(scan_id);
            CREATE INDEX IF NOT EXISTS idx_feedbacks_user ON feedbacks(user_id);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_feedbacks_user_scan ON feedbacks(user_id, scan_id);
        """)
        conn.commit()
        conn.close()
        logger.info("[feedback] feedbacks 表初始化完成")
    except Exception as e:
        logger.error("[feedback] 初始化表失败: %s", e)


# ==================== API 路由 ====================

@feedback_bp.route("/api/feedback", methods=["POST"])
@csrf_required
def submit_feedback():
    """提交反馈"""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error", "error": "请先登录"}), HTTP_UNAUTHORIZED

    data = request.get_json(silent=True) or {}
    scan_id = (data.get("scan_id") or "").strip()
    rating = data.get("rating")
    issue_types = data.get("issue_types") or []
    feedback_text = (data.get("feedback_text") or "").strip()

    if not scan_id:
        return jsonify({"status": "error", "error": "缺少 scan_id"}), HTTP_BAD_REQUEST
    if rating not in (1, 5):
        return jsonify({"status": "error", "error": "rating 只能为 1 或 5"}), HTTP_BAD_REQUEST
    if not isinstance(issue_types, list):
        return jsonify({"status": "error", "error": "issue_types 格式错误"}), HTTP_BAD_REQUEST

    valid_types = {"漏报", "误报", "报告不清晰", "修复建议没用", "其他"}
    issue_types = [t for t in issue_types if t in valid_types]

    if len(feedback_text) > 1000:
        feedback_text = feedback_text[:1000]

    try:
        db = get_db()
        existing = db.execute(
            "SELECT id FROM feedbacks WHERE user_id = ? AND scan_id = ?",
            (user_id, scan_id)
        ).fetchone()
        if existing:
            return jsonify({"status": "error", "error": "您已对此报告提交过反馈"}), HTTP_BAD_REQUEST

        db.execute(
            "INSERT INTO feedbacks (scan_id, user_id, rating, issue_types, feedback_text) VALUES (?, ?, ?, ?, ?)",
            (scan_id, user_id, rating, json.dumps(issue_types, ensure_ascii=False), feedback_text)
        )
        db.commit()
        logger.info("[feedback] 用户 %s 对扫描 %s 提交反馈: rating=%s", user_id, scan_id, rating)

        if rating == 1:
            threading.Thread(
                target=_send_feishu_notify,
                args=(user_id, scan_id, issue_types, feedback_text),
                daemon=True
            ).start()

        return jsonify({"status": "ok", "message": "感谢反馈！"})

    except Exception as e:
        logger.error("[feedback] 提交反馈失败: %s", e)
        return jsonify({"status": "error", "error": "提交失败，请稍后重试"}), HTTP_BAD_REQUEST


@feedback_bp.route("/api/feedback/status", methods=["GET"])
def check_feedback_status():
    """检查当前用户是否已对某扫描提交反馈"""
    user_id = session.get("user_id")
    scan_id = request.args.get("scan_id", "").strip()
    if not user_id or not scan_id:
        return jsonify({"submitted": False})
    try:
        db = get_db()
        row = db.execute(
            "SELECT id, rating FROM feedbacks WHERE user_id = ? AND scan_id = ?",
            (user_id, scan_id)
        ).fetchone()
        if row:
            return jsonify({"submitted": True, "rating": row["rating"]})
        return jsonify({"submitted": False})
    except Exception:
        return jsonify({"submitted": False})


@feedback_bp.route("/api/feedback/stats", methods=["GET"])
def feedback_stats():
    """获取反馈统计（管理员）"""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error", "error": "请先登录"}), HTTP_UNAUTHORIZED

    try:
        db = get_db()
        if user_id != 6:
            return jsonify({"status": "error", "error": "无权限"}), 403

        stats = db.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN rating = 5 THEN 1 ELSE 0 END) as useful_count,
                SUM(CASE WHEN rating = 1 THEN 1 ELSE 0 END) as useless_count,
                ROUND(AVG(rating), 2) as avg_rating
            FROM feedbacks
        """).fetchone()

        recent = db.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN rating = 5 THEN 1 ELSE 0 END) as useful_count,
                SUM(CASE WHEN rating = 1 THEN 1 ELSE 0 END) as useless_count
            FROM feedbacks
            WHERE created_at >= datetime('now', '-7 days')
        """).fetchone()

        issue_dist = db.execute(
            "SELECT issue_types FROM feedbacks WHERE rating = 1 AND issue_types IS NOT NULL"
        ).fetchall()

        type_counts = {}
        for row in issue_dist:
            try:
                types = json.loads(row["issue_types"])
                for t in types:
                    type_counts[t] = type_counts.get(t, 0) + 1
            except (json.JSONDecodeError, TypeError):
                pass

        return jsonify({
            "status": "ok",
            "total": stats["total"] or 0,
            "useful_count": stats["useful_count"] or 0,
            "useless_count": stats["useless_count"] or 0,
            "avg_rating": float(stats["avg_rating"] or 0),
            "recent_7d": {
                "total": recent["total"] or 0,
                "useful_count": recent["useful_count"] or 0,
                "useless_count": recent["useless_count"] or 0,
            },
            "issue_type_distribution": type_counts
        })

    except Exception as e:
        logger.error("[feedback] 获取统计失败: %s", e)
        return jsonify({"status": "error", "error": "获取统计失败"}), HTTP_BAD_REQUEST


# ==================== 飞书通知 ====================

def _send_feishu_notify(user_id, scan_id, issue_types, feedback_text):
    """发送飞书通知（差评时触发）"""
    if not FEISHU_WEBHOOK_URL:
        return
    try:
        content = (
            f"👎 用户反馈差评\n"
            f"用户ID: {user_id}\n"
            f"扫描ID: {scan_id}\n"
            f"问题分类: {', '.join(issue_types) if issue_types else '未选择'}\n"
            f"具体反馈: {feedback_text or '无'}"
        )
        payload = {"msg_type": "text", "content": {"text": content}}
        requests.post(FEISHU_WEBHOOK_URL, json=payload, timeout=5)
    except Exception as e:
        logger.error("[feedback] 飞书通知发送失败: %s", e)
