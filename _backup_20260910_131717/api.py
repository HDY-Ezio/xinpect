"""Xinpect - Scan API with Member Credits System

Provides /api/v1/scan endpoint with API Key authentication + credits deduction.
Supports:
- Boss key (user_id=15): unlimited, no credits deducted
- Member keys: daily free scan + credits deduction
- Credits warning levels in response
"""
import json
import secrets
import time
from datetime import datetime
from collections import defaultdict
from flask import Blueprint, request, jsonify

from .constants import (
    app, logger,
    ALL_BRAIN_IDS, FREE_BRAIN_IDS,
    HTTP_OK, HTTP_BAD_REQUEST, HTTP_UNAUTHORIZED, HTTP_FORBIDDEN,
    HTTP_NOT_FOUND, HTTP_INTERNAL_ERROR, HTTP_PAYMENT_REQUIRED,
    SCAN_COST_PER_100_LINES_FULL,
)
from .db import get_db
from .scanner import call_scanner, ScanEngineError
from .scoring import (
    calculate_score, calculate_building_block_scores,
    score_to_grade, severity_label,
    get_user_credits, consume_credits, calculate_scan_cost, grant_credits,
    get_credit_pools,
)

api_bp = Blueprint('api', __name__)

# Boss user_id - unlimited, no credits deduction
UNLIMITED_USER_ID = 15

# ============================================================
# Rate Limiter (simple in-memory, reset on restart)
# ============================================================
_rate_limit_store = defaultdict(list)
RATE_LIMIT_WINDOW = 60   # 60 seconds
RATE_LIMIT_MAX = 10       # 10 requests per window


def _check_rate_limit(api_key_hash):
    """Check if the API key has exceeded rate limit. Returns (allowed, remaining)."""
    now = time.time()
    _rate_limit_store[api_key_hash] = [
        t for t in _rate_limit_store[api_key_hash]
        if now - t < RATE_LIMIT_WINDOW
    ]
    if len(_rate_limit_store[api_key_hash]) >= RATE_LIMIT_MAX:
        return False, 0
    _rate_limit_store[api_key_hash].append(now)
    remaining = RATE_LIMIT_MAX - len(_rate_limit_store[api_key_hash])
    return True, remaining


# ============================================================
# API Key Generation & Validation
# ============================================================
def generate_api_key():
    """Generate API key in format: xk_ + 32 random hex chars"""
    return 'xk_' + secrets.token_hex(16)


def validate_api_key(api_key):
    """
    Validate API key and return user info dict.
    Returns None if key is invalid or inactive.
    """
    if not api_key or not api_key.startswith('xk_'):
        return None
    db = get_db()
    row = db.execute(
        'SELECT ak.*, u.email, u.is_vip FROM api_keys ak '
        'JOIN users u ON ak.user_id = u.id '
        'WHERE ak.api_key = ? AND ak.is_active = 1',
        (api_key,)
    ).fetchone()
    if row:
        return dict(row)
    return None


def _get_credits_warning(credits_remaining):
    """Generate warning message based on credits level."""
    if credits_remaining > 100:
        return None
    elif credits_remaining >= 50:
        return "积分余额不足100，建议充值"
    elif credits_remaining >= 10:
        return "积分余额不足50，请尽快充值"
    else:
        return "积分即将耗尽，请立即充值"


def _update_key_usage(db, key_id):
    """Update API key usage stats."""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    db.execute(
        'UPDATE api_keys SET last_used = ?, usage_count = COALESCE(usage_count, 0) + 1 WHERE id = ?',
        (now, key_id)
    )


# ============================================================
# api_scan 拆分：参数验证
# ============================================================
def _validate_api_scan_request():
    """验证 API Key、VIP 状态、请求体。
    返回 (user_info, code_files, language, error_response) 四元组。
    error_response 非 None 表示验证失败，应直接返回。
    """
    api_key = request.headers.get('X-API-Key', '').strip()
    if not api_key:
        return None, None, None, (
            jsonify({'error': 'Missing X-API-Key header'}), HTTP_UNAUTHORIZED
        )

    user_info = validate_api_key(api_key)
    if not user_info:
        return None, None, None, (
            jsonify({'error': 'Invalid or inactive API key'}), HTTP_FORBIDDEN
        )

    if not user_info.get('is_vip'):
        return None, None, None, (
            jsonify({
                'error': 'API扫描功能仅对会员开放，请先开通会员',
                'upgrade_url': '/dashboard?recharge',
            }), HTTP_PAYMENT_REQUIRED
        )

    if not request.is_json:
        return None, None, None, (
            jsonify({'error': 'Content-Type must be application/json'}), HTTP_BAD_REQUEST
        )

    data = request.get_json(silent=True)
    if not data:
        return None, None, None, (
            jsonify({'error': 'Invalid JSON body'}), HTTP_BAD_REQUEST
        )

    code_files = data.get('code_files', {})
    language = data.get('language', 'auto')

    if not code_files:
        return None, None, None, (
            jsonify({'error': 'code_files is required and cannot be empty'}),
            HTTP_BAD_REQUEST
        )

    return user_info, code_files, language, None


# ============================================================
# api_scan 拆分：积分处理
# ============================================================
def _process_api_credits(user_id, scan_cost):
    """检查并扣除积分。
    返回 (credits_used, error_response)。
    error_response 非 None 表示积分不足或扣减失败。
    """
    current_credits = get_user_credits(user_id)
    if current_credits < scan_cost:
        return 0, (
            jsonify({
                'error': '积分不足，请充值后重试',
                'credits_required': scan_cost,
                'credits_remaining': current_credits,
                'upgrade_url': '/dashboard?recharge',
            }), HTTP_PAYMENT_REQUIRED
        )

    success = consume_credits(
        user_id, scan_cost,
        ref_type='api_scan',
        remark=f'API扫描: 积分扣减'
    )
    if not success:
        return 0, (
            jsonify({'error': '积分扣除失败'}), HTTP_INTERNAL_ERROR
        )

    return scan_cost, None


# ============================================================
# api_scan 拆分：结果格式化
# ============================================================
def _count_severity(issues):
    """统计各级别问题数量"""
    counts = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0, 'info': 0}
    for issue in issues:
        sev = issue.get('severity', 'low')
        if sev in counts:
            counts[sev] += 1
        else:
            counts['low'] += 1
    return counts


def _format_api_issues(issues):
    """格式化 issues 为 API 响应格式"""
    return [
        {
            'check_id': issue.get('rule_id', ''),
            'severity': issue.get('severity', 'medium'),
            'file': issue.get('file', ''),
            'line': issue.get('line', 0),
            'message': issue.get('description', ''),
            'suggestion': issue.get('suggestion', ''),
            'brain_id': issue.get('brain_id', ''),
            'brain_name': issue.get('brain_name', ''),
            'title': issue.get('title', ''),
        }
        for issue in issues
    ]


def _build_credits_detail(user_id):
    """构建积分池详情"""
    credit_pools_info = get_credit_pools(user_id)
    return {
        'total_balance': credit_pools_info['total_balance'],
        'subscription_balance': credit_pools_info['subscription_balance'],
        'pack_balance': credit_pools_info['pack_balance'],
        'subscription_refresh_at': credit_pools_info.get('subscription_refresh_at'),
        'pack_expire_at': credit_pools_info.get('pack_nearest_expire_at'),
    }


def _build_scan_response(scan_ctx):
    """构建完整的 API 响应字典。scan_ctx: dict"""
    issues = scan_ctx['issues']
    result = scan_ctx['result']
    code_files = scan_ctx['code_files']
    total_lines = scan_ctx['total_lines']
    scan_cost = scan_ctx['scan_cost']
    user_id = scan_ctx['user_id']
    language = scan_ctx['language']

    score = calculate_score(issues, ALL_BRAIN_IDS)
    grade = score_to_grade(score)
    bb_scores = calculate_building_block_scores(issues, file_count=len(code_files))

    warning = None
    if total_lines < 10:
        warning = f"样本过小（有效代码 {total_lines} 行），结果仅供参考"

    credits_remaining = get_user_credits(user_id)
    credits_warning = _get_credits_warning(credits_remaining)
    if credits_remaining < 50:
        credits_warning = "积分余额不足50，建议充值积分包"

    return {
        'score': score,
        'grade': grade,
        'total_issues': len(issues),
        'severity_counts': _count_severity(issues),
        'building_block_scores': bb_scores,
        'issues': _format_api_issues(issues),
        'file_count': len(code_files),
        'language': language,
        'scan_mode': 'full',
        'scan_time': result.get('scan_time', 0),
        'version': result.get('version', ''),
        'total_lines': total_lines,
        'warning': warning,
        'credits_used': scan_cost,
        'credits_remaining': credits_remaining,
        'credits_warning': credits_warning,
        'credits_detail': _build_credits_detail(user_id),
    }, score


# ============================================================
# api_scan 拆分：保存扫描历史
# ============================================================
def _save_api_scan_history(db, scan_ctx, score, grade):
    """保存 API 扫描历史到数据库"""
    try:
        import uuid as _uuid
        user_id = scan_ctx['user_id']
        code_files = scan_ctx['code_files']
        file_names = list(code_files.keys())
        title = (
            f"{file_names[0]} 等 {len(file_names)} 个文件"
            if len(file_names) > 1 else file_names[0]
        )
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.execute(
            "INSERT INTO scans "
            "(scan_id, user_id, title, file_count, files_meta, results, "
            "score, grade, issue_count, language, created_at, "
            "credits_spent, total_lines, scan_mode, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                _uuid.uuid4().hex, user_id, title, len(code_files),
                json.dumps(file_names, ensure_ascii=False),
                json.dumps(scan_ctx['result'], ensure_ascii=False),
                score, grade,
                len(scan_ctx['result'].get('issues', [])),
                scan_ctx['language'], now,
                scan_ctx['scan_cost'], scan_ctx['total_lines'],
                'full', "api",
            )
        )
        db.commit()
    except Exception as e:
        logger.error(f"Failed to save API scan history: {e}")


# ============================================================
# API Scan Endpoint（入口）
# ============================================================
@api_bp.route('/api/v1/scan', methods=['GET'])
def api_scan_info():
    """GET请求返回API说明，防止405噪音"""
    return jsonify({
        "endpoint": "/api/v1/scan",
        "method": "POST",
        "description": "煋鉴代码扫描API",
        "auth": "需要API Key (Header: X-API-Key)",
        "docs": "https://xinpect.ai/docs/api"
    })

@api_bp.route('/api/v1/scan', methods=['POST'])
def api_scan():
    """Scan API endpoint with credits system."""
    # 1. 参数验证
    user_info, code_files, language, err = _validate_api_scan_request()
    if err:
        return err

    user_id = user_info['user_id']
    key_id = user_info['id']

    # 2. 计算费用
    total_lines = sum(
        sum(1 for ln in c.split('\n') if ln.strip())
        for c in code_files.values() if isinstance(c, str)
    )
    scan_cost = calculate_scan_cost(total_lines, is_full_scan=True)

    # 3. 扣除积分
    db = get_db()
    credits_used, err = _process_api_credits(user_id, scan_cost)
    if err:
        return err

    # 4. 加载用户自定义阈值
    user_thresholds = _load_user_thresholds(db, user_id)

    # 5. 调用扫描引擎
    try:
        result = call_scanner(code_files, ALL_BRAIN_IDS, {
            'language': language, 'scan_mode': 'full',
            'is_vip': True, 'thresholds': user_thresholds,
        })
    except ScanEngineError as e:
        if credits_used > 0:
            grant_credits(
                user_id, credits_used,
                ref_type='refund', ref_id=str(key_id),
                remark='API扫描失败退款',
            )
            db.commit()
        return jsonify({
            'error': '扫描服务暂时不可用，请稍后重试',
            'detail': str(e),
        }), 503

    issues = result.get('issues', [])

    # 6. 构建响应 + 保存历史
    scan_ctx = {
        'issues': issues, 'result': result, 'code_files': code_files,
        'total_lines': total_lines, 'scan_cost': credits_used,
        'user_id': user_id, 'language': language,
    }
    response, score = _build_scan_response(scan_ctx)
    _update_key_usage(db, key_id)
    _save_api_scan_history(db, scan_ctx, score, response['grade'])

    return jsonify(response), HTTP_OK


def _load_user_thresholds(db, user_id):
    """加载用户自定义阈值配置"""
    try:
        row = db.execute(
            'SELECT config_json FROM scan_thresholds WHERE user_id=?',
            (user_id,),
        ).fetchone()
        if row and row[0]:
            return json.loads(row[0])
    except Exception:
        pass
    return None


# ============================================================
# API Key Management Endpoints (for dashboard, session auth)
# ============================================================
@api_bp.route('/api/v1/keys', methods=['GET'])
def api_list_keys():
    """List API keys for current logged-in user"""
    from flask import session as flask_session

    if not flask_session.get('user_id'):
        return jsonify({'error': 'Not authenticated'}), HTTP_UNAUTHORIZED

    user_id = flask_session.get('user_id')
    db = get_db()
    rows = db.execute(
        'SELECT id, name, api_key, is_active, created_at, last_used, usage_count '
        'FROM api_keys WHERE user_id = ? ORDER BY created_at DESC',
        (user_id,)
    ).fetchall()

    keys = []
    for row in rows:
        key_dict = dict(row)
        full_key = key_dict['api_key']
        masked = full_key[:8] + '***' if len(full_key) > 8 else '***'
        key_dict['masked_key'] = masked
        del key_dict['api_key']
        keys.append(key_dict)

    return jsonify({'keys': keys}), HTTP_OK


@api_bp.route('/api/v1/keys/create', methods=['POST'])
def api_create_key():
    """Create a new API key for current user"""
    from flask import session as flask_session

    if not flask_session.get('user_id'):
        return jsonify({'error': 'Not authenticated'}), HTTP_UNAUTHORIZED

    user_id = flask_session.get('user_id')
    data = request.get_json(silent=True) or {}
    name = data.get('name', 'default').strip()[:50]

    db = get_db()
    count = db.execute(
        'SELECT COUNT(*) as cnt FROM api_keys WHERE user_id = ?', (user_id,)
    ).fetchone()
    if count['cnt'] >= 5:
        return jsonify({'error': '每个用户最多5个API密钥'}), HTTP_BAD_REQUEST

    new_key = generate_api_key()

    try:
        db.execute(
            'INSERT INTO api_keys (user_id, api_key, name, is_active) VALUES (?, ?, ?, 1)',
            (user_id, new_key, name or 'default')
        )
        db.commit()
    except Exception as e:
        logger.error('Failed to create API key: %s', e)
        return jsonify({'error': '创建API密钥失败'}), HTTP_INTERNAL_ERROR

    return jsonify({
        'message': 'API密钥已创建，请立即保存 - 之后无法再次查看完整密钥！',
        'key': new_key,
        'name': name or 'default',
    }), HTTP_OK


@api_bp.route('/api/v1/keys/<int:key_id>/delete', methods=['POST'])
def api_delete_key(key_id):
    """Delete an API key"""
    from flask import session as flask_session

    if not flask_session.get('user_id'):
        return jsonify({'error': 'Not authenticated'}), HTTP_UNAUTHORIZED

    user_id = flask_session.get('user_id')
    db = get_db()

    row = db.execute(
        'SELECT id FROM api_keys WHERE id = ? AND user_id = ?',
        (key_id, user_id)
    ).fetchone()
    if not row:
        return jsonify({'error': 'Key not found'}), HTTP_NOT_FOUND

    db.execute('DELETE FROM api_keys WHERE id = ? AND user_id = ?', (key_id, user_id))
    db.commit()

    return jsonify({'message': 'API密钥已删除'}), HTTP_OK
