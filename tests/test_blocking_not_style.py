# -*- coding: utf-8 -*-
"""「代码跑不起来」不许被当成风格建议（2026-11-23）

病灶：`is_style_rule` 按规则 ID 的族记号判风格，`SYN` 一整个族都在名单里。
可 SYN 族里混着两类东西——

    SYN-JAVA-003  超长代码行      真风格，不该扣分
    E1-SYN-COMP-001 Python 编译失败  代码根本跑不起来

结果「Python 编译失败」在报告页写着「必须修」（category_of 判 BUG），
分数上却不扣一分。同一个问题，页面说必须修，分数说满分。

本文件钉住三件事：
  1. 编译/解析验证类永远不判风格；
  2. SYN 族里的真风格照旧不判（改动不能把风格又拖回来扣分）；
  3. 这条判据是唯一的守卫——把它拿掉，第 1 条必须失败。
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules import rule_kind                      # noqa: E402
from modules.rule_kind import is_style_rule        # noqa: E402
from modules.scoring import calculate_score, grade_of  # noqa: E402
from modules.constants import RISK_SCORE_CAP       # noqa: E402


BLOCKING = ("E1-SYN-COMP-001", "E1-SYN-COMP-002", "E1-SYN-COMP-003", "E1-SYN-COMP-005")
STYLE_SYN = ("SYN-JAVA-003", "SYN-JAVA-010", "SYN-JS-009")


def issue(rule_id, severity="high", brain_id="1"):
    return {"rule_id": rule_id, "severity": severity, "brain_id": brain_id,
            "title": "x", "file": "a.py", "line": 1}


@pytest.mark.parametrize("rid", BLOCKING)
def test_compile_failure_is_not_style(rid):
    """编译/解析失败：代码跑不起来，不能算优化建议。"""
    assert is_style_rule(rid) is False, "%s 被当成了风格建议" % rid


@pytest.mark.parametrize("rid", STYLE_SYN)
def test_syn_family_real_style_still_style(rid):
    """同一个 SYN 族里的真风格不许被这次改动拖回来扣分。"""
    assert is_style_rule(rid) is True, "%s 本来是风格，现在不判风格了" % rid


def test_compile_failure_deducts_and_caps():
    """编译失败必须扣分，并且按高危封顶。"""
    score = calculate_score([issue("E1-SYN-COMP-001", "high")])
    assert score == RISK_SCORE_CAP["high"], "编译失败应封在 %s，实际 %s" % (RISK_SCORE_CAP["high"], score)
    assert grade_of(score) == "C"


def test_compile_failure_mixed_with_style():
    """编译失败 + 一堆风格建议：分数由编译失败决定，风格不许把它抬上去。"""
    items = [issue("E1-SYN-COMP-001", "high")] + \
            [issue("SYN-JAVA-003", "info") for _ in range(20)]
    assert calculate_score(items) == RISK_SCORE_CAP["high"]


def test_blocking_segments_is_the_only_guard(monkeypatch):
    """造坏自检：把 COMP 从阻断段里拿掉，编译失败必须重新被判成风格。

    这条证明「编译失败不判风格」不是碰巧——挡住它的只有 `_BLOCKING_SEGMENTS`
    一处。谁把它清空，这里立刻红。
    """
    monkeypatch.setattr(rule_kind, "_BLOCKING_SEGMENTS", ())
    assert is_style_rule("E1-SYN-COMP-001") is True, (
        "阻断段被清空后仍然不判风格，说明判据不止一处——单一事实来源破了")
