# -*- coding: utf-8 -*-
"""
煋鉴 v2.0 - 全局常量定义
========================

统一各模块重复定义的严重度排序、映射等常量，确保单一数据源。

v2.0 优化：将原先分散在 result_aggregator.py、brains/cli.py、dedup_engine.py 等
4 处的 SEVERITY_ORDER 统一收敛到此文件。
"""

# =============================================================================
# 严重度排序（数值越大越严重）
# =============================================================================
SEVERITY_ORDER = {
    "blocker": 4,
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
    "info": 0,
    # 兼容 S1~S4 旧格式
    "S1": 4,
    "S2": 3,
    "S3": 2,
    "S4": 1,
}

# 严重度升序排列（用于排序，数值越小越严重）
SEVERITY_SORT_ASC = {
    "blocker": 0,
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "info": 4,
    "S1": 0,
    "S2": 1,
    "S3": 2,
    "S4": 3,
}

# 严重度统一映射（将各种写法统一为标准名称）
SEVERITY_NORMALIZE = {
    "S1": "blocker",
    "S2": "high",
    "S3": "medium",
    "S4": "low",
    "critical": "blocker",
}

# =============================================================================
# 自适应去重容忍范围（按问题类型）
# =============================================================================
DEDUP_LINE_TOLERANCE = {
    "security": 1,        # 安全类问题：精确定位
    "安全": 1,
    "performance": 5,     # 性能类问题：函数级粒度较粗
    "性能": 5,
    "default": 3,         # 默认容忍范围
}

# =============================================================================
# 契约系统 - 动态阈值基准
# =============================================================================
CONTRACT_THRESHOLDS = {
    "small": {     # 文件数 < 50
        "brain1": 0.7,   # 规则引擎
        "brain2": 0.75,  # 安全扫描（规则引擎，高精度）
        "brain3": 0.7,   # 性能分析
        "brain4": 0.7,   # 依赖审计
        "brain5": 0.6,   # UI审查
        "brain6": 0.5,   # AI语义（LLM，低精度）
        "brain7": 0.65,  # 架构检查
    },
    "medium": {    # 文件数 50~200
        "brain1": 0.65,
        "brain2": 0.7,
        "brain3": 0.65,
        "brain4": 0.65,
        "brain5": 0.55,
        "brain6": 0.45,
        "brain7": 0.6,
    },
    "large": {     # 文件数 > 200
        "brain1": 0.6,
        "brain2": 0.65,
        "brain3": 0.6,
        "brain4": 0.6,
        "brain5": 0.5,
        "brain6": 0.4,
        "brain7": 0.55,
    },
}


def severity_rank(sev: str) -> int:
    """获取严重度排名（越高越严重）"""
    return SEVERITY_ORDER.get(sev, 0)


def severity_rank_asc(sev: str) -> int:
    """获取严重度排名（越低越严重，用于升序排序）"""
    return SEVERITY_SORT_ASC.get(sev, 99)


def normalize_severity(sev: str) -> str:
    """统一严重度表示"""
    return SEVERITY_NORMALIZE.get(sev, sev)


def get_dedup_tolerance(category: str = "") -> int:
    """根据问题类型获取自适应去重行号容忍范围"""
    if not category:
        return DEDUP_LINE_TOLERANCE["default"]
    cat_lower = category.lower()
    for key, tolerance in DEDUP_LINE_TOLERANCE.items():
        if key != "default" and key in cat_lower:
            return tolerance
    return DEDUP_LINE_TOLERANCE["default"]


def get_dynamic_threshold(brain_id: str, file_count: int) -> float:
    """根据项目规模动态获取契约阈值"""
    if file_count < 50:
        scale = "small"
    elif file_count <= 200:
        scale = "medium"
    else:
        scale = "large"
    thresholds = CONTRACT_THRESHOLDS.get(scale, CONTRACT_THRESHOLDS["small"])
    return thresholds.get(str(brain_id), 0.6)


__all__ = [
    "SEVERITY_ORDER",
    "SEVERITY_SORT_ASC",
    "SEVERITY_NORMALIZE",
    "DEDUP_LINE_TOLERANCE",
    "CONTRACT_THRESHOLDS",
    "severity_rank",
    "severity_rank_asc",
    "normalize_severity",
    "get_dedup_tolerance",
    "get_dynamic_threshold",
]
