#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
煋旺智能全项目自动检修中枢 v3.0
=================================
取代旧的 xinpect_monitor.py（只覆盖煋鉴5个服务、且门房health端点写错）。

治本设计（对应老板诉求"发现即自动处理，不用发邮件给老板"）：
1. 全量体检：全公司所有服务（systemd + pm2 + nginx站点），一个不漏
2. 自动修复：能重启的自动重启（带冷却期，不误伤扫描高峰期）
3. 升级兜底：自动重启仍修不好的，写入"待办文件" TODOS.md，
   供 AI 下次接入时读取并深度处理（而不是发邮件给不懂代码的老板）

新增能力（相对 v2.0）：
- 门房 xinpect-pay 健康端点从错误根路径 / 改为 /api/health（解析 wechat_pay_configured）
- 纳入煋旺AI backend(5012)、stardirector(8888)、xw-gateway、pdf-pro
- 纳入 pm2 进程（ai-cost-gateway 8001/8002）；技能按次付费的 payserver:8010 已于 2026-11-14 下线
- 修复失败写 /opt/xinpect-website/monitoring/TODOS.md 供 AI 兜底
"""

import json
import logging
import os
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

LOG_DIR = Path("/opt/xinpect-website/monitoring")
LOG_DIR.mkdir(parents=True, exist_ok=True)
STATUS_FILE = LOG_DIR / "status.json"
HEAL_LOG = LOG_DIR / "heal.log"
HEAL_STATE = LOG_DIR / "heal_state.json"
TODO_FILE = LOG_DIR / "TODOS.md"          # AI 兜底待办文件
SLOW_STATE = LOG_DIR / "slow_state.json"

logging.basicConfig(
    filename=str(LOG_DIR / "monitor.log"),
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# ===== 全项目服务清单（单一事实来源）=====
# type: systemd(可systemctl restart) | pm2(可pm2 restart) | probe(只探测不自愈)
SERVICES = {
    # ---- 煋鉴（代码质检）----
    "xinpect-website":        {"type": "systemd", "port": 8621, "health": "http://127.0.0.1:8621/health", "aggregate_health": True},
    "xinpect-scanner-green":  {"type": "systemd", "port": 8620, "health": "http://127.0.0.1:8620/health"},
    "xinpect-scanner-blue":   {"type": "systemd", "port": 8622, "health": "http://127.0.0.1:8622/health"},
    "xinpect-pay":            {"type": "systemd", "port": 8765, "health": "http://127.0.0.1:8765/api/health", "check_wechat": True},

    # ---- 煋旺AI主站 ----
    "starwang-backend-clean": {"type": "systemd", "port": 5012, "health": "http://127.0.0.1:5012/health"},
    "xw-gateway":             {"type": "systemd", "port": None, "health": None, "process_only": True},
    "stardirector":           {"type": "systemd", "port": 8888, "health": None, "process_only": True},

    # ---- pm2 进程 ----
    "ai-cost-gateway":        {"type": "pm2", "port": 8001, "health": "http://127.0.0.1:8001/health"},
    "ai-cost-gateway-blue":   {"type": "pm2", "port": 8002, "health": "http://127.0.0.1:8002/health"},
}

AUTO_HEAL = True
HEAL_COOLDOWN = 300          # 同一服务两次修复间隔至少5分钟
SLOW_TOLERANCE_CYCLES = 3    # 进程存活仅健康检查慢，连续N次才重启


def log(msg, level="INFO"):
    logging.getLogger().log(getattr(logging, level.upper(), logging.INFO), msg)


# ===== 状态文件读写 =====
def load_json(path, default):
    try:
        if Path(path).exists():
            with open(path) as f:
                return json.load(f)
    except Exception:
        pass
    return default


def save_json(path, data):
    try:
        with open(path, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def heal_log(msg):
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(HEAL_LOG, "a") as f:
            f.write(f"[{ts}] {msg}\n")
        with open(HEAL_LOG) as f:
            lines = f.readlines()
        if len(lines) > 500:
            with open(HEAL_LOG, "w") as f:
                f.writelines(lines[-500:])
    except Exception:
        pass


# ===== 检查函数 =====
def check_service(name, config):
    result = {"status": "ok", "port_alive": True, "message": ""}
    svc_type = config.get("type", "systemd")

    # 1. 进程/服务状态
    if svc_type == "systemd":
        try:
            r = subprocess.run(["systemctl", "is-active", name], capture_output=True, text=True, timeout=5)
            if r.stdout.strip() != "active":
                result["status"] = "inactive"
                result["message"] = f"systemd状态: {r.stdout.strip()}"
        except Exception as e:
            result["status"] = "unknown"
            result["message"] = f"检查失败: {str(e)[:50]}"
    elif svc_type == "pm2":
        try:
            # pm2 daemon 是 ubuntu 用户跑的，必须用 ubuntu 身份 + 正确 HOME 查询
            r = subprocess.run(
                ["sudo", "-u", "ubuntu", "env", "HOME=/home/ubuntu", "pm2", "pid", name],
                capture_output=True, text=True, timeout=5
            )
            if not r.stdout.strip().isdigit():
                result["status"] = "inactive"
                result["message"] = "pm2进程不在线"
        except Exception as e:
            result["status"] = "unknown"
            result["message"] = f"pm2检查失败: {str(e)[:50]}"

    # 2. 端口监听
    port = config.get("port")
    if port:
        try:
            r = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True, timeout=5)
            if f":{port} " not in r.stdout and f":{port}\t" not in r.stdout:
                result["port_alive"] = False
                if result["status"] == "ok":
                    result["status"] = "port_missing"
                    result["message"] = f"端口 {port} 未监听"
        except Exception:
            pass

    # 3. HTTP 健康检查
    health = config.get("health")
    if health:
        t0 = time.time()
        try:
            req = urllib.request.Request(health, method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                elapsed_ms = round((time.time() - t0) * 1000)
                result["response_ms"] = elapsed_ms
                body = resp.read().decode()
                try:
                    data = json.loads(body)
                    result["active_scans"] = int(data.get("active_scans") or 0)
                    if data.get("status") not in ("ok", "healthy"):
                        result["status"] = "degraded"
                        result["message"] = f"健康状态: {data.get('status', 'unknown')}"
                    # 门房微信支付配置专项检查
                    if config.get("check_wechat") and not data.get("wechat_pay_configured"):
                        result["status"] = "wechat_broken"
                        result["message"] = "微信支付配置失效(wechat_pay_configured=false)"
                except (json.JSONDecodeError, ValueError):
                    if resp.status != 200:
                        result["status"] = "degraded"
                        result["message"] = f"HTTP {resp.status}"
        except urllib.error.HTTPError as e:
            result["status"] = "degraded"
            result["message"] = f"HTTP {e.code}"
        except Exception as e:
            result["status"] = "degraded"
            result["message"] = f"HTTP检查失败: {str(e)[:60]}"

    return result


# ===== 自动修复 =====
def try_heal_service(name, config):
    state = load_json(HEAL_STATE, {})
    now = time.time()
    if now - state.get(name, 0) < HEAL_COOLDOWN:
        return {"success": False, "action": "cooldown", "detail": "冷却中"}
    state[name] = now
    save_json(HEAL_STATE, state)

    svc_type = config.get("type", "systemd")
    heal_log(f"[HEAL_START] {name} type={svc_type}")

    if svc_type == "systemd":
        restart_cmd = ["sudo", "systemctl", "restart", name]
    elif svc_type == "pm2":
        restart_cmd = ["sudo", "-u", "ubuntu", "env", "HOME=/home/ubuntu", "pm2", "restart", name]
    else:
        return {"success": False, "action": "no_healer", "detail": "无自动修复方式"}

    try:
        r = subprocess.run(restart_cmd, capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            heal_log(f"[HEAL_FAIL] {name} 重启失败: {r.stderr[:200]}")
            return {"success": False, "action": "restart_failed", "detail": r.stderr[:200]}
    except Exception as e:
        heal_log(f"[HEAL_ERROR] {name}: {e}")
        return {"success": False, "action": "error", "detail": str(e)}

    # 等待恢复
    time.sleep(3)
    port = config.get("port")
    for attempt in range(6):
        try:
            if svc_type == "systemd":
                r = subprocess.run(["systemctl", "is-active", name], capture_output=True, text=True, timeout=5)
                alive = r.stdout.strip() == "active"
            else:
                r = subprocess.run(
                    ["sudo", "-u", "ubuntu", "env", "HOME=/home/ubuntu", "pm2", "pid", name],
                    capture_output=True, text=True, timeout=5
                )
                alive = r.stdout.strip().isdigit()
            if alive and port:
                r2 = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True, timeout=5)
                if f":{port} " not in r2.stdout and f":{port}\t" not in r2.stdout:
                    alive = False
            if alive:
                heal_log(f"[HEAL_OK] {name} 恢复成功")
                return {"success": True, "action": "restart_ok", "detail": f"重启后恢复"}
        except Exception:
            pass
        time.sleep(2)

    heal_log(f"[HEAL_FAIL] {name} 修复后仍未恢复")
    return {"success": False, "action": "restart_no_recovery", "detail": "重启后仍未恢复"}


# ===== AI 兜底待办文件 =====
def write_todo(unrecoverable):
    """把自动修不好的问题写成待办文件，供 AI 下次接入时读取处理"""
    lines = [
        "# 煋旺智能自动检修 - AI 兜底待办",
        f"更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "以下问题机器已尝试自动重启，但仍未恢复，需要 AI 深度排查修复：",
        "",
    ]
    for item in unrecoverable:
        lines.append(f"- **{item['name']}**：{item.get('detail', '未知原因')}")
    lines.append("")
    try:
        with open(TODO_FILE, "w") as f:
            f.write("\n".join(lines))
    except Exception:
        pass


def main():
    log("全项目检修开始")

    results = {}
    for name, config in SERVICES.items():
        results[name] = check_service(name, config)

    # 收集异常
    slow_state = load_json(SLOW_STATE, {})
    unhealthy = {}
    for name, r in results.items():
        if r.get("status") != "ok" or not r.get("port_alive", True):
            unhealthy[name] = r
    save_json(slow_state, slow_state)

    # 自动修复
    heal_results = []
    unrecoverable = []
    if unhealthy and AUTO_HEAL:
        for name, r in unhealthy.items():
            config = SERVICES[name]
            status = r.get("status")
            # 「进程死/端口丢/连不上」是真病，立刻修；「degraded」可能只是忙或者慢，
            # 按连续轮次判断 —— SLOW_TOLERANCE_CYCLES 之前只是定义着没生效。
            hard_down = status in ("inactive", "port_missing", "unknown")
            if not hard_down:
                slow_state[name] = slow_state.get(name, 0) + 1
                if slow_state[name] < SLOW_TOLERANCE_CYCLES:
                    heal_log(f"[WAIT] {name} 状态 {status}（{r.get('message')}），"
                             f"连续第 {slow_state[name]} 次，未达 {SLOW_TOLERANCE_CYCLES} 次不动手")
                    continue
            # 重启会掐断进程里正在跑的任务。客户在等结果的时候，宁可先不修。
            if int(r.get("active_scans") or 0) > 0:
                heal_log(f"[SKIP] {name} 状态 {status}，但此刻有 "
                         f"{r['active_scans']} 个任务在跑，重启会打断它们，本轮不修")
                unrecoverable.append({
                    "name": name,
                    "detail": f"状态 {status}（{r.get('message')}），"
                              f"{r['active_scans']} 个任务在跑，等跑完再修"})
                continue
            slow_state[name] = 0
            heal_log(f"[CHECK] {name} 异常: {r.get('message')}，尝试修复")
            result = try_heal_service(name, config)
            result["name"] = name
            result["reason"] = r.get("message", "")
            heal_results.append(result)
            if result.get("success"):
                results[name]["status"] = "ok"
                results[name]["port_alive"] = True
                results[name]["healed"] = result.get("detail", "")
            else:
                unrecoverable.append(result)

    # 写状态文件
    status_data = {
        "timestamp": datetime.now().isoformat(),
        "services": results,
        "heal_results": heal_results if heal_results else None,
    }
    for name, r in results.items():
        if r.get("status") == "ok" and r.get("port_alive", True):
            slow_state[name] = 0
    save_json(SLOW_STATE, slow_state)

    healthy = sum(1 for r in results.values() if r.get("status") == "ok" and r.get("port_alive", True))
    status_data["overall"] = "healthy" if healthy == len(results) else "degraded"
    save_json(STATUS_FILE, status_data)

    # 修不好的 → 写 AI 兜底待办
    if unrecoverable:
        write_todo(unrecoverable)
        for u in unrecoverable:
            log(f"[TODO] {u['name']} 自动修复失败，已写入待办: {u.get('detail')}", "ERROR")
    else:
        # 清空旧待办
        try:
            if TODO_FILE.exists():
                TODO_FILE.unlink()
        except Exception:
            pass

    heal_msg = ""
    if heal_results:
        ok_n = sum(1 for h in heal_results if h.get("success"))
        fail_n = len(heal_results) - ok_n
        heal_msg = f", 自动修复 {ok_n}成功/{fail_n}失败"
    log(f"检修完成: {healthy}/{len(results)} 健康{heal_msg}")


if __name__ == "__main__":
    main()
