# -*- coding: utf-8 -*-
"""评级的风险封顶：一档问题对应一档上限。

写这份测试的原因（2026-11-23）：
  全库 1 份带 blocker（阻断级）的扫描拿到过 SSS，57 份带 high 的拿到过 SSS，
  18 份 critical 里评出过 S 和 A。评级的判据只看「扣了多少分」，
  而扣分制对「少而重」极不敏感——一处阻断级漏洞只扣 10 分。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.scoring import (  # noqa: E402
    calculate_score, calculate_dimension_score, grade_of, score_to_grade,
    worst_severity_bucket,
)
from modules.constants import RISK_SCORE_CAP  # noqa: E402


def iss(sev, rule_id="E2-SEC-001"):
    """构造一条问题。rule_id 用安全族，保证不会被「风格类不扣分」筛掉。"""
    return {"severity": sev, "rule_id": rule_id, "brain_id": "2", "title": "t"}


# ------------------------------------------------------------------ 判据 1

def test_cap_table_is_what_we_promised():
    """封顶表就是对外承诺的那五个数，谁改都得先改这里。

    这张表决定了「有阻断级问题的项目最高几分」，属于对外口径，
    不是随手能调的参数。
    """
    assert RISK_SCORE_CAP == {
        'blocker': 29, 'critical': 29, 'high': 59, 'medium': 79, 'low': 94,
    }


def test_every_severity_hits_its_ceiling():
    """一档问题对应一档上限，且上限落进对应等级的区间里。"""
    cases = [
        ('blocker', 29, 'D'),
        ('critical', 29, 'D'),
        ('high', 59, 'C'),
        ('correctness', 59, 'C'),     # 确定是错的，与 high 同档
        ('medium', 79, 'B'),
        ('suspicious', 79, 'B'),      # 可能是错的，与 medium 同档
        ('low', 94, 'A'),
        ('info', 94, 'A'),
    ]
    bad = []
    for sev, want_score, want_grade in cases:
        s = calculate_score([iss(sev)])
        g = grade_of(s)
        if s != want_score or g != want_grade:
            bad.append((sev, s, g, want_score, want_grade))
    assert not bad, "封顶没落到对应档位：%r" % (bad,)


def test_many_style_issues_cannot_bury_a_blocker():
    """30 条风格建议 + 1 处阻断级：分数必须还是 29，不许被风格淹没。"""
    items = [iss("style", "QLT-JAVA-003") for _ in range(30)] + [iss("blocker")]
    assert calculate_score(items) == 29
    assert grade_of(calculate_score(items)) == 'D'


def test_style_only_stays_clean():
    """阴性对照：纯风格建议不封顶、不扣分，50 条也是满分 S。"""
    items = [iss("style", "QLT-JAVA-003") for _ in range(50)]
    assert calculate_score(items) == 100
    assert grade_of(100) == 'S'


# ------------------------------------------------------------------ 判据 2

def test_no_scan_with_blocker_or_critical_can_ever_be_s():
    """回归历史事故：带 blocker 的扫描拿到过 SSS。

    现在无论三层多漂亮、分数多高，只要还剩一处阻断/严重问题，
    等级都不可能落到 S 及以上。
    """
    tiers_all_s = {
        'spec': {'score': 100, 'grade': 'S', 'locked': False, 'incomplete': False},
        'quality': {'score': 100, 'grade': 'S', 'locked': False, 'incomplete': False},
        'security': {'score': 100, 'grade': 'S', 'locked': False, 'incomplete': False},
    }
    for sev in ('blocker', 'critical', 'high', 'medium', 'low'):
        s = calculate_score([iss(sev)])
        g = grade_of(s, tiers_all_s, is_vip=True)
        assert g not in ('S', 'SS', 'SSS'), (
            '带 %s 问题却给了 %s 级（分数 %d）' % (sev, g, s))


# ------------------------------------------------------------------ 判据 3

def test_ss_and_sss_no_longer_exist():
    """S 就是最高档。全区间扫描，不许再产出 SS / SSS。"""
    bad = []
    for score in range(0, 101):
        g = grade_of(score, tier_scores=None, is_vip=True)
        if g in ('SS', 'SSS'):
            bad.append((score, g))
    assert not bad, '还在发放 SS/SSS：%r' % bad[:5]


def test_grade_still_reads_the_score():
    """等级仍然是分数的读法：同分同档，不因三层漂亮而抬高。"""
    tiers = {
        'spec': {'score': 100, 'grade': 'S', 'locked': False, 'incomplete': False},
        'quality': {'score': 100, 'grade': 'S', 'locked': False, 'incomplete': False},
        'security': {'score': 100, 'grade': 'S', 'locked': False, 'incomplete': False},
    }
    for score in (0, 30, 59, 60, 79, 80, 94, 95, 100):
        assert grade_of(score, tiers, is_vip=True) == score_to_grade(score)


# ------------------------------------------------------------------ 判据 4

def test_worst_bucket_picks_the_heaviest():
    assert worst_severity_bucket([]) is None
    assert worst_severity_bucket([iss("low"), iss("info")]) == 'low'
    assert worst_severity_bucket([iss("low"), iss("high")]) == 'high'
    assert worst_severity_bucket([iss("critical"), iss("blocker")]) == 'blocker'


def test_dimension_score_also_capped():
    """单引擎维度分同样封顶，否则报告会出现「某维度 100 分却含阻断级问题」。"""
    assert calculate_dimension_score([iss("blocker")]) == 29
    assert calculate_dimension_score([iss("high")]) == 59


# ------------------------------------------------------------------ 造坏自检

def test_cap_cannot_be_silently_disabled(monkeypatch):
    """把封顶表清空，上面那些判据必须当场变红。

    这条证明「测试能抓住回退」，而不是只证明「现在是对的」。
    """
    import modules.scoring as sc
    monkeypatch.setattr(sc, "RISK_SCORE_CAP", {})
    assert sc.calculate_score([iss("blocker")]) > 29, (
        '封顶表清空后分数没有回升，说明这条自检没接在真实的封顶逻辑上')


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
