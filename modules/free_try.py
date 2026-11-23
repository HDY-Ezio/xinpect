# -*- coding: utf-8 -*-
"""
免费试扫蓝图 —— 零门槛获客入口。

背景（2026-10-28）：竞品对标发现「无零门槛免费入口」是获客死结——
当前未登录用户访问 /upload 直接 401，还没看到任何价值就被挡在门外。
Snyk 的 freemium 打法：只要有代码，5 分钟看到价值。

设计（只治本、不碰付费核心）：
1. 独立 /try 路由，免登录，用户粘贴代码即可扫一次。
2. 每个访客每天限 3 次 + 全站每天 300 次天花板，防匿名通道白嫖无限扫。
3. 结果「摘要化」：只给检出几类问题、严重度分布、前若干条高危标题，
   不给完整 issue 详情 / 行号 / 修复建议——想看到全部，引导注册。
4. 复用现有 call_scanner（走 SCANNER_URL + SCANNER_API_KEY），
   不绕过积分体系（试扫不入库、不占用会员额度、不产生可追溯报告）。

## 为什么不用 IP 限流（2026-11-04 改）

原来按 `X-Forwarded-For` 的第一节限流，两个方向都不对：

- 取第一节 = 客户端自己写的那段，改个请求头就是无限额度（实测可行）。
- 取最后一节 = nginx 追加的 `$remote_addr`，而 443 前面挡着 sslh 1.22
  （纯 TCP 转发，不支持 PROXY protocol），这一跳恒为 127.0.0.1。
  实测整张 visitor_events 表里所有访客的 ip 都是 127.0.0.1 —— 也就是
  **全站所有人共用了一个「3 次」的桶，第 4 个人开始就是 429**。

也就是说，这个拓扑下「真实客户端 IP」从来没有到达过应用层，怎么取都不对。
所以改成用服务端签发的访客 id（cookie `xp_vid`）记账，额度直接数
`try.ok` 事件（已落库的事实，跨重启都准）；成本兜底另外加全站日上限。

顺带修掉一个真实误伤：按 IP 限 3 次，公司/学校/网吧共用一个出口的人
会被集体判超限——这些人本来就是最可能注册的用户。
"""

from flask import Blueprint, render_template, request, jsonify
import sqlite3

from .constants import DB_PATH
from .limits import TRY_GLOBAL_DAILY_LIMIT
# 2026-11-22: 试扫页原来自己一套扣分权重（危重 45/高 30/中 8/低 2）、
# 自己一套等级线（90/75/60/40），报告页是另一套（10/5/3/0.5、95/80/60/30）。
# 同一份代码先在 /try 看一眼、再正式扫一遍，会看到两个分数两个等级，
# 客户只会认为我们在乱报。现在两处都走 scoring 里的唯一实现。
from .scoring import calculate_score, grade_of, GRADE_TEXT
from .dimensions import (
    dim_coverage as _dim_coverage,
    coverage_report as _coverage_report,
    NOT_RUN as _NOT_RUN,
    PARTIAL as _PARTIAL,
    STATUS_TEXT as _DIM_STATUS_TEXT,
)

try_bp = Blueprint('try', __name__)

# 每个访客每天免费试扫次数上限
_TRY_DAILY_LIMIT = 3

# 试扫支持的语言 —— 唯一事实来源。
# 以前模板里手写一份下拉框、这里另写一份 ext_map，两份各自维护：
# 页面上能选的语言接口不认（选了报「暂不支持」），接口认的页面上又没有。
# 现在模板从这份表渲染，ext_map 也从这份表生成，加/删语言只改一处。
# 每项：(接口值, 显示名, 文件扩展名)
TRY_LANGS = [
    ('python', 'Python', 'py'),
    ('java', 'Java', 'java'),
    ('javascript', 'JavaScript', 'js'),
    ('typescript', 'TypeScript', 'ts'),
    ('go', 'Go', 'go'),
    ('php', 'PHP', 'php'),
    ('c', 'C', 'c'),
    ('cpp', 'C/C++', 'cpp'),
    ('csharp', 'C#', 'cs'),
    ('ruby', 'Ruby', 'rb'),
    ('swift', 'Swift', 'swift'),
    ('kotlin', 'Kotlin', 'kt'),
    ('rust', 'Rust', 'rs'),
    ('scala', 'Scala', 'scala'),
    ('lua', 'Lua', 'lua'),
    ('shell', 'Shell', 'sh'),
    ('sql', 'SQL', 'sql'),
]

# 常见别名 → 接口值。用户/自动识别可能给出 'py'、'golang'、'c++' 这类写法。
_LANG_ALIASES = {
    'py': 'python', 'js': 'javascript', 'ts': 'typescript', 'golang': 'go',
    'c++': 'cpp', 'cs': 'csharp', 'rb': 'ruby', 'kt': 'kotlin', 'kts': 'kotlin',
    'rs': 'rust', 'bash': 'shell', 'sh': 'shell',
}

# 接口值 → 扩展名（含别名），由 TRY_LANGS 生成，不再手写第二份
TRY_EXT_MAP = {v: ext for v, _label, ext in TRY_LANGS}
TRY_EXT_MAP.update({alias: TRY_EXT_MAP[canon] for alias, canon in _LANG_ALIASES.items()})

# 全站每天总次数上限：真正的成本兜底。
# 「每个人 3 次」挡不住有意的刷（换个身份就是新的 3 次），而算力成本是全局的，
# 所以天花板必须也建在全局这一层。超了就是今天不提供了，而不是被一个人吃光。
# 数值本身在 modules/limits.py，报表读的是同一个常量。
_GLOBAL_DAILY_LIMIT = TRY_GLOBAL_DAILY_LIMIT


def _used_today(vid):
    """今天这个访客已经扫成功几次。

    不往内存里记账，直接数 `visitor_events` 里的 `try.ok` 事件：
    - 那是已经落库的事实，跨进程、跨重启都准（进程内计数一重启就归零）；
    - 单一事实来源——报表和限流数出来的是同一个数，不会出现
      「报表说扫了 5 次、系统以为扫了 2 次」这种对不上的情况。

    代价：计数依赖埋点表写入成功。写失败时方向是**放行**（不误伤真人），
    并在 try_scan 里留一条 warning，方便发现异常。
    """
    if not vid:
        return 0
    conn = sqlite3.connect(DB_PATH, timeout=1)
    try:
        row = conn.execute(
            "SELECT count(*) FROM visitor_events "
            "WHERE vid = ? AND kind = 'event' AND path = 'try.ok' "
            "AND created_at >= date('now','localtime')",
            (vid,),
        ).fetchone()
        return int(row[0] or 0)
    except Exception:  # 表还没建 / 查询出错都不该让试扫挂掉
        return 0
    finally:
        conn.close()


def _global_used_today():
    """全站今天总共扫成功几次（成本天花板的当前水位）。"""
    conn = sqlite3.connect(DB_PATH, timeout=1)
    try:
        row = conn.execute(
            "SELECT count(*) FROM visitor_events "
            "WHERE kind = 'event' AND path = 'try.ok' "
            "AND created_at >= date('now','localtime')"
        ).fetchone()
        return int(row[0] or 0)
    except Exception:
        return 0
    finally:
        conn.close()


def _remaining_tries(vid):
    """返回该访客今日剩余试扫次数。"""
    return max(0, _TRY_DAILY_LIMIT - _used_today(vid))


def _track(name, **props):
    """试扫漏斗埋点。失败绝不影响试扫本身——埋点是观察工具，不是业务链路。

    返回「是否真的记下来了」。`try.ok` 同时也是额度账本，写失败就必须留痕，
    否则会出现「某人一天扫了不限次、日志里却查不出原因」这种哑巴故障。
    """
    try:
        from modules.visitor_analytics import track_event
        return bool(track_event(name, **props))
    except Exception:  # noqa: BLE001
        return False


def _health_score(result):
    """把扫描结果折算成「代码健康度」评分（0-100）。

    算法不在这里：扣分权重只有 scoring.calculate_score 一份
    （危重 10 / 高 5 / 中 3（封顶 30）/ 低 0.5（封顶 20），满分 100）。
    本函数只负责三件事：分维度、判「这一维查没查」、挡住满分假象。

    （改之前这里自己写了一套 45/30/8/2 的权重，而函数自己的 docstring
    写的是 20/10/4/1 —— 三个数谁都不知道哪个是对的，这就是副本的下场。）

    分维度：security（安全）/ quality（质量）/ arch（架构）。
    说明：试扫只跑规范层 + 安全引擎（E1/E2/E4/E5/E6），不跑性能(E3)，
    所以健康度只出这三维，避免展示一个永远 100 分的「性能」维度误导用户。
    """
    issues = result.get('issues', []) or []

    dims = {'security': 0, 'quality': 0, 'arch': 0}

    # issue.category -> 评估维度。category 由引擎侧 _output_normalize 统一补
    # （检测器注册表优先、规则包次之、引擎归属兜底），这里只做收敛，不做猜测。
    dim_by_category = {
        'security': 'security',
        'architecture': 'arch',
        'performance': 'quality',   # 试扫不跑 E3，性能先并入质量
        'quality': 'quality',
        'correctness': 'quality',
    }

    def _dim_of(issue):
        """按 category 判维度；判不出返回 None（未归类）。

        2026-11-04 之前这里拿 check_id 匹配 9 个关键词，匹配不上一律算质量。
        结果 E2-BIZ-PY-002（Flask 路由直接查库，检测器注册时写的就是 security）
        因为编号里没有 SEC 字样被算成质量问题，报告上出现
        「安全 100 分」和「1 条越权高危」同框。
        编号是流水号，不是语义——别再从编号里猜。
        """
        cat = str((issue or {}).get('category') or '').strip().lower()
        return dim_by_category.get(cat)

    unclassified = 0
    unclassified_high = 0

    for it in issues:
        sev = (it.get('severity') or 'info').lower()
        if _dim_of(it) is None:
            # 扣分照扣（总分不能因为归不了类就放过），但维度上不硬塞
            unclassified += 1
            if sev in ('critical', 'high'):
                unclassified_high += 1

    # 总分和每一维都用同一个算法。维度分就是「这一维自己的健康分」，
    # 所以一维里的问题只会影响这一维，不会被别的维度摊薄。
    score = calculate_score(issues)
    dim_scores = {
        dim: calculate_score([i for i in issues if _dim_of(i) == dim])
        for dim in dims
    }

    # ── 这一维到底查了没有（2026-11-04）──
    # 扣分只回答「查出来的问题有多严重」，不回答「有没有查」。
    # 100 分原来是 issues 为空的默认值，于是「两百条规则扫过、真没查出问题」
    # 和「安全引擎根本没跑」在页面上长得一模一样——用户会把后者当成前者。
    # 判据只能来自引擎返回的事实（engines / degraded_brains / unsupported），
    # 不能来自我们自己推断。
    _engines = result.get('engines') or {}
    _coverage = _dim_coverage(_engines)
    cov_report = _coverage_report(
        _engines, _coverage,
        unsupported=result.get('unsupported_count') or 0,
        trimmed=result.get('trimmed_count') or 0,
    )

    for _dim, _state in _coverage.items():
        if _state == _NOT_RUN:
            # 负责这个维度的引擎一个都没跑成：不给数字。
            # 写 100 分等于告诉用户「查过了」。
            dim_scores[_dim] = _DIM_STATUS_TEXT[_NOT_RUN]
        elif _state == _PARTIAL:
            # 跑了一部分（有引擎报错/被降级）：分数照算，但必须标明不完整
            dim_scores[_dim] = _DIM_STATUS_TEXT[_PARTIAL]

    # 有文件根本没被解析（认不出的语言 / 超大被截断）时，任何满分都不成立：
    # 没读过的文件里可能有漏洞。这种影响是全局的，三个维度一起降级，
    # 而不是只在总分上扣几分装装样子。
    if result.get('unsupported_count') or result.get('trimmed_count'):
        for _dim in dim_scores:
            if dim_scores[_dim] == 100:
                dim_scores[_dim] = _DIM_STATUS_TEXT[_PARTIAL]

    # 保底（2026-11-04）：有判不出维度的高危问题时，安全维度不许显示满分。
    # 我们不知道它该算哪一维，但知道它不该被一句「100 分」盖过去——
    # 满分比不报危险：不报，用户知道没查；满分，用户以为查过了。
    if unclassified_high:
        dim_scores['security'] = '待确认'

    # 健康度评级：档位由分数读出来，档位线也只有 scoring 一份
    # （S>=95 / A>=80 / B>=60 / C>=30）。之前这里自己一套 90/75/60/40，
    # 同一份代码在试扫页是「A 优秀」、在正式报告里是「C」。
    if not cov_report['complete']:
        # 没查全就不给等级。「A · 优秀」和「安全引擎没跑」同时出现，
        # 跟「安全 100 分 + 1 条越权」是同一种病：拿漂亮的结论盖住没做的事。
        grade = '—'
    else:
        # 试扫永远是免费通道：等级上限 A，与报告页对免费用户的规矩一致。
        # 而且试扫是「粘一段代码」——永远只有一个文件，只能是片段级评估。
        # 不传这一项的话，粘 5 行没报错的代码会拿到「A · 良好」，
        # 那正是这次要治的通胀：没看多少东西，却给了质量结论。
        grade = grade_of(score, tier_scores=None, is_vip=False, file_count=1)
    grade_cn = GRADE_TEXT.get(grade, '未完整检测')

    return {
        'score': score,
        'grade': grade,
        'grade_cn': grade_cn,
        'dims': dim_scores,
        # 每个维度是「查全了」还是「没查/查了一部分」，以及为什么
        'dim_status': _coverage,
        'coverage': cov_report,
        'unclassified': unclassified,
        'unclassified_high': unclassified_high,
    }


def _summarize(result):
    """把完整扫描结果压成「摘要」——只给结论，不给细节。

    返回：健康度评分 + 严重度分布 + 每档前几条标题（脱敏，不含行号/代码/完整修复建议）。
    """
    issues = result.get('issues', []) or []

    # 严重度顺序：critical > high > medium > low
    sev_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3, 'info': 4}
    by_sev = {}
    for it in issues:
        sev = (it.get('severity') or 'info').lower()
        by_sev.setdefault(sev, []).append(it)

    summary = {
        'total_issues': len(issues),
        'health': _health_score(result),
        'severity_breakdown': {
            sev: len(items)
            for sev, items in sorted(by_sev.items(), key=lambda kv: sev_order.get(kv[0], 99))
        },
        # 每档最多给 3 条「标题」作钩子，脱敏（不报行号、不报代码、不报完整建议）
        'highlights': [],
    }

    # 按严重度优先，每档取前 3 条，最多总共 5 条
    seen = 0
    for sev in ['critical', 'high', 'medium', 'low']:
        items = by_sev.get(sev, [])
        for it in items[:3]:
            if seen >= 5:
                break
            summary['highlights'].append({
                'severity': sev,
                'name': (it.get('title') or it.get('name') or it.get('rule_id') or '检测问题')[:60],
                # 只给「类别」级别的提示，不给具体行号和代码
                'category': it.get('category', ''),
            })
            seen += 1
        if seen >= 5:
            break

    return summary


@try_bp.route('/try')
def try_page():
    """免费试扫页面（免登录）。"""
    from modules.visitor_analytics import current_vid
    remaining = _remaining_tries(current_vid())
    return render_template('try.html', remaining=remaining, daily_limit=_TRY_DAILY_LIMIT,
                           try_langs=TRY_LANGS, try_ext_map=TRY_EXT_MAP)


@try_bp.route('/api/try-scan/progress/<job_id>')
def try_scan_progress(job_id):
    """免登录试扫的真实进度：只转发扫描器事件，不估算、不编阶段。"""
    from modules.scan_progress_bridge import forward
    return jsonify(forward(job_id))


@try_bp.route('/api/try-scan', methods=['POST'])
def try_scan():
    """免登录试扫接口：限次、只回摘要。

    限流按访客 id（xp_vid），不按 IP——原因见模块顶部「为什么不用 IP」。
    """
    from modules.visitor_analytics import current_vid
    vid = current_vid()
    remaining = _remaining_tries(vid)
    if remaining <= 0:
        _track('try.fail', reason='quota')
        return jsonify({
            'error': '今日免费试扫次数已用完，注册后可无限使用',
            'remaining': 0,
        }), 429

    # 全站天花板：被刷爆时宁可今天不提供，也不能让一个人把算力吃光。
    if _global_used_today() >= _GLOBAL_DAILY_LIMIT:
        _track('try.fail', reason='global_quota')
        return jsonify({
            'error': '今天的免费试扫名额已用完，请明天再来或注册后使用',
            'remaining': 0,
        }), 429

    data = request.get_json(silent=True) or {}
    code = (data.get('code') or '').strip()
    language = (data.get('language') or 'auto').strip()
    # 前端生成的本次任务号，用来在等待期间查「真的扫到哪一步了」
    progress_job_id = str(data.get('progress_job_id') or '')[:128]

    if not code:
        _track('try.fail', reason='empty')
        return jsonify({'error': '请先粘贴要检测的代码'}), 400

    # 大小保护：单次试扫代码不超过 100KB（够覆盖绝大多数单文件）
    if len(code.encode('utf-8')) > 100 * 1024:
        _track('try.fail', reason='too_big')
        return jsonify({'error': '试扫最多支持 100KB 代码，更大项目请注册后使用'}), 413

    # 构造 files_dict（试扫按「单文件」处理，路径后缀决定引擎走哪套语法分析）
    # 「自动识别」必须真的识别。原来这里默认落成 .txt，引擎拿不到语法信息，
    # 只能跑纯正则的通用规则：同一段 Python（SQL注入 + os.system）实测
    # 指定 python 出 2 条高危、健康度 40/D；落成 txt 只出 1 条中危、健康度 92/A。
    # 默认路径废掉，等于这个功能白做——所以认不出来就让用户选，不再偷偷当 txt。
    language_was_auto = language.lower() in ('', 'auto')
    if language_was_auto:
        from modules.lang_detect import detect as _detect_language
        guessed, _top, _second = _detect_language(code)
        if not guessed:
            _track('try.fail', reason='need_language')
            return jsonify({
                'error': '识别不出这段代码是哪门语言，请在「代码语言」里手动选一个（选错会导致漏报）',
                'need_language': True,
            }), 400
        language = guessed

    ext = TRY_EXT_MAP.get(language.lower())
    if not ext:
        _track('try.fail', reason='unsupported', lang=language)
        return jsonify({
            'error': f'暂不支持这门语言：{language}，请换一门或注册后用完整项目扫描',
            'need_language': True,
        }), 400
    files_dict = {f'sample.{ext}': code}

    # 复用现有扫描器调用
    try:
        from modules.scanner import call_scanner
        from modules.constants import FREE_BRAIN_IDS

        brain_ids = ["1", "2", "4", "5", "6"]  # 试扫：规范层 + 安全(E2)，只给摘要不给细节
        result = call_scanner(
            files_dict,
            brain_ids,
            options={'language': language, 'scan_mode': 'basic', 'is_vip': False,
                     'progress_job_id': progress_job_id},
        )
    except Exception as e:
        from modules import logger
        logger.warning(f'免费试扫失败 (vid={vid}): {e}')
        _track('try.fail', reason='engine', lang=language)
        return jsonify({'error': '扫描引擎暂时不可用，请稍后再试'}), 503

    summary = _summarize(result)

    # 漏斗关键事件，同时是额度账本：`try.ok` 落库一条 = 这个访客今天用掉一次。
    # 分数要一起记——「什么问题的人才会去注册」只能从这上面看出来。
    recorded = _track(
        'try.ok',
        lang=language,
        auto=1 if language_was_auto else 0,
        issues=summary.get('total_issues', 0),
        score=(summary.get('health') or {}).get('score'),
        grade=(summary.get('health') or {}).get('grade'),
        size=len(code.encode('utf-8')),
        secs=round(float(result.get('scan_time') or 0), 1),
        # 这次是不是全维度查完了。日后看漏斗能回答「有多少人拿到的
        # 是一份不完整的报告」——这决定我们该不该在高峰期限流。
        covered=1 if (summary.get('health') or {}).get('coverage', {}).get('complete') else 0,
    )
    if not recorded:
        # 记不下来就等于没扣额度。方向是放行（不误伤真人），但必须留痕，
        # 否则会变成「有人无限扫、日志里一点线索都没有」的哑巴故障。
        from modules import logger
        logger.warning(f'试扫额度未能记账（埋点写入失败）vid={vid}')

    return jsonify({
        'status': 'ok',
        'remaining': _remaining_tries(vid),
        'summary': summary,
        'file_count': result.get('file_count', 1),
        'scan_time': result.get('scan_time', 0),
        # 让页面能告诉用户「这次是按什么语言解析的」——认错了要让人看得见
        'language': language,
        'language_auto': language_was_auto,
    })
