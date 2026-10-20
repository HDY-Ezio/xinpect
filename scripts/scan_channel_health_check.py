#!/usr/bin/env python3
"""煋鉴全链路健康检查 — 免费+付费扫描+支付+扫描器 全覆盖"""
import json, os, socket, sys
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

DATA_DIR = '/opt/xinpect-website/data'
RESULT_FILE = os.path.join(DATA_DIR, 'scan_channel_health.json')
ALERT_THRESHOLD = 3

CHECKS = [
    # === 核心服务端口 ===
    {'name': 'xinpect-pay:8765(X402付费+支付+免费入口)', 'type': 'port', 'host': '127.0.0.1', 'port': 8765, 'critical': True},
    {'name': '扫描器green:8620', 'type': 'port', 'host': '127.0.0.1', 'port': 8620, 'critical': True},
    {'name': '扫描器blue:8622', 'type': 'port', 'host': '127.0.0.1', 'port': 8622, 'critical': True},
    {'name': '网站前端:8621', 'type': 'port', 'host': '127.0.0.1', 'port': 8621, 'critical': False},
    # === 免费扫描链路 ===
    {'name': '[免费扫描]nginx→xinpect-pay→scanner链路', 'type': 'http', 'url': 'http://127.0.0.1:80/api/scan/health',
     'host_header': 'xinpect.xingwangzhineng.com', 'expect_key': 'scanner_available', 'expect_value': True, 'critical': True},
    # === 付费扫描链路 ===
    {'name': '[付费扫描]X402健康检查', 'type': 'http', 'url': 'http://127.0.0.1:8765/api/scan/health',
     'expect_key': 'scanner_available', 'expect_value': True, 'critical': True},
    # === 微信支付 ===
    {'name': '[微信支付]回调端点', 'type': 'http_status', 'url': 'http://127.0.0.1:80/api/pay/wechat/notify',
     'method': 'POST', 'host_header': 'xinpect.xingwangzhineng.com', 'expect_status': 200, 'critical': True},
    # === 内部API（合作方） ===
    {'name': '[合作方API]内部扫描接口', 'type': 'http_status', 'url': 'http://127.0.0.1:8765/api/scan/health',
     'expect_status': 200, 'critical': False},
    # === 扫描器直连 ===
    {'name': '扫描器green直连', 'type': 'http', 'url': 'http://127.0.0.1:8620/health', 'expect_key': 'status', 'expect_value': 'ok', 'critical': False},
    {'name': '扫描器blue直连', 'type': 'http', 'url': 'http://127.0.0.1:8622/health', 'expect_key': 'status', 'expect_value': 'ok', 'critical': False},
]

def check_port(host, port, timeout=3):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout); s.connect((host, port)); s.close()
        return True, None
    except Exception as e:
        return False, str(e)

def check_http(url, host_header=None, expect_key=None, expect_value=None, timeout=10):
    try:
        req = Request(url)
        if host_header: req.add_header('Host', host_header)
        resp = urlopen(req, timeout=timeout)
        body = resp.read().decode('utf-8', errors='replace')
        if expect_key and expect_value is not None:
            data = json.loads(body)
            actual = data.get(expect_key)
            if actual != expect_value:
                return False, f'期望{expect_key}={expect_value}, 实际={actual}'
        return True, None
    except HTTPError as e: return False, f'HTTP {e.code}'
    except URLError as e: return False, str(e.reason)
    except Exception as e: return False, str(e)

def check_http_status(url, method='GET', host_header=None, expect_status=200, timeout=10):
    try:
        req = Request(url, method=method)
        if host_header: req.add_header('Host', host_header)
        resp = urlopen(req, timeout=timeout)
        if resp.status != expect_status:
            return False, f'期望HTTP {expect_status}, 实际HTTP {resp.status}'
        return True, None
    except HTTPError as e:
        if e.code == expect_status: return True, None
        return False, f'HTTP {e.code}'
    except Exception as e: return False, str(e)

def load_previous_state():
    try:
        with open(RESULT_FILE) as f: return json.load(f)
    except: return {'consecutive_failures': 0}

def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    prev = load_previous_state()
    prev_failures = prev.get('consecutive_failures', 0)
    results, warnings, critical_failures = {}, [], []
    passed = failed = 0
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    for c in CHECKS:
        name = c['name']
        if c['type'] == 'port':
            ok, err = check_port(c['host'], c['port'])
        elif c['type'] == 'http':
            ok, err = check_http(c['url'], host_header=c.get('host_header'),
                                 expect_key=c.get('expect_key'), expect_value=c.get('expect_value'))
        elif c['type'] == 'http_status':
            ok, err = check_http_status(c['url'], method=c.get('method','GET'),
                                        host_header=c.get('host_header'), expect_status=c.get('expect_status',200))
        else:
            ok, err = False, 'unknown type'
        results[name] = {'status': 'pass' if ok else 'fail', 'error': err, 'critical': c.get('critical',False), 'checked_at': now}
        if ok: passed += 1
        else:
            failed += 1
            if c.get('critical'): critical_failures.append(name)
            warnings.append(f'{name}: {err}')

    consecutive = prev_failures + 1 if critical_failures else 0
    needs_alert = consecutive >= ALERT_THRESHOLD and consecutive > prev_failures

    output = {
        'timestamp': now, 'passed': passed, 'failed': failed, 'total': len(CHECKS),
        'consecutive_failures': consecutive, 'needs_alert': needs_alert,
        'critical_failures': critical_failures, 'warnings': warnings, 'results': results,
    }
    with open(RESULT_FILE, 'w') as f: json.dump(output, f, ensure_ascii=False, indent=2)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    sys.exit(1 if critical_failures else 0)

if __name__ == '__main__': main()
