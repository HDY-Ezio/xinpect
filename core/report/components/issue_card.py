"""
煋鉴(Xinpect) 报告组件 - 问题卡片组件
单个问题卡片、问题区域（含搜索/视图切换）、AI建议区
"""

from ._utils import _esc, _esc_js, _get_level_badge, _get_level_icon


def render_issue_card(r, idx, brain_name=''):
    """生成单个问题卡片HTML

    Args:
        r: 问题结果对象
        idx: 卡片索引/ID
        brain_name: 所属大脑名称

    Returns:
        问题卡片HTML片段
    """
    level = getattr(r, 'level', 'info')
    if level not in ('blocking', 'problem', 'suggestion', 'error', 'warning', 'info'):
        level = 'info'
    badge = _get_level_badge(level)
    icon = _get_level_icon(level)

    location = getattr(r, 'location', {}) or {}
    file_info = location.get('file', '')
    line_info = location.get('line', 0)
    loc_str = f'{_esc(file_info)}:{line_info}' if file_info else '全局'

    # 修复建议（优先LLM建议）
    llm_fix = getattr(r, 'llm_fix_suggestion', '')
    llm_code = getattr(r, 'llm_fixed_code', '')
    fix_text = getattr(r, 'fix', '') or ''
    suggestion_code = getattr(r, 'suggestion_code', '') or ''

    detail_html = ''
    if llm_fix:
        detail_html += f'<div class="detail-block"><strong>🤖 AI修复建议:</strong><p>{_esc(llm_fix)}</p></div>'
    if llm_code:
        detail_html += f'<div class="detail-block"><strong>🤖 AI修复代码:</strong><pre><code>{_esc(llm_code)}</code></pre></div>'
    if suggestion_code and not llm_code:
        detail_html += f'<div class="detail-block"><strong>💡 修复代码示例:</strong><pre><code>{_esc(suggestion_code)}</code></pre></div>'

    detail_text = getattr(r, 'detail', '') or ''
    if detail_text and not llm_fix:
        detail_html += f'<div class="detail-block"><strong>详情:</strong><pre><code>{_esc(detail_text[:500])}</code></pre></div>'

    if fix_text and not llm_fix and not suggestion_code:
        detail_html += f'<div class="detail-block"><strong>🔧 修复建议:</strong><p>{_esc(fix_text)}</p></div>'

    has_detail = bool(detail_html)
    toggle = ''
    if has_detail:
        toggle = f'''<button class="toggle-btn" onclick="event.stopPropagation();this.parentElement.classList.toggle('expanded')">
            <span class="toggle-text">展开详情</span> <span class="toggle-arrow">▼</span>
        </button>'''

    rule_name = getattr(r, 'rule_name', '') or getattr(r, 'name', '') or ''
    rule_id = getattr(r, 'rule_id', '') or getattr(r, 'check_id', '') or getattr(r, 'id', '') or ''
    message = getattr(r, 'message', '') or ''

    return f'''<div class="issue-card issue-{level}" id="issue-{idx}" data-level="{level}" data-file="{_esc_js(file_info)}" data-brain="{_esc_js(brain_name)}" data-search="{_esc_js(rule_id)} {_esc_js(rule_name)} {_esc_js(message)} {_esc_js(file_info)}">
        <div class="issue-header">
            <div class="issue-left">
                {badge}
                <span class="issue-id">{_esc(rule_id)}</span>
                <span class="issue-name">{_esc(rule_name)}</span>
            </div>
            <span class="issue-loc">📍 {loc_str}</span>
        </div>
        <div class="issue-msg">{icon} {_esc(message)}</div>
        {toggle}
        <div class="issue-detail">
            {detail_html}
        </div>
    </div>'''


def render_issues_section(all_issues, issues_html):
    """渲染代码问题区域（含搜索/视图切换）

    Args:
        all_issues: 问题列表（用于计数）
        issues_html: 问题卡片HTML集合

    Returns:
        问题区域HTML片段
    """
    return f'''
    <!-- 问题详情（含搜索/视图切换/展开折叠） -->
    <div class="issues-section" id="issues-section">
        <div class="section-title">🐛 代码问题 ({len(all_issues)}项)</div>

        <!-- 搜索框 -->
        <div class="search-bar">
            <span class="search-icon">🔍</span>
            <input type="text" class="search-input" id="searchInput"
                   placeholder="搜索规则ID、文件名或关键词..." autocomplete="off">
            <span class="search-count" id="searchCount"></span>
        </div>

        <!-- 视图切换Tab -->
        <div class="view-tabs" id="viewTabs">
            <button class="view-tab active" data-view="severity" onclick="switchView('severity')">🔴 按严重度</button>
            <button class="view-tab" data-view="file" onclick="switchView('file')">📁 按文件</button>
            <button class="view-tab" data-view="brain" onclick="switchView('brain')">🧠 按大脑</button>
        </div>

        <!-- 工具栏 -->
        <div class="toolbar">
            <div class="result-count" id="resultCount">显示 <strong>{len(all_issues)}</strong> / {len(all_issues)} 项</div>
            <div class="toolbar-actions">
                <button class="toolbar-btn" onclick="expandAll()">📂 全部展开</button>
                <button class="toolbar-btn" onclick="collapseAll()">📁 全部折叠</button>
            </div>
        </div>

        <!-- 分组容器（JS动态填充） -->
        <div id="issuesContainer"></div>

        <!-- 原始卡片数据（供JS读取，隐藏） -->
        <div id="rawIssuesData" style="display:none;">
            {issues_html}
        </div>
    </div>
    '''


def render_suggestions_section(all_suggestions, suggestions_html):
    """渲染AI优化建议区域（独立区块，不扣分）

    Args:
        all_suggestions: 建议列表
        suggestions_html: 建议卡片HTML集合

    Returns:
        建议区域HTML片段（若无建议则返回空字符串）
    """
    if not all_suggestions:
        return ''
    return f'''
    <!-- AI 优化建议（独立区块，不扣分） -->
    <div class="issues-section" id="suggestions-section" style="border-top: 2px dashed #cbd5e1;">
        <div class="section-title">💡 AI 优化建议 ({len(all_suggestions)}项)
            <span style="font-size:12px;font-weight:400;color:var(--text-secondary);margin-left:8px;">（仅作提醒，不计入评分）</span>
        </div>

        <!-- 搜索框 -->
        <div class="search-bar">
            <span class="search-icon">🔍</span>
            <input type="text" class="search-input" id="sugSearchInput"
                   placeholder="搜索建议内容..." autocomplete="off">
            <span class="search-count" id="sugSearchCount"></span>
        </div>

        <!-- 视图切换Tab -->
        <div class="view-tabs" id="sugViewTabs">
            <button class="view-tab active" data-view="severity" onclick="switchSugView('severity')">📋 按类型</button>
            <button class="view-tab" data-view="file" onclick="switchSugView('file')">📁 按文件</button>
            <button class="view-tab" data-view="brain" onclick="switchSugView('brain')">🧠 按大脑</button>
        </div>

        <!-- 工具栏 -->
        <div class="toolbar">
            <div class="result-count" id="sugResultCount">显示 <strong>{len(all_suggestions)}</strong> / {len(all_suggestions)} 项</div>
            <div class="toolbar-actions">
                <button class="toolbar-btn" onclick="expandAllSug()">📂 全部展开</button>
                <button class="toolbar-btn" onclick="collapseAllSug()">📁 全部折叠</button>
            </div>
        </div>

        <!-- 分组容器（JS动态填充） -->
        <div id="suggestionsContainer"></div>

        <!-- 原始卡片数据（供JS读取，隐藏） -->
        <div id="rawSuggestionsData" style="display:none;">
            {suggestions_html}
        </div>
    </div>
    '''
