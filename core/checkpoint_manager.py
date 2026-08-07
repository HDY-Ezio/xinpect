# -*- coding: utf-8 -*-
"""
检查点与故障恢复管理器 (Checkpoint Manager)
章鱼架构 v2.0 - 模块4

核心能力：
1. 每个大脑执行完毕后自动保存快照（输入+输出+时间戳+成本）
2. 支持从最近检查点恢复
3. 存储后端：本地文件（JSON），可扩展到 Redis/SQLite
4. 断点续审：大任务中断后从最后完成的大脑继续

Usage:
    from core.checkpoint_manager import CheckpointManager

    manager = CheckpointManager(task_id="review_20260802_001")

    # 保存检查点
    manager.save_checkpoint("1", input_data={"path": "/project"}, result=brain_result)

    # 恢复检查点
    last_state = manager.restore("review_20260802_001")

    # 获取待执行的大脑
    remaining = manager.get_remaining_brains(["1", "2", "3", "4", "5"])
"""

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime


# =============================================================================
# 数据结构
# =============================================================================

@dataclass
class Checkpoint:
    """
    单个大脑执行的检查点快照。

    记录：哪个大脑、什么输入、什么输出、耗时多少、花了多少。
    """

    brain_id: str                          # 大脑ID
    status: str = "completed"              # completed / failed / timeout
    input_hash: str = ""                   # 输入数据的摘要/哈希
    input_summary: Dict[str, Any] = field(default_factory=dict)  # 输入摘要
    output_summary: Dict[str, Any] = field(default_factory=dict) # 输出摘要（BrainResult.to_dict()）
    started_at: str = ""                   # 开始时间（ISO 格式）
    completed_at: str = ""                 # 完成时间（ISO 格式）
    elapsed_seconds: float = 0.0           # 耗时（秒）
    cost_estimate: float = 0.0             # 成本估算（元）
    error_message: str = ""                # 错误信息（如果失败）

    def to_dict(self) -> Dict[str, Any]:
        return {
            "brain_id": self.brain_id,
            "status": self.status,
            "input_hash": self.input_hash,
            "input_summary": self.input_summary,
            "output_summary": self.output_summary,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "cost_estimate": round(self.cost_estimate, 6),
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Checkpoint":
        return cls(
            brain_id=data.get("brain_id", ""),
            status=data.get("status", "completed"),
            input_hash=data.get("input_hash", ""),
            input_summary=data.get("input_summary", {}),
            output_summary=data.get("output_summary", {}),
            started_at=data.get("started_at", ""),
            completed_at=data.get("completed_at", ""),
            elapsed_seconds=data.get("elapsed_seconds", 0.0),
            cost_estimate=data.get("cost_estimate", 0.0),
            error_message=data.get("error_message", ""),
        )


@dataclass
class TaskSnapshot:
    """
    任务级快照：包含所有已完成大脑的检查点。
    """

    task_id: str
    project_path: str = ""
    config_hash: str = ""                  # 配置哈希（检测配置是否变化）
    created_at: str = ""                   # 任务创建时间
    updated_at: str = ""                   # 最后更新时间
    checkpoints: Dict[str, Checkpoint] = field(default_factory=dict)  # {brain_id: Checkpoint}
    status: str = "in_progress"            # in_progress / completed / failed / restored

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "project_path": self.project_path,
            "config_hash": self.config_hash,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "checkpoints": {
                bid: cp.to_dict() for bid, cp in self.checkpoints.items()
            },
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskSnapshot":
        snapshot = cls(
            task_id=data.get("task_id", ""),
            project_path=data.get("project_path", ""),
            config_hash=data.get("config_hash", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            status=data.get("status", "in_progress"),
        )
        for bid, cp_data in data.get("checkpoints", {}).items():
            snapshot.checkpoints[bid] = Checkpoint.from_dict(cp_data)
        return snapshot


# =============================================================================
# 成本估算
# =============================================================================

# 每个大脑的近似单次调用成本（元）
BRAIN_COST_ESTIMATES: Dict[str, float] = {
    "1": 0.0,           # 规则引擎：零 Token
    "2": 0.02,          # AI 引擎：LLM 调用
    "3": 0.0,           # 性能分析：纯规则
    "4": 0.0,           # 依赖审计：纯规则
    "5": 0.0,           # UI 审查：纯规则
}


def estimate_brain_cost(brain_id: str) -> float:
    """估算大脑单次调用成本"""
    return BRAIN_COST_ESTIMATES.get(str(brain_id), 0.0)


# =============================================================================
# 存储后端
# =============================================================================

class StorageBackend:
    """存储后端抽象基类"""

    def save(self, task_id: str, snapshot: TaskSnapshot) -> None:
        raise NotImplementedError

    def load(self, task_id: str) -> Optional[TaskSnapshot]:
        raise NotImplementedError

    def list_tasks(self) -> List[str]:
        raise NotImplementedError

    def delete(self, task_id: str) -> None:
        raise NotImplementedError


class FileStorageBackend(StorageBackend):
    """
    本地文件存储后端。

    存储路径：{storage_dir}/{task_id}.json

    [v2.0优化] 原子写入：先写临时文件再 os.rename，防止写入中断导致文件损坏。
    """

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        os.makedirs(storage_dir, exist_ok=True)

    def _task_path(self, task_id: str) -> str:
        # 清理 task_id 中的非法字符
        safe_id = "".join(c if c.isalnum() or c in "-_." else "_" for c in task_id)
        return os.path.join(self.storage_dir, f"{safe_id}.json")

    def save(self, task_id: str, snapshot: TaskSnapshot) -> None:
        """
        原子写入检查点文件。

        [v2.0优化] 先写入临时文件 (.tmp)，再 os.rename 原子替换，
        防止写入过程中断导致数据文件损坏。
        """
        path = self._task_path(task_id)
        tmp_path = path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(snapshot.to_dict(), f, ensure_ascii=False, indent=2)
            # 原子替换（POSIX 上 os.rename 是原子操作）
            os.replace(tmp_path, path)
        except Exception as e:  # noqa: broad exception handling
            # 写入失败时尝试清理临时文件
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:  # noqa: intentional empty handler
                pass
            raise

    def load(self, task_id: str) -> Optional[TaskSnapshot]:
        path = self._task_path(task_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return TaskSnapshot.from_dict(data)
        except (json.JSONDecodeError, IOError):
            return None

    def list_tasks(self) -> List[str]:
        if not os.path.exists(self.storage_dir):
            return []
        tasks = []
        for fname in os.listdir(self.storage_dir):
            if fname.endswith(".json"):
                tasks.append(fname[:-5])
        return sorted(tasks)

    def delete(self, task_id: str) -> None:
        path = self._task_path(task_id)
        if os.path.exists(path):
            os.remove(path)


# =============================================================================
# 检查点管理器
# =============================================================================

class CheckpointManager:
    """
    执行检查点管理器。

    每个触手执行完毕后自动保存快照，故障后从最近的检查点恢复，不重头来。

    支持：
    - 保存检查点（每个大脑执行完毕后）
    - 恢复检查点（从上次中断的地方继续）
    - 查询剩余待执行的大脑
    - 任务总览（查看各大脑执行状态）
    """

    def __init__(
        self,
        task_id: str,
        storage_dir: Optional[str] = None,
        backend: Optional[StorageBackend] = None,
    ):
        """
        Args:
            task_id: 任务唯一标识
            storage_dir: 检查点存储目录（默认使用 .qa_history/checkpoints/）
            backend: 自定义存储后端（默认使用 FileStorageBackend）
        """
        self.task_id = task_id

        if backend is not None:
            self._backend = backend
        else:
            if storage_dir is None:
                # 默认存储目录
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                storage_dir = os.path.join(base_dir, ".qa_history", "checkpoints")
            self._backend = FileStorageBackend(storage_dir)

        # 加载或创建快照
        self._snapshot = self._backend.load(task_id)
        if self._snapshot is None:
            self._snapshot = TaskSnapshot(
                task_id=task_id,
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
                status="in_progress",
            )

    def save_checkpoint(
        self,
        brain_id: str,
        input_data: Optional[Dict[str, Any]] = None,
        result: Any = None,
        elapsed: float = 0.0,
        error: str = "",
        config: Optional[dict] = None,
    ) -> Checkpoint:
        """
        保存大脑执行检查点。

        Args:
            brain_id: 大脑ID
            input_data: 输入数据摘要（可选）
            result: BrainResult 对象或 dict
            elapsed: 执行耗时（秒）
            error: 错误信息（如果有）
            config: 配置字典（用于成本估算等）

        Returns:
            保存的 Checkpoint 对象
        """
        # 构建输入摘要
        input_summary = {}
        input_hash = ""
        if input_data:
            input_summary = {
                "path": input_data.get("path", ""),
                "file_count": input_data.get("file_count", 0),
                "mode": input_data.get("mode", ""),
            }
            # 简单哈希
            key_str = f"{input_data.get('path', '')}:{input_data.get('mode', '')}"
            input_hash = str(hash(key_str))[:12]

        # 构建输出摘要
        output_summary = {}
        if result is not None:
            if hasattr(result, "to_dict"):
                output_summary = result.to_dict()
            elif isinstance(result, dict):
                output_summary = result

        # 构建检查点
        now = datetime.now().isoformat()
        checkpoint = Checkpoint(
            brain_id=str(brain_id),
            status="failed" if error else "completed",
            input_hash=input_hash,
            input_summary=input_summary,
            output_summary=output_summary,
            started_at=now,  # 简化：不单独记录开始时间
            completed_at=now,
            elapsed_seconds=elapsed,
            cost_estimate=estimate_brain_cost(brain_id),
            error_message=error,
        )

        # 更新快照
        self._snapshot.checkpoints[str(brain_id)] = checkpoint
        self._snapshot.updated_at = now

        # 如果所有大脑都完成了，标记任务完成
        if all(
            cp.status == "completed"
            for cp in self._snapshot.checkpoints.values()
        ):
            self._snapshot.status = "completed"

        # 持久化
        self._backend.save(self.task_id, self._snapshot)

        return checkpoint

    def restore(self, task_id: Optional[str] = None) -> Optional[TaskSnapshot]:
        """
        恢复到最近的检查点。

        Args:
            task_id: 任务ID（默认使用当前 task_id）

        Returns:
            TaskSnapshot 或 None（如果无检查点）
        """
        tid = task_id or self.task_id
        return self._backend.load(tid)

    def get_remaining_brains(self, all_brain_ids: List[str]) -> List[str]:
        """
        获取尚未执行的大脑ID列表。

        Args:
            all_brain_ids: 所有需要执行的大脑ID列表

        Returns:
            尚未完成的大脑ID列表
        """
        completed = set(
            bid for bid, cp in self._snapshot.checkpoints.items()
            if cp.status == "completed"
        )
        return [bid for bid in all_brain_ids if bid not in completed]

    def get_checkpoint(self, brain_id: str) -> Optional[Checkpoint]:
        """获取指定大脑的检查点"""
        return self._snapshot.checkpoints.get(str(brain_id))

    def get_task_summary(self) -> Dict[str, Any]:
        """获取任务总览"""
        checkpoints = self._snapshot.checkpoints
        total = len(checkpoints)
        completed = sum(1 for cp in checkpoints.values() if cp.status == "completed")
        failed = sum(1 for cp in checkpoints.values() if cp.status == "failed")
        total_cost = sum(cp.cost_estimate for cp in checkpoints.values())
        total_time = sum(cp.elapsed_seconds for cp in checkpoints.values())

        return {
            "task_id": self.task_id,
            "status": self._snapshot.status,
            "total_brains": total,
            "completed": completed,
            "failed": failed,
            "remaining": total - completed - failed,
            "total_cost_estimate": round(total_cost, 6),
            "total_elapsed": round(total_time, 3),
            "created_at": self._snapshot.created_at,
            "updated_at": self._snapshot.updated_at,
            "brain_details": {
                bid: {
                    "status": cp.status,
                    "elapsed": round(cp.elapsed_seconds, 3),
                    "cost": round(cp.cost_estimate, 6),
                    "error": cp.error_message or None,
                }
                for bid, cp in checkpoints.items()
            },
        }

    def replay(
        self,
        brain_id: str,
        brain_factory: Any = None,
        scan_fn: Any = None,
        project_path: str = "",
        config: Optional[dict] = None,
    ) -> Optional[Checkpoint]:
        """
        从指定检查点重新执行某个大脑。

        Args:
            brain_id: 要重放的大脑ID
            brain_factory: 大脑工厂函数
            scan_fn: 扫描执行函数
            project_path: 项目路径
            config: 配置

        Returns:
            新的 Checkpoint（如果重新执行了）或 None
        """
        if brain_factory is None or scan_fn is None:
            return None

        brain = brain_factory(brain_id)
        if brain is None:
            return None

        config = config or {}
        start = time.time()
        try:
            result = scan_fn(brain, project_path, config)
            elapsed = time.time() - start
            return self.save_checkpoint(
                brain_id=brain_id,
                input_data={"path": project_path},
                result=result,
                elapsed=elapsed,
            )
        except Exception as e:  # noqa: intentional catch-all
            elapsed = time.time() - start
            return self.save_checkpoint(
                brain_id=brain_id,
                input_data={"path": project_path},
                elapsed=elapsed,
                error=str(e),
            )

    def cleanup(self, max_age_hours: int = 72) -> int:
        """
        清理过期的检查点文件。

        Args:
            max_age_hours: 最大保留时间（小时）

        Returns:
            清理的文件数
        """
        if not isinstance(self._backend, FileStorageBackend):
            return 0

        cleaned = 0
        now = time.time()
        storage_dir = self._backend.storage_dir

        if not os.path.exists(storage_dir):
            return 0

        for fname in os.listdir(storage_dir):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(storage_dir, fname)
            try:
                file_age_hours = (now - os.path.getmtime(fpath)) / 3600
                if file_age_hours > max_age_hours:
                    os.remove(fpath)
                    cleaned += 1
            except OSError:  # noqa: intentional empty handler
                pass

        return cleaned


__all__ = [
    "Checkpoint",
    "TaskSnapshot",
    "CheckpointManager",
    "StorageBackend",
    "FileStorageBackend",
    "estimate_brain_cost",
    "BRAIN_COST_ESTIMATES",
]
