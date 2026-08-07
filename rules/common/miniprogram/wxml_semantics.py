"""
小程序WXML规则集 - 语义与语法检查 (v3.4 AST增强版)
微信小程序WXML模板检查 - 语义/语法类
包含: 方法绑定存在性、标签规范性、列表渲染key、数据绑定语法

v3.4 改进: 优先使用AST解析(JS用@babel/parser, WXML用htmlparser2)，
           AST不可用时自动降级到原有正则匹配。
           AST优势: 精准识别ES6 shorthand/async/箭头函数/类方法，
           精准解析WXML多行标签和属性值，消除正则误报。
"""

"""
小程序WXML规则集 (v3.4 AST增强版)
微信小程序WXML模板检查
包含: 方法绑定存在性、标签合法性、数据绑定、列表渲染等检查

v3.4 改进: 优先使用AST解析(JS用@babel/parser, WXML用htmlparser2)，
           AST不可用时自动降级到原有正则匹配。
           AST优势: 精准识别ES6 shorthand/async/箭头函数/类方法，
           精准解析WXML多行标签和属性值，消除正则误报。
"""

import re
import os
import json
from typing import List, Dict, Any, Set, Optional

# v4.6.1 性能优化：AST分析器懒加载，避免import时启动Node.js子进程
_ast_analyzer = None
_ast_available = None  # None=未检查, True/False=结果


def _get_ast_analyzer():
    """懒加载AST分析器：首次真正使用时才导入并启动Node.js子进程"""
    global _ast_analyzer, _ast_available
    if _ast_available is not None:
        return _ast_analyzer if _ast_available else None
    try:
        from core.js_ast_analyzer import get_js_ast_analyzer
        _ast_analyzer = get_js_ast_analyzer()
        _ast_available = _ast_analyzer.is_available
    except Exception as e:  # noqa: broad exception handling
        _ast_analyzer = None
        _ast_available = False
    return _ast_analyzer if _ast_available else None


# ===== JS关键字和Page/Component配置属性名（不是方法）=====
_JS_KEYWORDS_AND_CONFIG_KEYS = {
    # JS关键字
    'if', 'for', 'while', 'switch', 'catch', 'with', 'return',
    'function', 'typeof', 'void', 'delete', 'new', 'do', 'else',
    'try', 'finally', 'class', 'super', 'yield', 'await', 'async',
    # Page/Component配置属性名
    'data', 'properties', 'methods', 'lifetimes',
    'pageLifetimes', 'observers', 'options', 'behaviors',
    'externalClasses', 'relations', 'attached', 'detached',
    'created', 'ready', 'moved',
    # ES modules
    'import', 'export', 'default', 'const', 'let', 'var',
    'require', 'module', 'exports',
}


def _get_page_js_methods(context) -> Set[str]:
    """获取所有页面JS中定义的方法名
    
    v3.4: 优先使用AST解析，不可用时降级到正则。
    AST优势: 精准识别ES6 shorthand/async/箭头函数/类方法/嵌套函数，
             不会误匹配字符串中的函数调用语法。
    
    v1.20.1 修复：额外从Component({methods:{}})的methods对象中提取方法名，
    确保组件methods中定义的事件处理函数不被误报为未定义。
    """
    methods = set()
    
    js_files = context.find_files([".js"])
    
    ast = _get_ast_analyzer()
    if ast:
        # ===== AST模式 =====
        for fpath in js_files:
            ast_methods = ast.get_js_method_names(fpath)
            if ast_methods is not None:
                methods.update(ast_methods)
            else:
                # AST不可用对该文件（解析失败），降级到正则
                methods.update(_get_page_js_methods_regex(context, fpath))
            # v1.20.1: 始终补充提取Component({methods:{}})中的方法
            methods.update(_extract_component_methods_regex(fpath, context))
        return methods
    else:
        # ===== 正则降级模式 =====
        for fpath in js_files:
            methods.update(_get_page_js_methods_regex(context, fpath))
            # v1.20.1: 始终补充提取Component({methods:{}})中的方法
            methods.update(_extract_component_methods_regex(fpath, context))
        return methods


def _extract_component_methods_regex(fpath: str, context) -> Set[str]:
    """从Component({methods:{...}})中提取方法名
    
    v1.20.1 新增：专门处理微信小程序Component构造器中methods对象内的方法定义。
    这些方法在WXML事件绑定中经常使用，需要被识别。
    """
    methods = set()
    content = context.safe_read(fpath)
    if not content or 'Component(' not in content:
        return methods
    
    # 查找 methods: { ... } 块
    methods_pattern = re.compile(r'\bmethods\s*:\s*\{', re.MULTILINE)
    for m in methods_pattern.finditer(content):
        start = m.end()
        brace_depth = 1
        idx = start
        while idx < len(content) and brace_depth > 0:
            if content[idx] == '{':
                brace_depth += 1
            elif content[idx] == '}':
                brace_depth -= 1
            elif content[idx] in ('"', "'", '`'):
                # 跳过字符串
                quote = content[idx]
                idx += 1
                while idx < len(content):
                    if content[idx] == '\\':
                        idx += 2
                        continue
                    if content[idx] == quote:
                        break
                    idx += 1
            idx += 1
        
        methods_body = content[start:idx - 1]
        
        # 从methods体内提取方法名
        method_pattern = re.compile(
            r'(?:^|[\s,])(?:async\s+)?(\w+)\s*'
            r'(?:[:=]\s*(?:async\s+)?(?:function\s*)?)?'
            r'\([^)\n]*\)\s*'
            r'(?:=>\s*)?\{',
            re.MULTILINE
        )
        for pm in method_pattern.finditer(methods_body):
            name = pm.group(1)
            if name not in _JS_KEYWORDS_AND_CONFIG_KEYS:
                methods.add(name)
    
    return methods


def _get_page_js_methods_regex(context, fpath: str) -> Set[str]:
    """正则方式提取JS方法名（降级用）
    
    支持三种语法 + async 前缀：
      1. ES6 shorthand:  onTap(e) { / async onTap(e) {
      2. 传统函数:        onTap: function(e) { / onTap: async function(e) {
      3. 箭头函数:        onTap: (e) => { / onTap: async (e) => {
    """
    methods = set()
    content = context.safe_read(fpath)
    if not content:
        return methods
    
    method_pattern = re.compile(
        r'^[ \t]*(?:async\s+)?(\w+)\s*'         # 行首，可选async前缀，方法名
        r'(?:[:=]\s*(?:async\s+)?(?:function\s*)?)?'  # 可选的 :/= function/async
        r'\([^)\n]*\)\s*'                          # 参数列表（不跨行）
        r'(?:=>\s*)?\{',                            # 可选的 => 然后 {
        re.MULTILINE
    )
    for m in method_pattern.finditer(content):
        method_name = m.group(1)
        if method_name in _JS_KEYWORDS_AND_CONFIG_KEYS:
            continue
        methods.add(method_name)
    
    return methods


# ===== MP-001 WXML方法绑定存在性 =====
def check_mp_001_method_binding(context) -> List[Dict]:
    """MP-001 WXML方法绑定存在性 - WXML中bind事件绑定的方法必须在JS中存在定义
    
    v3.4: 使用AST精确解析WXML标签和属性，准确识别bind/catch事件绑定。
          AST能正确处理多行标签、属性值中的特殊字符等正则难以处理的场景。
    """
    results = []
    
    wxml_files = context.find_files([".wxml"])
    if not wxml_files:
        return results
    
    js_methods = _get_page_js_methods(context)
    
    # Page/Component生命周期方法白名单
    lifecycle_whitelist = {
        'onLoad', 'onShow', 'onReady', 'onHide', 'onUnload',
        'onPullDownRefresh', 'onReachBottom', 'onShareAppMessage',
        'onShareTimeline', 'onPageScroll', 'onResize', 'onTabItemTap',
        'onAddToFavorites', 'onChooseAvatar', 'onSaveExitState',
    }
    
    for fpath in wxml_files:
        missing_methods = set()
        
        ast = _get_ast_analyzer()
        if ast:
            # ===== AST模式 =====
            bindings = ast.get_wxml_bindings(fpath)
            if bindings is not None:
                for b in bindings:
                    method_name = b.get("method", "")
                    event_type = b.get("event", "")
                    
                    if not method_name:
                        continue
                    if method_name in lifecycle_whitelist:
                        continue
                    if method_name not in js_methods:
                        missing_methods.add(f'{method_name}(bind{event_type})')
                _process_mp_001_results(results, fpath, missing_methods)
                continue
            # AST对该文件不可用，降级
            _check_mp_001_regex(context, fpath, js_methods, lifecycle_whitelist, missing_methods, results)
        else:
            # ===== 正则降级模式 =====
            _check_mp_001_regex(context, fpath, js_methods, lifecycle_whitelist, missing_methods, results)
    
    return results


def _check_mp_001_regex(context, fpath, js_methods, lifecycle_whitelist, missing_methods, results):
    """正则方式检查MP-001（降级用）"""
    content = context.safe_read(fpath)
    if not content:
        return
    
    binding_pattern = re.compile(r'(?:bind|catch)(\w+)\s*=\s*["\'](\w+)["\']')
    
    for m in binding_pattern.finditer(content):
        event_type = m.group(1)
        method_name = m.group(2)
        
        if not method_name:
            continue
        if method_name in lifecycle_whitelist:
            continue
        if method_name not in js_methods:
            missing_methods.add(f'{method_name}(bind{event_type})')
    
    _process_mp_001_results(results, fpath, missing_methods)


def _process_mp_001_results(results, fpath, missing_methods):
    """处理MP-001结果"""
    if missing_methods:
        results.append({
            'id': 'MP-001',
            'name': 'WXML方法绑定存在性',
            'level': 'error',
            'message': f'{len(missing_methods)}个绑定的方法在JS中未找到定义',
            'detail': '缺失方法: ' + ', '.join(sorted(missing_methods)[:10]),
            'file': fpath,
            'line': 0,
            'fix': '在对应的JS文件中定义这些方法，或修正WXML中的绑定名',
            'suggestion_code': _generate_mp_001_fix(missing_methods),
        })


def _generate_mp_001_fix(missing_methods: set) -> str:
    """为MP-001生成修复建议代码"""
    lines = []
    for method_str in sorted(missing_methods)[:5]:
        # 提取方法名: "onViewDetail(bindtap)" -> "onViewDetail"
        name = method_str.split('(')[0]
        lines.append(f'  {name}(e) {{\n    // TODO: 实现事件处理逻辑\n  }},')
    if lines:
        return '// 在Page/Component中添加缺失的方法:\n' + '\n'.join(lines)
    return ''


# ===== MP-002 标签使用规范性 =====
def check_mp_002_tag_usage(context) -> List[Dict]:
    """MP-002 标签使用规范性 - 检查是否使用了不推荐或废弃的标签"""
    results = []
    
    wxml_files = context.find_files([".wxml"])
    if not wxml_files:
        return results
    
    deprecated_patterns = [
        (r'<audio\s', 'audio组件已废弃，推荐使用InnerAudioContext API'),
    ]
    
    for fpath in wxml_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        issues = []
        for pattern, desc in deprecated_patterns:
            if re.search(pattern, content):
                issues.append(desc)
        
        if issues:
            results.append({
                'id': 'MP-002',
                'name': '标签使用规范性',
                'level': 'warning',
                'message': f'使用了不推荐的标签/属性: {len(issues)}项',
                'detail': '问题: ' + '; '.join(issues),
                'file': fpath,
                'line': 0,
                'fix': '替换为推荐的实现方式',
                'suggestion_code': '<!-- 废弃的audio组件 -->\n<!-- <audio src="{{url}}" /> -->\n\n<!-- 推荐使用InnerAudioContext API -->\nconst innerAudio = wx.createInnerAudioContext();\ninnerAudio.src = url;\ninnerAudio.play();',
            })
    
    return results


# ===== MP-003 列表渲染key检查 =====
def check_mp_003_list_rendering_key(context) -> List[Dict]:
    """MP-003 列表渲染key检查 - wx:for必须指定wx:key
    
    v3.4: 使用AST精确解析WXML标签，准确识别wx:for和wx:key属性。
          AST能正确处理跨多行的标签和属性值。
    """
    results = []
    
    wxml_files = context.find_files([".wxml"])
    if not wxml_files:
        return results
    
    for fpath in wxml_files:
        ast = _get_ast_analyzer()
        if ast:
            # ===== AST模式 =====
            for_tags = ast.get_wxml_for_tags(fpath)
            if for_tags is not None:
                missing_key_count = 0
                samples = []
                
                for ft in for_tags:
                    if not ft.get("hasKey"):
                        missing_key_count += 1
                        if len(samples) < 3:
                            samples.append(f'第{ft["line"]}行')
                
                if missing_key_count > 0:
                    results.append({
                        'id': 'MP-003',
                        'name': '列表渲染key检查',
                        'level': 'warning',
                        'message': f'{missing_key_count}处wx:for缺少wx:key',
                        'detail': '位置: ' + ', '.join(samples),
                        'file': fpath,
                        'line': 0,
                        'fix': '为wx:for添加wx:key属性，提高列表渲染性能',
                        'suggestion_code': '<view wx:for="{{list}}" wx:key="id">\n  <!-- 添加wx:key属性 -->\n</view>',
                    })
                continue
            # AST对该文件不可用，降级
        
        # ===== 正则降级模式 =====
        _check_mp_003_regex(context, fpath, results)
    
    return results


def _check_mp_003_regex(context, fpath, results):
    """正则方式检查MP-003（降级用）"""
    content = context.safe_read(fpath)
    if not content:
        return
    
    missing_key_count = 0
    samples = []
    
    tag_pattern = re.compile(r'<[\w-]+[^>]*>', re.DOTALL)
    
    for m in tag_pattern.finditer(content):
        tag_content = m.group(0)
        
        if 'wx:for' not in tag_content:
            continue
        if 'wx:key' in tag_content:
            continue
        
        missing_key_count += 1
        if len(samples) < 3:
            line_num = content[:m.start()].count('\n') + 1
            samples.append(f'第{line_num}行')
    
    if missing_key_count > 0:
        results.append({
            'id': 'MP-003',
            'name': '列表渲染key检查',
            'level': 'warning',
            'message': f'{missing_key_count}处wx:for缺少wx:key',
            'detail': '位置: ' + ', '.join(samples),
            'file': fpath,
            'line': 0,
            'fix': '为wx:for添加wx:key属性，提高列表渲染性能',
        })


# ===== MP-004 数据绑定语法检查 =====
def check_mp_004_data_binding(context) -> List[Dict]:
    """MP-004 数据绑定语法检查 - 检查{{}}语法是否正确
    
    v3.4: 使用AST统计mustache数量（与正则计数一致，但保持接口统一）。
    """
    results = []
    
    wxml_files = context.find_files([".wxml"])
    if not wxml_files:
        return results
    
    for fpath in wxml_files:
        ast = _get_ast_analyzer()
        if ast:
            # ===== AST模式 =====
            mustache = ast.get_wxml_mustache_count(fpath)
            if mustache is not None:
                open_count = mustache.get("open", 0)
                close_count = mustache.get("close", 0)
                
                if open_count != close_count:
                    results.append({
                        'id': 'MP-004',
                        'name': '数据绑定语法检查',
                        'level': 'error',
                        'message': f'数据绑定语法不匹配: {{{{ {open_count}个, }}}} {close_count}个',
                        'file': fpath,
                        'line': 0,
                        'fix': '检查并修复不匹配的{{}}数据绑定语法',
                        'suggestion_code': '<!-- 检查每个{{ }}是否有对应的 }} -->\n<!-- 正确 -->\n<view>{{ text }}</view>\n\n<!-- 错误：缺少闭合 -->\n<!-- <view>{{ text }} -->\n\n<!-- 错误：多余闭合 -->\n<!-- <view>text }}</view> -->',
                    })
                continue
            # AST对该文件不可用，降级
        
        # ===== 正则降级模式 =====
        content = context.safe_read(fpath)
        if not content:
            continue
        
        open_count = content.count('{{')
        close_count = content.count('}}')
        
        if open_count != close_count:
            results.append({
                'id': 'MP-004',
                'name': '数据绑定语法检查',
                'level': 'error',
                'message': f'数据绑定语法不匹配: {{{{ {open_count}个, }}}} {close_count}个',
                'file': fpath,
                'line': 0,
                'fix': '检查并修复不匹配的{{}}数据绑定语法',
                'suggestion_code': '<!-- 检查每个{{ }}是否有对应的 }} -->\n<!-- 正确 -->\n<view>{{ text }}</view>\n\n<!-- 错误：缺少闭合 -->\n<!-- <view>{{ text }} -->\n\n<!-- 错误：多余闭合 -->\n<!-- <view>text }}</view> -->',
            })
    
    return results


# ===== MP-005 图片懒加载 =====


# ===== 规则定义列表 =====
RULES = [
        {
            'id': 'MP-001',
            'name': 'WXML方法绑定存在性',
            'level': 'blocking',
            'category': 'wxml',
            'module_id': '2',
            'applicable_types': ['miniprogram', 'mixed'],
            'description': 'WXML中bind事件绑定的方法必须在JS中存在定义（AST增强：精准识别ES6/async/箭头函数）',
            'check': check_mp_001_method_binding,
        },
        {
            'id': 'MP-002',
            'name': '标签使用规范性',
            'level': 'problem',
            'category': 'wxml',
            'module_id': '2',
            'applicable_types': ['miniprogram', 'mixed'],
            'description': '检查是否使用了不推荐或废弃的标签/属性',
            'check': check_mp_002_tag_usage,
        },
        {
            'id': 'MP-003',
            'name': '列表渲染key检查',
            'level': 'problem',
            'category': 'wxml',
            'module_id': '5',
            'applicable_types': ['miniprogram', 'mixed'],
            'description': 'wx:for必须指定wx:key以提高渲染性能（AST增强：精准解析多行标签）',
            'check': check_mp_003_list_rendering_key,
        },
        {
            'id': 'MP-004',
            'name': '数据绑定语法检查',
            'level': 'blocking',
            'category': 'wxml',
            'module_id': '2',
            'applicable_types': ['miniprogram', 'mixed'],
            'description': '检查{{}}数据绑定语法是否正确匹配',
            'check': check_mp_004_data_binding,
        },
]
