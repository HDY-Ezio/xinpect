"""
Agent/LLM应用安全规则集 - 插件与供应链安全 (M14)
LLM/Agent应用专项安全检查 - 插件与供应链安全类
包含: HTTPS强制、Manifest敏感信息、域名作用域、密钥扫描

来源标准: OpenAI插件安全 / 虾评四维检测
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


def check_oai_sec_001_https_enforcement(context) -> List[Dict]:
    """OAI-SEC-001 插件通信HTTPS强制 - 检查插件/Agent所有外部通信是否使用HTTPS"""
    results = []
    
    all_files = context.find_files([".py", ".js", ".ts", ".json", ".yaml", ".yml"])
    
    http_urls = []
    for fpath in all_files:
        if _is_skippable_file(fpath):
            continue
        content = context.safe_read(fpath)
        if not content:
            continue
        
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if _is_comment_line(line):
                continue
            
            # 查找明文HTTP URL（排除localhost和内网地址）
            urls = re.findall(r'["\'](http://[a-zA-Z0-9._\-:]+)', line)
            for url in urls:
                # 排除本地和内网地址
                if any(x in url for x in ['localhost', '127.0.0.1', '0.0.0.0', '192.168.', '10.', '172.']):
                    continue
                if 'example.com' in url or 'test.com' in url:
                    continue
                
                http_urls.append({
                    'file': fpath,
                    'line': i,
                    'url': url[:60],
                })
    
    if http_urls:
        results.append({
            'id': 'OAI-SEC-001',
            'name': '插件通信HTTPS强制',
            'level': 'error',
            'message': f'检测到 {len(http_urls)} 处使用明文HTTP通信',
            'detail': '示例: ' + '; '.join(f"{os.path.basename(i['file'])}:{i['line']} {i['url']}" for i in http_urls[:5]),
            'file': http_urls[0]['file'],
            'line': http_urls[0]['line'],
            'snippet': http_urls[0]['url'],
            'fix': '所有外部API通信必须使用HTTPS加密，禁止明文HTTP传输',
            'category': 'llm_security',
        })
    
    return results


# ============================================================
# OAI-SEC-002: Manifest文件敏感信息检测
# ============================================================
def check_oai_sec_002_manifest_sensitive_info(context) -> List[Dict]:
    """OAI-SEC-002 Manifest文件敏感信息检测 - 检查ai-plugin.json等manifest文件是否包含敏感信息"""
    results = []
    
    # 优化：manifest文件通常在固定位置，优先直接检查已知路径，避免全项目遍历json
    manifest_names = {'ai-plugin.json', 'manifest.json', 'plugin.json'}
    manifest_files = []
    _checked_manifests = set()
    
    # 优先检查常见位置（O(1)直接定位，不遍历全目录）
    _manifest_search_dirs = []
    if context.project_path and os.path.isdir(context.project_path):
        _manifest_search_dirs.append(context.project_path)
        _manifest_search_dirs.append(os.path.join(context.project_path, '.well-known'))
    if context.backend_path and context.backend_path != context.project_path and os.path.isdir(context.backend_path):
        _manifest_search_dirs.append(context.backend_path)
    
    for search_dir in _manifest_search_dirs:
        for name in manifest_names:
            candidate = os.path.join(search_dir, name)
            if os.path.isfile(candidate) and candidate not in _checked_manifests:
                manifest_files.append(candidate)
                _checked_manifests.add(candidate)
    
    # 如果常见位置没找到，再从缓存中过滤（find_files有_all_walk_cache，不会重复os.walk）
    if not manifest_files:
        json_files = context.find_files([".json"])
        manifest_files = [f for f in json_files if os.path.basename(f).lower() in manifest_names]
    
    if not manifest_files:
        return results
    
    sensitive_patterns = [
        (r'(api_key|secret|token|password)\s*["\']?\s*[:=]\s*["\'][^"\']{8,}',
         '密钥/凭证'),
        (r'sk-[a-zA-Z0-9]{20,}', 'OpenAI API Key'),
        (r'(private_key|-----BEGIN)', '私钥'),
    ]
    
    issues = []
    for fpath in manifest_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            for pattern, desc in sensitive_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    # 排除描述性文字
                    if 'description' in line.lower() and 'api key' in line.lower():
                        continue
                    
                    issues.append({
                        'file': fpath,
                        'line': i,
                        'desc': desc,
                        'snippet': line.strip()[:80],
                    })
                    break
    
    if issues:
        results.append({
            'id': 'OAI-SEC-002',
            'name': 'Manifest文件敏感信息检测',
            'level': 'error',
            'message': f'检测到 {len(issues)} 处Manifest文件中包含敏感信息',
            'detail': '示例: ' + '; '.join(f"{os.path.basename(i['file'])}:{i['line']} {i['desc']}" for i in issues[:5]),
            'file': issues[0]['file'],
            'line': issues[0]['line'],
            'snippet': issues[0]['snippet'],
            'fix': 'Manifest文件中不得包含任何密钥、凭证或敏感配置，应通过环境变量注入',
            'category': 'llm_security',
        })
    
    return results


# ============================================================
# OAI-SEC-006: 插件域名范围校验
# ============================================================
def check_oai_sec_006_domain_scope(context) -> List[Dict]:
    """OAI-SEC-006 插件域名范围校验 - 检查代码实际请求域名是否在manifest声明范围内"""
    results = []
    
    # 查找manifest文件中的域名声明
    manifest_domains = set()
    manifest_files = []
    
    if context.project_path:
        _manifest_names_006 = {'ai-plugin.json', 'manifest.json', 'openapi.yaml', 'openapi.json'}
        _candidate_files = context.find_files([".json", ".yaml"])
        manifest_files = [f for f in _candidate_files if os.path.basename(f).lower() in _manifest_names_006]
    
    for fpath in manifest_files:
        content = context.safe_read(fpath)
        # 提取URL中的域名
        urls = re.findall(r'https?://([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', content)
        for domain in urls:
            manifest_domains.add(domain.lower())
    
    if not manifest_domains:
        return results
    
    # 检查代码中实际请求的域名
    all_py = context.find_files([".py"])
    actual_domains = set()
    for f in all_py:
        content = context.safe_read(f)
        urls = re.findall(r'(?:requests\.|urllib\.|httpx\.)(?:get|post|put|delete|patch)\s*\(\s*f?["\']https?://([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', content)
        for d in urls:
            actual_domains.add(d.lower())
    
    if actual_domains:
        out_of_scope = actual_domains - manifest_domains
        # 子域名视为在范围内
        truly_out = []
        for d in out_of_scope:
            is_sub = any(d.endswith('.' + md) for md in manifest_domains)
            if not is_sub:
                truly_out.append(d)
        
        if truly_out:
            results.append({
                'id': 'OAI-SEC-006',
                'name': '插件域名范围校验',
                'level': 'warning',
                'message': f'检测到 {len(truly_out)} 个超出manifest声明范围的请求域名',
                'detail': '超出范围: ' + ', '.join(truly_out[:5]) + 
                         f'\n声明域名: {", ".join(sorted(manifest_domains)[:5])}',
                'file': '',
                'line': 0,
                'fix': '确保所有API请求都在manifest/OpenAPI声明的域名范围内，不得跨域调用',
                'category': 'llm_security',
            })
    
    return results


# ============================================================
# GH-SEC-001: 通用密钥扫描（增强版，200+模式核心子集）
# ============================================================
def check_gh_sec_001_secret_scanning(context) -> List[Dict]:
    """GH-SEC-001 通用密钥扫描 - 多模式密钥/凭证检测（GitHub Secret Scanning核心子集）"""
    results = []
    
    all_files = context.find_files([".py", ".js", ".ts", ".jsx", ".tsx", ".env", ".json", ".yaml", ".yml", ".ini", ".cfg"])
    
    # 精选高置信度密钥模式（GitHub Secret Scanning核心子集）
    secret_patterns = [
        # 云服务商
        (r'AKIA[0-9A-Z]{16}', 'AWS Access Key ID'),
        (r'ASIA[0-9A-Z]{16}', 'AWS STS Access Key'),
        (r'AIza[0-9A-Za-z\-_]{35}', 'Google API Key'),
        (r'ya29\.[0-9A-Za-z\-_]+', 'Google OAuth Token'),
        (r'AZ[a-zA-Z0-9]{32}', 'Azure Storage Key'),
        
        # LLM/AI服务商
        (r'sk-[a-zA-Z0-9]{20,}', 'OpenAI API Key'),
        (r'proj-[a-zA-Z0-9]{20,}', 'OpenAI Project Key'),
        (r'antsk_[a-zA-Z0-9]{32,}', 'Anthropic API Key'),
        
        # 通用密钥模式
        (r'(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token)\s*[:=]\s*["\'][a-zA-Z0-9_\-]{16,}["\']',
         '通用API密钥/Token'),
        (r'(?:private[_-]?key|secret)\s*[:=]\s*["\'][a-zA-Z0-9+/=\n]{32,}["\']',
         '私钥/密钥'),
        
        # GitHub
        (r'ghp_[a-zA-Z0-9]{36}', 'GitHub Personal Access Token'),
        (r'github_pat_[a-zA-Z0-9_]{82}', 'GitHub Fine-grained PAT'),
        
        # Slack
        (r'xox[baprs]-[a-zA-Z0-9-]{10,}', 'Slack Token'),
        
        # Stripe
        (r'sk_live_[0-9a-zA-Z]{24,}', 'Stripe Live Secret Key'),
        (r'pk_live_[0-9a-zA-Z]{24,}', 'Stripe Live Publishable Key'),
    ]
    
    issues = []
    for fpath in all_files:
        if _is_skippable_file(fpath):
            continue
        
        # 跳过示例配置文件
        basename = os.path.basename(fpath).lower()
        if any(x in basename for x in ['.example', '.sample', '.template', 'example.', 'sample.']):
            continue
        
        content = context.safe_read(fpath)
        if not content:
            continue
        
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if _is_comment_line(line):
                continue
            
            for pattern, desc in secret_patterns:
                matches = re.findall(pattern, line)
                if matches:
                    match_val = matches[0] if isinstance(matches[0], str) else matches[0][0]
                    
                    # 排除占位符和示例值
                    if any(x in match_val.lower() for x in ['xxxx', 'your_', 'example', 'placeholder']):
                        continue
                    if any(x in line.lower() for x in ['xxx', 'your_', 'example', 'placeholder', 'replace_me', 'test_key']):
                        continue
                    
                    issues.append({
                        'file': fpath,
                        'line': i,
                        'desc': desc,
                        'snippet': line.strip()[:60],
                    })
                    break  # 每行只报一次
    
    if issues:
        # 去重（按文件+描述）
        seen = set()
        unique_issues = []
        for i in issues:
            key = (i['file'], i['desc'])
            if key not in seen:
                seen.add(key)
                unique_issues.append(i)
        
        if unique_issues:
            results.append({
                'id': 'GH-SEC-001',
                'name': '通用密钥扫描',
                'level': 'error',
                'message': f'检测到 {len(unique_issues)} 处可能的密钥/凭证泄露',
                'detail': '示例: ' + '; '.join(f"{os.path.basename(i['file'])}:{i['line']} {i['desc']}" for i in unique_issues[:5]),
                'file': unique_issues[0]['file'],
                'line': unique_issues[0]['line'],
                'snippet': unique_issues[0]['snippet'],
                'fix': '立即轮换泄露的密钥，将密钥移至环境变量/密钥管理系统，从代码历史中彻底清除',
                'category': 'llm_security',
            })
    
    return results


# ============================================================
# 规则定义列表（23条P0 Agent/LLM安全规则）
# ============================================================


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'OAI-SEC-001',
        'name': '插件通信HTTPS强制',
        'level': 'blocking',
        'category': 'llm_security',
        'module_id': '14',
        'applicable_types': ['skill', 'agent', 'web', 'mixed', 'python_backend', 'python_tool', 'flask'],
        'description': '检查插件/Agent所有外部通信是否使用HTTPS加密',
        'check': check_oai_sec_001_https_enforcement,
    },
    {
        'id': 'OAI-SEC-002',
        'name': 'Manifest文件敏感信息检测',
        'level': 'blocking',
        'category': 'llm_security',
        'module_id': '14',
        'applicable_types': ['skill', 'agent'],
        'description': '检查ai-plugin.json等manifest文件是否包含密钥等敏感信息',
        'check': check_oai_sec_002_manifest_sensitive_info,
    },
    {
        'id': 'OAI-SEC-006',
        'name': '插件域名范围校验',
        'level': 'problem',
        'category': 'llm_security',
        'module_id': '14',
        'applicable_types': ['skill', 'agent'],
        'description': '检查代码实际请求域名是否在manifest/OpenAPI声明范围内',
        'check': check_oai_sec_006_domain_scope,
    },
    {
        'id': 'GH-SEC-001',
        'name': '通用密钥扫描',
        'level': 'blocking',
        'category': 'llm_security',
        'module_id': '14',
        'applicable_types': [],  # 所有类型适用
        'description': '多模式密钥/凭证检测（GitHub Secret Scanning核心子集：AWS/Google/GitHub/Stripe/Slack等）',
        'check': check_gh_sec_001_secret_scanning,
    },
]
