# -*- coding: utf-8 -*-
"""报告结论的唯一出口：一条问题该不该修、先说哪个、第一句话怎么说。

============================================================
为什么要有这个文件（2026-11-22）
============================================================

改之前的报告，同一个页面同时说两句话：

    顶部结论：    「发现 4 个高危问题，建议优先修复」
    修复路线图：  「立即修复 0 个文件 · 0 个问题」

两句都是真的，因为它们各自算各自的：

  * 结论看 `severity_counts`（high=4）
  * 路线图看 `fix_roadmap.PRIORITY_MAP`，而那张表把 high 映射成 P1，
    标签写的是「计划修复」；「立即修复」只留给 critical
  * 推荐优先修复列表又是第三套：按 severity 权重排序，不看优先级分桶

三套算法三个说法。客户读到的是「没逻辑」。

更根本的一条：报告根本没用自家 AI 的复核结论。
全库 66748 条 issue 里 19040 条（28.5%）带 `ai_source=ai_false_positive`，
AI 写了分析、给了置信度、说「无需修复」，报告照单全收，
甚至把两条 AI 说「无需修复」的问题排进「推荐优先修复」第 4、5 位。

本模块把「该不该修、先说哪个」压成一处，其余模块只许读，不许自己再算。

============================================================
三个处置层
============================================================

    must      必须修    漏洞 / 缺陷，且没有被复核排除
    should    建议改    优化建议（命名、行数、性能写法这类）
    excluded  复核未采纳 规则报出来了，但 AI 复核判定不成立且把握足够

「复核未采纳」不等于「不存在」：AI 会错。所以这层必须单独列出来、
写明判断依据和置信度、允许用户点回去，绝不允许静默消失。
"""

from modules.rule_kind import (
    CATEGORY_LABELS,
    CODE_SMELL,
    VULNERABILITY,
    BUG,
    kind_of_issue,
)

# ── 处置层 ────────────────────────────────────────────────────
TIER_MUST = "must"
TIER_SHOULD = "should"
TIER_EXCLUDED = "excluded"

TIER_META = {
    TIER_MUST: {
        "label": "必须修",
        "hint": "有真实影响，且复核未推翻",
        "color": "#DC2626",
    },
    TIER_SHOULD: {
        "label": "建议改",
        "hint": "不影响安全，改不改取决于你的取舍",
        "color": "#D97706",
    },
    TIER_EXCLUDED: {
        "label": "复核未采纳",
        "hint": "规则报出来了，复核判定不成立，供你核对",
        "color": "#6B7280",
    },
}

# AI 判定为误报、且置信度达到这条线，才允许移出主列表。
#
# 80 不是拍的：实测 19040 条 ai_false_positive 的置信度均值 88.8、
# 绝大多数在 90 以上；留 80 这道线是给「AI 说了但没把握」的留出路——
# 那些宁可留在主列表里让人自己判断，也不许替人决定。
AI_EXCLUDE_MIN_CONFIDENCE = 80.0

# ── 严重度归一 ────────────────────────────────────────────────
# 落库的 severity 混着两套体系，必须先压到同一根刻度（4 最重，0 最轻）：
#   SonarQube 四档：correctness / suspicious / style / restriction
#   常见五档：      critical / high / medium / low / info
# 映射依据：
#   correctness = 「确定是错的」，在四档里最重 → 与 high 同档
#   suspicious  = 「可能是错的」              → 与 medium 同档
#   restriction = 「用法的限制」              → 与 low 同档
#   style       = 风格                        → 最轻，与 info 同档
_SEVERITY_RANK = {
    "critical": 4, "blocker": 4,
    "high": 3, "correctness": 3,
    "medium": 2, "suspicious": 2,
    "low": 1, "restriction": 1,
    "info": 0, "style": 0,
}

_RANK_LABEL = {4: "严重", 3: "高危", 2: "中危", 1: "低危", 0: "建议"}


def severity_rank(issue):
    """把一条问题的 severity 压成 0-4 的整数档。认不出来当 0（最轻）。"""
    if not isinstance(issue, dict):
        return 0
    return _SEVERITY_RANK.get(str(issue.get("severity") or "").strip().lower(), 0)


def severity_label(issue):
    return _RANK_LABEL.get(severity_rank(issue), "建议")


def impact_label(issue, tier=None):
    """对外展示的「多严重」措辞。

    优化建议这一层不许用「高危」两个字：写法问题再重也不是安全风险，
    放在同一根刻度上说什么都会误导。所以按层换词。
    """
    if tier == TIER_SHOULD:
        return {3: "影响较大", 2: "一般", 1: "轻微", 0: "轻微"}.get(severity_rank(issue), "一般")
    return _RANK_LABEL.get(severity_rank(issue), "建议")


def _ai_confidence(issue):
    try:
        return float(issue.get("ai_confidence") or 0)
    except (TypeError, ValueError):
        return 0.0


def is_review_excluded(issue):
    """这条问题是否该被移出主列表（AI 复核判定不成立且把握足够）。"""
    if not isinstance(issue, dict):
        return False
    src = str(issue.get("ai_source") or "").strip()
    if src != "ai_false_positive":
        return False
    return _ai_confidence(issue) >= AI_EXCLUDE_MIN_CONFIDENCE


def verdict_of(issue):
    """单条问题的处置判定。

    返回 dict：
        tier       must / should / excluded
        kind       漏洞 / 缺陷 / 优化建议
        reason     为什么这么判（一句人话）
        rank       0-4 严重度档（同层内排序用）
        ai_note     AI 复核说了什么（没复核就是空串）
    """
    kind = kind_of_issue(issue)
    rank = severity_rank(issue)
    conf = _ai_confidence(issue)
    src = str(issue.get("ai_source") or "").strip()

    ai_note = ""
    if src == "ai_false_positive":
        ai_note = "复核判定：不成立（把握 %d%%）" % int(round(conf))
    elif src == "ai_confirmed":
        ai_note = "复核确认：成立（把握 %d%%）" % int(round(conf))

    if is_review_excluded(issue):
        # reason 用复核自己的话，而不是一句复读的模板。
        # 客户点开这一层，要的是「凭什么说不成立」，不是「已排除」。
        basis = str(issue.get("ai_analysis") or "").strip()
        if not basis:
            basis = "复核未给出具体依据"
        return {
            "tier": TIER_EXCLUDED,
            "kind": kind,
            "reason": basis,
            "rank": rank,
            "ai_note": ai_note,
        }

    if kind == CODE_SMELL:
        return {
            "tier": TIER_SHOULD,
            "kind": kind,
            "reason": "写法上的改进项，不影响安全",
            "rank": rank,
            "ai_note": ai_note,
        }

    if src == "ai_false_positive":
        # AI 说了不成立，但没给够把握 —— 不替人下结论，留在必修里并标出来
        return {
            "tier": TIER_MUST,
            "kind": kind,
            "reason": "复核存疑（把握不足），建议自行确认",
            "rank": rank,
            "ai_note": ai_note,
        }

    return {
        "tier": TIER_MUST,
        "kind": kind,
        "reason": "有真实影响" if kind == VULNERABILITY else "逻辑上可能出错",
        "rank": rank,
        "ai_note": ai_note,
    }


def _sort_key(item):
    """层内排序：严重度高的在前；同档里复核确认过的在前；再按文件行号稳定。"""
    v = item["verdict"]
    issue = item["issue"]
    confirmed = 0 if str(issue.get("ai_source") or "") == "ai_confirmed" else 1
    exploitable = 0 if str(issue.get("ai_exploitability") or "") == "high" else 1
    return (-v["rank"], confirmed, exploitable,
            str(issue.get("file") or ""), int(issue.get("line") or 0))


def build(issues, gaps=None):
    """把一堆 issue 分成三层，并给出第一屏要用的全部数字。

    gaps：这次没查全的地方（人话短句列表），由调用方从引擎台账得出。
          报告页和 Markdown 导出都传同一份，保证「页面说没查全、导出说查得很好」
          这种事不会再发生。0 个问题 + 有缺口时，第一句不许说「没有问题」。

    返回 dict：
        tiers       {must: [...], should: [...], excluded: [...]}  每项 {issue, verdict}
        counts      {must: n, should: n, excluded: n}
        by_kind     {vulnerability: n, bug: n, code_smell: n}   只看前两层
        conclusion  {headline, detail, tone}
        top         前 5 条必须修的（同规则同文件合并计数）
        score_basis 评分依据的一句话解释
    """
    tiers = {TIER_MUST: [], TIER_SHOULD: [], TIER_EXCLUDED: []}
    by_kind = {VULNERABILITY: 0, BUG: 0, CODE_SMELL: 0}

    for issue in issues or []:
        if not isinstance(issue, dict):
            continue
        v = verdict_of(issue)
        tiers[v["tier"]].append({"issue": issue, "verdict": v})
        if v["tier"] != TIER_EXCLUDED:
            by_kind[v["kind"]] = by_kind.get(v["kind"], 0) + 1

    for t in (TIER_MUST, TIER_SHOULD):
        tiers[t].sort(key=_sort_key)
    # 复核未采纳的按「把握高」在前——把握越高越该信它
    tiers[TIER_EXCLUDED].sort(
        key=lambda x: (-_ai_confidence(x["issue"]), str(x["issue"].get("file") or ""))
    )

    counts = {t: len(v) for t, v in tiers.items()}
    return {
        "tiers": tiers,
        "counts": counts,
        "by_kind": by_kind,
        "conclusion": _apply_gaps(_conclusion(tiers, counts, by_kind), counts, gaps),
        "top": _top_fixes(tiers[TIER_MUST], limit=5),
        "score_basis": "按必须修的问题数量与严重度扣分；复核未采纳的不计入",
    }


def _apply_gaps(conclusion, counts, gaps):
    """把「这次没查全」写进结论。缺口为空时原样返回。

    为什么必须写进第一句：一个没能解析的文件里可能就藏着那条漏洞。
    「没有需要处理的问题」和「部分未检测」同框，等于用漂亮结论盖住没做的事。
    """
    gaps = [g for g in (gaps or []) if g]
    if not gaps:
        return conclusion

    detail = "；".join(gaps) + "，这些地方不算查过"
    if counts.get(TIER_MUST) or counts.get(TIER_SHOULD):
        out = dict(conclusion)
        out["detail"] = (out["detail"] + "；" + detail + "。") if out.get("detail") else (detail + "。")
        if out.get("tone") == "good":
            out["tone"] = "warn"
        return out

    # 一条问题都没有，但确实有地方没查全：第一句不许说「没有问题」
    return {
        "headline": "这次没查出问题，但没检查全",
        "detail": detail + "。",
        "tone": "warn",
    }


def _top_fixes(must_items, limit=5):
    """推荐优先修复：同规则同文件合并成一条，带出现次数。"""
    out = []
    seen = {}
    for item in must_items:
        iss = item["issue"]
        rule_id = iss.get("rule_id") or iss.get("check_id") or ""
        key = (rule_id, iss.get("file") or "")
        if key in seen:
            seen[key]["times"] += 1
            continue
        if len(out) >= limit:
            continue
        rec = {
            "title": iss.get("title") or iss.get("name") or rule_id,
            "rule_id": rule_id,
            "file": iss.get("file") or "",
            "line": iss.get("line") or 0,
            "rank": item["verdict"]["rank"],
            "severity": severity_label(iss),
            "kind": item["verdict"]["kind"],
            "times": 1,
            "ai_note": item["verdict"]["ai_note"],
        }
        seen[key] = rec
        out.append(rec)
    return out


def _conclusion(tiers, counts, by_kind):
    """第一句话。数字全部来自上面的分层，不另算。"""
    must = counts[TIER_MUST]
    should = counts[TIER_SHOULD]
    excluded = counts[TIER_EXCLUDED]
    vulns = by_kind.get(VULNERABILITY, 0)
    bugs = by_kind.get(BUG, 0)

    if must == 0 and should == 0 and excluded == 0:
        return {
            "headline": "没有需要处理的问题",
            "detail": "这次扫描没有发现可处理的问题。",
            "tone": "good",
        }

    if must == 0:
        detail = "没有必须修的问题"
        if should:
            detail += "；另有 %d 条写法上的改进建议，改不改由你定" % should
        if excluded:
            detail += "；%d 条规则告警经复核判定不成立，列在最后供核对" % excluded
        return {"headline": detail, "detail": "", "tone": "good"}

    # 有必修：先说要修几个、其中几个涉及安全
    # 措辞用「涉及安全」而不是「是漏洞」：规则归类≠已确认漏洞，
    # 对外承诺宁可留余地——说成漏洞，客户按漏洞标准验收，差一条就是失信。
    if vulns:
        head = "有 %d 个问题必须修，其中 %d 个涉及安全" % (must, vulns)
    elif bugs:
        head = "有 %d 个问题必须修" % must
    else:
        head = "有 %d 个问题必须修" % must

    parts = []
    if excluded:
        parts.append("%d 条规则告警经复核判定不成立，已单列在报告最后，不计入上面这个数"
                     % excluded)
    if should:
        parts.append("另有 %d 条写法改进建议" % should)
    parts.append("修复顺序按影响大小排，第一条见下方推荐")

    return {
        "headline": head,
        "detail": "；".join(parts) + "。",
        "tone": "danger" if vulns else "warn",
    }
