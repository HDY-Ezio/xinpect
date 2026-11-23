#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""免费试扫限流守卫 —— 锁住「额度按人算，不按客户端说了算」。

## 为什么要有这套断言（2026-11-04）

原来的限流按 `X-Forwarded-For` 的第一节算，两个方向都错：

- 取第一节：客户端自己写的那段，改个请求头就是无限额度。实测可行。
- 取最后一节：nginx 追加的 `$remote_addr`，而 443 前面挡着 sslh 1.22
  （纯 TCP 转发、不支持 PROXY protocol），恒为 127.0.0.1。
  实测整张表所有访客 ip 都是 127.0.0.1 —— 等于**全站共用了一个 3 次的桶**。

也就是说这个拓扑下没有一个「取法」是对的，根因是**真实 IP 从未到达应用层**。
所以改成按服务端签发的访客 id 记账。这套守卫锁的就是：

1. 伪造 `X-Forwarded-For` 换不来任何额度（核心判据）；
2. 额度数的是已经落库的 `try.ok`，跨重启不会凭空恢复；
3. 不同访客互不影响（不许因为别人用满了就拦我）；
4. 扫描失败（try.fail）不扣额度；
5. 全站日上限兜底存在且真能拦；
6. 伪造的 IP 不会被写进库（避免将来有人拿它做判断）。

运行：
    sudo bash -c 'set -a; . /etc/xinpect/website.env; set +a; cd /opt/xinpect-website \
        && python3 tests/test_try_quota.py'

会在 visitor_events 里写测试记录，**每个用例跑完立刻删干净**
（脚本模式和 pytest 模式都挂同一套 setup/teardown，不留垃圾）。
"""

import os
import sqlite3
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

FAILED = []

# 含 z/q/y 的 32 位串：uuid4().hex 只可能由 0-9a-f 组成，
# 所以这几个值绝不会和真实访客撞上，删起来可以放心。
VID_USED_UP = 'zq' + '0' * 30     # 用来模拟「今天已用满」
VID_FRESH = 'zz' + '1' * 30       # 用来模拟「另一个没用过的人」
VID_EMPTY = 'zy' + '2' * 30       # 只读断言，不落库

TEST_VIDS = (VID_USED_UP, VID_FRESH, VID_EMPTY)

FAKE_XFF = '203.0.113.9'          # 文档保留地址，伪造专用
BROWSER_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0'

_CTX = {}


def check(cond, msg):
    """断言一条。失败既记台账也抛异常。

    为什么要抛：本文件会被 pytest 自动收集（函数名 test_*），而 pytest 只认
    断言、不认我们的 FAILED 列表。只记录不抛，pytest 就会把失败报成通过。
    """
    if cond:
        print(f'  [OK]   {msg}')
        return
    print(f'  [FAIL] {msg}')
    FAILED.append(msg)
    raise AssertionError(msg)


def _app():
    from app import app
    from modules.constants import DB_PATH
    return app, DB_PATH


def _ensure(db):
    """确保 visitor_events 存在。复用埋点模块的建表逻辑，不在这里抄 schema。"""
    from modules.visitor_analytics import _ensure_schema
    conn = sqlite3.connect(db, timeout=5)
    try:
        _ensure_schema(conn)
    finally:
        conn.close()


def _max_id(db):
    conn = sqlite3.connect(db, timeout=5)
    try:
        return conn.execute(
            'SELECT COALESCE(max(id), 0) FROM visitor_events').fetchone()[0]
    except sqlite3.Error:
        return 0
    finally:
        conn.close()


def _exec(db, sql, args=()):
    conn = sqlite3.connect(db, timeout=5)
    try:
        conn.execute(sql, args)
        conn.commit()
    finally:
        conn.close()


def _seed(db, vid, event, n):
    """造 n 条当日事件（等价于「今天已经发生过 n 次」）。"""
    for _ in range(n):
        _exec(
            db,
            "INSERT INTO visitor_events "
            "(vid, user_id, kind, path, method, status, referer, ua, ip, is_bot, detail, created_at) "
            "VALUES (?, NULL, 'event', ?, 'EVENT', NULL, '', 'pytest', '127.0.0.1', 0, '{}', "
            "datetime('now','localtime'))",
            (vid, event),
        )


def _reset_vids(db):
    """清掉本文件专用 vid 的记录，保证每个用例从「干净的人」开始。"""
    _exec(db, 'DELETE FROM visitor_events WHERE vid IN (?, ?, ?)', TEST_VIDS)


def _cleanup(db, since_id):
    _reset_vids(db)
    if since_id:
        # after_request 可能用新 vid 记了页面访问，一并回收
        _exec(db, 'DELETE FROM visitor_events WHERE id > ?', (since_id,))


def _setup():
    app, db = _app()
    app.config['TESTING'] = True
    app.config.pop('VISITOR_ANALYTICS_ALLOW_TESTING', None)
    _ensure(db)
    _reset_vids(db)
    _CTX.update(app=app, db=db, since=_max_id(db))


def _teardown():
    app = _CTX.get('app')
    if app is not None:
        app.config.pop('VISITOR_ANALYTICS_ALLOW_TESTING', None)
    if _CTX.get('db'):
        _cleanup(_CTX['db'], _CTX.get('since'))


# pytest 模式下也会调这两个，确保不留垃圾
def setup_function(function):
    _setup()


def teardown_function(function):
    _teardown()


# --------------------------------------------------------------------------- #
# 用例
# --------------------------------------------------------------------------- #

def test_identity_ignores_forwarded_for():
    """核心判据：换 X-Forwarded-For 不换身份，换不来新额度。"""
    app = _CTX['app']
    from modules.visitor_analytics import current_vid

    seen = set()
    for spoof in (FAKE_XFF, '8.8.8.8', '1.1.1.1, 5.5.5.5', ''):
        headers = {'Cookie': f'xp_vid={VID_USED_UP}'}
        if spoof:
            headers['X-Forwarded-For'] = spoof
        with app.test_request_context('/', headers=headers):
            seen.add(current_vid())

    check(seen == {VID_USED_UP},
          f'4 组不同 XFF 下身份始终是同一个 vid（实际拿到 {len(seen)} 个）')


def test_quota_counts_try_ok_events():
    """额度数的是已落库的 try.ok，不是内存里的计数。"""
    db = _CTX['db']
    from modules import free_try

    check(free_try._remaining_tries(VID_EMPTY) == free_try._TRY_DAILY_LIMIT,
          f'没用过的人剩余 {free_try._TRY_DAILY_LIMIT} 次')

    _seed(db, VID_USED_UP, 'try.ok', free_try._TRY_DAILY_LIMIT)
    check(free_try._remaining_tries(VID_USED_UP) == 0, '用满 3 次后剩余 0 次')
    check(free_try._used_today(VID_USED_UP) == free_try._TRY_DAILY_LIMIT,
          '已用次数 == 落库的 try.ok 条数')


def test_spoofed_forwarded_for_cannot_reset_quota():
    """真打接口：用满的人即使伪造 XFF 也必须是 429。"""
    app, db = _CTX['app'], _CTX['db']
    from modules import free_try

    _seed(db, VID_USED_UP, 'try.ok', free_try._TRY_DAILY_LIMIT)

    client = app.test_client()
    # Werkzeug 3.x 的测试客户端会丢掉手写的 Cookie 头，必须走 set_cookie 灌进 jar
    client.set_cookie('xp_vid', VID_USED_UP)
    r = client.post(
        '/api/try-scan',
        json={'code': 'print(1)\n', 'language': 'python'},
        headers={
            'X-Forwarded-For': FAKE_XFF,
            'User-Agent': BROWSER_UA,
        },
    )
    check(r.status_code == 429,
          f'已用满 + 伪造 XFF → 429（实际 {r.status_code}）')
    body = r.get_json() or {}
    check('次数已用完' in (body.get('error') or ''),
          '回的是个人额度用完，不是全局名额用完')


def test_quota_is_per_visitor():
    """别人用满了不该连累我，同一 XFF 也不行。"""
    app, db = _CTX['app'], _CTX['db']
    from modules import free_try

    _seed(db, VID_USED_UP, 'try.ok', free_try._TRY_DAILY_LIMIT)

    client = app.test_client()
    client.set_cookie('xp_vid', VID_FRESH)
    # 同一段伪造 XFF、换成没用过的 vid：应该过额度闸门。
    # 空代码是在闸门之后才被 400 挡住的，所以 400 恰好证明「没被 429 拦」。
    r = client.post(
        '/api/try-scan',
        json={'code': '', 'language': 'python'},
        headers={
            'X-Forwarded-For': FAKE_XFF,
            'User-Agent': BROWSER_UA,
        },
    )
    check(r.status_code == 400,
          f'另一个访客在同一 XFF 下没被误拦（实际 {r.status_code}）')


def test_failed_scan_does_not_consume_quota():
    """扫失败不该扣次数——扣了就是白扣用户的钱。"""
    db = _CTX['db']
    from modules import free_try

    _seed(db, VID_FRESH, 'try.fail', 5)
    check(free_try._remaining_tries(VID_FRESH) == free_try._TRY_DAILY_LIMIT,
          '5 条 try.fail 不占额度')


def test_global_daily_cap():
    """全站日上限必须存在，且能拦住——这是算力成本的最后一道闸。"""
    app, db = _CTX['app'], _CTX['db']
    from modules import free_try

    check(free_try._GLOBAL_DAILY_LIMIT > 0,
          f'全站日上限已配置（{free_try._GLOBAL_DAILY_LIMIT} 次）')
    total = free_try._global_used_today()
    check(isinstance(total, int) and total >= 0, f'能读出当日全站用量（{total} 次）')

    _seed(db, VID_USED_UP, 'try.ok', 2)
    check(free_try._global_used_today() >= 2, '全站用量会把所有人的成功扫描都算进去')

    # 把天花板临时压到「已经用掉的程度」，确认真的会拦。
    client = app.test_client()
    client.set_cookie('xp_vid', VID_FRESH)
    original = free_try._GLOBAL_DAILY_LIMIT
    try:
        free_try._GLOBAL_DAILY_LIMIT = max(0, free_try._global_used_today() - 1)
        r = client.post(
            '/api/try-scan',
            json={'code': 'print(1)\n', 'language': 'python'},
            headers={'User-Agent': BROWSER_UA},
        )
        body = r.get_json() or {}
        check(r.status_code == 429 and '名额已用完' in (body.get('error') or ''),
              f'触顶后回全局名额用完（实际 {r.status_code}）')
    finally:
        free_try._GLOBAL_DAILY_LIMIT = original


def test_trusted_ip_takes_last_hop():
    """伪造的 IP 不许进库：只认反向代理亲手追加的最后一跳。"""
    app = _CTX['app']
    from modules.visitor_analytics import _trusted_ip

    with app.test_request_context(
            '/', headers={'X-Forwarded-For': f'{FAKE_XFF}, 127.0.0.1'}):
        got = _trusted_ip()
    check(got == '127.0.0.1',
          f'XFF 取最后一跳而不是客户端伪造的第一节（实际 {got}）')

    with app.test_request_context('/', headers={'X-Forwarded-For': FAKE_XFF}):
        got2 = _trusted_ip()
    check(got2 == FAKE_XFF, '只有一跳时照原样记录（不绑死单一部署形态）')


def test_try_page_gets_vid_cookie():
    """首次访问 /try 要下发访客 id（这条原来顶着 POST 的名字）。"""
    app = _CTX['app']
    # 打开 TESTING 的埋点短路，才能验证 cookie 真的会下发
    app.config['VISITOR_ANALYTICS_ALLOW_TESTING'] = True
    client = app.test_client()
    r = client.get('/try', headers={'User-Agent': BROWSER_UA})
    set_cookie = r.headers.get('Set-Cookie') or ''
    check(r.status_code == 200, f'/try 正常打开（实际 {r.status_code}）')
    check('xp_vid=' in set_cookie, '首次访问 /try 会下发访客 id')


def test_no_cookie_post_still_gets_vid():
    """没有 cookie 的 POST 也必须下发 vid，否则额度根本记不上账。

    2026-11-04 修正：这条用例原来名字叫 POST，代码测的却是 GET /try。
    于是「GET 能拿到 cookie」一直绿着，真正要紧的 POST 一次都没被看过。
    实测那时 POST /api/try-scan 的响应里一个 Set-Cookie 都没有 ——
    after_request 里下发 cookie 的那段写在 `if not _is_trackable: return`
    之后，而 /api/* 恰好被 _is_trackable 排除，等于永远不执行。
    后果：匿名每次扫描都是新访客，3 次额度永远用不完，限流形同不存在。

    守卫名不副实比没有守卫更糟，它会让人以为查过了。
    """
    app = _CTX['app']
    app.config['VISITOR_ANALYTICS_ALLOW_TESTING'] = True
    client = app.test_client()
    r = client.post(
        '/api/try-scan',
        json={'code': 'def add(a, b):\n    return a + b\n', 'language': 'python'},
        headers={'User-Agent': BROWSER_UA, 'Origin': 'http://localhost'},
    )
    set_cookie = r.headers.get('Set-Cookie') or ''
    check(r.status_code == 200, f'匿名 POST 试扫成功（实际 {r.status_code}）')
    check('xp_vid=' in set_cookie,
          '匿名首次 POST 必须下发访客 id（少了它额度永远不扣）')


def main():
    cases = (
        test_identity_ignores_forwarded_for,
        test_quota_counts_try_ok_events,
        test_spoofed_forwarded_for_cannot_reset_quota,
        test_quota_is_per_visitor,
        test_failed_scan_does_not_consume_quota,
        test_global_daily_cap,
        test_trusted_ip_takes_last_hop,
        test_try_page_gets_vid_cookie,
        test_no_cookie_post_still_gets_vid,
    )
    for fn in cases:
        print(f'RUN  {fn.__name__}')
        setup_function(fn)
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            FAILED.append(f'{fn.__name__}: {exc}')
        finally:
            teardown_function(fn)

    print()
    if FAILED:
        print(f'失败 {len(FAILED)} 项：')
        for m in FAILED:
            print(f'  - {m}')
        return 1
    print(f'全部通过（{len(cases)} 项）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
