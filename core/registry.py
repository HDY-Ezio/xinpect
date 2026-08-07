# -*- coding: utf-8 -*-
"""
章鱼架构 v2.0 - 统一注册入口 (Architecture Registry)
煋鉴 Xinpect - 8大架构模块的统一入口

将所有架构模块注册到统一入口，提供：
1. 一站式导入
2. 全局初始化
3. 版本信息
4. 模块状态检查

Usage:
    from core.registry import OctopusArchitecture

    # 一键初始化所有模块
    arch = OctopusArchitecture(project_id="my_project")
    arch.initialize()

    # 按模块使用
    arch.contract_validator.validate_brain_result(...)
    arch.aggregator.aggregate(...)
    arch.cost_manager.estimate(...)
"""

import os
import sys
from typing import Any, Dict, Optional

# 版本信息
__version__ = "2.0.0"
__architecture__ = "Octopus Architecture v2.0"


class OctopusArchitecture:
    """
    章鱼架构 v2.0 统一入口。

    将8大架构模块聚合到一个对象中，提供统一的初始化和访问接口。
    """

    VERSION = __version__
    MODULES = [
        "task_contract",       # 模块1: 交付标准契约系统
        "result_aggregator",   # 模块2: 跨引擎去重 + 共识度计算
        "collaboration_modes", # 模块3: 多模式协同
        "checkpoint_manager",  # 模块4: 检查点与故障恢复
        "message_bus",         # 模块5: 消息总线
        "cost_manager",        # 模块6: 动态成本管理
        "adaptive_router",     # 模块7: 自适应路由
        "knowledge_base",      # 模块8: 跨项目知识库
    ]

    def __init__(
        self,
        project_id: str = "default",
        storage_dir: Optional[str] = None,
    ):
        """
        Args:
            project_id: 项目标识
            storage_dir: 持久化存储根目录（默认 .qa_history/）
        """
        self.project_id = project_id

        if storage_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            storage_dir = os.path.join(base_dir, ".qa_history")
        self.storage_dir = storage_dir

        # 模块实例（延迟初始化）
        self._modules: Dict[str, Any] = {}
        self._initialized = False

    def initialize(self) -> Dict[str, bool]:
        """
        初始化所有架构模块。

        Returns:
            {module_name: success_bool} 初始化状态
        """
        status: Dict[str, bool] = {}

        # 模块1: 契约系统
        status["task_contract"] = self._init_task_contract()

        # 模块2: 结果聚合器
        status["result_aggregator"] = self._init_result_aggregator()

        # 模块3: 协同模式
        status["collaboration_modes"] = self._init_collaboration_modes()

        # 模块4: 检查点管理
        status["checkpoint_manager"] = self._init_checkpoint_manager()

        # 模块5: 消息总线
        status["message_bus"] = self._init_message_bus()

        # 模块6: 成本管理
        status["cost_manager"] = self._init_cost_manager()

        # 模块7: 自适应路由
        status["adaptive_router"] = self._init_adaptive_router()

        # 模块8: 知识库
        status["knowledge_base"] = self._init_knowledge_base()

        self._initialized = all(status.values())
        return status

    # ---- 模块属性访问 ----

    @property
    def contracts(self) -> Any:
        """模块1: 契约配置"""
        return self._modules.get("task_contract")

    @property
    def aggregator(self) -> Any:
        """模块2: 结果聚合器"""
        return self._modules.get("result_aggregator")

    @property
    def modes(self) -> Any:
        """模块3: 模式选择器"""
        return self._modules.get("collaboration_modes")

    @property
    def checkpoint(self) -> Any:
        """模块4: 检查点管理器"""
        return self._modules.get("checkpoint_manager")

    @property
    def bus(self) -> Any:
        """模块5: 消息总线"""
        return self._modules.get("message_bus")

    @property
    def cost_manager(self) -> Any:
        """模块6: 成本管理器"""
        return self._modules.get("cost_manager")

    @property
    def router(self) -> Any:
        """模块7: 自适应路由器"""
        return self._modules.get("adaptive_router")

    @property
    def knowledge(self) -> Any:
        """模块8: 知识库"""
        return self._modules.get("knowledge_base")

    # ---- 初始化方法 ----

    def _init_task_contract(self) -> bool:
        try:
            from .task_contract import load_brain_contracts
            self._modules["task_contract"] = load_brain_contracts()
            return True
        except Exception as e:  # noqa: broad exception handling
            self._modules["task_contract"] = {}
            return False

    def _init_result_aggregator(self) -> bool:
        try:
            from .result_aggregator import ResultAggregator
            self._modules["result_aggregator"] = ResultAggregator()
            return True
        except Exception as e:  # noqa: broad exception handling
            self._modules["result_aggregator"] = None
            return False

    def _init_collaboration_modes(self) -> bool:
        try:
            from .collaboration_modes import ModeSelector
            self._modules["collaboration_modes"] = ModeSelector()
            return True
        except Exception as e:  # noqa: broad exception handling
            self._modules["collaboration_modes"] = None
            return False

    def _init_checkpoint_manager(self) -> bool:
        try:
            from .checkpoint_manager import CheckpointManager
            checkpoint_dir = os.path.join(self.storage_dir, "checkpoints")
            self._modules["checkpoint_manager"] = CheckpointManager(
                task_id=f"session_{self.project_id}",
                storage_dir=checkpoint_dir,
            )
            return True
        except Exception as e:  # noqa: broad exception handling
            self._modules["checkpoint_manager"] = None
            return False

    def _init_message_bus(self) -> bool:
        try:
            from .message_bus import get_message_bus
            self._modules["message_bus"] = get_message_bus()
            return True
        except Exception as e:  # noqa: broad exception handling
            self._modules["message_bus"] = None
            return False

    def _init_cost_manager(self) -> bool:
        try:
            from .cost_manager import CostManager
            cost_dir = os.path.join(self.storage_dir, "costs")
            self._modules["cost_manager"] = CostManager(
                project_id=self.project_id,
                storage_dir=cost_dir,
            )
            return True
        except Exception as e:  # noqa: broad exception handling
            self._modules["cost_manager"] = None
            return False

    def _init_adaptive_router(self) -> bool:
        try:
            from .adaptive_router import AdaptiveRouter
            self._modules["adaptive_router"] = AdaptiveRouter(
                storage_dir=self.storage_dir,
            )
            return True
        except Exception as e:  # noqa: broad exception handling
            self._modules["adaptive_router"] = None
            return False

    def _init_knowledge_base(self) -> bool:
        try:
            from .knowledge_base import KnowledgeBase
            kb_dir = os.path.join(self.storage_dir, "knowledge")
            self._modules["knowledge_base"] = KnowledgeBase(
                project_id=self.project_id,
                storage_dir=kb_dir,
            )
            return True
        except Exception as e:  # noqa: broad exception handling
            self._modules["knowledge_base"] = None
            return False

    # ---- 状态查询 ----

    def status(self) -> Dict[str, Any]:
        """获取所有模块状态"""
        return {
            "version": self.VERSION,
            "architecture": __architecture__,
            "project_id": self.project_id,
            "storage_dir": self.storage_dir,
            "initialized": self._initialized,
            "modules": {
                name: {
                    "loaded": module is not None,
                    "type": type(module).__name__ if module else None,
                }
                for name, module in self._modules.items()
            },
        }

    def health_check(self) -> Dict[str, bool]:
        """检查所有模块健康状态"""
        health: Dict[str, bool] = {}
        for name in self.MODULES:
            module = self._modules.get(name)
            health[name] = module is not None
        return health


# =============================================================================
# 便捷导入函数
# =============================================================================

def get_architecture(project_id: str = "default", **kwargs) -> OctopusArchitecture:
    """
    获取并初始化章鱼架构实例。

    Args:
        project_id: 项目标识
        **kwargs: 传递给 OctopusArchitecture 的参数

    Returns:
        已初始化的 OctopusArchitecture 实例
    """
    arch = OctopusArchitecture(project_id=project_id, **kwargs)
    arch.initialize()
    return arch


__all__ = [
    "OctopusArchitecture",
    "get_architecture",
    "__version__",
    "__architecture__",
]
