#!/usr/bin/env python3
"""颜色真值与真渲染守卫（2026-11-08）。

背景：11-06 把全站颜色收进 tokens.css 时，style.css 里那份 :root 副本
被自动替换写成 `--x: var(--x)` 自引用。style.css 后加载覆盖 tokens.css，
浏览器把自引用变量判为无效，首页之外的内页整片失色。
当时的验收只查「页面打得开、字在不在」，查不出「人眼看到什么颜色」。

本守卫钉死三件事：
  1) 变量依赖图：自引用 / 循环依赖 / 最终生效值里失效变量，必须为 0。
  2) 单一事实来源：除 tokens.css 外，css/ 下不许再有 :root 变量定义；
     tokens.css 必须是 base.html 的第一份样式表。
  3) 真渲染：无头浏览器取计算样式，颜色变量不为空、按钮底色不透明。

--self-test 用内置最小样本造 4 类坏副本，必须全判红；干净样本必须判绿。
自检不依赖当前生产状态，也不读任何固定临时文件。
"""
import argparse
import glob
import re
import shutil
import sys
import tempfile
from pathlib import Path

SITE = Path("/opt/xinpect-website")
ROOT_RE = re.compile(r":root\s*\{([^}]*)\}", re.S)
DECL_RE = re.compile(r"(--[A-Za-z0-9_-]+)\s*:\s*([^;]+);")
VAR_REF_RE = re.compile(r"var\(\s*(--[A-Za-z0-9_-]+)")
CSS_LINK_RE = re.compile(r"css/([\w.-]+\.css)")

TOKENS_MIN = (":root{\n"
              "--color-bg-secondary:#1A2B4A;--color-bg-primary:#FFFFFF;--primary:#1A2B4A;\n"
              "--color-bg-tertiary:#F5F7FA;--color-text-primary:#1A2B4A;--color-text-secondary:#6B7B94;\n"
              "--color-border:#E0E6ED;--color-accent-steel:#3E5C8A;--color-success:#52C41A;\n"
              "--color-danger:#F5222D;--color-warning:#FAAD14;--color-info:#1890FF;\n"
              "}\n")
STYLE_MIN = "body{background:var(--color-bg-primary);color:var(--color-bg-secondary);}\n"
BASE_MIN = """<!DOCTYPE html><html><head>
<link rel="stylesheet" href="/static/css/tokens.css?v=20261106">
<link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
</head><body></body></html>
"""


def root_decls(text):
    out = {}
    for block in ROOT_RE.findall(text):
        for k, v in DECL_RE.findall(block):
            out[k] = v.strip()
    return out


def cycles(final):
    """返回所有因自引用/循环依赖而失效的变量名。"""
    graph = {k: VAR_REF_RE.findall(v) for k, v in final.items()}
    bad = set()
    for start in list(graph):
        stack = [start]
        visited = set()

        def walk(node):
            for dep in graph.get(node, []):
                if dep in stack:
                    bad.update(stack[stack.index(dep):])
                    bad.add(dep)
                    continue
                if dep in graph and dep not in visited:
                    visited.add(dep)
                    stack.append(dep)
                    walk(dep)
                    stack.pop()

        walk(start)
    # 传递失效：依赖到坏变量的也失效
    changed = True
    while changed:
        changed = False
        for k, deps in graph.items():
            if k not in bad and any(d in bad for d in deps):
                bad.add(k)
                changed = True
    return bad


def css_order(base_text):
    order = []
    for line in base_text.splitlines():
        if "stylesheet" not in line:
            continue
        m = CSS_LINK_RE.search(line)
        if m:
            order.append(m.group(1))
    return order


def check_static(site: Path):
    errors = []
    css_dir = site / "static" / "css"
    tokens_path = css_dir / "tokens.css"
    base_path = site / "templates" / "base.html"

    for p in (tokens_path, base_path, css_dir / "style.css"):
        if not p.is_file():
            errors.append(f"缺文件: {p}")
    if errors:
        return errors

    tokens = root_decls(tokens_path.read_text(encoding="utf-8"))
    if len(tokens) < 10:
        errors.append(f"tokens.css 变量太少({len(tokens)})，疑似被清空")
        return errors

    # G4: 单一事实来源——其它 css 不许再定义 :root 变量
    for f in sorted(css_dir.glob("*.css")):
        if f.name == "tokens.css":
            continue
        d = root_decls(f.read_text(encoding="utf-8"))
        if d:
            errors.append(f"G4 {f.name} 重复定义了 {len(d)} 个 :root 变量"
                          f"（唯一事实来源是 tokens.css）: {sorted(d)[:6]}")

    # G6: tokens.css 必须是 base.html 第一份样式表
    base_text = base_path.read_text(encoding="utf-8")
    order = css_order(base_text)
    if not order or order[0] != "tokens.css":
        errors.append(f"G6 base.html 样式表顺序错误，tokens.css 必须在最前: {order}")
    if "style.css" not in order:
        errors.append("G6 base.html 未加载 style.css")

    # G1/G2/G3: 按真实加载顺序合并，检查最终生效值
    merged = {}
    for name in order:
        p = css_dir / name
        if p.is_file():
            merged.update(root_decls(p.read_text(encoding="utf-8")))
    selfref = sorted(k for k, v in merged.items()
                     if v.strip() == f"var({k})")
    if selfref:
        errors.append(f"G1 自引用变量 {len(selfref)} 个: {selfref[:8]}")
    bad = cycles(merged)
    if bad:
        errors.append(f"G2/G3 循环依赖导致 {len(bad)} 个变量失效: {sorted(bad)[:8]}")
    missing = sorted(set(tokens) - set(merged))
    if missing:
        errors.append(f"G3 tokens.css 定义的变量在合并后消失 {len(missing)} 个: {missing[:8]}")
    return errors


def find_chromium():
    env = __import__("os").environ.get("XP_CHROMIUM")
    if env and Path(env).is_file():
        return env
    cands = sorted(glob.glob("/home/ubuntu/.cache/ms-playwright/chromium-*/chrome-linux64/chrome"))
    cands += sorted(glob.glob("/root/.cache/ms-playwright/chromium-*/chrome-linux64/chrome"))
    return cands[-1] if cands else None


def import_playwright():
    """QA 以 root 跑时，用户级安装的 playwright 不在 sys.path 里。

    从机器上真实存在的用户级 site-packages 里找，不写死版本号；
    找不到就返回 None，由调用方判红，绝不静默跳过渲染检查。
    """
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        pass
    found = []
    for base in ("/home/*/.local/lib/python3*/site-packages",
                 "/usr/local/lib/python3*/dist-packages",
                 "/usr/lib/python3/dist-packages"):
        found.extend(sorted(glob.glob(base)))
    for p in found:
        if p not in sys.path and (Path(p) / "playwright").is_dir():
            sys.path.insert(0, p)
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        return None


def check_render(base_url):
    errors = []
    sync_playwright = import_playwright()
    if sync_playwright is None:
        return ["G5 缺 playwright，无法做真渲染检查（不许静默跳过）"]
    exe = find_chromium()
    if not exe:
        return ["G5 找不到 chromium 可执行文件，无法做真渲染检查"]

    probe = r"""() => {
      const root = getComputedStyle(document.documentElement);
      const v = (n) => (root.getPropertyValue(n) || '').trim();
      const btn = document.querySelector('.btn-primary');
      const b = btn ? getComputedStyle(btn) : null;
      return {
        bg2: v('--color-bg-secondary'),
        bg1: v('--color-bg-primary'),
        bodyBG: getComputedStyle(document.body).backgroundColor,
        btnBG: b ? b.backgroundColor : null,
      };
    }"""
    transparent = {"rgba(0, 0, 0, 0)", "transparent", ""}
    saw_button = False
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=exe,
                                        args=["--no-sandbox"])
            ctx = browser.new_context(viewport={"width": 1280, "height": 800})
            for path in ("/try", "/login", "/pricing"):
                page = ctx.new_page()
                try:
                    resp = page.goto(base_url.rstrip("/") + path,
                                     wait_until="load", timeout=25000)
                    if not resp or resp.status != 200:
                        errors.append(f"G5 {path} HTTP {resp.status if resp else '?'}")
                        page.close()
                        continue
                    page.wait_for_timeout(250)
                    r = page.evaluate(probe)
                    if not r["bg2"] or r["bg2"].startswith("var("):
                        errors.append(f"G5 {path} 主色变量为空/未解析: {r['bg2']!r}")
                    if r["bodyBG"] in transparent:
                        errors.append(f"G5 {path} body 背景透明: {r['bodyBG']}")
                    if r["btnBG"] is not None:
                        saw_button = True
                        if r["btnBG"] in transparent:
                            errors.append(f"G5 {path} 主按钮底色透明: {r['btnBG']}")
                    print(f"    {path:10s} bg2={r['bg2'] or '(空)':10s} "
                          f"body={r['bodyBG']:22s} btn={r['btnBG']}")
                except Exception as e:
                    errors.append(f"G5 {path} 渲染异常: {type(e).__name__}: {e}"[:180])
                finally:
                    page.close()
            ctx.close()
            browser.close()
    except Exception as e:
        errors.append(f"G5 浏览器启动失败: {type(e).__name__}: {e}"[:180])
    if not saw_button:
        errors.append("G5 三页都没找到 .btn-primary，等于没检查按钮颜色")
    return errors


def make_min_site(dest: Path):
    (dest / "static" / "css").mkdir(parents=True)
    (dest / "templates").mkdir(parents=True)
    (dest / "static" / "css" / "tokens.css").write_text(TOKENS_MIN, encoding="utf-8")
    (dest / "static" / "css" / "style.css").write_text(STYLE_MIN, encoding="utf-8")
    (dest / "templates" / "base.html").write_text(BASE_MIN, encoding="utf-8")
    return dest


def self_test():
    results = []

    def case(name, mutate, should_fail):
        tmp = Path(tempfile.mkdtemp(prefix="cssguard_"))
        try:
            make_min_site(tmp)
            mutate(tmp)
            errs = check_static(tmp)
            ok = (bool(errs) == should_fail)
            results.append((name, ok, errs))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    case("干净样本必须判绿", lambda d: None, False)
    case("A style.css 注入自引用必须判红", lambda d: (
        (d / "static/css/style.css").write_text(
            ":root{--color-bg-secondary:var(--color-bg-secondary);}\n" + STYLE_MIN,
            encoding="utf-8")), True)
    case("B style.css 重新定义 :root 必须判红", lambda d: (
        (d / "static/css/style.css").write_text(
            ":root{--primary:#111111;}\n" + STYLE_MIN, encoding="utf-8")), True)
    case("C base.html 去掉 tokens.css 必须判红", lambda d: (
        (d / "templates/base.html").write_text(
            BASE_MIN.replace(
                '<link rel="stylesheet" href="/static/css/tokens.css?v=20261106">\n', ''),
            encoding="utf-8")), True)
    case("D 加载顺序颠倒必须判红", lambda d: (
        (d / "templates/base.html").write_text(
            BASE_MIN.replace(
                '<link rel="stylesheet" href="/static/css/tokens.css?v=20261106">\n'
                '<link rel="stylesheet" href="{{ url_for(\'static\', filename=\'css/style.css\') }}">',
                '<link rel="stylesheet" href="/static/css/style.css">\n'
                '<link rel="stylesheet" href="/static/css/tokens.css?v=20261106">'),
            encoding="utf-8")), True)
    case("E tokens.css 被清空必须判红", lambda d: (
        (d / "static/css/tokens.css").write_text(":root{}\n", encoding="utf-8")), True)

    failed = 0
    for name, ok, errs in results:
        print(f"  [{'OK' if ok else 'FAIL'}] {name}"
              + (f"  命中 {len(errs)} 条" if errs else ""))
        if not ok:
            failed += 1
            for e in errs[:3]:
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
        print("=== 颜色真值守卫自检（内置最小样本，不依赖生产状态）===")
        return self_test()

    site = Path(a.root)
    print(f"=== 颜色真值守卫 站点={site} ===")
    errors = check_static(site)
    if not a.no_render:
        print("  -- 真渲染取计算样式 --")
        errors += check_render(a.base_url)
    for e in errors:
        print(f"  [FAIL] {e}")
    if errors:
        print(f"\n❌ 颜色真值守卫失败: {len(errors)} 条")
        return 1
    print("\n✅ 颜色真值守卫通过: 变量依赖 0 环、单一来源、真渲染有颜色")
    return 0


if __name__ == "__main__":
    sys.exit(main())
