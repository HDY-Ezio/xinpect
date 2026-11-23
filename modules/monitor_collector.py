# -*- coding: utf-8 -*-
"""
煋鉴总控监视器 —— 只读数据采集模块

定位：像工厂总控台，一眼看到全项目实时状态。只能看，不能做任何操作。
数据源（全部只读 GET）：
  1. 扫描器 health (8620/8622) —— 引擎数、扫描性能
  2. 规则 bundle 文件 —— 有效/停用规则数、语言覆盖、severity 分布
  3. 门房 health (8765) —— 服务状态、支付是否就绪
  4. systemd 服务状态 —— 各服务是否 active

本模块不 import flask，纯数据采集，方便单独测试。
"""

import json
import subprocess
import os

BUNDLE_PATH = "/opt/xinpect-scanner-green/rules/brain_rules_bundle.json"
SCANNER_GREEN = "http://127.0.0.1:8620"
SCANNER_BLUE = "http://127.0.0.1:8622"
MENFANG = "http://127.0.0.1:8765"
SYSTEMCTL_TIMEOUT_SECONDS = 5  # systemctl is-active 探测超时

# 7 引擎 + 2 防线的标准表述（对齐老板定的口径）
ENGINES = [
    ("E1", "语法与AST分析"),
    ("E2", "安全检测"),
    ("E3", "性能与可靠性"),
    ("E4", "代码质量与可观测性"),
    ("E5", "架构与部署"),
    ("E6", "组件合规"),
    ("E7", "AI应用健康检测"),
]
DEFENSE_LAYERS = [
    ("ai", "AI语义分析（二审降噪）"),
    ("poc", "PoC实弹验证（漏洞确认真假）"),
]


def _http_get_json(url, timeout=4):
    """只读 GET，返回 dict 或 None。"""
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", str(timeout), url],
            capture_output=True, text=True, timeout=timeout + 2,
        )
        if r.returncode != 0:
            return None
        return json.loads(r.stdout)
    except Exception:
        return None


def _service_active(name):
    """查 systemd 服务是否 active（只读）。"""
    try:
        r = subprocess.run(
            ["systemctl", "is-active", name],
            capture_output=True, text=True, timeout=SYSTEMCTL_TIMEOUT_SECONDS,
        )
        return r.stdout.strip() == "active"
    except Exception:
        return False


def read_rules():
    """读规则 bundle，统计有效/停用/severity/语言覆盖。"""
    try:
        with open(BUNDLE_PATH, encoding="utf-8") as f:
            d = json.load(f)
    except Exception as e:
        return {"error": str(e)}

    total = 0
    disabled = 0
    sev_counter = {}
    lang_counter = {}
    brain_counter = {}

    for brain, rules in d.items():
        brain_counter[brain] = len(rules)
        for r in rules:
            total += 1
            if r.get("disabled"):
                disabled += 1
            sev = r.get("severity", "unknown")
            sev_counter[sev] = sev_counter.get(sev, 0) + 1
            # 语言从 id 前缀或 applicable_files 推断，这里简单统计 applicable_files
            af = r.get("applicable_files", [])
            if isinstance(af, list):
                for item in af:
                    if isinstance(item, str) and "." in item:
                        ext = item.rsplit(".", 1)[-1]
                        lang_counter[ext] = lang_counter.get(ext, 0) + 1

    return {
        "total": total,
        "disabled": disabled,
        "active": total - disabled,
        "severity": sev_counter,
        "brain_distribution": brain_counter,
    }


def read_scanner(port_url, label):
    """读扫描器 health。"""
    h = _http_get_json(port_url + "/health")
    if not h:
        return {"label": label, "status": "down"}
    perf = h.get("performance", {})
    return {
        "label": label,
        "status": h.get("status", "unknown"),
        "version": h.get("version", "?"),
        "brains_loaded": h.get("brains_loaded", 0),
        "total_scans": perf.get("total_scans", 0),
        "success_rate": perf.get("success_rate", 0),
        "avg_elapsed": perf.get("avg_elapsed_seconds", 0),
    }


def read_menfang():
    """读门房 health。"""
    h = _http_get_json(MENFANG + "/api/health")
    if not h:
        return {"status": "down"}
    return {
        "status": h.get("status", "unknown"),
        "wechat_pay_configured": h.get("wechat_pay_configured", False),
        "keys_loaded": h.get("keys_loaded", False),
    }


def read_services():
    """读所有关键服务的 systemd 状态。"""
    svcs = [
        ("xinpect-website", "官网"),
        ("xinpect-scanner-green", "绿扫描器(生产)"),
        ("xinpect-scanner-blue", "蓝扫描器"),
        ("xinpect-pay", "门房(付费)"),
    ]
    return [{"name": n, "label": l, "active": _service_active(n + ".service")} for n, l in svcs]


def collect_all():
    """汇总所有只读数据，供监视器前端使用。"""
    rules = read_rules()
    return {
        "engines": ENGINES,
        "defense_layers": DEFENSE_LAYERS,
        "rules": rules,
        "scanner_green": read_scanner(SCANNER_GREEN, "绿扫描器"),
        "scanner_blue": read_scanner(SCANNER_BLUE, "蓝扫描器"),
        "menfang": read_menfang(),
        "services": read_services(),
    }


if __name__ == "__main__":
    # 单独运行测试：打印采集结果
    print(json.dumps(collect_all(), ensure_ascii=False, indent=2))
