"""试扫三维评估的「维度 ← 引擎」契约，以及「到底查没查」的判定。

为什么需要这个文件（2026-11-04）：

试扫页面原来只有一个输入——issues 列表。列表为空就是 100 分。
于是这两件事在页面上长得一模一样：
    ① 引擎跑了，这两百条规则扫过，真没查出问题
    ② 引擎根本没跑（进程崩了 / 超时 / 高负载被跳过 / 认不出的文件被 ignore）
用户看到 100 分，会当成 ①。这是「给假安心」，比不报更危险——
不报，用户知道自己没查；满分，用户以为查过了。

判据必须来自事实，不能来自推断。引擎其实已经把这些事实吐出来了：
    results[brain]['error']      —— 这个引擎跑了但失败了
    degraded_brains              —— 高负载时被主动跳过的重引擎
    unsupported_files / ignored  —— 这文件压根没解析
只是 call_scanner 的白名单没往上带（见 modules/scanner.py），下游看不见。

所以这里只做两件事：
    1. 声明每个维度由哪些引擎负责（唯一事实来源，别在别处再写一遍）
    2. 把引擎侧的事实翻译成「这个维度查没查」，三态：查全 / 查了一部分 / 没查
"""
from __future__ import annotations

# 维度 ← 引擎编号。依据 modules.constants.BRAINS 的官方定义：
#   1 = E1 语法与AST      → 质量问题
#   2 = E2 安全检测        → 安全问题
#   4 = E4 代码质量与可观测 → 质量问题
#   5 = E5 架构与部署      → 架构问题
#   6 = E6 组件合规        → 质量问题（合规属于质量范畴）
#   3 = E3 性能、7 = E7 AI应用健康：试扫不跑，因此不列入任何维度，
#      也不会因为「它们没跑」而让某个维度变成没查——那是设计，不是缺陷。
DIM_ENGINES = {
    'security': ('2',),
    'quality': ('1', '4', '6'),
    'arch': ('5',),
}

DIM_LABELS = {
    'security': '安全',
    'quality': '质量',
    'arch': '架构',
}

# 维度覆盖状态
CHECKED = 'checked'      # 该维度负责的引擎全部跑完且没报错
PARTIAL = 'partial'      # 跑了一部分（部分引擎失败/降级）
NOT_RUN = 'not_run'      # 一个都没跑成

# 对外展示文案。显示"未检测"而不是 100 分——这是我们唯一诚实的选项。
STATUS_TEXT = {
    CHECKED: '',
    PARTIAL: '部分未检测',
    NOT_RUN: '未检测',
}

# 成绩可用、但有文件没读进来时的那句话。
# 与 PARTIAL 分开写：「部分未检测」是这一维没查全；这句是「查的部分是准的，
# 但有文件没读到」。两件事混成一句，客户没法判断该不该信这个分。
COVERAGE_CAVEAT = '基于已解析的文件'

# 读到多少比例的文件，成绩才算代表这份代码。
# 实测 89 份报告有未解析文件：12 份是「唯一的文件都没读进去」，
# 另有 47 份只是零星几个补丁/二进制文件。一刀切（有未解析就不给评级）
# 会把 77 份正常报告的成绩抹掉；一刀不切又会把 12 份没读过的当成满分。
# 判据因此改成覆盖率——读到一半以上才评级，这句话对客户讲得清。
COVERAGE_MIN_GRADED = 0.5


def engine_ready(engines, brain_id):
    """这个引擎能不能拿来评级：真跑了、且没报错。

    与 card_state 的分工：card_state 回答「卡片上写什么」，所以文件没解析
    也会降成「部分未检测」；这里只回答「这个引擎给的结果能不能用」。
    文件没解析是整个报告的覆盖问题，由 coverage_ok 单独判——
    把两件事塞进同一个 state，就会出现「明明查出 14 个问题，三层却全写未检测」。
    """
    if not isinstance(engines, dict) or not engines:
        return True
    st = engines.get(str(brain_id))
    if not isinstance(st, dict):
        return True
    return bool(st.get('executed')) and not st.get('error')


def coverage_ok(file_count, unsupported=0, trimmed=0):
    """读到的文件够不够多，够才配给评级。

    没有文件数（老报告没落这个字段）时返回 False —— 拿不到证据就不下结论，
    宁可显示「未完整检测」，也不给一个不知道覆盖多少的成绩。
    """
    gap = (unsupported or 0) + (trimmed or 0)
    if gap <= 0:
        return True
    try:
        total = int(file_count or 0)
    except (TypeError, ValueError):
        total = 0
    if total <= 0:
        return False
    return (total - gap) / float(total) >= COVERAGE_MIN_GRADED


def engine_status(results, requested, degraded=None):
    """从引擎返回的 results 里读出每个被请求引擎的执行状态。

    results: 引擎响应的 results 字典（brain_id -> {issues, error, elapsed...}）
    requested: 本次请求的 brain 列表（引擎实际被要求跑哪些）
    degraded: 引擎自报被跳过的 brain 列表

    返回 {brain_id: {'executed': bool, 'issues': n, 'error': str, 'reason': str}}
    reason 只在没跑成时出现，取值：no_result（响应里没有它）/ error / degraded。
    """
    results = results if isinstance(results, dict) else {}
    degraded = {str(b) for b in (degraded or [])}
    status = {}

    for bid in (requested or []):
        bid = str(bid)
        if bid in degraded:
            status[bid] = {'executed': False, 'issues': 0, 'error': '', 'reason': 'degraded'}
            continue

        node = results.get(bid)
        if not isinstance(node, dict):
            # 请求了但响应里没有这个键：引擎调度层就没执行它
            status[bid] = {'executed': False, 'issues': 0, 'error': '', 'reason': 'no_result'}
            continue

        err = node.get('error')
        entry = {
            'executed': True,
            'issues': len(node.get('issues') or []),
            'error': str(err)[:240] if err else '',
        }
        if err:
            # 跑了但失败：算部分可用。它可能扫了一半就崩了，所以不能当"查过了"
            entry['reason'] = 'error'
        elapsed = node.get('elapsed')
        if isinstance(elapsed, (int, float)):
            entry['elapsed'] = round(float(elapsed), 2)
        status[bid] = entry

    return status


def dim_coverage(status):
    """每个维度的覆盖状态。只对声明过的维度给结论，别的不猜。"""
    coverage = {}
    for dim, engines in DIM_ENGINES.items():
        states = [status.get(e) or {'executed': False, 'reason': 'not_requested'} for e in engines]
        usable = [s for s in states if s.get('executed') and not s.get('error')]
        if not usable:
            coverage[dim] = NOT_RUN
        elif len(usable) == len(states):
            coverage[dim] = CHECKED
        else:
            coverage[dim] = PARTIAL
    return coverage


def card_state(engines, brain_id, unsupported=0, trimmed=0):
    """单个引擎卡片该显示什么。返回 (state, text)。

    用于正式报告页的 9 个检测维度卡和三层评分。与试扫页共用同一份判定，
    不允许两处各写一套——已经吃过一次「同一份数据两条口径」的苦。

    engines=None 或空字典 = 台账缺失（2026-11-04 之前落库的报告）。
    这时不能断言「没跑」，只能退回旧行为：当作查过、不给提示。
    老报告一百多份，不能因为这次改动集体变黄。

    台账里没有这个 brain 的键 = 本次根本没请求它（例如免费版锁住、
    PoC 未启用），不属于「请求了但没跑」，不提示。只有键存在且
    executed=False 才是确定的「没跑」。
    """
    if not isinstance(engines, dict) or not engines:
        return CHECKED, ''

    st = engines.get(str(brain_id))
    if not isinstance(st, dict):
        return CHECKED, ''

    if not st.get('executed'):
        return NOT_RUN, STATUS_TEXT[NOT_RUN]
    if st.get('error') or unsupported or trimmed:
        return PARTIAL, STATUS_TEXT[PARTIAL]
    return CHECKED, ''


def coverage_report(status, coverage, unsupported=0, trimmed=0):
    """给前端和埋点用的一份账：哪些维度没查全、为什么。

    unsupported/trimmed 影响的是全局而不是单个维度：
    有文件根本没被解析时，任何维度的 100 分都不成立——没读过的文件里
    可能就有漏洞。所以这种情况把三个维度一起降级为「部分未检测」。
    """
    not_run = [d for d, s in coverage.items() if s == NOT_RUN]
    partial = [d for d, s in coverage.items() if s == PARTIAL]

    reasons = {}
    for bid, st in (status or {}).items():
        if st.get('executed') and not st.get('error'):
            continue
        reasons[bid] = st.get('reason') or 'unknown'

    complete = not not_run and not partial and not unsupported and not trimmed

    report = {
        'complete': complete,
        'not_run': not_run,
        'partial': partial,
        'engine_reasons': reasons,
    }
    if unsupported:
        report['unsupported_files'] = int(unsupported)
    if trimmed:
        report['trimmed_files'] = int(trimmed)
    return report
