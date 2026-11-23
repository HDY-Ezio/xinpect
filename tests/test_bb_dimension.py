#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：报告页积木五维不许再退回「永远满分」。

2026-11-04 之前这一块是三层假象叠在一起：
  ① 对照表写 `ARCH-BB-001`，引擎出口是 `E5-ARCH-BB-001` —— 六条规则零命中
  ② 被跨引擎去重合并的规则只留在 also_detected_by 里，只读 check_id 看不见
  ③ AI 降级到 low 的问题被分进 style_issues，完全不计
  ④ detected 硬编码 True，引擎没跑也显示满分
五维因此无论代码什么样都是 100 分 S 级。

这组用例逐条钉住上面四条，并额外钉两条等级语义：
  · 扣过分就不能还是 100
  · 有高危就不能还是 S（S 阈值 95，一条 high 只扣 5 分，不额外约束就会
    「S 级 + 一条高危」，和「安全 100 分 + 越权高危」是同一种自相矛盾）
"""
import os
import sys
from pathlib import Path

import pytest

SITE = Path('/opt/xinpect-website')
pytestmark = pytest.mark.skipif(
    not (SITE / 'modules' / 'scoring.py').exists(),
    reason='官网代码不在本机',
)
os.environ.setdefault('XINPECT_SECRET', 'pytest-placeholder-secret-0123456789abcdef')
if str(SITE) not in sys.path:
    sys.path.insert(0, str(SITE))

ENGINES_OK = {b: {'executed': True, 'issues': 0, 'error': ''}
              for b in ('1', '2', '4', '5', '6')}
ENGINES_ERR = dict(ENGINES_OK, **{'5': {'executed': True, 'issues': 0, 'error': 'boom'}})
ENGINES_NO5 = {b: v for b, v in ENGINES_OK.items() if b != '5'}


def _calc(issues=None, style=None, engines=None, files=1):
    from modules.scoring import calculate_building_block_scores
    return calculate_building_block_scores(
        issues or [], file_count=files, style_issues=style, engines=engines)


def test_rule_table_matches_engine_output():
    """对照表必须用引擎真正产出的编号。

    引擎出口是 `E5-ARCH-BB-00x`（E5 = 架构引擎）。表里少写 `E5-` 前缀
    就会全部落空 —— 这正是曾经五维永远满分的第一个原因。
    """
    from modules.scoring import _BB_DIMENSION_RULES

    for key, dim in _BB_DIMENSION_RULES.items():
        assert dim['rule_ids'], f'{key} 没有配任何规则编号'
        for rid in dim['rule_ids']:
            assert rid.startswith('E5-ARCH-BB-'), (
                f'{key} 的 {rid} 不是引擎产出的编号格式（应为 E5-ARCH-BB-00x）')

    covered = {rid for d in _BB_DIMENSION_RULES.values() for rid in d['rule_ids']}
    expect = {f'E5-ARCH-BB-00{i}' for i in range(1, 7)}
    assert covered == expect, f'六条积木规则没覆盖全，缺 {expect - covered}'


def test_canonical_id_hits():
    r = _calc([{'check_id': 'E5-ARCH-BB-001', 'severity': 'high', 'file': 'a.py'}],
              engines=ENGINES_OK)
    assert r['one_module_one_thing']['issue_count'] == 1
    assert r['one_module_one_thing']['score'] < 100


def test_merged_rule_is_counted():
    """跨引擎去重把同 file/line 的问题合并后，被合并的规则只留在
    also_detected_by / root_cause_merged 里。只读 check_id 会漏掉它们，
    实测积木规则里的 BB-003 每次都走这条路。"""
    issue = {
        'check_id': 'E5-ARCH-BB-001', 'severity': 'high', 'file': 'a.py', 'line': 1,
        'also_detected_by': [{'rule_id': 'E5-ARCH-BB-003', 'severity': 'high'}],
    }
    r = _calc([issue], engines=ENGINES_OK)
    assert r['one_module_one_thing']['issue_count'] == 2, (
        '同一条 issue 上的两个规则要各算一次，否则维度和总分都低估')

    issue2 = {
        'check_id': 'E5-ARCH-BB-001', 'severity': 'high', 'file': 'a.py', 'line': 1,
        'root_cause_merged': [{'rule_id': 'E5-ARCH-BB-003', 'severity': 'high'}],
    }
    r2 = _calc([issue2], engines=ENGINES_OK)
    assert r2['one_module_one_thing']['issue_count'] == 2


def test_downgraded_style_issues_count():
    """AI 复审把问题降到 low 后分进 style_issues。规则确实报了、证据确实在，
    丢掉就等于「查出来了但装作没看见」，「入口统一」「测试完备」会永远满分。"""
    r = _calc(style=[
        {'check_id': 'E5-ARCH-BB-004', 'severity': 'low', 'file': 'pkg/a.py'},
        {'check_id': 'E5-ARCH-BB-006', 'severity': 'low', 'file': 'pkg/c.py'},
    ], engines=ENGINES_OK)
    assert r['one_module_one_entry']['issue_count'] == 1
    assert r['one_module_one_entry']['score'] < 100, '有命中就不能是满分'
    assert r['one_module_one_test']['score'] < 100


def test_engine_not_run_is_not_perfect():
    """E5 报错 / 根本没请求，都不能显示 100 分 ——
    那和「查了没问题」长得一模一样，是这一整类假象里最危险的一种。"""
    for label, engines in (('报错', ENGINES_ERR), ('没请求', ENGINES_NO5)):
        r = _calc(engines=engines)
        assert all(not v['detected'] for v in r.values()), f'{label}时应显示未检测'
        assert all(v['score'] is None for v in r.values()), f'{label}时不能给分数'


def test_legacy_report_keeps_old_behaviour():
    """老报告的 results 里没有 engines（那字段今天才进白名单）。
    不能因此把 1300+ 份历史报告全变成「未检测」——历史数据里本就没这个事实，
    凭空判「没跑」是制造另一种假。"""
    r = _calc([{'check_id': 'E5-ARCH-3S-001', 'severity': 'high', 'file': 'a.py'}],
              engines=None)
    assert all(v['detected'] for v in r.values())
    assert r['one_module_one_thing']['score'] < 100, '历史 3S 编号仍要能命中'

    r2 = _calc([{'check_id': 'ARCH-BB-005', 'severity': 'high', 'file': 'a.py'}],
               engines=ENGINES_OK)
    assert r2['clean_splicing']['score'] < 100, '更早的无前缀编号仍要能命中'


def test_deducted_never_stays_100():
    """low 一档扣 0.5 分，calculate_score 最后 int(round()) 会抹回整数。
    扣了分却显示满分，就是「满分 + 有问题」。"""
    for sev in ('critical', 'high', 'medium', 'low'):
        r = _calc([{'check_id': 'E5-ARCH-BB-001', 'severity': sev, 'file': 'a.py'}],
                  engines=ENGINES_OK)
        assert r['one_module_one_thing']['score'] < 100, f'{sev} 扣分了却还是 100'


def test_severe_issue_never_gets_top_grade():
    """S 级阈值 95，一条 high 只扣 5 分 → 95 仍是 S。
    「S 级 + 一条高危」和「安全 100 分 + 越权高危」是同一种自相矛盾。"""
    for sev in ('critical', 'high', 'suspicious'):
        r = _calc([{'check_id': 'E5-ARCH-BB-001', 'severity': sev, 'file': 'a.py'}],
                  engines=ENGINES_OK)
        assert r['one_module_one_thing']['grade'] != 'S', f'{sev} 不该给最高等级'

    r = _calc(engines=ENGINES_OK)
    assert all(v['grade'] == 'S' and v['score'] == 100 for v in r.values()), (
        '真没问题时该是满分 S')


def test_clean_code_still_perfect():
    r = _calc([{'check_id': 'E2-BIZ-PY-002', 'severity': 'high', 'file': 'a.py',
                'category': 'security'}], engines=ENGINES_OK)
    assert all(v['score'] == 100 and v['detected'] for v in r.values()), (
        '非积木规则不该影响五维')
