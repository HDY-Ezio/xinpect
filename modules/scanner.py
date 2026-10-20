"""Xinpect - Scanner integration (real engine only, no fallback)

产品诚信底线：宁可报错也不允许假结果。
扫描引擎不可达时，直接抛出异常，绝不允许 fallback。
"""

from .constants import (
    app, logger,
    BRAINS_MAP, TIERS, TIERS_MAP,
    FREE_BRAIN_IDS,
    SCANNER_URL, SCAN_TIMEOUT_SECONDS,
)
import time as _time

from .helpers import _safe_http_post
from .scoring import severity_label

# 重试配置
SCANNER_MAX_RETRIES = 3
SCANNER_RETRY_DELAYS = [1, 2, 4]  # 指数退避（秒）


# ============================================================
# 自定义异常
# ============================================================
class ScanEngineError(Exception):
    """扫描引擎不可用或返回错误（基类）"""
    pass


class ScanEngineTimeout(ScanEngineError):
    """扫描引擎超时"""
    pass


class ScanEngineUnreachable(ScanEngineError):
    """扫描引擎连接失败"""
    pass


def _extract_code_snippet(content_text, line_num, context_before=3, context_after=2):
    """Extract code snippet with line numbers and marker"""
    if not content_text or not line_num:
        return ""
    src_lines = content_text.split('\n')
    start = max(0, line_num - context_before)
    end = min(len(src_lines), line_num + context_after)
    snippet_lines = []
    for i in range(start, end):
        marker = "> " if i + 1 == line_num else "  "
        snippet_lines.append(f"{marker}{i+1:4d}: {src_lines[i]}")
    return '\n'.join(snippet_lines)


def verify_scanner_engine():
    """启动时验证扫描引擎可达性，不可达则拒绝启动"""
    import requests as _requests
    health_url = SCANNER_URL.replace('/scan', '/health')
    try:
        resp = _requests.get(health_url, timeout=5)
        if resp.status_code != 200:
            logger.error("扫描引擎不可达 (HTTP %s)，服务启动失败", resp.status_code)
            raise SystemExit(1)
        data = resp.json()
        version = data.get('version', 'unknown')
        brains = data.get('brain_ids', [])
        logger.info("扫描引擎连接正常 [version=%s, brains=%d]", version, len(brains))
        return True
    except SystemExit:
        raise
    except Exception as e:
        logger.error("扫描引擎连接失败: %s", e)
        raise SystemExit(1)


def _build_scanner_payload(files_dict, brain_ids, scan_mode, is_vip, thresholds=None):
    """构建扫描引擎请求参数"""
    payload = {
        'code_files': files_dict,
        'brain_ids': brain_ids,
        'scan_mode': scan_mode,
        'is_vip': is_vip,
        'ai_enhance': is_vip,
        'fix_suggestions': True,
    }
    if thresholds:
        payload['thresholds'] = thresholds
    return payload


def _flatten_brain_results(raw_results, brain_ids, files_dict):
    """将按 brain 分组的扫描结果拍平为统一 issues 列表
    返回 (all_issues, style_issues) 元组"""
    all_issues = []
    style_issues = []
    results_by_brain = raw_results.get('results', {})

    # 当 brain_ids 为 None 时（免费用户），从返回结果的 keys 推断
    if brain_ids is None:
        brain_ids = list(results_by_brain.keys())

    for bid in brain_ids:
        brain_result = results_by_brain.get(str(bid), {})
        brain_issues = brain_result.get('issues', [])
        # P0: 提取 style 问题
        brain_style = brain_result.get('style_issues', [])
        brain_name = BRAINS_MAP.get(str(bid), {}).get('name', f'B{bid}')

        for issue in brain_issues:
            file_path = issue.get('file', '')
            line_num = issue.get('line', 0)
            file_content = files_dict.get(file_path, '')
            code_snippet = _extract_code_snippet(file_content, line_num)

            all_issues.append({
                'brain_id': str(bid),
                'brain_name': brain_name,
                'rule_id': issue.get('check_id', ''),
                'title': issue.get('name', issue.get('check_id', '')),
                'severity': issue.get('severity', 'medium'),
                'severity_label': severity_label(issue.get('severity', 'medium')),
                'description': issue.get('message', ''),
                'suggestion': issue.get('suggestion', ''),
                'file': file_path,
                'line': line_num,
                'code_snippet': code_snippet,
                'category': issue.get('category', ''),
                'fix_summary': issue.get('fix_summary', ''),
                'fix_suggestion': issue.get('fix_suggestion', ''),
                'ai_source': issue.get('ai_source', 'rule'),
                'ai_confidence': issue.get('ai_confidence'),
                'ai_analysis': issue.get('ai_analysis', ''),
                'ai_fix_suggestion': issue.get('ai_fix_suggestion', ''),
                'ai_exploitability': issue.get('ai_exploitability', ''),
            })

        # P0: 处理 style 问题
        for issue in brain_style:
            file_path = issue.get('file', '')
            line_num = issue.get('line', 0)
            file_content = files_dict.get(file_path, '')
            code_snippet = _extract_code_snippet(file_content, line_num)
            style_issues.append({
                'brain_id': str(bid),
                'brain_name': brain_name,
                'rule_id': issue.get('check_id', ''),
                'title': issue.get('name', issue.get('check_id', '')),
                'severity': issue.get('severity', 'info'),
                'severity_label': '建议',
                'description': issue.get('message', ''),
                'suggestion': issue.get('suggestion', ''),
                'file': file_path,
                'line': line_num,
                'code_snippet': code_snippet,
                'category': issue.get('category', ''),
                'fix_summary': issue.get('fix_summary', ''),
                'fix_suggestion': issue.get('fix_suggestion', ''),
                'ai_source': issue.get('ai_source', 'rule'),
            })

    return all_issues, style_issues


def _sort_issues_by_severity(all_issues):
    """按严重程度排序 issues"""
    sev_order = {
        'blocker': -1, 'critical': 0, 'high': 1,
        'medium': 2, 'low': 3, 'info': 4,
    }
    all_issues.sort(key=lambda x: (
        sev_order.get(x.get('severity', ''), 99),
        str(x.get('brain_id', '')),
    ))


def _handle_scanner_exception(exc, files_dict, file_count, total_code_size):
    """统一处理扫描引擎异常，抛出对应的 ScanEngineError"""
    import traceback
    import requests as _requests

    if isinstance(exc, _requests.exceptions.Timeout):
        logger.error(
            "扫描引擎超时: url=%s, timeout=%ds, files=%d, code_size=%d bytes, error=%s",
            SCANNER_URL, SCAN_TIMEOUT_SECONDS, file_count, total_code_size, exc
        )
        logger.error(traceback.format_exc())
        raise ScanEngineTimeout(
            f"扫描引擎超时 (>{SCAN_TIMEOUT_SECONDS}秒)，引擎地址: {SCANNER_URL}，"
            f"请求文件数: {file_count}，代码大小: {total_code_size} bytes"
        ) from exc

    if isinstance(exc, _requests.exceptions.ConnectionError):
        logger.error(
            "扫描引擎连接失败: url=%s, files=%d, code_size=%d bytes, error=%s",
            SCANNER_URL, file_count, total_code_size, exc
        )
        logger.error(traceback.format_exc())
        raise ScanEngineUnreachable(
            f"扫描引擎不可达，引擎地址: {SCANNER_URL}，错误: {exc}"
        ) from exc

    if isinstance(exc, _requests.exceptions.HTTPError):
        status_code = exc.response.status_code if exc.response is not None else 'unknown'
        logger.error(
            "扫描引擎返回错误: url=%s, status=%s, files=%d, code_size=%d bytes, error=%s",
            SCANNER_URL, status_code, file_count, total_code_size, exc
        )
        logger.error(traceback.format_exc())
        raise ScanEngineError(
            f"扫描引擎返回错误 (HTTP {status_code})，引擎地址: {SCANNER_URL}"
        ) from exc

    logger.error(
        "扫描引擎未知错误: url=%s, files=%d, code_size=%d bytes, error=%s",
        SCANNER_URL, file_count, total_code_size, exc
    )
    logger.error(traceback.format_exc())
    raise ScanEngineError(f"扫描引擎调用失败: {exc}") from exc


def _is_retryable_error(exc):
    """判断异常是否可重试（连接失败、超时、5xx等瞬时错误）"""
    import requests as _requests
    if isinstance(exc, (_requests.exceptions.ConnectionError,
                        _requests.exceptions.Timeout)):
        return True
    if isinstance(exc, _requests.exceptions.HTTPError) and exc.response is not None:
        return exc.response.status_code >= 500
    return False


def call_scanner(files_dict, brain_ids, options=None):
    """
    调用 xinpect-scanner v5 检测服务（带重试机制）

    options: dict with keys: language, scan_mode, is_vip, thresholds
    失败时直接抛出 ScanEngineError，绝不 fallback 到假结果。
    重试策略：瞬时错误（连接失败/超时/5xx）最多重试3次，指数退避。
    """
    options = options or {}
    language = options.get('language', 'auto')
    scan_mode = options.get('scan_mode', 'full')
    is_vip = options.get('is_vip', False)
    thresholds = options.get('thresholds')

    total_code_size = sum(len(v) for v in files_dict.values() if isinstance(v, str))
    file_count = len(files_dict)

    logger.info(
        "调用扫描引擎: files=%d, code_size=%d bytes, brains=%s, mode=%s",
        file_count, total_code_size, brain_ids, scan_mode
    )

    disabled_rules = (options or {}).get('disabled_rules', [])
    
    payload = _build_scanner_payload(
        files_dict, brain_ids, scan_mode, is_vip, thresholds
    )
    # P2-6: 传递用户禁用的规则
    if disabled_rules:
        payload['disabled_rules'] = disabled_rules

    last_exc = None
    for attempt in range(SCANNER_MAX_RETRIES + 1):
        try:
            # 大项目耗时长是正常的，不应该因为耗时长就报错
            # 超时按代码体积+文件数动态计算：基础300秒 + 每文件5秒 + 每10KB代码10秒
            size_kb = total_code_size / 1024
            dynamic_timeout = max(300, 300 + file_count * 5 + int(size_kb) * 1)
            dynamic_timeout = min(dynamic_timeout, 900)  # 上限15分钟，防止极端情况
            logger.info("扫描超时设置: %ds (files=%d, size=%.1fKB, code_size=%d bytes)", dynamic_timeout, file_count, size_kb, total_code_size)
            logger.info("扫描超时设置: %ds (files=%d, code_size=%d bytes)", dynamic_timeout, file_count, total_code_size)
            resp = _safe_http_post(SCANNER_URL, json=payload, timeout=dynamic_timeout)
            resp.raise_for_status()
            raw = resp.json()

            all_issues, style_issues = _flatten_brain_results(raw, brain_ids, files_dict)
            _sort_issues_by_severity(all_issues)

            if attempt > 0:
                logger.info(
                    "扫描引擎第%d次重试成功: issues=%d, elapsed=%.2fs",
                    attempt, len(all_issues), raw.get('total_elapsed', 0)
                )
            else:
                logger.info(
                    "扫描完成: issues=%d, elapsed=%.2fs, version=%s",
                    len(all_issues), raw.get('total_elapsed', 0), raw.get('version', '?')
                )

            return {
                'brains': brain_ids,
                'language': language,
                'issues': all_issues,
                'style_issues': style_issues,
                'style_count': len(style_issues),
                'file_count': len(files_dict),
                'total_issues': len(all_issues),
                'scan_time': raw.get('total_elapsed', 0),
                'version': raw.get('version', '5.0'),
                'ai_stats': raw.get('ai_stats', {}),
                'ai_elapsed': raw.get('ai_elapsed', 0),
                'fix_suggestion_stats': raw.get('fix_suggestion_stats', {}),
                'scan_id': raw.get('scan_id', ''),
            }
        except ScanEngineError:
            raise
        except Exception as exc:
            last_exc = exc
            if attempt < SCANNER_MAX_RETRIES and _is_retryable_error(exc):
                delay = SCANNER_RETRY_DELAYS[min(attempt, len(SCANNER_RETRY_DELAYS) - 1)]
                logger.warning(
                    "扫描引擎瞬时错误(第%d次)，%ds后重试: %s",
                    attempt + 1, delay, exc
                )
                _time.sleep(delay)
                continue
            _handle_scanner_exception(exc, files_dict, file_count, total_code_size)

    # 所有重试均失败
    _handle_scanner_exception(last_exc, files_dict, file_count, total_code_size)
