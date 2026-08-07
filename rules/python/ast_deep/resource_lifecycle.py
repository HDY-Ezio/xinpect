# -*- coding: utf-8 -*-
"""
资源生命周期AST深度分析规则集
检测资源未正确关闭、数据库连接未归还、网络请求缺少timeout等
规则ID: PYAST049 - PYAST051

归脑: module_id = '4'（Brain 4 性能）
"""

import ast
import re
from typing import List, Dict, Any, Optional


def _parse_ast_safe(filepath: str, content: str) -> Optional[ast.Module]:
    """安全解析AST，语法错误返回None"""
    try:
        return ast.parse(content, filename=filepath)
    except SyntaxError:
        return None


def _find_ast_call_info(node: ast.Call) -> Optional[str]:
    """从 Call 节点提取被调用函数名"""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _find_with_ranges(tree: ast.Module) -> list:
    """收集所有 with 块的行号范围 [(start_line, end_line), ...]"""
    ranges = []
    for node in ast.walk(tree):
        if isinstance(node, ast.With):
            start = node.lineno
            end = node.end_lineno if hasattr(node, 'end_lineno') and node.end_lineno else start + 10
            ranges.append((start, end))
    return ranges


def _is_inside_with(line_no: int, with_ranges: list) -> bool:
    """检查某行是否在 with 块内"""
    for start, end in with_ranges:
        if start <= line_no <= end:
            return True
    return False


# ============================================================
# RES-001 / PYAST049: open() / urlopen() / connect() 不在 with 块中
# ============================================================

_RESOURCE_OPEN_FUNCS = {'open', 'urlopen', 'connect'}

_ASSIGN_OPEN_PATTERN = re.compile(
    r'^\s*(\w+)\s*=\s*(?:[\w.]*\.)?(open|urlopen|connect)\s*\(',
    re.MULTILINE,
)


def check_resource_open_not_in_with(context) -> List[Dict]:
    """RES-001: 检测 open()/urlopen()/connect() 不在 with 块中"""
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

        content_lines = content.split('\n')
        with_ranges = _find_with_ranges(tree)
        seen_lines = set()

        # AST方式：遍历所有 Call 节点
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func_name = _find_ast_call_info(node)
            if func_name not in _RESOURCE_OPEN_FUNCS:
                continue

            line_no = node.lineno
            if line_no in seen_lines:
                continue
            if _is_inside_with(line_no, with_ranges):
                continue

            line_text = content_lines[line_no - 1] if line_no - 1 < len(content_lines) else ""
            if line_text.strip().startswith('#'):
                continue

            seen_lines.add(line_no)
            results.append({
                'id': 'PYAST049',
                'name': '资源生命周期-文件/网络资源未用with管理',
                'level': 'error',
                'message': f'{func_name}() 返回值未使用 with 语句管理，可能导致资源泄漏',
                'file': fpath,
                'line': line_no,
                'snippet': line_text.strip()[:120],
                'fix': f'使用 with 语句: with {func_name}(...) as f: ...',
            })

        # 正则兜底：检测赋值模式
        for m in _ASSIGN_OPEN_PATTERN.finditer(content):
            line_no = content[:m.start()].count('\n') + 1
            if line_no in seen_lines:
                continue
            if _is_inside_with(line_no, with_ranges):
                continue
            line_text = content_lines[line_no - 1] if line_no - 1 < len(content_lines) else ""
            if line_text.strip().startswith('#'):
                continue

            seen_lines.add(line_no)
            func_name = m.group(2)
            results.append({
                'id': 'PYAST049',
                'name': '资源生命周期-文件/网络资源未用with管理',
                'level': 'error',
                'message': f'{func_name}() 赋值给变量但未使用 with 语句管理',
                'file': fpath,
                'line': line_no,
                'snippet': line_text.strip()[:120],
                'fix': f'使用 with 语句: with {func_name}(...) as f: ...',
            })

    return results


# ============================================================
# RES-002 / PYAST050: 数据库连接不在 finally 中归还/关闭
# ============================================================

_DB_CONNECT_PATTERN = re.compile(
    r'(?:(\w+)\s*=\s*)?'
    r'(?:pymysql|mysql\.connector|sqlite3|psycopg2|cx_Oracle|pyodbc|mongo|MongoClient|redis|Redis|ConnectionPool)\.'
    r'(?:connect|Connection)\s*\(',
    re.MULTILINE,
)


def _find_try_finally_ranges(tree: ast.Module) -> list:
    """收集所有 try...finally 块的行号范围"""
    ranges = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            if node.finalbody:
                try_end = node.end_lineno if hasattr(node, 'end_lineno') and node.end_lineno else node.finalbody[-1].lineno + 10
                ranges.append((node.lineno, try_end))
    return ranges


def check_db_connection_not_closed(context) -> List[Dict]:
    """RES-002: 检测数据库连接未在 finally 中关闭/归还"""
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

        content_lines = content.split('\n')
        try_ranges = _find_try_finally_ranges(tree)

        connect_matches = list(_DB_CONNECT_PATTERN.finditer(content))
        if not connect_matches:
            continue

        for cm in connect_matches:
            line_no = content[:cm.start()].count('\n') + 1
            line_text = content_lines[line_no - 1] if line_no - 1 < len(content_lines) else ""
            if line_text.strip().startswith('#'):
                continue

            var_name = cm.group(1)
            if not var_name:
                in_try = any(s <= line_no <= e for s, e in try_ranges)
                if not in_try:
                    results.append({
                        'id': 'PYAST050',
                        'name': '资源生命周期-数据库连接未关闭',
                        'level': 'error',
                        'message': '数据库连接创建后未在 finally 中关闭，可能导致连接池耗尽',
                        'file': fpath,
                        'line': line_no,
                        'snippet': line_text.strip()[:120],
                        'fix': '使用 try/finally 确保连接关闭，或使用 with 上下文管理器',
                    })
                continue

            # 检查变量是否有对应的 close/disconnect 调用
            close_pattern = re.compile(
                rf'\b{re.escape(var_name)}\s*\.\s*(?:close|disconnect|return_conn|release)\s*\(',
            )
            has_close = close_pattern.search(content)

            if has_close:
                close_line = content[:has_close.start()].count('\n') + 1
                in_try = any(s <= close_line <= e for s, e in try_ranges)
                if not in_try:
                    results.append({
                        'id': 'PYAST050',
                        'name': '资源生命周期-数据库连接未在finally中关闭',
                        'level': 'warning',
                        'message': f'变量 {var_name} 的 close() 调用不在 try/finally 块中，异常时可能跳过关闭',
                        'file': fpath,
                        'line': line_no,
                        'snippet': line_text.strip()[:120],
                        'fix': f'将 {var_name}.close() 移到 finally 块中确保异常时也能关闭',
                    })
            else:
                results.append({
                    'id': 'PYAST050',
                    'name': '资源生命周期-数据库连接未关闭',
                    'level': 'error',
                    'message': f'数据库连接（变量 {var_name}）创建后未调用 close()/disconnect()，可能导致连接泄漏',
                    'file': fpath,
                    'line': line_no,
                    'snippet': line_text.strip()[:120],
                    'fix': '使用 try/finally 确保连接关闭，或使用 with 上下文管理器',
                })

    return results


# ============================================================
# RES-003 / PYAST051: 网络连接没有设置 timeout
# ============================================================

_NET_CALL_PATTERN = re.compile(
    r'(?:urlopen|requests\.(?:get|post|put|delete|patch|head|options|request)'
    r'|http\.client\.\w+|aiohttp\.\w+|urllib\.request\.urlopen)\s*\(',
    re.MULTILINE,
)

_TIMEOUT_KW_PATTERN = re.compile(r'timeout\s*=')


def check_network_no_timeout(context) -> List[Dict]:
    """RES-003: 检测网络请求未设置 timeout"""
    results = []

    py_files = context.get_backend_py_files()
    if not py_files:
        return results

    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        content_lines = content.split('\n')
        tree = _parse_ast_safe(fpath, content)
        seen_lines = set()

        # AST方式
        if tree is not None:
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue

                is_net_call = False
                func = node.func

                if isinstance(func, ast.Attribute):
                    owner = None
                    if isinstance(func.value, ast.Name):
                        owner = func.value.id
                    if owner == 'requests' and func.attr in (
                        'get', 'post', 'put', 'delete', 'patch', 'head', 'options', 'request'
                    ):
                        is_net_call = True
                    elif owner == 'urllib' and func.attr == 'urlopen':
                        is_net_call = True
                elif isinstance(func, ast.Name):
                    if func.id == 'urlopen':
                        is_net_call = True

                if not is_net_call:
                    continue

                line_no = node.lineno
                if line_no in seen_lines:
                    continue

                has_timeout = any(kw.arg == 'timeout' for kw in node.keywords)
                if has_timeout:
                    continue

                line_text = content_lines[line_no - 1] if line_no - 1 < len(content_lines) else ""
                if line_text.strip().startswith('#'):
                    continue

                seen_lines.add(line_no)
                func_name = func.attr if isinstance(func, ast.Attribute) else func.id
                results.append({
                    'id': 'PYAST051',
                    'name': '资源生命周期-网络请求缺少timeout',
                    'level': 'warning',
                    'message': f'网络请求 {func_name}() 未设置 timeout 参数，可能导致请求永久挂起',
                    'file': fpath,
                    'line': line_no,
                    'snippet': line_text.strip()[:120],
                    'fix': '添加 timeout 参数，例如: timeout=30',
                })

        # 正则兜底
        for m in _NET_CALL_PATTERN.finditer(content):
            line_no = content[:m.start()].count('\n') + 1
            if line_no in seen_lines:
                continue

            line_text = content_lines[line_no - 1] if line_no - 1 < len(content_lines) else ""
            if line_text.strip().startswith('#'):
                continue

            # 检查该行及后续几行是否有 timeout=
            snippet_area = '\n'.join(content_lines[line_no - 1:min(line_no + 4, len(content_lines))])
            if _TIMEOUT_KW_PATTERN.search(snippet_area):
                continue

            seen_lines.add(line_no)
            results.append({
                'id': 'PYAST051',
                'name': '资源生命周期-网络请求缺少timeout',
                'level': 'warning',
                'message': '网络请求未设置 timeout 参数，可能导致请求永久挂起',
                'file': fpath,
                'line': line_no,
                'snippet': line_text.strip()[:120],
                'fix': '添加 timeout 参数，例如: timeout=30',
            })

    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'PYAST049',
        'name': '资源生命周期-文件/网络资源未用with管理',
        'level': 'error',
        'category': 'resource_lifecycle',
        'module_id': '4',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测 open()/urlopen()/connect() 不在 with 块中，可能导致资源泄漏',
        'check': check_resource_open_not_in_with,
    },
    {
        'id': 'PYAST050',
        'name': '资源生命周期-数据库连接未关闭',
        'level': 'error',
        'category': 'resource_lifecycle',
        'module_id': '4',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测数据库连接创建后未在 finally 中关闭/归还，可能导致连接池耗尽',
        'check': check_db_connection_not_closed,
    },
    {
        'id': 'PYAST051',
        'name': '资源生命周期-网络请求缺少timeout',
        'level': 'warning',
        'category': 'resource_lifecycle',
        'module_id': '4',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测网络请求未设置 timeout 参数，可能导致请求永久挂起',
        'check': check_network_no_timeout,
    },
]
