#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫红绿验证：把实现改坏，测试必须变红；恢复后必须变绿。

2026-11-04 立的规矩：「写了守卫」不等于「守卫有用」。
`check()` 只记录失败不抛异常那次教训说明，测试文件本身也会骗人。
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys

SITE = pathlib.Path('/opt/xinpect-website')
SCAN = SITE / 'modules' / 'scan.py'
SCORING = SITE / 'modules' / 'scoring.py'
TEST = 'tests/test_report_dimensions.py'
ENV = {
    'PYTHONDONTWRITEBYTECODE': '1',
    'XINPECT_SECRET': 'pytest-placeholder-secret-0123456789abcdef',
    'PATH': '/usr/local/bin:/usr/bin:/bin',
}


def md5(p):
    return hashlib.md5(p.read_bytes()).hexdigest()


def run_test():
    r = subprocess.run(
        [sys.executable, '-m', 'pytest', TEST, '-q', '--no-header', '-p', 'no:cacheprovider'],
        cwd=str(SITE), env=ENV, capture_output=True, text=True,
    )
    tail = [l for l in r.stdout.splitlines() if 'passed' in l or 'failed' in l]
    return r.returncode, (tail[-1] if tail else r.stdout[-200:])


def break_and_check(path, old, new, label):
    orig = path.read_text(encoding='utf-8')
    before = md5(path)
    assert old in orig, f'[{label}] 锚点失配，改不坏'
    broken = orig.replace(old, new, 1)
    assert broken != orig
    try:
        path.write_text(broken, encoding='utf-8')
        rc, summary = run_test()
        print(f'[{label}] 改坏后 -> rc={rc} {summary}')
        if rc == 0:
            print(f'!! [{label}] 改坏了测试还是绿的，这条守卫是假的')
            return False
    finally:
        path.write_text(orig, encoding='utf-8')
        assert md5(path) == before, f'[{label}] 恢复后 md5 不一致'
    rc, summary = run_test()
    print(f'[{label}] 恢复后 -> rc={rc} {summary}')
    return rc == 0


def main():
    ok = True
    # ① 维度卡回到「不认识台账」：引擎没跑也照给 100
    ok &= break_and_check(
        SCAN,
        '        elif state == _DIM_NOT_RUN:',
        '        elif False:  # 故意改坏：假装台账不存在',
        '维度卡不认台账',
    )
    # ② 三层评分回到「缺的引擎按 100 分顶上」
    ok &= break_and_check(
        SCORING,
        '        if engines:\n            ok_brain_ids = [',
        '        if False:  # 故意改坏：忽略台账\n            ok_brain_ids = [',
        '三层评分忽略台账',
    )
    # ③ 模板不再渲染未检测
    ok &= break_and_check(
        SITE / 'templates' / 'report.html',
        '{{ dim.status_text }}（无结果）',
        '&nbsp;',
        '模板不渲染未检测',
    )
    print('OK' if ok else 'FAILED')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
