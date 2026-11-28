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


def _ensure_legacy_tables(conn):
    """把历史上「只存在于生产库、从没写进代码」的表补齐。

    2026-11-28：做开票端到端测试时发现全新库跑完启动仍缺 22 张表。
    这些表当年是手工 CREATE 进生产库的，代码里从来没有创建语句。
    后果不是理论问题 —— 换台机器重装，控制台 summary、CI 配置、许可、
    开票页全都 500。这里按生产库结构一次性补齐，全部 IF NOT EXISTS，幂等。
    """
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS admin_bind_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            code TEXT NOT NULL,
            device_fingerprint TEXT NOT NULL,
            device_name TEXT,
            expires_at TEXT NOT NULL,
            used INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS admin_devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            device_fingerprint TEXT NOT NULL,
            device_name TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            last_used_at TEXT,
            is_trusted INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS alert_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            scan_id TEXT NOT NULL,
            trigger_details TEXT DEFAULT '{}',
            delivery_status TEXT DEFAULT 'pending',
            delivery_response TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (rule_id) REFERENCES alert_rules(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS alert_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL DEFAULT '高危告警',
            channel TEXT NOT NULL DEFAULT 'webhook',
            channel_config TEXT NOT NULL DEFAULT '{}',
            trigger_json TEXT NOT NULL DEFAULT '{}',
            is_active INTEGER DEFAULT 1,
            last_triggered_at TEXT,
            cooldown_minutes INTEGER DEFAULT 60,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS api_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            endpoint VARCHAR(200) NOT NULL,
            method VARCHAR(10) DEFAULT 'GET',
            status_code INTEGER DEFAULT 200,
            called_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS auth_attempts ( id INTEGER PRIMARY KEY AUTOINCREMENT, scope TEXT NOT NULL, account TEXT NOT NULL, ip TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS benchmark_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_name TEXT NOT NULL,
                    total_samples INTEGER,
                    true_positives INTEGER,
                    false_positives INTEGER,
                    false_negatives INTEGER,
                    true_negatives INTEGER,
                    precision_score REAL,
                    recall_score REAL,
                    f1_score REAL,
                    false_positive_rate REAL,
                    by_severity TEXT,
                    by_language TEXT,
                    created_at TEXT DEFAULT (datetime('now', 'localtime'))
                );
        CREATE TABLE IF NOT EXISTS benchmark_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT NOT NULL,
                    language TEXT NOT NULL,
                    code_snippet TEXT NOT NULL,
                    issue_type TEXT NOT NULL,
                    severity TEXT NOT NULL DEFAULT 'P1',
                    cwe_id TEXT,
                    ground_truth TEXT NOT NULL DEFAULT 'pending',
                    annotated_by TEXT,
                    annotated_at TEXT,
                    notes TEXT,
                    source TEXT DEFAULT 'synthetic',
                    source_scan_id TEXT,
                    created_at TEXT DEFAULT (datetime('now', 'localtime'))
                );
        CREATE TABLE IF NOT EXISTS ci_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            default_scan_mode TEXT NOT NULL DEFAULT 'quick',
            default_threshold INTEGER NOT NULL DEFAULT 60,
            ignore_patterns TEXT DEFAULT NULL,
            auto_share INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')), block_mode TEXT DEFAULT "all_issues", block_severity TEXT DEFAULT "P0,P1",
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS cold_outreach (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            company TEXT,
            subject TEXT,
            sent_at TEXT DEFAULT (datetime('now','localtime')),
            ok INTEGER DEFAULT 0,
            UNIQUE(email, subject)
        );
        CREATE TABLE IF NOT EXISTS false_positives (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            scan_id TEXT NOT NULL,
            rule_id TEXT NOT NULL,
            file_path TEXT NOT NULL,
            line_number INTEGER DEFAULT 0,
            issue_title TEXT DEFAULT '',
            reason TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (scan_id) REFERENCES scans(scan_id)
        );
        CREATE TABLE IF NOT EXISTS gate_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            gate_id INTEGER,
            passed INTEGER NOT NULL DEFAULT 0,
            details_json TEXT DEFAULT '[]',
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (gate_id) REFERENCES quality_gates(id)
        );
        CREATE TABLE IF NOT EXISTS licenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    license_key TEXT UNIQUE NOT NULL,
                    org_name TEXT NOT NULL DEFAULT '',
                    plan_type TEXT NOT NULL DEFAULT 'pro',
                    max_users INTEGER NOT NULL DEFAULT 10,
                    max_scans INTEGER NOT NULL DEFAULT 1000,
                    expires_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'issued',
                    server_fingerprint TEXT DEFAULT '',
                    activated_at TEXT DEFAULT '',
                    contact_email TEXT DEFAULT '',
                    note TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now', 'localtime'))
                );
        CREATE TABLE IF NOT EXISTS membership_reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            tier INTEGER NOT NULL,
            expire_at TEXT NOT NULL,
            sent_at TEXT DEFAULT (datetime('now', 'localtime')),
            email TEXT,
            UNIQUE (user_id, tier, expire_at)
        );
        CREATE TABLE IF NOT EXISTS onboarding_recalls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            stage INTEGER NOT NULL,
            email TEXT,
            sent_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(user_id, stage)
        );
        CREATE TABLE IF NOT EXISTS payment_audit_dispositions (
            order_id    TEXT PRIMARY KEY,
            side        TEXT NOT NULL,
            reason      TEXT NOT NULL,
            decided_by  TEXT NOT NULL,
            decided_at  TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS quality_gates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL DEFAULT 'default',
            rules_json TEXT NOT NULL DEFAULT '{}',
            is_active INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            updated_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS rate_limit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            endpoint VARCHAR(200) NOT NULL,
            reason TEXT,
            limited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS repo_webhooks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        repo_full_name TEXT NOT NULL,
                        github_webhook_id INTEGER,
                        secret TEXT NOT NULL,
                        events TEXT NOT NULL DEFAULT 'push,pull_request',
                        active INTEGER NOT NULL DEFAULT 1,
                        auto_scan INTEGER NOT NULL DEFAULT 1,
                        auto_pr_comment INTEGER NOT NULL DEFAULT 1,
                        last_scan_at TEXT,
                        scan_count INTEGER DEFAULT 0,
                        created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                        FOREIGN KEY (user_id) REFERENCES users(id)
                    );
        CREATE TABLE IF NOT EXISTS scan_thresholds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            config_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            updated_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS scans_score_prev (
                            scan_id TEXT PRIMARY KEY,
                            score INTEGER, grade TEXT,
                            saved_at TEXT DEFAULT (datetime('now','localtime'))
                          );
        CREATE TABLE IF NOT EXISTS visitor_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vid TEXT NOT NULL,
            user_id INTEGER,
            path TEXT NOT NULL,
            method TEXT,
            status INTEGER,
            referer TEXT,
            ua TEXT,
            ip TEXT,
            is_bot INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        , kind TEXT NOT NULL DEFAULT 'page', detail TEXT, is_internal INTEGER NOT NULL DEFAULT 0);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_scans_share_token ON scans(share_token);
        CREATE INDEX IF NOT EXISTS idx_scans_user_hash ON scans(user_id, content_hash, created_at);
        CREATE INDEX IF NOT EXISTS idx_users_onboarding ON users(onboarding_completed);
        CREATE INDEX IF NOT EXISTS idx_admin_bind_codes_user ON admin_bind_codes(user_id);
        CREATE INDEX IF NOT EXISTS idx_admin_devices_user ON admin_devices(user_id);
        CREATE INDEX IF NOT EXISTS idx_admin_devices_fp ON admin_devices(device_fingerprint);
        CREATE INDEX IF NOT EXISTS idx_alert_history_user ON alert_history(user_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_alert_rules_user ON alert_rules(user_id);
        CREATE INDEX IF NOT EXISTS idx_api_calls_user ON api_calls(user_id);
        CREATE INDEX IF NOT EXISTS idx_api_calls_time ON api_calls(called_at);
        CREATE INDEX IF NOT EXISTS idx_api_calls_user_time ON api_calls(user_id, called_at);
        CREATE INDEX IF NOT EXISTS idx_auth_attempts_lookup ON auth_attempts (scope, account, ip, created_at);
        CREATE INDEX IF NOT EXISTS idx_bench_truth ON benchmark_samples(ground_truth);
        CREATE INDEX IF NOT EXISTS idx_bench_severity ON benchmark_samples(severity);
        CREATE INDEX IF NOT EXISTS idx_fp_user ON false_positives(user_id);
        CREATE INDEX IF NOT EXISTS idx_fp_user_rule_file ON false_positives(user_id, rule_id, file_path);
        CREATE INDEX IF NOT EXISTS idx_fp_scan ON false_positives(scan_id);
        CREATE INDEX IF NOT EXISTS idx_gate_results_user ON gate_results(user_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_gate_results_scan ON gate_results(scan_id);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_gates_user ON quality_gates(user_id);
        CREATE INDEX IF NOT EXISTS idx_rate_limit_user ON rate_limit_logs(user_id);
        CREATE INDEX IF NOT EXISTS idx_rate_limit_time ON rate_limit_logs(limited_at);
        CREATE INDEX IF NOT EXISTS idx_repo_webhooks_user ON repo_webhooks(user_id);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_repo_webhooks_repo ON repo_webhooks(repo_full_name);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_thresholds_user ON scan_thresholds(user_id);
        CREATE INDEX IF NOT EXISTS idx_visitor_created ON visitor_events(created_at);
        CREATE INDEX IF NOT EXISTS idx_visitor_vid ON visitor_events(vid);
        CREATE INDEX IF NOT EXISTS idx_visitor_path ON visitor_events(path);

    """)


def _init_db_inner(conn):
    """数据库初始化内部实现（入口）"""
    _create_core_tables(conn)
    _create_credit_tables(conn)
    _create_misc_tables(conn)
    _create_monitoring_tables(conn)
    _run_versioned_migrations(conn)
    _ensure_legacy_tables(conn)
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
        -- 扫描指标表：同样从没在代码里建过（生产手工建的）。
        -- /api/dashboard/summary 读它，缺表 → 控制台每页一个 500。
        CREATE TABLE IF NOT EXISTS scan_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            scan_id TEXT NOT NULL,
            score INTEGER NOT NULL,
            grade TEXT NOT NULL,
            issue_count INTEGER NOT NULL,
            critical_count INTEGER DEFAULT 0,
            high_count INTEGER DEFAULT 0,
            medium_count INTEGER DEFAULT 0,
            low_count INTEGER DEFAULT 0,
            brain_scores_json TEXT DEFAULT '{}',
            file_count INTEGER DEFAULT 0,
            total_lines INTEGER DEFAULT 0,
            duration_ms REAL DEFAULT 0,
            scan_mode TEXT DEFAULT 'basic',
            project_tag TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE INDEX IF NOT EXISTS idx_metrics_user ON scan_metrics(user_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_metrics_project ON scan_metrics(project_tag, created_at DESC);

        -- 开票申请表：原本只在代码里读写、靠手工建表，全新库缺这张表，
        -- 开票页对所有人 500（2026-11-28 做端到端测试时发现）。
        CREATE TABLE IF NOT EXISTS invoice_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            order_id TEXT NOT NULL,
            amount REAL NOT NULL,
            plan_name TEXT DEFAULT '',
            company_name TEXT NOT NULL,
            tax_number TEXT NOT NULL,
            email TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            admin_note TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            completed_at TEXT,
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
            is_legacy INTEGER NOT NULL DEFAULT 1,
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
        ("026_add_scan_total_bytes",
         "scans 增加 total_bytes 字段（代码字节量：ETA 估算的行数之外的第二维度）",
         "ALTER TABLE scans ADD COLUMN total_bytes INTEGER DEFAULT 0"),
        ("025_add_scan_is_replay",
         "scans 增加 is_replay 字段（复用结果落账标记：区分真实扫描与复用表演耗时）",
         "ALTER TABLE scans ADD COLUMN is_replay INTEGER DEFAULT 0"),
        ("027_add_scan_last_heartbeat",
         "scans 增加 last_heartbeat_at 字段（在途任务存活心跳：大文件分片扫描合法可达数十分钟，按心跳判活而非按提交时间）",
         "ALTER TABLE scans ADD COLUMN last_heartbeat_at TEXT DEFAULT NULL"),
        ("028_add_scan_progress_events",
         "scans 增加 scan_progress_events 字段（扫描器真实事件流水，供进度条显示实际在查什么）",
         "ALTER TABLE scans ADD COLUMN scan_progress_events TEXT DEFAULT NULL"),
        # 029~037：新库补列（2026-11-28）
        # 这 9 列历史上是手工 ALTER 加到生产的，从没进过迁移清单。结果是
        # 全新库只有 11 列，登录/控制台一读 onboarding_completed 就 500。
        # 生产一直没炸，只因为那台机器的库早就被手工补过 —— 换台机器重装就现原形。
        ("029_add_session_version",
         "users 增加 session_version 字段（改密后失效旧会话）",
         "ALTER TABLE users ADD COLUMN session_version INTEGER DEFAULT 1"),
        ("030_add_mf_sync_needed",
         "users 增加 mf_sync_needed 字段",
         "ALTER TABLE users ADD COLUMN mf_sync_needed INTEGER DEFAULT 0"),
        ("031_add_github_token",
         "users 增加 github_token 字段",
         "ALTER TABLE users ADD COLUMN github_token TEXT DEFAULT NULL"),
        ("032_add_github_username",
         "users 增加 github_username 字段",
         "ALTER TABLE users ADD COLUMN github_username TEXT DEFAULT NULL"),
        ("033_add_first_login_at",
         "users 增加 first_login_at 字段（首登引导判定）",
         "ALTER TABLE users ADD COLUMN first_login_at TEXT"),
        ("034_add_onboarding_completed",
         "users 增加 onboarding_completed 字段（控制台首登引导）",
         "ALTER TABLE users ADD COLUMN onboarding_completed INTEGER DEFAULT 0"),
        ("035_add_is_banned",
         "users 增加 is_banned 字段（封禁）",
         "ALTER TABLE users ADD COLUMN is_banned INTEGER NOT NULL DEFAULT 0"),
        ("036_add_gitlab_token",
         "users 增加 gitlab_token 字段",
         "ALTER TABLE users ADD COLUMN gitlab_token TEXT DEFAULT NULL"),
        ("037_add_gitlab_username",
         "users 增加 gitlab_username 字段",
         "ALTER TABLE users ADD COLUMN gitlab_username TEXT DEFAULT NULL"),
        ("038_add_scans_source",
         "scans 增加 source 字段（历史手工加过，补齐空库）",
         "ALTER TABLE scans ADD COLUMN source TEXT"),
        ("039_add_scans_ci_repo",
         "scans 增加 ci_repo 字段（历史手工加过，补齐空库）",
         "ALTER TABLE scans ADD COLUMN ci_repo TEXT"),
        ("040_add_scans_ci_branch",
         "scans 增加 ci_branch 字段（历史手工加过，补齐空库）",
         "ALTER TABLE scans ADD COLUMN ci_branch TEXT"),
        ("041_add_scans_ci_commit_sha",
         "scans 增加 ci_commit_sha 字段（历史手工加过，补齐空库）",
         "ALTER TABLE scans ADD COLUMN ci_commit_sha TEXT"),
        ("042_add_scans_share_token",
         "scans 增加 share_token 字段（历史手工加过，补齐空库）",
         "ALTER TABLE scans ADD COLUMN share_token TEXT"),
        ("043_add_scans_content_hash",
         "scans 增加 content_hash 字段（历史手工加过，补齐空库）",
         "ALTER TABLE scans ADD COLUMN content_hash TEXT"),
        ("044_add_scans_duration_seconds",
         "scans 增加 duration_seconds 字段（历史手工加过，补齐空库）",
         "ALTER TABLE scans ADD COLUMN duration_seconds REAL"),
        ("045_add_orders_hidden_at",
         "orders 增加 hidden_at 字段（用户删除过期订单：只隐藏不物理删）",
         "ALTER TABLE orders ADD COLUMN hidden_at TEXT DEFAULT NULL"),
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
        'CREATE INDEX IF NOT EXISTS idx_credit_tx_type_ref ON credit_transactions(type, ref_type, ref_id)',
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
