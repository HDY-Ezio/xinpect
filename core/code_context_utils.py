# -*- coding: utf-8 -*-
"""
煋鉴 v4.4 误报治理辅助工具 - 上下文感知匹配

提供跳过字符串字面量、注释、docstring 的行级匹配工具函数，
供所有基于字符串/regex 的规则使用，系统性降低误报率。

策略：
1. strip_code_line(line, lang) - 移除注释、字符串后返回纯代码内容
2. find_code_occurrences(line, pattern, lang) - 在纯代码部分查找模式
3. is_in_string(line, pos) - 判断位置是否在字符串内
4. remove_comments(line, lang) - 移除行内/行尾注释
5. find_python_docstring_ranges(lines) - 找出 Python 三重引号 docstring 范围
6. find_python_rules_list_range(lines) - 找出 RULES = [...] 列表范围（规则文件自指）
7. find_python_class_func_ranges(lines) - 找出 class/def 缩进范围，用于模块级判断

v4.4 新增:
- 支持 Python/JS/TS 多语言
- 支持单行字符串、三引号 docstring、单行注释、多行注释
- 提供 is_identifier_boundary 确保标识符边界匹配
"""

import re
from typing import List, Tuple, Optional, Match, Iterator


# ======================================================================
# 基础工具：判断位置是否在字符串字面量内
# ======================================================================

def is_in_string(line: str, pos: int, lang: str = 'py') -> bool:
    """判断 line 中 pos 位置是否位于字符串字面量内部。

    支持单引号、双引号、反引号；支持转义字符。
    对于三引号字符串，建议使用更上层的 docstring range 判断。

    Args:
        line: 单行代码
        pos: 字符位置
        lang: 'py' | 'js' | 'ts' | 'tsx' | 'jsx'

    Returns:
        True 表示该位置在字符串字面量内部
    """
    if pos >= len(line):
        return False

    in_single = False
    in_double = False
    in_backtick = False if lang == 'py' else False  # Python无模板字符串

    i = 0
    while i < pos:
        ch = line[i]

        # 转义字符跳过下一个
        if ch == '\\' and i + 1 < len(line):
            i += 2
            continue

        # 处理三引号（Python）：粗略处理 — 只要遇到三个连续引号就切换
        if lang == 'py' and i + 2 < len(line) and line[i:i+3] in ('"""', "'''"):
            # 三引号切换只影响对应类型
            if line[i:i+3] == '"""' and not in_single:
                in_double = not in_double
            elif line[i:i+3] == "'''" and not in_double:
                in_single = not in_single
            i += 3
            continue

        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif not in_single and not in_double and ch == '`' and lang != 'py':
            in_backtick = not in_backtick

        i += 1

    return in_single or in_double or in_backtick


# ======================================================================
# 基础工具：移除行内注释（保留代码部分）
# ======================================================================

def remove_inline_comment(line: str, lang: str = 'py') -> str:
    """移除行尾注释，保留代码部分。

    Args:
        line: 单行代码
        lang: 'py' | 'js' | 'ts' | 'tsx' | 'jsx'

    Returns:
        移除注释后的代码行
    """
    if lang == 'py':
        # Python: # 开头的注释
        # 需要排除字符串内部的 #
        in_single = False
        in_double = False
        in_backtick = False
        for i, ch in enumerate(line):
            if ch == '\\' and i + 1 < len(line):
                continue
            # 三引号
            if i + 2 < len(line) and line[i:i+3] in ('"""', "'''"):
                if line[i:i+3] == '"""' and not in_single:
                    in_double = not in_double
                elif line[i:i+3] == "'''" and not in_double:
                    in_single = not in_single
                continue
            if ch == "'" and not in_double and not in_backtick:
                in_single = not in_single
            elif ch == '"' and not in_single and not in_backtick:
                in_double = not in_double
            elif ch == '#' and not in_single and not in_double:
                return line[:i].rstrip()
        return line
    else:
        # JS/TS: // 开头的行内注释
        in_single = False
        in_double = False
        in_backtick = False
        for i, ch in enumerate(line):
            if ch == '\\' and i + 1 < len(line):
                continue
            if ch == "'" and not in_double and not in_backtick:
                in_single = not in_single
            elif ch == '"' and not in_single and not in_backtick:
                in_double = not in_double
            elif ch == '`' and not in_single and not in_double:
                in_backtick = not in_backtick
            elif ch == '/' and i + 1 < len(line) and line[i+1] == '/' and not in_single and not in_double and not in_backtick:
                return line[:i].rstrip()
        return line


# ======================================================================
# 综合工具：提取纯代码行（移注释 + 移字符串）
# ======================================================================

def extract_code_content(line: str, lang: str = 'py') -> str:
    """提取一行中的纯代码内容：移除注释和字符串字面量。

    字符串字面量替换为对应的空引号，保留位置信息（用于 match 起始位置回算）。
    注释部分直接移除。

    Args:
        line: 单行代码
        lang: 'py' | 'js' | 'ts' | 'tsx' | 'jsx'

    Returns:
        纯代码内容，字符串字面量被替换为空引号
    """
    # 先移除注释
    code = remove_inline_comment(line, lang)

    # 再移除字符串内容（保留引号外壳）
    result = []
    in_single = False
    in_double = False
    in_backtick = False
    i = 0
    while i < len(code):
        ch = code[i]

        # 三引号处理（Python）
        if lang == 'py' and i + 2 < len(code) and code[i:i+3] in ('"""', "'''"):
            quote = code[i:i+3]
            if quote == '"""' and not in_single:
                if in_double:
                    # 结束
                    result.append(quote)
                    in_double = False
                else:
                    # 开始
                    result.append(quote)
                    in_double = True
                i += 3
                continue
            elif quote == "'''" and not in_double:
                if in_single:
                    result.append(quote)
                    in_single = False
                else:
                    result.append(quote)
                    in_single = True
                i += 3
                continue

        if ch == '\\' and i + 1 < len(code):
            if in_single or in_double or in_backtick:
                # 跳过转义（字符串内的转义字符，不输出）
                i += 2
                continue
            # 代码中的转义（少见，保留）
            result.append(ch)
            i += 1
            continue

        if ch == "'" and not in_double and not in_backtick:
            in_single = not in_single
            result.append(ch)
        elif ch == '"' and not in_single and not in_backtick:
            in_double = not in_double
            result.append(ch)
        elif ch == '`' and not in_single and not in_double and lang != 'py':
            in_backtick = not in_backtick
            result.append(ch)
        elif in_single or in_double or in_backtick:
            # 字符串内部的字符，跳过（不输出）
            pass
        else:
            result.append(ch)
        i += 1

    return ''.join(result)


# ======================================================================
# 正则匹配工具：在纯代码中查找模式
# ======================================================================

def finditer_in_code(line: str, pattern: re.Pattern, lang: str = 'py') -> Iterator[Match]:
    """在一行的纯代码部分（排除注释和字符串）中查找正则匹配。

    用法：替代 re.finditer(pattern, line) 调用。

    Args:
        line: 单行代码
        pattern: 编译后的正则表达式
        lang: 'py' | 'js' | 'ts' | 'tsx' | 'jsx'

    Yields:
        re.Match 对象（匹配位置相对于原始 line）
    """
    # 提取纯代码（字符串替换为空引号，注释移除）
    code_line = extract_code_content(line, lang)

    # 在纯代码中查找
    for m in pattern.finditer(code_line):
        # 由于我们保持了引号外壳，位置基本对应原始位置
        # 需要验证：该位置在原始行中不在字符串内
        original_pos = m.start()
        if original_pos < len(line) and not is_in_string(line, original_pos, lang):
            # 返回一个新的匹配对象，使用原始 line 的位置
            # 简化：由于引号外壳保留，起始位置基本一致
            # 直接在原始 line 上从该位置重新匹配
            orig_match = pattern.search(line, original_pos, original_pos + len(m.group(0)) + 10)
            if orig_match and not is_in_string(line, orig_match.start(), lang):
                yield orig_match


def search_in_code(line: str, pattern: re.Pattern, lang: str = 'py') -> Optional[Match]:
    """在一行的纯代码部分查找第一个匹配。

    Args:
        line: 单行代码
        pattern: 编译后的正则表达式
        lang: 'py' | 'js' | 'ts' | 'tsx' | 'jsx'

    Returns:
        第一个 Match 对象，或 None
    """
    for m in finditer_in_code(line, pattern, lang):
        return m
    return None


# ======================================================================
# 标识符边界匹配
# ======================================================================

def is_identifier_boundary(text: str, start: int, end: int) -> bool:
    """判断 match 位置是否是完整标识符边界（不是另一个标识符的一部分）。

    Args:
        text: 原始文本
        start: 匹配起始位置
        end: 匹配结束位置

    Returns:
        True 表示是完整标识符
    """
    before = text[start - 1] if start > 0 else ''
    after = text[end] if end < len(text) else ''
    # 前后都不是字母、数字、下划线
    before_ok = not before or not (before.isalnum() or before == '_')
    after_ok = not after or not (after.isalnum() or after == '_')
    return before_ok and after_ok


# ======================================================================
# Python 多行范围工具
# ======================================================================

def find_python_docstring_ranges(lines: List[str]) -> List[Tuple[int, int]]:
    """找出 Python 三重引号 docstring 的行范围（1-based，闭区间）。

    Args:
        lines: 代码行列表

    Returns:
        [(start_line, end_line), ...]  行号从1开始
    """
    ranges = []
    in_doc = False
    start = 0
    quote_type = None  # '"""' 或 "'''"

    for i, line in enumerate(lines):
        # 跳过注释行里的三引号
        stripped = line.strip()
        if stripped.startswith('#'):
            continue

        # 统计三引号数量
        pos = 0
        toggles = 0
        # 简化：逐对找三引号
        for quote in ('"""', "'''"):
            idx = 0
            while True:
                p = line.find(quote, idx)
                if p < 0:
                    break
                # 检查前面是否有转义
                if p > 0 and line[p-1] == '\\':
                    idx = p + 3
                    continue
                toggles += 1
                idx = p + 3

        if toggles % 2 == 1:
            if not in_doc:
                in_doc = True
                start = i + 1  # 包含起始行
            else:
                in_doc = False
                ranges.append((start, i + 1))  # 包含结束行

    return ranges


def find_python_rules_list_range(lines: List[str]) -> Optional[Tuple[int, int]]:
    """找出 RULES = [ ... ] 列表定义的行范围（1-based，闭区间）。

    用于规则文件自指过滤 — 规则元数据中的字符串不应触发检测。

    Args:
        lines: 代码行列表

    Returns:
        (start_line, end_line) 或 None
    """
    depth = 0
    start_line = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if start_line is None and re.match(r'^RULES\s*=\s*\[', stripped):
            start_line = i + 1
            depth = line.count('[') - line.count(']')
            if depth <= 0:
                return (start_line, i + 1)
        elif start_line is not None:
            # 需要考虑字符串中的 [ ]
            # 简化：直接计数
            depth += line.count('[') - line.count(']')
            if depth <= 0:
                return (start_line, i + 1)
    return None


def is_line_in_range(lineno: int, ranges: List[Tuple[int, int]]) -> bool:
    """判断行号是否在任何一个范围内。

    Args:
        lineno: 1-based 行号
        ranges: [(start, end), ...] 1-based 闭区间

    Returns:
        True 表示在范围内
    """
    for s, e in ranges:
        if s <= lineno <= e:
            return True
    return False


# ======================================================================
# 便捷函数：Python 文件级跳过范围构建器
# ======================================================================

def build_python_skip_ranges(lines: List[str]) -> dict:
    """为 Python 文件构建所有需要跳过的范围。

    返回:
        {
            'docstring_ranges': [(start, end), ...],
            'rules_list_range': (start, end) or None,
        }
    """
    return {
        'docstring_ranges': find_python_docstring_ranges(lines),
        'rules_list_range': find_python_rules_list_range(lines),
    }


def is_skippable_python_line(lineno: int, skip_info: dict) -> bool:
    """判断 Python 行号是否在所有跳过范围内。

    Args:
        lineno: 1-based 行号
        skip_info: build_python_skip_ranges 的返回值

    Returns:
        True 表示该行应跳过
    """
    docstring_ranges = skip_info.get('docstring_ranges', [])
    if is_line_in_range(lineno, docstring_ranges):
        return True
    rules_range = skip_info.get('rules_list_range')
    if rules_range and rules_range[0] <= lineno <= rules_range[1]:
        return True
    return False
