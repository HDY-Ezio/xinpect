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


def is_internal_ua(ua):
    """UA 是否来自我们自己的工具。空 UA 不算（那是另一种情况，交给 is_bot）。"""
    if not ua:
        return False
    return ua.strip().lower().startswith(INTERNAL_UA_PREFIXES)
