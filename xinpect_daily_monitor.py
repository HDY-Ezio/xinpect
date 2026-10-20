#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""煋鉴每日运营数据监控
统计维度：注册、扫描、充值、会员、积分消耗
已排除内部测试账号，数据更真实
"""
import logging
import sqlite3
import sys
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

DB_PATH = "/opt/xinpect-website/xinpect.db"
DEFAULT_HOURS = 24
PERCENTAGE_BASE = 100
MAX_LIST_DISPLAY = 10

# 排除的内部测试账号（不计入运营数据统计）
EXCLUDE_EMAILS = [
    "hdyabcd@163.com",
    "scan@test.com",
    "test_1786099373@example.com",
    "qa_1786099436@example.com",
    "qa_1786099455@example.com",
    "test_v131_1786102568@example.com",
    "test_v140_vxkfqz@test.com",
    "test_v140_lievum@test.com",
    "test_v140_ybkbdp@test.com",
    "free3s_cooodx@test.com",
    "test_credit_v15@test.com",
]


def _get_exclude_ids(cur):
    """获取排除账号的用户ID列表（参数化查询）"""
    if not EXCLUDE_EMAILS:
        return []
    placeholders = ",".join(["?"] * len(EXCLUDE_EMAILS))
    sql = "SELECT id FROM users WHERE email IN (" + placeholders + ")"
    cur.execute(sql, EXCLUDE_EMAILS)
    return [row[0] for row in cur.fetchall()]


def _build_where(field, exclude_ids):
    """构建安全 WHERE 子句（字段名白名单校验）"""
    allowed = {"id", "user_id"}
    if field not in allowed:
        raise ValueError("Invalid field name")
    if not exclude_ids:
        return "1=1", []
    placeholders = ",".join(["?"] * len(exclude_ids))
    return field + " NOT IN (" + placeholders + ")", list(exclude_ids)


def _exec_query(cur, base_sql, field, exclude_ids, extra_params=None):
    """安全执行带排除条件的查询"""
    where_result = _build_where(field, exclude_ids)
    condition = where_result[0]
    cond_params = where_result[1]
    sql = base_sql.replace("{WHERE}", condition)
    params = list(extra_params or []) + cond_params
    cur.execute(sql, params)
    return cur


def get_stats(hours=DEFAULT_HOURS):
    """统计最近 N 小时的数据"""
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        now = datetime.now()
        since = now - timedelta(hours=hours)
        since_str = since.strftime("%Y-%m-%d %H:%M:%S")

        exclude_ids = _get_exclude_ids(cur)
        stats = {}

        # === 用户统计 ===
        _exec_query(cur, "SELECT COUNT(*) FROM users WHERE {WHERE}", "id", exclude_ids)
        stats['total_users'] = cur.fetchone()[0]

        _exec_query(cur, "SELECT COUNT(*) FROM users WHERE created_at >= ? AND {WHERE}", "id", exclude_ids, [since_str])
        stats['new_users'] = cur.fetchone()[0]

        _exec_query(
            cur,
            "SELECT id, email, is_vip, created_at FROM users "
            "WHERE created_at >= ? AND {WHERE} ORDER BY created_at DESC",
            "id", exclude_ids, [since_str])
        stats['new_users_list'] = cur.fetchall()

        # === 会员统计 ===
        _exec_query(cur, "SELECT COUNT(*) FROM users WHERE is_vip = 1 AND {WHERE}", "id", exclude_ids)
        stats['total_vip'] = cur.fetchone()[0]

        _exec_query(cur, "SELECT COUNT(*) FROM users WHERE is_vip = 1 AND created_at >= ? AND {WHERE}", "id", exclude_ids, [since_str])
        stats['new_vip'] = cur.fetchone()[0]

        # === 扫描统计 ===
        _exec_query(cur, "SELECT COUNT(*) FROM scans WHERE {WHERE}", "user_id", exclude_ids)
        stats['total_scans'] = cur.fetchone()[0]

        _exec_query(cur, "SELECT COUNT(*) FROM scans WHERE created_at >= ? AND {WHERE}", "user_id", exclude_ids, [since_str])
        stats['new_scans'] = cur.fetchone()[0]

        _exec_query(
            cur,
            "SELECT scan_mode, COUNT(*), SUM(COALESCE(credits_spent, 0)) "
            "FROM scans WHERE created_at >= ? AND {WHERE} GROUP BY scan_mode",
            "user_id", exclude_ids, [since_str])
        stats['scan_mode_dist'] = cur.fetchall()

        _exec_query(
            cur,
            "SELECT SUM(file_count), SUM(COALESCE(total_lines, 0)) "
            "FROM scans WHERE created_at >= ? AND {WHERE}",
            "user_id", exclude_ids, [since_str])
        row = cur.fetchone()
        stats['total_files'] = row[0] or 0
        stats['total_lines'] = row[1] or 0

        _exec_query(
            cur,
            "SELECT SUM(COALESCE(credits_spent, 0)) "
            "FROM scans WHERE created_at >= ? AND {WHERE}",
            "user_id", exclude_ids, [since_str])
        stats['credits_spent'] = cur.fetchone()[0] or 0

        # === 充值/订单统计 ===
        _exec_query(cur, "SELECT COUNT(*) FROM orders WHERE status = 'paid' AND {WHERE}", "user_id", exclude_ids)
        stats['total_paid_orders'] = cur.fetchone()[0]

        _exec_query(
            cur,
            "SELECT COUNT(*) FROM orders "
            "WHERE status = 'paid' AND paid_at >= ? AND {WHERE}",
            "user_id", exclude_ids, [since_str])
        stats['new_paid_orders'] = cur.fetchone()[0]

        _exec_query(
            cur,
            "SELECT SUM(amount) FROM orders "
            "WHERE status = 'paid' AND paid_at >= ? AND {WHERE}",
            "user_id", exclude_ids, [since_str])
        stats['new_paid_amount'] = cur.fetchone()[0] or 0

        _exec_query(
            cur,
            "SELECT order_type, COUNT(*), SUM(amount) FROM orders "
            "WHERE status = 'paid' AND paid_at >= ? AND {WHERE} GROUP BY order_type",
            "user_id", exclude_ids, [since_str])
        stats['order_type_dist'] = cur.fetchall()

        # 订单明细
        _detail_base = (
            "SELECT o.order_id, u.email, o.plan_name, o.amount, o.order_type, o.paid_at "
            "FROM orders o LEFT JOIN users u ON o.user_id = u.id "
            "WHERE o.status = 'paid' AND o.paid_at >= ? "
        )
        if exclude_ids:
            placeholders = ",".join(["?"] * len(exclude_ids))
            detail_sql = _detail_base + "AND o.user_id NOT IN (" + placeholders + ") ORDER BY o.paid_at DESC"
            cur.execute(detail_sql, [since_str] + list(exclude_ids))
        else:
            detail_sql = _detail_base + "ORDER BY o.paid_at DESC"
            cur.execute(detail_sql, [since_str])
        stats['paid_orders_list'] = cur.fetchall()

        # pending: count ALL pending orders (no time filter, no test exclusion)
        # pending is an ops metric - need to see all unpaid orders
        cur.execute("SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM orders WHERE status = 'pending'")
        row = cur.fetchone()
        stats["pending_orders"] = row[0]
        stats["pending_amount"] = row[1]

        # === 积分流水 ===
        _exec_query(
            cur,
            "SELECT type, COUNT(*), SUM(amount) FROM credit_transactions "
            "WHERE created_at >= ? AND {WHERE} GROUP BY type",
            "user_id", exclude_ids, [since_str])
        stats['credit_tx_dist'] = cur.fetchall()

        # === 获客转化（组件契约引流） ===
        _exec_query(
            cur,
            "SELECT COUNT(*) FROM scans "
            "WHERE source = 'component_check' AND created_at >= ? AND {WHERE}",
            "user_id", exclude_ids, [since_str])
        stats['cc_new_scans'] = cur.fetchone()[0]

        _exec_query(
            cur,
            "SELECT COUNT(*) FROM scans WHERE source = 'component_check' AND {WHERE}",
            "user_id", exclude_ids)
        stats['cc_total_scans'] = cur.fetchone()[0]

        _exec_query(
            cur,
            "SELECT COUNT(DISTINCT user_id) FROM scans "
            "WHERE source = 'component_check' AND created_at >= ? "
            "AND user_id IS NOT NULL AND {WHERE}",
            "user_id", exclude_ids, [since_str])
        stats['cc_new_users'] = cur.fetchone()[0]

        _exec_query(
            cur,
            "SELECT COUNT(DISTINCT user_id) FROM scans "
            "WHERE source = 'component_check' AND user_id IS NOT NULL AND {WHERE}",
            "user_id", exclude_ids)
        stats['cc_total_users'] = cur.fetchone()[0]

        _exec_query(cur, ("SELECT COUNT(DISTINCT o.user_id), COUNT(*), COALESCE(SUM(o.amount), 0) "
                          "FROM orders o WHERE o.status = 'paid' AND o.paid_at >= ? "
                          "AND o.user_id IN (SELECT DISTINCT user_id FROM scans WHERE source = 'component_check' AND user_id IS NOT NULL) "
                          "AND {WHERE}"), "user_id", exclude_ids, [since_str])
        row = cur.fetchone()
        stats['cc_paid_users'] = row[0]
        stats['cc_paid_orders'] = row[1]
        stats['cc_paid_amount'] = row[2]

        _exec_query(cur, ("SELECT COUNT(*) FROM users u WHERE u.created_at >= ? AND {WHERE} "
                          "AND EXISTS (SELECT 1 FROM scans s WHERE s.user_id = u.id AND s.source = 'component_check' AND s.created_at >= u.created_at)"),
                     "id", exclude_ids, [since_str])
        stats['cc_registered_users'] = cur.fetchone()[0]

        return stats, since, now


def format_report(stats, since, now, label="近24小时"):
    # 类型映射表（提前定义，避免条件分支中的未定义变量风险）
    type_map = {'subscription': '会员订阅', 'credit_pack': '积分包', 'times_card': '次卡'}
    type_map_short = {'subscription': '订阅', 'credit_pack': '积分包', 'times_card': '次卡'}
    lines = []
    lines.append("## 煋鉴运营数据监控报告（{}）".format(label))
    lines.append("")
    lines.append("**检查时间**：{}".format(now.strftime('%Y-%m-%d %H:%M')))
    lines.append("**统计范围**：{} 之后".format(since.strftime('%Y-%m-%d %H:%M')))
    lines.append("> 已排除内部测试账号，数据为真实用户")
    lines.append("")

    # 用户
    lines.append("### 📊 用户数据")
    lines.append("")
    lines.append("| 指标 | 数值 |")
    lines.append("|------|------|")
    lines.append("| 累计注册用户 | {} |".format(stats['total_users']))
    lines.append("| 新增注册 | {} |".format(stats['new_users']))
    lines.append("| 累计会员 | {} |".format(stats['total_vip']))
    lines.append("| 新增会员 | {} |".format(stats['new_vip']))
    lines.append("")

    if stats['new_users_list']:
        lines.append("**新注册用户：**")
        lines.append("")
        lines.append("| ID | 邮箱 | 会员 | 注册时间 |")
        lines.append("|----|------|------|----------|")
        for uid, email, is_vip, created in stats['new_users_list'][:MAX_LIST_DISPLAY]:
            vip_str = "✅" if is_vip else "—"
            lines.append("| {} | {} | {} | {} |".format(uid, email, vip_str, created[:16]))
        lines.append("")

    # 扫描
    lines.append("### 🔍 扫描数据")
    lines.append("")
    lines.append("| 指标 | 数值 |")
    lines.append("|------|------|")
    lines.append("| 累计扫描次数 | {} |".format(stats['total_scans']))
    lines.append("| 新增扫描 | {} |".format(stats['new_scans']))
    lines.append("| 扫描文件数 | {} |".format(stats['total_files']))
    lines.append("| 代码行数 | {:,} |".format(stats['total_lines']))
    lines.append("| 积分消耗 | {:,} |".format(stats['credits_spent']))
    lines.append("")

    if stats['scan_mode_dist']:
        lines.append("**扫描模式分布：**")
        lines.append("")
        mode_map = {'full': '全量(会员)', 'basic': '基础(免费)', 'vip': 'VIP'}
        for mode, cnt, credits in stats['scan_mode_dist']:
            mode_name = mode_map.get(mode, mode)
            lines.append("- {}: {} 次，消耗 {} 积分".format(mode_name, cnt, credits))
        lines.append("")

    # 充值
    lines.append("### 💰 充值数据")
    lines.append("")
    lines.append("| 指标 | 数值 |")
    lines.append("|------|------|")
    lines.append("| 累计支付订单 | {} |".format(stats['total_paid_orders']))
    lines.append("| 新增支付订单 | {} |".format(stats['new_paid_orders']))
    lines.append("| 新增支付金额 | ¥{:,.2f} |".format(stats['new_paid_amount']))
    lines.append("| 待支付订单 | {} 笔 / ¥{:,.2f} |".format(stats['pending_orders'], stats.get('pending_amount', 0)))
    lines.append("")

    if stats['order_type_dist']:
        lines.append("**订单类型分布：**")
        lines.append("")
        for otype, cnt, amount in stats['order_type_dist']:
            type_name = type_map.get(otype, otype)
            lines.append("- {}: {} 单，¥{:,.2f}".format(type_name, cnt, amount or 0))
        lines.append("")

    if stats['paid_orders_list']:
        lines.append("**支付订单明细：**")
        lines.append("")
        lines.append("| 订单号 | 用户 | 套餐 | 金额 | 类型 | 支付时间 |")
        lines.append("|--------|------|------|------|------|----------|")
        for oid, email, plan, amount, otype, paid in stats['paid_orders_list'][:MAX_LIST_DISPLAY]:
            type_name = type_map_short.get(otype, otype or '?')
            lines.append("| {} | {} | {} | ¥{} | {} | {} |".format(oid[:12], email, plan, amount, type_name, paid[:16]))
        lines.append("")

    # 积分流水
    if stats['credit_tx_dist']:
        lines.append("### 💳 积分流水")
        lines.append("")
        type_map = {
            'scan_consume': '扫描消耗',
            'recharge': '充值获得',
            'vip_bonus': '会员赠送',
            'refund': '退款',
            'adjust': '调整',
        }
        for ttype, cnt, amount in stats['credit_tx_dist']:
            tname = type_map.get(ttype, ttype)
            lines.append("- {}: {} 笔，{} 积分".format(tname, cnt, amount if amount else 0))
        lines.append("")

    # 获客转化
    lines.append("### 🎯 获客转化 · 组件契约引流")
    lines.append("")
    lines.append("| 指标 | 数值 |")
    lines.append("|------|------|")
    lines.append("| 累计组件契约检测 | {} 次 |".format(stats['cc_total_scans']))
    lines.append("| 新增组件契约检测 | {} 次 |".format(stats['cc_new_scans']))
    lines.append("| 累计使用用户 | {} 人 |".format(stats['cc_total_users']))
    lines.append("| 新增使用用户 | {} 人 |".format(stats['cc_new_users']))
    lines.append("| 组件契约来源注册 | {} 人 |".format(stats['cc_registered_users']))
    lines.append("| 组件契约付费转化 | {} 人 / ¥{:,.2f} |".format(stats['cc_paid_users'], stats['cc_paid_amount']))
    lines.append("")

    funnel = []
    if stats['cc_new_scans'] > 0:
        funnel.append("检测→注册: {:.1f}%".format(stats['cc_registered_users']/stats['cc_new_scans']*PERCENTAGE_BASE))
    if stats['cc_registered_users'] > 0:
        funnel.append("注册→付费: {:.1f}%".format(stats['cc_paid_users']/max(stats['cc_registered_users'],1)*100))
    if funnel:
        lines.append("**漏斗转化**：{}".format(" → ".join(funnel)))
        lines.append("")

    lines.append("---")
    if stats['new_paid_orders'] > 0:
        lines.append("**⚠️ 有新订单！** 新增 {} 笔支付，金额 ¥{:,.2f}".format(stats['new_paid_orders'], stats['new_paid_amount']))
    elif stats['new_users'] > 0:
        lines.append("📈 新增 {} 位注册用户，暂无付费转化".format(stats['new_users']))
    else:
        lines.append("✅ 无新用户和新订单，正常运行")

    return "\n".join(lines)


if __name__ == "__main__":
    hours = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    label = sys.argv[2] if len(sys.argv) > 2 else "近{}小时".format(hours)
    stats, since, now = get_stats(hours)
    print(format_report(stats, since, now, label))
