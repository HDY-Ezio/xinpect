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


if __name__ == '__main__':
    port = int(os.environ['XP_E2E_PORT'])
    site_app.init_db()
    print('E2E_READY db=%s port=%s' % (site_app.DB_PATH, port), flush=True)
    site_app.app.run(host='127.0.0.1', port=port, threaded=True, use_reloader=False)
