#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扫描结果库清理：删掉超过保留期的旧记录（默认 30 天）。

用法：
    python3 scripts/purge_scan_cache.py --dry-run      # 只看要删多少，不动手
    python3 scripts/purge_scan_cache.py                # 正式清理
    python3 scripts/purge_scan_cache.py --compact      # 清理 + 空闲时 VACUUM 缩文件

退出码：0 正常（含「有任务在跑所以跳过」）；1 出错。
跳过会在日志里写明原因——「脚本跑过了」不等于「清理生效了」，
这两件事必须分开记，否则又是「进程活着就算健康」那种自欺。
"""

import argparse
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from modules import result_retention as rr  # noqa: E402


def _human(n):
    if n is None:
        return '-'
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    v = float(n)
    for u in units:
        if v < 1024 or u == units[-1]:
            return '%.2f %s' % (v, u) if u != 'B' else '%d B' % v
        v /= 1024.0


def main(argv=None):
    ap = argparse.ArgumentParser(description='清理扫描结果库的过期记录')
    ap.add_argument('--dry-run', action='store_true', help='只统计，不删除')
    ap.add_argument('--compact', action='store_true', help='清理后空闲时 VACUUM 缩文件')
    ap.add_argument('--force', action='store_true', help='有在途任务也照做（危险，只在确认无人用时）')
    ap.add_argument('--json', dest='json_path', default=None, help='把账单写成 JSON 文件')
    args = ap.parse_args(argv)

    db_path = rr.resolve_db_path()
    website_db = os.path.join(_ROOT, 'xinpect.db')

    print('[扫描结果库清理] 库：%s' % db_path)
    print('[扫描结果库清理] 保留 %d 天' % rr.RETENTION_DAYS)

    before = rr.survey(db_path)
    print('[扫描结果库清理] 现状：%s / %d 条扫描 / %d 条代码副本 / 最早 %s' % (
        _human(before['size_bytes']), before['total_scans'],
        before['expired_code_rows'], before['oldest_at']))
    print('[扫描结果库清理] 过期判定线：%s 之前（待删 %d 条扫描、%s 代码原文）' % (
        before['cutoff_at'], before['expired_scans'],
        _human(before['expired_code_bytes'])))

    report = rr.purge(db_path=db_path, website_db_path=website_db, dry_run=args.dry_run,
                      force=args.force)
    report['survey_before'] = before

    if report['skipped']:
        print('[扫描结果库清理] 本轮跳过：%s（%s）' % (report['skipped'], report['reason']))
    else:
        print('[扫描结果库清理] %s 删除 %d 条扫描 / %d 条代码副本（%d 批，%.1f 秒）' % (
            '试运行' if args.dry_run else '已',
            report['deleted_scans'], report['deleted_code_rows'],
            report['batches'], report['elapsed_seconds']))
        print('[扫描结果库清理] 文件：%s → %s（VACUUM 前不会缩小，空闲页会被新数据复用）' % (
            _human(report['size_before']), _human(report['size_after'])))

    if args.compact:
        info = rr.compact(db_path=db_path, website_db_path=website_db, dry_run=args.dry_run,
                          force=args.force)
        report['compact'] = info
        if info['skipped']:
            print('[扫描结果库清理] 不缩文件：%s（%s）' % (info['skipped'], info['reason']))
        else:
            print('[扫描结果库清理] VACUUM 完成：%s → %s（%.1f 秒）' % (
                _human(info['size_before']), _human(info['size_after']),
                info['elapsed_seconds']))

    dangling = rr.dangling_code_rows(db_path)
    report['dangling_code_rows'] = dangling
    print('[扫描结果库清理] 孤儿代码副本：%d 条（应为 0）' % dangling)

    if args.json_path:
        os.makedirs(os.path.dirname(args.json_path) or '.', exist_ok=True)
        with open(args.json_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

    return 1 if dangling else 0


if __name__ == '__main__':
    sys.exit(main())
