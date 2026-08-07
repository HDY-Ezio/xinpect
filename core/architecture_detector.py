#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
架构识别层 - QA质检框架v21 P0根因修复
核心目标：先识别项目架构风格，再应用对应规则集，避免强行套用DDD规则导致的误报

架构风格分类（7类）：
1. DDD_LAYERED        - DDD分层架构（领域层/应用层/基础设施层/表现层清晰分离）
2. THREE_TIER_MVC     - 三层MVC架构（Model-View-Controller / 数据层-业务层-表现层）
3. MICROSERVICE       - 微服务架构（多服务、独立部署、API网关）
4. SINGLE_FILE        - 单文件轻量架构（FastAPI/Flask小项目，main.py集中大部分逻辑）
5. PURE_SCRIPT        - 纯脚本/工具项目（一次性脚本、运维工具、CLI工具）
6. SINGLE_FILE_SCRIPT - 单文件脚本工具（只有1个主Python文件、无目录结构、以脚本方式运行）
7. NEXTJS_WEB         - Next.js Web前端项目（App Router/Pages Router）

检测依据：
- 目录结构深度与模式
- 是否有domain/application/infra等DDD特征目录
- 框架特征（FastAPI/Flask/Django/Spring等）
- 总文件数与代码量
- 入口文件数量与职责分布
"""

import os
import re
from typing import Dict, List, Tuple, Optional, Any
from collections import defaultdict


# ===== 架构风格枚举 =====
ARCH_STYLE_DDD = "ddd_layered"
ARCH_STYLE_THREE_TIER = "three_tier_mvc"
ARCH_STYLE_MICROSERVICE = "microservice"
ARCH_STYLE_SINGLE_FILE = "single_file_lightweight"
ARCH_STYLE_PURE_SCRIPT = "pure_script"
ARCH_STYLE_SINGLE_FILE_SCRIPT = "single_file_script"  # v21新增：单文件脚本工具
ARCH_STYLE_NEXTJS_WEB = "nextjs_web"  # v21新增：Next.js Web前端项目

ARCH_STYLE_NAMES = {
    ARCH_STYLE_DDD: "DDD分层架构",
    ARCH_STYLE_THREE_TIER: "三层MVC架构",
    ARCH_STYLE_MICROSERVICE: "微服务架构",
    ARCH_STYLE_SINGLE_FILE: "单文件轻量架构",
    ARCH_STYLE_PURE_SCRIPT: "纯脚本/工具项目",
    ARCH_STYLE_SINGLE_FILE_SCRIPT: "单文件脚本工具",
    ARCH_STYLE_NEXTJS_WEB: "Next.js Web项目",
}

# ===== 各层关键词 =====
ARCH_LAYER_KEYWORDS = {
    "domain": ["domain", "core/domain", "entities", "domain_model", "domain_models"],
    "application": ["application", "app", "usecase", "use_case", "use_cases", "service", "services", "business"],
    "infrastructure": ["infrastructure", "infra", "repository", "repositories", "persistence", "data_access", "dal", "dao"],
    "presentation": ["presentation", "api", "controllers", "controller", "handlers", "handler", "views", "view", "routes", "route", "entrypoints", "entrypoint"],
    "interface": ["interface", "interfaces", "port", "ports", "gateway", "gateways"],
}

# DDD特征模式
DDD_PATTERNS = [
    (r'class\s+\w+Repository\b', "Repository接口"),
    (r'class\s+\w+Gateway\b', "Gateway接口"),
    (r'class\s+\w+Port\b', "Port接口"),
    (r'class\s+\w+Aggregate\b', "聚合根"),
    (r'class\s+\w+Entity\b', "实体基类"),
    (r'class\s+\w+ValueObject\b', "值对象"),
    (r'ABC|abstractmethod|@abstractmethod', "抽象基类/接口"),
    (r'DomainEvent|domain_event', "领域事件"),
]

# 运维脚本特征文件名
OPS_SCRIPT_PATTERNS = [
    r'^patch_.*\.py$',
    r'^migrate_.*\.py$',
    r'^fix_.*\.py$',
    r'^deploy.*\.py$',
    r'^setup_.*\.py$',
    r'^init_db.*\.py$',
    r'^seed_.*\.py$',
    r'^backup_.*\.py$',
    r'^restore_.*\.py$',
    r'^cleanup_.*\.py$',
    r'^data_migration.*\.py$',
    r'^test_.*\.py$',
    r'_test\.py$',
    r'^conftest\.py$',
]

# Web框架特征
WEB_FRAMEWORK_PATTERNS = {
    "fastapi": [r'from\s+fastapi|import\s+fastapi|FastAPI\s*\(', r'@app\.(get|post|put|delete|patch)\b', r'APIRouter\s*\('],
    "flask": [r'from\s+flask|import\s+flask|Flask\s*\(', r'@app\.route\b', r'@blueprint\.route\b'],
    "django": [r'django\.db|from\s+django|import\s+django', r'class\s+\w+View\b', r'urls\.py'],
}


def find_files_frontend(project_path: str, ext: str, exclude_dirs: list, exclude_files: list) -> List[str]:
    """前端文件查找辅助函数"""
    result = []
    if not project_path or not os.path.isdir(project_path):
        return result
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for f in files:
            if f.endswith(ext):
                full_path = os.path.join(root, f)
                skip = False
                for ef in exclude_files:
                    if ef in full_path:
                        skip = True
                        break
                if not skip:
                    result.append(full_path)
    return result



def _collect_py_files_for_arch(search_paths, exclude_dirs, exclude_files):
    """Collect Python files for architecture detection."""
    py_files = []
    for search_path in search_paths:
        for root, dirs, files in os.walk(search_path):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for f in files:
                if f.endswith('.py'):
                    full_path = os.path.join(root, f)
                    if not any(ef in full_path for ef in exclude_files):
                        py_files.append(full_path)
    return py_files


def _count_code_lines(py_files):
    """Count total code lines across all Python files."""
    total = 0
    for f in py_files:
        try:
            with open(f, 'r', encoding='utf-8', errors='ignore') as fh:
                total += len(fh.read().split('\n'))
        except Exception as e:  # noqa: broad exception handling
            pass
    return total


def _detect_ops_scripts(py_files):
    """Detect ops/maintenance script files."""
    return [f for f in py_files
            for pattern in OPS_SCRIPT_PATTERNS
            if re.match(pattern, os.path.basename(f), re.IGNORECASE)]


def _detect_framework(py_files, search_paths):
    """Detect web framework from main entry files."""
    main_files = [f for f in py_files
                  if os.path.basename(f) in ('main.py', 'app.py', 'application.py', '__init__.py')]
    all_content = ""
    for f in main_files[:5]:
        try:
            with open(f, 'r', encoding='utf-8', errors='ignore') as fh:
                all_content += fh.read()
        except Exception as e:  # noqa: broad exception handling
            pass

    for fw, patterns in WEB_FRAMEWORK_PATTERNS.items():
        match_count = sum(1 for pat in patterns if re.search(pat, all_content, re.IGNORECASE))
        if match_count >= 2:
            return fw, [f"{fw}框架特征({match_count}个)"]
    return "", []


def _score_ddd_architecture(layers, layer_count, py_files):
    """Score DDD architecture likelihood."""
    ddd_score = 0.0
    features = []
    domain_dirs = layers.get("domain", [])
    if not domain_dirs or layer_count < 3:
        return 0.0, []

    ddd_score += 0.3
    domain_files = [f for d in domain_dirs for f in py_files
                    if f.startswith(d + os.sep) or f == d]

    ddd_feature_count = 0
    for f in domain_files[:20]:
        try:
            with open(f, 'r', encoding='utf-8', errors='ignore') as fh:
                fc = fh.read()
            if any(re.search(p, fc) for p, _ in DDD_PATTERNS):
                ddd_feature_count += 1
        except Exception as e:  # noqa: broad exception handling
            pass

    if domain_files and ddd_feature_count / len(domain_files[:20]) >= 0.2:
        ddd_score += 0.4
        features.append(f"领域层有{ddd_feature_count}个DDD特征模式")
    if layers.get("application"):
        ddd_score += 0.15
    if layers.get("infrastructure"):
        ddd_score += 0.15

    return min(ddd_score, 1.0), features


def _score_mvc_architecture(py_files, layers, layer_count, detected_framework):
    """Score three-tier MVC architecture."""
    has_model = any('model' in os.path.basename(f).lower() or 'models' in f.lower() for f in py_files)
    has_controller = bool(layers.get("presentation"))
    has_service = bool(layers.get("application")) or any('service' in f.lower() for f in py_files)

    score = 0.0
    if has_model and has_controller:
        score += 0.4
    if has_service:
        score += 0.2
    if layer_count == 3 and not layers.get("domain"):
        score += 0.2
    if detected_framework in ('django', 'flask'):
        score += 0.2
    return min(score, 1.0)


def _score_single_file_architecture(py_files, total_lines, layer_count, detected_framework,
                                     backend_path, project_path, layers=None):
    """Score single-file/lightweight architecture.
    
    v3.5.1 fix: added optional `layers` parameter to avoid NameError if
    callers need to reference layer info. When layers is provided and has
    no domain layer, it reinforces the single-file classification.
    """
    biz_files = [f for f in py_files if not is_ops_script(f)
                 and '/tests/' not in f and '\\tests\\' not in f
                 and not os.path.basename(f).startswith('test_')
                 and not os.path.basename(f).endswith('_test.py')]
    biz_file_count = len(biz_files)

    score = 0.0
    features = []
    if biz_file_count <= 20:
        score += 0.2
    if biz_file_count <= 10:
        score += 0.15
    if total_lines < 8000:
        score += 0.15
    if total_lines < 5000:
        score += 0.1

    # Main entry file dominance
    base = backend_path or project_path or ""
    main_entry = ""
    for candidate in ("main.py", "app.py"):
        p = os.path.join(base, candidate)
        if os.path.isfile(p):
            main_entry = p
            break
    if main_entry:
        try:
            with open(main_entry, 'r', encoding='utf-8', errors='ignore') as fh:
                main_lines = len(fh.read().split('\n'))
            if total_lines > 0 and main_lines / total_lines > 0.2:
                score += 0.2
                features.append(f"主入口文件占代码量的{main_lines/total_lines:.0%}")
        except Exception as e:  # noqa: broad exception handling
            pass

    if detected_framework in ('fastapi', 'flask') and layer_count <= 2:
        score += 0.25
        features.append(f"{detected_framework}轻量服务特征")
    if layer_count < 3:
        score += 0.1

    return min(score, 1.0), features


def _score_script_architecture(py_files, total_lines, detected_framework):
    """Score pure-script architecture."""
    score = 0.0
    no_web = not detected_framework
    no_route = not any(re.search(r'route|endpoint|api.*handler', f.lower()) for f in py_files)
    if no_web and no_route:
        score += 0.3
    if len(py_files) <= 5 and total_lines < 2000:
        score += 0.3
    if all(os.path.basename(f).startswith(('test_', 'patch_', 'migrate_', 'fix_')) for f in py_files):
        score += 0.4
    return min(score, 1.0)


def _score_single_file_script(py_files, detected_framework, backend_path, project_path):
    """Score single-file-script architecture (v21)."""
    non_ops = [f for f in py_files if not is_ops_script(f)
               and not os.path.basename(f).startswith('test_')
               and not os.path.basename(f).endswith('_test.py')
               and os.path.basename(f) != '__init__.py']
    score = 0.0
    features = []

    if len(non_ops) <= 3:
        score += 0.3
    if len(non_ops) <= 1:
        score += 0.2

    base_dir = backend_path or project_path or ""
    if base_dir and all(os.path.dirname(f) == base_dir.rstrip('/').rstrip('\\') for f in non_ops):
        score += 0.2
    if not detected_framework:
        score += 0.15

    # Script entry point
    has_script_entry = False
    for f in non_ops[:3]:
        try:
            with open(f, 'r', encoding='utf-8', errors='ignore') as fh:
                fc = fh.read()
            if re.search(r"if\s+__name__\s*==\s*['\"]__main__['\"]", fc):
                has_script_entry = True
                break
        except Exception as e:  # noqa: broad exception handling
            pass
    if has_script_entry:
        score += 0.15
        features.append("脚本入口模式(__main__)")

    req_path = os.path.join(backend_path or project_path or "", "requirements.txt")
    if not os.path.isfile(req_path):
        score += 0.1
    else:
        try:
            with open(req_path, 'r') as rf:
                req_lines = [l.strip() for l in rf.readlines() if l.strip() and not l.startswith('#')]
            if len(req_lines) <= 3:
                score += 0.1
        except Exception as e:  # noqa: broad exception handling
            pass

    return min(score, 1.0), features, len(non_ops)


def _score_nextjs_architecture(project_path, config):
    """Score Next.js web frontend architecture (v21)."""
    front_path = project_path or ""
    score = 0.0
    features = []
    if not front_path or not os.path.isdir(front_path):
        return 0.0, []

    pkg_json = os.path.join(front_path, "package.json")
    if os.path.isfile(pkg_json):
        try:
            with open(pkg_json, 'r', encoding='utf-8') as pf:
                pkg_content = pf.read()
            if '"next"' in pkg_content or "'next'" in pkg_content or 'next.js' in pkg_content.lower():
                score += 0.4
                features.append("Next.js依赖")
            if '"react"' in pkg_content or "'react'" in pkg_content:
                score += 0.1
        except Exception as e:  # noqa: broad exception handling
            pass

    # App/Pages router dirs
    for prefix in ("src/", ""):
        app_dir = os.path.join(front_path, prefix + "app")
        if os.path.isdir(app_dir):
            score += 0.25
            features.append("App Router目录")
            break
    for prefix in ("src/", ""):
        pages_dir = os.path.join(front_path, prefix + "pages")
        if os.path.isdir(pages_dir):
            score += 0.2
            features.append("Pages Router目录")
            break

    # next.config
    for nc in ("next.config.js", "next.config.ts", "next.config.mjs"):
        if os.path.isfile(os.path.join(front_path, nc)):
            score += 0.15
            features.append(f"{nc}配置文件")
            break

    # tsx/jsx files
    tsx_files = []
    for ext in (".tsx", ".jsx"):
        tsx_files.extend(find_files_frontend(front_path, ext,
                                              config.get("exclude_dirs", []),
                                              config.get("exclude_files", [])))
    if tsx_files:
        score += 0.1

    return min(score, 1.0), features


def detect_architecture_style(project_path: str, backend_path: str, config: dict) -> Dict[str, Any]:
    """
    识别项目的架构风格
    
    返回: {
        "style": str,           # 架构风格ID
        "style_name": str,      # 架构风格中文名
        "confidence": float,    # 置信度 0-1
        "features": list,       # 检测到的特征列表
        "layer_count": int,     # 检测到的架构层数
        "total_py_files": int,  # Python文件总数
        "total_code_lines": int,# 代码总行数
        "framework": str,       # 检测到的Web框架
        "ops_scripts": list,    # 检测到的运维脚本文件列表
        "is_ddd": bool,         # 是否为DDD架构
        "skip_ddd_checks": bool,# 是否跳过DDD相关检查
        "reason": str,          # 判定理由
    }
    """
    result = {
        "style": ARCH_STYLE_SINGLE_FILE,
        "style_name": ARCH_STYLE_NAMES[ARCH_STYLE_SINGLE_FILE],
        "confidence": 0.0,
        "features": [],
        "layer_count": 0,
        "total_py_files": 0,
        "total_code_lines": 0,
        "framework": "",
        "ops_scripts": [],
        "is_ddd": False,
        "skip_ddd_checks": True,
        "reason": "",
    }
    
    if not project_path and not backend_path:
        result["reason"] = "未指定项目路径，无法识别架构"
        return result
    
    # 收集所有Python文件
    search_paths = []
    if project_path and os.path.isdir(project_path):
        search_paths.append(project_path)
    if backend_path and backend_path != project_path and os.path.isdir(backend_path):
        search_paths.append(backend_path)
    
    exclude_dirs = set(config.get("exclude_dirs", []))
    exclude_files = config.get("exclude_files", [])
    py_files = _collect_py_files_for_arch(search_paths, exclude_dirs, exclude_files)
    
    result["total_py_files"] = len(py_files)
    
    if not py_files:
        result["style"] = ARCH_STYLE_PURE_SCRIPT
        result["style_name"] = ARCH_STYLE_NAMES[ARCH_STYLE_PURE_SCRIPT]
        result["confidence"] = 0.5
        result["reason"] = "未检测到Python代码文件"
        return result
    
    # 统计代码行数
    total_lines = _count_code_lines(py_files)
    result["total_code_lines"] = total_lines
    
    # 检测运维脚本
    ops_scripts = _detect_ops_scripts(py_files)
    result["ops_scripts"] = ops_scripts
    
    # 检测Web框架
    detected_framework, fw_features = _detect_framework(py_files, search_paths)
    result["framework"] = detected_framework
    result["features"].extend(fw_features)
    
    # 检测目录结构深度和分层
    layers = _detect_layers(py_files, search_paths)
    layer_count = sum(1 for v in layers.values() if v)
    result["layer_count"] = layer_count
    
    if layer_count >= 3:
        result["features"].append(f"检测到{layer_count}个架构层")
    
    # ===== 架构风格判定 =====
    
    # 评分系统：每种架构风格打一个分
    scores = defaultdict(float)
    
    # 1. DDD架构评分
    ddd_score, ddd_features = _score_ddd_architecture(layers, layer_count, py_files)
    result["features"].extend(ddd_features)
    scores[ARCH_STYLE_DDD] = ddd_score
    
    # 2. 三层MVC架构评分
    scores[ARCH_STYLE_THREE_TIER] = _score_mvc_architecture(py_files, layers, layer_count, detected_framework)
    
    # 3. 单文件轻量架构评分
    single_score, single_features = _score_single_file_architecture(
        py_files, total_lines, layer_count, detected_framework, backend_path, project_path, layers=layers)
    result["features"].extend(single_features)
    scores[ARCH_STYLE_SINGLE_FILE] = single_score
    
    # 4. 纯脚本项目评分
    scores[ARCH_STYLE_PURE_SCRIPT] = _score_script_architecture(py_files, total_lines, detected_framework)
    
    # 5. 单文件脚本工具评分（v21新增）
    sfs_score, sfs_features, sfs_non_ops_count = _score_single_file_script(
        py_files, detected_framework, backend_path, project_path)
    result["features"].extend(sfs_features)
    scores[ARCH_STYLE_SINGLE_FILE_SCRIPT] = sfs_score
    if sfs_score >= 0.6:
        result["features"].append(f"单文件脚本特征({sfs_non_ops_count}个业务文件)")

    # 6. Next.js Web前端项目评分（v21新增）
    nextjs_score, nextjs_features = _score_nextjs_architecture(project_path, config)
    result["features"].extend(nextjs_features)
    scores[ARCH_STYLE_NEXTJS_WEB] = nextjs_score
    
    # 7. 微服务架构评分（简化）
    micro_score = 0.0
    if len(py_files) > 50 and layer_count >= 2:
        if any('/services/' in f for f in py_files):
            micro_score += 0.5
    scores[ARCH_STYLE_MICROSERVICE] = min(micro_score, 1.0)
    
    # 取最高分作为判定结果
    best_style = max(scores, key=scores.get)
    best_score = scores[best_style]
    
    # 最低置信度阈值
    if best_score < 0.3:
        best_style = ARCH_STYLE_SINGLE_FILE  # 默认兜底
        best_score = 0.3
    
    result["style"] = best_style
    result["style_name"] = ARCH_STYLE_NAMES[best_style]
    result["confidence"] = round(best_score, 2)
    result["is_ddd"] = (best_style == ARCH_STYLE_DDD)
    result["skip_ddd_checks"] = (best_style != ARCH_STYLE_DDD)
    
    reason_parts = [
        f"Python文件{len(py_files)}个",
        f"代码约{total_lines}行",
        f"检测到{layer_count}层结构",
    ]
    if detected_framework:
        reason_parts.append(f"{detected_framework}框架")
    
    result["reason"] = f"{ARCH_STYLE_NAMES[best_style]}：" + "，".join(reason_parts)
    result["scores"] = {k: round(v, 2) for k, v in scores.items()}
    
    return result


def _match_dir_to_layers(d: str, dirname: str, parent_dir: str, layers: dict):
    """Match a directory to architecture layers based on keywords."""
    for layer, keywords in ARCH_LAYER_KEYWORDS.items():
        for kw in keywords:
            kw_parts = kw.split('/')
            if len(kw_parts) == 1:
                if dirname == kw_parts[0] and d not in layers[layer]:
                    layers[layer].append(d)
            else:
                if parent_dir == kw_parts[0] and dirname == kw_parts[1] and d not in layers[layer]:
                    layers[layer].append(d)


def _detect_layers(py_files: List[str], search_paths: List[str]) -> Dict[str, List[str]]:
    """检测项目的架构分层目录"""
    layers = {
        "domain": [],
        "application": [],
        "infrastructure": [],
        "presentation": [],
        "interface": [],
    }
    
    all_dirs = set()
    for f in py_files:
        d = os.path.dirname(f)
        while d and any(d.startswith(sp) for sp in search_paths):
            all_dirs.add(d)
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent
    
    for d in all_dirs:
        dirname = os.path.basename(d).lower()
        parent_dir = os.path.basename(os.path.dirname(d)).lower()
        _match_dir_to_layers(d, dirname, parent_dir, layers)
    
    return layers


def is_ops_script(file_path: str) -> bool:
    """判断文件是否为运维脚本（补丁、迁移、测试等）"""
    basename = os.path.basename(file_path)
    for pattern in OPS_SCRIPT_PATTERNS:
        if re.match(pattern, basename, re.IGNORECASE):
            return True
    return False


def get_non_ops_files(files: List[str]) -> List[str]:
    """过滤掉运维脚本文件"""
    return [f for f in files if not is_ops_script(f)]


# ===== 规则适用性判断 =====
def should_apply_ddd_rules(arch_info: Dict[str, Any]) -> bool:
    """是否应该应用DDD相关规则"""
    if arch_info.get("skip_ddd_checks", True):
        return False
    return arch_info.get("is_ddd", False)


def get_rule_strictness_level(arch_info: Dict[str, Any]) -> str:
    """
    根据架构风格返回规则严格度
    - strict: DDD架构，严格执行所有规则
    - normal: 三层MVC/微服务/Next.js Web，执行大部分规则
    - relaxed: 单文件轻量，宽松模式，跳过架构类检查
    - minimal: 纯脚本/单文件脚本项目，只做基础安全和代码质量检查
    """
    style = arch_info.get("style", "")
    if style == ARCH_STYLE_DDD:
        return "strict"
    elif style in (ARCH_STYLE_THREE_TIER, ARCH_STYLE_MICROSERVICE, ARCH_STYLE_NEXTJS_WEB):
        return "normal"
    elif style == ARCH_STYLE_SINGLE_FILE:
        return "relaxed"
    elif style in (ARCH_STYLE_PURE_SCRIPT, ARCH_STYLE_SINGLE_FILE_SCRIPT):
        return "minimal"
    else:
        return "relaxed"  # 默认宽松模式


def get_applicable_checks(arch_info: Dict[str, Any], all_checks: List[Tuple[str, str, callable]]) -> List[Tuple[str, str, callable]]:
    """
    根据架构风格返回适用的检查项列表
    
    all_checks: [(check_id, check_name, check_function), ...]
    """
    strictness = get_rule_strictness_level(arch_info)
    
    # 不同严格度下跳过的检查ID模式
    skip_patterns_by_strictness = {
        "minimal": [
            # 纯脚本：跳过所有架构、分层、领域相关检查
            r'^17\.\d+',  # 架构依赖方向检查
            r'^9\.[456]',  # 错误处理覆盖率、配置密钥分离等
            r'^13\.7',    # 日志质量（脚本不适用）
        ],
        "relaxed": [
            # 单文件轻量：跳过DDD相关、领域纯净度等
            r'^17\.[23456]',  # DDD依赖方向检查
        ],
        "normal": [
            # 三层MVC/微服务：跳过部分DDD特有的检查
            r'^17\.[46]',  # 领域层纯净度、架构独立性验证
        ],
        "strict": [],  # DDD架构：全部执行
    }
    
    skip_patterns = skip_patterns_by_strictness.get(strictness, [])
    
    applicable = []
    for check_id, check_name, check_func in all_checks:
        skip = False
        for pat in skip_patterns:
            if re.match(pat, check_id):
                skip = True
                break
        if not skip:
            applicable.append((check_id, check_name, check_func))
    
    return applicable


# ===================== 全局缓存 =====================
# 架构识别结果缓存（全局共享，避免每个模块重复检测）
_ARCH_INFO_CACHE = {}


def get_cached_arch_info(project_path, backend_path, config):
    """全局缓存的架构识别结果，按项目路径缓存
    
    对外公开版本（原_get_cached_arch_info的公开版），所有模块共享同一份检测结果
    """
    cache_key = f"{project_path}|{backend_path}"
    if cache_key in _ARCH_INFO_CACHE:
        return _ARCH_INFO_CACHE[cache_key]
    
    result = detect_architecture_style(project_path, backend_path, config)
    
    _ARCH_INFO_CACHE[cache_key] = result
    return result
