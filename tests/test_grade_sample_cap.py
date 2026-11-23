# -*- coding: utf-8 -*-
"""评级必须同时看「分数」和「审查范围」。

背景（2026-11-23）：全库 975 份 S 里 603 份（62%）是单文件或不到 200 行的
片段快检。一个 5 行的 t.py 扫完没报错就是 100 分 -> S，S 因此从荣誉变成默认值。
老板原话：「随随便便都能拿 S，那你这个东西就没有价值」。

第一版只是把片段压到 A——那等于把通胀从 S 挪到 A，A 还是被占着。现在改成
片段扫描不给等级字母，标注「文件级评估」：能说「这段代码查过」，不能说
「这个项目很好」。低档仍然照给——找到问题不需要样本量，只有「没问题」才需要。

判据分四层：
  1. 范围函数的边界（含「未知规模不设限」）；
  2. grade_of 真的按范围处理（高档抹掉、低档保留）；
  3. 等级读法要能区分 S / A / 文件级；
  4. 全仓不许有第二套等级表，页面必须认识「文件级」这个标注。
"""
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from modules.constants import (  # noqa: E402
    GRADE_SCOPE_FRAGMENT, SAMPLE_SMALL_MAX_FILES, SAMPLE_SMALL_MAX_LINES,
    SCOPE_FRAGMENT, SCOPE_PROJECT, SCOPE_UNKNOWN, scan_scope,
)
from modules.scoring import GRADE_TEXT, grade_of, score_to_grade  # noqa: E402


# ── 1. 范围判定的边界 ──────────────────────────────────────
@pytest.mark.parametrize("files,lines,expect", [
    (1, 5, SCOPE_FRAGMENT),            # 5 行单文件
    (1, 5000, SCOPE_FRAGMENT),         # 单文件再大也是片段
    (2, 150, SCOPE_FRAGMENT),          # 行数不足
    (5, 482, SCOPE_FRAGMENT),          # 小样本
    (SAMPLE_SMALL_MAX_FILES - 1, SAMPLE_SMALL_MAX_LINES - 1, SCOPE_FRAGMENT),
    (SAMPLE_SMALL_MAX_FILES - 1, SAMPLE_SMALL_MAX_LINES, SCOPE_PROJECT),  # 行数够
    (SAMPLE_SMALL_MAX_FILES, 300, SCOPE_PROJECT),                         # 文件数够
    (59, 29318, SCOPE_PROJECT),        # 完整项目
])
def test_scan_scope_boundaries(files, lines, expect):
    assert scan_scope(files, lines) == expect


@pytest.mark.parametrize("files,lines", [
    (None, None), (0, 0), (0, None), (None, 0),
])
def test_unknown_scale_is_not_fragment(files, lines):
    """规模未知时不许判定为片段——判不了不等于该判死。

    历史扫描的 file_count / total_lines 默认是 0，把它们当「0 行代码」
    会把整批老报告无理由降级成「文件级」。
    """
    assert scan_scope(files, lines) == SCOPE_UNKNOWN


def test_scan_scope_ignores_text_values():
    """字段是字符串或垃圾值时不能炸，也不能乱判。"""
    assert scan_scope("abc", None) == SCOPE_UNKNOWN
    assert scan_scope("1", "50") == SCOPE_FRAGMENT
    assert scan_scope(None, "") == SCOPE_UNKNOWN


# ── 2. grade_of 按范围处理 ────────────────────────────────
def test_perfect_score_on_snippet_is_not_a_grade():
    """满分 + 5 行单文件 = 文件级。这是这次改动的核心。"""
    assert score_to_grade(100) == 'S'          # 分数本身够 S
    assert grade_of(100, None, is_vip=True, file_count=1, total_lines=5) == GRADE_SCOPE_FRAGMENT


def test_fragment_does_not_take_a_or_b():
    """片段不许占 A——那是把通胀换个档位继续发。"""
    for score in (100, 96, 90, 85, 80):        # 全部落在 S/A 区间
        got = grade_of(score, None, is_vip=True, file_count=1, total_lines=5)
        assert got == GRADE_SCOPE_FRAGMENT, "score=%s 拿到 %s" % (score, got)


def test_fragment_keeps_low_grades():
    """找到问题不需要样本量：单文件里查出毛病，照样给低档。

    片段扫描只抹掉「优秀」这类需要覆盖度支撑的结论。把 D 也抹成「文件级」
    等于用「样本小」盖住「有毒代码」。
    """
    assert grade_of(75, None, is_vip=True, file_count=1, total_lines=5) == 'B'
    assert grade_of(45, None, is_vip=True, file_count=1, total_lines=5) == 'C'
    assert grade_of(10, None, is_vip=True, file_count=1, total_lines=5) == 'D'


def test_perfect_score_on_real_project_stays_s():
    """完整项目满分仍然是 S——门槛不是把所有人都压下去。"""
    assert grade_of(100, None, is_vip=True, file_count=59, total_lines=29318) == 'S'


def test_unknown_scale_keeps_old_behavior():
    """不传规模时行为与改动前一致（老调用点、老记录不会被误伤）。"""
    assert grade_of(100, None, is_vip=True) == 'S'
    assert grade_of(85, None, is_vip=True) == 'A'


def test_free_user_cap_still_wins():
    """免费版上限 A 与范围判定互不干扰。"""
    assert grade_of(100, None, is_vip=False, file_count=59, total_lines=29318) == 'A'
    assert grade_of(100, None, is_vip=False, file_count=1, total_lines=5) == GRADE_SCOPE_FRAGMENT


# ── 3. 等级读法 ───────────────────────────────────────────
def test_grade_text_distinguishes_s_and_a():
    """S 和 A 都叫「优秀」等于没有 S。"""
    assert GRADE_TEXT['S'] != GRADE_TEXT['A']
    assert GRADE_TEXT['S'] == '卓越'
    assert GRADE_TEXT['A'] == '良好'


def test_grade_text_covers_all_grades():
    for g in ('S', 'A', 'B', 'C', 'D', '—', GRADE_SCOPE_FRAGMENT):
        assert g in GRADE_TEXT and GRADE_TEXT[g]


def test_fragment_label_is_not_a_letter_grade():
    """「文件级」不能长得像字母档，否则用户仍会拿它比高低。"""
    assert GRADE_SCOPE_FRAGMENT not in ('S', 'A', 'B', 'C', 'D')


# ── 4. 一个出口 + 页面认识这个标注 ─────────────────────────
# 「xxx if score >= N else 'X'」这种就地写死的等级表，一旦存在，
# 同一份代码走不同入口就会拿到不同等级。api.py 曾有第四套（S 线 90）、
# ci.py 曾有第五套（S 线 90 且没有 S 档）。
# 只抓「给 grade 赋值」的写法。2026-11-24 起组件契约检测也走 grade_of()
# （单文件 → 「文件级」），第六套 CC_SCORE_* 阈值表已删除，这里不再留例外。
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


def test_pages_know_the_fragment_label():
    """页面必须认识「文件级」，否则会渲染成「文件级级」或者一片空白。

    检查的是常量的**值**：改了标注文字，这里跟着变，不会把旧文案钉死。
    """
    for tpl in ("report_shared.html", "try.html"):
        path = os.path.join(ROOT, "templates", tpl)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        assert GRADE_SCOPE_FRAGMENT in text, (
            "%s 不认识「%s」——片段级报告在这一页会显示成空白或「文件级级」"
            % (tpl, GRADE_SCOPE_FRAGMENT))


# ── 5. 组件契约检测不许自带等级表（曾经的第六套） ───────────────
# 它审的是单个 wxml 文件，却按 CC_SCORE_*（S 线 90）自己分档，于是
# scans 表里 5 条组件检测记录带着 S/A/B/C，而同表 972 条只审一个文件的
# 试扫记录写的是「文件级」——同一列两种字母含义。现在两条都走 grade_of()。
_COMPONENT_SAVE = "_save_component_check_record"


def _component_save_body(text):
    idx = text.find("def " + _COMPONENT_SAVE)
    assert idx != -1, (
        "找不到 %s —— 函数改名了这个守卫就失效，改名时同步改这里" % _COMPONENT_SAVE)
    end = text.find("\ndef ", idx + 1)
    return text[idx:end if end != -1 else len(text)]


def _has_inline_grade_table(body):
    """出现「if score >= ...」这种就地分档，说明又造了一套阈值表。"""
    return bool(re.search(r"if\s+score\s*>=", body))


def test_component_check_uses_single_grade_outlet():
    path = os.path.join(ROOT, "modules", "scan.py")
    with open(path, encoding="utf-8") as fh:
        body = _component_save_body(fh.read())
    assert "grade_of(" in body, (
        "组件契约检测没走 grade_of() —— 一个组件的合规分会拿到项目级字母（S），"
        "和「只审一个文件不给字母」的规则打架")
    assert not _has_inline_grade_table(body), (
        "组件契约检测又在自己分档（if score >= ...），应交给 grade_of()")


def test_component_grade_guard_catches_old_code():
    """造坏自检：把删掉的那行原样放回来，上面的判据必须判红。"""
    old = ("cc_grade = 'S' if score >= CC_SCORE_S else "
           "('A' if score >= CC_SCORE_A else 'B')")
    assert _has_inline_grade_table(old), (
        "守卫认不出旧的第六套等级表 —— 换成旧代码它照样报绿，等于没守")
    assert "grade_of(" not in old
