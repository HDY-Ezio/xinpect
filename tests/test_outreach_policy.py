#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""外联纠偏守卫：名单性质、群发通道隔离、召回窗口。

背景（2026-11-24）：
  生产上有一个会话在 13:44 用告警账号（163）给 21 家公司发出 19 封冷邮件，
  13:39 又给 8 个注册用户发了召回邮件。代价不是「多发了几封信」——
  163 判异常发信是先限流后封号，封了「服务器出事」那类告警就发不出去，
  而这台机器上跑着扫描器和站点。

  事后查下去，三个问题都不在文案上：
    1. 名单里 6 个是私人 QQ/163 地址 —— 名单是扒来的，没人分辨地址性质；
    2. 群发和告警共用一个发信账号 —— 没有任何东西阻止这件事；
    3. 召回没有时间窗 —— 最老的注册于 9 月 6 日，快 3 个月了，这时候发
       「你注册了但还没扫过」，对方第一反应是「我什么时候注册过这个站」。

  这三条都不是「这次注意到了」能解决的：下次换一批名单、换一个脚本，
  同样的错会再来。所以把三条钉成硬规则，由代码判，不靠人记。

跑法（服务器没装 pytest 也能直接跑）：
  python3 tests/test_outreach_policy.py
  python3 -m pytest tests/test_outreach_policy.py -q
"""
import ast
import contextlib
import os
import sqlite3
import sys
import types

import pytest  # noqa: F401 —— 体检按 pytest 分支挂载（见 tests/test_qa_mount_completeness.py 规则 3），
               # 本文件自身也能 python3 直跑，不依赖 pytest 的 fixture
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from modules import mailbox_policy
from modules.email_sender import _send_mail, bulk_configured


@contextlib.contextmanager
def _env(**kv):
    """临时改环境变量（不依赖 pytest 的 monkeypatch，直跑也能用）。"""
    old = dict((k, os.environ.get(k)) for k in kv)
    for k, v in kv.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _boom(*a, **k):
    raise AssertionError('不该连 SMTP：守卫必须在建连之前就拒绝')


# ── 1. 地址性质 ────────────────────────────────────────────────────────
def test_personal_mailbox_rejected():
    """私人/免费邮箱不能做 B2B 冷邮件收件地址。"""
    for addr in ('89530205@qq.com', 'grass5188@163.com', 'jzsoftit@163.COM',
                 '  someone@gmail.com  ', 'x@126.com', 'a@foxmail.com',
                 'a@outlook.com', 'a@icloud.com'):
        assert mailbox_policy.is_consumer_mailbox(addr), addr
    for addr in ('contact@xiriyun.cn', 'service@ytgkz.cn', 'master@fichtech.com',
                 'linqinqiang@zhumentech.com'):
        assert not mailbox_policy.is_consumer_mailbox(addr), addr


def test_malformed_address_rejected():
    """格式不对的地址同样不能发 —— 除了刷退信率没有任何作用。"""
    for bad in ('', 'no-at-sign', 'a@b', 'a@@b.com', 'a@ b.com', '@x.com', 'a@'):
        assert mailbox_policy.domain_of(bad) == '', repr(bad)
        assert mailbox_policy.is_consumer_mailbox(bad) is False, repr(bad)


def test_split_targets_counts_and_reasons():
    """切名单：能发的进 ok，私人/写错的进 skipped 且带原因（人要看懂）。"""
    items = [
        {'email': 'a@qq.com', 'name': 'A'},
        {'email': 'b@corp.cn', 'name': 'B'},
        {'email': 'broken', 'name': 'C'},
        {'email': 'c@163.com', 'name': 'D'},
        {'email': 'd@acme.com.cn', 'name': 'E'},
    ]
    ok, skipped = mailbox_policy.split_targets(items)
    assert [i['email'] for i in ok] == ['b@corp.cn', 'd@acme.com.cn'], ok
    assert len(skipped) == 3, skipped
    why = dict((i['email'], w) for i, w in skipped)
    assert '私人邮箱' in why['a@qq.com'], why
    assert '私人邮箱' in why['c@163.com'], why
    assert '格式' in why['broken'], why


# ── 2. 群发通道必须独立于告警通道 ──────────────────────────────────────
def test_bulk_channel_must_be_independent():
    """没配 → 不就绪；配成告警账号 → 仍不就绪；换成独立账号 → 才就绪。"""
    with _env(SMTP_USER='alert@163.com', SMTP_PASSWORD='x',
              SMTP_BULK_USER=None, SMTP_BULK_PASSWORD=None, SMTP_BULK_HOST=None):
        ready, why = bulk_configured()
        assert ready is False and '未配置' in why, why

    with _env(SMTP_USER='alert@163.com', SMTP_BULK_USER='alert@163.com',
              SMTP_BULK_PASSWORD='x'):
        ready, why = bulk_configured()
        assert ready is False and '同一个账号' in why, why

    with _env(SMTP_USER='alert@163.com',
              SMTP_BULK_USER='outreach@xingwangzhineng.com', SMTP_BULK_PASSWORD='x',
              SMTP_BULK_HOST='smtp.exmail.qq.com'):
        ready, why = bulk_configured()
        assert ready is True and why == 'ok', why


def test_bulk_send_refuses_before_touching_smtp():
    """拒绝必须发生在建连之前：真连上再失败等于已经发出去了。"""
    import modules.email_sender as es
    orig_ssl, orig_plain = es.smtplib.SMTP_SSL, es.smtplib.SMTP
    es.smtplib.SMTP_SSL = _boom
    es.smtplib.SMTP = _boom
    try:
        with _env(SMTP_USER='alert@163.com', SMTP_PASSWORD='x',
                  SMTP_BULK_USER='alert@163.com', SMTP_BULK_PASSWORD='x'):
            assert es._send_mail('a@b.com', 's', 'h', purpose='bulk') is False
        with _env(SMTP_BULK_USER=None, SMTP_BULK_PASSWORD=None):
            assert es._send_mail('a@b.com', 's', 'h', purpose='bulk') is False
    finally:
        es.smtplib.SMTP_SSL, es.smtplib.SMTP = orig_ssl, orig_plain


def test_transactional_send_still_uses_alert_account():
    """反向确认：守卫没把事务邮件一起掐掉（验证码、邀请还得能发）。"""
    import modules.email_sender as es
    orig_ssl = es.smtplib.SMTP_SSL

    class FakeSMTP(object):
        def __init__(self, *a, **k):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def login(self, *a):
            pass
        def sendmail(self, *a):
            pass

    es.smtplib.SMTP_SSL = FakeSMTP
    try:
        with _env(SMTP_USER='alert@163.com', SMTP_PASSWORD='x'):
            assert es._send_mail('u@example.com', 's', 'h') is True
    finally:
        es.smtplib.SMTP_SSL = orig_ssl


def test_cold_outreach_declares_bulk_purpose():
    """外联脚本每个发送点都必须声明 purpose='bulk'。

    脚本按 .gitignore 不入库（名单里有别人的联系方式），文件不在就明说跳过，
    不装成通过。
    """
    p = os.path.join(ROOT, 'scripts', 'cold_outreach.py')
    if not os.path.exists(p):
        print('[跳过·不在库] scripts/cold_outreach.py 不存在，本条不适用')
        return
    tree = ast.parse(open(p, encoding='utf-8').read())
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and getattr(n.func, 'id', '') == '_send_mail']
    assert calls, '外联脚本里没找到发送调用'
    for c in calls:
        kws = dict((k.arg, k.value) for k in c.keywords)
        assert 'purpose' in kws, '发送调用没声明 purpose（会默认落到告警账号）'
        assert getattr(kws['purpose'], 'value', None) == 'bulk', '外联发送没走群发通道'


# ── 3. 召回窗口 ────────────────────────────────────────────────────────
def _load_recall():
    """直接编译源码，不走 importlib 的字节码缓存。

    踩过的坑（2026-11-24）：造坏时把 `RECALL_WINDOW_DAYS = 7` 改成 `0`
    —— 长度一样、改完在同一秒内还原、mtime 只精确到秒，
    于是 pyc 校验通过、加载的是坏例那份字节码：造坏判红了，还原后仍然红。
    守卫读源码才不会被同秒内的两次写骗过去。
    """
    p = os.path.join(ROOT, 'scripts', 'recall_never_scanned.py')
    if not os.path.exists(p):
        return None
    src = open(p, encoding='utf-8').read()
    ns = {'__name__': 'recall_probe', '__file__': p}
    exec(compile(src, p, 'exec'), ns)
    return types.SimpleNamespace(
        **dict((k, v) for k, v in ns.items() if not k.startswith('__')))


def test_recall_window_excludes_stale_users():
    """注册 1 天的人要召回；注册 60 天的不要（那不是召回，是打扰）。"""
    mod = _load_recall()
    if mod is None:
        print('[跳过·不在库] scripts/recall_never_scanned.py 不存在，本条不适用')
        return
    db = sqlite3.connect(':memory:')
    db.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, created_at TEXT)')
    db.execute('CREATE TABLE scans (user_id INTEGER)')
    db.execute(mod.DDL)
    now = datetime.now()
    fmt = '%Y-%m-%d %H:%M:%S'
    fresh = (now - timedelta(days=1)).strftime(fmt)
    stale = (now - timedelta(days=60)).strftime(fmt)
    db.execute('INSERT INTO users VALUES (1,?,?)', ('fresh@corp.cn', fresh))
    db.execute('INSERT INTO users VALUES (2,?,?)', ('old@corp.cn', stale))
    db.execute('INSERT INTO users VALUES (3,?,?)', ('test_123@test.com', fresh))
    rows, blocked = mod._targets(db, 24, 1)
    assert [r[1] for r in rows] == ['fresh@corp.cn'], rows
    assert blocked == 1, blocked   # 测试账号不计入「被窗口挡掉」


def test_recall_window_zero_is_explicit_bypass():
    """--max-days 0 才不限窗口；默认必须有窗口，防止有人把默认值改没。"""
    mod = _load_recall()
    if mod is None:
        print('[跳过·不在库] scripts/recall_never_scanned.py 不存在，本条不适用')
        return
    assert mod.RECALL_WINDOW_DAYS == 7, mod.RECALL_WINDOW_DAYS
    db = sqlite3.connect(':memory:')
    db.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, created_at TEXT)')
    db.execute('CREATE TABLE scans (user_id INTEGER)')
    db.execute(mod.DDL)
    fmt = '%Y-%m-%d %H:%M:%S'
    db.execute('INSERT INTO users VALUES (2,?,?)',
               ('old@corp.cn', (datetime.now() - timedelta(days=60)).strftime(fmt)))
    rows, blocked = mod._targets(db, 24, 1, max_days=0)
    assert len(rows) == 1 and blocked == 0, (rows, blocked)


TESTS = [v for k, v in sorted(globals().items()) if k.startswith('test_') and callable(v)]


def main():
    passed = failed = 0
    for fn in TESTS:
        try:
            fn()
        except AssertionError as exc:
            failed += 1
            print('FAIL %-50s %s' % (fn.__name__, exc))
        except Exception as exc:
            failed += 1
            print('ERROR %-49s %r' % (fn.__name__, exc))
        else:
            passed += 1
            print('ok   %s' % fn.__name__)
    print('\n%d 项通过，%d 项失败' % (passed, failed))
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
