#!/usr/bin/env python3
"""
从 systemd journal 收集所有业务服务的错误，写入 xinpect.db 的 error_logs 表。
每小时由 cron 执行一次，使用 cursor 文件避免重复写入。
"""

import sqlite3
import subprocess
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = "/opt/xinpect-website/xinpect.db"
CURSOR_FILE = "/opt/xinpect-website/data/journal_cursor.json"

# 需要监控的所有业务服务
MONITORED_SERVICES = [
    "xinpect-website",
    "xinpect-scanner",
    "xinpect-pay",
    "xinpect-pay-notify",
    "starwang-backend",
    "starwang-backend-clean",
    "starwang-billing",
    "starwang-promotion",
    "starwang-voice",
    "starwang-voice-v3",
    "xw-gateway",
    "fcc-server",
]

# journal 日志优先级
PRIORITY_MAP = {
    "0": "EMERG",
    "1": "ALERT",
    "2": "CRIT",
    "3": "ERR",
    "4": "WARNING",
}


def load_cursor():
    """加载上次的读取位置"""
    if os.path.exists(CURSOR_FILE):
        with open(CURSOR_FILE, "r") as f:
            return json.load(f)
    return {}


def save_cursor(cursor_data):
    """保存读取位置"""
    os.makedirs(os.path.dirname(CURSOR_FILE), exist_ok=True)
    with open(CURSOR_FILE, "w") as f:
        json.dump(cursor_data, f)


def get_journal_errors(service, since_iso=None):
    """从 journalctl 获取指定服务的错误日志"""
    cmd = [
        "sudo", "journalctl",
        "-u", f"{service}.service",
        "--priority=err",
        "--no-pager",
        "-o", "json",
        "--output-fields=__REALTIME_TIMESTAMP,SYSLOG_IDENTIFIER,_PID,MESSAGE,PRIORITY,_SYSTEMD_UNIT",
    ]
    if since_iso:
        cmd.extend(["--since", since_iso])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            print(f"  [WARN] journalctl failed for {service}: {result.stderr[:200]}")
            return []

        entries = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                entries.append(entry)
            except json.JSONDecodeError:
                continue
        return entries
    except subprocess.TimeoutExpired:
        print(f"  [WARN] journalctl timeout for {service}")
        return []
    except Exception as e:
        print(f"  [WARN] Failed to read journal for {service}: {e}")
        return []


def collect_all():
    """收集所有服务的错误并写入数据库"""
    # 计算查询起始时间：默认查最近2小时（比cron间隔稍长，确保不遗漏）
    # 如果有 cursor，从 cursor 时间开始
    cursor_data = load_cursor()
    
    # 如果从未运行过，查最近6小时；否则从上次时间开始
    if "last_run" in cursor_data:
        since = cursor_data["last_run"]
    else:
        since = (datetime.now() - timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S")

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始收集 journal 错误...")
    print(f"  查询起始时间: {since}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    total_new = 0
    seen_keys = set()

    # 获取已有记录的指纹，避免重复
    existing = conn.execute(
        """SELECT timestamp, endpoint, error_message FROM error_logs 
           WHERE error_type LIKE 'JOURNAL_%' AND timestamp > ?""",
        (since,),
    ).fetchall()
    for row in existing:
        key = f"{row['timestamp']}|{row['endpoint']}|{(row['error_message'] or '')[:100]}"
        seen_keys.add(key)

    latest_ts = since  # 跟踪最新的时间戳

    for service in MONITORED_SERVICES:
        entries = get_journal_errors(service, since)
        if not entries:
            continue

        for entry in entries:
            # 解析时间戳（微秒级 Unix 时间戳）
            raw_ts = entry.get("__REALTIME_TIMESTAMP", "")
            try:
                ts_us = int(raw_ts)
                ts_dt = datetime.fromtimestamp(ts_us / 1_000_000)
                ts_str = ts_dt.strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, OSError):
                ts_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            message = entry.get("MESSAGE", "").strip()
            priority = entry.get("PRIORITY", "3")
            syslog_id = entry.get("SYSLOG_IDENTIFIER", service)
            pid = entry.get("_PID", "")

            # 去重：相同时间+服务+消息前100字
            dedup_key = f"{ts_str}|/{service}|{message[:100]}"
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)

            # 写入数据库
            conn.execute(
                """INSERT INTO error_logs 
                (timestamp, user_id, endpoint, method, error_type, error_message, 
                 stack_trace, request_params, response_status, ip_address, user_agent)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ts_str,
                    None,  # 系统级错误，无用户ID
                    f"/{service}",  # endpoint = 服务名
                    "JOURNAL",
                    f"JOURNAL_{PRIORITY_MAP.get(priority, 'ERR')}",
                    message,
                    None,  # 无堆栈
                    json.dumps({
                        "syslog_id": syslog_id,
                        "pid": pid,
                        "priority": priority,
                        "source": "systemd_journal",
                    }),
                    int(priority) * 100,  # 3->300(ERR), 4->400(WARNING)
                    None,  # 无IP
                    f"{syslog_id}[{pid}]",
                ),
            )
            total_new += 1

            # 更新最新时间戳
            if ts_str > latest_ts:
                latest_ts = ts_str

        print(f"  {service}: {len(entries)} 条错误")

    conn.commit()
    conn.close()

    # 保存 cursor：减去5分钟缓冲，避免边界遗漏
    save_cursor_ts = (datetime.strptime(latest_ts, "%Y-%m-%d %H:%M:%S") - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
    save_cursor({"last_run": save_cursor_ts})

    print(f"  总计新增: {total_new} 条")
    print(f"  完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return total_new


if __name__ == "__main__":
    collect_all()
