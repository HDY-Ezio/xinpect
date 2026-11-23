# -*- coding: utf-8 -*-
"""
煋鉴 - 团队版企业级能力（P1-P6）
================================

本模块承载团队版「个人账号给不了的价值」，严格复用个人扫描成熟链路，不重造引擎：

  P1 统一治理看板   —— 全队漏洞数量/严重度分布/修复进度/成员活跃度聚合
  P2 审计留痕       —— 谁在什么时候扫描/邀请/改角色/删成员，可追溯、不可抵赖
  P3 报告归属       —— 成员被踢后其扫描结果仍归属团队（见 team.py 的 remove 保护）
  P4 统一质量门禁   —— 团队定规则/阈值，全员强制，不达标标注 fail
  P5 标准对照报告       —— 扫描结果套 OWASP Top10 / CWE 模板，给审计看
  P6 团队版购买闭环 —— 团队版套餐 + 共享积分池（团队扫描从共享池扣费，不再扣个人）

架构原则（铁律）：
  1. 所有团队版能力只读写「团队维度」的数据，个人扫描零侵入；
  2. 表结构用幂等初始化（CREATE TABLE IF NOT EXISTS + PRAGMA 查列补列），
     不依赖启动时序，首次访问即自愈；
  3. 共享积分池复用 scoring.consume_credits 的原子扣费语义，只改「扣谁」，
     不改「怎么扣」，杜绝超扣/漏扣。
"""
import os
import json
import sqlite3
from datetime import datetime, timedelta

from flask import request, session, jsonify, render_template, redirect, url_for, flash

from .constants import app, logger, DB_PATH
from .db import get_db
from .helpers import login_required, get_current_user
from .dashboard_context import dashboard_context


# ══════════════════════════════════════════════════════════
#  常量
# ══════════════════════════════════════════════════════════

TEAM_ROLE_OWNER = 'owner'
TEAM_ROLE_ADMIN = 'admin'
TEAM_ROLE_MEMBER = 'member'

# 团队版套餐（P6）：纯积分制 + 最低门槛，单价上浮（个人 ¥0.33/积分 → 团队 ¥0.50/积分）
TEAM_PLANS = {
    'team_basic': {
        'name': '团队版·基础',
        'amount': 1499,          # ¥1499/月
        'credits': 3000,         # 3000 共享积分
        'member_limit': 10,      # 席位上界（团队多大对成本无差，纯治理价值）
        'mf_plan': 'team-basic', # 门房套餐标识
    },
    'team_pro': {
        'name': '团队版·专业',
        'amount': 4999,
        'credits': 12000,
        'member_limit': 50,
        'mf_plan': 'team-pro',
    },
}

# 团队共享积分池的 pool_type 取值（与个人 credit_pools 的 subscription/pack 区分）
TEAM_POOL_TYPE = 'team'

# 审计操作类型（P2）
AUDIT_ACTIONS = {
    'team_created':       '创建团队',
    'team_updated':       '修改团队',
    'team_deleted':       '删除团队',
    'member_invited':     '邀请成员',
    'member_joined':      '成员加入',
    'member_removed':     '移除成员',
    'role_changed':       '变更角色',
    'ownership_transfer': '转让所有权',
    'scan_submitted':     '提交扫描',
    'gate_updated':       '更新质量门禁',
    'plan_purchased':     '购买团队版',
}


# ══════════════════════════════════════════════════════════
#  幂等表初始化（首次访问自愈，不依赖启动时序）
# ══════════════════════════════════════════════════════════

def init_governance_tables():
    """创建团队版企业级能力所需表（幂等）。"""
    try:
        _changed = False
        conn = sqlite3.connect(DB_PATH)
        conn.executescript("""
            -- P2 审计留痕
            CREATE TABLE IF NOT EXISTS team_audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id INTEGER NOT NULL,
                actor_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                target_type TEXT DEFAULT '',
                target_id TEXT DEFAULT '',
                detail TEXT DEFAULT '',
                ip_address TEXT,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            );
            CREATE INDEX IF NOT EXISTS idx_team_audit_team ON team_audit_logs(team_id);
            CREATE INDEX IF NOT EXISTS idx_team_audit_created ON team_audit_logs(created_at);

            -- P4 统一质量门禁（每团队一条门禁配置）
            CREATE TABLE IF NOT EXISTS team_gates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id INTEGER NOT NULL UNIQUE,
                min_score INTEGER NOT NULL DEFAULT 80,      -- 最低综合分（不达标 fail）
                max_critical INTEGER NOT NULL DEFAULT 0,    -- 严重漏洞上限
                max_high INTEGER NOT NULL DEFAULT 0,        -- 高危漏洞上限
                scan_mode TEXT NOT NULL DEFAULT 'quick',    -- 团队允许子账号使用的扫描档位：quick/smart/deep（无免费档）
                enabled INTEGER NOT NULL DEFAULT 1,         -- 门禁开关
                updated_by INTEGER,
                updated_at TEXT DEFAULT (datetime('now', 'localtime'))
            );
            CREATE INDEX IF NOT EXISTS idx_team_gates_team ON team_gates(team_id);

            -- P6 团队版订阅（谁买了团队版、何时到期）
            CREATE TABLE IF NOT EXISTS team_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id INTEGER NOT NULL UNIQUE,
                plan_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',      -- active / expired / cancelled
                member_limit INTEGER NOT NULL DEFAULT 10,
                period_start TEXT,
                period_end TEXT,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            );

            -- P6 团队共享积分池
            CREATE TABLE IF NOT EXISTS team_credit_pools (
                id TEXT PRIMARY KEY,
                team_id INTEGER NOT NULL,
                balance INTEGER NOT NULL DEFAULT 0,
                total_earned INTEGER NOT NULL DEFAULT 0,
                total_spent INTEGER NOT NULL DEFAULT 0,
                period_start TEXT,
                period_end TEXT,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                updated_at TEXT DEFAULT (datetime('now', 'localtime'))
            );
            CREATE INDEX IF NOT EXISTS idx_team_cp_team ON team_credit_pools(team_id);
        """)
        # orders 表加 team_id 列（P6 团队版订单关联），幂等补列
        _cols = [r[1] for r in conn.execute('PRAGMA table_info(orders)').fetchall()]
        if 'team_id' not in _cols:
            conn.execute('ALTER TABLE orders ADD COLUMN team_id INTEGER')
            _changed = True
        # orders 表加 team_name 列（购买团队版时记住待建团队名，付费后自动建团用），幂等补列
        if 'team_name' not in _cols:
            conn.execute('ALTER TABLE orders ADD COLUMN team_name TEXT')
            _changed = True
        # team_gates 表补 scan_mode 列（团队档位配置），幂等补列
        _gcols = [r[1] for r in conn.execute('PRAGMA table_info(team_gates)').fetchall()]
        if 'scan_mode' not in _gcols:
            conn.execute("ALTER TABLE team_gates ADD COLUMN scan_mode TEXT NOT NULL DEFAULT 'quick'")
            _changed = True
        conn.commit()
        conn.close()
        if _changed:
            logger.info('[团队治理] 企业级能力表初始化完成（含结构变更）')
    except Exception as e:
        logger.error(f'[团队治理] 表初始化失败: {e}')


# ══════════════════════════════════════════════════════════
#  审计留痕（P2）—— 单一写入口
# ══════════════════════════════════════════════════════════

def audit_log(team_id, actor_id, action, target_type='', target_id='', detail=''):
    """写审计日志。所有团队写操作必须经过此函数，保证留痕不可抵赖。"""
    try:
        init_governance_tables()
        db = get_db()
        db.execute("""
            INSERT INTO team_audit_logs
                (team_id, actor_id, action, target_type, target_id, detail, ip_address)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (team_id, actor_id, action, target_type, str(target_id), detail,
              request.remote_addr if request else None))
        db.commit()
    except Exception as e:
        # 审计失败不阻断主流程，但必须告警（留痕是团队版核心价值，不能静默丢失）
        logger.error(f'[审计] 写入失败 team_id={team_id} action={action}: {e}')


# ══════════════════════════════════════════════════════════
#  内部工具（团队权限校验，复用 team.py 语义但避免循环 import）
# ══════════════════════════════════════════════════════════

def _team_role(team_id, user_id, db):
    """查用户在团队中的角色，非成员返回 None。"""
    row = db.execute(
        'SELECT role FROM team_members WHERE team_id = ? AND user_id = ?',
        (team_id, user_id)
    ).fetchone()
    return row['role'] if row else None


def _is_team_admin(team_id, user_id, db):
    role = _team_role(team_id, user_id, db)
    return role in (TEAM_ROLE_OWNER, TEAM_ROLE_ADMIN)


def _is_team_owner(team_id, user_id, db):
    return _team_role(team_id, user_id, db) == TEAM_ROLE_OWNER


def _get_team_or_none(team_id, db):
    return db.execute('SELECT * FROM teams WHERE id = ?', (team_id,)).fetchone()


# ══════════════════════════════════════════════════════════
#  P1 统一治理看板 —— 聚合接口
# ══════════════════════════════════════════════════════════

def _team_dashboard_data(team_id, db):
    """聚合团队治理看板所需全部数据。

    全队维度：
      - 扫描总次数 / 最近 30 天次数
      - 漏洞总数 + 按严重度分布（critical/high/medium/low）
      - 平均评分 / 最低评分（风险最高的项目）
      - 成员活跃度（每人扫描次数，谁最久没扫）
      - 修复进度（remediated 标记的问题数 / 总数）
    """
    # 成员总数
    member_count = db.execute(
        'SELECT COUNT(*) c FROM team_members WHERE team_id = ?', (team_id,)
    ).fetchone()['c']

    # 扫描统计
    scan_stats = db.execute("""
        SELECT
            COUNT(*) as total_scans,
            SUM(CASE WHEN created_at >= datetime('now', 'localtime', '-30 day') THEN 1 ELSE 0 END) as scans_30d,
            AVG(score) as avg_score,
            MIN(score) as min_score,
            SUM(issue_count) as total_issues
        FROM scans
        WHERE team_id = ?
    """, (team_id,)).fetchone()

    # 严重度分布：从每份扫描的 results JSON 里聚合 issue 的 severity
    # （scans.results 存的是 {issues:[...], style_issues:[...]}）
    severity_dist = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0, 'info': 0}
    _sev_map = {
        'critical': 'critical', 'blocker': 'critical',
        'high': 'high', 'suspicious': 'high',
        'medium': 'medium', 'correctness': 'medium', 'restriction': 'medium',
        'low': 'low', 'style': 'low',
    }
    result_rows = db.execute(
        'SELECT results FROM scans WHERE team_id = ? AND results IS NOT NULL AND results != ""',
        (team_id,)
    ).fetchall()
    for r in result_rows:
        try:
            data = json.loads(r['results'])
            for iss in data.get('issues', []):
                sev = _sev_map.get(iss.get('severity', ''), 'info')
                severity_dist[sev] = severity_dist.get(sev, 0) + 1
        except (json.JSONDecodeError, TypeError):
            continue

    # 成员活跃度：每人扫描次数
    member_activity = db.execute("""
        SELECT u.id, u.email,
               COUNT(s.id) as scan_count,
               MAX(s.created_at) as last_scan_at
        FROM team_members tm
        JOIN users u ON u.id = tm.user_id
        LEFT JOIN scans s ON s.team_id = tm.team_id AND s.user_id = tm.user_id
        WHERE tm.team_id = ?
        GROUP BY u.id, u.email
        ORDER BY scan_count DESC, last_scan_at DESC
    """, (team_id,)).fetchall()

    # 修复进度：false_positives 表里标记的误报 + fix_progress（若有）
    # 简化口径：remediated 数 = 修复记录表里的条数
    fixed_count = 0
    try:
        row = db.execute("""
            SELECT COUNT(*) c FROM fix_progress fp
            JOIN scans s ON s.id = fp.scan_id
            WHERE s.team_id = ?
        """, (team_id,)).fetchone()
        fixed_count = row['c'] if row else 0
    except Exception:
        pass  # fix_progress 表可能不存在

    return {
        'member_count': member_count,
        'total_scans': scan_stats['total_scans'] or 0,
        'scans_30d': scan_stats['scans_30d'] or 0,
        'avg_score': round(scan_stats['avg_score'], 1) if scan_stats['avg_score'] is not None else None,
        'min_score': scan_stats['min_score'],
        'total_issues': scan_stats['total_issues'] or 0,
        'severity_dist': severity_dist,
        'member_activity': [dict(m) for m in member_activity],
        'fixed_count': fixed_count,
    }


@app.route('/api/teams/<int:team_id>/dashboard', methods=['GET'])
@login_required
def api_team_dashboard(team_id):
    """P1 统一治理看板数据接口。"""
    user = get_current_user()
    db = get_db()
    if not _team_role(team_id, user['id'], db):
        return jsonify({'code': -1, 'msg': '无权访问'}), 401
    return jsonify({'code': 0, 'data': _team_dashboard_data(team_id, db)})


@app.route('/dashboard/team/<int:team_id>/governance')
@login_required
def team_governance_page(team_id):
    """P1 治理看板页面（含看板 + 门禁 + 标准对照报告 + 审计日志的 Tab）。"""
    user = get_current_user()
    db = get_db()
    role = _team_role(team_id, user['id'], db)
    if not role:
        flash('无权访问该团队', 'error')
        return redirect(url_for('team_dashboard'))

    team = _get_team_or_none(team_id, db)
    dashboard = _team_dashboard_data(team_id, db)

    # 门禁配置（无则返回默认值）
    gate = db.execute('SELECT * FROM team_gates WHERE team_id = ?', (team_id,)).fetchone()
    gate = dict(gate) if gate else {
        'min_score': 80, 'max_critical': 0, 'max_high': 0, 'enabled': 1
    }

    # 审计日志（最近 50 条）
    audit_rows = db.execute("""
        SELECT al.*, u.email as actor_email
        FROM team_audit_logs al
        LEFT JOIN users u ON u.id = al.actor_id
        WHERE al.team_id = ?
        ORDER BY al.id DESC LIMIT 50
    """, (team_id,)).fetchall()

    # 团队版订阅状态（P6）
    sub = db.execute('SELECT * FROM team_subscriptions WHERE team_id = ?', (team_id,)).fetchone()

    # 治理页同样挂后台母版：侧栏高亮「团队协作」，身份切换/未读公告一处不漏。
    ctx = dashboard_context(user)
    ctx.update({
        'user': user,
        'page': 'team',
        'team': dict(team),
        'my_role': role,
        'is_admin': role in (TEAM_ROLE_OWNER, TEAM_ROLE_ADMIN),
        'dashboard': dashboard,
        'gate': gate,
        'audit_logs': [dict(a) for a in audit_rows],
        'audit_actions': AUDIT_ACTIONS,
        'subscription': dict(sub) if sub else None,
        'team_plans': TEAM_PLANS,
    })
    return render_template('dashboard/team_governance.html', **ctx)


# ══════════════════════════════════════════════════════════
#  P4 统一质量门禁
# ══════════════════════════════════════════════════════════

@app.route('/api/teams/<int:team_id>/gate', methods=['GET', 'PUT'])
@login_required
def api_team_gate(team_id):
    """读取/更新团队质量门禁配置（仅管理员）。"""
    user = get_current_user()
    db = get_db()
    if not _is_team_admin(team_id, user['id'], db):
        return jsonify({'code': -1, 'msg': '仅管理员可配置门禁'}), 401

    if request.method == 'GET':
        gate = db.execute('SELECT * FROM team_gates WHERE team_id = ?', (team_id,)).fetchone()
        if not gate:
            gate = {'min_score': 80, 'max_critical': 0, 'max_high': 0, 'scan_mode': 'quick', 'enabled': 1}
            return jsonify({'code': 0, 'data': gate})
        return jsonify({'code': 0, 'data': dict(gate)})

    # PUT 更新
    data = request.get_json(silent=True) or {}
    min_score = int(data.get('min_score', 80))
    max_critical = int(data.get('max_critical', 0))
    max_high = int(data.get('max_high', 0))
    scan_mode = data.get('scan_mode', 'quick')
    enabled = 1 if data.get('enabled', True) else 0

    # 边界校验（治本：拒绝非法阈值，而不是运行时兜底）
    if not (0 <= min_score <= 100):
        return jsonify({'code': -1, 'msg': '最低分需在 0-100 之间'}), 400
    if max_critical < 0 or max_high < 0:
        return jsonify({'code': -1, 'msg': '漏洞上限不能为负'}), 400
    # 档位白名单（quick/smart/deep，团队无免费档），非法档位拒绝
    if scan_mode not in ('quick', 'smart', 'deep'):
        return jsonify({'code': -1, 'msg': '团队扫描档位需为 quick/smart/deep 之一'}), 400

    db.execute("""
        INSERT INTO team_gates (team_id, min_score, max_critical, max_high, scan_mode, enabled, updated_by, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
        ON CONFLICT(team_id) DO UPDATE SET
            min_score = excluded.min_score,
            max_critical = excluded.max_critical,
            max_high = excluded.max_high,
            scan_mode = excluded.scan_mode,
            enabled = excluded.enabled,
            updated_by = excluded.updated_by,
            updated_at = excluded.updated_at
    """, (team_id, min_score, max_critical, max_high, scan_mode, enabled, user['id']))
    db.commit()

    audit_log(team_id, user['id'], 'gate_updated', 'gate', team_id,
              f'最低分={min_score},严重={max_critical},高危={max_high},档位={scan_mode},启用={enabled}')
    return jsonify({'code': 0, 'msg': '门禁已更新'})


# 团队档位查询：团队管理员配置的扫描档位，决定子账号在团队身份下能用哪个档位。
# 团队无免费档（只有 quick/smart/deep），与子账号本人是否会员、有无个人积分完全无关。
_SCAN_MODE_ORDER = {'quick': 1, 'smart': 2, 'deep': 3}

def get_team_scan_mode(team_id):
    """读团队配置的扫描档位（= 子账号可用档位的「上限」）。默认 'quick'（无配置时）。返回档位字符串。

    语义：管理员给子账号设的档位是「权限上限」，不是「定死一档」。
    设 quick → 只能用 quick；设 smart → quick/smart 都能选；设 deep → 三档随便选。
    """
    try:
        init_governance_tables()
        db = get_db()
        row = db.execute('SELECT scan_mode FROM team_gates WHERE team_id = ?', (team_id,)).fetchone()
        if row and row['scan_mode'] in ('quick', 'smart', 'deep'):
            return row['scan_mode']
    except Exception as e:
        logger.warning('[团队档位] 查询失败，回退 quick: %s', e)
    return 'quick'


def get_team_member_limit(team_id):
    """读团队席位上限。有订阅记录用订阅的 member_limit；无记录（未购团队版）默认基础版 10。"""
    try:
        init_governance_tables()
        db = get_db()
        row = db.execute(
            'SELECT member_limit FROM team_subscriptions WHERE team_id = ? AND status = ?',
            (team_id, 'active')
        ).fetchone()
        if row and row['member_limit']:
            return int(row['member_limit'])
    except Exception as e:
        logger.warning('[团队席位] 查询失败，回退基础版上限 10: %s', e)
    return TEAM_PLANS['team_basic']['member_limit']


def resolve_team_scan_mode(team_id, requested_mode=None):
    """融合「管理员档位上限」+「成员自选」得到最终扫描档位。

    规则（权限上限模型，不是定死一档）：
      - 管理员配置的 scan_mode 是上限（quick < smart < deep）。
      - 成员可以自己选档，但不能超过管理员给的上限；超了自动降到上限。
      - 成员不选（requested_mode 为空或非法）→ 默认取上限本身？不，默认 quick（最保守）。
        但为符合「成员想用哪个用哪个」的直觉：不选时用 quick（最省积分）。
      - 团队无免费档，任何情况都只落在 quick/smart/deep 三档。

    返回最终档位字符串，恒为 quick/smart/deep 之一。
    """
    cap = get_team_scan_mode(team_id)  # 管理员配置的上限，恒为三档之一
    cap_rank = _SCAN_MODE_ORDER[cap]

    req = (requested_mode or '').strip().lower()
    if req in _SCAN_MODE_ORDER:
        # 成员选了合法档位：取 min(成员选的档, 上限)
        if _SCAN_MODE_ORDER[req] <= cap_rank:
            return req
        # 选了超过上限的档 → 降级到上限
        return cap
    # 成员没选或选了非法档 → 默认 quick（最保守，省积分）
    return 'quick'


def check_team_gate(team_id, score, severity_dist):
    """按团队门禁判定扫描是否通过。返回 (passed, gate, violations)。

    被 team.py 的 api_team_scan 在扫描完成后调用，把结果写回 scans 表
    的 gate_result 字段（若存在），实现「全员强制、不达标标注」。
    """
    init_governance_tables()
    db = get_db()
    gate = db.execute('SELECT * FROM team_gates WHERE team_id = ?', (team_id,)).fetchone()
    if not gate or not gate['enabled']:
        return True, None, []

    violations = []
    if score < gate['min_score']:
        violations.append(f"综合分 {score} 低于门禁 {gate['min_score']}")
    if severity_dist.get('critical', 0) > gate['max_critical']:
        violations.append(
            f"严重漏洞 {severity_dist['critical']} 超过门禁 {gate['max_critical']}")
    if severity_dist.get('high', 0) > gate['max_high']:
        violations.append(f"高危漏洞 {severity_dist['high']} 超过门禁 {gate['max_high']}")

    return (len(violations) == 0), dict(gate), violations


# ══════════════════════════════════════════════════════════
#  P5 标准对照报告（OWASP Top10 / CWE 对照）
# ══════════════════════════════════════════════════════════

# CWE 映射（确定性对照，锚定扫描器真实产出的 rule_id 前缀 + title 关键词两个维度）。
#
# 事实依据（2026-10-29 对 471 种真实 rule_id 全量对账得出）：
#   - 扫描器真实 issue 的 rule_id 是 B3-*/E1-*/E2-*/E3-*/E2-SEC-*/E8-SEC-*/SEC-*/
#     B3001/B14-*/BIZ-LOGIC-*/B15-LLM-*/TAINT-CWE-* 这套编号体系。
#   - 2026-11-02 前缀归位：正则 bundle 原本也输出 E7-SEC-<语言>，与「E7 = AI 应用
#     健康引擎」冲突，已统一改为 E2-SEC-<语言>（组 8 本就由 E2 安全引擎消费）。
#     故本表内的 e2-sec-* 条目既覆盖 AST 引擎的老编号，也覆盖 bundle 的现编号。
#   - 旧的「sec-sqli/sec-cmd/sec-xss…」前缀在真实 issue 里一个都不存在，是死映射。
#   - CWE 只属于「安全漏洞」；quality/perf/architecture/命名等规则本就不该映射 CWE。
#
# 匹配优先级：先 rule_id 前缀（精确、快），匹配不到再 title 关键词兜底。
# 每条只映射到「能确凿对应」的 CWE，其余归「未映射」（正确行为，不是漏）。
_CWE_RULEID_MAP = [
    # ── 污点引擎直接带 CWE 编号（最权威）──
    ('taint-cwe-89', 'CWE-89', 'SQL 注入', 'A03'),
    ('taint-cwe-611', 'CWE-611', 'XML 外部实体注入', 'A05'),
    ('taint-cwe-22', 'CWE-22', '路径遍历', 'A01'),
    ('taint-cwe-918', 'CWE-918', '服务端请求伪造', 'A10'),
    # ── SQL 注入 ──
    ('sec-java-sql', 'CWE-89', 'SQL 注入', 'A03'),
    ('sec-inj', 'CWE-89', 'SQL 注入', 'A03'),
    ('e2-sec-sql', 'CWE-89', 'SQL 注入', 'A03'),
    ('e2-sec-php-004', 'CWE-89', 'SQL 注入', 'A03'),
    ('e2-sec-jv-002', 'CWE-89', 'SQL 注入', 'A03'),
    ('e2-sec-js-001', 'CWE-89', 'SQL 注入', 'A03'),
    ('b3001', 'CWE-89', 'SQL 注入', 'A03'),
    ('b15-llm-sql', 'CWE-89', 'SQL 注入', 'A03'),
    # ── SSRF ──
    ('sec-java-ssrf', 'CWE-918', '服务端请求伪造', 'A10'),
    ('sec-ssrf', 'CWE-918', '服务端请求伪造', 'A10'),
    ('b3-sec-pysr', 'CWE-918', '服务端请求伪造', 'A10'),
    ('e2-sec-jv-031', 'CWE-918', '服务端请求伪造', 'A10'),
    ('b15-llm-ssrf', 'CWE-918', '服务端请求伪造', 'A10'),
    # ── OS 命令注入 ──
    ('sec-cmd', 'CWE-78', 'OS 命令注入', 'A03'),
    ('b3-sec-cmd', 'CWE-78', 'OS 命令注入', 'A03'),
    ('e2-sec-cmd', 'CWE-78', 'OS 命令注入', 'A03'),
    ('e2-sec-py-005', 'CWE-78', 'OS 命令注入', 'A03'),
    ('e2-sec-py-006', 'CWE-78', 'OS 命令注入', 'A03'),
    ('e8-sec-py-006', 'CWE-78', 'OS 命令注入', 'A03'),
    # ── 路径遍历 ──
    ('sec-java-path', 'CWE-22', '路径遍历', 'A01'),
    ('b3-sec-ptr', 'CWE-22', '路径遍历', 'A01'),
    ('b3-sec-jvpt', 'CWE-22', '路径遍历', 'A01'),
    ('b15-llm-path', 'CWE-22', '路径遍历', 'A01'),
    # ── XSS ──
    ('b3003', 'CWE-79', '跨站脚本 XSS', 'A03'),
    ('e2-sec-php-018', 'CWE-79', '跨站脚本 XSS', 'A03'),
    ('b15-llm-xss', 'CWE-79', '跨站脚本 XSS', 'A03'),
    # ── 硬编码凭据 ──
    ('sec-auth', 'CWE-798', '硬编码凭据', 'A07'),
    ('b3002', 'CWE-798', '硬编码凭据', 'A07'),
    ('b3-sec-hcs', 'CWE-798', '硬编码凭据', 'A07'),
    ('b3-sec-jhcs', 'CWE-798', '硬编码凭据', 'A07'),
    ('e2-sec-hcs', 'CWE-798', '硬编码凭据', 'A07'),
    ('e2-sec-jhcs', 'CWE-798', '硬编码凭据', 'A07'),
    ('e2-sec-jv-006', 'CWE-798', '硬编码凭据', 'A07'),
    ('e2-sec-py-010', 'CWE-798', '硬编码凭据', 'A07'),
    ('e8-sec-py-010', 'CWE-798', '硬编码凭据', 'A07'),
    ('sec-java-020', 'CWE-798', '硬编码凭据', 'A07'),
    ('sec-java-021', 'CWE-798', '硬编码凭据', 'A07'),
    # ── 不安全反序列化 ──
    ('sec-java-jvds', 'CWE-502', '不安全的反序列化', 'A08'),
    ('b3-sec-jvdc', 'CWE-502', '不安全的反序列化', 'A08'),
    ('e2-sec-jvds', 'CWE-502', '不安全的反序列化', 'A08'),
    ('e2-sec-jv-004', 'CWE-502', '不安全的反序列化', 'A08'),
    ('e2-sec-py-003', 'CWE-502', '不安全的反序列化', 'A08'),
    ('b15-llm-deser', 'CWE-502', '不安全的反序列化', 'A08'),
    ('sec-java-cve-001', 'CWE-502', '不安全的反序列化', 'A08'),
    # ── 弱加密 / 弱哈希 ──
    ('sec-java-crypto', 'CWE-327', '弱加密算法', 'A02'),
    ('sec-py-010', 'CWE-328', '弱哈希', 'A02'),
    ('sec-py-011', 'CWE-328', '弱哈希', 'A02'),
    ('b3-sec-jcrp', 'CWE-327', '弱加密算法', 'A02'),
    ('e2-sec-jv-043', 'CWE-328', '弱哈希', 'A02'),
    ('e2-sec-py-012', 'CWE-328', '弱哈希', 'A02'),
    ('b15-llm-crypto', 'CWE-327', '弱加密算法', 'A02'),
    # ── 弱随机数 ──
    ('b3004', 'CWE-338', '弱随机数', 'A02'),
    ('e2-sec-jv-034', 'CWE-338', '弱随机数', 'A02'),
    ('sec-java-crypto-020', 'CWE-338', '弱随机数', 'A02'),
    # ── CSRF ──
    ('biz-logic-csrf', 'CWE-352', '跨站请求伪造', 'A01'),
    ('sec-go-018', 'CWE-352', '跨站请求伪造', 'A01'),
    ('b14-csrf', 'CWE-352', '跨站请求伪造', 'A01'),
    # ── IDOR / 越权 / 缺失授权 ──
    ('biz-logic-idor', 'CWE-639', '不安全的直接对象引用', 'A01'),
    ('b14-idor', 'CWE-639', '不安全的直接对象引用', 'A01'),
    ('idor-java', 'CWE-639', '不安全的直接对象引用', 'A01'),
    ('e2-biz-java', 'CWE-639', '不安全的直接对象引用', 'A01'),
    ('sec-kt-auth-002', 'CWE-639', '不安全的直接对象引用', 'A01'),
    ('sec-swift-auth-002', 'CWE-639', '不安全的直接对象引用', 'A01'),
    ('biz-logic-vpriv', 'CWE-862', '缺失授权', 'A01'),
    ('b14-pe', 'CWE-862', '缺失授权', 'A01'),
    ('e2-bs-auth', 'CWE-862', '缺失授权', 'A01'),
    ('bs-auth', 'CWE-862', '缺失授权', 'A01'),
    ('sec-go-auth', 'CWE-862', '缺失授权', 'A01'),
    ('sec-kt-auth', 'CWE-862', '缺失授权', 'A01'),
    ('sec-scala-auth', 'CWE-862', '缺失授权', 'A01'),
    ('sec-sh-auth', 'CWE-862', '缺失授权', 'A01'),
    ('b15-llm-privilege', 'CWE-862', '缺失授权', 'A01'),
    ('b15-llm-auth', 'CWE-287', '认证绕过', 'A07'),
    # ── 支付数据篡改 ──
    ('biz-logic-pay', 'CWE-347', '数据完整性校验缺失', 'A08'),
    ('b14-pay', 'CWE-347', '数据完整性校验缺失', 'A08'),
    ('bs-pay', 'CWE-347', '数据完整性校验缺失', 'A08'),
    ('e2-bs-pay', 'CWE-347', '数据完整性校验缺失', 'A08'),
    # ── 会话固定 ──
    ('biz-logic-sess', 'CWE-384', '会话固定', 'A07'),
    ('b14-sess', 'CWE-384', '会话固定', 'A07'),
    # ── XXE ──
    ('b15-llm-xxe', 'CWE-611', 'XML 外部实体注入', 'A05'),
    # ── 日志注入 / 敏感信息写日志 ──
    ('sec-java-log-001', 'CWE-117', '日志注入', 'A09'),
    ('sec-java-log-002', 'CWE-532', '敏感信息写入日志', 'A09'),
    ('e2-sec-jv-020', 'CWE-532', '敏感信息写入日志', 'A09'),
    # ── 缓冲区溢出 / 不安全字符串函数 ──
    ('b3-sec-bovf', 'CWE-120', '缓冲区溢出', 'A01'),
    ('b3-sec-cpus', 'CWE-120', '缓冲区溢出', 'A01'),
    ('sec-c-010', 'CWE-120', '缓冲区溢出', 'A01'),
    # ── 空指针 / 未初始化 ──
    ('b3-sec-cpnd', 'CWE-476', '空指针解引用', 'A01'),
    ('e8-sec-go-023', 'CWE-476', '空指针解引用', 'A01'),
    ('sec-c-009', 'CWE-457', '未初始化变量', 'A01'),
    # ── 资源未释放 / 内存泄漏 ──
    ('b3-sec-jrlc', 'CWE-772', '资源未释放', 'A01'),
    ('e2-sec-jrlc', 'CWE-772', '资源未释放', 'A01'),
    ('e2-sec-jv-049', 'CWE-772', '资源未释放', 'A01'),
    ('e2-sec-jv-050', 'CWE-401', '内存泄漏', 'A01'),
    ('e8-sec-go-009', 'CWE-754', '未检查返回值', 'A01'),
    # ── 竞态条件 ──
    ('race-java', 'CWE-362', '竞态条件', 'A01'),
    ('b15-llm-race', 'CWE-362', '竞态条件', 'A01'),
    # ── JNDI / 表达式注入 ──
    ('b3-sec-jvja', 'CWE-917', '表达式语言注入', 'A03'),
    # ── 文件上传 ──
    ('b3-sec-jvfu', 'CWE-434', '不受限制的文件上传', 'A04'),
    ('e2-sec-jv-030', 'CWE-434', '不受限制的文件上传', 'A04'),
    # ── 已知漏洞组件 / 未锁版本 ──
    ('sca-cve', 'CWE-937', '使用已知漏洞组件', 'A06'),
    ('sca-unpinned', 'CWE-1104', '使用未锁版本组件', 'A06'),
    ('dep-rem', 'CWE-937', '使用已知漏洞组件', 'A06'),
    ('dep-sec', 'CWE-937', '使用已知漏洞组件', 'A06'),
    ('dep-trans', 'CWE-937', '使用已知漏洞组件', 'A06'),
    ('dep-lic', 'CWE-937', '使用已知漏洞组件', 'A06'),
    ('b8001', 'CWE-937', '使用已知漏洞组件', 'A06'),
    ('b8003', 'CWE-937', '使用已知漏洞组件', 'A06'),
    ('e7-xml-034', 'CWE-937', '使用已知漏洞组件', 'A06'),
    # ── LLM 其他安全 ──
    ('b15-llm-injection', 'CWE-74', '注入', 'A03'),
    ('b15-llm-info', 'CWE-200', '敏感信息泄露', 'A01'),
    ('sec-leak-llm', 'CWE-200', '敏感信息泄露', 'A01'),
    ('sec-other-llm', 'CWE-200', '敏感信息泄露', 'A01'),
]

# title 关键词 → CWE（rule_id 匹配不到时的兜底，按确定性语义）。
_CWE_TITLE_MAP = [
    ('sql注入', 'CWE-89', 'SQL 注入', 'A03'),
    ('sql 注入', 'CWE-89', 'SQL 注入', 'A03'),
    ('命令注入', 'CWE-78', 'OS 命令注入', 'A03'),
    ('command injection', 'CWE-78', 'OS 命令注入', 'A03'),
    ('ssrf', 'CWE-918', '服务端请求伪造', 'A10'),
    ('xss', 'CWE-79', '跨站脚本 XSS', 'A03'),
    ('跨站脚本', 'CWE-79', '跨站脚本 XSS', 'A03'),
    ('路径遍历', 'CWE-22', '路径遍历', 'A01'),
    ('path traversal', 'CWE-22', '路径遍历', 'A01'),
    ('硬编码', 'CWE-798', '硬编码凭据', 'A07'),
    ('反序列化', 'CWE-502', '不安全的反序列化', 'A08'),
    ('xxe', 'CWE-611', 'XML 外部实体注入', 'A05'),
    ('外部实体', 'CWE-611', 'XML 外部实体注入', 'A05'),
    ('csrf', 'CWE-352', '跨站请求伪造', 'A01'),
    ('越权', 'CWE-862', '缺失授权', 'A01'),
    ('idor', 'CWE-639', '不安全的直接对象引用', 'A01'),
    ('会话固定', 'CWE-384', '会话固定', 'A07'),
    ('弱哈希', 'CWE-328', '弱哈希', 'A02'),
    ('弱加密', 'CWE-327', '弱加密算法', 'A02'),
    ('弱随机', 'CWE-338', '弱随机数', 'A02'),
    ('缓冲区溢出', 'CWE-120', '缓冲区溢出', 'A01'),
    ('buffer overflow', 'CWE-120', '缓冲区溢出', 'A01'),
    ('日志注入', 'CWE-117', '日志注入', 'A09'),
    ('log injection', 'CWE-117', '日志注入', 'A09'),
    ('敏感信息', 'CWE-200', '敏感信息泄露', 'A01'),
    ('文件上传', 'CWE-434', '不受限制的文件上传', 'A04'),
    ('竞态', 'CWE-362', '竞态条件', 'A01'),
    ('已知漏洞', 'CWE-937', '使用已知漏洞组件', 'A06'),
    ('cve', 'CWE-937', '使用已知漏洞组件', 'A06'),
    ('jndi', 'CWE-917', '表达式语言注入', 'A03'),
    ('eval', 'CWE-95', '代码注入', 'A03'),
    ('代码注入', 'CWE-94', '代码注入', 'A03'),
    ('支付金额', 'CWE-347', '数据完整性校验缺失', 'A08'),
]

# OWASP Top10 (2021) 中文名
OWASP_TOP10_2021 = {
    'A01': '失效的访问控制',
    'A02': '加密机制失效',
    'A03': '注入',
    'A04': '不安全设计',
    'A05': '安全配置错误',
    'A06': '易受攻击和过时的组件',
    'A07': '身份识别和认证失败',
    'A08': '软件和数据完整性故障',
    'A09': '安全日志和监控故障',
    'A10': '服务器端请求伪造',
}


def _map_issue_to_cwe(issue):
    """把单条 issue 映射到 CWE。返回 (cwe_id, cwe_name, owasp_id) 或 None。

    双维匹配：先 rule_id 前缀（精确），匹配不到再 title 关键词兜底。
    CWE 只属于「安全漏洞」，quality/perf/architecture 等规则返回 None 是正确行为。
    """
    rule_id = str(issue.get('rule_id') or issue.get('check_id') or '').lower()
    for kw, cwe_id, cwe_name, owasp_id in _CWE_RULEID_MAP:
        if kw in rule_id:
            return cwe_id, cwe_name, owasp_id
    title = str(issue.get('title') or issue.get('message') or '').lower()
    for kw, cwe_id, cwe_name, owasp_id in _CWE_TITLE_MAP:
        if kw in title:
            return cwe_id, cwe_name, owasp_id
    return None


def build_compliance_report(team_id, scan_ids=None):
    """构建团队标准对照报告：把团队所有（或指定）扫描的 issue 按 CWE/OWASP 归集。"""
    init_governance_tables()
    db = get_db()

    if scan_ids:
        placeholders = ','.join('?' * len(scan_ids))
        rows = db.execute(
            f'SELECT scan_id, title, created_at, results, score FROM scans '
            f'WHERE team_id = ? AND scan_id IN ({placeholders}) ORDER BY created_at DESC',
            [team_id] + list(scan_ids)
        ).fetchall()
    else:
        rows = db.execute(
            'SELECT scan_id, title, created_at, results, score FROM scans '
            'WHERE team_id = ? ORDER BY created_at DESC',
            (team_id,)
        ).fetchall()

    cwe_buckets = {}       # cwe_id -> {name, owasp, count, issues, severity}
    owasp_buckets = {}     # owasp_id -> count
    unmapped = 0
    total_issues = 0
    scan_summaries = []

    for r in rows:
        issues = []
        try:
            data = json.loads(r['results']) if r['results'] else {}
            issues = data.get('issues', [])
        except (json.JSONDecodeError, TypeError):
            pass

        total_issues += len(issues)
        scan_summaries.append({
            'scan_id': r['scan_id'],
            'title': r['title'],
            'created_at': r['created_at'],
            'score': r['score'],
            'issue_count': len(issues),
        })

        for iss in issues:
            mapped = _map_issue_to_cwe(iss)
            if not mapped:
                unmapped += 1
                continue
            cwe_id, cwe_name, owasp_id = mapped
            bucket = cwe_buckets.setdefault(cwe_id, {
                'cwe_id': cwe_id, 'cwe_name': cwe_name, 'owasp_id': owasp_id,
                'count': 0, 'severity': {'critical': 0, 'high': 0, 'medium': 0, 'low': 0},
            })
            bucket['count'] += 1
            sev = iss.get('severity', 'low')
            if sev in ('blocker', 'critical'):
                bucket['severity']['critical'] += 1
            elif sev in ('high', 'suspicious'):
                bucket['severity']['high'] += 1
            elif sev in ('medium', 'correctness', 'restriction'):
                bucket['severity']['medium'] += 1
            else:
                bucket['severity']['low'] += 1

            owasp_buckets[owasp_id] = owasp_buckets.get(owasp_id, 0) + 1

    # 按 CWE 数量降序
    cwe_list = sorted(cwe_buckets.values(), key=lambda b: b['count'], reverse=True)

    owasp_list = []
    for owasp_id, name in OWASP_TOP10_2021.items():
        cnt = owasp_buckets.get(owasp_id, 0)
        if cnt > 0:
            owasp_list.append({'owasp_id': owasp_id, 'name': name, 'count': cnt})
    owasp_list.sort(key=lambda x: x['count'], reverse=True)

    return {
        'team_id': team_id,
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_scans': len(rows),
        'total_issues': total_issues,
        'unmapped': unmapped,
        'cwe_buckets': cwe_list,
        'owasp_list': owasp_list,
        'scan_summaries': scan_summaries,
    }


@app.route('/api/teams/<int:team_id>/compliance', methods=['GET'])
@login_required
def api_team_compliance(team_id):
    """P5 标准对照报告数据接口。"""
    user = get_current_user()
    db = get_db()
    if not _team_role(team_id, user['id'], db):
        return jsonify({'code': -1, 'msg': '无权访问'}), 401
    report = build_compliance_report(team_id)
    return jsonify({'code': 0, 'data': report})


# ══════════════════════════════════════════════════════════
#  P6 团队版购买闭环 + 共享积分池
# ══════════════════════════════════════════════════════════

def _ensure_team_pool(db, team_id):
    """确保团队共享积分池存在（幂等）。"""
    init_governance_tables()
    row = db.execute(
        'SELECT id FROM team_credit_pools WHERE team_id = ?', (team_id,)
    ).fetchone()
    if not row:
        import uuid as _uuid
        pool_id = str(_uuid.uuid4())
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        db.execute("""
            INSERT INTO team_credit_pools (id, team_id, balance, total_earned, total_spent, period_start, period_end)
            VALUES (?, ?, 0, 0, 0, ?, ?)
        """, (pool_id, team_id, now, now))
        db.commit()
    return team_id


def get_team_credit_balance(team_id):
    """团队共享积分池余额。"""
    init_governance_tables()
    db = get_db()
    row = db.execute(
        'SELECT COALESCE(SUM(balance), 0) b FROM team_credit_pools WHERE team_id = ?',
        (team_id,)
    ).fetchone()
    return row['b'] if row else 0


def consume_team_credits(team_id, amount, actor_id, ref_type='team_scan', ref_id=None, remark=''):
    """从团队共享积分池原子扣费（复用 BEGIN IMMEDIATE 语义，防超扣）。"""
    if not team_id or amount <= 0:
        return False
    init_governance_tables()
    db = get_db()
    _ensure_team_pool(db, team_id)

    try:
        db.execute('BEGIN IMMEDIATE')
        pool = db.execute(
            'SELECT id, balance FROM team_credit_pools WHERE team_id = ?',
            (team_id,)
        ).fetchone()
        if not pool or pool['balance'] < amount:
            db.execute('ROLLBACK')
            return False

        db.execute("""
            UPDATE team_credit_pools SET balance = balance - ?, total_spent = total_spent + ?,
                   updated_at = datetime('now', 'localtime')
            WHERE id = ?
        """, (amount, amount, pool['id']))

        # 写团队积分流水到 credit_transactions（复用个人流水表，team 维度用 pool_type 区分）
        db.execute("""
            INSERT INTO credit_transactions
                (user_id, type, amount, balance_after, ref_type, ref_id, remark, pool_id, pool_type)
            VALUES (?, 'consume', -?, ?, ?, ?, ?, ?, 'team')
        """, (actor_id, amount, pool['balance'] - amount,
              ref_type, str(ref_id) if ref_id else None, remark, pool['id']))
        db.commit()
        return True
    except sqlite3.Error as e:
        logger.warning('[团队积分] consume_team_credits 失败 team_id=%s: %s', team_id, e)
        try:
            db.execute('ROLLBACK')
        except Exception:
            pass
        return False


def grant_team_credits(team_id, amount, actor_id, ref_type='team_plan', ref_id=None, remark=''):
    """给团队共享积分池发放积分（购买团队版时调用，幂等防重）。"""
    if not team_id or amount <= 0:
        return False
    init_governance_tables()
    db = get_db()
    _ensure_team_pool(db, team_id)

    # 幂等防重：同一 (ref_type, ref_id) 已发放过则跳过
    if ref_id:
        dup = db.execute("""
            SELECT 1 FROM credit_transactions
            WHERE type = 'grant' AND ref_type = ? AND ref_id = ? AND pool_type = 'team'
            LIMIT 1
        """, (ref_type, str(ref_id))).fetchone()
        if dup:
            logger.info('[团队积分] 幂等跳过重复发放 team_id=%s ref_id=%s', team_id, ref_id)
            return True

    try:
        db.execute('BEGIN IMMEDIATE')
        pool = db.execute(
            'SELECT id, balance FROM team_credit_pools WHERE team_id = ?', (team_id,)
        ).fetchone()
        if not pool:
            db.execute('ROLLBACK')
            return False

        db.execute("""
            UPDATE team_credit_pools SET balance = balance + ?, total_earned = total_earned + ?,
                   updated_at = datetime('now', 'localtime')
            WHERE id = ?
        """, (amount, amount, pool['id']))

        db.execute("""
            INSERT INTO credit_transactions
                (user_id, type, amount, balance_after, ref_type, ref_id, remark, pool_id, pool_type)
            VALUES (?, 'grant', ?, ?, ?, ?, ?, ?, 'team')
        """, (actor_id, amount, pool['balance'] + amount,
              ref_type, str(ref_id) if ref_id else None, remark, pool['id']))
        db.commit()
        return True
    except sqlite3.Error as e:
        logger.warning('[团队积分] grant_team_credits 失败 team_id=%s: %s', team_id, e)
        try:
            db.execute('ROLLBACK')
        except Exception:
            pass
        return False


def _activate_team_subscription(team_id, plan_id, actor_id):
    """开通团队版订阅（发放共享积分 + 更新订阅状态）。"""
    plan = TEAM_PLANS.get(plan_id)
    if not plan:
        return False, '无效的团队版套餐'

    init_governance_tables()
    db = get_db()
    now = datetime.now()
    period_end = (now + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')

    db.execute("""
        INSERT INTO team_subscriptions (team_id, plan_id, status, member_limit, period_start, period_end)
        VALUES (?, ?, 'active', ?, ?, ?)
        ON CONFLICT(team_id) DO UPDATE SET
            plan_id = excluded.plan_id, status = 'active',
            member_limit = excluded.member_limit,
            period_start = excluded.period_start, period_end = excluded.period_end
    """, (team_id, plan_id, plan['member_limit'], now.strftime('%Y-%m-%d %H:%M:%S'), period_end))
    db.commit()

    grant_team_credits(team_id, plan['credits'], actor_id,
                       ref_type='team_plan', ref_id=f'{plan_id}:{team_id}',
                       remark=f'购买{plan["name"]}共享积分{plan["credits"]}')
    audit_log(team_id, actor_id, 'plan_purchased', 'plan', plan_id, f'购买{plan["name"]}')
    return True, None


@app.route('/api/teams/<int:team_id>/credits', methods=['GET'])
@login_required
def api_team_credits(team_id):
    """查询团队共享积分池余额 + 流水。"""
    user = get_current_user()
    db = get_db()
    if not _team_role(team_id, user['id'], db):
        return jsonify({'code': -1, 'msg': '无权访问'}), 401

    balance = get_team_credit_balance(team_id)
    txns = db.execute("""
        SELECT ct.*, u.email as actor_email
        FROM credit_transactions ct
        LEFT JOIN users u ON u.id = ct.user_id
        WHERE ct.pool_type = 'team' AND ct.pool_id IN (
            SELECT id FROM team_credit_pools WHERE team_id = ?
        )
        ORDER BY ct.id DESC LIMIT 50
    """, (team_id,)).fetchall()

    sub = db.execute('SELECT * FROM team_subscriptions WHERE team_id = ?', (team_id,)).fetchone()
    return jsonify({
        'code': 0,
        'data': {
            'balance': balance,
            'transactions': [dict(t) for t in txns],
            'subscription': dict(sub) if sub else None,
        }
    })


# ── P6 团队版购买（复用门房微信支付）──

def _ensure_orders_team_id():
    """给 orders 表加 team_id 列（幂等），用于团队版订单关联。"""
    init_governance_tables()  # 该迁移已并入 init_governance_tables，此处兜底


@app.route('/api/teams/<int:team_id>/subscribe', methods=['POST'])
@login_required
def api_team_subscribe(team_id):
    """P6 创建团队版购买订单（对接门房微信支付）。

    流程：校验管理员权限 → 复用 payment 的门房下单函数 → 订单落 orders 表
    （order_type='team'，team_id 关联）→ 返回支付二维码。
    """
    user = get_current_user()
    db = get_db()
    if not _is_team_admin(team_id, user['id'], db):
        return jsonify({'code': -1, 'msg': '仅管理员可为团队购买团队版'}), 401

    data = request.get_json(silent=True) or {}
    plan_id = data.get('plan_id', 'team_basic')
    plan = TEAM_PLANS.get(plan_id)
    if not plan:
        return jsonify({'code': -1, 'msg': '无效的团队版套餐'}), 400

    # 复用 payment 模块的门房下单函数（同一门房、同一微信支付，不重造）
    from . import payment as _pay
    email = user.get('email', '')
    mf_token = session.get('mf_token', '')
    mf_pwd_hash = user.get('mf_password_hash', '') or ''

    _pay._menfang_lazy_sync(email, mf_pwd_hash)

    result = _pay._menfang_create_pay_order_with_token(
        email, mf_token, plan['mf_plan'], plan['amount'])
    if not result.get('success') and mf_pwd_hash:
        result = _pay._menfang_create_pay_order_with_hash(
            email, mf_pwd_hash, plan['mf_plan'], plan['amount'])
    if not result.get('success'):
        return jsonify({'code': -1, 'msg': result.get('message', '创建订单失败')}), 400

    mf_order_id = result['order_id']
    _ensure_orders_team_id()
    db.execute("""
        INSERT INTO orders (order_id, user_id, plan_id, plan_name, order_type, amount, status, mf_order_id, team_id)
        VALUES (?, ?, ?, ?, 'team', ?, 'pending', ?, ?)
    """, (mf_order_id, user['id'], plan_id, plan['name'], plan['amount'], mf_order_id, team_id))
    db.commit()

    audit_log(team_id, user['id'], 'plan_purchased', 'order', mf_order_id,
              f'发起购买{plan["name"]}（待支付）')
    return jsonify({
        'code': 0,
        'order_id': mf_order_id,
        'amount': plan['amount'],
        'qr_url': result.get('qr_code_url', ''),
    })


@app.route('/api/teams/<int:team_id>/subscribe/status/<order_id>', methods=['GET'])
@login_required
def api_team_subscribe_status(team_id, order_id):
    """P6 查询团队版订单支付状态，支付成功则开通订阅 + 发放共享积分。"""
    user = get_current_user()
    db = get_db()
    if not _is_team_admin(team_id, user['id'], db):
        return jsonify({'code': -1, 'msg': '无权操作'}), 401

    order = db.execute(
        'SELECT * FROM orders WHERE order_id = ? AND team_id = ? AND user_id = ?',
        (order_id, team_id, user['id'])
    ).fetchone()
    if not order:
        return jsonify({'code': -1, 'msg': '订单不存在'}), 404

    if order['status'] == 'paid':
        return jsonify({'code': 0, 'status': 'paid'})

    from . import payment as _pay
    mf_status = _pay._menfang_get_order_status(order_id)
    if not mf_status['found'] or mf_status['status'] != 'paid':
        return jsonify({'code': 0, 'status': mf_status.get('status', order['status'])})

    # 支付成功 → 开通订阅 + 发放共享积分
    db.execute(
        "UPDATE orders SET status='paid', paid_at=datetime('now','localtime') WHERE order_id=?",
        (order_id,))
    db.commit()
    ok, err = _activate_team_subscription(team_id, order['plan_id'], user['id'])
    if not ok:
        return jsonify({'code': -1, 'msg': err}), 500
    return jsonify({'code': 0, 'status': 'paid'})


# ── 独立「购买团队版」入口：付费即自动建团 + 设购买者为管理员 ──

def _auto_create_team_for_purchase(user_id, team_name):
    """付费成功后自动建团队 + 设购买者为 owner 管理员。

    返回 (team_id, None) 或 (None, 错误信息)。复用 team.py 的建团规则
    （teams/team_members/team_quotas 三表 + owner 角色）。
    """
    from . import team as _team
    db = get_db()

    # 复用 team.py 的团队数量上限
    count = db.execute(
        'SELECT COUNT(*) c FROM team_members WHERE user_id = ? AND role = ?',
        (user_id, _team.TEAM_ROLE_OWNER)).fetchone()
    if count and count['c'] >= _team.MAX_TEAMS_PER_USER:
        return None, f'最多创建{_team.MAX_TEAMS_PER_USER}个团队'

    if not team_name or len(team_name.strip()) < 2:
        team_name = '我的团队'

    try:
        cur = db.execute(
            'INSERT INTO teams (name, description, owner_id) VALUES (?, ?, ?)',
            (team_name.strip(), '', user_id))
        team_id = cur.lastrowid
        db.execute(
            'INSERT INTO team_members (team_id, user_id, role) VALUES (?, ?, ?)',
            (team_id, user_id, _team.TEAM_ROLE_OWNER))
        today = datetime.now().strftime('%Y-%m-%d')
        db.execute(
            'INSERT INTO team_quotas (team_id, daily_limit, used_today, reset_date) VALUES (?, ?, 0, ?)',
            (team_id, _team.TEAM_QUOTA_DEFAULT, today))
        db.commit()
        logger.info('[团队版] 付费自动建团: user=%s team=%s (ID=%s)', user_id, team_name, team_id)
        return team_id, None
    except Exception as e:
        db.rollback()
        logger.error('[团队版] 付费自动建团失败: %s', e)
        return None, '自动创建团队失败'


@app.route('/api/team/purchase', methods=['POST'])
@login_required
def api_team_purchase():
    """独立购买团队版入口：下单时不必已有团队，付费成功后自动建团。

    请求：{ plan_id: 'team_basic'|'team_pro', team_name?: '团队名' }
    返回：{ code, order_id, amount, qr_url }
    """
    user = get_current_user()
    db = get_db()
    data = request.get_json(silent=True) or {}

    plan_id = data.get('plan_id', 'team_basic')
    plan = TEAM_PLANS.get(plan_id)
    if not plan:
        return jsonify({'code': -1, 'msg': '无效的团队版套餐'}), 400

    team_name = (data.get('team_name') or '').strip()

    # 复用 payment 门房下单（同一门房、同一微信支付）
    from . import payment as _pay
    email = user.get('email', '')
    mf_token = session.get('mf_token', '')
    mf_pwd_hash = user.get('mf_password_hash', '') or ''

    _pay._menfang_lazy_sync(email, mf_pwd_hash)

    result = _pay._menfang_create_pay_order_with_token(
        email, mf_token, plan['mf_plan'], plan['amount'])
    if not result.get('success') and mf_pwd_hash:
        result = _pay._menfang_create_pay_order_with_hash(
            email, mf_pwd_hash, plan['mf_plan'], plan['amount'])
    if not result.get('success'):
        return jsonify({'code': -1, 'msg': result.get('message', '创建订单失败')}), 400

    mf_order_id = result['order_id']
    _ensure_orders_team_id()
    # team_id 先不填（NULL），付费成功后再建团回填；team_name 记住待建团队名
    db.execute("""
        INSERT INTO orders (order_id, user_id, plan_id, plan_name, order_type, amount, status, mf_order_id, team_id, team_name)
        VALUES (?, ?, ?, ?, 'team', ?, 'pending', ?, NULL, ?)
    """, (mf_order_id, user['id'], plan_id, plan['name'], plan['amount'], mf_order_id, team_name))
    db.commit()

    return jsonify({
        'code': 0,
        'order_id': mf_order_id,
        'amount': plan['amount'],
        'qr_url': result.get('qr_code_url', ''),
    })


@app.route('/api/team/purchase/qrcode', methods=['GET'])
@login_required
def api_team_purchase_qrcode():
    """把微信支付链接(weixin:// 或 http)转成二维码图片返回，供前端在弹窗内显示。

    兜底场景：门房偶发返回原始 code_url 而非 base64 图片时，前端不跳转、不开新窗，
    而是请求本接口把链接转成二维码 PNG 图片就地显示。
    """
    from flask import Response
    url = request.args.get('url', '').strip()
    if not url or not (url.startswith('weixin://') or url.startswith('http://') or url.startswith('https://')):
        return jsonify({'code': -1, 'msg': '无效的支付链接'}), 400
    try:
        import qrcode
        from io import BytesIO
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color='#1A3A5C', back_color='white')
        buf = BytesIO()
        img.save(buf, format='PNG')
        return Response(buf.getvalue(), mimetype='image/png')
    except Exception as e:
        logger.warning('[团队版] 二维码兜底渲染失败: %s', e)
        return jsonify({'code': -1, 'msg': '二维码生成失败'}), 500


def _finalize_team_purchase(order_id, user_id=None):
    """支付成功后收尾：建团 + 设 owner + 发共享积分 + 标记订单 paid。

    幂等设计（治本）：先用「原子抢占」把订单从 pending 更新为 paid，
    只有抢占成功（rowcount==1）的那个请求才继续建团发积分；并发下
    前端轮询与门房回调同时触发时，只会有一路真正执行，杜绝重复建团/重复发积分。

    返回 (ok, team_id, message)：
      - ok=True  → 已支付且团队就绪（team_id 可能为 None 表示刚抢占但建团失败后的降级）
      - ok=False → 失败原因
    """
    db = get_db()

    order = db.execute(
        'SELECT * FROM orders WHERE order_id = ?', (order_id,)).fetchone()
    if not order:
        return False, None, '订单不存在'

    # 已支付 → 直接返回既有 team_id（幂等，重复调用安全）
    if order['status'] == 'paid':
        return True, order['team_id'], ''

    # 归属校验（可选）：调用方传了 user_id 时，订单必须属于该用户
    if user_id is not None and order['user_id'] != user_id:
        return False, None, '订单不存在'

    # 原子抢占：只有把 pending → paid 更新成功的那一路才继续建团。
    # 用 rowcount 判断是否抢占成功，防止并发重复建团。
    cur = db.execute(
        "UPDATE orders SET status='paid', paid_at=datetime('now','localtime') "
        "WHERE order_id = ? AND status = 'pending'", (order_id,))
    if cur.rowcount == 0:
        # 已被另一路抢占，读回最新 team_id 返回
        refreshed = db.execute(
            'SELECT team_id FROM orders WHERE order_id = ?', (order_id,)).fetchone()
        return True, refreshed['team_id'] if refreshed else None, ''
    db.commit()

    # 建团（若订单还没有 team_id）
    team_id = order['team_id']
    if not team_id:
        team_id, err = _auto_create_team_for_purchase(
            order['user_id'], order['team_name'] if 'team_name' in order.keys() else '')
        if not team_id:
            # 建团失败：订单已标 paid，钱已到账，但不能让用户丢权益。
            # 回滚状态为 pending，等下次轮询/回调重试。
            db.execute("UPDATE orders SET status='pending' WHERE order_id = ?", (order_id,))
            db.commit()
            return False, None, err

    # 回填 team_id
    db.execute("UPDATE orders SET team_id=? WHERE order_id=?", (team_id, order_id))
    db.commit()

    # 开通订阅 + 发放共享积分（幂等：team_subscriptions 用 ON CONFLICT 覆盖）
    ok, err = _activate_team_subscription(team_id, order['plan_id'], order['user_id'])
    if not ok:
        return False, team_id, err

    return True, team_id, ''


@app.route('/api/team/purchase/status/<order_id>', methods=['GET'])
@login_required
def api_team_purchase_status(order_id):
    """查询独立购买订单支付状态；支付成功则自动建团 + 设 owner + 发共享积分。"""
    user = get_current_user()
    db = get_db()

    order = db.execute(
        'SELECT * FROM orders WHERE order_id = ? AND user_id = ?',
        (order_id, user['id'])).fetchone()
    if not order:
        return jsonify({'code': -1, 'msg': '订单不存在'}), 404

    if order['status'] == 'paid':
        return jsonify({'code': 0, 'status': 'paid', 'team_id': order['team_id']})

    # 先查门房：还没支付就返回当前状态（前端继续轮询）
    from . import payment as _pay
    mf_status = _pay._menfang_get_order_status(order_id)
    if not mf_status['found'] or mf_status['status'] != 'paid':
        return jsonify({'code': 0, 'status': mf_status.get('status', order['status'])})

    # 已支付 → 走统一幂等收尾（建团 + 设 owner + 发积分）
    ok, team_id, err = _finalize_team_purchase(order_id, user_id=user['id'])
    if not ok:
        return jsonify({'code': -1, 'msg': err or '支付处理失败'}), 500

    return jsonify({'code': 0, 'status': 'paid', 'team_id': team_id})


@app.route('/api/internal/team/purchase/paid', methods=['POST'])
def api_internal_team_purchase_paid():
    """门房微信回调成功后主动调用的内部接口（服务间密钥鉴权）。

    门房在团队版支付回调里、更新订单为 paid 后，主动 POST 本接口，
    让官网立刻建团 + 设 owner + 发共享积分，不再依赖用户前端页面轮询。
    请求头带 X-Internal-Key（与门房共享的 MENFANG_INTERNAL_KEY），
    请求体 { order_id: 门房订单号 }。
    """
    import hmac as _hmac
    provided = request.headers.get('X-Internal-Key', '')
    expected = os.environ.get('MENFANG_INTERNAL_KEY', '')
    if not expected or not _hmac.compare_digest(provided, expected):
        return jsonify({'code': -1, 'msg': 'unauthorized'}), 401

    data = request.get_json(silent=True) or {}
    order_id = (data.get('order_id') or '').strip()
    if not order_id:
        return jsonify({'code': -1, 'msg': '缺少 order_id'}), 400

    ok, team_id, err = _finalize_team_purchase(order_id)
    if not ok:
        logger.warning('[团队版] 内部收尾失败 order=%s err=%s', order_id, err)
        return jsonify({'code': -1, 'msg': err or '处理失败'}), 500

    logger.info('[团队版] 门房回调触发收尾成功 order=%s team=%s', order_id, team_id)
    return jsonify({'code': 0, 'status': 'paid', 'team_id': team_id})
