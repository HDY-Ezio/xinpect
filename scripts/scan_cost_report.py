#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扫描成本核算：把网关的 LLM 花销归集到每次扫描上。

为什么需要：
  usage_records 只知道「每次 API 调用花多少」，scans 表只知道「谁扫了多少文件」。
  两本账对不上，所以 11-14 一个项目烧了 90 元，事后要翻三个库、写四条 SQL 才
  拼得出来。这个脚本把两本账合并，一眼能看到「这次扫描花了多少钱、每文件多少」。

归集口径（唯一事实来源）：
  一次扫描的成本 = [本次提交时刻, 下一次提交时刻) 窗口内，同一 api_key 的
  LLM 实际花费。生产扫描是串行执行（一次提交后等它扫完再提交下一次），窗口
  不重叠，因此不会重复计算。窗口上限 1 小时，避免长时间无新扫描时把之后的
  零散调用都算进来。

判红三条：
  1. 单次扫描成本 > 单次阈值（默认 20 元）——一次提交烧掉这么多，必须让人知道
  2. 单日总成本 > 单日阈值（默认 30 元）——当天整体失控
  3. 每文件成本 > 0.1 元 ——说明有不正常的重复调用，同样文件数不该这么贵

用法：
  python3 scan_cost_report.py                # 最近 7 天汇总
  python3 scan_cost_report.py --date 2026-11-14
  python3 scan_cost_report.py --json          # 机器可读
  python3 scan_cost_report.py --alert-check   # 只判要不要告警（给 cron 用）
"""
import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta

WEBSITE_DB = os.environ.get("XINPECT_WEBSITE_DB", "/opt/xinpect-website/xinpect.db")
GATEWAY_DB = os.environ.get("XINPECT_GATEWAY_DB",
                            "/home/ubuntu/ai-cost-optimizer/data/ai_cost_optimizer.db")

# 阈值：从环境变量读，缺省用实测出来的合理值
SINGLE_SCAN_LIMIT = float(os.environ.get("SCAN_COST_SINGLE_LIMIT", "20"))
DAILY_LIMIT = float(os.environ.get("SCAN_COST_DAILY_LIMIT", "30"))
PER_FILE_LIMIT = float(os.environ.get("SCAN_COST_PER_FILE_LIMIT", "0.1"))
MAX_WINDOW_MINUTES = 60


def _parse(ts):
    """解析两边不同的时间格式，统一成本地 naive datetime。"""
    if not ts:
        return None
    s = str(ts).strip()
    if "T" in s:
        s = s.replace("T", " ")
    # 去掉时区后缀（两边都是 +08:00 或本地时间，做差不需要时区）
    for suffix in ("+08:00", "+0800", "Z"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
    s = s.split(".")[0]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def load_scans(day_from, day_to):
    """取网站库的扫描提交记录（谁来扫、扫多少文件、什么时候）。"""
    db = sqlite3.connect("file:%s?mode=ro" % WEBSITE_DB, uri=True, timeout=10)
    try:
        rows = db.execute(
            """
            SELECT user_id, scan_id, title, file_count, created_at
            FROM scans
            WHERE date(created_at) BETWEEN ? AND ?
            ORDER BY created_at
            """,
            (day_from, day_to),
        ).fetchall()
    finally:
        db.close()
    out = []
    for user_id, scan_id, title, file_count, created_at in rows:
        ts = _parse(created_at)
        if ts is None:
            continue
        out.append({
            "user_id": user_id,
            "scan_id": scan_id,
            "title": (title or "")[:60],
            "file_count": int(file_count or 0),
            "at": ts,
        })
    return out


def load_usage(day_from, day_to):
    """取网关库的全部调用明细，用于按窗口求和。"""
    start = datetime.strptime(day_from, "%Y-%m-%d")
    end = datetime.strptime(day_to, "%Y-%m-%d") + timedelta(days=2)  # 多留一天余量
    db = sqlite3.connect("file:%s?mode=ro" % GATEWAY_DB, uri=True, timeout=10)
    try:
        rows = db.execute(
            """
            SELECT created_at, api_key_id, model, total_tokens, actual_cost
            FROM usage_records
            WHERE created_at >= ? AND created_at < ?
            """,
            (start.strftime("%Y-%m-%dT00:00:00"), end.strftime("%Y-%m-%dT00:00:00")),
        ).fetchall()
    finally:
        db.close()
    out = []
    for created_at, key, model, tokens, cost in rows:
        ts = _parse(created_at)
        if ts is None:
            continue
        out.append({
            "at": ts,
            "key": key or "",
            "model": model or "",
            "tokens": int(tokens or 0),
            "cost": float(cost or 0.0),
        })
    return out


def attribute(scans, usage):
    """把每次调用归到它前面最近的那次扫描。并发生效时会偏高，生产串行无此问题。"""
    if not scans:
        return []
    scans = sorted(scans, key=lambda x: x["at"])
    usage = sorted(usage, key=lambda x: x["at"])

    for s in scans:
        s["cost"] = 0.0
        s["tokens"] = 0
        s["calls"] = 0
        s["models"] = {}

    # 双指针：每次调用归到「提交时刻 <= 调用时刻」里最近的那次扫描
    j = 0
    for u in usage:
        while j + 1 < len(scans) and scans[j + 1]["at"] <= u["at"]:
            j += 1
        if scans[j]["at"] > u["at"]:
            continue  # 早于第一次扫描的调用，不归属
        gap_min = (u["at"] - scans[j]["at"]).total_seconds() / 60.0
        if gap_min > MAX_WINDOW_MINUTES:
            continue
        s = scans[j]
        s["cost"] += u["cost"]
        s["tokens"] += u["tokens"]
        s["calls"] += 1
        s["models"][u["model"]] = s["models"].get(u["model"], 0.0) + u["cost"]
    return scans


def summarize(scans):
    total_cost = sum(s.get("cost", 0.0) for s in scans)
    total_files = sum(s.get("file_count", 0) for s in scans)
    total_calls = sum(s.get("calls", 0) for s in scans)
    return {
        "scans": len(scans),
        "files": total_files,
        "calls": total_calls,
        "cost": round(total_cost, 2),
        "per_file": round(total_cost / total_files, 4) if total_files else 0.0,
        "per_scan": round(total_cost / len(scans), 2) if scans else 0.0,
    }


def check_alerts(day, scans, summary):
    """判红三条。返回问题列表，空表示健康。"""
    problems = []
    for s in scans:
        if s["cost"] > SINGLE_SCAN_LIMIT:
            problems.append(
                "单次扫描超限：%s 扫 %d 个文件花了 %.2f 元（阈值 %.0f 元）" % (
                    s["title"] or s["scan_id"], s["file_count"], s["cost"], SINGLE_SCAN_LIMIT))
    if summary["cost"] > DAILY_LIMIT:
        problems.append("单日总成本 %.2f 元，超过阈值 %.0f 元" % (
            summary["cost"], DAILY_LIMIT))
    if summary["per_file"] > PER_FILE_LIMIT:
        problems.append("每文件成本 %.4f 元，超过阈值 %.2f 元（可能存在重复调用）" % (
            summary["per_file"], PER_FILE_LIMIT))
    return problems


STATE_FILE = os.environ.get("SCAN_COST_STATE",
                            "/var/log/xinpect/scan_cost_alerted.json")


def _already_alerted(fingerprint):
    """同一天同一个问题只发一次邮件。防止手动重跑时轰炸邮箱。"""
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            st = json.load(f)
    except Exception:
        st = {}
    return st.get("fingerprint") == fingerprint


def _mark_alerted(fingerprint, detail):
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"fingerprint": fingerprint,
                       "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                       "detail": detail}, f, ensure_ascii=False, indent=1)
    except Exception as e:  # noqa: BLE001
        print("写告警状态失败（不影响主流程）:", e, file=sys.stderr)


def send_cost_alert(day, problems, summary, top):
    """发一封说人话的成本告警。走项目唯一发信出口，不另开 SMTP 连接。"""
    fingerprint = "%s|%s" % (day, "|".join(sorted(problems))[:200])
    if _already_alerted(fingerprint):
        print("今天这个成本问题已经告过警了，不重复发")
        return "skipped"

    lines = [
        "扫描成本超了，具体是这样：",
        "",
        "【%s】一共扫了 %d 次、%d 个文件，花了 %.2f 元。" % (
            day, summary["scans"], summary["files"], summary["cost"]),
        "平均每文件 %.4f 元，每次 %.2f 元。" % (
            summary["per_file"], summary["per_scan"]),
        "",
        "超限的地方：",
    ]
    for p in problems:
        lines.append("  · " + p)

    if top:
        lines += ["", "花钱最多的几次："]
        for t in top[:5]:
            if t["cost"] < 0.01:
                continue
            lines.append("  · %s —— %d 个文件，%.2f 元，%d 次调用" % (
                t["title"] or "(无标题)", t["files"], t["cost"], t["calls"]))

    lines += [
        "",
        "怎么降：",
        "  1. 大项目扫之前先算账：文件数 × 0.025 元 ≈ 成本",
        "  2. 长任务避开高峰（9-12 点、14-18 点单价翻倍）",
        "  3. flex 低优档已经上线，走它单价约是常规的一半",
        "",
        "完整账目：/var/log/xinpect/scan_cost_last.json",
    ]

    body = "\n".join(lines)
    try:
        sys.path.insert(0, "/opt/xinpect-website")
        from modules.email_sender import _send_mail

        ok = _send_mail(
            "hdyabcd@163.com",
            "【煋鉴】扫描成本超限：%s 花了 %.2f 元" % (day, summary["cost"]),
            "<pre style=\"font-family:monospace;font-size:14px;line-height:1.7\">"
            + body.replace("&", "&amp;").replace("<", "&lt;") + "</pre>",
        )
        if ok:
            _mark_alerted(fingerprint, body)
            return "sent"
        return "failed"
    except Exception as e:  # noqa: BLE001
        print("发告警失败:", e, file=sys.stderr)
        return "failed"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="指定单日 YYYY-MM-DD")
    ap.add_argument("--days", type=int, default=7, help="最近 N 天（默认 7）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--alert-check", action="store_true", help="只判告警，退出码 1 表示有问题")
    ap.add_argument("--notify", action="store_true", help="超限时发邮件告警")
    ap.add_argument("--top", type=int, default=5, help="列出成本最高的前 N 次扫描")
    args = ap.parse_args()

    if args.date:
        day_from = day_to = args.date
    else:
        today = datetime.now().date()
        day_to = today.strftime("%Y-%m-%d")
        day_from = (today - timedelta(days=args.days - 1)).strftime("%Y-%m-%d")

    scans = load_scans(day_from, day_to)
    if not scans:
        if args.json:
            print(json.dumps({"ok": True, "message": "区间内没有扫描记录",
                              "range": [day_from, day_to]}, ensure_ascii=False))
        else:
            print("区间 %s ~ %s 内没有扫描记录" % (day_from, day_to))
        return 0

    usage = load_usage(day_from, day_to)
    attributed = attribute(scans, usage)

    # 按天分组
    by_day = {}
    for s in attributed:
        d = s["at"].strftime("%Y-%m-%d")
        by_day.setdefault(d, []).append(s)

    result = {"range": [day_from, day_to], "days": {}, "problems": []}
    for d in sorted(by_day):
        day_scans = by_day[d]
        summ = summarize(day_scans)
        probs = check_alerts(d, day_scans, summ)
        summ["problems"] = probs
        summ["top"] = [
            {"title": s["title"], "files": s["file_count"],
             "cost": round(s["cost"], 2), "calls": s["calls"],
             "models": {k: round(v, 2) for k, v in s["models"].items()}}
            for s in sorted(day_scans, key=lambda x: -x["cost"])[: args.top]
        ]
        result["days"][d] = summ
        result["problems"].extend(probs)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    else:
        print("=" * 72)
        print("扫描成本核算  %s ~ %s" % (day_from, day_to))
        print("=" * 72)
        for d in sorted(result["days"]):
            s = result["days"][d]
            print("\n【%s】%d 次扫描 / %d 文件 / %d 次LLM / 合计 %.2f 元"
                  % (d, s["scans"], s["files"], s["calls"], s["cost"]))
            print("   每文件 %.4f 元   每次 %.2f 元" % (s["per_file"], s["per_scan"]))
            for t in s["top"]:
                if t["cost"] < 0.01:
                    continue
                print("   ├ %-42s %4d文件 %7.2f元 %4d次" % (
                    t["title"][:42], t["files"], t["cost"], t["calls"]))
        if result["problems"]:
            print("\n⚠ 问题：")
            for p in result["problems"]:
                print("   - " + p)
        else:
            print("\n✅ 成本在阈值内")

    if args.notify and result["problems"]:
        # 告警只看「指定那天」或「最近一天」，避免 7 天汇总时把历史问题重复报一遍
        target = args.date if args.date else sorted(result["days"])[-1]
        day_info = result["days"].get(target, {})
        outcome = send_cost_alert(target, day_info.get("problems", result["problems"]),
                                  {k: day_info.get(k, 0) for k in
                                   ("scans", "files", "cost", "per_file", "per_scan")},
                                  day_info.get("top", []))
        # 退出码：0=健康 1=有问题(alert-check) 2=超限刚发信 3=超限发信失败 4=超限但今天已发过
        return {"sent": 2, "failed": 3, "skipped": 4}.get(outcome, 3)

    return 1 if (args.alert_check and result["problems"]) else 0


if __name__ == "__main__":
    sys.exit(main())
