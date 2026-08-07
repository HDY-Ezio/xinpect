"""
煋鉴(Xinpect) 报告组件 - 头部组件
"""

from ._utils import _esc


def render_header(project_path, project_type, now_str, llm_badge, incremental_html):
    """渲染头部区域

    Args:
        project_path: 项目路径
        project_type: 项目类型
        now_str: 当前时间字符串
        llm_badge: LLM增强标识HTML
        incremental_html: 增量检查信息HTML

    Returns:
        头部HTML片段
    """
    return f'''
    <!-- 头部 -->
    <div class="header">
        <div class="header-brand">
            <span class="header-logo">🔍 煋鉴</span>
            <span class="header-subtitle">Xinpect · AI代码质检报告</span>
        </div>
        <div class="header-meta">
            <span>📁 {_esc(project_path or '未指定')}</span>
            <span>📋 类型: {_esc(project_type or '未检测')}</span>
            <span>🕐 {_esc(now_str)}</span>
        </div>
        {llm_badge}
        {incremental_html}
    </div>
    '''
