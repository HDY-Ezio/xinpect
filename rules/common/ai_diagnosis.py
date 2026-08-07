"""
AI深度诊断规则集 (M18) - 简化版
AI深度诊断静态规则 - 适用于所有项目类型
基于模式匹配的深度代码质量分析，覆盖逻辑漏洞、性能瓶颈、设计缺陷等
包含: 逻辑漏洞分析、性能瓶颈识别、设计缺陷诊断、深度安全检查等4项检查
注意：完整LLM深度诊断能力保留在旧模块中，本文件仅包含可静态分析的规则
"""

import re
import os
from typing import List, Dict, Any


# ===== 工具函数 =====
def _get_all_code_files(context) -> List[str]:
    """获取所有代码文件"""
    all_files = []
    if context.project_path and os.path.isdir(context.project_path):
        if context.is_web_frontend():
            all_files += context.find_files([".js", ".ts", ".tsx", ".jsx"])
        else:
            all_files += context.find_files([".js", ".wxml"])
    all_files += context.get_backend_py_files()
    return all_files


# ===== 快速模式规则配置 =====
# 逻辑漏洞模式
LOGIC_ISSUE_PATTERNS = [
    (r'\bif\s+.*\s*==\s*None\b', "可能缺少None判断的边界处理", "logic"),
    (r'\.get\([^)]+\)\s*\.', "链式调用可能因None报错，建议增加空值保护", "logic"),
    (r'dict\(.*\)\[', "字典直接访问可能KeyError，建议用get()", "logic"),
    (r'\bglobal\s+\w+', "全局变量可能导致状态不一致", "logic"),
    (r'\bnonlocal\s+\w+', "nonlocal变量可能导致闭包状态问题", "logic"),
]

# 性能问题模式
PERFORMANCE_ISSUE_PATTERNS = [
    (r'\.index\(', "list.index()在循环中使用可能导致O(n²)", "performance"),
    (r'\.\s*count\(', "list.count()在循环中使用可能导致O(n²)", "performance"),
    (r'len\(\w+\)\s*in\s*range', "循环中重复调用len()", "performance"),
    (r'\.read\(\)', "全量读取文件可能导致大内存占用", "performance"),
]

# 设计问题模式
DESIGN_ISSUE_PATTERNS = [
    (r'def\s+\w+\s*\([^)]{80,}\)', "函数参数过多，可能职责不单一", "design"),
    (r'import\s+\.\.', "相对导入过深，可能耦合问题", "design"),
    (r'from\s+\.\.\.', "三层以上相对导入，模块耦合度高", "design"),
]

# 深度安全问题模式
SECURITY_DEEP_PATTERNS = [
    (r'\beval\s*\(', "eval()使用存在代码注入风险", "security"),
    (r'\bexec\s*\(', "exec()使用存在代码执行风险", "security"),
    (r'pickle\.loads', "反序列化不可信数据存在代码执行风险", "security"),
    (r'subprocess\.(call|run|Popen)\(.*shell\s*=\s*True', "shell=True存在命令注入风险", "security"),
    (r'print\s*\(.*password', "密码等敏感信息打印到日志", "security"),
    (r'logging\..*\(.*password', "敏感信息写入日志", "security"),
]


# ===== 18.1 代码上下文收集 =====
def check_18_1_code_context_collection(context) -> List[Dict]:
    """18.1 代码上下文收集 - 统计代码规模和复杂度概况"""
    results = []
    
    code_files = _get_all_code_files(context)
    if not code_files:
        results.append({
            'id': '18.1',
            'name': '代码上下文收集',
            'level': 'suggestion',
            'message': '无代码文件可供分析',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    total_files = len(code_files)
    total_lines = 0
    total_funcs = 0
    
    for f in code_files:
        content = context.safe_read(f)
        if not content:
            continue
        total_lines += len(content.split('\n'))
        if f.endswith('.py'):
            total_funcs += len(re.findall(r'^\s*def\s+\w+\s*\(', content, re.MULTILINE))
        else:
            total_funcs += len(re.findall(r'function\s+\w+\s*\(', content, re.MULTILINE))
            total_funcs += len(re.findall(r'const\s+\w+\s*=\s*(async\s+)?\([^)]*\)\s*=>', content, re.MULTILINE))
    
    results.append({
        'id': '18.1',
        'name': '代码上下文收集',
        'level': 'suggestion',
        'message': f'已收集 {total_files} 个文件，约 {total_lines} 行代码，{total_funcs} 个函数',
        'file': '',
        'line': 0,
        'snippet': f'文件数: {total_files}\n代码行数: {total_lines}\n函数数: {total_funcs}',
        'fix': '',
    })
    
    return results


# ===== 18.2 逻辑漏洞深度分析 =====
def check_18_2_logic_issues(context) -> List[Dict]:
    """18.2 逻辑漏洞深度分析 - 基于模式匹配检测潜在逻辑问题"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        results.append({
            'id': '18.2',
            'name': '逻辑漏洞深度分析',
            'level': 'suggestion',
            'message': '无Python后端代码，跳过深度逻辑分析',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    findings = []
    files_with_issues = set()
    
    for f in py_files[:50]:  # 抽样
        content = context.safe_read(f)
        if not content:
            continue
        lines = content.split('\n')
        
        for pattern, desc, category in LOGIC_ISSUE_PATTERNS:
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                # 跳过注释
                if stripped.startswith('#') or stripped.startswith('//'):
                    continue
                if re.search(pattern, line):
                    files_with_issues.add(f)
                    if len(findings) < 15:
                        try:
                            rel = os.path.relpath(f)
                        except ValueError:
                            rel = f
                        findings.append(f"{os.path.basename(rel)}:{i} [{category}] {desc}")
                    break  # 每个文件每个模式只报一次
    
    issue_count = len(files_with_issues)
    
    if issue_count > 10:
        level = 'problem'
        message = f'发现 {issue_count} 个文件存在潜在逻辑问题'
    elif issue_count > 0:
        level = 'suggestion'
        message = f'发现 {issue_count} 个文件存在潜在逻辑问题（需人工确认）'
    else:
        level = 'suggestion'
        message = '未发现明显的深层逻辑漏洞'
    
    results.append({
        'id': '18.2',
        'name': '逻辑漏洞深度分析',
        'level': level,
        'message': message,
        'file': '',
        'line': 0,
        'snippet': '\n'.join(findings[:10]),
        'fix': '逐一审查标记的潜在逻辑问题，确保边界条件处理正确',
    })
    
    return results


# ===== 18.3 性能瓶颈识别 =====
def check_18_3_performance_bottlenecks(context) -> List[Dict]:
    """18.3 性能瓶颈识别 - 检测可能导致性能问题的代码模式"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        results.append({
            'id': '18.3',
            'name': '性能瓶颈识别',
            'level': 'suggestion',
            'message': '无Python后端代码，跳过性能分析',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    findings = []
    files_with_issues = set()
    
    for f in py_files[:50]:
        content = context.safe_read(f)
        if not content:
            continue
        lines = content.split('\n')
        
        # 检测嵌套循环（O(n²)模式）
        nested_loop_count = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            # 检查嵌套for循环
            if re.match(r'^\s*for\s+\w+\s+in\s+', stripped):
                # 检查后面50行内是否有另一个for循环（缩进更深）
                indent = len(line) - len(line.lstrip())
                for j in range(i+1, min(i+30, len(lines))):
                    inner_line = lines[j]
                    inner_indent = len(inner_line) - len(inner_line.lstrip())
                    if inner_indent > indent and re.match(r'^\s*for\s+\w+\s+in\s+', inner_line.strip()):
                        nested_loop_count += 1
                        if len(findings) < 10:
                            try:
                                rel = os.path.relpath(f)
                            except ValueError:
                                rel = f
                            findings.append(f"{os.path.basename(rel)}:{i+1} [performance] 嵌套循环可能存在O(n²)性能问题")
                        files_with_issues.add(f)
                        break
        
        for pattern, desc, category in PERFORMANCE_ISSUE_PATTERNS:
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith('#'):
                    continue
                if re.search(pattern, line):
                    files_with_issues.add(f)
                    if len(findings) < 15:
                        try:
                            rel = os.path.relpath(f)
                        except ValueError:
                            rel = f
                        findings.append(f"{os.path.basename(rel)}:{i} [{category}] {desc}")
                    break
    
    issue_count = len(files_with_issues)
    
    if issue_count > 5:
        level = 'problem'
        message = f'发现 {issue_count} 个文件存在潜在性能瓶颈'
    elif issue_count > 0:
        level = 'suggestion'
        message = f'发现 {issue_count} 个文件存在潜在性能问题（需人工确认）'
    else:
        level = 'suggestion'
        message = '未发现明显的性能瓶颈模式'
    
    results.append({
        'id': '18.3',
        'name': '性能瓶颈识别',
        'level': level,
        'message': message,
        'file': '',
        'line': 0,
        'snippet': '\n'.join(findings[:10]),
        'fix': '对性能瓶颈进行基准测试，优化热点路径',
    })
    
    return results


# ===== 18.4 设计缺陷诊断 =====
def check_18_4_design_issues(context) -> List[Dict]:
    """18.4 设计缺陷诊断 - 检测代码设计问题和耦合度过高的模式"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        results.append({
            'id': '18.4',
            'name': '设计缺陷诊断',
            'level': 'suggestion',
            'message': '无Python后端代码，跳过设计分析',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    findings = []
    files_with_issues = set()
    
    for f in py_files[:50]:
        content = context.safe_read(f)
        if not content:
            continue
        lines = content.split('\n')
        
        # 检测过长函数（>50行）
        try:
            import ast
            _sum = context.get_ast_summary(f)
            if not _sum:
                continue
            for _f_info in _sum.get('functions', []):
                node = _f_info['node']
                if True:
                    func_lines = node.end_lineno - node.lineno if hasattr(node, 'end_lineno') else 0
                    if func_lines > 80:
                        files_with_issues.add(f)
                        if len(findings) < 10:
                            try:
                                rel = os.path.relpath(f)
                            except ValueError:
                                rel = f
                            findings.append(f"{os.path.basename(rel)}:{node.lineno} [design] 函数{node.name}过长({func_lines}行)")
        except (SyntaxError, ImportError):  # noqa: intentional empty handler
            pass
        
        for pattern, desc, category in DESIGN_ISSUE_PATTERNS:
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith('#'):
                    continue
                if re.search(pattern, line):
                    files_with_issues.add(f)
                    if len(findings) < 15:
                        try:
                            rel = os.path.relpath(f)
                        except ValueError:
                            rel = f
                        findings.append(f"{os.path.basename(rel)}:{i} [{category}] {desc}")
                    break
    
    issue_count = len(files_with_issues)
    
    if issue_count > 5:
        level = 'problem'
        message = f'发现 {issue_count} 个文件存在设计改进点'
    elif issue_count > 0:
        level = 'suggestion'
        message = f'发现 {issue_count} 个文件存在潜在设计问题（需人工确认）'
    else:
        level = 'suggestion'
        message = '整体设计合理，未发现明显设计缺陷'
    
    results.append({
        'id': '18.4',
        'name': '设计缺陷诊断',
        'level': level,
        'message': message,
        'file': '',
        'line': 0,
        'snippet': '\n'.join(findings[:10]),
        'fix': '结合架构设计原则进行重构优化，降低耦合度',
    })
    
    return results


# ===== 18.5 深度安全与架构建议 =====
def check_18_5_deep_security_arch(context) -> List[Dict]:
    """18.5 深度安全与架构建议 - 检测深层安全问题和架构改进点"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        results.append({
            'id': '18.5',
            'name': '深度安全与架构建议',
            'level': 'suggestion',
            'message': '无Python后端代码，跳过深度安全检查',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    findings = []
    files_with_critical = set()
    files_with_warning = set()
    
    for f in py_files[:50]:
        content = context.safe_read(f)
        if not content:
            continue
        lines = content.split('\n')
        
        for pattern, desc, category in SECURITY_DEEP_PATTERNS:
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith('#'):
                    continue
                if re.search(pattern, line, re.IGNORECASE):
                    # 高危安全问题
                    if any(kw in desc for kw in ['注入', '执行', '反序列化']):
                        files_with_critical.add(f)
                    else:
                        files_with_warning.add(f)
                    if len(findings) < 15:
                        try:
                            rel = os.path.relpath(f)
                        except ValueError:
                            rel = f
                        findings.append(f"{os.path.basename(rel)}:{i} [{category}] {desc}")
                    break
    
    critical_count = len(files_with_critical)
    warning_count = len(files_with_warning)
    total = critical_count + warning_count
    
    if critical_count > 0:
        level = 'blocking'
        message = f'发现 {critical_count} 个文件存在高危安全问题，{warning_count} 个文件存在安全隐患'
    elif warning_count > 3:
        level = 'problem'
        message = f'发现 {warning_count} 个文件存在安全隐患'
    elif warning_count > 0:
        level = 'suggestion'
        message = f'发现 {warning_count} 个安全相关问题（需人工确认）'
    else:
        level = 'suggestion'
        message = '架构整体健康，未发现深层安全隐患'
    
    results.append({
        'id': '18.5',
        'name': '深度安全与架构建议',
        'level': level,
        'message': message,
        'file': '',
        'line': 0,
        'snippet': '\n'.join(findings[:10]),
        'fix': '根据优先级逐步修复安全问题，使用安全的API替代危险函数',
    })
    
    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': '18.1',
        'name': '代码上下文收集',
        'level': 'suggestion',
        'category': 'ai_diagnosis',
        'module_id': '18',
        'applicable_types': [],
        'description': '收集代码规模和复杂度概况，为深度诊断提供上下文',
        'check': check_18_1_code_context_collection,
    },
    {
        'id': '18.2',
        'name': '逻辑漏洞深度分析',
        'level': 'problem',
        'category': 'ai_diagnosis',
        'module_id': '18',
        'applicable_types': ['python_backend', 'python_tool', 'flask', 'mixed', 'mixed_electron'],
        'description': '基于模式匹配检测潜在逻辑漏洞（空值、边界条件、状态一致性等）',
        'check': check_18_2_logic_issues,
    },
    {
        'id': '18.3',
        'name': '性能瓶颈识别',
        'level': 'problem',
        'category': 'ai_diagnosis',
        'module_id': '18',
        'applicable_types': ['python_backend', 'python_tool', 'flask', 'mixed', 'mixed_electron'],
        'description': '检测可能导致性能问题的代码模式（嵌套循环、重复计算等）',
        'check': check_18_3_performance_bottlenecks,
    },
    {
        'id': '18.4',
        'name': '设计缺陷诊断',
        'level': 'problem',
        'category': 'ai_diagnosis',
        'module_id': '18',
        'applicable_types': ['python_backend', 'python_tool', 'flask', 'mixed', 'mixed_electron'],
        'description': '检测代码设计问题（过长函数、高耦合、职责不单一等）',
        'check': check_18_4_design_issues,
    },
    {
        'id': '18.5',
        'name': '深度安全与架构建议',
        'level': 'blocking',
        'category': 'ai_diagnosis',
        'module_id': '18',
        'applicable_types': ['python_backend', 'python_tool', 'flask', 'mixed', 'mixed_electron'],
        'description': '深度安全检查（eval/exec/反序列化/shell注入等高危模式）',
        'check': check_18_5_deep_security_arch,
    },
]
