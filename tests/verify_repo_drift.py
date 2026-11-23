#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""仓库漂移守卫：线上跑的东西必须都在版本库里。

为什么要有这个：

2026-11-23 盘点时仓库落后线上整一个月——16 个功能模块、39 份自动检查、
19 个运维脚本从未提交。app.py 一 import visitor_scope 就失败，也就是说
这台机器真出事，站点从仓库恢复不出来。而这么严重的事，一年里没有任何东西
会因为它是红的而报警。守卫就是那个东西。

判据只问「记没记账」，不问「改得对不对」（对不对是人的事）：

  1. 未跟踪、也没被 .gitignore 排除的代码类文件，必须为 0。
     它们要么该入库，要么该进忽略名单，不许悬着。
  2. 已跟踪文件的未提交改动（M/D/A/R/C/T/U）超过 30 条就判红。
     说明攒太久了。

阈值为什么是 30 而不是 0：

开发过程中工作区必然有未提交改动，阈值取 0 会让每轮体检都红；红太多次就没人
看了，守卫等于不存在。30 是「明显攒过头」的线：一次功能改动通常 5~15 个文件，
连续做三四件事不提交才会到这里。反过来说，30 条以下不红，不代表可以永远不提交。

自检造坏三处（缺一个都不算数）：
  a. 临时仓库里丢一个未跟踪 .py → 必须判红
  b. 把它 add 进去 → 必须转绿（证明判的是「没入库」，不是「有文件」）
  c. 造 31 个已跟踪改动 → 必须判红（证明阈值那条真的会响）
  d. 被 .gitignore 排除的 .py 不该被判红（证明忽略名单真起了作用）
"""
import os
import subprocess
import sys
import tempfile
import shutil

ROOT = os.environ.get('XP_SITE', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CODE_EXT = ('.py', '.sh', '.js', '.mjs', '.html', '.css', '.json', '.md', '.xml',
            '.sql', '.service', '.yml', '.yaml', '.toml', '.ini', '.cfg')
DIRTY_LIMIT = 30


def _git(root, *args):
    cmd = ['git', '-c', 'safe.directory=%s' % root] + list(args)
    return subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=120)


def inspect(root):
    """返回 (未入库的代码文件, 未提交改动条数, 未提交改动清单)。"""
    r = _git(root, 'status', '--porcelain', '-uall')
    if r.returncode != 0:
        raise SystemExit('git status 失败：%s' % (r.stderr or '').strip())
    untracked_code = []
    dirty = []
    for line in r.stdout.splitlines():
        if len(line) < 4:
            continue
        code, path = line[:2], line[3:]
        if code == '??':
            if path.lower().endswith(CODE_EXT):
                untracked_code.append(path)
        elif code.strip() and code.strip()[0] in 'MDARCTU':
            dirty.append(path)
    return untracked_code, len(dirty), dirty


def check(root=None, verbose=True):
    root = root or ROOT
    untracked_code, dirty_count, dirty_list = inspect(root)
    ok = True

    if untracked_code:
        ok = False
        if verbose:
            print('❌ 未入库的代码文件 %d 个（既不在 git，也没被 .gitignore 排除）：' % len(untracked_code))
            for p in untracked_code[:20]:
                print('     %s' % p)
            if len(untracked_code) > 20:
                print('     …还有 %d 个' % (len(untracked_code) - 20))
    elif verbose:
        print('✅ 未入库的代码文件：0 个')

    if dirty_count > DIRTY_LIMIT:
        ok = False
        if verbose:
            print('❌ 未提交的改动 %d 条，超过 %d 条上限，该提交了：' % (dirty_count, DIRTY_LIMIT))
            for p in dirty_list[:10]:
                print('     %s' % p)
            if len(dirty_list) > 10:
                print('     …还有 %d 条' % (len(dirty_list) - 10))
    elif verbose:
        print('✅ 未提交的改动：%d 条（上限 %d）' % (dirty_count, DIRTY_LIMIT))

    return ok


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def self_test():
    print('--- 自检 ---')
    tmp = tempfile.mkdtemp(prefix='drift_selftest_')
    failures = []
    try:
        if _git(tmp, 'init', '-q').returncode != 0:
            print('❌ 临时仓库建不起来，自检无法进行')
            return False
        _git(tmp, 'config', 'user.email', 'selftest@local')
        _git(tmp, 'config', 'user.name', 'selftest')
        # 基线：一个已跟踪文件 + 一个被忽略的 .py
        _write(os.path.join(tmp, '.gitignore'), 'ignored_*.py\n*.log\n')
        _write(os.path.join(tmp, 'ok.txt'), 'baseline\n')
        _git(tmp, 'add', '.gitignore', 'ok.txt')
        _git(tmp, 'commit', '-q', '-m', 'baseline')

        # a. 未跟踪 .py 必须判红
        _write(os.path.join(tmp, 'leaked_module.py'), 'x = 1\n')
        if check(tmp, verbose=False):
            failures.append('a: 未跟踪的 .py 没有判红')
        else:
            print('  ✅ a 未跟踪 .py 判红')

        # d. 被忽略的 .py 不该判红
        _write(os.path.join(tmp, 'ignored_artifact.py'), 'x = 1\n')
        ut, _, _ = inspect(tmp)
        if any(p.endswith('ignored_artifact.py') for p in ut):
            failures.append('d: 被 .gitignore 排除的 .py 仍被判成未入库')
        else:
            print('  ✅ d 被忽略的 .py 不判红')

        # b. add 之后转绿
        _git(tmp, 'add', 'leaked_module.py')
        if not check(tmp, verbose=False):
            failures.append('b: 入库后仍然判红')
        else:
            print('  ✅ b 入库后转绿')

        # c. 攒过多改动必须判红
        for i in range(DIRTY_LIMIT + 1):
            p = os.path.join(tmp, 'bulk_%02d.txt' % i)
            _write(p, 'x\n')
        _git(tmp, 'add', '.')
        if check(tmp, verbose=False):
            failures.append('c: %d 条改动没有判红' % (DIRTY_LIMIT + 1))
        else:
            print('  ✅ c 超过 %d 条改动判红' % DIRTY_LIMIT)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if failures:
        for f in failures:
            print('  ❌ %s' % f)
        print('❌ 自检失败 %d 项' % len(failures))
        return False
    print('✅ 自检 4/4 通过')
    return True


def main(argv):
    if '--self-test' in argv:
        return 0 if self_test() else 1
    print('=== 仓库漂移检查（root=%s）===' % ROOT)
    return 0 if check() else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
