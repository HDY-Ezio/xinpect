#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
新引擎 (RuleRunner) 扫描适配层
==================================

将 CLI 的 scan 子命令接到 core.runner.RuleRunner（新引擎，2600+ 规则、8 大脑），
保持与旧引擎一致的 CLI 输出风格（彩色、进度条、汇总表）。

向后兼容：
  - --engine-mode legacy  仍然走 qa_framework 旧引擎
  - --engine-mode new     走 RuleRunner 新引擎（默认）
  - --engine-mode hybrid  两个引擎都跑（对比模式）
"""

import os
import sys
import time
import json
import logging
from collections import defaultdict

# 颜色与表格工具（复用 cli/utils.py）
from cli.utils import (
    Colors,
    color_bold, color_info, color_pass, color_high,
    color_medium, color_low, color_suggestion, color_dim,
    ascii_table, render_summary_table, ProgressPrinter,
)


# ---------------------------------------------------------------------------
# 辅助：Level 等级文本
# ---------------------------------------------------------------------------

def _level_label(level: str) -> str:
    """标准化 level 为人类可读的带色标签"""
    lvl = (level or "").lower()
    if lvl in ("blocking", "error"):
        return color_high("高危")
    if lvl in ("problem", "warning"):
        return color_medium("中危")
    if lvl == "info":
        return color_low("低危")
    if lvl == "suggestion":
        return color_suggestion("建议")
    return level or "-"


def _grade_of_score(score: int) -> str:
    """根据总分返回等级描述"""
    if score >= 90:
        return "优秀"
    if score >= 75:
        return "良好"
    if score >= 60:
        return "中等"
    if score >= 40:
        return "需整改"
    return "严重"


# ---------------------------------------------------------------------------
# 核心：执行新引擎扫描
# ---------------------------------------------------------------------------

def run_new_engine_scan(
    path: str,
    *,
    level: str = "standard",            # quick / standard / full
    config_path: str = "",
    rule_path: str = "",
    enable_fp_filter: bool = True,
    enable_deep_diagnosis: bool = True,
    incremental: bool = True,
    project_type: str = "",
    output_dir: str = "",
    output_format: str = "cli",         # cli / md / html / json
    only_level: str = "",               # high / medium / low / suggestion / ""
    brief: bool = True,
    verbose: bool = False,
    ai_full: bool = False,
    perf_report: bool = False,
    no_cache: bool = False,
    cache_clear: bool = False,
    since_ref: str = "HEAD~1",
    rule_health: bool = False,
) -> int:
    """用 RuleRunner（新引擎）执行扫描并输出结果

    Args:
        path: 项目路径
        level: 扫描级别 quick/standard/full
        config_path: 配置文件路径
        ...其他参数同 CLI 选项

    Returns:
        退出码: 0 成功，1 有高危问题，2 执行错误
    """
    # 延迟导入，避免子模块 import 时开销
    from core.context import QAContext
    from core.runner import RuleRunner
    from core.scoring import CATEGORY_NAMES, CATEGORY_ICONS

    project_path = os.path.abspath(path)
    if not os.path.exists(project_path):
        print(f"{color_high('错误')}: 路径不存在: {project_path}")
        return 2

    # ---- 1. 级别映射 ----
    # quick:    最快，关闭 FP 过滤深度模式、关闭深度诊断
    # standard: 默认平衡
    # full:     全开，包括深度诊断、FP 深度模式、评分 full 模式
    if level == "quick":
        fp_mode = "quick"
        diagnosis_mode = "quick"
        scoring_mode = "quick"
        use_rule_pruning = True
        use_fp_filter = enable_fp_filter  # 保持用户选择
        use_deep_diag = False             # quick 模式下强制关闭深度诊断
    elif level == "full":
        fp_mode = "deep"
        diagnosis_mode = "deep"
        scoring_mode = "full"
        use_rule_pruning = False          # 全量模式不裁剪规则
        use_fp_filter = enable_fp_filter
        use_deep_diag = enable_deep_diagnosis
    else:  # standard
        fp_mode = "standard"
        diagnosis_mode = "standard"
        scoring_mode = "standard"
        use_rule_pruning = True
        use_fp_filter = enable_fp_filter
        use_deep_diag = enable_deep_diagnosis

    # 覆盖：用户明确关闭 FP / 深度诊断时
    if not enable_fp_filter:
        fp_mode = "off"
    if not enable_deep_diagnosis:
        use_deep_diag = False
        diagnosis_mode = "quick"

    # ---- 2. 加载配置 ----
    config = {}
    if config_path and os.path.isfile(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception as e:
            print(f"{color_high('警告')}: 配置文件读取失败，使用默认配置: {e}")
            config = {}

    # ---- 3. 初始化上下文 & 运行器 ----
    ctx_kwargs = dict(
        project_path=project_path,
        config=config,
    )
    if project_type:
        ctx_kwargs["project_type"] = project_type

    context = QAContext(**ctx_kwargs)

    runner = RuleRunner(
        context=context,
        enable_fp_filter=use_fp_filter,
        enable_deep_diagnosis=use_deep_diag,
        fp_mode=fp_mode if use_fp_filter else "quick",
        diagnosis_mode=diagnosis_mode,
        scoring_mode=scoring_mode,
        enable_telemetry=False,             # CLI 模式下不启用遥测
        incremental=incremental,
        enable_rule_pruning=use_rule_pruning,
        force_full_scan=(not incremental),
    )

    # ---- 4. 打印 Banner ----
    print()
    print(f"  {color_bold('🔥 煋鉴 Xinpect')} v4.6  —  AI 代码安全官 (新引擎)")
    print(f"  {color_info('扫描路径')}: {project_path}")
    print(f"  {color_info('项目类型')}: {context.project_type_name}")
    print(f"  {color_info('扫描级别')}: {level}")
    print()

    # ---- 5. 执行扫描 ----
    t_start = time.time()
    try:
        # 先加载规则，展示规则数量
        runner.rule_loader.load_all()
        total_rules = len(runner.rule_loader.all_rules)
        semgrep_count = len(runner.rule_loader.get_semgrep_rules())
        semantic_count = len(runner.rule_loader.get_semantic_rules())
        grand_total = total_rules + semgrep_count + semantic_count

        print(f"  {color_info('📦 规则加载')}: {color_bold(str(grand_total))} 条 "
              f"(AST/正则 {total_rules} + semgrep {semgrep_count} + 语义 {semantic_count})")
        if incremental:
            print(f"  {color_info('⚡ 增量模式')}: 已开启（仅扫描变更文件）")
        print()

        # ---- 5.1 规则性能体检（--rule-health）----
        if rule_health:
            from core.rule_loader.loader import SLOW_RULE_TOP_N
            print(f"  {color_bold('🏥 规则性能体检')} — 正在用 5000 行大文本压测正则规则...")
            print()
            slow_rules = runner.rule_loader._perf_health_check()
            if slow_rules:
                print(f"  {color_high(f'⚠️  发现 {len(slow_rules)} 条慢规则')}（阈值 100ms/次）")
                print()
                # 输出 Top N 榜单
                header = ["排名", "规则 ID", "规则名称", "平均(ms)", "最大(ms)"]
                rows = []
                for i, r in enumerate(slow_rules[:SLOW_RULE_TOP_N]):
                    rows.append([
                        f"#{i+1}",
                        r["rule_id"],
                        r["name"][:30],
                        f"{r['avg_ms']:.2f}",
                        f"{r['max_ms']:.2f}",
                    ])
                for line in ascii_table(rows, header).split("\n"):
                    print("  " + line)
                print()
                print(f"  {color_dim('提示：慢规则会显著拖慢扫描速度，建议优化正则或使用负向前瞻快速预检')}")
                print()
            else:
                print(f"  {color_pass('✓ 所有正则规则性能良好')}（均 < 100ms/次）")
                print()

        # 执行完整扫描
        results = runner.run_all()

        # v4.3.0 P1-1: Semgrep 未安装时给出醒目提示
        if getattr(runner.executor, 'semgrep_skipped', False):
            semgrep_count = len(runner.rule_loader.get_semgrep_rules())
            print()
            print(f"  {color_medium('⚠️  Semgrep 未安装')}：{semgrep_count} 条 AST 安全规则已跳过")
            print(f"     {color_dim('安装方法：pip install semgrep')}")
            print()

    except Exception as e:
        import traceback
        print(f"{color_high('扫描失败')}: {e}")
        if verbose:
            traceback.print_exc()
        return 2

    elapsed = time.time() - t_start

    # ---- 6. 计算评分 ----
    scores = runner.calculate_scores()
    total_score = scores.get("total", 100)
    grade = _grade_of_score(total_score)

    # ---- 7. 统计信息 ----
    flat = runner.get_flat_results()
    active = [r for r in flat if getattr(r, "status", "active") == "active"]

    # 按级别统计
    # 注意：新引擎的 level 值为 blocking/error/problem/warning/info/suggestion
    # 对应关系：
    #   高危 (high)     = blocking + error
    #   中危 (medium)   = problem + warning
    #   低危 (low)      = info （非建议类）
    #   建议 (suggestion) = suggestion
    error_count = sum(1 for r in active if r.level in ("blocking", "error"))
    warning_count = sum(1 for r in active if r.level in ("problem", "warning"))
    info_count = sum(1 for r in active if r.level == "info")
    suggestion_count = sum(1 for r in active if r.level == "suggestion")

    # 误报统计
    fp_count = runner.fp_count

    # 通过规则数（估算：总执行规则 - 触发问题）
    # 新引擎没有显式的"通过"计数，这里用触发规则 ID 去重估算
    triggered_ids = set(r.rule_id for r in active)
    pass_count = max(0, grand_total - len(triggered_ids))

    # ---- 8. 结果过滤（--only）----
    if only_level:
        sev_map = {
            "high": ("blocking", "error"),
            "medium": ("problem", "warning"),
            "low": ("info",),
            "suggestion": ("suggestion",),
        }
        target_levels = sev_map.get(only_level, ())
        active = [r for r in active if r.level in target_levels]

    # ---- 9. 输出报告 ----
    report_path = ""
    if output_format in ("html", "json", "md") or output_dir:
        out_dir = output_dir or os.path.join(project_path, "xinpect_report")
        os.makedirs(out_dir, exist_ok=True)

        # HTML 报告（总是生成，当用户指定 html 或指定了 output_dir 时）
        if output_format in ("html",) or output_dir:
            try:
                from core.html_report import generate_html_report
                report_path = generate_html_report(
                    runner=runner,
                    output_dir=out_dir,
                    project_path=project_path,
                    project_type=context.project_type,
                    all_results=results,
                    scores=scores,
                    theme="light",
                )
            except Exception as e:
                print(f"{color_high('警告')}: HTML 报告生成失败: {e}")

        # JSON 报告
        if output_format == "json":
            try:
                json_path = os.path.join(out_dir, "scan_result.json")
                json_data = _build_json_report(runner, scores, context, elapsed)
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(json_data, f, indent=2, ensure_ascii=False, default=str)
                if not report_path:
                    report_path = json_path
                print(f"  {color_info('📄 JSON 报告')}: {json_path}")
            except Exception as e:
                print(f"{color_high('警告')}: JSON 报告生成失败: {e}")

        # Markdown 报告
        if output_format == "md":
            try:
                md_path = os.path.join(out_dir, "scan_result.md")
                md_content = _build_md_report(runner, scores, context, elapsed)
                with open(md_path, "w", encoding="utf-8") as f:
                    f.write(md_content)
                if not report_path:
                    report_path = md_path
                print(f"  {color_info('📄 Markdown 报告')}: {md_path}")
            except Exception as e:
                print(f"{color_high('警告')}: Markdown 报告生成失败: {e}")

    # ---- 10. CLI 输出汇总 ----
    issue_counts = {
        "error": error_count,
        "warning": warning_count,
        "info": info_count,
        "suggestion": suggestion_count,
        "pass": pass_count,
    }

    summary = render_summary_table(
        score=total_score,
        grade=grade,
        scores=scores,
        issue_counts=issue_counts,
        report_path=report_path or "(未生成)",
    )
    print(summary)

    # ---- 11. 问题列表（详细模式）----
    if verbose or (not brief and active):
        _print_issue_list(active, only_level=only_level)

    # ---- 12. 额外统计 ----
    inc_stats = runner.get_incremental_scan_stats() if hasattr(runner, "get_incremental_scan_stats") else {}
    prune_stats = runner.get_prune_stats() if hasattr(runner, "get_prune_stats") else {}

    extra_lines = []
    extra_lines.append(f"  {color_dim('⏱  耗时')}: {elapsed:.2f}s")
    if fp_count:
        extra_lines.append(f"  {color_dim('🚫 误报过滤')}: 过滤 {fp_count} 条")
    # v4.6.1: 正则超时降级统计
    from core.rule_loader.loader import get_regex_timeout_stats
    timeout_stats = get_regex_timeout_stats()
    if timeout_stats:
        total_timeouts = sum(timeout_stats.values())
        affected_rules = len(timeout_stats)
        extra_lines.append(
            f"  {color_dim('⏰ 正则熔断')}: {total_timeouts} 次超时降级 "
            f"(涉及 {affected_rules} 条规则)"
        )
    if inc_stats and inc_stats.get("mode") == "incremental":
        extra_lines.append(
            f"  {color_dim('⚡ 增量扫描')}: "
            f"{inc_stats.get('changed_files', 0)} 个变更文件 / "
            f"{inc_stats.get('total_files', 0)} 个总文件"
        )
    if prune_stats and prune_stats.get("pruned_count"):
        extra_lines.append(
            f"  {color_dim('✂️  规则裁剪')}: "
            f"裁剪 {prune_stats.get('pruned_count', 0)} / {prune_stats.get('original_count', 0)} 条"
        )

    # v4.3.0 P1-1: Semgrep 状态标记
    if getattr(runner.executor, 'semgrep_skipped', False):
        semgrep_count = len(runner.rule_loader.get_semgrep_rules())
        extra_lines.append(
            f"  {color_dim('🔍 Semgrep规则')}: 已跳过（未安装） - {semgrep_count} 条"
        )

    for line in extra_lines:
        print(line)
    print()

    # ---- 12.5 引流钩子（基础版提示）----
    _print_lite_hook()

    # ---- 13. 退出码 ----
    # 有高危问题返回 1，否则 0
    if error_count > 0:
        return 1
    return 0


# ---------------------------------------------------------------------------
# 引流钩子（基础版提示）
# ---------------------------------------------------------------------------

def _print_lite_hook():
    """打印基础版引流提示文案"""
    print("  " + "─" * 56)
    print("  💡 提示：您正在使用基础版检测")
    print("  B1~B3 基础检测可以帮您发现语法错误、低级安全漏洞和规范问题，")
    print("  但还有以下维度未覆盖：")
    print("    📊 性能问题（死循环、内存泄漏、低效查询…）")
    print("    📦 依赖漏洞（第三方包 CVE 风险…）")
    print("    🧩 代码质量（复杂度、重复率、可维护性…）")
    print("    🏗️ 架构设计（分层合理性、耦合度、模块化…）")
    print("    🔒 业务安全（越权、注入、数据泄露…）")
    print("  完整 8 维度检测请前往 煋鉴官网 获取。")
    print("  " + "─" * 56)
    print()


# ---------------------------------------------------------------------------
# 辅助：打印问题列表
# ---------------------------------------------------------------------------

def _print_issue_list(active_results: list, only_level: str = "", max_show: int = 50):
    """打印问题列表（按模块分组）"""
    if not active_results:
        print(f"  {color_pass('✓')} 未发现问题")
        print()
        return

    from collections import defaultdict
    by_module = defaultdict(list)
    for r in active_results:
        # 从 rule_id 提取模块号
        rid = r.rule_id or ""
        if "." in rid and rid.split(".")[0].isdigit():
            mid = rid.split(".")[0]
        elif "-" in rid:
            mid = rid.split("-")[0]
        else:
            mid = "other"
        by_module[mid].append(r)

    print(f"  {color_bold('📋 问题详情')}  (共 {len(active_results)} 条，仅展示前 {max_show} 条)")
    print()

    shown = 0
    for mid in sorted(by_module.keys(), key=lambda x: (not x.isdigit(), x)):
        if shown >= max_show:
            break
        items = by_module[mid]
        print(f"  {color_info(f'[{mid}]')} {color_dim(f'({len(items)} 个问题)')}")
        for r in items[:8]:  # 每个模块最多显示 8 条
            if shown >= max_show:
                break
            loc = r.location or {}
            file_info = ""
            if loc.get("file"):
                file_info = f"  {color_dim(loc['file'])}"
                if loc.get("line"):
                    file_info += f":{loc['line']}"

            print(f"    {_level_label(r.level)} {color_bold(r.rule_id)} {r.rule_name}{file_info}")
            shown += 1
        print()

    if len(active_results) > max_show:
        print(f"  {color_dim(f'... 还有 {len(active_results) - max_show} 条问题未显示，详见 HTML 报告')}")
        print()


# ---------------------------------------------------------------------------
# 报告生成辅助：JSON
# ---------------------------------------------------------------------------

def _build_json_report(runner, scores, context, elapsed: float) -> dict:
    """构建 JSON 格式的扫描报告"""
    flat = runner.get_flat_results()
    active = [r for r in flat if getattr(r, "status", "active") == "active"]
    issues = []
    for r in active:
        issues.append({
            "id": r.rule_id,
            "name": r.rule_name,
            "level": r.level,
            "category": r.category,
            "message": r.message,
            "detail": r.detail,
            "fix": r.fix,
            "location": r.location or {},
            "suggestion_code": r.suggestion_code,
        })

    # 按级别统计
    error_count = sum(1 for r in active if r.level in ("blocking", "error"))
    warning_count = sum(1 for r in active if r.level in ("problem", "warning"))
    info_count = sum(1 for r in active if r.level == "info")
    suggestion_count = sum(1 for r in active if r.level == "suggestion")

    report = {
        "scan_summary": {
            "project_path": context.project_path,
            "project_type": context.project_type,
            "project_type_name": context.project_type_name,
            "elapsed_seconds": round(elapsed, 2),
            "total_rules": len(runner.rule_loader.all_rules),
            "semgrep_rules": len(runner.rule_loader.get_semgrep_rules()),
            "semantic_rules": len(runner.rule_loader.get_semantic_rules()),
        },
        "scores": scores,
        "issue_stats": {
            "high": error_count,
            "medium": warning_count,
            "low": info_count,
            "suggestion": suggestion_count,
            "fp_count": runner.fp_count,
        },
        "issues": issues,
    }
    return report


# ---------------------------------------------------------------------------
# 报告生成辅助：Markdown
# ---------------------------------------------------------------------------

def _build_md_report(runner, scores, context, elapsed: float) -> str:
    """构建 Markdown 格式的扫描报告"""
    from core.scoring import CATEGORY_NAMES

    flat = runner.get_flat_results()
    active = [r for r in flat if getattr(r, "status", "active") == "active"]

    error_count = sum(1 for r in active if r.level in ("blocking", "error"))
    warning_count = sum(1 for r in active if r.level in ("problem", "warning"))
    info_count = sum(1 for r in active if r.level == "info")
    suggestion_count = sum(1 for r in active if r.level == "suggestion")

    total_score = scores.get("total", 100)
    grade = _grade_of_score(total_score)

    lines = []
    lines.append(f"# 煋鉴代码审查报告")
    lines.append("")
    lines.append(f"- **项目路径**: `{context.project_path}`")
    lines.append(f"- **项目类型**: {context.project_type_name}")
    lines.append(f"- **综合评分**: **{total_score}/100** ({grade})")
    lines.append(f"- **扫描耗时**: {elapsed:.2f}s")
    lines.append("")

    lines.append("## 各维度得分")
    lines.append("")
    lines.append("| 维度 | 得分 |")
    lines.append("|------|------|")
    for dim in ("bug", "code_smell", "engineering_maturity"):
        lines.append(f"| {CATEGORY_NAMES.get(dim, dim)} | {scores.get(dim, 0)}/100 |")
    lines.append("")

    lines.append("## 问题统计")
    lines.append("")
    lines.append("| 级别 | 数量 |")
    lines.append("|------|------|")
    lines.append(f"| 🔴 高危 | {error_count} |")
    lines.append(f"| 🟡 中危 | {warning_count} |")
    lines.append(f"| 🔵 低危 | {info_count} |")
    lines.append(f"| 💡 建议 | {suggestion_count} |")
    lines.append("")

    if active:
        lines.append("## 问题详情")
        lines.append("")
        # 按级别分组
        for level_label, level_filter in [
            ("高危", ("blocking", "error")),
            ("中危", ("problem", "warning")),
            ("低危", ("info",)),
            ("建议", ("suggestion",)),
        ]:
            group = [r for r in active if r.level in level_filter]
            if not group:
                continue
            lines.append(f"### {level_label} ({len(group)})")
            lines.append("")
            lines.append("| ID | 名称 | 文件 | 说明 |")
            lines.append("|----|------|------|------|")
            for r in group[:30]:  # 最多 30 条
                loc = r.location or {}
                file_str = ""
                if loc.get("file"):
                    file_str = f"`{loc['file']}`"
                    if loc.get("line"):
                        file_str += f":{loc['line']}"
                msg = (r.message or r.detail or "")[:80].replace("|", "\\|")
                lines.append(f"| {r.rule_id} | {r.rule_name} | {file_str} | {msg} |")
            if len(group) > 30:
                lines.append(f"| ... | 还有 {len(group)-30} 条 | | |")
            lines.append("")

    lines.append("---")
    lines.append(f"*由煋鉴 Xinpect 生成*")
    lines.append("")

    # 基础版引流提示
    lines.append("---")
    lines.append("")
    lines.append("💡 **提示：您正在使用基础版检测**")
    lines.append("")
    lines.append("B1~B3 基础检测可以帮您发现语法错误、低级安全漏洞和规范问题，")
    lines.append("但还有以下维度未覆盖：")
    lines.append("")
    lines.append("- 📊 性能问题（死循环、内存泄漏、低效查询…）")
    lines.append("- 📦 依赖漏洞（第三方包 CVE 风险…）")
    lines.append("- 🧩 代码质量（复杂度、重复率、可维护性…）")
    lines.append("- 🏗️ 架构设计（分层合理性、耦合度、模块化…）")
    lines.append("- 🔒 业务安全（越权、注入、数据泄露…）")
    lines.append("")
    lines.append("完整 8 维度检测请前往 煋鉴官网 获取。")

    return "\n".join(lines)
