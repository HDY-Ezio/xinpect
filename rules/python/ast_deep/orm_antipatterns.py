# -*- coding: utf-8 -*-
"""
ORM反模式AST深度分析规则集
检测N+1查询、未使用索引字段、事务内非DB操作等
规则ID: PYAST017 - PYAST024
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


def _is_db_query_call(node: ast.Call) -> bool:
    """判断AST Call节点是否是数据库查询调用"""
    db_methods = {
        'filter', 'get', 'all', 'first', 'last', 'count', 'exists',
        'values', 'values_list', 'annotate', 'aggregate', 'order_by',
        'select_related', 'prefetch_related', 'distinct', 'raw',
        'create', 'update', 'delete', 'bulk_create', 'bulk_update',
        'save', 'objects', 'query', 'execute',
    }
    if isinstance(node.func, ast.Attribute):
        return node.func.attr in db_methods
    return False


def _find_loop_bodies(tree: ast.Module) -> List[Tuple[ast.AST, List[ast.AST]]]:
    """查找所有循环及其body内的语句"""
    loops = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.For, ast.While, ast.AsyncFor)):
            body_nodes = []
            for item in node.body:
                body_nodes.append(item)
                for sub in ast.walk(item):
                    body_nodes.append(sub)
            loops.append((node, body_nodes))
    return loops


def check_n_plus_one_query(context) -> List[Dict]:
    """PYAST017 - 检测循环内执行数据库查询（N+1问题）"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        # 快速检查是否是ORM项目
        if not re.search(r'(objects\.|query\.|session\.|\.filter\(|\.get\(|Model|QuerySet|select_related|prefetch_related)', content):
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        lines = content.split('\n')
        issues = []
        
        loops = _find_loop_bodies(tree)
        
        for loop_node, body_nodes in loops:
            query_count = 0
            query_lines = []
            for node in body_nodes:
                if isinstance(node, ast.Call) and _is_db_query_call(node):
                    # 排除明显非查询的方法
                    if isinstance(node.func, ast.Attribute):
                        method = node.func.attr
                        if method in ('filter', 'get', 'all', 'first', 'values', 'values_list', 'execute', 'query'):
                            query_count += 1
                            query_lines.append(node.lineno)
            
            if query_count >= 1:
                issues.append({
                    'loop_line': loop_node.lineno,
                    'query_lines': query_lines,
                    'count': query_count,
                })
        
        if issues:
            first = issues[0]
            results.append({
                'id': 'PYAST017',
                'name': 'ORM反模式-N+1查询',
                'level': 'warning',
                'message': f'检测到{len(issues)}处循环内执行数据库查询(N+1问题)，共{sum(i["count"] for i in issues)}次查询',
                'file': fpath,
                'line': first['loop_line'],
                'snippet': lines[first['loop_line']-1].strip()[:120] if first['loop_line']-1 < len(lines) else '',
                'fix': '使用select_related/prefetch_related预加载关联数据，或将查询移到循环外批量执行',
            })
    
    return results


def check_missing_prefetch(context) -> List[Dict]:
    """PYAST018 - 检测未使用select_related/prefetch_related的外键访问"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        if not re.search(r'(objects\.(filter|all|get)|\.select_related|\.prefetch_related)', content):
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        lines = content.split('\n')
        
        # 查找queryset但没有链式调用select_related/prefetch_related
        has_prefetch = 'select_related' in content or 'prefetch_related' in content
        
        # 查找 .属性.属性 的模式（外键访问）
        fk_access = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                # obj.field.field 模式
                if isinstance(node.value, ast.Attribute):
                    if isinstance(node.value.value, ast.Name):
                        # 可能是 obj.relation.field，检查是否在filter/get结果上
                        pass
        
        # 正则兜底：查找 for item in queryset: item.relation.field 模式
        for_patterns = [
            r'for\s+\w+\s+in\s+\w+\.objects\.\w+\(.*?\)',
            r'for\s+\w+\s+in\s+\w+\.objects\.all\s*\(\s*\)',
            r'for\s+\w+\s+in\s+\w+\.objects\.filter\s*\(',
        ]
        
        for pattern in for_patterns:
            for m in re.finditer(pattern, content):
                line_num = content[:m.start()].count('\n') + 1
                # 检查接下来的行是否有 .xxx.yyy 访问（外键字段访问）
                ctx = '\n'.join(lines[line_num:min(line_num + 15, len(lines))])
                # 匹配 obj.field.field 模式
                if re.search(r'\w+\.\w+\.\w+\s*[\.\(\=]', ctx):
                    # 检查该queryset是否有prefetch
                    pre_ctx = '\n'.join(lines[max(0, line_num-5):line_num])
                    if not re.search(r'select_related|prefetch_related', pre_ctx):
                        if not has_prefetch:
                            fk_access.append(line_num)
        
        if fk_access:
            results.append({
                'id': 'PYAST018',
                'name': 'ORM反模式-缺少预加载',
                'level': 'info',
                'message': f'检测到{len(fk_access)}处循环中可能未使用select_related/prefetch_related加载外键',
                'file': fpath,
                'line': fk_access[0],
                'snippet': lines[fk_access[0]-1].strip()[:120] if fk_access[0]-1 < len(lines) else '',
                'fix': '使用select_related()加载外键关系，prefetch_related()加载多对多关系',
            })
    
    return results


def check_unindexed_field(context) -> List[Dict]:
    """PYAST019 - 检测.filter()中可能未建索引的字段"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    # 常见未索引字段模式
    unindexed_patterns = [
        (r'\.filter\s*\([^)]*(?:__icontains|__contains|__startswith|__endswith|__iexact)\s*=', 
         'LIKE查询字段可能未建索引'),
        (r'\.filter\s*\([^)]*(?:__regex|__iregex)\s*=', 
         '正则查询字段无法使用索引'),
        (r'\.filter\s*\([^)]*(?:__isnull)\s*=\s*False', 
         'IS NOT NULL查询在部分DB中不使用索引'),
    ]
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        if '.filter(' not in content:
            continue
        
        lines = content.split('\n')
        issues = []
        
        for pattern, desc in unindexed_patterns:
            for m in re.finditer(pattern, content):
                line_num = content[:m.start()].count('\n') + 1
                line_text = lines[line_num - 1] if line_num - 1 < len(lines) else ""
                if line_text.strip().startswith('#'):
                    continue
                issues.append((line_num, desc, line_text.strip()[:120]))
        
        if issues:
            results.append({
                'id': 'PYAST019',
                'name': 'ORM反模式-未索引字段',
                'level': 'info',
                'message': f'检测到{len(issues)}处filter使用可能未建索引的字段查询方式',
                'file': fpath,
                'line': issues[0][0],
                'snippet': issues[0][2],
                'fix': '为高频查询字段添加db_index=True；LIKE查询考虑全文索引',
            })
    
    return results


def check_values_vs_values_list(context) -> List[Dict]:
    """PYAST020 - 检测.values()与.values_list()的误用"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        if '.values(' not in content and '.values_list(' not in content:
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        lines = content.split('\n')
        issues = []
        
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            
            # .values() 只传了1个字段，建议用 .values_list()
            if node.func.attr == 'values' and len(node.args) == 1:
                # 检查是否赋值给了单变量解构
                for parent in ast.walk(tree):
                    if isinstance(parent, ast.Assign):
                        if isinstance(parent.value, ast.Call) and parent.value is node:
                            if isinstance(parent.targets[0], ast.Name):
                                issues.append((
                                    node.lineno,
                                    '单字段.values()返回字典列表，建议使用.values_list(flat=True)减少内存开销',
                                ))
            
            # .values_list() 传了多个字段但未解构
            if node.func.attr == 'values_list' and len(node.args) > 1:
                # 检查是否用了named=True
                has_named = any(kw.arg == 'named' for kw in node.keywords)
                if not has_named:
                    # 检查是否后续有解构
                    pass  # 这种情况太复杂，跳过减少误报
        
        if issues:
            results.append({
                'id': 'PYAST020',
                'name': 'ORM反模式-values误用',
                'level': 'info',
                'message': f'检测到{len(issues)}处.values()可能应替换为.values_list()',
                'file': fpath,
                'line': issues[0][0],
                'snippet': lines[issues[0][0]-1].strip()[:120] if issues[0][0]-1 < len(lines) else '',
                'fix': '查询单字段时使用.values_list(field, flat=True)返回扁平列表',
            })
    
    return results


def check_bulk_save_missing(context) -> List[Dict]:
    """PYAST021 - 检测循环内.save()未使用bulk_create/bulk_update"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        if '.save(' not in content:
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        lines = content.split('\n')
        issues = []
        
        loops = _find_loop_bodies(tree)
        
        for loop_node, body_nodes in loops:
            save_count = 0
            save_lines = []
            for node in body_nodes:
                if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                    if isinstance(node.value.func, ast.Attribute) and node.value.func.attr == 'save':
                        save_count += 1
                        save_lines.append(node.lineno)
            
            if save_count >= 1:
                issues.append({
                    'loop_line': loop_node.lineno,
                    'save_count': save_count,
                    'save_lines': save_lines,
                })
        
        if issues:
            first = issues[0]
            results.append({
                'id': 'PYAST021',
                'name': 'ORM反模式-批量操作',
                'level': 'warning',
                'message': f'检测到{len(issues)}处循环内执行.save()，应使用bulk_create/bulk_update',
                'file': fpath,
                'line': first['loop_line'],
                'snippet': lines[first['loop_line']-1].strip()[:120] if first['loop_line']-1 < len(lines) else '',
                'fix': '使用bulk_create()批量创建或bulk_update()批量更新，减少数据库往返',
            })
    
    return results


def check_transaction_non_db_ops(context) -> List[Dict]:
    """PYAST022 - 检测事务内执行非数据库操作"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        # 检查是否有事务相关代码
        if not re.search(r'(transaction\.atomic|with\s+transaction|begin\(\)|commit\(\))', content):
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        lines = content.split('\n')
        issues = []
        
        # 非DB操作模式
        non_db_calls = {
            'get': 'HTTP请求', 'post': 'HTTP请求', 'put': 'HTTP请求', 'delete': 'HTTP请求',
            'send': '网络请求', 'request': 'HTTP请求',
            'open': '文件IO', 'read': '文件IO', 'write': '文件IO',
            'sleep': '阻塞等待',
            'print': '控制台输出',
            'sendmail': '邮件发送', 'send_email': '邮件发送',
        }
        
        # 查找transaction.within/atomic块内的非DB操作
        for node in ast.walk(tree):
            if isinstance(node, ast.With):
                # 检查with transaction.atomic():
                is_transaction = False
                for item in node.items:
                    if isinstance(item.context_expr, ast.Call):
                        if isinstance(item.context_expr.func, ast.Attribute):
                            if item.context_expr.func.attr in ('atomic', 'transaction'):
                                is_transaction = True
                        elif isinstance(item.context_expr.func, ast.Name):
                            if 'transaction' in item.context_expr.func.id:
                                is_transaction = True
                
                if not is_transaction:
                    continue
                
                # 检查事务块内的操作
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call):
                        call_name = ''
                        if isinstance(sub.func, ast.Name):
                            call_name = sub.func.id
                        elif isinstance(sub.func, ast.Attribute):
                            call_name = sub.func.attr
                        
                        if call_name in non_db_calls:
                            issues.append((
                                sub.lineno,
                                f'事务内调用{non_db_calls[call_name]}({call_name})',
                            ))
                    
                    # HTTP请求调用
                    if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
                        if sub.func.attr in ('requests', 'httpx', 'urlopen'):
                            issues.append((sub.lineno, '事务内发起HTTP请求'))
        
        if issues:
            results.append({
                'id': 'PYAST022',
                'name': 'ORM反模式-事务内非DB操作',
                'level': 'warning',
                'message': f'检测到{len(issues)}处事务内执行非数据库操作，增加事务持锁时间',
                'file': fpath,
                'line': issues[0][0],
                'snippet': lines[issues[0][0]-1].strip()[:120] if issues[0][0]-1 < len(lines) else '',
                'fix': '将HTTP请求、文件IO等非DB操作移到事务之外，缩短事务持锁时间',
            })
    
    return results


def check_query_without_limit(context) -> List[Dict]:
    """PYAST023 - 检测无限制的查询（.all()/.filter()无[:limit]截断）"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        if not re.search(r'\.objects\.(all|filter)\s*\(', content):
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        lines = content.split('\n')
        issues = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in ('all', 'filter'):
                    # 检查是否在循环中使用且无limit
                    # 向上查找是否链式调用了[:N]或.count()
                    ctx_start = max(0, node.lineno - 3)
                    ctx_end = min(len(lines), node.lineno + 3)
                    ctx = '\n'.join(lines[ctx_start:ctx_end])
                    
                    # 如果.all()的结果直接赋值且没有limit/count/exist判断
                    if not re.search(r'\[:\d+\]|\[:\s*\w+\]|\.count\(\)|\.exists\(\)|\.first\(\)|\.get\(', ctx):
                        # 检查是否在for循环中
                        for parent in ast.walk(tree):
                            if isinstance(parent, (ast.For, ast.While)):
                                for sub in ast.walk(parent):
                                    if sub is node:
                                        issues.append(node.lineno)
                                        break
        
        if issues:
            results.append({
                'id': 'PYAST023',
                'name': 'ORM反模式-无限制查询',
                'level': 'info',
                'message': f'检测到{len(issues)}处循环中使用.all()/filter()无数量限制',
                'file': fpath,
                'line': issues[0],
                'snippet': lines[issues[0]-1].strip()[:120] if issues[0]-1 < len(lines) else '',
                'fix': '对查询结果添加数量限制[:limit]或使用.iterator()流式处理大数据集',
            })
    
    return results


def check_raw_sql_in_orm(context) -> List[Dict]:
    """PYAST024 - 检测ORM项目中不必要的raw SQL使用"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        # 确认是ORM项目
        if not re.search(r'(objects\.|Model|QuerySet|session\.query|Base\.metadata)', content):
            continue
        
        # 统计raw SQL使用次数
        raw_count = len(re.findall(r'(?:\.raw\s*\(|RawSQL\s*\(|text\s*\(|execute\s*\(\s*["\'])', content))
        orm_count = len(re.findall(r'\.objects\.(filter|get|all|create|update|delete)', content))
        
        if raw_count > 5 and orm_count > 10 and raw_count / (orm_count + raw_count) > 0.3:
            results.append({
                'id': 'PYAST024',
                'name': 'ORM反模式-过度使用Raw SQL',
                'level': 'info',
                'message': f'ORM项目中Raw SQL占比过高({raw_count}次raw/{orm_count}次ORM)，建议优先使用ORM API',
                'file': fpath,
                'line': 1,
                'snippet': f'Raw SQL: {raw_count}次, ORM查询: {orm_count}次',
                'fix': '优先使用ORM的filter/annotate/aggregate等API，仅在ORM无法满足时使用Raw SQL',
            })
    
    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'PYAST017',
        'name': 'ORM反模式-N+1查询',
        'level': 'warning',
        'category': 'orm',
        'module_id': '4',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测循环内执行数据库查询导致的N+1问题',
        'check': check_n_plus_one_query,
    },
    {
        'id': 'PYAST018',
        'name': 'ORM反模式-缺少预加载',
        'level': 'info',
        'category': 'orm',
        'module_id': '4',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测未使用select_related/prefetch_related的外键访问',
        'check': check_missing_prefetch,
    },
    {
        'id': 'PYAST019',
        'name': 'ORM反模式-未索引字段',
        'level': 'info',
        'category': 'orm',
        'module_id': '4',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测.filter()中使用LIKE/正则等可能未建索引的查询方式',
        'check': check_unindexed_field,
    },
    {
        'id': 'PYAST020',
        'name': 'ORM反模式-values误用',
        'level': 'info',
        'category': 'orm',
        'module_id': '4',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测.values()与.values_list()的误用场景',
        'check': check_values_vs_values_list,
    },
    {
        'id': 'PYAST021',
        'name': 'ORM反模式-批量操作',
        'level': 'warning',
        'category': 'orm',
        'module_id': '4',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测循环内.save()未使用bulk_create/bulk_update',
        'check': check_bulk_save_missing,
    },
    {
        'id': 'PYAST022',
        'name': 'ORM反模式-事务内非DB操作',
        'level': 'warning',
        'category': 'orm',
        'module_id': '4',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测事务内执行HTTP请求、文件IO等非数据库操作',
        'check': check_transaction_non_db_ops,
    },
    {
        'id': 'PYAST023',
        'name': 'ORM反模式-无限制查询',
        'level': 'info',
        'category': 'orm',
        'module_id': '4',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测循环中使用.all()/filter()无数量限制',
        'check': check_query_without_limit,
    },
    {
        'id': 'PYAST024',
        'name': 'ORM反模式-过度使用Raw SQL',
        'level': 'info',
        'category': 'orm',
        'module_id': '4',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测ORM项目中Raw SQL使用比例过高',
        'check': check_raw_sql_in_orm,
    },
]
