#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对外数字口径守卫（2026-11-22，客户评审录屏后补；同日二次修订）

治的是什么：官网三个数字互相打架，且都比事实大：
  · 引擎：engine/parallel_runner.BRAIN_MODULES = 1..8 + ai + poc → 8 个规则引擎 + 两道验证
  · 规则：rules/*.json 去重后 9,481 条 → 对外写 9,400+
  · 语言：对外 23 种 = 数据流/AST 级 17 种 + 规则级 6 种（T-SQL、PL/SQL、R、
    HTML 模板、Dart、Ansible），跟 templates/help.html 里那份枚举一一对得上。

⚠ 语言数这一条当天被改错过一次：有人拿 e1_syntax.registry.list_supported_langs
的读数（17，而且还漏了 Dart）当成「全站语言数」，把 23 全改成了 17。
**17 是 AST 那一层的窄口径，不是平台覆盖总数。** 判据放在这里就是防第二次：
对外只认 23，出现「17 种语言」这种把窄口径当总数的说法必须判红。

判据只写「禁止什么」，不写「必须包含什么」——文案换说法不该判红，
但把窄口径 / 旧的大数字写回去必须判红。

为什么不写死新句子：写死「必须出现 8 个规则引擎」会把某一版文案固化成规矩，
下次正常改文案就假红（历史上真发生过）。

运行：python3 -m pytest tests/test_outbound_numbers.py -q
"""
import os
import re
import sys

import pytest

ROOT = os.environ.get("XINPECT_WEB_ROOT", "/opt/xinpect-website")

# 禁止出现的旧/窄口径。每条都必须是「数字 + 名词」的完整说法，
# 不能只写数字——不然日期、行号、别的统计都会误伤。
FORBIDDEN = [
    (r"17\s*种\s*(?:主流)?(?:编程)?语言",
     "语言数写成 17 种（那是 AST 解析层的窄口径，对外总数是 23 = 17 AST + 6 规则级）"),
    (r"七大规则引擎|7\s*大规则引擎|7\s*个规则引擎",
     "引擎数写成 7 个（实测 8 个规则引擎 + AI + PoC）"),
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
    """返回命中的 [(说明, 命中原样)]。单一判据入口，测试与造坏自检共用。"""
    hits = []
    for pat, why in FORBIDDEN:
        for m in re.finditer(pat, text):
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
    """全站模板与 llms.txt 不得再出现窄口径 / 旧的大数字。"""
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


def test_detector_can_fail(tmp_path):
    """造坏自检：故意写回窄口径/旧口径，判据必须报出来。

    只让「没命中」等于绿是不够的——判据本身写错（比如正则拼错）也会一直绿。
    这里先证明它会红，再谈上面的绿有意义。
    """
    bad_text = "支持 17 种语言，七大规则引擎，9,500+ 条规则"
    hits = scan_text(bad_text)
    assert len(hits) == 3, "造坏样本应命中 3 类，实际 %d 类：%s" % (len(hits), hits)


def test_clean_text_passes():
    """阴性对照：现在的正确说法不能被误判。"""
    good = "8 个规则引擎 + AI 语义 + PoC 验证，9,400+ 条检测规则，23 种语言"
    assert scan_text(good) == []
    # 「上面列的 17 种有 AST 级解析」这种限定说法是对的，不许误伤
    assert scan_text("上面列的 17 种有 AST 级语法解析；另外 6 种走规则级检测") == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
