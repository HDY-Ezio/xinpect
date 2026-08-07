#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI增强模块 — 兼容入口
实际实现已迁移到 core.ai_enhancer 包（按3S骨架拆分）：
- core.ai_enhancer.prompts     - Prompt模板库
- core.ai_enhancer.strategies  - 4种增强策略实现
- core.ai_enhancer.engine      - 核心引擎（AIEnhancer类）

本文件保持向后兼容，所有公开符号从 core.ai_enhancer 转发
"""

# 向后兼容：从 core.ai_enhancer 包转发
from core.ai_enhancer import AIEnhancer, should_enable_ai

__all__ = ['AIEnhancer', 'should_enable_ai']
