#!/usr/bin/env python3
"""
煋鉴 Benchmark 评估脚本
对比煋鉴扫描结果与人工标注集，计算精确率、召回率、误报率
"""
import csv
import sys
from collections import defaultdict

def load_annotations(csv_path):
    issues = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            issues.append(row)
    return issues

def evaluate(issues):
    total = len(issues)
    labeled = [i for i in issues if i.get("label", "").strip()]
    unlabeled = total - len(labeled)
    
    tp = sum(1 for i in labeled if i["label"].strip().lower() == "true_positive")
    fp = sum(1 for i in labeled if i["label"].strip().lower() == "false_positive")
    unsure = sum(1 for i in labeled if i["label"].strip().lower() == "unsure")
    
    precision = tp / (tp + fp) * 100 if (tp + fp) > 0 else 0
    fpr = fp / (tp + fp) * 100 if (tp + fp) > 0 else 0
    
    by_severity = defaultdict(lambda: {"tp": 0, "fp": 0})
    for i in labeled:
        sev = i.get("severity", "unknown")
        if i["label"].strip().lower() == "true_positive":
            by_severity[sev]["tp"] += 1
        elif i["label"].strip().lower() == "false_positive":
            by_severity[sev]["fp"] += 1
    
    by_brain = defaultdict(lambda: {"tp": 0, "fp": 0})
    for i in labeled:
        bid = i.get("brain_id", "unknown")
        if i["label"].strip().lower() == "true_positive":
            by_brain[bid]["tp"] += 1
        elif i["label"].strip().lower() == "false_positive":
            by_brain[bid]["fp"] += 1
    
    print("=" * 60)
    print("Xinpect Benchmark Report")
    print("=" * 60)
    print(f"Total issues: {total}")
    print(f"Labeled: {len(labeled)} | Unlabeled: {unlabeled}")
    print(f"  TP: {tp} | FP: {fp} | Unsure: {unsure}")
    print()
    print(f"Precision: {precision:.1f}%")
    print(f"False Positive Rate: {fpr:.1f}%")
    print()
    
    print("--- By Severity ---")
    hdr = f"{'Severity':<14} {'TP':>6} {'FP':>6} {'FPR':>8}"
    print(hdr)
    print("-" * 38)
    for sev in sorted(by_severity.keys()):
        d = by_severity[sev]
        t = d["tp"] + d["fp"]
        r = d["fp"] / t * 100 if t > 0 else 0
        print(f"{sev:<14} {d['tp']:>6} {d['fp']:>6} {r:>7.1f}%")
    
    print()
    print("--- By Engine ---")
    hdr = f"{'Engine':<10} {'TP':>6} {'FP':>6} {'FPR':>8}"
    print(hdr)
    print("-" * 38)
    for bid in sorted(by_brain.keys()):
        d = by_brain[bid]
        t = d["tp"] + d["fp"]
        r = d["fp"] / t * 100 if t > 0 else 0
        print(f"E{bid:<9} {d['tp']:>6} {d['fp']:>6} {r:>7.1f}%")
    
    return {"precision": precision, "fpr": fpr, "tp": tp, "fp": fp}

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/xinpect_label.csv"
    issues = load_annotations(path)
    evaluate(issues)
