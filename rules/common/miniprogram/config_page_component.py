"""
小程序配置规则集 - 页面与组件配置 (M19)
微信小程序专属配置检查 - 页面/组件/目录相关
包含: 未使用页面、window配置、全局组件、性能SEO、权限格式、目录结构、自定义组件、嵌套重复目录
"""

"""
小程序配置规则集 (M19)
微信小程序专属配置检查
包含: app.json配置、页面注册、tabBar配置、分包配置、权限声明等11项检查
"""

import re
import os
import json
from typing import List, Dict, Any



def _load_app_json(context):
    """加载app.json配置"""
    if not context.project_path:
        return None, ''
    
    app_json_path = os.path.join(context.project_path, 'app.json')
    if not os.path.isfile(app_json_path):
        return None, ''
    
    content = context.safe_read(app_json_path)
    try:
        config = json.loads(content)
        return config, app_json_path
    except json.JSONDecodeError:
        return None, app_json_path


def check_19_6_unused_pages(context) -> List[Dict]:
    """19.6 未使用页面检测 - 检测配置中注册但未被引用的页面"""
    results = []
    
    config, app_json_path = _load_app_json(context)
    if not config or 'pages' not in config:
        return results
    
    pages = set(config['pages'])
    
    # 查找所有wxml文件
    wxml_files = context.find_files([".wxml"])
    all_page_dirs = set()
    for fpath in wxml_files:
        rel_path = os.path.relpath(fpath, context.project_path)
        # 去掉.wxml后缀
        page_name = rel_path[:-5]
        all_page_dirs.add(page_name)
    
    # 找未注册的页面（有文件但未在pages中）
    unregistered = all_page_dirs - pages
    
    if unregistered:
        # 排除组件目录和分包页面
        true_unregistered = []
        subpackage_roots = set()
        subpackages = config.get('subpackages') or config.get('subPackages', [])
        for pkg in subpackages:
            if 'root' in pkg:
                subpackage_roots.add(pkg['root'])
        
        for page in unregistered:
            # 检查是否是组件
            if '/components/' in page or page.startswith('components/'):
                continue
            # 检查是否在分包中
            in_subpackage = any(page.startswith(root + '/') for root in subpackage_roots)
            if in_subpackage:
                continue
            true_unregistered.append(page)
        
        if true_unregistered:
            results.append({
                'id': '19.6',
                'name': '未注册页面检测',
                'level': 'info',
                'message': f'发现{len(true_unregistered)}个未在app.json中注册的页面文件',
                'detail': '示例: ' + ', '.join(true_unregistered[:5]),
                'file': '',
                'line': 0,
                'fix': '确认这些页面是否需要注册到app.json中',
            })
    
    return results


def check_19_7_window_config(context) -> List[Dict]:
    """19.7 window配置合法性 - 检查window窗口配置字段是否合法"""
    results = []
    
    config, app_json_path = _load_app_json(context)
    if not config:
        return results
    
    window = config.get("window", {})
    if not isinstance(window, dict):
        results.append({
            'id': '19.7',
            'name': 'window配置合法性',
            'level': 'warning',
            'message': 'window字段类型错误，应为对象',
            'file': app_json_path,
            'line': 0,
            'fix': 'window必须是对象类型',
        })
        return results
    
    issues = []
    
    # 合法值校验
    nav_text = window.get("navigationBarTextStyle")
    if nav_text and nav_text not in ("black", "white"):
        issues.append(f'navigationBarTextStyle非法值: {nav_text}（仅支持black/white）')
    
    bg_text = window.get("backgroundTextStyle")
    if bg_text and bg_text not in ("dark", "light"):
        issues.append(f'backgroundTextStyle非法值: {bg_text}（仅支持dark/light）')
    
    nav_style = window.get("navigationStyle")
    if nav_style and nav_style not in ("default", "custom"):
        issues.append(f'navigationStyle非法值: {nav_style}（仅支持default/custom）')
    
    # 颜色值格式
    color_fields = ["navigationBarBackgroundColor", "backgroundColor",
                    "backgroundColorTop", "backgroundColorBottom"]
    for cf in color_fields:
        val = window.get(cf)
        if val and isinstance(val, str) and not re.match(r'^#[0-9A-Fa-f]{6}$', val):
            issues.append(f'{cf}颜色格式错误: {val}（需#RRGGBB十六进制格式）')
    
    # darkmode检查
    if window.get("darkmode") is True and not config.get("themeLocation"):
        issues.append('启用了darkmode但未配置themeLocation')
    
    if issues:
        level = 'error' if any('darkmode' in i for i in issues) else 'warning'
        results.append({
            'id': '19.7',
            'name': 'window配置合法性',
            'level': level,
            'message': f'发现{len(issues)}个window配置问题',
            'detail': '问题: ' + '; '.join(issues),
            'file': app_json_path,
            'line': 0,
            'fix': '按照微信小程序官方规范修正window配置字段',
        })
    
    return results


def check_19_8_global_components(context) -> List[Dict]:
    """19.8 全局组件配置检查 - 检查app.json中usingComponents全局组件配置"""
    results = []
    
    config, app_json_path = _load_app_json(context)
    if not config:
        return results
    
    uc = config.get("usingComponents", {})
    if not uc:
        return results
    
    if not isinstance(uc, dict):
        results.append({
            'id': '19.8',
            'name': '全局组件配置检查',
            'level': 'error',
            'message': 'usingComponents类型错误，应为对象',
            'file': app_json_path,
            'line': 0,
            'fix': 'usingComponents必须是对象类型',
        })
        return results
    
    issues = []
    for comp_name, comp_path in uc.items():
        if not isinstance(comp_path, str):
            issues.append(f'组件{comp_name}路径类型错误')
            continue
        # 跳过插件组件
        if comp_path.startswith("plugin://"):
            continue
        
        # 解析路径
        resolved = None
        if comp_path.startswith("/"):
            resolved = os.path.normpath(os.path.join(context.project_path, comp_path.lstrip("/")))
        elif comp_path.startswith("./") or comp_path.startswith("../"):
            resolved = os.path.normpath(os.path.join(context.project_path, comp_path))
        elif "/" in comp_path:
            # npm包路径
            npm_path = os.path.normpath(os.path.join(context.project_path, "miniprogram_npm", comp_path))
            node_path = os.path.normpath(os.path.join(context.project_path, "node_modules", comp_path))
            if os.path.isdir(npm_path) or os.path.isfile(npm_path + ".js"):
                resolved = npm_path
            elif os.path.isdir(node_path):
                resolved = node_path
            else:
                resolved = npm_path
        
        if resolved:
            # 检查组件文件存在
            exists = False
            if os.path.isdir(resolved):
                base = os.path.basename(resolved)
                if (os.path.isfile(os.path.join(resolved, "index.js")) or
                    os.path.isfile(os.path.join(resolved, "index.json")) or
                    os.path.isfile(os.path.join(resolved, base + ".js"))):
                    exists = True
            elif os.path.isfile(resolved + ".js"):
                exists = True
            elif os.path.isfile(resolved):
                exists = True
            
            if not exists:
                issues.append(f'组件文件不存在: {comp_name} -> {comp_path}')
            
            # 检查组件json是否含component:true
            comp_json = None
            if os.path.isdir(resolved) and os.path.isfile(os.path.join(resolved, "index.json")):
                comp_json = os.path.join(resolved, "index.json")
            elif resolved.endswith(".js"):
                json_path = resolved.replace(".js", ".json")
                if os.path.isfile(json_path):
                    comp_json = json_path
            
            if comp_json:
                try:
                    with open(comp_json, "r", encoding="utf-8") as f:
                        cj = json.load(f)
                    if cj.get("component") is not True:
                        issues.append(f'组件缺少component:true声明: {comp_name}')
                except (json.JSONDecodeError, UnicodeDecodeError):  # noqa: intentional empty handler
                    pass
    
    if issues:
        results.append({
            'id': '19.8',
            'name': '全局组件配置检查',
            'level': 'error',
            'message': f'发现{len(issues)}个组件问题',
            'detail': '问题: ' + '; '.join(issues[:10]),
            'file': app_json_path,
            'line': 0,
            'fix': '检查组件路径是否正确、文件是否完整、json是否声明component:true',
        })
    
    return results


def check_19_9_perf_seo_config(context) -> List[Dict]:
    """19.9 性能与SEO配置 - 检查sitemap、lazyCodeLoading、style等配置"""
    results = []
    
    config, app_json_path = _load_app_json(context)
    if not config:
        return results
    
    issues = []
    
    # sitemapLocation
    sitemap_loc = config.get("sitemapLocation", "sitemap.json")
    sitemap_path = os.path.join(context.project_path, sitemap_loc)
    if not os.path.isfile(sitemap_path):
        issues.append(f'sitemap文件不存在: {sitemap_loc}')
    
    # lazyCodeLoading
    lcl = config.get("lazyCodeLoading")
    if lcl and lcl != "requiredComponents":
        issues.append(f'lazyCodeLoading建议使用requiredComponents，当前: {lcl}')
    
    # style v2
    style = config.get("style")
    if style and style != "v2":
        issues.append(f'style建议配置为v2，当前: {style}')
    
    if issues:
        level = 'error' if any('sitemap' in i for i in issues) else 'warning'
        results.append({
            'id': '19.9',
            'name': '性能与SEO配置',
            'level': level,
            'message': f'发现{len(issues)}个配置问题',
            'detail': '问题: ' + '; '.join(issues),
            'file': app_json_path,
            'line': 0,
            'fix': '确保sitemap文件存在、性能配置合理',
        })
    
    return results


def check_19_10_permission_format(context) -> List[Dict]:
    """19.10 权限格式合法性 - 检查permission、requiredPrivateInfos等配置格式"""
    results = []
    
    config, app_json_path = _load_app_json(context)
    if not config:
        return results
    
    issues = []
    
    permission = config.get("permission", {})
    if permission and isinstance(permission, dict):
        for scope, val in permission.items():
            if not isinstance(val, dict):
                issues.append(f'权限{scope}配置格式错误，应为对象')
                continue
            desc = val.get("desc", "")
            if not desc:
                issues.append(f'权限{scope}缺少desc描述')
    
    # requiredPrivateInfos
    rpi = config.get("requiredPrivateInfos")
    if rpi and not isinstance(rpi, list):
        issues.append('requiredPrivateInfos类型错误，应为数组')
    
    # requiredBackgroundModes合法值
    rbm = config.get("requiredBackgroundModes", [])
    valid_modes = {"audio", "location"}
    if isinstance(rbm, list):
        for m in rbm:
            if m not in valid_modes:
                issues.append(f'requiredBackgroundModes非法值: {m}')
    
    if issues:
        results.append({
            'id': '19.10',
            'name': '权限格式合法性',
            'level': 'warning',
            'message': f'发现{len(issues)}个权限配置问题',
            'detail': '问题: ' + '; '.join(issues),
            'file': app_json_path,
            'line': 0,
            'fix': '按照小程序权限规范修正配置',
        })
    
    return results


def check_19_11_directory_structure(context) -> List[Dict]:
    """19.11 目录结构完整性 - 检查核心文件、页面文件完整性"""
    results = []
    
    config, app_json_path = _load_app_json(context)
    if not config or not context.project_path:
        return results
    
    issues = []
    
    # 三大核心文件
    core_files = ["app.js", "app.json", "app.wxss"]
    for cf in core_files:
        if not os.path.isfile(os.path.join(context.project_path, cf)):
            issues.append(f'核心文件缺失: {cf}')
    
    # project.config.json
    if not os.path.isfile(os.path.join(context.project_path, "project.config.json")):
        issues.append('缺失: project.config.json')
    
    # 所有页面文件完整性（pages + 分包 pages）
    all_pages = list(config.get("pages", []))
    sub_pkgs = config.get("subPackages") or config.get("subpackages") or []
    if isinstance(sub_pkgs, list):
        for pkg in sub_pkgs:
            root = pkg.get("root", "").rstrip("/")
            for sp in pkg.get("pages", []):
                all_pages.append(f"{root}/{sp}")
    
    missing_wxss = []
    missing_json = []
    for p in all_pages:
        full = os.path.join(context.project_path, p)
        if not os.path.isfile(full + ".wxss"):
            missing_wxss.append(p)
        if not os.path.isfile(full + ".json"):
            missing_json.append(p)
    
    if missing_json:
        issues.append(f'{len(missing_json)}个页面缺少.json配置文件')
    
    if issues:
        level = 'error' if any('核心文件' in i or 'project.config' in i for i in issues) else 'warning'
        results.append({
            'id': '19.11',
            'name': '目录结构完整性',
            'level': level,
            'message': f'发现{len(issues)}个目录结构问题',
            'detail': '问题: ' + '; '.join(issues),
            'file': '',
            'line': 0,
            'fix': '确保核心文件和页面文件完整',
        })
    
    return results


def check_19_14_custom_components(context) -> List[Dict]:
    """19.14 自定义组件规范 - 检查components目录下组件的规范"""
    results = []
    
    if not context.project_path:
        return results
    
    comp_dir = os.path.join(context.project_path, "components")
    if not os.path.isdir(comp_dir):
        return results
    
    issues = []
    comp_count = 0
    
    for root, dirs, files in os.walk(comp_dir):
        # 找组件目录（含.js和.json的目录）
        if any(f.endswith(".js") for f in files) and any(f.endswith(".json") for f in files):
            comp_count += 1
            json_file = None
            for f in files:
                if f.endswith(".json"):
                    json_file = os.path.join(root, f)
                    break
            if json_file:
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        cj = json.load(f)
                    if cj.get("component") is not True:
                        rel = os.path.relpath(root, context.project_path)
                        issues.append(f'组件缺少component:true: {rel}')
                except (json.JSONDecodeError, UnicodeDecodeError):  # noqa: intentional empty handler
                    pass
            
            # 目录名不以wx-开头
            dir_name = os.path.basename(root)
            if dir_name.startswith("wx-"):
                rel = os.path.relpath(root, context.project_path)
                issues.append(f'组件目录名不能以wx-开头: {rel}')
    
    if issues:
        results.append({
            'id': '19.14',
            'name': '自定义组件规范',
            'level': 'warning',
            'message': f'发现{len(issues)}个组件规范问题',
            'detail': '问题: ' + '; '.join(issues[:10]),
            'file': '',
            'line': 0,
            'fix': '确保自定义组件声明component:true，命名符合规范',
        })
    
    return results


def check_19_17_nested_duplicate_dirs(context) -> List[Dict]:
    """19.17 嵌套重复目录 - 检查项目根目录下是否存在同名子目录（不同层级）"""
    results = []

    if not context.project_path:
        return results

    if context.project_type not in ("miniprogram", "mixed"):
        return results

    # 收集所有目录名→路径映射
    dir_names = {}  # {dir_name: [path1, path2, ...]}
    exclude_dirs = {"node_modules", ".git", "miniprogram_npm", "minitest",
                    "dist", "build", "__pycache__", ".idea", ".vscode"}

    for root, dirs, files in os.walk(context.project_path):
        # 排除特定目录
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        rel_root = os.path.relpath(root, context.project_path)
        if rel_root == '.':
            continue
        for d in dirs:
            if d in exclude_dirs:
                continue
            dir_names.setdefault(d, []).append(
                os.path.join(rel_root, d).replace(os.sep, '/')
            )

    # 找出出现多次的目录名
    duplicate_dirs = {}
    for name, paths in dir_names.items():
        if len(paths) > 1:
            # 进一步判断是否有嵌套关系或同级冲突
            # 按路径深度排序
            paths_sorted = sorted(paths, key=lambda p: p.count('/'))
            if len(paths_sorted) >= 2:
                duplicate_dirs[name] = paths_sorted

    if duplicate_dirs:
        issues = []
        for name, paths in sorted(duplicate_dirs.items()):
            issues.append(f'{name}: {", ".join(paths[:4])}')

        # 区分问题等级：如果同名目录在不同层级可能导致引用混乱
        problem_items = []
        for name, paths in duplicate_dirs.items():
            # 检查是否有父子路径关系
            for i, p1 in enumerate(paths):
                for p2 in paths[i+1:]:
                    if p2.startswith(p1 + '/') or p1.startswith(p2 + '/'):
                        problem_items.append(f'{name}: {p1} 与 {p2} 存在嵌套关系')
                    else:
                        # 检查是否有同名文件可能造成冲突
                        pass

        if problem_items:
            results.append({
                'id': '19.17',
                'name': '嵌套重复目录',
                'level': 'warning',
                'message': f'发现{len(problem_items)}组同名目录存在嵌套关系，可能导致引用混乱',
                'detail': '问题: ' + '; '.join(problem_items[:8]),
                'file': '',
                'line': 0,
                'fix': '统一目录命名，避免不同层级出现同名目录导致引用歧义',
            })
        elif duplicate_dirs:
            results.append({
                'id': '19.17',
                'name': '嵌套重复目录',
                'level': 'info',
                'message': f'发现{len(duplicate_dirs)}个目录名在多个位置出现，建议检查是否有意为之',
                'detail': '详情: ' + '; '.join(issues[:8]),
                'file': '',
                'line': 0,
                'fix': '确认同名目录是否为有意设计，否则建议统一命名规范',
            })

    return results


# ===== 规则定义列表 =====
RULES = [
        {
            'id': '19.6',
            'name': '未注册页面检测',
            'level': 'suggestion',
            'category': 'miniprogram_config',
            'module_id': '19',
            'applicable_types': ['miniprogram', 'mixed'],
            'description': '检测有文件但未在app.json中注册的页面',
            'check': check_19_6_unused_pages,
        },
        {
            'id': '19.7',
            'name': 'window配置合法性',
            'level': 'problem',
            'category': 'miniprogram_config',
            'module_id': '19',
            'applicable_types': ['miniprogram', 'mixed'],
            'description': '检查window窗口配置字段是否合法（颜色格式、枚举值、darkmode等）',
            'check': check_19_7_window_config,
        },
        {
            'id': '19.8',
            'name': '全局组件配置检查',
            'level': 'blocking',
            'category': 'miniprogram_config',
            'module_id': '19',
            'applicable_types': ['miniprogram', 'mixed'],
            'description': '检查app.json中usingComponents全局组件路径是否存在、是否声明component:true',
            'check': check_19_8_global_components,
        },
        {
            'id': '19.9',
            'name': '性能与SEO配置',
            'level': 'problem',
            'category': 'miniprogram_config',
            'module_id': '19',
            'applicable_types': ['miniprogram', 'mixed'],
            'description': '检查sitemap文件存在性、lazyCodeLoading、style等性能与SEO配置',
            'check': check_19_9_perf_seo_config,
        },
        {
            'id': '19.10',
            'name': '权限格式合法性',
            'level': 'problem',
            'category': 'miniprogram_config',
            'module_id': '19',
            'applicable_types': ['miniprogram', 'mixed'],
            'description': '检查permission、requiredPrivateInfos、requiredBackgroundModes等配置格式',
            'check': check_19_10_permission_format,
        },
        {
            'id': '19.11',
            'name': '目录结构完整性',
            'level': 'blocking',
            'category': 'miniprogram_config',
            'module_id': '19',
            'applicable_types': ['miniprogram', 'mixed'],
            'description': '检查核心文件(app.js/app.json/app.wxss)、页面配置文件完整性',
            'check': check_19_11_directory_structure,
        },
        {
            'id': '19.14',
            'name': '自定义组件规范',
            'level': 'problem',
            'category': 'miniprogram_config',
            'module_id': '19',
            'applicable_types': ['miniprogram', 'mixed'],
            'description': '检查components目录下自定义组件是否声明component:true、命名是否符合规范',
            'check': check_19_14_custom_components,
        },
        {
            'id': '19.17',
            'name': '嵌套重复目录',
            'level': 'warning',
            'category': 'miniprogram_config',
            'module_id': '19',
            'applicable_types': ['miniprogram', 'mixed'],
            'description': '检查项目目录下是否存在同名子目录（不同层级），避免引用歧义',
            'check': check_19_17_nested_duplicate_dirs,
        },
]
