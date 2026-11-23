"""模板「属性块」守卫：被塞进标签属性里的块，不许带标记或双引号。

钉住的病（2026-11-17 实证）：
母版 base.html 把标题块的内容同时用在两处——
  <title>{% block title %}...{% endblock %}</title>
  <meta property="og:title" content="{{ self.title() }}">
第二处是标签属性。self.title() 返回的是已标记安全的 Markup，不会再转义，
所以只要标题块里混进了 <style> / <script>，属性会被脚本里的第一个双引号截断，
截断之后的脚本源码就被浏览器当成正文文字显示在页面上。

report.html 就是这么中的：{% block title %} 被写成跨 105 行的大块，
把整段 <style> 和 <script> 圈了进去，于是每个访客看到的报告页里
都摊着一大段 JavaScript 源码（用户 11-17 截图即为现场）。

这里不写死「哪些块算属性块」，而是从母版自己读出来——
以后谁往别的属性里塞块，守卫自动覆盖，不用改这份清单。
"""
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL_DIR = os.path.join(_ROOT, "templates")
BASE = "base.html"
BACKUP_OLD_REPORT = "/var/backups/xinpect/report.html.bak_titleblock_20261117"

BLOCK_RE = re.compile(r"{%\s*block\s+(\w+)\s*%}(.*?){%\s*endblock", re.S)


def attr_block_names(base_html):
    """从母版读出「内容会落进标签属性」的块名。

    两种写法都算：
      content="{% block og_title %}...{% endblock %}"   —— 块直接写在属性里
      content="{{ self.title() }}"                      —— 属性里引用另一个块
    """
    names = set()
    for m in re.finditer(r'=\s*"{%\s*block\s+(\w+)', base_html):
        names.add(m.group(1))
    for m in re.finditer(r'<[a-zA-Z][^>]*=\s*"[^"]*\{\{\s*self\.(\w+)\(\)', base_html, re.S):
        names.add(m.group(1))
    return names


def violations_in(html, attr_names):
    """返回 [(块名, 原因)]。属性里出现标记或双引号都会撑破属性。"""
    out = []
    for name, body in BLOCK_RE.findall(html):
        if name not in attr_names:
            continue
        if "<" in body:
            tag = re.findall(r"<[^>\n]{0,20}", body)[:2]
            out.append((name, "含标记 %r，会撑破属性" % tag))
        elif '"' in body:
            out.append((name, "含双引号，会撑破属性"))
    return out


def scan_dir(path, base_name=BASE):
    """扫一个模板目录，返回 [(文件, 块名, 原因)]。母版缺失直接报错，不静默放过。"""
    base_path = os.path.join(path, base_name)
    if not os.path.exists(base_path):
        raise AssertionError("母版不存在：%s（没有母版就没法判断哪些块进属性）" % base_path)
    attr_names = attr_block_names(open(base_path, encoding="utf-8", errors="replace").read())
    if not attr_names:
        raise AssertionError("母版里没读出任何属性块——判据失效，不能当通过")

    found = []
    for fn in sorted(os.listdir(path)):
        if not fn.endswith(".html"):
            continue
        txt = open(os.path.join(path, fn), encoding="utf-8", errors="replace").read()
        for name, reason in violations_in(txt, attr_names):
            found.append((fn, name, reason))
    return found, attr_names


# --------------------------------------------------------------------------
# 测试
# --------------------------------------------------------------------------
def test_no_markup_in_attribute_blocks():
    """全站模板：属性块里不许带标记 / 双引号。"""
    found, names = scan_dir(TPL_DIR)
    assert names, "没读出属性块清单"
    assert not found, "属性块里混进了标记，会在页面上漏出源码：%r" % (found,)


def test_scan_covers_real_pages():
    """确认扫的是真模板目录，块数不能太少（防止路径错了还绿）。"""
    total = 0
    for fn in os.listdir(TPL_DIR):
        if fn.endswith(".html"):
            total += len(BLOCK_RE.findall(
                open(os.path.join(TPL_DIR, fn), encoding="utf-8", errors="replace").read()))
    assert total > 80, "全站模板里的块只有 %d 个，明显没扫到正文" % total


def test_old_report_template_is_flagged():
    """真数据回归：出事那一版 report.html 必须被判红（否则守卫没有判别力）。"""
    if not os.path.exists(BACKUP_OLD_REPORT):
        return  # 备份被清理后不再要求，但当前环境里它应该在
    found, _names = scan_dir(TPL_DIR)
    old = open(BACKUP_OLD_REPORT, encoding="utf-8", errors="replace").read()
    _f, names = scan_dir(TPL_DIR)
    bad = violations_in(old, names)
    assert bad, "出事那一版模板居然判不出问题——判据失效"


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


# --------------------------------------------------------------------------
# 造坏自检：守卫自己不会红，等于没有
# --------------------------------------------------------------------------
def _self_test():
    import tempfile
    print("=== 模板属性块守卫 · 造坏自检 ===")
    ok = True

    base = ('<html><head>\n'
            '<title>{% block title %}默认{% endblock %}</title>\n'
            '<meta property="og:title" content="{{ self.title() }}">\n'
            '<meta name="description" content="{% block meta_description %}默{% endblock %}">\n'
            '</head><body>{% block content %}{% endblock %}</body></html>\n')

    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "base.html"), "w", encoding="utf-8").write(base)

        # 1) 正常模板：标题只写文字，必须判绿
        open(os.path.join(d, "good.html"), "w", encoding="utf-8").write(
            '{% extends "base.html" %}\n{% block title %}检测报告 - 煋鉴{% endblock %}\n'
            '{% block content %}<h1>正文</h1>{% endblock %}\n')
        found, names = scan_dir(d)
        if found:
            print("  ❌ 正常模板被判红：%r" % (found,))
            ok = False
        else:
            print("  ✅ 正常模板判绿（属性块：%s）" % ",".join(sorted(names)))

        # 2) 复刻出事写法：标题块里混进 <style>/<script>，必须判红
        open(os.path.join(d, "bad.html"), "w", encoding="utf-8").write(
            '{% extends "base.html" %}\n'
            '{% block title %}检测报告</title>\n<style>.a{}</style>\n'
            '<script>var s = "x";</script>\n{% endblock %}\n'
            '{% block content %}<h1>正文</h1>{% endblock %}\n')
        found, _ = scan_dir(d)
        if any(f[0] == "bad.html" and f[1] == "title" for f in found):
            print("  ✅ 复刻出事写法被判红：%s" % found[0][2])
        else:
            print("  ❌ 复刻出事写法没判红——守卫瞎了：%r" % (found,))
            ok = False
        os.remove(os.path.join(d, "bad.html"))

        # 3) 新块自动覆盖：母版里新增一个属性块，子模板里带标记，必须判红
        open(os.path.join(d, "base.html"), "w", encoding="utf-8").write(
            base.replace('</head>',
                         '<meta name="author" content="{% block meta_author %}x{% endblock %}">\n</head>'))
        open(os.path.join(d, "newattr.html"), "w", encoding="utf-8").write(
            '{% extends "base.html" %}\n{% block meta_author %}<b>带标记</b>{% endblock %}\n'
            '{% block content %}x{% endblock %}\n')
        found, names2 = scan_dir(d)
        if "meta_author" in names2 and any(f[1] == "meta_author" for f in found):
            print("  ✅ 母版新增属性块后自动纳入检查")
        else:
            print("  ❌ 新增属性块没被自动检查：names=%r found=%r" % (names2, found))
            ok = False

        # 4) 母版缺了必须报错，不许当通过
        os.remove(os.path.join(d, "base.html"))
        try:
            scan_dir(d)
        except AssertionError as e:
            print("  ✅ 母版缺失时报错而不是放绿：%s" % str(e)[:40])
        else:
            print("  ❌ 母版缺失竟然判绿")
            ok = False

    print("造坏自检:", "✅ 全部通过" if ok else "❌ 有项目没通过")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(_self_test())
    failed, total = _run_all()
    print("\n%s %d/%d 通过" % ("✅" if failed == 0 else "❌", total - failed, total))
    sys.exit(0 if failed == 0 else 1)
