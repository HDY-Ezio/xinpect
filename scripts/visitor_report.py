#!/usr/bin/env python3
"""访客与注册转化报表 —— 回答「来了多少人、走到哪一步、卡在哪」。

用法：
    sudo -u xinpect-web python3 scripts/visitor_report.py            # 最近 7 天
    sudo -u xinpect-web python3 scripts/visitor_report.py --days 30  # 最近 30 天

口径说明（重要）：
- 「访客」= 独立 vid，且不是爬虫、也不是我们自己的工具。
  判据只有一处出处：`modules/visitor_scope.py` 的 `VISITOR_FILTER`。
  vid 是匿名 cookie，不依赖 IP（443 前端是 sslh，nginx 拿不到真实 IP）。
  **2026-11-18 修正**：此前只排除 `is_bot=1`，而我们自己的监控/守卫脚本
  （UA 是 `xinpect-*` / `xp-*`）没命中爬虫特征，被算成了真人——报表上
  每天一千多人，实际真人零。现在它们单独记 `is_internal=1`，见文末那行。
- 同一 vid 先匿名后注册的，会被合并到注册用户，这是跨匿名/登录的同一人。
- 表里有两类记录，必须分开看：
    kind='page'  页面访问（after_request 自动记）
    kind='event' 行为事件（track_event 显式记，path 存事件名，detail 存 JSON）
  混着算会把「点了开始检测」当成「访问了一个叫 try.submit 的页面」。
"""

import argparse
import os
import sqlite3
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'xinpect.db')

PAGE = "kind = 'page'"
EVENT = "kind = 'event'"


def q(conn, sql, args=()):
    try:
        return conn.execute(sql, args).fetchall()
    except sqlite3.Error as exc:
        print(f'  [查询失败] {exc}')
        return []


def pct(a, b):
    return f'{(a * 100.0 / b):.1f}%' if b else '-'


def has_column(conn, table, column):
    try:
        return column in {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}
    except sqlite3.Error:
        return False


def load_scope():
    """读「真人访客」口径常量。

    **不能 `from modules.visitor_scope import ...`**：`modules/__init__` 会把
    整个 Flask app 拉起来（还要 XINPECT_SECRET），报表只要一个字符串。
    所以按文件路径直接加载——`visitor_scope.py` 不 import 任何东西，没副作用。
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'xinpect_visitor_scope', os.path.join(BASE_DIR, 'modules', 'visitor_scope.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=7)
    args = ap.parse_args()
    since = f'-{args.days} days'
    since_args = (since,)

    if not os.path.exists(DB_PATH):
        sys.exit(f'数据库不存在: {DB_PATH}')

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    has_table = conn.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='visitor_events'"
    ).fetchone()[0]
    if not has_table:
        print('visitor_events 表还不存在——埋点尚未产生数据。')
        return

    # 老库可能还没补 kind 列（升级过但进程没重启）。降级成原来的口径，不报错。
    kind_ready = has_column(conn, 'visitor_events', 'kind')
    if not kind_ready:
        print('[提示] 表里还没有 kind 列（迁移未生效），下面只统计页面访问。\n')
        where = "created_at >= datetime('now','localtime',?)"
    else:
        where = f"created_at >= datetime('now','localtime',?) AND {PAGE}"
    events_ready = kind_ready and has_column(conn, 'visitor_events', 'detail')
    page_only = f' AND {PAGE}' if kind_ready else ''

    # 「真人」的判据只有一处出处（modules/visitor_scope.py）。
    # 本文件不许再出现裸的 `is_bot = 0` —— 见 tests/verify_visitor_scope.py。
    scope = load_scope()
    internal_ready = has_column(conn, 'visitor_events', 'is_internal')
    if not internal_ready:
        print('[提示] 表里还没有 is_internal 列（迁移未生效），'
              '自检流量仍会被算进访客。\n')
    VF = scope.VISITOR_FILTER if internal_ready else scope.VISITOR_FILTER_LEGACY

    print(f'===== 访客与转化（最近 {args.days} 天）=====\n')

    rows = q(conn, f'''
        SELECT
            count(*)                                             AS 请求数,
            count(DISTINCT vid)                                  AS 独立访客,
            sum(CASE WHEN user_id IS NOT NULL THEN 1 ELSE 0 END) AS 登录态请求
        FROM visitor_events
        WHERE {where} AND {VF}
    ''', since_args)
    if rows:
        r = rows[0]
        print(f'页面请求 {r["请求数"]} 次 / 独立访客 {r["独立访客"]} 人 '
              f'/ 登录态请求 {r["登录态请求"]} 次')

    bots = q(conn, f'SELECT count(*) c FROM visitor_events WHERE {where} AND is_bot = 1',
             since_args)
    if bots and bots[0]['c']:
        print(f'（另有爬虫请求 {bots[0]["c"]} 次，已排除）')
    # 自检流量单独报一行：不报出来的话，将来只会有人对着「访客 0」怀疑
    # 「是不是埋点坏了」，而看不见「其实是我们自己在刷」。
    if internal_ready:
        ins = q(conn, f'''
            SELECT count(*) c, count(DISTINCT vid) v FROM visitor_events
            WHERE {where} AND is_internal = 1
        ''', since_args)
        if ins and ins[0]['c']:
            print(f'（另有我们自己的监控/守卫脚本 {ins[0]["c"]} 次 / '
                  f'{ins[0]["v"]} 个 id，已排除）')
    print()

    print('--- 各页面独立访客 ---')
    for row in q(conn, f'''
        SELECT path, count(*) AS 次数, count(DISTINCT vid) AS 访客
        FROM visitor_events
        WHERE {where} AND {VF}
        GROUP BY path ORDER BY 访客 DESC LIMIT 15
    ''', since_args):
        print(f'  {row["访客"]:>4} 人 {row["次数"]:>5} 次  {row["path"]}')

    # ------------------------------------------------------------------
    # 试扫漏斗：免注册入口到底有没有人走完
    # ------------------------------------------------------------------
    if events_ready:
        print('\n--- 免费试扫漏斗 ---')
        f = q(conn, f'''
            SELECT
                count(DISTINCT CASE WHEN path = '/try' THEN vid END)          AS 打开,
                count(DISTINCT CASE WHEN path = 'try.submit' THEN vid END)    AS 提交,
                count(DISTINCT CASE WHEN path = 'try.ok' THEN vid END)        AS 出结果,
                count(DISTINCT CASE WHEN path = 'try.cta_click' THEN vid END) AS 点注册,
                count(DISTINCT CASE WHEN path = 'try.fail' THEN vid END)      AS 失败
            FROM visitor_events
            WHERE created_at >= datetime('now','localtime',?) AND {VF}
        ''', since_args)
        if f:
            r = f[0]
            opened = r['打开'] or 0
            submitted = r['提交'] or 0
            ok = r['出结果'] or 0
            cta = r['点注册'] or 0
            print(f'  打开试扫页     {opened:>4} 人')
            print(f'  点了开始检测   {submitted:>4} 人   占打开 {pct(submitted, opened)}')
            print(f'  成功出结果     {ok:>4} 人   占提交 {pct(ok, submitted)}')
            print(f'  点了注册引导   {cta:>4} 人   占出结果 {pct(cta, ok)}')
            failed = r['失败'] or 0
            if failed or ok:
                print(f'  （其中失败过   {failed:>4} 人）')

        # 试扫完的人最后有没有真的注册（同一 vid 后续带 user_id）
        turned = q(conn, f'''
            SELECT count(DISTINCT vid) AS 人数 FROM visitor_events
            WHERE created_at >= datetime('now','localtime',?) AND {VF}
              AND user_id IS NOT NULL
              AND vid IN (
                  SELECT vid FROM visitor_events
                  WHERE created_at >= datetime('now','localtime',?)
                    AND {EVENT} AND path IN ('try.ok', 'try.cta_click')
              )
        ''', (since, since))
        if turned:
            n = turned[0]['人数'] or 0
            print(f'  其中已注册     {n:>4} 人   占点注册 {pct(n, cta)}')

        # 全站额度水位：这个数快满的时候，真人会被 429 挡在门外，
        # 而他们不会跑来告诉你——只能靠这一行看见。
        #
        # 上限从 modules/limits.py 读，和限流用同一个常量，不会漂移。
        # 但**不能用常规 import**：`modules` 包的 __init__ 会把整个 Flask app
        # 拉起来（还要 XINPECT_SECRET），报表只要一个数字，不该被它拖住。
        # 所以按文件路径直接加载——limits.py 只依赖 os，没有副作用。
        _cap = None
        try:
            import importlib.util
            _spec = importlib.util.spec_from_file_location(
                'xinpect_limits', os.path.join(BASE_DIR, 'modules', 'limits.py'))
            _mod = importlib.util.module_from_spec(_spec)
            _spec.loader.exec_module(_mod)
            _cap = _mod.TRY_GLOBAL_DAILY_LIMIT
        except Exception as exc:  # noqa: BLE001
            print(f'  [警告] 读不到全站试扫上限（{exc}），这行跳过')
        if _cap:
            used_row = q(conn, '''
                SELECT count(*) AS n FROM visitor_events
                WHERE kind = 'event' AND path = 'try.ok'
                  AND created_at >= date('now','localtime')
            ''')
            used = (used_row[0]['n'] if used_row else 0) or 0
            bar = '#' * int(20 * used / _cap)
            print(f'  今日全站额度   {used:>4}/{_cap}  {bar}')
            if used >= _cap * 0.8:
                print('  [注意] 额度已过 80%，再往上真人就会被 429 挡住')

        # 失败原因：卡在哪一步
        reasons = q(conn, f'''
            SELECT json_extract(detail, '$.reason') AS reason, count(*) AS 次数,
                   count(DISTINCT vid) AS 人数
            FROM visitor_events
            WHERE created_at >= datetime('now','localtime',?) AND {VF}
              AND {EVENT} AND path = 'try.fail'
            GROUP BY reason ORDER BY 次数 DESC
        ''', since_args)
        if reasons:
            print('\n  -- 试扫失败原因 --')
            for row in reasons:
                print(f'    {row["人数"]:>3} 人 {row["次数"]:>4} 次  {row["reason"] or "(未记录)"}')

        # 什么结果的人更愿意点注册——按检出问题数分桶
        buckets = q(conn, f'''
            SELECT
                CASE
                    WHEN json_extract(detail, '$.issues') IS NULL THEN '未知'
                    WHEN json_extract(detail, '$.issues') = 0  THEN '0 条（干净）'
                    WHEN json_extract(detail, '$.issues') <= 2 THEN '1-2 条'
                    WHEN json_extract(detail, '$.issues') <= 5 THEN '3-5 条'
                    ELSE '6 条以上'
                END AS 桶,
                count(DISTINCT vid) AS 人数
            FROM visitor_events
            WHERE created_at >= datetime('now','localtime',?) AND {VF}
              AND {EVENT} AND path = 'try.ok'
            GROUP BY 桶 ORDER BY 人数 DESC
        ''', since_args)
        if buckets:
            print('\n  -- 出结果的人里，检出多少条问题 --')
            total = sum(b['人数'] or 0 for b in buckets)
            for row in buckets:
                print(f'    {row["人数"]:>3} 人  占 {pct(row["人数"] or 0, total):>6}  {row["桶"]}')

        langs = q(conn, f'''
            SELECT json_extract(detail, '$.lang') AS lang, count(DISTINCT vid) AS 人数,
                   sum(CASE WHEN json_extract(detail, '$.auto') = 1 THEN 1 ELSE 0 END) AS 自动识别
            FROM visitor_events
            WHERE created_at >= datetime('now','localtime',?) AND {VF}
              AND {EVENT} AND path = 'try.ok'
            GROUP BY lang ORDER BY 人数 DESC LIMIT 8
        ''', since_args)
        if langs:
            print('\n  -- 试扫用了哪些语言 --')
            for row in langs:
                print(f'    {row["人数"]:>3} 人  {(row["lang"] or "?"):<10} 自动识别 {row["自动识别"]} 次')

    # ------------------------------------------------------------------
    # 注册漏斗（保持原有口径）
    # ------------------------------------------------------------------
    print('\n--- 注册漏斗（同一 vid 口径）---')
    funnel = q(conn, f'''
        SELECT
            count(DISTINCT vid)                                              AS 来了,
            count(DISTINCT CASE WHEN path = '/register' THEN vid END)        AS 看过注册页,
            count(DISTINCT CASE WHEN path = '/register' AND method='POST' THEN vid END) AS 提交注册,
            count(DISTINCT CASE WHEN user_id IS NOT NULL THEN vid END)       AS 有账号
        FROM visitor_events
        WHERE {where} AND {VF}
    ''', since_args)
    if funnel:
        came = funnel[0]['来了'] or 0
        saw = funnel[0]['看过注册页'] or 0
        sub = funnel[0]['提交注册'] or 0
        has = funnel[0]['有账号'] or 0
        print(f'  到达网站      {came:>4} 人')
        print(f'  打开注册页    {saw:>4} 人   占到达 {pct(saw, came)}')
        print(f'  提交注册      {sub:>4} 人   占打开 {pct(sub, saw)}')
        print(f'  已登录账号    {has:>4} 人   占到达 {pct(has, came)}')

    print('\n--- 注册页流失（打开过但没提交的 vid）---')
    lost = q(conn, f'''
        SELECT vid, min(created_at) AS 首次
        FROM visitor_events
        WHERE {where} AND {VF} AND path = '/register' AND method = 'GET'
          AND vid NOT IN (
              SELECT vid FROM visitor_events
              WHERE {where} AND method = 'POST' AND path = '/register'
          )
        GROUP BY vid ORDER BY 首次 DESC LIMIT 10
    ''', (since, since))
    if not lost:
        print('  无（要么没人打开注册页，要么打开的都提交了）')
    for row in lost:
        print(f'  {row["vid"][:12]}…  {row["首次"]}')

    print('\n--- 新访客 vs 回访（按 vid 首次出现）---')
    for row in q(conn, f'''
        SELECT first_day, count(*) AS 人数 FROM (
            SELECT vid, min(substr(created_at,1,10)) AS first_day
            FROM visitor_events WHERE {VF}{page_only} GROUP BY vid
        ) WHERE first_day >= date('now','localtime',?) GROUP BY first_day ORDER BY first_day
    ''', since_args):
        print(f'  {row["first_day"]}  新增 {row["人数"]} 人')

    conn.close()


if __name__ == '__main__':
    main()
