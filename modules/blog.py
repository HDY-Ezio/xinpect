# -*- coding: utf-8 -*-
"""
煋鉴博客内容系统
================
设计原则（治本，不打补丁）：
    加一篇文章 = 往 content/blog/ 丢一个 .md 文件。不改任何代码。
    列表页 / 详情页 / sitemap 全部自动包含。

front matter 格式（不用 yaml 依赖，手写解析）：

    ---
    title: 误报率 1.7% 是怎么测出来的
    slug: how-we-measured-false-positive-rate
    date: 2026-11-03
    summary: 一句话摘要，同时用于列表页和 meta description
    tags: 实测数据, 方法学
    keywords: 误报率, 代码扫描
    draft: false
    ---
    正文 Markdown

作者字段默认「煋鉴团队」。
"""

import os
import re
import glob
from datetime import datetime

import markdown as _md

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLOG_DIR = os.path.join(BASE_DIR, "content", "blog")
SITE = "https://xinpect.xingwangzhineng.com"
DEFAULT_AUTHOR = "煋鉴团队"

_MD_EXTS = ["fenced_code", "tables", "sane_lists", "toc"]
_MD_CFG = {"toc": {"permalink": False, "toc_depth": "2-3"}}

# path -> (mtime, post_dict)
_cache = {}


def _parse_front_matter(text):
    """切分 front matter 与正文，返回 (dict, body)。"""
    if not text.startswith("---"):
        return {}, text
    m = re.match(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?(.*)$", text, re.S)
    if not m:
        return {}, text
    head, body = m.group(1), m.group(2)
    meta = {}
    for line in head.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, val = line.split(":", 1)
        key = key.strip().lower()
        val = val.strip().strip('"').strip("'")
        if key == "tags":
            meta[key] = [t.strip() for t in re.split(r"[,，]", val) if t.strip()]
        elif key == "draft":
            meta[key] = val.lower() in ("true", "1", "yes")
        else:
            meta[key] = val
    return meta, body


def _slug_from_path(path):
    """从文件名提取 slug：2026-11-03-xxx.md -> xxx"""
    name = os.path.splitext(os.path.basename(path))[0]
    return re.sub(r"^\d{4}-\d{2}-\d{2}[-_]", "", name)


def _read_minutes(words):
    """中文阅读速度按 400 字/分钟，最少 1 分钟。"""
    return max(1, int(round(words / 400.0)))


def _cn_date(date_str):
    """2026-11-03 -> 2026 年 11 月 3 日"""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return "%d 年 %d 月 %d 日" % (d.year, d.month, d.day)
    except Exception:
        return date_str


def _load_one(path):
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None

    cached = _cache.get(path)
    if cached and cached[0] == mtime:
        return cached[1]

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
    except OSError:
        return None

    meta, body = _parse_front_matter(raw)
    if meta.get("draft") is True:
        return None

    slug = meta.get("slug") or _slug_from_path(path)
    date = meta.get("date") or datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")

    md = _md.Markdown(extensions=_MD_EXTS, extension_configs=_MD_CFG)
    body_html = md.convert(body)
    toc_html = getattr(md, "toc", "") or ""

    words = len(re.sub(r"\s", "", body))
    summary = meta.get("summary") or ""
    if not summary:
        plain = re.sub(r"[#*`>|\-\[\]()]", "", body).strip().replace("\n", " ")
        summary = plain[:120] + ("…" if len(plain) > 120 else "")

    post = {
        "slug": slug,
        "title": meta.get("title") or slug,
        "date": date,
        "date_cn": _cn_date(date),
        "summary": summary,
        "tags": meta.get("tags") or [],
        "keywords": meta.get("keywords") or "",
        "author": meta.get("author") or DEFAULT_AUTHOR,
        "html": body_html,
        "toc": toc_html,
        "words": words,
        "read_min": _read_minutes(words),
        "url": "%s/blog/%s" % (SITE, slug),
        "path": "/blog/%s" % slug,
    }
    _cache[path] = (mtime, post)
    return post


def load_all(include_draft=False):
    """按日期倒序返回全部已发布文章。"""
    posts = []
    for path in glob.glob(os.path.join(BLOG_DIR, "*.md")):
        p = _load_one(path)
        if p:
            posts.append(p)
    posts.sort(key=lambda x: (x["date"], x["slug"]), reverse=True)
    return posts


def get(slug):
    """按 slug 取单篇，找不到返回 None。"""
    for p in load_all():
        if p["slug"] == slug:
            return p
    return None


def latest(n=5):
    return load_all()[:n]


def all_tags():
    counter = {}
    for p in load_all():
        for t in p["tags"]:
            counter[t] = counter.get(t, 0) + 1
    return sorted(counter.items(), key=lambda x: (-x[1], x[0]))


def related(slug, n=3):
    """同标签优先，其次按日期近的补足。"""
    posts = [p for p in load_all() if p["slug"] != slug]
    me = get(slug)
    my_tags = set(me["tags"]) if me else set()
    # 一次排序：标签重叠数降序 → 日期降序
    posts.sort(key=lambda p: (len(my_tags & set(p["tags"])), p["date"]), reverse=True)
    return posts[:n]


def slug_is_offline(slug):
    """这个 slug 是不是「发布过、后来下线」的文章（文件还在，只是标了 draft: true）。

    为什么要区分：下线文章直接返回 404，搜索引擎和收藏过的人都会撞空页。
    知道它曾经存在，就 301 回博客首页——比 404 体面，也不会把权重全丢掉。
    """
    for path in glob.glob(os.path.join(BLOG_DIR, "*.md")):
        meta, _body = _parse_front_matter(_read_head(path))
        if (meta.get("slug") or _slug_from_path(path)) == slug and meta.get("draft") is True:
            return True
    return False


def _read_head(path, limit=4096):
    """只读文件头：判 draft 不需要整篇正文。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read(limit)
    except OSError:
        return ""
