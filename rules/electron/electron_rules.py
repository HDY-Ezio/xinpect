"""
Electron桌面端规则集
Electron桌面应用专项检查
包含: 安全配置、进程模型、IPC通信、打包配置等检查
"""

import re
import os
from typing import List, Dict, Any


def _find_package_json(context):
    """查找package.json"""
    check_paths = []
    if context.project_path:
        check_paths.append(context.project_path)
    if context.backend_path:
        check_paths.append(context.backend_path)
    
    for check_path in check_paths:
        if check_path and os.path.isdir(check_path):
            candidate = os.path.join(check_path, 'package.json')
            if os.path.isfile(candidate):
                return candidate
    return ''


# ===== ELECTRON-001 安全配置检查 =====
def check_electron_001_security(context) -> List[Dict]:
    """ELECTRON-001 安全配置检查 - 检查Electron安全配置"""
    results = []
    
    main_files = []
    js_files = context.find_files([".js", ".ts"])
    
    for fpath in js_files:
        basename = os.path.basename(fpath).lower()
        if basename in ('main.js', 'main.ts', 'electron.js', 'electron.ts', 'index.js'):
            content = context.safe_read(fpath)
            if 'BrowserWindow' in content or 'app.on' in content:
                main_files.append(fpath)
    
    if not main_files:
        return results
    
    issues = []
    
    for fpath in main_files:
        content = context.safe_read(fpath)
        
        # 检查nodeIntegration
        if 'nodeIntegration: true' in content or 'nodeIntegration:true' in content:
            issues.append(f'{os.path.basename(fpath)}: 启用了nodeIntegration（建议禁用）')
        
        # 检查contextIsolation
        if 'contextIsolation: false' in content or 'contextIsolation:false' in content:
            issues.append(f'{os.path.basename(fpath)}: 禁用了contextIsolation（建议启用）')
        
        # 检查sandbox
        if 'sandbox: false' in content:
            issues.append(f'{os.path.basename(fpath)}: 禁用了sandbox（建议启用）')
    
    if issues:
        results.append({
            'id': 'ELECTRON-001',
            'name': '安全配置检查',
            'level': 'warning',
            'message': f'发现{len(issues)}个安全配置问题',
            'detail': '问题: ' + '; '.join(issues),
            'file': main_files[0] if main_files else '',
            'line': 0,
            'fix': '遵循Electron安全最佳实践：禁用nodeIntegration，启用contextIsolation和sandbox',
        })
    
    return results


# ===== ELECTRON-002 IPC通信检查 =====
def check_electron_002_ipc(context) -> List[Dict]:
    """ELECTRON-002 IPC通信检查 - 检查IPC通信安全性"""
    results = []
    
    js_files = context.find_files([".js", ".ts"])
    
    renderer_remote_count = 0
    for fpath in js_files:
        content = context.safe_read(fpath)
        if 'ipcRenderer' in content and 'remote' in content:
            renderer_remote_count += 1
    
    # 检查是否使用了remote模块（已废弃）
    remote_count = 0
    for fpath in js_files:
        content = context.safe_read(fpath)
        if re.search(r'require\s*\(\s*["\']@electron/remote["\']', content) or \
           re.search(r'from\s+["\']electron["\'].*remote', content):
            remote_count += 1
    
    if remote_count > 0:
        results.append({
            'id': 'ELECTRON-002',
            'name': 'IPC通信检查',
            'level': 'warning',
            'message': f'{remote_count}个文件使用了@electron/remote（已不推荐）',
            'file': '',
            'line': 0,
            'fix': '使用ipcRenderer/ipcMain替代remote模块',
        })
    
    return results


# ===== ELECTRON-003 打包配置检查 =====
def check_electron_003_packaging(context) -> List[Dict]:
    """ELECTRON-003 打包配置检查 - 检查打包工具配置"""
    results = []
    
    pkg_path = _find_package_json(context)
    if not pkg_path:
        return results
    
    content = context.safe_read(pkg_path)
    
    # 检查是否有electron-builder或electron-packager配置
    has_builder = 'electron-builder' in content
    has_packager = 'electron-packager' in content
    
    if not has_builder and not has_packager:
        results.append({
            'id': 'ELECTRON-003',
            'name': '打包配置检查',
            'level': 'info',
            'message': '未检测到electron打包工具配置',
            'file': pkg_path,
            'line': 0,
            'fix': '建议配置electron-builder或electron-packager进行打包',
        })
    
    return results


# ===== ELECTRON-004 进程模型检查 =====
def check_electron_004_process_model(context) -> List[Dict]:
    """ELECTRON-004 进程模型检查 - 检查主进程/渲染进程划分"""
    results = []
    
    # 检查是否有明确的主进程和渲染进程分离
    main_dir = os.path.join(context.project_path or '', 'main')
    renderer_dir = os.path.join(context.project_path or '', 'renderer')
    src_main_dir = os.path.join(context.project_path or '', 'src/main')
    src_renderer_dir = os.path.join(context.project_path or '', 'src/renderer')
    
    has_clear_structure = (
        (os.path.isdir(main_dir) and os.path.isdir(renderer_dir)) or
        (os.path.isdir(src_main_dir) and os.path.isdir(src_renderer_dir))
    )
    
    if not has_clear_structure and context.is_electron():
        results.append({
            'id': 'ELECTRON-004',
            'name': '进程模型检查',
            'level': 'info',
            'message': '建议明确分离主进程和渲染进程代码目录',
            'file': '',
            'line': 0,
            'fix': '使用main/和renderer/或src/main/和src/renderer/目录结构',
        })
    
    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'ELECTRON-001',
        'name': '安全配置检查',
        'level': 'blocking',
        'category': 'security',
        'module_id': '3',
        'applicable_types': ['electron', 'mixed_electron'],
        'description': '检查Electron安全配置（nodeIntegration、contextIsolation等）',
        'check': check_electron_001_security,
    },
    {
        'id': 'ELECTRON-002',
        'name': 'IPC通信检查',
        'level': 'problem',
        'category': 'security',
        'module_id': '3',
        'applicable_types': ['electron', 'mixed_electron'],
        'description': '检查IPC通信安全性和remote模块使用',
        'check': check_electron_002_ipc,
    },
    {
        'id': 'ELECTRON-003',
        'name': '打包配置检查',
        'level': 'suggestion',
        'category': 'deploy',
        'module_id': '7',
        'applicable_types': ['electron', 'mixed_electron'],
        'description': '检查打包工具配置是否存在',
        'check': check_electron_003_packaging,
    },
    {
        'id': 'ELECTRON-004',
        'name': '进程模型检查',
        'level': 'suggestion',
        'category': 'architecture',
        'module_id': '9',
        'applicable_types': ['electron', 'mixed_electron'],
        'description': '检查主进程/渲染进程目录结构',
        'check': check_electron_004_process_model,
    },
]
