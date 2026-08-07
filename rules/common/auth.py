"""安全审计规则集 - 子模块
从 security.py 拆分而来，包含以下规则: 3.4, 3.5, 3.8, 3.9, 3.10
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


def _get_lang(fpath: str) -> str:
    """根据扩展名获取语言标识"""
    ext = os.path.splitext(fpath)[1].lower()
    if ext == '.py':
        return 'py'
    return 'js'


def _skip_line_py(line_no: int, lines: List[str],
                  docstring_ranges: List, rules_list_range) -> bool:
    """v4.4: 判断 Python 文件中某行是否应跳过（docstring / RULES列表）"""
    if not _HAS_CODE_CONTEXT_UTILS:
        return False
    if docstring_ranges and is_line_in_range(line_no, docstring_ranges):
        return True
    if rules_list_range and rules_list_range[0] <= line_no <= rules_list_range[1]:
        return True
    return False


def _prepare_py_skip_ranges(lines: List[str]):
    """v4.4: 预计算 Python 文件的跳过范围"""
    if not _HAS_CODE_CONTEXT_UTILS:
        return [], None
    doc_ranges = find_python_docstring_ranges(lines)
    rules_range = find_python_rules_list_range(lines)
    return doc_ranges, rules_range


# ===== 3.4 鉴权绕过 =====
def check_3_4_auth_bypass(context) -> List[Dict]:
    """3.4 鉴权绕过 - 检查是否存在鉴权绕过风险"""
    results = []

    # skill/agent类型是CLI工具或本地脚本，无Web鉴权体系，跳过鉴权绕过检测
    if context.project_type in ("skill", "agent"):
        return results
    
    be_content = context.get_backend_content()
    if not be_content:
        return results
    
    has_auth_mw = "auth_middleware" in be_content
    if not has_auth_mw:
        results.append({
            'id': '3.4',
            'name': '鉴权绕过',
            'level': 'error',
            'message': '未发现auth_middleware，所有接口可能绕过鉴权',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '确保所有非公开接口经过鉴权中间件验证',
            'category': 'security',
        })
    
    return results


# ===== 3.5 CORS/CSRF配置 =====


# ===== 3.5 CORS/CSRF配置 =====
def check_3_5_cors_csrf(context) -> List[Dict]:
    """3.5 CORS/CSRF配置 - 检查CORS/CSRF配置是否安全"""
    results = []

    # skill/agent类型是CLI工具或本地脚本，无Web服务，跳过CORS/CSRF检测
    if context.project_type in ("skill", "agent"):
        return results
    
    be_content = context.get_backend_content()
    if not be_content:
        return results
    
    cors_issues = []
    cors_suggestions = []
    
    has_cors_whitelist = bool(re.search(
        r'CORS_ALLOWED_PATTERNS|_CURRENT_ORIGIN|cors.*whitelist|cors.*白名单|allowed_origin',
        be_content, re.IGNORECASE))
    
    idx = be_content.find("def get_cors_headers")
    if idx >= 0:
        chunk = be_content[idx:idx+500]
        if '"*"' in chunk and "Allow-Origin" in chunk:
            if has_cors_whitelist:
                cors_suggestions.append("cors_headers含通配符*但已有动态白名单校验(CORS_ALLOWED_PATTERNS)")
            else:
                cors_issues.append("cors_headers返回通配符Origin")
    
    if "Access-Control-Allow-Origin" in be_content and '"*"' in be_content:
        if has_cors_whitelist:
            if not cors_suggestions:
                cors_suggestions.append("CORS含通配符*但已有动态白名单校验")
        else:
            cors_issues.append("CORS配置为通配符*，过于宽松")
    
    if cors_issues:
        results.append({
            'id': '3.5',
            'name': 'CORS/CSRF配置',
            'level': 'warning',
            'message': f'发现 {len(cors_issues)} 处CORS/CSRF配置问题',
            'file': '',
            'line': 0,
            'snippet': '\n'.join(cors_issues),
            'fix': '限制CORS为具体域名，添加CSRF Token验证',
            'category': 'security',
        })
    elif cors_suggestions:
        results.append({
            'id': '3.5',
            'name': 'CORS/CSRF配置',
            'level': 'info',
            'message': f'CORS含通配符*但已有动态白名单校验，{len(cors_suggestions)} 项建议',
            'file': '',
            'line': 0,
            'snippet': '\n'.join(cors_suggestions),
            'fix': '建议持续维护CORS动态白名单校验逻辑',
            'category': 'security',
        })
    
    return results


# ===== 3.6 路径穿越检测 =====


# ===== 3.8 越权访问(IDOR)检测 =====
def check_3_8_idor(context) -> List[Dict]:
    """3.8 越权访问(IDOR)检测 - 检查是否存在越权访问风险

    v4.4 误报治理:
    - 跳过注释行
    - 跳过 Python docstring 内的示例（规则文档中的 SQL 示例不算）
    - 跳过规则文件 RULES 定义列表（自指）
    """
    results = []

    # skill/agent类型无用户系统和数据归属，跳过IDOR检测
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
    
    idor_errors = []
    idor_warnings = []
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        lines = content.split('\n')
        # v4.4: 预计算跳过范围（docstring / RULES列表）
        doc_ranges, rules_range = _prepare_py_skip_ranges(lines)
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            # v4.4: 跳过 docstring / RULES 列表内的行
            if _skip_line_py(i, lines, doc_ranges, rules_range):
                continue
            # Look for f-string SQL with WHERE and id but no owner check
            sql_match = re.search(r'f["\']\s*(SELECT|UPDATE|DELETE)\s+.*?WHERE\s+.*?id\s*=\s*\{', line, re.IGNORECASE)
            match_line = line
            if not sql_match:
                # Also check multi-line: f-string SQL start + WHERE in nearby lines
                if re.search(r'f["\']\s*(SELECT|UPDATE|DELETE)\s', line, re.IGNORECASE):
                    context_str = '\n'.join(lines[i-1:min(i+4, len(lines))])
                    if re.search(r'WHERE\s+.*?id\s*=\s*\{', context_str, re.IGNORECASE):
                        sql_match = True
                        match_line = context_str
            if not sql_match:
                continue
            has_safe = '# safe:' in lines[i-1] or (i >= 2 and '# safe:' in lines[i-2])
            if has_safe:
                continue
            # Check if owner validation exists in the same SQL
            has_owner = bool(re.search(r'user_id\s*=|tenant_id\s*=|owner\s*=|creator\s*=', match_line, re.IGNORECASE))
            if not has_owner:
                is_write = bool(re.search(r'f["\']\s*(UPDATE|DELETE)', match_line, re.IGNORECASE))
                if is_write:
                    idor_errors.append(f"{os.path.relpath(fpath)}:{i} 写操作仅按ID查询无归属校验")
                else:
                    idor_warnings.append(f"{os.path.relpath(fpath)}:{i} 查询仅按ID无归属校验")
    
    if idor_errors:
        results.append({
            'id': '3.8',
            'name': '越权访问(IDOR)检测',
            'level': 'error',
            'message': f'发现 {len(idor_errors)} 处越权风险（写操作仅按资源ID无归属校验）',
            'file': '',
            'line': 0,
            'snippet': '\n'.join(idor_errors[:10]),
            'fix': 'UPDATE/DELETE操作必须同时校验user_id/tenant_id归属',
            'category': 'security',
        })
    elif idor_warnings:
        results.append({
            'id': '3.8',
            'name': '越权访问(IDOR)检测',
            'level': 'warning',
            'message': f'发现 {len(idor_warnings)} 处潜在越权风险（查询仅按ID无归属校验）',
            'file': '',
            'line': 0,
            'snippet': '\n'.join(idor_warnings[:10]),
            'fix': '查询操作建议增加user_id/tenant_id条件隔离数据',
            'category': 'security',
        })
    
    return results


# ===== 3.9 速率限制检测 =====


# ===== 3.9 速率限制检测 =====
def check_3_9_rate_limit(context) -> List[Dict]:
    """3.9 速率限制检测 - 检查是否实现了速率限制"""
    results = []
    
    # skill/agent类型是CLI工具或本地脚本，不需要Web级速率限制
    if context.project_type in ("skill", "agent"):
        return results
    
    be_content = context.get_all_backend_content()
    if not be_content:
        return results
    
    has_rate_limit = bool(re.search(r'rate.?limit|throttle|limiter|RateLimit|频率限制|调用限制', be_content, re.IGNORECASE))
    
    # Check AI interfaces for rate limiting
    ai_keywords = re.findall(r'(chat|analysis|generate|completion|infer|ai_|llm_)', be_content, re.IGNORECASE)
    has_ai_rate_limit = False
    if ai_keywords:
        for keyword in set(ai_keywords[:10]):
            pattern = rf'{keyword}\w*'
            for m in re.finditer(pattern, be_content, re.IGNORECASE):
                ctx = be_content[max(0, m.start()-200):m.end()+200]
                if re.search(r'rate.?limit|throttle|limiter|频率|限制', ctx, re.IGNORECASE):
                    has_ai_rate_limit = True
                    break
            if has_ai_rate_limit:
                break
    
    if not has_rate_limit:
        results.append({
            'id': '3.9',
            'name': '速率限制检测',
            'level': 'error',
            'message': '后端未实现任何速率限制(rate limit/throttle)',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '实现API速率限制，至少对AI接口(chat/analysis)做per-user/per-IP频率控制',
            'category': 'security',
        })
    elif ai_keywords and not has_ai_rate_limit:
        results.append({
            'id': '3.9',
            'name': '速率限制检测',
            'level': 'warning',
            'message': f'已有速率限制，但检测到AI相关接口({len(set(kw.lower() for kw in ai_keywords))}个)未单独限流',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '对AI接口(chat/analysis/generate等)单独设置更严格的速率限制',
            'category': 'security',
        })
    
    return results


# ===== 3.10 JWT安全检测 =====


# ===== 3.10 JWT安全检测 =====
def check_3_10_jwt_security(context) -> List[Dict]:
    """3.10 JWT安全检测 - 检查JWT配置是否安全"""
    results = []

    # skill/agent类型无鉴权体系，跳过JWT检测
    if context.project_type in ("skill", "agent"):
        return results
    
    be_content = context.get_all_backend_content()
    if not be_content:
        return results
    
    has_jwt = bool(re.search(r'jwt|JWT|jsonwebtoken|pyjwt|_verify_token|encode.*token|decode.*token|flask_jwt|jwt_required|create_access_token', be_content, re.IGNORECASE))
    if not has_jwt:
        return results
    
    jwt_errors = []
    jwt_warnings = []
    
    # Check algorithm specification (prohibit 'none')
    has_algo_spec = bool(re.search(r'algorithms\s*=\s*\[|algorithm\s*=\s*["\']HS["\']|algorithms\s*=\s*\[?["\']HS|JWT_ALGORITHM|jwt_algorithm|ALGORITHM\s*=', be_content, re.IGNORECASE))
    has_none_algo = bool(re.search(r'algorithms\s*=\s*\[?["\']none["\']', be_content, re.IGNORECASE))
    if has_none_algo:
        jwt_errors.append("JWT算法包含none，允许绕过签名验证")
    elif not has_algo_spec and re.search(r'jwt\.decode\(', be_content):
        jwt_warnings.append("jwt.decode未显式指定algorithms参数")
    
    # Check expiration time
    has_exp = bool(re.search(r'\bexp\b|expire|expiry|expiration|过期|有效期', be_content, re.IGNORECASE))
    if not has_exp:
        jwt_errors.append("JWT未设置过期时间(exp claim)")
    else:
        exp_match = re.search(r'expir(?:e|ation|y)[^=]*=\s*(\d+)', be_content, re.IGNORECASE)
        if exp_match:
            try:
                exp_val = int(exp_match.group(1))
                ctx = be_content[max(0, exp_match.start()-50):exp_match.end()+50]
                if 'hour' in ctx.lower() and exp_val > 24:
                    jwt_warnings.append(f"JWT过期时间过长({exp_val}小时>24h)")
                elif exp_val > 86400 and 'second' in ctx.lower():
                    jwt_warnings.append(f"JWT过期时间过长({exp_val}秒>86400)")
            except ValueError:  # noqa: intentional empty handler
                pass
    
    # Check key source (should be from env, not hardcoded)
    jwt_key_patterns = re.finditer(r'(?:secret|key|jwt_secret|secret_key)\s*=\s*(["\'][^"\']{8,}["\'])', be_content, re.IGNORECASE)
    for m in jwt_key_patterns:
        line_start = be_content.rfind('\n', 0, m.start()) + 1
        line_end = be_content.find('\n', m.end())
        if line_end == -1:
            line_end = len(be_content)
        line = be_content[line_start:line_end]
        if line.strip().startswith('#'):
            continue
        ctx = be_content[max(0, m.start()-100):m.end()+50]
        if 'os.environ' not in ctx and 'os.getenv' not in ctx:
            jwt_errors.append(f"JWT密钥疑似硬编码: {m.group(1)[:15]}...")
    
    # Check for token refresh mechanism
    has_refresh = bool(re.search(r'refresh.?token|token.?refresh|renew.?token|刷新.?token|token.?续期', be_content, re.IGNORECASE))
    if not has_refresh:
        jwt_warnings.append("缺少token刷新机制")
    
    if jwt_errors:
        results.append({
            'id': '3.10',
            'name': 'JWT安全检测',
            'level': 'error',
            'message': f'发现 {len(jwt_errors)} 处JWT安全问题',
            'file': '',
            'line': 0,
            'snippet': '\n'.join(jwt_errors[:10]),
            'fix': '修复JWT配置：指定算法(禁止none)、设置过期时间、密钥从环境变量读取',
            'category': 'security',
        })
    elif jwt_warnings:
        results.append({
            'id': '3.10',
            'name': 'JWT安全检测',
            'level': 'warning',
            'message': f'发现 {len(jwt_warnings)} 处JWT安全建议',
            'file': '',
            'line': 0,
            'snippet': '\n'.join(jwt_warnings[:10]),
            'fix': '完善JWT配置：添加token刷新机制、控制过期时间',
            'category': 'security',
        })
    
    return results


# ===== 3.11 输入校验检测 =====


# ===== 规则定义列表 =====
RULES = [
    {
        'id': '3.4',
        'name': '鉴权绕过',
        'level': 'blocking',
        'category': 'security',
        'module_id': '3',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron'],
        'description': '检查是否存在鉴权绕过风险，如缺少auth_middleware',
        
        'check': check_3_4_auth_bypass,
    },
    {
        'id': '3.5',
        'name': 'CORS/CSRF配置',
        'level': 'problem',
        'category': 'security',
        'module_id': '3',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron'],
        'description': '检查CORS/CSRF配置是否安全，如是否使用通配符*',
        
        'check': check_3_5_cors_csrf,
    },
    {
        'id': '3.8',
        'name': '越权访问(IDOR)检测',
        'level': 'blocking',
        'category': 'security',
        'module_id': '3',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron'],
        'description': '检查是否存在越权访问风险，如写操作仅按ID无归属校验',
        
        'check': check_3_8_idor,
    },
    {
        'id': '3.9',
        'name': '速率限制检测',
        'level': 'blocking',
        'category': 'security',
        'module_id': '3',
        'applicable_types': ['miniprogram', 'web', 'python_backend', 'flask', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查是否实现了速率限制(rate limit/throttle)',
        
        'check': check_3_9_rate_limit,
    },
    {
        'id': '3.10',
        'name': 'JWT安全检测',
        'level': 'blocking',
        'category': 'security',
        'module_id': '3',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron'],
        'description': '检查JWT配置是否安全，如算法指定、过期时间、密钥来源等',
        
        'check': check_3_10_jwt_security,
    },
]
