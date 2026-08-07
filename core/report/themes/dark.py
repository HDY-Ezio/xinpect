"""
煋鉴(Xinpect) 主题系统 - 深色主题
定义深色主题下的所有CSS变量值
"""


def get_dark_css() -> str:
    """获取深色主题CSS变量定义"""
    return '''
[data-theme="dark"] {
    /* ===== 品牌色 ===== */
    --brand: #FF8C5A;
    --brand-light: rgba(255,140,90,0.15);
    --brand-dark: #e55a2b;
    --brand-glow: rgba(255,140,90,0.25);

    /* ===== 背景与前景 ===== */
    --bg: #0f172a;
    --card-bg: #1e293b;
    --text: #f1f5f9;
    --text-secondary: #94a3b8;
    --border: #334155;
    --placeholder-color: #64748b;

    /* ===== 状态色 ===== */
    --error: #f87171;
    --error-bg: rgba(248,113,113,0.1);
    --warning: #fbbf24;
    --warning-bg: rgba(251,191,36,0.1);
    --info: #60a5fa;
    --info-bg: rgba(96,165,250,0.1);
    --success: #4ade80;
    --fp-color: #a78bfa;

    /* ===== 问题卡片渐变背景 ===== */
    --issue-blocking-bg: linear-gradient(90deg, rgba(248,113,113,0.08), transparent 200px);
    --issue-problem-bg: linear-gradient(90deg, rgba(251,191,36,0.08), transparent 200px);
    --issue-suggestion-bg: linear-gradient(90deg, rgba(96,165,250,0.08), transparent 200px);

    /* ===== 通过项 ===== */
    --passed-bg: rgba(74,222,128,0.1);
    --passed-border: rgba(74,222,128,0.3);

    /* ===== 代码块 ===== */
    --code-bg: #0f172a;
    --code-fg: #e2e8f0;

    /* ===== Tab相关 ===== */
    --tab-hover-bg: rgba(30,41,59,0.6);

    /* ===== 增量徽章 ===== */
    --inc-badge-bg: rgba(74,222,128,0.15);
    --inc-badge-fg: #4ade80;

    /* ===== 字体（与浅色一致） ===== */
    --font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans SC", sans-serif;
    --font-mono: "SF Mono","Fira Code",monospace;
    --line-height: 1.6;

    /* ===== 间距与尺寸（与浅色一致） ===== */
    --container-max-width: 1100px;
    --container-pad-y: 24px;
    --container-pad-x: 16px;
    --section-gap: 24px;
    --header-pad-y: 40px;
    --header-pad-x: 32px;

    /* ===== 圆角与阴影 ===== */
    --radius: 12px;
    --shadow: 0 1px 3px rgba(0,0,0,0.3), 0 1px 2px rgba(0,0,0,0.2);
    --shadow-lg: 0 10px 15px -3px rgba(0,0,0,0.4), 0 4px 6px -2px rgba(0,0,0,0.25);
    --footer-cta-shadow: 0 4px 6px -1px rgba(255,140,90,0.35);
    --footer-cta-shadow-hover: 0 6px 12px -2px rgba(255,140,90,0.5);
}
'''
