"""
小程序组件检查规则集 (v1.20.0)
组件属性、API响应结构等交叉检查
包含: 组件属性名一致性、API响应数据结构一致性等2项检查
"""

import re
import os
import json
from typing import List, Dict, Any, Set, Optional, Tuple


# ===== 20.3 组件属性名一致性 =====

# Vant Weapp 常用组件属性内置白名单
# v1.23.0: 扩充常见属性（custom-style, bind:click等），减少误报
_VANT_COMMON_ATTRS = {
    'custom-style', 'custom-class', 'class', 'style',
    'bind:click', 'bind:change', 'bind:close', 'bind:open',
    'bind:input', 'bind:focus', 'bind:blur', 'bind:clear',
    'bind:submit', 'bind:reset', 'bind:scroll', 'bind:load',
    'bind:error', 'bind:tap', 'bind:longpress',
    'bind:touchstart', 'bind:touchmove', 'bind:touchend',
    'bind:touchcancel', 'bind:transition', 'bind:animationfinish',
    'bind:animationstart', 'bind:select', 'bind:toggle',
    'bind:opened', 'bind:closed', 'bind:update:visible',
    'bind:overlayclick', 'bind:keypress',
    'id', 'slot', 'data-',
}

_VANT_WEAPP_PROPS = {
    'van-tag': {'type', 'size', 'color', 'round', 'block', 'plain', 'mark', 'custom-class',
                'custom-style', 'text-color', 'closeable', 'show', 'hairline'},
    'van-field': {'value', 'label', 'type', 'placeholder', 'required', 'disabled', 'readonly',
                  'maxlength', 'border', 'input-align', 'error', 'error-message', 'left-icon',
                  'right-icon', 'is-link', 'clickable', 'custom-class', 'placeholder-style',
                  'placeholder-class', 'title-width', 'colon', 'center', 'clearable',
                  'arrow-direction', 'autosize', 'button', 'suffix', 'show-word-limit',
                  'custom-style', 'bind:input', 'bind:focus', 'bind:blur', 'bind:clear',
                  'bind:click', 'bind:click-input', 'bind:click-left-icon', 'bind:click-right-icon',
                  'formatter', 'format-trigger', 'autofocus', 'cursor-spacing'},
    'van-icon': {'name', 'size', 'color', 'class-prefix', 'dot', 'info', 'custom-class',
                 'custom-style', 'bind:click'},
    'van-button': {'type', 'size', 'round', 'block', 'loading', 'disabled', 'plain',
                   'hairline', 'icon', 'class-prefix', 'native-type', 'custom-class',
                   'color', 'loading-size', 'loading-type', 'loading-text',
                   'custom-style', 'icon-prefix', 'square', 'bind:click', 'bind:touchstart'},
    'van-cell': {'title', 'value', 'label', 'icon', 'border', 'is-link', 'required',
                 'clickable', 'title-width', 'arrow-direction', 'use-label-slot',
                 'center', 'url', 'link-type', 'custom-class',
                 'custom-style', 'right-icon', 'size', 'bind:click'},
    'van-cell-group': {'title', 'border', 'inset', 'custom-class', 'custom-style'},
    'van-popup': {'show', 'position', 'duration', 'round', 'overlay', 'closeable',
                  'overlay-style', 'custom-style', 'close-icon', 'close-on-click-overlay',
                  'z-index', 'lock-scroll', 'safe-area-inset-bottom', 'safe-area-inset-top',
                  'custom-class', 'bind:close', 'bind:click-overlay',
                  'bind:transition', 'bind:opened', 'bind:closed'},
    'van-loading': {'type', 'size', 'color', 'vertical', 'custom-class', 'custom-style'},
    'van-toast': {'show', 'type', 'position', 'message', 'mask', 'forbid-click',
                  'duration', 'z-index', 'loading-type', 'custom-class', 'custom-style'},
    'van-dialog': {'show', 'title', 'message', 'confirm-button-text', 'cancel-button-text',
                   'show-cancel-button', 'close-on-click-overlay', 'z-index',
                   'custom-class', 'custom-style', 'message-align',
                   'bind:confirm', 'bind:cancel', 'bind:close', 'bind:click-overlay'},
    'van-tabs': {'active', 'type', 'color', 'border', 'duration', 'line-width',
                 'line-height', 'animated', 'ellipsis', 'swipeable', 'scrollable',
                 'lazy-render', 'custom-class', 'custom-style',
                 'bind:change', 'bind:click', 'bind:disabled', 'bind:scroll'},
    'van-tab': {'title', 'disabled', 'name', 'title-style', 'dot', 'info', 'custom-class',
                'custom-style', 'title-color'},
    'van-picker': {'show-toolbar', 'title', 'columns', 'loading', 'item-height',
                   'confirm-button-text', 'cancel-button-text', 'visible-item-count',
                   'value-key', 'custom-class', 'custom-style',
                   'bind:confirm', 'bind:cancel', 'bind:change', 'bind:click'},
    'van-image': {'src', 'fit', 'alt', 'width', 'height', 'radius', 'round', 'lazy-load',
                  'use-error-slot', 'use-loading-slot', 'show-error', 'show-loading',
                  'custom-class', 'custom-style', 'show-loading',
                  'bind:load', 'bind:error', 'bind:click'},
    'van-swipe-cell': {'name', 'left-width', 'right-width', 'disabled', 'before-close', 'custom-class',
                       'custom-style', 'bind:open', 'bind:close', 'bind:click'},
    'van-switch': {'checked', 'loading', 'disabled', 'active-color', 'inactive-color',
                   'active-value', 'inactive-value', 'size', 'custom-class', 'custom-style',
                   'bind:change'},
    'van-checkbox': {'name', 'value', 'disabled', 'label-disabled', 'label-position',
                     'shape', 'icon-size', 'checked-color', 'custom-class', 'custom-style',
                     'bind:change'},
    'van-radio': {'name', 'value', 'disabled', 'icon-size', 'checked-color', 'custom-class',
                  'custom-style', 'bind:change'},
    'van-grid': {'column-num', 'icon-size', 'square', 'gutter', 'center', 'border',
                 'direction', 'clickable', 'custom-class', 'custom-style'},
    'van-grid-item': {'text', 'icon', 'icon-prefix', 'dot', 'info', 'url', 'link-type',
                      'use-slot', 'custom-class', 'custom-style', 'bind:click'},
}

# 微信原生组件标准属性内置白名单
_NATIVE_COMPONENT_PROPS = {
    'scroll-view': {'scroll-y', 'scroll-x', 'enable-back-to-top', 'refresher-enabled',
                    'refresher-triggered', 'scroll-into-view', 'scroll-top',
                    'scroll-with-animation', 'enhanced', 'bounces', 'show-scrollbar',
                    'paging-enabled', 'fast-deceleration', 'enable-flex',
                    'scroll-anchoring', 'lower-threshold', 'upper-threshold',
                    'bindscroll', 'bindscrolltoupper', 'bindscrolltolower',
                    'bindrefresherpulling', 'bindrefresherrefresh', 'bindrefresherrestore',
                    'bindrefresherabort', 'type', 'throttle', 'refresher-default-style',
                    'refresher-background', 'class', 'style'},
    'image': {'lazy-load', 'mode', 'show-menu-by-longpress', 'src', 'webp',
              'bindload', 'binderror', 'class', 'style'},
    'view': {'hover-class', 'hover-start-time', 'hover-stay-time', 'hover-stop-propagation',
             'bindtouchstart', 'bindtouchmove', 'bindtouchend', 'bindtouchcancel',
             'bindlongpress', 'bindtap', 'bindtransitionend', 'bindanimationstart',
             'bindanimationiteration', 'bindanimationend', 'class', 'style'},
    'text': {'user-select', 'space', 'decode', 'selectable', 'class', 'style'},
    'button': {'type', 'size', 'plain', 'loading', 'disabled', 'open-type',
               'form-type', 'hover-class', 'hover-stop-propagation', 'hover-start-time',
               'hover-stay-time', 'lang', 'session-from', 'send-message-title',
               'send-message-path', 'send-message-img', 'app-parameter', 'show-message-card',
               'bindgetuserinfo', 'bindcontact', 'bindgetphonenumber', 'binderror',
               'bindopensetting', 'bindlaunchapp', 'bindchooseavatar', 'class', 'style'},
    'swiper': {'autoplay', 'circular', 'vertical', 'indicator-dots', 'duration',
               'interval', 'current', 'indicator-color', 'indicator-active-color',
               'previous-margin', 'next-margin', 'display-multiple-items',
               'snap-to-edge', 'easing-function', 'bindchange', 'bindtransition',
               'bindanimationfinish', 'class', 'style'},
    'swiper-item': {'item-id', 'class', 'style'},
    'input': {'value', 'type', 'password', 'placeholder', 'placeholder-style',
              'placeholder-class', 'disabled', 'maxlength', 'cursor-spacing',
              'auto-focus', 'focus', 'confirm-type', 'confirm-hold', 'cursor',
              'selection-start', 'selection-end', 'adjust-position', 'hold-keyboard',
              'bindinput', 'bindfocus', 'bindblur', 'bindconfirm', 'bindkeyboardheightchange',
              'class', 'style'},
    'textarea': {'value', 'placeholder', 'placeholder-style', 'placeholder-class',
                 'disabled', 'maxlength', 'auto-focus', 'focus', 'auto-height',
                 'fixed', 'cursor-spacing', 'cursor', 'show-confirm-bar',
                 'selection-start', 'selection-end', 'adjust-position',
                 'hold-keyboard', 'disable-default-padding', 'confirm-type',
                 'confirm-hold', 'bindinput', 'bindfocus', 'bindblur', 'bindconfirm',
                 'bindlinechange', 'bindkeyboardheightchange', 'class', 'style'},
    'form': {'report-submit', 'report-submit-timeout', 'bindsubmit', 'bindreset',
             'class', 'style'},
    'label': {'for', 'class', 'style'},
    'picker': {'mode', 'range', 'range-key', 'value', 'start', 'end', 'fields',
               'custom-item', 'bindcancel', 'bindchange', 'bindcolumnchange',
               'class', 'style'},
    'radio': {'value', 'checked', 'disabled', 'color', 'class', 'style'},
    'radio-group': {'bindchange', 'class', 'style'},
    'checkbox': {'value', 'checked', 'disabled', 'color', 'class', 'style'},
    'checkbox-group': {'bindchange', 'class', 'style'},
    'switch': {'checked', 'disabled', 'type', 'color', 'bindchange', 'class', 'style'},
    'slider': {'min', 'max', 'step', 'disabled', 'value', 'color', 'selected-color',
               'activeColor', 'backgroundColor', 'block-size', 'block-color',
               'show-value', 'bindchange', 'bindchanging', 'class', 'style'},
    'navigator': {'url', 'open-type', 'delta', 'app-id', 'path', 'extra-data',
                  'version', 'hover-class', 'hover-stop-propagation', 'hover-start-time',
                  'hover-stay-time', 'target', 'class', 'style'},
    'map': {'latitude', 'longitude', 'scale', 'markers', 'covers', 'polyline',
            'circles', 'controls', 'include-points', 'show-location', 'enable-poi',
            'enable-zoom', 'enable-scroll', 'enable-rotate', 'enable-overlooking',
            'enable-3D', 'show-compass', 'enable-satellite', 'enable-traffic',
            'bindmarkertap', 'bindcallouttap', 'bindcontroltap', 'bindregionchange',
            'bindtap', 'bindupdated', 'bindlabeltap', 'class', 'style'},
    'canvas': {'type', 'canvas-id', 'disable-scroll', 'bindtouchstart', 'bindtouchmove',
               'bindtouchend', 'bindtouchcancel', 'bindlongtap', 'binderror',
               'class', 'style'},
    'open-data': {'type', 'open-gid', 'lang', 'default-text', 'default-avatar',
                  'class', 'style'},
    'web-view': {'src', 'bindload', 'binderror', 'bindmessage', 'class', 'style'},
    'rich-text': {'nodes', 'space', 'class', 'style'},
    'progress': {'percent', 'show-info', 'border-radius', 'font-size', 'stroke-width',
                 'color', 'activeColor', 'backgroundColor', 'active',
                 'active-mode', 'bindactiveend', 'class', 'style'},
    'page-container': {'show', 'position', 'duration', 'z-index', 'close-on-click-overlay',
                       'overlay', 'custom-style', 'overlay-style', 'class', 'style'},
}


def _get_vant_props_from_npm(context, tag_name: str) -> Optional[Set[str]]:
    """尝试从miniprogram_npm目录读取Vant组件的properties定义"""
    if not context.project_path:
        return None
    # Vant Weapp npm路径
    npm_comp_dir = os.path.join(context.project_path, 'miniprogram_npm', '@vant', 'weapp', tag_name)
    js_path = os.path.join(npm_comp_dir, 'index.js')
    if not os.path.isfile(js_path):
        return None
    content = context.safe_read(js_path)
    if not content:
        return None
    # 提取properties
    props = _extract_component_properties(content)
    return props if props else None


def _get_builtin_props(tag_name: str) -> Optional[Set[str]]:
    """获取内置组件白名单属性（Vant + 微信原生组件）
    
    v1.23.0: van-组件合并通用属性白名单(_VANT_COMMON_ATTRS)，减少误报
    """
    # 1. 检查Vant Weapp白名单（合并通用属性）
    if tag_name in _VANT_WEAPP_PROPS:
        return _VANT_WEAPP_PROPS[tag_name] | _VANT_COMMON_ATTRS
    # 2. 检查微信原生组件白名单
    if tag_name in _NATIVE_COMPONENT_PROPS:
        return _NATIVE_COMPONENT_PROPS[tag_name]
    # 3. 检查是否以van-开头（Vant组件但未在白名单中）
    if tag_name.startswith('van-'):
        return None  # 返回None表示无法确认，跳过检查
    return None


def check_20_3_component_props(context) -> List[Dict]:
    """20.3 组件属性名一致性
    
    检测逻辑：
    1. 扫描组件JS文件中properties定义（提取属性名列表）
    2. 扫描所有WXML中使用该组件时传入的属性名
    3. 对比：WXML中传了但properties中没定义的→warning
    
    v1.20.1 修复：
    - 内置Vant Weapp和微信原生组件属性白名单，避免误报
    - 修复跨组件嵌套时属性归属错误的问题（只检查当前开始标签的属性）
    - 对usingComponents声明的标签，使用被引用组件自身的属性定义进行校验
    """
    results = []
    
    if not context.project_path:
        return results
    
    # 1. 找到所有组件目录
    components = _find_components(context)
    if not components:
        return results
    
    wxml_files = context.find_files([".wxml"])
    if not wxml_files:
        return results
    
    # 构建全局组件名->props映射（用于交叉引用）
    comp_name_to_props = {}
    for comp_info in components:
        comp_name_to_props[comp_info['name']] = comp_info['props']
        # 也为usingComponents中声明的标签名建立映射
        comp_json_path = comp_info.get('json_path', '')
        component_tags = _get_component_tags(comp_json_path, context)
        for tag in component_tags:
            if tag not in comp_name_to_props:
                # 尝试从npm目录读取
                npm_props = _get_vant_props_from_npm(context, tag)
                if npm_props:
                    comp_name_to_props[tag] = npm_props
    
    # 2. 对每个组件，检查WXML中的使用
    for comp_info in components:
        comp_name = comp_info['name']
        comp_props = comp_info['props']
        comp_json_path = comp_info.get('json_path', '')
        
        # 获取组件的usingComponents声明
        component_tags = _get_component_tags(comp_json_path, context)
        
        if not comp_props and not component_tags:
            continue
        
        # v1.23.0 FP-03: van-前缀组件（Vant Weapp）属性太多无法穷举，跳过属性检查
        if comp_name.startswith('van-'):
            continue
        
        # 在所有WXML中查找该组件的使用
        for fpath in wxml_files:
            content = context.safe_read(fpath)
            if not content:
                continue
            
            # 只匹配组件自身的标签（不含usingComponents声明的其他组件标签）
            # 修复跨组件嵌套bug：属性应归属到最近的开始标签
            tag_patterns = _build_tag_patterns_for_self(comp_name)
            
            for tag_pattern in tag_patterns:
                for m in tag_pattern.finditer(content):
                    tag_content = m.group(0)
                    line_num = content[:m.start()].count('\n') + 1
                    
                    # 提取该标签使用的所有属性
                    used_attrs = _extract_wxml_attrs(tag_content)
                    
                    # 过滤掉通用属性（class, style, id, hidden, data-*, bind*, catch*等）
                    special_attrs = {
                        'class', 'style', 'id', 'hidden', 'slot',
                        'wx:if', 'wx:for', 'wx:for-item', 'wx:for-index',
                        'wx:key', 'wx:else', 'wx:elif',
                    }
                    
                    unknown_attrs = []
                    for attr in used_attrs:
                        if attr in special_attrs:
                            continue
                        if attr.startswith('data-') or attr.startswith('bind') or attr.startswith('catch'):
                            continue
                        if attr.startswith('aria-'):
                            continue
                        # 检查是否在properties中定义
                        if comp_props and attr not in comp_props:
                            unknown_attrs.append(attr)
                    
                    if unknown_attrs:
                        rel_path = os.path.relpath(fpath, context.project_path) if context.project_path else fpath
                        results.append({
                            'id': '20.3',
                            'name': '组件属性名一致性',
                            'level': 'warning',
                            'message': f'组件<{comp_name}>使用了{len(unknown_attrs)}个未定义的属性',
                            'detail': f'文件: {rel_path}:{line_num}\n未定义属性: {", ".join(unknown_attrs[:10])}\n已定义属性: {", ".join(sorted(comp_props)[:15]) if comp_props else "无"}',
                            'file': fpath,
                            'line': line_num,
                            'fix': f'在组件{comp_name}的properties中添加这些属性定义，或修正属性名拼写',
                            'suggestion_code': f"// {comp_name}.js\nComponent({{\n  properties: {{\n    // 已有: {', '.join(sorted(comp_props)[:10]) if comp_props else '无'}\n    // 需要添加: {', '.join(unknown_attrs[:5])}\n  }}\n}})",
                        })
        
        # 另外：独立检查usingComponents声明的标签（使用被引用组件的白名单）
        for tag_name in component_tags:
            # 获取该标签的有效属性白名单
            effective_props = comp_name_to_props.get(tag_name)
            if effective_props is None:
                # 尝试内置白名单
                effective_props = _get_builtin_props(tag_name)
            if effective_props is None:
                # 无法确认该标签的属性定义，跳过检查避免误报
                continue
            
            for fpath in wxml_files:
                content = context.safe_read(fpath)
                if not content:
                    continue
                
                # 匹配该标签
                tag_patterns = _build_tag_patterns_for_self(tag_name)
                for tag_pattern in tag_patterns:
                    for m in tag_pattern.finditer(content):
                        tag_content = m.group(0)
                        line_num = content[:m.start()].count('\n') + 1
                        
                        used_attrs = _extract_wxml_attrs(tag_content)
                        
                        special_attrs = {
                            'class', 'style', 'id', 'hidden', 'slot',
                            'wx:if', 'wx:for', 'wx:for-item', 'wx:for-index',
                            'wx:key', 'wx:else', 'wx:elif',
                        }
                        
                        unknown_attrs = []
                        for attr in used_attrs:
                            if attr in special_attrs:
                                continue
                            if attr.startswith('data-') or attr.startswith('bind') or attr.startswith('catch'):
                                continue
                            if attr.startswith('aria-'):
                                continue
                            if attr not in effective_props:
                                unknown_attrs.append(attr)
                        
                        if unknown_attrs:
                            rel_path = os.path.relpath(fpath, context.project_path) if context.project_path else fpath
                            results.append({
                                'id': '20.3',
                                'name': '组件属性名一致性',
                                'level': 'warning',
                                'message': f'组件<{tag_name}>使用了{len(unknown_attrs)}个未定义的属性',
                                'detail': f'文件: {rel_path}:{line_num}\n未定义属性: {", ".join(unknown_attrs[:10])}\n已定义属性: {", ".join(sorted(effective_props)[:15])}',
                                'file': fpath,
                                'line': line_num,
                                'fix': f'在组件{tag_name}的properties中添加这些属性定义，或修正属性名拼写',
                                'suggestion_code': '',
                            })
    
    return results


def _build_tag_patterns_for_self(comp_name: str) -> List[re.Pattern]:
    """构建仅匹配组件自身标签的正则（不匹配usingComponents中引用的其他组件标签）
    
    修复跨组件嵌套bug：确保属性归属到最近的开始标签。
    使用更精确的正则匹配完整的开始标签，不包含嵌套标签内容。
    """
    patterns = []
    
    tag_names = {comp_name}
    # PascalCase变体
    pascal = ''.join(word.capitalize() for word in comp_name.replace('-', '_').split('_'))
    tag_names.add(pascal)
    
    for tag_name in tag_names:
        # 匹配完整的开始标签：<tag-name ... > 或 <tag-name ... />
        # 使用 [^>]* 确保不跨越标签边界
        pattern = re.compile(
            r'<' + re.escape(tag_name) + r'(?:\s[^>]*)?\s*/?>',
            re.DOTALL | re.IGNORECASE
        )
        patterns.append(pattern)
    
    return patterns


def _find_components(context) -> List[Dict]:
    """查找项目中的所有组件，提取其properties定义"""
    components = []
    
    js_files = context.find_files([".js"])
    for fpath in js_files:
        norm_path = fpath.replace(os.sep, '/')
        if '/components/' not in norm_path:
            continue
        
        content = context.safe_read(fpath)
        if not content or 'Component(' not in content:
            continue
        
        props = _extract_component_properties(content)
        comp_name = _infer_component_name(fpath, context)
        
        # 对应的json文件
        json_path = os.path.splitext(fpath)[0] + '.json'
        
        components.append({
            'name': comp_name,
            'props': props,
            'js_path': fpath,
            'json_path': json_path,
        })
    
    return components


def _extract_component_properties(content: str) -> Set[str]:
    """从组件JS中提取properties定义的属性名"""
    props = set()
    
    # 匹配 properties: { ... } 块
    props_pattern = re.compile(r'properties\s*:\s*\{', re.MULTILINE)
    m = props_pattern.search(content)
    if not m:
        return props
    
    start = m.end()
    brace_depth = 1
    idx = start
    while idx < len(content) and brace_depth > 0:
        if content[idx] == '{':
            brace_depth += 1
        elif content[idx] == '}':
            brace_depth -= 1
        idx += 1
    
    props_body = content[start:idx - 1]
    
    # 提取属性名
    # 模式1: propName: { type: ..., value: ... }
    # 模式2: propName: Type（简写）
    prop_name_pattern = re.compile(r'(\w+)\s*:\s*(?:\{|String|Number|Boolean|Object|Array|null)', re.MULTILINE)
    for pm in prop_name_pattern.finditer(props_body):
        props.add(pm.group(1))
    
    # 也匹配简写形式
    simple_pattern = re.compile(r'(?:^|[\s,])(\w+)\s*(?=,|\}|$)', re.MULTILINE)
    for pm in simple_pattern.finditer(props_body):
        name = pm.group(1)
        if name not in ('type', 'value', 'observer', 'optionalTypes'):
            props.add(name)
    
    return props


def _infer_component_name(fpath: str, context) -> str:
    """从文件路径推断组件名"""
    # 通常 components/my-comp/my-comp.js
    basename = os.path.splitext(os.path.basename(fpath))[0]
    parent_dir = os.path.basename(os.path.dirname(fpath))
    
    if parent_dir == basename:
        return parent_dir
    return basename


def _get_component_tags(comp_json_path: str, context) -> List[str]:
    """从组件json文件中获取usingComponents声明的标签名"""
    tags = []
    if not comp_json_path or not os.path.isfile(comp_json_path):
        return tags
    
    content = context.safe_read(comp_json_path)
    if not content:
        return tags
    
    try:
        config = json.loads(content)
        using = config.get('usingComponents', {})
        for tag_name in using.keys():
            tags.append(tag_name)
    except (json.JSONDecodeError, TypeError):  # noqa: intentional empty handler
        pass
    
    return tags


def _build_tag_patterns(comp_name: str, component_tags: List[str]) -> List[re.Pattern]:
    """构建匹配组件标签的正则"""
    patterns = []
    
    # 直接用组件名匹配
    tag_names = set()
    tag_names.add(comp_name)
    
    # 添加usingComponents中声明的标签名
    for tag in component_tags:
        tag_names.add(tag)
    
    # PascalCase变体
    pascal = ''.join(word.capitalize() for word in comp_name.replace('-', '_').split('_'))
    tag_names.add(pascal)
    
    for tag_name in tag_names:
        # 匹配完整的开始标签
        pattern = re.compile(
            r'<' + re.escape(tag_name) + r'(?:\s[^>]*)?\s*/?>',
            re.DOTALL | re.IGNORECASE
        )
        patterns.append(pattern)
    
    return patterns


def _extract_wxml_attrs(tag_content: str) -> Set[str]:
    """从WXML标签中提取所有属性名"""
    attrs = set()
    
    # 匹配属性名（不含值）
    attr_pattern = re.compile(r'\s(\w[\w-]*)\s*(?:=|$)')
    for m in attr_pattern.finditer(tag_content):
        attrs.add(m.group(1))
    
    return attrs


# ===== 20.5 API响应数据结构一致性（简化版） =====
def check_20_5_api_response_structure(context) -> List[Dict]:
    """20.5 API响应数据结构一致性（简化版）
    
    检测逻辑：
    1. 扫描api.js中的请求函数，提取handleResponse/返回结构中使用的字段名
    2. 扫描页面JS中res.data.xxx的访问路径
    3. 如果页面访问了API文件中未出现的data.xxx字段→warning
    
    注意：这是简化版静态分析，可能存在误报。
    只检查明显的路径不一致（如res.data.list vs res.data.items）。
    """
    results = []
    
    if not context.project_path:
        return results
    
    # 1. 查找api.js或类似API文件
    api_files = []
    js_files = context.find_files([".js"])
    
    for fpath in js_files:
        basename = os.path.basename(fpath).lower()
        norm_path = fpath.replace(os.sep, '/')
        if 'api' in basename or '/api/' in norm_path or '/services/' in norm_path:
            api_files.append(fpath)
    
    if not api_files:
        return results
    
    # 2. 从API文件中提取res.data.xxx使用的字段路径
    api_data_fields = set()
    data_field_pattern = re.compile(r'(?:res|response|result)\s*\.\s*data\s*\.\s*(\w+)')
    
    for fpath in api_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        for m in data_field_pattern.finditer(content):
            api_data_fields.add(m.group(1))
    
    if not api_data_fields:
        return results
    
    # 3. 扫描页面JS中的res.data.xxx访问
    page_field_access = {}  # {field_name: [(file, line), ...]}
    
    for fpath in js_files:
        norm_path = fpath.replace(os.sep, '/')
        # 只检查页面文件，不检查api文件本身
        if fpath in api_files:
            continue
        if '/utils/' in norm_path or '/libs/' in norm_path or '/lib/' in norm_path:
            continue
        
        content = context.safe_read(fpath)
        if not content:
            continue
        
        lines = content.split('\n')
        for line_idx, line in enumerate(lines):
            for m in data_field_pattern.finditer(line):
                field_name = m.group(1)
                if field_name not in api_data_fields:
                    if field_name not in page_field_access:
                        page_field_access[field_name] = []
                    page_field_access[field_name].append((fpath, line_idx + 1))
    
    if page_field_access:
        detail_lines = []
        for field_name, locations in sorted(page_field_access.items()):
            for fpath, line in locations[:2]:
                rel_path = os.path.relpath(fpath, context.project_path) if context.project_path else fpath
                detail_lines.append(f"  res.data.{field_name} → {rel_path}:{line}")
        
        results.append({
            'id': '20.5',
            'name': 'API响应数据结构一致性',
            'level': 'warning',
            'message': f'页面访问了{len(page_field_access)}个API响应中未出现的data字段',
            'detail': f'API文件中使用的data字段: {", ".join(sorted(api_data_fields)[:10])}\n页面访问了但未在API中定义:\n' + '\n'.join(detail_lines[:10]),
            'file': api_files[0] if api_files else '',
            'line': 0,
            'fix': '检查API返回结构，确保页面访问的字段在API响应中存在；或更新API文件中的字段处理',
            'suggestion_code': f'// API文件中确保处理以下字段:\n// res.data.{", res.data.".join(sorted(page_field_access.keys())[:5])}',
        })
    
    return results


# ===== 20.7 JSON配置与JS实现一致性 =====
def check_20_7_json_js_consistency(context) -> List[Dict]:
    """20.7 JSON配置与JS实现一致性
    
    检测逻辑：检查页面json配置中的功能开关是否在JS中实现了对应处理函数：
    - enablePullDownRefresh:true → JS中是否有onPullDownRefresh
    - enableReachBottom → JS中是否有onReachBottom
    - disableScroll:true → 是否有相关scroll处理
    """
    results = []
    
    if not context.project_path:
        return results
    
    # 找到所有页面json文件
    json_files = context.find_files([".json"])
    
    config_mappings = {
        'enablePullDownRefresh': {
            'method': 'onPullDownRefresh',
            'desc': '下拉刷新',
        },
        'enableReachBottom': {
            'method': 'onReachBottom',
            'desc': '触底加载',
        },
    }
    
    for fpath in json_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        # 跳过app.json和组件json
        basename = os.path.basename(fpath)
        if basename == 'app.json':
            continue
        
        try:
            config = json.loads(content)
        except json.JSONDecodeError:
            continue
        
        # 只检查页面json（有usingComponents或window配置的）
        has_page_config = any(key in config for key in [
            'enablePullDownRefresh', 'enableReachBottom', 
            'disableScroll', 'navigationStyle',
            'usingComponents'
        ])
        if not has_page_config:
            continue
        
        # 找到对应的JS文件
        base_path = os.path.splitext(fpath)[0]
        js_path = base_path + '.js'
        
        if not os.path.isfile(js_path):
            continue
        
        js_content = context.safe_read(js_path)
        if not js_content:
            continue
        
        missing_handlers = []
        
        for config_key, mapping in config_mappings.items():
            if config.get(config_key, False):
                method_name = mapping['method']
                # 检查JS中是否定义了该方法
                method_pattern = re.compile(
                    r'(?:^|[\s,])' + re.escape(method_name) + r'\s*[\(:]\s*(?:function\s*)?\([^)]*\)\s*(?:=>\s*)?\{',
                    re.MULTILINE
                )
                if not method_pattern.search(js_content):
                    missing_handlers.append({
                        'config': config_key,
                        'method': method_name,
                        'desc': mapping['desc'],
                    })
        
        if missing_handlers:
            rel_path = os.path.relpath(fpath, context.project_path) if context.project_path else fpath
            detail = '; '.join([
                f"{h['config']}:true 但JS中未定义{h['method']}" 
                for h in missing_handlers
            ])
            
            results.append({
                'id': '20.7',
                'name': 'JSON配置与JS实现一致性',
                'level': 'warning',
                'message': f'JSON配置启用了{len(missing_handlers)}个功能但JS中未实现对应处理函数',
                'detail': f'文件: {rel_path}\n{detail}',
                'file': fpath,
                'line': 0,
                'fix': '在JS文件中添加对应的生命周期处理函数，或在JSON中关闭未实现的功能',
                'suggestion_code': '\n'.join([
                    f"// 添加{h['desc']}处理函数:\n{h['method']}() {{\n  // TODO: 实现{h['desc']}逻辑\n}},"
                    for h in missing_handlers
                ]),
            })
    
    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': '20.3',
        'name': '组件属性名一致性',
        'level': 'warning',
        'category': 'miniprogram_component',
        'module_id': '20',
        'applicable_types': ['miniprogram', 'mixed'],
        'description': '检查WXML中组件使用的属性是否在组件properties中定义',
        'check': check_20_3_component_props,
    },
    {
        'id': '20.5',
        'name': 'API响应数据结构一致性',
        'level': 'warning',
        'category': 'miniprogram_component',
        'module_id': '20',
        'applicable_types': ['miniprogram', 'mixed'],
        'description': '检查页面访问的res.data字段是否在API文件中出现过',
        'check': check_20_5_api_response_structure,
    },
    {
        'id': '20.7',
        'name': 'JSON配置与JS实现一致性',
        'level': 'warning',
        'category': 'miniprogram_component',
        'module_id': '20',
        'applicable_types': ['miniprogram', 'mixed'],
        'description': '检查页面json配置的功能开关(enablePullDownRefresh等)是否在JS中实现了处理函数',
        'check': check_20_7_json_js_consistency,
    },
]
