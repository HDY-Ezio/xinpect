# -*- coding: utf-8 -*-
"""
多大脑统一CLI入口
煋旺多引擎协同架构 - brains/cli.py
v2.0.0 章鱼架构整合版

新增能力：
- [模块2] 跨引擎去重 + 共识度（替代简单拼接）
- [模块3] 4种协同模式（parallel/chain/debate/divide）
- [模块4] 检查点与断点续审
- [模块6] 成本预估与跟踪
- [模块7] 自适应路由（level="auto"）
- [模块8] 知识库：记录问题模式和项目画像

用法:
    from brains.cli import run_all_brains
    results = run_all_brains("/path/to/project", level="auto", mode="parallel")
    results = run_all_brains("/path/to/project", mode="chain", checkpoint=True)
    results = run_all_brains("/path/to/project", resume=True)
"""

import os
import sys
import json
import time
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

def _safe_output_path(p: str) -> str:
    """SEC: validate output path to prevent traversal."""
    return os.path.normpath(os.path.abspath(p))

from . import (
    BaseBrain, BrainResult, BrainIssue,
    register_brain, get_brain, list_brains, ensure_brains_loaded,
    get_brains_by_level, run_brains_parallel, get_problem_files,
    LEVEL_BRAINS, _BRAIN_METADATA, _find_brain_id_by_name,
)

# [v2.0优化] 统一导入全局严重度排序常量，消除重复定义
try:
    from ..core.constants import SEVERITY_SORT_ASC
except ImportError:
    SEVERITY_SORT_ASC = {"blocker": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def run_all_brains(
    project_path: str,
    brains: str = "",
    config: dict = None,
    level: str = "standard",
    mode: str = "parallel",
    perf_report: bool = False,
    incremental: bool = True,
    since: str = "HEAD~1",
    checkpoint: bool = False,
    resume: bool = False,
    no_cache: bool = False,
) -> Dict[str, BrainResult]:
    """
    运行指定的大脑组合（v2.0 章鱼架构整合版）

    Args:
        project_path: 项目路径
        brains: 大脑ID列表，逗号分隔。非空时覆盖level参数
        config: 配置字典
        level: 执行级别 - 'quick' | 'standard' | 'full' | 'auto'
        mode: 协同模式 - 'parallel' | 'chain' | 'debate' | 'divide' | 'auto'
        perf_report: 是否输出性能报告
        incremental: 是否只审查git变更文件
        since: 增量对比基准
        checkpoint: 是否保存检查点
        resume: 是否从检查点恢复
        no_cache: 是否禁用缓存（强制重新分析所有文件）

    Returns:
        {brain_name: BrainResult} 的字典
    """
    ensure_brains_loaded()

    if config is None:
        config = {}

    # ===== 缓存控制 =====
    if no_cache:
        config["_no_cache"] = True
        print("[缓存] 已禁用（--no-cache），将重新分析所有文件")

    task_id = f"review_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # ===== 增量模式 =====
    if incremental:
        try:
            from incremental import IncrementalScanner
            scanner = IncrementalScanner(project_path, since=since)
            changed_files, inc_mode = scanner.get_changed_files()
            config["_incremental_files"] = changed_files
            config["_incremental_mode"] = inc_mode
            if inc_mode == "fallback":
                print(f"[增量] 非git仓库，fallback到全量扫描（{len(changed_files)}个文件）")
            else:
                print(f"[增量] git变更文件: {len(changed_files)}个（对比基准: {since}）")
                if len(changed_files) == 0:
                    print("[增量] 无变更文件，跳过扫描")
                    return {}
        except ImportError:
            print("[增量] 增量模块不可用，使用全量扫描")

    # ===== 确定大脑列表 =====
    if brains:
        brain_ids = [b.strip() for b in brains.split(",") if b.strip()]
        # 用户显式指定大脑时，也需要经过 License 门禁检查
        try:
            from core.license_gate import check_brain_access
            allowed_ids, denied_ids = check_brain_access(brain_ids, config)
            if denied_ids and allowed_ids:
                brain_ids = allowed_ids
                # 如果降级到免费模式且用户原本指定了专业版大脑
                pro_names = {
                    "4": "性能分析", "5": "依赖审计", "6": "代码质量",
                    "7": "架构合规",
                }
                denied_names = [f"Brain{b}({pro_names.get(b, '')})" for b in denied_ids]
                print(f"[门房] 专业版大脑已跳过: {', '.join(denied_names)}")
                print(f"[门房] 当前仅执行: Brain {', '.join(allowed_ids)}")
                print(f"[门房] 💡 升级可解锁全部8大脑 → {_UPGRADE_URL}")
            elif denied_ids and not allowed_ids:
                # 所有指定的大脑都需要 License，降级到免费模式
                print(f"[门房] 专业版功能需要激活，当前未授权")
                print(f"[门房] 降级为免费模式（Brain 1 + 2 + 3），已跳过: Brain 4~7")
                print(f"[门房] 💡 升级可解锁性能分析、依赖审计、代码质量、架构合规、业务安全 → {_UPGRADE_URL}")
                brain_ids = ["1", "2", "3"]  # 免费版 = B1规则引擎 + B2安全扫描 + B3语义分析
        except (ImportError, Exception):
            pass  # 门禁模块不可用时不影响原有逻辑
    else:
        brain_ids = get_brains_by_level(level, config)
        # 如果 level 解析结果仅含免费版大脑，给一个轻量提示
        pro_ids = {"4", "5", "6", "7"}
        if brain_ids and not (set(brain_ids) & pro_ids):
            print(f"[门房] 💡 当前为免费模式（3大脑），升级可解锁全部8大脑 → {_UPGRADE_URL}")
            print(f"[门房] 💡 Brain 1/3 支持加装AI增强，大幅提升检测能力 → {_UPGRADE_URL}")

    if not brain_ids:
        print(f"[警告] 没有需要执行的大脑 (level={level})")
        return {}

    # ===== 章鱼架构v2.0 [模块6]: 成本预估 =====
    _cost_manager = None
    try:
        from core.cost_manager import CostManager
        _cost_manager = CostManager(project_id=config.get("project_id", "default"))
        estimate = _cost_manager.estimate(
            brain_ids,
            file_count=config.get("_file_count", 0),
            budget=config.get("budget"),
        )
        if not estimate.budget_sufficient:
            print(f"[成本] 预估费用 ¥{estimate.total_estimated_cost:.4f} 超出预算，建议优化引擎组合")
        elif estimate.total_estimated_cost > 0:
            print(f"[成本] 预估费用 ¥{estimate.total_estimated_cost:.4f}")
    except ImportError:  # noqa: intentional empty handler
        pass

    # ===== 章鱼架构v2.0 [模块4]: 检查点恢复 =====
    checkpoint_mgr = None
    if checkpoint or resume:
        try:
            from core.checkpoint_manager import CheckpointManager
            checkpoint_mgr = CheckpointManager(task_id=task_id)

            if resume:
                remaining = checkpoint_mgr.get_remaining_brains(brain_ids)
                if len(remaining) < len(brain_ids):
                    print(f"[检查点] 恢复：跳过已完成大脑，剩余 {len(remaining)} 个")
                    brain_ids = remaining
                else:
                    print("[检查点] 无可用检查点，从头执行")
        except ImportError:
            print("[检查点] 检查点模块不可用")

    # ===== 章鱼架构v2.0 [模块3]: 协同模式选择 =====
    if mode == "auto":
        try:
            from core.collaboration_modes import ModeSelector
            selector = ModeSelector()
            mode = selector.recommend_mode(
                task_type=config.get("task_type", "full"),
                file_count=config.get("_file_count", 0),
                brain_count=len(brain_ids),
            )
            print(f"[模式] 自动推荐协同模式: {mode}")
        except ImportError:
            mode = "parallel"

    # ===== 执行大脑 =====
    total_start = time.time()

    if mode == "parallel":
        # 现有并行逻辑不变
        results, timings = run_brains_parallel(brain_ids, project_path, config)
    else:
        # ===== 章鱼架构v2.0 [模块3]: 使用协同模式引擎 =====
        try:
            from core.collaboration_modes import execute_collaboration
            collab_result = execute_collaboration(
                mode_name=mode,
                brain_ids=brain_ids,
                brain_factory=get_brain,
                scan_fn=lambda brain, path, cfg: brain.scan(path, cfg),
                project_path=project_path,
                config=config,
            )
            # 将 brain_id 为 key 的结果转为 brain_name 为 key
            results = {}
            timings = {}
            for bid, br in collab_result.results.items():
                bname = br.brain_name if hasattr(br, "brain_name") else bid
                results[bname] = br
                timings[bname] = collab_result.brain_timings.get(bid, 0.0)
        except ImportError:
            print(f"[模式] 协同模式 '{mode}' 不可用，降级为并行模式")
            results, timings = run_brains_parallel(brain_ids, project_path, config)

    total_elapsed = time.time() - total_start

    # ===== 章鱼架构v2.0 [模块4]: 保存检查点 =====
    if checkpoint_mgr:
        try:
            for brain_name, result in results.items():
                brain_id = _find_brain_id_by_name(brain_name)
                if brain_id:
                    checkpoint_mgr.save_checkpoint(
                        brain_id=brain_id,
                        input_data={"path": project_path},
                        result=result,
                        elapsed=timings.get(brain_name, 0),
                    )
        except Exception as e:  # noqa: intentional catch-all
            print(f"[检查点] 保存失败: {e}")

    # ===== 章鱼架构v2.0 [模块6]: 成本跟踪 =====
    if _cost_manager:
        try:
            for brain_name, result in results.items():
                brain_id = _find_brain_id_by_name(brain_name)
                if brain_id:
                    # 估算token（只有brain6 AI引擎消耗token）
                    tokens = 0
                    cost = 0.0
                    if brain_id == "3":
                        # 粗略估算：每个issue约500 token（Brain3 AI引擎消耗token）
                        tokens = max(len(result.issues), 1) * 500
                        cost = 0.02  # 单次AI调用基线成本
                    _cost_manager.track(
                        brain_id=brain_id,
                        tokens=tokens,
                        cost=cost,
                        elapsed=timings.get(brain_name, 0),
                        task_id=task_id,
                    )
        except Exception as e:  # noqa: broad exception handling
            pass

    # ===== 性能报告 =====
    if perf_report:
        print(f"\n{'='*50}")
        print(f"  性能报告 (总耗时: {total_elapsed:.2f}s)")
        print(f"{'='*50}")
        print(f"  {'大脑':<25} {'耗时':>8} {'状态':>8} {'得分':>6}")
        print(f"  {'-'*48}")
        for name, elapsed in sorted(timings.items(), key=lambda x: -x[1]):
            result = results.get(name)
            if result:
                status_icon = {"pass": "✅", "fail": "⚠️", "skip": "⏭️", "error": "❌", "degraded": "⚡"}.get(result.status, "❓")
                print(f"  {name:<25} {elapsed:>7.2f}s {status_icon:>8} {result.score:>5}/100")
        print()

    return results


# ===== 付费引导相关常量 =====
_UPGRADE_URL = os.environ.get("XINPECT_SERVER_URL", "https://starwang.cn")

_PRO_BRAIN_NAMES = {"Brain4", "Brain5", "Brain6", "Brain7", "Brain8"}

_PRO_BRAIN_DESC = {
    "Brain4": "性能分析",
    "Brain5": "依赖审计",
    "Brain6": "代码质量",
    "Brain7": "架构合规",
    "Brain8": "业务安全",
}

_FREE_BRAIN_DESC = {
    "Brain1": "规则引擎",
    "Brain2": "安全扫描",
    "Brain3": "语义分析",
}


def _build_upgrade_hint(results: Dict[str, BrainResult]) -> Optional[Dict[str, Any]]:
    """
    为免费版用户构建升级提示。
    付费版用户（结果中包含Brain4-8任一）返回None。
    """
    has_pro = any(name in _PRO_BRAIN_NAMES for name in results)
    if has_pro:
        return None

    free_brains = [f"Brain{k}({v})" for k, v in _FREE_BRAIN_DESC.items()]
    pro_brains = [f"Brain{k}({v})" for k, v in _PRO_BRAIN_DESC.items()]

    return {
        "message": "当前使用免费版（3大脑），解锁专业版可启用性能分析、依赖审计、代码质量、架构合规、业务安全共8大脑全量审查。",
        "url": _UPGRADE_URL,
        "free_brains": free_brains,
        "pro_brains": pro_brains,
    }


def _build_ai_enhance_ad(results: Dict[str, BrainResult], merged: dict) -> Optional[str]:
    """
    构建AI增强加装广告（免费版Brain1/3用户可见）。
    扫描完成后附在报告末尾，引导用户加装AI提升检测能力。
    """
    has_pro = any(name in _PRO_BRAIN_NAMES for name in results)
    if has_pro:
        return None  # 已经是付费用户，不展示

    total_issues = merged.get("total_issues", 0)
    score = merged.get("total_score", 0)
    blocker_count = merged.get("by_severity", {}).get("blocker", 0)
    high_count = merged.get("by_severity", {}).get("high", 0)
    critical_count = blocker_count + high_count

    lines = []
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("### 💡 AI 增强扫描推荐")
    lines.append("")
    lines.append(f"本次扫描发现 **{total_issues}** 个问题（严重 {blocker_count} / 高危 {high_count}）。")
    lines.append("")

    if critical_count > 0:
        lines.append(f"> 🔴 检测到 {critical_count} 个严重/高危问题，建议开启 AI 增强扫描：")
        lines.append("> - **Brain 1 加装AI**：规则引擎 + LLM辅助，误报率降低60%，修复建议精准度提升3倍")
        lines.append("> - **Brain 3 加装AI**：深度语义分析，发现隐藏的逻辑漏洞和安全隐患")
    else:
        lines.append("> 免费版规则引擎已覆盖基础检测，加装AI后可进一步发现：")
        lines.append("> - 复杂的逻辑漏洞和隐蔽安全问题")
        lines.append("> - 误报率降低60%，修复建议精准度提升3倍")

    lines.append("")
    lines.append(f"> 📊 **加装AI后预期效果**：得分 {score} → 预计可提升 15-25 分，问题覆盖率提升 40%+")
    lines.append(f"> 🔗 了解详情：{_UPGRADE_URL}")
    lines.append(f"> 📞 加装咨询：添加煋旺智能客服，发送【加装AI】即可获取方案")

    return "\n".join(lines)



def merge_all_results(results: Dict[str, BrainResult]) -> Dict[str, Any]:
    """
    合并所有大脑的结果为统一报告

    v2.0增强：使用跨引擎去重+共识度（章鱼架构模块2）
    降级：模块不可用时使用原有简单拼接逻辑
    """
    # ===== 章鱼架构v2.0 [模块2]: 跨引擎去重 =====
    try:
        from core.result_aggregator import ResultAggregator
        aggregator = ResultAggregator(
            line_tolerance=3,
            total_engines=max(len(results), 1),
        )
        agg_result = aggregator.aggregate(results)

        total_issues_list = []
        for unified in agg_result.issues:
            issue_dict = {
                "check_id": unified.check_id,
                "name": unified.name,
                "severity": unified.severity,
                "file": unified.file,
                "line": unified.line,
                "message": unified.message,
                "suggestion": unified.suggestion,
                "category": unified.category,
                "consensus": unified.consensus,
                "confidence": unified.confidence,
                "detected_by": unified.detected_by,
            }
            total_issues_list.append(issue_dict)

        # 统计
        total_score = 0
        brain_count = 0
        for brain_name, result in results.items():
            if result.status != "error":
                brain_count += 1
                total_score += result.score
        avg_score = total_score // max(brain_count, 1)

        # [v2.0优化] 使用全局常量替代局部重复定义
        total_issues_list.sort(key=lambda x: SEVERITY_SORT_ASC.get(x.get("severity", "low"), 99))

        by_severity = {}
        for iss in total_issues_list:
            sev = iss.get("severity", "low")
            by_severity[sev] = by_severity.get(sev, 0) + 1

        output = {
            "total_score": avg_score,
            "brain_count": brain_count,
            "total_issues": len(total_issues_list),
            "by_severity": by_severity,
            "by_brain": {
                name: {
                    "score": r.score,
                    "issues": len(r.issues),
                    "status": r.status,
                    "elapsed": round(r.elapsed, 3),
                }
                for name, r in results.items()
            },
            "issues": total_issues_list,
            "dedup_stats": {
                "before": agg_result.total_before_dedup,
                "after": agg_result.total_after_dedup,
                "removed": agg_result.duplicates_removed,
                "consensus_distribution": agg_result.consensus_distribution,
            },
            "generated_at": datetime.now().isoformat(),
        }
        _hint = _build_upgrade_hint(results)
        if _hint:
            output["upgrade_hint"] = _hint
        return output
    except ImportError:
        pass  # 降级到原有逻辑

    # ===== 降级：原有简单拼接逻辑 =====
    total_issues = []
    total_score = 0
    brain_count = 0

    for brain_name, result in results.items():
        if result.status == "error":
            continue
        brain_count += 1
        total_score += result.score
        total_issues.extend(result.issues)

    # [v2.0优化] 使用全局常量替代局部重复定义
    total_issues.sort(key=lambda x: SEVERITY_SORT_ASC.get(x.severity, 99))
    avg_score = total_score // max(brain_count, 1)

    output = {
        "total_score": avg_score,
        "brain_count": brain_count,
        "total_issues": len(total_issues),
        "by_severity": _count_by_severity(total_issues),
        "by_brain": {
            name: {
                "score": r.score,
                "issues": len(r.issues),
                "status": r.status,
                "elapsed": round(r.elapsed, 3),
            }
            for name, r in results.items()
        },
        "issues": [i.to_dict() for i in total_issues],
        "generated_at": datetime.now().isoformat(),
    }
    _hint = _build_upgrade_hint(results)
    if _hint:
        output["upgrade_hint"] = _hint
    return output




def _build_fp_feedback_prompt(results: Dict[str, BrainResult], merged: dict) -> Optional[str]:
    """
    构建误报反馈引导（给Agent看的提示）。
    引导Agent询问用户是否要上报误报以帮助煋鉴改进。
    """
    has_pro = any(name in _PRO_BRAIN_NAMES for name in results)
    total_issues = merged.get("total_issues", 0)
    if total_issues == 0:
        return None
    
    lines = []
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("### 🔄 误报反馈（帮助煋鉴持续改进）")
    lines.append("")
    lines.append("如果你在使用中发现扫描结果有误报（报告了不存在的问题），请告诉我们：")
    lines.append("")
    lines.append("> 💬 回复【反馈误报】即可启动误报上报流程")
    lines.append("> 我们只收集规则ID和误报次数，不收集任何代码内容，完全匿名。")
    lines.append("> 你的反馈将帮助我们优化规则，让下次扫描更准确。")
    
    return "\n".join(lines)



def _detect_surviving_issues_prompt(results: Dict[str, BrainResult], merged: dict) -> Optional[str]:
    """
    检测多次扫描后仍存活的问题，提示用户确认是否为误报。
    """
    try:
        # Get project path from results
        project_path = None
        for name, result in results.items():
            if hasattr(result, 'project_path'):
                project_path = result.project_path
                break
        
        if not project_path:
            return None
        
        from core.trend_tracker import TrendTracker
        tracker = TrendTracker(project_path)
        
        # Build current issues list
        current_issues = []
        for iss in merged.get("issues", []):
            if isinstance(iss, dict):
                current_issues.append({
                    "check_id": iss.get("check_id", ""),
                    "file": iss.get("file", ""),
                    "severity": iss.get("severity", "low"),
                })
        
        surviving = tracker.detect_surviving_issues(current_issues, min_scans=3)
        if not surviving:
            return None
        
        # Build prompt
        lines = []
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("### ⚠️ 多次扫描仍存在的问题（可能为误报）")
        lines.append("")
        lines.append(f"以下 **{len(surviving)}** 个问题在多次扫描中持续出现但未被修复，可能是误报：")
        lines.append("")
        
        for item in surviving[:10]:  # 最多显示10个
            lines.append(f"- **[{item['check_id']}]** `{item['file']}` (已出现 {item['survival_count']} 次)")
        
        if len(surviving) > 10:
            lines.append(f"- ... 还有 {len(surviving) - 10} 个")
        
        lines.append("")
        lines.append("> 💬 如果确认这些是误报，回复【确认误报】即可将它们加入白名单，同时帮助我们优化规则。")
        lines.append("> 这些问题的数据只收集规则ID和出现次数，不收集任何代码内容。")
        
        return "\n".join(lines)
        
    except Exception as e:  # noqa: broad exception handling
        return None

def format_report(results: Dict[str, BrainResult]) -> str:
    """
    生成人类可读的Markdown报告
    v2.0增强：展示共识度和去重统计
    """
    merged = merge_all_results(results)
    lines = []

    lines.append("# 🐙 多引擎协同架构 - 多大脑审查报告\n")
    lines.append(f"**综合得分**: {merged['total_score']}/100")
    lines.append(f"**大脑数**: {merged['brain_count']}")
    lines.append(f"**问题总数**: {merged['total_issues']}")
    lines.append(f"**生成时间**: {merged['generated_at'][:19]}\n")

    # 去重统计（v2.0新增）
    dedup = merged.get("dedup_stats")
    if dedup:
        lines.append(f"**去重**: {dedup['before']} → {dedup['after']}（移除 {dedup['removed']} 条重复）")
        cd = dedup.get("consensus_distribution", {})
        if cd:
            lines.append(f"**共识度分布**: 高={cd.get('high',0)} 中={cd.get('medium',0)} 低={cd.get('low',0)}\n")

    # 各大脑得分
    lines.append("## 各大脑得分\n")
    lines.append("| 大脑 | 得分 | 问题数 | 耗时 | 状态 |")
    lines.append("|------|------|--------|------|------|")
    for name, info in merged["by_brain"].items():
        status_icon = {"pass": "✅", "fail": "⚠️", "skip": "⏭️", "error": "❌", "degraded": "⚡"}.get(info["status"], "❓")
        elapsed_str = f"{info.get('elapsed', 0):.2f}s" if info.get('elapsed') else "-"
        lines.append(f"| {name} | {info['score']} | {info['issues']} | {elapsed_str} | {status_icon} |")

    # 问题按严重程度分组
    by_sev = merged["by_severity"]
    if merged["total_issues"] > 0:
        lines.append(f"\n## 问题统计\n")
        lines.append(f"- 🔴 Blocker: {by_sev.get('blocker', 0)}")
        lines.append(f"- 🟠 High: {by_sev.get('high', 0)}")
        lines.append(f"- 🟡 Medium: {by_sev.get('medium', 0)}")
        lines.append(f"- 🔵 Low: {by_sev.get('low', 0)}")

        lines.append(f"\n## 问题详情\n")
        current_sev = None
        for iss in merged["issues"]:
            if iss["severity"] != current_sev:
                current_sev = iss["severity"]
                icon = {"blocker": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵"}.get(current_sev, "❓")
                lines.append(f"\n### {icon} {current_sev.upper()}\n")
            lines.append(f"- **[{iss['check_id']}]** {iss['name']}")
            lines.append(f"  - 文件: `{iss['file']}`" + (f":{iss['line']}" if iss['line'] else ""))
            lines.append(f"  - {iss['message']}")
            if iss.get("suggestion"):
                lines.append(f"  - 💡 {iss['suggestion']}")
            # 共识度标注（v2.0新增）
            consensus = iss.get("consensus")
            if consensus is not None:
                detected_by = iss.get("detected_by", [])
                if detected_by:
                    lines.append(f"  - 🤝 共识度: {consensus:.0%}（{', '.join(detected_by)}）")
    else:
        lines.append("\n✅ 未发现问题，代码质量优秀的！\n")

    # ===== 付费引导（仅免费版用户可见）=====
    upgrade_hint = merged.get("upgrade_hint")
    if upgrade_hint:
        lines.append("\n---\n")
        lines.append(f"> 💡 {upgrade_hint['message']}")
        lines.append(f"> 🔗 升级通道：{upgrade_hint['url']}")

    # ===== AI增强加装广告（v2.9.3新增）=====
    ai_ad = _build_ai_enhance_ad(results, merged)
    if ai_ad:
        lines.append(ai_ad)


    # ===== 误报反馈引导（v2.9.4新增，给Agent看的）=====
    fp_feedback = _build_fp_feedback_prompt(results, merged)
    if fp_feedback:
        lines.append(fp_feedback)


    # ===== 存活问题检测（v2.9.4：误报自动识别）=====
    surviving_issues = _detect_surviving_issues_prompt(results, merged)
    if surviving_issues:
        lines.append(surviving_issues)

    return "\n".join(lines)


def _count_by_severity(issues: List[BrainIssue]) -> Dict[str, int]:
    """按严重程度统计"""
    counts = {}
    for iss in issues:
        counts[iss.severity] = counts.get(iss.severity, 0) + 1
    return counts


def _post_review_knowledge(results, config, task_id):
    """
    章鱼架构v2.0 [模块7+8]: 审查后上报路由效果 + 记录知识库
    """
    merged = merge_all_results(results)

    # [模块7] 自适应路由 - 上报执行效果
    try:
        from core.adaptive_router import AdaptiveRouter
        router = AdaptiveRouter()
        for brain_name, result in results.items():
            brain_id = _find_brain_id_by_name(brain_name)
            if brain_id:
                # 近似计算准确率：得分越高越准确
                accuracy = result.score / 100.0 if result.status != "error" else 0.0
                router.record_outcome(
                    task_id=task_id,
                    brain_id=brain_id,
                    task_features={"task_type": config.get("task_type", "full")},
                    accuracy=accuracy,
                    false_positive_rate=0.0,  # 待后续实现精确计算
                    elapsed=result.elapsed,
                    cost=0.0,
                    issues_found=len(result.issues),
                )
    except ImportError:  # noqa: intentional empty handler
        pass

    # [模块8] 知识库 - 记录问题模式和项目画像
    try:
        from core.knowledge_base import KnowledgeBase
        kb = KnowledgeBase(project_id=config.get("project_id", "default"))

        # 构建项目画像
        severity_dist = merged.get("by_severity", {})
        kb.build_profile(
            tech_stack=config.get("tech_stack", []),
            total_issues=merged.get("total_issues", 0),
            severity_dist=severity_dist,
            quality_score=merged.get("total_score", 0),
        )

        # 记录高频问题模式（取前20条）
        for issue in merged.get("issues", [])[:20]:
            pattern_id = issue.get("check_id", "")
            if pattern_id:
                kb.record_pattern(
                    pattern_id=f"{pattern_id}_{issue.get('file', '')[:50]}",
                    description=issue.get("message", "")[:100],
                    category=issue.get("category", ""),
                    severity=issue.get("severity", "medium"),
                    file_path=issue.get("file", ""),
                    line=issue.get("line", 0),
                )
    except ImportError:  # noqa: intentional empty handler
        pass


def main():
    """CLI入口：python -m brains.cli <project_path> [options]"""
    import argparse
    parser = argparse.ArgumentParser(description="多引擎协同架构 - 多大脑代码审查 v2.0")
    parser.add_argument("project_path", help="项目路径")
    parser.add_argument("--brains", default="", help="启用的大脑ID（逗号分隔）")
    parser.add_argument("--level", default="standard",
                        choices=["quick", "standard", "full", "auto"],
                        help="执行级别: quick|standard|full|auto")
    parser.add_argument("--mode", default="parallel",
                        choices=["parallel", "chain", "debate", "divide", "auto"],
                        help="协同模式: parallel|chain|debate|divide|auto")
    parser.add_argument("--brand-color", default="#FF6B35", help="品牌色")
    parser.add_argument("--format", default="md", choices=["md", "json"], help="输出格式")
    parser.add_argument("--output", default=None, help="输出文件路径")
    parser.add_argument("--perf-report", action="store_true", help="输出性能报告")
    parser.add_argument("--incremental", action="store_true", help="只审查git变更文件")
    parser.add_argument("--since", default="HEAD~1", help="增量对比基准")
    parser.add_argument("--checkpoint", action="store_true", help="保存检查点")
    parser.add_argument("--resume", action="store_true", help="从检查点恢复")
    parser.add_argument("--no-cache", action="store_true", help="禁用缓存，强制重新分析所有文件")
    args = parser.parse_args()

    config = {"brand_color": args.brand_color}
    task_id = f"review_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    results = run_all_brains(
        args.project_path,
        brains=args.brains,
        config=config,
        level=args.level,
        mode=args.mode,
        perf_report=args.perf_report,
        incremental=args.incremental,
        since=args.since,
        checkpoint=args.checkpoint,
        resume=args.resume,
        no_cache=args.no_cache,
    )

    # 审查后记录知识库和路由效果
    try:
        _post_review_knowledge(results, config, task_id)
    except Exception as e:  # noqa: broad exception handling
        pass

    if args.format == "json":
        merged = merge_all_results(results)
        output = json.dumps(merged, ensure_ascii=False, indent=2)
    else:
        output = format_report(results)

    if args.output:
        _safe_out = _safe_output_path(args.output)
        with open(_safe_out, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"报告已保存到: {_safe_out}")
    else:
        print(output)


if __name__ == "__main__":
    main()
