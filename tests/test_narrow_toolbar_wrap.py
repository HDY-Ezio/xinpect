"""一行塞很多按钮的工具条，必须允许换行。

钉住的病（2026-11-17 实证）：
报告页「问题筛选」那一行是 `display:flex` 却没有 `flex-wrap`，
在 390 宽的手机上整行宽 479px，右边两个按钮（规则 / AI）被裁到屏幕外，
既看不见也点不到——而页面主体 `overflow-x: clip`，连横滑都滑不出来。
用户截图里那面「代码墙」修好后，这一处才露出来。

判据是结构性的，不看类名：
模板里任何一个容器，只要一行里放了 5 个以上 <button>，它的样式就必须
带 flex-wrap（或自己有横向滚动），否则窄屏必然被裁。

用法：
    python3 tests/test_narrow_toolbar_wrap.py            # 校验
    python3 tests/test_narrow_toolbar_wrap.py --self-test # 造坏自检
"""
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL_DIR = os.path.join(ROOT, "templates")
CSS_DIR = os.path.join(ROOT, "static", "css")
MIN_BUTTONS = 5


def _container_buttons(html):
    """找出「一个 div 里塞了多个 button」的容器：{class_name: 按钮数}（取最多的那次）。"""
    out = {}
    for m in re.finditer(r'<div\s+class="([^"]+)"[^>]*>', html):
        cls = m.group(1).split()[0]
        depth, i, n = 1, m.end(), 0
        while i < len(html) and depth:
            nxt_open = html.find('<div', i)
            nxt_close = html.find('</div>', i)
            if nxt_close == -1:
                break
            if nxt_open != -1 and nxt_open < nxt_close:
                depth += 1
                i = nxt_open + 4
            else:
                depth -= 1
                i = nxt_close + 6
        block = html[m.end():i]
        # 只数「直接子元素」里的按钮：遇到第一个嵌套 <div 就停。
        # 不这么做的话，整页大容器（container / issues-section）会因为深处
        # 有一堆按钮而被误判成工具条。
        head = block.split('<div', 1)[0]
        cnt = len(re.findall(r'<button\b', head))
        if cnt >= MIN_BUTTONS:
            out[cls] = max(out.get(cls, 0), cnt)
    return out


def _rule_body(css, cls):
    """取出 .cls 的规则体（可能多条，拼接）。"""
    bodies = []
    for m in re.finditer(r'([^{}]*)\{([^{}]*)\}', css):
        sel, body = m.group(1), m.group(2)
        if re.search(r'\.' + re.escape(cls) + r'(?![\w-])', sel):
            bodies.append(body)
    return "\n".join(bodies)


def _all_css(html):
    """外部样式表 + 模板内联样式，一起算。内联 <style> 也常是元凶。"""
    parts = []
    for fn in sorted(os.listdir(CSS_DIR)):
        if fn.endswith(".css"):
            parts.append(open(os.path.join(CSS_DIR, fn), encoding="utf-8",
                              errors="replace").read())
    parts += re.findall(r"<style[^>]*>(.*?)</style>", html, re.S)
    return "\n".join(parts)


def scan(anchor_dir, tpl_dir=None, css_text=None):
    """返回 [(模板, 容器类名, 按钮数)]。tpl_dir/css_text 仅供自检用。"""
    tpl_dir = tpl_dir or TPL_DIR
    found = []
    for fn in sorted(os.listdir(tpl_dir)):
        if not fn.endswith(".html"):
            continue
        html = open(os.path.join(tpl_dir, fn), encoding="utf-8", errors="replace").read()
        css = css_text if css_text is not None else _all_css(html)
        for cls, cnt in _container_buttons(html).items():
            body = _rule_body(css, cls)
            if not body:
                # 样式里根本没这个类，无法判断能不能换行——按不通过处理，别装看不见
                found.append((fn, cls, cnt, "样式里找不到这个类"))
                continue
            if "flex-wrap" not in body and "overflow-x" not in body:
                found.append((fn, cls, cnt, "没有 flex-wrap，窄屏会被裁"))
    return found


def test_toolbars_can_wrap():
    found = scan(TPL_DIR)
    assert not found, "这些工具条窄屏会溢出：%r" % (found,)


def test_scan_reaches_templates():
    """确认扫到真模板：全站按钮总数不能太少，否则说明路径又错了。"""
    total = 0
    for fn in os.listdir(TPL_DIR):
        if fn.endswith(".html"):
            total += len(re.findall(r'<button\b',
                                    open(os.path.join(TPL_DIR, fn), encoding="utf-8",
                                         errors="replace").read()))
    assert total > 20, "全站只扫到 %d 个按钮，明显没扫到正文" % total


def _run_all():
    tests = [(k, v) for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
        except AssertionError as e:
            failed += 1
            print("  ❌ %s: %s" % (name, e))
        else:
            print("  ✅ %s" % name)
    return failed, len(tests)


def _self_test():
    print("=== 工具条换行守卫 · 造坏自检 ===")
    ok = True
    btns = "".join('<button class="b">%d</button>' % i for i in range(1, 7))
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "p.html"), "w", encoding="utf-8").write(
            '<div class="bar">%s</div>' % btns)
        # 1) 没有 flex-wrap：必须判红
        bad = scan(d, tpl_dir=d, css_text=".bar { display:flex; gap:8px; }")
        if bad:
            print("  ✅ 不换行被判红：%s" % (bad[0][3],))
        else:
            print("  ❌ 不换行却判绿")
            ok = False
        # 2) 有 flex-wrap：必须判绿
        good = scan(d, tpl_dir=d, css_text=".bar { display:flex; flex-wrap:wrap; }")
        if not good:
            print("  ✅ 允许换行判绿")
        else:
            print("  ❌ 允许换行却判红：%r" % (good,))
            ok = False
        # 3) 样式里根本没有这个类：必须判红，不能当通过
        none = scan(d, tpl_dir=d, css_text=".other { display:flex; }")
        if none:
            print("  ✅ 类名找不到样式时判红（不装看不见）")
        else:
            print("  ❌ 类名没样式却判绿")
            ok = False
        # 4) 按钮不够多：不该乱报
        open(os.path.join(d, "few.html"), "w", encoding="utf-8").write(
            '<div class="bar"><button>1</button><button>2</button></div>')
        few = [x for x in scan(d, tpl_dir=d, css_text=".bar { display:flex; }")
               if x[0] == "few.html"]
        if not few:
            print("  ✅ 只有两个按钮时不误报")
        else:
            print("  ❌ 两个按钮也报：%r" % (few,))
            ok = False
    print("造坏自检:", "✅ 全部通过" if ok else "❌ 有项目没通过")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(_self_test())
    failed, total = _run_all()
    print("\n%s %d/%d 通过" % ("✅" if failed == 0 else "❌", total - failed, total))
    sys.exit(0 if failed == 0 else 1)
