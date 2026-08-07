"""
补充规则集 (v5.2.0)
包含: 循环体过大、switch/case过多、空循环体、DOM循环操作、
同步XHR、未处理Promise、await循环、eval使用、innerHTML使用、
代码风格(过长行/尾部空格/文件结尾)、异常处理等补充检查
"""

import re
import os
from typing import List, Dict, Any


def check_cc_009_large_loop_body(context) -> List[Dict]:
    """CC-009 循环体过大 (v2: pre-split, limit files)"""
    results = []
    code_files = context.find_files(['.js', '.ts', '.py', '.tsx', '.jsx'])
    if len(code_files) > 500:
        code_files = code_files[:500]
    max_body = 30
    for fpath in code_files:
        fcontent = context.safe_read(fpath)
        if not fcontent:
            continue
        lines_list = fcontent.split('\n')
        issues = []
        for idx, ln in enumerate(lines_list):
            stripped = ln.strip()
            if stripped.startswith(('for ', 'while ', 'for(')):
                body_lines = 0
                for j in range(idx+1, min(idx+200, len(lines_list))):
                    if lines_list[j].strip() in ('}', 'end'):
                        break
                    body_lines += 1
                if body_lines > max_body:
                    issues.append((fpath, idx+1, body_lines))
        if issues:
            detail = '\n'.join([f'{p}:{l} 循环体{c}行' for p, l, c in issues[:5]])
            results.append({
                'id': 'CC-009', 'name': '循环体过大', 'level': 'warning',
                'category': 'complexity', 'module_id': '21', 'applicable_types': [],
                'description': f'循环体超过{max_body}行', 'detail': detail,
                'check': check_cc_009_large_loop_body,
            })
    return results

def check_cc_010_many_cases(context) -> List[Dict]:
    """CC-010 switch/case过多"""
    results = []
    code_files = context.find_files(['.js', '.ts', '.py', '.tsx', '.jsx'])
    max_cases = 10
    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        for m in re.finditer(r'switch\s*\(', content):
            block = content[m.start():m.start()+3000]
            cases = len(re.findall(r'\bcase\b', block))
            if cases > max_cases:
                line_num = content[:m.start()].count('\n') + 1
                results.append({
                    'id': 'CC-010', 'name': 'switch/case过多', 'level': 'warning',
                    'category': 'complexity', 'module_id': '21', 'applicable_types': [],
                    'description': f'switch有{cases}个case分支(>{max_cases})，建议拆分或用Map替代',
                    'check': check_cc_010_many_cases,
                })
                break
    return results


def check_dead_009_empty_loop(context) -> List[Dict]:
    """DEAD-009 空循环体"""
    results = []
    code_files = context.find_files(['.js', '.ts', '.py', '.tsx', '.jsx'])
    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        for m in re.finditer(r'(?:for|while)\s*\([^)]*\)\s*\{\s*\}', content):
            line_num = content[:m.start()].count('\n') + 1
            results.append({
                'id': 'DEAD-009', 'name': '空循环体', 'level': 'warning',
                'category': 'dead_code', 'module_id': '22', 'applicable_types': [],
                'description': '循环体为空，可能是遗漏了实现逻辑',
                'check': check_dead_009_empty_loop,
            })
            break
    return results


def check_perf_001_dom_in_loop(context) -> List[Dict]:
    """PERF-001 DOM操作在循环中"""
    results = []
    code_files = context.find_files(['.js', '.ts', '.tsx', '.jsx'])
    dom_ops = ['getElementById', 'querySelector', 'innerHTML', 'appendChild', 'createElement', 'setAttribute']
    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        for m in re.finditer(r'(?:for|while)\s*\(', content):
            block = content[m.start():m.start()+1000]
            for op in dom_ops:
                if f'document.{op}' in block or f'.{op}(' in block:
                    line_num = content[:m.start()].count('\n') + 1
                    results.append({
                        'id': 'PERF-001', 'name': 'DOM操作在循环中', 'level': 'warning',
                        'category': 'performance', 'module_id': '12', 'applicable_types': [],
                        'description': f'循环中执行document.{op}，应使用DocumentFragment批量操作',
                        'check': check_perf_001_dom_in_loop,
                    })
                    break
            break
    return results


def check_perf_002_sync_xhr(context) -> List[Dict]:
    """PERF-002 同步XHR"""
    results = []
    code_files = context.find_files(['.js', '.ts'])
    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        if re.search(r'XMLHttpRequest.*async\s*:\s*false|\.open\([^,]+,[^,]+,\s*false\)', content):
            results.append({
                'id': 'PERF-002', 'name': '同步XHR', 'level': 'error',
                'category': 'performance', 'module_id': '12', 'applicable_types': [],
                'description': '使用同步XMLHttpRequest会阻塞主线程，应使用异步请求或fetch',
                'check': check_perf_002_sync_xhr,
            })
    return results


def check_async_001_unhandled_promise(context) -> List[Dict]:
    """ASYNC-001 未处理的Promise"""
    results = []
    code_files = context.find_files(['.js', '.ts', '.tsx', '.jsx'])
    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        for m in re.finditer(r'(?:new\s+)?Promise\s*\(', content):
            line = content[m.start():content.find('\n', m.start())]
            if 'await' not in line and '.catch' not in content[m.start():m.start()+500]:
                line_num = content[:m.start()].count('\n') + 1
                if 'return' not in content[max(0,m.start()-50):m.start()]:
                    results.append({
                        'id': 'ASYNC-001', 'name': '未处理的Promise', 'level': 'warning',
                        'category': 'async_handling', 'module_id': '23', 'applicable_types': [],
                        'description': 'Promise未使用await或.catch()处理错误',
                        'check': check_async_001_unhandled_promise,
                    })
                    break
    return results


def check_async_002_await_in_loop(context) -> List[Dict]:
    """ASYNC-002 await在循环中"""
    results = []
    code_files = context.find_files(['.js', '.ts', '.tsx', '.jsx'])
    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        for m in re.finditer(r'(?:for|while)\s*\(', content):
            block = content[m.start():m.start()+2000]
            if re.search(r'\bawait\b', block):
                line_num = content[:m.start()].count('\n') + 1
                results.append({
                    'id': 'ASYNC-002', 'name': 'await在循环中', 'level': 'warning',
                    'category': 'async_handling', 'module_id': '23', 'applicable_types': [],
                    'description': '循环中使用await导致串行等待，可使用Promise.all并行处理',
                    'check': check_async_002_await_in_loop,
                })
                break
    return results


def check_sec_ext_001_eval(context) -> List[Dict]:
    """SEC-EXT-001 eval使用"""
    results = []
    code_files = context.find_files(['.js', '.ts', '.tsx', '.jsx'])
    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        for m in re.finditer(r'\beval\s*\(', content):
            line_num = content[:m.start()].count('\n') + 1
            snippet = content.split('\n')[line_num - 1].strip()
            results.append({
                'file': fpath,
                'line': line_num,
                'message': 'eval()可执行任意代码，存在注入风险',
                'snippet': snippet,
                'level': 'error',
                'fix': '使用JSON.parse或其他安全方式替代eval',
            })
    return results


def check_sec_ext_002_innerhtml(context) -> List[Dict]:
    """SEC-EXT-002 innerHTML使用"""
    results = []
    code_files = context.find_files(['.js', '.ts', '.tsx', '.jsx'])
    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        for m in re.finditer(r'\.innerHTML\s*=', content):
            line_num = content[:m.start()].count('\n') + 1
            snippet = content.split('\n')[line_num - 1].strip()
            results.append({
                'file': fpath,
                'line': line_num,
                'message': 'innerHTML赋值未转义可能导致XSS',
                'snippet': snippet,
                'level': 'warning',
                'fix': '使用textContent或DOMPurify转义后再赋值',
            })
    return results


def check_style_001_long_line(context) -> List[Dict]:
    """STYLE-001 过长行"""
    results = []
    code_files = context.find_files(['.js', '.ts', '.py', '.tsx', '.jsx'])
    max_len = 120
    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        long_lines = [(i+1, len(line)) for i, line in enumerate(content.split('\n')) if len(line) > max_len]
        if long_lines:
            results.append({
                'id': 'STYLE-001', 'name': '过长行', 'level': 'info',
                'category': 'code_style', 'module_id': '36', 'applicable_types': [],
                'description': f'有{len(long_lines)}行超过{max_len}字符',
                'check': check_style_001_long_line,
            })
    return results


def check_style_002_trailing_space(context) -> List[Dict]:
    """STYLE-002 尾部空格"""
    results = []
    code_files = context.find_files(['.js', '.ts', '.py'])
    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        trailing = sum(1 for line in content.split('\n') if line != line.rstrip())
        if trailing > 5:
            results.append({
                'id': 'STYLE-002', 'name': '尾部空格', 'level': 'info',
                'category': 'code_style', 'module_id': '36', 'applicable_types': [],
                'description': f'有{trailing}行包含尾部空格',
                'check': check_style_002_trailing_space,
            })
    return results


def check_style_003_no_newline_eof(context) -> List[Dict]:
    """STYLE-003 文件结尾无换行"""
    results = []
    code_files = context.find_files(['.js', '.ts', '.py', '.java', '.go'])
    for fpath in code_files:
        content = context.safe_read(fpath)
        if content and not content.endswith('\n'):
            results.append({
                'id': 'STYLE-003', 'name': '文件结尾无换行', 'level': 'info',
                'category': 'code_style', 'module_id': '36', 'applicable_types': [],
                'description': '文件末尾缺少换行符',
                'check': check_style_003_no_newline_eof,
            })
            break
    return results


def check_err_001_generic_exception(context) -> List[Dict]:
    """ERR-001 通用异常捕获"""
    results = []
    code_files = context.find_files(['.java', '.cs', '.py'])
    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        if re.search(r'catch\s*\(\s*(Exception|Throwable|Error)\b', content):
            results.append({
                'id': 'ERR-001', 'name': '通用异常捕获', 'level': 'info',
                'category': 'error_handling_ext', 'module_id': '35', 'applicable_types': [],
                'description': 'catch(Exception)不区分异常类型，可能掩盖编程错误',
                'check': check_err_001_generic_exception,
            })
    return results


def check_err_002_swallowed_exception(context) -> List[Dict]:
    """ERR-002 吞掉异常"""
    results = []
    code_files = context.find_files(['.js', '.ts', '.java', '.py'])
    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        for m in re.finditer(r'catch\s*(?:\([^)]*\))?\s*\{([^}]*)\}', content):
            body = m.group(1).strip()
            if not body or body == '// ignore' or body == '// TODO':
                results.append({
                    'id': 'ERR-002', 'name': '吞掉异常', 'level': 'warning',
                    'category': 'error_handling_ext', 'module_id': '35', 'applicable_types': [],
                    'description': 'catch块为空或仅包含注释，异常被完全忽略',
                    'check': check_err_002_swallowed_exception,
                })
                break
    return results


RULES = [
    {
        'id': 'CC-009', 'name': '循环体过大', 'level': 'warning',
        'category': 'complexity', 'module_id': '21', 'applicable_types': [],
        'description': '循环体超过30行，建议提取为独立函数',
        'check': check_cc_009_large_loop_body,
    },
    {
        'id': 'CC-010', 'name': 'switch/case过多', 'level': 'warning',
        'category': 'complexity', 'module_id': '21', 'applicable_types': [],
        'description': 'switch有超过10个case分支，建议用Map/策略模式替代',
        'check': check_cc_010_many_cases,
    },
    {
        'id': 'DEAD-009', 'name': '空循环体', 'level': 'warning',
        'category': 'dead_code', 'module_id': '22', 'applicable_types': [],
        'description': '循环体为空，可能是遗漏了实现逻辑',
        'check': check_dead_009_empty_loop,
    },
    {
        'id': 'PERF-001', 'name': 'DOM操作在循环中', 'level': 'warning',
        'category': 'performance', 'module_id': '12', 'applicable_types': [],
        'description': '循环中执行DOM操作，应使用DocumentFragment批量操作',
        'check': check_perf_001_dom_in_loop,
    },
    {
        'id': 'PERF-002', 'name': '同步XHR', 'level': 'error',
        'category': 'performance', 'module_id': '12', 'applicable_types': [],
        'description': '使用同步XMLHttpRequest会阻塞主线程',
        'check': check_perf_002_sync_xhr,
    },
    {
        'id': 'ASYNC-001-py', 'name': '未处理的Promise', 'level': 'warning',
        'category': 'async_handling', 'module_id': '23', 'applicable_types': [],
        'description': 'Promise未使用await或.catch()处理错误',
        'check': check_async_001_unhandled_promise,
    },
    {
        'id': 'ASYNC-002-py', 'name': 'await在循环中', 'level': 'warning',
        'category': 'async_handling', 'module_id': '23', 'applicable_types': [],
        'description': '循环中使用await导致串行等待',
        'check': check_async_002_await_in_loop,
    },
    {
        'id': 'SEC-EXT-001', 'name': 'eval使用', 'level': 'error',
        'category': 'security_extension', 'module_id': '3', 'applicable_types': [],
        'description': 'eval()可执行任意代码，存在注入风险',
        'check': check_sec_ext_001_eval,
    },
    {
        'id': 'SEC-EXT-002', 'name': 'innerHTML使用', 'level': 'warning',
        'category': 'security_extension', 'module_id': '3', 'applicable_types': [],
        'description': 'innerHTML赋值未转义可能导致XSS',
        'check': check_sec_ext_002_innerhtml,
    },
    {
        'id': 'STYLE-001', 'name': '过长行', 'level': 'info',
        'category': 'code_style', 'module_id': '36', 'applicable_types': [],
        'description': '代码行超过120字符',
        'check': check_style_001_long_line,
    },
    {
        'id': 'STYLE-002', 'name': '尾部空格', 'level': 'info',
        'category': 'code_style', 'module_id': '36', 'applicable_types': [],
        'description': '代码行包含尾部空格',
        'check': check_style_002_trailing_space,
    },
    {
        'id': 'STYLE-003', 'name': '文件结尾无换行', 'level': 'info',
        'category': 'code_style', 'module_id': '36', 'applicable_types': [],
        'description': '文件末尾缺少换行符',
        'check': check_style_003_no_newline_eof,
    },
    {
        'id': 'ERR-001', 'name': '通用异常捕获', 'level': 'info',
        'category': 'error_handling_ext', 'module_id': '35', 'applicable_types': [],
        'description': 'catch(Exception)不区分异常类型',
        'check': check_err_001_generic_exception,
    },
    {
        'id': 'ERR-002', 'name': '吞掉异常', 'level': 'warning',
        'category': 'error_handling_ext', 'module_id': '35', 'applicable_types': [],
        'description': 'catch块仅console.log不抛出异常',
        'check': check_err_002_swallowed_exception,
    },
]
