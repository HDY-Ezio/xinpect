#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""端到端验证：报告页维度卡在「引擎没跑」时的真实表现。

为什么不能只跑单元测试：`_build_dimensions` 拿到了 correct 的字典，
不等于用户打开 /report/<id> 看得见。中间还隔着落库白名单、模板渲染、
以及「这个字段到底有没有存进 results」。这三层任何一层断了，
页面上看起来都是「一切正常」。

验证两件事：
  A. 真扫一份有漏洞的代码 → 报告页照常出分数（不能把正常报告也判成未检测）
     必须用 deep 档：quick 只请求 E1/E4/E5/E6，安全引擎压根不在场，
     那种情况下 E2 卡本来就是「升级解锁」，验证不到台账逻辑。
  B. 把这份报告的引擎台账改成「E2 没跑」→ 报告页必须显示「未检测（无结果）」，
     且安全卡的位置不能是 100
"""
import json
import sqlite3
import sys
import time

sys.path.insert(0, '/opt/xinpect-website')
from app import app                       # noqa: E402
from modules.constants import DB_PATH     # noqa: E402

CODE = '''from flask import Flask, request
import sqlite3

app = Flask(__name__)
SECRET_KEY = "hardcoded-secret-123456"


@app.route('/user/<uid>')
def user(uid):
    db = sqlite3.connect('x.db')
    row = db.execute('SELECT * FROM users WHERE id=' + uid).fetchone()
    return str(row)
'''
FILENAME = 'demo_idor.py'


def _vip_user():
    """返回 (id, email, session_version)。

    session_version 必须一起塞进测试 session：get_current_user 会拿它和
    库里的值比对，不一致就 session.clear() 返回 None。少了这个，测试里
    永远是「未登录」，vip=False，扫描档位退化成 free，E2 根本不请求 ——
    这正是第一次验证只跑到 E1/E4/E5/E6 的原因。
    """
    db = sqlite3.connect(DB_PATH)
    row = db.execute(
        "SELECT id, email, COALESCE(session_version, 1) FROM users WHERE is_vip=1 "
        "AND (vip_expire_at IS NULL OR vip_expire_at > datetime('now')) "
        "ORDER BY id LIMIT 1"
    ).fetchone()
    db.close()
    return row


def _wait_done(sid, timeout=180):
    db = sqlite3.connect(DB_PATH)
    t0 = time.time()
    last = ''
    while time.time() - t0 < timeout:
        row = db.execute(
            'SELECT scan_status, scan_error FROM scans WHERE scan_id=?', (sid,)
        ).fetchone()
        if row:
            last = row[0]
            if row[0] in ('completed', 'failed'):
                db.close()
                return row[0], row[1] or ''
        time.sleep(2)
    db.close()
    return last or 'timeout', ''


def _brain_block(html, bid, nxt):
    if f'data-brain="{bid}"' not in html:
        return ''
    return html.split(f'data-brain="{bid}"', 1)[1].split(f'data-brain="{nxt}"', 1)[0]


def main():
    user = _vip_user()
    if not user:
        print('FAIL: 没有可用的 VIP 账号')
        return 1
    uid, email, sess_ver = user
    print(f'账号: {uid} {email} session_version={sess_ver}')

    db = sqlite3.connect(DB_PATH)
    ev_before = db.execute('SELECT COALESCE(MAX(id),0) FROM visitor_events').fetchone()[0]
    db.close()

    client = app.test_client()
    with client.session_transaction() as s:
        s['user_id'] = uid
        s['session_version'] = sess_ver
        s['_csrf_token'] = 'x' * 64

    r = client.post(
        '/scan',
        data={'code': CODE, 'filename': FILENAME, 'language': 'python', 'scan_mode': 'deep'},
        headers={'X-Requested-With': 'XMLHttpRequest'},
    )
    body = r.get_data(as_text=True)
    print('提交:', r.status_code, body[:160])
    if r.status_code != 200:
        return 1
    sid = (r.get_json() or {}).get('scan_id') or (r.get_json() or {}).get('id')
    if not sid:
        print('FAIL: 没拿到 scan_id')
        return 1
    print('scan_id:', sid)

    status, err = _wait_done(sid)
    print('扫描状态:', status, err[:200])
    if status != 'completed':
        return 1

    db = sqlite3.connect(DB_PATH)
    res = json.loads(db.execute('SELECT results FROM scans WHERE scan_id=?', (sid,)).fetchone()[0])
    print('落库字段 engines:', 'engines' in res)
    print('engine 台账:', json.dumps(res.get('engines') or {}, ensure_ascii=False)[:400])
    print('E2 检出条数:', len([i for i in res.get('issues') or [] if str(i.get('brain_id')) == '2']))
    db.close()

    ok = True

    # ---- A. 正常报告：照常出分数 ----
    r = client.get(f'/report/{sid}')
    html = r.get_data(as_text=True)
    print('报告页:', r.status_code, 'len', len(html))
    e2 = _brain_block(html, '2', '3')
    if '未检测（无结果）' in html:
        print('FAIL(A): 正常报告出现了「未检测（无结果）」')
        ok = False
    else:
        print('PASS(A): 正常报告没有误报未检测')
    print('  安全卡片段:', ' '.join(e2.split())[:180])

    # ---- B. 模拟 E2 没跑 ----
    db = sqlite3.connect(DB_PATH)
    engines = res.get('engines') or {}
    engines['2'] = {'executed': False, 'issues': 0, 'error': '', 'reason': 'degraded'}
    res['engines'] = engines
    db.execute('UPDATE scans SET results=? WHERE scan_id=?',
               (json.dumps(res, ensure_ascii=False), sid))
    db.commit()
    db.close()

    r = client.get(f'/report/{sid}')
    html2 = r.get_data(as_text=True)
    e2b = _brain_block(html2, '2', '3')
    print('改台账后安全卡:', ' '.join(e2b.split())[:220])

    if '未检测（无结果）' not in html2:
        print('FAIL(B): 引擎没跑，页面没显示「未检测（无结果）」')
        ok = False
    else:
        print('PASS(B): 页面显示了「未检测（无结果）」')

    if '>100<' in e2b:
        print('FAIL(B): 引擎没跑，安全卡仍显示 100 分')
        ok = False
    else:
        print('PASS(B): 安全卡没有显示 100 分')

    if '部分未检测' not in html2:
        print('FAIL(B): 三层卡没显示「部分未检测」')
        ok = False
    else:
        print('PASS(B): 三层卡显示了「部分未检测」')

    # ---- 清理 ----
    db = sqlite3.connect(DB_PATH)
    db.execute('DELETE FROM scans WHERE scan_id=?', (sid,))
    n_ev = db.execute('DELETE FROM visitor_events WHERE id > ?', (ev_before,)).rowcount
    db.commit()
    db.close()
    print(f'已清理测试扫描记录，顺带清理埋点 {n_ev} 条')

    print('RESULT:', 'OK' if ok else 'FAILED')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
