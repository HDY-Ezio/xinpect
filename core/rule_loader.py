"""
规则加载器 — 向后兼容入口
=============================

已拆分为 core.rule_loader 子包，本文件保留原导入路径不变。

新代码请使用:
    from core.rule_loader import RuleLoader
"""

from core.rule_loader import (
    Rule,
    RuleCheckResult,
    RuleLoader,
    _get_semantic_scanner_registered_categories,
)

__all__ = [
    "Rule",
    "RuleCheckResult",
    "RuleLoader",
]
