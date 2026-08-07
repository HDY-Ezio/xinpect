"""
魔法数字与字面量检测规则集 (v5.2.0)
检测硬编码字面量问题 - 适用于所有项目类型
包含: 硬编码数字、硬编码URL、硬编码颜色值、重复字面量等4项检查
"""

import re
import os
from typing import List, Dict, Any
from collections import defaultdict


def _is_match_in_string(line: str, match_start: int) -> bool:
    """判断匹配位置是否位于字符串字面量内部（单/双/反引号包裹）"""
    in_single = False
    in_double = False
    in_backtick = False
    i = 0
    while i < match_start:
        ch = line[i]
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


def _find_python_docstring_ranges(lines: List[str]) -> List[tuple]:
    """找出Python三重引号docstring的行范围（闭区间）"""
    ranges = []
    in_doc = False
    start = 0
    for i, line in enumerate(lines):
        toggle = 0
        for quote in ('"""', "'''"):
            idx = 0
            while True:
                pos = line.find(quote, idx)
                if pos < 0:
                    break
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


def _find_python_rules_list_range(lines: List[str]) -> tuple:
    """找出 RULES = [ ... ] 列表定义的行范围（闭区间），不存在返回None"""
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
            depth += line.count('[') - line.count(']')
            if depth <= 0:
                return (start_line, i + 1)
    return None


# ===== MAGIC-001 硬编码数字 =====
def check_magic_001_hardcoded_numbers(context) -> List[Dict]:
    """MAGIC-001 硬编码数字 - 非0/1/-1的数字字面量应提取为常量
    
    v2.1 优化降噪：
    - 大幅扩展白名单（常见端口、状态码、年份、2的幂次等）
    - 排除配置文件和测试文件
    - 排除数组索引、循环计数器
    - 排除常量定义行
    - 排除字符串中的数字
    - 总共最多报15个
    
    v5.3.0 自指误报修复：
    - 跳过 Python docstring 三重引号内的示例数字
    - 跳过 RULES 定义列表中的元数据字符串/数字
    - 字符串中的数字已通过 cleaned_line 移除
    """
    results = []
    code_files = context.find_files([".js", ".ts", ".py", ".tsx", ".jsx"])
    
    # 扩展白名单
    allowed = {
        0, 1, -1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16,
        20, 24, 30, 32, 40, 48, 50, 60, 64, 80, 99, 100, 120, 128,
        150, 180, 200, 255, 256, 360, 512, 720, 900,
        1000, 1024, 1500, 2000, 2048, 3000, 3600, 4096, 5000,
        8080, 8192, 8443, 10000, 16384, 30000, 32768, 60000, 65536,
        86400, 100000, 999999,
        # v2.9.1: 动画/延迟/UI时序常见值
        100, 200, 250, 300, 350, 400, 450, 500, 600, 700, 800, 900,
        1200, 1500, 1800, 2500, 3500, 4000, 5000, 8000, 10000,
        # 常见业务数字
        50, 75, 150, 250, 500, 750, 999,
        # HTTP 状态码
        201, 204, 300, 301, 302, 304, 400, 401, 403, 404, 405,
        500, 502, 503, 504,
        # 常见端口
        443, 3306, 5432, 6379, 9200, 27017,
        # 年份
        2020, 2021, 2022, 2023, 2024, 2025, 2026, 2027, 2028, 2029, 2030,
        # 毫秒
        60000, 3600000,
    }

    # 排除的文件名模式
    _SKIP_FILENAMES = {
        'config', 'constant', 'enum', 'setting', 'type',
        'api.', 'util', 'logger',
    }

    issues = []

    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        basename = os.path.basename(fpath).lower()
        
        # 跳过配置/常量/测试文件
        if any(kw in basename for kw in _SKIP_FILENAMES):
            continue
        if any(p in fpath for p in ['test_', '_test.', '.test.', '.spec.', '/tests/', '/__tests__/']):
            continue

        lines = content.split('\n')
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('#') or stripped.startswith('*'):
                continue
            # Skip constant definitions
            if re.match(r'^(const|final|readonly|static)\s+[A-Z_]+', stripped):
                continue
            if re.match(r'^[A-Z_]+\s*=', stripped):
                continue
            # Skip enum/type definitions
            if re.match(r'^\s*(enum|type|interface)\s+', stripped):
                continue
            # Skip array indices, loop counters, etc.
            if re.search(r'\[\d+\]', stripped):
                continue
            if re.search(r'(for|while|range)\b.*\d+', stripped):
                continue

            # 先移除字符串内容
            cleaned_line = re.sub(r'"[^"]*"', '""', line)
            cleaned_line = re.sub(r"'[^']*'", "''", cleaned_line)
            cleaned_line = re.sub(r'`[^`]*`', '``', cleaned_line)

            # Find numeric literals
            numbers = re.finditer(r'(?<!\w)(-?\d+\.?\d*)(?!\w)(?!\s*[=:]\s*[A-Za-z_]\w*\s*;)', cleaned_line)
            for m in numbers:
                try:
                    num = float(m.group(1))
                    if num not in allowed and num != int(num):
                        # Floating point that's not in whitelist
                        # Only report if it looks truly "magic" (not a common fraction/percentage)
                        abs_num = abs(num)
                        if abs_num < 0.001 or abs_num > 1e9:
                            continue  # Skip extremely small/large numbers (likely scientific notation)
                        issues.append((fpath, i + 1, m.group(1), stripped[:50]))
                    elif num not in allowed:
                        int_num = int(num)
                        if int_num not in allowed and abs(int_num) > 16:
                            issues.append((fpath, i + 1, m.group(1), stripped[:50]))
                except ValueError:
                    continue

        if len(issues) > 15:
            break

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} 数字 {n}"
            for f, l, n, _ in issues[:8]
        )
        results.append({
            'id': 'MAGIC-001',
            'name': '硬编码数字',
            'level': 'info',
            'message': f'发现{len(issues)}个硬编码数字字面量',
            'detail': detail,
            'file': issues[0][0],
            'line': issues[0][1],
            'fix': '将魔法数字提取为命名常量，如 const MAX_RETRY = 3',
        })

    return results


# ===== MAGIC-002 硬编码URL =====
def check_magic_002_hardcoded_urls(context) -> List[Dict]:
    """MAGIC-002 硬编码URL - URL应提取为配置
    
    v5.3.0 自指误报修复：
    - 跳过 Python docstring 三重引号内的示例URL
    - 跳过 RULES 定义列表中的元数据字符串
    - 跳过字符串字面量内部的匹配（docstring示例/注释里的URL）
    """
    results = []
    code_files = context.find_files([".js", ".ts", ".py", ".tsx", ".jsx"])
    issues = []

    url_pattern = re.compile(
        r"""(?:https?://|www\.)[^\s"'`<>{}\[\]\\^~|]+""",
        re.IGNORECASE
    )

    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        # Skip config files
        basename = os.path.basename(fpath).lower()
        if any(kw in basename for kw in ('config', 'env', 'setting', '.json')):
            continue

        ext = os.path.splitext(fpath)[1].lower()
        lines = content.split('\n')

        # Python: 计算docstring和RULES列表范围
        docstring_ranges = _find_python_docstring_ranges(lines) if ext == '.py' else []
        rules_list_range = _find_python_rules_list_range(lines) if ext == '.py' else None

        def in_skip_range(lineno: int) -> bool:
            if ext != '.py':
                return False
            for s, e in docstring_ranges:
                if s <= lineno <= e:
                    return True
            if rules_list_range and rules_list_range[0] <= lineno <= rules_list_range[1]:
                return True
            return False

        for i, line in enumerate(lines):
            lineno = i + 1
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('#') or stripped.startswith('*'):
                continue
            # Skip import statements
            if stripped.startswith('import ') or stripped.startswith('from '):
                continue
            # Skip constant definitions
            if re.match(r'^(const|final|readonly)\s+[A-Z_]+', stripped):
                continue
            # Skip docstring / RULES 列表（规则文件自指）
            if in_skip_range(lineno):
                continue

            for m in url_pattern.finditer(line):
                url = m.group(0)
                # Skip common utility URLs
                if any(skip in url.lower() for skip in (
                    'schema.org', 'xmlsoap', 'w3.org', 'mozilla.org',
                    'github.com', 'npmjs.com', 'pypi.org',
                    'localhost', '127.0.0.1', 'example.com',
                )):
                    continue
                issues.append((fpath, i + 1, url[:50]))

        if len(issues) > 30:
            break

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} {u}"
            for f, l, u in issues[:8]
        )
        results.append({
            'id': 'MAGIC-002',
            'name': '硬编码URL',
            'level': 'info',
            'message': f'发现{len(issues)}处硬编码URL',
            'detail': detail,
            'file': issues[0][0],
            'line': issues[0][1],
            'fix': '将URL提取到配置文件或环境变量中，便于切换环境',
        })

    return results


# ===== MAGIC-003 硬编码颜色值 =====
def check_magic_003_hardcoded_colors(context) -> List[Dict]:
    """MAGIC-003 硬编码颜色值 - 颜色值应使用CSS变量或常量"""
    results = []
    css_files = context.find_files([".css", ".scss", ".less", ".wxss"])
    js_files = context.find_files([".js", ".ts", ".tsx", ".jsx", ".vue"])
    issues = []

    # Color patterns
    hex_color = re.compile(r'#[0-9a-fA-F]{3,8}\b')
    rgb_color = re.compile(r'rgba?\s*\(\s*\d+\s*,\s*\d+\s*,\s*\d+')
    hsl_color = re.compile(r'hsla?\s*\(\s*\d+')

    for fpath in css_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        basename = os.path.basename(fpath).lower()
        if 'variable' in basename or 'theme' in basename:
            continue

        lines = content.split('\n')
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*'):
                continue
            # Check for hardcoded colors
            if hex_color.search(line) or rgb_color.search(line) or hsl_color.search(line):
                # Skip CSS variable definitions
                if re.search(r'--\w+\s*:', line):
                    continue
                issues.append((fpath, i + 1, stripped[:50]))

        if len(issues) > 30:
            break

    # Also check JS/TS files for inline color values
    for fpath in js_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        lines = content.split('\n')
        for i, line in enumerate(lines):
            # Look for color values in style objects
            if re.search(r"""(?:color|background|border|fill|stroke)\s*[:=]\s*['"]\s*#[0-9a-fA-F]{3,8}""", line):
                issues.append((fpath, i + 1, line.strip()[:50]))

        if len(issues) > 50:
            break

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} {code}"
            for f, l, code in issues[:8]
        )
        results.append({
            'id': 'MAGIC-003',
            'name': '硬编码颜色值',
            'level': 'info',
            'message': f'发现{len(issues)}处硬编码颜色值',
            'detail': detail,
            'file': issues[0][0],
            'line': issues[0][1],
            'fix': '使用CSS变量(--primary-color)或设计系统Token统一管理颜色',
        })

    return results


# ===== MAGIC-004 重复字面量 =====
def check_magic_004_repeated_literals(context) -> List[Dict]:
    """MAGIC-004 重复字面量 - 相同字面量出现>2次
    
    v5.3.0 自指误报修复：
    - 跳过 Python docstring 三重引号内的示例字符串
    - 跳过 RULES 定义列表中的元数据字符串
    """
    results = []
    code_files = context.find_files([".js", ".ts", ".py", ".tsx", ".jsx"])
    threshold = 2
    min_length = 4
    literal_count = defaultdict(list)

    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        ext = os.path.splitext(fpath)[1].lower()
        lines = content.split('\n')

        # Python: 计算docstring和RULES列表范围
        docstring_ranges = _find_python_docstring_ranges(lines) if ext == '.py' else []
        rules_list_range = _find_python_rules_list_range(lines) if ext == '.py' else None

        def in_skip_range(lineno: int) -> bool:
            if ext != '.py':
                return False
            for s, e in docstring_ranges:
                if s <= lineno <= e:
                    return True
            if rules_list_range and rules_list_range[0] <= lineno <= rules_list_range[1]:
                return True
            return False

        for i, line in enumerate(lines):
            lineno = i + 1
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('#') or stripped.startswith('*'):
                continue
            if stripped.startswith('import ') or stripped.startswith('from '):
                continue
            # 跳过docstring / RULES 列表（规则文件自指）
            if in_skip_range(lineno):
                continue

            # Find string literals
            for m in re.finditer(r"""(?:"([^"\\]{4,})"|'([^'\\]{4,})')""", line):
                val = m.group(1) or m.group(2)
                if val and len(val) >= min_length:
                    # Skip common utility strings
                    if val.lower() in ('true', 'false', 'null', 'undefined', 'none',
                                      'error', 'success', 'warning', 'info'):
                        continue
                    if val.startswith('http') or val.startswith('/') or val.startswith('.'):
                        continue
                    literal_count[val].append((fpath, i + 1))

    # Find literals appearing more than threshold times
    duplicates = {lit: locs for lit, locs in literal_count.items() if len(locs) > threshold}

    if duplicates:
        sorted_dups = sorted(duplicates.items(), key=lambda x: len(x[1]), reverse=True)
        samples = sorted_dups[:5]
        detail = '\n'.join(
            f'  "{s[:25]}" 出现{len(locs)}次'
            for s, locs in samples
        )
        results.append({
            'id': 'MAGIC-004',
            'name': '重复字面量',
            'level': 'info',
            'message': f'发现{len(duplicates)}个重复字面量(>{threshold}次)',
            'detail': detail,
            'file': '',
            'line': 0,
            'fix': '将重复字面量提取为常量，提高可维护性',
        })

    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'MAGIC-001',
        'name': '硬编码数字',
        'level': 'info',
        'category': 'magic_literal',
        'module_id': '24',
        'applicable_types': [],
        'description': '非0/1/-1的数字字面量应提取为常量',
        'check': check_magic_001_hardcoded_numbers,
    },
    {
        'id': 'MAGIC-002',
        'name': '硬编码URL',
        'level': 'info',
        'category': 'magic_literal',
        'module_id': '24',
        'applicable_types': [],
        'description': 'URL应提取为配置，避免硬编码',
        'check': check_magic_002_hardcoded_urls,
    },
    {
        'id': 'MAGIC-003',
        'name': '硬编码颜色值',
        'level': 'info',
        'category': 'magic_literal',
        'module_id': '24',
        'applicable_types': [],
        'description': '颜色值应使用CSS变量或设计Token',
        'check': check_magic_003_hardcoded_colors,
    },
    {
        'id': 'MAGIC-004',
        'name': '重复字面量',
        'level': 'info',
        'category': 'magic_literal',
        'module_id': '24',
        'applicable_types': [],
        'description': '相同字面量出现>2次应提取为常量',
        'check': check_magic_004_repeated_literals,
    },
]
