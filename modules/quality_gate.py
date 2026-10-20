# -*- coding: utf-8 -*-
"""
P1: 质量门禁评估引擎
=====================
评估扫描结果是否满足用户设定的门禁规则。

门禁规则示例：
- 最低总分 >= 80
- 零严重问题 (critical == 0)
- 高危问题上限 <= 5
- 单引擎最低分 >= 60
"""

import json
import logging

from modules.constants import logger

# 预设门禁模板
GATE_TEMPLATES = {
    'strict': {
        'name': '严格模式',
        'rules': [
            {'id': 'score_min', 'name': '最低总分', 'operator': '>=', 'value': 90, 'enabled': True},
            {'id': 'no_critical', 'name': '零严重问题', 'field': 'severity_counts.critical', 'operator': '==', 'value': 0, 'enabled': True},
            {'id': 'no_high', 'name': '零高危问题', 'field': 'severity_counts.high', 'operator': '==', 'value': 0, 'enabled': True},
            {'id': 'max_medium', 'name': '中危上限', 'field': 'severity_counts.medium', 'operator': '<=', 'value': 3, 'enabled': True},
        ],
    },
    'standard': {
        'name': '标准模式',
        'rules': [
            {'id': 'score_min', 'name': '最低总分', 'operator': '>=', 'value': 80, 'enabled': True},
            {'id': 'no_critical', 'name': '零严重问题', 'field': 'severity_counts.critical', 'operator': '==', 'value': 0, 'enabled': True},
            {'id': 'max_high', 'name': '高危上限', 'field': 'severity_counts.high', 'operator': '<=', 'value': 5, 'enabled': True},
        ],
    },
    'relaxed': {
        'name': '宽松模式',
        'rules': [
            {'id': 'score_min', 'name': '最低总分', 'operator': '>=', 'value': 60, 'enabled': True},
            {'id': 'no_critical', 'name': '零严重问题', 'field': 'severity_counts.critical', 'operator': '==', 'value': 0, 'enabled': True},
        ],
    },
}


def _count_severity(issues):
    """统计各级别问题数"""
    counts = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0, 'info': 0}
    for issue in issues:
        sev = issue.get('severity', 'low')
        if sev in counts:
            counts[sev] += 1
        else:
            counts['low'] += 1
    return counts


def _get_field_value(scan_result, field):
    """从扫描结果中获取字段值"""
    issues = scan_result.get('issues', [])
    severity_counts = _count_severity(issues)
    score = scan_result.get('score', 0) or 0

    field_map = {
        'score': score,
        'severity_counts.critical': severity_counts['critical'],
        'severity_counts.high': severity_counts['high'],
        'severity_counts.medium': severity_counts['medium'],
        'severity_counts.low': severity_counts['low'],
        'total_issues': len(issues),
    }

    # 单引擎统计
    if field == 'brain_max_issues':
        brain_issues = {}
        for issue in issues:
            bid = issue.get('brain_id', 'unknown')
            brain_issues[bid] = brain_issues.get(bid, 0) + 1
        return max(brain_issues.values()) if brain_issues else 0

    if field == 'brain_min_score':
        # 简化：用总分代替（实际应从 brain scores 中取最低）
        return score

    return field_map.get(field, 0)


def _evaluate_operator(actual, operator, expected):
    """评估运算符"""
    ops = {
        '==': lambda a, b: a == b,
        '!=': lambda a, b: a != b,
        '>=': lambda a, b: a >= b,
        '<=': lambda a, b: a <= b,
        '>': lambda a, b: a > b,
        '<': lambda a, b: a < b,
    }
    fn = ops.get(operator)
    if fn:
        return fn(actual, expected)
    return True


def evaluate_gate(scan_result, gate_rules):
    """
    评估扫描结果是否满足门禁规则。

    Args:
        scan_result: 扫描结果字典（包含 issues, score 等）
        gate_rules: 门禁规则字典（包含 rules 列表）

    Returns:
        dict: {passed, rules, failed_count, total_count}
    """
    rules = gate_rules.get('rules', [])
    enabled_rules = [r for r in rules if r.get('enabled', True)]

    results = []
    failed_count = 0

    for rule in enabled_rules:
        field = rule.get('field', 'score')
        operator = rule.get('operator', '>=')
        expected = rule.get('value', 0)

        actual = _get_field_value(scan_result, field)
        passed = _evaluate_operator(actual, operator, expected)

        if not passed:
            failed_count += 1

        results.append({
            'id': rule.get('id', ''),
            'name': rule.get('name', ''),
            'passed': passed,
            'actual': actual,
            'expected': expected,
            'operator': operator,
        })

    return {
        'passed': failed_count == 0,
        'rules': results,
        'failed_count': failed_count,
        'total_count': len(enabled_rules),
    }


def get_user_active_gate(db, user_id):
    """获取用户当前生效的门禁配置"""
    if not user_id:
        return None
    row = db.execute(
        'SELECT rules_json FROM quality_gates WHERE user_id=? AND is_active=1',
        (user_id,)
    ).fetchone()
    if row and row[0]:
        try:
            return json.loads(row[0])
        except Exception:
            return None
    return None


def get_templates():
    """获取预设门禁模板"""
    return GATE_TEMPLATES
