#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""仓库里不许出现数据库/备份类文件（NOTICE: 公开仓库曾泄漏 10 个生产库备份）

起因（2026-11-23 发现）：`backups/database/*.db.gz` 从 10-20 那次提交起就在公开仓库里，
任何人可匿名下载；里面有 14 个用户邮箱、753 条扫描记录、2 个明文 API key。
根因不是「忘了删」，是 `.gitignore` 只写了 `*.db`，而这些文件叫 `*.db.gz`——
一条粒度不够的忽略规则，让 5 天的每日备份顺着 `git add .` 全进了仓库。

所以判据落在两处：
  1. 仓库里现在不许有（历史清理是另一件事，见 filter-repo 记录）；
  2. 新的同类文件必须被忽略规则挡住——否则下次再来一遍。

判据只写「禁止什么」，不写「必须包含什么」：以后备份改叫别的名字、换个目录，
只要不是数据库转储就不该判红。

运行：python3 -m pytest tests/test_no_db_dumps_tracked.py -q
"""
import os
import re
import subprocess
import sys

import pytest

ROOT = os.environ.get("XINPECT_WEB_ROOT", "/opt/xinpect-website")

# 数据库转储 / 备份校验文件：全路径匹配
FORBIDDEN = [
    (re.compile(r"(^|/)backups/"), "备份目录整个不许进仓库"),
    (re.compile(r"\.db$", re.I), "SQLite 库文件"),
    (re.compile(r"\.db\.gz$", re.I), "gzip 过的 SQLite 库文件"),
    (re.compile(r"\.sqlite3?$", re.I), "SQLite 库文件"),
    (re.compile(r"\.dump$", re.I), "数据库转储"),
    (re.compile(r"\.md5$", re.I), "备份校验文件"),
]

# 这些路径带 .sql 之类但是源码/文档，不许误伤
ALLOW = re.compile(r"(schema|migration|\.sql$)", re.I)


def scan(paths):
    """返回 [(路径, 原因)]。纯函数，测试和造坏自检共用同一个判据。"""
    hits = []
    for p in paths:
        if ALLOW.search(p) and not re.search(r"(^|/)backups/", p):
            continue
        for rx, why in FORBIDDEN:
            if rx.search(p):
                hits.append((p, why))
                break
    return hits


def tracked_files(root):
    out = subprocess.run(
        ["git", "-C", root, "-c", "safe.directory=*", "ls-files"],
        capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        return None
    return [l for l in out.stdout.splitlines() if l.strip()]


def test_no_dump_files_tracked():
    files = tracked_files(ROOT)
    if files is None:
        pytest.skip("拿不到 git 文件清单（不是仓库或 git 不可用）：%s" % ROOT)
    hits = scan(files)
    assert not hits, "仓库里跟踪了数据库/备份文件：\n" + "\n".join(
        "  %s —— %s" % (p, why) for p, why in hits)


def test_gitignore_blocks_new_dumps():
    """忽略规则必须挡得住同类文件，否则下次备份又会顺着 git add . 进来。"""
    if not os.path.isdir(os.path.join(ROOT, ".git")):
        pytest.skip("不是 git 仓库：%s" % ROOT)
    samples = [
        "backups/database/xinpect_backup_20991231_030001.db.gz",
        "backups/database/xinpect_backup_20991231_030001.md5",
        "xinpect.db",
        "data/app.sqlite3",
        "export/full.dump",
        "some/where/check.md5",
    ]
    missed = []
    for s in samples:
        r = subprocess.run(
            ["git", "-C", ROOT, "-c", "safe.directory=*", "check-ignore", "-q", s],
            capture_output=True, timeout=30)
        if r.returncode != 0:
            missed.append(s)
    assert not missed, "这些路径没被 .gitignore 挡住：\n" + "\n".join("  " + m for m in missed)


def test_detector_can_fail():
    """造坏自检：真放一个备份进去，必须报出来。"""
    bad = [
        "backups/database/xinpect_backup_20261020_030001.db.gz",
        "backups/database/xinpect_backup_20261020_030001.md5",
        "static/other.db",
        "tmp/thing.sqlite",
    ]
    hits = scan(bad)
    assert len(hits) == len(bad), "造坏样本应全部命中，实际 %d/%d：%s" % (
        len(hits), len(bad), hits)


def test_detector_not_overzealous():
    """阴性对照：正常源码不能被误判，否则守卫会逼人改文件名。"""
    good = [
        "app.py",
        "modules/api.py",
        "templates/index.html",
        "docs/schema.sql",
        "db/migrations/0001_init.sql",
        "tests/test_offsite_backup.py",
    ]
    assert scan(good) == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
