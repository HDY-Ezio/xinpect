#!/usr/bin/env python3
"""后台窄屏骨架守卫。

背景（2026-11-09）：手机上打开后台，侧栏被 `@media (max-width:640px){.dashboard
{flex-direction:column}} .dashboard-sidebar{width:100%}` 改成整块排在正文上面，
390 宽实测侧栏 608px 高——必须先划过一整屏菜单才看得到内容。这不是"能跑就行"，
是真人一进后台就撞上的墙。

修法是侧栏收进屏幕外、用顶部工具条的☰拉出来（抽屉）。这类回归特别隐蔽：
谁再往响应式里加一句 `.dashboard{flex-direction:column}` 或把侧栏改回 width:100%，
桌面截图完全看不出来，只有真拿手机打开才知道。

所以这里钉四条：
  1. 窄屏必须存在把侧栏定位到屏幕外的规则（position: fixed + translateX(-100%)）；
  2. 任何 CSS 里都不许再给 .dashboard-sidebar 定 width: 100%（那是"压在正文上面"的写法）；
  3. 后台母版必须带抽屉三件套：工具条、☰按钮、遮罩；
  4. 抽屉样式只对后台页面生效（body 上有 dashboard-page 标记），不许污染营销页。

跑法（两种都支持）：
    python3 tests/test_dashboard_mobile.py
    python3 tests/test_dashboard_mobile.py --selftest   # 造坏自检：逐条证明判据会红
    pytest tests/test_dashboard_mobile.py -q
"""

import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = os.path.join(BASE, 'static', 'css', 'style.css')
DASH_TPL = os.path.join(BASE, 'templates', 'dashboard', 'base.html')
ROOT_TPL = os.path.join(BASE, 'templates', 'base.html')

MOBILE_MAX = 900  # 抽屉断点


class GuardFailure(Exception):
    pass


def _read(path, root=None):
    p = path if root is None else os.path.join(root, os.path.relpath(path, BASE))
    try:
        with open(p, encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        raise GuardFailure('读不到 %s: %s' % (p, e))


def _strip_comments(css):
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    return re.sub(r'^\s*//.*$', '', css, flags=re.M)


def _media_block(css, width):
    """取出 @media (max-width: <width>px) 的整块内容，允许嵌套一层花括号。"""
    m = re.search(r'@media[^{]*max-width:\s*%dpx[^{]*\{' % width, css)
    if not m:
        return None
    i = m.end()
    depth = 1
    out = []
    while i < len(css) and depth:
        ch = css[i]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if not depth:
                break
        out.append(ch)
        i += 1
    return ''.join(out)


def _rules(block, selector):
    """从样式块里找 selector 的声明体（只要有一条命中就返回该声明）。"""
    hit = []
    for m in re.finditer(r'([^{}]+)\{([^{}]*)\}', block):
        sel, decl = m.group(1), m.group(2)
        if selector in sel:
            hit.append(decl)
    return hit


def check_sidebar_offcanvas(root=None):
    css = _strip_comments(_read(CSS, root))
    block = _media_block(css, MOBILE_MAX)
    if block is None:
        raise GuardFailure('style.css 里找不到 @media (max-width: %dpx) 断点' % MOBILE_MAX)
    decls = _rules(block, '.dashboard-sidebar')
    if not decls:
        raise GuardFailure('%dpx 断点里没有 .dashboard-sidebar 的规则，窄屏侧栏会照旧占版面' % MOBILE_MAX)
    joined = ' '.join(decls)
    if 'position: fixed' not in joined:
        raise GuardFailure('%dpx 断点里 .dashboard-sidebar 不是 fixed，仍在文档流里挤正文' % MOBILE_MAX)
    if 'translateX(-100%)' not in joined.replace(' ', ''):
        raise GuardFailure('%dpx 断点里 .dashboard-sidebar 没有收到屏幕外（缺 translateX(-100%)）' % MOBILE_MAX)


def check_no_fullwidth_sidebar(root=None):
    css = _strip_comments(_read(CSS, root))
    bad = []
    for m in re.finditer(r'([^{}]+)\{([^{}]*)\}', css):
        sel, decl = m.group(1), m.group(2)
        if '.dashboard-sidebar' not in sel:
            continue
        if re.search(r'width:\s*100%', decl):
            bad.append(sel.strip().replace('\n', ' ')[:60])
    if bad:
        raise GuardFailure('有规则把 .dashboard-sidebar 拉成整行（压在正文上面）：%s' % '; '.join(bad))


def check_template_hooks(root=None):
    tpl = _read(DASH_TPL, root)
    for token, why in [
        ('dashboard-mobilebar', '缺手机工具条'),
        ('dashNavToggle', '缺☰按钮'),
        ('dashboard-backdrop', '缺抽屉遮罩'),
        ('is-nav-open', '缺抽屉打开状态的处理'),
        ('class="dashboard-page"', 'body 上没有后台标记'),
    ]:
        if token not in tpl:
            raise GuardFailure('templates/dashboard/base.html %s（%s）' % (why, token))


def check_body_mark_is_dashboard_only(root=None):
    root_tpl = _read(ROOT_TPL, root)
    if '{% block body_attr %}' not in root_tpl:
        raise GuardFailure('templates/base.html 的 <body> 上没有 body_attr 块，后台标记没地方落')
    # 营销页不能自带 dashboard-page 标记，否则手机端导航会被一起改掉
    bad = []
    for dirpath, _dirs, files in os.walk(os.path.join(root or BASE, 'templates')):
        for f in files:
            if not f.endswith('.html') or f == 'base.html':
                continue
            p = os.path.join(dirpath, f)
            if os.path.abspath(p) == os.path.abspath(DASH_TPL if root is None else os.path.join(root, 'templates/dashboard/base.html')):
                continue
            try:
                txt = open(p, encoding='utf-8').read()
            except Exception:
                continue
            if 'dashboard-page' in txt:
                bad.append(os.path.relpath(p, root or BASE))
    if bad:
        raise GuardFailure('这些模板自己写了 dashboard-page 标记，会连带改掉手机端导航：%s' % ', '.join(bad))


CHECKS = [
    ('窄屏侧栏收到屏幕外', check_sidebar_offcanvas),
    ('没有任何规则把侧栏拉成整行', check_no_fullwidth_sidebar),
    ('母版抽屉三件套齐全', check_template_hooks),
    ('后台标记只出现在后台母版', check_body_mark_is_dashboard_only),
]


def run(root=None):
    failed = 0
    for name, fn in CHECKS:
        try:
            fn(root)
            print('  ✅ %s' % name)
        except GuardFailure as e:
            failed += 1
            print('  ❌ %s：%s' % (name, e))
    return failed


def selftest():
    """造坏自检：逐条证明判据真的会红，而不是写了个永远通过的断言。"""
    import shutil
    import tempfile

    print('== 造坏自检 ==')
    src_css = _read(CSS)
    src_dash = _read(DASH_TPL)
    src_root = _read(ROOT_TPL)

    cases = [
        ('删掉 900 断点里的 .dashboard-sidebar 定位',
         lambda d: _write(d, 'static/css/style.css',
                          re.sub(r'position:\s*fixed;', 'position: static;', src_css, count=0)),
         check_sidebar_offcanvas),
        ('把侧栏改回 width: 100%',
         lambda d: _write(d, 'static/css/style.css',
                          src_css + '\n@media (max-width: 900px){ .dashboard-sidebar { width: 100%; } }\n'),
         check_no_fullwidth_sidebar),
        ('删掉☰按钮',
         lambda d: _write(d, 'templates/dashboard/base.html',
                          src_dash.replace('dashNavToggle', 'navToggleGone')),
         check_template_hooks),
        ('营销页误加 dashboard-page',
         lambda d: _write(d, 'templates/pricing.html',
                          '{% extends "base.html" %}{% block body_attr %} class="dashboard-page"{% endblock %}'),
         check_body_mark_is_dashboard_only),
    ]

    bad = 0
    for i, (label, mutate, fn) in enumerate(cases, 1):
        d = tempfile.mkdtemp(prefix='dashguard_')
        try:
            _copy_tree(d)
            mutate(d)
            # 造坏必须真的改到东西，改不动就单独报错（防止锚点失配的假自检）
            if _tree_digest(d) == _tree_digest(BASE):
                print('  ❌ 用例%d（%s）：造坏没生效，文件根本没变' % (i, label))
                bad += 1
                continue
            try:
                fn(d)
                print('  ❌ 用例%d（%s）：造坏了还判绿' % (i, label))
                bad += 1
            except GuardFailure as e:
                print('  ✅ 用例%d（%s）判红：%s' % (i, label, str(e)[:60]))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    # 好副本必须判绿
    d = tempfile.mkdtemp(prefix='dashguard_ok_')
    try:
        _copy_tree(d)
        rc = run(d)
        if rc:
            print('  ❌ 干净副本没通过（%d 条红）' % rc)
            bad += 1
        else:
            print('  ✅ 干净副本判绿')
    finally:
        shutil.rmtree(d, ignore_errors=True)
    return bad


_FILES = ['static/css/style.css', 'templates/base.html', 'templates/dashboard/base.html', 'templates/pricing.html']


def _copy_tree(dst):
    import shutil
    for rel in _FILES:
        target = os.path.join(dst, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(os.path.join(BASE, rel), target)


def _write(root, rel, text):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(text)


def _tree_digest(root):
    import hashlib
    h = hashlib.md5()
    for rel in _FILES:
        p = os.path.join(root, rel)
        h.update(open(p, 'rb').read() if os.path.exists(p) else b'')
    return h.hexdigest()


def test_dashboard_mobile_guard():
    """pytest 入口。"""
    assert run() == 0


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        sys.exit(1 if selftest() else 0)
    print('== 后台窄屏骨架守卫 ==')
    sys.exit(1 if run() else 0)
