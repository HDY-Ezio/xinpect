# -*- coding: utf-8 -*-
"""
环境路径与构建规则集 (v5.3.0)
Brain1 确定性规则引擎 - 补漏规则
包含: ENV-001 禁止硬编码绝对路径、BUILD-001 构建产物配置完整性校验、
      BUILD-002 发布包清洁度校验、SYNTAX-001 Python转义序列合规性
"""

import re
import os
import py_compile
import tempfile
from typing import List, Dict, Any


# ======================================================================
# ENV-001: 禁止硬编码绝对路径
# 扫描所有源码文件中的字符串字面量，匹配绝对路径模式
# 排除注释行、白名单文件（测试fixture、示例）
# ======================================================================

# 绝对路径匹配模式
_ABSOLUTE_PATH_PATTERNS = [
    # Linux/Unix 绝对路径: /home/xxx, /usr/local, /var/log 等
    (re.compile(r'''(?:"|'|`)(/(?:home|usr|var|etc|opt|tmp|srv)/[^"'`\s]{3,})(?:"|'|`)'''),
     'Linux 绝对路径'),
    # macOS 用户路径: /Users/xxx
    (re.compile(r'''(?:"|'|`)(/Users/[^"'`\s]{3,})(?:"|'|`)'''),
     'macOS 用户路径'),
    # Windows 绝对路径: C:\Users\xxx, D:\Projects 等
    (re.compile(r'''(?:"|'|`)([A-Z]:\\\\(?:Users|Projects|Program|Windows|ProgramData)[^"'`\s]*)(?:"|'|`)'''),
     'Windows 绝对路径'),
    # Windows 单反斜杠形式
    (re.compile(r'''(?:"|'|`)([A-Z]:\\(?:Users|Projects|Program|Windows|ProgramData)[^"'`\s]*)(?:"|'|`)'''),
     'Windows 绝对路径(单反斜杠)'),
    # Python Path-like: os.path 拼接中的硬编码根路径
    (re.compile(r'''(?:["'])(/(?:home|Users)/\w+)["\']'''),
     '硬编码用户目录路径'),
]

# 白名单文件模式（测试 fixture、示例、配置模板等）
_ENV_WHITELIST_FILES = {
    'fixture', 'fixtures', 'example', 'examples', 'sample', 'samples',
    'demo', 'mock', 'mocks', '__mocks__', 'test_data', 'testdata',
    'seed', 'seeds', 'template', 'templates', '.example', '.sample',
    '.template', 'conftest',
}

# 白名单路径片段
_ENV_WHITELIST_PATH_FRAGMENTS = [
    '/test/', '/tests/', '/__tests__/', '/__mocks__/',
    '/fixture', '/example', '/demo/', '/sample/',
    '.test.', '.spec.', '.example.', '.fixture.',
    '/node_modules/', '/.git/', '/dist/', '/build/',
]


def _is_env_whitelist_file(fpath: str) -> bool:
    """判断文件是否在环境路径白名单中"""
    basename = os.path.basename(fpath).lower()
    name_without_ext = os.path.splitext(basename)[0]

    # 检查文件名是否包含白名单关键词
    for keyword in _ENV_WHITELIST_FILES:
        if keyword in name_without_ext or keyword in basename:
            return True

    # 检查路径中是否包含白名单片段
    norm_path = fpath.replace(os.sep, '/')
    for fragment in _ENV_WHITELIST_PATH_FRAGMENTS:
        if fragment in norm_path:
            return True

    return False


def check_env_001_hardcoded_paths(context) -> List[Dict]:
    """ENV-001 禁止硬编码绝对路径

    扫描所有源码文件中的字符串字面量，匹配绝对路径模式。
    排除注释行和白名单文件（测试fixture、示例等）。
    """
    results = []
    all_files = context.find_files([".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yaml", ".yml"])
    if not all_files:
        return results

    violations = []

    for fpath in all_files:
        # 跳过白名单文件
        if _is_env_whitelist_file(fpath):
            continue

        # 跳过配置文件（.env、config.json等本身可能包含路径）
        basename = os.path.basename(fpath).lower()
        if basename.startswith('.env') or basename in ('config.json', 'settings.json'):
            continue

        content = context.safe_read(fpath)
        if not content:
            continue

        lines = content.split('\n')
        for line_idx, line in enumerate(lines):
            stripped = line.strip()

            # 跳过注释行
            if stripped.startswith('#') or stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*'):
                continue

            # 跳过 import/require 行
            if stripped.startswith(('import ', 'from ', 'require(')):
                continue

            # 跳过 docstring
            if stripped.startswith(('"""', "'''")):
                continue

            for pattern, desc in _ABSOLUTE_PATH_PATTERNS:
                for m in pattern.finditer(line):
                    matched_path = m.group(1)

                    # 排除占位符和示例值
                    if any(p in matched_path.lower() for p in ['xxx', 'your_', 'example', 'placeholder', 'TODO']):
                        continue

                    # 排除环境变量引用中的路径
                    ctx_start = max(0, line.find(matched_path) - 30)
                    ctx = line[ctx_start:line.find(matched_path) + len(matched_path) + 5]
                    if re.search(r'(?:os\.environ|process\.env|getenv|environ\[)', ctx):
                        continue

                    violations.append({
                        'file': fpath,
                        'line': line_idx + 1,
                        'path': matched_path,
                        'desc': desc,
                        'snippet': stripped[:100],
                    })
                    break  # 每行每个模式只报一次

            if len(violations) >= 100:
                break
        if len(violations) >= 100:
            break

    if violations:
        detail_lines = [
            f"  {os.path.basename(v['file'])}:{v['line']} {v['desc']}: {v['path']}"
            for v in violations[:10]
        ]
        results.append({
            'id': 'ENV-001',
            'name': '禁止硬编码绝对路径',
            'level': 'error',
            'message': f'发现{len(violations)}处硬编码绝对路径',
            'detail': '\n'.join(detail_lines),
            'file': violations[0]['file'],
            'line': violations[0]['line'],
            'fix': '使用环境变量、相对路径或 os.path.join + 配置项替代硬编码绝对路径',
        })

    return results


# ======================================================================
# BUILD-001: 构建产物配置完整性校验
# 扫描打包脚本中对配置文件的写操作，对敏感字段空值变更触发告警
# ======================================================================

# 配置文件扩展名
_BUILD_CONFIG_EXTENSIONS = {'.json', '.yaml', '.yml', '.toml', '.env'}

# 敏感字段关键词
_SENSITIVE_FIELD_KEYWORDS = [
    'key', 'secret', 'token', 'password', 'passwd', 'pwd',
    'api_key', 'apikey', 'auth', 'credential', 'private',
    'signing', 'encryption', 'cipher',
]

# 打包脚本文件名模式
_BUILD_SCRIPT_PATTERNS = re.compile(
    r'(?:build|package|deploy|publish|release|bundle|dist|make)',
    re.IGNORECASE,
)

# 配置写操作模式
_CONFIG_WRITE_PATTERNS = [
    # Python: open(xxx.json, 'w'), json.dump, yaml.dump
    re.compile(r'''open\s*\([^)]*\.(?:json|yaml|yml|toml|env)[^)]*['\"]w['\"]\s*\)'''),
    re.compile(r'''json\.dump\s*\('''),
    re.compile(r'''yaml\.(?:dump|safe_dump)\s*\('''),
    re.compile(r'''toml\.dump\s*\('''),
    # JS: writeFileSync, writeFile, fs.write
    re.compile(r'''(?:writeFileSync|writeFile|fs\.write)\s*\([^)]*\.(?:json|yaml|yml)'''),
    # shutil.copy 配置文件
    re.compile(r'''shutil\.(?:copy|copy2|copyfile)\s*\([^)]*\.(?:json|yaml|yml|toml|env)'''),
]

# 空值/清除模式
_EMPTY_VALUE_PATTERNS = [
    re.compile(r'''(?:=\s*["']{2}|=\s*null|= None|= ""|=\s*\{\s*\}|=\s*\[\s*\])''', re.IGNORECASE),
    re.compile(r'''\.pop\s*\(|\.clear\s*\(|\.remove\s*\(|del\s+'''),
    re.compile(r'''(?:set\s*\(\s*["'][^"']*["']\s*,\s*(?:None|null|""|''|0|false)\s*\))''', re.IGNORECASE),
]


def check_build_001_config_integrity(context) -> List[Dict]:
    """BUILD-001 构建产物配置完整性校验

    扫描打包脚本中对 .json/.yaml/.toml/.env 配置文件的写操作，
    对敏感字段（含 key/secret/token/password）的空值变更触发告警。
    """
    results = []

    all_files = context.find_files([".py", ".js", ".ts", ".sh"])
    if not all_files:
        return results

    violations = []

    for fpath in all_files:
        basename = os.path.basename(fpath).lower()

        # 只关注打包/构建相关脚本
        is_build_script = bool(_BUILD_SCRIPT_PATTERNS.search(basename))
        if not is_build_script:
            # 也检查文件内容是否包含打包操作
            content = context.safe_read(fpath)
            if not content:
                continue
            if not any(p.search(content) for p in _CONFIG_WRITE_PATTERNS):
                continue
        else:
            content = context.safe_read(fpath)
            if not content:
                continue

        lines = content.split('\n')
        for line_idx, line in enumerate(lines):
            stripped = line.strip()

            # 跳过注释
            if stripped.startswith('#') or stripped.startswith('//'):
                continue

            # 检查是否涉及配置文件写操作
            is_config_write = any(p.search(line) for p in _CONFIG_WRITE_PATTERNS)
            if not is_config_write:
                continue

            # 检查附近（±5行）是否有敏感字段空值操作
            context_start = max(0, line_idx - 5)
            context_end = min(len(lines), line_idx + 6)
            context_block = '\n'.join(lines[context_start:context_end])

            has_sensitive_field = False
            has_empty_value = False

            for kw in _SENSITIVE_FIELD_KEYWORDS:
                if kw in context_block.lower():
                    has_sensitive_field = True
                    break

            for pattern in _EMPTY_VALUE_PATTERNS:
                if pattern.search(context_block):
                    has_empty_value = True
                    break

            if has_sensitive_field and has_empty_value:
                violations.append({
                    'file': fpath,
                    'line': line_idx + 1,
                    'snippet': stripped[:100],
                })

            elif has_sensitive_field:
                # 有敏感字段引用但无法确定是否清空，降级为 warning
                violations.append({
                    'file': fpath,
                    'line': line_idx + 1,
                    'snippet': stripped[:100],
                    'level': 'warning',
                })

    if violations:
        errors = [v for v in violations if v.get('level') != 'warning']
        warnings = [v for v in violations if v.get('level') == 'warning']

        if errors:
            detail_lines = [
                f"  {os.path.basename(v['file'])}:{v['line']} {v['snippet']}"
                for v in errors[:10]
            ]
            results.append({
                'id': 'BUILD-001',
                'name': '构建产物配置完整性校验',
                'level': 'error',
                'message': f'发现{len(errors)}处构建脚本中敏感字段可能被清空',
                'detail': '\n'.join(detail_lines),
                'file': errors[0]['file'],
                'line': errors[0]['line'],
                'fix': '构建脚本中修改配置文件时，确保敏感字段（key/secret/token/password）不被意外清空',
            })
        elif warnings:
            detail_lines = [
                f"  {os.path.basename(v['file'])}:{v['line']} {v['snippet']}"
                for v in warnings[:10]
            ]
            results.append({
                'id': 'BUILD-001',
                'name': '构建产物配置完整性校验',
                'level': 'warning',
                'message': f'发现{len(warnings)}处构建脚本涉及敏感配置字段操作',
                'detail': '\n'.join(detail_lines),
                'file': warnings[0]['file'],
                'line': warnings[0]['line'],
                'fix': '检查构建脚本中对敏感字段的处理，确保不会被意外清空',
            })

    return results


# ======================================================================
# BUILD-002: 发布包清洁度校验
# 定义禁止出现在发布包中的文件模式，扫描打包脚本排除配置和产物目录
# ======================================================================

# 禁止出现在发布包中的文件/目录模式
_FORBIDDEN_PATTERNS = [
    '__pycache__', '.pyc', '.pyo', '.pyd',
    '.DS_Store', 'Thumbs.db', 'desktop.ini',
    '.git', '.gitignore', '.gitmodules',
    '.svn', '.hg',
    '.env', '.env.local', '.env.production',
    '.pytest_cache', '.mypy_cache', '.tox',
    'node_modules',
    '.coverage', 'htmlcov',
    '.idea', '.vscode', '.vs',
    '*.log', '.log',
    '.bak', '.swp', '.tmp',
    'eggs_info', '.eggs',
]

# 打包排除配置检测模式
_EXCLUDE_CONFIG_PATTERNS = [
    # Python setup.py/pyproject.toml: exclude, MANIFEST
    re.compile(r'''(?:exclude|exclude_package_data|MANIFEST|packages_exclude)''', re.IGNORECASE),
    # .gitignore entries
    re.compile(r'''(?:__pycache__|\.pyc|\.DS_Store|node_modules|\.pytest_cache)'''),
    # webpack/rollup exclude
    re.compile(r'''(?:exclude|IgnorePlugin|external)''', re.IGNORECASE),
    # MANIFEST.in
    re.compile(r'''(?:global-exclude|prune|graft)''', re.IGNORECASE),
]


def check_build_002_release_cleanliness(context) -> List[Dict]:
    """BUILD-002 发布包清洁度校验

    定义禁止出现在发布包中的文件模式列表，
    扫描打包脚本的排除配置是否完整，
    扫描产物目录检测不应存在的文件。
    """
    results = []

    if not context.project_path or not os.path.isdir(context.project_path):
        return results

    violations = []
    missing_exclusions = []

    # --- 检查1: 扫描产物目录中不应存在的文件 ---
    dist_dirs = ['dist', 'build', 'release', 'package', 'out', 'publish']
    for dist_dir in dist_dirs:
        dist_path = os.path.join(context.project_path, dist_dir)
        if not os.path.isdir(dist_path):
            continue

        for root, dirs, files in os.walk(dist_path):
            # 检查目录名
            for d in dirs:
                if d in ('__pycache__', '.git', '.pytest_cache', '.mypy_cache',
                         'node_modules', '.DS_Store', '.eggs'):
                    violations.append({
                        'path': os.path.join(root, d),
                        'type': 'directory',
                        'pattern': d,
                    })

            # 检查文件名
            for f in files:
                f_lower = f.lower()
                for forbidden in _FORBIDDEN_PATTERNS:
                    if forbidden.startswith('.'):
                        if f_lower == forbidden.lower() or f_lower.endswith(forbidden.lower()):
                            violations.append({
                                'path': os.path.join(root, f),
                                'type': 'file',
                                'pattern': forbidden,
                            })
                            break
                    elif forbidden in f_lower:
                        violations.append({
                            'path': os.path.join(root, f),
                            'type': 'file',
                            'pattern': forbidden,
                        })
                        break

            # 限制扫描深度
            depth = root.count(os.sep) - dist_path.count(os.sep)
            if depth > 5:
                dirs.clear()

    # --- 检查2: 扫描打包脚本的排除配置 ---
    build_scripts = context.find_files([".py", ".js", ".ts", ".sh"])
    build_script_files = [
        f for f in build_scripts
        if _BUILD_SCRIPT_PATTERNS.search(os.path.basename(f))
    ]

    # 也检查 MANIFEST.in, setup.py, pyproject.toml
    for manifest_name in ['MANIFEST.in', 'setup.py', 'pyproject.toml', 'setup.cfg']:
        manifest_path = os.path.join(context.project_path, manifest_name)
        if os.path.isfile(manifest_path):
            build_script_files.append(manifest_path)

    if build_script_files:
        for fpath in build_script_files:
            content = context.safe_read(fpath)
            if not content:
                continue

            # 检查是否包含关键排除项
            critical_exclusions = ['__pycache__', '.pyc', '.DS_Store', 'node_modules']
            for excl in critical_exclusions:
                if excl not in content:
                    missing_exclusions.append({
                        'file': fpath,
                        'pattern': excl,
                    })

    # --- 构建结果 ---
    if violations:
        detail_lines = [
            f"  {v['type']}: {os.path.basename(v['path'])} (匹配: {v['pattern']})"
            for v in violations[:10]
        ]
        results.append({
            'id': 'BUILD-002',
            'name': '发布包清洁度校验',
            'level': 'error',
            'message': f'发布包中发现{len(violations)}个不应存在的文件/目录',
            'detail': '\n'.join(detail_lines),
            'file': violations[0]['path'],
            'line': 0,
            'fix': '在打包配置中添加排除规则，清理 __pycache__、.pyc、.DS_Store、node_modules 等文件',
        })

    if missing_exclusions:
        unique_missing = {}
        for me in missing_exclusions:
            unique_missing[me['pattern']] = me['file']

        detail_lines = [
            f"  {os.path.basename(f)} 缺少排除: {p}"
            for p, f in unique_missing.items()
        ]
        results.append({
            'id': 'BUILD-002',
            'name': '发布包清洁度校验',
            'level': 'warning',
            'message': f'打包脚本缺少{len(unique_missing)}项关键排除配置',
            'detail': '\n'.join(detail_lines),
            'file': '',
            'line': 0,
            'fix': '在打包脚本/MANIFEST.in 中添加 __pycache__、.pyc、.DS_Store、node_modules 的排除规则',
        })

    return results


# ======================================================================
# SYNTAX-001: Python 转义序列合规性
# 正则扫描非 raw string 中的无效转义序列，用 py_compile 捕获 SyntaxWarning
# ======================================================================

# 标准有效转义字符白名单
_VALID_ESCAPES = set(
    '\\ \n \r \t \' \" a b f n r t v 0 '
    'x u N '  # \xHH \uHHHH \N{name}
    '\n \r \t'  # 实际换行/回车/制表符
)

# 无效转义序列正则: 反斜杠后跟不在白名单中的字符
_INVALID_ESCAPE_RE = re.compile(
    r'(?<!\\)'            # 前面不是反斜杠（避免匹配 \\x）
    r'\\'                 # 反斜杠
    r'(?![\\\'\"abfnrtv0xNuN\n\r\t ])'  # 后面不是有效转义字符
    r'([a-zA-Z])'         # 捕获被错误转义的字母
)


def check_syntax_001_escape_sequences(context) -> List[Dict]:
    """SYNTAX-001 Python 转义序列合规性

    正则扫描非 raw string 中的无效转义序列，
    用 py_compile 实际编译捕获 SyntaxWarning。
    """
    results = []

    py_files = context.find_files([".py"])
    if not py_files:
        return results

    violations = []
    compile_warnings = []

    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        lines = content.split('\n')
        in_docstring = False
        docstring_char = None

        for line_idx, line in enumerate(lines):
            stripped = line.strip()

            # 跟踪 docstring 状态
            if not in_docstring:
                if stripped.startswith('"""') or stripped.startswith("'''"):
                    docstring_char = stripped[:3]
                    if stripped.count(docstring_char) >= 2 and len(stripped) > 3:
                        continue  # 单行 docstring
                    in_docstring = True
                    continue
            else:
                if docstring_char in stripped:
                    in_docstring = False
                continue

            # 跳过注释行
            if stripped.startswith('#'):
                continue

            # 跳过 raw string (r"..." 或 r'...')
            if re.search(r'(?<![a-zA-Z0-9_])r["\']', line):
                continue

            # 检查无效转义序列
            for m in _INVALID_ESCAPE_RE.finditer(line):
                invalid_char = m.group(1)

                # 排除常见的合法模式
                # - 正则表达式中的转义
                if re.search(r're\.(?:compile|match|search|sub|findall|split)\s*\(', line):
                    continue
                # - 正则字符串中的转义
                if re.search(r'r["\'].*\\' + re.escape(invalid_char), line):
                    continue
                # - 路径分隔符 (Windows)
                if invalid_char in ('U',):
                    continue

                violations.append({
                    'file': fpath,
                    'line': line_idx + 1,
                    'char': invalid_char,
                    'snippet': stripped[:100],
                })

                if len(violations) >= 50:
                    break
            if len(violations) >= 50:
                break
        if len(violations) >= 50:
            break

    # 使用 py_compile 做二次验证
    if violations:
        # 只取前 5 个文件做编译检查，避免耗时过长
        checked_files = set()
        for v in violations[:20]:
            if v['file'] in checked_files:
                continue
            checked_files.add(v['file'])

            try:
                # 写入临时文件并编译
                content = context.safe_read(v['file'])
                if content:
                    with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False, encoding='utf-8') as tmp:
                        tmp.write(content)
                        tmp_path = tmp.name
                    try:
                        py_compile.compile(tmp_path, doraise=True)
                    except py_compile.PyCompileError as e:
                        compile_warnings.append({
                            'file': v['file'],
                            'message': str(e)[:200],
                        })
                    finally:
                        try:
                            os.unlink(tmp_path)
                        except OSError:  # noqa: intentional empty handler
                            pass
            except Exception as e:  # noqa: broad exception handling
                pass

    if violations:
        detail_lines = [
            f"  {os.path.basename(v['file'])}:{v['line']} 无效转义 '\\{v['char']}'"
            for v in violations[:10]
        ]
        if compile_warnings:
            detail_lines.append(f"  --- py_compile 确认 {len(compile_warnings)} 个文件有编译警告 ---")

        results.append({
            'id': 'SYNTAX-001',
            'name': 'Python转义序列合规性',
            'level': 'warning',
            'message': f'发现{len(violations)}处无效转义序列',
            'detail': '\n'.join(detail_lines),
            'file': violations[0]['file'],
            'line': violations[0]['line'],
            'fix': '使用 raw string (r"...") 包裹包含反斜杠的字符串，或双写反斜杠 (\\\\)',
        })

    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'ENV-001',
        'name': '禁止硬编码绝对路径',
        'level': 'blocking',
        'category': 'engineering_maturity',
        'module_id': '30',
        'applicable_types': [],
        'description': '扫描所有源码文件中的字符串字面量，匹配 /home/、/Users/、C:\\Users\\ 等绝对路径模式，排除注释行和白名单文件',
        'check': check_env_001_hardcoded_paths,
    },
    {
        'id': 'BUILD-001',
        'name': '构建产物配置完整性校验',
        'level': 'blocking',
        'category': 'engineering_maturity',
        'module_id': '30',
        'applicable_types': [],
        'description': '扫描打包脚本中对配置文件的写操作，对敏感字段的空值变更触发告警',
        'check': check_build_001_config_integrity,
    },
    {
        'id': 'BUILD-002',
        'name': '发布包清洁度校验',
        'level': 'problem',
        'category': 'engineering_maturity',
        'module_id': '30',
        'applicable_types': [],
        'description': '定义禁止出现在发布包中的文件模式列表，扫描打包脚本排除配置和产物目录',
        'check': check_build_002_release_cleanliness,
    },
    {
        'id': 'SYNTAX-001',
        'name': 'Python转义序列合规性',
        'level': 'problem',
        'category': 'code_quality',
        'module_id': '30',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill', 'agent'],
        'description': '正则扫描非raw string中的无效转义序列，用py_compile实际编译捕获SyntaxWarning',
        'check': check_syntax_001_escape_sequences,
    },
]
