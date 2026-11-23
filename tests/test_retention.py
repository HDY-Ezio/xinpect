"""用户留存链路守卫（访客埋点 + 首登引导）。

## 为什么需要这组测试

这一批修复的根因不是「写错了」，是「做了没接线」，而且没人发现：
- `templates/onboarding.html` 825 行，写得很完整，**全站零引用、无路由**，
  从写出来那天起一次都没被渲染过；
- `users.first_login_at` / `onboarding_completed` 两列建好了，**全库零写入**；
- `onboarding.html` 里写死调 `/api/user/onboarding/status`，**这个接口根本不存在**；
- 结果：15 个注册用户里 11 个从没产生过一次扫描，而系统里没有任何数据能回答
  「他注册完到底看到了什么」。

所以这组测试的重点不是「功能对不对」，是**「做的东西有没有接上」**：
1. 模板里 fetch 的每一个 /api/ 地址，必须在 app.url_map 里真实存在；
2. onboarding 组件必须被某个模板 include，否则它就是死文件；
3. 首登两列必须有写入路径，否则统计永远是空的；
4. 埋点必须真的落库，且同一 cookie 能认成同一个人。

服务器没装 pytest，所以本文件同时支持 pytest 与 `python3 test_retention.py`。
"""

import os
import re
import sqlite3
import sys
from contextlib import contextmanager

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates')
ONBOARDING = os.path.join(TEMPLATES_DIR, 'onboarding.html')


def _read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def _template_files():
    for root, _dirs, files in os.walk(TEMPLATES_DIR):
        for fn in files:
            if fn.endswith('.html'):
                yield os.path.join(root, fn)


# ---------------------------------------------------------------- 接线检查

def test_onboarding_component_is_referenced():
    """onboarding.html 必须被至少一个模板 include。

    这条就是防止它再变回孤儿文件——当初它就是这样躺了几个月没人发现。
    """
    refs = []
    for path in _template_files():
        if os.path.abspath(path) == os.path.abspath(ONBOARDING):
            continue
        if 'onboarding.html' in _read(path):
            refs.append(os.path.relpath(path, TEMPLATES_DIR))
    assert refs, 'onboarding.html 没有被任何模板引用，等于一个死文件'
    print('    引用方: %s' % ', '.join(refs))


def test_onboarding_api_endpoints_exist():
    """onboarding.html 里 fetch 的接口必须真实注册在路由表里。

    这条抓到的是真事故：组件写死调 `/api/user/onboarding/status`，
    而这个接口直到现在才被实现——也就是说组件就算被渲染，也拿不到状态。

    注意不要全站扫：别的模板大量用 JS 拼基址（`/api/scan/` + id），
    正则只能抓到前缀，硬套会产出一堆假警报，反而让这条守卫没人信。
    这里只做前缀/完全匹配两种判定，宁宽勿假。
    """
    from app import app  # noqa: WPS433

    src = _read(ONBOARDING)
    wanted = set(re.findall(r"""['"](/api/[A-Za-z0-9_\-/]+)['"]""", src))
    assert wanted, 'onboarding.html 里没有抽到任何接口调用，规则可能失效了'

    rules = {r.rule for r in app.url_map.iter_rules()}
    missing = []
    for url in sorted(wanted):
        norm = url.rstrip('/')
        hit = norm in rules or any(r.rstrip('/') == norm or r.startswith(norm + '/') for r in rules)
        if not hit:
            missing.append(url)

    assert not missing, '模板里调用了不存在的接口: %s' % missing
    print('    onboarding 引用接口 %d 个，全部存在: %s' % (len(wanted), sorted(wanted)))


def test_first_login_columns_are_written():
    """users.first_login_at / onboarding_completed 必须有写入路径。

    两列建了不写，等于「有多少人注册后真的登录过」这个问题永远答不出来。
    """
    src = _read(os.path.join(BASE_DIR, 'modules', 'auth.py'))
    assert 'first_login_at = datetime' in src, 'first_login_at 没有任何写入'
    assert 'onboarding_completed = 1' in src, 'onboarding_completed 没有任何写入'
    assert 'onboarding_completed = 0' in src, '注册时没有重置 onboarding_completed'


# ---------------------------------------------------------------- 埋点检查

@contextmanager
def _allow_tracking():
    """临时允许 TESTING 模式写埋点，退出时把自己写的那几条删干净。

    生产访问表不能被测试污染（自家脚本会刷出假访客，已实测踩过），
    但埋点口径又必须真落库才能验证「同一 cookie 认成同一个人」。
    折中：开一个小窗，测完擦掉，不靠人工记得清理。
    """
    from app import app

    prev = app.config.get('VISITOR_ANALYTICS_ALLOW_TESTING')
    app.config['VISITOR_ANALYTICS_ALLOW_TESTING'] = True

    conn = sqlite3.connect(os.path.join(BASE_DIR, 'xinpect.db'))
    try:
        start_id = conn.execute(
            'SELECT COALESCE(MAX(id), 0) FROM visitor_events'
        ).fetchone()[0]
    finally:
        conn.close()

    try:
        yield
    finally:
        app.config['VISITOR_ANALYTICS_ALLOW_TESTING'] = prev
        conn = sqlite3.connect(os.path.join(BASE_DIR, 'xinpect.db'))
        try:
            conn.execute('DELETE FROM visitor_events WHERE id > ?', (start_id,))
            conn.commit()
        finally:
            conn.close()


def test_visitor_cookie_identifies_same_person():
    """同一个 cookie 的多次访问，必须记成同一个 vid。

    这是访客口径的地基：443 前面是 sslh，nginx 拿不到真实 IP，
    所以只能靠 cookie 认人。如果这里失效，所有访客数据都是错的。
    """
    from app import app

    app.config['TESTING'] = True
    c = app.test_client()
    with _allow_tracking():
        for _ in range(2):
            r = c.get('/pricing')
            assert r.status_code == 200

        # 查询必须写在 with 里面。_allow_tracking 退出时会删掉本次写入的记录，
        # 放到外面查，拿到的是历史残留（我第一版就是这么写的，于是报
        # "同一 cookie 被记成两个访客"，白查了一轮）。
        conn = sqlite3.connect(os.path.join(BASE_DIR, 'xinpect.db'))
        try:
            rows = conn.execute(
                "SELECT vid FROM visitor_events WHERE path='/pricing' "
                "ORDER BY id DESC LIMIT 2"
            ).fetchall()
        finally:
            conn.close()
    assert len(rows) == 2, '埋点没有落库，查到 %d 条' % len(rows)
    assert rows[0][0] == rows[1][0], '同一 cookie 被记成了两个访客：%r' % (rows,)


def test_bot_traffic_is_flagged():
    """爬虫必须被标记 is_bot=1，不能混进访客口径。"""
    from app import app

    app.config['TESTING'] = True
    c = app.test_client()
    with _allow_tracking():
        c.get('/pricing', headers={'User-Agent': 'Googlebot/2.1 (+http://www.google.com/bot.html)'})

        # 同上：必须在 with 内查询，否则读到的是别人留下的记录
        conn = sqlite3.connect(os.path.join(BASE_DIR, 'xinpect.db'))
        try:
            row = conn.execute(
                "SELECT is_bot, ua FROM visitor_events WHERE path='/pricing' "
                "ORDER BY id DESC LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
    assert row is not None, '埋点没有落库'
    assert row[0] == 1, '爬虫没有被标记: UA=%r' % (row[1],)


def test_static_and_api_are_not_tracked():
    """静态资源和接口不该进访客表——否则音量会炸，口径也会脏。"""
    from app import app

    app.config['TESTING'] = True
    c = app.test_client()
    with _allow_tracking():
        before = _count_events()
        c.get('/static/css/style.css')
        c.get('/api/nonexistent-for-test')
        after = _count_events()
    assert after == before, '/static/ 或 /api/ 的请求被误记进访客表'


def _count_events():
    conn = sqlite3.connect(os.path.join(BASE_DIR, 'xinpect.db'))
    try:
        return conn.execute('SELECT count(*) FROM visitor_events').fetchone()[0]
    except sqlite3.Error:
        return 0
    finally:
        conn.close()


# ---------------------------------------------------------------- 引导渲染

def test_new_user_sees_onboarding():
    """从未扫描过的用户进后台，必须看到引导，且看不到四个 0 的统计卡。"""
    from app import app

    conn = sqlite3.connect(os.path.join(BASE_DIR, 'xinpect.db'))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute('''
            SELECT u.id, u.email, u.session_version FROM users u
            LEFT JOIN (SELECT user_id, count(*) c FROM scans GROUP BY user_id) s
                   ON s.user_id = u.id
            WHERE COALESCE(s.c, 0) = 0
            ORDER BY u.id DESC LIMIT 1
        ''').fetchone()
        if not row:
            print('    SKIP 没有「从未扫描」的用户')
            return
        conn.execute('UPDATE users SET onboarding_completed = 0 WHERE id = ?', (row['id'],))
        conn.commit()
    finally:
        conn.close()

    app.config['TESTING'] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s['user_id'] = row['id']
        s['session_version'] = row['session_version'] or 1
        s['user_email'] = row['email']

    r = c.get('/dashboard')
    assert r.status_code == 200, '后台首页返回 %d' % r.status_code
    html = r.get_data(as_text=True)
    assert 'id="onboarding-overlay"' in html, '首登引导没有渲染'
    assert '账号已就绪' in html, '新用户引导卡没有出现'
    assert '总检测次数' not in html, '新用户仍然看到四个 0 的统计卡'


def test_veteran_user_unaffected():
    """有扫描记录的老用户，界面必须保持原样，不能被引导打扰。"""
    from app import app

    conn = sqlite3.connect(os.path.join(BASE_DIR, 'xinpect.db'))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute('''
            SELECT u.id, u.email, u.session_version FROM users u
            JOIN (SELECT user_id, count(*) c FROM scans GROUP BY user_id) s
              ON s.user_id = u.id
            ORDER BY s.c DESC LIMIT 1
        ''').fetchone()
        if not row:
            print('    SKIP 没有发生过扫描的用户')
            return
    finally:
        conn.close()

    app.config['TESTING'] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s['user_id'] = row['id']
        s['session_version'] = row['session_version'] or 1
        s['user_email'] = row['email']

    html = c.get('/dashboard').get_data(as_text=True)
    assert 'id="onboarding-overlay"' not in html, '老用户被弹了首登引导'
    assert '总检测次数' in html, '老用户的统计卡没了'


if __name__ == '__main__':
    fails = 0
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_') and callable(v)]
    for fn in tests:
        try:
            fn()
            print('PASS %s' % fn.__name__)
        except Exception as e:  # noqa: BLE001
            fails += 1
            print('FAIL %s -> %r' % (fn.__name__, e))
    print('结果: %d/%d 通过' % (len(tests) - fails, len(tests)))
    sys.exit(1 if fails else 0)
