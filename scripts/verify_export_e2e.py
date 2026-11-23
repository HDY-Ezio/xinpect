#!/usr/bin/env python3
"""端到端验证：报告页「下载 HTML」与「导出 PDF」两个入口真能用。

不只是断言 200 —— 要证明导出的文件是**能独立打开**的东西：
有 <base>、有正文、数字与网页版一致、不带导航栏。

跑法：sudo -u xinpect-web bash -c 'set -a; . /etc/xinpect/website.env; set +a; python3 scripts/verify_export_e2e.py'
"""
import os
import sqlite3
import sys

BASE = '/opt/xinpect-website'
DB = os.path.join(BASE, 'xinpect.db')
sys.path.insert(0, BASE)

from app import app  # noqa: E402

app.config['TESTING'] = True
app.config['VISITOR_ANALYTICS_ALLOW_TESTING'] = False

ok = 0
fail = 0


def check(cond, msg):
    global ok, fail
    if cond:
        ok += 1
        print(f'  OK   {msg}')
    else:
        fail += 1
        print(f'  FAIL {msg}')


def pick_scan():
    db = sqlite3.connect(DB)
    row = db.execute(
        "SELECT s.scan_id, s.user_id, COALESCE(u.session_version, 1) "
        "FROM scans s LEFT JOIN users u ON u.id = s.user_id "
        "WHERE s.scan_status='completed' AND s.user_id IS NOT NULL "
        "ORDER BY s.id DESC LIMIT 1"
    ).fetchone()
    db.close()
    return row


def main():
    row = pick_scan()
    if not row:
        print('没有可用的已完成报告，跳过')
        return 0
    sid, uid, sess_ver = row
    print(f'样本报告: {sid}  归属用户: {uid}')

    client = app.test_client()
    with client.session_transaction() as s:
        s['user_id'] = uid
        s['session_version'] = sess_ver

    print('[1] 报告页本身')
    page = client.get(f'/report/{sid}')
    check(page.status_code == 200, f'报告页 200（实际 {page.status_code}）')
    page_html = page.get_data(as_text=True)
    check("url_for('download_html_report'" not in page_html, '模板已渲染（不是源码）')
    check(f'/report/{sid}/html' in page_html, '页面里有 HTML 下载链接')
    check('pdf-export-btn' in page_html and 'window.print()' in page_html,
          '页面里有 PDF 导出按钮且接了打印')

    print('[2] 导出 HTML')
    r = client.get(f'/report/{sid}/html')
    check(r.status_code == 200, f'导出 200（实际 {r.status_code}）')
    disp = r.headers.get('Content-Disposition', '')
    check('attachment' in disp, f'是附件下载：{disp}')
    html = r.get_data(as_text=True)
    check('<base href=' in html, '有 <base>，换目录打开不掉样式')
    check('xinpect-export-style' in html, '注入了导出样式（导航/按钮不落盘）')
    check(len(html) > 20000, f'导出件不像空壳（{len(html)} 字节）')

    # 正文一致性：网页版 body 必须完整出现在导出件里
    core = page_html.split('<body', 1)[-1].split('</body>', 1)[0].strip()
    check(bool(core) and core in html, '导出件正文 == 网页版正文（同一份渲染）')

    # 关键数字不能丢
    import re
    score = sqlite3.connect(DB).execute(
        'SELECT score FROM scans WHERE scan_id=?', (sid,)).fetchone()[0]
    check(f'>{score}<' in html, f'导出件里带着总分 {score}')

    out = f'/tmp/xinpect_export_{sid[:8]}.html'
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'  已落盘: {out}（{len(html)} 字节）')

    print('[3] 访问控制')
    anon = app.test_client()
    r2 = anon.get(f'/report/{sid}/html')
    check(r2.status_code == 404, f'匿名导出他人报告被拒（实际 {r2.status_code}）')

    print(f'\n结果：{ok} 通过 / {fail} 失败')
    return 1 if fail else 0


if __name__ == '__main__':
    sys.exit(main())
