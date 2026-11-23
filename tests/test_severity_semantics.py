# -*- coding: utf-8 -*-
"""严重度分档只能有一张表（2026-11-23）

病灶：同一份代码里两张方向相反的分档表。

    report_verdict._SEVERITY_RANK   correctness=3（与 high 同档）、suspicious=2
    scoring._SEVERITY_BUCKET        correctness=medium、suspicious=high

报告页按第一张说「必须修」，扣分按第二张把这条确定缺陷扣得比「可能是错的」
还少。同一批问题，页面一个说法、分数另一个说法。

现在 scoring 的分档从 report_verdict 的 rank 派生，本文件钉住这件事：
  1. 同义档位必须同桶、同分；
  2. 改 rank 表，分档必须跟着变（证明它真的派生，不是又抄了一份）；
  3. 认不出来的写法按最轻档，不许给未知值发高危。
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules import report_verdict                     # noqa: E402
from modules.scoring import (                          # noqa: E402
    calculate_score, grade_of, severity_bucket, worst_severity_bucket,
)
from modules.constants import RISK_SCORE_CAP           # noqa: E402


def issue(severity):
    return {"rule_id": "E2-SEC-SQL-001", "severity": severity, "brain_id": "2",
            "title": "x", "file": "a.py", "line": 1}


def test_same_meaning_same_bucket():
    """同义档位必须同桶：correctness=high、suspicious=medium、style=info。"""
    pairs = [("correctness", "high"), ("suspicious", "medium"),
             ("restriction", "low"), ("style", "info")]
    bad = [p for p in pairs if severity_bucket(p[0]) != severity_bucket(p[1])]
    assert not bad, "这些同义档位落进了不同的桶：%r" % (bad,)
    # 桶名也钉死：两边一起改错（都落 medium）同样算分叉
    assert severity_bucket("correctness") == "high"
    assert severity_bucket("suspicious") == "medium"


def test_same_meaning_same_score():
    """同义档位必须同分——桶对了但扣分另算，等于没改。"""
    pairs = [("correctness", "high"), ("suspicious", "medium")]
    for a, b in pairs:
        assert calculate_score([issue(a)]) == calculate_score([issue(b)]), (
            "%s 与 %s 扣分不同：%s vs %s"
            % (a, b, calculate_score([issue(a)]), calculate_score([issue(b)])))


def test_unknown_severity_is_lightest():
    """认不出来的写法按最轻档，不给未知值发高危。"""
    assert severity_bucket("wat") == "low"
    assert severity_bucket(None) == "low"
    assert worst_severity_bucket([issue("wat")]) == "low"


def test_scoring_really_derives_from_rank(monkeypatch):
    """造坏自检：把 rank 表里 correctness 提到最重，分档必须跟着走。

    scoring 如果自己又抄了一份表，这条会红——抄的那份不会跟着改。
    """
    rank = dict(report_verdict._SEVERITY_RANK)
    rank["correctness"] = 4
    monkeypatch.setattr(report_verdict, "_SEVERITY_RANK", rank)
    assert severity_bucket("correctness") == "blocker", (
        "rank 改了分档没跟着改，说明分档表又分叉了")


def test_grade_cap_matches_bucket():
    """封顶和扣分用同一档：落在高危档就一定封在高危上限。"""
    for sev in ("high", "correctness"):
        score = calculate_score([issue(sev)])
        assert score <= RISK_SCORE_CAP["high"], "%s 没被封在高危档：%s" % (sev, score)
        assert grade_of(score) in ("C", "D")
