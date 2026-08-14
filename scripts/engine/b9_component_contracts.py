# -*- coding: utf-8 -*-
"""
B9: 专项引擎（免费版）— 微信小程序基础检测

覆盖：
  1. WXML 基础规范检测
  2. WXSS 基础规范检测
  3. 小程序页面注册完整性基础检测

【免费版说明】
本引擎覆盖微信小程序基础规范检测。
深度专项检测（TDesign组件契组合规、跨文件连接完整性、事件绑定校验等）为付费版功能。
"""

import os
import re
from typing import Dict, List, Any, Optional


def scan(code_files: Dict[str, str], config: dict = None) -> List[Dict]:
    """B9 专项引擎扫描入口（免费版）"""
    if config is None:
        config = {}

    issues = []

    for filepath, content in code_files.items():
        if not content:
            continue
        ext = os.path.splitext(filepath)[1].lower()

        if ext == ".wxml":
            issues.extend(_check_wxml_basic(filepath, content))
        elif ext == ".wxss":
            issues.extend(_check_wxss_basic(filepath, content))
        elif ext == ".json":
            issues.extend(_check_json_basic(filepath, content))

    # 小程序页面完整性基础检测
    issues.extend(_check_mini_program_pages_basic(code_files))

    return issues


# ============================================================
# WXML 基础规范检测
# ============================================================

def _check_wxml_basic(filepath: str, content: str) -> List[Dict]:
    """WXML 基础规范检测"""
    issues = []
    lines = content.split("\n")

    # 1. 禁止使用的 HTML 标签
    forbidden_tags = ["<div", "<span", "<p>", "<br", "<img", "<a ",
                      "<ul", "<ol", "<li", "<table", "<form"]
    for i, line in enumerate(lines, 1):
        for tag in forbidden_tags:
            if tag in line.lower() and "<!--" not in line:
                tag_name = tag.strip("<").strip()
                issues.append({
                    "check_id": "MP-WXML-001",
                    "name": "禁止使用HTML标签(%s)" % tag_name,
                    "severity": "medium",
                    "file": filepath,
                    "line": i,
                    "message": "小程序 WXML 中不应使用 HTML 标签 %s，应使用小程序原生组件" % tag_name,
                    "suggestion": "使用 view 替代 div/p/span，使用 image 替代 img，使用 navigator 替代 a 标签",
                })
                break

    # 2. 检查 wx:for 是否有 wx:key
    for_match = re.compile(r'wx:for\s*=\s*["\']')
    key_match = re.compile(r'wx:key\s*=\s*["\']')

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if for_match.search(stripped):
            if not key_match.search(stripped):
                has_key = False
                for j in range(i - 1, min(i + 5, len(lines))):
                    if key_match.search(lines[j]):
                        has_key = True
                        break
                    if ">" in lines[j] and "wx:for" not in lines[j]:
                        break
                if not has_key:
                    issues.append({
                        "check_id": "MP-WXML-002",
                        "name": "wx:for缺少wx:key",
                        "severity": "medium",
                        "file": filepath,
                        "line": i,
                        "message": "使用 wx:for 时未指定 wx:key，列表重渲染时性能较差",
                        "suggestion": '为 wx:for 添加 wx:key 属性，提升列表渲染性能；简单列表可用 wx:key="*this"',
                    })

    # 3. 模板表达式空格规范
    for i, line in enumerate(lines, 1):
        if "{{" in line and "}}" in line:
            if re.search(r'\{\{\s\s+', line) or re.search(r'\s\s+\}\}', line):
                issues.append({
                    "check_id": "MP-WXML-003",
                    "name": "模板表达式空格不规范",
                    "severity": "low",
                    "file": filepath,
                    "line": i,
                    "message": "{{ }} 表达式内空格不规范，建议 {{ 变量 }} 格式",
                    "suggestion": "模板表达式使用 {{ variable }} 格式，保持前后各一个空格",
                })
                break

    return issues


# ============================================================
# WXSS 基础规范检测
# ============================================================

def _check_wxss_basic(filepath: str, content: str) -> List[Dict]:
    """WXSS 基础规范检测"""
    issues = []
    lines = content.split("\n")

    # 1. 禁止使用的 CSS 属性/选择器
    forbidden_props = [
        (":hover", ":hover 伪类（小程序不支持）"),
        ("::before", "::before 伪元素（小程序支持有限）"),
        ("::after", "::after 伪元素（小程序支持有限）"),
    ]

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("/*") or stripped.startswith("*") or stripped.startswith("//"):
            continue
        for prop, desc in forbidden_props:
            if prop in stripped:
                issues.append({
                    "check_id": "MP-WXSS-001",
                    "name": "不建议使用的CSS(%s)" % desc,
                    "severity": "low",
                    "file": filepath,
                    "line": i,
                    "message": "检测到 %s，在小程序中兼容性或体验可能有问题" % desc,
                    "suggestion": "查阅微信小程序文档，确认该CSS特性的支持情况，考虑替代方案",
                })
                break

    # 2. 通配符选择器
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("*") and ("{" in stripped or stripped == "*"):
            issues.append({
                "check_id": "MP-WXSS-002",
                "name": "通配符选择器",
                "severity": "medium",
                "file": filepath,
                "line": i,
                "message": "使用 * 通配符选择器，性能较差且可能影响非预期元素",
                "suggestion": "避免使用 * 选择器，明确指定需要设置样式的元素或类",
            })
            break

    # 3. 未使用 rpx 自适应单位
    px_count = sum(1 for line in lines if re.search(r'\b\d+px', line))
    rpx_count = sum(1 for line in lines if re.search(r'\b\d+rpx', line))
    if px_count > 10 and rpx_count == 0:
        issues.append({
            "check_id": "MP-WXSS-003",
            "name": "未使用rpx自适应单位",
            "severity": "low",
            "file": filepath,
            "line": 1,
            "message": "WXSS 中全部使用 px 固定单位，未使用 rpx 自适应单位",
            "suggestion": "布局类尺寸使用 rpx 自适应单位，字体和边框等可使用 px",
        })

    return issues


# ============================================================
# JSON 配置基础检测
# ============================================================

def _check_json_basic(filepath: str, content: str) -> List[Dict]:
    """JSON 配置基础检测"""
    issues = []

    try:
        import json as _json
        _json.loads(content)
    except _json.JSONDecodeError as e:
        issues.append({
            "check_id": "MP-JSON-001",
            "name": "JSON格式错误",
            "severity": "blocker",
            "file": filepath,
            "line": e.lineno,
            "message": "JSON 解析失败: %s" % e.msg,
            "suggestion": "修复 JSON 格式错误，确保配置文件语法正确",
        })

    return issues


# ============================================================
# 小程序页面完整性基础检测
# ============================================================

def _check_mini_program_pages_basic(code_files: Dict[str, str]) -> List[Dict]:
    """小程序页面完整性基础检测"""
    issues = []

    # 找 app.json
    app_json = None
    for filepath in code_files:
        basename = os.path.basename(filepath)
        if basename == "app.json":
            app_json = filepath
            break

    if not app_json:
        return issues

    try:
        import json as _json
        app_data = _json.loads(code_files[app_json])
    except Exception:
        return issues

    pages = app_data.get("pages", [])
    if not pages:
        return issues

    # 检查每个页面的4个文件是否齐全
    for page_path in pages:
        needed_exts = [".wxml", ".wxss", ".js", ".json"]
        missing = []
        for ext in needed_exts:
            full_path = page_path + ext
            if full_path not in code_files and "./" + full_path not in code_files:
                missing.append(ext)
        if missing:
            report_file = page_path + ".wxml"
            if report_file not in code_files:
                report_file = app_json
            issues.append({
                "check_id": "MP-PAGE-001",
                "name": "页面文件不完整",
                "severity": "high",
                "file": report_file,
                "line": 1,
                "message": "页面 %s 缺少文件: %s" % (page_path, ", ".join(missing)),
                "suggestion": "小程序页面应包含 .wxml/.wxss/.js/.json 四个文件，补全缺失文件",
            })

    return issues
