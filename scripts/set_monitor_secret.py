#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""交互式更换监控告警的邮箱授权码。

为什么要有这个脚本：2026-11-23 发现三个监控脚本把 163 授权码写死在源码里，
并随代码进了公开仓库。凭据已迁到 /etc/xinpect/monitor.env，但「代码里不再有」
不等于「这个码还安全」——必须重置。重置后需要有办法把新值填进去，且不能
经过命令行参数（会进 shell 历史）或聊天记录。

做法：
- 新值用 getpass 输入，不回显、不落盘到临时明文、不进 history
- 写入前先用新值真登录一次 SMTP，登录失败就不写——避免填错把告警通道弄哑
- 原子写入（临时文件 + rename），保留原权限与属组
- 只改 SMTP_PASSWORD 一行，其余键与注释原样保留

用法：
    sudo python3 scripts/set_monitor_secret.py           # 更换授权码
    sudo python3 scripts/set_monitor_secret.py --check   # 只看现状，不改
"""
import getpass
import os
import shutil
import smtplib
import sys
import tempfile
import time

ENV_PATH = '/etc/xinpect/monitor.env'
BAK_DIR = '/root/.xinpect_patch_bak'


def read_conf(path):
    """按行读，保留顺序与注释；返回 (行列表, 键值)。"""
    lines = []
    conf = {}
    with open(path, encoding='utf-8') as f:
        for raw in f:
            line = raw.rstrip('\n')
            lines.append(line)
            s = line.strip()
            if s and not s.startswith('#') and '=' in s:
                k, v = s.split('=', 1)
                conf[k.strip()] = v.strip().strip('"').strip("'")
    return lines, conf


def replace_key(lines, key, value):
    out, done = [], False
    for line in lines:
        s = line.strip()
        if not done and s and not s.startswith('#') and s.split('=', 1)[0].strip() == key:
            out.append('%s=%s' % (key, value))
            done = True
        else:
            out.append(line)
    if not done:
        out.append('%s=%s' % (key, value))
    return out


def try_login(host, port, user, password):
    """真登录一次，不发信。返回 (是否成功, 说明)。"""
    try:
        s = smtplib.SMTP_SSL(host, int(port), timeout=20)
        try:
            s.login(user, password)
        finally:
            try:
                s.quit()
            except Exception:
                pass
        return True, '登录成功'
    except smtplib.SMTPAuthenticationError as e:
        return False, '认证被拒：%s' % (str(e)[:90],)
    except Exception as e:  # noqa: BLE001
        return False, '连不上或超时：%s: %s' % (type(e).__name__, str(e)[:80])


def write_atomic(path, lines):
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.monitor.env.')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
            f.write('\n'.join(lines) + '\n')
        # 沿用原文件的属主与权限：640 root:xinpect-monitor
        st = os.stat(path)
        os.chmod(tmp, st.st_mode & 0o7777)
        try:
            os.chown(tmp, st.st_uid, st.st_gid)
        except PermissionError:
            pass
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def main(argv):
    if os.geteuid() != 0:
        print('需要 root：sudo python3 %s' % (argv[0],))
        return 2
    if not os.path.isfile(ENV_PATH):
        print('配置文件不存在：%s' % ENV_PATH)
        return 2

    lines, conf = read_conf(ENV_PATH)
    host = conf.get('SMTP_HOST', 'smtp.163.com')
    port = conf.get('SMTP_PORT', '465')
    user = conf.get('SMTP_USER', '')
    cur = conf.get('SMTP_PASSWORD', '')

    print('配置文件：%s' % ENV_PATH)
    print('  服务器：%s:%s' % (host, port))
    print('  账号　：%s' % (user or '(未配置)'))
    print('  当前码：%s' % ('已配置（%d 位）' % len(cur) if cur else '(空)'))
    if '--check' in argv:
        if cur:
            ok, msg = try_login(host, port, user, cur)
            print('  现用码有效性：%s' % msg)
        return 0
    if not user:
        print('SMTP_USER 没配置，先补上再换码')
        return 2

    print('\n到 163 邮箱 → 设置 → POP3/SMTP/IMAP → 重置授权码，然后把新码粘贴到这里。')
    print('（输入不回显；直接回车放弃）')
    try:
        new = getpass.getpass('新授权码：').strip()
    except (KeyboardInterrupt, EOFError):
        print('\n已取消')
        return 1
    if not new:
        print('没有输入，已取消')
        return 1
    if new == cur:
        print('与当前值相同，无需更换')
        return 1
    if len(new) < 8:
        print('长度 %d，短得不像授权码，已取消' % len(new))
        return 1

    print('正在用新码登录验证……')
    ok, msg = try_login(host, port, user, new)
    print('  %s' % msg)
    if not ok:
        print('验证没过，什么都不写。请确认复制完整、没有多余空格。')
        return 2

    os.makedirs(BAK_DIR, exist_ok=True)
    bak = os.path.join(BAK_DIR, 'monitor.env.' + time.strftime('%Y%m%d_%H%M%S'))
    shutil.copy2(ENV_PATH, bak)
    os.chmod(bak, 0o600)

    write_atomic(ENV_PATH, replace_key(lines, 'SMTP_PASSWORD', new))
    print('已写入 %s（旧文件备份在 %s）' % (ENV_PATH, bak))

    # 写完再读一遍确认，并真发一封
    _, conf2 = read_conf(ENV_PATH)
    if conf2.get('SMTP_PASSWORD') != new:
        print('!! 写入后校验不一致，请检查')
        return 3
    print('回读校验通过。发一封测试邮件……')
    try:
        from email.mime.text import MIMEText
        msg = MIMEText('授权码已重置，这封用于确认告警通道仍然可用。\n', 'plain', 'utf-8')
        msg['Subject'] = '[煋鉴] 授权码重置后的通道验证'
        msg['From'] = user
        msg['To'] = conf2.get('ALERT_TO', user)
        s = smtplib.SMTP_SSL(host, int(port), timeout=30)
        s.login(user, new)
        s.send_message(msg)
        s.quit()
        print('测试邮件已发出，去收件箱确认一眼。')
    except Exception as e:  # noqa: BLE001
        print('测试邮件没发出去：%s: %s（配置本身已写好）' % (type(e).__name__, e))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
