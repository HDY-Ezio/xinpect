"""
组件设计规则集 (v5.2.0)
检测组件设计问题 - 适用于含前端组件的项目
包含: props数量、组件行数、单一职责、状态提升、组件命名、
PropTypes、默认值、事件命名等8项检查
"""

import re
import os
from typing import List, Dict, Any


# ===== COMP-001 props数量过多 =====
def check_comp_001_props_count(context) -> List[Dict]:
    """COMP-001 props数量过多 - props>7个"""
    results = []
    component_files = context.find_files([".tsx", ".jsx", ".vue"])
    threshold = context.project_profile.get_adjusted_threshold('max_props', 7)
    issues = []

    for fpath in component_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        ext = os.path.splitext(fpath)[1].lower()

        if ext in ('.tsx', '.jsx'):
            # Find interface/type definition for props
            props_pattern = re.compile(
                r'(?:interface|type)\s+\w*Props\w*\s*\{([^}]+)\}',
                re.DOTALL
            )
            for m in props_pattern.finditer(content):
                props_body = m.group(1)
                # Count property definitions
                props = re.findall(r'^\s*(?:readonly\s+)?(\w+)[?]?\s*:', props_body, re.MULTILINE)
                if len(props) > threshold:
                    line_num = content[:m.start()].count('\n') + 1
                    issues.append((fpath, line_num, len(props)))

            # Also check destructured props in function params
            destructure = re.search(r'(?:function\s+\w+|const\s+\w+)\s*\(\s*\{([^}]+)\}', content)
            if destructure:
                props_str = destructure.group(1)
                prop_names = [p.strip().split(':')[0].strip().split(' ')[0] for p in props_str.split(',')]
                prop_names = [p for p in prop_names if p and not p.startswith('//')]
                if len(prop_names) > threshold:
                    line_num = content[:destructure.start()].count('\n') + 1
                    issues.append((fpath, line_num, len(prop_names)))

        elif ext == '.vue':
            # Check Vue component props
            props_match = re.search(r'props\s*:\s*\{([^}]+)\}', content, re.DOTALL)
            if props_match:
                props_body = props_match.group(1)
                props = re.findall(r'(\w+)\s*:', props_body)
                if len(props) > threshold:
                    line_num = content[:props_match.start()].count('\n') + 1
                    issues.append((fpath, line_num, len(props)))

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} 有{c}个props"
            for f, l, c in issues[:8]
        )
        results.append({
            'id': 'COMP-001',
            'name': 'props数量过多',
            'level': 'info',
            'message': f'发现{len(issues)}个组件props超过{threshold}个',
            'detail': detail,
            'file': issues[0][0] if issues else '',
            'line': issues[0][1] if issues else 0,
            'fix': '将相关props合并为对象，或使用children/render props模式减少props',
        })

    return results


# ===== COMP-002 组件行数过多 =====
def check_comp_002_component_length(context) -> List[Dict]:
    """COMP-002 组件行数过多 - 组件>300行"""
    results = []
    component_files = context.find_files([".tsx", ".jsx", ".vue"])
    max_lines = context.project_profile.get_adjusted_threshold('component_lines', 300)
    issues = []

    for fpath in component_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        line_count = len(content.split('\n'))
        if line_count > max_lines:
            issues.append((fpath, line_count))

    if issues:
        issues.sort(key=lambda x: x[1], reverse=True)
        detail = '\n'.join(
            f"  {os.path.basename(f)}: {c}行"
            for f, c in issues[:5]
        )
        results.append({
            'id': 'COMP-002',
            'name': '组件行数过多',
            'level': 'info',
            'message': f'发现{len(issues)}个组件超过{max_lines}行',
            'detail': detail,
            'file': issues[0][0] if issues else '',
            'line': 0,
            'fix': '将大组件拆分为子组件，提取自定义Hook/Composable，保持组件<300行',
        })

    return results


# ===== COMP-003 单一职责违反 =====
def check_comp_003_single_responsibility(context) -> List[Dict]:
    """COMP-003 单一职责违反 - 组件同时处理UI和业务逻辑"""
    results = []
    component_files = context.find_files([".tsx", ".jsx"])
    issues = []

    # Business logic indicators
    biz_patterns = [
        r'fetch\s*\(', r'axios\.', r'\.get\s*\(', r'\.post\s*\(',
        r'localStorage', r'sessionStorage',
        r'setTimeout\s*\(', r'setInterval\s*\(',
        r'WebSocket', r'new\s+Worker',
        r'indexedDB',
    ]

    for fpath in component_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        # Check if component has both UI (JSX return) and business logic
        has_jsx = bool(re.search(r'return\s*\(\s*<', content)) or bool(re.search(r'return\s*<\w+', content))
        biz_count = 0
        for pattern in biz_patterns:
            if re.search(pattern, content):
                biz_count += 1

        if has_jsx and biz_count >= 3:
            # Component mixes UI and business logic
            line_count = len(content.split('\n'))
            if line_count > 100:  # Only flag substantial components
                issues.append((fpath, 1, biz_count))

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)} 有{c}个业务逻辑模式"
            for f, _, c in issues[:8]
        )
        results.append({
            'id': 'COMP-003',
            'name': '单一职责违反',
            'level': 'info',
            'message': f'发现{len(issues)}个组件混合UI和业务逻辑',
            'detail': detail,
            'file': issues[0][0] if issues else '',
            'line': issues[0][1] if issues else 0,
            'fix': '将业务逻辑提取到自定义Hook或Service层，组件只负责UI渲染',
        })

    return results


# ===== COMP-004 状态提升不当 =====
def check_comp_004_state_lift(context) -> List[Dict]:
    """COMP-004 状态提升不当 - 状态应在子组件管理"""
    results = []
    component_files = context.find_files([".tsx", ".jsx"])
    issues = []

    for fpath in component_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        # Find useState hooks and check if state is only passed down to one child
        state_pattern = re.compile(r'const\s+\[(\w+),\s*set(\w+)\]\s*=\s*useState')
        states = state_pattern.findall(content)

        for state_name, setter_name in states:
            # Check if state is only used in one place (passed as prop)
            state_refs = len(re.findall(rf'\b{re.escape(state_name)}\b', content))
            setter_refs = len(re.findall(rf'\bset{re.escape(setter_name)}\b', content))

            # If state is defined but setter is only used once and state is passed as prop
            if state_refs <= 2 and setter_refs == 1:
                # Might be an unnecessarily lifted state
                line_num = content.find(f'[{state_name},') 
                if line_num >= 0:
                    line = content[:line_num].count('\n') + 1
                    # Only flag if component has children that receive this state
                    if re.search(rf'<\w+\s+[^>]*{re.escape(state_name)}', content):
                        issues.append((fpath, line, state_name))

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} 状态 '{n}' 可能不需要提升"
            for f, l, n in issues[:8]
        )
        results.append({
            'id': 'COMP-004',
            'name': '状态提升不当',
            'level': 'info',
            'message': f'发现{len(issues)}个可能不需要提升的状态',
            'detail': detail,
            'file': issues[0][0] if issues else '',
            'line': issues[0][1] if issues else 0,
            'fix': '考虑将状态下移到实际使用它的子组件中，减少不必要的props传递',
        })

    return results


# ===== COMP-005 组件命名不规范 =====
def check_comp_005_component_naming(context) -> List[Dict]:
    """COMP-005 组件命名不规范 - 未使用PascalCase"""
    results = []
    component_files = context.find_files([".tsx", ".jsx"])
    issues = []

    for fpath in component_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        # Find component definitions
        patterns = [
            r'function\s+([a-z]\w*)\s*(?:<[^>]*>)?\s*\(',  # function component (lowercase)
            r'const\s+([a-z]\w*)\s*(?::\s*\w+)?\s*=\s*(?:React\.memo|React\.forwardRef)?\s*\(',  # arrow component
        ]

        for pattern in patterns:
            for m in re.finditer(pattern, content):
                name = m.group(1)
                # Skip hooks (useXxx)
                if name.startswith('use'):
                    continue
                # Skip if starts with uppercase (already PascalCase)
                if name[0].isupper():
                    continue
                line_num = content[:m.start()].count('\n') + 1
                issues.append((fpath, line_num, name))

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} '{n}' 应为PascalCase"
            for f, l, n in issues[:8]
        )
        results.append({
            'id': 'COMP-005',
            'name': '组件命名不规范',
            'level': 'info',
            'message': f'发现{len(issues)}个组件未使用PascalCase命名',
            'detail': detail,
            'file': issues[0][0] if issues else '',
            'line': issues[0][1] if issues else 0,
            'fix': '组件名使用PascalCase，如 UserProfile、OrderList',
        })

    return results


# ===== COMP-006 缺少PropTypes =====
def check_comp_006_missing_proptypes(context) -> List[Dict]:
    """COMP-006 缺少PropTypes - props无类型定义"""
    results = []
    component_files = context.find_files([".tsx", ".jsx"])
    issues = []

    for fpath in component_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        ext = os.path.splitext(fpath)[1].lower()

        if ext == '.jsx':
            # Check for components with destructured props but no PropTypes
            # Find function components
            func_components = re.finditer(
                r'(?:function\s+(\w+)|const\s+(\w+)\s*=\s*(?:React\.memo|React\.forwardRef)?)\s*[\(<]',
                content
            )
            for m in func_components:
                comp_name = m.group(1) or m.group(2)
                if not comp_name or comp_name[0].islower():
                    continue
                # Check if this component uses props
                has_props = bool(re.search(rf'\b{re.escape(comp_name)}\b.*\bprops\b|\b{re.escape(comp_name)}\b.*\(\s*\{{', content))
                # Check if PropTypes or TypeScript types are defined
                has_types = (
                    bool(re.search(rf'{re.escape(comp_name)}\.propTypes', content)) or
                    bool(re.search(rf'interface\s+\w*{re.escape(comp_name)}\w*Props', content)) or
                    bool(re.search(rf'type\s+\w*{re.escape(comp_name)}\w*Props', content)) or
                    bool(re.search(r':\s*\w+Props\b', content))
                )

                if has_props and not has_types:
                    line_num = content[:m.start()].count('\n') + 1
                    issues.append((fpath, line_num, comp_name))

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} 组件 '{n}' 缺少props类型"
            for f, l, n in issues[:8]
        )
        results.append({
            'id': 'COMP-006',
            'name': '缺少PropTypes',
            'level': 'info',
            'message': f'发现{len(issues)}个组件缺少props类型定义',
            'detail': detail,
            'file': issues[0][0] if issues else '',
            'line': issues[0][1] if issues else 0,
            'fix': '为组件添加TypeScript接口或PropTypes定义，明确props类型',
        })

    return results


# ===== COMP-007 默认值缺失 =====
def check_comp_007_missing_defaults(context) -> List[Dict]:
    """COMP-007 默认值缺失 - 可选props无默认值"""
    results = []
    component_files = context.find_files([".tsx", ".jsx", ".vue"])
    issues = []

    for fpath in component_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        ext = os.path.splitext(fpath)[1].lower()

        if ext in ('.tsx', '.jsx'):
            # Find optional props (with ?) that don't have default values
            interface_match = re.search(r'(?:interface|type)\s+\w*Props\w*\s*\{([^}]+)\}', content, re.DOTALL)
            if interface_match:
                props_body = interface_match.group(1)
                optional_props = re.findall(r'(\w+)\??:', props_body)
                optional_with_q = re.findall(r'(\w+)\?:', props_body)

                # Check if defaultProps or default values exist
                has_defaults = bool(re.search(r'defaultProps', content))
                # Check for default values in destructuring
                has_param_defaults = bool(re.search(r'=\s*[^,}\s]+', content))

                if optional_with_q and not has_defaults:
                    # Check individual props for default values
                    for prop in optional_with_q:
                        # Check if prop has default in destructuring
                        if not re.search(rf'{re.escape(prop)}\s*=\s*[^,}}]', content):
                            line_match = re.search(rf'({re.escape(prop)}\?:)', props_body)
                            if line_match:
                                line_num = content[:interface_match.start()].count('\n') + \
                                          props_body[:line_match.start()].count('\n') + 1
                                issues.append((fpath, line_num, prop))

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} prop '{n}' 缺少默认值"
            for f, l, n in issues[:8]
        )
        results.append({
            'id': 'COMP-007',
            'name': '默认值缺失',
            'level': 'info',
            'message': f'发现{len(issues)}个可选props缺少默认值',
            'detail': detail,
            'file': issues[0][0] if issues else '',
            'line': issues[0][1] if issues else 0,
            'fix': '为可选props添加默认值，如在解构时设置 const { title = "" } = props',
        })

    return results


# ===== COMP-008 事件命名不规范 =====
def check_comp_008_event_naming(context) -> List[Dict]:
    """COMP-008 事件命名不规范 - 未使用on前缀"""
    results = []
    component_files = context.find_files([".tsx", ".jsx"])
    issues = []

    for fpath in component_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        # Find props that are functions but don't start with 'on'
        interface_match = re.search(r'(?:interface|type)\s+\w*Props\w*\s*\{([^}]+)\}', content, re.DOTALL)
        if interface_match:
            props_body = interface_match.group(1)
            # Find function-type props
            func_props = re.findall(r'(\w+)\s*\??:\s*(?:\(|React\.EventHandler|Function|\w+Handler)', props_body)
            for prop in func_props:
                if not prop.startswith('on') and not prop.startswith('render') and not prop.startswith('children'):
                    if len(prop) > 2:
                        line_match = re.search(rf'\b{re.escape(prop)}\s*\?:', props_body)
                        if line_match:
                            line_num = content[:interface_match.start()].count('\n') + \
                                      props_body[:line_match.start()].count('\n') + 1
                            issues.append((fpath, line_num, prop))

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} '{n}' 建议改为 'on{ n[0].upper()}{n[1:]}'"
            for f, l, n in issues[:8]
        )
        results.append({
            'id': 'COMP-008',
            'name': '事件命名不规范',
            'level': 'info',
            'message': f'发现{len(issues)}个事件prop未使用on前缀',
            'detail': detail,
            'file': issues[0][0] if issues else '',
            'line': issues[0][1] if issues else 0,
            'fix': '事件prop使用on前缀，如 onClick、onChange、onSubmit',
        })

    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'COMP-001',
        'name': 'props数量过多',
        'level': 'info',
        'category': 'component_design',
        'module_id': '28',
        'applicable_types': ['miniprogram', 'web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查组件props是否超过7个',
        'check': check_comp_001_props_count,
    },
    {
        'id': 'COMP-002',
        'name': '组件行数过多',
        'level': 'info',
        'category': 'component_design',
        'module_id': '28',
        'applicable_types': ['miniprogram', 'web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查组件是否超过300行',
        'check': check_comp_002_component_length,
    },
    {
        'id': 'COMP-003',
        'name': '单一职责违反',
        'level': 'info',
        'category': 'component_design',
        'module_id': '28',
        'applicable_types': ['miniprogram', 'web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查组件是否同时处理UI和业务逻辑',
        'check': check_comp_003_single_responsibility,
    },
    {
        'id': 'COMP-004',
        'name': '状态提升不当',
        'level': 'info',
        'category': 'component_design',
        'module_id': '28',
        'applicable_types': ['miniprogram', 'web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查状态是否应下移到子组件',
        'check': check_comp_004_state_lift,
    },
    {
        'id': 'COMP-005',
        'name': '组件命名不规范',
        'level': 'info',
        'category': 'component_design',
        'module_id': '28',
        'applicable_types': ['miniprogram', 'web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查组件是否使用PascalCase命名',
        'check': check_comp_005_component_naming,
    },
    {
        'id': 'COMP-006',
        'name': '缺少PropTypes',
        'level': 'info',
        'category': 'component_design',
        'module_id': '28',
        'applicable_types': ['miniprogram', 'web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查组件props是否有类型定义',
        'check': check_comp_006_missing_proptypes,
    },
    {
        'id': 'COMP-007',
        'name': '默认值缺失',
        'level': 'info',
        'category': 'component_design',
        'module_id': '28',
        'applicable_types': ['miniprogram', 'web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查可选props是否有默认值',
        'check': check_comp_007_missing_defaults,
    },
    {
        'id': 'COMP-008',
        'name': '事件命名不规范',
        'level': 'info',
        'category': 'component_design',
        'module_id': '28',
        'applicable_types': ['miniprogram', 'web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查事件prop是否使用on前缀',
        'check': check_comp_008_event_naming,
    },
]
