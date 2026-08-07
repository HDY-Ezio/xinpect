"""安全审计规则集 - 子模块
从 security.py 拆分而来，包含以下规则: 3.1, 3.3, 3.6, 3.7

v4.4 误报治理:
- 所有基于字符串匹配的安全检测均跳过注释、docstring
- SQL注入/路径穿越/SSRF 检测使用上下文感知匹配
- 对 Python 文件额外跳过 RULES 定义列表（规则自指）
"""

"""
安全审计规则集 (M3)
通用安全检查 - 适用于所有项目类型
包含: SQL注入、敏感信息泄露、XSS、鉴权绕过、CORS/CSRF等12项检查
"""

import re
import os
from typing import List, Dict, Any

# v4.4: 上下文感知匹配工具
try:
    from core.code_context_utils import (
        find_python_docstring_ranges, find_python_rules_list_range,
        is_line_in_range, search_in_code,
    )
    _HAS_CODE_CONTEXT_UTILS = True
except ImportError:  # noqa: 兼容旧版本
    _HAS_CODE_CONTEXT_UTILS = False


def _get_lang(fpath: str) -> str:
    """根据扩展名获取语言标识"""
    ext = os.path.splitext(fpath)[1].lower()
    if ext == '.py':
        return 'py'
    return 'js'


# ===== 3.1 SQL注入检测 =====
def check_3_1_sql_injection(context) -> List[Dict]:
    """3.1 SQL注入检测 - 检查代码中是否存在SQL注入风险

    v4.4 误报治理:
    - 跳过注释行（# / // 开头）
    - 跳过 Python 三重引号 docstring（规则文档/说明中的SQL示例不算）
    - 跳过规则文件的 RULES = [...] 定义列表（自指）
    - 跳过字符串字面量内部的匹配（使用 search_in_code）
    - 保留 logger/response/raise 等非SQL上下文过滤
    """
    results = []

    # skill/agent类型是CLI工具或本地脚本，无数据库服务端，跳过SQL注入检测
    if context.project_type in ("skill", "agent"):
        return results

    all_files = []
    if context.project_path and os.path.isdir(context.project_path):
        if context.is_web_frontend():
            all_files += context.find_files([".js", ".wxml", ".wxss", ".ts", ".tsx", ".jsx"])
        else:
            all_files += context.find_files([".js", ".wxml", ".wxss"])
    all_files += context.get_backend_py_files()

    if not all_files:
        return results

    sql_injection_patterns = [
        (re.compile(r'(\+|\%)\s*["\']?\w+["\']?\s*\+\s*["\'](SELECT|INSERT|UPDATE|DELETE)', re.IGNORECASE),
         '字符串拼接SQL（变量+SQL）'),
        # v4.4: 补充反方向 — SQL字符串在前、变量在后的拼接
        (re.compile(r'["\'](SELECT|INSERT|UPDATE|DELETE)\b[^"\']*["\']\s*\+\s*["\']?\w+', re.IGNORECASE),
         '字符串拼接SQL（SQL+变量）'),
        (re.compile(r'f["\'].*?\{.*?\}.*?(SELECT|INSERT|UPDATE|DELETE)', re.IGNORECASE),
         'f-string拼接SQL'),
        (re.compile(r'format\(.*?\).*?(SELECT|INSERT|UPDATE|DELETE)', re.IGNORECASE),
         'format拼接SQL'),
    ]

    for fpath in all_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        file_lines = content.split('\n')
        lang = _get_lang(fpath)

        # v4.4: Python 预计算跳过范围
        docstring_ranges = []
        rules_list_range = None
        if lang == 'py' and _HAS_CODE_CONTEXT_UTILS:
            docstring_ranges = find_python_docstring_ranges(file_lines)
            rules_list_range = find_python_rules_list_range(file_lines)

        def _is_skip_line(lineno: int) -> bool:
            """判断该行是否应跳过（docstring / RULES列表）"""
            if docstring_ranges and is_line_in_range(lineno, docstring_ranges):
                return True
            if rules_list_range and rules_list_range[0] <= lineno <= rules_list_range[1]:
                return True
            return False

        for pattern, desc in sql_injection_patterns:
            for m in pattern.finditer(content):
                line_num = content[:m.start()].count('\n') + 1
                line_text = file_lines[line_num-1] if line_num-1 < len(file_lines) else ""

                # v4.4: 跳过 docstring / RULES 列表
                if _is_skip_line(line_num):
                    continue

                # 跳过注释行
                stripped = line_text.strip()
                if stripped.startswith('#') or stripped.startswith('//') or stripped.startswith('*'):
                    continue

                # Skip if line has # safe: comment (project convention for safe SQL)
                if '# safe:' in line_text.lower() or '# safe' in line_text.lower():
                    continue

                # Skip if the matched line is inside an execute() call with >=2 args (parameterized query)
                _ctx_start = max(0, line_num - 6)
                _ctx_end = min(len(file_lines), line_num + 6)
                check_ctx = '\n'.join(file_lines[_ctx_start:_ctx_end])
                if re.search(r'\.execute\s*\([^)]*,', check_ctx):
                    continue

                # Skip non-SQL context: f-string in logger/response/raise (not actual SQL)
                lower_line = line_text.lower()
                non_sql_indicators = [
                    'logger.', 'logging.', 'print(', 'console.',
                    'response_error', 'response_success', 'response_',
                    'raise ', 'return f"', "return f'",
                    'change_summary', 'summary',
                ]
                if any(ns in lower_line for ns in non_sql_indicators):
                    continue
                # Also skip if f-string is in a function call that's not execute
                if re.search(r'(logger|log|print|raise|return|wx\.|response|summary|toast|msg|message)\s*[\.(]\s*f["\']', line_text, re.IGNORECASE):
                    continue

                results.append({
                    'id': '3.1',
                    'name': 'SQL注入检测',
                    'level': 'error',
                    'message': f'存在SQL注入风险: {desc}',
                    'file': fpath,
                    'line': line_num,
                    'snippet': line_text.strip()[:100],
                    'fix': '使用参数化查询(prepared statement)替代字符串拼接',
                })
                break  # 每个文件每个模式只报一次

    return results


# ===== 3.2 敏感信息泄露 =====


# ===== 3.3 XSS风险 =====
def check_3_3_xss(context) -> List[Dict]:
    """3.3 XSS风险 - 检查是否存在跨站脚本攻击风险

    v4.4 误报治理:
    - 跳过注释行
    - 跳过 Python docstring 内的示例
    - 跳过规则文件 RULES 定义列表（自指）
    - 确保匹配在代码部分（不在字符串内部）
    """
    results = []

    # skill/agent类型是CLI工具或本地脚本，无Web前端，跳过XSS检测
    if context.project_type in ("skill", "agent"):
        return results

    fe_files = context.find_files([".js", ".ts", ".html", ".wxml", ".tsx", ".jsx"])

    xss_patterns = [
        (re.compile(r'document\.write\s*\('), 'document.write可能导致XSS'),
        (re.compile(r'innerHTML\s*[+]?='), 'innerHTML可能导致XSS'),
        (re.compile(r'eval\s*\('), 'eval执行动态代码'),
        (re.compile(r'\.html\s*\('), 'jQuery .html()可能导致XSS'),
        (re.compile(r'dangerouslySetInnerHTML'), 'React dangerouslySetInnerHTML'),
    ]

    for fpath in fe_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        lines = content.split('\n')
        lang = _get_lang(fpath)

        # v4.4: Python/JS 预计算跳过范围
        docstring_ranges = []
        rules_list_range = None
        if lang == 'py' and _HAS_CODE_CONTEXT_UTILS:
            docstring_ranges = find_python_docstring_ranges(lines)
            rules_list_range = find_python_rules_list_range(lines)

        def _is_skip_line(lineno: int) -> bool:
            if docstring_ranges and is_line_in_range(lineno, docstring_ranges):
                return True
            if rules_list_range and rules_list_range[0] <= lineno <= rules_list_range[1]:
                return True
            return False

        file_has_issue = False
        for pattern, desc in xss_patterns:
            matches = []
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith('//') or stripped.startswith('#') or stripped.startswith('/*') or stripped.startswith('*'):
                    continue
                if _is_skip_line(i):
                    continue
                # v4.4: 上下文感知匹配
                if _HAS_CODE_CONTEXT_UTILS:
                    m = search_in_code(line, pattern, lang)
                    if m:
                        matches.append((i, line.strip()[:80]))
                else:
                    if pattern.search(line):
                        matches.append((i, line.strip()[:80]))
                if len(matches) > 5:
                    break

            if matches:
                results.append({
                    'id': '3.3',
                    'name': 'XSS风险',
                    'level': 'warning',
                    'message': f'存在XSS风险: {desc} (共{len(matches)}处)',
                    'file': fpath,
                    'line': matches[0][0],
                    'snippet': matches[0][1],
                    'fix': '对用户输入进行转义，使用textContent替代innerHTML，避免使用eval',
                })
                file_has_issue = True
                break  # 每个文件只报一次

    return results


# ===== 3.4 鉴权绕过 =====


# ===== 3.6 路径穿越检测 =====
def check_3_6_path_traversal(context) -> List[Dict]:
    """3.6 路径穿越检测 - 检查是否存在路径穿越风险

    v4.4 误报治理:
    - 跳过注释行
    - 跳过 Python docstring 三重引号内的示例
    - 跳过规则文件 RULES = [...] 定义列表（自指）
    - 保留 # safe: 标记的安全豁免
    """
    results = []

    all_files = []
    if context.project_path and os.path.isdir(context.project_path):
        if context.is_web_frontend():
            all_files += context.find_files([".js", ".ts", ".tsx", ".jsx"])
        else:
            all_files += context.find_files([".js", ".wxml", ".wxss"])
    all_files += context.get_backend_py_files()

    py_files = [f for f in all_files if f.endswith('.py')]

    path_errors = []
    path_warnings = []

    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        lines = content.split('\n')

        # v4.4: Python 预计算跳过范围
        docstring_ranges = []
        rules_list_range = None
        if _HAS_CODE_CONTEXT_UTILS:
            docstring_ranges = find_python_docstring_ranges(lines)
            rules_list_range = find_python_rules_list_range(lines)

        def _is_skip_line(lineno: int) -> bool:
            if docstring_ranges and is_line_in_range(lineno, docstring_ranges):
                return True
            if rules_list_range and rules_list_range[0] <= lineno <= rules_list_range[1]:
                return True
            return False

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            # v4.4: 跳过 docstring / RULES 列表
            if _is_skip_line(i):
                continue
            # Detect f-string with variable interpolation in file operations
            if re.search(r'(open|os\.path\.join|shutil\.\w+|send_file)\s*\([^)]*f["\'][^"\']*\{', line):
                ctx_lines = '\n'.join(lines[max(0, i-3):i+2])
                has_normalize = bool(re.search(r'os\.path\.(realpath|abspath|normpath|commonpath)', ctx_lines))
                has_safe = '# safe:' in line or (i >= 2 and '# safe:' in lines[i-2])
                if has_safe:
                    continue
                if has_normalize:
                    path_warnings.append(f"{os.path.relpath(fpath)}:{i} 路径拼接已有规范化校验")
                else:
                    path_errors.append(f"{os.path.relpath(fpath)}:{i} f-string路径拼接无校验")
            # Detect string concatenation with variable in file paths
            elif re.search(r'(open|os\.path\.join)\s*\([^)]*\+\s*\w', line):
                ctx_lines = '\n'.join(lines[max(0, i-3):i+2])
                has_normalize = bool(re.search(r'os\.path\.(realpath|abspath|normpath|commonpath)', ctx_lines))
                has_safe = '# safe:' in line or (i >= 2 and '# safe:' in lines[i-2])
                if has_safe:
                    continue
                if not has_normalize:
                    path_warnings.append(f"{os.path.relpath(fpath)}:{i} 路径拼接无规范化校验")

    if path_errors:
        # skill/agent项目是CLI工具，文件路径多为本地配置，无用户输入驱动，降级为建议
        if context.project_type in ("skill", "agent"):
            results.append({
                'id': '3.6',
                'name': '路径穿越检测',
                'level': 'suggestion',
                'message': f'发现 {len(path_errors)} 处路径拼接建议优化',
                'file': '',
                'line': 0,
                'snippet': '\n'.join(path_errors[:10]),
                'fix': '建议使用os.path.realpath/os.path.abspath规范化路径，增强健壮性',
                'category': 'security',
            })
        else:
            results.append({
                'id': '3.6',
                'name': '路径穿越检测',
                'level': 'error',
                'message': f'发现 {len(path_errors)} 处路径穿越风险（用户输入直接拼接路径无校验）',
                'file': '',
                'line': 0,
                'snippet': '\n'.join(path_errors[:10]),
                'fix': '使用os.path.realpath/os.path.abspath规范化路径并校验边界',
                'category': 'security',
            })
    elif path_warnings:
        if context.project_type in ("skill", "agent"):
            results.append({
                'id': '3.6',
                'name': '路径穿越检测',
                'level': 'suggestion',
                'message': f'发现 {len(path_warnings)} 处路径操作建议优化',
                'file': '',
                'line': 0,
                'snippet': '\n'.join(path_warnings[:10]),
                'fix': '建议补充路径规范化校验(os.path.realpath)，增强健壮性',
                'category': 'security',
            })
        else:
            results.append({
                'id': '3.6',
                'name': '路径穿越检测',
                'level': 'warning',
                'message': f'发现 {len(path_warnings)} 处路径操作校验不完整',
                'file': '',
                'line': 0,
                'snippet': '\n'.join(path_warnings[:10]),
                'fix': '补充路径规范化校验(os.path.realpath + 边界检查)',
                'category': 'security',
            })

    return results


# ===== 3.7 SSRF风险检测 =====


# ===== 3.7 SSRF风险检测 =====
def check_3_7_ssrf(context) -> List[Dict]:
    """3.7 SSRF风险检测 - 检查外部HTTP请求是否存在SSRF风险

    v4.4 误报治理:
    - 跳过注释行
    - 跳过 Python docstring 三重引号内的示例
    - 跳过规则文件 RULES = [...] 定义列表（自指）
    - 保留环境变量/配置来源的URL豁免逻辑
    """
    results = []

    # skill/agent类型走平台工具调用，无原生HTTP请求，跳过SSRF检测
    if context.project_type in ("skill", "agent"):
        return results

    all_files = []
    if context.project_path and os.path.isdir(context.project_path):
        if context.is_web_frontend():
            all_files += context.find_files([".js", ".ts", ".tsx", ".jsx"])
        else:
            all_files += context.find_files([".js", ".wxml", ".wxss"])
    all_files += context.get_backend_py_files()

    py_files = [f for f in all_files if f.endswith('.py')]

    # 常见安全校验函数名
    safe_functions = [
        '_is_safe_url', 'is_safe_url', 'validate_url', 'check_ssrf',
        'url_whitelist', 'is_domain_allowed', 'safe_request',
        'verify_url', 'sanitize_url', 'url_safe_check'
    ]
    # 从配置中读取额外安全函数名
    config_safe_funcs = context.config.get('ssrf_safe_functions', [])
    if config_safe_funcs:
        safe_functions = list(set(safe_functions + config_safe_funcs))

    ssrf_errors = []
    ssrf_warnings = []

    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        lines = content.split('\n')

        # v4.4: Python 预计算跳过范围
        docstring_ranges = []
        rules_list_range = None
        if _HAS_CODE_CONTEXT_UTILS:
            docstring_ranges = find_python_docstring_ranges(lines)
            rules_list_range = find_python_rules_list_range(lines)

        def _is_skip_line(lineno: int) -> bool:
            if docstring_ranges and is_line_in_range(lineno, docstring_ranges):
                return True
            if rules_list_range and rules_list_range[0] <= lineno <= rules_list_range[1]:
                return True
            return False

        # 文件级检测：检查该文件是否定义了URL安全校验函数
        file_has_safe_func = False
        for func in safe_functions:
            if f'def {func}' in content:
                file_has_safe_func = True
                break

        # 统计安全函数被调用的次数
        safe_func_calls = 0
        for func in safe_functions:
            safe_func_calls += content.count(f'{func}(')

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            # v4.4: 跳过 docstring / RULES 列表
            if _is_skip_line(i):
                continue
            # Detect external HTTP requests with variable URL (not constant string)
            http_match = re.search(r'(requests\.(get|post|put|delete|head|patch)|urllib\.request\.urlopen|httpx\.(get|post|Client))\s*\(', line)
            if not http_match:
                continue
            # Check if URL argument is a variable (not a string literal)
            call_start = http_match.end()
            rest_of_line = line[call_start:]
            # URL is a variable if it doesn't start with a quote (string literal)
            if rest_of_line.lstrip() and not rest_of_line.lstrip()[0] in ('"', "'"):
                # It's a variable or expression — potential SSRF
                ctx_lines = '\n'.join(lines[max(0, i-10):i+3])
                has_protocol_check = bool(re.search(r'https?://|protocol.*白名单|protocol.*whitelist|allowedProtocol|scheme.*check', ctx_lines, re.IGNORECASE))
                has_domain_check = bool(re.search(r'domain.*whitelist|domain.*白名单|域名.*白名单|allowed.*host|host.*check|ALLOWED_HOST|startswith.*https', ctx_lines, re.IGNORECASE))
                has_ip_block = bool(re.search(r'10\.\d|172\.(1[6-9]|2[0-9]|3[01])\.|192\.168\.|127\.0\.0|private.*ip|internal.*ip|内网', ctx_lines, re.IGNORECASE))
                has_safe = '# safe:' in line.lower() or (i >= 2 and '# safe:' in lines[i-2].lower())
                if has_safe:
                    continue

                # Skip if URL variable comes from env var or config module (not user input)
                url_var_match = re.match(r'\s*(\w+)', rest_of_line)
                if url_var_match:
                    url_var = url_var_match.group(1)
                    # Check os.environ.get(), os.getenv(), and config module patterns
                    env_patterns = [
                        rf'\b{re.escape(url_var)}\s*=\s*os\.environ\.get\s*\(',
                        rf'\b{re.escape(url_var)}\s*=\s*os\.getenv\s*\(',
                        rf'\b{re.escape(url_var)}\s*=\s*config\.',
                        rf'\b{re.escape(url_var)}\s*=\s*core_config\.',
                        rf'\b{re.escape(url_var)}\s*=\s*app\.config',
                        rf'\b{re.escape(url_var)}\s*=\s*settings\.',
                    ]
                    is_env_sourced = False
                    for ep in env_patterns:
                        if re.search(ep, ctx_lines):
                            is_env_sourced = True
                            break
                    # Also check broader context if var name suggests URL config
                    if not is_env_sourced:
                        if any(hint in url_var.lower() for hint in ['base_url', 'url', 'endpoint', 'host', 'api_url', 'webhook']):
                            broader_ctx = '\n'.join(lines[max(0, i-20):i+3])
                            if re.search(r'(os\.environ|os\.getenv|config\.|core_config\.|settings\.)', broader_ctx):
                                is_env_sourced = True
                    if is_env_sourced:
                        continue

                # 检查该行附近是否调用了安全校验函数
                has_safe_func_call = False
                for func in safe_functions:
                    if func + '(' in ctx_lines:
                        has_safe_func_call = True
                        break

                # 文件有安全函数定义 + 有调用 → 视为有防护
                if file_has_safe_func and (has_safe_func_call or safe_func_calls > 0):
                    if has_protocol_check or has_domain_check or has_ip_block or has_safe_func_call:
                        continue  # 有完整防护，通过
                    else:
                        # 文件有防护函数但不确定本请求是否用了，降为警告
                        ssrf_warnings.append(f"{os.path.relpath(fpath)}:{i} 外部请求URL校验待确认（文件有防护函数）")
                        continue

                if has_protocol_check and (has_domain_check or has_ip_block):
                    pass  # 协议+域名/IP校验齐全，视为安全
                elif has_protocol_check or has_domain_check or has_ip_block:
                    ssrf_warnings.append(f"{os.path.relpath(fpath)}:{i} 外部请求URL校验不完整")
                else:
                    ssrf_errors.append(f"{os.path.relpath(fpath)}:{i} 外部请求URL来自变量且无校验")

    if ssrf_errors:
        results.append({
            'id': '3.7',
            'name': 'SSRF风险检测',
            'level': 'error',
            'message': f'发现 {len(ssrf_errors)} 处SSRF风险（外部请求URL来自变量且无校验）',
            'file': '',
            'line': 0,
            'snippet': '\n'.join(ssrf_errors[:10]),
            'fix': '对URL做协议白名单(仅http/https)+域名白名单+禁止内网IP',
            'category': 'security',
        })
    elif ssrf_warnings:
        results.append({
            'id': '3.7',
            'name': 'SSRF风险检测',
            'level': 'warning',
            'message': f'发现 {len(ssrf_warnings)} 处外部请求校验不完整',
            'file': '',
            'line': 0,
            'snippet': '\n'.join(ssrf_warnings[:10]),
            'fix': '补充URL协议白名单、域名白名单和内网IP阻断',
            'category': 'security',
        })

    return results


# ===== 3.8 越权访问(IDOR)检测 =====


# ===== 规则定义列表 =====
RULES = [
    {
        'id': '3.1',
        'name': 'SQL注入检测',
        'level': 'blocking',
        'category': 'security',
        'module_id': '3',
        'applicable_types': [],  # 所有类型适用
        'description': '检查代码中是否存在SQL注入风险，包括字符串拼接SQL、f-string拼接等',
        
        'check': check_3_1_sql_injection,
    },
    {
        'id': '3.3',
        'name': 'XSS风险',
        'level': 'problem',
        'category': 'security',
        'module_id': '3',
        'applicable_types': ['miniprogram', 'web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查是否存在跨站脚本攻击风险，如innerHTML、eval等',
        
        'check': check_3_3_xss,
    },
    {
        'id': '3.6',
        'name': '路径穿越检测',
        'level': 'blocking',
        'category': 'security',
        'module_id': '3',
        'applicable_types': [],
        'description': '检查是否存在路径穿越风险，如f-string路径拼接无校验',
        
        'check': check_3_6_path_traversal,
    },
    {
        'id': '3.7',
        'name': 'SSRF风险检测',
        'level': 'blocking',
        'category': 'security',
        'module_id': '3',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron'],
        'description': '检查外部HTTP请求是否存在SSRF风险，URL是否来自变量且无校验',
        
        'check': check_3_7_ssrf,
    },
]
