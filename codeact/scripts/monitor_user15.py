#!/usr/bin/env python3
"""
煋鉴付费用户(user_id=15)活动与异常监控
通过腾讯云TAT远程执行，检查数据库和日志
"""
import json
import sys
import sqlite3
import subprocess
from datetime import datetime

DB_PATH = '/opt/xinpect-website/xinpect.db'
LOG_PATH = '/opt/xinpect-website/website.log'
NGINX_LOG = '/var/log/nginx/error.log'
STATE_FILE = '/opt/xinpect-website/codeact/output/monitor_user15_state.json'

def get_last_check():
    """获取上次检查时间"""
    try:
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
            return state.get('last_check', '2026-09-11 13:42:00')
    except:
        return '2026-09-11 13:42:00'

def save_last_check(timestamp):
    """保存检查时间"""
    state = {'last_check': timestamp}
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

def check_new_scans(last_check):
    """检查新的扫描记录"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT scan_id, title, file_count, score, grade, created_at 
        FROM scans 
        WHERE user_id = 15 AND created_at > ?
        ORDER BY created_at DESC
    """, (last_check,))
    scans = cursor.fetchall()
    conn.close()
    return scans

def check_api_key_usage(last_check):
    """检查API Key使用情况"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name, last_used, usage_count 
        FROM api_keys 
        WHERE user_id = 15 AND last_used > ?
    """, (last_check,))
    keys = cursor.fetchall()
    conn.close()
    return keys

def check_app_errors(last_check):
    """检查应用日志错误"""
    errors = []
    try:
        with open(LOG_PATH, 'r') as f:
            for line in f:
                if last_check in line and any(kw in line.lower() for kw in ['error', 'exception', 'traceback']):
                    errors.append(line.strip()[:200])
    except:
        pass
    return errors[:5]

def check_nginx_errors(last_check):
    """检查Nginx 5xx错误"""
    errors = []
    try:
        with open(NGINX_LOG, 'r') as f:
            for line in f:
                if last_check in line and '5' in line:
                    errors.append(line.strip()[:200])
    except:
        pass
    return errors[:5]

def main():
    result_mode = sys.argv[1] if len(sys.argv) > 1 else 'notify'
    last_check = get_last_check()
    
    # 检查各项指标
    new_scans = check_new_scans(last_check)
    api_usage = check_api_key_usage(last_check)
    app_errors = check_app_errors(last_check)
    nginx_errors = check_nginx_errors(last_check)
    
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    save_last_check(now)
    
    # 构建通知
    notifications = []
    
    if new_scans:
        notifications.append(f"📋 **新扫描活动**：检测到 {len(new_scans)} 次新扫描")
        for scan in new_scans[:3]:
            notifications.append(f"  - {scan[1] or '未命名'} | 得分:{scan[3]} | {scan[5]}")
    
    if api_usage:
        notifications.append(f"🔑 **API调用**：{len(api_usage)} 个Key被使用")
    
    if app_errors:
        notifications.append(f"🚨 **应用错误**：{len(app_errors)} 条错误日志")
        for err in app_errors[:2]:
            notifications.append(f"  - {err}")
    
    if nginx_errors:
        notifications.append(f"🌐 **Nginx错误**：{len(nginx_errors)} 条5xx错误")
    
    # 输出结果
    if notifications:
        print("\n".join(notifications))
    else:
        print(f"✅ 无新活动，无异常 | 检查时间: {now}")

if __name__ == '__main__':
    main()
