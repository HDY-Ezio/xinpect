"""真人访客口径守卫：我们自己的工具不许被数成客户。

## 为什么需要这组测试

2026-11-18 发现：报表上每天 1000~2000 个「独立访客」，同期真人扫描为 0。
翻 UA 才看清主力是我们的监控/守卫脚本：

    xinpect-uptime-sv/1.0      1140 次/天
    xp-consistency-guard/1.0    348 次/天
    xp-growth-guard/1.0          84 次/天
    xinpect-audit/1.0            72 次/天

它们没命中 `_BOT_RE`（UA 是我们自己起的名字，里面没有 bot/spider 这类词），
于是被算成了真人。**这不是爬虫问题，是我们把自己数成了客户。**

后果比没数据更糟：它会让人得出「有人来过但没转化」的结论，
而真相是「根本没人来过」——据这个结论做决定，方向一定是错的。

## 这些测试在守什么

1. 内部 UA 必须落 `is_internal=1`，且**不能**同时被算成爬虫（两档互不干扰）；
2. 真浏览器不能被误判成内部流量（否则真人也会被排除，从"多算"变成"少算"）；
3. 口径只有一处出处：报表脚本里不许再出现裸的 `is_bot = 0`；
4. **端到端**：报表的「独立访客」真的不受内部流量影响，同时还能正常增长
   ——第 4 条是重点。前三条都能在"东西存在"层面通过，只有第 4 条能证明
   "事情成了"（数字真的对上了）。

服务器没装 pytest，所以本文件同时支持 pytest 与 `python3 verify_visitor_scope.py`。
"""

import os
import re
import sqlite3
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

DB_PATH = os.path.join(BASE_DIR, 'xinpect.db')
MODULES_DIR = os.path.join(BASE_DIR, 'modules')
SCOPE = os.path.join(MODULES_DIR, 'visitor_scope.py')
REPORT = os.path.join(BASE_DIR, 'scripts', 'visitor_report.py')

_CHROME = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
           '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')


def _read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def _conn():
    return sqlite3.connect(DB_PATH, timeout=5)


def _cleanup(since_id):
    """删掉测试期间插入的记录。**必须删**——往生产访客表里留垃圾，等于我们自己
    又制造一次「假访客」，那就成了用新错误掩盖旧错误。"""
    conn = _conn()
    try:
        conn.execute('DELETE FROM visitor_events WHERE id > ?', (since_id,))
        conn.commit()
    finally:
        conn.close()


def _max_id():
    conn = _conn()
    try:
        return conn.execute('SELECT coalesce(max(id), 0) FROM visitor_events').fetchone()[0]
    except sqlite3.Error:
        return 0
    finally:
        conn.close()


def _insert(vid, ua, path='/guard-probe'):
    """直接写表，模拟**历史脏数据**（is_internal 故意留 0）。

    只在测回填时才该用它——回填要处理的正是这种"规则上线前写进去的行"。
    测「新记录会不会被标对」必须走 `_http_probe`，走真实链路。
    """
    conn = _conn()
    try:
        conn.execute(
            'INSERT INTO visitor_events (vid, kind, path, method, ua, ip, '
            'is_bot, is_internal) VALUES (?, ?, ?, ?, ?, ?, 0, 0)',
            (vid, 'page', path, 'GET', ua, '127.0.0.1'))
        conn.commit()
        return conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    finally:
        conn.close()


# 探针用的假外网 IP（RFC 5737 文档段）。不能用 127.0.0.1：体检反复跑，
# 这条路上会攒出几十个单次命中的 vid，被「一次一换 cookie」判据整段剔除。
PROBE_IP_INTERNAL = '203.0.113.10'
PROBE_IP_HUMAN = '203.0.113.20'


def _http_probes(ua, count=1, same_client=False, ip=None):
    """走真实链路发 count 次请求（每次一个新 client = 一个新 vid）。

    **不能用 `_insert` 代替**：那样测的是「我能不能把字段写成 1」，
    而不是「规则会不会把这条记成 1」。第一版就是图省事直接写表，
    结果三条内部流量全被算进访客，守卫判红——判红是对的，错的是测试。
    """
    from app import app

    app.config['TESTING'] = True
    prev = app.config.get('VISITOR_ANALYTICS_ALLOW_TESTING')
    app.config['VISITOR_ANALYTICS_ALLOW_TESTING'] = True
    try:
        headers = {'User-Agent': ua}
        if ip:
            headers['X-Forwarded-For'] = ip
        if same_client:
            # 同一访客连看两页：1 个 vid、2 次命中。
            # 每个请求都新建 client 等于「一次一换 cookie」，会被机器判据吃掉。
            c = app.test_client()
            for _ in range(count):
                c.get('/pricing', headers=headers)
        else:
            for _ in range(count):
                app.test_client().get('/pricing', headers=headers)
    finally:
        app.config['VISITOR_ANALYTICS_ALLOW_TESTING'] = prev


def _report_visitors():
    """跑一次报表，取「独立访客」那个数。报表是唯一对外的口径，测它才有意义。"""
    out = subprocess.run(
        [sys.executable, REPORT, '--days', '1'],
        capture_output=True, text=True, cwd=BASE_DIR, timeout=120)
    if out.returncode != 0:
        raise AssertionError(f'报表脚本跑失败（rc={out.returncode}）: {out.stderr[-500:]}')
    m = re.search(r'独立访客\s+(\d+)\s+人', out.stdout)
    if not m:
        raise AssertionError(f'报表输出里找不到「独立访客」: {out.stdout[:400]}')
    return int(m.group(1)), out.stdout


# ------------------------------------------------------------------ 判据本身

def test_scope_module_has_no_imports():
    """visitor_scope.py 必须零依赖。

    报表脚本按文件路径加载它（不能 import modules 包，那会把整个 Flask app
    拉起来）。一旦有人往里面加了 `import`，报表就会在加载时炸——
    而且是在生产上、凌晨、没人看的时候炸。
    """
    src = _read(SCOPE)
    body = '\n'.join(
        line for line in src.splitlines()
        if line.strip() and not line.strip().startswith('#'))
    # 去掉模块 docstring（""" ... """）后再看
    body = re.sub(r'"""[\s\S]*?"""', '', body)
    bad = [ln for ln in body.splitlines()
           if ln.strip().startswith(('import ', 'from '))]
    assert not bad, f'visitor_scope.py 不许 import 任何东西，发现: {bad}'


def test_internal_ua_matches_prefix_rule():
    """判据必须是「前缀」规则，不是一份 UA 全串名单。

    名单会随脚本增减而漏；前缀是我们自己的命名空间，新脚本自动覆盖。
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location('scope_probe', SCOPE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert mod.is_internal_ua('xinpect-uptime-sv/1.0'), '监控脚本 UA 没被认成内部'
    assert mod.is_internal_ua('xp-consistency-guard/1.0'), '守卫脚本 UA 没被认成内部'
    assert mod.is_internal_ua('XP-future-tool/9.9'), '大小写不该影响判定'
    assert mod.is_internal_ua('xinpect-something-new/0.1'), \
        '新写的内部工具（前缀相同）必须自动覆盖，不该要求回来改代码'

    assert not mod.is_internal_ua(_CHROME), '真浏览器被误判成内部流量'
    assert not mod.is_internal_ua('Googlebot/2.1'), '爬虫不该算内部流量'
    assert not mod.is_internal_ua(''), '空 UA 不该算内部流量'
    assert not mod.is_internal_ua('Mozilla/5.0 xinpect-inside'), \
        '前缀只看开头，UA 中间出现 xinpect 不算我们自己的工具'


def test_visitor_filter_is_single_source():
    """报表脚本里不许再出现裸的 `is_bot = 0`。

    这就是根因的写法：同一个判据散在十几条 SQL 里，改一处漏一处，
    账面出现两个数，然后没人知道该信哪个。
    """
    src = _read(REPORT)
    # 允许出现的是 `is_bot = 1`（爬虫计数，另一种用途）和注释
    offenders = []
    for i, line in enumerate(src.splitlines(), 1):
        code = line.split('#', 1)[0]
        if re.search(r'is_bot\s*=\s*0', code):
            offenders.append(f'{i}: {line.strip()}')
    assert not offenders, (
        '报表脚本里还有裸的 is_bot = 0，必须改用 {VF}（来自 visitor_scope）:\n'
        + '\n'.join(offenders))


# ------------------------------------------------------------------ 落库行为

def test_internal_ua_is_flagged_on_insert():
    """内部工具请求落库后 is_internal=1、is_bot=0（各归各档，不互相污染）。"""
    from app import app

    app.config['TESTING'] = True
    start = _max_id()
    prev = app.config.get('VISITOR_ANALYTICS_ALLOW_TESTING')
    app.config['VISITOR_ANALYTICS_ALLOW_TESTING'] = True
    try:
        c = app.test_client()
        r = c.get('/pricing', headers={'User-Agent': 'xinpect-uptime-sv/1.0'})
        assert r.status_code == 200

        conn = _conn()
        try:
            row = conn.execute(
                'SELECT is_bot, is_internal, ua FROM visitor_events '
                "WHERE path='/pricing' AND id > ? ORDER BY id DESC LIMIT 1",
                (start,)).fetchone()
        finally:
            conn.close()
    finally:
        app.config['VISITOR_ANALYTICS_ALLOW_TESTING'] = prev
        _cleanup(start)

    assert row is not None, '埋点没有落库'
    assert row[1] == 1, f'内部工具没被标记 is_internal: UA={row[2]!r}'
    assert row[0] == 0, f'内部工具被误标成爬虫（两档应各归各）: UA={row[2]!r}'


def test_real_browser_is_not_flagged():
    """真浏览器必须两个标记都是 0——否则从「多算」变成「少算」，一样错。"""
    from app import app

    app.config['TESTING'] = True
    start = _max_id()
    prev = app.config.get('VISITOR_ANALYTICS_ALLOW_TESTING')
    app.config['VISITOR_ANALYTICS_ALLOW_TESTING'] = True
    try:
        c = app.test_client()
        c.get('/pricing', headers={'User-Agent': _CHROME})

        conn = _conn()
        try:
            row = conn.execute(
                'SELECT is_bot, is_internal FROM visitor_events '
                "WHERE path='/pricing' AND id > ? ORDER BY id DESC LIMIT 1",
                (start,)).fetchone()
        finally:
            conn.close()
    finally:
        app.config['VISITOR_ANALYTICS_ALLOW_TESTING'] = prev
        _cleanup(start)

    assert row is not None, '埋点没有落库'
    assert row == (0, 0), f'真浏览器被标记成 bot/internal 了: {row}'


def test_404_probe_is_not_recorded():
    """探测请求（404）不许进访客表，但正常页面必须照记。

    2026-11-18 实测：7 天里 1894 次 `/.env`、`/.git/config` 探测，
    占了「独立访客」的 1353/1567——真人一个没多。

    **两个断言缺一不可**：只验「404 没记」的话，把整段记录逻辑删掉
    也能通过；必须同时验「正常页面记了」，才证明是筛出来的、不是关掉了。
    """
    from app import app

    app.config['TESTING'] = True
    start = _max_id()
    prev = app.config.get('VISITOR_ANALYTICS_ALLOW_TESTING')
    app.config['VISITOR_ANALYTICS_ALLOW_TESTING'] = True
    try:
        c = app.test_client()
        r = c.get('/.env', headers={'User-Agent': _CHROME})
        assert r.status_code == 404, f'探测路径居然没 404: {r.status_code}'

        c2 = app.test_client()
        r2 = c2.get('/pricing', headers={'User-Agent': _CHROME})
        assert r2.status_code == 200, f'正常页面居然不是 200: {r2.status_code}'

        conn = _conn()
        try:
            probe = conn.execute(
                "SELECT count(*) FROM visitor_events WHERE id > ? AND path='/.env'",
                (start,)).fetchone()[0]
            real = conn.execute(
                "SELECT count(*) FROM visitor_events WHERE id > ? AND path='/pricing'",
                (start,)).fetchone()[0]
        finally:
            conn.close()
    finally:
        app.config['VISITOR_ANALYTICS_ALLOW_TESTING'] = prev
        _cleanup(start)

    assert probe == 0, f'404 探测被记进了访客表（{probe} 条），访客数会被灌爆'
    assert real == 1, f'正常页面没被记录（{real} 条）——排除过头，把真人也挡了'


def test_report_excludes_internal_but_still_counts_people():
    """端到端：报表的「独立访客」不受内部流量影响，但真人来了要能涨。

    **这条是整组测试的核心**。前几条都只能证明「字段填对了」，
    只有这条能证明「报表上那个数字真的对了」——而人看的是那个数字。
    """
    before, _ = _report_visitors()

    start = _max_id()
    try:
        # 灌三条内部流量（走真实链路，模拟我们自己的监控脚本跑三次）
        _http_probes('xinpect-uptime-sv/1.0', count=3, ip=PROBE_IP_INTERNAL)
        after_internal, out = _report_visitors()
        assert after_internal == before, (
            f'内部流量被算进了访客：{before} -> {after_internal}\n'
            f'报表那行自检说明: '
            + next((l for l in out.splitlines() if '监控' in l), '(没有这行)'))

        # 再来一个真人访问：数字必须涨 1，证明报表没被改坏。
        # 同一 client 看两页 —— 真人不会只发一个请求就走，而且这样才不会被
        # 「一次一换 cookie」的机器判据当成爬虫（见 _http_probes 注释）。
        _http_probes(_CHROME, count=2, same_client=True, ip=PROBE_IP_HUMAN)
        after_human, _ = _report_visitors()
        assert after_human == before + 1, (
            f'真人访问没有让访客数 +1：{before} -> {after_human}'
            '（说明排除范围过头了，把真人也挡了）')
    finally:
        _cleanup(start)


def test_backfill_is_idempotent():
    """回填脚本跑两遍，第二遍应该没事可做（幂等），且不会误伤真人。"""
    script = os.path.join(BASE_DIR, 'scripts', 'backfill_internal_flag.py')
    assert os.path.exists(script), '回填脚本不存在'

    start = _max_id()
    try:
        _insert('c' * 32, 'xp-growth-guard/1.0')   # 应被回填
        _insert('d' * 32, _CHROME)                 # 不该被动

        for run in (1, 2):
            r = subprocess.run([sys.executable, script], capture_output=True,
                               text=True, cwd=BASE_DIR, timeout=120)
            assert r.returncode == 0, f'第 {run} 次回填失败: {r.stderr[-400:]}'

        conn = _conn()
        try:
            kept = conn.execute(
                'SELECT is_internal FROM visitor_events WHERE vid = ?',
                ('d' * 32,)).fetchone()
            fixed = conn.execute(
                'SELECT is_internal FROM visitor_events WHERE vid = ?',
                ('c' * 32,)).fetchone()
        finally:
            conn.close()

        assert fixed and fixed[0] == 1, '内部流量没有被回填'
        assert kept and kept[0] == 0, '回填误伤了真浏览器记录'
    finally:
        _cleanup(start)


def main():
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith('test_') and callable(f)]
    passed = 0
    for name, fn in tests:
        try:
            fn()
        except AssertionError as exc:
            print(f'[FAIL] {name}: {exc}')
            return 1
        except Exception as exc:  # noqa: BLE001
            print(f'[ERROR] {name}: {type(exc).__name__}: {exc}')
            return 1
        passed += 1
        print(f'[ok] {name}')
    print(f'VISITOR_SCOPE_GUARD_PASS={passed}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
