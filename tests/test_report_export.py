#!/usr/bin/env python3
"""报告导出守卫：HTML 下载与 PDF 打印必须「真能出东西」。

背景（2026-11-04 夜）：
  `/report/<scan_id>/html` 这个路由写好了、也注册了，但它去引擎取
  `/report/<id>` —— 引擎从来没有这个路由（带 API Key 实测 404），
  模板里也没有任何地方指向它。也就是说：功能存在、接口存在、页面 200，
  但**没有任何一个真人走得到**，谁点谁看「报告生成失败」。

  同一张页面上还有第二种「做了没接线」：`.pdf-export-btn` 的样式、
  `@media print` 的整套打印规则都写完了，但页面上根本没有这个按钮。

这里守四件事：
  1. 导出件必须是**同一份渲染**（不许再出现第二套数字）
  2. 导出件必须能离线打开（要有 <base>，否则样式/图片全丢）
  3. 导出件必须是附件下载（Content-Disposition），不是又一个网页
  4. 页面上必须真有这两个入口（按钮存在且指向正确的地方）

跑法：pytest tests/test_report_export.py -q
     或 python3 tests/test_report_export.py（没装 pytest 时）
"""

import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SID = 'exp0rt0000000000000000000000test'


# ---------------------------------------------------------------- 桩

class _StubCursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row

    def fetchall(self):
        return []


class _StubDB:
    def __init__(self, row):
        self._row = row

    def execute(self, *a, **k):
        return _StubCursor(self._row)

    def commit(self):
        pass

    def close(self):
        pass


def _results(issues, engines=None):
    payload = {'issues': issues, 'style_issues': []}
    if engines is not None:
        payload['engines'] = engines
    return json.dumps(payload)


def _scan_row(**kw):
    row = {
        'scan_id': SID,
        'title': '导出守卫测试',
        'file_count': 2,
        'issue_count': 1,
        'created_at': '2026-11-04 08:00:00',
        'results': _results([
            {'brain_id': '2', 'brain_name': '安全检测', 'rule_id': 'E2-SEC-SQL-001',
             'title': 'SQL注入风险', 'severity': 'high', 'file': 'a.py', 'line': 3,
             'category': 'security'},
        ], engines={'2': {'executed': True, 'issues': 1, 'error': ''}}),
        'score': 70,
        'grade': 'B',
        'scan_mode': 'deep',
        'share_token': 'tok-export-test',
        'user_id': None,
        'team_id': None,
    }
    row.update(kw)
    return row


def _app():
    sys.path.insert(0, BASE)
    from app import app
    app.config['TESTING'] = True
    app.config['VISITOR_ANALYTICS_ALLOW_TESTING'] = False
    return app


# ---------------------------------------------------------------- 用例

def test_export_html_is_attachment_and_offline_capable():
    """导出件：200 + 附件 + 有 <base> + 带导出样式。"""
    app = _app()
    import modules.scan as scan_mod

    scan_mod.get_db = lambda: _StubDB(_scan_row())
    # 引擎取报告这条老路必须彻底不再走：真走上去就是 404
    def _boom(*a, **k):
        raise AssertionError('导出仍在向引擎请求 /report/<id>，而引擎没有这个路由')
    scan_mod._safe_http_get = _boom

    r = app.test_client().get(f'/report/{SID}/html')
    assert r.status_code == 200, r.status_code

    disp = r.headers.get('Content-Disposition', '')
    assert 'attachment' in disp, f'不是附件下载：{disp!r}'
    assert f'xinpect_report_{SID[:8]}.html' in disp, disp

    html = r.get_data(as_text=True)
    assert '<base href=' in html, '没有 <base>，导出的文件换个目录打开就掉样式'
    assert 'xinpect-export-style' in html, '导出样式没注入，导航和按钮会一起被存下来'
    assert 'Cache-Control' in r.headers and 'no-store' in r.headers['Cache-Control']


def test_export_html_same_numbers_as_page():
    """导出件与网页版必须是同一份 DOM —— 数字对不上就是第二套口径。"""
    app = _app()
    import modules.scan as scan_mod
    scan_mod.get_db = lambda: _StubDB(_scan_row())

    c = app.test_client()
    page = c.get(f'/report/{SID}').get_data(as_text=True)
    export = c.get(f'/report/{SID}/html').get_data(as_text=True)

    assert '>70<' in page or '70' in page
    # 关键正文两页都在，且导出件只是多了 <base> 与导出样式
    core = page.split('<body', 1)[-1]
    core = core.split('</body>', 1)[0].strip()
    exported_core = export.split('<body', 1)[-1].split('</body>', 1)[0].strip()
    assert core and core in exported_core, '导出件正文与网页版不一致（渲染了两套）'


def test_export_html_respects_access_control():
    """别人的报告不许导出——导出这条路上也要过访问控制。"""
    app = _app()
    import modules.scan as scan_mod
    scan_mod.get_db = lambda: _StubDB(_scan_row(user_id=99))

    r = app.test_client().get(f'/report/{SID}/html')
    assert r.status_code == 404, f'非本人报告被导出了：{r.status_code}'


def test_report_page_exposes_both_export_entries():
    """入口必须真实存在：HTML 下载链接 + PDF 打印按钮。"""
    path = os.path.join(BASE, 'templates', 'report.html')
    with open(path, encoding='utf-8') as f:
        tpl = f.read()

    assert "url_for('download_html_report'" in tpl, '页面上没有 HTML 下载入口'
    assert 'pdf-export-btn' in tpl.split('<style', 1)[-1], '.pdf-export-btn 只有样式没有按钮'
    # 按钮必须是真按钮，不是只有 class 的注释
    assert '<button' in tpl and 'window.print()' in tpl, 'PDF 导出没接打印'
    # 打印时这些会被隐藏，别把导航/按钮印进 PDF
    for cls in ('.report-actions', '.pdf-export-btn'):
        assert cls in tpl


if __name__ == '__main__':
    failures = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith('test_') or not callable(fn):
            continue
        try:
            fn()
            print(f'PASS {name}')
        except Exception as e:
            failures += 1
            print(f'FAIL {name}: {e}')
    print(f'\n{"FAILED" if failures else "ALL PASS"} ({failures} failed)')
    sys.exit(1 if failures else 0)
