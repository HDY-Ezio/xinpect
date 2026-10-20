#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Xinpect - CI/CD Integration Module
v1.0 - 2026-09-11

CI/CD 集成模块：API 扫描、分享报告、徽章 SVG
"""
import json
import time
import secrets
import hashlib
import os
import re
import subprocess
import tempfile
import shutil
import sqlite3
from datetime import datetime
from fnmatch import fnmatch

from flask import Blueprint, request, jsonify, make_response, render_template

from .constants import (
    app, logger, DB_PATH,
    HTTP_OK, HTTP_BAD_REQUEST, HTTP_UNAUTHORIZED,
    HTTP_NOT_FOUND, HTTP_INTERNAL_ERROR, HTTP_PAYMENT_REQUIRED,
    HTTP_ENTITY_TOO_LARGE,
    CODE_EXTS, ARCHIVE_SKIP_DIRS, ALL_BRAIN_IDS, FREE_BRAIN_IDS,
)
from .db import get_db
from .scanner import call_scanner, ScanEngineError
from .scoring import (
    get_user_credits, consume_credits, grant_credits,
    calculate_scan_cost, count_total_lines,
    calculate_score,
)
from .helpers import login_required, get_current_user
from .csrf_protection import csrf_required


ci_bp = Blueprint("ci", __name__)

# ── 常量 ──
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX = 3
MAX_CODE_FILES = 200
MAX_SINGLE_FILE_KB = 500
BADGE_CACHE_SECONDS = 300

# 抽样预览：基础引擎（规范层，免费可见）vs 深度引擎（质量层+防护层，锁定预览）
BASIC_BRAIN_IDS = {'1', '6', '7', '9'}  # 规范层 = 免费可见
DEEP_BRAIN_IDS = {'2', '3', '4', '5', '8'}  # 质量层 + 防护层 = 锁定预览


# ============================================================
# 数据库初始化（纯 sqlite3，不依赖 Flask app context）
# ============================================================

def init_ci_tables():
    """直接操作 sqlite3 创建 CI 相关表和字段"""
    db = sqlite3.connect(DB_PATH)
    cur = db.cursor()

    # ci_configs 表
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ci_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            default_scan_mode TEXT NOT NULL DEFAULT 'quick',
            default_threshold INTEGER NOT NULL DEFAULT 60,
            ignore_patterns TEXT DEFAULT NULL,
            auto_share INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # scans 表新增 CI 相关字段
    cols = {row[1] for row in cur.execute("PRAGMA table_info(scans)").fetchall()}
    alters = [
        ("source", "TEXT DEFAULT 'web'"),
        ("ci_repo", "TEXT DEFAULT NULL"),
        ("ci_branch", "TEXT DEFAULT NULL"),
        ("ci_commit_sha", "TEXT DEFAULT NULL"),
        ("share_token", "TEXT DEFAULT NULL"),
    ]
    for col_name, col_type in alters:
        if col_name not in cols:
            cur.execute("ALTER TABLE scans ADD COLUMN %s %s" % (col_name, col_type))
            logger.info("DB migration: added scans.%s %s", col_name, col_type)

    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_scans_share_token ON scans(share_token)")
    db.commit()
    db.close()
    logger.info("CI tables initialized.")


# ============================================================
# 辅助函数
# ============================================================

def _verify_ci_api_key(api_key):
    """验证 API Key，返回 (user_id, api_key_name) 或 (None, None)"""
    if not api_key:
        return None, None
    db = get_db()
    row = db.execute(
        "SELECT user_id, name FROM api_keys WHERE api_key = ? AND is_active = 1",
        (api_key,)
    ).fetchone()
    if not row:
        return None, None
    db.execute(
        "UPDATE api_keys SET last_used = datetime('now', 'localtime'), usage_count = usage_count + 1 WHERE api_key = ?",
        (api_key,)
    )
    db.commit()
    return row[0], row[1]


def _get_ci_config(user_id):
    """获取用户 CI 偏好配置"""
    db = get_db()
    row = db.execute(
        "SELECT default_scan_mode, default_threshold, ignore_patterns, auto_share FROM ci_configs WHERE user_id = ?",
        (user_id,)
    ).fetchone()
    if row:
        return {
            'default_scan_mode': row[0] or 'quick',
            'default_threshold': row[1] or 60,
            'ignore_patterns': json.loads(row[2]) if row[2] else [],
            'auto_share': bool(row[3]),
        }
    return {
        'default_scan_mode': 'quick',
        'default_threshold': 60,
        'ignore_patterns': [],
        'auto_share': False,
    }


def _determine_scan_mode(user_id, requested_mode, is_vip):
    """
    扫描档位策略：
    - 非 VIP → 强制 free
    - VIP + 未指定 → 用户默认（默认 quick）
    - VIP + 指定 → 允许任意档位
    """
    if not is_vip:
        return 'free'
    if not requested_mode:
        config = _get_ci_config(user_id)
        return config.get('default_scan_mode', 'quick')
    allowed = ('free', 'quick', 'smart', 'deep')
    if requested_mode in allowed:
        return requested_mode
    return 'quick'


# 频率限制：进程内缓存
_rate_cache = {}

def _check_rate_limit(user_id):
    now = time.time()
    timestamps = _rate_cache.get(user_id, [])
    timestamps = [t for t in timestamps if now - t < RATE_LIMIT_WINDOW]
    _rate_cache[user_id] = timestamps
    if len(timestamps) >= RATE_LIMIT_MAX:
        retry_after = int(RATE_LIMIT_WINDOW - (now - timestamps[0])) + 1
        return False, max(1, retry_after)
    timestamps.append(now)
    return True, 0


def _filter_code_files(code_files, ignore_patterns):
    """过滤忽略文件"""
    if not ignore_patterns:
        return code_files, 0
    valid = {}
    ignored = 0
    for path, content in code_files.items():
        skip = any(fnmatch(path, p) or fnmatch(path.split('/')[-1], p) for p in ignore_patterns)
        if skip:
            ignored += 1
        else:
            valid[path] = content
    return valid, ignored


def _calc_score_from_result(scanner_result):
    """从扫描结果计算总分"""
    try:
        issues = scanner_result.get('issues', [])
        if not issues:
            return 100
        return calculate_score(issues)
    except Exception:
        total = scanner_result.get('total_issues', 0)
        if total == 0:
            return 100
        return max(0, 100 - total * 3)


def _count_issues_by_severity(issues):
    counts = {'critical': 0, 'warning': 0, 'info': 0}
    for issue in issues:
        sev = str(issue.get('severity', '')).lower()
        if sev in ('critical', 'error', 'fatal'):
            counts['critical'] += 1
        elif sev in ('warning', 'major'):
            counts['warning'] += 1
        else:
            counts['info'] += 1
    return counts


def _save_ci_scan(user_id, scan_id, scanner_result, scan_mode, ci_repo, ci_branch, ci_commit_sha, total_lines=0, auto_share=False):
    """保存 CI 扫描记录，返回 (record_id, share_token)"""
    db = get_db()
    score = _calc_score_from_result(scanner_result)
    issues_json = json.dumps(scanner_result.get('issues', [])[:200], ensure_ascii=False)
    summary_json = json.dumps({
        'total_issues': scanner_result.get('total_issues', 0),
        'file_count': scanner_result.get('file_count', 0),
        'scan_time': scanner_result.get('scan_time', 0),
        'version': scanner_result.get('version', ''),
    })

    share_token = None
    if auto_share:
        share_token = secrets.token_urlsafe(12)

    # 构建 issues 摘要 JSON（存入 results 列）
    issues_summary = json.dumps({
        'issues': scanner_result.get('issues', [])[:200],
        'version': scanner_result.get('version', ''),
        'scan_time': scanner_result.get('scan_time', 0),
    }, ensure_ascii=False)
    
    # 构建 files_meta（存入 files_meta 列）
    files_meta = json.dumps({
        'file_count': scanner_result.get('file_count', 0),
        'source': 'ci',
        'repo': ci_repo,
        'branch': ci_branch,
        'commit': ci_commit_sha,
    })
    
    db.execute("""
        INSERT INTO scans (user_id, scan_id, title, score, grade, issue_count,
                          file_count, total_lines, credits_spent, language,
                          results, files_meta, scan_mode, source,
                          ci_repo, ci_branch, ci_commit_sha, share_token,
                          created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ci', ?, ?, ?, ?,
                datetime('now', 'localtime'))
    """, (user_id, scan_id,
          'CI Scan' + (' - ' + ci_repo if ci_repo else ''),
          score,
          'A' if score >= 90 else 'B' if score >= 80 else 'C' if score >= 60 else 'D',
          scanner_result.get('total_issues', 0),
          scanner_result.get('file_count', 0),
          total_lines if 'total_lines' in dir() else 0,
          0,  # credits_spent (后续扣费后更新)
          'auto',
          issues_summary,
          files_meta,
          scan_mode,
          ci_repo, ci_branch, ci_commit_sha, share_token))
    db.commit()

    row = db.execute("SELECT id FROM scans WHERE scan_id = ?", (scan_id,)).fetchone()
    return (row[0] if row else None), share_token


# ============================================================
# API 路由
# ============================================================


# ========== GitHub 仓库扫描 ==========

_GITHUB_URL_RE = re.compile(
    r'^https?://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?(?:/tree/([^/]+))?(?:/.*)?$'
)

def _parse_github_url(repo_url):
    """解析 GitHub 仓库 URL，返回 (owner, repo, branch_or_none)"""
    m = _GITHUB_URL_RE.match(repo_url.strip())
    if not m:
        return None
    return m.group(1), m.group(2), m.group(3)


def _collect_files_from_repo(clone_dir):
    """从已 clone 的目录中收集代码文件，返回 {相对路径: 文件内容}"""
    files = {}
    for root, dirs, filenames in os.walk(clone_dir):
        dirs[:] = [d for d in dirs if not any(
            skip.rstrip('/') in d or d == skip.rstrip('/')
            for skip in ARCHIVE_SKIP_DIRS
        )]
        for fname in filenames:
            fpath = os.path.join(root, fname)
            _, ext = os.path.splitext(fname)
            if ext.lower() not in CODE_EXTS:
                continue
            try:
                fsize = os.path.getsize(fpath)
                if fsize > MAX_SINGLE_FILE_KB * 1024 or fsize == 0:
                    continue
            except OSError:
                continue
            rel = os.path.relpath(fpath, clone_dir)
            try:
                with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                if content.strip():
                    files[rel] = content
            except Exception:
                continue
            if len(files) >= MAX_CODE_FILES:
                return files
    return files


@ci_bp.route('/api/scan/github', methods=['POST'])
def api_scan_github():
    """
    GitHub 仓库扫描 API
    接收 GitHub 公开仓库 URL，clone 后走标准扫描流程。
    支持 X-API-Key 或 Session 两种鉴权方式。
    """
    # ── 鉴权（支持 API Key 和 Session 两种方式）──
    api_key = request.headers.get('X-API-Key', '')
    user_id, key_name = _verify_ci_api_key(api_key)
    if not user_id:
        # 回退到 session 认证
        user = get_current_user()
        if user:
            user_id = user['id']
        else:
            return jsonify(status='error', error='invalid_api_key',
                           message='API Key 无效或未登录'), HTTP_UNAUTHORIZED

    # ── VIP 状态 ──
    db = get_db()
    user = db.execute(
        "SELECT is_vip, vip_expire_at FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    is_vip = False
    if user:
        is_vip = bool(user[0])
        if is_vip and user[1]:
            try:
                if datetime.strptime(user[1], '%Y-%m-%d %H:%M:%S') < datetime.now():
                    is_vip = False
            except (ValueError, TypeError):
                pass

    # ── 频率限制 ──
    allowed, retry_after = _check_rate_limit(user_id)
    if not allowed:
        return jsonify(status='error', error='rate_limited',
                       message='请求过于频繁，请稍后重试',
                       retry_after=retry_after), 429

    # ── 参数解析 ──
    data = request.get_json(silent=True) or {}
    repo_url = (data.get('repo_url') or '').strip()
    branch = (data.get('branch') or '').strip()
    scan_mode = (data.get('scan_mode') or '').strip()
    github_token = (data.get('github_token') or '').strip()

    if not repo_url:
        return jsonify(status='error', error='invalid_request',
                       message='缺少 repo_url 参数'), HTTP_BAD_REQUEST

    # ── 解析 GitHub URL ──
    parsed = _parse_github_url(repo_url)
    if not parsed:
        return jsonify(status='error', error='invalid_request',
                       message='无效的 GitHub 仓库 URL，请提供形如 https://github.com/user/repo 的地址'), HTTP_BAD_REQUEST
    owner, repo, url_branch = parsed
    branch = url_branch or branch

    # ── 确定扫描档位 ──
    scan_mode = _determine_scan_mode(user_id, scan_mode, is_vip)

    # ── Clone 仓库 ──
    clone_dir = tempfile.mkdtemp(prefix='xinpect_repo_')
    try:
        clone_url = f'https://github.com/{owner}/{repo}.git'
        if github_token:
            clone_url = f'https://{github_token}@github.com/{owner}/{repo}.git'

        cmd = ['git', 'clone', '--depth', '1']
        if branch:
            cmd.extend(['--branch', branch])
        cmd.extend(['--single-branch', clone_url, clone_dir])

        logger.info(f'[GitHub] Cloning {owner}/{repo} (branch={branch or "default"})')
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            err = result.stderr.strip()
            logger.warning(f'[GitHub] Clone failed: {err}')
            if 'not found' in err.lower() or '404' in err:
                return jsonify(status='error', error='repo_not_found',
                               message='仓库不存在或无权访问'), HTTP_NOT_FOUND
            if 'authentication' in err.lower() or '403' in err:
                return jsonify(status='error', error='auth_required',
                               message='私有仓库需要提供 GitHub Token'), HTTP_UNAUTHORIZED
            return jsonify(status='error', error='clone_failed',
                           message=f'克隆仓库失败: {err[:200]}'), HTTP_BAD_REQUEST

        # ── 收集代码文件 ──
        code_files = _collect_files_from_repo(clone_dir)
        if not code_files:
            return jsonify(status='error', error='no_valid_files',
                           message='仓库中未找到支持的代码文件'), HTTP_BAD_REQUEST

        # ── 获取 commit SHA ──
        ci_commit = ''
        try:
            r = subprocess.run(['git', '-C', clone_dir, 'rev-parse', 'HEAD'],
                               capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                ci_commit = r.stdout.strip()
        except Exception:
            pass

        ci_repo = f'{owner}/{repo}'
        ci_branch = branch or 'default'

        # ── 忽略模式过滤 ──
        ci_config = _get_ci_config(user_id)
        ignore_patterns = data.get('ignore_patterns') or ci_config.get('ignore_patterns', [])
        code_files, ignored_count = _filter_code_files(code_files, ignore_patterns)
        if not code_files:
            return jsonify(status='error', error='all_filtered',
                           message='所有文件被忽略模式过滤'), HTTP_BAD_REQUEST

        # ── 积分检查 ──
        total_lines = count_total_lines(code_files)
        credits_cost = 0
        if is_vip and scan_mode != 'free':
            credits_cost = calculate_scan_cost(total_lines, is_full_scan=True)
            balance = get_user_credits(user_id)
            if balance < credits_cost:
                return jsonify(status='error', error='credits_insufficient',
                               message='积分不足',
                               credits_needed=credits_cost, credits_balance=balance), HTTP_PAYMENT_REQUIRED

        # ── 调用扫描引擎 ──
        is_vip_engine = scan_mode in ('smart', 'deep')
        try:
            scanner_result = call_scanner(code_files, list(ALL_BRAIN_IDS if scan_mode in ('deep', 'full') else FREE_BRAIN_IDS), {
                'scan_mode': scan_mode,
                'is_vip': is_vip_engine,
            })
        except ScanEngineError as e:
            logger.error(f'[GitHub] Scan engine error: {e}')
            return jsonify(status='error', error='scan_failed',
                           message=f'扫描失败: {str(e)}'), HTTP_INTERNAL_ERROR
        except Exception as e:
            logger.error(f'[GitHub] Scan unexpected: {e}', exc_info=True)
            return jsonify(status='error', error='scan_failed',
                           message='扫描服务异常，请稍后重试'), HTTP_INTERNAL_ERROR

        # ── 保存记录 ──
        raw_id = scanner_result.get('scan_id', '') or hashlib.md5(
            json.dumps(sorted(code_files.keys())).encode()).hexdigest()[:12]
        gh_scan_id = "gh_" + raw_id
        auto_share = ci_config.get('auto_share', False)
        record_id, share_token = _save_ci_scan(
            user_id, gh_scan_id, scanner_result, scan_mode,
            ci_repo, ci_branch, ci_commit,
            total_lines=total_lines, auto_share=auto_share)

        # ── 扣积分 ──
        if credits_cost > 0:
            ok = consume_credits(user_id, credits_cost,
                                ref_type='github_scan_pre', ref_id=gh_scan_id,
                                remark='GitHub仓库扫描: %d行, mode=%s' % (total_lines, scan_mode))
            if not ok:
                grant_credits(user_id, credits_cost,
                             ref_type='github_scan_refund', ref_id=gh_scan_id,
                             remark='GitHub扫描退款')
                return jsonify(status='error', error='credits_failed',
                               message='积分扣费失败'), HTTP_PAYMENT_REQUIRED

        # ── 构造响应 ──
        score = _calc_score_from_result(scanner_result)
        issues = scanner_result.get('issues', [])
        issue_counts = _count_issues_by_severity(issues)
        threshold = data.get('threshold', ci_config.get('default_threshold', 60))
        new_balance = get_user_credits(user_id) if credits_cost > 0 else None
        base_url = 'https://xinpect.xingwangzhineng.com'

        resp = {
            'status': 'ok',
            'scan_id': gh_scan_id,
            'score': score,
            'passed': score >= threshold,
            'issues': {
                'total': len(issues),
                'critical': issue_counts['critical'],
                'warning': issue_counts['warning'],
                'info': issue_counts['info'],
            },
            'scan_mode': scan_mode,
            'report_url': base_url + '/report/' + gh_scan_id,
            'badge_markdown': '[![煋鉴评分](%s/api/badge/%s.svg)](%s/report/%s)' % (base_url, gh_scan_id, base_url, gh_scan_id),
            'elapsed': round(scanner_result.get('scan_time', 0), 2),
            'file_count': scanner_result.get('file_count', 0),
            'ignored_count': ignored_count,
            'repo': ci_repo,
            'branch': ci_branch,
            'commit': ci_commit,
        }
        if new_balance is not None:
            resp['credits_used'] = credits_cost
            resp['credits_balance'] = new_balance
        if share_token:
            resp['share_url'] = base_url + '/report/share/' + share_token

        logger.info(f'[GitHub] Scan complete: {gh_scan_id}, {ci_repo}, {scanner_result.get("file_count", 0)} files, score={score}, {len(issues)} issues')
        return jsonify(resp), HTTP_OK

    except subprocess.TimeoutExpired:
        logger.error(f'[GitHub] Clone timeout for {owner}/{repo}')
        return jsonify(status='error', error='clone_timeout',
                       message='克隆仓库超时，请稍后重试'), HTTP_INTERNAL_ERROR
    except Exception as e:
        logger.exception(f'[GitHub] Unexpected error: {e}')
        return jsonify(status='error', error='unexpected_error',
                       message='扫描服务异常，请稍后重试'), HTTP_INTERNAL_ERROR
    finally:
        try:
            shutil.rmtree(clone_dir, ignore_errors=True)
        except Exception:
            pass


@ci_bp.route('/api/ci/scan', methods=['POST'])
@csrf_required
def api_ci_scan():
    """CI/CD 扫描入口"""
    # 1. 鉴权
    api_key = request.headers.get('X-API-Key', '')
    user_id, key_name = _verify_ci_api_key(api_key)
    if not user_id:
        return jsonify(status='error', error='invalid_api_key',
                       message='API Key 无效或已停用'), HTTP_UNAUTHORIZED

    # 2. VIP 状态
    db = get_db()
    user = db.execute(
        "SELECT is_vip, vip_expire_at FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    is_vip = False
    if user:
        is_vip = bool(user[0])
        if is_vip and user[1]:
            try:
                if datetime.strptime(user[1], '%Y-%m-%d %H:%M:%S') < datetime.now():
                    is_vip = False
            except (ValueError, TypeError):
                pass

    # 3. 频率限制
    allowed, retry_after = _check_rate_limit(user_id)
    if not allowed:
        return jsonify(status='error', error='rate_limited',
                       message='请求过于频繁，请稍后重试',
                       retry_after=retry_after), 429

    # 4. 确定扫描档位
    data = request.get_json(silent=True) or {}
    scan_mode = _determine_scan_mode(user_id, data.get('scan_mode', ''), is_vip)

    # 5. 文件校验
    code_files = data.get('code_files', {})
    if not code_files or not isinstance(code_files, dict):
        return jsonify(status='error', error='invalid_request',
                       message='code_files 不能为空'), HTTP_BAD_REQUEST
    if len(code_files) > MAX_CODE_FILES:
        return jsonify(status='error', error='too_many_files',
                       message='单次最多 %d 个文件' % MAX_CODE_FILES), HTTP_ENTITY_TOO_LARGE

    max_bytes = MAX_SINGLE_FILE_KB * 1024
    valid_files = {p: c for p, c in code_files.items()
                   if isinstance(c, str) and len(c.encode('utf-8', errors='replace')) <= max_bytes}
    if not valid_files:
        return jsonify(status='error', error='no_valid_files',
                       message='没有有效的代码文件'), HTTP_BAD_REQUEST

    # 忽略模式
    ci_config = _get_ci_config(user_id)
    ignore_patterns = data.get('ignore_patterns') or ci_config.get('ignore_patterns', [])
    valid_files, ignored_count = _filter_code_files(valid_files, ignore_patterns)
    if not valid_files:
        return jsonify(status='error', error='all_filtered',
                       message='所有文件被忽略模式过滤'), HTTP_BAD_REQUEST

    # 6. 积分检查
    total_lines = count_total_lines(valid_files)
    credits_cost = 0
    if is_vip and scan_mode != 'free':
        credits_cost = calculate_scan_cost(total_lines, is_full_scan=True)
        balance = get_user_credits(user_id)
        if balance < credits_cost:
            return jsonify(status='error', error='credits_insufficient',
                           message='积分不足，需 %d 积分，余额 %d' % (credits_cost, balance),
                           credits_needed=credits_cost, credits_balance=balance), HTTP_PAYMENT_REQUIRED

    # 7. 调用扫描引擎
    is_vip_engine = scan_mode in ('smart', 'deep')
    try:
        scanner_result = call_scanner(valid_files, ['1','2','3','4','5','6','7'], {
            'scan_mode': scan_mode,
            'is_vip': is_vip_engine,
        })
    except ScanEngineError as e:
        logger.error("CI scan engine error: user=%d mode=%s err=%s", user_id, scan_mode, e)
        return jsonify(status='error', error='scan_failed',
                       message='扫描失败: %s' % str(e)), HTTP_INTERNAL_ERROR
    except Exception as e:
        logger.error("CI scan unexpected: user=%d err=%s", user_id, e, exc_info=True)
        return jsonify(status='error', error='scan_failed',
                       message='扫描服务异常，请稍后重试'), HTTP_INTERNAL_ERROR

    # 8. 保存记录
    raw_id = scanner_result.get('scan_id', '') or hashlib.md5(
        json.dumps(sorted(valid_files.keys())).encode()).hexdigest()[:12]
    ci_scan_id = "ci_" + raw_id
    auto_share = ci_config.get('auto_share', False)
    record_id, share_token = _save_ci_scan(
        user_id, ci_scan_id, scanner_result, scan_mode,
        data.get('repo'), data.get('branch'), data.get('commit_sha'),
        total_lines=total_lines, auto_share=auto_share)

    # 9. 扣积分
    if credits_cost > 0:
        ok = consume_credits(user_id, credits_cost,
                            ref_type='ci_scan_pre', ref_id=ci_scan_id,
                            remark='CI扫描: %d行, mode=%s' % (total_lines, scan_mode))
        if not ok:
            grant_credits(user_id, credits_cost,
                         ref_type='ci_scan_refund', ref_id=ci_scan_id,
                         remark='CI扫描退款')
            return jsonify(status='error', error='credits_failed',
                           message='积分扣费失败'), HTTP_PAYMENT_REQUIRED

    # 10. 响应
    score = _calc_score_from_result(scanner_result)
    issues = scanner_result.get('issues', [])
    issue_counts = _count_issues_by_severity(issues)
    threshold = data.get('threshold', ci_config.get('default_threshold', 60))
    new_balance = get_user_credits(user_id) if credits_cost > 0 else None
    base_url = 'https://xinpect.xingwangzhineng.com'

    resp = {
        'status': 'ok',
        'scan_id': ci_scan_id,
        'score': score,
        'passed': score >= threshold,
        'issues': {
            'total': len(issues),
            'critical': issue_counts['critical'],
            'warning': issue_counts['warning'],
            'info': issue_counts['info'],
        },
        'scan_mode': scan_mode,
        'report_url': base_url + '/report/' + ci_scan_id,
        'badge_markdown': '[![煋鉴评分](%s/api/badge/%s.svg)](%s/report/%s)' % (base_url, ci_scan_id, base_url, ci_scan_id),
        'elapsed': round(scanner_result.get('scan_time', 0), 2),
        'file_count': scanner_result.get('file_count', 0),
        'ignored_count': ignored_count,
    }
    if new_balance is not None:
        resp['credits_used'] = credits_cost
        resp['credits_balance'] = new_balance
    if share_token:
        resp['share_url'] = base_url + '/report/share/' + share_token

    return jsonify(resp), HTTP_OK


@ci_bp.route('/api/ci/config', methods=['GET'])
def api_ci_config_get():
    """获取用户 CI 配置"""
    api_key = request.headers.get('X-API-Key', '')
    user_id, key_name = _verify_ci_api_key(api_key)
    if not user_id:
        return jsonify(status='error', error='invalid_api_key',
                       message='API Key 无效或已停用'), HTTP_UNAUTHORIZED
    db = get_db()
    user = db.execute("SELECT is_vip, vip_expire_at FROM users WHERE id = ?", (user_id,)).fetchone()
    is_vip = False
    vip_expire = None
    if user:
        is_vip = bool(user[0])
        vip_expire = user[1]
    config = _get_ci_config(user_id)
    balance = get_user_credits(user_id) if is_vip else 0
    return jsonify(
        user_id=user_id, is_vip=is_vip, vip_expire_at=vip_expire,
        default_scan_mode=config['default_scan_mode'],
        default_threshold=config['default_threshold'],
        ignore_patterns=config['ignore_patterns'],
        auto_share=config['auto_share'],
        credits_balance=balance, api_key_name=key_name,
        allowed_scan_modes=['free','quick','smart','deep'] if is_vip else ['free'],
    )


@ci_bp.route('/api/ci/config', methods=['POST'])
@csrf_required
def api_ci_config_update():
    """更新用户 CI 配置"""
    api_key = request.headers.get('X-API-Key', '')
    user_id, _ = _verify_ci_api_key(api_key)
    if not user_id:
        return jsonify(status='error', error='invalid_api_key'), HTTP_UNAUTHORIZED
    data = request.get_json(silent=True) or {}
    db = get_db()
    existing = db.execute("SELECT id FROM ci_configs WHERE user_id = ?", (user_id,)).fetchone()
    mode = data.get('default_scan_mode', 'quick')
    if mode not in ('free', 'quick', 'smart', 'deep'):
        mode = 'quick'
    threshold = max(0, min(100, int(data.get('default_threshold', 60))))
    ignore_pats = json.dumps(data.get('ignore_patterns', []))
    auto_share = 1 if data.get('auto_share') else 0
    if existing:
        db.execute("""UPDATE ci_configs SET default_scan_mode=?, default_threshold=?,
            ignore_patterns=?, auto_share=?, updated_at=datetime('now','localtime')
            WHERE user_id=?""", (mode, threshold, ignore_pats, auto_share, user_id))
    else:
        db.execute("""INSERT INTO ci_configs (user_id, default_scan_mode, default_threshold, ignore_patterns, auto_share)
            VALUES (?, ?, ?, ?, ?)""", (user_id, mode, threshold, ignore_pats, auto_share))
    db.commit()
    return jsonify(status='ok', message='配置已保存')


@ci_bp.route('/api/ci/scan/<scan_id>', methods=['GET'])
def api_ci_scan_result(scan_id):
    """查询CI扫描结果"""
    # 支持API Key或Session认证
    api_key = request.headers.get('X-API-Key', '')
    if api_key:
        user_id, _ = _verify_ci_api_key(api_key)
        if not user_id:
            return jsonify(status='error', error='invalid_api_key'), HTTP_UNAUTHORIZED
    else:
        from flask import session as flask_session
        user_id = flask_session.get('user_id')
        if not user_id:
            return jsonify(status='error', error='未登录'), HTTP_UNAUTHORIZED
    
    # 查询扫描记录
    db = get_db()
    row = db.execute("SELECT scan_id, user_id, score, grade, issue_count, file_count, total_lines, scan_mode, results, created_at FROM scans WHERE scan_id = ? AND user_id = ?", (scan_id, user_id)).fetchone()
    
    if not row:
        return jsonify(status='error', error='not_found', message='扫描记录不存在'), HTTP_NOT_FOUND
    
    # 解析结果
    try:
        results = json.loads(row[8]) if row[8] else {}
    except:
        results = {}
    
    return jsonify(
        status='ok',
        scan_id=row[0],
        user_id=row[1],
        score=row[2],
        grade=row[3],
        issue_count=row[4],
        file_count=row[5],
        total_lines=row[6],
        scan_mode=row[7],
        results=results,
        created_at=row[9],
    )



# ============================================================
# 分享报告
# ============================================================

@ci_bp.route('/api/scan/<scan_id>/share', methods=['POST'])
@csrf_required
def api_create_share(scan_id):
    """分享扫描报告（支持 session 登录和 API Key 两种认证）"""
    db = get_db()
    user = get_current_user()
    if not user:
        api_key = request.headers.get('X-API-Key', '')
        if api_key:
            key_record = db.execute(
                "SELECT user_id FROM api_keys WHERE api_key = ? AND is_active = 1",
                (api_key,)).fetchone()
            if key_record:
                user = {'id': key_record[0]}
    if not user:
        return jsonify(status='error', message='未认证'), 401
    scan = db.execute("SELECT id, user_id FROM scans WHERE scan_id = ?", (scan_id,)).fetchone()
    if not scan or scan[1] != user['id']:
        return jsonify(status='error', message='扫描记录不存在'), HTTP_NOT_FOUND
    token = secrets.token_urlsafe(12)
    db.execute("UPDATE scans SET share_token = ? WHERE scan_id = ?", (token, scan_id))
    db.commit()
    return jsonify(status='ok', share_token=token,
                   share_url='https://xinpect.xingwangzhineng.com/report/share/' + token)


@ci_bp.route('/report/share/<share_token>')
def report_share_page(share_token):
    """公开分享报告页面（无需登录）"""
    db = get_db()
    scan = db.execute(
        "SELECT scan_id, user_id, score, grade, issue_count, file_count, "
        "total_lines, scan_mode, source, ci_repo, ci_branch, ci_commit_sha, "
        "results, files_meta, created_at, language "
        "FROM scans WHERE share_token = ?",
        (share_token,)).fetchone()
    if not scan:
        return render_template('404.html'), HTTP_NOT_FOUND

    import json as _json
    scan_id, user_id, score, grade, issue_count, file_count,     total_lines, scan_mode, source, ci_repo, ci_branch, ci_commit_sha,     results_json, files_meta_json, created_at, language = scan

    try:
        results_data = _json.loads(results_json) if results_json else {}
    except Exception:
        results_data = {}
    try:
        files_meta = _json.loads(files_meta_json) if files_meta_json else {}
    except Exception:
        files_meta = {}

    # 从 results_data 中提取 issues
    if isinstance(results_data, dict):
        issues = results_data.get('issues', [])
    elif isinstance(results_data, list):
        issues = results_data
    else:
        issues = []

    # 抽样预览：按引擎层级分组
    is_paid_scan = scan_mode in ('smart', 'deep', 'full')
    if is_paid_scan:
        # 付费扫描：全部展示，不锁定
        basic_issues = issues
        deep_issues = []
    else:
        # 免费扫描：按 brain_id 分为基础/深度两组
        basic_issues = []
        deep_issues = []
        for issue in issues:
            if issue.get('brain_id') in BASIC_BRAIN_IDS:
                basic_issues.append(issue)
            elif issue.get('brain_id') in DEEP_BRAIN_IDS:
                deep_issues.append(issue)
            else:
                # 未知引擎 → 兜底归入基础
                basic_issues.append(issue)

    # 基础 issues 按严重度分类（用于完整展示区）
    critical = [i for i in basic_issues if str(i.get('severity','')).lower() in ('critical','error','fatal','blocker')]
    warning = [i for i in basic_issues if str(i.get('severity','')).lower() in ('warning','major','high','medium')]
    info = [i for i in basic_issues if i not in critical and i not in warning]

    # 深度 issues 按严重度分类（用于锁定预览区）
    deep_critical = [i for i in deep_issues if str(i.get('severity','')).lower() in ('critical','error','fatal','blocker')]
    deep_warning = [i for i in deep_issues if str(i.get('severity','')).lower() in ('warning','major','high','medium')]
    deep_info = [i for i in deep_issues if i not in deep_critical and i not in deep_warning]

    return render_template('report_shared.html',
        scan_id=scan_id, score=score, grade=grade,
        issue_count=issue_count, file_count=file_count,
        total_lines=total_lines, scan_mode=scan_mode,
        source=source or 'web', ci_repo=ci_repo, ci_branch=ci_branch,
        ci_commit_sha=ci_commit_sha, created_at=created_at, language=language,
        critical=critical, warning=warning, info=info,
        issues=basic_issues, files_meta=files_meta,
        is_paid_scan=is_paid_scan,
        deep_issues=deep_issues,
        deep_critical=deep_critical, deep_warning=deep_warning, deep_info=deep_info,
    )


@ci_bp.route('/api/scan/<scan_id>/unshare', methods=['POST'])
@csrf_required
def api_remove_share(scan_id):
    """取消分享扫描报告（支持 session 登录和 API Key 两种认证）"""
    db = get_db()
    user = get_current_user()
    if not user:
        api_key = request.headers.get('X-API-Key', '')
        if api_key:
            key_record = db.execute(
                "SELECT user_id FROM api_keys WHERE api_key = ? AND is_active = 1",
                (api_key,)).fetchone()
            if key_record:
                user = {'id': key_record[0]}
    if not user:
        return jsonify(status='error', message='未认证'), 401
    scan = db.execute("SELECT id, user_id FROM scans WHERE scan_id = ?", (scan_id,)).fetchone()
    if not scan or scan[1] != user['id']:
        return jsonify(status='error', message='扫描记录不存在'), HTTP_NOT_FOUND
    db.execute("UPDATE scans SET share_token = NULL WHERE scan_id = ?", (scan_id,))
    db.commit()
    return jsonify(status='ok', message='分享已取消')


# ============================================================
# 徽章 SVG
# ============================================================

def _build_badge_svg(score):
    if score >= 80:
        color = '#4c1'
        label = '优秀'
    elif score >= 60:
        color = '#FF6B35'
        label = '良好'
    else:
        color = '#e05d44'
        label = '需改进'
    score_text = '%d %s' % (score, label)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="186" height="20" role="img">'
        '<title>煋鉴评分: ' + score_text + '</title>'
        '<linearGradient id="s" x2="0" y2="100%">'
        '<stop offset="0" stop-color="#bbb" stop-opacity=".1"/>'
        '<stop offset="1" stop-opacity=".1"/>'
        '</linearGradient>'
        '<clipPath id="r"><rect width="186" height="20" rx="3" fill="#fff"/></clipPath>'
        '<g clip-path="url(#r)">'
        '<rect width="106" height="20" fill="#555"/>'
        '<rect x="106" width="80" height="20" fill="' + color + '"/>'
        '<rect width="186" height="20" fill="url(#s)"/>'
        '</g>'
        '<g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">'
        '<text x="53" y="14">煋鉴评分</text>'
        '<text x="146" y="14">' + score_text + '</text>'
        '</g></svg>'
    )


@ci_bp.route('/api/badge/<scan_id>.svg')
def badge_svg(scan_id):
    db = get_db()
    scan = db.execute("SELECT score FROM scans WHERE scan_id = ?", (scan_id,)).fetchone()
    if not scan:
        svg = _build_badge_svg(0)
    else:
        svg = _build_badge_svg(scan[0] or 0)
    resp = make_response(svg)
    resp.headers['Content-Type'] = 'image/svg+xml'
    resp.headers['Cache-Control'] = 'public, max-age=%d' % BADGE_CACHE_SECONDS
    return resp


# ============================================================
# Dashboard CI 配置页面
# ============================================================

@ci_bp.route('/dashboard/ci-setup')
@login_required
def ci_setup_page():
    """CI/CD 配置管理页面"""
    user = get_current_user()
    db = get_db()
    config = _get_ci_config(user['id'])
    balance = get_user_credits(user['id'])

    # 获取 API Keys
    api_keys = db.execute(
        "SELECT api_key, name, is_active, last_used, usage_count "
        "FROM api_keys WHERE user_id = ? ORDER BY created_at DESC",
        (user['id'],)
    ).fetchall()

    return render_template('dashboard/ci_setup.html',
        user_email=user.get('email', ''),
        is_vip=bool(user.get('is_vip', False)),
        config=config,
        balance=balance,
        api_keys=api_keys,
    )
