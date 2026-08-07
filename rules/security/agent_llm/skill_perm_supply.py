"""
Agent/LLM应用安全规则集 - Skill权限与供应链安全 (M14)
LLM/Agent应用专项安全检查 - Skill权限与供应链类
包含: 权限一致性、远程脚本执行、依赖漏洞、隐藏提示注入

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


def check_skill_sec_007_permission_consistency(context) -> List[Dict]:
    """SKILL-SEC-007 权限声明与实际使用一致性 - 检查技能描述中声明的权限与代码实际使用是否一致"""
    results = []
    
    # 从SKILL.md提取声明的权限
    skill_md = ''
    all_md = context.find_files([".md"])
    for f in all_md:
        if os.path.basename(f).lower() == 'skill.md':
            skill_md = context.safe_read(f)
            break
    
    if not skill_md:
        return results
    
    # 检测代码中实际使用的权限
    all_py = context.find_files([".py"])
    actual_permissions = set()
    
    permission_checks = {
        'network': [r'requests\.|urllib\.|httpx\.|aiohttp', '网络请求权限'],
        'file_write': [r'open\s*\([^)]*["\']w|with open.*w', '文件写入权限'],
        'file_read': [r'open\s*\(.*read|\.read\(\)', '文件读取权限'],
        'shell': [r'os\.system|subprocess\.|eval\(|exec\(', '代码/命令执行权限'],
        'environment': [r'os\.environ|os\.getenv|os\.putenv', '环境变量访问权限'],
    }
    
    for f in all_py:
        content = context.safe_read(f)
        for perm, (pattern, desc) in permission_checks.items():
            if re.search(pattern, content):
                actual_permissions.add(perm)
    
    # 检查文档中是否声明了这些权限
    declared_permissions = set()
    for perm, (pattern, desc) in permission_checks.items():
        if re.search(desc, skill_md):
            declared_permissions.add(perm)
    
    # 未声明但实际使用的权限
    undeclared = actual_permissions - declared_permissions
    
    if undeclared:
        undeclared_names = [permission_checks[p][1] for p in undeclared]
        results.append({
            'id': 'SKILL-SEC-007',
            'name': '权限声明与实际使用一致性',
            'level': 'warning',
            'message': f'检测到 {len(undeclared)} 项代码实际使用但未在文档声明的权限',
            'detail': '未声明权限: ' + ', '.join(undeclared_names),
            'file': '',
            'line': 0,
            'fix': '在SKILL.md中如实声明技能使用的所有权限，遵循最小权限原则',
            'category': 'llm_security',
        })
    
    return results


# ============================================================
# SKILL-SEC-008: 远程拉取脚本并执行检测
# ============================================================
def check_skill_sec_008_remote_script_exec(context) -> List[Dict]:
    """SKILL-SEC-008 远程拉取脚本并执行检测 - 检测从远程URL下载脚本并执行的供应链投毒风险"""
    results = []
    
    all_py_files = context.find_files([".py"])
    if not all_py_files:
        return results
    
    # 远程下载 + 执行的模式
    dangerous_chains = [
        # requests下载后执行
        (r'requests\.get\(.*\)\.text.*\)\)\s*(eval|exec)', 'HTTP请求内容直接执行'),
        (r'response\.text.*\)\s*(eval|exec)', 'HTTP响应直接执行'),
        # urllib下载后执行
        (r'urlopen.*read.*decode.*\)\s*(eval|exec)', 'URL读取内容直接执行'),
        # 动态导入远程模块
        (r'importlib.*import.*url|__import__.*http', '动态导入远程模块'),
        # pip install从git+https
        (r'pip.*install.*git\+https.*', '从远程Git安装（可能投毒）'),
        # exec + 远程内容
        (r'exec\s*\(.*requests|exec\s*\(.*urlopen', 'exec执行远程内容'),
    ]
    
    issues = []
    for fpath in all_py_files:
        if _is_skippable_file(fpath):
            continue
        content = context.safe_read(fpath)
        if not content:
            continue
        
        lines = content.split('\n')
        
        # 检查单行
        for i, line in enumerate(lines, 1):
            if _is_comment_line(line):
                continue
            
            for pattern, desc in dangerous_chains:
                if re.search(pattern, line, re.IGNORECASE):
                    issues.append({
                        'file': fpath,
                        'line': i,
                        'desc': desc,
                        'snippet': line.strip()[:80],
                    })
                    break
        
        # 检查跨行：先下载到变量，再执行
        download_vars = re.findall(r'(\w+)\s*=\s*.*(?:requests\.get|urlopen|urlretrieve)', content)
        for var in download_vars:
            exec_match = re.search(rf'(eval|exec)\s*\(\s*{var}', content)
            if exec_match:
                line_num = content[:exec_match.start()].count('\n') + 1
                issues.append({
                    'file': fpath,
                    'line': line_num,
                    'desc': f'远程下载内容({var})后执行',
                    'snippet': lines[line_num-1].strip()[:80] if line_num <= len(lines) else '',
                })
    
    if issues:
        results.append({
            'id': 'SKILL-SEC-008',
            'name': '远程拉取脚本并执行检测',
            'level': 'error',
            'message': f'检测到 {len(issues)} 处从远程拉取代码并执行的高危模式',
            'detail': '示例: ' + '; '.join(f"{os.path.basename(i['file'])}:{i['line']} {i['desc']}" for i in issues[:5]),
            'file': issues[0]['file'],
            'line': issues[0]['line'],
            'snippet': issues[0]['snippet'],
            'fix': '禁止从远程URL拉取代码并执行，依赖应通过requirements.txt明确声明版本',
            'category': 'llm_security',
        })
    
    return results


# ============================================================
# SKILL-SEC-010: 依赖包已知漏洞检测（简化版）
# ============================================================
def check_skill_sec_010_dependency_vuln(context) -> List[Dict]:
    """SKILL-SEC-010 依赖包已知漏洞检测 - 检查依赖包是否存在已知高危漏洞（基于已知风险包名）"""
    results = []
    
    # 检查requirements.txt（使用find_files避免重复os.walk）
    req_names = {'requirements.txt', 'requirements-dev.txt', 'setup.py', 'pyproject.toml'}
    candidates = context.find_files([".txt", ".py", ".toml"])
    req_files = [f for f in candidates if os.path.basename(f) in req_names]
    
    if not req_files:
        return results
    
    # 已知有重大历史漏洞的包（简化列表，实际应接入SCA数据库）
    known_risky_packages = {
        'requests<2.31.0': '存在代理授权绕过漏洞(CVE-2023-32681)',
        'urllib3<1.26.18': '存在CRLF注入漏洞',
        'pyyaml<5.4': '存在反序列化漏洞',
        'jinja2<2.11.3': '存在XSS漏洞',
        'flask<2.3.2': '存在安全修复版本',
        'django<3.2.20': '存在多个安全漏洞',
        'cryptography<41.0.0': '存在OpenSSL漏洞',
        'paramiko<3.0.0': '存在SSH安全漏洞',
    }
    
    issues = []
    for fpath in req_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            # 解析包名和版本
            pkg_match = re.match(r'^([a-zA-Z0-9_-]+)\s*([<>=!~]+.*)', line)
            if not pkg_match:
                continue
            
            pkg_name = pkg_match.group(1).lower()
            version_spec = pkg_match.group(2)
            
            # 简单检测：检查是否为已知高风险包且版本过低
            for risky_pkg, desc in known_risky_packages.items():
                risky_name = risky_pkg.split('<')[0].lower()
                if pkg_name == risky_name:
                    # 简化：只要包名匹配且有版本号，就提示检查
                    issues.append({
                        'file': fpath,
                        'line': i,
                        'desc': f'{pkg_name}: {desc}',
                        'snippet': line.strip()[:80],
                    })
                    break
    
    if issues:
        results.append({
            'id': 'SKILL-SEC-010',
            'name': '依赖包已知漏洞检测',
            'level': 'warning',
            'message': f'检测到 {len(issues)} 个可能存在已知漏洞的依赖包',
            'detail': '示例: ' + '; '.join(f"{os.path.basename(i['file'])}:{i['line']}" for i in issues[:5]),
            'file': issues[0]['file'],
            'line': issues[0]['line'],
            'snippet': issues[0]['snippet'],
            'fix': '升级依赖到安全版本，建议接入SCA工具（如pip-audit、safety）持续检测',
            'category': 'llm_security',
        })
    
    return results


# ============================================================
# SKILL-SEC-011: Prompt文档隐藏注入指令检测
# ============================================================
def check_skill_sec_011_hidden_prompt_injection(context) -> List[Dict]:
    """SKILL-SEC-011 Prompt文档隐藏注入指令检测 - 检查提示词中是否有微字体/同色文字/注释等隐藏指令"""
    results = []
    
    # 检查.md和.txt格式的提示词文件
    prompt_files = []
    all_files = context.find_files([".md", ".txt"])
    
    for fpath in all_files:
        basename = os.path.basename(fpath).lower()
        if any(k in basename for k in ['prompt', 'system', 'instruction', '角色', '提示']):
            prompt_files.append(fpath)
    
    # 也检查SKILL.md
    for f in all_files:
        if os.path.basename(f).lower() == 'skill.md':
            prompt_files.append(f)
    
    suspicious_patterns = [
        # HTML注释中隐藏指令
        (r'<!--\s*(ignore|disregard|forget|override|bypass|绕过|忽略|无视|忘记).*?-->',
         'HTML注释中隐藏绕过指令', re.IGNORECASE | re.DOTALL),
        # 零宽字符
        (r'[\u200b-\u200f\u202a-\u202e\ufeff]',
         '零宽字符（可能用于隐藏文本）', 0),
        # 小字/隐藏文字的CSS/HTML
        (r'(font-size\s*:\s*[01](?:px|pt)|color\s*:\s*(white|transparent|#fff|#ffffff).*background.*white|display\s*:\s*none).*指令',
         '隐藏样式文字', re.IGNORECASE),
        # Markdown注释中隐藏的指令
        (r'^\[//\]:\s*#\s*\(.*(ignore|disregard|forget|bypass|忽略|绕过).*\)',
         'Markdown注释中隐藏指令', re.IGNORECASE | re.MULTILINE),
    ]
    
    issues = []
    for fpath in prompt_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        for item in suspicious_patterns:
            pattern = item[0]
            desc = item[1]
            flags = item[2] if len(item) > 2 else 0
            
            matches = list(re.finditer(pattern, content, flags))
            for m in matches[:5]:  # 每个文件每个模式最多5条
                line_num = content[:m.start()].count('\n') + 1
                snippet = m.group(0)[:60].replace('\n', ' ')
                issues.append({
                    'file': fpath,
                    'line': line_num,
                    'desc': desc,
                    'snippet': snippet,
                })
    
    if issues:
        results.append({
            'id': 'SKILL-SEC-011',
            'name': 'Prompt文档隐藏注入指令检测',
            'level': 'error',
            'message': f'检测到 {len(issues)} 处提示词文档中可能包含隐藏注入指令',
            'detail': '示例: ' + '; '.join(f"{os.path.basename(i['file'])}:{i['line']} {i['desc']}" for i in issues[:5]),
            'file': issues[0]['file'],
            'line': issues[0]['line'],
            'snippet': issues[0]['snippet'],
            'fix': '检查提示词文档中是否有通过零宽字符、隐藏注释、同色文字等方式嵌入的恶意指令',
            'category': 'llm_security',
        })
    
    return results


# ============================================================
# OAI-SEC-001: 插件通信HTTPS强制
# ============================================================


# ===== 规则定义列表 =====


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'SKILL-SEC-007',
        'name': '权限声明与实际使用一致性',
        'level': 'blocking',
        'category': 'llm_security',
        'module_id': '14',
        'applicable_types': ['skill'],
        'description': '检查技能描述中声明的权限与代码实际使用是否一致（最小权限原则）',
        'check': check_skill_sec_007_permission_consistency,
    },
    {
        'id': 'SKILL-SEC-008',
        'name': '远程拉取脚本并执行检测',
        'level': 'blocking',
        'category': 'llm_security',
        'module_id': '14',
        'applicable_types': ['skill', 'agent', 'python', 'python_backend', 'python_tool'],
        'description': '检测从远程URL下载脚本并执行的供应链投毒风险（供应链维度）',
        'check': check_skill_sec_008_remote_script_exec,
    },
    {
        'id': 'SKILL-SEC-010',
        'name': '依赖包已知漏洞检测',
        'level': 'problem',
        'category': 'llm_security',
        'module_id': '14',
        'applicable_types': ['skill', 'agent', 'python', 'python_backend', 'python_tool', 'flask'],
        'description': '检查依赖包是否存在已知高危漏洞（供应链维度）',
        'check': check_skill_sec_010_dependency_vuln,
    },
    {
        'id': 'SKILL-SEC-011',
        'name': 'Prompt文档隐藏注入指令检测',
        'level': 'blocking',
        'category': 'llm_security',
        'module_id': '14',
        'applicable_types': ['skill', 'agent'],
        'description': '检测提示词中微字体/同色文字/零宽字符/注释等隐藏注入指令（提示词注入维度）',
        'check': check_skill_sec_011_hidden_prompt_injection,
    },
]
