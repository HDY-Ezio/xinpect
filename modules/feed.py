"""
P2-05: 静态结果结构化输出（供动态验证 Agent 消费）

提供标准化的扫描结果输出格式，让动态验证 Agent 可以：
1. 获取最近的可疑发现列表
2. 按优先级消费待验证项
3. 回写验证结果（确认为真阳性/误报）

API:
  GET  /api/v1/feed/suspicious      - 获取待验证的可疑发现列表
  POST /api/v1/feed/verify          - 回写验证结果
  GET  /api/v1/scan/<scan_id>/export - 导出单次扫描的结构化结果
"""
import json
from datetime import datetime
from flask import Blueprint, request, jsonify, session as flask_session
from .db import get_db
from .constants import logger

feed_bp = Blueprint('feed', __name__)

# ============================================================
# 标准化输出 Schema
# ============================================================
FINDING_SCHEMA_VERSION = "1.0"

FINDING_SEVERITY_MAP = {
    'critical': 'P0',
    'P0': 'P0',
    'high': 'P1',
    'P1': 'P1',
    'medium': 'P2',
    'P2': 'P2',
    'low': 'P3',
    'P3': 'P3',
    'info': 'P4',
    'P4': 'P4',
}


def format_finding(issue, scan_id, user_id, created_at=''):
    """将单条 issue 格式化为标准 Finding 结构"""
    severity = issue.get('severity', 'medium')
    priority = FINDING_SEVERITY_MAP.get(severity, 'P2')

    return {
        'finding_id': '{}-{}'.format(scan_id[:12], issue.get('rule_id', 'unknown')),
        'scan_id': scan_id,
        'user_id': user_id,
        'version': FINDING_SCHEMA_VERSION,
        'priority': priority,
        'severity': severity,
        'rule_id': issue.get('rule_id', ''),
        'rule_name': issue.get('rule_name', issue.get('rule_id', '')),
        'engine': issue.get('engine', issue.get('brain_id', '')),
        'category': issue.get('category', ''),
        'title': issue.get('title', issue.get('message', '')),
        'description': issue.get('description', ''),
        'file': issue.get('file', issue.get('file_path', '')),
        'line': issue.get('line', issue.get('line_number', 0)),
        'code_snippet': issue.get('code_snippet', issue.get('evidence', '')),
        'suggestion': issue.get('suggestion', issue.get('fix', '')),
        'cwe': issue.get('cwe', ''),
        'confidence': issue.get('confidence', 0.7),
        'scan_created_at': created_at,
        'verification': {
            'status': 'pending',  # pending / confirmed / false_positive / wont_fix
            'verified_by': '',
            'verified_at': '',
            'note': '',
        }
    }


# ============================================================
# API: 获取待验证的可疑发现
# ============================================================
@feed_bp.route('/api/v1/feed/suspicious', methods=['GET'])
def get_suspicious_feed():
    """
    获取待验证的可疑发现列表。
    支持参数:
      - limit: 返回数量（默认 50）
      - priority: 筛选优先级 P0/P1/P2/P3
      - user_id: 指定用户（管理员用）
      - since: ISO 时间，只返回此时间之后的
    认证: X-API-Key header 或 session
    """
    # 认证
    user_id = _get_auth_user_id()
    if not user_id:
        return jsonify({'error': '未认证'}), 401

    limit = request.args.get('limit', 50, type=int)
    priority_filter = request.args.get('priority', '')
    since = request.args.get('since', '')

    db = get_db()

    # 查询最近的扫描结果
    where_parts = ["s.user_id = ?"]
    where_params = [user_id]

    if since:
        where_parts.append("s.created_at >= ?")
        where_params.append(since)

    rows = db.execute(
        "SELECT s.scan_id, s.results, s.created_at, s.score, s.issue_count "
        "FROM scans s "
        "WHERE " + " AND ".join(where_parts) + " "
        "ORDER BY s.id DESC LIMIT ?",
        where_params + [min(limit * 2, 200)]  # 多取一些，因为需要展开 issues
    ).fetchall()

    findings = []
    for row in rows:
        scan_id = row[0]
        try:
            results = json.loads(row[1]) if row[1] else {}
        except json.JSONDecodeError:
            continue

        issues = results.get('issues', [])
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            finding = format_finding(issue, scan_id, user_id, row[2] or '')

            # 优先级过滤
            if priority_filter and finding['priority'] != priority_filter:
                continue

            # 只返回有实际代码位置的发现
            if not finding['file'] and not finding['code_snippet']:
                continue

            findings.append(finding)

            if len(findings) >= limit:
                break

        if len(findings) >= limit:
            break

    # 按优先级排序
    priority_order = {'P0': 0, 'P1': 1, 'P2': 2, 'P3': 3, 'P4': 4}
    findings.sort(key=lambda f: priority_order.get(f['priority'], 9))

    return jsonify({
        'status': 'ok',
        'count': len(findings),
        'findings': findings[:limit],
        'generated_at': datetime.now().isoformat(),
    })


# ============================================================
# API: 导出单次扫描的结构化结果
# ============================================================
@feed_bp.route('/api/v1/scan/<scan_id>/export', methods=['GET'])
def export_scan_results(scan_id):
    """
    导出单次扫描的完整结构化结果。
    认证: X-API-Key header 或 session
    """
    user_id = _get_auth_user_id()
    if not user_id:
        return jsonify({'error': '未认证'}), 401

    db = get_db()
    row = db.execute(
        "SELECT scan_id, user_id, results, score, grade, issue_count, "
        "file_count, total_lines, language, scan_mode, created_at "
        "FROM scans WHERE scan_id = ? AND user_id = ?",
        (scan_id, user_id)
    ).fetchone()

    if not row:
        return jsonify({'error': '扫描记录不存在'}), 404

    try:
        results = json.loads(row[2]) if row[2] else {}
    except json.JSONDecodeError:
        results = {}

    issues = results.get('issues', [])
    findings = [
        format_finding(issue, scan_id, user_id, row[10] or '')
        for issue in issues if isinstance(issue, dict)
    ]

    export = {
        'version': FINDING_SCHEMA_VERSION,
        'scan': {
            'scan_id': row[0],
            'score': row[3],
            'grade': row[4],
            'issue_count': row[5],
            'file_count': row[6],
            'total_lines': row[7],
            'language': row[8],
            'scan_mode': row[9],
            'created_at': row[10],
        },
        'findings': findings,
        'summary': {
            'by_priority': {},
            'by_category': {},
        }
    }

    # 统计
    for f in findings:
        p = f['priority']
        export['summary']['by_priority'][p] = export['summary']['by_priority'].get(p, 0) + 1
        cat = f.get('category', 'unknown')
        export['summary']['by_category'][cat] = export['summary']['by_category'].get(cat, 0) + 1

    return jsonify(export)


# ============================================================
# API: 回写验证结果
# ============================================================
@feed_bp.route('/api/v1/feed/verify', methods=['POST'])
def verify_finding():
    """
    回写动态 Agent 的验证结果。
    请求:
    {
        "finding_id": "abc12345-P1-03",
        "status": "confirmed" | "false_positive" | "wont_fix",
        "note": "确认存在SQL注入",
        "evidence": "..."  // 可选，动态验证的证据
    }
    """
    user_id = _get_auth_user_id()
    if not user_id:
        return jsonify({'error': '未认证'}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': '缺少请求体'}), 400

    finding_id = data.get('finding_id', '').strip()
    status = data.get('status', '').strip()
    note = data.get('note', '').strip()

    if not finding_id or not status:
        return jsonify({'error': '缺少 finding_id 或 status'}), 400

    if status not in ('confirmed', 'false_positive', 'wont_fix'):
        return jsonify({'error': 'status 必须是 confirmed/false_positive/wont_fix'}), 400

    # 解析 finding_id 获取 scan_id 和 rule_id
    parts = finding_id.split('-', 1)
    if len(parts) != 2:
        return jsonify({'error': 'finding_id 格式不正确'}), 400

    scan_id_prefix = parts[0]
    rule_id = parts[1]

    db = get_db()

    # 查找对应的扫描记录
    row = db.execute(
        "SELECT scan_id, results FROM scans WHERE scan_id LIKE ? AND user_id = ?",
        (scan_id_prefix + '%', user_id)
    ).fetchone()

    if not row:
        return jsonify({'error': '找不到对应的扫描记录'}), 404

    # 记录验证结果到 false_positives 表（如果标记为误报）
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if status == 'false_positive':
        try:
            db.execute(
                "INSERT INTO false_positives (user_id, scan_id, rule_id, reason, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, row[0], rule_id, note, now)
            )
            db.commit()
        except Exception as e:
            # 可能已存在，忽略重复
            logger.debug('FP record skip: %s', e)

    return jsonify({
        'status': 'ok',
        'finding_id': finding_id,
        'verification': {
            'status': status,
            'verified_by': 'dynamic_agent',
            'verified_at': now,
            'note': note,
        },
        'message': '验证结果已记录',
    })


# ============================================================
# 辅助函数
# ============================================================
def _get_auth_user_id():
    """从 API Key 或 session 获取 user_id"""
    # 先检查 API Key
    api_key = request.headers.get('X-API-Key', '')
    if api_key:
        from .api import validate_api_key
        user_info = validate_api_key(api_key)
        if user_info:
            return user_info['user_id']

    # 再检查 session
    return flask_session.get('user_id')


# ============================================================
# P2-06: Webhook 回调接口（通知动态 Agent 有新可疑点）
# ============================================================
import threading
try:
    import requests as _requests
except ImportError:
    _requests = None


@feed_bp.route('/api/v1/webhook/register', methods=['POST'])
def register_agent_webhook():
    """
    注册动态 Agent Webhook。
    当有新的高危发现时，自动 POST 到指定 URL。
    请求:
    {
        "url": "https://agent.example.com/webhook",
        "secret": "shared_secret",          # 可选，用于签名验证
        "trigger_priority": "P1",           # P0/P1/P2（默认 P1，即 P0+P1 触发）
        "events": ["new_finding", "scan_complete"]  # 触发事件
    }
    """
    user_id = _get_auth_user_id()
    if not user_id:
        return jsonify({'error': '未认证'}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': '缺少请求体'}), 400

    webhook_url = data.get('url', '').strip()
    if not webhook_url:
        return jsonify({'error': '缺少 url'}), 400

    secret = data.get('secret', '')
    trigger_priority = data.get('trigger_priority', 'P1')
    events = data.get('events', ['new_finding'])

    db = get_db()

    # 存入 alert_rules（复用现有告警系统）
    channel_config = json.dumps({
        'url': webhook_url,
        'secret': secret,
        'type': 'dynamic_agent',
    })
    trigger_json = json.dumps({
        'trigger_priority': trigger_priority,
        'events': events,
    })

    try:
        cursor = db.execute(
            "INSERT INTO alert_rules "
            "(user_id, name, channel, channel_config, trigger_json, is_active) "
            "VALUES (?, ?, 'webhook', ?, ?, 1)",
            (user_id, '动态Agent通知', channel_config, trigger_json)
        )
        db.commit()
        rule_id = cursor.lastrowid
    except Exception as e:
        logger.error('Register webhook error: %s', e)
        return jsonify({'error': '注册失败', 'detail': str(e)}), 500

    return jsonify({
        'status': 'ok',
        'rule_id': rule_id,
        'webhook_url': webhook_url,
        'trigger_priority': trigger_priority,
        'message': 'Webhook 注册成功，有新发现时会通知你的 Agent',
    })


@feed_bp.route('/api/v1/webhook/list', methods=['GET'])
def list_agent_webhooks():
    """列出用户已注册的 Agent Webhook"""
    user_id = _get_auth_user_id()
    if not user_id:
        return jsonify({'error': '未认证'}), 401

    db = get_db()
    rows = db.execute(
        "SELECT id, name, channel_config, trigger_json, is_active, "
        "last_triggered_at, created_at "
        "FROM alert_rules WHERE user_id = ? "
        "AND channel = 'webhook' "
        "AND channel_config LIKE '%dynamic_agent%' "
        "ORDER BY id DESC",
        (user_id,)
    ).fetchall()

    webhooks = []
    for row in rows:
        try:
            config = json.loads(row[2]) if row[2] else {}
        except json.JSONDecodeError:
            config = {}
        try:
            trigger = json.loads(row[3]) if row[3] else {}
        except json.JSONDecodeError:
            trigger = {}

        webhooks.append({
            'id': row[0],
            'name': row[1],
            'url': config.get('url', ''),
            'trigger_priority': trigger.get('trigger_priority', 'P1'),
            'events': trigger.get('events', []),
            'is_active': bool(row[4]),
            'last_triggered_at': row[5],
            'created_at': row[6],
        })

    return jsonify({'status': 'ok', 'webhooks': webhooks})


@feed_bp.route('/api/v1/webhook/<int:rule_id>/delete', methods=['POST'])
def delete_agent_webhook(rule_id):
    """删除 Agent Webhook"""
    user_id = _get_auth_user_id()
    if not user_id:
        return jsonify({'error': '未认证'}), 401

    db = get_db()
    db.execute(
        "DELETE FROM alert_rules WHERE id = ? AND user_id = ?",
        (rule_id, user_id)
    )
    db.commit()
    return jsonify({'status': 'ok', 'message': 'Webhook 已删除'})


@feed_bp.route('/api/v1/webhook/test', methods=['POST'])
def test_agent_webhook():
    """测试 Agent Webhook 连通性"""
    user_id = _get_auth_user_id()
    if not user_id:
        return jsonify({'error': '未认证'}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': '缺少请求体'}), 400

    webhook_url = data.get('url', '').strip()
    secret = data.get('secret', '')
    if not webhook_url:
        return jsonify({'error': '缺少 url'}), 400

    # 发送测试 payload
    payload = {
        'msg_type': 'webhook_test',
        'version': FINDING_SCHEMA_VERSION,
        'timestamp': datetime.now().isoformat(),
        'message': '煋鉴 Webhook 测试 - 如果你收到这条消息，说明连通正常',
        'test_findings': [
            {
                'finding_id': 'test-001-P1-03',
                'priority': 'P1',
                'severity': 'high',
                'rule_id': 'TEST-001',
                'title': '测试发现（Webhook 连通性测试）',
                'file': 'test.py',
                'line': 1,
            }
        ],
    }

    headers = {'Content-Type': 'application/json'}
    if secret:
        import hashlib
        import hmac
        sig = hmac.new(secret.encode(), json.dumps(payload).encode(), hashlib.sha256).hexdigest()
        headers['X-Xinpect-Signature'] = sig

    try:
        if _requests:
            resp = _requests.post(webhook_url, json=payload, headers=headers, timeout=10)
            return jsonify({
                'status': 'ok',
                'http_status': resp.status_code,
                'response': resp.text[:200],
                'message': '测试消息已发送',
            })
        else:
            import urllib.request
            req = urllib.request.Request(
                webhook_url,
                data=json.dumps(payload).encode('utf-8'),
                headers=headers,
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return jsonify({
                    'status': 'ok',
                    'http_status': resp.status,
                    'message': '测试消息已发送',
                })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)[:300],
            'message': 'Webhook 发送失败，请检查 URL 是否可达',
        }), 400


def notify_agent_webhook(user_id, scan_id, findings, db):
    """
    触发 Agent Webhook 通知（在扫描完成后调用）。
    findings: P2-05 格式的 Finding 列表
    """
    rows = db.execute(
        "SELECT * FROM alert_rules WHERE user_id = ? AND is_active = 1 "
        "AND channel = 'webhook' AND channel_config LIKE '%dynamic_agent%'",
        (user_id,)
    ).fetchall()

    for rule in rows:
        rule = dict(rule)
        try:
            config = json.loads(rule.get('channel_config', '{}'))
        except json.JSONDecodeError:
            continue

        if config.get('type') != 'dynamic_agent':
            continue

        webhook_url = config.get('url', '')
        secret = config.get('secret', '')
        if not webhook_url:
            continue

        # 按 trigger_priority 过滤
        try:
            trigger = json.loads(rule.get('trigger_json', '{}'))
        except json.JSONDecodeError:
            trigger = {}
        trigger_priority = trigger.get('trigger_priority', 'P1')
        priority_threshold = {'P0': 0, 'P1': 1, 'P2': 2, 'P3': 3}
        threshold = priority_threshold.get(trigger_priority, 1)

        # 只发送达到阈值优先级的发现
        filtered = [
            f for f in findings
            if priority_threshold.get(f.get('priority', 'P4'), 4) <= threshold
        ]
        if not filtered:
            continue

        # 构建 payload
        payload = {
            'msg_type': 'new_findings',
            'version': FINDING_SCHEMA_VERSION,
            'scan_id': scan_id,
            'timestamp': datetime.now().isoformat(),
            'finding_count': len(filtered),
            'findings': filtered,
        }

        headers = {'Content-Type': 'application/json'}
        if secret:
            import hashlib
            import hmac
            sig = hmac.new(
                secret.encode(),
                json.dumps(payload).encode(),
                hashlib.sha256
            ).hexdigest()
            headers['X-Xinpect-Signature'] = sig

        # 异步发送
        def _send(url, p, h, rid):
            try:
                if _requests:
                    resp = _requests.post(url, json=p, headers=h, timeout=10)
                    status = 'sent' if resp.status_code < 400 else 'failed'
                    resp_text = resp.text[:500]
                else:
                    import urllib.request
                    req = urllib.request.Request(
                        url, data=json.dumps(p).encode('utf-8'),
                        headers=h, method='POST'
                    )
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        status = 'sent'
                        resp_text = str(resp.status)
            except Exception as e:
                status = 'failed'
                resp_text = str(e)[:500]

            # 记录历史
            try:
                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                db2 = get_db()
                db2.execute(
                    "INSERT INTO alert_history (rule_id, user_id, scan_id, trigger_details, delivery_status, delivery_response) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (rid, user_id, scan_id, json.dumps({'finding_count': len(filtered)}), status, resp_text)
                )
                db2.execute(
                    "UPDATE alert_rules SET last_triggered_at = ? WHERE id = ?",
                    (now, rid)
                )
                db2.commit()
            except Exception:
                pass

        threading.Thread(target=_send, args=(webhook_url, payload, headers, rule['id']), daemon=True).start()

