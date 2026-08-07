"""
小程序WXSS规则集
微信小程序样式表检查
包含: rpx/px混用、!important滥用、选择器嵌套过深、内联style硬编码、
      全局选择器污染、position:fixed滥用、未使用样式类

v3.5: 每条规则带suggestion_code修复示例
"""

import re
import os
from typing import List, Dict, Any, Set


def _get_line_number(content: str, pos: int) -> int:
    return content[:pos].count('\n') + 1


def _truncate(s: str, max_len: int = 120) -> str:
    s = s.strip()
    return s[:max_len] + '...' if len(s) > max_len else s


# ===== WXSS-001 rpx/px混用检测 =====
def check_wxss_001_rpx_px_mix(context) -> List[Dict]:
    """WXSS-001 rpx/px混用 - 同一文件中同时使用rpx和px单位，导致不同设备适配不一致"""
    results = []
    
    wxss_files = context.find_files([".wxss"])
    if not wxss_files:
        return results
    
    for fpath in wxss_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        has_rpx = bool(re.search(r'\d+rpx\b', content))
        has_px = bool(re.search(r'\d+px\b', content))
        
        if has_rpx and has_px:
            # 统计各自数量
            rpx_count = len(re.findall(r'\d+rpx\b', content))
            px_count = len(re.findall(r'\d+px\b', content))
            # 找到第一个px使用的行作为示例
            first_px = re.search(r'\d+px\b', content)
            line_num = _get_line_number(content, first_px.start()) if first_px else 0
            
            results.append({
                'id': 'WXSS-001',
                'name': 'rpx/px混用',
                'level': 'warning',
                'message': f'同时使用rpx({rpx_count}处)和px({px_count}处)单位，不同设备适配可能不一致',
                'detail': f'rpx是响应式单位(750rpx=屏幕宽度)，px是固定像素。混用会导致大屏小屏显示比例不一致。\n第一个px使用位置: 第{line_num}行',
                'file': fpath,
                'line': line_num,
                'fix': '统一使用rpx作为尺寸单位，px仅用于边框(1px)等不需要响应式的场景',
                'suggestion_code': (
                    '/* ❌ 混用rpx和px */\n'
                    '.card {\n'
                    '  width: 300rpx;\n'
                    '  padding: 10px;  /* px在大屏会偏小 */\n'
                    '}\n\n'
                    '/* ✅ 统一使用rpx */\n'
                    '.card {\n'
                    '  width: 300rpx;\n'
                    '  padding: 20rpx;\n'
                    '  border: 1px solid #eee;  /* 1px边框例外，不需要响应式 */\n'
                    '}'
                ),
            })
    
    return results


# ===== WXSS-002 !important滥用 =====
def check_wxss_002_important_abuse(context) -> List[Dict]:
    """WXSS-002 !important滥用 - 过多使用!important表明样式优先级混乱"""
    results = []
    
    wxss_files = context.find_files([".wxss"])
    if not wxss_files:
        return results
    
    IMPORTANT_THRESHOLD = 5  # 超过5个!important视为滥用
    
    for fpath in wxss_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        important_count = len(re.findall(r'!\s*important', content, re.IGNORECASE))
        
        if important_count >= IMPORTANT_THRESHOLD:
            # 找前3个!important的位置作为示例
            samples = []
            for m in re.finditer(r'!\s*important', content, re.IGNORECASE):
                line_num = _get_line_number(content, m.start())
                line_content = content.split('\n')[line_num - 1] if line_num <= len(content.split('\n')) else ''
                samples.append(f'第{line_num}行: {_truncate(line_content)}')
                if len(samples) >= 3:
                    break
            
            results.append({
                'id': 'WXSS-002',
                'name': '!important滥用',
                'level': 'warning',
                'message': f'该文件使用了{important_count}个!important，表明样式优先级混乱',
                'detail': '过多!important说明CSS优先级管理失控，后续维护时难以覆盖样式。\n示例:\n' + '\n'.join(samples),
                'file': fpath,
                'line': 0,
                'fix': '通过提高选择器特异性来解决优先级问题，而非使用!important',
                'suggestion_code': (
                    '/* ❌ 用!important强制覆盖 */\n'
                    '.card .title { color: red !important; }\n'
                    '.card .title.active { color: blue !important; }\n\n'
                    '/* ✅ 提高选择器特异性 */\n'
                    '.card .title { color: red; }\n'
                    '.card .title.active { color: blue; }  /* 更具体的选择器自然优先 */'
                ),
            })
    
    return results


# ===== WXSS-003 选择器嵌套过深 =====
def check_wxss_003_deep_nesting(context) -> List[Dict]:
    """WXSS-003 选择器嵌套过深 - 超过3级嵌套的选择器影响渲染性能"""
    results = []
    
    wxss_files = context.find_files([".wxss"])
    if not wxss_files:
        return results
    
    MAX_DEPTH = 3
    
    for fpath in wxss_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        # 匹配选择器（规则前的部分）
        # 简单方式：找 } 后到 { 之间的文本
        rule_pattern = re.compile(r'\}\s*([^{}]+)\{', re.DOTALL)
        # 也匹配文件开头第一个规则
        first_rule = re.match(r'\s*([^{}]+)\{', content)
        
        deep_selectors = []
        
        selectors_to_check = []
        if first_rule:
            selectors_to_check.append(first_rule.group(1))
        for m in rule_pattern.finditer(content):
            selectors_to_check.append(m.group(1))
        
        for selector_text in selectors_to_check:
            selector_text = selector_text.strip()
            if not selector_text or selector_text.startswith('@'):
                continue
            
            # 按逗号分割多选择器
            for sel in selector_text.split(','):
                sel = sel.strip()
                if not sel:
                    continue
                # 计算后代选择器深度（空格分隔的组合）
                # 排除伪类/伪元素和属性选择器
                parts = re.split(r'\s+', sel)
                depth = len(parts)
                
                if depth > MAX_DEPTH:
                    line_num = content.find(sel)
                    line_num = _get_line_number(content, line_num) if line_num >= 0 else 0
                    deep_selectors.append({
                        'selector': _truncate(sel, 80),
                        'depth': depth,
                        'line': line_num,
                    })
        
        if deep_selectors:
            samples = deep_selectors[:3]
            sample_text = '; '.join([f'{s["selector"]}({s["depth"]}层)' for s in samples])
            
            results.append({
                'id': 'WXSS-003',
                'name': '选择器嵌套过深',
                'level': 'warning',
                'message': f'{len(deep_selectors)}个选择器嵌套超过{MAX_DEPTH}层，影响渲染性能',
                'detail': f'深层嵌套选择器浏览器需要从右向左匹配，层级越深性能越差。\n示例: {sample_text}',
                'file': fpath,
                'line': samples[0]['line'] if samples else 0,
                'fix': '使用BEM命名规范或增加类名，减少后代选择器嵌套层级',
                'suggestion_code': (
                    '/* ❌ 4层嵌套 */\n'
                    '.page .content .list .item .title { font-size: 28rpx; }\n\n'
                    '/* ✅ BEM命名，1层即可 */\n'
                    '.list-item__title { font-size: 28rpx; }'
                ),
            })
    
    return results


# ===== WXSS-004 内联style硬编码 =====
def check_wxss_004_inline_style(context) -> List[Dict]:
    """WXSS-004 内联style硬编码 - WXML中style属性包含过多样式声明"""
    results = []
    
    wxml_files = context.find_files([".wxml"])
    if not wxml_files:
        return results
    
    INLINE_THRESHOLD = 3  # style属性中超过3个声明视为硬编码
    
    for fpath in wxml_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        # 匹配 style="..." 属性
        style_pattern = re.compile(r'style\s*=\s*["\']([^"\']+)["\']')
        
        issues = []
        for m in style_pattern.finditer(content):
            style_value = m.group(1)
            # 统计声明数量（分号分隔）
            declarations = [d.strip() for d in style_value.split(';') if d.strip()]
            
            if len(declarations) >= INLINE_THRESHOLD:
                line_num = _get_line_number(content, m.start())
                issues.append({
                    'line': line_num,
                    'count': len(declarations),
                    'snippet': _truncate(style_value),
                })
        
        if issues:
            for issue in issues[:5]:
                results.append({
                    'id': 'WXSS-004',
                    'name': '内联style硬编码',
                    'level': 'warning',
                    'message': f"style属性包含{issue['count']}个样式声明，应提取到WXSS类中",
                    'detail': f"位置: 第{issue['line']}行\nstyle: {issue['snippet']}",
                    'file': fpath,
                    'line': issue['line'],
                    'fix': '将内联样式提取到WXSS文件中，通过class引用',
                    'suggestion_code': (
                        '<!-- ❌ 内联style硬编码 -->\n'
                        '<view style="display:flex; justify-content:center; align-items:center; height:100rpx;">\n\n'
                        '<!-- ✅ 提取到WXSS类 -->\n'
                        '<view class="center-row">\n\n'
                        '/* WXSS */\n'
                        '.center-row {\n'
                        '  display: flex;\n'
                        '  justify-content: center;\n'
                        '  align-items: center;\n'
                        '  height: 100rpx;\n'
                        '}'
                    ),
                })
    
    return results


# ===== WXSS-005 全局选择器污染 =====
def check_wxss_005_global_selector(context) -> List[Dict]:
    """WXSS-005 全局选择器污染 - app.wxss中使用过于宽泛的标签选择器"""
    results = []
    
    # 只检查 app.wxss
    all_wxss = context.find_files([".wxss"])
    app_wxss_files = [f for f in all_wxss if os.path.basename(f) == 'app.wxss']
    
    if not app_wxss_files:
        return results
    
    # 宽泛标签选择器：直接对标签名设置样式（如 view {}, text {}）
    # 排除 page {}（这是合法的全局样式）
    BROAD_TAGS = {'view', 'text', 'image', 'button', 'input', 'scroll-view', 'swiper', 'navigator'}
    
    for fpath in app_wxss_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        issues = []
        # 匹配 标签名 { 或 标签名, 
        tag_pattern = re.compile(r'(?:^|\})\s*(\w[\w-]*)\s*(?:[,:\s{])', re.MULTILINE)
        
        for m in tag_pattern.finditer(content):
            tag = m.group(1).lower()
            if tag in BROAD_TAGS:
                line_num = _get_line_number(content, m.start())
                line_content = content.split('\n')[line_num - 1] if line_num <= len(content.split('\n')) else ''
                issues.append({
                    'tag': tag,
                    'line': line_num,
                    'snippet': _truncate(line_content),
                })
        
        # 去重
        seen_tags = set()
        unique_issues = []
        for issue in issues:
            if issue['tag'] not in seen_tags:
                seen_tags.add(issue['tag'])
                unique_issues.append(issue)
        
        if unique_issues:
            tag_list = ', '.join([f'{i["tag"]}' for i in unique_issues])
            results.append({
                'id': 'WXSS-005',
                'name': '全局选择器污染',
                'level': 'warning',
                'message': f'app.wxss中对标签({tag_list})直接设置样式，会影响所有页面',
                'detail': f'全局标签选择器会污染所有页面的同名标签，难以局部覆盖。\n示例: 第{unique_issues[0]["line"]}行 {unique_issues[0]["snippet"]}',
                'file': fpath,
                'line': unique_issues[0]['line'],
                'fix': '使用class选择器替代标签选择器，或在具体页面内限定作用域',
                'suggestion_code': (
                    '/* app.wxss */\n'
                    '/* ❌ 全局标签选择器，影响所有页面 */\n'
                    'view { box-sizing: border-box; }\n'
                    'text { color: #333; }\n\n'
                    '/* ✅ 使用class，需要时引用 */\n'
                    '.box-border { box-sizing: border-box; }\n'
                    '.text-default { color: #333; }\n\n'
                    '/* 例外: page {} 是合法的，用于设置全局背景 */\n'
                    'page { background-color: #f5f5f5; }  /* OK */'
                ),
            })
    
    return results


# ===== WXSS-006 position:fixed滥用 =====
def check_wxss_006_fixed_abuse(context) -> List[Dict]:
    """WXSS-006 position:fixed滥用 - 过多position:fixed影响滚动性能"""
    results = []
    
    wxss_files = context.find_files([".wxss"])
    if not wxss_files:
        return results
    
    FIXED_THRESHOLD = 4  # 超过4个fixed视为滥用
    
    for fpath in wxss_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        fixed_count = len(re.findall(r'position\s*:\s*fixed', content, re.IGNORECASE))
        
        if fixed_count >= FIXED_THRESHOLD:
            # 找前3个位置
            samples = []
            for m in re.finditer(r'position\s*:\s*fixed', content, re.IGNORECASE):
                line_num = _get_line_number(content, m.start())
                samples.append(f'第{line_num}行')
                if len(samples) >= 3:
                    break
            
            results.append({
                'id': 'WXSS-006',
                'name': 'position:fixed滥用',
                'level': 'warning',
                'message': f'该文件使用了{fixed_count}个position:fixed，过多fixed元素影响滚动性能',
                'detail': f'position:fixed创建独立的渲染层，过多会导致GPU合成层爆炸。\n位置: {", ".join(samples)}',
                'file': fpath,
                'line': 0,
                'fix': '使用position:sticky替代固定定位，或减少固定元素数量',
                'suggestion_code': (
                    '/* ❌ position:fixed 每个都创建合成层 */\n'
                    '.header { position: fixed; top: 0; }\n'
                    '.footer { position: fixed; bottom: 0; }\n'
                    '.sidebar { position: fixed; left: 0; }\n'
                    '.float-btn { position: fixed; right: 20rpx; bottom: 100rpx; }\n\n'
                    '/* ✅ position:sticky 不脱离文档流，性能更好 */\n'
                    '.header { position: sticky; top: 0; z-index: 100; }\n'
                    '/* footer/float-btn保留fixed（确实需要脱离文档流的场景） */'
                ),
            })
    
    return results


# ===== WXSS-007 未使用样式类检测 =====
def check_wxss_007_unused_class(context) -> List[Dict]:
    """WXSS-007 未使用样式类 - WXSS中定义的类在对应WXML中未使用"""
    results = []
    
    wxss_files = context.find_files([".wxss"])
    wxml_files = context.find_files([".wxml"])
    
    if not wxss_files or not wxml_files:
        return results
    
    # 构建WXML中所有类名的集合
    all_wxml_classes: Set[str] = set()
    for wfpath in wxml_files:
        content = context.safe_read(wfpath)
        if not content:
            continue
        # 匹配 class="..." 或 class='...'
        for m in re.finditer(r'class\s*=\s*["\']([^"\']+)["\']', content):
            classes = m.group(1).split()
            all_wxml_classes.update(classes)
    
    if not all_wxml_classes:
        return results
    
    # 检查每个WXSS文件（排除app.wxss，因为它的类可能被任何页面引用）
    for fpath in wxss_files:
        basename = os.path.basename(fpath)
        if basename == 'app.wxss':
            continue
        
        content = context.safe_read(fpath)
        if not content:
            continue
        
        # 提取WXSS中定义的类名
        # 匹配 .classname { 或 .classname,
        defined_classes = set()
        # 去除注释
        clean_content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        for m in re.finditer(r'\.([a-zA-Z_][\w-]*)', clean_content):
            cls = m.group(1)
            # 排除伪类前缀（如 .item:hover 中的 item 是类名，hover 是伪类）
            defined_classes.add(cls)
        
        if not defined_classes:
            continue
        
        # 找未使用的类
        unused = defined_classes - all_wxml_classes
        
        # 过滤掉可能是动态拼接的类名（如包含 _active _selected 等后缀的变体）
        # 如果基础类名被使用，则认为变体也可能被使用
        filtered_unused = set()
        for cls in unused:
            # 检查是否是某个已使用类名的变体
            base_used = False
            for used in all_wxml_classes:
                if cls.startswith(used + '_') or cls.startswith(used + '-'):
                    base_used = True
                    break
            if not base_used:
                filtered_unused.add(cls)
        
        if len(filtered_unused) >= 3:  # 至少3个未使用才报告
            sample = list(filtered_unused)[:5]
            results.append({
                'id': 'WXSS-007',
                'name': '未使用样式类',
                'level': 'info',
                'message': f'{len(filtered_unused)}个样式类在WXML中未使用',
                'detail': f'未使用类名(前5个): {", ".join(sample)}',
                'file': fpath,
                'line': 0,
                'fix': '删除未使用的样式类，减小包体积',
                'suggestion_code': (
                    '/* WXSS中定义但WXML未引用的类 → 删除 */\n\n'
                    '/* .old-layout { ... } */  /* 已废弃，删除 */\n'
                    '/* .legacy-card { ... } */  /* 不再使用，删除 */\n\n'
                    '/* 保留实际使用的类 */\n'
                    '.card { ... }  /* WXML中有 class="card" → 保留 */'
                ),
            })
    
    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'WXSS-001',
        'name': 'rpx/px混用',
        'level': 'problem',
        'category': 'style',
        'module_id': '12',
        'applicable_types': ['miniprogram', 'mixed'],
        'description': '同一WXSS文件中同时使用rpx和px单位，不同设备适配可能不一致',
        'check': check_wxss_001_rpx_px_mix,
    },
    {
        'id': 'WXSS-002',
        'name': '!important滥用',
        'level': 'problem',
        'category': 'code_smell',
        'module_id': '12',
        'applicable_types': ['miniprogram', 'mixed'],
        'description': '过多使用!important表明样式优先级混乱，影响可维护性',
        'check': check_wxss_002_important_abuse,
    },
    {
        'id': 'WXSS-003',
        'name': '选择器嵌套过深',
        'level': 'problem',
        'category': 'performance',
        'module_id': '12',
        'applicable_types': ['miniprogram', 'mixed'],
        'description': '超过3级嵌套的CSS选择器影响渲染性能',
        'check': check_wxss_003_deep_nesting,
    },
    {
        'id': 'WXSS-004',
        'name': '内联style硬编码',
        'level': 'problem',
        'category': 'code_smell',
        'module_id': '12',
        'applicable_types': ['miniprogram', 'mixed'],
        'description': 'WXML中style属性包含过多样式声明，应提取到WXSS类中',
        'check': check_wxss_004_inline_style,
    },
    {
        'id': 'WXSS-005',
        'name': '全局选择器污染',
        'level': 'problem',
        'category': 'code_smell',
        'module_id': '12',
        'applicable_types': ['miniprogram', 'mixed'],
        'description': 'app.wxss中对标签直接设置样式，会污染所有页面',
        'check': check_wxss_005_global_selector,
    },
    {
        'id': 'WXSS-006',
        'name': 'position:fixed滥用',
        'level': 'problem',
        'category': 'performance',
        'module_id': '12',
        'applicable_types': ['miniprogram', 'mixed'],
        'description': '过多position:fixed元素影响滚动性能和GPU合成',
        'check': check_wxss_006_fixed_abuse,
    },
    {
        'id': 'WXSS-007',
        'name': '未使用样式类',
        'level': 'suggestion',
        'category': 'code_smell',
        'module_id': '12',
        'applicable_types': ['miniprogram', 'mixed'],
        'description': 'WXSS中定义的样式类在WXML中未引用，可删除以减小包体积',
        'check': check_wxss_007_unused_class,
    },
]
