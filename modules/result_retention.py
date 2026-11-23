# -*- coding: utf-8 -*-
"""扫描结果库（scan_results.db）的保留策略。

为什么要有这个文件
------------------
这个库自 2026-08 上线起只增不删。2026-11-14 查的时候：4.2 GB、185239 条扫描、
212027 条代码副本，磁盘 79G 已用 41G。它之所以能白长三个月，是因为没有任何
一处代码问过「这些旧记录还有没有人要」——只问「能不能写进去」。

库里存的是什么
--------------
- scan_results：每个 scan_id 的结论 JSON（按内容指纹去重，同样的代码再扫直接命中）
- scan_code_files：该次扫描的**代码原文**（报告里回看代码片段用）

网站自己的 xinpect.db::scans 另存了一份完整结果（1530 条，客户能看到的报告都在那儿）。
所以删这里的旧记录不会让客户打不开报告，只会让「一个月前扫过的文件」重新算一次。

策略（天数只在这里定义一次，别在脚本里再写一遍）
------------------------------------------------
* 保留 RETENTION_DAYS 天，判定依据 scan_results.created_at（unix 秒）
* 分批删、批间让路：2 核机器上一次删十几万行会把磁盘 IO 打满，
  官网和正在跑的扫描会一起卡——这正是 11-13 整机卡死的同一种病
* 有在途任务时整轮跳过：清理绝不能跟客户正在跑的扫描抢写锁
* 代码副本按同一批 scan_id 删，不留孤儿行
* 默认不 VACUUM（要独占锁 + 几分钟），只在空闲且碎片率高时由 compact() 做
"""

import os
import sqlite3
import time
from datetime import datetime, timezone

# ---- 策略参数（唯一出处）----
RETENTION_DAYS = 30          # 保留天数
BATCH_SIZE = 2000            # 每批删多少条
BATCH_SLEEP_SECONDS = 0.3    # 批间让路
BUSY_TIMEOUT_MS = 5000       # 抢不到写锁就等 5 秒，不硬撞扫描器
COMPACT_MIN_FREE_RATIO = 0.25  # 空闲页占比超过这个才值得 VACUUM

# 表示「还在跑」的任务状态
IN_FLIGHT_STATUSES = ('queued', 'pending', 'running', 'scanning', 'starting')

DB_FILENAME = 'scan_results.db'


def resolve_db_path():
    """扫描结果库路径：与扫描器共用 XINPECT_DATA_DIR，不给默认值。

    不给默认值是有意的——写死一个 /opt/xinpect-data，一旦换了机器就会
    悄悄去操作一个不存在的库（或者更糟：操作到一个旧的同名库）。
    """
    data_dir = (os.environ.get('XINPECT_DATA_DIR') or '').strip()
    if not data_dir:
        raise RuntimeError(
            'XINPECT_DATA_DIR 未设置：扫描结果库没有默认路径，'
            '请从 /etc/xinpect/website.env 载入（与扫描器同一份数据目录）')
    return os.path.join(data_dir, DB_FILENAME)


def _connect(db_path, readonly=False):
    if readonly:
        uri = 'file:%s?mode=ro' % db_path
        conn = sqlite3.connect(uri, uri=True, timeout=BUSY_TIMEOUT_MS / 1000.0)
    else:
        conn = sqlite3.connect(db_path, timeout=BUSY_TIMEOUT_MS / 1000.0)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn, name):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def in_flight_scan_count(db_path, website_db_path=None):
    """在途任务数：扫描库自己的任务表 + 网站侧 scan_status。

    两边都要看。只看一边就会漏：API 直连扫描不写网站 scans 表，
    而网站里的排队任务在扫描库任务表里可能还没落条目。
    """
    total = 0
    marks = ','.join('?' for _ in IN_FLIGHT_STATUSES)

    if os.path.exists(db_path):
        conn = _connect(db_path, readonly=True)
        try:
            if _table_exists(conn, 'scan_tasks'):
                row = conn.execute(
                    'SELECT count(*) FROM scan_tasks WHERE status IN (%s)' % marks,
                    IN_FLIGHT_STATUSES,
                ).fetchone()
                total += int(row[0] or 0)
        finally:
            conn.close()

    if website_db_path and os.path.exists(website_db_path):
        conn = _connect(website_db_path, readonly=True)
        try:
            if _table_exists(conn, 'scans'):
                # 只认一天内的活动，避免历史脏状态永久挡住清理
                row = conn.execute(
                    'SELECT count(*) FROM scans '
                    "WHERE scan_status IN (%s) "
                    "AND created_at > datetime('now', '-1 day')" % marks,
                    IN_FLIGHT_STATUSES,
                ).fetchone()
                total += int(row[0] or 0)
        finally:
            conn.close()

    return total


def _iso(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M:%S')


def survey(db_path, now=None):
    """清理前先看清要动多少东西——dry-run 和正式清理共用这一份统计。"""
    now = time.time() if now is None else now
    cutoff = now - RETENTION_DAYS * 86400
    conn = _connect(db_path, readonly=True)
    try:
        expired = conn.execute(
            'SELECT count(*) FROM scan_results WHERE created_at < ?', (cutoff,)
        ).fetchone()[0]
        total = conn.execute('SELECT count(*) FROM scan_results').fetchone()[0]
        oldest = conn.execute('SELECT min(created_at) FROM scan_results').fetchone()[0]
        code_rows = 0
        code_bytes = 0
        if _table_exists(conn, 'scan_code_files'):
            row = conn.execute(
                'SELECT count(*), coalesce(sum(length(content)), 0) '
                'FROM scan_code_files WHERE scan_id IN '
                '(SELECT scan_id FROM scan_results WHERE created_at < ?)', (cutoff,)
            ).fetchone()
            code_rows, code_bytes = int(row[0] or 0), int(row[1] or 0)
    finally:
        conn.close()

    size = os.path.getsize(db_path) if os.path.exists(db_path) else 0
    return {
        'db': db_path,
        'size_bytes': size,
        'total_scans': int(total),
        'oldest_at': _iso(oldest) if oldest else None,
        'cutoff_at': _iso(cutoff),
        'expired_scans': int(expired),
        'expired_code_rows': code_rows,
        'expired_code_bytes': code_bytes,
    }


def purge(db_path=None, website_db_path=None, now=None, dry_run=False,
          batch_size=BATCH_SIZE, sleep_seconds=BATCH_SLEEP_SECONDS,
          force=False):
    """删掉超过保留期的记录。返回一份可写进日志的账单。

    返回值里 skipped 非空表示这轮什么都没做，reason 说明原因——
    跳过必须留痕，不能让「清理脚本在跑」被误当成「清理有效」。
    """
    db_path = db_path or resolve_db_path()
    now = time.time() if now is None else now
    cutoff = now - RETENTION_DAYS * 86400

    if not os.path.exists(db_path):
        raise FileNotFoundError('扫描结果库不存在：%s' % db_path)

    report = {
        'db': db_path,
        'retention_days': RETENTION_DAYS,
        'cutoff_at': _iso(cutoff),
        'dry_run': bool(dry_run),
        'skipped': None,
        'reason': None,
        'batches': 0,
        'deleted_scans': 0,
        'deleted_code_rows': 0,
        'size_before': os.path.getsize(db_path),
        'size_after': None,
        'elapsed_seconds': 0.0,
    }

    if not force:
        busy = in_flight_scan_count(db_path, website_db_path)
        if busy:
            report['skipped'] = 'in_flight'
            report['reason'] = '有 %d 个任务在跑，这轮不动' % busy
            return report

    started = time.time()
    conn = _connect(db_path)
    has_code = _table_exists(conn, 'scan_code_files')
    try:
        if dry_run:
            s = survey(db_path, now=now)
            report.update({
                'deleted_scans': s['expired_scans'],
                'deleted_code_rows': s['expired_code_rows'],
                'elapsed_seconds': round(time.time() - started, 2),
            })
            report['size_after'] = report['size_before']
            return report

        while True:
            rows = conn.execute(
                'SELECT scan_id FROM scan_results WHERE created_at < ? LIMIT ?',
                (cutoff, batch_size),
            ).fetchall()
            if not rows:
                break
            ids = [r[0] for r in rows]
            marks = ','.join('?' for _ in ids)
            code_deleted = 0
            if has_code:
                cur = conn.execute(
                    'DELETE FROM scan_code_files WHERE scan_id IN (%s)' % marks, ids)
                code_deleted = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
            conn.execute('DELETE FROM scan_results WHERE scan_id IN (%s)' % marks, ids)
            conn.commit()
            report['batches'] += 1
            report['deleted_scans'] += len(ids)
            report['deleted_code_rows'] += code_deleted
            if sleep_seconds:
                time.sleep(sleep_seconds)

        # 孤儿行：代码副本还在、结果没了。理论上不该有，有就顺手清掉并记账。
        if has_code:
            orphans = conn.execute(
                'SELECT count(*) FROM scan_code_files WHERE scan_id NOT IN '
                '(SELECT scan_id FROM scan_results)'
            ).fetchone()[0]
            if orphans:
                conn.execute(
                    'DELETE FROM scan_code_files WHERE scan_id NOT IN '
                    '(SELECT scan_id FROM scan_results)')
                conn.commit()
                report['deleted_code_rows'] += int(orphans)
                report['orphan_code_rows'] = int(orphans)
    finally:
        conn.close()

    report['size_after'] = os.path.getsize(db_path)
    report['elapsed_seconds'] = round(time.time() - started, 2)
    return report


def compact(db_path=None, website_db_path=None, min_free_ratio=COMPACT_MIN_FREE_RATIO,
            dry_run=False, force=False):
    """删完记录后文件不会自己变小（auto_vacuum=0），空闲页会被新数据复用。

    所以体积会稳定在「历史最高水位」，不会继续涨——这已经解决了「盘被涨满」。
    想真正把文件缩回去，只能 VACUUM，而它要独占锁几分钟：只在空闲、
    且空闲页占比够高时才做，并且默认由人工/夜间窗口触发。
    """
    db_path = db_path or resolve_db_path()
    if not os.path.exists(db_path):
        raise FileNotFoundError('扫描结果库不存在：%s' % db_path)

    info = {'db': db_path, 'size_before': os.path.getsize(db_path),
            'free_ratio': None, 'compacted': False, 'skipped': None,
            'reason': None, 'size_after': None, 'elapsed_seconds': 0.0}

    if not force:
        busy = in_flight_scan_count(db_path, website_db_path)
        if busy:
            info['skipped'] = 'in_flight'
            info['reason'] = '有 %d 个任务在跑，不做 VACUUM' % busy
            return info

    conn = _connect(db_path)
    try:
        page_count = conn.execute('PRAGMA page_count').fetchone()[0]
        free_pages = conn.execute('PRAGMA freelist_count').fetchone()[0]
        ratio = (free_pages / page_count) if page_count else 0.0
        info['free_ratio'] = round(ratio, 4)
        if ratio < min_free_ratio:
            info['skipped'] = 'below_threshold'
            info['reason'] = '空闲页只占 %.1f%%，不值得锁库' % (ratio * 100)
            info['size_after'] = info['size_before']
            return info
        if dry_run:
            info['skipped'] = 'dry_run'
            info['reason'] = '空闲页占 %.1f%%，正式跑会 VACUUM' % (ratio * 100)
            info['size_after'] = info['size_before']
            return info
        started = time.time()
        conn.execute('VACUUM')
        info['compacted'] = True
        info['elapsed_seconds'] = round(time.time() - started, 2)
    finally:
        conn.close()

    info['size_after'] = os.path.getsize(db_path)
    return info


def dangling_code_rows(db_path=None):
    """自检用：返回「代码副本还在、对应结果已不存在」的行数。必须是 0。"""
    db_path = db_path or resolve_db_path()
    conn = _connect(db_path, readonly=True)
    try:
        if not _table_exists(conn, 'scan_code_files'):
            return 0
        return int(conn.execute(
            'SELECT count(*) FROM scan_code_files WHERE scan_id NOT IN '
            '(SELECT scan_id FROM scan_results)').fetchone()[0])
    finally:
        conn.close()
