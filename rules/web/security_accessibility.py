"""
Web端安全P0补充规则集 - 无障碍可访问性 (M15)
从 security_p0.py 拆分而来，包含 WCAG 可访问性检查:
  WEB-SEC-P0-004 lang属性缺失检测
  WEB-SEC-P0-005 键盘可访问性检测
  WEB-SEC-P0-006 ARIA属性有效性检测
  WEB-SEC-P0-007 颜色对比度检测
"""

import re
import os
from typing import List, Dict, Any

def _get_line_number(content: str, match_start: int) -> int:
    return content[:match_start].count('\n') + 1


def _is_comment_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith(('//', '/*', '*', '<!--'))


def _is_test_file(filepath: str) -> bool:
    basename = os.path.basename(filepath).lower()
    return any(x in basename for x in ['.test.', '.spec.', 'test_', '_test.', 'mock', 'fixture'])


# ============================================================
# WEB-SEC-P0-001: localStorage/sessionStorage敏感数据检测
# 对应OWASP客户端安全Top 10 #7
# ============================================================


def check_web_sec_p0_004_lang_attribute(context) -> List[Dict]:
    """WEB-SEC-P0-004 HTML lang属性检测 - 检查页面是否设置了lang属性声明语言"""
    results = []
    
    if not context.is_web_frontend():
        return results
    
    html_files = context.find_files([".html", ".htm"])
    
    # 找主index.html
    index_files = [f for f in html_files if os.path.basename(f).lower() in ('index.html', 'index.htm')]
    check_files = index_files or html_files[:1]
    
    if not check_files:
        # JSX/TSX项目检查入口文件
        jsx_files = context.find_files([".jsx", ".tsx"])
        main_files = [f for f in jsx_files if os.path.basename(f).lower() in 
                     ('app.tsx', 'app.jsx', '_app.tsx', '_app.jsx', 'main.tsx', 'main.jsx', 'index.tsx', 'index.jsx')]
        if main_files:
            for f in main_files:
                content = context.safe_read(f)
                if '<html' in content or 'Html' in content or 'createRoot' in content:
                    # 检查是否有lang属性设置
                    if not re.search(r'lang\s*=\s*["\'][a-z]{2}', content, re.IGNORECASE):
                        results.append({
                            'id': 'WEB-SEC-P0-004',
                            'name': 'HTML lang属性检测',
                            'level': 'warning',
                            'message': '未检测到页面lang属性设置',
                            'file': f,
                            'line': 0,
                            'fix': '在<html>标签中添加lang="zh-CN"或对应语言属性，提升可访问性',
                            'category': 'web_security',
                        })
                    break
        return results
    
    for fpath in check_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        # 检查<html>标签是否有lang属性
        html_tag = re.search(r'<html[^>]*>', content, re.IGNORECASE)
        if html_tag:
            if not re.search(r'\blang\s*=\s*["\'][a-zA-Z-]+["\']', html_tag.group(0), re.IGNORECASE):
                results.append({
                    'id': 'WEB-SEC-P0-004',
                    'name': 'HTML lang属性检测',
                    'level': 'warning',
                    'message': '页面<html>标签缺少lang属性',
                    'file': fpath,
                    'line': _get_line_number(content, html_tag.start()),
                    'snippet': html_tag.group(0)[:100],
                    'fix': '在<html>标签中添加lang="zh-CN"或对应语言属性，满足WCAG 3.1.1可访问性要求',
                    'category': 'web_security',
                })
    
    return results


# ============================================================
# WEB-SEC-P0-005: 键盘可访问性检测（div按钮模式）
# 对应WCAG 2.2 2.1.1 Keyboard (A) - P0
# ============================================================


def check_web_sec_p0_005_keyboard_accessible(context) -> List[Dict]:
    """WEB-SEC-P0-005 键盘可访问性检测 - 检查使用onclick的div/span是否支持键盘访问"""
    results = []
    
    if not context.is_web_frontend():
        return results
    
    jsx_files = context.find_files([".jsx", ".tsx", ".vue"])
    if not jsx_files:
        return results
    
    issues = []
    
    for fpath in jsx_files:
        if _is_test_file(fpath):
            continue
        
        content = context.safe_read(fpath)
        if not content:
            continue
        
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if _is_comment_line(stripped):
                continue
            
            # 检测div/span/li等非交互元素使用onClick但没有tabIndex和键盘事件
            div_onclick = re.search(
                r'<(div|span|li|p|div)\s[^>]*onClick\s*=\s*\{',
                line, re.IGNORECASE)
            
            if div_onclick:
                # 检查同行或附近是否有tabIndex和onKeyDown/onKeyUp
                context_lines = '\n'.join(lines[max(0, i-2):min(len(lines), i+3)])
                has_tabindex = bool(re.search(r'tabIndex\s*=', context_lines, re.IGNORECASE))
                has_keyhandler = bool(re.search(r'onKey(Down|Up|Press)\s*=', context_lines, re.IGNORECASE))
                has_role = bool(re.search(r'role\s*=\s*["\'](button|link|menuitem)["\']', context_lines, re.IGNORECASE))
                
                if not has_tabindex or not has_keyhandler:
                    issues.append({
                        'file': fpath,
                        'line': i,
                        'desc': f'{div_onclick.group(1)}元素onClick缺少键盘可访问性',
                        'snippet': stripped[:80],
                    })
                    if len(issues) >= 20:
                        break
        
        if len(issues) >= 20:
            break
    
    if issues:
        results.append({
            'id': 'WEB-SEC-P0-005',
            'name': '键盘可访问性检测',
            'level': 'warning',
            'message': f'检测到 {len(issues)} 处非交互元素onClick可能缺少键盘访问支持',
            'detail': '示例: ' + '; '.join(f"{os.path.basename(i['file'])}:{i['line']}" for i in issues[:5]),
            'file': issues[0]['file'],
            'line': issues[0]['line'],
            'snippet': issues[0]['snippet'],
            'fix': '使用<button>等原生交互元素替代div+onClick；如必须用div，添加role="button"、tabIndex={0}和键盘事件',
            'category': 'web_security',
        })
    
    return results


# ============================================================
# WEB-SEC-P0-006: ARIA属性有效性检测
# 对应WCAG 2.2 4.1.2 Name, Role, Value (A) - P0
# ============================================================


def check_web_sec_p0_006_aria_validity(context) -> List[Dict]:
    """WEB-SEC-P0-006 ARIA属性有效性检测 - 检查ARIA属性和角色是否有效"""
    results = []
    
    if not context.is_web_frontend():
        return results
    
    html_files = context.find_files([".html", ".htm", ".jsx", ".tsx", ".vue"])
    if not html_files:
        return results
    
    # 常见的有效ARIA角色（部分列表）
    valid_roles = {
        'alert', 'alertdialog', 'application', 'article', 'banner', 'button',
        'checkbox', 'combobox', 'complementary', 'contentinfo', 'dialog',
        'document', 'feed', 'figure', 'form', 'grid', 'gridcell', 'group',
        'heading', 'img', 'link', 'list', 'listbox', 'listitem', 'log',
        'main', 'marquee', 'math', 'menu', 'menubar', 'menuitem',
        'menuitemcheckbox', 'menuitemradio', 'navigation', 'none', 'note',
        'option', 'presentation', 'progressbar', 'radio', 'radiogroup',
        'region', 'row', 'rowgroup', 'rowheader', 'scrollbar', 'search',
        'searchbox', 'separator', 'slider', 'spinbutton', 'status',
        'switch', 'tab', 'table', 'tablist', 'tabpanel', 'term', 'textbox',
        'timer', 'toolbar', 'tooltip', 'tree', 'treegrid', 'treeitem',
    }
    
    # 常见有效ARIA属性（部分列表）
    valid_aria_attrs = {
        'aria-activedescendant', 'aria-atomic', 'aria-autocomplete', 'aria-busy',
        'aria-checked', 'aria-colcount', 'aria-colindex', 'aria-colspan',
        'aria-controls', 'aria-current', 'aria-describedby', 'aria-description',
        'aria-details', 'aria-disabled', 'aria-dropeffect', 'aria-errormessage',
        'aria-expanded', 'aria-flowto', 'aria-grabbed', 'aria-haspopup',
        'aria-hidden', 'aria-invalid', 'aria-keyshortcuts', 'aria-label',
        'aria-labelledby', 'aria-level', 'aria-live', 'aria-modal', 'aria-multiline',
        'aria-multiselectable', 'aria-orientation', 'aria-owns', 'aria-placeholder',
        'aria-posinset', 'aria-pressed', 'aria-readonly', 'aria-relevant',
        'aria-required', 'aria-roledescription', 'aria-rowcount', 'aria-rowindex',
        'aria-rowspan', 'aria-selected', 'aria-setsize', 'aria-sort',
        'aria-valuemax', 'aria-valuemin', 'aria-valuenow', 'aria-valuetext',
    }
    
    issues = []
    
    for fpath in html_files:
        if _is_test_file(fpath):
            continue
        
        content = context.safe_read(fpath)
        if not content:
            continue
        
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if _is_comment_line(line):
                continue
            
            # 检查无效role
            role_matches = re.finditer(r'role\s*=\s*["\']([^"\']+)["\']', line, re.IGNORECASE)
            for m in role_matches:
                roles = m.group(1).lower().split()
                for role in roles:
                    if role not in valid_roles and role != '':
                        # 可能是自定义role，只做警告
                        if not role.startswith('data-') and len(role) < 30:
                            issues.append({
                                'file': fpath,
                                'line': i,
                                'desc': f'可能无效的ARIA role: {role}',
                                'snippet': line.strip()[:80],
                            })
                        break
            
            # 检查明显无效的aria-*属性
            aria_matches = re.finditer(r'\b(aria-[a-z-]+)\s*[={]', line, re.IGNORECASE)
            for m in aria_matches:
                attr = m.group(1).lower()
                if attr.startswith('aria-') and attr not in valid_aria_attrs:
                    # 可能是拼写错误
                    if len(attr) > 5 and not attr.endswith('-'):
                        issues.append({
                            'file': fpath,
                            'line': i,
                            'desc': f'可能无效的ARIA属性: {attr}',
                            'snippet': line.strip()[:80],
                        })
                        break
            
            if len(issues) >= 30:
                break
        
        if len(issues) >= 30:
            break
    
    if issues:
        results.append({
            'id': 'WEB-SEC-P0-006',
            'name': 'ARIA属性有效性检测',
            'level': 'warning',
            'message': f'检测到 {len(issues)} 处可能无效的ARIA角色或属性',
            'detail': '示例: ' + '; '.join(f"{os.path.basename(i['file'])}:{i['line']} {i['desc']}" for i in issues[:5]),
            'file': issues[0]['file'],
            'line': issues[0]['line'],
            'snippet': issues[0]['snippet'],
            'fix': '使用标准ARIA角色和属性，参考WAI-ARIA规范，避免自定义或拼写错误的ARIA属性',
            'category': 'web_security',
        })
    
    return results


# ============================================================
# WEB-SEC-P0-007: 颜色对比度检测（简化版）
# 对应WCAG 2.2 1.4.3 Contrast (Minimum) (AA) - P0
# ============================================================


def check_web_sec_p0_007_color_contrast(context) -> List[Dict]:
    """WEB-SEC-P0-007 颜色对比度检测 - 检查CSS中前景/背景色对比度不足的情况"""
    results = []
    
    if not context.is_web_frontend():
        return results
    
    css_files = context.find_files([".css", ".scss", ".less"])
    if not css_files:
        return results
    
    def _hex_to_rgb(hex_color):
        """将十六进制颜色转换为RGB"""
        hex_color = hex_color.lstrip('#')
        if len(hex_color) == 3:
            hex_color = ''.join(c * 2 for c in hex_color)
        if len(hex_color) == 6:
            return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        return None
    
    def _luminance(r, g, b):
        """计算相对亮度"""
        def _to_linear(c):
            c = c / 255.0
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        
        return 0.2126 * _to_linear(r) + 0.7152 * _to_linear(g) + 0.0722 * _to_linear(b)
    
    def _contrast_ratio(color1, color2):
        """计算对比度"""
        rgb1 = _hex_to_rgb(color1)
        rgb2 = _hex_to_rgb(color2)
        if not rgb1 or not rgb2:
            return None
        
        l1 = _luminance(*rgb1)
        l2 = _luminance(*rgb2)
        
        lighter = max(l1, l2)
        darker = min(l1, l2)
        
        return (lighter + 0.05) / (darker + 0.05)
    
    issues = []
    
    for fpath in css_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        # 简化检测：查找同一选择器块中同时有color和background-color的情况
        # 这是一个简化版本，完整的对比度检测需要DOM树分析
        blocks = re.split(r'\}', content)
        
        for block in blocks:
            color_match = re.search(r'color\s*:\s*(#[0-9a-fA-F]{3,8})', block, re.IGNORECASE)
            bg_match = re.search(r'background(?:-color)?\s*:\s*(#[0-9a-fA-F]{3,8})', block, re.IGNORECASE)
            
            if color_match and bg_match:
                fg_color = color_match.group(1)
                bg_color = bg_match.group(1)
                
                ratio = _contrast_ratio(fg_color, bg_color)
                if ratio and ratio < 4.5:
                    # 找到行号（近似）
                    block_start = content.find(block)
                    line_num = content[:block_start].count('\n') + 1
                    
                    issues.append({
                        'file': fpath,
                        'line': line_num,
                        'desc': f'对比度{ratio:.2f}:1 < 4.5:1 ({fg_color} on {bg_color})',
                        'snippet': f'color: {fg_color}; background: {bg_color}',
                    })
                    
                    if len(issues) >= 20:
                        break
        
        if len(issues) >= 20:
            break
    
    if issues:
        results.append({
            'id': 'WEB-SEC-P0-007',
            'name': '颜色对比度检测',
            'level': 'warning',
            'message': f'检测到 {len(issues)} 处颜色对比度低于WCAG AA标准(4.5:1)',
            'detail': '示例: ' + '; '.join(f"{os.path.basename(i['file'])}:{i['line']} {i['desc']}" for i in issues[:5]),
            'file': issues[0]['file'],
            'line': issues[0]['line'],
            'snippet': issues[0]['snippet'],
            'fix': '调整前景/背景色使对比度达到4.5:1以上（正常文本），满足WCAG 2.2 1.4.3可访问性要求',
            'category': 'web_security',
        })
    
    return results


# ============================================================
# WEB-SEC-P0-008: HTTPS强制检测
# 对应Lighthouse Best Practices P0
# ============================================================


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'WEB-SEC-P0-004',
        'name': 'HTML lang属性检测',
        'level': 'problem',
        'category': 'web_security',
        'module_id': '15',
        'applicable_types': ['web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查页面是否设置了lang属性声明语言（WCAG 3.1.1 P0）',
        'check': check_web_sec_p0_004_lang_attribute,
    },
    {
        'id': 'WEB-SEC-P0-005',
        'name': '键盘可访问性检测',
        'level': 'problem',
        'category': 'web_security',
        'module_id': '15',
        'applicable_types': ['web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查非交互元素onClick是否支持键盘访问（WCAG 2.1.1 P0）',
        'check': check_web_sec_p0_005_keyboard_accessible,
    },
    {
        'id': 'WEB-SEC-P0-006',
        'name': 'ARIA属性有效性检测',
        'level': 'problem',
        'category': 'web_security',
        'module_id': '15',
        'applicable_types': ['web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查ARIA角色和属性是否有效（WCAG 4.1.2 P0）',
        'check': check_web_sec_p0_006_aria_validity,
    },
    {
        'id': 'WEB-SEC-P0-007',
        'name': '颜色对比度检测',
        'level': 'problem',
        'category': 'web_security',
        'module_id': '15',
        'applicable_types': ['web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查CSS颜色对比度是否满足WCAG AA标准4.5:1（WCAG 1.4.3 P0）',
        'check': check_web_sec_p0_007_color_contrast,
    },
]
