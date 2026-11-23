"""钉住「会员过期 / 积分不足」时给客户的升级地址。

背景（2026-11-13）：api.py 里两处返回 `upgrade_url: '/dashboard?recharge'`，
但全站没有任何代码处理 `?recharge` 这个 query 参数 —— 客户点过去只是普通首页，
不会停在充值页。付费客户被 402 拒绝后，最后一步是死路。

这条守卫生在「字面量」层面：只要 UPGRADE_URL 与真实路由不一致，或者又退化成
带 query 参数的写法，立即判红。

注意：dashboard 路由是 `@app.route('/dashboard/<page>')`，定义在 modules/auth.py，
必须显式 import 才会挂到 url_map 上，否则 url_for 会报 BuildError。
"""
import re

import pytest


def _app():
    """带上 dashboard 路由的 Flask app。"""
    from modules.constants import app
    import modules.auth  # noqa: F401  注册 @app.route('/dashboard/<page>')
    return app


def test_upgrade_url_matches_real_route():
    """UPGRADE_URL 必须与 dashboard 充值页的真实路由完全一致。"""
    from modules import api
    from flask import url_for

    assert hasattr(api, 'UPGRADE_URL'), 'UPGRADE_URL 常量不存在，可能退回了字面量'

    app = _app()
    with app.test_request_context():
        real = url_for('dashboard_page', page='recharge')

    assert api.UPGRADE_URL == real, (
        'UPGRADE_URL=%r 与真实路由 %r 不一致' % (api.UPGRADE_URL, real)
    )


def test_upgrade_url_has_no_query_string():
    """不许再出现 `?recharge` 这类没人处理的 query 参数。"""
    from modules import api

    assert '?' not in api.UPGRADE_URL, (
        'UPGRADE_URL 含 query 参数：%r —— 这类参数全站无人处理，客户会落到空白页'
        % api.UPGRADE_URL
    )


def test_no_hardcoded_dead_upgrade_literal():
    """源码里不许再有写死的 `/dashboard?recharge`。"""
    import modules.api as api_mod
    src = open(api_mod.__file__, encoding='utf-8').read()
    hits = re.findall(r"['\"]/dashboard\?recharge['\"]", src)
    assert not hits, 'api.py 里仍有写死的死链接 %d 处' % len(hits)


def test_upgrade_url_actually_resolves_under_app():
    """把地址丢回 Flask 的路由表，必须能匹配到端点（不是 404）。"""
    from modules import api

    app = _app()
    adapter = app.url_map.bind('localhost')
    endpoint, args = adapter.match(api.UPGRADE_URL, method='GET')
    assert endpoint == 'dashboard_page'
    assert args.get('page') == 'recharge'
