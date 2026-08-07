"""
死代码检测规则集 (v5.2.0)
检测未使用和不可达代码 - 适用于所有项目类型
包含: 未使用变量、未使用函数、未使用导入、不可达代码、
注释代码块、空catch块、TODO堆积、废弃API等8项检查
"""

import re
import os
from typing import List, Dict, Any


# ===== DEAD-001 未使用变量 =====
def check_dead_001_unused_variables(context) -> List[Dict]:
    """DEAD-001 未使用变量 - 声明后未读取的变量

    v4.4 误报治理:
    - 跳过模块级 RULES 常量（规则框架通过 module.RULES 加载，非未使用）
    - 跳过全大写常量（通常是模块级配置/导出，如 _ARCH_LAYER_KEYWORDS）
    - 跳过以下划线开头的变量（Python 惯例：有意不使用）
    - 跳过注释行、docstring 内的赋值
    """
    results = []
    code_files = context.find_files([".js", ".ts", ".py", ".tsx", ".jsx"])
    issues = []

    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        ext = os.path.splitext(fpath)[1].lower()
        lines = content.split('\n')

        if ext == '.py':
            # v2.9.2 P4: O(n)算法 - 一次提取所有标识符，批量检查
            # 先建全文标识符集合（一次正则扫描）
            import re as _re
            all_identifiers = _re.findall(r'\b([a-zA-Z_]\w*)\b', content)
            # 统计每个标识符出现次数
            id_count = {}
            for _id in all_identifiers:
                id_count[_id] = id_count.get(_id, 0) + 1
            
            _skip_names = {'self', 'cls', '_', '__all__', '__name__', '__init__',
                          'True', 'False', 'None', 'print', 'len', 'range', 'str',
                          'int', 'float', 'list', 'dict', 'set', 'tuple', 'type',
                          'isinstance', 'getattr', 'setattr', 'hasattr', 'super',
                          'property', 'staticmethod', 'classmethod', 'abs', 'map',
                          'filter', 'sorted', 'enumerate', 'zip', 'open', 'input'}
            
            # v4.4: 找出 docstring 范围，跳过 docstring 内的赋值
            _doc_ranges = _find_docstring_ranges(lines)

            def _in_docstring(lineno: int) -> bool:
                for s, e in _doc_ranges:
                    if s <= lineno <= e:
                        return True
                return False

            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith('#'):
                    continue
                # v4.4: 跳过 docstring 内的行
                if _in_docstring(i + 1):
                    continue
                m = _re.match(r'^(\w+)\s*=\s*(?!.*\1)', stripped)
                if m:
                    var_name = m.group(1)
                    if var_name in _skip_names or var_name.startswith('__'):
                        continue
                    # v4.4: 以下划线开头的变量视为有意不使用（Python 惯例）
                    if var_name.startswith('_'):
                        continue
                    # v4.4: 全大写常量视为模块级配置/导出（如 RULES, _ARCH_LAYER_KEYWORDS）
                    # RULES 等由规则加载器通过 module.RULES 动态访问，不计入未使用
                    if var_name.isupper() and '_' in var_name and any(c.isalpha() for c in var_name):
                        continue
                    # v4.4: 单一全大写单词常量（如 RULES = [...]）也跳过
                    if var_name.isupper() and var_name.isalpha():
                        continue
                    # O(1) 查找代替 O(n) 全文搜索
                    if id_count.get(var_name, 0) <= 1:
                        issues.append((fpath, i + 1, var_name))

        elif ext in ('.js', '.ts', '.tsx', '.jsx'):
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith('//'):
                    continue
                # Match const/let declarations
                m = re.match(r'(?:const|let|var)\s+(\w+)\s*=\s*', stripped)
                if m:
                    var_name = m.group(1)
                    if var_name.startswith('_'):
                        continue
                    # Check usage in rest of file
                    # Exclude the declaration line itself
                    other_content = '\n'.join(lines[:i] + lines[i+1:])
                    if not re.search(rf'\b{re.escape(var_name)}\b', other_content):
                        issues.append((fpath, i + 1, var_name))

        if len(issues) > 50:
            break

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} 变量 '{n}' 声明后未使用"
            for f, l, n in issues[:8]
        )
        results.append({
            'id': 'DEAD-001',
            'name': '未使用变量',
            'level': 'warning',
            'message': f'发现{len(issues)}个未使用的变量',
            'detail': detail,
            'file': issues[0][0],
            'line': issues[0][1],
            'fix': '删除未使用的变量声明，或添加下划线前缀表示有意忽略',
        })

    return results


# ===== DEAD-002 未使用函数 =====
def check_dead_002_unused_functions(context) -> List[Dict]:
    """DEAD-002 未使用函数 - 定义后未调用的函数(排除export)"""
    results = []
    code_files = context.find_files([".js", ".ts", ".py", ".tsx", ".jsx"])
    issues = []

    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        ext = os.path.splitext(fpath)[1].lower()
        lines = content.split('\n')

        if ext == '.py':
            # Find function definitions
            for i, line in enumerate(lines):
                m = re.match(r'\s*def\s+(\w+)\s*\(', line)
                if m:
                    func_name = m.group(1)
                    # Skip dunder methods
                    if func_name.startswith('__') and func_name.endswith('__'):
                        continue
                    # Check if exported or used
                    if not re.search(rf'\b{re.escape(func_name)}\b(?!.*def\s)', content[m.end():]):
                        # Not called anywhere after definition
                        call_count = len(re.findall(rf'\b{re.escape(func_name)}\s*\(', content))
                        if call_count <= 1:  # Only the definition itself
                            issues.append((fpath, i + 1, func_name))

        elif ext in ('.js', '.ts', '.tsx', '.jsx'):
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith('//') or stripped.startswith('*'):
                    continue
                # Check for function declarations (not exported)
                func_match = re.match(r'(?:async\s+)?function\s+(\w+)\s*\(', stripped)
                if not func_match:
                    # Arrow function assigned to const
                    func_match = re.match(r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\([^)]*\)|[^=])\s*=>', stripped)
                if func_match:
                    func_name = func_match.group(1)
                    # Skip if exported
                    if 'export' in line:
                        continue
                    if func_name.startswith('_'):
                        continue
                    # Count usages
                    other_lines = lines[:i] + lines[i+1:]
                    other_content = '\n'.join(other_lines)
                    usage_count = len(re.findall(rf'\b{re.escape(func_name)}\s*[\(<]', other_content))
                    if usage_count == 0:
                        issues.append((fpath, i + 1, func_name))

        if len(issues) > 50:
            break

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} 函数 '{n}' 未被调用"
            for f, l, n in issues[:8]
        )
        results.append({
            'id': 'DEAD-002',
            'name': '未使用函数',
            'level': 'warning',
            'message': f'发现{len(issues)}个未使用的函数',
            'detail': detail,
            'file': issues[0][0],
            'line': issues[0][1],
            'fix': '删除未使用的函数，或将需要保留的函数添加export导出',
        })

    return results


# ===== DEAD-003 未使用导入 =====
def check_dead_003_unused_imports(context) -> List[Dict]:
    """DEAD-003 未使用导入 - import后未使用的模块"""
    results = []
    code_files = context.find_files([".js", ".ts", ".py", ".tsx", ".jsx"])
    issues = []

    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        ext = os.path.splitext(fpath)[1].lower()
        lines = content.split('\n')

        if ext == '.py':
            for i, line in enumerate(lines):
                stripped = line.strip()
                # import xxx
                m = re.match(r'^import\s+(\w+)', stripped)
                if m:
                    module_name = m.group(1)
                    # Check if used in rest of file
                    rest_content = '\n'.join(lines[i+1:])
                    if not re.search(rf'\b{re.escape(module_name)}\b', rest_content):
                        issues.append((fpath, i + 1, stripped))
                    continue
                # from xxx import yyy
                m = re.match(r'^from\s+\S+\s+import\s+(.+)', stripped)
                if m:
                    imports = m.group(1).split(',')
                    rest_content = '\n'.join(lines[i+1:])
                    for imp in imports:
                        imp = imp.strip()
                        # Handle 'as' alias
                        name = imp.split(' as ')[-1].strip() if ' as ' in imp else imp.strip()
                        if name and not re.search(rf'\b{re.escape(name)}\b', rest_content):
                            issues.append((fpath, i + 1, f"from ... import {name}"))

        elif ext in ('.js', '.ts', '.tsx', '.jsx'):
            for i, line in enumerate(lines):
                stripped = line.strip()
                if not stripped.startswith('import '):
                    continue
                # Extract imported names
                # import { A, B } from '...'
                m = re.search(r'import\s+\{([^}]+)\}\s+from', stripped)
                if m:
                    names = [n.strip().split(' as ')[-1].strip() for n in m.group(1).split(',')]
                    rest_content = '\n'.join(lines[i+1:])
                    for name in names:
                        if name and not re.search(rf'\b{re.escape(name)}\b', rest_content):
                            issues.append((fpath, i + 1, f"import {{ {name} }}"))
                    continue
                # import X from '...'
                m = re.match(r'import\s+(\w+)\s+from', stripped)
                if m:
                    name = m.group(1)
                    rest_content = '\n'.join(lines[i+1:])
                    if not re.search(rf'\b{re.escape(name)}\b', rest_content):
                        issues.append((fpath, i + 1, f"import {name}"))

        if len(issues) > 50:
            break

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} {n}"
            for f, l, n in issues[:8]
        )
        results.append({
            'id': 'DEAD-003',
            'name': '未使用导入',
            'level': 'warning',
            'message': f'发现{len(issues)}个未使用的import',
            'detail': detail,
            'file': issues[0][0],
            'line': issues[0][1],
            'fix': '删除未使用的import语句，减少不必要的依赖加载',
        })

    return results


# ===== DEAD-004 不可达代码 =====
def check_dead_004_unreachable_code(context) -> List[Dict]:
    """DEAD-004 不可达代码 - return/break/continue后的代码

    v4.4 误报治理:
    - 修复缩进判断：只有前一行(控制语句)与当前行处于相同缩进层级才视为同一块的不可达代码
      （避免 if 块内的 return 之后、函数主体的正常代码被误判）
    - 跳过 docstring 内的行
    - 跳过装饰器行
    """
    results = []
    code_files = context.find_files([".js", ".ts", ".py", ".tsx", ".jsx"])
    issues = []

    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        lines = content.split('\n')
        ext = os.path.splitext(fpath)[1].lower()

        if ext == '.py':
            # v4.4: 预计算 docstring 范围
            _doc_ranges = _find_docstring_ranges(lines)

            def _in_docstring(lineno: int) -> bool:
                for s, e in _doc_ranges:
                    if s <= lineno <= e:
                        return True
                return False

            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith('#'):
                    continue
                # v4.4: 跳过 docstring
                if _in_docstring(i + 1):
                    continue
                # v4.4: 跳过装饰器行
                if stripped.startswith('@'):
                    continue
                # Check if previous non-empty line is return/break/continue/raise
                if stripped and i > 0:
                    # Find previous non-empty, non-comment line at same or greater indent
                    curr_indent = len(line) - len(line.lstrip())
                    for j in range(i - 1, max(i - 5, -1), -1):
                        prev = lines[j]
                        prev_stripped = prev.strip()
                        if not prev_stripped or prev_stripped.startswith('#'):
                            continue
                        # v4.4: 跳过装饰器
                        if prev_stripped.startswith('@'):
                            continue
                        prev_indent = len(prev) - len(prev.lstrip())
                        # v4.4: 必须是相同缩进层级才视为同一块的不可达代码
                        # （if/for 内部的 return 之后，外层代码是可达的）
                        if prev_indent == curr_indent:
                            if re.match(r'(return|break|continue|raise)\b', prev_stripped):
                                if not re.match(r'(else|elif|except|finally|case)\b', stripped):
                                    issues.append((fpath, i + 1, stripped[:50]))
                            break
                        # 如果前一行缩进更大（内层块），继续向前找同层级
                        elif prev_indent > curr_indent:
                            continue
                        else:
                            # 前一行缩进更小，说明已经到了外层，找不到同层级控制语句
                            break

        elif ext in ('.js', '.ts', '.tsx', '.jsx'):
            for i, line in enumerate(lines):
                stripped = line.strip()
                if not stripped or stripped.startswith('//'):
                    continue
                # Check for code after return/throw/break/continue in same block
                if i > 0:
                    for j in range(i - 1, max(i - 3, -1), -1):
                        prev = lines[j].strip()
                        if not prev or prev.startswith('//'):
                            continue
                        # If previous statement ends with return/throw/break/continue
                        if re.match(r'^(return|throw|break|continue)\b', prev) or prev.endswith(';'):
                            if re.search(r'(?:return|throw|break|continue)\s*[^;]*;?\s*$', prev):
                                if not stripped.startswith(('}', 'case', 'default')):
                                    issues.append((fpath, i + 1, stripped[:50]))
                        break

        if len(issues) > 30:
            break

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} {code}"
            for f, l, code in issues[:8]
        )
        results.append({
            'id': 'DEAD-004',
            'name': '不可达代码',
            'level': 'warning',
            'message': f'发现{len(issues)}处不可达代码',
            'detail': detail,
            'file': issues[0][0],
            'line': issues[0][1],
            'fix': '删除return/throw/break/continue后的不可达代码',
        })

    return results


# ===== DEAD-005 注释掉的代码块 =====
def check_dead_005_commented_code(context) -> List[Dict]:
    """DEAD-005 注释掉的代码块 - 大段注释掉的代码(>5行)"""
    results = []
    code_files = context.find_files([".js", ".ts", ".py", ".tsx", ".jsx"])
    issues = []

    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        lines = content.split('\n')
        ext = os.path.splitext(fpath)[1].lower()

        consecutive_comment_lines = 0
        code_like_lines = 0
        start_line = 0

        for i, line in enumerate(lines):
            stripped = line.strip()

            is_comment = False
            looks_like_code = False

            if ext == '.py':
                if stripped.startswith('#'):
                    is_comment = True
                    comment_body = stripped[1:].strip()
                    # Check if comment looks like code
                    if re.match(r'^(def |class |if |for |while |return |import |from |print\(|self\.)', comment_body):
                        looks_like_code = True
                    elif re.match(r'^\w+\s*[=+\-*/]', comment_body):
                        looks_like_code = True
            elif ext in ('.js', '.ts', '.tsx', '.jsx'):
                if stripped.startswith('//'):
                    is_comment = True
                    comment_body = stripped[2:].strip()
                    if re.match(r'^(function |const |let |var |if |for |while |return |import |export |class )', comment_body):
                        looks_like_code = True
                    elif re.match(r'^\w+[\.\(]|//.*[;{}\(\)]', comment_body):
                        looks_like_code = True
                elif stripped.startswith('/*') or stripped.startswith('*'):
                    is_comment = True
                    if re.search(r'[;{}()=]', stripped):
                        looks_like_code = True

            if is_comment:
                if consecutive_comment_lines == 0:
                    start_line = i + 1
                consecutive_comment_lines += 1
                if looks_like_code:
                    code_like_lines += 1
            else:
                # Check if accumulated comments look like commented-out code
                if consecutive_comment_lines > 5 and code_like_lines >= 3:
                    issues.append((fpath, start_line, consecutive_comment_lines))
                consecutive_comment_lines = 0
                code_like_lines = 0

        # Check end of file
        if consecutive_comment_lines > 5 and code_like_lines >= 3:
            issues.append((fpath, start_line, consecutive_comment_lines))

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} {c}行注释代码"
            for f, l, c in issues[:8]
        )
        results.append({
            'id': 'DEAD-005',
            'name': '注释掉的代码块',
            'level': 'info',
            'message': f'发现{len(issues)}处大段注释代码(>5行)',
            'detail': detail,
            'file': issues[0][0],
            'line': issues[0][1],
            'fix': '删除注释掉的代码块，使用版本控制系统(git)保存历史代码',
        })

    return results


# ===== DEAD-006 空的catch块 =====
def check_dead_006_empty_catch(context) -> List[Dict]:
    """DEAD-006 空的catch块 - catch(e) {} 无任何处理"""
    results = []
    code_files = context.find_files([".js", ".ts", ".py", ".tsx", ".jsx"])
    issues = []

    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        ext = os.path.splitext(fpath)[1].lower()
        lines = content.split('\n')

        if ext == '.py':
            for i, line in enumerate(lines):
                stripped = line.strip()
                if re.match(r'except\s*(\w+)?\s*:', stripped):
                    # Check if next non-empty line has different indent
                    has_body = False
                    for j in range(i + 1, min(i + 5, len(lines))):
                        next_line = lines[j]
                        next_stripped = next_line.strip()
                        if not next_stripped:
                            continue
                        curr_indent = len(line) - len(line.lstrip())
                        next_indent = len(next_line) - len(next_line.lstrip())
                        if next_indent > curr_indent:
                            # Has actual body (not just pass)
                            if next_stripped not in ('pass', 'pass  # noqa', '# pass', '# ignore', '# TODO'):
                                has_body = True
                        break
                    if not has_body:
                        issues.append((fpath, i + 1, stripped))

        elif ext in ('.js', '.ts', '.tsx', '.jsx'):
            for i, line in enumerate(lines):
                stripped = line.strip()
                if re.match(r'(?:}\s*)?catch\s*(\([^)]*\))?\s*\{?\s*$', stripped):
                    # Check if catch block is empty
                    brace_count = stripped.count('{') - stripped.count('}')
                    if '{' not in stripped:
                        # Look for opening brace
                        if i + 1 < len(lines) and '{' in lines[i + 1].strip():
                            brace_count = 1
                            check_start = i + 2
                        else:
                            continue
                    else:
                        check_start = i + 1

                    if brace_count > 0:
                        has_body = False
                        for j in range(check_start, min(check_start + 5, len(lines))):
                            next_stripped = lines[j].strip()
                            if not next_stripped:
                                continue
                            if next_stripped == '}':
                                break
                            if next_stripped.startswith('//'):
                                # Comment-only catch
                                break
                            has_body = True
                            break
                        if not has_body:
                            issues.append((fpath, i + 1, stripped))

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} {code}"
            for f, l, code in issues[:8]
        )
        results.append({
            'id': 'DEAD-006',
            'name': '空的catch块',
            'level': 'warning',
            'message': f'发现{len(issues)}个空的catch/except块',
            'detail': detail,
            'file': issues[0][0],
            'line': issues[0][1],
            'fix': '在catch块中添加错误处理逻辑，至少记录日志或使用console.error',
        })

    return results


def _is_todo_in_string(line: str, match_start: int) -> bool:
    """判断TODO匹配位置是否位于字符串字面量内部（引号包裹）"""
    in_single = False
    in_double = False
    in_backtick = False
    i = 0
    while i < match_start:
        ch = line[i]
        # 转义字符跳过下一个
        if ch == '\\' and i + 1 < len(line):
            i += 2
            continue
        if ch == "'" and not in_double and not in_backtick:
            in_single = not in_single
        elif ch == '"' and not in_single and not in_backtick:
            in_double = not in_double
        elif ch == '`' and not in_single and not in_double:
            in_backtick = not in_backtick
        i += 1
    return in_single or in_double or in_backtick


def _is_line_self_referential(line: str) -> bool:
    """判断该行是否是规则代码/检测逻辑的自指（说明TODO是在描述规则本身）"""
    lower = line.lower()
    keywords = ('检测', '规则', 'check', 'rule', 'detect', '规则集',
                'description', '示例', 'example', 'docstring',
                '过滤', '跳过', '排除', 'filter', 'skip', 'exclude',
                '标记', 'marker', '待办', '堆积', 'accumulation')
    # 只有同时包含TODO和规则相关关键词才跳过
    return any(kw in lower for kw in keywords)


def _is_rule_file(fpath: str) -> bool:
    """判断是否是规则代码文件（文件名含_rules），用于自指过滤的安全开关"""
    basename = os.path.basename(fpath).lower()
    return '_rules' in basename or 'rule_' in basename or 'rules' in basename


def _find_docstring_ranges(lines: List[str]) -> List[tuple]:
    """找出Python三重引号docstring的行范围（起止行号，从1开始，闭区间）"""
    ranges = []
    in_doc = False
    start = 0
    for i, line in enumerate(lines):
        # 简单匹配三引号（不考虑转义场景，已足够实用）
        triple_count = line.count('"""') + line.count("'''")
        if triple_count == 0:
            if in_doc:
                continue
        # 奇数个引号表示切换状态
        toggle = 0
        # 逐对统计
        for quote in ('"""', "'''"):
            idx = 0
            while True:
                pos = line.find(quote, idx)
                if pos < 0:
                    break
                # 粗略判断是否在另一种引号内（简化处理）
                toggle += 1
                idx = pos + 3
        if toggle % 2 == 1:
            if not in_doc:
                in_doc = True
                start = i + 1
            else:
                in_doc = False
                ranges.append((start, i + 1))
    return ranges


# ===== DEAD-007 TODO/FIXME堆积 =====
def check_dead_007_todo_accumulation(context) -> List[Dict]:
    """DEAD-007 TODO/FIXME堆积 - TODO/FIXME数量>10
    
    v5.3.0 自指误报修复：
    - 排除docstring三重引号内的TODO（规则说明文档）
    - 排除字符串字面量内部的TODO（示例代码/常量值）
    - 排除规则定义RULES字典行内的TODO
    - 排除同时含"检测/规则/check/rule"等关键词的行（规则代码自描述）
    """
    results = []
    code_files = context.find_files([".js", ".ts", ".py", ".tsx", ".jsx"])
    threshold = context.project_profile.get_adjusted_threshold('todo_threshold', 10)
    todos = []

    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        ext = os.path.splitext(fpath)[1].lower()
        lines = content.split('\n')

        # Python: 先找出docstring范围，用于后续跳过
        docstring_ranges = _find_docstring_ranges(lines) if ext == '.py' else []

        def in_docstring(lineno: int) -> bool:
            for s, e in docstring_ranges:
                if s <= lineno <= e:
                    return True
            return False

        # 识别 RULES = [ ... ] 列表范围（规则元数据，跳过）
        rules_list_range = None
        if ext == '.py':
            depth = 0
            start_line = None
            for i, line in enumerate(lines):
                stripped = line.strip()
                if start_line is None and re.match(r'^RULES\s*=\s*\[', stripped):
                    start_line = i + 1
                    depth = line.count('[') - line.count(']')
                    if depth <= 0:
                        rules_list_range = (start_line, i + 1)
                        break
                elif start_line is not None:
                    depth += line.count('[') - line.count(']')
                    if depth <= 0:
                        rules_list_range = (start_line, i + 1)
                        break

        def in_rules_list(lineno: int) -> bool:
            if rules_list_range is None:
                return False
            return rules_list_range[0] <= lineno <= rules_list_range[1]

        for i, line in enumerate(lines):
            lineno = i + 1
            # 跳过整行注释（纯注释行里的TODO才算待办，但docstring里的不算）
            # 注意：这里保留普通注释行里的TODO，因为它们才是真正的待办
            stripped = line.strip()

            # 跳过docstring中的TODO
            if ext == '.py' and in_docstring(lineno):
                continue

            # 跳过 RULES 定义列表内的TODO（规则元数据）
            if ext == '.py' and in_rules_list(lineno):
                continue

            m = re.search(r'(TODO|FIXME|HACK|XXX|WORKAROUND)\b[:\s]*(.*)', line, re.IGNORECASE)
            if m:
                # 跳过字符串字面量内部的TODO
                if _is_todo_in_string(line, m.start()):
                    continue

                tag = m.group(1).upper()

                # 对 XXX 标记额外检查：如果是小写 xxx 且前面有空格/等号/变量名（是占位符），跳过
                # 例如 "import xxx", "xxx.abc" 中的 xxx 不是待办标记
                if tag == 'XXX' and m.group(1).islower():
                    # 小写xxx大概率是占位符，不是待办
                    continue
                if tag == 'XXX':
                    # 大写XXX也要判断上下文：如果前后是变量名字符（如xxx_method），跳过
                    start = m.start()
                    before = line[start-1] if start > 0 else ''
                    after = line[m.end()] if m.end() < len(line) else ''
                    if before.isalpha() or after.isalpha():
                        # XXX 是变量名的一部分，不是待办标记
                        continue

                # 跳过规则代码自指（行内同时有"检测/规则/check/rule"等词）
                # 只在规则代码文件中启用此过滤，避免正常项目漏报真实TODO
                if ext == '.py' and _is_rule_file(fpath) and _is_line_self_referential(line):
                    continue

                note = m.group(2).strip()[:50]
                todos.append((fpath, lineno, tag, note))

    if len(todos) > threshold:
        # Group by tag
        tag_counts = {}
        for _, _, tag, _ in todos:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

        tag_summary = ', '.join(f"{t}: {c}" for t, c in sorted(tag_counts.items()))
        samples = '\n'.join(
            f"  {os.path.basename(f)}:{l} [{t}] {n}"
            for f, l, t, n in todos[:5]
        )
        results.append({
            'id': 'DEAD-007',
            'name': 'TODO/FIXME堆积',
            'level': 'info',
            'message': f'发现{len(todos)}个待办标记({tag_summary})',
            'detail': samples,
            'file': todos[0][0],
            'line': todos[0][1],
            'fix': '定期清理TODO/FIXME，将重要待办转为任务跟踪',
        })

    return results


# ===== DEAD-008 废弃API使用 =====
def check_dead_008_deprecated_api(context) -> List[Dict]:
    """DEAD-008 废弃API使用 - 使用了已标记@deprecated的函数"""
    results = []
    code_files = context.find_files([".js", ".ts", ".py", ".tsx", ".jsx"])
    issues = []

    # First pass: collect deprecated function names
    deprecated_funcs = set()

    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        # Find @deprecated annotations
        dep_pattern = re.compile(r'@deprecated\s*(?:.*?\n)?\s*(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)|def\s+(\w+))', re.IGNORECASE)
        for m in dep_pattern.finditer(content):
            func_name = m.group(1) or m.group(2) or m.group(3)
            if func_name:
                deprecated_funcs.add(func_name)

        # Also check for /** @deprecated */ JSDoc pattern
        jsdoc_dep = re.compile(r'/\*\*.*?@deprecated.*?\*/\s*(?:async\s+)?(?:function\s+(\w+)|(?:const|let|var)\s+(\w+))', re.DOTALL)
        for m in jsdoc_dep.finditer(content):
            func_name = m.group(1) or m.group(2)
            if func_name:
                deprecated_funcs.add(func_name)

    if not deprecated_funcs:
        return results

    # Second pass: check for usage of deprecated functions
    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        lines = content.split('\n')
        for func_name in deprecated_funcs:
            for i, line in enumerate(lines):
                # Skip the definition/declaration itself
                if re.search(rf'(?:function|def|const|let|var)\s+{re.escape(func_name)}\b', line):
                    continue
                if re.search(rf'@deprecated', line, re.IGNORECASE):
                    continue
                # Check for actual usage
                if re.search(rf'\b{re.escape(func_name)}\s*[\(<]', line):
                    issues.append((fpath, i + 1, func_name))

    if issues:
        # Deduplicate by function name
        seen = set()
        unique_issues = []
        for f, l, n in issues:
            key = f"{f}:{n}"
            if key not in seen:
                seen.add(key)
                unique_issues.append((f, l, n))

        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} 使用了废弃函数 '{n}'"
            for f, l, n in unique_issues[:8]
        )
        results.append({
            'id': 'DEAD-008',
            'name': '废弃API使用',
            'level': 'warning',
            'message': f'发现{len(unique_issues)}处使用已废弃的API',
            'detail': detail,
            'file': issues[0][0],
            'line': issues[0][1],
            'fix': '替换废弃API为新版本API，参考官方迁移文档',
        })

    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'DEAD-001',
        'name': '未使用变量',
        'level': 'warning',
        'category': 'dead_code',
        'module_id': '22',
        'applicable_types': [],
        'description': '检测声明后未读取的变量',
        'check': check_dead_001_unused_variables,
    },
    {
        'id': 'DEAD-002',
        'name': '未使用函数',
        'level': 'warning',
        'category': 'dead_code',
        'module_id': '22',
        'applicable_types': [],
        'description': '检测定义后未调用的函数(排除export)',
        'check': check_dead_002_unused_functions,
    },
    {
        'id': 'DEAD-003',
        'name': '未使用导入',
        'level': 'warning',
        'category': 'dead_code',
        'module_id': '22',
        'applicable_types': [],
        'description': '检测import后未使用的模块',
        'check': check_dead_003_unused_imports,
    },
    {
        'id': 'DEAD-004',
        'name': '不可达代码',
        'level': 'warning',
        'category': 'dead_code',
        'module_id': '22',
        'applicable_types': [],
        'description': '检测return/break/continue后的不可达代码',
        'check': check_dead_004_unreachable_code,
    },
    {
        'id': 'DEAD-005',
        'name': '注释掉的代码块',
        'level': 'info',
        'category': 'dead_code',
        'module_id': '22',
        'applicable_types': [],
        'description': '检测大段注释掉的代码(>5行)',
        'check': check_dead_005_commented_code,
    },
    {
        'id': 'DEAD-006',
        'name': '空的catch块',
        'level': 'warning',
        'category': 'dead_code',
        'module_id': '22',
        'applicable_types': [],
        'description': '检测catch(e) {}无任何处理的空catch块',
        'check': check_dead_006_empty_catch,
    },
    {
        'id': 'DEAD-007',
        'name': 'TODO/FIXME堆积',
        'level': 'info',
        'category': 'dead_code',
        'module_id': '22',
        'applicable_types': [],
        'description': '检测TODO/FIXME数量>10',
        'check': check_dead_007_todo_accumulation,
    },
    {
        'id': 'DEAD-008',
        'name': '废弃API使用',
        'level': 'warning',
        'category': 'dead_code',
        'module_id': '22',
        'applicable_types': [],
        'description': '检测使用了已标记@deprecated的函数',
        'check': check_dead_008_deprecated_api,
    },
]
