# -*- coding: utf-8 -*-
"""体检脚本的测试清单必须覆盖所有测试文件。

为什么要有这条（2026-11-23）：
  45 份测试里有 10 份没写进 scripts/run_qa_suite.sh，包括「对外数字口径」
  和当天新加的「风格类不打分」「裸 8 归并」。于是每轮 QA 都报
  「✅ 套件通过 pytest=0」，看着全绿，实际漏跑了一整批。
  这不是「跑挂了」，是「没跑」——比跑挂更危险，因为没人会去看日志。

三条判据：
  1. 每个 tests/test_*.py 都要出现在 pytest 分支的清单里（或登记豁免理由）；
  2. 「无 pytest」分支的清单必须是它的子集；
  3. 只在 pytest 分支里的文件，必须真的 import pytest —— 不依赖 pytest 的
     文件没理由在没装 pytest 的机器上被跳过。
"""
import os
import re
import sys

import pytest

ROOT = os.environ.get("XINPECT_WEB_ROOT", "/opt/xinpect-website")
SCRIPT = os.path.join(ROOT, "scripts", "run_qa_suite.sh")
TESTS_DIR = os.path.join(ROOT, "tests")

# 不能进体检的测试，必须写清原因。这里每加一条，就是承认它长期不被自动跑。
EXEMPT = {
    "test_api_integration.py": "要真实 scanner(8620) 与 API token，属于环境冒烟；"
                               "体检环境里必红（实测 28 红），放在发布前手工跑",
}


def list_test_files(tests_dir=TESTS_DIR):
    if not os.path.isdir(tests_dir):
        return []
    return sorted(f for f in os.listdir(tests_dir)
                  if f.startswith("test_") and f.endswith(".py"))


def parse_lists(script_text):
    """从体检脚本里读出两套清单：不带 tests/ 前缀的（无 pytest 分支）
    和带前缀的（pytest 分支）。"""
    bare, prefixed = set(), set()
    for ln in script_text.split("\n"):
        s = ln.strip()
        m = re.match(r"^(?:tests/)?(test_[a-z_0-9]+\.py)\s*\\?$", s)
        if not m:
            continue
        (prefixed if s.startswith("tests/") else bare).add(m.group(1))
    return bare, prefixed


def unmounted(files, mounted, exempt=None):
    exempt = EXEMPT if exempt is None else exempt
    return [f for f in files if f not in exempt and f not in mounted]


def test_script_is_readable_and_non_trivial():
    """先证明自己读的是真的体检脚本，否则后面「全都挂上了」毫无意义。"""
    assert os.path.isfile(SCRIPT), "找不到体检脚本：%s" % SCRIPT
    text = open(SCRIPT, encoding="utf-8").read()
    bare, prefixed = parse_lists(text)
    assert len(prefixed) >= 30 and len(bare) >= 20, (
        "清单解析结果太少（pytest 分支 %d、无 pytest 分支 %d），"
        "脚本被换过或格式变了？" % (len(prefixed), len(bare)))


def test_every_test_file_is_mounted_or_exempted():
    bare, prefixed = parse_lists(open(SCRIPT, encoding="utf-8").read())
    files = list_test_files()
    assert files, "tests 目录下一个测试都没找到：%s" % TESTS_DIR
    missing = unmounted(files, prefixed)
    assert not missing, (
        "这些测试没挂进体检（pytest 分支）、也没登记豁免理由，等于从来没被自动跑过：\n  "
        + "\n  ".join(missing)
        + "\n（加进 scripts/run_qa_suite.sh 的两个清单，或写进本文件 EXEMPT 并说明原因）")


def test_bare_list_is_subset_of_full_list():
    bare, prefixed = parse_lists(open(SCRIPT, encoding="utf-8").read())
    extra = sorted(bare - prefixed)
    assert not extra, "只在「无 pytest」分支里出现，pytest 分支反而没跑：%s" % extra


def test_files_skipped_without_pytest_really_need_pytest():
    """不在「无 pytest」清单里的文件，必须真的 import pytest。

    否则就是「这台机器没装 pytest，所以这个守卫被静默跳过」——干净的假绿。
    """
    bare, prefixed = parse_lists(open(SCRIPT, encoding="utf-8").read())
    bad = []
    for name in sorted(prefixed - bare):
        path = os.path.join(TESTS_DIR, name)
        if not os.path.isfile(path):
            continue
        src = open(path, encoding="utf-8").read()
        if not re.search(r"^\s*import pytest", src, re.M):
            bad.append(name)
    assert not bad, (
        "这些文件不依赖 pytest，却没进「无 pytest」分支——"
        "在没装 pytest 的机器上会被静默跳过：%s" % bad)


def test_guard_can_fail():
    """造假一个没挂载的文件，漏挂判据必须把它抓出来。"""
    got = unmounted(["test_mounted.py", "test_nobody_mounted_me.py"],
                    {"test_mounted.py"}, exempt={})
    assert got == ["test_nobody_mounted_me.py"], "漏挂判据失效：%r" % got
    # 豁免表要真的能免掉，否则 EXEMPT 就成了摆设
    assert unmounted(["test_x.py"], set(), exempt={"test_x.py": "理由"}) == []
    # 清单解析要能分开两套：带前缀的进 pytest 分支，不带的进无 pytest 分支
    bare, prefixed = parse_lists("  test_a.py \\\n  tests/test_b.py \\\n")
    assert bare == {"test_a.py"} and prefixed == {"test_b.py"}, (bare, prefixed)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
