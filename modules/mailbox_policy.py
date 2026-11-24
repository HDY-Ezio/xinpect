# -*- coding: utf-8 -*-
"""收件地址性质判定：B2B 外联能不能发到这个地址。

为什么要有这个（2026-11-24）：
  外联名单是「从公司官网抄下来的联系邮箱」。抄的人不分辨「公司邮箱」和
  「老板的私人 QQ」——一批冷邮件发到 89530205@qq.com 这类地址上，收件人
  看到的是「有人拿私人信箱给我发广告」，观感即骚扰，退信率也高。

  这个判断原本只存在人脑里（上次是人工数的 6 个）。人脑里的判据不会被
  用到下一批名单上，所以挪进代码：发送端自己挑，不依赖名单抄得对不对。

判据只有一条：域名属于消费级邮箱服务商 → 不是公司地址。
  反过来「公司域名」不保证一定是公司，但至少背后有个组织在用这个地址收信。
  这里不追求精确分类，只拦「一眼就知道是私人信箱」的那一类。
"""

CONSUMER_MAILBOX_DOMAINS = frozenset((
    # 国内免费邮箱
    'qq.com', 'foxmail.com', 'vip.qq.com',
    '163.com', '126.com', 'yeah.net', '188.com', 'vip.163.com', 'vip.126.com',
    'sina.com', 'sina.cn', 'sohu.com', '139.com', '189.cn', '21cn.com',
    'tom.com', '263.net', 'aliyun.com', 'wo.cn', 'china.com',
    # 境外免费邮箱
    'gmail.com', 'googlemail.com', 'hotmail.com', 'outlook.com', 'live.com',
    'msn.com', 'yahoo.com', 'ymail.com', 'icloud.com', 'me.com', 'mac.com',
    'aol.com', 'protonmail.com', 'gmx.com', 'mail.com', 'zoho.com',
))


def domain_of(email):
    """取域名（小写、去空白）。取不到返回空串。"""
    e = (email or '').strip().lower()
    if not e or any(c.isspace() for c in e):
        return ''
    if e.count('@') != 1:
        return ''
    local, dom = e.split('@')
    if not local:
        return ''
    dom = dom.strip().rstrip('.')
    if not dom or '.' not in dom or ' ' in dom:
        return ''
    return dom


def is_consumer_mailbox(email):
    """True = 私人/免费邮箱，不适合做 B2B 冷邮件的收件地址。"""
    return domain_of(email) in CONSUMER_MAILBOX_DOMAINS


def split_targets(items, key='email'):
    """按地址性质切开名单。返回 (可发, 跳过[(条目, 原因)])。

    取不到域名的（拼错、缺 @、带空格）也算跳过 —— 发给一个格式都不对的
    地址，除了给自己刷退信率没有任何作用。
    """
    ok, skipped = [], []
    for it in items:
        addr = it.get(key, '') if isinstance(it, dict) else str(it)
        dom = domain_of(addr)
        if not dom:
            skipped.append((it, '地址格式不对'))
        elif dom in CONSUMER_MAILBOX_DOMAINS:
            skipped.append((it, '私人邮箱（%s）' % dom))
        else:
            ok.append(it)
    return ok, skipped
