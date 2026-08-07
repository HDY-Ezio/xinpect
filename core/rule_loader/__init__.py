# -*- coding: utf-8 -*-
"""
规则加载器子包

从 rule_loader.py 拆分而来，保持向后兼容。
"""

from core.rule_loader.models import Rule, RuleCheckResult
from core.rule_loader.loader import (
    RuleLoader,
    _get_semantic_scanner_registered_categories,
    safe_regex_finditer,
    get_regex_timeout_stats,
    reset_regex_timeout_stats,
    DEFAULT_REGEX_TIMEOUT,
    SLOW_RULE_THRESHOLD_MS,
)

__all__ = [
    "Rule",
    "RuleCheckResult",
    "RuleLoader",
    "_get_semantic_scanner_registered_categories",
    "safe_regex_finditer",
    "get_regex_timeout_stats",
    "reset_regex_timeout_stats",
    "DEFAULT_REGEX_TIMEOUT",
    "SLOW_RULE_THRESHOLD_MS",
]
