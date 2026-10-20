#!/usr/bin/env python3
"""数据迁移脚本：将现有用户的 balance 迁移到积分池 (SQLite)"""
import sys
import os
import sqlite3
import uuid
from datetime import datetime, timedelta

# 查找数据库
BASE_DIR = '/opt/xinpect-website'
db_path = os.path.join(BASE_DIR, 'xinpect.db')

if not os.path.exists(db_path):
    print(f"ERROR: 数据库不存在 {db_path}")
    sys.exit(1)

print(f"数据库路径: {db_path}")

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# 检查 credit_pools 表是否存在
try:
    cursor.execute("SELECT COUNT(*) FROM credit_pools")
    print(f"credit_pools 表已存在, 当前记录数: {cursor.fetchone()[0]}")
except sqlite3.OperationalError:
    print("ERROR: credit_pools 表不存在，请先重启服务让 init_db 创建表")
    sys.exit(1)

# 查找所有有余额的用户
cursor.execute("""
    SELECT uc.user_id, uc.balance, u.is_vip, u.vip_expire_at, u.email
    FROM user_credits uc
    JOIN users u ON uc.user_id = u.id
    WHERE uc.balance > 0
""")
users = cursor.fetchall()

print(f"\n找到 {len(users)} 个有余额的用户")

migrated = 0
skipped = 0

for user in users:
    uid = user['user_id']
    balance = user['balance']
    is_vip = user['is_vip']
    vip_expire = user['vip_expire_at']
    email = user['email']

    # 检查是否已迁移
    cursor.execute("SELECT COUNT(*) as cnt FROM credit_pools WHERE user_id = ?", (uid,))
    cnt = cursor.fetchone()['cnt']
    if cnt > 0:
        print(f"  跳过 user_id={uid} ({email}) - 已有 {cnt} 个积分池")
        skipped += 1
        continue

    now = datetime.now()
    now_str = now.strftime('%Y-%m-%d %H:%M:%S')

    if is_vip and vip_expire:
        # 有活跃会员 → 创建 subscription 池
        pool_id = str(uuid.uuid4())

        # 计算刷新时间（vip_expire 就是 period_end）
        try:
            expire_dt = datetime.strptime(vip_expire[:19], '%Y-%m-%d %H:%M:%S')
        except (ValueError, TypeError):
            expire_dt = now + timedelta(days=30)

        # 如果已过期，用当前时间+30天
        if expire_dt < now:
            expire_dt = now + timedelta(days=30)

        period_end_str = expire_dt.strftime('%Y-%m-%d %H:%M:%S')

        # 推断 plan_key（简单按 days 推断）
        days_diff = (expire_dt - now).days
        if days_diff <= 35:
            plan_key = 'monthly'
        elif days_diff <= 95:
            plan_key = 'quarterly'
        elif days_diff <= 185:
            plan_key = 'half_year'
        else:
            plan_key = 'yearly'

        cursor.execute("""
            INSERT INTO credit_pools
            (id, user_id, pool_type, balance, total_earned, period_start, period_end,
             priority, subscription_plan, is_active)
            VALUES (?, ?, 'subscription', ?, ?, ?, ?, 1, ?, 1)
        """, (pool_id, uid, balance, balance, now_str, period_end_str, plan_key))

        print(f"  迁移 user_id={uid} ({email}): {balance}积分 → subscription池 (plan={plan_key}, refresh={period_end_str})")
    else:
        # 无会员 → 创建 pack 池（有效期1年）
        pool_id = str(uuid.uuid4())
        period_end_str = (now + timedelta(days=365)).strftime('%Y-%m-%d %H:%M:%S')

        cursor.execute("""
            INSERT INTO credit_pools
            (id, user_id, pool_type, balance, total_earned, period_start, period_end,
             priority, subscription_plan, is_active)
            VALUES (?, ?, 'pack', ?, ?, ?, ?, 100, NULL, 1)
        """, (pool_id, uid, balance, balance, now_str, period_end_str))

        print(f"  迁移 user_id={uid} ({email}): {balance}积分 → pack池 (有效期1年)")

    migrated += 1

conn.commit()

# 验证
cursor.execute("SELECT COUNT(*) FROM credit_pools")
total_pools = cursor.fetchone()[0]
cursor.execute("SELECT COALESCE(SUM(balance), 0) as total FROM credit_pools")
total_balance = cursor.fetchone()[0]

cursor.close()
conn.close()

print(f"\n=== 迁移完成 ===")
print(f"  已迁移: {migrated} 个用户")
print(f"  已跳过: {skipped} 个用户")
print(f"  积分池总数: {total_pools}")
print(f"  积分池总余额: {total_balance}")
