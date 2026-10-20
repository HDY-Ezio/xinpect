#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
B15 扫描指标查询报告

读取 b15_metrics.jsonl，输出最近 N 次扫描的统计摘要。

用法：
    python3 b15_metrics_report.py                    # 默认最近 10 次
    python3 b15_metrics_report.py --last 20          # 最近 20 次
    python3 b15_metrics_report.py --last 5 --json    # JSON 格式输出
    python3 b15_metrics_report.py --file /path/to/b15_metrics.jsonl  # 指定文件
"""

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List


DEFAULT_METRICS_PATH = "/opt/xinpect-scanner-blue/logs/b15_metrics.jsonl"


def load_metrics(path: str, last_n: int = 0) -> List[Dict[str, Any]]:
    """从 JSONL 文件加载指标记录"""
    if not os.path.exists(path):
        print(f"指标文件不存在: {path}")
        print("尚未有扫描记录产生指标数据。")
        return []

    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                records.append(record)
            except json.JSONDecodeError as e:
                print(f"警告: 第 {line_num} 行 JSON 解析失败: {e}")

    if last_n > 0:
        records = records[-last_n:]

    return records


def compute_summary(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """计算统计摘要"""
    if not records:
        return {"count": 0}

    durations = [r["scan_duration_seconds"] for r in records if r.get("scan_duration_seconds") is not None]
    segments = [r["total_segments"] for r in records if r.get("total_segments") is not None]
    llm_segments = [r["llm_segments"] for r in records if r.get("llm_segments") is not None]
    truncated = [r["truncated_segments"] for r in records if r.get("truncated_segments") is not None]
    llm_calls = [r["llm_call_count"] for r in records if r.get("llm_call_count") is not None]
    llm_errors = [r["llm_call_errors"] for r in records if r.get("llm_call_errors") is not None]
    tokens = [r["llm_total_tokens"] for r in records if r.get("llm_total_tokens") is not None]
    findings = [r["total_findings"] for r in records if r.get("total_findings") is not None]
    unique = [r["unique_findings"] for r in records if r.get("unique_findings") is not None]

    # 状态分布
    status_counts = {}
    for r in records:
        s = r.get("status", "unknown")
        status_counts[s] = status_counts.get(s, 0) + 1

    total_calls = sum(llm_calls) if llm_calls else 0
    total_errors = sum(llm_errors) if llm_errors else 0
    error_rate = (total_errors / total_calls * 100) if total_calls > 0 else 0.0

    summary = {
        "scan_count": len(records),
        "time_range": {
            "first": records[0].get("timestamp", "N/A"),
            "last": records[-1].get("timestamp", "N/A"),
        },
        "duration": {
            "avg": round(sum(durations) / len(durations), 2) if durations else None,
            "max": round(max(durations), 2) if durations else None,
            "min": round(min(durations), 2) if durations else None,
            "p50": _percentile(durations, 50),
            "p95": _percentile(durations, 95),
        },
        "segments": {
            "avg": round(sum(segments) / len(segments), 1) if segments else None,
            "max": max(segments) if segments else None,
        },
        "llm_segments": {
            "avg": round(sum(llm_segments) / len(llm_segments), 1) if llm_segments else None,
            "max": max(llm_segments) if llm_segments else None,
        },
        "truncated_segments": {
            "total": sum(truncated) if truncated else 0,
            "avg": round(sum(truncated) / len(truncated), 1) if truncated else 0,
            "max": max(truncated) if truncated else 0,
        },
        "llm_calls": {
            "total": total_calls,
            "avg": round(total_calls / len(records), 1) if records else 0,
        },
        "llm_errors": {
            "total": total_errors,
            "error_rate_pct": round(error_rate, 2),
        },
        "tokens": {
            "total": sum(tokens) if tokens else 0,
            "avg": round(sum(tokens) / len(tokens), 0) if tokens else 0,
        },
        "findings": {
            "total": sum(findings) if findings else 0,
            "unique_total": sum(unique) if unique else 0,
            "avg_per_scan": round(sum(findings) / len(findings), 1) if findings else 0,
        },
        "status_distribution": status_counts,
    }
    return summary


def _percentile(data: List, pct: int) -> float:
    """计算百分位数"""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (pct / 100)
    f = int(k)
    c = f + 1
    if c >= len(sorted_data):
        return round(sorted_data[f], 2)
    d0 = sorted_data[f] * (c - k)
    d1 = sorted_data[c] * (k - f)
    return round(d0 + d1, 2)


def print_report(records: List[Dict[str, Any]], summary: Dict[str, Any]):
    """打印可读报告"""
    if summary["scan_count"] == 0:
        print("无扫描记录。")
        return

    print("=" * 60)
    print("  B15 LLM 语义扫描 — 指标报告")
    print("=" * 60)
    print(f"  扫描次数: {summary['scan_count']}")
    print(f"  时间范围: {summary['time_range']['first']} → {summary['time_range']['last']}")
    print()

    # 耗时
    d = summary["duration"]
    if d["avg"] is not None:
        print("  ⏱  扫描耗时 (秒)")
        print(f"      平均: {d['avg']}s | 最大: {d['max']}s | 最小: {d['min']}s")
        print(f"      P50:  {d['p50']}s | P95:  {d['p95']}s")
        print()

    # 分片
    seg = summary["segments"]
    llm_seg = summary["llm_segments"]
    trunc = summary["truncated_segments"]
    print("  📦  分片统计")
    if seg["avg"] is not None:
        print(f"      选段总数: 平均 {seg['avg']} | 最大 {seg['max']}")
    if llm_seg["avg"] is not None:
        print(f"      LLM 分片: 平均 {llm_seg['avg']} | 最大 {llm_seg['max']}")
    print(f"      截断分片: 总计 {trunc['total']} | 平均 {trunc['avg']} | 最大 {trunc['max']}")
    print()

    # LLM 调用
    llm = summary["llm_calls"]
    err = summary["llm_errors"]
    tok = summary["tokens"]
    print("  🤖  LLM 调用")
    print(f"      总调用: {llm['total']} | 平均 {llm['avg']}/次")
    print(f"      错误数: {err['total']} | 错误率: {err['error_rate_pct']}%")
    print(f"      Token:  总计 {tok['total']} | 平均 {int(tok['avg'])}/次")
    print()

    # 发现
    f = summary["findings"]
    print("  🔍  安全发现")
    print(f"      总发现: {f['total']} | 去重后: {f['unique_total']} | 平均 {f['avg_per_scan']}/次")
    print()

    # 状态分布
    print("  📊  状态分布")
    for status, count in sorted(summary["status_distribution"].items()):
        pct = count / summary["scan_count"] * 100
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        print(f"      {status:12s} {bar} {count} ({pct:.0f}%)")
    print()
    print("=" * 60)


def print_detail_table(records: List[Dict[str, Any]]):
    """打印每次扫描的详情表格"""
    print()
    print("-" * 100)
    print(f"  {'#':>3}  {'时间':^20}  {'耗时':>6}  {'分片':>4}  {'LLM':>4}  {'截断':>4}  {'调用':>4}  {'错误':>4}  {'Token':>7}  {'发现':>4}  {'状态':^10}")
    print("-" * 100)

    for i, r in enumerate(records, 1):
        ts = r.get("timestamp", "N/A")
        if ts and ts != "N/A":
            try:
                dt = datetime.fromisoformat(ts)
                ts = dt.strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                pass
            ts = ts[:20]

        dur = r.get("scan_duration_seconds")
        dur_s = f"{dur:.1f}s" if dur is not None else "  -  "
        seg = r.get("total_segments", "-")
        llm = r.get("llm_segments", "-")
        trunc = r.get("truncated_segments", "-")
        calls = r.get("llm_call_count", "-")
        errs = r.get("llm_call_errors", "-")
        tok = r.get("llm_total_tokens", "-")
        finds = r.get("total_findings", "-")
        status = r.get("status", "?")

        tok_s = f"{tok:,}" if isinstance(tok, int) else str(tok)

        print(
            f"  {i:>3}  {ts:^20}  {dur_s:>6}  {seg:>4}  {llm:>4}  {trunc:>4}  "
            f"{calls:>4}  {errs:>4}  {tok_s:>7}  {finds:>4}  {status:^10}"
        )

    print("-" * 100)


def main():
    parser = argparse.ArgumentParser(description="B15 扫描指标报告")
    parser.add_argument("--last", type=int, default=10, help="查看最近 N 条记录 (默认 10)")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    parser.add_argument("--file", type=str, default=DEFAULT_METRICS_PATH, help="指标文件路径")
    parser.add_argument("--detail", action="store_true", help="显示每次扫描的详情表格")
    args = parser.parse_args()

    records = load_metrics(args.file, last_n=args.last)
    if not records:
        sys.exit(0)

    summary = compute_summary(records)

    if args.json:
        output = {"summary": summary}
        if args.detail:
            output["records"] = records
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print_report(records, summary)
        if args.detail:
            print_detail_table(records)


if __name__ == "__main__":
    main()
