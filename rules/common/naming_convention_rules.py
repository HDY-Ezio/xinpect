"""
命名规范规则集 (v5.2.0)
检测命名规范问题 - 适用于所有项目类型
包含: 变量命名、函数命名、类命名、常量命名、布尔值命名、
文件名规范、缩写规范、语义化命名等8项检查
"""

import re
import os
from typing import List, Dict, Any


# 无意义变量名黑名单
MEANINGLESS_NAMES = {
    'a', 'b', 'c', 'd', 'e', 'x', 'y', 'z', 'n', 'i', 'j', 'k',
    'aa', 'bb', 'cc', 'dd', 'ee',
    'temp', 'tmp', 'foo', 'bar', 'baz', 'qux',
    'data', 'data1', 'data2', 'result', 'res', 'ret',
    'val', 'value', 'item', 'obj', 'element', 'elem', 'el',
    'str', 'num', 'bool', 'arr', 'list', 'dict', 'map',
    'info', 'msg', 'text', 'str1', 'str2',
}

# 合理缩写白名单
ALLOWED_ABBREVIATIONS = {
    'id', 'url', 'api', 'http', 'html', 'css', 'js', 'ts',
    'io', 'ui', 'db', 'os', 'app', 'config', 'env',
    'max', 'min', 'avg', 'cnt', 'idx', 'len',
    'req', 'res', 'err', 'msg', 'param', 'params',
    'btn', 'nav', 'ctx', 'src', 'dest', 'auth',
}


def _is_camel_case(name: str) -> bool:
    """检查是否为小驼峰命名"""
    if not name:
        return False
    if name.startswith('_'):
        name = name.lstrip('_')
    if not name:
        return True
    return bool(re.match(r'^[a-z][a-zA-Z0-9]*$', name))


def _is_pascal_case(name: str) -> bool:
    """检查是否为大驼峰命名"""
    if not name:
        return False
    return bool(re.match(r'^[A-Z][a-zA-Z0-9]*$', name))


def _is_snake_case(name: str) -> bool:
    """检查是否为蛇形命名"""
    if not name:
        return False
    return bool(re.match(r'^[a-z][a-z0-9_]*$', name))


def _is_upper_snake(name: str) -> bool:
    """检查是否为大写蛇形命名(常量风格)"""
    if not name:
        return False
    return bool(re.match(r'^[A-Z][A-Z0-9_]*$', name))


def _is_kebab_case(name: str) -> bool:
    """检查是否为kebab-case"""
    if not name:
        return False
    return bool(re.match(r'^[a-z][a-z0-9-]*$', name))


# ===== NAME-001 变量命名风格 =====
def check_name_001_variable_naming(context) -> List[Dict]:
    """NAME-001 变量命名风格 - 驼峰命名检查"""
    results = []
    code_files = context.find_files([".js", ".ts", ".tsx", ".jsx"])
    issues = []

    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        lines = content.split('\n')
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('*'):
                continue

            # Check const/let/var declarations
            m = re.match(r'(?:const|let|var)\s+(\w+)\s*=', stripped)
            if m:
                var_name = m.group(1)
                # Skip constants (UPPER_SNAKE)
                if _is_upper_snake(var_name):
                    continue
                # Skip destructuring
                if stripped.startswith('const {') or stripped.startswith('const ['):
                    continue
                # Check if camelCase
                if not _is_camel_case(var_name) and not var_name.startswith('_'):
                    if len(var_name) > 1 and not var_name.isupper():
                        issues.append((fpath, i + 1, var_name, '应为camelCase'))

            # Check Python variable assignments
            if os.path.splitext(fpath)[1].lower() == '.py':
                m = re.match(r'^(\w+)\s*=\s*', stripped)
                if m:
                    var_name = m.group(1)
                    if var_name in ('self', 'cls', '_', '__all__', '__name__'):
                        continue
                    if var_name.startswith('__'):
                        continue
                    # Python should use snake_case
                    if not _is_snake_case(var_name) and not _is_upper_snake(var_name):
                        if len(var_name) > 2:
                            issues.append((fpath, i + 1, var_name, '应为snake_case'))

        if len(issues) > 30:
            break

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} '{n}' {r}"
            for f, l, n, r in issues[:8]
        )
        results.append({
            'id': 'NAME-001',
            'name': '变量命名风格',
            'level': 'info',
            'message': f'发现{len(issues)}个变量命名不符合规范',
            'detail': detail,
            'file': issues[0][0],
            'line': issues[0][1],
            'fix': 'JS/TS使用camelCase，Python使用snake_case命名变量',
        })

    return results


# ===== NAME-002 函数命名风格 =====
def check_name_002_function_naming(context) -> List[Dict]:
    """NAME-002 函数命名风格 - 动词开头检查"""
    results = []
    code_files = context.find_files([".js", ".ts", ".py", ".tsx", ".jsx"])
    issues = []

    # Common verb prefixes for functions
    verb_prefixes = (
        'get', 'set', 'add', 'remove', 'delete', 'create', 'update', 'edit',
        'find', 'search', 'filter', 'sort', 'map', 'reduce', 'forEach',
        'is', 'has', 'can', 'should', 'will', 'check', 'validate', 'verify',
        'load', 'save', 'fetch', 'send', 'receive', 'read', 'write',
        'open', 'close', 'start', 'stop', 'init', 'reset', 'clear',
        'handle', 'on', 'emit', 'trigger', 'call', 'apply', 'bind',
        'parse', 'format', 'convert', 'transform', 'build', 'make',
        'show', 'hide', 'toggle', 'enable', 'disable', 'lock', 'unlock',
        'compute', 'calculate', 'process', 'execute', 'run', 'perform',
        'test', 'assert', 'expect', 'mock', 'setup', 'teardown',
        'render', 'mount', 'unmount', 'compose', 'wrap', 'unwrap',
        '_get', '_set', '_init', '_handle', '_check', '_validate', '_process',
    )

    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        # Find function definitions
        func_pattern = re.compile(
            r'(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\([^)]*\)|[\w]+)\s*=>|def\s+(\w+)\s*\()'
        )
        for m in func_pattern.finditer(content):
            func_name = m.group(1) or m.group(2) or m.group(3)
            if not func_name:
                continue
            # Skip constructors and lifecycle methods
            if func_name in ('constructor', 'render', 'componentDidMount', 'componentWillUnmount',
                           '__init__', '__str__', '__repr__', '__call__'):
                continue
            if func_name.startswith('__') and func_name.endswith('__'):
                continue
            # Skip short names and event handlers
            if len(func_name) <= 2:
                continue
            if func_name.startswith('on') and len(func_name) > 2 and func_name[2].isupper():
                continue

            # Check if starts with a verb
            starts_with_verb = any(func_name.startswith(v) for v in verb_prefixes)
            if not starts_with_verb:
                line_num = content[:m.start()].count('\n') + 1
                issues.append((fpath, line_num, func_name))

        if len(issues) > 30:
            break

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} '{n}'"
            for f, l, n in issues[:8]
        )
        results.append({
            'id': 'NAME-002',
            'name': '函数命名风格',
            'level': 'info',
            'message': f'发现{len(issues)}个函数未以动词开头',
            'detail': detail,
            'file': issues[0][0],
            'line': issues[0][1],
            'fix': '函数名应以动词开头，如 getUserData、calculateTotal、handleSubmit',
        })

    return results


# ===== NAME-003 类命名风格 =====
def check_name_003_class_naming(context) -> List[Dict]:
    """NAME-003 类命名风格 - 大驼峰检查"""
    results = []
    code_files = context.find_files([".js", ".ts", ".py", ".tsx", ".jsx"])
    issues = []

    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        lines = content.split('\n')
        for i, line in enumerate(lines):
            m = re.match(r'\s*class\s+(\w+)', line)
            if m:
                class_name = m.group(1)
                if not _is_pascal_case(class_name):
                    issues.append((fpath, i + 1, class_name))

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} '{n}' 应为PascalCase"
            for f, l, n in issues[:8]
        )
        results.append({
            'id': 'NAME-003',
            'name': '类命名风格',
            'level': 'info',
            'message': f'发现{len(issues)}个类未使用大驼峰命名',
            'detail': detail,
            'file': issues[0][0],
            'line': issues[0][1],
            'fix': '类名应使用PascalCase，如 UserService、OrderController',
        })

    return results


# ===== NAME-004 常量命名风格 =====
def check_name_004_constant_naming(context) -> List[Dict]:
    """NAME-004 常量命名风格 - 全大写+下划线
    
    v5.3.0 Python常量误判修复：
    - 仅对模块级的简单值（数字/字符串/布尔/None）报常量命名问题
    - 排除 = 后面以 [ { ( 开头的行（列表/字典/元组/集合/函数调用）
    - 排除 import / from / class / def / if / for / while 等语句内的赋值
    - 排除在函数/类定义内部的赋值（只检测真正的模块级常量）
    """
    results = []
    code_files = context.find_files([".js", ".ts", ".py", ".tsx", ".jsx"])
    issues = []

    # Python 语句级关键字前缀（这些行不是模块级常量赋值）
    _PY_STATEMENT_PREFIXES = (
        'import ', 'from ', 'class ', 'def ', 'if ', 'elif ', 'else:',
        'for ', 'while ', 'with ', 'try:', 'except', 'finally:',
        'return ', 'raise ', 'yield ', 'assert ', 'pass', 'break', 'continue',
        'global ', 'nonlocal ', 'lambda ', 'del ',
    )
    # Python 复杂赋值开头（= 后面第一个非空字符属于这些，说明不是简单常量）
    _PY_COMPLEX_VAL_STARTS = ('[', '{', '(', '[',)

    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        ext = os.path.splitext(fpath)[1].lower()
        lines = content.split('\n')

        # Python: 计算函数/类定义的缩进层级，用于判断是否模块级
        # 保守方案：只对缩进为0（顶格）且不是关键字语句的赋值行报常量
        for i, line in enumerate(lines):
            stripped = line.strip()
            lineno = i + 1

            # === JS/TS 部分：const 声明 ===
            if ext in ('.js', '.ts', '.tsx', '.jsx'):
                # Check const declarations with primitive values (should be UPPER_SNAKE)
                m = re.match(r'const\s+(\w+)\s*=\s*(["\']|[\d]|true|false|null)', stripped)
                if m:
                    const_name = m.group(1)
                    # Skip short names and already correct names
                    if len(const_name) <= 2:
                        continue
                    if _is_upper_snake(const_name):
                        continue
                    if _is_camel_case(const_name) and len(const_name) > 3:
                        # camelCase const with primitive value
                        issues.append((fpath, lineno, const_name, '应为UPPER_SNAKE_CASE'))

            # === Python 部分：模块级常量 ===
            if ext == '.py':
                # 跳过空行
                if not stripped:
                    continue
                # 仅顶格行（模块级）才可能是常量
                if line[0] in (' ', '\t'):
                    continue
                # 跳过关键字开头的语句
                if any(stripped.startswith(p) for p in _PY_STATEMENT_PREFIXES):
                    continue
                # 跳过注释行
                if stripped.startswith('#'):
                    continue
                # 跳过装饰器
                if stripped.startswith('@'):
                    continue

                # 匹配 NAME = value 形式
                m = re.match(r'^(\w+)\s*=\s*(.+)', stripped)
                if not m:
                    continue

                const_name = m.group(1)
                rest = m.group(2)

                # 下划线开头跳过
                if const_name.startswith('_'):
                    continue
                if len(const_name) <= 2:
                    continue

                # 排除复杂值：列表/字典/元组/集合/函数调用
                rest_stripped = rest.strip()
                if not rest_stripped:
                    continue
                first_char = rest_stripped[0]
                if first_char in ('[', '{', '('):
                    continue

                # 只对简单字面量（数字、字符串、布尔、None）报常量命名问题
                if not re.match(r'^(["\']|[\d]|True\b|False\b|None\b)', rest_stripped):
                    continue

                # 进一步确认：这一行内必须完成赋值（不跨行），且值在同一行结束
                # 字符串情况：检查引号是否闭合（简化：同一行内配对）
                if first_char in ('"', "'"):
                    # 统计引号对数是否闭合（粗略）
                    quote = first_char
                    count = 0
                    in_escape = False
                    for ch in rest_stripped:
                        if in_escape:
                            in_escape = False
                            continue
                        if ch == '\\':
                            in_escape = True
                            continue
                        if ch == quote:
                            count += 1
                    if count < 2:
                        # 字符串未在本行闭合，可能是多行字符串，跳过
                        continue

                # 只对非大写且非蛇形的名字报问题
                if not _is_upper_snake(const_name) and not _is_snake_case(const_name):
                    issues.append((fpath, lineno, const_name, '应为UPPER_SNAKE_CASE'))

        if len(issues) > 30:
            break

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} '{n}' {r}"
            for f, l, n, r in issues[:8]
        )
        results.append({
            'id': 'NAME-004',
            'name': '常量命名风格',
            'level': 'info',
            'message': f'发现{len(issues)}个常量未使用大写命名',
            'detail': detail,
            'file': issues[0][0],
            'line': issues[0][1],
            'fix': '常量应使用UPPER_SNAKE_CASE，如 MAX_RETRY_COUNT、API_BASE_URL',
        })

    return results


# ===== NAME-005 布尔值命名 =====
def check_name_005_boolean_naming(context) -> List[Dict]:
    """NAME-005 布尔值命名 - is/has/can/should前缀"""
    results = []
    code_files = context.find_files([".js", ".ts", ".py", ".tsx", ".jsx"])
    issues = []

    bool_prefixes = ('is', 'has', 'can', 'should', 'will', 'was', 'are', 'need')

    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        lines = content.split('\n')
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('#'):
                continue

            # Detect boolean assignments
            # const/let/var xxx = true/false
            m = re.match(r'(?:const|let|var)\s+(\w+)\s*=\s*(true|false)\b', stripped)
            if not m:
                # Python: xxx = True/False
                m = re.match(r'^(\w+)\s*=\s*(True|False)\b', stripped)
            if not m:
                # Function returning boolean: xxx = ... > ... or xxx = ... && ...
                m = re.match(r'(?:const|let|var)\s+(\w+)\s*=\s*.*(?:[><=!]=|&&|\|\||instanceof)\s*', stripped)
            if not m:
                m = re.match(r'^(\w+)\s*=\s*.*(?:[><=!]=|and|or|not)\s*', stripped)

            if m:
                var_name = m.group(1)
                if len(var_name) <= 2:
                    continue
                if var_name.startswith('_'):
                    continue
                # Check if starts with boolean prefix
                has_prefix = any(var_name.startswith(p) for p in bool_prefixes)
                if not has_prefix:
                    issues.append((fpath, i + 1, var_name))

        if len(issues) > 30:
            break

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} '{n}'"
            for f, l, n in issues[:8]
        )
        results.append({
            'id': 'NAME-005',
            'name': '布尔值命名',
            'level': 'info',
            'message': f'发现{len(issues)}个布尔变量未使用is/has/can/should前缀',
            'detail': detail,
            'file': issues[0][0],
            'line': issues[0][1],
            'fix': '布尔变量应以is/has/can/should开头，如 isVisible、hasPermission',
        })

    return results


# ===== NAME-006 文件名规范 =====
def check_name_006_filename_convention(context) -> List[Dict]:
    """NAME-006 文件名规范 - kebab-case或PascalCase"""
    results = []
    code_files = context.find_files([".js", ".ts", ".py", ".tsx", ".jsx", ".css", ".scss"])
    issues = []

    for fpath in code_files:
        basename = os.path.basename(fpath)
        name_without_ext = os.path.splitext(basename)[0]

        # Skip special files
        if name_without_ext.startswith('.') or name_without_ext.startswith('_'):
            continue
        if name_without_ext in ('index', '__init__', 'config', 'setup', 'types'):
            continue
        # Skip test files
        if 'test' in name_without_ext.lower() or 'spec' in name_without_ext.lower():
            continue

        # Check naming convention
        is_valid = (
            _is_kebab_case(name_without_ext) or
            _is_pascal_case(name_without_ext) or
            _is_snake_case(name_without_ext) or
            _is_camel_case(name_without_ext)
        )

        if not is_valid:
            issues.append((fpath, basename))

    if issues:
        detail = '\n'.join(
            f"  {n}"
            for _, n in issues[:8]
        )
        results.append({
            'id': 'NAME-006',
            'name': '文件名规范',
            'level': 'info',
            'message': f'发现{len(issues)}个文件名不符合命名规范',
            'detail': detail,
            'file': issues[0][0],
            'line': 0,
            'fix': '文件名使用kebab-case(如user-service.ts)或PascalCase(如UserService.ts)',
        })

    return results


# ===== NAME-007 缩写规范 =====
def check_name_007_abbreviation_convention(context) -> List[Dict]:
    """NAME-007 缩写规范 - 禁止不合理缩写"""
    results = []
    code_files = context.find_files([".js", ".ts", ".py", ".tsx", ".jsx"])
    issues = []

    # Common bad abbreviations
    bad_abbreviations = {
        'btn': 'button', 'cb': 'callback', 'cfg': 'config',
        'ctx': 'context', 'ctrl': 'control', 'desc': 'description',
        'elem': 'element', 'env': 'environment', 'fn': 'function',
        'len': 'length', 'mgr': 'manager', 'msg': 'message',
        'num': 'number', 'obj': 'object', 'param': 'parameter',
        'pos': 'position', 'req': 'request', 'resp': 'response',
        'ret': 'return', 'src': 'source', 'str': 'string',
        'tmp': 'temp', 'txt': 'text', 'val': 'value',
        'var': 'variable', 'wd': 'width', 'ht': 'height',
    }

    # Only flag very short suspicious names used as variable names
    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        lines = content.split('\n')
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('#') or stripped.startswith('*'):
                continue
            if stripped.startswith('import ') or stripped.startswith('from '):
                continue

            # Check short variable names (2-3 chars that are suspicious abbreviations)
            m = re.match(r'(?:const|let|var)\s+(\w{2,3})\s*=', stripped)
            if not m:
                m = re.match(r'^(\w{2,3})\s*=\s*', stripped)
            if m:
                var_name = m.group(1)
                if var_name.lower() in bad_abbreviations and var_name.lower() not in ALLOWED_ABBREVIATIONS:
                    issues.append((fpath, i + 1, var_name, bad_abbreviations[var_name.lower()]))

        if len(issues) > 20:
            break

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} '{n}' -> 建议使用 '{full}'"
            for f, l, n, full in issues[:8]
        )
        results.append({
            'id': 'NAME-007',
            'name': '缩写规范',
            'level': 'info',
            'message': f'发现{len(issues)}处不合理缩写',
            'detail': detail,
            'file': issues[0][0],
            'line': issues[0][1],
            'fix': '使用完整单词命名变量，提高代码可读性',
        })

    return results


# ===== NAME-008 语义化命名 =====
def check_name_008_semantic_naming(context) -> List[Dict]:
    """NAME-008 语义化命名 - 避免a/b/temp/data等无意义名"""
    results = []
    code_files = context.find_files([".js", ".ts", ".py", ".tsx", ".jsx"])
    issues = []

    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        lines = content.split('\n')
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('#') or stripped.startswith('*'):
                continue
            if stripped.startswith('import ') or stripped.startswith('from '):
                continue

            # Check for meaningless names
            m = re.match(r'(?:const|let|var)\s+(\w+)\s*=', stripped)
            if not m:
                m = re.match(r'^(\w+)\s*=\s*', stripped)
            if m:
                var_name = m.group(1)
                if var_name.lower() in MEANINGLESS_NAMES and len(var_name) <= 5:
                    # Skip loop iterators
                    if var_name in ('i', 'j', 'k', 'n') and re.search(r'(for|while|range|map|filter)\b', line):
                        continue
                    issues.append((fpath, i + 1, var_name))

        if len(issues) > 30:
            break

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} '{n}' 缺乏语义"
            for f, l, n in issues[:8]
        )
        results.append({
            'id': 'NAME-008',
            'name': '语义化命名',
            'level': 'info',
            'message': f'发现{len(issues)}个无意义变量名',
            'detail': detail,
            'file': issues[0][0],
            'line': issues[0][1],
            'fix': '使用描述性名称，如用 userData 替代 data，用 userName 替代 str',
        })

    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'NAME-001',
        'name': '变量命名风格',
        'level': 'info',
        'category': 'naming',
        'module_id': '25',
        'applicable_types': [],
        'description': '检查变量是否使用驼峰命名',
        'check': check_name_001_variable_naming,
    },
    {
        'id': 'NAME-002',
        'name': '函数命名风格',
        'level': 'info',
        'category': 'naming',
        'module_id': '25',
        'applicable_types': [],
        'description': '检查函数名是否以动词开头',
        'check': check_name_002_function_naming,
    },
    {
        'id': 'NAME-003',
        'name': '类命名风格',
        'level': 'info',
        'category': 'naming',
        'module_id': '25',
        'applicable_types': [],
        'description': '检查类名是否使用大驼峰',
        'check': check_name_003_class_naming,
    },
    {
        'id': 'NAME-004',
        'name': '常量命名风格',
        'level': 'info',
        'category': 'naming',
        'module_id': '25',
        'applicable_types': [],
        'description': '检查常量是否使用全大写+下划线',
        'check': check_name_004_constant_naming,
    },
    {
        'id': 'NAME-005',
        'name': '布尔值命名',
        'level': 'info',
        'category': 'naming',
        'module_id': '25',
        'applicable_types': [],
        'description': '检查布尔变量是否使用is/has/can/should前缀',
        'check': check_name_005_boolean_naming,
    },
    {
        'id': 'NAME-006',
        'name': '文件名规范',
        'level': 'info',
        'category': 'naming',
        'module_id': '25',
        'applicable_types': [],
        'description': '检查文件名是否使用kebab-case或PascalCase',
        'check': check_name_006_filename_convention,
    },
    {
        'id': 'NAME-007',
        'name': '缩写规范',
        'level': 'info',
        'category': 'naming',
        'module_id': '25',
        'applicable_types': [],
        'description': '检查是否使用了不合理的缩写',
        'check': check_name_007_abbreviation_convention,
    },
    {
        'id': 'NAME-008',
        'name': '语义化命名',
        'level': 'info',
        'category': 'naming',
        'module_id': '25',
        'applicable_types': [],
        'description': '检查是否使用了无意义变量名如a/b/temp/data',
        'check': check_name_008_semantic_naming,
    },
]
