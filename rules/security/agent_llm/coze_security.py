"""
Agent/LLM应用安全规则集 - 扣子平台安全 (M14)
LLM/Agent应用专项安全检查 - 扣子(Coze)平台专属安全类
包含: 代码中PII泄露、凭证作用域、凭证域名、API密钥作凭证

来源标准: 扣子平台审核规范
"""

"""
Agent/LLM应用安全规则集 (M14)
LLM/Agent应用专项安全检查
包含: 提示词安全、工具权限、数据外泄、供应链安全、输出验证等23条P0规则
来源标准: OWASP LLM Top 10 2025 / 虾评四维检测 / 扣子平台审核规范 / OpenAI插件安全
"""

import re
import os
import json
from typing import List, Dict, Any


# ============================================================
# 辅助函数
# ============================================================


# ============================================================
# 辅助函数
# ============================================================
def _get_line_number(content: str, match_start: int) -> int:
    """获取匹配位置的行号"""
    return content[:match_start].count('\n') + 1


def _is_skippable_file(filepath: str) -> bool:
    """判断是否为可跳过的文件（测试、示例、配置示例等）"""
    basename = os.path.basename(filepath).lower()
    skip_patterns = ['test', 'spec', 'example', 'sample', 'demo', 'mock', 'fixture', '.example']
    return any(p in basename for p in skip_patterns)


def _is_comment_line(line: str) -> bool:
    """判断是否为注释行"""
    stripped = line.strip()
    return stripped.startswith(('#', '//', '/*', '*', '<!--'))


def _has_safe_comment(line: str, prev_line: str = '') -> bool:
    """检查是否有安全标记注释"""
    return '# safe:' in line or '# safe:' in prev_line or '// safe:' in line


# ============================================================


def check_coze_001_pii_in_code(context) -> List[Dict]:
    """COZE-001 技能代码中真实个人信息检测 - 检查代码中是否包含真实手机号、身份证号等PII"""
    results = []
    
    all_files = context.find_files([".py", ".js", ".ts", ".md", ".json", ".txt"])
    
    # PII检测模式
    pii_patterns = [
        (r'1[3-9]\d{9}', '手机号', lambda m: _is_likely_real_phone(m.group(0))),
        (r'[1-9]\d{5}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]', '身份证号', None),
        (r'(微信号|wechat|wx)\s*[:：]\s*[a-zA-Z][a-zA-Z0-9_-]{5,}', '微信号', None),
    ]
    
    def _is_likely_real_phone(phone: str) -> bool:
        """判断是否为真实手机号（排除测试号段）"""
        # 排除常见测试号段
        test_prefixes = ['1380000', '1390000', '1500000', '1888888', '1300000', '1311111']
        return not any(phone.startswith(p) for p in test_prefixes)
    
    issues = []
    for fpath in all_files:
        if _is_skippable_file(fpath):
            continue
        
        content = context.safe_read(fpath)
        if not content:
            continue
        
        # 跳过配置示例和文档示例
        basename = os.path.basename(fpath).lower()
        if 'readme' in basename or 'changelog' in basename:
            continue
        
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if _is_comment_line(line):
                # 注释中的PII也需要关注，但降为提示
                pass
            
            for pattern, desc, validator in pii_patterns:
                matches = list(re.finditer(pattern, line))
                for m in matches:
                    if validator and not validator(m):
                        continue
                    
                    # 排除占位符
                    match_text = m.group(0)
                    if any(x in match_text for x in ['000000', '111111', 'xxxx', 'XXXX']):
                        continue
                    if '测试' in line and len(line) < 50:
                        continue
                    
                    issues.append({
                        'file': fpath,
                        'line': i,
                        'desc': desc,
                        'snippet': line.strip()[:60],
                    })
                    break  # 每行每种类型只报一次
    
    if issues:
        results.append({
            'id': 'COZE-001',
            'name': '技能代码中真实个人信息检测',
            'level': 'error',
            'message': f'检测到 {len(issues)} 处可能包含真实个人信息',
            'detail': '示例: ' + '; '.join(f"{os.path.basename(i['file'])}:{i['line']} {i['desc']}" for i in issues[:5]),
            'file': issues[0]['file'],
            'line': issues[0]['line'],
            'snippet': issues[0]['snippet'],
            'fix': '移除代码中的真实个人信息，使用占位符或测试数据替代示例中的PII',
            'category': 'llm_security',
        })
    
    return results


# ============================================================
# COZE-002: 凭证变量最小授权检测
# ============================================================
def check_coze_002_credential_scope(context) -> List[Dict]:
    """COZE-002 凭证变量最小授权检测 - 检查凭证权限范围与功能是否匹配"""
    results = []
    
    # 检查SKILL.md中的权限声明与实际使用
    skill_md = ''
    all_md = context.find_files([".md"])
    for f in all_md:
        if os.path.basename(f).lower() == 'skill.md':
            skill_md = context.safe_read(f)
            break
    
    if not skill_md:
        return results
    
    # 检测凭证变量声明
    credential_pattern = re.compile(r'[#=]*\s*(凭证|credential|密钥|API Key).*?\n([\s\S]*?)(?=\n#|\Z)', re.IGNORECASE)
    cred_match = credential_pattern.search(skill_md)
    
    if not cred_match:
        # 没有声明凭证，检查是否实际使用了凭证
        all_py = context.find_files([".py"])
        uses_credential = False
        for f in all_py:
            content = context.safe_read(f)
            if re.search(r'(get_credential|credential|secret_var|api_key).*get', content, re.IGNORECASE):
                uses_credential = True
                break
        
        if uses_credential:
            results.append({
                'id': 'COZE-002',
                'name': '凭证变量最小授权检测',
                'level': 'warning',
                'message': '检测到代码使用了凭证但SKILL.md中未声明凭证权限',
                'file': '',
                'line': 0,
                'fix': '在SKILL.md中明确声明所需凭证及其权限范围，遵循最小授权原则',
                'category': 'llm_security',
            })
    
    return results


# ============================================================
# COZE-003: 凭证域名与请求域名一致性
# ============================================================
def check_coze_003_credential_domain(context) -> List[Dict]:
    """COZE-003 凭证域名与请求域名一致性 - 检查凭证关联域名与代码中实际请求域名是否一致"""
    results = []
    
    # 从SKILL.md提取凭证域名
    skill_md = ''
    all_md = context.find_files([".md"])
    for f in all_md:
        if os.path.basename(f).lower() == 'skill.md':
            skill_md = context.safe_read(f)
            break
    
    if not skill_md:
        return results
    
    # 提取文档中声明的域名白名单
    declared_domains = set()
    domain_patterns = [
        r'(域名|domain|host|endpoint|白名单)[^：:\n]*[:：]\s*([^\n,，]+)',
        r'https?://([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
    ]
    for pattern in domain_patterns:
        for m in re.finditer(pattern, skill_md, re.IGNORECASE):
            domain = m.group(1)
            if '.' in domain and len(domain) > 4:
                declared_domains.add(domain.lower().strip())
    
    # 提取代码中实际请求的域名
    all_py = context.find_files([".py"])
    actual_domains = set()
    for f in all_py:
        content = context.safe_read(f)
        # 匹配requests/urllib等的URL
        urls = re.findall(r'(?:requests\.(?:get|post|put|delete)|urlopen)\s*\(\s*["\']https?://([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', content)
        for domain in urls:
            actual_domains.add(domain.lower())
    
    if declared_domains and actual_domains:
        mismatched = actual_domains - declared_domains
        # 做模糊匹配（子域名可能合法）
        truly_mismatched = []
        for ad in mismatched:
            is_subdomain = any(dd in ad or ad.endswith('.' + dd) for dd in declared_domains)
            if not is_subdomain:
                truly_mismatched.append(ad)
        
        if truly_mismatched:
            results.append({
                'id': 'COZE-003',
                'name': '凭证域名与请求域名一致性',
                'level': 'warning',
                'message': f'检测到 {len(truly_mismatched)} 个未在文档声明的请求域名',
                'detail': '未声明域名: ' + ', '.join(truly_mismatched[:5]) + 
                         f'\n声明域名: {", ".join(sorted(declared_domains)[:5])}',
                'file': '',
                'line': 0,
                'fix': '确保代码中所有外部请求的域名都在凭证配置的白名单内，及时更新文档声明',
                'category': 'llm_security',
            })
    
    return results


# ============================================================
# COZE-005: API Key必须设为凭证变量
# ============================================================
def check_coze_005_api_key_as_credential(context) -> List[Dict]:
    """COZE-005 API Key必须设为凭证变量 - 检查敏感变量是否被正确归类为凭证"""
    results = []
    
    # 检查.env或配置文件中的敏感变量
    env_files = context.find_files([".env", ".env.local"])
    config_files = context.find_files([".json", ".yaml", ".yml"])
    
    sensitive_env_vars = []
    
    for fpath in env_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if _is_comment_line(line):
                continue
            
            # 检测看起来像密钥的环境变量
            if re.search(r'(API[_-]?KEY|SECRET|TOKEN|PASSWORD|PRIVATE[_-]?KEY)\s*=\s*.+', line, re.IGNORECASE):
                value = line.split('=', 1)[1].strip() if '=' in line else ''
                if value and value not in ('', '""', "''") and not value.startswith('${'):
                    # 检查是否为合理长度的密钥
                    if len(value) >= 16:
                        sensitive_env_vars.append({
                            'file': fpath,
                            'line': i,
                            'snippet': line.strip()[:60],
                        })
    
    if sensitive_env_vars:
        results.append({
            'id': 'COZE-005',
            'name': 'API Key必须设为凭证变量',
            'level': 'error',
            'message': f'检测到 {len(sensitive_env_vars)} 个敏感变量存储在普通环境变量中',
            'detail': '示例: ' + '; '.join(f"{os.path.basename(i['file'])}:{i['line']}" for i in sensitive_env_vars[:5]),
            'file': sensitive_env_vars[0]['file'],
            'line': sensitive_env_vars[0]['line'],
            'snippet': sensitive_env_vars[0]['snippet'],
            'fix': '将API Key等敏感变量设为凭证变量（加密存储），不要作为普通环境变量暴露',
            'category': 'llm_security',
        })
    
    return results


# ============================================================
# SKILL-SEC-001: 可疑外联请求检测
# ============================================================


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'COZE-001',
        'name': '技能代码中真实个人信息检测',
        'level': 'blocking',
        'category': 'llm_security',
        'module_id': '14',
        'applicable_types': ['skill', 'agent'],
        'description': '检查代码/示例中是否包含真实手机号、身份证号、微信号等PII',
        'check': check_coze_001_pii_in_code,
    },
    {
        'id': 'COZE-002',
        'name': '凭证变量最小授权检测',
        'level': 'blocking',
        'category': 'llm_security',
        'module_id': '14',
        'applicable_types': ['skill'],
        'description': '检查凭证权限范围与功能是否匹配，是否遵循最小授权原则',
        'check': check_coze_002_credential_scope,
    },
    {
        'id': 'COZE-003',
        'name': '凭证域名与请求域名一致性',
        'level': 'blocking',
        'category': 'llm_security',
        'module_id': '14',
        'applicable_types': ['skill'],
        'description': '检查凭证关联域名与代码中实际请求域名是否一致',
        'check': check_coze_003_credential_domain,
    },
    {
        'id': 'COZE-005',
        'name': 'API Key必须设为凭证变量',
        'level': 'blocking',
        'category': 'llm_security',
        'module_id': '14',
        'applicable_types': ['skill', 'agent'],
        'description': 'API Key等敏感变量必须设为凭证变量，不得作为普通环境变量',
        'check': check_coze_005_api_key_as_credential,
    },
]
