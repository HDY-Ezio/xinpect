"""
变更影响分析规则集 (M11)
通用变更影响检查 - 适用于所有项目类型
包含: API变更检测、接口参数变更、数据库Schema变更、前端调用受影响分析等4项检查
注意：需配置reference_backend_path才能启用完整分析
"""

import re
import os
import json
from typing import List, Dict, Any


# ===== 11.1 API变更检测 =====
def check_11_1_api_change_detection(context) -> List[Dict]:
    """11.1 API变更检测 - 对比新旧版本的API路由定义"""
    results = []
    
    ref_path = context.config.get("reference_backend_path", "")
    if not ref_path or not os.path.isfile(ref_path):
        results.append({
            'id': '11.1',
            'name': 'API变更检测',
            'level': 'suggestion',
            'message': '未配置reference_backend_path，跳过变更影响分析',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '在config.json中配置reference_backend_path指定旧版本后端代码路径',
        })
        return results
    
    old_content = context.safe_read(ref_path)
    new_content = context.get_all_backend_content()
    
    if not old_content or not new_content:
        results.append({
            'id': '11.1',
            'name': 'API变更检测',
            'level': 'suggestion',
            'message': '缺少参照版本或当前版本代码，跳过',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    # 解析路由定义（匹配domain_routes风格）
    domain_pattern = re.compile(r'"/(api/[\w-]+)"\s*:\s*{([^}]+)}', re.DOTALL)
    action_pattern = re.compile(r'"(\w+)"\s*:')
    
    old_routes = {}
    for m in domain_pattern.finditer(old_content):
        domain = "/" + m.group(1)
        actions_block = m.group(2)
        actions = set(action_pattern.findall(actions_block))
        old_routes[domain] = actions
    
    new_routes = {}
    for m in domain_pattern.finditer(new_content):
        domain = "/" + m.group(1)
        actions_block = m.group(2)
        actions = set(action_pattern.findall(actions_block))
        new_routes[domain] = actions
    
    added_domains = set(new_routes.keys()) - set(old_routes.keys())
    removed_domains = set(old_routes.keys()) - set(new_routes.keys())
    added_actions = []
    removed_actions = []
    
    for domain in set(new_routes.keys()) & set(old_routes.keys()):
        for a in new_routes[domain] - old_routes[domain]:
            added_actions.append(f"{domain}/{a}")
        for a in old_routes[domain] - new_routes[domain]:
            removed_actions.append(f"{domain}/{a}")
    
    changes = []
    if added_domains:
        changes.append(f"新增域: {', '.join(added_domains)}")
    if removed_domains:
        changes.append(f"删除域: {', '.join(removed_domains)}")
    if added_actions:
        changes.append(f"新增接口: {', '.join(added_actions[:5])}")
    if removed_actions:
        changes.append(f"删除接口: {', '.join(removed_actions[:5])}")
    
    if changes:
        results.append({
            'id': '11.1',
            'name': 'API变更检测',
            'level': 'problem',
            'message': f"检测到API变更: {'; '.join(changes)}",
            'file': '',
            'line': 0,
            'snippet': '\n'.join(changes),
            'fix': '评估变更对前端调用的影响，确保兼容性',
        })
    else:
        results.append({
            'id': '11.1',
            'name': 'API变更检测',
            'level': 'suggestion',
            'message': 'API未发生变化',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
    
    return results


# ===== 11.2 接口参数变更 =====
def check_11_2_api_parameter_change(context) -> List[Dict]:
    """11.2 接口参数变更 - 提示需深度分析工具检测"""
    results = []
    
    ref_path = context.config.get("reference_backend_path", "")
    if not ref_path or not os.path.isfile(ref_path):
        results.append({
            'id': '11.2',
            'name': '接口参数变更',
            'level': 'suggestion',
            'message': '未配置参照版本，跳过',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    results.append({
        'id': '11.2',
        'name': '接口参数变更',
        'level': 'suggestion',
        'message': '需对比handler函数签名，建议用AST分析工具自动检测',
        'file': '',
        'line': 0,
        'snippet': '',
        'fix': '使用AST工具对比函数参数变化，确保向后兼容',
    })
    
    return results


# ===== 11.3 数据库Schema变更 =====
def check_11_3_db_schema_change(context) -> List[Dict]:
    """11.3 数据库Schema变更 - 提示需对比迁移脚本"""
    results = []
    
    ref_path = context.config.get("reference_backend_path", "")
    if not ref_path or not os.path.isfile(ref_path):
        results.append({
            'id': '11.3',
            'name': '数据库Schema变更',
            'level': 'suggestion',
            'message': '未配置参照版本，跳过',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    results.append({
        'id': '11.3',
        'name': '数据库Schema变更',
        'level': 'suggestion',
        'message': '需对比数据库迁移脚本，建议集成Alembic等工具',
        'file': '',
        'line': 0,
        'snippet': '',
        'fix': '使用数据库迁移工具管理Schema变更',
    })
    
    return results


# ===== 11.4 前端调用受影响分析 =====
def check_11_4_frontend_impact(context) -> List[Dict]:
    """11.4 前端调用受影响分析 - 检查删除接口是否影响前端"""
    results = []
    
    ref_path = context.config.get("reference_backend_path", "")
    ref_mapping = context.config.get("reference_frontend_mapping", "")
    
    if not ref_path or not os.path.isfile(ref_path):
        results.append({
            'id': '11.4',
            'name': '前端调用受影响分析',
            'level': 'suggestion',
            'message': '未配置参照版本，跳过',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    # 先检测是否有删除的接口
    old_content = context.safe_read(ref_path)
    new_content = context.get_all_backend_content()
    
    if not old_content or not new_content:
        results.append({
            'id': '11.4',
            'name': '前端调用受影响分析',
            'level': 'suggestion',
            'message': '缺少代码，跳过',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    domain_pattern = re.compile(r'"/(api/[\w-]+)"\s*:\s*{([^}]+)}', re.DOTALL)
    action_pattern = re.compile(r'"(\w+)"\s*:')
    
    old_routes = {}
    for m in domain_pattern.finditer(old_content):
        domain = "/" + m.group(1)
        actions = set(action_pattern.findall(m.group(2)))
        old_routes[domain] = actions
    
    new_routes = {}
    for m in domain_pattern.finditer(new_content):
        domain = "/" + m.group(1)
        actions = set(action_pattern.findall(m.group(2)))
        new_routes[domain] = actions
    
    removed_actions = []
    for domain in set(new_routes.keys()) & set(old_routes.keys()):
        for a in old_routes[domain] - new_routes[domain]:
            removed_actions.append(f"{domain}/{a}")
    
    removed_domains = set(old_routes.keys()) - set(new_routes.keys())
    for d in removed_domains:
        for a in old_routes.get(d, set()):
            removed_actions.append(f"{d}/{a}")
    
    if not removed_actions:
        results.append({
            'id': '11.4',
            'name': '前端调用受影响分析',
            'level': 'suggestion',
            'message': '无删除接口，前端不受影响',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    # 有删除接口时，检查前端映射
    affected_pages = []
    if ref_mapping and os.path.isfile(ref_mapping):
        try:
            fe_mapping = json.loads(context.safe_read(ref_mapping))
            for page, calls in fe_mapping.items():
                for call in calls:
                    for ra in removed_actions:
                        if ra.replace("/", "_") in call or ra.split("/")[-1] in call:
                            affected_pages.append(f"{page}: {call}")
                            break
        except:  # noqa: intentional empty handler
            pass
    
    if affected_pages:
        results.append({
            'id': '11.4',
            'name': '前端调用受影响分析',
            'level': 'blocking',
            'message': f'后端删除接口影响前端 {len(affected_pages)} 处调用',
            'file': '',
            'line': 0,
            'snippet': '\n'.join(affected_pages[:5]),
            'fix': '前端需同步移除或适配受影响的API调用',
        })
    else:
        results.append({
            'id': '11.4',
            'name': '前端调用受影响分析',
            'level': 'problem',
            'message': f'检测到{len(removed_actions)}个删除接口，需确认前端影响',
            'file': '',
            'line': 0,
            'snippet': '\n'.join(removed_actions[:5]),
            'fix': '配置reference_frontend_mapping可自动检测受影响页面',
        })
    
    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': '11.1',
        'name': 'API变更检测',
        'level': 'problem',
        'category': 'change_impact',
        'module_id': '11',
        'applicable_types': ['python_backend', 'python_tool', 'flask', 'mixed', 'mixed_electron'],
        'description': '对比新旧版本API路由定义，检测新增/删除/修改的接口',
        'check': check_11_1_api_change_detection,
    },
    {
        'id': '11.2',
        'name': '接口参数变更',
        'level': 'suggestion',
        'category': 'change_impact',
        'module_id': '11',
        'applicable_types': ['python_backend', 'python_tool', 'flask', 'mixed', 'mixed_electron'],
        'description': '提示需深度AST分析检测接口参数变更',
        'check': check_11_2_api_parameter_change,
    },
    {
        'id': '11.3',
        'name': '数据库Schema变更',
        'level': 'suggestion',
        'category': 'change_impact',
        'module_id': '11',
        'applicable_types': ['python_backend', 'python_tool', 'flask', 'mixed', 'mixed_electron'],
        'description': '提示需对比数据库迁移脚本检测Schema变更',
        'check': check_11_3_db_schema_change,
    },
    {
        'id': '11.4',
        'name': '前端调用受影响分析',
        'level': 'blocking',
        'category': 'change_impact',
        'module_id': '11',
        'applicable_types': ['python_backend', 'python_tool', 'flask', 'mixed', 'mixed_electron'],
        'description': '检测后端删除接口是否影响前端调用，需配置前端映射',
        'check': check_11_4_frontend_impact,
    },
]
