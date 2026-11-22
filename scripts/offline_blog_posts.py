#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把重复度最高的几篇博客下线（draft: true），文件保留不删。

为什么这么干（2026-11-22，客户评审录屏原话）：
  「你代码只审查越权吗」「博客是技术文档，有很高的专业性……你还不如把博客给删了」
11 篇里有 8 篇标题带越权，读者翻两屏就得出「这家只会一招」的结论。
下线不是删——文件仍在 content/blog/，改回 draft: false 就恢复；
文章 URL 由 app.py 301 回博客首页，不留 404。

判据：同一话题保留原理篇 + 数据篇 + 写法篇各一，其余下线。
以后加文章别再往同一话题堆。
"""
import io
import os
import re
import sys

BLOG_DIR = sys.argv[1] if len(sys.argv) > 1 else "/opt/xinpect-website/content/blog"

OFFLINE_SLUGS = [
    "sonarqube-what-it-catches-and-misses",   # 竞品对比，论据被 08/09 覆盖
    "why-no-incident-is-not-evidence",        # 同话题第三篇
    "shift-left-where-to-move",               # 同话题第四篇
    "outsource-code-acceptance-checklist",    # 同话题第五篇
    "missing-authorization-ai-generated-code",# 案例篇，结论与 20 写法篇重复
]


def set_draft(path, flag=True):
    text = io.open(path, encoding="utf-8").read()
    if not text.startswith("---"):
        return "跳过（无 front matter）"
    m = re.match(r"^---[ \t]*\r?\n(.*?)\r?\n---", text, re.S)
    if not m:
        return "跳过（front matter 不完整）"
    head = m.group(1)
    body_part = text[m.end():]
    lines = [l for l in head.splitlines() if not l.strip().lower().startswith("draft:")]
    if flag:
        lines.append("draft: true")
    new = "---\n" + "\n".join(lines) + "\n---" + body_part
    if new == text:
        return "无变化"
    io.open(path, "w", encoding="utf-8").write(new)
    return "已标记 draft: true" if flag else "已恢复发布"


for fn in sorted(os.listdir(BLOG_DIR)):
    if not fn.endswith(".md"):
        continue
    path = os.path.join(BLOG_DIR, fn)
    meta_head = io.open(path, encoding="utf-8").read(2000)
    ms = re.search(r"^slug:\s*(\S+)", meta_head, re.M)
    slug = ms.group(1) if ms else re.sub(r"^\d{4}-\d{2}-\d{2}-", "", fn[:-3])
    if slug in OFFLINE_SLUGS:
        print("%-46s %s" % (fn, set_draft(path, True)))
