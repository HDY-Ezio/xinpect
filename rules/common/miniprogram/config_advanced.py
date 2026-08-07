"""
小程序配置规则集 - 高级配置与合规 (M19)
微信小程序专属配置检查 - 性能/项目/包体积/权限反向检查/隐私合规
包含: project.config.json配置、包体积估算、权限反向检查、隐私合规配置
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



def _load_project_config_json(context):
    """加载project.config.json配置"""
    if not context.project_path:
        return None, ''
    
    proj_path = os.path.join(context.project_path, 'project.config.json')
    if not os.path.isfile(proj_path):
        return None, proj_path
    
    content = context.safe_read(proj_path)
    try:
        config = json.loads(content)
        return config, proj_path
    except json.JSONDecodeError:
        return None, proj_path


def check_19_12_project_config(context) -> List[Dict]:
    """19.12 项目配置检查 - 检查project.config.json的配置合法性"""
    results = []
    
    proj_cfg, proj_path = _load_project_config_json(context)
    
    if not proj_path or not os.path.isfile(proj_path):
        results.append({
            'id': '19.12',
            'name': '项目配置检查',
            'level': 'error',
            'message': 'project.config.json不存在',
            'file': '',
            'line': 0,
            'fix': '项目根目录必须包含project.config.json',
        })
        return results
    
    if proj_cfg is None:
        results.append({
            'id': '19.12',
            'name': '项目配置检查',
            'level': 'warning',
            'message': 'project.config.json JSON解析失败',
            'file': proj_path,
            'line': 0,
            'fix': '修复JSON语法错误',
        })
        return results
    
    issues = []
    
    # appid格式校验
    appid = proj_cfg.get("appid", "")
    if appid:
        if not re.match(r'^wx[a-fA-F0-9]{16}$', appid):
            issues.append(f'appid格式错误: {appid}（应为wx + 16位十六进制）')
        if appid in ("touristappid", "testappid", "", "tourist"):
            issues.append(f'appid为测试号: {appid}，不能用于正式发布')
    else:
        issues.append('appid未配置')
    
    # compileType
    ct = proj_cfg.get("compileType")
    if ct and ct not in ("miniprogram", "plugin"):
        issues.append(f'compileType非法值: {ct}')
    
    # npm构建配置
    setting = proj_cfg.get("setting", {})
    if isinstance(setting, dict):
        if setting.get("packNpmManually") is True:
            rel_list = setting.get("packNpmRelationList", [])
            if not rel_list or not isinstance(rel_list, list):
                issues.append('启用了packNpmManually但未配置packNpmRelationList')
            else:
                for idx, rel in enumerate(rel_list):
                    pkg_path = rel.get("packageJsonPath", "")
                    if pkg_path:
                        full_pkg = os.path.join(context.project_path, pkg_path)
                        if not os.path.isfile(full_pkg):
                            issues.append(f'packNpmRelationList[{idx}] packageJsonPath文件不存在: {pkg_path}')
                    else:
                        issues.append(f'packNpmRelationList[{idx}] 缺少packageJsonPath')
        
        # urlCheck上线前应为true
        if setting.get("urlCheck") is False:
            issues.append('urlCheck为false（开发时可关闭，上线前应开启域名校验）')
    
    # miniprogram_npm存在性（如果有npm依赖）
    pkg_json = os.path.join(context.project_path, "package.json")
    npm_dir = os.path.join(context.project_path, "miniprogram_npm")
    if os.path.isfile(pkg_json) and not os.path.isdir(npm_dir):
        try:
            with open(pkg_json, "r", encoding="utf-8") as f:
                pkg = json.load(f)
            deps = pkg.get("dependencies", {})
            if deps:
                issues.append(f'有{len(deps)}个npm依赖但miniprogram_npm目录不存在，需执行npm构建')
        except (json.JSONDecodeError, UnicodeDecodeError):  # noqa: intentional empty handler
            pass
    
    if issues:
        level = 'error' if any('appid' in i and ('格式' in i or '无效' in i or '不存在' in i) for i in issues) else 'warning'
        results.append({
            'id': '19.12',
            'name': '项目配置检查',
            'level': level,
            'message': f'发现{len(issues)}个项目配置问题',
            'detail': '问题: ' + '; '.join(issues),
            'file': proj_path,
            'line': 0,
            'fix': '修正project.config.json中的配置问题',
        })
    
    return results


def check_19_13_bundle_size(context) -> List[Dict]:
    """19.13 包体积估算 - 估算主包/分包/总包体积是否超限"""
    results = []
    
    config, app_json_path = _load_app_json(context)
    if not config or not context.project_path:
        return results
    
    main_pages = config.get("pages", [])
    exclude_dirs = context.config.get("exclude_dirs", [])
    
    def calc_dir_size(dir_path):
        total = 0
        if not os.path.isdir(dir_path):
            return 0
        for root, dirs, files in os.walk(dir_path):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for f in files:
                fp = os.path.join(root, f)
                try:
                    total += os.path.getsize(fp)
                except OSError:  # noqa: intentional empty handler
                    pass
        return total
    
    main_size = 0
    # 根目录核心文件
    for cf in ["app.js", "app.json", "app.wxss", "sitemap.json", "project.config.json"]:
        fp = os.path.join(context.project_path, cf)
        if os.path.isfile(fp):
            main_size += os.path.getsize(fp)
    
    # components目录
    comp_dir = os.path.join(context.project_path, "components")
    main_size += calc_dir_size(comp_dir)
    
    # utils目录
    utils_dir = os.path.join(context.project_path, "utils")
    main_size += calc_dir_size(utils_dir)
    
    # images目录
    img_dir = os.path.join(context.project_path, "images")
    main_size += calc_dir_size(img_dir)
    
    # miniprogram_npm
    npm_dir = os.path.join(context.project_path, "miniprogram_npm")
    main_size += calc_dir_size(npm_dir)
    
    # 主包pages
    for p in main_pages:
        page_dir = os.path.dirname(os.path.join(context.project_path, p))
        if os.path.isdir(page_dir):
            main_size += calc_dir_size(page_dir)
    
    main_size_mb = main_size / (1024 * 1024)
    
    # 分包体积
    sub_pkgs = config.get("subPackages") or config.get("subpackages") or []
    sub_sizes = {}
    total_size = main_size
    if isinstance(sub_pkgs, list):
        for pkg in sub_pkgs:
            root = pkg.get("root", "").rstrip("/")
            if root:
                s = calc_dir_size(os.path.join(context.project_path, root))
                sub_sizes[root] = s / (1024 * 1024)
                total_size += s
    
    total_size_mb = total_size / (1024 * 1024)
    
    issues = []
    if main_size_mb > 2.0:
        issues.append(f'主包体积超限: {main_size_mb:.2f}MB（上限2MB）')
    for root, sz in sub_sizes.items():
        if sz > 2.0:
            issues.append(f'分包{root}体积超限: {sz:.2f}MB（上限2MB）')
    if total_size_mb > 20.0:
        issues.append(f'总包体积超限: {total_size_mb:.2f}MB（普通账号上限20MB）')
    
    if issues:
        results.append({
            'id': '19.13',
            'name': '包体积估算',
            'level': 'error',
            'message': f'发现{len(issues)}个体积超限问题',
            'detail': f'主包: {main_size_mb:.2f}MB | 总包: {total_size_mb:.2f}MB | ' + '; '.join(issues),
            'file': '',
            'line': 0,
            'fix': '优化包体积：图片上CDN、代码分包、移除未使用依赖',
        })
    
    return results


def check_19_15_reverse_permission_check(context) -> List[Dict]:
    """19.15 权限声明反向检查 - 检测app.json中声明了permission但代码中未使用对应API"""
    results = []

    config, app_json_path = _load_app_json(context)
    if not config:
        return results

    app_permissions = config.get('permission', {})
    if not app_permissions or not isinstance(app_permissions, dict):
        return results

    # scope → 对应的wx.* API列表
    scope_to_apis = {
        'scope.userLocation': ['getLocation', 'chooseLocation', 'startLocationUpdate',
                                'onLocationChange', 'openLocation'],
        'scope.userFuzzyLocation': ['getLocation', 'chooseLocation'],
        'scope.userInfo': ['getUserInfo', 'getUserProfile'],
        'scope.record': ['getRecorderManager', 'startRecord'],
        'scope.writePhotosAlbum': ['saveImageToPhotosAlbum', 'saveVideoToPhotosAlbum'],
        'scope.album': ['chooseImage'],
        'scope.address': ['chooseAddress'],
        'scope.invoiceTitle': ['chooseInvoiceTitle'],
        'scope.werun': ['getWeRunData'],
        'scope.bluetooth': ['openBluetoothAdapter', 'createBLEConnection',
                            'startBluetoothDevicesDiscovery'],
        'scope.addPhoneContact': ['addPhoneContact'],
        'scope.addPhoneCalendar': ['addPhoneCalendar'],
        'scope.camera': ['createCameraContext'],
        'scope.clipboardWrite': ['setClipboardData'],
    }

    # 扫描所有JS文件中的API调用
    js_files = context.find_files([".js"])
    api_pattern = re.compile(r'wx\.(\w+)')
    used_apis = set()

    for fpath in js_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        for m in api_pattern.finditer(content):
            used_apis.add(m.group(1))

    # 反向检查：声明了scope但没用对应API
    unused_scopes = []
    for scope_key in app_permissions:
        expected_apis = scope_to_apis.get(scope_key, [])
        if not expected_apis:
            continue  # 未知的scope跳过
        has_usage = any(api in used_apis for api in expected_apis)
        if not has_usage:
            unused_scopes.append(scope_key)

    if unused_scopes:
        results.append({
            'id': '19.15',
            'name': '权限声明反向检查',
            'level': 'warning',
            'message': f'发现{len(unused_scopes)}个权限已声明但代码中未使用对应API',
            'detail': '未使用的权限: ' + ', '.join(unused_scopes[:10]),
            'file': app_json_path,
            'line': 0,
            'fix': '移除app.json中未使用的permission声明，减少审核风险和用户权限请求',
        })

    return results


def check_19_16_privacy_compliance(context) -> List[Dict]:
    """19.16 隐私合规配置 - 检查隐私API声明和__usePrivacyCheck__配置"""
    results = []

    config, app_json_path = _load_app_json(context)
    if not config:
        return results

    issues = []

    # 1. 检查project.config.json中的__usePrivacyCheck__
    proj_cfg, proj_path = _load_project_config_json(context)
    if proj_cfg:
        settings = proj_cfg.get('setting', {})
        use_privacy_check = settings.get('__usePrivacyCheck__')
        if use_privacy_check is not True:
            issues.append({
                'type': 'config',
                'msg': '__usePrivacyCheck__未开启（建议在project.config.json的setting中设为true）',
                'file': proj_path,
            })
    elif proj_path and os.path.isfile(proj_path):
        # 文件存在但解析失败
        pass

    # 2. 隐私API → requiredPrivateInfos 映射
    privacy_apis = {
        'chooseAddress': 'chooseAddress',
        'getLocation': 'getLocation',
        'chooseLocation': 'chooseLocation',
        'onLocationChange': 'onLocationChange',
        'startLocationUpdate': 'startLocationUpdate',
        'choosePoi': 'choosePoi',
        'openLocation': 'openLocation',
        'startLocationUpdateBackground': 'startLocationUpdateBackground',
        'chooseContact': 'chooseContact',
        'addPhoneContact': 'addPhoneContact',
    }

    # 扫描代码中使用的隐私API
    js_files = context.find_files([".js"])
    used_privacy_apis = set()

    for fpath in js_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        for api_name in privacy_apis:
            if re.search(r'wx\.' + api_name + r'\s*\(', content):
                used_privacy_apis.add(api_name)

    # 检查requiredPrivateInfos声明
    declared_private_infos = set()
    rpi = config.get('requiredPrivateInfos', [])
    if isinstance(rpi, list):
        for item in rpi:
            declared_private_infos.add(item)

    # 找出使用了但未声明的隐私API
    missing_declarations = []
    for api_name in sorted(used_privacy_apis):
        required_name = privacy_apis[api_name]
        if required_name not in declared_private_infos:
            missing_declarations.append(f'wx.{api_name}(需声明{required_name})')

    if missing_declarations:
        issues.append({
            'type': 'missing_privacy',
            'msg': f'使用了{len(missing_declarations)}个隐私API但未在requiredPrivateInfos中声明',
            'detail': '缺失: ' + ', '.join(missing_declarations[:10]),
            'file': app_json_path,
        })

    # 3. 额外检查：声明了但未使用的隐私API
    unused_privacy = []
    for declared in declared_private_infos:
        has_usage = False
        for api_name, required_name in privacy_apis.items():
            if required_name == declared and api_name in used_privacy_apis:
                has_usage = True
                break
        if not has_usage:
            unused_privacy.append(declared)

    if unused_privacy:
        issues.append({
            'type': 'unused_privacy',
            'msg': f'requiredPrivateInfos中有{len(unused_privacy)}个声明但代码中未使用',
            'detail': '未使用: ' + ', '.join(unused_privacy[:10]),
            'file': app_json_path,
        })

    if issues:
        # 按严重程度判定level
        has_config_issue = any(i['type'] == 'config' for i in issues)
        has_missing_privacy = any(i['type'] == 'missing_privacy' for i in issues)

        if has_missing_privacy:
            level = 'error'
            msg = '隐私合规配置不完整，涉及隐私API未在requiredPrivateInfos中声明'
        elif has_config_issue:
            level = 'warning'
            msg = '隐私合规配置不完整'
        else:
            level = 'info'
            msg = f'隐私合规有{len(issues)}个待优化项'

        detail_parts = []
        for issue in issues[:5]:
            if issue['type'] == 'config':
                detail_parts.append(issue['msg'])
            elif issue.get('detail'):
                detail_parts.append(issue['detail'])
            else:
                detail_parts.append(issue['msg'])

        results.append({
            'id': '19.16',
            'name': '隐私合规配置',
            'level': level,
            'message': msg,
            'detail': '; '.join(detail_parts),
            'file': app_json_path,
            'line': 0,
            'fix': '1.在project.config.json的setting中开启__usePrivacyCheck__:true; '
                   '2.在app.json的requiredPrivateInfos中声明所有使用的隐私API',
        })

    return results


# ===== 规则定义列表 =====
RULES = [
        {
            'id': '19.12',
            'name': '项目配置检查',
            'level': 'problem',
            'category': 'miniprogram_config',
            'module_id': '19',
            'applicable_types': ['miniprogram', 'mixed'],
            'description': '检查project.config.json的appid格式、compileType、npm构建、urlCheck等配置',
            'check': check_19_12_project_config,
        },
        {
            'id': '19.13',
            'name': '包体积估算',
            'level': 'blocking',
            'category': 'miniprogram_config',
            'module_id': '19',
            'applicable_types': ['miniprogram', 'mixed'],
            'description': '估算主包/分包/总包体积是否超过微信小程序限制',
            'check': check_19_13_bundle_size,
        },
        {
            'id': '19.15',
            'name': '权限声明反向检查',
            'level': 'warning',
            'category': 'miniprogram_config',
            'module_id': '19',
            'applicable_types': ['miniprogram', 'mixed'],
            'description': '检测app.json中声明了permission但代码中未使用对应API的冗余权限',
            'check': check_19_15_reverse_permission_check,
        },
        {
            'id': '19.16',
            'name': '隐私合规配置',
            'level': 'problem',
            'category': 'miniprogram_config',
            'module_id': '19',
            'applicable_types': ['miniprogram', 'mixed'],
            'description': '检查__usePrivacyCheck__配置、隐私API是否在requiredPrivateInfos中声明',
            'check': check_19_16_privacy_compliance,
        },
]
