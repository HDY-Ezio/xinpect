"""付费履约对账的守卫。

钉住这些事：
1. 收了钱没给积分 / 没开会员，对账必须报出来（技能通道那次就是这么漏的）
2. 已经履约的订单不能误报（否则告警会被无视）
3. 认不出的订单类型必须报「无法核对」，不许静默跳过
4. 刚支付完的订单有 10 分钟宽限期，别把回调处理中的单子当事故
5. 反向也要查：门房收了钱、网站没这笔，必须报（11-14 实测有 3 笔 ¥23 是这么漏的）
6. 差异登记成「已知」后不判红，但理由文案变了要重新判红（台账不能当挡箭牌）
"""
import importlib.util
import os
import sqlite3
import sys
from datetime import datetime, timedelta

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)


def _load_audit_module():
    """scripts 不是 Python 包（没有 __init__.py），按路径加载，顺带不改项目结构。"""
    path = os.path.join(_ROOT, 'scripts', 'audit_paid_orders.py')
    spec = importlib.util.spec_from_file_location('audit_paid_orders', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_M = _load_audit_module()
audit = _M.audit
dispose = _M.dispose

NOW = datetime(2026, 11, 14, 12, 0, 0)
OLD = '2026-11-14 09:00:00'       # 3 小时前，过宽限期
FRESH = '2026-11-14 11:58:00'     # 2 分钟前，宽限期内


def _mf(rows=()):
    """门房库：rows 是 (order_id, email, plan, amount, status)。"""
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript('''
        CREATE TABLE orders (
            order_id TEXT, email TEXT, plan TEXT, amount REAL, status TEXT,
            wechat_order_id TEXT, paid_at TEXT, created_at TEXT);
    ''')
    for oid, email, plan, amount, status in rows:
        conn.execute('INSERT INTO orders (order_id,email,plan,amount,status)'
                     ' VALUES (?,?,?,?,?)', (oid, email, plan, amount, status))
    conn.commit()
    return conn


def _db(orders, grants=(), users=()):
    """orders: (order_id, user_id, order_type, amount, paid_at)
    grants:  (user_id, amount, ref_id)
    users:   (id, vip_expire_at)"""
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript('''
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT, user_id INTEGER,
            plan_id TEXT, order_type TEXT, amount REAL, status TEXT, paid_at TEXT);
        CREATE TABLE credit_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER,
            ref_id TEXT, ref_type TEXT);
        CREATE TABLE users (id INTEGER PRIMARY KEY, vip_expire_at TEXT);
    ''')
    for oid, uid, otype, amount, paid in orders:
        conn.execute('INSERT INTO orders (order_id,user_id,order_type,amount,status,paid_at)'
                     ' VALUES (?,?,?,?,?,?)', (oid, uid, otype, amount, 'paid', paid))
    for uid, amount, ref in grants:
        conn.execute('INSERT INTO credit_transactions (user_id,amount,ref_id,ref_type)'
                     ' VALUES (?,?,?,?)', (uid, amount, ref, 'test'))
    for uid, expire in users:
        conn.execute('INSERT INTO users (id,vip_expire_at) VALUES (?,?)', (uid, expire))
    conn.commit()
    return conn


def _audit(conn, now=NOW, mf=None):
    """默认配一个空门房库，免得单条用例被真实门房数据干扰。"""
    return audit(conn, now=now, menfang_db=mf if mf is not None else _mf())


# ---------------------------------------------------------------- 正向：网站 → 权益

def test_credit_pack_without_grant_is_reported():
    """钱收了，积分没入账 → 必须报出来。"""
    conn = _db([('A1', 9, 'credit_pack', 1299.0, OLD)])
    issues, checked = _audit(conn)
    assert checked == 0
    assert len(issues) == 1 and '积分没有入账' in issues[0]['reason'], issues


def test_credit_pack_with_grant_passes():
    conn = _db([('A2', 9, 'credit_pack', 1299.0, OLD)], grants=[(9, 5000, 'A2')])
    issues, checked = _audit(conn)
    assert issues == [] and checked == 1, (issues, checked)


def test_subscription_without_vip_is_reported():
    """赠积分发了，但会员到期日没覆盖支付时刻 → 等于没开通，必须报。"""
    conn = _db([('B1', 8, 'subscription', 99.0, OLD)],
               grants=[(8, 300, 'B1')], users=[(8, '2026-01-01 00:00:00')])
    issues, _ = _audit(conn)
    assert len(issues) == 1 and '会员到期日' in issues[0]['reason'], issues


def test_subscription_fully_served_passes():
    conn = _db([('B2', 8, 'subscription', 99.0, OLD)],
               grants=[(8, 300, 'B2')], users=[(8, '2027-01-01 00:00:00')])
    issues, checked = _audit(conn)
    assert issues == [] and checked == 1, (issues, checked)


def test_subscription_without_grant_is_reported():
    conn = _db([('B3', 8, 'subscription', 99.0, OLD)],
               users=[(8, '2027-01-01 00:00:00')])
    issues, _ = _audit(conn)
    assert len(issues) == 1 and '赠送积分' in issues[0]['reason'], issues


def test_unknown_order_type_is_reported():
    """认不出的类型不许静默通过——那正是「没人补规则」时的漏点。"""
    conn = _db([('C1', 7, 'skill_scan_once', 0.5, OLD)],
               grants=[(7, 1, 'C1')])
    issues, checked = _audit(conn)
    assert checked == 0
    assert len(issues) == 1 and '无法确认' in issues[0]['reason'], issues


def test_fresh_order_is_not_alarmed():
    """刚付完 2 分钟的单子不该报——回调可能还在路上。"""
    conn = _db([('D1', 6, 'credit_pack', 99.0, FRESH)])
    issues, checked = _audit(conn)
    assert issues == [] and checked == 0, (issues, checked)


def test_grace_actually_expires():
    """同一笔单子，过了宽限期就必须报。

    这是宽限期那条判据的自检：如果宽限期被写死成「永不报」，上一条会绿、
    这一条会红，两种情况都跑不掉。
    """
    conn = _db([('D2', 6, 'credit_pack', 99.0, FRESH)])
    issues, _ = _audit(conn, now=NOW + timedelta(minutes=30))
    assert len(issues) == 1, issues


def test_missing_paid_at_is_reported():
    """paid_at 为空/乱码：不能当成正常单子放过去。"""
    conn = _db([('E1', 5, 'subscription', 99.0, '不是时间')],
               grants=[(5, 300, 'E1')], users=[(5, '2027-01-01 00:00:00')])
    issues, _ = _audit(conn)
    assert len(issues) == 1 and '支付时间' in issues[0]['reason'], issues


# ---------------------------------------------------------------- 反向：门房 → 网站

def test_menfang_paid_missing_on_site_is_reported():
    """门房收了钱，网站根本没这笔 → 权益永远不会发，必须报。

    11-14 实测：门房 3 笔已收款（¥23）网站没有记录，第一版单向对账全看不见。
    """
    site = _db([])
    mf = _mf([('M1', 'someone@163.com', 'monthly', 99.0, 'paid')])
    issues, checked = _audit(site, mf=mf)
    assert len(issues) == 1, issues
    assert issues[0]['side'] == 'menfang'
    assert '网站没有这笔订单' in issues[0]['reason'], issues
    assert checked == 0


def test_menfang_paid_but_site_pending_is_reported():
    """门房收了钱，网站状态还挂在 pending（回调没落地）→ 必须报。"""
    site = _db([])
    site.execute("INSERT INTO orders (order_id,user_id,order_type,amount,status,paid_at)"
                 " VALUES ('M2',9,'subscription',99.0,'pending',NULL)")
    site.commit()
    mf = _mf([('M2', 'someone@163.com', 'monthly', 99.0, 'paid')])
    issues, _ = _audit(site, mf=mf)
    assert len(issues) == 1 and '回调没落地' in issues[0]['reason'], issues


def test_menfang_paid_and_site_paid_passes():
    site = _db([('M3', 9, 'credit_pack', 1299.0, OLD)], grants=[(9, 5000, 'M3')])
    mf = _mf([('M3', 'someone@163.com', 'credit-5000', 1299.0, 'paid')])
    issues, checked = _audit(site, mf=mf)
    assert issues == [] and checked == 2, (issues, checked)


def test_menfang_unpaid_orders_are_ignored():
    """门房里没付的单子（expired / pending）不参与对账，别乱报。"""
    site = _db([])
    mf = _mf([('M4', 'a@163.com', 'monthly', 99.0, 'expired'),
              ('M5', 'a@163.com', 'monthly', 99.0, 'pending')])
    issues, checked = _audit(site, mf=mf)
    assert issues == [] and checked == 0, (issues, checked)


def test_menfang_unreadable_is_reported():
    """门房库打不开：反向对账做不了就得说，不能静默当通过。"""
    site = _db([])
    issues, _ = audit(site, now=NOW, menfang_db='/tmp/definitely_not_here_%d.db' % os.getpid())
    assert len(issues) == 1 and '门房' in issues[0]['reason'], issues


# ---------------------------------------------------------------- 差异登记台账

def test_disposed_difference_is_not_red_but_still_listed():
    """登记过的历史差异：不判失败，但仍要列出来（不许假装没有）。"""
    site = _db([])
    mf = _mf([('M6', 'boss@163.com', 'trial', 10.0, 'paid')])
    issues, _ = _audit(site, mf=mf)
    assert len(issues) == 1 and not issues[0]['known']
    dispose(site, 'M6', 'menfang', issues[0]['reason'], 'test')
    issues2, _ = _audit(site, mf=mf)
    assert len(issues2) == 1 and issues2[0]['known'], issues2


def test_disposition_does_not_mask_a_changed_problem():
    """台账理由对不上当前判定 → 重新判红。防止拿台账当挡箭牌把新问题一起盖住。"""
    site = _db([])
    mf = _mf([('M7', 'boss@163.com', 'trial', 10.0, 'paid')])
    dispose(site, 'M7', 'menfang', '当初写的是另一回事', 'test')
    issues, _ = _audit(site, mf=mf)
    assert len(issues) == 1 and not issues[0]['known'], issues


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
