"""
AI质检 P0 安全规则 - 密钥与注入检测 (AI-SEC)
从 security_rules.py 拆分而来，包含:
  AI-SEC-01 硬编码密钥扫描 - API Key、Token、密码、数据库连接串写在代码/注释里
  AI-SEC-04 SQL注入风险 - 字符串拼接SQL语句（f-string、+号拼接）
"""

import re
import os
import ast
from typing import List, Dict, Any

# v4.6.1: AI-SEC-01 模块级预编译正则与工具函数，避免每次调用重复工作
_SECRET_PATTERNS_RAW = [
    # API Key / Secret Key
    (r'(?:api[_-]?key|apikey|api[_-]?secret|secret[_-]?key|client[_-]?secret)\s*[:=]\s*["\']([a-zA-Z0-9_\-]{20,})["\']',
     '硬编码API密钥', 'high'),
    # Token / Access Token
    (r'(?:access[_-]?token|auth[_-]?token|bearer[_-]?token|refresh[_-]?token)\s*[:=]\s*["\']([a-zA-Z0-9_\-\.]{20,})["\']',
     '硬编码Token', 'high'),
    # 密码
    (r'(?:password|passwd|pwd|db[_-]?password)\s*[:=]\s*["\']([^"\']{8,})["\']',
     '硬编码密码', 'high'),
    # 数据库连接串
    (r'(?:mysql|postgres|postgresql|mongodb|redis)://[^"\']*:([^"\'@/]+)@',
     '数据库连接串含密码', 'high'),
    # OpenAI / 大模型 API Key
    (r'(?:sk-|sk-proj-|pk-)[a-zA-Z0-9]{20,}',
     'OpenAI风格API Key', 'high'),
    # AWS Key
    (r'AKIA[0-9A-Z]{16}',
     'AWS Access Key', 'high'),
    # 私钥
    (r'-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----',
     '私钥文件内容', 'high'),
    # JWT Token (长的)
    (r'eyJ[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+',
     'JWT Token', 'medium'),
]

# 预编译正则（模块加载时一次性完成，避免每次调用 re.compile）
_SECRET_COMPILED = [
    (re.compile(pat, re.IGNORECASE), desc, sev)
    for pat, desc, sev in _SECRET_PATTERNS_RAW
]

# 安全值标记（预计算 frozenset，in 操作 O(1)）
_SAFE_VALUE_MARKERS = frozenset([
    'xxx', 'your_', 'example', 'placeholder', 'test',
    'replace_me', 'changeme', 'dummy', 'sample', 'demo',
    'todo', 'none', 'null', 'undefined', 'false', 'true',
    'default', 'config', 'set_me', 'enter_your',
])


def _is_safe_value(value: str) -> bool:
    """判断值是否为安全占位符/测试值"""
    v = value.lower().strip()
    if len(v) < 10:
        return True
    for marker in _SAFE_VALUE_MARKERS:
        if marker in v:
            return True
    return False


def _is_safe_context(file_path: str, line_content: str) -> bool:
    """判断行是否在安全上下文中（注释、环境变量读取等）"""
    basename = os.path.basename(file_path).lower()
    
    # 跳过测试/示例文件
    if any(x in basename for x in ['test', 'spec', 'example', 'sample', 'demo', 'mock', 'fixture']):
        return True
    
    # 跳过配置模板
    if any(x in basename for x in ['.example', '.sample', '.template', '.tpl']):
        return True
    
    stripped = line_content.strip()
    
    # Python 文件：跳过纯注释行
    if file_path.endswith('.py'):
        if stripped.startswith('#'):
            return True
    
    # JS/TS 文件：跳过纯注释行
    if file_path.endswith(('.js', '.ts', '.jsx', '.tsx')):
        if stripped.startswith(('//', '*', '/*')):
            return True
    
    # 从环境变量读取
    if 'os.environ' in line_content or 'os.getenv' in line_content or 'process.env' in line_content:
        return True
    
    # 配置读取
    if re.search(r'(?:get_config|load_config|from_config|config\.get|settings\.)', line_content):
        return True
    
    return False


def _build_line_offsets(text: str) -> tuple:
    """一次性构建行偏移表和行列表，用于 O(log n) 行号查找
    
    返回: (lines_list, offsets_list)
    """
    lines = text.split('\n')
    offsets = [0]
    pos = 0
    for line in lines[:-1]:
        pos += len(line) + 1
        offsets.append(pos)
    return lines, offsets


def check_ai_sec_01_hardcoded_secrets(context) -> List[Dict]:
    """AI-SEC-01 硬编码密钥扫描
    检测AI生成代码中常见的密钥硬编码问题，包括代码和注释中的
    
    v4.6.1 性能优化：
    1. 正则预编译到模块级（每次调用省 9 次 re.compile）
    2. 行偏移表 + bisect 二分查找替代 count('\\n')，O(n) -> O(log n)
    3. 安全值白名单改为 frozenset，in 操作 O(1)
    4. 短文件快速跳过（< 20 字节不可能有密钥）
    5. is_safe_context 改为独立函数，减少闭包开销
    """
    import bisect
    results = []
    
    all_files = context.get_filtered_files("security")
    if not all_files:
        return results
    
    for fpath in all_files:
        content = context.safe_read(fpath)
        if not content or len(content) < 20:
            continue
        
        # 一次性构建行列表和行偏移表
        lines, line_offsets = _build_line_offsets(content)
        
        for pat, desc, severity in _SECRET_COMPILED:
            found = False
            for m in pat.finditer(content):
                # 二分查找行号（O(log n) 替代 O(n) count）
                line_idx = bisect.bisect_right(line_offsets, m.start()) - 1
                if line_idx < 0:
                    line_idx = 0
                line_num = line_idx + 1
                line_content = lines[line_idx] if line_idx < len(lines) else ""
                
                # 安全上下文过滤
                if _is_safe_context(fpath, line_content):
                    continue
                
                # 安全值过滤
                matched_value = m.group(1) if m.groups() else m.group(0)
                if _is_safe_value(matched_value):
                    continue
                
                results.append({
                    'id': 'AI-SEC-01',
                    'name': '硬编码密钥扫描',
                    'level': 'error',
                    'message': f'检测到硬编码敏感信息: {desc}',
                    'detail': f'文件: {os.path.relpath(fpath, context.project_path or context.backend_path or ".")}',
                    'file': fpath,
                    'line': line_num,
                    'snippet': line_content.strip()[:100],
                    'fix': '将密钥移至环境变量或配置文件，代码中只读取不存储',
                    'category': 'ai_security',
                })
                found = True
                break  # 每个文件每个模式只报一次
            # 如果第一个模式（最常见的 API Key）就找到了，可以考虑不跳过其他模式
            # 保持原行为：每个模式独立检查
    
    return results



# ===== AI-SEC-02 裸异常捕获 =====


def check_ai_sec_04_sql_injection(context) -> List[Dict]:
    """AI-SEC-04 SQL注入风险检测
    AI生成代码常见：用f-string或+号拼接SQL语句
    比通用规则更严格，专门检测AI常犯的模式
    """
    results = []
    
    all_files = []
    py_files = [f for f in context.find_files([".py"])
                if os.path.basename(f) != "__init__.py"]
    js_files = [f for f in context.get_filtered_files("security") if f.endswith((".js", ".ts", ".jsx", ".tsx"))]
    all_files = py_files + js_files
    
    if not all_files:
        return results
    
    all_issues = []
    
    # Python SQL注入模式（更全面，覆盖AI常生成的模式）
    py_sql_patterns = [
        # f-string拼接SQL
        (r'f["\']\s*(SELECT|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER)\s+.*?\{.*?\}',
         'f-string拼接SQL语句', 'high'),
        # +号拼接SQL
        (r'["\']\s*(SELECT|INSERT|UPDATE|DELETE)\s+[^"\']*["\']\s*\+\s*\w+',
         '+号拼接SQL语句', 'high'),
        # format拼接
        (r'["\']\s*(SELECT|INSERT|UPDATE|DELETE)\s+[^"\']*["\']\.format\s*\(',
         '.format()拼接SQL语句', 'high'),
        # %格式化
        (r'["\']\s*(SELECT|INSERT|UPDATE|DELETE)\s+[^"\']*["\']\s*%\s*[\(\w]',
         '%格式化SQL语句', 'high'),
    ]
    
    # JS SQL注入模式
    js_sql_patterns = [
        # 模板字符串拼接SQL
        (r'`\s*(SELECT|INSERT|UPDATE|DELETE|CREATE|DROP)\s+.*?\$\{.*?\}',
         '模板字符串拼接SQL语句', 'high'),
        # +号拼接SQL
        (r'["\']\s*(SELECT|INSERT|UPDATE|DELETE)\s+[^"\']*["\']\s*\+\s*\w+',
         '+号拼接SQL语句', 'high'),
    ]
    
    def is_safe_sql_context(line: str, content: str, fpath: str, lines: list = None, line_num: int = 0) -> bool:
        """检查是否是安全的SQL上下文（不是真正的SQL注入）"""
        lower_line = line.lower()

        # 1. # safe: 注释标记（大小写不敏感）
        if '# safe' in lower_line:
            return True

        # 在注释中
        stripped = line.strip()
        if fpath.endswith('.py') and stripped.startswith('#'):
            return True
        if fpath.endswith(('.js', '.ts', '.jsx', '.tsx')) and stripped.startswith(('//', '*', '/*')):
            return True

        # 是docstring/注释中的示例SQL
        if 'example' in lower_line or 'e.g.' in lower_line or '例如' in line:
            return True

        # 是测试文件中的
        basename = os.path.basename(fpath).lower()
        if any(x in basename for x in ['test', 'spec', 'fixture', 'mock']):
            return True

        # 2. 参数化查询检测：如果同一行或上下文中有 execute(%s) 或 execute(?)
        # 说明 f-string 只是构造 SQL 模板，参数通过占位符传入
        if lines and line_num > 0:
            start_line = max(0, line_num - 5)
            end_line = min(len(lines), line_num + 5)
            ctx_lines = lines[start_line:end_line]
            ctx_text = '\n'.join(ctx_lines)
            # 检查是否有参数化执行迹象
            if re.search(r'\.execute\s*\([^)]*%s', ctx_text) or \
               re.search(r'\.execute\s*\([^)]*\?', ctx_text) or \
               re.search(r'cursor\.execute.*%s', ctx_text) or \
               re.search(r'execute.*params\s*=', ctx_text):
                return True

        # 3. 非 SQL 执行上下文：f-string 包含 SQL 关键词但不是 SQL 语句
        # 常见误报：logger.info(f"...UPDATE..."), response_error(f"...DELETE...")
        # 检查 f-string 是否传给了非 execute 的函数调用
        non_sql_contexts = [
            'logger.', 'logging.', 'print(', 'console.',
            'response_error', 'response_success', 'response_',
            'raise ', 'return f"', 'return f\'',
            'wx.showtoast', 'showtoast',
            'change_summary', 'summary',
        ]
        for ns_ctx in non_sql_contexts:
            if ns_ctx in lower_line:
                return True

        # 检查 f-string 是否只包含 SQL 关键词但实际是日志/消息
        # 模式：f"...UPDATE xxx..." 但 UPDATE 不是 SQL 语句开头
        # 如果 f-string 前面有非 SQL 函数调用，跳过
        if re.search(r'(logger|log|print|raise|return|wx\.|response|summary|toast|msg|message)\s*[\.(]\s*f["\']', line, re.IGNORECASE):
            return True

        return False
    
    # 检查Python文件
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        lines = content.split('\n')
        rel = os.path.relpath(fpath, context.project_path or context.backend_path or ".")
        
        for pat, desc, severity in py_sql_patterns:
            for m in re.finditer(pat, content, re.IGNORECASE):
                line_num = content[:m.start()].count('\n') + 1
                line_content = lines[line_num - 1] if line_num - 1 < len(lines) else ""
                
                if is_safe_sql_context(line_content, content, fpath, lines, line_num):
                    continue
                
                # 检查附近是否有参数化查询的迹象（如果是纯拼接就报）
                # 取上下文
                start_line = max(0, line_num - 3)
                end_line = min(len(lines), line_num + 3)
                ctx = '\n'.join(lines[start_line:end_line])
                
                # 如果有参数化执行的迹象（%s, ?, execute），且是构造SQL字符串变量
                # 这种可能是AI生成的危险代码，但要结合上下文判断
                # 保守策略：只要检测到字符串拼接SQL就报
                # 但如果是用ORM的filter等方法的不算（已由SQL关键字过滤）
                
                all_issues.append({
                    'file': fpath,
                    'rel': rel,
                    'line': line_num,
                    'desc': desc,
                    'snippet': line_content.strip()[:120],
                    'severity': severity,
                })
    
    # 检查JS文件
    for fpath in js_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        lines = content.split('\n')
        rel = os.path.relpath(fpath, context.project_path or context.backend_path or ".")
        
        for pat, desc, severity in js_sql_patterns:
            for m in re.finditer(pat, content, re.IGNORECASE):
                line_num = content[:m.start()].count('\n') + 1
                line_content = lines[line_num - 1] if line_num - 1 < len(lines) else ""
                
                if is_safe_sql_context(line_content, content, fpath, lines, line_num):
                    continue
                
                all_issues.append({
                    'file': fpath,
                    'rel': rel,
                    'line': line_num,
                    'desc': desc,
                    'snippet': line_content.strip()[:120],
                    'severity': severity,
                })
    
    if all_issues:
        total = len(all_issues)
        detail_lines = [
            f"{issue['rel']}:{issue['line']} - {issue['desc']}"
            for issue in all_issues[:15]
        ]
        
        results.append({
            'id': 'AI-SEC-04',
            'name': 'SQL注入风险',
            'level': 'error',  # 高危
            'message': f'发现 {total} 处SQL注入风险（字符串拼接SQL语句）',
            'detail': '\n'.join(detail_lines),
            'file': all_issues[0]['file'] if all_issues else '',
            'line': all_issues[0]['line'] if all_issues else 0,
            'snippet': all_issues[0]['snippet'] if all_issues else '',
            'fix': '使用参数化查询(prepared statement)，不要用字符串拼接构造SQL',
            'category': 'ai_security',
        })
    
    return results


# ===== AI-SEC-05 静默失败 =====


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'AI-SEC-01',
        'name': '硬编码密钥扫描',
        'level': 'blocking',
        'category': 'ai_code_check',
        'module_id': 'ai_security',
        'applicable_types': [],
        'description': '检测AI生成代码中常见的密钥硬编码问题，包括API Key、Token、密码、数据库连接串等',
        'check': check_ai_sec_01_hardcoded_secrets,
    },
    {
        'id': 'AI-SEC-04',
        'name': 'SQL注入风险',
        'level': 'blocking',
        'category': 'ai_code_check',
        'module_id': 'ai_security',
        'applicable_types': [],
        'description': '检测AI生成代码常见的字符串拼接SQL语句（f-string、+号、模板字符串）',
        'check': check_ai_sec_04_sql_injection,
    },
]
