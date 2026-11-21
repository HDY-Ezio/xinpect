# -*- coding: utf-8 -*-
"""把所有已完成扫描的报告页全渲染一遍，任何一份不是 200 都要报出来。

为什么要有这个：今晚改了 scan.py 的渲染路径，语法检查过了、单份报告也过了，
但另一份（走的是另一条分支）500 —— 报错是 NameError（漏了一个导入），
`py_compile` 看不出来。只有「每一份都打开一遍」才知道有没有漏。

用法：python3 scripts/audit_reports_render.py [--limit N]
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import modules.helpers as helpers  # noqa: E402
helpers.is_vip_user = lambda: True
import modules.scan as scan_mod      # noqa: E402
scan_mod.is_vip_user = lambda: True

from app import app                  # noqa: E402
from modules.db import get_db        # noqa: E402

LIMIT = None
if '--limit' in sys.argv:
    LIMIT = int(sys.argv[sys.argv.index('--limit') + 1])

app.config['TESTING'] = True
# 捕获异常让 500 不中断整轮，但状态码照实记账
app.config['PROPAGATE_EXCEPTIONS'] = False

with app.app_context():
    db = get_db()
    rows = db.execute(
        "SELECT scan_id, user_id, scan_mode FROM scans "
        "WHERE scan_status='completed' AND results IS NOT NULL "
        "ORDER BY created_at DESC").fetchall()

if LIMIT:
    rows = rows[:LIMIT]

print('要渲染 %d 份报告' % len(rows))
bad = []
t0 = time.time()
with app.test_client() as cli:
    for i, r in enumerate(rows, 1):
        uid = r['user_id'] or 0
        with cli.session_transaction() as sess:
            sess.clear()
            if uid:
                sess['user_id'] = uid
                sess['logged_in'] = True
        try:
            resp = cli.get('/report/%s' % r['scan_id'])
            code = resp.status_code
        except Exception as e:
            code = 'EXC %s: %s' % (type(e).__name__, str(e)[:60])
        if code != 200:
            bad.append((r['scan_id'], r['scan_mode'], code))
            print('  [FAIL] %s (%s) -> %s' % (r['scan_id'][:12], r['scan_mode'], code))
        if i % 50 == 0:
            print('  ...已渲染 %d 份，耗时 %.1fs' % (i, time.time() - t0))

print('\n渲染 %d 份，失败 %d 份，总耗时 %.1fs' % (len(rows), len(bad), time.time() - t0))
if bad:
    print('失败清单：')
    for s, m, c in bad[:20]:
        print('   %s  %s  %s' % (s, m, c))
sys.exit(1 if bad else 0)
