"""
Web/H5视觉质量规则集
从 frontend_rules.py 拆分而来，包含 UI 视觉设计规范:
  5.4 AI复制按钮 / 5.5 AI头像 / 5.7 Emoji图标
  5.8 硬编码颜色 / 5.9 卡片圆角 / 5.10 按钮高度
  5.14 深色模式 / 5.15 品牌色 / 5.16 CSS变量
  5.17 字号层级 / 5.18 间距一致性
"""

import re
import os
from typing import List, Dict, Any

def check_5_4_ai_copy_button(context) -> List[Dict]:
    """5.4 AI复制按钮 - 检查AI生成内容是否有一键复制功能"""
    results = []
    
    if not context.is_web_frontend():
        return results
    
    tsx_files = context.find_files([".tsx", ".jsx"])
    if not tsx_files:
        return results
    
    ai_content_files = []
    for f in tsx_files:
        content = context.safe_read(f)
        if not content:
            continue
        if re.search(r'AI|ai[_-]|gpt|chat|生成', content, re.IGNORECASE) and \
           not re.search(r'copy|clipboard|navigator\.clipboard|复制', content, re.IGNORECASE):
            ai_content_files.append(os.path.relpath(f, context.project_path) if context.project_path else f)
    
    if ai_content_files:
        results.append({
            'id': '5.4',
            'name': 'AI复制按钮',
            'level': 'warning',
            'message': f"发现 {len(ai_content_files)} 个AI相关组件缺少复制功能",
            'detail': "\n".join(ai_content_files[:5]),
            'file': '',
            'line': 0,
            'fix': '为AI生成内容添加一键复制功能，提升用户体验',
        })
    
    return results


# ===== 5.5 AI头像/标识 =====


def check_5_5_ai_avatar(context) -> List[Dict]:
    """5.5 AI头像 - 检查AI交互是否有明显的AI标识"""
    results = []
    
    if not context.is_web_frontend():
        return results
    
    front_files = context.find_files([".tsx", ".jsx", ".ts", ".js", ".css", ".scss"])
    all_content = ""
    for f in front_files:
        all_content += context.safe_read(f) + "\n"
    
    has_ai_logo = bool(re.search(r'ai[_-]?logo|ai[_-]?avatar|bot[_-]?avatar|AI.*Logo', all_content, re.IGNORECASE))
    
    if not has_ai_logo:
        # 只有检测到AI相关内容时才报
        has_ai_content = bool(re.search(r'AI|gpt|chatbot|智能', all_content, re.IGNORECASE))
        if has_ai_content:
            results.append({
                'id': '5.5',
                'name': 'AI头像',
                'level': 'warning',
                'message': '检测到AI相关内容但未检测到AI标识/头像',
                'file': '',
                'line': 0,
                'fix': '为AI交互添加明显的AI标识，如AI头像、AI标签等',
            })
    
    return results


# ===== 5.7 emoji图标 =====


def check_5_7_emoji_icon(context) -> List[Dict]:
    """5.7 emoji图标 - 检查是否使用emoji作为图标"""
    results = []
    
    if not context.is_web_frontend():
        return results
    
    tsx_files = context.find_files([".tsx", ".jsx"])
    if not tsx_files:
        return results
    
    emoji_pattern = re.compile(
        r'[\U0001F300-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\U00002600-\U000027BF]')
    emoji_icons = []
    
    for f in tsx_files:
        content = context.safe_read(f)
        if not content:
            continue
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if emoji_pattern.search(line) and \
               not line.strip().startswith('//') and \
               re.search(r'icon|Icon|emoji|text.*=|label.*=', line, re.IGNORECASE):
                rel_path = os.path.relpath(f, context.project_path) if context.project_path else f
                emoji_icons.append(f"{rel_path}:{i}")
                if len(emoji_icons) >= 20:
                    break
        if len(emoji_icons) >= 20:
            break
    
    if emoji_icons:
        results.append({
            'id': '5.7',
            'name': 'emoji图标',
            'level': 'warning',
            'message': f"发现 {len(emoji_icons)} 处可能用emoji做图标",
            'detail': "\n".join(emoji_icons[:5]),
            'file': '',
            'line': 0,
            'fix': '使用正式图标库(如lucide-react/heroicons)替代emoji，保证一致性',
        })
    
    return results


# ===== 5.8 硬编码色值 =====


def check_5_8_hardcoded_colors(context) -> List[Dict]:
    """5.8 硬编码色值 - 检查CSS/内联样式中的硬编码颜色"""
    results = []
    
    if not context.is_web_frontend():
        return results
    
    css_files = context.find_files([".css", ".scss", ".less"])
    tsx_files = context.find_files([".tsx", ".jsx"])
    all_files = css_files + tsx_files
    
    if not all_files:
        return results
    
    thresholds = context.config.get("thresholds", {})
    brand_color = thresholds.get("brand_color", "#FF6B35")
    brand_colors_lower = [c.lower() for c in thresholds.get("brand_colors", [brand_color])]
    
    # 中性色白名单
    neutral_colors = {'#fff', '#ffffff', '#000', '#000000', '#333', '#333333', 
                      '#666', '#666666', '#999', '#999999', '#ccc', '#cccccc', 
                      '#eee', '#eeeeee', '#f5f5f5', '#f8f8f8'}
    
    hardcoded_colors = []
    color_re = re.compile(r'(?:color|background|border|fill|stroke)\s*:\s*(#[0-9a-fA-F]{3,8})', re.IGNORECASE)
    
    for f in all_files:
        content = context.safe_read(f)
        if not content:
            continue
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('//', '/*', '*')):
                continue
            for m in color_re.finditer(line):
                color = m.group(1).lower()
                if color not in brand_colors_lower and color not in neutral_colors:
                    rel_path = os.path.relpath(f, context.project_path) if context.project_path else f
                    hardcoded_colors.append(f"{rel_path}:{i} {color}")
                    if len(hardcoded_colors) >= 50:
                        break
            if len(hardcoded_colors) >= 50:
                break
    
    if hardcoded_colors:
        level = 'warning' if len(hardcoded_colors) > 20 else 'info'
        results.append({
            'id': '5.8',
            'name': '硬编码色值',
            'level': level,
            'message': f"发现 {len(hardcoded_colors)} 处硬编码色值（非品牌色/中性色）",
            'detail': "\n".join(hardcoded_colors[:10]),
            'file': '',
            'line': 0,
            'fix': '将颜色提取为CSS变量或主题变量，统一管理颜色体系',
        })
    
    return results


# ===== 5.9 卡片圆角 =====


def check_5_9_card_border_radius(context) -> List[Dict]:
    """5.9 卡片圆角 - 检查border-radius是否统一"""
    results = []
    
    if not context.is_web_frontend():
        return results
    
    css_files = context.find_files([".css", ".scss", ".less"])
    if not css_files:
        return results
    
    thresholds = context.config.get("thresholds", {})
    expected_radius = thresholds.get("card_border_radius", 12)
    if isinstance(expected_radius, str):
        m = re.search(r'\d+', expected_radius)
        expected_radius = int(m.group()) if m else 12
    
    radius_re = re.compile(r'border-radius\s*:\s*(\d+)px', re.IGNORECASE)
    radii = set()
    
    for f in css_files:
        content = context.safe_read(f)
        if not content:
            continue
        for m in radius_re.finditer(content):
            radii.add(int(m.group(1)))
    
    if radii:
        non_standard = [r for r in radii if r != expected_radius and abs(r - expected_radius) > 2]
        if non_standard:
            results.append({
                'id': '5.9',
                'name': '卡片圆角',
                'level': 'warning',
                'message': f"发现 {len(non_standard)} 种非标准圆角值(标准={expected_radius}px): {sorted(non_standard)}",
                'file': '',
                'line': 0,
                'fix': f'统一使用{expected_radius}px圆角，保持设计一致性',
            })
    
    return results


# ===== 5.10 按钮高度 =====


def check_5_10_button_height(context) -> List[Dict]:
    """5.10 按钮高度 - 检查按钮最小高度"""
    results = []
    
    if not context.is_web_frontend():
        return results
    
    css_files = context.find_files([".css", ".scss", ".less"])
    if not css_files:
        return results
    
    thresholds = context.config.get("thresholds", {})
    min_height = thresholds.get("min_button_height", 36)
    
    btn_height_re = re.compile(r'(?:button|btn).*?height\s*:\s*(\d+)px', re.IGNORECASE | re.DOTALL)
    heights = []
    
    for f in css_files:
        content = context.safe_read(f)
        if not content:
            continue
        for m in btn_height_re.finditer(content):
            h = int(m.group(1))
            if h < min_height:
                rel_path = os.path.relpath(f, context.project_path) if context.project_path else f
                heights.append(f"{rel_path}: {h}px")
    
    if heights:
        results.append({
            'id': '5.10',
            'name': '按钮高度',
            'level': 'warning',
            'message': f"发现 {len(heights)} 个按钮高度低于最小值({min_height}px)",
            'detail': "\n".join(heights[:5]),
            'file': '',
            'line': 0,
            'fix': f'按钮高度不低于{min_height}px，保证点击区域可访问性',
        })
    
    return results


# ===== 5.11 空状态组件 =====


def check_5_14_dark_mode(context) -> List[Dict]:
    """5.14 深色模式 - 检查是否支持深色模式"""
    results = []
    
    if not context.is_web_frontend():
        return results
    
    front_files = context.find_files([".tsx", ".jsx", ".ts", ".js", ".css", ".scss"])
    all_content = ""
    for f in front_files:
        all_content += context.safe_read(f) + "\n"
    
    has_dark_mode = bool(re.search(r'dark:|prefers-color-scheme|theme.*dark|\.dark\s', all_content, re.IGNORECASE))
    
    # 深色模式为可选项，仅作提示
    if not has_dark_mode:
        results.append({
            'id': '5.14',
            'name': '深色模式',
            'level': 'info',
            'message': '未检测到深色模式支持（非必须）',
            'file': '',
            'line': 0,
            'fix': '可考虑添加深色模式支持，提升夜间使用体验',
        })
    
    return results


# ===== 5.15 品牌色一致性 =====


def check_5_15_brand_color(context) -> List[Dict]:
    """5.15 品牌色一致性 - 检查品牌色是否统一使用"""
    results = []
    
    if not context.is_web_frontend():
        return results
    
    thresholds = context.config.get("thresholds", {})
    brand_color = thresholds.get("brand_color", "#FF6B35")
    
    front_files = context.find_files([".tsx", ".jsx", ".ts", ".js", ".css", ".scss"])
    all_content = ""
    for f in front_files:
        all_content += context.safe_read(f) + "\n"
    
    brand_used = brand_color.lower() in all_content.lower()
    
    if not brand_used:
        results.append({
            'id': '5.15',
            'name': '品牌色一致性',
            'level': 'warning',
            'message': f"未检测到品牌色{brand_color}的使用",
            'file': '',
            'line': 0,
            'fix': f'确保品牌色{brand_color}在CSS变量中定义并统一使用',
        })
    
    return results


# ===== 5.16 CSS变量使用 =====


def check_5_16_css_variables(context) -> List[Dict]:
    """5.16 CSS变量使用 - 检查是否使用CSS变量管理主题"""
    results = []
    
    if not context.is_web_frontend():
        return results
    
    front_files = context.find_files([".tsx", ".jsx", ".ts", ".js", ".css", ".scss"])
    all_content = ""
    for f in front_files:
        all_content += context.safe_read(f) + "\n"
    
    css_vars = len(re.findall(r'var\(--', all_content))
    
    if css_vars == 0:
        results.append({
            'id': '5.16',
            'name': 'CSS变量使用',
            'level': 'warning',
            'message': '未检测到CSS变量使用',
            'file': '',
            'line': 0,
            'fix': '使用CSS变量管理主题色、间距、字号等设计令牌',
        })
    
    return results


# ===== 5.17 字体字号层级 =====


def check_5_17_font_size_hierarchy(context) -> List[Dict]:
    """5.17 字体字号层级 - 检查字号种类是否过多"""
    results = []
    
    if not context.is_web_frontend():
        return results
    
    css_files = context.find_files([".css", ".scss", ".less"])
    if not css_files:
        return results
    
    font_re = re.compile(r'font-size\s*:\s*(\d+)px', re.IGNORECASE)
    font_sizes = set()
    
    for f in css_files:
        content = context.safe_read(f)
        if not content:
            continue
        for m in font_re.finditer(content):
            font_sizes.add(int(m.group(1)))
    
    if len(font_sizes) > 8:
        results.append({
            'id': '5.17',
            'name': '字体字号层级',
            'level': 'warning',
            'message': f"发现 {len(font_sizes)} 种不同字号，建议精简到6-8种",
            'detail': f"字号集合: {sorted(font_sizes)}",
            'file': '',
            'line': 0,
            'fix': '建立字号体系(如12/14/16/18/24/32)，统一字体层级',
        })
    
    return results


# ===== 5.18 间距一致性 =====


def check_5_18_spacing_consistency(context) -> List[Dict]:
    """5.18 间距一致性 - 检查间距值是否过多"""
    results = []
    
    if not context.is_web_frontend():
        return results
    
    css_files = context.find_files([".css", ".scss", ".less"])
    if not css_files:
        return results
    
    spacing_re = re.compile(r'(?:margin|padding|gap)\s*:\s*(\d+)px', re.IGNORECASE)
    spacings = set()
    
    for f in css_files:
        content = context.safe_read(f)
        if not content:
            continue
        for m in spacing_re.finditer(content):
            spacings.add(int(m.group(1)))
    
    if len(spacings) > 12:
        results.append({
            'id': '5.18',
            'name': '间距一致性',
            'level': 'warning',
            'message': f"发现 {len(spacings)} 种不同间距值，建议使用8px网格系统",
            'detail': f"间距集合: {sorted(spacings)}",
            'file': '',
            'line': 0,
            'fix': '采用8px倍数间距体系(8/16/24/32/48)，保持间距一致性',
        })
    
    return results


# ===== 5.20 加载状态反馈 =====


# ===== 规则定义列表 =====
RULES = [
    {
        'id': '5.4',
        'name': 'AI复制按钮',
        'level': 'problem',
        'category': 'ui_design',
        'module_id': '5',
        'applicable_types': ['web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查AI生成内容是否有一键复制功能',
        'check': check_5_4_ai_copy_button,
    },
    {
        'id': '5.5',
        'name': 'AI头像/标识',
        'level': 'problem',
        'category': 'ui_design',
        'module_id': '5',
        'applicable_types': ['web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查AI交互是否有明显的AI标识',
        'check': check_5_5_ai_avatar,
    },
    {
        'id': '5.7',
        'name': 'emoji图标',
        'level': 'problem',
        'category': 'ui_design',
        'module_id': '5',
        'applicable_types': ['web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查是否使用emoji作为图标替代',
        'check': check_5_7_emoji_icon,
    },
    {
        'id': '5.8',
        'name': '硬编码色值',
        'level': 'problem',
        'category': 'ui_design',
        'module_id': '5',
        'applicable_types': ['web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查CSS/内联样式中的硬编码颜色',
        'check': check_5_8_hardcoded_colors,
    },
    {
        'id': '5.9',
        'name': '卡片圆角',
        'level': 'problem',
        'category': 'ui_design',
        'module_id': '5',
        'applicable_types': ['web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查border-radius是否统一规范',
        'check': check_5_9_card_border_radius,
    },
    {
        'id': '5.10',
        'name': '按钮高度',
        'level': 'problem',
        'category': 'ui_design',
        'module_id': '5',
        'applicable_types': ['web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查按钮最小高度是否符合可访问性要求',
        'check': check_5_10_button_height,
    },
    {
        'id': '5.14',
        'name': '深色模式',
        'level': 'suggestion',
        'category': 'ui_design',
        'module_id': '5',
        'applicable_types': ['web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查是否支持深色模式（非必须）',
        'check': check_5_14_dark_mode,
    },
    {
        'id': '5.15',
        'name': '品牌色一致性',
        'level': 'problem',
        'category': 'ui_design',
        'module_id': '5',
        'applicable_types': ['web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查品牌色是否统一使用',
        'check': check_5_15_brand_color,
    },
    {
        'id': '5.16',
        'name': 'CSS变量使用',
        'level': 'problem',
        'category': 'ui_design',
        'module_id': '5',
        'applicable_types': ['web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查是否使用CSS变量管理主题设计令牌',
        'check': check_5_16_css_variables,
    },
    {
        'id': '5.17',
        'name': '字体字号层级',
        'level': 'problem',
        'category': 'ui_design',
        'module_id': '5',
        'applicable_types': ['web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查字号种类是否过多，建议精简到6-8种',
        'check': check_5_17_font_size_hierarchy,
    },
    {
        'id': '5.18',
        'name': '间距一致性',
        'level': 'problem',
        'category': 'ui_design',
        'module_id': '5',
        'applicable_types': ['web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查间距值是否过多，建议使用8px网格系统',
        'check': check_5_18_spacing_consistency,
    },
]
