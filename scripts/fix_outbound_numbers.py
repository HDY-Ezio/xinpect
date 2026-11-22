#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把对外数字统一成实测口径（8 个规则引擎 / 9,400+ 条规则 / 23 种语言）。

口径来源（2026-11-22 复核）：
  · engine/parallel_runner.BRAIN_MODULES = 1..8 + ai + poc  → 8 个规则引擎 + 两道智能验证
  · rules/*.json 唯一规则 ID 9,481 条                        → 对外写 9,400+
  · 语言数 23 = 平台覆盖的语言总数，跟 templates/help.html 里那份枚举一一对得上
    （Python、JavaScript、TypeScript、Java、Go、PHP、C、C++、C#、Ruby、Swift、
      Kotlin、Rust、Scala、Lua、Shell/Bash、SQL、T-SQL、PL/SQL、R、HTML、Dart、Ansible）
  · 17 只是 AST 语法解析那一层的覆盖数（engine/e1_syntax.registry.list_supported_langs，
    而且那次读数还漏了 Dart）。**拿窄口径当全站口径是条错路，2026-11-22 走过一次，
    被 tests/verify_site_consistency.py 的 S4 挡回来了**：对外只能有一个语言数。

改文案不改事实：以后引擎/规则/语言数变了，先改这三处事实，再改这份表。
"""
import io
import os
import re
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else "/opt/xinpect-website"

# 把「窄口径 / 旧口径」改成对外唯一口径。只动数量词 + 「种语言」，不碰别的 17。
LANG_RULES = [
    (re.compile(r"17(\s*)种(主流)?(编程)?语言"), r"23\1种\2\3语言"),
    (re.compile(r"23(\s*)种(主流)?(编程)?语言"), r"23\1种\2\3语言"),  # 已经对的保持不变
]

RULES = [
    ("7大规则引擎", "8 个规则引擎"),
    ("7 大规则引擎", "8 个规则引擎"),
    ("七大规则引擎", "八个规则引擎"),
    ("9,500+", "9,400+"),
    ("9,500 多", "9,400 多"),
    ("9,500多条", "9,400 多条"),
    ("7 大规则引擎（E1~E7）", "8 个规则引擎（E1~E8）"),
    ("七大规则引擎（E1~E7）", "八个规则引擎（E1~E8）"),
]

targets = []
for sub in ("templates", os.path.join("static", "pages")):
    d = os.path.join(ROOT, sub)
    if os.path.isdir(d):
        for fn in sorted(os.listdir(d)):
            p = os.path.join(d, fn)
            if os.path.isfile(p) and fn.endswith(".html"):
                targets.append(p)
for extra in (os.path.join("static", "llms.txt"),):
    p = os.path.join(ROOT, extra)
    if os.path.isfile(p):
        targets.append(p)

total = 0
for path in targets:
    try:
        s = io.open(path, encoding="utf-8").read()
    except Exception as e:
        print("SKIP", path, e)
        continue
    orig = s
    hits = []
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
