"""
代码质量规则集 (M6)
通用代码质量检查 - 适用于所有项目类型
包含: 重复代码、函数过长、命名规范、注释率、魔法数字、TODO追踪等7项检查

v4.4 误报治理:
- 6.6 TODO/FIXME 追踪：跳过注释中的 TODO 示例、docstring、字符串字面量
- 6.5 console.log 残留：跳过字符串内的 console.log 匹配
- 6.4 魔法数字：已跳过字符串内数字，补充 docstring 跳过
"""

import re
import os
from typing import List, Dict, Any

# v4.4: 上下文感知匹配工具
try:
    from core.code_context_utils import (
        find_python_docstring_ranges, find_python_rules_list_range,
        is_line_in_range, search_in_code,
    )
    _HAS_CODE_CONTEXT_UTILS = True
except ImportError:  # noqa: 兼容旧版本
    _HAS_CODE_CONTEXT_UTILS = False


def _get_lang(fpath: str) -> str:
    """根据扩展名获取语言标识"""
    ext = os.path.splitext(fpath)[1].lower()
    if ext == '.py':
        return 'py'
    return 'js'


def _is_todo_in_string(line: str, match_start: int) -> bool:
    """判断TODO匹配位置是否在字符串字面量内"""
    in_single = False
    in_double = False
    i = 0
    while i < match_start:
        ch = line[i]
        if ch == '\\' and i + 1 < len(line):
            i += 2
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        i += 1
    return in_single or in_double


# ===== 6.1 重复代码检测 =====
def check_6_1_duplicate_code(context) -> List[Dict]:
    """6.1 重复代码检测 - 检测代码重复率"""
    results = []
    
    js_files = context.find_files([".js", ".ts", ".py", ".tsx", ".jsx"])
    if len(js_files) < 2:
        return results
    
    # 简化版：统计重复的函数签名
    function_signatures = {}
    threshold = context.project_profile.get_adjusted_threshold('duplicate_similarity', 80)
    
    for fpath in js_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        # 提取函数定义
        func_pattern = re.compile(r'function\s+(\w+)\s*\(|def\s+(\w+)\s*\(|const\s+(\w+)\s*=\s*(?:async\s+)?\(')
        for m in func_pattern.finditer(content):
            func_name = m.group(1) or m.group(2) or m.group(3)
            if not func_name or len(func_name) < 3:
                continue
            if func_name.startswith('_') or func_name in ('main', 'init', 'constructor'):
                continue
            
            if func_name in function_signatures:
                function_signatures[func_name].append(fpath)
            else:
                function_signatures[func_name] = [fpath]
    
    # 找出重复定义的函数（出现在多个文件中且名称相同）
    duplicates = {name: files for name, files in function_signatures.items() if len(files) > 1}
    
    if duplicates:
        dup_count = len(duplicates)
        sample = list(duplicates.items())[:5]
        sample_str = ', '.join(f'{n}({len(f)}个文件)' for n, f in sample)
        results.append({
            'id': '6.1',
            'name': '重复代码检测',
            'level': 'warning',
            'message': f'检测到{dup_count}个可能的重复函数: {sample_str}',
            'detail': f'重复函数可能导致维护困难，建议抽取为公共模块',
            'file': '',
            'line': 0,
            'fix': '将重复代码抽取为公共函数或工具类，统一维护',
        })
    
    return results


# ===== 6.2 函数过长检测 =====
def check_6_2_long_functions(context) -> List[Dict]:
    """6.2 函数过长检测 - 检测超长函数"""
    results = []
    
    code_files = context.find_files([".js", ".ts", ".py", ".tsx", ".jsx"])
    
    max_lines = context.project_profile.get_adjusted_threshold('function_lines', 80)
    long_functions = []
    
    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        lines = content.split('\n')
        
        # Python函数检测
        if fpath.endswith('.py'):
            func_pattern = re.compile(r'^(\s*)def\s+(\w+)\s*\(')
            current_func = None
            func_start = 0
            base_indent = 0
            
            for i, line in enumerate(lines):
                m = func_pattern.match(line)
                if m:
                    # 结束上一个函数
                    if current_func:
                        func_len = i - func_start
                        if func_len > max_lines:
                            long_functions.append((fpath, current_func, func_start + 1, func_len))
                    
                    current_func = m.group(2)
                    func_start = i
                    base_indent = len(m.group(1))
                elif current_func and line.strip() and not line.strip().startswith('#'):
                    current_indent = len(line) - len(line.lstrip())
                    if current_indent <= base_indent and not line.strip().startswith('@'):
                        # 函数结束
                        func_len = i - func_start
                        if func_len > max_lines:
                            long_functions.append((fpath, current_func, func_start + 1, func_len))
                        current_func = None
            
            # 处理最后一个函数
            if current_func:
                func_len = len(lines) - func_start
                if func_len > max_lines:
                    long_functions.append((fpath, current_func, func_start + 1, func_len))
        
        # JS/TS函数检测
        else:
            # 简化版：统计函数
            pass
    
    if long_functions:
        worst = sorted(long_functions, key=lambda x: x[3], reverse=True)[:10]
        results.append({
            'id': '6.2',
            'name': '函数过长检测',
            'level': 'warning',
            'message': f'发现{len(long_functions)}个超长函数(>{max_lines}行)',
            'detail': '最长的10个: ' + ', '.join(f'{os.path.basename(f)}:{n}({l}行)' for f, n, s, l in worst),
            'file': long_functions[0][0] if long_functions else '',
            'line': long_functions[0][2] if long_functions else 0,
            'fix': '将长函数拆分为多个小函数，每个函数只做一件事',
        })
    
    return results


# ===== 6.3 命名规范检测 =====
def check_6_3_naming_convention(context) -> List[Dict]:
    """6.3 命名规范检测 - 检查变量/函数命名是否规范"""
    results = []
    
    code_files = context.find_files([".js", ".ts", ".py"])
    if not code_files:
        return results
    
    # 检查Python命名规范
    py_bad_names = []
    js_bad_names = []
    
    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        if fpath.endswith('.py'):
            # Python: 检查是否有驼峰命名的函数/变量
            camel_case_funcs = re.findall(r'def\s+([a-z]+[A-Z][a-zA-Z0-9_]*)\s*\(', content)
            if camel_case_funcs:
                py_bad_names.append((fpath, len(camel_case_funcs), camel_case_funcs[:5]))
        else:
            # JS: 检查是否有蛇形命名的函数
            snake_funcs = re.findall(r'function\s+([a-zA-Z]+_[a-zA-Z0-9_]+)\s*\(', content)
            if snake_funcs:
                js_bad_names.append((fpath, len(snake_funcs), snake_funcs[:5]))
    
    total_bad = sum(x[1] for x in py_bad_names) + sum(x[1] for x in js_bad_names)
    
    if total_bad > 10:
        results.append({
            'id': '6.3',
            'name': '命名规范检测',
            'level': 'warning',
            'message': f'发现{total_bad}处命名不规范(Python应使用蛇形，JS应使用驼峰)',
            'file': '',
            'line': 0,
            'fix': '统一命名规范：Python使用snake_case，JS使用camelCase',
        })
    
    return results


# ===== 6.6 TODO/FIXME追踪 =====
def check_6_6_todo_tracking(context) -> List[Dict]:
    """6.6 TODO/FIXME追踪 - 统计待办事项

    v4.4 误报治理:
    - 跳过注释行（纯注释行的 TODO 才是真实待办，但 docstring 里的不是）
    - 跳过 Python docstring 三重引号内的 TODO（文档/说明）
    - 跳过字符串字面量内部的 TODO（占位符/示例）
    - 跳过规则文件 RULES 定义列表（自指）
    - 小写 xxx 作为占位符不视为待办标记
    """
    results = []

    code_files = context.find_files([".js", ".ts", ".py", ".tsx", ".jsx", ".wxml"])
    if not code_files:
        return results

    todo_count = 0
    fixme_count = 0
    hack_count = 0
    todo_samples = []

    # TODO 标记正则（带单词边界）
    todo_pat = re.compile(r'(TODO)\s*[:：]?\s*(.+)', re.IGNORECASE)
    fixme_pat = re.compile(r'(FIXME)\s*[:：]?\s*(.+)', re.IGNORECASE)
    hack_pat = re.compile(r'(HACK)\s*[:：]?\s*(.+)', re.IGNORECASE)

    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        lines = content.split('\n')
        lang = _get_lang(fpath)

        # v4.4: 预计算跳过范围
        docstring_ranges = []
        rules_list_range = None
        if lang == 'py' and _HAS_CODE_CONTEXT_UTILS:
            docstring_ranges = find_python_docstring_ranges(lines)
            rules_list_range = find_python_rules_list_range(lines)

        def _is_skip_line(lineno: int) -> bool:
            if docstring_ranges and is_line_in_range(lineno, docstring_ranges):
                return True
            if rules_list_range and rules_list_range[0] <= lineno <= rules_list_range[1]:
                return True
            return False

        def _count_todos(pattern, line, lineno):
            """统计一行中的待办标记，排除字符串内的"""
            count = 0
            samples = []
            for m in pattern.finditer(line):
                # 跳过字符串内的
                if _is_todo_in_string(line, m.start()):
                    continue
                # 跳过小写 xxx（占位符）
                tag = m.group(1)
                if tag.lower() == 'xxx':
                    # 只有大写 XXX 才是待办标记
                    if tag != 'XXX':
                        continue
                # 检查标识符边界（避免匹配到变量名中间）
                start = m.start()
                before = line[start-1] if start > 0 else ''
                after = line[m.end()] if m.end() < len(line) else ''
                if (before and (before.isalnum() or before == '_')) or \
                   (after and (after.isalnum() or after == '_')):
                    continue
                count += 1
                if len(samples) < 3:
                    samples.append((lineno, m.group(2)[:50]))
            return count, samples

        file_todo_samples = []

        for i, line in enumerate(lines):
            lineno = i + 1
            stripped = line.strip()

            # 跳过空行
            if not stripped:
                continue

            # 跳过 docstring / RULES 列表
            if _is_skip_line(lineno):
                continue

            # 跳过纯代码行（非注释行不统计 TODO，只有注释里的才算待办）
            # 但是保留行尾注释中的 TODO
            is_comment_line = (
                stripped.startswith('#') or
                stripped.startswith('//') or
                stripped.startswith('/*') or
                stripped.startswith('*')
            )

            # v4.4: 只统计注释行中的 TODO（代码中的 TODO 大概率是字符串或变量名）
            # 但也需要检查行尾注释
            if not is_comment_line:
                # 检查行内注释
                comment_start = None
                if lang == 'py':
                    # 找 # 位置（不在字符串内）
                    in_single = False
                    in_double = False
                    for j, ch in enumerate(line):
                        if ch == '\\' and j + 1 < len(line):
                            continue
                        if ch == "'" and not in_double:
                            in_single = not in_single
                        elif ch == '"' and not in_single:
                            in_double = not in_double
                        elif ch == '#' and not in_single and not in_double:
                            comment_start = j
                            break
                else:
                    # JS: 找 // 位置
                    in_single = False
                    in_double = False
                    in_backtick = False
                    for j, ch in enumerate(line):
                        if ch == '\\' and j + 1 < len(line):
                            continue
                        if ch == "'" and not in_double and not in_backtick:
                            in_single = not in_single
                        elif ch == '"' and not in_single and not in_backtick:
                            in_double = not in_double
                        elif ch == '`' and not in_single and not in_double:
                            in_backtick = not in_backtick
                        elif ch == '/' and j + 1 < len(line) and line[j+1] == '/' and not in_single and not in_double and not in_backtick:
                            comment_start = j
                            break

                if comment_start is None:
                    continue
                # 只检查注释部分
                comment_part = line[comment_start:]
            else:
                comment_part = line

            # 统计 TODO
            cnt, samps = _count_todos(todo_pat, comment_part, lineno)
            todo_count += cnt
            for ln, txt in samps:
                if len(file_todo_samples) < 3:
                    file_todo_samples.append((os.path.basename(fpath), txt))

            # 统计 FIXME
            cnt, _ = _count_todos(fixme_pat, comment_part, lineno)
            fixme_count += cnt

            # 统计 HACK
            cnt, _ = _count_todos(hack_pat, comment_part, lineno)
            hack_count += cnt

        todo_samples.extend(file_todo_samples[:3])

    total = todo_count + fixme_count + hack_count
    if total > 0:
        sample_str = ''
        if todo_samples:
            sample_str = '示例: ' + '; '.join(f'{f}: {t}' for f, t in todo_samples[:5])

        level = 'warning' if fixme_count > 3 else 'info'

        results.append({
            'id': '6.6',
            'name': 'TODO/FIXME追踪',
            'level': level,
            'message': f'共{total}个待办: TODO({todo_count}) FIXME({fixme_count}) HACK({hack_count})',
            'detail': sample_str,
            'file': '',
            'line': 0,
            'fix': '及时清理已完成的TODO，规划FIXME的修复时间',
        })

    return results


# ===== 6.7 代码注释率 =====
def check_6_7_comment_ratio(context) -> List[Dict]:
    """6.7 代码注释率 - 检查代码注释比例"""
    results = []
    
    code_files = context.find_files([".js", ".ts", ".py"])
    if not code_files:
        return results
    
    total_lines = 0
    comment_lines = 0
    low_comment_files = []
    
    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        file_lines = 0
        file_comments = 0
        
        if fpath.endswith('.py'):
            for line in content.split('\n'):
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped.startswith('#'):
                    file_comments += 1
                file_lines += 1
        else:
            # JS/TS: 统计//注释
            for line in content.split('\n'):
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*'):
                    file_comments += 1
                file_lines += 1
        
        total_lines += file_lines
        comment_lines += file_comments
        
        if file_lines > 100:
            ratio = file_comments / file_lines
            if ratio < 0.05:
                low_comment_files.append((fpath, ratio, file_lines))
    
    if low_comment_files:
        results.append({
            'id': '6.7',
            'name': '代码注释率',
            'level': 'warning',
            'message': f'{len(low_comment_files)}个文件注释率低于5%',
            'detail': '注释率过低可能导致维护困难',
            'file': '',
            'line': 0,
            'fix': '为核心逻辑添加必要的注释，特别是复杂算法和业务逻辑',
        })
    
    return results


# ===== 6.4 魔法数字检测 =====
def check_6_4_magic_numbers(context) -> List[Dict]:
    """6.4 魔法数字检测 - 检查代码中的硬编码魔法数字

    v2.1 优化降噪：
    - 扩大白名单：常见端口、年份、HTTP状态码、颜色值等
    - 排除配置文件（*.json, *.yaml, *.yml, *.toml, *.env）
    - 排除测试文件（test_*, *_test.*, *.spec.*, *.test.*）
    - 排除数组索引、range()参数、循环计数器
    - 排除常量定义行（UPPER_CASE = value）
    - 排除字符串中的数字（引号内的内容）
    - 每个文件最多报3个，总共最多报15个

    v4.4 误报治理:
    - 跳过 Python docstring 三重引号内的数字（文档/示例中的数字）
    - 跳过规则文件 RULES 定义列表（自指元数据）
    """
    results = []

    code_files = context.find_files([".js", ".ts", ".py", ".tsx", ".jsx"])
    if not code_files:
        return results

    magic_numbers = []

    # 扩展白名单：常见的合理数字
    whitelist = {
        # 基础数字
        0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16,
        20, 24, 30, 32, 40, 48, 50, 60, 64, 80, 100, 128,
        # 2的幂次
        255, 256, 512, 1000, 1024, 2048, 4096, 8192, 16384, 32768, 65536,
        # 时间相关
        3600, 86400, 60000, 3600000,
        # HTTP状态码
        200, 201, 204, 300, 301, 302, 304, 400, 401, 403, 404, 405, 500, 502, 503, 504,
        # 常见端口
        80, 443, 8080, 8443, 3000, 3306, 5432, 6379, 27017, 9200,
        # 常见年份范围
        2020, 2021, 2022, 2023, 2024, 2025, 2026, 2027, 2028, 2029, 2030,
        # 常见颜色值
        16777215,  # #FFFFFF
        # 常见进制
        36, 100, 255,
        # 其他常见
        11, 17, 19, 23, 29, 31,
        42, 59, 99,
        120, 150, 180, 360, 720, 900,
        1500, 2000, 3000, 5000, 10000, 30000,
        100000, 999999,
    }

    # 排除的文件扩展名（配置文件）
    _SKIP_EXTS = {'.json', '.yaml', '.yml', '.toml', '.env', '.cfg', '.ini', '.conf'}
    # 排除的文件名模式
    _SKIP_FILENAMES = {
        "api.js", "util.js", "utils.js", "security.js", "constants.js",
        "config.js", "settings.js", "constants.py", "config.py", "settings.py",
        "enums.py", "enum.py", "types.py",
    }

    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        basename = os.path.basename(fpath)
        _, ext = os.path.splitext(fpath)

        # 跳过配置文件
        if ext.lower() in _SKIP_EXTS:
            continue

        # 跳过工具类和常量文件
        if basename.lower() in _SKIP_FILENAMES:
            continue

        # 跳过测试文件
        if any(p in fpath for p in ['test_', '_test.', '.test.', '.spec.', '/tests/', '/__tests__/']):
            continue

        lines = content.split('\n')
        lang = _get_lang(fpath)

        # v4.4: 预计算跳过范围
        docstring_ranges = []
        rules_list_range = None
        if lang == 'py' and _HAS_CODE_CONTEXT_UTILS:
            docstring_ranges = find_python_docstring_ranges(lines)
            rules_list_range = find_python_rules_list_range(lines)

        def _is_skip_line(lineno: int) -> bool:
            if docstring_ranges and is_line_in_range(lineno, docstring_ranges):
                return True
            if rules_list_range and rules_list_range[0] <= lineno <= rules_list_range[1]:
                return True
            return False

        file_magic_count = 0
        MAX_PER_FILE = 3

        for i, line in enumerate(lines, 1):
            if file_magic_count >= MAX_PER_FILE:
                break

            # v4.4: 跳过 docstring / RULES 列表
            if _is_skip_line(i):
                continue

            stripped = line.strip()
            # 跳过注释行
            if stripped.startswith(('//', '#', '/*', '*')):
                continue
            # 跳过 import/require 行
            if stripped.startswith(('import ', 'require(', 'from ', '@')):
                continue
            # 跳过常量定义行（UPPER_CASE = value）
            if re.match(r'^\s*(?:const|let|var|final|static|readonly)?\s*[A-Z_][A-Z_0-9]*\s*=', stripped):
                continue
            # 跳过 enum/type 定义
            if re.match(r'^\s*(?:enum|type|interface)\s+', stripped):
                continue

            # 先移除字符串内容（避免匹配字符串中的数字）
            cleaned_line = re.sub(r'"[^"]*"', '""', line)
            cleaned_line = re.sub(r"'[^']*'", "''", cleaned_line)
            cleaned_line = re.sub(r'`[^`]*`', '``', cleaned_line)

            # 匹配数字（3位及以上）
            for m in re.finditer(r'(?<!\w)(\d{3,})(?!\w)', cleaned_line):
                val = int(m.group(1))
                if val in whitelist:
                    continue

                # 排除数组索引（前面有 [ ）
                prefix = cleaned_line[:m.start()].rstrip()
                if prefix.endswith('['):
                    continue

                # 排除 range()/Array(n)/new Array 等构造函数参数
                if re.search(r'(?:range|Array|Buffer|setTimeout|setInterval)\s*\(\s*' + str(val), cleaned_line[:m.start()+len(str(val))+5]):
                    continue

                # 排除端口绑定（listen(3000), port=5432 等）
                if re.search(r'(?:port|listen|bind|connect)\s*[\(=]\s*' + str(val), cleaned_line, re.IGNORECASE):
                    continue

                magic_numbers.append(f"{os.path.relpath(fpath, context.project_path) if context.project_path else fpath}:{i} 数字{val}")
                file_magic_count += 1
                if len(magic_numbers) >= 15:
                    break
            if len(magic_numbers) >= 15:
                break

    if magic_numbers:
        results.append({
            'id': '6.4',
            'name': '魔法数字检测',
            'level': 'info',
            'message': f"发现 {len(magic_numbers)} 处硬编码数字（可能需提取为常量）",
            'detail': "\n".join(magic_numbers[:10]),
            'file': '',
            'line': 0,
            'fix': '将业务相关的硬编码数字提取为命名常量，提升可读性和可维护性',
        })

    return results


# ===== 6.5 console.log残留检测 =====
def check_6_5_console_log(context) -> List[Dict]:
    """6.5 console.log残留检测 - 检查生产代码中是否有console.log等调试日志

    v1.20.1 修复：
    - 排除日志工具/封装文件（logger.js, log.js, debug.js, util/log* 等）
    - 如果console.log在函数封装内部（日志工具封装），跳过该文件

    v4.4 误报治理:
    - 跳过字符串字面量内部的 console.log 匹配（如注释/消息文本中提到）
    - 跳过注释行
    """
    results = []

    js_files = context.find_files([".js", ".ts", ".tsx", ".jsx"])
    if not js_files:
        return results

    # v1.20.1: 日志工具文件名排除列表
    log_util_filenames = {
        'logger.js', 'logger.ts', 'log.js', 'log.ts',
        'debug.js', 'debug.ts', 'logging.js', 'logging.ts',
        'log-util.js', 'log-util.ts', 'log_utils.js', 'log_utils.ts',
        'logHelper.js', 'logHelper.ts', 'log-helper.js', 'log-helper.ts',
    }

    # v1.20.1: 日志工具目录模式
    log_util_dir_patterns = [
        '/util/log', '/utils/log', '/lib/log',
        '/util/logger', '/utils/logger', '/lib/logger',
        '/log/', '/logging/',
    ]

    console_logs = []
    # v4.4: 编译正则
    console_pat = re.compile(r'console\.(log|debug|info)\s*\(')

    for fpath in js_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        # 跳过测试文件
        basename = os.path.basename(fpath)
        if '.test.' in basename or '.spec.' in basename or basename.startswith('test_'):
            continue

        # v1.20.1 修复：跳过日志工具/封装文件
        if basename in log_util_filenames:
            continue

        # v1.20.1 修复：跳过日志工具目录下的文件
        norm_path = fpath.replace(os.sep, '/')
        if any(pattern in norm_path for pattern in log_util_dir_patterns):
            continue

        # v1.20.1 修复：如果文件中包含日志封装模式（如导出logger、封装console等），
        # 则认为是日志工具文件，跳过
        if _is_log_wrapper_file(content):
            continue

        lines = content.split('\n')
        lang = _get_lang(fpath)
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            # 跳过注释行
            if stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*'):
                continue
            # v4.4: 只在纯代码部分匹配（跳过字符串内的 console.log）
            if _HAS_CODE_CONTEXT_UTILS:
                m = search_in_code(line, console_pat, lang)
                if m:
                    console_logs.append(f"{os.path.relpath(fpath, context.project_path) if context.project_path else fpath}:{i}")
            else:
                if console_pat.search(line):
                    console_logs.append(f"{os.path.relpath(fpath, context.project_path) if context.project_path else fpath}:{i}")
            if len(console_logs) >= 50:
                break
        if len(console_logs) >= 50:
            break

    if console_logs:
        results.append({
            'id': '6.5',
            'name': 'console.log残留检测',
            'level': 'warning',
            'message': f"发现 {len(console_logs)} 处console.log调试日志残留",
            'detail': "\n".join(console_logs[:10]),
            'file': '',
            'line': 0,
            'fix': '生产环境移除调试日志，使用条件编译或统一的日志框架管理',
        })

    return results


def _is_log_wrapper_file(content: str) -> bool:
    """判断文件是否为日志封装/工具文件
    
    v1.20.1: 如果文件中包含日志封装模式，则认为是日志工具文件，
    其中的console.log是封装逻辑而非调试残留。
    """
    # 检查是否包含日志封装特征
    wrapper_patterns = [
        r'export\s+(?:default\s+)?(?:class|function|const)\s+\w*[Ll]ogger',
        r'export\s+(?:default\s+)?(?:class|function|const)\s+\w*[Ll]og(?:Utils|Helper|Service)',
        r'module\.exports\s*=\s*\{[^}]*\b(?:log|debug|info|warn|error)\b',
        r'(?:const|let|var)\s+logger\s*=',
        r'(?:const|let|var)\s+\w*[Ll]og\s*=\s*(?:wx\.getLog|console)',
    ]
    
    match_count = 0
    for pattern in wrapper_patterns:
        if re.search(pattern, content, re.IGNORECASE):
            match_count += 1
    
    # 如果有2个以上封装特征，认为是日志工具文件
    return match_count >= 2


# ===== 规则定义列表 =====
RULES = [
    {
        'id': '6.1',
        'name': '重复代码检测',
        'level': 'suggestion',
        'category': 'code_quality',
        'module_id': '6',
        'applicable_types': [],
        'description': '检测代码重复率，找出重复的函数定义',
        'check': check_6_1_duplicate_code,
    },
    {
        'id': '6.2',
        'name': '函数过长检测',
        'level': 'suggestion',
        'category': 'code_quality',
        'module_id': '6',
        'applicable_types': [],
        'description': '检测超长函数，函数过长影响可读性和可维护性',
        'check': check_6_2_long_functions,
    },
    {
        'id': '6.3',
        'name': '命名规范检测',
        'level': 'suggestion',
        'category': 'code_quality',
        'module_id': '6',
        'applicable_types': [],
        'description': '检查变量/函数命名是否符合语言规范',
        'check': check_6_3_naming_convention,
    },
    {
        'id': '6.4',
        'name': '魔法数字检测',
        'level': 'suggestion',
        'category': 'code_quality',
        'module_id': '6',
        'applicable_types': [],
        'description': '检查代码中的硬编码魔法数字，建议提取为命名常量',
        'check': check_6_4_magic_numbers,
    },
    {
        'id': '6.5',
        'name': 'console.log残留检测',
        'level': 'problem',
        'category': 'code_quality',
        'module_id': '6',
        'applicable_types': [],
        'description': '检查生产代码中是否有console.log等调试日志残留',
        'check': check_6_5_console_log,
    },
    {
        'id': '6.6',
        'name': 'TODO/FIXME追踪',
        'level': 'suggestion',
        'category': 'code_quality',
        'module_id': '6',
        'applicable_types': [],
        'description': '统计代码中的TODO、FIXME、HACK等待办事项',
        'check': check_6_6_todo_tracking,
    },
    {
        'id': '6.7',
        'name': '代码注释率',
        'level': 'suggestion',
        'category': 'code_quality',
        'module_id': '6',
        'applicable_types': [],
        'description': '检查代码注释比例，确保代码可维护性',
        'check': check_6_7_comment_ratio,
    },
]
