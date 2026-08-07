# -*- coding: utf-8 -*-
"""
异步安全AST深度分析规则集
检测async函数中的同步阻塞IO、event loop阻塞、协程泄漏等
规则ID: PYAST033 - PYAST040
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


# 已知的同步阻塞IO调用
SYNC_BLOCKING_CALLS = {
    # HTTP
    'get': 'requests.get', 'post': 'requests.post', 'put': 'requests.put',
    'delete': 'requests.delete', 'head': 'requests.head', 'patch': 'requests.patch',
    'request': 'requests.request',
    # 文件IO
    'open': '内置open()',
    # 时间
    'sleep': 'time.sleep()',
    # 子进程
    'run': 'subprocess.run()', 'call': 'subprocess.call()',
    'Popen': 'subprocess.Popen()', 'check_output': 'subprocess.check_output()',
    'check_call': 'subprocess.check_call()',
    # 数据库（同步驱动）
    'execute': '数据库execute()', 'executemany': '数据库executemany()',
    # socket
    'recv': 'socket.recv()', 'send': 'socket.send()',
    'recvfrom': 'socket.recvfrom()', 'sendto': 'socket.sendto()',
    'connect': 'socket.connect()', 'accept': 'socket.accept()',
    # 其他
    'read': '文件read()', 'write': '文件write()', 'readlines': '文件readlines()',
    'input': 'input()', 'getpass': 'getpass()',
}

# 安全的异步替代
ASYNC_ALTERNATIVES = {
    'requests': 'aiohttp/httpx.AsyncClient',
    'time.sleep': 'asyncio.sleep',
    'subprocess.run': 'asyncio.create_subprocess_exec',
    'open': 'aiofiles.open',
}


def _is_async_function(node: ast.AST) -> bool:
    """检查节点是否是async函数"""
    return isinstance(node, ast.AsyncFunctionDef)


def _get_blocking_module(func_node: ast.AST) -> Optional[str]:
    """获取阻塞调用所属模块"""
    if isinstance(func_node, ast.Attribute):
        if isinstance(func_node.value, ast.Name):
            module = func_node.value.id
            blocking_modules = {
                'requests': 'requests', 'urllib': 'urllib',
                'time': 'time', 'subprocess': 'subprocess',
                'socket': 'socket', 'os': 'os',
                'sqlite3': 'sqlite3', 'MySQLdb': 'MySQLdb',
                'psycopg2': 'psycopg2', 'pymongo': 'pymongo',
            }
            if module in blocking_modules:
                return blocking_modules[module]
    return None


def check_sync_io_in_async(context) -> List[Dict]:
    """PYAST033 - 检测async函数中调用同步阻塞IO"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        # 快速检查是否有async函数
        if not re.search(r'async\s+def\s+', content):
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        lines = content.split('\n')
        
        for node in tree.body:
            if not _is_async_function(node):
                continue
            
            issues = []
            
            for child in ast.walk(node):
                if not isinstance(child, ast.Call):
                    continue
                
                # 检查是否是同步阻塞调用
                blocking_module = _get_blocking_module(child.func)
                if blocking_module:
                    # 排除一些安全的调用
                    func_name = ''
                    if isinstance(child.func, ast.Attribute):
                        func_name = child.func.attr
                    
                    # requests.get/post等是明确的阻塞调用
                    if blocking_module == 'requests':
                        issues.append((child.lineno, f'async函数中调用{blocking_module}.{func_name}()'))
                    elif blocking_module == 'time' and func_name == 'sleep':
                        issues.append((child.lineno, 'async函数中调用time.sleep()，应使用asyncio.sleep()'))
                    elif blocking_module == 'subprocess':
                        issues.append((child.lineno, f'async函数中调用{blocking_module}.{func_name}()，应使用asyncio子进程'))
                
                # 检查内置open()
                if isinstance(child.func, ast.Name) and child.func.id == 'open':
                    issues.append((child.lineno, 'async函数中使用同步open()，建议使用aiofiles.open()'))
                
                # 检查直接导入的requests方法
                if isinstance(child.func, ast.Name):
                    if child.func.id in ('get', 'post', 'put', 'delete', 'head', 'patch'):
                        # 检查上下文是否来自requests
                        ctx = '\n'.join(lines[max(0, child.lineno-10):child.lineno])
                        if re.search(r'from\s+requests\s+import|import\s+requests', ctx):
                            issues.append((child.lineno, f'async函数中调用requests的{child.func.id}()'))
            
            if issues:
                results.append({
                    'id': 'PYAST033',
                    'name': '异步安全-同步阻塞IO',
                    'level': 'warning',
                    'message': f'async函数{node.name}()中存在{len(issues)}处同步阻塞调用',
                    'file': fpath,
                    'line': issues[0][0],
                    'snippet': issues[0][1],
                    'fix': '使用异步替代：aiohttp替代requests、asyncio.sleep替代time.sleep、aiofiles替代open',
                })
    
    return results


def check_event_loop_blocking(context) -> List[Dict]:
    """PYAST034 - 检测async函数中的CPU密集型操作"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        if not re.search(r'async\s+def\s+', content):
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        lines = content.split('\n')
        
        for node in tree.body:
            if not _is_async_function(node):
                continue
            
            issues = []
            
            # 统计函数体复杂度（简易CPU密集型检测）
            complexity = 0
            for child in ast.walk(node):
                if isinstance(child, (ast.For, ast.While)):
                    complexity += 5
                elif isinstance(child, ast.If):
                    complexity += 1
                elif isinstance(child, ast.comprehension):
                    complexity += 3
            
            # 检测排序/大数据操作
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    if isinstance(child.func, ast.Attribute):
                        if child.func.attr in ('sort', 'sorted'):
                            issues.append((child.lineno, 'async函数中执行排序操作'))
            
            # 高复杂度async函数
            if complexity > 30:
                issues.append((node.lineno, f'async函数{node.name}()复杂度过高({complexity})，可能阻塞event loop'))
            
            if issues:
                results.append({
                    'id': 'PYAST034',
                    'name': '异步安全-event loop阻塞',
                    'level': 'info',
                    'message': f'async函数{node.name}()中可能存在CPU密集型操作阻塞event loop',
                    'file': fpath,
                    'line': issues[0][0],
                    'snippet': issues[0][1],
                    'fix': '将CPU密集操作移至线程池：await loop.run_in_executor(None, cpu_heavy_func)',
                })
    
    return results


def check_coroutine_leak(context) -> List[Dict]:
    """PYAST035 - 检测协程泄漏（创建Task但未await/取消）"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        if not re.search(r'(asyncio\.create_task|asyncio\.ensure_future|loop\.create_task|asyncio\.Task)', content):
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        lines = content.split('\n')
        
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            
            # 查找create_task调用
            task_vars = []
            for child in ast.walk(node):
                if isinstance(child, ast.Assign):
                    if isinstance(child.value, ast.Call):
                        func = child.value.func
                        is_create_task = False
                        if isinstance(func, ast.Attribute):
                            if func.attr in ('create_task', 'ensure_future'):
                                is_create_task = True
                        elif isinstance(func, ast.Name):
                            if func.id in ('create_task', 'ensure_future'):
                                is_create_task = True
                        
                        if is_create_task and isinstance(child.targets[0], ast.Name):
                            task_vars.append(child.targets[0].id)
            
            # 检查task变量是否有await/cancel/add_done_callback
            for var_name in task_vars:
                has_await = bool(re.search(
                    rf'await\s+{re.escape(var_name)}|{re.escape(var_name)}\s*=\s*await|{re.escape(var_name)}\.\s*(?:cancel|result|done|add_done_callback)',
                    content
                ))
                if not has_await:
                    results.append({
                        'id': 'PYAST035',
                        'name': '异步安全-协程泄漏',
                        'level': 'warning',
                        'message': f'Task变量{var_name}创建后未被await或取消，可能泄漏',
                        'file': fpath,
                        'line': node.lineno,
                        'snippet': f'变量: {var_name}',
                        'fix': '确保Task被await、加入TaskGroup管理，或添加add_done_callback处理异常',
                    })
    
    return results


def check_async_with_misuse(context) -> List[Dict]:
    """PYAST036 - 检测async with/async for误用"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        if not re.search(r'(async\s+with|async\s+for)', content):
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        lines = content.split('\n')
        issues = []
        
        # 检测在非async函数中使用async with/for
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                is_async = isinstance(node, ast.AsyncFunctionDef)
                for child in ast.walk(node):
                    if isinstance(child, (ast.AsyncWith, ast.AsyncFor)):
                        if not is_async:
                            issues.append((child.lineno, '非async函数中使用async with/for'))
        
        if issues:
            results.append({
                'id': 'PYAST036',
                'name': '异步安全-async误用',
                'level': 'error',
                'message': f'检测到{len(issues)}处async with/for在非async函数中使用',
                'file': fpath,
                'line': issues[0][0],
                'snippet': lines[issues[0][0]-1].strip()[:120] if issues[0][0]-1 < len(lines) else '',
                'fix': '将函数声明为async def，或使用对应的同步版本',
            })
    
    return results


def check_thread_asyncio_mix(context) -> List[Dict]:
    """PYAST037 - 检测混用threading + asyncio的风险"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        has_threading = bool(re.search(r'(import\s+threading|from\s+threading|Thread\s*\(|threading\.Thread)', content))
        has_asyncio = bool(re.search(r'(import\s+asyncio|from\s+asyncio|asyncio\.run|async\s+def)', content))
        
        if not (has_threading and has_asyncio):
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        lines = content.split('\n')
        issues = []
        
        # 检测在async函数中直接创建Thread
        for node in tree.body:
            if _is_async_function(node):
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        if isinstance(child.func, ast.Attribute):
                            if isinstance(child.func.value, ast.Name):
                                if child.func.value.id == 'threading' and child.func.attr in ('Thread', 'Lock', 'Event'):
                                    issues.append((child.lineno, f'async函数中直接创建threading.{child.func.attr}'))
                        elif isinstance(child.func, ast.Name):
                            if child.func.id == 'Thread':
                                issues.append((child.lineno, 'async函数中直接创建Thread'))
        
        # 检测在Thread target中调用asyncio.run
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_name = ''
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    func_name = node.func.attr
                
                if func_name == 'Thread':
                    for kw in node.keywords:
                        if kw.arg == 'target' and isinstance(kw.value, ast.Name):
                            # 查找target函数
                            for fn in tree.body:
                                if isinstance(fn, ast.FunctionDef) and fn.name == kw.value.id:
                                    for sub in ast.walk(fn):
                                        if isinstance(sub, ast.Call):
                                            if isinstance(sub.func, ast.Attribute):
                                                if isinstance(sub.func.value, ast.Name):
                                                    if sub.func.value.id == 'asyncio' and sub.func.attr == 'run':
                                                        issues.append((sub.lineno, 'Thread中调用asyncio.run()可能导致event loop冲突'))
        
        if issues:
            results.append({
                'id': 'PYAST037',
                'name': '异步安全-thread/asyncio混用',
                'level': 'warning',
                'message': f'检测到{len(issues)}处threading与asyncio混用风险',
                'file': fpath,
                'line': issues[0][0],
                'snippet': issues[0][1],
                'fix': '使用loop.run_in_executor()在线程池运行同步代码，或用asyncio.to_thread()包装',
            })
    
    return results


def check_run_in_executor_missing(context) -> List[Dict]:
    """PYAST038 - 检测async函数中直接调用可能的阻塞操作而未使用run_in_executor"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    # 已知阻塞的第三方库
    blocking_libs = [
        'redis', 'Redis', 'pymongo', 'MySQLdb', 'psycopg2',
        'cx_Oracle', 'pyodbc', 'sqlite3',
        'paramiko', 'fabric',
    ]
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        if not re.search(r'async\s+def\s+', content):
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        lines = content.split('\n')
        issues = []
        
        # 检查import
        blocking_imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in blocking_libs:
                        blocking_imports.add(alias.asname or alias.name)
            if isinstance(node, ast.ImportFrom):
                if node.module and node.module.split('.')[0] in blocking_libs:
                    for alias in node.names:
                        blocking_imports.add(alias.asname or alias.name)
        
        if not blocking_imports:
            continue
        
        # 检查async函数中使用这些库
        for node in tree.body:
            if not _is_async_function(node):
                continue
            
            for child in ast.walk(node):
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                    if isinstance(child.func.value, ast.Name):
                        if child.func.value.id in blocking_imports:
                            issues.append((child.lineno, f'async函数中直接调用阻塞库{child.func.value.id}.{child.func.attr}()'))
            
            if issues:
                results.append({
                    'id': 'PYAST038',
                    'name': '异步安全-阻塞库调用',
                    'level': 'warning',
                    'message': f'async函数{node.name}()中直接调用阻塞库',
                    'file': fpath,
                    'line': issues[0][0],
                    'snippet': issues[0][1],
                    'fix': '使用await loop.run_in_executor(None, blocking_call)包装阻塞调用',
                })
                break
    
    return results


def check_asyncio_gather_exception(context) -> List[Dict]:
    """PYAST039 - 检测asyncio.gather未处理异常"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        if 'asyncio.gather' not in content and 'gather(' not in content:
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        lines = content.split('\n')
        issues = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                is_gather = False
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr == 'gather' and isinstance(node.func.value, ast.Name):
                        if node.func.value.id == 'asyncio':
                            is_gather = True
                elif isinstance(node.func, ast.Name):
                    if node.func.id == 'gather':
                        is_gather = True
                
                if not is_gather:
                    continue
                
                # 检查是否有return_exceptions=True
                has_return_exceptions = False
                for kw in node.keywords:
                    if kw.arg == 'return_exceptions':
                        if isinstance(kw.value, ast.Constant) and kw.value.value is True:
                            has_return_exceptions = True
                
                # 检查是否在try块中
                in_try = False
                for parent in ast.walk(tree):
                    if isinstance(parent, ast.Try):
                        for body_node in ast.walk(parent):
                            if body_node is node:
                                in_try = True
                                break
                
                if not has_return_exceptions and not in_try:
                    issues.append(node.lineno)
        
        if issues:
            results.append({
                'id': 'PYAST039',
                'name': '异步安全-gather异常',
                'level': 'info',
                'message': f'检测到{len(issues)}处asyncio.gather()未处理异常',
                'file': fpath,
                'line': issues[0],
                'snippet': lines[issues[0]-1].strip()[:120] if issues[0]-1 < len(lines) else '',
                'fix': '使用try/except包裹gather()或设置return_exceptions=True防止一个任务失败取消所有',
            })
    
    return results


def check_loop_run_in_thread(context) -> List[Dict]:
    """PYAST040 - 检测asyncio.get_event_loop()在多线程中的误用"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        if 'get_event_loop' not in content:
            continue
        
        has_thread = bool(re.search(r'(Thread|threading|multiprocessing|Process)', content))
        
        if not has_thread:
            continue
        
        lines = content.split('\n')
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            if re.search(r'asyncio\.get_event_loop\s*\(\)', stripped):
                # 检查是否在函数内（可能从不同线程调用）
                # 查找所在函数
                func_ctx = '\n'.join(lines[max(0, i-20):i+1])
                if re.search(r'def\s+\w+', func_ctx):
                    results.append({
                        'id': 'PYAST040',
                        'name': '异步安全-event loop误用',
                        'level': 'warning',
                        'message': 'asyncio.get_event_loop()在多线程环境中使用可能导致RuntimeError',
                        'file': fpath,
                        'line': i + 1,
                        'snippet': stripped[:120],
                        'fix': '使用asyncio.get_running_loop()或asyncio.new_event_loop()替代，Python 3.10+中get_event_loop已弃用',
                    })
                    break
    
    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'PYAST033',
        'name': '异步安全-同步阻塞IO',
        'level': 'warning',
        'category': 'async',
        'module_id': '4',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测async函数中调用同步阻塞IO（requests/time.sleep/open等）',
        'check': check_sync_io_in_async,
    },
    {
        'id': 'PYAST034',
        'name': '异步安全-event loop阻塞',
        'level': 'info',
        'category': 'async',
        'module_id': '4',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测async函数中CPU密集型操作阻塞event loop',
        'check': check_event_loop_blocking,
    },
    {
        'id': 'PYAST035',
        'name': '异步安全-协程泄漏',
        'level': 'warning',
        'category': 'async',
        'module_id': '4',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测create_task创建后未await/取消的Task',
        'check': check_coroutine_leak,
    },
    {
        'id': 'PYAST036',
        'name': '异步安全-async误用',
        'level': 'error',
        'category': 'async',
        'module_id': '4',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测async with/for在非async函数中的误用',
        'check': check_async_with_misuse,
    },
    {
        'id': 'PYAST037',
        'name': '异步安全-thread/asyncio混用',
        'level': 'warning',
        'category': 'async',
        'module_id': '4',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测混用threading和asyncio的风险模式',
        'check': check_thread_asyncio_mix,
    },
    {
        'id': 'PYAST038',
        'name': '异步安全-阻塞库调用',
        'level': 'warning',
        'category': 'async',
        'module_id': '4',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测async函数中直接调用同步阻塞的第三方库',
        'check': check_run_in_executor_missing,
    },
    {
        'id': 'PYAST039',
        'name': '异步安全-gather异常',
        'level': 'info',
        'category': 'async',
        'module_id': '4',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测asyncio.gather()未处理异常的情况',
        'check': check_asyncio_gather_exception,
    },
    {
        'id': 'PYAST040',
        'name': '异步安全-event loop误用',
        'level': 'warning',
        'category': 'async',
        'module_id': '4',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测asyncio.get_event_loop()在多线程环境中的误用',
        'check': check_loop_run_in_thread,
    },
]
