#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：正式报告页的维度卡和三层评分，不许再「引擎没跑 = 100 分」。

2026-11-04 之前，报告页和试扫页犯的是同一个错，只是报告页更隐蔽：
  · 9 个引擎维度卡：按 brain 数 issues，空列表就是 100 分
  · 三层评分：层内加权平均，缺的引擎按 0 条 issue 算，也就是按 100 分算
于是这三件事在页面上长得一模一样：引擎跑了没查出问题 / 引擎崩了 / 文件没被解析。
用户看到 100 分 S 级，会当成第一种。

这组用例钉住：
  ① 台账说没跑 → 不给分数，标「未检测」
  ② 台账说报错/文件没解析 → 分数照给（那是已查部分的真实成绩），但标「部分未检测」
  ③ 台账缺失（老报告）→ 退回旧行为，一百多份历史报告不能集体变黄
  ④ 三层评分里，没跑的引擎不许用 100 分顶上；层内查不全不给等级
  ⑤ 干净代码 + 全跑 → 仍然是 100 分 S 级（不能矫枉过正）
  ⑥ 模板真的把「未检测」渲染出来了（写了但没渲染，这个坑踩过）
"""
import json
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

# 除 poc 外，每个 brain 都跑成了。poc 单独处理：它不是检测引擎，
# 台账里通常没有它 —— 正好覆盖「台账没这个键 ≠ 没跑」这条判定。
_ALL_BRAINS = ('1', '2', '3', '4', '5', '6', '7', 'ai')
ENGINES_OK = {b: {'executed': True, 'issues': 0, 'error': ''} for b in _ALL_BRAINS}
# 含 poc 的全量台账，用于「全局降级」这种需要每张卡都参与判定的用例
ENGINES_ALL = dict(ENGINES_OK, poc={'executed': True, 'issues': 0, 'error': ''})


def _engines(**override):
    """复制一份台账，用 brain_id=dict 的方式覆盖单条。"""
    led = {b: dict(v) for b, v in ENGINES_OK.items()}
    for bid, state in override.items():
        led[bid] = state
    return led


def _dim(dims, brain_id):
    for d in dims:
        if d['id'] == brain_id:
            return d
    raise AssertionError(f'维度卡里没有 brain={brain_id}')


def _build(issues=None, vip=True, engines=None, unsupported=0, trimmed=0):
    from modules.scan import _build_dimensions
    return _build_dimensions(issues or [], vip, engines, unsupported, trimmed)


# ---------------------------------------------------------------- 维度卡

def test_no_ledger_keeps_legacy_behavior():
    """老报告（没有 engines 字段）必须保持原样。

    库里 1300 多份历史报告都是在没有台账的年代生成的，这次改完不能让它们
    集体变成「未检测」——那不是诚实，那是把历史数据判死。
    """
    e2 = _dim(_build(), '2')
    assert e2['score'] == 100
    assert e2['not_run'] is False
    assert e2['status_text'] == ''


def test_engine_not_run_shows_no_score():
    """引擎没跑：不许出现 100 这个数字。"""
    led = _engines(**{'2': {'executed': False, 'issues': 0, 'error': '', 'reason': 'degraded'}})
    e2 = _dim(_build(engines=led), '2')
    assert e2['score'] == '—', '引擎被降级了还给分数，等于告诉用户「查过了」'
    assert e2['not_run'] is True
    assert e2['status_text'] == '未检测'


def test_engine_error_keeps_score_but_flags():
    """引擎跑了但报错：那是「扫了一半」，分数可以有，但必须标出来。"""
    led = _engines(**{'2': {'executed': True, 'issues': 0, 'error': 'boom'}})
    e2 = _dim(_build(engines=led), '2')
    assert e2['score'] == 100
    assert e2['not_run'] is False
    assert e2['status_text'] == '部分未检测'


def test_unsupported_files_downgrade_every_card():
    """有文件没被解析时，任何维度的满分都不成立——没读过的代码里可能有洞。"""
    dims = _build(engines=ENGINES_ALL, unsupported=3)
    for d in dims:
        if d['locked']:
            continue
        assert d['status_text'] == '部分未检测', f'{d["code"]} 没有因为残文件降级'


def test_trimmed_files_downgrade_every_card():
    """文件被截断（后半截没进分析）同理。"""
    dims = _build(engines=ENGINES_ALL, trimmed=2)
    for d in dims:
        if d['locked']:
            continue
        assert d['status_text'] == '部分未检测', f'{d["code"]} 没有因为截断降级'


def test_brain_absent_from_ledger_is_not_not_run():
    """台账里没这个键 = 本次没请求它（如 PoC 未启用），不是「跑失败了」。

    这两种混为一谈的话，所有没请求的引擎卡都会挂上「未检测」，变成狼来了。
    """
    assert 'poc' not in ENGINES_OK
    poc = _dim(_build(engines=ENGINES_OK), 'poc')
    assert poc['not_run'] is False
    assert poc['status_text'] == ''


def test_clean_code_still_full_marks():
    """矫枉过正也是错：真查全了、真没问题，就该是 100。"""
    dims = _build(engines=ENGINES_OK)
    for d in dims:
        if d['locked'] or d['id'] == 'poc':
            continue
        assert d['score'] == 100
        assert d['status_text'] == ''


# ---------------------------------------------------------------- 三层评分

def test_tier_missing_engine_not_padded_with_full_marks():
    """防护层里 E2 没跑：分数不能拿 100 分顶上。

    旧逻辑 E2 空 = 100、poc 一条 critical = 60、权重 0.6/0.4
    → 84 分，看起来「还行」。真实情况是安全引擎根本没跑，
    唯一有效的证据只有 PoC 那 60 分。新逻辑只按已查的引擎归一化。
    """
    from modules.scoring import calculate_tier_scores, calculate_dimension_score
    issues = [{'brain_id': 'poc', 'severity': 'critical', 'rule_id': 'P-1'}]
    led = _engines(**{'2': {'executed': False, 'issues': 0, 'error': '', 'reason': 'degraded'}})

    # 这条问题的真实成绩（只有 PoC 在撑），以及「E2 按 100 分顶上」的假成绩
    only_poc = calculate_dimension_score(issues)
    padded = int(round(only_poc * 0.4 + 100 * 0.6))
    assert only_poc != padded, '样本分不清两种算法，测不出问题'

    ts = calculate_tier_scores(issues, is_vip=True, engines=led)
    sec = ts['security']
    assert sec['incomplete'] is True
    assert sec['grade'] == '—', '查不全还给出等级，就是给假安心'
    assert sec['status_text'] == '部分未检测'
    assert sec['score'] == only_poc, f'缺的引擎被当成 100 分顶上了：{sec["score"]}（应为 {only_poc}）'
    assert sec['score'] != padded
    assert sec['missing_brain_ids'] == ['2']


def test_tier_wholly_not_run_has_no_score():
    """一层全没查成：没有分数，只有「未检测」。"""
    from modules.scoring import calculate_tier_scores
    led = _engines(
        **{'2': {'executed': False, 'issues': 0, 'error': '', 'reason': 'no_result'},
           'poc': {'executed': False, 'issues': 0, 'error': '', 'reason': 'no_result'}}
    )
    sec = calculate_tier_scores([], is_vip=True, engines=led)['security']
    assert sec['score'] is None
    assert sec['grade'] == '—'
    assert sec['status_text'] == '未检测'


def test_tier_clean_all_run_is_s():
    """三层全跑全干净 → S（最高档），不误伤。"""
    from modules.scoring import calculate_tier_scores, grade_of
    ts = calculate_tier_scores([], is_vip=True, engines=ENGINES_OK)
    for key, t in ts.items():
        assert t['score'] == 100, f'{key} 层干净代码没拿满分'
        assert t['grade'] == 'S', f'{key} 层干净代码不是 S'
        assert t['incomplete'] is False
    # 干净代码 = 100 分，等级就是 S；2026-11-23 起 S 之上不再有 SS/SSS
    assert grade_of(100, ts, is_vip=True) == 'S'


def test_grade_of_excludes_incomplete_tiers():
    """查不全的层不参与综合评级；一层都没查成时给 '—'，不许给 'S'。

    旧代码「没有可评分层 → 返回 S」正是满分假象的源头之一。

    2026-11-22 起综合等级由 grade_of(分数, 三层) 给出：档位只看分数。
    2026-11-23 起不再在 S 之上叠加 SS/SSS。分数是必填参数——没有分数就没有等级。
    """
    from modules.scoring import grade_of
    all_incomplete = {
        'spec': {'score': None, 'grade': '—', 'locked': False, 'incomplete': True},
        'quality': {'score': None, 'grade': '—', 'locked': False, 'incomplete': True},
        'security': {'score': None, 'grade': '—', 'locked': False, 'incomplete': True},
    }
    # 0 条问题算出来的 100 分在这里必须被挡掉：那是「没看」，不是「干净」
    assert grade_of(100, all_incomplete, is_vip=True) == '—'

    mixed = {
        'spec': {'score': 100, 'grade': 'S', 'locked': False, 'incomplete': False},
        'quality': {'score': 100, 'grade': 'S', 'locked': False, 'incomplete': False},
        'security': {'score': 70, 'grade': '—', 'locked': False, 'incomplete': True},
    }
    # security 查不全 → 只有两层 S；等级仍由分数读出来，给 'S'
    # （不再叠加成 SS/SSS：这个叠加以「三层全 S」为判据，已证明判不住风险）
    assert grade_of(100, mixed, is_vip=True) == 'S'
    # 分数没到 S 线时，三层再漂亮也不许给 S —— 等级是分数的读法，不是第二套算法
    assert grade_of(70, mixed, is_vip=True) == 'B'


# ---------------------------------------------------------------- 模板真渲染

def _report_ctx(**over):
    ctx = dict(
        scan_id='00000000-0000-0000-0000-000000000000',
        report_title='守卫测试',
        score=100, grade='S', conclusion={'headline': '测试', 'detail': ''},
        file_count=1, total_issues=0, created_at='2026-11-04 00:00',
        dimensions=over.get('dimensions') or [],
        tier_scores=over.get('tier_scores') or {},
        tiers=[], visible_issues=[], visible_issues_count=0,
        style_issues=[], style_count=0, profile_groups=[], profile_count=0,
        suppressed_groups=[], suppressed_total=0, suppressed_stats={},
        severity_counts={'critical': 0, 'high': 0, 'medium': 0, 'low': 0, 'info': 0},
        bb_scores={}, is_vip=True, scan_mode='deep', is_fix_eligible=False,
        fix_roadmap=[], fix_progress=None, share_token='tok',
    )
    ctx.update(over)
    return ctx


def test_template_actually_renders_not_detected():
    """写了分支不等于页面会显示。必须真的渲染一遍模板再断言。

    `report.html` 曾经有过「include 写了但母版没渲染」的先例，
    所以这里不搜源码、直接渲染成品 HTML。
    """
    from flask import render_template
    from app import app          # 导入入口模块，确保所有路由已注册（url_for('index') 要能构建）
    from modules.constants import TIERS
    from modules.scan import _build_dimensions
    from modules.scoring import calculate_tier_scores

    led = _engines(
        **{'2': {'executed': False, 'issues': 0, 'error': '', 'reason': 'degraded'},
           'poc': {'executed': True, 'issues': 0, 'error': ''}}
    )
    dims = _build_dimensions([], True, led, 0, 0)
    ts = calculate_tier_scores([], is_vip=True, engines=led)

    with app.test_request_context('/report/x'):
        html = render_template(
            'report.html',
            **_report_ctx(dimensions=dims, tier_scores=ts, tiers=TIERS),
        )

    # 用本功能独有的文案断言，别用泛化的「未检测」——
    # 积木五维那边本来就有「未检测」三个字，会把这个断言测成永远通过。
    assert '未检测（无结果）' in html, '维度卡没渲染出「未检测（无结果）」'
    assert '部分未检测' in html, '三层卡没渲染出「部分未检测」'
    # 安全卡的分数位置不能是 100
    e2_block = html.split('data-brain="2"', 1)[1].split('data-brain="3"', 1)[0]
    assert '>100<' not in e2_block, '安全引擎没跑，页面仍然显示 100 分'


def test_template_shows_clean_full_marks():
    """反向断言：干净代码的页面里不该冒「未检测」。"""
    from flask import render_template
    from app import app
    from modules.constants import TIERS
    from modules.scan import _build_dimensions
    from modules.scoring import calculate_tier_scores

    led = _engines(**{'poc': {'executed': True, 'issues': 0, 'error': ''}})
    dims = _build_dimensions([], True, led, 0, 0)
    ts = calculate_tier_scores([], is_vip=True, engines=led)

    with app.test_request_context('/report/x'):
        html = render_template(
            'report.html',
            **_report_ctx(dimensions=dims, tier_scores=ts, tiers=TIERS),
        )
    for flag in ('未检测（无结果）', '部分未检测'):
        assert flag not in html, f'干净代码的页面里出现了「{flag}」'


# ---------------------------------------------------------------- 维度归属

def test_rule_prefix_decides_brain():
    """规则编号首段说了算：E2-* 的规则即使被 E1 执行，也归安全卡。

    引擎 `engine/e1_syntax/checks/security/` 下有 176 个安全规则文件，
    产出时 brain_id 写成 1，于是安全卡 0 条 = 100 分。这是用户看到
    「安全 100 分，却有越权高危」的直接原因。
    """
    from modules.scanner import _dimension_brain

    assert _dimension_brain('1', 'E2-SEC-SQL-001') == '2'
    assert _dimension_brain('1', 'E2-BIZ-PY-002') == '2'
    assert _dimension_brain('1', 'E2-SEC-HCS-001') == '2'
    # 没有引擎前缀的编号保持引擎实际归属
    assert _dimension_brain('3', 'PERF-IO-002') == '3'
    assert _dimension_brain('1', 'C12-29') == '1'
    assert _dimension_brain('1', 'DEP-001') == '1'
    assert _dimension_brain('1', '') == '1'
    # 前缀指向不存在的引擎：不猜，保持原归属
    assert _dimension_brain('1', 'E9-XXX-001') == '1'
    assert _dimension_brain('1', 'E1-AST-001') == '1'


def test_security_category_overrides_wrong_rule_number():
    """编号写错了也要归对：category=security 的规则一律进安全卡。

    实测 828 条已注册规则里有 53 条安全规则被编成非 E2 号
    （48 条 E3-*：E3-TAINT-PY-001 是 SQL 注入、E3-PERF-RUBY-XSS-001 是 XSS，
    另 1 条 E1-*、4 条无前缀）。只认编号的话，它们全落进「性能与可靠性」卡，
    安全卡照样 100 分——和用户最初报的「安全满分 + 越权高危」是同一个病。
    """
    from modules.scanner import _dimension_brain

    # 编号说性能，实质是安全 → 安全卡
    assert _dimension_brain('3', 'E3-TAINT-PY-001', 'security') == '2'
    assert _dimension_brain('3', 'E3-PERF-RUBY-XSS-001', 'security') == '2'
    assert _dimension_brain('1', 'E1-XXX-001', 'security') == '2'
    assert _dimension_brain('4', 'SOMETHING-001', 'security') == '2'
    # category 大小写/空格不该影响判定
    assert _dimension_brain('3', 'E3-TAINT-PY-001', ' Security ') == '2'

    # 非安全 category 不改变既有归属（不许借此把别的规则也搬走）
    assert _dimension_brain('3', 'E3-TAINT-PY-001', 'performance') == '3'
    assert _dimension_brain('3', 'PERF-IO-002', 'performance') == '3'
    assert _dimension_brain('2', 'E2-SEC-SQL-001', '') == '2'


def test_security_rule_lands_in_security_card():
    """端到端钉住用户诉状：一条 E2-* 高危必须在安全卡里，且安全卡不许还是 100。"""
    from modules.scanner import _flatten_brain_results

    raw = {'results': {'1': {'issues': [
        {'check_id': 'E2-SEC-SQL-001', 'name': 'SQL注入风险', 'severity': 'high',
         'file': 'a.py', 'line': 3, 'category': 'security'},
        {'check_id': 'E1-AST-001', 'name': '命名不规范', 'severity': 'low',
         'file': 'a.py', 'line': 1, 'category': 'style'},
    ]}}}
    issues, _style, _profile = _flatten_brain_results(raw, ['1'], {'a.py': 'x = 1\n'})

    by_rule = {i['rule_id']: i for i in issues}
    assert by_rule['E2-SEC-SQL-001']['brain_id'] == '2', '安全规则还挂在 E1 卡下'
    assert by_rule['E1-AST-001']['brain_id'] == '1'

    led = _engines(**{'2': {'executed': True, 'issues': 1, 'error': ''}})
    dims = _build(issues, engines=led)
    sec = _dim(dims, '2')
    assert sec['issues_count'] == 1
    assert sec['score'] < 100, f'安全卡有高危却是 {sec["score"]} 分'
    assert _dim(dims, '1')['issues_count'] == 1


def test_conclusion_does_not_claim_clean_when_engine_crashed():
    """引擎崩了、0 条问题，第一屏不许写「代码质量优秀」。

    维度卡改成「未检测」之后，如果一句话结论还在报喜，等于把刚补的那层
    诚实又抹掉了——用户只看第一屏。

    2026-11-22：结论改由 report_verdict.build(issues, gaps=...) 一处给出，
    缺口由调用方从引擎台账算出。原来这里测的 _build_conclusion 已经删掉
    （它是第二个拼装处：页面一套、Markdown 导出另一套）。
    """
    from modules.report_verdict import build

    crashed = build([], gaps=['安全检测 没有出结果'])['conclusion']
    assert '优秀' not in crashed['headline']
    assert '没有问题' not in crashed['headline'], '引擎没跑成还敢说没有问题'
    assert crashed['tone'] == 'warn'
    assert '没检查全' in crashed['headline'], crashed['headline']

    clean = build([], gaps=[])['conclusion']
    assert clean['tone'] == 'good'
    assert '没有需要处理的问题' in clean['headline'], clean['headline']


# ---------------------------------------------------------------- 落库白名单

def test_ledger_fields_are_in_payload_whitelist():
    """call_scanner 是白名单组装，不列进去的字段到不了库。

    这条已经咬人两次（被抑制清单、引擎台账）。unsupported/trimmed 只落
    engines 不落这两个，报告页就只看得到「引擎跑了」，看不到「跑的是残文件」。
    """
    from modules.scanner import REPORT_PAYLOAD_KEYS

    for key in ('engines', 'unsupported_files', 'trimmed_files', 'degraded_brains'):
        assert key in REPORT_PAYLOAD_KEYS, f'报告页要用 {key}，但它不在落库白名单里'


def test_ledger_of_reads_three_fields():
    """三条渲染路径共用的取值函数，不能只取 engines。"""
    from modules.scan import _ledger_of

    led, uns, trim = _ledger_of({
        'engines': {'2': {'executed': True}},
        'unsupported_files': ['a.go', 'b.go'],
        'trimmed_files': ['c.py'],
    })
    assert led == {'2': {'executed': True}}
    assert uns == 2
    assert trim == 1

    # 老报告：三个键都没有
    assert _ledger_of({}) == (None, 0, 0)
    assert _ledger_of(None) == (None, 0, 0)
