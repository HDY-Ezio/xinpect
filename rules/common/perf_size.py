"""性能与资源规则集 - 体积/构建/资源子模块
从 performance.py 拆分而来，包含包体积、代码分割、图片/字体优化、构建配置等规则
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


# ===== 12.1 包体积检查 =====
def check_12_1_package_size(context) -> List[Dict]:
    """12.1 包体积检查 - 检查项目包体积/依赖数量"""
    results = []

    if not context.project_path or not os.path.isdir(context.project_path):
        return results

    # Web前端: 检查package.json依赖数量
    if context.is_web_frontend():
        pkg_json_path = os.path.join(context.project_path, "package.json")
        if os.path.isfile(pkg_json_path):
            try:
                pkg = json.loads(context.safe_read(pkg_json_path))
                dep_count = len(pkg.get("dependencies", {}))
                dev_dep_count = len(pkg.get("devDependencies", {}))
                total = dep_count + dev_dep_count
                if total > 100:
                    results.append({
                        'id': '12.1',
                        'name': '包体积检查',
                        'level': 'warning',
                        'message': f"依赖总数 {total}(deps={dep_count}, devDeps={dev_dep_count})过多",
                        'file': '',
                        'line': 0,
                        'fix': '清理未使用的依赖，使用bundle-analyzer分析包体积',
                    })
                else:
                    pass  # 依赖数量合理，不报
            except Exception as e:  # noqa: broad exception handling
                pass
        return results

    # 小程序: 检查主包/总包体积
    subpkg_roots = set()
    app_json_path = os.path.join(context.project_path, "app.json")
    if os.path.isfile(app_json_path):
        try:
            aj = json.loads(context.safe_read(app_json_path))
            for subpkg in aj.get("subpackages", []):
                root = subpkg.get("root", "")
                if root:
                    subpkg_roots.add(root)
        except Exception as e:  # noqa: broad exception handling
            pass

    main_size = 0
    total_size = 0
    exclude_dirs = _get_exclude_dirs(context)

    for fp, fsize in context.get_all_files_with_size(exclude_dirs):
        total_size += fsize
        is_subpkg = any(fp.startswith(os.path.join(context.project_path, r)) for r in subpkg_roots)
        if not is_subpkg:
            main_size += fsize

    main_mb = main_size / (1024 * 1024)
    total_mb = total_size / (1024 * 1024)
    max_main = _get_threshold(context, "main_package_size_mb", 2)
    max_total = _get_threshold(context, "total_package_size_mb", 20)

    if main_mb > max_main:
        results.append({
            'id': '12.1',
            'name': '包体积检查',
            'level': 'error',
            'message': f"主包体积 {main_mb:.2f}MB 超过阈值 {max_main}MB",
            'file': '',
            'line': 0,
            'fix': '拆分非核心页面到分包，压缩主包资源',
        })

    return results


# ===== 12.2 总包体积/代码分割 =====



# ===== 12.2 总包体积/代码分割 =====
def check_12_2_code_splitting(context) -> List[Dict]:
    """12.2 代码分割/懒加载 - 检查是否使用了代码分割或懒加载"""
    results = []

    if not context.project_path or not os.path.isdir(context.project_path):
        return results

    # Web前端: 检查代码分割/懒加载
    if context.is_web_frontend():
        front_files = context.find_files([".tsx", ".jsx", ".ts", ".js"])
        all_content = ""
        for f in front_files:
            all_content += context.safe_read(f) + "\n"

        has_lazy = bool(re.search(r'React\.lazy|dynamic\(|import\(|loadable', all_content, re.IGNORECASE))
        has_next_dynamic = bool(re.search(r'next/dynamic', all_content))

        if front_files and not has_lazy and not has_next_dynamic:
            results.append({
                'id': '12.2',
                'name': '代码分割/懒加载',
                'level': 'warning',
                'message': '未检测到代码分割或懒加载',
                'file': '',
                'line': 0,
                'fix': '使用React.lazy/next/dynamic对大组件进行懒加载',
            })
        return results

    # 小程序: 总包体积
    subpkg_roots = set()
    app_json_path = os.path.join(context.project_path, "app.json")
    if os.path.isfile(app_json_path):
        try:
            aj = json.loads(context.safe_read(app_json_path))
            for subpkg in aj.get("subpackages", []):
                root = subpkg.get("root", "")
                if root:
                    subpkg_roots.add(root)
        except Exception as e:  # noqa: broad exception handling
            pass

    total_size = 0
    exclude_dirs = _get_exclude_dirs(context)

    for fp, fsize in context.get_all_files_with_size(exclude_dirs):
        total_size += fsize

    total_mb = total_size / (1024 * 1024)
    max_total = _get_threshold(context, "total_package_size_mb", 20)

    if total_mb > max_total:
        results.append({
            'id': '12.2',
            'name': '总包体积',
            'level': 'error',
            'message': f"总包体积 {total_mb:.2f}MB 超过阈值 {max_total}MB",
            'file': '',
            'line': 0,
            'fix': '压缩图片/静态资源，清理无用依赖',
        })

    return results


# ===== 12.3 图片优化 =====



# ===== 12.3 图片优化 =====
def check_12_3_image_optimization(context) -> List[Dict]:
    """12.3 图片优化 - 检查图片优化情况（大图片/懒加载）"""
    results = []

    if not context.project_path or not os.path.isdir(context.project_path):
        return results

    # Web前端: 检查图片懒加载/next/image使用
    if context.is_web_frontend():
        front_files = context.find_files([".tsx", ".jsx", ".ts", ".js"])
        all_content = ""
        for f in front_files:
            all_content += context.safe_read(f) + "\n"

        has_next_image = bool(re.search(r'next/image|<Image', all_content))
        has_lazy_img = bool(re.search(r'loading\s*=\s*["\']lazy', all_content))
        has_raw_img = bool(re.search(r'<img\s', all_content))

        if has_raw_img and not has_next_image and not has_lazy_img:
            results.append({
                'id': '12.3',
                'name': '图片优化',
                'level': 'warning',
                'message': '检测到原生<img>标签但无懒加载/优化',
                'file': '',
                'line': 0,
                'fix': '使用next/image或添加loading=lazy属性',
            })
        return results

    # 小程序: 大图片资源检测
    large_images = []
    img_exts = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp')
    warn_kb = _get_threshold(context, "large_image_kb_warning", 100)
    error_kb = _get_threshold(context, "large_image_kb_error", 500)
    exclude_dirs = _get_exclude_dirs(context)

    for fp, fsize in context.get_all_files_with_size(exclude_dirs):
        fn = os.path.basename(fp)
        if fn.lower().endswith(img_exts):
            size_kb = fsize / 1024
            if size_kb > error_kb:
                large_images.append((os.path.relpath(fp, context.project_path), size_kb, "error"))
            elif size_kb > warn_kb:
                large_images.append((os.path.relpath(fp, context.project_path), size_kb, "warning"))

    error_imgs = [x for x in large_images if x[2] == "error"]
    warn_imgs = [x for x in large_images if x[2] == "warning"]

    if error_imgs:
        detail = "\n".join(f"{x[0]} {x[1]:.0f}KB" for x in (error_imgs + warn_imgs)[:10])
        results.append({
            'id': '12.3',
            'name': '大图片资源检测',
            'level': 'error',
            'message': f"发现 {len(error_imgs)} 张图片>{error_kb}KB（阻断），{len(warn_imgs)} 张>{warn_kb}KB（警告）",
            'detail': detail,
            'file': '',
            'line': 0,
            'fix': '压缩图片或使用WebP格式，超大图片考虑CDN加载',
        })
    elif warn_imgs:
        detail = "\n".join(f"{x[0]} {x[1]:.0f}KB" for x in warn_imgs[:5])
        results.append({
            'id': '12.3',
            'name': '大图片资源检测',
            'level': 'warning',
            'message': f"发现 {len(warn_imgs)} 张图片>{warn_kb}KB",
            'detail': detail,
            'file': '',
            'line': 0,
            'fix': '考虑压缩图片或使用WebP格式',
        })

    return results


# ===== 12.4 字体优化/setData数据量 =====



# ===== 12.4 字体优化/setData数据量 =====
def check_12_4_font_optimization(context) -> List[Dict]:
    """12.4 字体优化/setData数据量 - 检查字体优化或setData数据量"""
    results = []

    if not context.project_path or not os.path.isdir(context.project_path):
        return results

    # Web前端: 检查字体优化
    if context.is_web_frontend():
        front_files = context.find_files([".tsx", ".jsx", ".ts", ".js", ".css", ".scss"])
        all_content = ""
        for f in front_files:
            all_content += context.safe_read(f) + "\n"

        has_font_opt = bool(re.search(r'next/font|font-display|@font-face', all_content, re.IGNORECASE))
        # 字体优化为非必须项，不强制报告
        return results

    # 小程序: setData数据量检查
    js_files = context.find_files([".js"])
    big_setdata = []
    setdata_warn_kb = _get_threshold(context, "setdata_kb_warning", 10)
    setdata_warn_chars = setdata_warn_kb * 1024

    for f in js_files:
        content = context.safe_read(f)
        setdata_matches = list(re.finditer(r'setData\s*\(\s*\{([^}]+)\}', content, re.DOTALL))
        if not setdata_matches:
            continue

        # 分组连续的setData调用
        groups = []
        current_group = [(0, setdata_matches[0])]
        for i in range(1, len(setdata_matches)):
            prev_end_line = content[:setdata_matches[i - 1].end()].count('\n')
            curr_start_line = content[:setdata_matches[i].start()].count('\n')
            if curr_start_line - prev_end_line <= 3:
                current_group.append((i, setdata_matches[i]))
            else:
                groups.append(current_group)
                current_group = [(i, setdata_matches[i])]
        groups.append(current_group)

        # 标记需要跳过的（连续小调用）
        skip_indices = set()
        for group in groups:
            if len(group) >= 2:
                all_small = True
                for idx, m in group:
                    block = m.group(1)
                    field_count = len(re.findall(r'\n\s*(?:["\'][\w.]+["\']|[\w$]+)\s*:', block))
                    if field_count >= 5:
                        all_small = False
                        break
                if all_small:
                    for idx, m in group:
                        skip_indices.add(idx)

        for i, m in enumerate(setdata_matches):
            if i in skip_indices:
                continue
            block = m.group(1)
            field_count = len(re.findall(r'\n\s*(?:["\'][\w.]+["\']|[\w$]+)\s*:', block))
            if field_count <= 3:
                continue
            if len(block) < 500:
                continue
            # 路径式更新检查
            path_keys = re.findall(r'["\']([\w]+\.[\w.]+)["\']\s*:', block)
            if path_keys:
                values = re.split(r'["\'][\w.]+["\']\s*:\s*', block)
                has_large_value = False
                for v in values[1:]:
                    v_stripped = v.strip().rstrip(',').strip()
                    if len(v_stripped) > setdata_warn_chars:
                        has_large_value = True
                        break
                if not has_large_value:
                    continue
            line_no = content[:m.start()].count('\n') + 1
            big_setdata.append(f"{os.path.relpath(f, context.project_path)}:{line_no}")

    if big_setdata:
        results.append({
            'id': '12.4',
            'name': 'setData数据量',
            'level': 'warning',
            'message': f"发现 {len(big_setdata)} 处setData可能数据量过大",
            'detail': "\n".join(big_setdata[:5]),
            'file': '',
            'line': 0,
            'fix': '拆分大数据setData为多次小数据调用',
        })

    return results


# ===== 12.5 内存泄漏风险 =====



# ===== 12.6 构建配置/分包配置 =====
def check_12_6_build_config(context) -> List[Dict]:
    """12.6 构建配置检查 - 检查构建配置/分包配置"""
    results = []

    if not context.project_path or not os.path.isdir(context.project_path):
        return results

    # Web前端: next.config检查
    if context.is_web_frontend():
        next_config_path = os.path.join(context.project_path, "next.config.ts")
        if not os.path.isfile(next_config_path):
            next_config_path = os.path.join(context.project_path, "next.config.js")
        if os.path.isfile(next_config_path):
            cfg_content = context.safe_read(next_config_path)
            has_compression = bool(re.search(r'compress', cfg_content, re.IGNORECASE))
            # 构建配置为信息类，不强制报告
        return results

    # 小程序: 分包配置检查
    app_json_path = os.path.join(context.project_path, "app.json")
    has_subpkg = False
    page_count = 0

    if os.path.isfile(app_json_path):
        try:
            aj = json.loads(context.safe_read(app_json_path))
            has_subpkg = bool(aj.get("subpackages"))
            page_count = len(aj.get("pages", []))
            for sp in aj.get("subpackages", []):
                page_count += len(sp.get("pages", []))
        except Exception as e:  # noqa: broad exception handling
            pass

    # 小项目不强制要求分包
    profile = context.project_profile
    main_pkg_size = getattr(profile, 'main_package_size_mb', 0) if profile else 0
    scale_level = getattr(profile, 'scale_level', 'medium') if profile else 'medium'

    is_small_project = page_count > 0 and page_count < 30 and main_pkg_size < 1.8
    is_tiny_scale = scale_level in ('tiny', 'small')

    if not has_subpkg:
        if not is_small_project and not is_tiny_scale:
            results.append({
                'id': '12.6',
                'name': '分包配置检查',
                'level': 'warning',
                'message': 'app.json未配置subpackages',
                'file': '',
                'line': 0,
                'fix': '配置分包加载，减小主包体积',
            })

    return results


# ===== 12.7 按需注入配置 =====



# ===== 12.7 按需注入配置 =====
def check_12_7_lazy_code_loading(context) -> List[Dict]:
    """12.7 按需注入配置 - 小程序lazyCodeLoading配置检查"""
    results = []

    if not context.project_path or not os.path.isdir(context.project_path):
        return results

    # 仅小程序项目
    if context.project_type not in ("miniprogram", "mixed"):
        return results

    app_json_path = os.path.join(context.project_path, "app.json")
    has_lazy = False
    if os.path.isfile(app_json_path):
        try:
            aj = json.loads(context.safe_read(app_json_path))
            has_lazy = bool(aj.get("lazyCodeLoading"))
        except Exception as e:  # noqa: broad exception handling
            pass

    if not has_lazy:
        results.append({
            'id': '12.7',
            'name': '按需注入配置',
            'level': 'warning',
            'message': 'app.json未开启lazyCodeLoading',
            'file': '',
            'line': 0,
            'fix': '添加 "lazyCodeLoading": "requiredComponents"',
        })

    return results


# ===== 12.8 WXML节点数量 =====



# ===== 12.12 base64大图传输 =====
def check_12_12_base64_transfer(context) -> List[Dict]:
    """12.12 base64大图传输 - 小程序setData传输base64图片检查"""
    results = []

    if not context.project_path or not os.path.isdir(context.project_path):
        return results

    # 仅小程序项目
    if context.project_type not in ("miniprogram", "mixed"):
        return results

    js_files = context.find_files([".js"])
    base64_transfer = []

    for f in js_files:
        content = context.safe_read(f)
        lines = content.split('\n')
        # 单行检测
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith('//'):
                continue
            if 'setData' in line and 'base64' in line.lower():
                if re.search(r'this\._\w*[Bb]ase64', line):
                    continue
                base64_transfer.append(f"{os.path.relpath(f, context.project_path)}:{i}")
        # 多行setData检测
        for m in re.finditer(r'setData\s*\(\s*\{([^}]+)\}', content, re.DOTALL):
            block = m.group(1)
            if 'base64' in block.lower():
                if re.search(r'this\._\w*[Bb]ase64', block):
                    continue
                line_no = content[:m.start()].count('\n') + 1
                entry = f"{os.path.relpath(f, context.project_path)}:{line_no}"
                if entry not in base64_transfer:
                    base64_transfer.append(entry)

    if base64_transfer:
        results.append({
            'id': '12.12',
            'name': 'base64大图传输',
            'level': 'warning',
            'message': f"发现 {len(base64_transfer)} 处setData可能传输base64图片",
            'detail': "\n".join(base64_transfer[:5]),
            'file': '',
            'line': 0,
            'fix': '图片使用URL传输，避免setData传base64',
        })

    return results


# ===== 规则定义列表 =====


# ===== 规则定义列表 =====
RULES = [
    {
        'id': '12.1',
        'name': '包体积检查',
        'level': 'problem',
        'category': 'performance',
        'module_id': '12',
        'applicable_types': [],  # 所有类型适用
        'description': '检查项目包体积/依赖数量，Web端检查依赖数量，小程序端检查主包体积',
        'check': check_12_1_package_size,
    },
    {
        'id': '12.2',
        'name': '代码分割/总包体积',
        'level': 'problem',
        'category': 'performance',
        'module_id': '12',
        'applicable_types': [],
        'description': 'Web端检查代码分割/懒加载，小程序端检查总包体积',
        'check': check_12_2_code_splitting,
    },
    {
        'id': '12.3',
        'name': '图片优化',
        'level': 'problem',
        'category': 'performance',
        'module_id': '12',
        'applicable_types': [],
        'description': 'Web端检查图片懒加载，小程序端检查大图片资源',
        'check': check_12_3_image_optimization,
    },
    {
        'id': '12.4',
        'name': '字体优化/setData数据量',
        'level': 'problem',
        'category': 'performance',
        'module_id': '12',
        'applicable_types': [],
        'description': 'Web端检查字体优化，小程序端检查setData数据量',
        'check': check_12_4_font_optimization,
    },
    {
        'id': '12.6',
        'name': '构建配置/分包配置',
        'level': 'suggestion',
        'category': 'performance',
        'module_id': '12',
        'applicable_types': [],
        'description': 'Web端检查构建配置，小程序端检查分包配置',
        'check': check_12_6_build_config,
    },
    {
        'id': '12.7',
        'name': '按需注入配置',
        'level': 'problem',
        'category': 'performance',
        'module_id': '12',
        'applicable_types': ['miniprogram', 'mixed'],
        'description': '检查小程序是否开启lazyCodeLoading按需注入',
        'check': check_12_7_lazy_code_loading,
    },
    {
        'id': '12.12',
        'name': 'base64大图传输',
        'level': 'problem',
        'category': 'performance',
        'module_id': '12',
        'applicable_types': ['miniprogram', 'mixed'],
        'description': '检查setData中是否传输base64大图数据',
        'check': check_12_12_base64_transfer,
    },
]
