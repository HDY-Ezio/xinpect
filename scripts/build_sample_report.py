#!/usr/bin/env python3
"""用生产扫描器真跑一段演示代码，产出报告样例的唯一事实源。

在生产运行（会重写同目录 sample_report.json，改后必须重签基线）：
  sudo bash -c 'set -a; . /etc/xinpect/website.env; set +a; python3 scripts/build_sample_report.py'

不写数据库、不走试扫路由、不消耗访客额度、不产生埋点。
输出 scripts/sample_report.json，页面只从这里取数，不许手抄数字。
"""
import hashlib
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, "/opt/xinpect-website")
from modules.scanner import call_scanner  # noqa: E402

# 演示用代码：刻意含有几类常见缺陷，全部由我们自己编写，不涉及任何用户代码。
SAMPLE_CODE = '''import hashlib
import os
import sqlite3
from flask import Flask, request

app = Flask(__name__)
DB_PASSWORD = "demo_secret_123"

def get_user(name):
    conn = sqlite3.connect("demo.db")
    sql = "SELECT * FROM users WHERE name = '" + name + "'"
    return conn.execute(sql).fetchall()

def make_token(payload):
    return hashlib.md5(payload.encode()).hexdigest()

def run_task(cmd):
    os.system("sh -c " + cmd)

@app.route("/user")
def user():
    try:
        return str(get_user(request.args.get("name")))
    except:
        pass
'''

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_report.json")


def main():
    files = {"demo_app.py": SAMPLE_CODE}
    brains = ["1", "2", "4", "5", "6"]  # 与 /api/try-scan 完全同一组引擎
    raw = call_scanner(
        files, brains,
        options={"language": "python", "scan_mode": "basic", "is_vip": False},
    )
    issues = raw.get("issues") or []
    kept = []
    for i in issues:
        kept.append({
            "rule_id": i.get("rule_id") or "",
            "title": i.get("title") or "",
            "severity": i.get("severity") or "info",
            "severity_label": i.get("severity_label") or "",
            "brain_name": i.get("brain_name") or "",
            "file": i.get("file") or "",
            "line": i.get("line") or 0,
            "description": i.get("description") or "",
            "suggestion": i.get("suggestion") or "",
            "code_snippet": i.get("code_snippet") or "",
        })
    sev = {}
    for i in kept:
        k = i["severity"].lower()
        sev[k] = sev.get(k, 0) + 1
    payload = {
        "schema": 1,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": "生产扫描器真跑（modules.scanner.call_scanner），未经人工改写",
        "scanner_version": raw.get("version") or "",
        "scan_time_seconds": raw.get("scan_time") or 0,
        "sample_file": "demo_app.py",
        "sample_language": "python",
        "sample_code": SAMPLE_CODE,
        "sample_code_sha256": hashlib.sha256(SAMPLE_CODE.encode()).hexdigest(),
        "scan_mode": "basic",
        "brains": brains,
        "total_issues": len(kept),
        "severity_breakdown": sev,
        "issues": kept,
        "note": "免费试扫只跑规范层与安全引擎，本样例与试扫同口径，属初筛，不等于完整报告。",
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print("scanner_version=", payload["scanner_version"])
    print("scan_time=", payload["scan_time_seconds"])
    print("total_issues=", payload["total_issues"])
    print("severity=", sev)
    for i in kept:
        print("  ", i["severity"], i["rule_id"], i["title"], "line", i["line"])
    print("OUT", OUT)


if __name__ == "__main__":
    main()
