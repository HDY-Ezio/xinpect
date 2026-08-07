"""
错误处理与韧性规则集 - 可观测性与响应子模块 (M13)
从 error_handling.py 拆分而来，包含:
  13.6 健康检查端点 - /health 或 /ping 端点配置
  13.7 日志质量 - 敏感数据日志、console.log生产残留
  13.8 错误响应标准化 - 统一的{code, message, data}格式
  13.9 小程序组件依赖完整性 - usingComponents引用存在性检查
"""

import re
import os
import json
from typing import List, Dict, Any
from collections import defaultdict


# ===== 工具依赖（误报过滤增强） =====
try:
    from core.utils import is_ops_script, is_mock_context
    _HAS_UTILS = True
except ImportError:
    # 兼容旧架构的独立导入路径
    try:
        from architecture_detector import is_ops_script
        from context_analyzer import is_mock_context
        _HAS_UTILS = True
    except ImportError:
        _HAS_UTILS = False


# 敏感数据日志模式
SENSITIVE_LOG_PATTERNS = [
    r'(?:password|passwd|pwd)\s*[=:]\s*["\'][^"\']+["\']',
    r'(?:secret|api_key|apikey|api-key)\s*[=:]\s*["\'][^"\']+["\']',
    r'(?:token|authorization)\s*[=:]\s*["\'][^"\']+["\']',
    r'print\s*\(\s*f?["\'].*(?:password|secret|token|key).*["\']',
    r'console\.(log|debug|info)\s*\(.*(?:password|secret|token|key|credential).*\)',
    r'logging\.\w+\s*\(.*(?:password|secret|token|key|credential).*\)',
]

def _get_frontend_files(context) -> List[str]:
    """获取前端文件列表（根据项目类型）"""
    if not context.project_path or not os.path.isdir(context.project_path):
        return []
    if context.is_web_frontend():
        return context.find_files([".tsx", ".jsx", ".ts", ".js"])
    else:
        return context.find_files([".js", ".wxml"])


def check_13_6_health_endpoint(context) -> List[Dict]:
    """13.6 健康检查端点 - /health或/ping"""
    results = []
    backend_files = context.get_backend_py_files()

    if not backend_files:
        return results

    found = False
    for f in backend_files:
        content = context.safe_read(f)
        if re.search(r'["\']/(health|ping|healthz|status)["\']', content, re.IGNORECASE):
            found = True
            break
        if re.search(r'def\s+(health|ping|healthz)\b', content, re.IGNORECASE):
            found = True
            break

    if not found:
        results.append({
            'id': '13.6',
            'name': '健康检查端点',
            'level': 'warning',
            'message': '未检测到健康检查端点(/health或/ping)',
            'file': '',
            'line': 0,
            'fix': '添加GET /health端点返回{"status":"ok"}，供负载均衡和监控使用',
        })

    return results


# ===== 13.7 日志质量 =====


def check_13_7_logging_quality(context) -> List[Dict]:
    """13.7 日志质量 - 敏感数据入日志、生产环境console.log"""
    results = []
    issues = []
    pending_verify = []

    backend_files = context.get_backend_py_files()
    front_files = _get_frontend_files(context)
    all_files = backend_files + front_files

    if not all_files:
        return results

    # 排除测试文件和运维脚本
    skip_patterns = ['test_', '_test.py', 'test/', 'tests/', '/test_']
    skip_patterns += context.config.get('log_skip_patterns', [])

    filtered_files = []
    skipped_ops = 0
    for f in all_files:
        skip = False
        for pat in skip_patterns:
            if pat in f:
                skip = True
                break
        # 跳过运维补丁脚本
        if not skip and _HAS_UTILS:
            try:
                if is_ops_script(f):
                    skipped_ops += 1
                    skip = True
            except Exception as e:  # noqa: broad exception handling
                pass
        if not skip:
            filtered_files.append(f)

    # 逐文件检测，跳过注释行
    log_skip_comments = context.config.get('log_skip_comments', True)

    # 敏感字段模式，用于识别具体泄露了什么
    sensitive_field_patterns = {
        "password": r'password|passwd|pwd',
        "api_key": r'api[_-]?key|apikey',
        "secret": r'secret|token',
        "email": r'email|邮箱',
        "phone": r'phone|mobile|手机号',
        "id_card": r'id[_-]?card|身份证',
        "private_key": r'private[_-]?key',
    }

    for f in filtered_files:
        content = context.safe_read(f)
        lines = content.split('\n')
        fname = os.path.basename(f)

        for pattern in SENSITIVE_LOG_PATTERNS:
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                # 跳过注释行
                if log_skip_comments:
                    if f.endswith('.py') and stripped.startswith('#'):
                        continue
                    if f.endswith('.js') and (stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*')):
                        continue
                # 必须是日志输出相关的行
                has_log = bool(re.search(
                    r'(print|console\.log|logger\.|logging\.|log\.|debug\(|info\(|warning\(|error\()',
                    line, re.IGNORECASE
                ))
                if not has_log:
                    continue
                if re.search(pattern, line, re.IGNORECASE):
                    # 识别具体泄露的字段名
                    leaked_fields = []
                    line_lower = line.lower()
                    for field_name, field_pat in sensitive_field_patterns.items():
                        if re.search(field_pat, line_lower):
                            leaked_fields.append(field_name)

                    # 检查是否是mock/test日志
                    is_mock_log = False
                    if _HAS_UTILS:
                        ctx_start = max(0, i - 6)
                        ctx_end = min(len(lines), i + 3)
                        context_lines = lines[ctx_start:ctx_end]
                        try:
                            if is_mock_context(line, context_lines):
                                is_mock_log = True
                        except Exception as e:  # noqa: broad exception handling
                            pass

                    if is_mock_log:
                        continue

                    if leaked_fields:
                        field_str = "、".join(leaked_fields[:3])
                        issues.append(f"{fname}:{i} 日志可能泄露{field_str}等敏感字段")
                    else:
                        # 匹配到了模式但无法确定具体字段 → 待确认，不计入问题
                        pending_verify.append(f"{fname}:{i} 日志含疑似敏感词，需人工确认")

    # 前端: 生产环境console.log
    if front_files and context.is_web_frontend():
        prod_console = 0
        for f in front_files:
            content = context.safe_read(f)
            if 'console.log' in content and '.test.' not in f and '.spec.' not in f:
                count = len(re.findall(r'console\.log\s*\(', content))
                if count > 0:
                    prod_console += count
        if prod_console > 10:
            issues.append(f"Web前端有{prod_console}处console.log(生产环境应移除或使用条件判断)")

    if issues:
        level = "warning"
        detail = "\n".join(issues[:15])
        if pending_verify:
            detail += f"\n--- 另有 {len(pending_verify)} 处待人工确认（不计入扣分）---"
        if skipped_ops > 0:
            detail += f"\n--- 已跳过{skipped_ops}个运维补丁脚本 ---"
        results.append({
            'id': '13.7',
            'name': '日志质量',
            'level': level,
            'message': f"发现{len(issues)}处日志质量问题",
            'detail': detail,
            'file': '',
            'line': 0,
            'fix': '移除日志中的敏感数据；生产环境移除console.log或使用LOG_LEVEL条件判断',
        })
    elif pending_verify:
        results.append({
            'id': '13.7',
            'name': '日志质量',
            'level': 'info',
            'message': f"未发现确定的日志质量问题，另有{len(pending_verify)}处待人工确认",
            'detail': "\n".join(pending_verify[:10]),
            'file': '',
            'line': 0,
            'fix': '建议人工确认待检查项是否确实包含敏感数据',
        })

    return results


# ===== 13.8 错误响应标准化 =====


def check_13_8_error_response_format(context) -> List[Dict]:
    """13.8 错误响应标准化 - 错误返回格式一致性"""
    results = []
    backend_files = context.get_backend_py_files()

    if not backend_files:
        return results

    all_content = ""
    for f in backend_files:
        all_content += context.safe_read(f) + "\n"

    # 检查是否有统一的错误响应格式
    has_error_code = bool(re.search(r'"code"\s*:', all_content))
    has_error_msg = bool(re.search(r'"message"\s*:|\"msg\"\s*:', all_content))
    has_error_detail = bool(re.search(r'"detail"\s*:|\"data\"\s*:', all_content))

    # 检查不一致的error response模式
    inconsistent = 0
    # 排除内部函数返回格式和日志中的error
    content_clean = re.sub(r'"success"\s*:\s*False.*?"error"\s*:\s*[^}]+}', '', all_content)
    content_clean = re.sub(r'"level"\s*:\s*"error"', '', content_clean)
    content_clean = re.sub(r'"severity"\s*:\s*"error"', '', content_clean)
    content_clean = re.sub(r'"status"\s*:\s*"error"', '', content_clean)
    content_clean = re.sub(r'\.get\("error"', '', content_clean)
    content_clean = re.sub(r'\.get\(\'error\'', '', content_clean)
    # 排除非响应格式的error键
    content_clean = re.sub(r'"error"\s*:\s*(?:error|None|err|e)\b', '', content_clean)
    if re.search(r'["\']error["\']\s*:', content_clean) and has_error_code:
        inconsistent += 1
    # 有些地方直接return字符串错误
    direct_returns = len(re.findall(r'return\s+(?:jsonify\s*\()?\s*["\'][^"\']*error[^"\']*["\']', all_content, re.IGNORECASE))
    if direct_returns > 3:
        inconsistent += direct_returns

    if inconsistent > 0:
        results.append({
            'id': '13.8',
            'name': '错误响应标准化',
            'level': 'warning',
            'message': f"发现{inconsistent}处错误响应格式不一致",
            'detail': "混用{'error': msg}和{'code': xxx, 'message': msg}格式",
            'file': '',
            'line': 0,
            'fix': '统一使用{code, message, data}格式，所有错误通过统一中间件返回',
        })
    elif not (has_error_code and has_error_msg):
        results.append({
            'id': '13.8',
            'name': '错误响应标准化',
            'level': 'warning',
            'message': '未检测到标准化的错误响应格式',
            'file': '',
            'line': 0,
            'fix': '定义统一错误响应格式{code: int, message: str, data: any}，所有API错误通过统一中间件返回',
        })

    return results


# ===== 13.9 小程序组件依赖完整性 =====


def check_13_9_miniprogram_components(context) -> List[Dict]:
    """13.9 小程序组件依赖完整性 - 检查usingComponents引用的组件是否存在"""
    results = []

    # 仅微信小程序项目
    if context.project_type not in ("miniprogram", "mixed"):
        return results

    if not context.project_path or not os.path.isdir(context.project_path):
        return results

    issues = []
    # 扫描所有.json配置文件
    json_files = context.find_files([".json"])

    # 过滤掉非组件配置文件
    skip_names = {"package.json", "package-lock.json", "project.config.json",
                  "project.private.config.json", "sitemap.json", "qa_config.json"}
    config_json_files = []
    for jf in json_files:
        fname = os.path.basename(jf)
        if fname not in skip_names and not fname.endswith(".config.json"):
            config_json_files.append(jf)

    total_checked = 0
    missing_components = {}  # {文件相对路径: [缺失的组件名]}

    for jf in config_json_files:
        try:
            with open(jf, "r", encoding="utf-8") as fj:
                cfg = json.load(fj)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue

        using_components = cfg.get("usingComponents", {})
        if not using_components or not isinstance(using_components, dict):
            continue

        file_dir = os.path.dirname(jf)
        file_missing = []

        for comp_name, comp_path in using_components.items():
            total_checked += 1
            # 跳过插件组件（plugin://）
            if isinstance(comp_path, str) and comp_path.startswith("plugin://"):
                continue
            if not isinstance(comp_path, str):
                continue

            resolved = None
            # 绝对路径（以/开头，相对于项目根目录）
            if comp_path.startswith("/"):
                resolved = os.path.normpath(os.path.join(context.project_path, comp_path.lstrip("/")))
            # 相对路径
            elif comp_path.startswith("./") or comp_path.startswith("../"):
                resolved = os.path.normpath(os.path.join(file_dir, comp_path))
            # npm包路径（如@vant/weapp/button/index）
            elif "/" in comp_path and not comp_path.startswith("/"):
                # 先在 miniprogram_npm 找
                npm_path = os.path.normpath(os.path.join(context.project_path, "miniprogram_npm", comp_path))
                node_path = os.path.normpath(os.path.join(context.project_path, "node_modules", comp_path))
                if os.path.isdir(npm_path) or os.path.isfile(npm_path + ".js"):
                    resolved = npm_path
                elif os.path.isdir(node_path) or os.path.isfile(node_path + ".js"):
                    resolved = node_path
                else:
                    resolved = npm_path  # 用npm路径作为报告路径

            if resolved is None:
                continue  # 无法解析的路径跳过

            # 检查组件文件是否存在
            exists = False
            if os.path.isdir(resolved):
                # 目录型组件：检查index.js或同名文件
                base_name = os.path.basename(resolved)
                if (os.path.isfile(os.path.join(resolved, "index.js")) or
                    os.path.isfile(os.path.join(resolved, "index.json")) or
                    os.path.isfile(os.path.join(resolved, "index.wxml")) or
                    os.path.isfile(os.path.join(resolved, base_name + ".js"))):
                    exists = True
            elif os.path.isfile(resolved + ".js"):
                exists = True
            elif os.path.isfile(resolved):
                exists = True

            if not exists:
                file_missing.append(f"{comp_name} -> {comp_path}")

        if file_missing:
            rel_path = os.path.relpath(jf, context.project_path)
            missing_components[rel_path] = file_missing

    if missing_components:
        total_missing = sum(len(v) for v in missing_components.values())
        detail_lines = []
        for fp, comps in missing_components.items():
            detail_lines.append(f"{fp}: {', '.join(comps)}")
        results.append({
            'id': '13.9',
            'name': '小程序组件依赖完整性',
            'level': 'error',
            'message': f"发现{total_missing}个缺失组件，分布在{len(missing_components)}个文件中",
            'detail': "\n".join(detail_lines),
            'file': '',
            'line': 0,
            'fix': '执行npm构建生成miniprogram_npm，或检查usingComponents路径是否正确',
        })

    return results


# ===== 规则定义列表 =====


# ===== 规则定义列表 =====
RULES = [
    {
        'id': '13.6',
        'name': '健康检查端点',
        'level': 'problem',
        'category': 'error_handling',
        'module_id': '13',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检查后端是否配置了/health或/ping健康检查端点',
        'check': check_13_6_health_endpoint,
    },
    {
        'id': '13.7',
        'name': '日志质量',
        'level': 'problem',
        'category': 'error_handling',
        'module_id': '13',
        'applicable_types': [],
        'description': '检查日志中是否包含敏感数据、生产环境是否有console.log等',
        'check': check_13_7_logging_quality,
    },
    {
        'id': '13.8',
        'name': '错误响应标准化',
        'level': 'problem',
        'category': 'error_handling',
        'module_id': '13',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检查错误返回格式是否一致，是否使用统一的{code, message, data}格式',
        'check': check_13_8_error_response_format,
    },
    {
        'id': '13.9',
        'name': '小程序组件依赖完整性',
        'level': 'blocking',
        'category': 'error_handling',
        'module_id': '13',
        'applicable_types': ['miniprogram', 'mixed'],
        'description': '检查小程序usingComponents引用的组件是否真实存在',
        'check': check_13_9_miniprogram_components,
    },
]
