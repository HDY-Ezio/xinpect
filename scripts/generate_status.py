#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
煋鉴状态快照生成器
从实际系统提取数据，生成JSON状态文件
"""

import json
import os
import sys
import sqlite3
import subprocess
from datetime import datetime, timezone, timedelta

# 路径配置
BASE_DIR = "/opt/xinpect-website"
DB_PATH = os.path.join(BASE_DIR, "xinpect.db")
OUTPUT_DIR = os.path.join(BASE_DIR, "status")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "xinpect_status.json")
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)  # 供 monitoring.safe_write 导入
SCANNER_URL = "http://localhost:8620"

# 扫描引擎目录（蓝绿部署，取当前活跃目录）
SCANNER_DIRS = ["/opt/xinpect-scanner-green", "/opt/xinpect-scanner-blue"]

CST = timezone(timedelta(hours=8))

# 敏感词列表，用于脱敏
SENSITIVE_KEYS = {"secret", "password", "passwd", "pwd", "key", "token", "apikey", "credential"}


def safe_query(db, sql, params=(), default=None):
    """安全执行SQL查询，返回单值"""
    try:
        cur = db.execute(sql, params)
        row = cur.fetchone()
        return row[0] if row else default
    except Exception:
        return default


def get_db_stats(db):
    """数据库统计"""
    stats = {}
    stats["users_total"] = safe_query(db, "SELECT COUNT(*) FROM users", default=0)
    stats["users_vip"] = safe_query(db, "SELECT COUNT(*) FROM users WHERE is_vip=1", default=0)
    stats["users_banned"] = safe_query(db, "SELECT COUNT(*) FROM users WHERE is_banned=1", default=0)
    stats["users_admin"] = safe_query(db, "SELECT COUNT(*) FROM users WHERE is_admin=1", default=0)
    stats["scans_total"] = safe_query(db, "SELECT COUNT(*) FROM scans", default=0)
    stats["scans_today"] = safe_query(db,
        "SELECT COUNT(*) FROM scans WHERE date(created_at)=date('now','localtime')", default=0)
    stats["orders_paid"] = safe_query(db, "SELECT COUNT(*) FROM orders WHERE status='paid'", default=0)
    stats["revenue_month"] = float(safe_query(db,
        "SELECT COALESCE(SUM(amount),0) FROM orders WHERE status='paid' AND strftime('%Y-%m',paid_at)=strftime('%Y-%m','now','localtime')",
        default=0.0))
    stats["revenue_total"] = float(safe_query(db,
        "SELECT COALESCE(SUM(amount),0) FROM orders WHERE status='paid'", default=0.0))
    stats["invoices_pending"] = safe_query(db,
        "SELECT COUNT(*) FROM invoice_requests WHERE status='pending'", default=0)
    try:
        stats["api_keys_active"] = safe_query(db,
            "SELECT COUNT(*) FROM api_keys WHERE is_active=1", default=0)
    except:
        stats["api_keys_active"] = "N/A"
    stats["latest_user"] = safe_query(db,
        "SELECT email FROM users ORDER BY created_at DESC LIMIT 1", default="")
    return stats


def get_scanner_info():
    """从扫描引擎获取信息"""
    info = {"status": "unknown", "version": "", "brains_loaded": 0,
            "brain_names": {}, "ai_model": "", "rules_count": 0,
            "languages": [], "languages_count": 0,
            "rule_engines_count": 7, "rule_engines": {},
            "ai_layers": [], "architecture": ""}
    try:
        import urllib.request
        req = urllib.request.Request(f"{SCANNER_URL}/health", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            info["status"] = data.get("status", "unknown")
            info["version"] = data.get("version", "")
            info["brains_loaded"] = data.get("brains_loaded", 0)
            info["brain_names"] = data.get("brain_names", {})
            ai_engine = data.get("ai_engine", {})
            # 从ai_engine提取模型信息
            info["ai_model"] = ai_engine.get("model", "")
            if not info["ai_model"] and ai_engine.get("legacy_engine"):
                info["ai_model"] = "legacy(内置规则引擎)"
    except Exception as e:
        info["status"] = f"error: {str(e)[:50]}"

    # 对外引擎口径（三层结构：7 大规则引擎 + AI + PoC）
    # brains_loaded 为内部技术计数（brain 1-7 + ai + poc = 9），仅供排查
    eng_file = os.path.join(BASE_DIR, "config", "engines.json")
    try:
        with open(eng_file, "r", encoding="utf-8") as f:
            eng = json.load(f)
        info["rule_engines_count"] = eng.get("rule_engines_count", 7)
        info["rule_engines"] = eng.get("rule_engines", {})
        info["ai_layers"] = eng.get("ai_layers", [])
        info["architecture"] = eng.get("architecture", "")
    except Exception:
        info["rule_engines_count"] = 7

    # 从配置文件读取AI模型
    for scanner_dir in SCANNER_DIRS:
        config_file = os.path.join(scanner_dir, "_ai_client_config.py")
        if os.path.exists(config_file):
            try:
                with open(config_file, "r", errors="ignore") as f:
                    content = f.read()
                # 提取模型名称
                import re
                models = re.findall(r'"model":\s*"([^"]+)"', content)
                if models:
                    info["ai_model"] = ", ".join(sorted(set(models)))
                    break
            except:
                pass

    # 统计规则数量
    for scanner_dir in SCANNER_DIRS:
        if not os.path.exists(scanner_dir):
            continue
        try:
            result = subprocess.run(
                ["grep", "-rn", "def check_", scanner_dir, "--include=*.py"],
                capture_output=True, text=True, timeout=10
            )
            def_check_count = 0
            if result.stdout:
                def_check_count = len([l for l in result.stdout.strip().split("\n") if l.strip()])

            result2 = subprocess.run(
                ["grep", "-rn", "rule_id", scanner_dir, "--include=*.py"],
                capture_output=True, text=True, timeout=10
            )
            rule_id_count = 0
            if result2.stdout:
                rule_id_count = len([l for l in result2.stdout.strip().split("\n") if l.strip()])

            info["rules_count"] = max(def_check_count, rule_id_count)
            if info["rules_count"] > 0:
                break
        except:
            pass

    # 规则总数：从规则库文件精确统计（权威口径）
    for scanner_dir in SCANNER_DIRS:
        bundle = os.path.join(scanner_dir, "rules", "brain_rules_bundle.json")
        if os.path.exists(bundle):
            try:
                with open(bundle, "r", encoding="utf-8", errors="ignore") as f:
                    data = json.load(f)
                total = sum(len(v) for v in data.values() if isinstance(v, list))
                if total > 0:
                    info["rules_count"] = total
                    break
            except Exception:
                pass

    # 支持的语言/技术栈：读取权威清单（单一数据源）
    lang_file = os.path.join(BASE_DIR, "config", "supported_languages.json")
    try:
        with open(lang_file, "r", encoding="utf-8") as f:
            lang_data = json.load(f)
        info["languages"] = lang_data.get("languages", [])
        info["languages_count"] = lang_data.get("count", len(info["languages"]))
    except Exception:
        info["languages"] = []
        info["languages_count"] = 0
    return info


def get_deployment_info():
    """部署信息"""
    info = {"status": "unknown", "last_deploy": "", "git_commit": "",
            "git_message": "", "service_uptime": ""}

    # 服务状态
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "xinpect-website"],
            capture_output=True, text=True, timeout=5
        )
        info["status"] = result.stdout.strip()
    except:
        pass

    # 服务启动时间
    try:
        result = subprocess.run(
            ["systemctl", "show", "xinpect-website", "--property=ActiveEnterTimestamp"],
            capture_output=True, text=True, timeout=5
        )
        if "=" in result.stdout:
            info["service_uptime"] = result.stdout.split("=", 1)[1].strip()
    except:
        pass

    # Git信息
    try:
        result = subprocess.run(
            ["git", "-C", BASE_DIR, "log", "--oneline", "-5"],
            capture_output=True, text=True, timeout=5
        )
        if result.stdout.strip():
            lines = result.stdout.strip().split("\n")
            first = lines[0].split(" ", 1)
            info["git_commit"] = first[0]
            info["git_message"] = first[1] if len(first) > 1 else ""
    except:
        pass

    # 最后部署时间 - 用app.py修改时间
    try:
        app_py = os.path.join(BASE_DIR, "app.py")
        mtime = os.path.getmtime(app_py)
        dt = datetime.fromtimestamp(mtime, tz=CST)
        info["last_deploy"] = dt.isoformat()
    except:
        pass

    return info


def get_recent_changes():
    """最近变更"""
    changes = []
    try:
        result = subprocess.run(
            ["git", "-C", BASE_DIR, "log", "--oneline", "-5", "--format=%s"],
            capture_output=True, text=True, timeout=5
        )
        if result.stdout.strip():
            changes = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
    except:
        pass
    return changes


def get_env_info():
    """环境变量（脱敏）"""
    env_vars = {}
    service_file = "/etc/systemd/system/xinpect-website.service"
    try:
        with open(service_file, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("Environment="):
                    kv = line[len("Environment="):]
                    if "=" in kv:
                        key, val = kv.split("=", 1)
                        key = key.strip()
                        if any(s in key.lower() for s in SENSITIVE_KEYS):
                            env_vars[key] = "***MASKED***"
                        else:
                            env_vars[key] = val.strip()
    except:
        pass
    return env_vars


def main():
    now = datetime.now(CST)

    # 连接数据库（只读）
    try:
        db = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=10)
    except Exception as e:
        print(f"ERROR: 无法连接数据库: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        status = {
            "version": "6.3.0",
            "generated_at": now.isoformat(),
            "generated_by": "generate_status.py",
            "database": get_db_stats(db),
            "engines": get_scanner_info(),
            "deployment": get_deployment_info(),
            "environment": get_env_info(),
            "recent_changes": get_recent_changes(),
        }

        # 确保输出目录存在
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        # 写入文件（统一落盘出口：原子写 + 存储异常降级，不中断快照生成）
        from monitoring.safe_write import write_json
        if write_json(OUTPUT_FILE, status, perm=0o600, label="状态快照"):
            print(f"[OK] 状态快照已生成: {OUTPUT_FILE}")
        else:
            print(f"[WARN] 状态快照未落盘，已降级到标准输出: {OUTPUT_FILE}")
        print(f"[OK] 生成时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
