#!/usr/bin/env python3
"""
煋鉴扫描器 蓝绿同步校验脚本
部署位置: /opt/xinpect-website/scripts/blue_green_sync_check.py

检查内容:
  1. 核心引擎文件 (engine/ 下所有 .py，排除备份/bak/开发专用) 的 diff 对比
  2. 核心根目录文件的 diff 对比
  3. 绿版所有 .py 文件的 py_compile 编译检查
  4. 绿版关键 import 测试

输出: JSON 报告到 stdout
退出码: 0=ok, 1=warn(有差异但可编译), 2=fail(编译错误或严重问题)

用法:
  python3 blue_green_sync_check.py [--json] [--verbose]
"""

import os
import sys
import json
import hashlib
import py_compile
import subprocess
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta

# ======================== 配置 ========================

BLUE_DIR = "/opt/xinpect-scanner-blue"
GREEN_DIR = "/opt/xinpect-scanner-green"

# 排除的文件/目录模式（fnmatch 风格）
EXCLUDE_DIRS = {
    "__pycache__",
    ".pytest_cache",
    "benchmark",
    "benchmarks",
    "engine.bak_pre_phase2",
    "engine_backup_v5.163.0_pre_building_block",
    "engine_phase1_plan",
    "_archive",
    "b2_security_go_bak_pre_secbench",
    "poc_verification",
    "specialist_ai",
    "bb_scan",  # 蓝版独有的开发扫描目录
}

EXCLUDE_FILE_PATTERNS = [
    "analyze_*.py",
    "dbg*.py",
    "debug*.py",
    "test_*.py",
    "fix_*.py",
    "tmp_*.py",
    "e2e_test*.py",
    "self_scan*.py",       # 自扫描脚本不需要同步
    "quick_verify.py",
    "noise_analysis*.py",
    "build_*_stats.py",
    "gen_*.py",
    "show_result.py",
    "check_*.py",
    "count_*.py",
    "patch_*.py",
    "remaining_rules.py",
    "verify_*.py",
    "owasp_benchmark_test.py",
    "rule_counter.py",      # 绿版独有工具
    "scan_backend_v*.py",
    "scan_green_*.py",
]

# 绿版独有但不需要告警的文件（绿版特有的生产配置）
GREEN_ONLY_IGNORE = {
    "rule_counter.py",
    "green.log",
    "install.sh",
}

# 根目录核心文件列表（必须同步的）
CORE_ROOT_FILES = [
    "http_handlers.py",
    "_scan_handler.py",
    "_batch_handler.py",
    "scanner_service.py",
    "batch_module.py",
    "batch_scanner.py",
    "_batch_file_scanner.py",
    "_batch_utils.py",
    "_report_collector.py",
    "_report_components.py",
    "report_generator.py",
    "_report_handler.py",
    "_report_styles.py",
    "result_store.py",
    "_rule_collector.py",
    "rule_registry_query.py",
    "_rule_utils.py",
    "scan_cache.py",
    "vuln_chain_engine.py",
    "_vuln_classifier.py",
    "perf_stats.py",
]

# 绿版关键 import 测试模块
IMPORT_TEST_MODULES = [
    "scanner_service",
    "http_handlers",
    "_scan_handler",
    "_batch_handler",
    "batch_module",
    "batch_scanner",
    "_batch_file_scanner",
    "_batch_utils",
    "result_store",
    "scan_cache",
    "_report_collector",
    "_report_components",
    "report_generator",
    "_report_handler",
    "_report_styles",
    "_rule_collector",
    "rule_registry_query",
    "_rule_utils",
    "vuln_chain_engine",
    "_vuln_classifier",
]

# ======================== 工具函数 ========================

import fnmatch


def should_exclude_file(filename: str) -> bool:
    """检查文件是否应被排除"""
    # 排除 .bak* 文件
    if ".bak" in filename:
        return True
    # 排除匹配模式的文件
    for pattern in EXCLUDE_FILE_PATTERNS:
        if fnmatch.fnmatch(filename, pattern):
            return True
    return False


def should_exclude_dir(dirname: str) -> bool:
    """检查目录是否应被排除"""
    return dirname in EXCLUDE_DIRS or dirname.startswith("engine_backup_")


def file_md5(filepath: str) -> str:
    """计算文件 MD5"""
    h = hashlib.md5()
    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except (OSError, PermissionError):
        return "READ_ERROR"


def collect_engine_files(base_dir: str) -> set:
    """收集 engine/ 下所有需要同步的 .py 文件的相对路径"""
    result = set()
    engine_dir = os.path.join(base_dir, "engine")
    if not os.path.isdir(engine_dir):
        return result

    for root, dirs, files in os.walk(engine_dir):
        # 过滤排除目录（原地修改 dirs 以阻止 os.walk 进入）
        dirs[:] = [d for d in dirs if not should_exclude_dir(d)]

        for f in files:
            if not f.endswith(".py"):
                continue
            if should_exclude_file(f):
                continue
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, base_dir)
            result.add(rel_path)

    return result


def collect_root_core_files(base_dir: str) -> set:
    """收集根目录核心文件的相对路径"""
    result = set()
    for f in CORE_ROOT_FILES:
        full_path = os.path.join(base_dir, f)
        if os.path.isfile(full_path):
            result.add(f)
    return result


def collect_all_green_py(base_dir: str) -> list:
    """收集绿版所有 .py 文件（排除 __pycache__、.bak 和解析器测试数据）"""
    # 编译检查需额外排除的目录（测试数据、示例代码，不是实际运行代码）
    COMPILE_EXCLUDE_DIRS = {
        "test", "tests", "examples", "tags", "highlight",
        "tree-sitter-python", "tree-sitter-java", "tree-sitter-javascript",
        "tree-sitter-typescript", "tree-sitter-go", "tree-sitter-rust",
        "tree-sitter-c", "tree-sitter-cpp", "tree-sitter-kotlin",
    }
    result = []
    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__" and not d.startswith(".")]
        # 检查路径中是否包含需排除的测试数据目录
        rel_root = os.path.relpath(root, base_dir)
        parts = set(Path(rel_root).parts)
        if parts & COMPILE_EXCLUDE_DIRS:
            # 检查是否是 tree-sitter 解析器的测试/示例数据
            if any(p in COMPILE_EXCLUDE_DIRS for p in parts if p.startswith("tree-sitter-") or p in {"test", "tests", "examples", "tags", "highlight"}):
                continue
        for f in files:
            if not f.endswith(".py"):
                continue
            if ".bak" in f:
                continue
            full_path = os.path.join(root, f)
            result.append(full_path)
    return result


def get_diff_summary(blue_path: str, green_path: str, context_lines: int = 3) -> str:
    """获取两个文件的 diff 摘要（前 10 行）"""
    try:
        result = subprocess.run(
            ["diff", "-u", "--label", "blue", "--label", "green",
             blue_path, green_path],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return ""
        # 取前 15 行 diff 输出作为摘要
        lines = result.stdout.split("\n")
        # 统计变更行数
        additions = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
        deletions = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
        return f"+{additions}/-{deletions} lines"
    except (subprocess.TimeoutExpired, Exception) as e:
        return f"diff error: {e}"


# ======================== 主检查逻辑 ========================

def run_sync_check(verbose: bool = False) -> dict:
    """执行完整的蓝绿同步校验"""
    tz_cn = timezone(timedelta(hours=8))
    report = {
        "check_time": datetime.now(tz_cn).isoformat(),
        "blue_dir": BLUE_DIR,
        "green_dir": GREEN_DIR,
        "sync_status": "ok",
        "missing_in_green": [],        # 蓝版有但绿版缺失的文件
        "extra_in_green": [],           # 绿版有但蓝版没有的文件（仅核心文件范围）
        "divergent_files": [],          # 内容不一致的文件
        "compile_errors": [],           # 绿版编译错误
        "import_errors": [],            # 绿版 import 错误
        "summary": {
            "blue_engine_files": 0,
            "green_engine_files": 0,
            "blue_core_root_files": 0,
            "green_core_root_files": 0,
            "total_checked": 0,
            "matched": 0,
            "diverged": 0,
            "missing": 0,
            "compile_checked": 0,
            "compile_failed": 0,
            "import_tested": 0,
            "import_failed": 0,
        }
    }

    # ===== 1. 检查目录存在 =====
    if not os.path.isdir(BLUE_DIR):
        report["sync_status"] = "fail"
        report["error"] = f"蓝版目录不存在: {BLUE_DIR}"
        return report
    if not os.path.isdir(GREEN_DIR):
        report["sync_status"] = "fail"
        report["error"] = f"绿版目录不存在: {GREEN_DIR}"
        return report

    # ===== 2. 收集文件列表 =====
    blue_engine = collect_engine_files(BLUE_DIR)
    green_engine = collect_engine_files(GREEN_DIR)
    blue_root = collect_root_core_files(BLUE_DIR)
    green_root = collect_root_core_files(GREEN_DIR)

    report["summary"]["blue_engine_files"] = len(blue_engine)
    report["summary"]["green_engine_files"] = len(green_engine)
    report["summary"]["blue_core_root_files"] = len(blue_root)
    report["summary"]["green_core_root_files"] = len(green_root)

    # 合并需要同步的文件集合
    all_sync_files = blue_engine | blue_root
    report["summary"]["total_checked"] = len(all_sync_files)

    # ===== 3. 检查缺失和差异 =====
    for rel_path in sorted(all_sync_files):
        blue_path = os.path.join(BLUE_DIR, rel_path)
        green_path = os.path.join(GREEN_DIR, rel_path)

        if not os.path.isfile(green_path):
            # 文件在绿版缺失
            entry = {
                "file": rel_path,
                "blue_size": os.path.getsize(blue_path) if os.path.isfile(blue_path) else 0,
                "blue_md5": file_md5(blue_path),
                "status": "missing",
            }
            report["missing_in_green"].append(entry)
            continue

        # 两边都有，比较内容
        blue_md5 = file_md5(blue_path)
        green_md5 = file_md5(green_path)

        if blue_md5 != green_md5:
            diff_summary = get_diff_summary(blue_path, green_path)
            entry = {
                "file": rel_path,
                "blue_md5": blue_md5,
                "green_md5": green_md5,
                "blue_size": os.path.getsize(blue_path),
                "green_size": os.path.getsize(green_path),
                "diff": diff_summary,
                "status": "diverged",
            }
            report["divergent_files"].append(entry)
        else:
            report["summary"]["matched"] += 1

    report["summary"]["missing"] = len(report["missing_in_green"])
    report["summary"]["diverged"] = len(report["divergent_files"])

    # ===== 4. 绿版 py_compile 编译检查 =====
    green_py_files = collect_all_green_py(GREEN_DIR)
    report["summary"]["compile_checked"] = len(green_py_files)

    for py_file in green_py_files:
        try:
            py_compile.compile(py_file, doraise=True)
        except py_compile.PyCompileError as e:
            rel_path = os.path.relpath(py_file, GREEN_DIR)
            report["compile_errors"].append({
                "file": rel_path,
                "error": str(e).split("\n")[-1] if "\n" in str(e) else str(e)[:200],
            })

    report["summary"]["compile_failed"] = len(report["compile_errors"])

    # ===== 5. 绿版 import 测试 =====
    # 在绿版目录下运行 python3 -c "import xxx"
    report["summary"]["import_tested"] = len(IMPORT_TEST_MODULES)

    for module_name in IMPORT_TEST_MODULES:
        try:
            result = subprocess.run(
                [sys.executable, "-c", f"import {module_name}"],
                capture_output=True, text=True, timeout=15,
                cwd=GREEN_DIR,
                env={**os.environ, "PYTHONPATH": GREEN_DIR}
            )
            if result.returncode != 0:
                error_msg = result.stderr.strip().split("\n")[-1] if result.stderr.strip() else f"exit code {result.returncode}"
                report["import_errors"].append({
                    "module": module_name,
                    "error": error_msg[:300],
                })
        except subprocess.TimeoutExpired:
            report["import_errors"].append({
                "module": module_name,
                "error": "import timeout (15s)",
            })
        except Exception as e:
            report["import_errors"].append({
                "module": module_name,
                "error": str(e)[:200],
            })

    report["summary"]["import_failed"] = len(report["import_errors"])

    # ===== 6. 判定最终状态 =====
    if report["compile_errors"] or report["import_errors"]:
        report["sync_status"] = "fail"
    elif report["divergent_files"] or report["missing_in_green"]:
        report["sync_status"] = "warn"
    else:
        report["sync_status"] = "ok"

    return report


def format_human_report(report: dict) -> str:
    """将 JSON 报告格式化为人类可读文本"""
    lines = []
    status_emoji = {"ok": "✅", "warn": "⚠️", "fail": "❌"}
    emoji = status_emoji.get(report["sync_status"], "?")

    lines.append(f"{emoji} 煋鉴蓝绿同步校验报告")
    lines.append(f"时间: {report['check_time']}")
    lines.append(f"状态: {report['sync_status'].upper()}")
    lines.append("")

    s = report["summary"]
    lines.append(f"📊 概览:")
    lines.append(f"  蓝版引擎文件: {s['blue_engine_files']} | 绿版引擎文件: {s['green_engine_files']}")
    lines.append(f"  蓝版核心根文件: {s['blue_core_root_files']} | 绿版核心根文件: {s['green_core_root_files']}")
    lines.append(f"  检查总数: {s['total_checked']} | 一致: {s['matched']} | 差异: {s['diverged']} | 缺失: {s['missing']}")
    lines.append(f"  编译检查: {s['compile_checked']} | 失败: {s['compile_failed']}")
    lines.append(f"  Import测试: {s['import_tested']} | 失败: {s['import_failed']}")
    lines.append("")

    if report["missing_in_green"]:
        lines.append(f"🔴 绿版缺失文件 ({len(report['missing_in_green'])}):")
        for entry in report["missing_in_green"]:
            lines.append(f"  - {entry['file']} (蓝版 {entry['blue_size']} bytes)")
        lines.append("")

    if report["divergent_files"]:
        lines.append(f"🟡 内容不一致文件 ({len(report['divergent_files'])}):")
        for entry in report["divergent_files"]:
            lines.append(f"  - {entry['file']} (diff: {entry['diff']})")
        lines.append("")

    if report["compile_errors"]:
        lines.append(f"❌ 编译错误 ({len(report['compile_errors'])}):")
        for entry in report["compile_errors"]:
            lines.append(f"  - {entry['file']}: {entry['error']}")
        lines.append("")

    if report["import_errors"]:
        lines.append(f"❌ Import 错误 ({len(report['import_errors'])}):")
        for entry in report["import_errors"]:
            lines.append(f"  - {entry['module']}: {entry['error']}")
        lines.append("")

    if report["sync_status"] == "ok":
        lines.append("🎉 所有检查通过！蓝绿完全同步。")

    return "\n".join(lines)


# ======================== 入口 ========================

def main():
    parser = argparse.ArgumentParser(description="煋鉴扫描器蓝绿同步校验")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    parser.add_argument("--output", "-o", type=str, help="输出到文件")
    args = parser.parse_args()

    print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] 开始蓝绿同步校验...", file=sys.stderr)

    report = run_sync_check(verbose=args.verbose)

    # 输出
    if args.json:
        output = json.dumps(report, ensure_ascii=False, indent=2)
    else:
        output = format_human_report(report)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"报告已写入: {args.output}", file=sys.stderr)
    else:
        print(output)

    # 同时保存 JSON 报告到固定位置
    report_dir = "/opt/xinpect-website/scripts/reports"
    os.makedirs(report_dir, exist_ok=True)
    json_path = os.path.join(report_dir, "last_sync_check.json")
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report, ensure_ascii=False, indent=2, fp=f)
    except Exception:
        pass  # 非关键，不阻断

    # 退出码
    if report["sync_status"] == "fail":
        sys.exit(2)
    elif report["sync_status"] == "warn":
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
