"""
煋鉴(Xinpect) HTML报告模块
3S皮肤层架构：模板化 + 主题系统
- themes/      主题系统（CSS变量 + light/dark + JS交互）
- components/  组件模板（各独立渲染函数）
- templates/   页面模板（完整文档结构装配）
- html_generator.py  生成器（装配逻辑，对外接口）
"""

from .html_generator import generate_html_report, _RunnerAdapter, _module_to_brain
from .themes import BRAIN_NAMES

__all__ = [
    'generate_html_report',
    '_RunnerAdapter',
    '_module_to_brain',
    'BRAIN_NAMES',
]
