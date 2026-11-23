#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
煋旺智能全公司代码全量扫描（用煋鉴扫描器扫自己）
==================================================
用途：把全公司所有项目的真实业务源码，逐文件喂给煋鉴扫描器 API，
汇总所有问题，产出「全公司代码问题总清单」。一石二鸟：
①盘清全公司代码问题 ②顺便验证煋鉴产品对自家代码的检出能力。

排除：.bak / __pycache__ / node_modules / 规则库 / 测试样本 / 日志 / 报告json / .git
"""

import json
import os
import sys
import time
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

API = "http://127.0.0.1:8620/scan"
def _load_api_key():
    """凭据不入库：先看环境变量，再读仓库外的 /etc/xinpect/monitor.key。"""
    import os as _os
    key = _os.environ.get("XINPECT_API_KEY", "").strip()
    if not key:
        try:
            with open("/etc/xinpect/monitor.key", encoding="utf-8") as _f:
                key = _f.read().strip()
        except OSError:
            key = ""
    if not key:
        raise SystemExit(
            "缺少扫描器 API 凭据：设置环境变量 XINPECT_API_KEY，"
            "或把密钥写入 /etc/xinpect/monitor.key（权限 640 root:ubuntu）"
        )
    return key

KEY = _load_api_key()
CONCURRENCY = 3  # 与扫描器 SCAN_MAX_CONCURRENT 一致，低并发不压垮线上服务

# 全公司项目清单（只扫真实业务源码）
PROJECTS = {
    "煋鉴扫描器": "/opt/xinpect-scanner-green",
    "煋鉴官网": "/opt/xinpect-website",
    "煋鉴门房(付费)": "/opt/xinpect-pay",
    "煋旺AI后端": "/opt/starwang/backend_clean",
    "StarDirector": "/opt/stardirector",
    "节能阀(ai-cost-optimizer)": "/home/ubuntu/ai-cost-optimizer",
    "微信网关(xw-gateway)": "/home/ubuntu/xw-wechat-gateway",
    "付费技能(payserver)": "/home/ubuntu/payserver",
}

# 排除的目录/文件名片段（只排真正的非业务代码：缓存/依赖/备份/日志/报告）
EXCLUDE_DIRS = {
    "__pycache__", "node_modules", ".git", "venv", ".venv",
    "backup_rename_20261020_102633", "bak_qltbatch_20261025",
    "benchmark", "engine_backups", "engine_phase1_plan",
    "backups", "backup", "_backup", "_backup2",
    "codeact", "logs", "reports",
    "bb_scan",  # 扫描器的测试样本/批量扫描产物，非业务代码
}
EXCLUDE_NAME_FRAG = {".bak", ".bak_", "_backup_", "test_", "conftest",
                     "report", ".log", "README", "LICENSE", "NOTICE",
                     "requirements", "ecosystem", "pytest.ini", "manifest",
                     "docker-compose", "Dockerfile", "pyproject.toml"}
EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".java"}


def is_excluded(path: Path) -> bool:
    parts = path.parts
    for p in parts:
        if p in EXCLUDE_DIRS:
            return True
    name = path.name
    for frag in EXCLUDE_NAME_FRAG:
        if frag in name:
            return True
    return False


def collect_files(proj_root: str) -> list:
    files = []
    root = Path(proj_root)
    if not root.exists():
        return files
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix not in EXTENSIONS:
            continue
        if is_excluded(p):
            continue
        if p.stat().st_size > 200 * 1024:  # 跳过超大文件
            continue
        files.append(p)
    return files


def scan_file(path: Path) -> dict:
    """扫单个文件，返回 {issues, style_issues, error}，超时自动重试一次"""
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None
    lang = path.suffix.lstrip(".")
    payload = {"code_files": {str(path): content}}
    req = urllib.request.Request(
        API,
        data=json.dumps(payload).encode("utf-8"),
        headers={"X-API-Key": KEY, "Content-Type": "application/json"},
        method="POST",
    )
    # 第一次尝试：30秒超时
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
            break
        except Exception as e:
            if attempt == 0:
                time.sleep(1)  # 重试前短暂等待
                continue
            return {"issues": [], "style_issues": [], "error": str(e)[:100]}

    issues = []
    style_issues = []
    results = data.get("results", {})
    for rid, r in results.items():
        for iss in r.get("issues", []) or []:
            issues.append(iss)
        for iss in r.get("style_issues", []) or []:
            style_issues.append(iss)
        # 收割子列表
        for iss in r.get("issues", []) or []:
            for sub in iss.get("root_cause_merged", []) or []:
                issues.append(sub)
    return {"issues": issues, "style_issues": style_issues, "error": None}


def _dump_partial(stats, all_findings):
    """每100个文件落盘一次中间结果"""
    try:
        partial = {
            "stats": dict(stats),
            "findings_by_project": {k: v for k, v in all_findings.items()},
            "partial": True,
        }
        with open("/tmp/full_scan_partial.json", "w") as f:
            json.dump(partial, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def main():
    all_findings = defaultdict(list)  # project -> [findings]
    stats = {"scanned": 0, "clean": 0, "with_issues": 0, "errors": 0}

    # 断点续扫：加载已扫过的文件清单
    scanned_file = set()
    done_path = "/tmp/full_scan_done.txt"
    if os.path.exists(done_path):
        with open(done_path) as f:
            scanned_file = set(x.strip() for x in f if x.strip())
        print(f"断点续扫：已跳过 {len(scanned_file)} 个已扫文件", flush=True)

    # 收集所有待扫文件（项目名 + 路径）
    all_tasks = []  # (proj_name, file_path)
    for proj_name, proj_root in PROJECTS.items():
        files = collect_files(proj_root)
        print(f"\n=== [{proj_name}] 待扫 {len(files)} 个文件 ===", flush=True)
        for fp in files:
            if str(fp) in scanned_file:
                continue
            all_tasks.append((proj_name, fp))
    print(f"\n总计待扫 {len(all_tasks)} 个文件（已跳过 {len(scanned_file)} 个），{CONCURRENCY} 并发启动\n", flush=True)

    t0 = time.time()

    def _scan_one(task):
        proj_name, fp = task
        res = scan_file(fp)
        # 只有成功(有明确结果)才记为已扫；超时error不记录，留待下次补扫
        if res is not None and not res.get("error"):
            with open(done_path, "a") as f:
                f.write(str(fp) + "\n")
        return proj_name, fp, res

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        futures = {pool.submit(_scan_one, t): t for t in all_tasks}
        for fut in as_completed(futures):
            proj_name, fp, res = fut.result()
            stats["scanned"] += 1
            if res is None or res.get("error"):
                stats["errors"] += 1
            elif res["issues"] or res["style_issues"]:
                stats["with_issues"] += 1
                for iss in res["issues"]:
                    all_findings[proj_name].append({
                        "file": str(fp),
                        "rule_id": iss.get("rule_id", "?"),
                        "severity": iss.get("severity", "?"),
                        "message": (iss.get("message") or iss.get("title") or "")[:200],
                        "line": iss.get("line", ""),
                    })
                for iss in res["style_issues"]:
                    all_findings[proj_name].append({
                        "file": str(fp),
                        "rule_id": iss.get("rule_id", "?"),
                        "severity": "style",
                        "message": (iss.get("message") or iss.get("title") or "")[:200],
                        "line": iss.get("line", ""),
                    })
            else:
                stats["clean"] += 1

            if stats["scanned"] % 20 == 0:
                elapsed = time.time() - t0
                speed = stats["scanned"] / elapsed if elapsed > 0 else 0
                eta = (len(all_tasks) - stats["scanned"]) / speed if speed > 0 else 0
                print(f"  已扫 {stats['scanned']}/{len(all_tasks)} ({speed:.1f}文件/秒, 预计剩余{eta/60:.0f}分钟), 问题文件 {stats['with_issues']}", flush=True)
            if stats["scanned"] % 200 == 0:
                _dump_partial(stats, all_findings)

    # 输出报告
    out = {
        "stats": stats,
        "findings_by_project": {k: v for k, v in all_findings.items()},
        "total_findings": sum(len(v) for v in all_findings.values()),
    }
    out_path = "/opt/xinpect-website/monitoring/full_scan_report.json"
    with open(out_path, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n=== 扫描完成，总耗时 {round((time.time()-t0)/60, 1)} 分钟 ===", flush=True)
    print(json.dumps(stats, ensure_ascii=False, indent=2), flush=True)
    print(f"总问题数: {out['total_findings']}", flush=True)
    print(f"报告: {out_path}", flush=True)


if __name__ == "__main__":
    main()
