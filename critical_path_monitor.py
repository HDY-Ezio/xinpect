#!/usr/bin/env python3
"""
煋鉴关键业务链路监控（服务器端独立版）
检查3条关键链路 + 前端错误聚合
异常时发送邮件告警，全部正常静默。
"""

import json
import os
import smtplib
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from email.mime.text import MIMEText

# 配置
DB_PATH = '/opt/xinpect-website/xinpect.db'
STATE_FILE = '/opt/xinpect-website/critical_path_state.json'
ADMIN_EMAIL = 'hdyabcd@163.com'
SMTP_SERVER = 'smtp.163.com'
SMTP_PORT = 465
SMTP_USER = 'hdyabcd@163.com'
SMTP_PASS = 'JV3Zg7ekmUU7GF7L'

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {'last_check_time': '', 'last_alerts': {}}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def send_alert(subject, body):
    """发送邮件告警"""
    try:
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['Subject'] = f'[煋鉴告警] {subject}'
        msg['From'] = SMTP_USER
        msg['To'] = ADMIN_EMAIL
        
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        print(f'[ALERT] {subject}')
    except Exception as e:
        print(f'[ERROR] 发送告警邮件失败: {e}')

def check_systemd_service(service_name):
    """检查 systemd 服务状态"""
    try:
        result = subprocess.run(
            ['systemctl', 'is-active', service_name],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip()
    except Exception:
        return 'unknown'

def check_port(port):
    """检查端口是否监听"""
    try:
        result = subprocess.run(
            ['ss', '-tlnp'],
            capture_output=True, text=True, timeout=5
        )
        return f':{port} ' in result.stdout
    except Exception:
        return False

def check_http(url, timeout=5):
    """检查 HTTP 端点"""
    try:
        result = subprocess.run(
            ['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', '--max-time', str(timeout), url],
            capture_output=True, text=True, timeout=timeout+2
        )
        return result.stdout.strip()
    except Exception:
        return '000'

def check_db_query(query, expected_value=None):
    """执行数据库查询"""
    try:
        db = sqlite3.connect(DB_PATH, timeout=5)
        cursor = db.execute(query)
        result = cursor.fetchone()
        db.close()
        if expected_value is not None:
            return result[0] == expected_value if result else False
        return result[0] if result else None
    except Exception as e:
        print(f'[DB ERROR] {query[:50]}... : {e}')
        return None

def should_alert(alert_key, state):
    """检查是否应该告警（10分钟内去重）"""
    last_alerts = state.get('last_alerts', {})
    last_time = last_alerts.get(alert_key)
    if not last_time:
        return True
    try:
        last_dt = datetime.fromisoformat(last_time)
        return (datetime.now() - last_dt).total_seconds() > 600  # 10分钟
    except Exception:
        return True

def main():
    state = load_state()
    alerts = []
    
    # 1. 扫描链路
    scanner_status = check_systemd_service('xinpect-scanner-green.service')
    port_8620_ok = check_port(8620)
    scanner_health = check_http('http://127.0.0.1:8620/health')
    scan_errors = check_db_query(
        "SELECT COUNT(*) FROM error_logs WHERE method='REPORT' AND error_type LIKE '%scan%' AND timestamp >= datetime('now', '-30 minutes')"
    ) or 0
    
    if scanner_status != 'active':
        alerts.append(f'扫描引擎服务异常: {scanner_status}')
    if not port_8620_ok:
        alerts.append('扫描引擎端口 8620 未监听')
    if scanner_health not in ['200', '000']:  # 000 表示没有该端点，不算异常
        alerts.append(f'扫描引擎健康检查失败: HTTP {scanner_health}')
    if scan_errors > 0:
        alerts.append(f'扫描相关错误: {scan_errors} 条（5分钟内）')
    
    # 2. 付费链路
    website_status = check_systemd_service('xinpect-website.service')
    website_health = check_http('http://127.0.0.1:8621/health')
    pay_errors = check_db_query(
        "SELECT COUNT(*) FROM error_logs WHERE method='REPORT' AND (error_type LIKE '%pay%' OR error_type LIKE '%credit%' OR endpoint LIKE '%pay%') AND timestamp >= datetime('now', '-30 minutes')"
    ) or 0
    
    if website_status != 'active':
        alerts.append(f'官网服务异常: {website_status}')
    if website_health != '200':
        alerts.append(f'官网健康检查失败: HTTP {website_health}')
    if pay_errors > 0:
        alerts.append(f'支付相关错误: {pay_errors} 条（5分钟内）')
    
    # 3. 积分链路
    credits_ok = check_db_query('SELECT 1 FROM user_credits LIMIT 1', 1)
    credit_errors = check_db_query(
        "SELECT COUNT(*) FROM error_logs WHERE method='REPORT' AND (error_type LIKE '%credit%' OR error_type LIKE '%transaction%') AND timestamp >= datetime('now', '-30 minutes')"
    ) or 0
    
    if not credits_ok:
        alerts.append('积分系统数据库异常')
    if credit_errors > 0:
        alerts.append(f'积分相关错误: {credit_errors} 条（5分钟内）')
    
    # 4. 前端错误聚合
    try:
        db = sqlite3.connect(DB_PATH, timeout=5)
        # click_no_response是启发式检测误报率高，阈值提高到5
        cursor = db.execute(
            """SELECT endpoint, error_type, COUNT(*) as cnt FROM error_logs 
               WHERE method='REPORT' AND timestamp >= datetime('now', '-30 minutes')
               GROUP BY endpoint, error_type
               HAVING (error_type = 'click_no_response' AND COUNT(*) >= 5)
                   OR (error_type != 'click_no_response' AND COUNT(*) >= 2)"""
        )
        frontend_errors = cursor.fetchall()
        db.close()
        
        for endpoint, error_type, count in frontend_errors:
            alerts.append(f'🔥 前端错误聚合: {endpoint} ({error_type}) x{count}')
    except Exception as e:
        print(f'[ERROR] 查询前端错误聚合失败: {e}')
    
    # 5. 前端路由主动健康检查
    try:
        import urllib.request
        critical_routes = [
            ("/", "首页"),
            ("/pricing", "定价页"),
            ("/login", "登录页"),
        ]
        for path, name in critical_routes:
            try:
                req = urllib.request.Request(f"http://127.0.0.1:8621{path}", method="GET")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status != 200:
                        alerts.append(f"前端路由异常: {name}({path}) HTTP {resp.status}")
            except urllib.error.HTTPError as e:
                if e.code >= 500:
                    alerts.append(f"前端路由错误: {name}({path}) HTTP {e.code}")
            except Exception as e:
                alerts.append(f"前端路由不可达: {name}({path}) {str(e)[:60]}")
    except Exception as e:
        print(f"[ERROR] 前端路由检查失败: {e}")
    
    # 6. 数据库完整性检查
    try:
        db = sqlite3.connect(DB_PATH, timeout=5)
        result = db.execute("PRAGMA integrity_check").fetchone()
        db.close()
        if result[0] != 'ok':
            alerts.append(f'⚠️ 数据库完整性异常: {result[0]}')
    except Exception as e:
        alerts.append(f'⚠️ 数据库连接失败: {str(e)[:80]}')
    
    # 7. 备份有效性检查（每天检查一次最新备份是否存在且非空）
    import glob as glob_mod
    try:
        backup_dir = '/opt/xinpect-website/backups/database'
        backups = sorted(glob_mod.glob(os.path.join(backup_dir, '*.db.gz')))
        if not backups:
            # 也检查直接sql文件
            backups = sorted(glob_mod.glob(os.path.join(backup_dir, '*.db')))
        if backups:
            latest = backups[-1]
            size = os.path.getsize(latest)
            if size < 1000:  # 小于1KB可能是空备份
                alerts.append(f'⚠️ 数据库备份异常: {os.path.basename(latest)} 仅{size}字节')
        else:
            alerts.append('⚠️ 未找到数据库备份文件')
    except Exception as e:
        print(f'[WARN] 备份检查失败: {e}')
    
    # 更新状态
    state['last_check_time'] = datetime.now().isoformat()
    
    if alerts:
        # 有异常，检查是否需要告警
        alert_keys = [a[:50] for a in alerts]
        new_alerts = [a for a, k in zip(alerts, alert_keys) if should_alert(k, state)]
        
        if new_alerts:
            # 更新告警时间戳
            for k in alert_keys:
                state['last_alerts'][k] = datetime.now().isoformat()
            
            # 发送告警邮件
            body = '煋鉴关键链路监控告警\n\n'
            body += '检查时间: ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + '\n\n'
            body += '异常项:\n'
            for i, alert in enumerate(alerts, 1):
                body += f'{i}. {alert}\n'
            body += '\n请立即检查并处理。\n'
            
            send_alert(f'发现 {len(alerts)} 项异常', body)
        else:
            print('[OK] 有异常但10分钟内已告警过，跳过')
    else:
        print('[OK] ALL CLEAR - 所有链路正常')
    
    save_state(state)

if __name__ == '__main__':
    main()
