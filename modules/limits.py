"""全站配额常量 —— 「一个数字决定全站行为」的东西放这里。

为什么单独一个模块，而不是塞进 constants.py：
    constants.py 会建 Flask app、挂日志 handler，是给 Web 进程用的。
    报表脚本（scripts/visitor_report.py）只需要读一个数字，
    不该为此把整个 app 拉起来——那既慢又容易在 cron 环境下踩到配置缺失。

为什么必须只有一处：
    这个上限同时决定「限流会不会拦人」和「报表上显示的分母」。
    分两处写，早晚会出现「报表说还剩 50 次、实际已经被 429」这种对不上的事。
"""

import os

# 免费试扫的全站日上限（成本天花板）。
# 单个访客每天 3 次在 free_try 里，这个是全站总量——
# 有人换身份刷的时候，靠这个保住算力不被吃光。
TRY_GLOBAL_DAILY_LIMIT = int(os.environ.get('TRY_GLOBAL_DAILY_LIMIT', '300'))
