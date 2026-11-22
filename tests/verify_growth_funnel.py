#!/usr/bin/env python3
"""转化链路与真实报告样例守卫（2026-11-08，QA 6l）。

要治的不是「页面有没有这个文件」，而是三件会自己骗自己的事：

1. 报告样例被手编 / 被手抄：页面上写死「6 条问题」「引擎版本 5.163.0」，
   过几天扫描器一升级，样例就变成假的，访客看到的和事实源对不上。
   → 事实源必须是真跑产物（自校验代码指纹 + 生成器含同一份代码 + 声明来源），
     页面只许从 `report[...]` 取数，不许出现任何结果字面量。
2. 把「初筛」说成完整报告、把零发现说成「代码很干净」，或复活停用的旧百分比。
   → 按语义查措辞，否定语境里的提醒不算违规（那是特意写给人看的边界说明）。
3. 入口只是写在 href 里、实际点不开；或者模板没渲染，访客看到 `{{ ... }}`。
   → 真发 HTTP 请求，检查响应体里真的有引擎版本、问题条数、规则编号。

判据全部按语义分类：结果值从事实源动态取，颜色不写死色值（只禁裸 hex），
文件按目录类别圈，不按文件名开白名单。造坏自检用本地真实 HTTP 服务，
不是拿 mock 冒充「真发过请求」。

用法：
  python3 verify_growth_funnel.py                     # QA 巡检（真发请求）
  python3 verify_growth_funnel.py --self-test         # 造坏自检
  python3 verify_growth_funnel.py --root <dir> --base-url none   # 本地 dry-run
"""
import argparse
import hashlib
import json
import re
import ssl
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DEFAULT_ROOT = Path("/opt/xinpect-website")
DEFAULT_BASE = "https://xinpect.xingwangzhineng.com"

FACTS_REL = "scripts/sample_report.json"
GENERATOR_REL = "scripts/build_sample_report.py"
SAMPLE_TPL_REL = "templates/sample_report.html"
PRICING_REL = "templates/pricing.html"
TRY_REL = "templates/try.html"
NAV_REL = "scripts/site_nav.json"
SITEMAP_REL = "templates/sitemap.xml"
LLMS_REL = "static/llms.txt"
APP_REL = "app.py"
# 四个独立导航块：缺一块就等于有人从侧门进来找不到样例页。
# 2026-11-22 起导航收敛到片段 templates/_nav.html（三套样式合一），
# 于是「块里有字面链接」不再是唯一合法写法：块里 include 了这个片段也算，
# 但前提是片段真按 scripts/site_nav.json 的 core 渲染 —— 否则等于把导航抄了第三份。
NAV_BLOCKS = (
    "templates/index.html",
    "templates/base.html",
    "static/pages/product.html",
    "static/pages/about.html",
)
NAV_PARTIAL = "templates/_nav.html"
NAV_INCLUDE_RE = re.compile(r"{%-?\s*include\s+[\"']_nav\.html[\"']\s*-?%}")
# 结果类字段：模板必须逐项从单一事实源取，且不许出现它们的字面量。
RESULT_FIELDS = (
    "scanner_version", "scan_time_seconds", "sample_file", "sample_language",
    "total_issues", "severity_breakdown", "issues",
)
ISSUE_FIELDS = (
    "rule_id", "title", "severity", "severity_label", "brain_name",
    "file", "line", "description", "suggestion", "code_snippet",
)
# 停用口径：旧样本百分比换了写法也照样抓。
BANNED_METRICS = ("91.3", "1.7%")
# 身份红线判的是「自称」，不是「有没有出现公司名」：工商登记字段是事实登记，
# 用「我是 / 我们是 / 由我」把公司名或创始人身份往自己身上揽，才判红。
IDENTITY_BANNED = ("黄迪尧", "创始人", "老板", "法人代表", "我叫")
ORG_SELF_CLAIM_RE = re.compile(
    r"(?:我是|我们是|本人|我们来自|由我)[^\n。；]{0,30}(?:有限公司|长沙煋旺|创始人)")
NEGATIVE_WORDS = ("不代表", "不等于", "不写", "不能说", "别当成", "并非", "不是", "不许", "别把")
OVERCLAIM_WORDS = ("代码很干净", "没问题", "保证没有漏洞", "零风险")
QUOTE_OPEN = "「『\"“‘《"
QUOTE_CLOSE = "」』\"”’》"
ASSERT_CUES = ("说明", "代表", "证明", "表示", "意味着", "可以放心", "放心上线",
               "等于", "就是", "直接上线", "零风险", "保证")
SOFTEN_CUES = ("不代表", "不等于", "别", "吗", "?", "？", "当成", "误导",
               "怎么", "如何", "误读", "并非", "验证", "没写")
JINJA_RE = re.compile(r"\{\{[\s\S]*?\}\}|\{%[\s\S]*?%\}")
HEX_RE = re.compile(r"#[0-9A-Fa-f]{3,8}\b")
YEN_RE = re.compile(r"¥\s*([\d,]+)")
SCRIPT_RE = re.compile(r"<(?:script|style)\b[\s\S]*?</(?:script|style)>", re.I)
COMMENT_RE = re.compile(r"<!--[\s\S]*?-->")
TAG_RE = re.compile(r"<[^>]+>")


def read(root: Path, rel: str):
    p = root / rel
    if not p.is_file():
        return None
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def strip_jinja(text: str):
    return JINJA_RE.sub("", text or "")


def visible_text(text: str):
    """只取访客真看得到的文字：脚本、样式、源码注释、HTML 标签都不算对外文案。

    试扫页有一段 JS 注释专门提醒「别把零发现当成我的代码没问题」，
    那是给开发者看的边界说明，不是页面上对用户下的结论。
    """
    t = SCRIPT_RE.sub(" ", text or "")
    t = COMMENT_RE.sub(" ", t)
    t = TAG_RE.sub(" ", t)
    return t


def overclaim_hits(plain: str):
    """按「结论句」语义判，不按关键词一刀切。

    引号里引用别人的说法、疑问句、否定提醒，全都不是我们下结论；
    只有句子里真的出现「说明 / 代表 / 可以放心」这类断言，才判红。
    """
    hits = []
    for w in OVERCLAIM_WORDS:
        for m in re.finditer(re.escape(w), plain):
            before = plain[m.start() - 1:m.start()] if m.start() else ""
            after = plain[m.end():m.end() + 1]
            if before in QUOTE_OPEN or after in QUOTE_CLOSE:
                continue
            if any(n in plain[max(0, m.start() - 12):m.start()] for n in NEGATIVE_WORDS):
                continue
            left = max([plain.rfind(c, 0, m.start()) for c in "。！？\n；"] + [-1])
            rights = [plain.find(c, m.end()) for c in "。！？\n；"]
            right = min([x for x in rights if x >= 0] or [len(plain)])
            sent = plain[left + 1:right]
            if any(s in sent for s in SOFTEN_CUES):
                continue
            if any(a in sent for a in ASSERT_CUES):
                hits.append((w, sent.strip()[:48]))
    return hits


# ---------------------------------------------------------------- S1 事实源
def check_facts(root: Path):
    errs = []
    raw = read(root, FACTS_REL)
    if raw is None:
        return ["S1 事实源缺失：%s（守卫拒绝判绿）" % FACTS_REL]
    try:
        facts = json.loads(raw)
    except ValueError as exc:
        return ["S1 事实源不是合法 JSON：%s" % exc]

    for key in ("schema", "source", "sample_code", "sample_code_sha256",
                "brains", "total_issues", "severity_breakdown", "issues", "note"):
        if key not in facts:
            errs.append("S1 事实源缺字段 %s" % key)
    if errs:
        return errs

    src = str(facts["source"])
    if "真跑" not in src or "call_scanner" not in src:
        errs.append("S1 事实源没声明来自扫描器真跑（不许人工改写冒充）")
    code = str(facts["sample_code"])
    if hashlib.sha256(code.encode()).hexdigest() != facts["sample_code_sha256"]:
        errs.append("S1 样例代码指纹与事实源不符（数据被手编过或代码被换过）")
    issues = facts["issues"]
    if not isinstance(issues, list) or not issues:
        errs.append("S1 事实源没有逐条问题明细，样例页会变成空壳")
    elif facts["total_issues"] != len(issues):
        errs.append("S1 事实源 total_issues=%s，明细却有 %d 条（数字和明细对不上）"
                    % (facts["total_issues"], len(issues)))
    else:
        for i, issue in enumerate(issues):
            for k in ISSUE_FIELDS:
                if k not in issue or issue[k] in ("", None):
                    errs.append("S1 第 %d 条问题缺 %s（报告形态不完整）" % (i + 1, k))
        if sum(facts["severity_breakdown"].values()) != facts["total_issues"]:
            errs.append("S1 严重度分档合计与问题总数对不上")
    for k in ("scanner_version", "scan_time_seconds", "sample_file", "sample_language"):
        if facts.get(k) in ("", None, 0):
            errs.append("S1 事实源结果字段 %s 为空，页面会显示空白" % k)
    if "初筛" not in str(facts["note"]) or "不等于完整报告" not in str(facts["note"]):
        errs.append("S1 事实源没写清「初筛不等于完整报告」的边界")

    # 生成器必须真的能复跑出这份数据：同一份代码原文 + 真的调 call_scanner。
    gen = read(root, GENERATOR_REL)
    if gen is None:
        errs.append("S1 可复跑生成器缺失：%s" % GENERATOR_REL)
    else:
        if "call_scanner" not in gen:
            errs.append("S1 生成器没调 call_scanner（等于手编一份 JSON）")
        if code not in gen:
            errs.append("S1 生成器里的样例代码与事实源不是同一份（结果不可复跑）")
        if FACTS_REL.split("/")[-1] not in gen:
            errs.append("S1 生成器没有把结果写回事实源")
    return errs


# ------------------------------------------------------- S2 页面不手抄结果
def check_no_hardcoded(root: Path, facts):
    errs = []
    tpl = read(root, SAMPLE_TPL_REL)
    if tpl is None:
        return ["S2 报告样例页缺失：%s" % SAMPLE_TPL_REL]
    plain = strip_jinja(tpl)

    for key in RESULT_FIELDS:
        if "report['%s']" % key not in tpl and 'report["%s"]' % key not in tpl:
            errs.append("S2 样例页没有从单一事实源取 %s（结果会漂移）" % key)

    # 结果字面量：从事实源动态取，不写死任何数字。
    literals = [("scanner_version", str(facts.get("scanner_version", "")))]
    literals += [("规则编号 " + str(i.get("rule_id")), str(i.get("rule_id", "")))
                 for i in facts.get("issues", [])[:8]]
    for label, val in literals:
        if val and val in plain:
            errs.append("S2 样例页手抄了结果字面量 %s（必须改为 report[...] 渲染）" % label)

    total = str(facts.get("total_issues", ""))
    if total and re.search(r"(?<![\d.])%s\s*(?:条|类|项|个)\s*(?:问题|风险|告警|发现|结果)?" % re.escape(total),
                           plain):
        errs.append("S2 样例页把「%s 条问题」写死了（扫描器一升级样例就是假的）" % total)

    # 装饰颜色必须走 tokens.css：按语义禁裸 hex，不写死具体色值。
    m = HEX_RE.search(plain)
    if m:
        errs.append("S2 样例页出现裸颜色 %s，颜色必须走 tokens.css 变量" % m.group(0))
    return errs


# ------------------------------------------------------------ S3 措辞与身份
def check_wording(root: Path):
    errs = []
    for rel in (SAMPLE_TPL_REL, TRY_REL, PRICING_REL, LLMS_REL):
        text = read(root, rel)
        if text is None:
            errs.append("S3 口径检查对象缺失：%s" % rel)
            continue
        plain = visible_text(strip_jinja(text))
        # 停用百分比写在源码注释里也不该放行：那是会被复制出去的口径。
        raw_plain = strip_jinja(text)
        for b in BANNED_METRICS:
            if b in raw_plain:
                errs.append("S3 %s 复活停用口径 %s（现行只给绝对条数：检出 1,292 条、漏报 123 条，"
                            "误报率只在 OWASP 题库口径下说，不许写成 0）" % (rel, b))
        for b in IDENTITY_BANNED:
            if b in plain:
                errs.append("S3 %s 出现身份禁写词 %s（对外只写「我是煋鉴 / 我们」）" % (rel, b))
        m = ORG_SELF_CLAIM_RE.search(plain)
        if m:
            errs.append("S3 %s 拿公司主体/创始人当自称：%s（对外只写「我是煋鉴 / 我们」）"
                        % (rel, m.group(0)[:32]))
        for w, sent in overclaim_hits(plain):
            errs.append("S3 %s 出现肯定式结论「%s」：%s（零发现只能说本次初筛未发现）"
                        % (rel, w, sent))

    tpl = read(root, SAMPLE_TPL_REL) or ""
    plain = strip_jinja(tpl)
    if "初筛" not in plain or "不等于完整报告" not in plain:
        errs.append("S3 样例页没把「初筛不等于完整报告」讲清楚")
    for act in ("/try", "/pricing", "/register"):
        if 'href="%s"' % act not in tpl:
            errs.append("S3 样例页缺下一步入口 %s（看完报告没地方去）" % act)
    if "不是任何客户的代码" not in plain and "不是客户代码" not in plain:
        errs.append("S3 样例页没声明演示代码不是客户代码")
    return errs


# ------------------------------------------------------- S4 定价页收短不丢数据
def check_pricing(root: Path):
    errs = []
    text = read(root, PRICING_REL)
    if text is None:
        return ["S4 定价页缺失：%s" % PRICING_REL]
    n_open, n_close = text.count("<details"), text.count("</details>")
    if n_open < 1 or n_open != n_close:
        errs.append("S4 定价页收短区 <details> 开合不配对（%d/%d），等于把细则删了或写坏了"
                    % (n_open, n_close))
        return errs
    if "<summary" not in text:
        errs.append("S4 收短区没有可点的标题，访客找不到展开入口")

    head, rest = text.split("<details", 1)
    folded = rest.split("</details>", 1)[0]
    # 首屏结论：先给「要不要花钱」和下一步，别让人翻半天。
    if not re.search(r"不用注册|免注册", head):
        errs.append("S4 定价页首屏没给出「免注册」结论")
    for act in ("/try", "/sample-report"):
        if 'href="%s"' % act not in head:
            errs.append("S4 定价页首屏结论条缺按钮 %s" % act)
    if head.count("recharge-plan-name") < 3:
        errs.append("S4 定价页档位卡片被收短收掉了（首屏只剩 %d 档）"
                    % head.count("recharge-plan-name"))
    # 收起的是排版，不是数据：金额、积分、对照内容都还在。
    amounts = set(YEN_RE.findall(folded))
    if len(amounts) < 2:
        errs.append("S4 收起区只剩 %d 个价格数字，积分包/权益数据被删了" % len(amounts))
    if "积分" not in folded:
        errs.append("S4 收起区没有积分说明，权益数据被删了")
    if len(folded) < 180:
        errs.append("S4 收起区只剩 %d 字，像是把整页细则删空了" % len(folded))
    return errs


# ------------------------------------------------------ S5 导航与入口声明（静态）
def check_entries(root: Path):
    errs = []
    nav_raw = read(root, NAV_REL)
    if nav_raw is None:
        return ["S5 导航事实源缺失：%s" % NAV_REL]
    try:
        nav = json.loads(nav_raw)
    except ValueError as exc:
        return ["S5 导航事实源不是合法 JSON：%s" % exc]
    core = nav.get("core") or []
    hits = [x for x in core if x.get("href") == "/sample-report"]
    if len(hits) != 1 or not hits[0].get("label"):
        errs.append("S5 导航单一事实源的 core 里没有唯一且有名字的 /sample-report 入口")
    for rel in NAV_BLOCKS:
        text = read(root, rel)
        if text is None:
            errs.append("S5 导航块 %s 不存在（有人从侧门进来找不到）" % rel)
            continue
        if 'href="/sample-report"' in text:
            continue
        if NAV_INCLUDE_RE.search(text):
            # 走片段：片段必须在，且必须按事实源 core 渲染（不许自己再抄一份导航项）
            part = read(root, NAV_PARTIAL)
            if part is None:
                errs.append("S5 导航块 %s include 了 %s，但这个片段不存在" % (rel, NAV_PARTIAL))
            elif "nav_core" not in part:
                errs.append("S5 导航片段 %s 没按 nav_core 渲染，等于又抄了一份导航" % NAV_PARTIAL)
            continue
        errs.append("S5 导航块 %s 没有 /sample-report（有人从侧门进来找不到）" % rel)

    app = read(root, APP_REL)
    if app is None or '@app.route("/sample-report")' not in app:
        errs.append("S5 后端没接 /sample-report 路由（链接只是摆设）")
    elif "sample_report.json" not in app or "render_template" not in app:
        errs.append("S5 /sample-report 路由没读事实源或没渲染页面")

    tr = read(root, TRY_REL)
    if tr is None or 'href="/sample-report"' not in tr:
        errs.append("S5 试扫页没有样例页入口（正在犹豫的人没东西可看）")
    elif "初筛" not in tr:
        errs.append("S5 试扫页丢了「初筛」口径")

    sm = read(root, SITEMAP_REL)
    if sm is None or "/sample-report" not in sm:
        errs.append("S5 sitemap 没收录 /sample-report")

    ll = read(root, LLMS_REL)
    if ll is None:
        errs.append("S5 AI 爬虫说明缺失：%s" % LLMS_REL)
    else:
        # 判据只写「禁止什么」，不写「必须宣称什么」（2026-11-22 修）：
        # 原来这条要求 llms.txt 必须写「误报 0 条」，把一句可被任意真实报告推翻的
        # 话做成了门禁 —— 谁想改对，先被守卫拦下。误报 0 是照 OWASP 题库补规则
        # 刷出来的过拟合结果，真实用户数据上不是这样，对外说出去就是给同行递刀。
        for bad in ("误报 0", "0 条误报", "零误报", "误报率 0", "结果是 0"):
            if bad in ll:
                errs.append("S5 AI 爬虫说明里还有绝对承诺「%s」，"
                            "这是可被任意一份真实报告推翻的话" % bad)
        if "漏报 123" not in ll:
            errs.append("S5 AI 爬虫说明没写现行基准结论（漏报 123 条）")
        for act in ("/try", "/sample-report"):
            if act not in ll:
                errs.append("S5 AI 爬虫说明没把 %s 列为免注册入口" % act)
    return errs


# ------------------------------------------- S6 入口真可达（真发 HTTP 请求）
ENTRY_PATHS = ("/try", "/pricing", "/sample-report", "/sitemap.xml")


def fetch(base: str, path: str):
    """真发一次 GET，返回 (status, body)。绝不只看 href 就宣布可达。"""
    url = base.rstrip("/") + path
    req = urllib.request.Request(url, method="GET",
                                 headers={"User-Agent": "xp-growth-guard/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=12,
                                    context=ssl._create_unverified_context()) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, e)


def check_http(base: str, facts):
    errs = []
    for path in ENTRY_PATHS:
        code, body = fetch(base, path)
        if code is None:
            errs.append("S6 真发请求失败 %s：%s" % (path, body[:80]))
        elif code in (404, 410) or code >= 500:
            errs.append("S6 %s 实测 HTTP %s（访客点不开，href 写得再全也没用）" % (path, code))

    code, body = fetch(base, "/sample-report")
    if code == 200:
        if "{{" in body:
            errs.append("S6 /sample-report 返回了未渲染的模板变量，访客看到的是 {{ ... }}")
        ver = str(facts.get("scanner_version", ""))
        if ver and ver not in body:
            errs.append("S6 /sample-report 页面里看不到引擎版本 %s（事实源没被渲染出来）" % ver)
        total = str(facts.get("total_issues", ""))
        if total and not re.search(r"%s\s*条" % re.escape(total), body):
            errs.append("S6 /sample-report 页面里看不到「%s 条」问题总数" % total)
        rule_ids = [str(i.get("rule_id")) for i in facts.get("issues", []) if i.get("rule_id")]
        if not rule_ids or not any(r in body for r in rule_ids):
            errs.append("S6 /sample-report 页面里一条规则编号都没有，逐条明细没渲染出来")
        if "初筛" not in body:
            errs.append("S6 /sample-report 页面里看不到初筛边界说明")

    code, body = fetch(base, "/sitemap.xml")
    if code == 200 and "/sample-report" not in body:
        errs.append("S6 线上 sitemap.xml 没有 /sample-report（线上还是旧文件）")
    return errs


def check(root: Path, base=None, with_http=True):
    errs = []
    raw = read(root, FACTS_REL)
    facts = {}
    if raw:
        try:
            facts = json.loads(raw)
        except ValueError:
            pass
    errs += check_facts(root)
    errs += check_no_hardcoded(root, facts)
    errs += check_wording(root)
    errs += check_pricing(root)
    errs += check_entries(root)
    if with_http and base:
        errs += check_http(base, facts)
    return errs


# ---------------------------------------------------------------- self-test
SEED_CODE = "def demo(x):\n    return x\n"


def seed_facts():
    return {
        "schema": 1,
        "generated_at": "2026-11-08T00:00:00+08:00",
        "source": "生产扫描器真跑（modules.scanner.call_scanner），未经人工改写",
        "scanner_version": "9.9.9",
        "scan_time_seconds": 1.25,
        "sample_file": "demo_app.py",
        "sample_language": "python",
        "sample_code": SEED_CODE,
        "sample_code_sha256": hashlib.sha256(SEED_CODE.encode()).hexdigest(),
        "scan_mode": "basic",
        "brains": ["1", "2", "4", "5", "6"],
        "total_issues": 2,
        "severity_breakdown": {"high": 2},
        "issues": [
            {"rule_id": "E1-DEMO-001", "title": "示例问题一", "severity": "high",
             "severity_label": "高危", "brain_name": "E1 语法与AST分析",
             "file": "demo_app.py", "line": 2, "description": "说明一",
             "suggestion": "改法一", "code_snippet": "1: def demo(x):"},
            {"rule_id": "E2-DEMO-002", "title": "示例问题二", "severity": "high",
             "severity_label": "高危", "brain_name": "E2 安全检测",
             "file": "demo_app.py", "line": 3, "description": "说明二",
             "suggestion": "改法二", "code_snippet": ">   3: return x"},
        ],
        "note": "免费试扫只跑规范层与安全引擎，本样例与试扫同口径，属初筛，不等于完整报告。",
    }


SEED_TPL = """{% extends "base.html" %}
{% block meta_description %}不注册先看一份真实扫描报告：每一条问题都给出代码位置、判定依据和修复写法。{% endblock %}
{% block content %}
引擎版本 {{ report['scanner_version'] }}，耗时 {{ report['scan_time_seconds'] | round(1) }} 秒。
文件 {{ report['sample_file'] }}，语言 {{ report['sample_language'] }}。
共 {{ report['total_issues'] }} 条，高危 {{ report['severity_breakdown'].get('high', 0) }} 条。
{% for issue in report['issues'] %}
<code>{{ issue['rule_id'] }}</code> {{ issue['title'] }} {{ issue['severity_label'] }}
{{ issue['brain_name'] }} {{ issue['file'] }} 第 {{ issue['line'] }} 行
<pre>{{ issue['code_snippet'] }}</pre>
{{ issue['description'] }} {{ issue['suggestion'] }}
{% endfor %}
<strong>免费试扫是初筛</strong>，<strong>不等于完整报告</strong>；初筛没报问题，也不代表代码很干净，只是本次初筛没发现。
演示代码由我们编写，<strong>不是任何客户的代码</strong>。
<a href="/try">免注册 · 先试扫一次</a>
<a href="/pricing">看看要花多少钱</a>
<a href="/register">直接注册看完整报告</a>
{% endblock %}
"""

SEED_PRICING = """{% extends "base.html" %}
{% block content %}
<div class="info-card" style="background:var(--bg-card);">
  <div>不用注册 · 不用付钱</div>
  <div>¥99 / 月起</div><div>¥1,499 / 月起</div>
  <a href="/try" class="btn btn-primary">免注册 · 先试扫一次</a>
  <a href="/sample-report" class="btn btn-secondary">先看一份真实报告样例</a>
  <p>免费试扫是初筛，不等于完整报告。</p>
</div>
<div class="recharge-plans">
  <div class="recharge-plan-name">免费版</div>
  <div class="recharge-plan-name">月卡</div>
  <div class="recharge-plan-name">季卡</div>
  <div class="recharge-plan-name">团队版</div>
</div>
<details style="background:var(--bg-card);">
  <summary>展开看：积分加量包、三档能力对照、完整权益表、邀请奖励</summary>
  <h3>积分加量包</h3><p>¥19 加 100 积分，¥89 加 600 积分，积分按需消耗，用多少扣多少。</p>
  <h3>完整权益表</h3><p>每月 300 积分；积分包不过期；团队共享 3000 积分池；邀请奖励各得 50 积分。</p>
  <h3>三档能力对照</h3><p>智能模式、深度模式、全引擎模式的扫描范围、AI 语义分析、PoC 自动验证逐项对照。</p>
  <h3>邀请奖励</h3><p>好友首次付费，双方各得 50 积分，积分直接进活跃池。</p>
</details>
{% endblock %}
"""

SEED_SERVED_SAMPLE = """<html><body>
引擎版本 9.9.9，耗时 1.3 秒。文件 demo_app.py，语言 python。
共 2 条，高危 2 条。
<code>E1-DEMO-001</code> 示例问题一
<code>E2-DEMO-002</code> 示例问题二
<strong>免费试扫是初筛</strong>，<strong>不等于完整报告</strong>。
<a href="/try">免注册 · 先试扫一次</a>
</body></html>
"""
SEED_SERVED_SITEMAP = "<urlset><url><loc>https://example.com/try</loc></url><url><loc>https://example.com/sample-report</loc></url></urlset>"
SEED_SERVED_TRY = "<html><body>免费代码初筛，粘贴一段代码。<a href=\"/sample-report\">看一份真实报告样例</a></body></html>"
SEED_SERVED_PRICING = "<html><body>价格方案 <a href=\"/try\">免注册先试扫</a></body></html>"


def seed(root: Path):
    files = {
        FACTS_REL: json.dumps(seed_facts(), ensure_ascii=False, indent=2) + "\n",
        GENERATOR_REL: (
            "#!/usr/bin/env python3\n"
            "from modules.scanner import call_scanner\n"
            "SAMPLE_CODE = '''%s'''\n"
            "raw = call_scanner({'demo_app.py': SAMPLE_CODE}, ['1','2','4','5','6'], options={})\n"
            "with open('sample_report.json', 'w') as f:\n"
            "    json.dump(raw, f)\n" % SEED_CODE.rstrip("\n")),
        SAMPLE_TPL_REL: SEED_TPL,
        PRICING_REL: SEED_PRICING,
        TRY_REL: "<p>免费代码初筛，只给结论摘要</p><a href=\"/sample-report\">看一份真实报告样例</a>",
        NAV_REL: json.dumps({"core": [
            {"label": "免费试扫", "href": "/try"},
            {"label": "报告样例", "href": "/sample-report"},
            {"label": "价格", "href": "/pricing"},
        ]}, ensure_ascii=False, indent=2) + "\n",
        SITEMAP_REL: "<urlset><url><loc>https://example.com/sample-report</loc></url></urlset>",
        LLMS_REL: "煋鉴：2,740 个 OWASP Benchmark 测试用例上检出 1,292 条、漏报 123 条，"
                  "真实项目上的误报率另算。免注册入口 /try；报告样例 /sample-report。",
        APP_REL: ("@app.route(\"/sample-report\")\n"
                  "def sample_report_page():\n"
                  "    with open('sample_report.json') as f:\n"
                  "        report = json.load(f)\n"
                  "    return render_template('sample_report.html', report=report)\n"),
        "served/sample-report.html": SEED_SERVED_SAMPLE,
        "served/sitemap.xml": SEED_SERVED_SITEMAP,
        "served/try.html": SEED_SERVED_TRY,
        "served/pricing.html": SEED_SERVED_PRICING,
    }
    for rel in NAV_BLOCKS:
        files[rel] = "<nav><a href=\"/sample-report\">报告样例</a><a href=\"/try\">免费试扫</a></nav>"
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    # 生成器必须含事实源里那一模一样的代码原文（末尾换行对齐）
    gen = root / GENERATOR_REL
    gen.write_text(gen.read_text(encoding="utf-8").replace(
        "SAMPLE_CODE = '''%s'''" % SEED_CODE.rstrip("\n"),
        "SAMPLE_CODE = '''%s'''" % SEED_CODE), encoding="utf-8")
    return files


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        mapping = {
            "/try": "served/try.html",
            "/pricing": "served/pricing.html",
            "/sample-report": "served/sample-report.html",
            "/sitemap.xml": "served/sitemap.xml",
        }
        rel = mapping.get(self.path.split("?")[0])
        root = self.server.site_root
        p = root / rel if rel else None
        if p is None or not p.is_file():
            self.send_error(404)
            return
        body = p.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def local_server(root: Path):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    srv.site_root = root
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, "http://127.0.0.1:%d" % srv.server_address[1]


def edit(root: Path, rel: str, fn):
    p = root / rel
    p.write_text(fn(p.read_text(encoding="utf-8")), encoding="utf-8")


def mutate_json(root: Path, rel: str, fn):
    p = root / rel
    d = json.loads(p.read_text(encoding="utf-8"))
    fn(d)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mutate_facts(root: Path, fn):
    mutate_json(root, FACTS_REL, fn)


def mutate_facts_json(root: Path, rel: str, fn):
    mutate_json(root, rel, fn)


def self_test():
    cases = []

    def case(name, mutate, want_red):
        cases.append((name, mutate, want_red))

    case("干净样本必须判绿", lambda r: None, False)
    case("事实源被删会判红", lambda r: (r / FACTS_REL).unlink(), True)
    case("总数与明细条数对不上会判红",
         lambda r: mutate_facts(r, lambda d: d.update(total_issues=3)), True)
    case("样例代码被手编过（指纹不符）会判红",
         lambda r: mutate_facts(r, lambda d: d.update(sample_code="tampered\n")), True)
    case("事实源没声明是真跑会判红",
         lambda r: mutate_facts(r, lambda d: d.update(source="人工整理")), True)
    case("事实源丢掉初筛边界会判红",
         lambda r: mutate_facts(r, lambda d: d.update(note="这是一份完整报告")), True)
    case("生成器改成手编 JSON 会判红",
         lambda r: edit(r, GENERATOR_REL, lambda t: t.replace("call_scanner", "fake_result")), True)
    case("生成器里的代码与事实源不是同一份会判红",
         lambda r: edit(r, GENERATOR_REL, lambda t: t.replace(SEED_CODE, "def other(): pass\n")), True)
    case("页面手抄问题总数会判红",
         lambda r: edit(r, SAMPLE_TPL_REL, lambda t: t.replace("每一条问题", "2 条问题")), True)
    case("页面手抄引擎版本号会判红",
         lambda r: edit(r, SAMPLE_TPL_REL, lambda t: t.replace("引擎版本 {{ report['scanner_version'] }}",
                                                               "引擎版本 9.9.9")), True)
    case("页面漏渲染某个结果字段会判红",
         lambda r: edit(r, SAMPLE_TPL_REL, lambda t: t.replace("{{ report['sample_language'] }}", "python")), True)
    case("页面写肯定式「代码很干净」会判红",
         lambda r: edit(r, SAMPLE_TPL_REL, lambda t: t.replace("也不代表代码很干净，只是本次初筛没发现",
                                                               "说明代码很干净，可以放心上线")), True)
    case("页面复活 1.7% 旧误报率会判红",
         lambda r: edit(r, SAMPLE_TPL_REL, lambda t: t + "\n<p>误报率 1.7%</p>"), True)
    case("页面写出创始人/公司全称会判红",
         lambda r: edit(r, SAMPLE_TPL_REL, lambda t: t + "\n<p>创始人亲自打磨</p>"), True)
    case("样例页出现裸颜色会判红",
         lambda r: edit(r, SAMPLE_TPL_REL, lambda t: t + "\n<div style=\"color:#FF8800\">暖色</div>"), True)
    case("样例页缺下一步按钮会判红",
         lambda r: edit(r, SAMPLE_TPL_REL, lambda t: t.replace('<a href="/register">直接注册看完整报告</a>', "")), True)
    case("定价页把收起区删掉（收短变删数据）会判红",
         lambda r: edit(r, PRICING_REL, lambda t: t.split("<details", 1)[0]), True)
    case("定价页收起区丢掉价格数据会判红",
         lambda r: edit(r, PRICING_REL, lambda t: t.replace("¥19 加 100 积分，¥89 加 600 积分", "价格面议")), True)
    case("定价页首屏结论条丢掉免注册按钮会判红",
         lambda r: edit(r, PRICING_REL, lambda t: t.replace('<a href="/try" class="btn btn-primary">免注册 · 先试扫一次</a>', "")), True)
    case("定价页档位卡片被删会判红",
         lambda r: edit(r, PRICING_REL, lambda t: t.replace('<div class="recharge-plan-name">', '<div class="plan">', 2)), True)
    case("导航单一事实源删掉样例入口会判红",
         lambda r: mutate_facts_json(r, NAV_REL,
                                     lambda d: d.update(core=[x for x in d["core"]
                                                              if x["href"] != "/sample-report"])), True)
    case("四个导航块少一块会判红",
         lambda r: edit(r, NAV_BLOCKS[2], lambda t: '<nav><a href="/try">免费试扫</a></nav>'), True)
    # 2026-11-22：导航收敛到片段之后，新写法也得能判红判绿，否则等于给自己开了个后门。
    case("导航块改成引用片段但片段不存在会判红",
         lambda r: edit(r, NAV_BLOCKS[1], lambda t: '{% include "_nav.html" %}'), True)

    def _nav_with_partial(r, body):
        edit(r, NAV_BLOCKS[1], lambda t: '{% include "_nav.html" %}')
        p = r / NAV_PARTIAL
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")

    case("导航块引用片段、片段真接 nav_core 渲染必须判绿",
         lambda r: _nav_with_partial(
             r, '{% for it in nav_core %}<a href="{{ it.href }}">{{ it.label }}</a>{% endfor %}'),
         False)
    case("导航片段自己手抄导航项（没接 nav_core）会判红",
         lambda r: _nav_with_partial(r, '<a href="/sample-report">报告样例</a>'), True)
    case("后端没接路由会判红",
         lambda r: edit(r, APP_REL, lambda t: t.replace('@app.route("/sample-report")', '@app.route("/old")')), True)
    case("AI 爬虫说明复活旧口径会判红",
         lambda r: edit(r, LLMS_REL, lambda t: t.replace("漏报 123 条", "误报率 1.7%")), True)
    case("线上 /sample-report 真发请求 404 会判红",
         lambda r: (r / "served/sample-report.html").unlink(), True)
    case("线上页面返回未渲染的模板变量会判红",
         lambda r: edit(r, "served/sample-report.html", lambda t: t.replace("引擎版本 9.9.9", "引擎版本 {{ report['scanner_version'] }}")), True)
    case("线上页面看不到问题条数会判红",
         lambda r: edit(r, "served/sample-report.html", lambda t: t.replace("共 2 条，高危 2 条", "共若干条")), True)
    case("线上页面丢掉逐条规则编号会判红",
         lambda r: edit(r, "served/sample-report.html", lambda t: t.replace("E1-DEMO-001", "").replace("E2-DEMO-002", "")), True)
    case("线上 sitemap 没收录样例页会判红",
         lambda r: edit(r, "served/sitemap.xml", lambda t: '<urlset></urlset>'), True)
    case("只改时间戳不改内容必须判绿",
         lambda r: __import__("os").utime(r / SAMPLE_TPL_REL, (1, 1)), False)

    ok = failed = 0
    for name, mutate, want_red in cases:
        with tempfile.TemporaryDirectory(prefix="xp_growth_") as td:
            root = Path(td)
            seed(root)
            mutate(root)
            srv, base = local_server(root)
            try:
                errs = check(root, base, with_http=True)
            finally:
                srv.shutdown()
                srv.server_close()
            red = bool(errs)
            if red == want_red:
                ok += 1
                print("  OK  %s%s" % (name, ("（判红 %d 项）" % len(errs)) if red else ""))
            else:
                failed += 1
                print("FAIL  %s：期望%s，实际%s；%s" % (
                    name, "判红" if want_red else "判绿",
                    "判红" if red else "判绿", "; ".join(errs[:2])))
    print("转化链路守卫自测: %d 项, 通过 %d, 失败 %d" % (len(cases), ok, failed))
    return 1 if failed else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    ap.add_argument("--base-url", default=DEFAULT_BASE,
                    help="入口真发请求的目标；写 none 可跳过 HTTP（仅本地 dry-run）")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    root = Path(args.root)
    base = None if args.base_url.lower() == "none" else args.base_url
    errs = check(root, base, with_http=bool(base))
    if errs:
        for e in errs:
            print("FAIL " + e)
        print("转化链路守卫: %d 项不通过" % len(errs))
        return 1
    facts = json.loads((root / FACTS_REL).read_text(encoding="utf-8"))
    print("转化链路守卫: 事实源 %s 条真跑问题、页面 0 处手抄、%d 个入口真发请求可达%s"
          % (facts["total_issues"], len(ENTRY_PATHS), "" if base else "（本次跳过 HTTP）"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
