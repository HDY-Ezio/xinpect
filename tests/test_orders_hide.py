#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""订单记录删除的守卫。

钉住六件事（每一条都对应一个真会发生的事故）：
1. 只有 expired 能删 —— paid 是开票与流水凭证，pending 还能去付款
2. 只能删自己的单 —— user_id 必须在 WHERE 里，不是靠前端不出按钮
3. 重复点不报错、不重复计数 —— 双击、网络重试都会撞上
4. 批量清理只清 expired，不顺手带走 paid
5. 删掉的订单在页面上真的不出现，且没删的还在
6. 页面上「删除」按钮只挂在 expired 那一行 —— 挂错行等于给了删 paid 的入口

背景（2026-11-29）：老板账号有 16 笔下单未付款的 expired 订单，把「我的订单」
刷满了屏，留着没意义。做删除功能时守的不是「按钮能不能点」，而是
「有没有可能把已支付订单删掉」。
"""
import os
import sqlite3
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

_TMP = tempfile.mkdtemp(prefix='xp-orders-')
os.environ['XINPECT_SECRET'] = 'x' * 64
os.environ['XINPECT_DB_PATH'] = os.path.join(_TMP, 'test.db')
os.environ['XINPECT_DATA_DIR'] = _TMP

import app as site_app  # noqa: E402
from tests.e2e_serve import _init_like_production  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402

_inited = False


def _ensure_db():
    global _inited
    if not _inited:
        _init_like_production()
        _inited = True


PW = 'Probe#2026xp'
A_EMAIL = 'order-a@test.local'
B_EMAIL = 'order-b@test.local'


def _uid(email):
    conn = sqlite3.connect(site_app.DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
    conn.close()
    return row['id'] if row else None


def _mk_user(email):
    _ensure_db()
    conn = sqlite3.connect(site_app.DB_PATH)
    conn.execute(
        "INSERT OR IGNORE INTO users (email, password_hash, onboarding_completed)"
        " VALUES (?, ?, 1)", (email, generate_password_hash(PW)))
    conn.commit()
    uid = conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()[0]
    conn.close()
    return uid


def _mk_order(uid, oid, status, amount=99.0, plan='月卡'):
    conn = sqlite3.connect(site_app.DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO orders"
        " (order_id, user_id, plan_id, plan_name, order_type, amount, status, created_at)"
        " VALUES (?, ?, 'monthly', ?, 'subscription', ?, ?, datetime('now','localtime'))",
        (oid, uid, plan, amount, status))
    conn.commit()
    conn.close()


def _hidden_at(oid):
    conn = sqlite3.connect(site_app.DB_PATH)
    row = conn.execute('SELECT hidden_at FROM orders WHERE order_id = ?', (oid,)).fetchone()
    conn.close()
    return row[0] if row else 'MISSING'


def _client(email):
    _mk_user(email)
    c = site_app.app.test_client()
    resp = c.post('/login', data={'email': email, 'password': PW})
    assert resp.status_code in (302, 303), '登录失败 %s' % resp.status_code
    return c


def _post(c, url):
    return c.post(url, headers={'X-Requested-With': 'XMLHttpRequest'})


def _cleanup(*oids):
    conn = sqlite3.connect(site_app.DB_PATH)
    for oid in oids:
        conn.execute('DELETE FROM orders WHERE order_id = ?', (oid,))
    conn.commit()
    conn.close()


# ------------------------------------------------------------------ 1 & 2
def test_only_expired_order_can_be_deleted():
    """paid 和 pending 都删不掉，expired 能删。"""
    a = _mk_user(A_EMAIL)
    _mk_order(a, 'ORD-PAID-1', 'paid')
    _mk_order(a, 'ORD-PEND-1', 'pending')
    _mk_order(a, 'ORD-EXP-1', 'expired')
    c = _client(A_EMAIL)

    r = _post(c, '/api/orders/ORD-PAID-1/hide')
    assert r.status_code == 409, '已支付订单居然能删：%s %s' % (r.status_code, r.get_json())
    assert _hidden_at('ORD-PAID-1') is None

    r = _post(c, '/api/orders/ORD-PEND-1/hide')
    assert r.status_code == 409, '待支付订单居然能删：%s' % r.status_code
    assert _hidden_at('ORD-PEND-1') is None

    r = _post(c, '/api/orders/ORD-EXP-1/hide')
    assert r.status_code == 200 and r.get_json()['hidden'] == 1
    assert _hidden_at('ORD-EXP-1'), '接口说成功，库里却没有 hidden_at'
    _cleanup('ORD-PAID-1', 'ORD-PEND-1', 'ORD-EXP-1')


# ------------------------------------------------------------------ 3
def test_cannot_delete_other_users_order():
    """越权：删别人的单必须 404，且对方那行纹丝不动。"""
    a = _mk_user(A_EMAIL)
    b = _mk_user(B_EMAIL)
    _mk_order(b, 'ORD-B-EXP', 'expired')
    c = _client(A_EMAIL)

    r = _post(c, '/api/orders/ORD-B-EXP/hide')
    assert r.status_code == 404, '越权删除返回了 %s' % r.status_code
    assert _hidden_at('ORD-B-EXP') is None, '别人的订单被删掉了'
    _cleanup('ORD-B-EXP')


# ------------------------------------------------------------------ 4
def test_repeat_delete_is_idempotent():
    """重复点不报错，也不重复计数。"""
    a = _mk_user(A_EMAIL)
    _mk_order(a, 'ORD-EXP-2', 'expired')
    c = _client(A_EMAIL)

    r1 = _post(c, '/api/orders/ORD-EXP-2/hide')
    r2 = _post(c, '/api/orders/ORD-EXP-2/hide')
    assert r1.status_code == 200 and r1.get_json()['hidden'] == 1
    assert r2.status_code == 200, '重复删除报错了：%s %s' % (r2.status_code, r2.get_json())
    assert r2.get_json()['hidden'] == 0, '重复删除又算了一笔'
    _cleanup('ORD-EXP-2')


# ------------------------------------------------------------------ 5
def test_batch_clean_only_takes_expired():
    """批量清理只清 expired，paid 一根汗毛都不动。"""
    a = _mk_user(A_EMAIL)
    for i in range(3):
        _mk_order(a, 'ORD-BATCH-E%d' % i, 'expired')
    _mk_order(a, 'ORD-BATCH-P', 'paid')
    c = _client(A_EMAIL)

    r = _post(c, '/api/orders/hide-expired')
    assert r.status_code == 200
    assert r.get_json()['hidden'] == 3, '批量清了 %s 笔，应为 3' % r.get_json()['hidden']
    assert _hidden_at('ORD-BATCH-P') is None, '批量清理把已支付订单带走了'
    for i in range(3):
        assert _hidden_at('ORD-BATCH-E%d' % i), '第 %d 笔过期订单没被清理' % i
    _cleanup('ORD-BATCH-E0', 'ORD-BATCH-E1', 'ORD-BATCH-E2', 'ORD-BATCH-P')


# ------------------------------------------------------------------ 6
def test_unhide_restores_everything():
    """恢复后所有被删的订单都回来。"""
    a = _mk_user(A_EMAIL)
    _mk_order(a, 'ORD-RESTORE-1', 'expired')
    c = _client(A_EMAIL)
    _post(c, '/api/orders/ORD-RESTORE-1/hide')
    assert _hidden_at('ORD-RESTORE-1')

    r = _post(c, '/api/orders/unhide-all')
    assert r.status_code == 200
    assert _hidden_at('ORD-RESTORE-1') is None, '恢复接口返回成功，hidden_at 还在'
    _cleanup('ORD-RESTORE-1')


# ------------------------------------------------------------------ 7
def test_deleted_order_disappears_from_page():
    """页面上真的不显示被删的订单，没删的还在。"""
    a = _mk_user(A_EMAIL)
    _mk_order(a, 'ORD-PAGE-GONE', 'expired')
    _mk_order(a, 'ORD-PAGE-KEPT', 'expired')
    c = _client(A_EMAIL)
    _post(c, '/api/orders/ORD-PAGE-GONE/hide')

    html = c.get('/dashboard/orders').get_data(as_text=True)
    assert 'ORD-PAGE-GONE' not in html, '删掉的订单还在页面上'
    assert 'ORD-PAGE-KEPT' in html, '没删的订单反而不见了'
    _cleanup('ORD-PAGE-GONE', 'ORD-PAGE-KEPT')


# ------------------------------------------------------------------ 8
def test_delete_button_only_on_expired_row():
    """「删除」按钮只能出现在过期订单那一行。

    这条守的是模板里那个 if 分支。挂错一行，等于给用户一个删已支付订单的入口
    —— 后端会拦，但用户点了会收到 409，是明摆着的坏体验。
    """
    a = _mk_user(A_EMAIL)
    _mk_order(a, 'ORD-ROW-EXP', 'expired')
    _mk_order(a, 'ORD-ROW-PAID', 'paid')
    c = _client(A_EMAIL)

    html = c.get('/dashboard/orders').get_data(as_text=True)
    for oid, must_have in (('ORD-ROW-EXP', True), ('ORD-ROW-PAID', False)):
        idx = html.find(oid)
        assert idx > 0, '订单 %s 没渲染出来' % oid
        row_end = html.find('</tr>', idx)
        row = html[idx:row_end]
        has_btn = 'orders-del' in row
        assert has_btn == must_have, (
            '%s 那一行 orders-del=%s，应为 %s —— 删除按钮挂错行了'
            % (oid, has_btn, must_have))
    _cleanup('ORD-ROW-EXP', 'ORD-ROW-PAID')


# ------------------------------------------------------------------ 9
def test_orders_page_requires_login():
    """没登录不许碰，也不许看。"""
    c = site_app.app.test_client()
    r = c.post('/api/orders/hide-expired', headers={'X-Requested-With': 'XMLHttpRequest'})
    assert r.status_code in (302, 401), '未登录也能批量删单：%s' % r.status_code
    assert '/login' in (r.headers.get('Location') or '') or r.status_code == 401


if __name__ == '__main__':
    sys.exit(__import__('pytest').main([__file__, '-v']))
