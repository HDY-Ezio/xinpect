# -*- coding: utf-8 -*-
"""
资源管理AST深度分析规则集
检测上下文管理器缺失、临时文件未清理、subprocess无timeout等
规则ID: PYAST041 - PYAST048
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


def check_missing_context_manager(context) -> List[Dict]:
    """PYAST041 - 检测需要with语句的资源操作"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    # 需要上下文管理器的操作
    resource_ops = [
        # (模式, 描述, 安全替代)
        ('open', '文件操作', 'with open() as f:'),
        ('connect', '数据库连接', 'with engine.connect() as conn:'),
        ('socket', 'Socket连接', 'with socket.socket() as s:'),
        ('Lock', '锁操作', 'with lock:'),
        ('Semaphore', '信号量', 'with semaphore:'),
    ]
    
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
            if not isinstance(node, ast.Call):
                continue
            
            func_name = ''
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                func_name = node.func.attr
            
            # 检查open()不在with中
            if func_name == 'open':
                in_with = False
                for parent in ast.walk(tree):
                    if isinstance(parent, ast.With):
                        for item in parent.items:
                            if isinstance(item.context_expr, ast.Call):
                                if item.context_expr.lineno == node.lineno:
                                    if isinstance(item.context_expr.func, ast.Name) and item.context_expr.func.id == 'open':
                                        in_with = True
                
                if not in_with:
                    # 检查是否赋值给了变量并后续有close
                    assigned_var = None
                    for parent in ast.walk(tree):
                        if isinstance(parent, ast.Assign):
                            if isinstance(parent.value, ast.Call) and parent.value.lineno == node.lineno:
                                if isinstance(parent.targets[0], ast.Name):
                                    assigned_var = parent.targets[0].id
                    
                    has_close = False
                    if assigned_var:
                        has_close = bool(re.search(
                            rf'\b{re.escape(assigned_var)}\s*\.\s*(?:close|__exit__)\s*\(',
                            content
                        ))
                    
                    if not has_close:
                        issues.append((node.lineno, 'open()未使用with语句且无close()调用'))
        
        if issues:
            results.append({
                'id': 'PYAST041',
                'name': '资源管理-上下文管理器缺失',
                'level': 'warning',
                'message': f'检测到{len(issues)}处资源操作未使用with语句',
                'file': fpath,
                'line': issues[0][0],
                'snippet': lines[issues[0][0]-1].strip()[:120] if issues[0][0]-1 < len(lines) else '',
                'fix': '使用with语句自动管理资源生命周期',
            })
    
    return results


def check_temp_file_cleanup(context) -> List[Dict]:
    """PYAST042 - 检测临时文件未清理"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        # 检查是否使用了临时文件/目录
        has_tempfile = bool(re.search(r'(tempfile\.|tmp|/tmp/|temp_dir|temp_path)', content, re.IGNORECASE))
        if not has_tempfile:
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        lines = content.split('\n')
        issues = []
        
        # 检测手动创建/tmp/路径下的文件但无清理
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value.startswith('/tmp/') and not node.value.endswith('/'):
                    # 检查附近是否有os.remove/unlink/cleanup
                    ctx = '\n'.join(lines[max(0, node.lineno-5):min(len(lines), node.lineno+15)])
                    if not re.search(r'(os\.remove|os\.unlink|shutil\.rmtree|cleanup|delete|atexit)', ctx):
                        issues.append((node.lineno, f'硬编码临时路径{node.value}'))
        
        # 检测tempfile.NamedTemporaryFile(delete=False)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in ('NamedTemporaryFile', 'TemporaryDirectory'):
                    has_delete_false = False
                    for kw in node.keywords:
                        if kw.arg == 'delete' and isinstance(kw.value, ast.Constant) and kw.value.value is False:
                            has_delete_false = True
                    if has_delete_false:
                        issues.append((node.lineno, f'tempfile.{node.func.attr}(delete=False)需确保后续清理'))
        
        if issues:
            results.append({
                'id': 'PYAST042',
                'name': '资源管理-临时文件未清理',
                'level': 'warning',
                'message': f'检测到{len(issues)}处临时文件可能未清理',
                'file': fpath,
                'line': issues[0][0],
                'snippet': issues[0][1],
                'fix': '使用tempfile.NamedTemporaryFile(delete=True)或try/finally确保清理',
            })
    
    return results


def check_subprocess_no_timeout(context) -> List[Dict]:
    """PYAST043 - 检测subprocess调用未设置timeout"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        if not re.search(r'subprocess\.', content):
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        lines = content.split('\n')
        issues = []
        
        subprocess_calls = {'run', 'call', 'check_output', 'check_call'}
        
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            
            func_name = ''
            if isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id == 'subprocess':
                    func_name = node.func.attr
            
            if func_name not in subprocess_calls:
                continue
            
            # 检查是否有timeout参数
            has_timeout = False
            for kw in node.keywords:
                if kw.arg == 'timeout':
                    has_timeout = True
                    break
            
            if not has_timeout:
                issues.append((node.lineno, f'subprocess.{func_name}()未设置timeout'))
        
        # 也检测Popen无timeout的communicate/wait
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in ('communicate', 'wait'):
                    has_timeout = any(kw.arg == 'timeout' for kw in node.keywords)
                    if not has_timeout and node.args:
                        pass  # 有位置参数作为timeout
                    
                    if not has_timeout and not node.args:
                        # 检查Popen创建时是否设了timeout
                        # 这里简化处理：communicate/wait本身没有timeout就是风险
                        issues.append((node.lineno, f'.{node.func.attr}()未设置timeout'))
        
        if issues:
            results.append({
                'id': 'PYAST043',
                'name': '资源管理-subprocess无超时',
                'level': 'warning',
                'message': f'检测到{len(issues)}处subprocess调用未设置timeout',
                'file': fpath,
                'line': issues[0][0],
                'snippet': lines[issues[0][0]-1].strip()[:120] if issues[0][0]-1 < len(lines) else '',
                'fix': '为subprocess调用设置timeout参数：subprocess.run(cmd, timeout=30)',
            })
    
    return results


def check_signal_handler_unsafe(context) -> List[Dict]:
    """PYAST044 - 检测signal handler中的不安全操作"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        if 'signal.signal' not in content:
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        lines = content.split('\n')
        
        # 找到signal handler函数
        handler_funcs = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == 'signal' and isinstance(node.func.value, ast.Name):
                    if node.func.value.id == 'signal' and len(node.args) >= 2:
                        handler = node.args[1]
                        if isinstance(handler, ast.Name):
                            handler_funcs.add(handler.id)
                        elif isinstance(handler, ast.Attribute):
                            handler_funcs.add(handler.attr)
        
        if not handler_funcs:
            continue
        
        issues = []
        unsafe_ops = [
            'open', 'print', 'input', 'input',
            'sleep', 'time.sleep',
            'malloc', 'free',
        ]
        
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name in handler_funcs:
                for child in ast.walk(node):
                    # 检测不安全操作
                    if isinstance(child, ast.Call):
                        call_name = ''
                        if isinstance(child.func, ast.Name):
                            call_name = child.func.id
                        elif isinstance(child.func, ast.Attribute):
                            call_name = child.func.attr
                        
                        if call_name in unsafe_ops:
                            issues.append((child.lineno, f'signal handler中调用{call_name}()不安全'))
                    
                    # 检测logging调用（signal handler中logging可能死锁）
                    if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                        if isinstance(child.func.value, ast.Name):
                            if child.func.value.id in ('logging', 'logger', 'log'):
                                issues.append((child.lineno, 'signal handler中调用logging可能死锁'))
                    
                    # 检测异常抛出
                    if isinstance(child, ast.Raise):
                        issues.append((child.lineno, 'signal handler中抛出异常不安全'))
        
        if issues:
            results.append({
                'id': 'PYAST044',
                'name': '资源管理-signal handler不安全',
                'level': 'warning',
                'message': f'检测到{len(issues)}处signal handler中的不安全操作',
                'file': fpath,
                'line': issues[0][0],
                'snippet': issues[0][1],
                'fix': 'signal handler中只做最小操作（设置标志位），避免IO/logging/异常',
            })
    
    return results


def check_logging_no_handler(context) -> List[Dict]:
    """PYAST045 - 检测logging未配置handler"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        if 'logging' not in content:
            continue
        
        # 检查是否有logging配置
        has_config = bool(re.search(
            r'(basicConfig|dictConfig|fileConfig|addHandler|StreamHandler|FileHandler|RotatingFileHandler|logging\.config)',
            content
        ))
        
        # 检查是否有logging调用
        has_logging_calls = bool(re.search(
            r'(logging\.(debug|info|warning|error|critical)|logger\.(debug|info|warning|error|critical))',
            content
        ))
        
        if has_logging_calls and not has_config:
            # 检查是否import了配置模块
            has_import_config = bool(re.search(
                r'(from.*config.*import|import.*logging_config|setup_logging|configure_logging)',
                content
            ))
            
            if not has_import_config:
                results.append({
                    'id': 'PYAST045',
                    'name': '资源管理-logging未配置',
                    'level': 'info',
                    'message': '使用了logging但未找到handler配置，日志可能丢失',
                    'file': fpath,
                    'line': 1,
                    'snippet': 'logging调用存在但无handler配置',
                    'fix': '添加logging.basicConfig()或dictConfig()配置handler',
                })
    
    return results


def check_bare_raise_in_except(context) -> List[Dict]:
    """PYAST046 - 检测except中的裸raise（丢失异常上下文）"""
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
            if isinstance(node, ast.Try):
                for handler in node.handlers:
                    # 检查handler body中的raise语句
                    for child in handler.body:
                        if isinstance(child, ast.Raise):
                            # raise without from (bare raise is OK, raise NewException without from is not)
                            if child.exc is not None and child.cause is None:
                                # raise SomeException() without 'from e'
                                if isinstance(child.exc, ast.Call):
                                    issues.append((child.lineno, 'raise新异常未使用from保留原始异常链'))
        
        if issues:
            results.append({
                'id': 'PYAST046',
                'name': '资源管理-异常链丢失',
                'level': 'info',
                'message': f'检测到{len(issues)}处except中raise新异常未使用from保留异常链',
                'file': fpath,
                'line': issues[0][0],
                'snippet': lines[issues[0][0]-1].strip()[:120] if issues[0][0]-1 < len(lines) else '',
                'fix': '使用raise NewException("msg") from e保留原始异常链',
            })
    
    return results


def check_missing_atexit_cleanup(context) -> List[Dict]:
    """PYAST047 - 检测需要atexit清理但未注册"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        # 检查是否有需要清理的全局资源
        has_global_resources = bool(re.search(
            r'(atexit|signal\.signal|tempfile|NamedTemporaryFile|mkdtemp|mkstemp)',
            content
        ))
        
        # 检测创建了需要清理的资源但无atexit
        has_resource_creation = bool(re.search(
            r'(mkdtemp|mkstemp|TemporaryDirectory|NamedTemporaryFile\(delete=False\)|Popen\()',
            content
        ))
        
        has_atexit = 'atexit' in content
        has_cleanup = bool(re.search(r'(atexit\.register|signal\.signal.*SIGTERM|signal\.signal.*SIGINT|try:|finally:)', content))
        
        if has_resource_creation and not has_atexit and not has_cleanup:
            results.append({
                'id': 'PYAST047',
                'name': '资源管理-缺少退出清理',
                'level': 'info',
                'message': '创建了临时资源但未注册atexit清理回调',
                'file': fpath,
                'line': 1,
                'snippet': '临时资源创建无清理回调',
                'fix': '使用atexit.register()注册清理函数，或使用try/finally确保退出时清理',
            })
    
    return results


def check_missing_signal_handling(context) -> List[Dict]:
    """PYAST048 - 检测长时间运行进程未处理SIGTERM/SIGINT"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        # 检测主入口文件特征
        is_main = bool(re.search(r'if\s+__name__\s*==\s*["\']__main__["\']', content))
        has_loop = bool(re.search(r'while\s+True|while\s+1|for\s+.*in\s+itertools\.count', content))
        has_signal = bool(re.search(r'signal\.signal', content))
        
        if is_main and has_loop and not has_signal:
            results.append({
                'id': 'PYAST048',
                'name': '资源管理-未处理系统信号',
                'level': 'info',
                'message': '主入口包含无限循环但未处理SIGTERM/SIGINT信号，无法优雅退出',
                'file': fpath,
                'line': 1,
                'snippet': 'while True循环无信号处理',
                'fix': '注册SIGTERM/SIGINT handler实现优雅退出：signal.signal(signal.SIGTERM, graceful_shutdown)',
            })
    
    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'PYAST041',
        'name': '资源管理-上下文管理器缺失',
        'level': 'warning',
        'category': 'resource',
        'module_id': '6',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测需要with语句的资源操作未使用上下文管理器',
        'check': check_missing_context_manager,
    },
    {
        'id': 'PYAST042',
        'name': '资源管理-临时文件未清理',
        'level': 'warning',
        'category': 'resource',
        'module_id': '6',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测临时文件创建后未清理',
        'check': check_temp_file_cleanup,
    },
    {
        'id': 'PYAST043',
        'name': '资源管理-subprocess无超时',
        'level': 'warning',
        'category': 'resource',
        'module_id': '6',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测subprocess调用未设置timeout',
        'check': check_subprocess_no_timeout,
    },
    {
        'id': 'PYAST044',
        'name': '资源管理-signal handler不安全',
        'level': 'warning',
        'category': 'resource',
        'module_id': '6',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测signal handler中的不安全操作（IO/logging/异常）',
        'check': check_signal_handler_unsafe,
    },
    {
        'id': 'PYAST045',
        'name': '资源管理-logging未配置',
        'level': 'info',
        'category': 'resource',
        'module_id': '6',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测logging调用存在但未配置handler',
        'check': check_logging_no_handler,
    },
    {
        'id': 'PYAST046',
        'name': '资源管理-异常链丢失',
        'level': 'info',
        'category': 'resource',
        'module_id': '6',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测except中raise新异常未使用from保留异常链',
        'check': check_bare_raise_in_except,
    },
    {
        'id': 'PYAST047',
        'name': '资源管理-缺少退出清理',
        'level': 'info',
        'category': 'resource',
        'module_id': '6',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测临时资源创建但未注册atexit清理',
        'check': check_missing_atexit_cleanup,
    },
    {
        'id': 'PYAST048',
        'name': '资源管理-未处理系统信号',
        'level': 'info',
        'category': 'resource',
        'module_id': '6',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测长时间运行进程未处理SIGTERM/SIGINT',
        'check': check_missing_signal_handling,
    },
]
