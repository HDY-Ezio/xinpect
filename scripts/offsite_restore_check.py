#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从云上把最新备份拉回来，验证它是**能用的数据库**。

为什么要做：2026-11-14 之前，本站备份只在本地跑 `PRAGMA integrity_check`。
拷贝和压缩都成功、日志写着「备份成功 ✅」，这不代表云上那份能还原。
唯一能证明备份有用的动作是**真的拿它当数据库打开一次**。

判据（全过才算通过）：
1. 能从云上取回，字节数与记录一致
2. 能解压（不是半截 gzip）
3. PRAGMA integrity_check == ok
4. 关键表都在，且用户/订单/扫描三张表有数据（空库也能"完整"，但没用）

每周日 05:00 跑一次；也可以随时手工跑。
"""
import argparse
import gzip
import os
import shutil
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import offsite_backup as ob  # noqa: E402


def _count(db, table):
    try:
        with sqlite3.connect('file:%s?mode=ro' % db, uri=True) as c:
            return c.execute('SELECT COUNT(*) FROM "%s"' % table).fetchone()[0]
    except sqlite3.Error:
        return None


def check(tables=('users', 'orders', 'scans')):
    """返回 (是否通过, 报告行列表)。"""
    lines = []
    cos = ob.Cos(ob.load_conf())

    keys, _trunc = cos.list_objects()
    if not keys:
        return False, ['云上一个备份都没有（%s）' % ob.PREFIX]

    key, size_cloud = sorted(keys)[-1]
    lines.append('云上最新：%s（%d 字节）' % (key, size_cloud))

    tmpdir = tempfile.mkdtemp(prefix='xinpect_restore_')
    gz_path = os.path.join(tmpdir, os.path.basename(key))
    db_path = gz_path[:-3] if gz_path.endswith('.gz') else gz_path + '.db'
    try:
        with cos._request('GET', key, timeout=300) as r:
            with open(gz_path, 'wb') as f:
                shutil.copyfileobj(r, f)
        got = os.path.getsize(gz_path)
        lines.append('下载回来：%d 字节' % got)
        if got != size_cloud:
            return False, lines + ['❌ 下载大小与云上记录不一致（%d vs %d）' % (got, size_cloud)]

        try:
            with gzip.open(gz_path, 'rb') as src, open(db_path, 'wb') as dst:
                shutil.copyfileobj(src, dst)
        except (OSError, EOFError) as e:
            return False, lines + ['❌ 解压失败（压缩包可能是半截）：%s' % e]
        lines.append('解压后：%d 字节' % os.path.getsize(db_path))

        with sqlite3.connect('file:%s?mode=ro' % db_path, uri=True) as c:
            integrity = c.execute('PRAGMA integrity_check').fetchone()[0]
        lines.append('完整性检查：%s' % integrity)
        if integrity != 'ok':
            return False, lines + ['❌ 数据库完整性异常']

        bad = []
        for t in tables:
            n = _count(db_path, t)
            if n is None:
                bad.append('%s 表不存在' % t)
            elif n == 0:
                bad.append('%s 表是空的' % t)
            else:
                lines.append('%s：%d 行' % (t, n))
        if bad:
            return False, lines + ['❌ ' + '；'.join(bad)]
        return True, lines
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', help='把结果写到这个 JSON 文件（给监控读）')
    args = ap.parse_args(argv)

    ok, lines = check()
    for line in lines:
        print(line)
    print('✅ 云上备份可以还原' if ok else '❌ 云上备份不能还原')

    if args.json:
        import json
        import time
        with open(args.json, 'w') as f:
            json.dump({'epoch': int(time.time()), 'ok': ok,
                       'when': time.strftime('%Y-%m-%d %H:%M:%S'),
                       'detail': lines[-6:]}, f, ensure_ascii=False)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
