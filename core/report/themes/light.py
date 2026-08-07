"""
煋鉴(Xinpect) 主题系统 - 浅色主题（默认）
定义浅色主题下的所有CSS变量值
"""


def get_light_css() -> str:
    """获取浅色主题CSS变量定义"""
    return '''
:root, [data-theme="light"] {
    /* ===== 品牌色 ===== */
    --brand: #FF6B35;
    --brand-light: #fff3ed;
    --brand-dark: #cc5529;
    --brand-glow: rgba(255,107,53,0.12);

    /* ===== 背景与前景 ===== */
    --bg: #f8fafc;
    --card-bg: #ffffff;
    --text: #1e293b;
    --text-secondary: #64748b;
    --border: #e2e8f0;
    --placeholder-color: #94a3b8;

    /* ===== 状态色 ===== */
    --error: #ef4444;
    --error-bg: #fef2f2;
    --warning: #f59e0b;
    --warning-bg: #fffbeb;
    --info: #3b82f6;
    --info-bg: #eff6ff;
    --success: #22c55e;
    --fp-color: #8b5cf6;

    /* ===== 问题卡片渐变背景 ===== */
    --issue-blocking-bg: linear-gradient(90deg, rgba(239,68,68,0.03), transparent 200px);
    --issue-problem-bg: linear-gradient(90deg, rgba(245,158,11,0.03), transparent 200px);
    --issue-suggestion-bg: linear-gradient(90deg, rgba(59,130,246,0.03), transparent 200px);

    /* ===== 通过项 ===== */
    --passed-bg: #f0fdf4;
    --passed-border: #bbf7d0;

    /* ===== 代码块 ===== */
    --code-bg: #1e293b;
    --code-fg: #e2e8f0;

    /* ===== Tab相关 ===== */
    --tab-hover-bg: rgba(255,255,255,0.6);

    /* ===== 增量徽章 ===== */
    --inc-badge-bg: #ecfdf5;
    --inc-badge-fg: #065f46;

    /* ===== 字体 ===== */
    --font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans SC", sans-serif;
    --font-mono: "SF Mono","Fira Code",monospace;
    --line-height: 1.6;

    /* ===== 间距与尺寸 ===== */
    --container-max-width: 1100px;
    --container-pad-y: 24px;
    --container-pad-x: 16px;
    --section-gap: 24px;
    --header-pad-y: 40px;
    --header-pad-x: 32px;

    /* ===== 圆角与阴影 ===== */
    --radius: 12px;
    --shadow: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
    --shadow-lg: 0 10px 15px -3px rgba(0,0,0,0.08), 0 4px 6px -2px rgba(0,0,0,0.04);
    --footer-cta-shadow: 0 4px 6px -1px rgba(255,107,53,0.3);
    --footer-cta-shadow-hover: 0 6px 12px -2px rgba(255,107,53,0.4);
}
'''
