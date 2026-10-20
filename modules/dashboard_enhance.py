"""
P2-03: 看板增强 API（趋势/来源分布/合规状态）
"""
import json
from datetime import datetime
from flask import Blueprint, request, jsonify, session as flask_session
from .db import get_db
from .constants import logger


def register_dashboard_enhancement_routes(bp):
    """注册看板增强路由到 scan_bp"""

    @bp.route('/api/dashboard/summary')
    def api_dashboard_summary():
        """
        看板增强数据：分数趋势 + 来源分布 + 合规状态
        支持 ?days=7|30&project_tag=xxx 参数
        """
        if not flask_session.get('user_id'):
            return jsonify({'error': '未登录'}), 401

        user_id = flask_session['user_id']
        days = request.args.get('days', 30, type=int)
        project_tag = request.args.get('project_tag', '')

        db = get_db()

        # 1. 分数趋势（按天聚合）
        if project_tag:
            trend_rows = db.execute(
                "SELECT date(created_at) as d, "
                "  AVG(score) as avg_score, "
                "  MIN(score) as min_score, "
                "  MAX(score) as max_score, "
                "  COUNT(*) as scan_count, "
                "  SUM(issue_count) as total_issues "
                "FROM scan_metrics "
                "WHERE user_id = ? "
                "  AND created_at >= date('now', ? || ' days') "
                "  AND project_tag = ? "
                "GROUP BY date(created_at) "
                "ORDER BY d",
                (user_id, -days, project_tag)
            ).fetchall()
        else:
            trend_rows = db.execute(
                "SELECT date(created_at) as d, "
                "  AVG(score) as avg_score, "
                "  MIN(score) as min_score, "
                "  MAX(score) as max_score, "
                "  COUNT(*) as scan_count, "
                "  SUM(issue_count) as total_issues "
                "FROM scan_metrics "
                "WHERE user_id = ? "
                "  AND created_at >= date('now', ? || ' days') "
                "GROUP BY date(created_at) "
                "ORDER BY d",
                (user_id, -days)
            ).fetchall()

        trend = []
        for row in trend_rows:
            trend.append({
                'date': row[0],
                'avg_score': round(row[1] or 0, 1),
                'min_score': row[2] or 0,
                'max_score': row[3] or 0,
                'scan_count': row[4] or 0,
                'total_issues': row[5] or 0,
            })

        # 2. 来源分布
        source_rows = db.execute(
            "SELECT source, COUNT(*) as cnt, AVG(score) as avg_score "
            "FROM scans "
            "WHERE user_id = ? AND created_at >= date('now', ? || ' days') "
            "GROUP BY source ORDER BY cnt DESC",
            (user_id, -days)
        ).fetchall()

        source_labels = {
            'upload': '网页上传', 'api': 'API调用', 'cli': 'CLI上传',
            'ci': 'CI/CD', 'github': 'GitHub',
        }
        sources = []
        for row in source_rows:
            sources.append({
                'source': row[0] or 'unknown',
                'label': source_labels.get(row[0], row[0] or '未知'),
                'count': row[1],
                'avg_score': round(row[2] or 0, 1),
            })

        # 3. 合规状态
        latest = db.execute(
            "SELECT score, grade, issue_count FROM scan_metrics "
            "WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,)
        ).fetchone()

        week_avg_row = db.execute(
            "SELECT AVG(score) FROM scan_metrics "
            "WHERE user_id = ? AND created_at >= date('now', '-7 days')",
            (user_id,)
        ).fetchone()

        week_avg = round(week_avg_row[0], 1) if week_avg_row and week_avg_row[0] else None
        latest_score = latest[0] if latest else None
        latest_grade = latest[1] if latest else None
        latest_issues = latest[2] if latest else 0

        status = 'pass'
        if week_avg is not None:
            if week_avg < 60:
                status = 'fail'
            elif week_avg < 80:
                status = 'warn'

        compliance = {
            'latest_score': latest_score,
            'latest_grade': latest_grade,
            'latest_issues': latest_issues,
            'week_avg': week_avg,
            'status': status,
        }

        # 4. 项目标签列表
        tag_rows = db.execute(
            "SELECT DISTINCT ci_repo FROM scans "
            "WHERE user_id = ? AND ci_repo IS NOT NULL AND ci_repo != '' "
            "ORDER BY created_at DESC LIMIT 20",
            (user_id,)
        ).fetchall()
        project_tags = [row[0] for row in tag_rows]

        return jsonify({
            'status': 'ok',
            'trend': trend,
            'sources': sources,
            'compliance': compliance,
            'project_tags': project_tags,
            'days': days,
        })
