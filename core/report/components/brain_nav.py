"""
煋鉴(Xinpect) 报告组件 - 大脑维度导航
展示8大维度的问题分布
"""

from ._utils import _esc


def render_brain_section(brain_stats):
    """渲染大脑分布区域

    Args:
        brain_stats: 大脑统计字典 {brain_name: {'total': int, 'blocking': int, 'problem': int, 'suggestion': int}}

    Returns:
        大脑分布HTML片段
    """
    brain_cards = ''
    for brain_name, bstats in sorted(brain_stats.items(), key=lambda x: -x[1]['total']):
        if bstats['total'] == 0:
            continue
        brain_cards += f'''<div class="brain-card">
            <div class="brain-name">{_esc(brain_name)}</div>
            <div class="brain-total">{bstats['total']}</div>
            <div class="brain-breakdown">
                <span class="brain-err">🚫 {bstats['blocking']}</span>
                <span class="brain-warn">🟡 {bstats['problem']}</span>
                <span class="brain-inf">💡 {bstats['suggestion']}</span>
            </div>
        </div>'''
    return f'''
    <!-- 大脑分布 -->
    <div class="brain-section">
        <div class="section-title">🧠 按大脑分布</div>
        <div class="brains-grid">
            {brain_cards if brain_cards else '<div class="empty-state" style="grid-column:1/-1;padding:20px;">暂无数据</div>'}
        </div>
    </div>
    '''
