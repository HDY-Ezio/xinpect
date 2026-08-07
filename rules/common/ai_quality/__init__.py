"""
智能质检模块 (v3.2.0新增，内部代码名: ai_code_check)
AI增强的代码质量检测——专抓传统Linter漏过的问题

定位：不替代现有规则，作为独立模块附加
一句话卖点："AI时代的代码质检——专抓传统Linter漏过的问题"

包含13条规则：
- P0 安全红线 (5条): AI-SEC-01 ~ AI-SEC-05
- P0 特有问题检测 (4条): AI-SPEC-01 ~ AI-SPEC-04
- P1 质量问题 (4条): AI-QUAL-01 ~ AI-QUAL-04

配套 代码质量评分系统
"""

__version__ = "3.2.0"
__all__ = ["security_rules", "ai_specific_rules", "quality_rules", "vibe_score"]
