"""性能与资源规则集 - 运行时子模块
从 performance.py 拆分而来，包含内存泄漏、并发请求、Storage使用等运行时规则
"""

"""
性能与资源规则集 (M12)
通用性能检查 - 适用于所有项目类型
包含: 包体积、代码分割、图片优化、字体优化、内存泄漏、构建配置、
按需注入、节点数量、并发请求、Storage使用、内存告警、base64传输等12项检查
"""

import re
import os
import json
from typing import List, Dict, Any
from collections import defaultdict



# ===== 工具函数 =====
def _get_frontend_files(context) -> List[str]:
    """获取前端文件列表（根据项目类型）"""
    if not context.project_path or not os.path.isdir(context.project_path):
        return []
    if context.is_web_frontend():
        return context.find_files([".tsx", ".jsx", ".ts", ".js", ".css", ".scss", ".less"])
    else:
        return context.find_files([".js", ".wxml", ".wxss"])


def _get_threshold(context, key: str, default):
    """获取阈值配置"""
    thresholds = context.config.get("thresholds", {})
    return thresholds.get(key, default)


def _get_exclude_dirs(context) -> List[str]:
    """获取排除目录列表"""
    return context.config.get("exclude_dirs", ["node_modules", ".git", "dist", "build"])


# ===== 生命周期配对分析（供12.5使用）=====
def _analyze_lifecycle_pairing_miniprogram(file_path: str, content: str):
    """
    小程序生命周期配对分析
    分析页面/组件中定时器、事件监听等资源的创建-清除配对情况
    返回: (confirmed_leaks, suspicious, confirmed_safe)
    """
    lines = content.split('\n')
    basename = os.path.basename(file_path)
    is_app_js = basename == 'app.js'
    norm_path = file_path.replace(os.sep, '/')
    is_component = '/components/' in norm_path

    has_lifecycle = any(kw in content for kw in [
        'onUnload', 'onHide', 'onDetach', 'lifetimes', 'pageLifetimes'
    ])

    if is_app_js or '/utils/' in norm_path or '/libs/' in norm_path or '/lib/' in norm_path:
        return [], [], []

    if not has_lifecycle and not is_component:
        if 'Page(' not in content and 'Component(' not in content:
            return [], [], []

    results = {
        'setInterval': {'created_vars': [], 'created_anon': 0, 'cleared_vars': set()},
        'setTimeout': {'created_vars': [], 'created_anon': 0, 'cleared_vars': set()},
        'addEventListener': {'created': 0, 'has_remove': False},
    }

    # 1. 找出所有创建位置
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('//') or stripped.startswith('*') or stripped.startswith('/*'):
            continue

        for fn in ['setInterval', 'setTimeout']:
            m = re.search(r'(?:const|let|var)\s+(\w+)\s*=\s*' + fn + r'\s*\(', line)
            if m:
                results[fn]['created_vars'].append((m.group(1), i+1))
                continue
            m2 = re.search(r'this\.(\w+)\s*=\s*' + fn + r'\s*\(', line)
            if m2:
                results[fn]['created_vars'].append(('this.' + m2.group(1), i+1))
                continue
            if re.search(fn + r'\s*\(', line):
                results[fn]['created_anon'] += 1

        if re.search(r'\.addEventListener\s*\(', line):
            results['addEventListener']['created'] += 1

    # 2. 找出所有清除位置
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('//') or stripped.startswith('*'):
            continue

        for fn, clear_fn in [('setInterval', 'clearInterval'), ('setTimeout', 'clearTimeout')]:
            for m in re.finditer(clear_fn + r'\s*\(\s*(?:this\.)?(\w+)', line):
                var_name = m.group(1)
                if 'this.' + var_name in line[m.start():m.end()]:
                    results[fn]['cleared_vars'].add('this.' + var_name)
                else:
                    results[fn]['cleared_vars'].add(var_name)

        if 'removeEventListener' in line:
            results['addEventListener']['has_remove'] = True

    # 3. 检测生命周期中是否有清除操作
    lifecycle_hooks = {}
    current_hook = None
    hook_start = -1
    brace_depth = 0

    for i, line in enumerate(lines):
        hook_match = re.search(r'(onUnload|onHide|onDetach)\s*[:\(]', line)
        if hook_match and current_hook is None:
            current_hook = hook_match.group(1)
            hook_start = i
            brace_depth = line.count('{') - line.count('}')
            if brace_depth > 0:
                continue

        if current_hook is not None:
            brace_depth += line.count('{') - line.count('}')
            if brace_depth <= 0:
                lifecycle_hooks[current_hook] = (hook_start, i)
                current_hook = None

    unload_hooks = [h for h in ['onUnload', 'onHide', 'onDetach'] if h in lifecycle_hooks]

    lifecycle_clear_vars = {'setInterval': set(), 'setTimeout': set()}
    lifecycle_has_remove = False

    for hook_name in unload_hooks:
        start, end = lifecycle_hooks[hook_name]
        for j in range(start, min(end + 1, len(lines))):
            line = lines[j]
            for fn, clear_fn in [('setInterval', 'clearInterval'), ('setTimeout', 'clearTimeout')]:
                for m in re.finditer(clear_fn + r'\s*\(\s*(?:this\.)?(\w+)', line):
                    var_name = m.group(1)
                    if 'this.' + var_name in line[m.start():m.end()]:
                        lifecycle_clear_vars[fn].add('this.' + var_name)
                    else:
                        lifecycle_clear_vars[fn].add(var_name)
            if 'removeEventListener' in line:
                lifecycle_has_remove = True

    # 4. 匹配判定
    confirmed_leaks = []
    suspicious = []
    confirmed_safe = []

    # setInterval 分析
    for var_name, line_num in results['setInterval']['created_vars']:
        if var_name in lifecycle_clear_vars['setInterval']:
            confirmed_safe.append(f"setInterval({var_name}): 生命周期内清除")
        elif var_name in results['setInterval']['cleared_vars']:
            suspicious.append(f"setInterval({var_name}): 有清除但不在卸载生命周期")
        else:
            confirmed_leaks.append(f"setInterval({var_name}): 无对应clearInterval")

    if results['setInterval']['created_anon'] > 0:
        if results['setInterval']['cleared_vars']:
            suspicious.append(f"{results['setInterval']['created_anon']}个匿名setInterval: 无法确认配对")
        else:
            confirmed_leaks.append(f"{results['setInterval']['created_anon']}个匿名setInterval: 无clearInterval")

    # setTimeout 分析（一次性定时器不强制清除）
    for var_name, line_num in results['setTimeout']['created_vars']:
        if var_name in lifecycle_clear_vars['setTimeout']:
            confirmed_safe.append(f"setTimeout({var_name}): 生命周期内清除")

    # addEventListener 分析
    if results['addEventListener']['created'] > 0:
        if lifecycle_has_remove:
            confirmed_safe.append(f"addEventListener: 生命周期内有removeEventListener")
        elif results['addEventListener']['has_remove']:
            suspicious.append(f"{results['addEventListener']['created']}处addEventListener: 有移除但不在生命周期")
        else:
            suspicious.append(f"{results['addEventListener']['created']}处addEventListener: 无对应移除")

    return confirmed_leaks, suspicious, confirmed_safe


# ===== 12.1 包体积检查 =====


# ===== 12.5 内存泄漏风险 =====
def check_12_5_memory_leak(context) -> List[Dict]:
    """12.5 内存泄漏风险 - 检查内存泄漏风险（useEffect清理/生命周期配对）"""
    results = []

    if not context.project_path or not os.path.isdir(context.project_path):
        return results

    # Web前端: useEffect清理检查
    if context.is_web_frontend():
        front_files = context.find_files([".tsx", ".jsx", ".ts", ".js"])
        all_content = ""
        for f in front_files:
            all_content += context.safe_read(f) + "\n"

        useEffect_count = len(re.findall(r'useEffect\s*\(', all_content))
        cleanup_count = len(re.findall(r'useEffect\s*\([^)]*\)\s*\{[^}]*return', all_content, re.DOTALL))

        if useEffect_count > 0 and cleanup_count == 0:
            results.append({
                'id': '12.5',
                'name': '内存泄漏风险',
                'level': 'warning',
                'message': f"检测到 {useEffect_count} 个useEffect但无cleanup函数",
                'file': '',
                'line': 0,
                'fix': '在useEffect中返回cleanup函数清理定时器/监听器',
            })
        return results

    # 小程序: 生命周期配对分析
    js_files = context.find_files([".js"])
    leak_risks = []
    suspicious_items = []

    for f in js_files:
        if '/components/ec-canvas/' in f:
            continue
        file_content = context.safe_read(f)
        rel_path = os.path.relpath(f, context.project_path)
        basename = os.path.basename(f)

        is_app_or_module = basename == 'app.js' or '/utils/' in f or '/libs/' in f or '/lib/' in f

        if is_app_or_module:
            has_setinterval = bool(re.search(r'setInterval', file_content))
            has_clear_interval = 'clearInterval' in file_content
            if has_setinterval and not has_clear_interval:
                suspicious_items.append(f"{rel_path}: setInterval未清除（模块级，需确认）")
            continue

        confirmed_leaks, suspicious, confirmed_safe = _analyze_lifecycle_pairing_miniprogram(f, file_content)

        for leak in confirmed_leaks:
            leak_risks.append(f"{rel_path}: {leak}")
        for item in suspicious:
            suspicious_items.append(f"{rel_path}: {item}")

    if leak_risks:
        results.append({
            'id': '12.5',
            'name': '内存泄漏风险',
            'level': 'warning',
            'message': f"发现 {len(leak_risks)} 处确认内存泄漏风险",
            'detail': "\n".join(leak_risks[:10]),
            'file': '',
            'line': 0,
            'fix': '页面卸载时清除定时器、解绑事件、释放全局缓存',
        })

    return results


# ===== 12.6 构建配置/分包配置 =====



# ===== 12.8 WXML节点数量 =====
def check_12_8_wxml_node_count(context) -> List[Dict]:
    """12.8 WXML节点数量 - 小程序WXML页面节点数量检查"""
    results = []

    if not context.project_path or not os.path.isdir(context.project_path):
        return results

    # 仅小程序项目
    if context.project_type not in ("miniprogram", "mixed"):
        return results

    wxml_files = context.find_files([".wxml"])
    heavy_pages = []
    node_warn = _get_threshold(context, "wxml_node_warning", 1000)
    node_err = _get_threshold(context, "wxml_node_error", 3000)

    for f in wxml_files:
        content = context.safe_read(f)
        tag_count = len(re.findall(r'<[a-zA-Z][\w-]*', content))
        if tag_count > node_err:
            heavy_pages.append((os.path.relpath(f, context.project_path), tag_count, "error"))
        elif tag_count > node_warn:
            heavy_pages.append((os.path.relpath(f, context.project_path), tag_count, "warning"))

    err_pages = [x for x in heavy_pages if x[2] == "error"]
    warn_pages = [x for x in heavy_pages if x[2] == "warning"]

    if err_pages:
        detail = "\n".join(f"{x[0]} {x[1]}节点" for x in heavy_pages[:10])
        results.append({
            'id': '12.8',
            'name': 'WXML节点数量',
            'level': 'error',
            'message': f"发现 {len(err_pages)} 个页面节点>{node_err}",
            'detail': detail,
            'file': '',
            'line': 0,
            'fix': '精简WXML结构，减少嵌套层级，使用虚拟列表',
        })
    elif warn_pages:
        detail = "\n".join(f"{x[0]} {x[1]}节点" for x in warn_pages[:5])
        results.append({
            'id': '12.8',
            'name': 'WXML节点数量',
            'level': 'warning',
            'message': f"发现 {len(warn_pages)} 个页面节点>{node_warn}",
            'detail': detail,
            'file': '',
            'line': 0,
            'fix': '优化页面结构减少DOM节点',
        })

    return results


# ===== 12.9 并发请求过多 =====



# ===== 12.9 并发请求过多 =====
def check_12_9_concurrent_requests(context) -> List[Dict]:
    """12.9 并发请求过多 - 小程序onLoad中并发请求检查"""
    results = []

    if not context.project_path or not os.path.isdir(context.project_path):
        return results

    # 仅小程序项目
    if context.project_type not in ("miniprogram", "mixed"):
        return results

    js_files = context.find_files([".js"])
    concurrent_pages = []
    warn_threshold = _get_threshold(context, "concurrent_requests_warning", 5)

    for f in js_files:
        content = context.safe_read(f)
        if 'onLoad' in content:
            onload_match = re.search(r'onLoad\s*[\(:][^}]*', content, re.DOTALL)
            if onload_match:
                onload_body = onload_match.group(0)
                api_count = len(re.findall(r'\.api\(|api\(', onload_body))
                if api_count > warn_threshold:
                    concurrent_pages.append(f"{os.path.relpath(f, context.project_path)}: onLoad中{api_count}个并发请求")

    if concurrent_pages:
        results.append({
            'id': '12.9',
            'name': '并发请求过多',
            'level': 'warning',
            'message': f"发现 {len(concurrent_pages)} 个页面onLoad中并发请求过多",
            'detail': "\n".join(concurrent_pages[:5]),
            'file': '',
            'line': 0,
            'fix': '合并请求或使用串行/队列方式控制并发',
        })

    return results


# ===== 12.10 Storage使用量 =====



# ===== 12.10 Storage使用量 =====
def check_12_10_storage_usage(context) -> List[Dict]:
    """12.10 Storage使用量 - 小程序Storage大数据存储检查（含截断逻辑验证）"""
    results = []

    if not context.project_path or not os.path.isdir(context.project_path):
        return results

    # 仅小程序项目
    if context.project_type not in ("miniprogram", "mixed"):
        return results

    js_files = context.find_files([".js"])
    storage_issues = []

    for f in js_files:
        content = context.safe_read(f)
        if not content:
            continue

        # 放宽匹配：所有setStorageSync/setStorage调用
        storage_calls = list(re.finditer(
            r'setStorageSync?\s*\(\s*["\']([^"\']+)["\']\s*,\s*([^)]+)',
            content, re.DOTALL
        ))

        for m in storage_calls:
            key = m.group(1)
            value_str = m.group(2).strip()[:200]  # 截取前200字符分析
            line_no = content[:m.start()].count('\n') + 1

            # 判断是否存储了大数据（JSON.stringify、变量名暗示集合/列表）
            is_large_data = bool(re.search(
                r'JSON\.stringify|\.data\b|\.result\b|\.list\b|\.records\b|'
                r'\.items\b|\.rows\b|\.response\b|\.res\.\w+\b',
                value_str
            ))

            if not is_large_data:
                continue

            rel_path = os.path.relpath(f, context.project_path)

            # 检查同文件中是否有截断/限制逻辑
            has_truncation = bool(re.search(
                r'\.slice\s*\(|\.splice\s*\(|'
                r'(?:limit|MAX|max_length|maxLength|max_length|truncat|cap\b).{0,30}[:=]|'
                r'(?:length\s*[<>=!]+\s*\d+.*?(?:slice|splice|substring))',
                content, re.IGNORECASE
            ))

            if not has_truncation:
                storage_issues.append(
                    f"{rel_path}:{line_no} key='{key}' 存储大数据但无截断保护"
                )

    if storage_issues:
        results.append({
            'id': '12.10',
            'name': 'Storage使用量',
            'level': 'warning',
            'message': f"发现 {len(storage_issues)} 处Storage存储大数据但无截断保护",
            'detail': "\n".join(storage_issues[:8]),
            'file': '',
            'line': 0,
            'fix': '存储前对数据进行截断处理，避免超出Storage 10MB限制导致写入失败',
            'suggestion_code': '// 存储前截断示例:\nconst MAX_ITEMS = 100;\nconst truncatedData = data.slice(0, MAX_ITEMS);\ntry {\n  wx.setStorageSync("key", JSON.stringify(truncatedData));\n} catch (e) {\n  console.warn("Storage写入失败:", e);\n}',
        })

    return results


# ===== 12.11 内存告警处理 =====



# ===== 12.11 内存告警处理 =====
def check_12_11_memory_warning(context) -> List[Dict]:
    """12.11 内存告警处理 - 小程序内存告警回调检查"""
    results = []

    if not context.project_path or not os.path.isdir(context.project_path):
        return results

    # 仅小程序项目
    if context.project_type not in ("miniprogram", "mixed"):
        return results

    js_files = context.find_files([".js"])
    has_mem_warning = False
    for f in js_files:
        content = context.safe_read(f)
        if 'onMemoryWarning' in content:
            has_mem_warning = True
            break

    if not has_mem_warning:
        results.append({
            'id': '12.11',
            'name': '内存告警处理',
            'level': 'info',
            'message': '未注册wx.onMemoryWarning（建议添加）',
            'file': '',
            'line': 0,
            'fix': '在app.js中注册wx.onMemoryWarning清理缓存',
        })

    return results


# ===== 12.12 base64大图传输 =====


# ===== 规则定义列表 =====
RULES = [
    {
        'id': '12.5',
        'name': '内存泄漏风险',
        'level': 'problem',
        'category': 'performance',
        'module_id': '12',
        'applicable_types': [],
        'description': 'Web端检查useEffect清理，小程序端检查生命周期配对',
        'check': check_12_5_memory_leak,
    },
    {
        'id': '12.8',
        'name': 'WXML节点数量',
        'level': 'problem',
        'category': 'performance',
        'module_id': '12',
        'applicable_types': ['miniprogram', 'mixed'],
        'description': '检查WXML页面节点数量，过多节点影响渲染性能',
        'check': check_12_8_wxml_node_count,
    },
    {
        'id': '12.9',
        'name': '并发请求过多',
        'level': 'problem',
        'category': 'performance',
        'module_id': '12',
        'applicable_types': ['miniprogram', 'mixed'],
        'description': '检查onLoad中并发请求数量，避免阻塞页面渲染',
        'check': check_12_9_concurrent_requests,
    },
    {
        'id': '12.10',
        'name': 'Storage使用量',
        'level': 'suggestion',
        'category': 'performance',
        'module_id': '12',
        'applicable_types': ['miniprogram', 'mixed'],
        'description': '检查是否有大量数据存储到本地Storage',
        'check': check_12_10_storage_usage,
    },
    {
        'id': '12.11',
        'name': '内存告警处理',
        'level': 'suggestion',
        'category': 'performance',
        'module_id': '12',
        'applicable_types': ['miniprogram', 'mixed'],
        'description': '检查是否注册了内存告警回调wx.onMemoryWarning',
        'check': check_12_11_memory_warning,
    },
]
