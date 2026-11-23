#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
煋鉴 · 生产对抗性自检（Golden-Sample Adversarial Regression）
- malicious：生产绿版必须检出，消息命中期望关键词；漏报即 FAIL
- clean：安全引擎(brain 2/8/9/10)不应报警，出现即误报
唯一文件名强制真实扫描，明细从共享库 result_json 轮询读取。漏报 -> exit 1 + 邮件告警。
"""
import json, os, sqlite3, sys, time, uuid, urllib.request, smtplib
from datetime import datetime
from email.mime.text import MIMEText

SCANNER = os.environ.get("XINPECT_SCANNER", "http://127.0.0.1:8620")
def _load_api_key():
    """凭据不入库：先看环境变量，再读仓库外的 /etc/xinpect/monitor.key。"""
    import os as _os
    key = _os.environ.get("XINPECT_API_KEY", "").strip()
    if not key:
        try:
            with open("/etc/xinpect/monitor.key", encoding="utf-8") as _f:
                key = _f.read().strip()
        except OSError:
            key = ""
    if not key:
        raise SystemExit(
            "缺少扫描器 API 凭据：设置环境变量 XINPECT_API_KEY，"
            "或把密钥写入 /etc/xinpect/monitor.key（权限 640 root:ubuntu）"
        )
    return key

API_KEY = _load_api_key()
DB = os.environ.get("XINPECT_DATA_DB", "/opt/xinpect-data/scan_results.db")
SAMPLES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden_samples.json")
STATE = "/opt/xinpect-website/monitoring/adversarial/state.json"
LOGDIR = "/opt/xinpect-website/monitoring/adversarial"
SECURITY_BRAINS = ("2", "8", "9", "10")

# 告警邮件（与 critical_path_monitor 同一通道）
ADMIN_EMAIL = "hdyabcd@163.com"
SMTP_SERVER, SMTP_PORT, SMTP_USER = "smtp.163.com", 465, "hdyabcd@163.com"
SMTP_PASS = os.environ.get("SMTP_PASSWORD", "")

EXT = {"py": ".py", "js": ".js", "java": ".java", "rs": ".rs", "go": ".go"}


def http_scan(files):
    body = json.dumps({"files": files}).encode()
    req = urllib.request.Request(
        SCANNER + "/scan/batch", data=body,
        headers={"X-API-Key": API_KEY, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def fetch_security_issues(scan_id, tries=24):
    """轮询共享库取该次扫描在安全引擎下的问题，返回消息列表。"""
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            db = sqlite3.connect(DB, timeout=5)
            row = db.execute("SELECT result_json FROM scan_results WHERE scan_id=?", (scan_id,)).fetchone()
            db.close()
            if row and row[0]:
                msgs = []
                for bid, blk in json.loads(row[0]).get("results", {}).items():
                    if bid in SECURITY_BRAINS:
                        for it in blk.get("issues", []):
                            msgs.append(str(it.get("message", "")))
                return msgs
        except Exception:
            pass
        time.sleep(0.5)
    return None  # 取不到明细


def load_state():
    try:
        with open(STATE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    """统一落盘出口：原子写 + 存储异常降级（原实现 except: pass 会让故障无声）。"""
    _root = "/opt/xinpect-website"
    if _root not in sys.path:
        sys.path.insert(0, _root)
    from monitoring.safe_write import write_json
    return write_json(STATE, state, label="对抗自检状态")


def should_alert(state, key, gap=3600):
    last = state.get(key)
    if not last:
        return True
    try:
        return (datetime.now() - datetime.fromisoformat(last)).total_seconds() > gap
    except Exception:
        return True


def send_alert(subject, body):
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = "[煋鉴P1告警] " + subject
        msg["From"] = SMTP_USER
        msg["To"] = ADMIN_EMAIL
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=30) as s:  # 2026-10-23 修复：加超时防挂死
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)
    except Exception as e:
        print("[ERROR] 告警邮件发送失败:", e)


def main():
    with open(SAMPLES) as f:
        data = json.load(f)
    tag = uuid.uuid4().hex[:8]  # 唯一前缀，确保不命中缓存

    files, meta = [], {}
    for s in data["malicious"]:
        fn = f"adv_{tag}_{s['id']}{EXT.get(s['lang'], '.txt')}"
        files.append({"filename": fn, "content": s["code"]})
        meta[fn] = ("MAL", s)
    for s in data["clean"]:
        fn = f"adv_{tag}_clean_{s['id']}{EXT.get(s['lang'], '.txt')}"
        files.append({"filename": fn, "content": s["code"]})
        meta[fn] = ("CLEAN", s)

    try:
        resp = http_scan(files)
    except Exception as e:
        print(f"[FAIL] 扫描服务不可用: {e}")
        return 2

    misses, falsepos, noresult = [], [], []
    for fr in resp.get("file_results", []):
        fn = fr["filename"]
        if fn not in meta:
            continue
        kind, sample = meta[fn]
        if fr.get("status") != "success":
            noresult.append((sample["id"], fr.get("error")))
            continue
        msgs = fetch_security_issues(fr["scan_id"])
        if msgs is None:
            noresult.append((sample["id"], "明细未取到"))
            continue
        if kind == "MAL":
            joined = " ".join(msgs).lower()
            if not any(k.lower() in joined for k in sample["expect"]):
                misses.append((sample["id"], sample["expect"], msgs[:3]))
        else:
            if msgs:
                falsepos.append((sample["id"], msgs[:3]))

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    n_mal, n_clean = len(data["malicious"]), len(data["clean"])
    ok = not misses and not falsepos and not noresult
    print(f"[{ts}] 对抗性自检: 恶意{n_mal} 干净{n_clean} | "
          f"漏报{len(misses)} 误报{len(falsepos)} 取数失败{len(noresult)} -> "
          f"{'PASS' if ok else 'FAIL'}")
    for m in misses:
        print("  [漏报]", m[0], "期望含", m[1], "实际安全消息", m[2])
    for m in falsepos:
        print("  [误报]", m[0], m[1])
    for m in noresult:
        print("  [取数失败]", m[0], m[1])

    # 追加简明日志
    try:
        with open(os.path.join(LOGDIR, "adversarial_selfcheck.log"), "a") as f:
            f.write(f"{ts} {'PASS' if ok else 'FAIL'} miss={len(misses)} fp={len(falsepos)} noresult={len(noresult)}\n")
    except Exception:
        pass

    if not ok:
        state = load_state()
        key = f"advfail:{sorted(x[0] for x in misses) or sorted(x[0] for x in noresult)}"
        if should_alert(state, key):
            lines = ["煋鉴生产对抗性自检未通过（%s）" % ts, ""]
            for m in misses:
                lines.append(f"漏报: {m[0]} 期望关键词{m[1]} 实际安全引擎消息={m[2]}")
            for m in falsepos:
                lines.append(f"误报: {m[0]} -> {m[1]}")
            for m in noresult:
                lines.append(f"取数失败: {m[0]} {m[1]}")
            lines += ["", f"扫描器: {SCANNER}", "这是'有洞没报'或'干净乱报'的强信号，请人工核查规则接线。"]
            send_alert("[P1]对抗性自检未过(漏报/误报,检测能力退化)", "\n".join(lines))
            state[key] = datetime.now().isoformat()
            save_state(state)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
