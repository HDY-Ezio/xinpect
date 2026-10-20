# -*- coding: utf-8 -*-
"""
煋鉴排队系统 - 核心队列管理器（v2）
基于 Redis Sorted Set 实现优先级队列
VIP用户自动插队，支持并发控制和CPU限流
"""

import time
import json
import logging
import os
import subprocess
import threading
from typing import Optional, Dict, List, Tuple

logger = logging.getLogger("xinpect-queue")

# ── 配置 ─────────────────────────────────────────────
REDIS_HOST = os.environ.get("QUEUE_REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.environ.get("QUEUE_REDIS_PORT", "6379"))
REDIS_DB = int(os.environ.get("QUEUE_REDIS_DB", "1"))
REDIS_PASSWORD = os.environ.get("QUEUE_REDIS_PASSWORD", "")

MAX_CONCURRENT_SCANS = int(os.environ.get("QUEUE_MAX_CONCURRENT", "5"))
CPU_THRESHOLD_PERCENT = int(os.environ.get("QUEUE_CPU_THRESHOLD", "80"))
QUEUE_SCAN_TIMEOUT = int(os.environ.get("QUEUE_SCAN_TIMEOUT", "600"))  # 10分钟

# Redis Key 前缀
KEY_QUEUE = "xinpect:queue"           # Sorted Set: score=优先级, member=task_id
KEY_TASK = "xinpect:task:{}"          # Hash: 任务详情
KEY_RUNNING = "xinpect:running"       # Set: 正在运行的 task_id
KEY_STATS = "xinpect:queue:stats"     # Hash: 统计数据
KEY_CPU_LOCK = "xinpect:queue:cpu_locked"  # String: CPU限流锁

# 优先级定义（score越小越优先）
PRIORITY_VIP = 100
PRIORITY_NORMAL = 1000
PRIORITY_LOW = 5000


class QueueManager:
    """煋鉴扫描排队队列管理器"""

    def __init__(self):
        self._redis = None
        self._lock = threading.Lock()

    @property
    def redis(self):
        if self._redis is None:
            import redis
            self._redis = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                password=REDIS_PASSWORD or None,
                decode_responses=True,
                socket_connect_timeout=5,
                retry_on_timeout=True,
            )
        return self._redis

    def ping(self) -> bool:
        """检查 Redis 连接"""
        try:
            return self.redis.ping()
        except Exception as e:
            logger.error(f"Redis连接失败: {e}")
            return False

    # ── 提交任务 ────────────────────────────────────────

    def submit_task(
        self,
        task_id: str,
        user_id: int,
        email: str,
        project_name: str,
        scan_mode: str = "smart",
        is_vip: bool = False,
        file_count: int = 0,
        extra: Optional[dict] = None,
    ) -> Dict:
        """
        提交扫描任务到队列
        返回: {position, estimated_wait, task_id, status}
        """
        # CPU限流检查
        if self._is_cpu_locked():
            return {
                "success": False,
                "error": "系统负载过高，请稍后再试",
                "retry_after": 60,
            }

        # 检查是否已有排队中的任务
        existing = self._get_task(task_id)
        if existing and existing.get("status") in ("queued", "running"):
            return {
                "success": False,
                "error": "该任务已在队列中或正在执行",
                "task_id": task_id,
            }

        # 计算优先级（VIP插队）
        priority = PRIORITY_VIP if is_vip else PRIORITY_NORMAL
        # 同优先级内按时间排序（加上小数时间戳）
        score = priority + (time.time() % 1)

        # 存入队列
        pipe = self.redis.pipeline()
        pipe.zadd(KEY_QUEUE, {task_id: score})

        # 任务详情
        task_data = {
            "task_id": task_id,
            "user_id": str(user_id),
            "email": email,
            "project_name": project_name,
            "scan_mode": scan_mode,
            "is_vip": "1" if is_vip else "0",
            "file_count": str(file_count),
            "status": "queued",
            "submitted_at": str(time.time()),
            "started_at": "",
            "finished_at": "",
            "position": "0",
            "error": "",
        }

        # 存储额外数据（文件内容等）
        if extra:
            for key, value in extra.items():
                task_data[key] = value

        pipe.hset(KEY_TASK.format(task_id), mapping=task_data)
        # 24h过期（有文件数据时可能较大）
        pipe.expire(KEY_TASK.format(task_id), 86400)
        pipe.execute()

        # 获取排队位置
        position = self.get_position(task_id)
        estimated_wait = self._estimate_wait(position)

        # 更新统计
        self._incr_stat("total_submitted")

        logger.info(f"任务入队: {task_id} user={user_id} vip={is_vip} pos={position} files={file_count}")

        return {
            "success": True,
            "task_id": task_id,
            "status": "queued",
            "position": position,
            "estimated_wait": estimated_wait,
            "is_vip": is_vip,
        }

    # ── 查询状态 ────────────────────────────────────────

    def get_status(self, task_id: str) -> Optional[Dict]:
        """获取任务状态"""
        task = self._get_task(task_id)
        if not task:
            return None

        result = {
            "task_id": task.get("task_id", task_id),
            "status": task.get("status", "unknown"),
            "project_name": task.get("project_name", ""),
            "scan_mode": task.get("scan_mode", "smart"),
            "is_vip": task.get("is_vip") == "1",
            "submitted_at": float(task.get("submitted_at", 0)),
            "started_at": float(task.get("started_at", 0)) if task.get("started_at") else None,
            "finished_at": float(task.get("finished_at", 0)) if task.get("finished_at") else None,
            "error": task.get("error", ""),
        }

        if result["status"] == "queued":
            result["position"] = self.get_position(task_id)
            result["estimated_wait"] = self._estimate_wait(result["position"])

        return result

    def get_position(self, task_id: str) -> int:
        """获取排队位置（从1开始）"""
        rank = self.redis.zrank(KEY_QUEUE, task_id)
        return rank + 1 if rank is not None else 0

    def get_queue_overview(self) -> Dict:
        """队列全局概览"""
        total_queued = self.redis.zcard(KEY_QUEUE)
        total_running = self.redis.scard(KEY_RUNNING)

        # VIP数量
        vip_count = 0
        for member in self.redis.zrangebyscore(KEY_QUEUE, PRIORITY_VIP, PRIORITY_VIP + 1):
            vip_count += 1

        # 平均等待时间（基于最近完成的10个任务）
        avg_wait = self._calc_avg_wait()

        return {
            "queued": total_queued,
            "running": total_running,
            "vip_queued": vip_count,
            "max_concurrent": MAX_CONCURRENT_SCANS,
            "available_slots": max(0, MAX_CONCURRENT_SCANS - total_running),
            "avg_wait_seconds": avg_wait,
            "cpu_locked": self._is_cpu_locked(),
        }

    # ── 取消任务 ────────────────────────────────────────

    def cancel_task(self, task_id: str, user_id: int) -> Dict:
        """取消排队中的任务"""
        task = self._get_task(task_id)
        if not task:
            return {"success": False, "error": "任务不存在"}

        if str(task.get("user_id")) != str(user_id):
            return {"success": False, "error": "无权操作此任务"}

        status = task.get("status")
        if status == "running":
            return {"success": False, "error": "任务正在执行中，无法取消"}
        if status in ("completed", "cancelled", "failed"):
            return {"success": False, "error": f"任务已{status}，无法取消"}

        # 从队列移除
        self.redis.zrem(KEY_QUEUE, task_id)
        self.redis.hset(KEY_TASK.format(task_id), "status", "cancelled")

        logger.info(f"任务取消: {task_id} user={user_id}")
        return {"success": True, "task_id": task_id, "status": "cancelled"}

    # ── Worker 操作（取出/完成） ────────────────────────

    def dequeue_next(self) -> Optional[Dict]:
        """
        取出下一个待执行任务（由Worker调用）
        自动跳过CPU限流期间的任务
        """
        if self._is_cpu_locked():
            return None

        running_count = self.redis.scard(KEY_RUNNING)
        if running_count >= MAX_CONCURRENT_SCANS:
            return None

        # 取优先级最高的（score最小）
        results = self.redis.zrange(KEY_QUEUE, 0, 0, withscores=True)
        if not results:
            return None

        task_id, score = results[0]
        self.redis.zrem(KEY_QUEUE, task_id)
        self.redis.sadd(KEY_RUNNING, task_id)

        now = time.time()
        self.redis.hset(KEY_TASK.format(task_id), mapping={
            "status": "running",
            "started_at": str(now),
        })

        # 记录等待时间
        task = self._get_task(task_id)
        if task and task.get("submitted_at"):
            wait_time = now - float(task["submitted_at"])
            self._record_wait_time(wait_time)

        logger.info(f"任务出队执行: {task_id}")
        return self._get_task(task_id)

    def complete_task(self, task_id: str, success: bool = True, error: str = "") -> None:
        """标记任务完成"""
        status = "completed" if success else "failed"
        now = time.time()

        pipe = self.redis.pipeline()
        pipe.hset(KEY_TASK.format(task_id), mapping={
            "status": status,
            "finished_at": str(now),
            "error": error,
        })
        pipe.srem(KEY_RUNNING, task_id)
        pipe.execute()

        self._incr_stat(f"total_{status}")
        logger.info(f"任务完成: {task_id} status={status}")

    # ── VIP插队 ─────────────────────────────────────────

    def upgrade_to_vip(self, task_id: str, user_id: int) -> Dict:
        """将普通任务提升为VIP优先"""
        task = self._get_task(task_id)
        if not task:
            return {"success": False, "error": "任务不存在"}
        if str(task.get("user_id")) != str(user_id):
            return {"success": False, "error": "无权操作"}
        if task.get("status") != "queued":
            return {"success": False, "error": "只有排队中的任务可以升级"}

        score = PRIORITY_VIP + (time.time() % 1)
        self.redis.zadd(KEY_QUEUE, {task_id: score})
        self.redis.hset(KEY_TASK.format(task_id), "is_vip", "1")

        position = self.get_position(task_id)
        logger.info(f"任务VIP升级: {task_id} new_pos={position}")
        return {"success": True, "position": position}

    # ── CPU限流 ─────────────────────────────────────────

    def _is_cpu_locked(self) -> bool:
        """检查CPU使用率是否超过阈值"""
        # 先检查缓存锁（30秒有效）
        if self.redis.exists(KEY_CPU_LOCK):
            return True

        try:
            # 读取系统CPU使用率
            cpu_percent = self._get_cpu_percent()
            if cpu_percent >= CPU_THRESHOLD_PERCENT:
                self.redis.setex(KEY_CPU_LOCK, 30, "1")  # 锁定30秒
                logger.warning(f"CPU限流触发: {cpu_percent}% >= {CPU_THRESHOLD_PERCENT}%")
                return True
        except Exception as e:
            logger.warning(f"CPU检测失败: {e}")

        return False

    def _get_cpu_percent(self) -> float:
        """获取系统CPU使用率"""
        try:
            result = subprocess.run(
                ["top", "-bn1"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.split("\n"):
                if "Cpu(s)" in line or "%Cpu" in line:
                    # 解析 idle 百分比
                    parts = line.split()
                    for i, p in enumerate(parts):
                        if "id" in p.lower() or "idle" in p.lower():
                            idle = float(parts[i - 1].replace(",", "").replace("%", ""))
                            return 100.0 - idle
        except Exception:
            pass
        return 0.0

    # ── 内部工具函数 ─────────────────────────────────────

    def _get_task(self, task_id: str) -> Optional[Dict]:
        """获取任务详情"""
        data = self.redis.hgetall(KEY_TASK.format(task_id))
        return data if data else None

    def _estimate_wait(self, position: int) -> int:
        """估算等待时间（秒）"""
        if position <= 0:
            return 0
        avg_scan_time = self._get_avg_scan_time()
        running = self.redis.scard(KEY_RUNNING)
        effective_concurrent = max(1, MAX_CONCURRENT_SCANS - running)
        return int((position / effective_concurrent) * avg_scan_time)

    def _get_avg_scan_time(self) -> float:
        """获取平均扫描耗时（秒）"""
        val = self.redis.hget(KEY_STATS, "avg_scan_time")
        return float(val) if val else 120.0  # 默认2分钟

    def _calc_avg_wait(self) -> int:
        """计算平均等待时间"""
        val = self.redis.hget(KEY_STATS, "avg_wait_time")
        return int(float(val)) if val else 0

    def _record_wait_time(self, wait_seconds: float):
        """记录等待时间（滑动平均）"""
        prev = self.redis.hget(KEY_STATS, "avg_wait_time")
        count = self.redis.hget(KEY_STATS, "wait_count")
        if prev and count:
            n = int(count) + 1
            avg = (float(prev) * int(count) + wait_seconds) / n
        else:
            n = 1
            avg = wait_seconds
        self.redis.hset(KEY_STATS, mapping={
            "avg_wait_time": str(avg),
            "wait_count": str(n),
        })

    def _incr_stat(self, key: str):
        """递增统计计数"""
        self.redis.hincrby(KEY_STATS, key, 1)

    def get_queue_list(self, limit: int = 50) -> List[Dict]:
        """获取当前排队列表"""
        items = self.redis.zrange(KEY_QUEUE, 0, limit - 1, withscores=True)
        result = []
        for task_id, score in items:
            task = self._get_task(task_id)
            if task:
                task_copy = {k: v for k, v in task.items() if k not in ("files_data",)}
                task_copy["position"] = self.get_position(task_id)
                result.append(task_copy)
        return result


# 全局单例
queue_manager = QueueManager()
