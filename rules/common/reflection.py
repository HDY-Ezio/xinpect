"""
反思验证规则集 (M16) - 简化版
代码质量反思检查 - 适用于所有项目类型
通过静态分析检测代码中可能被遗漏的质量问题
包含: TODO密度、临时代码检测、注释密度、重复模式检测等4项检查
注意：完整AI反思能力保留在旧模块中，本文件仅包含可静态检查的规则
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


# ===== 16.1 TODO/FIXME密度检查 =====
def check_16_1_todo_density(context) -> List[Dict]:
    """16.1 TODO/FIXME密度检查 - 统计待办事项，识别技术债务密度"""
    results = []
    
    code_files = _get_all_code_files(context)
    if not code_files:
        results.append({
            'id': '16.1',
            'name': 'TODO/FIXME密度',
            'level': 'suggestion',
            'message': '无代码文件，跳过检查',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    todo_count = 0
    fixme_count = 0
    hack_count = 0
    total_lines = 0
    todo_examples = []
    
    todo_pattern = re.compile(r'(TODO|FIXME|HACK|XXX|BUG)\s*[:\-]?\s*(.*)', re.IGNORECASE)
    
    for f in code_files:
        content = context.safe_read(f)
        if not content:
            continue
        lines = content.split('\n')
        total_lines += len(lines)
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            # 只检查注释行
            if not (stripped.startswith('#') or stripped.startswith('//') or 
                    stripped.startswith('*') or '/*' in stripped or '#' in stripped):
                # 检查行内注释中的TODO
                if '//' in stripped and 'TODO' in stripped.upper():
                    pass  # 仍然检查
                elif '#' in stripped and 'TODO' in stripped.upper() and f.endswith('.py'):
                    pass  # 仍然检查
                else:
                    continue
            
            m = todo_pattern.search(stripped)
            if m:
                tag = m.group(1).upper()
                desc = m.group(2).strip()[:60]
                if tag == 'TODO':
                    todo_count += 1
                elif tag == 'FIXME':
                    fixme_count += 1
                elif tag in ('HACK', 'XXX', 'BUG'):
                    hack_count += 1
                
                if len(todo_examples) < 5:
                    try:
                        rel = os.path.relpath(f)
                    except ValueError:
                        rel = f
                    todo_examples.append(f"{os.path.basename(rel)}:{i} [{tag}] {desc}")
    
    total_todos = todo_count + fixme_count + hack_count
    
    if total_lines == 0:
        density = 0
    else:
        density = total_todos / total_lines * 1000  # per 1000 lines
    
    if density > 20:  # 每千行超过20个待办
        level = 'problem'
        message = f'TODO密度较高: {total_todos}个待办({density:.1f}/千行) - {todo_count}TODO/{fixme_count}FIXME/{hack_count}HACK'
    elif density > 10:
        level = 'suggestion'
        message = f'TODO密度适中: {total_todos}个待办({density:.1f}/千行)'
    else:
        level = 'suggestion'
        message = f'技术债务低: {total_todos}个待办({density:.1f}/千行)'
    
    results.append({
        'id': '16.1',
        'name': 'TODO/FIXME密度',
        'level': level,
        'message': message,
        'file': '',
        'line': 0,
        'snippet': '\n'.join(todo_examples) if todo_examples else '',
        'fix': '优先处理FIXME和HACK标记的技术债务',
    })
    
    return results


# ===== 16.2 临时代码检测 =====
def check_16_2_temp_code_detection(context) -> List[Dict]:
    """16.2 临时代码检测 - 检测临时实现、硬编码值和调试残留"""
    results = []
    
    code_files = _get_all_code_files(context)
    if not code_files:
        results.append({
            'id': '16.2',
            'name': '临时代码检测',
            'level': 'suggestion',
            'message': '无代码文件，跳过检查',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    temp_patterns = [
        (r'\btemp\b.*=.*\btemp\b', '临时变量命名'),
        (r'\bquick.*fix\b|\bquickfix\b', '快速修复标记'),
        (r'\bworkaround\b', '绕过方案'),
        (r'\btemporary\b|\btmp_\w+', '临时实现'),
        (r'\bnot.*implemented\b|\bplaceholder\b', '未实现占位'),
        (r'debugger\s*;', '调试器断点'),
        (r'console\.(log|debug|warn)\s*\(\s*["\']?(debug|test|temp)', '调试日志'),
    ]
    
    findings = []
    files_with_temp = set()
    
    for f in code_files:
        content = context.safe_read(f)
        if not content:
            continue
        for pattern, desc in temp_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                files_with_temp.add(f)
                if len(findings) < 10:
                    try:
                        rel = os.path.relpath(f)
                    except ValueError:
                        rel = f
                    findings.append(f"{os.path.basename(rel)}: {desc}")
                break
    
    if len(files_with_temp) > 5:
        level = 'problem'
        message = f'发现{len(files_with_temp)}个文件包含临时代码标记'
    elif len(files_with_temp) > 0:
        level = 'suggestion'
        message = f'发现{len(files_with_temp)}个文件包含临时代码标记'
    else:
        level = 'suggestion'
        message = '未发现明显的临时代码标记'
    
    results.append({
        'id': '16.2',
        'name': '临时代码检测',
        'level': level,
        'message': message,
        'file': '',
        'line': 0,
        'snippet': '\n'.join(findings[:10]),
        'fix': '清理临时代码，使用正式实现替代',
    })
    
    return results


# ===== 16.3 注释密度检查 =====
def check_16_3_comment_density(context) -> List[Dict]:
    """16.3 注释密度检查 - 评估代码可读性和可维护性"""
    results = []
    
    py_files = context.get_backend_py_files()
    js_files = _get_all_code_files(context)
    all_files = list(set(py_files + js_files))
    
    if not all_files:
        results.append({
            'id': '16.3',
            'name': '注释密度',
            'level': 'suggestion',
            'message': '无代码文件，跳过检查',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    total_lines = 0
    comment_lines = 0
    files_low_comment = []
    
    for f in all_files[:50]:  # 抽样检查前50个文件
        content = context.safe_read(f)
        if not content:
            continue
        lines = content.split('\n')
        file_lines = len(lines)
        file_comments = 0
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if f.endswith('.py'):
                if stripped.startswith('#') or stripped.startswith('"""') or stripped.startswith("'''"):
                    file_comments += 1
            else:
                if (stripped.startswith('//') or stripped.startswith('/*') or 
                    stripped.startswith('*') or stripped.startswith('*/')):
                    file_comments += 1
        
        total_lines += file_lines
        comment_lines += file_comments
        
        if file_lines > 50 and file_comments / file_lines < 0.05:
            try:
                rel = os.path.relpath(f)
            except ValueError:
                rel = f
            files_low_comment.append(f"{os.path.basename(rel)} ({file_comments}/{file_lines}行)")
    
    if total_lines == 0:
        density = 0
    else:
        density = comment_lines / total_lines * 100
    
    if density < 3:
        level = 'problem'
        message = f'注释密度偏低: {density:.1f}% ({comment_lines}/{total_lines}行)'
    elif density < 5:
        level = 'suggestion'
        message = f'注释密度略低: {density:.1f}% ({comment_lines}/{total_lines}行)'
    else:
        level = 'suggestion'
        message = f'注释密度正常: {density:.1f}% ({comment_lines}/{total_lines}行)'
    
    results.append({
        'id': '16.3',
        'name': '注释密度',
        'level': level,
        'message': message,
        'file': '',
        'line': 0,
        'snippet': f'低注释文件({len(files_low_comment)}个):\n' + '\n'.join(files_low_comment[:5]) if files_low_comment else '',
        'fix': '为复杂逻辑添加注释，提高代码可维护性',
    })
    
    return results


# ===== 16.4 命名一致性检查 =====
def check_16_4_naming_consistency(context) -> List[Dict]:
    """16.4 命名一致性检查 - 检测变量/函数命名风格是否统一"""
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        results.append({
            'id': '16.4',
            'name': '命名一致性',
            'level': 'suggestion',
            'message': '无Python代码，跳过检查',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    # 检测函数命名风格
    snake_case_funcs = 0
    camel_case_funcs = 0
    inconsistent_files = []
    
    func_pattern = re.compile(r'^\s*def\s+(\w+)\s*\(', re.MULTILINE)
    
    for f in py_files[:30]:  # 抽样
        content = context.safe_read(f)
        if not content:
            continue
        
        funcs = func_pattern.findall(content)
        if len(funcs) < 3:
            continue
        
        file_snake = 0
        file_camel = 0
        for func_name in funcs:
            if func_name.startswith('_'):
                continue  # 跳过私有方法
            if '_' in func_name:
                file_snake += 1
            elif func_name[0].islower() and any(c.isupper() for c in func_name):
                file_camel += 1
        
        snake_case_funcs += file_snake
        camel_case_funcs += file_camel
        
        if file_snake > 0 and file_camel > 0:
            # 同一文件内混用
            ratio = min(file_snake, file_camel) / max(file_snake, file_camel)
            if ratio > 0.3:  # 超过30%的混用
                try:
                    rel = os.path.relpath(f)
                except ValueError:
                    rel = f
                inconsistent_files.append(f"{os.path.basename(rel)}: {file_snake}蛇形/{file_camel}驼峰")
    
    total = snake_case_funcs + camel_case_funcs
    if total == 0:
        level = 'suggestion'
        message = '未检测到足够的函数命名样本'
    elif camel_case_funcs == 0:
        level = 'suggestion'
        message = f'命名风格统一: 全部使用蛇形命名({snake_case_funcs}个函数)'
    elif snake_case_funcs == 0:
        level = 'suggestion'
        message = f'命名风格: 全部使用驼峰命名({camel_case_funcs}个函数)'
    else:
        ratio = camel_case_funcs / total
        if ratio > 0.2:
            level = 'problem'
            message = f'命名风格不一致: {snake_case_funcs}个蛇形 vs {camel_case_funcs}个驼峰 ({ratio:.0%}混用)'
        else:
            level = 'suggestion'
            message = f'命名风格基本一致: {snake_case_funcs}个蛇形 vs {camel_case_funcs}个驼峰'
    
    results.append({
        'id': '16.4',
        'name': '命名一致性',
        'level': level,
        'message': message,
        'file': '',
        'line': 0,
        'snippet': f'混用文件({len(inconsistent_files)}个):\n' + '\n'.join(inconsistent_files[:5]) if inconsistent_files else '',
        'fix': '统一使用蛇形命名（Python推荐）或驼峰命名，保持风格一致',
    })
    
    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': '16.1',
        'name': 'TODO/FIXME密度',
        'level': 'suggestion',
        'category': 'reflection',
        'module_id': '16',
        'applicable_types': [],
        'description': '统计代码中TODO/FIXME/HACK等技术债务标记的密度',
        'check': check_16_1_todo_density,
    },
    {
        'id': '16.2',
        'name': '临时代码检测',
        'level': 'problem',
        'category': 'reflection',
        'module_id': '16',
        'applicable_types': [],
        'description': '检测临时实现、硬编码值、调试残留等需要清理的代码',
        'check': check_16_2_temp_code_detection,
    },
    {
        'id': '16.3',
        'name': '注释密度',
        'level': 'suggestion',
        'category': 'reflection',
        'module_id': '16',
        'applicable_types': [],
        'description': '评估代码注释密度，识别可读性和可维护性问题',
        'check': check_16_3_comment_density,
    },
    {
        'id': '16.4',
        'name': '命名一致性',
        'level': 'problem',
        'category': 'reflection',
        'module_id': '16',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron'],
        'description': '检测函数/变量命名风格是否统一（蛇形vs驼峰）',
        'check': check_16_4_naming_consistency,
    },
]
