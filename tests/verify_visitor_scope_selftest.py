#!/usr/bin/env python3
"""造坏自检：把访客口径的实现改坏，`verify_visitor_scope.py` 必须判红。

## 为什么必须有这个

守卫全绿有两种可能：实现真的对，或者守卫根本没在测东西。
后者非常常见——判据写成 `assert 'is_internal' in src`（只查字符串在不在），
实现改成什么都不写它照样绿。所以每个守卫都必须能证明自己会红。

## 手法

每个用例：备份 → 改坏 → 跑守卫 → **断言它非 0** → 恢复 → 核对 md5。
全程 try/finally，任何一步炸了都要把文件放回去——
这些是生产文件，改坏留在那儿，官网就会把监控流量重新数成客户。

## 造坏清单

1. `is_internal_ua()` 永远返回 False  → 内部流量重新混进访客
2. `VISITOR_FILTER` 退回 `is_bot = 0`  → 报表不再排除自检流量
3. 报表里塞一行裸 `is_bot = 0`        → 口径重新散落（单一出处被破坏）
4. 判据改成 UA 全串白名单（放弃前缀规则）→ 新脚本不再自动覆盖
"""

import hashlib
import os
import shutil
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCOPE = os.path.join(BASE_DIR, 'modules', 'visitor_scope.py')
REPORT = os.path.join(BASE_DIR, 'scripts', 'visitor_report.py')
GUARD = os.path.join(BASE_DIR, 'tests', 'verify_visitor_scope.py')
ENV_FILE = '/etc/xinpect/website.env'


def _md5(path):
    with open(path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()


def _read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def _write(path, text):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def _run_guard():
    """按线上环境跑守卫（要 XINPECT_SECRET，否则 import app 就炸）。"""
    cmd = f'set -a; . {ENV_FILE} 2>/dev/null; set +a; '
    cmd += f'{sys.executable} {GUARD}'
    r = subprocess.run(['bash', '-c', cmd], capture_output=True, text=True,
                       cwd=BASE_DIR, timeout=300)
    return r.returncode, (r.stdout or '') + (r.stderr or '')


def _case(name, path, transform, expect_in_output=None):
    """改坏 → 跑守卫 → 必须红 → 恢复。返回 (ok, detail)。"""
    original = _read(path)
    before = _md5(path)
    try:
        _write(path, transform(original))
        rc, out = _run_guard()
    finally:
        _write(path, original)
        after = _md5(path)
        if after != before:
            return False, f'{name}: 恢复失败！md5 {before} -> {after}'

    if rc == 0:
        return False, f'{name}: 实现已改坏，守卫仍然全绿（守卫是摆设）'
    if expect_in_output and expect_in_output not in out:
        # 判红但红错了地方，也算失败：说明是别的原因炸的，不是这条判据在起作用
        return False, (f'{name}: 判红了但原因不对，输出里没有 '
                       f'{expect_in_output!r}')
    return True, f'{name}: 判红 rc={rc}'


def case_internal_always_false(src):
    return src.replace(
        '    if not ua:\n        return False\n'
        '    return ua.strip().lower().startswith(INTERNAL_UA_PREFIXES)',
        '    return False')


def case_visitor_filter_degraded(src):
    return src.replace(
        "VISITOR_FILTER = 'is_bot = 0 AND is_internal = 0'",
        "VISITOR_FILTER = 'is_bot = 0'   # 造坏：不再排除自检流量")


def case_report_bare_is_bot(src):
    marker = "    print(f'===== 访客与转化"
    bad = ("    _ = conn.execute('SELECT 1 FROM visitor_events "
           "WHERE is_bot = 0 LIMIT 1')\n")
    return src.replace(marker, bad + marker, 1)


def case_prefix_becomes_whitelist(src):
    return src.replace(
        "    return ua.strip().lower().startswith(INTERNAL_UA_PREFIXES)",
        "    return ua.strip().lower() in ('xinpect-uptime-sv/1.0',)")


def main():
    if not os.path.exists(ENV_FILE):
        print(f'[跳过] 找不到 {ENV_FILE}，无法按线上环境跑守卫')
        return 1

    cases = [
        ('内部流量判据失效', SCOPE, case_internal_always_false, '内部工具没被标记'),
        ('口径退回旧版', SCOPE, case_visitor_filter_degraded, '内部流量被算进了访客'),
        ('口径重新散落', REPORT, case_report_bare_is_bot, '必须改用 {VF}'),
        # 退化成白名单后，最先撞红的是「xp-consistency-guard 没被认成内部」
        # 这条断言——白名单里只有 xinpect-uptime-sv 一个串。
        ('前缀规则退化成白名单', SCOPE, case_prefix_becomes_whitelist, '没被认成内部'),
    ]

    passed = 0
    for name, path, fn, hint in cases:
        ok, detail = _case(name, path, fn, expect_in_output=hint)
        print(('[ok] ' if ok else '[FAIL] ') + detail)
        if not ok:
            print('SELFTEST_FAIL')
            return 1
        passed += 1

    print(f'VISITOR_SCOPE_SELFTEST_PASS={passed}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
