"""架构健康度规则集 - 依赖反转与架构独立性子模块
从 architecture.py 拆分而来，包含依赖反转检测和架构独立性验证规则（17.5-17.6）

v4.6.1 性能优化：
- 提取共享工具到 _arch_utils.py，与 arch_layering.py 共用同一份缓存
- 复用 context walk 缓存，避免重复 os.walk
- 预编译正则 + imports 缓存 + 分层缓存跨模块共享
- 零行为变更：检测结果完全一致
"""

import re
import os
from typing import List, Dict

# 从共享工具模块导入（与 arch_layering.py 共用同一份缓存）
from rules.common._arch_utils import (
    detect_arch_layers,
    get_layer_files,
    extract_imports,
    is_forbidden_domain_import,
    has_domain_interface,
    get_infra_implementations,
    is_relative_import,
    resolve_relative_import,
    get_file_layer,
    relpath,
    _ARCH_LAYER_KEYWORDS,
    _PYTHON_STDLIB,
)


# ===== 17.5 依赖反转检测 =====
def check_17_5_dependency_inversion(context) -> List[Dict]:
    """17.5 依赖反转检测：数据访问接口是否定义在领域层"""
    results = []
    layers = detect_arch_layers(context)
    domain_files = get_layer_files(context, layers, "domain")
    infra_files = get_layer_files(context, layers, "infrastructure")

    if not domain_files:
        results.append({
            'id': '17.5',
            'name': '依赖反转检测',
            'level': 'suggestion',
            'message': '未发现领域层文件，跳过检查',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results

    # 查找领域层中的接口/抽象类
    domain_interfaces = {}
    for f in domain_files:
        has_iface, names = has_domain_interface(f, context)
        if has_iface:
            rel_path = relpath(f, context.project_path, context.backend_path)
            domain_interfaces[rel_path] = names

    # 查找基础设施层中的实现
    infra_implementations = []
    for f in infra_files:
        content = context.safe_read(f)
        if not content:
            continue
        rel_path = relpath(f, context.project_path, context.backend_path)
        impls = get_infra_implementations(f, context)
        for impl_str in impls:
            infra_implementations.append(f"{rel_path}: {impl_str}")

    if domain_interfaces:
        total_interfaces = sum(len(v) for v in domain_interfaces.values())
        details = [f"  {path}: {', '.join(names)}" for path, names in list(domain_interfaces.items())[:10]]
        if infra_implementations:
            details.append("")
            details.append("基础设施层实现:")
            details.extend([f"  {impl}" for impl in infra_implementations[:10]])
            level = 'suggestion'
            message = f"检测到{total_interfaces}个领域层接口，基础设施层有{len(infra_implementations)}个实现"
        else:
            level = 'problem'
            message = f"领域层有{total_interfaces}个接口，但未检测到基础设施层的对应实现"
        results.append({
            'id': '17.5',
            'name': '依赖反转检测',
            'level': level,
            'message': message,
            'file': '',
            'line': 0,
            'snippet': '\n'.join(details),
            'fix': '确保Repository/Gateway等接口定义在领域层，具体实现在基础设施层（依赖反转原则）',
        })
    else:
        results.append({
            'id': '17.5',
            'name': '依赖反转检测',
            'level': 'suggestion',
            'message': '领域层未检测到明确的Repository/Gateway接口定义',
            'file': '',
            'line': 0,
            'snippet': '建议将数据访问抽象为接口放在领域层，实现放在基础设施层（依赖反转原则）',
            'fix': '',
        })

    return results


# ===== 17.6 架构独立性验证 =====
def check_17_6_arch_independence(context) -> List[Dict]:
    """17.6 架构独立性验证：领域层是否能独立存在（仅依赖自身或标准库）"""
    results = []
    layers = detect_arch_layers(context)
    domain_files = get_layer_files(context, layers, "domain")

    if not domain_files:
        results.append({
            'id': '17.6',
            'name': '架构独立性验证',
            'level': 'suggestion',
            'message': '未发现领域层文件，跳过检查',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results

    external_deps = {}
    internal_deps = set()
    stdlib_deps = set()

    for f in domain_files:
        imports = extract_imports(f, context)
        rel_path = relpath(f, context.project_path, context.backend_path)
        for lineno, module, imp_type in imports:
            module_lower = module.lower()

            # 跳过相对导入（属于领域层内部）
            if is_relative_import(module):
                target_file = resolve_relative_import(f, module, context)
                if target_file:
                    target_layer = get_file_layer(target_file, layers, context)
                    if target_layer == "domain":
                        internal_deps.add(module)
                    else:
                        if module not in external_deps:
                            external_deps[module] = []
                        external_deps[module].append(f"{rel_path}:{lineno}")
                continue

            # Python标准库
            if f.endswith(".py"):
                top_module = module_lower.split(".")[0]
                if top_module in _PYTHON_STDLIB:
                    stdlib_deps.add(module)
                    continue

            # 检查是否是领域层内部模块
            is_internal = False
            for d in layers.get("domain", []):
                d_name = os.path.basename(d).lower()
                if module_lower.startswith(d_name + ".") or module_lower.startswith(d_name + "/"):
                    is_internal = True
                    internal_deps.add(module)
                    break
            if is_internal:
                continue

            # 其余视为外部依赖
            if module not in external_deps:
                external_deps[module] = []
            external_deps[module].append(f"{rel_path}:{lineno}")

    if external_deps:
        total_external = len(external_deps)
        details = []
        for dep, files in sorted(external_deps.items())[:20]:
            details.append(f"  {dep} ({len(files)}处): {files[0]}")
        results.append({
            'id': '17.6',
            'name': '架构独立性验证',
            'level': 'problem',
            'message': f'领域层依赖{total_external}个外部模块，独立性不足',
            'file': '',
            'line': 0,
            'snippet': '\n'.join(details),
            'fix': '通过依赖反转和接口抽象，将外部依赖移至基础设施层，使领域层可独立测试',
        })
    else:
        results.append({
            'id': '17.6',
            'name': '架构独立性验证',
            'level': 'suggestion',
            'message': '领域层仅依赖自身和标准库，架构独立性良好',
            'file': '',
            'line': 0,
            'snippet': f'领域层依赖：{len(internal_deps)}个内部模块 + {len(stdlib_deps)}个标准库模块',
            'fix': '',
        })

    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': '17.5',
        'name': '依赖反转检测',
        'level': 'suggestion',
        'category': 'architecture',
        'module_id': '17',
        'applicable_types': [],
        'description': '检测Repository/Gateway等数据访问接口是否定义在领域层（依赖反转原则）',
        'check': check_17_5_dependency_inversion,
    },
    {
        'id': '17.6',
        'name': '架构独立性验证',
        'level': 'problem',
        'category': 'architecture',
        'module_id': '17',
        'applicable_types': [],
        'description': '验证领域层是否能独立存在（仅依赖自身或标准库）',
        'check': check_17_6_arch_independence,
    },
]
