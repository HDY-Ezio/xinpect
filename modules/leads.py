# -*- coding: utf-8 -*-
"""价格页留资 —— 把「来问价的人」接住。

为什么要有（2026-11-22，客户评审录屏）：
价格页是意向最强的一屏，此前除了「注册」没有任何出口。看完价格又不注册的人，
直接流失且我们完全不知道他是谁、卡在哪。留资入口的作用不是马上成交，
是让「想聊但没注册」的人有地方留下联系方式。

设计取舍：
· 只要一个联系方式（邮箱或微信，二选一即可），加一句「想要什么」。多一个必填项就少一半提交。
· 不建账号、不发验证码——这一步只收集意向，转化留给人工跟进。
· 存 ip_hash 而不是明文 IP：够用来限流和排重，不用把访客 IP 明文堆在库里。
"""
import hashlib
import re
import sqlite3
from functools import wraps

from flask import Blueprint, render_template, request, jsonify, session

from .constants import DB_PATH, logger
from .csrf_protection import csrf_required
from .db import get_db, is_admin_user

leads_bp = Blueprint("leads", __name__)

_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,}$")
_WECHAT_RE = re.compile(r"^[A-Za-z][-_A-Za-z0-9]{4,19}$|^1[3-9]\d{9}$")

# 限流：同一出口 IP 每小时 3 条、每天 10 条。挡的是脚本刷表，不是挡人。
_HOURLY_MAX = 3
_DAILY_MAX = 10


def init_leads_tables():
    """建表。用 sqlite3 直连，不依赖 Flask 上下文（导入即初始化不出错）。"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT,
                wechat TEXT,
                need TEXT,
                intent TEXT,
                source TEXT,
                ip_hash TEXT,
                ua TEXT,
                user_id INTEGER,
                status TEXT DEFAULT 'new',
                note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_leads_created ON leads(created_at);
            CREATE INDEX IF NOT EXISTS idx_leads_email ON leads(email);
            CREATE INDEX IF NOT EXISTS idx_leads_iphash ON leads(ip_hash, created_at);
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error("[leads] 建表失败: %s", e)


def _ip_hash():
    """IP 的单向指纹：只用于限流与排重，不落明文。"""
    ip = (request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
          or request.remote_addr or "")
    return hashlib.sha256(("xinpect-lead:" + ip).encode("utf-8")).hexdigest()[:32]


def _too_many(conn, ip_hash):
    row = conn.execute(
        "SELECT count(*) FROM leads WHERE ip_hash = ? AND created_at >= datetime('now','-1 hour','localtime')",
        (ip_hash,)).fetchone()
    if int(row[0] or 0) >= _HOURLY_MAX:
        return "这一小时提交得有点多，请稍后再试，或者直接邮件联系 hdyabcd@163.com"
    row = conn.execute(
        "SELECT count(*) FROM leads WHERE ip_hash = ? AND created_at >= date('now','localtime')",
        (ip_hash,)).fetchone()
    if int(row[0] or 0) >= _DAILY_MAX:
        return "今天已经收到你不少留言了，我们会按最早那条联系你"
    return ""


@leads_bp.route("/api/lead", methods=["POST"])
@csrf_required
def submit_lead():
    """收一条留资。邮箱/微信至少给一个，其余都可空。"""
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()
    wechat = (data.get("wechat") or "").strip()
    need = (data.get("need") or "").strip()[:1000]
    intent = (data.get("intent") or "").strip()[:40]
    source = (data.get("source") or "pricing").strip()[:40]

    if not email and not wechat:
        return jsonify({"status": "error", "error": "留一个联系方式就行：邮箱或微信"}), 400
    if email and not _EMAIL_RE.match(email):
        return jsonify({"status": "error", "error": "邮箱格式看起来不对，检查一下？"}), 400
    if not email and not _WECHAT_RE.match(wechat):
        return jsonify({"status": "error", "error": "微信号格式看起来不对（5-20 位字母数字，或手机号）"}), 400

    ip_hash = _ip_hash()
    try:
        conn = sqlite3.connect(DB_PATH, timeout=3)
        try:
            limit_msg = _too_many(conn, ip_hash)
            if limit_msg:
                return jsonify({"status": "error", "error": limit_msg}), 429

            if email:
                dup = conn.execute(
                    "SELECT id FROM leads WHERE email = ? AND created_at >= date('now','localtime')",
                    (email,)).fetchone()
                if dup:
                    conn.execute("UPDATE leads SET need = ? WHERE id = ?", (need or None, dup[0]))
                    conn.commit()
                    return jsonify({"status": "ok", "message": "今天已经收到你的留言，补充的需求已记下，我们会尽快联系你"})

            conn.execute(
                "INSERT INTO leads (email, wechat, need, intent, source, ip_hash, ua, user_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (email or None, wechat or None, need or None, intent or None, source, ip_hash,
                 (request.headers.get("User-Agent") or "")[:300],
                 session.get("user_id")))
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        logger.exception("[leads] 保存留资失败: %s", e)
        return jsonify({"status": "error", "error": "提交失败，稍后再试，或邮件 hdyabcd@163.com"}), 500

    logger.info("[leads] 新留资 email=%s wechat=%s intent=%s source=%s",
                bool(email), bool(wechat), intent, source)
    return jsonify({"status": "ok", "message": "收到了，我们会在一个工作日内联系你"})


def _admin_only(f):
    @wraps(f)
    def w(*a, **kw):
        if not session.get("user_id") or not is_admin_user(session.get("user_id")):
            return jsonify({"error": "无权限"}), 403
        return f(*a, **kw)
    return w


@leads_bp.route("/admin/leads")
def admin_leads_page():
    """后台看留资：谁留的、想要什么、什么时候留的。"""
    if not session.get("user_id") or not is_admin_user(session.get("user_id")):
        from flask import redirect, url_for
        return redirect(url_for("login", next=request.url))
    db = get_db()
    rows = db.execute(
        "SELECT id, email, wechat, need, intent, source, status, created_at "
        "FROM leads ORDER BY id DESC LIMIT 500").fetchall()
    total = db.execute("SELECT count(*) FROM leads").fetchone()[0]
    today = db.execute(
        "SELECT count(*) FROM leads WHERE created_at >= date('now','localtime')").fetchone()[0]
    return render_template("admin/leads.html", rows=rows, total=total, today=today)
