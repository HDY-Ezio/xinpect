#!/usr/bin/env python3
"""窄屏栅格 / 表格横滑 / 等级徽章对比度 三条守卫。

为什么要有这一份：
1. 模板里内联 `grid-template-columns: repeat(5,1fr)` 这种写死列数的写法，
   在 320 宽手机上一列只剩几十像素，右侧 3 张卡被裁到屏幕外、手指也滑不到，
   等于内容丢失（定价页积分包真踩过）。而且 `1fr` 的最小尺寸是内容宽度，
   里面 300px 的图表能把整列撑到 350，更糟。规则：栅格要么用类，
   要么用 auto-fit/auto-fill/minmax，不许写死列数。
2. 后台宽表格没有自己的滚动容器时，会把整块正文撑出横向滚动，
   手指一滑连页面标题都跟着跑。规则：宽表格必须包在 .table-scroll 里。
3. 等级徽章是白字压在等级色上，等级色一旦调浅，字就糊在底上。
   规则：五种等级色的白字对比度必须 ≥ 4.5。

注意：颜色解析必须支持 oklch——tokens.css 里白字就是 `oklch(1 0 0)`。
早先审计脚本用正则抓数字，把 oklch(1 0 0) 当成 rgb(1,0,0)（近黑），
凭空报出 268 条「浅字」假警报。这里用标准公式换算，并有自测钉住。

用法：
    python3 tests/test_mobile_responsive.py            # 正常校验
    python3 tests/test_mobile_responsive.py --selftest # 造坏自检，必须全判红
"""
import math
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKENS = os.path.join(ROOT, "static", "css", "tokens.css")
STYLE = os.path.join(ROOT, "static", "css", "style.css")
TPL_DIR = os.path.join(ROOT, "templates")

GRADES = ["s", "a", "b", "c", "d"]
MIN_RATIO = 4.5


# ---------- 颜色 ----------

def _srgb_to_linear(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def rel_lum(rgb):
    r, g, b = (_srgb_to_linear(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = rel_lum(a), rel_lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _gamma(x):
    x = max(0.0, min(1.0, x))
    v = 1.055 * (x ** (1 / 2.4)) - 0.055 if x > 0.0031308 else 12.92 * x
    return max(0, min(255, round(v * 255)))


def oklch_to_rgb(L, C, H):
    """OKLCh -> sRGB。公式来自 CSS Color 4 规范。"""
    h = math.radians(H)
    a = C * math.cos(h)
    b = C * math.sin(h)
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    bb = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s
    return (_gamma(r), _gamma(g), _gamma(bb))


def parse_color(value):
    """把一个 CSS 颜色字面量转成 (r,g,b)。不认识的返回 None。"""
    v = (value or "").strip().rstrip(";")
    if not v:
        return None
    m = re.match(r"^#([0-9a-fA-F]{6})$", v)
    if m:
        h = m.group(1)
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    m = re.match(r"^#([0-9a-fA-F]{3})$", v)
    if m:
        h = m.group(1)
        return tuple(int(c * 2, 16) for c in h)
    m = re.match(r"^rgba?\(([^)]+)\)$", v)
    if m:
        parts = [p.strip() for p in m.group(1).split(",")]
        if len(parts) >= 3:
            try:
                return tuple(int(round(float(p))) for p in parts[:3])
            except ValueError:
                return None
    m = re.match(r"^oklch\(\s*([\d.]+%?)\s+([\d.]+%?)\s+([\d.]+)", v)
    if m:
        def num(s, scale):
            return float(s[:-1]) / 100.0 * scale if s.endswith("%") else float(s)
        L = num(m.group(1), 1.0)
        C = num(m.group(2), 0.4)
        H = float(m.group(3))
        return oklch_to_rgb(L, C, H)
    return None


def read_tokens(path=TOKENS):
    text = open(path, encoding="utf-8").read()
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    out = {}
    for m in re.finditer(r"(--[\w-]+)\s*:\s*([^;{}]+);", text):
        out.setdefault(m.group(1), m.group(2).strip())
    return out


def resolve(name, tokens, depth=0):
    """解开 var() 链，返回 (r,g,b) 或 None。"""
    if depth > 12 or name not in tokens:
        return None
    val = tokens[name].strip()
    m = re.match(r"^var\(\s*(--[\w-]+)\s*(?:,\s*(.+))?\)$", val)
    if m:
        got = resolve(m.group(1), tokens, depth + 1)
        if got:
            return got
        return parse_color(m.group(2)) if m.group(2) else None
    return parse_color(val)


# ---------- 三条判据 ----------

FIXED_TRACK = re.compile(r"grid-template-columns\s*:\s*([^;\"]+)")


def is_fixed_tracks(value):
    v = value.strip().lower()
    if "auto-fit" in v or "auto-fill" in v or "minmax(" in v:
        return False
    # repeat(5,1fr)、1fr 1fr、2fr 1fr、repeat(4,minmax(0,1fr)) 都算写死
    return bool(re.search(r"repeat\(\s*\d+\s*,", v) or re.search(r"\d*fr\b", v))


def check_inline_grids(root=TPL_DIR):
    bad = []
    for dirpath, _dirs, files in os.walk(root):
        if "__pycache__" in dirpath:
            continue
        for fn in files:
            if not fn.endswith(".html"):
                continue
            path = os.path.join(dirpath, fn)
            try:
                text = open(path, encoding="utf-8").read()
            except OSError as e:
                bad.append("%s 读不了: %s" % (os.path.relpath(path, ROOT), e))
                continue
            for lineno, line in enumerate(text.split("\n"), 1):
                if "style=" not in line:
                    continue
                for m in FIXED_TRACK.finditer(line):
                    if is_fixed_tracks(m.group(1)):
                        bad.append("%s:%d 内联写死栅格列数（%s）——用 .grid-2/.grid-3/.grid-4/.grid-2-1 "
                                   "或 auto-fit/minmax，否则窄屏会把右边几列裁掉"
                                   % (os.path.relpath(path, ROOT), lineno, m.group(1).strip()[:40]))
    return bad


def check_grid_collapse(style_path=STYLE):
    text = open(style_path, encoding="utf-8").read()
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    bad = []
    for cls in (".grid-2", ".grid-3", ".grid-4", ".grid-2-1"):
        if not re.search(re.escape(cls) + r"\s*\{", text):
            bad.append("style.css 缺少 %s 定义" % cls)
    # 折叠必须在 ≤900px 的媒体块里，且用 minmax(0,1fr)
    found = False
    for m in re.finditer(r"@media\s*\(max-width:\s*(\d+)px\)\s*\{", text):
        if int(m.group(1)) > 900:
            continue
        start = m.end()
        depth = 1
        i = start
        while i < len(text) and depth:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        block = text[start:i]
        if re.search(r"\.grid-2[^-]", block) and "minmax(0, 1fr)" in block:
            found = True
            break
    if not found:
        bad.append("≤900px 的媒体块里没有 `.grid-2 { grid-template-columns: minmax(0, 1fr) }` 折叠规则，"
                   "窄屏栅格不会塌成一列")
    return bad


def check_table_wrapper(root=os.path.join(TPL_DIR, "dashboard")):
    bad = []
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            if not fn.endswith(".html"):
                continue
            path = os.path.join(dirpath, fn)
            text = open(path, encoding="utf-8").read()
            if '<table class="data-table">' not in text:
                continue
            if '<div class="table-scroll">' not in text:
                bad.append("%s 有 .data-table 但没有 .table-scroll 横滑容器——"
                           "窄屏会把整块正文撑出横向滚动"
                           % os.path.relpath(path, ROOT))
    return bad


def check_badge_contrast(tokens_path=TOKENS):
    tokens = read_tokens(tokens_path)
    text_rgb = resolve("--color-v-f46b78eeb", tokens)
    if not text_rgb:
        return ["徽章字色 --color-v-f46b78eeb 解不出来（tokens.css 结构变了？）"]
    bad = []
    for g in GRADES:
        name = "--color-grade-%s" % g
        bg = resolve(name, tokens)
        if not bg:
            bad.append("%s 解不出来" % name)
            continue
        ratio = contrast(text_rgb, bg)
        if ratio < MIN_RATIO:
            bad.append("%s 级徽章字底对比度只有 %.2f（要 ≥%.1f）——等级色调浅了，白字会糊"
                       % (g.upper(), ratio, MIN_RATIO))
    return bad


# ---------- 造坏自检 ----------

def selftest():
    """故意造坏，确认每条判据都会判红。任何一条造坏后还绿，就是守卫失灵。"""
    tmp = tempfile.mkdtemp(prefix="mobileguard_")
    results = []

    def expect_red(name, fn):
        try:
            bad = fn()
        except Exception as e:  # 造坏副本本身出错也要算失败
            results.append((name, False, "抛异常: %s" % e))
            return
        results.append((name, bool(bad), "；".join(bad[:2]) if bad else "没报错（守卫失灵）"))

    # 1. 内联写死列数
    d1 = os.path.join(tmp, "tpl1")
    os.makedirs(d1)
    open(os.path.join(d1, "x.html"), "w", encoding="utf-8").write(
        '<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:16px;"></div>')
    expect_red("内联 repeat(5,1fr) 判红", lambda: check_inline_grids(d1))

    d1b = os.path.join(tmp, "tpl1b")
    os.makedirs(d1b)
    open(os.path.join(d1b, "y.html"), "w", encoding="utf-8").write(
        '<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;"></div>')
    expect_red("内联 1fr 1fr 判红", lambda: check_inline_grids(d1b))

    # 2. 自适应写法必须放行（否则守卫等于逼人写死列数）
    d2 = os.path.join(tmp, "tpl2")
    os.makedirs(d2)
    open(os.path.join(d2, "z.html"), "w", encoding="utf-8").write(
        '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));"></div>')
    bad = check_inline_grids(d2)
    results.append(("auto-fit 写法放行", not bad, "误报" if bad else "正常"))

    # 3. 折叠规则缺失
    s3 = os.path.join(tmp, "style3.css")
    open(s3, "w", encoding="utf-8").write(
        ".grid-2 { display:grid; grid-template-columns: repeat(2, minmax(0,1fr)); }\n"
        ".grid-3 { display:grid; }\n.grid-4 { display:grid; }\n.grid-2-1 { display:grid; }\n")
    expect_red("缺 900px 折叠规则判红", lambda: check_grid_collapse(s3))

    # 4. 折叠写成 1fr（min-content 会撑破）
    s4 = os.path.join(tmp, "style4.css")
    open(s4, "w", encoding="utf-8").write(
        ".grid-2{display:grid}.grid-3{display:grid}.grid-4{display:grid}.grid-2-1{display:grid}\n"
        "@media (max-width: 900px) { .grid-2, .grid-3, .grid-4, .grid-2-1 "
        "{ grid-template-columns: 1fr; } }\n")
    expect_red("折叠写成 1fr 判红", lambda: check_grid_collapse(s4))

    # 5. 表格没包容器
    d5 = os.path.join(tmp, "tpl5")
    os.makedirs(d5)
    open(os.path.join(d5, "t.html"), "w", encoding="utf-8").write(
        '<table class="data-table"><tr><td>x</td></tr></table>')
    expect_red("表格缺横滑容器判红", lambda: check_table_wrapper(d5))

    # 6. 等级色调浅 -> 白字不够
    t6 = os.path.join(tmp, "tokens6.css")
    src = open(TOKENS, encoding="utf-8").read()
    src = src.replace("--color-grade-b: #17707E;", "--color-grade-b: #8FD8E8;")
    open(t6, "w", encoding="utf-8").write(src)
    expect_red("等级色调浅判红", lambda: check_badge_contrast(t6))

    # 7. oklch 白字必须解成纯白（钉住那个假警报的真因）
    white = parse_color("oklch(1 0 0)")
    ok = white == (255, 255, 255)
    results.append(("oklch(1 0 0) 解成纯白", ok, "解成 %s" % (white,)))

    print("=== 造坏自检 ===")
    allok = True
    for name, ok, msg in results:
        print(("✅ " if ok else "❌ ") + name + ("  " + msg if msg else ""))
        if not ok:
            allok = False
    print("自检结果:", "全部符合预期" if allok else "有判据失灵")
    return 0 if allok else 1


def main():
    if "--selftest" in sys.argv:
        return selftest()
    fails = []
    fails += check_inline_grids()
    fails += check_grid_collapse()
    fails += check_table_wrapper()
    fails += check_badge_contrast()
    if fails:
        print("❌ 窄屏/徽章守卫不通过：")
        for f in fails:
            print("   -", f)
        return 1
    print("✅ 窄屏栅格、表格横滑、等级徽章对比度全部通过")
    return 0


# ---------- pytest 入口 ----------
# 必须写成 test_* 函数：QA 套件是用 pytest 跑这份名单的，
# 只有 __main__ 的话进名单也只算「收集到 0 个用例」，等于守卫没生效。

def test_no_hardcoded_grid_columns():
    fails = check_inline_grids()
    assert not fails, "\n".join(fails)


def test_grid_collapses_on_narrow_screen():
    fails = check_grid_collapse()
    assert not fails, "\n".join(fails)


def test_wide_tables_have_scroll_container():
    fails = check_table_wrapper()
    assert not fails, "\n".join(fails)


def test_grade_badge_contrast():
    fails = check_badge_contrast()
    assert not fails, "\n".join(fails)


if __name__ == "__main__":
    sys.exit(main())
