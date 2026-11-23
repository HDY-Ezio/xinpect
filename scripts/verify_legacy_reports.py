#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回归：库里所有历史完成报告，改完必须和改前长得一样。

为什么单开这条：2026-11-04 之前的报告没有 engines 字段。
如果新逻辑把「没有台账」也当成「没查」，两百多份历史报告会集体变成
「未检测」——那不是诚实，那是把历史数据判死。这次改动对老报告必须零影响。

判据（全部满足才算过）：
  ① 渲染不抛异常
  ② 页面里不出现「未检测（无结果）」「部分未检测」
  ③ 三个维度的分数与旧算法（空 issues = 100）逐份一致
"""
import json
import sqlite3
import sys

sys.path.insert(0, '/opt/xinpect-website')
from app import app                                        # noqa: E402
from modules.constants import DB_PATH                      # noqa: E402
from modules.scan import _build_dimensions                 # noqa: E402
from modules.scoring import calculate_dimension_score      # noqa: E402


def main():
    db = sqlite3.connect(DB_PATH)
    rows = db.execute(
        "SELECT scan_id, scan_status, results FROM scans "
        "WHERE scan_status='completed' AND results IS NOT NULL ORDER BY id"
    ).fetchall()
    db.close()
    print(f'共 {len(rows)} 份完成报告')

    bad_render = 0
    bad_flag = 0
    bad_score = 0
    legacy = 0
    with_ledger = 0
    app.config['TESTING'] = True

    for scan_id, _status, raw in rows:
        try:
            results = json.loads(raw or '{}')
        except ValueError:
            continue
        if isinstance(results, list):
            # 最老的报告 results 直接就是 issues 数组
            results = {'issues': results}
        if not isinstance(results, dict):
            continue
        issues = results.get('issues') or []
        has_ledger = 'engines' in results
        legacy += 0 if has_ledger else 1
        with_ledger += 1 if has_ledger else 0

        led, uns, trim = (
            results.get('engines') or None,
            len(results.get('unsupported_files') or []),
            len(results.get('trimmed_files') or []),
        )
        try:
            dims = _build_dimensions(issues, True, led, uns, trim)
        except Exception as e:
            bad_render += 1
            print(f'  RENDER FAIL {scan_id[:8]}: {e}')
            continue

        if not has_ledger:
            # 老报告：每个维度的分数必须与旧算法完全一致
            for d in dims:
                expect = calculate_dimension_score(
                    [i for i in issues if str(i.get('brain_id')) == d['id']]
                )
                if d['locked']:
                    continue
                if d['score'] != expect or d['status_text']:
                    bad_score += 1
                    print(f'  SCORE DIFF {scan_id[:8]} brain={d["id"]} '
                          f'{d["score"]} != {expect} flag={d["status_text"]!r}')
                    break

    print(f'老报告(无台账) {legacy} 份 / 新报告(有台账) {with_ledger} 份')
    print(f'渲染失败 {bad_render} / 分数漂移 {bad_score} / 误标未检测 {bad_flag}')

    # 模板真的能渲染老报告（挑一份最老的）
    from flask import render_template
    from modules.constants import TIERS
    from modules.scoring import calculate_tier_scores

    db = sqlite3.connect(DB_PATH)
    row = db.execute(
        "SELECT scan_id, results FROM scans WHERE scan_status='completed' "
        "AND results IS NOT NULL ORDER BY id LIMIT 1"
    ).fetchone()
    db.close()
    sid, raw = row
    results = json.loads(raw)
    if isinstance(results, list):
        results = {'issues': results}
    issues = results.get('issues') or []
    dims = _build_dimensions(issues, True, None, 0, 0)
    ts = calculate_tier_scores(issues, is_vip=True, engines=None)
    with app.test_request_context('/report/x'):
        html = render_template(
            'report.html', scan_id=sid, report_title='回归', score=100, grade='S',
            conclusion={'headline': '', 'detail': ''}, file_count=1,
            total_issues=len(issues), created_at='2026-01-01 00:00',
            dimensions=dims, tier_scores=ts, tiers=TIERS,
            visible_issues=[], visible_issues_count=0,
            style_issues=[], style_count=0, profile_groups=[], profile_count=0,
            suppressed_groups=[], suppressed_total=0, suppressed_stats={},
            severity_counts={'critical': 0, 'high': 0, 'medium': 0, 'low': 0, 'info': 0},
            bb_scores={}, is_vip=True, scan_mode='deep', is_fix_eligible=False,
            fix_roadmap=[], fix_progress=None, share_token='t',
        )
    for flag in ('未检测（无结果）', '部分未检测'):
        if flag in html:
            bad_flag += 1
            print(f'  FLAG LEAK 老报告页面出现「{flag}」')
    print(f'模板渲染老报告 {sid[:8]}: len={len(html)}')

    ok = not (bad_render or bad_score or bad_flag)
    print('RESULT:', 'OK' if ok else 'FAILED')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
