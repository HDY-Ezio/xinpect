# -*- coding: utf-8 -*-
"""
文件上传完整性检查规则集
检测文件上传接口缺少大小限制、跨文件一致性检查等
规则ID: UPL-001 - UPL-002

归脑: module_id = '2'（Brain 2 安全）
"""

import os
import re
from typing import List, Dict, Any, Tuple


# ============================================================
# 上传相关模式
# ============================================================

# 文件上传接口标识
_UPLOAD_PATTERNS = [
    re.compile(r'request\.files'),
    re.compile(r'request\.files\[.*\]'),
    re.compile(r'file\.save\s*\('),
    re.compile(r'UploadedFile'),
    re.compile(r'upload_file|upload_image|upload_attachment', re.IGNORECASE),
    re.compile(r'werkzeug\.datastructures\.FileStorage'),
    re.compile(r'@.*route.*(?:upload|file|image|attachment)', re.IGNORECASE),
    re.compile(r'Django.*FileField|forms\.FileField|forms\.ImageField', re.IGNORECASE),
]

# 大小限制检查标识
_SIZE_LIMIT_PATTERNS = [
    re.compile(r'content_length'),
    re.compile(r'MAX_CONTENT_LENGTH'),
    re.compile(r'MAX_UPLOAD_SIZE'),
    re.compile(r'file_size|filesize|file\.size', re.IGNORECASE),
    re.compile(r'len\s*\(\s*file\s*\.\s*read'),
    re.compile(r'os\.path\.getsize'),
    re.compile(r'content_length\s*[<>=]'),
    re.compile(r'\.content_length\s*>\s*\d+'),
    re.compile(r'size\s*[<>=]+\s*\d+'),
    re.compile(r'MAX_FILE_SIZE'),
]

# 文件扩展名检查标识
_EXT_CHECK_PATTERNS = [
    re.compile(r'allowed_extensions|ALLOWED_EXTENSIONS|allowed_ext'),
    re.compile(r'\.filename.*\.split|\.filename.*\.rsplit|secure_filename'),
    re.compile(r'mimetype|mimes|file\.content_type'),
    re.compile(r'extension\s*(?:in|==|not in)'),
    re.compile(r'file_ext|file_extension', re.IGNORECASE),
]


def _find_upload_functions(content: str) -> list:
    """找到所有包含文件上传逻辑的函数及其行号范围"""
    functions = []
    lines = content.split('\n')

    # 找到所有函数定义
    func_starts = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('def ') or stripped.startswith('async def '):
            func_starts.append(i)

    if not func_starts:
        return functions

    for idx, start in enumerate(func_starts):
        # 函数结束行：下一个函数开始行或文件末尾
        end = func_starts[idx + 1] if idx + 1 < len(func_starts) else len(lines)
        func_body = '\n'.join(lines[start:end])
        func_name_match = re.match(r'(?:async\s+)?def\s+(\w+)', lines[start].strip())
        func_name = func_name_match.group(1) if func_name_match else f'func_line_{start + 1}'

        # 检查函数内是否包含上传逻辑
        has_upload = any(p.search(func_body) for p in _UPLOAD_PATTERNS)
        if not has_upload:
            continue

        has_size_limit = any(p.search(func_body) for p in _SIZE_LIMIT_PATTERNS)
        has_ext_check = any(p.search(func_body) for p in _EXT_CHECK_PATTERNS)

        functions.append({
            'name': func_name,
            'start_line': start + 1,
            'end_line': end,
            'has_size_limit': has_size_limit,
            'has_ext_check': has_ext_check,
            'func_body': func_body,
        })

    return functions


def check_upload_no_size_limit(context) -> List[Dict]:
    """UPL-001: 检测文件上传接口缺少大小限制"""
    results = []

    py_files = context.get_backend_py_files()
    if not py_files:
        return results

    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        content_lines = content.split('\n')
        upload_funcs = _find_upload_functions(content)

        for func_info in upload_funcs:
            if not func_info['has_size_limit']:
                func_line = func_info['start_line']
                line_text = content_lines[func_line - 1] if func_line - 1 < len(content_lines) else ""

                results.append({
                    'id': 'UPL-001',
                    'name': '文件上传安全-缺少大小限制',
                    'level': 'error',
                    'message': f'函数 {func_info["name"]}() 处理文件上传但未检查文件大小，可能被上传大文件导致 DoS',
                    'file': fpath,
                    'line': func_line,
                    'snippet': line_text.strip()[:120],
                    'fix': '添加文件大小检查：\n'
                           'MAX_SIZE = 10 * 1024 * 1024  # 10MB\n'
                           'if file.content_length > MAX_SIZE:\n'
                           '    return jsonify({"error": "File too large"}), 413',
                })

    return results


def check_upload_consistency(context) -> List[Dict]:
    """UPL-002: 跨文件一致性 - 检查所有上传接口是否都有大小限制"""
    results = []

    py_files = context.get_backend_py_files()
    if not py_files:
        return results

    all_upload_funcs = []
    total_with_limit = 0
    total_without_limit = 0
    funcs_without_limit = []

    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        upload_funcs = _find_upload_functions(content)

        for func_info in upload_funcs:
            all_upload_funcs.append(func_info)
            if func_info['has_size_limit']:
                total_with_limit += 1
            else:
                total_without_limit += 1
                funcs_without_limit.append({
                    'file': fpath,
                    'name': func_info['name'],
                    'line': func_info['start_line'],
                })

    # 如果只有一个上传接口或全部都有/没有大小限制，则不报一致性
    total = total_with_limit + total_without_limit
    if total <= 1:
        return results

    if total_without_limit == 0:
        return results

    # 计算覆盖率
    coverage = total_with_limit / total * 100 if total > 0 else 0

    # 报告一致性检查结果
    content_lines_map = {}
    for func_info in funcs_without_limit:
        fpath = func_info['file']
        if fpath not in content_lines_map:
            content = context.safe_read(fpath)
            if content:
                content_lines_map[fpath] = content.split('\n')
            else:
                content_lines_map[fpath] = []

        lines = content_lines_map.get(fpath, [])
        line_no = func_info['line']
        line_text = lines[line_no - 1] if line_no - 1 < len(lines) else ""

        results.append({
            'id': 'UPL-002',
            'name': '文件上传安全-跨接口一致性',
            'level': 'warning',
            'message': (
                f'项目共 {total} 个上传接口，仅 {total_with_limit} 个有大小限制 '
                f'（覆盖率 {coverage:.0f}%）。'
                f'函数 {func_info["name"]}() 缺少大小限制。'
            ),
            'file': fpath,
            'line': line_no,
            'snippet': line_text.strip()[:120],
            'fix': '统一为所有上传接口添加文件大小限制，建议使用统一的装饰器或中间件',
        })

    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'UPL-001',
        'name': '文件上传安全-缺少大小限制',
        'level': 'error',
        'category': 'upload_safety',
        'module_id': '2',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测文件上传接口未限制文件大小，可能被大文件DoS攻击',
        'check': check_upload_no_size_limit,
    },
    {
        'id': 'UPL-002',
        'name': '文件上传安全-跨接口一致性',
        'level': 'warning',
        'category': 'upload_safety',
        'module_id': '2',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '跨文件一致性检查：统计所有上传接口中有/无大小限制的比例',
        'check': check_upload_consistency,
    },
]
