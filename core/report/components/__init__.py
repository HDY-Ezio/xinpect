"""
煋鉴(Xinpect) 报告组件库
所有独立的组件函数，每个组件输入数据输出HTML片段
"""

from ._utils import _esc, _esc_js, _get_score_color, _get_level_badge, _get_level_icon
from .header import render_header
from .score_card import render_scores, render_gauge_svg
from .stats_bar import render_stats
from .brain_nav import render_brain_section
from .issue_card import render_issue_card, render_issues_section, render_suggestions_section
from .passed_list import render_passed_section
from .fp_section import render_fp_section, render_llm_fp_section, render_ai_verified_badge
from .footer import render_footer

__all__ = [
    # utils
    '_esc',
    '_esc_js',
    '_get_score_color',
    '_get_level_badge',
    '_get_level_icon',
    # header
    'render_header',
    # score_card
    'render_scores',
    'render_gauge_svg',
    # stats_bar
    'render_stats',
    # brain_nav
    'render_brain_section',
    # issue_card
    'render_issue_card',
    'render_issues_section',
    'render_suggestions_section',
    # passed_list
    'render_passed_section',
    # fp_section
    'render_fp_section',
    'render_llm_fp_section',
    'render_ai_verified_badge',
    # footer
    'render_footer',
]
