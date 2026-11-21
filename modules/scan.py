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
    BRAINS, BRAINS_MAP, TIERS, TIERS_MAP, brain_label,
    FREE_BRAIN_IDS, ALL_BRAIN_IDS, FREE_BRAIN_ID_SET,
    CODE_EXTS, ARCHIVE_SKIP_DIRS,
    MAX_CONTENT_LENGTH, MAX_CODE_LENGTH,
    MAX_CONTENT_SIZE_MB, ESTIMATED_UNZIP_FACTOR, ESTIMATED_LINE_SIZE,
    MIN_ESTIMATED_LINES, MIN_ESTIMATED_SIZE_ADDITION,
    MOCK_SCAN_TIMEOUT,
    DAILY_LIMIT_FREE,
    CC_SCORE_S, CC_SCORE_A, CC_SCORE_B,
    MAX_WXML_CODE_LENGTH,
    HTTP_OK, HTTP_BAD_REQUEST, HTTP_UNAUTHORIZED, HTTP_NOT_FOUND, HTTP_INTERNAL_ERROR,
    HTTP_PAYMENT_REQUIRED, HTTP_ENTITY_TOO_LARGE,
    SCANNER_URL, SCANNER_API_KEY, REPORT_TIMEOUT_SECONDS,
)
from .db import get_db
from .helpers import login_required, get_current_user, is_vip_user, _safe_http_post, _safe_http_get
from .scoring import (
    get_user_credits, consume_credits, grant_credits,
    calculate_scan_cost, count_total_lines, check_credit_sufficient,
    calculate_tier_scores, grade_of,
    calculate_score, calculate_dimension_score, calculate_building_block_scores,
    score_to_grade, score_color, severity_label, GRADE_TEXT,
    get_daily_usage, check_daily_limit, increment_daily_usage,
)
from .fix_roadmap import build_fix_roadmap, build_fix_progress
from . import report_verdict
from .report_verdict import TIER_MUST, TIER_SHOULD, TIER_EXCLUDED
from .csrf_protection import csrf_required
from .dimensions import (
    card_state as _dim_card_state,
    coverage_ok as _coverage_ok,
    NOT_RUN as _DIM_NOT_RUN,
    PARTIAL as _DIM_PARTIAL,
)
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
        credits_cost = calculate_scan_cost(total_lines, scan_mode=actual_mode, user_id=user_id)
        credit_balance = get_user_credits(user_id)
        sufficient = check_credit_sufficient(user_id, credits_cost)
        
        # 计算每100行单价（v7.0 新价）
        mode_rates = {'quick': 1, 'smart': 4, 'deep': 10}
        price_per_100 = mode_rates.get(actual_mode, 1)
        
        return jsonify({
            'ok': True, 'file_count': file_count, 'total_lines': total_lines,
            'scan_mode': actual_mode, 'is_vip': True,
            'cost': credits_cost, 'credits_cost': credits_cost,
            'credit_balance': credit_balance, 'is_sufficient': sufficient,
            'price_per_100': price_per_100,
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


def _strip_single_root_prefix(names):
    """识别并剥离压缩包包裹仓库的「单一顶层目录」，保留项目真实相对路径。

    治本（10-31）：旧逻辑 `parts = name.split('/', 1); display_name = parts[1]`
    盲目剥第一层目录，把正常的包目录也剥掉了——`modules/db.py` 被剥成 `db.py`，
    扫描器拿不到「modules 是包」的项目结构上下文，跨模块 import 规则误判。

    正确做法：只有当所有代码文件都共享**同一个**顶层目录（GitHub 下载 zip 的
    `repo-master/` 包裹）时才剥离它；否则（文件分布在多个顶层、或直接在根）保留
    完整相对路径。这样 `modules/db.py` 保留原样，`repo-master/modules/db.py` 剥成
    `modules/db.py`。
    """
    if not names:
        return {}

    # 提取每个路径的顶层目录（无目录的记为 ''）
    tops = []
    for n in names:
        n = n.replace('\\', '/')
        if '/' in n:
            tops.append(n.split('/', 1)[0])
        else:
            tops.append('')

    # 所有文件是否共享同一非空顶层目录
    non_empty_tops = {t for t in tops if t}
    strip_prefix = ''
    if len(non_empty_tops) == 1 and '' not in tops:
        # 唯一顶层目录，且没有任何文件直接在根（说明是包裹目录）
        strip_prefix = non_empty_tops.pop() + '/'

    stripped = {}
    for n in names:
        nn = n.replace('\\', '/')
        key = nn[len(strip_prefix):] if strip_prefix and nn.startswith(strip_prefix) else nn
        stripped[n] = key
    return stripped


def _extract_zip_data(data, result):
    """从 zip 数据中提取代码文件"""
    # 第一遍：收集所有代码文件路径
    candidates = []  # [(name, content)]
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
                candidates.append((name, file_content))
            except (UnicodeDecodeError, KeyError):
                logger.debug('skip undecodable file in archive')
            except (OSError, IOError) as _arch_err:
                logger.debug('skip file parse error in archive: %s', _arch_err)

    # 第二遍：识别单一顶层包裹目录后落盘
    name_map = _strip_single_root_prefix([c[0] for c in candidates])
    for name, content in candidates:
        result[name_map[name]] = content


def _extract_tar_data(data, result):
    """从 tar 数据中提取代码文件"""
    candidates = []
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
                    candidates.append((name, file_content))
            except (UnicodeDecodeError, KeyError):
                logger.debug('skip undecodable file in archive')
            except (OSError, IOError) as _arch_err:
                logger.debug('skip file in tar archive: %s', _arch_err)

    name_map = _strip_single_root_prefix([c[0] for c in candidates])
    for name, content in candidates:
        result[name_map[name]] = content


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


def _ledger_of(results):
    """从落库的 results 里取引擎台账三元组：(engines, unsupported_n, trimmed_n)。

    报告页、Markdown 导出、后台异步落库三条路径都从这里取，避免各写一份
    `results.get('engines')` 然后漏掉一两个字段。
    老报告没有这几个键 → (None, 0, 0)，下游据此退回旧行为。
    """
    if not isinstance(results, dict):
        return None, 0, 0
    return (
        results.get('engines') or None,
        len(results.get('unsupported_files') or []),
        len(results.get('trimmed_files') or []),
    )


def _build_dimensions(all_issues, vip, engines=None, unsupported=0, trimmed=0):
    """构建报告页维度数据列表

    2026-11-04：这张卡原来是「按 brain 数 issues，空就是 100 分」。
    引擎崩了、被高负载降级、文件没解析，三种情况都表现为 issues 为空，
    于是全部显示 100 分。现在先问台账这个引擎查没查：
      没查成 → 分数位置显示「—」，并注明「未检测」，绝不给百分比；
      查了一部分 → 分数照给（那是已查部分的真实成绩），但要标「部分未检测」；
      台账缺失（老报告）→ 保持旧行为。
    """
    dimensions = []
    for brain in BRAINS:
        brain_issues = [i for i in all_issues if str(i.get('brain_id')) == brain['id']]
        is_locked = (not vip) and (brain['id'] not in FREE_BRAIN_ID_SET)
        state, status_text = _dim_card_state(
            engines, brain['id'], unsupported, trimmed
        )
        if is_locked:
            dimensions.append({
                'id': brain['id'], 'code': brain.get('code', brain['id']), 'name': brain['name'],
                'score': '—', 'score_color': '#6b7280',
                'issues_count': '🔒', 'locked': True,
                'status_text': '', 'not_run': False,
            })
        elif state == _DIM_NOT_RUN:
            # 没有分数可言。issues_count 照实给（通常是 0，但那是「没查」不是「干净」）
            dimensions.append({
                'id': brain['id'], 'code': brain.get('code', brain['id']), 'name': brain['name'],
                'score': '—', 'score_color': '#6b7280',
                'issues_count': len(brain_issues), 'locked': False,
                'status_text': status_text, 'not_run': True,
            })
        else:
            dim_score = calculate_dimension_score(brain_issues)
            dimensions.append({
                'id': brain['id'], 'code': brain.get('code', brain['id']), 'name': brain['name'],
                'score': dim_score, 'score_color': score_color(dim_score),
                'issues_count': len(brain_issues), 'locked': False,
                'status_text': status_text, 'not_run': False,
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


def _detection_gaps(engines, unsupported=0, trimmed=0, file_count=None):
    """这次到底有哪些地方没查全，给人话短句。

    报告页和 Markdown 导出都从这里取同一份，避免「页面说没检查全、
    导出的 MD 说查得很好」——同一份报告两个说法，客户只会信那个
    对他有利的，剩下的一条都不信。

    三条缺口分开说，因为它们对客户的意义不同：
      引擎没出结果 → 这一类问题这次根本没查
      引擎报错     → 查了但没查完
      文件没解析   → 这些文件里的代码没看（不是引擎的问题）

    改之前这三件事被压成一句「所有引擎都只查了一部分」，于是一份 5 个文件、
    4 个正常解析的报告，第一屏写着「所有引擎都只查了一部分」——既不准确，
    也让人以为整份结果不能用。

    engines 为 None（2026-11-04 之前落库、没有台账的老报告）时返回空：
    拿不到证据就不编缺口。
    """
    if not engines:
        return []

    not_run, errored = [], []
    for brain in BRAINS:
        st = engines.get(str(brain['id']))
        if not isinstance(st, dict):
            continue          # 本次没请求它（免费版锁住 / PoC 未启用），不算缺口
        if not st.get('executed'):
            not_run.append(brain['name'])
        elif st.get('error'):
            errored.append(brain['name'])

    gaps = []
    if not_run:
        gaps.append('%d 个引擎完全没有出结果（%s）'
                    % (len(not_run), '、'.join(not_run[:3])))
    if errored:
        gaps.append('%d 个引擎报错（%s）'
                    % (len(errored), '、'.join(errored[:3])))

    unparsed = (unsupported or 0) + (trimmed or 0)
    if unparsed:
        try:
            total = int(file_count or 0)
        except (TypeError, ValueError):
            total = 0
        if total > 0:
            gaps.append('%d 个文件没能解析（占 %d%%），这些文件里的代码没查过'
                        % (unparsed, int(round(100.0 * unparsed / total))))
        else:
            gaps.append('%d 个文件没能解析，这些文件里的代码没查过' % unparsed)
        if not _coverage_ok(file_count, unsupported, trimmed):
            gaps.append('读到的文件不足一半，本次不给评级')
    return gaps


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

def _resolve_active_team(user_id):
    """解析当前激活的团队身份（主扫描入口用）。

    返回 team_id 或 None。校验 session 里的 active_team_id 是否仍有效
    （用户确实还是该团队成员），无效则返回 None（回退个人身份）。
    """
    team_id = session.get('active_team_id')
    if not team_id or not user_id:
        return None
    try:
        db = get_db()
        row = db.execute(
            'SELECT 1 FROM team_members WHERE team_id = ? AND user_id = ?',
            (team_id, user_id)
        ).fetchone()
        return team_id if row else None
    except Exception as exc:
        logger.warning('[团队] 解析激活团队失败 team_id=%s user_id=%s: %s',
                       team_id, user_id, exc)
        return None


def _scan_credits_with_team_pool(team_id, vip, user_id, total_lines, file_count, scan_mode):
    """团队身份扫描的积分：只扣团队共享积分池，绝不扣个人积分。

    团队无免费档，必然产生积分消耗。

    返回 (credits_cost, error_response, paid_from)。
    paid_from: 'team_pool'
    """
    credits_cost = calculate_scan_cost(total_lines, scan_mode=scan_mode, user_id=user_id)
    if credits_cost <= 0:
        # 极端情况（0 行代码）不产生费用，但仍走团队路径，不扣个人
        return 0, None, 'team_pool'

    try:
        from . import team_governance
        ref_id = f'team:{team_id}:{user_id}:{int(time.time())}'
        if team_governance.consume_team_credits(
            team_id, credits_cost, user_id,
            ref_type='team_scan', ref_id=ref_id,
            remark=f'团队扫描：{total_lines}行，{file_count}个文件，{scan_mode}模式'
        ):
            # 共享池扣费成功，credits_cost 传 0（避免再走个人扣费）
            return 0, None, 'team_pool'

        # 共享池余额不足 → 明确报错，不回退个人积分
        balance = team_governance.get_team_credit_balance(team_id)
        return 0, (
            jsonify({
                'error': (
                    f'团队共享积分不足，本次扫描需 {credits_cost} 积分，'
                    f'团队共享池当前余额 {balance} 积分。请联系团队管理员充值团队积分。'
                ),
                'credits_needed': credits_cost,
                'team_credit_balance': balance,
                'total_lines': total_lines,
            }), HTTP_BAD_REQUEST
        ), 'team_pool'
    except Exception as e:
        logger.error('[扫描] 共享积分池扣费异常 team_id=%s: %s', team_id, e)
        return 0, (
            jsonify({'error': '团队共享积分扣费失败，请稍后重试或联系团队管理员'})
        ), HTTP_BAD_REQUEST


def _scan_credits_handling(vip, user_id, total_lines, file_count, scan_mode='quick'):
    """处理扫描积分逻辑。
    v5.53 修复竞态：移除独立的 check_credit_sufficient，由 consume_credits 原子处理。
    返回 (credits_cost, error_response)。error_response 非 None 表示失败。
    scan_mode: quick/smart/deep 决定计费倍率
    """
    if not vip:
        return 0, None

    credits_cost = calculate_scan_cost(total_lines, scan_mode=scan_mode, user_id=user_id)
    
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


def _brain_ids_for_scan_mode(vip, scan_mode):
    """按检测模式裁剪引擎清单（与扫描器四档路由对齐，v5.164.0）。

    能力递进口径：
      free  → E1+E4+E5+E6（规范层，纯规则，无 AI）
      quick → E1-E7 全量规则，不调 AI、不跑 PoC（零 token、零成本）
      smart → quick 引擎 + AI 语义分析（含 ai 引擎）
      deep  → smart 引擎 + PoC 实际验证（含 ai + poc 引擎）
    """
    if not vip:
        return list(FREE_BRAIN_IDS)
    if scan_mode == 'quick':
        # 纯规则：剔除 ai / poc 引擎
        return [b for b in ALL_BRAIN_IDS if b not in ('ai', 'poc')]
    if scan_mode == 'smart':
        # 规则 + AI 语义：剔除 poc
        return [b for b in ALL_BRAIN_IDS if b != 'poc']
    # deep（或未识别）：规则 + AI + PoC 全量
    return list(ALL_BRAIN_IDS)


def _execute_scanner_call(files_dict, brain_ids, language, vip, user_id,
                          scan_mode='quick', progress_job_id=None):
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

    # 将四档模式透传给扫描器（扫描器已实现 free/quick/smart/deep 能力路由，
    # quick 不跑 AI、smart 跑 AI 语义、deep 跑 AI+PoC）。
    # 兼容扫描器旧版不识别的场景：非 vip 强制 basic（纯规则）。
    scan_mode_for_scanner = scan_mode if vip else 'basic'
    try:
        results = call_scanner(files_dict, brain_ids, {
            'language': language, 'scan_mode': scan_mode_for_scanner,
            'is_vip': vip, 'thresholds': user_thresholds,
            'user_id': str(user_id),  # X-02 fix
            'progress_job_id': progress_job_id,
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
        _project_tag = scan_info.get('project_tag', '')  # 2026-10-22: 后台线程无 request 上下文
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


def _evaluate_quality_gate(db, user_id, results, score, file_count):
    """评估质量门禁

    2026-10-22 修复：原实现两个调用参数全不匹配，异常被自身 except 吞掉，
    导致质量门禁从未生效（gate_results 长期为 0 行）：
      * get_user_active_gate(user_id)        -> 真实签名 (db, user_id)
      * evaluate_gate(gate, score, n, iss, f)-> 真实签名 (scan_result, gate_rules)
    """
    try:
        from modules.quality_gate import evaluate_gate, get_user_active_gate
        _active_gate = get_user_active_gate(db, user_id) if user_id else None
        if not _active_gate:
            return None
        _all_issues = results.get('issues', [])
        _scan_result = {'issues': _all_issues, 'score': score}
        _res = evaluate_gate(_scan_result, _active_gate)
        # 2026-10-22: gate_id 注入（gate_results.gate_id 外键 -> quality_gates.id）
        if _res is not None:
            _gid = _active_gate.get('id') if isinstance(_active_gate, dict) else None
            _res['gate_id'] = _gid
            _res['id'] = _gid
        return _res
    except Exception as _ge:
        logger.warning('P1: gate evaluation failed: %s', _ge, exc_info=True)
        return None


def _scan_visible_to_session(scan):
    """报告访问控制

    旧实现里 /report/<scan_id> 完全没有归属校验：任何拿到链接的人都能看到
    别人的源码片段。这里按"报告属于谁"判定：
      * 匿名扫描（user_id 为空）：scan_id 本身即不可猜的访问凭证，放行；
      * 已登录用户的扫描：只允许本人或管理员查看；
      * 团队扫描（team_id 非空）：同团队所有成员可见（共享扫描结果的核心价值），
        成员被踢后其历史扫描仍归属团队、仍可被团队其他成员追溯（不可抵赖）。
    """
    owner = scan['user_id'] if scan['user_id'] is not None else None
    if not owner:
        return True
    uid = session.get('user_id')
    if uid == owner:
        return True
    admin_id = int(os.environ.get('XINPECT_ADMIN_USER_ID', '6'))
    if uid == admin_id:
        return True

    # P3 团队共享：报告归属团队，团队内成员可见
    # scan 可能是 sqlite3.Row 或 dict，统一用 keys + [] 读取
    try:
        _keys = scan.keys()
        team_id = scan['team_id'] if 'team_id' in _keys else None
    except Exception:
        team_id = None
    if team_id and uid:
        try:
            _db = get_db()
            _m = _db.execute(
                'SELECT 1 FROM team_members WHERE team_id = ? AND user_id = ?',
                (team_id, uid)
            ).fetchone()
            if _m:
                return True
        except Exception:
            pass  # 团队表异常不阻断，走默认拒绝

    return False


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

    # ── 身份感知：切到团队身份后，主扫描自动归队 + 走共享积分池 ──
    active_team_id = _resolve_active_team(user_id)
    paid_from = 'personal' if not active_team_id else None

    # ── 档位决定：团队身份 = 管理员上限 + 成员自选；个人身份 = 本人会员决定 ──
    if active_team_id:
        # 团队档位：管理员配置的是「上限」，成员自选不超过上限。
        # 与子账号本人是否会员、有无个人积分完全无关。
        req_scan_mode = request.form.get('scan_mode', '')
        try:
            from . import team_governance
            actual_scan_mode = team_governance.resolve_team_scan_mode(active_team_id, req_scan_mode)
        except Exception as e:
            logger.warning('[扫描] 融合团队档位失败，回退 quick: %s', e)
            actual_scan_mode = 'quick'
        # 团队无免费档（只有 quick/smart/deep），必然走引擎能力，engine_vip 恒 True
        engine_vip = True
    else:
        # 个人身份：本人会员决定档位
        req_scan_mode = request.form.get('scan_mode', '')
        if not vip:
            actual_scan_mode = 'free'
        elif req_scan_mode in ('quick', 'smart', 'deep'):
            actual_scan_mode = req_scan_mode
        else:
            actual_scan_mode = 'quick'
        engine_vip = vip
    scan_mode = actual_scan_mode  # 记录到DB用

    # 按模式裁剪引擎清单：quick 不调 AI/PoC、smart 加 AI 语义、deep 加 PoC 验证
    brain_ids = _brain_ids_for_scan_mode(engine_vip, actual_scan_mode)

    file_count = len(files_dict)
    total_lines = count_total_lines(files_dict)

    # 积分处理：团队身份走共享池，个人身份走个人积分
    if active_team_id:
        credits_cost, err, paid_from = _scan_credits_with_team_pool(
            active_team_id, engine_vip, user_id, total_lines, file_count, actual_scan_mode
        )
    else:
        credits_cost, err = _scan_credits_handling(vip, user_id, total_lines, file_count, scan_mode=actual_scan_mode)
    if err:
        return err

    # 空文件或免费扫描，credits_cost=0，跳过扣费
    if credits_cost == 0:
        pass  # 继续执行扫描

    # 异步扫描：提交到后台线程池，立即返回 scan_id
    source = _get_source_from_request()
    scan_id, err_resp, err_code = _do_async_scan(
        files_dict, brain_ids, language, engine_vip, user_id, credits_cost, total_lines, scan_mode, source,
        team_id=active_team_id
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
        'team_id': active_team_id,
        'paid_from': paid_from if active_team_id else 'personal',
        'message': '扫描任务已提交，请等待完成',
    })


def _run_post_scan_hooks(db, scan_info, results, file_count):
    """执行扫描后处理：度量写入、告警触发、门禁评估"""
    user_id = scan_info.get('user_id')
    _write_scan_metrics(db, scan_info, results)
    db.commit()  # 2026-10-22: metrics 独立提交，不再依赖门禁分支
    _trigger_alerts_async(user_id, scan_info['score'], scan_info['grade'], results)

    gate_result = _evaluate_quality_gate(db, user_id, results, scan_info['score'], file_count)
    if gate_result and user_id and gate_result.get('gate_id'):
        try:
            db.execute("""
                INSERT INTO gate_results (scan_id, user_id, gate_id, passed, details_json)
                VALUES (?, ?, ?, ?, ?)
            """, (scan_info['scan_id'], user_id,
                  gate_result.get('gate_id'),
                  1 if gate_result.get('passed') else 0,
                  json.dumps(gate_result, ensure_ascii=False)))
            db.commit()
        except Exception as _ge2:
            # 2026-10-22: 原为 except Exception: pass，静默吞掉写入失败
            logger.warning('P1: gate_results insert failed: %s', _ge2, exc_info=True)


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

def _async_scan_fail(scan_id, user_id, credits_cost, err):
    """扫描失败：提炼错误信息、退款（重试3次）、落 failed 状态。"""
    import sqlite3 as _sqlite3
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


def _async_scan_success(scan_id, user_id, files_dict, total_lines, results, vip):
    """扫描成功：计算评分/等级、落 completed 状态、回填积分流水。"""
    import sqlite3 as _sqlite3
    avail_brains = None if vip else FREE_BRAIN_IDS
    _ledger, _uns, _trim = _ledger_of(results)
    score = calculate_score(results["issues"], available_brain_ids=avail_brains)
    tier_scores = calculate_tier_scores(
        results["issues"], available_brain_ids=avail_brains, is_vip=vip,
        engines=_ledger, unsupported=_uns, trimmed=_trim,
        file_count=len(files_dict),
    )
    # 分数与等级同源：calculate_score 已经默认剔除复核未采纳的条目，
    # grade_of 只把这个分数读成档位（三层全 S 才在 S 之上加 SS/SSS）。
    grade = grade_of(score, tier_scores, is_vip=vip)

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
    return score, grade


def _run_post_hooks(scan_id, user_id, files_dict, total_lines, scan_mode, results, score, grade):
    """接回扫描后处理链（指标写入 / 告警触发 / 质量门禁）。失败仅告警，不影响主流程。"""
    try:
        _hook_info = {
            "scan_id": scan_id, "user_id": user_id,
            "score": score, "grade": grade,
            "file_count": len(files_dict), "total_lines": total_lines,
            "scan_mode": scan_mode, "project_tag": "",
        }
        _hdb = get_db()
        _run_post_scan_hooks(_hdb, _hook_info, results, len(files_dict))
        _hdb.commit()
    except Exception as _he:
        logger.warning("post_scan_hooks failed: %s", _he, exc_info=True)


def _async_scan_task(scan_id, user_id, files_dict, brain_ids, language, vip,
                     credits_cost, total_lines, scan_mode, source, progress_callback=None):
    """后台线程执行的异步扫描任务（在 app_context 中运行）"""
    import sqlite3 as _sqlite3
    with app.app_context():
        try:
            # 2026-11-05：进度只来自扫描器真实事件。删掉原先编的
            # 「正在连接扫描引擎 / 正在生成报告 / 后处理中」三段（它们跟实际毫无关系）。
            from modules.scan_progress_bridge import start as _progress_start
            _progress_start(scan_id)
            results, err = _execute_scanner_call(files_dict, brain_ids, language, vip,
                                                 user_id, scan_mode=scan_mode,
                                                 progress_job_id=scan_id)

            if err:
                _async_scan_fail(scan_id, user_id, credits_cost, err)
                return

            score, grade = _async_scan_success(scan_id, user_id, files_dict, total_lines, results, vip)

            # 2026-10-22 修复：接回扫描后处理链（指标写入 / 告警触发 / 质量门禁）
            # 回归原因：10/21 异步化改造时丢失了 _run_post_scan_hooks 调用，
            # 只留下上面那句"后处理中"的进度提示。
            _run_post_hooks(scan_id, user_id, files_dict, total_lines, scan_mode, results, score, grade)

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
        finally:
            try:
                from modules.scan_progress_bridge import stop as _progress_stop
                _progress_stop(scan_id)
            except Exception:
                pass


@app.route("/api/scan/status/<scan_id>")
def scan_status(scan_id):
    """查询扫描任务状态（供前端轮询）"""
    job_status = job_manager.get_status(scan_id)

    db = get_db()
    row = db.execute(
        "SELECT scan_status, scan_progress, scan_progress_text, scan_error, score, grade, issue_count, scan_progress_events, files_meta FROM scans WHERE scan_id = ?",
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
        "progress_source": "engine",
    }
    try:
        _snap = json.loads(row[7]) if row[7] else {}
    except Exception:
        _snap = {}
    if not isinstance(_snap, dict):
        _snap = {}
    resp["events"] = _snap.get("events") or []
    resp["engines_done"] = _snap.get("engines_done", 0)
    resp["engines_total"] = _snap.get("engines_total", 0)
    _files = _snap.get("files") or []
    if not _files:
        try:
            _files = json.loads(row[8]) if row[8] else []
        except Exception:
            _files = []
    resp["files"] = _files
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


def _do_async_scan(files_dict, brain_ids, language, vip, user_id, credits_cost, total_lines, scan_mode, source, team_id=None):
    """将扫描任务提交到后台线程池，立即返回 scan_id。
    team_id 可选：团队扫描时传入，把结果归属到团队（个人扫描保持 None）。
    """
    scan_id = _generate_scan_id()
    title = _build_scan_title(files_dict)
    file_count = len(files_dict)

    db = get_db()
    db.execute("INSERT INTO scans (scan_id, user_id, title, file_count, files_meta, results, score, grade, issue_count, language, credits_spent, total_lines, scan_mode, source, scan_status, scan_progress, scan_progress_text, team_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
               (scan_id, user_id, title, file_count,
                json.dumps(list(files_dict.keys()), ensure_ascii=False),
                "[]", 0, "", 0, language,
                credits_cost if user_id else 0,
                total_lines, scan_mode, source,
                "pending", 5, "正在准备扫描", team_id))
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

def _build_profile_groups(profile_items, max_groups=60, sample_files=3):
    """把依赖画像条目按「识别到的库/API」聚合，供报告页展示。

    画像是「这个项目用了什么」，同一类特征往往在几十个文件里重复命中，
    逐条列出没有意义，所以按 title 聚成一行：命中几次 + 出现在哪些文件。
    不参与评分、不计入问题总数。
    """
    groups = {}
    for item in profile_items or []:
        title = (item.get('title') or item.get('rule_id') or '').strip()
        if not title:
            continue
        g = groups.setdefault(title, {
            'title': title,
            'rule_id': item.get('rule_id', ''),
            'count': 0,
            'files': [],
        })
        g['count'] += 1
        fp = item.get('file', '')
        if fp and fp not in g['files'] and len(g['files']) < sample_files:
            g['files'].append(fp)

    ordered = sorted(groups.values(), key=lambda x: (-x['count'], x['title']))
    return ordered[:max_groups]


# 报告页最多展开多少条抑制记录（清单本身在 scanner 侧已封顶 500）
SUPPRESSED_PAGE_MAX = 300

_SUPPRESSED_STAGE_FALLBACK = {
    'b13_reject': 'AI 降噪判定为误报',
    'b13_likely_fp_reject': 'AI 降噪复核判定为误报',
    'b13_dedup_copy': '同文件同问题的代表条目被判误报，本条连带抑制',
    'specialist_reject': '专科AI 未确认且评分低于阈值',
}


def _build_suppressed_groups(results, max_items=SUPPRESSED_PAGE_MAX):
    """把「被抑制清单」按抑制阶段分组，供报告页回答「这条为什么没报」。

    抑制清单 = 扫描发现、但被 AI 判定为误报而没计入报告的问题
    （扫描器 results.ai_denoise.suppressed_issues，本页从 results 顶层同名
    字段读取，由 modules/scanner.py 的 _collect_suppressed 透传）。

    它不是缺陷：不进问题数、不影响评分、不进严重度分布。
    分组维度用「抑制阶段」而不是文件——客户质疑时问的是
    「凭什么说这条不算」，对应的是阶段，不是路径。

    返回 (groups, total)。groups 里每个元素：
        {stage, label, count(真实总数), records(展示用，可能少于 count), records_shown}

    注意：展示用的列表字段名**不能叫 items**——Jinja 取 g.items 会命中 dict 自带的
    dict.items 方法（属性优先于下标），渲染时报 object is not iterable。
    """
    records = results.get('suppressed_issues') if isinstance(results, dict) else None
    if not isinstance(records, list):
        records = []
    stats = results.get('suppressed_stats') if isinstance(results, dict) else None
    if not isinstance(stats, dict):
        stats = {}
    real_by_stage = stats.get('by_stage')
    if not isinstance(real_by_stage, dict):
        real_by_stage = {}

    groups = {}
    order = []
    shown = 0
    for rec in records:
        if not isinstance(rec, dict):
            continue
        stage = rec.get('stage') or 'unknown'
        group = groups.get(stage)
        if group is None:
            group = {
                'stage': stage,
                'label': (rec.get('stage_label')
                          or _SUPPRESSED_STAGE_FALLBACK.get(stage)
                          or '已被抑制'),
                'count': 0,
                'records': [],
            }
            groups[stage] = group
            order.append(stage)
        group['count'] += 1
        if shown < max_items:
            group['records'].append({
                'rule_id': rec.get('check_id') or '',
                'title': rec.get('title') or '',
                'file': rec.get('file') or '',
                'line': rec.get('line') or 0,
                'reason': rec.get('reason') or '',
                'confidence': rec.get('confidence'),
                'engine': rec.get('engine') or '',
            })
            shown += 1

    # 清单可能被截断：用扫描器给的真实分阶段计数覆盖，避免显示成「就这么几条」
    for stage, group in groups.items():
        real = real_by_stage.get(stage)
        if isinstance(real, int) and real > group['count']:
            group['count'] = real

    ordered = [groups[s] for s in order]
    ordered.sort(key=lambda x: (-x['count'], x['label']))
    for group in ordered:
        group['records_shown'] = len(group['records'])

    try:
        total = int(stats.get('total'))
    except (TypeError, ValueError):
        total = sum(g['count'] for g in ordered)
    return ordered, total


# 2026-11-03: 对外公开名。完整报告页（本模块）与 CI 分享页（modules/ci.py）
# 必须用同一份分组逻辑——客户在两个页面上看到的「为什么没报」不能有两种说法，
# 所以 CI 侧直接 import 这个名字，而不是复制一份实现。
build_suppressed_groups = _build_suppressed_groups

# 同理：依赖画像（「用了哪些库/API」）的分组也共用一份，避免两页对同一批
# profile_items 聚出不同的行数与排序。
build_profile_groups = _build_profile_groups


@app.route('/report/<scan_id>')
def report_page(scan_id):
    """报告页"""
    db = get_db()
    scan = db.execute('SELECT * FROM scans WHERE scan_id = ?', (scan_id,)).fetchone()

    if not scan or not _scan_visible_to_session(scan):
        return render_template('404.html'), 404

    results = json.loads(scan['results']) if scan['results'] else {'issues': []}
    # 落库数据不保证是对象：实测 api_scan_1794626939255_15（引擎超时失败）
    # 的 results 存的是 "[]"，直接 .get() 就整页 500。
    # 报告页不能因为一条脏数据崩掉——客户看到的是「网站坏了」。
    if not isinstance(results, dict):
        results = {'issues': []}
    all_issues = results.get('issues', [])
    if not isinstance(all_issues, list):
        all_issues = []
    # P0: style 问题单独展示
    style_issues = results.get('style_issues', [])
    style_count = len(style_issues)
    # 2026-11-04: 积木五维要能看到 style_issues（AI 降级的问题）和引擎台账，
    # 否则「查了没问题」和「查出来但被降级/引擎没跑」在页面上是同一个样子
    bb_scores = calculate_building_block_scores(
        all_issues,
        file_count=scan['file_count'],
        style_issues=style_issues,
        engines=results.get('engines'),
    )
    # 2026-11-03: 依赖画像（「用了哪些库/API」）单独成栏，不是缺陷、不计分
    profile_items = results.get('profile_items') or []
    profile_count = len(profile_items)
    profile_groups = _build_profile_groups(profile_items)
    # 2026-11-03: 被抑制清单（AI 判为误报而没进报告的条目），同样单独成栏、不计分
    suppressed_groups, suppressed_total = _build_suppressed_groups(results)
    vip = is_vip_user()

    # 2026-11-04: 引擎台账。三个字段回答同一个问题——「这次到底查全了没有」：
    #   engines          某个 brain 跑了/报错/被降级
    #   unsupported_files 有文件没被解析（没读过的代码里可能有洞）
    #   trimmed_files     有文件被截断（后半截没进分析）
    # 缺台账的老报告是 None，下游一律退回旧行为。
    _ledger, _unsupported_n, _trimmed_n = _ledger_of(results)

    dimensions = _build_dimensions(all_issues, vip, _ledger, _unsupported_n, _trimmed_n)
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

    # ===== 三层分层（2026-11-22）=====
    # 主列表只放「必须修 + 建议改」；复核判定不成立的单列在报告最后。
    # 改之前：全库 66748 条 issue 里 19040 条（28.5%）带 ai_false_positive，
    # AI 写了分析说「无需修复」，报告照单全收，还把其中两条排进「推荐优先修复」。
    # gaps 一起传进去：0 条问题 + 有引擎没跑成时，第一句不许说「没有问题」。
    _gaps = _detection_gaps(_ledger, _unsupported_n, _trimmed_n, scan['file_count'])
    _verdict = report_verdict.build(visible_issues, gaps=_gaps)
    _must_items = _verdict['tiers'][TIER_MUST]
    _should_items = _verdict['tiers'][TIER_SHOULD]
    _excluded_items = _verdict['tiers'][TIER_EXCLUDED]
    for _it in _must_items + _should_items + _excluded_items:
        # 打临时标记给修复路线图和模板用，不落库
        _iss = _it['issue']
        _iss['_verdict_tier'] = _it['verdict']['tier']
        _iss['_verdict_kind'] = _it['verdict']['kind']
        _iss['_verdict_reason'] = _it['verdict']['reason']
        _iss['_verdict_rank'] = _it['verdict']['rank']
        _iss['_verdict_ai_note'] = _it['verdict']['ai_note']
    # 主列表 = 前两层。第三层不进 visible_issues，但会单独渲染。
    visible_issues = [i['issue'] for i in (_must_items + _should_items)]

    avail_brains = None if vip else FREE_BRAIN_IDS
    tier_scores = calculate_tier_scores(
        all_issues, available_brain_ids=avail_brains, is_vip=vip,
        engines=_ledger, unsupported=_unsupported_n, trimmed=_trimmed_n,
        file_count=scan['file_count'],
    )
    severity_counts = _compute_severity_counts(visible_issues)

    # 分数与等级都在这里按「我们认的问题」重算，不再读库里存的那两个数。
    # 库里存的是旧口径（含复核未采纳、等级走三层平均），而且 441 份历史报告里
    # 有 76 份两个数互相打架。报告是给客户看的那份东西，必须自洽：
    # 同一份报告在任何时候打开、在哪个页面打开，都是同一个分、同一个档。
    score = calculate_score(all_issues, available_brain_ids=avail_brains)
    grade = grade_of(score, tier_scores, is_vip=vip)

    created_at = scan['created_at']
    try:
        dt = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
        created_at_str = dt.strftime('%Y-%m-%d %H:%M')
    except (ValueError, TypeError):
        created_at_str = created_at

    # 修复路线图
    fix_roadmap = build_fix_roadmap(visible_issues)
    fix_progress = build_fix_progress(scan_id, session.get("user_id"))

    # 一句话结论摘要：整段由 report_verdict 给出，页面不再自己拼。
    # 缺口（哪些引擎没跑成/哪些文件没解析）在 build 时就已经写进第一句，
    # 所以这里不需要再补文字——补文字就是第二个拼装处，早晚两边不一致。
    _vc = _verdict['conclusion']
    conclusion = {
        'headline': _vc['headline'],
        'detail': _vc.get('detail') or '',
        'tone': _vc['tone'],
    }

    scan_mode = scan['scan_mode'] if 'scan_mode' in scan.keys() else ''
    is_fix_eligible = bool(vip and scan_mode == 'deep')

    return render_template(
        'report.html',
        scan_id=scan_id,
        report_title=scan['title'],
        score=score,
        grade=grade,
        conclusion=conclusion,
        verdict=_verdict,
        must_count=len(_must_items),
        should_count=len(_should_items),
        excluded_count=len(_excluded_items),
        excluded_items=_excluded_items,
        tier_must_meta=report_verdict.TIER_META[TIER_MUST],
        tier_should_meta=report_verdict.TIER_META[TIER_SHOULD],
        tier_excluded_meta=report_verdict.TIER_META[TIER_EXCLUDED],
        ai_exclude_threshold=report_verdict.AI_EXCLUDE_MIN_CONFIDENCE,
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
        profile_groups=profile_groups,
        profile_count=profile_count,
        suppressed_groups=suppressed_groups,
        suppressed_total=suppressed_total,
        suppressed_stats=results.get('suppressed_stats') or {},
        severity_counts=severity_counts,
        bb_scores=bb_scores,
        is_vip=vip,
        scan_mode=scan_mode,
        is_fix_eligible=is_fix_eligible,
        fix_roadmap=fix_roadmap,
        fix_progress=fix_progress,
        share_token=scan['share_token'],
        # 报告页不弹「推荐有礼」：那是交付现场，不是拉新现场
        suppress_promo=True,
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

# 导出的独立 HTML：去掉导航、页脚、操作按钮、反馈区，只留报告正文。
# 静态资源靠注入的 <base> 指向线上地址，所以导出的文件双击就能看。
_EXPORT_STYLE = """
<style id="xinpect-export-style">
.topbar, .footer, .report-actions, .feedback-section, #feedbackSection,
.fp-mark-btn, .issue-toggle, .filter-bar, .tab-nav, .drill-down-section,
.one-click-fix-actions { display: none !important; }
body { background:#fff !important; }
</style>
"""


@app.route('/report/<scan_id>/html')
def download_html_report(scan_id):
    """下载 HTML 报告（单文件，可直接转发给同事/领导）。

    2026-11-04 之前这里是从引擎取 `/report/<id>`，但引擎从来没有这个路由
    （带 API Key 实测 404），也没有任何模板指向它——也就是说这是个死功能，
    谁点谁看「报告生成失败」。更根本的是：就算引擎能出，那也是第二套渲染、
    第二套数字，正是这一轮在收的「同一份数据两套口径」。

    现在复用 report_page 的渲染结果，注入 <base> 让静态资源走线上地址，
    并隐藏导航与按钮。导出件与网页版是同一份 DOM，数字不可能对不上。
    """
    rendered = report_page(scan_id)
    if isinstance(rendered, tuple):        # 无权访问 / 不存在，原样透传 404
        return rendered
    html_content = rendered if isinstance(rendered, str) else rendered.get_data(as_text=True)

    head_inject = f'<base href="{request.url_root}">' + _EXPORT_STYLE
    if '<head>' in html_content:
        html_content = html_content.replace('<head>', '<head>\n' + head_inject, 1)
    else:
        html_content = head_inject + html_content

    response = make_response(html_content)
    response.headers['Content-Type'] = 'text/html; charset=utf-8'
    response.headers['Content-Disposition'] = (
        f'attachment; filename="xinpect_report_{scan_id[:8]}.html"'
    )
    # 报告内容是私有数据，别让中间层或浏览器缓存成公共资源
    response.headers['Cache-Control'] = 'private, no-store'
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
    try:
        _res_md = json.loads(scan['results']) if scan['results'] else {}
    except (ValueError, TypeError):
        _res_md = {}
    _led_md, _uns_md, _trim_md = _ledger_of(_res_md)
    tier_scores_md = calculate_tier_scores(
        all_issues, available_brain_ids=avail_brains_md, is_vip=vip,
        engines=_led_md, unsupported=_uns_md, trimmed=_trim_md,
        file_count=scan['file_count'],
    )
    # 导出的 MD 与页面同一口径。原来这里写 scan["score"]（旧口径存值），
    # 同一份报告「看页面 82 分、下载 MD 50 分」。
    md_score = calculate_score(all_issues, available_brain_ids=avail_brains_md)
    md_grade = grade_of(md_score, tier_scores_md, is_vip=vip)

    # 查不全时不能写「S 级」——那是把没查的地方当成干净
    _md_grade_text = '未完整检测（评级不可用）' if md_grade == '—' else f'{md_grade} 级'
    md_lines.append(f'**综合评级：** {_md_grade_text}')
    md_lines.append(f'**综合得分：** {md_score} / 100')
    md_lines.append('')

    # 结论与报告页同源：同一个 build，同一份缺口清单。
    # 改之前这里走 _build_conclusion（按 severity 五档计数），页面走三层分层，
    # 同一份报告「页面说必须修 2 个、导出的 MD 说 4 个高危建议优先修复」。
    _md_verdict = report_verdict.build(
        all_issues, gaps=_detection_gaps(_led_md, _uns_md, _trim_md))
    _conc = _md_verdict['conclusion']
    md_lines.append(f'**结论：** {_conc["headline"]}')
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
        md_lines.append(f'> ⚡ 免费版仅展示规范层结果，[升级专业版](https://xinpect.xingwangzhineng.com) 解锁全部 7 大规则引擎 + AI 语义 + PoC 验证')
    md_lines.append('')
    md_lines.append('---')
    md_lines.append('')
    return md_lines, tier_scores_md, visible_issues


def _build_md_dimension_scores(scan, visible_issues, vip):
    """构建各维度得分表

    2026-11-04：与报告页同源——引擎没查成写「未检测」，不写 100。
    """
    md_lines = []
    md_lines.append('## 各维度得分')
    md_lines.append('')
    md_lines.append('| 维度 | 名称 | 得分 | 问题数 |')
    md_lines.append('|------|------|------|--------|')
    try:
        _res_dim = json.loads(scan['results']) if scan['results'] else {}
    except (ValueError, TypeError):
        _res_dim = {}
    _led_dim, _uns_dim, _trim_dim = _ledger_of(_res_dim)
    for brain in BRAINS:
        if vip or brain['id'] in FREE_BRAIN_ID_SET:
            brain_issues = [i for i in visible_issues if str(i.get('brain_id')) == brain['id']]
            _state, _state_text = _dim_card_state(
                _led_dim, brain['id'], _uns_dim, _trim_dim
            )
            if _state == _DIM_NOT_RUN:
                md_lines.append(f'| {brain["code"]} | {brain["name"]} | {_state_text} | {len(brain_issues)} |')
            else:
                dim_score = calculate_dimension_score(brain_issues)
                _suffix = f'（{_state_text}）' if _state_text else ''
                md_lines.append(f'| {brain["code"]} | {brain["name"]} | {dim_score}{_suffix} | {len(brain_issues)} |')
        else:
            md_lines.append(f'| {brain["code"]} | {brain["name"]} | 🔒 升级解锁 | - |')
    md_lines.append('')
    return md_lines


def _build_md_issue_detail(brain, visible_issues):
    """构建单个维度的问题详情"""
    md_lines = []
    brain_issues = [i for i in visible_issues if str(i.get('brain_id')) == brain['id']]
    if not brain_issues:
        return md_lines

    md_lines.append(f'### {brain["code"]} {brain["name"]}')
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


def _build_md_issues(visible_issues, vip, profile_groups=None, gaps=None):
    """构建问题详情部分"""
    md_lines = []
    md_lines.append('## 问题详情')
    md_lines.append('')

    if not visible_issues:
        # 这句原来写死成「未检测到任何问题，代码质量优秀」——有文件没解析时
        # 照样报喜。现在由结论统一给：有缺口就说「没查出问题，但没检查全」。
        _empty_head = report_verdict.build([], gaps=gaps)['conclusion']['headline']
        md_lines.append('🎉 **%s**' % _empty_head)
    else:
        visible_brains = BRAINS if vip else [b for b in BRAINS if b['id'] in FREE_BRAIN_ID_SET]
        for brain in visible_brains:
            md_lines.extend(_build_md_issue_detail(brain, visible_issues))

    # 2026-11-03: 依赖画像单列一节，明确标注「不是缺陷」
    if profile_groups:
        _total = sum(g['count'] for g in profile_groups)
        md_lines.append('')
        md_lines.append(f'## 技术栈与依赖画像（{_total} 项，非缺陷）')
        md_lines.append('')
        md_lines.append('> 这些是扫描识别到的库 / 函数 / API 使用特征，用于了解项目构成，不代表存在问题。')
        md_lines.append('')
        md_lines.append('| 识别项 | 命中 | 示例文件 |')
        md_lines.append('|---|---|---|')
        for g in profile_groups:
            _files = '<br>'.join(g['files']) if g['files'] else '-'
            md_lines.append(f"| {g['title']} | {g['count']} | {_files} |")

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
    # 落库数据不保证是对象：实测 api_scan_1794626939255_15（引擎超时失败）
    # 的 results 存的是 "[]"，直接 .get() 就整页 500。
    # 报告页不能因为一条脏数据崩掉——客户看到的是「网站坏了」。
    if not isinstance(results, dict):
        results = {'issues': []}
    all_issues = results.get('issues', [])
    if not isinstance(all_issues, list):
        all_issues = []
    # P0: style 问题单独展示
    style_issues = results.get('style_issues', [])
    style_count = len(style_issues)
    # 2026-11-03: 依赖画像（非缺陷，单列一节）
    profile_groups = _build_profile_groups(results.get('profile_items', []))
    vip = is_vip_user()

    if not vip:
        for _iss in all_issues:
            _iss['is_free_locked'] = True

    header_lines, tier_scores_md, visible_issues = _build_md_header(scan, all_issues, vip)
    dimension_lines = _build_md_dimension_scores(scan, visible_issues, vip)
    _md_gaps = _detection_gaps(*_ledger_of(results), file_count=scan['file_count'])
    issues_lines = _build_md_issues(visible_issues, vip, profile_groups, gaps=_md_gaps)

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
            # 扫描器引擎 ID：6 = 组件合规（engine.e6_component，即原 B9 组件契约检测）
            'brains': ['6'],
            'scan_mode': 'basic',
            'is_vip': False,
        }, timeout=REPORT_TIMEOUT_SECONDS,
            headers={"X-API-Key": SCANNER_API_KEY} if SCANNER_API_KEY else {})
        resp.raise_for_status()
        raw = resp.json()
    except Exception as e:
        app.logger.exception('Component check scanner call failed: %s', e)
        return jsonify({'success': False, 'error': '检测服务暂不可用，请稍后重试'}), HTTP_INTERNAL_ERROR

    b9_result = raw.get('results', {}).get('6', {})
    raw_issues = b9_result.get('issues', [])
    # 注：扫描器返回的 per-brain score 基于旧的五级严重度模型，对组件契约类问题（已归为四级
    # 梯度 restriction/suspicious）不扣分，恒为 100；与主扫描流程一致，改用本站 calculate_score
    # 依据问题列表计算契约合规分，使 CC_SCORE_S/A/B（90/75/60）分档真实生效。
    score = calculate_score(raw_issues)

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

    brain_id = (request.args.get('brain_id') or '').strip()
    if not brain_id:
        return jsonify({'error': '请指定 brain_id'}), HTTP_BAD_REQUEST

    days = min(max(request.args.get('days', 30, type=int), 7), 365)
    data = get_user_trends(user_id, days=days)

    brain_data = [
        {'date': dp['date'], 'score': dp.get('brain_scores', {}).get(str(brain_id))}
        for dp in data['data_points']
    ]
    brain_name = brain_label(brain_id)

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
