"""会员到期提醒的守卫。

钉住四件事，任何一条破了都会让客户收到错邮件或收不到邮件：
1. 档位边界（剩几天发第几封）
2. 只提醒真正付过费的会员
3. 同一轮每档只发一次，续费后重新开始
4. 发信失败不记账，下一轮必须重试
"""
import sqlite3
from datetime import datetime, timedelta

import modules.membership_reminder as M

NOW = datetime(2026, 11, 13, 21, 0, 0)


def _conn(users):
    """users: [(id, email, is_vip, vip_expire_at, is_admin, is_banned, balance, paid_orders)]"""
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript('''
        CREATE TABLE users (
            id INTEGER PRIMARY KEY, email TEXT, is_vip INTEGER,
            vip_expire_at TEXT, is_admin INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0);
        CREATE TABLE user_credits (user_id INTEGER, balance INTEGER);
        CREATE TABLE orders (user_id INTEGER, status TEXT, plan_name TEXT,
            paid_at TEXT, created_at TEXT);
    ''')
    for uid, email, vip, exp, admin, banned, bal, paid in users:
        conn.execute('INSERT INTO users (id,email,is_vip,vip_expire_at,is_admin,is_banned)'
                     ' VALUES (?,?,?,?,?,?)', (uid, email, vip, exp, admin, banned))
        conn.execute('INSERT INTO user_credits (user_id,balance) VALUES (?,?)', (uid, bal))
        for i in range(paid):
            conn.execute('INSERT INTO orders (user_id,status,plan_name,paid_at,created_at)'
                         ' VALUES (?,?,?,?,?)',
                         (uid, 'paid', '月卡', '2026-10-16 16:46:15', '2026-10-16 16:46:15'))
    conn.commit()
    return conn


def _due(conn, now=NOW):
    return M.collect_due(conn, now)


def _one(uid=15, days=2, paid=1, admin=0, banned=0):
    """到期时间 = 现在 + days 天 - 5 小时，落在「向上取整正好等于 days」的区间里。

    减 5 小时是有意的：不减的话 2 天 1 小时会被取整成 3 天，用例自己就先错了。
    """
    exp = (NOW + timedelta(days=days) - timedelta(hours=5)).strftime('%Y-%m-%d %H:%M:%S')
    return _conn([(uid, 'buyer%d@example.com' % uid, 1, exp, admin, banned, 2709, paid)])


# ── 1. 天数与档位 ─────────────────────────────────────────────────────────
def test_days_left_rounds_up():
    """1 天 19 小时必须算 2 天：人对"还有 2 天"的理解是向上取整。"""
    exp = NOW + timedelta(days=1, hours=19)
    assert M.days_left(exp, NOW) == 2


def test_tier_boundaries():
    cases = {7: 1, 6: 1, 5: 1, 4: 1, 3: 2, 2: 2, 1: 3, 0: 3}
    for days, expect in cases.items():
        assert M.pick_tier(days) == expect, '剩 %d 天应发第 %d 封' % (days, expect)


def test_tier_none_outside_window():
    """剩 8 天以上还没到提醒窗口，不发。"""
    assert M.pick_tier(8) is None
    assert M.pick_tier(30) is None


def test_customer_with_two_days_gets_second_mail_only():
    """错过第一封不补发：只剩 2 天的客户，本轮只有第二封。"""
    conn = _one(days=2)
    due = _due(conn)
    assert len(due) == 1
    assert due[0][1] == 2


def test_expired_member_is_skipped():
    """已经过期的不再发提醒——提醒过期的人没有意义。"""
    exp = (NOW - timedelta(hours=3)).strftime('%Y-%m-%d %H:%M:%S')
    conn = _conn([(15, 'a@example.com', 1, exp, 0, 0, 100, 1)])
    assert _due(conn) == []


# ── 2. 只提醒付过费的会员 ─────────────────────────────────────────────────
def test_non_payer_gets_nothing():
    """内部账号、测试账号、试用账号都没有已支付订单，一个都不打扰。"""
    conn = _one(days=2, paid=0)
    assert _due(conn) == []


def test_admin_never_reminded():
    conn = _one(days=2, paid=1, admin=1)
    assert _due(conn) == []


def test_banned_user_skipped():
    conn = _one(days=2, paid=1, banned=1)
    assert _due(conn) == []


# ── 3. 防重发与续费重算 ───────────────────────────────────────────────────
def test_same_tier_sent_once():
    conn = _one(days=2)
    sent = []

    def fake(to, subject, html):
        sent.append(subject)
        return True

    M.send_due_reminders(now=NOW, sender=fake, conn=conn)
    assert len(sent) == 1
    # 同一天再跑一次，什么都不发
    M.send_due_reminders(now=NOW, sender=fake, conn=conn)
    assert len(sent) == 1


def test_renewal_starts_new_round():
    """续费后到期日变了，第二封要能重新发——不能被"发过"永久锁死。"""
    conn = _one(days=2)
    sent = []
    M.send_due_reminders(now=NOW, sender=lambda t, s, h: sent.append(s) or True, conn=conn)
    assert len(sent) == 1

    # 续费：到期日往后推 30 天
    new_exp = (NOW + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
    conn.execute('UPDATE users SET vip_expire_at=? WHERE id=15', (new_exp,))
    conn.commit()
    # 30 天后还剩 2 天时，应重新收到第二封
    later = NOW + timedelta(days=28)
    M.send_due_reminders(now=later, sender=lambda t, s, h: sent.append(s) or True, conn=conn)
    assert len(sent) == 2


def test_failed_send_is_retried_next_run():
    """发信失败不写记录，否则客户永远收不到那封邮件。"""
    conn = _one(days=2)
    M.send_due_reminders(now=NOW, sender=lambda t, s, h: False, conn=conn)
    assert conn.execute('SELECT COUNT(*) FROM membership_reminders').fetchone()[0] == 0
    sent = []
    M.send_due_reminders(now=NOW, sender=lambda t, s, h: sent.append(s) or True, conn=conn)
    assert len(sent) == 1


def test_dry_run_sends_nothing_and_records_nothing():
    conn = _one(days=2)
    out = M.send_due_reminders(now=NOW, dry_run=True,
                               sender=lambda t, s, h: (_ for _ in ()).throw(AssertionError('dry-run 不许发信')),
                               conn=conn)
    assert len(out) == 1 and out[0]['ok'] is None
    assert conn.execute('SELECT COUNT(*) FROM membership_reminders').fetchone()[0] == 0


# ── 4. 内容正确 ───────────────────────────────────────────────────────────
def test_mail_content_has_balance_and_recharge_link():
    conn = _one(days=2)
    due = _due(conn)
    rec, tier, days = due[0]
    subject, html = M.render(tier, {
        'expire_at': rec['expire_at'], 'now': NOW, 'days': days,
        'balance': rec['balance'], 'plan_name': rec['plan_name'],
        'url': 'https://example.com/dashboard/recharge'})
    assert '2 天' in subject
    assert '2,709' in html          # 余额带千位分隔，客户一眼能认
    assert '/dashboard/recharge' in html
    assert '煋鉴 Xinpect' in html


def test_last_mail_says_it_is_the_last_one():
    """最后一封必须明说不再发，否则客户以为是骚扰。"""
    conn = _one(days=1)
    rec, tier, days = _due(conn)[0]
    assert tier == 3
    _, html = M.render(tier, {
        'expire_at': rec['expire_at'], 'now': NOW, 'days': days,
        'balance': 100, 'plan_name': '月卡', 'url': 'https://example.com/x'})
    assert '最后一封' in html


def test_no_platform_specific_date_format():
    """%-m / %-d 是 glibc 扩展，换平台直接抛异常，渲染时必须能跑通。"""
    conn = _one(days=5)
    rec, tier, days = _due(conn)[0]
    subject, html = M.render(tier, {
        'expire_at': rec['expire_at'], 'now': NOW, 'days': days,
        'balance': 1, 'plan_name': '月卡', 'url': 'https://example.com/x'})
    assert str(rec['expire_at'].year) in html


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
