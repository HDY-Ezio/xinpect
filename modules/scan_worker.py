"""
Xinpect - Async Scan Worker Pool
异步扫描任务管理，使用线程池处理后台扫描任务。
"""

import threading
import time
import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from collections import OrderedDict

from .constants import app, logger, DB_PATH
import sqlite3

# ============================================================
# 配置
# ============================================================
MAX_WORKERS = 3          # 最大并发扫描数
MAX_QUEUE_SIZE = 20      # 最大排队任务数
JOB_TIMEOUT = 900        # 单任务超时15分钟
POLL_INTERVAL = 3        # 前端轮询间隔（秒）


# ============================================================
# 扫描任务管理器
# ============================================================
class ScanJobManager:
    """管理异步扫描任务的生命周期"""

    def __init__(self, max_workers=MAX_WORKERS, max_queue=MAX_QUEUE_SIZE):
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix='scan_worker'
        )
        self._max_queue = max_queue
        self._lock = threading.Lock()
        # scan_id -> job meta (轻量内存缓存，DB为权威源)
        self._jobs = OrderedDict()
        logger.info("ScanJobManager initialized: workers=%d, queue=%d", max_workers, max_queue)

    def can_accept(self):
        """检查是否可以接受新任务"""
        with self._lock:
            pending = sum(1 for j in self._jobs.values() if j['status'] in ('pending', 'running'))
            return pending < self._max_queue + MAX_WORKERS

    def active_count(self):
        """当前运行中+排队中的任务数"""
        with self._lock:
            return sum(1 for j in self._jobs.values() if j['status'] in ('pending', 'running'))

    def submit(self, scan_id, task_fn, task_args=None):
        """
        提交扫描任务到后台执行。
        task_fn: 实际执行扫描的函数
        task_args: 传给 task_fn 的参数 dict
        返回 True 如果成功提交，False 如果队列已满。
        """
        if not self.can_accept():
            return False

        with self._lock:
            self._jobs[scan_id] = {
                'scan_id': scan_id,
                'status': 'pending',
                'submitted_at': time.time(),
                'started_at': None,
                'finished_at': None,
                'error': None,
                'progress': 0,
                'progress_text': '',
            }

        self._update_db_status(scan_id, 'pending', progress=0, progress_text='排队等待中')

        future = self._executor.submit(self._run_task, scan_id, task_fn, task_args or {})
        future.add_done_callback(lambda f: self._on_done(scan_id, f))
        logger.info("[ScanWorker] Job submitted: %s (active=%d)", scan_id, self.active_count())
        return True

    def _run_task(self, scan_id, task_fn, task_args):
        """后台线程执行扫描任务"""
        with self._lock:
            if scan_id in self._jobs:
                self._jobs[scan_id]['status'] = 'running'
                self._jobs[scan_id]['started_at'] = time.time()

        self._update_db_status(scan_id, 'running', progress=10, progress_text='正在初始化扫描')

        try:
            # 进度回调函数，传给 task_fn
            def progress_cb(pct, text=''):
                with self._lock:
                    if scan_id in self._jobs:
                        self._jobs[scan_id]['progress'] = pct
                        self._jobs[scan_id]['progress_text'] = text
                self._update_db_status(scan_id, 'running', progress=pct, progress_text=text)

            task_args['progress_callback'] = progress_cb
            result = task_fn(**task_args)

            with self._lock:
                if scan_id in self._jobs:
                    self._jobs[scan_id]['status'] = 'completed'
                    self._jobs[scan_id]['progress'] = 100
                    self._jobs[scan_id]['progress_text'] = '扫描完成'
                    self._jobs[scan_id]['finished_at'] = time.time()

            self._update_db_status(scan_id, 'completed', progress=100, progress_text='扫描完成')
            logger.info("[ScanWorker] Job completed: %s", scan_id)
            return result

        except Exception as e:
            logger.error("[ScanWorker] Job failed: %s, error=%s", scan_id, e, exc_info=True)
            error_msg = str(e)
            # 友好错误提示
            if 'timeout' in error_msg.lower() or '超时' in error_msg:
                error_msg = '扫描引擎处理超时，请稍后重试或减少文件数量'
            elif 'connection' in error_msg.lower() or '连接' in error_msg or '不可达' in error_msg:
                error_msg = '扫描引擎暂时不可用，请稍后重试'
            elif 'memory' in error_msg.lower():
                error_msg = '文件过大导致内存不足，请减少文件数量或单文件大小'
            else:
                error_msg = f'扫描失败：{error_msg[:100]}'

            with self._lock:
                if scan_id in self._jobs:
                    self._jobs[scan_id]['status'] = 'failed'
                    self._jobs[scan_id]['error'] = error_msg
                    self._jobs[scan_id]['finished_at'] = time.time()

            self._update_db_status(scan_id, 'failed', progress=0, progress_text=error_msg)
            return None

    def _on_done(self, scan_id, future):
        """任务完成回调，清理内存"""
        # 延迟清理，保留结果给前端最后一次轮询
        def cleanup():
            time.sleep(300)  # 5分钟后清理
            with self._lock:
                self._jobs.pop(scan_id, None)
        threading.Thread(target=cleanup, daemon=True).start()

    def get_status(self, scan_id):
        """获取任务状态"""
        with self._lock:
            if scan_id in self._jobs:
                return dict(self._jobs[scan_id])

        # 内存中没有，查DB（后台线程不能用 get_db，需要直接 sqlite3）
        try:
            _conn = sqlite3.connect(DB_PATH)
            row = _conn.execute(
                "SELECT scan_status, scan_progress, scan_progress_text, scan_error FROM scans WHERE scan_id = ?",
                (scan_id,)
            ).fetchone()
            _conn.close()
            if row:
                return {
                    'scan_id': scan_id,
                    'status': row[0] or 'unknown',
                    'progress': row[1] or 0,
                    'progress_text': row[2] or '',
                    'error': row[3],
                }
        except Exception:
            pass

        return {'scan_id': scan_id, 'status': 'unknown', 'progress': 0, 'progress_text': '', 'error': None}

    def _update_db_status(self, scan_id, status, progress=0, progress_text='', error=None):
        """更新数据库中的任务状态"""
        try:
            _conn = sqlite3.connect(DB_PATH)
            if error:
                _conn.execute(
                    "UPDATE scans SET scan_status=?, scan_progress=?, scan_progress_text=?, scan_error=? WHERE scan_id=?",
                    (status, progress, progress_text, error, scan_id)
                )
            else:
                _conn.execute(
                    "UPDATE scans SET scan_status=?, scan_progress=?, scan_progress_text=? WHERE scan_id=?",
                    (status, progress, progress_text, scan_id)
                )
            _conn.commit()
            _conn.close()
        except Exception as e:
            logger.warning("[ScanWorker] Failed to update DB status for %s: %s", scan_id, e)


# ============================================================
# 全局实例
# ============================================================
job_manager = ScanJobManager()


def init_scan_tables():
    """给 scans 表添加异步扫描相关字段"""
    import sqlite3
    db = sqlite3.connect(DB_PATH)
    cur = db.cursor()
    cols = {row[1] for row in cur.execute("PRAGMA table_info(scans)").fetchall()}

    new_cols = [
        ("scan_status", "TEXT DEFAULT NULL"),
        ("scan_progress", "INTEGER DEFAULT 0"),
        ("scan_progress_text", "TEXT DEFAULT NULL"),
        ("scan_error", "TEXT DEFAULT NULL"),
    ]
    for col_name, col_type in new_cols:
        if col_name not in cols:
            cur.execute("ALTER TABLE scans ADD COLUMN %s %s" % (col_name, col_type))
            logger.info("DB migration: added scans.%s %s", col_name, col_type)
    db.commit()
    db.close()
    logger.info("Scan async tables initialized.")
