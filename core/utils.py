#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用工具函数集 - QA质检框架
收集各模块通用的小工具，避免循环依赖
"""

import os
import re
from typing import List


# ===== 运维脚本检测（来自 architecture_detector.py） =====
OPS_SCRIPT_PATTERNS = [
    r'^patch_.*\.py$',
    r'^migrate_.*\.py$',
    r'^fix_.*\.py$',
    r'^deploy.*\.py$',
    r'^setup_.*\.py$',
    r'^init_db.*\.py$',
    r'^seed_.*\.py$',
    r'^backup_.*\.py$',
    r'^restore_.*\.py$',
    r'^cleanup_.*\.py$',
    r'^data_migration.*\.py$',
    r'^test_.*\.py$',
    r'_test\.py$',
    r'^conftest\.py$',
]


def is_ops_script(file_path: str) -> bool:
    """判断文件是否为运维脚本（补丁、迁移、测试等）"""
    basename = os.path.basename(file_path)
    for pattern in OPS_SCRIPT_PATTERNS:
        if re.match(pattern, basename, re.IGNORECASE):
            return True
    return False


# ===== Mock上下文检测（来自 context_analyzer.py） =====
MOCK_KEYWORDS = [
    'mock', 'test', 'demo', 'example', 'placeholder',
    'dummy', 'fake', 'sample', 'stub', 'fixture',
    'is_mock', 'is_test', 'is_demo', 'testing',
    'mock_key', 'test_key', 'mock_api', 'test_api',
    'fake_data', 'sample_data', 'default_value',
]

MOCK_VALUE_PATTERNS = [
    r'mock[-_]?key', r'test[-_]?key', r'demo[-_]?key',
    r'mock[-_]?secret', r'test[-_]?secret',
    r'mock[-_]?password', r'test[-_]?password',
    r'example[-_]?key', r'placeholder',
    r'xxx+', r'\*\*\*+', r'your[_-]?here',
    r'changeme', r'changethis', r'replace_me',
    r'123456', r'password123',
    r'localhost', r'127\.0\.0\.1',
]


def is_mock_context(line: str, context_lines: List[str] = None) -> bool:
    """
    判断代码行是否处于mock/test上下文中
    
    判断依据：
    1. 当前行包含mock/test/demo等关键词
    2. 附近行有is_mock=True等标记
    3. 值是明显的占位符值
    4. 位于test/mock目录
    """
    context_lines = context_lines or []
    all_text = line + '\n' + '\n'.join(context_lines)
    text_lower = all_text.lower()
    
    # 检查is_mock / is_test 等明确标记
    if re.search(r'\bis_mock\s*=\s*True\b', text_lower):
        return True
    if re.search(r'\bis_test\s*=\s*True\b', text_lower):
        return True
    if re.search(r'\bis_demo\s*=\s*True\b', text_lower):
        return True
    
    # 检查mock/test/demo等关键词（变量名或值中包含）
    mock_keyword_count = 0
    for kw in MOCK_KEYWORDS:
        if kw in text_lower:
            mock_keyword_count += 1
            if mock_keyword_count >= 2:
                return True
    
    # 检查值是否为明显的占位符
    line_lower = line.lower()
    for pat in MOCK_VALUE_PATTERNS:
        if re.search(pat, line_lower):
            # 有占位符值 + 有上下文关键词才判定，避免误伤
            if mock_keyword_count >= 1:
                return True
    
    # 函数名/类名包含mock/test
    if re.search(r'(def|class)\s+\w*(mock|test|demo|fake)\w*', text_lower, re.IGNORECASE):
        return True
    
    return False


# ===== 跨盘符安全路径（v1.23.0 新增） =====
# 保存原始os.path.relpath引用，避免monkey-patch后递归
_original_relpath = os.path.relpath

def safe_relpath(path, start=None):
    """安全的相对路径计算，Windows跨盘符时返回绝对路径
    
    v1.23.0: 修复Windows跨盘符场景（如QA工具在C盘，项目在D盘）
    os.path.relpath报ValueError: path is on mount 'D:', start on mount 'C:'
    """
    try:
        if start:
            return _original_relpath(path, start)
        return _original_relpath(path)
    except ValueError:
        # Windows跨盘符，返回绝对路径
        return os.path.abspath(path)


# ===== 以下迁移自 qa_framework.py 通用工具函数 =====


def safe_read(path: str) -> str:
    """安全读取文件，出错返回空字符串"""
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    except Exception:  # noqa: broad exception handling
        return ""


def find_files(root: str, exts: list, exclude_dirs: list, exclude_files: list) -> list:
    """递归查找指定扩展名的文件"""
    import os
    result = []
    if not root or not os.path.isdir(root):
        return result
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
        for fn in filenames:
            if any(fn.endswith(ef) for ef in exclude_files):
                continue
            if any(fn.endswith(ext) for ext in exts):
                result.append(os.path.join(dirpath, fn))
    return result


def severity_icon(level: str) -> str:
    """严重程度对应的图标"""
    return {"error": "❌", "warning": "⚠️", "info": "💡"}.get(level, "💡")
