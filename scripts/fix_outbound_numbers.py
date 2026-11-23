#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把对外数字统一成实测口径（7 个规则引擎 / 9,400+ 条规则 / 23 种语言）。

口径来源（2026-11-23 复核，此前一天写成 8 是错的）：
  · 引擎数 7：engine/parallel_runner.BRAIN_MODULES 里模块路径 `engine.e<N>_xxx`
    的 eN 前缀去重 = 7。**槽位有 8 个不代表 8 个引擎**——8 号模块的路径是
    `engine.e7_deployment_readiness`，它归属 E7；「ai」「poc」是两道智能验证，不是规则引擎。
    design.md 里早写着这句：「运行时还有 8 号模块，它归属 E7，不是第 8 个引擎」。
    2026-11-22 有人（我）数了 BRAIN_MODULES 的键，把 7 改成 8，改错了一整天。
  · 规则数 9,481 条去重 → 对外 9,400+
  · 语言数 23 = AST/数据流级 17 + 规则级 6（T-SQL、PL/SQL、R、HTML 模板、Dart、Ansible），
    与 templates/help.html 里那份枚举一一对应。

改文案不改事实：以后引擎/规则/语言数变了，先改这三处事实，再改这份表。
用法：python3 scripts/fix_outbound_numbers.py [根目录]
"""
import io
import os
import re
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else "/opt/xinpect-website"

# 历史页面不回改：更新日志/版本档案里的数字是当时真实发生过的事。
HISTORY = re.compile(r"changelog|versions", re.I)

# 引擎总数：数量词（阿拉伯数字或中文数字）配「大/个」配「规则/无规则」的任意组合，
# 一律归一到 7。说法有几十种写法都无所谓，数字只有一个。
# 注意只在这里做归一，别把「E1-E5 这个档位」之类的子集声明卷进来——那种写法是
# 「E1-E5 规则引擎」，不带数量词，正则不会命中。
ENGINE_RULES = [
    (re.compile(r"(?:\d+|[六七八九十])\s*个\s*规则引擎"), "7 个规则引擎"),
    (re.compile(r"(?:\d+|[六七八九十])\s*个\s*引擎"), "7 个引擎"),
    (re.compile(r"[六七八九十]\s*个\s*规则引擎"), "七个规则引擎"),
    (re.compile(r"(?:\d+|[六七八九十])\s*大\s*规则引擎"), "7 大规则引擎"),
]

# 语言数：17 -> 23（17 是 AST 那一层的窄口径，不是全站口径）
LANG_RULES = [
    (re.compile(r"17(\s*)种(主流)?(编程)?语言"), "23\\1种\\2\\3语言"),
]

RULES = [
    ("9,500+", "9,400+"),
    ("9,500 多", "9,400 多"),
    ("9,500多条", "9,400 多条"),
    ("E1~E8", "E1~E7"),
    ("E1-E8", "E1-E7"),
]


def files(root):
    out = []
    for sub in ("templates", os.path.join("static", "pages")):
        d = os.path.join(root, sub)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            p = os.path.join(d, fn)
            if os.path.isfile(p) and fn.endswith(".html") and not HISTORY.search(fn):
                out.append(p)
    p = os.path.join(root, "static", "llms.txt")
    if os.path.isfile(p):
        out.append(p)
    return out


def main():
    total = 0
    for path in files(ROOT):
        s = io.open(path, encoding="utf-8").read()
        orig = s
        hits = []
        for rx, rep in ENGINE_RULES:
            s, n = rx.subn(rep, s)
            if n:
                hits.append("引擎数→%s×%d" % (rep, n))
                total += n
        for rx, rep in LANG_RULES:
            s, n = rx.subn(rep, s)
            if n:
                hits.append("语言数→23×%d" % n)
                total += n
        for a, b in RULES:
            c = s.count(a)
            if c:
                s = s.replace(a, b)
                hits.append("%s→%s×%d" % (a, b, c))
                total += c
        if s != orig:
            io.open(path, "w", encoding="utf-8").write(s)
            print("OK", os.path.relpath(path, ROOT), "|", "; ".join(hits))
    print("总替换:", total)


if __name__ == "__main__":
    main()
