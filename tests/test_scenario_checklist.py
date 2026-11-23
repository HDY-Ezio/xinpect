#!/usr/bin/env python3
"""
场景清单测试 —— 把「做完测试却没查出来的坑」钉成可自动检出的断言。

来源：2026-10-30 复盘，根因是「测试围绕代码分支设计，而不是围绕用户场景设计」。
本文件覆盖两类事故，与 tests/SCENARIO_CHECKLIST.md 配套：

  一、补偿条「未登录」—— 不能只看 DOM 不渲染，要连源码一起查（黑盒 HTTP）
  二、老用户「新充值」分段计价 —— 存量旧价 / 新充新价 / 混合分段 / 边界（单元）

运行（纯脚本，不依赖 pytest）：
    cd /opt/xinpect-website \
    && sudo bash -c 'set -a; source /etc/xinpect/website.env; set +a; \
       PYTHONDONTWRITEBYTECODE=1 python3 tests/test_scenario_checklist.py'
退出码：0 = 全部通过，1 = 有失败。
"""
import sys
import math

sys.path.insert(0, "/opt/xinpect-website")

import requests  # noqa: E402
from modules.scoring import calculate_scan_cost, _legacy_credit_balance  # noqa: E402

WEBSITE_URL = "http://127.0.0.1:8621"

_PASS = 0
_FAIL = 0


def ok(name):
    global _PASS
    _PASS += 1
    print(f"  ✅ {name}")


def bad(name, msg=""):
    global _FAIL
    _FAIL += 1
    print(f"  ❌ {name}{': ' + msg if msg else ''}")


# ============================================================
# 一、补偿条：未登录连源码一起查（不只 DOM）
# ============================================================
BANNER_WORDS = ["50 积分", "立即领取", "compensation-banner", "已到账", "已领取"]


def test_homepage_no_banner_when_not_logged_in():
    name = "未登录首页源码不含补偿/50积分字样（含源码，不只DOM）"
    try:
        resp = requests.get(f"{WEBSITE_URL}/", timeout=15)
        assert resp.status_code == 200, f"HTTP {resp.status_code}"
        html = resp.text
        for word in BANNER_WORDS:
            assert word not in html, f"未登录首页源码不该含「{word}」，却出现了"
        ok(name)
    except Exception as e:
        bad(name, str(e))


def test_changelog_mentions_legacy_qualifier():
    name = "更新公告写清「10月30日前注册的老用户」（不能只写「登录即可领取」）"
    try:
        resp = requests.get(f"{WEBSITE_URL}/changelog", timeout=15)
        assert resp.status_code == 200, f"HTTP {resp.status_code}"
        html = resp.text
        assert ("10 月 30 日前注册" in html) or ("10月30日前注册" in html), \
            "更新公告必须写清补偿对象是「10 月 30 日前注册的老用户」"
        ok(name)
    except Exception as e:
        bad(name, str(e))


# ============================================================
# 二、老用户新充值：分段计价（单元）
# ============================================================
_ORIG_LEGACY = _legacy_credit_balance


def _with_legacy(legacy_bal):
    """临时替换 _legacy_credit_balance，返回上下文后恢复。"""
    class _Ctx:
        def __enter__(self):
            import modules.scoring as scoring
            scoring._legacy_credit_balance = lambda uid: legacy_bal

        def __exit__(self, *a):
            import modules.scoring as scoring
            scoring._legacy_credit_balance = _ORIG_LEGACY
    return _Ctx()


def _cost(lines, mode, legacy_bal):
    with _with_legacy(legacy_bal):
        return calculate_scan_cost(lines, scan_mode=mode, user_id=1)


def test_no_legacy_uses_new_price():
    name = "无旧积分 → 全新价（deep 3000行 = 300）"
    got = _cost(3000, "deep", 0)
    if got == 300:
        ok(name)
    else:
        bad(name, f"期望 300，实际 {got}")


def test_plenty_legacy_uses_old_price():
    name = "旧积分充足 → 全旧价（deep 3000行 = 40）"
    got = _cost(3000, "deep", 100)
    if got == 40:
        ok(name)
    else:
        bad(name, f"期望 40，实际 {got}")


def test_partial_legacy_segments():
    name = "旧积分不足 → 分段（legacy=30 → 7*4 + 90 = 118）"
    got = _cost(3000, "deep", 30)
    if got == 118:
        ok(name)
    else:
        bad(name, f"期望 118，实际 {got}")


def test_exact_boundary_uses_old():
    name = "旧积分刚好覆盖整单 → 全旧价（legacy=40 → 40）"
    got = _cost(3000, "deep", 40)
    if got == 40:
        ok(name)
    else:
        bad(name, f"期望 40，实际 {got}")


def test_quick_new_price():
    name = "quick 无旧积分 → 全新价（3000行 = 30）"
    got = _cost(3000, "quick", 0)
    if got == 30:
        ok(name)
    else:
        bad(name, f"期望 30，实际 {got}")


def test_quick_old_price():
    name = "quick 旧积分充足 → 全旧价（old_cost = 10）"
    got = _cost(3000, "quick", 10)
    if got == 10:
        ok(name)
    else:
        bad(name, f"期望 10，实际 {got}")


def test_compensation_legacy_uses_old():
    name = "补偿50积分（is_legacy=1）→ 按旧价（deep 3000行 = 40）"
    got = _cost(3000, "deep", 50)
    if got == 40:
        ok(name)
    else:
        bad(name, f"期望 40，实际 {got}")


# ============================================================
# 主入口
# ============================================================
if __name__ == "__main__":
    print("=" * 70)
    print("场景清单测试（补偿条未登录 + 老用户新充值分段计价）")
    print("=" * 70)

    print("\n【一、补偿条：未登录连源码一起查】")
    test_homepage_no_banner_when_not_logged_in()
    test_changelog_mentions_legacy_qualifier()

    print("\n【二、老用户新充值：分段计价】")
    test_no_legacy_uses_new_price()
    test_plenty_legacy_uses_old_price()
    test_partial_legacy_segments()
    test_exact_boundary_uses_old()
    test_quick_new_price()
    test_quick_old_price()
    test_compensation_legacy_uses_old()

    print("\n" + "=" * 70)
    print(f"结果：{_PASS} 通过 / {_FAIL} 失败")
    print("=" * 70)
    sys.exit(1 if _FAIL else 0)
