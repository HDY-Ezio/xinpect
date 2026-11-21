# -*- coding: utf-8 -*-
"""把库里存的 score / grade 按新口径重算一遍（历史 441 份报告）。

为什么必须做：列表页、分享页、API 读的是扫描时落库的 score/grade，
报告页则按「我们认的条目」现算。不重算的话，同一个客户在自己的
扫描历史里会看到两个刻度混在一起（老的单子 50 分 C、新的单子 82 分 A）。

只改派生数据（score/grade 是 issue 列表的函数），不动 issues 本身。
改动前把旧值存进 scans_score_prev，随时能退回去。

用法：
    python3 scripts/backfill_score_scope.py --dry-run
    python3 scripts/backfill_score_scope.py --apply
    python3 scripts/backfill_score_scope.py --rollback     # 按 scans_score_prev 退回
"""
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MODE = '--dry-run'
if '--apply' in sys.argv:
    MODE = '--apply'
elif '--rollback' in sys.argv:
    MODE = '--rollback'

import modules.helpers as helpers  # noqa: E402
helpers.is_vip_user = lambda: True

from modules.db import get_db          # noqa: E402
from modules.scoring import calculate_score, calculate_tier_scores, grade_of  # noqa: E402
from modules.scan import _ledger_of    # noqa: E402
from modules.constants import FREE_BRAIN_IDS  # noqa: E402
from app import app                    # noqa: E402


def _load(results):
    if isinstance(results, dict):
        return results
    try:
        data = json.loads(results or '{}')
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


with app.app_context():
    db = get_db()

    if MODE == '--rollback':
        prev = db.execute("SELECT scan_id, score, grade FROM scans_score_prev").fetchall()
        for p in prev:
            db.execute("UPDATE scans SET score=?, grade=? WHERE scan_id=?",
                       (p['score'], p['grade'], p['scan_id']))
        db.commit()
        print('[已退回] %d 份扫描恢复成改动前的分数与等级' % len(prev))
        sys.exit(0)

    rows = db.execute(
        "SELECT scan_id, score, grade, results, scan_mode, credits_spent, file_count FROM scans "
        "WHERE scan_status='completed' AND results IS NOT NULL"
    ).fetchall()

    changed, same, skipped = 0, 0, 0
    move = Counter()
    filter_matters = 0
    vip_mix = Counter()
    samples = []
    plan = []

    for r in rows:
        data = _load(r['results'])
        issues = data.get('issues') or []
        if not isinstance(issues, list):
            skipped += 1
            continue

        # 历史扫描没法查当时的会员状态，只能从落库的事实倒推：
        # 免费通道是 scan_mode='free'/'basic'（匿名/未付费），付费扫描会扣积分。
        # 判错的后果很实在——免费单子会被算成 VIP，等级从 A 变成 SSS，
        # 等于把「付费才给 S」这条商品规则白送出去。
        mode = (r['scan_mode'] or '').lower()
        vip = (mode not in ('free', 'basic')) or (r['credits_spent'] or 0) > 0
        vip_mix['VIP' if vip else '免费'] += 1
        avail = None if vip else FREE_BRAIN_IDS

        ledger, uns, trim = _ledger_of(data)
        score_vip = calculate_score(issues, available_brain_ids=None)
        score_free = calculate_score(issues, available_brain_ids=FREE_BRAIN_IDS)
        if score_vip != score_free:
            filter_matters += 1
        new_score = score_vip if vip else score_free

        tiers = calculate_tier_scores(
            issues, available_brain_ids=avail, is_vip=vip,
            engines=ledger, unsupported=uns, trimmed=trim,
            file_count=r['file_count'],
        )
        new_grade = grade_of(new_score, tiers, is_vip=vip)

        old_score, old_grade = r['score'], (r['grade'] or '')
        if old_score == new_score and old_grade == new_grade:
            same += 1
            continue
        changed += 1
        move['%s%s -> %s%s' % (old_score, old_grade, new_score, new_grade)] += 1
        if len(samples) < 10:
            samples.append((r['scan_id'][:12], old_score, old_grade, new_score, new_grade))
        plan.append((new_score, new_grade, r['scan_id'], old_score, old_grade))

    print('扫描总数（完成且有结果）：%d' % len(rows))
    print('  会变化：%d 份    不变：%d 份    跳过（结果不是列表）：%d 份'
          % (changed, same, skipped))
    print('  会员判定：%s' % dict(vip_mix))
    print('  「免费/付费引擎过滤」实际影响的行数：%d' % filter_matters)
    print('\n变化方向（取前 12 种）：')
    for k, v in move.most_common(12):
        print('   %-24s %d 份' % (k, v))
    print('\n样例（scan / 旧分旧级 / 新分新级）：')
    for s in samples:
        print('   %s  %s%s -> %s%s' % s)

    if MODE != '--apply':
        print('\n[干跑] 没有写库。确认无误后加 --apply 执行。')
        sys.exit(0)

    db.execute("""CREATE TABLE IF NOT EXISTS scans_score_prev (
                    scan_id TEXT PRIMARY KEY,
                    score INTEGER, grade TEXT,
                    saved_at TEXT DEFAULT (datetime('now','localtime'))
                  )""")
    for new_score, new_grade, scan_id, old_score, old_grade in plan:
        # OR IGNORE：第二次跑不许把第一次记下的「真原件」盖掉，否则退无可退
        db.execute("INSERT OR IGNORE INTO scans_score_prev (scan_id, score, grade) "
                   "VALUES (?,?,?)", (scan_id, old_score, old_grade))
        db.execute("UPDATE scans SET score=?, grade=? WHERE scan_id=?",
                   (new_score, new_grade, scan_id))
    db.commit()
    print('\n[已写入] 更新 %d 份；旧值在 scans_score_prev（退回用）' % len(plan))
