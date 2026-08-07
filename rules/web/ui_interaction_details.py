"""
Web/H5交互细节规则集
从 frontend_rules.py 拆分而来，包含 UI 交互与细节规范:
  5.11 空状态 / 5.12 ErrorBoundary / 5.20 加载反馈
  5.21 安全区域 / 5.22 图标一致性 / 5.25 表单Label
  5.26 交互状态 / 5.27 图片尺寸 / 5.28 禁用状态
"""

import re
import os
from typing import List, Dict, Any

def check_5_11_empty_state(context) -> List[Dict]:
    """5.11 空状态组件 - 检查是否有空状态处理"""
    results = []
    
    if not context.is_web_frontend():
        return results
    
    front_files = context.find_files([".tsx", ".jsx", ".ts", ".js"])
    all_content = ""
    for f in front_files:
        all_content += context.safe_read(f) + "\n"
    
    has_list = bool(re.search(r'list|List|table|Table|data|Data', all_content))
    has_empty = bool(re.search(r'empty|noData|no-data|EmptyState|placeholder.*暂无|空状态', all_content, re.IGNORECASE))
    
    if has_list and not has_empty:
        results.append({
            'id': '5.11',
            'name': '空状态组件',
            'level': 'warning',
            'message': '检测到列表/数据展示但未检测到空状态组件',
            'file': '',
            'line': 0,
            'fix': '为列表/数据展示添加空状态占位，提升用户体验',
        })
    
    return results


# ===== 5.12 错误兜底 =====


def check_5_12_error_boundary(context) -> List[Dict]:
    """5.12 错误兜底 - 检查是否有ErrorBoundary错误边界"""
    results = []
    
    if not context.is_web_frontend():
        return results
    
    front_files = context.find_files([".tsx", ".jsx", ".ts", ".js"])
    all_content = ""
    for f in front_files:
        all_content += context.safe_read(f) + "\n"
    
    has_error_boundary = bool(re.search(r'ErrorBoundary|errorBoundary|componentDidCatch|getDerivedStateFromError', all_content, re.IGNORECASE))
    
    if not has_error_boundary:
        results.append({
            'id': '5.12',
            'name': '错误兜底',
            'level': 'warning',
            'message': '未检测到ErrorBoundary错误边界组件',
            'file': '',
            'line': 0,
            'fix': '添加React ErrorBoundary捕获渲染错误，避免白屏',
        })
    
    return results


# ===== 5.14 深色模式 =====


def check_5_20_loading_feedback(context) -> List[Dict]:
    """5.20 加载状态反馈 - 检查异步操作是否有loading状态"""
    results = []
    
    if not context.is_web_frontend():
        return results
    
    front_files = context.find_files([".tsx", ".jsx", ".ts", ".js"])
    all_content = ""
    for f in front_files:
        all_content += context.safe_read(f) + "\n"
    
    loading_count = len(re.findall(r'loading|isLoading|setLoading|spinner|skeleton', all_content, re.IGNORECASE))
    async_count = len(re.findall(r'useEffect|fetch\(|axios|useSWR|useQuery', all_content, re.IGNORECASE))
    
    if async_count > 0 and loading_count == 0:
        results.append({
            'id': '5.20',
            'name': '加载状态反馈',
            'level': 'warning',
            'message': f"检测到 {async_count} 处异步操作但无loading状态",
            'file': '',
            'line': 0,
            'fix': '为异步操作添加loading/skeleton状态，提升用户体验',
        })
    
    return results


# ===== 5.21 安全区域适配 =====


def check_5_21_safe_area(context) -> List[Dict]:
    """5.21 安全区域适配 - 检查移动端安全区域适配"""
    results = []
    
    if not context.is_web_frontend():
        return results
    
    front_files = context.find_files([".tsx", ".jsx", ".ts", ".js", ".css", ".scss"])
    all_content = ""
    for f in front_files:
        all_content += context.safe_read(f) + "\n"
    
    has_safe_area = bool(re.search(r'safe-area|env\(safe-area|viewport-fit', all_content, re.IGNORECASE))
    
    if not has_safe_area:
        # 仅在有移动端相关内容时报
        has_mobile = bool(re.search(r'mobile|phone|iphone|移动端|H5', all_content, re.IGNORECASE))
        if has_mobile:
            results.append({
                'id': '5.21',
                'name': '安全区域适配',
                'level': 'warning',
                'message': '未检测到安全区域适配(iPhone刘海/底部)',
                'file': '',
                'line': 0,
                'fix': '添加env(safe-area-inset-*)适配，兼容iPhone刘海屏',
            })
    
    return results


# ===== 5.22 图标风格一致性 =====


def check_5_22_icon_consistency(context) -> List[Dict]:
    """5.22 图标风格一致性 - 检查是否统一使用一种图标库"""
    results = []
    
    if not context.is_web_frontend():
        return results
    
    front_files = context.find_files([".tsx", ".jsx", ".ts", ".js"])
    all_content = ""
    for f in front_files:
        all_content += context.safe_read(f) + "\n"
    
    icon_libs = set()
    if re.search(r'lucide-react', all_content):
        icon_libs.add("lucide-react")
    if re.search(r'@heroicons', all_content):
        icon_libs.add("heroicons")
    if re.search(r'@ant-design/icons', all_content):
        icon_libs.add("antd-icons")
    if re.search(r'react-icons', all_content):
        icon_libs.add("react-icons")
    if re.search(r'@mui/icons-material', all_content):
        icon_libs.add("mui-icons")
    
    if len(icon_libs) > 1:
        results.append({
            'id': '5.22',
            'name': '图标风格一致性',
            'level': 'warning',
            'message': f"检测到 {len(icon_libs)} 种图标库: {', '.join(sorted(icon_libs))}",
            'file': '',
            'line': 0,
            'fix': '统一使用一种图标库，保持图标风格一致性',
        })
    
    return results


# ===== 5.25 表单标签可见性 =====


def check_5_25_form_label(context) -> List[Dict]:
    """5.25 表单标签可见性 - 检查表单输入是否有label"""
    results = []
    
    if not context.is_web_frontend():
        return results
    
    front_files = context.find_files([".tsx", ".jsx", ".ts", ".js", ".html"])
    all_content = ""
    for f in front_files:
        all_content += context.safe_read(f) + "\n"
    
    form_labels = len(re.findall(r'<label|htmlFor|aria-label', all_content, re.IGNORECASE))
    form_inputs = len(re.findall(r'<input|<textarea|<select', all_content, re.IGNORECASE))
    
    if form_inputs > 0 and form_labels == 0:
        results.append({
            'id': '5.25',
            'name': '表单标签可见性',
            'level': 'warning',
            'message': f"检测到 {form_inputs} 个表单输入但无label标签",
            'file': '',
            'line': 0,
            'fix': '为所有表单输入添加label或aria-label，提升可访问性',
        })
    
    return results


# ===== 5.26 交互状态完整性 =====


def check_5_26_interaction_state(context) -> List[Dict]:
    """5.26 交互状态完整性 - 检查可交互元素是否有hover/active状态"""
    results = []
    
    if not context.is_web_frontend():
        return results
    
    tsx_files = context.find_files([".tsx", ".jsx"])
    css_files = context.find_files([".css", ".scss", ".less"])
    
    all_content = ""
    for f in tsx_files + css_files:
        all_content += context.safe_read(f) + "\n"
    
    hover_count = len(re.findall(r':hover|onMouseEnter|onMouseLeave', all_content, re.IGNORECASE))
    has_button = bool(re.search(r'<button|<Button|button.*className', all_content, re.IGNORECASE))
    
    if has_button and hover_count == 0:
        results.append({
            'id': '5.26',
            'name': '交互状态完整性',
            'level': 'warning',
            'message': '未检测到hover状态处理',
            'file': '',
            'line': 0,
            'fix': '为可交互元素添加hover/active/focus状态，提供视觉反馈',
        })
    
    return results


# ===== 5.27 图片尺寸规范 =====


def check_5_27_image_size(context) -> List[Dict]:
    """5.27 图片尺寸规范 - 检查img标签是否有width/height属性"""
    results = []
    
    if not context.is_web_frontend():
        return results
    
    front_files = context.find_files([".tsx", ".jsx", ".html"])
    all_content = ""
    for f in front_files:
        all_content += context.safe_read(f) + "\n"
    
    img_no_size = len(re.findall(r'<img[^>]+src[^>]*(?!width|height)[^>]*>', all_content, re.IGNORECASE))
    
    if img_no_size > 5:
        results.append({
            'id': '5.27',
            'name': '图片尺寸规范',
            'level': 'warning',
            'message': f"发现 {img_no_size} 个img标签可能缺少width/height属性",
            'file': '',
            'line': 0,
            'fix': '为img标签添加width/height属性防止CLS布局偏移',
        })
    
    return results


# ===== 5.28 禁用状态设计 =====


def check_5_28_disabled_state(context) -> List[Dict]:
    """5.28 禁用状态设计 - 检查按钮是否有disabled状态"""
    results = []
    
    if not context.is_web_frontend():
        return results
    
    front_files = context.find_files([".tsx", ".jsx", ".ts", ".js", ".css", ".scss"])
    all_content = ""
    for f in front_files:
        all_content += context.safe_read(f) + "\n"
    
    disabled_count = len(re.findall(r'disabled|:disabled|aria-disabled', all_content, re.IGNORECASE))
    btn_count = len(re.findall(r'<button|<Button', all_content, re.IGNORECASE))
    
    if btn_count > 0 and disabled_count == 0:
        results.append({
            'id': '5.28',
            'name': '禁用状态设计',
            'level': 'warning',
            'message': f"检测到 {btn_count} 个按钮但无disabled状态处理",
            'file': '',
            'line': 0,
            'fix': '为提交类按钮添加disabled状态样式，防止重复提交',
        })
    
    return results


# ===== 规则定义列表 =====


# ===== 规则定义列表 =====
RULES = [
    {
        'id': '5.11',
        'name': '空状态组件',
        'level': 'problem',
        'category': 'ui_design',
        'module_id': '5',
        'applicable_types': ['web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查列表/数据展示是否有空状态处理',
        'check': check_5_11_empty_state,
    },
    {
        'id': '5.12',
        'name': '错误兜底',
        'level': 'problem',
        'category': 'ui_design',
        'module_id': '5',
        'applicable_types': ['web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查是否有ErrorBoundary错误边界组件',
        'check': check_5_12_error_boundary,
    },
    {
        'id': '5.20',
        'name': '加载状态反馈',
        'level': 'problem',
        'category': 'ui_design',
        'module_id': '5',
        'applicable_types': ['web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查异步操作是否有loading状态反馈',
        'check': check_5_20_loading_feedback,
    },
    {
        'id': '5.21',
        'name': '安全区域适配',
        'level': 'problem',
        'category': 'ui_design',
        'module_id': '5',
        'applicable_types': ['web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查移动端安全区域适配',
        'check': check_5_21_safe_area,
    },
    {
        'id': '5.22',
        'name': '图标风格一致性',
        'level': 'problem',
        'category': 'ui_design',
        'module_id': '5',
        'applicable_types': ['web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查是否统一使用一种图标库',
        'check': check_5_22_icon_consistency,
    },
    {
        'id': '5.25',
        'name': '表单标签可见性',
        'level': 'problem',
        'category': 'ui_design',
        'module_id': '5',
        'applicable_types': ['web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查表单输入是否有label标签',
        'check': check_5_25_form_label,
    },
    {
        'id': '5.26',
        'name': '交互状态完整性',
        'level': 'problem',
        'category': 'ui_design',
        'module_id': '5',
        'applicable_types': ['web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查可交互元素是否有hover/active状态',
        'check': check_5_26_interaction_state,
    },
    {
        'id': '5.27',
        'name': '图片尺寸规范',
        'level': 'problem',
        'category': 'ui_design',
        'module_id': '5',
        'applicable_types': ['web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查img标签是否有width/height属性防止CLS',
        'check': check_5_27_image_size,
    },
    {
        'id': '5.28',
        'name': '禁用状态设计',
        'level': 'problem',
        'category': 'ui_design',
        'module_id': '5',
        'applicable_types': ['web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查按钮是否有disabled状态处理',
        'check': check_5_28_disabled_state,
    },
]
