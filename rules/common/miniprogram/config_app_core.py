"""
小程序配置规则集 - App核心配置 (M19)
微信小程序专属配置检查 - App基础配置部分
包含: app.json格式合法性、页面文件存在性、tabBar配置、分包配置、权限声明
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


def check_19_1_app_json_valid(context) -> List[Dict]:
    """19.1 app.json格式合法性 - 检查app.json是否为合法JSON且包含必要字段"""
    results = []
    
    config, app_json_path = _load_app_json(context)
    if not app_json_path:
        results.append({
            'id': '19.1',
            'name': 'app.json格式合法性',
            'level': 'error',
            'message': '未找到app.json配置文件',
            'file': '',
            'line': 0,
            'fix': '在项目根目录创建app.json配置文件',
        })
        return results
    
    if config is None:
        results.append({
            'id': '19.1',
            'name': 'app.json格式合法性',
            'level': 'error',
            'message': 'app.json格式错误，无法解析',
            'file': app_json_path,
            'line': 0,
            'fix': '修复app.json的JSON格式错误',
        })
        return results
    
    # 检查必要字段
    required_fields = ['pages', 'window']
    missing = [f for f in required_fields if f not in config]
    
    if missing:
        results.append({
            'id': '19.1',
            'name': 'app.json格式合法性',
            'level': 'error',
            'message': f'app.json缺少必要字段: {", ".join(missing)}',
            'file': app_json_path,
            'line': 0,
            'fix': '在app.json中添加缺失的必要字段',
        })
    
    return results


def check_19_2_page_files_exist(context) -> List[Dict]:
    """19.2 页面文件存在性 - 检查app.json中注册的页面是否有对应文件"""
    results = []
    
    config, app_json_path = _load_app_json(context)
    if not config or 'pages' not in config:
        return results
    
    pages = config['pages']
    missing_pages = []
    
    for page in pages:
        page_path = os.path.join(context.project_path, page)
        # 检查4个文件是否存在
        has_wxml = os.path.isfile(page_path + '.wxml')
        has_js = os.path.isfile(page_path + '.js')
        has_json = os.path.isfile(page_path + '.json')
        has_wxss = os.path.isfile(page_path + '.wxss')
        
        if not has_wxml and not has_js:
            missing_pages.append(f'{page}(缺少wxml/js)')
        elif not has_wxml:
            missing_pages.append(f'{page}(缺少wxml)')
        elif not has_js:
            missing_pages.append(f'{page}(缺少js)')
    
    if missing_pages:
        results.append({
            'id': '19.2',
            'name': '页面文件存在性',
            'level': 'error',
            'message': f'{len(missing_pages)}个页面文件不完整',
            'detail': '缺失页面: ' + ', '.join(missing_pages[:10]),
            'file': app_json_path,
            'line': 0,
            'fix': '创建缺失的页面文件，或从pages配置中移除无效页面',
        })
    
    return results


def check_19_3_tabbar_config(context) -> List[Dict]:
    """19.3 tabBar配置合法性 - 检查tabBar配置是否合法"""
    results = []
    
    config, app_json_path = _load_app_json(context)
    if not config or 'tabBar' not in config:
        return results
    
    tabbar = config['tabBar']
    issues = []
    
    # 检查必要字段
    required_fields = ['color', 'selectedColor', 'list']
    for field in required_fields:
        if field not in tabbar:
            issues.append(f'缺少{field}字段')
    
    # 检查list配置
    if 'list' in tabbar:
        tab_list = tabbar['list']
        if len(tab_list) < 2:
            issues.append('tabBar list至少需要2个tab')
        elif len(tab_list) > 5:
            issues.append('tabBar list最多5个tab')
        
        for i, tab in enumerate(tab_list):
            if 'pagePath' not in tab:
                issues.append(f'第{i+1}个tab缺少pagePath')
            elif 'pages' in config and tab['pagePath'] not in config['pages']:
                issues.append(f'tab页面{tab["pagePath"]}未在pages中注册')
            
            if 'text' not in tab:
                issues.append(f'第{i+1}个tab缺少text')
    
    if issues:
        results.append({
            'id': '19.3',
            'name': 'tabBar配置合法性',
            'level': 'warning',
            'message': f'tabBar配置有{len(issues)}个问题',
            'detail': '问题: ' + '; '.join(issues[:5]),
            'file': app_json_path,
            'line': 0,
            'fix': '修复tabBar配置问题',
        })
    
    return results


def check_19_4_subpackages_config(context) -> List[Dict]:
    """19.4 分包配置合法性 - 检查分包配置是否合法"""
    results = []
    
    config, app_json_path = _load_app_json(context)
    if not config:
        return results
    
    # 检查subpackages字段（支持两种写法）
    subpackages = config.get('subpackages') or config.get('subPackages', [])
    if not subpackages:
        return results
    
    issues = []
    
    for i, pkg in enumerate(subpackages):
        if 'root' not in pkg:
            issues.append(f'第{i+1}个分包缺少root字段')
            continue
        
        root = pkg['root']
        pkg_path = os.path.join(context.project_path, root)
        if not os.path.isdir(pkg_path):
            issues.append(f'分包{root}目录不存在')
        
        if 'pages' in pkg:
            for page in pkg['pages']:
                page_path = os.path.join(pkg_path, page + '.js')
                if not os.path.isfile(page_path):
                    issues.append(f'分包页面{root}/{page}不存在')
                    break  # 每个分包只报第一个
    
    if issues:
        results.append({
            'id': '19.4',
            'name': '分包配置合法性',
            'level': 'warning',
            'message': f'分包配置有{len(issues)}个问题',
            'detail': '问题: ' + '; '.join(issues[:5]),
            'file': app_json_path,
            'line': 0,
            'fix': '修复分包配置问题',
        })
    
    return results


def check_19_5_permission_config(context) -> List[Dict]:
    """19.5 权限配置完整性 - 检查使用的API是否声明了相应权限（含插件API）"""
    results = []

    config, app_json_path = _load_app_json(context)
    if not config:
        return results

    # 查找代码中使用的API
    js_files = context.find_files([".js"])
    api_pattern = re.compile(r'wx\.(\w+)')
    used_apis = set()

    # 插件使用检测: requirePlugin / plugin:// / require('plugin://...')
    plugin_pattern = re.compile(
        r"""(?:requirePlugin\s*\(\s*['"]([^'"]+)['"]|"""
        r"""require\s*\(\s*['"]plugin://([^/'"]+)/|"""
        r"""plugin://([^/'"]+)/)"""
    )
    used_plugins = set()

    for fpath in js_files:
        content = context.safe_read(fpath)
        for m in api_pattern.finditer(content):
            used_apis.add(m.group(1))
        # 收集插件使用
        for m in plugin_pattern.finditer(content):
            plugin_name = m.group(1) or m.group(2) or m.group(3)
            if plugin_name:
                used_plugins.add(plugin_name)

    # 需要权限的API
    permission_apis = {
        'getLocation': 'scope.userLocation',
        'chooseLocation': 'scope.userLocation',
        'startLocationUpdate': 'scope.userLocation',
        'getUserInfo': 'scope.userInfo',
        'getUserProfile': 'scope.userInfo',
        'chooseAddress': 'scope.address',
        'chooseInvoiceTitle': 'scope.invoiceTitle',
        'getWeRunData': 'scope.werun',
        'openBluetoothAdapter': 'scope.bluetooth',
        'createBLEConnection': 'scope.bluetooth',
        'startBluetoothDevicesDiscovery': 'scope.bluetooth',
        'addPhoneContact': 'scope.addPhoneContact',
        'addPhoneCalendar': 'scope.addPhoneCalendar',
        'chooseImage': 'scope.album',
        'saveImageToPhotosAlbum': 'scope.writePhotosAlbum',
        'saveVideoToPhotosAlbum': 'scope.writePhotosAlbum',
        'getRecorderManager': 'scope.record',
        'startRecord': 'scope.record',
        'getSetting': '',  # 不需要声明
    }

    # 插件→权限映射（常见官方/第三方插件）
    plugin_permission_map = {
        'WechatSI': {'scope.record': ['语音识别插件WechatSI'], 'scope.speechSynthesis': []},
        'wechatSI': {'scope.record': ['语音识别插件wechatSI']},
        'plugin-assistant': set(),
    }
    # 也检查app.json中声明的plugins字段
    declared_plugins = set()
    plugins_config = config.get('plugins', {})
    if isinstance(plugins_config, dict):
        for plugin_key in plugins_config:
            declared_plugins.add(plugin_key)

    # 检查是否有permission配置
    app_permissions = set()
    if 'permission' in config:
        for key in config['permission'].keys():
            app_permissions.add(key)

    used_permission_apis = []
    missing_permissions = []

    for api, perm in permission_apis.items():
        if api in used_apis and perm and perm not in app_permissions:
            missing_permissions.append(perm)
            used_permission_apis.append(api)

    # 检查插件所需权限
    plugin_missing = []
    for plugin_name in used_plugins:
        if plugin_name in plugin_permission_map:
            required_perms = plugin_permission_map[plugin_name]
            if isinstance(required_perms, dict):
                for perm, desc in required_perms.items():
                    if perm and perm not in app_permissions:
                        plugin_missing.append(f'{perm}(插件{plugin_name}需要)')

    if missing_permissions or plugin_missing:
        all_missing = sorted(set(missing_permissions)) + plugin_missing
        results.append({
            'id': '19.5',
            'name': '权限配置完整性',
            'level': 'warning',
            'message': f'使用了{len(used_permission_apis)}个需要权限的API/插件，但未在app.json中声明',
            'detail': '缺少权限: ' + ', '.join(all_missing[:10]),
            'file': app_json_path,
            'line': 0,
            'fix': '在app.json的permission字段中声明所需权限；确认插件所需权限已正确配置',
        })

    return results


# ===== 规则定义列表 =====
RULES = [
        {
            'id': '19.1',
            'name': 'app.json格式合法性',
            'level': 'blocking',
            'category': 'miniprogram_config',
            'module_id': '19',
            'applicable_types': ['miniprogram', 'mixed'],
            'description': '检查app.json是否为合法JSON且包含必要字段',
            'check': check_19_1_app_json_valid,
        },
        {
            'id': '19.2',
            'name': '页面文件存在性',
            'level': 'blocking',
            'category': 'miniprogram_config',
            'module_id': '19',
            'applicable_types': ['miniprogram', 'mixed'],
            'description': '检查app.json中注册的页面是否有对应文件',
            'check': check_19_2_page_files_exist,
        },
        {
            'id': '19.3',
            'name': 'tabBar配置合法性',
            'level': 'problem',
            'category': 'miniprogram_config',
            'module_id': '19',
            'applicable_types': ['miniprogram', 'mixed'],
            'description': '检查tabBar配置是否合法',
            'check': check_19_3_tabbar_config,
        },
        {
            'id': '19.4',
            'name': '分包配置合法性',
            'level': 'problem',
            'category': 'miniprogram_config',
            'module_id': '19',
            'applicable_types': ['miniprogram', 'mixed'],
            'description': '检查分包配置是否合法',
            'check': check_19_4_subpackages_config,
        },
        {
            'id': '19.5',
            'name': '权限配置完整性',
            'level': 'problem',
            'category': 'miniprogram_config',
            'module_id': '19',
            'applicable_types': ['miniprogram', 'mixed'],
            'description': '检查使用的API是否声明了相应权限',
            'check': check_19_5_permission_config,
        },
]
