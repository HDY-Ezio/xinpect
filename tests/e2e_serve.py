#!/usr/bin/env python3
"""给前端端到端测试用的最小启动入口。

与生产 `app.py` 的唯一区别：不启动队列调度器、Redis worker、支付补单线程。
那三样是后台任务，会跟生产实例抢同一个队列、同一个门房接口；测试只需要
「页面 + /api/try-scan」这条链路能跑。

蓝图注册、模板、静态资源全部走生产代码，不复制也不覆写 ——
测试入口一旦和生产入口分家，绿的就是另一个东西了。
"""
import os
import sys

SITE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SITE)
os.chdir(SITE)

import app as site_app  # noqa: E402  （蓝图在 import 时注册，main 块不会执行）


def _init_like_production():
    """跟生产启动同一套建表，一个都不能少。

    生产 app.py 的启动顺序是 init_db + scan/webhook/feedback/leads/team/
    governance 六套建表。这里原本只调 init_db，结果隔离实例缺 team_members、
    invoice_requests 等表，开票页直接 500 —— 那不是被测代码的问题，是测试
    环境本身残缺。
    """
    site_app.init_db()
    from modules.scan_worker import init_scan_tables
    init_scan_tables()
    from modules.webhook_manager import init_webhook_tables
    init_webhook_tables()
    from modules.feedback import init_feedback_tables
    init_feedback_tables()
    from modules.leads import init_leads_tables
    init_leads_tables()
    from modules.team import init_team_tables
    init_team_tables()
    from modules.team_governance import init_governance_tables
    init_governance_tables()


if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from proc_guard import watch_parent

    # 父进程（测试）被 kill -9 / SIGHUP 带走时，finally 不会执行。
    # 这里让进程自己发现「头上换人了」，否则隔离实例会抱着随机端口长跑。
    watch_parent()
    port = int(os.environ['XP_E2E_PORT'])
    _init_like_production()
    print('E2E_READY db=%s port=%s' % (site_app.DB_PATH, port), flush=True)
    site_app.app.run(host='127.0.0.1', port=port, threaded=True, use_reloader=False)
