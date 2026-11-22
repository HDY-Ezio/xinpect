#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把两页静态 HTML 的导航并进全站统一导航，并修正对外数字。

背景：/pages/product.html 与 /pages/about.html 是纯静态 HTML（不走 Jinja），
自带一套 .site-nav（浅色、8 项、没有 logo），和 base.html 的深蓝导航、首页的
.nav 各是一套 —— 客户说的「三个页面三种样式」里就包括它俩。

静态页没法 include _nav.html，所以这里生成同一份结构写进去：
结构、类名、项数必须与 _nav.html 完全一致，改导航时这份脚本要跟着改，
并用 test_nav_single_source.py 卡住「项数不一致」。
"""
import io
import json
import os
import re
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else "/opt/xinpect-website"

def load_items():
    """导航项从 scripts/site_nav.json 读 —— 与 templates/_nav.html 同源。

    原来这里手写了一串 ITEMS，和 _nav.html、和 site_nav.json 三份并存，
    正好复刻「三页三样式」的老毛病。现在只认 JSON。
    """
    path = os.path.join(ROOT, "scripts", "site_nav.json")
    with io.open(path, encoding="utf-8") as f:
        return [(it["href"], it["label"]) for it in json.load(f)["core"]]

NUMBER_FIX = [
    ("7 大规则引擎", "8 个规则引擎"),
    ("7大规则引擎", "8 个规则引擎"),
    ("七大规则引擎", "八个规则引擎"),
    ("9,500+", "9,400+"),
    ("支持23种", "支持17种"),
    ("23 种主流", "17 种主流"),
    ("23种主流", "17种主流"),
    ("23 种语言", "17 种语言"),
    ("23种语言", "17 种语言"),
]


def render_nav(items, active):
    links = []
    for href, label in items:
        cls = ' class="active"' if href == active else ""
        links.append('      <a href="%s"%s>%s</a>' % (href, cls, label))
    return (
        '<header class="xp-nav">\n'
        '  <div class="xp-nav-inner">\n'
        '    <a class="xp-nav-brand" href="/" aria-label="煋鉴首页">\n'
        '      <img src="/static/xinpect-mark-wide-128.png" alt="煋鉴">\n'
        '      <span>煋鉴</span>\n'
        '    </a>\n'
        '    <nav class="xp-nav-links" aria-label="主导航">\n'
        + "\n".join(links) + "\n"
        '    </nav>\n'
        '    <div class="xp-nav-actions">\n'
        '      <a class="xp-nav-ghost" href="/login">登录</a>\n'
        '      <a class="xp-nav-solid" href="/register">免费注册</a>\n'
        '    </div>\n'
        '  </div>\n'
        '</header>'
    )


def patch(rel, active):
    path = ROOT + "/" + rel
    s = io.open(path, encoding="utf-8").read()
    orig = s

    # 1) 引共享导航样式
    if "/static/css/nav.css" not in s:
        anchor = re.search(r'<link rel="stylesheet" href="/static/css/cool-fx\.css[^"]*">', s)
        if anchor:
            s = s[:anchor.end()] + '\n<link rel="stylesheet" href="/static/css/nav.css?v=20261122">' + s[anchor.end():]

    # 2) 换导航
    items = load_items()
    m = re.search(r'<nav class="site-nav">.*?</nav>', s, re.S) or \
        re.search(r'<header class="xp-nav">.*?</header>', s, re.S)
    if m:
        s = s[:m.start()] + render_nav(items, active) + s[m.end():]
        print("  %s: 导航已按 site_nav.json 重建" % rel)
    else:
        print("  %s: 没找到导航块，跳过" % rel)

    # 3) 数字口径
    n = 0
    for a, b in NUMBER_FIX:
        c = s.count(a)
        if c:
            s = s.replace(a, b)
            n += c
    if n:
        print("  %s: 数字修正 %d 处" % (rel, n))

    if s != orig:
        io.open(path, "w", encoding="utf-8").write(s)
        return True
    return False


patch("static/pages/product.html", "/pages/product.html")
patch("static/pages/about.html", "/pages/about.html")
print("完成")
