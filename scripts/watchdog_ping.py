#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""向外部「看门狗」报一次平安。

为什么需要：本站所有监控都长在这台机器上（nginx、systemd、SQLite、cron 全在
同一台）。机器死机、断网、磁盘满到服务停 —— 监控跟着一起死，于是没有人知道，
直到几个小时以后客户来投诉。

这个脚本每 5 分钟往机器外面报一次平安。外面那个服务（healthchecks.io 之类）
收不到就发邮件：**看门的人不在你机器上**，这才是能叫醒人的那种告警。

配置在 /etc/xinpect/watchdog.env：
    WATCHDOG_URL=https://hc-ping.com/xxxxxxxx-xxxx-xxxx

没配就静默跳过（还没开通，不算故障）；配了但报不出去就非 0 退出 ——
cron 日志里留痕，别让它悄悄失效。
"""
import os
import sys
import time
import urllib.error
import urllib.request

CONF = '/etc/xinpect/watchdog.env'
RECORD = '/opt/xinpect-website/tests/reports/last_watchdog_ping.json'


def load_url(path=CONF):
    if not os.path.exists(path):
        return ''
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line.startswith('WATCHDOG_URL='):
                return line.split('=', 1)[1].strip().strip('"').strip("'")
    return ''


def ping(url, timeout=10, attempts=2):
    last = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'xinpect-watchdog/1'})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                if r.status < 400:
                    return True, r.status
                last = 'HTTP %d' % r.status
        except urllib.error.HTTPError as e:
            last = 'HTTP %d' % e.code
        except Exception as e:                      # noqa: BLE001
            last = '%s: %s' % (type(e).__name__, str(e)[:80])
        if i + 1 < attempts:
            time.sleep(2)
    return False, last


def main():
    url = load_url()
    if not url:
        print('未配置看门狗（%s 里没有 WATCHDOG_URL），跳过' % CONF)
        return 0

    ok, info = ping(url)
    if not ok:
        print('❌ 报平安失败：%s' % info)
        return 1

    import json
    os.makedirs(os.path.dirname(RECORD), exist_ok=True)
    tmp = RECORD + '.tmp'
    with open(tmp, 'w') as f:
        json.dump({'epoch': int(time.time()),
                   'when': time.strftime('%Y-%m-%d %H:%M:%S')}, f)
    os.replace(tmp, RECORD)
    return 0


if __name__ == '__main__':
    sys.exit(main())
