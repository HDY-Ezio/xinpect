#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
项目画像与成熟度检测 (迁移自 qa_framework.py)
================================================
包含：
- ProjectProfile: 项目画像数据类
- _build_project_profile: 构建项目画像
- _detect_project_maturity: 检测项目成熟度阶段
- _estimate_main_package_size / _estimate_total_package_size: 包大小估算
"""

import os
import re
import json
import sys

# 确保技能根目录在 sys.path 中
_SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SKILL_ROOT not in sys.path:
    sys.path.insert(0, _SKILL_ROOT)

from core.utils import safe_read, find_files


class ProjectProfile:
    """项目画像：包含项目规模、复杂度、技术栈等信息，供规则自适应调用"""
    def __init__(self):
        # 规模指标
        self.main_package_size_mb = 0.0
        self.total_package_size_mb = 0.0
        self.total_code_lines = 0
        self.page_count = 0
        self.component_count = 0
        self.subpackage_count = 0
        self.js_file_count = 0
        self.py_file_count = 0
        
        # 规模等级: tiny / small / medium / large / xlarge
        self.scale_level = "small"
        
        # 平台类型: miniprogram / h5 / mp(通用小程序) / backend / mixed
        self.platform = "unknown"
        # 平台特性矩阵
        self.platform_features = {
            "has_hover": True,           # 是否有hover交互（触屏无hover）
            "emoji_as_icon": "unusual",  # emoji做图标: normal / unusual
            "webview_business": False,   # web-view是否为业务组件
        }
        # 技术栈特征
        self.has_typescript = False
        self.has_vue = False
        self.has_react = False
        self.has_flask = False
        
        # P3新增: 项目成熟度阶段
        # early: 早期项目（代码量小、注释多、功能不完整）→ 放宽标准
        # migration: 迁移项目（大量历史代码、风格不统一）→ 复杂度/重复代码放宽
        # mature: 成熟项目（标准严格）
        self.maturity_stage = "mature"  # early / migration / mature
        self.maturity_confidence = 0.0  # 判定置信度 0-1
        self.todo_density = 0.0  # TODO密度（每千行）
        self.comment_ratio = 0.0  # 注释比例
        self.stub_function_ratio = 0.0  # 占位函数比例
        self.has_git_history = False  # 是否有git提交历史
        self.git_commit_count = 0  # git提交次数
    
    def is_small_project(self) -> bool:
        """判断是否为小型项目（<10个页面或<5000行）"""
        return (self.page_count > 0 and self.page_count < 10) or \
               (self.total_code_lines > 0 and self.total_code_lines < 5000)
    
    def is_early_project(self) -> bool:
        """P3: 判断是否为早期项目（放宽代码质量标准）"""
        return self.maturity_stage == "early"
    
    def is_migration_project(self) -> bool:
        """P3: 判断是否为迁移项目（放宽复杂度/重复代码标准）"""
        return self.maturity_stage == "migration"
    
    def should_relax_quality_rules(self) -> bool:
        """P3: 是否应该放宽代码质量标准（早期或迁移项目）"""
        return self.maturity_stage in ("early", "migration")
    
    def get_adjusted_threshold(self, rule_name, default_value):
        """P3: 根据项目阶段获取调整后的阈值"""
        if self.maturity_stage == "mature":
            return default_value
        
        # 早期/迁移项目的阈值调整
        adjustments = {
            "function_lines": 1.5,      # 6.2 函数过长: 80→120
            "cyclomatic_complexity": 1.67,  # 9.3 圈复杂度: 15→25
            "duplicate_similarity": 1.125,  # 6.1 重复代码相似度: 80%→90%
            "hardcoded_color_density": 2.0,  # 5.8 硬编码色值密度: 翻倍
        }
        
        if rule_name in adjustments:
            return int(default_value * adjustments[rule_name])
        return default_value
    
    def to_dict(self):
        return {
            "main_package_size_mb": self.main_package_size_mb,
            "total_package_size_mb": self.total_package_size_mb,
            "total_code_lines": self.total_code_lines,
            "page_count": self.page_count,
            "component_count": self.component_count,
            "subpackage_count": self.subpackage_count,
            "scale_level": self.scale_level,
            "platform": self.platform,
            "platform_features": self.platform_features,
            "is_small_project": self.is_small_project(),
            # P3新增: 项目成熟度
            "maturity_stage": self.maturity_stage,
            "maturity_confidence": self.maturity_confidence,
            "todo_density": self.todo_density,
            "comment_ratio": self.comment_ratio,
            "is_early_project": self.is_early_project(),
            "should_relax_quality_rules": self.should_relax_quality_rules(),
        }


def _detect_project_maturity(profile, project_path, backend_path, config):
    """
    P3升级: 检测项目成熟度阶段
    判断维度：
    1. TODO/FIXME数量密度
    2. 代码提交历史（如果有.git）
    3. 注释比例
    4. stub/占位函数比例
    5. 文件更新时间分布
    
    设置: profile.maturity_stage = "early" / "migration" / "mature"
    """
    exclude_dirs = config.get("exclude_dirs", [])
    exclude_files = config.get("exclude_files", [])
    
    todo_count = 0
    comment_lines = 0
    total_lines = 0
    stub_count = 0
    total_funcs = 0
    
    # 扫描前端代码
    all_code_files = []
    if project_path and os.path.isdir(project_path):
        code_exts = [".js", ".ts", ".tsx", ".jsx", ".wxml", ".wxss"]
        all_code_files += find_files(project_path, code_exts, exclude_dirs, exclude_files)
    
    # 扫描后端代码
    if backend_path and os.path.isdir(backend_path):
        all_code_files += find_files(backend_path, [".py"], exclude_dirs, exclude_files)
    
    for f in all_code_files:
        try:
            with open(f, 'r', encoding='utf-8', errors='ignore') as fh:
                lines = fh.readlines()
                total_lines += len(lines)
                
                for line in lines:
                    stripped = line.strip()
                    # 统计注释
                    if stripped.startswith(('//', '#', '/*', '*')):
                        comment_lines += 1
                    # 统计TODO/FIXME
                    if re.search(r'\b(TODO|FIXME|HACK|XXX|BODGE)\b', line, re.IGNORECASE):
                        if stripped.startswith(('//', '#', '/*', '*')):
                            todo_count += 1
                    
                    # 统计占位函数（只有pass/return None/空函数体）
                    if re.match(r'^def \w+\s*\(', stripped):
                        total_funcs += 1
        except Exception:
            pass  # 文件分析异常不影响主流程
    
    # 计算指标
    if total_lines > 0:
        profile.todo_density = (todo_count / total_lines) * 1000  # 每千行TODO数
        profile.comment_ratio = comment_lines / total_lines
    
    # 检测git历史
    git_dir = None
    if project_path and os.path.isdir(os.path.join(project_path, '.git')):
        git_dir = os.path.join(project_path, '.git')
    elif backend_path and os.path.isdir(os.path.join(backend_path, '.git')):
        git_dir = os.path.join(backend_path, '.git')
    
    if git_dir:
        profile.has_git_history = True
        # 简单估计：检查git对象数量
        try:
            git_objs_dir = os.path.join(git_dir, 'objects')
            if os.path.isdir(git_objs_dir):
                obj_count = sum(1 for root, dirs, files in os.walk(git_objs_dir) for _ in files)
                profile.git_commit_count = min(obj_count // 10, 1000)  # 粗略估计
        except Exception:
            pass  # git对象计数仅为估算，异常时保持默认值
    
    # 综合判定
    early_score = 0  # 越高越可能是早期项目
    max_score = 5
    
    # 维度1: TODO密度（每千行>5个=早期）
    if profile.todo_density > 5:
        early_score += 2
    elif profile.todo_density > 2:
        early_score += 1
    
    # 维度2: 注释比例高（>20%可能是早期项目在写文档）
    if profile.comment_ratio > 0.25:
        early_score += 1
    
    # 维度3: 代码量小且git提交少
    if profile.total_code_lines < 3000 and profile.git_commit_count < 20:
        early_score += 2
    elif profile.total_code_lines < 8000 and profile.git_commit_count < 50:
        early_score += 1
    
    # 维度4: 小项目可能是早期
    if profile.is_small_project():
        early_score += 1
    
    # 迁移项目检测：有大量历史代码特征
    migration_score = 0
    
    # 判定阶段
    if early_score >= 3 and profile.total_code_lines < 10000:
        profile.maturity_stage = "early"
        profile.maturity_confidence = min(early_score / max_score, 1.0)
    elif migration_score >= 2:
        profile.maturity_stage = "migration"
        profile.maturity_confidence = min(migration_score / 3, 1.0)
    else:
        profile.maturity_stage = "mature"
        profile.maturity_confidence = 0.8


def _build_project_profile(project_path, backend_path, config, project_type="unknown"):
    """
    构建项目画像：计算项目规模指标，供所有规则自适应调用
    这是P0重构的核心基础设施
    """
    profile = ProjectProfile()
    
    exclude_dirs = config.get("exclude_dirs", [])
    exclude_files = config.get("exclude_files", [])
    
    # ===== 前端项目指标 =====
    if project_path and os.path.isdir(project_path):
        # 小程序项目：解析app.json获取页面数和分包数
        app_json_path = os.path.join(project_path, "app.json")
        if os.path.isfile(app_json_path):
            try:
                aj = json.loads(safe_read(app_json_path))
                pages = aj.get("pages", [])
                profile.page_count = len(pages)
                
                subpackages = aj.get("subpackages", [])
                profile.subpackage_count = len(subpackages)
                
                for sp in subpackages:
                    sp_pages = sp.get("pages", [])
                    profile.page_count += len(sp_pages)
            except Exception:
                pass  # 小程序配置解析失败不影响其他指标
        
        # 统计代码行数（非空行）
        code_exts = [".js", ".ts", ".wxml", ".wxss", ".json", ".tsx", ".jsx", ".css", ".scss"]
        all_code_files = find_files(project_path, code_exts, exclude_dirs, exclude_files)
        for cf in all_code_files:
            try:
                with open(cf, 'r', encoding='utf-8', errors='ignore') as f:
                    profile.total_code_lines += sum(1 for line in f if line.strip())
            except Exception:
                pass  # 单文件读取失败不影响总行数统计
        
        # JS/TS文件数量
        profile.js_file_count = len(find_files(project_path, [".js", ".ts", ".tsx", ".jsx"], exclude_dirs, exclude_files))
        
        # 组件目录统计
        components_dir = os.path.join(project_path, "components")
        if os.path.isdir(components_dir):
            try:
                comp_dirs = [d for d in os.listdir(components_dir) 
                            if os.path.isdir(os.path.join(components_dir, d))]
                profile.component_count = len(comp_dirs)
            except Exception:
                pass  # 组件目录扫描失败不影响整体画像
        
        # 技术栈检测
        ts_files = find_files(project_path, [".ts", ".tsx"], exclude_dirs, exclude_files)
        profile.has_typescript = len(ts_files) > 0
        
        # 估算主包大小（小程序）
        if project_type in ("miniprogram", "mixed"):
            profile.main_package_size_mb = _estimate_main_package_size(project_path, config)
            profile.total_package_size_mb = _estimate_total_package_size(project_path, config)
    
    # ===== 后端项目指标 =====
    if backend_path:
        bp = backend_path if os.path.isdir(backend_path) else os.path.dirname(backend_path)
        if os.path.isdir(bp):
            py_files = find_files(bp, [".py"], exclude_dirs, exclude_files)
            profile.py_file_count = len(py_files)
            for pf in py_files:
                try:
                    with open(pf, 'r', encoding='utf-8', errors='ignore') as f:
                        profile.total_code_lines += sum(1 for line in f if line.strip())
                except Exception:
                    pass  # Intentionally empty: non-critical validation
            
            # Flask检测
            for pf in py_files[:5]:
                pf_content = safe_read(pf)
                if re.search(r'from\s+flask|import\s+flask|Flask\s*\(', pf_content):
                    profile.has_flask = True
                    break
    
    # ===== 规模等级判定 =====
    total_lines = profile.total_code_lines
    if total_lines < 1000:
        profile.scale_level = "tiny"
    elif total_lines < 5000:
        profile.scale_level = "small"
    elif total_lines < 20000:
        profile.scale_level = "medium"
    elif total_lines < 50000:
        profile.scale_level = "large"
    else:
        profile.scale_level = "xlarge"
    
    # ===== 平台类型检测（P2升级） =====
    has_app_json = os.path.isfile(os.path.join(project_path, "app.json")) if project_path else False
    has_project_config = os.path.isfile(os.path.join(project_path, "project.config.json")) if project_path else False
    has_wxml = len(find_files(project_path, [".wxml"], exclude_dirs, exclude_files)) > 0 if project_path else False
    has_wxss = len(find_files(project_path, [".wxss"], exclude_dirs, exclude_files)) > 0 if project_path else False
    has_html = len(find_files(project_path, [".html"], exclude_dirs, exclude_files)) > 0 if project_path else False
    has_css = len(find_files(project_path, [".css"], exclude_dirs, exclude_files)) > 0 if project_path else False
    has_dom_ops = False
    if project_path:
        js_files_for_platform = find_files(project_path, [".js", ".ts"], exclude_dirs, exclude_files)
        for jf in js_files_for_platform[:10]:
            jc = safe_read(jf)
            if re.search(r'document\.|window\.|getElementById|querySelector', jc):
                has_dom_ops = True
                break
    
    has_backend_only = (not project_path or not os.path.isdir(project_path)) and backend_path
    has_frontend_only = project_path and os.path.isdir(project_path) and not backend_path
    
    if has_app_json and has_project_config and has_wxml:
        # 微信小程序
        profile.platform = "miniprogram"
        profile.platform_features = {
            "has_hover": False,
            "emoji_as_icon": "normal",
            "webview_business": True,
        }
    elif has_wxml and has_wxss and not has_app_json:
        # 通用小程序
        profile.platform = "mp"
        profile.platform_features = {
            "has_hover": False,
            "emoji_as_icon": "normal",
            "webview_business": True,
        }
    elif has_html and (has_css or has_dom_ops):
        # H5/Web前端
        profile.platform = "h5"
        profile.platform_features = {
            "has_hover": True,
            "emoji_as_icon": "unusual",
            "webview_business": False,
        }
    elif has_backend_only and not has_frontend_only:
        # 纯后端项目
        profile.platform = "backend"
        profile.platform_features = {
            "has_hover": False,
            "emoji_as_icon": "unusual",
            "webview_business": False,
        }
    elif has_app_json and backend_path:
        # 混合项目（小程序+后端）
        profile.platform = "miniprogram"
        profile.platform_features = {
            "has_hover": False,
            "emoji_as_icon": "normal",
            "webview_business": True,
        }
    elif has_html and backend_path:
        # 混合项目（H5+后端）
        profile.platform = "h5"
        profile.platform_features = {
            "has_hover": True,
            "emoji_as_icon": "unusual",
            "webview_business": False,
        }
    else:
        profile.platform = "unknown"
    
    # 页面数交叉验证
    if profile.page_count > 0:
        if profile.page_count < 10 and profile.scale_level in ("medium", "large", "xlarge"):
            # 代码多但页面少，可能是工具类多，保留原等级
            pass
        elif profile.page_count > 50 and profile.scale_level in ("tiny", "small"):
            profile.scale_level = "medium"
    

    # ===== P3升级: 项目成熟度检测 =====
    _detect_project_maturity(profile, project_path, backend_path, config)

    return profile


def _estimate_main_package_size(project_path, config):
    """估算小程序主包大小（MB）"""
    try:
        total_size = 0
        app_json_path = os.path.join(project_path, "app.json")
        subpkg_roots = set()
        if os.path.isfile(app_json_path):
            try:
                aj = json.loads(safe_read(app_json_path))
                for sp in aj.get("subpackages", []):
                    root = sp.get("root", "")
                    if root:
                        subpkg_roots.add(root.rstrip("/"))
            except Exception:
                pass  # Intentionally empty: non-critical validation
        
        for item in os.listdir(project_path):
            item_path = os.path.join(project_path, item)
            if item in subpkg_roots:
                continue
            if item in config.get("exclude_dirs", []):
                continue
            if os.path.isdir(item_path):
                for root, dirs, files in os.walk(item_path):
                    dirs[:] = [d for d in dirs if d not in config.get("exclude_dirs", [])]
                    for fn in files:
                        fp = os.path.join(root, fn)
                        try:
                            total_size += os.path.getsize(fp)
                        except Exception:
                            pass  # Intentionally empty: non-critical validation
            elif os.path.isfile(item_path):
                try:
                    total_size += os.path.getsize(item_path)
                except Exception:
                    pass  # Intentionally empty: non-critical validation
        
        return round(total_size / (1024 * 1024), 2)
    except Exception:
        return 0.0


def _estimate_total_package_size(project_path, config):
    """估算小程序总包大小（MB）"""
    try:
        total_size = 0
        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in config.get("exclude_dirs", [])]
            for fn in files:
                fp = os.path.join(root, fn)
                try:
                    total_size += os.path.getsize(fp)
                except Exception:
                    pass  # Intentionally empty: non-critical validation
        return round(total_size / (1024 * 1024), 2)
    except Exception:
        return 0.0
