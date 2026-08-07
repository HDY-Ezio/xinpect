# -*- coding: utf-8 -*-
"""
SQL安全AST深度分析规则集
检测SQL注入、参数化查询缺失、ORM原始SQL风险等
规则ID: PYAST001 - PYAST008
"""

import ast
import re
import os
from typing import List, Dict, Any, Optional, Tuple


def _parse_ast_safe(filepath: str, content: str) -> Optional[ast.Module]:
    """安全解析AST，语法错误返回None"""
    try:
        return ast.parse(content, filename=filepath)
    except SyntaxError:
        return None


def _get_string_value(node: ast.AST) -> Optional[str]:
    """从AST节点提取字符串值"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):  # f-string
        return "<fstring>"
    return None


def _is_sql_keyword(s: str) -> bool:
    """检查字符串是否包含SQL关键字"""
    sql_keywords = [
        'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE',
        'ALTER', 'EXEC', 'EXECUTE', 'UNION', 'FROM', 'WHERE',
        'TABLE', 'INTO', 'VALUES', 'SET', 'JOIN', 'ORDER BY',
        'GROUP BY', 'HAVING', 'LIMIT', 'OFFSET', 'TRUNCATE',
    ]
    s_upper = s.upper()
    return any(kw in s_upper for kw in sql_keywords)


def _has_parameterized_query(execute_node: ast.Call) -> bool:
    """检查execute()调用是否有参数化占位符（第二个参数或%s/?占位符）"""
    if len(execute_node.args) >= 2:
        return True
    for kw in execute_node.keywords:
        if kw.arg in ('params', 'parameters', 'args'):
            return True
    return False


def _check_fstring_sql_injection(node: ast.JoinedStr, content_lines: List[str]) -> Optional[Dict]:
    """检测f-string中的SQL注入 - f-string包含SQL关键字且有变量插值"""
    if not node.values:
        return None
    
    has_formatted_value = any(isinstance(v, ast.FormattedValue) for v in node.values)
    if not has_formatted_value:
        return None
    
    # 拼接f-string中的常量部分
    const_parts = []
    for v in node.values:
        if isinstance(v, ast.Constant) and isinstance(v.value, str):
            const_parts.append(v.value)
        elif isinstance(v, ast.FormattedValue):
            const_parts.append("{}")
    
    full_str = "".join(const_parts)
    if _is_sql_keyword(full_str):
        line = content_lines[node.lineno - 1] if node.lineno - 1 < len(content_lines) else ""
        return {
            'rule_id': 'PYAST001',
            'severity': 'P0',
            'category': 'sql_safety',
            'message': 'f-string拼接SQL语句存在注入风险',
            'line': node.lineno,
            'snippet': line.strip()[:120],
            'fix': '使用参数化查询替代f-string拼接：cursor.execute("SELECT * FROM t WHERE id = %s", (id_val,))',
        }
    return None


def _check_format_sql_injection(node: ast.Call, content_lines: List[str]) -> Optional[Dict]:
    """检测str.format()拼接SQL"""
    if not isinstance(node.func, ast.Attribute):
        return None
    if node.func.attr != 'format':
        return None
    
    # 检查被format的字符串是否包含SQL关键字
    if isinstance(node.func.value, ast.Constant) and isinstance(node.func.value.value, str):
        s = node.func.value.value
        if _is_sql_keyword(s) and node.args:
            line = content_lines[node.lineno - 1] if node.lineno - 1 < len(content_lines) else ""
            return {
                'rule_id': 'PYAST002',
                'severity': 'P0',
                'category': 'sql_safety',
                'message': 'str.format()拼接SQL语句存在注入风险',
                'line': node.lineno,
                'snippet': line.strip()[:120],
                'fix': '使用参数化查询：cursor.execute("SELECT * FROM t WHERE id = %s", (id_val,))',
            }
    return None


def _check_percent_sql_injection(node: ast.BinOp, content_lines: List[str]) -> Optional[Dict]:
    """检测%运算符拼接SQL"""
    if not isinstance(node.op, ast.Mod):
        return None
    
    # 左侧是字符串且包含SQL关键字
    if isinstance(node.left, ast.Constant) and isinstance(node.left.value, str):
        s = node.left.value
        if _is_sql_keyword(s) and ('%s' in s or '%d' in s or '%(' in s):
            line = content_lines[node.lineno - 1] if node.lineno - 1 < len(content_lines) else ""
            return {
                'rule_id': 'PYAST003',
                'severity': 'P0',
                'category': 'sql_safety',
                'message': '%运算符拼接SQL语句存在注入风险',
                'line': node.lineno,
                'snippet': line.strip()[:120],
                'fix': '使用参数化查询替代%格式化',
            }
    return None


def _check_concat_sql_injection(node: ast.BinOp, content_lines: List[str]) -> Optional[Dict]:
    """检测+运算符拼接SQL字符串"""
    if not isinstance(node.op, ast.Add):
        return None
    
    # 检查是否涉及字符串+变量的SQL拼接
    has_str = False
    has_var = False
    str_parts = []
    
    for operand in [node.left, node.right]:
        if isinstance(operand, ast.Constant) and isinstance(operand.value, str):
            has_str = True
            str_parts.append(operand.value)
        elif isinstance(operand, ast.Name):
            has_var = True
        elif isinstance(operand, ast.BinOp) and isinstance(operand.op, ast.Add):
            # 递归检查多级拼接
            pass
    
    if has_str and has_var:
        combined = " ".join(str_parts)
        if _is_sql_keyword(combined):
            line = content_lines[node.lineno - 1] if node.lineno - 1 < len(content_lines) else ""
            return {
                'rule_id': 'PYAST004',
                'severity': 'P0',
                'category': 'sql_safety',
                'message': '+运算符拼接SQL字符串存在注入风险',
                'line': node.lineno,
                'snippet': line.strip()[:120],
                'fix': '使用参数化查询替代字符串拼接',
            }
    return None


def _check_execute_no_params(node: ast.Call, content_lines: List[str]) -> Optional[Dict]:
    """检测execute()调用但无参数化（单参数execute）"""
    func = node.func
    
    # 匹配 .execute() 调用
    is_execute = False
    if isinstance(func, ast.Attribute) and func.attr == 'execute':
        is_execute = True
    elif isinstance(func, ast.Name) and func.id == 'execute':
        is_execute = True
    
    if not is_execute:
        return None
    
    # 只有一个参数且是字符串类型（f-string、format、拼接）
    if len(node.args) != 1:
        return None
    
    arg = node.args[0]
    
    # 参数是f-string
    if isinstance(arg, ast.JoinedStr):
        # 检查f-string是否包含SQL关键字
        const_parts = []
        for v in arg.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                const_parts.append(v.value)
        if any(_is_sql_keyword(p) for p in const_parts):
            line = content_lines[node.lineno - 1] if node.lineno - 1 < len(content_lines) else ""
            return {
                'rule_id': 'PYAST005',
                'severity': 'P0',
                'category': 'sql_safety',
                'message': 'execute()使用f-string参数，未使用参数化查询',
                'line': node.lineno,
                'snippet': line.strip()[:120],
                'fix': '使用参数化查询：cursor.execute("SQL %s", (param,))',
            }
    
    # 参数是format调用
    if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Attribute):
        if arg.func.attr == 'format':
            if isinstance(arg.func.value, ast.Constant) and isinstance(arg.func.value.value, str):
                if _is_sql_keyword(arg.func.value.value):
                    line = content_lines[node.lineno - 1] if node.lineno - 1 < len(content_lines) else ""
                    return {
                        'rule_id': 'PYAST005',
                        'severity': 'P0',
                        'category': 'sql_safety',
                        'message': 'execute()使用format()参数，未使用参数化查询',
                        'line': node.lineno,
                        'snippet': line.strip()[:120],
                        'fix': '使用参数化查询：cursor.execute("SQL %s", (param,))',
                    }
    
    # 参数是%运算
    if isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Mod):
        if isinstance(arg.left, ast.Constant) and isinstance(arg.left.value, str):
            if _is_sql_keyword(arg.left.value):
                line = content_lines[node.lineno - 1] if node.lineno - 1 < len(content_lines) else ""
                return {
                    'rule_id': 'PYAST005',
                    'severity': 'P0',
                    'category': 'sql_safety',
                    'message': 'execute()使用%格式化参数，未使用参数化查询',
                    'line': node.lineno,
                    'snippet': line.strip()[:120],
                    'fix': '使用参数化查询：cursor.execute("SQL %s", (param,))',
                }
    
    # 参数是+拼接
    if isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Add):
        if isinstance(arg.left, ast.Constant) and isinstance(arg.left.value, str):
            if _is_sql_keyword(arg.left.value):
                line = content_lines[node.lineno - 1] if node.lineno - 1 < len(content_lines) else ""
                return {
                    'rule_id': 'PYAST005',
                    'severity': 'P0',
                    'category': 'sql_safety',
                    'message': 'execute()使用字符串拼接参数，未使用参数化查询',
                    'line': node.lineno,
                    'snippet': line.strip()[:120],
                    'fix': '使用参数化查询：cursor.execute("SQL %s", (param,))',
                }
    
    return None


def _check_orm_raw_sql(node: ast.Call, content_lines: List[str]) -> Optional[Dict]:
    """检测ORM的.raw()/.extra()/RawSQL中的SQL注入"""
    func = node.func
    if not isinstance(func, ast.Attribute):
        return None
    
    method_name = func.attr
    
    # 检测 .raw() 调用
    if method_name == 'raw':
        if node.args and isinstance(node.args[0], (ast.JoinedStr, ast.BinOp)):
            if isinstance(node.args[0], ast.JoinedStr):
                line = content_lines[node.lineno - 1] if node.lineno - 1 < len(content_lines) else ""
                return {
                    'rule_id': 'PYAST006',
                    'severity': 'P1',
                    'category': 'sql_safety',
                    'message': 'ORM .raw()使用f-string拼接SQL',
                    'line': node.lineno,
                    'snippet': line.strip()[:120],
                    'fix': '使用.raw()的params参数：Model.objects.raw("SQL %s", [param])',
                }
            elif isinstance(node.args[0], ast.BinOp) and isinstance(node.args[0].op, ast.Mod):
                line = content_lines[node.lineno - 1] if node.lineno - 1 < len(content_lines) else ""
                return {
                    'rule_id': 'PYAST006',
                    'severity': 'P1',
                    'category': 'sql_safety',
                    'message': 'ORM .raw()使用%拼接SQL',
                    'line': node.lineno,
                    'snippet': line.strip()[:120],
                    'fix': '使用.raw()的params参数：Model.objects.raw("SQL %s", [param])',
                }
    
    # 检测 .extra() 调用中的where参数
    if method_name == 'extra' and node.args:
        for arg in node.args:
            if isinstance(arg, (ast.List, ast.Tuple)):
                for elt in arg.elts:
                    if isinstance(elt, (ast.JoinedStr, ast.BinOp)):
                        line = content_lines[node.lineno - 1] if node.lineno - 1 < len(content_lines) else ""
                        return {
                            'rule_id': 'PYAST007',
                            'severity': 'P1',
                            'category': 'sql_safety',
                            'message': 'ORM .extra()中where参数使用了动态拼接',
                            'line': node.lineno,
                            'snippet': line.strip()[:120],
                            'fix': '使用.extra()的params参数：.extra(where=["col = %s"], params=[val])',
                        }
    
    # 检测 keywords 中的 where
    for kw in node.keywords:
        if kw.arg == 'where' and isinstance(kw.value, (ast.List, ast.Tuple)):
            for elt in kw.value.elts:
                if isinstance(elt, (ast.JoinedStr, ast.BinOp)):
                    line = content_lines[node.lineno - 1] if node.lineno - 1 < len(content_lines) else ""
                    return {
                        'rule_id': 'PYAST007',
                        'severity': 'P1',
                        'category': 'sql_safety',
                        'message': 'ORM .extra(where=...)中使用动态SQL拼接',
                        'line': node.lineno,
                        'snippet': line.strip()[:120],
                        'fix': '使用params参数而非字符串拼接',
                    }
    
    # 检测 RawSQL() 构造
    if isinstance(func, ast.Name) and func.id == 'RawSQL':
        if node.args and isinstance(node.args[0], (ast.JoinedStr, ast.BinOp)):
            if isinstance(node.args[0], ast.JoinedStr):
                line = content_lines[node.lineno - 1] if node.lineno - 1 < len(content_lines) else ""
                return {
                    'rule_id': 'PYAST008',
                    'severity': 'P1',
                    'category': 'sql_safety',
                    'message': 'RawSQL()使用f-string拼接SQL',
                    'line': node.lineno,
                    'snippet': line.strip()[:120],
                    'fix': '使用RawSQL的params参数：RawSQL("SQL %s", [param])',
                }
    
    return None


def check_sql_safety_ast(context) -> List[Dict]:
    """SQL安全AST深度分析 - 检测各类SQL注入风险"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    seen_rules = set()  # 每个rule_id每个文件只报一次
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        content_lines = content.split('\n')
        
        # Annotate AST nodes with parent references
        for _node in ast.walk(tree):
            for _child in ast.iter_child_nodes(_node):
                _child._parent = _node
        
        for node in ast.walk(tree):
            findings = []
            
            # f-string SQL注入 - 跳过作为 execute() 第一参数且有第二参数(参数化)的情况
            if isinstance(node, ast.JoinedStr):
                _skip_fstring = False
                _parent = getattr(node, '_parent', None)
                if _parent and isinstance(_parent, ast.Call):
                    func = _parent.func
                    is_exec = (isinstance(func, ast.Attribute) and func.attr == 'execute') or \
                              (isinstance(func, ast.Name) and func.id == 'execute')
                    if is_exec and len(_parent.args) >= 2:
                        _skip_fstring = True
                if not _skip_fstring:
                    r = _check_fstring_sql_injection(node, content_lines)
                    if r:
                        findings.append(r)
            
            # format() SQL注入
            if isinstance(node, ast.Call):
                r = _check_format_sql_injection(node, content_lines)
                if r:
                    findings.append(r)
                
                # execute() 无参数化
                r = _check_execute_no_params(node, content_lines)
                if r:
                    findings.append(r)
                
                # ORM raw/extra/RawSQL
                r = _check_orm_raw_sql(node, content_lines)
                if r:
                    findings.append(r)
            
            # % 运算符SQL注入
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
                r = _check_percent_sql_injection(node, content_lines)
                if r:
                    findings.append(r)
            
            # + 运算符SQL注入
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
                r = _check_concat_sql_injection(node, content_lines)
                if r:
                    findings.append(r)
            
            for finding in findings:
                key = (finding['rule_id'], fpath, finding['line'])
                if key not in seen_rules:
                    seen_rules.add(key)
                    results.append({
                        'id': finding['rule_id'],
                        'name': 'SQL安全AST分析',
                        'level': 'error' if finding['severity'] == 'P0' else 'warning',
                        'message': finding['message'],
                        'file': fpath,
                        'line': finding['line'],
                        'snippet': finding['snippet'],
                        'fix': finding['fix'],
                    })
    
    return results


# ===== 正则兜底规则 =====
def check_sql_safety_regex(context) -> List[Dict]:
    """SQL安全正则兜底 - 检测AST无法覆盖的模式"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    # 检测 SQLAlchemy text() 中使用字符串格式化
    text_format_patterns = [
        (r'\.execute\s*\(\s*text\s*\(\s*f["\']', 'SQLAlchemy text()使用f-string'),
        (r'\.execute\s*\(\s*text\s*\([^)]*\.format\s*\(', 'SQLAlchemy text()使用format()'),
        (r'\.execute\s*\(\s*text\s*\([^)]*%\s*\w', 'SQLAlchemy text()使用%格式化'),
        (r'\.execute\s*\(\s*text\s*\([^)]*\+', 'SQLAlchemy text()使用+拼接'),
        # 检测 MongoDB $where 注入
        (r'\$where.*?f["\']', 'MongoDB $where使用f-string'),
        (r'\$where.*?\.format', 'MongoDB $where使用format()'),
        (r'\$where[^}]*%', 'MongoDB $where使用%格式化'),
    ]
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        lines = content.split('\n')
        for pattern, desc in text_format_patterns:
            for m in re.finditer(pattern, content):
                line_num = content[:m.start()].count('\n') + 1
                line_text = lines[line_num - 1] if line_num - 1 < len(lines) else ""
                
                # 跳过注释行
                if line_text.strip().startswith('#'):
                    continue
                
                results.append({
                    'id': 'PYAST005',
                    'name': 'SQL安全正则检测',
                    'level': 'warning',
                    'message': f'{desc}，存在SQL注入风险',
                    'file': fpath,
                    'line': line_num,
                    'snippet': line_text.strip()[:120],
                    'fix': '使用参数化查询或绑定参数',
                })
                break  # 每个文件每个模式只报一次
    
    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'PYAST001',
        'name': 'SQL安全AST分析',
        'level': 'error',
        'category': 'sql_safety',
        'module_id': '2',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': 'AST级检测f-string/format/%拼接SQL语句的注入风险',
        'check': check_sql_safety_ast,
    },
    {
        'id': 'PYAST005',
        'name': 'SQL安全正则检测',
        'level': 'warning',
        'category': 'sql_safety',
        'module_id': '2',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '正则兜底检测SQLAlchemy text()、MongoDB $where等SQL注入',
        'check': check_sql_safety_regex,
    },
]
