"""
Agent/LLM应用安全规则集 - 提示词与数据安全 (M14)
LLM/Agent应用专项安全检查 - 通用提示词与数据安全类
包含: 系统提示词敏感信息、硬编码API密钥、工具权限、不可信输入、输出验证

来源标准: OWASP LLM Top 10 2025 / 虾评四维检测
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


def check_llm_sec_001_prompt_sensitive_info(context) -> List[Dict]:
    """LLM-SEC-001 系统提示词敏感信息检测 - 检查系统提示词中是否包含密钥、内部逻辑等敏感信息"""
    results = []
    
    # 查找提示词相关文件
    prompt_files = []
    all_files = context.find_files([".md", ".txt", ".py", ".json", ".yaml", ".yml"])
    
    for fpath in all_files:
        basename = os.path.basename(fpath).lower()
        if any(k in basename for k in ['prompt', 'system', 'instruction', '角色', '提示', 'skll', 'skill']):
            prompt_files.append(fpath)
    
    # 也检查Python代码中的大段prompt定义
    py_files = context.find_files([".py"])
    for fpath in py_files:
        if _is_skippable_file(fpath):
            continue
        content = context.safe_read(fpath)
        if re.search(r'(system_prompt|system_message|base_prompt|prompt_template|SYSTEM_PROMPT)\s*=', content):
            prompt_files.append(fpath)
    
    sensitive_patterns = [
        (r'(api[_-]?key|secret|token|password)\s*[:=]\s*["\'][^"\']{8,}["\']', '硬编码凭证'),
        (r'(sk-[a-zA-Z0-9]{20,}|AKIA[0-9A-Z]{16})', 'API密钥'),
        (r'内部规则|内部逻辑|禁止泄露|保密.*规则', '内部业务规则'),
        (r'(真实姓名|身份证|手机号|银行卡|家庭住址)\s*[:：]\s*[^，\n]{2,}', '个人敏感信息'),
    ]
    
    issues = []
    for fpath in prompt_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if _is_comment_line(line):
                continue
            
            for pattern, desc in sensitive_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    issues.append({
                        'file': fpath,
                        'line': i,
                        'desc': desc,
                        'snippet': line.strip()[:80],
                    })
                    break  # 每行只报一次
    
    if issues:
        results.append({
            'id': 'LLM-SEC-001',
            'name': '系统提示词敏感信息检测',
            'level': 'error',
            'message': f'检测到 {len(issues)} 处系统提示词中包含敏感信息',
            'detail': '示例: ' + '; '.join(f"{os.path.basename(i['file'])}:{i['line']} {i['desc']}" for i in issues[:5]),
            'file': issues[0]['file'],
            'line': issues[0]['line'],
            'snippet': issues[0]['snippet'],
            'fix': '将敏感信息从提示词中移除，通过环境变量或凭证系统注入；业务规则用通用描述替代具体细节',
            'category': 'llm_security',
        })
    
    return results


# ============================================================
# LLM-SEC-002: LLM API密钥硬编码检测（增强版）
# ============================================================
def check_llm_sec_002_hardcoded_api_key(context) -> List[Dict]:
    """LLM-SEC-002 LLM API密钥硬编码检测 - 检测OpenAI/Anthropic/Google等LLM服务商的API密钥"""
    results = []
    
    all_files = context.find_files([".py", ".js", ".ts", ".jsx", ".tsx", ".env", ".json", ".yaml", ".yml"])
    
    # LLM服务商密钥模式
    key_patterns = [
        (r'sk-[a-zA-Z0-9]{20,}', 'OpenAI API Key'),
        (r'sk-proj-[a-zA-Z0-9]{20,}', 'OpenAI Project Key'),
        (r'antsk_[a-zA-Z0-9]{20,}', 'Anthropic API Key'),
        (r'AIza[0-9A-Za-z\-_]{35}', 'Google API Key'),
        (r'api-?[a-z0-9]{20,}', '通用API Key'),
        (r'Bearer\s+[a-zA-Z0-9_\-]{20,}', 'Bearer Token (硬编码)'),
    ]
    
    issues = []
    for fpath in all_files:
        if _is_skippable_file(fpath):
            continue
        
        # 跳过.env.example等示例文件
        basename = os.path.basename(fpath).lower()
        if '.env' in basename and any(x in basename for x in ['example', 'sample', 'template']):
            continue
        
        content = context.safe_read(fpath)
        if not content:
            continue
        
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if _is_comment_line(line):
                continue
            
            for pattern, desc in key_patterns:
                matches = re.findall(pattern, line)
                if matches:
                    # 排除占位符和示例值
                    first_match = matches[0]
                    if any(x in first_match.lower() for x in ['xxxx', 'your_', 'example', 'placeholder', 'test_key']):
                        continue
                    if any(x in line.lower() for x in ['xxx', 'your_', 'example', 'placeholder', 'replace']):
                        continue
                    
                    issues.append({
                        'file': fpath,
                        'line': i,
                        'desc': desc,
                        'snippet': line.strip()[:60],
                    })
                    break  # 每行只报一次
    
    if issues:
        results.append({
            'id': 'LLM-SEC-002',
            'name': 'LLM API密钥硬编码检测',
            'level': 'error',
            'message': f'检测到 {len(issues)} 处硬编码的LLM API密钥',
            'detail': '示例: ' + '; '.join(f"{os.path.basename(i['file'])}:{i['line']}" for i in issues[:5]),
            'file': issues[0]['file'],
            'line': issues[0]['line'],
            'snippet': issues[0]['snippet'],
            'fix': '将API密钥移至环境变量或凭证管理系统，代码中通过os.environ/凭证变量读取',
            'category': 'llm_security',
        })
    
    return results


# ============================================================
# LLM-SEC-003: Agent工具权限最小化检测
# ============================================================
def check_llm_sec_003_tool_permission(context) -> List[Dict]:
    """LLM-SEC-003 Agent工具权限最小化检测 - 检查工具权限是否遵循最小权限原则"""
    results = []
    
    all_py_files = context.find_files([".py"])
    if not all_py_files:
        return results
    
    # 检测模式：工具定义中是否授予了过宽权限
    risky_patterns = [
        (r'tools?\s*[:=]\s*\[?\s*["\']all["\']', '授予了全部工具权限(all)'),
        (r'permission[s]?\s*[:=]\s*["\'].*full.*["\']', '授予了完全权限(full)'),
        (r'grant.*all.*access|allow.*all.*tool', '授予了所有工具访问权'),
        (r'file_access\s*[:=]\s*["\'].*write.*["\']', '文件写权限(需确认必要性)'),
        (r'network_access\s*[:=]\s*["\'].*all.*["\']', '全网络访问权限'),
        (r'shell_access\s*[:=]\s*True|allow_shell\s*[:=]\s*True', 'Shell执行权限'),
    ]
    
    issues = []
    for fpath in all_py_files:
        if _is_skippable_file(fpath):
            continue
        content = context.safe_read(fpath)
        if not content:
            continue
        
        # 只检查包含agent/tool/skill相关代码的文件
        if not re.search(r'agent|tool|skill|plugin|function.*call', content, re.IGNORECASE):
            continue
        
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if _is_comment_line(line):
                continue
            
            for pattern, desc in risky_patterns:
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
            'id': 'LLM-SEC-003',
            'name': 'Agent工具权限最小化检测',
            'level': 'warning',
            'message': f'检测到 {len(issues)} 处工具权限配置可能违反最小权限原则',
            'detail': '示例: ' + '; '.join(f"{os.path.basename(i['file'])}:{i['line']} {i['desc']}" for i in issues[:5]),
            'file': issues[0]['file'],
            'line': issues[0]['line'],
            'snippet': issues[0]['snippet'],
            'fix': '遵循最小权限原则，仅授予完成任务所需的工具和权限，避免使用all/full等通配权限',
            'category': 'llm_security',
        })
    
    return results


# ============================================================
# LLM-SEC-004: 外部输入直接信任检测（间接提示注入）
# ============================================================
def check_llm_sec_004_untrusted_input(context) -> List[Dict]:
    """LLM-SEC-004 外部输入直接信任检测 - 检查用户/工具/文档输入是否被直接送入LLM而无过滤"""
    results = []
    
    all_py_files = context.find_files([".py"])
    if not all_py_files:
        return results
    
    # 检测外部输入源直接拼接到prompt中的模式
    risky_patterns = [
        # 用户输入直接进入prompt
        (r'prompt.*\+.*user[_-]?input|user[_-]?input.*\+.*prompt', '用户输入直接拼接prompt'),
        (r'f["\'][^"\']*\{.*(user_input|user_msg|message|query).*\}.*prompt', 'f-string中用户输入直接进入prompt'),
        # 工具返回直接进入prompt
        (r'tool[_-]?result.*\+.*prompt|prompt.*\+.*tool[_-]?output', '工具输出直接拼接prompt'),
        # 知识库/RAG文档直接进入prompt
        (r'(rag_content|retrieved_docs|knowledge_base|context_docs).*\+.*prompt', 'RAG文档直接拼接prompt'),
    ]
    
    issues = []
    for fpath in all_py_files:
        if _is_skippable_file(fpath):
            continue
        content = context.safe_read(fpath)
        if not content:
            continue
        
        # 只检查包含LLM调用的文件
        if not re.search(r'chat\.completions|openai|anthropic|llm|model\.generate|client\.chat', content, re.IGNORECASE):
            continue
        
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if _is_comment_line(line):
                continue
            
            for pattern, desc in risky_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    # 检查附近是否有过滤/验证
                    ctx_start = max(0, i - 6)
                    ctx_end = min(len(lines), i + 2)
                    ctx = '\n'.join(lines[ctx_start:ctx_end])
                    has_sanitize = bool(re.search(
                        r'sanitize|filter|validate|escape|strip_html|remove.*instruction|ignore.*previous',
                        ctx, re.IGNORECASE))
                    
                    if not has_sanitize:
                        issues.append({
                            'file': fpath,
                            'line': i,
                            'desc': desc,
                            'snippet': line.strip()[:80],
                        })
                        break
    
    if issues:
        results.append({
            'id': 'LLM-SEC-004',
            'name': '外部输入直接信任检测',
            'level': 'warning',
            'message': f'检测到 {len(issues)} 处外部输入可能直接送入LLM（间接提示注入风险）',
            'detail': '示例: ' + '; '.join(f"{os.path.basename(i['file'])}:{i['line']}" for i in issues[:5]),
            'file': issues[0]['file'],
            'line': issues[0]['line'],
            'snippet': issues[0]['snippet'],
            'fix': '对用户输入、工具返回、RAG文档等外部内容进行过滤净化，添加安全指令前缀隔离',
            'category': 'llm_security',
        })
    
    return results


# ============================================================
# LLM-SEC-005: LLM输出未验证直接传入危险API
# ============================================================
def check_llm_sec_005_output_validation(context) -> List[Dict]:
    """LLM-SEC-005 LLM输出未验证直接传入危险API - 检查LLM输出是否直接传给数据库/Shell/文件系统"""
    results = []
    
    all_py_files = context.find_files([".py"])
    if not all_py_files:
        return results
    
    # 危险API列表
    dangerous_apis = [
        # 数据库操作
        (r'(execute|query|cursor\.execute)\s*\([^)]*(response|result|content|completion|llm_).*[,)]',
         'LLM输出直接传入SQL执行', 'SQL注入'),
        # 系统命令执行
        (r'(os\.system|subprocess\.(run|Popen|call)|eval|exec)\s*\([^)]*(response|result|content|llm_|ai_).*[,)]',
         'LLM输出直接传入系统命令执行', '命令注入'),
        # 文件系统操作
        (r'(open\s*\([^)]*(response|result|content|llm_)|file_path\s*=.*response)',
         'LLM输出直接控制文件路径', '路径穿越'),
        # 网络请求
        (r'(requests\.(get|post)|urllib\.request)\s*\([^)]*(response|result|content|llm_).*http',
         'LLM输出直接控制请求URL', 'SSRF'),
    ]
    
    issues = []
    for fpath in all_py_files:
        if _is_skippable_file(fpath):
            continue
        content = context.safe_read(fpath)
        if not content:
            continue
        
        # 只检查包含LLM调用的文件
        if not re.search(r'chat\.completions|openai|anthropic|llm|model\.generate|client\.chat', content, re.IGNORECASE):
            continue
        
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if _is_comment_line(line):
                continue

            # Skip if line has # safe: comment (case-insensitive)
            if '# safe' in line.lower():
                continue

            for pattern, desc, risk in dangerous_apis:
                if re.search(pattern, line, re.IGNORECASE):
                    issues.append({
                        'file': fpath,
                        'line': i,
                        'desc': desc,
                        'risk': risk,
                        'snippet': line.strip()[:80],
                    })
                    break
    
    if issues:
        results.append({
            'id': 'LLM-SEC-005',
            'name': 'LLM输出未验证直接传入危险API',
            'level': 'error',
            'message': f'检测到 {len(issues)} 处LLM输出未验证直接传入危险API',
            'detail': '示例: ' + '; '.join(f"{os.path.basename(i['file'])}:{i['line']} {i['desc']}" for i in issues[:5]),
            'file': issues[0]['file'],
            'line': issues[0]['line'],
            'snippet': issues[0]['snippet'],
            'fix': 'LLM输出在传入数据库/Shell/文件系统前必须经过严格的白名单校验、类型转换和格式验证',
            'category': 'llm_security',
        })
    
    return results


# ============================================================
# COZE-001: 技能代码中真实个人信息检测
# ============================================================


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'LLM-SEC-001',
        'name': '系统提示词敏感信息检测',
        'level': 'blocking',
        'category': 'llm_security',
        'module_id': '14',
        'applicable_types': ['agent', 'skill'],
        'description': '检查系统提示词中是否包含密钥、内部业务规则等敏感信息（LLM07 System Prompt Leakage）',
        'check': check_llm_sec_001_prompt_sensitive_info,
    },
    {
        'id': 'LLM-SEC-002',
        'name': 'LLM API密钥硬编码检测',
        'level': 'blocking',
        'category': 'llm_security',
        'module_id': '14',
        'applicable_types': ['agent', 'skill', 'python', 'python_backend', 'python_tool', 'flask', 'mixed', 'mixed_electron'],
        'description': '检测OpenAI/Anthropic/Google等LLM服务商的硬编码API密钥（LLM02/LLM03）',
        'check': check_llm_sec_002_hardcoded_api_key,
    },
    {
        'id': 'LLM-SEC-003',
        'name': 'Agent工具权限最小化检测',
        'level': 'blocking',
        'category': 'llm_security',
        'module_id': '14',
        'applicable_types': ['agent', 'skill'],
        'description': '检查Agent工具权限是否遵循最小权限原则（LLM06 Excessive Agency）',
        'check': check_llm_sec_003_tool_permission,
    },
    {
        'id': 'LLM-SEC-004',
        'name': '外部输入直接信任检测',
        'level': 'blocking',
        'category': 'llm_security',
        'module_id': '14',
        'applicable_types': ['agent', 'skill', 'python_backend', 'python_tool', 'flask'],
        'description': '检查用户/工具/文档输入是否被直接送入LLM而无过滤（LLM01 Prompt Injection）',
        'check': check_llm_sec_004_untrusted_input,
    },
    {
        'id': 'LLM-SEC-005',
        'name': 'LLM输出未验证直接传入危险API',
        'level': 'blocking',
        'category': 'llm_security',
        'module_id': '14',
        'applicable_types': ['agent', 'skill', 'python_backend', 'python_tool', 'flask'],
        'description': '检查LLM输出是否直接传给数据库/Shell/文件系统等危险API（LLM05 Improper Output Handling）',
        'check': check_llm_sec_005_output_validation,
    },
]
