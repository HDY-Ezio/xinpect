# -*- coding: utf-8 -*-
"""
煋鉴代码质检 — 扫描入口（Skill 调用封装）

使用方式：
    from scripts.scan import scan_code

    result = scan_code({
        "main.py": "import os\nprint('hello')",
        "utils.py": "def foo():\n    pass",
    })

返回格式：
    {
        "total_score": 85,
        "status": "pass",
        "total_elapsed": 2.5,
        "brain_count": 7,
        "brains": {
            "1": {"name": "语法格式", "score": 100, "status": "pass", ...},
            ...
        },
        "all_issues": [...],
        "version": "5.9.0",
        "edition": "free",
    }
"""

import os
import sys
import time
from typing import Dict, List, Any, Optional

# 确保 engine 模块可以被导入
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from engine.parallel_runner import run_brains_parallel, DEFAULT_FREE_BRAINS, BRAIN_NAMES
from engine.scoring import calculate_overall_score

VERSION = "5.9.0"
EDITION = "free"
PRODUCT_NAME = "煋鉴代码质检"
DEVELOPER = "煋旺智能"
OFFICIAL_SITE = "xinpect.xingwangzhineng.com"


def scan_code(
    code_files: Dict[str, str],
    brain_ids: Optional[List[str]] = None,
    config: Optional[Dict] = None,
) -> Dict[str, Any]:
    """代码质量扫描入口

    Args:
        code_files: {file_path: file_content} 字典
        brain_ids: 指定运行的大脑ID列表，None表示全部免费版大脑
        config: 配置字典
            - timeout_per_brain: 每个大脑超时时间，默认30秒
            - max_workers: 最大并行进程数，默认4

    Returns:
        扫描结果字典
    """
    if not code_files:
        return {
            "total_score": 0,
            "status": "error",
            "total_elapsed": 0,
            "brain_count": 0,
            "brains": {},
            "all_issues": [],
            "version": VERSION,
            "edition": EDITION,
            "error": "No code files provided",
        }

    if config is None:
        config = {}

    if brain_ids is None:
        brain_ids = DEFAULT_FREE_BRAINS

    start_time = time.time()

    # 执行并行扫描
    result = run_brains_parallel(code_files, brain_ids, config)

    # 计算整体评分
    overall = calculate_overall_score(result["results"])

    # 组装返回结果
    brains = {}
    all_issues = []
    for bid, brain_result in result["results"].items():
        brain_info = {
            "id": bid,
            "name": BRAIN_NAMES.get(bid, f"大脑{bid}"),
            "score": brain_result.get("score"),
            "status": brain_result.get("status", "unknown"),
            "issues": brain_result.get("issues", []),
            "summary": brain_result.get("summary", ""),
            "elapsed": brain_result.get("elapsed", 0),
        }
        if brain_result.get("skipped"):
            brain_info["skipped"] = True
            brain_info["error"] = brain_result.get("error", "")
        brains[bid] = brain_info
        all_issues.extend(brain_result.get("issues", []))

    total_elapsed = round(time.time() - start_time, 3)
    total_score = overall["total_score"]

    return {
        "total_score": total_score,
        "status": "pass" if total_score >= 60 else "fail",
        "total_elapsed": total_elapsed,
        "brain_count": overall["active_brains"],
        "skipped_brains": overall["skipped_brains"],
        "brains": brains,
        "all_issues": all_issues,
        "total_issues": len(all_issues),
        "version": VERSION,
        "edition": EDITION,
        "product": PRODUCT_NAME,
        "developer": DEVELOPER,
        "official_site": OFFICIAL_SITE,
    }


def scan_file(file_path: str, config: Optional[Dict] = None) -> Dict[str, Any]:
    """扫描单个文件"""
    with open(file_path, "r", encoding="utf-8-sig") as f:
        content = f.read()
    return scan_code({file_path: content}, config=config)


def scan_directory(dir_path: str, config: Optional[Dict] = None) -> Dict[str, Any]:
    """扫描整个目录"""
    code_files = {}
    skip_dirs = {"__pycache__", ".git", "node_modules", ".venv", "venv", "dist", "build", ".idea", ".vscode"}
    code_exts = {".py", ".js", ".ts", ".jsx", ".tsx", ".wxml", ".wxss", ".json",
                 ".sql", ".java", ".go", ".rb", ".php", ".yaml", ".yml", ".env",
                 ".css", ".html", ".properties", ".conf"}

    for root, dirs, files in os.walk(dir_path):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for fname in files:
            fpath = os.path.join(root, fname)
            ext = os.path.splitext(fname)[1].lower()
            if ext in code_exts:
                try:
                    with open(fpath, "r", encoding="utf-8-sig") as f:
                        content = f.read()
                    rel_path = os.path.relpath(fpath, dir_path)
                    code_files[rel_path] = content
                except (UnicodeDecodeError, IOError):
                    continue

    return scan_code(code_files, config=config)
