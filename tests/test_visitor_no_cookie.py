#!/usr/bin/env python3
"""「一次一换 cookie 的机器」判据的测试。

要守的东西只有一条：**真浏览器带 cookie，所以同一个 vid 会重复出现；
不带 cookie 的机器每个请求领一张新 vid，独立访客数会被灌成请求数。**

这个测试不连生产库，自己造一个内存库；判据从 `modules/visitor_scope.py`
按文件路径加载（和报表同一个手法，不起 Flask）。

跑法：
    python3 tests/test_visitor_no_cookie.py      # 自带 6 组造坏自检
    pytest tests/test_visitor_no_cookie.py
"""
import importlib.util
import os
import sqlite3

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCOPE_PATH = os.path.join(BASE, 'modules', 'visitor_scope.py')


def load_scope():
    spec = importlib.util.spec_from_file_location('xp_visitor_scope', SCOPE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make_db(rows):
    """rows = [(ip, vid, ua), ...]，时间统一放今天。"""
    conn = sqlite3.connect(':memory:')
    conn.execute('''CREATE TABLE visitor_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, vid TEXT, path TEXT, ua TEXT,
        ip TEXT, is_bot INTEGER DEFAULT 0, is_internal INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now','localtime')))''')
    for ip, vid, ua in rows:
        conn.execute('INSERT INTO visitor_events (vid, path, ua, ip) '
                     "VALUES (?, '/', ?, ?)", (vid, ua, ip))
    conn.commit()
    return conn


CHROME = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/158.0.0.0'


def count_visitors(conn, scope):
    """按报表同一口径数独立访客：VF + 排除 suspect IP。"""
    sub = scope.suspect_ips_sql(7, scope.VISITOR_FILTER)
    sql = ('SELECT count(DISTINCT vid) FROM visitor_events '
           f'WHERE {scope.VISITOR_FILTER} AND ip NOT IN ({sub})')
    return conn.execute(sql).fetchone()[0]


def suspects(conn, scope):
    sub = scope.suspect_ips_sql(7, scope.VISITOR_FILTER)
    return {r[0] for r in conn.execute(f'SELECT ip FROM ({sub})')}


# ---- 造坏自检：每一组都必须是「判据真的改变了结论」 ----

def test_crawler_one_vid_per_hit_is_excluded():
    """无 cookie 机器：6 次请求 6 张新 vid → 判成机器，访客数记 0。"""
    scope = load_scope()
    rows = [('66.249.64.15', f'bot-{i}', CHROME) for i in range(6)]
    conn = make_db(rows)
    assert suspects(conn, scope) == {'66.249.64.15'}, '6 次 6 张新 vid 没被识别'
    assert count_visitors(conn, scope) == 0, '机器被算成了访客'


def test_real_user_repeat_visits_kept():
    """真浏览器：3 次请求同一个 vid → 保留 1 个访客。"""
    scope = load_scope()
    conn = make_db([('120.227.74.16', 'v-real', CHROME)] * 3)
    assert suspects(conn, scope) == set(), '真人被误判成机器'
    assert count_visitors(conn, scope) == 1


def test_below_threshold_not_excluded():
    """阈值下沿：4 次 4 张新 vid → 不够 5 次，不动它（判不了 ≠ 该判死）。"""
    scope = load_scope()
    rows = [('93.123.109.103', f'x-{i}', CHROME) for i in range(4)]
    conn = make_db(rows)
    assert suspects(conn, scope) == set(), '4 次就被判死，阈值失效'
    assert count_visitors(conn, scope) == 4


def test_ratio_boundary_not_excluded():
    """比例下沿：5 张 vid 里 2 张各出现 2 次 → 单次占比 0.6 < 0.9，保留。"""
    scope = load_scope()
    rows = [('1.2.3.4', 'v1', CHROME), ('1.2.3.4', 'v1', CHROME),
            ('1.2.3.4', 'v2', CHROME), ('1.2.3.4', 'v2', CHROME),
            ('1.2.3.4', 'v3', CHROME), ('1.2.3.4', 'v4', CHROME),
            ('1.2.3.4', 'v5', CHROME)]
    conn = make_db(rows)
    assert suspects(conn, scope) == set(), '比例门槛失效，把重复来访的人判死了'


def test_googlebot_like_multi_ip_all_caught():
    """爬虫换 IP 来：每个 IP 自己 8~12 次、次次新 vid → 每个 IP 都该被抓。"""
    scope = load_scope()
    rows = []
    for ip, n in [('66.249.64.1', 8), ('66.249.64.8', 9), ('66.249.64.14', 12)]:
        rows += [(ip, f'{ip}-{i}', CHROME) for i in range(n)]
    conn = make_db(rows)
    got = suspects(conn, scope)
    assert got == {'66.249.64.1', '66.249.64.8', '66.249.64.14'}, got
    assert count_visitors(conn, scope) == 0


def test_internal_and_bot_not_used_as_evidence():
    """我们自己的工具（is_internal=1）次数再多，也不该把它的 IP 判成机器。

    否则本机 IP 会被自己刷成「机器」，连带把同 IP 的真人一起抹掉。
    """
    scope = load_scope()
    conn = make_db([])
    for i in range(20):
        conn.execute("INSERT INTO visitor_events (vid, path, ua, ip, is_internal) "
                     "VALUES (?, '/', ?, '154.8.211.17', 1)", (f'g-{i}', 'xp-growth-guard/1.0'))
    conn.execute("INSERT INTO visitor_events (vid, path, ua, ip) "
                 "VALUES ('v-real', '/', ?, '154.8.211.17')", (CHROME,))
    conn.commit()
    assert suspects(conn, scope) == set(), '自检流量把 IP 拖成了机器'
    assert count_visitors(conn, scope) == 1, '同 IP 的真人被自检流量连累'


ALL = [test_crawler_one_vid_per_hit_is_excluded,
       test_real_user_repeat_visits_kept,
       test_below_threshold_not_excluded,
       test_ratio_boundary_not_excluded,
       test_googlebot_like_multi_ip_all_caught,
       test_internal_and_bot_not_used_as_evidence]


def main():
    bad = 0
    for fn in ALL:
        try:
            fn()
            print('  ✅ %s' % fn.__name__)
        except AssertionError as exc:
            bad += 1
            print('  ❌ %s: %s' % (fn.__name__, exc))
    print('---- %d/%d 通过 ----' % (len(ALL) - bad, len(ALL)))
    return 1 if bad else 0


if __name__ == '__main__':
    raise SystemExit(main())
