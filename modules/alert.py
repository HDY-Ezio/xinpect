"""P5: 高危问题告警模块"""
import json
import time
import threading
from datetime import datetime
from flask import session, request, jsonify
from .db import get_db
from .constants import app, logger, HTTP_OK, HTTP_BAD_REQUEST, HTTP_UNAUTHORIZED, HTTP_NOT_FOUND


# ==================== 核心逻辑 ====================

def evaluate_alert_rules(scan_context, user_id, db):
    """评估用户的所有告警规则，返回需要触发的规则列表"""
    rules = db.execute(
        'SELECT * FROM alert_rules WHERE user_id = ? AND is_active = 1',
        (user_id,)
    ).fetchall()

    triggered = []
    for rule in rules:
        rule = dict(rule)
        if _is_in_cooldown(rule):
            continue
        trigger = _parse_trigger_json(rule)
        if _evaluate_trigger(trigger, scan_context):
            triggered.append(rule)
    return triggered


def _is_in_cooldown(rule):
    """检查规则是否在冷却期内"""
    if not rule.get('last_triggered_at'):
        return False
    try:
        last = datetime.strptime(rule['last_triggered_at'], '%Y-%m-%d %H:%M:%S')
        cooldown = rule.get('cooldown_minutes', 60)
        return (datetime.now() - last).total_seconds() < cooldown * 60
    except (ValueError, TypeError):
        return False


def _parse_trigger_json(rule):
    """解析规则的 trigger_json"""
    trigger_json = rule.get('trigger_json', '{}')
    if isinstance(trigger_json, str):
        try:
            return json.loads(trigger_json)
        except Exception:
            return {}
    return trigger_json


def _evaluate_trigger(trigger, scan_context):
    """评估触发条件"""
    conditions = trigger.get('conditions', [])
    if not conditions:
        conditions = [{'field': 'severity_counts.critical', 'operator': '>=', 'value': 1}]

    logic = trigger.get('logic', 'any')
    results = []
    for cond in conditions:
        actual = _get_field_value(cond['field'], scan_context)
        results.append(_compare(actual, cond.get('operator', '>='), cond.get('value', 0)))

    if logic == 'all':
        return all(results)
    return any(results)


def _get_field_value(field, data):
    """从嵌套字典中获取值"""
    keys = field.split('.')
    val = data
    for k in keys:
        if isinstance(val, dict):
            val = val.get(k)
        else:
            return None
    return val


def _compare(actual, operator, expected):
    """比较运算"""
    if actual is None:
        return False
    try:
        ops = {
            '>=': lambda a, b: a >= b,
            '<=': lambda a, b: a <= b,
            '==': lambda a, b: a == b,
            '!=': lambda a, b: a != b,
            '>': lambda a, b: a > b,
            '<': lambda a, b: a < b,
        }
        return ops.get(operator, lambda a, b: False)(actual, expected)
    except (TypeError, ValueError):
        return False


def deliver_alert(rule, scan_context, scan_id, db):
    """发送告警通知"""
    channel = rule.get('channel', 'webhook')
    config = _parse_channel_config(rule)

    status = 'pending'
    response_text = ''

    if channel == 'webhook':
        status, response_text = _deliver_webhook(config, rule, scan_context, scan_id)
    elif channel == 'email':
        status = 'pending'
        response_text = 'Email delivery not yet implemented'

    _record_alert_history(rule, scan_context, scan_id, db, (status, response_text))
    return status, response_text


def _parse_channel_config(rule):
    """解析 channel_config"""
    channel_config = rule.get('channel_config', '{}')
    if isinstance(channel_config, str):
        try:
            return json.loads(channel_config)
        except Exception:
            return {}
    return channel_config


def _deliver_webhook(config, rule, scan_context, scan_id):
    """通过 Webhook 发送告警"""
    webhook_url = config.get('url', '')
    if not webhook_url:
        return 'failed', 'Webhook URL is empty'

    payload = _build_webhook_payload(rule, scan_context, scan_id)

    try:
        import urllib.request
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return 'sent', f"HTTP {resp.status}"
    except Exception as e:
        return 'failed', str(e)[:500]


def _build_webhook_payload(rule, scan_context, scan_id):
    """构建 Webhook 请求体"""
    return {
        "msg_type": "alert",
        "rule_name": rule.get('name', '高危告警'),
        "scan_id": scan_id,
        "score": scan_context.get('score'),
        "grade": scan_context.get('grade'),
        "total_issues": scan_context.get('total_issues', 0),
        "severity_counts": scan_context.get('severity_counts', {}),
        "timestamp": datetime.now().isoformat(),
        "message": f"⚠️ 高危告警：扫描得分 {scan_context.get('score')}，"
                   f"发现 {scan_context.get('severity_counts', {}).get('critical', 0)} 个严重问题",
        "report_url": f"https://xinpect.xingwangzhineng.com/report/{scan_id}",
    }


def _record_alert_history(rule, scan_context, scan_id, db, delivery_result):
    """记录告警历史。delivery_result: (status, response_text)"""
    status, response_text = delivery_result
    try:
        db.execute('''
            INSERT INTO alert_history (rule_id, user_id, scan_id, trigger_details, delivery_status, delivery_response)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            rule.get('id', 0), rule.get('user_id', 0), scan_id,
            json.dumps(scan_context.get('severity_counts', {}), ensure_ascii=False),
            status, response_text,
        ))
        db.execute(
            'UPDATE alert_rules SET last_triggered_at = ? WHERE id = ?',
            (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), rule.get('id'))
        )
        db.commit()
    except Exception as e:
        logger.warning('P5: Failed to record alert history: %s', e)


def check_alerts_async(user_id, scan_context, scan_id):
    """异步检查并发送告警（在线程中调用）"""
    try:
        import sqlite3
        db_conn = sqlite3.connect('/opt/xinpect-website/xinpect.db')
        db_conn.row_factory = sqlite3.Row

        triggered = evaluate_alert_rules(scan_context, user_id, db_conn)
        for rule in triggered:
            try:
                deliver_alert(dict(rule), scan_context, scan_id, db_conn)
            except Exception as e:
                logger.error('P5: Alert delivery failed for rule %s: %s', rule.get('id'), e)
        db_conn.close()
    except Exception as e:
        logger.error('P5: Alert evaluation failed: %s', e)


# ==================== API 路由（拆分为独立函数） ====================

def _api_get_alerts():
    """获取告警规则列表"""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': '未登录'}), HTTP_UNAUTHORIZED

    db = get_db()
    rows = db.execute(
        'SELECT * FROM alert_rules WHERE user_id = ? ORDER BY id DESC',
        (user_id,)
    ).fetchall()

    rules = []
    for r in rows:
        r = dict(r)
        try:
            r['trigger_json'] = json.loads(r.get('trigger_json', '{}') or '{}')
        except Exception:
            r['trigger_json'] = {}
        try:
            r['channel_config'] = json.loads(r.get('channel_config', '{}') or '{}')
        except Exception:
            r['channel_config'] = {}
        rules.append(r)
    return jsonify({'success': True, 'rules': rules})


def _api_create_alert():
    """创建告警规则"""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': '未登录'}), HTTP_UNAUTHORIZED

    data = request.get_json(silent=True) or {}
    name = data.get('name', '高危告警')
    channel = data.get('channel', 'webhook')
    channel_config = data.get('channel_config', {})
    trigger = data.get('trigger', {
        'conditions': [{'field': 'severity_counts.critical', 'operator': '>=', 'value': 1}],
        'logic': 'any'
    })
    cooldown = data.get('cooldown_minutes', 60)

    if channel not in ('webhook', 'email'):
        return jsonify({'error': '不支持的通知渠道'}), HTTP_BAD_REQUEST
    if channel == 'webhook' and not channel_config.get('url'):
        return jsonify({'error': '请填写 Webhook URL'}), HTTP_BAD_REQUEST

    db = get_db()
    db.execute('''
        INSERT INTO alert_rules (user_id, name, channel, channel_config, trigger_json, cooldown_minutes, is_active)
        VALUES (?, ?, ?, ?, ?, ?, 1)
    ''', (
        user_id, name, channel,
        json.dumps(channel_config, ensure_ascii=False),
        json.dumps(trigger, ensure_ascii=False),
        cooldown,
    ))
    db.commit()
    return jsonify({'success': True})


def _api_update_alert(rule_id):
    """更新告警规则"""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': '未登录'}), HTTP_UNAUTHORIZED

    db = get_db()
    rule = db.execute(
        'SELECT * FROM alert_rules WHERE id = ? AND user_id = ?', (rule_id, user_id)
    ).fetchone()
    if not rule:
        return jsonify({'error': '规则不存在'}), HTTP_NOT_FOUND

    data = request.get_json(silent=True) or {}
    name = data.get('name', rule['name'])
    channel = data.get('channel', rule['channel'])
    cooldown = data.get('cooldown_minutes', rule['cooldown_minutes'])
    is_active = data.get('is_active', rule['is_active'])

    updates = ['name=?', 'channel=?', 'cooldown_minutes=?', 'is_active=?']
    params = [name, channel, cooldown, is_active]

    channel_config = data.get('channel_config')
    if channel_config is not None:
        updates.append('channel_config=?')
        params.append(json.dumps(channel_config, ensure_ascii=False))
    trigger = data.get('trigger')
    if trigger is not None:
        updates.append('trigger_json=?')
        params.append(json.dumps(trigger, ensure_ascii=False))

    # 安全加固：白名单校验字段名
    ALLOWED_FIELDS = {"name", "channel", "channel_config", "trigger_json", "cooldown_minutes", "is_active"}
    for u_str in updates:
        uname = u_str.split('=')[0]
        if uname not in ALLOWED_FIELDS:
            return jsonify({'success': False, 'error': f'非法字段名: {uname}'}), 400
    params.append(rule_id)
    db.execute(f'UPDATE alert_rules SET {", ".join(updates)} WHERE id = ?', params)
    db.commit()
    return jsonify({'success': True})


def _api_delete_alert(rule_id):
    """删除告警规则"""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': '未登录'}), HTTP_UNAUTHORIZED

    db = get_db()
    rule = db.execute(
        'SELECT id FROM alert_rules WHERE id = ? AND user_id = ?', (rule_id, user_id)
    ).fetchone()
    if not rule:
        return jsonify({'error': '规则不存在'}), 404

    db.execute('DELETE FROM alert_history WHERE rule_id = ?', (rule_id,))
    db.execute('DELETE FROM alert_rules WHERE id = ?', (rule_id,))
    db.commit()
    return jsonify({'success': True})


def _api_test_alert(rule_id):
    """发送测试告警"""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': '未登录'}), HTTP_UNAUTHORIZED

    db = get_db()
    rule = db.execute(
        'SELECT * FROM alert_rules WHERE id = ? AND user_id = ?', (rule_id, user_id)
    ).fetchone()
    if not rule:
        return jsonify({'error': '规则不存在'}), HTTP_NOT_FOUND

    test_context = {
        'score': 42, 'grade': 'C', 'total_issues': 15,
        'severity_counts': {'critical': 3, 'high': 5, 'medium': 4, 'low': 3},
    }
    status, response = deliver_alert(
        dict(rule), test_context,
        'test_scan_' + datetime.now().strftime('%Y%m%d%H%M%S'), db,
    )
    return jsonify({'success': True, 'delivery_status': status, 'delivery_response': response})


def _api_alert_history():
    """告警历史"""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': '未登录'}), HTTP_UNAUTHORIZED

    db = get_db()
    rows = db.execute('''
        SELECT h.*, r.name as rule_name
        FROM alert_history h
        LEFT JOIN alert_rules r ON h.rule_id = r.id
        WHERE h.user_id = ?
        ORDER BY h.id DESC LIMIT 50
    ''', (user_id,)).fetchall()

    history = []
    for r in rows:
        r = dict(r)
        try:
            r['trigger_details'] = json.loads(r.get('trigger_details', '{}') or '{}')
        except Exception:
            pass
        history.append(r)
    return jsonify({'success': True, 'history': history})


# ==================== 路由注册入口 ====================

def register_alert_routes(bp):
    """注册告警相关 API 路由"""
    bp.add_url_rule('/api/alerts', 'api_get_alerts', _api_get_alerts, methods=['GET'])
    bp.add_url_rule('/api/alerts', 'api_create_alert', _api_create_alert, methods=['POST'])
    bp.add_url_rule('/api/alerts/<int:rule_id>', 'api_update_alert', _api_update_alert, methods=['PUT'])
    bp.add_url_rule('/api/alerts/<int:rule_id>', 'api_delete_alert', _api_delete_alert, methods=['DELETE'])
    bp.add_url_rule('/api/alerts/<int:rule_id>/test', 'api_test_alert', _api_test_alert, methods=['POST'])
    bp.add_url_rule('/api/alerts/history', 'api_alert_history', _api_alert_history, methods=['GET'])
