# -*- coding: utf-8 -*-
"""官网模块自检：先注入生产环境变量，再导入被测模块。

为什么不在 shell 里 source：
    sudo -u xinpect-web 会重置环境；而在 root shell 里 source 后再切用户，
    变量又丢了。干脆在 Python 里读 env 文件自己设，谁跑都一样。
"""
import os
import sys

ENV_FILE = "/etc/xinpect/website.env"

# 只认 KEY=VALUE 行，不执行任何内容
try:
    with open(ENV_FILE, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
except (FileNotFoundError, PermissionError):
    # 服务账号读不到 env 文件是正常的（600 root）。
    # 正常调用路径是 run_as_service.py 由 root 读好后注入，这里只是兜底。
    pass

ROOT = os.environ.get("XINPECT_WEBSITE_ROOT", "/opt/xinpect-website")
sys.path.insert(0, ROOT)


def _load_isolation():
    """绕开 modules/__init__.py，直接按文件加载被测模块。

    为什么要绕：modules/__init__.py 会拉起 constants → db → 一整条启动链，
    缺环境变量就 RuntimeError。守卫要验的是「分层判定对不对」，
    不是「生产进程能不能起来」——这两件事混在一起，造坏时会用
    ModuleNotFoundError 冒充断言失败，看着红、其实没验到东西。

    做法：先伪造一个 modules 包（只给 __path__，不执行 __init__），
    再把 rule_kind 和 report_verdict 装进去，让 report_verdict 里
    `from modules.rule_kind import ...` 命中已装载的模块。
    """
    import importlib.util
    import types

    pkg = types.ModuleType("modules")
    pkg.__path__ = [os.path.join(ROOT, "modules")]
    sys.modules["modules"] = pkg

    for name in ("rule_kind", "report_verdict"):
        path = os.path.join(ROOT, "modules", name + ".py")
        if not os.path.exists(path):
            sys.exit("缺文件：%s" % path)
        spec = importlib.util.spec_from_file_location("modules." + name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["modules." + name] = mod
        spec.loader.exec_module(mod)


_load_isolation()

failures = []


def check(name, fn):
    try:
        ok, detail = fn()
    except Exception as exc:  # noqa: BLE001
        failures.append(name)
        print("  [FAIL] %s -> %r" % (name, exc))
        return
    if ok:
        print("  [ OK ] %s  %s" % (name, detail))
    else:
        failures.append(name)
        print("  [FAIL] %s  %s" % (name, detail))


def _t_import():
    from modules.report_verdict import build
    r = build([])
    return r["counts"]["must"] == 0, "空输入 counts=%s" % r["counts"]


def _t_kind():
    from modules.rule_kind import category_of, VULNERABILITY, CODE_SMELL, BUG
    cases = [
        ("E2-SEC-PY-001", "2", VULNERABILITY, "安全引擎"),
        ("PERF-M-006", "3", CODE_SMELL, "性能族前缀优先于引擎"),
        ("CQ-NAM-004", "4", CODE_SMELL, "质量族"),
        ("E2-SH-001", "2", VULNERABILITY, "shell 注入族"),
        ("UNKNOWN-X", "1", BUG, "认不出算缺陷"),
    ]
    bad = []
    for cid, bid, want, why in cases:
        got = category_of(cid, bid)
        if got != want:
            bad.append("%s(%s) 期望 %s 实际 %s [%s]" % (cid, bid, want, got, why))
    return not bad, "; ".join(bad) if bad else "%d 条判据全部符合" % len(cases)


def _t_layers():
    """构造三条样本：真问题 / 写法建议 / AI 判误报。"""
    from modules.report_verdict import build, TIER_MUST, TIER_SHOULD, TIER_EXCLUDED
    issues = [
        {"rule_id": "E2-SEC-PY-001", "brain_id": "2", "severity": "high",
         "title": "SQL 注入", "file": "a.py", "line": 1},
        {"rule_id": "PERF-M-006", "brain_id": "3", "severity": "high",
         "title": "字符串拼接", "file": "a.py", "line": 2},
        {"rule_id": "E2-SH-001", "brain_id": "2", "severity": "medium",
         "title": "未加引号", "file": "a.sh", "line": 3,
         "ai_source": "ai_false_positive", "ai_confidence": 95,
         "ai_analysis": "变量已加引号"},
        {"rule_id": "E2-SH-001", "brain_id": "2", "severity": "medium",
         "title": "未加引号（把握不足）", "file": "a.sh", "line": 4,
         "ai_source": "ai_false_positive", "ai_confidence": 50,
         "ai_analysis": "可能吧"},
    ]
    r = build(issues)
    c = r["counts"]
    problems = []
    if c[TIER_MUST] != 2:
        problems.append("必修应为 2（安全1 + 把握不足的1），实际 %d" % c[TIER_MUST])
    if c[TIER_SHOULD] != 1:
        problems.append("建议改应为 1，实际 %d" % c[TIER_SHOULD])
    if c[TIER_EXCLUDED] != 1:
        problems.append("复核未采纳应为 1，实际 %d" % c[TIER_EXCLUDED])
    # 把握 50 的不许被排除——那是替人下结论
    for it in r["tiers"][TIER_MUST]:
        if it["issue"]["line"] == 4 and "存疑" not in it["verdict"]["reason"]:
            problems.append("把握不足的那条应标「复核存疑」")
    # 结论里的数字必须和分层一致
    head = r["conclusion"]["headline"]
    if "2 个问题必须修" not in head:
        problems.append("结论与分层不一致：%s" % head)
    return not problems, "; ".join(problems) if problems else "4 条样本分层与结论一致"


def _t_excluded_has_reason():
    """复核未采纳必须带具体依据，不许只有一句复读。"""
    from modules.report_verdict import build, TIER_EXCLUDED
    r = build([{"rule_id": "E2-SH-001", "brain_id": "2", "severity": "medium",
                "ai_source": "ai_false_positive", "ai_confidence": 90,
                "ai_analysis": "第16行所有变量均已加引号"}])
    items = r["tiers"][TIER_EXCLUDED]
    if not items:
        return False, "该被排除却没排除"
    reason = items[0]["verdict"]["reason"]
    return "均已加引号" in reason, "依据=%s" % reason[:30]


def _t_gaps_change_headline():
    """有地方没查全时，第一句不许说「没有问题」。

    实证：一份 8 个文件没解析、10 个大脑模块全部只查了一部分的报告，
    第一屏写着「太棒了！未检测到任何问题」，三层卡却标着「部分未检测」。
    """
    from modules.report_verdict import build
    clean = build([])
    if clean["conclusion"]["tone"] != "good":
        return False, "没有缺口时结论不是 good：%r" % clean["conclusion"]

    gapped = build([], gaps=["3 个文件没能解析"])
    head = gapped["conclusion"]["headline"]
    detail = gapped["conclusion"].get("detail") or ""
    problems = []
    if "没有需要处理的问题" in head or "没有任何问题" in head:
        problems.append("有缺口时第一句还在报喜：%s" % head)
    if gapped["conclusion"]["tone"] != "warn":
        problems.append("有缺口时 tone 应为 warn，实际 %s" % gapped["conclusion"]["tone"])
    if "3 个文件没能解析" not in detail:
        problems.append("缺口没写进说明：%s" % detail)
    return not problems, "; ".join(problems) if problems else "缺口=%s" % head


print("=== report_verdict / rule_kind 自检 ===")
check("模块可导入", _t_import)
check("分类判据", _t_kind)
check("三层分组与结论一致", _t_layers)
check("排除项带具体依据", _t_excluded_has_reason)
check("没查全时结论不报喜", _t_gaps_change_headline)

if failures:
    print("\n结果：%d 项失败 -> %s" % (len(failures), ", ".join(failures)))
    sys.exit(1)
print("\n结果：5 项全部通过")
