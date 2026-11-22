#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""退役规则清单守卫。

守的不是「文件在不在」，是「这份清单会不会变成垃圾桶」：
一份「不再报出某些规则」的清单，最危险的用法是有人手工往里塞一条
「这条规则别报了」来掩盖误报。所以每条都必须带实测证据，且证据必须够格。

另外守两件容易悄悄坏掉的事：
  · 清单有两份物理副本（仓库 / 部署），必须逐字节一致，否则扫描器读的和
    官网读的不是同一份判据；
  · 空匹配规则的拦截必须真的生效 —— 这是「以后别再进新的坏规则」的唯一防线，
    它要是坏了，清单只会越来越长。

跑法：python3 tests/test_retired_rules_gate.py
"""
import importlib.util
import json
import os
import sys

CANON = "/opt/xinpect-scanner-green/rules/retired_rules.json"
DEPLOY = "/etc/xinpect/retired_rules.json"
MIN_RATIO = 0.80
MIN_HITS = 10


# pytest 会收集本文件里的 test_*，而 pytest 不接受测试函数有返回值
# （PytestReturnNotNoneWarning，未来版本直接报错）。所以说明文字走 _note()
# 记到全局，由 _run_all 打印；测试函数自身只断言、不返回。
_MSG = {}


def _note(msg):
    import inspect
    _MSG[inspect.stack()[1].function] = msg


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _doc():
    assert os.path.exists(CANON), "清单不存在：%s" % CANON
    return _load(CANON)


# ---------- 1. 结构必须完整 ----------
def test_every_rule_has_evidence():
    doc = _doc()
    rules = doc.get("rules") or []
    assert rules, "清单里一条规则都没有（要么没生成，要么被清空了）"
    missing = []
    for r in rules:
        ev = r.get("evidence") or {}
        for key in ("hits", "false_positives", "true_positives"):
            if not isinstance(ev.get(key), int):
                missing.append("%s 缺 evidence.%s" % (r.get("id"), key))
        if not r.get("reason"):
            missing.append("%s 缺 reason" % r.get("id"))
        if not r.get("restore"):
            missing.append("%s 缺 restore（恢复条件）" % r.get("id"))
        if not r.get("retired_at"):
            missing.append("%s 缺 retired_at" % r.get("id"))
    assert not missing, "清单条目信息不全：%s" % missing[:5]
    _note("每条都带实测证据、退役原因、恢复条件（共 %d 条）" % len(rules))


# ---------- 2. 证据必须够格 ----------
def test_evidence_meets_threshold():
    """误报率不到阈值的不许进清单 —— 否则清单就是掩盖问题的手工黑名单。"""
    doc = _doc()
    bad = []
    for r in doc.get("rules") or []:
        ev = r.get("evidence") or {}
        hits = ev.get("hits") or 0
        fp = ev.get("false_positives") or 0
        ratio = fp / hits if hits else 0
        if hits < MIN_HITS:
            bad.append("%s 命中仅 %d 次（门槛 %d）" % (r.get("id"), hits, MIN_HITS))
        elif ratio < MIN_RATIO:
            bad.append("%s 误报率 %.0f%%（门槛 %.0f%%）" % (r.get("id"), ratio * 100, MIN_RATIO * 100))
    assert not bad, "清单里有证据不达标的规则：%s" % bad[:5]
    _note("全部 %d 条都满足「命中≥%d 且误报率≥%.0f%%」" % (
        len(doc.get("rules") or []), MIN_HITS, MIN_RATIO * 100))


# ---------- 3. 两份副本必须一致 ----------
def test_deployed_copy_in_sync():
    assert os.path.exists(DEPLOY), "部署副本不存在：%s" % DEPLOY
    a = open(CANON, "rb").read()
    b = open(DEPLOY, "rb").read()
    assert a == b, ("两份清单内容不一致：扫描器读 %s，官网读 %s。"
                    "改完清单要重新 install 到 /etc/xinpect/" % (CANON, DEPLOY))
    _note("仓库与部署副本逐字节一致（%d 字节）" % len(a))


# ---------- 4. 空匹配拦截必须真的生效 ----------
def test_empty_match_rule_is_blocked():
    """这条防线坏了，坏规则会源源不断进来，清单永远治不完。"""
    sys.path.insert(0, "/opt/xinpect-scanner-green")
    from engine.misc.rule_direction_guard import judge_broken

    must_block = [
        "(?<!networkSecurityConfig)",     # 空匹配：任何位置都中
        "a*",                              # 空匹配
        r"\w*",                            # 空匹配
    ]
    must_pass = [
        r"eval\s*\(",                      # 正常规则
        r"<img(?!alt)",                    # 正常负向断言
    ]
    errs = []
    for pat in must_block:
        lvl, why = judge_broken({"pattern": pat})
        if lvl != "hard":
            errs.append("该拦没拦：%r" % pat)
    for pat in must_pass:
        lvl, why = judge_broken({"pattern": pat})
        if lvl == "hard":
            errs.append("误拦正常规则：%r（%s）" % (pat, why))
    assert not errs, errs
    _note("空匹配拦截生效（拦 %d 条 / 放行 %d 条）" % (len(must_block), len(must_pass)))


# ---------- 5. 清单不得出现在绕过逻辑里 ----------
def test_no_bypass_whitelist():
    """清单只允许被 _output_normalize 读取；别处再建一份禁用名单就是双头判据。"""
    hits = []
    for root, dirs, files in os.walk("/opt/xinpect-scanner-green"):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", "tests", "logs", "reports")
                   and not d.startswith(".bak")]
        for fn in files:
            if not fn.endswith(".py"):
                continue
            p = os.path.join(root, fn)
            if fn == "_output_normalize.py":
                continue
            try:
                t = open(p, encoding="utf-8", errors="replace").read()
            except Exception:
                continue
            if "retired_rules.json" in t or "retired_rule_ids" in t:
                hits.append(os.path.relpath(p, "/opt/xinpect-scanner-green"))
    assert not hits, "除 _output_normalize.py 外还有人读退役清单（会形成第二套判据）：%s" % hits
    _note("只有 _output_normalize.py 读清单，无第二套判据")


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    ok = 0
    for fn in tests:
        try:
            fn()
            print("  PASS  %-34s %s" % (fn.__name__, _MSG.get(fn.__name__, "")))
            ok += 1
        except AssertionError as e:
            print("  FAIL  %-34s %s" % (fn.__name__, e))
        except Exception as e:
            print("  ERROR %-34s %s: %s" % (fn.__name__, type(e).__name__, e))
    print("\n退役规则清单守卫：%d/%d 通过" % (ok, len(tests)))
    return 0 if ok == len(tests) else 1


if __name__ == "__main__":
    sys.exit(_run_all())
