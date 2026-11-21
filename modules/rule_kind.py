# -*- coding: utf-8 -*-
"""问题性质分类：漏洞 / 缺陷 / 优化建议。

============================================================
唯一事实来源在扫描器：`engine/rule_taxonomy.py`
============================================================

这个文件是它在官网侧的副本，存在的唯一原因是**网站进程不能 import 扫描器目录**
（两个 systemd 服务、两个用户、两套依赖）。它不许有自己的判据：常量、
判定顺序必须和扫描器那份逐字一致，改了这边就是改错了地方。

同步守卫：`scripts/verify_rule_kind_sync.py`
  逐个比对 `_SECURITY_FAMILY_MARKERS` / `_SMELL_PREFIXES` / `_BRAIN_CATEGORY`
  与扫描器原件；任一处漂移即报红。

为什么要分性质（2026-11-22）：
    同一份报告里，「循环内字符串拼接」和「SQL 注入」共用一根 severity 刻度，
    两者都可能是 high。客户看到的是「4 个高危」，读完发现没有一个是真漏洞——
    不是降噪没做好，是报告只有「多严重」，没有「什么性质」。
"""

VULNERABILITY = "vulnerability"
BUG = "bug"
CODE_SMELL = "code_smell"

CATEGORY_LABELS = {
    VULNERABILITY: "漏洞",
    BUG: "缺陷",
    CODE_SMELL: "优化建议",
}

# 规则族里明确属于安全攻防的记号（安全类别名，不是误报豁免名单）
_SECURITY_FAMILY_MARKERS = (
    "CWE-", "TAINT", "SSRF", "CSRF", "XSS", "INJECT",
    "TRAVERSAL", "DESERIALIZE", "XXE", "PATH-TRAVERSAL",
)

# 优化与维护性规则族：出现在任何引擎里都算优化建议
_SMELL_PREFIXES = ("PERF-", "QUAL-", "CQ-", "ARCH-")

# 引擎身份 → 类型（键与扫描器 BRAIN_NAMES 一一对应）
_BRAIN_CATEGORY = {
    "1": BUG,            # 语法与AST分析
    "2": VULNERABILITY,  # 安全检测
    "3": BUG,            # 性能与可靠性
    "4": CODE_SMELL,     # 代码质量与可观测性
    "5": CODE_SMELL,     # 架构与部署
    "6": VULNERABILITY,  # 组件合规
    "7": BUG,            # AI应用健康检测
    "8": VULNERABILITY,  # 部署就绪与CI/CD安全
    "ai": VULNERABILITY,  # AI语义分析
    "poc": VULNERABILITY,  # PoC自动验证
}

DEFAULT_CATEGORY = BUG


def category_of(check_id, brain_id=None):
    """判定单条问题的类型。

    优先级：安全族记号 > 优化族前缀 > 引擎身份 > 默认（缺陷）。
    安全族记号排第一，因为它来自规则本身（CWE 编号 / 攻击面名），
    比「哪个引擎跑出来的」更硬。

    认不出来一律算缺陷，**不算漏洞**——对外数字宁可少，不可虚。
    """
    cid = str(check_id or "").upper()
    if cid:
        for marker in _SECURITY_FAMILY_MARKERS:
            if marker in cid:
                return VULNERABILITY
        for prefix in _SMELL_PREFIXES:
            if cid.startswith(prefix):
                return CODE_SMELL
    return _BRAIN_CATEGORY.get(str(brain_id or "").strip(), DEFAULT_CATEGORY)


def kind_of_issue(issue):
    """给一条 issue 判性质。

    扫描器新版本会在 issue 上直接写 `category` 三分类字段；老报告（1530 次扫描
    落库时还没有这个字段）里 `category` 可能是规则包自己的
    security/quality/... 值，不能直接用。所以：

      1. 只认三分类合法值，直接用；
      2. 否则按 rule_id + brain_id 重判（判据与扫描器一致）。
    """
    if not isinstance(issue, dict):
        return DEFAULT_CATEGORY
    cat = str(issue.get("category") or "").strip()
    if cat in CATEGORY_LABELS:
        return cat
    rid = issue.get("rule_id") or issue.get("check_id") or ""
    return category_of(rid, issue.get("brain_id"))
