# -*- coding: utf-8 -*-
"""
内存泄漏AST深度分析规则集
检测大对象缓存无上限、闭包引用大对象、循环引用、全局变量累积等
规则ID: PYAST025 - PYAST032
"""

import ast
import re
import os
from typing import List, Dict, Any, Optional, Set, Tuple


def _parse_ast_safe(filepath: str, content: str) -> Optional[ast.Module]:
    """安全解析AST"""
    try:
        return ast.parse(content, filename=filepath)
    except SyntaxError:
        return None


def _is_cache_or_store_name(name: str) -> bool:
    """检查变量名是否是缓存/存储类名称"""
    cache_names = [
        'cache', '_cache', 'store', '_store', 'buffer', '_buffer',
        'history', '_history', 'log', '_log', 'registry', '_registry',
        'pool', '_pool', 'queue', '_queue', 'stack', '_stack',
        'data', '_data', 'results', '_results', 'items', '_items',
        'entries', '_entries', 'records', '_records',
    ]
    name_lower = name.lower()
    return any(cn in name_lower for cn in cache_names)


def check_unbounded_cache(context) -> List[Dict]:
    """PYAST025 - 检测大对象缓存无上限（dict/list持续增长无清理机制）"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        lines = content.split('\n')
        
        # 查找模块级或类级 dict/list 定义
        module_dicts = []
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        if isinstance(node.value, (ast.Dict, ast.List, ast.Set)):
                            if _is_cache_or_store_name(target.id):
                                module_dicts.append(target.id)
                        elif isinstance(node.value, ast.Call):
                            if isinstance(node.value.func, ast.Name):
                                if node.value.func.id in ('dict', 'list', 'set', 'defaultdict', 'deque', 'OrderedDict'):
                                    if _is_cache_or_store_name(target.id):
                                        module_dicts.append(target.id)
        
        if not module_dicts:
            continue
        
        # 检查是否有清理机制
        has_cleanup = bool(re.search(
            r'(clear\s*\(\)|pop\s*\(|del\s|\.popitem|maxsize|max_size|max_len|evict|expire|ttl|lru_cache|cache_size|cleanup|clean_up|gc\.collect)',
            content, re.IGNORECASE
        ))
        
        if not has_cleanup:
            # 检查是否有 append/update/setitem 等增长操作
            growth_ops = []
            for var_name in module_dicts:
                if re.search(rf'\b{re.escape(var_name)}\s*(?:\.append|\.update|\.add|\.extend|\[)', content):
                    growth_ops.append(var_name)
            
            if growth_ops:
                results.append({
                    'id': 'PYAST025',
                    'name': '内存泄漏-缓存无上限',
                    'level': 'warning',
                    'message': f'模块级变量{", ".join(growth_ops[:3])}持续增长但无清理机制',
                    'file': fpath,
                    'line': 1,
                    'snippet': f'变量: {", ".join(growth_ops[:3])}',
                    'fix': '添加缓存大小限制(collections.deque(maxlen=N))、定期清理或LRU淘汰策略',
                })
    
    return results


def check_closure_large_reference(context) -> List[Dict]:
    """PYAST026 - 检测闭包引用大对象"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        lines = content.split('\n')
        issues = []
        
        # 查找嵌套函数（闭包）
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            
            # 查找内部定义的函数/lambda
            for inner in ast.walk(node):
                if inner is node:
                    continue
                if not isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                    continue
                
                # 检查内部函数是否引用了外部函数的局部变量
                outer_locals = set()
                for arg in node.args.args:
                    outer_locals.add(arg.arg)
                for stmt in node.body:
                    for sub in ast.walk(stmt):
                        if isinstance(sub, ast.Assign):
                            for t in sub.targets:
                                if isinstance(t, ast.Name):
                                    outer_locals.add(t.id)
                
                inner_refs = set()
                for sub in ast.walk(inner):
                    if isinstance(sub, ast.Name) and sub.id in outer_locals:
                        inner_refs.add(sub.id)
                
                if inner_refs:
                    # 检查引用的变量是否可能是大对象（通过命名推断）
                    large_hints = {'data', 'result', 'response', 'content', 'body', 'payload', 
                                   'records', 'rows', 'items', 'buffer', 'html', 'text', 'json_data'}
                    large_refs = inner_refs & large_hints
                    if large_refs:
                        func_name = inner.name if hasattr(inner, 'name') else '<lambda>'
                        issues.append((
                            inner.lineno,
                            func_name,
                            ', '.join(large_refs),
                        ))
        
        if issues:
            results.append({
                'id': 'PYAST026',
                'name': '内存泄漏-闭包引用大对象',
                'level': 'info',
                'message': f'检测到{len(issues)}处闭包引用可能的大对象',
                'file': fpath,
                'line': issues[0][0],
                'snippet': f'函数{issues[0][1]}引用: {issues[0][2]}',
                'fix': '闭包中只引用需要的数据切片，避免引用整个大对象',
            })
    
    return results


def check_circular_reference(context) -> List[Dict]:
    """PYAST027 - 检测潜在的循环引用（对象互相引用无__del__或weakref）"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        lines = content.split('\n')
        
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            
            # 检查类是否有 __del__ 或使用 weakref
            has_del = False
            has_weakref = False
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == '__del__':
                    has_del = True
                if isinstance(item, ast.FunctionDef) and item.name == '__init__':
                    # 检查是否使用了weakref
                    for sub in ast.walk(item):
                        if isinstance(sub, ast.Name) and sub.id == 'weakref':
                            has_weakref = True
                        if isinstance(sub, ast.Attribute) and sub.attr == 'ref':
                            has_weakref = True
            
            # 检查是否有self.xxx = other_obj的相互引用模式
            self_refs = set()
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    for sub in ast.walk(item):
                        # self.xxx = yyy.zzz 模式
                        if isinstance(sub, ast.Assign):
                            for target in sub.targets:
                                if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                                    if target.value.id == 'self':
                                        self_refs.add(target.attr)
            
            # 如果类有多个属性且没有weakref/del，可能有循环引用风险
            if len(self_refs) >= 3 and not has_del and not has_weakref:
                # 检查是否引用了同类型或其他类的实例
                has_mutual_ref = False
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == '__init__':
                        for sub in ast.walk(item):
                            if isinstance(sub, ast.Call):
                                if isinstance(sub.func, ast.Name) and sub.func.id == node.name:
                                    has_mutual_ref = True
                                    break
                
                if has_mutual_ref:
                    results.append({
                        'id': 'PYAST027',
                        'name': '内存泄漏-循环引用',
                        'level': 'info',
                        'message': f'类{node.name}可能存在循环引用（有{len(self_refs)}个属性且创建同类实例）',
                        'file': fpath,
                        'line': node.lineno,
                        'snippet': lines[node.lineno-1].strip()[:120] if node.lineno-1 < len(lines) else '',
                        'fix': '使用weakref.ref()存储弱引用，或实现__del__打破循环引用',
                    })
    
    return results


def check_global_accumulation(context) -> List[Dict]:
    """PYAST028 - 检测全局变量持续累积（模块级list/dict不断append）"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        lines = content.split('\n')
        
        # 查找模块级可变变量
        module_mutables = []
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        if isinstance(node.value, (ast.List, ast.Dict)):
                            module_mutables.append((target.id, node.lineno))
                        elif isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
                            if node.value.func.id in ('list', 'dict', 'set', 'defaultdict', 'deque', 'OrderedDict'):
                                module_mutables.append((target.id, node.lineno))
        
        if not module_mutables:
            continue
        
        # 检查函数内是否有增长操作且无对应的清理
        growth_vars = []
        for var_name, def_line in module_mutables:
            # 统计增长操作次数
            append_count = len(re.findall(
                rf'\b{re.escape(var_name)}\s*(?:\.append|\.extend|\.update|\.add|\.insert)',
                content
            ))
            # 统计清理操作
            clear_count = len(re.findall(
                rf'\b{re.escape(var_name)}\s*(?:\.clear|\.pop|\.popitem|\.remove)',
                content
            ))
            
            if append_count > 3 and clear_count == 0:
                growth_vars.append((var_name, def_line, append_count))
        
        if growth_vars:
            results.append({
                'id': 'PYAST028',
                'name': '内存泄漏-全局累积',
                'level': 'warning',
                'message': f'检测到{len(growth_vars)}个模块级变量持续累积无清理',
                'file': fpath,
                'line': growth_vars[0][1],
                'snippet': f'{growth_vars[0][0]}: {growth_vars[0][2]}次增长操作',
                'fix': '定期清理或使用有界容器(deque(maxlen=N))，避免模块级变量无限增长',
            })
    
    return results


def check_unclosed_resources(context) -> List[Dict]:
    """PYAST029 - 检测未关闭的文件/网络连接"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        lines = content.split('\n')
        issues = []
        
        for node in ast.walk(tree):
            # open() 不在 with 中且没有 close()
            if isinstance(node, ast.Call):
                func_name = ''
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                
                if func_name != 'open':
                    continue
                
                # 检查是否在with语句中
                in_with = False
                for parent in ast.walk(tree):
                    if isinstance(parent, ast.With):
                        for item in parent.items:
                            if isinstance(item.context_expr, ast.Call):
                                if item.context_expr.lineno == node.lineno and isinstance(item.context_expr.func, ast.Name):
                                    if item.context_expr.func.id == 'open':
                                        in_with = True
                
                if in_with:
                    continue
                
                # 检查是否赋值给变量，该变量后续有close
                assigned_var = None
                for parent in ast.walk(tree):
                    if isinstance(parent, ast.Assign):
                        if isinstance(parent.value, ast.Call) and parent.value.lineno == node.lineno:
                            if isinstance(parent.targets[0], ast.Name):
                                assigned_var = parent.targets[0].id
                
                if assigned_var:
                    # 检查是否有 close
                    has_close = bool(re.search(
                        rf'\b{re.escape(assigned_var)}\s*\.\s*close\s*\(',
                        content
                    ))
                    if not has_close:
                        issues.append(node.lineno)
                else:
                    # 直接 open() 无赋值，未关闭
                    issues.append(node.lineno)
        
        if issues:
            results.append({
                'id': 'PYAST029',
                'name': '内存泄漏-未关闭资源',
                'level': 'warning',
                'message': f'检测到{len(issues)}处open()调用未使用with语句或未close()',
                'file': fpath,
                'line': issues[0],
                'snippet': lines[issues[0]-1].strip()[:120] if issues[0]-1 < len(lines) else '',
                'fix': '使用with open() as f:自动管理文件关闭，或在finally中调用close()',
            })
    
    return results


def check_large_literal_in_function(context) -> List[Dict]:
    """PYAST030 - 检测函数内定义大列表/大字典常量"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        lines = content.split('\n')
        issues = []
        
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            
            # 检查函数体内的字面量大小
            for child in ast.walk(node):
                if isinstance(child, (ast.List, ast.Tuple, ast.Set)):
                    if len(child.elts) > 100:
                        issues.append((child.lineno, f'大列表({len(child.elts)}项)', len(child.elts)))
                elif isinstance(child, ast.Dict):
                    if len(child.keys) > 50:
                        issues.append((child.lineno, f'大字典({len(child.keys)}项)', len(child.keys)))
        
        if issues:
            worst = max(issues, key=lambda x: x[2])
            results.append({
                'id': 'PYAST030',
                'name': '内存泄漏-大常量',
                'level': 'info',
                'message': f'函数内定义{worst[1]}，每次调用都重新创建，建议提取为模块级常量',
                'file': fpath,
                'line': worst[0],
                'snippet': lines[worst[0]-1].strip()[:120] if worst[0]-1 < len(lines) else '',
                'fix': '将大列表/字典提取为模块级常量，避免每次函数调用重复创建',
            })
    
    return results


def check_gc_disabled(context) -> List[Dict]:
    """PYAST031 - 检测gc.disable()调用"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        lines = content.split('\n')
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            if re.search(r'gc\.disable\s*\(', stripped):
                # 检查是否有对应的gc.enable()
                has_enable = bool(re.search(r'gc\.enable\s*\(', content))
                if not has_enable:
                    results.append({
                        'id': 'PYAST031',
                        'name': '内存泄漏-GC关闭',
                        'level': 'warning',
                        'message': 'gc.disable()被调用但未找到gc.enable()，可能导致内存泄漏',
                        'file': fpath,
                        'line': i + 1,
                        'snippet': stripped[:120],
                        'fix': '使用gc.disable()后必须确保gc.enable()被调用，或定期调用gc.collect()',
                    })
    
    return results


def check_signal_handler_leak(context) -> List[Dict]:
    """PYAST032 - 检测signal handler中的内存泄漏风险"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        if 'signal.signal' not in content and 'signal.setitimer' not in content:
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        lines = content.split('\n')
        issues = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr == 'signal' and isinstance(node.func.value, ast.Name):
                        if node.func.value.id == 'signal' and len(node.args) >= 2:
                            # 检查handler是否是lambda或闭包
                            handler = node.args[1]
                            if isinstance(handler, ast.Lambda):
                                issues.append((handler.lineno, 'signal handler使用lambda，可能持有外部引用'))
                            elif isinstance(handler, ast.Name):
                                # 查找handler函数定义
                                for fn in tree.body:
                                    if isinstance(fn, ast.FunctionDef) and fn.name == handler.id:
                                        # 检查handler是否操作了全局可变变量
                                        for sub in ast.walk(fn):
                                            if isinstance(sub, ast.Global):
                                                issues.append((fn.lineno, f'signal handler {handler.id}修改全局变量'))
                                                break
        
        if issues:
            results.append({
                'id': 'PYAST032',
                'name': '内存泄漏-signal handler',
                'level': 'info',
                'message': f'检测到{len(issues)}处signal handler可能存在内存泄漏风险',
                'file': fpath,
                'line': issues[0][0],
                'snippet': issues[0][1],
                'fix': 'signal handler应保持轻量，避免持有大对象引用或修改全局状态',
            })
    
    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'PYAST025',
        'name': '内存泄漏-缓存无上限',
        'level': 'warning',
        'category': 'memory',
        'module_id': '4',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测模块级dict/list持续增长但无清理机制',
        'check': check_unbounded_cache,
    },
    {
        'id': 'PYAST026',
        'name': '内存泄漏-闭包引用大对象',
        'level': 'info',
        'category': 'memory',
        'module_id': '4',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测闭包中引用外部大变量导致对象无法回收',
        'check': check_closure_large_reference,
    },
    {
        'id': 'PYAST027',
        'name': '内存泄漏-循环引用',
        'level': 'info',
        'category': 'memory',
        'module_id': '4',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测对象互相引用形成循环且无weakref/__del__',
        'check': check_circular_reference,
    },
    {
        'id': 'PYAST028',
        'name': '内存泄漏-全局累积',
        'level': 'warning',
        'category': 'memory',
        'module_id': '4',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测模块级list/dict不断append/update无清理',
        'check': check_global_accumulation,
    },
    {
        'id': 'PYAST029',
        'name': '内存泄漏-未关闭资源',
        'level': 'warning',
        'category': 'memory',
        'module_id': '4',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测open()无with语句或无close()调用',
        'check': check_unclosed_resources,
    },
    {
        'id': 'PYAST030',
        'name': '内存泄漏-大常量',
        'level': 'info',
        'category': 'memory',
        'module_id': '4',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测函数内定义大列表/字典常量导致重复创建',
        'check': check_large_literal_in_function,
    },
    {
        'id': 'PYAST031',
        'name': '内存泄漏-GC关闭',
        'level': 'warning',
        'category': 'memory',
        'module_id': '4',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测gc.disable()调用且无对应gc.enable()',
        'check': check_gc_disabled,
    },
    {
        'id': 'PYAST032',
        'name': '内存泄漏-signal handler',
        'level': 'info',
        'category': 'memory',
        'module_id': '4',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测signal handler中的内存泄漏风险',
        'check': check_signal_handler_leak,
    },
]
