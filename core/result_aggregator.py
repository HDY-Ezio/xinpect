# -*- coding: utf-8 -*-
"""
跨引擎去重 + 共识度计算引擎 (Result Aggregator)
章鱼架构 v2.0 - 模块2

核心能力：
1. 跨引擎去重：不同大脑发现的同一问题，合并为一条
   匹配规则：文件路径 + 行号（±容忍范围） + 问题类型
2. 共识度计算：标注 detected_by 列表，confidence = detected_by数量 / 总引擎数
3. 冲突仲裁：引擎间意见不一致时的处理逻辑
4. 统一输出格式化

Usage:
    from core.result_aggregator import ResultAggregator

    aggregator = ResultAggregator()
    merged = aggregator.aggregate(brain_results_dict)
"""

import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

# [v2.0优化] 统一导入全局常量，消除重复定义
try:
    from .constants import (
        SEVERITY_ORDER, severity_rank, normalize_severity,
        get_dedup_tolerance, DEDUP_LINE_TOLERANCE,
    )
except ImportError:
    # 降级兼容：模块路径异常时使用内联定义
    SEVERITY_ORDER = {
        "blocker": 4, "critical": 4, "high": 3, "medium": 2,
        "low": 1, "info": 0, "S1": 4, "S2": 3, "S3": 2, "S4": 1,
    }
    def severity_rank(sev: str) -> int:
        return SEVERITY_ORDER.get(sev, 0)
    def normalize_severity(sev: str) -> str:
        return {"S1": "blocker", "S2": "high", "S3": "medium", "S4": "low", "critical": "blocker"}.get(sev, sev)
    def get_dedup_tolerance(category: str = "") -> int:
        return 3


# =============================================================================
# 数据结构
# =============================================================================

@dataclass
class UnifiedIssue:
    """
    统一问题条目（跨引擎去重后的合并结果）。

    一个 UnifiedIssue 可能由多个大脑独立发现，
    detected_by 记录哪些大脑发现了它。
    """

    check_id: str                        # 主检查ID（取最高优先级引擎的）
    name: str                            # 问题名称
    severity: str                        # 严重度（取最严重的）
    file: str                            # 文件路径
    line: int                            # 行号
    message: str                         # 问题描述
    suggestion: str = ""                 # 修复建议（取最长的）
    category: str = ""                   # 问题分类
    detected_by: List[str] = field(default_factory=list)  # 发现此问题的大脑列表
    consensus: float = 0.0              # 共识度 (0.0 ~ 1.0)
    confidence: str = "low"              # 置信度: high / medium / low
    source_severities: Dict[str, str] = field(default_factory=dict)  # 各引擎给出的严重度
    source_ids: List[str] = field(default_factory=list)  # 各引擎的原始 check_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_id": self.check_id,
            "name": self.name,
            "severity": self.severity,
            "file": self.file,
            "line": self.line,
            "message": self.message,
            "suggestion": self.suggestion,
            "category": self.category,
            "detected_by": self.detected_by,
            "consensus": round(self.consensus, 3),
            "confidence": self.confidence,
            "source_ids": self.source_ids,
        }


@dataclass
class AggregationResult:
    """聚合结果"""

    issues: List[UnifiedIssue] = field(default_factory=list)
    total_before_dedup: int = 0          # 去重前总问题数
    total_after_dedup: int = 0           # 去重后总问题数
    duplicates_removed: int = 0          # 移除的重复数
    conflicts_resolved: int = 0          # 解决的冲突数
    consensus_distribution: Dict[str, int] = field(default_factory=dict)  # 共识度分布

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issues": [i.to_dict() for i in self.issues],
            "stats": {
                "total_before_dedup": self.total_before_dedup,
                "total_after_dedup": self.total_after_dedup,
                "duplicates_removed": self.duplicates_removed,
                "conflicts_resolved": self.conflicts_resolved,
                "consensus_distribution": self.consensus_distribution,
            },
        }


# =============================================================================
# 严重度工具 [v2.0优化] 已迁移至 core/constants.py 统一维护
# =============================================================================
# SEVERITY_ORDER / _severity_rank / _normalize_severity 现在统一来自 constants.py
# 上方 try/except ImportError 块已完成导入，此处仅提供兼容别名

_severity_rank = severity_rank
_normalize_severity = normalize_severity


# =============================================================================
# 去重键生成
# =============================================================================

def _make_dedup_key(file_path: str, line: int, issue_type: str = "",
                    line_tolerance: int = 3) -> str:
    """
    生成去重键。

    规则：
    - 同文件 + 同行（±容忍范围） + 同问题类型 → 同一去重键
    - line_tolerance: 行号容忍范围（默认 ±3 行，自适应调整见 _compute_dedup_key）

    [v2.0优化] 支持自适应容忍范围：安全类±1行，性能类±5行，默认±3行
    """
    # 文件路径归一化
    normalized_file = os.path.normpath(file_path).replace("\\", "/")

    # 行号分桶（每 line_tolerance*2+1 行一个桶）
    bucket_size = line_tolerance * 2 + 1
    line_bucket = (line // bucket_size) * bucket_size

    # 问题类型归一化（提取关键词）
    normalized_type = _normalize_issue_type(issue_type)

    return f"{normalized_file}:{line_bucket}:{normalized_type}"


def _message_similarity(msg1: str, msg2: str) -> float:
    """
    [v2.0优化] 计算两条消息的文本相似度（简易版）。

    基于 Jaccard 字符 n-gram 相似度，无需外部依赖。
    返回值: 0.0 ~ 1.0，>0.8 视为高度相似。
    """
    try:
        if not msg1 or not msg2:
            return 0.0
        if msg1 == msg2:
            return 1.0

        # 使用 2-gram 字符级相似度
        def _ngrams(text: str, n: int = 2) -> set:
            text = text.lower().strip()
            return {text[i:i+n] for i in range(len(text) - n + 1)} if len(text) >= n else {text}

        set1 = _ngrams(msg1)
        set2 = _ngrams(msg2)
        intersection = set1 & set2
        union = set1 | set2

        if not union:
            return 0.0
        return len(intersection) / len(union)
    except Exception as e:  # noqa: broad exception handling
        return 0.0


def _normalize_issue_type(issue_type: str) -> str:
    """
    归一化问题类型，使不同引擎对同类问题的描述能匹配上。

    例如: "SQL注入" 和 "SQL Injection" 和 "sql_injection" → 同一个键
    """
    if not issue_type:
        return ""

    # 转小写，去除特殊字符
    t = issue_type.lower().strip()
    t = re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", t)

    # 中英文映射（常见安全/性能问题类型）
    cn_en_map = {
        "内存泄漏": "memoryleak",
        "空指针": "nullpointer",
        "注入": "injection",
        "硬编码": "hardcoded",
        "敏感信息": "sensitiveinfo",
        "性能": "performance",
        "安全": "security",
        "异常处理": "exceptionhandling",
        "并发": "concurrency",
        "资源泄漏": "resourceleak",
    }

    for cn, en in cn_en_map.items():
        if cn in t:
            return en

    return t


# =============================================================================
# 结果聚合引擎
# =============================================================================

class ResultAggregator:
    """
    跨引擎结果聚合器。

    核心流程：
    1. 收集所有大脑的 issues
    2. 按去重键分组
    3. 同组内合并（取最严重、取最长建议、记录 detected_by）
    4. 计算共识度
    5. 冲突仲裁
    6. 输出格式化
    """

    def __init__(self, line_tolerance: int = 3, total_engines: int = 5):
        """
        Args:
            line_tolerance: 行号容忍范围（默认 ±3 行视为同一问题）
            total_engines: 总引擎数（用于计算共识度）
        """
        self.line_tolerance = line_tolerance
        self.total_engines = total_engines

    def aggregate(
        self,
        brain_results: Dict[str, Any],
    ) -> AggregationResult:
        """
        聚合多个大脑的审查结果。

        Args:
            brain_results: {brain_name: BrainResult_or_dict}
                支持 BrainResult 对象或 dict

        Returns:
            AggregationResult 聚合结果
        """
        result = AggregationResult()

        # Step 1: 收集所有 issues（带来源标注）
        all_issues: List[Tuple[str, Dict[str, Any]]] = []  # (brain_name, issue_dict)

        for brain_name, brain_result in brain_results.items():
            # 兼容 BrainResult 对象和 dict
            issues = self._extract_issues(brain_result)
            for issue in issues:
                all_issues.append((brain_name, issue))

        result.total_before_dedup = len(all_issues)

        # Step 2: 按去重键分组
        groups: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {}
        for brain_name, issue in all_issues:
            key = self._compute_dedup_key(issue)
            if key not in groups:
                groups[key] = []
            groups[key].append((brain_name, issue))

        # Step 2.5: [v2.0优化] 消息相似度兜底合并
        # 对于不同去重键但消息高度相似的 issue，尝试合并
        groups = self._similarity_merge_groups(groups)

        # Step 3: 合并同组 issues
        merged_issues: List[UnifiedIssue] = []
        for key, group in groups.items():
            merged = self._merge_group(key, group)
            merged_issues.append(merged)

        # Step 4: 计算共识度
        for issue in merged_issues:
            issue.consensus = len(issue.detected_by) / max(self.total_engines, 1)
            # 置信度分级
            if issue.consensus >= 0.6:
                issue.confidence = "high"
            elif issue.consensus >= 0.3:
                issue.confidence = "medium"
            else:
                issue.confidence = "low"

        # Step 5: 冲突仲裁
        conflicts = self._detect_conflicts(merged_issues)
        result.conflicts_resolved = len(conflicts)

        # Step 6: 排序（按严重度降序，同严重度按共识度降序）
        merged_issues.sort(
            key=lambda x: (_severity_rank(x.severity), x.consensus),
            reverse=True,
        )

        result.issues = merged_issues
        result.total_after_dedup = len(merged_issues)
        result.duplicates_removed = result.total_before_dedup - result.total_after_dedup

        # 共识度分布统计
        high = sum(1 for i in merged_issues if i.confidence == "high")
        medium = sum(1 for i in merged_issues if i.confidence == "medium")
        low = sum(1 for i in merged_issues if i.confidence == "low")
        result.consensus_distribution = {
            "high": high,
            "medium": medium,
            "low": low,
        }

        return result

    def _extract_issues(self, brain_result: Any) -> List[Dict[str, Any]]:
        """从大脑结果中提取 issues 列表（兼容对象和字典）"""
        issues = []

        # 兼容 BrainResult 对象
        if hasattr(brain_result, "issues"):
            for issue in brain_result.issues:
                if hasattr(issue, "to_dict"):
                    issues.append(issue.to_dict())
                elif isinstance(issue, dict):
                    issues.append(issue)
            return issues

        # 兼容 dict
        if isinstance(brain_result, dict):
            raw_issues = brain_result.get("issues", [])
            for issue in raw_issues:
                if isinstance(issue, dict):
                    issues.append(issue)

        return issues

    def _compute_dedup_key(self, issue: Dict[str, Any]) -> str:
        """
        计算单个 issue 的去重键。
        
        [v2.0优化] 自适应容忍范围：根据 issue 的 category 动态调整行号容忍度。
        """
        file_path = issue.get("file", "")
        line = issue.get("line", 0)

        # 问题类型：优先用 category，其次从 check_id / message 提取
        issue_type = (
            issue.get("category", "")
            or issue.get("check_id", "")
            or issue.get("message", "")[:30]
        )

        # [v2.0优化] 根据 category 获取自适应容忍范围
        category = issue.get("category", "")
        try:
            adaptive_tolerance = get_dedup_tolerance(category)
        except Exception as e:  # noqa: broad exception handling
            adaptive_tolerance = self.line_tolerance

        return _make_dedup_key(file_path, line, issue_type, adaptive_tolerance)

    def _merge_group(
        self,
        key: str,
        group: List[Tuple[str, Dict[str, Any]]],
    ) -> UnifiedIssue:
        """
        合并同一去重键下的多个 issues。

        策略：
        - check_id: 取第一个（最高优先级引擎的）
        - severity: 取最严重的
        - message: 取最长的（信息最丰富）
        - suggestion: 取最长的
        - detected_by: 所有来源大脑
        """
        # 按引擎优先级排序（brain1 > brain2 > brain3 > brain4 > brain5 > brain6 > brain7）
        priority_order = {
            "brain1_rule_engine": 1,
            "brain2_security_engine": 2,
            "brain3_ai_engine": 3,
            "brain4_performance": 4,
            "brain5_deps": 5,
            "brain6_code_quality": 6,
            "brain7_architecture_engine": 7,
        }
        group.sort(key=lambda x: priority_order.get(x[0], 99))

        # 取优先级最高的作为基础
        primary_brain, primary_issue = group[0]

        # 收集所有来源
        detected_by: List[str] = []
        source_severities: Dict[str, str] = {}
        source_ids: List[str] = []
        most_severe = primary_issue.get("severity", "low")
        longest_message = primary_issue.get("message", "")
        longest_suggestion = primary_issue.get("suggestion", "")

        for brain_name, issue in group:
            if brain_name not in detected_by:
                detected_by.append(brain_name)

            sev = issue.get("severity", "low")
            source_severities[brain_name] = sev

            check_id = issue.get("check_id", "")
            if check_id and check_id not in source_ids:
                source_ids.append(check_id)

            if _severity_rank(sev) > _severity_rank(most_severe):
                most_severe = sev

            msg = issue.get("message", "")
            if len(msg) > len(longest_message):
                longest_message = msg

            sug = issue.get("suggestion", "")
            if len(sug) > len(longest_suggestion):
                longest_suggestion = sug

        return UnifiedIssue(
            check_id=primary_issue.get("check_id", "unknown"),
            name=primary_issue.get("name", primary_issue.get("check_id", "unknown")),
            severity=_normalize_severity(most_severe),
            file=primary_issue.get("file", ""),
            line=primary_issue.get("line", 0),
            message=longest_message,
            suggestion=longest_suggestion,
            category=primary_issue.get("category", ""),
            detected_by=detected_by,
            source_severities=source_severities,
            source_ids=source_ids,
        )

    def _similarity_merge_groups(
        self,
        groups: Dict[str, List[Tuple[str, Dict[str, Any]]]],
        similarity_threshold: float = 0.8,
    ) -> Dict[str, List[Tuple[str, Dict[str, Any]]]]:
        """
        [v2.0优化] 消息相似度兜底合并。

        当去重键不同但消息文本高度相似（>threshold）且属于同一文件时，
        将较小组合并到较大组中，减少因行号偏移导致的漏合并。
        """
        try:
            keys = list(groups.keys())
            merged_keys: Dict[str, str] = {}  # old_key -> target_key

            for i, k1 in enumerate(keys):
                if k1 in merged_keys:
                    continue
                for k2 in keys[i+1:]:
                    if k2 in merged_keys:
                        continue
                    # 取各组第一条消息做比较
                    msg1 = groups[k1][0][1].get("message", "")
                    msg2 = groups[k2][0][1].get("message", "")
                    file1 = groups[k1][0][1].get("file", "")
                    file2 = groups[k2][0][1].get("file", "")

                    # 仅同文件的才做相似度合并
                    if file1 and file2 and os.path.normpath(file1) == os.path.normpath(file2):
                        sim = _message_similarity(msg1, msg2)
                        if sim >= similarity_threshold:
                            # 合并到较大的组
                            target = k1 if len(groups[k1]) >= len(groups[k2]) else k2
                            source = k2 if target == k1 else k1
                            groups[target].extend(groups[source])
                            merged_keys[source] = target
                            del groups[source]
        except Exception as e:  # noqa: broad exception handling
            pass  # 相似度合并失败时静默降级，不影响主流程

        return groups

    def _detect_conflicts(self, issues: List[UnifiedIssue]) -> List[Dict[str, Any]]:
        """
        检测冲突：同一问题被不同引擎给出不同严重度。

        冲突类型：
        1. 严重度冲突：一个引擎说 blocker，另一个说 low
        2. 存在性冲突：此处暂不处理（已在去重阶段合并）
        """
        conflicts = []
        for issue in issues:
            if len(issue.source_severities) <= 1:
                continue

            sevs = list(issue.source_severities.values())
            ranks = [_severity_rank(s) for s in sevs]

            if max(ranks) - min(ranks) >= 2:
                # 严重度差距 ≥ 2 级视为冲突
                conflicts.append({
                    "file": issue.file,
                    "line": issue.line,
                    "check_id": issue.check_id,
                    "severities": issue.source_severities,
                    "resolved_as": issue.severity,
                })

        return conflicts


# =============================================================================
# 便捷函数
# =============================================================================

def aggregate_results(
    brain_results: Dict[str, Any],
    line_tolerance: int = 3,
) -> AggregationResult:
    """
    快速聚合大脑结果。

    Args:
        brain_results: {brain_name: BrainResult_or_dict}
        line_tolerance: 行号容忍范围

    Returns:
        AggregationResult
    """
    aggregator = ResultAggregator(line_tolerance=line_tolerance)
    return aggregator.aggregate(brain_results)


__all__ = [
    "UnifiedIssue",
    "AggregationResult",
    "ResultAggregator",
    "aggregate_results",
]
