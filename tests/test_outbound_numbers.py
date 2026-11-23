#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对外数字口径守卫（2026-11-22 建；2026-11-23 纠正引擎口径后重写）

治的是什么：官网三个数字互相打架，且都比事实大。

引擎数 = **7**，不是 8：
  engine/parallel_runner.BRAIN_MODULES 有 8 个槽位，但槽 8 的模块路径是
  `engine.e7_deployment_readiness`——它归属 E7。「ai」「poc」是两道智能验证，不是规则引擎。
  design.md 里原本就写着：「运行时还有 8 号模块，它归属 E7，不是第 8 个引擎」。
  ⚠ 2026-11-22 有人（我）数了 BRAIN_MODULES 的键，把全站 7 改成 8，还写了这一版守卫
  去禁止 7——**守卫变成了错误的帮凶**。第二天被 verify_engine_claims.py 的运行时推导挡回来。
  现在这条只禁 8，7 必须能过。

规则数 9,481 条去重 → 对外 9,400+；语言 23 = AST/数据流级 17 + 规则级 6。

判据只写「禁止什么」，不写「必须包含什么」——文案换说法不该判红。
运行：python3 -m pytest tests/test_outbound_numbers.py -q
"""
import os
import re
import sys

import pytest

ROOT = os.environ.get("XINPECT_WEB_ROOT", "/opt/xinpect-website")

FORBIDDEN = [
    (r"17\s*种\s*(?:主流)?(?:编程)?语言",
     "语言数写成 17 种（那是 AST 解析层的窄口径，对外总数是 23 = 17 AST + 6 规则级）"),
    (r"(?:八|8)\s*(?:大|个)\s*(?:规则)?引擎",
     "引擎数写成 8（BRAIN_MODULES 有 8 个槽位，但 8 号模块路径是 e7_deployment_readiness，"
     "归属 E7；规则引擎族只有 7 个）"),
    (r"9,?\s*500\s*\+", "规则数写成 9,500+（实测 9,481 条，对外口径 9,400+）"),
]

# 对外物料：全站活跃模板 + 静态页 + 给 AI 爬虫看的 llms.txt
TARGETS = ["templates", "static/pages", "static/llms.txt"]

# 对外唯一语言数。改它必须同时改 help.html 那份枚举，否则下面第三条测试会红。
LANG_TOTAL = 23
HELP_REL = "templates/help.html"


def _iter_files(root):
    for t in TARGETS:
        p = os.path.join(root, t)
        if os.path.isfile(p):
            yield p
        elif os.path.isdir(p):
            for fn in sorted(os.listdir(p)):
                if fn.endswith(".html"):
                    yield os.path.join(p, fn)


def scan_text(text):
    """返回命中的 [(说明, 命中原样)]。单一判据入口，测试与造坏自检共用。

    「不是第 8 个引擎」这种是在解释「8 号槽位不等于第 8 个引擎」，属于正确说法，
    必须放过——否则守卫会逼着人把事实说明也删掉。
    """
    hits = []
    for pat, why in FORBIDDEN:
        for m in re.finditer(pat, text):
            head = text[max(0, m.start() - 4):m.start()].rstrip()
            if why.startswith("引擎数") and head.endswith("第"):
                continue
            hits.append((why, m.group(0)))
    return hits


def scan_root(root):
    bad = []
    for path in _iter_files(root):
        try:
            text = open(path, encoding="utf-8").read()
        except Exception:
            continue
        for why, hit in scan_text(text):
            bad.append("%s: %s（%r）" % (os.path.relpath(path, root), why, hit))
    return bad


def test_no_stale_outbound_numbers():
    """全站模板与 llms.txt 不得再出现错误口径（8 个引擎 / 17 种语言 / 9,500+）。"""
    root = ROOT
    if not os.path.isdir(os.path.join(root, "templates")):
        pytest.skip("找不到官网模板目录：%s" % root)
    bad = scan_root(root)
    assert not bad, "对外数字口径回退：\n" + "\n".join(bad)


def test_help_enumeration_matches_declared_count():
    """声明的语言数必须等于它自己列出来的语言个数。

    这条是治本的一半：23 这个数字不是拍出来的，是 help.html 那份枚举数出来的。
    谁以后再改清单（加一种语言 / 删一种语言）而忘了改数字，这里当场红。
    """
    path = os.path.join(ROOT, HELP_REL)
    if not os.path.isfile(path):
        pytest.skip("找不到帮助页：%s" % path)
    text = open(path, encoding="utf-8").read()
    m = re.search(r"支持\s*(\d+)\s*种编程语言[:：]([^<。]+)", text)
    assert m, "帮助页找不到「支持 N 种编程语言：<枚举>」这句"
    declared = int(m.group(1))
    names = [x.strip(" 。；;\n") for x in m.group(2).split("、") if x.strip(" 。；;\n")]
    assert declared == len(names), (
        "帮助页自相矛盾：写着 %d 种，实际列了 %d 种：%s"
        % (declared, len(names), "、".join(names)))
    assert declared == LANG_TOTAL, (
        "对外语言数应为 %d，帮助页写着 %d（改口径要同时改这里和正文）"
        % (LANG_TOTAL, declared))


def test_detector_can_fail():
    """造坏自检：故意写回错误口径，判据必须报出来。

    只让「没命中」等于绿是不够的——判据本身写错（比如正则拼错）也会一直绿。
    这里先证明它会红，再谈上面的绿有意义。
    """
    bad_text = "支持 17 种语言，8 个规则引擎，9,500+ 条规则"
    hits = scan_text(bad_text)
    assert len(hits) == 3, "造坏样本应命中 3 类，实际 %d 类：%s" % (len(hits), hits)


def test_clean_text_passes():
    """阴性对照：现在的正确说法不能被误判。"""
    good = "7 个规则引擎 + AI 语义 + PoC 验证，9,400+ 条检测规则，23 种语言"
    assert scan_text(good) == []
    # 「上面列的 17 种有 AST 级解析」这种限定说法是对的，不许误伤
    assert scan_text("上面列的 17 种有 AST 级语法解析；另外 6 种走规则级检测") == []
    # 「八号模块归属 E7」这类解释不是数量声明，不许误伤
    assert scan_text("8 号模块 engine.e7_deployment_readiness 归属 E7，不是第 8 个引擎") == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
