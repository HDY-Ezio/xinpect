# -*- coding: utf-8 -*-
"""
规则数据模型
"""

import os
from typing import List


class Rule:
    """规则定义类"""
    
    def __init__(
        self,
        rule_id: str,
        name: str,
        level: str,  # blocking / problem / suggestion
        category: str,
        description: str,
        check_func: callable,
        applicable_types: list = None,
        module_id: str = "",
        is_json_rule: bool = False,
        execution_status: str = "executable",
        source_dir: str = "",  # v4.2: 规则来源目录（用于规则裁剪）
        file_pattern: str = "",  # v4.2: JSON规则文件名模式（用于批量执行预过滤）
    ):
        self.id = rule_id
        self.name = name
        self.level = level  # 对应原有 error / warning / info
        self.category = category  # bug / code_smell / engineering_maturity
        self.description = description
        self.check_func = check_func
        self.applicable_types = applicable_types or []  # 空列表表示所有类型适用
        self.module_id = module_id
        self.is_json_rule = is_json_rule
        self.execution_status = execution_status  # "executable" 或 "reference"
        self.file_pattern = file_pattern or "*"  # JSON规则的文件名模式，用于批量执行时预过滤
        self.source_dir = source_dir  # v4.2: 规则来源目录名（rules/ 下的一级目录）
    
    def is_applicable(self, project_type: str, context=None) -> bool:
        """检查规则是否适用于当前项目类型
        
        v3.5.1: 二次校验 - 如果 project_type 是 "mixed"，但实际没有找到任何前端框架文件
        （.wxml/.vue/.tsx/.jsx），则小程序/UI 相关规则不应触发。
        """
        if not self.applicable_types:
            return True
        
        if project_type not in self.applicable_types:
            return False
        
        # 二次校验：如果规则要求 mixed 类型，但项目实际没有前端文件，跳过
        if project_type == "mixed" and context is not None:
            # 检查项目是否真的有前端框架文件
            frontend_exts = [".wxml", ".vue", ".tsx", ".jsx"]
            has_frontend = any(context.find_files([ext]) for ext in frontend_exts)
            if not has_frontend:
                return False
        
        return True
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "level": self.level,
            "category": self.category,
            "description": self.description,
            "module_id": self.module_id,
            "is_json_rule": self.is_json_rule,
            "file_pattern": self.file_pattern,
            "execution_status": self.execution_status,
            "source_dir": self.source_dir,  # v4.2
        }


class RuleCheckResult:
    """规则检查结果项"""
    
    def __init__(
        self,
        rule_id: str,
        rule_name: str,
        level: str,  # error / warning / info
        message: str,
        detail: str = "",
        fix: str = "",
        location: dict = None,
        category: str = "",
        status: str = "active",  # active / fp(误报) / suppressed
        fp_reason: str = "",  # 误报原因
        suggestion_code: str = "",  # v3.5: 代码示例修复建议
    ):
        self.rule_id = rule_id
        self.rule_name = rule_name
        self.level = level
        self.message = message
        self.detail = detail
        self.fix = fix
        self.location = location or {}
        self.category = category
        self.status = status  # active: 有效问题; fp: 误报(已过滤); suppressed: 手动抑制
        self.fp_reason = fp_reason  # 误报过滤原因
        self.suggestion_code = suggestion_code  # v3.5: 代码示例修复建议
    
    @property
    def check_id(self):
        """兼容旧版属性名"""
        return self.rule_id
    
    @property
    def name(self):
        """兼容旧版属性名"""
        return self.rule_name
    
    def to_dict(self) -> dict:
        return {
            "id": self.rule_id,
            "name": self.rule_name,
            "level": self.level,
            "message": self.message,
            "detail": self.detail,
            "fix": self.fix,
            "category": self.category,
            "location": self.location,
            "status": self.status,
            "fp_reason": self.fp_reason,
            "suggestion_code": self.suggestion_code,
        }
