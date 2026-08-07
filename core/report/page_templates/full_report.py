"""
煋鉴(Xinpect) 页面模板 - 完整报告模板
负责将body片段装配成完整的HTML文档（含head/body/script结构）
"""

from ..themes import get_css, get_javascript
from ..components._utils import _esc


def build_full_html(project_path, now_str, body_parts, theme: str = 'light'):
    """构建完整的HTML文档结构

    Args:
        project_path: 项目路径（用于title）
        now_str: 当前时间字符串
        body_parts: body部分的HTML片段列表
        theme: 主题名称 'light' / 'dark'，默认 'light'

    Returns:
        完整的HTML文档字符串
    """
    css = get_css(theme)
    js = get_javascript()
    body = '\n'.join(body_parts)
    return f'''<!DOCTYPE html>
<html lang="zh-CN" data-theme="{theme}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>煋鉴 QA报告 - {_esc(project_path or '项目')}</title>
<style>
{css}
</style>
</head>
<body>
<div class="container">
{body}
</div>

<script>
{js}
</script>
</body>
</html>'''
