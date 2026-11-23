#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
煋鉴 SLO/SLI 监控（轻量版，无 Prometheus 依赖）
每日 08:00 cron 运行，滚动 30 天窗口，三个 SLI：
  SLI-1 扫描成功率 = (扫描无任何7引擎error) / 总扫描        SLO >= 99.5%
  SLI-2 服务可用性 = 关键端点探测成功 / 总探测(跨日累计)    SLO >= 99.9%
  SLI-3 扫描超时率 = 单文件扫描 duration>=300s 视为超时     SLO 超时率 <= 0.5%
错误预算燃尽率 = 实际坏事件 / 允许坏事件；>1 即违约 -> 邮件告警(当日去重)。
只统计 30 天窗口内的现行数据；历史已修复错误天然落在窗口外，不做文本白名单。
"""
import json, os, sqlite3, sys, urllib.request, datetime, smtplib
from email.mime.text import MIMEText
from email.header import Header

DB = "/opt/xinpect-data/scan_results.db"
STATE = "/opt/xinpect-website/monitoring/slo/slo_state.json"
LOGDIR = "/opt/xinpect-website/monitoring/slo"
ENDPOINTS = [
    ("绿版扫描器", "http://127.0.0.1:8620/health", 200),
    ("官网", "http://127.0.0.1:8621/health", 200),
    ("蓝版扫描器", "http://127.0.0.1:8622/health", 200),
]
SLO_SUCCESS = 99.5
SLO_AVAIL = 99.9
SLO_TIMEOUT_MAX = 0.5      # 超时率上限 %
TIMEOUT_MS = 300000
BRAINS = ("1", "2", "3", "4", "5", "6", "7")
# 凭据只从仓库外读（2026-11-23）：授权码原先写死在这里，随代码进了公开仓库。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from secrets_env import load as _load_secrets  # noqa: E402

_SECRETS = _load_secrets()
SMTP_HOST = _SECRETS.get('SMTP_HOST') or 'smtp.163.com'
SMTP_PORT = int(_SECRETS.get('SMTP_PORT') or 465)
SMTP_USER = _SECRETS.get('SMTP_USER', '')
SMTP_PASS = _SECRETS.get('SMTP_PASSWORD', '')
ALERT_TO = _SECRETS.get('ALERT_TO') or 'hdyabcd@163.com'

def now_cn():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))

def calc_sli():
    con = sqlite3.connect(DB)
    cutoff = (now_cn() - datetime.timedelta(days=30)).timestamp()
    rows = con.execute(
        "SELECT result_json,duration_ms,file_count FROM scan_results WHERE created_at>?",
        (cutoff,)).fetchall()
    con.close()
    total = failed = timeout_single = single_n = 0
    err_kinds = {}
    for rj, dur, fc in rows:
        total += 1
        if fc == 1:
            single_n += 1
            if dur and dur >= TIMEOUT_MS:
                timeout_single += 1
        try:
            d = json.loads(rj)
        except Exception:
            failed += 1; err_kinds["result_json解析失败"] = err_kinds.get("result_json解析失败", 0) + 1
            continue
        for b in BRAINS:
            e = (d.get("results", {}).get(b) or {}).get("error")
            if e:
                failed += 1
                k = "[b%s] %s" % (b, e[:50])
                err_kinds[k] = err_kinds.get(k, 0) + 1
                break
    success = 100.0 * (total - failed) / total if total else 100.0
    timeout_rate = 100.0 * timeout_single / single_n if single_n else 0.0
    return total, failed, success, single_n, timeout_single, timeout_rate, err_kinds

def probe_avail():
    ok = 0; detail = []
    for name, url, expect in ENDPOINTS:
        try:
            with urllib.request.urlopen(urllib.request.Request(url), timeout=8) as r:
                good = r.status == expect
            detail.append("%s=%s" % (name, "OK" if good else "HTTP%s" % r.status))
            ok += 1 if good else 0
        except Exception as e:
            detail.append("%s=DOWN:%s" % (name, type(e).__name__))
    return ok, len(ENDPOINTS), detail

def load_state():
    if os.path.exists(STATE):
        try:
            return json.load(open(STATE))
        except Exception:
            pass
    return {"avail_probes": 0, "avail_ok": 0, "history": []}

def save_state(st):
    """统一落盘出口：原子写 + 存储异常降级，不中断监控。"""
    _root = "/opt/xinpect-website"
    if _root not in sys.path:
        sys.path.insert(0, _root)
    from monitoring.safe_write import write_json
    return write_json(STATE, st, label="SLO 状态")

def send_alert(subj, body):
    if not SMTP_USER or not SMTP_PASS:
        print("[ALERT-SKIP] 凭据未配置，告警邮件未发送:", subj)
        return
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header(subj, "utf-8"); msg["From"] = SMTP_USER; msg["To"] = ALERT_TO
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as s:  # 2026-10-23 修复：加超时防SMTP挂死
        s.login(SMTP_USER, SMTP_PASS); s.sendmail(SMTP_USER, [ALERT_TO], msg.as_string())

def main():
    os.makedirs(LOGDIR, exist_ok=True)
    ts = now_cn().strftime("%Y-%m-%d %H:%M:%S")
    total, failed, success, sn, t1, trate, kinds = calc_sli()
    a_ok, a_tot, adetail = probe_avail()
    st = load_state()
    st["avail_probes"] = st.get("avail_probes", 0) + a_tot
    st["avail_ok"] = st.get("avail_ok", 0) + a_ok
    avail = 100.0 * st["avail_ok"] / st["avail_probes"] if st["avail_probes"] else 100.0

    succ_burn = (failed / (total * (1 - SLO_SUCCESS / 100.0))) if total else 0
    avail_bad = st["avail_probes"] - st["avail_ok"]
    avail_burn = (avail_bad / (st["avail_probes"] * (1 - SLO_AVAIL / 100.0))) if st["avail_probes"] else 0

    violations = []
    if success < SLO_SUCCESS:
        violations.append("扫描成功率 %.2f%% < %.1f%%（错误预算燃尽 %.1fx，%d/%d）" % (success, SLO_SUCCESS, succ_burn, failed, total))
    if avail < SLO_AVAIL and st["avail_probes"] >= 30:
        violations.append("可用性 %.3f%% < %.1f%%（燃尽 %.1fx）" % (avail, SLO_AVAIL, avail_burn))
    if trate > SLO_TIMEOUT_MAX:
        violations.append("单文件超时率 %.2f%% > %.1f%%（%d/%d 卡到%d秒）" % (trate, SLO_TIMEOUT_MAX, t1, sn, TIMEOUT_MS // 1000))

    line = ("[%s] SLI 扫描成功率=%.3f%%(%d/%d 现行error=%d) 可用性=%.3f%%(%d/%d) 单文件超时率=%.2f%%(%d/%d) -> %s"
            % (ts, success, total - failed, total, failed, avail, st["avail_ok"], st["avail_probes"],
               trate, t1, sn, "SLO_PASS" if not violations else "SLO_VIOLATION"))
    print(line)
    with open(os.path.join(LOGDIR, "slo.log"), "a") as f:
        f.write(line + "\n")

    rec = {"ts": ts, "success_rate": round(success, 3), "total": total, "failed_window": failed,
           "avail_rate": round(avail, 3), "timeout_rate": round(trate, 3),
           "succ_budget_burn": round(succ_burn, 2), "violations": violations,
           "top_errors": dict(sorted(kinds.items(), key=lambda x: -x[1])[:5])}
    st["last"] = rec
    st["history"] = (st.get("history", []) + [rec])[-90:]
    save_state(st)

    if violations:
        today = now_cn().strftime("%Y-%m-%d")
        if st.get("last_alert_ts") != today:
            top = "\n".join("- %s x%d" % (k, n) for k, n in rec["top_errors"].items()) or "-（无明细）"
            body = ("煋鉴 SLO 违约告警（30天滚动窗口）\n时间：%s\n\n%s\n\n现行错误TOP：\n%s\n\n探测：%s"
                    % (ts, "\n".join("- " + v for v in violations), top, "; ".join(adetail)))
            try:
                send_alert("[P1]煋鉴SLO违约(30天可靠性目标)", body)
                st["last_alert_ts"] = today; save_state(st); print("告警邮件已发送")
            except Exception as e:
                print("告警发送失败:", e)
        sys.exit(1)
    print("SLO_PASS exit0"); sys.exit(0)

if __name__ == "__main__":
    main()
