"""
煋鉴(Xinpect) 报告组件 - 误报区组件
展示已过滤的误报、LLM确认非问题、AI二次校验标记
"""

from ._utils import _esc


def render_fp_section(fp_count, fp_html, fp_results):
    """渲染已过滤误报区域

    Args:
        fp_count: 误报数量
        fp_html: 误报列表HTML
        fp_results: 误报结果列表（用于判断是否展示）

    Returns:
        误报区域HTML片段（若无误报则返回空字符串）
    """
    if not fp_results:
        return ''
    return f'''
    <!-- 误报 -->
    <div class="passed-section">
        <div class="section-title">🤖 已过滤误报 ({fp_count}项)</div>
        {fp_html}
    </div>
    '''


def render_llm_fp_section(llm_fp_count, llm_fp_html, llm_fp_results):
    """渲染LLM确认非问题区域

    Args:
        llm_fp_count: LLM确认非问题数量
        llm_fp_html: LLM非问题列表HTML
        llm_fp_results: LLM非问题结果列表（用于判断是否展示）

    Returns:
        LLM非问题区域HTML片段
    """
    if not llm_fp_results:
        return ''
    return f'''
    <!-- LLM非问题 -->
    <div class="passed-section">
        <div class="section-title">🤖 LLM确认非问题 ({llm_fp_count}项)</div>
        <p style="font-size:13px;color:var(--text-secondary);margin-bottom:12px;">以下问题经AI大语言模型二次确认，判定为非真实问题，不计入评分。</p>
        {llm_fp_html}
    </div>
    '''


def render_ai_verified_badge(ai_verified):
    """渲染AI二次校验标记

    Args:
        ai_verified: AI二次校验的问题数量

    Returns:
        AI校验标记HTML片段（若为0则返回空字符串）
    """
    if ai_verified <= 0:
        return ''
    return f'''
    <!-- v3.5.1: AI二次校验标记 -->
    <div class="passed-section" style="margin-top:8px;">
        <div style="font-size:13px;color:var(--text-secondary);padding:8px 12px;background:rgba(34,197,94,0.06);border-radius:8px;border:1px solid rgba(34,197,94,0.15);">
            ✅ <b>AI二次校验</b>：本报告共{ai_verified}个问题已通过AI大语言模型二次确认，确保问题真实性。
        </div>
    </div>
    '''
