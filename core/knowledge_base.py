# -*- coding: utf-8 -*-
"""
跨项目知识库 (Knowledge Base)
章鱼架构 v2.0 - 模块8

v3 - 按3S骨架优化拆分：
- 数据模型（Pattern/ProjectProfile/RuleSuggestion）→ core.knowledge.base
- 误报反馈子系统 → core.knowledge.fp_feedback
- 主类 KnowledgeBase 保留在此（向后兼容）

三层结构：
1. 问题模式库 (Pattern)     - 记录反复出现的问题模式，按代码上下文匹配
2. 项目画像 (Profile)       - 技术栈/常见问题分布/质量趋势
3. 规则建议 (RuleSuggestion)- 基于历史数据发现值得固化为规则的模式

存储后端：JSON 文件（可后续扩展到 SQLite/Redis）
"""

import os
import re
import fnmatch
from typing import Any, Dict, List, Optional, Set, Tuple
from datetime import datetime
from collections import defaultdict

# 从拆分模块导入数据模型和存储类
from core.knowledge.base import (
    Pattern,
    ProjectProfile,
    RuleSuggestion,
    _KBStorage,
)
from core.knowledge.fp_feedback import FalsePositiveFeedback


# =============================================================================
# 知识库主类
# =============================================================================

class KnowledgeBase:
    """
    跨项目知识库。

    三层结构：
    1. 问题模式库 (Pattern)     - 记录反复出现的问题模式
    2. 项目画像 (Profile)       - 技术栈/问题分布/质量趋势
    3. 规则建议 (RuleSuggestion)- 基于历史数据的规则建议

    数据通过 JSON 文件持久化，支持跨项目共享。

    [v2.0优化] 新增功能：
    - 倒排索引：按 category 和 language 建立索引，加速 find_patterns 查询
    - 联动降误报：历史误报记录辅助过滤，减少重复误报

    [v3.0拆分] 误报反馈逻辑委托给 FalsePositiveFeedback 子系统
    """

    # 规则建议阈值
    RULE_SUGGESTION_THRESHOLD = 10         # 出现 N+ 次的问题模式 → 建议写规则
    WHITELIST_SUGGESTION_THRESHOLD = 5     # 出现 N+ 次的误报 → 建议加白名单
    MIN_CONFIDENCE = 0.5                   # 最低建议置信度

    def __init__(
        self,
        project_id: str = "global",
        storage_dir: Optional[str] = None,
    ):
        """
        Args:
            project_id: 项目标识（"global" 表示全局知识库）
            storage_dir: 存储目录（默认 .qa_history/knowledge/）
        """
        self.project_id = project_id

        if storage_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            storage_dir = os.path.join(base_dir, ".qa_history", "knowledge")
        self._storage = _KBStorage(storage_dir)

        # 加载数据
        self._patterns: Dict[str, Pattern] = self._load_patterns()
        self._profiles: Dict[str, ProjectProfile] = self._load_profiles()
        self._suggestions: List[RuleSuggestion] = []

        # [v2.0优化] 倒排索引：category -> set(pattern_id), language -> set(pattern_id)
        self._category_index: Dict[str, Set[str]] = defaultdict(set)
        self._language_index: Dict[str, Set[str]] = defaultdict(set)
        self._build_inverted_indices()

        # [v3.0拆分] 误报反馈子系统（委托模式）
        self._fp_feedback = FalsePositiveFeedback(self._storage)

    # ==================================================================
    # [v2.0优化] 倒排索引
    # ==================================================================

    def _build_inverted_indices(self) -> None:
        """构建倒排索引：按 category 和 language 建立 pattern_id 索引。"""
        try:
            self._category_index.clear()
            self._language_index.clear()
            for pid, p in self._patterns.items():
                if p.category:
                    self._category_index[p.category].add(pid)
                if p.language:
                    self._language_index[p.language].add(pid)
        except Exception:  # noqa: broad exception handling
            pass  # 索引构建失败不影响核心功能

    def _rebuild_index_for_pattern(self, pattern: Pattern) -> None:
        """增量更新单个 pattern 的倒排索引。"""
        try:
            pid = pattern.pattern_id
            if pattern.category:
                self._category_index[pattern.category].add(pid)
            if pattern.language:
                self._language_index[pattern.language].add(pid)
        except Exception:  # noqa: broad exception handling
            pass

    # ==================================================================
    # 误报反馈（委托给 FalsePositiveFeedback）
    # ==================================================================

    def record_false_positive(self, file_path: str, check_id_or_category: str) -> None:
        """记录一次误报（委托）。"""
        self._fp_feedback.record(file_path, check_id_or_category)

    def analyze_qa_ignore_frequency(self, project_path: str) -> Dict[str, int]:
        """分析项目中 qa-ignore 注释的使用频率（委托静态方法）。"""
        return FalsePositiveFeedback.analyze_qa_ignore_frequency(project_path)

    def get_high_false_positive_rules(self, threshold: int = 5) -> List[str]:
        """获取高误报率规则列表（委托）。"""
        return self._fp_feedback.get_high_fp_rules(threshold)

    def compute_issue_survival_rate(self, previous_issues: Dict, current_issues: Dict) -> Dict[str, float]:
        """计算问题存活率（委托静态方法）。"""
        return FalsePositiveFeedback.compute_issue_survival_rate(previous_issues, current_issues)

    def get_fp_feedback_summary(self, project_path: str = None) -> Dict[str, Any]:
        """生成误报反馈摘要（委托）。"""
        return self._fp_feedback.get_feedback_summary(project_path)

    def is_likely_false_positive(self, file_path: str, check_id_or_category: str,
                                  threshold: int = 3) -> bool:
        """判断某问题是否可能是误报（委托）。"""
        return self._fp_feedback.is_likely_false_positive(file_path, check_id_or_category, threshold)

    def get_false_positive_score(self, file_path: str, check_id_or_category: str) -> int:
        """获取某文件+规则组合的历史误报次数（委托）。"""
        return self._fp_feedback.get_score(file_path, check_id_or_category)

    # ==================================================================
    # 层1：问题模式库
    # ==================================================================

    def record_pattern(
        self,
        pattern_id: str,
        description: str,
        category: str = "",
        severity: str = "medium",
        file_pattern: str = "",
        code_pattern: str = "",
        language: str = "",
        example_file: str = "",
        example_line: int = 0,
        fix_suggestion: str = "",
        tags: Optional[List[str]] = None,
    ) -> Pattern:
        """
        记录一个问题模式。

        如果模式已存在，则更新出现次数和最近发现时间。
        """
        now = datetime.now().isoformat()
        
        if pattern_id in self._patterns:
            pattern = self._patterns[pattern_id]
            pattern.occurrence_count += 1
            pattern.last_seen = now
            if self.project_id not in pattern.affected_projects:
                pattern.affected_projects.append(self.project_id)
            # 更新示例（用最新的）
            if example_file:
                pattern.example_file = example_file
                pattern.example_line = example_line
        else:
            pattern = Pattern(
                pattern_id=pattern_id,
                description=description,
                category=category,
                severity=severity,
                file_pattern=file_pattern,
                code_pattern=code_pattern,
                language=language,
                occurrence_count=1,
                first_seen=now,
                last_seen=now,
                affected_projects=[self.project_id],
                example_file=example_file,
                example_line=example_line,
                fix_suggestion=fix_suggestion,
                tags=tags or [],
            )
            self._patterns[pattern_id] = pattern
            self._rebuild_index_for_pattern(pattern)

        self._save_patterns()
        return pattern

    def find_patterns(
        self,
        file_path: str = "",
        language: str = "",
        category: str = "",
        code_content: str = "",
        limit: int = 20,
    ) -> List[Pattern]:
        """
        查找匹配的问题模式。

        Args:
            file_path: 文件路径（用 file_pattern 匹配）
            language: 编程语言过滤
            category: 分类过滤
            code_content: 代码内容（用 code_pattern 正则匹配）
            limit: 返回结果上限

        Returns:
            匹配的 Pattern 列表，按出现次数降序
        """
        # 先用倒排索引缩小范围
        candidate_ids: Optional[Set[str]] = None
        
        if category:
            cat_ids = self._category_index.get(category, set())
            candidate_ids = set(cat_ids)
        
        if language:
            lang_ids = self._language_index.get(language, set())
            if candidate_ids is None:
                candidate_ids = set(lang_ids)
            else:
                candidate_ids = candidate_ids & lang_ids

        # 收集候选模式
        if candidate_ids is not None:
            candidates = [self._patterns[pid] for pid in candidate_ids if pid in self._patterns]
        else:
            candidates = list(self._patterns.values())

        # 文件路径匹配
        if file_path:
            matched = []
            for p in candidates:
                if not p.file_pattern:
                    continue
                # glob 匹配
                if fnmatch.fnmatch(file_path, p.file_pattern):
                    matched.append(p)
                # 也检查相对路径匹配
                elif fnmatch.fnmatch(os.path.basename(file_path), p.file_pattern):
                    matched.append(p)
            candidates = matched

        # 代码内容匹配
        if code_content:
            matched = []
            for p in candidates:
                if not p.code_pattern:
                    continue
                try:
                    if re.search(p.code_pattern, code_content):
                        matched.append(p)
                except re.error:
                    continue
            candidates = matched

        # 按出现次数降序
        candidates.sort(key=lambda p: p.occurrence_count, reverse=True)
        return candidates[:limit]

    def get_pattern(self, pattern_id: str) -> Optional[Pattern]:
        """根据ID获取模式。"""
        return self._patterns.get(pattern_id)

    def list_patterns(
        self,
        category: str = "",
        language: str = "",
        limit: int = 100,
    ) -> List[Pattern]:
        """列出所有模式。"""
        patterns = list(self._patterns.values())
        
        if category:
            patterns = [p for p in patterns if p.category == category]
        if language:
            patterns = [p for p in patterns if p.language == language]
        
        patterns.sort(key=lambda p: p.occurrence_count, reverse=True)
        return patterns[:limit]

    def pattern_count(self) -> int:
        """模式总数。"""
        return len(self._patterns)

    # ==================================================================
    # 层2：项目画像
    # ==================================================================

    def build_profile(
        self,
        tech_stack: Optional[List[str]] = None,
        languages: Optional[List[str]] = None,
        frameworks: Optional[List[str]] = None,
        total_files: int = 0,
        total_issues: int = 0,
        severity_distribution: Optional[Dict[str, int]] = None,
        category_distribution: Optional[Dict[str, int]] = None,
        common_issue_files: Optional[List[str]] = None,
        score: float = 0.0,
    ) -> ProjectProfile:
        """
        构建或更新项目画像。

        Args:
            tech_stack: 技术栈列表
            languages: 编程语言列表
            frameworks: 框架列表
            total_files: 文件总数
            total_issues: 历史问题总数
            severity_distribution: 严重度分布
            category_distribution: 分类分布
            common_issue_files: 高频问题文件列表
            score: 当前质量分
        """
        pid = self.project_id
        now = datetime.now().isoformat()
        
        if pid in self._profiles:
            profile = self._profiles[pid]
        else:
            profile = ProjectProfile(
                project_id=pid,
                created_at=now,
            )
            self._profiles[pid] = profile

        # 更新字段
        if tech_stack is not None:
            profile.tech_stack = tech_stack
        if languages is not None:
            profile.languages = languages
        if frameworks is not None:
            profile.frameworks = frameworks
        if total_files > 0:
            profile.total_files = total_files
        if total_issues > 0:
            profile.total_issues = total_issues
        if severity_distribution is not None:
            profile.severity_distribution = severity_distribution
        if category_distribution is not None:
            profile.category_distribution = category_distribution
        if common_issue_files is not None:
            profile.common_issue_files = common_issue_files[:20]  # 只保留 Top 20

        profile.last_reviewed = now
        profile.review_count += 1

        # 更新质量趋势
        profile.quality_trend.append({
            "date": now[:10],
            "score": round(score, 1),
            "issues": total_issues,
        })
        # 只保留最近 30 条
        if len(profile.quality_trend) > 30:
            profile.quality_trend = profile.quality_trend[-30:]

        # 更新平均分
        scores = [t["score"] for t in profile.quality_trend if t["score"] > 0]
        if scores:
            profile.avg_score = sum(scores) / len(scores)

        self._save_profiles()
        return profile

    def get_profile(self, project_id: Optional[str] = None) -> Optional[ProjectProfile]:
        """获取项目画像。"""
        pid = project_id or self.project_id
        return self._profiles.get(pid)

    def list_profiles(self) -> List[ProjectProfile]:
        """列出所有项目画像"""
        return list(self._profiles.values())

    def profile_count(self) -> int:
        """项目画像总数。"""
        return len(self._profiles)

    # ==================================================================
    # 层3：规则建议
    # ==================================================================

    def suggest_new_rules(
        self,
        min_occurrences: Optional[int] = None,
        min_whitelist_occurrences: Optional[int] = None,
    ) -> List[RuleSuggestion]:
        """
        基于历史数据发现值得固化为规则的模式。

        逻辑：
        - 出现 10+ 次的问题模式 → 建议写新规则
        - 出现 5+ 次的误报模式 → 建议加白名单
        - 某引擎在某类问题上准确率 < 0.3 → 建议调整严重度
        """
        rule_threshold = min_occurrences or self.RULE_SUGGESTION_THRESHOLD
        wl_threshold = min_whitelist_occurrences or self.WHITELIST_SUGGESTION_THRESHOLD

        suggestions: List[RuleSuggestion] = []
        now = datetime.now().isoformat()

        # 1. 高频问题模式 → 建议新规则
        for pattern in self._patterns.values():
            if pattern.occurrence_count >= rule_threshold:
                sid = f"rule_{pattern.pattern_id}"
                suggestion = RuleSuggestion(
                    suggestion_id=sid,
                    suggestion_type="new_rule",
                    title=f"将模式 [{pattern.pattern_id}] 固化为规则",
                    description=(
                        f"模式 \"{pattern.description}\" 已在 "
                        f"{pattern.occurrence_count} 次审查中出现"
                        f"（涉及 {len(pattern.affected_projects)} 个项目），"
                        f"建议固化为确定性规则以提升检测效率。"
                    ),
                    evidence_count=pattern.occurrence_count,
                    confidence=min(1.0, pattern.occurrence_count / (rule_threshold * 2)),
                    source_pattern=pattern.pattern_id,
                    suggested_rule_id=f"AUTO_{pattern.pattern_id.upper()}",
                    suggested_severity=pattern.severity,
                    affected_files=[pattern.example_file] if pattern.example_file else [],
                    created_at=now,
                )
                suggestions.append(suggestion)

        # 2. 检查项目画像中的高频误报文件 → 建议白名单
        for profile in self._profiles.values():
            for fpath in profile.common_issue_files[:5]:  # 取 Top 5
                related_patterns = [
                    p for p in self._patterns.values()
                    if p.example_file == fpath
                ]
                if len(related_patterns) >= 2:
                    total_occ = sum(p.occurrence_count for p in related_patterns)
                    if total_occ >= wl_threshold:
                        sid = f"whitelist_{hash(fpath) % 10000:04d}"
                        suggestions.append(RuleSuggestion(
                            suggestion_id=sid,
                            suggestion_type="whitelist",
                            title=f"考虑将 {fpath} 加入白名单",
                            description=(
                                f"文件 {fpath} 在 {len(related_patterns)} 个问题模式中出现，"
                                f"累计触发 {total_occ} 次。如果是误报，建议加入白名单。"
                            ),
                            evidence_count=total_occ,
                            confidence=min(1.0, total_occ / (wl_threshold * 2)),
                            affected_files=[fpath],
                            created_at=now,
                        ))

        # 3. 严重度调整建议（如果有画像数据）
        for profile in self._profiles.values():
            sev_dist = profile.severity_distribution
            total = sum(sev_dist.values()) if sev_dist else 0
            if total > 20:
                high_ratio = sev_dist.get("high", 0) / total
                if high_ratio > 0.5:
                    suggestions.append(RuleSuggestion(
                        suggestion_id=f"sev_adj_{profile.project_id}",
                        suggestion_type="severity_adjust",
                        title=f"项目 {profile.project_id} 高严重度比例偏高",
                        description=(
                            f"高严重度问题占比 {high_ratio:.0%}（共 {total} 个问题），"
                            f"可能存在严重度评估偏高的情况，建议复核。"
                        ),
                        evidence_count=total,
                        confidence=0.6,
                        created_at=now,
                    ))

        # 按置信度降序排列
        suggestions.sort(key=lambda s: s.confidence, reverse=True)
        self._suggestions = suggestions
        return suggestions

    def get_suggestions(self) -> List[RuleSuggestion]:
        """获取最新的规则建议"""
        return list(self._suggestions)

    # ==================================================================
    # 存储方法
    # ==================================================================

    def _load_patterns(self) -> Dict[str, Pattern]:
        data = self._storage.load_json("patterns.json")
        if not data:
            return {}
        return {
            pid: Pattern.from_dict(pdata)
            for pid, pdata in data.items()
        }

    def _save_patterns(self) -> None:
        data = {pid: p.to_dict() for pid, p in self._patterns.items()}
        self._storage.save_json("patterns.json", data)

    def _load_profiles(self) -> Dict[str, ProjectProfile]:
        data = self._storage.load_json("profiles.json")
        if not data:
            return {}
        return {
            pid: ProjectProfile.from_dict(pdata)
            for pid, pdata in data.items()
        }

    def _save_profiles(self) -> None:
        data = {pid: p.to_dict() for pid, p in self._profiles.items()}
        self._storage.save_json("profiles.json", data)

    def export_summary(self) -> Dict[str, Any]:
        """导出知识库摘要信息。"""
        return {
            "project_id": self.project_id,
            "pattern_count": len(self._patterns),
            "profile_count": len(self._profiles),
            "suggestion_count": len(self._suggestions),
            "fp_record_count": self._fp_feedback.total_records(),
            "high_fp_rules": self._fp_feedback.get_high_fp_rules(),
        }
