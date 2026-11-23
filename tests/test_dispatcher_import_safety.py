# -*- coding: utf-8 -*-
"""队列调度器与在途任务判活的守卫。

钉住 2026-11-14 实证的缺陷：
  任何进程只要 `from modules import api`，就会起一个队列调度线程，
  并跑「重启清扫」——把 scans 表里所有 pending 无条件判成「服务重启中断」并退款，
  **完全不看心跳**。复现证据：造一条心跳是「刚刚」的在途任务，
  另起一个进程只做一次 import，那条任务当场变成 failed。

这个缺陷的杀伤面不是某个监控脚本，而是「所有 import 网站模块的东西」：
QA 的 pytest、巡检脚本、工具脚本、任何探针。它们都会顺手砍掉生产在途任务。

本文件钉住四件事：
1. 导入模块不许起调度线程
2. 只有服务入口能启动调度器
3. 判活只认心跳：心跳还在就绝不准杀
4. 心跳确实停了的任务必须被判死并退款（功能没丢）

不依赖 pytest fixture：QA 里 pytest 与直跑两个分支都要能过。
"""
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent
# 直跑（python3 tests/xxx.py）时 sys.path[0] 是 tests/，站点根要自己加
if str(SITE) not in sys.path:
    sys.path.insert(0, str(SITE))

import modules.api as api  # noqa: E402
SCHEMA = """
CREATE TABLE scans (
    scan_id TEXT PRIMARY KEY, user_id INTEGER, title TEXT, file_count INTEGER,
    files_meta TEXT, results TEXT, score REAL, grade TEXT, issue_count INTEGER,
    language TEXT, created_at TEXT, credits_spent INTEGER, total_lines INTEGER,
    scan_mode TEXT, source TEXT, scan_status TEXT, scan_progress INTEGER,
    scan_progress_text TEXT, content_hash TEXT, total_bytes INTEGER,
    last_heartbeat_at TEXT, scan_error TEXT
);
"""


def _ts(minutes_ago=0):
    return (datetime.now() - timedelta(minutes=minutes_ago)).strftime('%Y-%m-%d %H:%M:%S')


def _db(rows):
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.executemany(
        "INSERT INTO scans (scan_id, user_id, created_at, credits_spent, "
        "scan_status, last_heartbeat_at, scan_error, file_count) "
        "VALUES (?,?,?,?,?,?,NULL,1)", rows)
    conn.commit()
    return conn


def _reap(rows):
    """跑一次收割，返回 (连接, 退款记录)。用完还原全局，不污染别的用例。"""
    conn = _db(rows)
    refunds = []
    old_db, old_grant = api.get_db, api.grant_credits
    api.get_db = lambda: conn
    api.grant_credits = lambda uid, amt, **kw: refunds.append((uid, amt, kw))
    try:
        api._reap_stale_scans()
    finally:
        api.get_db, api.grant_credits = old_db, old_grant
    return conn, refunds


def _status(conn, scan_id):
    return conn.execute("SELECT scan_status, scan_error FROM scans WHERE scan_id=?",
                        (scan_id,)).fetchone()


# ---------- 判活：心跳还在就不许杀 ----------

def test_live_heartbeat_survives():
    """心跳是「刚刚」的在途任务，哪怕已经跑了很久，也不许判死。"""
    conn, refunds = _reap([('s_live', 15, _ts(40), 133, 'pending', _ts(0))])
    row = _status(conn, 's_live')
    assert row['scan_status'] == 'pending', '心跳正常的任务被杀了'
    assert row['scan_error'] is None
    assert refunds == [], '不该有退款'


def test_live_heartbeat_two_minutes_silent_survives():
    """静默 2 分钟仍在宽限期内（心跳线程写库可能被锁短暂卡住）。"""
    conn, _ = _reap([('s_slow', 15, _ts(20), 50, 'pending', _ts(2))])
    assert _status(conn, 's_slow')['scan_status'] == 'pending'


# ---------- 收割：心跳真停了的必须判死退款 ----------

def test_silent_heartbeat_is_reaped_and_refunded():
    conn, refunds = _reap([('s_dead', 15, _ts(30), 133, 'pending', _ts(10))])
    row = _status(conn, 's_dead')
    assert row['scan_status'] == 'failed', '心跳停 10 分钟的任务没被收割'
    assert '中断' in row['scan_error']
    assert refunds and refunds[0][0] == 15 and refunds[0][1] == 133, '没退款'


def test_reap_reason_matches_real_rule():
    """失败原因要写真实判据（心跳静默多少秒），不能还写「45 分钟上限」。

    客户任务跑了一分半就被判死，却被告知超了 45 分钟上限 —— 没法排查。
    """
    conn, _ = _reap([('s_dead2', 15, _ts(30), 10, 'pending', _ts(10))])
    reason = _status(conn, 's_dead2')['scan_error']
    assert str(api._HEARTBEAT_SILENCE_SECONDS) in reason, \
        '失败原因没写真实的心跳静默秒数：%s' % reason
    assert '45' not in reason, '失败原因还留着「45 分钟上限」的旧说法：%s' % reason


def test_never_started_task_uses_created_at():
    """心跳为空（还没出队）时用创建时间判活，刚创建的不许杀。"""
    conn, _ = _reap([('s_new', 15, _ts(0), 10, 'pending', None)])
    assert _status(conn, 's_new')['scan_status'] == 'pending'


# ---------- 结构：导入不许起线程、清扫函数不许回来 ----------

def test_import_does_not_start_dispatcher():
    """另起进程只做一次 import，线程表里不该出现调度器。"""
    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "import threading\n"
        "from modules import api\n"
        "print(','.join(t.name for t in threading.enumerate()))\n"
    ) % str(SITE)
    r = subprocess.run([sys.executable, '-c', code], capture_output=True,
                       text=True, timeout=180, cwd=str(SITE))
    assert r.returncode == 0, '子进程导入失败：%s' % r.stderr[-600:]
    assert 'scan-queue-dispatcher' not in r.stdout, \
        '导入模块就起了调度线程：%s' % r.stdout.strip()


def test_no_module_level_dispatcher_start():
    src = (SITE / 'modules' / 'api.py').read_text(encoding='utf-8')
    assert not re.search(r'^start_queue_dispatcher\(\)', src, re.M), \
        'api.py 里又有模块级启动调度器的调用'


def test_importing_entry_does_not_start_background_workers():
    """import app 也不许起后台 worker：Redis 队列 worker 也曾在模块级启动。

    它比调度器更隐蔽：导入之后会静静地去 Redis 抢任务执行，
    测试进程、巡检进程都可能替生产的活在暗处跑。
    """
    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "import threading\n"
        "import app as entry\n"
        "print(','.join(t.name for t in threading.enumerate()))\n"
    ) % str(SITE)
    r = subprocess.run([sys.executable, '-c', code], capture_output=True,
                       text=True, timeout=240, cwd=str(SITE))
    assert r.returncode == 0, '子进程导入 app 失败：%s' % r.stderr[-600:]
    names = r.stdout.strip()
    assert 'queue-worker' not in names, '导入 app 就起了 Redis 队列 worker：%s' % names
    assert 'scan-queue-dispatcher' not in names, '导入 app 就起了扫描调度器：%s' % names


def test_startup_sweep_is_gone():
    src = (SITE / 'modules' / 'api.py').read_text(encoding='utf-8')
    assert '_sweep_on_startup' not in src, '重启清扫函数又回来了'
    assert '服务重启中断' not in src, '无条件判死的语句又回来了'


def test_entrypoint_starts_dispatcher_after_init():
    src = (SITE / 'app.py').read_text(encoding='utf-8')
    body = src.split('if __name__ == "__main__":', 1)[-1]
    at = body.find('start_queue_dispatcher()')
    assert at > 0, '服务入口没有启动调度器，排队任务永远不会被执行'
    assert body.find('init_db()') < at, '调度器必须晚于建表启动，否则首圈会撞未建列'
    assert body.find('start_worker_thread()') > 0, \
        'Redis 队列 worker 移出模块级之后，入口里必须启动，否则队列没人干活'


def test_ticker_retries_instead_of_dying():
    """心跳线程遇到一次数据库锁冲突就 return，会让活任务失去心跳后被误杀。"""
    src = (SITE / 'modules' / 'api.py').read_text(encoding='utf-8')
    assert 'fails >= 60' in src, '心跳线程的连续失败上限没了'
    assert 'logger.warning("progress ticker %s: %s", scan_id, e)\n' \
           '                return' not in src, '心跳线程又变成遇错即退'


# ---------- 忙不是病：引擎忙不许判成自己不健康 ----------

def _health_with(get_impl):
    """把 requests.get 换掉，看 /health 怎么判。"""
    import requests
    from app import app as flask_app

    old = requests.get
    requests.get = get_impl
    try:
        with flask_app.test_client() as c:
            r = c.get('/health')
            return r.status_code, r.get_json()
    finally:
        requests.get = old


def test_health_treats_engine_timeout_as_busy():
    """引擎超时 = 正在扫，不是倒了。必须 200 + busy，不许 503。"""
    import requests

    def timeout(*a, **kw):
        raise requests.exceptions.Timeout('read timed out')

    code, body = _health_with(timeout)
    assert code == 200, '引擎一忙就把自己判成病（503），巡检会据此重启官网杀任务'
    assert body['scanner']['status'] == 'busy'
    assert body['status'] == 'ok'
    assert 'active_scans' in body


def test_health_reports_503_when_engine_refuses():
    """引擎真连不上，还是要如实报不健康，不能一律放过。"""
    import requests

    def refused(*a, **kw):
        raise requests.exceptions.ConnectionError('connection refused')

    code, body = _health_with(refused)
    assert code == 503, '引擎倒了却报健康，等于放弃监控'
    assert body['scanner']['status'] == 'down'


def test_monitor_skips_restart_while_scans_running():
    """巡检重启会掐断进程里正在跑的任务，有在途任务时不许动手。"""
    src = (SITE / 'monitoring' / 'xinpect_monitor.py').read_text(encoding='utf-8')
    assert 'active_scans' in src, '巡检没看有没有在途任务就要重启'
    assert '[SKIP]' in src, '没有「有任务在跑就不修」的分支'
    assert src.count('SLOW_TOLERANCE_CYCLES') >= 2, \
        '连续容忍轮次只定义没使用（历史上就是这么空着的）'


if __name__ == '__main__':
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith('test_')]
    bad = 0
    for name, fn in fns:
        try:
            fn()
            print('  ok   %s' % name)
        except AssertionError as e:
            bad += 1
            print('  FAIL %s: %s' % (name, e))
    print('%d 条用例，失败 %d 条' % (len(fns), bad))
    raise SystemExit(1 if bad else 0)
