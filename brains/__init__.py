# -*- coding: utf-8 -*-
"""
多引擎协同架构 - 多大脑注册表
煋旺智能 QA Code Expert v2.8.0 (章鱼架构整合版)

七大脑协同（v2.8.0 最终确认版）：
- Brain1: 规则引擎（含UI/UX规则）[免费]
- Brain2: 安全漏洞扫描引擎（含分发安全审计）[免费]
- Brain3: AI语义分析引擎（静态规则兜底+LLM增强）[免费]
- Brain4: 性能分析引擎 [专业版]
- Brain5: 依赖与配置审计引擎 [专业版]
- Brain6: 代码质量引擎 [专业版]
- Brain7: 架构合规检查引擎 [专业版]

免费版 = Brain 1 + 2 + 3（规则模式）（纯规则引擎，零成本）
专业版 = Brain 1-8（全部大脑 + Brain3 AI模式 + AI增强）

v2.0.0 章鱼架构整合新增：
- [模块1] 契约校验：大脑执行后自动校验输出质量
- [模块5] 消息总线：大脑生命周期事件发布
- [模块7] 自适应路由：level="auto" 自动选最优引擎组合
"""

import time
import concurrent.futures
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Tuple


@dataclass
class BrainIssue:
    """统一的审查发现问题"""
    check_id: str
    name: str
    severity: str  # blocker/high/medium/low
    file: str
    line: int
    message: str
    suggestion: str = ""
    cwe_id: str = ""  # CWE编号（Brain2安全引擎使用）

    def to_dict(self) -> Dict:
        result = {
            "check_id": self.check_id,
            "name": self.name,
            "severity": self.severity,
            "file": self.file,
            "line": self.line,
            "message": self.message,
            "suggestion": self.suggestion,
        }
        # 仅在Brain2等安全引擎中输出cwe_id
        if self.cwe_id:
            result["cwe_id"] = self.cwe_id
        return result


@dataclass
class BrainResult:
    """统一的审查结果"""
    brain_name: str
    status: str  # pass/fail/skip/error
    score: int   # 0-100
    issues: List[BrainIssue] = field(default_factory=list)
    summary: str = ""
    elapsed: float = 0.0  # 执行耗时（秒）

    def to_dict(self) -> Dict:
        return {
            "brain_name": self.brain_name,
            "status": self.status,
            "score": self.score,
            "issues": [i.to_dict() for i in self.issues],
            "summary": self.summary,
            "elapsed": round(self.elapsed, 3),
        }


class BaseBrain:
    """大脑基类 - 所有审查大脑的统一接口"""
    name: str = "base"
    description: str = "基础大脑"
    priority: int = 50
    cost_level: str = "cheap"

    def scan(self, project_path: str, config: dict) -> BrainResult:
        """执行扫描，返回统一格式结果"""
        raise NotImplementedError


# ===== 大脑注册表 =====
_BRAIN_REGISTRY: Dict[str, type] = {}

_BRAIN_METADATA: Dict[str, Dict[str, Any]] = {
    "1": {"name": "brain1_rule_engine", "priority": 100, "cost_level": "cheap",
          "desc": "规则引擎（零Token）"},
    "2": {"name": "brain2_security_engine", "priority": 85, "cost_level": "cheap",
          "desc": "安全漏洞扫描引擎（OWASP/CWE）"},
    "3": {"name": "brain3_ai_engine", "priority": 10, "cost_level": "cheap",
          "desc": "AI语义分析引擎（静态规则兜底）"},
}

# 分级执行模式（v2.0 新增 auto 级别）
LEVEL_BRAINS = {
    "quick": ["1"],
    "standard": ["1", "2", "3"],
    "full": ["1", "2", "3"],
    "auto": ["1", "2", "3"],  # lite版固定为B1~B3
}


def register_brain(brain_id: str):
    """装饰器：注册大脑到注册表"""
    def decorator(cls):
        _BRAIN_REGISTRY[brain_id] = cls
        meta = _BRAIN_METADATA.get(brain_id, {})
        if meta and not hasattr(cls, '_meta_set'):
            if not hasattr(cls, 'priority') or cls.priority == 50:
                cls.priority = meta.get("priority", 50)
            if not hasattr(cls, 'cost_level') or cls.cost_level == "cheap":
                cls.cost_level = meta.get("cost_level", "cheap")
        return cls
    return decorator


def get_brain(brain_id: str) -> Optional[BaseBrain]:
    """根据ID获取大脑实例"""
    cls = _BRAIN_REGISTRY.get(str(brain_id))
    if cls is None:
        return None
    try:
        return cls()
    except Exception as e:  # noqa: broad exception handling
        return None


def list_brains() -> Dict[str, str]:
    """列出所有已注册的大脑"""
    result = {}
    for bid, cls in _BRAIN_REGISTRY.items():
        instance = cls()
        meta = _BRAIN_METADATA.get(bid, {})
        result[bid] = {
            "name": instance.name,
            "description": instance.description,
            "priority": meta.get("priority", instance.priority),
            "cost_level": meta.get("cost_level", instance.cost_level),
        }
    return result


# ===== 章鱼架构v2.0: 辅助函数 =====

def _find_brain_id_by_name(brain_name: str) -> Optional[str]:
    """
    从 brain_name 反查 brain_id（章鱼架构v2.0新增）。
    用于契约校验、消息总线等需要 brain_id 的场景。
    """
    # 先从元数据查
    for bid, meta in _BRAIN_METADATA.items():
        if meta.get("name") == brain_name:
            return bid
    # 再从注册表查
    for bid, cls in _BRAIN_REGISTRY.items():
        try:
            inst = cls()
            if inst.name == brain_name:
                return bid
        except Exception as e:  # noqa: broad exception handling
            pass
    return None


def get_brains_by_level(level: str, config: dict = None) -> List[str]:
    """
    根据执行级别获取对应的大脑ID列表

    Args:
        level: 执行级别 - 'quick' | 'standard' | 'full' | 'auto'
        config: 配置字典（auto模式需要）

    Returns:
        大脑ID列表，按优先级降序排列（已通过 License 门禁过滤）
    """
    # ===== 章鱼架构v2.0 [模块7]: 自适应路由 =====
    if level == "auto":
        try:
            import sys, os
            core_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "core")
            if core_dir not in sys.path:
                sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from core.adaptive_router import AdaptiveRouter
            router = AdaptiveRouter()
            task_type = (config or {}).get("task_type", "full")
            file_count = (config or {}).get("_file_count", 0)
            plan = router.route(task_type=task_type, file_count=file_count)
            if plan.selected_brains:
                # License 门禁过滤
                allowed, _denied = _license_filter(plan.selected_brains, config)
                return allowed
        except (ImportError, Exception):  # noqa: intentional empty handler
            pass
        # 降级到 standard
        level = "standard"

    brain_ids = LEVEL_BRAINS.get(level, LEVEL_BRAINS["standard"])
    brain_ids_sorted = sorted(
        brain_ids,
        key=lambda bid: _BRAIN_METADATA.get(bid, {}).get("priority", 0),
        reverse=True,
    )

    # ===== 门房 License 门禁过滤 =====
    allowed, _denied = _license_filter(brain_ids_sorted, config)
    return allowed


def _license_filter(brain_ids: List[str], config: dict = None) -> tuple:
    """
    Lite版本无 License 门禁，全部放行。
    """
    return brain_ids, []


def run_brains_parallel(
    brain_ids: List[str],
    project_path: str,
    config: dict = None,
    max_workers: int = 4,
) -> Tuple[Dict[str, BrainResult], Dict[str, float]]:
    """
    并行执行多个大脑

    v2.0增强：
    - [模块5] 消息总线：发布大脑生命周期事件
    - [模块1] 契约校验：执行后校验输出质量
    """
    ensure_brains_loaded()

    if config is None:
        config = {}

    results: Dict[str, BrainResult] = {}
    timings: Dict[str, float] = {}

    # ===== 章鱼架构v2.0 [模块5]: 消息总线 - 审查开始事件 =====
    _bus = None
    try:
        from core.message_bus import get_message_bus, Channels, Message
        _bus = get_message_bus()
        _bus.publish(Channels.REVIEW_START, Message(
            sender="orchestrator",
            data={"brain_ids": brain_ids, "project_path": project_path},
        ))
    except (ImportError, Exception):  # noqa: intentional empty handler
        pass

    # 如果只有一个大脑，直接串行执行
    if len(brain_ids) <= 1:
        for bid in brain_ids:
            brain = get_brain(bid)
            if brain is None:
                results[f"unknown_{bid}"] = BrainResult(
                    brain_name=f"unknown_{bid}",
                    status="error", score=0,
                    summary=f"未知大脑ID: {bid}",
                )
                continue

            # 消息总线: 大脑开始
            if _bus:
                try:
                    from core.message_bus import Channels, Message
                    _bus.publish(Channels.BRAIN_START, Message(
                        sender=f"brain_{bid}",
                        data={"project_path": project_path},
                    ))
                except Exception as e:  # noqa: broad exception handling
                    pass

            start = time.time()
            result = brain.scan(project_path, config)
            elapsed = time.time() - start
            result.elapsed = elapsed
            results[brain.name] = result
            timings[brain.name] = elapsed

            # 消息总线: 大脑完成
            if _bus:
                try:
                    from core.message_bus import Channels, Message
                    _bus.publish(Channels.BRAIN_COMPLETE, Message(
                        sender=f"brain_{bid}",
                        data={"issues": len(result.issues), "score": result.score, "elapsed": elapsed},
                    ))
                except Exception as e:  # noqa: broad exception handling
                    pass

        # ===== 章鱼架构v2.0 [模块1]: 契约校验 =====
        _apply_contract_validation(results)
        return results, timings

    # 多线程并行执行
    def _run_single_brain(bid: str) -> Tuple[str, BrainResult, float]:
        """在线程中执行单个大脑"""
        brain = get_brain(bid)
        if brain is None:
            return (
                f"unknown_{bid}",
                BrainResult(
                    brain_name=f"unknown_{bid}",
                    status="error", score=0,
                    summary=f"未知大脑ID: {bid}",
                ),
                0.0,
            )

        # 消息总线: 大脑开始
        if _bus:
            try:
                from core.message_bus import Channels, Message
                _bus.publish(Channels.BRAIN_START, Message(
                    sender=f"brain_{bid}",
                    data={"project_path": project_path},
                ))
            except Exception as e:  # noqa: broad exception handling
                pass

        start = time.time()
        try:
            result = brain.scan(project_path, config)
        except Exception as e:  # noqa: intentional catch-all
            result = BrainResult(
                brain_name=brain.name,
                status="error", score=0,
                summary=f"大脑执行异常: {e}",
            )
        elapsed = time.time() - start
        result.elapsed = elapsed

        # 消息总线: 大脑完成/出错
        if _bus:
            try:
                from core.message_bus import Channels, Message
                channel = Channels.BRAIN_ERROR if result.status == "error" else Channels.BRAIN_COMPLETE
                _bus.publish(channel, Message(
                    sender=f"brain_{bid}",
                    data={"issues": len(result.issues), "score": result.score, "elapsed": elapsed},
                ))
            except Exception as e:  # noqa: broad exception handling
                pass

        return (brain.name, result, elapsed)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_run_single_brain, bid): bid
            for bid in brain_ids
        }
        for future in concurrent.futures.as_completed(futures):
            try:
                brain_name, result, elapsed = future.result()
                results[brain_name] = result
                timings[brain_name] = elapsed
            except Exception as e:  # noqa: intentional catch-all
                bid = futures[future]
                results[f"error_{bid}"] = BrainResult(
                    brain_name=f"error_{bid}",
                    status="error", score=0,
                    summary=f"并行执行异常: {e}",
                )

    # ===== 章鱼架构v2.0 [模块1]: 契约校验 =====
    _apply_contract_validation(results)

    # ===== 章鱼架构v2.0 [模块5]: 消息总线 - 审查完成事件 =====
    if _bus:
        try:
            from core.message_bus import Channels, Message
            _bus.publish(Channels.REVIEW_COMPLETE, Message(
                sender="orchestrator",
                data={
                    "brain_count": len(results),
                    "total_issues": sum(len(r.issues) for r in results.values()),
                },
            ))
        except Exception as e:  # noqa: broad exception handling
            pass

    return results, timings


def _validate_single_brain_contract(brain_name: str, result, contracts) -> None:
    """Validate a single brain result against its contract."""
    brain_id = _find_brain_id_by_name(brain_name)
    if not brain_id:
        return
    try:
        from core.task_contract import validate_brain_result
        passed, report = validate_brain_result(brain_id, result.to_dict(), contracts)
        if not passed:
            if report.needs_fallback:
                result.status = "degraded"
                result.summary += f" [契约未通过: quality={report.quality_score:.2f}, 降级模式]"
            elif report.needs_retry:
                result.summary += f" [契约警告: quality={report.quality_score:.2f}, 建议重试]"
    except Exception as e:  # noqa: broad exception handling
        pass


def _apply_contract_validation(results: Dict[str, BrainResult]) -> None:
    """
    章鱼架构v2.0 [模块1]: 对所有大脑结果执行契约校验。
    校验失败时标记降级，不影响结果返回。
    """
    try:
        from core.task_contract import load_brain_contracts
        contracts = load_brain_contracts()
    except ImportError:
        return  # 契约模块不可用时静默跳过

    for brain_name, result in results.items():
        _validate_single_brain_contract(brain_name, result, contracts)


def get_problem_files(results: Dict[str, BrainResult]) -> List[str]:
    """
    从大脑结果中提取发现问题的文件列表（去重）
    """
    problem_files = set()
    for brain_name, result in results.items():
        if result.status in ("pass", "skip", "error"):
            continue
        for issue in result.issues:
            if issue.file:
                problem_files.add(issue.file)
    return sorted(problem_files)


# 延迟导入所有大脑模块以触发注册
def _ensure_loaded():
    """确保所有大脑模块已加载"""
    try:
        from . import brain1_rule_engine  # noqa: F401
    except ImportError:  # noqa: intentional empty handler
        pass
    try:
        from . import brain2_security_engine  # noqa: F401
    except ImportError:  # noqa: intentional empty handler
        pass
    try:
        from . import brain3_ai_engine  # noqa: F401
    except ImportError:  # noqa: intentional empty handler
        pass


_loaded = False


def ensure_brains_loaded():
    """确保所有大脑已加载（幂等）"""
    global _loaded
    if not _loaded:
        _ensure_loaded()
        _loaded = True


__all__ = [
    "BaseBrain",
    "BrainResult",
    "BrainIssue",
    "register_brain",
    "get_brain",
    "list_brains",
    "ensure_brains_loaded",
    "get_brains_by_level",
    "run_brains_parallel",
    "get_problem_files",
    "LEVEL_BRAINS",
    "_BRAIN_METADATA",
    "_find_brain_id_by_name",
]
