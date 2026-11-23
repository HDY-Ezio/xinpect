# -*- coding: utf-8 -*-
"""自检结论→告警 这条链路的守卫。

钉四件事（不是「函数存在」，是「红了真能叫醒人」）：
1. 结论正常时安静（不制造噪音，否则人就不看了）
2. 自检失败时说出是哪一段失败（不让人自己去翻日志找）
3. 结论太旧 / 文件没了 / 文件坏了，都要叫（「没跑」和「跑挂了」一样危险）
4. 套件收尾真的会调记录器（写了文件没人调，等于白写）

第 4 条是重点：2026-11-14 之前，套件成功了只 echo 一行到 cron.log。
日志里那行和「脚本崩在半路」长得一样，红了也没人知道。
"""
import json
import os
import sys
import tempfile
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import critical_path_monitor as cpm  # noqa: E402
sys.path.insert(0, os.path.join(_ROOT, 'scripts'))
import record_qa_result as rec  # noqa: E402


def _write(payload, path):
    with open(path, 'w') as f:
        json.dump(payload, f)
    return path


def test_fresh_ok_is_silent():
    """正常时必须一声不吭。天天误报的系统，等于没有系统。"""
    d = tempfile.mkdtemp()
    p = _write({'epoch': int(time.time()), 'ok': True,
                'rc': {'qa': 0, 'pytest': 0, 'pay': 0}}, os.path.join(d, 'r.json'))
    assert cpm.check_selfcheck_result(p) == []


def test_failed_reports_failing_segment():
    d = tempfile.mkdtemp()
    p = _write({'epoch': int(time.time()), 'ok': False,
                'rc': {'qa': 0, 'pytest': 1, 'pay': 0}}, os.path.join(d, 'r.json'))
    out = cpm.check_selfcheck_result(p)
    assert out, '自检失败竟然没告警'
    assert 'pytest' in out[0], out


def test_stale_result_is_caught():
    """结论超过 8 小时没更新 = 套件没在跑，必须叫。"""
    d = tempfile.mkdtemp()
    p = _write({'epoch': int(time.time()) - 9 * 3600, 'ok': True,
                'rc': {'qa': 0}}, os.path.join(d, 'r.json'))
    out = cpm.check_selfcheck_result(p)
    assert out and '小时' in out[0], out


def test_missing_file_is_caught():
    out = cpm.check_selfcheck_result('/nonexistent/last_result.json')
    assert out and '从没' in out[0], out


def test_corrupt_file_is_caught():
    """文件坏了不能默默当正常——读不出来本身就是异常。"""
    d = tempfile.mkdtemp()
    p = os.path.join(d, 'r.json')
    with open(p, 'w') as f:
        f.write('{这不是 json')
    out = cpm.check_selfcheck_result(p)
    assert out and '读不出来' in out[0], out


def test_record_roundtrip():
    """记录器写出来的东西，监控必须读得懂、且判为正常（闭环）。"""
    d = tempfile.mkdtemp()
    p = os.path.join(d, 'r.json')
    rec.write_result(True, {'qa': 0, 'pytest': 0, 'pay': 0}, path=p)
    assert cpm.check_selfcheck_result(p) == []

    rec.write_result(False, {'qa': 0, 'pytest': 2, 'pay': 0}, path=p)
    out = cpm.check_selfcheck_result(p)
    assert out and 'pytest' in out[0], out


def test_qa_suite_actually_calls_recorder():
    """钉调用方：套件收尾必须真的去写结论，否则前面全白搭。"""
    p = os.path.join(_ROOT, 'scripts', 'run_qa_suite.sh')
    with open(p, encoding='utf-8') as f:
        src = f.read()
    assert 'record_qa_result.py ok' in src, '成功分支没写结论'
    assert 'record_qa_result.py fail' in src, '失败分支没写结论'


def test_monitor_actually_consumes_result():
    """钉消费方：监控主流程必须把这条检查挂进去。"""
    p = os.path.join(_ROOT, 'critical_path_monitor.py')
    with open(p, encoding='utf-8') as f:
        src = f.read()
    assert 'check_selfcheck_result()' in src, '监控没调这条检查'


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_') and callable(v)]
    bad = 0
    for t in tests:
        try:
            t()
            print('  ✅ %s' % t.__name__)
        except AssertionError as e:
            bad += 1
            print('  ❌ %s: %s' % (t.__name__, e))
    print('%s 自检结论告警守卫: %d 项, 通过 %d, 失败 %d'
          % ('✅' if not bad else '❌', len(tests), len(tests) - bad, bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
