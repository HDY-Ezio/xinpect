# -*- coding: utf-8 -*-
"""评级必须同时看「分数」和「审查规模」。

背景（2026-11-23）：全库 975 份 S 里 603 份（62%）是单文件或不到 200 行的
片段快检。一个 5 行的 t.py 扫完没报错就是 100 分 -> S，S 因此从荣誉变成默认值。
老板原话：「随随便便都能拿 S，那你这个东西就没有价值」。

判据分三层：
  1. 规模门槛函数本身的边界（含「未知规模不设限」）；
  2. grade_of 真的按规模封顶；
  3. 全仓不许再有第二套等级表——等级只能有一个出口。
"""
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from modules.constants import (  # noqa: E402
    SAMPLE_GRADE_CAP, SAMPLE_SNIPPET_MAX_LINES, SAMPLE_SMALL_MAX_FILES,
    SAMPLE_SMALL_MAX_LINES, sample_grade_cap,
)
from modules.scoring import GRADE_TEXT, grade_of, score_to_grade  # noqa: E402


# ── 1. 规模门槛的边界 ──────────────────────────────────────
@pytest.mark.parametrize("files,lines,expect", [
    (1, 5, SAMPLE_GRADE_CAP),          # 5 行单文件
    (1, 5000, SAMPLE_GRADE_CAP),       # 单文件再大也是片段
    (2, 150, SAMPLE_GRADE_CAP),        # 行数不足
    (5, 482, SAMPLE_GRADE_CAP),        # 小样本
    (SAMPLE_SMALL_MAX_FILES - 1, SAMPLE_SMALL_MAX_LINES - 1, SAMPLE_GRADE_CAP),
    (SAMPLE_SMALL_MAX_FILES - 1, SAMPLE_SMALL_MAX_LINES, None),   # 行数够
    (SAMPLE_SMALL_MAX_FILES, 300, None),                          # 文件数够
    (59, 29318, None),                 # 完整项目
])
def test_sample_cap_boundaries(files, lines, expect):
    assert sample_grade_cap(files, lines) == expect


@pytest.mark.parametrize("files,lines", [
    (None, None), (0, 0), (0, None), (None, 0),
])
def test_sample_cap_unknown_does_not_punish(files, lines):
    """规模未知时不许判定为小样本——判不了不等于该判死。

    历史扫描的 file_count / total_lines 默认是 0，把它们当「0 行代码」
    会把整批老报告无理由降级。
    """
    assert sample_grade_cap(files, lines) is None


def test_sample_cap_ignores_text_values():
    """字段是字符串或垃圾值时不能炸，也不能乱判。"""
    assert sample_grade_cap("abc", None) is None
    assert sample_grade_cap("1", "50") == SAMPLE_GRADE_CAP
    assert sample_grade_cap(None, "") is None


# ── 2. grade_of 真的按规模封顶 ─────────────────────────────
def test_perfect_score_on_snippet_is_not_s():
    """满分 + 5 行单文件 = A。这是这次改动的核心。"""
    assert score_to_grade(100) == 'S'          # 分数本身够 S
    assert grade_of(100, None, is_vip=True, file_count=1, total_lines=5) == 'A'


def test_perfect_score_on_real_project_stays_s():
    """完整项目满分仍然是 S——门槛不是把所有人都压下去。"""
    assert grade_of(100, None, is_vip=True, file_count=59, total_lines=29318) == 'S'


def test_cap_never_raises_grade():
    """门槛只能往下压，不能把 A 抬成 S。"""
    assert grade_of(82, None, is_vip=True, file_count=59, total_lines=29318) == 'A'
    assert grade_of(45, None, is_vip=True, file_count=1, total_lines=5) == grade_of(
        45, None, is_vip=True)


def test_unknown_scale_keeps_old_behavior():
    """不传规模时行为与改动前一致（老调用点不会被误伤）。"""
    assert grade_of(100, None, is_vip=True) == 'S'


def test_free_user_cap_still_wins():
    """免费版上限 A 与规模门槛互不干扰，取更严的那个。"""
    assert grade_of(100, None, is_vip=False, file_count=59, total_lines=29318) == 'A'


# ── 3. 等级读法要能区分 S 和 A ─────────────────────────────
def test_grade_text_distinguishes_s_and_a():
    """S 和 A 都叫「优秀」等于没有 S。"""
    assert GRADE_TEXT['S'] != GRADE_TEXT['A']
    assert GRADE_TEXT['S'] == '卓越'
    assert GRADE_TEXT['A'] == '良好'


def test_grade_text_covers_all_grades():
    for g in ('S', 'A', 'B', 'C', 'D', '—'):
        assert g in GRADE_TEXT and GRADE_TEXT[g]


# ── 4. 全仓只能有一个等级出口 ──────────────────────────────
# 「xxx if score >= N else 'X'」这种就地写死的等级表，一旦存在，
# 同一份代码走不同入口就会拿到不同等级。api.py 曾有第四套（S 线 90）、
# ci.py 曾有第五套（S 线 90 且没有 S 档）。
# 只抓「给 grade 赋值」的写法。`cc_grade = ...` 是组件契约检测自己的
# 评分体系（CC_SCORE_* 阈值，语义是「单个组件写得合不合规」），
# 不是代码质量评级，不在本守卫范围内。
_INLINE_GRADE = re.compile(r"(?:^|\s)grade\s*=\s*['\"][SABCD]['\"]\s*if\s+score\s*>=")


def test_no_inline_grade_table_in_modules():
    offenders = []
    mod_dir = os.path.join(ROOT, "modules")
    for name in sorted(os.listdir(mod_dir)):
        if not name.endswith(".py"):
            continue
        path = os.path.join(mod_dir, name)
        with open(path, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                if line.lstrip().startswith("#"):
                    continue
                if _INLINE_GRADE.search(line):
                    offenders.append("%s:%d %s" % (name, lineno, line.strip()[:80]))
    assert not offenders, "这些地方还在自己写等级表，应改为 grade_of()：\n" + "\n".join(offenders)


def test_no_hardcoded_grade_threshold_chain():
    """`>= 90 else` 这种链式阈值是等级表的变形写法。"""
    offenders = []
    mod_dir = os.path.join(ROOT, "modules")
    for name in sorted(os.listdir(mod_dir)):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(mod_dir, name), encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                s = line.strip()
                if s.startswith("#"):
                    continue
                # 只抓「等级判断」的写法：同一行既有 >= 又紧跟 else 'X'
                if re.search(r">=\s*\d+\s+else\s+['\"][SABCD]['\"]", s):
                    offenders.append("%s:%d %s" % (name, lineno, s[:80]))
    assert not offenders, "这些地方还在用链式阈值定等级：\n" + "\n".join(offenders)


# ── 5. 调用点必须把规模传下去 ──────────────────────────────
@pytest.mark.parametrize("relpath,min_hits", [
    ("modules/scan.py", 3),
    ("scripts/backfill_score_scope.py", 1),
])
def test_callers_pass_scale(relpath, min_hits):
    """grade_of 不传规模就等于门槛没生效——调用点漏一个，那条路径白改。"""
    path = os.path.join(ROOT, relpath)
    text = open(path, encoding="utf-8").read()
    hits = len(re.findall(r"grade_of\((?:[^()]|\([^()]*\))*file_count=", text))
    assert hits >= min_hits, "%s 只有 %d 处 grade_of 带了 file_count，期望 >= %d" % (
        relpath, hits, min_hits)


# ── 6. 报告页要说明这条规则 ────────────────────────────────
@pytest.mark.parametrize("tpl", ["report.html", "report_shared.html"])
def test_report_explains_sample_cap(tpl):
    """用户看到 A 而不是 S 时必须知道为什么，否则只像系统出错。"""
    path = os.path.join(ROOT, "templates", tpl)
    text = open(path, encoding="utf-8").read()
    assert ("审查规模" in text or "覆盖不足" in text or "样本不足" in text), (
        "%s 没有说明评级与审查规模的关系——用户看到 A 而不是 S 时，"
        "必须能在这里读到原因" % tpl)


# ── 7. 规模字段缺失不能把页面打崩 ──────────────────────────
def test_row_scale_tolerates_missing_fields():
    """真实 scans 表有 total_lines，但测试桩/老记录可能没有。

    直接下标取值会让报告页和导出接口 500——一个只用来设上限的说明性
    字段不该有这种杀伤力。取不到就当未知，未知不设限。
    """
    from modules.scan import _row_scale

    assert _row_scale({}) == (None, None)
    assert _row_scale({'file_count': 2}) == (2, None)
    assert _row_scale({'total_lines': 100}) == (None, 100)
    assert _row_scale({'file_count': 2, 'total_lines': 100}) == (2, 100)
