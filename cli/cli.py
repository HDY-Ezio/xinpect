#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
煋鉴 Xinpect CLI — 子命令化入口 (v4.5)
========================================

子命令：
  xinpect scan [path]     扫描项目
  xinpect init [path]     生成配置文件
  xinpect rules [keyword] 查看规则列表
  xinpect config          查看/校验当前配置
  xinpect version         输出版本号

零行为变更原则：所有子命令内部复用 cli/main.py 的主流程，
仅做参数映射和输出包装。旧的 `python qa_framework.py ...` 
方式完全兼容，不受影响。
"""

import os
import sys
import argparse
import json
import asyncio

# 确保技能根目录在 sys.path 中
_SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SKILL_ROOT not in sys.path:
    sys.path.insert(0, _SKILL_ROOT)

__version__ = "4.6.0"
__release_date__ = "2026-08-06"
__engine_version__ = "21.0.3"


# ============================================================
# 子命令：scan — 扫描项目
# ============================================================

def cmd_scan(args) -> int:
    """执行扫描子命令
    
    v4.5: 新增新引擎 (RuleRunner) 支持
      - engine-mode == "new"     → 走 RuleRunner（默认，2600+ 规则 / 8 大脑）
      - engine-mode == "legacy"  → 走旧 qa_framework 引擎（兼容）
      - engine-mode == "hybrid"  → 两个引擎都跑（对比模式）
    """
    # 新引擎模式：直接走 RuleRunner 适配层
    if args.engine_mode in ("new", "hybrid"):
        from cli.new_engine_scan import run_new_engine_scan
        from cli.utils import color_bold

        path = args.path or "."
        new_result = run_new_engine_scan(
            path=path,
            level=args.level,
            config_path=args.config,
            rule_path=args.rule,
            enable_fp_filter=not args.no_fp_filter,
            enable_deep_diagnosis=not args.no_deep_diagnosis,
            incremental=not args.no_incremental,
            project_type=args.project_type,
            output_dir=args.output,
            output_format=args.format,
            only_level=args.only,
            brief=args.brief and not args.verbose,
            verbose=args.verbose,
            ai_full=args.ai_full,
            perf_report=args.perf_report,
            no_cache=args.no_cache,
            cache_clear=args.cache_clear,
            since_ref=args.since,
            rule_health=args.rule_health,
        )

        # new 模式直接返回；hybrid 模式继续跑旧引擎做对比
        if args.engine_mode == "new":
            return new_result

        # hybrid：打印分隔线，再跑旧引擎
        print()
        print("  " + "═" * 50)
        print(f"  {color_bold('双引擎对比模式')} — 下面是旧引擎 (qa_framework) 结果")
        print("  " + "═" * 50)
        print()

    # ---- 旧引擎 / hybrid 下半部分：沿用 qa_framework 主流程 ----
    # 延迟导入，避免循环依赖
    import qa_framework as qf
    from cli.main import main as scan_main
    
    # 第一步：用空参数初始化所有默认值和 _args 对象
    # 先备份 sys.argv，避免 _parse_and_set_args 读到子命令的 argv
    orig_argv = sys.argv
    sys.argv = [orig_argv[0]]  # 只留程序名，参数为空
    try:
        qf._parse_and_set_args()
    finally:
        sys.argv = orig_argv
    
    # 第二步：覆盖用户在子命令中指定的参数
    path = args.path or "."
    qf.PROJECT_PATH = os.path.abspath(path)
    
    # 配置文件
    if args.config:
        qf.CONFIG_PATH = args.config
    
    # 自定义规则文件
    if args.rule:
        qf.QA_RULE_PATH = args.rule
    
    # 扫描级别
    qf.QA_LEVEL = args.level
    
    # 引擎模式
    qf.ENGINE_MODE = args.engine_mode
    qf.USE_NEW_ENGINE = (args.engine_mode == "new")
    
    # 误报过滤
    qf.ENABLE_FP_FILTER = not args.no_fp_filter
    
    # 深度诊断
    qf.ENABLE_DEEP_DIAGNOSIS = not args.no_deep_diagnosis
    
    # 缓存
    qf.NO_CACHE = args.no_cache
    qf.CACHE_CLEAR = args.cache_clear
    
    # 增量模式
    qf.ENABLE_INCREMENTAL = not args.no_incremental
    qf.SINCE_REF = args.since
    
    # AI 全量诊断
    qf.AI_FULL = args.ai_full
    
    # 性能报告
    qf.PERF_REPORT = args.perf_report
    
    # 输出模式
    if args.verbose:
        qf.BRIEF_MODE = False
    elif args.brief:
        qf.BRIEF_MODE = True
    
    # 项目类型
    if args.project_type:
        qf._args.project_type = args.project_type
    
    # 结果模式（保持默认 notify）
    qf.RESULT_MODE = "notify"
    
    # 执行扫描
    from cli.utils import (
        color_bold, color_info, color_pass, color_high,
        render_summary_table,
    )
    
    # 打印 banner（hybrid 模式下不重复打印）
    if args.engine_mode != "hybrid":
        print()
        print(f"  {color_bold('🔥 煋鉴 Xinpect')} v{__version__}  —  AI 代码安全官")
        print(f"  {color_info('扫描路径')}: {os.path.abspath(path)}")
        if qf.CONFIG_PATH:
            print(f"  {color_info('配置文件')}: {qf.CONFIG_PATH}")
        if qf.QA_LEVEL != "standard":
            print(f"  {color_info('扫描级别')}: {qf.QA_LEVEL}")
        print()
    
    try:
        asyncio.run(scan_main())
        return 0
    except Exception as e:
        print(f"{color_high('扫描失败')}: {e}")
        return 2


# ============================================================
# 子命令：init — 生成配置文件
# ============================================================

def cmd_init(args) -> int:
    """生成 .xinpectrc.json 配置模板"""
    path = args.path or "."
    target_dir = os.path.abspath(path)
    
    # 目录不存在则自动创建
    if not os.path.isdir(target_dir):
        os.makedirs(target_dir, exist_ok=True)
    
    config_file = os.path.join(target_dir, ".xinpectrc.json")
    
    # 如果已有配置，提示
    if os.path.isfile(config_file):
        print(f"配置文件已存在: {config_file}")
        print("如需重新生成，请先删除现有文件。")
        return 0
    
    # 从 qa_framework 导入默认配置
    try:
        import qa_framework as qf
        default_config = qf.DEFAULT_CONFIG
    except Exception:
        # 兜底默认配置
        default_config = {
            "thresholds": {
                "nav_depth_max": 3,
                "function_lines_warning": 80,
                "function_lines_error": 150,
                "duplication_similarity": 0.8,
                "main_package_size_mb": 2,
                "total_package_size_mb": 20,
                "large_image_kb_warning": 100,
                "large_image_kb_error": 300,
                "setdata_kb_warning": 256,
                "wxml_node_warning": 200,
            },
            "exclude_dirs": ["node_modules", "dist", "build", ".git"],
            "exclude_files": ["*.min.js", "*.bundle.js"],
        }
    
    # 写入配置模板
    try:
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=2, ensure_ascii=False)
            f.write("\n")
        
        from cli.utils import color_pass, color_info
        print(f"{color_pass('✓')} 配置文件已生成: {color_info(config_file)}")
        print()
        print("  配置项说明：")
        print("    thresholds.*        — 各检查项阈值")
        print("    exclude_dirs        — 排除目录列表")
        print("    exclude_files       — 排除文件模式")
        print()
        print("  下次扫描时可通过 --config 指定配置文件：")
        print(f"    xinpect scan --config {config_file} {target_dir}")
        return 0
    except Exception as e:
        print(f"生成配置文件失败: {e}")
        return 1


# ============================================================
# 子命令：rules — 查看规则列表
# ============================================================

def cmd_rules(args) -> int:
    """列出规则"""
    from cli.utils import render_rules_table, color_bold, color_info
    
    keyword = args.keyword or ""
    lang_filter = args.lang or "all"
    severity_filter = args.severity or ""
    category_filter = args.category or ""
    
    # 加载规则
    try:
        from core.rule_loader import RuleLoader
        rules_dir = os.path.join(_SKILL_ROOT, "rules")
        loader = RuleLoader(rules_dir=rules_dir)
        loader.load_all()
        rules = loader.all_rules  # property，不是方法
    except Exception as e:
        import traceback
        print(f"加载规则失败: {e}")
        traceback.print_exc()
        return 1
    
    # 按语言筛选
    if lang_filter != "all":
        lang_map = {
            "python": ["python", "python_backend", "flask", "django"],
            "web": ["web", "miniprogram", "electron", "react_native", "mixed"],
            "miniprogram": ["miniprogram"],
        }
        target_types = lang_map.get(lang_filter, [])
        if target_types:
            rules = [
                r for r in rules
                if not r.applicable_types or any(t in r.applicable_types for t in target_types)
            ]
    
    # 按严重级别筛选
    if severity_filter:
        sev_map = {
            "high": ["blocking", "error"],
            "medium": ["problem", "warning"],
            "low": ["info"],
            "suggestion": ["suggestion"],
        }
        target_sev = sev_map.get(severity_filter, [severity_filter])
        rules = [r for r in rules if r.level in target_sev]
    
    # 按类别筛选
    if category_filter:
        cat_map = {
            "security": ["security", "安全"],
            "bug": ["bug", "缺陷"],
            "quality": ["code_smell", "代码质量"],
            "perf": ["performance", "性能"],
            "architecture": ["architecture", "架构"],
        }
        target_cat = cat_map.get(category_filter, [category_filter])
        rules = [
            r for r in rules
            if r.category in target_cat or any(c in r.category for c in target_cat)
        ]
    
    # 按关键词模糊搜索
    if keyword:
        kw = keyword.lower()
        rules = [
            r for r in rules
            if kw in r.id.lower()
            or kw in r.name.lower()
            or kw in r.description.lower()
        ]
    
    # 输出
    print()
    print(f"  {color_bold('📋 规则列表')}  —  共 {len(rules)} 条")
    if lang_filter != "all":
        print(f"  {color_info('语言筛选')}: {lang_filter}")
    if severity_filter:
        print(f"  {color_info('级别筛选')}: {severity_filter}")
    if category_filter:
        print(f"  {color_info('类别筛选')}: {category_filter}")
    if keyword:
        print(f"  {color_info('关键词')}: {keyword}")
    print()
    
    table = render_rules_table(rules, show_details=False)
    for line in table.split("\n"):
        print("  " + line)
    
    print()
    print(f"  使用 {color_info('xinpect scan')} 对项目执行扫描")
    print()
    
    return 0


# ============================================================
# 子命令：config — 查看/校验配置
# ============================================================

def cmd_config(args) -> int:
    """查看或校验配置文件"""
    from cli.utils import color_bold, color_info, color_pass, color_high
    
    # 确定配置文件路径
    config_path = args.config or ""
    if not config_path:
        # 依次查找：当前目录 .xinpectrc.json → qa_config.json
        candidates = [
            os.path.join(os.getcwd(), ".xinpectrc.json"),
            os.path.join(os.getcwd(), "qa_config.json"),
            os.path.join(_SKILL_ROOT, "qa_config.json"),
        ]
        for c in candidates:
            if os.path.isfile(c):
                config_path = c
                break
    
    if args.validate:
        # 校验模式
        if not config_path or not os.path.isfile(config_path):
            print(f"{color_high('✗')} 未找到配置文件")
            return 1
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # 基本校验
            errors = []
            warnings = []
            
            if not isinstance(config, dict):
                errors.append("配置文件根节点必须是对象")
            else:
                if "thresholds" not in config:
                    warnings.append("缺少 thresholds 节，将使用默认阈值")
                elif not isinstance(config["thresholds"], dict):
                    errors.append("thresholds 必须是对象")
            
            if errors:
                print(f"{color_high('✗')} 配置校验失败：")
                for e in errors:
                    print(f"    - {e}")
                return 1
            
            print(f"{color_pass('✓')} 配置文件校验通过")
            print(f"  文件: {color_info(config_path)}")
            if warnings:
                print(f"  警告:")
                for w in warnings:
                    print(f"    - {w}")
            return 0
            
        except json.JSONDecodeError as e:
            print(f"{color_high('✗')} JSON 解析失败: {e}")
            return 1
        except Exception as e:
            print(f"{color_high('✗')} 校验异常: {e}")
            return 1
    
    # show 模式（默认）
    if not config_path or not os.path.isfile(config_path):
        print(f"未找到配置文件")
        print()
        print(f"  使用 {color_info('xinpect init')} 生成配置模板")
        return 0
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        print()
        print(f"  {color_bold('⚙️ 当前配置')}")
        print(f"  {color_info('文件')}: {config_path}")
        print()
        
        config_str = json.dumps(config, indent=2, ensure_ascii=False)
        for line in config_str.split("\n"):
            print(f"  {line}")
        print()
        return 0
    except Exception as e:
        print(f"读取配置失败: {e}")
        return 1


# ============================================================
# 子命令：version — 输出版本号
# ============================================================

def cmd_version(args) -> int:
    """输出版本信息"""
    from cli.utils import render_version
    print()
    print("  " + render_version(__version__, __release_date__, __engine_version__))
    print()
    return 0


# ============================================================
# 主入口：参数解析 + 子命令分发
# ============================================================

def _build_parser() -> argparse.ArgumentParser:
    """构建 argparse 解析器"""
    parser = argparse.ArgumentParser(
        prog="xinpect",
        description="煋鉴 Xinpect — AI 代码安全官 (v{})".format(__version__),
        epilog="示例:\n"
               "  xinpect scan .                    # 扫描当前目录\n"
               "  xinpect scan --level quick .      # 快速扫描\n"
               "  xinpect init /path/to/project     # 生成配置模板\n"
               "  xinpect rules --lang python       # 查看 Python 规则\n"
               "  xinpect version                   # 查看版本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    subparsers = parser.add_subparsers(dest="command", help="可用子命令")
    
    # ---------- scan ----------
    scan_parser = subparsers.add_parser(
        "scan", 
        help="扫描项目",
        description="对指定路径的项目执行代码审查"
    )
    scan_parser.add_argument("path", nargs="?", default=".", help="项目路径（默认当前目录）")
    scan_parser.add_argument("--config", "-c", default="", help="配置文件路径")
    scan_parser.add_argument("--rule", "-r", default="", help="自定义规则文件路径")
    scan_parser.add_argument(
        "--level", 
        default="standard",
        choices=["quick", "standard", "full"],
        help="扫描级别（默认 standard）"
    )
    scan_parser.add_argument(
        "--engine-mode",
        default="new",
        choices=["hybrid", "new", "legacy"],
        help="引擎模式（默认 new：使用 RuleRunner 新引擎；legacy：旧 qa_framework 引擎；hybrid：双引擎对比）"
    )
    scan_parser.add_argument(
        "--only",
        default="",
        choices=["high", "medium", "low", "suggestion", ""],
        help="只显示某级别问题"
    )
    scan_parser.add_argument(
        "--format", "-f",
        default="cli",
        choices=["cli", "md", "html", "json"],
        help="输出格式（默认 cli）"
    )
    scan_parser.add_argument("--output", "-o", default="", help="输出目录")
    scan_parser.add_argument("--no-fp-filter", action="store_true", help="关闭误报过滤")
    scan_parser.add_argument("--no-deep-diagnosis", action="store_true", help="关闭深度诊断")
    scan_parser.add_argument("--no-cache", action="store_true", help="禁用缓存")
    scan_parser.add_argument("--cache-clear", action="store_true", help="清除缓存后扫描")
    scan_parser.add_argument("--no-incremental", action="store_true", help="禁用增量模式")
    scan_parser.add_argument("--since", default="HEAD~1", help="增量模式基准（默认 HEAD~1）")
    scan_parser.add_argument("--ai-full", action="store_true", help="全量 AI 诊断")
    scan_parser.add_argument("--perf-report", action="store_true", help="输出性能报告")
    scan_parser.add_argument("--brief", "-q", action="store_true", default=True, help="精简输出（默认）")
    scan_parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    scan_parser.add_argument("--project-type", default="", help="强制指定项目类型")
    scan_parser.add_argument(
        "--rule-health",
        action="store_true",
        help="执行规则性能体检（慢规则检测），扫描前对所有正则规则跑大文件压测",
    )
    scan_parser.set_defaults(func=cmd_scan)
    
    # ---------- init ----------
    init_parser = subparsers.add_parser(
        "init",
        help="生成配置文件",
        description="在目标目录生成 .xinpectrc.json 配置模板"
    )
    init_parser.add_argument("path", nargs="?", default=".", help="目标目录（默认当前目录）")
    init_parser.set_defaults(func=cmd_init)
    
    # ---------- rules ----------
    rules_parser = subparsers.add_parser(
        "rules",
        help="查看规则列表",
        description="列出所有可用规则，支持筛选和搜索"
    )
    rules_parser.add_argument("keyword", nargs="?", default="", help="关键词（模糊搜索）")
    rules_parser.add_argument(
        "--lang",
        default="all",
        choices=["python", "web", "miniprogram", "all"],
        help="按语言筛选（默认 all）"
    )
    rules_parser.add_argument(
        "--severity",
        default="",
        choices=["high", "medium", "low", "suggestion", ""],
        help="按严重级别筛选"
    )
    rules_parser.add_argument(
        "--category",
        default="",
        choices=["security", "bug", "quality", "perf", "architecture", ""],
        help="按类别筛选"
    )
    rules_parser.set_defaults(func=cmd_rules)
    
    # ---------- config ----------
    config_parser = subparsers.add_parser(
        "config",
        help="查看/校验当前配置",
        description="显示或校验当前生效的配置文件"
    )
    config_parser.add_argument("--config", "-c", default="", help="配置文件路径")
    config_parser.add_argument("--show", action="store_true", default=True, help="显示当前配置（默认）")
    config_parser.add_argument("--validate", action="store_true", help="校验配置文件合法性")
    config_parser.set_defaults(func=cmd_config)
    
    # ---------- version ----------
    version_parser = subparsers.add_parser(
        "version",
        help="输出版本号",
        description="显示版本号和发布日期"
    )
    version_parser.set_defaults(func=cmd_version)
    
    return parser


def main(argv=None) -> int:
    """主入口函数
    
    Args:
        argv: 命令行参数列表（默认 sys.argv[1:]）
    
    Returns:
        退出码：0 成功，1 有高危问题，2 执行错误
    """
    parser = _build_parser()
    
    if argv is None:
        argv = sys.argv[1:]
    
    # 向后兼容：不传子命令时，默认走 scan
    # 判断第一个参数是否是子命令名
    subcommands = {"scan", "init", "rules", "config", "version", "help", "--help", "-h"}
    
    if not argv:
        # 无参数，默认 scan 当前目录
        argv = ["scan", "."]
    elif argv[0] == "help":
        # help 子命令 → --help
        argv = ["--help"] + argv[1:]
    elif argv[0] not in subcommands and not argv[0].startswith("-"):
        # 第一个参数不是子命令，也不是 flag → 当作路径，走 scan
        argv = ["scan"] + argv
    
    args = parser.parse_args(argv)
    
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
