# -*- coding: utf-8 -*-
"""
煋鉴排队系统 - 后台Worker（v2 - 对接真实扫描引擎）
持续从队列中取出任务并执行扫描，完成后保存结果到数据库并发送通知
"""

import time
import logging
import threading
import signal
import sys
import os
import json
import sqlite3

logger = logging.getLogger("xinpect")

# 项目根目录（用于导入modules）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

_shutdown = False

def _handle_signal(signum, frame):
    global _shutdown
    logger.info(f"收到信号 {signum}，准备退出...")
    _shutdown = True

signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


def _get_db():
    """获取数据库连接"""
    from modules.constants import DB_PATH
    return sqlite3.connect(DB_PATH)


def _execute_scan(task: dict) -> dict:
    """执行真实扫描任务"""
    from queue_manager import queue_manager

    task_id = task.get("task_id", "")
    project_name = task.get("project_name", "")
    scan_mode = task.get("scan_mode", "smart")
    email = task.get("email", "")
    user_id = int(task.get("user_id", "0"))

    logger.info(f"开始扫描: {task_id} project={project_name} mode={scan_mode} user={user_id}")

    try:
        # 1. 从任务数据中获取文件
        files_json = task.get("files_data", "{}")
        try:
            files_dict = json.loads(files_json) if isinstance(files_json, str) else files_json
        except json.JSONDecodeError:
            files_dict = {}

        if not files_dict:
            raise ValueError("扫描任务缺少文件数据")

        # 2. 确定扫描参数（使用用户选择的scan_mode）
        is_vip = task.get("is_vip", "0") == "1"
        language = task.get("language", "auto")

        # 四档模式路由：free/quick/smart/deep
        # scan_mode已在任务入队时从前端传入，这里直接使用
        actual_scan_mode = scan_mode  # 保留用户选择
        if scan_mode == "free":
            from modules.constants import FREE_BRAIN_IDS
            brain_ids = FREE_BRAIN_IDS
        elif scan_mode == "quick":
            from modules.constants import ALL_BRAIN_IDS
            brain_ids = ALL_BRAIN_IDS
        elif scan_mode in ("smart", "deep"):
            from modules.constants import ALL_BRAIN_IDS
            brain_ids = ALL_BRAIN_IDS
            is_vip = True  # smart/deep需要AI，强制vip
        else:
            # 兼容旧模式(full/basic)
            from modules.constants import ALL_BRAIN_IDS
            brain_ids = ALL_BRAIN_IDS

        # 3. 调用真实扫描引擎
        from modules.scanner import call_scanner

        results = call_scanner(
            files_dict, brain_ids,
            options={
                'language': language,
                'scan_mode': actual_scan_mode,
                'is_vip': is_vip,
            }
        )

        issue_count = results.get('total_issues', 0)
        score = 0
        grade = ''

        # 4. 计算评分
        try:
            from modules.scoring import calculate_score, calculate_tier_scores, calculate_overall_grade

            avail_brains = None if is_vip else None
            from modules.constants import FREE_BRAIN_IDS
            avail_brains = FREE_BRAIN_IDS if not is_vip else None

            score = calculate_score(results.get("issues", []), available_brain_ids=avail_brains)
            tier_scores = calculate_tier_scores(results.get("issues", []), available_brain_ids=avail_brains, is_vip=is_vip)
            grade = calculate_overall_grade(tier_scores)
        except Exception as e:
            logger.warning(f"评分计算失败: {e}")

        # 5. 保存结果到数据库
        try:
            db = _get_db()
            # 检查是否已有此task_id的scan记录
            existing = db.execute("SELECT id FROM scans WHERE scan_id = ?", (task_id,)).fetchone()
            if existing:
                db.execute("""
                    UPDATE scans SET results=?, score=?, grade=?, issue_count=?,
                    scan_status='completed', scan_progress=100, scan_progress_text='扫描完成'
                    WHERE scan_id=?
                """, (json.dumps(results, ensure_ascii=False), score, grade, issue_count, task_id))
            else:
                # 创建新记录
                file_count = len(files_dict)
                total_lines = sum(len(v.split('\n')) for v in files_dict.values() if isinstance(v, str))
                db.execute("""
                    INSERT INTO scans (scan_id, user_id, title, file_count, files_meta, results,
                    score, grade, issue_count, language, credits_spent, total_lines, scan_mode,
                    source, scan_status, scan_progress, scan_progress_text)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (task_id, user_id, project_name, file_count,
                      json.dumps(list(files_dict.keys()), ensure_ascii=False),
                      json.dumps(results, ensure_ascii=False),
                      score, grade, issue_count, language,
                      0, total_lines, actual_scan_mode, 'queue',
                      'completed', 100, '扫描完成'))
            db.commit()
            db.close()
            logger.info(f"扫描结果已保存: {task_id} score={score} grade={grade} issues={issue_count}")
        except Exception as e:
            logger.error(f"保存扫描结果到数据库失败: {e}")

        # 6. 标记队列任务完成
        queue_manager.complete_task(task_id, success=True)

        # 7. 发送完成邮件
        try:
            from queue_emails import send_scan_complete_email
            send_scan_complete_email(email, project_name, task_id, True, issue_count)
        except Exception as e:
            logger.warning(f"完成邮件发送失败: {e}")

        logger.info(f"扫描完成: {task_id} issues={issue_count} score={score} grade={grade}")
        return results

    except Exception as e:
        logger.error(f"扫描失败: {task_id} error={e}", exc_info=True)
        queue_manager.complete_task(task_id, success=False, error=str(e))

        try:
            from queue_emails import send_scan_complete_email
            send_scan_complete_email(email, project_name, task_id, False)
        except Exception:
            pass

        # 更新DB状态为失败
        try:
            db = _get_db()
            existing = db.execute("SELECT id FROM scans WHERE scan_id = ?", (task_id,)).fetchone()
            if existing:
                db.execute("UPDATE scans SET scan_status='failed', scan_error=? WHERE scan_id=?",
                          (str(e)[:200], task_id))
            else:
                db.execute("""
                    INSERT INTO scans (scan_id, user_id, title, scan_status, scan_error, source)
                    VALUES (?, ?, ?, 'failed', ?, 'queue')
                """, (task_id, user_id, project_name, str(e)[:200]))
            db.commit()
            db.close()
        except Exception as db_e:
            logger.error(f"更新失败状态到DB失败: {db_e}")

        return {}


def _check_almost_ready():
    """检查即将开始的任务（前面只剩1-2人时发通知）"""
    from queue_manager import queue_manager, KEY_QUEUE

    try:
        items = queue_manager.redis.zrange(KEY_QUEUE, 0, 2)
        for i, task_id in enumerate(items):
            if i >= 2:
                break
            task = queue_manager._get_task(task_id)
            if not task:
                continue
            alerted = queue_manager.redis.get(f"xinpect:alerted:{task_id}")
            if alerted:
                continue

            email = task.get("email", "")
            project_name = task.get("project_name", "")
            remaining = i

            try:
                from queue_emails import send_queue_almost_email
                send_queue_almost_email(email, project_name, remaining)
                queue_manager.redis.setex(f"xinpect:alerted:{task_id}", 300, "1")
            except Exception as e:
                logger.warning(f"即将开始邮件发送失败: {e}")

    except Exception as e:
        logger.warning(f"检查即将开始任务失败: {e}")


def worker_loop(interval: float = 2.0):
    """Worker主循环"""
    from queue_manager import queue_manager

    logger.info("煋鉴排队Worker v2 启动（真实扫描引擎）")

    if not queue_manager.ping():
        logger.error("Redis连接失败，Worker退出")
        return

    cycle = 0
    while not _shutdown:
        try:
            task = queue_manager.dequeue_next()
            if task:
                t = threading.Thread(
                    target=_execute_scan,
                    args=(task,),
                    daemon=True,
                    name=f"scan-{task.get('task_id', 'unknown')[:20]}"
                )
                t.start()
            else:
                cycle += 1
                if cycle % 15 == 0:
                    _check_almost_ready()
                    cycle = 0

        except Exception as e:
            logger.error(f"Worker循环异常: {e}")

        time.sleep(interval)

    logger.info("煋鉴排队Worker已停止")


def start_worker_thread(interval: float = 2.0):
    """以守护线程方式启动Worker"""
    t = threading.Thread(
        target=worker_loop,
        args=(interval,),
        daemon=True,
        name="queue-worker"
    )
    t.start()
    logger.info("排队Worker守护线程已启动（v2-真实扫描）")
    return t


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    worker_loop(interval=2.0)
