"""
小程序生命周期规则集 (R2-13 / 12.17)
微信小程序页面生命周期完整性检查
包含: async页面缺onUnload、wx.onXxx事件监听无清理等检查
"""

import re
import os
from typing import List, Dict, Any, Set


# ===== 12.17 async页面缺onUnload =====
def check_12_17_async_page_missing_onunload(context) -> List[Dict]:
    """12.17 async页面缺onUnload - 检测有异步操作但缺少onUnload清理的页面"""
    results = []

    if not context.project_path:
        return results

    if context.project_type not in ("miniprogram", "mixed"):
        return results

    js_files = context.find_files([".js"])
    if not js_files:
        return results

    missing_pages = []

    for fpath in js_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        # 跳过非页面文件（utils/libs/components）
        norm_path = fpath.replace(os.sep, '/')
        if '/utils/' in norm_path or '/libs/' in norm_path or '/lib/' in norm_path:
            continue
        basename = os.path.basename(fpath)
        if basename == 'app.js':
            continue

        # 检查是否为页面JS（包含Page(调用）
        if 'Page(' not in content and 'Component(' not in content:
            continue

        # 检查是否有异步操作
        has_async = bool(re.search(
            r'(?:async\s+|await\s+|wx\.request\s*\(|wx\.uploadFile\s*\(|'
            r'wx\.downloadFile\s*\(|wx\.getFileSystemManager|'
            r'wx\.cloud\.callFunction|\.then\s*\()',
            content
        ))
        if not has_async:
            continue

        # 检查是否有onUnload
        has_onunload = bool(re.search(
            r'(?:onUnload\s*[\(:]|onUnload\s*:\s*function)',
            content
        ))
        # 也检查Component的lifetimes中的detach
        has_detach = bool(re.search(
            r'(?:detach\s*[\(:]|detach\s*:\s*function)',
            content
        ))

        if not has_onunload and not has_detach:
            rel_path = os.path.relpath(fpath, context.project_path)
            # 识别具体的异步操作类型
            async_ops = []
            if re.search(r'async\s+|await\s+', content):
                async_ops.append('async/await')
            if re.search(r'wx\.request\s*\(', content):
                async_ops.append('wx.request')
            if re.search(r'wx\.uploadFile\s*\(', content):
                async_ops.append('wx.uploadFile')
            if re.search(r'wx\.downloadFile\s*\(', content):
                async_ops.append('wx.downloadFile')
            if re.search(r'wx\.cloud\.callFunction', content):
                async_ops.append('云函数调用')
            if re.search(r'\.then\s*\(', content):
                async_ops.append('Promise.then')

            missing_pages.append({
                'file': rel_path,
                'ops': ', '.join(async_ops[:3]),
            })

    if missing_pages:
        detail_lines = [f"{p['file']}: 使用了{p['ops']}" for p in missing_pages[:10]]
        results.append({
            'id': '12.17',
            'name': 'async页面缺onUnload',
            'level': 'warning',
            'message': f'发现{len(missing_pages)}个页面有异步操作但缺少onUnload/detach清理',
            'detail': '\n'.join(detail_lines),
            'file': '',
            'line': 0,
            'fix': '在页面中添加onUnload生命周期钩子，清理未完成的异步请求、定时器、事件监听等资源',
            'suggestion_code': '// 在Page中添加:\nonUnload() {\n  // 取消未完成的请求\n  if (this._requestTask) this._requestTask.abort();\n  // 清除定时器\n  if (this._timer) clearInterval(this._timer);\n},',
        })

    return results


# ===== 12.18 wx.onXxx事件监听无清理 =====
def check_12_18_global_event_listener_leak(context) -> List[Dict]:
    """12.18 wx.onXxx事件监听无清理 - 检测全局事件注册后未在onUnload中取消"""
    results = []

    if not context.project_path:
        return results

    if context.project_type not in ("miniprogram", "mixed"):
        return results

    js_files = context.find_files([".js"])
    if not js_files:
        return results

    # 全局事件监听器列表
    GLOBAL_EVENTS = [
        'onAppShow', 'onAppHide', 'onAppError',
        'onNetworkStatusChange', 'onLocationChange',
        'onLocationChangeError', 'onAccelerometerChange',
        'onCompassChange', 'onGyroscopeChange',
        'onBluetoothDeviceFound', 'onBluetoothAdapterStateChange',
        'onBLEConnectionStateChange', 'onBLECharacteristicValueChange',
        'onUserCaptureScreen', 'onMemoryWarning',
        'onThemeChange', 'onAudioInterruptionBegin', 'onAudioInterruptionEnd',
        'onUnhandledRejection', 'onError',
        'onWindowResize',
    ]

    leak_items = []

    for fpath in js_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        norm_path = fpath.replace(os.sep, '/')
        # 跳过非页面文件
        if '/utils/' in norm_path or '/libs/' in norm_path or '/lib/' in norm_path:
            continue
        basename = os.path.basename(fpath)
        if basename == 'app.js':
            continue  # app.js的全局监听生命周期与app一致，不需要onUnload

        if 'Page(' not in content and 'Component(' not in content:
            continue

        # 找出注册的wx.onXxx
        registered_events = []
        for event_name in GLOBAL_EVENTS:
            pattern = r'wx\.' + event_name + r'\s*\('
            if re.search(pattern, content):
                registered_events.append(event_name)

        if not registered_events:
            continue

        # 对应的off方法
        off_events = []
        for event_name in registered_events:
            off_name = event_name.replace('on', 'off', 1)
            off_pattern = r'wx\.' + off_name + r'\s*\('
            if re.search(off_pattern, content):
                off_events.append(off_name)

        # 检查off是否在onUnload/detach中调用
        # 提取onUnload/detach函数体
        unload_body = ''
        for hook_name in ['onUnload', 'detach']:
            # 匹配 onUnload() { ... } 或 onUnload: function() { ... }
            hook_pattern = hook_name + r'\s*[\(:]\s*(?:function\s*)?\([^)]*\)\s*\{'
            m = re.search(hook_pattern, content)
            if m:
                start = m.end()
                brace_depth = 1
                idx = start
                while idx < len(content) and brace_depth > 0:
                    if content[idx] == '{':
                        brace_depth += 1
                    elif content[idx] == '}':
                        brace_depth -= 1
                    idx += 1
                unload_body += content[start:idx]

        # 检查是否在onUnload中调用了off
        off_in_unload = []
        for off_name in off_events:
            if off_name in unload_body:
                off_in_unload.append(off_name)

        # 判定：有on+无对应off，或有off但不在onUnload中
        missing_off = []
        for event_name in registered_events:
            off_name = event_name.replace('on', 'off', 1)
            if off_name not in off_events:
                missing_off.append(f'wx.{event_name} 无对应 wx.{off_name}')
            elif off_name not in off_in_unload:
                missing_off.append(f'wx.{off_name} 未在onUnload中调用')

        if missing_off:
            rel_path = os.path.relpath(fpath, context.project_path)
            leak_items.append({
                'file': rel_path,
                'issues': missing_off,
            })

    if leak_items:
        detail_lines = []
        for item in leak_items[:8]:
            for issue in item['issues'][:3]:
                detail_lines.append(f"{item['file']}: {issue}")

        results.append({
            'id': '12.18',
            'name': '全局事件监听未清理',
            'level': 'warning',
            'message': f'发现{len(leak_items)}个文件有全局事件监听未在onUnload中清理',
            'detail': '\n'.join(detail_lines[:15]),
            'file': '',
            'line': 0,
            'fix': '在onUnload/detach生命周期中调用对应的wx.offXxx取消事件监听',
            'suggestion_code': '// 在onUnload中清理事件监听:\nonUnload() {\n  wx.offNetworkStatusChange(this._onNetworkChange);\n  wx.offLocationChange(this._onLocationChange);\n  wx.offAppShow(this._onAppShow);\n},',
        })

    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': '12.17',
        'name': 'async页面缺onUnload',
        'level': 'warning',
        'category': 'miniprogram_lifecycle',
        'module_id': '12',
        'applicable_types': ['miniprogram', 'mixed'],
        'description': '检测有async/await/wx.request等异步操作但缺少onUnload/detach生命周期清理的页面',
        'check': check_12_17_async_page_missing_onunload,
    },
    {
        'id': '12.18',
        'name': '全局事件监听未清理',
        'level': 'warning',
        'category': 'miniprogram_lifecycle',
        'module_id': '12',
        'applicable_types': ['miniprogram', 'mixed'],
        'description': '检测wx.onXxx全局事件监听是否在onUnload中通过wx.offXxx取消注册',
        'check': check_12_18_global_event_listener_leak,
    },
]
