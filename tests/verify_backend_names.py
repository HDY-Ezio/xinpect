#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""官网后端完整性守卫（2026-11-06，QA 第 6e 段）。

背景：管理员「错误统计」页一打开就 500，根因是 app.py 漏导入 datetime。
同类问题全站共 6 处，且被 try/except 或假防御吞掉，页面绿灯看不出来。
本守门做四件事，任一不过就 raise AssertionError：

1. 用固定版检查器（scripts/vendor/pyflakes 3.4.0）扫全站运行时 Python，
   「用了没导入的名字」必须为 0；检查器缺失或跑不起来一律判红，不许静默跳过。
2. 不许再有 'datetime' in dir() 这类「看起来防御、实际永远走假值」的写法。
3. 邮件函数签名以 modules/team.py 的真实调用关键字为准，不许两边各写一套。
4. 真实以管理员身份打开 /admin/error-stats：200、字段齐全、匿名 401；
   并验证两封业务邮件都走 _send_mail 唯一出口（只替换发送函数，不真发信）。

--self-test 复制源文件造坏，确认每一种坏法都会被判红。
"""
import argparse
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

WEB = Path('/opt/xinpect-website')
VENDOR = WEB / 'scripts/vendor'
# 生产固定用系统解释器；本地预演可指向另一个解释器，检查器版本仍由 vendor 固定。
PYTHON_BIN = os.environ.get('XP_PYTHON_BIN', '/usr/bin/python3')
ENV_FILE = Path('/etc/xinpect/website.env')
APP_PY = WEB / 'app.py'
TEAM_PY = WEB / 'modules/team.py'
MAIL_PY = WEB / 'modules/email_sender.py'
HELPERS_PY = WEB / 'modules/helpers.py'
REFERRAL_PY = WEB / 'modules/referral.py'
REPORT_KEYS = ('period_days', 'total_errors', 'by_type', 'by_endpoint',
               'unresolved_count', 'unresolved_recent')
FAKE_GUARD = "'datetime' in dir()"


def load_env():
    """自己加载 systemd 环境变量，让守卫不依赖调用方是否 source 过 env。"""
    if not ENV_FILE.is_file():
        return
    for line in ENV_FILE.read_text(encoding='utf-8', errors='replace').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        k = k.strip()
        if k and k not in os.environ:
            os.environ[k] = v.strip().strip('"').strip("'")


def scan_paths():
    out = []
    for p in sorted(WEB.rglob('*.py')):
        rel = p.relative_to(WEB).as_posix()
        if rel.startswith('_archive/') or rel.startswith('scripts/vendor/'):
            continue
        if 'backup' in p.name.lower() or p.name.endswith('.bak'):
            continue
        out.append(p)
    return out


def pyflakes_undefined(paths):
    """返回 (问题列表, 检查器是否成功启动)。"""
    if not (VENDOR / 'pyflakes' / '__init__.py').is_file():
        return ['固定检查器缺失: %s' % (VENDOR / 'pyflakes')], False
    env = dict(os.environ)
    env['PYTHONPATH'] = str(VENDOR) + os.pathsep + env.get('PYTHONPATH', '')
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    r = subprocess.run(
        [PYTHON_BIN, '-m', 'pyflakes'] + [str(p) for p in paths],
        capture_output=True, text=True, env=env)
    allout = r.stdout + r.stderr
    issues = []
    if 'No module named pyflakes' in allout:
        return ['固定检查器无法启动'], False
    if re.search(r'(could not parse|invalid syntax|SyntaxError)', allout, re.I):
        issues.append('检查器有文件解析不了，扫描不完整: ' + allout.strip()[:200])
    for line in allout.splitlines():
        if 'undefined name' in line.lower():
            issues.append(line.strip())
    return issues, True


def text_issues(app_src, mail_src, team_src):
    issues = []
    if FAKE_GUARD in app_src:
        issues.append('假防御复活：' + FAKE_GUARD)
    m = re.search(r'def send_team_invitation_email\(([^)]*)\)', mail_src)
    if not m:
        issues.append('找不到 send_team_invitation_email 定义')
    # team.py 顶部还有一个 `def send_team_invitation_email(*args, **kwargs)` 兜底定义，
    # 只取第一个匹配会把它当成「调用」，关键字集合为空，签名检查就永远假绿。
    # 这里取关键字参数最多的那个调用块，以真实调用方为唯一事实来源。
    keys = set()
    for block in re.findall(r'send_team_invitation_email\s*\((.*?)\)', team_src, re.S):
        found = set(re.findall(r'(\w+)\s*=', block))
        if len(found) > len(keys):
            keys = found
    if not keys:
        issues.append('找不到 team.py 里带关键字参数的真实调用')
    if m and keys:
        params = set(re.findall(r'[A-Za-z_]\w*', m.group(1)))
        missing = keys - params
        if missing:
            issues.append('邮件函数缺少调用方参数: ' + ','.join(sorted(missing)))
    if 'def _send_mail(' not in mail_src or 'send_email(' in mail_src:
        issues.append('SMTP 发送没有收敛到 _send_mail 唯一出口')
    # 一次定义 + 两个业务函数各调用一次；少了就是有函数在偷偷走别的路
    if mail_src.count('_send_mail(') < 3:
        issues.append('不是所有业务邮件都走 _send_mail 唯一出口')
    return issues


def read_all():
    return {
        'app.py': APP_PY.read_text(encoding='utf-8', errors='replace').replace('\r\n', '\n'),
        'modules/email_sender.py': MAIL_PY.read_text(encoding='utf-8', errors='replace').replace('\r\n', '\n'),
        'modules/team.py': TEAM_PY.read_text(encoding='utf-8', errors='replace').replace('\r\n', '\n'),
        'modules/helpers.py': HELPERS_PY.read_text(encoding='utf-8', errors='replace').replace('\r\n', '\n'),
        'modules/referral.py': REFERRAL_PY.read_text(encoding='utf-8', errors='replace').replace('\r\n', '\n'),
    }


def runtime_checks():
    """真实调用：动态检查结果 {name: (bool, detail)}。"""
    res = {}
    load_env()
    sys.path.insert(0, str(WEB))
    os.chdir(str(WEB))
    try:
        import app as appmod
    except Exception as e:
        return {'后端可导入': (False, repr(e))}
    res['后端可导入'] = (True, '')

    con = sqlite3.connect('file:%s?mode=ro' % (WEB / 'xinpect.db'), uri=True)
    try:
        admin = con.execute(
            'SELECT id, email, COALESCE(session_version,1) FROM users '
            'WHERE is_admin=1 LIMIT 1').fetchone()
    finally:
        con.close()
    if not admin:
        return dict(res, **{'存在管理员账号可验证': (False, 'users 表无 is_admin=1')})
    res['存在管理员账号可验证'] = (True, 'user_id=%s' % admin[0])

    c = appmod.app.test_client()
    with c.session_transaction() as s:
        s['user_id'] = admin[0]
        s['session_version'] = admin[2]
        s['user_email'] = admin[1]
    r = c.get('/admin/error-stats?days=7')
    body = r.get_json(silent=True) or {}
    missing = [k for k in REPORT_KEYS if k not in body]
    res['管理员打开错误统计页 = 200 且字段齐'] = (
        r.status_code == 200 and not missing,
        'status=%s 缺字段=%s 响应头=%s' % (r.status_code, missing,
                                        r.get_data(as_text=True)[:160]))
    anon = appmod.app.test_client().get('/admin/error-stats?days=7')
    res['匿名访问错误统计页 = 401'] = (anon.status_code == 401,
                                  'status=%s' % anon.status_code)

    # 邮件：只替换发送出口，绝不真发信
    try:
        from modules import email_sender as es
        seen = []
        orig = es._send_mail

        def fake(to, subj, html_body):
            seen.append((to, subj, html_body))
            return True

        es._send_mail = fake
        try:
            ok1 = es.send_reset_code_email('probe@example.com', '123456')
            ok2 = es.send_team_invitation_email(
                to_email='probe@example.com', team_name='探针团队',
                inviter_email='owner@example.com',
                invite_url='https://xinpect.com/team/invite/probe-token',
                expire_days=7)
        finally:
            es._send_mail = orig
        bodies = [x[2] for x in seen]
        good = (ok1 is True and ok2 is True and len(seen) == 2
                and '123456' in bodies[0]
                and 'probe-token' in bodies[1] and '<a href=' in bodies[1])
        res['两封业务邮件都走唯一出口且内容完整'] = (
            good, 'ok1=%s ok2=%s 调用数=%s' % (ok1, ok2, len(seen)))
    except Exception as e:
        res['两封业务邮件都走唯一出口且内容完整'] = (False, repr(e))
    return res


def normal():
    checks = {}
    paths = scan_paths()
    undef, started = pyflakes_undefined(paths)
    checks['固定检查器可用且扫全站 %d 个 .py' % len(paths)] = (
        started and not any('检查器' in x for x in undef), str(undef[:2]))
    checks['全站「用了没导入的名字」= 0'] = (not undef, '; '.join(undef[:6]))
    src = read_all()
    ti = text_issues(src['app.py'], src['modules/email_sender.py'],
                     src['modules/team.py'])
    checks['无假防御、邮件签名对齐、发送出口唯一'] = (not ti, '; '.join(ti))
    for k, v in runtime_checks().items():
        checks[k] = v
    report('后端完整性守卫', checks)


def self_test():
    """造坏副本：每一种坏法都必须被判红。"""
    src = read_all()
    cases = [
        ('app.py 删掉 datetime 导入', 'app.py',
         'from datetime import datetime\n', ''),
        ('helpers.py 删掉 sqlite3 导入', 'modules/helpers.py',
         'import sqlite3\n', ''),
        ('referral.py 删掉 sqlite3 导入', 'modules/referral.py',
         'import sqlite3\n', ''),
        ('假防御复活', 'app.py',
         "'updated_at': str(datetime.now()),",
         "'updated_at': str(datetime.now()) if 'datetime' in dir() else 'now',"),
        ('邮件函数签名改回旧名', 'modules/email_sender.py',
         'def send_team_invitation_email(to_email, team_name, inviter_email, invite_url, expire_days=7):',
         'def send_team_invitation_email(invitee_email, team_name, inviter_name, invite_link):'),
        ('不存在的发信函数复活', 'modules/email_sender.py',
         'return _send_mail(to_email, subject, html_body)',
         'send_email(to_email, subject, html_body); return True', 2),
        ('团队邀请不再走唯一出口', 'modules/email_sender.py',
         'return _send_mail(to_email, subject, html_body)\n',
         'return False\n', 2),
    ]
    checks = {}
    with tempfile.TemporaryDirectory(prefix='xp_backend_guard_') as td:
        d = Path(td)
        for label, rel, old, new, *rest in cases:
            case_dir = d / re.sub(r'\W+', '_', label)
            case_dir.mkdir()
            copies = {}
            for name, text in src.items():
                p = case_dir / Path(name).name
                p.write_bytes(text.encode('utf-8'))
                copies[name] = p
            target = copies[rel]
            body = target.read_text(encoding='utf-8')
            expect = rest[0] if rest else 1
            n = body.count(old)
            checks['造坏前提成立：' + label] = (n == expect,
                                          '命中 %s 处，期望 %s 处' % (n, expect))
            body = body.replace(old, new, expect)
            target.write_bytes(body.encode('utf-8'))

            mutated = dict(src)
            for name in src:
                mutated[name] = copies[name].read_text(encoding='utf-8')
            undef, _ = pyflakes_undefined(list(copies.values()))
            issues = list(undef) + text_issues(
                mutated['app.py'], mutated['modules/email_sender.py'],
                mutated['modules/team.py'])
            checks['造坏能判红：' + label] = (len(issues) > 0,
                                        '; '.join(issues[:3]))
    report('后端完整性守卫自测', checks)


def report(title, checks):
    bad = []
    for k, (ok, detail) in checks.items():
        print('%s %s%s' % ('[OK]  ' if ok else '[FAIL]', k,
                           ('  <- ' + detail) if (detail and not ok) else ''))
        if not ok:
            bad.append(k)
    print('%s: %d 项, 通过 %d, 失败 %d' % (title, len(checks),
                                       len(checks) - len(bad), len(bad)))
    if bad:
        raise AssertionError('%s 未通过: %s' % (title, '; '.join(bad)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--self-test', action='store_true')
    a = ap.parse_args()
    if a.self_test:
        self_test()
    else:
        normal()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
