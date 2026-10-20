"""扫描结果对比（Diff）模块"""
import json
from flask import session, request, jsonify
from .db import get_db
from .constants import app, logger, HTTP_OK, HTTP_BAD_REQUEST, HTTP_UNAUTHORIZED, HTTP_NOT_FOUND


def _build_issue_index(issues):
    """以 check_id + file 为 key 建立索引，忽略行号变化"""
    index = {}
    for issue in issues:
        key = f"{issue.get('check_id', '')}:{issue.get('file', '')}"
        base_key = key
        counter = 1
        while key in index:
            key = f"{base_key}#{counter}"
            counter += 1
        index[key] = issue
    return index


def _format_issue(issue):
    """格式化单个 issue 用于 diff 输出"""
    return {
        'check_id': issue.get('check_id', ''),
        'title': issue.get('name', issue.get('title', '')),
        'file': issue.get('file', ''),
        'line': issue.get('line', 0),
        'severity': issue.get('severity', 'medium'),
        'message': issue.get('message', issue.get('description', '')),
        'brain_id': issue.get('brain_id', ''),
        'rule_id': issue.get('rule_id', issue.get('check_id', '')),
    }


def compare_scans(scan_a_result_json, scan_b_result_json, score_a, score_b):
    """对比两次扫描结果"""
    data_a = json.loads(scan_a_result_json) if isinstance(scan_a_result_json, str) else scan_a_result_json
    data_b = json.loads(scan_b_result_json) if isinstance(scan_b_result_json, str) else scan_b_result_json

    issues_a = data_a.get('issues', [])
    issues_b = data_b.get('issues', [])

    index_a = _build_issue_index(issues_a)
    index_b = _build_issue_index(issues_b)

    keys_a = set(index_a.keys())
    keys_b = set(index_b.keys())

    return {
        'summary': {
            'total_new': len(keys_b - keys_a),
            'total_fixed': len(keys_a - keys_b),
            'total_remaining': len(keys_a & keys_b),
            'score_change': (score_b or 0) - (score_a or 0),
            'issue_change': len(issues_b) - len(issues_a),
        },
        'new_issues': [_format_issue(index_b[k]) for k in sorted(keys_b - keys_a)],
        'fixed_issues': [_format_issue(index_a[k]) for k in sorted(keys_a - keys_b)],
        'remaining_issues': [_format_issue(index_b[k]) for k in sorted(keys_a & keys_b)],
    }


def get_user_scan_list(user_id, limit=50):
    """获取用户的扫描列表（用于选择器）"""
    db = get_db()
    rows = db.execute(
        'SELECT scan_id, title, score, grade, issue_count, created_at '
        'FROM scans WHERE user_id=? ORDER BY id DESC LIMIT ?',
        (user_id, limit)
    ).fetchall()
    return [dict(r) for r in rows]


# ==================== API 路由（拆分为独立函数） ====================

def _api_scan_diff():
    """对比两次扫描"""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': '未登录'}), HTTP_UNAUTHORIZED

    scan_id_a = request.args.get('a', '').strip()
    scan_id_b = request.args.get('b', '').strip()

    if not scan_id_a or not scan_id_b:
        return jsonify({'error': '请提供两个 scan_id（a 和 b）'}), HTTP_BAD_REQUEST

    db = get_db()
    scan_a = db.execute(
        'SELECT scan_id, score, grade, issue_count, results, created_at, title FROM scans WHERE scan_id=? AND user_id=?',
        (scan_id_a, user_id)
    ).fetchone()
    scan_b = db.execute(
        'SELECT scan_id, score, grade, issue_count, results, created_at, title FROM scans WHERE scan_id=? AND user_id=?',
        (scan_id_b, user_id)
    ).fetchone()

    if not scan_a or not scan_b:
        return jsonify({'error': '扫描记录不存在或无权访问'}), HTTP_NOT_FOUND

    diff = compare_scans(scan_a['results'], scan_b['results'], scan_a['score'], scan_b['score'])

    return jsonify({
        'success': True,
        'scan_a': _scan_summary(scan_a),
        'scan_b': _scan_summary(scan_b),
        'diff': diff,
    })


def _scan_summary(scan):
    """提取扫描摘要字段"""
    return {
        'scan_id': scan['scan_id'],
        'title': scan['title'],
        'score': scan['score'],
        'grade': scan['grade'],
        'issue_count': scan['issue_count'],
        'created_at': scan['created_at'],
    }


def _api_scan_prev_diff(scan_id):
    """获取该扫描与上一次的 diff"""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': '未登录'}), HTTP_UNAUTHORIZED

    db = get_db()
    current = db.execute(
        'SELECT id, scan_id, score, grade, issue_count, results, created_at, title FROM scans WHERE scan_id=? AND user_id=?',
        (scan_id, user_id)
    ).fetchone()

    if not current:
        return jsonify({'error': '扫描记录不存在'}), HTTP_NOT_FOUND

    prev = db.execute(
        'SELECT scan_id, score, grade, issue_count, results, created_at, title FROM scans '
        'WHERE user_id=? AND id < ? ORDER BY id DESC LIMIT 1',
        (user_id, current['id'])
    ).fetchone()

    if not prev:
        return jsonify({
            'success': True,
            'message': '没有更早的扫描记录可供对比',
            'scan_id': scan_id,
        })

    diff = compare_scans(prev['results'], current['results'], prev['score'], current['score'])

    return jsonify({
        'success': True,
        'scan_a': _scan_summary(prev),
        'scan_b': _scan_summary(current),
        'diff': diff,
    })


def _api_scan_list():
    """获取用户扫描列表（用于对比选择器）"""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': '未登录'}), HTTP_UNAUTHORIZED

    limit = min(max(request.args.get('limit', 50, type=int), 5), 200)
    scans = get_user_scan_list(user_id, limit)
    return jsonify({'success': True, 'scans': scans})


# ==================== 路由注册入口 ====================

def register_diff_routes(bp):
    """注册 diff 相关 API 路由"""
    bp.add_url_rule('/api/scan/diff', 'api_scan_diff', _api_scan_diff, methods=['GET'])
    bp.add_url_rule('/api/scan/<scan_id>/prev', 'api_scan_prev_diff', _api_scan_prev_diff, methods=['GET'])
    bp.add_url_rule('/api/scan/list', 'api_scan_list', _api_scan_list, methods=['GET'])
