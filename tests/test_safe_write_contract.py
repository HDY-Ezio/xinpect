#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""safe_write 落盘契约测试（2026-11-03 交接整改配套）

钉住三件事，任何一条破坏都说明监控会重新变成"假活着"：
  1. 原子写：产出的 JSON 一定能被解析，且不留临时文件
  2. 失败降级：目标不可写时返回 False，绝不抛异常中断监控
  3. 属主继承：root 覆写既有文件后属主不变（否则 xinpect-web 的读取方直接读不到）

服务器没装 pytest，所以本文件同时支持两种跑法：
    python3 tests/test_safe_write_contract.py            # 直接跑，打印 PASS/FAIL
    python3 -m pytest tests/test_safe_write_contract.py  # 装了 pytest 时也可
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, "/opt/xinpect-website")
from monitoring.safe_write import write_json  # noqa: E402


def test_atomic_write_valid_json_no_residue():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "state.json")
    assert write_json(p, {"k": "值", "n": 1}, perm=0o600) is True
    assert json.load(open(p, encoding="utf-8")) == {"k": "值", "n": 1}
    assert oct(os.stat(p).st_mode & 0o777) == "0o600"
    assert [f for f in os.listdir(d) if f.startswith(".tmp_")] == []


def test_degrade_on_unwritable_target():
    """父路径是普通文件 -> ENOTDIR，任何身份都会失败，可跨用户验证降级。"""
    d = tempfile.mkdtemp()
    blocker = os.path.join(d, "blocker")
    open(blocker, "w").close()
    bad = os.path.join(blocker, "state.json")  # 不可能创建
    assert write_json(bad, {"a": 1}, label="契约测试") is False


def test_ownership_inherited():
    if os.geteuid() != 0:
        print("SKIP 属主继承（仅 root 身份可验证）")
        return
    d = tempfile.mkdtemp()
    p = os.path.join(d, "state.json")
    write_json(p, {"v": 1})
    os.chown(p, 1000, 1000)  # 造一个"别人家的文件"
    before = os.stat(p)
    assert write_json(p, {"v": 2}) is True
    after = os.stat(p)
    assert (after.st_uid, after.st_gid) == (before.st_uid, before.st_gid)
    assert json.load(open(p, encoding="utf-8")) == {"v": 2}


if __name__ == "__main__":
    fails = 0
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in tests:
        try:
            fn()
            print("PASS %s" % fn.__name__)
        except Exception as e:
            fails += 1
            print("FAIL %s -> %r" % (fn.__name__, e))
    print("结果: %d/%d 通过" % (len(tests) - fails, len(tests)))
    sys.exit(1 if fails else 0)
