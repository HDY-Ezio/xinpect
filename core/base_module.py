#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基础模块类 (迁移自 qa_framework.py BaseModule)
================================================
所有QA检查模块的基类，定义统一的 run() 接口和公共属性。
"""

from __future__ import annotations

import os
import sys
from typing import List, Dict, Optional, Any

# 确保技能根目录在 sys.path 中
_SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SKILL_ROOT not in sys.path:
    sys.path.insert(0, _SKILL_ROOT)

# 延迟导入 CheckResult（避免循环依赖）
# CheckResult 定义在 core/report_generator.py，而 report_generator 
# 可能间接依赖 base_module（通过模块类）
# 实际在运行时才需要 CheckResult，所以用 TYPE_CHECKING 模式
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from core.report_generator import CheckResult
    from core.project_profiler import ProjectProfile

# 运行时导入 ProjectProfile（__init__ 中使用）
from core.project_profiler import ProjectProfile  # noqa: E402


class BaseModule:
    module_id: str = ""
    module_name: str = ""

    def __init__(self, project_path: str, backend_path: str, config: dict, project_type: str = "unknown", project_profile: "ProjectProfile" = None, arch_info: dict = None):
        self.project_path = project_path
        self.backend_path = backend_path
        self.config = config
        self.project_type = project_type
        self.results: List[CheckResult] = []
        # P0重构: 项目画像（供所有规则自适应调用）
        self.project_profile = project_profile or ProjectProfile()
        # P1根因修复: 架构信息（懒加载，供架构识别层调用）
        self._arch_info = arch_info  # 可直接传入，避免重复检测

    def add(self, check_id: str, name: str, level: str, message: str, detail: str = "", fix: str = "", location: dict = None):
        # 延迟导入CheckResult（避免循环依赖：report_generator可能间接依赖base_module）
        from core.report_generator import CheckResult
        self.results.append(CheckResult(check_id, name, level, message, detail, fix, location))

    def is_web_frontend(self) -> bool:
        """判断项目是否为Web前端（非小程序），结果缓存"""
        if hasattr(self, '_cached_is_web'):
            return self._cached_is_web
        if self.project_type in ("web", "electron"):
            self._cached_is_web = True
            return True
        if self.project_type in ("mixed", "mixed_electron"):
            has_wxml = bool(find_files(self.project_path or "", [".wxml"],
                                       self.config["exclude_dirs"], self.config["exclude_files"]))
            has_tsx = bool(find_files(self.project_path or "", [".tsx", ".jsx"],
                                       self.config["exclude_dirs"], self.config["exclude_files"]))
            self._cached_is_web = has_tsx and not has_wxml
            return self._cached_is_web
        self._cached_is_web = False
        return False

    def is_electron(self) -> bool:
        """判断项目是否为Electron桌面端"""
        return self.project_type in ("electron", "mixed_electron")

    def get_arch_info(self) -> dict:
        """P1根因修复: 获取架构识别信息（懒加载+全局缓存，所有模块共享同一份检测结果）
        返回架构风格、层数、是否跳过DDD检查等信息
        """
        if self._arch_info is not None:
            return self._arch_info
        
        # 使用全局缓存，避免每个模块重复检测
        from core.architecture_detector import get_cached_arch_info
        self._arch_info = get_cached_arch_info(
            self.project_path, self.backend_path, self.config
        )
        return self._arch_info

    def should_skip_ddd_checks(self) -> bool:
        """P1根因修复: 是否应该跳过DDD相关检查"""
        arch_info = self.get_arch_info()
        return arch_info.get("skip_ddd_checks", True)

    def get_ops_scripts(self) -> list:
        """P1根因修复: 获取运维脚本文件列表"""
        arch_info = self.get_arch_info()
        return arch_info.get("ops_scripts", [])

    def should_skip(self, check_id: str) -> tuple:
        """检查某个具体检查项是否应该跳过（基于项目类型）
        返回: (是否跳过, 跳过原因)"""
        # 从实例或类获取CHECK_SKIP配置（兼容旧框架和新框架）
        check_skip = getattr(self, 'CHECK_SKIP', None)
        if check_skip is None:
            check_skip = getattr(type(self), 'CHECK_SKIP', {})
        if not check_skip:
            # 最后尝试从qa_framework全局获取（向后兼容）
            try:
                import qa_framework
                check_skip = getattr(qa_framework, 'CHECK_SKIP', {})
            except ImportError:
                check_skip = {}
        skip_map = check_skip.get(self.project_type, {})
        module_id = check_id.split(".")[0]
        skip_items = skip_map.get(module_id, {})
        if check_id in skip_items:
            return True, skip_items[check_id]
        return False, ""

    def add_skip(self, check_id: str, name: str, reason: str = ""):
        """添加跳过结果"""
        self.add(check_id, name, "info", f"不适用({self.project_type})，跳过" + (f"：{reason}" if reason else ""))


    def _make_location(self, file_path, line=0, column=0, snippet=""):
        """
        P1升级: 构建标准化的location数据结构
        - 统一使用相对项目根目录的路径
        - 行号边界校验
        - 自动提取代码片段
        """
        if not file_path:
            return {"file": "", "line": 0, "column": 0, "snippet": ""}
        
        # 确保是相对路径
        rel_path = file_path
        if os.path.isabs(rel_path) and self.project_path and rel_path.startswith(self.project_path):
            rel_path = os.path.relpath(rel_path, self.project_path)
        elif rel_path.startswith("../") or rel_path.startswith("./"):
            rel_path = os.path.normpath(rel_path)
            if rel_path.startswith("../") and self.project_path:
                # 尝试规范化
                abs_path = os.path.abspath(os.path.join(self.project_path, rel_path))
                if abs_path.startswith(self.project_path):
                    rel_path = os.path.relpath(abs_path, self.project_path)
        
        # 行号边界校验
        line_num = line if isinstance(line, int) else 0
        if line_num > 0 and self.project_path:
            full_path = os.path.join(self.project_path, rel_path)
            if os.path.isfile(full_path):
                try:
                    with open(full_path, 'r', encoding='utf-8') as f:
                        file_lines = f.readlines()
                    if line_num > len(file_lines):
                        line_num = len(file_lines)
                    if not snippet and line_num > 0:
                        snippet = file_lines[line_num - 1].strip()
                except (OSError, UnicodeDecodeError, ValueError):
                    pass  # Intentionally empty: non-critical validation
        
        return {
            "file": rel_path,
            "line": line_num,
            "column": column if isinstance(column, int) else 0,
            "snippet": snippet,
        }
    
    def add_with_location(self, check_id, name, level, message, detail="", fix="", 
                          file="", line=0, column=0, snippet=""):
        """P1升级: 带定位信息的问题上报（自动规范化location）"""
        location = self._make_location(file, line, column, snippet)
        return self.add(check_id, name, level, message, detail, fix, location=location)

    def run(self) -> List[CheckResult]:
        raise NotImplementedError
