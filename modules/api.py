"""Xinpect - Scan API with Member Credits System

Provides /api/v1/scan endpoint with API Key authentication + credits deduction.
Supports:
- Boss key (user_id=15): unlimited, no credits deducted
- Member keys: daily free scan + credits deduction
- Credits warning levels in response
"""
import gc
import json
import re as _re
import secrets
import time
from datetime import datetime
from collections import defaultdict
from flask import Blueprint, request, jsonify, session

from .constants import (
    app, logger,
    ALL_BRAIN_IDS, FREE_BRAIN_IDS, brain_label,
    HTTP_OK, HTTP_BAD_REQUEST, HTTP_UNAUTHORIZED, HTTP_FORBIDDEN,
    HTTP_NOT_FOUND, HTTP_INTERNAL_ERROR, HTTP_PAYMENT_REQUIRED,
    SCAN_MAX_FILES, SCAN_MAX_BYTES, SCAN_MAX_LINES,
)
from .db import get_db, init_db, is_admin_user
from .scanner import call_scanner, ScanEngineError
from .scoring import (
    calculate_score, calculate_building_block_scores, calculate_tier_scores,
    score_to_grade, severity_label,
    get_user_credits, consume_credits, calculate_scan_cost, grant_credits,
    get_credit_pools,
)
from .fix_roadmap import build_fix_roadmap, PRIORITY_MAP

api_bp = Blueprint('api', __name__)

# 会员/积分不足时给客户看的升级地址。
# 必须是真实路由 `/dashboard/recharge`——历史上这里写的是 `/dashboard?recharge`，
# 那个 query 参数全站无人处理，客户点进去只是空白首页，等于把最后一步堵死。
# tests/test_upgrade_url_is_reachable.py 钉住这条。
UPGRADE_URL = '/dashboard/recharge'

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
                'upgrade_url': UPGRADE_URL,
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
                'upgrade_url': UPGRADE_URL,
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
            'brain_name': brain_label(issue.get('brain_id', '')),
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
    _scan_result = scan_ctx.get('result') or {}
    bb_scores = calculate_building_block_scores(
        issues,
        file_count=len(code_files),
        style_issues=_scan_result.get('style_issues') or [],
        engines=_scan_result.get('engines'),
    )

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
        'tier_scores': calculate_tier_scores(
            issues, available_brain_ids=ALL_BRAIN_IDS, is_vip=True,
            engines=result.get('engines') or None,
            unsupported=len(result.get('unsupported_files') or []),
            trimmed=len(result.get('trimmed_files') or []),
        ),
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
            "credits_spent, total_lines, scan_mode, source, scan_status, "
            "content_hash, duration_seconds, is_replay) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                _uuid.uuid4().hex, user_id, title, len(code_files),
                json.dumps(file_names, ensure_ascii=False),
                json.dumps(scan_ctx['result'], ensure_ascii=False),
                score, grade,
                len(scan_ctx['result'].get('issues', [])),
                scan_ctx['language'], now,
                scan_ctx['scan_cost'], scan_ctx['total_lines'],
                'full', "api", "completed", scan_ctx.get('content_hash'),
                round(float(scan_ctx.get('duration_seconds') or 0), 2),
                1 if scan_ctx.get('is_replay') else 0,
            )
        )
        db.commit()
    except Exception as e:
        logger.exception(f"Failed to save API scan history: {e}")


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
        "docs": "/api-docs"
    })


# ============================================================
# 2026-10-23 幂等扫描：同内容 24h 内重复提交不重复扣费/重算
# ============================================================
def _scan_fingerprint(code_files, language):
    """内容指纹：语言 + 排序后的 (文件名, 内容MD5) 列表"""
    import hashlib
    h = hashlib.md5()
    h.update(str(language).encode("utf-8", "ignore"))
    for name in sorted(code_files.keys()):
        content = code_files[name]
        if not isinstance(content, str):
            content = ""
        h.update(b"\x00")
        h.update(str(name).encode("utf-8", "ignore"))
        h.update(b"\x00")
        h.update(hashlib.md5(content.encode("utf-8", "ignore")).hexdigest().encode())
    return h.hexdigest()


def _find_reusable_scan(db, user_id, content_hash):
    """24h 内同用户同内容的成功/在途扫描。created_at 存的是本地时间(UTC+8)，故先 +8h 再 -1day。"""
    try:
        return db.execute(
            "SELECT scan_id, results, total_lines, file_count, files_meta, language, scan_status, created_at, score, grade, "
            "COALESCE(duration_seconds, 0) "
            "FROM scans WHERE user_id=? AND content_hash=? AND ("
            "  (scan_status = 'pending' AND created_at > datetime('now','+8 hours','-2 hours'))"
            "  OR (scan_status = 'completed' AND created_at > datetime('now','+8 hours','-1 day'))"
            "  OR (scan_status = 'queued' AND created_at > datetime('now','+8 hours','-1 day'))"
            "  OR (scan_status IS NULL AND results NOT IN ('','[]') AND created_at > datetime('now','+8 hours','-1 day'))"
            ") ORDER BY created_at DESC LIMIT 1",
            (user_id, content_hash)
        ).fetchone()
    except Exception as e:
        logger.exception("idempotent lookup failed: %s", e)
        return None


def _replay_scan_response(row, user_id):
    """复用历史结果构建响应 dict（不做扣费，credits_used 由调用方按实际扣额回填）。"""
    scan_id, results_json, total_lines, file_count, files_meta, language, scan_status, created_at = row[:8]
    if scan_status in ("pending", "queued"):
        return {
            "status": "processing",
            "scan_id": scan_id,
            "idempotent_replay": True,
            "credits_used": 0,
            "message": "相同内容的扫描已在队列中或正在进行，请直接轮询该任务（不会重复扣费）",
            "poll_url": "/api/v1/scan/status/%s" % scan_id,
        }
    try:
        blob = json.loads(results_json)
    except Exception:
        return None
    # 两种存储形态：同步=原始 result dict（内含 issues）；异步={'issues':..., 'result':...}
    if isinstance(blob, dict) and isinstance(blob.get("result"), dict):
        result = blob["result"]
        issues = blob.get("issues") or result.get("issues", [])
    elif isinstance(blob, dict):
        result = blob
        issues = blob.get("issues", [])
    else:
        return None
    try:
        file_names = json.loads(files_meta) if files_meta else []
    except Exception:
        file_names = []
    fake_files = {n: "" for n in file_names}  # 仅需 len()
    scan_ctx = {
        "issues": issues, "result": result, "code_files": fake_files,
        "total_lines": total_lines or 0, "scan_cost": 0,
        "user_id": user_id, "language": language or "auto",
    }
    response, _score = _build_scan_response(scan_ctx)
    response["idempotent_replay"] = True
    response["replayed_from"] = scan_id
    response["original_scan_at"] = created_at
    return response


# ============================================================
# 排队机制（2026-10-23，用户拍板规格）
#   单账号串行（同一账号同时只跑一个任务）+ 全局并行槽位（服务器吃得消时多账号各跑一条）
#   排队不扣积分；出队开始跑才扣（余额不足则任务失败、不扣费）
#   排队中免费取消；运行中可取消但不退积分、结果丢弃
#   兜底：在途超 45 分钟判死退款；排队超 24h 自动取消；服务重启清扫在途
# ============================================================
import os as _os
import threading as _threading

_QUEUE_PAYLOAD_DIR = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
    'data', 'queue_payloads')
# 判活只认心跳：心跳线程每 5 秒写一次 last_heartbeat_at，静默超过这个秒数
# 才认为执行它的进程已经不在了。不再按「提交时间 + 45 分钟」判死 ——
# 大文件分片扫描合法可达数十分钟，那样会把正在正常跑的任务当卡死。
_HEARTBEAT_SILENCE_SECONDS = 180
# 大文件分片扫描只要心跳在动就一直跑，不受固定钟点限制（历史最大单 38 分钟）
_dispatcher_guard = _threading.Event()


def _queue_payload_path(scan_id):
    return _os.path.join(_QUEUE_PAYLOAD_DIR, scan_id + '.json')


def _save_queue_payload(scan_id, code_files, language):
    _os.makedirs(_QUEUE_PAYLOAD_DIR, exist_ok=True)
    tmp = _queue_payload_path(scan_id) + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump({'code_files': code_files, 'language': language}, f, ensure_ascii=False)
    _os.replace(tmp, _queue_payload_path(scan_id))


def _load_queue_payload(scan_id):
    try:
        with open(_queue_payload_path(scan_id), encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def _discard_queue_payload(scan_id):
    try:
        _os.remove(_queue_payload_path(scan_id))
    except OSError:
        pass


def _enqueue_scan(db, user_id, code_files, language, total_lines, content_hash,
                  total_bytes=0):
    """入队（不扣费）。代码体落盘（payload 文件），库里只留元数据。"""
    import uuid as _uuid
    scan_id = 'api_scan_q_%d_%s' % (int(time.time() * 1000), _uuid.uuid4().hex[:8])
    names = list(code_files.keys())
    title = ('%s 等 %d 个文件' % (names[0], len(names))) if len(names) > 1 \
        else (names[0] if names else 'API扫描')
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    db.execute(
        "INSERT INTO scans (scan_id, user_id, title, file_count, files_meta, results, "
        "score, grade, issue_count, language, created_at, credits_spent, total_lines, "
        "scan_mode, source, scan_status, scan_progress, scan_progress_text, "
        "content_hash, total_bytes) "
        "VALUES (?, ?, ?, ?, ?, '[]', 0, '', 0, ?, ?, 0, ?, 'full', 'api', 'queued', "
        "0, '排队中', ?, ?)",
        (scan_id, user_id, title, len(names), json.dumps(names, ensure_ascii=False),
         language, now, total_lines, content_hash, int(total_bytes or 0)))
    db.commit()
    _save_queue_payload(scan_id, code_files, language)
    return scan_id


def _slot_limit():
    """全局并行槽位。

    必须 <= 扫描引擎的 SCAN_MAX_CONCURRENT，否则就是"虚假并行"：
    网站放行第二个任务，它却在引擎信号量门口干等到 HTTP 超时，
    客户既看不到排队位置也没法取消（2026-10-23 实测：小任务等 300s 未返回）。
    引擎侧默认 1 —— 单个扫描内部已按核数开 worker，再并行会把 2 核打爆（10-22 事故）。
    要提高这里，必须同步提高引擎 SCAN_MAX_CONCURRENT 且机器核数够。
    """
    try:
        n = int(_os.environ.get('SCAN_CONCURRENT_SLOTS', '') or 0)
    except Exception:
        n = 0
    if n <= 0:
        n = 1
    return max(1, min(n, 8))


def _queue_order_sql(alias='s'):
    """排队优先级：小任务优先（快速通道），大任务排队超 10 分钟升级防饿死。

    目的：一个大任务跑 7 分钟时不该让所有人干等——小任务插到它前面，
    引擎一有空就先跑小的；但大任务等够 10 分钟也会升到前面，不会被饿死。
    """
    return ("CASE WHEN COALESCE(%s.total_lines, 0) <= 2000 "
            "OR %s.created_at < datetime('now','+8 hours','-10 minutes') "
            "THEN 0 ELSE 1 END" % (alias, alias))


_REPLAY_MIN_SECONDS = 2.0
_REPLAY_MAX_SECONDS = 45.0


def _simulate_scan_duration(first_seconds, total_lines):
    """复用历史结果时的"表演耗时"（2026-10-23 用户拍板修订）。

    以该内容【首次真实扫描】耗时为锚，取 80%~95%：
    ① 重复扫描理应比第一次略快——AI 有缓存/记忆，不该越扫越长；
    ② 必须锚在首次而非上一次——若逐次递减，扫十次会越演越短，明显失真。
    没有首次耗时时按代码量估算。下限 2 秒，且永不超过首次基准。
    省的是 token/算力，不是客户的体感——不能 0.0 秒把旧结果甩回去。
    """
    import random as _random
    try:
        base = float(first_seconds or 0)
    except Exception:
        base = 0.0
    if base <= 0:
        base = max(3.0, min(25.0, (total_lines or 0) / 60.0))
    target = base * _random.uniform(0.80, 0.95)
    target = max(target, min(2.0, base))   # 极短任务不低于 2s（也不超过基准）
    target = min(target, base)             # 永不超过首次
    time.sleep(target)
    return target


# ------------------------------------------------------------
# 进度估算：扫描引擎是"一次调用、内部没有中间进度"的黑盒，
# 客户提交后只能看到 0% 干等 —— 这是"API 查不到进度"的根因。
# 基线不写死常数：从本系统真实跑完的扫描里学（固定开销 + 每行开销），
# 样本不够时回落到实测默认值（小任务 ~15s 起步，大任务 ~0.06 s/行）。
# ------------------------------------------------------------
_ETA_CACHE = {'ts': 0.0, 'fixed': None, 'per_line': None}
_ETA_DEFAULT_FIXED = 15.0      # 一次扫描的固定开销（引擎调度/AI 降噪）
_ETA_DEFAULT_PER_LINE = 0.06   # 实测：6400 行 Java 项目 406s ≈ 0.063 s/行
_ETA_DEFAULT_PER_KB = 0.5      # 实测：121KB 单文件 24s ≈ 0.2 s/KB，取 0.5 留余量


def _eta_baseline():
    """从历史 completed 记录学出 (固定开销秒, 每行秒)。10 分钟刷新一次。

    只认真实扫描：复用结果落库带 is_replay=1，其"表演耗时"必须排除，
    否则基线会被自己造出来的假耗时污染（治本：让数据源可分辨）。
    """
    now = time.time()
    if _ETA_CACHE['per_line'] is not None and now - _ETA_CACHE['ts'] < 600:
        return _ETA_CACHE['fixed'], _ETA_CACHE['per_line']
    fixed, per_line = _ETA_DEFAULT_FIXED, _ETA_DEFAULT_PER_LINE
    try:
        db = get_db()
        rows = db.execute(
            "SELECT COALESCE(total_lines,0) l, duration_seconds d FROM scans "
            "WHERE scan_status='completed' AND COALESCE(duration_seconds,0) > 0 "
            "AND COALESCE(duration_seconds,0) < 1800 AND COALESCE(is_replay,0)=0 "
            "ORDER BY rowid DESC LIMIT 300").fetchall()
        pts = [(r['l'], r['d']) for r in rows if r['l'] > 0]
        if len(pts) >= 5:
            n = len(pts)
            sx = sum(p[0] for p in pts)
            sy = sum(p[1] for p in pts)
            sxx = sum(p[0] * p[0] for p in pts)
            sxy = sum(p[0] * p[1] for p in pts)
            denom = n * sxx - sx * sx
            if denom > 0:
                b = (n * sxy - sx * sy) / denom
                a = (sy - b * sx) / n
                fixed = min(60.0, max(5.0, a))
                per_line = min(0.5, max(0.005, b))
    except Exception as e:
        logger.warning("eta baseline fallback: %s", e)
    _ETA_CACHE.update({'ts': now, 'fixed': fixed, 'per_line': per_line})
    return fixed, per_line


def _estimate_scan_seconds(total_lines, total_bytes=0):
    """估算一次扫描需要多少秒。用于排队等待提示与在途任务的进度推进。

    行数与字节量各算一遍取大者：行数决定规则跑几遍，字节量决定单遍多大，
    只看一个维度会低估（实测 900 行 / 177KB 单文件跑满 100s+，
    按行只有 69s，按字节 354s 才贴近）。
    """
    fixed, per_line = _eta_baseline()
    by_lines = fixed + (total_lines or 0) * per_line
    by_bytes = (total_bytes or 0) / 1024.0 * _ETA_DEFAULT_PER_KB
    return max(20.0, min(1800.0, max(by_lines, by_bytes)))


def _start_progress_ticker(scan_id, total_lines, total_bytes=0):
    """在途任务的心跳（后台线程，返回 stop 事件）。

    2026-11-05 治本：原先按「预计总耗时」把 5%→80% 匀速推进，还报
    「预计还需约 N 秒」——那是按时间编的，跟实际扫到哪一步毫无关系。
    现在这里只续存活心跳，绝不再写百分比、绝不再报倒计时。
    进度百分比只由扫描器真实事件写入（见 scan_progress_bridge）。
    收尾时由调用方 stop.set() 停表。参数保留是为了不改动两处调用点。
    """
    stop = _threading.Event()

    def _tick():
        fails = 0
        while not stop.wait(5.0):
            try:
                with app.app_context():
                    _db = get_db()
                    _db.execute(
                        "UPDATE scans SET last_heartbeat_at=? "
                        "WHERE scan_id=? AND scan_status='pending'",
                        (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), scan_id))
                    _db.commit()
                    fails = 0
            except Exception as e:
                # 一次数据库锁冲突就把心跳线程判死，等于让活着的任务从此失去心跳、
                # 再被收割逻辑误杀（2026-11-14 修）。连续失败才放弃。
                fails += 1
                if fails == 1 or fails % 12 == 0:
                    logger.warning("progress ticker %s 第 %d 次写心跳失败: %s",
                                   scan_id, fails, e)
                if fails >= 60:
                    return

    _threading.Thread(target=_tick, daemon=True,
                      name='scan-ticker-%s' % str(scan_id)[:24]).start()
    return stop


def _queue_position(db, created_at, total_lines, rowid):
    """排队位置（1 = 下一个就轮到）。算法必须与调度器 _dispatch_queued_scans 的
    ORDER BY 完全一致：小任务优先；大任务排队满 10 分钟升级防饿死；同级按提交先后。
    """
    ahead = db.execute(
        "SELECT COUNT(*) FROM scans WHERE scan_status='pending'").fetchone()[0]
    cut = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time() - 600))

    def _prio(tl, ca, rid):
        return (0 if ((tl or 0) <= 2000 or (ca or '') < cut) else 1, ca or '', rid or 0)

    me = _prio(total_lines, created_at, rowid)
    for r in db.execute(
            "SELECT COALESCE(total_lines,0) tl, created_at ca, rowid AS rid "
            "FROM scans WHERE scan_status='queued'"):
        if _prio(r['tl'], r['ca'], r['rid']) < me:
            ahead += 1
    return ahead + 1


def _dispatch_queued_scans():
    """调度一轮：在槽位允许范围内尽量多启动任务。返回本轮启动数。

    两条硬约束（用户拍板）：
      ① 同一账号同时只能有 1 个任务在跑 —— 队首若属于"已有任务在跑"的账号则跳过往下找
      ② 全局并行数 <= _slot_limit() —— 服务器吃得消时多个账号可各跑一条
    """
    started = 0
    db = get_db()
    limit = _slot_limit()
    for _ in range(limit + 2):
        running = db.execute(
            "SELECT COUNT(*) FROM scans WHERE scan_status='pending'").fetchone()[0]
        if running >= limit:
            break
        row = db.execute(
            "SELECT s.scan_id, s.user_id, s.language, s.total_lines FROM scans s "
            "WHERE s.scan_status='queued' AND NOT EXISTS ("
            "  SELECT 1 FROM scans x WHERE x.user_id = s.user_id "
            "  AND x.scan_status = 'pending') "
            "ORDER BY %s, s.created_at, s.rowid LIMIT 1" % _queue_order_sql('s')
        ).fetchone()
        if not row:
            break
        if not _start_queued_scan(db, row):
            break
        started += 1
    return started


# ------------------------------------------------------------
# 大文件服务端自动分片（2026-10-23 用户拍板：用户只交整包，拆分是服务端的事）
#
# 分片要解决的是「超大项目必超时」和「引擎对超 5000 行文件只扫前 5000 行」
# （静默截断：客户付全量的钱却只扫了前半截）。这两条与片大小无关，小片大片都能解决。
#
# 片大小怎么定（2026-11-14 重测，推翻了 10-23 那版结论）：
#   10-23 测的是"一次请求塞多少行"（700 行 19s / 1400 行 66s / 2251 行 207s），
#   据此定成 700 行/片。但那是【单次请求】的耗时，没有算每片的固定开销。
#   11-14 用同一批代码、只改切法、全部冷缓存重测：
#     每片 2100 行 → 1 片 18.7s；每片 700 行 → 3 片 99.5s（每片 33s）。
#   → 每片固定开销 ≈ 27s（10 个大脑模块重新初始化 + 进程池拉起），
#     片越细，这份"开工费"付的次数越多。4 万行的包按 700 行切 31 分钟，按 2000 行切约 8 分钟。
#
# 进度按"安装包"式推进：第 k/N 片 + 正在检查的文件名 + 剩余时间。
# ------------------------------------------------------------
_CHUNK_TARGET_LINES = 2000  # 每片目标行数（2026-11-14 实测校准）
_CHUNK_MAX_FILES = 30       # 每片文件数上限（引擎单请求 200 文件限制内留余量）

# 片大小的依据（2026-11-14 冷缓存实测，同一批代码只改切法）：
#   每片 2100 行 → 1 片，18.7s
#   每片  700 行 → 3 片，99.5s（每片均 33s）
# 每片都要把 10 个大脑模块重新初始化一遍，固定开销约 27 秒/片，
# 行数本身占的比例很小。所以片切得越细、重复付的"开工费"越多，
# 4 万行的包按 700 行切要 31 分钟，按 2000 行切约 8 分钟。
# 上限受三个东西约束：引擎单请求 5 万行/200 文件、单文件 5000 行截断、
# 官网调用引擎的动态超时（300~900s）。2000 行 / 30 文件远在安全区内。


def _plan_scan_chunks(code_files, target_lines=_CHUNK_TARGET_LINES,
                      max_files=_CHUNK_MAX_FILES):
    """把一次提交拆成小片（像安装包逐个文件安装）。

    返回 [{'files': {文件名: 内容}, 'lines': 有效行数,
           'offsets': {文件名: 行窗偏移}}, ...]
    - 小文件凑一片，累计有效行不超过 target_lines、文件数不超过 max_files
    - 超过 target_lines 的单文件按行窗切：片内第 i 行 = 原文件第 offset+i 行，
      合并结果时按偏移回正行号，保证告警行号与客户提交的代码一致
    """
    chunks = []
    cur, cur_lines = {}, 0

    def _flush():
        nonlocal cur, cur_lines
        if cur:
            chunks.append({'files': cur, 'lines': cur_lines, 'offsets': {}})
            cur, cur_lines = {}, 0

    for name, content in code_files.items():
        if not isinstance(content, str):
            continue
        n = sum(1 for ln in content.split('\n') if ln.strip())
        if n == 0:
            cur[name] = content      # 空文件搭首片，不占行数
            continue
        if n <= target_lines:
            if cur and (cur_lines + n > target_lines or len(cur) >= max_files):
                _flush()
            cur[name] = content
            cur_lines += n
            continue
        # 超大文件：按行窗切（片内行号 + 偏移 = 原文件真实行号）
        _flush()
        src = content.split('\n')
        win, win_lines, offset = [], 0, 0
        for ln in src:
            win.append(ln)
            if ln.strip():
                win_lines += 1
            if win_lines >= target_lines:
                chunks.append({'files': {name: '\n'.join(win)},
                               'lines': win_lines, 'offsets': {name: offset}})
                offset += len(win)
                win, win_lines = [], 0
        if win:
            chunks.append({'files': {name: '\n'.join(win)},
                           'lines': win_lines, 'offsets': {name: offset}})
    _flush()
    if not chunks:
        chunks = [{'files': {}, 'lines': 0, 'offsets': {}}]
    return chunks


def _chunk_files_brief(names):
    """进度文案里的文件名摘要：前三名 + 等 N 个文件。"""
    if not names:
        return '空文件'
    if len(names) <= 3:
        return '、'.join(names)
    return '%s 等 %d 个文件' % ('、'.join(names[:3]), len(names))


def _update_scan_progress(scan_id, pct, text):
    """更新在途任务进度 + 存活心跳。

    心跳供 _reap_stale_scans 判活：大文件分片扫描合法可达数十分钟，
    只要心跳还在刷新就不是卡死；心跳停更才判死退款
    （根治"大扫描被 45 分钟规则误判超时"）。
    """
    if not scan_id:
        return   # 同步路径没有在途行，跳过进度落库
    try:
        _db = get_db()
        _db.execute(
            "UPDATE scans SET scan_progress=?, scan_progress_text=?, "
            "last_heartbeat_at=? WHERE scan_id=? AND scan_status='pending'",
            (pct, text, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), scan_id))
        _db.commit()
    except Exception as e:
        logger.warning("progress update %s: %s", scan_id, e)


# 片间让路：每片跑完主动把 CPU 交还系统，避免连续占满全部核心。
#
# 依据（2026-11-14 实证）：321 个文件 / 4 万行的包切成 57 片后连续跑，
# 引擎的 CPU 上限设的是"可吃满 2 核"，于是 57 片首尾相接、中间不松手，
# 官网 / MySQL / nginx 全程抢不到 CPU —— 客户看到的是"整个网站卡死"。
# 这不是扫描慢，是把机器独占了。让路 0.8 秒 + 回收内存，机器才有喘息间隙。
_CHUNK_YIELD_SECONDS = 0.8


def _execute_scan_in_chunks(scan_id, code_files, language, thresholds, user_id,
                            total_lines):
    """分片调用扫描引擎并合并结果（安装包式逐片检查）。

    返回 (issues, merged_result)。任何一片失败都向上抛异常，
    由调用方统一走失败退款流程（与整包扫描的失败语义一致）。

    稳定性子句（2026-11-14）：
    - 片间让路：每片结束 sleep + GC，不连续独占 CPU（否则整站像卡死）。
    - 进度说实话：多片任务显示「第 k/N 片 + 约剩几分钟」。
      大包要跑几十分钟，只写"正在检查 xxx"客户会以为死机了；
      给出片序与剩余时间，客户知道它在往前走。
    """
    chunks = _plan_scan_chunks(code_files)
    total_chunks = len(chunks)
    all_issues = []
    total_scan_time = 0.0
    done_lines = 0
    last = None
    started_at = time.time()
    for idx, ch in enumerate(chunks, 1):
        brief = _chunk_files_brief(list(ch['files'].keys()))
        if total_chunks > 1:
            # 用已完成片的平均耗时外推剩余时间；第 1 片还没跑，先不给
            eta = ''
            if idx > 1:
                per_chunk = (time.time() - started_at) / (idx - 1)
                remain_sec = per_chunk * (total_chunks - idx + 1)
                if remain_sec >= 60:
                    eta = '（约剩 %d 分钟）' % int(remain_sec / 60)
                elif remain_sec >= 10:
                    eta = '（约剩 %d 秒）' % int(remain_sec)
                else:
                    eta = '（马上完成）'
            _update_scan_progress(
                scan_id,
                int(5 + 90 * done_lines / max(1, total_lines)),
                '第 %d/%d 片%s · 正在检查：%s' % (idx, total_chunks, eta, brief))
        else:
            _update_scan_progress(
                scan_id,
                int(5 + 90 * done_lines / max(1, total_lines)),
                '正在检查：%s' % brief)
        r = call_scanner(ch['files'], ALL_BRAIN_IDS, {
            'language': language, 'scan_mode': 'full', 'is_vip': True,
            'thresholds': thresholds, 'user_id': str(user_id),
        })
        total_scan_time += float(r.get('scan_time', 0) or 0)
        # 行窗偏移回正：片内行号 + 偏移 = 原文件行号
        offs = ch.get('offsets') or {}
        _is_window = bool(offs)   # 行窗片 = 大文件切出的片段，不是完整文件
        for i in r.get('issues', []):
            # 行窗片不是完整文件，有两类"整文件断言跑到片段上"的假象：
            # ① 编译失败——片段当然编译不过，不是客户代码有问题；
            # ② 整文件级架构规则（如 3S 行数红线）——把"片段共 873 行"
            #    当成"文件共 873 行"报，行数和语义都是假的。
            # 首片/整文件片的这两类发现是真信号，保留（治本：按片的性质分流，
            # 而不是给具体案例开白名单）
            if _is_window:
                _t = str(i.get('title') or '')
                _rid = str(i.get('rule_id') or '')
                if ('编译失败' in _t or 'compile' in _rid.lower()
                        or _rid.startswith('E5-ARCH-3S')
                        or _re.search(r'文件共\s*\d+\s*行', str(i.get('message') or ''))):
                    continue
            off = offs.get(i.get('file'), 0)
            if off and isinstance(i.get('line'), int) and i['line'] > 0:
                i = dict(i)
                i['line'] = i['line'] + off
            all_issues.append(i)
        done_lines += ch['lines']
        last = r
        # 片间让路：交还 CPU + 回收本片占用的内存，下一片再开
        if idx < total_chunks:
            time.sleep(_CHUNK_YIELD_SECONDS)
            gc.collect()
    # 去重：同文件 + 同行 + 同规则只留一条（行窗不重叠，这里是兜底）
    seen, issues = set(), []
    for i in all_issues:
        k = (i.get('file'), i.get('line'), i.get('rule_id'))
        if k in seen:
            continue
        seen.add(k)
        issues.append(i)
    result = dict(last or {})
    result.update({
        'issues': issues,
        'total_issues': len(issues),
        'file_count': len(code_files),
        'scan_time': round(total_scan_time, 2),
    })
    return issues, result


def _start_queued_scan(db, row):
    """出队执行单个任务：扣费 -> 扫描 -> 落结果。返回 True 表示已处理（无论成败）。"""
    scan_id, user_id = row['scan_id'], row['user_id']
    language, total_lines = row['language'], row['total_lines']

    # 原子认领：被 cancel 抢先则放弃
    claimed = db.execute(
        "UPDATE scans SET scan_status='pending', scan_progress=1, "
        "scan_progress_text='已出队，开始扫描', last_heartbeat_at=?, "
        "created_at=? WHERE scan_id=? AND scan_status='queued'",
        (datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
         datetime.now().strftime('%Y-%m-%d %H:%M:%S'), scan_id)).rowcount
    db.commit()
    if not claimed:
        return False
    # 竞态兜底：认领后若同账号出现两个在跑任务（几乎不可能），退回队列重排
    dup = db.execute(
        "SELECT COUNT(*) FROM scans WHERE user_id=? AND scan_status='pending'",
        (user_id,)).fetchone()[0]
    if dup > 1:
        db.execute(
            "UPDATE scans SET scan_status='queued', scan_progress=0, "
            "scan_progress_text='排队中' WHERE scan_id=? AND scan_status='pending'",
            (scan_id,))
        db.commit()
        return False

    _t0 = time.time()

    # 出队才扣费；余额不足 -> 失败、不扣费
    cost = calculate_scan_cost(total_lines or 0, is_full_scan=True, user_id=user_id)
    if cost > 0:
        if get_user_credits(user_id) < cost:
            db.execute("UPDATE scans SET scan_status='failed', "
                       "scan_error='排队到执行时积分余额不足' WHERE scan_id=?", (scan_id,))
            db.commit()
            _discard_queue_payload(scan_id)
            return True
        if not consume_credits(user_id, cost, ref_type='api_scan',
                               remark='API扫描: 排队出队扣费'):
            db.execute("UPDATE scans SET scan_status='failed', "
                       "scan_error='积分扣减失败' WHERE scan_id=?", (scan_id,))
            db.commit()
            _discard_queue_payload(scan_id)
            return True
        db.execute("UPDATE scans SET credits_spent=? WHERE scan_id=?", (cost, scan_id))
        db.commit()

    payload = _load_queue_payload(scan_id)
    if payload is None:
        db.execute("UPDATE scans SET scan_status='failed', "
                   "scan_error='排队载荷丢失' WHERE scan_id=?", (scan_id,))
        db.commit()
        if cost > 0:
            grant_credits(user_id, cost, ref_type='refund', ref_id=scan_id,
                          remark='API扫描失败退款')
        return True

    _chunks_q = _plan_scan_chunks(payload['code_files'])
    _ticker_stop = None
    if len(_chunks_q) <= 1:
        # 单片任务没有中间进度可报，继续用心跳匀速推进；多片由分片循环实时报进度
        _ticker_stop = _start_progress_ticker(
            scan_id, total_lines,
            sum(len(v) for v in payload['code_files'].values() if isinstance(v, str)))
    try:
        thresholds = _load_user_thresholds(db, user_id)
        issues, r = _execute_scan_in_chunks(
            scan_id, payload['code_files'],
            payload.get('language') or language or 'auto',
            thresholds, user_id, total_lines or 0)
        score = max(0, 100 - sum(
            {'critical': 10, 'blocker': 15, 'high': 5, 'medium': 3, 'low': 0.5}.get(
                i.get('severity', ''), 0) for i in issues))
        grade = ('S' if score >= 90 else 'A' if score >= 75 else 'B' if score >= 60
                 else 'C' if score >= 40 else 'D')
        # 守卫：运行中被用户取消的，结果丢弃、状态不翻转、积分不退（用户拍板）
        db.execute(
            "UPDATE scans SET results=?, score=?, grade=?, issue_count=?, "
            "scan_status='completed', scan_progress=100, scan_progress_text='扫描完成', "
            "duration_seconds=? "
            "WHERE scan_id=? AND scan_status='pending'",
            (json.dumps({'issues': issues, 'result': r}, ensure_ascii=False, default=str),
             score, grade, len(issues), round(time.time() - _t0, 2), scan_id))
        db.commit()
    except Exception as e:
        cur = db.execute("SELECT scan_status FROM scans WHERE scan_id=?",
                         (scan_id,)).fetchone()
        if cur and cur['scan_status'] == 'pending':
            db.execute("UPDATE scans SET scan_status='failed', scan_error=? "
                       "WHERE scan_id=?", (str(e)[:500], scan_id))
            db.commit()
            if cost > 0:
                grant_credits(user_id, cost, ref_type='refund', ref_id=scan_id,
                              remark='API扫描失败退款')
    finally:
        if _ticker_stop:
            _ticker_stop.set()
        _discard_queue_payload(scan_id)
    return True


def count_active_scans():
    """当前在跑的任务数。

    巡检脚本据此判断「此刻重启会不会打断客户」——官网进程里跑着扫描线程，
    重启等于把客户正在等的任务掐断。健康检查端点也把它透出来。
    """
    try:
        db = get_db()
        row = db.execute(
            "SELECT COUNT(*) FROM scans WHERE scan_status='pending'").fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0


def _reap_stale_scans():
    """卡死兜底：在途超时判死退款；排队超 24h 自动取消（从未扣费）；
    遗留非受管状态（如老代码写过的 'running'）按同一套心跳规则兜底收割。"""
    db = get_db()
    stuck = db.execute(
        "SELECT scan_id, user_id, credits_spent FROM scans WHERE scan_status='pending' "
        # 判活看心跳而不是看提交时间：大文件分片扫描合法可达数十分钟，
        # 只要分片循环还在刷新心跳就不是卡死（心跳停更才判死）
        "AND COALESCE(last_heartbeat_at, created_at) < datetime('now','+8 hours','-%d seconds')"
        % _HEARTBEAT_SILENCE_SECONDS).fetchall()
    for r in stuck:
        done = db.execute(
            "UPDATE scans SET scan_status='failed', "
            "scan_error='扫描中断：心跳停止超过 %d 秒，执行它的进程已不在' "
            "WHERE scan_id=? AND scan_status='pending'"
            % _HEARTBEAT_SILENCE_SECONDS, (r['scan_id'],)).rowcount
        db.commit()
        if done and (r['credits_spent'] or 0) > 0:
            grant_credits(r['user_id'], r['credits_spent'], ref_type='refund',
                          ref_id=r['scan_id'], remark='API扫描超时退款')
    # 遗留状态兜底：老版本代码写过 'running' 等当前已不再产生的状态，而调度/占位/
    # 轮询/收割都只认 pending/queued——这类行会永久滞留，任何规则都看不见它。
    # 按同一套心跳判活规则一并收割（判活看心跳，不停更才判死）。
    # NULL 状态是老内部 API 的已交付历史单（库内近千条带扣费记录），不是在途任务，
    # 明确排除，否则会把已交付的扫描误判失败并重复退款。
    legacy = db.execute(
        "SELECT scan_id, user_id, credits_spent FROM scans "
        "WHERE scan_status IS NOT NULL "
        "AND scan_status NOT IN ('completed','failed','cancelled','pending','queued') "
        "AND COALESCE(last_heartbeat_at, created_at) < datetime('now','+8 hours','-%d seconds')"
        % _HEARTBEAT_SILENCE_SECONDS).fetchall()
    for r in legacy:
        done = db.execute(
            "UPDATE scans SET scan_status='failed', "
            "scan_error='扫描超时中断（遗留状态兜底收割）' "
            "WHERE scan_id=? AND scan_status IS NOT NULL "
            "AND scan_status NOT IN ('completed','failed','cancelled','pending','queued')",
            (r['scan_id'],)).rowcount
        db.commit()
        if done and (r['credits_spent'] or 0) > 0:
            grant_credits(r['user_id'], r['credits_spent'], ref_type='refund',
                          ref_id=r['scan_id'], remark='API扫描超时退款(遗留状态兜底)')
    db.execute(
        "UPDATE scans SET scan_status='cancelled', "
        "scan_error='排队超过24小时自动取消' "
        "WHERE scan_status='queued' AND created_at < datetime('now','+8 hours','-1 day')")
    db.commit()



def _queue_dispatcher_loop():
    while True:
        try:
            with app.app_context():
                _reap_stale_scans()
                _dispatch_queued_scans()
        except Exception as e:
            try:
                logger.exception('queue dispatcher error: %s', e)
            except Exception:
                pass
        time.sleep(2)


def _log_dispatcher_owner():
    """记下是谁启动了调度器。

    调度器会认领并执行排队任务，全局只该有一个。2026-11-14 之前本函数在**模块导入时**
    就被调用，于是任何 `from modules import api` 的进程（QA 的 pytest、巡检脚本、
    工具脚本）都会抢队列任务，还会把生产在途任务当成「自己重启前的遗留」清掉。
    现在只在服务入口 app.py 里启动；谁再在别处起，这条日志会点名。
    """
    try:
        me = _os.getpid()
        cmd = _proc_cmdline(me)
        ppid = 0
        try:
            with open('/proc/%d/stat' % me, 'rb') as f:
                ppid = int(f.read().rsplit(b') ', 1)[-1].split()[1])
        except Exception:
            pass
        log_dir = _os.path.join(
            _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), 'logs')
        _os.makedirs(log_dir, exist_ok=True)
        with open(_os.path.join(log_dir, 'dispatcher_owner.log'), 'a',
                  encoding='utf-8') as f:
            f.write('[%s] pid=%d ppid=%d cmd=%s parent=%s\n' % (
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'), me, ppid,
                cmd, _proc_cmdline(ppid)))
    except Exception:
        pass


def _proc_cmdline(pid):
    try:
        with open('/proc/%d/cmdline' % int(pid), 'rb') as f:
            return f.read().replace(b'\x00', b' ').decode('utf-8', 'replace').strip()[:200]
    except Exception:
        return ''


def start_queue_dispatcher():
    """启动队列调度器。只许服务入口 app.py 调用，不许在模块导入时调用。"""
    if _dispatcher_guard.is_set():
        return
    _dispatcher_guard.set()
    _log_dispatcher_owner()
    _threading.Thread(target=_queue_dispatcher_loop, daemon=True,
                      name='scan-queue-dispatcher').start()


def _status_queued(resp, db, row, scan_id):
    """排队状态：补充队列位置、预计等待、取消链接。"""
    resp['queue_position'] = _queue_position(
        db, row['created_at'], row['total_lines'], row['rid'])
    resp['credits_used'] = 0
    resp['server_slots'] = _slot_limit()
    resp['fast_lane'] = (row['total_lines'] or 0) <= 2000
    # 预计等待：0.06 秒/行 估算（实测 148KB/6400 行大任务 406s ≈ 0.063 s/行）
    _wait = 0.0
    for _r in db.execute(
            "SELECT COALESCE(total_lines,0) tl, COALESCE(total_bytes,0) tb "
            "FROM scans WHERE scan_status IN ('pending','queued')"):
        _wait += _estimate_scan_seconds(_r['tl'], _r['tb'])
    resp['estimated_wait_seconds'] = int(_wait)
    try:
        _qt0 = datetime.strptime((row['created_at'] or '')[:19], '%Y-%m-%d %H:%M:%S')
        resp['elapsed_seconds'] = int(max(
            0.0, (datetime.now() - _qt0).total_seconds()))
    except Exception:
        pass
    resp['message'] = (
        '排队中（不扣积分）。%s轮到自动开始；可随时免费取消'
        % ('小任务优先通道，' if (row['total_lines'] or 0) <= 2000 else ''))
    resp['cancel_url'] = '/api/v1/scan/%s/cancel' % scan_id


def _status_pending(resp, row):
    """执行中状态：补充已用时、预计剩余。"""
    resp['credits_used'] = row['credits_spent'] or 0
    _est = _estimate_scan_seconds(row['total_lines'], row['tb'])
    try:
        _t0 = datetime.strptime((row['created_at'] or '')[:19], '%Y-%m-%d %H:%M:%S')
        _elapsed = max(0.0, (datetime.now() - _t0).total_seconds())
    except Exception:
        _elapsed = 0.0
    resp['elapsed_seconds'] = int(_elapsed)
    resp['estimated_total_seconds'] = int(_est)
    resp['estimated_remaining_seconds'] = max(0, int(_est - _elapsed))
    if not resp.get('progress_text'):
        resp['progress_text'] = '代码分析中'


def _status_completed(resp, row):
    """完成状态：重建完整扫描报告。"""
    try:
        blob = json.loads(row['results'])
        result = (blob.get('result')
                  if isinstance(blob, dict) and isinstance(blob.get('result'), dict)
                  else blob)
        issues = blob.get('issues') or (
            result.get('issues', []) if isinstance(result, dict) else [])
        names = json.loads(row['files_meta']) if row['files_meta'] else []
        scan_ctx = {
            'issues': issues,
            'result': result if isinstance(result, dict) else {'issues': issues},
            'code_files': {n: '' for n in names},
            'total_lines': row['total_lines'] or 0,
            'scan_cost': row['credits_spent'] or 0,
            'user_id': row['user_id'],
            'language': row['language'] or 'auto',
        }
        full, _sc = _build_scan_response(scan_ctx)
        resp.update(full)
        resp['status'] = 'completed'
        resp['credits_used'] = row['credits_spent'] or 0
    except Exception as e:
        resp['result_error'] = '结果重建失败: %s' % e
        resp['score'] = row['score']
        resp['grade'] = row['grade']
        resp['total_issues'] = row['issue_count']


@api_bp.route('/api/v1/scan/status/<scan_id>', methods=['GET'])
def api_scan_status(scan_id):
    """API 钥匙版任务状态查询（排队位置 / 进度 / 完成后交付完整结果）。"""
    api_key = request.headers.get('X-API-Key', '')
    user_info = validate_api_key(api_key)
    if not user_info:
        return jsonify({'error': '无效或未激活的 API Key'}), HTTP_UNAUTHORIZED
    db = get_db()
    row = db.execute(
        "SELECT user_id, scan_status, scan_progress, scan_progress_text, scan_error, "
        "score, grade, issue_count, results, credits_spent, created_at, total_lines, "
        "file_count, files_meta, language, rowid AS rid, COALESCE(total_bytes, 0) AS tb "
        "FROM scans WHERE scan_id=?",
        (scan_id,)).fetchone()
    if not row or row['user_id'] != user_info['user_id']:
        return jsonify({'error': '扫描记录不存在'}), HTTP_NOT_FOUND
    st = row['scan_status'] or 'unknown'
    resp = {'scan_id': scan_id, 'status': st,
            'progress': row['scan_progress'] or 0,
            'progress_text': row['scan_progress_text'] or '',
            'submitted_at': row['created_at']}
    if row['scan_error']:
        resp['error'] = row['scan_error']
    if st == 'queued':
        _status_queued(resp, db, row, scan_id)
    elif st == 'pending':
        _status_pending(resp, row)
    elif st == 'completed':
        _status_completed(resp, row)
    elif st in ('failed', 'cancelled'):
        resp['credits_used'] = row['credits_spent'] or 0
    return jsonify(resp)


@api_bp.route('/api/v1/scan/<scan_id>/cancel', methods=['POST'])
def api_cancel_scan(scan_id):
    """取消任务：排队中免费取消；运行中取消不退积分、结果丢弃。"""
    api_key = request.headers.get('X-API-Key', '')
    user_info = validate_api_key(api_key)
    if not user_info:
        return jsonify({'error': '无效或未激活的 API Key'}), HTTP_UNAUTHORIZED
    user_id = user_info['user_id']
    db = get_db()
    row = db.execute(
        "SELECT user_id, scan_status, credits_spent FROM scans WHERE scan_id=?",
        (scan_id,)).fetchone()
    if not row or row['user_id'] != user_id:
        return jsonify({'error': '扫描记录不存在'}), HTTP_NOT_FOUND
    st = row['scan_status']
    if st == 'queued':
        db.execute(
            "UPDATE scans SET scan_status='cancelled', "
            "scan_error='用户取消（排队中，全程未扣费）' "
            "WHERE scan_id=? AND scan_status='queued'", (scan_id,))
        db.commit()
        _discard_queue_payload(scan_id)
        return jsonify({
            'status': 'cancelled', 'scan_id': scan_id,
            'charged': 0, 'refunded': 0,
            'message': '排队任务已取消，全程未扣积分'}), HTTP_OK
    if st == 'pending':
        db.execute(
            "UPDATE scans SET scan_status='cancelled', "
            "scan_error='用户取消（运行中中断，积分不退）' "
            "WHERE scan_id=? AND scan_status='pending'", (scan_id,))
        db.commit()
        return jsonify({
            'status': 'cancelled', 'scan_id': scan_id,
            'charged': row['credits_spent'] or 0, 'refunded': 0,
            'message': '运行中任务已标记取消，已扣积分不退回，扫描结果将不再交付'}), HTTP_OK
    return jsonify({'error': '任务已结束，无法取消', 'status': st}), HTTP_BAD_REQUEST


# 调度器不在这里启动：模块被任何进程导入（测试、巡检、工具脚本）都不该起调度线程。
# 服务入口见 app.py 的 __main__。

def _replay_scan_or_none(user_id, code_files, language, content_hash):
    """幂等复用：同内容重复提交 -> 复用结果不重算，积分照扣。返回 (response, status) 或 None。"""
    _prev = _find_reusable_scan(get_db(), user_id, content_hash)
    if _prev is None:
        return None
    _rep = _replay_scan_response(_prev, user_id)
    if _rep is None:
        return None
    if _prev[6] in ('pending', 'queued'):
        return jsonify(_rep), HTTP_OK
    # 已完成：先确认响应能构建，再扣费（扣费失败/余额不足直接报错，绝不白给）
    _lines = _prev[2] or 0
    _cost = calculate_scan_cost(_lines, is_full_scan=True, user_id=user_id)
    _used, _err = _process_api_credits(user_id, _cost)
    if _err:
        return _err
    _rep["credits_used"] = _used
    # 复用结果也要"像真的扫过一遍"（用户拍板）：以该任务上次真实耗时为基准
    # 上下浮动几秒再返回。省的是 token，不是客户的体感。
    # 表演耗时的锚 = 该内容【首次真实扫描】耗时（用户拍板：重复应略快
    # 且稳定；若逐次递减，扫十次会越演越短，明显失真）
    _first_row = get_db().execute(
        "SELECT COALESCE(duration_seconds,0) d FROM scans "
        "WHERE user_id=? AND content_hash=? AND scan_status='completed' "
        "AND COALESCE(is_replay,0)=0 AND COALESCE(duration_seconds,0)>0 "
        "ORDER BY created_at ASC LIMIT 1",
        (user_id, content_hash)).fetchone()
    _first_dur = (_first_row['d'] if _first_row
                  else (_prev[10] if len(_prev) > 10 else 0))
    _elapsed = _simulate_scan_duration(_first_dur, _lines)
    _rep["duration_seconds"] = round(_elapsed, 2)
    # 扣过费必须落账（5.1 教训）：复用也插一条 scans 记录
    try:
        _blob = json.loads(_prev[1])
        _result = (_blob.get('result')
                   if isinstance(_blob, dict) and isinstance(_blob.get('result'), dict)
                   else _blob)
        _names = json.loads(_prev[4]) if _prev[4] else []
        _ctx = {
            'user_id': user_id,
            'code_files': {n: '' for n in _names},
            'result': _result if isinstance(_result, dict) else {'issues': []},
            'language': _prev[5] or 'auto',
            'scan_cost': _used, 'total_lines': _lines,
            'content_hash': content_hash,
            'duration_seconds': _elapsed,
            'is_replay': 1,
        }
        _save_api_scan_history(get_db(), _ctx, _prev[8] or 0, _prev[9] or '')
    except Exception as _e:
        logger.exception("replay history save failed: %s", _e)
    return jsonify(_rep), HTTP_OK


def _check_scan_limits(code_files, total_lines):
    """单次提交能力边界校验。超限返回 (response, 413)，否则返回 None。"""
    _MAX_FILES = SCAN_MAX_FILES
    _MAX_BYTES = SCAN_MAX_BYTES
    _MAX_LINES = SCAN_MAX_LINES
    _total_bytes = sum(len(v) for v in code_files.values() if isinstance(v, str))
    if not (len(code_files) > _MAX_FILES or _total_bytes > _MAX_BYTES
            or total_lines > _MAX_LINES):
        return None, _total_bytes
    _over = []
    if len(code_files) > _MAX_FILES:
        _over.append('文件数 %d > %d' % (len(code_files), _MAX_FILES))
    if _total_bytes > _MAX_BYTES:
        _over.append('代码量 %.1fMB > 10MB' % (_total_bytes / 1024.0 / 1024.0))
    if total_lines > _MAX_LINES:
        _over.append('有效行数 %d > %d' % (total_lines, _MAX_LINES))
    return jsonify({
        'error': '单次提交超出极限规模',
        'reason': '；'.join(_over),
        'limit': {'files': _MAX_FILES, 'bytes': _MAX_BYTES, 'lines': _MAX_LINES},
        'yours': {'files': len(code_files), 'bytes': _total_bytes,
                  'lines': total_lines},
        'message': ('单次极限为 %d 个文件 / 10MB / %d 行，您的提交已超出。'
                    '普通项目请直接整包提交（文件大只是检查时间更长）；'
                    '超出此规模请联系管理员定制扫描。'
                    % (_MAX_FILES, _MAX_LINES)),
        'credits_used': 0,
    }), 413


def _enqueue_if_busy(user_id, code_files, language, total_lines, content_hash,
                     _total_bytes, scan_cost, _chunked):
    """排队闸门：同账号串行 + 服务器槽位限制。需排队返回 (response, HTTP_OK)，否则 None。"""
    _qdb = get_db()
    _my_active = _qdb.execute(
        "SELECT COUNT(*) FROM scans WHERE user_id=? "
        "AND scan_status IN ('pending','queued')", (user_id,)).fetchone()[0]
    _running = _qdb.execute(
        "SELECT COUNT(*) FROM scans WHERE scan_status='pending'").fetchone()[0]
    _slots = _slot_limit()
    if not (_my_active or _running >= _slots):
        return None
    _qid = _enqueue_scan(_qdb, user_id, code_files, language, total_lines,
                     content_hash, _total_bytes)
    _qm = _qdb.execute(
        "SELECT created_at, rowid AS rid FROM scans WHERE scan_id=?", (_qid,)).fetchone()
    _pos = _queue_position(_qdb, _qm['created_at'], total_lines, _qm['rid'])
    return jsonify({
        'status': 'queued',
        'scan_id': _qid,
        'queue_position': _pos,
        'credits_used': 0,
        'queue_reason': ('您的账号已有任务在跑或在排队（同一账号串行执行）'
                         if _my_active else '服务器并行槽位已满，按提交顺序排队'),
        'server_slots': _slots,
        'fast_lane': total_lines <= 2000,
        'estimated_wait_seconds': int(sum(
            _estimate_scan_seconds(_r['tl'], _r['tb']) for _r in _qdb.execute(
                "SELECT COALESCE(total_lines,0) tl, COALESCE(total_bytes,0) tb "
                "FROM scans WHERE scan_status IN ('pending','queued')"))),
        'message': ('%s；本任务已入队（排队不扣积分，轮到执行时扣 %d 分）%s；排队中可随时免费取消%s'
                    % ('您的账号已有任务在跑或在排队（同一账号串行执行）'
                       if _my_active else '服务器当前有任务在执行，按提交顺序排队',
                       scan_cost,
                       '，小任务优先插队' if total_lines <= 2000 else '',
                       '；代码量较大，将逐文件依次检查，耗时会更长' if _chunked else '')),
        'poll_url': '/api/v1/scan/status/%s' % _qid,
        'cancel_url': '/api/v1/scan/%s/cancel' % _qid,
    }), HTTP_OK


def _start_async_scan(user_id, key_id, code_files, language, user_thresholds,
                      total_lines, content_hash, credits_used, _chunked):
    """异步扫描：>100KB 立即返回 scan_id，后台线程执行。返回 (response, HTTP_OK)。"""
    db = get_db()
    total_code_size = sum(len(v) for v in code_files.values() if isinstance(v, str))
    scan_id = f"api_scan_{int(time.time() * 1000)}_{user_id}"
    db.execute(
        "INSERT INTO scans (scan_id, user_id, title, file_count, files_meta, results, score, grade, issue_count, language, created_at, credits_spent, total_lines, scan_mode, source, scan_status, content_hash, total_bytes) VALUES (?, ?, ?, ?, ?, '[]', 0, '', 0, ?, ?, ?, ?, 'full', 'api', 'pending', ?, ?)",
        (scan_id, user_id, f"API扫描({len(code_files)}个文件)", len(code_files),
         json.dumps(list(code_files.keys()), ensure_ascii=False),
         language, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
         credits_used, total_lines, content_hash, int(total_code_size or 0))
    )
    db.commit()

    def _bg_scan():
        _t_bg = time.time()
        _chunks_bg = _plan_scan_chunks(code_files)
        _ticker_stop = None
        if len(_chunks_bg) <= 1:
            # 单片任务没有中间进度可报，用心跳匀速推进；多片由分片循环实时报进度
            _ticker_stop = _start_progress_ticker(scan_id, total_lines, total_code_size)
        try:
            issues, r = _execute_scan_in_chunks(
                scan_id, code_files, language, user_thresholds,
                user_id, total_lines)
            score = max(0, 100 - sum(
                {'critical': 10, 'blocker': 15, 'high': 5, 'medium': 3, 'low': 0.5}.get(i.get('severity',''), 0)
                for i in issues
            ))
            grade = 'S' if score >= 90 else 'A' if score >= 75 else 'B' if score >= 60 else 'C' if score >= 40 else 'D'
            _db = get_db()
            _db.execute("UPDATE scans SET results=?, score=?, grade=?, issue_count=?, scan_status='completed', scan_progress=100, scan_progress_text='扫描完成', duration_seconds=? WHERE scan_id=? AND scan_status='pending'",
                (json.dumps({'issues': issues, 'result': r}, ensure_ascii=False, default=str), score, grade, len(issues), round(time.time() - _t_bg, 2), scan_id))
            _db.commit()
        except Exception as e:
            try:
                _db = get_db()
                _db.execute("UPDATE scans SET scan_status='failed', scan_error=? WHERE scan_id=? AND scan_status='pending'", (str(e)[:500], scan_id))
                _db.commit()
                if credits_used > 0:
                    from modules.scoring import grant_credits as _gc
                    _gc(user_id, credits_used, ref_type='refund', ref_id=str(key_id), remark='API扫描失败退款')
                    _db.commit()
            except Exception as e2:
                logger.exception('_bg_scan 收尾失败: %s (原异常: %s)', e2, e)
        finally:
            if _ticker_stop:
                _ticker_stop.set()

    def _bg_scan_with_ctx():
        # 后台线程无请求上下文，get_db() 依赖 flask.g -> 必须包 app_context
        with app.app_context():
            _bg_scan()
    import threading
    threading.Thread(target=_bg_scan_with_ctx, daemon=True).start()

    return jsonify({
        'status': 'processing',
        'scan_id': scan_id,
        'message': (f'大项目扫描已提交（{total_code_size/1024:.0f}KB，{total_lines} 行'
                    + ('，将逐文件依次检查' if _chunked else '')
                    + '）。请轮询获取结果，进度会显示正在检查哪些文件'),
        'poll_url': f'/api/v1/scan/status/{scan_id}',
        'cancel_url': f'/api/v1/scan/{scan_id}/cancel',
        'estimated_seconds': int(_estimate_scan_seconds(total_lines, total_code_size)),
        'credits_used': credits_used,
    }), HTTP_OK


def _run_sync_scan(user_id, key_id, code_files, language, user_thresholds,
                   total_lines, content_hash, credits_used):
    """同步扫描：<100KB 阻塞执行。成功返回 (issues, result)；失败返回 (None, response, 503)。"""
    db = get_db()
    try:
        _sync_issues, result = _execute_scan_in_chunks(
            None, code_files, language, user_thresholds, user_id, total_lines)
        return _sync_issues, result
    except ScanEngineError as e:
        if credits_used > 0:
            grant_credits(
                user_id, credits_used,
                ref_type='refund', ref_id=str(key_id),
                remark='API扫描失败退款',
            )
        # 5.1 修复（2026-10-23）：同步失败也留痕——扣过费的扫描必须有账可查，
        # 不能只退款了事（历史上 43% 失败率无任何扫描记录，客户无从对账）
        try:
            import uuid as _uuid2
            _fid = _uuid2.uuid4().hex
            _fnames = list(code_files.keys())
            db.execute(
                "INSERT INTO scans (scan_id, user_id, title, file_count, "
                "files_meta, results, score, grade, issue_count, language, "
                "created_at, credits_spent, total_lines, scan_mode, source, "
                "scan_status, scan_error, content_hash) "
                "VALUES (?, ?, ?, ?, ?, '[]', 0, '', 0, ?, ?, 0, ?, 'full', "
                "'api', 'failed', ?, ?)",
                (_fid, user_id,
                 ("%s 等 %d 个文件" % (_fnames[0], len(_fnames)))
                 if len(_fnames) > 1 else (_fnames[0] if _fnames else "API扫描"),
                 len(_fnames),
                 json.dumps(_fnames, ensure_ascii=False),
                 language,
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 total_lines, str(e)[:500], content_hash)
            )
        except Exception as _se:
            logger.exception("failed-scan 落库失败: %s", _se)
        db.commit()
        return None, jsonify({
            'error': '扫描服务暂时不可用，请稍后重试',
            'detail': str(e),
        }), 503


@api_bp.route('/api/v1/scan', methods=['POST'])
def api_scan():
    """Scan API endpoint with credits system."""
    _t_start = time.time()
    # 1. 参数验证
    user_info, code_files, language, err = _validate_api_scan_request()
    if err:
        return err

    user_id = user_info['user_id']
    key_id = user_info['id']

    content_hash = _scan_fingerprint(code_files, language)
    _replay = _replay_scan_or_none(user_id, code_files, language, content_hash)
    if _replay is not None:
        return _replay

    # 2. 计算费用
    total_lines = sum(
        sum(1 for ln in c.split('\n') if ln.strip())
        for c in code_files.values() if isinstance(c, str)
    )
    scan_cost = calculate_scan_cost(total_lines, is_full_scan=True, user_id=user_id)

    # 单次提交能力边界（硬顶防失控；正常多大的项目都整包收下、自动分片）
    _limit_resp = _check_scan_limits(code_files, total_lines)
    if _limit_resp[0] is not None:
        return _limit_resp
    _total_bytes = _limit_resp[1]

    # 分片是内部机制，对客户不可见（进度只说在检查哪些文件，不说分了几片）
    _chunks = _plan_scan_chunks(code_files)
    _chunked = len(_chunks) > 1

    # 排队闸门（排队不扣积分，出队真正开始跑才扣）
    _q_resp = _enqueue_if_busy(user_id, code_files, language, total_lines,
                               content_hash, _total_bytes, scan_cost, _chunked)
    if _q_resp is not None:
        return _q_resp

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
        return _start_async_scan(user_id, key_id, code_files, language,
                                 user_thresholds, total_lines, content_hash,
                                 credits_used, _chunked)

    # 同步模式（<100KB，客户契约：POST 阻塞直到返回完整报告）
    _sync_result = _run_sync_scan(user_id, key_id, code_files, language,
                                  user_thresholds, total_lines, content_hash,
                                  credits_used)
    if len(_sync_result) == 3:  # 出错时返回 (None, error_response, status)
        return _sync_result[1], _sync_result[2]
    issues, result = _sync_result

    issues = result.get('issues', [])

    # 6. 构建响应 + 保存历史
    scan_ctx = {
        'issues': issues, 'result': result, 'code_files': code_files,
        'total_lines': total_lines, 'scan_cost': credits_used,
        'user_id': user_id, 'language': language,
        'content_hash': content_hash,
        'duration_seconds': time.time() - _t_start,
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
                    "brain_name": brain_label(issue.get("brain_id", "")),
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
        logger.exception('Failed to create API key: %s', e)
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
def _derive_score_grade(results, issues):
    """从结果中推导评分与等级（缺失时用简单算法兜底）。返回 (score, grade)。"""
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
    return score, grade


def _extract_file_info(results):
    """从结果中提取文件信息。返回 (file_count, file_names)。"""
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
    return file_count, file_names


def _make_upload_title(file_names):
    """根据文件名生成扫描标题。"""
    if file_names:
        return file_names[0] if len(file_names) == 1 else "{} 等 {} 个文件".format(file_names[0], len(file_names))
    return "CLI上传 {}".format(datetime.now().strftime('%m-%d %H:%M'))


def _count_severities(issues):
    """按严重级别统计 issue 数量。返回 dict。"""
    severity_counts = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
    for issue in issues:
        if isinstance(issue, dict):
            sev = str(issue.get('severity', '')).lower()
            for key in severity_counts:
                if key in sev or sev in key:
                    severity_counts[key] += 1
                    break
    return severity_counts


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
    issue_count = len(issues) if isinstance(issues, list) else 0
    score, grade = _derive_score_grade(results, issues)
    file_count, file_names = _extract_file_info(results)

    language = data.get('language', results.get('language', ''))
    project_tag = data.get('project_tag', '')
    total_lines = results.get('total_lines', 0)
    title = _make_upload_title(file_names)

    # 4. 存入 scans 表
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

        # 5. 同时写入 scan_metrics 表
        severity_counts = _count_severities(issues)
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
    if "user_id" not in session or not is_admin_user(session.get("user_id")):
        return jsonify({"error": "admin required"}), 403
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
    if "user_id" not in session or not is_admin_user(session.get("user_id")):
        return jsonify({"error": "admin required"}), 403
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
    if "user_id" not in session or not is_admin_user(session.get("user_id")):
        return jsonify({"error": "admin required"}), 403
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
    if "user_id" not in session or not is_admin_user(session.get("user_id")):
        return jsonify({"error": "admin required"}), 403
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
    if "user_id" not in session or not is_admin_user(session.get("user_id")):
        return jsonify({"error": "admin required"}), 403
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
    if "user_id" not in session or not is_admin_user(session.get("user_id")):
        return jsonify({"error": "admin required"}), 403
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
