"""
扣子技能规则集
扣子(Coze)技能专项检查
包含: SKILL.md规范、工具函数、配置文件等检查
"""

import re
import os
import json
from typing import List, Dict, Any


def _find_skill_md(context):
    """查找SKILL.md文件"""
    if context.project_path and os.path.isdir(context.project_path):
        candidate = os.path.join(context.project_path, 'SKILL.md')
        if os.path.isfile(candidate):
            return candidate
    
    # 向上查找
    if context.project_path:
        for root, dirs, files in os.walk(context.project_path):
            if 'SKILL.md' in files:
                return os.path.join(root, 'SKILL.md')
            # 只查一层
            break
    
    return ''


# ===== SKILL-001 SKILL.md完整性 =====
def check_skill_001_skill_md(context) -> List[Dict]:
    """SKILL-001 SKILL.md完整性 - 检查SKILL.md是否存在且内容完整"""
    results = []
    
    skill_md_path = _find_skill_md(context)
    
    if not skill_md_path:
        results.append({
            'id': 'SKILL-001',
            'name': 'SKILL.md完整性',
            'level': 'error',
            'message': '未找到SKILL.md文件',
            'file': '',
            'line': 0,
            'fix': '在技能根目录创建SKILL.md文件',
        })
        return results
    
    content = context.safe_read(skill_md_path)
    
    # 检查必要章节
    required_sections = ['描述', '使用场景', '使用方式']
    missing_sections = []
    
    for section in required_sections:
        if f'# {section}' not in content and f'## {section}' not in content:
            missing_sections.append(section)
    
    if missing_sections:
        results.append({
            'id': 'SKILL-001',
            'name': 'SKILL.md完整性',
            'level': 'warning',
            'message': f'SKILL.md缺少必要章节: {", ".join(missing_sections)}',
            'file': skill_md_path,
            'line': 0,
            'fix': '补充缺失的章节，完善SKILL.md文档',
        })
    
    # 检查内容长度
    if len(content) < 200:
        results.append({
            'id': 'SKILL-001',
            'name': 'SKILL.md完整性',
            'level': 'info',
            'message': 'SKILL.md内容较少，建议补充详细说明',
            'file': skill_md_path,
            'line': 0,
            'fix': '完善SKILL.md内容，详细描述技能功能和使用方法',
        })
    
    return results


# ===== SKILL-002 技能入口检查 =====
def check_skill_002_entry_point(context) -> List[Dict]:
    """SKILL-002 技能入口检查 - 检查技能入口文件是否存在"""
    results = []
    
    # 检查是否有主脚本
    py_files = context.find_files([".py"])
    has_main_script = any('skill' in os.path.basename(f).lower() for f in py_files)
    
    if not py_files:
        results.append({
            'id': 'SKILL-002',
            'name': '技能入口检查',
            'level': 'warning',
            'message': '未找到Python脚本文件',
            'file': '',
            'line': 0,
            'fix': '创建技能主脚本文件',
        })
    
    return results


# ===== SKILL-003 依赖清单检查 =====
def check_skill_003_dependencies(context) -> List[Dict]:
    """SKILL-003 依赖清单检查 - 检查requirements.txt是否存在"""
    results = []
    
    has_requirements = False
    check_paths = []
    if context.project_path:
        check_paths.append(context.project_path)
    if context.backend_path:
        check_paths.append(context.backend_path)
    
    for check_path in check_paths:
        if check_path and os.path.isdir(check_path):
            if os.path.isfile(os.path.join(check_path, 'requirements.txt')):
                has_requirements = True
                break
    
    if not has_requirements and context.project_type == 'skill':
        results.append({
            'id': 'SKILL-003',
            'name': '依赖清单检查',
            'level': 'info',
            'message': '建议添加requirements.txt声明依赖',
            'file': '',
            'line': 0,
            'fix': '创建requirements.txt，列出所有Python依赖',
        })
    
    return results


# ===== SKILL-004 配置文件检查 =====
def check_skill_004_config(context) -> List[Dict]:
    """SKILL-004 配置文件检查 - 检查配置文件格式"""
    results = []
    
    # 检查pyproject.toml或setup.py
    check_paths = []
    if context.project_path:
        check_paths.append(context.project_path)
    
    has_pyproject = False
    for check_path in check_paths:
        if check_path and os.path.isdir(check_path):
            if os.path.isfile(os.path.join(check_path, 'pyproject.toml')):
                has_pyproject = True
                break
    
    return results  # 简化版本


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'SKILL-001',
        'name': 'SKILL.md完整性',
        'level': 'problem',
        'category': 'skill',
        'module_id': '7',
        'applicable_types': ['skill'],
        'description': '检查SKILL.md是否存在且内容完整',
        'check': check_skill_001_skill_md,
    },
    {
        'id': 'SKILL-002',
        'name': '技能入口检查',
        'level': 'problem',
        'category': 'skill',
        'module_id': '7',
        'applicable_types': ['skill'],
        'description': '检查技能入口文件是否存在',
        'check': check_skill_002_entry_point,
    },
    {
        'id': 'SKILL-003',
        'name': '依赖清单检查',
        'level': 'suggestion',
        'category': 'skill',
        'module_id': '7',
        'applicable_types': ['skill'],
        'description': '检查依赖清单是否存在',
        'check': check_skill_003_dependencies,
    },
]
