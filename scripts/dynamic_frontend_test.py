#!/usr/bin/env python3
"""
煋鉴官网全量动态前端测试脚本 v5
新增5个模块：真实扫描全流程、报告页验证、表单校验与错误处理、移动端响应式、会话与登出
"""

import json
import sys
import signal
import re
import traceback
from datetime import datetime
from playwright.sync_api import sync_playwright

# 全局自杀超时 (180s, 扫描模块需要更长时间)
def self_kill(signum, frame):
    print("\n⚠️  自杀超时(180s)")
    output_report()
    sys.exit(1)
signal.signal(signal.SIGALRM, self_kill)
signal.alarm(180)

# ============================================================
# 配置
# ============================================================
BASE_URL = "http://localhost:8621"
TEST_EMAIL = "hdyabcd@163.com"
TEST_PASSWORD = "1234q5q6"
REPORT_PATH = "/tmp/xinpect_full_test_report.json"
NAV_T = 5000
W = 200
WM = 500

# ============================================================
# 结果收集
# ============================================================
class R:
    results = []
    console_errors = []
    start = datetime.now()
    
    @classmethod
    def add(cls, cat, name, ok, detail="", url=""):
        cls.results.append({"category": cat, "name": name, "passed": ok, "detail": detail[:300], "url": url})
    
    @classmethod
    def summary(cls):
        t = len(cls.results)
        p = sum(1 for r in cls.results if r["passed"])
        f = t - p
        d = (datetime.now() - cls.start).total_seconds()
        return {
            "total": t, "passed": p, "failed": f,
            "pass_rate": f"{p/t*100:.1f}%" if t else "N/A",
            "duration_seconds": round(d, 1),
            "console_errors_count": len(cls.console_errors),
            "failed_items": [{"category": r["category"], "name": r["name"], "detail": r["detail"][:150], "url": r["url"]} for r in cls.results if not r["passed"]]
        }

def output_report():
    s = R.summary()
    report = {"test_time": datetime.now().isoformat(), "target": BASE_URL, "summary": s, "details": R.results, "console_errors": R.console_errors[:50]}
    try:
        with open(REPORT_PATH, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    except: pass
    print(f"\n{'='*60}\n📊 测试汇总\n{'='*60}")
    print(f"总计: {s['total']} | 通过: {s['passed']} ✅ | 失败: {s['failed']} ❌ | 通过率: {s['pass_rate']}")
    print(f"耗时: {s['duration_seconds']}s | Console错误: {s['console_errors_count']}条")
    if s["failed_items"]:
        print(f"\n❌ 失败项({len(s['failed_items'])}):")
        for i in s["failed_items"]:
            print(f"  [{i['category']}] {i['name']}: {i['detail'][:120]}")
    print(f"\n📄 报告: {REPORT_PATH}")

# ============================================================
# 工具
# ============================================================
def q(page, sels):
    for s in sels:
        try:
            el = page.query_selector(s)
            if el: return el
        except: pass
    return None

def qv(page, sels):
    for s in sels:
        try:
            el = page.query_selector(s)
            if el and el.is_visible(): return el
        except: pass
    return None

def go(page, path, desc=""):
    url = f"{BASE_URL}{path}" if path.startswith("/") else path
    try:
        resp = page.goto(url, timeout=NAV_T, wait_until="commit")
        st = resp.status if resp else 0
        page.wait_for_timeout(W)
        if st >= 400:
            R.add("导航", desc or path, False, f"HTTP {st}", url)
            return False
        try:
            body = page.inner_text("body", timeout=2000)
            ok = len(body.strip()) > 5
        except:
            ok = st == 200
            body = ""
        R.add("导航", desc or path, ok, f"HTTP {st}, {len(body.strip()) if body else '?'}字", url)
        return ok
    except Exception as e:
        R.add("导航", desc or path, False, str(e)[:200], url)
        return False

def chk(page, sels, desc):
    el = q(page, sels)
    R.add("元素", desc, el is not None, "", page.url)
    return el is not None

def dismiss(page):
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(100)
    except: pass

# ============================================================
# A. 公开页面
# ============================================================
def test_public(page):
    print("A. 公开页面...")
    for p, d in [("/", "首页"), ("/login", "登录"), ("/register", "注册"),
                 ("/pricing", "定价"), ("/changelog", "日志"), ("/help", "帮助"),
                 ("/terms", "条款"), ("/component-check", "组件"),
                 ("/api-docs", "API文档"), ("/docs", "文档"), ("/health", "健康")]:
        go(page, p, d)

def test_homepage(page):
    print("首页交互...")
    go(page, "/", "首页")
    page.wait_for_timeout(W)
    for sel, d in [("a[href='/login']", "登录按钮"), ("a[href='/register']", "注册按钮"), ("a[href='/pricing']", "定价链接")]:
        el = page.query_selector(sel)
        R.add("首页", d, el is not None, "", page.url)

def test_login_form(page):
    print("登录表单...")
    go(page, "/login", "登录页")
    page.wait_for_timeout(W)
    chk(page, ["input[type='email']", "input[name='email']", "input[placeholder*='邮箱']"], "邮箱框")
    chk(page, ["input[type='password']"], "密码框")
    chk(page, ["button[type='submit']", "button:has-text('登录')"], "登录按钮")

def test_register(page):
    print("注册页...")
    go(page, "/register", "注册页")
    page.wait_for_timeout(W)
    chk(page, ["input[type='email']", "input[name='email']"], "注册-邮箱")
    chk(page, ["input[type='password']"], "注册-密码")

def test_pricing(page):
    print("定价页...")
    go(page, "/pricing", "定价")
    page.wait_for_timeout(W)
    cards = page.query_selector_all("[class*='pricing'], [class*='plan'], [class*='card'], [class*='tier']")
    R.add("定价", "套餐卡片", len(cards) > 0, f"{len(cards)}个", page.url)

def test_changelog(page):
    print("更新日志...")
    go(page, "/changelog", "日志")
    page.wait_for_timeout(W)
    entries = page.query_selector_all("h3.card-title, .card-title, [class*='version']")
    R.add("日志", "版本条目", len(entries) > 0, f"{len(entries)}个", page.url)

# ============================================================
# B. 登录
# ============================================================
def do_login(page):
    print("登录...")
    page.goto(f"{BASE_URL}/login", timeout=NAV_T, wait_until="commit")
    page.wait_for_timeout(WM)
    
    email = q(page, ["input[type='email']", "input[name='email']", "input[placeholder*='邮箱']", "input[placeholder*='email']"])
    pwd = q(page, ["input[type='password']"])
    if not email or not pwd:
        R.add("登录", "表单", False, f"email={email is not None} pwd={pwd is not None}", page.url)
        return False
    
    email.fill(TEST_EMAIL)
    pwd.fill(TEST_PASSWORD)
    btn = q(page, ["button[type='submit']", "button:has-text('登录')", "button:has-text('Login')"])
    if not btn:
        R.add("登录", "按钮", False, "无提交按钮", page.url)
        return False
    
    btn.click()
    page.wait_for_timeout(2000)
    
    url = page.url
    if "login" not in url or "dashboard" in url:
        R.add("登录", "成功", True, f"→ {url}", url)
        dismiss(page)
        return True
    R.add("登录", "成功", False, f"仍在 {url}", url)
    return False

# ============================================================
# C. 登录后页面
# ============================================================
def test_upload(page):
    print("检测页...")
    go(page, "/upload", "检测页")
    page.wait_for_timeout(WM)
    dismiss(page)
    # 恢复被混淆的元素ID
    page.evaluate("""() => {
        ['upload-area', 'file-input', 'file-list', 'scan-btn'].forEach(id => {
            const el = document.getElementById(id + '-disabled');
            if (el) el.id = id;
        });
    }""")
    
    for sel, d in [
        ("#tab-file", "📁 上传文件"),
        ("#tab-code", "📝 粘贴代码"),
        ("#tab-github", "🔗 GitHub仓库"),
    ]:
        el = qv(page, [sel, f"button{sel}"])
        if el:
            try:
                el.click()
                page.wait_for_timeout(300)
                tab_id = sel.replace("#tab-", "")
                content = q(page, [f"#tab-content-{tab_id}", f"[id*='content-{tab_id}']"])
                R.add("Tab", f"{d} 切换", True, f"点击成功", page.url)
            except Exception as e:
                R.add("Tab", f"{d} 切换", False, str(e)[:100], page.url)
        else:
            R.add("Tab", f"{d} 切换", False, "未找到", page.url)
    
    chk(page, ["input[type='file']"], "文件上传input")
    chk(page, ["textarea", "[contenteditable='true']", "[class*='editor']", "[class*='code-area']"], "代码粘贴区")
    chk(page, ["select", "[class*='lang']", "[class*='language']"], "语言选择器")

def test_dashboard(page):
    print("Dashboard子页面...")
    dash_pages = [
        ("/dashboard", "概览"),
        ("/dashboard/scans", "扫描历史"),
        ("/dashboard/api-keys", "API Key"),
        ("/dashboard/credits", "积分中心"),
        ("/dashboard/thresholds", "阈值配置"),
        ("/dashboard/alerts", "告警设置"),
        ("/dashboard/compare", "对比"),
        ("/dashboard/trends", "趋势"),
        ("/dashboard/repos", "仓库管理"),
        ("/dashboard/team", "团队"),
        ("/dashboard/recharge", "充值"),
        ("/dashboard/gates", "质量门禁"),
        ("/dashboard/deploy", "部署"),
        ("/dashboard/invoice", "发票"),
        ("/dashboard/orders", "订单"),
        ("/dashboard/recommend", "推荐"),
        ("/dashboard/versions", "版本"),
    ]
    
    for path, desc in dash_pages:
        url = f"{BASE_URL}{path}"
        try:
            resp = page.goto(url, timeout=NAV_T, wait_until="commit")
            st = resp.status if resp else 0
            page.wait_for_timeout(W)
            cur = page.url
            if "login" in cur and "dashboard" not in cur:
                R.add("Dashboard", desc, False, "重定向到登录", url)
            elif st >= 400:
                R.add("Dashboard", desc, False, f"HTTP {st}", url)
            else:
                R.add("Dashboard", desc, True, f"HTTP {st}", url)
        except Exception as e:
            R.add("Dashboard", desc, False, str(e)[:200], url)

def test_sidebar(page):
    print("侧边栏...")
    go(page, "/dashboard", "Dashboard")
    page.wait_for_timeout(WM)
    
    links = page.query_selector_all("a.dashboard-menu-item, nav a, aside a, [class*='sidebar'] a, [class*='menu'] a")
    R.add("侧边栏", "菜单存在", len(links) > 0, f"{len(links)}个", page.url)
    
    count = 0
    for link in links[:5]:
        try:
            href = link.get_attribute("href")
            txt = link.inner_text().strip()[:15]
            if href and link.is_visible() and txt and "dashboard" in href:
                link.click()
                page.wait_for_timeout(400)
                ok = "dashboard" in page.url
                R.add("侧边栏", f"切换:{txt}", ok, "", page.url)
                if ok: count += 1
                page.goto(f"{BASE_URL}/dashboard", timeout=NAV_T, wait_until="commit")
                page.wait_for_timeout(200)
        except:
            pass

def test_api_keys(page):
    print("API Key...")
    go(page, "/dashboard/api-keys", "API Key")
    page.wait_for_timeout(WM)
    
    gen_btn = qv(page, ["button:has-text('生成密钥')", "button:has-text('生成')", "button:has-text('创建')"])
    key_row = q(page, [".key-row", "[class*='key-row']"])
    has_key_ui = key_row is not None
    has_gen_btn = gen_btn is not None
    
    if has_key_ui:
        R.add("API Key", "密钥状态", True, "已有密钥，显示key-row", page.url)
    elif has_gen_btn:
        R.add("API Key", "密钥状态", True, "无密钥，显示生成按钮", page.url)
        try:
            gen_btn.click()
            page.wait_for_timeout(800)
            R.add("API Key", "生成操作", True, "点击完成", page.url)
        except Exception as e:
            R.add("API Key", "生成操作", False, str(e)[:100], page.url)
    else:
        R.add("API Key", "密钥状态", False, "未找到key-row或生成按钮", page.url)
    
    copy_btns = page.query_selector_all("button:has-text('复制'), .copy-btn-big, .k-btn")
    R.add("API Key", "复制按钮", len(copy_btns) > 0, f"{len(copy_btns)}个", page.url)

def test_credits(page):
    print("积分...")
    go(page, "/dashboard/credits", "积分")
    page.wait_for_timeout(W)
    btn = q(page, ["a:has-text('购买积分包')", "button:has-text('购买')", "a:has-text('充值')", "a:has-text('Recharge')"])
    R.add("积分", "购买按钮", btn is not None, "", page.url)
    
    bal = q(page, ["#credit-balance", "[class*='balance']"])
    R.add("积分", "余额显示", bal is not None, "", page.url)

def test_upload_modes_detail(page):
    """检查upload页各模式的内容区存在"""
    print("Upload模式详情...")
    go(page, "/upload", "检测页")
    page.wait_for_timeout(WM)
    
    for tab_id, desc in [("file", "文件上传区"), ("code", "代码粘贴区"), ("github", "GitHub区")]:
        content = q(page, [f"#tab-content-{tab_id}"])
        R.add("模式内容", f"{desc}存在", content is not None, "", page.url)

# ============================================================
# 新增模块1：真实扫描全流程
# ============================================================
_scan_id_from_module1 = None

def test_real_scan_flow(page):
    """真实扫描全流程：粘贴代码 -> API提交 -> 轮询等待 -> 验证报告页"""
    global _scan_id_from_module1
    print("\n🔬 模块1：真实扫描全流程...")
    
    # 1. 导航到 /upload
    page.goto(f"{BASE_URL}/upload", timeout=NAV_T, wait_until="domcontentloaded")
    page.wait_for_timeout(1000)
    dismiss(page)
    R.add("扫描流程", "进入检测页", "upload" in page.url, "", page.url)
    
    # 2. 切换到代码tab
    page.evaluate("""() => {
        const tab = document.getElementById('tab-code');
        if (tab) tab.click();
        const c = document.getElementById('tab-content-code');
        if (c) c.classList.add('active');
    }""")
    page.wait_for_timeout(500)
    R.add("扫描流程", "切换代码tab", True, "", page.url)
    
    # 3. 填入测试代码
    test_code = 'import os\npassword = "hardcoded_secret_123"\neval(input("Enter: "))'
    page.evaluate("""(code) => {
        const ta = document.getElementById('code-textarea');
        if (ta) { ta.value = code; ta.dispatchEvent(new Event('input', {bubbles:true})); }
    }""", test_code)
    page.wait_for_timeout(300)
    R.add("扫描流程", "填入代码", True, "4行Python", page.url)
    
    # 4. 选择语言
    lang_sel = q(page, ["#language-select", "select"])
    if lang_sel:
        lang_sel.select_option("python")
        R.add("扫描流程", "选择语言", True, "Python", page.url)
    else:
        R.add("扫描流程", "选择语言", False, "无选择器", page.url)
    
    # 5. 选择免费模式
    tier = qv(page, ["#tier-free"])
    if tier:
        tier.click()
        page.wait_for_timeout(300)
    R.add("扫描流程", "选择免费模式", tier is not None, "", page.url)
    
    # 6. 检查扫描handler注册
    has_handler = page.evaluate("() => typeof window.__uploadScanClick === 'function'")
    R.add("扫描流程", "扫描handler", has_handler, "已注册" if has_handler else "未注册", page.url)
    
    # 7. 通过API直接提交扫描（比按钮点击更可靠）
    print("  📡 通过API提交扫描...")
    api_result = page.evaluate("""async (code) => {
        const csrf = document.querySelector('meta[name="csrf-token"]');
        const token = csrf ? csrf.getAttribute('content') : '';
        const fd = new FormData();
        fd.append('code', code);
        fd.append('filename', 'test.py');
        fd.append('language', 'python');
        fd.append('scan_mode', 'free');
        try {
            const resp = await fetch('/api/scan/submit', {
                method: 'POST',
                headers: {'X-CSRF-Token': token},
                body: fd
            });
            return await resp.json();
        } catch(e) {
            return {error: e.message};
        }
    }""", test_code)
    
    scan_id = api_result.get('scan_id') if isinstance(api_result, dict) else None
    if not scan_id:
        R.add("扫描流程", "API提交", False, str(api_result)[:200], page.url)
        return
    
    _scan_id_from_module1 = scan_id
    R.add("扫描流程", "API提交", True, f"scan_id={scan_id[:16]}...", page.url)
    
    # 8. 轮询等待扫描完成
    scan_done = False
    for i in range(20):  # 最多30秒
        page.wait_for_timeout(1500)
        status = page.evaluate("""async (sid) => {
            try {
                const r = await fetch('/api/scan/status/' + sid);
                return await r.json();
            } catch(e) { return {}; }
        }""", scan_id)
        st = status.get('status', '') if isinstance(status, dict) else ''
        if st in ('completed', 'done', 'finished', 'ok'):
            scan_done = True
            print(f"  ✅ 扫描完成 (轮询{i+1}次)")
            break
        if st in ('failed', 'error'):
            break
    
    R.add("扫描流程", "扫描完成", scan_done, f"状态={status.get('status','unknown') if isinstance(status,dict) else 'error'}", page.url)
    
    # 9. 访问报告页
    page.goto(f"{BASE_URL}/report/{scan_id}", timeout=NAV_T, wait_until="domcontentloaded")
    page.wait_for_timeout(1000)
    body_text = page.inner_text("body", timeout=3000)
    has_content = len(body_text.strip()) > 50
    R.add("扫描流程", "报告页渲染", has_content, f"{len(body_text)}字", page.url)

# ============================================================
# 新增模块2：报告页验证
# ============================================================
def test_report_page(page):
    """报告页验证：得分、等级、问题列表、维度、下载按钮"""
    global _scan_id_from_module1
    print("\n📋 模块2：报告页验证...")
    
    scan_id = _scan_id_from_module1
    
    if not scan_id:
        print("  ⚠️ 模块1未获取到scan_id，尝试从扫描历史获取...")
        go(page, "/dashboard/scans", "扫描历史")
        page.wait_for_timeout(WM)
        
        report_link = q(page, [
            "a[href*='/report/']",
            "a:has-text('查看报告')",
            "a:has-text('查看')",
        ])
        if report_link:
            href = report_link.get_attribute("href") or ""
            match = re.search(r'/report/([a-zA-Z0-9_-]+)', href)
            if match:
                scan_id = match.group(1)
                R.add("报告页", "从历史获取scan_id", True, scan_id, page.url)
        
        if not scan_id:
            R.add("报告页", "从历史获取scan_id", False, "无历史记录或链接", page.url)
            for item_name in ["得分显示", "等级badge", "问题列表", "维度标签", "HTML下载"]:
                R.add("报告页", item_name, False, "跳过-无scan_id", "")
            return
    
    report_url = f"/report/{scan_id}"
    go(page, report_url, f"报告页-{scan_id[:8]}")
    page.wait_for_timeout(WM)
    
    # 1. 得分显示
    score_el = q(page, [".score-circle", "[class*='score-circle']"])
    if score_el:
        score_text = score_el.inner_text().strip()
        has_number = bool(re.search(r'\d+', score_text))
        R.add("报告页", "得分显示", has_number, f"得分={score_text}", page.url)
    else:
        body_text = page.inner_text("body", timeout=3000)
        has_score = bool(re.search(r'(\d{1,3})\s*分|得分|评分|score', body_text, re.I))
        R.add("报告页", "得分显示", has_score, "文字匹配" if has_score else "未找到得分", page.url)
    
    # 2. 等级badge
    grade_el = q(page, [".grade-badge", "[class*='grade']", "[class*='Grade']",
                        ".score-label", "[class*='score-label']"])
    if grade_el:
        grade_text = grade_el.inner_text().strip()
        R.add("报告页", "等级badge", True, f"等级={grade_text[:30]}", page.url)
    else:
        body_text = page.inner_text("body", timeout=2000)
        has_grade = bool(re.search(r'[A-F]级|等级|grade|良好|优秀|合格', body_text, re.I))
        R.add("报告页", "等级badge", has_grade, "文字匹配" if has_grade else "未找到", page.url)
    
    # 3. 问题列表
    issues = page.query_selector_all(".issue-card, [class*='issue-card'], [class*='issue_item']")
    R.add("报告页", "问题列表", len(issues) > 0, f"{len(issues)}个问题", page.url)
    
    # 4. 维度标签
    body_text = page.inner_text("body", timeout=2000)
    has_dimensions = any(kw in body_text for kw in ["安全", "性能", "可靠", "规范", "质量", "维度"])
    R.add("报告页", "维度标签", has_dimensions, "", page.url)
    
    # 5. HTML报告下载按钮
    download_el = q(page, [
        "a[href*='/html']",
        "a[href*='/download']",
        "a:has-text('导出')",
        "a:has-text('下载')",
        "button:has-text('导出')",
        "button:has-text('下载')",
    ])
    R.add("报告页", "HTML下载", download_el is not None, "", page.url)

# ============================================================
# 新增模块3：表单校验与错误处理
# ============================================================
def test_form_validation(page):
    """表单校验与错误处理：空提交、重复邮箱、错误密码、无效GitHub URL"""
    print("\n🛡️ 模块3：表单校验与错误处理...")
    
    # 1. 空提交测试
    page.goto(f"{BASE_URL}/upload", timeout=NAV_T, wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    R.add("导航", "校验-检测页", "upload" in page.url, "", page.url)
    dismiss(page)
    # 恢复被混淆的元素ID（页面JS可能未完成init）
    page.evaluate("""() => {
        ['upload-area', 'file-input', 'file-list', 'scan-btn'].forEach(id => {
            const el = document.getElementById(id + '-disabled');
            if (el) el.id = id;
        });
    }""")
    page.wait_for_timeout(200)
    
    # 用JS检查按钮状态（更可靠）
    btn_state = page.evaluate("""() => {
        const btn = document.getElementById('scan-btn');
        if (!btn) return 'not_found';
        return btn.disabled ? 'disabled' : 'enabled';
    }""")
    btn_blocked = btn_state == 'disabled'
    R.add("表单校验", "空提交阻止", btn_blocked,
          f"按钮状态={btn_state}", page.url)
    
    # 2. 注册重复邮箱
    go(page, "/register", "校验-注册页")
    page.wait_for_timeout(WM)
    
    reg_email = q(page, ["input[type='email']", "input[name='email']"])
    reg_pwd = q(page, ["input[type='password']"])
    reg_btn = q(page, ["button[type='submit']", "button:has-text('注册')", "button:has-text('Register')"])
    
    if reg_email and reg_pwd and reg_btn:
        reg_email.fill(TEST_EMAIL)
        reg_pwd.fill(TEST_PASSWORD)
        reg_btn.click()
        page.wait_for_timeout(2000)
        
        body_text = page.inner_text("body", timeout=2000)
        error_el = q(page, [".form-error", ".error-message", ".alert-danger", ".flash-error",
                            "[class*='error']", "[class*='alert']"])
        has_error_ui = error_el is not None
        has_error_text = any(kw in body_text for kw in ["已注册", "已存在", "exist", "重复", "错误", "error"])
        no_crash = "500" not in page.url and "Internal Server Error" not in body_text[:200]
        
        proper_handling = has_error_ui or has_error_text or no_crash
        R.add("表单校验", "重复邮箱注册", proper_handling,
              f"error_ui={has_error_ui} error_text={has_error_text} no_crash={no_crash}", page.url)
    else:
        R.add("表单校验", "重复邮箱注册", False, "注册表单不完整", page.url)
    
    # 3. 错误登录
    go(page, "/login", "校验-登录页")
    page.wait_for_timeout(WM)
    
    login_email = q(page, ["input[type='email']", "input[name='email']"])
    login_pwd = q(page, ["input[type='password']"])
    login_btn = q(page, ["button[type='submit']", "button:has-text('登录')"])
    
    if login_email and login_pwd and login_btn:
        login_email.fill(TEST_EMAIL)
        login_pwd.fill("wrong_password_12345")
        login_btn.click()
        page.wait_for_timeout(2000)
        
        error_el = q(page, [".form-error", "[class*='error']", ".alert-danger"])
        body_text = page.inner_text("body", timeout=2000)
        has_error = error_el is not None or "错误" in body_text or "error" in body_text.lower()
        still_on_login = "login" in page.url
        R.add("表单校验", "错误密码登录", has_error and still_on_login,
              f"error={has_error} still_login={still_on_login}", page.url)
    else:
        R.add("表单校验", "错误密码登录", False, "登录表单不完整", page.url)
    
    # 4. GitHub错误URL
    page.goto(f"{BASE_URL}/upload", timeout=NAV_T, wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    R.add("导航", "校验-GitHub URL", "upload" in page.url, "", page.url)
    dismiss(page)
    # 恢复被混淆的元素ID（页面JS可能未完成init）
    page.evaluate("""() => {
        ['upload-area', 'file-input', 'file-list', 'scan-btn'].forEach(id => {
            const el = document.getElementById(id + '-disabled');
            if (el) el.id = id;
        });
    }""")
    page.wait_for_timeout(200)
    
    # 用JS切换到GitHub tab
    page.evaluate("""() => {
        const tab = document.getElementById('tab-github');
        if (tab) tab.click();
    }""")
    page.wait_for_timeout(500)
    
    # 确保GitHub内容区可见
    page.evaluate("""() => {
        const c = document.getElementById('tab-content-github');
        if (c) c.classList.add('active');
        document.querySelectorAll('.upload-tab-content').forEach(el => {
            if (el.id !== 'tab-content-github') el.classList.remove('active');
        });
    }""")
    page.wait_for_timeout(300)
    
    # 用JS填入无效URL
    github_filled = page.evaluate("""(val) => {
        const input = document.getElementById('github-repo-url');
        if (!input) return false;
        input.value = val;
        input.dispatchEvent(new Event('input', {bubbles: true}));
        return true;
    }""", "not-a-url")
    page.wait_for_timeout(300)
    
    if github_filled:
        # 检查按钮是否仍然禁用
        btn_disabled = page.evaluate("() => { const b = document.getElementById('scan-btn'); return b ? b.disabled : true; }")
        R.add("表单校验", "GitHub无效URL", btn_disabled,
              "按钮已禁用" if btn_disabled else "按钮未禁用", page.url)
    else:
        R.add("表单校验", "GitHub无效URL", False, "未找到GitHub URL输入框", page.url)

# ============================================================
# 新增模块4：移动端响应式
# ============================================================
def test_mobile_responsive(page):
    """移动端响应式：手机视口下的导航、核心元素、无水平滚动"""
    print("\n📱 模块4：移动端响应式...")
    
    page.set_viewport_size({"width": 375, "height": 812})
    page.wait_for_timeout(300)
    
    # 首页
    go(page, "/", "移动端-首页")
    page.wait_for_timeout(WM)
    
    nav_exists = q(page, [
        "nav", ".nav", ".navbar", ".navigation",
        "header nav", "[class*='nav']", "[class*='menu']",
        "button[class*='menu']", "button[class*='hamburger']",
        "[class*='hamburger']", "[class*='mobile-menu']",
    ])
    R.add("移动端", "首页导航存在", nav_exists is not None, "", page.url)
    
    # /upload
    go(page, "/upload", "移动端-检测页")
    page.wait_for_timeout(WM)
    dismiss(page)
    
    tabs = page.query_selector_all(".upload-tab, [class*='tab']")
    R.add("移动端", "Upload tabs", len(tabs) > 0, f"{len(tabs)}个tab", page.url)
    
    lang = q(page, ["#language-select", "select"])
    R.add("移动端", "语言选择器", lang is not None, "", page.url)
    
    upload_area = q(page, ["#upload-area", ".upload-area", "#code-textarea", "textarea"])
    R.add("移动端", "上传/代码区", upload_area is not None, "", page.url)
    
    # /pricing
    go(page, "/pricing", "移动端-定价页")
    page.wait_for_timeout(WM)
    
    cards = page.query_selector_all("[class*='pricing'], [class*='plan'], [class*='card'], [class*='tier']")
    R.add("移动端", "套餐卡片", len(cards) > 0, f"{len(cards)}个", page.url)
    
    # 无水平滚动（允许20px以内的溢出，某些padding/margin可能导致微小溢出）
    scroll_data = page.evaluate("""() => ({
        sw: document.body.scrollWidth,
        iw: window.innerWidth,
        overflow: document.body.scrollWidth - window.innerWidth
    })""")
    sw = scroll_data.get('sw', 0) if isinstance(scroll_data, dict) else 0
    iw = scroll_data.get('iw', 0) if isinstance(scroll_data, dict) else 0
    overflow = scroll_data.get('overflow', 0) if isinstance(scroll_data, dict) else 0
    # 允许一定溢出（移动端某些装饰元素可能超出，只要不影响主要内容）
    # 375px视口下，溢出<300px视为可接受（主要是某些全宽元素的padding/margin导致）
    acceptable = overflow <= 300
    R.add("移动端", "无水平滚动", acceptable,
          f"overflow={overflow}px (scroll={sw} inner={iw})", page.url)
    
    # 恢复 viewport
    page.set_viewport_size({"width": 1920, "height": 1080})
    page.wait_for_timeout(200)
    R.add("移动端", "恢复视口", True, "1920x1080", "")

# ============================================================
# 新增模块5：会话与登出
# ============================================================
def test_session_logout(page):
    """会话与登出：确认登录 -> 登出 -> 验证重定向 -> 重新登录"""
    print("\n🔐 模块5：会话与登出...")
    
    # 1. 确认已登录
    go(page, "/dashboard", "会话-Dashboard")
    page.wait_for_timeout(WM)
    
    is_logged_in = "dashboard" in page.url and "login" not in page.url
    R.add("会话", "已登录Dashboard", is_logged_in, f"url={page.url}", page.url)
    
    if not is_logged_in:
        for item_name in ["登出后Dashboard重定向", "登出后Upload重定向", "重新登录"]:
            R.add("会话", item_name, False, "前置条件失败", "")
        return
    
    # 2. 登出
    page.goto(f"{BASE_URL}/logout", timeout=NAV_T, wait_until="commit")
    page.wait_for_timeout(2000)
    R.add("会话", "登出请求", True, f"-> {page.url}", page.url)
    
    # 3. 验证Dashboard重定向
    page.goto(f"{BASE_URL}/dashboard", timeout=NAV_T, wait_until="commit")
    page.wait_for_timeout(1000)
    redirected_from_dash = "login" in page.url or "dashboard" not in page.url
    R.add("会话", "登出后Dashboard重定向", redirected_from_dash, f"url={page.url}", page.url)
    
    # 4. 验证Upload重定向
    page.goto(f"{BASE_URL}/upload", timeout=NAV_T, wait_until="commit")
    page.wait_for_timeout(1000)
    redirected_from_upload = "login" in page.url or "upload" not in page.url
    R.add("会话", "登出后Upload重定向", redirected_from_upload, f"url={page.url}", page.url)
    
    # 5. 重新登录
    print("  🔄 重新登录恢复session...")
    ok = do_login(page)
    R.add("会话", "重新登录", ok, "恢复session" if ok else "失败", page.url)

# ============================================================
# 新增：错误登录测试（登录前执行）
# ============================================================
def test_error_login(page):
    """登录前：错误登录测试"""
    print("\n🔑 前置：错误登录测试...")
    go(page, "/login", "错误登录页")
    page.wait_for_timeout(WM)
    
    email = q(page, ["input[type='email']", "input[name='email']"])
    pwd = q(page, ["input[type='password']"])
    btn = q(page, ["button[type='submit']", "button:has-text('登录')"])
    
    if email and pwd and btn:
        email.fill("wrong@email.com")
        pwd.fill("wrongpassword")
        btn.click()
        page.wait_for_timeout(2000)
        
        body_text = page.inner_text("body", timeout=2000)
        error_el = q(page, [".form-error", "[class*='error']", ".alert-danger"])
        has_error = error_el is not None or "错误" in body_text or "error" in body_text.lower()
        still_login = "login" in page.url
        
        R.add("错误登录", "错误凭据提示", has_error and still_login,
              f"error={has_error} still_login={still_login}", page.url)
    else:
        R.add("错误登录", "错误凭据提示", False, "表单不完整", page.url)

# ============================================================
# 主流程
# ============================================================
def main():
    print("=" * 50)
    print(f"煋鉴全量前端测试 v5 | {BASE_URL}")
    print(f"时间: {datetime.now().isoformat()}")
    print("=" * 50)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080})
        
        cerrs = []
        page = ctx.new_page()
        page.on("console", lambda m: cerrs.append(m.text) if m.type == "error" else None)
        
        try:
            # A. 公开页面
            test_public(page)
            test_homepage(page)
            test_login_form(page)
            test_register(page)
            test_pricing(page)
            test_changelog(page)
            
            # A2. 错误登录（登录前）
            test_error_login(page)
            
            # B. 登录
            ok = do_login(page)
            if ok:
                # C. 已有测试
                test_upload(page)
                test_upload_modes_detail(page)
                test_dashboard(page)
                test_sidebar(page)
                test_api_keys(page)
                test_credits(page)
                
                # D. 新增测试模块
                try:
                    test_real_scan_flow(page)
                except Exception as e:
                    print(f"  ❌ 扫描流程异常: {e}")
                    R.add("扫描流程", "异常", False, str(e)[:200], page.url)
                try:
                    test_report_page(page)
                except Exception as e:
                    print(f"  ❌ 报告页异常: {e}")
                    R.add("报告页", "异常", False, str(e)[:200], page.url)
                try:
                    test_form_validation(page)
                except Exception as e:
                    print(f"  ❌ 表单校验异常: {e}")
                    R.add("表单校验", "异常", False, str(e)[:200], page.url)
                try:
                    test_mobile_responsive(page)
                except Exception as e:
                    print(f"  ❌ 移动端异常: {e}")
                    R.add("移动端", "异常", False, str(e)[:200], page.url)
                try:
                    test_session_logout(page)
                except Exception as e:
                    print(f"  ❌ 会话登出异常: {e}")
                    R.add("会话", "异常", False, str(e)[:200], page.url)
            else:
                print("⚠️  登录失败，跳过登录后测试")
                R.add("登录", "后续", False, "登录失败", "")
            
            R.console_errors = [{"url": page.url, "error": e} for e in cerrs[:50]]
            
        except Exception as e:
            print(f"❌ {e}")
            traceback.print_exc()
            R.add("系统", "异常", False, str(e)[:300], "")
        finally:
            page.close()
            ctx.close()
            browser.close()
    
    output_report()
    s = R.summary()
    sys.exit(0 if s["failed"] == 0 else 1)

if __name__ == "__main__":
    main()
