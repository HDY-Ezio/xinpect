"""
文档规范规则集 (v5.2.0)
检测文档规范问题 - 适用于所有项目类型
包含: 函数无注释、公共API无文档、README缺失、README过时、
注释质量差等5项检查
"""

import re
import os
from typing import List, Dict, Any


# ===== DOC-001 函数无注释 =====
def check_doc_001_function_comments(context) -> List[Dict]:
    """DOC-001 函数无注释 - 公共函数无JSDoc/docstring"""
    results = []
    code_files = context.find_files([".js", ".ts", ".py", ".tsx", ".jsx"])
    issues = []

    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        ext = os.path.splitext(fpath)[1].lower()
        lines = content.split('\n')

        if ext == '.py':
            for i, line in enumerate(lines):
                m = re.match(r'\s*def\s+(\w+)\s*\(', line)
                if m:
                    func_name = m.group(1)
                    # Skip private/dunder methods
                    if func_name.startswith('_'):
                        continue
                    # Check if next non-empty line has docstring
                    has_docstring = False
                    for j in range(i + 1, min(i + 3, len(lines))):
                        next_stripped = lines[j].strip()
                        if not next_stripped:
                            continue
                        if next_stripped.startswith(('"""', "'''")):
                            has_docstring = True
                        break
                    if not has_docstring:
                        issues.append((fpath, i + 1, func_name))

        elif ext in ('.js', '.ts', '.tsx', '.jsx'):
            for i, line in enumerate(lines):
                stripped = line.strip()
                # Find exported/public functions
                is_exported = 'export' in line
                func_match = re.search(r'(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\([^)]*\)|[\w]+)\s*=>)', stripped)
                if func_match:
                    func_name = func_match.group(1) or func_match.group(2)
                    if not func_name:
                        continue
                    # Only check exported or longer functions
                    if not is_exported and len(func_name) < 5:
                        continue
                    # Check if previous lines have JSDoc comment
                    has_jsdoc = False
                    for j in range(max(0, i - 5), i):
                        if '/**' in lines[j]:
                            has_jsdoc = True
                            break
                        if lines[j].strip() and not lines[j].strip().startswith('*') and not lines[j].strip().startswith('//'):
                            break

                    if not has_jsdoc and is_exported:
                        issues.append((fpath, i + 1, func_name))

        if len(issues) > 30:
            break

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} 函数 '{n}' 无注释"
            for f, l, n in issues[:8]
        )
        results.append({
            'id': 'DOC-001',
            'name': '函数无注释',
            'level': 'info',
            'message': f'发现{len(issues)}个公共函数缺少文档注释',
            'detail': detail,
            'file': issues[0][0] if issues else '',
            'line': issues[0][1] if issues else 0,
            'fix': '为公共函数添加JSDoc/docstring注释，说明参数、返回值和用途',
        })

    return results


# ===== DOC-002 公共API无文档 =====
def check_doc_002_public_api_docs(context) -> List[Dict]:
    """DOC-002 公共API无文档 - 导出函数无说明"""
    results = []
    code_files = context.find_files([".js", ".ts", ".py", ".tsx", ".jsx"])
    issues = []

    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        ext = os.path.splitext(fpath)[1].lower()
        lines = content.split('\n')

        # Find exported items
        exported_items = []
        for i, line in enumerate(lines):
            stripped = line.strip()

            if ext == '.py':
                # Check __all__ or module-level functions
                if re.match(r'^def\s+(\w+)\s*\(', stripped) and not stripped.split()[1].startswith('_'):
                    func_name = stripped.split()[1].split('(')[0]
                    exported_items.append((func_name, i + 1))

            elif ext in ('.js', '.ts', '.tsx', '.jsx'):
                # export function/class/const
                m = re.match(r'export\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|let|var)\s+(\w+)', stripped)
                if m:
                    exported_items.append((m.group(1), i + 1))
                # module.exports
                m = re.match(r'module\.exports\s*=', stripped)
                if m:
                    exported_items.append(('module.exports', i + 1))

        # Check if exported items have documentation
        for name, line_num in exported_items:
            # Look for preceding comment
            has_doc = False
            for j in range(max(0, line_num - 6), line_num - 1):
                prev_line = lines[j].strip()
                if '/**' in prev_line or prev_line.startswith('///') or prev_line.startswith('#'):
                    has_doc = True
                    break
                if prev_line.startswith('#'):
                    has_doc = True
                    break

            if not has_doc:
                issues.append((fpath, line_num, name))

        if len(issues) > 20:
            break

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} 导出 '{n}' 无文档"
            for f, l, n in issues[:8]
        )
        results.append({
            'id': 'DOC-002',
            'name': '公共API无文档',
            'level': 'info',
            'message': f'发现{len(issues)}个导出项缺少文档说明',
            'detail': detail,
            'file': issues[0][0] if issues else '',
            'line': issues[0][1] if issues else 0,
            'fix': '为导出的函数/类/常量添加文档注释，便于其他开发者使用',
        })

    return results


# ===== DOC-003 README缺失 =====
def check_doc_003_readme_missing(context) -> List[Dict]:
    """DOC-003 README缺失 - 项目无README.md"""
    results = []

    search_paths = []
    if context.project_path and os.path.isdir(context.project_path):
        search_paths.append(context.project_path)
    if context.backend_path and os.path.isdir(context.backend_path):
        search_paths.append(context.backend_path)

    has_readme = False
    readme_variants = ['readme.md', 'README.md', 'Readme.md', 'README.txt', 'README.rst']

    for sp in search_paths:
        for variant in readme_variants:
            if os.path.isfile(os.path.join(sp, variant)):
                has_readme = True
                break
        if has_readme:
            break

    if not has_readme:
        # Only flag if project has substantial code
        code_files = context.find_files([".js", ".ts", ".py", ".tsx", ".jsx"])
        if len(code_files) >= 5:
            results.append({
                'id': 'DOC-003',
                'name': 'README缺失',
                'level': 'warning',
                'message': '项目缺少README.md文件',
                'detail': f'项目有{len(code_files)}个代码文件但缺少README文档',
                'file': '',
                'line': 0,
                'fix': '创建README.md，包含项目简介、安装方法、使用说明、API文档等',
            })

    return results


# ===== DOC-004 README过时 =====
def check_doc_004_readme_outdated(context) -> List[Dict]:
    """DOC-004 README过时 - README与实际代码不符"""
    results = []

    readme_path = None
    search_paths = []
    if context.project_path and os.path.isdir(context.project_path):
        search_paths.append(context.project_path)

    for sp in search_paths:
        for variant in ['README.md', 'readme.md']:
            path = os.path.join(sp, variant)
            if os.path.isfile(path):
                readme_path = path
                break
        if readme_path:
            break

    if not readme_path:
        return results

    content = context.safe_read(readme_path)
    if not content:
        return results

    issues = []

    # Check if README mentions files that don't exist
    file_refs = re.findall(r'`([\w./-]+\.\w+)`', content)
    for ref in file_refs:
        # Normalize path
        if ref.startswith('/'):
            ref = ref[1:]
        full_path = os.path.join(os.path.dirname(readme_path), ref)
        if not os.path.isfile(full_path) and '.' in ref:
            issues.append(f"README引用文件 {ref} 不存在")

    # Check if README mentions commands/scripts that don't exist
    script_refs = re.findall(r'(?:npm|yarn|python|node)\s+(?:run\s+)?(\w[\w-]*)', content)
    code_files = context.find_files([".js", ".ts", ".py", ".json"])

    # Check if README has been updated recently (heuristic: if it's very short for a large project)
    if len(content) < 100 and len(code_files) > 10:
        issues.append("README内容过少，可能不够详细")

    if issues:
        detail = '\n'.join(f"  {issue}" for issue in issues[:5])
        results.append({
            'id': 'DOC-004',
            'name': 'README过时',
            'level': 'info',
            'message': f'README可能存在过时信息({len(issues)}处问题)',
            'detail': detail,
            'file': readme_path,
            'line': 0,
            'fix': '更新README，确保引用的文件路径、命令和说明与实际代码一致',
        })

    return results


# ===== DOC-005 注释质量差 =====
def check_doc_005_comment_quality(context) -> List[Dict]:
    """DOC-005 注释质量差 - 注释与代码不符/过时"""
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

            # Check for low-quality comments
            # 1. Comments that just repeat the code
            if stripped.startswith('//'):
                comment_text = stripped[2:].strip().lower()
                next_code = ''
                for j in range(i + 1, min(i + 3, len(lines))):
                    if lines[j].strip():
                        next_code = lines[j].strip().lower()
                        break

                # Comment that just echoes the code
                if comment_text and next_code:
                    # Remove common words to compare
                    code_words = set(re.findall(r'\w+', next_code))
                    comment_words = set(re.findall(r'\w+', comment_text))
                    if code_words and comment_words:
                        overlap = len(code_words & comment_words) / max(len(code_words), 1)
                        if overlap > 0.8 and len(comment_words) <= 3:
                            issues.append((fpath, i + 1, 'echo', stripped[:40]))

            # 2. Very short meaningless comments
            if stripped.startswith('//') or stripped.startswith('#'):
                comment_body = stripped.lstrip('/# ').strip()
                if comment_body in ('TODO', 'FIXME', 'hack', 'temp', 'xxx', '...', '!!', '??'):
                    issues.append((fpath, i + 1, 'minimal', stripped[:40]))

            # 3. Commented-out code with no explanation
            if stripped.startswith('//') and i > 0:
                comment_body = stripped[2:].strip()
                if re.match(r'^(?:const|let|var|function|return|if|for|while)\b', comment_body):
                    # Check if there's no "TODO" or explanation
                    if not re.search(r'(TODO|FIXME|deprecated|old|removed)', stripped, re.IGNORECASE):
                        issues.append((fpath, i + 1, 'dead_comment', stripped[:40]))

        if len(issues) > 30:
            break

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} [{t}] {c}"
            for f, l, t, c in issues[:8]
        )
        results.append({
            'id': 'DOC-005',
            'name': '注释质量差',
            'level': 'info',
            'message': f'发现{len(issues)}处低质量注释',
            'detail': detail,
            'file': issues[0][0] if issues else '',
            'line': issues[0][1] if issues else 0,
            'fix': '改善注释质量：删除重复代码的注释，补充有意义的说明，清理注释掉的代码',
        })

    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'DOC-001',
        'name': '函数无注释',
        'level': 'info',
        'category': 'documentation',
        'module_id': '30',
        'applicable_types': [],
        'description': '检查公共函数是否有JSDoc/docstring注释',
        'check': check_doc_001_function_comments,
    },
    {
        'id': 'DOC-002',
        'name': '公共API无文档',
        'level': 'info',
        'category': 'documentation',
        'module_id': '30',
        'applicable_types': [],
        'description': '检查导出函数/类是否有文档说明',
        'check': check_doc_002_public_api_docs,
    },
    {
        'id': 'DOC-003',
        'name': 'README缺失',
        'level': 'warning',
        'category': 'documentation',
        'module_id': '30',
        'applicable_types': [],
        'description': '检查项目是否有README.md',
        'check': check_doc_003_readme_missing,
    },
    {
        'id': 'DOC-004',
        'name': 'README过时',
        'level': 'info',
        'category': 'documentation',
        'module_id': '30',
        'applicable_types': [],
        'description': '检查README内容是否与实际代码一致',
        'check': check_doc_004_readme_outdated,
    },
    {
        'id': 'DOC-005',
        'name': '注释质量差',
        'level': 'info',
        'category': 'documentation',
        'module_id': '30',
        'applicable_types': [],
        'description': '检查注释质量，发现重复代码注释、无意义注释等',
        'check': check_doc_005_comment_quality,
    },
]
