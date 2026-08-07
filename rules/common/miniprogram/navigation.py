"""
小程序页面导航规则集 (M2)
微信小程序页面导航完整性检查
包含: 页面注册、入口可达性、导航深度、死链检测、返回链完整性等5项检查
"""

import re
import os
import json
from typing import List, Dict, Any, Set


def _load_app_json(context):
    """加载app.json配置"""
    if not context.project_path:
        return {}, ''
    
    app_json_path = os.path.join(context.project_path, 'app.json')
    if not os.path.isfile(app_json_path):
        return {}, app_json_path
    
    content = context.safe_read(app_json_path)
    try:
        config = json.loads(content)
        return config, app_json_path
    except json.JSONDecodeError:
        return {}, app_json_path


def _build_page_navigation_graph(context):
    """
    构建页面跳转有向图
    - 收集所有页面（app.json pages + subPackages）
    - 扫描WXML中的navigator组件
    - 扫描JS中的wx.navigateTo/switchTab/redirectTo/reLaunch
    - 扫描所有文件中的页面路径字符串（保守估计）
    - 组件中的跳转视为从所有页面可达
    返回: (all_pages, adjacency_list, tabbar_pages, string_seen_pages)
    """
    app_cfg, _ = _load_app_json(context)
    
    # 1. 收集所有页面
    all_pages = set()
    for p in app_cfg.get("pages", []):
        all_pages.add(p)
    for subpkg in app_cfg.get("subpackages", []) + app_cfg.get("subPackages", []):
        root = subpkg.get("root", "")
        for p in subpkg.get("pages", []):
            full_path = os.path.join(root, p).replace(os.sep, '/')
            all_pages.add(full_path)
    
    # 2. TabBar页面
    tabbar_pages = set()
    tabbar = app_cfg.get("tabBar", {})
    if tabbar:
        for item in tabbar.get("list", []):
            page_path = item.get("pagePath", "")
            if page_path:
                tabbar_pages.add(page_path)
    
    # 3. 构建邻接表
    adjacency = {p: set() for p in all_pages}
    
    # 4. 字符串中出现过的页面（保守估计，用于二次验证）
    string_seen_pages = set()
    
    all_files = context.find_files([".wxml", ".js"])
    
    for fpath in all_files:
        file_content = context.safe_read(fpath)
        norm_path = fpath.replace(os.sep, '/')
        
        # 确定当前文件所属页面
        current_page = None
        is_component = '/components/' in norm_path
        
        for page in all_pages:
            if norm_path.endswith(page + '.wxml') or norm_path.endswith(page + '.js'):
                current_page = page
                break
        
        targets = set()
        
        # WXML: navigator组件url
        if fpath.endswith('.wxml'):
            for m in re.finditer(r'<navigator[^>]*url\s*=\s*["\'](/?[^"\'?]+)["\']', file_content):
                target = m.group(1).lstrip('/')
                if target in all_pages:
                    targets.add(target)
        
        # JS: 各种导航API调用
        if fpath.endswith('.js'):
            nav_fns = ["navigateTo", "redirectTo", "switchTab", "reLaunch"]
            for fn in nav_fns:
                pattern = fn + r'\s*\(\s*\{[^}]*url\s*:\s*["\']([^"\'?]+)["\']'
                for m in re.finditer(pattern, file_content):
                    target = m.group(1).lstrip('/')
                    if target in all_pages:
                        targets.add(target)
            
            # 搜索所有页面路径字符串（保守估计：只要出现过就算被引用）
            for page in all_pages:
                page_pattern = '["\']/?' + re.escape(page) + r'(?:\?[^"\'\s]*)?["\']'
                if re.search(page_pattern, file_content):
                    string_seen_pages.add(page)
                    # 页面JS中出现的其他页面路径，视为该页面可跳转
                    if current_page and current_page != page:
                        targets.add(page)
        
        # 将目标添加到当前页面的邻接表
        if current_page and current_page in adjacency:
            for target in targets:
                if target in all_pages and target != current_page:
                    adjacency[current_page].add(target)
        elif is_component and targets:
            # 组件中的跳转：保守视为从一个虚拟入口可达
            for target in targets:
                if target in all_pages:
                    string_seen_pages.add(target)
    
    return all_pages, adjacency, tabbar_pages, string_seen_pages


def _bfs_reachable_pages(all_pages, adjacency, tabbar_pages, string_seen_pages=None):
    """
    从TabBar页面+首页出发BFS，标记所有可达页面
    增强：组件/字符串中出现的页面也保守视为可达
    返回: reachable_pages集合
    """
    if not all_pages:
        return set()
    
    # 确定起始页面
    start_pages = set()
    if tabbar_pages:
        start_pages = tabbar_pages.copy()
    else:
        pages_list = sorted(all_pages)
        if pages_list:
            # 首页 = pages[0]
            start_pages.add(pages_list[0])
    
    # 确保起始页面有效
    start_pages = {p for p in start_pages if p in all_pages}
    if not start_pages:
        start_pages = {sorted(all_pages)[0]}
    
    # BFS
    visited = set()
    queue = list(start_pages)
    
    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        
        neighbors = adjacency.get(current, set())
        for neighbor in neighbors:
            if neighbor not in visited and neighbor in all_pages:
                queue.append(neighbor)
    
    # 增强：字符串中出现过的页面也保守视为可达
    if string_seen_pages:
        visited.update(string_seen_pages)
    
    return visited


# ===== 2.1 app.json页面注册 =====
def check_2_1_page_registration(context) -> List[Dict]:
    """2.1 app.json页面注册 - 检查页面目录是否都在app.json中注册"""
    results = []
    
    app_cfg, app_json_path = _load_app_json(context)
    if not context.project_path:
        return results
    
    registered_pages = set(app_cfg.get("pages", []))
    subpkg_pages = set()
    for subpkg in app_cfg.get("subpackages", []):
        root = subpkg.get("root", "")
        for p in subpkg.get("pages", []):
            full_path = os.path.join(root, p)
            subpkg_pages.add(full_path)
    
    pages_dir = os.path.join(context.project_path, "pages")
    actual_pages = set()
    if os.path.isdir(pages_dir):
        for d in os.listdir(pages_dir):
            page_dir = os.path.join(pages_dir, d)
            if os.path.isdir(page_dir):
                for f in os.listdir(page_dir):
                    if f.endswith(".wxml"):
                        page_name = os.path.splitext(f)[0]
                        if page_name == d:
                            actual_pages.add(f"pages/{d}/{d}")
    
    unregistered = actual_pages - registered_pages - subpkg_pages
    if unregistered:
        results.append({
            'id': '2.1',
            'name': 'app.json页面注册',
            'level': 'error',
            'message': f'发现{len(unregistered)}个页面目录未在app.json注册',
            'detail': '未注册页面: ' + ', '.join(sorted(unregistered)),
            'file': app_json_path,
            'line': 0,
            'fix': '在app.json的pages或subpackages中补充注册',
        })
    
    return results


# ===== 2.2 页面入口可达性 =====
def check_2_2_page_reachability(context) -> List[Dict]:
    """2.2 页面入口可达性 - 通过BFS跳转图检查所有页面是否有导航入口可达"""
    results = []
    
    all_pages, adjacency, tabbar_pages, string_seen_pages = _build_page_navigation_graph(context)
    
    if not all_pages:
        return results
    
    # BFS计算可达页面
    reachable = _bfs_reachable_pages(all_pages, adjacency, tabbar_pages, string_seen_pages)
    
    # 不可达页面
    unreachable = all_pages - reachable
    
    # 白名单：登录页、隐私页等合法独立入口
    legit_standalone = {"pages/login/login", "pages/main/main",
                        "pages/privacy/privacy", "pages/terms/terms",
                        "pages/webview/webview", "pages/index/index"}
    
    # 过滤掉白名单中的页面
    unreachable_filtered = set()
    for p in unreachable:
        page_name = p.split("/")[-1]
        if page_name in ("privacy", "terms", "webview", "login"):
            continue
        if p in legit_standalone:
            continue
        unreachable_filtered.add(p)
    
    if unreachable_filtered:
        # 定位到第一个不可达页面的文件
        first_page = sorted(unreachable_filtered)[0]
        page_file = first_page + ".wxml"
        full_path = os.path.join(context.project_path, page_file) if context.project_path else page_file
        loc_file = page_file if os.path.isfile(full_path) else ''
        
        results.append({
            'id': '2.2',
            'name': '页面入口可达性',
            'level': 'warning',
            'message': f'发现{len(unreachable_filtered)}个页面无导航入口可能不可达',
            'detail': '不可达页面: ' + ', '.join(sorted(unreachable_filtered)),
            'file': loc_file,
            'line': 0,
            'fix': '确认是否为独立入口页面，否则添加导航链接',
        })
    
    return results


# ===== 2.3 导航深度 =====
def check_2_3_navigation_depth(context) -> List[Dict]:
    """2.3 导航深度≤3 - 人工验证核心功能3步可达"""
    results = []
    
    # 该检查项为人工验证项，自动检查仅提示
    results.append({
        'id': '2.3',
        'name': '导航深度≤3',
        'level': 'info',
        'message': '需人工验证核心功能3步可达',
        'file': '',
        'line': 0,
        'fix': '请人工确认核心业务流程是否在3次点击内可达',
    })
    
    return results


# ===== 2.4 死链检测 =====
def check_2_4_dead_links(context) -> List[Dict]:
    """2.4 死链检测 - 检查导航目标页面是否真实存在（含模板字符串路径）"""
    results = []

    app_cfg, _ = _load_app_json(context)
    if not context.project_path:
        return results

    registered_pages = set(app_cfg.get("pages", []))
    subpkg_pages = set()
    for subpkg in app_cfg.get("subpackages", []):
        root = subpkg.get("root", "")
        for p in subpkg.get("pages", []):
            subpkg_pages.add(os.path.join(root, p))

    all_registered = registered_pages | subpkg_pages

    js_files = context.find_files([".js", ".wxml"])
    nav_targets = set()

    for fpath in js_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        # 匹配navigateTo/switchTab/redirectTo/reLaunch中的url
        for m in re.finditer(r"(navigateTo|switchTab|redirectTo|reLaunch)", content):
            idx = content.find("url:", m.start())
            if idx > 0:
                url_m = re.search(r"['\"](.*?)['\"]", content[idx:idx+200])
                if url_m:
                    nav_targets.add(url_m.group(1))

        # 新增：模板字符串（反引号）路径提取
        for m in re.finditer(r"url\s*:\s*`([^`]*)`", content):
            template_url = m.group(1)
            # 提取静态路径部分（去掉${...}表达式）
            static_part = re.sub(r'\$\{[^}]*\}', '', template_url)
            if static_part and '/' in static_part:
                nav_targets.add(static_part)

        # 新增：navigator组件url中的模板路径
        if fpath.endswith('.wxml'):
            for m in re.finditer(r'<navigator[^>]*url\s*=\s*["\']([^"\'?]+)["\']', content):
                nav_targets.add(m.group(1))

    # 死链检测
    dead_links = []
    for nav in nav_targets:
        # 剥离query参数，只保留路径部分
        target = nav.split('?')[0].lstrip('/')
        # 只检查看起来像页面路径的目标（以pages/开头）
        if target and target.startswith('pages/') and not any(target in rp for rp in all_registered):
            dead_links.append(nav)

    if dead_links:
        results.append({
            'id': '2.4',
            'name': '死链检测',
            'level': 'error',
            'message': f'发现{len(dead_links)}个导航目标页面不存在',
            'detail': '死链: ' + ', '.join(dead_links[:10]),
            'file': '',
            'line': 0,
            'fix': '修正或移除无效导航链接',
        })

    return results


# ===== 2.5 返回链完整 =====
def check_2_5_back_navigation(context) -> List[Dict]:
    """2.5 返回链完整 - 人工验证非工作台页面的返回导航"""
    results = []
    
    # 该检查项为人工验证项，自动检查仅提示
    results.append({
        'id': '2.5',
        'name': '返回链完整',
        'level': 'info',
        'message': '需人工验证非工作台页面的返回导航',
        'file': '',
        'line': 0,
        'fix': '请人工确认所有非首页/工作台页面都有返回导航',
    })
    
    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': '2.1',
        'name': 'app.json页面注册',
        'level': 'blocking',
        'category': 'navigation',
        'module_id': '2',
        'applicable_types': ['miniprogram', 'mixed'],
        'description': '检查pages目录下的页面是否都在app.json中注册',
        'check': check_2_1_page_registration,
    },
    {
        'id': '2.2',
        'name': '页面入口可达性',
        'level': 'problem',
        'category': 'navigation',
        'module_id': '2',
        'applicable_types': ['miniprogram', 'mixed'],
        'description': '通过BFS跳转图检查所有页面是否有导航入口可达',
        'check': check_2_2_page_reachability,
    },
    {
        'id': '2.3',
        'name': '导航深度≤3',
        'level': 'suggestion',
        'category': 'navigation',
        'module_id': '2',
        'applicable_types': ['miniprogram', 'mixed'],
        'description': '人工验证核心功能是否在3步导航内可达',
        'check': check_2_3_navigation_depth,
    },
    {
        'id': '2.4',
        'name': '死链检测',
        'level': 'blocking',
        'category': 'navigation',
        'module_id': '2',
        'applicable_types': ['miniprogram', 'mixed'],
        'description': '检查导航API调用的目标页面是否真实存在于app.json注册列表中',
        'check': check_2_4_dead_links,
    },
    {
        'id': '2.5',
        'name': '返回链完整',
        'level': 'suggestion',
        'category': 'navigation',
        'module_id': '2',
        'applicable_types': ['miniprogram', 'mixed'],
        'description': '人工验证非首页/工作台页面是否有返回导航',
        'check': check_2_5_back_navigation,
    },
]
