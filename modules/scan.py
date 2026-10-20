"""Xinpect - Scan routes, reports, component check"""
import hashlib
import time
import io
import os
import re
import json
import uuid
import zipfile
import tarfile
import sqlite3
from datetime import datetime
from urllib.parse import quote

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    session, flash, jsonify, g, make_response
)

from .scan_worker import job_manager, init_scan_tables
from .constants import (
    app, logger, DB_PATH,
    BRAINS, BRAINS_MAP, TIERS, TIERS_MAP,
    FREE_BRAIN_IDS, ALL_BRAIN_IDS, FREE_BRAIN_ID_SET,
    CODE_EXTS, ARCHIVE_SKIP_DIRS,
    MAX_CONTENT_LENGTH, MAX_FILE_SIZE_SINGLE, MAX_CODE_LENGTH,
    MAX_CONTENT_SIZE_MB, ESTIMATED_UNZIP_FACTOR, ESTIMATED_LINE_SIZE,
    MIN_ESTIMATED_LINES, MIN_ESTIMATED_SIZE_ADDITION,
    MOCK_SCAN_TIMEOUT,
    SCAN_COST_BASE_FEE, SCAN_COST_PER_100_LINES_FULL,
    DAILY_LIMIT_FREE,
    CC_SCORE_S, CC_SCORE_A, CC_SCORE_B,
    MAX_WXML_CODE_LENGTH,
    HTTP_OK, HTTP_BAD_REQUEST, HTTP_UNAUTHORIZED, HTTP_NOT_FOUND, HTTP_INTERNAL_ERROR,
    HTTP_PAYMENT_REQUIRED, HTTP_ENTITY_TOO_LARGE,
    SCANNER_URL, REPORT_TIMEOUT_SECONDS,
)
from .db import get_db
from .helpers import login_required, get_current_user, is_vip_user, _safe_http_post, _safe_http_get
from .scoring import (
    get_user_credits, consume_credits, grant_credits,
    calculate_scan_cost, count_total_lines, check_credit_sufficient,
    calculate_tier_scores, calculate_overall_grade,
    calculate_score, calculate_dimension_score, calculate_building_block_scores,
    score_to_grade, score_color, severity_label,
    get_daily_usage, check_daily_limit, increment_daily_usage,
)
from .fix_roadmap import build_fix_roadmap, build_fix_progress
from .csrf_protection import csrf_required
from .scanner import call_scanner, _extract_code_snippet, ScanEngineError


scan_bp = Blueprint("scan", __name__)


# ============================================================
# 文件收集与解析
# ============================================================

def _build_estimate_response(file_count, total_lines, request_scan_mode=None):
    """构造预估接口的统一返回（支持 VIP 和免费版，按scan_mode计费）"""
    vip = is_vip_user()

    user = get_current_user()
    user_id = user.get('id') if user else None

    # 确定实际scan_mode
    if not vip:
        actual_mode = 'free'
    elif request_scan_mode and request_scan_mode in ('quick', 'smart', 'deep'):
        actual_mode = request_scan_mode
    else:
        actual_mode = 'quick'  # 会员默认quick

    if vip:
        credits_cost = calculate_scan_cost(total_lines, scan_mode=actual_mode)
        credit_balance = get_user_credits(user_id)
        sufficient = check_credit_sufficient(user_id, credits_cost)
        
        # 计算每300行单价
        mode_rates = {'quick': 1, 'smart': 2, 'deep': 4}
        price_per_300 = mode_rates.get(actual_mode, 1)
        
        return jsonify({
            'ok': True, 'file_count': file_count, 'total_lines': total_lines,
            'scan_mode': actual_mode, 'is_vip': True,
            'cost': credits_cost, 'credits_cost': credits_cost,
            'credit_balance': credit_balance, 'is_sufficient': sufficient,
            'price_per_300': price_per_300,
        })
    return jsonify({
        'ok': True, 'file_count': file_count, 'total_lines': total_lines,
        'scan_mode': 'free', 'is_vip': False,
        'cost': 0, 'daily_remaining': DAILY_LIMIT_FREE, 'daily_allowed': True,
        'free_file_limit': None, 'over_file_limit': False,
    })


def _is_archive_filename(filename):
    """判断是否为压缩包文件"""
    lower = filename.lower()
    return (
        lower.endswith('.zip') or lower.endswith('.tar')
        or lower.endswith('.tgz') or lower.endswith('.tar.gz')
    )


def _extract_code_from_archive(file_storage):
    """从压缩包中提取代码文件，返回 {path: content} 字典。
    支持 .zip / .tar.gz / .tgz / .tar 格式。
    """
    result = {}
    filename = file_storage.filename.lower()
    data = file_storage.read()

    try:
        if filename.endswith('.zip'):
            _extract_zip_data(data, result)
        elif filename.endswith(('.tar.gz', '.tgz', '.tar')):
            _extract_tar_data(data, result)
    except (zipfile.BadZipFile, tarfile.TarError, OSError) as e:
        logger.warning('压缩包解析失败: %s', e)
    return result


def _extract_zip_data(data, result):
    """从 zip 数据中提取代码文件"""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename
            if any(x in name for x in ARCHIVE_SKIP_DIRS) or name.startswith('.') or '/.' in name:
                continue
            if os.path.splitext(name)[1].lower() not in CODE_EXTS:
                continue
            try:
                with zf.open(info) as zf_file:
                    file_content = zf_file.read().decode('utf-8', errors='replace')
                parts = name.split('/', 1)
                display_name = parts[1] if len(parts) > 1 else parts[0]
                result[display_name] = file_content
            except (UnicodeDecodeError, KeyError):
                logger.debug('skip undecodable file in archive')
            except (OSError, IOError) as _arch_err:
                logger.debug('skip file parse error in archive: %s', _arch_err)


def _extract_tar_data(data, result):
    """从 tar 数据中提取代码文件"""
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:*') as tf:
        for member in tf.getmembers():
            if not member.isfile():
                continue
            name = member.name
            if any(x in name for x in ARCHIVE_SKIP_DIRS) or name.startswith('.') or '/.' in name:
                continue
            if os.path.splitext(name)[1].lower() not in CODE_EXTS:
                continue
            try:
                tf_file = tf.extractfile(member)
                if tf_file:
                    file_content = tf_file.read().decode('utf-8', errors='replace')
                    parts = name.split('/', 1)
                    display_name = parts[1] if len(parts) > 1 else parts[0]
                    result[display_name] = file_content
            except (UnicodeDecodeError, KeyError):
                logger.debug('skip undecodable file in archive')
            except (OSError, IOError) as _arch_err:
                logger.debug('skip file in tar archive: %s', _arch_err)


def _collect_files_from_request():
    """从HTTP请求中收集代码文件，返回 files_dict。
    支持：上传文件（单文件/多文件/压缩包）、粘贴代码。
    """
    files_dict = {}
    uploaded_files = request.files.getlist('files')
    if uploaded_files and uploaded_files[0].filename:
        for f in uploaded_files:
            if f and f.filename:
                fname_lower = f.filename.lower()
                if _is_archive_filename(f.filename):
                    extracted = _extract_code_from_archive(f)
                    files_dict.update(extracted)
                else:
                    file_content = f.read().decode('utf-8', errors='replace')
                    files_dict[f.filename] = file_content

    code = request.form.get('code', '').strip()
    if code:
        fname = request.form.get('filename', 'code.txt') or 'code.txt'
        files_dict[fname] = code
    
    # v5.53: 过滤0字节空文件，避免浪费扫描资源
    files_dict = {k: v for k, v in files_dict.items() if v and v.strip()}
    
    return files_dict


# ============================================================
# 报告辅助函数
# ============================================================

def _format_visible_issues(all_issues, vip):
    """格式化可见问题列表（免费版只看规范层，加锁定标记）"""
    if vip:
        visible = list(all_issues)
    else:
        visible = [i for i in all_issues if str(i.get('brain_id')) in FREE_BRAIN_ID_SET]
    for _iss in visible:
        _iss['is_free_locked'] = True
    return visible


def _build_dimensions(all_issues, vip):
    """构建报告页维度数据列表"""
    dimensions = []
    for brain in BRAINS:
        brain_issues = [i for i in all_issues if str(i.get('brain_id')) == brain['id']]
        is_locked = (not vip) and (brain['id'] not in FREE_BRAIN_ID_SET)
        if is_locked:
            dimensions.append({
                'id': brain['id'], 'name': brain['name'],
                'score': '—', 'score_color': '#6b7280',
                'issues_count': '🔒', 'locked': True,
            })
        else:
            dim_score = calculate_dimension_score(brain_issues)
            dimensions.append({
                'id': brain['id'], 'name': brain['name'],
                'score': dim_score, 'score_color': score_color(dim_score),
                'issues_count': len(brain_issues), 'locked': False,
            })
    return dimensions


def _compute_severity_counts(visible_issues):
    """计算严重度统计（兼容新旧 severity 体系）"""
    _sev_map = {
        'critical': 'critical', 'blocker': 'critical',
        'high': 'high', 'suspicious': 'high',
        'medium': 'medium', 'correctness': 'medium', 'restriction': 'medium',
        'low': 'low', 'style': 'low',
        'info': 'info',
    }
    return {
        'critical': sum(1 for i in visible_issues if _sev_map.get(i.get('severity', ''), '') == 'critical'),
        'high':     sum(1 for i in visible_issues if _sev_map.get(i.get('severity', ''), '') == 'high'),
        'medium':   sum(1 for i in visible_issues if _sev_map.get(i.get('severity', ''), '') == 'medium'),
        'low':      sum(1 for i in visible_issues if _sev_map.get(i.get('severity', ''), '') == 'low'),
        'info':     sum(1 for i in visible_issues if _sev_map.get(i.get('severity', ''), '') == 'info'),
    }


def _issue_tier_assignment(visible_issues):
    """给每个issue标注所属层（用于前端筛选）"""
    _tier_map = {}
    for _t in TIERS:
        for _bid in _t['brain_ids']:
            _tier_map[_bid] = _t['key']
    for _iss in visible_issues:
        _bid = str(_iss.get('brain_id', ''))
        _iss['tier'] = _tier_map.get(_bid, 'unknown')


# ============================================================
# 扫描主流程拆分
# ============================================================

def _scan_credits_handling(vip, user_id, total_lines, file_count, scan_mode='quick'):
    """处理扫描积分逻辑。
    v5.53 修复竞态：移除独立的 check_credit_sufficient，由 consume_credits 原子处理。
    返回 (credits_cost, error_response)。error_response 非 None 表示失败。
    scan_mode: quick/smart/deep 决定计费倍率
    """
    if not vip:
        return 0, None

    credits_cost = calculate_scan_cost(total_lines, scan_mode=scan_mode)
    
    # 空文件或免费扫描，credits_cost=0，跳过扣费
    if credits_cost == 0:
        return 0, None
    
    # v5.53: consume_credits 内部已包含余额校验（BEGIN IMMEDIATE），无需单独检查
    success = consume_credits(
        user_id, credits_cost,
        ref_type='scan_pre', ref_id='pending',
        remark=f'扫描预扣：{total_lines}行，{file_count}个文件，{scan_mode}模式',
    )
    if not success:
        # 扣费失败 = 余额不足（consume_credits 已在事务内判断）
        balance = get_user_credits(user_id)
        return 0, (
            jsonify({
                'error': (
                    f'积分不足，本次扫描需 {credits_cost} 积分，'
                    f'当前余额 {balance} 积分'
                ),
                'credits_needed': credits_cost,
                'credits_balance': balance,
                'total_lines': total_lines,
                'scan_mode': 'full',
            }), HTTP_PAYMENT_REQUIRED
        )

    return credits_cost, None


def _execute_scanner_call(files_dict, brain_ids, language, vip, user_id):
    """调用扫描引擎，包含自定义阈值加载。
    返回 (results, error_response)。
    """
    user_thresholds = None
    if user_id:
        try:
            _db = get_db()
            _row = _db.execute(
                'SELECT config_json FROM scan_thresholds WHERE user_id=?', (user_id,)
            ).fetchone()
            if _row and _row[0]:
                user_thresholds = json.loads(_row[0])
        except Exception:
            pass

    scan_mode_for_scanner = 'full' if vip else 'basic'
    try:
        results = call_scanner(files_dict, brain_ids, {
            'language': language, 'scan_mode': scan_mode_for_scanner,
            'is_vip': vip, 'thresholds': user_thresholds,
        })
        return results, None
    except ScanEngineError as e:
        return None, (
            jsonify({'error': '扫描服务暂时不可用，请稍后重试', 'detail': str(e)}), 503
        )


def _save_scan_record(scan_info):
    """保存扫描记录到数据库。scan_info: dict with all scan fields."""
    db = get_db()
    db.execute('''
        INSERT INTO scans (scan_id, user_id, title, file_count, files_meta,
                          results, score, grade, issue_count, language,
                          credits_spent, total_lines, scan_mode, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        scan_info['scan_id'], scan_info['user_id'], scan_info['title'],
        scan_info['file_count'],
        json.dumps(scan_info['file_names'], ensure_ascii=False),
        json.dumps(scan_info['results'], ensure_ascii=False),
        scan_info['score'], scan_info['grade'], scan_info['issue_count'],
        scan_info['language'],
        scan_info['credits_cost'] if scan_info['user_id'] else 0,
        scan_info['total_lines'], scan_info['scan_mode'],
        scan_info.get('source', 'upload'),
    ))
    return db


def _update_credit_transaction(db, scan_info, vip):
    """更新积分流水 ref_id"""
    user_id = scan_info.get('user_id')
    if not vip or not user_id:
        return
    scan_id = scan_info['scan_id']
    total_lines = scan_info['total_lines']
    file_count = scan_info['file_count']
    last_tx = db.execute('''
        SELECT id FROM credit_transactions
        WHERE user_id = ? AND type = 'consume' AND ref_type = 'scan_pre'
        ORDER BY id DESC LIMIT 1
    ''', (user_id,)).fetchone()
    if last_tx:
        db.execute('''
            UPDATE credit_transactions
            SET ref_type = 'scan', ref_id = ?, remark = ?
            WHERE id = ?
        ''', (scan_id, f'扫描消耗：{total_lines}行，{file_count}个文件，完整版', last_tx['id']))


def _write_scan_metrics(db, scan_info, results):
    """写入技术债度量数据。scan_info: dict, results: scan results."""
    user_id = scan_info.get('user_id')
    if not user_id:
        return
    try:
        _sev = _compute_severity_counts(results.get('issues', []))
        _brain_scores = {
            str(bid): bd['score']
            for bid, bd in results.get('brain_results', {}).items()
            if isinstance(bd, dict) and bd.get('score') is not None
        }
        _project_tag = request.form.get('project_tag', '')
        db.execute("""
            INSERT INTO scan_metrics (user_id, scan_id, score, grade, issue_count,
                critical_count, high_count, medium_count, low_count,
                brain_scores_json, file_count, total_lines, duration_ms, scan_mode, project_tag)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id, scan_info['scan_id'], scan_info['score'], scan_info['grade'],
            results['total_issues'],
            _sev.get('critical', 0), _sev.get('high', 0),
            _sev.get('medium', 0), _sev.get('low', 0),
            json.dumps(_brain_scores), scan_info['file_count'],
            scan_info['total_lines'],
            results.get('total_elapsed', 0) * 1000,
            scan_info['scan_mode'], _project_tag,
        ))
    except Exception as _me:
        logger.warning('P3: Failed to write scan_metrics: %s', _me)


def _trigger_alerts_async(user_id, score, grade, results):
    """异步触发高危告警"""
    if not user_id:
        return
    import threading
    _alert_ctx = {
        'score': score,
        'grade': grade,
        'total_issues': results['total_issues'],
        'severity_counts': _compute_severity_counts(results.get('issues', [])),
    }
    threading.Thread(
        target=__import__('modules.alert', fromlist=['check_alerts_async']).check_alerts_async,
        args=(user_id, _alert_ctx, None),
        daemon=True,
    ).start()


def _evaluate_quality_gate(user_id, results, score, file_count):
    """评估质量门禁"""
    try:
        from modules.quality_gate import evaluate_gate, get_user_active_gate
        _active_gate = get_user_active_gate(user_id) if user_id else None
        if not _active_gate:
            return None
        _all_issues = results.get('issues', [])
        return evaluate_gate(_active_gate, score, results['total_issues'], _all_issues, file_count)
    except Exception as _ge:
        logger.warning('P1: gate evaluation failed: %s', _ge)
        return None


def _scan_visible_to_session(scan):
    """报告访问控制

    旧实现里 /report/<scan_id> 完全没有归属校验：任何拿到链接的人都能看到
    别人的源码片段。这里按"报告属于谁"判定：
      * 匿名扫描（user_id 为空）：scan_id 本身即不可猜的访问凭证，放行；
      * 已登录用户的扫描：只允许本人或管理员查看。
    """
    owner = scan['user_id'] if scan['user_id'] is not None else None
    if not owner:
        return True
    uid = session.get('user_id')
    if uid == owner:
        return True
    admin_id = int(os.environ.get('XINPECT_ADMIN_USER_ID', '6'))
    return uid == admin_id


def _generate_scan_id():
    """生成唯一的 scan_id"""
    _scan_seed = f"{uuid.uuid4()}{datetime.now().isoformat()}"
    return hashlib.sha256(_scan_seed.encode()).hexdigest()[:32]


def _build_scan_title(files_dict):
    """构建扫描标题"""
    first_file = list(files_dict.keys())[0] if files_dict else 'unknown'
    if len(files_dict) > 1:
        return f"{first_file} 等 {len(files_dict)} 个文件"
    return first_file


def _get_source_from_request():
    """从请求中提取来源标记"""
    source = request.form.get('source') or request.args.get('source')
    if not source:
        data_json = request.get_json(silent=True) or {}
        source = data_json.get('source')
    return source or 'upload'


# --- Scan submit（入口） ---

@app.route('/scan', methods=['POST'])
@app.route('/api/scan/submit', methods=['POST'])
@csrf_required
def scan():
    """发起检测（返回 JSON）"""
    _req_files = request.files.getlist('files') if request else []
    app.logger.debug("[SCAN] files count=%d, content_length=%s",
                     len(_req_files), request.content_length if request else 0)
    check_daily_limit()

    files_dict = _collect_files_from_request()
    if not files_dict:
        return jsonify({'error': '请上传文件或粘贴代码'}), HTTP_BAD_REQUEST

    # 大文件前置过滤：单文件>1MB自动过滤（可能是二进制/资源文件），不拒绝用户
    # 大项目由引擎自动分批扫描，不再硬性拒绝
    _max_single = 1024 * 1024  # 1MB
    _skipped_files = []
    for _fn in list(files_dict.keys()):
        _fc = files_dict[_fn]
        if isinstance(_fc, str) and len(_fc.encode('utf-8', errors='replace')) > _max_single:
            _skipped_files.append(_fn)
            del files_dict[_fn]

    language = request.form.get('language', 'auto')
    vip = is_vip_user()
    user_id = session.get('user_id')
    is_full_scan = vip
    brain_ids = ALL_BRAIN_IDS if is_full_scan else FREE_BRAIN_IDS
    
    # 读取前端传的scan_mode（quick/smart/deep），用于计费和记录
    req_scan_mode = request.form.get('scan_mode', '')
    if not vip:
        actual_scan_mode = 'free'
    elif req_scan_mode in ('quick', 'smart', 'deep'):
        actual_scan_mode = req_scan_mode
    else:
        actual_scan_mode = 'quick'
    scan_mode = actual_scan_mode  # 记录到DB用
    
    file_count = len(files_dict)
    total_lines = count_total_lines(files_dict)

    # 积分处理（按scan_mode计费）
    credits_cost, err = _scan_credits_handling(vip, user_id, total_lines, file_count, scan_mode=actual_scan_mode)
    if err:
        return err
    
    # 空文件或免费扫描，credits_cost=0，跳过扣费
    if credits_cost == 0:
        pass  # 继续执行扫描

    # 异步扫描：提交到后台线程池，立即返回 scan_id
    source = _get_source_from_request()
    scan_id, err_resp, err_code = _do_async_scan(
        files_dict, brain_ids, language, vip, user_id, credits_cost, total_lines, scan_mode, source
    )

    if err_resp:
        return err_resp, err_code

    # 非VIP记录今日用量
    if not vip:
        increment_daily_usage()

    # 返回 scan_id 供前端轮询
    return jsonify({
        'scan_id': scan_id,
        'status': 'pending',
        'file_count': len(files_dict),
        'total_lines': total_lines,
        'credits_spent': credits_cost if user_id else 0,
        'message': '扫描任务已提交，请等待完成',
    })


def _run_post_scan_hooks(db, scan_info, results, file_count):
    """执行扫描后处理：度量写入、告警触发、门禁评估"""
    user_id = scan_info.get('user_id')
    _write_scan_metrics(db, scan_info, results)
    _trigger_alerts_async(user_id, scan_info['score'], scan_info['grade'], results)

    gate_result = _evaluate_quality_gate(user_id, results, scan_info['score'], file_count)
    if gate_result and user_id:
        try:
            db.execute("""
                INSERT INTO gate_results (scan_id, user_id, gate_id, passed, details_json)
                VALUES (?, ?, ?, ?, ?)
            """, (scan_info['scan_id'], user_id,
                  gate_result.get('id', 0),
                  1 if gate_result.get('passed') else 0,
                  json.dumps(gate_result, ensure_ascii=False)))
            db.commit()
        except Exception:
            pass


def _build_scan_response(scan_info, results, credits_cost):
    """构建扫描结果响应"""
    user_id = scan_info.get('user_id')
    return jsonify({
        'scan_id': scan_info['scan_id'],
        'score': scan_info['score'],
        'grade': scan_info['grade'],
        'total_issues': results['total_issues'],
        'credits_spent': credits_cost if user_id else 0,
        'credits_balance': get_user_credits(user_id) if user_id else 0,
    })


# ============================================================
# 异步扫描支持
# ============================================================

def _async_scan_task(scan_id, user_id, files_dict, brain_ids, language, vip,
                     credits_cost, total_lines, scan_mode, source, progress_callback=None):
    """后台线程执行的异步扫描任务（在 app_context 中运行）"""
    import sqlite3 as _sqlite3
    with app.app_context():
        try:
            if progress_callback:
                progress_callback(15, "正在连接扫描引擎")

            results, err = _execute_scanner_call(files_dict, brain_ids, language, vip, user_id)

            if err:
                # 提取具体错误信息
                err_msg = "扫描服务暂时不可用，请稍后重试"
                try:
                    err_data = err[0].get_json(silent=True) if hasattr(err[0], 'get_json') else {}
                    detail = err_data.get('detail', '') if err_data else ''
                    if 'timeout' in detail.lower() or '超时' in detail:
                        err_msg = "扫描引擎处理超时，可能是文件过多或引擎繁忙。建议减少文件数量后重试"
                    elif 'connection' in detail.lower() or '不可达' in detail or '连接' in detail:
                        err_msg = "扫描引擎暂时无法连接，技术团队已收到通知，请稍后重试"
                    elif detail:
                        err_msg = detail[:150]
                except Exception:
                    pass

                if user_id and credits_cost > 0:
                    for _ra in range(3):
                        try:
                            grant_credits(user_id, credits_cost, ref_type="scan_refund",
                                          ref_id="scan_failed", remark="Scan engine failed refund")
                            break
                        except Exception:
                            if _ra == 2:
                                logger.critical("Refund permanently failed: user=%s amount=%s", user_id, credits_cost)
                _db = _sqlite3.connect(DB_PATH)
                _db.execute("UPDATE scans SET scan_status=?, scan_error=? WHERE scan_id=?",
                           ("failed", err_msg, scan_id))
                _db.commit()
                _db.close()
                return

            if progress_callback:
                progress_callback(80, "正在生成报告")

            avail_brains = None if vip else FREE_BRAIN_IDS
            score = calculate_score(results["issues"], available_brain_ids=avail_brains)
            tier_scores = calculate_tier_scores(results["issues"], available_brain_ids=avail_brains, is_vip=vip)
            grade = calculate_overall_grade(tier_scores)

            _db = _sqlite3.connect(DB_PATH)
            _db.execute("UPDATE scans SET results=?, score=?, grade=?, issue_count=?, scan_status=?, scan_progress=?, scan_progress_text=? WHERE scan_id=?",
                       (json.dumps(results, ensure_ascii=False), score, grade, results["total_issues"],
                        "completed", 100, "扫描完成", scan_id))

            if vip and user_id:
                last_tx = _db.execute("SELECT id FROM credit_transactions WHERE user_id = ? AND type = ? AND ref_type = ? ORDER BY id DESC LIMIT 1",
                                     (user_id, "consume", "scan_pre")).fetchone()
                if last_tx:
                    remark_str = "扫描消耗：%d行，%d个文件，完整版" % (total_lines, len(files_dict))
                    _db.execute("UPDATE credit_transactions SET ref_type = ?, ref_id = ?, remark = ? WHERE id = ?",
                               ("scan", scan_id, remark_str, last_tx[0]))

            _db.commit()
            _db.close()

            if progress_callback:
                progress_callback(95, "后处理中")

            logger.info("Async scan completed: %s, score=%s, grade=%s, issues=%d",
                         scan_id, score, grade, results["total_issues"])

        except Exception as e:
            logger.error("Async scan task error: %s", e, exc_info=True)
            try:
                _db = _sqlite3.connect(DB_PATH)
                _db.execute("UPDATE scans SET scan_status=?, scan_error=? WHERE scan_id=?",
                           ("failed", str(e)[:200], scan_id))
                _db.commit()
                _db.close()
            except Exception:
                pass


@app.route("/api/scan/status/<scan_id>")
def scan_status(scan_id):
    """查询扫描任务状态（供前端轮询）"""
    job_status = job_manager.get_status(scan_id)

    db = get_db()
    row = db.execute(
        "SELECT scan_status, scan_progress, scan_progress_text, scan_error, score, grade, issue_count FROM scans WHERE scan_id = ?",
        (scan_id,)
    ).fetchone()

    if not row:
        return jsonify({"error": "扫描记录不存在"}), HTTP_NOT_FOUND

    # 归属校验：已登录用户的扫描不向第三方暴露状态/评分
    _owner = db.execute(
        "SELECT user_id FROM scans WHERE scan_id = ?", (scan_id,)
    ).fetchone()
    if _owner and _owner[0] and not _scan_visible_to_session({'user_id': _owner[0]}):
        return jsonify({"error": "扫描记录不存在"}), HTTP_NOT_FOUND

    db_status = row[0]
    status = db_status or job_status.get("status", "unknown")
    progress = row[1] or job_status.get("progress", 0)
    progress_text = row[2] or job_status.get("progress_text", "")
    error = row[3] or job_status.get("error")

    resp = {
        "scan_id": scan_id,
        "status": status,
        "progress": progress,
        "progress_text": progress_text,
    }
    if error:
        resp["error"] = error
    if status == "completed":
        resp["score"] = row[4]
        resp["grade"] = row[5]
        resp["total_issues"] = row[6]
        user_id = session.get("user_id")
        if user_id:
            resp["credits_balance"] = get_user_credits(user_id)

    return jsonify(resp)


def _do_async_scan(files_dict, brain_ids, language, vip, user_id, credits_cost, total_lines, scan_mode, source):
    """将扫描任务提交到后台线程池，立即返回 scan_id"""
    scan_id = _generate_scan_id()
    title = _build_scan_title(files_dict)
    file_count = len(files_dict)

    db = get_db()
    db.execute("INSERT INTO scans (scan_id, user_id, title, file_count, files_meta, results, score, grade, issue_count, language, credits_spent, total_lines, scan_mode, source, scan_status, scan_progress, scan_progress_text) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
               (scan_id, user_id, title, file_count,
                json.dumps(list(files_dict.keys()), ensure_ascii=False),
                "[]", 0, "", 0, language,
                credits_cost if user_id else 0,
                total_lines, scan_mode, source,
                "pending", 5, "正在准备扫描"))
    db.commit()

    ok = job_manager.submit(
        scan_id, _async_scan_task,
        {"scan_id": scan_id, "user_id": user_id, "files_dict": files_dict,
         "brain_ids": brain_ids, "language": language, "vip": vip,
         "credits_cost": credits_cost, "total_lines": total_lines,
         "scan_mode": scan_mode, "source": source})

    if not ok:
        db.execute("DELETE FROM scans WHERE scan_id=?", (scan_id,))
        db.commit()
        return None, jsonify({"error": "当前扫描任务排队已满，请稍后再试",
                              "detail": "当前有 %d 个任务在处理中" % job_manager.active_count()}), HTTP_BAD_REQUEST

    logger.info("Async scan submitted: %s, files=%d, mode=%s", scan_id, file_count, scan_mode)
    init_scan_tables()
    return scan_id, None, None


# ============================================================
# 报告页
# ============================================================

@app.route('/report/<scan_id>')
def report_page(scan_id):
    """报告页"""
    db = get_db()
    scan = db.execute('SELECT * FROM scans WHERE scan_id = ?', (scan_id,)).fetchone()

    if not scan or not _scan_visible_to_session(scan):
        return render_template('404.html'), 404

    results = json.loads(scan['results']) if scan['results'] else {'issues': []}
    all_issues = results.get('issues', [])
    # P0: style 问题单独展示
    style_issues = results.get('style_issues', [])
    style_count = len(style_issues)
    vip = is_vip_user()

    dimensions = _build_dimensions(all_issues, vip)
    visible_issues = _format_visible_issues(all_issues, vip)
    _issue_tier_assignment(visible_issues)
    
    # 误报反馈闭环：过滤用户已标记的误报
    user_fps = []
    if session.get('user_id'):
        try:
            fp_rows = get_db().execute(
                'SELECT rule_id, file_path, line_number FROM false_positives WHERE user_id=? AND scan_id=?',
                (session['user_id'], scan_id)
            ).fetchall()
            user_fps = {(r[0], r[1], r[2]) for r in fp_rows}
            if user_fps:
                visible_issues = [
                    iss for iss in visible_issues
                    if (iss.get('rule_id'), iss.get('file'), iss.get('line')) not in user_fps
                ]
        except Exception:
            pass  # 过滤失败不影响正常展示
    avail_brains = None if vip else FREE_BRAIN_IDS
    tier_scores = calculate_tier_scores(all_issues, available_brain_ids=avail_brains, is_vip=vip)
    severity_counts = _compute_severity_counts(visible_issues)

    score = scan['score']
    grade = scan['grade']
    if len(grade) <= 1:
        grade = calculate_overall_grade(tier_scores)

    created_at = scan['created_at']
    try:
        dt = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
        created_at_str = dt.strftime('%Y-%m-%d %H:%M')
    except (ValueError, TypeError):
        created_at_str = created_at

    bb_scores = calculate_building_block_scores(all_issues, file_count=scan['file_count'])

    # 修复路线图
    fix_roadmap = build_fix_roadmap(visible_issues)
    fix_progress = build_fix_progress(scan_id, session.get("user_id"))

    return render_template(
        'report.html',
        scan_id=scan_id,
        report_title=scan['title'],
        score=score,
        grade=grade,
        file_count=scan['file_count'],
        total_issues=scan['issue_count'],
        created_at=created_at_str,
        dimensions=dimensions,
        tier_scores=tier_scores,
        tiers=TIERS,
        visible_issues=visible_issues,
        visible_issues_count=len(visible_issues),
        style_issues=style_issues,
        style_count=style_count,
        severity_counts=severity_counts,
        bb_scores=bb_scores,
        is_vip=vip,
        fix_roadmap=fix_roadmap,
        fix_progress=fix_progress,
        share_token=scan['share_token'],
    )




# ============================================================
# 误报反馈 API
# ============================================================

@app.route('/api/scan/<scan_id>/false-positive', methods=['POST'])
def report_false_positive(scan_id):
    """用户标记某个 issue 为误报"""
    if not session.get('user_id'):
        return jsonify({'error': '请先登录'}), 401
    
    data = request.get_json() or {}
    rule_id = data.get('rule_id', '')
    file_path = data.get('file', '')
    line_number = data.get('line', 0)
    issue_title = data.get('title', '')
    reason = data.get('reason', '')
    
    if not rule_id or not file_path:
        return jsonify({'error': '缺少必要参数'}), 400
    
    db = get_db()
    # 检查是否已标记过
    existing = db.execute(
        'SELECT id FROM false_positives WHERE user_id=? AND scan_id=? AND rule_id=? AND file_path=? AND line_number=?',
        (session['user_id'], scan_id, rule_id, file_path, line_number)
    ).fetchone()
    
    if existing:
        return jsonify({'status': 'ok', 'message': '已标记过', 'id': existing[0]})
    
    db.execute(
        'INSERT INTO false_positives (user_id, scan_id, rule_id, file_path, line_number, issue_title, reason) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (session['user_id'], scan_id, rule_id, file_path, line_number, issue_title, reason)
    )
    db.commit()
    
    return jsonify({'status': 'ok', 'message': '已标记为误报'})


@app.route('/api/scan/<scan_id>/false-positives', methods=['GET'])
def list_false_positives(scan_id):
    """获取某次扫描中用户标记的误报列表"""
    if not session.get('user_id'):
        return jsonify({'error': '请先登录'}), 401
    
    db = get_db()
    rows = db.execute(
        'SELECT id, rule_id, file_path, line_number, issue_title, reason, created_at FROM false_positives WHERE user_id=? AND scan_id=? ORDER BY created_at DESC',
        (session['user_id'], scan_id)
    ).fetchall()
    
    fps = []
    for row in rows:
        fps.append({
            'id': row[0],
            'rule_id': row[1],
            'file': row[2],
            'line': row[3],
            'title': row[4],
            'reason': row[5],
            'created_at': row[6],
        })
    
    return jsonify({'status': 'ok', 'false_positives': fps})


@app.route('/api/scan/<scan_id>/false-positive/<int:fp_id>', methods=['DELETE'])
def remove_false_positive(scan_id, fp_id):
    """取消标记误报"""
    if not session.get('user_id'):
        return jsonify({'error': '请先登录'}), 401
    
    db = get_db()
    db.execute('DELETE FROM false_positives WHERE id=? AND user_id=?', (fp_id, session['user_id']))
    db.commit()
    
    return jsonify({'status': 'ok', 'message': '已取消'})


# ============================================================
# HTML 报告下载
# ============================================================

@app.route('/report/<scan_id>/html')
def download_html_report(scan_id):
    """下载 HTML 报告"""
    db = get_db()
    scan = db.execute('SELECT * FROM scans WHERE scan_id = ?', (scan_id,)).fetchone()

    if not scan or not _scan_visible_to_session(scan):
        return render_template('404.html'), 404

    try:
        scanner_report_url = SCANNER_URL.replace('/scan', f'/report/{scan_id}')
        resp = _safe_http_get(scanner_report_url, timeout=REPORT_TIMEOUT_SECONDS)
        resp.raise_for_status()
        html_content = resp.text
    except (ConnectionError, OSError, RuntimeError) as e:
        app.logger.error('HTML report fetch failed: %s', e)
        flash('报告生成失败', 'error')
        return redirect(url_for('report_page', scan_id=scan_id))

    response = make_response(html_content)
    response.headers['Content-Type'] = 'text/html; charset=utf-8'
    response.headers['Content-Disposition'] = f'attachment; filename="xinpect_report_{scan_id}.html"'
    return response


# ============================================================
# Markdown 报告下载（拆分 download_report）
# ============================================================

def _build_md_header(scan, all_issues, vip):
    """构建 Markdown 报告头部"""
    md_lines = []
    md_lines.append('# 煋鉴 Xinpect 代码检测报告')
    md_lines.append('')
    md_lines.append(f'**检测名称：** {scan["title"]}')
    md_lines.append(f'**检测时间：** {scan["created_at"]}')
    md_lines.append(f'**文件数量：** {scan["file_count"]}')

    avail_brains_md = None if vip else FREE_BRAIN_IDS
    tier_scores_md = calculate_tier_scores(all_issues, available_brain_ids=avail_brains_md, is_vip=vip)
    md_grade = calculate_overall_grade(tier_scores_md)

    md_lines.append(f'**综合评级：** {md_grade} 级')
    md_lines.append(f'**综合得分：** {scan["score"]} / 100')
    md_lines.append('')
    md_lines.append('**三层评级明细：**')
    md_lines.append('')
    md_lines.append('| 层级 | 名称 | 得分 | 评级 | 问题数 |')
    md_lines.append('|------|------|------|------|--------|')
    for tier in TIERS:
        ts = tier_scores_md[tier['key']]
        if ts.get('locked') or ts.get('score') is None:
            md_lines.append(f'| {tier["name"]} | {tier["subtitle"]} | 🔒 | 未解锁 | - |')
        else:
            md_lines.append(f'| {tier["name"]} | {tier["subtitle"]} | {ts["score"]} | {ts["grade"]} | {ts["issue_count"]} |')
    md_lines.append('')

    visible_issues = all_issues if vip else [
        i for i in all_issues if str(i.get('brain_id')) in FREE_BRAIN_ID_SET
    ]
    md_lines.append(f'**问题总数：** {len(visible_issues)}')
    if not vip:
        md_lines.append(f'> ⚡ 免费版仅展示规范层结果，[升级专业版](https://xinpect.xingwangzhineng.com) 解锁全部 9 大脑 + 小程序专项')
    md_lines.append('')
    md_lines.append('---')
    md_lines.append('')
    return md_lines, tier_scores_md, visible_issues


def _build_md_dimension_scores(scan, visible_issues, vip):
    """构建各维度得分表"""
    md_lines = []
    md_lines.append('## 各维度得分')
    md_lines.append('')
    md_lines.append('| 维度 | 名称 | 得分 | 问题数 |')
    md_lines.append('|------|------|------|--------|')
    for brain in BRAINS:
        if vip or brain['id'] in FREE_BRAIN_ID_SET:
            brain_issues = [i for i in visible_issues if str(i.get('brain_id')) == brain['id']]
            dim_score = calculate_dimension_score(brain_issues)
            md_lines.append(f'| B{brain["id"]} | {brain["name"]} | {dim_score} | {len(brain_issues)} |')
        else:
            md_lines.append(f'| B{brain["id"]} | {brain["name"]} | 🔒 升级解锁 | - |')
    md_lines.append('')
    return md_lines


def _build_md_issue_detail(brain, visible_issues):
    """构建单个维度的问题详情"""
    md_lines = []
    brain_issues = [i for i in visible_issues if str(i.get('brain_id')) == brain['id']]
    if not brain_issues:
        return md_lines

    md_lines.append(f'### B{brain["id"]} {brain["name"]}')
    md_lines.append('')

    for idx, issue in enumerate(brain_issues, 1):
        sev_label = issue.get('severity_label', issue['severity'])
        md_lines.append(f'#### [{sev_label}] {idx}. {issue["title"]}')
        md_lines.append('')
        md_lines.append(f'- **规则ID：** {issue["rule_id"]}')
        md_lines.append(f'- **位置：** `{issue["file"]}:{issue["line"]}`')
        md_lines.append('')
        md_lines.append('**问题描述：**')
        md_lines.append('')
        md_lines.append(issue['description'])
        md_lines.append('')

        if issue.get('code_snippet'):
            md_lines.append('**问题代码：**')
            md_lines.append('')
            md_lines.append('```')
            md_lines.append(issue['code_snippet'])
            md_lines.append('```')
            md_lines.append('')

        if issue.get('suggestion'):
            md_lines.append('**修复建议：**')
            md_lines.append('')
            md_lines.append(f'> {issue["suggestion"]}')
            md_lines.append('')

    md_lines.append('---')
    md_lines.append('')
    return md_lines


def _build_md_issues(visible_issues, vip):
    """构建问题详情部分"""
    md_lines = []
    md_lines.append('## 问题详情')
    md_lines.append('')

    if not visible_issues:
        md_lines.append('🎉 **未检测到任何问题，代码质量优秀！**')
    else:
        visible_brains = BRAINS if vip else [b for b in BRAINS if b['id'] in FREE_BRAIN_ID_SET]
        for brain in visible_brains:
            md_lines.extend(_build_md_issue_detail(brain, visible_issues))

    md_lines.append('')
    md_lines.append('---')
    md_lines.append(f'*本报告由 [煋鉴 Xinpect](https://xinpect.xingwangzhineng.com) 自动生成*')
    return md_lines


def _build_download_filename(scan):
    """构建下载文件名"""
    report_title = scan['title'] or '代码检测'
    title_safe = re.sub(r'[\\/:*?"<>|]', '', report_title).strip()[:30]
    time_str = scan['created_at'].replace('-', '').replace(':', '').replace(' ', '')[:12]
    filename_cn = f'煋鉴检测报告_{title_safe}_{time_str}.md'
    return quote(filename_cn)


@app.route('/report/<scan_id>/download')
def download_report(scan_id):
    """下载报告（Markdown 格式）"""
    db = get_db()
    scan = db.execute('SELECT * FROM scans WHERE scan_id = ?', (scan_id,)).fetchone()

    if not scan or not _scan_visible_to_session(scan):
        return render_template('404.html'), 404

    results = json.loads(scan['results']) if scan['results'] else {'issues': []}
    all_issues = results.get('issues', [])
    # P0: style 问题单独展示
    style_issues = results.get('style_issues', [])
    style_count = len(style_issues)
    vip = is_vip_user()

    if not vip:
        for _iss in all_issues:
            _iss['is_free_locked'] = True

    header_lines, tier_scores_md, visible_issues = _build_md_header(scan, all_issues, vip)
    dimension_lines = _build_md_dimension_scores(scan, visible_issues, vip)
    issues_lines = _build_md_issues(visible_issues, vip)

    md_lines = header_lines + dimension_lines + issues_lines
    md_content = '\n'.join(md_lines)

    filename_encoded = _build_download_filename(scan)
    response = make_response(md_content)
    response.headers['Content-Type'] = 'text/markdown; charset=utf-8'
    response.headers['Content-Disposition'] = f"attachment; filename*=UTF-8''{filename_encoded}"
    return response


# ============================================================
# 组件契约检测（拆分 api_component_check）
# ============================================================

@app.route('/component-check')
def component_check_page():
    """小程序组件契约检测页面（免费引流入口）"""
    return render_template('component_check.html')


def _validate_wxml_input(data):
    """验证 WXML 输入。
    返回 (wxml_code, filename, error_response)。
    """
    wxml_code = (data.get('wxml_code', '') or '').strip()
    filename = data.get('filename', 'component.wxml') or 'component.wxml'

    if not wxml_code:
        return None, None, (
            jsonify({'success': False, 'error': '请输入 WXML 代码'}), HTTP_BAD_REQUEST
        )
    if len(wxml_code) > MAX_CODE_LENGTH:
        return None, None, (
            jsonify({'success': False, 'error': f'代码长度不能超过 {MAX_CODE_LENGTH} 字符'}),
            HTTP_BAD_REQUEST
        )
    if not re.search(r'<[a-zA-Z]', wxml_code):
        return None, None, (
            jsonify({'success': False, 'error': '未检测到有效的 WXML 标签，请检查代码格式'}),
            HTTP_BAD_REQUEST
        )
    return wxml_code, filename, None


def _format_component_issues(raw_issues, wxml_code, filename):
    """格式化组件检测问题列表"""
    issues = []
    sev_counts = {'high': 0, 'medium': 0, 'low': 0, 'info': 0}

    for issue in raw_issues:
        severity = issue.get('severity', 'medium')
        if severity in ('critical', 'blocker'):
            severity = 'high'
        if severity not in sev_counts:
            sev_counts[severity] = 0
        sev_counts[severity] += 1

        code_snippet = _extract_wxml_snippet(wxml_code, issue.get('line', 0))
        issues.append({
            'rule_id': issue.get('check_id', ''),
            'title': issue.get('name', ''),
            'severity': severity,
            'severity_label': severity_label(severity),
            'description': issue.get('message', ''),
            'suggestion': issue.get('suggestion', ''),
            'file': filename,
            'line': issue.get('line', 0),
            'code_snippet': code_snippet,
        })

    sev_order = {'high': 0, 'medium': 1, 'low': 2, 'info': 3}
    issues.sort(key=lambda x: (sev_order.get(x.get('severity', ''), 99), x.get('line', 0)))
    return issues, sev_counts


def _extract_wxml_snippet(wxml_code, line_num):
    """提取 WXML 代码片段"""
    if not line_num or not wxml_code:
        return ''
    _lines = wxml_code.split('\n')
    _start = max(0, line_num - 2)
    _end = min(len(_lines), line_num + 1)
    _parts = []
    for _i in range(_start, _end):
        _m = '> ' if _i + 1 == line_num else '  '
        _parts.append(f"{_m}{_i+1:3d}: {_lines[_i]}")
    return '\n'.join(_parts)


def _save_component_check_record(filename, raw_issues, score, wxml_code):
    """保存组件检测记录"""
    try:
        cc_scan_id = 'cc_' + uuid.uuid4().hex[:12]
        db = get_db()
        cc_results = {'results': {'9': {'issues': raw_issues, 'score': score}}}
        cc_grade = 'S' if score >= CC_SCORE_S else ('A' if score >= CC_SCORE_A else ('B' if score >= CC_SCORE_B else 'C'))
        db.execute('''
            INSERT INTO scans (scan_id, user_id, title, file_count, files_meta,
                              results, score, grade, issue_count, language,
                              credits_spent, total_lines, scan_mode, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            cc_scan_id, session.get('user_id'), '组件契约检测', 1,
            json.dumps([filename], ensure_ascii=False),
            json.dumps(cc_results, ensure_ascii=False),
            score, cc_grade, len(raw_issues), 'wxml', 0,
            len(wxml_code.splitlines()), 'basic', 'component_check',
        ))
        db.commit()
    except (sqlite3.Error, OSError) as e:
        logger.warning("Failed to save CC scan record: %s", e)


@app.route('/api/component-check', methods=['POST'])
def api_component_check():
    """组件契约检测 API"""
    if not session.get('user_id'):
        return jsonify({
            'success': False, 'error': 'login_required',
            'message': '请先登录后使用检测功能',
        }), HTTP_UNAUTHORIZED

    data = request.get_json() or {}
    wxml_code, filename, err = _validate_wxml_input(data)
    if err:
        return err

    start_time = time.time()

    try:
        resp = _safe_http_post(SCANNER_URL, json={
            'code_files': {filename: wxml_code},
            'brain_ids': ['9'],
            'scan_mode': 'basic',
            'is_vip': False,
        }, timeout=REPORT_TIMEOUT_SECONDS)
        resp.raise_for_status()
        raw = resp.json()
    except Exception as e:
        app.logger.error('Component check scanner call failed: %s', e)
        return jsonify({'success': False, 'error': '检测服务暂不可用，请稍后重试'}), HTTP_INTERNAL_ERROR

    b9_result = raw.get('results', {}).get('9', {})
    raw_issues = b9_result.get('issues', [])
    score = b9_result.get('score', 100)

    issues, sev_counts = _format_component_issues(raw_issues, wxml_code, filename)
    elapsed_ms = int((time.time() - start_time) * 1000)

    _save_component_check_record(filename, raw_issues, score, wxml_code)

    return jsonify({
        'success': True,
        'score': score,
        'total_issues': len(issues),
        'elapsed_ms': elapsed_ms,
        'sev_counts': sev_counts,
        'issues': issues,
    })


# ============================================================
# 预估接口
# ============================================================

@app.route('/api/scan/estimate', methods=['POST'])
@csrf_required
def api_scan_estimate():
    """预估扫描积分消耗"""
    if request.is_json:
        return _handle_json_estimate()

    files_dict = _collect_files_from_request()
    if not files_dict:
        return jsonify({'ok': False, 'error': '请上传文件或粘贴代码'}), HTTP_BAD_REQUEST

    file_count = len(files_dict)
    total_lines = count_total_lines(files_dict)
    scan_mode = request.form.get('scan_mode', None)
    return _build_estimate_response(file_count, total_lines, request_scan_mode=scan_mode)


def _handle_json_estimate():
    """处理 JSON 格式的预估请求"""
    data = request.get_json() or {}
    files_meta = data.get('files_meta', [])
    total_lines = 0
    file_count = 0
    for fm in files_meta:
        name = fm.get('name', '') or ''
        size = fm.get('size', 0) or 0
        is_archive = _is_archive_filename(name)
        ext = '.' + name.rsplit('.', 1)[-1].lower() if '.' in name else ''
        if ext in CODE_EXTS:
            file_count += 1
            total_lines += max(1, int(size / 50))
        elif is_archive:
            file_count += 1
            estimated_unzipped = max(size * ESTIMATED_UNZIP_FACTOR, size + MIN_ESTIMATED_SIZE_ADDITION)
            total_lines += max(MIN_ESTIMATED_LINES, int(estimated_unzipped / ESTIMATED_LINE_SIZE))
    # Fallback: unknown exts still estimated
    if file_count == 0 and files_meta:
        for fm in files_meta:
            size = fm.get('size', 0) or 0
            if size > 0:
                file_count += 1
                total_lines += max(1, int(size / 50))
    if file_count == 0:
        return jsonify({'ok': False, 'error': '未识别到有效代码文件'}), HTTP_BAD_REQUEST
    scan_mode = data.get('scan_mode', None)
    return _build_estimate_response(file_count, total_lines, request_scan_mode=scan_mode)


# ============================================================
# P0: 自定义阈值 API
# ============================================================

@scan_bp.route('/api/thresholds', methods=['GET'])
def api_get_thresholds():
    """获取用户当前的阈值配置"""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': '未登录'}), 401

    db = get_db()
    row = db.execute('SELECT config_json FROM scan_thresholds WHERE user_id=?', (user_id,)).fetchone()

    from modules.constants import DEFAULT_THRESHOLDS_WEB
    default_config = DEFAULT_THRESHOLDS_WEB

    user_config = {}
    if row and row[0]:
        try:
            user_config = json.loads(row[0])
        except Exception:
            pass

    return jsonify({'success': True, 'default': default_config, 'current': user_config})


@scan_bp.route('/api/thresholds', methods=['POST'])
def api_save_thresholds():
    """保存用户阈值配置"""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': '未登录'}), 401

    data = request.get_json(silent=True) or {}
    config = data.get('config', {})
    if not isinstance(config, dict):
        return jsonify({'error': 'config 格式错误'}), 400

    from modules.constants import ALLOWED_THRESHOLD_KEYS
    # P2-6: 规则禁用配置
    disabled_rules = data.get('disabled_rules', [])
    cleaned = _clean_threshold_config(config, ALLOWED_THRESHOLD_KEYS)
    if isinstance(disabled_rules, list):
        cleaned['_disabled_rules'] = [r for r in disabled_rules if isinstance(r, str) and len(r) < 100][:50]
    config_json = json.dumps(cleaned, ensure_ascii=False)

    db = get_db()
    existing = db.execute('SELECT id FROM scan_thresholds WHERE user_id=?', (user_id,)).fetchone()
    if existing:
        db.execute('UPDATE scan_thresholds SET config_json=?, updated_at=datetime("now","localtime") WHERE user_id=?',
                   (config_json, user_id))
    else:
        db.execute('INSERT INTO scan_thresholds (user_id, config_json) VALUES (?, ?)',
                   (user_id, config_json))
    db.commit()

    return jsonify({'success': True, 'config': cleaned})


def _clean_threshold_config(config, allowed_keys):
    """清洗阈值配置，只保留合法字段"""
    cleaned = {}
    for category, values in config.items():
        if category in allowed_keys and isinstance(values, dict):
            cleaned[category] = {}
            for key, val in values.items():
                if key in allowed_keys[category] and isinstance(val, (int, float)) and 0 < val <= 10000:
                    cleaned[category][key] = int(val)
    return cleaned


# ============================================================

# P1: 质量门禁 API
# ============================================================

@scan_bp.route('/api/gates', methods=['GET'])
def api_get_gates():
    """获取用户门禁配置"""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': '未登录'}), 401

    from modules.quality_gate import get_templates
    db = get_db()
    row = db.execute('SELECT rules_json, name FROM quality_gates WHERE user_id=?', (user_id,)).fetchone()

    current = {}
    gate_name = ''
    if row and row[0]:
        try:
            current = json.loads(row[0])
            gate_name = row[1]
        except Exception:
            pass

    return jsonify({'success': True, 'name': gate_name, 'current': current, 'templates': get_templates()})


@scan_bp.route('/api/gates', methods=['POST'])
def api_save_gates():
    """保存用户门禁配置"""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': '未登录'}), 401

    data = request.get_json(silent=True) or {}
    rules = data.get('rules', [])
    name = data.get('name', 'default')

    if not isinstance(rules, list):
        return jsonify({'error': 'rules 格式错误'}), 400

    config_json = json.dumps({'rules': rules}, ensure_ascii=False)
    db = get_db()
    existing = db.execute('SELECT id FROM quality_gates WHERE user_id=?', (user_id,)).fetchone()
    if existing:
        db.execute('UPDATE quality_gates SET rules_json=?, name=?, is_active=1, updated_at=datetime("now","localtime") WHERE user_id=?',
                   (config_json, name, user_id))
    else:
        db.execute('INSERT INTO quality_gates (user_id, rules_json, name, is_active) VALUES (?, ?, ?, 1)',
                   (user_id, config_json, name))
    db.commit()

    return jsonify({'success': True, 'config': {'rules': rules}})


@scan_bp.route('/api/gates/templates', methods=['GET'])
def api_gate_templates():
    """获取门禁模板"""
    from modules.quality_gate import get_templates
    return jsonify({'success': True, 'templates': get_templates()})


# ============================================================
# P3: 技术债趋势 API
# ============================================================

@scan_bp.route('/api/trends')
def api_trends():
    """获取趋势数据"""
    from modules.trends import get_user_trends
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': '未登录'}), HTTP_UNAUTHORIZED
    days = min(max(request.args.get('days', 30, type=int), 7), 365)
    project_tag = request.args.get('project', '')
    data = get_user_trends(user_id, days=days, project_tag=project_tag or None)
    return jsonify({'success': True, **data})


@scan_bp.route('/api/trends/summary')
def api_trends_summary():
    """获取趋势摘要"""
    from modules.trends import get_user_trends
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': '未登录'}), HTTP_UNAUTHORIZED
    days = min(max(request.args.get('days', 30, type=int), 7), 365)
    data = get_user_trends(user_id, days=days)
    return jsonify({'success': True, 'summary': data['summary']})


@scan_bp.route('/api/trends/brain')
def api_trends_brain():
    """获取单引擎趋势"""
    from modules.trends import get_user_trends
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': '未登录'}), HTTP_UNAUTHORIZED

    brain_id = request.args.get('brain_id', type=int)
    if not brain_id:
        return jsonify({'error': '请指定 brain_id'}), HTTP_BAD_REQUEST

    days = min(max(request.args.get('days', 30, type=int), 7), 365)
    data = get_user_trends(user_id, days=days)

    brain_data = [
        {'date': dp['date'], 'score': dp.get('brain_scores', {}).get(str(brain_id))}
        for dp in data['data_points']
    ]
    brain_name = BRAINS_MAP.get(brain_id, {}).get('name', f'Brain {brain_id}')

    return jsonify({
        'success': True, 'brain_id': brain_id,
        'brain_name': brain_name, 'data': brain_data,
    })


# ============================================================
# 外部模块路由注册
# ============================================================

from modules.scan_diff import register_diff_routes
register_diff_routes(scan_bp)

from modules.alert import register_alert_routes
register_alert_routes(scan_bp)

# P2-03: 看板增强
from modules.dashboard_enhance import register_dashboard_enhancement_routes
register_dashboard_enhancement_routes(scan_bp)
