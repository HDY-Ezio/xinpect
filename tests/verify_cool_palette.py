#!/usr/bin/env python3
"""冷光质感 / 装饰色红线守卫（2026-11-08，QA 6g）。

用户 2026-10-26 定的五行配色红线：藏青属水、白银蓝属金（金生水），
装饰色忌红橙（火克金）、忌土黄（土克水）；报错红叉 / 警告黄叹号属提醒，保留。

11-08 之前官网只有藏青、白、浅灰三档，用户当面指出「太素」；
本轮加了冷光质感层，守卫钉死六件事，防止「加颜色」加回忌讳色或挡住内容：
  1) 装饰色必须冷色（蓝通道 >= 红通道），暖色一律判红。
  2) 功能状态色不许被误删（提醒要留着）。
  3) 氛围层不写裸颜色、不定义 :root、不引用状态色当装饰。
  4) 装饰层 pointer-events:none / z-index:0 / 尊重 reduced-motion。
  5) 主按钮对比度 >= 4.5:1，且在真人视口里完整落首屏。
  6) 真浏览器取计算样式验颜色与遮挡，不许静默跳过。

--self-test 用临时最小样本造 12 类坏副本，必须全判红；干净样本判绿。
不读任何固定临时文件，不依赖当前生产状态。
"""
import argparse
import glob
import re
import shutil
import sys
import tempfile
from pathlib import Path

SITE = Path("/opt/xinpect-website")
HEX_RE = re.compile(r"#([0-9A-Fa-f]{6})\b")
RGB_RE = re.compile(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)")
DECL_RE = re.compile(r"(--[\w-]+)\s*:\s*([^;]+);")
STATE_VAR_RE = re.compile(
    r"var\(\s*--(?:color-(?:danger|warning|success|grade-[a-z])|red|warn|error|orange)\b")
BANNED_TRANSITION_RE = re.compile(
    r"transition\s*:\s*(?:all\b|[^;]*\b(?:top|left|right|width|height)\b)")

STATUS_COLORS = ("--color-danger", "--color-warning")


# ---------------------------------------------------------------- 纯函数
def parse_color(value):
    """取一段 CSS 值里第一个颜色字面量，返回 (r,g,b) 或 None（无彩/透明/纯变量）。"""
    m = HEX_RE.search(value)
    if m:
        h = m.group(1)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    m = RGB_RE.search(value)
    if m:
        return tuple(int(x) for x in m.groups())
    return None


def is_cool(value):
    """冷色判据：蓝 >= 红（无彩 / 白 / 银灰允许，暖色红>蓝判 False）。"""
    c = parse_color(value)
    if c is None:
        return True
    return c[2] >= c[0]


def contrast_ratio(fg, bg):
    """WCAG 2.1 相对亮度对比度。fg/bg 为 (r,g,b)。"""
    def lum(c):
        def ch(v):
            v = v / 255.0
            return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
        return 0.2126 * ch(c[0]) + 0.7152 * ch(c[1]) + 0.0722 * ch(c[2])
    a, b = lum(fg), lum(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def in_view(bottom, viewport_height):
    return bottom <= viewport_height


# ---------------------------------------------------------------- 静态检查
def check_static(site: Path):
    errors = []
    css = site / "static" / "css"
    tpl = site / "templates"
    pages = site / "static" / "pages"
    tokens_p = css / "tokens.css"
    cool_p = css / "cool-fx.css"
    base_p = tpl / "base.html"

    for p in (tokens_p, cool_p, base_p):
        if not p.is_file():
            errors.append(f"G1 缺文件: {p.relative_to(site) if p.is_relative_to(site) else p}")
    if errors:
        return errors

    tokens = tokens_p.read_text(encoding="utf-8")
    cool = cool_p.read_text(encoding="utf-8")

    # G1 新增装饰色必须冷色
    decls = dict(DECL_RE.findall(tokens))
    cool_vars = {k: v for k, v in decls.items()
                 if k.startswith("--color-cool-") or k.startswith("--shadow-cool-")}
    if len(cool_vars) < 8:
        errors.append(f"G1 冷光变量太少({len(cool_vars)})，疑似氛围层色板被删")
    for k, v in sorted(cool_vars.items()):
        if not is_cool(v):
            errors.append(f"G1 装饰色 {k}={v.strip()} 是暖色，踩了红橙/土黄红线")

    # G2 功能状态色必须还在（提醒不许被「收干净」收掉）
    for k in STATUS_COLORS:
        if k not in decls:
            errors.append(f"G2 功能提醒色 {k} 被删，报错/警告将看不懂")

    # G3 氛围层不许写裸颜色、不许自定义 :root、不许拿状态色当装饰
    for m in HEX_RE.finditer(cool):
        errors.append(f"G3 cool-fx.css 出现裸颜色 {m.group(0)}，颜色必须走 tokens.css")
    for m in RGB_RE.finditer(cool):
        errors.append(f"G3 cool-fx.css 出现裸颜色 {m.group(0)}，颜色必须走 tokens.css")
    if re.search(r":root\s*\{", cool):
        errors.append("G3 cool-fx.css 不许定义 :root，唯一事实来源是 tokens.css")
    sm = STATE_VAR_RE.search(cool)
    if sm:
        errors.append(f"G3 cool-fx.css 把功能状态色 {sm.group(0)} 当装饰用")

    # G4 装饰层不挡点击、不抢层级、尊重减弱动效
    for sel in (".xp-ambient {", ".xp-ambient-banner {"):
        i = cool.find(sel)
        if i < 0:
            errors.append(f"G4 缺氛围层规则 {sel}")
            continue
        block = cool[i:cool.find("}", i) + 1]
        if "pointer-events: none" not in block:
            errors.append(f"G4 {sel} 没写 pointer-events: none，会挡住点击")
        if "z-index: 0" not in block and sel == ".xp-ambient {":
            errors.append("G4 .xp-ambient 没写 z-index: 0，会盖住内容")
        if sel == ".xp-ambient {" and "position: absolute" not in block:
            errors.append("G4 .xp-ambient 必须绝对定位，不许占文档流高度")
    if "prefers-reduced-motion" not in cool:
        errors.append("G4 缺 prefers-reduced-motion 段，装饰动画停不下来")
    bm = BANNED_TRANSITION_RE.search(cool)
    if bm:
        errors.append(f"G4 出现动布局属性的过渡: {bm.group(0).strip()[:70]}")
    if re.search(r"transition\s*:\s*all", cool):
        errors.append("G4 不许写 transition: all")

    # G5 门面装饰主色必须冷色（两页老橙 + 首页偏棕按钮）
    for p, key in ((pages / "product.html", "--primary"),
                   (pages / "about.html", "--primary"),
                   (tpl / "index.html", "--accent")):
        if not p.is_file():
            errors.append(f"G5 缺门面页 {p.name}")
            continue
        t = p.read_text(encoding="utf-8")
        m = re.search(re.escape(key) + r"\s*:\s*([^;]+);", t)
        if not m:
            errors.append(f"G5 {p.name} 找不到 {key}")
        elif not is_cool(m.group(1)):
            errors.append(f"G5 {p.name} 的 {key}={m.group(1).strip()} 是暖色装饰主色")

    # G6 独立页挂载一致：挂了 tokens.css 的独立页必须挂 cool-fx.css，
    #    除非页面自带首页招牌（codeflow + scanline 自证），不算路径白名单。
    linked = 0
    for p in sorted(list(tpl.rglob("*.html")) + list(pages.glob("*.html"))):
        t = p.read_text(encoding="utf-8", errors="replace")
        if "<html" not in t or "tokens.css" not in t:
            continue
        if "cool-fx.css" not in t:
            if "codeflow" in t and "scanline" in t:
                continue
            errors.append(f"G6 独立页 {p.relative_to(site)} 挂了色板却没挂氛围层")
        else:
            linked += 1
    if linked < 5:
        errors.append(f"G6 只有 {linked} 个独立页挂了氛围层，疑似整站没生效")
    if "cool-fx.css" not in base_p.read_text(encoding="utf-8"):
        errors.append("G6 base.html 没挂氛围层，绝大多数页面不会变")

    # G7 门面氛围层结构在位
    tr = tpl / "try.html"
    if tr.is_file():
        t = tr.read_text(encoding="utf-8")
        if "xp-has-ambient" not in t or "xp-ambient-code" not in t:
            errors.append("G7 试扫页门面氛围层结构缺失")
    for name in ("report.html", "report_shared.html"):
        p = tpl / name
        if p.is_file() and "xp-ambient-banner" not in p.read_text(encoding="utf-8"):
            errors.append(f"G7 {name} 缺报告门面光效横幅")
    return errors


# ---------------------------------------------------------------- 真渲染
def _playwright():
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        pass
    for base in ("/home/*/.local/lib/python3*/site-packages",
                 "/usr/local/lib/python3*/dist-packages",
                 "/usr/lib/python3/dist-packages"):
        for p in sorted(glob.glob(base)):
            if p not in sys.path and (Path(p) / "playwright").is_dir():
                sys.path.insert(0, p)
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        return None


def _chromium():
    import os
    env = os.environ.get("XP_CHROMIUM")
    if env and Path(env).is_file():
        return env
    c = sorted(glob.glob("/home/ubuntu/.cache/ms-playwright/chromium-*/chrome-linux64/chrome"))
    c += sorted(glob.glob("/root/.cache/ms-playwright/chromium-*/chrome-linux64/chrome"))
    return c[-1] if c else None


PROBE = r"""() => {
  const cs = (el) => el ? getComputedStyle(el) : null;
  const btn = document.querySelector('#scan-btn') || document.querySelector('.btn-primary');
  const amb = document.querySelector('.xp-ambient');
  const b = cs(btn), a = cs(amb), body = cs(document.body);
  let rect = null, hit = null, occluded = false;
  if (btn) {
    const r = btn.getBoundingClientRect();
    rect = { top: r.top, bottom: r.bottom, left: r.left, right: r.right };
    const el = document.elementFromPoint((r.left + r.right) / 2, (r.top + r.bottom) / 2);
    hit = el ? (el.id || el.className || el.tagName) : null;
    occluded = !!(el && btn !== el && !btn.contains(el));
  }
  return {
    btnBG: b ? b.backgroundColor : null,
    btnFG: b ? b.color : null,
    bodyBG: body ? body.backgroundColor : null,
    ambPE: a ? a.pointerEvents : null,
    ambZ: a ? a.zIndex : null,
    rect, hit, occluded,
    title: document.title,
  };
}"""


def check_render(base_url):
    errors = []
    sp = _playwright()
    if sp is None:
        return ["G8 缺 playwright，无法做真渲染检查（不许静默跳过）"]
    exe = _chromium()
    if not exe:
        return ["G8 找不到 chromium，无法做真渲染检查"]

    viewports = ({"width": 1280, "height": 800}, {"width": 1080, "height": 640})
    try:
        with sp() as p:
            browser = p.chromium.launch(headless=True, executable_path=exe,
                                        args=["--no-sandbox"])
            for vp in viewports:
                ctx = browser.new_context(viewport=vp)
                page = ctx.new_page()
                try:
                    resp = page.goto(base_url.rstrip("/") + "/try",
                                     wait_until="load", timeout=25000)
                    if not resp or resp.status != 200:
                        errors.append(f"G8 /try HTTP {resp.status if resp else '?'}")
                        continue
                    page.wait_for_timeout(300)
                    r = page.evaluate(PROBE)
                    tag = f"{vp['width']}x{vp['height']}"
                    if not r["rect"]:
                        errors.append(f"G8 {tag} 找不到试扫主按钮")
                    else:
                        if not in_view(r["rect"]["bottom"], vp["height"]):
                            errors.append(
                                f"G8 {tag} 主按钮掉出首屏 bottom={r['rect']['bottom']:.0f}")
                        if r["occluded"]:
                            errors.append(f"G8 {tag} 主按钮被装饰层挡住 hit={r['hit']}")
                    if r["ambPE"] and r["ambPE"] != "none":
                        errors.append(f"G8 {tag} 氛围层会吃点击 pointerEvents={r['ambPE']}")
                    bg = parse_color(r["btnBG"] or "")
                    fg = parse_color(r["btnFG"] or "")
                    if bg and fg:
                        cr = contrast_ratio(fg, bg)
                        if cr < 4.5:
                            errors.append(f"G8 {tag} 主按钮对比度 {cr:.2f}:1 < 4.5:1")
                    else:
                        errors.append(f"G8 {tag} 按钮色值取不到 bg={r['btnBG']} fg={r['btnFG']}")
                    bodyc = parse_color(r["bodyBG"] or "")
                    if bodyc and not is_cool(r["bodyBG"] or ""):
                        errors.append(f"G8 {tag} 页面底色是暖色 {r['bodyBG']}")
                    print(f"    {tag} btn={r['btnBG']} 对比度="
                          f"{(round(contrast_ratio(fg, bg), 2) if bg and fg else '?')} "
                          f"bottom={r['rect']['bottom']:.0f} 遮挡={r['occluded']}")
                except Exception as e:
                    errors.append(f"G8 渲染异常 {type(e).__name__}: {e}"[:180])
                finally:
                    page.close()
                    ctx.close()
            # 首页主按钮换色后也必须冷色且可读
            ctx = browser.new_context(viewport={"width": 1280, "height": 800})
            page = ctx.new_page()
            try:
                resp = page.goto(base_url.rstrip("/") + "/", wait_until="load", timeout=25000)
                if resp and resp.status == 200:
                    page.wait_for_timeout(250)
                    r = page.evaluate("""() => {
                      const b = document.querySelector('.hero .btn-solid');
                      if (!b) return null;
                      const s = getComputedStyle(b);
                      return { bg: s.backgroundColor, fg: s.color };
                    }""")
                    if not r:
                        errors.append("G8 首页找不到主按钮，等于没检查换色")
                    else:
                        if not is_cool(r["bg"] or ""):
                            errors.append(f"G8 首页主按钮仍是暖色 {r['bg']}")
                        bg, fg = parse_color(r["bg"] or ""), parse_color(r["fg"] or "")
                        if bg and fg and contrast_ratio(fg, bg) < 4.5:
                            errors.append("G8 首页主按钮对比度不足 4.5:1")
                        print(f"    首页按钮 bg={r['bg']} 冷色={is_cool(r['bg'] or '')}")
            except Exception as e:
                errors.append(f"G8 首页渲染异常 {type(e).__name__}: {e}"[:180])
            finally:
                page.close()
                ctx.close()
            browser.close()
    except Exception as e:
        errors.append(f"G8 浏览器启动失败: {type(e).__name__}: {e}"[:180])
    return errors


# ---------------------------------------------------------------- 造坏自检
MIN_TOKENS = """:root{
--color-cool-page:#F7FAFD;--color-cool-surface:#EEF4FA;
--color-cool-edge:rgba(62,92,138,0.22);--color-cool-beam:#7FA9D8;
--color-cool-sheen:rgba(255,255,255,0.28);--color-cool-grid:rgba(62,92,138,0.05);
--color-cool-ink:#0B1830;--color-cool-screen:#0D1729;
--color-danger:#F5222D;--color-warning:#FAAD14;
}
"""
MIN_COOL = """.xp-ambient {
  position: absolute; pointer-events: none; z-index: 0;
  background: var(--color-cool-surface);
}
.xp-ambient-banner { pointer-events: none; }
@media (prefers-reduced-motion: reduce) { .xp-ambient { animation: none; } }
"""
MIN_BASE = """<!DOCTYPE html><html><head>
<link rel="stylesheet" href="/static/css/tokens.css?v=20261106">
<link rel="stylesheet" href="/static/css/cool-fx.css?v=20261108">
</head><body></body></html>
"""
MIN_TRY = """{% extends "base.html" %}
<div class="container xp-has-ambient">
<div class="xp-ambient"><div class="xp-ambient-code"></div></div>
<button id="scan-btn">开始免费检测</button></div>
"""
MIN_REPORT = "<div class='xp-ambient-banner'></div>"
MIN_INDEX = """<html><head>
<link rel="stylesheet" href="/static/css/tokens.css?v=20261106">
</head><body><div class="codeflow"></div><div class="scanline"></div>
<style>:root{--accent:#3E5C8A;}</style></body></html>
"""
MIN_PAGE = """<!DOCTYPE html><html><head>
<link rel="stylesheet" href="/static/css/tokens.css?v=20261106">
<link rel="stylesheet" href="/static/css/cool-fx.css?v=20261108">
<title>x</title></head><body><style>:root{--primary:#3E5C8A;}</style></body></html>
"""


def make_min_site(d: Path):
    for sub in ("static/css", "static/pages", "templates"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    (d / "static/css/tokens.css").write_text(MIN_TOKENS, encoding="utf-8")
    (d / "static/css/cool-fx.css").write_text(MIN_COOL, encoding="utf-8")
    (d / "templates/base.html").write_text(MIN_BASE, encoding="utf-8")
    (d / "templates/try.html").write_text(MIN_TRY, encoding="utf-8")
    (d / "templates/report.html").write_text(MIN_REPORT, encoding="utf-8")
    (d / "templates/report_shared.html").write_text(MIN_REPORT, encoding="utf-8")
    (d / "templates/index.html").write_text(MIN_INDEX, encoding="utf-8")
    for i in range(6):
        (d / f"templates/p{i}.html").write_text(MIN_PAGE, encoding="utf-8")
    (d / "static/pages/product.html").write_text(MIN_PAGE, encoding="utf-8")
    (d / "static/pages/about.html").write_text(MIN_PAGE, encoding="utf-8")
    return d


def self_test():
    results = []

    def case(name, mutate, should_fail):
        tmp = Path(tempfile.mkdtemp(prefix="coolguard_"))
        try:
            make_min_site(tmp)
            mutate(tmp)
            errs = check_static(tmp)
            ok = (bool(errs) == should_fail)
            results.append((name, ok, errs))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def edit(d, rel, fn):
        p = d / rel
        p.write_text(fn(p.read_text(encoding="utf-8")), encoding="utf-8")

    case("干净样本必须判绿", lambda d: None, False)
    case("A 冷光变量改成橙必须判红", lambda d: edit(
        d, "static/css/tokens.css",
        lambda t: t.replace("--color-cool-page:#F7FAFD", "--color-cool-page:#FF6B35")), True)
    case("B 冷光变量改成土黄必须判红", lambda d: edit(
        d, "static/css/tokens.css",
        lambda t: t.replace("--color-cool-page:#F7FAFD", "--color-cool-page:#FAAD14")), True)
    case("C 氛围层写裸橙必须判红", lambda d: edit(
        d, "static/css/cool-fx.css",
        lambda t: t.replace("background: var(--color-cool-surface);",
                            "background: #FF6B35;")), True)
    case("D 氛围层拿报错红当装饰必须判红", lambda d: edit(
        d, "static/css/cool-fx.css",
        lambda t: t.replace("background: var(--color-cool-surface);",
                            "background: var(--color-danger);")), True)
    case("E 装饰层能吃点击必须判红", lambda d: edit(
        d, "static/css/cool-fx.css",
        lambda t: t.replace("pointer-events: none; z-index: 0;", "z-index: 9;")), True)
    case("F 装饰层占文档流高度必须判红", lambda d: edit(
        d, "static/css/cool-fx.css",
        lambda t: t.replace("position: absolute;", "position: relative;")), True)
    case("G 缺减弱动效段必须判红", lambda d: edit(
        d, "static/css/cool-fx.css",
        lambda t: t.split("@media")[0]), True)
    case("H 出现 transition:all 必须判红", lambda d: edit(
        d, "static/css/cool-fx.css",
        lambda t: t + "\n.x{transition:all .3s;}\n"), True)
    case("I 功能提醒色被删必须判红", lambda d: edit(
        d, "static/css/tokens.css",
        lambda t: t.replace("--color-danger:#F5222D;", "")), True)
    case("J 两页介绍主色改回橙必须判红", lambda d: edit(
        d, "static/pages/product.html",
        lambda t: t.replace("--primary:#3E5C8A", "--primary:#FF6B35")), True)
    case("K 首页主按钮改回棕必须判红", lambda d: edit(
        d, "templates/index.html",
        lambda t: t.replace("--accent:#3E5C8A", "--accent:#a45f33")), True)
    case("L 独立页漏挂氛围层必须判红", lambda d: edit(
        d, "templates/p0.html",
        lambda t: t.replace('<link rel="stylesheet" href="/static/css/cool-fx.css?v=20261108">\n', '')), True)

    # 纯函数造坏：色相 / 对比度 / 视口
    fn_cases = [
        ("M 纯函数 暖色必须判红", not is_cool("#FF6B35")),
        ("N 纯函数 银蓝必须判绿", is_cool("#3E5C8A")),
        ("O 纯函数 对比度不足必须判红", contrast_ratio((255, 255, 255), (250, 250, 250)) < 4.5),
        ("P 纯函数 藏青白字必须判绿", contrast_ratio((255, 255, 255), (26, 43, 74)) >= 4.5),
        ("Q 纯函数 按钮出屏必须判红", not in_view(684, 640)),
        ("R 纯函数 按钮在首屏必须判绿", in_view(600, 640)),
    ]
    for name, ok in fn_cases:
        results.append((name, ok, []))

    failed = 0
    for name, ok, errs in results:
        print(f"  [{'OK' if ok else 'FAIL'}] {name}" + (f"  命中 {len(errs)} 条" if errs else ""))
        if not ok:
            failed += 1
            for e in errs[:2]:
                print(f"        {e}")
    print(f"\n自检结果: {len(results) - failed}/{len(results)} 通过")
    return 1 if failed else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(SITE))
    ap.add_argument("--base-url", default="https://xinpect.xingwangzhineng.com")
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        print("=== 冷光质感 / 装饰色红线守卫自检（临时最小样本）===")
        return self_test()
    site = Path(a.root)
    print(f"=== 冷光质感守卫 站点={site} ===")
    errors = check_static(site)
    if not a.no_render:
        print("  -- 真浏览器取计算样式 --")
        errors += check_render(a.base_url)
    for e in errors:
        print(f"  [FAIL] {e}")
    if errors:
        print(f"\n❌ 冷光质感守卫失败: {len(errors)} 条")
        return 1
    print("\n✅ 冷光质感守卫通过: 装饰全冷色、提醒留着、不挡内容、按钮在首屏")
    return 0


if __name__ == "__main__":
    sys.exit(main())
