#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""引擎覆盖守卫 —— 锁住「没查」不许显示成「查了没问题」。

## 为什么要有这套断言（2026-11-04）

试扫原来只有一个输入：issues 列表。列表空就是 100 分。于是这两件事
在页面上长得一模一样：

    ① 两百条规则都跑过了，真没查出问题
    ② 安全引擎崩了 / 被降级 / 这个文件压根没解析

用户看到 100 分，会当成 ①。这是「给假安心」，比不报更危险——
不报，用户知道自己没查；满分，用户以为查过了。

判据来自引擎返回的事实（engines / degraded_brains / unsupported / trimmed），
不是我们自己推断。这套守卫锁四条：

1. 全跑成 → 三维都是数字，等级照常给（不许为了防呆把正常结果也弄坏）
2. 安全引擎报错 → 安全维度不许是 100，等级不许还是 A
3. 某维度负责的引擎没被请求 → 该维度「未检测」
4. 有文件没解析 → 三维都不许 100，整体标记不完整
5. 真查出问题时扣分逻辑不受影响（防止改覆盖判定时把扣分改坏）

运行：
    sudo -u xinpect-web env PYTHONDONTWRITEBYTECODE=1 \
        python3 -m pytest tests/test_engine_coverage.py -q
"""

import os
import sys
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parent.parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))


def _free_try():
    """导入官网模块。modules/__init__ 会校验 XINPECT_SECRET（长度≥32）。"""
    os.environ.setdefault('XINPECT_SECRET', 'pytest-placeholder-secret-0123456789abcdef')
    from modules import free_try
    return free_try


def _ok():
    return {'executed': True, 'issues': 0, 'error': ''}


ALL_OK = {'1': _ok(), '2': _ok(), '4': _ok(), '5': _ok(), '6': _ok()}


def test_all_engines_ran_keeps_normal_scores():
    """全跑成、无问题：三维 100、A 级、complete=True。

    这是基准——覆盖判定不能把正常结果也弄坏，否则用户会以为产品坏了。
    """
    ft = _free_try()
    h = ft._health_score({
        'issues': [],
        'engines': dict(ALL_OK),
        'unsupported_count': 0, 'trimmed_count': 0,
    })
    assert h['dims'] == {'security': 100, 'quality': 100, 'arch': 100}, h['dims']
    assert h['grade'] == 'A', h['grade']
    assert h['coverage']['complete'] is True, h['coverage']


def test_security_engine_error_blocks_perfect_security():
    """安全引擎报错 → 安全维度不许满分，等级不许是 A。

    这就是线上那个「安全 100 分 + 1 条越权高危」的另一半：
    引擎没跑成还打满分，等于替它担保。
    """
    ft = _free_try()
    engines = dict(ALL_OK)
    engines['2'] = {'executed': True, 'issues': 0, 'error': 'TimeoutError: 300s',
                    'reason': 'error'}
    h = ft._health_score({
        'issues': [], 'engines': engines,
        'unsupported_count': 0, 'trimmed_count': 0,
    })
    assert h['dims']['security'] != 100, f'安全引擎报错了还给满分: {h["dims"]}'
    assert h['grade'] != 'A', f'没查全还给了 A: {h["grade"]}'
    assert 'security' in (h['coverage']['not_run'] + h['coverage']['partial']), h['coverage']
    assert h['coverage']['engine_reasons'].get('2') == 'error', h['coverage']


def test_engine_not_requested_marks_dimension_not_run():
    """架构引擎没被请求 → 架构维度「未检测」，不给数字。"""
    ft = _free_try()
    engines = {k: v for k, v in ALL_OK.items() if k != '5'}
    h = ft._health_score({
        'issues': [], 'engines': engines,
        'unsupported_count': 0, 'trimmed_count': 0,
    })
    assert isinstance(h['dims']['arch'], str), f'引擎没跑却给了数字: {h["dims"]}'
    assert h['coverage']['complete'] is False, h['coverage']
    assert 'arch' in h['coverage']['not_run'], h['coverage']


def test_unsupported_file_blocks_all_perfect_scores():
    """有文件没解析 → 三维都不许 100。没读过的文件里可能有漏洞。"""
    ft = _free_try()
    h = ft._health_score({
        'issues': [], 'engines': dict(ALL_OK),
        'unsupported_count': 1, 'trimmed_count': 0,
    })
    perfect = [d for d, v in h['dims'].items() if v == 100]
    assert not perfect, f'有文件没解析还给满分: {perfect}'
    assert h['coverage']['complete'] is False, h['coverage']


def test_deduction_still_works_when_engine_ran():
    """引擎都跑了、确实查出问题：扣分逻辑不受覆盖判定影响。"""
    ft = _free_try()
    h = ft._health_score({
        'issues': [
            {'severity': 'high', 'category': 'security'},
            {'severity': 'medium', 'category': 'quality'},
        ],
        'engines': dict(ALL_OK),
        'unsupported_count': 0, 'trimmed_count': 0,
    })
    # 2026-11-22 起权重只有 scoring 一份（危重 10 / 高 5 / 中 3 / 低 0.5）。
    # 这里原来写 70/92，是试扫页私有的 45/30/8/2 那套算出来的；
    # 同一条问题在试扫页和报告页扣的分不一样，正是这轮要消灭的东西。
    assert h['dims']['security'] == 95, h['dims']
    assert h['dims']['quality'] == 97, h['dims']
    assert h['coverage']['complete'] is True, h['coverage']


def test_dim_engines_covers_three_dims_and_matches_brains():
    """维度契约必须和 constants.BRAINS 对得上，别写错引擎编号。

    编号写错是静默失败：维度永远「未检测」或者永远 100，两种都没人报警。
    """
    from modules import dimensions
    from modules.constants import BRAINS

    codes = {b['id']: b['code'] for b in BRAINS}
    assert set(dimensions.DIM_ENGINES) == {'security', 'quality', 'arch'}

    # 每个维度引用的引擎都必须真实存在
    for dim, engines in dimensions.DIM_ENGINES.items():
        for e in engines:
            assert e in codes, f'{dim} 引用了不存在的引擎 {e}'

    # 安全维度必须且只能由 E2 负责
    assert dimensions.DIM_ENGINES['security'] == ('2',), dimensions.DIM_ENGINES['security']
    assert dimensions.DIM_ENGINES['arch'] == ('5',), dimensions.DIM_ENGINES['arch']


if __name__ == '__main__':
    # 没有 pytest 的机器上也能跑（QA 套件有一个「pytest 不可用」分支）。
    _cases = [v for k, v in sorted(globals().items())
              if k.startswith('test_') and callable(v)]
    _failed = 0
    for _fn in _cases:
        try:
            _fn()
            print(f'  [OK]   {_fn.__name__}')
        except AssertionError as _e:
            _failed += 1
            print(f'  [FAIL] {_fn.__name__}: {_e}')
        except Exception as _e:  # noqa: BLE001
            _failed += 1
            print(f'  [ERR ] {_fn.__name__}: {type(_e).__name__}: {_e}')
    print(f'\n{len(_cases) - _failed}/{len(_cases)} 通过')
    raise SystemExit(1 if _failed else 0)
