"""官网站点元素一致性守卫（2026-11-08，QA 6h）。

治本思路：
1. 单一事实来源 scripts/site_nav.json —— 全站核心导航清单；
2. 反馈闭环 —— 逐页核对、每条链接真发请求、真浏览器匿名态验证；
3. 造坏自检 —— 每项检查都得有能判红的坏副本，藏守卫或写死结果一律不让过。

检查项：
 S1  清单存在且 core 格式正确
 S2  四处导航（首页 / 内页母版 / 产品页 / 关于页）都含 core 全部链接
 S3  core 每条链接真发 HTTP 请求，404/5xx 一律判红
 S4  对外语言数唯一（23），不许再出现 17 种之类旧值
 S5  装饰色消费方冷色化（含 .kicker 小字、.brand-logo 这类易漏处）
 S6  首页数字条 .stat 个数 == 栅格列数（防第四项被挤到第二屏）
 S7  推荐有礼横幅只对已登录用户渲染（模板 + 真浏览器匿名态）
 S8  全站交付文件（6j 指纹守卫同一口径）属主必须是服务身份
 S9  两页独立页不再出现 /pages/pricing.html 死链
 S10 真浏览器匿名态逐页导航含齐 core

用法:
  python3 verify_site_consistency.py [--root SITE] [--base-url URL]
  python3 verify_site_consistency.py --self-test
"""
import argparse
import colorsys
import glob
import json
import os
import re
import shutil
import ssl
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

try:
    import grp
    import pwd
except ImportError:  # 本地 Windows 只做语法检查；生产 Linux 必有
    grp = pwd = None

DEFAULT_ROOT = "/opt/xinpect-website"
DEFAULT_BASE = "https://xinpect.xingwangzhineng.com"
SERVICE_OWNER = "xinpect-web"
# 守卫自己持有最小核心集：防止有人「改清单删掉一条」让守卫不检查那条而假绿。
# 清单可以加链接，但一条都不能少；加进来的链接一样要真请求、逐页出现。
REQUIRED_HREFS = ["/", "/pages/product.html", "/pricing", "/try",
                  "/help", "/pages/about.html", "/blog"]

# 提醒类语义：报错 / 警告 / 老用户补偿公告属于「提醒」，不是装饰，按语义放行。
# 不写死文件名、不写死某个色值，判据是这一行的语义。
REMINDER_WORDS = re.compile(
    r"error|danger|warning|alert|compensation|invalid|failed|提醒|报错|错误|警告|补偿",
    re.I)
WARM_VAR = re.compile(r"var\(--color-v-([0-9a-fA-F]{6})\)")
WARM_HEX = re.compile(r"#([0-9a-fA-F]{6})\b")
LANG_NUM = re.compile(r"(\d+)\s*种(?:主流)?(?:编程)?语言")


def find_chromium():
    env = os.environ.get("XP_CHROMIUM")
    if env and Path(env).is_file():
        return env
    cands = sorted(glob.glob("/home/ubuntu/.cache/ms-playwright/chromium-*/chrome-linux64/chrome"))
    cands += sorted(glob.glob("/root/.cache/ms-playwright/chromium-*/chrome-linux64/chrome"))
    return cands[-1] if cands else None


def import_playwright():
    """QA 以 root 跑时，用户级 playwright 不在 sys.path；找不到必须判红。"""
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        pass
    for pat in ("/home/ubuntu/.local/lib/python3.*/site-packages",
                "/usr/local/lib/python3.*/dist-packages"):
        for hit in glob.glob(pat):
            if hit not in sys.path:
                sys.path.insert(0, hit)
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        return None


def is_warm(hexstr):
    """从颜色本身算色相：红橙黄（0–70°）且饱和度够，判暖色。不是色值白名单。"""
    try:
        r, g, b = (int(hexstr[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return False
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    deg = h * 360
    return (deg <= 70 or deg >= 345) and s >= 0.30 and v >= 0.35


def load_palette(root):
    """从唯一色板解析变量名 -> 真实色值，语义变量（--color-cool-*）也认。"""
    t = read(root, "static/css/tokens.css") or ""
    out = {}
    for name, val in re.findall(r"(--[a-zA-Z0-9-]+)\s*:\s*([^;]+);", t):
        hx = WARM_HEX.search(val)
        if hx:
            out[name] = hx.group(1)
    return out


def resolve_color(val, palette):
    """把一段 CSS 颜色声明解析成 6 位 hex；解析不出来返回 None。"""
    v = re.search(r"var\(\s*(--[a-zA-Z0-9-]+)", val)
    if v:
        name = v.group(1)
        if name in palette:
            return palette[name]
        m = re.match(r"--color-v-([0-9a-fA-F]{6})$", name)
        return m.group(1) if m else None
    hx = WARM_HEX.search(val)
    return hx.group(1) if hx else None


def read(root, rel):
    p = Path(root) / rel
    if not p.is_file():
        return None
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def core_list(root):
    raw = read(root, "scripts/site_nav.json")
    if raw is None:
        # 缺清单也要继续跑其它检查，不许只报一条就收工
        return ([{"label": "?", "href": h} for h in REQUIRED_HREFS],
                ["S1 缺 scripts/site_nav.json（导航单一事实来源）"])
    errs = []
    try:
        cfg = json.loads(raw)
        core = cfg["core"]
        assert isinstance(core, list) and core
        for it in core:
            assert set(it) == {"label", "href"} and it["href"].startswith("/")
    except Exception as e:
        return ([{"label": "?", "href": h} for h in REQUIRED_HREFS],
                [f"S1 清单格式错: {e}"])
    have = {it["href"] for it in core}
    missing = [h for h in REQUIRED_HREFS if h not in have]
    if missing:
        errs.append(f"S1 清单缺关键导航 {missing}（不许靠删清单蒙混过关）")
    return core, errs


# ---------------- 各检查项 ----------------

def check_nav_static(root, core):
    """导航块里必须包含清单里的全部核心链接。

    2026-11-22 改：导航已收成一份 templates/_nav.html，base.html 与 index.html
    都只写 {% include "_nav.html" %}，页面上没有字面量链接；而 _nav.html 又是
    按 site_nav.json 的 core 渲染的，文本里同样没有 href。所以判据要顺着这条链走：
      页面 include 了片段 → 片段的链接（如果片段是文本写死的）或清单本身（片段由
      JSON 渲染）都算这个页面的导航内容。
    渲染后的真检查由 check_http 与 tests/test_nav_single_source.py 负责。
    """
    errs = []
    partial = read(root, "templates/_nav.html") or ""
    partial_hrefs = set(re.findall(r'<a\s[^>]*href="([^"]+)"', partial))
    partial_from_json = "nav_core" in partial
    targets = {
        "templates/index.html": "</header>",
        "templates/base.html": "</nav>",
        "static/pages/product.html": "</header>",
        "static/pages/about.html": "</header>",
    }
    for rel, stop in targets.items():
        t = read(root, rel)
        if t is None:
            errs.append(f"S2 缺页面 {rel}")
            continue
        block = t.split(stop)[0]
        hrefs = set(re.findall(r'<a\s[^>]*href="([^"]+)"', block))
        if '{% include "_nav.html" %}' in t:
            hrefs |= partial_hrefs
            if partial_from_json:
                hrefs |= {it["href"] for it in core}
        for it in core:
            if it["href"] not in hrefs:
                errs.append(f"S2 {rel} 缺核心导航 {it['href']}（{it['label']}）")
    return errs


def check_http(core, base):
    errs = []
    ctx = ssl._create_unverified_context()
    for it in core:
        url = base.rstrip("/") + it["href"]
        try:
            req = urllib.request.Request(url, method="GET",
                                         headers={"User-Agent": "xp-consistency-guard/1.0"})
            with urllib.request.urlopen(req, timeout=12, context=ctx) as r:
                code = r.status
        except urllib.error.HTTPError as e:
            code = e.code
        except Exception as e:
            errs.append(f"S3 请求失败 {it['href']}: {type(e).__name__}")
            continue
        if code in (404, 410) or code >= 500:
            errs.append(f"S3 核心导航 {it['href']} 实测 HTTP {code}（访客点不开）")
    return errs


def check_lang_number(root):
    """只管「当前对外能力声明」。

    更新日志 / 版本档案天然是历史记录（里面 8/17/19/30 种是当时真实发生过的事，
    按用户红线不许改，只在正文里钉口径更新声明）；某个具体检测能力的覆盖语种
    是局部口径，也不该被当成全站语言数。这两类按语义跳过，不是按文件名开白名单。
    """
    errs = []
    found = set()
    history_page = re.compile(r"changelog|versions", re.I)
    local_capability = re.compile(r"新增|扩展|从\s*\d+\s*种|统一|数据流级|更新日志|"
                                  r"语法规则|SSRF|检测覆盖\s*\d+\s*种", re.I)

    def scan(where):
        for p in (Path(root) / where).rglob("*.html"):
            if history_page.search(p.name):
                continue
            try:
                t = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                errs.append(f"S4 读不了 {p.relative_to(root)}（权限/属主异常，不许静默跳过）")
                continue
            for line in t.splitlines():
                if local_capability.search(line):
                    continue
                for m in LANG_NUM.finditer(line):
                    found.add(m.group(1))
    scan("templates")
    scan("static/pages")
    if not found:
        errs.append("S4 全站找不到当前语言数声明（不许静默跳过）")
    bad = found - {"23"}
    if bad:
        errs.append(f"S4 当前能力声明出现多套语言口径 {sorted(found)}，对外只允许 23")
    return errs


def check_decor_warm(root):
    """装饰色消费方：按颜色本身算冷暖，按语义区分「提醒」与「装饰」。"""
    errs = []
    pal = load_palette(root)
    if not pal:
        errs.append("S5 色板 static/css/tokens.css 解析不出颜色（不许静默跳过）")
    home = read(root, "templates/index.html")
    if home is None:
        errs.append("S5 缺 templates/index.html")
    else:
        m = re.search(r"\.kicker\{[^}]*color:\s*([^;]+);", home)
        if not m:
            errs.append("S5 首页 .kicker 找不到 color 声明")
        else:
            hx = resolve_color(m.group(1), pal)
            if not hx:
                errs.append(f"S5 首页 .kicker 颜色解析不出色值: {m.group(1).strip()}")
            elif is_warm(hx):
                errs.append(f"S5 首页 .kicker 小字是暖色 #{hx}（装饰忌红橙土黄）")
    for rel in ("static/pages/product.html", "static/pages/about.html"):
        t = read(root, rel)
        if t is None:
            errs.append(f"S5 缺 {rel}")
            continue
        if "🔥" in t:
            errs.append(f"S5 {rel} 品牌位仍是火焰 emoji（暖色装饰）")
        blk = re.search(r"\.page-header\s+\.brand-logo\s*\{([^}]*)\}", t)
        if not blk or "color:" not in blk.group(1):
            errs.append(f"S5 {rel} 品牌方块没声明冷色")
        else:
            val = re.search(r"color:\s*([^;]+);", blk.group(1)).group(1)
            hx = resolve_color(val, pal)
            if not hx:
                errs.append(f"S5 {rel} 品牌方块颜色解析不出色值: {val.strip()}")
            elif is_warm(hx):
                errs.append(f"S5 {rel} 品牌方块是暖色 #{hx}")
    # 全站氛围层：所有直接写死的色值必须是冷色（提醒语义除外）
    fx = read(root, "static/css/cool-fx.css")
    if fx is None:
        errs.append("S5 缺唯一氛围层 static/css/cool-fx.css")
    else:
        for i, line in enumerate(fx.splitlines(), 1):
            if ":" not in line or REMINDER_WORDS.search(line):
                continue
            for hx in list(WARM_VAR.finditer(line)) + list(WARM_HEX.finditer(line)):
                if is_warm(hx.group(1)):
                    errs.append(f"S5 cool-fx.css:{i} 装饰用了暖色 #{hx.group(1)}")
    return errs


def check_stats_grid(root):
    t = read(root, "templates/index.html")
    if t is None:
        return ["S6 缺 templates/index.html"]
    n = t.count('<div class="stat">')
    m = re.search(r"\.stats-inner\{[^}]*grid-template-columns:\s*repeat\((\d+)", t)
    if not m:
        return ["S6 找不到 stats-inner 栅格列数"]
    cols = int(m.group(1))
    if n != cols:
        return [f"S6 数字条 {n} 项 / 栅格 {cols} 列，会有项被挤到第二屏"]
    return []


def check_banner_template(root):
    t = read(root, "templates/base.html")
    if t is None:
        return ["S7 缺 templates/base.html"]
    m = re.search(r"<!-- 推荐活动公告栏(.+?)<!-- 推荐活动弹窗", t, re.S)
    if not m:
        return ["S7 找不到推荐活动横幅区块"]
    blk = m.group(1)
    if "referral-banner" not in blk:
        return ["S7 横幅区块里没有 referral-banner"]
    if "{% if session.get('user_id') %}" not in blk or "{% endif %}" not in blk:
        return ["S7 横幅没有按登录身份分发，匿名访客首屏仍会看到老用户活动"]
    return []


def check_owner(root):
    """站点交付文件属主必须是服务身份。

    范围不自己维护一份：直接复用 6j 整站指纹守卫的 collect()，
    那份口径按目录类别圈交付物、按类别排除运行产物。
    2026-11-08 之前这里只查 templates/ 和 static/，
    scripts/ tests/ modules/ 下 23 个 root:root 漂移一直漏检。
    """
    errs = []
    if pwd is None or grp is None:
        return ["S8 本机无 pwd/grp，属主检查不许静默跳过（守卫须在 Linux 跑）"]
    try:
        want_u = pwd.getpwnam(SERVICE_OWNER).pw_uid
        want_g = grp.getgrnam(SERVICE_OWNER).gr_gid
    except KeyError:
        return [f"S8 本机找不到服务身份 {SERVICE_OWNER}"]
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from verify_site_fingerprint import collect
        rels = sorted(collect(Path(root)))
    except Exception as exc:  # noqa: BLE001
        return [f"S8 拿不到整站交付物口径，属主检查不许静默跳过：{exc}"]
    if len(rels) < 3:
        errs.append("S8 交付物只有 %d 份，范围被吞掉了（守卫不许假绿）" % len(rels))
    # 基线本身被 collect() 排除（不能进自己的清单），但它同样归属服务身份：
    # root 重签曾经把它变成 root:root，这里单独纳入，漂移下次 QA 就能报出来。
    baseline_rel = "scripts/site_files_baseline.json"
    if (Path(root) / baseline_rel).is_file() and baseline_rel not in rels:
        rels.append(baseline_rel)
    # 基线本身被 collect() 排除（不能进自己的清单），但它同样归属服务身份：
    # root 重签曾经把它变成 root:root，这里单独纳入，漂移下次 QA 就能报出来。
    baseline_rel = "scripts/site_files_baseline.json"
    if (Path(root) / baseline_rel).is_file() and baseline_rel not in rels:
        rels.append(baseline_rel)
    for rel in rels:
        p = Path(root) / rel
        try:
            st = p.stat()
        except OSError as exc:
            errs.append(f"S8 {rel} 读不了（权限/属主异常）：{exc}")
            continue
        if st.st_uid != want_u or st.st_gid != want_g:
            errs.append(f"S8 {rel} 属主不是 {SERVICE_OWNER}（服务身份）")
    return errs


def check_dead_link(root):
    errs = []
    for rel in ("static/pages/product.html", "static/pages/about.html",
                "templates/base.html", "templates/index.html"):
        t = read(root, rel)
        if t and "/pages/pricing.html" in t:
            errs.append(f"S9 {rel} 仍有 404 死链 /pages/pricing.html")
    return errs


def check_render(base, core):
    """真浏览器匿名态：横幅不可见 + 逐页导航含齐 core。"""
    sp = import_playwright()
    if sp is None:
        return ["S10 找不到 playwright，真渲染检查不许静默跳过"]
    exe = find_chromium()
    if not exe:
        return ["S10 找不到 chromium 可执行文件，真渲染检查不许静默跳过"]
    errs = []
    pages = [("/", "header"), ("/try", "nav"),
             ("/pages/product.html", "nav.site-nav"),
             ("/pages/about.html", "nav.site-nav")]
    try:
        with sp() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"],
                                        executable_path=exe)
            ctx = browser.new_context(viewport={"width": 1280, "height": 800})
            for path, sel in pages:
                page = ctx.new_page()
                try:
                    page.goto(base.rstrip("/") + path, wait_until="load", timeout=25000)
                    page.wait_for_timeout(250)
                    rec = page.evaluate("""(sel) => {
                      const root = document.querySelector(sel) ||
                                   document.querySelector('nav') ||
                                   document.querySelector('header');
                      const hrefs = root ? Array.from(root.querySelectorAll('a[href]'))
                                              .map(a => a.getAttribute('href')) : [];
                      const b = document.getElementById('referral-banner');
                      const bannerVisible = !!(b && b.offsetParent !== null &&
                                               getComputedStyle(b).display !== 'none');
                      return {hrefs, bannerVisible,
                              overflowX: document.documentElement.scrollWidth > window.innerWidth + 2};
                    }""", sel)
                except Exception as e:
                    errs.append(f"S10 打开 {path} 失败: {type(e).__name__}")
                    page.close()
                    continue
                miss = [it["href"] for it in core
                        if it["href"] not in rec["hrefs"] and it["href"] != "/"]
                if miss:
                    errs.append(f"S10 真浏览器 {path} 导航缺 {miss}")
                if path == "/try" and rec["bannerVisible"]:
                    errs.append("S10 匿名访客首屏仍能看到老用户推荐横幅")
                if rec["overflowX"]:
                    errs.append(f"S10 {path} 页面出现横向溢出")
                page.close()
            ctx.close()
            browser.close()
    except Exception as e:
        errs.append(f"S10 真浏览器启动失败: {type(e).__name__}: {e}"[:200])
    return errs


def run_checks(root, base, with_http=True, with_render=True, with_owner=True):
    core, errs = core_list(root)
    errs += check_nav_static(root, core)
    if with_http:
        errs += check_http(core, base)
    errs += check_lang_number(root)
    errs += check_decor_warm(root)
    errs += check_stats_grid(root)
    errs += check_banner_template(root)
    if with_owner:
        errs += check_owner(root)
    errs += check_dead_link(root)
    if with_render:
        errs += check_render(base, core)
    return errs


# ---------------- 造坏自检 ----------------

def self_test(root, base):
    """每项检查都要有能判红的坏副本；造坏不写死当前色值/文件名当锚点。"""
    cases = []

    def add(name, mutate, expect, http=False, render=False):
        cases.append((name, mutate, expect, http, render))

    add("删掉导航清单", lambda d: (d / "scripts/site_nav.json").unlink(), "S1")
    # 2026-11-22 导航收敛到 templates/_nav.html 之后，首页里已经没有字面导航链接了，
    # 原来的锚点 '<a href="/try">' 找不到、坏例没造出来却判了绿（自测就是这样抓到假绿的）。
    # 现在的造坏方式：把 include 换成一份只有首页一项的残缺导航 —— 等价于「少了九个入口」。
    add("首页少一条核心导航",
        lambda d: (d / "templates/index.html").write_text(
            re.sub(r'\{%-?\s*include\s+["\']_nav\.html["\']\s*-?%\}',
                   '<nav class="xp-nav-links"><a href="/">首页</a></nav>',
                   (d / "templates/index.html").read_text(encoding="utf-8"), count=1),
            encoding="utf-8"), "S2")
    add("清单塞一条不存在的链接",
        lambda d: (d / "scripts/site_nav.json").write_text(json.dumps({
            "version": "bad", "core": json.loads(
                (d / "scripts/site_nav.json").read_text(encoding="utf-8"))["core"] +
            [{"label": "坏链接", "href": "/xp-guard-definitely-404"}]},
            ensure_ascii=False), encoding="utf-8"), "S3", http=True)
    # 造坏不能依赖「正文里恰好有某个不带空格的写法」：23 和「种」之间常有空格，
    # 原来的字面量替换匹配不上，坏例没造出来却判绿。改用正则，空格可有可无。
    add("语言数改回 17",
        lambda d: (d / "static/pages/product.html").write_text(
            re.sub(r"23(\s*)种主流编程语言", r"17\1种主流编程语言",
                   (d / "static/pages/product.html").read_text(encoding="utf-8"), count=1),
            encoding="utf-8"), "S4")
    add("kicker 小字改回暖色（按声明行注入，不认当前色值）",
        lambda d: (d / "templates/index.html").write_text(re.sub(
            r"(\.kicker\{[^}]*color:\s*)[^;]+;",
            r"\1#d9a877;",
            (d / "templates/index.html").read_text(encoding="utf-8"), count=1),
            encoding="utf-8"), "S5")
    add("品牌方块换回火苗",
        lambda d: (d / "static/pages/product.html").write_text(
            (d / "static/pages/product.html").read_text(encoding="utf-8").replace(
                '<div class="brand-logo">◆</div>', '<div class="brand-logo">🔥</div>', 1),
            encoding="utf-8"), "S5")
    add("数字条多塞一项",
        lambda d: (d / "templates/index.html").write_text(
            (d / "templates/index.html").read_text(encoding="utf-8").replace(
                '<section class="stats">', '<div class="stat">x</div><section class="stats">', 1),
            encoding="utf-8"), "S6")
    add("横幅去掉登录态包裹",
        lambda d: (d / "templates/base.html").write_text(
            (d / "templates/base.html").read_text(encoding="utf-8").replace(
                "{% if session.get('user_id') %}\n    <div id=\"referral-banner\"",
                "<div id=\"referral-banner\"", 1), encoding="utf-8"), "S7")
    add("站点文件属主改错",
        lambda d: os.chown(d / "static/pages/product.html", 0, 0), "S8")
    add("脚本目录交付文件属主改错也要判红",
        lambda d: os.chown(d / "scripts/site_nav.json", 0, 0), "S8")
    add("死链复活",
        lambda d: (d / "static/pages/about.html").write_text(
            (d / "static/pages/about.html").read_text(encoding="utf-8").replace(
                '<a href="/pricing">定价</a>',
                '<a href="/pages/pricing.html">定价方案</a>', 1), encoding="utf-8"), "S9")
    add("清单塞假链接让真浏览器判红",
        lambda d: (d / "scripts/site_nav.json").write_text(json.dumps({
            "version": "bad", "core": json.loads(
                (d / "scripts/site_nav.json").read_text(encoding="utf-8"))["core"] +
            [{"label": "假", "href": "/xp-guard-no-such-nav"}]},
            ensure_ascii=False), encoding="utf-8"), "S10", render=True)

    passed = 0
    fails = []
    owner_uid = owner_gid = None
    if pwd is not None and grp is not None:
        try:
            owner_uid = pwd.getpwnam(SERVICE_OWNER).pw_uid
            owner_gid = grp.getgrnam(SERVICE_OWNER).gr_gid
        except KeyError:
            pass
    for name, mutate, expect, http, render in cases:
        with tempfile.TemporaryDirectory(prefix="xp_guard_") as td:
            site = Path(td) / "site"
            site.mkdir()
            # 只复制守卫真正会读的文件（自检目的是验判据，不是全量镜像）
            for sub, pat in (("templates", "*.html"), ("static/pages", "*.html")):
                src = Path(root) / sub
                if not src.is_dir():
                    continue
                dst = site / sub
                dst.mkdir(parents=True, exist_ok=True)
                for f in src.rglob(pat):
                    rel = f.relative_to(src)
                    target = dst / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, target)
            css = site / "static/css"
            css.mkdir(parents=True, exist_ok=True)
            for n in ("tokens.css", "cool-fx.css"):
                f = Path(root) / "static/css" / n
                if f.is_file():
                    shutil.copy2(f, css / n)
            nav = Path(root) / "scripts/site_nav.json"
            if nav.is_file():
                (site / "scripts").mkdir(parents=True, exist_ok=True)
                shutil.copy2(nav, site / "scripts/site_nav.json")
            # 副本先归位成服务身份，否则每个用例都会被 S8 刷成红，判据失真
            if owner_uid is not None:
                for f in site.rglob("*"):
                    if f.is_file():
                        os.chown(f, owner_uid, owner_gid)
            mutate(site)
            try:
                errs = run_checks(str(site), base, with_http=http,
                                  with_render=render, with_owner=owner_uid is not None)
            except Exception as e:
                errs = [f"EXC {type(e).__name__}: {e}"]
            if any(x.startswith(expect) for x in errs):
                passed += 1
            else:
                fails.append((name, expect, errs[:3]))
    print(f"造坏自检: {passed}/{len(cases)} 判红")
    for name, expect, errs in fails:
        print(f"  ❌ {name}: 期望 {expect} 判红，实际 {errs}")
    return 0 if not fails else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=DEFAULT_ROOT)
    ap.add_argument("--base-url", default=DEFAULT_BASE)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test(a.root, a.base_url)
    errs = run_checks(a.root, a.base_url)
    for e in errs:
        print("❌", e)
    if errs:
        print(f"\n元素一致性守卫：{len(errs)} 项不合格")
        return 1
    print("✅ 元素一致性守卫全绿：导航清单 / 真请求 / 数字口径 / 装饰色 / "
          "首屏身份 / 属主 / 真浏览器匿名态")
    return 0


if __name__ == "__main__":
    sys.exit(main())
