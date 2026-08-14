# -*- coding: utf-8 -*-
"""
B1: 语法/格式检查引擎（轻量版）
- Python 语法检查（ast.parse）
- 基本格式规范检查
- 基础编码规范

修复 v4.6.1 Bug 3: 'dict' object has no attribute '__name__'
原因：dict 类被直接当装饰器使用或传入需要 __name__ 的地方
修复：避免对 dict 类型调用 __name__，使用 type(x).__name__ 替代
"""

import os
import ast
import re
from typing import Dict, List


def scan(code_files: Dict[str, str], config: dict = None) -> List[Dict]:
    """B1 语法/格式检查入口"""
    if config is None:
        config = {}

    issues = []

    for filepath, content in code_files.items():
        if not content:
            continue
        ext = os.path.splitext(filepath)[1].lower()

        if ext == ".py":
            issues.extend(_check_python_syntax(filepath, content))
            issues.extend(_check_python_style(filepath, content))

        # 通用格式检查
        issues.extend(_check_general_format(filepath, content))

    return issues


def _check_python_syntax(filepath: str, content: str) -> List[Dict]:
    """Python 语法检查"""
    issues = []
    try:
        ast.parse(content, filename=filepath)
    except SyntaxError as e:
        issues.append({
            "check_id": "SYN-PY-001",
            "name": "Python语法错误",
            "severity": "blocker",
            "file": filepath,
            "line": e.lineno or 1,
            "message": f"语法错误: {e.msg}",
            "suggestion": "修复语法错误后再提交",
        })
    except Exception as e:
        issues.append({
            "check_id": "SYN-PY-002",
            "name": "解析异常",
            "severity": "high",
            "file": filepath,
            "line": 1,
            "message": f"代码解析异常: {type(e).__name__}: {str(e)[:100]}",
            "suggestion": "检查代码完整性和编码格式",
        })

    return issues


def _check_python_style(filepath: str, content: str) -> List[Dict]:
    """Python 基本风格/格式检查"""
    lines = content.split("\n")
    issues = []

    # Tab 缩进混合（只检查真正的代码缩进，排除字符串/注释/continuation）
    # 方法：检查每行的开头空白字符类型
    tab_indent_lines = 0
    space_indent_lines = 0
    in_multiline_str = False
    str_char = None
    for line in lines:
        stripped = line.strip()
        # 处理多行字符串状态
        if in_multiline_str:
            if str_char and (str_char * 3) in stripped:
                in_multiline_str = False
                str_char = None
            continue  # 字符串内的缩进不参与判断
        # 跳过空行和注释
        if not stripped or stripped.startswith("#"):
            continue
        # 检查三引号字符串开始
        triple_match = re.match(r'^\s*(\'\'\'|""")', line)
        if triple_match:
            quote = triple_match.group(1)[0]
            rest = line[triple_match.end():]
            if (quote * 3) not in rest:
                in_multiline_str = True
                str_char = quote
            continue
        # 检查行首缩进类型
        leading = line[:len(line) - len(line.lstrip())]
        if leading:
            if "\t" in leading:
                tab_indent_lines += 1
            elif " " in leading:
                space_indent_lines += 1

    if tab_indent_lines > 0 and space_indent_lines > 0:
        issues.append({
            "check_id": "SYN-PY-010",
            "name": "缩进方式混合",
            "severity": "medium",
            "file": filepath,
            "line": 1,
            "message": f"文件同时使用 Tab ({tab_indent_lines}行) 和空格 ({space_indent_lines}行) 缩进，可能导致 IndentationError",
            "suggestion": "统一使用 4 空格缩进（PEP 8 推荐）",
        })

    # 行尾空格
    trailing_space_count = sum(1 for line in lines if line.rstrip() != line and line.strip())
    if trailing_space_count > 10:
        issues.append({
            "check_id": "SYN-PY-011",
            "name": "行尾空格过多",
            "severity": "info",
            "file": filepath,
            "line": 1,
            "message": f"有 {trailing_space_count} 行存在行尾空格",
            "suggestion": "使用编辑器自动去除行尾空格，或配置 pre-commit hook",
        })

    # 文件末尾无空行
    if content and not content.endswith("\n"):
        issues.append({
            "check_id": "SYN-PY-012",
            "name": "文件末尾无换行",
            "severity": "info",
            "file": filepath,
            "line": len(lines),
            "message": "文件末尾缺少换行符",
            "suggestion": "在文件末尾添加一个空行（POSIX 规范）",
        })

    # 空行过多（连续空行 > 3）
    consecutive_blank = 0
    for i, line in enumerate(lines, 1):
        if not line.strip():
            consecutive_blank += 1
            if consecutive_blank > 3:
                issues.append({
                    "check_id": "SYN-PY-013",
                    "name": "过多连续空行",
                    "severity": "low",
                    "file": filepath,
                    "line": i,
                    "message": "连续空行超过 3 行，PEP 8 建议函数间空 2 行，方法间空 1 行",
                    "suggestion": "删除多余空行，保持代码紧凑",
                })
                break
        else:
            consecutive_blank = 0

    # 过长行
    long_lines = [i + 1 for i, line in enumerate(lines) if len(line) > 120 and not line.strip().startswith("#")]
    if len(long_lines) > 5:
        issues.append({
            "check_id": "SYN-PY-014",
            "name": "超长代码行",
            "severity": "low",
            "file": filepath,
            "line": long_lines[0],
            "message": f"有 {len(long_lines)} 行超过 120 字符",
            "suggestion": "PEP 8 建议每行不超过 79 字符，最长不超过 120",
        })

    # import 顺序检查（粗略）
    std_libs = {"os", "sys", "re", "json", "time", "datetime", "collections",
                "typing", "logging", "math", "random", "pathlib", "io", "abc",
                "enum", "subprocess", "threading", "hashlib", "copy", "shutil",
                "tempfile", "argparse", "unittest", "pytest"}

    imports = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            imports.append((i, stripped))

    if imports:
        # 检查是否有本地导入在第三方导入之前
        found_third_party = False
        for idx, imp_line in imports:
            module = imp_line.split()[1].split(".")[0]
            is_std = module in std_libs
            is_local = "." in imp_line.split()[1]
            if not is_std and not is_local:
                found_third_party = True
            elif is_local and found_third_party:
                # 本地导入在第三方之后，这是正确的
                pass
            # 简化：只检查 import 排序不做严格判断

    return issues


def _check_general_format(filepath: str, content: str) -> List[Dict]:
    """通用格式检查"""
    issues = []
    lines = content.split("\n")

    # 编码声明（Python 2 时代遗留，但检查 BOM）
    if content.startswith("\ufeff"):
        issues.append({
            "check_id": "SYN-GEN-001",
            "name": "BOM字符",
            "severity": "low",
            "file": filepath,
            "line": 1,
            "message": "文件以 BOM (U+FEFF) 开头，可能导致解析问题",
            "suggestion": "保存为 UTF-8 无 BOM 格式",
        })

    # 混合换行符
    crlf_count = content.count("\r\n")
    lf_count = content.count("\n") - crlf_count
    if crlf_count > 0 and lf_count > 0:
        issues.append({
            "check_id": "SYN-GEN-002",
            "name": "混合换行符",
            "severity": "low",
            "file": filepath,
            "line": 1,
            "message": f"文件混合使用 CRLF 和 LF 换行符（CRLF: {crlf_count}, LF: {lf_count}）",
            "suggestion": "统一使用 LF 换行符，配置 .gitattributes 自动转换",
        })

    return issues
