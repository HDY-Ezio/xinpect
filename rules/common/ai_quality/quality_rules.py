"""
智能质检 - P1 质量问题规则 (4条)
AI时代常见的代码质量问题

AI-QUAL-01: 上帝函数 - 函数超过80行
AI-QUAL-02: 深度嵌套 - 嵌套超过4层
AI-QUAL-03: 复制粘贴克隆 - 连续20行以上重复代码块
AI-QUAL-04: 模糊错误信息 - "Something went wrong"这类无意义错误文案
"""

import re
import os
import ast
from typing import List, Dict, Any


# ===== AI-QUAL-01 上帝函数 =====
def check_ai_qual_01_god_function(context) -> List[Dict]:
    """AI-QUAL-01 上帝函数检测
    函数超过80行，AI生成代码常把所有逻辑塞在一个函数里
    """
    results = []
    
    py_files = [f for f in context.get_filtered_files("performance")
                if f.endswith(".py") and os.path.basename(f) != "__init__.py"]
    js_files = [f for f in context.get_filtered_files("performance") if f.endswith((".js", ".ts", ".jsx", ".tsx"))]
    
    if not py_files and not js_files:
        return results
    
    # 获取配置中的阈值
    ai_config = context.config.get('ai_code_check', {})
    max_function_lines = ai_config.get('max_function_lines', 80)
    
    all_issues = []
    
    # ===== Python 检测 =====
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        lines = content.split('\n')
        rel = os.path.relpath(fpath, context.project_path or context.backend_path or ".")
        
        try:
            tree = context.parse_ast(fpath)
            if tree is None:
                continue
            
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                
                # 计算函数行数
                func_lines = node.end_lineno - node.lineno + 1
                
                if func_lines > max_function_lines:
                    all_issues.append({
                        'file': fpath,
                        'rel': rel,
                        'line': node.lineno,
                        'desc': f'函数 "{node.name}" 有 {func_lines} 行（超过 {max_function_lines} 行阈值）',
                        'snippet': lines[node.lineno - 1].strip() if node.lineno - 1 < len(lines) else "",
                    })
        except SyntaxError:
            continue
    
    # ===== JS/TS 检测（正则简化版）=====
    for fpath in js_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        lines = content.split('\n')
        rel = os.path.relpath(fpath, context.project_path or context.backend_path or ".")
        basename = os.path.basename(fpath)
        
        if any(x in basename.lower() for x in ['.test.', '.spec.']):
            continue
        
        # 简单的函数定义匹配
        # function name(...) {
        # const name = (...) => {
        func_pattern = re.compile(
            r'^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?'
            r'(?:function\s+(\w+)|'
            r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>)'
            r'\s*\{',
            re.MULTILINE
        )
        
        for m in func_pattern.finditer(content):
            func_name = m.group(1) or m.group(2) or 'anonymous'
            start_line = content[:m.start()].count('\n') + 1
            start_pos = m.end() - 1  # { 的位置
            
            # 找匹配的 }
            depth = 1
            pos = start_pos + 1
            while pos < len(content) and depth > 0:
                if content[pos] == '{':
                    depth += 1
                elif content[pos] == '}':
                    depth -= 1
                pos += 1
            
            if depth > 0:
                continue
            
            end_pos = pos - 1
            end_line = content[:end_pos].count('\n') + 1
            func_lines = end_line - start_line + 1
            
            if func_lines > max_function_lines:
                all_issues.append({
                    'file': fpath,
                    'rel': rel,
                    'line': start_line,
                    'desc': f'函数 "{func_name}" 有 {func_lines} 行（超过 {max_function_lines} 行阈值）',
                    'snippet': lines[start_line - 1].strip() if start_line - 1 < len(lines) else "",
                })
    
    if all_issues:
        total = len(all_issues)
        # 按行数降序
        all_issues.sort(key=lambda x: int(re.search(r'有 (\d+) 行', x['desc']).group(1)) 
                       if re.search(r'有 (\d+) 行', x['desc']) else 0, reverse=True)
        
        detail_lines = [
            f"{issue['rel']}:{issue['line']} - {issue['desc']}"
            for issue in all_issues[:15]
        ]
        
        results.append({
            'id': 'AI-QUAL-01',
            'name': '上帝函数检测',
            'level': 'warning',  # 中危
            'message': f'发现 {total} 个超大函数（超过 {max_function_lines} 行）',
            'detail': '\n'.join(detail_lines),
            'file': all_issues[0]['file'] if all_issues else '',
            'line': all_issues[0]['line'] if all_issues else 0,
            'snippet': all_issues[0]['snippet'] if all_issues else '',
            'fix': '拆分为多个职责单一的小函数，每个函数只做一件事',
            'category': 'ai_quality',
        })
    
    return results


# ===== AI-QUAL-02 深度嵌套 =====
def check_ai_qual_02_deep_nesting(context) -> List[Dict]:
    """AI-QUAL-02 深度嵌套检测
    嵌套超过4层，AI生成代码常有过多嵌套
    """
    results = []
    
    py_files = [f for f in context.get_filtered_files("performance")
                if f.endswith(".py") and os.path.basename(f) != "__init__.py"]
    js_files = [f for f in context.get_filtered_files("performance") if f.endswith((".js", ".ts", ".jsx", ".tsx"))]
    
    if not py_files and not js_files:
        return results
    
    ai_config = context.config.get('ai_code_check', {})
    max_nesting_depth = ai_config.get('max_nesting_depth', 4)
    
    all_issues = []
    
    # ===== Python 检测（用AST更准确）=====
    def calc_py_nesting(node, depth=0):
        """计算Python AST的最大嵌套深度"""
        max_depth = depth
        
        # 会增加嵌套的节点类型
        nesting_types = (
            ast.If, ast.For, ast.While, ast.Try,
            ast.FunctionDef, ast.AsyncFunctionDef,
            ast.With,
        )
        
        for child in ast.iter_child_nodes(node):
            if isinstance(child, nesting_types):
                child_depth = calc_py_nesting(child, depth + 1)
                max_depth = max(max_depth, child_depth)
            else:
                child_depth = calc_py_nesting(child, depth)
                max_depth = max(max_depth, child_depth)
        
        return max_depth
    
    def find_deep_nesting_py(node, depth=0, max_depth=4, results_list=None, lines=None):
        """找到深度嵌套的具体位置"""
        if results_list is None:
            results_list = []
        
        nesting_types = (
            ast.If, ast.For, ast.While, ast.Try, ast.With,
        )
        
        for child in ast.iter_child_nodes(node):
            if isinstance(child, nesting_types):
                new_depth = depth + 1
                if new_depth > max_depth:
                    results_list.append({
                        'line': child.lineno,
                        'depth': new_depth,
                        'type': type(child).__name__,
                        'snippet': lines[child.lineno - 1].strip() if child.lineno - 1 < len(lines) else "",
                    })
                find_deep_nesting_py(child, new_depth, max_depth, results_list, lines)
            else:
                find_deep_nesting_py(child, depth, max_depth, results_list, lines)
        
        return results_list
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        lines = content.split('\n')
        rel = os.path.relpath(fpath, context.project_path or context.backend_path or ".")
        
        try:
            tree = context.parse_ast(fpath)
            if tree is None:
                continue
            
            # 先计算最大深度
            max_depth = calc_py_nesting(tree)
            
            if max_depth > max_nesting_depth:
                # 找到具体的深度嵌套位置
                deep_spots = find_deep_nesting_py(tree, 0, max_nesting_depth, lines=lines)
                
                # 每个文件最多报3处
                for spot in deep_spots[:3]:
                    all_issues.append({
                        'file': fpath,
                        'rel': rel,
                        'line': spot['line'],
                        'desc': f'嵌套深度 {spot["depth"]} 层（超过 {max_nesting_depth} 层阈值）',
                        'snippet': spot['snippet'],
                    })
        except SyntaxError:
            continue
    
    # ===== JS/TS 检测（简化版，基于缩进）=====
    for fpath in js_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        lines = content.split('\n')
        rel = os.path.relpath(fpath, context.project_path or context.backend_path or ".")
        basename = os.path.basename(fpath)
        
        if any(x in basename.lower() for x in ['.test.', '.spec.']):
            continue
        
        # 用大括号深度计算（简化版）
        max_depth = 0
        max_depth_line = 0
        current_depth = 0
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # 跳过注释行
            if stripped.startswith('//'):
                continue
            if stripped.startswith('/*') or stripped.startswith('*'):
                continue
            
            # 统计大括号
            for ch in line:
                if ch == '{':
                    current_depth += 1
                    if current_depth > max_depth:
                        max_depth = current_depth
                        max_depth_line = i + 1
                elif ch == '}':
                    current_depth = max(0, current_depth - 1)
        
        # JS的大括号深度比Python的嵌套层级多（函数体也算一层）
        # 所以阈值适当放宽
        js_threshold = max_nesting_depth + 2  # 函数体+顶层+...
        
        if max_depth > js_threshold:
            actual_nesting = max_depth - 2  # 减去函数体等基础层级
            all_issues.append({
                'file': fpath,
                'rel': rel,
                'line': max_depth_line,
                'desc': f'最大嵌套深度约 {actual_nesting} 层（超过 {max_nesting_depth} 层阈值）',
                'snippet': lines[max_depth_line - 1].strip() if max_depth_line - 1 < len(lines) else "",
            })
    
    if all_issues:
        total = len(all_issues)
        detail_lines = [
            f"{issue['rel']}:{issue['line']} - {issue['desc']}"
            for issue in all_issues[:15]
        ]
        
        results.append({
            'id': 'AI-QUAL-02',
            'name': '深度嵌套检测',
            'level': 'warning',  # 中危
            'message': f'发现 {total} 处深度嵌套（超过 {max_nesting_depth} 层）',
            'detail': '\n'.join(detail_lines),
            'file': all_issues[0]['file'] if all_issues else '',
            'line': all_issues[0]['line'] if all_issues else 0,
            'snippet': all_issues[0]['snippet'] if all_issues else '',
            'fix': '使用提前返回、提取函数、卫语句等方式降低嵌套深度',
            'category': 'ai_quality',
        })
    
    return results


# ===== AI-QUAL-03 复制粘贴克隆 =====
def check_ai_qual_03_code_duplication(context) -> List[Dict]:
    """AI-QUAL-03 复制粘贴克隆检测
    连续20行以上重复代码块（简化版）
    AI生成代码常大量复制粘贴
    """
    results = []
    
    all_files = context.get_filtered_files("performance")
    if not all_files:
        return results
    
    ai_config = context.config.get('ai_code_check', {})
    min_dup_lines = ai_config.get('min_duplication_lines', 20)
    
    all_issues = []
    
    # 读取所有文件内容，按行存储
    file_lines = {}
    for fpath in all_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        basename = os.path.basename(fpath)
        if basename.startswith('__') or basename.startswith('.'):
            continue
        lines = content.split('\n')
        # 过滤空行和纯注释行
        meaningful_lines = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith('#') or stripped.startswith('//'):
                continue
            if stripped.startswith('/*') or stripped.startswith('*'):
                continue
            meaningful_lines.append((i + 1, stripped))  # (行号, 内容)
        if len(meaningful_lines) >= min_dup_lines:
            file_lines[fpath] = meaningful_lines
    
    # 简单的重复检测：对每个文件，检查是否有重复的连续行块
    # 简化版：只检测同一个文件内的重复
    for fpath, meaningful in file_lines.items():
        rel = os.path.relpath(fpath, context.project_path or context.backend_path or ".")
        
        # 用哈希检测重复块
        # 对每一行开始的min_dup_lines行计算一个指纹
        seen_blocks = {}  # {fingerprint: first_line}
        
        for i in range(len(meaningful) - min_dup_lines + 1):
            # 计算块指纹（用行内容拼接的哈希）
            block_lines = [meaningful[i + j][1] for j in range(min_dup_lines)]
            fingerprint = '\n'.join(block_lines)
            
            if fingerprint in seen_blocks:
                first_line = seen_blocks[fingerprint]
                current_line = meaningful[i][0]
                
                # 同一个块不重复报告
                all_issues.append({
                    'file': fpath,
                    'rel': rel,
                    'line': current_line,
                    'desc': f'重复代码块（{min_dup_lines}行以上，首次出现在第{first_line}行）',
                    'snippet': block_lines[0][:80] if block_lines else "",
                })
                break  # 每个文件最多报一处
            else:
                seen_blocks[fingerprint] = meaningful[i][0]
    
    if all_issues:
        total = len(all_issues)
        detail_lines = [
            f"{issue['rel']}:{issue['line']} - {issue['desc']}"
            for issue in all_issues[:10]
        ]
        
        results.append({
            'id': 'AI-QUAL-03',
            'name': '复制粘贴克隆检测',
            'level': 'warning',  # 中危
            'message': f'发现 {total} 处重复代码块（{min_dup_lines}行以上）',
            'detail': '\n'.join(detail_lines),
            'file': all_issues[0]['file'] if all_issues else '',
            'line': all_issues[0]['line'] if all_issues else 0,
            'snippet': all_issues[0]['snippet'] if all_issues else '',
            'fix': '抽取公共逻辑为函数/组件，避免复制粘贴',
            'category': 'ai_quality',
        })
    
    return results


# ===== AI-QUAL-04 模糊错误信息 =====
def check_ai_qual_04_vague_errors(context) -> List[Dict]:
    """AI-QUAL-04 模糊错误信息检测
    "Something went wrong"这类无意义错误文案
    AI生成代码常写模糊的错误信息
    """
    results = []
    
    all_files = context.get_filtered_files("performance")
    if not all_files:
        return results
    
    # 常见的模糊错误信息模式
    vague_error_patterns = [
        (r'(?:throw|raise)\s+[\'"](?:Something went wrong|出错了|发生错误|有问题|未知错误|出问题了)[\'"]',
         '模糊错误信息（直接抛出无意义字符串）'),
        (r'(?:throw\s+new\s+Error|raise\s+Exception|raise\s+ValueError|raise\s+RuntimeError)\s*\(\s*["\'](?:Something went wrong|出错了|发生了错误|有问题|未知错误|出问题了|出错了，请重试|An error occurred|发生一个错误)["\']',
         '模糊错误信息（"Something went wrong"类无意义错误）'),
        (r'(?:throw\s+new\s+Error|raise\s+Exception)\s*\(\s*["\'](?:Error|错误|Failed|失败|Something wrong)[\'"]\s*\)',
         '模糊错误信息（仅"错误/失败"无具体描述）'),
    ]
    
    all_issues = []
    
    for fpath in all_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        lines = content.split('\n')
        rel = os.path.relpath(fpath, context.project_path or context.backend_path or ".")
        basename = os.path.basename(fpath)
        
        # 跳过测试文件
        if any(x in basename.lower() for x in ['test', 'spec', 'fixture', 'mock']):
            continue
        
        for pat, desc in vague_error_patterns:
            for m in re.finditer(pat, content, re.IGNORECASE):
                line_num = content[:m.start()].count('\n') + 1
                line_content = lines[line_num - 1].strip() if line_num - 1 < len(lines) else ""
                
                # 跳过注释行
                stripped = line_content.strip()
                if fpath.endswith('.py') and stripped.startswith('#'):
                    continue
                if fpath.endswith(('.js', '.ts', '.jsx', '.tsx')) and stripped.startswith('//'):
                    continue
                
                all_issues.append({
                    'file': fpath,
                    'rel': rel,
                    'line': line_num,
                    'desc': desc,
                    'snippet': line_content[:100],
                })
    
    if all_issues:
        total = len(all_issues)
        detail_lines = [
            f"{issue['rel']}:{issue['line']} - {issue['desc']}"
            for issue in all_issues[:15]
        ]
        
        results.append({
            'id': 'AI-QUAL-04',
            'name': '模糊错误信息检测',
            'level': 'info',  # 提示
            'message': f'发现 {total} 处模糊错误信息（无具体描述）',
            'detail': '\n'.join(detail_lines),
            'file': all_issues[0]['file'] if all_issues else '',
            'line': all_issues[0]['line'] if all_issues else 0,
            'snippet': all_issues[0]['snippet'] if all_issues else '',
            'fix': '错误信息应包含具体原因和上下文，帮助用户和开发者定位问题',
            'category': 'ai_quality',
        })
    
    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'AI-QUAL-01',
        'name': '上帝函数检测',
        'level': 'problem',
        'category': 'ai_code_check',
        'module_id': 'ai_quality',
        'applicable_types': [],
        'description': '检测超过80行的超大函数（AI生成代码常把所有逻辑塞在一个函数里）',
        'check': check_ai_qual_01_god_function,
    },
    {
        'id': 'AI-QUAL-02',
        'name': '深度嵌套检测',
        'level': 'problem',
        'category': 'ai_code_check',
        'module_id': 'ai_quality',
        'applicable_types': [],
        'description': '检测嵌套超过4层的代码块（AI生成代码常有过多嵌套）',
        'check': check_ai_qual_02_deep_nesting,
    },
    {
        'id': 'AI-QUAL-03',
        'name': '复制粘贴克隆检测',
        'level': 'problem',
        'category': 'ai_code_check',
        'module_id': 'ai_quality',
        'applicable_types': [],
        'description': '检测连续20行以上的重复代码块（AI生成代码常大量复制粘贴）',
        'check': check_ai_qual_03_code_duplication,
    },
    {
        'id': 'AI-QUAL-04',
        'name': '模糊错误信息检测',
        'level': 'suggestion',
        'category': 'ai_code_check',
        'module_id': 'ai_quality',
        'applicable_types': [],
        'description': '检测"Something went wrong"这类无意义的模糊错误文案',
        'check': check_ai_qual_04_vague_errors,
    },
]
