# -*- coding: utf-8 -*-
"""
通用规则扫描工具（免费版简化）
提供字符串处理、严重级别映射等通用工具函数
"""

import re
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)

SEVERITY_MAP = {
    "S1": "blocker", "S2": "high", "S3": "medium", "S4": "low",
    "critical": "critical", "blocker": "blocker", "high": "high",
    "medium": "medium", "low": "low", "warning": "medium",
    "error": "high", "info": "low",
}


def strip_string_content(line: str) -> str:
    """剥离行内字符串内容，用空格替换，避免正则匹配到字符串字面量。
    支持单引号、双引号，处理转义字符。"""
    result = []
    i = 0
    in_str = False
    str_char = None
    while i < len(line):
        ch = line[i]
        if not in_str:
            if ch == '"' or ch == "'":
                if i + 2 < len(line) and line[i:i+3] == ch * 3:
                    return line
                in_str = True
                str_char = ch
                result.append(ch)
            else:
                result.append(ch)
            i += 1
        else:
            if ch == '\\' and i + 1 < len(line):
                result.append('  ')
                i += 2
                continue
            if ch == str_char:
                in_str = False
                str_char = None
                result.append(ch)
            else:
                result.append(' ')
            i += 1
    return ''.join(result)
