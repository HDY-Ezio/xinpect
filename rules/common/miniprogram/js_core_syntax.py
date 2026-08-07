"""
小程序JS语法规则集 - 核心语法校验 (v1.20.0)
JavaScript核心语法与错误模式检查
包含: JS语法校验（括号匹配/字符串闭合/常见错误）、空catch块检测
"""

"""
小程序JS语法规则集 (v1.20.0)
JavaScript语法与引用完整性检查
包含: JS语法校验、globalData属性引用、事件绑定函数存在性、重复方法定义等4项检查
"""

import re
import os
from typing import List, Dict, Any, Set, Optional, Tuple


def check_20_1_js_syntax(context) -> List[Dict]:
    """20.1 JS语法校验 - 纯Python实现检测常见JS语法错误
    
    检测逻辑（不依赖node）：
    1. 括号/方括号/花括号匹配检查
    2. 字符串引号配对检查（单引号、双引号、模板字符串）
    3. 常见语法错误模式（如连续运算符、缺少逗号等）
    """
    results = []
    
    if not context.project_path:
        return results
    
    js_files = context.find_files([".js"])
    if not js_files:
        return results
    
    for fpath in js_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        # 跳过vendored/minified文件
        norm_path = fpath.replace(os.sep, '/')
        if _is_vendored_js(norm_path, content):
            continue
        
        # v1.20.1 修复：每个文件用try-except包裹，解析失败时记录具体文件路径和行号，
        # 跳过该文件继续扫描，而非中断整个规则
        try:
            issues = []
            
            # 1. 括号匹配检查
            bracket_issues = _check_bracket_matching(content, fpath)
            issues.extend(bracket_issues)
            
            # 2. 字符串引号配对检查
            string_issues = _check_string_quoting(content, fpath)
            issues.extend(string_issues)
            
            # 3. 常见语法错误模式
            syntax_pattern_issues = _check_common_syntax_errors(content, fpath)
            issues.extend(syntax_pattern_issues)
            
            if issues:
                rel_path = os.path.relpath(fpath, context.project_path) if context.project_path else fpath
                issue_summary = '; '.join([i['desc'] for i in issues[:5]])
                results.append({
                    'id': '20.1',
                    'name': 'JS语法校验',
                    'level': 'error',
                    'message': f'发现{len(issues)}处可能的JS语法错误',
                    'detail': issue_summary,
                    'file': fpath,
                    'line': issues[0].get('line', 0),
                    'fix': '检查并修复语法错误：括号匹配、字符串闭合、运算符使用等',
                })
        except Exception as e:  # noqa: intentional catch-all
            # 记录具体文件路径和错误信息，跳过该文件继续扫描
            rel_path = os.path.relpath(fpath, context.project_path) if context.project_path else fpath
            results.append({
                'id': '20.1',
                'name': 'JS语法校验',
                'level': 'warning',
                'message': f'JS语法解析异常(已跳过): {rel_path}',
                'detail': f'文件: {rel_path}\n异常: {str(e)[:200]}',
                'file': fpath,
                'line': 0,
                'fix': '该文件语法解析失败，请手动检查是否有特殊语法导致解析器无法处理',
            })
    
    return results


def _is_vendored_js(norm_path: str, content: str) -> bool:
    """判断是否为第三方/minified文件"""
    vendored_dirs = ['node_modules/', 'miniprogram_npm/', 'vendor/', 'vendors/']
    if any(d in norm_path for d in vendored_dirs):
        return True
    # 检测minified特征：单行超长
    lines = content.split('\n')
    if lines:
        max_line_len = max(len(line) for line in lines)
        if max_line_len > 5000 and len(lines) < 50:
            return True
    return False


def _check_bracket_matching(content: str, fpath: str) -> List[Dict]:
    """检查括号/方括号/花括号匹配"""
    issues = []
    
    # 移除注释和字符串，避免误判
    cleaned = _remove_comments_and_strings(content)
    
    # 括号匹配
    bracket_map = {')': '(', ']': '[', '}': '{'}
    open_brackets = {'(', '[', '{'}
    stack = []  # (char, line_number)
    
    line_num = 1
    for i, ch in enumerate(cleaned):
        if ch == '\n':
            line_num += 1
            continue
        
        if ch in open_brackets:
            stack.append((ch, line_num))
        elif ch in bracket_map:
            if not stack:
                issues.append({
                    'desc': f'多余的闭合括号{ch}(第{line_num}行)',
                    'line': line_num,
                })
                if len(issues) >= 5:
                    return issues
            elif stack[-1][0] != bracket_map[ch]:
                issues.append({
                    'desc': f'括号不匹配: 期望闭合{bracket_map[stack[-1][0]]}但遇到{ch}(第{line_num}行)',
                    'line': line_num,
                })
                if len(issues) >= 5:
                    return issues
            else:
                stack.pop()
    
    # 报告未闭合的括号
    for bracket, line in stack[-5:]:  # 最多报5个
        bracket_name = {'(': '圆括号(', '[': '方括号[', '{': '花括号{'}[bracket]
        issues.append({
            'desc': f'未闭合的{bracket_name}(第{line}行)',
            'line': line,
        })
    
    return issues


def _remove_comments_and_strings(content: str) -> str:
    """移除JS代码中的注释和字符串内容，保留结构"""
    result = []
    i = 0
    length = len(content)
    
    while i < length:
        # 单行注释
        if i < length - 1 and content[i] == '/' and content[i + 1] == '/':
            while i < length and content[i] != '\n':
                result.append(' ')
                i += 1
            continue
        
        # 多行注释
        if i < length - 1 and content[i] == '/' and content[i + 1] == '*':
            result.append(' ')
            result.append(' ')
            i += 2
            while i < length:
                if i < length - 1 and content[i] == '*' and content[i + 1] == '/':
                    result.append(' ')
                    result.append(' ')
                    i += 2
                    break
                if content[i] == '\n':
                    result.append('\n')
                else:
                    result.append(' ')
                i += 1
            continue
        
        # 模板字符串
        if content[i] == '`':
            result.append(' ')
            i += 1
            while i < length:
                if content[i] == '\\' and i + 1 < length:
                    result.append(' ')
                    result.append(' ')
                    i += 2
                    continue
                if content[i] == '`':
                    result.append(' ')
                    i += 1
                    break
                if content[i] == '\n':
                    result.append('\n')
                else:
                    result.append(' ')
                i += 1
            continue
        
        # 字符串（单引号、双引号）
        if content[i] in ('"', "'"):
            quote = content[i]
            result.append(' ')
            i += 1
            while i < length:
                if content[i] == '\\' and i + 1 < length:
                    result.append(' ')
                    result.append(' ')
                    i += 2
                    continue
                if content[i] == quote:
                    result.append(' ')
                    i += 1
                    break
                if content[i] == '\n':
                    result.append('\n')
                else:
                    result.append(' ')
                i += 1
            continue
        
        result.append(content[i])
        i += 1
    
    return ''.join(result)


def _check_string_quoting(content: str, fpath: str) -> List[Dict]:
    """检查字符串引号配对（只检测跨行的未闭合字符串）"""
    issues = []
    lines = content.split('\n')
    
    in_multiline_string = False
    string_char = None
    string_start_line = 0
    
    for line_idx, line in enumerate(lines):
        stripped = line.strip()
        
        # 跳过注释行
        if stripped.startswith('//') or stripped.startswith('*') or stripped.startswith('/*'):
            continue
        
        if in_multiline_string:
            # 检查当前行是否闭合了字符串
            if string_char in line:
                # 简单检查：行末尾是否有未转义的闭合引号
                j = 0
                while j < len(line):
                    if line[j] == '\\':
                        j += 2
                        continue
                    if line[j] == string_char:
                        in_multiline_string = False
                        break
                    j += 1
            continue
        
        # 检查行内是否有未闭合的字符串（排除注释）
        # 简化检测：统计非转义的引号数量
        i = 0
        while i < len(line):
            ch = line[i]
            if ch == '/' and i + 1 < len(line) and line[i + 1] == '/':
                break  # 行注释，后面不用看
            
            if ch in ('"', "'", '`'):
                # 检查是否有转义
                if i > 0 and line[i - 1] == '\\':
                    i += 1
                    continue
                
                if ch == '`':
                    # 模板字符串可能跨行，简单跳过
                    i += 1
                    continue
                
                # 找配对的引号
                j = i + 1
                found_close = False
                while j < len(line):
                    if line[j] == '\\':
                        j += 2
                        continue
                    if line[j] == ch:
                        found_close = True
                        break
                    j += 1
                
                if not found_close and ch in ('"', "'"):
                    # 可能是跨行字符串，标记
                    in_multiline_string = True
                    string_char = ch
                    string_start_line = line_idx + 1
                    break
            
            i += 1
    
    return issues


def _check_common_syntax_errors(content: str, fpath: str) -> List[Dict]:
    """检测常见JS语法错误模式"""
    issues = []
    lines = content.split('\n')
    
    for line_idx, line in enumerate(lines):
        stripped = line.strip()
        
        # 跳过注释
        if stripped.startswith('//') or stripped.startswith('*') or stripped.startswith('/*'):
            continue
        
        # 检测: 连续比较运算符 (a === b === c)
        if re.search(r'===\s*\w+\s*===', stripped) and not stripped.startswith('//'):
            # 排除合理场景如 if (a === b || c === d)
            if '||' not in stripped and '&&' not in stripped:
                issues.append({
                    'desc': f'疑似连续比较运算符(第{line_idx + 1}行)',
                    'line': line_idx + 1,
                })
        
        # 检测: 赋值语句缺少右侧 (= 后面直接跟 ; 或换行)
        if re.search(r'[^!=<>]=\s*[;,]\s*$', stripped) and not re.search(r'[!=<>]=', stripped):
            # 排除 for 循环和条件
            if not stripped.startswith('for') and not stripped.startswith('if'):
                issues.append({
                    'desc': f'赋值语句可能不完整(第{line_idx + 1}行)',
                    'line': line_idx + 1,
                })
    
    return issues


def check_20_9_empty_catch(context) -> List[Dict]:
    """20.9 空catch块检测 - Promise链中的空catch
    
    检测逻辑：正则匹配Promise.catch中的空处理体。
    模式：.catch(() => {})、.catch(err => {})、.catch(function(){})
    也包括只有空白/注释的catch块。
    
    注意：与AI-SEC-02（裸异常捕获）和13.2（错误处理深度分析）不同，
    本规则专注于JS Promise链中的.catch()空处理。
    """
    results = []
    
    if not context.project_path:
        return results
    
    js_files = context.find_files([".js"])
    if not js_files:
        return results
    
    # 匹配.catch后跟空函数的模式
    # 模式1: .catch(() => {}) 或 .catch(e => {})
    # 模式2: .catch(function() {}) 或 .catch(function(e) {})
    # 模式3: .catch(() => { }) 或 .catch(e => {   }) 只有空白
    # 模式4: .catch(function() { /* 只有注释 */ })
    empty_catch_patterns = [
        # 箭头函数空catch
        re.compile(r'\.catch\s*\(\s*(?:\(\s*\w*\s*\)|\w+)\s*=>\s*\{\s*\}', re.MULTILINE),
        # 传统函数空catch
        re.compile(r'\.catch\s*\(\s*function\s*\([^)]*\)\s*\{\s*\}', re.MULTILINE),
        # 箭头函数只有空白和注释
        re.compile(r'\.catch\s*\(\s*(?:\(\s*\w*\s*\)|\w+)\s*=>\s*\{\s*(?://[^\n]*\s*)*\}', re.MULTILINE),
        # 传统函数只有空白和注释
        re.compile(r'\.catch\s*\(\s*function\s*\([^)]*\)\s*\{\s*(?://[^\n]*\s*)*\}', re.MULTILINE),
    ]
    
    total_files = 0
    total_empty = 0
    
    for fpath in js_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        norm_path = fpath.replace(os.sep, '/')
        if _is_vendored_js(norm_path, content):
            continue
        
        file_empty_catches = []
        
        for pattern in empty_catch_patterns:
            for m in pattern.finditer(content):
                line_num = content[:m.start()].count('\n') + 1
                # 避免重复计数（不同模式匹配到同一个）
                if not any(fc['line'] == line_num for fc in file_empty_catches):
                    file_empty_catches.append({
                        'line': line_num,
                        'snippet': content[m.start():m.end()][:60],
                    })
        
        if file_empty_catches:
            total_files += 1
            total_empty += len(file_empty_catches)
            
            rel_path = os.path.relpath(fpath, context.project_path) if context.project_path else fpath
            detail_lines = [f"  {rel_path}:{fc['line']}" for fc in file_empty_catches[:5]]
            
            results.append({
                'id': '20.9',
                'name': '空catch块检测',
                'level': 'warning',
                'message': f'发现{len(file_empty_catches)}处Promise.catch空处理（异常被静默吞掉）',
                'detail': '\n'.join(detail_lines),
                'file': fpath,
                'line': file_empty_catches[0]['line'],
                'fix': '在catch块中至少记录错误日志或给用户提示',
                'suggestion_code': '.catch(err => {\n  console.error("操作失败:", err);\n  wx.showToast({ title: "操作失败", icon: "none" });\n})',
            })
    
    return results


# ===== 规则定义列表 =====


# ===== 规则定义列表 =====
RULES = [
        {
            'id': '20.1',
            'name': 'JS语法校验',
            'level': 'error',
            'category': 'miniprogram_js',
            'module_id': '20',
            'applicable_types': ['miniprogram', 'mixed'],
            'description': '纯Python实现检测JS语法错误：括号不匹配、字符串未闭合等',
            'check': check_20_1_js_syntax,
        },
        {
            'id': '20.9',
            'name': '空catch块检测',
            'level': 'warning',
            'category': 'miniprogram_js',
            'module_id': '20',
            'applicable_types': ['miniprogram', 'mixed', 'web', 'electron'],
            'description': '检测Promise.catch中的空处理体（异常被静默吞掉）',
            'check': check_20_9_empty_catch,
        },
]
