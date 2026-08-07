"""
煋鉴(Xinpect) 报告组件 - 评分卡片组件
包含仪表盘SVG和综合评分区域
"""

from ._utils import _esc, _get_score_color


def render_gauge_svg(score, label, size=160):
    """生成仪表盘SVG

    Args:
        score: 分数 (0-100)
        label: 标签文字
        size: SVG尺寸

    Returns:
        SVG HTML字符串
    """
    color = _get_score_color(score)
    circumference = 2 * 3.14159 * 60
    offset = circumference - (score / 100) * circumference
    return f'''<svg width="{size}" height="{size}" viewBox="0 0 160 160">
        <circle cx="80" cy="80" r="60" fill="none" stroke="#e5e7eb" stroke-width="12"/>
        <circle cx="80" cy="80" r="60" fill="none" stroke="{color}" stroke-width="12"
            stroke-dasharray="{circumference:.1f}" stroke-dashoffset="{offset:.1f}"
            stroke-linecap="round" transform="rotate(-90 80 80)"
            style="transition: stroke-dashoffset 0.8s ease;"/>
        <text x="80" y="72" text-anchor="middle" font-size="32" font-weight="700" fill="{color}">{score}</text>
        <text x="80" y="95" text-anchor="middle" font-size="13" fill="#6b7280">/ 100</text>
        <text x="80" y="140" text-anchor="middle" font-size="14" font-weight="600" fill="#374151">{_esc(label)}</text>
    </svg>'''


def render_scores(score_total, score_bug, score_smell, score_eng, scoring_note):
    """渲染综合评分区域

    Args:
        score_total: 综合分数
        score_bug: Bug维度分数
        score_smell: Code Smell分数
        score_eng: 工程成熟度分数
        scoring_note: 评分备注

    Returns:
        评分区域HTML片段
    """
    return f'''
    <!-- 综合评分 -->
    <div class="scores-section">
        <div class="scores-title">📊 综合评分</div>
        <div class="scores-grid">
            <div class="score-item">{render_gauge_svg(score_total, '综合')}</div>
            <div class="score-item">{render_gauge_svg(score_bug, 'Bug维度')}</div>
            <div class="score-item">{render_gauge_svg(score_smell, 'Code Smell')}</div>
            <div class="score-item">{render_gauge_svg(score_eng, '工程成熟度')}</div>
        </div>
        <div style="margin-top:20px;padding:10px 16px;background:#eff6ff;border-radius:8px;font-size:13px;color:#1e40af;display:inline-block;">
            💡 {_esc(scoring_note)}
        </div>
    </div>
    '''
