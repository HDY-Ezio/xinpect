#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用户生命周期唯一入口：审计 / 清孤儿 / 删号。

为什么需要这个文件（2026-11-03 交接整改）

  这台机器历史上的「删号」全部是手工执行 DELETE FROM users WHERE id=?。
  users 一删，所有引用它的子表行立刻变成孤儿——实测 15 个已删账号留下
  79 行残渣（scans 9 / orders 19 / error_logs 22 / user_credits 12 /
  credit_transactions 4 / daily_usage 5 / scan_metrics 8），把数据一致性
  测试搞红。

  根因不是「有几条脏数据」，而是「删号没有唯一入口」。所以这里收敛两件事：
    delete_user(uid)   事务内先清全部引用行、再删 users —— 结构上不可能留孤儿
    purge_orphans()    清历史残渣，幂等，可反复执行

  引用表不手写清单：从 schema 自动发现「列名像用户引用」的表列
  （user_id / 任意 *_user_id / uid / owner_id）。全库现在有 28 处这样的列，
  老测试只盯 scans 和 orders 两张，其余 5 张表的孤儿一直没人管——手写必漏。
  新表只要按命名习惯加列就自动纳入，不需要回来改代码。

用法
  python3 scripts/user_lifecycle.py --audit
  python3 scripts/user_lifecycle.py --purge-orphans              # 干跑，只报告
  python3 scripts/user_lifecycle.py --purge-orphans --apply      # 真正删
  python3 scripts/user_lifecycle.py --delete-user 99 --apply     # 事务内连坐删除
"""

import argparse
import os
import re
import sqlite3
import sys

DB_PATH = os.environ.get("XINPECT_DB", "/opt/xinpect-website/xinpect.db")

# 用户引用列的命名约定。全库 28 处引用列都落在这个集合里；
# 用约定而不是枚举表名，才能保证新表自动纳入。
USER_REF_RE = re.compile(r"^(user_id|uid|owner_id|.+_user_id)$")


def connect(path=None):
    conn = sqlite3.connect(path or DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def tables(conn):
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def user_ref_columns(conn):
    """返回 [(table, column)]：所有语义上指向 users.id 的列。"""
    out = []
    for t in tables(conn):
        for row in conn.execute("PRAGMA table_info(%s)" % t):
            if USER_REF_RE.match(row[1]):
                out.append((t, row[1]))
    return out


def find_orphans(conn):
    """孤儿行分布 {(table, column): rows}。

    只把整数型值算作孤儿：某些表可能把 user_id 留成空串或 'system'
    这类标记值，直接 NOT IN 会误判成孤儿。
    """
    result = {}
    for t, col in user_ref_columns(conn):
        sql = ("SELECT COUNT(*) FROM %s WHERE %s IS NOT NULL "
               "AND typeof(%s)='integer' "
               "AND %s NOT IN (SELECT id FROM users)") % (t, col, col, col)
        n = conn.execute(sql).fetchone()[0]
        if n:
            result[(t, col)] = n
    return result


def find_dead_uids(conn):
    """所有引用列里出现、但 users 里已不存在的 user_id 集合。"""
    dead = set()
    for t, col in user_ref_columns(conn):
        sql = ("SELECT DISTINCT %s AS uid FROM %s WHERE %s IS NOT NULL "
               "AND typeof(%s)='integer' "
               "AND %s NOT IN (SELECT id FROM users)") % (col, t, col, col, col)
        dead.update(r[0] for r in conn.execute(sql))
    return sorted(dead)


def purge_orphans(conn, apply=False):
    """清理孤儿行。返回 [(table, column, rows)]，apply=False 时 rows 是待删数。

    单事务：要么全删成功，要么一行不动。幂等：重复执行第二次返回空列表。
    """
    plan = find_orphans(conn)
    if not apply:
        return [(t, c, n) for (t, c), n in sorted(plan.items())]
    deleted = []
    with conn:  # 自动 commit / 异常 rollback
        for (t, col), _n in sorted(plan.items()):
            cur = conn.execute(
                "DELETE FROM %s WHERE %s IS NOT NULL AND typeof(%s)='integer' "
                "AND %s NOT IN (SELECT id FROM users)" % (t, col, col, col))
            deleted.append((t, col, cur.rowcount))
    return deleted


def delete_user(conn, uid, apply=False):
    """删一个用户及其全部关联行，单事务。返回 (ok, detail)。

    团队 owner 直接拒绝：团队会因为没人拥有而变成孤儿团队，
    这种情况要先转移所有权——这不是能静默处理的事。
    """
    row = conn.execute("SELECT id, email FROM users WHERE id=?", (uid,)).fetchone()
    if not row:
        return False, {"error": "用户 %s 不存在" % uid}

    if "teams" in tables(conn):
        owned = [r[0] for r in conn.execute("SELECT id FROM teams WHERE owner_id=?", (uid,))]
        if owned:
            return False, {"error": "该用户是团队 %s 的所有者，请先转移或解散团队"
                                    % owned}

    breakdown = {}
    for t, col in user_ref_columns(conn):
        n = conn.execute("SELECT COUNT(*) FROM %s WHERE %s=?" % (t, col),
                         (uid,)).fetchone()[0]
        if n:
            breakdown["%s.%s" % (t, col)] = n

    detail = {"user_id": uid, "email": row["email"], "rows": breakdown,
              "total": sum(breakdown.values()), "applied": bool(apply)}
    if not apply:
        detail["dry_run"] = True
        return True, detail

    with conn:
        for key in sorted(breakdown):
            t, col = key.split(".", 1)
            conn.execute("DELETE FROM %s WHERE %s=?" % (t, col), (uid,))
        conn.execute("DELETE FROM users WHERE id=?", (uid,))
        left = find_orphans(conn)
        if left:
            # 结构保证：本次删除不允许留下任何孤儿，否则整笔回滚
            raise RuntimeError("删号后仍有孤儿残留，已回滚: %s" % left)
    return True, detail


def _print_plan(rows, empty_msg="没有孤儿行"):
    if not rows:
        print("  " + empty_msg)
        return 0
    for t, col, n in rows:
        print("  %-34s %6d" % ("%s.%s" % (t, col), n))
    return sum(n for _t, _c, n in rows)


def main():
    ap = argparse.ArgumentParser(
        description="用户生命周期唯一入口：审计 / 清孤儿 / 删号")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--audit", action="store_true", help="只报告孤儿分布")
    g.add_argument("--purge-orphans", action="store_true", help="清理孤儿行（默认干跑）")
    g.add_argument("--delete-user", type=int, metavar="UID",
                   help="删一个用户及其全部关联行（默认干跑）")
    ap.add_argument("--apply", action="store_true", help="真正写库；不加只报告")
    ap.add_argument("--db", default=DB_PATH, help="数据库路径")
    args = ap.parse_args()

    conn = connect(args.db)
    try:
        if args.audit:
            orph = find_orphans(conn)
            print("孤儿行分布（表.列 → 行数）")
            rows = [(t, c, n) for (t, c), n in sorted(orph.items())]
            total = _print_plan(rows)
            print("合计：%d 处 / %d 行" % (len(orph), total))
            dead = find_dead_uids(conn)
            print("已删账号（users 里不存在的 user_id）：%s"
                  % (", ".join(map(str, dead)) if dead else "无"))
            return 0 if not orph else 1

        if args.purge_orphans:
            rows = purge_orphans(conn, apply=args.apply)
            print("孤儿清理%s" % ("（已写库）" if args.apply else "（干跑，未写库）"))
            total = _print_plan(rows)
            print("合计：%d 处 / %d 行" % (len(rows), total))
            if not args.apply and total:
                print("确认无误后加 --apply 真正删除。")
            return 0

        ok, detail = delete_user(conn, args.delete_user, apply=args.apply)
        if not ok:
            print("拒绝执行：%s" % detail["error"])
            return 2
        print("删号%s：user_id=%s <%s>"
              % ("（已写库）" if detail["applied"] else "（干跑，未写库）",
                 detail["user_id"], detail["email"]))
        rows = [(k.split(".", 1)[0], k.split(".", 1)[1], v)
                for k, v in sorted(detail["rows"].items())]
        total = _print_plan(rows, "该用户没有任何关联行")
        print("合计：%d 处 / %d 行 + users 表 1 行" % (len(rows), total))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
