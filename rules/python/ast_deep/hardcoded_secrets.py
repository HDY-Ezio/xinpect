# -*- coding: utf-8 -*-
"""
硬编码密钥/密码/Token AST 深度检测规则集
对应 bandit B105/B106/B107 + 扩展常见敏感词

检测原理：
- 遍历 AST 赋值节点，左值变量名匹配敏感词模式（password/secret/token/key 等）
- 右值为字符串常量时判定为硬编码
- 过滤占位符、示例值、空字符串等低风险场景
- 精确 AST 定位，避免字符串匹配误报

规则ID: PYAST052 - PYAST058
"""

import ast
import re
import os
from typing import List, Dict, Any, Optional


def _parse_ast_safe(filepath: str, content: str) -> Optional[ast.Module]:
    """安全解析AST，语法错误返回None"""
    try:
        return ast.parse(content, filename=filepath)
    except SyntaxError:
        return None


def _is_const_str(node: ast.AST) -> Optional[str]:
    """提取字符串常量值，非字符串返回None"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


# 敏感变量名关键词（变量名包含任一即视为敏感）
SENSITIVE_VAR_PATTERNS = [
    # 密码类 (B105)
    r'passw(or)?d',
    r'passwd',
    r'pwd',
    # 密钥/Token 类 (B106/B107)
    r'secret',
    r'token',
    r'api[_-]?key',
    r'access[_-]?key',
    r'secret[_-]?key',
    r'private[_-]?key',
    r'ssh[_-]?key',
    r'aws[_-]?(access|secret)[_-]?key',
    r'github[_-]?token',
    r'auth[_-]?token',
    r'bearer[_-]?token',
    r'jwt[_-]?secret',
    r'crypto[_-]?key',
    r'encryption[_-]?key',
    # 连接字符串
    r'db[_-]?url',
    r'database[_-]?url',
    r'redis[_-]?url',
    r'mongo[_-]?url',
    r'connection[_-]?string',
]

_sensitive_var_re = re.compile(
    r'^.*(' + '|'.join(SENSITIVE_VAR_PATTERNS) + r').*$',
    re.IGNORECASE
)


def _is_sensitive_var_name(name: str) -> bool:
    """判断变量名是否为敏感变量"""
    if not name or len(name) < 3:
        return False
    return bool(_sensitive_var_re.match(name))


# 占位符/示例值白名单（忽略这些值）
PLACEHOLDER_VALUES = {
    '', 'password', 'passw0rd', '123456', 'admin', 'root',
    'test', 'example', 'sample', 'demo', 'placeholder',
    'your_password', 'your_password_here', 'your_api_key',
    'your-secret-key', 'your-access-key', 'xxx', '****',
    'changeit', 'changeme', 'default', 'none', 'null',
}

# 值中包含这些关键词也跳过（仅当值为明显的占位符时）
PLACEHOLDER_KEYWORDS = [
    'replace_with_', 'replace_me', 'your_', 'your-', '<your', 'todo:', 'fixme:',
    'xxx_placeholder', '_placeholder_', 'placeholder_value',
    'test_key_', 'example_key_', 'sample_key_', 'demo_key_',
    'changeme',
]


def _is_placeholder_value(value: str) -> bool:
    """判断是否为占位符/示例值（应忽略）"""
    v = value.strip().lower()
    if not v:
        return True
    if v in PLACEHOLDER_VALUES:
        return True
    # 纯特殊字符
    if all(c in '*_-.xX?<' for c in v):
        return True
    # 占位符关键词（更精确的匹配，避免误杀包含 example 的真实key）
    for kw in PLACEHOLDER_KEYWORDS:
        if kw in v:
            return True
    # 形如 "your-xxx-here" 结构
    if v.startswith('your') and v.endswith('here'):
        return True
    return False


def _get_target_name(target: ast.AST) -> Optional[str]:
    """从赋值目标节点提取变量名"""
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    if isinstance(target, ast.Subscript):
        # 字典键值对 d["password"] = "..."
        if isinstance(target.slice, ast.Constant) and isinstance(target.slice.value, str):
            return target.slice.value
    return None


def check_hardcoded_passwords_ast(context) -> List[Dict]:
    """
    PYAST052 - 硬编码密码检测（对应 bandit B105）
    
    检测原理：遍历 AST Assign 节点，左值变量名匹配 password/passwd/pwd 等敏感模式，
    右值为字符串常量且非占位符时判定为硬编码密码。
    
    风险等级：P0 (高危)
    修复建议：从环境变量、配置文件或密钥管理服务读取密码，禁止硬编码。
    """
    results = []
    password_vars = {'password', 'passwd', 'pwd', 'pass'}
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        content_lines = content.split('\n')
        
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            
            value_str = _is_const_str(node.value)
            if value_str is None:
                continue
            if _is_placeholder_value(value_str):
                continue
            
            for target in node.targets:
                name = _get_target_name(target)
                if not name:
                    continue
                name_lower = name.lower()
                if not any(pw in name_lower for pw in password_vars):
                    continue
                
                line_text = content_lines[node.lineno - 1] if node.lineno - 1 < len(content_lines) else ""
                # 跳过注释行中的赋值（实际上AST不会解析注释）
                results.append({
                    'id': 'PYAST052',
                    'name': '硬编码密码检测',
                    'level': 'blocking',
                    'category': 'hardcoded_secrets',
                    'message': f'硬编码密码：变量 {name} 的值直接写在代码中，存在凭据泄露风险',
                    'file': fpath,
                    'line': node.lineno,
                    'snippet': line_text.strip()[:120],
                    'fix': f'从环境变量或密钥管理服务读取：{name} = os.environ.get("{name.upper()}")',
                })
    
    return results


def check_hardcoded_secrets_ast(context) -> List[Dict]:
    """
    PYAST053 - 硬编码密钥/Token 检测（对应 bandit B106/B107）
    
    检测原理：遍历 AST Assign 节点，左值变量名匹配 secret/token/api_key/private_key
    /aws_access_key 等敏感模式，右值为字符串常量且非占位符时判定为硬编码密钥。
    
    风险等级：P0 (高危)
    修复建议：使用环境变量、密钥管理服务(AWS KMS/HashiCorp Vault)或配置中心管理密钥。
    """
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    # 排除已被 PYAST052 覆盖的密码类变量
    exclude_vars = {'password', 'passwd', 'pwd', 'pass'}
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        content_lines = content.split('\n')
        
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            
            value_str = _is_const_str(node.value)
            if value_str is None:
                continue
            if _is_placeholder_value(value_str):
                continue
            # 过短的值可能是占位
            if len(value_str) < 8:
                continue
            
            for target in node.targets:
                name = _get_target_name(target)
                if not name:
                    continue
                name_lower = name.lower()
                if any(pw in name_lower for pw in exclude_vars):
                    continue
                if not _is_sensitive_var_name(name):
                    continue
                
                line_text = content_lines[node.lineno - 1] if node.lineno - 1 < len(content_lines) else ""
                results.append({
                    'id': 'PYAST053',
                    'name': '硬编码密钥/Token检测',
                    'level': 'blocking',
                    'category': 'hardcoded_secrets',
                    'message': f'硬编码敏感凭据：变量 {name} 的密钥/Token直接写在代码中',
                    'file': fpath,
                    'line': node.lineno,
                    'snippet': line_text.strip()[:120],
                    'fix': f'从环境变量安全读取：{name} = os.environ.get("{name.upper()}")',
                })
    
    return results


def check_hardcoded_private_key_ast(context) -> List[Dict]:
    """
    PYAST054 - 硬编码私钥检测（对应 bandit B106 扩展）
    
    检测原理：检测字符串常量中包含 -----BEGIN RSA/EC/DSA/OPENSSH PRIVATE KEY----- 
    等私钥头的情况，私钥绝不应出现在源码中。
    
    风险等级：P0 (高危)
    修复建议：立即从代码中移除私钥，使用密钥管理服务或安全的密钥分发机制。
    """
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    private_key_markers = [
        '-----BEGIN RSA PRIVATE KEY-----',
        '-----BEGIN EC PRIVATE KEY-----',
        '-----BEGIN DSA PRIVATE KEY-----',
        '-----BEGIN OPENSSH PRIVATE KEY-----',
        '-----BEGIN PRIVATE KEY-----',
        '-----BEGIN PGP PRIVATE KEY BLOCK-----',
    ]
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        content_lines = content.split('\n')
        
        for node in ast.walk(tree):
            value_str = _is_const_str(node)
            if value_str is None:
                continue
            
            for marker in private_key_markers:
                if marker in value_str:
                    line_text = content_lines[node.lineno - 1] if hasattr(node, 'lineno') and node.lineno - 1 < len(content_lines) else ""
                    results.append({
                        'id': 'PYAST054',
                        'name': '硬编码私钥检测',
                        'level': 'blocking',
                        'category': 'hardcoded_secrets',
                        'message': '代码中硬编码了私钥内容，存在严重密钥泄露风险',
                        'file': fpath,
                        'line': getattr(node, 'lineno', 0),
                        'snippet': line_text.strip()[:120],
                        'fix': '立即移除代码中的私钥，使用密钥管理服务或文件权限保护的密钥文件',
                    })
                    break
    
    return results


def check_hardcoded_aws_keys_ast(context) -> List[Dict]:
    """
    PYAST055 - 硬编码 AWS 密钥检测（对应 bandit B107）
    
    检测原理：检测值以 AKIA/ASIA 开头（AWS Access Key ID 特征）的字符串常量，
    或变量名匹配 aws_access_key_id/aws_secret_access_key 且值非空。
    
    风险等级：P0 (高危)
    修复建议：使用 AWS IAM 角色、环境变量或 ~/.aws/credentials 文件管理密钥。
    """
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    # AWS Access Key ID 特征: AKIA/ASIA + 16位字母数字
    aws_key_pattern = re.compile(r'(A[SK]IA[0-9A-Z]{16})')
    # AWS Secret Access Key 特征: 40位 base64 字符
    aws_secret_pattern = re.compile(r'^[0-9a-zA-Z/+=]{40}$')
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        content_lines = content.split('\n')
        
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            
            value_str = _is_const_str(node.value)
            if value_str is None:
                continue
            if _is_placeholder_value(value_str):
                continue
            
            is_aws_key = False
            # 方式一：值匹配 AWS Access Key ID 模式
            if aws_key_pattern.search(value_str):
                is_aws_key = True
            # 方式二：变量名含 aws 且值匹配 secret key 长度模式
            else:
                for target in node.targets:
                    name = _get_target_name(target)
                    if name and 'aws' in name.lower() and 'secret' in name.lower():
                        if aws_secret_pattern.match(value_str.strip()):
                            is_aws_key = True
                        break
            
            if is_aws_key:
                line_text = content_lines[node.lineno - 1] if node.lineno - 1 < len(content_lines) else ""
                results.append({
                    'id': 'PYAST055',
                    'name': '硬编码AWS密钥检测',
                    'level': 'blocking',
                    'category': 'hardcoded_secrets',
                    'message': '代码中硬编码了AWS访问密钥，存在云资源被滥用的严重风险',
                    'file': fpath,
                    'line': node.lineno,
                    'snippet': line_text.strip()[:120],
                    'fix': '使用IAM角色或环境变量管理AWS密钥：os.environ.get("AWS_ACCESS_KEY_ID")',
                })
    
    return results


def check_hardcoded_connection_string_ast(context) -> List[Dict]:
    """
    PYAST056 - 硬编码数据库连接字符串检测
    
    检测原理：检测包含 mysql:///postgresql:///mongodb:///redis:// 等协议且
    内嵌用户名密码的字符串常量（如 mysql://user:pass@host/db）。
    
    风险等级：P1 (中危)
    修复建议：从环境变量或配置中心读取连接字符串，敏感信息使用变量替换。
    """
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    # 带认证信息的连接串模式: scheme://user:pass@host...
    conn_pattern = re.compile(
        r'^(mysql|postgresql|postgres|mongodb|redis|mssql|oracle|amqp|ftp)://'
        r'[^:@/]+:[^:@/]+@',
        re.IGNORECASE
    )
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        content_lines = content.split('\n')
        
        for node in ast.walk(tree):
            value_str = _is_const_str(node)
            if value_str is None:
                continue
            if _is_placeholder_value(value_str):
                continue
            
            if conn_pattern.match(value_str.strip()):
                line = getattr(node, 'lineno', 0)
                line_text = content_lines[line - 1] if line and line - 1 < len(content_lines) else ""
                results.append({
                    'id': 'PYAST056',
                    'name': '硬编码数据库连接字符串检测',
                    'level': 'problem',
                    'category': 'hardcoded_secrets',
                    'message': '硬编码包含用户名密码的数据库连接字符串',
                    'file': fpath,
                    'line': line,
                    'snippet': line_text.strip()[:120],
                    'fix': '从环境变量读取连接串：DATABASE_URL = os.environ.get("DATABASE_URL")',
                })
    
    return results


def check_debug_statements_ast(context) -> List[Dict]:
    """
    PYAST057 - 生产代码中的调试语句（对应 bandit B101）
    
    检测原理：检测 assert 语句、breakpoint() 调用、pdb.set_trace() 等调试代码，
    这些语句在生产环境可能被利用或影响性能。
    
    风险等级：P2 (低危，但生产代码必须清理)
    修复建议：生产代码中移除 assert/breakpoint/pdb，使用日志替代调试输出。
    """
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        # 测试文件通常允许调试语句
        basename = os.path.basename(fpath)
        if basename.startswith('test_') or basename.endswith('_test.py'):
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        content_lines = content.split('\n')
        
        for node in ast.walk(tree):
            # assert 语句
            if isinstance(node, ast.Assert):
                line_text = content_lines[node.lineno - 1] if node.lineno - 1 < len(content_lines) else ""
                results.append({
                    'id': 'PYAST057',
                    'name': '调试语句遗留检测',
                    'level': 'suggestion',
                    'category': 'hardcoded_secrets',
                    'message': '生产代码中遗留 assert 语句，使用 -O 优化时会被跳过',
                    'file': fpath,
                    'line': node.lineno,
                    'snippet': line_text.strip()[:120],
                    'fix': '使用显式条件判断+异常抛出替代 assert',
                })
                continue
            
            # breakpoint() / pdb.set_trace()
            if isinstance(node, ast.Call):
                func = node.func
                is_debug_call = False
                detail = ""
                
                if isinstance(func, ast.Name) and func.id == 'breakpoint':
                    is_debug_call = True
                    detail = 'breakpoint()'
                elif isinstance(func, ast.Attribute) and func.attr == 'set_trace':
                    # pdb.set_trace() / import pdb; pdb.set_trace()
                    if isinstance(func.value, ast.Name) and func.value.id == 'pdb':
                        is_debug_call = True
                        detail = 'pdb.set_trace()'
                
                if is_debug_call:
                    line_text = content_lines[node.lineno - 1] if node.lineno - 1 < len(content_lines) else ""
                    results.append({
                        'id': 'PYAST057',
                        'name': '调试语句遗留检测',
                        'level': 'suggestion',
                        'category': 'hardcoded_secrets',
                        'message': f'生产代码中遗留 {detail} 调试调用',
                        'file': fpath,
                        'line': node.lineno,
                        'snippet': line_text.strip()[:120],
                        'fix': '移除生产代码中的调试调用',
                    })
    
    return results


def check_hardcoded_tmpfile_ast(context) -> List[Dict]:
    """
    PYAST058 - 硬编码临时文件路径（对应 bandit B108/B305/B306）
    
    检测原理：检测 open() 调用中使用 /tmp/ 开头的硬编码路径或 mktemp()，
    存在符号链接攻击和竞争条件风险。
    
    风险等级：P1 (中危)
    修复建议：使用 tempfile.mkstemp() / tempfile.NamedTemporaryFile() 替代硬编码临时路径。
    """
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    tmp_path_prefixes = ('/tmp/', '/var/tmp/', '/dev/shm/', 'C:\\Windows\\Temp\\')
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        content_lines = content.split('\n')
        
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            
            func = node.func
            func_name = None
            if isinstance(func, ast.Name):
                func_name = func.id
            elif isinstance(func, ast.Attribute):
                func_name = func.attr
            
            # open("/tmp/xxx", ...)
            if func_name == 'open' and node.args:
                path_str = _is_const_str(node.args[0])
                if path_str and any(path_str.startswith(p) for p in tmp_path_prefixes):
                    line_text = content_lines[node.lineno - 1] if node.lineno - 1 < len(content_lines) else ""
                    results.append({
                        'id': 'PYAST058',
                        'name': '硬编码临时文件路径检测',
                        'level': 'problem',
                        'category': 'hardcoded_secrets',
                        'message': '使用硬编码临时文件路径，存在符号链接攻击和竞争条件风险',
                        'file': fpath,
                        'line': node.lineno,
                        'snippet': line_text.strip()[:120],
                        'fix': '使用 tempfile.mkstemp() 或 tempfile.NamedTemporaryFile() 安全创建临时文件',
                    })
            
            # tempfile.mktemp() — 已废弃，存在竞争条件
            if func_name == 'mktemp':
                line_text = content_lines[node.lineno - 1] if node.lineno - 1 < len(content_lines) else ""
                results.append({
                    'id': 'PYAST058',
                    'name': '硬编码临时文件路径检测',
                    'level': 'problem',
                    'category': 'hardcoded_secrets',
                    'message': '使用 tempfile.mktemp() 已废弃函数，存在竞争条件风险',
                    'file': fpath,
                    'line': node.lineno,
                    'snippet': line_text.strip()[:120],
                    'fix': '使用 tempfile.mkstemp() 替代 mktemp()',
                })
    
    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'PYAST052',
        'name': '硬编码密码检测',
        'level': 'blocking',
        'category': 'security_hardcoded_secrets',
        'module_id': '8',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': 'AST级检测硬编码密码变量赋值（B105）',
        'check': check_hardcoded_passwords_ast,
    },
    {
        'id': 'PYAST053',
        'name': '硬编码密钥/Token检测',
        'level': 'blocking',
        'category': 'security_hardcoded_secrets',
        'module_id': '8',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': 'AST级检测硬编码密钥、Token、API Key等敏感凭据（B106/B107）',
        'check': check_hardcoded_secrets_ast,
    },
    {
        'id': 'PYAST054',
        'name': '硬编码私钥检测',
        'level': 'blocking',
        'category': 'security_hardcoded_secrets',
        'module_id': '8',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测字符串常量中包含私钥PEM头的硬编码私钥（B106扩展）',
        'check': check_hardcoded_private_key_ast,
    },
    {
        'id': 'PYAST055',
        'name': '硬编码AWS密钥检测',
        'level': 'blocking',
        'category': 'security_hardcoded_secrets',
        'module_id': '8',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测硬编码AWS Access Key / Secret Key（B107）',
        'check': check_hardcoded_aws_keys_ast,
    },
    {
        'id': 'PYAST056',
        'name': '硬编码数据库连接字符串检测',
        'level': 'problem',
        'category': 'security_hardcoded_secrets',
        'module_id': '8',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测包含用户名密码的硬编码数据库/缓存连接字符串',
        'check': check_hardcoded_connection_string_ast,
    },
    {
        'id': 'PYAST057',
        'name': '调试语句遗留检测',
        'level': 'suggestion',
        'category': 'security_hardcoded_secrets',
        'module_id': '8',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测生产代码中的 assert/breakpoint/pdb.set_trace() 调试语句（B101）',
        'check': check_debug_statements_ast,
    },
    {
        'id': 'PYAST058',
        'name': '硬编码临时文件路径检测',
        'level': 'problem',
        'category': 'security_hardcoded_secrets',
        'module_id': '8',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测硬编码/tmp路径和tempfile.mktemp()竞争条件风险（B108/B305）',
        'check': check_hardcoded_tmpfile_ast,
    },
]

# 供 RuleLoader 发现
ALL_RULES = RULES
