#!/usr/bin/env python3
"""备案号合规守卫。

背景：全站上线一个多月，页脚**从没挂过** ICP 备案号（模板、静态文件、历史备份
全扫过，零命中）。依据《互联网信息服务管理办法》第十三条这是硬性违规，
而且没挂备案号的站在百度那边的信任分也会打折。

这条测试解决的不是"这次补上"，而是"以后永远不会再漏"：
  - 静态断言：凡是不 extends 别人的独立模板（真正对外的一整页），必须 include 备案片段
  - 动态断言：凡是不需要参数、不需要登录就能打开的 GET 页面，渲染结果里必须有备案号
  - 单一维护点断言：号码只允许出现在 _beian.html 一个文件里，防止多处复制导致改号漏改

跑法（服务器没装 pytest，两种都支持）：
    python3 tests/test_beian.py
    pytest tests/test_beian.py -q
"""

import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(BASE, 'templates')
BEIAN_FILE = os.path.join(TEMPLATES, '_beian.html')

ICP_NO = '湘ICP备2026029574号-2'
ICP_HOST = 'beian.miit.gov.cn'

# 不属于"对外一整页"的模板：片段、弹层、母版
_SKIP_TPL = {
    '_beian.html',        # 备案片段本体
    'onboarding.html',    # 全屏弹层，不是页面，没有页脚
    '_quota_card.html',   # 局部片段
}

# 不要求挂备案号的目录（按目录规则判定，不是逐文件白名单）。
# admin/ 是 root 运维后台，只有我们自己登录能看到，不属于《互联网信息服务管理办法》
# 里说的"对外提供服务的网站内容"，挂了纯属噪音。
_SKIP_DIRS = {'admin'}


def _read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def _tpl_files():
    """所有真正参与渲染的模板（跳过备份目录和不要求备案的目录）。"""
    out = []
    for root, dirs, files in os.walk(TEMPLATES):
        dirs[:] = [d for d in dirs
                   if not d.startswith('backup') and 'backup_' not in d
                   and d not in _SKIP_DIRS]
        for name in files:
            if name.endswith('.html'):
                out.append(os.path.join(root, name))
    return out


def test_beian_file_exists_and_links_official():
    """备案片段必须存在，且指向工信部官网。"""
    assert os.path.exists(BEIAN_FILE), '备案片段 _beian.html 不存在'
    src = _read(BEIAN_FILE)
    assert ICP_NO in src, '备案号写错或缺失：%s' % ICP_NO
    assert ICP_HOST in src, '备案号没有链接到 %s，工信部要求必须可点击跳转' % ICP_HOST
    print('    备案片段存在，链接指向工信部官网')


def test_single_source_of_truth():
    """备案号只允许出现在 _beian.html 一处。

    之前全站各处手搓品牌元素（logo 图标、页脚文案）就是吃了这个亏：
    同一个东西写在五个地方，改的时候漏一个就前后不一致。
    """
    offenders = []
    for path in _tpl_files():
        if os.path.abspath(path) == os.path.abspath(BEIAN_FILE):
            continue
        if ICP_NO in _read(path):
            offenders.append(os.path.relpath(path, BASE))
    assert not offenders, (
        '备案号被复制到了多个文件，改号会漏改。只允许写在 _beian.html：%s' % offenders
    )
    print('    备案号只有一处维护点')


def test_standalone_templates_include_beian():
    """独立页面（不 extends 别人的）必须 include 备案片段。

    继承 base.html 的页面自动有；独立页容易漏——实测就是这个原因导致
    首页和分享页原本一个都没有。

    2026-11-22 补：以下划线开头的模板是**片段**（_beian.html、_nav.html 这种
    被 include 进去的零件），不是页面，本身不该有备案号——备案号在片段里出现
    反而会变成两处维护点，正是上一条要防的事。所以片段一律不参与这项检查。
    """
    missing = []
    checked = 0
    for path in _tpl_files():
        name = os.path.basename(path)
        if name in _SKIP_TPL or name.startswith('_'):
            continue
        src = _read(path)
        if re.search(r'{%-?\s*extends\s', src):
            continue  # 继承母版，由母版负责
        checked += 1
        if '_beian.html' not in src:
            missing.append(os.path.relpath(path, BASE))
    assert not missing, '这些独立页面没有挂备案号：%s' % missing
    print('    独立页面 %d 个，全部已挂' % checked)


def test_public_pages_render_beian():
    """真正打开每一个公开页面，页面里必须能看到备案号。

    静态检查会被 include 骗过（写了 include 但母版没渲染），所以必须实跑。
    """
    sys.path.insert(0, BASE)
    cwd = os.getcwd()
    os.chdir(BASE)
    try:
        from app import app
        app.config['TESTING'] = True
        client = app.test_client()

        checked, skipped = [], []
        for rule in app.url_map.iter_rules():
            if 'GET' not in rule.methods:
                continue
            path = rule.rule
            if path.startswith(('/api/', '/static/')):
                continue
            # 和静态检查同一条规则：admin 是内部运维后台，不对外，不要求挂。
            if path.startswith('/admin'):
                skipped.append('%s (内部后台)' % path)
                continue
            if rule.arguments:
                skipped.append(path + ' (含参数)')
                continue
            resp = client.get(path)
            if resp.status_code != 200:
                skipped.append('%s (HTTP %d)' % (path, resp.status_code))
                continue
            # sitemap.xml 这类是给搜索引擎读的机器文件，不是给人看的页面。
            # 按 Content-Type 判定，不按扩展名——避免将来再加 feed/json 又要改一遍。
            ctype = (resp.headers.get('Content-Type') or '').lower()
            if 'text/html' not in ctype:
                skipped.append('%s (%s)' % (path, ctype.split(';')[0] or '非HTML'))
                continue
            html = resp.get_data(as_text=True)
            assert ICP_NO in html, '%s 渲染结果里没有备案号' % path
            assert ICP_HOST in html, '%s 的备案号没有链接到工信部' % path
            checked.append(path)

        assert len(checked) >= 8, '只校验到 %d 个页面，路由枚举可能失效' % len(checked)
        print('    实跑 %d 个公开页面，全部含备案号' % len(checked))
        if skipped:
            print('    跳过 %d 个（含参数或非 200）：%s' % (len(skipped), ', '.join(skipped[:6])))
    finally:
        os.chdir(cwd)


if __name__ == '__main__':
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    failed = 0
    for fn in tests:
        try:
            print('[RUN] %s' % fn.__name__)
            fn()
            print('  OK\n')
        except AssertionError as e:
            failed += 1
            print('  FAIL: %s\n' % e)
        except Exception as e:  # noqa: BLE001
            failed += 1
            print('  ERROR: %s: %s\n' % (type(e).__name__, e))
    print('=' * 50)
    print('%d 项通过, %d 项失败' % (len(tests) - failed, failed))
    sys.exit(1 if failed else 0)
