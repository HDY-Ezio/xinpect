#!/usr/bin/env python3
"""
煋鉴每周深度巡检脚本
部署位置: /opt/xinpect-website/weekly_inspection.py
"""

import os
import json
import sqlite3
import subprocess
from datetime import datetime, timedelta

WEBSITE_DIR = "/opt/xinpect-website"
SERVICES = ["xinpect-website", "xinpect-scanner-green", "xinpect-scanner-blue", "xinpect-pay"]
REPORT_DIR = f"{WEBSITE_DIR}/reports/weekly"

results = {"pass": 0, "fail": 0, "warn": 0, "details": []}

def section(title):
    results["details"].append(f"\n[{title}]")

def check(name, passed, detail=""):
    if passed:
        results["pass"] += 1
        results["details"].append(f"  PASS: {name} {detail}")
    else:
        results["fail"] += 1
        results["details"].append(f"  FAIL: {name} {detail}")

def warn(name, detail=""):
    results["warn"] += 1
    results["details"].append(f"  WARN: {name} {detail}")

def run(cmd):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as e:
        return -1, "", str(e)

def read_json_safe(filepath):
    try:
        if os.path.exists(filepath):
            with open(filepath) as f:
                return json.load(f)
    except:
        pass
    return None

# ===== 11. 资源趋势 =====
def check_resource_trends():
    section("11. 资源趋势")
    rc, out, _ = run("df -h / | tail -1 | awk '{print $5}' | tr -d '%'"  )
    current_disk = int(out) if out.strip().isdigit() else -1
    
    trend_file = f"{WEBSITE_DIR}/data/disk_trend.json"
    history = read_json_safe(trend_file) or []
    
    if history and current_disk >= 0:
        last = history[-1]
        growth = current_disk - last.get("usage_pct", current_disk)
        if growth > 5:
            warn(f"磁盘周增长 +{growth}%（{last.get('usage_pct', '?')}% -> {current_disk}%）", "增长过快")
        elif growth > 0:
            check(f"磁盘周增长 +{growth}%（{last.get('usage_pct', '?')}% -> {current_disk}%）", True, "正常")
        elif growth == 0:
            check(f"磁盘使用率 {current_disk}%（无增长）", True)
        else:
            check(f"磁盘使用率 {current_disk}%（下降 {growth}%）", True, "清理有效")
        
        if growth > 0:
            remaining = 100 - current_disk
            days_left = round(remaining / growth * 7)
            if days_left < 30:
                warn(f"按当前增速，磁盘约 {days_left} 天后满载", "需要清理或扩容")
            else:
                check(f"磁盘预计可用 {days_left} 天（约 {round(days_left/30, 1)} 个月）", True)
    else:
        check(f"当前磁盘使用率 {current_disk}%", current_disk < 85, "" if current_disk < 85 else "超85%")
    
    history.append({"date": datetime.now().strftime("%Y-%m-%d"), "usage_pct": current_disk})
    history = history[-12:]
    os.makedirs(os.path.dirname(trend_file), exist_ok=True)
    with open(trend_file, "w") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    
    rc, out, _ = run("free | awk 'NR==2{printf \"%.0f\", $7/$2*100}'")
    mem_avail = int(out) if out.strip().isdigit() else -1
    check(f"当前可用内存 {mem_avail}%", mem_avail > 20, "" if mem_avail > 20 else "可用内存不足")

# ===== 12. 引擎演进 =====
def check_engine_evolution():
    section("12. 引擎演进")
    rc, out, _ = run("find /opt/xinpect-scanner-green/engine -name '*.py' | wc -l")
    engine_files = int(out) if out.strip().isdigit() else 0
    
    trend_file = f"{WEBSITE_DIR}/data/engine_trend.json"
    history = read_json_safe(trend_file) or []
    
    if history:
        last = history[-1]
        delta = engine_files - last.get("engine_files", 0)
        if delta != 0:
            sign = "+" if delta > 0 else ""
            check(f"引擎文件数 {engine_files}（周变化 {sign}{delta}）", True)
        else:
            check(f"引擎文件数 {engine_files}（无变化）", True)
    else:
        check(f"引擎文件数 {engine_files}", True)
    
    history.append({"date": datetime.now().strftime("%Y-%m-%d"), "engine_files": engine_files})
    history = history[-12:]
    os.makedirs(os.path.dirname(trend_file), exist_ok=True)
    with open(trend_file, "w") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

# ===== 13. 业务运营 =====
def check_business_ops():
    section("13. 业务运营")
    db_path = f"{WEBSITE_DIR}/xinpect.db"
    if not os.path.exists(db_path):
        warn("数据库文件不存在")
        return
    
    try:
        conn = sqlite3.connect(db_path, timeout=10)
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        
        # 新用户
        try:
            cnt = conn.execute("SELECT COUNT(*) FROM users WHERE created_at > ?", (week_ago,)).fetchone()[0]
            if cnt > 0:
                check(f"本周新注册用户 {cnt} 人", True)
            else:
                warn("本周无新注册用户")
        except:
            warn("无法查询用户注册数据")
        
        # 扫描次数
        try:
            cnt = conn.execute("SELECT COUNT(*) FROM scans WHERE created_at > ?", (week_ago,)).fetchone()[0]
            check(f"本周扫描次数 {cnt}", True)
        except:
            warn("无法查询扫描数据")
        
        # 付费用户
        try:
            rows = conn.execute(
                "SELECT COUNT(*) FROM users WHERE vip_expire_at > date('now')"
            ).fetchone()
            vip_count = rows[0] if rows else 0
            if vip_count > 0:
                check(f"有效付费用户 {vip_count} 人", True)
            else:
                warn("无有效付费用户记录")
        except:
            warn("无法查询付费用户数据")
        
        conn.close()
    except Exception as e:
        warn(f"数据库查询异常: {str(e)[:80]}")

# ===== 14. 竞品差距 =====
def check_competitive_gap():
    section("14. 竞品差距")
    
    key_modules = [
        ("PoC 验证模块", "/opt/xinpect-scanner-green/engine/poc_verification"),
        ("B14 业务逻辑检测", "/opt/xinpect-scanner-green/engine/b14_business_logic"),
        ("B16 业务逻辑安全", "/opt/xinpect-scanner-green/engine/b16_business_logic_security"),
        ("AI 增强引擎", "/opt/xinpect-scanner-green/engine/a1_ai_enhance"),
    ]
    
    for name, path in key_modules:
        exists = os.path.isdir(path)
        if exists:
            rc, out, _ = run(f"find {path} -name '*.py' | wc -l")
            cnt = int(out) if out.strip().isdigit() else 0
            check(f"{name}", True, f"({cnt} 个.py)")
        else:
            warn(f"{name} 目录不存在（待建设）")

# ===== 15. 系统健康趋势（优化版）=====
def check_system_trends():
    section("15. 系统健康趋势（近7天·按天分）")
    
    for svc in SERVICES:
        # 当前状态（核心判断依据）
        rc_a, active_st, _ = run(f"systemctl show {svc} -p ActiveState --value")
        active = active_st.strip()
        rc_r, result_val, _ = run(f"systemctl show {svc} -p Result --value")
        result_str = result_val.strip() if result_val else "unknown"
        is_healthy = (active == "active" and result_str == "success")
        
        # 近1h故障（活跃问题）
        rc, recent_str, _ = run(f"journalctl -u {svc} --since 1 hour ago --no-pager | grep -c Failed with result")
        recent_fails = int(recent_str.strip()) if recent_str.strip().isdigit() else 0
        
        # 7天总故障（仅参考）
        rc2, total_str, _ = run(f"journalctl -u {svc} --since 7 days ago --no-pager | grep -c Failed with result")
        total_fails = int(total_str.strip()) if total_str.strip().isdigit() else 0
        
        # systemd 重启次数
        rc3, nr, _ = run(f"systemctl show {svc} -p NRestarts --value")
        restarts = int(nr.strip()) if nr.strip().isdigit() else 0
        
        # 核心判断：当前健康 + 近1h无活跃故障 = 通过
        if not is_healthy:
            warn(f"{svc} 当前状态异常: {active}/{result_str}", "服务不可用")
        elif recent_fails >= 3:
            warn(f"{svc} 近1h故障{recent_fails}次（已恢复）| 7天累计{total_fails}次", "关注是否复发")
        else:
            check(f"{svc} 稳定运行 | 近1h故障{recent_fails}次 | 7天累计{total_fails}次 | 重启{restarts}次", True)
        
# ===== 主流程 =====
if __name__ == "__main__":
    print(f"煋鉴每周深度巡检 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    check_resource_trends()
    check_engine_evolution()
    check_business_ops()
    check_competitive_gap()
    check_system_trends()
    
    for line in results["details"]:
        print(line)
    
    print(f"\n总计: {results['pass']} 通过, {results['fail']} 失败, {results['warn']} 警告")
    conclusion = "HAS ISSUES" if results["fail"] > 0 else ("WARNINGS" if results["warn"] > 0 else "ALL CLEAR")
    print(f"结论: {conclusion}")
    
    os.makedirs(REPORT_DIR, exist_ok=True)
    rf = f"{REPORT_DIR}/weekly_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(rf, "w") as f:
        f.write(f"煋鉴每周深度巡检 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        for line in results["details"]:
            f.write(line + "\n")
        f.write(f"\n总计: {results['pass']} 通过, {results['fail']} 失败, {results['warn']} 警告\n结论: {conclusion}\n")
    print(f"报告: {rf}")
    
    summary = {"time": datetime.now().isoformat(), "pass": results["pass"],
               "fail": results["fail"], "warn": results["warn"], "conclusion": conclusion}
    print(f"\nSUMMARY_JSON: {json.dumps(summary)}")
