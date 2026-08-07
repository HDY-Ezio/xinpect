#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
场景感知层 - QA质检框架v21 P1根因修复
核心目标：对代码片段做场景分类，识别代码在做什么，再决定应用什么规则
遵循"疑罪从无"原则：无法确定是真问题的，一律不报告或标记为待确认

场景类型：
1. mock_test_config - mock/测试配置场景
2. dynamic_sql_structural - 动态SQL构造（SQL结构拼接，非用户数据参数化）
3. local_file_read - 本地文件读取（非用户上传）
4. ops_patch_script - 运维补丁脚本
5. init_config - 初始化配置/默认值
6. email_attachment - 邮件附件读取
7. http_handler - HTTP接口处理器
8. utility_function - 工具函数/通用方法
9. unknown - 无法识别
"""

import os
import re
import ast
from typing import Dict, List, Tuple, Optional, Any
from collections import defaultdict


# ===== 场景类型常量 =====
SCENE_MOCK_TEST = "mock_test_config"
SCENE_DYNAMIC_SQL_STRUCTURAL = "dynamic_sql_structural"
SCENE_LOCAL_FILE_READ = "local_file_read"
SCENE_OPS_PATCH = "ops_patch_script"
SCENE_INIT_CONFIG = "init_config"
SCENE_EMAIL_ATTACHMENT = "email_attachment"
SCENE_HTTP_HANDLER = "http_handler"
SCENE_UTILITY = "utility_function"
SCENE_UNKNOWN = "unknown"

SCENE_NAMES = {
    SCENE_MOCK_TEST: "Mock/测试配置",
    SCENE_DYNAMIC_SQL_STRUCTURAL: "动态SQL结构拼接",
    SCENE_LOCAL_FILE_READ: "本地文件读取",
    SCENE_OPS_PATCH: "运维补丁脚本",
    SCENE_INIT_CONFIG: "初始化配置",
    SCENE_EMAIL_ATTACHMENT: "邮件附件处理",
    SCENE_HTTP_HANDLER: "HTTP接口处理器",
    SCENE_UTILITY: "工具函数",
    SCENE_UNKNOWN: "未识别场景",
}

# ===== Mock/测试配置识别 =====
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


def is_mock_value(value: str) -> bool:
    """判断一个值字符串是否为明显的mock占位值"""
    val_lower = value.lower().strip('"\' ')
    
    if not val_lower:
        return False
    
    # 长度太短的不算（真实密钥通常较长）
    if len(val_lower) < 8:
        return True  # 太短的不太可能是真实密钥
    
    # 明显的占位符模式
    for pat in MOCK_VALUE_PATTERNS:
        if re.fullmatch(pat, val_lower):
            return True
    
    # 包含明显的占位词
    placeholder_words = ['mock', 'test', 'demo', 'example', 'placeholder', 'dummy', 'fake', 'sample', 'changeme']
    for word in placeholder_words:
        if word in val_lower and len(val_lower) < 30:
            return True
    
    # 全是x或*
    if all(c in 'x*X' for c in val_lower):
        return True
    
    return False


# ===== SQL场景识别 =====

_USER_INPUT_KEYWORDS = [
    'request', 'user_input', 'input_data', 'form_data',
    'json_data', 'post_data', 'body', 'payload',
    'user_id', 'username', 'email', 'name',
    'query_params', 'params', 'args',
]

_STRUCTURAL_KEYWORDS = [
    'updates', 'columns', 'fields', 'table_name',
    'col', 'column', 'field', 'set_clause',
    'order_by', 'sort_by', 'group_by',
    'select_fields', 'update_fields',
]


def _classify_fstring_vars(fstring_vars: list, result: dict) -> tuple:
    """Classify f-string variables as structural or user-input. Returns (structural_count, user_input_count)."""
    structural_count = 0
    user_input_count = 0

    for var in fstring_vars:
        var_clean = var.strip()
        var_lower = var_clean.lower()

        if any(kw in var_lower for kw in _STRUCTURAL_KEYWORDS):
            structural_count += 1
        elif any(kw in var_lower for kw in _USER_INPUT_KEYWORDS):
            user_input_count += 1
            result["user_input_vars"].append(var_clean)

    return structural_count, user_input_count


def analyze_sql_scene(sql_line: str, context_lines: List[str], full_file_content: str = "") -> Dict[str, Any]:
    """
    分析SQL语句的场景，判断是否为安全的动态SQL构造
    
    返回: {
        "is_structural": bool,     # 是否为SQL结构拼接（列名/表名等，非用户数据）
        "has_parameterized": bool,  # 是否有参数化查询
        "user_input_vars": list, # 疑似用户输入变量名
        "confidence": float,    # 置信度
        "reason": str,         # 判定理由
    }
    """
    result = {
        "is_structural": False,
        "has_parameterized": False,
        "user_input_vars": [],
        "confidence": 0.0,
        "reason": "",
    }
    
    context = '\n'.join(context_lines) if context_lines else ""
    full_context = sql_line + '\n' + context
    
    # 1. 检查是否有参数化查询（execute with params）
    param_patterns = [
        r'\.execute\s*\([^)]*,\s*params',
        r'\.execute\s*\([^)]*,\s*\(',
        r'\.execute\s*\([^)]*,\s*\[',
        r'\.execute\s*\([^)]*,\s*\{',
        r'cursor\.execute\s*\([^)]*,\s*',
    ]
    for pat in param_patterns:
        if re.search(pat, full_context, re.IGNORECASE):
            result["has_parameterized"] = True
            break
    
    # 2. 分析f-string中拼接的内容
    # 提取f-string中的{}内容
    fstring_vars = re.findall(r'\{([^{}]+)\}', sql_line)
    
    if not fstring_vars:
        # 没有f-string变量，可能是完全静态SQL或其他拼接方式
        # 检查是否是列名/表名列表拼接
        if re.search(r"join\s*\(\s*updates|join\s*\(\s*columns|join\s*\(\s*fields", sql_line, re.IGNORECASE):
            result["is_structural"] = True
            result["confidence"] = 0.8
            result["reason"] = "SQL结构拼接（列名/字段列表），无用户输入"
            return result
        return result
    
    # 3. 判断变量是否来自用户输入
    structural_count, user_input_count = _classify_fstring_vars(
        fstring_vars, result
    )
    
    # 4. 综合判断
    if structural_count > 0 and result["has_parameterized"]:
        result["is_structural"] = True
        result["confidence"] = 0.9
        result["reason"] = f"SQL结构拼接({structural_count}个结构变量) + 参数化查询，无注入风险"
    elif result["has_parameterized"] and user_input_count == 0:
        result["is_structural"] = True
        result["confidence"] = 0.7
        result["reason"] = "有参数化查询，变量不包含明显用户输入"
    elif user_input_count > 0:
        result["is_structural"] = False
        result["confidence"] = 0.6
        result["reason"] = f"疑似包含用户输入变量({user_input_count}个)"
    
    return result


# ===== 文件操作场景识别 =====
def analyze_file_operation_scene(file_path: str, line_content: str, context_lines: List[str],
                                function_name: str = "", file_basename: str = "") -> Dict[str, Any]:
    """
    判断文件操作属于什么场景
    
    返回: {
        "scene": str,           # 场景类型
        "is_user_upload": bool, # 是否是用户上传文件操作
        "confidence": float,    # 置信度
        "reason": str,         # 判定理由
    }
    """
    result = {
        "scene": SCENE_UNKNOWN,
        "is_user_upload": False,
        "confidence": 0.0,
        "reason": "",
    }
    
    context = '\n'.join(context_lines) if context_lines else ""
    full_text = line_content + '\n' + context
    text_lower = full_text.lower()
    file_lower = file_basename.lower()
    
    # 1. 判断是否是用户上传场景
    upload_indicators = [
        'request.files', 'request.FILES',
        'file.save', 'file_storage',
        'upload', 'multipart',
        'form-data', 'form_data',
        '.filename', 'file.filename',
        'save_upload', 'handle_upload',
    ]
    
    upload_count = 0
    for ind in upload_indicators:
        if ind.lower() in text_lower:
            upload_count += 1
    
    # 2. 判断是否是邮件附件场景
    email_indicators = [
        'smtplib', 'email.mime', 'MIMEMultipart',
        'MIMEBase', 'attachment', 'attach_file',
        'send_email', 'send_mail', 'email_sender',
        'add_attachment', '邮件', '附件',
    ]
    
    email_count = 0
    for ind in email_indicators:
        if ind.lower() in text_lower or ind.lower() in file_lower:
            email_count += 1
    
    # 3. 判断是否是本地配置/静态文件读取
    local_indicators = [
        'open.*config', 'open.*static', 'open.*template',
        'config.json', 'config.yaml', 'settings.',
        'static/', 'templates/', 'assets/',
        'os.path.join.*static', 'os.path.join.*config',
        'read_template', 'load_config',
    ]
    
    local_count = 0
    for ind in local_indicators:
        if ind.lower() in text_lower:
            local_count += 1
    
    # 4. 判断所在函数是否是HTTP handler
    http_handler_indicators = [
        '@app.route', '@app.get', '@app.post',
        '@router.', 'FastAPI', 'flask',
        'request.', 'response.',
        'def.*handler', 'def.*endpoint',
    ]
    
    is_http_handler = False
    for ind in http_handler_indicators:
        if ind.lower() in text_lower:
            is_http_handler = True
            break
    
    # 5. 综合判定
    if upload_count >= 2 and is_http_handler:
        result["scene"] = SCENE_HTTP_HANDLER
        result["is_user_upload"] = True
        result["confidence"] = 0.8
        result["reason"] = f"HTTP接口中的文件上传操作"
    elif email_count >= 2:
        result["scene"] = SCENE_EMAIL_ATTACHMENT
        result["is_user_upload"] = False
        result["confidence"] = 0.85
        result["reason"] = f"邮件附件处理，非用户上传场景"
    elif local_count >= 1:
        result["scene"] = SCENE_LOCAL_FILE_READ
        result["is_user_upload"] = False
        result["confidence"] = 0.7
        result["reason"] = "本地配置/静态文件读取，非用户上传"
    elif 'email' in file_lower and 'sender' in file_lower:
        result["scene"] = SCENE_EMAIL_ATTACHMENT
        result["is_user_upload"] = False
        result["confidence"] = 0.6
        result["reason"] = "邮件发送模块，文件操作为附件读取"
    else:
        result["scene"] = SCENE_LOCAL_FILE_READ
        result["confidence"] = 0.3
        result["reason"] = "无法确定文件操作场景，默认视为本地文件读取"
    
    return result


# ===== 函数级场景识别 =====
def detect_function_scene(func_content: str, file_path: str = "") -> str:
    """识别一个函数属于什么场景"""
    content_lower = func_content.lower()
    file_lower = file_path.lower()
    
    # Mock/测试函数
    if re.search(r'def\s+(test_|mock_|demo_|fake_|fixture)', content_lower):
        return SCENE_MOCK_TEST
    
    # HTTP handler
    if re.search(r'@app\.|@router\.|@.*route|@.*get|@.*post', content_lower):
        return SCENE_HTTP_HANDLER
    
    # 邮件发送
    if 'smtplib' in content_lower or 'email.mime' in content_lower or '邮件' in content_lower:
        return SCENE_EMAIL_ATTACHMENT
    
    return SCENE_UNKNOWN


# ===== 文件级场景识别 =====
def detect_file_scene(file_path: str) -> str:
    """识别一个文件属于什么场景"""
    basename = os.path.basename(file_path).lower()
    
    # 测试文件
    if basename.startswith('test_') or basename.endswith('_test.py'):
        return SCENE_MOCK_TEST
    
    # 补丁/迁移脚本
    if re.match(r'^(patch_|migrate_|fix_|deploy_|setup_)', basename):
        return SCENE_OPS_PATCH
    
    # 邮件模块
    if 'email' in basename and 'sender' in basename:
        return SCENE_EMAIL_ATTACHMENT
    
    # 配置文件
    if basename in ('config.py', 'settings.py', 'constants.py'):
        return SCENE_INIT_CONFIG
    
    return SCENE_UNKNOWN


# ===== 敏感信息上下文判断 =====
def is_safe_sensitive_line(line: str, context_lines: List[str], file_path: str = "") -> Tuple[bool, str]:
    """
    判断疑似敏感信息行是否为安全的（mock/配置引用/测试等）
    
    返回: (is_safe, reason)
    is_safe=True 表示这行不是真实的敏感信息泄露
    """
    line_lower = line.lower()
    context = '\n'.join(context_lines)
    context_lower = context.lower()
    file_lower = file_path.lower()
    basename = os.path.basename(file_path).lower()
    
    # 1. Mock/test上下文
    if is_mock_context(line, context_lines):
        return True, "Mock/测试配置，非真实敏感信息"
    
    # 2. 从环境变量读取（os.environ / os.getenv
    if 'os.environ' in line or 'os.getenv' in line or 'os.environ.get' in line:
        return True, "从环境变量读取，非硬编码"
    
    # 3. 明显的占位符值
    # 提取值部分
    val_match = re.search(r'["\']([^"\']{6,})["\']', line)
    if val_match:
        value = val_match.group(1)
        if is_mock_value(value):
            return True, f"值为明显的占位符({value[:20]})...)"
    
    # 4. 测试文件中的值
    if basename.startswith('test_') or basename.endswith('_test.py') or '/tests/' in file_lower or '\\tests\\' in file_lower:
        return True, "测试文件中的值，非生产环境密钥"
    
    # 5. 配置文件中的值（如果是默认值/示例）
    if basename in ('config.py', 'settings.py'):
        # 检查是否是从环境变量读取的默认值
        if 'os.environ' in context or 'os.getenv' in context or 'getenv' in context:
            # 默认值配置，检查默认值是否是占位符
            if val_match:
                value = val_match.group(1)
                if is_mock_value(value) or len(value) < 16:
                    return True, "配置文件中的默认占位值，真实值从环境变量读取"
    
    # 6. 注释中
    stripped = line.strip()
    if stripped.startswith('#') or stripped.startswith('//') or stripped.startswith('/*'):
        return True, "注释中的内容，非实际代码"
    
    # 7. 文档字符串
    if '"""' in context or "'''" in context:
        # 粗略判断是否在docstring中
        pass
    
    return False, ""


# ===== 待确认项判断 =====
def needs_manual_verification(check_type: str, evidence: Dict[str, Any]) -> Tuple[bool, str]:
    """
    判断一个检测结果是否需要人工确认（疑罪从无原则）
    
    返回: (needs_verify, reason)
    True = 需要人工确认，不计入扣分
    """
    
    # 敏感信息检测：无法确定是真实密钥还是mock值
    if check_type == "sensitive_info":
        value = evidence.get("value", "")
        context = evidence.get("context", "")
        # 值较短（可能是真实密钥但无法确认）
        if len(value) < 20:
            return True, "疑似敏感信息，但值较短，需人工确认是否为真实密钥"
        # 有mock关键词但不能100%确定
        if any(kw in context.lower() for kw in ['example', 'sample', 'demo']):
            return True, "上下文含示例/演示等词，需人工确认是否为真实密钥"
        return False, ""
    
    # SQL注入检测：f-string但无法确定拼接内容
    if check_type == "sql_injection":
        has_params = evidence.get("has_parameterized", False)
        user_vars = evidence.get("user_input_vars", [])
        if has_params and not user_vars:
            return True, "f-string SQL有参数化查询，但无法确认拼接内容是否含用户输入，需人工确认"
        if not has_params:
            return False, ""  # 完全没有参数化，确定是问题
        return False, ""
    
    # 文件上传检测：无法确定是否为用户上传
    if check_type == "file_upload":
        scene = evidence.get("scene", "")
        if scene in (SCENE_EMAIL_ATTACHMENT, SCENE_LOCAL_FILE_READ):
            return False, ""  # 确定不是上传，直接跳过
        if scene == SCENE_UNKNOWN:
            return True, "无法确定文件操作是否为用户上传场景，需人工确认"
        return False, ""
    
    return False, ""
