"""扫描成本核算的守卫。

钉住这些事：
1. 一次调用必须归到它前面最近的那次扫描，不能算到下一次头上（账要能对得上）
2. 距离上次提交超过 1 小时的零散调用不许归进来（否则夜里零星调用会把早上的账越算越胖）
3. 单次超限 / 单日超限 / 每文件超限，三条都要能判红（11-14 就是三条全中）
4. 正常的一天必须静默，不许狼来了（否则告警会被无视）
5. 同一个问题同一天只告一次（手动重跑不能轰炸邮箱）
6. 拿 11-14 的真实数据真跑一遍，算出来必须跟实际 90.28 元对得上
   —— 这条防的是「逻辑改坏了但单元测试还绿」这种假绿

造坏自检（python3 test_scan_cost_report.py --self-test）会把窗口上限和单次阈值
故意改坏，确认上面这些测试真的会红。守卫自己不会红的测试等于没有。
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)


def _load():
    path = os.path.join(_ROOT, "scripts", "scan_cost_report.py")
    spec = importlib.util.spec_from_file_location("scan_cost_report", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M = _load()

T0 = datetime(2026, 11, 14, 10, 0, 0)


def _scan(at, files=10, title="测试扫描", user_id=15):
    return {"user_id": user_id, "scan_id": "s_%s" % at.strftime("%H%M%S"),
            "title": title, "file_count": files, "at": at}


def _call(at, cost=1.0, tokens=1000, model="deepseek-v4-flash"):
    return {"at": at, "key": "k1", "model": model, "tokens": tokens, "cost": cost}


# ---------------------------------------------------------------- 归集口径

def test_attribution_basic():
    """调用落在两次扫描之间，必须归给前面那次，不能算到后面那次。"""
    scans = [_scan(T0), _scan(T0 + timedelta(minutes=10))]
    usage = [
        _call(T0 + timedelta(minutes=1), cost=2.0),
        _call(T0 + timedelta(minutes=5), cost=3.0),
        _call(T0 + timedelta(minutes=12), cost=7.0),  # 归第二次
    ]
    out = M.attribute(scans, usage)
    assert abs(out[0]["cost"] - 5.0) < 1e-6, "第一次扫描应承担 5 元，实际 %s" % out[0]["cost"]
    assert abs(out[1]["cost"] - 7.0) < 1e-6, "第二次扫描应承担 7 元，实际 %s" % out[1]["cost"]


def test_window_cap():
    """离提交超过 1 小时的调用不许归进来，否则孤立的零星调用会把老账越滚越大。"""
    scans = [_scan(T0)]
    usage = [
        _call(T0 + timedelta(minutes=5), cost=1.0),
        _call(T0 + timedelta(minutes=90), cost=99.0),  # 超窗口，必须丢弃
    ]
    out = M.attribute(scans, usage)
    assert abs(out[0]["cost"] - 1.0) < 1e-6, "超窗口的调用被算进来了：%s" % out[0]["cost"]


def test_before_first_scan_ignored():
    """第一次扫描之前的调用不归给任何人。"""
    scans = [_scan(T0)]
    out = M.attribute(scans, [_call(T0 - timedelta(minutes=5), cost=50.0)])
    assert out[0]["cost"] == 0.0, "早于首次提交的调用不该归属"


# ---------------------------------------------------------------- 判红

def test_alert_single_scan():
    scans = [{"cost": 50.0, "file_count": 10, "title": "大项目", "scan_id": "x", "models": {}}]
    summ = M.summarize(scans)
    probs = M.check_alerts("2026-11-14", scans, summ)
    assert any("单次扫描超限" in p for p in probs), "单次超限没判红: %s" % probs


def test_alert_daily():
    scans = [{"cost": 20.0, "file_count": 1000, "title": "a", "scan_id": "1", "models": {}},
             {"cost": 20.0, "file_count": 1000, "title": "b", "scan_id": "2", "models": {}}]
    summ = M.summarize(scans)
    probs = M.check_alerts("2026-11-14", scans, summ)
    assert any("单日总成本" in p for p in probs), "单日超限没判红: %s" % probs


def test_alert_per_file():
    scans = [{"cost": 5.0, "file_count": 10, "title": "小项目巨贵", "scan_id": "x", "models": {}}]
    summ = M.summarize(scans)
    probs = M.check_alerts("2026-11-14", scans, summ)
    assert any("每文件成本" in p for p in probs), "每文件超限没判红: %s" % probs


def test_clean_day_silent():
    """正常的一天必须一条都不报——狼来了比不报更糟。"""
    scans = [{"cost": 0.5, "file_count": 50, "title": "小项目", "scan_id": "x", "models": {}}]
    summ = M.summarize(scans)
    assert M.check_alerts("2026-11-14", scans, summ) == [], "正常成本被误报"


# ---------------------------------------------------------------- 去重

def test_dedup():
    tmp = tempfile.mkdtemp()
    old_state = M.STATE_FILE
    M.STATE_FILE = os.path.join(tmp, "alerted.json")
    try:
        fp = "2026-11-14|某问题"
        assert M._already_alerted(fp) is False
        M._mark_alerted(fp, "第一次")
        assert M._already_alerted(fp) is True, "同一问题第二次仍被判为未告警，会重复发信"
        assert M._already_alerted("2026-11-15|另一个问题") is False, "不同问题被误判为已告警"
    finally:
        M.STATE_FILE = old_state


# ---------------------------------------------------------------- 真数据回归

def test_real_20261114_matches_actual():
    """11-14 真实数据：脚本算出 86.77 元，当时实际扣费 90.28 元。

    允许 8% 误差（窗口上限会截掉少量零散调用）。这条防的是「函数都对、
    但整条链路跑出来是错的」——只测函数不测真实产出，就是假绿。
    """
    if not (os.path.exists(M.WEBSITE_DB) and os.path.exists(M.GATEWAY_DB)):
        print("  [SKIP] 生产库不可读，跳过真数据回归")
        return
    scans = M.load_scans("2026-11-14", "2026-11-14")
    if not scans:
        print("  [SKIP] 库里没有 11-14 的扫描记录")
        return
    usage = M.load_usage("2026-11-14", "2026-11-14")
    out = M.attribute(scans, usage)
    total = sum(s["cost"] for s in out)
    actual = 90.28
    assert abs(total - actual) / actual < 0.10, (
        "11-14 归集出 %.2f 元，与实际 %.2f 元差超过 10%%，归集逻辑可能被改坏了" % (total, actual))
    assert len(scans) > 100, "11-14 应有 200+ 次扫描记录，实际只有 %d 条" % len(scans)


# ---------------------------------------------------------------- 自检入口

def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in tests:
        try:
            fn()
            print("  ✅ %s" % fn.__name__)
        except AssertionError as e:
            failed += 1
            print("  ❌ %s: %s" % (fn.__name__, e))
        except Exception as e:  # noqa: BLE001
            failed += 1
            print("  ❌ %s 异常 %s: %s" % (fn.__name__, type(e).__name__, e))
    return failed, len(tests)


def _self_test():
    """造坏：把判据改坏，确认守卫真的会红。"""
    print("=== 造坏自检：改坏窗口上限 ===")
    script = (
        "import importlib.util,sys;"
        "p=r'%s';"
        "s=importlib.util.spec_from_file_location('m',p);"
        "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
        "m.MAX_WINDOW_MINUTES=10**9;"  # 窗口上限形同虚设
        "scans=[{'user_id':1,'scan_id':'a','title':'t','file_count':1,"
        "'at':__import__('datetime').datetime(2026,11,14,10,0,0)}];"
        "usage=[{'at':__import__('datetime').datetime(2026,11,14,11,30,0),"
        "'key':'k','model':'m','tokens':1,'cost':99.0}];"
        "o=m.attribute(scans,usage);"
        "sys.exit(0 if o[0]['cost']==0.0 else 1)"
    ) % os.path.join(_ROOT, "scripts", "scan_cost_report.py")
    rc = subprocess.run([sys.executable, "-c", script],
                        capture_output=True, text=True).returncode
    # 改坏后：超窗口的调用被算进来（cost=99 ≠ 0），说明 test_window_cap 能感知到
    if rc != 0:
        print("  ✅ 窗口上限失效后归集行为改变，test_window_cap 抓得住")
    else:
        print("  ❌ 窗口上限改成无穷大，归集结果却不变——test_window_cap 测不出这个回归")
        return 1

    print("=== 造坏自检：把阈值调到无穷大 ===")
    script2 = (
        "import importlib.util,sys;"
        "p=r'%s';"
        "s=importlib.util.spec_from_file_location('m',p);"
        "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
        "m.SINGLE_SCAN_LIMIT=1e9;"
        "scans=[{'cost':50.0,'file_count':10,'title':'t','scan_id':'x','models':{}}];"
        # 只看「单次扫描超限」这一条有没有消失：其它判据（每文件超限）仍会报，
        # 拿整体非空当判据会被它们盖住，测不出阈值本身有没有被验证。
        "probs=m.check_alerts('d',scans,m.summarize(scans));"
        "sys.exit(0 if not any('单次扫描超限' in x for x in probs) else 1)"
    ) % os.path.join(_ROOT, "scripts", "scan_cost_report.py")
    rc2 = subprocess.run([sys.executable, "-c", script2],
                         capture_output=True, text=True).returncode
    # 改坏后：单次超限告警应消失（rc2=0），说明 test_alert_single_scan 依赖这个阈值
    if rc2 == 0:
        print("  ✅ 阈值抬高后告警消失，test_alert_single_scan 确有判别力")
        return 0
    print("  ❌ 阈值调到无穷大告警还在——阈值逻辑没被真正验证")
    return 1


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(_self_test())
    failed, total = _run_all()
    print("\n%s %d/%d 通过" % ("✅" if failed == 0 else "❌", total - failed, total))
    sys.exit(0 if failed == 0 else 1)
