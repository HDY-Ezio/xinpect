#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
煋鉴 Flaky Test 守门（对标 Google flaky 治理：让失败=真bug成为可信信号）
对目标侧 tests/ 连续重复跑 N 轮（默认5轮），逐用例统计通过/失败：
  - 全部用例在所有轮次 100% 通过 -> FLAKY_PASS exit 0
  - 任一轮出现失败 -> 报告 flaky/真实失败明细 exit 1（发布门禁拦截）
用法: flaky_guard.py <scanner_dir> [轮数]
配合 release_gate.sh 使用；被认定 flaky 的用例应移入 tests/_quarantine/ 并登记 owner+SLA。
"""
import subprocess, sys, re, os, collections

def main():
    if len(sys.argv) < 2:
        print("用法: flaky_guard.py <scanner_dir> [轮数]"); sys.exit(2)
    scanner_dir = sys.argv[1]
    rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    test_dir = os.path.join(scanner_dir, "tests")
    env = dict(os.environ); env["PYTHONPATH"] = scanner_dir

    # 用 -v 拿逐用例行；解析 PASSED/FAILED/ERROR
    results = collections.defaultdict(lambda: collections.Counter())
    total_fail_rounds = 0
    for r in range(1, rounds + 1):
        p = subprocess.run(
            [sys.executable, "-m", "pytest", "-v", "-p", "no:cacheprovider", "--tb=no"],
            cwd=test_dir, env=env, capture_output=True, text=True, timeout=300)
        out = p.stdout + p.stderr
        round_failed = 0
        for line in out.splitlines():
            m = re.match(r"\s*(\S+::\S+)\s+(PASSED|FAILED|ERROR)\b", line)
            if m:
                node, state = m.group(1), m.group(2)
                results[node][state] += 1
                if state in ("FAILED", "ERROR"):
                    round_failed += 1
        if round_failed:
            total_fail_rounds += 1
        print("第%d轮: %s" % (r, "全通过" if not round_failed else "%d个失败/错误" % round_failed))

    flaky, hardfail = [], []
    for node, c in results.items():
        fails = c.get("FAILED", 0) + c.get("ERROR", 0)
        passes = c.get("PASSED", 0)
        if fails and passes:
            flaky.append((node, passes, fails))
        elif fails and not passes:
            hardfail.append((node, fails))

    print("─" * 56)
    if not flaky and not hardfail and total_fail_rounds == 0:
        print("FLAKY_PASS: %d 个用例 × %d 轮全部稳定通过，无 flaky。" % (len(results), rounds))
        sys.exit(0)
    if flaky:
        print("❌ 发现 %d 个 FLAKY 用例（时过时不过，腐蚀CI信号）：" % len(flaky))
        for node, pa, fa in flaky:
            print("   ⚠ %s  通过%d轮/失败%d轮  -> 移入 _quarantine 并登记 owner+14天SLA" % (node, pa, fa))
    if hardfail:
        print("❌ %d 个用例稳定失败（疑似真实回归，非flaky）：" % len(hardfail))
        for node, fa in hardfail:
            print("   ✗ %s  失败%d轮" % (node, fa))
    if not flaky and not hardfail:
        print("❌ 有轮次失败但未解析到用例，检查pytest输出。")
    sys.exit(1)

if __name__ == "__main__":
    main()
