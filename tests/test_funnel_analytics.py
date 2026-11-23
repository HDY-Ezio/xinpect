#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""试扫漏斗埋点守卫 —— 保证「有没有人用」这件事以后一直看得见。

为什么要有这套断言：
    免注册试扫上线后，我们**看不见**有没有人真的走完流程。页面能打开、
    接口能出结果，都不等于有人用。上一轮的教训就是：功能「做好了」和
    功能「有人走到」是两件事，中间只能靠数据分辨。

    这个守卫锁住三件事：
    1. 页面访问和事件记录不会混在一起（kind 过滤必须真的生效）；
    2. 试扫失败/成功都会落事件，且带够能分析的属性；
    3. 上报接口只认同源 + 白名单，不会被灌垃圾。

运行：
    sudo bash -c 'set -a; . /etc/xinpect/website.env; set +a; cd /opt/xinpect-website \
        && python3 tests/test_funnel_analytics.py'

注意：会在 visitor_events 里写测试记录，跑完自动删除（只删本进程新增的 id）。
"""

import json
import os
import sqlite3
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

FAILED = []


def check(cond, msg):
    """断言一条。失败既记台账、也抛异常。

    为什么要抛：这个文件会被 pytest 自动收集（函数名是 test_*）。
    pytest 只认断言，不认我们自己的 FAILED 列表——只记录不抛，
    pytest 就会把失败的用例报成"通过"，比没有测试更糟。
    脚本模式下由 main() 的 try/except 接住，不影响后面的用例继续跑。
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


def _max_id(db):
    conn = sqlite3.connect(db)
    try:
        return conn.execute('SELECT COALESCE(max(id), 0) FROM visitor_events').fetchone()[0]
    except sqlite3.Error:
        return 0
    finally:
        conn.close()


def _rows(db, since_id):
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            'SELECT * FROM visitor_events WHERE id > ? ORDER BY id', (since_id,)
        ).fetchall()
    finally:
        conn.close()


def _cleanup(db, since_id):
    conn = sqlite3.connect(db)
    try:
        conn.execute('DELETE FROM visitor_events WHERE id > ?', (since_id,))
        conn.commit()
    finally:
        conn.close()


def test_schema_has_kind_and_detail():
    """老库升级后必须真的补上 kind / detail 两列，否则漏斗没法按类型分开算。"""
    app, db = _app()
    conn = sqlite3.connect(db)
    try:
        cols = {row[1] for row in conn.execute('PRAGMA table_info(visitor_events)')}
    finally:
        conn.close()
    check('kind' in cols, 'visitor_events 有 kind 列（区分页面访问 / 行为事件）')
    check('detail' in cols, 'visitor_events 有 detail 列（事件属性 JSON）')


def test_track_event_writes_event_kind():
    """track_event 写进来的必须是 kind='event'，且 detail 是能解析的 JSON。"""
    from modules.visitor_analytics import track_event
    app, db = _app()
    app.config['TESTING'] = True
    app.config['VISITOR_ANALYTICS_ALLOW_TESTING'] = True
    start = _max_id(db)
    try:
        client = app.test_client()
        client.get('/try')  # 先拿到 xp_vid 才有 vid 可挂
        # 没有 cookie 时不再静默丢弃事件：就地发放一个 vid 落库，
        # 并由 after_request 下发给浏览器，所以不会变成串不起来的孤儿记录。
        with app.test_request_context('/', headers={'Cookie': ''}):
            from modules.visitor_analytics import current_vid
            issued = current_vid()
            wrote = track_event('test.probe', n=1, tag='x')
        check(wrote is True, '没有 cookie 时就地发放 vid 并落事件（不再丢）')
        probes = [x for x in _rows(db, start) if x['path'] == 'test.probe']
        check(bool(probes) and probes[-1]['vid'] == issued,
              '事件挂在这次发放的 vid 上，后续请求能串起来')
    finally:
        app.config['VISITOR_ANALYTICS_ALLOW_TESTING'] = False
        _cleanup(db, start)


def test_page_and_event_are_separated():
    """页面访问不能混进事件统计——否则「打开试扫页」会被算法污染。"""
    app, db = _app()
    app.config['TESTING'] = True
    app.config['VISITOR_ANALYTICS_ALLOW_TESTING'] = True
    start = _max_id(db)
    try:
        client = app.test_client()
        client.get('/try')
        client.post('/api/track', json={'event': 'try.submit'},
                    headers={'Origin': 'http://localhost'})
        rows = _rows(db, start)
        kinds = {r['kind'] for r in rows}
        check('page' in kinds, '访问 /try 落了一条 kind=page')
        check('event' in kinds, '上报 try.submit 落了一条 kind=event')
        page_paths = {r['path'] for r in rows if r['kind'] == 'page'}
        event_paths = {r['path'] for r in rows if r['kind'] == 'event'}
        check('try.submit' not in page_paths, 'try.submit 没有被当成页面访问记下来')
        check('/try' not in event_paths, '/try 没有被当成行为事件记下来')
    finally:
        app.config['VISITOR_ANALYTICS_ALLOW_TESTING'] = False
        _cleanup(db, start)


def test_track_api_whitelist_and_origin():
    """上报接口：白名单外拒收、非同源拒收、白名单内收下且属性是标量。"""
    app, db = _app()
    app.config['TESTING'] = True
    app.config['VISITOR_ANALYTICS_ALLOW_TESTING'] = True
    start = _max_id(db)
    try:
        client = app.test_client()
        client.get('/try')  # 种下 xp_vid

        r = client.post('/api/track', json={'event': 'hack.whatever'},
                        headers={'Origin': 'http://localhost'})
        check(r.status_code == 400, '白名单外的事件被拒（400）')

        r = client.post('/api/track', json={'event': 'try.cta_click'})
        check(r.status_code == 403, '没有来源头的跨站上报被拒（403）')

        r = client.post('/api/track',
                        json={'event': 'try.cta_click',
                              'props': {'issues': 3, 'grade': 'D', 'junk': {'a': 1}}},
                        headers={'Origin': 'http://localhost'})
        check(r.status_code == 200, '同源白名单事件被接受（200）')

        rows = [x for x in _rows(db, start) if x['kind'] == 'event']
        detail = {}
        for row in rows:
            if row['path'] == 'try.cta_click' and row['detail']:
                detail = json.loads(row['detail'])
        check(detail.get('issues') == 3, '标量属性原样落库（issues=3）')
        check(detail.get('grade') == 'D', '字符串属性原样落库（grade=D）')
        check('junk' not in detail, '嵌套对象被丢弃（只收标量）')
    finally:
        app.config['VISITOR_ANALYTICS_ALLOW_TESTING'] = False
        _cleanup(db, start)


def test_try_scan_failure_is_recorded():
    """试扫失败也要落事件——不记失败，就永远不知道用户卡在哪一步。"""
    app, db = _app()
    app.config['TESTING'] = True
    app.config['VISITOR_ANALYTICS_ALLOW_TESTING'] = True
    start = _max_id(db)
    try:
        client = app.test_client()
        # /try 会给这个 client 发一个新的访客 id，额度天然是满的 3 次；
        # 额度按 vid 记账（不再按 IP、也不在内存里），所以不用手动清计数。
        client.get('/try')
        r = client.post('/api/try-scan', json={'code': '', 'language': 'python'})
        check(r.status_code == 400, '空代码返回 400')

        events = [x for x in _rows(db, start)
                  if x['kind'] == 'event' and x['path'] == 'try.fail']
        check(len(events) >= 1, '失败落了一条 try.fail 事件')
        if events:
            detail = json.loads(events[-1]['detail'] or '{}')
            check(detail.get('reason') == 'empty', '失败原因被记下来（reason=empty）')
    finally:
        app.config['VISITOR_ANALYTICS_ALLOW_TESTING'] = False
        _cleanup(db, start)


def test_report_script_covers_funnel():
    """报表脚本必须真的会输出试扫漏斗——报表里没有，等于没埋。"""
    path = os.path.join(BASE, 'scripts', 'visitor_report.py')
    src = open(path, encoding='utf-8').read()
    check('免费试扫漏斗' in src, '报表含「免费试扫漏斗」段落')
    check("kind = 'page'" in src, '报表的页面查询带 kind 过滤')
    check("kind = 'event'" in src, '报表的事件查询带 kind 过滤')
    check('try.cta_click' in src, '报表统计了注册引导点击')
    check('json_extract' in src, '报表能按事件属性分桶（json_extract）')


def test_no_code_content_is_tracked():
    """铁律：埋点不许记录用户粘贴的代码内容。"""
    src = open(os.path.join(BASE, 'modules', 'visitor_analytics.py'), encoding='utf-8').read()
    body = src.split('def track_event', 1)[-1]
    for bad in ('code', 'source', 'content'):
        check(f"'{bad}'" not in body and f'"{bad}"' not in body,
              f'track_event 没有把 {bad} 写进埋点')


def test_api_paths_never_count_as_pages():
    """接口路径不能算成页面访问——带前缀的也不许漏。

    实测踩过：/xinpect/api/scan/health 被记成一次页面访问，
    因为过滤只认 '/api/' 开头，认不出带前缀的接口。
    """
    from modules.visitor_analytics import _is_trackable
    check(_is_trackable('/xinpect/api/scan/health', 'GET') is False,
          '/xinpect/api/scan/health 不算页面访问')
    check(_is_trackable('/api/try-scan', 'GET') is False, '/api/try-scan 不算页面访问')
    check(_is_trackable('/try', 'GET') is True, '/try 算页面访问')
    check(_is_trackable('/', 'GET') is True, '首页算页面访问')
    check(_is_trackable('/api/try-scan', 'POST') is False, 'POST 一律不算页面访问')


def test_try_page_does_not_overclaim():
    """试扫页面必须先交代「这是初筛」。

    试扫只跑规范层 + 安全引擎、basic 模式，和完整报告不是一个量级。
    页面上如果直接说「代码很干净」，等于替用户下了个我们没资格下的结论——
    比不报还危险：他会真以为没问题。
    """
    src = open(os.path.join(BASE, 'templates', 'try.html'), encoding='utf-8').read()
    check('初筛' in src, '页面写明了「试扫是初筛」')
    check('不含性能' in src or '性能、架构' in src, '页面说明了初筛不覆盖哪些维度')
    check('代码很干净' not in src, '没有「代码很干净」这种绝对结论')
    check('cta-title' in src, '注册引导标题按本次结果动态生成（不是套话）')


def main():
    print('试扫漏斗埋点守卫')
    for fn in (
        test_schema_has_kind_and_detail,
        test_track_event_writes_event_kind,
        test_page_and_event_are_separated,
        test_track_api_whitelist_and_origin,
        test_try_scan_failure_is_recorded,
        test_report_script_covers_funnel,
        test_no_code_content_is_tracked,
        test_api_paths_never_count_as_pages,
        test_try_page_does_not_overclaim,
    ):
        print(f'\n[{fn.__name__}] {fn.__doc__.strip().splitlines()[0]}')
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            # check() 抛出来的失败已经记过台账了，别重复记、也别再打一堆堆栈
            if str(exc) not in FAILED:
                import traceback
                traceback.print_exc()
                FAILED.append(f'{fn.__name__}: {exc}')

    print('\n' + '=' * 60)
    if FAILED:
        print(f'失败 {len(FAILED)} 项：')
        for f in FAILED:
            print(f'  - {f}')
        sys.exit(1)
    print('全部通过')


if __name__ == '__main__':
    main()
