"""
补充规则集 Part 2 (v5.2.0)
额外补充规则，进一步扩展检测覆盖面
包含: 不安全正则、正则拒绝服务、过度使用全局变量、
不当类型比较、缺失错误边界、不安全存储等补充检查
"""

import re
import os
from typing import List, Dict, Any


# ===== SEC-EXT-003 不安全正则 =====
def check_sec_ext_003_unsafe_regex(context) -> List[Dict]:
    """SEC-EXT-003 不安全正则 - 可能导致ReDoS的正则表达式"""
    results = []
    code_files = context.find_files([".js", ".ts", ".py", ".tsx", ".jsx"])
    issues = []

    # Patterns that may cause ReDoS (nested quantifiers)
    redos_patterns = [
        r'\(.*[+*].*\)\{2,\}',  # (x+){2,}
        r'\(.*[+*].*[+*].*\)',  # (x+y+)
        r'\(\.\*\)\{2,\}',  # (.*){2,}
    ]

    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        lines = content.split('\n')
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('#'):
                continue

            # Find regex patterns
            regex_matches = re.finditer(r'(?:/([^/]+)/[gimsuy]*|re\.compile\s*\(["\']([^"\']+)["\']\))', line)
            for m in regex_matches:
                pattern = m.group(1) or m.group(2)
                if not pattern:
                    continue
                # Check for nested quantifiers
                if re.search(r'\([^)]*[+*][^)]*\)[+*{]', pattern):
                    issues.append((fpath, i + 1, pattern[:40]))
                # Check for overlapping alternation
                if re.search(r'\([^)]*\|[^)]*\)[+*]', pattern):
                    issues.append((fpath, i + 1, pattern[:40]))

        if len(issues) > 10:
            break

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} /{p}/"
            for f, l, p in issues[:8]
        )
        results.append({
            'id': 'SEC-EXT-003',
            'name': '不安全正则',
            'level': 'warning',
            'message': f'发现{len(issues)}处可能导致ReDoS的正则表达式',
            'detail': detail,
            'file': issues[0][0] if issues else '',
            'line': issues[0][1] if issues else 0,
            'fix': '避免嵌套量词和重叠分支，使用非回溯正则或限制输入长度',
        })

    return results


# ===== SEC-EXT-004 localStorage敏感数据 =====
def check_sec_ext_004_localstorage_sensitive(context) -> List[Dict]:
    """SEC-EXT-004 localStorage敏感数据 - 在localStorage中存储敏感信息"""
    results = []
    code_files = context.find_files([".js", ".ts", ".tsx", ".jsx"])
    issues = []

    sensitive_keys = [
        'token', 'password', 'secret', 'key', 'credential',
        'auth', 'session', 'private', 'ssn', 'credit_card',
    ]

    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        lines = content.split('\n')
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('//'):
                continue

            # Check localStorage/sessionStorage with sensitive data
            if re.search(r'(?:localStorage|sessionStorage)\s*\.\s*(?:setItem|set)', line):
                for key in sensitive_keys:
                    if re.search(rf'["\'].*{key}.*["\']', line, re.IGNORECASE):
                        issues.append((fpath, i + 1, stripped[:50]))
                        break

        if len(issues) > 10:
            break

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} {code}"
            for f, l, code in issues[:8]
        )
        results.append({
            'id': 'SEC-EXT-004',
            'name': 'localStorage敏感数据',
            'level': 'warning',
            'message': f'发现{len(issues)}处在localStorage中存储敏感信息',
            'detail': detail,
            'file': issues[0][0] if issues else '',
            'line': issues[0][1] if issues else 0,
            'fix': '敏感数据(如token)应使用httpOnly cookie存储，而非localStorage',
        })

    return results


# ===== SEC-EXT-005 硬编码IP =====
def check_sec_ext_005_hardcoded_ip(context) -> List[Dict]:
    """SEC-EXT-005 硬编码IP - 代码中硬编码IP地址"""
    results = []
    code_files = context.find_files([".js", ".ts", ".py", ".tsx", ".jsx"])
    issues = []

    ip_pattern = re.compile(r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b')
    allowed_ips = {'127.0.0.1', '0.0.0.0', '255.255.255.255', '192.168.1.1', '10.0.0.1', '1.1.1.1', '8.8.8.8'}

    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        basename = os.path.basename(fpath).lower()
        if any(kw in basename for kw in ('config', 'env', 'setting', 'test', 'spec')):
            continue

        lines = content.split('\n')
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('#') or stripped.startswith('*'):
                continue

            for m in ip_pattern.finditer(line):
                ip = m.group(1)
                # Validate it's a real IP (each octet 0-255)
                parts = ip.split('.')
                if all(0 <= int(p) <= 255 for p in parts):
                    if ip not in allowed_ips:
                        issues.append((fpath, i + 1, ip))

        if len(issues) > 10:
            break

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} IP: {ip}"
            for f, l, ip in issues[:8]
        )
        results.append({
            'id': 'SEC-EXT-005',
            'name': '硬编码IP',
            'level': 'warning',
            'message': f'发现{len(issues)}处硬编码IP地址',
            'detail': detail,
            'file': issues[0][0] if issues else '',
            'line': issues[0][1] if issues else 0,
            'fix': '将IP地址提取到配置文件中，使用环境变量或DNS域名替代',
        })

    return results


# ===== COMP-009 useEffect依赖缺失 =====
def check_comp_009_useeffect_deps(context) -> List[Dict]:
    """COMP-009 useEffect依赖缺失 - React useEffect缺少依赖"""
    results = []
    tsx_files = context.find_files([".tsx", ".jsx"])
    if not tsx_files:
        return results

    issues = []

    for fpath in tsx_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        lines = content.split('\n')
        for i, line in enumerate(lines):
            # Check useEffect with empty dependency array but using variables
            if re.search(r'useEffect\s*\(\s*\(\)\s*=>', line):
                # Check if dependency array is empty
                effect_body = ''
                dep_array_found = False
                empty_deps = False
                for j in range(i, min(i + 20, len(lines))):
                    effect_body += lines[j] + '\n'
                    if re.search(r'\[\s*\]\s*\)?\s*;?\s*$', lines[j]):
                        dep_array_found = True
                        empty_deps = True
                        break
                    if re.search(r'\[\s*\w+', lines[j]):
                        dep_array_found = True
                        break

                if empty_deps and effect_body:
                    # Check if effect uses any variables from outer scope
                    used_vars = set(re.findall(r'\b(\w+)\b', effect_body))
                    # Filter to likely external variables (exclude common keywords)
                    keywords = {'useEffect', 'return', 'const', 'let', 'var', 'if', 'else',
                               'true', 'false', 'null', 'undefined', 'console', 'set', 'get'}
                    external = used_vars - keywords
                    if len(external) > 3:
                        issues.append((fpath, i + 1, f"useEffect使用{len(external)}个外部变量但依赖为空"))

        if len(issues) > 10:
            break

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} {d}"
            for f, l, d in issues[:8]
        )
        results.append({
            'id': 'COMP-009',
            'name': 'useEffect依赖缺失',
            'level': 'warning',
            'message': f'发现{len(issues)}处useEffect可能缺少依赖',
            'detail': detail,
            'file': issues[0][0] if issues else '',
            'line': issues[0][1] if issues else 0,
            'fix': '确保useEffect的依赖数组包含所有使用的外部变量',
        })

    return results


# ===== COMP-010 key属性缺失 =====
def check_comp_010_missing_key(context) -> List[Dict]:
    """COMP-010 key属性缺失 - 列表渲染缺少key"""
    results = []
    tsx_files = context.find_files([".tsx", ".jsx"])
    if not tsx_files:
        return results

    issues = []

    for fpath in tsx_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        lines = content.split('\n')
        for i, line in enumerate(lines):
            # Check for .map() returning JSX without key
            if re.search(r'\.map\s*\(', line):
                # Check if the returned element has a key prop
                has_key = False
                for j in range(i, min(i + 5, len(lines))):
                    if re.search(r'\bkey\s*=', lines[j]):
                        has_key = True
                        break
                    if re.search(r'\)\s*$', lines[j].strip()):
                        break

                if not has_key:
                    # Double check it's returning JSX
                    map_region = '\n'.join(lines[i:min(i+5, len(lines))])
                    if re.search(r'<\w+', map_region):
                        issues.append((fpath, i + 1, line.strip()[:40]))

        if len(issues) > 10:
            break

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} {code}"
            for f, l, code in issues[:8]
        )
        results.append({
            'id': 'COMP-010',
            'name': 'key属性缺失',
            'level': 'warning',
            'message': f'发现{len(issues)}处列表渲染缺少key属性',
            'detail': detail,
            'file': issues[0][0] if issues else '',
            'line': issues[0][1] if issues else 0,
            'fix': '为列表渲染的元素添加唯一key属性，如 key={item.id}',
        })

    return results


# ===== NAME-009 文件名与内容不一致 =====
def check_name_009_filename_content_mismatch(context) -> List[Dict]:
    """NAME-009 文件名与导出内容不匹配 - 文件名和默认导出不一致"""
    results = []
    code_files = context.find_files([".js", ".ts", ".tsx", ".jsx"])
    issues = []

    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        basename = os.path.splitext(os.path.basename(fpath))[0]
        # Skip index files
        if basename.lower() == 'index':
            continue

        # Check default export
        default_export = re.search(r'export\s+default\s+(?:class|function)\s+(\w+)', content)
        if not default_export:
            default_export = re.search(r'export\s+default\s+(\w+)', content)

        if default_export:
            export_name = default_export.group(1)
            # Compare with filename (allow camelCase/PascalCase variations)
            if basename.lower() != export_name.lower():
                # Allow some common patterns
                if basename.replace('-', '').replace('_', '').lower() != export_name.lower():
                    issues.append((fpath, 1, basename, export_name))

    if issues:
        detail = '\n'.join(
            f"  文件 {f} 导出 {n}"
            for _, _, f, n in issues[:8]
        )
        results.append({
            'id': 'NAME-009',
            'name': '文件名与导出不一致',
            'level': 'info',
            'message': f'发现{len(issues)}个文件名与默认导出不匹配',
            'detail': detail,
            'file': issues[0][0] if issues else '',
            'line': 0,
            'fix': '保持文件名与默认导出名称一致，如文件MyComponent.tsx导出MyComponent',
        })

    return results


# ===== DEAD-011 重复声明 =====
def check_dead_011_duplicate_declaration(context) -> List[Dict]:
    """DEAD-011 重复声明 - 同一作用域内重复声明变量"""
    results = []
    code_files = context.find_files([".js", ".ts", ".py", ".tsx", ".jsx"])
    issues = []

    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        ext = os.path.splitext(fpath)[1].lower()
        lines = content.split('\n')

        # Track declarations in current scope (simplified)
        declarations = {}

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('#'):
                continue

            if ext == '.py':
                m = re.match(r'^(\w+)\s*=\s*', stripped)
                if m:
                    var = m.group(1)
                    if var in declarations:
                        issues.append((fpath, i + 1, var, declarations[var]))
                    declarations[var] = i + 1
            elif ext in ('.js', '.ts', '.tsx', '.jsx'):
                m = re.match(r'(?:const|let|var)\s+(\w+)\s*=', stripped)
                if m:
                    var = m.group(1)
                    if var in declarations and 'const' in stripped and 'const' in lines[declarations[var]-1]:
                        issues.append((fpath, i + 1, var, declarations[var]))
                    declarations[var] = i + 1

        if len(issues) > 15:
            break

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} '{n}' (首次声明在第{fl}行)"
            for f, l, n, fl in issues[:8]
        )
        results.append({
            'id': 'DEAD-011',
            'name': '重复声明',
            'level': 'warning',
            'message': f'发现{len(issues)}处变量重复声明',
            'detail': detail,
            'file': issues[0][0] if issues else '',
            'line': issues[0][1] if issues else 0,
            'fix': '避免在同一作用域内重复声明变量，使用不同名称或重构代码',
        })

    return results


# ===== PERF-003 未节流的频繁事件 =====
def check_perf_003_untrottled_events(context) -> List[Dict]:
    """PERF-003 未节流的频繁事件 - scroll/resize/input未使用节流"""
    results = []
    code_files = context.find_files([".js", ".ts", ".tsx", ".jsx"])
    issues = []

    throttled_events = {'scroll', 'resize', 'mousemove', 'touchmove', 'input', 'keypress'}

    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        lines = content.split('\n')
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('//'):
                continue

            # Check addEventListener for high-frequency events
            m = re.search(r'addEventListener\s*\(\s*["\'](\w+)["\']', line)
            if m:
                event_name = m.group(1)
                if event_name in throttled_events:
                    # Check if throttle/debounce is used nearby
                    context_lines = '\n'.join(lines[max(0, i-5):min(len(lines), i+5)])
                    if not re.search(r'(throttle|debounce|requestAnimationFrame|setTimeout)', context_lines, re.IGNORECASE):
                        issues.append((fpath, i + 1, event_name))

        if len(issues) > 10:
            break

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} 事件 '{n}' 未节流"
            for f, l, n in issues[:8]
        )
        results.append({
            'id': 'PERF-003',
            'name': '未节流的频繁事件',
            'level': 'warning',
            'message': f'发现{len(issues)}处高频事件未使用节流/防抖',
            'detail': detail,
            'file': issues[0][0] if issues else '',
            'line': issues[0][1] if issues else 0,
            'fix': '为scroll/resize/input等高频事件添加throttle或debounce',
        })

    return results


# ===== DOC-006 魔术注释 =====
def check_doc_006_magic_comments(context) -> List[Dict]:
    """DOC-006 魔术注释 - eslint-disable/prettier-ignore等抑制注释过多"""
    results = []
    code_files = context.find_files([".js", ".ts", ".py", ".tsx", ".jsx"])
    suppress_count = 0
    suppress_locations = []

    suppress_patterns = [
        r'eslint-disable',
        r'eslint-disable-next-line',
        r'prettier-ignore',
        r'tslint:disable',
        r'#\s*noqa',
        r'#\s*type:\s*ignore',
        r'@ts-ignore',
        r'@ts-nocheck',
        r'lint-disable',
    ]

    combined_pattern = re.compile('|'.join(suppress_patterns))

    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        lines = content.split('\n')
        for i, line in enumerate(lines):
            if combined_pattern.search(line):
                suppress_count += 1
                if len(suppress_locations) < 8:
                    suppress_locations.append((fpath, i + 1, line.strip()[:40]))

    if suppress_count > 10:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} {code}"
            for f, l, code in suppress_locations[:8]
        )
        results.append({
            'id': 'DOC-006',
            'name': '魔术注释',
            'level': 'info',
            'message': f'发现{suppress_count}处lint/type抑制注释(>10)',
            'detail': detail,
            'file': suppress_locations[0][0] if suppress_locations else '',
            'line': suppress_locations[0][1] if suppress_locations else 0,
            'fix': '解决根本问题而非抑制检查，减少eslint-disable/ts-ignore等注释',
        })

    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'SEC-EXT-003',
        'name': '不安全正则',
        'level': 'warning',
        'category': 'security_extension',
        'module_id': '33',
        'applicable_types': [],
        'description': '检测可能导致ReDoS的正则表达式',
        'check': check_sec_ext_003_unsafe_regex,
    },
    {
        'id': 'SEC-EXT-004',
        'name': 'localStorage敏感数据',
        'level': 'warning',
        'category': 'security_extension',
        'module_id': '33',
        'applicable_types': ['miniprogram', 'web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检测在localStorage中存储敏感信息',
        'check': check_sec_ext_004_localstorage_sensitive,
    },
    {
        'id': 'SEC-EXT-005',
        'name': '硬编码IP',
        'level': 'warning',
        'category': 'security_extension',
        'module_id': '33',
        'applicable_types': [],
        'description': '检测代码中硬编码的IP地址',
        'check': check_sec_ext_005_hardcoded_ip,
    },
    {
        'id': 'COMP-009',
        'name': 'useEffect依赖缺失',
        'level': 'warning',
        'category': 'component_design',
        'module_id': '28',
        'applicable_types': ['miniprogram', 'web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查React useEffect是否缺少依赖',
        'check': check_comp_009_useeffect_deps,
    },
    {
        'id': 'COMP-010',
        'name': 'key属性缺失',
        'level': 'warning',
        'category': 'component_design',
        'module_id': '28',
        'applicable_types': ['miniprogram', 'web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查列表渲染是否缺少key属性',
        'check': check_comp_010_missing_key,
    },
    {
        'id': 'NAME-009',
        'name': '文件名与导出不一致',
        'level': 'info',
        'category': 'naming',
        'module_id': '25',
        'applicable_types': [],
        'description': '检查文件名与默认导出名称是否一致',
        'check': check_name_009_filename_content_mismatch,
    },
    {
        'id': 'DEAD-011',
        'name': '重复声明',
        'level': 'warning',
        'category': 'dead_code',
        'module_id': '22',
        'applicable_types': [],
        'description': '检测同一作用域内变量重复声明',
        'check': check_dead_011_duplicate_declaration,
    },
    {
        'id': 'PERF-003',
        'name': '未节流的频繁事件',
        'level': 'warning',
        'category': 'performance',
        'module_id': '31',
        'applicable_types': ['miniprogram', 'web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查scroll/resize等高频事件是否使用节流',
        'check': check_perf_003_untrottled_events,
    },
    {
        'id': 'DOC-006',
        'name': '魔术注释',
        'level': 'info',
        'category': 'documentation',
        'module_id': '30',
        'applicable_types': [],
        'description': '检查eslint-disable/ts-ignore等抑制注释是否过多',
        'check': check_doc_006_magic_comments,
    },
]
