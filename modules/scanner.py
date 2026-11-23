"""Xinpect - Scanner integration (real engine only, no fallback)

产品诚信底线：宁可报错也不允许假结果。
扫描引擎不可达时，直接抛出异常，绝不允许 fallback。
"""

from .constants import (
    app, logger,
    BRAINS_MAP, TIERS, TIERS_MAP,
    FREE_BRAIN_IDS, ALL_BRAIN_IDS, brain_label,
    SCANNER_URL, SCANNER_API_KEY, SCAN_TIMEOUT_SECONDS,
)
import re as _re
import time as _time

from .helpers import _safe_http_post
from .scoring import severity_label
from .dimensions import engine_status as _engine_status

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
        resp = _requests.get(health_url, timeout=5, headers={"X-API-Key": SCANNER_API_KEY} if SCANNER_API_KEY else {})
        if resp.status_code != 200:
            logger.error("扫描引擎不可达 (HTTP %s)，服务启动失败", resp.status_code)
            raise SystemExit(1)
        data = resp.json()
        version = data.get('version', 'unknown')
        # 注意：此处是读取扫描器 /health 的【出参】字段 brain_ids；
        # 调用 /scan 时的【入参】字段是 brains（见 _build_scanner_payload），两者不可混改。
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
        'brains': brain_ids,
        'scan_mode': scan_mode,
        'is_vip': is_vip,
        'ai_enhance': is_vip,
        'fix_suggestions': True,
    }
    if thresholds:
        payload['thresholds'] = thresholds
    return payload


_ENGINE_PREFIX = _re.compile(r'^E(\d{1,2})-')
_BRAIN_ID_SET = {str(b) for b in ALL_BRAIN_IDS}


def _dimension_brain(bid, rule_id, category=None):
    """这条问题该显示在哪个引擎维度下 —— 先看查的是什么，再看得懂编号。

    为什么需要这一步（2026-11-04 实测）：

    引擎的 `engine/e1_syntax/checks/security/` 下有 176 个安全规则文件，
    它们由 E1 引擎执行，产出时 brain_id 被写成 1。但规则编号是 E2-*
    （E2 = 安全引擎，见 docs/rule_id_ledger.md 的编号铁律）。

    后果很具体：一份含硬编码密钥 + IDOR + SQL 注入的代码，三条全是
    high，全部挂在「E1 语法与AST分析」卡下，而「E2 安全检测」卡 0 条问题
    → 显示 100 分。这就是「安全 100 分，却有 1 条越权高危」的完整形态，
    比归错 category 更直接：报告页的维度卡就是按 brain_id 分的。

    ── 第二层（2026-11-05）：编号本身也会错 ──
    只认编号还不够。实测 828 条已注册规则里，有 **53 条 category=security
    的规则被编成了非 E2 的号**（48 条 E3-*，比如 E3-TAINT-PY-001 是 SQL 注入、
    E3-PERF-RUBY-XSS-001 是 XSS，另有 1 条 E1-*、4 条无引擎前缀）。
    按编号走，它们会落进「性能与可靠性」卡，安全卡一栏照样 100 分——
    用户看到的就是同一个病：**有注入高危，安全维度满分**。

    所以归属判据按可靠性排序：
      ① `category == 'security'` → 安全卡。安全是「风险维度」，不是「哪个引擎
         干的活」。一条 SQL 注入不管由谁执行、编号写成什么，它就是安全问题。
      ② 编号首段 `E<n>` 指向真实引擎 → 该引擎。
      ③ 都没有 → 引擎实际归属。
    ②③ 保持不变，是为了不推翻已对账过的 300 条真实 check_id 的归属。
    """
    if str(category or '').strip().lower() == 'security':
        return '2'
    m = _ENGINE_PREFIX.match(str(rule_id or '').strip().upper())
    if not m:
        return str(bid)
    num = m.group(1).lstrip('0') or '0'
    return num if num in _BRAIN_ID_SET else str(bid)


def _flatten_brain_results(raw_results, brain_ids, files_dict):
    """将按 brain 分组的扫描结果拍平为统一 issues 列表
    返回 (all_issues, style_issues, profile_items) 三元组

    profile_items = 技术栈/依赖画像（扫描器的 profile_items 通道）。
    它们是「这个项目用了哪些库 / API」，不是缺陷：不进 issues、不计分。
    """
    all_issues = []
    style_issues = []
    profile_items = []
    results_by_brain = raw_results.get('results', {})

    # 当 brain_ids 为 None 时（免费用户），从返回结果的 keys 推断
    if brain_ids is None:
        brain_ids = list(results_by_brain.keys())

    for bid in brain_ids:
        brain_result = results_by_brain.get(str(bid), {})
        brain_issues = brain_result.get('issues', [])
        # P0: 提取 style 问题
        brain_style = brain_result.get('style_issues', [])
        # 2026-11-03: 提取依赖画像（「用了哪些库/API」，不是缺陷）
        brain_profile = brain_result.get('profile_items', [])
        brain_name = brain_label(bid)

        for issue in brain_issues:
            file_path = issue.get('file', '')
            line_num = issue.get('line', 0)
            file_content = files_dict.get(file_path, '')
            code_snippet = _extract_code_snippet(file_content, line_num)

            # 归属以规则编号为准：E2-* 的问题是安全引擎的规则，即使由 E1 执行，
            # 也要显示在安全卡下（详见 _dimension_brain 的说明）
            _rule_id = issue.get('check_id', '')
            _dim_bid = _dimension_brain(bid, _rule_id, issue.get('category'))
            all_issues.append({
                'brain_id': _dim_bid,
                'brain_name': brain_label(_dim_bid),
                'rule_id': _rule_id,
                'title': issue.get('name', _rule_id),
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
            _rule_id = issue.get('check_id', '')
            _dim_bid = _dimension_brain(bid, _rule_id, issue.get('category'))
            style_issues.append({
                'brain_id': _dim_bid,
                'brain_name': brain_label(_dim_bid),
                'rule_id': _rule_id,
                'title': issue.get('name', _rule_id),
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

        # 2026-11-03: 处理依赖画像条目（技术栈清单，不参与评分）
        for issue in brain_profile:
            profile_items.append({
                'brain_id': str(bid),
                'brain_name': brain_name,
                'rule_id': issue.get('check_id', ''),
                'title': issue.get('name', issue.get('check_id', '')),
                'description': issue.get('message', ''),
                'file': issue.get('file', ''),
                'line': issue.get('line', 0),
            })

    return all_issues, style_issues, profile_items


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


# ============================================================
# 被抑制清单（suppressed_issues）
# ============================================================
# 扫描器的 AI 降噪（B13）会把判定为误报的问题从报告里删掉。删之前它留了
# 「凭条」，写在 results.ai_denoise.suppressed_issues / suppressed_stats。
# 这两个字段不进 issues、不计分，唯一用途是回答「这条明明有问题，为什么没报」。
#
# 落库体积约束：清单可能上千条，而 scans.results 是整包 JSON 存库。
# 与 issues 一样需要封顶，超出部分只保留计数（stats.total 仍是真实总数）。
SUPPRESSED_STORE_LIMIT = 500

# 只搬运报告页要显示的字段，不整条透传（防止内部临时字段漏出去、也防体积膨胀）
_SUPPRESSED_FIELDS = ('stage', 'stage_label', 'reason', 'engine',
                      'file', 'line', 'check_id', 'title', 'confidence')


def _slim_suppressed_record(rec):
    """把扫描器的一条抑制记录压成白名单字段。非 dict 直接丢。"""
    if not isinstance(rec, dict):
        return None
    out = {}
    for key in _SUPPRESSED_FIELDS:
        out[key] = rec.get(key)
    # 归一化：字符串字段保证是字符串，行号保证是整数（前端直接拼"文件:行"）
    for key in ('stage', 'stage_label', 'reason', 'engine', 'file', 'check_id', 'title'):
        if out[key] is None:
            out[key] = ''
        elif not isinstance(out[key], str):
            out[key] = str(out[key])
    try:
        out['line'] = int(out['line'] or 0)
    except (TypeError, ValueError):
        out['line'] = 0
    # 置信度统一成 0~1 的浮点或 None：模板要按 %.2f 展示，字符串会让它炸
    conf = out.get('confidence')
    if conf is None:
        out['confidence'] = None
    else:
        try:
            out['confidence'] = round(float(conf), 4)
        except (TypeError, ValueError):
            out['confidence'] = None
    return out


def _collect_suppressed(raw_results):
    """提取被抑制清单，返回 (records, stats)。

    扫描器没跑降噪时（免费扫描 / quick 模式），results 里没有 ai_denoise，
    此时返回空列表——这与「跑了降噪、但没抑制任何条目」是两件事：
    报告页对前者的处理是整栏不显示，后者显示 0 条。
    """
    raw_results = raw_results if isinstance(raw_results, dict) else {}
    denoise = raw_results.get('ai_denoise')
    if not isinstance(denoise, dict):
        return [], {}

    raw_records = denoise.get('suppressed_issues')
    if not isinstance(raw_records, list):
        raw_records = []

    stats = denoise.get('suppressed_stats')
    if not isinstance(stats, dict):
        stats = {}

    records = [r for r in (_slim_suppressed_record(x) for x in raw_records) if r]
    truncated = bool(stats.get('truncated'))
    if len(records) > SUPPRESSED_STORE_LIMIT:
        records = records[:SUPPRESSED_STORE_LIMIT]
        truncated = True

    by_stage = stats.get('by_stage')
    if not isinstance(by_stage, dict):
        by_stage = {}
    try:
        total = int(stats.get('total'))
    except (TypeError, ValueError):
        total = len(raw_records)

    out_stats = {
        'total': total,
        'returned': len(records),
        'truncated': truncated,
        'by_stage': {str(k): v for k, v in by_stage.items() if isinstance(v, int)},
    }
    return records, out_stats


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


# ============================================================
# 报告落库字段清单（单一事实来源）
# ============================================================
# call_scanner 的返回值里有「报告要展示的东西」，也有「只用于日志的中间量」。
# 落库的两条路径——网页扫描（modules/scan.py 整包存 results）与 CI
# （modules/ci.py::_save_ci_scan 逐字段组装）——必须对「哪些字段算报告内容」
# 有同一份认知。
#
# 2026-11-03 之前 CI 那边是手写字典白名单，于是每加一个报告栏目就静默丢一次字段：
# 被抑制清单丢过一次、样式问题丢过一次、依赖画像丢过一次，页面表现为「栏目不存在」
# 而不是报错，极难察觉。现在改成在这里声明一次，CI 侧按这张表派生落库内容，
# 新增栏目只改这一处；tests 里另有守卫断言「页面读取的字段 ⊆ 本表」。
#
# 表的值是该字段的默认值（缺失时用），类型同时充当校验依据。
REPORT_PAYLOAD_KEYS = {
    'issues': [],
    'style_issues': [],
    # 2026-11-04: 引擎台账（哪个 brain 跑了/报错/被降级）。
    # 不落库的话报告页拿不到，只能默认"都跑成了"，五维就会永远满分。
    'engines': {},
    # 与 engines 同一件事的另外两面：有文件没被解析 / 被截断，
    # 任何维度的 100 分在这两种情况下都不成立。只落 engines 不落这两个，
    # 报告页就只看得到"引擎跑了"，看不到"跑的是残文件"。
    'unsupported_files': [],
    'unsupported_count': 0,
    'trimmed_files': [],
    'trimmed_count': 0,
    'degraded_brains': [],
    'profile_items': [],
    'suppressed_issues': [],
    'suppressed_stats': {},
    'total_issues': 0,
    'version': '',
    'scan_time': 0,
}


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
    # X-02 fix: 传递user_id用于扫描结果归属
    user_id = options.get('user_id', '')
    if user_id:
        payload['user_id'] = user_id

    # P2-6: 传递用户禁用的规则
    if disabled_rules:
        payload['disabled_rules'] = disabled_rules

    # 2026-11-05：真实进度任务号。扫描器只在旁路登记「真的发生了什么」，
    # 这个字段不参与任何检测判定，也不写进 config（config 参与缓存键）。
    _progress_job_id = options.get('progress_job_id')
    if _progress_job_id:
        payload['progress_job_id'] = str(_progress_job_id)

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
            resp = _safe_http_post(SCANNER_URL, json=payload, timeout=dynamic_timeout, headers={"X-API-Key": SCANNER_API_KEY} if SCANNER_API_KEY else {})
            resp.raise_for_status()
            raw = resp.json()

            all_issues, style_issues, profile_items = _flatten_brain_results(raw, brain_ids, files_dict)
            _sort_issues_by_severity(all_issues)
            # 2026-11-03: 被抑制清单（AI 判为误报而没进报告的条目），供报告页回答「为什么没报」
            suppressed_issues, suppressed_stats = _collect_suppressed(raw.get('results'))
            if suppressed_stats:
                logger.info(
                    "被抑制清单: %d 条（抑制总数 %s，截断=%s）",
                    suppressed_stats['returned'], suppressed_stats['total'],
                    suppressed_stats['truncated']
                )

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

            # 2026-11-04 引擎台账：把「哪些引擎真的跑了」带上去。
            # 引擎其实一直在吐这些事实：results[brain]['error'] 记了执行失败，
            # degraded_brains 记了高负载时被主动跳过的重引擎，unsupported/trimmed
            # 记了没被解析的文件。但 call_scanner 是白名单组装——不在这里列出来，
            # 下游一个字都看不到。结果就是「引擎崩了」和「干净代码」在页面上
            # 都显示 100 分，用户以为查过了。
            _eng_status = _engine_status(
                raw.get('results'), brain_ids, raw.get('degraded_brains') or []
            )
            return {
                'brains': brain_ids,
                'engines': _eng_status,
                'degraded_brains': list(raw.get('degraded_brains') or []),
                'unsupported_files': list(raw.get('unsupported_files') or []),
                'unsupported_count': int(raw.get('unsupported_count') or 0),
                'trimmed_files': list(raw.get('trimmed_files') or []),
                'trimmed_count': int(raw.get('trimmed_count') or 0),
                'language': language,
                'issues': all_issues,
                'style_issues': style_issues,
                'style_count': len(style_issues),
                'profile_items': profile_items,
                'profile_count': len(profile_items),
                'suppressed_issues': suppressed_issues,
                'suppressed_stats': suppressed_stats,
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
