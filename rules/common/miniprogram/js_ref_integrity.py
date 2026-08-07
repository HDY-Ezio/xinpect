"""
小程序JS语法规则集 - 引用完整性检查 (v1.20.0)
JavaScript引用与方法完整性检查
包含: globalData属性引用检查、事件绑定函数存在性、重复方法定义检测
"""

"""
小程序JS语法规则集 (v1.20.0)
JavaScript语法与引用完整性检查
包含: JS语法校验、globalData属性引用、事件绑定函数存在性、重复方法定义等4项检查
"""

import re
import os
from typing import List, Dict, Any, Set, Optional, Tuple


def _is_vendored_js(norm_path: str, content: str) -> bool:
    """判断是否为第三方/压缩/vendored JS文件"""
    rel_lower = norm_path.lower().replace('\\', '/')
    basename = os.path.basename(norm_path).lower()
    vendored_dirs = {'node_modules', 'miniprogram_npm', 'vendor', 
                     'third_party', 'libs', 'lib', 'dist'}
    rel_parts = rel_lower.split('/')
    if any(d in rel_parts for d in vendored_dirs):
        return True
    vendored_name_markers = ['sdk', 'min.', 'vendor', 'ec-canvas', 'polyfill',
                              'weapp', 'wxapp', 'utils.min']
    if any(m in basename for m in vendored_name_markers):
        return True
    # 超长行压缩特征
    if content and len(content) > 5000 and content.count('\n') < len(content) / 200:
        return True
    return False


def check_20_2_globaldata_ref(context) -> List[Dict]:
    """20.2 globalData属性引用检查
    
    检测逻辑：
    1. 扫描app.js中globalData的定义，提取所有属性名
    2. 扫描所有JS文件中getApp().globalData.xxx的引用
    3. 对比：引用了但globalData中没定义的→warning
    """
    results = []
    
    if not context.project_path:
        return results
    
    # 1. 读取app.js中的globalData定义
    app_js_path = os.path.join(context.project_path, 'app.js')
    app_content = context.safe_read(app_js_path)
    if not app_content:
        return results
    
    defined_props = _extract_globaldata_props(app_content)
    if not defined_props:
        # globalData未定义或为空，跳过检查
        return results
    
    # 2. 扫描所有JS文件中的globalData引用
    js_files = context.find_files([".js"])
    undefined_refs = {}  # {prop_name: [(file, line), ...]}
    
    ref_pattern = re.compile(r'getApp\s*\(\s*\)\s*\.\s*globalData\s*\.\s*(\w+)')
    
    for fpath in js_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        lines = content.split('\n')
        for line_idx, line in enumerate(lines):
            for m in ref_pattern.finditer(line):
                prop_name = m.group(1)
                # 排除赋值（定义端）
                # 检查是否在globalData对象定义内部
                if fpath.replace(os.sep, '/').endswith('app.js'):
                    if _is_in_globaldata_definition(content, line_idx):
                        continue
                
                if prop_name not in defined_props:
                    if prop_name not in undefined_refs:
                        undefined_refs[prop_name] = []
                    undefined_refs[prop_name].append((fpath, line_idx + 1))
    
    if undefined_refs:
        detail_lines = []
        for prop_name, locations in sorted(undefined_refs.items()):
            for fpath, line in locations[:3]:
                rel_path = os.path.relpath(fpath, context.project_path) if context.project_path else fpath
                detail_lines.append(f"  globalData.{prop_name} → {rel_path}:{line}")
        
        results.append({
            'id': '20.2',
            'name': 'globalData属性引用检查',
            'level': 'warning',
            'message': f'发现{len(undefined_refs)}个globalData属性在app.js中未定义但被引用',
            'detail': '\n'.join(detail_lines[:15]),
            'file': app_js_path,
            'line': 0,
            'fix': '在app.js的globalData对象中添加缺失的属性定义，或检查引用拼写',
            'suggestion_code': f"// app.js\nApp({{\n  globalData: {{\n    // 已定义的属性: {', '.join(sorted(defined_props)[:10])}\n    // 需要添加: {', '.join(sorted(undefined_refs.keys())[:5])}\n  }}\n}})",
        })
    
    return results


def _extract_globaldata_props(content: str) -> Set[str]:
    """从app.js中提取globalData的属性名"""
    props = set()
    
    # 匹配 globalData: { ... } 块
    gd_pattern = re.compile(r'globalData\s*:\s*\{', re.MULTILINE)
    m = gd_pattern.search(content)
    if not m:
        return props
    
    # 提取globalData对象内容（括号匹配）
    start = m.end()
    brace_depth = 1
    idx = start
    while idx < len(content) and brace_depth > 0:
        if content[idx] == '{':
            brace_depth += 1
        elif content[idx] == '}':
            brace_depth -= 1
        idx += 1
    
    gd_body = content[start:idx - 1]
    
    # 提取属性名：key: value 或 key（shorthand）
    prop_pattern = re.compile(r'(?:^|[\s,])(\w+)\s*(?::|(?=,|\}|$))', re.MULTILINE)
    for pm in prop_pattern.finditer(gd_body):
        prop_name = pm.group(1)
        if prop_name not in ('globalData', 'getApp'):
            props.add(prop_name)
    
    return props


def _is_in_globaldata_definition(content: str, line_idx: int) -> bool:
    """判断指定行是否在globalData定义内部"""
    lines = content.split('\n')
    # 向上搜索globalData: {
    for i in range(line_idx, -1, -1):
        if 'globalData' in lines[i] and '{' in lines[i]:
            return True
    return False


# ===== 20.4 事件绑定函数存在性（按文件配对检查） =====
def check_20_4_event_binding_per_file(context) -> List[Dict]:
    """20.4 事件绑定函数存在性 - 按页面/组件文件配对检查
    
    与MP-001的全局检查不同，本规则检查每个WXML文件绑定的事件
    是否在其对应的JS文件中定义（同一目录下同名JS文件）。
    """
    results = []
    
    if not context.project_path:
        return results
    
    wxml_files = context.find_files([".wxml"])
    if not wxml_files:
        return results
    
    # 事件绑定属性模式
    event_pattern = re.compile(r'(?:bind|catch)(\w+)\s*=\s*["\'](\w+)["\']')
    
    # 生命周期方法白名单
    lifecycle_whitelist = {
        'onLoad', 'onShow', 'onReady', 'onHide', 'onUnload',
        'onPullDownRefresh', 'onReachBottom', 'onShareAppMessage',
        'onShareTimeline', 'onPageScroll', 'onResize', 'onTabItemTap',
        'onAddToFavorites', 'onChooseAvatar', 'onSaveExitState',
    }
    
    for fpath in wxml_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        # 找到对应的JS文件
        base_path = os.path.splitext(fpath)[0]
        js_path = base_path + '.js'
        
        if not os.path.isfile(js_path):
            continue
        
        js_content = context.safe_read(js_path)
        if not js_content:
            continue
        
        # 提取WXML中绑定的方法
        bound_methods = set()
        for m in event_pattern.finditer(content):
            method_name = m.group(2)
            if method_name and method_name not in lifecycle_whitelist:
                bound_methods.add(method_name)
        
        if not bound_methods:
            continue
        
        # 提取JS中定义的方法
        defined_methods = _extract_js_methods(js_content)
        
        # 找出缺失的
        missing = bound_methods - defined_methods
        
        if missing:
            rel_path = os.path.relpath(fpath, context.project_path) if context.project_path else fpath
            results.append({
                'id': '20.4',
                'name': '事件绑定函数存在性',
                'level': 'error',
                'message': f'{len(missing)}个事件绑定的函数在对应JS文件中未定义',
                'detail': f'文件: {rel_path}\n缺失: {", ".join(sorted(missing)[:10])}',
                'file': fpath,
                'line': 0,
                'fix': '在对应的JS文件中添加缺失的事件处理函数',
                'suggestion_code': '\n'.join([f'  {name}(e) {{\n    // TODO: 实现事件处理\n  }},' for name in sorted(missing)[:5]]),
            })
    
    return results


def _extract_js_methods(content: str) -> Set[str]:
    """从JS文件中提取所有定义的方法名"""
    methods = set()
    
    # 关键字和配置属性名
    keywords = {
        'if', 'for', 'while', 'switch', 'catch', 'with', 'return',
        'function', 'typeof', 'void', 'delete', 'new', 'do', 'else',
        'try', 'finally', 'class', 'super', 'yield', 'await', 'async',
        'data', 'properties', 'methods', 'lifetimes', 'pageLifetimes',
        'observers', 'options', 'behaviors', 'externalClasses',
        'relations', 'attached', 'detached', 'created', 'ready', 'moved',
        'import', 'export', 'default', 'const', 'let', 'var',
        'require', 'module', 'exports',
    }
    
    # ES6 shorthand: methodName(args) {
    # Traditional: methodName: function(args) {
    # Arrow: methodName: (args) => {
    method_pattern = re.compile(
        r'^[ \t]*(?:async\s+)?(\w+)\s*'
        r'(?:[:=]\s*(?:async\s+)?(?:function\s*)?)?'
        r'\([^)\n]*\)\s*'
        r'(?:=>\s*)?\{',
        re.MULTILINE
    )
    
    for m in method_pattern.finditer(content):
        method_name = m.group(1)
        if method_name not in keywords:
            methods.add(method_name)
    
    return methods


# ===== 20.6 重复方法定义检测 =====
def check_20_6_duplicate_methods(context) -> List[Dict]:
    """20.6 重复方法定义检测
    
    检测逻辑：扫描Page/Component对象中是否有同名方法定义。
    在JS对象中，重复的key后面的会覆盖前面的，导致前面的方法永远不会被调用。
    """
    results = []
    
    if not context.project_path:
        return results
    
    js_files = context.find_files([".js"])
    if not js_files:
        return results
    
    for fpath in js_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        norm_path = fpath.replace(os.sep, '/')
        if '/utils/' in norm_path or '/libs/' in norm_path or '/lib/' in norm_path:
            continue
        if _is_vendored_js(norm_path, content):
            continue
        
        # 检查是否有Page/Component定义
        if 'Page(' not in content and 'Component(' not in content:
            continue
        
        # 提取methods对象或Page对象中的所有方法名
        duplicates = _find_duplicate_methods(content)
        
        if duplicates:
            rel_path = os.path.relpath(fpath, context.project_path) if context.project_path else fpath
            dup_detail = '; '.join([f"'{name}'出现{count}次(行{lines})" for name, count, lines in duplicates])
            
            results.append({
                'id': '20.6',
                'name': '重复方法定义检测',
                'level': 'error',
                'message': f'发现{len(duplicates)}个重复方法定义（后者会覆盖前者）',
                'detail': dup_detail,
                'file': fpath,
                'line': 0,
                'fix': '删除重复的方法定义，保留正确的实现',
            })
    
    return results


def _find_duplicate_methods(content: str) -> List[Tuple[str, int, str]]:
    """查找JS对象中重复的方法名
    
    v1.20.1 修复：只提取Page({})/Component({})/App({})/Behavior({})的一级键作为方法定义。
    嵌套在wx.request({success:fn})、wx.uploadFile({fail:fn})等API回调参数对象中的
    success/fail/complete等key不被视为方法定义，避免误报重复方法。
    
    v1.23.0 修复(FP-01)：排除已知全局函数名白名单（setTimeout等），
    避免将函数调用误判为方法定义。同时收紧正则：方法定义必须有 `: function` / `: (` / `=>` 语法标记，
    纯函数调用 `name(args)` 不再被匹配。
    
    返回: [(method_name, count, lines_str), ...]
    """
    duplicates = []
    
    keywords = {
        'if', 'for', 'while', 'switch', 'catch', 'with', 'return',
        'function', 'typeof', 'void', 'delete', 'new', 'do', 'else',
        'try', 'finally', 'class', 'super', 'yield', 'await', 'async',
        'data', 'properties', 'methods', 'lifetimes', 'pageLifetimes',
        'observers', 'options', 'behaviors', 'externalClasses',
        'relations', 'import', 'export', 'default', 'const', 'let', 'var',
        'require', 'module', 'exports',
    }
    
    # v1.23.0: 全局函数名白名单（函数调用不应被视为方法定义）
    global_func_whitelist = {
        'setTimeout', 'setInterval', 'clearTimeout', 'clearInterval',
        'requestAnimationFrame', 'cancelAnimationFrame',
        'console', 'Promise', 'JSON', 'Object', 'Array', 'Math',
        'Date', 'String', 'Number', 'Boolean', 'RegExp', 'Error',
        'Map', 'Set', 'WeakMap', 'WeakSet', 'Symbol', 'Proxy',
        'parseInt', 'parseFloat', 'isNaN', 'isFinite',
        'encodeURIComponent', 'decodeURIComponent',
        'require', 'module', 'exports', '__dirname', '__filename',
        'wx', 'getApp', 'getCurrentPages', 'getCurrentInstance',
        'Reflect', 'globalThis', 'queueMicrotask', 'structuredClone',
    }
    
    # wx API 回调参数名（不应被视为方法定义）
    wx_callback_keys = {
        'success', 'fail', 'complete',
    }
    
    # wx API 调用模式 - 用于检测嵌套回调上下文
    wx_api_call_pattern = re.compile(
        r'(?:wx\.\w[\w.]*)\s*\(\s*\{',
    )
    
    # 方法定义模式
    method_pattern = re.compile(
        r'^[ \t]*(?:async\s+)?(\w+)\s*'
        r'(?:[:=]\s*(?:async\s+)?(?:function\s*)?)?'
        r'\([^)\n]*\)\s*'
        r'(?:=>\s*)?\{',
        re.MULTILINE
    )
    
    # 统计每个方法名的出现次数和行号
    method_locations = {}  # {name: [line_numbers]}
    
    # 第一步：找出所有 Page({})/Component({})/App({})/Behavior({}) 顶层对象的位置范围
    top_level_ranges = []
    for ctor in ['Page', 'Component', 'App', 'Behavior']:
        for m in re.finditer(r'\b' + ctor + r'\s*\(\s*\{', content):
            start = m.end() - 1  # 包含开始的 {
            brace_depth = 0
            idx = start
            while idx < len(content):
                if content[idx] == '{':
                    brace_depth += 1
                elif content[idx] == '}':
                    brace_depth -= 1
                    if brace_depth == 0:
                        break
                idx += 1
            top_level_ranges.append((start, idx + 1))
    
    # 如果没有找到任何顶层对象，用全文
    if not top_level_ranges:
        top_level_ranges = [(0, len(content))]
    
    for range_start, range_end in top_level_ranges:
        range_content = content[range_start:range_end]
        range_offset = range_start  # 字符偏移量
        
        # 对每个匹配，检查是否在 wx API 回调内部
        for m in method_pattern.finditer(range_content):
            name = m.group(1)
            if name in keywords:
                continue
            # v1.23.0 FP-01: 排除全局函数名白名单（setTimeout等函数调用）
            if name in global_func_whitelist:
                continue
            
            abs_pos = range_offset + m.start()
            line_num = content[:abs_pos].count('\n') + 1
            
            # 检查该位置是否在 wx API 回调内部
            # 方法：向上检查是否有未闭合的 wx.xxx({
            if name in wx_callback_keys:
                # 向上查找最近20行，看是否有 wx.xxx({ 的未闭合调用
                context_start = max(0, abs_pos - 1500)
                context_before = content[context_start:abs_pos]
                
                is_wx_callback = False
                for wx_m in wx_api_call_pattern.finditer(context_before):
                    # 检查从 wx.xxx({ 开始到当前位置，花括号是否未闭合
                    wx_obj_start = wx_m.end() - 1  # { 的位置
                    sub = context_before[wx_obj_start:]
                    depth = 0
                    for ch in sub:
                        if ch == '{':
                            depth += 1
                        elif ch == '}':
                            depth -= 1
                    if depth > 0:
                        # 有未闭合的 wx API 对象，说明当前在回调内部
                        is_wx_callback = True
                        break
                
                if is_wx_callback:
                    continue
            
            if name not in method_locations:
                method_locations[name] = []
            method_locations[name].append(line_num)
    
    # 找出重复的
    for name, lines in method_locations.items():
        if len(lines) > 1:
            duplicates.append((name, len(lines), ','.join(str(l) for l in lines)))
    
    return duplicates


# ===== 20.9 空catch块检测（Promise链） =====


# ===== 规则定义列表 =====
RULES = [
        {
            'id': '20.2',
            'name': 'globalData属性引用检查',
            'level': 'warning',
            'category': 'miniprogram_js',
            'module_id': '20',
            'applicable_types': ['miniprogram', 'mixed'],
            'description': '检查getApp().globalData.xxx引用的属性是否在app.js中定义',
            'check': check_20_2_globaldata_ref,
        },
        {
            'id': '20.4',
            'name': '事件绑定函数存在性',
            'level': 'error',
            'category': 'miniprogram_js',
            'module_id': '20',
            'applicable_types': ['miniprogram', 'mixed'],
            'description': '按页面/组件文件配对检查WXML事件绑定的函数是否在对应JS中定义',
            'check': check_20_4_event_binding_per_file,
        },
        {
            'id': '20.6',
            'name': '重复方法定义检测',
            'level': 'error',
            'category': 'miniprogram_js',
            'module_id': '20',
            'applicable_types': ['miniprogram', 'mixed'],
            'description': '检测Page/Component对象中是否有同名方法定义（后者会覆盖前者）',
            'check': check_20_6_duplicate_methods,
        },
]
