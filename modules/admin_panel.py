"""
煋鉴管理后台 - 完整版
功能：用户管理、订单管理、发票管理、扫描记录、数据看板
"""
from flask import Blueprint, render_template, jsonify, request, session, redirect, url_for
from functools import wraps
from .db import get_db, is_admin_user
from .device_bind import device_check_required
from datetime import datetime, timedelta

admin_bp = Blueprint("admin_panel", __name__)

def admin_required(f):
    """管理员权限装饰器"""
    @wraps(f)
    def decorated(*args, **kwargs):
        uid = session.get("user_id")
        if not uid:
            if request.headers.get("Accept", "").startswith("application/json"):
                return jsonify({"error": "未登录"}), 401
            return redirect(url_for("login", next=request.url))
        if not is_admin_user(uid):
            if request.headers.get("Accept", "").startswith("application/json"):
                return jsonify({"error": "无权限"}), 403
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

# ============================================================
# 页面路由
# ============================================================

@admin_bp.route("/admin")
@device_check_required
def admin_dashboard():
    """管理后台首页 - 数据看板"""
    return render_template("admin/dashboard.html")

@admin_bp.route("/admin/users")
@device_check_required
def admin_users():
    """用户管理"""
    return render_template("admin/users.html")

@admin_bp.route("/admin/orders")
@device_check_required
def admin_orders():
    """订单管理"""
    return render_template("admin/orders.html")

@admin_bp.route("/admin/invoices")
@device_check_required
def admin_invoices():
    """发票管理"""
    return render_template("admin/invoices.html")

@admin_bp.route("/admin/scans")
@device_check_required
def admin_scans():
    """扫描记录"""
    return render_template("admin/scans.html")

# ============================================================
# Helper: 时间范围计算
# ============================================================

def _get_date_range(period):
    """根据period参数返回(start_date_str, end_date_str)或(None,None)表示全部"""
    if not period or period == "all":
        return None, None
    today = datetime.now().strftime("%Y-%m-%d")
    if period == "today":
        return today, today
    elif period == "7d":
        start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        return start, today
    elif period == "30d":
        start = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        return start, today
    return None, None

# ============================================================
# API - 数据看板
# ============================================================

@admin_bp.route("/api/admin/dashboard/stats")
@admin_required
def api_dashboard_stats():
    """获取看板统计数据"""
    db = get_db()
    period = request.args.get("period", "7d")
    
    # 按时间段统计
    start_date, end_date = _get_date_range(period)
    
    period_where = "1=1"
    period_params = []
    if start_date and end_date:
        period_where = "DATE(created_at) >= ? AND DATE(created_at) <= ?"
        period_params = [start_date, end_date]
    
    period_revenue = db.execute(
        f"SELECT COALESCE(SUM(amount), 0) FROM orders WHERE status='paid' AND {period_where}",
        period_params
    ).fetchone()[0]
    
    period_users = db.execute(
        f"SELECT COUNT(*) FROM users WHERE {period_where}",
        period_params
    ).fetchone()[0]
    
    period_scans = db.execute(
        f"SELECT COUNT(*) FROM scans WHERE {period_where}",
        period_params
    ).fetchone()[0]
    
    # 总统计
    total_users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_orders = db.execute("SELECT COUNT(*) FROM orders WHERE status='paid'").fetchone()[0]
    total_revenue = db.execute("SELECT COALESCE(SUM(amount), 0) FROM orders WHERE status='paid'").fetchone()[0]
    total_scans = db.execute("SELECT COUNT(*) FROM scans").fetchone()[0]
    
    # 待处理
    pending_invoices = db.execute(
        "SELECT COUNT(*) FROM invoice_requests WHERE status='pending'"
    ).fetchone()[0]
    
    return jsonify({
        "period": {
            "revenue": period_revenue,
            "users": period_users,
            "scans": period_scans
        },
        "total": {
            "users": total_users,
            "orders": total_orders,
            "revenue": total_revenue,
            "scans": total_scans
        },
        "pending": {
            "invoices": pending_invoices
        }
    })

# ============================================================
# API - 用户管理
# ============================================================

@admin_bp.route("/api/admin/users")
@admin_required
def api_list_users():
    """用户列表"""
    db = get_db()
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    search = request.args.get("search", "")
    status = request.args.get("status", "")
    start_date = request.args.get("start_date", "")
    end_date = request.args.get("end_date", "")
    
    offset = (page - 1) * per_page
    
    where_clauses = []
    params = []
    
    if search:
        where_clauses.append("(email LIKE ? OR CAST(id AS TEXT) LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    
    if status == "banned":
        where_clauses.append("is_banned = 1")
    elif status == "normal":
        where_clauses.append("is_banned = 0")
    elif status == "vip":
        where_clauses.append("is_vip = 1")
    elif status == "normal_user":
        where_clauses.append("is_vip = 0 AND is_banned = 0")
    
    if start_date:
        where_clauses.append("DATE(created_at) >= ?")
        params.append(start_date)
    if end_date:
        where_clauses.append("DATE(created_at) <= ?")
        params.append(end_date)
    
    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
    
    users = db.execute(
        f"SELECT * FROM users WHERE {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params + [per_page, offset]
    ).fetchall()
    
    total = db.execute(
        f"SELECT COUNT(*) FROM users WHERE {where_sql}",
        params
    ).fetchone()[0]
    
    return jsonify({
        "users": [dict(u) for u in users],
        "total": total,
        "page": page,
        "per_page": per_page
    })

@admin_bp.route("/api/admin/users/<int:user_id>", methods=["GET", "PUT"])
@admin_required
def api_user_detail(user_id):
    """用户详情/更新"""
    db = get_db()
    
    if request.method == "GET":
        user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not user:
            return jsonify({"error": "用户不存在"}), 404
        
        orders = db.execute(
            "SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM orders WHERE user_id=? AND status='paid'",
            (user_id,)
        ).fetchone()
        
        scans = db.execute(
            "SELECT COUNT(*) FROM scans WHERE user_id=?",
            (user_id,)
        ).fetchone()
        
        return jsonify({
            "user": dict(user),
            "stats": {
                "orders": orders[0],
                "total_spent": orders[1],
                "scans": scans[0]
            }
        })
    
    elif request.method == "PUT":
        data = request.get_json()
        
        updatable = ["is_banned", "vip_expire_at", "vip_expire_date", "is_admin", "credits", "is_vip"]
        updates = []
        values = []
        
        for field in updatable:
            if field in data:
                # vip_expire_date兼容旧前端
                actual_field = "vip_expire_at" if field == "vip_expire_date" else field
                updates.append(f"{actual_field}=?")
                values.append(data[field])
        
        if not updates:
            return jsonify({"error": "无有效更新字段"}), 400
        
        values.append(user_id)
        db.execute(f"UPDATE users SET {', '.join(updates)} WHERE id=?", values)
        db.commit()
        
        return jsonify({"success": True})

# ============================================================
# API - 订单管理
# ============================================================

@admin_bp.route("/api/admin/orders")
@admin_required
def api_list_orders():
    """订单列表"""
    db = get_db()
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    status = request.args.get("status", "")
    user_id = request.args.get("user_id", type=int)
    start_date = request.args.get("start_date", "")
    end_date = request.args.get("end_date", "")
    min_amount = request.args.get("min_amount", type=float)
    max_amount = request.args.get("max_amount", type=float)
    
    offset = (page - 1) * per_page
    
    where_clauses = []
    params = []
    
    if status:
        where_clauses.append("o.status=?")
        params.append(status)
    if user_id:
        where_clauses.append("o.user_id=?")
        params.append(user_id)
    if start_date:
        where_clauses.append("DATE(o.created_at) >= ?")
        params.append(start_date)
    if end_date:
        where_clauses.append("DATE(o.created_at) <= ?")
        params.append(end_date)
    if min_amount is not None:
        where_clauses.append("o.amount >= ?")
        params.append(min_amount)
    if max_amount is not None:
        where_clauses.append("o.amount <= ?")
        params.append(max_amount)
    
    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
    
    orders = db.execute(
        f"SELECT o.*, u.email as user_email FROM orders o LEFT JOIN users u ON o.user_id=u.id WHERE {where_sql} ORDER BY o.created_at DESC LIMIT ? OFFSET ?",
        params + [per_page, offset]
    ).fetchall()
    
    total = db.execute(
        f"SELECT COUNT(*) FROM orders o WHERE {where_sql}",
        params
    ).fetchone()[0]
    
    return jsonify({
        "orders": [dict(o) for o in orders],
        "total": total,
        "page": page,
        "per_page": per_page
    })

# ============================================================
# API - 发票管理
# ============================================================

@admin_bp.route("/api/admin/invoices")
@admin_required
def api_list_invoices():
    """发票申请列表"""
    db = get_db()
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    status = request.args.get("status", "")
    start_date = request.args.get("start_date", "")
    end_date = request.args.get("end_date", "")
    
    offset = (page - 1) * per_page
    
    where_clauses = []
    params = []
    
    if status:
        where_clauses.append("i.status=?")
        params.append(status)
    if start_date:
        where_clauses.append("DATE(i.created_at) >= ?")
        params.append(start_date)
    if end_date:
        where_clauses.append("DATE(i.created_at) <= ?")
        params.append(end_date)
    
    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
    
    invoices = db.execute(
        f"SELECT i.*, u.email as user_email FROM invoice_requests i LEFT JOIN users u ON i.user_id=u.id WHERE {where_sql} ORDER BY i.created_at DESC LIMIT ? OFFSET ?",
        params + [per_page, offset]
    ).fetchall()
    
    total = db.execute(
        f"SELECT COUNT(*) FROM invoice_requests i WHERE {where_sql}",
        params
    ).fetchone()[0]
    
    return jsonify({
        "invoices": [dict(i) for i in invoices],
        "total": total,
        "page": page,
        "per_page": per_page
    })

@admin_bp.route("/api/admin/invoices/<int:invoice_id>/complete", methods=["POST"])
@admin_required
def api_complete_invoice(invoice_id):
    """标记发票已开具"""
    db = get_db()
    db.execute("UPDATE invoice_requests SET status='completed' WHERE id=?", (invoice_id,))
    db.commit()
    return jsonify({"success": True})

print("✅ 管理后台模块加载成功")

# ============================================================
# API - 扫描记录
# ============================================================

@admin_bp.route("/api/admin/scans")
@admin_required
def api_list_scans():
    """扫描记录列表"""
    db = get_db()
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    user_search = request.args.get("user_search", "")
    language = request.args.get("language", "")
    status = request.args.get("status", "")
    start_date = request.args.get("start_date", "")
    end_date = request.args.get("end_date", "")
    
    offset = (page - 1) * per_page
    
    where_clauses = []
    params = []
    
    if user_search:
        # 支持按用户ID或邮箱搜索
        if user_search.isdigit():
            where_clauses.append("s.user_id=?")
            params.append(int(user_search))
        else:
            where_clauses.append("s.user_id IN (SELECT id FROM users WHERE email LIKE ?)")
            params.append(f"%{user_search}%")
    
    if language:
        where_clauses.append("s.language=?")
        params.append(language)
    
    if status:
        where_clauses.append("s.scan_status=?")
        params.append(status)
    
    if start_date:
        where_clauses.append("DATE(s.created_at) >= ?")
        params.append(start_date)
    if end_date:
        where_clauses.append("DATE(s.created_at) <= ?")
        params.append(end_date)
    
    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
    
    scans = db.execute(
        f"SELECT s.*, u.email as user_email FROM scans s LEFT JOIN users u ON s.user_id=u.id WHERE {where_sql} ORDER BY s.created_at DESC LIMIT ? OFFSET ?",
        params + [per_page, offset]
    ).fetchall()
    
    total = db.execute(
        f"SELECT COUNT(*) FROM scans s WHERE {where_sql}",
        params
    ).fetchone()[0]
    
    return jsonify({
        "scans": [dict(s) for s in scans],
        "total": total,
        "page": page,
        "per_page": per_page
    })
