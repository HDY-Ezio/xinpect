"""
小程序WXML规则集 - 质量与安全检查 (v3.4 AST增强版)
微信小程序WXML模板检查 - 性能/安全/规范类
包含: 图片懒加载、禁止JS函数调用、属性值引号、域名白名单

v3.4 改进: 优先使用AST解析(JS用@babel/parser, WXML用htmlparser2)，
           AST不可用时自动降级到原有正则匹配。
"""

"""
小程序WXML规则集 (v3.4 AST增强版)
微信小程序WXML模板检查
包含: 方法绑定存在性、标签合法性、数据绑定、列表渲染等检查

v3.4 改进: 优先使用AST解析(JS用@babel/parser, WXML用htmlparser2)，
           AST不可用时自动降级到原有正则匹配。
           AST优势: 精准识别ES6 shorthand/async/箭头函数/类方法，
           精准解析WXML多行标签和属性值，消除正则误报。
"""

import re
import os
import json
from typing import List, Dict, Any, Set, Optional

# v4.6.1 性能优化：AST分析器懒加载，避免import时启动Node.js子进程
_ast_analyzer = None
_ast_available = None  # None=未检查, True/False=结果


def _get_ast_analyzer():
    """懒加载AST分析器：首次真正使用时才导入并启动Node.js子进程"""
    global _ast_analyzer, _ast_available
    if _ast_available is not None:
        return _ast_analyzer if _ast_available else None
    try:
        from core.js_ast_analyzer import get_js_ast_analyzer
        _ast_analyzer = get_js_ast_analyzer()
        _ast_available = _ast_analyzer.is_available
    except Exception as e:  # noqa: broad exception handling
        _ast_analyzer = None
        _ast_available = False
    return _ast_analyzer if _ast_available else None


# ===== JS关键字和Page/Component配置属性名（不是方法）=====
_JS_KEYWORDS_AND_CONFIG_KEYS = {
    # JS关键字
    'if', 'for', 'while', 'switch', 'catch', 'with', 'return',
    'function', 'typeof', 'void', 'delete', 'new', 'do', 'else',
    'try', 'finally', 'class', 'super', 'yield', 'await', 'async',
    # Page/Component配置属性名
    'data', 'properties', 'methods', 'lifetimes',
    'pageLifetimes', 'observers', 'options', 'behaviors',
    'externalClasses', 'relations', 'attached', 'detached',
    'created', 'ready', 'moved',
    # ES modules
    'import', 'export', 'default', 'const', 'let', 'var',
    'require', 'module', 'exports',
}


def check_mp_005_image_lazy(context) -> List[Dict]:
    """MP-005 图片懒加载建议 - 长列表中的图片建议使用lazy-load
    
    v3.4: 使用AST精确识别image标签及其lazy-load属性。
    v1.19.0改进: 检查范围扩展到components/目录，覆盖非标准image标签
                 （如含动态class的image、多行标签内的image等）
    """
    results = []

    wxml_files = context.find_files([".wxml"])
    if not wxml_files:
        return results

    for fpath in wxml_files:
        ast = _get_ast_analyzer()
        if ast:
            # ===== AST模式 =====
            images = ast.get_wxml_images(fpath)
            if images is not None:
                image_count = len(images)
                lazy_count = sum(1 for img in images if img.get("hasLazyLoad"))

                if image_count > 5 and lazy_count == 0:
                    results.append({
                        'id': 'MP-005',
                        'name': '图片懒加载建议',
                        'level': 'info',
                        'message': f'页面有{image_count}张图片，建议添加lazy-load属性',
                        'file': fpath,
                        'line': 0,
                        'fix': '为图片添加lazy-load属性，提升长列表性能',
                        'suggestion_code': '<image src="{{url}}" lazy-load />',
                    })
                continue
            # AST对该文件不可用，降级

        # ===== 正则降级模式 =====
        content = context.safe_read(fpath)
        if not content:
            continue

        # 改进：使用DOTALL模式匹配多行image标签
        image_count = len(re.findall(r'<image\b', content, re.IGNORECASE))
        # 也检查cover-image标签
        image_count += len(re.findall(r'<cover-image\b', content, re.IGNORECASE))
        lazy_count = len(re.findall(r'<(?:image|cover-image)[^>]*lazy-load', content, re.IGNORECASE))

        if image_count > 5 and lazy_count == 0:
            # 判断是否在列表/循环渲染中（wx:for环境下的图片更值得提醒）
            in_loop = bool(re.search(r'wx:for', content))
            norm_path = fpath.replace(os.sep, '/')
            is_component = '/components/' in norm_path

            if in_loop or is_component:
                results.append({
                    'id': 'MP-005',
                    'name': '图片懒加载建议',
                    'level': 'info',
                    'message': f'{"组件" if is_component else ""}页面有{image_count}张图片{"含列表渲染" if in_loop else ""}，建议添加lazy-load属性',
                    'file': fpath,
                    'line': 0,
                    'fix': '为图片添加lazy-load属性，提升长列表/组件性能',
                    'suggestion_code': '<image src="{{url}}" lazy-load />',
                })

    return results


# ===== MP-006 WXML禁止调用JS函数 =====
def check_mp_006_no_js_call_in_wxml(context) -> List[Dict]:
    """MP-006 WXML禁止调用JS函数 - WXML的{{}}表达式中不允许直接调用JS函数
    
    WXML数据绑定表达式中只能使用简单运算和WXS函数，不能调用Page/Component中定义的JS方法。
    检测逻辑：解析{{}}表达式，检测是否包含xxx()函数调用（排除WXS引用和合法运算符）。
    
    v1.20.1 修复：排除||、&&、?:等逻辑运算符的误判。
    只匹配xxx()格式（带括号的调用），排除：
    - {{xxx || 'default'}} 中的||运算符
    - {{xxx && 'value'}} 中的&&运算符  
    - {{condition ? a : b}} 中的三元运算符
    """
    results = []
    
    wxml_files = context.find_files([".wxml"])
    if not wxml_files:
        return results
    
    # 合法的WXS模块方法调用前缀（WXS模块在wxs标签或.wxs文件中定义）
    wxs_modules = set()
    
    # 匹配模式：{{}}内的函数调用 - 严格匹配 word( 格式
    # 合法: {{a + b}}, {{a > 0 ? 'yes' : 'no'}}, {{a.length}}, {{a + ''}}, {{a || 'default'}}
    # 非法: {{formatPrice(price)}}, {{getTime()}}, {{item.filter(x)}}
    func_call_in_mustache = re.compile(r'{{\s*[^}]*?\b(\w+)\s*\([^)]*\)[^}]*?}}')
    
    # 合法的内置方法/属性（不是函数调用）
    allowed_calls = {
        'length', 'toString', 'toFixed',
    }
    
    for fpath in wxml_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        # 提取WXS模块名
        wxs_pattern = re.compile(r'<wxs[^>]*\bmodule\s*=\s*["\'](\w+)["\']', re.IGNORECASE)
        for m in wxs_pattern.finditer(content):
            wxs_modules.add(m.group(1))
        
        # 查找{{}}中的函数调用
        issues = []
        for m in func_call_in_mustache.finditer(content):
            full_match = m.group(0)
            func_name = m.group(1)
            
            # 排除WXS模块调用（合法）
            try:
                func_idx = full_match.index(func_name + '(')
                before_func = full_match[:func_idx]
            except ValueError:
                continue
            if any(module + '.' in before_func for module in wxs_modules):
                continue
            
            # 排除数字格式化等安全调用
            if func_name in allowed_calls:
                continue
            
            # v1.20.1 修复：排除逻辑运算符导致的误判
            # 检查函数调用前面紧邻的运算符，如果是 || || && 则跳过
            # 模式：... || funcName(...) 或 ... && funcName(...)
            # 这种情况下 funcName 很可能是变量名而非函数调用
            before_trimmed = before_func.rstrip()
            if before_trimmed.endswith('||') or before_trimmed.endswith('&&'):
                continue
            
            # 检查是否在三元运算符的分支中：condition ? funcName() : xxx
            # 提取 {{ }} 内部的表达式内容
            inner_expr = full_match[2:-2].strip()  # 去掉 {{ 和 }}
            # 如果函数调用前有 ? 运算符（三元条件），可能是分支值而非函数调用
            # 检查 funcName( 前面是否有 ? 紧邻
            func_pos = inner_expr.find(func_name + '(')
            if func_pos > 0:
                char_before = inner_expr[func_pos - 1] if func_pos > 0 else ''
                if char_before in ('?', ':'):
                    # 检查是否真的是三元运算符的一部分
                    # 简单启发式：如果?前面是表达式，则可能是三元条件
                    pass  # 保持匹配，因为三元运算符的分支中的函数调用仍然是JS函数调用
            
            # 排除 {{ xxx || fn() }} 模式：如果||后面的整个部分没有真正的函数调用语义
            # 例如 {{ a || 'default' }} 不应该匹配（但原regex不会匹配这个因为没有()）
            # 额外检查：如果匹配到的 "func" 实际上是 || 或 && 运算符后面的标识符
            # 且 () 部分是字符串/数字字面量的括号，则跳过
            func_call_pos = full_match.find(func_name + '(')
            after_paren = full_match[func_call_pos + len(func_name) + 1:]
            close_paren_pos = after_paren.find(')')
            if close_paren_pos >= 0:
                paren_content = after_paren[:close_paren_pos].strip()
                # 如果括号内只有字符串字面量或数字字面量，且前面有 || 或 &&
                if paren_content and paren_content[0] in ("'", '"') and ('||' in before_func or '&&' in before_func):
                    continue
            
            line_num = content[:m.start()].count('\n') + 1
            issues.append({
                'func': func_name,
                'line': line_num,
                'snippet': full_match[:80],
            })
        
        if issues:
            rel_path = os.path.relpath(fpath, context.project_path) if context.project_path else fpath
            detail_lines = [f"  第{iss['line']}行: {iss['snippet']}" for iss in issues[:5]]
            
            results.append({
                'id': 'MP-006',
                'name': 'WXML禁止调用JS函数',
                'level': 'error',
                'message': f'发现{len(issues)}处在WXML {{{{ }}}}表达式中直接调用JS函数',
                'detail': '\n'.join(detail_lines),
                'file': fpath,
                'line': issues[0]['line'],
                'fix': 'WXML中不能直接调用JS函数，应使用WXS模块或在JS中预处理数据后setData',
                'suggestion_code': '<!-- 错误方式 -->\n<!-- <view>{{ formatPrice(price) }}</view> -->\n\n<!-- 正确方式1: 在JS中预处理 -->\n<!-- JS: this.setData({ formattedPrice: this.formatPrice(price) }) -->\n<!-- <view>{{ formattedPrice }}</view> -->\n\n<!-- 正确方式2: 使用WXS -->\n<!-- <wxs module="utils">module.exports.formatPrice = function(p) { return p.toFixed(2) }</wxs> -->\n<!-- <view>{{ utils.formatPrice(price) }}</view> -->',
            })
    
    return results


# ===== MP-007 WXML属性值必须加引号 =====
def check_mp_007_attr_must_quote(context) -> List[Dict]:
    """MP-007 WXML属性值必须加引号
    
    检测逻辑：正则检查WXML标签的所有属性是否有引号包裹。
    模式：属性名=值（无引号）→ warning
    排除：布尔属性（如hidden, lazy-load不带值的情况）
    """
    results = []
    
    wxml_files = context.find_files([".wxml"])
    if not wxml_files:
        return results
    
    # 匹配属性赋值但无引号的情况
    # 合法: class="xxx", src='{{url}}', hidden
    # 非法: class=xxx, src={{url}}, data-id=123
    # 注意：{{}}中的=不是属性赋值
    unquoted_attr_pattern = re.compile(
        r'<(\w[\w-]*)'                     # 标签名
        r'([^>]*)>',                        # 属性区域
        re.DOTALL
    )
    
    # 在属性区域中找未加引号的赋值
    # 属性名=值（值不是以引号开头）
    attr_assign_pattern = re.compile(
        r'\s([\w][\w-]*)='                 # 属性名=
        r'(?!["\'])'                        # 不以引号开头
        r'([^\s>"\']+)'                     # 值（到空格或>为止）
    )
    
    for fpath in wxml_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        issues = []
        
        # 先提取所有标签
        for tag_m in unquoted_attr_pattern.finditer(content):
            tag_name = tag_m.group(1)
            attrs_section = tag_m.group(2)
            tag_start = tag_m.start()
            
            # 在属性区域中查找未加引号的属性
            for attr_m in attr_assign_pattern.finditer(attrs_section):
                attr_name = attr_m.group(1)
                attr_value = attr_m.group(2)
                
                # 排除特殊情况
                # 1. {{}}内的表达式
                if attr_value.startswith('{{'):
                    continue
                # 2. wx:xxx指令的值通常可以不带引号（但最好带）
                # 实际上wx:指令的值也应该加引号，所以这里不跳过
                
                # 计算行号
                abs_pos = tag_start + attr_m.start()
                line_num = content[:abs_pos].count('\n') + 1
                
                issues.append({
                    'attr': attr_name,
                    'value': attr_value[:40],
                    'line': line_num,
                })
        
        if issues:
            rel_path = os.path.relpath(fpath, context.project_path) if context.project_path else fpath
            detail_lines = [f"  第{iss['line']}行: {iss['attr']}={iss['value']}" for iss in issues[:5]]
            
            results.append({
                'id': 'MP-007',
                'name': 'WXML属性值必须加引号',
                'level': 'warning',
                'message': f'发现{len(issues)}处WXML属性值未加引号',
                'detail': '\n'.join(detail_lines),
                'file': fpath,
                'line': issues[0]['line'],
                'fix': '为所有WXML属性值添加双引号包裹',
                'suggestion_code': '<!-- 错误 -->\n<!-- <view class=my-class src={{url}} /> -->\n\n<!-- 正确 -->\n<view class="my-class" src="{{url}}" />',
            })
    
    return results


# ===== MP-008 API域名白名单完整性 =====
def check_mp_008_webview_domain_whitelist(context) -> List[Dict]:
    """MP-008 API域名白名单完整性
    
    检测逻辑：
    1. 扫描所有web-view组件的src属性中的URL
    2. 提取域名
    3. 检查是否在app.json的businessDomain或代码中的白名单配置中
    4. 不在白名单→warning
    """
    results = []
    
    if not context.project_path:
        return results
    
    wxml_files = context.find_files([".wxml"])
    if not wxml_files:
        return results
    
    # 1. 从app.json中提取webView域名白名单
    allowed_domains = set()
    
    app_json_path = os.path.join(context.project_path, 'app.json')
    app_json_content = context.safe_read(app_json_path)
    if app_json_content:
        try:
            app_config = json.loads(app_json_content)
            # 微信的businessDomain配置
            biz_domains = app_config.get('bizDomain', {})
            if isinstance(biz_domains, dict):
                for key in ['webview', 'webView', 'businessDomain']:
                    domains = biz_domains.get(key, [])
                    if isinstance(domains, list):
                        allowed_domains.update(domains)
            
            # 也检查navigateToMiniProgramAppIdList等
        except json.JSONDecodeError:  # noqa: intentional empty handler
            pass
    
    # 2. 从JS代码中提取ALLOWED_DOMAINS白名单
    js_files = context.find_files([".js"])
    for fpath in js_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        # 查找白名单定义
        whitelist_patterns = [
            re.compile(r'(?:ALLOWED_DOMAINS|allowedDomains|whiteList|白名单)\s*[=:]\s*\[([^\]]+)\]', re.IGNORECASE),
            re.compile(r'(?:webViewWhitelist|domainWhitelist)\s*[=:]\s*\[([^\]]+)\]', re.IGNORECASE),
        ]
        
        for pattern in whitelist_patterns:
            for m in pattern.finditer(content):
                domains_str = m.group(1)
                # 提取域名
                domain_matches = re.findall(r'["\']([^"\']+)["\']', domains_str)
                allowed_domains.update(domain_matches)
    
    # 3. 扫描web-view的src
    webview_pattern = re.compile(r'<web-view[^>]*\bsrc\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE | re.DOTALL)
    
    for fpath in wxml_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        for m in webview_pattern.finditer(content):
            url = m.group(1)
            line_num = content[:m.start()].count('\n') + 1
            
            # 提取域名
            domain = _extract_domain(url)
            if not domain:
                continue
            
            # 检查是否在白名单中
            is_allowed = False
            if domain in allowed_domains:
                is_allowed = True
            else:
                # 检查是否匹配通配符域名（如 *.example.com）
                for allowed in allowed_domains:
                    if allowed.startswith('*.'):
                        base_domain = allowed[2:]
                        if domain.endswith(base_domain):
                            is_allowed = True
                            break
            
            if not is_allowed:
                rel_path = os.path.relpath(fpath, context.project_path) if context.project_path else fpath
                results.append({
                    'id': 'MP-008',
                    'name': 'API域名白名单完整性',
                    'level': 'warning',
                    'message': f'web-view引用的域名 {domain} 未在白名单中配置',
                    'detail': f'文件: {rel_path}:{line_num}\nURL: {url[:100]}\n已配置的白名单域名: {", ".join(sorted(allowed_domains)[:10]) if allowed_domains else "无"}',
                    'file': fpath,
                    'line': line_num,
                    'fix': '在app.json的bizDomain.webview或代码白名单中添加该域名，或在微信后台配置业务域名',
                    'suggestion_code': f'// 在app.json中添加:\n{{\n  "bizDomain": {{\n    "webview": ["{domain}"]\n  }}\n}}\n// 或在微信后台 → 开发管理 → 业务域名中添加: {domain}',
                })
    
    return results


def _extract_domain(url: str) -> Optional[str]:
    """从URL中提取域名"""
    # 处理 {{}} 数据绑定的URL
    if '{{' in url:
        return None  # 动态URL无法静态分析
    
    # 提取域名
    domain_pattern = re.compile(r'https?://([^/\s:]+)', re.IGNORECASE)
    m = domain_pattern.search(url)
    if m:
        return m.group(1).lower()
    
    # 相对路径或无协议
    if url.startswith('//'):
        domain_pattern2 = re.compile(r'^//([^/\s:]+)')
        m2 = domain_pattern2.search(url)
        if m2:
            return m2.group(1).lower()
    
    return None


# ===== 规则定义列表 =====


# ===== 规则定义列表 =====
RULES = [
        {
            'id': 'MP-005',
            'name': '图片懒加载建议',
            'level': 'suggestion',
            'category': 'wxml',
            'module_id': '12',
            'applicable_types': ['miniprogram', 'mixed'],
            'description': '长列表中的图片建议使用lazy-load属性（AST增强：精准识别image标签）',
            'check': check_mp_005_image_lazy,
        },
        {
            'id': 'MP-006',
            'name': 'WXML禁止调用JS函数',
            'level': 'blocking',
            'category': 'wxml',
            'module_id': '2',
            'applicable_types': ['miniprogram', 'mixed'],
            'description': 'WXML的{{}}表达式中不允许直接调用JS函数，只能使用WXS模块或数据绑定',
            'check': check_mp_006_no_js_call_in_wxml,
        },
        {
            'id': 'MP-007',
            'name': 'WXML属性值必须加引号',
            'level': 'problem',
            'category': 'wxml',
            'module_id': '2',
            'applicable_types': ['miniprogram', 'mixed'],
            'description': '检查WXML标签的所有属性值是否有引号包裹',
            'check': check_mp_007_attr_must_quote,
        },
        {
            'id': 'MP-008',
            'name': 'API域名白名单完整性',
            'level': 'problem',
            'category': 'wxml',
            'module_id': '2',
            'applicable_types': ['miniprogram', 'mixed'],
            'description': '检查web-view引用的URL域名是否在业务域名白名单中配置',
            'check': check_mp_008_webview_domain_whitelist,
        },
]
