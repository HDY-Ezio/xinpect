#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导航单一事实来源守卫（2026-11-22）

治的是什么：站里曾经同时有三套导航 —— 首页 .nav、base.html .navbar、
静态页 .site-nav，导航项也各写各的。客户从首页点进定价页，导航项从 9 个变 11 个，
「能力 / 语言」两个定位点消失，原话是「我到底点的是哪个」。

现在只有一条链：
  scripts/site_nav.json  →  templates/_nav.html（app.py 注入 nav_core，按 JSON 渲染）
                          →  static/pages/*.html（scripts/patch_static_nav.py 按 JSON 生成）

判据（只判禁止项与一致性，不锁具体文案）：
  1. 不得再出现旧导航的类名（.navbar / .site-nav 的 nav 元素）。
  2. _nav.html 必须按 nav_core 渲染 —— 不许把导航项又写死一份进去。
  3. 静态页导航项数量必须等于 JSON 的 core 条数。
  4. 导航里的锚点必须是绝对路径（/#features），不许裸 #features。

运行：python3 -m pytest tests/test_nav_single_source.py -q
"""
import json
import os
import re

import pytest

ROOT = os.environ.get("XINPECT_WEB_ROOT", "/opt/xinpect-website")

OLD_NAV = re.compile(r'<nav[^>]*class="[^"]*(?:\bnavbar\b|\bsite-nav\b)[^"]*"')
BARE_ANCHOR = re.compile(r'href="#[a-zA-Z]')


def _read(rel):
    return open(os.path.join(ROOT, rel), encoding="utf-8").read()


def _core():
    return json.loads(_read("scripts/site_nav.json"))["core"]


def _static_nav_items(html):
    """静态页导航容器里的链接数；找不到容器返回 -1（让断言喊出来）。"""
    m = re.search(r'<nav[^>]*xp-nav-links[^>]*>(.*?)</nav>', html, re.S)
    if not m:
        return -1
    return len(re.findall(r"<a\s+href=", m.group(1)))


def test_no_legacy_nav_markup():
    bad = []
    for sub in ("templates", "static/pages"):
        d = os.path.join(ROOT, sub)
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if not fn.endswith(".html"):
                continue
            p = os.path.join(d, fn)
            try:
                text = open(p, encoding="utf-8").read()
            except OSError:
                continue
            if OLD_NAV.search(text):
                bad.append(os.path.relpath(p, ROOT))
    assert not bad, "旧导航又出现了（应改用 templates/_nav.html）：%s" % bad


def test_partial_renders_from_json():
    """_nav.html 必须是「按清单渲染」，不能把导航项又写死一份。"""
    partial = _read("templates/_nav.html")
    assert "nav_core" in partial, "_nav.html 不再按 nav_core 渲染，导航项又被写死了"
    assert len(_core()) > 0, "site_nav.json 的 core 是空的"


def test_static_pages_match_core_count():
    n_core = len(_core())
    for rel in ("static/pages/product.html", "static/pages/about.html"):
        p = os.path.join(ROOT, rel)
        if not os.path.isfile(p):
            continue
        n = _static_nav_items(_read(rel))
        assert n == n_core, "%s 导航项 %d 个，site_nav.json 是 %d 个 —— 两份又分叉了" % (rel, n, n_core)


def test_anchors_are_absolute():
    bad = [it["href"] for it in _core() if it["href"].startswith("#")]
    assert not bad, "清单里有裸锚点（只在首页有效）：%s" % bad
    for rel in ("static/pages/product.html", "static/pages/about.html"):
        p = os.path.join(ROOT, rel)
        if not os.path.isfile(p):
            continue
        m = re.search(r'<nav[^>]*xp-nav-links[^>]*>(.*?)</nav>', _read(rel), re.S)
        if m and BARE_ANCHOR.search(m.group(1)):
            raise AssertionError("%s 导航里有裸锚点" % rel)


def test_detector_can_fail():
    """造坏自检：旧导航类名、裸锚点必须被抓到；正常写法不能误判。"""
    assert OLD_NAV.search('<nav class="navbar">'), "旧导航判据失效"
    assert OLD_NAV.search('<nav class="site-nav">'), "旧导航判据失效"
    assert BARE_ANCHOR.search('href="#features"'), "裸锚点判据失效"
    assert not BARE_ANCHOR.search('href="/#features"'), "绝对锚点被误判"
