# -*- coding: utf-8 -*-
"""修复路线图（Fix Roadmap）模块

Phase 1: 优先级聚合、文件分组、TOP N 生成
Phase 3: 修复进度追踪（diff）
"""

# ── severity → 优先级映射 ──────────────────────────────────────
PRIORITY_MAP = {
    "critical": "P0",
    "blocker": "P0",
    "high": "P1",
    "suspicious": "P1",
    "medium": "P2",
    "correctness": "P2",
    "restriction": "P2",
    "low": "P3",
    "style": "P3",
    "info": "P3",
}

SEVERITY_WEIGHT = {
    "critical": 6, "blocker": 6,
    "high": 5, "suspicious": 5,
    "medium": 4, "correctness": 4, "restriction": 4,
    "low": 2, "style": 1,
    "info": 1,
}

PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}

PRIORITY_META = {
    "P0": {"label": "立即修复", "icon": "🔴", "color": "#EF4444", "bg": "rgba(239,68,68,0.08)"},
    "P1": {"label": "计划修复", "icon": "🟡", "color": "#F59E0B", "bg": "rgba(245,158,11,0.08)"},
    "P2": {"label": "尽快修复", "icon": "🟠", "color": "#F97316", "bg": "rgba(249,115,22,0.08)"},
    "P3": {"label": "建议优化", "icon": "⚪", "color": "#9CA3AF", "bg": "rgba(156,163,175,0.08)"},
}


def _get_priority(issue):
    """获取 issue 的优先级"""
    sev = issue.get("severity", "info")
    return PRIORITY_MAP.get(sev, "P3")


def _get_severity_weight(issue):
    """获取 issue 的严重度权重（用于排序）"""
    sev = issue.get("severity", "info")
    return SEVERITY_WEIGHT.get(sev, 0)


def _get_file_name(file_path):
    """从文件路径提取文件名"""
    if not file_path:
        return "未知文件"
    return file_path.split("/")[-1].split("\\")[-1]


def build_fix_roadmap(visible_issues):
    """构建修复路线图数据

    Args:
        visible_issues: 格式化的 issue 列表（已经过 _format_visible_issues 处理）

    Returns:
        dict: 包含 summary, top_fixes, file_groups 的修复路线图数据
    """
    if not visible_issues:
        return None

    # 1. 按优先级分桶统计
    priority_buckets = {"P0": [], "P1": [], "P2": [], "P3": []}
    for issue in visible_issues:
        p = _get_priority(issue)
        priority_buckets[p].append(issue)

    # 2. 计算 summary
    summary = {}
    for p in ["P0", "P1", "P2", "P3"]:
        issues = priority_buckets[p]
        if issues:
            files = set(i.get("file", "") for i in issues)
            summary[p] = {
                "file_count": len(files),
                "issue_count": len(issues),
                "label": PRIORITY_META[p]["label"],
                "icon": PRIORITY_META[p]["icon"],
                "color": PRIORITY_META[p]["color"],
                "bg": PRIORITY_META[p]["bg"],
            }
        else:
            summary[p] = {
                "file_count": 0,
                "issue_count": 0,
                "label": PRIORITY_META[p]["label"],
                "icon": PRIORITY_META[p]["icon"],
                "color": PRIORITY_META[p]["color"],
                "bg": PRIORITY_META[p]["bg"],
            }

    # 3. 生成 TOP N（最多5条，按 severity 降序，同 rule_id 合并计数）
    sorted_issues = sorted(visible_issues, key=lambda i: (_get_severity_weight(i), i.get("line", 0)), reverse=True)
    top_fixes = []
    seen_keys = {}  # (rule_id, file) -> index in top_fixes
    for issue in sorted_issues:
        if len(top_fixes) >= 5:
            break
        rule_id = issue.get("rule_id", issue.get("check_id", ""))
        file_path = issue.get("file", "")
        merge_key = (rule_id, file_path)

        if merge_key in seen_keys:
            # 同规则同文件，增加计数
            idx = seen_keys[merge_key]
            top_fixes[idx]["count"] += 1
        else:
            entry = {
                "priority": _get_priority(issue),
                "severity": issue.get("severity", ""),
                "title": issue.get("title", issue.get("name", "未知问题")),
                "file": file_path,
                "file_short": _get_file_name(file_path),
                "line": issue.get("line", 0),
                "suggestion": issue.get("suggestion", ""),
                "rule_id": rule_id,
                "count": 1,
                "icon": PRIORITY_META[_get_priority(issue)]["icon"],
                "color": PRIORITY_META[_get_priority(issue)]["color"],
            }
            top_fixes.append(entry)
            seen_keys[merge_key] = len(top_fixes) - 1

    # 4. 按文件分组
    file_groups_raw = {}
    for issue in visible_issues:
        file_path = issue.get("file", "")
        if file_path not in file_groups_raw:
            file_groups_raw[file_path] = {
                "file": file_path,
                "file_short": _get_file_name(file_path),
                "issues": [],
                "max_priority": "P3",
                "max_severity_weight": 0,
                "max_severity": "info",
                "issue_count": 0,
            }
        group = file_groups_raw[file_path]
        group["issues"].append(issue)
        group["issue_count"] += 1

        sev_w = _get_severity_weight(issue)
        if sev_w > group["max_severity_weight"]:
            group["max_severity_weight"] = sev_w
            group["max_priority"] = _get_priority(issue)
            group["max_severity"] = issue.get("severity", "info")

    # 5. 按最高严重级别排序文件组
    file_groups = sorted(
        file_groups_raw.values(),
        key=lambda g: (PRIORITY_ORDER.get(g["max_priority"], 9), -g["max_severity_weight"], g["file"])
    )

    # 6. 按优先级分文件组（用于前端分级折叠）
    file_groups_by_priority = {"P0": [], "P1": [], "P2": [], "P3": []}
    for fg in file_groups:
        file_groups_by_priority[fg["max_priority"]].append(fg)

    return {
        "summary": summary,
        "top_fixes": top_fixes,
        "file_groups": file_groups,
        "file_groups_by_priority": file_groups_by_priority,
    }


def build_fix_progress(current_scan_id, user_id):
    """构建修复进度数据（与上一次扫描对比）

    Returns:
        dict or None: 修复进度数据，无历史记录时返回 None
    """
    if not user_id:
        return None

    try:
        from .db import get_db
        from .scan_diff import compare_scans, _scan_summary
        import json

        db = get_db()
        current = db.execute(
            'SELECT id, scan_id, score, grade, issue_count, results, created_at, title '
            'FROM scans WHERE scan_id=? AND user_id=?',
            (current_scan_id, user_id)
        ).fetchone()

        if not current:
            return None

        prev = db.execute(
            'SELECT scan_id, score, grade, issue_count, results, created_at, title FROM scans '
            'WHERE user_id=? AND id < ? ORDER BY id DESC LIMIT 1',
            (user_id, current['id'])
        ).fetchone()

        if not prev:
            return None

        # 使用已有的 compare_scans
        diff = compare_scans(prev['results'], current['results'], prev['score'], current['score'])

        # 按优先级分类统计
        fixed_by_priority = {"P0": 0, "P1": 0, "P2": 0, "P3": 0}
        for issue in diff.get("fixed_issues", []):
            p = PRIORITY_MAP.get(issue.get("severity", "info"), "P3")
            fixed_by_priority[p] += 1

        new_by_priority = {"P0": 0, "P1": 0, "P2": 0, "P3": 0}
        for issue in diff.get("new_issues", []):
            p = PRIORITY_MAP.get(issue.get("severity", "info"), "P3")
            new_by_priority[p] += 1

        total_prev = prev['issue_count'] or 1
        total_fixed = diff['summary']['total_fixed']
        fix_rate = round(total_fixed / total_prev * 100, 1) if total_prev > 0 else 0

        return {
            "previous_scan": _scan_summary(prev),
            "fixed": fixed_by_priority,
            "fixed_total": total_fixed,
            "new": new_by_priority,
            "new_total": diff['summary']['total_new'],
            "remaining": diff['summary']['total_remaining'],
            "fix_rate": f"{fix_rate}%",
            "score_change": diff['summary']['score_change'],
        }
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("fix_progress error: %s", e)
        return None
