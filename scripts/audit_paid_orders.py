"""付费履约对账：钱收了，货到底给了没。

起因（2026-11-14 上午）：技能按次付费通道存在至今只成交 1.49 元，而且履约代码
是坏的（`engine.b10_sca` 缺模块）——钱收了、活没干，躺了几个月没人发现。
原因是所有巡检都在问「进程活不活、接口通不通」，没有一条在问「这笔钱对应
的东西给了没」。这个脚本补的就是那一问。

同日下午补的第二个缺口（2026-11-14 11:00）：
第一版只做「网站 → 权益」单向核对，等于假设「网站知道所有钱」。
实际查门房库发现 3 笔已收款订单网站根本没有记录（¥23），单向对账永远看不见——
因为它的起点就是网站自己。所以现在两个方向都查：
  正向：网站标记已付 → 权益（积分 / 会员时长）必须落地
  反向：门房标记已付 → 网站必须有这笔、且状态也是已付

差异的处置办法是「登记」，不是「忽略」：确认为历史遗留、无需履约的差异，
用 --dispose 写进 payment_audit_dispositions（谁核的、什么理由、哪天核的），
下次对账降级为「已知」但仍打印。理由文案变了会重新报红——防止拿台账当挡箭牌。

不做白名单、不做代码里的例外：新出现的订单类型如果没人补对账规则，它会自己报出来。
"""
import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 支付回调可能还在处理中，太新的订单不急着判「没履约」。
GRACE_MINUTES = 10

CREDIT_ORDER_TYPES = ('credit_pack', 'topup')
SUBSCRIPTION_TYPES = ('subscription',)

# 门房（收银台）的库：真正的收款事实来源，网站只是记账的一方。
MENFANG_DB_DEFAULT = '/opt/xinpect-pay/menfang.db'

DISPOSITION_DDL = '''
CREATE TABLE IF NOT EXISTS payment_audit_dispositions (
    order_id    TEXT PRIMARY KEY,
    side        TEXT NOT NULL,
    reason      TEXT NOT NULL,
    decided_by  TEXT NOT NULL,
    decided_at  TEXT NOT NULL
)
'''


def _dt(text):
    try:
        return datetime.strptime((text or '').strip(), '%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        return None


def _has_credit_grant(db, order_id):
    row = db.execute(
        "SELECT 1 FROM credit_transactions"
        " WHERE ref_id = ? AND amount > 0 LIMIT 1", (order_id,)
    ).fetchone()
    return bool(row)


def _vip_covers(db, user_id, paid_at):
    """会员到期日是否覆盖到这笔支付的时刻（含之后）。"""
    row = db.execute(
        "SELECT vip_expire_at FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if not row:
        return False
    expire = (row['vip_expire_at'] or '').strip()
    if not expire:
        return False
    paid_dt = _dt(paid_at)
    expire_dt = _dt(expire)
    if paid_dt is None or expire_dt is None:
        return False
    return expire_dt > paid_dt


def _load_dispositions(db):
    """已登记的差异处置结论：order_id -> reason。取不到就当成空台账。"""
    try:
        db.execute(DISPOSITION_DDL)
        db.commit()
        return {r['order_id']: r['reason']
                for r in db.execute('SELECT order_id, reason FROM payment_audit_dispositions')}
    except sqlite3.Error:
        return {}


def _open_menfang(menfang_db):
    """打开门房库。传连接就直接用；传路径/None 走只读打开。"""
    if isinstance(menfang_db, sqlite3.Connection):
        return menfang_db, None
    path = menfang_db or MENFANG_DB_DEFAULT
    if not os.path.exists(path):
        return None, '门房库不存在：%s' % path
    try:
        conn = sqlite3.connect('file:%s?mode=ro' % path, uri=True)
        conn.row_factory = sqlite3.Row
        conn.execute('SELECT 1 FROM orders LIMIT 1').fetchone()
        return conn, None
    except sqlite3.Error as exc:
        return None, '门房库读不了：%s' % exc


def audit_site(db, now=None):
    """正向：网站自己标记已付的订单，权益必须落地。"""
    now = now or datetime.now()
    issues = []
    checked = 0

    rows = db.execute(
        "SELECT order_id, user_id, plan_id, order_type, amount, paid_at"
        " FROM orders WHERE status = 'paid' ORDER BY id"
    ).fetchall()

    for r in rows:
        oid = r['order_id']
        otype = (r['order_type'] or '').strip()
        paid_at = (r['paid_at'] or '').strip()

        paid_dt = _dt(paid_at)
        if paid_dt is None:
            issues.append({'order_id': oid, 'user_id': r['user_id'], 'side': 'site',
                           'order_type': otype,
                           'reason': '已支付但没有可解析的支付时间：%r' % paid_at})
            continue
        if (now - paid_dt).total_seconds() < GRACE_MINUTES * 60:
            continue  # 太新，回调可能还在处理

        if otype in CREDIT_ORDER_TYPES:
            if not _has_credit_grant(db, oid):
                issues.append({'order_id': oid, 'user_id': r['user_id'], 'side': 'site',
                               'order_type': otype,
                               'reason': '积分没有入账（找不到该订单的入账流水）'})
                continue
        elif otype in SUBSCRIPTION_TYPES:
            if not _has_credit_grant(db, oid):
                issues.append({'order_id': oid, 'user_id': r['user_id'], 'side': 'site',
                               'order_type': otype,
                               'reason': '订阅赠送积分没有发放'})
                continue
            if not _vip_covers(db, r['user_id'], paid_at):
                issues.append({'order_id': oid, 'user_id': r['user_id'], 'side': 'site',
                               'order_type': otype,
                               'reason': '会员到期日没有覆盖这笔支付的时刻（等于没开通）'})
                continue
        else:
            issues.append({'order_id': oid, 'user_id': r['user_id'], 'side': 'site',
                           'order_type': otype or '(空)',
                           'reason': '订单类型没有对账规则，无法确认是否履约'})
            continue

        checked += 1

    return issues, checked


def audit_menfang(site_db, mf_conn):
    """反向：门房收了钱的订单，网站必须认账。

    这是单向对账的盲区补丁：如果网站根本没收到这笔（回调丢了、服务重启跨过
    了通知），正向对账从网站出发就永远看不到它。钱是门房收的，只能从门房查。
    """
    issues = []
    checked = 0

    for r in mf_conn.execute(
        "SELECT order_id, email, plan, amount, status FROM orders"
        " WHERE status = 'paid' ORDER BY rowid"
    ):
        oid = (r['order_id'] or '').strip()
        if not oid:
            continue
        site = site_db.execute(
            'SELECT status FROM orders WHERE order_id = ?', (oid,)).fetchone()
        if site is None:
            issues.append({'order_id': oid, 'user_id': r['email'], 'side': 'menfang',
                           'order_type': (r['plan'] or '(空)').strip(),
                           'reason': '门房已收款 ¥%s，网站没有这笔订单（权益不会发放）' % r['amount']})
            continue
        site_status = (site['status'] or '').strip()
        if site_status != 'paid':
            issues.append({'order_id': oid, 'user_id': r['email'], 'side': 'menfang',
                           'order_type': (r['plan'] or '(空)').strip(),
                           'reason': '门房已收款 ¥%s，网站订单状态仍是 %s（回调没落地）'
                                     % (r['amount'], site_status or '(空)')})
            continue
        checked += 1

    return issues, checked


def audit(db, now=None, menfang_db=None):
    """返回 (异常列表, 核对通过的订单数)。

    异常每项是 dict：order_id / user_id / order_type / reason / side / known。
    known=True 表示这条已在处置台账里登记过（历史遗留、无需履约），
    脚本仍会打印，但不算失败。
    """
    issues, checked = audit_site(db, now=now)

    mf_conn, mf_err = _open_menfang(menfang_db)
    if mf_conn is not None:
        mf_issues, mf_checked = audit_menfang(db, mf_conn)
        issues.extend(mf_issues)
        checked += mf_checked
        if not isinstance(menfang_db, sqlite3.Connection):
            mf_conn.close()
    else:
        # 反向对账做不了就必须说，不能当通过。
        issues.append({'order_id': '(门房)', 'user_id': '-', 'side': 'menfang',
                       'order_type': '-', 'reason': mf_err or '门房库打不开，反向对账没做'})

    known = _load_dispositions(db)
    for i in issues:
        i['known'] = bool(known.get(i['order_id'])) and known[i['order_id']] == i['reason']
    return issues, checked


def dispose(db, order_id, side, reason, decided_by):
    """把一条差异登记为「已核实、无需履约」，留痕可查。"""
    db.execute(DISPOSITION_DDL)
    db.execute(
        'INSERT OR REPLACE INTO payment_audit_dispositions'
        ' (order_id, side, reason, decided_by, decided_at) VALUES (?,?,?,?,?)',
        (order_id, side, reason, decided_by,
         datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    db.commit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', default=None, help='网站数据库路径（默认取站点 DB_PATH）')
    ap.add_argument('--menfang-db', default=None,
                    help='门房数据库路径（默认 %s）' % MENFANG_DB_DEFAULT)
    ap.add_argument('--json', default='', help='把结果同时写成 JSON')
    ap.add_argument('--dispose', default='', help='登记一条差异的处置结论（订单号）')
    ap.add_argument('--reason', default='', help='配合 --dispose：为什么不用履约')
    ap.add_argument('--by', default='manual', help='配合 --dispose：谁核实的')
    a = ap.parse_args()

    if a.db:
        db_path = a.db
    else:
        from modules.constants import DB_PATH  # 延迟导入，便于测试单独跑
        db_path = DB_PATH

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if a.dispose:
            dispose(conn, a.dispose, 'menfang', a.reason or '(未写理由)', a.by)
            print('已登记处置：%s — %s' % (a.dispose, a.reason or '(未写理由)'))
            return 0

        issues, checked = audit(conn, menfang_db=a.menfang_db)
    finally:
        conn.close()

    fresh = [i for i in issues if not i.get('known')]
    known = [i for i in issues if i.get('known')]

    if a.json:
        with open(a.json, 'w', encoding='utf-8') as fh:
            json.dump({'checked': checked, 'issues': issues,
                       'unknown_count': len(fresh), 'known_count': len(known),
                       'at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')},
                      fh, ensure_ascii=False, indent=2)

    for i in known:
        print('  · 已知 %s [%s] %s — %s'
              % (i['order_id'][:12], i['side'], i['order_type'], i['reason']))

    if fresh:
        print('❌ 付费履约对账：%d 笔订单有 %d 笔对不上（另有 %d 笔已知历史差异）'
              % (checked + len(fresh), len(fresh), len(known)))
        for i in fresh:
            print('  · %s [%s] 用户%s %s — %s'
                  % (i['order_id'][:12], i['side'], i['user_id'], i['order_type'], i['reason']))
        return 1

    print('✅ 付费履约对账通过：%d 笔已付款全部对上（双向）%s'
          % (checked, '，另有 %d 笔已登记的历史差异' % len(known) if known else ''))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
