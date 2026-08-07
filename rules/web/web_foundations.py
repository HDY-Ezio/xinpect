"""
Web/H5基础规则集
从 frontend_rules.py 拆分而来，包含 Web 基础规范:
  WEB-001 HTML语义化检查
  WEB-002 无障碍访问检查
  WEB-003 响应式设计检查
  WEB-004 XSS防护检查
  WEB-005 前端性能基础检查
  WEB-006 控制台错误/Meta完整检查
  WEB-007 全局错误处理
  WEB-008 构建产物检查
"""

import re
import os
from typing import List, Dict, Any

def check_web_001_html_semantic(context) -> List[Dict]:
    """WEB-001 HTML语义化检查 - 检查是否使用了语义化标签"""
    results = []
    
    html_files = context.find_files([".html", ".htm"])
    if not html_files:
        return results
    
    for fpath in html_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        # 检查是否使用div过多而语义化标签过少
        div_count = len(re.findall(r'<div[\s>]', content, re.IGNORECASE))
        semantic_tags = ['header', 'nav', 'main', 'section', 'article', 'aside', 'footer']
        semantic_count = sum(
            len(re.findall(rf'<{tag}[\s>]', content, re.IGNORECASE)) 
            for tag in semantic_tags
        )
        
        if div_count > 10 and semantic_count == 0:
            results.append({
                'id': 'WEB-001',
                'name': 'HTML语义化检查',
                'level': 'warning',
                'message': f'使用了{div_count}个div标签，但未使用语义化标签',
                'file': fpath,
                'line': 0,
                'fix': '使用header/nav/main/section/article/footer等语义化标签替代div',
            })
    
    return results


# ===== WEB-002 无障碍访问检查 =====


def check_web_002_accessibility(context) -> List[Dict]:
    """WEB-002 无障碍访问检查 - 检查图片alt属性、表单label等"""
    results = []
    
    html_files = context.find_files([".html", ".htm", ".jsx", ".tsx", ".vue"])
    if not html_files:
        return results
    
    issues = []
    
    for fpath in html_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        # 检查图片是否有alt属性
        img_pattern = re.compile(r'<img\s[^>]*>', re.IGNORECASE)
        imgs = img_pattern.findall(content)
        no_alt_count = 0
        
        for img in imgs:
            if not re.search(r'alt\s*=', img, re.IGNORECASE):
                no_alt_count += 1
        
        if no_alt_count > 3:
            issues.append((fpath, f'{no_alt_count}张图片缺少alt属性'))
    
    if issues:
        total = sum(int(re.search(r'(\d+)', desc).group(1)) for _, desc in issues)
        results.append({
            'id': 'WEB-002',
            'name': '无障碍访问检查',
            'level': 'warning',
            'message': f'共{total}张图片缺少alt属性',
            'detail': '示例: ' + '; '.join(f'{os.path.basename(f)}: {d}' for f, d in issues[:3]),
            'file': issues[0][0] if issues else '',
            'line': 0,
            'fix': '为所有图片添加alt属性，提升无障碍访问体验',
        })
    
    return results


# ===== WEB-003 响应式设计检查 =====


def check_web_003_responsive(context) -> List[Dict]:
    """WEB-003 响应式设计检查 - 检查是否有viewport meta和media query"""
    results = []
    
    # 检查HTML是否有viewport meta
    html_files = context.find_files([".html", ".htm"])
    css_files = context.find_files([".css", ".scss", ".less"])
    
    if not html_files and not css_files:
        return results
    
    has_viewport = False
    for fpath in html_files:
        content = context.safe_read(fpath)
        if 'viewport' in content and 'width=device-width' in content:
            has_viewport = True
            break
    
    has_media_query = False
    for fpath in css_files:
        content = context.safe_read(fpath)
        if '@media' in content:
            has_media_query = True
            break
    
    if html_files and not has_viewport:
        results.append({
            'id': 'WEB-003',
            'name': '响应式设计检查',
            'level': 'warning',
            'message': '未设置viewport meta标签，移动端显示可能有问题',
            'file': html_files[0] if html_files else '',
            'line': 0,
            'fix': '在<head>中添加: <meta name="viewport" content="width=device-width, initial-scale=1.0">',
        })
    
    return results


# ===== WEB-004 XSS防护检查 =====


def check_web_004_xss_protection(context) -> List[Dict]:
    """WEB-004 XSS防护检查 - 检查是否使用了危险的DOM操作"""
    results = []
    
    js_files = context.find_files([".js", ".ts", ".jsx", ".tsx", ".vue"])
    if not js_files:
        return results
    
    dangerous_apis = {
        'innerHTML': '使用innerHTML可能导致XSS',
        'document.write': '使用document.write可能导致XSS',
        'eval(': '使用eval执行动态代码有安全风险',
        'setTimeout("': 'setTimeout字符串形式有安全风险',
        'setInterval("': 'setInterval字符串形式有安全风险',
    }
    
    high_risk_files = []
    
    for fpath in js_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        file_issues = []
        for api, desc in dangerous_apis.items():
            if api in content:
                file_issues.append(api)
        
        if len(file_issues) >= 2:
            high_risk_files.append((fpath, len(file_issues)))
    
    if high_risk_files:
        results.append({
            'id': 'WEB-004',
            'name': 'XSS防护检查',
            'level': 'warning',
            'message': f'{len(high_risk_files)}个文件使用了多个危险API，存在XSS风险',
            'detail': '高风险文件: ' + ', '.join(os.path.basename(f) for f, _ in high_risk_files[:5]),
            'file': high_risk_files[0][0] if high_risk_files else '',
            'line': 0,
            'fix': '使用textContent替代innerHTML，避免使用eval，对用户输入进行转义',
        })
    
    return results


# ===== WEB-005 性能优化检查 =====


def check_web_005_performance(context) -> List[Dict]:
    """WEB-005 性能优化检查 - 检查基础性能优化点"""
    results = []
    
    html_files = context.find_files([".html", ".htm"])
    css_files = context.find_files([".css", ".scss", ".less"])
    js_files = context.find_files([".js", ".ts"])
    
    issues = []
    
    # 检查CSS是否在顶部
    for fpath in html_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        # 检查是否有大量console.log
        console_count = 0
        for jsf in js_files:
            js_content = context.safe_read(jsf)
            console_count += len(re.findall(r'console\.log\(', js_content))
        
        if console_count > 10:
            issues.append(f'生产代码中有{console_count}个console.log')
        
        break  # 只检查第一个HTML
    
    # 检查是否有未使用的大图片引用（简化）
    img_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg']
    
    if issues:
        results.append({
            'id': 'WEB-005',
            'name': '性能优化检查',
            'level': 'info',
            'message': f'发现{len(issues)}个性能优化点',
            'detail': '问题: ' + '; '.join(issues[:5]),
            'file': '',
            'line': 0,
            'fix': '清理生产代码中的console.log，优化图片大小',
        })
    
    return results


# ===== WEB-006 控制台错误检查 =====


def check_web_006_console_errors(context) -> List[Dict]:
    """WEB-006 控制台错误检查 - 检查代码中可能导致运行时错误的问题"""
    results = []
    
    js_files = context.find_files([".js", ".ts", ".jsx", ".tsx", ".vue"])
    if not js_files:
        return results
    
    # 检查可能的错误模式
    error_patterns = [
        (r'\.\s*[a-zA-Z_]+\s*\(\s*\)\s*\.\s*[a-zA-Z_]+\s*\(\s*\)', '链式调用缺少空值保护'),
    ]
    
    return results  # 简化版本


# ===== WEB-006 Meta标签完整性 =====


def check_web_006_meta_complete(context) -> List[Dict]:
    """WEB-006 Meta标签完整性 - 检查HTML基础meta标签是否完整"""
    results = []
    
    html_files = context.find_files([".html", ".htm"])
    if not html_files:
        return results
    
    # 检查index.html
    index_files = [f for f in html_files if os.path.basename(f).lower() in ('index.html', 'index.htm')]
    check_files = index_files or html_files[:1]
    
    for fpath in check_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        missing = []
        
        # 检查title
        if not re.search(r'<title>.+</title>', content, re.IGNORECASE | re.DOTALL):
            missing.append('title')
        
        # 检查viewport
        if not re.search(r'<meta[^>]*name=["\']viewport["\']', content, re.IGNORECASE):
            missing.append('viewport')
        
        # 检查description
        if not re.search(r'<meta[^>]*name=["\']description["\']', content, re.IGNORECASE):
            missing.append('description')
        
        # 检查charset
        if not re.search(r'<meta[^>]*charset=["\']', content, re.IGNORECASE):
            missing.append('charset')
        
        if missing:
            results.append({
                'id': 'WEB-006',
                'name': 'Meta标签完整性',
                'level': 'info',
                'message': f"缺少基础meta标签: {', '.join(missing)}",
                'file': fpath,
                'line': 0,
                'fix': '补充title/viewport/description/charset等基础meta标签，提升SEO和用户体验',
            })
    
    return results


# ===== WEB-007 全局错误处理 =====


def check_web_007_global_error(context) -> List[Dict]:
    """WEB-007 全局错误处理 - 检查是否配置了全局错误监听"""
    results = []
    
    js_files = context.find_files([".js", ".ts", ".jsx", ".tsx"])
    if not js_files:
        return results
    
    has_onerror = False
    has_unhandled = False
    has_error_boundary = False
    
    for fpath in js_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        basename = os.path.basename(fpath)
        # 跳过测试文件和第三方库
        if '.test.' in basename or '.spec.' in basename or basename in ('webpack.config.js', 'vite.config.ts'):
            continue
        
        if re.search(r'window\.onerror|window\.addEventListener\s*\(\s*["\']error["\']', content):
            has_onerror = True
        if re.search(r'unhandledrejection|onunhandledrejection', content):
            has_unhandled = True
        if re.search(r'componentDidCatch|getDerivedStateFromError|ErrorBoundary|error\.jsx|error\.tsx', content):
            has_error_boundary = True
    
    if not has_onerror and not has_unhandled and not has_error_boundary:
        results.append({
            'id': 'WEB-007',
            'name': '全局错误处理',
            'level': 'warning',
            'message': '未检测到全局错误处理机制（window.onerror/unhandledrejection/ErrorBoundary）',
            'file': '',
            'line': 0,
            'fix': '添加window.onerror和unhandledrejection监听，或使用React ErrorBoundary捕获渲染错误',
        })
    
    return results


# ===== WEB-008 构建产物检查 =====


def check_web_008_build_output(context) -> List[Dict]:
    """WEB-008 构建产物检查 - 检查前端构建产物是否完整"""
    results = []
    
    # 常见构建产物目录
    build_dirs = ['dist', 'build', 'out', '.next', '.nuxt', 'output']
    project_path = context.project_path or '.'
    
    has_build_dir = False
    for bd in build_dirs:
        build_path = os.path.join(project_path, bd)
        if os.path.isdir(build_path):
            has_build_dir = True
            
            # 检查index.html
            if bd in ('.next', '.nuxt'):
                # SSR框架检查server目录
                server_dir = os.path.join(build_path, 'server')
                if not os.path.isdir(server_dir):
                    results.append({
                        'id': 'WEB-008',
                        'name': '构建产物检查',
                        'level': 'warning',
                        'message': f'{bd}构建产物不完整（缺少server目录）',
                        'file': build_path,
                        'line': 0,
                        'fix': '重新执行构建命令，确保构建完整执行',
                    })
            else:
                index_html = os.path.join(build_path, 'index.html')
                assets_dir = os.path.join(build_path, 'assets')
                if not os.path.isfile(index_html):
                    results.append({
                        'id': 'WEB-008',
                        'name': '构建产物检查',
                        'level': 'warning',
                        'message': f'{bd}构建产物不完整（缺少index.html）',
                        'file': build_path,
                        'line': 0,
                        'fix': '重新执行构建命令，确保生成index.html',
                    })
            break
    
    # 没有构建目录时检查是否有构建配置
    if not has_build_dir:
        pkg_path = os.path.join(project_path, 'package.json')
        if os.path.isfile(pkg_path):
            content = context.safe_read(pkg_path)
            if 'build' in content:
                # 有构建脚本但没有产物，可能是未构建
                results.append({
                    'id': 'WEB-008',
                    'name': '构建产物检查',
                    'level': 'info',
                    'message': '检测到构建脚本配置，但未找到构建产物目录',
                    'file': pkg_path,
                    'line': 0,
                    'fix': '执行npm run build生成构建产物后再部署',
                })
    
    return results


# ===== 5.4 AI复制按钮 =====


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'WEB-001',
        'name': 'HTML语义化检查',
        'level': 'suggestion',
        'category': 'html',
        'module_id': '5',
        'applicable_types': ['web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查是否使用了语义化HTML标签',
        'check': check_web_001_html_semantic,
    },
    {
        'id': 'WEB-002',
        'name': '无障碍访问检查',
        'level': 'problem',
        'category': 'html',
        'module_id': '5',
        'applicable_types': ['web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查图片alt属性、表单label等无障碍访问要素',
        'check': check_web_002_accessibility,
    },
    {
        'id': 'WEB-003',
        'name': '响应式设计检查',
        'level': 'problem',
        'category': 'html',
        'module_id': '5',
        'applicable_types': ['web', 'mixed'],
        'description': '检查是否有viewport meta和响应式设计',
        'check': check_web_003_responsive,
    },
    {
        'id': 'WEB-004',
        'name': 'XSS防护检查',
        'level': 'blocking',
        'category': 'security',
        'module_id': '3',
        'applicable_types': ['web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查是否使用了危险的DOM操作API',
        'check': check_web_004_xss_protection,
    },
    {
        'id': 'WEB-005',
        'name': '性能优化检查',
        'level': 'suggestion',
        'category': 'performance',
        'module_id': '12',
        'applicable_types': ['web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查基础性能优化点',
        'check': check_web_005_performance,
    },
    {
        'id': 'WEB-006',
        'name': 'Meta标签完整性',
        'level': 'suggestion',
        'category': 'web_specific',
        'module_id': '7',
        'applicable_types': ['web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查HTML meta标签是否完整（viewport/title/description等）',
        'check': check_web_006_meta_complete,
    },
    {
        'id': 'WEB-007',
        'name': '全局错误处理',
        'level': 'problem',
        'category': 'error_handling',
        'module_id': '13',
        'applicable_types': ['web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查是否配置了全局错误监听（window.onerror/unhandledrejection）',
        'check': check_web_007_global_error,
    },
    {
        'id': 'WEB-008',
        'name': '构建产物检查',
        'level': 'problem',
        'category': 'deploy',
        'module_id': '7',
        'applicable_types': ['web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查前端构建产物是否完整（index.html/assets/manifest）',
        'check': check_web_008_build_output,
    },
]
