"""
煋鉴(Xinpect) 主题系统
支持 light / dark 主题切换，所有颜色、间距、字体均使用CSS变量定义
"""

from .base import BRAIN_NAMES, get_base_css
from .light import get_light_css
from .dark import get_dark_css
from .scripts import get_javascript


def get_css(theme: str = 'light') -> str:
    """获取完整的CSS样式（含变量定义 + 基础样式）

    Args:
        theme: 主题名称，'light' 或 'dark'，默认 'light'

    Returns:
        完整的CSS字符串
    """
    base = get_base_css()
    light = get_light_css()
    dark = get_dark_css()

    # 始终包含 light（作为 :root 默认）和 dark（通过 data-theme 切换）
    # 这样 HTML 中只需在 <html> 上加 data-theme="dark" 即可切换
    return light + dark + base


__all__ = [
    'BRAIN_NAMES',
    'get_css',
    'get_base_css',
    'get_light_css',
    'get_dark_css',
    'get_javascript',
]
