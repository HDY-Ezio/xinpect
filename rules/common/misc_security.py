"""安全审计规则集 - 子模块
从 security.py 拆分而来，包含以下规则: 3.11, 3.12
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
        is_line_in_range,
    )
    _HAS_CODE_CONTEXT_UTILS = True
except ImportError:  # noqa: 兼容旧版本
    _HAS_CODE_CONTEXT_UTILS = False


def _prepare_py_skip_ranges(lines: List[str]):
    """v4.4: 预计算 Python 文件的跳过范围（docstring / RULES列表）"""
    if not _HAS_CODE_CONTEXT_UTILS:
        return [], None
    doc_ranges = find_python_docstring_ranges(lines)
    rules_range = find_python_rules_list_range(lines)
    return doc_ranges, rules_range


def _skip_line_py(line_no: int, lines: List[str],
                  docstring_ranges: List, rules_list_range) -> bool:
    """v4.4: 判断 Python 文件中某行是否应跳过"""
    if not _HAS_CODE_CONTEXT_UTILS:
        return False
    if docstring_ranges and is_line_in_range(line_no, docstring_ranges):
        return True
    if rules_list_range and rules_list_range[0] <= line_no <= rules_list_range[1]:
        return True
    return False


# ===== 3.11 输入校验检测 =====
def check_3_11_input_validation(context) -> List[Dict]:
    """3.11 输入校验检测 - 检查是否缺少输入校验

    v4.4 误报治理:
    - 跳过 Python docstring 内的示例
    - 跳过规则文件 RULES 定义列表（自指）
    """
    results = []

    # skill/agent类型无API handler，跳过输入校验检测
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
    
    missing_validation = []
    has_global_validation = False
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if re.search(r'validation.?middleware|input.?validator|validate.?request|参数校验|全局校验', content, re.IGNORECASE):
            has_global_validation = True
        lines = content.split('\n')
        # v4.4: 预计算跳过范围
        doc_ranges, rules_range = _prepare_py_skip_ranges(lines)
        for i, line in enumerate(lines):
            # v4.4: 跳过 docstring / RULES 列表
            if _skip_line_py(i + 1, lines, doc_ranges, rules_range):
                continue
            m = re.match(r'\s*def\s+(handle_\w+|process_\w+|api_\w+)\s*\(([^)]*)\)', line)
            if not m:
                continue
            func_name = m.group(1)
            body = '\n'.join(lines[i:min(i+30, len(lines))])
            has_validation = bool(re.search(
                r'len\s*\(|isinstance\s*\(|int\s*\(|float\s*\(|max_length|min_length|validate|校验|检查|必填|required|ValidationError',
                body, re.IGNORECASE))
            if not has_validation:
                missing_validation.append(f"{os.path.relpath(fpath)}:{i+1} {func_name}()")
    
    if has_global_validation:
        pass  # 有全局校验，视为通过
    elif missing_validation:
        results.append({
            'id': '3.11',
            'name': '输入校验检测',
            'level': 'warning',
            'message': f'发现 {len(missing_validation)} 个handler函数缺少入参校验',
            'file': '',
            'line': 0,
            'snippet': '\n'.join(missing_validation[:15]),
            'fix': '为关键API入参添加类型/长度/范围校验，或部署全局校验中间件',
            'category': 'security',
        })
    
    return results


# ===== 3.12 文件上传安全检测 =====


# ===== 3.12 文件上传安全检测 =====
def check_3_12_file_upload(context) -> List[Dict]:
    """3.12 文件上传安全检测 - 检查文件上传是否安全

    v4.4 误报治理:
    - 跳过注释行
    - 跳过 Python docstring 内的示例
    - 跳过规则文件 RULES 定义列表（自指）
    """
    results = []

    # skill/agent类型无HTTP文件上传，跳过文件上传安全检测
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
    
    upload_errors = []
    upload_warnings = []
    pending_verify = []  # 待人工确认
    
    has_upload = False
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        lines = content.split('\n')
        basename = os.path.basename(fpath)
        # v4.4: 预计算跳过范围
        doc_ranges, rules_range = _prepare_py_skip_ranges(lines)
        
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            # v4.4: 跳过 docstring / RULES 列表
            if _skip_line_py(i, lines, doc_ranges, rules_range):
                continue
            if not re.search(r'request\.files|multipart|file\.read\s*\(|file\.save|\.filename', line, re.IGNORECASE):
                continue
            
            # 场景识别：判断是否为HTTP上传场景
            ctx_start = max(0, i - 10)
            ctx_end = min(len(lines), i + 15)
            context_lines = lines[ctx_start:ctx_end]
            context_str = '\n'.join(context_lines)
            text_lower = context_str.lower()
            
            # 获取函数名（向上找最近的def）
            func_name = ""
            for j in range(i - 1, max(0, i - 50), -1):
                func_match = re.match(r'\s*def\s+(\w+)\s*\(', lines[j])
                if func_match:
                    func_name = func_match.group(1)
                    break
            
            # 判断是否为HTTP handler场景
            is_http_handler = False
            http_indicators = ['@app.route', '@app.get', '@app.post', '@router.', 'flask', 'request.', 'response.']
            for ind in http_indicators:
                if ind.lower() in text_lower:
                    is_http_handler = True
                    break
            
            # 判断是否为邮件附件场景（非上传，跳过）
            email_indicators = ['smtplib', 'email.mime', 'MIMEMultipart', 'MIMEBase', 'add_attachment', '邮件', '附件']
            is_email = sum(1 for ind in email_indicators if ind.lower() in text_lower or ind.lower() in basename.lower()) >= 2
            
            # 判断是否为本地文件读取（非上传，跳过）
            local_indicators = ['open.*config', 'open.*static', 'config.json', 'static/', 'templates/']
            is_local = any(ind.lower() in text_lower for ind in local_indicators)
            
            # 非上传场景 → 直接跳过
            if is_email or is_local:
                continue
            
            # 场景不明确 → 待确认，不计入扣分
            if not is_http_handler:
                pending_verify.append(
                    f"{os.path.relpath(fpath)}:{i} - 场景不明确，需人工确认是否为文件上传"
                )
                continue
            
            # 确认是HTTP上传场景
            has_upload = True
            
            ctx = '\n'.join(lines[max(0, i-5):min(i+15, len(lines))])
            has_type_whitelist = bool(re.search(r'allowed.?ext|ALLOWED.?EXT|allowed.?type|ALLOWED.?TYPE|白名单|whitelist.*ext|ext.*whitelist|_validate.*upload|_validate.*image|validate.*file', ctx, re.IGNORECASE))
            has_size_limit = bool(re.search(r'max.?size|MAX.?SIZE|content.?length|file.?size|文件大小|size.?limit|MAX_CONTENT|_validate.*upload|_validate.*image|MAX_IMG', ctx, re.IGNORECASE))
            has_secure_filename = bool(re.search(r'secure_filename|uuid|werkzeug|safe_name|sanitize.*name|rename|重命名', ctx, re.IGNORECASE))
            uses_original_name = bool(re.search(r'\.filename\s*\)?\s*$|save.*\.filename|open.*\.filename', line, re.IGNORECASE))
            has_safe = '# safe:' in line or (i >= 2 and '# safe:' in lines[i-2])
            if has_safe:
                continue
            if not has_type_whitelist:
                upload_warnings.append(f"{os.path.relpath(fpath)}:{i} 文件上传缺少类型白名单校验")
            if not has_size_limit:
                upload_warnings.append(f"{os.path.relpath(fpath)}:{i} 文件上传缺少大小限制")
            if uses_original_name and not has_secure_filename:
                upload_errors.append(f"{os.path.relpath(fpath)}:{i} 直接使用用户文件名(路径穿越风险)")
    
    # 构建结果
    if not has_upload and not upload_errors and not upload_warnings:
        if pending_verify:
            results.append({
                'id': '3.12',
                'name': '文件上传安全检测',
                'level': 'info',
                'message': f'未检测到确定的文件上传功能（另有{len(pending_verify)}处待确认）',
                'file': '',
                'line': 0,
                'snippet': '\n'.join(pending_verify[:10]),
                'fix': '建议人工确认待检查项是否为用户文件上传',
                'category': 'security',
            })
        # 无文件上传且无待确认，不返回结果
    elif upload_errors:
        detail = '\n'.join(upload_errors[:10])
        if pending_verify:
            detail += f"\n--- 另有 {len(pending_verify)} 处待人工确认（不计入扣分）---"
        results.append({
            'id': '3.12',
            'name': '文件上传安全检测',
            'level': 'error',
            'message': f'发现 {len(upload_errors)} 处文件上传安全风险',
            'file': '',
            'line': 0,
            'snippet': detail,
            'fix': '禁止直接使用用户文件名，使用uuid/secure_filename重命名',
            'category': 'security',
        })
    elif upload_warnings:
        detail = '\n'.join(upload_warnings[:10])
        if pending_verify:
            detail += f"\n--- 另有 {len(pending_verify)} 处待人工确认（不计入扣分）---"
        results.append({
            'id': '3.12',
            'name': '文件上传安全检测',
            'level': 'warning',
            'message': f'发现 {len(upload_warnings)} 处文件上传校验不完整',
            'file': '',
            'line': 0,
            'snippet': detail,
            'fix': '补充文件类型白名单、大小限制和安全文件名处理',
            'category': 'security',
        })
    
    return results


# ===== 20.8 硬编码密钥检测 =====


# ===== 规则定义列表 =====
RULES = [
    {
        'id': '3.11',
        'name': '输入校验检测',
        'level': 'problem',
        'category': 'security',
        'module_id': '3',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron'],
        'description': '检查是否缺少输入校验，handler函数是否有入参校验',
        
        'check': check_3_11_input_validation,
    },
    {
        'id': '3.12',
        'name': '文件上传安全检测',
        'level': 'blocking',
        'category': 'security',
        'module_id': '3',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron'],
        'description': '检查文件上传是否安全，如类型白名单、大小限制、安全文件名',
        
        'check': check_3_12_file_upload,
    },
]
