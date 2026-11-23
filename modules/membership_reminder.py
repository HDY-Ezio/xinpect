"""会员到期提醒：三档邮件，每轮到期每档只发一次。

设计约定（改之前先读）：
1. 只提醒**真正付过费**的会员。没有已支付订单的账号（内部、测试、试用）不打扰。
2. 档位由「剩余天数」决定，不靠人工排期：
       ≥4 天且 ≤7 天 → 第一封（提前一周）
       2~3 天        → 第二封
       ≤1 天         → 第三封（最后一封）
   天数用**向上取整**，因为人对"还有 2 天"的理解是 1 天 19 小时也算 2 天。
3. 防重发靠数据库记录 (user_id, tier, expire_at)，不靠记名单：
   续费后 expire_at 变了，下一轮三封会自动重新开始。
4. 第一封错过不补发。只剩 2 天才开通的会员，只收第二、三封。
"""
import argparse
import math
import sqlite3
import sys
from datetime import datetime

from .constants import DB_PATH, SITE_BASE_URL, logger
from .email_sender import _send_mail

# ── 三档定义 ───────────────────────────────────────────────────────────────
# (档位, 最小剩余天数, 最大剩余天数)，天数按向上取整
TIERS = (
    (1, 4, 7),
    (2, 2, 3),
    (3, 0, 1),
)

REMINDER_DDL = """
CREATE TABLE IF NOT EXISTS membership_reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    tier INTEGER NOT NULL,
    expire_at TEXT NOT NULL,
    sent_at TEXT DEFAULT (datetime('now', 'localtime')),
    email TEXT,
    UNIQUE (user_id, tier, expire_at)
);
"""

RECHARGE_PATH = '/dashboard/recharge'


def _ensure_table(conn):
    conn.executescript(REMINDER_DDL)


def _parse_dt(text):
    """解析 'YYYY-MM-DD HH:MM:SS'，失败返回 None。"""
    if not text:
        return None
    text = str(text).strip()
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def days_left(expire_at, now):
    """剩余天数，向上取整。已过期返回 0 或负数。"""
    delta = (expire_at - now).total_seconds()
    return int(math.ceil(delta / 86400.0))


def pick_tier(days):
    """按剩余天数选档；不在任何档内返回 None。"""
    for tier, lo, hi in TIERS:
        if lo <= days <= hi:
            return tier
    return None


def _when_phrase(expire_at, now):
    """返回 ('今天'|'明天'|'后天'|'N 天后', 'HH:MM')，供正文使用。"""
    date_delta = (expire_at.date() - now.date()).days
    if date_delta <= 0:
        word = '今天'
    elif date_delta == 1:
        word = '明天'
    elif date_delta == 2:
        word = '后天'
    else:
        word = '%d 天后' % date_delta
    return word, expire_at.strftime('%H:%M')


def _fmt_int(n):
    try:
        return '{:,}'.format(int(n))
    except (TypeError, ValueError):
        return '0'


# ── 邮件外壳 ───────────────────────────────────────────────────────────────
def _wrap(body_html):
    return (
        '<div style="background:#f2f4f7;padding:24px 12px;'
        'font-family:-apple-system,\'Segoe UI\',\'Microsoft YaHei\',Arial,sans-serif">'
        '<div style="max-width:560px;margin:0 auto;background:#ffffff;border:1px solid #e5e9f0;'
        'border-radius:8px;overflow:hidden">'
        '<div style="background:#1A2B4A;padding:24px 28px;text-align:center;'
        'border-bottom:2px solid #A07C36">'
        '<div style="color:#ffffff;font-size:20px;font-weight:600;letter-spacing:1.5px">煋鉴 Xinpect</div>'
        '<div style="color:#9FB0CC;font-size:12px;margin-top:5px;letter-spacing:.5px">AI 代码质量审计平台</div>'
        '</div>'
        '<div style="padding:28px 30px 22px">' + body_html + '</div>'
        '<div style="background:#F5F7FA;padding:14px 28px;text-align:center;'
        'border-top:1px solid #E5E9F0">'
        '<p style="margin:0;color:#8B98A8;font-size:11.5px;line-height:1.7">'
        '煋鉴 Xinpect · 长沙煋旺智能科技有限公司</p>'
        '<p style="margin:2px 0 0;color:#8B98A8;font-size:11.5px;line-height:1.7">'
        '此邮件由系统自动发送，直接回复即可联系我们</p>'
        '</div></div></div>'
    )


def _p(text, size='14.5px', color='#333333', weight='normal', margin='0 0 15px'):
    return ('<p style="font-size:%s;color:%s;line-height:1.75;margin:%s;font-weight:%s">%s</p>'
            % (size, color, margin, weight, text))


def _facts(rows):
    """rows: [(标签, 值)]，渲染成灰底信息块。"""
    inner = ''.join(
        '<tr>'
        '<td style="padding:3px 0;font-size:13.5px;color:#6B7280;width:82px;vertical-align:top">%s</td>'
        '<td style="padding:3px 0;font-size:13.5px;color:#1A2B4A;font-weight:600">%s</td>'
        '</tr>' % (label, value) for label, value in rows)
    return (
        '<div style="background:#F5F7FA;border-left:3px solid #A07C36;padding:14px 18px;'
        'margin:0 0 20px;border-radius:0 4px 4px 0">'
        '<table cellpadding="0" cellspacing="0" border="0" style="width:100%%;border-collapse:collapse">%s</table>'
        '</div>' % inner)


def _button(url, label):
    return (
        '<div style="text-align:center;padding:4px 0 22px">'
        '<a href="%s" style="display:inline-block;background:#1A2B4A;color:#ffffff;'
        'font-size:14.5px;font-weight:600;text-decoration:none;padding:12px 40px;'
        'border-radius:5px;letter-spacing:.5px">%s</a>'
        '<div style="font-size:12px;color:#8B98A8;margin-top:10px">%s</div>'
        '</div>' % (url, label, url))


def _ul(items):
    lis = ''.join('<li style="font-size:14px;color:#333333;line-height:1.85;margin-bottom:4px">%s</li>' % i
                  for i in items)
    return '<ul style="margin:0 0 18px;padding-left:20px">%s</ul>' % lis


def _alert(text):
    return ('<div style="background:#FFF7E6;border:1px solid #E8D9A8;border-radius:4px;'
            'padding:12px 16px;margin:0 0 20px;font-size:13.5px;color:#7A5200;line-height:1.7">%s</div>'
            % text)


def render(tier, ctx):
    """返回 (主题, HTML)。ctx 需含 expire_at/now/balance/plan_name/url。"""
    expire_at = ctx['expire_at']
    now = ctx['now']
    days = ctx['days']
    balance = _fmt_int(ctx['balance'])
    plan = ctx.get('plan_name') or '会员'
    url = ctx['url']
    when_word, hhmm = _when_phrase(expire_at, now)
    # 不用 %-m / %-d：那是 glibc 扩展，换平台会直接抛异常
    full_dt = '%d 年 %d 月 %d 日 %s' % (expire_at.year, expire_at.month,
                                       expire_at.day, expire_at.strftime('%H:%M'))

    facts = _facts([
        ('当前套餐', plan),
        ('积分余额', balance + ' 积分'),
        ('到期时间', expire_at.strftime('%Y-%m-%d %H:%M') + ('（%d 天后）' % days if days > 1 else '')),
    ])

    if tier == 1:
        subject = '你的煋鉴会员还有 %d 天到期' % days
        body = (
            _p('你的会员将在 %d 天后到期' % days, size='16px', color='#1A2B4A',
               weight='600', margin='0 0 18px')
            + _p('您好，你的%s会员于 <b>%s</b> 到期，目前还剩 %d 天。' % (plan, full_dt, days))
            + _p('到期后，以下功能会暂停：')
            + _ul([
                '<b>API 密钥调用</b>——用密钥接口扫描会提示「仅对会员开放」',
                '<b>深度分析、报告下载、批量检测</b>——需要会员身份',
            ])
            + facts
            + _p('余额里的 %s 积分<b>不会清零</b>，但会员到期后暂时无法使用，续费即恢复。'
                 % balance, size='13px', color='#6B7280', margin='0 0 18px')
            + _button(url, '续费会员')
            + _p('续费不是必须的。如果这段时间没有要查的代码，等有项目再回来也一样，积分我们一直给你留着。',
                 size='13px', color='#6B7280', margin='0')
        )
    elif tier == 2:
        subject = '会员还有 %d 天到期，你的 %s 积分会被暂时锁住' % (days, balance)
        body = (
            _p('会员还有 %d 天到期' % days, size='16px', color='#1A2B4A',
               weight='600', margin='0 0 18px')
            + _p('您好，你的%s会员于 <b>%s</b> 到期，还剩 %d 天。' % (plan, full_dt, days))
            + _p('提醒一下到期后会停掉的部分，免得你到时候临时卡住：')
            + _ul([
                'API 密钥调用会返回「仅对会员开放」，如果你的流程里有自动扫描，会直接报错',
                '账户里的 <b>%s 积分</b>会暂时锁住，余额不清零，但到期期间用不了' % balance,
                '深度分析、报告下载、批量检测同步暂停',
            ])
            + facts
            + _button(url, '续费会员')
            + _p('手上这个项目扫完了、暂时没别的活，那就不用管这封邮件。下次有项目再回来，积分还在。',
                 size='13px', color='#6B7280', margin='0')
        )
    else:
        subject = '你的煋鉴会员%s %s 到期' % (when_word, hhmm)
        body = (
            _alert('<b>%s %s 到期</b>　——　这是最后一封提醒，之后不会再发。' % (when_word, hhmm))
            + _p('会员%s到期' % when_word, size='16px', color='#1A2B4A',
                 weight='600', margin='0 0 18px')
            + _p('您好，你的%s会员将在 <b>%s %s</b> 到期。如果还有没扫完的项目，赶在到期前处理完最省事。'
                 % (plan, when_word, hhmm))
            + facts
            + _p('到期那一刻起，API 密钥调用会停，积分暂时锁住。想继续用，点下面按钮续费就行，两分钟的事。')
            + _button(url, '现在续费')
            + _p('手头没项目就先放着。需要的时候随时回来，账号和数据都在。',
                 size='13px', color='#6B7280', margin='0')
        )

    return subject, _wrap(body)


# ── 取人 ───────────────────────────────────────────────────────────────────
_CANDIDATE_SQL = """
SELECT u.id, u.email, u.vip_expire_at, u.is_admin,
       COALESCE(uc.balance, 0) AS balance,
       (SELECT COUNT(*) FROM orders o
         WHERE o.user_id = u.id AND o.status = 'paid') AS paid_orders,
       (SELECT o.plan_name FROM orders o
         WHERE o.user_id = u.id AND o.status = 'paid'
         ORDER BY COALESCE(o.paid_at, o.created_at) DESC LIMIT 1) AS plan_name
  FROM users u
  LEFT JOIN user_credits uc ON uc.user_id = u.id
 WHERE u.is_vip = 1
   AND u.vip_expire_at IS NOT NULL
   AND TRIM(u.vip_expire_at) <> ''
   AND COALESCE(u.is_banned, 0) = 0
 ORDER BY u.vip_expire_at
"""


def collect_due(conn, now):
    """返回 [(row, tier, days)]，只含该发且没发过的。"""
    _ensure_table(conn)
    out = []
    for row in conn.execute(_CANDIDATE_SQL):
        rec = dict(row)
        if rec['is_admin']:
            continue
        # 只提醒真正付过费的会员：内部账号与测试账号没有付费订单，天然被排除
        if not rec['paid_orders']:
            continue
        expire_at = _parse_dt(rec['vip_expire_at'])
        if not expire_at:
            continue
        if expire_at <= now:
            continue
        days = days_left(expire_at, now)
        tier = pick_tier(days)
        if tier is None:
            continue
        already = conn.execute(
            'SELECT 1 FROM membership_reminders WHERE user_id=? AND tier=? AND expire_at=?',
            (rec['id'], tier, rec['vip_expire_at'])).fetchone()
        if already:
            continue
        rec['expire_at'] = expire_at
        out.append((rec, tier, days))
    return out


def send_due_reminders(now=None, dry_run=False, sender=None, conn=None):
    """发送本轮该发的提醒。返回 [{user_id,email,tier,days,subject,ok,skipped}]。"""
    now = now or datetime.now()
    sender = sender or _send_mail
    own_conn = conn is None
    if own_conn:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
    results = []
    try:
        due = collect_due(conn, now)
        for rec, tier, days in due:
            subject, html = render(tier, {
                'expire_at': rec['expire_at'],
                'now': now,
                'days': days,
                'balance': rec['balance'],
                'plan_name': rec['plan_name'],
                'url': SITE_BASE_URL.rstrip('/') + RECHARGE_PATH,
            })
            item = {'user_id': rec['id'], 'email': rec['email'],
                    'tier': tier, 'days': days, 'subject': subject}
            if dry_run:
                item['ok'] = None
                item['skipped'] = 'dry-run'
            else:
                ok = bool(sender(rec['email'], subject, html))
                item['ok'] = ok
                item['skipped'] = '' if ok else 'send-failed'
                if ok:
                    conn.execute(
                        'INSERT OR IGNORE INTO membership_reminders (user_id, tier, expire_at, email)'
                        ' VALUES (?,?,?,?)',
                        (rec['id'], tier, rec['vip_expire_at'], rec['email']))
                    conn.commit()
            results.append(item)
    finally:
        if own_conn:
            conn.close()
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description='会员到期提醒（三档）')
    ap.add_argument('--dry-run', action='store_true', help='只打印要发给谁，不发信、不记账')
    ap.add_argument('--now', help='指定当前时间，格式 "YYYY-MM-DD HH:MM"，便于演练')
    args = ap.parse_args(argv)

    now = datetime.now()
    if args.now:
        now = _parse_dt(args.now)
        if not now:
            print('时间格式不对，应为 "YYYY-MM-DD HH:MM"', file=sys.stderr)
            return 2

    results = send_due_reminders(now=now, dry_run=args.dry_run)
    if not results:
        print('本轮没有需要发送的提醒（%s）' % now.strftime('%Y-%m-%d %H:%M'))
        return 0
    for r in results:
        state = '待发' if args.dry_run else ('已发' if r['ok'] else '失败')
        print('%s  %-4s 第%d封  剩%d天  %s  %s'
              % (state, 'user%d' % r['user_id'], r['tier'], r['days'], r['email'], r['subject']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
