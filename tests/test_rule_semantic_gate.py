#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""规则语义闸门守卫。

守的不是「清单文件在不在」，是三件会悄悄变坏的事：

  1. **隔离清单变成垃圾桶** —— 一份「这条规则别报了」的清单，最危险的用法是
     有人手工塞一条进去掩盖误报。所以每条都必须能追到一次语义评审，
     且评审必须说清错在哪。
  2. **过滤没真生效** —— 清单写得再漂亮，`drop_offline()` 不生效等于零。
     这条必须真调 normalize_result 跑一遍，不许查字符串了事。
  3. **判据失去判别力** —— 评审模型若哪天开始一律说「不成立」，闸门会把全部
     规则下线（全红）；若一律说「成立」，闸门形同不存在（全绿）。两种都是假判据。
     所以要求评审结果里 sound 与 unsound 同时存在，比例在合理区间内。

跑法：python3 tests/test_rule_semantic_gate.py
造坏自检：python3 tests/test_rule_semantic_gate.py --self-test
"""
import json
import os
import sys
import tempfile

SCANNER = "/opt/xinpect-scanner-green"
AUDIT = os.path.join(SCANNER, "rules", "rule_semantic_audit.json")
CANON = os.path.join(SCANNER, "rules", "quarantine_rules.json")
CONTROLS = os.path.join(SCANNER, "rules", "rule_audit_controls.json")
DEPLOY = "/etc/xinpect/quarantine_rules.json"

MIN_AUDITED = 50          # 少于这个数说明还没真跑过，不算建好
MIN_REASON_LEN = 10       # 理由太短等于没理由
MIN_CONTROL_ACCURACY = 0.80   # 人工标注的对照组，评审必须判对 8 成以上

_MSG = {}


def _note(msg):
    import inspect
    _MSG[inspect.stack()[1].function] = msg


def _load(path, what):
    assert os.path.exists(path), "%s不存在：%s" % (what, path)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _audit():
    return _load(AUDIT, "语义评审结果")


def _quarantine():
    return _load(CANON, "隔离清单")


def _verdicts(doc):
    return {k: (v.get("verdict") or "") for k, v in (doc.get("rules") or {}).items()}


# ---------- 1. 评审结果必须是真跑出来的，不是空壳 ----------
def test_audit_is_substantive():
    doc = _audit()
    rules = doc.get("rules") or {}
    assert len(rules) >= MIN_AUDITED, (
        "评审结果只有 %d 条（至少 %d 条才算建好）。跑 scripts/audit_rule_semantics.py --all"
        % (len(rules), MIN_AUDITED))
    bad = []
    for rid, v in rules.items():
        if v.get("verdict") not in ("sound", "unsound", "weak"):
            bad.append("%s verdict 非法：%r" % (rid, v.get("verdict")))
        if len(str(v.get("reason") or "")) < MIN_REASON_LEN:
            bad.append("%s 评审理由过短" % rid)
        if not v.get("samples"):
            bad.append("%s 没有代码样本（评审没有依据）" % rid)
        if not v.get("audited_at"):
            bad.append("%s 缺评审时间" % rid)
    assert not bad, "评审记录不完整：%s" % bad[:5]
    _note("%d 条规则都有结论、理由、代码样本与时间" % len(rules))


# ---------- 2. 判 unsound 的必须说清错在哪 ----------
def test_unsound_states_the_wrong_point():
    rules = _audit().get("rules") or {}
    bad = [rid for rid, v in rules.items()
           if v.get("verdict") == "unsound"
           and len(str(v.get("wrong_point") or v.get("reason") or "")) < MIN_REASON_LEN]
    assert not bad, "判不成立却没写错在哪：%s" % bad[:5]
    _note("全部 unsound 条目都写明了具体错误")


# ---------- 3. 判据必须有判别力（拿人工标注的对照组验）----------
def test_verdicts_have_discrimination():
    """评审模型判得准不准，只能拿「人已经确认过对错」的规则去验。

    不能拿「全量 sound 占比」当判据：世界的真实分布不是我们能规定的 ——
    这批规则客观上确实大量不成立，占比低不代表判据坏了。判据坏的表现是
    **把明显成立的判成不成立**，所以必须有一组人工标注的正例与负例。
    """
    controls = _load(CONTROLS, "评审对照组")
    items = controls.get("controls") or []
    assert len(items) >= 6, "对照组只有 %d 条（至少 6 条，且正负都要有）" % len(items)
    pos = sum(1 for c in items if c.get("expect") == "sound")
    neg = sum(1 for c in items if c.get("expect") == "unsound")
    assert pos and neg, "对照组必须同时包含正例与负例（现在 pos=%d neg=%d）" % (pos, neg)

    verdicts = _verdicts(_audit())
    # 判据分层：「还没审到」不等于「审错了」。对照组里命中量小的规则会排在队尾，
    # 全量评审跑到一半时它们还没结论 —— 那时报「判据不可信」就是假红。
    # 但也不能因此放过：已审样本不足 6 条时单独报红，说明闸门还没建好。
    tested = [(c, verdicts[c.get("id")]) for c in items if verdicts.get(c.get("id"))]
    assert len(tested) >= 6, (
        "对照组只审到 %d 条（共 %d 条），样本不足以下结论。把评审跑完再来" % (len(tested), len(items)))

    wrong = []
    for c, got in tested:
        if got != c.get("expect"):
            wrong.append("%s 人工判 %s、评审判 %s" % (c.get("id"), c.get("expect"), got))
    accuracy = 1 - len(wrong) / float(len(tested))
    assert accuracy >= MIN_CONTROL_ACCURACY, (
        "对照组已审 %d 条里准确率 %.0f%%（门槛 %.0f%%）：%s —— 评审判据不可信，"
        "先修判据再用它下线规则"
        % (len(tested), accuracy * 100, MIN_CONTROL_ACCURACY * 100, wrong[:4]))

    rules = _audit().get("rules") or {}
    sound = sum(1 for v in rules.values() if v.get("verdict") == "sound")
    unsound = sum(1 for v in rules.values() if v.get("verdict") == "unsound")
    assert unsound > 0, "一条 unsound 都没有 —— 这份评审没有任何产出"
    _note("对照组已审 %d/%d 条，判对 %.0f%%；全量 sound %d / unsound %d"
          % (len(tested), len(items), accuracy * 100, sound, unsound))


# ---------- 4. 隔离清单只能来自评审结论 ----------
def test_quarantine_only_from_audit():
    q = (_quarantine().get("rules") or [])
    verdicts = _verdicts(_audit())
    bad = []
    for r in q:
        rid = r.get("id")
        if verdicts.get(rid) != "unsound":
            bad.append("%s 在评审里是 %r，却进了隔离清单" % (rid, verdicts.get(rid)))
    assert not bad, ("隔离清单里有规则不是评审判的不成立（说明有人手工塞了黑名单）：%s"
                     % bad[:5])
    _note("%d 条隔离规则全部可追到一次 unsound 评审" % len(q))


# ---------- 5. 每条隔离都必须带证据 ----------
def test_quarantine_entries_carry_evidence():
    q = (_quarantine().get("rules") or [])
    assert q, "隔离清单是空的 —— 要么评审还没跑完，要么生成步骤漏了"
    bad = []
    for r in q:
        rid = r.get("id")
        ev = r.get("evidence") or {}
        if len(str(r.get("reason") or "")) < MIN_REASON_LEN:
            bad.append("%s 缺隔离理由" % rid)
        if not isinstance(ev.get("observed_hits"), int) or ev.get("observed_hits", 0) <= 0:
            bad.append("%s 缺命中量证据" % rid)
        if not ev.get("samples"):
            bad.append("%s 缺代码样本" % rid)
        if not r.get("restore"):
            bad.append("%s 缺恢复条件" % rid)
    assert not bad, "隔离条目信息不全：%s" % bad[:5]
    _note("%d 条隔离都带理由、命中量、真实样本与恢复条件" % len(q))


# ---------- 6. 过滤必须真生效（跑一遍，不许查字符串）----------
def test_filter_actually_drops():
    q = (_quarantine().get("rules") or [])
    assert q, "隔离清单为空，无法验证过滤"
    verdicts = _verdicts(_audit())
    unsound_id = q[0]["id"]

    retired = set()
    try:
        with open("/etc/xinpect/retired_rules.json", encoding="utf-8") as f:
            retired = {r.get("id") for r in (json.load(f).get("rules") or [])}
    except Exception:
        pass
    sound_id = next((rid for rid, v in verdicts.items()
                     if v == "sound" and rid not in retired), None)
    assert sound_id, "评审里找不到一条 sound 规则可用于对照"

    sys.path.insert(0, SCANNER)
    import _output_normalize as on
    on._offline_ids.clear()

    result = {"results": {"2": {"issues": [
        {"rule_id": unsound_id, "title": "应被剔除"},
        {"rule_id": sound_id, "title": "应保留"},
    ]}},
        # 顶层两处对外列表也要过同一道过滤（2026-11-22 补：suppressed_issues
        # 实测 17,613 条，比主清单还多，之前完全没过滤）
        "profile_items": [{"rule_id": unsound_id}, {"rule_id": sound_id}],
        "suppressed_issues": [{"check_id": unsound_id}, {"check_id": sound_id}],
    }
    on.normalize_result(result)
    left = [i.get("rule_id") for i in result["results"]["2"]["issues"]]
    assert unsound_id not in left, (
        "隔离规则 %s 的问题没被剔除 —— 隔离清单没生效，等于白写" % unsound_id)
    assert sound_id in left, (
        "对照规则 %s 的问题被误删 —— 过滤范围超出了隔离清单" % sound_id)
    for top_key in ("profile_items", "suppressed_issues"):
        ids = [i.get("rule_id") or i.get("check_id") for i in result[top_key]]
        assert unsound_id not in ids, (
            "顶层 %s 没过滤掉隔离规则 %s（报告页折叠区会照原样露出）" % (top_key, unsound_id))
        assert sound_id in ids, "顶层 %s 误删了对照规则 %s" % (top_key, sound_id)
    _note("真跑一遍：%s 被剔除、%s 保留（含 profile_items / suppressed_issues）"
          % (unsound_id, sound_id))


# ---------- 7. 两份副本必须一致 ----------
def test_deployed_copy_in_sync():
    assert os.path.exists(DEPLOY), "部署副本不存在：%s" % DEPLOY
    a = open(CANON, "rb").read()
    b = open(DEPLOY, "rb").read()
    assert a == b, ("两份隔离清单内容不一致：扫描器读 %s，官网读 %s。"
                    "改完要重新 install 到 /etc/xinpect/" % (CANON, DEPLOY))
    _note("仓库与部署副本逐字节一致（%d 字节）" % len(a))


# ---------- 8. 不许出现第二套判据 ----------
# 允许出现该文件名的只有两处：_output_normalize.py（读，生效）与
# scripts/audit_rule_semantics.py（写，生成）。新增第三个文件必须改这里，
# 而且改的人要当场说明它是读还是写 —— 这个守卫的作用是逼人解释，不是绝对禁止。
ALLOWED_QUARANTINE_FILES = {"_output_normalize.py", "audit_rule_semantics.py"}


def test_no_second_judgement():
    hits = []
    for root, dirs, files in os.walk(SCANNER):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", "tests", "logs", "reports")
                   and not d.startswith(".bak")]
        for fn in files:
            if not fn.endswith(".py") or fn in ALLOWED_QUARANTINE_FILES:
                continue
            p = os.path.join(root, fn)
            try:
                text = open(p, encoding="utf-8", errors="replace").read()
            except Exception:
                continue
            if "quarantine_rules.json" in text:
                hits.append(os.path.relpath(p, SCANNER))
    assert not hits, ("除 _output_normalize.py（读）与 audit_rule_semantics.py（写）外，"
                      "还有人碰隔离清单（会形成第二套判据）：%s" % hits)
    _note("只有 _output_normalize.py 读、audit_rule_semantics.py 写")


# ---------- 造坏自检 ----------
def _self_test():
    """把清单造坏，确认上面每一条都真的会报红；再造回来，确认恢复绿。"""
    import shutil
    tmpdir = tempfile.mkdtemp(prefix="gate_selftest_")
    bak_q = os.path.join(tmpdir, "q.json")
    bak_a = os.path.join(tmpdir, "a.json")
    shutil.copy2(CANON, bak_q)
    shutil.copy2(AUDIT, bak_a)
    results = []

    def run(label, expect_fail):
        fails = []
        for name in sorted(k for k in globals() if k.startswith("test_")):
            try:
                globals()[name]()
            except AssertionError as e:
                fails.append(name)
            except Exception:
                fails.append(name)
        got_fail = bool(fails)
        ok = got_fail == expect_fail
        results.append((label, ok, fails))
        print("  %s  %-38s 报红=%s（预期 %s）%s"
              % ("PASS" if ok else "FAIL", label, got_fail, expect_fail,
                 ("→ " + ",".join(fails)) if fails else ""))

    def restore():
        shutil.copy2(bak_q, CANON)
        shutil.copy2(bak_a, AUDIT)

    try:
        # 基线：先确认干净状态下是绿的（否则后面全红都无意义）
        run("干净状态", False)

        # 造坏 1：往隔离清单塞一条评审为 sound 的规则
        verdicts = _verdicts(_audit())
        sound_id = next((k for k, v in verdicts.items() if v == "sound"), None)
        if sound_id:
            doc = _quarantine()
            doc["rules"].append({"id": sound_id, "reason": "手工塞进来的黑名单",
                                 "restore": "x", "evidence": {"observed_hits": 5,
                                                              "samples": ["x"]}})
            json.dump(doc, open(CANON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            run("隔离清单混入 sound 规则", True)
            restore()

        # 造坏 2：把评审结论全改成 sound（判据失去判别力）
        doc = _audit()
        for v in doc["rules"].values():
            v["verdict"] = "sound"
        json.dump(doc, open(AUDIT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        run("评审全判 sound（闸门失效）", True)
        restore()

        # 造坏 3：评审全判 unsound（闸门全红）
        doc = _audit()
        for v in doc["rules"].values():
            v["verdict"] = "unsound"
            v["wrong_point"] = v.get("wrong_point") or "统一判死"
        json.dump(doc, open(AUDIT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        run("评审全判 unsound（闸门全红）", True)
        restore()

        # 造坏 4：清空隔离清单（生成步骤失效）
        json.dump({"rules": []}, open(CANON, "w", encoding="utf-8"), ensure_ascii=False)
        run("隔离清单被清空", True)
        restore()
    finally:
        restore()
        shutil.rmtree(tmpdir, ignore_errors=True)

    bad = [r for r in results if not r[1]]
    print("\n造坏自检：%d/%d 符合预期" % (len(results) - len(bad), len(results)))
    return 0 if not bad else 1


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    ok = 0
    for fn in tests:
        try:
            fn()
            print("  PASS  %-36s %s" % (fn.__name__, _MSG.get(fn.__name__, "")))
            ok += 1
        except AssertionError as e:
            print("  FAIL  %-36s %s" % (fn.__name__, e))
        except Exception as e:
            print("  ERROR %-36s %s: %s" % (fn.__name__, type(e).__name__, e))
    print("\n规则语义闸门守卫：%d/%d 通过" % (ok, len(tests)))
    return 0 if ok == len(tests) else 1


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(_self_test())
    sys.exit(_run_all())
