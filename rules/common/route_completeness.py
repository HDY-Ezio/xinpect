# -*- coding: utf-8 -*-
"""
路由完整性与一致性检查规则集
检测RESTful路由注册不完整、handler支持的action未在路由表中注册等问题
规则ID: ROUTE-001, ROUTE-002, ROUTE-003

归脑: module_id = '7'（Brain 7 架构）
"""

import re
import ast
from typing import List, Dict, Any, Set, Tuple


# ============================================================
# ROUTE-001: RESTful路由注册不完整
# 检测DOMAIN_ROUTES等路由表中，handler函数支持的sub_action
# 是否全部在路由表中注册
# ============================================================

# Flask route decorator patterns
_FLASK_ROUTE_PATTERNS = [
    re.compile(r'@\w+\.route\s*\(\s*[\'"]([^\'"]+)[\'"]', re.IGNORECASE),
    re.compile(r'@app\.route\s*\(\s*[\'"]([^\'"]+)[\'"]', re.IGNORECASE),
    re.compile(r'@bp\.route\s*\(\s*[\'"]([^\'"]+)[\'"]', re.IGNORECASE),
    re.compile(r'@router\.\w+\s*\(\s*[\'"]([^\'"]+)[\'"]', re.IGNORECASE),
]

# DOMAIN_ROUTES / ROUTE_MAP style dict patterns
_ROUTE_DICT_PATTERNS = [
    re.compile(r'(?:DOMAIN_ROUTES|ROUTE_MAP|ROUTES|URL_MAP|API_ROUTES)\s*=\s*\{'),
    re.compile(r'(?:domain_routes|route_map|routes|url_map|api_routes)\s*=\s*\{'),
]

# Action registration patterns (list/dict of action names)
_ACTION_LIST_PATTERNS = [
    re.compile(r'["\']actions["\']\s*:\s*\[([^\]]+)\]', re.IGNORECASE),
    re.compile(r'["\']sub_actions["\']\s*:\s*\[([^\]]+)\]', re.IGNORECASE),
    re.compile(r'actions\s*=\s*\[([^\]]+)\]', re.IGNORECASE),
]


def _extract_handler_actions(content: str, handler_name: str) -> Set[str]:
    """从handler函数中提取支持的action/sub_action名称"""
    actions = set()

    # Pattern 1: if action == 'xxx' or elif action == 'xxx'
    action_if_pattern = re.compile(
        rf'(?:if|elif)\s+\w*action\w*\s*==\s*[\'"](\w+)[\'"]',
        re.IGNORECASE
    )
    for match in action_if_pattern.finditer(content):
        actions.add(match.group(1))

    # Pattern 2: match action: case 'xxx'
    case_pattern = re.compile(
        rf'case\s+[\'"](\w+)[\'"]',
    )
    for match in case_pattern.finditer(content):
        actions.add(match.group(1))

    # Pattern 3: action_map = {'xxx': func, ...}
    action_map_pattern = re.compile(
        r'(?:action_map|action_handlers|action_func)\s*=\s*\{([^}]+)\}',
        re.IGNORECASE
    )
    for match in action_map_pattern.finditer(content):
        inner = match.group(1)
        # Extract keys
        key_pattern = re.compile(r'[\'"](\w+)[\'"]\s*:')
        for key_match in key_pattern.finditer(inner):
            actions.add(key_match.group(1))

    return actions


def _extract_registered_actions(content: str, route_key: str) -> Set[str]:
    """从路由表定义中提取已注册的action列表"""
    registered = set()

    # Find the route definition for this path
    # Pattern: "/api/report": {"actions": ["report", "daily_briefing"]}
    # or: "/api/report": ["report", "daily_briefing"]
    escaped_key = re.escape(route_key)

    # Dict-style: "/api/report": { ... "actions": [...] ... }
    dict_pattern = re.compile(
        rf'[\'"]\s*{escaped_key}\s*[\'"]\s*:\s*\{{([^}}]+)\}}',
        re.DOTALL
    )
    for match in dict_pattern.finditer(content):
        block = match.group(1)
        # Find actions list in the block
        actions_in_block = re.compile(r'[\'"]actions[\'"]\s*:\s*\[([^\]]+)\]')
        for act_match in actions_in_block.finditer(block):
            items = act_match.group(1)
            for item in re.findall(r'[\'"](\w+)[\'"]', items):
                registered.add(item)

    # List-style: "/api/report": ["report", "daily_briefing"]
    list_pattern = re.compile(
        rf'[\'"]\s*{escaped_key}\s*[\'"]\s*:\s*\[([^\]]+)\]'
    )
    for match in list_pattern.finditer(content):
        items = match.group(1)
        for item in re.findall(r'[\'"](\w+)[\'"]', items):
            registered.add(item)

    return registered


def check_route_completeness(context) -> List[Dict]:
    """ROUTE-001: 检测handler支持的action是否全部在路由表中注册"""
    results = []

    py_files = context.get_backend_py_files() if hasattr(context, 'get_backend_py_files') else []
    if not py_files:
        return results

    for fpath in py_files:
        content = context.safe_read(fpath) if hasattr(context, 'safe_read') else ''
        if not content:
            continue

        # Check if this file has route definitions
        has_route_dict = any(p.search(content) for p in _ROUTE_DICT_PATTERNS)
        if not has_route_dict:
            continue

        # Find handler functions and their supported actions
        # Look for patterns like: def handle_report(self, action, ...):
        handler_pattern = re.compile(
            r'def\s+(handle_\w+|process_\w+|dispatch_\w+)\s*\([^)]*\baction\b',
            re.IGNORECASE
        )

        for match in handler_pattern.finditer(content):
            handler_name = match.group(1)
            # Get the function body (rough estimate: next 100 lines)
            start_line = content[:match.start()].count('\n')
            end_line = min(start_line + 100, len(content.split('\n')))
            func_body = '\n'.join(content.split('\n')[start_line:end_line])

            handler_actions = _extract_handler_actions(func_body, handler_name)
            if not handler_actions:
                continue

            # Find corresponding route key for this handler
            # Look for handler reference in route dict
            handler_ref_pattern = re.compile(
                rf'[\'"][^\'"]*[\'"]\s*:\s*\{{[^}}]*[\'"]?(?:handler|func|view)[\'"]?\s*:\s*\w*{re.escape(handler_name)}',
                re.DOTALL
            )

            # Find all route keys in this file
            route_keys = set()
            for rp in _ROUTE_DICT_PATTERNS:
                # Find the dict start
                dict_match = rp.search(content)
                if dict_match:
                    # Extract all top-level keys (route paths)
                    path_pattern = re.compile(r'[\'"](/[a-z_/]+)[\'"]\s*:')
                    for pm in path_pattern.finditer(content):
                        route_keys.add(pm.group(1))

            # Check each route key's registered actions against handler's supported actions
            for route_key in route_keys:
                registered = _extract_registered_actions(content, route_key)
                if not registered:
                    continue

                missing = handler_actions - registered
                if missing:
                    line_no = match.start()
                    line_no = content[:line_no].count('\n') + 1
                    results.append({
                        "rule_id": "ROUTE-001",
                        "name": "路由注册不完整",
                        "severity": "medium",
                        "file": fpath,
                        "line": line_no,
                        "message": f"{handler_name}支持action {sorted(missing)}但未在路由表中注册，访问这些路径会404",
                        "suggestion": f"在路由表中添加缺失的action: {sorted(missing)}",
                        "module_id": "7",
                    })

    return results


# ============================================================
# ROUTE-002: Flask/Express路由HTTP方法不完整
# 检测路由装饰器是否缺少必要的HTTP方法（如只有GET没有POST）
# ============================================================

def check_route_method_completeness(context) -> List[Dict]:
    """ROUTE-002: 检测路由的HTTP方法是否完整"""
    results = []

    py_files = context.get_backend_py_files() if hasattr(context, 'get_backend_py_files') else []
    if not py_files:
        return results

    for fpath in py_files:
        content = context.safe_read(fpath) if hasattr(context, 'safe_read') else ''
        if not content:
            continue

        # Find @app.route() with explicit methods
        route_with_methods = re.compile(
            r'@(\w+)\.route\s*\(\s*[\'"]([^\'"]+)[\'"]\s*,\s*methods\s*=\s*\[([^\]]+)\]',
            re.IGNORECASE
        )

        for match in route_with_methods.finditer(content):
            methods_str = match.group(3).upper()
            methods = set(re.findall(r'[\'"](\w+)[\'"]', methods_str))

            route_path = match.group(2)
            line_no = content[:match.start()].count('\n') + 1

            # If route has POST/PUT/DELETE but no OPTIONS, it might miss CORS preflight
            if any(m in methods for m in ['POST', 'PUT', 'DELETE', 'PATCH']):
                if 'OPTIONS' not in methods:
                    results.append({
                        "rule_id": "ROUTE-002",
                        "name": "路由缺少OPTIONS方法",
                        "severity": "low",
                        "file": fpath,
                        "line": line_no,
                        "message": f"路由 {route_path} 有写操作({', '.join(methods & {'POST','PUT','DELETE','PATCH'})})但未注册OPTIONS方法，可能影响CORS预检请求",
                        "suggestion": "添加methods=['OPTIONS', ...]或确保全局CORS中间件处理预检",
                        "module_id": "7",
                    })

    return results


# ============================================================
# ROUTE-003: 路由路径命名不一致
# 检测同一项目中的路由命名风格是否一致
# (如有的用/api/xxx有的用/v1/xxx)
# ============================================================

def check_route_naming_consistency(context) -> List[Dict]:
    """ROUTE-003: 检测路由路径命名风格不一致"""
    results = []

    py_files = context.get_backend_py_files() if hasattr(context, 'get_backend_py_files') else []
    if not py_files:
        return results

    all_routes = []  # [(file, line, path, prefix_style)]

    for fpath in py_files:
        content = context.safe_read(fpath) if hasattr(context, 'safe_read') else ''
        if not content:
            continue

        for pattern in _FLASK_ROUTE_PATTERNS:
            for match in pattern.finditer(content):
                path = match.group(1)
                line_no = content[:match.start()].count('\n') + 1

                # Determine prefix style
                if path.startswith('/api/'):
                    prefix = 'api'
                elif path.startswith('/v1/') or path.startswith('/v2/'):
                    prefix = 'versioned'
                elif path.startswith('/admin/'):
                    prefix = 'admin'
                else:
                    prefix = 'other'

                all_routes.append((fpath, line_no, path, prefix))

    if len(all_routes) < 3:
        return results

    # Check if there's mixed prefix styles
    prefix_counts = {}
    for _, _, _, prefix in all_routes:
        prefix_counts[prefix] = prefix_counts.get(prefix, 0) + 1

    # If majority uses one style but some use another, flag the minority
    if len(prefix_counts) >= 2:
        total = len(all_routes)
        dominant_prefix = max(prefix_counts, key=prefix_counts.get)
        dominant_count = prefix_counts[dominant_prefix]

        # If dominant style is >70%, flag the rest as inconsistent
        if dominant_count / total > 0.7:
            for fpath, line_no, path, prefix in all_routes:
                if prefix != dominant_prefix:
                    results.append({
                        "rule_id": "ROUTE-003",
                        "name": "路由命名风格不一致",
                        "severity": "info",
                        "file": fpath,
                        "line": line_no,
                        "message": f"路由路径 '{path}' 使用前缀风格'{prefix}'，但项目主流使用'{dominant_prefix}'风格",
                        "suggestion": f"统一使用/{dominant_prefix}/前缀风格，或添加路由别名",
                        "module_id": "7",
                    })

    return results


# ============================================================
# Rule registration
# ============================================================

RULES = [
    {
        "id": "ROUTE-001",
        "name": "路由注册完整性检查",
        "description": "检测handler支持的action是否全部在路由表中注册，避免404",
        "level": "problem",
        "check": check_route_completeness,
        "category": "route_completeness",
        "applicable_types": ["python_backend", "flask", "mixed", "mixed_electron", "skill"],
        "module_id": "7",
    },
    {
        "id": "ROUTE-002",
        "name": "路由HTTP方法完整性检查",
        "description": "检测路由是否缺少必要的HTTP方法（如OPTIONS for CORS）",
        "level": "suggestion",
        "check": check_route_method_completeness,
        "category": "route_completeness",
        "applicable_types": ["python_backend", "flask", "mixed", "mixed_electron", "skill"],
        "module_id": "7",
    },
    {
        "id": "ROUTE-003",
        "name": "路由命名风格一致性检查",
        "description": "检测项目中路由路径命名风格是否一致",
        "level": "suggestion",
        "check": check_route_naming_consistency,
        "category": "route_completeness",
        "applicable_types": ["python_backend", "flask", "mixed", "mixed_electron", "skill"],
        "module_id": "7",
    },
]
