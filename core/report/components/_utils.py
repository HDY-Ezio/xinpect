"""
煋鉴(Xinpect) 报告组件 - 工具函数
HTML转义、分数颜色、级别图标等辅助函数
"""

import html as html_module


def _esc(text: str) -> str:
    """HTML转义"""
    return html_module.escape(str(text)) if text else ''


def _esc_js(text: str) -> str:
    """转义用于JS字符串属性的文本"""
    if not text:
        return ''
    return (str(text)
            .replace('&', '&amp;')
            .replace('"', '&quot;')
            .replace("'", '&#39;')
            .replace('<', '&lt;')
            .replace('>', '&gt;'))


def _get_score_color(score: int) -> str:
    """根据分数返回颜色"""
    if score >= 80:
        return '#22c55e'
    elif score >= 60:
        return '#eab308'
    elif score >= 40:
        return '#f97316'
    else:
        return '#ef4444'


def _get_level_badge(level: str) -> str:
    mapping = {
        'blocking': ('#DC3545', '🚫 阻断'),
        'problem': ('#f59e0b', '🟡 警告'),
        'suggestion': ('#3b82f6', '💡 建议'),
        # 兼容旧级别
        'error': ('#DC3545', '🚫 阻断'),
        'warning': ('#f59e0b', '🟡 警告'),
        'info': ('#3b82f6', '💡 建议'),
    }
    bg, label = mapping.get(level, ('#6b7280', '信息'))
    return f'<span style="display:inline-block;padding:2px 10px;border-radius:12px;font-size:12px;font-weight:600;background:{bg};color:#fff;">{label}</span>'


def _get_level_icon(level: str) -> str:
    icons = {
        'blocking': '🚫', 'problem': '🟡', 'suggestion': '💡',
        # 兼容旧级别
        'error': '🚫', 'warning': '🟡', 'info': '💡',
    }
    return icons.get(level, '⚪')
