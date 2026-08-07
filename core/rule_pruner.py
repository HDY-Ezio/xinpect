#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
规则智能裁剪引擎 (RulePruner) - 煋鉴 v4.2

在 RuleLoader 和 RuleRunner 之间加一层裁剪层：
根据项目类型 + 检测到的语言/框架，智能裁剪规则集，减少无效扫描。

设计原则：
- 保守裁剪：不确定的规则保留，宁可多扫不能漏扫
- 跨语言通用规则（common/security 等）全部保留
- 仅针对明确语言绑定的目录进行过滤

煋旺智能 / Xinpect
"""

import os
import logging
from typing import Dict, List, Set, Optional, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)


# ====================================================================
# 规则目录 → 适用语言/框架 映射表
# ====================================================================
# key: 规则目录名 (rules/ 下的一级目录)
# value: set of applicable language tags
# 空集合 = 跨语言通用，不过滤
# 有值 = 仅当项目检测到对应语言时保留

DIR_LANG_MAP: Dict[str, Set[str]] = {
    # --- 语言专属目录 ---
    "python": {"python"},
    "java": {"java"},
    "go": {"go"},
    "rust": {"rust"},
    "cpp": {"cpp", "c"},
    "swift": {"swift", "ios"},
    "kotlin": {"kotlin", "android"},
    "flutter": {"dart", "flutter"},
    "web": {"javascript", "html", "css", "typescript"},
    "miniprogram": {"javascript", "wxml", "wxss"},
    "electron": {"javascript", "electron"},
    "react_native": {"javascript", "react_native"},

    # --- 大脑目录：按规则内容判定语言相关性 ---
    # brain2_security: 安全规则大部分跨语言，保留通用，按文件后缀过滤更细
    "brain2_security": set(),  # 通用安全，不过滤

    # brain3_semantic: 语义规则，分语言判断
    "brain3_semantic": set(),  # 保守：先不过滤，内部按applicable_files判断

    # brain4_performance: 性能规则
    "brain4_performance": set(),  # 保守：先不过滤

    # brain5_deps: 依赖规则，按项目语言走
    "brain5_deps": set(),  # 保守：不过滤（依赖检查按package manager自动适配）

    # brain6_code_quality: 代码质量规则
    "brain6_code_quality": set(),  # 保守：不过滤

    # brain7_architecture: 架构规则
    "brain7_architecture": set(),  # 通用架构，不过滤

    # --- 通用目录 ---
    "common": set(),  # 通用规则，不过滤
    "security": set(),  # 安全通用，不过滤

    # --- 其它业务目录（跨语言或待细化）---
    "async_concurrency": set(),
    "biz_logic": set(),
    "ci_cd": set(),
    "config_deploy": set(),
    "data_flow": set(),
    "dep_chain": set(),
    "distribution_security": set(),
    "error_quality": set(),
    "performance": set(),
    "supply_chain": set(),
}


# 文件后缀 → 语言标签 映射
EXT_TO_LANG: Dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "css",
    ".less": "css",
    ".wxml": "wxml",
    ".wxss": "wxss",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".swift": "swift",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".dart": "dart",
    ".cs": "csharp",
    ".php": "php",
    ".rb": "ruby",
    ".vue": "vue",
}


# 项目类型 → 语言集合 映射（从QAContext.project_type快速推导）
PROJECT_TYPE_LANGS: Dict[str, Set[str]] = {
    "miniprogram": {"javascript", "wxml", "wxss", "json"},
    "web": {"javascript", "html", "css", "typescript"},
    "python": {"python"},
    "python_backend": {"python"},
    "python_tool": {"python"},
    "flask": {"python"},
    "electron": {"javascript", "html", "css"},
    "skill": {"javascript", "python"},  # 扣子技能可能两者都有
    "agent": {"javascript", "python"},
    "mixed": {"python", "javascript", "html", "css", "typescript"},
    "mixed_electron": {"python", "javascript", "html", "css"},
    "unknown": set(),  # 未知类型不过滤
}


class RulePruner:
    """规则智能裁剪引擎

    根据项目类型 + 检测到的语言/框架，智能裁剪规则集。
    在 RuleLoader 和 RuleRunner 之间作为中间层。

    裁剪策略（保守）：
    1. 通用规则目录（common/security 等）→ 全部保留
    2. 语言专属目录（python/web/kotlin 等）→ 匹配语言才保留
    3. 语义/大脑目录 → 保守保留（内部有自己的applicable_files判断）
    4. _reference 目录已在 RuleLoader 层过滤，这里不重复处理
    """

    def __init__(self, context=None):
        """
        Args:
            context: QAContext 实例，用于获取项目类型和文件信息
        """
        self.context = context

        # 检测到的项目语言集合
        self._detected_langs: Set[str] = set()

        # 检测到的框架集合
        self._detected_frameworks: Set[str] = set()

        # 裁剪统计
        self._stats = {
            "original_regex": 0,
            "pruned_regex": 0,
            "original_semgrep": 0,
            "pruned_semgrep": 0,
            "original_semantic": 0,
            "pruned_semantic": 0,
            "by_lang": defaultdict(int),  # 按语言维度裁剪的数量
            "by_dir": defaultdict(int),   # 按目录维度裁剪的数量
        }

        # 自动检测
        self._detect()

    # ------------------------------------------------------------------
    # 语言/框架检测
    # ------------------------------------------------------------------

    def _detect(self):
        """检测项目语言和框架"""
        if self.context is None:
            return

        # 方式1: 从 project_type 推导
        pt = getattr(self.context, 'project_type', 'unknown')
        if pt in PROJECT_TYPE_LANGS:
            self._detected_langs.update(PROJECT_TYPE_LANGS[pt])

        # 方式2: 扫描文件后缀（更精确）
        try:
            if hasattr(self.context, 'find_files'):
                all_exts = list(EXT_TO_LANG.keys())
                files = self.context.find_files(all_exts)
                for f in files:
                    _, ext = os.path.splitext(f)
                    ext = ext.lower()
                    if ext in EXT_TO_LANG:
                        self._detected_langs.add(EXT_TO_LANG[ext])
        except Exception:
            pass

        # 方式3: 从 project_profile 补充
        profile = getattr(self.context, 'project_profile', None)
        if profile:
            if getattr(profile, 'has_typescript', False):
                self._detected_langs.add('typescript')
            if getattr(profile, 'has_vue', False):
                self._detected_langs.add('vue')
                self._detected_frameworks.add('vue')
            if getattr(profile, 'has_react', False):
                self._detected_frameworks.add('react')
            if getattr(profile, 'has_flask', False):
                self._detected_frameworks.add('flask')

        # 方式4: 从context已知标志补充
        for flag_attr, lang_tag in [
            ('has_django', 'django'),
            ('has_fastapi', 'fastapi'),
        ]:
            if getattr(self.context, flag_attr, False):
                self._detected_frameworks.add(lang_tag.replace('has_', ''))

        logger.debug("[RulePruner] 检测到语言: %s, 框架: %s",
                     sorted(self._detected_langs), sorted(self._detected_frameworks))

    @property
    def detected_languages(self) -> Set[str]:
        """返回检测到的语言集合"""
        return set(self._detected_langs)

    @property
    def detected_frameworks(self) -> Set[str]:
        """返回检测到的框架集合"""
        return set(self._detected_frameworks)

    # ------------------------------------------------------------------
    # 目录级裁剪判定
    # ------------------------------------------------------------------

    def _should_keep_dir(self, dir_name: str) -> Tuple[bool, str]:
        """判断某个规则目录是否应该保留

        Returns:
            (should_keep: bool, reason: str)
        """
        # 未知目录：保守保留
        if dir_name not in DIR_LANG_MAP:
            return True, "unknown_dir_conservative"

        required_langs = DIR_LANG_MAP[dir_name]

        # 空集合 = 通用目录，保留
        if not required_langs:
            return True, "universal_category"

        # 未知语言项目：保留所有（保守）
        if not self._detected_langs:
            return True, "unknown_project_language"

        # 检查语言交集
        intersection = required_langs & self._detected_langs
        if intersection:
            return True, f"lang_match:{','.join(sorted(intersection))}"

        return False, f"lang_mismatch:need_{','.join(sorted(required_langs))}"

    # ------------------------------------------------------------------
    # 规则级裁剪（REGEX 规则）
    # ------------------------------------------------------------------

    def _should_keep_rule(self, rule) -> Tuple[bool, str]:
        """判断单条 REGEX 规则是否应该保留

        先看来源目录，再看规则自身的applicable_files等精细条件
        """
        # v4.2: 优先使用 source_dir（规则来源目录），回退到 category
        source_dir = getattr(rule, 'source_dir', '') or getattr(rule, 'category', '') or ''
        is_json = getattr(rule, 'is_json_rule', False)

        # 目录级判断
        keep_dir, reason_dir = self._should_keep_dir(source_dir)
        if not keep_dir:
            return False, reason_dir

        # 规则自身有 applicable_types 的，二次确认
        applicable_types = getattr(rule, 'applicable_types', None)
        if applicable_types and isinstance(applicable_types, list) and len(applicable_types) > 0:
            pt = getattr(self.context, 'project_type', '')
            # v4.2.1: 若 source_dir 已通过语言匹配，跳过 project_type 精细检查
            # 因为规则定义时 project_type 枚举可能不全（如只有 python_backend，没有 python）
            # 但目录级语言检测已经确认项目是 Python 项目
            if source_dir in DIR_LANG_MAP:
                # source_dir 已有明确的语言要求，已通过语言检测，不再二次检查 project_type
                pass
            elif pt and pt not in applicable_types:
                return False, f"project_type_mismatch:{pt}"

        # JSON规则：根据file_pattern进一步精细判断
        if is_json:
            # 有 file_pattern 但项目没有匹配后缀的文件 → 可以跳过
            pass  # 保守：不做精细裁剪，规则执行时会自己过滤文件

        return True, "kept"

    # ------------------------------------------------------------------
    # 主入口：裁剪 REGEX 规则列表
    # ------------------------------------------------------------------

    def prune(self, rules: list) -> list:
        """裁剪 REGEX 规则列表

        Args:
            rules: Rule 对象列表（来自 RuleLoader）

        Returns:
            裁剪后的规则列表
        """
        self._stats["original_regex"] = len(rules)

        if not self._detected_langs:
            # 检测不到语言，不裁剪（安全兜底）
            self._stats["pruned_regex"] = len(rules)
            logger.info("[RulePruner] 未检测到项目语言，跳过规则裁剪（保留全部 %d 条）", len(rules))
            return list(rules)

        pruned = []
        for rule in rules:
            keep, reason = self._should_keep_rule(rule)
            if keep:
                pruned.append(rule)
            else:
                # 统计
                self._stats["by_dir"][getattr(rule, 'source_dir', '') or getattr(rule, 'category', 'unknown')] += 1
                if "lang_mismatch" in reason:
                    self._stats["by_lang"]["language_filter"] += 1
                elif "project_type" in reason:
                    self._stats["by_lang"]["project_type_filter"] += 1

        self._stats["pruned_regex"] = len(pruned)
        removed = self._stats["original_regex"] - self._stats["pruned_regex"]
        logger.info("[RulePruner] REGEX规则裁剪: %d → %d (裁剪 %d 条, %.1f%%)",
                    self._stats["original_regex"], self._stats["pruned_regex"],
                    removed,
                    removed / self._stats["original_regex"] * 100
                    if self._stats["original_regex"] else 0)
        return pruned

    # ------------------------------------------------------------------
    # SEMGREP 规则裁剪
    # ------------------------------------------------------------------

    def prune_semgrep_rules(self, semgrep_rules: List[dict]) -> List[dict]:
        """裁剪 SEMGREP 规则列表

        Args:
            semgrep_rules: semgrep规则原始dict列表

        Returns:
            裁剪后的规则列表
        """
        self._stats["original_semgrep"] = len(semgrep_rules)

        if not self._detected_langs:
            self._stats["pruned_semgrep"] = len(semgrep_rules)
            return list(semgrep_rules)

        pruned = []
        for rule in semgrep_rules:
            source_dir = rule.get("_source_dir", "")
            keep, _ = self._should_keep_dir(source_dir)

            # Semgrep规则还有language字段，可以更精细
            rule_lang = rule.get("language", "")
            if rule_lang and rule_lang.lower() not in ("generic", "regex"):
                # 有明确语言的，进一步匹配
                lang_tag = rule_lang.lower()
                lang_aliases = {
                    "python": {"python"},
                    "javascript": {"javascript", "typescript"},
                    "typescript": {"typescript", "javascript"},
                    "java": {"java"},
                    "go": {"go"},
                    "rust": {"rust"},
                    "c": {"c", "cpp"},
                    "cpp": {"cpp", "c"},
                }
                acceptable = lang_aliases.get(lang_tag, {lang_tag})
                if not (acceptable & self._detected_langs):
                    keep = False
                    self._stats["by_lang"]["semgrep_lang_filter"] += 1

            if keep:
                pruned.append(rule)
            else:
                self._stats["by_dir"][source_dir or "unknown"] += 1

        self._stats["pruned_semgrep"] = len(pruned)
        return pruned

    # ------------------------------------------------------------------
    # SEMANTIC 规则裁剪
    # ------------------------------------------------------------------

    def prune_semantic_rules(self, semantic_rules: Dict[str, list]) -> Dict[str, list]:
        """裁剪 SEMANTIC 规则字典

        Args:
            semantic_rules: {brain_id: [rule_dict, ...]}

        Returns:
            裁剪后的规则字典
        """
        total = sum(len(v) for v in semantic_rules.values())
        self._stats["original_semantic"] = total

        if not self._detected_langs:
            self._stats["pruned_semantic"] = total
            return {k: list(v) for k, v in semantic_rules.items()}

        pruned = {}
        for brain_id, rules in semantic_rules.items():
            kept = []
            for rule in rules:
                source_dir = rule.get("_source_dir", "")
                keep, _ = self._should_keep_dir(source_dir)

                # 语义规则有 applicable_files 的，再精细判断
                app_files = rule.get("applicable_files", [])
                if app_files and isinstance(app_files, list) and len(app_files) > 0:
                    # 如果applicable_files里的后缀都不在检测语言中，可以考虑跳过
                    # 保守策略：仅当所有 pattern 都是明确非当前语言时才裁剪
                    pass  # 保守保留

                if keep:
                    kept.append(rule)
                else:
                    self._stats["by_dir"][source_dir or "unknown"] += 1

            if kept:
                pruned[brain_id] = kept

        pruned_total = sum(len(v) for v in pruned.values())
        self._stats["pruned_semantic"] = pruned_total
        return pruned

    # ------------------------------------------------------------------
    # 统计信息
    # ------------------------------------------------------------------

    def get_prune_stats(self) -> dict:
        """返回裁剪统计信息

        Returns:
            dict with keys:
            - original_regex / pruned_regex
            - original_semgrep / pruned_semgrep
            - original_semantic / pruned_semantic
            - total_original / total_pruned / total_removed
            - detected_languages / detected_frameworks
            - by_lang / by_dir (裁剪维度明细)
        """
        total_orig = (self._stats["original_regex"] +
                      self._stats["original_semgrep"] +
                      self._stats["original_semantic"])
        total_pruned = (self._stats["pruned_regex"] +
                        self._stats["pruned_semgrep"] +
                        self._stats["pruned_semantic"])
        return {
            "original_regex": self._stats["original_regex"],
            "pruned_regex": self._stats["pruned_regex"],
            "original_semgrep": self._stats["original_semgrep"],
            "pruned_semgrep": self._stats["pruned_semgrep"],
            "original_semantic": self._stats["original_semantic"],
            "pruned_semantic": self._stats["pruned_semantic"],
            "total_original": total_orig,
            "total_pruned": total_pruned,
            "total_removed": total_orig - total_pruned,
            "prune_ratio": (total_orig - total_pruned) / total_orig if total_orig else 0,
            "detected_languages": sorted(self._detected_langs),
            "detected_frameworks": sorted(self._detected_frameworks),
            "by_lang": dict(self._stats["by_lang"]),
            "by_dir": dict(self._stats["by_dir"]),
        }
