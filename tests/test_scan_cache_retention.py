# -*- coding: utf-8 -*-
"""扫描结果库保留策略的守卫。

钉住这些事（不是「函数存在」，是「删得对、不误删、不抢锁」）：
1. 过期的扫描记录删掉，保留期内的一条不动
2. 代码副本跟着它的扫描记录一起走，删完不留孤儿行
3. 有任务在跑时整轮跳过（清理绝不能跟客户正在跑的扫描抢写锁）
4. 网站侧有 running 的扫描也算在途（API 直连扫描不写网站表，所以两边都要看）
5. 试运行不删任何东西
6. 没有 XINPECT_DATA_DIR 就报错，不许猜一个默认路径
7. 策略参数在合理范围（天数太短会误删客户报告，太长等于没清）
8. 重复跑第二遍不再删东西（幂等，cron 天天跑不会越界）
"""
import os
import sqlite3
import sys
import tempfile
import time
import shutil

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from modules import result_retention as rr  # noqa: E402

NOW = time.time()
OLD = NOW - 40 * 86400     # 40 天前，该删
FRESH = NOW - 1 * 86400    # 1 天前，该留


def _make_db(path, scans=(('s-old', OLD), ('s-new', FRESH)), tasks=(), code=True):
    conn = sqlite3.connect(path)
    conn.executescript('''
        CREATE TABLE scan_results (
            scan_id TEXT PRIMARY KEY, scan_mode TEXT NOT NULL DEFAULT 'full',
            file_count INTEGER DEFAULT 0, total_issues INTEGER DEFAULT 0,
            total_score REAL DEFAULT 0, brains TEXT DEFAULT '',
            duration_ms REAL DEFAULT 0, client_ip TEXT DEFAULT '',
            created_at REAL NOT NULL, result_json TEXT NOT NULL,
            user_id TEXT DEFAULT NULL, content_fingerprint TEXT DEFAULT NULL);
        CREATE TABLE scan_tasks (
            task_id TEXT PRIMARY KEY, scan_id TEXT, status TEXT NOT NULL DEFAULT 'queued',
            request_json TEXT NOT NULL, result_summary TEXT, error_message TEXT,
            client_ip TEXT DEFAULT '');
        CREATE INDEX idx_scan_created ON scan_results(created_at DESC);
    ''')
    if code:
        conn.execute('''CREATE TABLE scan_code_files (
            scan_id TEXT NOT NULL, file_path TEXT NOT NULL,
            content TEXT NOT NULL, PRIMARY KEY (scan_id, file_path))''')
    for sid, ts in scans:
        conn.execute('INSERT INTO scan_results (scan_id, created_at, result_json)'
                     ' VALUES (?,?,?)', (sid, ts, '{"issues":[]}'))
        if code:
            conn.execute('INSERT INTO scan_code_files (scan_id, file_path, content)'
                         ' VALUES (?,?,?)', (sid, 'a.py', 'print(1)\n' * 50))
    for i, (sid, status) in enumerate(tasks):
        conn.execute('INSERT INTO scan_tasks (task_id, scan_id, status, request_json)'
                     ' VALUES (?,?,?,?)', ('t%d' % i, sid, status, '{}'))
    conn.commit()
    conn.close()


def _make_website_db(path, rows=()):
    """rows: (scan_id, scan_status, created_at)"""
    conn = sqlite3.connect(path)
    conn.execute('''CREATE TABLE scans (
        scan_id TEXT UNIQUE NOT NULL, scan_status TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime')))''')
    for sid, status, created in rows:
        conn.execute('INSERT INTO scans (scan_id, scan_status, created_at)'
                     ' VALUES (?,?,?)', (sid, status, created))
    conn.commit()
    conn.close()


class _Sandbox(object):
    def __init__(self, scans=(('s-old', OLD), ('s-new', FRESH)), tasks=(),
                 code=True, website_rows=()):
        self.dir = tempfile.mkdtemp(prefix='xinpect_retention_')
        self.db = os.path.join(self.dir, 'scan_results.db')
        self.web = os.path.join(self.dir, 'xinpect.db')
        _make_db(self.db, scans=scans, tasks=tasks, code=code)
        _make_website_db(self.web, website_rows)

    def rows(self, table):
        conn = sqlite3.connect(self.db)
        try:
            return [r[0] for r in conn.execute('SELECT scan_id FROM %s' % table)]
        finally:
            conn.close()

    def close(self):
        shutil.rmtree(self.dir, ignore_errors=True)


def test_old_rows_deleted_recent_kept():
    sb = _Sandbox()
    try:
        rep = rr.purge(db_path=sb.db, website_db_path=sb.web, now=NOW,
                       sleep_seconds=0)
        assert rep['skipped'] is None, rep
        assert rep['deleted_scans'] == 1, rep
        left = sb.rows('scan_results')
        assert left == ['s-new'], left
    finally:
        sb.close()


def test_code_rows_follow_their_scan():
    sb = _Sandbox()
    try:
        rr.purge(db_path=sb.db, website_db_path=sb.web, now=NOW, sleep_seconds=0)
        code = sb.rows('scan_code_files')
        assert code == ['s-new'], code
        assert rr.dangling_code_rows(sb.db) == 0
    finally:
        sb.close()


def test_skip_when_scan_in_flight():
    sb = _Sandbox(tasks=(('s-new', 'running'),))
    try:
        rep = rr.purge(db_path=sb.db, website_db_path=sb.web, now=NOW, sleep_seconds=0)
        assert rep['skipped'] == 'in_flight', rep
        assert rep['deleted_scans'] == 0, rep
        assert sorted(sb.rows('scan_results')) == ['s-new', 's-old'], '有任务在跑却动了数据'
    finally:
        sb.close()


def test_skip_when_website_scan_running():
    # 网站侧 running 也算在途：API 直连扫描不写网站表，但网站发起的扫描
    # 在扫描库任务表里可能还没落条目，只看一边就会误伤。
    sb = _Sandbox(website_rows=(('some-scan', 'running',
                                time.strftime('%Y-%m-%d %H:%M:%S')),))
    try:
        rep = rr.purge(db_path=sb.db, website_db_path=sb.web, now=NOW, sleep_seconds=0)
        assert rep['skipped'] == 'in_flight', rep
        assert rep['deleted_scans'] == 0, rep
    finally:
        sb.close()


def test_dry_run_deletes_nothing():
    sb = _Sandbox()
    try:
        rep = rr.purge(db_path=sb.db, website_db_path=sb.web, now=NOW,
                       dry_run=True, sleep_seconds=0)
        assert rep['deleted_scans'] == 1, rep
        assert sorted(sb.rows('scan_results')) == ['s-new', 's-old'], '试运行删了数据'
    finally:
        sb.close()


def test_missing_env_is_loud():
    saved = os.environ.pop('XINPECT_DATA_DIR', None)
    try:
        try:
            rr.resolve_db_path()
        except RuntimeError as e:
            assert 'XINPECT_DATA_DIR' in str(e)
        else:
            raise AssertionError('没有 XINPECT_DATA_DIR 却猜出了一个库路径')
    finally:
        if saved is not None:
            os.environ['XINPECT_DATA_DIR'] = saved


def test_policy_sane():
    assert 7 <= rr.RETENTION_DAYS <= 90, '保留天数 %r 不合理' % rr.RETENTION_DAYS
    assert 100 <= rr.BATCH_SIZE <= 5000, '批大小 %r 不合理' % rr.BATCH_SIZE
    assert rr.BATCH_SLEEP_SECONDS >= 0.1, '批间必须让路，否则会打满磁盘 IO'


def test_idempotent():
    sb = _Sandbox()
    try:
        rr.purge(db_path=sb.db, website_db_path=sb.web, now=NOW, sleep_seconds=0)
        again = rr.purge(db_path=sb.db, website_db_path=sb.web, now=NOW, sleep_seconds=0)
        assert again['deleted_scans'] == 0, again
        assert sb.rows('scan_results') == ['s-new']
    finally:
        sb.close()


def test_respects_batch_size():
    scans = [('s%d' % i, OLD) for i in range(5)] + [('s-new', FRESH)]
    sb = _Sandbox(scans=scans)
    try:
        rep = rr.purge(db_path=sb.db, website_db_path=sb.web, now=NOW,
                       batch_size=2, sleep_seconds=0)
        assert rep['deleted_scans'] == 5, rep
        assert rep['batches'] == 3, rep
        assert sb.rows('scan_results') == ['s-new']
    finally:
        sb.close()


if __name__ == '__main__':
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            try:
                fn()
                print('  ok   %s' % name)
            except Exception as e:
                fails += 1
                print('  FAIL %s: %s' % (name, e))
    print('扫描结果库保留守卫：%d 条失败' % fails)
    sys.exit(1 if fails else 0)
