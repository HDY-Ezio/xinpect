#!/usr/bin/env python3
"""把历史记录里的「自检流量」回填成 is_internal=1。

为什么必须回填：加列只是让以后的新记录分得清，历史那 1600 多条
（我们自己的监控脚本被当成人）如果不改，账面还是错的——
报表上照样写着「今天来了 1400 人」。

判据不在这里重写：直接用 `modules/visitor_scope.py` 的
`INTERNAL_UA_PREFIXES`。改判据只需要改那一个文件。

幂等：只处理 is_internal=0 的行，重复跑不会翻来覆去。

用法：
    python3 scripts/backfill_internal_flag.py --dry-run   # 只看会改多少
    python3 scripts/backfill_internal_flag.py
"""

import argparse
import os
import sqlite3
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'xinpect.db')


def load_scope():
    """按路径加载口径常量（避免拉起 Flask app，理由见 visitor_report.py）。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'xinpect_visitor_scope', os.path.join(BASE_DIR, 'modules', 'visitor_scope.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true', help='只统计，不写入')
    args = ap.parse_args()

    if not os.path.exists(DB_PATH):
        sys.exit(f'数据库不存在: {DB_PATH}')

    scope = load_scope()
    prefixes = scope.INTERNAL_UA_PREFIXES

    conn = sqlite3.connect(DB_PATH)
    cols = {row[1] for row in conn.execute('PRAGMA table_info(visitor_events)')}
    if 'is_internal' not in cols:
        sys.exit('表里还没有 is_internal 列——先重启官网服务让迁移生效，再跑本脚本。')

    # 前缀用 LIKE 拼，不是写死 UA 全串：将来新增监控脚本，UA 只要落在
    # xinpect-/xp- 命名空间下，这个脚本直接覆盖，不用改代码。
    where = ' OR '.join(["lower(ua) LIKE ? || '%'" for _ in prefixes])
    like_args = list(prefixes)

    hit = conn.execute(
        f'SELECT count(*) FROM visitor_events WHERE is_internal = 0 AND ({where})',
        like_args).fetchone()[0]
    total = conn.execute('SELECT count(*) FROM visitor_events').fetchone()[0]

    print(f'库内共 {total} 条记录，其中 {hit} 条是我们自己的工具（is_internal 待置 1）')
    if args.dry_run or not hit:
        if args.dry_run:
            print('（--dry-run，未写入）')
        conn.close()
        return

    conn.execute(
        f'UPDATE visitor_events SET is_internal = 1 WHERE is_internal = 0 AND ({where})',
        like_args)
    conn.commit()

    left = conn.execute(
        f'SELECT count(*) FROM visitor_events WHERE is_internal = 0 AND ({where})',
        like_args).fetchone()[0]
    print(f'已回填 {hit} 条，剩余待处理 {left} 条（应为 0）')
    conn.close()
    if left:
        sys.exit(1)


if __name__ == '__main__':
    main()
