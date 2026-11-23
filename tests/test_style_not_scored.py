# -*- coding: utf-8 -*-
"""规范/风格类不参与扣分（2026-11-23 老板定）

背景：这类问题占全部命中的 83%（E1 报的 2291 条「可疑」里 99.6% 是
if 嵌套过深、圈复杂度、方法过长），却只贡献扣分贡献的中位数 20%。
让它们参与打分，结果是代码写得干净、只是 if 嵌套多几层的项目被判 0 分。

本文件钉住四件事：
  1. 纯风格问题不再扣分；
  2. 真问题照常扣分（不能因为改动把安全漏洞一起放过）；
  3. 安全族优先：ID 里同时有安全记号和风格记号时，按安全算；
  4. 同一批问题里混进风格类，分数不变。
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.rule_kind import is_style_rule          # noqa: E402
from modules.scoring import calculate_score, grade_of  # noqa: E402
from modules.constants import RISK_SCORE_CAP        # noqa: E402


def issue(rule_id, severity="suspicious", brain_id="1"):
    return {"rule_id": rule_id, "severity": severity, "brain_id": brain_id,
            "title": "x", "file": "a.java", "line": 1}


def test_pure_style_scores_full():
    """整份都是风格问题 —— 不扣分。"""
    issues = [
        issue("B3-JAVA-QLT-003", "suspicious"),   # if嵌套过深
        issue("B3-QLT-JVCC-001", "suspicious"),   # 圈复杂度
        issue("B3-JAVA-QLT-001", "suspicious"),   # 方法过长
        issue("B3-JAVA-NAM-003", "style"),        # 常量命名
        issue("SYN-JAVA-003", "style"),           # 超长代码行
        issue("B3-JAVA-QLT-002", "suspicious"),   # 参数过多
    ]
    assert calculate_score(issues) == 100


def test_real_issues_still_deduct():
    """安全问题一条都不能漏。"""
    issues = [
        issue("E2-SEC-SQL-001", "high", "2"),
        issue("B3-SEC-JVDC-001", "style", "1"),   # 反序列化链，曾被标成 style
        issue("B3-COR-JESW-001", "style", "1"),   # 异常丢失
    ]
    score = calculate_score(issues)
    assert score < 100, "真问题必须扣分，实际 %s" % score
    # 扣分算出来是 94（high 扣 5 + 两条各 0.5），但含一条 high，
    # 命中高危封顶（2026-11-23：一档问题封一档上限），落在高危上限。
    assert score == RISK_SCORE_CAP['high'], (
        "含 high 的扫描应封在 %s，实际 %s" % (RISK_SCORE_CAP['high'], score))
    assert grade_of(score) == 'C'


def test_safety_token_wins():
    """ID 里同时出现安全族与风格族时，按安全算。"""
    assert is_style_rule("B3-SEC-JVDC-001") is False
    assert is_style_rule("E2-SEC-QLT-001") is False   # 人为混族
    assert is_style_rule("B3-JAVA-QLT-003") is True


def test_mixing_style_changes_nothing():
    """往一批真问题里塞满风格问题，分数一分都不该动。"""
    real = [issue("E2-SEC-SQL-001", "high", "2"), issue("E3-PERF-LOOP-001", "medium", "3")]
    base = calculate_score(real)
    noisy = real + [issue("B3-JAVA-QLT-003", "suspicious") for _ in range(30)]
    assert calculate_score(noisy) == base, (
        "塞了 30 条风格问题后分数从 %s 变成 %s" % (base, calculate_score(noisy)))


def test_severity_no_longer_decides_alone():
    """同样是风格族与正确性族：前者不扣分，后者要扣分。

    注意用 high 而不是 style —— 单条 style 只扣 0.5 分，round 之后仍是 100，
    那样这条测试测的是四舍五入，不是判据。
    """
    style_only = [issue("SYN-JAVA-003", "high")]
    correctness = [issue("B3-JAVA-FEQ-001", "high")]      # 浮点精确比较
    assert calculate_score(style_only) == 100
    assert calculate_score(correctness) < 100


def test_empty_and_unknown_ids_are_safe():
    """空 ID、未知 ID 不许被当成风格放过。

    判据是「有没有扣分」而不是「扣了几分」：被当成风格放过才会是满分。
    """
    for rid in ("", "TOTALLY-UNKNOWN-RULE"):
        got = calculate_score([issue(rid, "high")])
        assert got < 100, "规则 ID %r 被当成风格放过（分数 %s）" % (rid, got)


def test_style_tokens_do_not_swallow_perf_or_arch():
    """PERF / ARCH 是真问题，不许被当成风格。"""
    assert is_style_rule("PERF-GEN-001") is False
    assert is_style_rule("ARCH-BB-001") is False
    assert is_style_rule("E5-ARCH-DEPLOY-001") is False
