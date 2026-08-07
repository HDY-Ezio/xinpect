"""
Web端安全P0补充规则集 - OWASP安全类 (M15)
从 security_p0.py 拆分而来，包含 OWASP 安全类检查:
  WEB-SEC-P0-001 localStorage/sessionStorage敏感数据检测
  WEB-SEC-P0-002 CSP unsafe-inline/unsafe-eval检测
  WEB-SEC-P0-003 target="_blank" 缺失 rel="noopener noreferrer"
  WEB-SEC-P0-008 HTTPS强制检测
  WEB-SEC-P0-009 document.write/eval安全检测
"""

import re
import os
from typing import List, Dict, Any

def _get_line_number(content: str, match_start: int) -> int:
    return content[:match_start].count('\n') + 1


def _is_comment_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith(('//', '/*', '*', '<!--'))


def _is_test_file(filepath: str) -> bool:
    basename = os.path.basename(filepath).lower()
    return any(x in basename for x in ['.test.', '.spec.', 'test_', '_test.', 'mock', 'fixture'])


# ============================================================
# WEB-SEC-P0-001: localStorage/sessionStorage敏感数据检测
# 对应OWASP客户端安全Top 10 #7
# ============================================================


def check_web_sec_p0_001_storage_sensitive_data(context) -> List[Dict]:
    """WEB-SEC-P0-001 localStorage敏感数据检测 - 检查是否在本地存储中保存密码、Token等敏感数据"""
    results = []
    
    if not context.is_web_frontend():
        return results
    
    js_files = context.find_files([".js", ".ts", ".jsx", ".tsx", ".vue", ".html", ".htm"])
    sensitive_storage_patterns = [
        (r'(localStorage|sessionStorage)\.setItem\s*\(\s*["\'].*(password|passwd|pwd).*["\']',
         '在localStorage中存储密码'),
        (r'(localStorage|sessionStorage)\.setItem\s*\(\s*["\'].*(token|access_token|auth_token|jwt).*["\']',
         '在localStorage中存储Token'),
        (r'(localStorage|sessionStorage)\.setItem\s*\(\s*["\'].*(api[_-]?key|secret).*["\']',
         '在localStorage中存储API密钥'),
        (r'(localStorage|sessionStorage)\.setItem\s*\(\s*["\'].*(credit.?card|cvv|ssn|id.?card).*["\']',
         '在localStorage中存储身份/金融信息'),
    ]
    
    issues = []
    for fpath in js_files:
        if _is_test_file(fpath):
            continue
        
        content = context.safe_read(fpath)
        if not content:
            continue
        
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if _is_comment_line(line):
                continue
            
            for pattern, desc in sensitive_storage_patterns:
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
            'id': 'WEB-SEC-P0-001',
            'name': 'localStorage敏感数据检测',
            'level': 'error',
            'message': f'检测到 {len(issues)} 处在localStorage/sessionStorage中存储敏感数据',
            'detail': '示例: ' + '; '.join(f"{os.path.basename(i['file'])}:{i['line']}" for i in issues[:5]),
            'file': issues[0]['file'],
            'line': issues[0]['line'],
            'snippet': issues[0]['snippet'],
            'fix': '敏感数据（密码/Token/密钥）应存储在HttpOnly Cookie或内存中，不得存入localStorage/sessionStorage',
            'category': 'web_security',
        })
    
    return results


# ============================================================
# WEB-SEC-P0-002: CSP策略unsafe-inline/unsafe-eval检测
# 对应OWASP客户端安全Top 10 #9
# ============================================================


def check_web_sec_p0_002_csp_unsafe(context) -> List[Dict]:
    """WEB-SEC-P0-002 CSP unsafe检测 - 检查Content Security Policy是否包含unsafe-inline或unsafe-eval"""
    results = []
    
    if not context.is_web_frontend():
        return results
    
    html_files = context.find_files([".html", ".htm"])
    
    issues = []
    
    # 检查HTML meta标签中的CSP
    for fpath in html_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        # 查找CSP meta标签
        # 用更宽容的匹配：找到包含Content-Security-Policy的meta标签，提取content值
        csp_meta_pattern = re.compile(
            r'<meta[^>]+http-equiv=["\']Content-Security-Policy["\'][^>]*>',
            re.IGNORECASE)
        
        for m in csp_meta_pattern.finditer(content):
            tag = m.group(0)
            # 提取content值（支持双引号和单引号）
            content_match = re.search(r'content=(?:"([^"]+)"|\'([^\']+)\')', tag, re.IGNORECASE)
            if content_match:
                csp_value = content_match.group(1) or content_match.group(2)
            else:
                # 无引号的值，不太规范但可能存在
                content_match2 = re.search(r'content=([^\s>]+)', tag, re.IGNORECASE)
                csp_value = content_match2.group(1) if content_match2 else ''
            
            line_num = _get_line_number(content, m.start())
            
            if "'unsafe-inline'" in csp_value or "'unsafe-eval'" in csp_value or \
               "unsafe-inline" in csp_value or "unsafe-eval" in csp_value:
                issues.append({
                    'file': fpath,
                    'line': line_num,
                    'desc': 'CSP包含unsafe-inline或unsafe-eval',
                    'snippet': csp_value[:100],
                })
    
    # 检查服务端配置文件中的CSP
    config_files = context.find_files([".json", ".js", ".ts"])
    for fpath in config_files:
        basename = os.path.basename(fpath).lower()
        if basename not in ('vite.config.ts', 'vite.config.js', 'next.config.js', 'webpack.config.js',
                           'vue.config.js', 'nuxt.config.js', 'headers.json', '_headers'):
            continue
        
        content = context.safe_read(fpath)
        if not content:
            continue
        
        if 'Content-Security-Policy' in content or 'contentSecurityPolicy' in content:
            if "'unsafe-inline'" in content or "'unsafe-eval'" in content:
                lines = content.split('\n')
                for i, line in enumerate(lines, 1):
                    if ('unsafe-inline' in line or 'unsafe-eval' in line) and 'Content-Security' in '\n'.join(lines[max(0,i-3):i+1]):
                        issues.append({
                            'file': fpath,
                            'line': i,
                            'desc': 'CSP配置包含unsafe-inline或unsafe-eval',
                            'snippet': line.strip()[:80],
                        })
                        break
    
    if issues:
        results.append({
            'id': 'WEB-SEC-P0-002',
            'name': 'CSP unsafe-inline/unsafe-eval检测',
            'level': 'error',
            'message': f'检测到 {len(issues)} 处CSP策略包含unsafe-inline或unsafe-eval',
            'detail': '示例: ' + '; '.join(f"{os.path.basename(i['file'])}:{i['line']}" for i in issues[:5]),
            'file': issues[0]['file'],
            'line': issues[0]['line'],
            'snippet': issues[0]['snippet'],
            'fix': '移除CSP中的unsafe-inline和unsafe-eval，使用nonce或hash方式放行必要内联脚本',
            'category': 'web_security',
        })
    
    return results


# ============================================================
# WEB-SEC-P0-003: 跨源链接noopener检测
# 对应Lighthouse Best Practices P0
# ============================================================


def check_web_sec_p0_003_noopener(context) -> List[Dict]:
    """WEB-SEC-P0-003 跨源链接noopener检测 - 检查target="_blank"的链接是否设置了rel="noopener"或"noreferrer" """
    results = []
    
    if not context.is_web_frontend():
        return results
    
    html_files = context.find_files([".html", ".htm", ".jsx", ".tsx", ".vue"])
    if not html_files:
        return results
    
    issues = []
    
    for fpath in html_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        # 查找有target="_blank"但没有noopener/noreferrer的链接
        pattern = re.compile(
            r'<a\s[^>]*target=["\']_blank["\'][^>]*>',
            re.IGNORECASE
        )
        
        for m in pattern.finditer(content):
            tag = m.group(0)
            
            # 检查是否有rel属性且包含noopener/noreferrer
            has_rel = bool(re.search(r'rel=["\'][^"\']*(noopener|noreferrer)[^"\']*["\']', tag, re.IGNORECASE))
            
            # 检查是否为同源链接（相对路径或同域名）
            href_match = re.search(r'href=["\']([^"\']+)["\']', tag, re.IGNORECASE)
            if href_match:
                href = href_match.group(1)
                # 相对路径视为同源，跳过
                if href.startswith('/') and not href.startswith('//'):
                    continue
                if href.startswith('#') or href.startswith('mailto:') or href.startswith('tel:'):
                    continue
                # 当前域名的也跳过（简化处理：无法静态判断，只检测明显的跨域）
                # 但为了不误报，我们只报有明显跨域URL且没有noopener的
                if not has_rel and ('http://' in href or 'https://' in href):
                    line_num = _get_line_number(content, m.start())
                    issues.append({
                        'file': fpath,
                        'line': line_num,
                        'desc': f'跨源链接缺少noopener: {href[:50]}',
                        'snippet': tag[:100],
                    })
    
    if issues:
        # 超过阈值才报告，避免误报过多
        if len(issues) >= 1:
            results.append({
                'id': 'WEB-SEC-P0-003',
                'name': '跨源链接noopener检测',
                'level': 'warning',
                'message': f'检测到 {len(issues)} 个跨源链接缺少rel="noopener"',
                'detail': '示例: ' + '; '.join(f"{os.path.basename(i['file'])}:{i['line']}" for i in issues[:5]),
                'file': issues[0]['file'],
                'line': issues[0]['line'],
                'snippet': issues[0]['snippet'],
                'fix': '为所有target="_blank"的跨源链接添加rel="noopener noreferrer"，防止tabnabbing攻击',
                'category': 'web_security',
            })
    
    return results


# ============================================================
# WEB-SEC-P0-004: HTML lang属性检测
# 对应WCAG 2.2 3.1.1 Language of Page (A) - P0
# ============================================================


def check_web_sec_p0_008_https_enforcement(context) -> List[Dict]:
    """WEB-SEC-P0-008 HTTPS强制检测 - 检查前端资源是否使用明文HTTP"""
    results = []
    
    if not context.is_web_frontend():
        return results
    
    html_files = context.find_files([".html", ".htm", ".jsx", ".tsx", ".vue", ".css", ".scss"])
    if not html_files:
        return results
    
    http_resources = []
    
    for fpath in html_files:
        if _is_test_file(fpath):
            continue
        
        content = context.safe_read(fpath)
        if not content:
            continue
        
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if _is_comment_line(line):
                continue
            
            # 查找硬编码的HTTP资源链接
            # <script src="http://...", <link href="http://..., <img src="http://...
            patterns = [
                (r'<(?:script|link|img|iframe|audio|video)\s[^>]*src\s*=\s*["\'](http://[^"\']+)["\']', '资源引用'),
                (r'url\s*\(\s*["\']?(http://[^"\'\)]+)["\']?\s*\)', 'CSS资源引用'),
            ]
            
            for pattern, desc in patterns:
                matches = re.finditer(pattern, line, re.IGNORECASE)
                for m in matches:
                    url = m.group(1) if len(m.groups()) >= 1 else ''
                    # 排除localhost和测试域名
                    if any(x in url for x in ['localhost', '127.0.0.1', '0.0.0.0', 'example.com', 'test.com']):
                        continue
                    
                    http_resources.append({
                        'file': fpath,
                        'line': i,
                        'url': url[:80],
                        'desc': desc,
                    })
                    break
    
    if http_resources:
        results.append({
            'id': 'WEB-SEC-P0-008',
            'name': 'HTTPS强制检测',
            'level': 'warning',
            'message': f'检测到 {len(http_resources)} 处使用明文HTTP加载资源',
            'detail': '示例: ' + '; '.join(f"{os.path.basename(i['file'])}:{i['line']}" for i in http_resources[:5]),
            'file': http_resources[0]['file'],
            'line': http_resources[0]['line'],
            'snippet': http_resources[0]['url'],
            'fix': '所有外部资源（脚本、样式、图片、字体）必须使用HTTPS加载，确保传输安全',
            'category': 'web_security',
        })
    
    return results


# ============================================================
# WEB-SEC-P0-009: document.write禁用检测
# 对应Lighthouse Performance P0
# ============================================================


def check_web_sec_p0_009_document_write(context) -> List[Dict]:
    """WEB-SEC-P0-009 document.write禁用检测 - 检查生产代码中是否使用document.write"""
    results = []
    
    if not context.is_web_frontend():
        return results
    
    js_files = context.find_files([".js", ".ts", ".jsx", ".tsx", ".vue", ".html", ".htm"])
    if not js_files:
        return results
    
    issues = []
    
    for fpath in js_files:
        if _is_test_file(fpath):
            continue
        
        # 跳过第三方库
        basename = os.path.basename(fpath)
        if basename in ('jquery.min.js', 'bootstrap.min.js', 'lodash.min.js'):
            continue
        
        content = context.safe_read(fpath)
        if not content:
            continue
        
        # 检查document.write调用
        matches = list(re.finditer(r'document\.write\s*\(', content))
        if matches:
            for m in matches[:3]:  # 每个文件最多3条
                line_num = _get_line_number(content, m.start())
                lines = content.split('\n')
                line = lines[line_num - 1] if line_num <= len(lines) else ''
                
                if _is_comment_line(line):
                    continue
                
                issues.append({
                    'file': fpath,
                    'line': line_num,
                    'desc': '使用document.write',
                    'snippet': line.strip()[:80],
                })
    
    if issues:
        results.append({
            'id': 'WEB-SEC-P0-009',
            'name': 'document.write禁用检测',
            'level': 'error',
            'message': f'检测到 {len(issues)} 处使用document.write动态注入内容',
            'detail': '示例: ' + '; '.join(f"{os.path.basename(i['file'])}:{i['line']}" for i in issues[:5]),
            'file': issues[0]['file'],
            'line': issues[0]['line'],
            'snippet': issues[0]['snippet'],
            'fix': '使用DOM操作方法（createElement、appendChild等）替代document.write，避免阻塞渲染和XSS风险',
            'category': 'web_security',
        })
    
    return results


# ============================================================
# 规则定义列表（Web P0补充规则）
# ============================================================

# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'WEB-SEC-P0-001',
        'name': 'localStorage敏感数据检测',
        'level': 'blocking',
        'category': 'web_security',
        'module_id': '15',
        'applicable_types': ['web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查是否在localStorage/sessionStorage中存储密码、Token等敏感数据（OWASP客户端Top10 #7）',
        'check': check_web_sec_p0_001_storage_sensitive_data,
    },
    {
        'id': 'WEB-SEC-P0-002',
        'name': 'CSP unsafe-inline/unsafe-eval检测',
        'level': 'blocking',
        'category': 'web_security',
        'module_id': '15',
        'applicable_types': ['web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查Content Security Policy是否包含unsafe-inline或unsafe-eval（OWASP客户端Top10 #9）',
        'check': check_web_sec_p0_002_csp_unsafe,
    },
    {
        'id': 'WEB-SEC-P0-003',
        'name': '跨源链接noopener检测',
        'level': 'problem',
        'category': 'web_security',
        'module_id': '15',
        'applicable_types': ['web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查target="_blank"的跨源链接是否设置了rel="noopener"（Lighthouse P0）',
        'check': check_web_sec_p0_003_noopener,
    },
    {
        'id': 'WEB-SEC-P0-008',
        'name': 'HTTPS强制检测',
        'level': 'blocking',
        'category': 'web_security',
        'module_id': '15',
        'applicable_types': ['web', 'mixed'],
        'description': '检查前端资源是否使用明文HTTP加载（Lighthouse Best Practices P0）',
        'check': check_web_sec_p0_008_https_enforcement,
    },
    {
        'id': 'WEB-SEC-P0-009',
        'name': 'document.write禁用检测',
        'level': 'blocking',
        'category': 'web_security',
        'module_id': '15',
        'applicable_types': ['web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查生产代码中是否使用document.write（Lighthouse Performance P0）',
        'check': check_web_sec_p0_009_document_write,
    },
]
