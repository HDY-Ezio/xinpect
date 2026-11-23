# -*- coding: utf-8 -*-
"""健康检查「耐心」的守卫。

钉住 2026-11-14 的两次 P0 误报（11:30:12、11:45:12 各一次）：
  巡检报「官网健康检查失败: HTTP 000」，而同一秒官网日志里 /pricing、/login 全是 200。

根因不是网站挂了，是两道预算撞在一起：
  官网 /health 内部探引擎最多等 5 秒（引擎在跑扫描时真的要 5 秒才回），
  巡检 curl 也正好等 5 秒。谁先到期谁说话——巡检先放弃，得 000，报「挂了」。
  健康接口的响应时间如果超过调用方的耐心，调用方永远拿不到真实答案。

本文件钉住四件事：
1. 健康接口探引擎的预算必须命名（不许再写裸数字）、必须够小
2. 巡检的耐心必须明显大于那个预算，且 000 必须再探一次
3. 真慢和真死要能分开：慢一次就过，死两次都不通
4. 告警文字必须说清楚看到了什么（打不通几次、当时几个任务在跑）

不依赖 pytest fixture：QA 里 pytest 与直跑两个分支都要能过。
"""
import http.server
import json
import re
import socket
import sys
import threading
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent
if str(SITE) not in sys.path:
    sys.path.insert(0, str(SITE))

import critical_path_monitor as mon  # noqa: E402


def _probe_budget():
    src = (SITE / 'app.py').read_text(encoding='utf-8')
    m = re.search(r'^_SCANNER_PROBE_TIMEOUT_SECONDS\s*=\s*([0-9.]+)', src, re.M)
    assert m, 'app.py 里找不到命名常量 _SCANNER_PROBE_TIMEOUT_SECONDS（探引擎的预算必须有个名字）'
    return float(m.group(1)), src


def test_probe_budget_is_small_and_used():
    """探引擎的预算必须够小，而且 health 真的用它了。"""
    budget, src = _probe_budget()
    assert 0 < budget <= 2.0, '探引擎预算 %ss 太大：引擎一忙，健康接口就跟着卡' % budget
    assert 'timeout=_SCANNER_PROBE_TIMEOUT_SECONDS' in src, \
        'health_check 没用这个常量，改成裸数字等于把这次的事故重新种一遍'


def test_monitor_patience_exceeds_probe_budget():
    """巡检的耐心必须明显大于健康接口自己的预算，否则它永远只能收到超时。"""
    budget, _ = _probe_budget()
    assert mon.WEBSITE_HEALTH_TIMEOUT >= budget + 5, \
        '巡检只等 %ss，健康接口探引擎就要 %ss，余量不够' % (
            mon.WEBSITE_HEALTH_TIMEOUT, budget)
    assert mon.WEBSITE_HEALTH_RETRY_TIMEOUT > mon.WEBSITE_HEALTH_TIMEOUT, \
        '重试的那一次必须给更长的时间，否则重试没有意义'


def test_healthy_site_is_one_shot():
    """站点正常时只探一次，不许无谓地多打一枪。"""
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({'status': 'ok', 'active_scans': 0}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        url = 'http://127.0.0.1:%d/health' % srv.server_address[1]
        attempts = mon.check_http_detailed(url, first_timeout=3, retry_timeout=5)
        assert len(attempts) == 1, '站点正常却探了 %d 次' % len(attempts)
        assert attempts[0]['code'] == '200', attempts[0]
    finally:
        srv.shutdown()
        srv.server_close()


def test_dead_site_is_retried_then_reported():
    """打不通必须再探一次；两次都不通才允许报，且耗时要如实记下来。"""
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    holder.bind(('127.0.0.1', 0))
    holder.listen(8)
    port = holder.getsockname()[1]
    stop = threading.Event()

    def swallow():
        # 接受连接但永不回话：模拟「进程在、但卡死了」
        holder.settimeout(0.2)
        while not stop.is_set():
            try:
                conn, _ = holder.accept()
                conn.settimeout(0.2)
            except Exception:
                continue

    threading.Thread(target=swallow, daemon=True).start()
    try:
        url = 'http://127.0.0.1:%d/health' % port
        attempts = mon.check_http_detailed(url, first_timeout=0.3, retry_timeout=0.4)
        assert len(attempts) == 2, '只探了 %d 次就下结论，正是误报的来源' % len(attempts)
        assert all(a['code'] == '000' for a in attempts), attempts
        assert attempts[0]['elapsed'] >= 0.25, '第一次的耗时要如实记录: %s' % attempts[0]
        text = mon.describe_health(attempts)
        assert '2 次打不通' in text, '告警没说打了几次: %s' % text
    finally:
        stop.set()
        holder.close()


def test_alert_text_says_what_was_seen():
    """告警要能照着干活：当时几个任务在跑、引擎什么状态。"""
    slow = [{'code': '000', 'elapsed': 10.0, 'body': ''},
            {'code': '200', 'elapsed': 0.4,
             'body': json.dumps({'status': 'ok', 'active_scans': 3,
                                 'scanner': {'status': 'busy'}})}]
    text = mon.describe_health(slow)
    assert 'HTTP 200' in text, text
    assert '在途任务=3' in text, text
    assert '引擎=busy' in text, text


def test_every_caller_waits_longer_than_the_probe():
    """凡是去探 8621/health 的脚本，耐心都必须明显大于探引擎的预算。

    只盯住巡检一个文件是治症状；真正的病是「调用方给的耐心比接口自己的耗时还短」，
    所以这台机器上每个探官网健康的脚本都要守同一条线。
    """
    budget, _ = _probe_budget()
    floor = budget + 2
    offenders = []
    for path in SITE.rglob('*'):
        if path.is_dir() or path.suffix not in ('.sh', '.py'):
            continue
        part = str(path)
        if '/tests/' in part or path.name == 'test_health_check_budget.py':
            continue
        try:
            text = path.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue
        for no, line in enumerate(text.splitlines(), 1):
            if '8621' not in line or 'health' not in line.lower():
                continue
            m = re.search(r'(?:--max-time|-m)\s+([0-9.]+)', line)
            if not m:
                continue
            waited = float(m.group(1))
            if waited < floor:
                offenders.append('%s:%d 只等 %ss' % (path.relative_to(SITE), no, waited))
    assert not offenders, '这些探官网健康的地方耐心不够（至少要 %ss）: %s' % (
        round(floor, 1), '；'.join(offenders))


if __name__ == '__main__':
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith('test_')]
    bad = 0
    for name, fn in fns:
        try:
            fn()
            print('  ok   %s' % name)
        except AssertionError as e:
            bad += 1
            print('  FAIL %s: %s' % (name, e))
    print('%d 条用例，失败 %d 条' % (len(fns), bad))
    raise SystemExit(1 if bad else 0)
