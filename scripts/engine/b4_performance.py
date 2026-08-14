# -*- coding: utf-8 -*-
"""
B4: 性能与可靠性分析引擎（免费版）
- 基础性能检测（N+1查询、循环内IO、sleep阻塞等）
- 【付费版】并发安全检测等深度性能检测
"""

import os
from typing import Dict, List


def scan(code_files: Dict[str, str], config: dict = None) -> List[Dict]:
    """B4 性能分析扫描入口（免费版）"""
    if config is None:
        config = {}

    issues = _custom_checks(code_files)
    return issues


def _custom_checks(code_files: Dict[str, str]) -> List[Dict]:
    """B4 专用手写检测逻辑"""
    issues = []

    for filepath, content in code_files.items():
        if not content:
            continue
        ext = os.path.splitext(filepath)[1].lower()
        lines = content.split("\n")

        # ===== Python 性能检测 =====
        if ext == ".py":
            issues.extend(_check_python_performance(filepath, content, lines))

        # ===== JS/TS 性能检测 =====
        elif ext in (".js", ".jsx", ".ts", ".tsx"):
            issues.extend(_check_js_performance(filepath, content, lines))

        # ===== SQL 性能检测 =====
        elif ext == ".sql":
            issues.extend(_check_sql_performance(filepath, content, lines))

        # ===== 通用性能检测 =====
        issues.extend(_check_general_performance(filepath, content, lines))

    return issues


def _check_python_performance(filepath: str, content: str, lines: List[str]) -> List[Dict]:
    issues = []

    # 循环中字符串拼接
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        import re as _re_py
        if _re_py.match(r"^[a-zA-Z_][a-zA-Z0-9_]*\[", stripped):
            continue
        if "join(" in stripped and "+=" in stripped:
            continue
        is_concat = False
        if _re_py.match('^[a-zA-Z_][a-zA-Z0-9_]*\\s*\\+=\\s*[fFrRbB]?[\\"\']', stripped):
            is_concat = True
        elif _re_py.match(r"^[a-zA-Z_][a-zA-Z0-9_]*\s*\+=\s*str\(", stripped):
            is_concat = True
        if not is_concat:
            continue
        line_indent = len(line) - len(line.lstrip())
        in_loop = False
        for j in range(i - 2, max(0, i - 20), -1):
            prev = lines[j - 1] if j > 0 else ""
            prev_stripped = prev.strip()
            if not prev_stripped or prev_stripped.startswith("#"):
                continue
            prev_indent = len(prev) - len(prev.lstrip())
            if prev_indent < line_indent:
                if prev_stripped.startswith("for ") and prev_stripped.endswith(":"):
                    in_loop = True
                break
        if not in_loop:
            continue
        issues.append({
            "check_id": "PERF-PY-001",
            "name": "循环中字符串拼接",
            "severity": "low",
            "file": filepath,
            "line": i,
            "message": "在循环中使用 += 拼接字符串，大数据量下可能存在性能问题",
            "suggestion": "使用列表收集字符串，最后用 join 一次性合并",
        })
        break  # 每文件只报一个
    # time.sleep 同步等待
    for i, line in enumerate(lines, 1):
        if "time.sleep(" in line and not line.strip().startswith("#"):
            issues.append({
                "check_id": "PERF-PY-002",
                "name": "同步阻塞等待",
                "severity": "low",
                "file": filepath,
                "line": i,
                "message": "使用 time.sleep() 同步阻塞等待，阻塞当前线程",
                "suggestion": "考虑使用 async/await 异步等待或事件驱动机制",
            })
            break

    # 全局变量过多
    global_count = sum(1 for line in lines if line.strip().startswith("global "))
    if global_count > 5:
        issues.append({
            "check_id": "PERF-PY-003",
            "name": "过多全局变量",
            "severity": "low",
            "file": filepath,
            "line": 1,
            "message": f"文件中有 {global_count} 个 global 声明，过多全局变量影响访问性能和可维护性",
            "suggestion": "使用函数参数传递或类属性封装状态",
        })

    # ============ 并发安全检测 ============
    # 并发安全检测为付费版功能

    return issues


def _check_js_performance(filepath: str, content: str, lines: List[str]) -> List[Dict]:
    issues = []

    # 同步 XHR
    if "XMLHttpRequest" in content and ".open(" in content:
        for i, line in enumerate(lines, 1):
            if ".open(" in line and "false" in line:
                issues.append({
                    "check_id": "PERF-JS-001",
                    "name": "同步XHR请求",
                    "severity": "high",
                    "file": filepath,
                    "line": i,
                    "message": "同步 XMLHttpRequest 会阻塞主线程，导致页面冻结",
                    "suggestion": "使用 fetch 或 axios 等异步请求方式",
                })
                break

    # 事件监听器未清理
    if "addEventListener" in content and "removeEventListener" not in content:
        issues.append({
            "check_id": "PERF-JS-002",
            "name": "未清理的事件监听器",
            "severity": "medium",
            "file": filepath,
            "line": 1,
            "message": "添加了事件监听器但未发现移除代码，可能导致内存泄漏",
            "suggestion": "在组件卸载/页面离开时调用 removeEventListener 清理",
        })

    # ============ 并发安全检测 ============
    # 并发安全检测为付费版功能

    return issues


# ==============================================================================
# 并发安全检测函数 (PERF-CONC- 前缀)
# ==============================================================================

def _check_sql_performance(filepath: str, content: str, lines: List[str]) -> List[Dict]:
    issues = []
    content_upper = content.upper()

    # SELECT *
    if "SELECT *" in content_upper:
        for i, line in enumerate(lines, 1):
            if "SELECT" in line.upper() and "*" in line:
                issues.append({
                    "check_id": "PERF-SQL-001",
                    "name": "SELECT * 查询",
                    "severity": "medium",
                    "file": filepath,
                    "line": i,
                    "message": "使用 SELECT * 查询所有列，浪费IO和内存，且可能导致索引失效",
                    "suggestion": "明确指定需要查询的列名",
                })
                break

    # 无 LIMIT 的查询
    if "SELECT" in content_upper and "LIMIT" not in content_upper:
        issues.append({
            "check_id": "PERF-SQL-002",
            "name": "查询缺少LIMIT",
            "severity": "low",
            "file": filepath,
            "line": 1,
            "message": "SELECT 查询未使用 LIMIT 限制返回行数，可能返回大量数据",
            "suggestion": "添加 LIMIT 子句限制返回行数，结合分页使用",
        })

    return issues


def _check_general_performance(filepath: str, content: str, lines: List[str]) -> List[Dict]:
    issues = []

    # 大文件
    if len(content) > 15000:
        issues.append({
            "check_id": "PERF-GEN-001",
            "name": "大文件",
            "severity": "low",
            "file": filepath,
            "line": 1,
            "message": f"文件较大（{len(content)}字符，{len(lines)}行），建议拆分",
            "suggestion": "将大文件拆分为多个职责单一的小模块",
        })

    # 超长行
    for i, line in enumerate(lines, 1):
        if len(line) > 200:
            issues.append({
                "check_id": "PERF-GEN-002",
                "name": "超长代码行",
                "severity": "info",
                "file": filepath,
                "line": i,
                "message": f"代码行过长（{len(line)}字符），影响可读性和维护性",
                "suggestion": "将长行拆分为多行，保持在 120 字符以内",
            })
            break

    return issues
