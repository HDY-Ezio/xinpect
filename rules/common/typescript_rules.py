"""
TypeScript规范规则集 (v5.2.0)
检测TypeScript代码规范问题 - 适用于含TypeScript的项目
包含: any类型滥用、接口命名、泛型约束、类型断言、可选链、空值合并等6项检查
"""

import re
import os
from typing import List, Dict, Any


# ===== TS-001 any类型滥用 =====
def check_ts_001_any_abuse(context) -> List[Dict]:
    """TS-001 any类型滥用 - any使用次数>5"""
    results = []
    ts_files = context.find_files([".ts", ".tsx"])
    if not ts_files:
        return results

    threshold = context.project_profile.get_adjusted_threshold('any_usage_threshold', 5)
    any_count = 0
    any_locations = []

    for fpath in ts_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        lines = content.split('\n')
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('*'):
                continue
            # Skip type definition files where any might be intentional
            basename = os.path.basename(fpath)
            if 'types' in basename.lower() or '.d.ts' in basename:
                continue

            # Find any type usage (but not in words like 'company', 'manager', etc.)
            for m in re.finditer(r':\s*any\b|<any>|as\s+any\b|\bany\s*\[\]', line):
                any_count += 1
                any_locations.append((fpath, i + 1))

    if any_count > threshold:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l}"
            for f, l in any_locations[:8]
        )
        results.append({
            'id': 'TS-001',
            'name': 'any类型滥用',
            'level': 'info',
            'message': f'发现{any_count}处any类型使用(>{threshold})',
            'detail': detail,
            'file': any_locations[0][0] if any_locations else '',
            'line': any_locations[0][1] if any_locations else 0,
            'fix': '使用具体类型、unknown或泛型替代any，提升类型安全性',
        })

    return results


# ===== TS-002 接口命名规范 =====
def check_ts_002_interface_naming(context) -> List[Dict]:
    """TS-002 接口命名规范 - 检查interface命名"""
    results = []
    ts_files = context.find_files([".ts", ".tsx"])
    if not ts_files:
        return results

    issues = []

    for fpath in ts_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        lines = content.split('\n')
        for i, line in enumerate(lines):
            m = re.match(r'\s*(?:export\s+)?interface\s+(\w+)', line)
            if m:
                iface_name = m.group(1)
                # Check naming convention: should be PascalCase
                # Some conventions use I prefix (IUser) or Interface suffix (UserInterface)
                # We just check PascalCase
                if not re.match(r'^[A-Z][a-zA-Z0-9]*$', iface_name):
                    issues.append((fpath, i + 1, iface_name, '应为PascalCase'))

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} '{n}' {r}"
            for f, l, n, r in issues[:8]
        )
        results.append({
            'id': 'TS-002',
            'name': '接口命名规范',
            'level': 'info',
            'message': f'发现{len(issues)}个接口命名不规范',
            'detail': detail,
            'file': issues[0][0],
            'line': issues[0][1],
            'fix': '接口名使用PascalCase，如 IUser、OrderConfig',
        })

    return results


# ===== TS-003 泛型约束缺失 =====
def check_ts_003_generic_constraint(context) -> List[Dict]:
    """TS-003 泛型约束缺失 - 泛型无extends约束"""
    results = []
    ts_files = context.find_files([".ts", ".tsx"])
    if not ts_files:
        return results

    issues = []

    for fpath in ts_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        # Find generic type parameters without constraints
        # Pattern: <T> without <T extends ...>
        generic_pattern = re.compile(r'<(\w+)(?:\s*,\s*(\w+))?>')
        constrained_pattern = re.compile(r'<(\w+)\s+extends\s+')

        lines = content.split('\n')
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('*'):
                continue

            # Check function/class generics
            func_generic = re.search(r'(?:function|class|interface|type)\s+\w+\s*<([^>]+)>', line)
            if func_generic:
                params = func_generic.group(1)
                # Check each type param
                for param in params.split(','):
                    param = param.strip()
                    if not param:
                        continue
                    # If param is a single letter without extends
                    if re.match(r'^[A-Z]$', param) and 'extends' not in param:
                        issues.append((fpath, i + 1, param))

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} 泛型 '{n}' 无约束"
            for f, l, n in issues[:8]
        )
        results.append({
            'id': 'TS-003',
            'name': '泛型约束缺失',
            'level': 'info',
            'message': f'发现{len(issues)}个泛型缺少extends约束',
            'detail': detail,
            'file': issues[0][0] if issues else '',
            'line': issues[0][1] if issues else 0,
            'fix': '为泛型添加约束，如 <T extends BaseType> 或 <T extends object>',
        })

    return results


# ===== TS-004 类型断言滥用 =====
def check_ts_004_type_assertion(context) -> List[Dict]:
    """TS-004 类型断言滥用 - as使用过多"""
    results = []
    ts_files = context.find_files([".ts", ".tsx"])
    if not ts_files:
        return results

    threshold = context.project_profile.get_adjusted_threshold('type_assertion_threshold', 10)
    assertion_count = 0
    assertion_locations = []

    for fpath in ts_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        lines = content.split('\n')
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('*'):
                continue

            # Count 'as' type assertions
            assertions = re.findall(r'\bas\s+\w+(?:\[\])?\b', line)
            assertion_count += len(assertions)
            for _ in assertions:
                assertion_locations.append((fpath, i + 1))

            # Also count angle bracket assertions: <Type>value
            angle_assertions = re.findall(r'<([A-Z]\w+)>\s*\w', line)
            assertion_count += len(angle_assertions)
            for _ in angle_assertions:
                assertion_locations.append((fpath, i + 1))

    if assertion_count > threshold:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l}"
            for f, l in assertion_locations[:8]
        )
        results.append({
            'id': 'TS-004',
            'name': '类型断言滥用',
            'level': 'info',
            'message': f'发现{assertion_count}处类型断言(>{threshold})',
            'detail': detail,
            'file': assertion_locations[0][0] if assertion_locations else '',
            'line': assertion_locations[0][1] if assertion_locations else 0,
            'fix': '减少类型断言使用，通过正确的类型推导和类型守卫来避免断言',
        })

    return results


# ===== TS-005 可选链未使用 =====
def check_ts_005_optional_chaining(context) -> List[Dict]:
    """TS-005 可选链未使用 - 可用?.但未用"""
    results = []
    ts_files = context.find_files([".ts", ".tsx", ".js", ".jsx"])
    issues = []

    for fpath in ts_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        lines = content.split('\n')
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('*'):
                continue

            # Pattern: a && a.b or (a !== null && a.b) or (a != null && a.b)
            patterns = [
                # x && x.y pattern
                r'(\w+)\s*&&\s*\1\.\w+',
                # x !== null && x.y or x != null && x.y
                r'(\w+)\s*!==?\s*null\s*&&\s*\1\.\w+',
                # x !== undefined && x.y
                r'(\w+)\s*!==?\s*undefined\s*&&\s*\1\.\w+',
            ]

            for pattern in patterns:
                if re.search(pattern, line):
                    issues.append((fpath, i + 1, stripped[:50]))
                    break

        if len(issues) > 20:
            break

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} {code}"
            for f, l, code in issues[:8]
        )
        results.append({
            'id': 'TS-005',
            'name': '可选链未使用',
            'level': 'info',
            'message': f'发现{len(issues)}处可用可选链(?.)简化的代码',
            'detail': detail,
            'file': issues[0][0],
            'line': issues[0][1],
            'fix': '使用可选链操作符 ?. 替代冗长的空值检查，如 user?.address?.city',
        })

    return results


# ===== TS-006 空值合并未使用 =====
def check_ts_006_nullish_coalescing(context) -> List[Dict]:
    """TS-006 空值合并未使用 - 可用??但未用"""
    results = []
    ts_files = context.find_files([".ts", ".tsx", ".js", ".jsx"])
    issues = []

    for fpath in ts_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        lines = content.split('\n')
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('*'):
                continue

            # Pattern: x !== null ? x : default or x != null ? x : default
            # Pattern: x || default (when x could be 0 or '' which are falsy but valid)
            patterns = [
                # x !== null && x !== undefined ? x : default
                r'(\w+)\s*!==?\s*null\s*&&\s*\1\s*!==?\s*undefined\s*\?\s*\1\s*:',
                # x != null ? x : default
                r'(\w+)\s*!=\s*null\s*\?\s*\1\s*:',
                # x === undefined ? default : x (ternary with undefined check)
                r'(\w+)\s*===?\s*undefined\s*\?\s*\w+\s*:\s*\1',
            ]

            for pattern in patterns:
                if re.search(pattern, line):
                    issues.append((fpath, i + 1, stripped[:50]))
                    break

            # Also check for || with potential null/undefined
            if re.search(r'(\w+)\s*\|\|\s*[\d\'"\[\{]', line):
                # This might need ?? instead of ||
                # But only flag if it's a variable that could be null/undefined
                pass

        if len(issues) > 20:
            break

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} {code}"
            for f, l, code in issues[:8]
        )
        results.append({
            'id': 'TS-006',
            'name': '空值合并未使用',
            'level': 'info',
            'message': f'发现{len(issues)}处可用空值合并(??)简化的代码',
            'detail': detail,
            'file': issues[0][0],
            'line': issues[0][1],
            'fix': '使用空值合并操作符 ?? 替代冗长的空值检查，如 value ?? defaultValue',
        })

    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'TS-001',
        'name': 'any类型滥用',
        'level': 'info',
        'category': 'typescript',
        'module_id': '26',
        'applicable_types': [],
        'description': '检测any类型使用次数>5',
        'check': check_ts_001_any_abuse,
    },
    {
        'id': 'TS-002',
        'name': '接口命名规范',
        'level': 'info',
        'category': 'typescript',
        'module_id': '26',
        'applicable_types': [],
        'description': '检查interface命名是否为PascalCase',
        'check': check_ts_002_interface_naming,
    },
    {
        'id': 'TS-003',
        'name': '泛型约束缺失',
        'level': 'info',
        'category': 'typescript',
        'module_id': '26',
        'applicable_types': [],
        'description': '检查泛型是否有extends约束',
        'check': check_ts_003_generic_constraint,
    },
    {
        'id': 'TS-004',
        'name': '类型断言滥用',
        'level': 'info',
        'category': 'typescript',
        'module_id': '26',
        'applicable_types': [],
        'description': '检测as类型断言使用过多',
        'check': check_ts_004_type_assertion,
    },
    {
        'id': 'TS-005',
        'name': '可选链未使用',
        'level': 'info',
        'category': 'typescript',
        'module_id': '26',
        'applicable_types': [],
        'description': '检查可用?.简化但未使用的代码',
        'check': check_ts_005_optional_chaining,
    },
    {
        'id': 'TS-006',
        'name': '空值合并未使用',
        'level': 'info',
        'category': 'typescript',
        'module_id': '26',
        'applicable_types': [],
        'description': '检查可用??简化但未使用的代码',
        'check': check_ts_006_nullish_coalescing,
    },
]
