"""安全审计规则集 - 子模块
从 security.py 拆分而来，包含以下规则: 3.2, 20.8

v4.4 误报治理:
- 所有基于字符串匹配的检测均跳过字符串字面量内部、注释、docstring
- 使用上下文感知匹配工具 extract_code_content / search_in_code
- 对 Python 文件额外跳过三重引号 docstring 范围
"""

"""
安全审计规则集 (M3)
通用安全检查 - 适用于所有项目类型
包含: SQL注入、敏感信息泄露、XSS、鉴权绕过、CORS/CSRF等12项检查
"""

import re
import os
from typing import List, Dict, Any

# v4.4: 上下文感知匹配工具（跳过字符串/注释/docstring）
try:
    from core.code_context_utils import (
        extract_code_content, search_in_code, finditer_in_code,
        find_python_docstring_ranges, is_line_in_range, is_in_string,
    )
    _HAS_CODE_CONTEXT_UTILS = True
except ImportError:  # noqa: 兼容旧版本
    _HAS_CODE_CONTEXT_UTILS = False


def _get_lang(fpath: str) -> str:
    """根据扩展名获取语言标识"""
    ext = os.path.splitext(fpath)[1].lower()
    if ext == '.py':
        return 'py'
    elif ext in ('.js', '.ts', '.tsx', '.jsx'):
        return 'js'
    return 'js'


# ===== 3.2 敏感信息泄露 =====
def check_3_2_sensitive_info(context) -> List[Dict]:
    """3.2 敏感信息泄露 - 检查代码中是否硬编码了敏感信息

    v4.4 误报治理:
    - 跳过注释行（# / // 开头）
    - 跳过字符串字面量内部的变量名匹配（仅匹配代码中的变量赋值左侧）
    - 跳过 Python 三重引号 docstring（文档中的示例不算）
    - 标识符边界匹配，确保是完整变量名
    - 排除常见占位符/示例值/环境变量读取
    - 匹配策略：先找左侧变量名（代码中），再检查右侧是否有字符串值
    """
    results = []

    all_files = context.find_files([".js", ".py", ".ts", ".tsx", ".jsx"])

    # v4.4: 敏感变量名模式（只匹配赋值左侧的标识符）
    # 使用 \b 确保标识符边界
    sensitive_var_pattern = re.compile(
        r'\b(password|passwd|pwd|api_key|apikey|api_secret|secret_key|'
        r'access_token|auth_token|token)\s*[:=]\s*["\']([^"\']+)["\']',
        re.IGNORECASE
    )
    # 独立密钥格式（字符串字面量内出现，无需变量上下文）
    key_format_patterns = [
        (re.compile(r'AKIA[0-9A-Z]{16}'), 'AWS Access Key', 1.0),
        (re.compile(r'sk-[a-zA-Z0-9]{20,}'), 'OpenAI API Key', 1.0),
    ]

    for fpath in all_files:
        # 跳过配置文件示例和测试文件
        basename = os.path.basename(fpath)
        if any(x in basename.lower() for x in ['example', 'sample', 'demo', 'test', '.example']):
            continue

        content = context.safe_read(fpath)
        if not content:
            continue

        lang = _get_lang(fpath)
        lines = content.split('\n')

        # Python: 预计算 docstring 范围
        docstring_ranges = find_python_docstring_ranges(lines) if lang == 'py' and _HAS_CODE_CONTEXT_UTILS else []

        for line_idx, line in enumerate(lines):
            lineno = line_idx + 1
            stripped = line.strip()
            # 跳过注释行
            if stripped.startswith('#') or stripped.startswith('//') or stripped.startswith('*') or stripped.startswith('/*'):
                continue
            # 跳过 docstring 行
            if docstring_ranges and is_line_in_range(lineno, docstring_ranges):
                continue
            # 排除环境变量读取行
            if any(kw in line for kw in ['os.environ', 'os.getenv', 'process.env', 'getenv']):
                continue

            # v4.4: 使用 extract_code_content 获取纯代码部分
            # 但注意：赋值语句右侧的字符串值会被移除
            # 因此策略改为：先在原始行匹配完整模式，再验证变量名部分在代码区
            m = sensitive_var_pattern.search(line)
            if m:
                var_name = m.group(1)
                value = m.group(2)
                # 验证：变量名位置是否在代码区（不在字符串内）
                if _HAS_CODE_CONTEXT_UTILS and is_in_string(line, m.start(1), lang):
                    continue  # 变量名在字符串内，跳过

                # 检查是否是占位符或示例值
                if any(x in value.lower() for x in ['xxx', 'your_', 'example', 'placeholder', 'test']):
                    continue
                if any(x in var_name.lower() for x in ['your_', 'example']):
                    continue

                # 根据变量名决定描述和阈值
                var_lower = var_name.lower()
                if var_lower in ('password', 'passwd', 'pwd'):
                    desc = '硬编码密码'
                elif var_lower in ('api_key', 'apikey', 'api_secret', 'secret_key'):
                    if len(value) < 10:
                        continue  # 值太短，跳过
                    desc = '硬编码API密钥'
                elif var_lower in ('access_token', 'auth_token', 'token'):
                    if len(value) < 20:
                        continue  # 值太短，跳过
                    desc = '硬编码Token'
                else:
                    continue

                results.append({
                    'id': '3.2',
                    'name': '敏感信息泄露',
                    'level': 'error',
                    'message': f'代码中存在敏感信息: {desc}',
                    'file': fpath,
                    'line': lineno,
                    'snippet': stripped[:80],
                    'fix': '将敏感信息移至环境变量或配置文件，不要硬编码在代码中',
                })
                break  # 每个文件只报一次

    return results


# ===== 3.3 XSS风险 =====


# ===== 20.8 硬编码密钥检测 =====
def check_20_8_hardcoded_keys(context) -> List[Dict]:
    """20.8 硬编码密钥检测 - 检测代码中硬编码的API密钥/Token等敏感信息

    检测模式：
    - sk-xxx格式（OpenAI等大模型API Key）
    - aco-xxx格式
    - 32位hex字符串（API Key）
    - apiKey/api_key/secret_key等变量名赋值
    - 排除：环境变量引用、config文件、测试文件、node_modules

    v4.4 误报治理:
    - 跳过注释行（# / // 开头）
    - 跳过字符串字面量内部匹配（使用 search_in_code）
    - 跳过 Python 三重引号 docstring
    - 变量赋值模式确保是标识符边界匹配，且在赋值左侧
    - 额外排除示例/测试/占位符值
    """
    results = []

    all_files = context.find_files([".js", ".ts", ".jsx", ".tsx", ".py"])
    if not all_files:
        return results

    # 密钥模式（编译为 re.Pattern）
    # v4.4: 模式按是否需要变量上下文分组
    # 自由出现的密钥格式（字符串内出现也算，因为密钥本身就是值）
    free_form_patterns = [
        (re.compile(r'["\']sk-[A-Za-z0-9]{20,}["\']'), 'OpenAI风格API Key (sk-xxx)'),
        (re.compile(r'["\']aco-[A-Za-z0-9]{10,}["\']'), 'ACO格式密钥 (aco-xxx)'),
        (re.compile(r'["\']Bearer\s+[A-Za-z0-9_\-\.]{20,}["\']'), '硬编码Bearer Token'),
    ]
    # 需要变量名上下文的模式（只有赋值语句才算）
    assignment_patterns = [
        (re.compile(r'\b(?:key|token|secret|apikey|api_key)\s*[=:]\s*["\']([a-fA-F0-9]{32})["\']', re.IGNORECASE), '32位hex密钥'),
        (re.compile(r'\b(?:apiKey|api_key|apiSecret|api_secret|secretKey|secret_key|accessToken|access_token|authToken)\s*[=:]\s*["\']([A-Za-z0-9_\-]{16,})["\']', re.IGNORECASE), '密钥变量硬编码'),
    ]

    # 排除模式（代码中出现这些就跳过整行）
    env_patterns = re.compile(r'(?:process\.env|os\.environ|getenv|config\.|CONFIG\.)\s*[\.\[]', re.IGNORECASE)
    placeholder_pattern = re.compile(r'(?:xxx|your[_-]?key|placeholder|example|test|demo|sample)', re.IGNORECASE)

    # 排除文件
    exclude_file_patterns = [
        re.compile(r'(?:node_modules|miniprogram_npm|\.env|test|spec|mock|fixture|__tests__|__mocks__)', re.IGNORECASE),
    ]

    for fpath in all_files:
        # 检查文件路径是否应排除
        norm_path = fpath.replace(os.sep, '/')
        if any(p.search(norm_path) for p in exclude_file_patterns):
            continue

        # 也排除配置文件
        basename = os.path.basename(fpath).lower()
        if basename in ('.env', '.env.local', 'config.json', 'settings.json'):
            continue

        content = context.safe_read(fpath)
        if not content:
            continue

        # 跳过vendored文件
        lines = content.split('\n')
        if lines:
            max_line_len = max(len(line) for line in lines[:100])
            if max_line_len > 5000 and len(lines) < 50:
                continue

        lang = _get_lang(fpath)

        # Python: 预计算 docstring 范围
        docstring_ranges = find_python_docstring_ranges(lines) if lang == 'py' and _HAS_CODE_CONTEXT_UTILS else []

        file_issues = []

        for line_idx, line in enumerate(lines):
            lineno = line_idx + 1
            stripped = line.strip()

            # 跳过注释
            if stripped.startswith('//') or stripped.startswith('#') or stripped.startswith('*') or stripped.startswith('/*'):
                continue

            # 跳过 docstring 行
            if docstring_ranges and is_line_in_range(lineno, docstring_ranges):
                continue

            # 检查是否应排除此行（环境变量 / 占位符）
            if env_patterns.search(line):
                continue
            if placeholder_pattern.search(stripped):
                continue

            # --- 自由格式密钥 ---
            # 这些模式直接匹配字符串字面量（密钥本身就是值），
            # 但需要排除注释和 docstring（已在上面跳过）
            for pattern, desc in free_form_patterns:
                m = pattern.search(line)
                if m:
                    matched_text = m.group(0)
                    # 额外检查：值不是占位符
                    if placeholder_pattern.search(matched_text):
                        continue
                    file_issues.append({
                        'line': lineno,
                        'desc': desc,
                        'snippet': stripped[:80],
                    })
                    break  # 每行只报一次自由格式

            # --- 赋值格式密钥 ---
            # v4.4: 使用 search_in_code 确保匹配在代码部分（变量赋值）
            for pattern, desc in assignment_patterns:
                if _HAS_CODE_CONTEXT_UTILS:
                    m = search_in_code(line, pattern, lang)
                else:
                    m = pattern.search(line)
                if m:
                    matched_text = m.group(0)
                    if placeholder_pattern.search(matched_text):
                        continue
                    file_issues.append({
                        'line': lineno,
                        'desc': desc,
                        'snippet': stripped[:80],
                    })
                    break  # 每行每个模式只报一次

        if file_issues:
            results.append({
                'id': '20.8',
                'name': '硬编码密钥检测',
                'level': 'error',
                'message': f'发现{len(file_issues)}处硬编码密钥/Token',
                'detail': '\n'.join([f"  第{iss['line']}行: {iss['desc']} | {iss['snippet']}" for iss in file_issues[:5]]),
                'file': fpath,
                'line': file_issues[0]['line'],
                'fix': '将密钥移至环境变量或安全的密钥管理服务，代码中通过环境变量读取',
                'suggestion_code': '// 错误: 硬编码\n// const API_KEY = "sk-abc123...";\n\n// 正确: 使用环境变量\n// const API_KEY = process.env.API_KEY;\n// 小程序中: const API_KEY = wx.getAccountInfoSync().miniProgram.envVersion;',
            })

    return results


# ===== 规则定义列表 =====


# ===== 规则定义列表 =====
RULES = [
    {
        'id': '3.2',
        'name': '敏感信息泄露',
        'level': 'blocking',
        'category': 'security',
        'module_id': '3',
        'applicable_types': [],
        'description': '检查代码中是否硬编码了密码、API密钥、Token等敏感信息',
        
        'check': check_3_2_sensitive_info,
    },
    {
        'id': '20.8',
        'name': '硬编码密钥检测',
        'level': 'error',
        'category': 'security',
        'module_id': '20',
        'applicable_types': ['miniprogram', 'web', 'python_backend', 'flask', 'mixed', 'electron', 'mixed_electron'],
        'description': '检测代码中硬编码的API密钥、Token等敏感信息（sk-xxx/aco-xxx/32位hex等模式）',
        
        'check': check_20_8_hardcoded_keys,
    },
]
