#!/usr/bin/env python3
"""守卫：节能阀逃生门必须「全部可判定」，且兜底链路真的能跑。

判据（任一不满足即 raise AssertionError，绝不用只记录不抛的假通过）：
  1. 台账模块可导入、生产 router 里导入恰好一处
  2. 所有 `_call_direct` / `_stream_call_direct` 调用只能出现在两个包装函数内
  3. 两个包装函数都必须登记台账
  4. `_call_direct` 不得引用未定义的 `use_opt`（否则兜底必崩）
  5. 真跑：临时台账写入 → 读回字段/汇总计数正确
  6. 造坏：删掉登记 / 加一处裸直连，守卫必须判红（证明不是摆设）
  7. 生产不得再用网关默认开发密钥
  8. 生产台账目录可写；守卫绝不创建 root 属主的生产台账文件
"""
import ast
import importlib.util
import json
import os
import shutil
import sys
import tempfile

BASE = "/opt/starwang/backend_clean"
ROUTER = os.path.join(BASE, "model_router.py")
LEDGER_MOD = os.path.join(BASE, "gateway_bypass_ledger.py")
ENV = os.path.join(BASE, ".env")
DIRECT = {"_call_direct", "_stream_call_direct"}
WRAPPERS = {"_fallback_sync", "_fallback_stream"}

passed = 0


def ok(name, fn):
    global passed
    fn()
    passed += 1
    print(f"  ✅ {name}")


def static_checks(path):
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    seen = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
                        and sub.func.id in DIRECT):
                    seen.append((node.name, sub.func.id))
    stray = [x for x in seen if x[0] not in WRAPPERS]
    assert not stray, f"存在绕过逃生门的直连调用: {stray}"
    assert len(seen) == 2, f"逃生门内直连调用应恰好 2 处，实际 {seen}"

    fnmap = {n.name: n for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    for w in WRAPPERS:
        assert w in fnmap, f"缺包装函数 {w}"
        calls = [s.func.id for s in ast.walk(fnmap[w])
                 if isinstance(s, ast.Call) and isinstance(s.func, ast.Name)]
        assert "_record_bypass" in calls, f"{w} 没有登记台账"

    cd = fnmap.get("_call_direct")
    assert cd is not None, "缺 _call_direct"
    names = [n.id for n in ast.walk(cd) if isinstance(n, ast.Name)]
    assert "use_opt" not in names, "_call_direct 仍引用未定义的 use_opt"

    imp = [n for n in ast.walk(tree)
           if isinstance(n, ast.ImportFrom) and n.module == "gateway_bypass_ledger"]
    assert len(imp) == 1, "台账导入应恰好一处"


def load_ledger(path):
    spec = importlib.util.spec_from_file_location("gbl_guard", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def c_files():
    assert os.path.isfile(ROUTER), f"缺 {ROUTER}"
    assert os.path.isfile(LEDGER_MOD), f"缺 {LEDGER_MOD}"
    assert os.path.isfile(ENV), f"缺 {ENV}"


def c_static():
    static_checks(ROUTER)


def c_ledger_runtime():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "bypass.jsonl")
        os.environ["GATEWAY_BYPASS_LEDGER"] = p
        mod = load_ledger(LEDGER_MOD)
        assert mod.LEDGER_PATH == p, "环境变量未生效"
        e = mod.record_bypass(model="deepseek", reason="http_error",
                              upstream="https://ark.cn-beijing.volces.com/api/v3",
                              stream=False, detail="guard")
        assert e and e["model"] == "deepseek" and e["reason"] == "http_error"
        assert e["stream"] is False and e["pid"] == os.getpid()
        e2 = mod.record_bypass(model="deepseek", reason="stream_error",
                               upstream="u", stream=True)
        assert e2 and e2["stream"] is True
        rows = mod.read_entries()
        assert len(rows) == 2, f"应读到 2 行，实际 {len(rows)}"
        s = mod.summary()
        assert s["count"] == 2 and s["by_reason"]["http_error"] == 1
        assert s["by_stream"] == {"stream": 1, "sync": 1}
        s2 = mod.summary(since_epoch=e2["epoch"])
        assert s2["count"] == 1, "since_epoch 过滤失效"
        # 并发写入不撕裂：8 线程各写 20 行，全部可解析
        import threading
        def writer(i):
            for j in range(20):
                mod.record_bypass(model="m", reason=f"r{i}", upstream="u")
        ts = [threading.Thread(target=writer, args=(i,)) for i in range(8)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        assert len(mod.read_entries()) == 162, "并发追加出现丢行/撕裂"
        os.environ.pop("GATEWAY_BYPASS_LEDGER", None)


def c_broken_copies():
    src = open(ROUTER, encoding="utf-8").read()
    with tempfile.TemporaryDirectory() as d:
        # 造坏 1：删掉同步包装函数的登记
        b1 = os.path.join(d, "no_record.py")
        open(b1, "w", encoding="utf-8").write(
            src.replace("    _record_bypass(model=model_name, reason=reason,\n"
                        "                   upstream=config.get(\"base_url\", \"\"), stream=False)\n", ""))
        try:
            static_checks(b1)
        except AssertionError:
            pass
        else:
            raise AssertionError("删掉台账登记后守卫仍判绿 = 假通过")
        # 造坏 2：在别处插一个裸直连
        b2 = os.path.join(d, "stray_direct.py")
        open(b2, "w", encoding="utf-8").write(
            src + "\n\ndef _stray():\n    return _call_direct(None, None, None, None, None, None)\n")
        try:
            static_checks(b2)
        except AssertionError:
            pass
        else:
            raise AssertionError("出现裸直连后守卫仍判绿 = 假通过")
        # 造坏 3：把 NameError 放回去
        b3 = os.path.join(d, "nameerror.py")
        open(b3, "w", encoding="utf-8").write(
            src.replace("if not _is_safe_url(_mr_url, allow_internal=False):",
                        "if not _is_safe_url(_mr_url, allow_internal=use_opt):", 1))
        try:
            static_checks(b3)
        except AssertionError:
            pass
        else:
            raise AssertionError("use_opt NameError 复原后守卫仍判绿 = 假通过")


def c_no_default_dev_key():
    cfg = {}
    for line in open(ENV, encoding="utf-8", errors="replace"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            cfg[k.strip()] = v.strip()
    assert cfg.get("COST_OPTIMIZER_ENABLED", "").lower() == "true", "节能阀未启用"
    key = cfg.get("COST_OPTIMIZER_API_KEY", "")
    assert key, "缺 COST_OPTIMIZER_API_KEY"
    assert key != "aco-default-dev-key-2026", "生产仍在用网关默认开发密钥"
    assert key.startswith("aco-") and len(key) >= 30, "不是正式网关密钥"


def c_ledger_dir():
    logdir = os.path.join(BASE, "logs")
    assert os.path.isdir(logdir), f"缺日志目录 {logdir}"
    assert os.access(logdir, os.W_OK), "日志目录不可写"
    # 若生产台账已存在，属主不能是 root（gunicorn 以业务账号写不进去）
    lp = os.path.join(logdir, "gateway_bypass.jsonl")
    if os.path.exists(lp):
        st = os.stat(lp)
        assert st.st_uid != 0, "生产台账属主是 root，业务进程写不进去"


def main():
    ok("文件齐备", c_files)
    ok("逃生门单一入口 / 兜底无 NameError", c_static)
    ok("台账真跑：写入、读回、汇总、并发追加", c_ledger_runtime)
    ok("造坏三例必须判红", c_broken_copies)
    ok("生产不用默认开发密钥", c_no_default_dev_key)
    ok("生产台账目录可写且属主正确", c_ledger_dir)
    print(f"✅ verify_bypass_ledger: {passed}/6 组通过")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as exc:
        print(f"❌ verify_bypass_ledger 失败: {exc}")
        sys.exit(1)
    except Exception as exc:
        print(f"❌ verify_bypass_ledger 异常: {exc}")
        sys.exit(1)
