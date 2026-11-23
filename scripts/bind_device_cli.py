#!/usr/bin/env python3
"""
煋鉴管理后台 - 设备绑定CLI工具
用法：直接在服务器执行，手动绑定设备指纹
"""
import sqlite3
import sys

DB_PATH = "/opt/xinpect-website/xinpect.db"

def bind_device(user_id, fingerprint, device_name="CLI绑定设备"):
    conn = sqlite3.connect(DB_PATH)
    # Check if already exists
    existing = conn.execute(
        "SELECT id FROM admin_devices WHERE user_id=? AND device_fingerprint=?",
        (user_id, fingerprint)
    ).fetchone()
    
    if existing:
        conn.execute(
            "UPDATE admin_devices SET is_trusted=1, device_name=? WHERE id=?",
            (device_name, existing[0])
        )
        print(f"设备已重新激活 (ID: {existing[0]})")
    else:
        conn.execute(
            "INSERT INTO admin_devices (user_id, device_fingerprint, device_name) VALUES (?, ?, ?)",
            (user_id, fingerprint, device_name)
        )
        print(f"设备绑定成功 (指纹: {fingerprint[:16]}...)")
    
    conn.commit()
    conn.close()

def list_devices(user_id):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id, device_fingerprint, device_name, created_at, last_used_at FROM admin_devices WHERE user_id=?",
        (user_id,)
    ).fetchall()
    conn.close()
    
    if not rows:
        print(f"用户{user_id}没有已绑定设备")
        return
    
    print(f"用户{user_id}已绑定设备 ({len(rows)}台):")
    for r in rows:
        print(f"  ID={r[0]} | 指纹={r[1][:16]}... | 名称={r[2]} | 绑定={r[3]} | 最后使用={r[4] or '从未'}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法:")
        print("  python3 bind_device_cli.py list <user_id>     - 列出已绑定设备")
        print("  python3 bind_device_cli.py bind <user_id> <fingerprint> [设备名称]  - 绑定设备")
        sys.exit(1)
    
    action = sys.argv[1]
    if action == "list":
        uid = int(sys.argv[2]) if len(sys.argv) > 2 else 6
        list_devices(uid)
    elif action == "bind":
        uid = int(sys.argv[2])
        fp = sys.argv[3]
        name = sys.argv[4] if len(sys.argv) > 4 else "CLI绑定设备"
        bind_device(uid, fp, name)
    else:
        print(f"未知操作: {action}")
