"""付款后补单的守卫。

钉住四件事：
1. 同一笔订单被处理两次（前端轮询 + 后台补单撞车），积分只发一次、会员只加一次
2. 「门房说已付、网站还挂着 pending」的单子，后台循环必须补开
3. 补单循环不许在 import 时启动（否则任何 import app 都替生产起线程）
4. app.py 里补单循环只在 __main__ 启动

背景（2026-11-14）：开通权益是前端轮询 /api/pay/status 触发的。客户扫完码关掉
页面，轮询就断了——钱在门房收了，会员没开、积分没发，而且没人会发现，因为
履约对账只查 status='paid'，pending 的根本不在视野里。
"""
import os
import sqlite3
import sys
from datetime import timedelta

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

os.environ.setdefault('XINPECT_SECRET', 'x' * 64)

from modules import payment  # noqa: E402

UID = 15


def _mkdb():
    """订单表 + 用户表，够 handler 跑。"""
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript('''
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT, user_id INTEGER,
            plan_id TEXT, plan_name TEXT, order_type TEXT, amount REAL,
            status TEXT, paid_at TEXT, created_at TEXT);
        CREATE TABLE users (
            id INTEGER PRIMARY KEY, is_vip INTEGER, vip_expire_at TEXT);
    ''')
    conn.execute("INSERT INTO users (id, is_vip, vip_expire_at)"
                 " VALUES (?, 1, '2026-12-01 00:00:00')", (UID,))
    conn.commit()
    return conn


def _add_order(conn, oid, otype='subscription', plan='monthly', status='pending',
               created=None, paid_at=None):
    # 2026-11-17 治本：原来把 created 写死成 '2026-11-14 09:00:00'，而补单循环
    # 只回看 48 小时（RECONCILE_LOOKBACK_HOURS）。日期一过，订单落在窗口外，
    # reconcile 查不到，测试就恒报 (0, 0)——测试自己随时间腐烂，比没测试更糟。
    if created is None:
        created = (payment.datetime.now() - timedelta(minutes=10)).strftime('%Y-%m-%d %H:%M:%S')
    conn.execute(
        "INSERT INTO orders (order_id,user_id,plan_id,plan_name,order_type,amount,"
        " status,paid_at,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (oid, UID, plan, plan, otype, 99.0, status, paid_at, created))
    conn.commit()


def _patch(attr, value):
    """临时替换 payment 模块里的符号，返回还原函数。"""
    old = getattr(payment, attr)
    setattr(payment, attr, value)
    return lambda: setattr(payment, attr, old)


def test_repeat_subscription_paid_grants_once():
    """轮询和补单撞车：第二次调用必须什么都不做。"""
    db = _mkdb()
    _add_order(db, 'S1', 'subscription', 'monthly')

    grants = []
    undo = [
        _patch('grant_credits', lambda *a, **k: grants.append(a)),
        _patch('process_referral_reward', lambda *a, **k: None),
        _patch('get_db', lambda: db),
    ]
    try:
        order = db.execute("SELECT * FROM orders WHERE order_id='S1'").fetchone()
        user = dict(db.execute('SELECT * FROM users WHERE id=?', (UID,)).fetchone())
        with payment.app.test_request_context('/'):
            payment._handle_subscription_paid(db, order, 'S1', user, '2026-11-14T03:00:00Z')
            payment._handle_subscription_paid(db, order, 'S1', user, '2026-11-14T03:00:00Z')
    finally:
        for u in reversed(undo):
            u()

    assert len(grants) == 1, '积分发了 %d 次，必须是 1 次' % len(grants)
    days = payment.SUBSCRIPTION_CREDITS.get('monthly', {}).get(
        'days', payment.DEFAULT_SUBSCRIPTION_DAYS)
    # 原到期 2026-12-01，未到期 → 从原到期日往后加，只加一次
    expect = payment.calc_vip_expire(
        payment.datetime(2026, 11, 14, 11), '2026-12-01 00:00:00', days)
    got = db.execute('SELECT vip_expire_at FROM users WHERE id=?', (UID,)).fetchone()[0]
    assert got == expect, '到期日 %s，应为 %s（重复调用把天数加了两遍？）' % (got, expect)


def test_repeat_credit_pack_grants_once():
    db = _mkdb()
    _add_order(db, 'P1', 'credit_pack', 'credit-5000')
    grants = []
    undo = [_patch('grant_credits', lambda *a, **k: grants.append(a))]
    try:
        order = db.execute("SELECT * FROM orders WHERE order_id='P1'").fetchone()
        user = dict(db.execute('SELECT * FROM users WHERE id=?', (UID,)).fetchone())
        with payment.app.test_request_context('/'):
            payment._handle_credit_pack_paid(db, order, 'P1', user)
            payment._handle_credit_pack_paid(db, order, 'P1', user)
    finally:
        for u in reversed(undo):
            u()
    assert len(grants) == 1, '积分包发了 %d 次，必须是 1 次' % len(grants)


def test_reconcile_opens_what_menfang_already_collected():
    """门房已收款、网站还 pending → 补开。这正是「客户关掉页面」的场景。"""
    db = _mkdb()
    _add_order(db, 'R1', 'subscription', 'monthly', status='pending')
    grants = []
    undo = [
        _patch('get_db', lambda: db),
        _patch('grant_credits', lambda *a, **k: grants.append(a)),
        _patch('process_referral_reward', lambda *a, **k: None),
        _patch('_menfang_get_order_status',
               lambda oid: {'found': True, 'status': 'paid', 'paid_at': '2026-11-14T03:00:00Z'}),
    ]
    try:
        with payment.app.test_request_context('/'):
            fixed, checked = payment.reconcile_pending_orders()
    finally:
        for u in reversed(undo):
            u()

    assert checked == 1 and fixed == 1, (fixed, checked)
    assert db.execute("SELECT status FROM orders WHERE order_id='R1'").fetchone()[0] == 'paid'
    assert len(grants) == 1


def test_reconcile_leaves_unpaid_alone():
    """门房说没付 → 不许动。"""
    db = _mkdb()
    _add_order(db, 'R2', 'subscription', 'monthly', status='pending')
    undo = [
        _patch('get_db', lambda: db),
        _patch('_menfang_get_order_status',
               lambda oid: {'found': True, 'status': 'pending', 'paid_at': None}),
    ]
    try:
        with payment.app.test_request_context('/'):
            fixed, checked = payment.reconcile_pending_orders()
    finally:
        for u in reversed(undo):
            u()
    assert checked == 1 and fixed == 0, (fixed, checked)
    assert db.execute("SELECT status FROM orders WHERE order_id='R2'").fetchone()[0] == 'pending'


def test_reconcile_skips_too_fresh_orders():
    """刚下单 30 秒的别抢——前端轮询可能正在处理，避免两边同时开。"""
    db = _mkdb()
    _add_order(db, 'R3', 'subscription', 'monthly', status='pending',
               created=payment.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    undo = [_patch('get_db', lambda: db)]
    try:
        with payment.app.test_request_context('/'):
            fixed, checked = payment.reconcile_pending_orders()
    finally:
        for u in reversed(undo):
            u()
    assert checked == 0 and fixed == 0, (fixed, checked)


def test_reconciler_does_not_start_on_import():
    """import 不许有副作用：模块加载完，补单循环必须是没启动的状态。"""
    assert payment._reconciler_started is False, '导入 payment 就把补单线程起了'


def test_reconciler_starts_only_from_entrypoint():
    """必须由 app.py 的 __main__ 启动，代码里要有这一句。"""
    src = open(os.path.join(_ROOT, 'app.py'), encoding='utf-8').read()
    main_block = src[src.index('if __name__ == "__main__":'):]
    assert 'start_payment_reconciler' in main_block, 'app.py 的 __main__ 里没有启动补单循环'
    # 以及：模块被导入时不许调（检查调用点确实在 main 块里，不在文件上半部分）
    assert src.count('start_payment_reconciler(') == 1, 'start_payment_reconciler 被调用了多次'



def test_reconcile_opens_paid_team_order():
    """团队版付款后回调丢了：必须补开，不能记一行 warning 就放过（2026-11-27）。

    背景：补开规则只有 subscription / credit_pack / topup，team 落进 else
    被静默跳过。客户花 1499 元买团队版、回调没到，钱在门房收了，团队永远
    开不起来，日志里只有一行 warning，没人会看见。

    造坏自检：把 payment.py 里的 team 分支删掉，这条必须变红。
    """
    db = _mkdb()
    _add_order(db, 'T1', 'team', 'team_basic', status='pending')
    called = []

    from modules import team_governance as tg
    old_finalize = tg._finalize_team_purchase
    tg._finalize_team_purchase = lambda oid, uid=None: (
        called.append((oid, uid)) or (True, 7, ''))

    undo = [
        _patch('get_db', lambda: db),
        _patch('_menfang_get_order_status',
               lambda oid: {'found': True, 'status': 'paid',
                            'paid_at': '2026-11-27T03:00:00Z'}),
    ]
    try:
        with payment.app.test_request_context('/'):
            fixed, checked = payment.reconcile_pending_orders()
    finally:
        tg._finalize_team_purchase = old_finalize
        for u in reversed(undo):
            u()

    assert called == [('T1', UID)], '团队版订单没被补开，called=%r' % (called,)
    assert fixed == 1 and checked == 1, '补开 %s 笔 / 检查 %s 笔，应为 1/1' % (fixed, checked)

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
