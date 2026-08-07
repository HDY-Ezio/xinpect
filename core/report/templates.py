"""
煋鉴(Xinpect) HTML模板 - 向后兼容层
已迁移至 components/ + templates/ 包，此处仅做转发。
"""

from .components import (
    _esc,
    _esc_js,
    _get_score_color,
    _get_level_badge,
    _get_level_icon,
    render_gauge_svg,
    render_issue_card,
    render_header,
    render_scores,
    render_stats,
    render_brain_section,
    render_issues_section,
    render_suggestions_section,
    render_passed_section,
    render_fp_section,
    render_llm_fp_section,
    render_ai_verified_badge,
    render_footer,
)
from .page_templates import build_full_html

# 兼容旧命名
_gauge_svg = render_gauge_svg
_issue_card = render_issue_card

__all__ = [
    '_esc',
    '_esc_js',
    '_get_score_color',
    '_get_level_badge',
    '_get_level_icon',
    'render_gauge_svg',
    'render_issue_card',
    'render_header',
    'render_scores',
    'render_stats',
    'render_brain_section',
    'render_issues_section',
    'render_suggestions_section',
    'render_passed_section',
    'render_fp_section',
    'render_llm_fp_section',
    'render_ai_verified_badge',
    'render_footer',
    'build_full_html',
    '_gauge_svg',
    '_issue_card',
]
