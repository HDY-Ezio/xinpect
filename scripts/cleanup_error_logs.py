#!/usr/bin/env python3
"""
煋鉴error_logs自动清理脚本
- 清理30天前的已解决记录
- 清理7天前的click_no_response记录（启发式检测误报率高，保留短期即可）
- 清理30天前的404/401爬虫扫描记录
- 保留所有5xx和critical错误记录

用法:
  python3 cleanup_error_logs.py           # 执行清理
  python3 cleanup_error_logs.py --dry-run # 仅统计不删除
"""

import sqlite3, sys, os
from datetime import datetime

DB_PATH = "/opt/xinpect-website/xinpect.db"

def cleanup(dry_run=False):
    db = sqlite3.connect(DB_PATH, timeout=10)
    
    print(f"=== error_logs清理 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
    if dry_run:
        print("（DRY RUN模式，不实际删除）")
    
    # 统计当前状态
    total = db.execute("SELECT COUNT(*) FROM error_logs").fetchone()[0]
    print(f"当前总数: {total}")
    
    # 1. 清理30天前的已解决记录
    count = db.execute(
        "SELECT COUNT(*) FROM error_logs WHERE resolved = 1 AND timestamp < datetime('now', '-30 days')"
    ).fetchone()[0]
    print(f"30天前已解决: {count}")
    if not dry_run and count > 0:
        db.execute("DELETE FROM error_logs WHERE resolved = 1 AND timestamp < datetime('now', '-30 days')")
    
    # 2. 清理7天前的click_no_response记录
    count = db.execute(
        "SELECT COUNT(*) FROM error_logs WHERE error_type = 'click_no_response' AND timestamp < datetime('now', '-7 days')"
    ).fetchone()[0]
    print(f"7天前click_no_response: {count}")
    if not dry_run and count > 0:
        db.execute("DELETE FROM error_logs WHERE error_type = 'click_no_response' AND timestamp < datetime('now', '-7 days')")
    
    # 3. 清理30天前的404/401非用户记录
    count = db.execute(
        "SELECT COUNT(*) FROM error_logs WHERE response_status IN (404, 401) AND user_id IS NULL AND timestamp < datetime('now', '-30 days')"
    ).fetchone()[0]
    print(f"30天前404/401(爬虫): {count}")
    if not dry_run and count > 0:
        db.execute("DELETE FROM error_logs WHERE response_status IN (404, 401) AND user_id IS NULL AND timestamp < datetime('now', '-30 days')")
    
    if not dry_run:
        db.commit()
        new_total = db.execute("SELECT COUNT(*) FROM error_logs").fetchone()[0]
        print(f"\n清理后: {new_total}（删除了 {total - new_total} 条）")
    else:
        print(f"\n预计可清理: {total - db.execute('SELECT COUNT(*) FROM error_logs').fetchone()[0]} 条")
    
    # 重建索引
    if not dry_run:
        db.execute("PRAGMA optimize")
    
    db.close()

if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    cleanup(dry_run)
