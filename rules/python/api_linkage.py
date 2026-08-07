"""
API链路完整性规则集 (M1)
Python后端API链路检查 - 适用于前后端混合项目
包含: 架构检测、路由映射完整性、路径拼写、HTTP方法、鉴权、API地址、请求封装等7项检查
"""

import re
import os
from typing import List, Dict, Any
from collections import defaultdict


# ===== 内部工具函数 =====

def _get_backend_content(context) -> str:
    """获取主后端文件内容"""
    return context.get_backend_content()


def _get_all_backend_content(context) -> str:
    """获取所有后端.py文件的合并内容"""
    return context.get_all_backend_content()


def _detect_backend_architecture(context) -> dict:
    """
    智能检测后端架构类型，返回架构信息
    支持的架构：
    - unified_entry: 统一入口模式
    - domain_routes: DOMAIN_ROUTES字典声明式路由
    - flask_decorator: Flask @app.route装饰器路由
    - unknown: 无法识别
    """
    result = {
        "type": "unknown",
        "confidence": 0,
        "features": [],
        "unified_entry": False,
        "domains_count": 0,
        "actions_count": 0,
        "has_domain_routes": False,
        "note": ""
    }
    if not context.backend_path or not os.path.isdir(context.backend_path):
        result["note"] = "无后端代码，跳过架构检测"
        return result

    content = _get_backend_content(context)
    all_content = _get_all_backend_content(context)

    # 检测1：DOMAIN_ROUTES字典模式
    if "DOMAIN_ROUTES = {" in content or "DOMAIN_ROUTES={" in content:
        result["type"] = "domain_routes"
        result["confidence"] = 0.9
        result["features"].append("DOMAIN_ROUTES字典")
    elif "DOMAIN_ROUTES = {" in all_content or "DOMAIN_ROUTES={" in all_content:
        result["type"] = "domain_routes"
        result["confidence"] = 0.8
        result["features"].append("DOMAIN_ROUTES字典(多文件)")

    # 检测2：Flask装饰器路由
    flask_count = len(re.findall(r"@app\.route\(|@blueprint\.route\(", all_content))
    if flask_count > 0:
        result["features"].append(f"Flask装饰器路由({flask_count}处)")
        if result["confidence"] < 0.5:
            result["type"] = "flask_decorator"
            result["confidence"] = 0.7

    # 检测3：统一入口通配模式
    unified_patterns = [
        r"/api/<path:subpath>",
        r"main_handler\(",
        r"scf_event",
        r"serverless_handler",
    ]
    unified_count = 0
    for pat in unified_patterns:
        if re.search(pat, all_content):
            unified_count += 1
    if unified_count >= 2:
        result["unified_entry"] = True
        result["features"].append(f"统一入口架构({unified_count}个特征)")
        if result["confidence"] < 0.6:
            result["type"] = "unified_gateway"
            result["confidence"] = 0.75

    # 统计domain和action数量
    routes = _parse_backend_routes(context)
    result["domains_count"] = len(routes)
    result["actions_count"] = sum(len(actions) for actions in routes.values())
    result["has_domain_routes"] = "DOMAIN_ROUTES" in all_content or "DOMAIN_ROUTES" in content

    if result["type"] == "domain_routes" and result["unified_entry"]:
        result["note"] = f"多引擎架构统一入口模式：{result['domains_count']}个domain，{result['actions_count']}个action，通配路由+DOMAIN_ROUTES内部分发"
    elif result["unified_entry"]:
        result["note"] = f"统一入口网关模式：{result['domains_count']}个domain，{result['actions_count']}个action，静态分析可能不完整"
    elif result["type"] == "domain_routes":
        result["note"] = f"DOMAIN_ROUTES字典模式：{result['domains_count']}个domain，{result['actions_count']}个action"

    return result


def _parse_backend_routes(context) -> dict:
    """解析后端路由，支持多种架构"""
    routes = {}
    if not context.backend_path:
        return routes

    content = _get_backend_content(context)
    all_content = _get_all_backend_content(context)

    # 方法1：DOMAIN_ROUTES字典模式
    target_content = content if "DOMAIN_ROUTES" in content else all_content
    idx = target_content.find("DOMAIN_ROUTES = {")
    if idx < 0:
        idx = target_content.find("DOMAIN_ROUTES={")
    if idx >= 0:
        brace_count = 0
        end = idx
        for i, c in enumerate(target_content[idx:], idx):
            if c == '{':
                brace_count += 1
            elif c == '}':
                brace_count -= 1
                if brace_count == 0:
                    end = i + 1
                    break
        routes_text = target_content[idx:end]
        domain_pattern = re.compile(r'"/(api/[\w-]+)"\s*:\s*{([^}]+)}', re.DOTALL)
        action_pattern = re.compile(r'"(\w+)"\s*:')
        for m in domain_pattern.finditer(routes_text):
            domain = "/" + m.group(1)
            actions_block = m.group(2)
            actions = action_pattern.findall(actions_block)
            routes[domain] = actions

    # 方法2：Flask装饰器路由（补充）
    if not routes:
        flask_routes = re.findall(r"@app\.route\(\s*['\"]([^'\"]+)['\"]", all_content)
        for route in flask_routes:
            if route.startswith('/api/'):
                parts = route.split('/')
                if len(parts) >= 3:
                    domain = '/' + '/'.join(parts[1:3])
                    if domain not in routes:
                        routes[domain] = []

    return routes


def _parse_frontend_api_calls(context) -> dict:
    """解析前端 api('domain', 'action') 实际调用"""
    calls = defaultdict(set)
    if not context.project_path or not os.path.isdir(context.project_path):
        return calls
    js_files = context.find_files([".js"])
    for jsf in js_files:
        content = context.safe_read(jsf)
        # Pattern: api('domain', 'action') with literal strings
        for m in re.finditer(r"api\(\s*['\"]([\w-]+)['\"]\s*,\s*['\"]([\w_]+)['\"]", content):
            calls["/api/" + m.group(1)].add(m.group(2))
        # Pattern: api('domain', variable) — dynamic action
        for m in re.finditer(r"api\(\s*['\"]([\w-]+)['\"]\s*,\s*(?!['\"])([\w.]+)", content):
            domain = "/api/" + m.group(1)
            if domain not in calls:
                calls[domain] = set()  # empty set means domain is used but actions are dynamic
    return calls


def _has_audit_comment(be_lines: list, action: str, radius: int = 5) -> bool:
    """检查action附近是否有审计注释"""
    audit_patterns = [
        r'#\s*audit:',
        r'#\s*reserved:',
        r'#\s*internal:',
        r'#\s*预留',
        r'#\s*内部',
    ]
    for i, line in enumerate(be_lines):
        if re.search(r'\b' + re.escape(action) + r'\b', line):
            start = max(0, i - radius)
            end = min(len(be_lines), i + radius + 1)
            for check_line in be_lines[start:end]:
                for pat in audit_patterns:
                    if re.search(pat, check_line, re.IGNORECASE):
                        return True
    return False


def _find_first_unmatched_location(context, unmatched_actions, frontend_calls, backend_routes):
    """尝试定位第一个不匹配的action的前端调用位置"""
    if not unmatched_actions:
        return None

    first_unmatched = unmatched_actions[0]
    parts = first_unmatched.rsplit("/", 1)
    if len(parts) != 2:
        return None

    domain = parts[0].replace("/api/", "")
    action = parts[1]

    js_files = context.find_files([".js"])
    for jf in js_files:
        try:
            content = context.safe_read(jf)
            for i, line in enumerate(content.split('\n'), 1):
                if f"api('{domain}'" in line and action in line:
                    rel_path = os.path.relpath(jf, context.project_path) if context.project_path else jf
                    return {
                        'file': rel_path,
                        'line': i,
                        'snippet': line.strip()[:100],
                    }
        except Exception as e:  # noqa: broad exception handling
            pass

    # 如果没找到具体位置，至少定位到api.js文件
    if context.project_path:
        api_file = "utils/api.js"
        full_api = os.path.join(context.project_path, api_file)
        if os.path.isfile(full_api):
            return {'file': api_file, 'line': 1, 'snippet': ''}

    return None


# ===== 1.0 后端架构检测 =====
def check_1_0_arch_detection(context) -> List[Dict]:
    """1.0 后端架构检测 - 识别后端架构类型"""
    results = []

    arch_info = _detect_backend_architecture(context)
    arch_desc = f"{arch_info['type']}" + (f"（{'、'.join(arch_info['features'])}）" if arch_info['features'] else "")
    if arch_info['note']:
        results.append({
            'id': '1.0',
            'name': '后端架构检测',
            'level': 'info',
            'message': arch_desc,
            'detail': arch_info['note'],
            'file': '',
            'line': 0,
            'fix': '架构检测结果用于调整检查策略',
        })
    else:
        results.append({
            'id': '1.0',
            'name': '后端架构检测',
            'level': 'info',
            'message': arch_desc,
            'file': '',
            'line': 0,
            'fix': '架构检测结果用于调整检查策略',
        })

    return results


# ===== 1.1 后端路由→前端调用映射完整性 =====
def check_1_1_backend_orphan_routes(context) -> List[Dict]:
    """1.1 后端路由→前端调用映射完整性 - 检查是否有后端路由前端未调用"""
    results = []

    backend_routes = _parse_backend_routes(context)
    frontend_calls = _parse_frontend_api_calls(context)
    if not backend_routes and not frontend_calls:
        return results

    be_content = _get_all_backend_content(context)
    be_lines = be_content.split('\n') if be_content else []

    orphan_routes = []
    audited_routes = []
    for domain, actions in backend_routes.items():
        fe_actions = frontend_calls.get(domain)
        if fe_actions is None:
            # Domain not called by frontend at all
            for action in actions:
                route_str = f"{domain}/{action}"
                if _has_audit_comment(be_lines, action):
                    audited_routes.append(route_str)
                else:
                    orphan_routes.append(route_str)
        elif len(fe_actions) == 0:
            # Domain has dynamic calls — can't determine specific actions, skip
            continue
        else:
            for action in actions:
                if action not in fe_actions:
                    route_str = f"{domain}/{action}"
                    if _has_audit_comment(be_lines, action):
                        audited_routes.append(route_str)
                    else:
                        orphan_routes.append(route_str)

    # 架构感知 - 统一入口模式下增加统计信息
    arch_info = _detect_backend_architecture(context)
    is_unified = arch_info.get('unified_entry', False)
    has_domain_routes = arch_info.get('has_domain_routes', False)
    be_domains_count = arch_info.get('domains_count', 0)
    be_actions_count = arch_info.get('actions_count', 0)

    if orphan_routes:
        arch_note = ""
        if is_unified or has_domain_routes:
            arch_note = f"（后端共{be_domains_count}个domain/{be_actions_count}个action，预留功能属正常现象）"
        results.append({
            'id': '1.1',
            'name': '后端路由→前端调用映射完整性',
            'level': 'warning',
            'message': f"发现 {len(orphan_routes)} 个后端路由前端未调用（可能为白写路由）" +
                       (f"，另有 {len(audited_routes)} 个已有审计注释" if audited_routes else "") +
                       arch_note,
            'detail': "\n".join(orphan_routes[:20]),
            'file': '',
            'line': 0,
            'fix': '确认是否为内部/定时任务/预留接口，否则前端应补调用或后端清理',
        })
    elif audited_routes:
        arch_note = ""
        if is_unified or has_domain_routes:
            arch_note = f"（后端共{be_domains_count}个domain/{be_actions_count}个action）"
        results.append({
            'id': '1.1',
            'name': '后端路由→前端调用映射完整性',
            'level': 'info',
            'message': f"发现 {len(audited_routes)} 个后端路由前端未调用，但已有审计注释标注（预留/内部接口）{arch_note}",
            'detail': "\n".join(audited_routes[:20]),
            'file': '',
            'line': 0,
            'fix': '审计注释已标注，建议定期复查是否仍需保留',
        })

    return results


# ===== 1.2 前端调用→后端路由映射 =====
def check_1_2_frontend_ghost_calls(context) -> List[Dict]:
    """1.2 前端调用→后端路由映射 - 检查前端是否调用了不存在的后端接口"""
    results = []

    backend_routes = _parse_backend_routes(context)
    frontend_calls = _parse_frontend_api_calls(context)
    if not backend_routes and not frontend_calls:
        return results

    arch_info = _detect_backend_architecture(context)
    is_unified = arch_info.get('unified_entry', False)
    has_domain_routes = arch_info.get('has_domain_routes', False)
    be_domains_count = arch_info.get('domains_count', 0)
    be_actions_count = arch_info.get('actions_count', 0)

    # 统计前端调用情况
    fe_domains_count = len(frontend_calls)
    fe_actions_count = sum(len(actions) for actions in frontend_calls.values())

    if is_unified or has_domain_routes:
        # 统一入口/多引擎架构模式 - 按domain/action维度精确匹配
        matched_domains = 0
        unmatched_domains = []
        matched_actions = 0
        unmatched_actions = []
        dynamic_domains = 0

        for domain, actions in frontend_calls.items():
            if len(actions) == 0:
                # 动态action域
                dynamic_domains += 1
                if domain not in backend_routes:
                    unmatched_domains.append(f"{domain} (动态action)")
                else:
                    matched_domains += 1
                continue

            if domain in backend_routes:
                matched_domains += 1
                be_actions = set(backend_routes[domain])
                for a in actions:
                    if a in be_actions:
                        matched_actions += 1
                    else:
                        unmatched_actions.append(f"{domain}/{a}")
            else:
                unmatched_domains.append(domain)
                for a in actions:
                    unmatched_actions.append(f"{domain}/{a}")

        # 计算覆盖率
        domain_coverage = matched_domains / fe_domains_count * 100 if fe_domains_count > 0 else 100
        action_coverage = matched_actions / fe_actions_count * 100 if fe_actions_count > 0 else 100

        if unmatched_actions:
            # 有找不到的action
            level = "warning"  # 统一入口模式下统一为warning，避免误报
            summary = (f"统一入口架构检测：后端{be_domains_count}个domain/{be_actions_count}个action，"
                      f"前端调用{fe_domains_count}个domain/{fe_actions_count}个action，"
                      f"{len(unmatched_actions)}个action后端未找到")
            detail = "\n".join(unmatched_actions[:15])
            if unmatched_domains:
                detail += f"\n\n未匹配的domain({len(unmatched_domains)}个): {', '.join(unmatched_domains[:10])}"
            detail += f"\n\n覆盖率: domain {domain_coverage:.0f}%, action {action_coverage:.0f}%"

            # 尝试定位第一个不匹配的action的前端调用位置
            location = _find_first_unmatched_location(context, unmatched_actions, frontend_calls, backend_routes)

            results.append({
                'id': '1.2',
                'name': '前端调用→后端路由映射',
                'level': level,
                'message': summary,
                'detail': detail,
                'file': location.get('file', '') if location else '',
                'line': location.get('line', 0) if location else 0,
                'snippet': location.get('snippet', '') if location else '',
                'fix': '检查前端调用是否拼写正确；统一入口架构下建议运行时验证，或补充后端接口',
            })
    else:
        # 传统模式：原来的检查逻辑
        ghost_calls = []
        for domain, actions in frontend_calls.items():
            if len(actions) == 0:
                if domain not in backend_routes:
                    ghost_calls.append(f"{domain} (动态action，后端无此域)")
                continue
            be_actions = set(backend_routes.get(domain, []))
            if domain not in backend_routes:
                for a in actions:
                    ghost_calls.append(f"{domain}/{a}")
            else:
                for a in actions:
                    if a not in be_actions:
                        ghost_calls.append(f"{domain}/{a}")

        if ghost_calls:
            has_backend = bool(backend_routes)
            level = "warning" if not has_backend else "error"
            extra_note = "" if has_backend else "（无后端代码，仅供参考）"

            # 定位到api.js文件
            loc_file = ''
            if context.project_path:
                api_file = "utils/api.js"
                full_api = os.path.join(context.project_path, api_file)
                if os.path.isfile(full_api):
                    loc_file = api_file

            results.append({
                'id': '1.2',
                'name': '前端调用→后端路由映射',
                'level': level,
                'message': f"发现 {len(ghost_calls)} 个前端调用了不存在的后端接口{extra_note}",
                'detail': "\n".join(ghost_calls[:20]),
                'file': loc_file,
                'line': 1 if loc_file else 0,
                'fix': '移除前端无效调用或后端补接口',
            })

    return results


# ===== 1.3 API路径拼写一致性 =====
def check_1_3_path_naming_consistency(context) -> List[Dict]:
    """1.3 API路径拼写一致性 - 检查连字符vs下划线命名风格不一致"""
    results = []

    backend_routes = _parse_backend_routes(context)
    frontend_calls = _parse_frontend_api_calls(context)
    if not backend_routes or not frontend_calls:
        return results

    mismatch_path = []
    for domain in frontend_calls:
        if domain not in backend_routes:
            alt1 = domain.replace("-", "_")
            alt2 = domain.replace("_", "-")
            if alt1 in backend_routes or alt2 in backend_routes:
                mismatch_path.append(domain)

    if mismatch_path:
        results.append({
            'id': '1.3',
            'name': 'API路径拼写一致性',
            'level': 'warning',
            'message': f"发现 {len(mismatch_path)} 个路径命名风格不一致（连字符vs下划线）",
            'detail': "\n".join(mismatch_path),
            'file': '',
            'line': 0,
            'fix': '统一前后端路径命名规范（建议用连字符）',
        })

    return results


# ===== 1.4 HTTP方法一致性 =====
def check_1_4_http_method_consistency(context) -> List[Dict]:
    """1.4 HTTP方法一致性 - 检查前后端HTTP方法(GET/POST)是否一致"""
    results = []

    if context.project_type in ("miniprogram", "mixed") and not context.is_web_frontend():
        results.append({
            'id': '1.4',
            'name': 'HTTP方法一致性',
            'level': 'info',
            'message': '微信小程序统一POST请求，此项默认通过',
            'file': '',
            'line': 0,
            'fix': '',
        })
    elif context.is_electron():
        # Electron项目可能使用IPC通信而非HTTP API
        if context.project_path and os.path.isdir(context.project_path):
            all_js = context.find_files([".js", ".ts"])
            has_ipc = False
            for jf in all_js:
                content = context.safe_read(jf)
                if re.search(r'ipcRenderer\.invoke|ipcRenderer\.send|ipcMain\.handle|ipcMain\.on', content):
                    has_ipc = True
                    break
            if has_ipc:
                results.append({
                    'id': '1.4',
                    'name': 'HTTP方法一致性',
                    'level': 'info',
                    'message': 'Electron项目使用IPC通信，HTTP方法检查跳过',
                    'file': '',
                    'line': 0,
                    'fix': '',
                })
            else:
                results.append({
                    'id': '1.4',
                    'name': 'HTTP方法一致性',
                    'level': 'info',
                    'message': '未检测到IPC通信，需人工验证HTTP方法一致性',
                    'file': '',
                    'line': 0,
                    'fix': '',
                })
        else:
            results.append({
                'id': '1.4',
                'name': 'HTTP方法一致性',
                'level': 'info',
                'message': '无前端代码可供检查',
                'file': '',
                'line': 0,
                'fix': '',
            })
    else:
        results.append({
            'id': '1.4',
            'name': 'HTTP方法一致性',
            'level': 'info',
            'message': '需人工验证前后端HTTP方法(GET/POST)一致性',
            'file': '',
            'line': 0,
            'fix': '',
        })

    return results


# ===== 1.5 鉴权标注完整性 =====
def check_1_5_auth_middleware(context) -> List[Dict]:
    """1.5 鉴权标注完整性 - 检查是否有统一鉴权中间件"""
    results = []

    be_content = _get_backend_content(context)
    if be_content:
        has_auth_middleware = "auth_middleware" in be_content
        if not has_auth_middleware:
            results.append({
                'id': '1.5',
                'name': '鉴权标注完整性',
                'level': 'error',
                'message': '未发现统一鉴权中间件，接口可能裸奔',
                'file': '',
                'line': 0,
                'fix': '实现统一鉴权中间件，保护所有API接口',
            })

    return results


# ===== 1.6 API Base URL真实性 =====
def check_1_6_api_base_url(context) -> List[Dict]:
    """1.6 API Base URL真实性 - 前端是否指向真实后端而非mock/localhost"""
    results = []
    api_base_issues = []

    if not context.project_path or not os.path.isdir(context.project_path):
        return results

    # Electron项目可能使用IPC通信，检测后跳过URL检查
    if context.is_electron():
        all_js = context.find_files([".js", ".ts"])
        has_ipc = False
        for jf in all_js:
            content = context.safe_read(jf)
            if re.search(r'ipcRenderer\.invoke|ipcRenderer\.send', content):
                has_ipc = True
                break
        if has_ipc:
            # Electron项目使用IPC通信，URL检查跳过
            return results

    js_files = context.find_files([".js", ".ts"])
    for f in js_files:
        content = context.safe_read(f)
        basename = os.path.basename(f)
        if basename in ("api.js", "config.js", "env.js", "request.js"):
            # Check for localhost/mock/test URLs in API base
            for i, line in enumerate(content.split('\n'), 1):
                if re.search(r'(apiBase|baseUrl|BASE_URL|API_URL)\s*[=:]\s*["\']', line):
                    if re.search(r'localhost|127\.0\.0\.1|0\.0\.0\.0|mock|test.*url|placeholder', line, re.IGNORECASE):
                        if not re.search(r'placeholderText|//.*comment', line):
                            api_base_issues.append(f"{basename}:{i} {line.strip()[:60]}")

    if api_base_issues:
        results.append({
            'id': '1.6',
            'name': 'API Base URL真实性',
            'level': 'error',
            'message': f"{len(api_base_issues)}处API地址指向本地/mock",
            'detail': "\n".join(api_base_issues[:5]),
            'file': '',
            'line': 0,
            'fix': '替换为生产环境API地址',
        })

    return results


# ===== 1.7 API请求封装完整性 =====
def check_1_7_api_wrapper_completeness(context) -> List[Dict]:
    """1.7 API请求封装完整性 - 是否有统一错误处理和加载状态"""
    results = []
    api_wrapper_issues = []

    if not context.project_path or not os.path.isdir(context.project_path):
        return results

    # 扩展检测范围：小程序用api.js/request.js，Electron用ipc.js/renderer.js/preload.js
    check_files = ("api.js", "request.js", "http.js", "ipc.js", "renderer.js", "preload.js")
    for kf in check_files:
        fp = os.path.join(context.project_path, kf)
        if os.path.isfile(fp):
            content = context.safe_read(fp)
            has_error_handler = bool(re.search(r'fail\s*[:=]|\.catch|onError|showToast.*失败|showModal.*错误|console\.error', content))
            has_loading = bool(re.search(r'wx\.showLoading|loading|spinner|Skeleton', content, re.IGNORECASE))
            if not has_error_handler:
                api_wrapper_issues.append(f"{kf}缺少统一错误处理")
            if not has_loading:
                api_wrapper_issues.append(f"{kf}缺少加载状态提示")
            break

    if api_wrapper_issues:
        results.append({
            'id': '1.7',
            'name': 'API请求封装完整性',
            'level': 'warning',
            'message': f"{len(api_wrapper_issues)}个封装问题",
            'detail': "\n".join(api_wrapper_issues),
            'file': '',
            'line': 0,
            'fix': 'API封装层应包含统一错误处理和加载状态',
        })

    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': '1.0',
        'name': '后端架构检测',
        'level': 'suggestion',
        'category': 'api_linkage',
        'module_id': '1',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'miniprogram', 'web'],
        'description': '识别后端架构类型（统一入口/多引擎架构/Flask装饰器等）',
        'check': check_1_0_arch_detection,
    },
    {
        'id': '1.1',
        'name': '后端路由→前端调用映射完整性',
        'level': 'problem',
        'category': 'api_linkage',
        'module_id': '1',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'miniprogram', 'web'],
        'description': '检查后端路由是否都有前端调用，识别可能的白写路由',
        'check': check_1_1_backend_orphan_routes,
    },
    {
        'id': '1.2',
        'name': '前端调用→后端路由映射',
        'level': 'blocking',
        'category': 'api_linkage',
        'module_id': '1',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'miniprogram', 'web'],
        'description': '检查前端调用的API是否都有对应的后端接口',
        'check': check_1_2_frontend_ghost_calls,
    },
    {
        'id': '1.3',
        'name': 'API路径拼写一致性',
        'level': 'problem',
        'category': 'api_linkage',
        'module_id': '1',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'miniprogram', 'web'],
        'description': '检查前后端API路径命名风格是否一致（连字符vs下划线）',
        'check': check_1_3_path_naming_consistency,
    },
    {
        'id': '1.4',
        'name': 'HTTP方法一致性',
        'level': 'suggestion',
        'category': 'api_linkage',
        'module_id': '1',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'miniprogram', 'web'],
        'description': '检查前后端HTTP方法(GET/POST)一致性',
        'check': check_1_4_http_method_consistency,
    },
    {
        'id': '1.5',
        'name': '鉴权标注完整性',
        'level': 'blocking',
        'category': 'api_linkage',
        'module_id': '1',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron'],
        'description': '检查是否有统一鉴权中间件，防止接口裸奔',
        'check': check_1_5_auth_middleware,
    },
    {
        'id': '1.6',
        'name': 'API Base URL真实性',
        'level': 'blocking',
        'category': 'api_linkage',
        'module_id': '1',
        'applicable_types': ['miniprogram', 'web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查前端API地址是否指向真实后端而非mock/localhost',
        'check': check_1_6_api_base_url,
    },
    {
        'id': '1.7',
        'name': 'API请求封装完整性',
        'level': 'problem',
        'category': 'api_linkage',
        'module_id': '1',
        'applicable_types': ['miniprogram', 'web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查API请求封装是否包含统一错误处理和加载状态',
        'check': check_1_7_api_wrapper_completeness,
    },
]
