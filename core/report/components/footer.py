"""
煋鉴(Xinpect) 报告组件 - 页脚组件
"""

from ._utils import _esc


def render_footer(now_str):
    """渲染底部区域

    Args:
        now_str: 当前时间字符串

    Returns:
        页脚HTML片段
    """
    return f'''
    <!-- 底部 -->
    <div class="footer">
        <div class="footer-brand">🌟 煋旺智能 · Xinpect</div>
        <div class="footer-desc">AI时代的代码质检工具 — 用AI抓Bug，用AI修Bug</div>
        <div class="footer-lite-hint">
            💡 提示：您正在使用基础版检测。B1~B3 基础检测可以帮您发现语法错误、
            低级安全漏洞和规范问题，完整 8 维度检测请前往 煋鉴官网 获取。
        </div>
        <div class="footer-note">报告由煋鉴 QA Framework 自动生成 · {now_str}</div>
    </div>
    '''
