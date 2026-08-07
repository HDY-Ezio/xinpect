# -*- coding: utf-8 -*-
"""
依赖与发布规则集 (v5.3.0)
Brain1/Brain4/Brain7 联合补漏规则
包含: DEP-001 所有可执行文件依赖完整性、RELEASE-001 破坏性变更须有迁移说明
"""

import re
import os
import ast
from typing import List, Dict, Any, Set, Tuple


# ======================================================================
# DEP-001: 所有可执行文件依赖完整性
# 递归扫描所有 .py 文件的 import 语句（不跳过测试文件），
# 与 requirements.txt 对比，区分运行入口和测试文件
# ======================================================================

# 标准库模块（常见），用于排除非第三方依赖
_STDLIB_MODULES = {
    'os', 'sys', 're', 'json', 'math', 'time', 'datetime', 'collections',
    'itertools', 'functools', 'operator', 'string', 'textwrap', 'io',
    'pathlib', 'glob', 'shutil', 'tempfile', 'pickle', 'shelve',
    'csv', 'configparser', 'argparse', 'logging', 'unittest', 'doctest',
    'threading', 'multiprocessing', 'subprocess', 'signal', 'socket',
    'http', 'urllib', 'email', 'html', 'xml', 'hashlib', 'hmac',
    'secrets', 'base64', 'binascii', 'struct', 'codecs', 'unicodedata',
    'locale', 'gettext', 'copy', 'pprint', 'reprlib', 'enum',
    'typing', 'types', 'abc', 'contextlib', 'dataclasses', 'inspect',
    'importlib', 'pkgutil', 'ast', 'dis', 'traceback', 'warnings',
    'errno', 'ctypes', 'concurrent', 'asyncio', 'queue', 'sched',
    'decimal', 'fractions', 'random', 'statistics', 'array',
    'bisect', 'heapq', 'weakref', 'sqlite3', 'zipfile', 'tarfile',
    'gzip', 'bz2', 'lzma', 'zlib', 'fnmatch', 'stat', 'fileinput',
    'filecmp', 'difflib', 'platform', 'site', 'builtins',
    'uuid', 'pdb', 'profile', 'cProfile', 'trace', 'atexit',
    'webbrowser', 'cgi', 'cgitb', 'wsgiref', 'xmlrpc',
    'ftplib', 'poplib', 'imaplib', 'smtplib', 'telnetlib',
    'socketserver', 'select', 'selectors', 'mmap',
    'ssl', 'ipaddress', 'posixpath', 'ntpath',
    '_thread', 'posix', 'nt', 'winreg', 'msvcrt',
    'test', 'turtle', 'tkinter', 'cmd', 'readline',
    'pydoc', '__future__', 'gc', 'sysconfig', 'venv',
    'distutils', 'ensurepip', 'setuptools', 'pip',
    'numbers', 'cmath',
}

# 相对导入标记
_RELATIVE_IMPORT_RE = re.compile(r'^from\s+\.')

# import 解析正则
_IMPORT_RE = re.compile(
    r'^\s*(?:from\s+([\w.]+)\s+)?import\s+(.+?)(?:\s*#.*)?$',
    re.MULTILINE,
)
_IMPORT_ITEM_RE = re.compile(r'(\w+)(?:\s+as\s+\w+)?')

# requirements.txt 解析
_REQ_LINE_RE = re.compile(r'^([a-zA-Z0-9_.-]+)')


def _parse_requirements(project_path: str) -> Dict[str, str]:
    """解析 requirements.txt，返回 {包名小写: 版本约束}"""
    req_map = {}
    req_path = os.path.join(project_path, 'requirements.txt')
    if not os.path.isfile(req_path):
        return req_map

    try:
        with open(req_path, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or line.startswith('-'):
                    continue
                m = _REQ_LINE_RE.match(line)
                if m:
                    pkg_name = m.group(1).lower().replace('-', '_')
                    req_map[pkg_name] = line
    except Exception as e:  # noqa: broad exception handling
        pass

    return req_map


def _extract_imports(content: str) -> List[str]:
    """从 Python 源码中提取顶层模块名（排除 try/except 中的可选依赖）"""
    imported_modules = set()
    optional_modules = set()
    
    # 检测 try/except ImportError 块中的 import（可选依赖模式）
    try_except_pattern = re.compile(
        r'try\s*:.*?(except\s+(?:ImportError|ModuleNotFoundError|Exception).*?:.*?)(?=\n\S|\Z)',
        re.DOTALL | re.MULTILINE
    )
    
    for try_match in try_except_pattern.finditer(content):
        try_block = try_match.group(0)
        # 提取 try 块中的 import
        for m in _IMPORT_RE.finditer(try_block):
            from_module = m.group(1)
            import_items = m.group(2)
            if from_module:
                top_module = from_module.split('.')[0]
                optional_modules.add(top_module)
            else:
                for item in _IMPORT_ITEM_RE.finditer(import_items):
                    mod_name = item.group(1)
                    optional_modules.add(mod_name)

    # 提取所有 import，但排除可选依赖
    for m in _IMPORT_RE.finditer(content):
        from_module = m.group(1)
        import_items = m.group(2)

        if from_module:
            # from xxx.yyy import zzz
            top_module = from_module.split('.')[0]
            if top_module not in optional_modules:
                imported_modules.add(top_module)
        else:
            # import xxx, yyy
            for item in _IMPORT_ITEM_RE.finditer(import_items):
                mod_name = item.group(1)
                if mod_name not in optional_modules:
                    imported_modules.add(mod_name)

    return list(imported_modules)


def _is_test_file(fpath: str) -> bool:
    """判断文件是否为测试文件"""
    basename = os.path.basename(fpath).lower()
    norm_path = fpath.replace(os.sep, '/')

    if basename.startswith('test_') or basename.endswith('_test.py'):
        return True
    if basename.startswith('conftest'):
        return True
    if '/test/' in norm_path or '/tests/' in norm_path:
        return True
    if '/__tests__/' in norm_path:
        return True
    return False


def check_dep_001_dependency_completeness(context) -> List[Dict]:
    """DEP-001 所有可执行文件依赖完整性

    递归扫描所有 .py 文件的 import 语句（不跳过测试文件），
    与 requirements.txt 对比。
    区分运行入口（HIGH）和测试文件（MEDIUM）。
    
    v4.6.1 优化：用内存中的文件集合替代 os.path.isfile 判断内部模块，
    避免 N×M 次文件系统调用。
    """
    results = []

    py_files = context.find_files([".py"])
    if not py_files:
        return results

    project_path = context.project_path
    if not project_path:
        return results

    # 解析 requirements.txt
    req_map = _parse_requirements(project_path)

    # 构建项目内部模块集合（基于已缓存的 py_files，避免每次 os.path.isfile）
    # 格式: {module_name: True}，module_name 是 import 时的顶层包名
    _internal_modules = set()
    _internal_pkg_dirs = set()  # 包目录（有 __init__.py 的目录）
    proj_prefix = project_path.rstrip('/') + '/'
    for fpath in py_files:
        if not fpath.startswith(proj_prefix):
            continue
        rel = fpath[len(proj_prefix):]
        parts = rel.replace('\\', '/').split('/')
        # 顶层模块/包名
        if len(parts) == 1:
            mod_name = os.path.splitext(parts[0])[0]
            if mod_name != '__init__':
                _internal_modules.add(mod_name)
        else:
            top_pkg = parts[0]
            _internal_pkg_dirs.add(top_pkg)
            _internal_modules.add(top_pkg)
    
    # 收集所有第三方 import
    missing_in_entry = []   # 运行入口中缺失的依赖
    missing_in_test = []    # 测试文件中缺失的依赖
    all_third_party = set()

    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        imports = _extract_imports(content)
        is_test = _is_test_file(fpath)

        for mod in imports:
            mod_lower = mod.lower()
            top_mod = mod.split('.')[0].lower()

            # 排除标准库
            if top_mod in _STDLIB_MODULES:
                continue

            # 排除相对导入
            if mod.startswith('.'):
                continue

            # 排除项目内部模块（基于内存集合判断，O(1)）
            if top_mod in _internal_modules:
                continue

            # 检查是否在 requirements.txt 中
            mod_normalized = mod_lower.replace('-', '_')
            if mod_normalized not in req_map and mod_lower not in req_map:
                all_third_party.add(mod)
                if is_test:
                    missing_in_test.append({
                        'module': mod,
                        'file': fpath,
                    })
                else:
                    missing_in_entry.append({
                        'module': mod,
                        'file': fpath,
                    })

    # 构建结果
    if missing_in_entry:
        unique_missing = {}
        for item in missing_in_entry:
            if item['module'] not in unique_missing:
                unique_missing[item['module']] = item['file']

        detail_lines = [
            f"  {mod} (在 {os.path.basename(f)} 中使用)"
            for mod, f in list(unique_missing.items())[:10]
        ]

        results.append({
            'id': 'DEP-001',
            'name': '可执行文件依赖完整性',
            'level': 'error',
            'message': f'运行入口中引用了{len(unique_missing)}个未声明的第三方依赖',
            'detail': '\n'.join(detail_lines),
            'file': list(unique_missing.values())[0] if unique_missing else '',
            'line': 0,
            'fix': '将缺少的依赖添加到 requirements.txt 中：' + ', '.join(list(unique_missing.keys())[:10]),
        })

    if missing_in_test:
        unique_missing_test = {}
        for item in missing_in_test:
            if item['module'] not in unique_missing_test:
                unique_missing_test[item['module']] = item['file']

        detail_lines = [
            f"  {mod} (在 {os.path.basename(f)} 中使用)"
            for mod, f in list(unique_missing_test.items())[:10]
        ]

        results.append({
            'id': 'DEP-001',
            'name': '可执行文件依赖完整性',
            'level': 'warning',
            'message': f'测试文件中引用了{len(unique_missing_test)}个未声明的第三方依赖',
            'detail': '\n'.join(detail_lines),
            'file': list(unique_missing_test.values())[0] if unique_missing_test else '',
            'line': 0,
            'fix': '将测试依赖添加到 requirements.txt 或 requirements-dev.txt 中',
        })

    return results


# ======================================================================
# RELEASE-001: 破坏性变更须有迁移说明
# 检测版本间文件重命名/删除，检查CHANGELOG和import引用更新
# ======================================================================

# CHANGELOG 文件名模式
_CHANGELOG_NAMES = {'CHANGELOG.md', 'CHANGELOG', 'CHANGES.md', 'CHANGES',
                    'HISTORY.md', 'RELEASE_NOTES.md', 'RELEASE.md'}

# 文件重命名/删除检测的 Git 命令
_GIT_LOG_RENAME_RE = re.compile(r'\{(.+?)\s*=>\s*(.+?)\}')
_GIT_DIFF_RENAME_RE = re.compile(r'^rename from (.+)$', re.MULTILINE)
_GIT_DIFF_RENAME_TO_RE = re.compile(r'^rename to (.+)$', re.MULTILINE)


def _find_changelog(project_path: str) -> str:
    """查找 CHANGELOG 文件路径"""
    for name in _CHANGELOG_NAMES:
        path = os.path.join(project_path, name)
        if os.path.isfile(path):
            return path
    return ''


def _get_git_deleted_files(project_path: str) -> List[str]:
    """通过 git 获取最近版本间被删除/重命名的文件"""
    deleted_files = []

    try:
        import subprocess
        # 获取最近两个 tag 或最近5次提交间的差异
        result = subprocess.run(
            ['git', 'log', '--diff-filter=D', '--name-only', '--pretty=format:',
             '-n', '10', '--'],
            capture_output=True, text=True, timeout=3,
            cwd=project_path,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                line = line.strip()
                if line and (line.endswith('.py') or line.endswith('.js') or line.endswith('.ts')):
                    deleted_files.append(line)
    except Exception as e:  # noqa: broad exception handling
        pass

    return deleted_files


def _get_git_renamed_files(project_path: str) -> List[Tuple[str, str]]:
    """通过 git 获取最近版本间被重命名的文件"""
    renamed_files = []

    try:
        import subprocess
        result = subprocess.run(
            ['git', 'log', '--diff-filter=R', '--name-status', '--pretty=format:',
             '-n', '10', '--'],
            capture_output=True, text=True, timeout=3,
            cwd=project_path,
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                if line.startswith('R') or line.startswith('r'):
                    # 重命名记录: R100 old_name new_name
                    parts = line.split('\t')
                    if len(parts) >= 3:
                        renamed_files.append((parts[1].strip(), parts[2].strip()))
                    elif i + 1 < len(lines):
                        renamed_files.append((line, lines[i + 1].strip()))
                i += 1
    except Exception as e:  # noqa: broad exception handling
        pass

    return renamed_files


def _check_import_references(project_path: str, file_names: List[str], context=None) -> List[Dict]:
    """检查被删除/重命名的文件是否还有 import 引用"""
    stale_refs = []

    if not file_names:
        return stale_refs

    # 提取模块名
    module_names = set()
    for f in file_names:
        basename = os.path.basename(f)
        if basename.endswith('.py'):
            mod_name = os.path.splitext(basename)[0]
            if mod_name != '__init__':
                module_names.add(mod_name)
        elif basename.endswith(('.js', '.ts')):
            mod_name = os.path.splitext(basename)[0]
            module_names.add(mod_name)

    if not module_names:
        return stale_refs

    # 使用context缓存的文件列表（如果有），否则os.walk
    if context and hasattr(context, 'find_files'):
        code_files = context.find_files(['.py', '.js', '.ts', '.tsx', '.jsx'])
    else:
        code_files = []
        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in
                       {'__pycache__', 'node_modules', '.git', '.venv', 'venv',
                        'dist', 'build', '.eggs'}]
            for fname in files:
                if fname.endswith(('.py', '.js', '.ts', '.tsx', '.jsx')):
                    code_files.append(os.path.join(root, fname))

    for fpath in code_files:
        try:
            with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                file_content = f.read()
        except Exception as e:  # noqa: broad exception handling
            continue

        for mod_name in module_names:
            if re.search(rf'(?:import|from)\s+.*\b{re.escape(mod_name)}\b', file_content):
                if os.path.basename(fpath) == f'{mod_name}.py':
                    continue
                stale_refs.append({
                    'file': fpath,
                    'reference': mod_name,
                })

    return stale_refs


def _check_changelog_entries(changelog_path: str, changes: List[str]) -> List[str]:
    """检查 CHANGELOG 中是否有对应变更的条目"""
    if not changelog_path or not os.path.isfile(changelog_path):
        return changes  # 没有 CHANGELOG，所有变更都缺少记录

    try:
        with open(changelog_path, 'r', encoding='utf-8', errors='replace') as f:
            changelog_content = f.read().lower()
    except Exception as e:  # noqa: broad exception handling
        return changes

    missing = []
    for change in changes:
        basename = os.path.basename(change).lower()
        module_name = os.path.splitext(basename)[0]

        # 在 CHANGELOG 中搜索文件名或模块名
        if module_name not in changelog_content and basename not in changelog_content:
            # 也搜索通用的"破坏性变更"关键词
            if not any(kw in changelog_content for kw in
                       ['breaking', 'breaking change', 'break', '移除', '删除',
                        '迁移', 'migration', 'rename', '重命名']):
                missing.append(change)
            else:
                # 有破坏性变更的总条目但未提及具体文件
                missing.append(change)

    return missing


def check_release_001_breaking_changes(context) -> List[Dict]:
    """RELEASE-001 破坏性变更须有迁移说明

    检测版本间文件重命名/删除，
    检查是否有对应 CHANGELOG 条目，
    检查 import 引用是否全部更新。
    """
    results = []

    project_path = context.project_path
    if not project_path or not os.path.isdir(project_path):
        return results

    # 检查是否有 git 仓库
    git_dir = os.path.join(project_path, '.git')
    if not os.path.isdir(git_dir):
        return results

    # 获取被删除和重命名的文件
    deleted_files = _get_git_deleted_files(project_path)
    renamed_files = _get_git_renamed_files(project_path)

    if not deleted_files and not renamed_files:
        return results

    all_changes = []
    change_descriptions = []

    for f in deleted_files:
        all_changes.append(f)
        change_descriptions.append(f'删除: {f}')

    for old, new in renamed_files:
        all_changes.append(new)
        change_descriptions.append(f'重命名: {old} -> {new}')

    # 检查 CHANGELOG
    changelog_path = _find_changelog(project_path)
    missing_changelog = _check_changelog_entries(changelog_path, all_changes)

    # 检查 import 引用是否过时
    renamed_old_files = [old for old, _ in renamed_files]
    all_affected = deleted_files + renamed_old_files
    stale_refs = _check_import_references(project_path, all_affected, context=context)

    # 构建结果
    issues_found = []

    if missing_changelog:
        issues_found.append({
            'type': 'missing_changelog',
            'items': missing_changelog,
        })

    if stale_refs:
        issues_found.append({
            'type': 'stale_import',
            'items': stale_refs,
        })

    if not issues_found:
        return results

    # 缺少 CHANGELOG 条目
    if missing_changelog:
        detail_lines = [
            f"  {os.path.basename(f)} - 未在 CHANGELOG 中记录"
            for f in missing_changelog[:10]
        ]
        if not changelog_path:
            detail_lines.insert(0, "  [项目缺少 CHANGELOG.md 文件]")

        results.append({
            'id': 'RELEASE-001',
            'name': '破坏性变更须有迁移说明',
            'level': 'error',
            'message': f'发现{len(missing_changelog)}处文件变更缺少CHANGELOG迁移说明',
            'detail': '\n'.join(detail_lines),
            'file': changelog_path if changelog_path else '',
            'line': 0,
            'fix': '在 CHANGELOG.md 中添加破坏性变更记录，包含旧路径、新路径和迁移方法',
        })

    # 过时的 import 引用
    if stale_refs:
        unique_refs = {}
        for ref in stale_refs:
            key = f"{ref['reference']} in {os.path.basename(ref['file'])}"
            if key not in unique_refs:
                unique_refs[key] = ref

        detail_lines = [
            f"  {os.path.basename(r['file'])} 仍然引用 '{r['reference']}'"
            for r in list(unique_refs.values())[:10]
        ]

        results.append({
            'id': 'RELEASE-001',
            'name': '破坏性变更须有迁移说明',
            'level': 'error',
            'message': f'发现{len(unique_refs)}处过时的import引用（文件已删除/重命名但引用未更新）',
            'detail': '\n'.join(detail_lines),
            'file': stale_refs[0]['file'],
            'line': 0,
            'fix': '更新所有 import 引用，指向重命名后的新模块路径',
        })

    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'DEP-001',
        'name': '可执行文件依赖完整性',
        'level': 'blocking',
        'category': 'engineering_maturity',
        'module_id': '31',
        'applicable_types': ['python_backend', 'python_tool', 'flask', 'mixed', 'mixed_electron', 'skill', 'agent'],
        'description': '递归扫描所有.py文件的import语句，与requirements.txt对比，区分运行入口和测试文件',
        'check': check_dep_001_dependency_completeness,
    },
    {
        'id': 'RELEASE-001',
        'name': '破坏性变更须有迁移说明',
        'level': 'blocking',
        'category': 'engineering_maturity',
        'module_id': '31',
        'applicable_types': [],
        'description': '检测版本间文件重命名/删除，检查是否有对应CHANGELOG条目和import引用更新',
        'check': check_release_001_breaking_changes,
    },
]
