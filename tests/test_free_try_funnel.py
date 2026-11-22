#!/usr/bin/env python3
"""免注册试扫「漏斗」守卫。

背景（2026-11-04）：/try 页面 2026-10-28 就做完了、接口也是通的，
但整整一周**没有一个真人走到它面前**：
  - 全站导航第 4 项「快速体验」指向 /upload，未登录 302 到登录页 → 第一道墙
  - 定价页免费档按钮同样指向 /upload → 第二道墙
  - sitemap.xml 里列的是 /upload（登录墙），/try 根本没被搜索引擎看见
  - 登录页/注册页底部只有「立即注册」，没有「先试试」的退路

所以真正要守的不是"页面存在"，而是**"从任何一页都走得进去"**：
  1. 匿名状态下，导航给的入口必须是 /try（不是 /upload）
  2. 定价页免费档、登录页、注册页都必须有 /try 的退路
  3. sitemap 只收匿名可见的页（收录登录墙等于把爬虫往墙上撞）
  4. /try 页与 /api/try-scan 必须**真能跑出结果**——不是"有路由"，是"能出数"
  5. 试扫结果必须仍是"摘要"：只能有 category/name/severity，不能漏行号和代码

跑法（服务器没装 pytest，两种都支持；需要 website.env 里的扫描器配置）：
    sudo bash -c 'set -a; . /etc/xinpect/website.env; set +a; python3 tests/test_free_try_funnel.py'
    pytest tests/test_free_try_funnel.py -q
"""

import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(BASE, 'templates')

# 摘要字段白名单：多一个字段就等于把「完整报告」免费送了
SUMMARY_ITEM_KEYS = {'category', 'name', 'severity'}


def _client():
    sys.path.insert(0, BASE)
    from app import app
    app.config['TESTING'] = True
    # 埋点不走测试请求，避免污染访客数据（与 test_retention 同一开关）
    app.config['VISITOR_ANALYTICS_ALLOW_TESTING'] = False
    return app, app.test_client()


def _html(client, path):
    resp = client.get(path)
    assert resp.status_code == 200, '%s 返回 %d（期望 200）' % (path, resp.status_code)
    return resp.get_data(as_text=True)


def test_try_page_anonymous_open():
    """匿名打开 /try 必须是 200 的页面，不能被登录墙挡住。"""
    app, client = _client()
    resp = client.get('/try')
    assert resp.status_code == 200, '/try 匿名访问返回 %d，登录墙把入口挡死了' % resp.status_code
    html = resp.get_data(as_text=True)
    assert 'code-input' in html, '/try 页面里没有代码输入框（code-input）'
    assert '/api/try-scan' in html, '/try 页面的前端没有调用 /api/try-scan'
    print('    /try 匿名可开，输入框与接口调用都在')


def test_nav_entry_points_to_try():
    """匿名访客在任何页面的导航里，都必须能直接点到 /try。

    2026-11-22 改判据：导航已经收成唯一一份（templates/_nav.html），首页不再
    自带一套。原判据写死了 `<a href="/try">免费试扫</a>` 这个精确写法，导航
    换结构就假红，而且只覆盖「首页 + 定价页」两页。
    现在按渲染结果判：三页都必须有导航容器，容器里都必须有 /try，且不能有
    /upload（匿名点了会 302 到登录页）。判「有没有」，不判「怎么写」。
    """
    app, client = _client()

    for path in ('/', '/pricing', '/blog'):
        html = _html(client, path)
        m = re.search(r'<nav[^>]*xp-nav-links[^>]*>(.*?)</nav>', html, re.S)
        assert m, '%s 找不到全站导航容器（xp-nav-links）' % path
        nav = m.group(1)
        assert 'href="/try"' in nav, '%s 的导航里没有 /try' % path
        assert '/upload' not in nav, '%s 的导航指向 /upload（匿名会 302 到登录页）' % path
    print('    导航：三个页面同一份，匿名 → /try，没有再撞登录墙')


def test_pricing_offers_free_try():
    """定价页的免费档必须给「先试扫」的退路，而不是直接推注册。"""
    app, client = _client()
    html = _html(client, '/pricing')
    assert 'href="/try"' in html, '定价页没有 /try 入口'
    assert '免注册' in html, '定价页没有说明可以免注册试扫'
    print('    定价页免费档已挂 /try')


def test_auth_pages_offer_way_out():
    """登录/注册/找回密码三个页面都要给「不想注册先试扫」的退路。"""
    app, client = _client()
    for path in ('/login', '/register'):
        html = _html(client, path)
        assert 'href="/try"' in html, '%s 没有 /try 退路' % path
    print('    登录页、注册页都有 /try 退路')


def test_sitemap_points_at_anonymous_pages():
    """sitemap 只能收匿名可见的页；登录墙（/upload）收进去等于浪费爬虫预算。"""
    app, client = _client()
    resp = client.get('/sitemap.xml')
    assert resp.status_code == 200
    xml = resp.get_data(as_text=True)
    assert '<loc>https://xinpect.xingwangzhineng.com/try</loc>' in xml, 'sitemap 里没有 /try'
    assert '/upload' not in xml, 'sitemap 里仍然有 /upload（未登录 302 到登录页，爬虫抓到的是墙）'
    print('    sitemap：收录 /try，不再收录 /upload')


def test_auth_pages_brand_consistent():
    """三个认证页曾经是手搓「X」方块 + 「煋鉴 Xinpect」双写，必须统一成品牌图。"""
    app, client = _client()
    for path in ('/login', '/register', '/forgot-password'):
        html = _html(client, path)
        assert 'logo-icon' not in html, '%s 里还有手搓的字母 X 图标（logo-icon）' % path
        assert 'xinpect-mark-wide-128.png' in html, '%s 没有引用品牌图 xinpect-mark-wide-128.png' % path
    print('    三个认证页品牌图已统一')


def test_referral_modal_not_for_anonymous():
    """推荐弹窗不许拦还没账号的人。

    实测（2026-11-04 截图）：匿名打开定价页，第一眼就被「推荐有礼 双方得利」
    全屏盖住，而弹窗里的按钮写着「获取我的推荐链接」→ 点进去是登录页。
    对一个还没注册的人谈"拉朋友"，等于第一次见面先递会员卡。
    治本：弹窗只对登录用户自动弹；匿名态只留顶部可关闭的横幅。
    """
    app, client = _client()
    html = _html(client, '/pricing')
    assert 'var loggedIn = false' in html, '匿名态渲染出的 loggedIn 不是 false（弹窗会拦新访客）'
    # 匿名态下弹窗里的 CTA 必须指向注册，而不是「我的推荐链接」后台页
    modal = re.search(r'<div id="referral-modal".*?</div>\s*</div>\s*</div>', html, re.S)
    assert modal, '找不到推荐弹窗结构'
    assert '/dashboard/account' not in modal.group(0), '匿名态弹窗仍然把访客指向「我的推荐链接」（会跳登录页）'
    print('    推荐弹窗：匿名不自动弹，CTA 指向注册')


def test_try_scan_really_returns_summary():
    """真跑一次试扫：必须出结果，且结果只能是摘要。

    引擎地址不是环境变量，是 modules.constants 里的常量（默认指本机绿版），
    所以这里不在 os.environ 里找，直接问常量——"有路由"不算通，"能出数"才算通。
    """
    app, client = _client()
    from modules.constants import SCANNER_URL
    assert SCANNER_URL, 'modules.constants.SCANNER_URL 是空的，试扫必然打不通'
    # 额度按访客 id 记账（不再是进程内计数、也不按 IP），而 _client() 每次都是
    # 全新的 test_client，拿到的是全新的 vid，天生满额 3 次，不需要手动清理。
    code = (
        'import os\n'
        'import sqlite3\n'
        'def q(uid):\n'
        '    conn = sqlite3.connect("a.db")\n'
        '    cur = conn.cursor()\n'
        '    cur.execute("SELECT * FROM users WHERE id=" + uid)\n'
        '    return cur.fetchall()\n'
        'def run(cmd):\n'
        '    os.system(cmd)\n'
    )
    resp = client.post('/api/try-scan', json={'code': code, 'language': 'python'})
    assert resp.status_code == 200, '试扫接口返回 %d：%s' % (resp.status_code, resp.get_data(as_text=True)[:200])
    data = resp.get_json()
    assert data.get('status') == 'ok', '试扫没返回 ok：%s' % data
    summary = data.get('summary') or {}
    total = summary.get('total_issues')
    assert total and total >= 1, '这段有明显 SQL 注入和命令执行的代码，试扫检出 %s 条' % total
    assert summary.get('severity_breakdown'), '结果里没有严重度分布'
    assert (summary.get('health') or {}).get('grade'), '结果里没有健康度评级'

    # 摘要边界：多给一个字段就等于把完整报告免费送出去
    for item in summary.get('highlights') or []:
        extra = set(item) - SUMMARY_ITEM_KEYS
        assert not extra, '试扫摘要泄漏了字段 %s（只允许 category/name/severity）' % extra
    print('    真跑通过：检出 %d 条，评级 %s，摘要无泄漏' % (total, summary['health']['grade']))


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
