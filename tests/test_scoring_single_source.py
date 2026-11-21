# -*- coding: utf-8 -*-
"""守卫：全站只能有一套打分。

============================================================
为什么要有这个文件（2026-11-22）
============================================================

改之前站里有四套算法各算各的：

    报告页健康分   calculate_score            危重 10 / 高 5 / 中 3 / 低 0.5（求和）
    综合等级       calculate_overall_grade    三层各自「引擎加权平均」再叠加
    试扫页健康度   free_try._health_score     危重 45 / 高 30 / 中 8 / 低 2
    试扫页等级     自己一套 90/75/60/40 线

后果不是「不好看」，是同一份代码在不同页面得到不同结论：

  * 441 份完成扫描里 76 份（17.2%）综合分与综合等级互相打架，
    最极端的一份 46 分评 S；
  * 报告页一边列「复核未采纳 10 条」，一边拿这 10 条扣掉 32 分，
    结论说「只有 2 个问题必须修」，分数说 50 分 C 级；
  * 同一段代码在 /try 看到「A 优秀」，正式扫一遍变成「C」。

本文件的四条判据，任何一条红都说明有人又造了一套副本：

  1. 复核判定不成立的条目，一分都不许扣（把握不足 80 的仍要扣）
  2. 等级必须就是分数读出来的那档，0~100 全区间扫一遍
  3. 「分数没到 S 线却是 S 级」这种组合不可能出现
  4. 试扫入口与报告入口，对同一批问题必须给出同一个分

跑法：`python3 tests/test_scoring_single_source.py`（pytest 也能收集）
失败必须以非 0 退出 —— 只写 test_* 不写 runner 的守卫是假绿。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import modules.helpers as _helpers          # noqa: E402
_helpers.is_vip_user = lambda: True          # 守卫不需要真实登录态

from modules.scoring import (                # noqa: E402
    calculate_score, grade_of, score_to_grade, GRADE_TEXT,
    SCORE_S_THRESHOLD, MAX_SCORE,
)


def _issue(severity, **over):
    """造一条最小可用的 issue。"""
    it = {
        'severity': severity,
        'brain_id': over.pop('brain_id', '2'),
        'check_id': over.pop('check_id', 'E2-SEC-TEST-001'),
        'title': over.pop('title', '测试条目'),
        'file_path': over.pop('file_path', 'a.py'),
        'line': over.pop('line', 1),
    }
    it.update(over)
    return it


def _reviewed(severity, confidence=95, **over):
    """一条「规则报出来了、复核判定不成立」的条目。"""
    return _issue(severity, ai_source='ai_false_positive',
                  ai_confidence=confidence,
                  ai_analysis='该变量已做参数化，不存在注入', **over)


# ------------------------------------------------------------------ 判据 1

def test_excluded_issues_do_not_deduct():
    """复核判定不成立的条目，不许从分数里扣。"""
    clean = calculate_score([])
    assert clean == MAX_SCORE, '没有问题时应该是满分，实际 %r' % clean

    one_critical_retracted = [_reviewed('critical')]
    got = calculate_score(one_critical_retracted)
    assert got == MAX_SCORE, (
        '一条被复核判定不成立的危重问题扣了 %d 分。'
        '报告一边说它不成立、一边拿它扣分，就是「结论 2 个问题 / 分数 50 分」的来源'
        % (MAX_SCORE - got))

    raw = calculate_score(one_critical_retracted, include_excluded=True)
    assert raw < MAX_SCORE, 'include_excluded=True 应该还原规则原始严格度，实际 %r' % raw


def test_low_confidence_review_still_deducts():
    """复核把握不足 80 的不许当结论用：仍按问题扣分。"""
    unsure = [_reviewed('critical', confidence=60)]
    got = calculate_score(unsure)
    assert got < MAX_SCORE, (
        '把握只有 60 的复核结论被当成定论了（分数仍满分）。'
        '把握不足时该留在「必须修」里标存疑，不该替客户下结论')


# ------------------------------------------------------------------ 判据 2

def test_grade_is_always_the_score_read_out():
    """等级必须就是分数读出来的那档——0~100 全区间扫一遍。"""
    for score in range(0, 101):
        g = grade_of(score, tier_scores=None, is_vip=True)
        want = score_to_grade(score)
        assert g == want, (
            '分数 %d 应读成 %s 级，实际给了 %s 级。'
            '等级不能是第二套算法' % (score, want, g))


def test_grade_with_tiers_never_contradicts_score():
    """带三层信息时，等级也不许跟分数打架。"""
    layers_all_s = {
        'spec': {'score': 100, 'grade': 'S', 'locked': False, 'incomplete': False},
        'quality': {'score': 100, 'grade': 'S', 'locked': False, 'incomplete': False},
        'security': {'score': 100, 'grade': 'S', 'locked': False, 'incomplete': False},
    }
    for score in range(0, 101):
        g = grade_of(score, layers_all_s, is_vip=True)
        base = score_to_grade(score)
        assert g.startswith(base) or (base == 'S' and g in ('SS', 'SSS')), (
            '三层全 S 把 %d 分的 %s 级抬成了 %s 级。'
            '三层全 S 只能加在 S 之上，不能盖住分数' % (score, base, g))


# ------------------------------------------------------------------ 判据 3

def test_low_score_can_never_be_s_grade():
    """「46 分 S 级」这种组合必须不可能出现。"""
    bad = []
    for score in range(0, SCORE_S_THRESHOLD):
        g = grade_of(score, tier_scores=None, is_vip=True)
        if 'S' in g:
            bad.append((score, g))
    assert not bad, '分数没到 S 线却给了 S 级：%r' % bad[:5]


# ------------------------------------------------------------------ 判据 4

def test_try_page_and_report_page_agree():
    """试扫入口与报告入口，对同一批问题必须给出同一个分。

    /try 是免费通道，等级上限 A 是生意规矩，但分数必须同一个刻度——
    否则同一段代码先在 /try 看、再正式扫，客户会看到两个数。
    """
    from modules.free_try import _health_score

    issues = [
        _issue('critical', category='security'),
        _issue('high', category='quality'),
        _issue('medium', category='architecture'),
        _issue('low', category='quality'),
        _issue('high', category='security', check_id='E2-SEC-TEST-002'),
    ]
    report_score = calculate_score(issues)
    try_result = {'issues': issues}
    try_score = _health_score(try_result)['score']

    assert try_score == report_score, (
        '同一批问题：试扫页 %r 分、报告页 %r 分。两个入口两套权重，'
        '客户只会认为我们在乱报' % (try_score, report_score))

    h = _health_score({'issues': []})
    assert h['score'] == MAX_SCORE, '试扫页干净代码不是满分：%r' % h['score']


def test_grade_text_covers_every_grade():
    """等级的中文读法必须齐，缺一个键会让页面显示「未完整检测」。"""
    for g in ('S', 'A', 'B', 'C', 'D', '—'):
        assert g in GRADE_TEXT, '等级 %s 没有中文读法' % g


# ------------------------------------------------------------------ runner

def _run_all():
    tests = [(k, v) for k, v in sorted(globals().items())
             if k.startswith('test_') and callable(v)]
    if not tests:
        print('没有收集到任何判据 —— 守卫形同不存在')
        return 1
    passed, failed = 0, []
    print('=== 打分单一来源自检（%d 条）===' % len(tests))
    for name, fn in tests:
        try:
            fn()
        except AssertionError as e:
            failed.append((name, str(e)))
            print('  [FAIL] %s\n         %s' % (name, e))
        except Exception as e:
            failed.append((name, '%s: %s' % (type(e).__name__, e)))
            print('  [ERR ] %s\n         %s: %s' % (name, type(e).__name__, e))
        else:
            passed += 1
            print('  [ OK ] %s' % name)
    print('')
    if failed:
        print('结果：%d 条不过（%s）—— 分数/等级又出现第二套算法了'
              % (len(failed), ', '.join(n for n, _ in failed)))
        return 1
    print('结果：%d 条全部通过' % passed)
    return 0


if __name__ == '__main__':
    sys.exit(_run_all())
