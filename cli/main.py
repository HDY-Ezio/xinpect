#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLI 入口模块 (迁移自 qa_framework.py)
========================================
包含：
- main(): 主扫描流程（旧版单体引擎）
- generate_config_template(): 生成配置模板
- _parse_and_set_args(): 解析命令行参数
- _handle_ecosystem_command(): 生态闭环子命令处理

注意：main 函数大量依赖 qa_framework.py 中的全局变量和模块类。
为了零行为变更，采用延迟导入方式从 qa_framework 引入所有依赖。
"""

import os
import sys
import asyncio
from datetime import datetime

# 确保技能根目录在 sys.path 中
_SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SKILL_ROOT not in sys.path:
    sys.path.insert(0, _SKILL_ROOT)


def _load_qa_framework():
    """延迟导入 qa_framework，避免循环依赖"""
    import qa_framework as _qf
    return _qf


def generate_config_template(output_dir: str):
    """生成默认配置模板文件"""
    _qf = _load_qa_framework()
    DEFAULT_CONFIG = _qf.DEFAULT_CONFIG
    BRIEF_MODE = _qf.BRIEF_MODE
    import json
    config_path = os.path.join(output_dir, "qa_config_template.json")
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
    if not BRIEF_MODE:
        print(f"[配置] 模板已生成: {config_path}")
    return config_path


async def main():
    # 延迟导入 qa_framework 中的全局变量和模块类
    _qf = _load_qa_framework()
    
    # 全局状态变量
    BRIEF_MODE = _qf.BRIEF_MODE
    CONFIG_PATH = _qf.CONFIG_PATH
    PROJECT_PATH = _qf.PROJECT_PATH
    BACKEND_PATH = _qf.BACKEND_PATH
    RESULT_MODE = _qf.RESULT_MODE
    QA_MODE = _qf.QA_MODE
    QA_BASE_BRANCH = _qf.QA_BASE_BRANCH
    QA_BACKGROUND = _qf.QA_BACKGROUND
    QA_RULE_PATH = _qf.QA_RULE_PATH
    USE_NEW_ENGINE = _qf.USE_NEW_ENGINE
    ENGINE_MODE = _qf.ENGINE_MODE
    ENABLE_FP_FILTER = _qf.ENABLE_FP_FILTER
    ENABLE_DEEP_DIAGNOSIS = _qf.ENABLE_DEEP_DIAGNOSIS
    ENABLE_TELEMETRY = _qf.ENABLE_TELEMETRY
    ENABLE_INCREMENTAL = _qf.ENABLE_INCREMENTAL
    QA_LEVEL = _qf.QA_LEVEL
    NO_CACHE = _qf.NO_CACHE
    CACHE_CLEAR = _qf.CACHE_CLEAR
    NO_FAIL_FAST = _qf.NO_FAIL_FAST
    AI_FULL = _qf.AI_FULL
    PERF_REPORT = _qf.PERF_REPORT
    SINCE_REF = _qf.SINCE_REF
    PROJECT_TYPE_NAMES = _qf.PROJECT_TYPE_NAMES
    
    # 函数
    _check_and_activate = _qf._check_and_activate
    load_config = _qf.load_config
    generate_config_template = _qf.generate_config_template
    detect_project_type = _qf.detect_project_type
    is_module_applicable = _qf.is_module_applicable
    _build_project_profile = _qf._build_project_profile
    _get_cached_arch_info = _qf._get_cached_arch_info
    generate_report = _qf.generate_report
    _count_issues_and_passes = _qf._count_issues_and_passes
    _validate_and_fix_locations = _qf._validate_and_fix_locations
    calculate_category_scores = _qf.calculate_category_scores
    
    # 模块类
    Module1APILinkage = _qf.Module1APILinkage
    Module2PageNavigation = _qf.Module2PageNavigation
    Module3SecurityAudit = _qf.Module3SecurityAudit
    Module4DataConsistency = _qf.Module4DataConsistency
    Module5UIDesign = _qf.Module5UIDesign
    Module6CodeQuality = _qf.Module6CodeQuality
    Module7DeployReadiness = _qf.Module7DeployReadiness
    Module8BusinessFlow = _qf.Module8BusinessFlow
    Module11ChangeImpact = _qf.Module11ChangeImpact
    Module14TestInfrastructure = _qf.Module14TestInfrastructure
    Module15GitDiffReview = _qf.Module15GitDiffReview
    Module16ReflectionVerify = _qf.Module16ReflectionVerify
    Module17ArchitectureDependency = _qf.Module17ArchitectureDependency
    Module18AIDeepDiagnosis = _qf.Module18AIDeepDiagnosis
    Module19MiniprogramConfig = _qf.Module19MiniprogramConfig
    Module20UnitTestSuggestion = _qf.Module20UnitTestSuggestion
    Module21CodeSmellDetector = _qf.Module21CodeSmellDetector
    Module22SecurityPenetrationVerify = _qf.Module22SecurityPenetrationVerify
    RulePenetration = _qf.RulePenetration
    CheckResult = _qf.CheckResult

    sdk = None
    try:
        from codeact_sdk import CodeActSDK
        sdk = CodeActSDK()
    except ImportError:
        if not BRIEF_MODE:
            print("[警告] codeact_sdk不可用，将以纯脚本模式运行")

    # ===== 商业化：CLI激活流程 =====
    _check_and_activate()

    config = load_config(CONFIG_PATH)
    if not BRIEF_MODE:
        print(f"[配置] 加载完成, 阈值项={len(config['thresholds'])}")

    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(output_dir, exist_ok=True)

    if not CONFIG_PATH or not os.path.isfile(CONFIG_PATH):
        template_path = generate_config_template(output_dir)

    # Inject /tmp mapping if available
    if not config.get("reference_frontend_mapping") and os.path.isfile("/tmp/page_api_mapping.json"):
        config["reference_frontend_mapping"] = "/tmp/page_api_mapping.json"

    # ===== 项目类型检测 =====
    project_type = detect_project_type(PROJECT_PATH, BACKEND_PATH, _qf._args.project_type)
    type_name = PROJECT_TYPE_NAMES.get(project_type, project_type)
    if not BRIEF_MODE:
        print(f"[检测] 项目类型: {type_name} ({project_type})")

    # 模块适用性过滤
    MODULE_SKIP_REASONS = {
        "1": "API链路检查需要前端项目",
        "2": "页面导航检查需要前端项目",
        "4": "数据一致性检查需要前端+后端项目",
        "5": "UI设计检查需要前端项目(小程序/网页)",
        "8": "业务流程检查需要前端项目",
        "12": "性能与资源检查针对前端项目",
        "18": "AI深度诊断需要LLM配额",
        "19": "小程序配置合法性仅适用于小程序项目",
    }

    # ===== v18: 加载四层规则穿透配置 =====
    rule_penetration = RulePenetration(PROJECT_PATH or ".", QA_RULE_PATH)
    rule_penetration.load()
    # Merge background from rule config and CLI
    background = QA_BACKGROUND or rule_penetration.get_background()

    # ===== P0重构: 构建项目画像（供所有规则自适应调用） =====
    project_profile = _build_project_profile(PROJECT_PATH, BACKEND_PATH, config, project_type)
    if not BRIEF_MODE:
        print(f"[画像] 项目规模: {project_profile.scale_level}, 代码行: {project_profile.total_code_lines}, 页面: {project_profile.page_count}")
    if project_profile.main_package_size_mb > 0:
        if not BRIEF_MODE:
            print(f"[画像] 主包大小: {project_profile.main_package_size_mb}MB, 总包: {project_profile.total_package_size_mb}MB")
    if not BRIEF_MODE:
        print(f"[画像] 小项目判定: {'是' if project_profile.is_small_project() else '否'}")

    # ===== P1根因修复: 架构风格识别（先识别架构，再应用规则） =====
    arch_info = _get_cached_arch_info(PROJECT_PATH, BACKEND_PATH, config)
    if arch_info.get("style") != "unknown":
        if not BRIEF_MODE:
            print(f"[架构] 风格: {arch_info['style_name']} (置信度: {arch_info.get('confidence', 0):.0%})")
        if not BRIEF_MODE:
            print(f"[架构] 层数: {arch_info.get('layer_count', 0)}层, DDD规则: {'启用' if arch_info.get('is_ddd') else '跳过'}")
        if arch_info.get('ops_scripts'):
            if not BRIEF_MODE:
                print(f"[架构] 检测到{len(arch_info['ops_scripts'])}个运维补丁脚本，已排除质量扫描")
    else:
        if not BRIEF_MODE:
            print(f"[架构] 未能识别架构风格，将执行通用规则")

    # Register and run all modules
    # 根→叶诊断式执行顺序：根(部署)→干(安全)→枝(核心逻辑)→皮(代码结构)→叶(UI体验)→茸(性能)

    # ===== v2.0: 新引擎执行路径 =====
    if USE_NEW_ENGINE:
        if not BRIEF_MODE:
            print(f"[引擎] 使用v2.0新规则引擎 (模式: {ENGINE_MODE})")
        
        from core.hybrid_runner import HybridQARunner
        from core.runner import RuleRunner
        from core.context import QAContext as NewQAContext
        
        # 创建新引擎上下文
        new_ctx = NewQAContext(
            project_path=PROJECT_PATH,
            backend_path=BACKEND_PATH,
            config=config,
            project_type=project_type if project_type != "auto" else "auto",
            mode="quick",
        )
        new_ctx.build_profile()
        if not BRIEF_MODE:
            print(f"[引擎] 项目类型: {new_ctx.project_type_name}, 规则加载中...")
        
        if ENGINE_MODE == "new":
            # 纯新规则引擎（仅执行rules/目录下的173条新规则）
            runner = RuleRunner(
                context=new_ctx,
                enable_fp_filter=ENABLE_FP_FILTER,
                enable_deep_diagnosis=ENABLE_DEEP_DIAGNOSIS,
                enable_telemetry=ENABLE_TELEMETRY,
                incremental=ENABLE_INCREMENTAL,
                fp_mode="quick",
                diagnosis_mode="quick",
                sdk=sdk,
            )
            runner.rule_loader.load_all()
            if not BRIEF_MODE:
                print(f"[引擎] 纯新模式: 加载 {runner.rule_loader.rule_count} 条规则")
            
            results = runner.run_all()
            total_issues = runner.active_checks
            fp_count = runner.fp_count
            errors = runner.error_count
            warnings = runner.warning_count
            skipped_modules_new = {}
            
            # 标记所有旧模块为跳过（新引擎模式）
            for mid in ["1","2","3","4","5","6","7","8","9","10","11","12","13","14","15","16","17","18","19","20","21","22"]:
                if mid not in results:
                    skipped_modules_new[mid] = "新引擎模式 - 由规则引擎统一执行"
            
            # 生成报告
            from core.reporter import ResultReporter
            reporter = ResultReporter(runner)
            report = reporter.generate_markdown_report(
                project_path=PROJECT_PATH,
                config=config,
                project_type=type_name,
                skipped_modules=skipped_modules_new,
            )
            scores = runner.calculate_scores()
            
        elif ENGINE_MODE == "old":
            # 仅旧模块模式（和默认行为一致，用于对比测试）
            if not BRIEF_MODE:
                print("[引擎] 仅旧模块模式 - 执行原有模块")
            # 继续执行下面的旧模块代码
            pass
            
        else:  # hybrid 模式
            # 混合模式：新规则 + 旧模块适配器
            hybrid_runner = HybridQARunner(
                project_path=PROJECT_PATH,
                backend_path=BACKEND_PATH,
                config=config,
                project_type=project_type if project_type != "auto" else "auto",
                mode="quick",
                enable_fp_filter=ENABLE_FP_FILTER,
                enable_deep_diagnosis=ENABLE_DEEP_DIAGNOSIS,
                enable_telemetry=ENABLE_TELEMETRY,
                incremental=ENABLE_INCREMENTAL,
                sdk=sdk,
            )
            if not BRIEF_MODE:
                print(f"[引擎] 混合模式: {hybrid_runner.rule_loader.rule_count} 条新规则 + 旧模块适配器")
            
            results = hybrid_runner.run()
            total_issues = hybrid_runner.total_checks
            errors = hybrid_runner.error_count
            warnings = hybrid_runner.warning_count
            
            # 生成报告
            report = hybrid_runner.generate_report(
                project_path=PROJECT_PATH,
                config=config,
                project_type=type_name,
            )
            scores = hybrid_runner.calculate_scores()
        
        # 保存报告
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = os.path.join(output_dir, f"qa_report_{timestamp}.md")
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report)
        if not BRIEF_MODE:
            print(f"[报告] 已生成: {report_path}")
        
        # 生成HTML可视化报告
        try:
            from core.html_report import generate_html_report
            html_path = generate_html_report(runner, output_dir=output_dir, project_path=PROJECT_PATH, project_type=type_name)
            if html_path:
                print(f"[报告] HTML报告: {html_path}")
        except Exception as e:
            print(f"[报告] HTML报告生成失败(不影响MD报告): {e}")
        
        # 输出摘要
        total_score = scores.get('total', 0)
        print(f"\n[结果] 综合评分: {total_score}/100")
        print(f"[结果] Bug维度: {scores.get('bug', 0)}/100, Code Smell: {scores.get('code_smell', 0)}/100, 工程成熟度: {scores.get('engineering_maturity', 0)}/100")
        print(f"[结果] 阻断: {errors}, 警告: {warnings}")
        print(f"[结果] 完整报告: {report_path}")
        
        # 提交结果到SDK（如果可用）
        if sdk:
            try:
                sdk.set_result({
                    "score": total_score,
                    "errors": errors,
                    "warnings": warnings,
                    "report_path": report_path,
                    "engine": "v2.0",
                    "engine_mode": ENGINE_MODE,
                })
            except Exception as e:  # noqa: intentional catch-all
                if not BRIEF_MODE:
                    print(f"[提交] SDK提交失败: {e}")
        
        return
    
    # ===== 旧引擎执行路径（默认，保持向后兼容）=====
    all_modules = [
        Module7DeployReadiness(PROJECT_PATH, BACKEND_PATH, config, project_type, project_profile),    # 根 - 部署就绪
        Module3SecurityAudit(PROJECT_PATH, BACKEND_PATH, config, project_type, project_profile),      # 干 - 安全审计
        Module4DataConsistency(PROJECT_PATH, BACKEND_PATH, config, project_type, project_profile),    # 枝 - 数据一致性
        Module1APILinkage(PROJECT_PATH, BACKEND_PATH, config, project_type, project_profile),         # 枝 - API链路
        Module8BusinessFlow(PROJECT_PATH, BACKEND_PATH, config, project_type, project_profile),       # 枝 - 业务流程
        Module6CodeQuality(PROJECT_PATH, BACKEND_PATH, config, project_type, project_profile),        # 皮 - 代码质量
        Module2PageNavigation(PROJECT_PATH, BACKEND_PATH, config, project_type, project_profile),     # 叶 - 页面导航
        Module5UIDesign(PROJECT_PATH, BACKEND_PATH, config, project_type, project_profile),           # 叶 - UI设计(28项)
        Module11ChangeImpact(PROJECT_PATH, BACKEND_PATH, config, project_type, project_profile),      # 茸 - 变更影响
        Module14TestInfrastructure(PROJECT_PATH, BACKEND_PATH, config, project_type, project_profile), # 茸 - 测试CI
        Module15GitDiffReview(PROJECT_PATH, BACKEND_PATH, config, project_type,
                              mode=QA_MODE, base_branch=QA_BASE_BRANCH, background=background),  # v18 - 增量审查
        Module17ArchitectureDependency(PROJECT_PATH, BACKEND_PATH, config, project_type, project_profile),         # v19 - 架构依赖方向
    ]

    # 按项目类型过滤不适用的模块
    modules = []
    skipped_modules = {}
    for mod in all_modules:
        if is_module_applicable(mod.module_id, project_type):
            modules.append(mod)
        else:
            reason = MODULE_SKIP_REASONS.get(mod.module_id, f"不适用于{type_name}")
            skipped_modules[mod.module_id] = reason
            if not BRIEF_MODE:
                print(f"[跳过] 模块{mod.module_id} {mod.module_name}: {reason}")

    all_results: Dict[str, List[CheckResult]] = {}
    if not BRIEF_MODE:
        print(f"[调度] 开始执行 {len(modules)} 个模块检查(共{len(all_modules)}个，跳过{len(skipped_modules)}个)...")

    for mod in modules:
        if not BRIEF_MODE:
            print(f"[模块{mod.module_id}] {mod.module_name}...")
        try:
            results = mod.run()
            all_results[mod.module_id] = results
            error_n = sum(1 for r in results if r.level == "error")
            warn_n = sum(1 for r in results if r.level == "warning")
            print(f"  -> {len(results)}项检查, {error_n}阻断, {warn_n}警告")
        except Exception as e:  # noqa: intentional catch-all
            if not BRIEF_MODE:
                print(f"  -> 执行异常: {e}")
            all_results[mod.module_id] = [CheckResult(
                f"{mod.module_id}.0", mod.module_name, "error", f"模块执行异常: {e}"
            )]

    # ===== v18: M16 反思验证（依赖其他模块的审查结果） =====
    if is_module_applicable("16", project_type):
        if not BRIEF_MODE:
            print(f"[模块16] 反思验证...")
        try:
            m16 = Module16ReflectionVerify(PROJECT_PATH, BACKEND_PATH, config, project_type, project_profile=project_profile,
                                           review_results=all_results, background=background)
            m16_results = m16.run()
            all_results["16"] = m16_results
            error_n = sum(1 for r in m16_results if r.level == "error")
            warn_n = sum(1 for r in m16_results if r.level == "warning")
            print(f"  -> {len(m16_results)}项检查, {error_n}阻断, {warn_n}警告")
        except Exception as e:  # noqa: intentional catch-all
            if not BRIEF_MODE:
                print(f"  -> 执行异常: {e}")
            all_results["16"] = [CheckResult("16.0", "反思验证", "error", f"模块执行异常: {e}")]

    # ===== 模块19: 小程序配置合法性 =====
    if is_module_applicable("19", project_type):
        if not BRIEF_MODE:
            print(f"[模块19] 小程序配置合法性...")
        try:
            m19 = Module19MiniprogramConfig(PROJECT_PATH, BACKEND_PATH, config, project_type, project_profile)
            m19_results = m19.run()
            all_results["19"] = m19_results
            error_n = sum(1 for r in m19_results if r.level == "error")
            warn_n = sum(1 for r in m19_results if r.level == "warning")
            print(f"  -> {len(m19_results)}项检查, {error_n}阻断, {warn_n}警告")
        except Exception as e:  # noqa: intentional catch-all
            if not BRIEF_MODE:
                print(f"  -> 执行异常: {e}")
            all_results["19"] = [CheckResult("19.0", "小程序配置合法性", "error", f"模块执行异常: {e}")]

    # ===== v20: M18 AI深度诊断（依赖LLM，异步执行） =====
    if is_module_applicable("18", project_type):
        if not BRIEF_MODE:
            print(f"[模块18] AI深度诊断...")
        try:
            m18 = Module18AIDeepDiagnosis(PROJECT_PATH, BACKEND_PATH, config, project_type, project_profile=project_profile,
                                          sdk=sdk, background=background)
            m18_results = await m18.run()
            all_results["18"] = m18_results
            error_n = sum(1 for r in m18_results if r.level == "error")
            warn_n = sum(1 for r in m18_results if r.level == "warning")
            print(f"  -> {len(m18_results)}项检查, {error_n}阻断, {warn_n}警告")
        except Exception as e:  # noqa: intentional catch-all
            if not BRIEF_MODE:
                print(f"  -> 执行异常: {e}")
            all_results["18"] = [CheckResult("18.0", "AI深度诊断", "error", f"模块执行异常: {e}")]

    # ===== v21: M20 单元测试建议 =====
    if is_module_applicable("20", project_type):
        if not BRIEF_MODE:
            print(f"[模块20] 单元测试建议...")
        try:
            m20 = Module20UnitTestSuggestion(PROJECT_PATH, BACKEND_PATH, config, project_type, project_profile)
            m20_results = m20.run()
            all_results["20"] = m20_results
            error_n = sum(1 for r in m20_results if r.level == "error")
            warn_n = sum(1 for r in m20_results if r.level == "warning")
            print(f"  -> {len(m20_results)}项检查, {error_n}阻断, {warn_n}警告")
        except Exception as e:  # noqa: intentional catch-all
            if not BRIEF_MODE:
                print(f"  -> 执行异常: {e}")
            all_results["20"] = [CheckResult("20.0", "单元测试建议", "error", f"模块执行异常: {e}")]

    # ===== v21: M21 代码坏味道检测 =====
    if is_module_applicable("21", project_type):
        if not BRIEF_MODE:
            print(f"[模块21] 代码坏味道检测...")
        try:
            m21 = Module21CodeSmellDetector(PROJECT_PATH, BACKEND_PATH, config, project_type, project_profile)
            m21_results = m21.run()
            all_results["21"] = m21_results
            error_n = sum(1 for r in m21_results if r.level == "error")
            warn_n = sum(1 for r in m21_results if r.level == "warning")
            print(f"  -> {len(m21_results)}项检查, {error_n}阻断, {warn_n}警告")
        except Exception as e:  # noqa: intentional catch-all
            if not BRIEF_MODE:
                print(f"  -> 执行异常: {e}")
            all_results["21"] = [CheckResult("21.0", "代码坏味道检测", "error", f"模块执行异常: {e}")]

    # ===== v21: M22 安全渗透验证 =====
    if is_module_applicable("22", project_type):
        if not BRIEF_MODE:
            print(f"[模块22] 安全渗透验证...")
        try:
            m22 = Module22SecurityPenetrationVerify(PROJECT_PATH, BACKEND_PATH, config, project_type, project_profile)
            m22_results = m22.run()
            all_results["22"] = m22_results
            error_n = sum(1 for r in m22_results if r.level == "error")
            warn_n = sum(1 for r in m22_results if r.level == "warning")
            print(f"  -> {len(m22_results)}项检查, {error_n}阻断, {warn_n}警告")
        except Exception as e:  # noqa: intentional catch-all
            if not BRIEF_MODE:
                print(f"  -> 执行异常: {e}")
            all_results["22"] = [CheckResult("22.0", "安全渗透验证", "error", f"模块执行异常: {e}")]

    # Generate report
    # P0修复: 全局行号校验和修正，确保所有行号引用在有效范围内
    all_results, location_fix_count = _validate_and_fix_locations(
        all_results, PROJECT_PATH, BACKEND_PATH
    )
    if location_fix_count > 0:
        if not BRIEF_MODE:
            print(f"[修正] 行号定位校验: 修正了{location_fix_count}处超出文件范围的行号引用")
    
    report = generate_report(all_results, PROJECT_PATH, config, project_type, skipped_modules)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(output_dir, f"qa_report_{timestamp}.md")
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    if not BRIEF_MODE:
        print(f"[报告] 已生成: {report_path}")

    # ===== v3.0.0: 记录扫描数据到规则有效性追踪器 =====
    try:
        from core.rule_effectiveness import RuleEffectivenessTracker
        _ret = RuleEffectivenessTracker()
        _all_issue_list = []
        for _mid, _results in all_results.items():
            for _r in _results:
                _cid = getattr(_r, 'check_id', str(_mid))
                _loc = getattr(_r, 'location', {}) or {}
                _all_issue_list.append({'check_id': _cid, 'file': _loc.get('file', ''), 'line': _loc.get('line', 0)})
        _ret.record_scan(_all_issue_list, project_type=str(project_type))
    except Exception as e:  # noqa: intentional catch-all
        pass  # noqa: intentional catch-all  # 静默处理，不影响主流程

    # Summary
    total = sum(len(r) for r in all_results.values())
    errors = sum(1 for results in all_results.values() for r in results if r.level == "error")
    warnings = sum(1 for results in all_results.values() for r in results if r.level == "warning")
    # P0重构: 使用三维评分系统
    _flat_for_score = []
    for _mid, _results in all_results.items():
        for _r in _results:
            _flat_for_score.append((_mid, _r))
    _cat_scores = calculate_category_scores(_flat_for_score)
    score = _cat_scores["total"]
    bug_score = _cat_scores["bug"]
    smell_score = _cat_scores["code_smell"]
    eng_score = _cat_scores["engineering_maturity"]

    # 生成HTML可视化报告
    try:
        from core.html_report import generate_html_report
        html_scores = {"total": score, "bug": bug_score, "code_smell": smell_score, "engineering_maturity": eng_score}
        html_path = generate_html_report(output_dir=output_dir, project_path=PROJECT_PATH, project_type=type_name, all_results=all_results, scores=html_scores)
        if html_path:
            print(f"[报告] HTML报告: {html_path}")
    except Exception as e:
        print(f"[报告] HTML报告生成失败(不影响MD报告): {e}")

    # 计算等级
    if score >= 90:
        grade = "优秀"
    elif score >= 70:
        grade = "良好"
    elif score >= 50:
        grade = "需整改"
    elif score >= 30:
        grade = "严重"
    else:
        grade = "极严重"

    # 统计各级别（区分问题和通过项）
    main_issues, main_passes, main_pass_by_cat, main_suggestions = _count_issues_and_passes(all_results)
    total_issues = main_issues["error"] + main_issues["warning"]

    msg_lines = [f"QA检测完成 | 综合评分 {score}/100 | {grade}"]
    msg_lines.append(f"项目类型：{type_name}")
    msg_lines.append(f"问题 {total_issues}（高危{main_issues['error']} | 中危{main_issues['warning']}）| 💡建议 {main_suggestions} | 通过 {main_passes} 项 | 总检查 {total}")

    # 高危问题Top5
    if main_issues["error"] > 0:
        msg_lines.append("")
        msg_lines.append("高危问题：")
        _count = 0
        for _mid, _results in all_results.items():
            for _r in _results:
                if _r.level == "error" and _count < 5:
                    _f = f" ({_r.location.get('file', '')})" if hasattr(_r, 'location') and _r.location and _r.location.get('file') else ""
                    msg_lines.append(f"  {_count+1}. {_r.check_id} {_r.name}{_f}")
                    _count += 1

    msg_lines.append(f"报告：{report_path}")
    message = "\n".join(msg_lines)
    actual_mode = RESULT_MODE if RESULT_MODE != "auto" else "notify"

    if sdk:
        try:
            await sdk.submit_result(
                result_mode=actual_mode,
                status="success",
                message=message,
                data={
                    "score": score,
                    "total_checks": total,
                    "errors": errors,
                    "warnings": warnings,
                    "total_issues": total_issues,
                    "passes": main_passes,
                    "report_path": report_path,
                },
            )
        except Exception as e:  # noqa: intentional catch-all
            if not BRIEF_MODE:
                print(f"[提交] SDK提交失败: {e}")
            print(f"[结果] {message}")
    else:
        print(f"[结果] {message}")

    # ===== 积分扣减（扫描完成后，无论哪个引擎）=====
    _xinpect_email = os.environ.get("XINPECT_USER_EMAIL", "")
    _xinpect_menfang = os.environ.get("XINPECT_SERVER_URL", os.environ.get("MENFANG_URL", "https://xinpect.xingwangzhineng.com"))
    if _xinpect_email:
        try:
            from coze_workload_identity import requests as _req
            _scan_credits = max(10, total * 2)  # 每次扫描至少10积分
            _resp = _req.post(
                f"{_xinpect_menfang}/api/credits/deduct",
                json={
                    "email": _xinpect_email,
                    "credits": _scan_credits,
                    "reason": "煋鉴AI代码审查",
                    "scan_id": f"scan_{timestamp}",
                    "project": "xinpect",
                },
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            if _resp.status_code == 200:
                _r = _resp.json()
                print(f"[积分] 本次扫描消耗 {_scan_credits} 积分，剩余 {_r.get("balance", "?")}")
            else:
                print(f"[积分] 扣减失败: HTTP {_resp.status_code}")
        except Exception as _e:
            print(f"[积分] 扣减异常: {_e}")
