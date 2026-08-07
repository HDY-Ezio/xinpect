"""
煋鉴(Xinpect) 页面模板 - 精简报告模板
用于快速预览的精简版报告（仅含核心数据）
"""

from ..themes import get_css, get_javascript
from ..components._utils import _esc


def build_mini_html(project_path, now_str, summary_html, theme: str = 'light'):
    """构建精简版HTML报告

    Args:
        project_path: 项目路径
        now_str: 当前时间字符串
        summary_html: 摘要内容HTML
        theme: 主题名称

    Returns:
        精简版HTML文档字符串
    """
    css = get_css(theme)
    js = get_javascript()
    return f'''<!DOCTYPE html>
<html lang="zh-CN" data-theme="{theme}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>煋鉴 QA报告（精简版）- {_esc(project_path or '项目')}</title>
<style>
{css}
</style>
</head>
<body>
<div class="container">
{summary_html}
</div>
<script>
{js}
</script>
</body>
</html>'''
