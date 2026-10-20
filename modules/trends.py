"""P3: 技术债趋势分析模块"""
import json
from datetime import datetime, timedelta
from flask import session, request, jsonify
from .db import get_db
from .constants import app, logger, BRAINS_MAP, HTTP_OK, HTTP_BAD_REQUEST, HTTP_UNAUTHORIZED
from .helpers import login_required


def get_user_trends(user_id, days=30, project_tag=None):
    """
    获取用户技术债趋势数据
    """
    db = get_db()

    since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')

    if project_tag:
        rows = db.execute(
            'SELECT * FROM scan_metrics WHERE project_tag=? AND created_at >= ? ORDER BY created_at ASC',
            (project_tag, since)
        ).fetchall()
    else:
        rows = db.execute(
            'SELECT * FROM scan_metrics WHERE user_id=? AND created_at >= ? ORDER BY created_at ASC',
            (user_id, since)
        ).fetchall()

    data_points = []
    for r in rows:
        r = dict(r)
        brain_scores = {}
        try:
            brain_scores = json.loads(r.get('brain_scores_json', '{}') or '{}')
        except Exception:
            pass

        dp = {
            'date': r['created_at'],
            'scan_id': r['scan_id'],
            'score': r['score'],
            'grade': r['grade'],
            'issue_count': r['issue_count'],
            'critical': r['critical_count'],
            'high': r['high_count'],
            'medium': r['medium_count'],
            'low': r['low_count'],
            'brain_scores': brain_scores,
            'file_count': r['file_count'],
            'total_lines': r['total_lines'],
            'duration_ms': r['duration_ms'],
            'scan_mode': r['scan_mode'],
        }
        data_points.append(dp)

    summary = _compute_summary(data_points)

    return {
        'period_days': days,
        'data_points': data_points,
        'summary': summary,
    }


def _compute_summary(data_points):
    """计算趋势摘要"""
    if not data_points:
        return {
            'score_trend': 'no_data',
            'score_change': 0,
            'issue_trend': 'no_data',
            'issue_change': 0,
            'total_scans': 0,
            'avg_score': 0,
            'weakest_brain': None,
            'most_common_severity': 'none',
            'severity_totals': {},
        }

    total_scans = len(data_points)
    scores = [dp['score'] for dp in data_points]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0

    # 分数趋势：比较前半段和后半段
    mid = len(scores) // 2
    if mid > 0 and len(scores) > 1:
        first_half_avg = sum(scores[:mid]) / mid
        second_half_avg = sum(scores[mid:]) / (len(scores) - mid)
        score_change = round(second_half_avg - first_half_avg, 1)
        if score_change > 2:
            score_trend = 'improving'
        elif score_change < -2:
            score_trend = 'declining'
        else:
            score_trend = 'stable'
    else:
        score_change = 0
        score_trend = 'stable'

    # 问题数趋势
    issues = [dp['issue_count'] for dp in data_points]
    if mid > 0 and len(issues) > 1:
        first_half_issues = sum(issues[:mid]) / mid
        second_half_issues = sum(issues[mid:]) / (len(issues) - mid)
        issue_change = round(second_half_issues - first_half_issues, 1)
        if issue_change > 0.5:
            issue_trend = 'increasing'
        elif issue_change < -0.5:
            issue_trend = 'declining'
        else:
            issue_trend = 'stable'
    else:
        issue_change = 0
        issue_trend = 'stable'

    # 最弱引擎
    last_dp = data_points[-1]
    brain_scores = last_dp.get('brain_scores', {})
    weakest_brain = None
    weakest_score = 101
    for bid, bscore in brain_scores.items():
        if bscore < weakest_score:
            weakest_score = bscore
            weakest_brain = bid

    # 最常见问题严重等级
    sev_map = {
        'critical': sum(dp['critical'] for dp in data_points),
        'high': sum(dp['high'] for dp in data_points),
        'medium': sum(dp['medium'] for dp in data_points),
        'low': sum(dp['low'] for dp in data_points),
    }
    most_common = max(sev_map, key=sev_map.get) if any(sev_map.values()) else 'none'

    return {
        'score_trend': score_trend,
        'score_change': score_change,
        'issue_trend': issue_trend,
        'issue_change': issue_change,
        'total_scans': total_scans,
        'avg_score': avg_score,
        'weakest_brain': weakest_brain,
        'weakest_brain_score': weakest_score if weakest_brain else None,
        'weakest_brain_name': BRAINS_MAP.get(int(weakest_brain), {}).get('name', '') if weakest_brain else '',
        'most_common_severity': most_common,
        'severity_totals': sev_map,
    }


# ==================== API 路由 ====================

def register_trends_routes(bp):
    """注册趋势相关 API 路由到 blueprint"""

    @bp.route('/api/trends')
    def api_trends():
        """获取趋势数据"""
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': '未登录'}), HTTP_UNAUTHORIZED

        days = request.args.get('days', 30, type=int)
        days = min(max(days, 7), 365)
        project_tag = request.args.get('project', '')

        data = get_user_trends(user_id, days=days, project_tag=project_tag or None)
        return jsonify({'success': True, **data})

    @bp.route('/api/trends/summary')
    def api_trends_summary():
        """获取趋势摘要"""
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': '未登录'}), HTTP_UNAUTHORIZED

        days = request.args.get('days', 30, type=int)
        days = min(max(days, 7), 365)

        data = get_user_trends(user_id, days=days)
        return jsonify({'success': True, 'summary': data['summary']})

    @bp.route('/api/trends/brain')
    def api_trends_brain():
        """获取单引擎趋势"""
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': '未登录'}), HTTP_UNAUTHORIZED

        brain_id = request.args.get('brain_id', type=int)
        if not brain_id:
            return jsonify({'error': '请指定 brain_id'}), HTTP_BAD_REQUEST

        days = request.args.get('days', 30, type=int)
        days = min(max(days, 7), 365)

        data = get_user_trends(user_id, days=days)

        # 提取单引擎趋势
        brain_data = []
        for dp in data['data_points']:
            bs = dp.get('brain_scores', {})
            score_val = bs.get(str(brain_id))
            brain_data.append({
                'date': dp['date'],
                'score': score_val,
            })

        brain_name = BRAINS_MAP.get(brain_id, {}).get('name', f'Brain {brain_id}')

        return jsonify({
            'success': True,
            'brain_id': brain_id,
            'brain_name': brain_name,
            'data': brain_data,
        })
