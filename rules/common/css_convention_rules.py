"""
CSS规范规则集 (v5.2.0)
检测CSS代码规范问题 - 适用于含CSS的项目
包含: 选择器复杂度、z-index混乱、!important滥用、硬编码px、
重复样式、过度嵌套、魔法数字、未使用样式等8项检查
"""

import re
import os
from typing import List, Dict, Any
from collections import defaultdict


# ===== CSS-001 选择器复杂度过高 =====
def check_css_001_selector_complexity(context) -> List[Dict]:
    """CSS-001 选择器复杂度过高 - 选择器层级>3"""
    results = []
    css_files = context.find_files([".css", ".scss", ".less", ".wxss"])
    threshold = 3
    issues = []

    for fpath in css_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        lines = content.split('\n')
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*'):
                continue
            # Skip property lines
            if ':' in stripped and '{' not in stripped and '}' not in stripped:
                continue

            # Check selector complexity (count descendant combinators)
            # A selector like .a .b .c .d has 4 levels
            selectors = stripped.split('{')[0].strip()
            if not selectors or selectors.startswith('@'):
                continue

            # Split by comma for multiple selectors
            for selector in selectors.split(','):
                selector = selector.strip()
                if not selector:
                    continue
                # Count parts (separated by spaces, >, +, ~)
                parts = re.split(r'\s+|[>+~]', selector)
                parts = [p for p in parts if p and p not in ('', '&')]
                if len(parts) > threshold:
                    issues.append((fpath, i + 1, selector[:50], len(parts)))

        if len(issues) > 20:
            break

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} 选择器 '{s}' ({c}层)"
            for f, l, s, c in issues[:8]
        )
        results.append({
            'id': 'CSS-001',
            'name': '选择器复杂度过高',
            'level': 'info',
            'message': f'发现{len(issues)}个选择器层级超过{threshold}',
            'detail': detail,
            'file': issues[0][0],
            'line': issues[0][1],
            'fix': '简化选择器层级，使用BEM命名规范，避免过深的后代选择器',
        })

    return results


# ===== CSS-002 z-index混乱 =====
def check_css_002_z_index(context) -> List[Dict]:
    """CSS-002 z-index混乱 - z-index值>100或负数"""
    results = []
    css_files = context.find_files([".css", ".scss", ".less", ".wxss"])
    issues = []

    for fpath in css_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        lines = content.split('\n')
        for i, line in enumerate(lines):
            m = re.search(r'z-index\s*:\s*(-?\d+)', line)
            if m:
                value = int(m.group(1))
                if value > 100 or value < 0:
                    issues.append((fpath, i + 1, value))

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} z-index: {v}"
            for f, l, v in issues[:8]
        )
        results.append({
            'id': 'CSS-002',
            'name': 'z-index混乱',
            'level': 'info',
            'message': f'发现{len(issues)}处z-index值异常(>100或负数)',
            'detail': detail,
            'file': issues[0][0],
            'line': issues[0][1],
            'fix': '建立z-index层级规范：基础层0-10，弹窗层100-200，遮罩层900-1000',
        })

    return results


# ===== CSS-003 !important滥用 =====
def check_css_003_important_abuse(context) -> List[Dict]:
    """CSS-003 !important滥用 - !important使用>5次"""
    results = []
    css_files = context.find_files([".css", ".scss", ".less", ".wxss"])
    threshold = context.project_profile.get_adjusted_threshold('important_threshold', 5)
    important_locations = []

    for fpath in css_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        lines = content.split('\n')
        for i, line in enumerate(lines):
            if '!important' in line:
                important_locations.append((fpath, i + 1, line.strip()[:50]))

    if len(important_locations) > threshold:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} {code}"
            for f, l, code in important_locations[:8]
        )
        results.append({
            'id': 'CSS-003',
            'name': '!important滥用',
            'level': 'info',
            'message': f'发现{len(important_locations)}处!important使用(>{threshold})',
            'detail': detail,
            'file': important_locations[0][0] if important_locations else '',
            'line': important_locations[0][1] if important_locations else 0,
            'fix': '通过提高选择器特异性替代!important，重构CSS层级结构',
        })

    return results


# ===== CSS-004 硬编码px值 =====
def check_css_004_hardcoded_px(context) -> List[Dict]:
    """CSS-004 硬编码px值 - 应使用rpx/rem(小程序/Web)"""
    results = []
    css_files = context.find_files([".css", ".scss", ".less", ".wxss"])
    issues = []

    # Check if this is a miniprogram project
    wxss_files = context.find_files([".wxss"])
    is_miniprogram = len(wxss_files) > 0

    for fpath in css_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        ext = os.path.splitext(fpath)[1].lower()
        basename = os.path.basename(fpath).lower()
        # Skip variable/theme files
        if 'variable' in basename or 'theme' in basename:
            continue
        # Skip media query definitions
        if '@media' in content[:100]:
            pass

        lines = content.split('\n')
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*'):
                continue

            # Find px values
            px_matches = re.finditer(r'(?<!\w)(\d+)px\b', line)
            for m in px_matches:
                value = int(m.group(1))
                # Skip 0px and 1px (commonly acceptable)
                if value <= 1:
                    continue
                # Skip border-width (commonly uses px)
                if re.search(r'border.*:', line):
                    continue
                # Skip @media queries
                if '@media' in line:
                    continue
                # Skip box-shadow
                if 'box-shadow' in line:
                    continue
                issues.append((fpath, i + 1, f"{value}px"))

        if len(issues) > 30:
            break

    if issues:
        unit = 'rpx' if is_miniprogram else 'rem'
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} {v}"
            for f, l, v in issues[:8]
        )
        results.append({
            'id': 'CSS-004',
            'name': '硬编码px值',
            'level': 'info',
            'message': f'发现{len(issues)}处硬编码px值，建议使用{unit}',
            'detail': detail,
            'file': issues[0][0],
            'line': issues[0][1],
            'fix': f'使用{unit}替代px以支持响应式布局',
        })

    return results


# ===== CSS-005 重复样式定义 =====
def check_css_005_duplicate_styles(context) -> List[Dict]:
    """CSS-005 重复样式定义 - 相同CSS规则重复"""
    results = []
    css_files = context.find_files([".css", ".scss", ".less", ".wxss"])
    declaration_groups = defaultdict(list)

    for fpath in css_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        # Extract declaration blocks
        # Simple approach: find selector { declarations }
        blocks = re.finditer(r'([^{}]+?)\{([^{}]+?)\}', content, re.DOTALL)
        for m in blocks:
            selector = m.group(1).strip()
            declarations = m.group(2).strip()
            if not selector or not declarations:
                continue
            # Normalize declarations
            normalized = re.sub(r'\s+', ' ', declarations).strip()
            # Only track blocks with multiple declarations
            if normalized.count(';') >= 2:
                line_num = content[:m.start()].count('\n') + 1
                declaration_groups[normalized].append((fpath, line_num, selector))

    # Find duplicate declaration blocks
    duplicates = {decl: locs for decl, locs in declaration_groups.items() if len(locs) > 1}

    if duplicates:
        samples = sorted(duplicates.items(), key=lambda x: len(x[1]), reverse=True)[:3]
        detail = '\n'.join(
            f"  相同样式出现在: " + ', '.join(f"{os.path.basename(f)}:{l}({s})" for f, l, s in locs[:3])
            for _, locs in samples
        )
        results.append({
            'id': 'CSS-005',
            'name': '重复样式定义',
            'level': 'info',
            'message': f'发现{len(duplicates)}组重复的CSS样式定义',
            'detail': detail,
            'file': '',
            'line': 0,
            'fix': '提取公共样式为class，使用CSS继承和组合减少重复',
        })

    return results


# ===== CSS-006 过度嵌套 =====
def check_css_006_over_nesting(context) -> List[Dict]:
    """CSS-006 过度嵌套 - 嵌套>4层"""
    results = []
    css_files = context.find_files([".scss", ".less"])  # Only SCSS/LESS support nesting
    threshold = 4
    issues = []

    for fpath in css_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        lines = content.split('\n')
        depth = 0
        max_depth = 0
        max_line = 0

        for i, line in enumerate(lines):
            stripped = line.strip()
            if '{' in stripped:
                depth += stripped.count('{')
                if depth > max_depth:
                    max_depth = depth
                    max_line = i + 1
            if '}' in stripped:
                depth = max(0, depth - stripped.count('}'))

        if max_depth > threshold:
            issues.append((fpath, max_line, max_depth))

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} 嵌套深度={d}"
            for f, l, d in issues[:8]
        )
        results.append({
            'id': 'CSS-006',
            'name': '过度嵌套',
            'level': 'info',
            'message': f'发现{len(issues)}处CSS嵌套超过{threshold}层',
            'detail': detail,
            'file': issues[0][0] if issues else '',
            'line': issues[0][1] if issues else 0,
            'fix': '减少SCSS/LESS嵌套层级，最多不超过4层，使用扁平化选择器',
        })

    return results


# ===== CSS-007 魔法数字 =====
def check_css_007_css_magic_numbers(context) -> List[Dict]:
    """CSS-007 魔法数字 - 未使用变量的数值"""
    results = []
    css_files = context.find_files([".css", ".scss", ".less", ".wxss"])
    issues = []

    for fpath in css_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        basename = os.path.basename(fpath).lower()
        if 'variable' in basename or 'theme' in basename:
            continue

        lines = content.split('\n')
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*'):
                continue
            # Skip variable definitions
            if re.search(r'--\w+\s*:', stripped):
                continue
            if re.search(r'\$\w+\s*:', stripped):
                continue
            if re.search(r'@\w+\s*:', stripped):
                continue

            # Find suspicious numeric values (like specific margins, paddings, widths)
            suspicious = re.finditer(r':\s*(\d+)(?:px|rem|rpx|em|%)?\s*[;}\s]', line)
            for m in suspicious:
                value = int(m.group(1))
                # Flag unusual values that should be in variables
                if value in (3, 7, 11, 13, 17, 19, 23, 33, 37, 43, 47, 53, 67, 73, 83, 97,
                            6, 14, 18, 22, 26, 34, 38, 46, 58, 62, 74, 86, 94):
                    # These are prime or unusual numbers that should be constants
                    if value > 2:
                        issues.append((fpath, i + 1, value, stripped[:40]))

        if len(issues) > 20:
            break

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} 数值 {v}"
            for f, l, v, _ in issues[:8]
        )
        results.append({
            'id': 'CSS-007',
            'name': '魔法数字',
            'level': 'info',
            'message': f'发现{len(issues)}处CSS魔法数字',
            'detail': detail,
            'file': issues[0][0] if issues else '',
            'line': issues[0][1] if issues else 0,
            'fix': '将CSS数值提取为变量，使用统一的设计间距规范(如4px倍数)',
        })

    return results


# ===== CSS-008 未使用样式 =====
def check_css_008_unused_styles(context) -> List[Dict]:
    """CSS-008 未使用样式 - 定义但未引用的class"""
    results = []
    css_files = context.find_files([".css", ".scss", ".less", ".wxss"])
    html_files = context.find_files([".html", ".htm", ".wxml", ".vue", ".tsx", ".jsx", ".js", ".ts"])

    if not css_files or not html_files:
        return results

    # Collect all defined CSS classes
    css_classes = {}
    for fpath in css_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        for m in re.finditer(r'\.([\w-]+)\s*[{,:]', content):
            class_name = m.group(1)
            if class_name not in css_classes:
                line_num = content[:m.start()].count('\n') + 1
                css_classes[class_name] = (fpath, line_num)

    if not css_classes:
        return results

    # Collect all used classes from HTML/JS files
    used_classes = set()
    for fpath in html_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        # Find class references
        for m in re.finditer(r"""class(?:Name)?=["'][^"']*["']|class=["']([^"']+)["']""", content):
            classes = m.group(1) or m.group(0)
            for cls in re.findall(r'[\w-]+', classes):
                used_classes.add(cls)
        # Also check for dynamic class references
        for m in re.finditer(r"""['"]([\w-]+)['"]""", content):
            used_classes.add(m.group(1))

    # Find unused classes
    unused = {name: loc for name, loc in css_classes.items() if name not in used_classes}

    if len(unused) > 5:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} .{name}"
            for name, (f, l) in list(unused.items())[:8]
        )
        results.append({
            'id': 'CSS-008',
            'name': '未使用样式',
            'level': 'info',
            'message': f'发现{len(unused)}个未引用的CSS class',
            'detail': detail,
            'file': list(unused.values())[0][0],
            'line': list(unused.values())[0][1],
            'fix': '删除未使用的CSS样式，减少样式文件体积',
        })

    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'CSS-001',
        'name': '选择器复杂度过高',
        'level': 'info',
        'category': 'css_convention',
        'module_id': '27',
        'applicable_types': [],
        'description': '检查选择器层级>3',
        'check': check_css_001_selector_complexity,
    },
    {
        'id': 'CSS-002',
        'name': 'z-index混乱',
        'level': 'info',
        'category': 'css_convention',
        'module_id': '27',
        'applicable_types': [],
        'description': '检查z-index值>100或负数',
        'check': check_css_002_z_index,
    },
    {
        'id': 'CSS-003',
        'name': '!important滥用',
        'level': 'info',
        'category': 'css_convention',
        'module_id': '27',
        'applicable_types': [],
        'description': '检查!important使用>5次',
        'check': check_css_003_important_abuse,
    },
    {
        'id': 'CSS-004',
        'name': '硬编码px值',
        'level': 'info',
        'category': 'css_convention',
        'module_id': '27',
        'applicable_types': [],
        'description': '检查硬编码px值，建议使用rpx/rem',
        'check': check_css_004_hardcoded_px,
    },
    {
        'id': 'CSS-005',
        'name': '重复样式定义',
        'level': 'info',
        'category': 'css_convention',
        'module_id': '27',
        'applicable_types': [],
        'description': '检查相同CSS规则重复定义',
        'check': check_css_005_duplicate_styles,
    },
    {
        'id': 'CSS-006',
        'name': '过度嵌套',
        'level': 'info',
        'category': 'css_convention',
        'module_id': '27',
        'applicable_types': [],
        'description': '检查SCSS/LESS嵌套>4层',
        'check': check_css_006_over_nesting,
    },
    {
        'id': 'CSS-007',
        'name': '魔法数字',
        'level': 'info',
        'category': 'css_convention',
        'module_id': '27',
        'applicable_types': [],
        'description': '检查CSS中未使用变量的数值',
        'check': check_css_007_css_magic_numbers,
    },
    {
        'id': 'CSS-008',
        'name': '未使用样式',
        'level': 'info',
        'category': 'css_convention',
        'module_id': '27',
        'applicable_types': [],
        'description': '检查定义但未引用的CSS class',
        'check': check_css_008_unused_styles,
    },
]
