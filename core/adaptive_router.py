# -*- coding: utf-8 -*-
"""
自适应路由 (Adaptive Router)
章鱼架构 v2.0 - 模块7

核心能力：
1. route()           - 基于历史数据选最优引擎组合
2. record_outcome()  - 记录每次执行效果，自动更新引擎评分
3. get_engine_score()- 获取引擎在特定任务类型上的历史评分
4. 路由优化闭环：任务 → 选择 → 执行 → 评估 → 更新评分 → 下次路由更准

内部使用 ExecutionHistory 类存储历史数据（JSON文件存储）。

Usage:
    from core.adaptive_router import AdaptiveRouter

    router = AdaptiveRouter()

    # 路由：根据任务特征选择最优引擎组合
    plan = router.route(
        task_type="security",
        file_count=50,
        languages=["python"],
    )

    # 执行后记录结果
    router.record_outcome(
        task_id="review_001",
        brain_id="1",
        accuracy=0.95,
        false_positive_rate=0.05,
        elapsed=5.0,
        cost=0.0,
    )

    # 查询引擎评分
    score = router.get_engine_score("1", task_type="security")
"""

import json
import math
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from collections import defaultdict


# =============================================================================
# 数据结构
# =============================================================================

@dataclass
class TaskFeatures:
    """任务特征描述"""

    task_type: str = ""                  # 任务类型: security/performance/quality/full
    file_count: int = 0                  # 文件数量
    languages: List[str] = field(default_factory=list)  # 编程语言
    framework: str = ""                  # 框架
    complexity: str = "medium"           # 复杂度: low/medium/high
    budget: float = -1.0                 # 预算（-1 = 不限制）
    requires_high_confidence: bool = False  # 是否需要高置信度
    project_id: str = ""                 # 项目标识

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_type": self.task_type,
            "file_count": self.file_count,
            "languages": self.languages,
            "framework": self.framework,
            "complexity": self.complexity,
            "budget": self.budget,
            "requires_high_confidence": self.requires_high_confidence,
            "project_id": self.project_id,
        }

    def similarity_to(self, other: "TaskFeatures") -> float:
        """
        计算两个任务特征的相似度 (0.0 ~ 1.0)。

        用于查找历史相似任务。
        """
        score = 0.0
        weights = 0.0

        # 任务类型匹配（权重最高）
        if self.task_type and other.task_type:
            weights += 3.0
            if self.task_type == other.task_type:
                score += 3.0

        # 复杂度匹配
        if self.complexity and other.complexity:
            weights += 2.0
            if self.complexity == other.complexity:
                score += 2.0

        # 文件数量接近程度
        if self.file_count > 0 and other.file_count > 0:
            weights += 1.5
            ratio = min(self.file_count, other.file_count) / max(self.file_count, other.file_count)
            score += 1.5 * ratio

        # 语言重叠
        if self.languages and other.languages:
            weights += 1.5
            overlap = len(set(self.languages) & set(other.languages))
            total = len(set(self.languages) | set(other.languages))
            score += 1.5 * (overlap / max(total, 1))

        # 框架匹配
        if self.framework and other.framework:
            weights += 1.0
            if self.framework == other.framework:
                score += 1.0

        if weights == 0:
            return 0.0
        return score / weights


@dataclass
class ExecutionRecord:
    """单次执行记录"""

    task_id: str
    brain_id: str
    task_features: Dict[str, Any] = field(default_factory=dict)
    accuracy: float = 0.0                # 准确率 (0~1)
    false_positive_rate: float = 0.0     # 误报率 (0~1)
    elapsed_seconds: float = 0.0         # 耗时
    cost: float = 0.0                    # 成本
    issues_found: int = 0                # 发现问题数
    issues_confirmed: int = 0            # 确认有效数
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "brain_id": self.brain_id,
            "task_features": self.task_features,
            "accuracy": round(self.accuracy, 4),
            "false_positive_rate": round(self.false_positive_rate, 4),
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "cost": round(self.cost, 6),
            "issues_found": self.issues_found,
            "issues_confirmed": self.issues_confirmed,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionRecord":
        return cls(
            task_id=data.get("task_id", ""),
            brain_id=data.get("brain_id", ""),
            task_features=data.get("task_features", {}),
            accuracy=data.get("accuracy", 0.0),
            false_positive_rate=data.get("false_positive_rate", 0.0),
            elapsed_seconds=data.get("elapsed_seconds", 0.0),
            cost=data.get("cost", 0.0),
            issues_found=data.get("issues_found", 0),
            issues_confirmed=data.get("issues_confirmed", 0),
            timestamp=data.get("timestamp", ""),
        )


@dataclass
class EngineScore:
    """引擎评分"""

    brain_id: str
    task_type: str = ""                  # 特定任务类型的评分（空 = 综合）
    effectiveness: float = 0.0           # 有效性 (0~1)
    efficiency: float = 0.0              # 效率 (0~1) = 准确率/耗时
    reliability: float = 0.0             # 可靠性 (0~1) = 1 - 误报率
    cost_efficiency: float = 0.0         # 性价比 (0~1)
    composite_score: float = 0.0         # 综合得分 (0~1)
    sample_count: int = 0                # 样本数

    def to_dict(self) -> Dict[str, Any]:
        return {
            "brain_id": self.brain_id,
            "task_type": self.task_type,
            "effectiveness": round(self.effectiveness, 4),
            "efficiency": round(self.efficiency, 4),
            "reliability": round(self.reliability, 4),
            "cost_efficiency": round(self.cost_efficiency, 4),
            "composite_score": round(self.composite_score, 4),
            "sample_count": self.sample_count,
        }


@dataclass
class RoutePlan:
    """路由方案"""

    selected_brains: List[str] = field(default_factory=list)
    execution_order: List[str] = field(default_factory=list)
    estimated_cost: float = 0.0
    estimated_time: float = 0.0
    confidence: float = 0.0              # 路由决策的置信度
    reasoning: List[str] = field(default_factory=list)  # 路由理由
    similar_task_count: int = 0          # 参考的历史相似任务数

    def to_dict(self) -> Dict[str, Any]:
        return {
            "selected_brains": self.selected_brains,
            "execution_order": self.execution_order,
            "estimated_cost": round(self.estimated_cost, 6),
            "estimated_time": round(self.estimated_time, 1),
            "confidence": round(self.confidence, 4),
            "reasoning": self.reasoning,
            "similar_task_count": self.similar_task_count,
        }


# =============================================================================
# 执行历史存储
# =============================================================================

class ExecutionHistory:
    """
    执行历史存储。

    记录每次大脑执行的详细数据，用于自适应路由决策。
    存储后端：JSON 文件。
    """

    def __init__(self, storage_path: str):
        self._path = storage_path
        os.makedirs(os.path.dirname(storage_path), exist_ok=True)
        self._records: List[ExecutionRecord] = self._load()

    def _load(self) -> List[ExecutionRecord]:
        if not os.path.exists(self._path):
            return []
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [ExecutionRecord.from_dict(d) for d in data]
        except (json.JSONDecodeError, IOError):
            return []

    def _save(self) -> None:
        data = [r.to_dict() for r in self._records]
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add(self, record: ExecutionRecord) -> None:
        self._records.append(record)
        self._save()

    def get_all(self) -> List[ExecutionRecord]:
        return list(self._records)

    def get_by_brain(self, brain_id: str) -> List[ExecutionRecord]:
        return [r for r in self._records if r.brain_id == str(brain_id)]

    def get_by_task_type(self, task_type: str) -> List[ExecutionRecord]:
        return [
            r for r in self._records
            if r.task_features.get("task_type", "") == task_type
        ]

    def get_by_brain_and_task_type(
        self, brain_id: str, task_type: str
    ) -> List[ExecutionRecord]:
        return [
            r for r in self._records
            if r.brain_id == str(brain_id)
            and r.task_features.get("task_type", "") == task_type
        ]

    @property
    def count(self) -> int:
        return len(self._records)


# =============================================================================
# 自适应路由器
# =============================================================================

class AdaptiveRouter:
    """
    自适应路由器。

    基于历史执行数据，自动选择最优的引擎组合。
    形成闭环：任务 → 选择 → 执行 → 评估 → 更新评分 → 下次路由更准。

    路由策略：
    1. 分析当前任务特征
    2. 查历史相似任务（基于 TaskFeatures 相似度）
    3. 计算各引擎在相似任务上的评分
    4. 选择评分最高的引擎组合
    5. 如果没有历史数据，使用默认规则
    """

    # 默认引擎优先级（无历史数据时使用）
    DEFAULT_PRIORITY = {
        "security": ["1", "6", "2", "3"],
        "performance": ["3", "1", "2"],
        "quality": ["1", "2", "5"],
        "full": ["1", "2", "3", "4", "5"],
        "quick": ["1"],
        "compliance": ["1", "4", "5"],
    }

    # 引擎成本基线
    ENGINE_COSTS: Dict[str, float] = {
        "1": 0.0, "2": 0.02, "3": 0.0, "4": 0.0,
        "5": 0.0, "6": 0.005, "7": 0.01,
    }

    # 评分维度权重
    WEIGHT_EFFECTIVENESS = 0.35
    WEIGHT_EFFICIENCY = 0.25
    WEIGHT_RELIABILITY = 0.25
    WEIGHT_COST = 0.15

    def __init__(self, storage_dir: Optional[str] = None):
        if storage_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            storage_dir = os.path.join(base_dir, ".qa_history")
        self._history = ExecutionHistory(
            os.path.join(storage_dir, "execution_history.json")
        )

    def route(
        self,
        task_type: str = "full",
        file_count: int = 0,
        languages: Optional[List[str]] = None,
        framework: str = "",
        complexity: str = "medium",
        budget: float = -1.0,
        requires_high_confidence: bool = False,
    ) -> RoutePlan:
        """
        基于历史数据选择最优引擎组合。

        Args:
            task_type: 任务类型
            file_count: 文件数量
            languages: 编程语言列表
            framework: 框架
            complexity: 复杂度
            budget: 预算（-1 = 不限）
            requires_high_confidence: 是否需高置信度

        Returns:
            RoutePlan 路由方案
        """
        current_features = TaskFeatures(
            task_type=task_type,
            file_count=file_count,
            languages=languages or [],
            framework=framework,
            complexity=complexity,
            budget=budget,
            requires_high_confidence=requires_high_confidence,
        )

        plan = RoutePlan()

        # Step 1: 查找历史相似任务
        similar_records = self._find_similar_tasks(current_features, top_k=20)
        plan.similar_task_count = len(similar_records)

        if len(similar_records) >= 3:
            # 有足够历史数据 → 基于评分路由
            plan = self._route_by_scores(current_features, similar_records)
        else:
            # 历史数据不足 → 使用默认规则
            plan = self._route_by_defaults(current_features)

        # Step 2: 高置信度需求 → 增加辩论模式的大脑
        if requires_high_confidence and len(plan.selected_brains) < 3:
            extra = ["2"]  # 加入 AI 引擎做交叉验证
            for bid in extra:
                if bid not in plan.selected_brains:
                    plan.selected_brains.append(bid)
                    plan.reasoning.append(f"高置信度需求：加入大脑{bid}交叉验证")

        # Step 3: 预算约束
        if budget >= 0:
            plan = self._apply_budget_constraint(plan, budget)

        # Step 4: 设置执行顺序（按优先级）
        plan.execution_order = self._sort_by_priority(plan.selected_brains)

        return plan

    def record_outcome(
        self,
        task_id: str,
        brain_id: str,
        task_features: Optional[Dict[str, Any]] = None,
        accuracy: float = 0.0,
        false_positive_rate: float = 0.0,
        elapsed: float = 0.0,
        cost: float = 0.0,
        issues_found: int = 0,
        issues_confirmed: int = 0,
    ) -> ExecutionRecord:
        """
        记录执行效果，自动更新引擎评分。

        Args:
            task_id: 任务ID
            brain_id: 大脑ID
            task_features: 任务特征
            accuracy: 准确率 (0~1)
            false_positive_rate: 误报率 (0~1)
            elapsed: 耗时（秒）
            cost: 成本（元）
            issues_found: 发现问题数
            issues_confirmed: 确认有效数

        Returns:
            ExecutionRecord
        """
        record = ExecutionRecord(
            task_id=task_id,
            brain_id=str(brain_id),
            task_features=task_features or {},
            accuracy=accuracy,
            false_positive_rate=false_positive_rate,
            elapsed_seconds=elapsed,
            cost=cost,
            issues_found=issues_found,
            issues_confirmed=issues_confirmed,
            timestamp=datetime.now().isoformat(),
        )
        self._history.add(record)
        return record

    def get_engine_score(
        self, brain_id: str, task_type: str = ""
    ) -> EngineScore:
        """
        获取引擎在特定任务类型上的历史评分。

        Args:
            brain_id: 大脑ID
            task_type: 任务类型（空 = 综合评分）

        Returns:
            EngineScore
        """
        if task_type:
            records = self._history.get_by_brain_and_task_type(brain_id, task_type)
        else:
            records = self._history.get_by_brain(brain_id)

        return self._compute_score(str(brain_id), task_type, records)

    def get_all_scores(self, task_type: str = "") -> Dict[str, EngineScore]:
        """获取所有引擎的评分"""
        scores = {}
        for bid in ["1", "2", "3", "4", "5", "6", "7"]:
            scores[bid] = self.get_engine_score(bid, task_type)
        return scores

    # ---- 内部方法 ----

    def _find_similar_tasks(
        self, features: TaskFeatures, top_k: int = 20
    ) -> List[ExecutionRecord]:
        """查找历史相似任务"""
        all_records = self._history.get_all()
        if not all_records:
            return []

        scored = []
        for record in all_records:
            hist_features = TaskFeatures(**{
                k: v for k, v in record.task_features.items()
                if k in TaskFeatures.__dataclass_fields__
            })
            sim = features.similarity_to(hist_features)
            if sim > 0.1:  # 相似度阈值
                scored.append((sim, record))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:top_k]]

    def _route_by_scores(
        self, features: TaskFeatures, similar_records: List[ExecutionRecord]
    ) -> RoutePlan:
        """基于历史评分路由"""
        plan = RoutePlan()

        # 从相似记录中提取所有涉及的大脑
        brain_ids = set(r.brain_id for r in similar_records)

        # 计算每个大脑在相似任务上的表现
        brain_performances: Dict[str, Dict[str, float]] = {}
        for bid in brain_ids:
            bid_records = [r for r in similar_records if r.brain_id == bid]
            if not bid_records:
                continue

            avg_accuracy = sum(r.accuracy for r in bid_records) / len(bid_records)
            avg_fp = sum(r.false_positive_rate for r in bid_records) / len(bid_records)
            avg_cost = sum(r.cost for r in bid_records) / len(bid_records)
            avg_time = sum(r.elapsed_seconds for r in bid_records) / len(bid_records)

            brain_performances[bid] = {
                "accuracy": avg_accuracy,
                "fp_rate": avg_fp,
                "cost": avg_cost,
                "time": avg_time,
                "count": len(bid_records),
            }

        # 选择准确率 >= 0.5 且样本数 >= 1 的引擎
        selected = []
        for bid, perf in brain_performances.items():
            if perf["accuracy"] >= 0.5 and perf["count"] >= 1:
                selected.append(bid)
                plan.reasoning.append(
                    f"大脑{bid}: 历史准确率 {perf['accuracy']:.2f}, "
                    f"样本 {perf['count']} 次"
                )

        if not selected:
            # 评分路由失败，回退到默认
            return self._route_by_defaults(features)

        plan.selected_brains = sorted(selected)
        plan.confidence = min(1.0, len(similar_records) / 10.0)
        return plan

    def _route_by_defaults(self, features: TaskFeatures) -> RoutePlan:
        """默认规则路由（无历史数据时使用）"""
        plan = RoutePlan()

        task_type = features.task_type or "full"
        defaults = self.DEFAULT_PRIORITY.get(task_type, self.DEFAULT_PRIORITY["full"])
        plan.selected_brains = list(defaults)

        # 大型项目 → 加入分工模式建议
        if features.file_count > 100:
            plan.reasoning.append(f"大型项目 ({features.file_count} 文件): 建议分工模式")

        plan.reasoning.append(f"历史数据不足，使用默认规则 (task_type={task_type})")
        plan.confidence = 0.3  # 低置信度
        return plan

    def _apply_budget_constraint(
        self, plan: RoutePlan, budget: float
    ) -> RoutePlan:
        """应用预算约束"""
        # 按成本从低到高排序
        sorted_brains = sorted(
            plan.selected_brains,
            key=lambda b: self.ENGINE_COSTS.get(b, 0.01),
        )

        selected = []
        total_cost = 0.0
        for bid in sorted_brains:
            cost = self.ENGINE_COSTS.get(bid, 0.01)
            if total_cost + cost <= budget:
                selected.append(bid)
                total_cost += cost
            else:
                plan.reasoning.append(
                    f"大脑{bid}因预算不足被移除 (成本 {cost:.4f})"
                )

        plan.selected_brains = selected
        plan.estimated_cost = total_cost
        return plan

    def _sort_by_priority(self, brain_ids: List[str]) -> List[str]:
        """按优先级排序执行顺序"""
        priority_map = {
            "1": 100, "3": 80, "4": 70, "5": 60, "6": 50, "7": 45, "2": 10,
        }
        return sorted(
            brain_ids,
            key=lambda b: priority_map.get(b, 0),
            reverse=True,
        )

    def _compute_score(
        self, brain_id: str, task_type: str, records: List[ExecutionRecord]
    ) -> EngineScore:
        """计算引擎评分"""
        score = EngineScore(
            brain_id=brain_id,
            task_type=task_type,
            sample_count=len(records),
        )

        if not records:
            return score

        # 有效性 = 平均准确率
        score.effectiveness = sum(r.accuracy for r in records) / len(records)

        # 效率 = 准确率 / 归一化耗时（耗时越少越好）
        avg_time = sum(r.elapsed_seconds for r in records) / len(records)
        max_time = 180.0  # 假设最大合理耗时 180 秒
        time_score = max(0, 1.0 - avg_time / max_time)
        score.efficiency = score.effectiveness * time_score

        # 可靠性 = 1 - 误报率
        avg_fp = sum(r.false_positive_rate for r in records) / len(records)
        score.reliability = 1.0 - avg_fp

        # 性价比 = 有效性 / 归一化成本
        avg_cost = sum(r.cost for r in records) / len(records)
        if avg_cost > 0:
            score.cost_efficiency = score.effectiveness / (1.0 + avg_cost * 50)
        else:
            score.cost_efficiency = score.effectiveness  # 免费引擎满分

        # 综合得分（加权平均）
        score.composite_score = (
            self.WEIGHT_EFFECTIVENESS * score.effectiveness
            + self.WEIGHT_EFFICIENCY * score.efficiency
            + self.WEIGHT_RELIABILITY * score.reliability
            + self.WEIGHT_COST * score.cost_efficiency
        )

        return score

    # ---- 便捷属性 ----

    @property
    def history_count(self) -> int:
        """历史记录总数"""
        return self._history.count


__all__ = [
    "TaskFeatures",
    "ExecutionRecord",
    "EngineScore",
    "RoutePlan",
    "ExecutionHistory",
    "AdaptiveRouter",
]
