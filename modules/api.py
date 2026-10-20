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
    calculate_score, calculate_building_block_scores, calculate_tier_scores,
    score_to_grade, severity_label,
    get_user_credits, consume_credits, calculate_scan_cost, grant_credits,
    get_credit_pools,
)
from .fix_roadmap import build_fix_roadmap, PRIORITY_MAP

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

    if not isinstance(code_files, dict):
        return None, None, None, (
            jsonify({'error': 'code_files must be a JSON object (dict), e.g. {"main.py": "code here"}'}),
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
    # 空文件或免费扫描，scan_cost=0，跳过扣费
    if scan_cost == 0:
        return 0, None
    
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
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    _alias = {
        "suspicious": "high",
        "correctness": "medium",
        "restriction": "medium",
        "warning": "medium",
        "style": "low",
        "minor": "low",
    }
    for issue in issues:
        sev = issue.get("severity", "low")
        sev = _alias.get(sev, sev)
        if sev in counts:
            counts[sev] += 1
        else:
            counts["low"] += 1
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
            'priority': PRIORITY_MAP.get(issue.get('severity', 'info'), 'P3'),
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
        'fix_roadmap': build_fix_roadmap(issues),
        'tier_scores': calculate_tier_scores(issues, available_brain_ids=ALL_BRAIN_IDS, is_vip=True),
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

    # 5. 调用扫描引擎（大项目走异步模式）
    total_code_size = sum(len(v) for v in code_files.values() if isinstance(v, str))
    ASYNC_THRESHOLD = 100 * 1024  # 100KB以上走异步

    if total_code_size >= ASYNC_THRESHOLD:
        # 异步模式：立即返回scan_id，用户轮询获取结果
        scan_id = f"api_scan_{int(time.time() * 1000)}_{user_id}"
        db.execute(
            "INSERT INTO scans (scan_id, user_id, title, file_count, files_meta, results, score, grade, issue_count, language, credits_spent, total_lines, scan_mode, source, scan_status) VALUES (?, ?, ?, ?, ?, '[]', 0, '', 0, ?, ?, ?, 'api', 'pending')",
            (scan_id, user_id, f"API扫描({len(code_files)}个文件)", len(code_files),
             json.dumps(list(code_files.keys()), ensure_ascii=False),
             language, credits_used, total_lines)
        )
        db.commit()

        # 后台线程执行扫描
        import threading
        def _bg_scan():
            try:
                from modules.scanner import call_scanner as _cs
                r = _cs(code_files, ALL_BRAIN_IDS, {
                    'language': language, 'scan_mode': 'full',
                    'is_vip': True, 'thresholds': user_thresholds,
                })
                issues = r.get('issues', [])
                score = max(0, 100 - sum(
                    {'critical': 10, 'blocker': 15, 'high': 5, 'medium': 3, 'low': 0.5}.get(i.get('severity',''), 0)
                    for i in issues
                ))
                grade = 'S' if score >= 90 else 'A' if score >= 75 else 'B' if score >= 60 else 'C' if score >= 40 else 'D'
                _db = get_db()
                _db.execute("UPDATE scans SET results=?, score=?, grade=?, issue_count=?, scan_status='completed', scan_progress=100, scan_progress_text='扫描完成' WHERE scan_id=?",
                    (json.dumps({'issues': issues, 'result': r}, ensure_ascii=False, default=str), score, grade, len(issues), scan_id))
                _db.commit()
            except Exception as e:
                _db = get_db()
                _db.execute("UPDATE scans SET scan_status='failed', scan_error=? WHERE scan_id=?", (str(e)[:500], scan_id))
                _db.commit()
                if credits_used > 0:
                    from modules.scoring import grant_credits as _gc
                    _gc(user_id, credits_used, ref_type='refund', ref_id=str(key_id), remark='API扫描失败退款')
                    _db.commit()

        threading.Thread(target=_bg_scan, daemon=True).start()

        return jsonify({
            'status': 'processing',
            'scan_id': scan_id,
            'message': f'大项目扫描已提交（{total_code_size/1024:.0f}KB），请轮询获取结果',
            'poll_url': f'/api/scan/status/{scan_id}',
            'estimated_seconds': max(60, int(total_code_size / 1024 * 2)),
            'credits_used': credits_used,
        }), HTTP_OK

    # 同步模式（小项目，<100KB）
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
    try:
        response, score = _build_scan_response(scan_ctx)
        _update_key_usage(db, key_id)
        _save_api_scan_history(db, scan_ctx, score, response['grade'])
    except Exception as e:
        import traceback
        app.logger.error('API scan result error: %s\n%s', e, traceback.format_exc())
        if credits_used > 0:
            grant_credits(user_id, credits_used, ref_type='refund', ref_id=str(key_id), remark='API scan result error refund')
            db.commit()
        return jsonify({'error': 'Scan result error, credits refunded'}), 500

    return jsonify(response), HTTP_OK



def _build_sarif_response(response, version="1.0.0"):
    """将扫描响应转换为 SARIF 2.1.0 格式"""
    issues = response.get("issues", [])
    
    # Build rules (deduplicated)
    rules = []
    seen_rules = set()
    for issue in issues:
        rule_id = issue.get("check_id", "UNKNOWN")
        if rule_id not in seen_rules:
            seen_rules.add(rule_id)
            rules.append({
                "id": rule_id,
                "shortDescription": {
                    "text": issue.get("title", issue.get("message", ""))
                },
                "properties": {
                    "brain_id": issue.get("brain_id", ""),
                    "brain_name": issue.get("brain_name", ""),
                    "priority": issue.get("priority", "P3"),
                }
            })
    
    # Map severity to SARIF level
    severity_to_level = {
        "critical": "error", "blocker": "error",
        "high": "warning", "suspicious": "warning",
        "medium": "warning", "correctness": "warning",
        "restriction": "warning", "warning": "warning",
        "low": "note", "style": "note", "info": "note", "minor": "note",
    }
    
    # Build results
    sarif_results = []
    for issue in issues:
        sev = issue.get("severity", "info")
        entry = {
            "ruleId": issue.get("check_id", "UNKNOWN"),
            "level": severity_to_level.get(sev, "note"),
            "message": {"text": issue.get("message", "")},
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": issue.get("file", "")},
                    "region": {"startLine": issue.get("line", 1)},
                }
            }],
        }
        if issue.get("suggestion"):
            entry["fixes"] = [{
                "description": {"text": issue["suggestion"]},
            }]
        sarif_results.append(entry)
    
    return {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {
                "driver": {
                    "name": "Xinpect",
                    "version": version,
                    "informationUri": "https://xinpect.xingwangzhineng.com",
                    "rules": rules,
                }
            },
            "results": sarif_results,
            "properties": {
                "score": response.get("score", 0),
                "grade": response.get("grade", ""),
                "file_count": response.get("file_count", 0),
                "total_lines": response.get("total_lines", 0),
                "scan_time": response.get("scan_time", 0),
            }
        }]
    }


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


# ============================================================
# P2-02: 本地扫描结果上传 API
# ============================================================
@api_bp.route('/api/v1/results/upload', methods=['POST'])
def api_upload_results():
    """
    接收本地 CLI 扫描结果并存储到云端看板。
    请求格式:
    {
        "results": { ... },
        "source": "cli",
        "language": "python",
        "project_tag": "my-project",
        "uploaded_at": "2026-..."
    }
    认证: X-API-Key header
    """
    # 1. 验证 API Key
    api_key = request.headers.get('X-API-Key', '')
    user_info = validate_api_key(api_key)
    if not user_info:
        return jsonify({'error': '无效的 API Key'}), HTTP_UNAUTHORIZED

    user_id = user_info['user_id']
    db = get_db()

    # 2. 解析请求体
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': '请求体必须是 JSON'}), HTTP_BAD_REQUEST

    results = data.get('results')
    if not results:
        return jsonify({'error': '缺少 results 字段'}), HTTP_BAD_REQUEST

    # 3. 从结果中提取关键信息
    issues = results.get('issues', [])
    if isinstance(issues, list):
        issue_count = len(issues)
    else:
        issue_count = 0

    # 计算评分（如果结果中没有则用简单算法）
    score = results.get('score')
    grade = results.get('grade')
    if score is None:
        critical = sum(1 for i in issues if isinstance(i, dict) and i.get('severity') in ('critical', 'P0'))
        high = sum(1 for i in issues if isinstance(i, dict) and i.get('severity') in ('high', 'P1'))
        medium = sum(1 for i in issues if isinstance(i, dict) and i.get('severity') in ('medium', 'P2'))
        low = sum(1 for i in issues if isinstance(i, dict) and i.get('severity') in ('low', 'P3'))
        score = max(0, 100 - critical * 15 - high * 10 - medium * 5 - low * 2)

    if grade is None:
        if score >= 95:
            grade = 'SSS'
        elif score >= 90:
            grade = 'SS'
        elif score >= 80:
            grade = 'S'
        elif score >= 70:
            grade = 'A'
        elif score >= 60:
            grade = 'B'
        elif score >= 40:
            grade = 'C'
        else:
            grade = 'D'

    # 4. 提取文件信息
    files = results.get('files', results.get('file_list', []))
    if isinstance(files, list):
        file_count = len(files)
        file_names = [f.get('name', f) if isinstance(f, dict) else str(f) for f in files[:50]]
    elif isinstance(files, dict):
        file_count = len(files)
        file_names = list(files.keys())[:50]
    else:
        file_count = results.get('file_count', 0)
        file_names = []

    language = data.get('language', results.get('language', ''))
    project_tag = data.get('project_tag', '')
    total_lines = results.get('total_lines', 0)

    # 生成标题
    if file_names:
        title = file_names[0] if len(file_names) == 1 else "{} 等 {} 个文件".format(file_names[0], len(file_names))
    else:
        title = "CLI上传 {}".format(datetime.now().strftime('%m-%d %H:%M'))

    # 5. 存入 scans 表
    import uuid as _uuid
    scan_id = _uuid.uuid4().hex
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        db.execute(
            "INSERT INTO scans "
            "(scan_id, user_id, title, file_count, files_meta, results, "
            "score, grade, issue_count, language, created_at, "
            "credits_spent, total_lines, scan_mode, source, ci_repo) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)",
            (
                scan_id, user_id, title, file_count,
                json.dumps(file_names, ensure_ascii=False),
                json.dumps(results, ensure_ascii=False),
                score, grade, issue_count,
                language, now,
                total_lines, 'full', 'cli',
                project_tag,
            )
        )

        # 6. 同时写入 scan_metrics 表
        severity_counts = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
        for issue in issues:
            if isinstance(issue, dict):
                sev = str(issue.get('severity', '')).lower()
                for key in severity_counts:
                    if key in sev or sev in key:
                        severity_counts[key] += 1
                        break

        db.execute(
            "INSERT INTO scan_metrics "
            "(user_id, scan_id, score, grade, issue_count, "
            "critical_count, high_count, medium_count, low_count, "
            "file_count, total_lines, scan_mode, project_tag, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user_id, scan_id, score, grade, issue_count,
                severity_counts['critical'], severity_counts['high'],
                severity_counts['medium'], severity_counts['low'],
                file_count, total_lines, 'full', project_tag, now,
            )
        )
        db.commit()

    except Exception as e:
        import traceback
        logger.error('Upload results error: %s\n%s', e, traceback.format_exc())
        return jsonify({'error': '保存失败', 'detail': str(e)}), HTTP_INTERNAL_ERROR

    msg = "上传成功，评分 {} ({})".format(score, grade)
    return jsonify({
        'status': 'ok',
        'scan_id': scan_id,
        'score': score,
        'grade': grade,
        'issue_count': issue_count,
        'message': msg,
    }), HTTP_OK

# ============================================================
# Benchmark APIs (P1-09/P1-10/P1-11)
# ============================================================

@api_bp.route("/api/v1/benchmark/stats", methods=["GET"])
def benchmark_stats():
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM benchmark_samples").fetchone()[0]
    if total == 0:
        return jsonify({"total": 0, "message": "标注集为空"}), HTTP_OK
    tp = db.execute("SELECT COUNT(*) FROM benchmark_samples WHERE ground_truth='true_positive'").fetchone()[0]
    fp = db.execute("SELECT COUNT(*) FROM benchmark_samples WHERE ground_truth='false_positive'").fetchone()[0]
    pending = db.execute("SELECT COUNT(*) FROM benchmark_samples WHERE ground_truth='pending'").fetchone()[0]
    by_language = db.execute("SELECT language, COUNT(*) as cnt FROM benchmark_samples GROUP BY language").fetchall()
    by_issue_type = db.execute("SELECT issue_type, COUNT(*) as cnt FROM benchmark_samples GROUP BY issue_type ORDER BY cnt DESC").fetchall()
    by_severity = db.execute("SELECT severity, COUNT(*) as cnt FROM benchmark_samples GROUP BY severity ORDER BY severity").fetchall()
    return jsonify({
        "total": total, "true_positive": tp, "false_positive": fp, "pending": pending,
        "by_language": {r["language"]: r["cnt"] for r in by_language},
        "by_issue_type": {r["issue_type"]: r["cnt"] for r in by_issue_type},
        "by_severity": {r["severity"]: r["cnt"] for r in by_severity},
    }), HTTP_OK

@api_bp.route("/api/v1/benchmark/samples", methods=["GET"])
def benchmark_samples_list():
    db = get_db()
    language = request.args.get("language")
    severity = request.args.get("severity")
    truth = request.args.get("truth")
    issue_type = request.args.get("issue_type")
    page = max(1, int(request.args.get("page", 1)))
    per_page = min(100, max(1, int(request.args.get("per_page", 20))))
    conditions = []
    params = []
    if language:
        conditions.append("language = ?")
        params.append(language)
    if severity:
        conditions.append("severity = ?")
        params.append(severity)
    if truth:
        conditions.append("ground_truth = ?")
        params.append(truth)
    if issue_type:
        conditions.append("issue_type = ?")
        params.append(issue_type)
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    total = db.execute("SELECT COUNT(*) FROM benchmark_samples " + where, params).fetchone()[0]
    offset = (page - 1) * per_page
    rows = db.execute(
        "SELECT id, file_path, language, code_snippet, issue_type, severity, cwe_id, ground_truth, notes, source, created_at FROM benchmark_samples " + where + " ORDER BY id LIMIT ? OFFSET ?",
        params + [per_page, offset]
    ).fetchall()
    return jsonify({"total": total, "page": page, "per_page": per_page, "samples": [dict(r) for r in rows]}), HTTP_OK

@api_bp.route("/api/v1/benchmark/annotate", methods=["POST"])
def benchmark_annotate():
    data = request.get_json(silent=True) or {}
    sample_id = data.get("sample_id")
    ground_truth = data.get("ground_truth")
    notes = data.get("notes", "")
    if not sample_id or ground_truth not in ("true_positive", "false_positive", "pending"):
        return jsonify({"error": "参数错误"}), HTTP_BAD_REQUEST
    db = get_db()
    row = db.execute("SELECT id FROM benchmark_samples WHERE id = ?", (sample_id,)).fetchone()
    if not row:
        return jsonify({"error": "样本不存在"}), HTTP_NOT_FOUND
    db.execute(
        "UPDATE benchmark_samples SET ground_truth=?, annotated_by=?, annotated_at=?, notes=? WHERE id=?",
        (ground_truth, "api_user", datetime.now().strftime("%Y-%m-%d %H:%M:%S"), notes, sample_id)
    )
    db.commit()
    return jsonify({"status": "ok", "sample_id": sample_id, "ground_truth": ground_truth}), HTTP_OK

@api_bp.route("/api/v1/benchmark/run", methods=["POST"])
def benchmark_run():
    import importlib.util
    spec = importlib.util.spec_from_file_location("run_bench", "/opt/xinpect-website/scripts/run_benchmark.py")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        result = mod.run_offline_benchmark()
        if result:
            return jsonify(result), HTTP_OK
        return jsonify({"error": "Benchmark运行失败"}), HTTP_INTERNAL_ERROR
    except Exception as e:
        import traceback
        logger.error("Benchmark run error: %s\n%s", e, traceback.format_exc())
        return jsonify({"error": str(e)}), HTTP_INTERNAL_ERROR

@api_bp.route("/api/v1/benchmark/results", methods=["GET"])
def benchmark_results():
    db = get_db()
    limit = min(50, max(1, int(request.args.get("limit", 10))))
    rows = db.execute("SELECT * FROM benchmark_results ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        try:
            d["by_severity"] = json.loads(d["by_severity"]) if d["by_severity"] else {}
            d["by_language"] = json.loads(d["by_language"]) if d["by_language"] else {}
        except Exception:
            pass
        results.append(d)
    return jsonify({"results": results, "count": len(results)}), HTTP_OK

@api_bp.route("/api/v1/benchmark/latest", methods=["GET"])
def benchmark_latest():
    db = get_db()
    row = db.execute("SELECT * FROM benchmark_results ORDER BY created_at DESC LIMIT 1").fetchone()
    if not row:
        return jsonify({"available": False, "message": "暂无benchmark数据"}), HTTP_OK
    d = dict(row)
    try:
        d["by_severity"] = json.loads(d["by_severity"]) if d["by_severity"] else {}
        d["by_language"] = json.loads(d["by_language"]) if d["by_language"] else {}
    except Exception:
        pass
    d["available"] = True
    precision = d.get("precision_score", 0)
    if precision > 0.90:
        d["messaging"] = "每条告警都站得住脚 — 误报率低于10%"
        d["messaging_short"] = "误报率<10%"
    elif precision > 0.85:
        d["messaging"] = "业界领先的低误报率，每条告警都值得跟进"
        d["messaging_short"] = "业界领先低误报"
    elif precision > 0.80:
        d["messaging"] = "持续优化的检测精度，告警可信赖"
        d["messaging_short"] = "高精度检测"
    else:
        d["messaging"] = "持续迭代中的检测引擎"
        d["messaging_short"] = "持续优化中"
    return jsonify(d), HTTP_OK
