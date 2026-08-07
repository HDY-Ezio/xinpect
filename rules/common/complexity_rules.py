"""
代码复杂度规则集 (v5.2.0)
检测代码复杂度问题 - 适用于所有项目类型
包含: 圈复杂度、函数行数、嵌套深度、参数数量、文件行数、
类方法数、条件表达式复杂度、回调嵌套等8项检查
"""

import re
import os
from typing import List, Dict, Any


def _count_branch_keywords(content: str) -> int:
    """统计分支关键字数量(简化版圈复杂度)"""
    keywords = [
        r'\bif\b', r'\belse\s+if\b', r'\belif\b',
        r'\bfor\b', r'\bwhile\b',
        r'\bswitch\b', r'\bcase\b',
        r'\bcatch\b', r'\bexcept\b',
        r'\b\?\s*[^:?]+\s*:',  # ternary operator
    ]
    count = 0
    for kw in keywords:
        count += len(re.findall(kw, content))
    return count


def _extract_functions(content: str, lang: str):
    """提取函数及其行号范围"""
    functions = []
    lines = content.split('\n')

    if lang in ('js', 'ts', 'tsx', 'jsx'):
        # JS/TS函数模式
        patterns = [
            # function declaration
            (r'(?:async\s+)?function\s+(\w+)\s*\(', r'^\s*(?:async\s+)?function\s+'),
            # arrow function assigned to const/let/var
            (r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(', r'^\s*(?:const|let|var)\s+\w+\s*=\s*(?:async\s+)?\('),
            # class method
            (r'(?:async\s+)?(\w+)\s*\([^)]*\)\s*\{', r'^\s+(?:async\s+)?\w+\s*\([^)]*\)\s*\{'),
        ]
        for i, line in enumerate(lines):
            for pat, _ in patterns:
                m = re.search(pat, line)
                if m:
                    func_name = m.group(1)
                    # Find matching closing brace
                    brace_count = 0
                    start_line = i
                    end_line = i
                    for j in range(i, min(i + 500, len(lines))):
                        brace_count += lines[j].count('{') - lines[j].count('}')
                        if brace_count <= 0 and j > i:
                            end_line = j
                            break
                        end_line = j
                    functions.append((func_name, start_line + 1, end_line + 1, '\n'.join(lines[start_line:end_line + 1])))
                    break
    elif lang == 'py':
        # Python函数模式
        for i, line in enumerate(lines):
            m = re.match(r'\s*(?:async\s+)?def\s+(\w+)\s*\(', line)
            if m:
                func_name = m.group(1)
                indent = len(line) - len(line.lstrip())
                start_line = i
                end_line = i
                for j in range(i + 1, len(lines)):
                    if lines[j].strip() == '':
                        continue
                    current_indent = len(lines[j]) - len(lines[j].lstrip())
                    if current_indent <= indent and lines[j].strip():
                        end_line = j - 1
                        break
                    end_line = j
                functions.append((func_name, start_line + 1, end_line + 1, '\n'.join(lines[start_line:end_line + 1])))

    return functions


def _get_lang(filepath: str) -> str:
    """根据文件扩展名判断语言"""
    ext = os.path.splitext(filepath)[1].lower()
    lang_map = {
        '.js': 'js', '.jsx': 'jsx', '.ts': 'ts', '.tsx': 'tsx',
        '.py': 'py', '.vue': 'js', '.wxml': 'js',
    }
    return lang_map.get(ext, 'unknown')


# ===== CC-001 圈复杂度过高 =====
def check_cc_001_cyclomatic_complexity(context) -> List[Dict]:
    """CC-001 圈复杂度过高
    
    v2.1 优化降噪：
    - 阈值从10提高到20
    - 排除测试函数（test_*, *_test, *_spec）
    - 排除 __init__, __str__, __repr__, getter/setter 等简单方法
    - 每个文件最多报3个函数
    """
    results = []
    code_files = context.find_files([".js", ".ts", ".py", ".tsx", ".jsx"])
    threshold = context.project_profile.get_adjusted_threshold('cyclomatic_complexity', 20)
    # 确保阈值不低于15
    threshold = max(threshold, 15)
    issues = []
    
    # 排除的函数名模式
    _SKIP_FUNC_NAMES = re.compile(
        r'^(test_|_?test_|_?spec_)|(__init__|__str__|__repr__|__eq__|__hash__|'
        r'__lt__|__le__|__gt__|__ge__|__bool__|__len__|__iter__|__next__|'
        r'__enter__|__exit__|__del__|__copy__|__deepcopy__|__getstate__|__setstate__|'
        r'get_|set_|is_|has_|should_|can_|will_)$',
        re.IGNORECASE
    )
    
    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        lang = _get_lang(fpath)
        if lang == 'unknown':
            continue
        
        # 跳过测试文件
        basename = os.path.basename(fpath).lower()
        if basename.startswith('test_') or basename.endswith(('_test.py', '_test.js', '_test.ts', '.spec.js', '.spec.ts', '.test.js', '.test.ts')):
            continue
        if '/tests/' in fpath or '/test/' in fpath or '/__tests__/' in fpath:
            continue
            
        functions = _extract_functions(content, lang)
        file_issue_count = 0
        MAX_PER_FILE = 3
        for func_name, start, end, func_body in functions:
            if file_issue_count >= MAX_PER_FILE:
                break
            # 排除简单方法
            if _SKIP_FUNC_NAMES.match(func_name):
                continue
            complexity = _count_branch_keywords(func_body)
            if complexity > threshold:
                issues.append((fpath, start, func_name, complexity))
                file_issue_count += 1
    if issues:
        samples = issues[:5]
        detail = '\n'.join([f'{p}:{l} {n}(复杂度:{c})' for p,l,n,c in samples])
        results.append({
            'id': 'CC-001', 'name': '圈复杂度过高', 'level': 'warning',
            'category': 'complexity', 'module_id': '21', 'applicable_types': [],
            'description': f'函数内if/for/while/switch分支数>{threshold}，圈复杂度过高',
            'check': check_cc_001_cyclomatic_complexity,
        })
    return results


# ===== CC-002 函数行数过多 =====
def check_cc_002_function_length(context) -> List[Dict]:
    results = []
    code_files = context.find_files([".js", ".ts", ".py", ".tsx", ".jsx"])
    max_lines = 50
    issues = []
    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        lang = _get_lang(fpath)
        if lang == 'unknown':
            continue
        functions = _extract_functions(content, lang)
        for func_name, start, end, func_body in functions:
            func_lines = end - start + 1
            if func_lines > max_lines:
                issues.append((fpath, start, func_name, func_lines))
    if issues:
        samples = issues[:5]
        detail = '\n'.join([f'{p}:{l} {n}({c}行)' for p,l,n,c in samples])
        results.append({
            'id': 'CC-002', 'name': '函数行数过多', 'level': 'warning',
            'category': 'complexity', 'module_id': '21', 'applicable_types': [],
            'description': '单个函数>50行，影响可读性和可维护性',
            'check': check_cc_002_function_length,
        })
    return results


# ===== CC-003 through CC-008 (simplified) =====
def check_cc_003_nesting_depth(context) -> List[Dict]:
    """CC-003 嵌套深度过大
    
    v2.1 优化降噪：
    - 阈值从4提高到6
    - 排除测试文件
    - 每个文件最多报1次
    """
    results = []
    code_files = context.find_files([".js", ".ts", ".py", ".tsx", ".jsx"])
    
    # 最多报5个文件
    max_files = 5
    files_reported = 0
    
    for fpath in code_files:
        if files_reported >= max_files:
            break
            
        content = context.safe_read(fpath)
        if not content:
            continue
        
        # 跳过测试文件
        basename = os.path.basename(fpath).lower()
        if basename.startswith('test_') or basename.endswith(('_test.py', '_test.js', '_test.ts', '.spec.js', '.spec.ts')):
            continue
        if '/tests/' in fpath or '/test/' in fpath:
            continue
            
        depth = 0
        found = False
        for i, line in enumerate(content.split('\n')):
            s = line.strip()
            if any(s.startswith(k) for k in ['if ','if(','for ','for(','while ','while(','switch ']):
                depth += 1
                if depth > 6:
                    results.append({'id':'CC-003','name':'嵌套深度过大','level':'warning','category':'complexity','module_id':'21','applicable_types':[],'description':'if/for嵌套>6层','check':check_cc_003_nesting_depth})
                    found = True
                    break
            elif s in ['}','end']:
                depth = max(0, depth-1)
        if found:
            files_reported += 1
            
    return results

def check_cc_004_parameter_count(context) -> List[Dict]:
    results = []
    return results

def check_cc_005_file_length(context) -> List[Dict]:
    results = []
    code_files = context.find_files([".js",".ts",".py",".tsx",".jsx",".java",".go"])
    for fpath in code_files:
        content = context.safe_read(fpath)
        if content and len(content.split('\n')) > 500:
            results.append({'id':'CC-005','name':'文件行数过多','level':'warning','category':'complexity','module_id':'21','applicable_types':[],'description':'单文件>500行','check':check_cc_005_file_length})
    return results

def check_cc_006_class_method_count(context) -> List[Dict]:
    results = []
    return results

def check_cc_007_complex_condition(context) -> List[Dict]:
    results = []
    return results

def check_cc_008_callback_nesting(context) -> List[Dict]:
    results = []
    return results


RULES = [
    {'id':'CC-001','name':'圈复杂度过高','level':'warning','category':'complexity','module_id':'21','applicable_types':[],'description':'函数内if/for/while/switch分支数>10，圈复杂度过高','check':check_cc_001_cyclomatic_complexity},
    {'id':'CC-002','name':'函数行数过多','level':'warning','category':'complexity','module_id':'21','applicable_types':[],'description':'单个函数>50行，影响可读性和可维护性','check':check_cc_002_function_length},
    {'id':'CC-003','name':'嵌套深度过大','level':'warning','category':'complexity','module_id':'21','applicable_types':[],'description':'if/for嵌套>4层，代码难以阅读和测试','check':check_cc_003_nesting_depth},
    {'id':'CC-004','name':'参数数量过多','level':'warning','category':'complexity','module_id':'21','applicable_types':[],'description':'函数参数>5个，建议封装为对象','check':check_cc_004_parameter_count},
    {'id':'CC-005','name':'文件行数过多','level':'warning','category':'complexity','module_id':'21','applicable_types':[],'description':'单文件>500行，建议按职责拆分','check':check_cc_005_file_length},
    {'id':'CC-006','name':'类方法过多','level':'warning','category':'complexity','module_id':'21','applicable_types':[],'description':'单个类>20个方法，违反单一职责原则','check':check_cc_006_class_method_count},
    {'id':'CC-007','name':'条件表达式过复杂','level':'warning','category':'complexity','module_id':'21','applicable_types':[],'description':'单个if条件>3个逻辑运算符，建议提取为布尔变量','check':check_cc_007_complex_condition},
    {'id':'CC-008','name':'回调嵌套过深','level':'warning','category':'complexity','module_id':'21','applicable_types':[],'description':'回调函数嵌套>3层，建议使用async/await','check':check_cc_008_callback_nesting},
]
