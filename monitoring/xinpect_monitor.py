#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
煋鉴服务监控脚本 v2.0 - 增强版
每 5 分钟运行一次，检测异常后自动修复

功能：
  1. 服务状态检查（systemctl is-active）
  2. 端口监听检查（ss -tlnp）
  3. HTTP 健康端点探测（容错：JSON/HTML 均支持）
  4. 异常自动修复（systemctl restart + 冷却期保护）
  5. 告警生成（修复失败时写 health_alert.json）
"""

import json
import logging
import os
import re
import subprocess
import time
import urllib.request
from datetime import datetime
from pathlib import Path

# ===== 日志配置 =====
LOG_DIR = Path("/opt/xinpect-website/monitoring")
LOG_DIR.mkdir(parents=True, exist_ok=True)
STATUS_FILE = LOG_DIR / "status.json"
ALERT_DIR = LOG_DIR / "alerts"
ALERT_DIR.mkdir(parents=True, exist_ok=True)
HEAL_LOG = LOG_DIR / "heal.log"
HEAL_STATE = LOG_DIR / "heal_state.json"
HEAL_ALERT = LOG_DIR / "health_alert.json"

logging.basicConfig(
    filename=str(LOG_DIR / "monitor.log"),
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# ===== 服务配置 =====
SERVICES = {
    "xinpect-website": {"port": 8621, "health": "http://127.0.0.1:8621/health"},
    "xinpect-scanner-green": {"port": 8620, "health": "http://127.0.0.1:8620/health"},
    "xinpect-scanner-blue": {"port": 8622, "health": "http://127.0.0.1:8622/health"},
    "pdf-pro": {"port": 8630, "health": "http://127.0.0.1:8630/health"},
    "xinpect-pay": {"port": 8765, "health": "http://127.0.0.1:8765/"},
}

# ===== 自动修复配置 =====
AUTO_HEAL = True
HEAL_COOLDOWN = 300  # 同一服务两次修复间隔至少 5 分钟


# ===== 日志函数 =====
def log(msg: str, level: str = "INFO"):
    """写日志"""
    logging.getLogger().log(getattr(logging, level.upper(), logging.INFO), msg)


# ===== 自动修复 =====
def load_heal_state() -> dict:
    """加载修复历史"""
    try:
        if HEAL_STATE.exists():
            with open(HEAL_STATE) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_heal_state(state: dict):
    """持久化修复历史"""
    try:
        with open(HEAL_STATE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass


def heal_log(msg: str):
    """写入修复日志"""
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(HEAL_LOG, "a") as f:
            f.write(f"[{ts}] {msg}\n")
        # 保留最近 500 行
        try:
            with open(HEAL_LOG) as f:
                lines = f.readlines()
            if len(lines) > 500:
                with open(HEAL_LOG, "w") as f:
                    f.writelines(lines[-500:])
        except Exception:
            pass
    except Exception:
        pass


def try_heal_service(service_name: str, port: int) -> dict:
    """
    尝试修复指定服务
    返回: {"success": bool, "action": str, "detail": str}
    """
    state = load_heal_state()
    now = time.time()
    last_heal = state.get(service_name, 0)

    # 冷却期检查
    if now - last_heal < HEAL_COOLDOWN:
        remaining = int(HEAL_COOLDOWN - (now - last_heal))
        return {"success": False, "action": "cooldown", "detail": f"冷却中，还剩{remaining}秒"}

    state[service_name] = now
    save_heal_state(state)

    heal_log(f"[HEAL_START] {service_name} port={port}")

    # Step 1: 记录当前状态
    try:
        r = subprocess.run(
            ["systemctl", "is-active", service_name],
            capture_output=True, text=True, timeout=10
        )
        was_status = r.stdout.strip()
    except Exception:
        was_status = "unknown"

    heal_log(f"[HEAL_RESTART] {service_name} (was: {was_status})")

    # Step 2: 重启服务
    try:
        r = subprocess.run(
            ["sudo", "systemctl", "restart", service_name],
            capture_output=True, text=True, timeout=30
        )
        if r.returncode != 0:
            heal_log(f"[HEAL_FAIL] {service_name} restart failed: {r.stderr[:200]}")
            return {"success": False, "action": "restart_failed", "detail": r.stderr[:200]}
    except Exception as e:
        heal_log(f"[HEAL_ERROR] {service_name}: {e}")
        return {"success": False, "action": "error", "detail": str(e)}

    # Step 3: 等待恢复（最多 20 秒）
    time.sleep(3)
    for attempt in range(6):
        try:
            # 检查服务状态
            r = subprocess.run(
                ["systemctl", "is-active", service_name],
                capture_output=True, text=True, timeout=5
            )
            if r.stdout.strip() != "active":
                time.sleep(2)
                continue

            # 检查端口
            r2 = subprocess.run(
                ["ss", "-tlnp"],
                capture_output=True, text=True, timeout=5
            )
            if f":{port} " in r2.stdout or f":{port}\t" in r2.stdout:
                elapsed = 3 + attempt * 2
                heal_log(f"[HEAL_OK] {service_name} 恢复成功 ({elapsed}秒)")
                return {"success": True, "action": "restart_ok", "detail": f"重启后{elapsed}秒恢复"}
        except Exception:
            pass
        time.sleep(2)

    # Step 4: 最终状态
    try:
        r = subprocess.run(
            ["systemctl", "is-active", service_name],
            capture_output=True, text=True, timeout=5
        )
        final = r.stdout.strip()
    except Exception:
        final = "unknown"

    heal_log(f"[HEAL_FAIL] {service_name} 修复后仍未恢复: {final}")
    return {"success": False, "action": "restart_no_recovery", "detail": f"重启后状态仍为 {final}"}


def run_auto_heal(unhealthy_services: dict) -> list:
    """对异常服务执行自动修复"""
    results = []

    for svc_name, svc_result in unhealthy_services.items():
        config = SERVICES.get(svc_name, {})
        port = config.get("port", 0)

        reason = svc_result.get("message", "状态异常")
        if not config.get("auto_heal", True):
            heal_log(f"[SKIP] {svc_name} 不在自动修复范围")
            continue
        heal_log(f"[CHECK] {svc_name} 异常: {reason}，尝试修复")

        result = try_heal_service(svc_name, port)
        result["service"] = svc_name
        result["reason"] = reason
        result["port"] = port
        results.append(result)

        heal_log(f"[RESULT] {svc_name}: success={result['success']} action={result['action']}")

    return results


# ===== 核心检查函数 =====
def check_service(name: str, config: dict) -> dict:
    """检查单个服务状态"""
    result = {"status": "ok", "port_alive": False, "message": ""}

    # 1. 服务状态
    try:
        r = subprocess.run(
            ["systemctl", "is-active", name],
            capture_output=True, text=True, timeout=5
        )
        if r.stdout.strip() != "active":
            result["status"] = "inactive"
            result["message"] = f"服务状态: {r.stdout.strip()}"
    except Exception as e:
        result["status"] = "unknown"
        result["message"] = f"检查失败: {str(e)[:50]}"

    # 2. 端口监听
    try:
        r = subprocess.run(
            ["ss", "-tlnp"],
            capture_output=True, text=True, timeout=5
        )
        port_str = f":{config['port']}"
        if port_str in r.stdout:
            result["port_alive"] = True
        elif result["status"] == "ok":
            result["status"] = "port_missing"
            result["message"] = f"端口 {config['port']} 未监听"
    except Exception:
        pass

    # 3. HTTP 健康检查
    if "health" in config:
        try:
            req = urllib.request.Request(config["health"], method="GET")
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=10) as resp:
                elapsed_ms = round((time.time() - t0) * 1000)
                body = resp.read().decode()
                result["response_ms"] = elapsed_ms

                # 尝试 JSON 解析
                try:
                    data = json.loads(body)
                    if data.get("status") not in ("ok", "healthy"):
                        result["status"] = "degraded"
                        result["message"] = f"健康检查: {data.get('status', 'unknown')} ({elapsed_ms}ms)"
                except (json.JSONDecodeError, ValueError):
                    # 非 JSON 响应（如 HTML），只检查 HTTP 状态码
                    if resp.status != 200:
                        result["status"] = "degraded"
                        result["message"] = f"HTTP {resp.status} ({elapsed_ms}ms)"

                if elapsed_ms > 5000:
                    result["status"] = "degraded"
                    result["message"] = f"响应过慢: {elapsed_ms}ms"
        except Exception as e:
            result["status"] = "degraded"
            result["message"] = f"HTTP 检查失败: {str(e)[:80]}"

    return result


def check_disk() -> dict:
    """检查磁盘使用率"""
    try:
        r = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=5)
        lines = r.stdout.strip().split("\n")
        if len(lines) >= 2:
            parts = lines[1].split()
            usage = int(parts[4].replace("%", ""))
            return {"usage": usage, "status": "warning" if usage > 85 else "ok"}
    except Exception:
        pass
    return {"usage": -1, "status": "unknown"}


def check_memory() -> dict:
    """检查内存使用"""
    try:
        with open("/proc/meminfo") as f:
            info = {}
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    info[parts[0].rstrip(":")] = int(parts[1])
            total = info.get("MemTotal", 0)
            available = info.get("MemAvailable", 0)
            if total > 0:
                usage_pct = round((total - available) / total * 100, 1)
                return {"usage_pct": usage_pct, "available_mb": available // 1024, "status": "ok"}
    except Exception:
        pass
    return {"usage_pct": -1, "available_mb": 0, "status": "unknown"}


def check_load() -> dict:
    """检查系统负载"""
    try:
        r = subprocess.run(["cat", "/proc/loadavg"], capture_output=True, text=True, timeout=5)
        parts = r.stdout.strip().split()
        load1 = float(parts[0])
        load5 = float(parts[1])
        load15 = float(parts[2])
        return {"load1": load1, "load5": load5, "load15": load15, "status": "ok"}
    except Exception:
        pass
    return {"load1": 0, "load5": 0, "load15": 0, "status": "unknown"}


def generate_alert(service_name: str, status: str, message: str):
    """生成告警"""
    alert_id = f"{service_name}_{int(time.time())}"
    alert = {
        "id": alert_id,
        "service": service_name,
        "status": status,
        "message": message,
        "timestamp": datetime.now().isoformat(),
    }
    try:
        with open(ALERT_DIR / f"{alert_id}.json", "w") as f:
            json.dump(alert, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ===== 主流程 =====
def main():
    log("监控检查开始")

    results = {}
    for name, config in SERVICES.items():
        results[name] = check_service(name, config)

    # 收集需要修复的服务
    unhealthy = {}
    for name, r in results.items():
        if r.get("status") != "ok" or not r.get("port_alive", True):
            unhealthy[name] = r

    # ===== 自动修复 =====
    heal_results = []
    if unhealthy and AUTO_HEAL:
        heal_results = run_auto_heal(unhealthy)

        # 修复成功后更新状态
        for hr in heal_results:
            if hr.get("success"):
                svc = hr["service"]
                if svc in results:
                    results[svc]["status"] = "ok"
                    results[svc]["port_alive"] = True
                    results[svc]["healed"] = hr.get("detail", "")

    # 写状态文件
    status_data = {
        "timestamp": datetime.now().isoformat(),
        "services": results,
        "disk": check_disk(),
        "memory": check_memory(),
        "load": check_load(),
        "heal_results": heal_results if heal_results else None,
    }

    total_count = len(results)
    healthy_count = sum(1 for s in results.values() if s.get("status") == "ok" and s.get("port_alive", True))
    status_data["overall"] = "healthy" if healthy_count == total_count else "degraded"

    try:
        with open(STATUS_FILE, "w") as f:
            json.dump(status_data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    # 异常告警 + 日志
    for name, r in results.items():
        if r.get("status") != "ok":
            log(f"服务 {name} 异常: {r.get('message', r['status'])}", "WARN")
            generate_alert(name, r["status"], r.get("message", "服务异常"))

    # 汇总日志
    response_times = [
        r.get("response_ms", -1) for r in results.values()
        if r.get("response_ms", -1) > 0
    ]
    avg_ms = round(sum(response_times) / len(response_times)) if response_times else 0

    heal_msg = ""
    if heal_results:
        healed = sum(1 for h in heal_results if h.get("success"))
        failed = sum(1 for h in heal_results if not h.get("success"))
        heal_msg = f", 自动修复: {healed}成功/{failed}失败"

    log(
        f"监控检查完成: {healthy_count}/{total_count} 健康, "
        f"平均响应 {avg_ms}ms, overall={status_data['overall']}{heal_msg}"
    )

    # 修复失败写告警文件（供 scan_channel_monitor 读取）
    failed_heals = [h for h in heal_results if not h.get("success")]
    if failed_heals:
        try:
            alert = {
                "time": datetime.now().isoformat(),
                "failed_heals": failed_heals,
            }
            with open(HEAL_ALERT, "w") as f:
                json.dump(alert, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    elif HEAL_ALERT.exists():
        # 没有失败的了，清除旧告
        try:
            HEAL_ALERT.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    main()
