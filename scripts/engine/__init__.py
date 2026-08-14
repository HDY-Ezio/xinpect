# -*- coding: utf-8 -*-
"""
煋鉴代码质检引擎（免费版 v5.9.0）
7 个检测引擎，多进程并行扫描架构
"""

from .scoring import calculate_weighted_score, generate_summary, calculate_overall_score
from .parallel_runner import run_brains_parallel, DEFAULT_FREE_BRAINS, BRAIN_NAMES

__all__ = [
    "calculate_weighted_score",
    "generate_summary",
    "calculate_overall_score",
    "run_brains_parallel",
    "DEFAULT_FREE_BRAINS",
    "BRAIN_NAMES",
]

__version__ = "5.9.0"
