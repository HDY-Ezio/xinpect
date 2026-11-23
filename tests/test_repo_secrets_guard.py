#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""接线测试：守卫本身能判红，且它真的被挂进了推送路径与体检里。

守卫生效需要三件同时成立，缺一件就是假绿：
  1. 判据能判红（造坏自检跑通）——否则是空壳；
  2. pre-push 钩子装好了——否则没人执行它；
  3. QA 套件里有这条测试——否则钩子被删也没人发现。

历史里有已知旧账（8 个提交带 backups/），所以历史扫描必须能在
`scripts/repo_secrets_allowlist.json` 登记后通过；名单一旦指向不存在的
提交（历史已清理），守卫报退出码 2，本测试判红，逼人把名单删空。
"""
import os
import subprocess
import sys

import pytest

ROOT = os.environ.get("XINPECT_WEB_ROOT", "/opt/xinpect-website")
SCRIPTS = os.path.join(ROOT, "scripts")
GUARD = os.path.join(SCRIPTS, "verify_repo_secrets.py")

sys.path.insert(0, SCRIPTS)
import verify_repo_secrets as guard  # noqa: E402


def _run(*args):
    return subprocess.run([sys.executable, GUARD, "--root", ROOT] + list(args),
                          capture_output=True, text=True, timeout=300)


def test_guard_script_exists():
    assert os.path.isfile(GUARD), "守卫脚本不在：%s" % GUARD


def test_index_is_clean():
    """将要提交的内容里不许有明文 Key / 私钥 / 数据库转储。"""
    if not os.path.isdir(os.path.join(ROOT, ".git")):
        pytest.skip("不是 git 仓库：%s" % ROOT)
    findings, _ = guard.scan_index(ROOT)
    assert not findings, "索引里有敏感内容：\n" + "\n".join(
        "  %s  %s" % (f["path"], f["reason"]) for f in findings)


def test_history_passes_with_allowlist():
    """历史扫描必须能跑通：要么本来就干净，要么旧账都登记在册。"""
    if not os.path.isdir(os.path.join(ROOT, ".git")):
        pytest.skip("不是 git 仓库：%s" % ROOT)
    r = _run("--scope", "history")
    assert r.returncode == 0, (
        "历史扫描未通过（退出码 %s）。若是名单过期（历史已清理），"
        "删掉 scripts/repo_secrets_allowlist.json 里报出的条目即可。\n%s\n%s"
        % (r.returncode, r.stdout[-2000:], r.stderr[-1000:]))


def test_hook_installed():
    ok, why = guard.hook_installed(ROOT)
    assert ok, "pre-push 钩子没装好：%s（跑 python3 scripts/verify_repo_secrets.py --install-hook）" % why


def test_self_test_can_fail():
    """造坏自检：六条断言里只要有假绿就判红。"""
    r = _run("--self-test")
    assert r.returncode == 0, "守卫自检未通过：\n%s" % (r.stdout[-2000:] or r.stderr[-2000:])


def test_qa_suite_wired():
    """体检套件里必须跑这条测试，否则钩子被删也不会有人知道。"""
    p = os.path.join(ROOT, "scripts", "run_qa_suite.sh")
    with open(p, encoding="utf-8", errors="replace") as fh:
        body = fh.read()
    assert "test_repo_secrets_guard.py" in body, "run_qa_suite.sh 没挂这条测试"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
