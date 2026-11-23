#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分享报告页守卫（2026-11-09，QA 6m）。

背景：report_shared.html 是别人点分享链接第一眼看到的页，也是站里唯一的
深色版面。它以前没有令牌可用，做的时候自己抄了一套 Tailwind Slate，结果
72 分那个大数字、问题总数、页脚链接在卡片上对比度只有 1.52:1 —— 不是「不
好看」，是根本看不见；次要文字一律 3.73:1，整页发灰发糊。11-09 重做后，
颜色全部来自 tokens.css 的 --color-dark-* / *-on-dark。

守卫钉四件事：
  1) 模板里不许有裸色值（#hex / rgb() / hsl()）。改色只能改 tokens.css。
  2) 不许引用 --color-v-* 这种按值自动生成的字面量变量名（语义不明，
     换个色值变量名就跟着变，页面迟早对不上）。
  3) 模板引用的每个变量都必须在 tokens.css 里定义过。引用了不存在的
     变量，浏览器按无效处理 —— 这就是 11-06「内页整片失色」的成因。
  4) 真渲染：把模板用一组固定假数据渲染出来，用无头浏览器逐元素量
     文字与它实际压着的背景色的对比度（屏幕态 >= 4.5:1），再把媒体切成
     打印，量每个版面元素是否还有深色底、文字是否还看得见。

--self-test 用内置最小样本造 5 类坏副本，必须全判红；干净样本必须判绿。
自检不读生产模板、不依赖任何固定临时文件，也不写死当前色值。
"""
import argparse
import glob
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

SITE = Path("/opt/xinpect-website")
TPL = SITE / "templates/report_shared.html"
TOKENS = SITE / "static/css/tokens.css"

VAR_DEF_RE = re.compile(r"(--[A-Za-z0-9_-]+)\s*:")
VAR_REF_RE = re.compile(r"var\(\s*(--[A-Za-z0-9_-]+)")
HEX_RE = re.compile(r"(?<!&)#[0-9a-fA-F]{3,8}\b")
FUNC_COLOR_RE = re.compile(r"\b(?:rgba?|hsla?)\s*\(")
STYLE_BLOCK_RE = re.compile(r"<style>(.*?)</style>", re.S)
STYLE_ATTR_RE = re.compile(r'style="([^"]*)"')

MIN_CONTRAST = 4.5


# ---------------------------------------------------------------- 静态检查
def colour_contexts(text):
    """只取真正会被当成颜色的地方：<style> 块 + style 属性。

    不扫正文，因为正文里写「#」也不一定是颜色（锚点、编号）；
    也不扫 Jinja 表达式里的内容。
    """
    for m in STYLE_BLOCK_RE.finditer(text):
        yield "style-block", m.group(1)
    for m in STYLE_ATTR_RE.finditer(text):
        yield "style-attr", m.group(1)


def check_static(text, tokens_text):
    bad = []
    defined = set(VAR_DEF_RE.findall(tokens_text))
    local = set(VAR_DEF_RE.findall(text))

    for where, chunk in colour_contexts(text):
        for m in HEX_RE.finditer(chunk):
            bad.append("裸色值 %s（%s，第 %d 字符附近）" %
                       (m.group(0), where, m.start()))
        for m in FUNC_COLOR_RE.finditer(chunk):
            bad.append("裸色值 %s...（%s，第 %d 字符附近）" %
                       (m.group(0), where, m.start()))

    if ":root" in text:
        bad.append("模板里自己定义了 :root 变量——页面不许自立色板，"
                   "颜色只能来自 tokens.css")

    for name in sorted(set(VAR_REF_RE.findall(text))):
        if name.startswith("--color-v-"):
            bad.append("引用了字面量变量 %s（按值生成的变量名，语义不明；"
                       "请改用语义令牌）" % name)
            continue
        if name not in defined and name not in local:
            bad.append("引用了未定义的变量 %s —— 浏览器会按无效处理，"
                       "该处颜色会变透明或继承" % name)
    return bad


# ---------------------------------------------------------------- 真渲染
def find_chromium():
    """QA 以 root 跑时浏览器装在 ubuntu 家目录下，root 自己找不到。

    从机器上真实存在的目录里找，不写死版本号；也允许 XP_CHROMIUM 指定。
    """
    env = os.environ.get("XP_CHROMIUM")
    if env and Path(env).is_file():
        return env
    cands = sorted(glob.glob(
        "/home/ubuntu/.cache/ms-playwright/chromium-*/chrome-linux64/chrome"))
    cands += sorted(glob.glob(
        "/root/.cache/ms-playwright/chromium-*/chrome-linux64/chrome"))
    return cands[-1] if cands else None


def import_playwright():
    """QA 以 root 跑时，用户级安装的 playwright 不在 sys.path 里。

    从机器上真实存在的用户级 site-packages 里找，不写死版本号。
    """
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        pass
    for base in ("/home/*/.local/lib/python3*/site-packages",
                 "/root/.local/lib/python3*/site-packages"):
        for p in sorted(glob.glob(base)):
            if p not in sys.path and (Path(p) / "playwright").is_dir():
                sys.path.insert(0, p)
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        return None


SCAN_JS = r"""() => {
  function parse(c) {
    const m = (c || '').match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(',').map(parseFloat);
    return {r:p[0], g:p[1], b:p[2], a:p.length > 3 ? p[3] : 1};
  }
  function lum(c) {
    const f = v => { v /= 255; return v <= 0.03928 ? v/12.92 : Math.pow((v+0.055)/1.055, 2.4); };
    return 0.2126*f(c.r) + 0.7152*f(c.g) + 0.0722*f(c.b);
  }
  function ratio(a, b) {
    const l1 = lum(a), l2 = lum(b);
    return (Math.max(l1,l2)+0.05) / (Math.min(l1,l2)+0.05);
  }
  function effBg(el) {
    let n = el;
    while (n && n.nodeType === 1) {
      const c = parse(getComputedStyle(n).backgroundColor);
      if (c && c.a > 0.6) return c;
      n = n.parentElement;
    }
    return {r:255,g:255,b:255,a:1};
  }
  function visible(el) {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return false;
    if (parseFloat(cs.opacity) < 0.15) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }
  function path(el) {
    let s = el.tagName.toLowerCase();
    if (el.className && typeof el.className === 'string')
      s += '.' + el.className.trim().split(/\s+/).slice(0,2).join('.');
    return s;
  }
  const low = [], dark = [];
  const CONTROLS = ['A','BUTTON','INPUT','SELECT','TEXTAREA','SVG','PATH'];
  for (const el of document.querySelectorAll('body *')) {
    if (!visible(el)) continue;
    const cs = getComputedStyle(el);
    const bg = effBg(el);
    const own = Array.from(el.childNodes)
      .filter(n => n.nodeType === 3 && n.textContent.trim())
      .map(n => n.textContent.trim()).join('');
    if (own) {
      const fg = parse(cs.color);
      if (fg) {
        const r = ratio(fg, bg);
        if (r < 4.5) low.push({el: path(el), text: own.slice(0,24),
          color: cs.color, bg: 'rgb('+bg.r+','+bg.g+','+bg.b+')',
          ratio: Math.round(r*100)/100});
      }
    }
    const ob = parse(cs.backgroundColor);
    if (!CONTROLS.includes(el.tagName) && ob && ob.a > 0.6 && lum(ob) < 0.5)
      dark.push({el: path(el), bg: cs.backgroundColor});
  }
  return {low, dark};
}"""


def demo_html(template_text, tokens_text):
    """用一组固定假数据把模板渲染成静态页。

    数据要覆盖全部分支（严重/警告/建议/深度问题/三个折叠栏），
    否则「某个分支的样式坏了」永远扫不到。
    """
    try:
        from jinja2 import Environment, DictLoader, select_autoescape
    except ImportError:
        return None, "缺 jinja2，无法渲染模板"

    issues = [
        {"file": "a/B.java", "line": 1, "message": "示例问题描述甲。",
         "engine": "E2", "severity": "critical", "severity_label": "Critical",
         "brain_id": 2, "title": "示例缺陷甲"},
        {"file": "a/C.java", "line": 2, "message": "示例问题描述乙。",
         "engine": "E3", "severity": "warning", "severity_label": "Warning",
         "brain_id": 3, "title": "示例缺陷乙"},
        {"file": "a/D.java", "line": 3, "message": "示例问题描述丙。",
         "engine": "E7", "severity": "info", "severity_label": "Info",
         "brain_id": 7, "title": "示例缺陷丙"},
    ]
    data = {
        "score": 72, "grade": "B", "scan_mode": "smart", "file_count": 10,
        "total_lines": 1000, "created_at": "2026-01-01 00:00",
        "ci_repo": "demo/repo", "ci_branch": "main",
        "ci_commit_sha": "0123456789abcdef",
        "scan_id": "00000000-0000-0000-0000-000000000000",
        "issues": issues,
        "critical": issues[:1], "warning": issues[1:2], "info": issues[2:],
        "deep_issues": [
            {"file": "a/E.java", "line": 4, "severity": "critical",
             "severity_label": "Critical", "brain_id": 2, "title": "深度缺陷甲"},
        ],
        "style_count": 1,
        "style_issues": [
            {"severity_label": "建议", "brain_id": 3, "rule_id": "STYLE-1",
             "title": "样式示例", "description": "样式说明。",
             "file": "a/F.java", "line": 5, "code_snippet": "int i = 0;",
             "suggestion": "换个名字。"},
        ],
        "profile_count": 1,
        "profile_groups": [
            {"title": "框架甲", "count": 1, "rule_id": "DEP-1", "files": ["pom.xml"]},
        ],
        "suppressed_total": 1,
        "suppressed_groups": [
            {"label": "误报分组", "count": 1, "records_shown": 1,
             "records": [{"rule_id": "R-1", "title": "被抑制示例",
                          "file": "a/G.java", "line": 6,
                          "reason": "示例理由。", "confidence": 0.9}]},
        ],
        "suppressed_stats": {"truncated": False},
    }

    env = Environment(
        loader=DictLoader({"report_shared.html": template_text,
                           "_beian.html": ""}),
        autoescape=select_autoescape(["html"]))
    env.filters["brain_label"] = lambda v: "大脑 %s" % v
    html = env.get_template("report_shared.html").render(**data)
    # 直接 file:// 打开，把站内绝对路径改成相对路径，不必起服务
    html = html.replace('href="/static/css/', 'href="static/css/')
    html = html.replace('src="/static/', 'src="static/')
    return html, None


def render_and_scan(sync_playwright, html_path, exe=None):
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, executable_path=exe,
                              args=["--no-sandbox"])
        pg = b.new_context(viewport={"width": 1440, "height": 900}).new_page()
        pg.goto(html_path.as_uri(), wait_until="load", timeout=30000)
        pg.evaluate("""() => document.querySelectorAll('.panel-body, .suppressed-body')
                        .forEach(el => el.style.display = 'block')""")
        pg.wait_for_timeout(200)
        screen = pg.evaluate(SCAN_JS)
        pg.emulate_media(media="print")
        pg.wait_for_timeout(200)
        pr = pg.evaluate(SCAN_JS)
        b.close()
    return screen, pr


def check_render(sync_playwright, html):
    bad = []
    tmp = Path(tempfile.mkdtemp(prefix="share_guard_"))
    try:
        (tmp / "static/css").mkdir(parents=True)
        for css in (SITE / "static/css").glob("*.css"):
            shutil.copy2(css, tmp / "static/css" / css.name)
        page_path = tmp / "page.html"
        page_path.write_text(html, encoding="utf-8")
        screen, pr = render_and_scan(sync_playwright, page_path,
                                    find_chromium())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    for x in screen["low"]:
        bad.append("屏幕态对比度 %.2f < %.1f：%s「%s」%s 压在 %s 上" %
                   (x["ratio"], MIN_CONTRAST, x["el"], x["text"],
                    x["color"], x["bg"]))
    for x in pr["dark"]:
        bad.append("打印态仍是深色底：%s %s（纸上打印不出来的白纸）" %
                   (x["el"], x["bg"]))
    for x in pr["low"]:
        bad.append("打印态对比度 %.2f < %.1f：%s「%s」%s 压在 %s 上" %
                   (x["ratio"], MIN_CONTRAST, x["el"], x["text"],
                    x["color"], x["bg"]))
    return bad


# ---------------------------------------------------------------- 自检
GOOD_HTML = """<!DOCTYPE html><html><head><style>
body{background:#101820;color:#F2F5F8;font:14px/1.6 sans-serif;}
.box{background:#18222E;color:#F2F5F8;padding:12px;}
.muted{color:#A6B3C2;}
@media print{
  body{background:#fff;color:#1A1A1A;}
  .box{background:#fff;color:#1A1A1A;}
  .muted{color:#4A4A4A;}
}
</style></head><body>
<div class="box">正文一段</div>
<div class="muted">次要文字</div>
</body></html>"""

GOOD_TOKENS = ":root{--color-dark-bg:#101820;--color-dark-text:#F2F5F8;}\n"


def self_test(sync_playwright):
    """造坏副本：检查器必须判红；干净样本必须判绿。"""
    fails = []

    def static_case(name, tpl, tokens, want_red=True):
        bad = check_static(tpl, tokens)
        hit = bool(bad)
        if hit != want_red:
            fails.append("自检[%s] 期望%s，实际%s（%s）" %
                         (name, "判红" if want_red else "判绿", "判红" if hit else "判绿",
                          bad[0] if bad else "-"))

    static_case("干净样本", "<style>body{color:var(--color-dark-text);}</style>",
                ":root{--color-dark-text:#F2F5F8;}", want_red=False)
    static_case("注入裸色值",
                "<style>body{color:#123456;}</style>",
                ":root{--color-dark-text:#F2F5F8;}")
    static_case("注入裸 rgb",
                '<style>body{color:rgb(1,2,3);}</style>',
                ":root{--color-dark-text:#F2F5F8;}")
    static_case("引用未定义变量",
                "<style>body{color:var(--color-nope);}</style>",
                ":root{--color-dark-text:#F2F5F8;}")
    static_case("引用字面量变量",
                "<style>body{color:var(--color-v-ab12cd34);}</style>",
                ":root{--color-v-ab12cd34:#F2F5F8;}")
    static_case("页面自立色板",
                "<style>:root{--x:#fff;}</style>",
                ":root{--color-dark-text:#F2F5F8;}")

    if sync_playwright is None:
        fails.append("自检缺 playwright，无法验真渲染（不许静默跳过）")
        return fails

    def render_case(name, html, want_red=True):
        bad = check_render(sync_playwright, html)
        hit = bool(bad)
        if hit != want_red:
            fails.append("自检[%s] 期望%s，实际%s（%s）" %
                         (name, "判红" if want_red else "判绿",
                          "判红" if hit else "判绿", bad[0] if bad else "-"))

    render_case("干净样本", GOOD_HTML, want_red=False)
    # 深底上放深字：看得见才有鬼
    render_case("深底深字",
                '<html><body style="background:#101820;color:#101820">'
                '<p>这段字跟背景一个色</p></body></html>')
    # 打印态留深块：纸上打印不出来
    render_case("打印态残留深底",
                '<html><head><style>@media print{.p{background:#101820}}'
                '</style></head><body><div class="p">深块</div></body></html>')
    return fails


# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    sync_playwright = import_playwright()

    if args.self_test:
        fails = self_test(sync_playwright)
        if fails:
            print("❌ 自检失败：")
            for f in fails:
                print("   -", f)
            return 1
        print("✅ 自检通过：6 类静态坏副本 + 3 类渲染坏副本全判红，干净样本判绿")
        return 0

    if not TPL.exists():
        print("❌ 模板不存在：%s" % TPL)
        return 1
    if not TOKENS.exists():
        print("❌ tokens.css 不存在：%s" % TOKENS)
        return 1

    text = TPL.read_text(encoding="utf-8")
    tokens_text = TOKENS.read_text(encoding="utf-8")

    bad = check_static(text, tokens_text)
    print("静态检查：%s" % ("通过" if not bad else "%d 个问题" % len(bad)))
    for b in bad:
        print("   -", b)

    if sync_playwright is None:
        bad.append("缺 playwright，真渲染检查跑不了（不许静默跳过）")
    else:
        html, err = demo_html(text, tokens_text)
        if err:
            bad.append(err)
        else:
            render_bad = check_render(sync_playwright, html)
            bad.extend(render_bad)
            print("真渲染检查：%s" % ("通过" if not render_bad
                                     else "%d 个问题" % len(render_bad)))

    if bad:
        print("\n❌ 分享报告页守卫不通过：%d 个问题" % len(bad))
        for b in bad:
            print("   -", b)
        return 1
    print("\n✅ 分享报告页守卫通过：无裸色值 / 无未定义变量 / "
          "屏幕与打印态对比度全部 >= %.1f:1" % MIN_CONTRAST)
    return 0


if __name__ == "__main__":
    sys.exit(main())
