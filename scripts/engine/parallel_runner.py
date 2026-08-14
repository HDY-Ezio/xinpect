# -*- coding: utf-8 -*-
"""
并行扫描调度器 — 免费版
7 大检测引擎（B1/B2/B4/B5/B6/B7/B9），不含 AI语义分析(B3) 和 业务安全(B8)
ProcessPoolExecutor 多进程并行，错误隔离 + 超时熔断
"""

import time
import logging
from concurrent.futures import ProcessPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

# 大脑ID -> 模块名映射（子进程内import）
# 免费版 7 大检测引擎
BRAIN_MODULES = {
    "1": "engine.b1_syntax",
    "2": "engine.b2_security",
    "4": "engine.b4_performance",
    "5": "engine.b5_observability",
    "6": "engine.b6_code_quality",
    "7": "engine.b7_architecture",
    "9": "engine.b9_component_contracts",
}

# 免费版默认大脑列表（7个）
DEFAULT_FREE_BRAINS = ["1", "2", "4", "5", "6", "7", "9"]

BRAIN_NAMES = {
    "1": "语法格式",
    "2": "安全与依赖",
    "4": "性能与可靠性",
    "5": "可观测性",
    "6": "代码质量",
    "7": "架构与合规",
    "9": "专项检测",
}


def _scan_single_brain(brain_id: str, code_files: Dict[str, str], config: Dict) -> Dict:
    """单个大脑的扫描入口（子进程内执行）
    
    注意：此函数在子进程中执行，需要自己 import 模块
    """
    import importlib
    import time as _time
    from engine.scoring import calculate_weighted_score, generate_summary

    start = _time.time()
    brain_name = BRAIN_NAMES.get(brain_id, f"大脑{brain_id}")

    try:
        module_path = BRAIN_MODULES.get(brain_id)
        if not module_path:
            return {
                "score": 0,
                "status": "error",
                "issues": [],
                "summary": f"未知的大脑ID: {brain_id}",
                "elapsed": round(_time.time() - start, 3),
                "error": f"unknown brain_id: {brain_id}",
            }

        # 动态导入大脑模块
        module = importlib.import_module(module_path)
        scan_func = getattr(module, "scan", None)
        if not scan_func:
            return {
                "score": 0,
                "status": "error",
                "issues": [],
                "summary": f"大脑{brain_id}模块缺少scan函数",
                "elapsed": round(_time.time() - start, 3),
                "error": "no scan function",
            }

        # 执行扫描
        issues = scan_func(code_files, config)

        # 计算分数和摘要
        score = calculate_weighted_score(issues)
        summary = generate_summary(brain_id, brain_name, issues, score)
        status = "pass" if score >= 60 else "fail"

        elapsed = round(_time.time() - start, 3)
        return {
            "score": score,
            "status": status,
            "issues": issues,
            "summary": summary,
            "elapsed": elapsed,
            "error": None,
        }

    except Exception as e:
        elapsed = round(_time.time() - start, 3)
        logger.error(f"Brain {brain_id} scan error: {e}", exc_info=True)
        return {
            "score": None,  # None表示跳过，不计入总分
            "status": "error",
            "issues": [],
            "skipped": True,  # 标记该大脑未正常执行
            "summary": f"{brain_name}扫描异常（已跳过，不计入评分）: {type(e).__name__}",
            "elapsed": elapsed,
            "error": str(e)[:200],
        }


def run_brains_parallel(
    code_files: Dict[str, str],
    brain_ids: List[str] = None,
    config: Dict = None,
) -> Dict[str, Any]:
    """并行执行多个大脑的扫描

    Args:
        code_files: {file_path: file_content} 字典
        brain_ids: 要执行的大脑ID列表，如 ["1","2","3","4","5","6","7","8"]
        config: 配置字典，可选 timeout_per_brain（默认30秒）

    Returns:
        {
            "results": { "1": {...}, "2": {...}, ... },
            "total_elapsed": float
        }
    """
    if brain_ids is None:
        brain_ids = DEFAULT_FREE_BRAINS

    if config is None:
        config = {}

    timeout = config.get("timeout_per_brain", 30)
    max_workers = config.get("max_workers", min(4, len(brain_ids)))

    total_start = time.time()
    results: Dict[str, Dict] = {}

    # 过滤掉不存在的大脑
    valid_brains = [bid for bid in brain_ids if bid in BRAIN_MODULES]
    if not valid_brains:
        return {"results": {}, "total_elapsed": 0}

    # 单进程模式：只有一个大脑或 max_workers=1 时直接在当前进程执行
    if len(valid_brains) == 1 or max_workers == 1:
        for bid in valid_brains:
            results[bid] = _scan_single_brain(bid, code_files, config)
        total_elapsed = round(time.time() - total_start, 3)
        return {"results": results, "total_elapsed": total_elapsed}

    # 多进程并行
    # 注意：每个子进程独立加载规则，避免 pickle 传递大对象
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        future_map = {}
        for bid in valid_brains:
            future = executor.submit(_scan_single_brain, bid, code_files, config)
            future_map[future] = bid

        for future in future_map:
            bid = future_map[future]
            try:
                result = future.result(timeout=timeout)
                results[bid] = result
            except FutureTimeoutError:
                results[bid] = {
                    "score": None,
                    "status": "timeout",
                    "issues": [],
                    "skipped": True,
                    "summary": f"{BRAIN_NAMES.get(bid, f'大脑{bid}')}扫描超时（已跳过，不计入评分）",
                    "elapsed": timeout,
                    "error": f"timeout after {timeout}s",
                }
            except Exception as e:
                results[bid] = {
                    "score": None,
                    "status": "error",
                    "issues": [],
                    "skipped": True,
                    "summary": f"{BRAIN_NAMES.get(bid, f'大脑{bid}')}进程异常（已跳过，不计入评分）",
                    "elapsed": 0,
                    "error": str(e)[:200],
                }

    total_elapsed = round(time.time() - total_start, 3)
    return {"results": results, "total_elapsed": total_elapsed}
