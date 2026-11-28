#!/usr/bin/env python3
"""隔离实例不许变成孤儿：父进程被 kill -9，子进程必须自己走。

为什么要有这一层（2026-11-29）
------------------------------
这个文件守的不是页面，是「测试自己留下的残骸」。三个前端实点守卫都 Popen
起隔离实例、`finally` 里 terminate，可 SSH 断线根本不走 `finally`：11-29
02:04 起来的那个 e2e_serve 一直活到 04:11，两小时零七分。

它没让体检变红 —— 孤儿不碰生产库、不占生产端口，九项全绿。这正是「绿着红掉」
的另一面：绿着漏掉。静态检查永远看不见这种漏，只有真杀一次父进程才现形。

断言分两半，少一半都白测：
  1. 父进程活着时，子进程不许被误杀（监护自己不能变成故障源）。
  2. 父进程 kill -9 之后，子进程必须在 12 秒内消失。

造坏自检
--------
把真 proc_guard 换成一个「什么都不做」的桩，同一套场景必须变红（子进程活
下来，变成孤儿）。桩写在临时目录、靠 sys.path 优先级盖住真文件 —— 不去改
源码，源码被改过一次就恢复不回去了。

用法
----
    python3 tests/test_e2e_proc_leak.py
    python3 tests/test_e2e_proc_leak.py --self-test

退出码：0 通过 / 1 失败。
"""
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid

SITE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(SITE, 'tests')
GUARD = os.path.join(TESTS, 'proc_guard.py')
SERVE = os.path.join(TESTS, 'e2e_serve.py')

# 用来在 /proc/<pid>/cmdline 里认出「还是我们那个进程」，pid 会被复用。
PROBE = 'XP_PROCGUARD_PROBE_' + uuid.uuid4().hex

# 被测对象：先起监护线程，再说自己就绪，然后长睡。
CHILD = (
    'import sys, time\n'
    'sys.path.insert(0, sys.argv[1])\n'
    'from proc_guard import watch_parent\n'
    'watch_parent(interval=0.2)\n'
    'sys.stdout.write("CHILD_READY\\n")\n'
    'sys.stdout.flush()\n'
    'time.sleep(45)\n'
)

# 中间层：起子进程、把 pid 报上来、然后长睡。测试杀的就是它。
MID = (
    'import subprocess, sys, time\n'
    'p = subprocess.Popen(sys.argv[1:])\n'
    'sys.stdout.write("MID_CHILD_PID=%d\\n" % p.pid)\n'
    'sys.stdout.flush()\n'
    'time.sleep(45)\n'
)

# 造坏自检的桩：签名一致、行为是空的。它活着，子进程就该变孤儿。
NOOP_STUB = (
    'def watch_parent(interval=2.0, exit_code=0):\n'
    '    """造坏自检专用空桩：故意不监护。"""\n'
    '    return None\n'
)


def _log(msg):
    sys.stdout.write(msg + '\n')
    sys.stdout.flush()


def _alive(pid):
    """活着，且还是我们那个探针（连命令行一起看，避免 pid 复用造成假活）。"""
    try:
        with open('/proc/%d/cmdline' % pid, 'rb') as fh:
            return PROBE.encode() in fh.read()
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return False


def _spawn(guard_dir):
    """起中间层 + 子进程，返回 (中间层进程, 子进程 pid)。"""
    env = os.environ.copy()
    env['PYTHONUNBUFFERED'] = '1'
    env.pop('PYTHONPATH', None)
    mid = subprocess.Popen(
        [sys.executable, '-c', MID, sys.executable, '-c', CHILD, guard_dir, PROBE],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)

    lines = queue.Queue()

    def _pump():
        for ln in mid.stdout:
            lines.put(ln.strip())

    threading.Thread(target=_pump, daemon=True).start()

    child_pid = None
    ready = False
    seen = []
    deadline = time.time() + 20
    while time.time() < deadline and not (child_pid and ready):
        try:
            ln = lines.get(timeout=0.5)
        except queue.Empty:
            if mid.poll() is not None:
                break
            continue
        seen.append(ln)
        if ln.startswith('MID_CHILD_PID='):
            child_pid = int(ln.split('=', 1)[1])
        elif ln == 'CHILD_READY':
            ready = True
    if not (child_pid and ready):
        try:
            mid.kill()
        except Exception:
            pass
        raise RuntimeError('探针没起来：pid=%s ready=%s 输出=%r' % (child_pid, ready, seen[-5:]))
    return mid, child_pid


def _scenario(guard_dir):
    """跑一遍场景，返回 (父进程活着时子进程还在吗, kill 父进程后子进程还在吗)。"""
    mid, child_pid = _spawn(guard_dir)
    try:
        time.sleep(2.5)
        alive_while_parent = _alive(child_pid)
        mid.kill()
        mid.wait(timeout=10)
        deadline = time.time() + 12
        while time.time() < deadline and _alive(child_pid):
            time.sleep(0.2)
        return alive_while_parent, _alive(child_pid)
    finally:
        try:
            if _alive(child_pid):
                os.kill(child_pid, 9)
        except Exception:
            pass
        try:
            mid.kill()
            mid.wait(timeout=5)
        except Exception:
            pass


def _predicate_ok():
    """判据本身先钉一遍：换了 ppid 是孤儿，没换不是。"""
    from proc_guard import parent_gone  # noqa: E402  （放在函数里：路径要先备好）
    if not parent_gone(1234, 1):
        return '父进程换成 init 后仍判「还在」'
    if parent_gone(1234, 1234):
        return '父进程没换却判成孤儿'
    return None


def _wiring_ok():
    """e2e_serve 必须真的把监护挂上去。

    这一条只到文本层：它能证明「有人写了这一行」，不能证明「这一行真跑到了」。
    真正跑到由上面那两条行为断言兜着 —— 这段只防「接线被误删后测试还绿」。
    注释不算：把调用写进注释是最省事的一种假绿。
    """
    if not os.path.isfile(SERVE):
        return '找不到 %s' % SERVE
    text = open(SERVE, encoding='utf-8').read()
    if 'from proc_guard import watch_parent' not in text:
        return 'e2e_serve.py 没有 import watch_parent'
    for ln in text.split('\n'):
        s = ln.strip()
        if s.startswith('#'):
            continue
        if re.match(r'^watch_parent\s*\(', s):
            return None
    return 'e2e_serve.py 里没有真正调用 watch_parent()（只在注释里不算）'


def main(argv):
    selftest = '--self-test' in argv
    if not os.path.isfile(GUARD):
        _log('❌ 找不到监护模块：%s' % GUARD)
        return 1
    sys.path.insert(0, TESTS)

    bad = _predicate_ok()
    if bad:
        _log('❌ 判据坏了：%s' % bad)
        return 1
    bad = _wiring_ok()
    if bad:
        _log('❌ 接线断了：%s' % bad)
        return 1

    tmp = tempfile.mkdtemp(prefix='xp-procguard-')
    try:
        if selftest:
            with open(os.path.join(tmp, 'proc_guard.py'), 'w', encoding='utf-8') as fh:
                fh.write(NOOP_STUB)
            alive_live, alive_after = _scenario(tmp)
            if not alive_live:
                _log('❌ 造坏自检跑不动：桩还没生效子进程就没了，场景本身不成立')
                return 1
            if not alive_after:
                _log('❌ 造坏自检失败：去掉监护后子进程照样死了 —— 那条用例的绿不是监护给的')
                return 1
            _log('✅ 造坏自检通过：去掉监护后子进程果然活成孤儿，真用例会判红')
            return 0

        alive_live, alive_after = _scenario(TESTS)
        if not alive_live:
            _log('❌ 父进程还活着，子进程却已退出 —— 监护误杀，这本身就是故障')
            return 1
        if alive_after:
            _log('❌ 父进程被 kill -9 后子进程仍活着：隔离实例会变成孤儿')
            return 1
        _log('✅ 孤儿守卫通过：父进程在时子进程在，父进程死后子进程 12 秒内退出')
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
