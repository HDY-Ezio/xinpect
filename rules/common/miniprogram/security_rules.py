"""
小程序安全审计规则集 (SEC-*)
微信小程序专属安全检查
包含: API域名硬编码、不安全HTTP请求、console敏感信息泄露、
      token明文存储、AppSecret前端暴露、敏感数据URL传参、
      未授权获取用户信息、eval/Function注入

v3.5: 每条规则带suggestion_code修复示例
"""

import re
import os
from typing import List, Dict, Any


# ===== 敏感信息关键词 =====
_SENSITIVE_KEYWORDS = [
    'password', 'passwd', 'pwd', 'token', 'access_token', 'refresh_token',
    'secret', 'appSecret', 'app_secret', 'apiKey', 'api_key', 'apikey',
    'private_key', 'privateKey', 'sessionKey', 'session_key',
    'openid', 'unionid', 'card_no', 'cardNo', 'id_card',
    'phone', 'mobile', '身份证',
]

# console.log 中出现这些关键词时报警
_CONSOLE_SENSITIVE_PATTERNS = [
    r'console\.(log|warn|error|info|debug)\s*\([^)]*\b(password|passwd|pwd|token|access_token|refresh_token|secret|appSecret|api_key|apiKey|sessionKey|private_key|privateKey)\b',
    r'console\.(log|warn|error|info|debug)\s*\([^)]*\b(userInfo|user_info|phone|mobile|身份证|card_no|cardNo)\b',
]

# wx.setStorageSync 明文存token的模式
_TOKEN_STORAGE_PATTERNS = [
    r"wx\.setStorageSync\s*\(\s*['\"](?:access_?token|refresh_?token|auth_?token|user_?token|jwt|session)['\"]",
    r"wx\.setStorageSync\s*\(\s*['\"](?:token)['\"]",
]

# AppSecret 暴露模式
_APP_SECRET_PATTERNS = [
    r"['\"]?(?:app_?secret|appSecret|APP_?SECRET)['\"]?\s*[:=]\s*['\"][a-zA-Z0-9]{16,}['\"]",
    r"['\"]?(?:api_?key|apiKey|API_?KEY)['\"]?\s*[:=]\s*['\"][a-zA-Z0-9]{20,}['\"]",
]

# 硬编码域名模式（完整URL含协议+域名，在wx.request等调用中直接使用）
_HARDCODED_URL_PATTERN = re.compile(
    r"""(?:wx\.request|wx\.uploadFile|wx\.downloadFile|wx\.connectSocket)\s*\(\s*\{[^}]*?url\s*:\s*['"]https?://([a-zA-Z0-9._-]+)""",
    re.DOTALL,
)

# 不安全HTTP请求
_HTTP_PATTERN = re.compile(
    r"""(?:wx\.request|wx\.uploadFile|wx\.downloadFile|wx\.connectSocket)\s*\(\s*\{[^}]*?url\s*:\s*['"]http://""",
    re.DOTALL,
)

# 敏感数据在URL查询参数中
_SENSITIVE_QUERY_PATTERN = re.compile(
    r"""['"]https?://[^'"]*?\?(?:[^'"]*?&)?(?:token|access_token|password|passwd|secret|openid|session_key|api_key)=""",
    re.IGNORECASE,
)

# eval / new Function 注入
_EVAL_PATTERNS = [
    (r'\beval\s*\(', 'eval()可执行任意代码'),
    (r'\bnew\s+Function\s*\(', 'new Function()可执行任意代码'),
    (r'\bsetTimeout\s*\(\s*["\']', 'setTimeout字符串参数等价于eval'),
    (r'\bsetInterval\s*\(\s*["\']', 'setInterval字符串参数等价于eval'),
]


def _get_line_number(content: str, pos: int) -> int:
    """根据字符位置获取行号"""
    return content[:pos].count('\n') + 1


def _truncate(s: str, max_len: int = 120) -> str:
    """截断字符串"""
    s = s.strip()
    return s[:max_len] + '...' if len(s) > max_len else s


# ===== SEC-001 API域名硬编码 =====
def check_sec_001_hardcoded_api_url(context) -> List[Dict]:
    """SEC-001 API域名硬编码 - wx.request等调用中直接写死完整URL而非配置化"""
    results = []
    
    js_files = context.find_files([".js"])
    if not js_files:
        return results
    
    # 常见配置变量名（存在这些说明已配置化，不算硬编码）
    config_var_patterns = [
        r'\b(?:BASE_URL|API_BASE|apiBase|baseUrl|API_HOST|HOST_URL|SERVER_URL|apiUrl)\b',
        r'const\s+\w*[Uu]rl\s*=',
        r'const\s+\w*[Hh]ost\s*=',
    ]
    
    for fpath in js_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        # 跳过配置文件本身（这些文件定义BASE_URL是正常的）
        basename = os.path.basename(fpath).lower()
        if basename in ('config.js', 'api.js', 'api-core.js', 'constants.js', 'env.js', 'request.js'):
            continue
        
        issues = []
        for m in _HARDCODED_URL_PATTERN.finditer(content):
            domain = m.group(1)
            # 排除 localhost / 127.0.0.1 / 占位域名
            if domain in ('localhost', '127.0.0.1', '0.0.0.0', 'example.com', 'api.example.com'):
                continue
            
            line_num = _get_line_number(content, m.start())
            line_content = content.split('\n')[line_num - 1] if line_num <= len(content.split('\n')) else ''
            issues.append({
                'line': line_num,
                'domain': domain,
                'snippet': _truncate(line_content),
            })
        
        # 每个文件最多报告3个
        for issue in issues[:3]:
            results.append({
                'id': 'WXSEC-MP-001',
                'name': 'API域名硬编码',
                'level': 'error',
                'message': f"wx.request中硬编码域名 '{issue['domain']}'，应使用配置常量",
                'detail': f"位置: 第{issue['line']}行\n代码: {issue['snippet']}",
                'file': fpath,
                'line': issue['line'],
                'fix': '将API域名提取到统一配置文件中，通过常量引用',
                'suggestion_code': (
                    '// config.js — 统一配置\n'
                    'const BASE_URL = "https://api.example.com";\n'
                    'module.exports = { BASE_URL };\n\n'
                    '// request.js — 使用配置\n'
                    'const { BASE_URL } = require("./config");\n'
                    'wx.request({\n'
                    '  url: `${BASE_URL}/api/products`,  // ✅ 配置化\n'
                    '  // url: "https://api.example.com/api/products",  // ❌ 硬编码\n'
                    '});'
                ),
            })
        
        if len(issues) > 3:
            results.append({
                'id': 'WXSEC-MP-001',
                'name': 'API域名硬编码',
                'level': 'warning',
                'message': f"该文件还有{len(issues) - 3}处域名硬编码（仅展示前3处）",
                'detail': f"文件: {fpath}",
                'file': fpath,
                'line': 0,
                'fix': '将所有API域名提取到统一配置文件中',
            })
    
    return results


# ===== SEC-002 不安全HTTP请求 =====
def check_sec_002_insecure_http(context) -> List[Dict]:
    """SEC-002 不安全HTTP请求 - wx.request使用http://而非https://"""
    results = []
    
    js_files = context.find_files([".js"])
    if not js_files:
        return results
    
    for fpath in js_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        for m in _HTTP_PATTERN.finditer(content):
            line_num = _get_line_number(content, m.start())
            line_content = content.split('\n')[line_num - 1] if line_num <= len(content.split('\n')) else ''
            
            results.append({
                'id': 'WXSEC-MP-002',
                'name': '不安全HTTP请求',
                'level': 'error',
                'message': 'wx.request使用了不安全的http://协议，微信要求必须使用HTTPS',
                'detail': f"位置: 第{line_num}行\n代码: {_truncate(line_content)}",
                'file': fpath,
                'line': line_num,
                'fix': '将http://改为https://，并在小程序后台配置合法域名',
                'suggestion_code': (
                    '// ❌ 不安全\n'
                    'wx.request({ url: "http://api.example.com/data" });\n\n'
                    '// ✅ 使用HTTPS\n'
                    'wx.request({ url: "https://api.example.com/data" });'
                ),
            })
            break  # 每个文件只报一次
    
    return results


# ===== SEC-003 console输出敏感信息 =====
def check_sec_003_console_sensitive(context) -> List[Dict]:
    """SEC-003 console输出敏感信息 - console.log/warn/error输出含token/password等"""
    results = []
    
    js_files = context.find_files([".js"])
    if not js_files:
        return results
    
    for fpath in js_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        issues = []
        for pattern in _CONSOLE_SENSITIVE_PATTERNS:
            for m in re.finditer(pattern, content, re.IGNORECASE):
                line_num = _get_line_number(content, m.start())
                line_content = content.split('\n')[line_num - 1] if line_num <= len(content.split('\n')) else ''
                issues.append({
                    'line': line_num,
                    'snippet': _truncate(line_content),
                })
        
        # 去重（同一行可能匹配多个模式）
        seen_lines = set()
        unique_issues = []
        for issue in issues:
            if issue['line'] not in seen_lines:
                seen_lines.add(issue['line'])
                unique_issues.append(issue)
        
        for issue in unique_issues[:5]:
            results.append({
                'id': 'WXSEC-MP-003',
                'name': 'console敏感信息泄露',
                'level': 'error',
                'message': f"console输出包含敏感信息（token/password等），生产环境会泄露用户数据",
                'detail': f"位置: 第{issue['line']}行\n代码: {issue['snippet']}",
                'file': fpath,
                'line': issue['line'],
                'fix': '移除敏感信息的console输出，或使用脱敏处理',
                'suggestion_code': (
                    '// ❌ 直接输出敏感信息\n'
                    'console.log("token:", token);\n'
                    'console.log("user:", { phone, password });\n\n'
                    '// ✅ 移除或脱敏\n'
                    '// console.log("token:", token);  // 删除\n'
                    'console.log("login success, uid:", uid);  // 只输出非敏感字段'
                ),
            })
    
    return results


# ===== SEC-004 token明文存储 =====
def check_sec_004_token_plaintext_storage(context) -> List[Dict]:
    """SEC-004 token明文存储 - wx.setStorageSync直接存token明文"""
    results = []
    
    js_files = context.find_files([".js"])
    if not js_files:
        return results
    
    for fpath in js_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        issues = []
        for pattern in _TOKEN_STORAGE_PATTERNS:
            for m in re.finditer(pattern, content, re.IGNORECASE):
                line_num = _get_line_number(content, m.start())
                line_content = content.split('\n')[line_num - 1] if line_num <= len(content.split('\n')) else ''
                issues.append({
                    'line': line_num,
                    'snippet': _truncate(line_content),
                })
        
        # 去重
        seen_lines = set()
        unique_issues = []
        for issue in issues:
            if issue['line'] not in seen_lines:
                seen_lines.add(issue['line'])
                unique_issues.append(issue)
        
        for issue in unique_issues[:3]:
            results.append({
                'id': 'WXSEC-MP-004',
                'name': 'token明文存储',
                'level': 'warning',
                'message': 'token以明文存储到wx.Storage，可能被篡改或窃取',
                'detail': f"位置: 第{issue['line']}行\n代码: {issue['snippet']}",
                'file': fpath,
                'line': issue['line'],
                'fix': '对token进行加密后再存储，或改用服务端session方案',
                'suggestion_code': (
                    '// ❌ 明文存储token\n'
                    'wx.setStorageSync("access_token", token);\n\n'
                    '// ✅ 方案1: 简单混淆（至少不直接可读）\n'
                    'const encrypt = (str) => btoa(encodeURIComponent(str));\n'
                    'wx.setStorageSync("tk", encrypt(token));\n\n'
                    '// ✅ 方案2: 服务端session（更安全）\n'
                    '// 前端只存session_id，token留在服务端\n'
                    '// wx.setStorageSync("sid", sessionId);'
                ),
            })
    
    return results


# ===== SEC-005 AppSecret前端暴露 =====
def check_sec_005_app_secret_exposure(context) -> List[Dict]:
    """SEC-005 AppSecret前端暴露 - 代码中包含appSecret/apiKey等密钥"""
    results = []
    
    js_files = context.find_files([".js"])
    if not js_files:
        return results
    
    for fpath in js_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        issues = []
        for pattern in _APP_SECRET_PATTERNS:
            for m in re.finditer(pattern, content, re.IGNORECASE):
                line_num = _get_line_number(content, m.start())
                line_content = content.split('\n')[line_num - 1] if line_num <= len(content.split('\n')) else ''
                # 脱敏显示
                safe_snippet = re.sub(r"['\"][a-zA-Z0-9]{8,}['\"]", "'***REDACTED***'", line_content)
                issues.append({
                    'line': line_num,
                    'snippet': _truncate(safe_snippet),
                })
        
        # 去重
        seen_lines = set()
        unique_issues = []
        for issue in issues:
            if issue['line'] not in seen_lines:
                seen_lines.add(issue['line'])
                unique_issues.append(issue)
        
        for issue in unique_issues[:3]:
            results.append({
                'id': 'WXSEC-MP-005',
                'name': 'AppSecret/ApiKey前端暴露',
                'level': 'error',
                'message': '代码中硬编码了AppSecret或ApiKey，小程序前端代码可被反编译，密钥会泄露',
                'detail': f"位置: 第{issue['line']}行\n代码: {issue['snippet']}",
                'file': fpath,
                'line': issue['line'],
                'fix': '将密钥移到服务端，前端通过登录接口获取临时凭证',
                'suggestion_code': (
                    '// ❌ AppSecret写在前端（可被反编译获取）\n'
                    'const appSecret = "abc123def456ghi789";\n'
                    'wx.request({ url: `https://api.weixin.qq.com/sns/jscode2session?secret=${appSecret}` });\n\n'
                    '// ✅ 密钥只在服务端\n'
                    '// 前端: 只发送wx.login的code到自己的服务端\n'
                    'wx.login({\n'
                    '  success: ({ code }) => {\n'
                    '    wx.request({\n'
                    '      url: `${BASE_URL}/auth/login`,\n'
                    '      data: { code },  // 只传code\n'
                    '    });\n'
                    '  }\n'
                    '});\n'
                    '// 服务端: 用code + appSecret换取session（密钥不暴露）'
                ),
            })
    
    return results


# ===== SEC-006 敏感数据URL参数传递 =====
def check_sec_006_sensitive_query_params(context) -> List[Dict]:
    """SEC-006 敏感数据URL参数传递 - GET请求URL中包含token/password等"""
    results = []
    
    js_files = context.find_files([".js"])
    if not js_files:
        return results
    
    for fpath in js_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        issues = []
        for m in _SENSITIVE_QUERY_PATTERN.finditer(content):
            line_num = _get_line_number(content, m.start())
            line_content = content.split('\n')[line_num - 1] if line_num <= len(content.split('\n')) else ''
            # 脱敏
            safe_snippet = re.sub(r'(token|password|secret|openid|api_key)=[^&"\'\s]+', r'\1=***', line_content, flags=re.IGNORECASE)
            issues.append({
                'line': line_num,
                'snippet': _truncate(safe_snippet),
            })
        
        # 去重
        seen_lines = set()
        unique_issues = []
        for issue in issues:
            if issue['line'] not in seen_lines:
                seen_lines.add(issue['line'])
                unique_issues.append(issue)
        
        for issue in unique_issues[:3]:
            results.append({
                'id': 'WXSEC-MP-006',
                'name': '敏感数据URL参数传递',
                'level': 'warning',
                'message': '敏感信息（token/password等）出现在URL查询参数中，会被日志和浏览器历史记录留存',
                'detail': f"位置: 第{issue['line']}行\n代码: {issue['snippet']}",
                'file': fpath,
                'line': issue['line'],
                'fix': '敏感数据应放在请求体(body)或请求头(header)中，不要放在URL参数',
                'suggestion_code': (
                    '// ❌ token放在URL参数中\n'
                    'wx.request({\n'
                    '  url: `${BASE_URL}/data?token=${token}`,\n'
                    '  method: "GET",\n'
                    '});\n\n'
                    '// ✅ token放在请求头中\n'
                    'wx.request({\n'
                    '  url: `${BASE_URL}/data`,\n'
                    '  method: "GET",\n'
                    '  header: { "Authorization": `Bearer ${token}` },\n'
                    '});'
                ),
            })
    
    return results


# ===== SEC-007 未授权获取用户信息 =====
def check_sec_007_unauthorized_user_info(context) -> List[Dict]:
    """SEC-007 未授权获取用户信息 - 直接调用wx.getUserInfo未配合授权流程"""
    results = []
    
    js_files = context.find_files([".js"])
    if not js_files:
        return results
    
    for fpath in js_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        # 检查 wx.getUserInfo / wx.getUserProfile 调用
        user_info_pattern = re.compile(r'wx\.(getUserInfo|getUserProfile)\s*\(')
        # 检查是否有授权流程配套（wx.getSetting / scope.userInfo / button open-type）
        has_auth_check = bool(re.search(r'wx\.getSetting|scope\.userInfo|scope\[.userInfo.\]|open-type\s*=\s*["\']getUserInfo', content))
        
        for m in user_info_pattern.finditer(content):
            line_num = _get_line_number(content, m.start())
            line_content = content.split('\n')[line_num - 1] if line_num <= len(content.split('\n')) else ''
            
            if not has_auth_check:
                results.append({
                    'id': 'WXSEC-MP-007',
                    'name': '未授权获取用户信息',
                    'level': 'warning',
                    'message': '调用wx.getUserInfo但未配套授权检查流程，可能导致授权失败或被审核拒绝',
                    'detail': f"位置: 第{line_num}行\n代码: {_truncate(line_content)}\n未检测到wx.getSetting或scope.userInfo授权检查",
                    'file': fpath,
                    'line': line_num,
                    'fix': '获取用户信息前先检查授权状态，未授权时引导用户通过按钮授权',
                    'suggestion_code': (
                        '// ❌ 直接调用，未检查授权\n'
                        'wx.getUserInfo({ success: (res) => { ... } });\n\n'
                        '// ✅ 先检查授权状态\n'
                        'wx.getSetting({\n'
                        '  success: (res) => {\n'
                        '    if (res.authSetting["scope.userInfo"]) {\n'
                        '      // 已授权，直接获取\n'
                        '      wx.getUserInfo({ success: (res) => { ... } });\n'
                        '    } else {\n'
                        '      // 未授权，引导用户点击按钮授权\n'
                        '      // <button open-type="getUserInfo" bindgetuserinfo="onAuth">\n'
                        '    }\n'
                        '  }\n'
                        '});'
                    ),
                })
                break  # 每个文件只报一次
    
    return results


# ===== SEC-008 eval/Function注入风险 =====
def check_sec_008_eval_injection(context) -> List[Dict]:
    """SEC-008 eval/Function注入 - 使用eval()、new Function()等可执行任意代码"""
    results = []
    
    js_files = context.find_files([".js"])
    if not js_files:
        return results
    
    for fpath in js_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        issues = []
        for pattern, desc in _EVAL_PATTERNS:
            for m in re.finditer(pattern, content):
                line_num = _get_line_number(content, m.start())
                line_content = content.split('\n')[line_num - 1] if line_num <= len(content.split('\n')) else ''
                issues.append({
                    'line': line_num,
                    'desc': desc,
                    'snippet': _truncate(line_content),
                })
        
        # 去重
        seen_lines = set()
        unique_issues = []
        for issue in issues:
            if issue['line'] not in seen_lines:
                seen_lines.add(issue['line'])
                unique_issues.append(issue)
        
        for issue in unique_issues[:3]:
            results.append({
                'id': 'WXSEC-MP-008',
                'name': 'eval/Function注入风险',
                'level': 'error',
                'message': f"使用了{issue['desc']}，存在代码注入风险",
                'detail': f"位置: 第{issue['line']}行\n代码: {issue['snippet']}",
                'file': fpath,
                'line': issue['line'],
                'fix': '使用JSON.parse替代eval解析JSON，使用函数引用替代字符串参数',
                'suggestion_code': (
                    '// ❌ eval解析JSON（有注入风险）\n'
                    'const data = eval("(" + jsonStr + ")");\n\n'
                    '// ✅ 使用JSON.parse\n'
                    'const data = JSON.parse(jsonStr);\n\n'
                    '// ❌ setTimeout字符串参数\n'
                    'setTimeout("doSomething(" + id + ")", 1000);\n\n'
                    '// ✅ 使用函数引用\n'
                    'setTimeout(() => doSomething(id), 1000);'
                ),
            })
    
    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'WXSEC-MP-001',
        'name': 'API域名硬编码',
        'level': 'blocking',
        'category': 'security',
        'module_id': '3',
        'applicable_types': ['miniprogram', 'mixed'],
        'description': 'wx.request等网络调用中直接写死完整域名URL，应使用配置常量统一管理',
        'check': check_sec_001_hardcoded_api_url,
    },
    {
        'id': 'WXSEC-MP-002',
        'name': '不安全HTTP请求',
        'level': 'blocking',
        'category': 'security',
        'module_id': '3',
        'applicable_types': ['miniprogram', 'mixed'],
        'description': 'wx.request使用了http://协议，微信要求所有网络请求必须使用HTTPS',
        'check': check_sec_002_insecure_http,
    },
    {
        'id': 'WXSEC-MP-003',
        'name': 'console敏感信息泄露',
        'level': 'blocking',
        'category': 'security',
        'module_id': '3',
        'applicable_types': ['miniprogram', 'mixed'],
        'description': 'console.log/warn/error输出包含token/password等敏感信息，生产环境会泄露用户数据',
        'check': check_sec_003_console_sensitive,
    },
    {
        'id': 'WXSEC-MP-004',
        'name': 'token明文存储',
        'level': 'problem',
        'category': 'security',
        'module_id': '3',
        'applicable_types': ['miniprogram', 'mixed'],
        'description': 'wx.setStorageSync直接存储token明文，可能被篡改或窃取',
        'check': check_sec_004_token_plaintext_storage,
    },
    {
        'id': 'WXSEC-MP-005',
        'name': 'AppSecret/ApiKey前端暴露',
        'level': 'blocking',
        'category': 'security',
        'module_id': '3',
        'applicable_types': ['miniprogram', 'mixed'],
        'description': '代码中硬编码了AppSecret或ApiKey，小程序前端代码可被反编译导致密钥泄露',
        'check': check_sec_005_app_secret_exposure,
    },
    {
        'id': 'WXSEC-MP-006',
        'name': '敏感数据URL参数传递',
        'level': 'problem',
        'category': 'security',
        'module_id': '3',
        'applicable_types': ['miniprogram', 'mixed'],
        'description': '敏感信息（token/password等）出现在URL查询参数中，会被日志和浏览器历史记录留存',
        'check': check_sec_006_sensitive_query_params,
    },
    {
        'id': 'WXSEC-MP-007',
        'name': '未授权获取用户信息',
        'level': 'problem',
        'category': 'security',
        'module_id': '3',
        'applicable_types': ['miniprogram', 'mixed'],
        'description': '调用wx.getUserInfo但未配套授权检查流程，可能导致授权失败或审核被拒',
        'check': check_sec_007_unauthorized_user_info,
    },
    {
        'id': 'WXSEC-MP-008',
        'name': 'eval/Function注入风险',
        'level': 'blocking',
        'category': 'security',
        'module_id': '3',
        'applicable_types': ['miniprogram', 'mixed'],
        'description': '使用eval()、new Function()等可执行任意代码的函数，存在代码注入风险',
        'check': check_sec_008_eval_injection,
    },
]
