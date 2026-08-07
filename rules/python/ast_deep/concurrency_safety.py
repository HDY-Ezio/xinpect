# -*- coding: utf-8 -*-
"""
并发安全AST深度分析规则集
检测共享状态无锁访问、竞态条件、连接池泄漏、死锁风险等
规则ID: PYAST009 - PYAST016
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


def _is_threading_import(node: ast.AST) -> bool:
    """检查是否是threading相关import"""
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name in ('threading', 'multiprocessing', '_thread'):
                return True
    if isinstance(node, ast.ImportFrom):
        if node.module and node.module.split('.')[0] in ('threading', 'multiprocessing', '_thread'):
            return True
    return False


def _has_lock_context(tree: ast.Module) -> Set[str]:
    """查找使用Lock/RLock保护的变量名集合"""
    protected = set()
    for node in ast.walk(tree):
        # with lock: 或 with self.lock:
        if isinstance(node, ast.With):
            for item in node.items:
                if isinstance(item.context_expr, ast.Call):
                    if isinstance(item.context_expr.func, ast.Attribute):
                        if item.context_expr.func.attr in ('acquire', '__enter__'):
                            pass
                # 简单标记：with内有lock操作
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Attribute) and sub.attr in ('acquire', 'release'):
                        if isinstance(sub.value, ast.Name):
                            protected.add(sub.value.id)
    return protected


def _find_global_assignments(tree: ast.Module) -> List[Tuple[str, int]]:
    """查找模块级变量赋值"""
    globals_vars = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    globals_vars.append((target.id, node.lineno))
    return globals_vars


def _find_class_attributes(tree: ast.Module) -> List[Tuple[str, str, int]]:
    """查找类属性（在类体内但不在方法内的赋值）"""
    class_attrs = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name):
                            class_attrs.append((node.name, target.id, item.lineno))
                elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    class_attrs.append((node.name, item.target.id, item.lineno))
    return class_attrs


def check_shared_state_no_lock(context) -> List[Dict]:
    """PYAST009 - 检测共享状态无锁访问"""
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
        
        # 检查是否有threading相关import
        has_threading = any(_is_threading_import(node) for node in ast.walk(tree))
        if not has_threading:
            continue
        
        # 检查是否有Lock相关定义
        has_lock = bool(re.search(r'(Lock|RLock|Semaphore|threading\.Lock|threading\.RLock)', content))
        
        # 查找模块级可变变量
        global_vars = _find_global_assignments(tree)
        mutable_globals = []
        for var_name, lineno in global_vars:
            # 检查变量类型是否可变
            for node in tree.body:
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == var_name:
                            if isinstance(node.value, (ast.List, ast.Dict, ast.Set)):
                                mutable_globals.append((var_name, lineno))
                                break
                            # 检查是否是空的 dict()/list() 调用
                            if isinstance(node.value, ast.Call):
                                if isinstance(node.value.func, ast.Name) and node.value.func.id in ('dict', 'list', 'set', 'defaultdict', 'deque'):
                                    mutable_globals.append((var_name, lineno))
                                    break
        
        # 检查这些全局变量是否在函数中被读写但无锁保护
        if mutable_globals and not has_lock:
            unprotected_access = []
            for var_name, def_lineno in mutable_globals:
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    stripped = line.strip()
                    if stripped.startswith('#') or stripped.startswith('def ') or stripped.startswith('class '):
                        continue
                    # 检测对全局可变变量的修改操作
                    if re.search(rf'\b{re.escape(var_name)}\s*(?:\.append|\.extend|\.update|\.add|\.insert|\.pop|\.remove|\[.*\]\s*=)', line):
                        # 检查附近是否有lock操作
                        ctx = '\n'.join(lines[max(0, i-10):i+3])
                        if not re.search(r'(acquire|release|with.*lock|with.*Lock)', ctx, re.IGNORECASE):
                            unprotected_access.append((var_name, i + 1))
                            break
            
            if unprotected_access:
                results.append({
                    'id': 'PYAST009',
                    'name': '并发安全-共享状态无锁',
                    'level': 'warning',
                    'message': f'检测到{len(unprotected_access)}个全局可变变量在多线程环境中无锁保护',
                    'file': fpath,
                    'line': unprotected_access[0][1],
                    'snippet': f'变量: {", ".join(v for v, _ in unprotected_access[:3])}',
                    'fix': '使用threading.Lock保护共享状态访问，或使用threading.local/queue.Queue',
                })
    
    return results


def check_race_condition(context) -> List[Dict]:
    """PYAST010 - 检测check-then-act竞态条件模式"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    # check-then-act 模式：if x.exists(): x.do() 或 if os.path.exists(): open()
    race_patterns = [
        (r'if\s+os\.path\.exists\s*\(.*?\)\s*:.*?(?:open|remove|rename|unlink)\s*\(', 
         '文件存在性检查与操作之间存在TOCTOU竞态'),
        (r'if\s+.*?in\s+dict\s*:.*?(?:del|pop)\s*\(',
         '字典键检查与删除之间存在竞态'),
        (r'if\s+.*?is\s+not\s+None\s*:.*?(?:del|close|stop)\s*\(',
         'None检查与操作之间存在竞态'),
    ]
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        has_threading = bool(re.search(r'(threading|multiprocessing|Thread|asyncio)', content))
        if not has_threading:
            continue
        
        lines = content.split('\n')
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            
            # 简单的TOCTOU检测：if exists followed by file operation on next line
            if re.search(r'if\s+os\.path\.exists\s*\(', stripped):
                # 检查下一行是否有文件操作
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if re.search(r'(open|remove|rename|os\.unlink|shutil)', next_line):
                        results.append({
                            'id': 'PYAST010',
                            'name': '并发安全-竞态条件',
                            'level': 'info',
                            'message': '文件操作存在TOCTOU竞态：先检查存在性再操作',
                            'file': fpath,
                            'line': i + 1,
                            'snippet': stripped[:120],
                            'fix': '直接使用try/except处理文件操作，避免先检查再操作的模式',
                        })
    
    return results


def check_connection_leak(context) -> List[Dict]:
    """PYAST011 - 检测连接/资源获取后未在finally/with中释放"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    # 连接获取模式
    conn_patterns = [
        r'(?:connect|get_connection|create_engine|Session|Connection)\s*\(',
        r'(?:pool|Pool)\s*\.\s*(?:get|acquire|checkout)\s*\(',
        r'(?:redis|Redis|pymongo|MongoClient|MySQLdb|psycopg2)',
    ]
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        lines = content.split('\n')
        leaks = []
        
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            
            # 检查是否是连接获取调用
            func_name = ''
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                func_name = node.func.attr
            
            is_conn_get = func_name in ('connect', 'get_connection', 'create_engine', 'Session')
            if not is_conn_get:
                continue
            
            # 检查这个调用是否在with语句内（安全）
            in_with = False
            in_try_finally = False
            for parent in ast.walk(tree):
                if isinstance(parent, ast.With):
                    for item in parent.items:
                        if item.context_expr is node or (
                            isinstance(item.context_expr, ast.Call) and 
                            item.context_expr.lineno == node.lineno
                        ):
                            in_with = True
                            break
                if isinstance(parent, ast.Try):
                    if parent.finalbody:
                        # 检查是否在try块内
                        for body_node in parent.body:
                            if hasattr(body_node, 'lineno') and body_node.lineno == node.lineno:
                                # 检查finally中是否有close
                                for fin_node in ast.walk(ast.Module(body=parent.finalbody, type_ignores=[])):
                                    if isinstance(fin_node, ast.Attribute) and fin_node.attr in ('close', 'dispose', 'release'):
                                        in_try_finally = True
                                        break
            
            if not in_with and not in_try_finally:
                # 检查赋值目标变量名，看后续是否有close调用
                assigned_var = None
                for parent in ast.walk(tree):
                    if isinstance(parent, ast.Assign):
                        if isinstance(parent.value, ast.Call) and parent.value.lineno == node.lineno:
                            if isinstance(parent.targets[0], ast.Name):
                                assigned_var = parent.targets[0].id
            
                if assigned_var:
                    # 检查该函数范围内是否有close调用
                    func_has_close = False
                    for fn in ast.walk(tree):
                        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            if fn.lineno <= node.lineno:
                                func_end = fn.end_lineno if hasattr(fn, 'end_lineno') and fn.end_lineno else node.lineno + 50
                                for sub in ast.walk(fn):
                                    if isinstance(sub, ast.Attribute) and sub.attr in ('close', 'dispose', 'release'):
                                        if isinstance(sub.value, ast.Name) and sub.value.id == assigned_var:
                                            if sub.lineno >= node.lineno and sub.lineno <= func_end:
                                                func_has_close = True
                
                    if not func_has_close:
                        leaks.append(node.lineno)
        
        if leaks:
            results.append({
                'id': 'PYAST011',
                'name': '并发安全-连接泄漏',
                'level': 'warning',
                'message': f'检测到{len(leaks)}处连接/资源获取后可能未正确释放',
                'file': fpath,
                'line': leaks[0],
                'snippet': lines[leaks[0]-1].strip()[:120] if leaks[0]-1 < len(lines) else '',
                'fix': '使用with语句管理连接生命周期，或在finally块中确保close()',
            })
    
    return results


def check_deadlock_risk(context) -> List[Dict]:
    """PYAST012 - 检测嵌套锁获取的死锁风险"""
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
        
        # 查找函数内的嵌套with lock模式
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            
            # 收集函数内所有with语句及其锁变量
            with_locks = []
            for child in ast.walk(node):
                if isinstance(child, ast.With):
                    for item in child.items:
                        expr = item.context_expr
                        lock_name = ''
                        if isinstance(expr, ast.Name):
                            lock_name = expr.id
                        elif isinstance(expr, ast.Attribute):
                            lock_name = expr.attr
                        elif isinstance(expr, ast.Call):
                            if isinstance(expr.func, ast.Attribute):
                                lock_name = expr.func.attr
                            elif isinstance(expr.func, ast.Name):
                                lock_name = expr.func.id
                        
                        if lock_name:
                            with_locks.append((lock_name, child.lineno, child))
            
            # 检测嵌套的with lock
            for i, (lock1, line1, with1) in enumerate(with_locks):
                for j, (lock2, line2, with2) in enumerate(with_locks):
                    if i >= j:
                        continue
                    # 检查with2是否嵌套在with1内
                    for sub in ast.walk(with1):
                        if sub is with2:
                            if lock1 != lock2:
                                results.append({
                                    'id': 'PYAST012',
                                    'name': '并发安全-死锁风险',
                                    'level': 'warning',
                                    'message': f'嵌套获取不同锁({lock1}, {lock2})可能导致死锁',
                                    'file': fpath,
                                    'line': line2,
                                    'snippet': lines[line2-1].strip()[:120] if line2-1 < len(lines) else '',
                                    'fix': '确保全局锁获取顺序一致，或使用单一锁/超时机制',
                                })
                            break
    
    return results


def check_gil_bypass_risk(context) -> List[Dict]:
    """PYAST013 - 检测ctypes/cffi中释放GIL后访问Python对象的风险"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    # 正则检测 ctypes 中 GIL 释放
    gil_patterns = [
        (r'ctypes\s*\.\s*CDLL|ctypes\s*\.\s*PyDLL', 'ctypes库加载'),
        (r'Py_BEGIN_ALLOW_THREADS|Py_END_ALLOW_THREADS', '手动GIL释放'),
        (r'\.release_gil\s*\(|gil_release', '显式GIL释放调用'),
    ]
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        has_ctypes = bool(re.search(r'(ctypes|cffi|CFFI|CDLL|Windll)', content))
        if not has_ctypes:
            continue
        
        lines = content.split('\n')
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            
            # 检测ctypes调用后紧跟Python对象操作
            if re.search(r'(ctypes\.\w+|lib\.\w+|dll\.\w+)\s*\(', stripped):
                # 检查附近是否有Python对象访问
                ctx = '\n'.join(lines[max(0, i-3):min(len(lines), i+5)])
                if re.search(r'(Py_\w+|PyObject|Py_INCREF|Py_DECREF)', ctx):
                    results.append({
                        'id': 'PYAST013',
                        'name': '并发安全-GIL绕过',
                        'level': 'warning',
                        'message': 'ctypes/cffi调用中可能存在GIL释放后访问Python对象的风险',
                        'file': fpath,
                        'line': i + 1,
                        'snippet': stripped[:120],
                        'fix': '确保ctypes调用期间不访问Python对象，或使用PyDLL保持GIL',
                    })
                    break
    
    return results


def check_thread_local_abuse(context) -> List[Dict]:
    """PYAST014 - 检测threading.local在asyncio中的误用"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        has_threading_local = bool(re.search(r'threading\.local\s*\(|threading_local', content))
        has_async = bool(re.search(r'async\s+def|asyncio|await\s+', content))
        
        if has_threading_local and has_async:
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if re.search(r'threading\.local\s*\(', line):
                    results.append({
                        'id': 'PYAST014',
                        'name': '并发安全-threading.local误用',
                        'level': 'warning',
                        'message': '同一文件同时使用threading.local和async/asyncio，可能导致数据混淆',
                        'file': fpath,
                        'line': i + 1,
                        'snippet': line.strip()[:120],
                        'fix': '在asyncio中使用contextvars.ContextVar替代threading.local',
                    })
                    break
    
    return results


def check_multiprocessing_unsafe(context) -> List[Dict]:
    """PYAST015 - 检测multiprocessing中不安全的共享方式"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        has_mp = bool(re.search(r'multiprocessing|Process\(|Pool\(', content))
        if not has_mp:
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        lines = content.split('\n')
        issues = []
        
        # 检测全局变量在多进程函数中被修改
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_name = ''
                if isinstance(node.func, ast.Attribute):
                    func_name = node.func.attr
                if func_name in ('Process', 'Pool'):
                    # 检查target参数引用的函数
                    for kw in node.keywords:
                        if kw.arg == 'target' and isinstance(kw.value, ast.Name):
                            target_func = kw.value.id
                            # 查找该函数定义
                            for n in tree.body:
                                if isinstance(n, ast.FunctionDef) and n.name == target_func:
                                    # 检查函数体是否访问了全局可变变量
                                    for sub in ast.walk(n):
                                        if isinstance(sub, ast.Global):
                                            issues.append((n.lineno, f'函数{target_func}声明global变量'))
                                            break
        
        if issues:
            results.append({
                'id': 'PYAST015',
                'name': '并发安全-多进程共享',
                'level': 'warning',
                'message': f'检测到{len(issues)}处多进程中的不安全共享方式',
                'file': fpath,
                'line': issues[0][0],
                'snippet': issues[0][1],
                'fix': '使用multiprocessing.Manager/Queue/Pipe进行进程间通信，避免直接共享全局变量',
            })
    
    return results


def check_lock_timeout_missing(context) -> List[Dict]:
    """PYAST016 - 检测Lock获取未设置timeout"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        has_lock = bool(re.search(r'(Lock|RLock|Semaphore|Mutex)', content))
        if not has_lock:
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        lines = content.split('\n')
        issues = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == 'acquire':
                    # 检查是否有timeout参数
                    has_timeout = False
                    for kw in node.keywords:
                        if kw.arg == 'timeout':
                            has_timeout = True
                            break
                    # 位置参数也算
                    if node.args:
                        has_timeout = True
                    
                    if not has_timeout:
                        issues.append(node.lineno)
        
        if issues:
            results.append({
                'id': 'PYAST016',
                'name': '并发安全-锁无超时',
                'level': 'info',
                'message': f'检测到{len(issues)}处Lock.acquire()未设置timeout',
                'file': fpath,
                'line': issues[0],
                'snippet': lines[issues[0]-1].strip()[:120] if issues[0]-1 < len(lines) else '',
                'fix': '为Lock.acquire()设置timeout参数避免无限等待：lock.acquire(timeout=5)',
            })
    
    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'PYAST009',
        'name': '并发安全-共享状态无锁',
        'level': 'warning',
        'category': 'concurrency',
        'module_id': '6',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测多线程环境下全局变量/类属性的无锁读写',
        'check': check_shared_state_no_lock,
    },
    {
        'id': 'PYAST010',
        'name': '并发安全-竞态条件',
        'level': 'info',
        'category': 'concurrency',
        'module_id': '6',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测check-then-act模式的TOCTOU竞态条件',
        'check': check_race_condition,
    },
    {
        'id': 'PYAST011',
        'name': '并发安全-连接泄漏',
        'level': 'warning',
        'category': 'concurrency',
        'module_id': '6',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测连接获取后未在finally/with中释放',
        'check': check_connection_leak,
    },
    {
        'id': 'PYAST012',
        'name': '并发安全-死锁风险',
        'level': 'warning',
        'category': 'concurrency',
        'module_id': '6',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测嵌套锁获取顺序不一致导致的死锁风险',
        'check': check_deadlock_risk,
    },
    {
        'id': 'PYAST013',
        'name': '并发安全-GIL绕过',
        'level': 'warning',
        'category': 'concurrency',
        'module_id': '6',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测ctypes/cffi调用中释放GIL后访问Python对象的风险',
        'check': check_gil_bypass_risk,
    },
    {
        'id': 'PYAST014',
        'name': '并发安全-threading.local误用',
        'level': 'warning',
        'category': 'concurrency',
        'module_id': '6',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测threading.local在asyncio环境中的误用',
        'check': check_thread_local_abuse,
    },
    {
        'id': 'PYAST015',
        'name': '并发安全-多进程共享',
        'level': 'warning',
        'category': 'concurrency',
        'module_id': '6',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测multiprocessing中不安全的全局变量共享',
        'check': check_multiprocessing_unsafe,
    },
    {
        'id': 'PYAST016',
        'name': '并发安全-锁无超时',
        'level': 'info',
        'category': 'concurrency',
        'module_id': '6',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测Lock.acquire()未设置timeout参数',
        'check': check_lock_timeout_missing,
    },
]
