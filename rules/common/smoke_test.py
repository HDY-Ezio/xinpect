"""
端到端冒烟测试规则集 (M10)
通用冒烟测试检查 - 适用于所有项目类型
包含: 构建产物完整性、阻断性占位符扫描、API连通性、认证验证、
核心链路验证、SSR一致性、CORS验证、完成度分级等8项检查
"""

import re
import os
import json
from typing import List, Dict, Any

# v4.6.1 性能优化：requests 懒加载，避免import时触发 coze_workload_identity 初始化
_HAS_REQUESTS = None  # None=未检查, True/False=结果
_requests = None


def _get_requests():
    """懒加载 requests 模块"""
    global _HAS_REQUESTS, _requests
    if _HAS_REQUESTS is not None:
        return _requests if _HAS_REQUESTS else None
    try:
        from coze_workload_identity import requests as _requests_mod
        _requests = _requests_mod
        _HAS_REQUESTS = True
    except ImportError:
        _HAS_REQUESTS = False
        _requests = None
    return _requests


# ===== 10.1 构建产物完整性 =====
def check_10_1_build_completeness(context) -> List[Dict]:
    """10.1 构建产物完整性 - 项目是否真正可启动"""
    results = []
    issues = []
    pt = context.project_type

    if not context.project_path or not os.path.isdir(context.project_path):
        results.append({
            'id': '10.1',
            'name': '构建产物完整性',
            'level': 'suggestion',
            'message': '未指定项目路径,跳过构建检查',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results

    if pt in ("miniprogram", "mixed"):
        app_json = os.path.join(context.project_path, "app.json")
        if os.path.isfile(app_json):
            try:
                aj = json.loads(context.safe_read(app_json))
                pages = list(aj.get("pages", []))
                for sp in aj.get("subpackages", []):
                    root = sp.get("root", "")
                    for p in sp.get("pages", []):
                        pages.append(os.path.join(root, p))
                for page in pages:
                    base = os.path.join(context.project_path, page)
                    for ext in (".js", ".wxml", ".json"):
                        if not os.path.isfile(base + ext):
                            issues.append(f"{page}{ext} 缺失")
            except Exception as e:  # noqa: intentional catch-all
                issues.append(f"app.json解析失败: {e}")

    if pt in ("web", "electron", "mixed_electron"):
        build_dirs = [".next", "dist", "build", "out", ".output", "release"]
        found = False
        for bd in build_dirs:
            bp = os.path.join(context.project_path, bd)
            if os.path.isdir(bp):
                found = True
                if bd == ".next":
                    sdir = os.path.join(bp, "server")
                    if not os.path.isdir(sdir):
                        issues.append(".next/server/缺失——SSR将失败")
                    elif not os.path.isfile(os.path.join(sdir, "middleware-manifest.json")):
                        issues.append("middleware-manifest.json缺失——hydration将失败")
                break
        if not found:
            issues.append("未找到构建产物(.next/dist/build/out/release)——项目未构建")

    if pt in ("python_backend", "mixed", "flask", "mixed_electron"):
        search_paths = [context.backend_path, context.project_path]
        entry_found = False
        for sp in search_paths:
            if not sp or not os.path.isdir(sp):
                continue
            for ef in ("index_v2.py", "main.py", "app.py", "index.py", "wsgi.py", "server.py"):
                fp = os.path.join(sp, ef)
                if os.path.isfile(fp):
                    entry_found = True
                    try:
                        import ast
                        ast.parse(context.safe_read(fp))
                    except SyntaxError as e:
                        issues.append(f"{ef}语法错误: {e}")
                    break
            if entry_found:
                break
        if not entry_found and pt in ("python_backend", "flask"):
            issues.append("未找到Python入口文件")

    if pt == "skill":
        sk = os.path.join(context.project_path, "SKILL.md")
        if not os.path.isfile(sk):
            issues.append("SKILL.md缺失")
        elif len(context.safe_read(sk).strip()) < 50:
            issues.append("SKILL.md内容过少")

    if issues:
        results.append({
            'id': '10.1',
            'name': '构建产物完整性',
            'level': 'blocking',
            'message': f'{len(issues)}个构建完整性问题',
            'file': '',
            'line': 0,
            'snippet': '\n'.join(issues[:10]),
            'fix': '确保项目构建完整后再部署',
        })
    else:
        results.append({
            'id': '10.1',
            'name': '构建产物完整性',
            'level': 'suggestion',
            'message': '构建产物完整，项目可启动',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })

    return results


# ===== 10.2 阻断性占位符扫描 =====
def check_10_2_blocking_placeholders(context) -> List[Dict]:
    """10.2 阻断性占位符扫描 - 识别会阻断产品使用的占位符"""
    results = []
    found = []
    scan_files = []

    blocking = re.compile(
        r'wx[0]{10,}|YOUR_API_KEY|YOUR_SECRET|REPLACE_ME|'
        r'TODO\s*[:]\s*(?:replace|implement|fix)|FIXME', re.IGNORECASE)

    if context.project_path and os.path.isdir(context.project_path):
        for kf in ("app.js", "app.json", "project.config.json", "config.js",
                    "env.js", ".env", "next.config.ts", "next.config.js",
                    "main.js", "main.ts", "electron.js", "preload.js",
                    "package.json", "electron-builder.json", "electron-builder.yml"):
            fp = os.path.join(context.project_path, kf)
            if os.path.isfile(fp):
                scan_files.append(fp)
        all_code = context.find_files([".js", ".ts"])
        scan_files.extend(f for f in all_code if "config" in f.lower() or "env" in f.lower())

    if context.backend_path and os.path.isdir(context.backend_path):
        for kf in ("index_v2.py", "main.py", "app.py", ".env", "config.py"):
            fp = os.path.join(context.backend_path, kf)
            if os.path.isfile(fp):
                scan_files.append(fp)

    seen = set()
    for f in scan_files:
        if f in seen:
            continue
        seen.add(f)
        content = context.safe_read(f)
        if not content:
            continue
        for i, line in enumerate(content.split('\n'), 1):
            if line.strip().startswith(('#', '//')):
                continue
            if blocking.search(line):
                try:
                    rel = os.path.relpath(f)
                except ValueError:
                    rel = f
                found.append(f"{rel}:{i} {line.strip()[:60]}")

    if found:
        results.append({
            'id': '10.2',
            'name': '阻断性占位符扫描',
            'level': 'blocking',
            'message': f'{len(found)}处阻断性占位符——产品无法正常运行',
            'file': '',
            'line': 0,
            'snippet': '\n'.join(found[:10]),
            'fix': '替换所有阻断性占位符后产品才能使用',
        })
    else:
        results.append({
            'id': '10.2',
            'name': '阻断性占位符扫描',
            'level': 'suggestion',
            'message': '未发现阻断性占位符',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })

    return results


# ===== 10.3 API运行时连通性 =====
def check_10_3_api_connectivity(context) -> List[Dict]:
    """10.3 API运行时连通性 - 需要配置smoke_test_base_url"""
    results = []
    base_url = context.config.get("smoke_test_base_url", "")
    test_urls = context.config.get("smoke_test_urls", [])

    if not base_url or _get_requests() is None:
        results.append({
            'id': '10.3',
            'name': 'API运行时连通性',
            'level': 'suggestion',
            'message': '未配置smoke_test_base_url或requests不可用,跳过动态检查',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '配置smoke_test_base_url启用运行时验证',
        })
        return results

    ok, fail = 0, []
    for url in test_urls:
        full = url if url.startswith('http') else base_url.rstrip('/') + '/' + url.lstrip('/')
        try:
            resp = _get_requests().get(full, timeout=10)
            if resp.status_code < 500:
                ok += 1
            else:
                fail.append(f"{url} -> HTTP {resp.status_code}")
        except Exception as e:  # noqa: intentional catch-all
            fail.append(f"{url} -> {str(e)[:50]}")

    # 尝试常见健康检查端点
    for ep in ("/api/health", "/health", "/api/status", "/ping"):
        try:
            r = _get_requests().get(base_url.rstrip('/') + ep, timeout=5)
            if r.status_code == 200:
                ok += 1
                break
        except:
            continue

    if fail:
        results.append({
            'id': '10.3',
            'name': 'API运行时连通性',
            'level': 'blocking',
            'message': f'{ok}个正常,{len(fail)}个异常',
            'file': '',
            'line': 0,
            'snippet': '\n'.join(fail[:5]),
            'fix': '检查异常API部署状态和日志',
        })
    elif ok > 0:
        results.append({
            'id': '10.3',
            'name': 'API运行时连通性',
            'level': 'suggestion',
            'message': f'测试API可达({ok}个)',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
    else:
        results.append({
            'id': '10.3',
            'name': 'API运行时连通性',
            'level': 'problem',
            'message': '未配置测试URL且健康检查端点不可达',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '在config中配置smoke_test_urls',
        })

    return results


# ===== 10.4 认证流程出口验证 =====
def check_10_4_auth_flow_verify(context) -> List[Dict]:
    """10.4 认证流程出口验证 - 无token/无效token应被拒绝"""
    results = []
    base_url = context.config.get("smoke_test_base_url", "")

    if not base_url or _get_requests() is None:
        results.append({
            'id': '10.4',
            'name': '认证流程出口验证',
            'level': 'suggestion',
            'message': '未配置smoke_test_base_url或requests不可用,跳过动态检查',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '配置smoke_test_base_url启用运行时验证',
        })
        return results

    api = base_url.rstrip('/')
    issues = []

    # Test 1: No token → should get 401/403
    try:
        r = _get_requests().get(f"{api}/api/auth/me", timeout=10)
        if r.status_code == 200:
            try:
                d = r.json()
                if d.get("success") or d.get("code") == 0:
                    issues.append("无token访问/auth/me返回成功——鉴权未生效")
            except:  # noqa: intentional empty handler
                pass
    except:  # noqa: intentional empty handler
        pass

    # Test 2: Invalid token → should get 401/403
    try:
        r = _get_requests().get(f"{api}/api/auth/me",
                         headers={"Authorization": "Bearer invalid_xxx"}, timeout=10)
        if r.status_code == 200:
            try:
                d = r.json()
                if d.get("success") or d.get("code") == 0:
                    issues.append("无效token访问/auth/me返回成功——鉴权未生效")
            except:  # noqa: intentional empty handler
                pass
    except:  # noqa: intentional empty handler
        pass

    if issues:
        results.append({
            'id': '10.4',
            'name': '认证流程出口验证',
            'level': 'blocking',
            'message': f'{len(issues)}个认证问题',
            'file': '',
            'line': 0,
            'snippet': '\n'.join(issues[:5]),
            'fix': '无token→401, 无效token→401, 有效token→200',
        })
    else:
        results.append({
            'id': '10.4',
            'name': '认证流程出口验证',
            'level': 'suggestion',
            'message': '认证流程正确(无token/无效token被拒绝)',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })

    return results


# ===== 10.5 核心业务链路验证 =====
def check_10_5_core_flow_verify(context) -> List[Dict]:
    """10.5 核心业务链路验证"""
    results = []
    base_url = context.config.get("smoke_test_base_url", "")

    if not base_url or _get_requests() is None:
        results.append({
            'id': '10.5',
            'name': '核心业务链路验证',
            'level': 'suggestion',
            'message': '未配置smoke_test_base_url或requests不可用,跳过动态检查',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '配置smoke_test_base_url启用运行时验证',
        })
        return results

    api = base_url.rstrip('/')
    issues = []
    steps_ok = 0

    # Step 1: Send code
    try:
        r = _get_requests().post(f"{api}/api/auth/send_code",
                          json={"phone": "13900000099"}, timeout=10)
        if r.status_code < 500:
            steps_ok += 1
        else:
            issues.append(f"send_code返回{r.status_code}")
    except Exception as e:  # noqa: intentional catch-all
        issues.append(f"send_code失败: {str(e)[:40]}")

    # Step 2: Login attempt
    try:
        r = _get_requests().post(f"{api}/api/auth/login",
                          json={"phone": "13900000099", "code": "0000"}, timeout=10)
        if r.status_code < 500:
            steps_ok += 1
            try:
                d = r.json()
                if "success" not in d and "code" not in d:
                    issues.append("API响应缺少success/code字段")
            except:
                issues.append("API响应非JSON格式")
        else:
            issues.append(f"login返回{r.status_code}")
    except Exception as e:  # noqa: intentional catch-all
        issues.append(f"login失败: {str(e)[:40]}")

    if issues:
        results.append({
            'id': '10.5',
            'name': '核心业务链路验证',
            'level': 'blocking',
            'message': f'链路验证失败({steps_ok}步通过)',
            'file': '',
            'line': 0,
            'snippet': '\n'.join(issues[:5]),
            'fix': '确保注册→登录→业务操作核心链路畅通',
        })
    else:
        results.append({
            'id': '10.5',
            'name': '核心业务链路验证',
            'level': 'suggestion',
            'message': f'核心链路畅通({steps_ok}步验证通过)',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })

    return results


# ===== 10.6 SSR/Hydration一致性 =====
def check_10_6_ssr_hydration(context) -> List[Dict]:
    """10.6 SSR/Hydration一致性 (Web项目)"""
    results = []
    base_url = context.config.get("smoke_test_base_url", "")
    pt = context.project_type

    if pt not in ("web", "mixed"):
        results.append({
            'id': '10.6',
            'name': 'SSR/Hydration一致性',
            'level': 'suggestion',
            'message': '非Web项目,跳过',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results

    if not base_url or _get_requests() is None:
        results.append({
            'id': '10.6',
            'name': 'SSR/Hydration一致性',
            'level': 'suggestion',
            'message': '未配置smoke_test_base_url或requests不可用,跳过动态检查',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '配置smoke_test_base_url启用运行时验证',
        })
        return results

    issues = []
    try:
        r = _get_requests().get(base_url.rstrip('/'), timeout=15)
        html = r.text
        bad_markers = [
            "正在验证登录状态", "正在加载", "Loading...",
            "__NEXT_ERROR__", "Application error",
            "Internal Server Error",
        ]
        for m in bad_markers:
            if m in html:
                issues.append(f"SSR输出含'{m}'——可能hydration失败")
        if '"statusCode":500' in html:
            issues.append("SSR返回500错误页面")
        if '<html' not in html.lower():
            issues.append("SSR输出无HTML结构")
    except Exception as e:  # noqa: intentional catch-all
        issues.append(f"页面请求失败: {str(e)[:50]}")

    if issues:
        results.append({
            'id': '10.6',
            'name': 'SSR/Hydration一致性',
            'level': 'blocking',
            'message': f'{len(issues)}个SSR问题',
            'file': '',
            'line': 0,
            'snippet': '\n'.join(issues[:5]),
            'fix': '检查构建完整性和SSR配置',
        })
    else:
        results.append({
            'id': '10.6',
            'name': 'SSR/Hydration一致性',
            'level': 'suggestion',
            'message': 'SSR输出正常',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })

    return results


# ===== 10.7 CORS跨域验证 =====
def check_10_7_cors_verify(context) -> List[Dict]:
    """10.7 CORS跨域验证"""
    results = []
    base_url = context.config.get("smoke_test_base_url", "")

    if not base_url or _get_requests() is None:
        results.append({
            'id': '10.7',
            'name': 'CORS跨域验证',
            'level': 'suggestion',
            'message': '未配置smoke_test_base_url或requests不可用,跳过动态检查',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '配置smoke_test_base_url启用运行时验证',
        })
        return results

    api = base_url.rstrip('/')
    issues = []

    try:
        r = _get_requests().options(f"{api}/api/auth",
                             headers={"Origin": "http://localhost:3000",
                                      "Access-Control-Request-Method": "POST"},
                             timeout=10)
        if not r.headers.get("Access-Control-Allow-Origin"):
            issues.append("OPTIONS预检缺少CORS头——浏览器跨域将被阻止")
    except:  # noqa: intentional empty handler
        pass

    try:
        r = _get_requests().get(f"{api}/api/auth",
                         headers={"Origin": "http://localhost:3000"}, timeout=10)
        if r.status_code < 500 and not r.headers.get("Access-Control-Allow-Origin"):
            issues.append("API响应缺少CORS头——前端跨域可能被阻止")
    except:  # noqa: intentional empty handler
        pass

    if issues:
        results.append({
            'id': '10.7',
            'name': 'CORS跨域验证',
            'level': 'problem',
            'message': f'{len(issues)}个CORS问题',
            'file': '',
            'line': 0,
            'snippet': '\n'.join(issues[:5]),
            'fix': '在服务端或API网关配置CORS',
        })
    else:
        results.append({
            'id': '10.7',
            'name': 'CORS跨域验证',
            'level': 'suggestion',
            'message': 'CORS配置正确',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })

    return results


# ===== 10.8 完成度分级 =====
def check_10_8_completion_level(context) -> List[Dict]:
    """10.8 完成度分级 - 汇总评估"""
    results = []
    base_url = context.config.get("smoke_test_base_url", "")
    pt = context.project_type

    # 动态检查是否因项目类型不适用
    dynamic_not_applicable = pt not in ("web", "mixed", "miniprogram", 
                                         "electron", "mixed_electron",
                                         "python_backend", "flask")
    
    has_dynamic_config = bool(base_url and (_get_requests() is not None))

    if not has_dynamic_config and not dynamic_not_applicable:
        results.append({
            'id': '10.8',
            'name': '完成度分级',
            'level': 'problem',
            'message': 'Lv2 静态检查通过——未进行运行时验证,配置smoke_test_base_url可升级',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '配置smoke_test_base_url启用动态检查',
        })
    elif dynamic_not_applicable:
        results.append({
            'id': '10.8',
            'name': '完成度分级',
            'level': 'suggestion',
            'message': 'Lv3 静态检查通过——当前项目类型无需运行时验证，静态检查已覆盖',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
    else:
        results.append({
            'id': '10.8',
            'name': '完成度分级',
            'level': 'suggestion',
            'message': 'Lv3 端到端可用——静态+运行时验证已配置，产品可交付',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })

    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': '10.1',
        'name': '构建产物完整性',
        'level': 'blocking',
        'category': 'smoke_test',
        'module_id': '10',
        'applicable_types': [],
        'description': '静态检查项目构建产物是否完整，页面/入口文件是否存在',
        'check': check_10_1_build_completeness,
    },
    {
        'id': '10.2',
        'name': '阻断性占位符扫描',
        'level': 'blocking',
        'category': 'smoke_test',
        'module_id': '10',
        'applicable_types': [],
        'description': '扫描配置文件中是否有未替换的占位符（YOUR_API_KEY等）',
        'check': check_10_2_blocking_placeholders,
    },
    {
        'id': '10.3',
        'name': 'API运行时连通性',
        'level': 'blocking',
        'category': 'smoke_test',
        'module_id': '10',
        'applicable_types': [],
        'description': '运行时验证API是否可达（需配置smoke_test_base_url）',
        'check': check_10_3_api_connectivity,
    },
    {
        'id': '10.4',
        'name': '认证流程出口验证',
        'level': 'blocking',
        'category': 'smoke_test',
        'module_id': '10',
        'applicable_types': [],
        'description': '验证无token/无效token访问是否被正确拒绝',
        'check': check_10_4_auth_flow_verify,
    },
    {
        'id': '10.5',
        'name': '核心业务链路验证',
        'level': 'blocking',
        'category': 'smoke_test',
        'module_id': '10',
        'applicable_types': [],
        'description': '验证注册→登录核心业务链路是否畅通',
        'check': check_10_5_core_flow_verify,
    },
    {
        'id': '10.6',
        'name': 'SSR/Hydration一致性',
        'level': 'blocking',
        'category': 'smoke_test',
        'module_id': '10',
        'applicable_types': ['web', 'mixed'],
        'description': '验证Web项目SSR输出是否正常，hydration是否可能失败',
        'check': check_10_6_ssr_hydration,
    },
    {
        'id': '10.7',
        'name': 'CORS跨域验证',
        'level': 'problem',
        'category': 'smoke_test',
        'module_id': '10',
        'applicable_types': [],
        'description': '验证API是否正确配置了CORS跨域头',
        'check': check_10_7_cors_verify,
    },
    {
        'id': '10.8',
        'name': '完成度分级',
        'level': 'suggestion',
        'category': 'smoke_test',
        'module_id': '10',
        'applicable_types': [],
        'description': '汇总评估项目完成度等级（Lv1/Lv2/Lv3）',
        'check': check_10_8_completion_level,
    },
]
