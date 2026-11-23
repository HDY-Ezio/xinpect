# -*- coding: utf-8 -*-
"""扫描器槽位 "8" 的对外标签必须归并到 E5（2026-11-23）

背景：parallel_runner.py::BRAIN_MODULES 的槽位 "8" 挂的是
engine.e7_deployment_readiness，它报出的规则 ID 是 E5-ARCH-DEPLOY-*，
本身属于 E5「架构与部署」。而 BRAINS 只有 9 项（1~7 + ai + poc）、没有
id="8"，于是 brain_label("8") 落进「未知 id 原样返回」分支，报告「检测维度」
那一栏显示成一个裸数字 8。

修法是 modules.constants 里加 _BRAIN_ID_ALIAS = {"8": "5"}，只影响显示，
不动问题分类与评分口径。本文件钉住三件事：
  1. 槽位 8 显示成 E5，不是裸数字；
  2. 已知引擎与未知 id 的行为都没被这个别名带偏；
  3. 别名表的键在扫描器里真实存在、目标在 BRAINS 里真实登记（防给幽灵发名字）。
"""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RUNTIME = Path("/opt/xinpect-scanner-green/engine/parallel_runner.py")


@pytest.fixture(scope="module")
def consts():
    from modules import constants
    return constants


def test_slot_8_maps_to_e5(consts):
    """槽位 8 的标签就是 E5，和直接查 E5 完全一致。"""
    assert consts.brain_label("8") == "E5 架构与部署"
    assert consts.brain_label("8") == consts.brain_label("5")
    assert consts.brain_label(8) == "E5 架构与部署"      # int 入参也要归一


def test_no_bare_digit_label(consts):
    """绝不把裸 id 当标签返回给用户。"""
    assert consts.brain_label("8") != "8"


def test_known_ids_unchanged(consts):
    """已登记引擎的标签不受别名影响。"""
    assert consts.brain_label("1") == "E1 语法与AST分析"
    assert consts.brain_label("5") == "E5 架构与部署"
    assert consts.brain_label("ai") == "AI语义分析"
    assert consts.brain_label("poc") == "PoC自动验证"


def test_unknown_id_still_verbatim(consts):
    """未知 id 仍原样返回——别名不能变成「任何 id 都自动有名字」。"""
    assert consts.brain_label("9") == "9"
    assert consts.brain_label("zzz") == "zzz"


def test_alias_keys_exist_in_scanner(consts):
    """别名表的键必须是扫描器真实存在的槽位，否则是在给幽灵发名字。"""
    if not RUNTIME.is_file():
        pytest.fail("读不到扫描器 %s —— 本条守卫不能静默跳过（需要 root 或路径存在）" % RUNTIME)
    text = RUNTIME.read_text(encoding="utf-8", errors="replace")
    block = re.search(r"BRAIN_MODULES\s*=\s*\{([\s\S]*?)\n\}", text)
    assert block, "运行时找不到 BRAIN_MODULES，守卫拒绝判绿"
    keys = set(re.findall(r"[\"']([A-Za-z0-9]+)[\"']\s*:", block.group(1)))
    for src in consts._BRAIN_ID_ALIAS:                      # noqa: SLF001
        assert src in keys, "别名键 %r 不在扫描器 BRAIN_MODULES 里（实际：%s）" % (src, sorted(keys))


def test_alias_targets_are_real_brains(consts):
    """别名必须指向一个真实登记的引擎，不能指向空。"""
    for src, dst in consts._BRAIN_ID_ALIAS.items():         # noqa: SLF001
        assert dst in consts.BRAINS_MAP, "别名 %r -> %r 的目标不是登记在册的引擎" % (src, dst)
