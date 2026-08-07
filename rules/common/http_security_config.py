# -*- coding: utf-8 -*-
"""
HTTP安全配置检查规则集
检测CORS配置、安全响应头缺失、Debug模式在生产代码等
规则ID: CFG-001 - CFG-003

归脑: module_id = '2'（Brain 2 安全）
"""

import os
import re
from typing import List, Dict, Any

# v4.4 误报治理: 复用上下文感知工具
try:
    from core.code_context_utils import (
        find_python_docstring_ranges, find_python_rules_list_range,
        is_line_in_range,
    )
    _HAS_CODE_CONTEXT_UTILS = True
except ImportError:  # noqa: 兼容旧版本
    _HAS_CODE_CONTEXT_UTILS = False


def _get_skip_ranges(lines):
    """v4.4: 计算需要跳过的行范围（docstring + RULES 列表）"""
    if not _HAS_CODE_CONTEXT_UTILS:
        return [], None
    doc_ranges = find_python_docstring_ranges(lines)
    rules_range = find_python_rules_list_range(lines)
    return doc_ranges, rules_range


def _should_skip(lineno, doc_ranges, rules_range):
    """v4.4: 判断行是否应跳过"""
    if doc_ranges and is_line_in_range(lineno, doc_ranges):
        return True
    if rules_range and rules_range[0] <= lineno <= rules_range[1]:
        return True
    return False


# ============================================================
# CFG-001: CORS Access-Control-Allow-Origin: *
# ============================================================

_CORS_WILDCARD_PATTERNS = [
    re.compile(r'Access-Control-Allow-Origin.*\*', re.IGNORECASE),
    re.compile(r'access_control_allow_origin.*\*', re.IGNORECASE),
    re.compile(r'allow_origin\s*[=:]\s*["\']?\*', re.IGNORECASE),
    re.compile(r'CORS_ALLOW_ALL_ORIGINS\s*=\s*True', re.IGNORECASE),
    re.compile(r'after_request.*Access-Control-Allow-Origin.*\*', re.IGNORECASE | re.DOTALL),
    re.compile(r'@app\.after_request[\s\S]{0,500}Access-Control-Allow-Origin["\']?\s*:\s*["\']?\*', re.IGNORECASE),
    re.compile(r'response\.headers\[.*Access-Control-Allow-Origin.*\]\s*=\s*["\']?\*', re.IGNORECASE),
    re.compile(r'return\s+["\']?\*["\']?\s*,\s*200', re.IGNORECASE),
]


def check_cors_wildcard(context) -> List[Dict]:
    """CFG-001: 检测 CORS 配置了通配符 *

    v4.4 误报治理:
    - 跳过注释行
    - 跳过 Python docstring 三重引号内的示例
    - 跳过规则文件 RULES 定义列表（自指）
    """
    results = []

    py_files = context.get_backend_py_files()
    if not py_files:
        return results

    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        content_lines = content.split('\n')
        seen_lines = set()

        # v4.4: 预计算跳过范围
        doc_ranges, rules_range = _get_skip_ranges(content_lines)

        for pattern in _CORS_WILDCARD_PATTERNS:
            for m in pattern.finditer(content):
                line_no = content[:m.start()].count('\n') + 1
                if line_no in seen_lines:
                    continue
                line_text = content_lines[line_no - 1] if line_no - 1 < len(content_lines) else ""
                if line_text.strip().startswith('#'):
                    continue
                # v4.4: 跳过 docstring / RULES 列表
                if _should_skip(line_no, doc_ranges, rules_range):
                    continue
                # v4.4: 跳过正则/字符串变量定义行（规则文件自身的模式定义）
                stripped_line = line_text.strip()
                if re.match(r'^[\w_]+\s*=\s*(re\.compile|["\'])', stripped_line):
                    continue
                # v4.4: 跳过列表/元组中的模式定义
                if re.match(r'^\s*[\({\[]?\s*re\.compile\s*\(', stripped_line):
                    continue
                # v4.4: 跳过字典值/字符串内部的匹配（'message': '...CORS...'）
                # 如果匹配位置在引号字符串内部，跳过
                match_col = m.start() - sum(len(l)+1 for l in content_lines[:line_no-1])
                before_match = line_text[:max(0, match_col)]
                # 统计前面未闭合的引号（简化判断）
                single_quotes = before_match.count("'") % 2
                double_quotes = before_match.count('"') % 2
                if single_quotes or double_quotes:
                    continue
                # v4.4: 行内注释后的内容跳过（# 之后）
                hash_pos = line_text.find('#')
                if hash_pos > 0 and match_col > hash_pos:
                    continue

                seen_lines.add(line_no)
                results.append({
                    'id': 'CFG-001',
                    'name': 'HTTP安全配置-CORS通配符Origin',
                    'level': 'error',
                    'message': 'CORS配置 Access-Control-Allow-Origin 为 *，允许任意来源跨域请求，存在安全风险',
                    'file': fpath,
                    'line': line_no,
                    'snippet': line_text.strip()[:120],
                    'fix': '将 * 替换为具体的允许域名列表，例如: "https://example.com"',
                })

    return results


# ============================================================
# CFG-002: 缺少安全响应头
# ============================================================

_SECURITY_HEADERS = {
    'X-Content-Type-Options': re.compile(r'X-Content-Type-Options', re.IGNORECASE),
    'X-Frame-Options': re.compile(r'X-Frame-Options', re.IGNORECASE),
    'Strict-Transport-Security': re.compile(r'Strict-Transport-Security|HSTS', re.IGNORECASE),
}

# 检测是否有设置安全头的中间件/装饰器
_AFTER_REQUEST_PATTERN = re.compile(
    r'(?:@app\.after_request|@blueprint\.after_request|'
    r'def\s+\w*after_request\w*|'
    r'class\s+\w*Middleware\w*|'
    r'@app\.before_request|'
    r'after_response|SecurityHeadersMiddleware)',
    re.IGNORECASE,
)

_HEADER_SET_PATTERN = re.compile(
    r'(?:response\.headers\[.*?(X-Content-Type-Options|X-Frame-Options|Strict-Transport-Security)'
    r'|headers\.set\(.*?(X-Content-Type-Options|X-Frame-Options|Strict-Transport-Security)'
    r'|headers\["?(X-Content-Type-Options|X-Frame-Options|Strict-Transport-Security))',
    re.IGNORECASE,
)


def check_missing_security_headers(context) -> List[Dict]:
    """CFG-002: 检测缺少安全响应头（X-Content-Type-Options, X-Frame-Options, HSTS）

    v4.4 误报治理:
    - 注释/docstring/RULES 列表中的安全头示例不计入统计
    """
    results = []

    py_files = context.get_backend_py_files()
    if not py_files:
        return results

    # 收集项目中所有文件的内容，判断是否有全局安全头设置
    has_after_request = False
    headers_set = set()
    app_files = []  # 可能是主应用文件

    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        content_lines = content.split('\n')
        # v4.4: 计算跳过范围，过滤注释/docstring/RULES中的匹配
        doc_ranges, rules_range = _get_skip_ranges(content_lines)

        def _code_line(lineno):
            """判断行是否在代码区域（非注释非docstring非RULES）"""
            line = content_lines[lineno-1] if lineno-1 < len(content_lines) else ''
            if line.strip().startswith('#'):
                return False
            if _should_skip(lineno, doc_ranges, rules_range):
                return False
            return True

        # 只检查可能的入口文件（包含 app 定义的文件）
        if re.search(r'(?:Flask|Django|FastAPI|app\s*=\s*)', content):
            app_files.append((fpath, content))

        # v4.4: 只统计代码行里的 after_request
        for m in _AFTER_REQUEST_PATTERN.finditer(content):
            lineno = content[:m.start()].count('\n') + 1
            if _code_line(lineno):
                has_after_request = True
                break

        # v4.4: 只统计代码行里的安全头设置
        for m in _HEADER_SET_PATTERN.finditer(content):
            lineno = content[:m.start()].count('\n') + 1
            if not _code_line(lineno):
                continue
            for group in m.groups():
                if group:
                    headers_set.add(group.lower())

    # 如果项目有 after_request 且设置了安全头，则不报告
    if has_after_request and len(headers_set) >= 3:
        return results

    # 确定缺失的头
    missing_headers = []
    for header_name, pattern in _SECURITY_HEADERS.items():
        if header_name.lower() not in headers_set:
            missing_headers.append(header_name)

    if not missing_headers:
        return results

    # 对每个应用文件报告缺失
    for fpath, content in app_files:
        if not content:
            continue

        content_lines = content.split('\n')
        # 找到 app 定义行或文件开头
        app_line = 1
        for i, line in enumerate(content_lines):
            if re.search(r'(?:Flask\s*\(|app\s*=\s*|from\s+flask\s+import)', line):
                app_line = i + 1
                break

        missing_str = ', '.join(missing_headers)
        results.append({
            'id': 'CFG-002',
            'name': 'HTTP安全配置-缺少安全响应头',
            'level': 'warning',
            'message': f'缺少安全响应头: {missing_str}，可能被利用进行点击劫持/MIME嗅探/降级攻击',
            'file': fpath,
            'line': app_line,
            'snippet': content_lines[app_line - 1].strip()[:120] if app_line - 1 < len(content_lines) else '',
            'fix': '添加 after_request 中间件设置安全头：\n'
                   '@app.after_request\n'
                   'def set_security_headers(response):\n'
                   '    response.headers["X-Content-Type-Options"] = "nosniff"\n'
                   '    response.headers["X-Frame-Options"] = "DENY"\n'
                   '    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"\n'
                   '    return response',
        })

    return results


# ============================================================
# CFG-003: Debug 模式在生产代码中（增强版）
# ============================================================

_DEBUG_PATTERNS = [
    # Flask debug=True
    (re.compile(r'app\.run\s*\([^)]*debug\s*=\s*True'), 'Flask app.run() 设置了 debug=True'),
    # os.environ 设置了 production 但仍有 debug
    (re.compile(r'FLASK_ENV\s*=\s*["\']?production'), None),  # 标记行，后面再检查
    # Django DEBUG = True 在 settings
    (re.compile(r'^\s*DEBUG\s*=\s*True\s*$', re.MULTILINE), 'Django settings 中 DEBUG = True'),
    # Werkzeug debugger 显式启用
    (re.compile(r'(?:Werkzeug|werkzeug\.debug)\s*\.\s*DebuggedApplication'), 'Werkzeug DebuggedApplication 被显式启用'),
    # Flask app.debug = True
    (re.compile(r'app\.debug\s*=\s*True'), 'Flask app.debug 被设置为 True'),
    # 环境变量 production 后仍然 debug
    (re.compile(r'(?:ENV|FLASK_ENV|DJANGO_SETTINGS_MODULE).*production[\s\S]{0,200}debug\s*=\s*True', re.DOTALL),
     '生产环境配置中仍存在 debug=True'),
]


def check_debug_in_production(context) -> List[Dict]:
    """CFG-003: 增强版检测 - 生产环境代码中的 Debug 模式

    v4.4 误报治理:
    - 跳过注释行
    - 跳过 Python docstring 三重引号内的示例
    - 跳过规则文件 RULES 定义列表（自指）
    """
    results = []

    py_files = context.get_backend_py_files()
    if not py_files:
        return results

    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        content_lines = content.split('\n')

        # v4.4: 预计算跳过范围
        doc_ranges, rules_range = _get_skip_ranges(content_lines)

        # 检查文件是否在生产/部署相关路径中
        is_prod_file = bool(re.search(r'(?:deploy|prod|production|settings)', fpath, re.IGNORECASE))

        # 检查是否有生产环境标识（只统计代码行里的）
        has_prod_env = False
        for m in re.finditer(r'FLASK_ENV\s*=\s*["\']?production|ENV\s*=\s*["\']?production', content):
            lineno = content[:m.start()].count('\n') + 1
            line = content_lines[lineno-1] if lineno-1 < len(content_lines) else ''
            if not line.strip().startswith('#') and not _should_skip(lineno, doc_ranges, rules_range):
                has_prod_env = True
                break

        seen_lines = set()

        for pattern, desc in _DEBUG_PATTERNS:
            if desc is None:
                continue
            for m in pattern.finditer(content):
                line_no = content[:m.start()].count('\n') + 1
                if line_no in seen_lines:
                    continue
                line_text = content_lines[line_no - 1] if line_no - 1 < len(content_lines) else ""
                if line_text.strip().startswith('#'):
                    continue
                # v4.4: 跳过 docstring / RULES 列表
                if _should_skip(line_no, doc_ranges, rules_range):
                    continue
                # v4.4: 跳过字符串内部的匹配
                match_col = m.start() - sum(len(l)+1 for l in content_lines[:line_no-1])
                before_match = line_text[:max(0, match_col)]
                if (before_match.count("'") % 2) or (before_match.count('"') % 2):
                    continue
                # v4.4: 跳过行内注释后的内容
                hash_pos = line_text.find('#')
                if hash_pos > 0 and match_col > hash_pos:
                    continue
                # v4.4: 跳过正则模式定义行
                if re.match(r'^\s*[\({\[]?\s*re\.compile\s*\(', line_text.strip()):
                    continue

                seen_lines.add(line_no)

                # 增强：如果是生产文件或生产环境标识，提升严重级别
                severity = 'error' if (is_prod_file or has_prod_env) else 'warning'

                results.append({
                    'id': 'CFG-003',
                    'name': 'HTTP安全配置-生产环境Debug模式',
                    'level': severity,
                    'message': desc + ('（生产环境）' if (is_prod_file or has_prod_env) else ''),
                    'file': fpath,
                    'line': line_no,
                    'snippet': line_text.strip()[:120],
                    'fix': '使用环境变量控制debug模式：\n'
                           'debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"\n'
                           'app.run(debug=debug)',
                })

    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'CFG-001',
        'name': 'HTTP安全配置-CORS通配符Origin',
        'level': 'error',
        'category': 'http_security',
        'module_id': '2',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测 CORS 配置 Access-Control-Allow-Origin 为通配符 *，允许任意来源跨域',
        'check': check_cors_wildcard,
    },
    {
        'id': 'CFG-002',
        'name': 'HTTP安全配置-缺少安全响应头',
        'level': 'warning',
        'category': 'http_security',
        'module_id': '2',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测缺少 X-Content-Type-Options/X-Frame-Options/HSTS 等安全响应头',
        'check': check_missing_security_headers,
    },
    {
        'id': 'CFG-003',
        'name': 'HTTP安全配置-生产环境Debug模式',
        'level': 'warning',
        'category': 'http_security',
        'module_id': '2',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '增强检测：生产环境中 debug=True、FLASK_ENV=production 时仍有 debug 等',
        'check': check_debug_in_production,
    },
]
