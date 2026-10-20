"""Xinpect - Database utilities"""
import sqlite3
from flask import g

from .constants import app, DB_PATH, logger


def get_db():
    """获取数据库连接，每个请求一个连接"""
    if 'db' not in g:
        db = sqlite3.connect(DB_PATH)
        g.db = db
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA journal_mode=WAL')
        g.db.execute('PRAGMA foreign_keys=ON')
    return g.db


@app.teardown_appcontext
def close_db(exception):
    """请求结束时关闭数据库连接"""
    db = g.pop('db', None)
    if db is not None:
        db.close()


def is_admin_user(user_id):
    """管理员判定的唯一入口。

    根因：此前 admin 权限被散写成三套互相矛盾的规则——`ADMIN_USER_IDS={6}`、
    `user_id != 6`、以及 `SELECT is_admin`（该列根本不存在，直接报 500）。
    结果：许可证管理必然 500、开票申请按 id==1 判断（真实 owner 是 6，永远看不到）。

    统一为数据库里的 is_admin 标记：身份跟着账号走，不再跟着自增 id 走，
    换号/重建库都不会把管理员身份"传给"另一个 user_id。
    """
    if not user_id:
        return False
    row = get_db().execute(
        'SELECT is_admin FROM users WHERE id = ?', (user_id,)
    ).fetchone()
    return bool(row and row[0])


def init_db():
    """初始化数据库表"""
    conn = sqlite3.connect(DB_PATH)
    try:
        _init_db_inner(conn)
    except Exception as _exc:
        conn.rollback()
        logger.error('Database initialization failed: %s', _exc)
        raise
    else:
        conn.commit()
    finally:
        conn.close()


def _init_db_inner(conn):
    """数据库初始化内部实现（入口）"""
    _create_core_tables(conn)
    _create_credit_tables(conn)
    _create_misc_tables(conn)
    _create_monitoring_tables(conn)
    _run_versioned_migrations(conn)
    _create_all_indexes(conn)
    conn.commit()


# ── 按表类型拆分 ──────────────────────────────────────────


def _create_core_tables(conn):
    """创建核心业务表：users, scans, orders, daily_usage"""
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_vip INTEGER DEFAULT 0,
            vip_expire_at TEXT,
            bonus_credits INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id TEXT UNIQUE NOT NULL,
            user_id INTEGER,
            title TEXT,
            file_count INTEGER DEFAULT 0,
            files_meta TEXT,
            results TEXT,
            score INTEGER DEFAULT 100,
            grade TEXT DEFAULT 'A',
            issue_count INTEGER DEFAULT 0,
            language TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT UNIQUE NOT NULL,
            user_id INTEGER NOT NULL,
            plan_id TEXT,
            plan_name TEXT,
            order_type TEXT DEFAULT 'subscription',
            amount REAL DEFAULT 0,
            status TEXT DEFAULT 'pending',
            pay_method TEXT,
            paid_at TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS daily_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            user_id INTEGER,
            ip TEXT,
            count INTEGER DEFAULT 0,
            UNIQUE(date, user_id, ip)
        );
    ''')


def _create_credit_tables(conn):
    """创建积分相关表：user_credits, credit_transactions, credit_pools"""
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS user_credits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            balance INTEGER DEFAULT 0,
            total_earned INTEGER DEFAULT 0,
            total_spent INTEGER DEFAULT 0,
            updated_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS credit_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            amount INTEGER NOT NULL,
            balance_after INTEGER NOT NULL,
            ref_type TEXT,
            ref_id TEXT,
            remark TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS credit_pools (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            pool_type TEXT NOT NULL CHECK(pool_type IN ('subscription', 'pack')),
            balance INTEGER NOT NULL DEFAULT 0,
            total_earned INTEGER NOT NULL DEFAULT 0,
            total_spent INTEGER NOT NULL DEFAULT 0,
            period_start TEXT,
            period_end TEXT,
            priority INTEGER NOT NULL DEFAULT 100,
            subscription_plan TEXT DEFAULT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );
    ''')


def _create_misc_tables(conn):
    """创建杂项表：reset_codes, announcements, user_announcement_read, referral_rewards, api_keys"""
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS reset_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            code TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS announcements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            type TEXT DEFAULT 'info',
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS user_announcement_read (
            user_id INTEGER NOT NULL,
            announcement_id INTEGER NOT NULL,
            read_at TEXT DEFAULT (datetime('now', 'localtime')),
            PRIMARY KEY (user_id, announcement_id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (announcement_id) REFERENCES announcements(id)
        );
        CREATE TABLE IF NOT EXISTS referral_rewards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_user_id INTEGER NOT NULL,
            referred_user_id INTEGER NOT NULL,
            order_id TEXT,
            reward_credits INTEGER DEFAULT 0,
            reward_type TEXT DEFAULT 'first_pay',
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (referrer_user_id) REFERENCES users(id),
            FOREIGN KEY (referred_user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            api_key TEXT UNIQUE NOT NULL,
            name TEXT DEFAULT 'default',
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    ''')


def _create_monitoring_tables(conn):
    """创建监控表：error_logs"""
    try:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS error_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                user_id INTEGER,
                endpoint TEXT NOT NULL,
                method TEXT NOT NULL,
                error_type TEXT NOT NULL,
                error_message TEXT,
                stack_trace TEXT,
                request_params TEXT,
                response_status INTEGER,
                ip_address TEXT,
                user_agent TEXT,
                resolved BOOLEAN DEFAULT 0,
                resolved_at DATETIME,
                resolution_notes TEXT
            )
        ''')
    except sqlite3.OperationalError:
        logger.debug('DB migration: error_logs table already exists')


def _run_versioned_migrations(conn):
    """结构化版本化迁移系统。每条迁移有唯一编号，执行后记录到 schema_migrations 表。"""
    conn.execute('''
        CREATE TABLE IF NOT EXISTS schema_migrations (
            migration_id TEXT PRIMARY KEY,
            description TEXT,
            applied_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    ''')

    applied = set()
    try:
        rows = conn.execute("SELECT migration_id FROM schema_migrations").fetchall()
        applied = {r[0] for r in rows}
    except Exception:
        pass

    # ── 迁移清单（按编号顺序执行，只跑未执行的） ──
    migrations = [
        ("001_add_bonus_credits",
         "users 增加 bonus_credits 字段",
         "ALTER TABLE users ADD COLUMN bonus_credits INTEGER DEFAULT 0"),
        ("002_add_order_type",
         "orders 增加 order_type 字段",
         "ALTER TABLE orders ADD COLUMN order_type TEXT DEFAULT 'subscription'"),
        ("003_add_mf_order_id",
         "orders 增加 mf_order_id 字段",
         "ALTER TABLE orders ADD COLUMN mf_order_id TEXT"),
        ("004_add_mf_password_hash",
         "users 增加 mf_password_hash 字段",
         "ALTER TABLE users ADD COLUMN mf_password_hash TEXT"),
        ("005_add_credits_spent",
         "scans 增加 credits_spent 字段",
         "ALTER TABLE scans ADD COLUMN credits_spent INTEGER DEFAULT 0"),
        ("006_add_total_lines",
         "scans 增加 total_lines 字段",
         "ALTER TABLE scans ADD COLUMN total_lines INTEGER DEFAULT 0"),
        ("007_add_scan_mode",
         "scans 增加 scan_mode 字段",
         "ALTER TABLE scans ADD COLUMN scan_mode TEXT DEFAULT 'basic'"),
        ("008_add_api_key_last_used",
         "api_keys 增加 last_used 字段",
         "ALTER TABLE api_keys ADD COLUMN last_used TEXT"),
        ("009_add_api_key_usage_count",
         "api_keys 增加 usage_count 字段",
         "ALTER TABLE api_keys ADD COLUMN usage_count INTEGER DEFAULT 0"),
        ("010_add_credit_tx_pool_id",
         "credit_transactions 增加 pool_id 字段",
         "ALTER TABLE credit_transactions ADD COLUMN pool_id TEXT DEFAULT NULL"),
        ("011_add_credit_tx_pool_type",
         "credit_transactions 增加 pool_type 字段",
         "ALTER TABLE credit_transactions ADD COLUMN pool_type TEXT DEFAULT NULL"),
        ("012_add_referral_code",
         "users 增加 referral_code 字段",
         "ALTER TABLE users ADD COLUMN referral_code TEXT"),
        ("013_add_referred_by",
         "users 增加 referred_by 字段",
         "ALTER TABLE users ADD COLUMN referred_by INTEGER"),
        ("014_add_referral_reward_type",
         "referral_rewards 增加 reward_type 字段",
         "ALTER TABLE referral_rewards ADD COLUMN reward_type TEXT DEFAULT 'first_pay'"),
        ("020_add_scan_status",
         "scans 增加 scan_status 字段（异步扫描状态）",
         "ALTER TABLE scans ADD COLUMN scan_status TEXT DEFAULT NULL"),
        ("021_add_scan_progress",
         "scans 增加 scan_progress 字段（异步扫描进度）",
         "ALTER TABLE scans ADD COLUMN scan_progress INTEGER DEFAULT 0"),
        ("022_add_scan_progress_text",
         "scans 增加 scan_progress_text 字段（进度描述）",
         "ALTER TABLE scans ADD COLUMN scan_progress_text TEXT DEFAULT NULL"),
        ("023_add_scan_error",
         "scans 增加 scan_error 字段（错误信息）",
         "ALTER TABLE scans ADD COLUMN scan_error TEXT DEFAULT NULL"),
        ("024_add_is_admin",
         "users 增加 is_admin 字段（管理员身份的单一事实来源）",
         "ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0"),
    ]

    for mid, desc, sql in migrations:
        if mid in applied:
            continue
        try:
            conn.execute(sql)
            logger.info("Migration applied: %s - %s", mid, desc)
        except sqlite3.OperationalError as e:
            logger.info("Migration %s: column already exists (%s)", mid, e)
        # 无论是否成功执行 ALTER TABLE，都标记为已处理（避免重复尝试）
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations (migration_id, description) VALUES (?, ?)",
            (mid, desc)
        )


def _run_column_migrations(conn):
    """执行列迁移（兼容旧逻辑，新迁移请加到 _run_versioned_migrations）"""
    pass  # 旧迁移已迁移到 _run_versioned_migrations


def _run_column_migrations_legacy(conn):
    """执行列迁移（兼容已有数据库补字段）"""
    _safe_migrations = [
        'ALTER TABLE users ADD COLUMN bonus_credits INTEGER DEFAULT 0',
        "ALTER TABLE orders ADD COLUMN order_type TEXT DEFAULT 'subscription'",
        "ALTER TABLE orders ADD COLUMN mf_order_id TEXT",
        "ALTER TABLE users ADD COLUMN mf_password_hash TEXT",
        "ALTER TABLE scans ADD COLUMN credits_spent INTEGER DEFAULT 0",
        "ALTER TABLE scans ADD COLUMN total_lines INTEGER DEFAULT 0",
        "ALTER TABLE scans ADD COLUMN scan_mode TEXT DEFAULT 'basic'",
        "ALTER TABLE api_keys ADD COLUMN last_used TEXT",
        "ALTER TABLE api_keys ADD COLUMN usage_count INTEGER DEFAULT 0",
    ]
    for _mig_sql in _safe_migrations:
        try:
            conn.execute(_mig_sql)
        except sqlite3.OperationalError:
            pass

    for _col_sql in [
        'ALTER TABLE credit_transactions ADD COLUMN pool_id TEXT DEFAULT NULL',
        'ALTER TABLE credit_transactions ADD COLUMN pool_type TEXT DEFAULT NULL',
    ]:
        try:
            conn.execute(_col_sql)
        except sqlite3.OperationalError:
            pass


def _run_referral_migrations(conn):
    """执行推荐系统列迁移"""
    _referral_migrations = [
        "ALTER TABLE users ADD COLUMN referral_code TEXT",
        "ALTER TABLE users ADD COLUMN referred_by INTEGER",
        "ALTER TABLE referral_rewards ADD COLUMN reward_type TEXT DEFAULT 'first_pay'",
    ]
    for _mig_sql in _referral_migrations:
        try:
            conn.execute(_mig_sql)
        except sqlite3.OperationalError:
            pass


def _create_all_indexes(conn):
    """创建所有索引"""
    _indexes = [
        'CREATE INDEX IF NOT EXISTS idx_scans_user ON scans(user_id)',
        'CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id)',
        'CREATE INDEX IF NOT EXISTS idx_scans_scan_id ON scans(scan_id)',
        'CREATE INDEX IF NOT EXISTS idx_reset_codes_email ON reset_codes(email)',
        'CREATE INDEX IF NOT EXISTS idx_announcements_active ON announcements(is_active)',
        'CREATE INDEX IF NOT EXISTS idx_announcements_created ON announcements(created_at DESC)',
        'CREATE UNIQUE INDEX IF NOT EXISTS idx_users_referral_code ON users(referral_code)',
        'CREATE INDEX IF NOT EXISTS idx_users_referred_by ON users(referred_by)',
        'CREATE INDEX IF NOT EXISTS idx_referral_rewards_referrer ON referral_rewards(referrer_user_id)',
        'CREATE INDEX IF NOT EXISTS idx_referral_rewards_referred ON referral_rewards(referred_user_id)',
        'CREATE INDEX IF NOT EXISTS idx_referral_rewards_type ON referral_rewards(reward_type)',
        'CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id)',
        'CREATE INDEX IF NOT EXISTS idx_api_keys_key ON api_keys(api_key)',
        'CREATE INDEX IF NOT EXISTS idx_user_credits_user ON user_credits(user_id)',
        'CREATE INDEX IF NOT EXISTS idx_credit_tx_user ON credit_transactions(user_id)',
        'CREATE INDEX IF NOT EXISTS idx_credit_tx_created ON credit_transactions(created_at)',
        'CREATE INDEX IF NOT EXISTS idx_error_timestamp ON error_logs(timestamp)',
        'CREATE INDEX IF NOT EXISTS idx_error_type ON error_logs(error_type)',
        'CREATE INDEX IF NOT EXISTS idx_error_resolved ON error_logs(resolved)',
        'CREATE INDEX IF NOT EXISTS idx_error_endpoint ON error_logs(endpoint)',
        'CREATE INDEX IF NOT EXISTS idx_cp_user ON credit_pools(user_id)',
        'CREATE INDEX IF NOT EXISTS idx_cp_user_active ON credit_pools(user_id, is_active)',
        'CREATE INDEX IF NOT EXISTS idx_cp_period ON credit_pools(period_end)',
    ]
    for _idx_sql in _indexes:
        try:
            conn.execute(_idx_sql)
        except sqlite3.OperationalError:
            pass
