# -*- coding: utf-8 -*-
"""
B5: 可观测性引擎（免费版）
  一、日志规范（7条）
  二、指标监控（6条）

  三、链路追踪（3条）
  四、告警机制（2条）
  五、错误可排查性（2条）


共20条规则，全面覆盖可观测性五大维度。

设计原则：宁漏勿误。每条规则都尽量避免误报，
对不确定的场景宁可放过也不误报。
"""

import os
import re
from typing import Dict, List


# ==============================================================================
# 扫描入口
# ==============================================================================

def scan(code_files: Dict[str, str], config: dict = None) -> List[Dict]:
    """B5 可观测性扫描入口

    按语言分发到专用检测函数，最后汇总去重。
    """
    if config is None:
        config = {}

    issues = []

    for filepath, content in code_files.items():
        if not content:
            continue
        ext = os.path.splitext(filepath)[1].lower()
        lines = content.split("\n")

        # === Python 可观测性检测 ===
        if ext == ".py":
            issues.extend(_check_python_observability(filepath, content, lines))

        # === JS/TS 可观测性检测 ===
        elif ext in (".js", ".jsx", ".ts", ".tsx"):
            issues.extend(_check_js_observability(filepath, content, lines))

        # === 通用可观测性检测（所有文件）===
        issues.extend(_check_general_observability(filepath, content, lines, code_files))

    # === 项目级检测（跨文件分析）===
    issues.extend(_check_project_observability(code_files))

    # 去重
    seen = set()
    unique_issues = []
    for iss in issues:
        key = (iss["rule_id"], iss["file_path"], iss["line_no"])
        if key not in seen:
            seen.add(key)
            unique_issues.append(iss)

    return unique_issues


# ==============================================================================
# Python 可观测性检测
# ==============================================================================

def _check_python_observability(filepath: str, content: str, lines: List[str]) -> List[Dict]:
    """Python 可观测性检测（免费版：日志相关）"""
    issues = []
    issues.extend(_check_log_sensitive(filepath, content, lines))
    issues.extend(_check_log_level_abuse_py(filepath, content, lines))
    issues.extend(_check_log_meaningless(filepath, content, lines))
    issues.extend(_check_log_debug_on_py(filepath, content, lines))
    return issues
def _check_js_observability(filepath: str, content: str, lines: List[str]) -> List[Dict]:
    """JS/TS 可观测性检测（免费版：日志相关）"""
    issues = []
    issues.extend(_check_log_sensitive(filepath, content, lines))
    issues.extend(_check_log_level_abuse_js(filepath, content, lines))
    issues.extend(_check_log_debug_on_js(filepath, content, lines))
    return issues
def _check_general_observability(filepath: str, content: str, lines: List[str], code_files: Dict[str, str] = None) -> List[Dict]:
    """通用可观测性检测（免费版）"""
    issues = []
    return issues
def _check_project_observability(code_files: Dict[str, str]) -> List[Dict]:
    """项目级可观测性检测（免费版）"""
    issues = []
    return issues
def _check_log_no_stack_py(filepath: str, content: str, lines: List[str]) -> List[Dict]:
    """OBS-LOG-NO-STACK: except 块里只有 logger.error 没有 traceback/stack

    严格限制：必须确认在 except 块内，且有日志输出但没有堆栈信息，
    也没有重新抛出异常（raise）。
    """
    issues = []

    in_except = False
    except_indent = -1
    except_start = -1
    has_log = False
    has_traceback = False
    has_reraise = False

    def _report():
        if has_log and not has_traceback and not has_reraise:
            issues.append({
                "rule_id": "OBS-LOG-NO-STACK",
                "rule_name": "异常捕获只打message不打堆栈",
                "severity": "medium",
                "category": "observability-log",
                "file_path": filepath,
                "line_no": except_start,
                "message": "except 块中记录了错误日志但未输出堆栈信息，排查问题时无法定位错误来源",
                "suggestion": "使用 logger.exception() 自动记录堆栈，或 logger.error(msg, exc_info=True)",
            })

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # 进入 except 块
        if re.match(r'^\s*except\s+', line) and stripped.endswith(":"):
            _report()  # 保存上一个 except 块的检测结果
            in_except = True
            except_indent = len(line) - len(line.lstrip())
            except_start = i
            has_log = False
            has_traceback = False
            has_reraise = False
            continue

        if in_except:
            line_indent = len(line) - len(line.lstrip())
            # 退出 except 块（缩进回到 except 同级或更少）
            if line_indent <= except_indent:
                _report()
                in_except = False
                continue

            # 检查是否有日志
            if re.search(r'(?:logger|log|logging)\.(?:error|exception|warning|critical)\s*\(', stripped):
                has_log = True
                # logger.exception 自动带堆栈
                if "logger.exception" in stripped or "exc_info=True" in stripped:
                    has_traceback = True
            if "print(" in stripped and ("error" in stripped.lower() or "exception" in stripped.lower()):
                has_log = True

            # 检查是否有堆栈输出
            if re.search(r'(?:traceback|stacktrace|sys\.exc_info|print_exc|format_exc)', stripped, re.IGNORECASE):
                has_traceback = True

            # 检查是否重新抛出
            if stripped == "raise" or re.match(r'^raise\s+\w', stripped):
                has_reraise = True

    # 处理最后一个 except 块
    _report()

    return issues


def _check_log_no_stack_js(filepath: str, content: str, lines: List[str]) -> List[Dict]:
    """OBS-LOG-NO-STACK: catch 块里只有 console.error 没有 err.stack

    严格限制：必须确认在 catch 块内，且有日志输出但没有堆栈信息，
    也没有重新抛出（throw）。
    """
    issues = []

    in_catch = False
    brace_count = 0
    catch_start = -1
    has_log = False
    has_stack = False
    has_throw = False

    def _report():
        if has_log and not has_stack and not has_throw:
            issues.append({
                "rule_id": "OBS-LOG-NO-STACK",
                "rule_name": "异常捕获只打message不打堆栈",
                "severity": "medium",
                "category": "observability-log",
                "file_path": filepath,
                "line_no": catch_start,
                "message": "catch 块中记录了错误日志但未输出堆栈信息，排查问题时无法定位错误来源",
                "suggestion": "输出 error.stack 或使用结构化日志库自动记录堆栈",
            })

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue

        # 进入 catch 块
        if re.search(r'\bcatch\s*\(', stripped):
            _report()  # 保存上一个
            in_catch = True
            brace_count = stripped.count("{") - stripped.count("}")
            catch_start = i
            has_log = False
            has_stack = False
            has_throw = False
            continue

        if in_catch:
            brace_count += stripped.count("{") - stripped.count("}")

            if brace_count <= 0 and "}" in stripped:
                _report()
                in_catch = False
                continue

            # 检测日志
            if re.search(r'(?:console\.(?:error|warn|log)|logger\.(?:error|warn))\s*\(', stripped):
                has_log = True
                if re.search(r'\.stack\b', stripped):
                    has_stack = True

            # 检测堆栈输出
            if re.search(r'\.stack\b|stacktrace|Error\.captureStackTrace', stripped, re.IGNORECASE):
                has_stack = True

            # 检测重新抛出
            if re.match(r'^\s*throw\s', stripped):
                has_throw = True

    _report()

    return issues


# ------------------------------------------------------------------------------
# OBS-LOG-SENSITIVE: 日志泄露敏感信息 - high
# ------------------------------------------------------------------------------

def _check_log_sensitive(filepath: str, content: str, lines: List[str]) -> List[Dict]:
    """OBS-LOG-SENSITIVE: 日志输出中包含 password/token/secret 等敏感变量

    严格限制：必须是日志函数调用 + 变量名包含敏感关键词。
    排除：字符串中的敏感词（如提示语"请输入password"）、配置赋值语句。
    """
    issues = []

    # 日志函数模式
    log_patterns = [
        r'(?:logger|log|logging)\.\w+\s*\(',
        r'console\.(?:log|error|warn|info|debug)\s*\(',
        r'print\s*\(',
    ]

    # 敏感变量名模式（作为变量出现在日志参数中）
    sensitive_patterns = [
        (r'(?i)password\b', "password"),
        (r'(?i)\b(?:api[_-]?key|apikey)\b', "api_key"),
        (r'(?i)\b(?:secret|access[_-]?secret)\b', "secret"),
        (r'(?i)\b(?:token|access[_-]?token|auth[_-]?token)\b', "token"),
        (r'(?i)\b(?:private[_-]?key|sign[_-]?key)\b', "private_key"),
    ]

    log_re_list = [re.compile(p) for p in log_patterns]

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("#", "//")):
            continue
        if stripped.startswith(("import ", "from ", "require(")):
            continue

        # 先判断是不是日志输出行
        is_log_line = False
        for lr in log_re_list:
            if lr.search(stripped):
                is_log_line = True
                break
        if not is_log_line:
            continue

        # 跳过纯字符串字面量行
        if re.match(r'^["\'].*["\']\s*,?$', stripped):
            continue
        # 跳过纯字典 value 的情况
        if re.match(r'^\s*["\']?\w+["\']?\s*:\s*["\'].*["\']\s*,?$', stripped):
            continue

        for sens_pat, sens_name in sensitive_patterns:
            # 敏感词作为变量出现：后面跟着 + ) , 等操作符/分隔符
            if re.search(sens_pat + r'\s*[+),]', stripped):
                # 排除：纯赋值语句（password = xxx 不是日志泄露）
                if re.match(r'^\s*\w+\s*=\s*', stripped):
                    continue
                issues.append({
                    "rule_id": "OBS-LOG-SENSITIVE",
                    "rule_name": "日志泄露敏感信息",
                    "severity": "high",
                    "category": "observability-log",
                    "file_path": filepath,
                    "line_no": i,
                    "message": f"日志输出中包含敏感变量「{sens_name}」，可能导致敏感信息泄露",
                    "suggestion": "敏感信息禁止输出到日志，如需记录请脱敏后再输出（如只保留前4后4位）",
                })
                break  # 每行只报一次

    return issues


# ------------------------------------------------------------------------------
# OBS-LOG-LEVEL-ABUSE: 日志级别滥用 - low
# ------------------------------------------------------------------------------

def _check_log_level_abuse_py(filepath: str, content: str, lines: List[str]) -> List[Dict]:
    """OBS-LOG-LEVEL-ABUSE: try 正常路径打 error / except 异常路径打 info

    严格限制：必须明确在 try/except 块内，且确实有对应级别的日志。
    """
    issues = []

    in_try = False
    try_indent = -1
    try_start = -1
    try_has_error_log = False

    in_except = False
    except_indent = -1
    except_start = -1
    except_has_info_log = False

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        line_indent = len(line) - len(line.lstrip())

        # try 块开始
        if re.match(r'^\s*try\s*:\s*$', line):
            if in_try and try_has_error_log:
                issues.append({
                    "rule_id": "OBS-LOG-LEVEL-ABUSE",
                    "rule_name": "日志级别滥用-try块内打error",
                    "severity": "low",
                    "category": "observability-log",
                    "file_path": filepath,
                    "line_no": try_start,
                    "message": "try 正常流程中使用了 error 级别日志，正常业务不应产生错误级日志",
                    "suggestion": "正常流程使用 info/debug 级别，错误级别只用于真正的异常场景",
                })
            in_try = True
            try_indent = line_indent
            try_start = i
            try_has_error_log = False
            in_except = False
            continue

        # except 块开始
        if re.match(r'^\s*except\s+', line) and stripped.endswith(":"):
            if in_try and try_has_error_log:
                issues.append({
                    "rule_id": "OBS-LOG-LEVEL-ABUSE",
                    "rule_name": "日志级别滥用-try块内打error",
                    "severity": "low",
                    "category": "observability-log",
                    "file_path": filepath,
                    "line_no": try_start,
                    "message": "try 正常流程中使用了 error 级别日志，正常业务不应产生错误级日志",
                    "suggestion": "正常流程使用 info/debug 级别，错误级别只用于真正的异常场景",
                })
            if in_except and except_has_info_log:
                issues.append({
                    "rule_id": "OBS-LOG-LEVEL-ABUSE",
                    "rule_name": "日志级别滥用-except块内打info",
                    "severity": "low",
                    "category": "observability-log",
                    "file_path": filepath,
                    "line_no": except_start,
                    "message": "except 异常处理块中使用了 info 级别日志，异常场景应使用 error/warning 级别",
                    "suggestion": "异常场景使用 warning/error 级别，便于日志系统筛选告警",
                })
            in_try = False
            in_except = True
            except_indent = line_indent
            except_start = i
            except_has_info_log = False
            continue

        # 在 try 块中
        if in_try and line_indent > try_indent:
            if re.search(r'(?:logger|log)\.error\s*\(', stripped):
                try_has_error_log = True
            continue

        # 在 except 块中
        if in_except and line_indent > except_indent:
            if re.search(r'(?:logger|log|logging)\.info\s*\(', stripped):
                except_has_info_log = True
            continue

        # 退出块
        if stripped and line_indent <= try_indent and in_try:
            if try_has_error_log:
                issues.append({
                    "rule_id": "OBS-LOG-LEVEL-ABUSE",
                    "rule_name": "日志级别滥用-try块内打error",
                    "severity": "low",
                    "category": "observability-log",
                    "file_path": filepath,
                    "line_no": try_start,
                    "message": "try 正常流程中使用了 error 级别日志，正常业务不应产生错误级日志",
                    "suggestion": "正常流程使用 info/debug 级别，错误级别只用于真正的异常场景",
                })
            in_try = False

        if stripped and line_indent <= except_indent and in_except:
            if except_has_info_log:
                issues.append({
                    "rule_id": "OBS-LOG-LEVEL-ABUSE",
                    "rule_name": "日志级别滥用-except块内打info",
                    "severity": "low",
                    "category": "observability-log",
                    "file_path": filepath,
                    "line_no": except_start,
                    "message": "except 异常处理块中使用了 info 级别日志，异常场景应使用 error/warning 级别",
                    "suggestion": "异常场景使用 warning/error 级别，便于日志系统筛选告警",
                })
            in_except = False

    # 收尾：文件结束时如果还在 try/except 块中
    if in_try and try_has_error_log:
        issues.append({
            "rule_id": "OBS-LOG-LEVEL-ABUSE",
            "rule_name": "日志级别滥用-try块内打error",
            "severity": "low",
            "category": "observability-log",
            "file_path": filepath,
            "line_no": try_start,
            "message": "try 正常流程中使用了 error 级别日志，正常业务不应产生错误级日志",
            "suggestion": "正常流程使用 info/debug 级别，错误级别只用于真正的异常场景",
        })
    if in_except and except_has_info_log:
        issues.append({
            "rule_id": "OBS-LOG-LEVEL-ABUSE",
            "rule_name": "日志级别滥用-except块内打info",
            "severity": "low",
            "category": "observability-log",
            "file_path": filepath,
            "line_no": except_start,
            "message": "except 异常处理块中使用了 info 级别日志，异常场景应使用 error/warning 级别",
            "suggestion": "异常场景使用 warning/error 级别，便于日志系统筛选告警",
        })

    return issues


def _check_log_level_abuse_js(filepath: str, content: str, lines: List[str]) -> List[Dict]:
    """OBS-LOG-LEVEL-ABUSE: try 正常路径打 error / catch 异常路径打 info（JS 版）"""
    issues = []

    in_try = False
    try_brace = 0
    try_start = -1
    try_has_error_log = False

    in_catch = False
    catch_brace = 0
    catch_start = -1
    catch_has_info_log = False

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue

        # try 块
        if re.search(r'\btry\s*\{', stripped):
            if in_try and try_has_error_log:
                issues.append({
                    "rule_id": "OBS-LOG-LEVEL-ABUSE",
                    "rule_name": "日志级别滥用-try块内打error",
                    "severity": "low",
                    "category": "observability-log",
                    "file_path": filepath,
                    "line_no": try_start,
                    "message": "try 正常流程中使用了 error 级别日志，正常业务不应产生错误级日志",
                    "suggestion": "正常流程使用 info/debug 级别，错误级别只用于真正的异常场景",
                })
            in_try = True
            try_brace = stripped.count("{") - stripped.count("}")
            try_start = i
            try_has_error_log = False
            continue

        if in_try:
            try_brace += stripped.count("{") - stripped.count("}")
            if re.search(r'console\.error\s*\(|logger\.error\s*\(', stripped):
                try_has_error_log = True
            if try_brace <= 0:
                if try_has_error_log:
                    issues.append({
                        "rule_id": "OBS-LOG-LEVEL-ABUSE",
                        "rule_name": "日志级别滥用-try块内打error",
                        "severity": "low",
                        "category": "observability-log",
                        "file_path": filepath,
                        "line_no": try_start,
                        "message": "try 正常流程中使用了 error 级别日志，正常业务不应产生错误级日志",
                        "suggestion": "正常流程使用 info/debug 级别，错误级别只用于真正的异常场景",
                    })
                in_try = False
                continue

        # catch 块
        if re.search(r'\bcatch\s*\(', stripped):
            if in_catch and catch_has_info_log:
                issues.append({
                    "rule_id": "OBS-LOG-LEVEL-ABUSE",
                    "rule_name": "日志级别滥用-catch块内打info",
                    "severity": "low",
                    "category": "observability-log",
                    "file_path": filepath,
                    "line_no": catch_start,
                    "message": "catch 异常处理块中使用了 info 级别日志，异常场景应使用 error/warning 级别",
                    "suggestion": "异常场景使用 warning/error 级别，便于日志系统筛选告警",
                })
            in_catch = True
            catch_brace = stripped.count("{") - stripped.count("}")
            catch_start = i
            catch_has_info_log = False
            continue

        if in_catch:
            catch_brace += stripped.count("{") - stripped.count("}")
            if re.search(r'console\.info\s*\(|logger\.info\s*\(', stripped):
                catch_has_info_log = True
            if catch_brace <= 0 and "}" in stripped:
                if catch_has_info_log:
                    issues.append({
                        "rule_id": "OBS-LOG-LEVEL-ABUSE",
                        "rule_name": "日志级别滥用-catch块内打info",
                        "severity": "low",
                        "category": "observability-log",
                        "file_path": filepath,
                        "line_no": catch_start,
                        "message": "catch 异常处理块中使用了 info 级别日志，异常场景应使用 error/warning 级别",
                        "suggestion": "异常场景使用 warning/error 级别，便于日志系统筛选告警",
                    })
                in_catch = False
                continue

    return issues


# ------------------------------------------------------------------------------
# OBS-LOG-MEANINGLESS: 无意义调试日志 - low
# ------------------------------------------------------------------------------

def _check_log_meaningless(filepath: str, content: str, lines: List[str]) -> List[Dict]:
    """OBS-LOG-MEANINGLESS: console.log("111")、log.info("进来了") 等无意义调试日志

    严格限制：必须是纯字符串常量（无变量/表达式），且内容确实无意义。
    排除：有明确语义的生产日志。
    """
    issues = []

    # 无意义日志特征
    meaningless_words = [
        r'^进来了$', r'^到这里了$', r'^到这了$',
        r'^test$', r'^debug$', r'^xxx$', r'^aaa$',
        r'^hello$', r'^ok$', r'^okok$', r'^here$',
        r'^===.*===$', r'^---.*---$',
    ]
    meaningless_re_list = [re.compile(p, re.IGNORECASE) for p in meaningless_words]

    # 日志函数模式
    log_func_patterns = [
        r'console\.(?:log|debug)\s*\(',
        r'(?:logger|log|logging)\.(?:debug|info)\s*\(',
        r'print\s*\(',
    ]
    log_func_re_list = [re.compile(p, re.IGNORECASE) for p in log_func_patterns]

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("#", "//")):
            continue

        # 先判断是不是日志函数
        is_log_line = False
        for lfr in log_func_re_list:
            if lfr.search(stripped):
                is_log_line = True
                break
        if not is_log_line:
            continue

        # 提取日志函数的第一个参数：只有一个字符串参数
        m = re.search(
            r'(?:console\.log|console\.debug|logger\.(?:debug|info)|log\.(?:debug|info)|logging\.(?:debug|info)|print)'
            r'\s*\(\s*([\'"])([^\'"]*)\1\s*\)',
            stripped,
            re.IGNORECASE
        )
        if not m:
            continue

        log_content = m.group(2)

        # 检查是否为无意义内容
        is_meaningless = False
        for mwr in meaningless_re_list:
            if mwr.match(log_content):
                is_meaningless = True
                break

        # 额外判断：短纯数字/短纯字母/纯符号也视为调试
        if not is_meaningless and len(log_content) <= 5:
            if re.match(r'^[a-zA-Z]+$', log_content) and len(log_content) <= 3:
                is_meaningless = True
            elif re.match(r'^\d+$', log_content) and len(log_content) <= 4:
                is_meaningless = True
            elif re.match(r'^[=*\-#]+$', log_content):
                is_meaningless = True

        if is_meaningless:
            issues.append({
                "rule_id": "OBS-LOG-MEANINGLESS",
                "rule_name": "无意义调试日志",
                "severity": "low",
                "category": "observability-log",
                "file_path": filepath,
                "line_no": i,
                "message": f"检测到无意义的调试日志：\"{log_content}\"，应在提交前移除",
                "suggestion": "移除调试用的无意义日志，生产环境日志应包含有价值的业务信息",
            })

    return issues


# ------------------------------------------------------------------------------
# OBS-LOG-DEBUG-ON: 生产环境 debug 日志未关闭 - medium
# ------------------------------------------------------------------------------

def _check_log_debug_on_py(filepath: str, content: str, lines: List[str]) -> List[Dict]:
    """OBS-LOG-DEBUG-ON: 全局配置中 debug=True 或 logging.basicConfig(level=DEBUG)
    且没有环境变量判断

    严格限制：必须同时满足有 DEBUG 配置 + 没有被环境变量控制。
    """
    issues = []

    debug_line = -1

    # 1) logging.basicConfig 中的 DEBUG 检测
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "logging.basicConfig" in stripped:
            if re.search(r'level\s*=\s*(?:logging\.)?DEBUG', stripped):
                if not re.search(r'(?:os\.environ|os\.getenv|getenv\()', stripped):
                    debug_line = i
                break

    # 2) 全局 DEBUG = True / LOG_LEVEL = "DEBUG" 检测
    if debug_line == -1:
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            matched = False
            if re.match(r'^DEBUG\s*=\s*True\s*(?:#.*)?$', stripped):
                matched = True
            if re.match(r'^LOG_LEVEL\s*=\s*["\']DEBUG["\']\s*(?:#.*)?$', stripped, re.IGNORECASE):
                matched = True
            if not matched:
                continue

            # 检查前后 5 行是否有环境变量控制
            has_env_wrap = False
            for j in range(max(0, i - 6), min(len(lines), i + 5)):
                nearby = lines[j].strip()
                if re.search(r'(?:os\.environ|os\.getenv|getenv\()', nearby):
                    has_env_wrap = True
                    break
            if not has_env_wrap:
                debug_line = i
                break

    if debug_line > 0:
        issues.append({
            "rule_id": "OBS-LOG-DEBUG-ON",
            "rule_name": "生产环境DEBUG日志未关闭风险",
            "severity": "medium",
            "category": "observability-log",
            "file_path": filepath,
            "line_no": debug_line,
            "message": "日志级别配置为 DEBUG 且未通过环境变量控制，生产环境可能输出大量调试日志",
            "suggestion": "通过环境变量控制日志级别，生产环境默认使用 INFO 或 WARNING 级别",
        })

    return issues


def _check_log_debug_on_js(filepath: str, content: str, lines: List[str]) -> List[Dict]:
    """OBS-LOG-DEBUG-ON: 文件中有大量 console.log/debug 且没有 NODE_ENV 等判断

    严格限制：console 数量较多（>=8）、文件较大（>50行）、且没有环境判断。
    小文件/脚本文件忽略。
    """
    issues = []

    console_count = 0
    has_env_check = False

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue

        if re.search(r'console\.(?:log|debug)\s*\(', stripped):
            console_count += 1

        if re.search(r'(?:process\.env\.NODE_ENV|process\.env\[\s*["\']NODE_ENV["\'])', stripped):
            has_env_check = True

    if console_count >= 8 and not has_env_check and len(lines) > 50:
        first_line = 1
        for i, line in enumerate(lines, 1):
            if re.search(r'console\.(?:log|debug)\s*\(', line):
                first_line = i
                break
        issues.append({
            "rule_id": "OBS-LOG-DEBUG-ON",
            "rule_name": "生产环境调试日志未关闭风险",
            "severity": "medium",
            "category": "observability-log",
            "file_path": filepath,
            "line_no": first_line,
            "message": f"文件中有 {console_count} 处 console.log/debug 且未发现生产环境判断，生产环境可能泄露调试信息",
            "suggestion": "使用专业日志库，通过环境变量控制日志级别；生产环境移除 console 调试日志",
        })

    return issues


# ------------------------------------------------------------------------------
# OBS-LOG-STRING-CONCAT: 日志字符串拼接而非参数化 - low
# ------------------------------------------------------------------------------

def _check_log_string_concat_py(filepath: str, content: str, lines: List[str]) -> List[Dict]:
    """OBS-LOG-STRING-CONCAT: log.info("user " + name) 而非 log.info("user %s", name)

    严格限制：必须是日志函数 + 显式 + 拼接，且拼接的是变量。
    排除 f-string、% 格式化、.format() 调用。
    """
    issues = []

    log_methods = [
        r'logger\.(?:debug|info|warning|error|critical)\s*\(',
        r'logging\.(?:debug|info|warning|error|critical)\s*\(',
        r'log\.(?:debug|info|warning|error|critical)\s*\(',
    ]

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # 是否为日志函数调用
        is_log = False
        for lm in log_methods:
            if re.search(lm, stripped):
                is_log = True
                break
        if not is_log:
            continue

        # 检测字符串 + 变量的拼接
        has_concat = False
        # "xxx" + varname
        if re.search(r'["\'][^"\']*["\']\s*\+\s*[a-zA-Z_]\w*', stripped):
            has_concat = True
        # varname + "xxx"
        elif re.search(r'[a-zA-Z_]\w*\s*\+\s*["\'][^"\']*["\']', stripped):
            has_concat = True

        if not has_concat:
            continue

        # 排除：% 参数化（"user %s" % name）
        if re.search(r'["\'].+?["\']\s*%\s*[\(\w]', stripped):
            continue

        # 排除：.format() 调用
        if re.search(r'\.format\s*\(', stripped):
            continue

        issues.append({
            "rule_id": "OBS-LOG-STRING-CONCAT",
            "rule_name": "日志使用字符串拼接而非参数化",
            "severity": "low",
            "category": "observability-log",
            "file_path": filepath,
            "line_no": i,
            "message": "日志消息使用 + 字符串拼接，性能较差且无法被日志系统正确结构化处理",
            "suggestion": "使用参数化日志：logger.info(\"user %s\", name)，避免字符串拼接",
        })
        break  # 每文件只报一个

    return issues


# ------------------------------------------------------------------------------
# OBS-LOG-KEY-PATH: 关键业务路径无日志 - medium
# ------------------------------------------------------------------------------

def _check_log_key_path_py(filepath: str, content: str, lines: List[str]) -> List[Dict]:
    """OBS-LOG-KEY-PATH: 支付/登录/注册等关键函数体内没有任何 log/print

    严格限制：必须是明确的关键业务函数（函数名含 pay/login/register 等关键词），
    且函数体内完全没有日志输出。排除空实现/接口定义（只有 pass/docstring）。
    """
    issues = []

    key_func_keywords = [
        'pay', 'payment', 'refund', 'withdraw', 'transfer',
        'login', 'register', 'signup', 'sign_in',
    ]

    # 找所有函数定义
    func_pattern = re.compile(r'^([ \t]*)def\s+(\w+)\s*\(', re.MULTILINE)
    for m in func_pattern.finditer(content):
        func_indent_str = m.group(1)
        func_name = m.group(2)
        func_name_lower = func_name.lower()

        # 判断是否为关键业务函数
        is_key_func = any(kw in func_name_lower for kw in key_func_keywords)
        if not is_key_func:
            continue

        func_start_line = content[:m.start()].count("\n") + 1
        func_indent = len(func_indent_str)

        # 收集函数体
        func_body_lines = []
        in_body = False
        for j, line in enumerate(lines):
            line_idx = j + 1
            if line_idx < func_start_line:
                continue
            if line_idx == func_start_line:
                in_body = True
                continue
            if not in_body:
                continue

            stripped = line.strip()
            line_indent = len(line) - len(line.lstrip())

            # 遇到与 def 同级或更浅缩进的非空非注释非装饰器行，函数体结束
            if stripped and not stripped.startswith("#") and not stripped.startswith("@"):
                if line_indent <= func_indent:
                    break

            func_body_lines.append(line)

        func_body = "\n".join(func_body_lines)

        # 检查函数体内是否有日志
        has_log = bool(re.search(r'(?:logger|log|logging)\.\w+\s*\(', func_body))
        has_print = "print(" in func_body

        if not has_log and not has_print:
            # 排除：空实现（只有 pass/docstring）
            code_only = [l for l in func_body_lines
                         if l.strip() and not l.strip().startswith("#")
                         and not l.strip().startswith('"""') and not l.strip().startswith("'''")
                         and l.strip() != "pass"]
            if len(code_only) < 2:
                continue  # 空函数/接口定义，不报

            issues.append({
                "rule_id": "OBS-LOG-KEY-PATH",
                "rule_name": "关键业务路径无日志",
                "severity": "medium",
                "category": "observability-log",
                "file_path": filepath,
                "line_no": func_start_line,
                "message": f"关键业务函数「{func_name}」中没有任何日志输出，出问题时无法追踪执行路径",
                "suggestion": "在关键业务路径的入口、关键分支和出口处添加日志，便于问题排查和链路追踪",
            })

    return issues


def _check_log_key_path_js(filepath: str, content: str, lines: List[str]) -> List[Dict]:
    """OBS-LOG-KEY-PATH: JS 关键业务函数体内无日志"""
    issues = []

    key_func_keywords = [
        'pay', 'payment', 'refund', 'withdraw', 'transfer',
        'login', 'register', 'signup', 'signIn', 'sign_in',
    ]

    # JS 函数定义模式：function xxx(、const xxx = (、xxx: function(、async function xxx(
    func_patterns = [
        re.compile(r'^(?:async\s+)?function\s+(\w+)\s*\(', re.MULTILINE),
        re.compile(r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:function\s*\(|\()', re.MULTILINE),
    ]

    for func_pat in func_patterns:
        for m in func_pat.finditer(content):
            func_name = m.group(1)
            func_name_lower = func_name.lower()

            is_key_func = any(kw in func_name_lower for kw in key_func_keywords)
            if not is_key_func:
                continue

            func_start_line = content[:m.start()].count("\n") + 1

            # 简单统计函数体（从定义行开始数花括号）
            brace_count = 0
            func_body_lines = []
            started = False

            for j in range(func_start_line - 1, min(len(lines), func_start_line + 100)):
                line = lines[j]
                stripped = line.strip()

                if not started:
                    if "{" in stripped:
                        brace_count += stripped.count("{")
                        started = True
                    func_body_lines.append(line)
                    continue

                brace_count += stripped.count("{") - stripped.count("}")
                func_body_lines.append(line)

                if brace_count <= 0:
                    break

            func_body = "\n".join(func_body_lines)

            has_log = bool(re.search(r'console\.(?:log|error|warn|info)', func_body))
            has_logger = bool(re.search(r'logger\.(?:info|error|warn|debug)', func_body))

            if not has_log and not has_logger:
                # 排除空实现
                code_only = [l for l in func_body_lines
                             if l.strip() and not l.strip().startswith("//")
                             and l.strip() != "{}" and l.strip() != "{"]
                # 去掉只有 return 的
                real_code = [l for l in code_only
                             if not re.match(r'^\s*return\s*;?\s*$', l.strip())]
                if len(real_code) < 2:
                    continue

                issues.append({
                    "rule_id": "OBS-LOG-KEY-PATH",
                    "rule_name": "关键业务路径无日志",
                    "severity": "medium",
                    "category": "observability-log",
                    "file_path": filepath,
                    "line_no": func_start_line,
                    "message": f"关键业务函数「{func_name}」中没有任何日志输出，出问题时无法追踪执行路径",
                    "suggestion": "在关键业务路径的入口、关键分支和出口处添加日志，便于问题排查和链路追踪",
                })

    return issues


# ==============================================================================
# ============ 指标监控检测 ============
# ==============================================================================

# ------------------------------------------------------------------------------
# OBS-METRIC-HTTP-TIME: 外部 HTTP 调用无耗时统计 - medium
# ------------------------------------------------------------------------------

def _check_traceability(lines: List[str], content: str, filepath: str,
                        code_files: Dict[str, str] = None) -> List[Dict]:
    """
    链路追踪类检测总入口（3条规则）

    Args:
        lines: 当前文件按行分割的列表
        content: 当前文件完整内容
        filepath: 当前文件路径
        code_files: 全部代码文件字典（跨文件检测用，可选）

    Returns:
        List[Dict]: issue列表
    """
    issues = []
    ext = os.path.splitext(filepath)[1].lower()

    # --- OBS-TRACE-NO-ID: 跨服务调用无trace_id传递 ---
    if ext in (".py", ".js", ".jsx", ".ts", ".tsx"):
        issues.extend(_check_trace_no_id_single(lines, content, filepath, ext))

    # --- OBS-TRACE-ASYNC-LOST: 异步任务丢失trace_id ---
    if ext == ".py":
        issues.extend(_check_trace_async_lost_py(lines, content, filepath))

    # --- OBS-TRACE-LOG-NO-ID: 日志格式不含trace_id ---
    # 这是跨文件检测，在 code_files 可用时执行
    if code_files is not None:
        # 只在入口文件触发一次（第一个文件）
        if _is_first_file(code_files, filepath):
            issues.extend(_check_trace_log_no_id_global(code_files))

    return issues

