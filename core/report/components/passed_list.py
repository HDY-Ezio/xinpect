"""
煋鉴(Xinpect) 报告组件 - 通过项列表组件
展示已通过的检查项
"""

from ._utils import _esc


def render_passed_section(passed_items, passed_html):
    """渲染已通过检查项区域

    Args:
        passed_items: 通过项列表（用于计数）
        passed_html: 通过项HTML集合

    Returns:
        通过项区域HTML片段（若无通过项则返回空字符串）
    """
    if not passed_items:
        return ''
    return f'''
    <!-- 通过项 -->
    <div class="passed-section">
        <details>
            <summary>✅ 已通过检查项 ({len(passed_items)}项) — 点击展开</summary>
            <div class="passed-grid">{passed_html}</div>
        </details>
    </div>
    '''
