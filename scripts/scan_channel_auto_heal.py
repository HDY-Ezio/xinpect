#!/usr/bin/env python3
"""
煋鉴扫描通道自动修复脚本
读取健康检查结果，对已知问题自动修复，记录修复动作
"""

import json
import subprocess
import time
import os
from datetime import datetime

HEALTH_FILE = '/opt/xinpect-website/data/scan_channel_health.json'
HEAL_LOG = '/opt/xinpect-website/data/auto_heal_history.json'

def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return None

def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def cmd(command, timeout=10):
    """执行运维命令。仅允许 str 类型，带前缀白名单校验。"""
    if not isinstance(command, str):
        return False, '', 'blocked: command must be str'
    _allowed = ("ss ", "grep", "cd ", "nohup", "sudo", "pgrep", "python3",
                "docker", "systemctl", "nginx", "pkill", "curl")
    if not any(command.strip().startswith(p) for p in _allowed):
        return False, '', f'blocked: command prefix not allowed'
    try:
        r = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, r.stdout.strip(), r.stderr.strip()
    except:
        return False, '', 'timeout'

def get_actual_port():
    ok, out, _ = cmd('ss -tlnp | grep python | grep server | head -1')
    if ok and ':' in out:
        return out.split(':')[1].split()[0].strip()
    return None

def get_nginx_port():
    ok, out, _ = cmd('grep -oP "127.0.0.1:\\K\\d+" /etc/nginx/sites-enabled/xinpect-subdomain | head -1')
    if ok and out:
        return out.strip()
    return None

def heal_port_mismatch():
    nginx_port = get_nginx_port()
    actual_port = get_actual_port()
    fixes = []

    if not actual_port and nginx_port:
        # xinpect-pay 没在运行
        ok, _, _ = cmd('cd /opt/xinpect-pay && nohup python3 server.py > /tmp/xinpect-pay.log 2>&1 &')
        time.sleep(3)
        new_port = get_actual_port()
        if new_port:
            fixes.append(f'xinpect-pay 已重启，监听端口 {new_port}')
        else:
            fixes.append('xinpect-pay 重启失败，需人工介入')
    elif actual_port and nginx_port and actual_port != nginx_port:
        # 端口不一致：统一以 nginx 配置为准
        fixes.append(f'端口不一致: nginx={nginx_port}, 实际={actual_port}')
        ok, _, _ = cmd(f"sudo sed -i 's/^PORT=.*/PORT={nginx_port}/' /opt/xinpect-pay/.env")
        cmd("sudo pkill -f 'xinpect-pay.*server.py' 2>/dev/null || true")
        time.sleep(1)
        cmd('cd /opt/xinpect-pay && nohup python3 server.py > /tmp/xinpect-pay.log 2>&1 &')
        time.sleep(3)
        new_port = get_actual_port()
        if new_port == nginx_port:
            fixes.append(f'已修复: 端口统一为 {nginx_port}')
        else:
            fixes.append(f'修复失败: nginx={nginx_port} actual={new_port}')
    return fixes

def heal_nginx_error():
    fixes = []
    ok, _, _ = cmd('pgrep nginx')
    if not ok:
        ok, _, err = cmd('sudo systemctl start nginx')
        if ok:
            fixes.append('nginx 已重启')
        else:
            fixes.append(f'nginx 启动失败: {err}')
    else:
        ok, out, err = cmd('sudo nginx -t')
        if not ok:
            fixes.append(f'nginx 配置错误: {err}')
        else:
            ok, _, _ = cmd('sudo systemctl reload nginx')
            if ok:
                fixes.append('nginx 已重载配置')
    return fixes

def heal_service_restart(service_name, port, display_name):
    fixes = []
    ok, out, _ = cmd(f'ss -tlnp | grep :{port}')
    if not out:
        if 'xinpect' in service_name and 'scanner' not in service_name:
            cmd(f'cd /opt/{service_name} && nohup python3 server.py > /tmp/{service_name}.log 2>&1 &')
        else:
            cmd(f'sudo docker restart {service_name} 2>/dev/null')
        time.sleep(3)
        ok2, out2, _ = cmd(f'ss -tlnp | grep :{port}')
        if out2:
            fixes.append(f'{display_name} 已恢复 (端口 {port})')
        else:
            fixes.append(f'{display_name} 恢复失败，需人工介入')
    return fixes

def main():
    health = load_json(HEALTH_FILE)
    if not health:
        return {'error': '无法读取健康检查文件'}

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
    all_fixes = []
    status = health.get('status', 'unknown')

    if status == 'ok':
        return {'timestamp': timestamp, 'status': 'ok', 'fixes': [], 'message': '一切正常，无需修复'}

    checks = health.get('checks', {})

    # 1. xinpect-pay 端口/服务修复
    if not checks.get('xinpect_pay_port', {}).get('ok', True) or \
       not checks.get('xinpect_pay_check', {}).get('ok', True):
        all_fixes.extend(heal_port_mismatch())

    # 2. nginx 修复
    if not checks.get('nginx_check', {}).get('ok', True):
        all_fixes.extend(heal_nginx_error())

    # 3. 免费扫描（依赖 xinpect-pay，如果上面没修好就单独处理）
    if not checks.get('free_scan_check', {}).get('ok', True) and not all_fixes:
        all_fixes.extend(heal_service_restart('xinpect-pay', 8765, '免费扫描通道'))

    # 4. 付费扫描
    if not checks.get('paid_scan_check', {}).get('ok', True) and not all_fixes:
        all_fixes.extend(heal_service_restart('xinpect-pay', 8765, '付费扫描通道'))

    # 5. 扫描器修复
    if not checks.get('scanner_green_check', {}).get('ok', True):
        cmd('sudo docker restart xinpect-scanner-green 2>/dev/null')
        all_fixes.append('scanner-green 尝试重启')
    if not checks.get('scanner_blue_check', {}).get('ok', True):
        cmd('sudo docker restart xinpect-scanner-blue 2>/dev/null')
        all_fixes.append('scanner-blue 尝试重启')

    # 6. 网站前端
    if not checks.get('website_check', {}).get('ok', True):
        all_fixes.extend(heal_service_restart('xinpect-website', 8621, '网站前端'))

    # 修复后重新跑健康检查
    time.sleep(2)
    cmd('python3 /opt/xinpect-website/scripts/scan_channel_health_check.py')
    recheck = load_json(HEALTH_FILE)
    new_status = recheck.get('status', 'unknown') if recheck else 'unknown'

    result = {
        'timestamp': timestamp,
        'status_before': status,
        'status_after': new_status,
        'fixes_applied': all_fixes,
        'fixed_count': len([f for f in all_fixes if '恢复' in f or '重启' in f or '修复' in f or '重载' in f]),
        'failed_count': len([f for f in all_fixes if '失败' in f or '需人工' in f])
    }

    # 记录到历史
    history = load_json(HEAL_LOG) or []
    history.append(result)
    history = history[-50:]
    save_json(HEAL_LOG, history)

    return result

if __name__ == '__main__':
    result = main()
    print(json.dumps(result, ensure_ascii=False, indent=2))
