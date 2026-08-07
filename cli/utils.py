#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLI 工具模块
=============
- 彩色输出（ANSI 颜色码，零依赖）
- 进度条
- ASCII 表格绘制
- 通用辅助函数
"""

import sys
import os
import shutil

# ===================== ANSI 颜色码 =====================

class Colors:
    """ANSI 颜色常量"""
    # 基础
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    UNDERLINE = "\033[4m"
    # 前景色
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    GRAY = "\033[90m"
    # 亮前景色
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    # 背景色
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"

    @staticmethod
    def supports_color() -> bool:
        """检查当前终端是否支持彩色输出"""
        if not sys.stdout.isatty():
            return False
        if os.environ.get("NO_COLOR"):
            return False
        if os.environ.get("TERM", "") == "dumb":
            return False
        return True


# 全局颜色开关：非 TTY 环境自动关闭颜色
_color_enabled = Colors.supports_color()


def set_color_enabled(enabled: bool):
    """手动设置颜色开关"""
    global _color_enabled
    _color_enabled = enabled


def c(text: str, color: str) -> str:
    """给文本添加颜色
    
    Args:
        text: 原始文本
        color: 颜色码（如 Colors.RED）
    
    Returns:
        带颜色的文本，或原始文本（若颜色被禁用）
    """
    if not _color_enabled:
        return text
    return f"{color}{text}{Colors.RESET}"


# 语义化颜色快捷函数
def color_high(text: str) -> str:
    """高危 - 红色"""
    return c(text, Colors.BRIGHT_RED)


def color_medium(text: str) -> str:
    """中危 - 黄色"""
    return c(text, Colors.YELLOW)


def color_low(text: str) -> str:
    """低危 - 蓝色"""
    return c(text, Colors.BRIGHT_BLUE)


def color_suggestion(text: str) -> str:
    """建议 - 灰色"""
    return c(text, Colors.GRAY)


def color_pass(text: str) -> str:
    """通过 - 绿色"""
    return c(text, Colors.BRIGHT_GREEN)


def color_info(text: str) -> str:
    """信息 - 青色"""
    return c(text, Colors.CYAN)


def color_dim(text: str) -> str:
    """暗淡 - 灰色"""
    return c(text, Colors.DIM)


def color_bold(text: str) -> str:
    """粗体"""
    return c(text, Colors.BOLD)


# ===================== 进度条 =====================

class ProgressPrinter:
    """逐模块扫描进度打印器（轻量，不依赖 tqdm）
    
    用法：
        pp = ProgressPrinter(total=10)
        for item in items:
            pp.update(item.name, status="running")
            # do work
            pp.update(item.name, status="done", detail="3 问题")
    """
    
    def __init__(self, total: int = 0, label: str = "扫描中"):
        self.total = total
        self.current = 0
        self.label = label
        self._last_line_len = 0
    
    def _write(self, text: str):
        """写一行（覆盖上一行的残留）"""
        # 清除上一行残留
        sys.stdout.write("\r" + " " * self._last_line_len + "\r")
        sys.stdout.write(text)
        sys.stdout.flush()
        self._last_line_len = len(text)
    
    def update(self, name: str, status: str = "running", detail: str = ""):
        """更新进度
        
        Args:
            name: 当前模块名
            status: running / done / skip / error
            detail: 附加信息
        """
        if status == "done":
            self.current += 1
        
        if self.total > 0:
            pct = self.current / self.total * 100
            bar_len = 20
            filled = int(bar_len * self.current / self.total)
            bar = "█" * filled + "░" * (bar_len - filled)
            
            if status == "running":
                prefix = color_info("▸")
            elif status == "done":
                prefix = color_pass("✓")
            elif status == "skip":
                prefix = color_dim("○")
            elif status == "error":
                prefix = color_high("✗")
            else:
                prefix = " "
            
            line = f"  {prefix} [{bar}] {self.current}/{self.total}  {name}"
            if detail:
                line += f"  {color_dim(detail)}"
            
            self._write(line)
        else:
            # 无总数模式
            if status == "running":
                prefix = color_info("▸")
            elif status == "done":
                prefix = color_pass("✓")
            elif status == "skip":
                prefix = color_dim("○")
            elif status == "error":
                prefix = color_high("✗")
            else:
                prefix = " "
            
            line = f"  {prefix} {name}"
            if detail:
                line += f"  {color_dim(detail)}"
            self._write(line)
    
    def finish(self, message: str = ""):
        """完成进度条，换行"""
        self._write("")
        sys.stdout.write("\r")
        if message:
            print(message)


# ===================== ASCII 表格 =====================

def ascii_table(rows: list, headers: list = None, align: list = None) -> str:
    """生成 ASCII 表格
    
    Args:
        rows: 数据行（列表的列表）
        headers: 表头列表
        align: 对齐方式列表，"left"/"center"/"right"，默认全左对齐
    
    Returns:
        表格字符串
    """
    if not rows:
        return ""
    
    # 统一数据格式
    all_rows = [headers] + rows if headers else rows
    str_rows = [[str(cell) for cell in row] for row in all_rows]
    
    # 计算每列最大宽度（考虑中文宽度，简化处理：每个中文字符算2）
    def _vis_len(s: str) -> int:
        n = 0
        for ch in s:
            if '\u4e00' <= ch <= '\u9fff' or '\u3000' <= ch <= '\u303f':
                n += 2
            else:
                n += 1
        return n
    
    col_count = len(str_rows[0])
    col_widths = [0] * col_count
    for row in str_rows:
        for i, cell in enumerate(row):
            w = _vis_len(cell)
            if w > col_widths[i]:
                col_widths[i] = w
    
    # 对齐方式
    if align is None:
        align = ["left"] * col_count
    
    def _pad_cell(text: str, width: int, align_type: str) -> str:
        text_w = _vis_len(text)
        pad = width - text_w
        if align_type == "right":
            return " " * pad + text
        elif align_type == "center":
            left = pad // 2
            right = pad - left
            return " " * left + text + " " * right
        else:  # left
            return text + " " * pad
    
    # 生成分隔线
    def _sep_line(char: str = "─") -> str:
        parts = [char * (w + 2) for w in col_widths]
        return "├" + "┼".join(parts) + "┤"
    
    def _top_line() -> str:
        parts = ["─" * (w + 2) for w in col_widths]
        return "┌" + "┬".join(parts) + "┐"
    
    def _bottom_line() -> str:
        parts = ["─" * (w + 2) for w in col_widths]
        return "└" + "┴".join(parts) + "┘"
    
    def _data_row(cells: list) -> str:
        parts = []
        for i, cell in enumerate(cells):
            parts.append(" " + _pad_cell(cell, col_widths[i], align[i]) + " ")
        return "│" + "│".join(parts) + "│"
    
    lines = [_top_line()]
    if headers:
        lines.append(_data_row(str_rows[0]))
        lines.append(_sep_line())
        for row in str_rows[1:]:
            lines.append(_data_row(row))
    else:
        for row in str_rows:
            lines.append(_data_row(row))
    lines.append(_bottom_line())
    
    return "\n".join(lines)


# ===================== 扫描结果汇总表 =====================

def render_summary_table(
    score: int,
    grade: str,
    scores: dict,
    issue_counts: dict,
    report_path: str,
) -> str:
    """渲染扫描结果汇总表
    
    Args:
        score: 综合评分 (0-100)
        grade: 等级（优秀/良好/需整改/严重/极严重）
        scores: 各维度得分 {"bug": int, "code_smell": int, "engineering_maturity": int}
        issue_counts: {"error": int, "warning": int, "info": int, "suggestion": int}
        report_path: 报告文件路径
    
    Returns:
        彩色表格字符串
    """
    lines = []
    
    # 评分颜色
    if score >= 90:
        score_color = color_pass
    elif score >= 70:
        score_color = color_info
    elif score >= 50:
        score_color = color_medium
    else:
        score_color = color_high
    
    # 等级颜色
    grade_color = score_color
    
    lines.append("")
    lines.append(color_bold("  📊 扫描结果汇总"))
    lines.append("")
    
    # 综合评分行
    score_str = f"  综合评分: {score_color(f'{score}/100')}  {c('●', Colors.BOLD)}{grade_color(f' {grade}')}"
    lines.append(score_str)
    lines.append("")
    
    # 各维度得分
    dim_rows = [
        ["Bug 维度", f"{scores.get('bug', 0)}/100"],
        ["Code Smell", f"{scores.get('code_smell', 0)}/100"],
        ["工程成熟度", f"{scores.get('engineering_maturity', 0)}/100"],
    ]
    dim_table = ascii_table(dim_rows, headers=["维度", "得分"], align=["left", "right"])
    # 给表格加缩进
    for line in dim_table.split("\n"):
        lines.append("  " + line)
    
    lines.append("")
    
    # 问题统计
    error_n = issue_counts.get("error", 0)
    warning_n = issue_counts.get("warning", 0)
    info_n = issue_counts.get("info", 0)
    suggestion_n = issue_counts.get("suggestion", 0)
    pass_n = issue_counts.get("pass", 0)
    total_n = error_n + warning_n + info_n + suggestion_n + pass_n
    
    stat_rows = [
        [color_high("🔴 高危"), str(error_n)],
        [color_medium("🟡 中危"), str(warning_n)],
        [color_low("🔵 低危"), str(info_n)],
        [color_suggestion("💡 建议"), str(suggestion_n)],
        [color_pass("✅ 通过"), str(pass_n)],
        [color_bold("📝 总计"), str(total_n)],
    ]
    stat_table = ascii_table(stat_rows, headers=["级别", "数量"], align=["left", "right"])
    for line in stat_table.split("\n"):
        lines.append("  " + line)
    
    lines.append("")
    lines.append(f"  📄 报告文件: {color_info(report_path)}")
    lines.append("")
    
    return "\n".join(lines)


# ===================== 规则列表渲染 =====================

def render_rules_table(rules: list, show_details: bool = False) -> str:
    """渲染规则列表表格
    
    Args:
        rules: Rule 对象列表
        show_details: 是否显示详细描述
    
    Returns:
        表格字符串
    """
    if not rules:
        return "  （无匹配规则）"
    
    # 级别着色
    def _level_text(level: str) -> str:
        if level in ("blocking", "error"):
            return color_high("高危")
        elif level in ("problem", "warning"):
            return color_medium("中危")
        elif level == "info":
            return color_low("低危")
        elif level == "suggestion":
            return color_suggestion("建议")
        return level
    
    rows = []
    for rule in rules:
        if show_details:
            rows.append([
                rule.id,
                rule.name,
                _level_text(rule.level),
                rule.category,
                rule.description[:40] + ("..." if len(rule.description) > 40 else ""),
            ])
        else:
            rows.append([
                rule.id,
                rule.name,
                _level_text(rule.level),
                rule.category,
                rule.source_dir or "-",
            ])
    
    if show_details:
        table = ascii_table(rows, headers=["ID", "名称", "级别", "类别", "描述"],
                            align=["left", "left", "center", "left", "left"])
    else:
        table = ascii_table(rows, headers=["ID", "名称", "级别", "类别", "来源"],
                            align=["left", "left", "center", "left", "left"])
    
    return table


# ===================== 版本号显示 =====================

def render_version(version: str, release_date: str, engine_version: str = "") -> str:
    """渲染版本信息"""
    lines = []
    lines.append(f"{color_bold('煋鉴 Xinpect')} v{version}")
    lines.append(f"  {color_dim('发布日期')}: {release_date}")
    if engine_version:
        lines.append(f"  {color_dim('引擎版本')}: {engine_version}")
    return "\n".join(lines)
