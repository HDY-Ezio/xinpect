"""
煋鉴管理后台 - 设备指纹绑定模块
功能：设备指纹验证、绑定、解绑、验证码发送
"""
import hashlib
import json
import random
import string
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, session, redirect, url_for, render_template
from functools import wraps
from .db import get_db, is_admin_user
from .email_sender import _get_smtp_config
from .constants import logger, SMTP_TIMEOUT_SECONDS

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

device_bp = Blueprint("device_bind", __name__)


def generate_fingerprint_hash(data):
    """根据前端采集的设备特征生成指纹hash"""
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def get_client_fingerprint():
    """从请求中获取客户端设备指纹（由前端JS计算后通过header传入）"""
    fp = request.headers.get("X-Device-Fingerprint", "")
    return fp


def check_device_bound(user_id, fingerprint):
    """检查设备指纹是否已绑定"""
    if not fingerprint:
        return False
    db = get_db()
    row = db.execute(
        "SELECT id FROM admin_devices WHERE user_id=? AND device_fingerprint=? AND is_trusted=1",
        (user_id, fingerprint)
    ).fetchone()
    return row is not None


def update_device_last_used(fingerprint):
    """更新设备最后使用时间"""
    if not fingerprint:
        return
    db = get_db()
    db.execute(
        "UPDATE admin_devices SET last_used_at=datetime('now','localtime') WHERE device_fingerprint=?",
        (fingerprint,)
    )


def device_check_required(f):
    """增强版admin装饰器：登录 + 设备绑定双重校验"""
    @wraps(f)
    def decorated(*args, **kwargs):
        uid = session.get("user_id")
        if not uid:
            if _is_api_request():
                return jsonify({"error": "未登录"}), 401
            return redirect(url_for("login", next=request.url))
        if not is_admin_user(uid):
            if _is_api_request():
                return jsonify({"error": "无权限"}), 403
            return redirect(url_for("login"))

        # 设备指纹检查
        fingerprint = get_client_fingerprint()
        if not check_device_bound(uid, fingerprint):
            if _is_api_request():
                return jsonify({"error": "device_not_bound", "message": "设备未绑定"}), 403
            return redirect(url_for("device_bind.device_verify_page"))

        # 更新最后使用时间
        update_device_last_used(fingerprint)
        return f(*args, **kwargs)
    return decorated


def _is_api_request():
    """判断是否为API请求"""
    accept = request.headers.get("Accept", "")
    return accept.startswith("application/json") or request.is_json


def send_bind_code_email(to_email, code, expire_minutes=5):
    """发送设备绑定验证码邮件"""
    cfg = _get_smtp_config()
    if not cfg["user"] or not cfg["password"]:
        logger.error("[设备绑定] SMTP未配置，跳过发送")
        return False

    subject = "煋鉴 - 设备绑定验证码"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    html_body = (
        '<div style="font-family: Microsoft YaHei,Arial,sans-serif;max-width:520px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">'
        '<div style="background:linear-gradient(135deg,#1A2B4A,#2d4a7a);padding:28px 32px;text-align:center;">'
        '<h1 style="color:#fff;margin:0;font-size:22px;font-weight:600;">煋鉴 Xinpect</h1>'
        '<p style="color:rgba(255,255,255,0.85);margin:6px 0 0;font-size:13px;">管理后台设备绑定</p>'
        '</div>'
        '<div style="padding:32px;">'
        '<p style="font-size:15px;color:#333;margin:0 0 20px;">您好，</p>'
        '<p style="font-size:15px;color:#333;margin:0 0 20px;">您正在绑定新设备访问管理后台，请使用以下验证码完成绑定：</p>'
        '<div style="background:#f0f4f8;border:2px dashed #1A2B4A;border-radius:8px;padding:20px;text-align:center;margin:24px 0;">'
        '<span style="font-size:32px;font-weight:700;color:#1A2B4A;letter-spacing:8px;">{code}</span>'
        '</div>'
        '<p style="font-size:13px;color:#888;margin:0 0 16px;">⏰ 验证码 <strong>{expire_minutes} 分钟</strong>后失效 · {now_str}</p>'
        '<p style="font-size:13px;color:#888;margin:0;">如非本人操作，请忽略此邮件并尽快修改密码。</p>'
        '</div>'
        '<div style="background:#f8f9fa;padding:16px 32px;text-align:center;border-top:1px solid #eee;">'
        '<p style="font-size:12px;color:#aaa;margin:0;">煋鉴 Xinpect · xinpect.com</p>'
        '</div>'
        '</div>'
    ).format(code=code, expire_minutes=expire_minutes, now_str=now_str)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["user"]
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        if cfg["use_ssl"]:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(cfg["host"], cfg["port"], context=context, timeout=SMTP_TIMEOUT_SECONDS) as server:
                server.login(cfg["user"], cfg["password"])
                server.sendmail(cfg["user"], [to_email], msg.as_string())
        else:
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=SMTP_TIMEOUT_SECONDS) as server:
                server.starttls(context=ssl.create_default_context())
                server.login(cfg["user"], cfg["password"])
                server.sendmail(cfg["user"], [to_email], msg.as_string())
        logger.info("[设备绑定] 验证码邮件已发送至 %s", to_email)
        return True
    except Exception as e:
        logger.error("[设备绑定] 邮件发送失败 to=%s: %s", to_email, e)
        return False


# ============================================================
# 页面路由
# ============================================================

@device_bp.route("/admin/device-verify")
def device_verify_page():
    """设备验证页面 - 未绑定设备时展示"""
    uid = session.get("user_id")
    if not uid:
        return redirect(url_for("login", next=request.url))
    if not is_admin_user(uid):
        return redirect(url_for("login"))

    fingerprint = get_client_fingerprint()
    if fingerprint and check_device_bound(uid, fingerprint):
        return redirect(url_for("admin_panel.admin_dashboard"))

    return render_template("admin/device_verify.html")


@device_bp.route("/admin/devices")
def device_manage_page():
    """设备管理页面"""
    uid = session.get("user_id")
    if not uid:
        return redirect(url_for("login"))
    if not is_admin_user(uid):
        return redirect(url_for("login"))
    # 也需要设备绑定
    fingerprint = get_client_fingerprint()
    if not fingerprint or not check_device_bound(uid, fingerprint):
        return redirect(url_for("device_bind.device_verify_page"))
    return render_template("admin/device_manage.html")


# ============================================================
# API路由
# ============================================================

@device_bp.route("/api/admin/device/send-code", methods=["POST"])
def api_send_bind_code():
    """发送设备绑定验证码"""
    uid = session.get("user_id")
    if not uid or not is_admin_user(uid):
        return jsonify({"error": "未登录或无权限"}), 401

    db = get_db()
    # 获取管理员邮箱
    user = db.execute("SELECT email FROM users WHERE id=?", (uid,)).fetchone()
    if not user:
        return jsonify({"error": "用户不存在"}), 404

    email = user[0]
    fingerprint = request.json.get("fingerprint", "") if request.is_json else ""
    if not fingerprint:
        return jsonify({"error": "缺少设备指纹"}), 400

    # 检查是否已经绑定
    if check_device_bound(uid, fingerprint):
        return jsonify({"error": "该设备已绑定"}), 400

    # 生成6位验证码
    code = "".join(random.choices(string.digits, k=6))
    expire_minutes = 5
    expires_at = (datetime.now() + timedelta(minutes=expire_minutes)).strftime("%Y-%m-%d %H:%M:%S")

    # 存储验证码
    db.execute(
        "INSERT INTO admin_bind_codes (user_id, code, device_fingerprint, device_name, expires_at) VALUES (?, ?, ?, ?, ?)",
        (uid, code, fingerprint, request.json.get("device_name", ""), expires_at)
    )

    # 发送邮件
    if send_bind_code_email(email, code, expire_minutes):
        return jsonify({"success": True, "message": f"验证码已发送至 {email}"})
    else:
        return jsonify({"error": "验证码发送失败，请稍后重试"}), 500


@device_bp.route("/api/admin/device/bind", methods=["POST"])
def api_bind_device():
    """绑定设备"""
    uid = session.get("user_id")
    if not uid or not is_admin_user(uid):
        return jsonify({"error": "未登录或无权限"}), 401

    data = request.get_json() or {}
    fingerprint = data.get("fingerprint", "")
    code = data.get("code", "")
    device_name = data.get("device_name", "").strip() or "未命名设备"

    if not fingerprint or not code:
        return jsonify({"error": "缺少必要参数"}), 400

    db = get_db()

    # 验证验证码
    record = db.execute(
        "SELECT id, expires_at, used FROM admin_bind_codes WHERE user_id=? AND code=? AND device_fingerprint=? ORDER BY id DESC LIMIT 1",
        (uid, code, fingerprint)
    ).fetchone()

    if not record:
        return jsonify({"error": "验证码错误"}), 400

    record_id, expires_at, used = record
    if used:
        return jsonify({"error": "验证码已使用"}), 400

    if datetime.now().strftime("%Y-%m-%d %H:%M:%S") > expires_at:
        return jsonify({"error": "验证码已过期"}), 400

    # 标记验证码已使用
    db.execute("UPDATE admin_bind_codes SET used=1 WHERE id=?", (record_id,))

    # 检查是否已存在相同指纹
    existing = db.execute(
        "SELECT id FROM admin_devices WHERE user_id=? AND device_fingerprint=?",
        (uid, fingerprint)
    ).fetchone()

    if existing:
        # 重新激活
        db.execute(
            "UPDATE admin_devices SET is_trusted=1, device_name=?, last_used_at=datetime('now','localtime') WHERE id=?",
            (device_name, existing[0])
        )
    else:
        db.execute(
            "INSERT INTO admin_devices (user_id, device_fingerprint, device_name) VALUES (?, ?, ?)",
            (uid, fingerprint, device_name)
        )

    logger.info("[设备绑定] 用户%d绑定了新设备: %s (指纹: %s)", uid, device_name, fingerprint[:8])
    return jsonify({"success": True, "message": "设备绑定成功"})


@device_bp.route("/api/admin/devices")
def api_list_devices():
    """获取已绑定设备列表"""
    uid = session.get("user_id")
    if not uid or not is_admin_user(uid):
        return jsonify({"error": "未登录或无权限"}), 401

    db = get_db()
    rows = db.execute(
        "SELECT id, device_fingerprint, device_name, created_at, last_used_at, is_trusted FROM admin_devices WHERE user_id=? ORDER BY last_used_at DESC",
        (uid,)
    ).fetchall()

    current_fp = get_client_fingerprint()
    devices = []
    for row in rows:
        devices.append({
            "id": row[0],
            "fingerprint": row[1],
            "name": row[2] or "未命名设备",
            "created_at": row[3],
            "last_used_at": row[4],
            "is_trusted": bool(row[5]),
            "is_current": row[1] == current_fp
        })

    return jsonify({"devices": devices})


@device_bp.route("/api/admin/device/<int:device_id>", methods=["DELETE"])
def api_unbind_device(device_id):
    """解绑设备"""
    uid = session.get("user_id")
    if not uid or not is_admin_user(uid):
        return jsonify({"error": "未登录或无权限"}), 401

    db = get_db()
    # 确认设备属于当前用户
    device = db.execute(
        "SELECT id, device_fingerprint FROM admin_devices WHERE id=? AND user_id=?",
        (device_id, uid)
    ).fetchone()

    if not device:
        return jsonify({"error": "设备不存在"}), 404

    # 不能解绑当前设备
    current_fp = get_client_fingerprint()
    if device[1] == current_fp:
        return jsonify({"error": "不能解绑当前使用的设备"}), 400

    db.execute("DELETE FROM admin_devices WHERE id=?", (device_id,))
    logger.info("[设备绑定] 用户%d解绑了设备%d", uid, device_id)
    return jsonify({"success": True, "message": "设备已解绑"})
