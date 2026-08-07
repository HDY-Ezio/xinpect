"""
Agent/LLM应用安全规则集 - Skill代码安全 (M14)
LLM/Agent应用专项安全检查 - Skill代码执行安全类
包含: 可疑外连、敏感文件读取、内存文件保护、危险函数、Base64执行、root权限

来源标准: OWASP LLM Top 10 2025 / 虾评四维检测 / 扣子平台审核规范
"""

"""
Agent/LLM应用安全规则集 - Skill运行时安全 (M14)
LLM/Agent应用专项安全检查 - Skill运行时安全防护类
包含: 可疑外连、敏感文件读取、内存文件保护、危险函数、Base64执行、
      root权限、权限一致性、远程脚本执行、依赖漏洞、隐藏提示注入

来源标准: OWASP LLM Top 10 2025 / 虾评四维检测 / 扣子平台审核规范
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


def check_skill_sec_001_suspicious_outbound(context) -> List[Dict]:
    """SKILL-SEC-001 可疑外联请求检测 - 检查是否有向不明服务器发送数据的行为"""
    results = []
    
    all_py_files = context.find_files([".py"])
    if not all_py_files:
        return results
    
    # 可疑域名/IP模式
    suspicious_patterns = [
        # IP地址直连（非内网、非回环）
        (r'https?://(?!(127\.|10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.|0\.|localhost))\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}',
         'IP地址直连（非内网）'),
        # 可疑TLD
        (r'https?://[a-zA-Z0-9.-]+\.(xyz|top|club|online|site|fun|tk|ml|ga|cf|gq)/',
         '可疑顶级域名'),
        # base64编码的URL（可能用于隐藏真实地址）
        (r'base64\.b64decode.*url|url.*base64\.b64decode', 'Base64编码的URL'),
        # DNS隧道迹象
        (r'socket\.connect.*\w{30,}\.[a-zA-Z]', '可能的DNS隧道'),
    ]
    
    issues = []
    for fpath in all_py_files:
        if _is_skippable_file(fpath):
            continue
        content = context.safe_read(fpath)
        if not content:
            continue
        
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if _is_comment_line(line):
                continue
            
            for pattern, desc in suspicious_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    issues.append({
                        'file': fpath,
                        'line': i,
                        'desc': desc,
                        'snippet': line.strip()[:80],
                    })
                    break
    
    if issues:
        results.append({
            'id': 'SKILL-SEC-001',
            'name': '可疑外联请求检测',
            'level': 'error',
            'message': f'检测到 {len(issues)} 处可疑的外联请求',
            'detail': '示例: ' + '; '.join(f"{os.path.basename(i['file'])}:{i['line']} {i['desc']}" for i in issues[:5]),
            'file': issues[0]['file'],
            'line': issues[0]['line'],
            'snippet': issues[0]['snippet'],
            'fix': '确认所有外联请求的目标域名是否合法可信，避免向未知服务器发送数据',
            'category': 'llm_security',
        })
    
    return results


# ============================================================
# SKILL-SEC-002: 敏感文件读取检测
# ============================================================
def check_skill_sec_002_sensitive_file_read(context) -> List[Dict]:
    """SKILL-SEC-002 敏感文件读取检测 - 检查是否读取SSH配置、AWS凭证、浏览器Cookie等敏感文件"""
    results = []
    
    all_py_files = context.find_files([".py"])
    if not all_py_files:
        return results
    
    sensitive_file_patterns = [
        (r'~/.ssh/|\.ssh/id_rsa|\.ssh/id_ed25519', 'SSH私钥文件'),
        (r'~/.aws/credentials|\.aws/credentials', 'AWS凭证文件'),
        (r'~/.google|credentials\.json|service[_-]account.*\.json', 'Google Cloud凭证'),
        (r'Cookies|cookies\.sqlite|Local Storage', '浏览器Cookie'),
        (r'/etc/passwd|/etc/shadow', '系统用户文件'),
        (r'~/.bash_history|\.zsh_history', 'Shell历史记录'),
        (r'~/.gitconfig|\.git/config', 'Git配置（可能含token）'),
    ]
    
    issues = []
    for fpath in all_py_files:
        if _is_skippable_file(fpath):
            continue
        content = context.safe_read(fpath)
        if not content:
            continue
        
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if _is_comment_line(line):
                continue
            
            for pattern, desc in sensitive_file_patterns:
                if re.search(pattern, line):
                    # 检查是否为文件读取操作
                    if re.search(r'(open|read_file|path\.read_text|os\.path\.join).*' + pattern.split('|')[0].replace('\\', ''), 
                                line, re.IGNORECASE):
                        issues.append({
                            'file': fpath,
                            'line': i,
                            'desc': desc,
                            'snippet': line.strip()[:80],
                        })
                    elif 'open(' in line or 'read' in line.lower():
                        issues.append({
                            'file': fpath,
                            'line': i,
                            'desc': desc,
                            'snippet': line.strip()[:80],
                        })
                    break
    
    if issues:
        results.append({
            'id': 'SKILL-SEC-002',
            'name': '敏感文件读取检测',
            'level': 'error',
            'message': f'检测到 {len(issues)} 处敏感文件读取操作',
            'detail': '示例: ' + '; '.join(f"{os.path.basename(i['file'])}:{i['line']} {i['desc']}" for i in issues[:5]),
            'file': issues[0]['file'],
            'line': issues[0]['line'],
            'snippet': issues[0]['snippet'],
            'fix': '技能不得读取用户的SSH密钥、云凭证、浏览器Cookie等敏感系统文件',
            'category': 'llm_security',
        })
    
    return results


# ============================================================
# SKILL-SEC-003: Agent记忆文件读取防护
# ============================================================
def check_skill_sec_003_memory_file_protection(context) -> List[Dict]:
    """SKILL-SEC-003 Agent记忆文件读取防护 - 检查是否读取MEMORY.md、USER.md等Agent记忆文件"""
    results = []
    
    all_py_files = context.find_files([".py"])
    all_js_files = context.find_files([".js", ".ts"])
    all_files = all_py_files + all_js_files
    
    if not all_files:
        return results
    
    sensitive_memory_files = [
        'MEMORY.md', 'USER.md', 'SOUL.md', 'SECRET.md',
        'memory.json', 'user_profile.json',
        '.agent_memory', '.user_data',
    ]
    
    issues = []
    for fpath in all_files:
        if _is_skippable_file(fpath):
            continue
        content = context.safe_read(fpath)
        if not content:
            continue
        
        # 跳过技能自身的SKILL.md读取（正常功能）
        if 'SKILL.md' in content and len(content.split('\n')) < 100:
            # 简单文件可能就是读自身SKILL.md，跳过
            pass
        
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if _is_comment_line(line):
                continue
            
            for mem_file in sensitive_memory_files:
                if mem_file in line and ('open(' in line or 'read' in line.lower() or 'path' in line.lower()):
                    issues.append({
                        'file': fpath,
                        'line': i,
                        'desc': f'读取Agent记忆文件: {mem_file}',
                        'snippet': line.strip()[:80],
                    })
                    break
    
    if issues:
        results.append({
            'id': 'SKILL-SEC-003',
            'name': 'Agent记忆文件读取防护',
            'level': 'error',
            'message': f'检测到 {len(issues)} 处可能读取Agent记忆/身份文件',
            'detail': '示例: ' + '; '.join(f"{os.path.basename(i['file'])}:{i['line']}" for i in issues[:5]),
            'file': issues[0]['file'],
            'line': issues[0]['line'],
            'snippet': issues[0]['snippet'],
            'fix': '技能不得读取Agent的MEMORY.md、USER.md等记忆和身份文件，防止数据外泄',
            'category': 'llm_security',
        })
    
    return results


# ============================================================
# SKILL-SEC-004: 危险函数调用检测（eval/exec/os.system）
# ============================================================
def check_skill_sec_004_dangerous_functions(context) -> List[Dict]:
    """SKILL-SEC-004 危险函数调用检测 - 检测eval/exec/os.system等危险函数用于执行外部输入"""
    results = []
    
    all_py_files = context.find_files([".py"])
    if not all_py_files:
        return results
    
    dangerous_funcs = {
        'eval(': 'eval()动态执行代码',
        'exec(': 'exec()动态执行代码',
        'os.system(': 'os.system()执行系统命令',
        'subprocess.call(': 'subprocess.call()执行命令',
        'subprocess.run(': 'subprocess.run()执行命令',
        'subprocess.Popen(': 'subprocess.Popen()执行命令',
        'os.popen(': 'os.popen()执行命令',
        '__import__(': '动态导入（可能用于绕过检测）',
    }
    
    issues = []
    for fpath in all_py_files:
        if _is_skippable_file(fpath):
            continue
        content = context.safe_read(fpath)
        if not content:
            continue
        
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if _is_comment_line(line):
                continue
            
            prev_line = lines[i-2] if i >= 2 else ''
            if _has_safe_comment(line, prev_line):
                continue
            
            for func, desc in dangerous_funcs.items():
                if func in line:
                    # 检查参数是否包含变量（可能来自用户输入）
                    after_func = line.split(func, 1)[1] if func in line else ''
                    has_variable = bool(re.match(r'\s*[a-zA-Z_]', after_func))
                    
                    if has_variable:
                        issues.append({
                            'file': fpath,
                            'line': i,
                            'desc': f'{desc}（参数为变量）',
                            'snippet': line.strip()[:80],
                        })
                    else:
                        # 常量参数也是危险的，但降为warning
                        issues.append({
                            'file': fpath,
                            'line': i,
                            'desc': f'{desc}（参数为常量）',
                            'snippet': line.strip()[:80],
                        })
                    break
    
    if issues:
        # 区分error和warning级别
        var_issues = [i for i in issues if '变量' in i['desc']]
        const_issues = [i for i in issues if '常量' in i['desc']]
        
        if var_issues:
            results.append({
                'id': 'SKILL-SEC-004',
                'name': '危险函数调用检测',
                'level': 'error',
                'message': f'检测到 {len(var_issues)} 处危险函数使用变量参数执行代码',
                'detail': '示例: ' + '; '.join(f"{os.path.basename(i['file'])}:{i['line']}" for i in var_issues[:5]),
                'file': var_issues[0]['file'],
                'line': var_issues[0]['line'],
                'snippet': var_issues[0]['snippet'],
                'fix': '禁止使用eval/exec执行动态代码；系统命令使用白名单方式严格限制可执行命令',
                'category': 'llm_security',
            })
        elif const_issues:
            results.append({
                'id': 'SKILL-SEC-004',
                'name': '危险函数调用检测',
                'level': 'warning',
                'message': f'检测到 {len(const_issues)} 处危险函数调用（参数为常量）',
                'detail': '示例: ' + '; '.join(f"{os.path.basename(i['file'])}:{i['line']}" for i in const_issues[:5]),
                'file': const_issues[0]['file'],
                'line': const_issues[0]['line'],
                'snippet': const_issues[0]['snippet'],
                'fix': '避免使用eval/exec/os.system等危险函数，考虑用更安全的API替代',
                'category': 'llm_security',
            })
    
    return results


# ============================================================
# SKILL-SEC-005: Base64解码后执行检测
# ============================================================
def check_skill_sec_005_base64_exec(context) -> List[Dict]:
    """SKILL-SEC-005 Base64解码后执行检测 - 检测base64解码后立即执行代码的混淆逃逸模式"""
    results = []
    
    all_py_files = context.find_files([".py"])
    if not all_py_files:
        return results
    
    # 检测base64解码后传给执行函数的模式
    suspicious_patterns = [
        (r'(eval|exec|compile)\s*\(.*base64', 'base64解码后eval/exec执行'),
        (r'base64.*decode.*\)\s*\)\s*\)\s*(eval|exec)', 'base64解码传入执行函数'),
        (r'b64decode.*\)\.decode.*\)\s*\)\s*exec|b64decode.*exec', 'base64解码后执行'),
        (r'__import__\(.base64.\).*decode.*eval', '动态导入base64后执行'),
    ]
    
    issues = []
    for fpath in all_py_files:
        if _is_skippable_file(fpath):
            continue
        content = context.safe_read(fpath)
        if not content:
            continue
        
        # 检查单行模式
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if _is_comment_line(line):
                continue
            
            for pattern, desc in suspicious_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    issues.append({
                        'file': fpath,
                        'line': i,
                        'desc': desc,
                        'snippet': line.strip()[:80],
                    })
                    break
        
        # 检查跨行模式（base64解码变量 + 后续eval）
        if 'base64' in content.lower() and ('eval(' in content or 'exec(' in content):
            # 简单的跨行检测
            b64_vars = re.findall(r'(\w+)\s*=\s*.*base64.*decode', content, re.IGNORECASE)
            for var in b64_vars:
                if re.search(rf'(eval|exec)\s*\(\s*{var}', content):
                    # 找行号
                    for i, line in enumerate(lines, 1):
                        if re.search(rf'(eval|exec)\s*\(\s*{var}', line):
                            issues.append({
                                'file': fpath,
                                'line': i,
                                'desc': f'变量{var}经base64解码后执行',
                                'snippet': line.strip()[:80],
                            })
                            break
    
    if issues:
        results.append({
            'id': 'SKILL-SEC-005',
            'name': 'Base64解码后执行检测',
            'level': 'error',
            'message': f'检测到 {len(issues)} 处Base64解码后执行代码的可疑模式',
            'detail': '示例: ' + '; '.join(f"{os.path.basename(i['file'])}:{i['line']} {i['desc']}" for i in issues[:5]),
            'file': issues[0]['file'],
            'line': issues[0]['line'],
            'snippet': issues[0]['snippet'],
            'fix': '禁止使用base64编码隐藏代码逻辑，这是典型的恶意代码混淆逃逸手段',
            'category': 'llm_security',
        })
    
    return results


# ============================================================
# SKILL-SEC-006: Root/Sudo权限请求检测
# ============================================================
def check_skill_sec_006_root_permission(context) -> List[Dict]:
    """SKILL-SEC-006 Root/Sudo权限请求检测 - 检查是否请求sudo/root或管理员权限"""
    results = []
    
    all_py_files = context.find_files([".py"])
    if not all_py_files:
        return results
    
    root_patterns = [
        (r'sudo\s+', 'sudo命令提权'),
        (r'os\.setuid\(0\)|os\.seteuid\(0\)', '设置UID为0(root)'),
        (r'runas.*admin|runas.*administrator', '以管理员身份运行'),
        (r'elevated.*privilege|admin.*right', '请求管理员权限'),
        (r'setuid|setgid', '设置UID/GID'),
    ]
    
    issues = []
    for fpath in all_py_files:
        if _is_skippable_file(fpath):
            continue
        content = context.safe_read(fpath)
        if not content:
            continue
        
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if _is_comment_line(line):
                continue
            
            for pattern, desc in root_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    # 在字符串中的sudo可能是合法描述，检查是否在代码执行路径
                    issues.append({
                        'file': fpath,
                        'line': i,
                        'desc': desc,
                        'snippet': line.strip()[:80],
                    })
                    break
    
    if issues:
        results.append({
            'id': 'SKILL-SEC-006',
            'name': 'Root/Sudo权限请求检测',
            'level': 'error',
            'message': f'检测到 {len(issues)} 处可能请求root/管理员权限',
            'detail': '示例: ' + '; '.join(f"{os.path.basename(i['file'])}:{i['line']} {i['desc']}" for i in issues[:5]),
            'file': issues[0]['file'],
            'line': issues[0]['line'],
            'snippet': issues[0]['snippet'],
            'fix': '技能/Agent不得以任何方式请求root或管理员权限，应在普通用户权限下运行',
            'category': 'llm_security',
        })
    
    return results


# ============================================================
# SKILL-SEC-007: 权限声明与实际使用一致性
# ============================================================


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'SKILL-SEC-001',
        'name': '可疑外联请求检测',
        'level': 'blocking',
        'category': 'llm_security',
        'module_id': '14',
        'applicable_types': ['skill', 'agent'],
        'description': '检测是否向不明服务器发送数据（数据外泄维度）',
        'check': check_skill_sec_001_suspicious_outbound,
    },
    {
        'id': 'SKILL-SEC-002',
        'name': '敏感文件读取检测',
        'level': 'blocking',
        'category': 'llm_security',
        'module_id': '14',
        'applicable_types': ['skill', 'agent'],
        'description': '检测是否读取SSH配置、AWS凭证、浏览器Cookie等敏感文件（数据外泄维度）',
        'check': check_skill_sec_002_sensitive_file_read,
    },
    {
        'id': 'SKILL-SEC-003',
        'name': 'Agent记忆文件读取防护',
        'level': 'blocking',
        'category': 'llm_security',
        'module_id': '14',
        'applicable_types': ['skill'],
        'description': '检测是否读取MEMORY.md、USER.md等Agent记忆/身份文件（数据外泄维度）',
        'check': check_skill_sec_003_memory_file_protection,
    },
    {
        'id': 'SKILL-SEC-004',
        'name': '危险函数调用检测',
        'level': 'blocking',
        'category': 'llm_security',
        'module_id': '14',
        'applicable_types': ['skill', 'agent', 'python', 'python_backend', 'python_tool'],
        'description': '检测eval/exec/os.system等危险函数执行外部输入（权限提升维度）',
        'check': check_skill_sec_004_dangerous_functions,
    },
    {
        'id': 'SKILL-SEC-005',
        'name': 'Base64解码后执行检测',
        'level': 'blocking',
        'category': 'llm_security',
        'module_id': '14',
        'applicable_types': ['skill', 'agent', 'python', 'python_backend', 'python_tool'],
        'description': '检测base64解码后立即执行代码的混淆逃逸模式（供应链维度）',
        'check': check_skill_sec_005_base64_exec,
    },
    {
        'id': 'SKILL-SEC-006',
        'name': 'Root/Sudo权限请求检测',
        'level': 'blocking',
        'category': 'llm_security',
        'module_id': '14',
        'applicable_types': ['skill', 'agent'],
        'description': '检测是否请求sudo/root或管理员权限（权限提升维度）',
        'check': check_skill_sec_006_root_permission,
    },
]
