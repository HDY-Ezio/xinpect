"""
Python后端规则集
Python后端专项检查
包含: 代码规范、安全、性能、架构等检查
"""

import re
import os
import ast
from typing import List, Dict, Any


# ===== PY-001 Python代码规范检查 =====
def check_py_001_code_style(context) -> List[Dict]:
    """PY-001 Python代码规范检查 - 检查PEP8规范基础项"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    issues = []
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        lines = content.split('\n')
        file_issues = 0
        
        # 检查行长度
        for i, line in enumerate(lines):
            if len(line) > 120:  # 放宽到120字符
                file_issues += 1
                if file_issues <= 3:
                    issues.append(f'{os.path.basename(fpath)}:{i+1} 行过长({len(line)}字符)')
                break  # 每个文件只统计一次
        
        # 检查是否有print语句（生产代码建议用logging）
        print_count = len(re.findall(r'\bprint\s*\(', content))
        if print_count > 5:
            issues.append(f'{os.path.basename(fpath)}: {print_count}个print语句')
    
    if len(issues) > 3:
        results.append({
            'id': 'PY-001',
            'name': 'Python代码规范检查',
            'level': 'info',
            'message': f'发现{len(issues)}处代码规范问题',
            'detail': '示例: ' + '; '.join(issues[:5]),
            'file': '',
            'line': 0,
            'fix': '遵循PEP8规范，使用logging替代print',
        })
    
    return results


# ===== PY-002 异常处理检查 =====
def check_py_002_exception_handling(context) -> List[Dict]:
    """PY-002 异常处理检查 - 检查裸except和异常吞掉问题"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    bare_except_count = 0
    except_pass_count = 0
    files_with_issues = []
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        # 裸except
        bare = len(re.findall(r'except\s*:', content))
        if bare > 0:
            bare_except_count += bare
            files_with_issues.append((fpath, 'bare except'))
        
        # except后直接pass
        except_pass = len(re.findall(r'except[^:]*:\s*\n\s*pass\b', content))
        if except_pass > 0:
            except_pass_count += except_pass
            files_with_issues.append((fpath, 'except pass'))
    
    if bare_except_count > 0 or except_pass_count > 0:
        results.append({
            'id': 'PY-002',
            'name': '异常处理检查',
            'level': 'warning',
            'message': f'发现{bare_except_count}个裸except, {except_pass_count}个异常吞掉',
            'detail': '涉及文件: ' + ', '.join(os.path.basename(f) for f, _ in files_with_issues[:5]),
            'file': '',
            'line': 0,
            'fix': '捕获具体的异常类型，记录错误日志，不要用空except和except: pass',
        })
    
    return results


# ===== PY-003 导入规范检查 =====
def check_py_003_import_style(context) -> List[Dict]:
    """PY-003 导入规范检查 - 检查导入顺序和通配符导入"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    wildcard_imports = []
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        # 通配符导入
        wildcards = re.findall(r'from\s+[\w.]+\s+import\s+\*', content)
        if wildcards:
            wildcard_imports.append((fpath, len(wildcards)))
    
    if wildcard_imports:
        results.append({
            'id': 'PY-003',
            'name': '导入规范检查',
            'level': 'warning',
            'message': f'发现{len(wildcard_imports)}个文件使用通配符导入',
            'detail': '文件: ' + ', '.join(os.path.basename(f) for f, _ in wildcard_imports[:5]),
            'file': '',
            'line': 0,
            'fix': '明确导入需要的名称，避免使用from xxx import *',
        })
    
    return results


# ===== PY-004 类型提示检查 =====
def check_py_004_type_hints(context) -> List[Dict]:
    """PY-004 类型提示检查 - 检查函数是否有类型注解"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    total_funcs = 0
    hinted_funcs = 0
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        # 统计函数定义
        func_defs = re.findall(r'def\s+\w+\s*\([^)]*\)\s*->', content)
        all_defs = re.findall(r'def\s+\w+\s*\(', content)
        
        total_funcs += len(all_defs)
        hinted_funcs += len(func_defs)
    
    if total_funcs > 10 and hinted_funcs / total_funcs < 0.3:
        results.append({
            'id': 'PY-004',
            'name': '类型提示检查',
            'level': 'info',
            'message': f'类型提示覆盖率较低: {hinted_funcs}/{total_funcs} ({hinted_funcs/total_funcs:.0%})',
            'file': '',
            'line': 0,
            'fix': '为函数添加类型注解，提高代码可读性和IDE支持',
        })
    
    return results


# ===== PY-005 循环复杂度检查 =====
def check_py_005_complexity(context) -> List[Dict]:
    """PY-005 循环复杂度检查 - 检查复杂度过高的函数"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    complex_funcs = []
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        lines = content.split('\n')
        max_complexity = context.project_profile.get_adjusted_threshold('cyclomatic_complexity', 15)
        
        # 简化版：统计函数中的if/for/while/try/and/or数量
        try:
            _sum = context.get_ast_summary(fpath)
            if not _sum:
                continue
            for _f_info in _sum.get('functions', []):
                node = _f_info['node']
                if True:
                    # 简单计算复杂度
                    complexity = 1
                    for child in ast.walk(node):
                        if isinstance(child, (ast.If, ast.For, ast.While, ast.Try, 
                                            ast.And, ast.Or, ast.ExceptHandler)):
                            complexity += 1
                    
                    if complexity > max_complexity:
                        complex_funcs.append((fpath, node.name, complexity))
        except SyntaxError:  # noqa: intentional empty handler
            pass
    
    if complex_funcs:
        worst = sorted(complex_funcs, key=lambda x: x[2], reverse=True)[:10]
        results.append({
            'id': 'PY-005',
            'name': '循环复杂度检查',
            'level': 'warning',
            'message': f'发现{len(complex_funcs)}个高复杂度函数(>{max_complexity})',
            'detail': '最高复杂度: ' + ', '.join(f'{n}({c})' for _, n, c in worst[:5]),
            'file': complex_funcs[0][0] if complex_funcs else '',
            'line': 0,
            'fix': '拆分复杂函数，降低圈复杂度',
        })
    
    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'PY-001',
        'name': 'Python代码规范检查',
        'level': 'suggestion',
        'category': 'code_quality',
        'module_id': '6',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检查PEP8规范基础项',
        'check': check_py_001_code_style,
    },
    {
        'id': 'PY-002',
        'name': '异常处理检查',
        'level': 'problem',
        'category': 'error_handling',
        'module_id': '13',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检查裸except和异常吞掉问题',
        'check': check_py_002_exception_handling,
    },
    {
        'id': 'PY-003',
        'name': '导入规范检查',
        'level': 'suggestion',
        'category': 'code_quality',
        'module_id': '6',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检查导入顺序和通配符导入',
        'check': check_py_003_import_style,
    },
    {
        'id': 'PY-004',
        'name': '类型提示检查',
        'level': 'suggestion',
        'category': 'code_quality',
        'module_id': '6',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检查函数类型注解覆盖率',
        'check': check_py_004_type_hints,
    },
    {
        'id': 'PY-005',
        'name': '循环复杂度检查',
        'level': 'problem',
        'category': 'code_quality',
        'module_id': '9',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检查复杂度过高的函数',
        'check': check_py_005_complexity,
    },
]
