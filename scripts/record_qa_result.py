#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把整套自检的最终结论落成一个文件，供关键链路监控读取。

为什么要这个文件：

自检红了，只往 cron.log 里写一行。而 cron.log 没人看 —— 2026-11-14 新加的
「定时任务出活」守卫更是如此：它红了也只是日志里多一行字，等于自己跟自己报喜。

结论必须落到一个固定文件上，由关键链路监控每 15 分钟读一次、红了发邮件，
才叫闭环。这跟「有调用方、真跑出结果」是同一个判据。

用法（run_qa_suite.sh 收尾调用）：
    record_qa_result.py ok   qa=0 pytest=0 category=0 engine=0 bench=0 cost=0 pay=0
    record_qa_result.py fail qa=0 pytest=1 category=0 engine=0 bench=0 cost=0 pay=0
"""
import json
import os
import sys
import time

DEFAULT_PATH = '/opt/xinpect-website/tests/reports/last_result.json'


def write_result(ok, rc, path=None):
    """原子写入：先写 .tmp 再 rename，避免监控读到半个 JSON。"""
    path = path or os.environ.get('QA_RESULT_PATH', DEFAULT_PATH)
    payload = {
        'epoch': int(time.time()),
        'when': time.strftime('%Y-%m-%d %H:%M:%S'),
        'ok': bool(ok),
        'rc': {k: int(v) for k, v in rc.items()},
    }
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(tmp, path)
    return payload


def main(argv):
    if len(argv) < 2 or argv[1] not in ('ok', 'fail'):
        print('用法: record_qa_result.py ok|fail key=value ...', file=sys.stderr)
        return 2
    rc = {}
    for item in argv[2:]:
        if '=' not in item:
            print('参数要写成 key=value：%r' % item, file=sys.stderr)
            return 2
        k, v = item.split('=', 1)
        rc[k] = v
    try:
        write_result(argv[1] == 'ok', rc)
    except OSError as e:
        # 写不进去不能把套件本身搞崩，但必须让人看见
        print('写自检结论失败：%s' % e, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
