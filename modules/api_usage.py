"""
煋鉴 API配额管理与调用统计模块
功能：配额查询、调用记录、限流日志、统计分析
"""
import logging
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, session as flask_session
from functools import wraps

api_usage_bp = Blueprint("api_usage", __name__)
logger = logging.getLogger("xinpect.api_usage")

# ============================================================
# 配额配置（按VIP等级）
# ============================================================
QUOTA_CONFIG = {
    'free': {'daily_limit': 10, 'label': '免费用户'},
    'registered': {'daily_limit': 50, 'label': '注册用户'},
    'monthly': {'daily_limit': 100, 'label': '月卡用户'},
    'quarterly': {'daily_limit': 200, 'label': '季卡用户'},
    'yearly': {'daily_limit': 500, 'label': '年卡用户'},
    'enterprise': {'daily_limit': -1, 'label': '企业版'},  # -1表示无限制
}


def get_user_quota_tier(user):
    """根据用户信息判断配额等级"""
    if not user:
        return 'free'
    
    is_vip = user.get('is_vip', 0) if isinstance(user, dict) else getattr(user, 'is_vip', 0)
    vip_type = user.get('vip_type', '') if isinstance(user, dict) else getattr(user, 'vip_type', '')
    
    if is_vip:
        if vip_type in ('enterprise', '企业版'):
            return 'enterprise'
        elif vip_type in ('yearly', '年卡'):
            return 'yearly'
        elif vip_type in ('quarterly', '季卡'):
            return 'quarterly'
        elif vip_type in ('monthly', '月卡'):
            return 'monthly'
        else:
            return 'monthly'  # 默认VIP为月卡
    else:
        # 检查是否已注册（有登录记录）
        has_account = user.get('id', 0) if isinstance(user, dict) else getattr(user, 'id', 0)
        if has_account:
            return 'registered'
        return 'free'


def get_daily_limit(tier):
    """获取每日配额上限"""
    config = QUOTA_CONFIG.get(tier, QUOTA_CONFIG['free'])
    return config['daily_limit']


# ============================================================
# 数据库操作函数
# ============================================================

def record_api_call(db, user_id, endpoint, method='GET', status_code=200):
    """记录一次API调用（异步批量写入用）"""
    try:
        db.execute(
            "INSERT INTO api_calls (user_id, endpoint, method, status_code, called_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            (user_id, endpoint, method, status_code)
        )
        db.commit()
    except Exception as e:
        logger.error(f"记录API调用失败: {e}")


def record_rate_limit(db, user_id, endpoint, reason):
    """记录限流事件"""
    try:
        db.execute(
            "INSERT INTO rate_limit_logs (user_id, endpoint, reason, limited_at) "
            "VALUES (?, ?, ?, datetime('now'))",
            (user_id, endpoint, reason)
        )
        db.commit()
    except Exception as e:
        logger.error(f"记录限流事件失败: {e}")


def get_today_usage(db, user_id):
    """获取今日调用次数"""
    row = db.execute(
        "SELECT COUNT(*) FROM api_calls "
        "WHERE user_id = ? AND date(called_at) = date('now')",
        (user_id,)
    ).fetchone()
    return row[0] if row else 0


def get_quota_info(db, user_id, user):
    """获取配额信息"""
    tier = get_user_quota_tier(user)
    daily_limit = get_daily_limit(tier)
    used_today = get_today_usage(db, user_id)
    
    # 计算重置时间（距离午夜）
    now = datetime.now()
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    hours_until_reset = (tomorrow - now).total_seconds() / 3600
    
    remaining = max(0, daily_limit - used_today) if daily_limit > 0 else -1
    
    return {
        'tier': tier,
        'tier_label': QUOTA_CONFIG[tier]['label'],
        'daily_limit': daily_limit,
        'used_today': used_today,
        'remaining': remaining,
        'unlimited': daily_limit < 0,
        'usage_percent': round((used_today / daily_limit * 100), 1) if daily_limit > 0 else 0,
        'hours_until_reset': round(hours_until_reset, 1),
        'reset_at': tomorrow.strftime('%Y-%m-%d %H:%M:%S'),
    }


def get_hourly_distribution(db, user_id):
    """获取今日按小时分布的调用统计"""
    rows = db.execute(
        "SELECT strftime('%H', called_at) as hour, COUNT(*) as cnt "
        "FROM api_calls "
        "WHERE user_id = ? AND date(called_at) = date('now') "
        "GROUP BY hour ORDER BY hour",
        (user_id,)
    ).fetchall()
    
    result = {f"{int(r[0]):02d}:00": r[1] for r in rows}
    # 补全0-23小时
    for h in range(24):
        key = f"{h:02d}:00"
        if key not in result:
            result[key] = 0
    return dict(sorted(result.items()))


def get_daily_trend(db, user_id, days=7):
    """获取最近N天按天分布的调用趋势"""
    rows = db.execute(
        "SELECT date(called_at) as d, COUNT(*) as cnt "
        "FROM api_calls "
        "WHERE user_id = ? AND called_at >= datetime('now', ? || ' days') "
        "GROUP BY d ORDER BY d",
        (user_id, -days)
    ).fetchall()
    
    result = {}
    for i in range(days):
        date_str = (datetime.now() - timedelta(days=days - 1 - i)).strftime('%Y-%m-%d')
        result[date_str] = 0
    for r in rows:
        result[r[0]] = r[1]
    return result


def get_endpoint_distribution(db, user_id, days=7):
    """获取调用类型分布"""
    rows = db.execute(
        "SELECT endpoint, COUNT(*) as cnt "
        "FROM api_calls "
        "WHERE user_id = ? AND called_at >= datetime('now', ? || ' days') "
        "GROUP BY endpoint ORDER BY cnt DESC LIMIT 10",
        (user_id, -days)
    ).fetchall()
    
    return [{'endpoint': r[0], 'count': r[1]} for r in rows]


def get_rate_limit_history(db, user_id, limit=20):
    """获取限流记录"""
    rows = db.execute(
        "SELECT endpoint, reason, limited_at "
        "FROM rate_limit_logs "
        "WHERE user_id = ? "
        "ORDER BY limited_at DESC LIMIT ?",
        (user_id, limit)
    ).fetchall()
    
    return [{'endpoint': r[0], 'reason': r[1], 'time': r[2]} for r in rows]


# ============================================================
# 装饰器：记录API调用
# ============================================================

def track_api_call(f):
    """装饰器：自动记录API调用"""
    @wraps(f)
    def decorated(*args, **kwargs):
        from .db import get_db
        result = f(*args, **kwargs)
        
        # 异步记录（不阻塞主流程）
        try:
            user_id = flask_session.get('user_id')
            if user_id:
                db = get_db()
                record_api_call(db, user_id, request.path, request.method)
        except Exception as e:
            logger.warning(f"API调用记录失败(不影响主流程): {e}")
        
        return result
    return decorated


def check_quota(f):
    """装饰器：检查配额是否超限"""
    @wraps(f)
    def decorated(*args, **kwargs):
        from .db import get_db
        from .helpers import get_current_user
        
        user_id = flask_session.get('user_id')
        if not user_id:
            return f(*args, **kwargs)  # 未登录不检查
        
        user = get_current_user()
        db = get_db()
        quota = get_quota_info(db, user_id, user)
        
        if not quota['unlimited'] and quota['remaining'] <= 0:
            # 记录限流
            record_rate_limit(db, user_id, request.path, '每日配额已用尽')
            
            return jsonify({
                'error': 'API调用频率超限',
                'message': f"您今日已使用{quota['used_today']}/{quota['daily_limit']}次API调用配额，请明日再试或升级配额",
                'quota': {
                    'limit': quota['daily_limit'],
                    'used': quota['used_today'],
                    'remaining': 0,
                    'reset_at': quota['reset_at'],
                },
                'upgrade_url': '/pricing',
            }), 429
        
        return f(*args, **kwargs)
    return decorated


# ============================================================
# API路由注册
# ============================================================


# 直接注册路由到blueprint

def register_api_usage_routes(bp):
    """注册API配额相关路由"""
    
    @bp.route('/api/user/api-usage/quota')
    def api_usage_quota():
        """获取当前配额信息"""
        from .db import get_db
        from .helpers import get_current_user
        
        user_id = flask_session.get('user_id')
        if not user_id:
            return jsonify({'error': '未登录'}), 401
        
        user = get_current_user()
        db = get_db()
        quota = get_quota_info(db, user_id, user)
        
        return jsonify({
            'success': True,
            'data': quota,
        })
    
    @bp.route('/api/user/api-usage/today')
    def api_usage_today():
        """获取今日调用统计"""
        from .db import get_db
        
        user_id = flask_session.get('user_id')
        if not user_id:
            return jsonify({'error': '未登录'}), 401
        
        db = get_db()
        hourly = get_hourly_distribution(db, user_id)
        total = sum(hourly.values())
        
        return jsonify({
            'success': True,
            'data': {
                'total': total,
                'hourly': hourly,
            }
        })
    
    @bp.route('/api/user/api-usage/week')
    def api_usage_week():
        """获取本周调用趋势"""
        from .db import get_db
        
        user_id = flask_session.get('user_id')
        if not user_id:
            return jsonify({'error': '未登录'}), 401
        
        db = get_db()
        trend = get_daily_trend(db, user_id, days=7)
        
        return jsonify({
            'success': True,
            'data': {
                'trend': trend,
                'total': sum(trend.values()),
            }
        })
    
    @bp.route('/api/user/api-usage/month')
    def api_usage_month():
        """获取本月调用趋势"""
        from .db import get_db
        
        user_id = flask_session.get('user_id')
        if not user_id:
            return jsonify({'error': '未登录'}), 401
        
        db = get_db()
        trend = get_daily_trend(db, user_id, days=30)
        
        return jsonify({
            'success': True,
            'data': {
                'trend': trend,
                'total': sum(trend.values()),
            }
        })
    
    @bp.route('/api/user/api-usage/history')
    def api_usage_history():
        """获取历史限流记录"""
        from .db import get_db
        
        user_id = flask_session.get('user_id')
        if not user_id:
            return jsonify({'error': '未登录'}), 401
        
        db = get_db()
        records = get_rate_limit_history(db, user_id)
        
        return jsonify({
            'success': True,
            'data': records,
        })
    
    @bp.route('/api/user/api-usage/overview')
    def api_usage_overview():
        """获取完整概览数据（一次请求拿全）"""
        from .db import get_db
        from .helpers import get_current_user
        
        user_id = flask_session.get('user_id')
        if not user_id:
            return jsonify({'error': '未登录'}), 401
        
        user = get_current_user()
        db = get_db()
        
        quota = get_quota_info(db, user_id, user)
        hourly = get_hourly_distribution(db, user_id)
        week_trend = get_daily_trend(db, user_id, days=7)
        endpoints = get_endpoint_distribution(db, user_id, days=7)
        rate_limits = get_rate_limit_history(db, user_id, limit=10)
        
        return jsonify({
            'success': True,
            'data': {
                'quota': quota,
                'today': {
                    'total': sum(hourly.values()),
                    'hourly': hourly,
                },
                'week': {
                    'total': sum(week_trend.values()),
                    'trend': week_trend,
                },
                'endpoints': endpoints,
                'rate_limits': rate_limits,
            }
        })

# 注册路由到blueprint
register_api_usage_routes(api_usage_bp)
