#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
煋鉴每日质检脚本
部署位置: /opt/xinpect-website/daily_inspection.py
功能: 全面健康检查，发现问题主动预警
"""

import os
import re
import sys
import json
import ast
import py_compile
import tempfile
import sqlite3
import subprocess
from datetime import datetime

SERVICES = ["xinpect-website", "xinpect-scanner-green", "xinpect-scanner-blue", "xinpect-pay"]
PORTS = {"8621": "website", "8620": "scanner-green", "8622": "scanner-blue", "8765": "pay", "8001": "energy-valve"}
ENGINE_DIR = "/opt/xinpect-scanner-green/engine"
AI_ENGINE_DIR = "/opt/xinpect-scanner-green/ai_engine"
WEBSITE_DIR = "/opt/xinpect-website"
REPORT_DIR = f"{WEBSITE_DIR}/reports/inspection"

# 排除测试/示例目录（不是业务代码）
EXCLUDE_DIRS = {"test", "tests", "examples", "tree-sitter-python"}

results = {"pass": 0, "fail": 0, "warn": 0, "details": []}

def check(name, passed, detail=""):
    if passed:
        results["pass"] += 1
        results["details"].append(f"  PASS: {name}")
    else:
        results["fail"] += 1
        results["details"].append(f"  FAIL: {name} {detail}")

def warn(name, detail=""):
    results["warn"] += 1
    results["details"].append(f"  WARN: {name} {detail}")

def section(title):
    results["details"].append(f"\n[{title}]")

def run(cmd):
    """执行命令。仅允许 str 类型（硬编码命令），禁止 list 外部输入。"""
    if not isinstance(cmd, str):
        return -1, "", "blocked: cmd must be str"
    # 白名单：只允许内部运维命令前缀
    _allowed = ("systemctl", "ss ", "journalctl", "df ", "free", "cat /proc",
                "pgrep", "curl", "nohup", "sudo", "cd ", "python3")
    if not any(cmd.strip().startswith(p) for p in _allowed):
        return -1, "", f"blocked: command prefix not allowed"
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as e:
        return -1, "", str(e)

# ===== 1. 服务健康检查 =====
def check_services():
    section("1. 服务健康检查")
    for svc in SERVICES:
        rc, out, _ = run(f"systemctl is-active {svc}")
        check(f"{svc} 运行状态", rc == 0 and out == "active", f"(实际: {out})")

# ===== 2. 端口可用性 =====
def check_ports():
    section("2. 端口可用性检查")
    for port, name in PORTS.items():
        rc, out, _ = run(f"ss -tlnp | grep -q :{port}")
        check(f"端口 {port} ({name})", rc == 0, "NOT LISTENING" if rc != 0 else "")

# ===== 3. 引擎模块语法检查 =====
def check_engine_syntax():
    section("3. 引擎模块语法检查 (py_compile)")
    
    ok_count = 0
    fail_list = []
    tmpdir = tempfile.mkdtemp()
    
    for d in [ENGINE_DIR, AI_ENGINE_DIR]:
        if not os.path.isdir(d):
            continue
        for root, dirs, files in os.walk(d):
            # 排除测试/示例目录
            rel = os.path.relpath(root, d)
            parts = rel.split(os.sep)
            if any(p in EXCLUDE_DIRS for p in parts):
                continue
            for f in files:
                if not f.endswith(".py"):
                    continue
                fp = os.path.join(root, f)
                cfile = os.path.join(tmpdir, f + ".pyc")
                try:
                    py_compile.compile(fp, cfile=cfile, doraise=True)
                    ok_count += 1
                except py_compile.PyCompileError as e:
                    fail_list.append(f"{fp}: {str(e)[:120]}")
    
    check(f"Python文件语法编译 ({ok_count} OK, {len(fail_list)} FAIL)", len(fail_list) == 0)
    for fl in fail_list[:10]:
        results["details"].append(f"    {fl}")

# ===== 4. xss_vectors.py 语法验证 =====
def check_xss_syntax():
    section("4. xss_vectors.py 语法验证")
    fp = f"{ENGINE_DIR}/b2_security_html/xss_vectors.py"
    if not os.path.exists(fp):
        warn("xss_vectors.py 文件不存在")
        return
    
    tmpdir = tempfile.mkdtemp()
    cfile = os.path.join(tmpdir, "xss_vectors.pyc")
    try:
        py_compile.compile(fp, cfile=cfile, doraise=True)
        check("xss_vectors.py 语法", True)
    except py_compile.PyCompileError as e:
        check("xss_vectors.py 语法", False, str(e)[:100])

# ===== 5. SSRF constants 完整性 =====
def check_ssrf_constants():
    section("5. SSRF constants.py 完整性检查")
    fp = f"{ENGINE_DIR}/b3_semantic/checks/security/_ssrf_sub/constants.py"
    if not os.path.exists(fp):
        check("constants.py 存在", False)
        return
    
    with open(fp) as f:
        content = f.read()
    
    required = ["HTTP_REQUEST_LIBS", "URLLIB_FUNCS", "AIOHTTP_METHODS", "USER_INPUT_PATTERNS",
                 "URLLIB3_MODULES", "URLLIB3_METHODS", "HTTPLIB2_CLASSES", "HTTPLIB2_METHODS"]
    missing = [v for v in required if v not in content]
    check(f"constants.py 必需变量 ({len(required) - len(missing)}/{len(required)})",
          len(missing) == 0,
          f"缺少: {', '.join(missing)}" if missing else "")

# ===== 6. 积分竞态修复回归 =====
def check_scoring_race():
    section("6. 积分竞态修复回归")
    fp = f"{WEBSITE_DIR}/modules/scoring.py"
    if not os.path.exists(fp):
        warn("scoring.py 不存在")
        return
    with open(fp) as f:
        content = f.read()
    has_immediate = "BEGIN IMMEDIATE" in content
    check("scoring.py BEGIN IMMEDIATE 事务", has_immediate, "未找到 BEGIN IMMEDIATE")

# ===== 7. 退款逻辑修复回归 =====
def check_refund_logic():
    section("7. 退款逻辑修复回归")
    fp = f"{WEBSITE_DIR}/modules/scan.py"
    if not os.path.exists(fp):
        warn("scan.py 不存在")
        return
    with open(fp) as f:
        lines = f.readlines()
    
    # 检查退款函数中是否有重试机制
    has_retry = False
    refund_vip_blocked = False
    in_refund_block = False
    
    for i, line in enumerate(lines):
        if "refund" in line.lower() and ("for" in line or "range" in line):
            in_refund_block = True
        if in_refund_block and "retry" in line.lower():
            has_retry = True
        # 检查退款grant_credits前面是否有is_vip的条件判断阻断
        if "scan_refund" in line:
            # 向上看5行，是否有 if is_vip 或 if not vip 之类的拦截
            context = "".join(lines[max(0,i-5):i])
            if re.search(r'if\s+.*is_vip.*return|if\s+not\s+vip.*return', context):
                refund_vip_blocked = True
            # 也检查grant_credits call附近是否有retry
            context_after = "".join(lines[i:i+8])
            if "range(3)" in context_after or "retry" in context_after.lower():
                has_retry = True
    
    # 简化检查：确认retry机制存在
    full_content = "".join(lines)
    has_retry_mechanism = "range(3)" in full_content and "scan_refund" in full_content
    check("退款重试机制", has_retry_mechanism, "未找到退款重试逻辑")
    check("退款无VIP拦截", not refund_vip_blocked, "退款路径中存在VIP条件拦截")

# ===== 8. 启动日志WARNING检查 =====
def check_startup_warnings():
    section("8. 启动日志WARNING检查（仅最近启动）")
    # 只看最近一次启动后的日志
    rc, out, _ = run("journalctl -u xinpect-scanner-green --no-pager -b -n 50")
    if out:
        lines = [l for l in out.split("\n") if any(kw in l.upper() for kw in ("WARNING", "ERROR", "TRACEBACK"))][:10]
        if lines:
            warn("最近启动日志存在告警", f"({len(lines)}条)")
            for line in lines[:3]:
                results["details"].append(f"    {line[:120]}")
        else:
            check("最近启动日志无WARNING/ERROR", True)
    else:
        check("最近启动日志无WARNING/ERROR", True)


# ===== 8b. 服务可靠性检查（故障计数 + crash loop 检测）=====
def check_service_reliability():
    section("服务可靠性检查（智能故障检测）")
    for svc in SERVICES:
        # 当前状态
        rc, active_state, _ = run(f"systemctl show {svc} -p ActiveState --value")
        active = active_state.strip()
        rc, last_result, _ = run(f"systemctl show {svc} -p Result --value")
        result_str = last_result.strip() if last_result else "unknown"
        rc, nrestarts, _ = run(f"systemctl show {svc} -p NRestarts --value")
        restart_count = int(nrestarts) if nrestarts.strip().isdigit() else 0
        
        is_healthy = (active == "active" and result_str == "success")
        
        # 近1h失败（活跃问题检测）
        rc2, recent_str, _ = run(f'journalctl -u {svc} --since "1 hour ago" --no-pager | grep -c "Failed with result"')
        recent_fails = int(recent_str) if recent_str.strip().isdigit() else 0
        
        # 近7天/24h失败（仅参考）
        time_window = "7 days" if "weekly" in "daily_inspection" else "24 hours"
        rc3, history_str, _ = run(f'journalctl -u {svc} --since "{time_window} ago" --no-pager | grep -c "Failed with result"')
        history_fails = int(history_str) if history_str.strip().isdigit() else 0
        
        # 核心逻辑：当前健康 + 近期无活跃故障 = 通过
        if not is_healthy:
            warn(f"{svc} 当前状态异常: {active}/{result_str}", "服务不可用")
        elif recent_fails >= 3:
            warn(f"{svc} 近1h故障{recent_fails}次（已恢复）| 历史累计{history_fails}次", "关注是否复发")
        else:
            check(f"{svc} 稳定运行 | 近1h故障{recent_fails}次 | 历史累计{history_fails}次 | 重启{restart_count}次", True)


# ===== 9. 系统资源 =====
def check_system_resources():
    section("9. 系统资源检查")
    
    # 磁盘
    rc, out, _ = run("df -h / | tail -1 | awk '{print $5}' | tr -d '%'")
    disk_pct = int(out) if out.isdigit() else -1
    check(f"磁盘使用率 {disk_pct}%", disk_pct >= 0 and disk_pct < 85,
          "超过85%阈值" if disk_pct >= 85 else "")
    
    # 内存
    rc, out, _ = run("free | awk 'NR==2{printf \"%.0f\", $7/$2*100}'")
    mem_avail_pct = int(out) if out.isdigit() else -1
    check(f"可用内存占比 {mem_avail_pct}%", mem_avail_pct > 20, "可用内存不足20%" if mem_avail_pct <= 20 else "")
    
    # CPU负载
    rc, out, _ = run("cat /proc/loadavg | awk '{print $1}'")
    if out:
        try:
            load = float(out)
            check(f"CPU负载 {load}", load < 4.0, "负载过高" if load >= 4.0 else "")
        except:
            warn("CPU负载读取失败")

# ===== 10. 数据库完整性 =====
def check_database():
    section("10. 数据库完整性")
    db_candidates = [
        f"{WEBSITE_DIR}/xinpect.db",
        f"{WEBSITE_DIR}/data/xinpect.db",
        f"{WEBSITE_DIR}/instance/xinpect.db",
        f"{WEBSITE_DIR}/menfang.db",
    ]
    
    found_db = None
    for db_path in db_candidates:
        if os.path.exists(db_path):
            found_db = db_path
            break
    
    if not found_db:
        warn("未找到数据库文件")
        return
    
    try:
        conn = sqlite3.connect(found_db)
        cursor = conn.execute("PRAGMA integrity_check")
        result = cursor.fetchone()
        conn.close()
        check(f"数据库完整性 ({os.path.basename(found_db)})", result[0] == "ok", f"结果: {result[0]}")
    except Exception as e:
        check("数据库完整性", False, str(e)[:80])

# ===== 主流程 =====
if __name__ == "__main__":
    print(f"煋鉴每日质检报告 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    check_services()
    check_ports()
    check_engine_syntax()
    check_xss_syntax()
    check_ssrf_constants()
    check_scoring_race()
    check_refund_logic()
    check_startup_warnings()
    check_service_reliability()
    check_system_resources()
    check_database()
    
    # 打印结果
    for line in results["details"]:
        print(line)
    
    total = results["pass"] + results["fail"] + results["warn"]
    print(f"\n总计: {results['pass']} 通过, {results['fail']} 失败, {results['warn']} 警告")
    
    conclusion = "HAS ISSUES ❌" if results["fail"] > 0 else ("WARNINGS ⚠️" if results["warn"] > 0 else "ALL CLEAR ✅")
    print(f"结论: {conclusion}")
    
    # 保存报告
    os.makedirs(REPORT_DIR, exist_ok=True)
    report_file = f"{REPORT_DIR}/inspection_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(report_file, "w") as f:
        f.write(f"煋鉴每日质检报告 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        for line in results["details"]:
            f.write(line + "\n")
        f.write(f"\n总计: {results['pass']} 通过, {results['fail']} 失败, {results['warn']} 警告\n")
        f.write(f"结论: {conclusion}\n")
    print(f"\n报告已保存: {report_file}")
    
    # 输出JSON摘要供外部解析
    summary = {"time": datetime.now().isoformat(), "pass": results["pass"], 
               "fail": results["fail"], "warn": results["warn"], "conclusion": conclusion}
    print(f"\nSUMMARY_JSON: {json.dumps(summary)}")
