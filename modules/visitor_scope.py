"""真人访客口径的唯一定义。

**这个模块不许 import 任何东西**，也不许有任何副作用。
理由：`scripts/visitor_report.py` 要在不起 Flask 的前提下读这些常量
（`modules/__init__` 会把整个 app 拉起来，报表只要一个字符串）。
所以它按文件路径直接加载本文件，跟读 `modules/limits.py` 是同一个手法。

## 为什么需要「自检流量」这一档

2026-11-18 实测：报表说每天 1000~2000 个独立访客，但同一时段真人扫描为 0。
查 UA 发现主力是这些：

    xinpect-uptime-sv/1.0      1140 次/天   在线监控
    xp-consistency-guard/1.0    348 次/天   一致性守卫
    xp-growth-guard/1.0          84 次/天   增长守卫
    xinpect-audit/1.0            72 次/天   审计脚本

全是我们自己的工具。它们没命中 `_BOT_RE`（因为这些 UA 里没有 bot/spider
这类词——名字是我们自己起的，起得还挺像客户端），于是被算进了「真人访客」。

**这不是爬虫问题，是「我们把自己数成了客户」。**
后果比没有数据更糟：它让人得出「有人来过但没转化」的错误结论，
而真相是「根本没人来过」。

## 为什么还需要「一次一换 cookie 的机器」这一档

2026-11-24 实测：11-23 报表 56 个独立访客，其中 43 个来自 `66.249.64.1/.8/.9/.14/.15`
（Google 爬虫段），11-21 报表 97 个里有 58 个来自 `93.123.109.103`。
它们的共同特征不是 UA（UA 伪装成正常 Chrome/Android），而是：
**同一个 IP 一天来 N 次，每次 vid 都不一样**。

判据就写在这条线上：**真浏览器一定带 cookie，因此同一个 vid 会重复出现；
不带 cookie 的机器每个请求都领一张新 vid，于是独立访客数等于请求数。**

这条规则是**通用**的，不认具体 UA、不认 IP 归属、不需要维护任何名单：
将来任何新爬虫、任何代理池、任何拨测，只要它不存 cookie，就自动命中。

## 判据为什么用 UA 前缀，而不加具体 UA 白名单

我们的工具都出自同一个命名空间：`xinpect-*` 和 `xp-*`。真人浏览器绝不会
发这种 UA（UA 的语法规定以产品名开头，`xinpect-` 不是任何真实产品）。
所以「以这两个前缀开头 = 我们自己的工具」是一条**通用规则**，
将来新写的监控脚本自动适用，不需要回来改表。

反过来，如果写成 EXACT_UA = {'xinpect-uptime-sv/1.0', ...}，就变成白名单：
每加一个脚本就要改一次代码，漏一个就再脏一次——那才是治标。
"""

# 我们自己的工具 UA 前缀。判定只看开头，不看全串。
INTERNAL_UA_PREFIXES = ('xinpect-', 'xp-')

# 真人访客的判据。**任何统计都必须引用这一句**，不许自己写 `is_bot = 0`
# ——同一判据散在十几个 SQL 里，改一处漏一处，账面就会有两个数。
VISITOR_FILTER = 'is_bot = 0 AND is_internal = 0'

# 老库还没补 is_internal 列时的降级口径（只可能出现在迁移未生效的窗口里）。
VISITOR_FILTER_LEGACY = 'is_bot = 0'

# ---- 一次一换 cookie 的机器 ----
# 命中条件（同一窗口内、同一 IP）：vid 数 >= 5，且「只出现过一次的 vid」占比 >= 0.9。
#
# 为什么是 5：真人清 cookie 一天清 5 次几乎不可能；而爬虫一天随便就 5 次。
# 为什么是 0.9 而不是 1.0：留一点余量，机器偶尔也可能复用一次 cookie
# （比如它被分配了固定会话），没必要因此整段漏掉。
#
# **已知误杀边界**（写在这里，不许假装没有）：公司/学校共用出口 IP、
# 同型号同系统版本的 5 个真人当天各只来一次，vid 数 5、单次占比 1.0，会被判成机器。
# 站点日活 5~40，撞上这个形状的概率极低；真撞上了，报表会明确写出
# 「已剔除 X 个 id」，看得见、可以追问，不会被悄悄抹掉。
SUSPECT_MIN_VIDS = 5
SUSPECT_SINGLE_HIT_RATIO = 0.9


def is_internal_ua(ua):
    """UA 是否来自我们自己的工具。空 UA 不算（那是另一种情况，交给 is_bot）。"""
    if not ua:
        return False
    return ua.strip().lower().startswith(INTERNAL_UA_PREFIXES)


def suspect_ips_sql(days, extra_filter=''):
    """返回一段 SQL 子查询：窗口内「一次一换 cookie」的 IP。

    用法（同一判据只有这一处出处，别在自己那里重写）：
        sub = suspect_ips_sql(7, VISITOR_FILTER)
        ... WHERE ... AND ip NOT IN ({sub})      # 剔除
        ... WHERE ... AND ip IN ({sub})          # 只为统计剔除了多少

    `days` 只允许整数（这里自己转 int，不接受外部拼串）；
    `extra_filter` 传 `VISITOR_FILTER`，避免把我们自己的监控 IP 也算成机器。
    """
    d = int(days)
    extra = f' AND {extra_filter}' if extra_filter else ''
    return (
        'SELECT ip FROM ('
        '  SELECT ip, vid, count(*) AS hits FROM visitor_events'
        f"  WHERE created_at >= datetime('now','localtime','-{d} day'){extra}"
        '  GROUP BY ip, vid'
        ') '
        'GROUP BY ip '
        f'HAVING count(*) >= {SUSPECT_MIN_VIDS} '
        '   AND 1.0 * sum(CASE WHEN hits = 1 THEN 1 ELSE 0 END) / count(*) '
        f'       >= {SUSPECT_SINGLE_HIT_RATIO}'
    )
