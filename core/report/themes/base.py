"""
煋鉴(Xinpect) 主题系统 - 基础样式
包含CSS变量定义、全局重置、通用布局样式
所有颜色/间距/字体均使用CSS变量，支持主题切换
"""

# 大脑名称映射（v2.0 修正）
BRAIN_NAMES = {
    '1': '规则引擎',
    '2': '安全审计',
    '3': 'AI语义分析',
    '4': '性能优化',
    '5': '依赖审计',
    '6': '代码质量',
    '7': '架构健康',
    '8': '业务安全',
}


def get_base_css() -> str:
    """获取基础CSS：全局重置、布局、响应式等与颜色无关的样式"""
    return '''
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: var(--font-family);
    background: var(--bg); color: var(--text); line-height: var(--line-height);
    -webkit-font-smoothing: antialiased;
}
.container { max-width: var(--container-max-width); margin: 0 auto; padding: var(--container-pad-y) var(--container-pad-x); }

/* ===== Header ===== */
.header {
    background: linear-gradient(135deg, var(--brand), var(--brand-dark));
    color: white; padding: var(--header-pad-y) var(--header-pad-x); border-radius: var(--radius);
    margin-bottom: var(--section-gap); box-shadow: var(--shadow-lg);
    position: relative; overflow: hidden;
}
.header::after {
    content: ''; position: absolute; top: -50%; right: -20%;
    width: 300px; height: 300px; background: rgba(255,255,255,0.08); border-radius: 50%;
}
.header-brand { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.header-logo { font-size: 36px; font-weight: 800; letter-spacing: -1px; }
.header-subtitle { font-size: 14px; opacity: 0.85; font-weight: 400; }
.header-meta { display: flex; flex-wrap: wrap; gap: 20px; font-size: 13px; opacity: 0.9; }
.header-meta span { display: flex; align-items: center; gap: 6px; }

/* ===== Scores ===== */
.scores-section {
    background: var(--card-bg); border-radius: var(--radius);
    padding: 32px; margin-bottom: var(--section-gap); box-shadow: var(--shadow); text-align: center;
}
.scores-title { font-size: 20px; font-weight: 700; margin-bottom: 24px; }
.scores-grid { display: flex; justify-content: center; flex-wrap: wrap; gap: 32px; }
.score-item { display: flex; flex-direction: column; align-items: center; }

/* ===== Stats ===== */
.stats-row {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 16px; margin-bottom: var(--section-gap);
}
.stat-card {
    background: var(--card-bg); border-radius: var(--radius); padding: 20px;
    text-align: center; box-shadow: var(--shadow);
    border-left: 4px solid var(--border); transition: transform 0.2s;
}
.stat-card:hover { transform: translateY(-2px); box-shadow: var(--shadow-lg); }
.stat-card.stat-error { border-left-color: var(--error); }
.stat-card.stat-warning { border-left-color: var(--warning); }
.stat-card.stat-info { border-left-color: var(--info); }
.stat-card.stat-total { border-left-color: var(--brand); }
.stat-card.stat-fp { border-left-color: var(--fp-color); }
.stat-number { font-size: 32px; font-weight: 800; line-height: 1.2; }
.stat-number.text-error { color: var(--error); }
.stat-number.text-warning { color: var(--warning); }
.stat-number.text-info { color: var(--info); }
.stat-number.text-total { color: var(--brand); }
.stat-number.text-fp { color: var(--fp-color); }
.stat-label { font-size: 13px; color: var(--text-secondary); margin-top: 4px; }

/* ===== Brains ===== */
.brain-section {
    background: var(--card-bg); border-radius: var(--radius);
    padding: 28px; margin-bottom: var(--section-gap); box-shadow: var(--shadow);
}
.section-title { font-size: 18px; font-weight: 700; margin-bottom: 20px; display: flex; align-items: center; gap: 8px; }
.brains-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }
.brain-card {
    background: var(--bg); border-radius: 10px; padding: 16px; text-align: center;
    border: 1px solid var(--border); transition: all 0.2s;
}
.brain-card:hover { border-color: var(--brand); box-shadow: 0 0 0 2px var(--brand-light); }
.brain-name { font-size: 13px; font-weight: 600; color: var(--text); margin-bottom: 6px; }
.brain-total { font-size: 28px; font-weight: 800; color: var(--brand); }
.brain-breakdown { display: flex; justify-content: center; gap: 8px; font-size: 12px; margin-top: 6px; }
.brain-err { color: var(--error); } .brain-warn { color: var(--warning); } .brain-inf { color: var(--info); }

/* ===== Issues ===== */
.issues-section {
    background: var(--card-bg); border-radius: var(--radius);
    padding: 28px; margin-bottom: var(--section-gap); box-shadow: var(--shadow);
}
.issue-card {
    border: 1px solid var(--border); border-radius: 10px; padding: 16px 20px;
    margin-bottom: 12px; transition: all 0.2s; background: var(--card-bg);
}
.issue-card:hover { box-shadow: var(--shadow); }
.issue-card.issue-blocking { border-left: 4px solid var(--error); background: var(--issue-blocking-bg); }
.issue-card.issue-problem { border-left: 4px solid var(--warning); background: var(--issue-problem-bg); }
.issue-card.issue-suggestion { border-left: 4px solid var(--info); background: var(--issue-suggestion-bg); }
.issue-card.issue-error { border-left: 4px solid var(--error); background: var(--issue-blocking-bg); }
.issue-card.issue-warning { border-left: 4px solid var(--warning); background: var(--issue-problem-bg); }
.issue-card.issue-info { border-left: 4px solid var(--info); background: var(--issue-suggestion-bg); }
.issue-header {
    display: flex; justify-content: space-between; align-items: center;
    flex-wrap: wrap; gap: 8px; margin-bottom: 8px;
}
.issue-left { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.issue-id {
    font-family: var(--font-mono); font-size: 12px;
    background: var(--bg); padding: 2px 8px; border-radius: 6px; color: var(--text-secondary);
}
.issue-name { font-weight: 600; font-size: 14px; }
.issue-loc { font-size: 12px; color: var(--text-secondary); font-family: var(--font-mono); }
.issue-msg { font-size: 14px; color: var(--text); padding: 4px 0; }

.toggle-btn {
    background: none; border: 1px solid var(--border); border-radius: 6px;
    padding: 4px 12px; font-size: 12px; color: var(--text-secondary);
    cursor: pointer; margin-top: 8px; transition: all 0.2s;
}
.toggle-btn:hover { background: var(--bg); border-color: var(--brand); color: var(--brand); }
.issue-detail { max-height: 0; overflow: hidden; transition: max-height 0.35s ease; }
.issue-card.expanded .issue-detail { max-height: 2000px; }
.issue-card.expanded .toggle-arrow { transform: rotate(180deg); }
.toggle-arrow { display: inline-block; transition: transform 0.3s; font-size: 10px; }
.detail-block {
    margin-top: 12px; padding: 12px; background: var(--bg);
    border-radius: 8px; font-size: 13px;
}
.detail-block p { margin: 4px 0; }
.detail-block pre {
    margin: 8px 0 0; padding: 12px; background: var(--code-bg); color: var(--code-fg);
    border-radius: 6px; overflow-x: auto; font-size: 12px; line-height: 1.5;
}
.detail-block code { font-family: var(--font-mono); }

/* ===== v2.0: Search Bar ===== */
.search-bar {
    position: relative; margin-bottom: 16px;
}
.search-icon {
    position: absolute; left: 14px; top: 50%; transform: translateY(-50%);
    font-size: 16px; color: var(--text-secondary); pointer-events: none; z-index: 1;
}
.search-input {
    width: 100%; padding: 12px 16px 12px 42px; border: 2px solid var(--border);
    border-radius: 10px; font-size: 14px; outline: none; transition: all 0.2s;
    background: var(--bg); color: var(--text);
}
.search-input:focus {
    border-color: var(--brand); box-shadow: 0 0 0 3px var(--brand-glow);
    background: var(--card-bg);
}
.search-input::placeholder { color: var(--placeholder-color); }
.search-count {
    position: absolute; right: 14px; top: 50%; transform: translateY(-50%);
    font-size: 12px; color: var(--text-secondary); background: var(--bg);
    padding: 2px 10px; border-radius: 10px; display: none;
}
.search-count.visible { display: block; }

/* ===== v2.0: View Tabs ===== */
.view-tabs {
    display: flex; gap: 4px; margin-bottom: 16px; background: var(--bg);
    border-radius: 10px; padding: 4px; border: 1px solid var(--border);
}
.view-tab {
    flex: 1; padding: 8px 12px; border: none; background: transparent;
    border-radius: 8px; cursor: pointer; font-size: 13px; font-weight: 500;
    color: var(--text-secondary); transition: all 0.2s; text-align: center;
    white-space: nowrap;
}
.view-tab:hover { color: var(--text); background: var(--tab-hover-bg); }
.view-tab.active {
    background: var(--card-bg); color: var(--brand); font-weight: 600;
    box-shadow: var(--shadow);
}

/* ===== v2.0: Toolbar ===== */
.toolbar {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 16px; flex-wrap: wrap; gap: 8px;
}
.result-count { font-size: 14px; color: var(--text-secondary); font-weight: 500; }
.result-count strong { color: var(--brand); font-weight: 700; }
.toolbar-actions { display: flex; gap: 8px; }
.toolbar-btn {
    padding: 6px 14px; border: 1px solid var(--border); border-radius: 8px;
    background: var(--card-bg); cursor: pointer; font-size: 12px; font-weight: 500;
    color: var(--text-secondary); transition: all 0.2s; white-space: nowrap;
}
.toolbar-btn:hover { border-color: var(--brand); color: var(--brand); background: var(--brand-light); }

/* ===== v2.0: Groups ===== */
.group-section { margin-bottom: 16px; }
.group-header {
    display: flex; align-items: center; gap: 10px; padding: 12px 16px;
    background: var(--bg); border-radius: 10px; cursor: pointer; user-select: none;
    border: 1px solid var(--border); transition: all 0.2s; margin-bottom: 2px;
}
.group-header:hover { border-color: var(--brand); background: var(--brand-light); }
.group-arrow {
    display: inline-block; font-size: 10px; color: var(--text-secondary);
    transition: transform 0.3s ease; flex-shrink: 0;
}
.group-section.collapsed .group-arrow { transform: rotate(-90deg); }
.group-title { font-weight: 600; font-size: 14px; color: var(--text); }
.group-count {
    font-size: 12px; color: var(--text-secondary); background: var(--card-bg);
    padding: 2px 10px; border-radius: 10px; border: 1px solid var(--border);
    margin-left: auto; flex-shrink: 0;
}
.group-level-dot {
    width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0;
}
.group-level-dot.dot-blocking { background: var(--error); }
.group-level-dot.dot-problem { background: var(--warning); }
.group-level-dot.dot-suggestion { background: var(--info); }
.group-content {
    overflow: hidden; transition: max-height 0.35s ease, opacity 0.25s ease;
    padding: 4px 0;
}
.group-section.collapsed .group-content {
    max-height: 0 !important; opacity: 0; padding: 0;
}

/* ===== Passed ===== */
.passed-section {
    background: var(--card-bg); border-radius: var(--radius);
    padding: 28px; margin-bottom: var(--section-gap); box-shadow: var(--shadow);
}
.passed-section details { cursor: pointer; }
.passed-section summary { font-size: 16px; font-weight: 600; padding: 8px 0; cursor: pointer; user-select: none; }
.passed-grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 8px; padding: 16px 0;
}
.passed-item {
    display: flex; align-items: center; gap: 8px; padding: 8px 12px;
    background: var(--passed-bg); border-radius: 8px; font-size: 13px; border: 1px solid var(--passed-border);
}
.passed-icon { font-size: 14px; }
.passed-id { font-family: var(--font-mono); font-size: 11px; color: var(--text-secondary); }
.passed-name { font-weight: 500; flex: 1; }
.passed-cat { font-size: 11px; color: var(--text-secondary); }

/* ===== FP ===== */
.fp-section { margin: 8px 0; border: 1px solid var(--border); border-radius: 8px; padding: 12px; }
.fp-section summary { font-size: 14px; cursor: pointer; padding: 4px 0; }
.fp-item { padding: 8px 12px; font-size: 13px; border-bottom: 1px solid var(--border); }
.fp-item:last-child { border-bottom: none; }
.fp-reason { font-size: 12px; color: var(--text-secondary); margin-top: 4px; padding-left: 20px; }

/* ===== Badges ===== */
.llm-badge, .inc-badge {
    display: inline-block; background: var(--brand-light); color: var(--brand-dark);
    padding: 6px 16px; border-radius: 20px; font-size: 13px; font-weight: 500; margin: 8px 4px;
}
.inc-badge { background: var(--inc-badge-bg); color: var(--inc-badge-fg); }

/* ===== Empty ===== */
.empty-state { text-align: center; padding: 60px 20px; font-size: 18px; color: var(--success); }
.no-results { text-align: center; padding: 40px 20px; color: var(--text-secondary); font-size: 15px; }

/* ===== Footer ===== */
.footer {
    background: var(--card-bg); border-radius: var(--radius);
    padding: 32px; text-align: center; box-shadow: var(--shadow); margin-top: 8px;
}
.footer-brand { font-size: 16px; font-weight: 700; color: var(--brand); margin-bottom: 8px; }
.footer-desc { font-size: 13px; color: var(--text-secondary); margin-bottom: 16px; }
.footer-cta {
    display: inline-block; background: linear-gradient(135deg, var(--brand), var(--brand-dark));
    color: white; text-decoration: none; padding: 12px 32px; border-radius: 8px;
    font-weight: 600; font-size: 14px; transition: all 0.2s;
    box-shadow: var(--footer-cta-shadow);
}
.footer-cta:hover { transform: translateY(-1px); box-shadow: var(--footer-cta-shadow-hover); }
.footer-note { font-size: 11px; color: var(--text-secondary); margin-top: 16px; opacity: 0.7; }

/* ===== Responsive ===== */
@media (max-width: 768px) {
    .container { padding: 12px 8px; }
    .header { padding: 24px 16px; }
    .header-logo { font-size: 26px; }
    .header-meta { gap: 8px; font-size: 12px; }
    .scores-section { padding: 20px 12px; }
    .scores-grid { gap: 12px; }
    .scores-grid svg { width: 110px; height: 110px; }
    .stats-row { grid-template-columns: repeat(2, 1fr); gap: 10px; }
    .stat-number { font-size: 24px; }
    .stat-card { padding: 14px 10px; }
    .stat-label { font-size: 11px; }
    .brains-grid { grid-template-columns: repeat(2, 1fr); }
    .issues-section, .brain-section, .passed-section { padding: 16px 12px; }
    .issue-header { flex-direction: column; align-items: flex-start; }
    .issue-card { padding: 12px 14px; }
    .passed-grid { grid-template-columns: 1fr; }
    .view-tabs { flex-wrap: nowrap; overflow-x: auto; -webkit-overflow-scrolling: touch; }
    .view-tab { min-width: 0; font-size: 12px; padding: 8px 8px; }
    .toolbar { flex-direction: column; align-items: stretch; }
    .toolbar-actions { justify-content: flex-end; }
    .search-input { font-size: 16px; }
    .group-header { padding: 10px 12px; }
    .section-title { font-size: 16px; }
}
@media (max-width: 480px) {
    .scores-grid { flex-direction: column; align-items: center; }
    .stats-row { grid-template-columns: repeat(2, 1fr); }
    .header-brand { flex-direction: column; align-items: flex-start; gap: 4px; }
    .brain-card { padding: 12px 8px; }
    .brain-total { font-size: 22px; }
    .brain-name { font-size: 12px; }
}
@media print {
    body { background: white; }
    .container { max-width: 100%; padding: 0; }
    .issue-card, .stat-card, .brain-card { break-inside: avoid; }
    .issue-detail { max-height: none !important; }
    .toggle-btn { display: none; }
    .search-bar, .view-tabs, .toolbar-actions { display: none !important; }
    .group-content { max-height: none !important; opacity: 1 !important; }
}
'''
