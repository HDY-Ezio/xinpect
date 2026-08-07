"""
煋鉴(Xinpect) 报告组件 - 统计栏组件
展示各类问题数量的统计卡片
"""


def render_stats(errors, warnings, suggestion_count, problem_count, fp_count, total):
    """渲染问题统计行

    Args:
        errors: 阻断级问题数
        warnings: 警告级问题数
        suggestion_count: 建议类数量（不扣分）
        problem_count: 代码问题总数（阻断+警告）
        fp_count: 已过滤误报数
        total: 总检查项数

    Returns:
        统计栏HTML片段
    """
    return f'''
    <!-- 问题统计 -->
    <div class="stats-row">
        <div class="stat-card stat-error">
            <div class="stat-number text-error">{errors}</div>
            <div class="stat-label">🚫 阻断</div>
        </div>
        <div class="stat-card stat-warning">
            <div class="stat-number text-warning">{warnings}</div>
            <div class="stat-label">🟡 警告</div>
        </div>
        <div class="stat-card stat-info">
            <div class="stat-number text-info">{suggestion_count}</div>
            <div class="stat-label">💡 建议（不扣分）</div>
        </div>
        <div class="stat-card stat-total">
            <div class="stat-number text-total">{problem_count}</div>
            <div class="stat-label">🐛 代码问题</div>
        </div>
        <div class="stat-card stat-fp">
            <div class="stat-number text-fp">{fp_count}</div>
            <div class="stat-label">🤖 已过滤误报</div>
        </div>
        <div class="stat-card stat-total">
            <div class="stat-number text-total">{total}</div>
            <div class="stat-label">📊 总检查项</div>
        </div>
    </div>
    '''
