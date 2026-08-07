"""架构健康度规则集 - 分层与依赖方向子模块
从 architecture.py 拆分而来，包含架构分层、依赖方向、反向依赖、领域纯净度等规则（17.1-17.4）

v4.6.1 性能优化：
- 提取共享工具到 _arch_utils.py，与 arch_dependency.py 共用
- 复用 context walk 缓存，避免重复 os.walk
- 预编译正则 + imports 缓存 + 分层缓存跨模块共享
- 零行为变更：检测结果完全一致
"""

import os
from typing import List, Dict

# 从共享工具模块导入（零行为变更，与 arch_dependency.py 共用同一份缓存）
from rules.common._arch_utils import (
    detect_arch_layers,
    get_layer_files,
    extract_imports,
    is_forbidden_domain_import,
    check_domain_purity,
    relpath,
    _ARCH_LAYER_KEYWORDS,
)


# ===== 17.1 架构分层检测 =====
def check_17_1_arch_layer_detection(context) -> List[Dict]:
    """17.1 架构分层检测：自动识别项目是否有领域层/核心层目录结构"""
    results = []
    layers = detect_arch_layers(context)
    found_layers = {k: v for k, v in layers.items() if v}

    if not found_layers:
        results.append({
            'id': '17.1',
            'name': '架构分层检测',
            'level': 'suggestion',
            'message': '未检测到明确的分层架构（domain/core/infrastructure/controller等目录）',
            'file': '',
            'line': 0,
            'snippet': '建议参考DDD/整洁架构思想，按领域层-应用层-基础设施层-表现层组织代码',
            'fix': '创建 domain/ 或 core/ 目录存放核心业务逻辑',
        })
        return results

    layer_names = {
        "domain": "领域层",
        "application": "应用层",
        "infrastructure": "基础设施层",
        "presentation": "表现层",
    }

    details = []
    for layer, dirs in found_layers.items():
        dir_names = [os.path.basename(d) for d in dirs]
        details.append(f"  {layer_names.get(layer, layer)}: {', '.join(dir_names)} ({len(dirs)}个目录)")

    has_domain = "domain" in found_layers
    has_infra = "infrastructure" in found_layers
    has_pres = "presentation" in found_layers

    if has_domain:
        message = f"检测到{len(found_layers)}层架构分层"
        if has_infra and has_pres:
            message += "，分层完整"
        elif not has_infra:
            message += "，缺少基础设施层划分"
    else:
        message = f"检测到{len(found_layers)}层结构，但未发现明确的领域层/核心层"

    results.append({
        'id': '17.1',
        'name': '架构分层检测',
        'level': 'suggestion',
        'message': message,
        'file': '',
        'line': 0,
        'snippet': '\n'.join(details),
        'fix': '确保核心业务逻辑独立于技术框架',
    })

    return results


# ===== 17.2 依赖方向检查 =====
def check_17_2_dependency_direction(context) -> List[Dict]:
    """17.2 依赖方向检查：领域层代码中是否import了外层技术细节"""
    results = []
    layers = detect_arch_layers(context)
    domain_files = get_layer_files(context, layers, "domain")

    if not domain_files:
        results.append({
            'id': '17.2',
            'name': '依赖方向检查',
            'level': 'suggestion',
            'message': '未发现领域层文件，跳过检查',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results

    violations = []
    for f in domain_files:
        imports = extract_imports(f, context)
        rel_path = relpath(f, context.project_path, context.backend_path)
        for lineno, module, imp_type in imports:
            is_violation, vtype, reason = is_forbidden_domain_import(module, f, layers, context)
            if is_violation and vtype == "tech_detail":
                violations.append(f"  {rel_path}:{lineno} - {reason}")

    if violations:
        results.append({
            'id': '17.2',
            'name': '依赖方向检查',
            'level': 'problem',
            'message': f'领域层中有{len(violations)}处导入了外层技术细节',
            'file': '',
            'line': 0,
            'snippet': '\n'.join(violations[:20]),
            'fix': '将技术依赖抽象为接口定义在领域层，实现在基础设施层（依赖反转）',
        })
    else:
        results.append({
            'id': '17.2',
            'name': '依赖方向检查',
            'level': 'suggestion',
            'message': '领域层未发现直接导入技术框架的情况',
            'file': '',
            'line': 0,
            'snippet': '领域层依赖方向正确，未检测到技术细节泄漏',
            'fix': '',
        })

    return results


# ===== 17.3 反向依赖检测 =====
def check_17_3_reverse_dependency(context) -> List[Dict]:
    """17.3 反向依赖检测：是否存在内层依赖外层的情况"""
    results = []
    layers = detect_arch_layers(context)
    domain_files = get_layer_files(context, layers, "domain")

    if not domain_files:
        results.append({
            'id': '17.3',
            'name': '反向依赖检测',
            'level': 'suggestion',
            'message': '未发现领域层文件，跳过检查',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results

    violations = []
    for f in domain_files:
        imports = extract_imports(f, context)
        rel_path = relpath(f, context.project_path, context.backend_path)
        for lineno, module, imp_type in imports:
            is_violation, vtype, reason = is_forbidden_domain_import(module, f, layers, context)
            if is_violation and vtype == "reverse_dependency":
                violations.append(f"  {rel_path}:{lineno} - {reason}")

    # 额外检查：应用层是否依赖表现层
    app_files = get_layer_files(context, layers, "application")

    for f in app_files:
        imports = extract_imports(f, context)
        rel_path = relpath(f, context.project_path, context.backend_path)
        for lineno, module, imp_type in imports:
            module_lower = module.lower()
            # 预编译模式匹配表现层关键词
            for kw, pattern in _ARCH_LAYER_KEYWORDS_PRESENTATION:
                if pattern.search(module_lower):
                    violations.append(f"  {rel_path}:{lineno} - 应用层依赖表现层: {module}")
                    break

    if violations:
        results.append({
            'id': '17.3',
            'name': '反向依赖检测',
            'level': 'blocking',
            'message': f'发现{len(violations)}处反向依赖（内层依赖外层）',
            'file': '',
            'line': 0,
            'snippet': '\n'.join(violations[:20]),
            'fix': '违反依赖方向原则：内层不能依赖外层。应通过依赖反转，将接口定义在内层',
        })
    else:
        results.append({
            'id': '17.3',
            'name': '反向依赖检测',
            'level': 'suggestion',
            'message': '未检测到明显的反向依赖',
            'file': '',
            'line': 0,
            'snippet': '内层（领域层）未发现直接依赖外层的情况',
            'fix': '',
        })

    return results


# ===== 17.4 领域层纯净度 =====
def check_17_4_domain_purity(context) -> List[Dict]:
    """17.4 领域层纯净度：领域层代码中是否包含技术实现细节"""
    results = []
    layers = detect_arch_layers(context)
    domain_files = get_layer_files(context, layers, "domain")

    if not domain_files:
        results.append({
            'id': '17.4',
            'name': '领域层纯净度',
            'level': 'suggestion',
            'message': '未发现领域层文件，跳过检查',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results

    impure_files = []
    total_issues = 0
    for f in domain_files:
        issues = check_domain_purity(f, context)
        if issues:
            rel_path = relpath(f, context.project_path, context.backend_path)
            total_issues += len(issues)
            details = [f"  行{i}: [{label}] {snippet}" for i, label, snippet in issues[:5]]
            impure_files.append(f"{rel_path} ({len(issues)}处):\n" + "\n".join(details))

    if impure_files:
        results.append({
            'id': '17.4',
            'name': '领域层纯净度',
            'level': 'problem',
            'message': f'领域层中有{len(impure_files)}个文件包含技术实现细节（共{total_issues}处）',
            'file': '',
            'line': 0,
            'snippet': '\n\n'.join(impure_files[:10]),
            'fix': '领域层应只包含纯业务逻辑，技术细节（SQL/HTTP/IO）应移至基础设施层',
        })
    else:
        results.append({
            'id': '17.4',
            'name': '领域层纯净度',
            'level': 'suggestion',
            'message': '领域层代码纯净，未检测到技术实现细节',
            'file': '',
            'line': 0,
            'snippet': '领域层保持业务纯净，未发现SQL/HTTP/文件IO等技术实现',
            'fix': '',
        })

    return results


# ===== 预编译：表现层关键词匹配（供17.3使用） =====
import re
_ARCH_LAYER_KEYWORDS_PRESENTATION = [
    (kw, re.compile(r'(^|[\./])' + re.escape(kw) + r'([\./]|$)'))
    for kw in _ARCH_LAYER_KEYWORDS["presentation"]
]


# ===== 规则定义列表 =====
RULES = [
    {
        'id': '17.1',
        'name': '架构分层检测',
        'level': 'suggestion',
        'category': 'architecture',
        'module_id': '17',
        'applicable_types': [],
        'description': '自动识别项目架构分层（DDD/整洁架构），检测领域层/应用层/基础设施层等',
        'check': check_17_1_arch_layer_detection,
    },
    {
        'id': '17.2',
        'name': '依赖方向检查',
        'level': 'problem',
        'category': 'architecture',
        'module_id': '17',
        'applicable_types': [],
        'description': '检查领域层代码中是否import了外层技术细节（数据库/HTTP/SDK等）',
        'check': check_17_2_dependency_direction,
    },
    {
        'id': '17.3',
        'name': '反向依赖检测',
        'level': 'blocking',
        'category': 'architecture',
        'module_id': '17',
        'applicable_types': [],
        'description': '检测是否存在内层依赖外层的反向依赖（违反依赖方向原则）',
        'check': check_17_3_reverse_dependency,
    },
    {
        'id': '17.4',
        'name': '领域层纯净度',
        'level': 'problem',
        'category': 'architecture',
        'module_id': '17',
        'applicable_types': [],
        'description': '检查领域层代码是否包含SQL/HTTP/文件IO等技术实现细节',
        'check': check_17_4_domain_purity,
    },
]
