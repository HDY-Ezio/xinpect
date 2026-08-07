"""
煋鉴(Xinpect) 页面模板
full_report：完整报告模板
mini_report：精简报告模板
"""

from .full_report import build_full_html
from .mini_report import build_mini_html

__all__ = [
    'build_full_html',
    'build_mini_html',
]
