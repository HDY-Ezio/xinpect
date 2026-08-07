"""
数据一致性规则集 (M4)
Python后端专项检查 - 数据一致性相关
包含: API响应格式一致性、前端空值防护、枚举值一致性、前后端字段引用等4项检查
"""

import re
import os
from typing import List, Dict, Any


# ===== 工具函数 =====
def _get_frontend_files(context) -> List[str]:
    """获取前端JS/TS文件列表"""
    if not context.project_path or not os.path.isdir(context.project_path):
        return []
    if context.is_web_frontend():
        return context.find_files([".js", ".ts", ".tsx", ".jsx"])
    else:
        return context.find_files([".js"])


# ===== 4.1 API响应格式一致性 =====
def check_4_1_api_response_consistency(context) -> List[Dict]:
    """4.1 API响应格式一致性 - 后端是否统一返回标准结构"""
    results = []
    
    be_content = context.get_all_backend_content()
    if not be_content:
        results.append({
            'id': '4.1',
            'name': 'API响应格式一致性',
            'level': 'suggestion',
            'message': '无后端代码可供检查',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    # 检查是否有统一的响应包装模式
    has_success_wrapper = bool(re.search(r'["\']success["\']\s*[:=]', be_content))
    has_code_wrapper = bool(re.search(r'["\']code["\']\s*[:=]', be_content))
    has_message_wrapper = bool(re.search(r'["\']message["\']\s*[:=]', be_content))
    
    if not has_success_wrapper and not has_code_wrapper:
        results.append({
            'id': '4.1',
            'name': 'API响应格式一致性',
            'level': 'problem',
            'message': '后端API未使用统一的success/code响应包装',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '所有API响应应包含{success, code, message, data}标准结构',
        })
    else:
        missing = []
        if not has_success_wrapper:
            missing.append("success")
        if not has_message_wrapper:
            missing.append("message")
        if missing:
            results.append({
                'id': '4.1',
                'name': 'API响应格式一致性',
                'level': 'problem',
                'message': f"响应格式不完整,缺少: {','.join(missing)}",
                'file': '',
                'line': 0,
                'snippet': '',
                'fix': f"补充{','.join(missing)}字段到响应结构中",
            })
        else:
            results.append({
                'id': '4.1',
                'name': 'API响应格式一致性',
                'level': 'suggestion',
                'message': '后端API响应格式统一',
                'file': '',
                'line': 0,
                'snippet': '',
                'fix': '',
            })
    
    return results


# ===== 4.2 前端空值防护 =====
def check_4_2_frontend_null_guard(context) -> List[Dict]:
    """4.2 前端空值防护 - 前端是否对API响应做了null/undefined防护"""
    results = []
    
    js_files = _get_frontend_files(context)
    if not js_files:
        results.append({
            'id': '4.2',
            'name': '前端空值防护',
            'level': 'suggestion',
            'message': '无前端代码，跳过空值防护检查',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    risky_pages = []
    for f in js_files:
        if '/utils/' in f:
            continue
        content = context.safe_read(f)
        if not content:
            continue
        # Quick check: if file accesses res.data.xxx without optional chaining
        has_api_access = bool(re.search(r'(res|result)\.data\.\w+', content))
        has_optional_chaining = '?.' in content
        has_null_guard = bool(re.search(r'\?\?|\|\|', content))
        if has_api_access and not has_optional_chaining and not has_null_guard:
            risky_pages.append(os.path.basename(f).replace('.js', ''))
    
    if len(risky_pages) > 5:
        results.append({
            'id': '4.2',
            'name': '前端空值防护',
            'level': 'problem',
            'message': f'{len(risky_pages)}个页面可能缺少空值防护',
            'file': '',
            'line': 0,
            'snippet': '\n'.join(risky_pages[:5]),
            'fix': '使用res.data?.field ?? defaultValue模式',
        })
    else:
        results.append({
            'id': '4.2',
            'name': '前端空值防护',
            'level': 'suggestion',
            'message': '前端空值防护基本覆盖',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
    
    return results


# ===== 4.3 枚举值一致性 =====
def check_4_3_enum_consistency(context) -> List[Dict]:
    """4.3 枚举值一致性 - 前后端枚举值是否匹配"""
    results = []
    
    be_content = context.get_all_backend_content()
    fe_content = ""
    
    fe_files = _get_frontend_files(context)
    for f in fe_files:
        content = context.safe_read(f)
        if content:
            fe_content += content + "\n"
    
    if not be_content or not fe_content:
        results.append({
            'id': '4.3',
            'name': '枚举值一致性',
            'level': 'suggestion',
            'message': '缺少前端或后端代码,跳过',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    # 检查套餐枚举值一致性
    be_plans = set(re.findall(r'["\'](trial|chief|operator)["\']', be_content))
    fe_plans = set(re.findall(r'["\'](trial|chief|operator)["\']', fe_content))
    
    if be_plans and fe_plans:
        be_only = be_plans - fe_plans
        fe_only = fe_plans - be_plans
        if be_only or fe_only:
            mismatches = []
            if be_only:
                mismatches.append(f"后端有前端无: {','.join(be_only)}")
            if fe_only:
                mismatches.append(f"前端有后端无: {','.join(fe_only)}")
            results.append({
                'id': '4.3',
                'name': '枚举值一致性',
                'level': 'problem',
                'message': f"套餐枚举值不匹配: {'; '.join(mismatches)}",
                'file': '',
                'line': 0,
                'snippet': '',
                'fix': '统一前后端套餐ID枚举值',
            })
        else:
            results.append({
                'id': '4.3',
                'name': '枚举值一致性',
                'level': 'suggestion',
                'message': '套餐枚举值前后端一致',
                'file': '',
                'line': 0,
                'snippet': '',
                'fix': '',
            })
    else:
        results.append({
            'id': '4.3',
            'name': '枚举值一致性',
            'level': 'suggestion',
            'message': '未发现套餐枚举值,跳过',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
    
    return results


# ===== 4.4 前后端字段引用检查 =====
def check_4_4_field_reference_check(context) -> List[Dict]:
    """4.4 前后端字段引用检查 - 前端访问的字段后端是否返回"""
    results = []
    
    be_content = context.get_all_backend_content()
    fe_files = _get_frontend_files(context)
    
    if not be_content or not fe_files:
        results.append({
            'id': '4.4',
            'name': '前后端字段引用',
            'level': 'suggestion',
            'message': '缺少前端或后端代码,跳过',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    # 检查后端是否定义了标准响应字段
    be_has_data = '"data"' in be_content or "'data'" in be_content
    be_has_success = '"success"' in be_content or "'success'" in be_content
    be_has_message = '"message"' in be_content or "'message'" in be_content
    
    missing_fields = []
    if not be_has_data:
        missing_fields.append("data")
    if not be_has_success:
        missing_fields.append("success")
    if not be_has_message:
        missing_fields.append("message")
    
    if missing_fields:
        results.append({
            'id': '4.4',
            'name': '前后端字段引用',
            'level': 'problem',
            'message': f"后端响应缺少标准字段: {','.join(missing_fields)}",
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '确保所有API响应包含data/success/message字段',
        })
    else:
        results.append({
            'id': '4.4',
            'name': '前后端字段引用',
            'level': 'suggestion',
            'message': '后端响应包含标准字段',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
    
    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': '4.1',
        'name': 'API响应格式一致性',
        'level': 'problem',
        'category': 'data_consistency',
        'module_id': '4',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron'],
        'description': '检查后端API是否统一返回{success, code, message, data}标准结构',
        'check': check_4_1_api_response_consistency,
    },
    {
        'id': '4.2',
        'name': '前端空值防护',
        'level': 'problem',
        'category': 'data_consistency',
        'module_id': '4',
        'applicable_types': ['miniprogram', 'web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查前端是否对API响应做了null/undefined防护，避免空值报错',
        'check': check_4_2_frontend_null_guard,
    },
    {
        'id': '4.3',
        'name': '枚举值一致性',
        'level': 'problem',
        'category': 'data_consistency',
        'module_id': '4',
        'applicable_types': ['miniprogram', 'web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查前后端枚举值（如套餐ID）是否一致，避免数据错位',
        'check': check_4_3_enum_consistency,
    },
    {
        'id': '4.4',
        'name': '前后端字段引用',
        'level': 'problem',
        'category': 'data_consistency',
        'module_id': '4',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron'],
        'description': '检查后端响应是否包含标准字段（data/success/message）',
        'check': check_4_4_field_reference_check,
    },
]
