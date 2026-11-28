#!/usr/bin/env python3
"""子进程跟着父进程一起退出：父进程没了，子进程自己走。

为什么要有这个（2026-11-29）
--------------------------
三个前端实点守卫（试扫页 / 开票页 / 订单页）都是 Popen 起一个隔离实例，
`finally` 里 terminate。这套写法在「测试正常报错」时是对的，在「测试进程被
打断」时一行都不执行 —— SIGKILL / SIGHUP 直接把进程带走，`finally` 没有
机会跑。SSH 断线走的就是这条路（本轮 255 的断连有十几条，全是这个形态）。

于是隔离实例变成孤儿，抱着一个随机端口继续跑：11-29 02:04 起的那一个，
到 04:11 还在，两小时零七分。它不碰生产库、不占生产端口，所以体检九项全绿
—— 绿得毫无破绽，漏掉的正是「测试自己留下的残骸」。

补法不是再写一个「清理脚本」（下次还得靠人记得跑），是让子进程自己知道
父进程已经不在了：Linux 上父进程一死，子进程立刻被挂到 init 或 subreaper
名下，`os.getppid()` 当场就变。判据就是「我头上的 ppid 还是不是当初那个」。

用法
----
    from proc_guard import watch_parent
    watch_parent()               # 默认 2 秒看一眼
    watch_parent(interval=0.2)   # 用例里用短间隔

被判定为孤儿时用 `os._exit(exit_code)` 走，不是 `sys.exit`：后者只结束当前
线程，主线程还抱着 dev server 不撒手。
"""
import os
import sys
import threading
import time

DEFAULT_INTERVAL = 2.0


def parent_gone(start_ppid, current_ppid):
    """父进程换了人就是没了。

    抽成纯函数，只为让测试能直接断言这条判据本身 —— 判下游现象（进程死没死）
    会把「为什么死」也糊掉。
    """
    return current_ppid != start_ppid


def watch_parent(interval=DEFAULT_INTERVAL, exit_code=0):
    """起一个守护线程盯着父进程，父进程没了就结束整个进程。

    必须在 fork 出来之后尽快调用：这里记下的 ppid 就是基准值。
    """
    start_ppid = os.getppid()

    def _loop():
        while True:
            time.sleep(interval)
            if parent_gone(start_ppid, os.getppid()):
                sys.stderr.write('proc_guard: 父进程 %d 已退出，子进程跟着退出\n' % start_ppid)
                sys.stderr.flush()
                os._exit(exit_code)

    th = threading.Thread(target=_loop, name='proc-guard', daemon=True)
    th.start()
    return th
