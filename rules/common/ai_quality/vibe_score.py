"""
代码质量评分系统 (v3.2.0新增)

智能质检模块的核心评分机制，衡量代码整体质量水平
满分100分，所有检测项加权计算

扣分规则：
- 高危 (error):   -5分/个
- 中危 (warning): -2分/个
- 提示 (info):    -0.5分/个

分级：
- 90-100: 优秀 - 代码质量高，无明显问题
- 70-89:  良好 - 少量建议项，不影响功能
- 50-69:  需整改 - 存在中危问题，建议修复
- 30-49:  严重问题 - 存在高危问题，必须修复
- 0-29:   极严重 - 大量高危问题，禁止上线
"""

import os
import re
from typing import Dict, List, Tuple, Any
from collections import defaultdict


# 代码质量评分等级定义（内部变量名 VIBE_LEVELS 保持不变）
VIBE_LEVELS = [
    (90, 100, "优秀", "🏆", "代码质量高，无明显问题"),
    (70, 89, "良好", "👍", "少量建议项，不影响功能"),
    (50, 69, "需整改", "⚠️", "存在中危问题，建议修复"),
    (30, 49, "严重问题", "🚨", "存在高危问题，必须修复"),
    (0, 29, "极严重", "💀", "大量高危问题，禁止上线"),
]

# 扣分权重
SEVERITY_WEIGHTS = {
    'error': 5,     # 高危
    'warning': 2,   # 中危
    'info': 0.5,    # 提示
}

# 智能质检模块ID（用于识别哪些问题属于智能质检）
AI_MODULE_IDS = {'ai_security', 'ai_specific', 'ai_quality'}
AI_RULE_PREFIXES = ('AI-SEC-', 'AI-SPEC-', 'AI-QUAL-')


def is_ai_check_result(result: Any) -> bool:
    """判断一个检查结果是否属于智能质检模块"""
    # 检查rule_id前缀
    rule_id = getattr(result, 'rule_id', '') or getattr(result, 'id', '') or ''
    if any(rule_id.startswith(prefix) for prefix in AI_RULE_PREFIXES):
        return True
    
    # 检查module_id
    module_id = getattr(result, 'module_id', '') or ''
    if module_id in AI_MODULE_IDS:
        return True
    
    # 检查category
    category = getattr(result, 'category', '') or ''
    if category == 'ai_code_check':
        return True
    
    return False


def calculate_vibe_score(ai_results: List[Any]) -> Dict[str, Any]:
    """计算代码质量评分
    
    Args:
        ai_results: 智能质检模块的检查结果列表
    
    Returns:
        包含分数、等级、统计信息的字典
    """
    # 统计各级别问题数
    counts = {
        'error': 0,
        'warning': 0,
        'info': 0,
    }
    
    # 按规则统计
    rule_stats = defaultdict(int)
    category_stats = defaultdict(int)
    
    for result in ai_results:
        # 获取级别
        level = getattr(result, 'level', 'info') or 'info'
        if level not in counts:
            level = 'info'
        
        counts[level] += 1
        
        # 按规则ID统计
        rule_id = getattr(result, 'rule_id', '') or getattr(result, 'id', '') or 'unknown'
        rule_stats[rule_id] += 1
        
        # 按类别统计
        if rule_id.startswith('AI-SEC-'):
            category_stats['security'] += 1
        elif rule_id.startswith('AI-SPEC-'):
            category_stats['ai_specific'] += 1
        elif rule_id.startswith('AI-QUAL-'):
            category_stats['quality'] += 1
    
    # 计算扣分
    deduction = 0
    for level, count in counts.items():
        weight = SEVERITY_WEIGHTS.get(level, 0)
        deduction += count * weight
    
    # 计算分数（最低0分）
    score = max(0, 100 - deduction)
    score = int(round(score))
    
    # 确定等级
    level_name = ""
    level_icon = ""
    level_desc = ""
    for min_score, max_score, name, icon, desc in VIBE_LEVELS:
        if min_score <= score <= max_score:
            level_name = name
            level_icon = icon
            level_desc = desc
            break
    
    return {
        'score': score,
        'level': level_name,
        'level_icon': level_icon,
        'level_desc': level_desc,
        'counts': counts,
        'deduction': deduction,
        'rule_stats': dict(rule_stats),
        'category_stats': dict(category_stats),
        'total_issues': sum(counts.values()),
    }


def get_vibe_level(score: int) -> Tuple[str, str, str]:
    """根据分数获取等级信息
    
    Returns:
        (等级名, 图标, 描述)
    """
    for min_score, max_score, name, icon, desc in VIBE_LEVELS:
        if min_score <= score <= max_score:
            return name, icon, desc
    return "未知", "❓", "无法判断"


def format_vibe_score_report(vibe_data: Dict) -> str:
    """生成代码质量评分的Markdown报告片段
    
    Args:
        vibe_data: calculate_vibe_score的返回结果
    
    Returns:
        Markdown格式的报告片段
    """
    score = vibe_data['score']
    level = vibe_data['level']
    icon = vibe_data['level_icon']
    desc = vibe_data['level_desc']
    counts = vibe_data['counts']
    deduction = vibe_data['deduction']
    total = vibe_data['total_issues']
    
    # 生成进度条
    bar_length = 20
    filled = int(score / 100 * bar_length)
    bar = '█' * filled + '░' * (bar_length - filled)
    
    # 颜色标识
    if score >= 90:
        color_tag = "🟢"
    elif score >= 70:
        color_tag = "🟡"
    elif score >= 50:
        color_tag = "🟠"
    elif score >= 30:
        color_tag = "🔴"
    else:
        color_tag = "💀"
    
    lines = []
    lines.append(f"### {icon} 代码质量评分: **{score}/100** {color_tag}")
    lines.append("")
    lines.append(f"**等级：{level}**")
    lines.append(f"")
    lines.append(f"`{bar}` {score}/100")
    lines.append("")
    lines.append(f"> {desc}")
    lines.append("")
    lines.append("| 维度 | 数量 | 扣分 |")
    lines.append("|------|------|------|")
    lines.append(f"| 🔴 高危问题 | {counts['error']} | -{counts['error'] * 5} 分 |")
    lines.append(f"| 🟡 中危问题 | {counts['warning']} | -{counts['warning'] * 2} 分 |")
    lines.append(f"| 💡 提示问题 | {counts['info']} | -{counts['info'] * 0.5} 分 |")
    lines.append(f"| **合计** | **{total}** | **-{deduction} 分** |")
    lines.append("")
    
    # 分类统计
    cat_stats = vibe_data.get('category_stats', {})
    if cat_stats:
        lines.append("**分类分布：**")
        lines.append("")
        cat_names = {
            'security': '🔒 安全红线',
            'ai_specific': '🎯 特有问题',
            'quality': '📐 代码质量',
        }
        for cat_key, cat_name in cat_names.items():
            count = cat_stats.get(cat_key, 0)
            lines.append(f"- {cat_name}: {count} 项")
        lines.append("")
    
    return "\n".join(lines)


def extract_ai_results_from_runner(runner) -> List[Any]:
    """从RuleRunner中提取智能质检的结果
    
    Args:
        runner: RuleRunner实例
    
    Returns:
        AI检测结果列表
    """
    ai_results = []
    
    for module_id, results in runner.results.items():
        for result in results:
            # 只统计有效问题（排除误报）
            status = getattr(result, 'status', 'active')
            if status != 'active':
                continue
            
            if is_ai_check_result(result):
                ai_results.append(result)
    
    return ai_results


def calculate_vibe_from_runner(runner) -> Dict[str, Any]:
    """从RuleRunner计算代码质量评分
    
    Args:
        runner: RuleRunner实例
    
    Returns:
        代码质量评分数据字典
    """
    ai_results = extract_ai_results_from_runner(runner)
    return calculate_vibe_score(ai_results)
