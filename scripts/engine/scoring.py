# -*- coding: utf-8 -*-
"""
统一评分与摘要生成

修复 v4.6.1 得分公式 bug：
- Blocker: 每个扣 10 分，不设上限
- High: 每个扣 5 分，不设上限
- Medium: 每个扣 3 分，最多扣 30 分
- Low: 每个扣 0.5 分，最多扣 20 分
- 最终 score = max(0, 100 - 扣分项)
"""

from collections import defaultdict
from typing import List, Dict


def calculate_weighted_score(issues: List[Dict]) -> int:
    """加权扣分 + 上限制

    Args:
        issues: issue 列表，每个 issue 含 severity 字段

    Returns:
        0~100 的整数分数
    """
    if not issues:
        return 100

    severity_counts = defaultdict(int)
    for issue in issues:
        sev = issue.get("severity", "low")
        severity_counts[sev] += 1

    # 扣分计算
    blocker_deduct = severity_counts.get("blocker", 0) * 10 + severity_counts.get("critical", 0) * 10
    high_deduct = severity_counts.get("high", 0) * 5
    medium_deduct = min(severity_counts.get("medium", 0) * 3, 30)  # 上限 30
    low_deduct = min(severity_counts.get("low", 0) * 0.5 + severity_counts.get("info", 0) * 0.5, 20)  # 上限 20

    total_deduct = blocker_deduct + high_deduct + medium_deduct + low_deduct
    score = max(0, int(round(100 - total_deduct)))
    return score


def generate_summary(brain_id: str, brain_name: str, issues: List[Dict], score: int) -> str:
    """生成检测摘要"""
    if not issues:
        return f"{brain_name}检测通过，未发现问题"

    severity_counts = defaultdict(int)
    for issue in issues:
        severity_counts[issue.get("severity", "info")] += 1

    parts = []
    if severity_counts.get("blocker", 0) + severity_counts.get("critical", 0):
        parts.append(f"{severity_counts['blocker'] + severity_counts.get('critical', 0)}个严重")
    if severity_counts.get("high", 0):
        parts.append(f"{severity_counts['high']}个高危")
    if severity_counts.get("medium", 0):
        parts.append(f"{severity_counts['medium']}个中等")
    if severity_counts.get("low", 0) + severity_counts.get("info", 0):
        parts.append(f"{severity_counts['low'] + severity_counts.get('info', 0)}个低危")

    summary = f"{brain_name}发现{len(issues)}个问题，得分{score}"
    if parts:
        summary += f"（{', '.join(parts)}）"

    return summary


def calculate_overall_score(brain_results: Dict[str, Dict]) -> Dict:
    """计算整体评分，跳过执行失败的大脑

    Args:
        brain_results: {brain_id: {score, issues, status, skipped, ...}}

    Returns:
        {
            "total_score": int,
            "active_brains": int,
            "skipped_brains": [brain_id...],
            "per_brain": {brain_id: score},
        }
    """
    total_score = 0
    active_brains = 0
    skipped_brains = []
    per_brain = {}

    for brain_id, result in brain_results.items():
        if result.get("skipped", False) or result.get("status") == "error":
            skipped_brains.append(brain_id)
            per_brain[brain_id] = None
            continue
        score = result.get("score")
        if score is None:
            skipped_brains.append(brain_id)
            per_brain[brain_id] = None
            continue
        total_score += score
        active_brains += 1
        per_brain[brain_id] = score

    if active_brains == 0:
        overall = 0
    else:
        overall = round(total_score / active_brains)

    return {
        "total_score": overall,
        "active_brains": active_brains,
        "skipped_brains": skipped_brains,
        "per_brain": per_brain,
    }
