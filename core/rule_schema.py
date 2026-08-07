# -*- coding: utf-8 -*-
"""
规则类型分类器 - 煋鉴 v3.0.2 规则架构重构
煋旺智能 / Xinpect

将混合规则按类型分类为不同执行引擎：
- REGEX: 有可执行正则 pattern → 规则引擎（Brain 1）
- SEMGREP: 有 semgrep 标识 → Semgrep 引擎（Brain 6）
- SEMANTIC: 无语义描述规则 → 对应大脑知识库（Brain 2/3/4/5/7）

v3.0.2 第一台手术：规则架构重构
"""

import re
from enum import Enum
from typing import Dict, Any, Optional, Tuple


class RuleType(Enum):
    """规则执行类型"""
    REGEX = "regex"          # 正则匹配规则 → Brain 1 规则引擎
    SEMGREP = "semgrep"      # Semgrep SAST规则 → Brain 6 代码质量引擎
    SEMANTIC = "semantic"    # 语义描述规则 → 对应大脑知识库


# 规则目录 → 大脑编号 映射
DIR_TO_BRAIN = {
    "brain2_security": "2",
    "brain3_semantic": "3",
    "brain4_performance": "4",
    "brain5_deps": "5",
    "brain6_code_quality": "6",
    "brain7_architecture": "7",
    # 非brain目录的默认映射
    "security": "2",
    "common": "1",
    "distribution_security": "2",
    "supply_chain": "2",
    "ci_cd": "2",
    "async_concurrency": "3",
    "biz_logic": "3",
    "config_deploy": "5",
    "data_flow": "3",
    "dep_chain": "5",
    "error_quality": "3",
    "performance": "4",
    # 语言目录 → Brain 1（通用规则引擎）
    "java": "1",
    "go": "1",
    "python": "1",
    "rust": "1",
    "cpp": "1",
    "csharp": "1",
    "php": "1",
    "ruby": "1",
    "swift": "1",
    "kotlin": "1",
    "web": "1",
    "flutter": "1",
    "electron": "1",
    "react_native": "1",
}


class RuleSchema:
    """规则类型验证与分类器"""

    @staticmethod
    def classify_rule(rule_def: Dict[str, Any]) -> RuleType:
        """
        根据规则字段判断执行类型
        
        判定优先级：
        1. 有非空 pattern → REGEX
        2. 有 semgrep_id 或 semgrep_rule → SEMGREP
        3. 其他（有 description/name 但无 pattern）→ SEMANTIC
        """
        if not isinstance(rule_def, dict):
            return RuleType.SEMANTIC

        # 检查1: 是否有可执行正则
        pattern = rule_def.get("pattern", "")
        if pattern and isinstance(pattern, str) and pattern.strip():
            # 验证是否为合法正则
            try:
                re.compile(pattern)
                return RuleType.REGEX
            except re.error:
                # pattern存在但不合法，仍视为REGEX（由执行引擎处理错误）
                return RuleType.REGEX

        # 检查2: 是否有semgrep标识
        # 多信号检测：detection_pattern字段、semgrep_*字段、ID以-semg结尾
        if (rule_def.get("detection_pattern") or
            rule_def.get("semgrep_id") or 
            rule_def.get("semgrep_rule") or 
            rule_def.get("semgrep_rule_id")):
            return RuleType.SEMGREP
        
        # ID后缀检测（如 SEC-001-semg）
        rule_id = rule_def.get("id", rule_def.get("check_id", ""))
        if rule_id and rule_id.lower().endswith("-semg"):
            return RuleType.SEMGREP

        # 检查3: 其余为语义规则
        return RuleType.SEMANTIC

    @staticmethod
    def get_brain_id(rule_def: Dict[str, Any], source_dir: str = "") -> str:
        """
        根据规则来源目录推断目标大脑编号
        """
        # 优先从source_dir推断
        if source_dir and source_dir in DIR_TO_BRAIN:
            return DIR_TO_BRAIN[source_dir]
        
        # 备用：从check_id前缀推断
        check_id = rule_def.get("check_id", rule_def.get("id", ""))
        if check_id:
            prefix = check_id.split("-")[0].upper()
            id_to_brain = {
                "SEC": "2", "B2": "2", "B3": "3", "B4": "4",
                "B5": "5", "B6": "6", "B7": "7",
                "PERF": "4", "DEP": "5", "ARCH": "7",
            }
            if prefix in id_to_brain:
                return id_to_brain[prefix]
        
        return "1"  # 默认归Brain 1

    @staticmethod
    def validate_rule(rule_def: Dict[str, Any]) -> Tuple[RuleType, str]:
        """
        完整验证规则，返回 (类型, 目标大脑)
        """
        rule_type = RuleSchema.classify_rule(rule_def)
        return rule_type, ""
