"""
AI质检 P0 安全规则 - 危险函数检测 (AI-SEC)
从 security_rules.py 拆分而来，包含:
  AI-SEC-03 危险函数 - eval()、exec()、pickle.load()、yaml.load(非SafeLoader)
"""

import re
import os
import ast
from typing import List, Dict, Any

def check_ai_sec_03_dangerous_functions(context) -> List[Dict]:
    """AI-SEC-03 危险函数检测
    AI生成代码常滥用eval/exec/pickle.load等危险函数
    误报控制：用AST检测（避免字符串/注释误报），排除测试文件和规则定义文件
    """
    results = []
    
    py_files = [f for f in context.find_files([".py"])
                if os.path.basename(f) != "__init__.py"]
    js_files = [f for f in context.get_filtered_files("security") if f.endswith((".js", ".ts", ".jsx", ".tsx"))]
    
    if not py_files and not js_files:
        return results
    
    all_issues = []
    
    def _is_excluded_py_file(fpath: str) -> bool:
        """判断是否应排除的Python文件"""
        basename = os.path.basename(fpath).lower()
        rel = os.path.relpath(fpath, context.project_path or context.backend_path or ".")
        rel_lower = rel.lower()
        
        # 测试文件
        if basename.startswith('test_') or basename.endswith('_test.py'):
            return True
        if 'test' in rel_lower.split(os.sep) or 'tests' in rel_lower.split(os.sep):
            return True
        
        # 规则定义文件（规则里常写eval/exec作为检测模式字符串）
        if 'rules' + os.sep in rel_lower:
            return True
        
        # 验证/测试辅助脚本
        if any(x in basename for x in ['verify', 'check_rule', 'poc', 'demo']):
            return True
        
        return False
    
    # ===== Python 危险函数（用AST准确检测，避免字符串/注释误报）=====
    py_dangerous_funcs = {
        'eval': 'eval()执行任意代码',
        'exec': 'exec()执行任意代码',
    }
    
    py_dangerous_methods = {
        ('pickle', 'load'): 'pickle.load()反序列化漏洞',
        ('pickle', 'loads'): 'pickle.loads()反序列化漏洞',
        ('yaml', 'load'): 'yaml.load()(未使用SafeLoader)',
    }
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        if _is_excluded_py_file(fpath):
            continue
        
        lines = content.split('\n')
        rel = os.path.relpath(fpath, context.project_path or context.backend_path or ".")
        
        try:
            tree = context.parse_ast(fpath)
            if tree is None:
                continue
            
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                
                func = node.func
                desc = None
                
                # 直接调用：eval(), exec()
                if isinstance(func, ast.Name):
                    if func.id in py_dangerous_funcs:
                        desc = py_dangerous_funcs[func.id]
                
                # 方法调用：pickle.load(), yaml.load()
                elif isinstance(func, ast.Attribute):
                    if isinstance(func.value, ast.Name):
                        key = (func.value.id, func.attr)
                        if key in py_dangerous_methods:
                            # yaml.load的特殊处理：检查是否用了SafeLoader
                            if func.value.id == 'yaml' and func.attr == 'load':
                                has_safe_loader = False
                                for kw in node.keywords:
                                    if kw.arg == 'Loader' and isinstance(kw.value, ast.Name):
                                        if 'SafeLoader' in kw.value.id:
                                            has_safe_loader = True
                                            break
                                if has_safe_loader:
                                    continue
                            desc = py_dangerous_methods[key]
                
                if desc:
                    all_issues.append({
                        'file': fpath,
                        'rel': rel,
                        'line': node.lineno,
                        'desc': desc,
                        'snippet': lines[node.lineno - 1].strip()[:100] if node.lineno - 1 < len(lines) else "",
                        'severity': 'high',
                    })
        except SyntaxError:
            continue
    
    # ===== JS/TS 危险函数 =====
    js_dangerous = [
        (r'\beval\s*\(', 'eval()执行任意代码', 'high'),
        (r'new\s+Function\s*\(', 'new Function()执行动态代码', 'high'),
    ]
    
    for fpath in js_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        lines = content.split('\n')
        rel = os.path.relpath(fpath, context.project_path or context.backend_path or ".")
        basename = os.path.basename(fpath)
        
        # 跳过测试文件
        if any(x in basename.lower() for x in ['test', 'spec', 'jest', 'mocha']):
            continue
        
        for pat, desc, severity in js_dangerous:
            for m in re.finditer(pat, content):
                line_num = content[:m.start()].count('\n') + 1
                line_content = lines[line_num - 1] if line_num - 1 < len(lines) else ""
                
                # 跳过注释行
                stripped = line_content.strip()
                if stripped.startswith(('//', '*', '/*')):
                    continue
                
                # 跳过字符串中的（简单判断：匹配内容前后有引号的可能是字符串）
                # 简化处理：只检查不在明显字符串中的
                
                all_issues.append({
                    'file': fpath,
                    'rel': rel,
                    'line': line_num,
                    'desc': desc,
                    'snippet': line_content.strip()[:100],
                    'severity': severity,
                })
    
    if all_issues:
        total = len(all_issues)
        detail_lines = [
            f"{issue['rel']}:{issue['line']} - {issue['desc']}"
            for issue in all_issues[:15]
        ]
        
        results.append({
            'id': 'AI-SEC-03',
            'name': '危险函数检测',
            'level': 'error',  # 高危
            'message': f'发现 {total} 处危险函数调用（可能导致代码执行漏洞）',
            'detail': '\n'.join(detail_lines),
            'file': all_issues[0]['file'] if all_issues else '',
            'line': all_issues[0]['line'] if all_issues else 0,
            'snippet': all_issues[0]['snippet'] if all_issues else '',
            'fix': '避免使用eval/exec等危险函数；pickle改用json；yaml改用yaml.safe_load()',
            'category': 'ai_security',
        })
    
    return results


# ===== AI-SEC-04 SQL注入风险 =====


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'AI-SEC-03',
        'name': '危险函数检测',
        'level': 'blocking',
        'category': 'ai_code_check',
        'module_id': 'ai_security',
        'applicable_types': [],
        'description': '检测eval/exec/pickle.load/yaml.load等危险函数调用',
        'check': check_ai_sec_03_dangerous_functions,
    },
]
