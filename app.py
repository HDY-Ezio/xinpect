#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Xinpect Website - Flask Backend (modular)
Main entry: app init, blueprint registration, page routes, error handlers
"""
import os
import sys
from datetime import datetime

from flask import render_template, request, jsonify, session, flash, redirect, url_for, send_from_directory

# Ensure project root in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import shared resources from modules package
from modules import app, logger, get_db, init_db, close_db, is_admin_user  # noqa: F401
from modules.constants import (  # noqa: F401
    BRAINS, DB_PATH, DEFAULT_PORT, PRINT_SEPARATOR_LEN,
    HTTP_NOT_FOUND, HTTP_ENTITY_TOO_LARGE, HTTP_INTERNAL_ERROR,
)

# ── 安全装饰器（架构级统一权限/校验） ──────────────────────────
from functools import wraps

ADMIN_USER_IDS = {6}  # 已废弃：保留常量仅为兼容旧代码，判定一律走 is_admin()

def admin_required(f):
    """管理员权限装饰器：session 登录且 users.is_admin = 1。

    安全修复(2026-10-19)：移除 localhost bypass——Nginx 反代下 remote_addr 恒为
    127.0.0.1，会让外网用户全部绕过 admin 鉴权。
    安全修复(2026-10-20)：不再硬编码 user_id，统一读 users.is_admin（单一事实来源）。
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        uid = session.get("user_id")
        if not uid:
            return jsonify({"error": "未登录"}), 401
        if not is_admin_user(uid):
            return jsonify({"error": "无权限"}), 403
        return f(*args, **kwargs)
    return decorated

def login_required_api(f):
    """登录态装饰器：只需登录（不要求管理员）
    - 页面路由（Accept: text/html）：302跳转到/login
    - API路由（Accept: application/json）：返回401 JSON
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            # 检查是否是页面请求（浏览器）还是API请求
            accept_header = request.headers.get("Accept", "")
            if "text/html" in accept_header:
                # 页面请求，跳转到登录
                return redirect("/login?next=" + request.path)
            else:
                # API请求，返回401
                return jsonify({"error": "未登录"}), 401
        return f(*args, **kwargs)
    return decorated

def require_json(*required_fields):
    """请求校验装饰器：确保请求包含有效JSON和必填字段
    
    用法：
        @require_json()                    # 只要求有效JSON
        @require_json("title", "content")  # 要求必填字段
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            data = request.get_json(silent=True)
            if data is None:
                return jsonify({"error": "请求体必须是有效JSON"}), 400
            missing = [field for field in required_fields if field not in data]
            if missing:
                return jsonify({"error": "缺少必填字段: " + ", ".join(missing)}), 400
            return f(*args, **kwargs)
        return decorated
    return decorator

# ── 安全装饰器结束 ──────────────────────────────────────────────

from modules.helpers import get_current_user, is_vip_user  # noqa: F401
import traceback
from modules.csrf_protection import csrf_required
import json

# Register blueprints
from modules import visitor_analytics  # noqa: F401  访客埋点：全站访问记录的唯一出口
from modules.auth import auth_bp
from modules.payment import payment_bp
from modules.scan import scan_bp
from modules.api import api_bp
from modules.license import license_bp, init_license_table
from modules.feed import feed_bp
from modules.ci import ci_bp
from modules.github_oauth import github_bp
from modules.fix import fix_bp
from modules.git_integration import gitlab_bp
from modules.webhook_manager import webhook_bp, init_webhook_tables
from modules.feedback import feedback_bp, init_feedback_tables
from modules.leads import leads_bp, init_leads_tables
from modules.api_usage import api_usage_bp
from modules.team import team_bp
from modules import team_governance  # noqa: F401  团队版企业级能力（P1-P6），@app.route 注册
from modules.seo import seo_bp
from modules.free_try import try_bp
from modules.compensation import compensation_bp
# ── 排队系统 ──
import sys as _sys
_sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'queue_system'))
from queue_api import queue_bp
from modules.admin_panel import admin_bp
from queue_worker import start_worker_thread

app.register_blueprint(auth_bp)
app.register_blueprint(payment_bp)
app.register_blueprint(scan_bp)
app.register_blueprint(api_bp)
app.register_blueprint(license_bp)
app.register_blueprint(feed_bp)
app.register_blueprint(ci_bp)
app.register_blueprint(github_bp)
app.register_blueprint(fix_bp)
app.register_blueprint(gitlab_bp)
app.register_blueprint(webhook_bp)
app.register_blueprint(feedback_bp)
app.register_blueprint(leads_bp)
app.register_blueprint(api_usage_bp)
app.register_blueprint(team_bp)
app.register_blueprint(seo_bp)
app.register_blueprint(try_bp)
app.register_blueprint(compensation_bp)
app.register_blueprint(queue_bp)
app.register_blueprint(admin_bp)
from modules.device_bind import device_bp
app.register_blueprint(device_bp)
# 排队 Worker 不在这里启动：模块被任何进程导入（测试、巡检、工具脚本）都会起一套
# 后台线程去 Redis 抢任务。启动点在 __main__，见文件末尾。

# DB teardown
app.teardown_appcontext(close_db)

@app.route("/favicon.ico")
def favicon():
    return send_from_directory(app.static_folder, "favicon.ico", mimetype="image/x-icon")


@app.route("/robots.txt")
def robots_txt():
    return send_from_directory(app.static_folder, "robots.txt", mimetype="text/plain")


@app.route("/llms.txt")
def llms_txt():
    # AI 抓取入口（llms.txt 标准）：把产品摘要、口径、页面清单交给大模型读。
    # 2026-11-09：漏洞百科与博客两段改为按数据源实时生成。
    # 手写的静态文件只作为底稿，加漏洞条目 / 发博客文章不用再手抄进来。
    import re as _re
    path = os.path.join(app.static_folder, "llms.txt")
    try:
        with open(path, encoding="utf-8") as fh:
            doc = fh.read()

        from modules.seo import VULN_KB as _vkb
        rows = []
        for slug, v in _vkb.items():
            ref = v.get("cwe", "")
            owasp = (v.get("owasp") or "").replace("OWASP Top 10 ", "").replace("OWASP ", "")
            if owasp:
                ref = (ref + " / OWASP " + owasp).strip(" /")
            brief = (v.get("summary") or "").split("。")[0].strip()
            rows.append("- [%s检测](https://xinpect.xingwangzhineng.com/detect/%s): %s —— %s"
                        % (v.get("vuln_name", slug), slug, ref, brief))
        doc = _re.sub(
            r"## 漏洞百科.*?(?=## 技术博客)",
            "## 漏洞百科（每类漏洞的原理、示例代码与检测方法）\n\n"
            + "\n".join(rows) + "\n\n",
            doc, flags=_re.S)

        from modules.blog import load_all as _blog_all

        def _llms_clean(text):
            # llms.txt 一律不给百分比（检出率 / 误报率）：按句剔除含 % 的句子，
            # 规则写在生成端，以后新文章带了百分比也不会漏进来。
            text = (text or "").replace("\n", " ")
            parts = [s for s in _re.split(r"(?<=。)", text) if s.strip()]
            kept = [s for s in parts if "%" not in s]
            out = "".join(kept).strip() or text.strip()
            return out[:160]

        items = []
        for p in _blog_all():
            items.append("- [%s](https://xinpect.xingwangzhineng.com/blog/%s) —— %s"
                         % (p.get("title", ""), p.get("slug", ""),
                            _llms_clean(p.get("summary"))))
        doc = _re.sub(
            r"## 技术博客.*?(?=## 常见问题)",
            "## 技术博客（原创，含实测数据与方法学，可直接引用）\n\n"
            + "\n".join(items) + "\n\n",
            doc, flags=_re.S)

        return doc, 200, {"Content-Type": "text/plain; charset=utf-8"}
    except Exception:
        return send_from_directory(app.static_folder, "llms.txt",
                                   mimetype="text/plain")



# ============================================================
# Page routes (lightweight page rendering)
# ============================================================

@app.route("/")
def index():
    """Homepage"""
    return render_template("index.html", brains=BRAINS)


@app.route("/pricing")
def pricing_page():
    """Pricing page"""
    vip = is_vip_user()
    user = get_current_user()
    return render_template("pricing.html", is_vip=vip, user=user)


@app.route("/upload")
@login_required_api
def upload_page():
    """Upload page - requires login"""
    vip = is_vip_user()
    user = get_current_user()
    user_id = user.get("id") if user else None

    if vip:
        session["is_vip"] = True
        remaining = 0
        scan_mode = "full"
        from modules.scoring import get_user_credits
        credit_balance = get_user_credits(user_id) if user_id else 0
    else:
        session["is_vip"] = False
        from modules.scoring import check_daily_limit
        _, remaining = check_daily_limit()
        scan_mode = "basic"
        credit_balance = 0

    # ── 团队身份：注入档位上限，供前端「成员自选不超过上限」 ──
    team_mode_cap = None
    active_team_id = session.get('active_team_id')
    if active_team_id and user_id:
        try:
            from modules import team_governance
            from modules.team import _get_team_detail
            db = get_db()
            if _get_team_detail(active_team_id, user_id, db):
                team_mode_cap = team_governance.get_team_scan_mode(active_team_id)
        except Exception as e:
            app.logger.warning('[upload] 读取团队档位上限失败: %s', e)

    return render_template("upload.html",
                           daily_remaining=remaining,
                           credit_balance=credit_balance,
                           scan_mode=scan_mode,
                           is_vip=vip,
                           team_mode_cap=team_mode_cap)


# ============================================================
# 全站导航唯一依据：scripts/site_nav.json
# ------------------------------------------------------------
# 背景（2026-11-22）：站里曾同时有三套导航（首页 .nav、base .navbar、静态页
# .site-nav），导航项也各写各的 —— 客户从首页点到定价页，发现导航项少了两个。
# 现在只有一份清单：这个 JSON。templates/_nav.html 按它渲染，静态页由
# scripts/patch_static_nav.py 按它生成，tests/verify_site_consistency.py 按它校验。
# 读文件带 mtime 缓存：改 JSON 不用重启进程，也不用每次请求都开一次文件。
_NAV_CACHE = {"mtime": None, "core": []}


def _load_nav_core():
    import json as _json
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "site_nav.json")
    try:
        mtime = os.path.getmtime(path)
        if _NAV_CACHE["mtime"] != mtime:
            with open(path, encoding="utf-8") as f:
                _NAV_CACHE["core"] = _json.load(f).get("core", [])
            _NAV_CACHE["mtime"] = mtime
    except Exception as _e:
        logger.warning("[nav] 读 site_nav.json 失败，沿用上次清单: %s", _e)
    return _NAV_CACHE["core"]


@app.context_processor
def _inject_nav():
    return {"nav_core": _load_nav_core()}


# ============================================================
# 技术博客（内容存 content/blog/*.md，加文章不用改代码）
# ============================================================
@app.route("/blog")
def blog_index():
    from modules.blog import load_all, all_tags
    tag = (request.args.get("tag") or "").strip()
    posts = load_all()
    if tag:
        posts = [p for p in posts if tag in p["tags"]]
    # 主题标签一起传：博客不能只剩一个话题，读者一眼要能看出我们写哪几类
    return render_template("blog_list.html", posts=posts, tags=all_tags(), active_tag=tag)


@app.route("/blog/<slug>")
def blog_detail(slug):
    from modules.blog import get, related, slug_is_offline
    post = get(slug)
    if not post:
        # 曾经发布、后来因为质量不达标下线的文章：文件还在（改了 draft: true），
        # 给 301 回博客首页，别留一堆 404 让搜索引擎和读者都撞墙。
        if slug_is_offline(slug):
            return redirect("/blog", code=301)
        return render_template("404.html"), 404
    return render_template("blog_post.html", post=post, related=related(slug))


@app.route("/changelog")
def changelog_page():
    return render_template("changelog.html")

@app.route("/help")
def help_page():
    return render_template("help.html")

@app.route("/api-docs")
def api_docs_page():
    """对外 API 说明书。

    2026-11-10 之前，外部客户（包括老板自己）找不到任何接口说明：
    /docs 被兜底跳到 /help，/openapi.json 不存在，接口能调但没人知道怎么调。
    这一页是唯一入口，help 页顶部有链接指过来。
    """
    return render_template("api_docs.html")


@app.route('/whitepaper')
def whitepaper_page():
    return render_template('whitepaper.html')


@app.route("/docs")
def docs_redirect():
    """常见文档地址统一指到说明书。

    /docs 是开发者和 AI 工具最先会去猜的路径。站上没有 API 说明之前它跳到
    帮助页；现在说明书独立成页，这里直接指过去，少绕一跳。
    注意：/api-docs 只允许有一处注册，别在这里再加一个同名跳转——Flask 同路径
    重复注册时后加的那条可能盖掉前面的，说明书会莫名其妙变成跳转页。
    """
    return redirect("/api-docs", code=302)


# ============================================================
# 商业页面（关于我们、产品介绍、定价方案）
# ============================================================

@app.route("/pages/<path:filename>")
def static_pages(filename):
    """Serve static pages from static/pages/ directory"""
    pages_dir = os.path.join(app.static_folder, "pages")
    return send_from_directory(pages_dir, filename)


@app.route("/terms")
def terms_page():
    return render_template("terms.html")



# ============================================================
# Health check endpoint
# ============================================================

# 探引擎的预算（秒）。这个数必须显著小于所有调用方的耐心：
#   巡检 critical_path_monitor  curl --max-time 10（000 再探一次 20）
#   自愈 xinpect_monitor         urllib timeout 10
#   发布闸门 release_gate        --max-time 8
# 踩过的坑（2026-11-14 11:30 与 11:45 两次 P0 误报）：
#   这里原本写 5 秒，巡检的 curl 也正好等 5 秒。引擎在跑扫描时 /health 要 5 秒才回，
#   两边同时到期，巡检先放弃 → 报「官网挂了 HTTP 000」，
#   而同一秒里官网每个页面都是 200（/pricing、/login 全绿）。
# 健康接口的响应时间不能超过调用方的耐心，否则调用方永远拿不到真实答案。
_SCANNER_PROBE_TIMEOUT_SECONDS = 1.2


@app.route("/health")
def health_check():
    """健康检查端点，返回服务和引擎状态"""
    import requests as _requests
    from modules.constants import SCANNER_URL

    scanner_status = "unknown"
    scanner_info = {}
    try:
        health_url = SCANNER_URL.replace('/scan', '/health')
        resp = _requests.get(health_url, timeout=_SCANNER_PROBE_TIMEOUT_SECONDS)
        if resp.status_code == 200:
            scanner_status = "ok"
            scanner_info = resp.json()
        else:
            scanner_status = "degraded"
    except _requests.exceptions.ConnectionError:
        scanner_status = "down"          # 连不上：引擎真倒了
    except _requests.exceptions.Timeout:
        # 超时多半是引擎正在处理扫描请求，不是倒了。忙不等于病：
        # 判成不健康会让巡检去重启官网，而官网进程里正跑着客户的任务。
        scanner_status = "busy"
    except Exception:
        scanner_status = "down"

    active_scans = 0
    try:
        from modules.api import count_active_scans
        active_scans = count_active_scans()
    except Exception:
        pass

    status = "ok" if scanner_status in ("ok", "busy") else "degraded"
    result = {
        "status": status,
        "service": "xinpect-website",
        "active_scans": active_scans,
        "scanner": {
            "status": scanner_status,
            "version": scanner_info.get("version", ""),
            "brains_loaded": len(scanner_info.get("brain_ids", [])),
        }
    }
    http_code = 200 if status == "ok" else 503
    return jsonify(result), http_code

# ============================================================

@app.route("/sample-report")
def sample_report_page():
    """真实报告样例：数字唯一来源是生产扫描器真跑导出的 JSON，页面不写死结果。"""
    import json
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "scripts", "sample_report.json")
    with open(path, encoding="utf-8") as fh:
        report = json.load(fh)
    return render_template("sample_report.html", report=report)


@app.route("/sitemap.xml")
def sitemap():
    # 博客文章自动并入 sitemap（加文章不用改这里）
    try:
        from modules.blog import load_all as _blog_all
        _posts = _blog_all()
    except Exception:
        _posts = []
    # 漏洞百科页由 VULN_KB 驱动，加条目不用改 sitemap
    try:
        from modules.seo import VULN_KB as _vkb
        _vulns = list(_vkb.keys())
    except Exception:
        _vulns = []
    return render_template("sitemap.xml", posts=_posts, vulns=_vulns), 200, {"Content-Type": "application/xml"}
# Error handlers (with DB logging)
# ============================================================


# 扫描器噪音过滤（路径正则 + 已知扫描路径集合）
import re as _re
_SCANNER_PATH_RES = [
    _re.compile(r'^/wp(/|$)', _re.I),
    _re.compile(r'^/wordpress(/|$)', _re.I),
    _re.compile(r'/wp-json/', _re.I),
    _re.compile(r'/wp-admin/', _re.I),
    _re.compile(r'/wp-login', _re.I),
    _re.compile(r'\.php$', _re.I),
    _re.compile(r'/\.git/', _re.I),
    _re.compile(r'\.env', _re.I),
    _re.compile(r'/livewire/', _re.I),
    _re.compile(r'/administrator/', _re.I),
    _re.compile(r'/\.well-known/security\.txt', _re.I),
    _re.compile(r'/blog/wp-json/', _re.I),
    _re.compile(r'^/(joomla|drupal|magento)', _re.I),
    _re.compile(r'^/(signin|dashboard)(/|$)', _re.I),
    _re.compile(r'^/api/auth/signin', _re.I),
]

def _is_scanner_path(path):
    """检查路径是否为扫描器探测"""
    if path in SECURITY_SCAN_PATHS:
        return True
    return any(r.search(path) for r in _SCANNER_PATH_RES)

@app.errorhandler(Exception)
def handle_exception(e):
    """全局异常处理：记录到数据库（过滤扫描器噪音）"""
    from modules.db import get_db
    
    user_id = session.get("user_id")
    code = getattr(e, "code", 500)
    
    # 4xx到扫描器路径：不记录，直接返回响应
    if code < 500 and (_is_scanner_path(request.path) or 
            (request.path == '/' and request.method == 'POST' and code == 405)):
        if request.path.startswith("/api/"):
            return jsonify({"error": "接口不存在"}), code
        if code == 404:
            return render_template("404.html"), code
        return jsonify({"error": "服务器内部错误"}), code
    
    # 记录错误到数据库
    try:
        db = get_db()
        db.execute(
            """INSERT INTO error_logs 
            (user_id, endpoint, method, error_type, error_message, 
             stack_trace, request_params, response_status, ip_address, user_agent)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                request.path,
                request.method,
                type(e).__name__,
                str(e),
                traceback.format_exc(),
                json.dumps({
                    "args": dict(request.args),
                    "form": dict(request.form),
                    "json": request.get_json(silent=True),
                }, ensure_ascii=False),
                code,
                request.remote_addr,
                request.headers.get("User-Agent", ""),
            ),
        )
        db.commit()
    except Exception as log_error:
        app.logger.error("Failed to log error to DB: %s", log_error)
    
    # 返回标准错误响应
    if request.path.startswith("/api/"):
        return jsonify({
            "error": "服务器内部错误",
            "message": "我们已记录此问题，会尽快修复",
        }), code
    return jsonify({"error": "服务器内部错误"}), code


@app.errorhandler(404)
def page_not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "接口不存在"}), HTTP_NOT_FOUND
    return render_template("404.html"), HTTP_NOT_FOUND


@app.errorhandler(413)
def too_large(e):
    return jsonify({"error": "文件太大"}), HTTP_ENTITY_TOO_LARGE


# 安全扫描探针常见路径（不记录为错误，减少噪音）
SECURITY_SCAN_PATHS = {
    '/.env', '/.git/HEAD', '/.ssh/id_rsa', '/.ssh/id_ed25519',
    '/wp-config.php', '/wp-config.php-backup', '/wp-admin/setup-config.php',
    '/config.php', '/config.xml', '/phpinfo.php', '/actuator/heapdump',
    '/.bash_history', '/.npmrc', '/.svn/wc.db', '/.vscode/sftp.json',
    '/_vti_pvt/service.pwd', '/server.key', '/secrets.json',
    '/user_secrets.yml', '/docker-compose.yml', '/.env.production',
    '/backup.sql', '/backup.tar.gz', '/backup.zip', '/database.sql',
    '/database_backup.sql', '/storage/logs/laravel.log',
    # WordPress/通用扫描路径
    '/wp/', '/wordpress/', '/wp-admin/', '/wp-login.php',
    '/xmlrpc.php', '/.well-known/security.txt',
}

@app.after_request
def log_http_errors(response):
    """记录所有非2xx/3xx响应到错误日志表（过滤安全扫描探针噪音）"""
    if response.status_code >= 400:
        # 跳过扫描器噪音（404/405到已知扫描路径，不限来源IP）
        if response.status_code in (404, 405) and _is_scanner_path(request.path):
            return response
        # 跳过根路径POST（扫描器行为）
        if request.path == '/' and request.method == 'POST' and response.status_code == 405:
            return response
        # 跳过内部监控脚本的预期401/403（来自localhost的自动化工具）
        if response.status_code in (401, 403) and request.remote_addr == '127.0.0.1':
            ua = request.headers.get("User-Agent", "").lower()
            _monitor_uas = ("python-requests", "python-urllib", "curl/", "playwright")
            if any(m in ua for m in _monitor_uas):
                return response
            # Playwright浏览器（功能测试）的401也跳过
            if "chrome" in ua and "linux" in ua and request.path.startswith("/api/"):
                return response
        from modules.db import get_db
        try:
            db = get_db()
            db.execute(
                """INSERT INTO error_logs 
                (user_id, endpoint, method, error_type, error_message, 
                 request_params, response_status, ip_address, user_agent)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session.get("user_id"),
                    request.path,
                    request.method,
                    "HTTP_ERROR",
                    f"HTTP {response.status_code}",
                    json.dumps({
                        "args": dict(request.args),
                        "form": dict(request.form),
                        "json": request.get_json(silent=True),
                    }, ensure_ascii=False),
                    response.status_code,
                    request.remote_addr,
                    request.headers.get("User-Agent", ""),
                ),
            )
            db.commit()
        except Exception as log_err:
            app.logger.exception("Failed to log HTTP error: %s", log_err)
    return response


# ============================================================
# Admin: Monitoring & Alerts
# ============================================================

@app.route("/api/admin/monitoring")
@admin_required
def monitoring_status():
    """获取平台监控状态和告警信息"""
    
    import json as _json
    status_file = "/opt/xinpect-website/monitoring/status.json"
    alert_dir = "/opt/xinpect-website/monitoring/alerts"
    
    # 读取最新状态
    status_data = {}
    try:
        with open(status_file, "r") as f:
            status_data = _json.load(f)
    except Exception:
        status_data = {"error": "尚未获取到监控数据"}
    
    # 读取未解决的告警
    alerts = []
    try:
        for fname in sorted(os.listdir(alert_dir), reverse=True)[:20]:
            if fname.endswith(".json"):
                with open(os.path.join(alert_dir, fname), "r") as f:
                    alert = _json.load(f)
                    if not alert.get("resolved", False):
                        alerts.append(alert)
    except Exception:
        pass
    
    return jsonify({
        "status": status_data,
        "unresolved_alerts": alerts,
        "alert_count": len(alerts),
    })


@app.route("/api/admin/monitoring/resolve", methods=["POST"])
@admin_required
@require_json("alert_id", "action")
@csrf_required
def resolve_alert():
    """标记告警为已解决"""
    
    import json as _json
    data = request.get_json(silent=True) or {}
    alert_id = data.get("alert_id")
    if not alert_id:
        return jsonify({"error": "缺少 alert_id"}), 400
    
    # 安全校验: alert_id 只允许字母数字下划线和连字符
    import re as _re
    if not _re.match(r'^[a-zA-Z0-9_-]+$', str(alert_id)):
        return jsonify({"error": "非法的 alert_id"}), 400
    alert_file = f"/opt/xinpect-website/monitoring/alerts/{alert_id}.json"
    try:
        with open(alert_file, "r") as f:
            alert = _json.load(f)
        alert["resolved"] = True
        alert["resolved_at"] = datetime.now().isoformat()
        with open(alert_file, "w") as f:
            _json.dump(alert, f, ensure_ascii=False, indent=2)
        return jsonify({"success": True})
    except FileNotFoundError:
        return jsonify({"error": "告警不存在"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================
# Admin: Platform Dashboard
# ============================================================

@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    """平台数据可视化看板"""
    return render_template("admin_dashboard.html")


@app.route("/api/admin/platform-stats")
@admin_required
def platform_stats():
    """平台统计 API（供 Dashboard 前端使用）"""
    
    from modules.db import get_db
    db = get_db()
    days = request.args.get("days", 30, type=int)
    
    # 基础指标
    total_scans = db.execute("SELECT COUNT(*) FROM scans WHERE scan_status IS NULL OR scan_status='completed'").fetchone()[0]
    total_users = db.execute("SELECT COUNT(DISTINCT user_id) FROM scans WHERE user_id IS NOT NULL").fetchone()[0]
    avg_score = db.execute("SELECT ROUND(AVG(score),1) FROM scans WHERE scan_status IS NULL OR scan_status='completed'").fetchone()[0] or 0
    today_scans = db.execute("SELECT COUNT(*) FROM scans WHERE (scan_status IS NULL OR scan_status='completed') AND DATE(created_at) = DATE('now','localtime')").fetchone()[0]
    
    # 质量趋势（按日）
    trend_rows = db.execute(
        "SELECT DATE(created_at) as dt, ROUND(AVG(score),1) as avg_score, COUNT(*) as cnt "
        "FROM scans WHERE (scan_status IS NULL OR scan_status='completed') "
        "AND created_at >= DATE('now','localtime',?) "
        "GROUP BY DATE(created_at) ORDER BY dt",
        ("-%d days" % days,)
    ).fetchall()
    trend = [{"date": r["dt"], "avg_score": r["avg_score"], "count": r["cnt"]} for r in trend_rows]
    
    # 等级分布
    grade_rows = db.execute(
        "SELECT grade, COUNT(*) as cnt FROM scans WHERE scan_status IS NULL OR scan_status='completed' GROUP BY grade ORDER BY grade"
    ).fetchall()
    grades = {r["grade"]: r["cnt"] for r in grade_rows}
    
    # 扫描来源分布
    source_rows = db.execute(
        "SELECT COALESCE(source,'upload') as src, COUNT(*) as cnt FROM scans WHERE scan_status IS NULL OR scan_status='completed' GROUP BY src ORDER BY cnt DESC"
    ).fetchall()
    sources = {r["src"]: r["cnt"] for r in source_rows}
    
    # 编程语言分布 TOP 10
    lang_rows = db.execute(
        "SELECT language, COUNT(*) as cnt FROM scans WHERE (scan_status IS NULL OR scan_status='completed') AND language IS NOT NULL GROUP BY language ORDER BY cnt DESC LIMIT 10"
    ).fetchall()
    languages = {r["language"]: r["cnt"] for r in lang_rows}
    
    # 用户活跃度 TOP 5
    user_rows = db.execute(
        "SELECT u.email, COUNT(s.id) as scans, ROUND(AVG(s.score),1) as avg_score "
        "FROM scans s JOIN users u ON s.user_id = u.id "
        "WHERE s.user_id IS NOT NULL AND (s.scan_status IS NULL OR s.scan_status='completed') "
        "GROUP BY s.user_id ORDER BY scans DESC LIMIT 5"
    ).fetchall()
    top_users = [{"email": r["email"] or ("用户#%d" % (i+1)), "scans": r["scans"], "avg_score": r["avg_score"]} for i, r in enumerate(user_rows)]
    
    return jsonify({
        "summary": {
            "total_scans": total_scans,
            "total_users": total_users,
            "avg_score": avg_score,
            "today_scans": today_scans,
        },
        "trend": trend,
        "grades": grades,
        "sources": sources,
        "languages": languages,
        "top_users": top_users,
    })


# ============================================================
# 总控监视器（只读）—— 工厂总控台，只能看不能操作
# ============================================================

@app.route("/monitor")
@admin_required
def monitor_page():
    """总控监视器页面（只读，无操作入口）。"""
    return render_template("monitor.html")


@app.route("/api/monitor/status")
@admin_required
def monitor_status():
    """总控监视器数据接口（只读，仅 GET 采集各服务状态）。"""
    try:
        from modules.monitor_collector import collect_all
        data = collect_all()
        return jsonify(data)
    except Exception as e:
        logger.exception("monitor_status 采集失败: %s", e)
        return jsonify({"error": str(e)}), 500


# ============================================================
# 已知误报口径（单一事实来源）
# 旧版点击监控靠「页面上有没有几个特定容器 class」判断响应，把成功的试扫
# 报成 click_no_response。这些记录是旧判据真实产生过的，保留不删（删了等于
# 抹证据）；错误统计接口自己带上口径和「修复后新增数」，看的人不必靠人记。
# ============================================================
KNOWN_FALSE_POSITIVE_TYPES = {
    "click_no_response": {
        "reason": "旧版点击监控靠特定容器 class 判断响应，正常试扫被误报",
        "fixed_at": "2026-11-08",
        "verification": "QA 6i 真浏览器 10 场景 + 改前红 / 改后绿",
        "policy": "历史记录保留不删；修复上线后不应再新增",
    },
}

# ============================================================
# Admin: Error statistics
# ============================================================

@app.route("/admin/error-stats")
@admin_required
def error_stats():
    """查看错误统计（需要管理员session）"""
    from datetime import timedelta
    from modules.db import get_db
    
    
    days = request.args.get("days", 7, type=int)
    since_dt = datetime.now() - timedelta(days=days)
    since = since_dt.strftime("%Y-%m-%d %H:%M:%S")
    
    db = get_db()
    
    # 总错误数
    total = db.execute(
        "SELECT COUNT(*) FROM error_logs WHERE timestamp > ?", (since,)
    ).fetchone()[0]
    
    # 按类型分组
    by_type_rows = db.execute(
        """SELECT error_type, COUNT(*) as count, MAX(timestamp) as last_seen
        FROM error_logs WHERE timestamp > ?
        GROUP BY error_type ORDER BY count DESC""",
        (since,),
    ).fetchall()
    by_type = []
    for row in by_type_rows:
        item = dict(row)
        note = KNOWN_FALSE_POSITIVE_TYPES.get(item.get("error_type"))
        item["known_false_positive"] = bool(note)
        if note:
            item["note"] = note
        by_type.append(item)

    # 口径自带证据：修复时间点之后这类假警新增了几条，应当恒为 0。
    fp_types = list(KNOWN_FALSE_POSITIVE_TYPES)
    fp_marks = ",".join("?" for _ in fp_types)
    fp_after_fix = db.execute(
        "SELECT COUNT(*) FROM error_logs WHERE error_type IN (%s) "
        "AND timestamp > ?" % fp_marks,
        fp_types + [KNOWN_FALSE_POSITIVE_TYPES["click_no_response"]["fixed_at"]],
    ).fetchone()[0]
    fp_total = sum(r["count"] for r in by_type if r["known_false_positive"])
    
    # 按端点分组（TOP 10）
    by_endpoint_rows = db.execute(
        """SELECT endpoint, COUNT(*) as count, 
               GROUP_CONCAT(DISTINCT error_type) as error_types
        FROM error_logs WHERE timestamp > ?
        GROUP BY endpoint ORDER BY count DESC LIMIT 10""",
        (since,),
    ).fetchall()
    by_endpoint = [dict(r) for r in by_endpoint_rows]
    
    # 未解决的错误数
    unresolved_count = db.execute(
        "SELECT COUNT(*) FROM error_logs WHERE resolved = 0 AND timestamp > ?",
        (since,),
    ).fetchone()[0]
    
    # 最近10条未解决错误
    unresolved_rows = db.execute(
        """SELECT id, timestamp, endpoint, method, error_type, error_message, 
               response_status, ip_address
        FROM error_logs WHERE resolved = 0 AND timestamp > ?
        ORDER BY timestamp DESC LIMIT 10""",
        (since,),
    ).fetchall()
    unresolved = [dict(r) for r in unresolved_rows]
    
    return jsonify({
        "period_days": days,
        "total_errors": total,
        "total_errors_excluding_known_false_positive": total - fp_total,
        "known_false_positive_types": KNOWN_FALSE_POSITIVE_TYPES,
        "known_false_positive_in_period": fp_total,
        "known_false_positive_after_fix": fp_after_fix,
        "known_false_positive_note": (
            "历史假警是旧判据真实产生过的记录，保留不删；"
            "known_false_positive_after_fix 应为 0，非 0 说明修复失效或旧规则回流。"
        ),
        "by_type": by_type,
        "by_endpoint": by_endpoint,
        "unresolved_count": unresolved_count,
        "unresolved_recent": unresolved,
    })


@app.route("/admin/error-resolve", methods=["POST"])
@admin_required
@require_json("error_id", "action")
@csrf_required
def error_resolve():
    """标记错误为已解决"""
    
    data = request.get_json(silent=True) or {}
    error_id = data.get("id")
    notes = data.get("notes", "")
    
    if not error_id:
        return jsonify({"error": "缺少错误ID"}), 400
    
    from modules.db import get_db
    from datetime import datetime as dt
    db = get_db()
    db.execute(
        "UPDATE error_logs SET resolved = 1, resolved_at = ?, resolution_notes = ? WHERE id = ?",
        (dt.now().strftime("%Y-%m-%d %H:%M:%S"), notes, error_id),
    )
    db.commit()
    return jsonify({"ok": True, "message": f"错误 #{error_id} 已标记为已解决"})


# ============================================================
# 公告管理 API（admin only）
# ============================================================

# ADMIN_USER_IDS 和 _check_admin() 已迁移到顶部装饰器区域

@app.route("/api/admin/announcements", methods=["GET"])
@admin_required
def api_list_announcements():
    """获取所有公告（含已归档）"""
    from modules.db import get_db
    db = get_db()
    rows = db.execute(
        "SELECT id, title, content, type, is_active, created_at FROM announcements ORDER BY created_at DESC"
    ).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/api/admin/announcement", methods=["POST"])
@admin_required
@require_json("title", "content", "type")
@csrf_required
def api_create_announcement():
    """创建公告"""
    from modules.db import get_db
    data = request.get_json(force=True)
    title = (data.get("title") or "").strip()
    content = (data.get("content") or "").strip()
    ann_type = data.get("type", "info")
    if not title or not content:
        return jsonify({"error": "title和content不能为空"}), 400
    if ann_type not in ("info", "warning", "success"):
        ann_type = "info"
    db = get_db()
    cur = db.execute(
        "INSERT INTO announcements (title, content, type, is_active) VALUES (?, ?, ?, 1)",
        (title, content, ann_type)
    )
    db.commit()
    return jsonify({"ok": True, "id": cur.lastrowid, "message": f"公告 #{cur.lastrowid} 已发布"})

@app.route("/api/admin/announcement/<int:ann_id>", methods=["PUT"])
@admin_required
@csrf_required
def api_update_announcement(ann_id):
    """更新公告"""
    from modules.db import get_db
    data = request.get_json(force=True)
    db = get_db()
    existing = db.execute("SELECT id FROM announcements WHERE id=?", (ann_id,)).fetchone()
    if not existing:
        return jsonify({"error": "公告不存在"}), 404
    fields = []
    values = []
    if "title" in data:
        fields.append("title=?"); values.append(data["title"].strip())
    if "content" in data:
        fields.append("content=?"); values.append(data["content"].strip())
    if "type" in data:
        if data["type"] not in ("info", "warning", "success"):
            return jsonify({"error": "非法的 type 值"}), 400
        fields.append("type=?"); values.append(data["type"])
    if "is_active" in data:
        fields.append("is_active=?"); values.append(1 if data["is_active"] else 0)
    if not fields:
        return jsonify({"error": "没有要更新的字段"}), 400
    # 安全加固：白名单校验字段名
    ALLOWED_FIELDS = {"title", "content", "type", "is_active"}
    field_names = set()
    for f_str in fields:
        fname = f_str.split('=')[0]
        if fname not in ALLOWED_FIELDS:
            return jsonify({"error": f"非法字段名: {fname}"}), 400
        field_names.add(fname)
    values.append(ann_id)
    # 安全拼接: fields 已经过 ALLOWED_FIELDS 白名单校验
    set_clause = ", ".join(fields)
    db.execute(f"UPDATE announcements SET {set_clause} WHERE id=?", values)
    db.commit()
    return jsonify({"ok": True, "message": f"公告 #{ann_id} 已更新"})

@app.route("/api/admin/announcement/<int:ann_id>", methods=["DELETE"])
@admin_required
@csrf_required
def api_delete_announcement(ann_id):
    """删除公告（物理删除）"""
    from modules.db import get_db
    try:
        db = get_db()
        db.execute("DELETE FROM announcements WHERE id=?", (ann_id,))
        db.commit()
    except Exception as e:
        app.logger.exception("删除公告失败 id=%s: %s", ann_id, e)
        return jsonify({"error": "删除失败"}), 500
    return jsonify({"ok": True, "message": f"公告 #{ann_id} 已删除"})


# ============================================================
# Startup
# ============================================================


# P2: 部署包下载
@app.route('/api/v1/deploy/download')
def download_deploy_package():
    """提供部署包下载"""
    deploy_dir = os.path.join(app.static_folder, 'deploy')
    deploy_file = 'xinpect-docker-deploy.zip'
    if not os.path.exists(os.path.join(deploy_dir, deploy_file)):
        return jsonify({'error': '部署包不存在'}), 404
    return send_from_directory(deploy_dir, deploy_file, as_attachment=True)



# ============================================================
# 前端错误监控 - 接收前端上报的错误
# ============================================================

@app.route('/api/report-error', methods=['POST'])
def api_report_frontend_error():
    """接收前端错误报告"""
    try:
        data = request.get_json(force=True, silent=True) or {}
        
        error_msg = str(data.get('message', ''))[:500]
        error_type = str(data.get('type', 'frontend_error'))[:50]
        page_url = str(data.get('url', ''))[:200]
        user_action = str(data.get('action', ''))[:200]
        browser_info = str(data.get('browser', ''))[:200]
        stack_trace = str(data.get('stack', ''))[:2000]
        
        if not error_msg and not stack_trace:
            return jsonify({'error': '缺少错误信息'}), 400
        
        user_id = session.get('user_id')
        
        from modules.db import get_db
        db = get_db()
        cursor = db.execute(
            'SELECT COUNT(*) FROM error_logs WHERE error_message=? AND endpoint=? '
            'AND timestamp > datetime(?, ?)',
            (error_msg, page_url, 'now', '-5 minutes')
        )
        count = cursor.fetchone()[0]
        
        db.execute(
            'INSERT INTO error_logs '
            '(user_id, endpoint, method, error_type, error_message, stack_trace, user_agent) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            (user_id, page_url, 'REPORT', error_type, error_msg, stack_trace, browser_info)
        )
        db.commit()
        
        if count >= 2:
            app.logger.warning(
                '[前端错误聚合] 同类错误5分钟内出现3次: type=%s url=%s msg=%s',
                error_type, page_url, error_msg[:100]
            )
            # 实时告警：立即发送邮件
            try:
                from modules.helpers import send_alert_email
                send_alert_email(
                    subject=f"前端JS错误: {error_type}",
                    body=f"页面: {page_url}\n错误: {error_msg[:200]}\n5分钟内出现{count}次"
                )
            except Exception as alert_err:
                app.logger.exception(f"告警邮件发送失败: {alert_err}")
        
        return jsonify({'ok': True, 'reported': True})
        
    except Exception as e:
        app.logger.exception('report-error failed: %s', e)
        return jsonify({'ok': False}), 500



# ============================================================
# 维护状态通知 - 修复后通知在线用户
# ============================================================

MAINTENANCE_STATUS_FILE = os.path.join(os.path.dirname(__file__), 'maintenance_status.json')

@app.route('/api/maintenance-status', methods=['GET'])
def api_maintenance_status():
    """前端轮询：检查是否有修复通知"""
    try:
        if os.path.exists(MAINTENANCE_STATUS_FILE):
            import json
            with open(MAINTENANCE_STATUS_FILE, 'r') as f:
                status = json.load(f)
            return jsonify(status)
        return jsonify({'status': 'normal'})
    except Exception:
        return jsonify({'status': 'normal'})

@app.route('/api/admin/set-maintenance', methods=['POST'])
@admin_required
def api_set_maintenance():
    """管理员设置维护状态"""
    
    import json
    data = request.get_json(force=True, silent=True) or {}
    status_type = data.get('status', 'fixing')  # fixing / fixed / normal
    message = data.get('message', '')
    
    if status_type == 'normal':
        # 清除维护状态
        if os.path.exists(MAINTENANCE_STATUS_FILE):
            os.remove(MAINTENANCE_STATUS_FILE)
        return jsonify({'ok': True})
    
    status_data = {
        'status': status_type,
        'message': message,
        'updated_at': str(datetime.now()),
        'affected_paths': data.get('affected_paths', [])
    }
    
    with open(MAINTENANCE_STATUS_FILE, 'w') as f:
        json.dump(status_data, f, ensure_ascii=False)
    
    return jsonify({'ok': True, 'status': status_type})



# ========== 用户引导系统 API ==========
@app.route('/api/user/onboarding/status', methods=['GET'])
@login_required_api
def get_onboarding_status():
    """获取用户引导状态"""
    try:
        user_id = session.get('user_id')
        db = get_db()
        user = db.execute(
            'SELECT first_login_at, onboarding_completed FROM users WHERE id = ?',
            (user_id,)
        ).fetchone()
        if not user:
            return jsonify({'error': '用户不存在'}), 404
        scan_count = db.execute(
            'SELECT COUNT(*) as count FROM scans WHERE user_id = ?',
            (user_id,)
        ).fetchone()['count']
        return jsonify({
            'first_login': user['first_login_at'] is None,
            'onboarding_completed': bool(user['onboarding_completed']),
            'scan_count': scan_count
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/user/onboarding/complete', methods=['POST'])
@login_required_api
def complete_onboarding():
    """标记用户引导完成"""
    try:
        user_id = session.get('user_id')
        db = get_db()
        db.execute(
            'UPDATE users SET onboarding_completed = 1, first_login_at = COALESCE(first_login_at, datetime("now", "localtime")) WHERE id = ?',
            (user_id,)
        )
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/user/onboarding/reset', methods=['POST'])
@login_required_api
def reset_onboarding():
    """重置用户引导状态"""
    try:
        user_id = session.get('user_id')
        db = get_db()
        db.execute('UPDATE users SET onboarding_completed = 0 WHERE id = ?', (user_id,))
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ===== License页面路由（本地部署版）=====

@app.route('/api/referral/info', methods=['GET'])
@login_required_api
def get_referral_info():
    """获取当前用户的推荐码"""
    try:
        user_id = session.get('user_id')
        db = get_db()
        user = db.execute(
            'SELECT referral_code FROM users WHERE id = ?',
            (user_id,)
        ).fetchone()
        if not user or not user['referral_code']:
            return jsonify({'success': False, 'referral_code': None})
        return jsonify({
            'success': True,
            'referral_code': user['referral_code']
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/license')
def license_page():
    """本地部署版License页面 - 显示积分和充值"""
    from flask import render_template
    return render_template('license.html')

if __name__ == "__main__":
    init_db()

    # 初始化异步扫描相关表字段
    from modules.scan_worker import init_scan_tables
    init_scan_tables()
    init_webhook_tables()
    init_feedback_tables()
    init_leads_tables()

    # 团队协作 + 企业级治理表（P1-P6）：历史遗留 init_team_tables 从未挂启动流程，
    # 导致 teams/team_members 等表靠手动建、治理表（审计/门禁/共享积分池）不落地。
    # 治本：显式挂到启动流程，与 init_db / init_scan_tables 并列，幂等。
    from modules.team import init_team_tables
    init_team_tables()

    # 团队版企业级治理表（审计/门禁/共享积分池/orders.team_name 列迁移）同样挂启动流程。
    # 治本：治理表的幂等迁移（含 orders 表补列）必须在启动时执行，否则新增列要等
    # 首次调用治理接口才落库，造成「下单接口引用新列但列还没建」的时序坑。
    from modules.team_governance import init_governance_tables
    init_governance_tables()

    # 启动时验证扫描引擎可达性（宁可启动失败也不允许假结果）
    from modules.scanner import verify_scanner_engine
    verify_scanner_engine()

    # 队列调度器只在这里启动。它要认领并执行排队任务，全局只该有一个；
    # 早先挂在 modules/api.py 的模块级，导致任何 import 该模块的进程都起一个，
    # 还会顺手把生产在途任务当成「重启遗留」判死退款（2026-11-14 复现实证）。
    from modules.api import start_queue_dispatcher
    start_queue_dispatcher()

    # 同一件事的第二套：Redis 队列 Worker 也只在这里启动（原来挂在模块级）。
    start_worker_thread()

    # 付款后补单：定期把「门房已付款、网站还挂着 pending」的订单补开通。
    # 开通本来是前端轮询触发的，客户关掉页面就没人触发——钱收了货没发。
    # 同样只在这里启动，导入不产生副作用。
    from modules.payment import start_payment_reconciler
    start_payment_reconciler()

    try:
        port = int(os.environ.get("PORT", DEFAULT_PORT))
    except (ValueError, TypeError):
        port = DEFAULT_PORT
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    print("=" * PRINT_SEPARATOR_LEN)
    print("煋鉴 Xinpect 官网 v1.2 (modular, hardened)")
    print("数据库:", DB_PATH)
    print("端口:", port)
    print("Debug:", debug)
    print("=" * PRINT_SEPARATOR_LEN)
    app.run(host="127.0.0.1", port=port, debug=debug, threaded=True)

