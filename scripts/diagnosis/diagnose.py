#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
煋鉴运维排障 - 自动化诊断脚本
只读采集系统状态，生成结构化诊断数据
绝不修改任何文件、配置、服务状态
"""
import json
import os
import re
import sqlite3
import subprocess
import time
from datetime import datetime, timedelta

SERVICES = ['xinpect-website', 'xinpect-scanner-green', 'xinpect-scanner-blue', 'xinpect-pay']
WEBSITE_DIR = '/opt/xinpect-website'
DB_PATH = os.path.join(WEBSITE_DIR, 'xinpect.db')
LOG_WINDOW_MINUTES = 30
MAX_LOG_LINES = 100
REPORT_DIR = os.path.join(WEBSITE_DIR, 'reports', 'diagnosis')

def run_readonly(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True, timeout=timeout)
        return {'cmd': cmd if isinstance(cmd, str) else ' '.join(cmd), 'returncode': r.returncode, 'stdout': r.stdout.strip()[:5000], 'stderr': r.stderr.strip()[:2000]}
    except subprocess.TimeoutExpired:
        return {'cmd': str(cmd), 'returncode': -1, 'stdout': '', 'stderr': 'TIMEOUT'}
    except Exception as e:
        return {'cmd': str(cmd), 'returncode': -1, 'stdout': '', 'stderr': str(e)[:500]}

def safe_int(val, default=-1):
    try: return int(val)
    except: return default

def check_basic_info():
    info = {}
    for name, cmd in [('hostname','hostname'),('uptime','uptime'),('os_version','cat /etc/os-release | grep PRETTY_NAME'),('kernel','uname -r'),('current_time',"date '+%Y-%m-%d %H:%M:%S'"),('current_user','whoami')]:
        info[name] = run_readonly(cmd)['stdout']
    return info

def check_services():
    results = {}
    for svc in SERVICES:
        r = run_readonly(f'systemctl is-active {svc}')
        results[svc] = {'active': r['stdout']=='active', 'status': r['stdout']}
        if not results[svc]['active']:
            results[svc]['detail'] = run_readonly(f'systemctl status {svc} --no-pager -l 2>&1 | head -20')['stdout']
    return results

def check_system_resources():
    resources = {}
    resources['load_average'] = run_readonly('cat /proc/loadavg')['stdout']
    resources['cpu_cores'] = safe_int(run_readonly('nproc')['stdout'])
    mem = run_readonly("free -m | awk 'NR==2{printf \\'{\"total\":%s,\"used\":%s,\"free\":%s,\"available\":%s}\\', \,\,\,\}'")
    try: resources['memory_mb'] = json.loads(mem['stdout'])
    except: resources['memory_mb'] = {'raw': mem['stdout']}
    resources['disk'] = run_readonly('df -h / /opt 2>/dev/null | tail -n +2')['stdout']
    return resources

def check_ports():
    result = run_readonly('ss -tlnp')
    listening = {}
    for line in result['stdout'].split('\n')[1:]:
        parts = line.split()
        if len(parts) >= 4:
            match = re.search(r':(\d+)$', parts[3])
            if match: listening[match.group(1)] = line.strip()
    return listening

def check_processes():
    return run_readonly('ps aux --sort=-%mem | head -20')['stdout']

def check_recent_logs():
    logs = {}
    since = f'{LOG_WINDOW_MINUTES} min ago'
    for svc in SERVICES:
        r = run_readonly(f"journalctl -u {svc} --no-pager --since '{since}' -p warning --lines {MAX_LOG_LINES} 2>/dev/null")
        if r['stdout']: logs[f'{svc}_warnings'] = r['stdout']
        r2 = run_readonly(f"journalctl -u {svc} --no-pager --since '{since}' -g 'Started|Stopped|Restarting|Failed' --lines 10 2>/dev/null")
        if r2['stdout']: logs[f'{svc}_lifecycle'] = r2['stdout']
    oom = run_readonly("dmesg --time-format iso 2>/dev/null | grep -i 'oom\\|killed process' | tail -10")
    if oom['stdout']: logs['oom_events'] = oom['stdout']
    return logs

def check_database():
    db_info = {'exists': os.path.exists(DB_PATH)}
    if not db_info['exists']: return db_info
    db_info['size_mb'] = round(os.path.getsize(DB_PATH)/1024/1024, 2)
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        db_info['integrity'] = conn.execute('PRAGMA integrity_check').fetchone()[0]
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        db_info['tables'] = {}
        for t in tables:
            db_info['tables'][t[0]] = conn.execute(f'SELECT COUNT(*) FROM "{t[0]}"').fetchone()[0]
        conn.close()
    except Exception as e:
        db_info['error'] = str(e)
    return db_info

def check_recent_file_changes():
    return run_readonly(f"find {WEBSITE_DIR} -maxdepth 2 -name '*.py' -o -name '*.html' -o -name '*.json' -o -name '*.conf' | xargs ls -lt 2>/dev/null | head -20")['stdout']

def check_network():
    checks = {}
    for port in ['8621','8620','8622']:
        checks[f'localhost:{port}'] = run_readonly(f"curl -s -o /dev/null -w '%{{http_code}}' --max-time 5 http://127.0.0.1:{port}/")['stdout']
    checks['external_dns'] = run_readonly("curl -s -o /dev/null -w '%{http_code}' --max-time 5 https://www.baidu.com")['stdout']
    return checks

def check_open_connections():
    return run_readonly('ss -s')['stdout']

def generate_health_summary(diagnosis):
    issues, warnings = [], []
    for svc, status in diagnosis.get('services',{}).items():
        if not status['active']: issues.append(f'🔴 服务 {svc} 未运行 (状态: {status["status"]})')
    mem = diagnosis.get('resources',{}).get('memory_mb',{})
    if isinstance(mem, dict) and 'total' in mem and mem['total']>0:
        pct = mem['used']/mem['total']*100
        if pct>90: issues.append(f'🔴 内存使用率过高: {pct:.1f}%')
        elif pct>80: warnings.append(f'🟡 内存使用率偏高: {pct:.1f}%')
    for line in diagnosis.get('resources',{}).get('disk','').split('\n'):
        parts = line.split()
        if len(parts)>=5:
            try:
                pct=int(parts[4].replace('%',''))
                mount = parts[5] if len(parts)>5 else parts[-1]
                if pct>90: issues.append(f'🔴 磁盘 {mount} 使用率过高: {pct}%')
                elif pct>80: warnings.append(f'🟡 磁盘 {mount} 使用率偏高: {pct}%')
            except: pass
    db = diagnosis.get('database',{})
    if db.get('integrity') and db['integrity']!='ok': issues.append(f"🔴 数据库完整性异常: {db['integrity']}")
    if 'oom_events' in diagnosis.get('logs',{}): issues.append('🔴 检测到 OOM Killer 记录')
    for key, content in diagnosis.get('logs',{}).items():
        if 'Traceback' in content: warnings.append(f'🟡 {key} 包含异常堆栈')
    return {'issues': issues, 'warnings': warnings}

def main():
    start_time = time.time()
    ts = datetime.now()
    diagnosis = {'timestamp': ts.isoformat(), 'script_version': '1.0.0', 'log_window_minutes': LOG_WINDOW_MINUTES}
    checks = [('基础信息',check_basic_info,'basic_info'),('服务状态',check_services,'services'),('系统资源',check_system_resources,'resources'),('端口监听',check_ports,'ports'),('进程状态',check_processes,'processes'),('近期日志',check_recent_logs,'logs'),('数据库健康',check_database,'database'),('网络连通',check_network,'network'),('活跃连接',check_open_connections,'connections'),('近期文件变更',check_recent_file_changes,'recent_changes')]
    for name, func, key in checks:
        print(f'[检查] {name}...')
        try:
            diagnosis[key] = func()
            print(f'  ✓ 完成')
        except Exception as e:
            diagnosis[key] = {'error': str(e)}
            print(f'  ✗ 异常: {e}')
    diagnosis['health_summary'] = generate_health_summary(diagnosis)
    elapsed = round(time.time()-start_time, 2)
    diagnosis['elapsed_seconds'] = elapsed
    os.makedirs(REPORT_DIR, exist_ok=True)
    report_file = os.path.join(REPORT_DIR, f"diagnosis_{ts.strftime('%Y%m%d_%H%M%S')}.json")
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(diagnosis, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n{'='*60}")
    print(f'诊断完成 ({elapsed}s)')
    print(f'报告: {report_file}')
    issues = diagnosis['health_summary']['issues']
    warnings = diagnosis['health_summary']['warnings']
    if issues:
        print(f'\n🔴 严重问题 ({len(issues)}):')
        for i in issues: print(f'  {i}')
    if warnings:
        print(f'\n🟡 警告 ({len(warnings)}):')
        for w in warnings: print(f'  {w}')
    if not issues and not warnings: print('\n✅ 未检测到明显异常')
    return diagnosis

if __name__ == '__main__':
    main()
