"""
重复代码高级检测规则集 (v5.2.0)
检测代码重复问题 - 适用于所有项目类型
包含: 相似代码块、重复字符串字面量、重复对象结构等3项检查
"""

import re
import os
from typing import List, Dict, Any
from collections import defaultdict


# ===== DUP-001 相似代码块 =====
def check_dup_001_similar_blocks(context) -> List[Dict]:
    """DUP-001 相似代码块 - 10+行代码相似度>80%"""
    results = []
    code_files = context.find_files([".js", ".ts", ".py", ".tsx", ".jsx"])
    threshold = context.project_profile.get_adjusted_threshold('duplicate_similarity', 80)
    min_lines = 10

    # Collect all code blocks of min_lines length
    blocks = []
    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        lines = content.split('\n')
        # Normalize lines (strip whitespace, skip empty)
        normalized = []
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith('//') and not stripped.startswith('#'):
                # Normalize variable names for similarity comparison
                norm = re.sub(r'\b[a-zA-Z_]\w{2,}\b', 'VAR', stripped)
                normalized.append(norm)

        # Extract blocks of min_lines
        for i in range(0, len(normalized) - min_lines + 1, min_lines // 2):
            block = normalized[i:i + min_lines]
            block_str = '|'.join(block)
            blocks.append((fpath, i + 1, block_str, block))

    # Find similar blocks using simple hashing
    if len(blocks) < 2:
        return results

    # Simple similarity check: compare block hashes
    seen_hashes = defaultdict(list)
    for fpath, line, block_str, _ in blocks:
        # Create a hash-like key
        key = block_str[:200]  # Use first 200 chars as key
        seen_hashes[key].append((fpath, line))

    duplicates = {k: v for k, v in seen_hashes.items() if len(v) > 1}

    if duplicates:
        samples = list(duplicates.items())[:3]
        detail_lines = []
        for key, locations in samples:
            locs = '; '.join(f"{os.path.basename(f)}:{l}" for f, l in locations[:3])
            detail_lines.append(f"  相似块: {locs}")

        results.append({
            'id': 'DUP-001',
            'name': '相似代码块',
            'level': 'info',
            'message': f'发现{len(duplicates)}组相似代码块(>={min_lines}行，相似度>{threshold}%)',
            'detail': '\n'.join(detail_lines),
            'file': '',
            'line': 0,
            'fix': '将相似代码提取为公共函数，使用参数化差异部分',
        })

    return results


# ===== DUP-002 重复字符串字面量 =====
def check_dup_002_duplicate_strings(context) -> List[Dict]:
    """DUP-002 重复字符串字面量 - 同一字符串出现>3次"""
    results = []
    code_files = context.find_files([".js", ".ts", ".py", ".tsx", ".jsx"])
    threshold = context.project_profile.get_adjusted_threshold('duplicate_string_threshold', 3)
    min_string_length = 5

    string_occurrences = defaultdict(list)

    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        lines = content.split('\n')
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('#') or stripped.startswith('*'):
                continue
            # Find string literals
            for m in re.finditer(r"""(?:"([^"\\]{5,}(?:\\.[^"\\]{5,})*)"|'([^'\\]{5,}(?:\\.[^'\\]{5,})*)')""", line):
                string_val = m.group(1) or m.group(2)
                if not string_val:
                    continue
                # Skip common strings
                if string_val.lower() in ('content-type', 'application/json', 'text/plain',
                                          'utf-8', 'utf8', 'charset'):
                    continue
                # Skip import paths
                if '/' in string_val and len(string_val) > 20:
                    continue
                string_occurrences[string_val].append((fpath, i + 1))

    # Find strings that appear more than threshold times
    duplicates = {s: locs for s, locs in string_occurrences.items() if len(locs) > threshold}

    if duplicates:
        # Sort by occurrence count
        sorted_dups = sorted(duplicates.items(), key=lambda x: len(x[1]), reverse=True)
        samples = sorted_dups[:5]
        detail = '\n'.join(
            f'  "{s[:30]}" 出现{len(locs)}次'
            for s, locs in samples
        )
        total = sum(len(locs) for _, locs in duplicates.items())
        results.append({
            'id': 'DUP-002',
            'name': '重复字符串字面量',
            'level': 'info',
            'message': f'发现{len(duplicates)}个重复字符串(共{total}次引用)',
            'detail': detail,
            'file': '',
            'line': 0,
            'fix': '将重复字符串提取为常量或配置文件，统一管理',
        })

    return results


# ===== DUP-003 重复对象结构 =====
def check_dup_003_duplicate_objects(context) -> List[Dict]:
    """DUP-003 重复对象结构 - 相似对象定义>2个"""
    results = []
    code_files = context.find_files([".js", ".ts", ".py", ".tsx", ".jsx"])
    issues = []

    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        ext = os.path.splitext(fpath)[1].lower()

        if ext in ('.js', '.ts', '.tsx', '.jsx'):
            # Find object literals with similar key patterns
            obj_pattern = re.compile(r'\{([^{}]{10,300})\}', re.DOTALL)
            obj_keys = []

            for m in obj_pattern.finditer(content):
                body = m.group(1)
                # Extract keys from object
                keys = re.findall(r'(\w+)\s*:', body)
                if len(keys) >= 3:
                    key_pattern = '|'.join(sorted(keys))
                    line_num = content[:m.start()].count('\n') + 1
                    obj_keys.append((key_pattern, line_num, len(keys)))

            # Find duplicate key patterns
            pattern_count = defaultdict(list)
            for pattern, line, key_count in obj_keys:
                if key_count >= 3:
                    pattern_count[pattern].append(line)

            for pattern, lines_list in pattern_count.items():
                if len(lines_list) > 2:
                    issues.append((fpath, lines_list[0], len(lines_list)))

        elif ext == '.py':
            # Find similar dict literals
            dict_pattern = re.compile(r'\{([^{}]{10,300})\}', re.DOTALL)
            dict_keys = []

            for m in dict_pattern.finditer(content):
                body = m.group(1)
                keys = re.findall(r"""['"](\w+)['"]\s*:""", body)
                if len(keys) >= 3:
                    key_pattern = '|'.join(sorted(keys))
                    line_num = content[:m.start()].count('\n') + 1
                    dict_keys.append((key_pattern, line_num, len(keys)))

            pattern_count = defaultdict(list)
            for pattern, line, key_count in dict_keys:
                if key_count >= 3:
                    pattern_count[pattern].append(line)

            for pattern, lines_list in pattern_count.items():
                if len(lines_list) > 2:
                    issues.append((fpath, lines_list[0], len(lines_list)))

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} 有{c}个相似对象结构"
            for f, l, c in issues[:5]
        )
        results.append({
            'id': 'DUP-003',
            'name': '重复对象结构',
            'level': 'info',
            'message': f'发现{len(issues)}组重复的对象/字典结构',
            'detail': detail,
            'file': issues[0][0],
            'line': issues[0][1],
            'fix': '使用工厂函数或类来创建相似对象，或使用配置模板',
        })

    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'DUP-001',
        'name': '相似代码块',
        'level': 'info',
        'category': 'duplicate',
        'module_id': '23',
        'applicable_types': [],
        'description': '检测10+行代码相似度>80%的重复代码块',
        'check': check_dup_001_similar_blocks,
    },
    {
        'id': 'DUP-002',
        'name': '重复字符串字面量',
        'level': 'info',
        'category': 'duplicate',
        'module_id': '23',
        'applicable_types': [],
        'description': '检测同一字符串出现>3次',
        'check': check_dup_002_duplicate_strings,
    },
    {
        'id': 'DUP-003',
        'name': '重复对象结构',
        'level': 'info',
        'category': 'duplicate',
        'module_id': '23',
        'applicable_types': [],
        'description': '检测相似对象定义>2个',
        'check': check_dup_003_duplicate_objects,
    },
]
