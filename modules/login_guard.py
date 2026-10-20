"""Xinpect - 认证失败计数与限速（登录 / 验证码校验共用）

根因说明
--------
原实现里登录、找回密码都没有任何失败计数：攻击者可以对同一邮箱无限次
试密码，也可以对 6 位重置码做百万级穷举。这里不采用"给某个 IP 加白名单"
之类的补丁，而是把"失败次数"变成系统的一等数据：

* 每次失败落一条 auth_attempts 记录（scope + 账号 + IP + 时间）
* 判定时按滑动窗口统计，达到阈值即返回剩余等待秒数
* 登录成功清除该账号在该 IP 的失败记录

阈值可用环境变量调整，默认：
    同账号同 IP  15 分钟内 5 次失败
    同 IP 全局    15 分钟内 30 次失败
"""

import os
import sqlite3
from datetime import datetime, timedelta

WINDOW_MINUTES = int(os.environ.get('AUTH_FAIL_WINDOW_MIN', '15'))
ACCOUNT_LIMIT = int(os.environ.get('AUTH_FAIL_ACCOUNT_LIMIT', '5'))
IP_LIMIT = int(os.environ.get('AUTH_FAIL_IP_LIMIT', '30'))

_TABLE_READY = False


def init_attempt_table(db):
    """懒建表：无迁移脚本时的最小改动，只建一次"""
    global _TABLE_READY
    if _TABLE_READY:
        return
    db.execute(
        'CREATE TABLE IF NOT EXISTS auth_attempts ('
        ' id INTEGER PRIMARY KEY AUTOINCREMENT,'
        ' scope TEXT NOT NULL,'
        ' account TEXT NOT NULL,'
        ' ip TEXT NOT NULL,'
        ' created_at TEXT NOT NULL)'
    )
    db.execute(
        'CREATE INDEX IF NOT EXISTS idx_auth_attempts_lookup '
        'ON auth_attempts (scope, account, ip, created_at)'
    )
    db.commit()
    _TABLE_READY = True


def client_ip():
    """取真实来源 IP：只信任 nginx 写入的 X-Real-IP

    直连 8621 端口时 remote_addr 才是真实值；反代场景下 remote_addr
    恒为 127.0.0.1，必须用 nginx 覆盖写入的 X-Real-IP。
    """
    from flask import request
    real_ip = (request.headers.get('X-Real-IP') or '').strip()
    candidate = real_ip or (request.remote_addr or '')
    # sslh 在 443 做 L4 转发，nginx 看到的 remote_addr 恒为 127.0.0.1，
    # 此时"IP"不具区分度。标记为 proxy-blind：只做账号级限速，绝不做
    # 全局 IP 级限速——否则任何人都能靠 30 次失败把全站用户锁死。
    if candidate in ('127.0.0.1', '::1', 'localhost', ''):
        return 'proxy-blind'
    return candidate[:64]


def _window_start():
    return (datetime.now() - timedelta(minutes=WINDOW_MINUTES)).strftime('%Y-%m-%d %H:%M:%S')


def _count(db, where, params):
    return db.execute(
        'SELECT COUNT(*) FROM auth_attempts WHERE created_at > ? AND ' + where,
        (_window_start(),) + params,
    ).fetchone()[0]


def _retry_after(db, where, params):
    row = db.execute(
        'SELECT MIN(created_at) FROM auth_attempts WHERE created_at > ? AND ' + where,
        (_window_start(),) + params,
    ).fetchone()
    if not row or not row[0]:
        return WINDOW_MINUTES * 60
    try:
        first = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        return WINDOW_MINUTES * 60
    remain = int((first + timedelta(minutes=WINDOW_MINUTES) - datetime.now()).total_seconds())
    return max(remain, 1)


def check_blocked(db, scope, account, ip):
    """返回 (blocked, retry_after_seconds)"""
    init_attempt_table(db)
    account = (account or '').lower().strip()[:200]
    ip = (ip or 'unknown')[:64]

    hits = _count(db, 'scope = ? AND account = ? AND ip = ?', (scope, account, ip))
    if hits >= ACCOUNT_LIMIT:
        return True, _retry_after(db, 'scope = ? AND account = ? AND ip = ?', (scope, account, ip))

    # 代理后面拿不到真实 IP 时跳过 IP 级限速（见 client_ip 注释），
    # 账号级限速仍然生效。
    if ip != 'proxy-blind':
        ip_hits = _count(db, 'scope = ? AND ip = ?', (scope, ip))
        if ip_hits >= IP_LIMIT:
            return True, _retry_after(db, 'scope = ? AND ip = ?', (scope, ip))

    return False, 0


def record_failure(db, scope, account, ip):
    init_attempt_table(db)
    db.execute(
        'INSERT INTO auth_attempts (scope, account, ip, created_at) VALUES (?, ?, ?, ?)',
        (scope, (account or '').lower().strip()[:200], (ip or 'unknown')[:64],
         datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
    )
    db.commit()


def clear_failures(db, scope, account, ip):
    init_attempt_table(db)
    db.execute(
        'DELETE FROM auth_attempts WHERE scope = ? AND account = ? AND ip = ?',
        (scope, (account or '').lower().strip()[:200], (ip or 'unknown')[:64]),
    )
    db.commit()


def prune(db, days=7):
    """清理过期记录，避免表无限增长"""
    try:
        init_attempt_table(db)
        cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
        db.execute('DELETE FROM auth_attempts WHERE created_at < ?', (cutoff,))
        db.commit()
    except sqlite3.Error:
        pass
