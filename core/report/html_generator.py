"""
煋鉴(Xinpect) HTML报告 - 主渲染器（皮肤层装配器）
负责数据提取、调用组件、使用模板生成完整HTML报告
- 组件层：components/  各独立渲染函数
- 模板层：templates/   完整文档结构装配
- 主题层：themes/      CSS变量主题系统 + JS交互
"""

import os
import logging
from datetime import datetime
from collections import defaultdict

from .themes import BRAIN_NAMES
from .components import (
    render_issue_card,
    render_header,
    render_scores,
    render_stats,
    render_brain_section,
    render_issues_section,
    render_suggestions_section,
    render_passed_section,
    render_fp_section,
    render_llm_fp_section,
    render_ai_verified_badge,
    render_footer,
    _esc,
    _get_level_icon,
)
from .page_templates import build_full_html

_logger = logging.getLogger(__name__)


def _module_to_brain(module_id: str) -> str:
    """将模块ID映射到大脑编号"""
    mod_num = module_id.split('.')[0] if '.' in module_id else module_id
    # 只取数字部分
    try:
        n = int(mod_num)
    except (ValueError, TypeError):
        return '8'

    mapping = {
        1: '1', 2: '2', 3: '2', 4: '3', 5: '3', 6: '4',
        7: '4', 8: '4', 9: '5', 10: '5', 11: '6', 12: '6',
        13: '6', 14: '6', 15: '7', 16: '7', 17: '7',
        18: '8', 19: '8',
    }
    return mapping.get(n, '8')


class _RunnerAdapter:
    """适配器：将旧引擎的数据格式包装成类似runner的接口"""

    def __init__(self, all_results: dict, scores: dict, project_type: str = ''):
        self.results = all_results
        self._scores = scores
        self._project_type = project_type
        self.total_checks = sum(len(r) for r in all_results.values())
        self.fp_count = 0
        self.llm_fp_count = 0
        self.llm_enabled = False
        self.llm_model_name = ''
        self.llm_fp_results = []
        self.fp_stats = {'total': 0, 'filtered': 0, 'by_rule': {}}
        self._incremental_stats = None

        # 统计各级别（支持新级别 blocking/problem/suggestion 及兼容旧级别）
        _BLOCKING_LEVELS = ('blocking', 'error')
        _PROBLEM_LEVELS = ('problem', 'warning')
        _SUGGESTION_LEVELS = ('suggestion', 'info')
        self.error_count = sum(
            1 for results in all_results.values()
            for r in results if getattr(r, 'level', '') in _BLOCKING_LEVELS and getattr(r, 'status', 'active') == 'active'
        )
        self.warning_count = sum(
            1 for results in all_results.values()
            for r in results if getattr(r, 'level', '') in _PROBLEM_LEVELS and getattr(r, 'status', 'active') == 'active'
        )
        self.info_count = sum(
            1 for results in all_results.values()
            for r in results if getattr(r, 'level', '') in _SUGGESTION_LEVELS and getattr(r, 'status', 'active') == 'active'
        )
        # 建议类总数（不计入问题、不扣分）
        self.suggestion_count = self.info_count
        # 真正的代码问题总数（阻断 + 警告）
        self.problem_count = self.error_count + self.warning_count
        # active_checks 仍保留为全部有效项（含建议），兼容旧接口
        self.active_checks = self.error_count + self.warning_count + self.info_count

        # 模拟 context
        self.context = type('Context', (), {'project_type': project_type, 'project_path': ''})()

        # 模拟 rule_loader (不提供passed items)
        self.rule_loader = type('RuleLoader', (), {'all_rules': []})()

    def calculate_scores(self, config=None):
        return self._scores

    def get_flat_results(self):
        flat = []
        for results in self.results.values():
            flat.extend(results)
        return flat

    def get_results_by_level(self, level):
        return [r for results in self.results.values() for r in results if getattr(r, 'level', '') == level]


def _extract_module_stats(runner):
    """按模块统计结果"""
    _VALID_LEVELS = ('blocking', 'problem', 'suggestion', 'error', 'warning', 'info')
    module_stats = defaultdict(lambda: {'total': 0, 'blocking': 0, 'error': 0, 'problem': 0, 'warning': 0, 'suggestion': 0, 'info': 0})
    for module_id, results in runner.results.items():
        for r in results:
            if getattr(r, 'status', 'active') != 'active':
                continue
            module_stats[module_id]['total'] += 1
            level = r.level if r.level in _VALID_LEVELS else 'info'
            module_stats[module_id][level] += 1
    return module_stats


def _extract_brain_stats(module_stats):
    """按大脑统计结果"""
    brain_stats = defaultdict(lambda: {'total': 0, 'blocking': 0, 'error': 0, 'problem': 0, 'warning': 0, 'suggestion': 0, 'info': 0})
    for module_id, stats in module_stats.items():
        brain_id = _module_to_brain(module_id)
        brain_name = BRAIN_NAMES.get(brain_id, f'大脑{brain_id}')
        brain_stats[brain_name]['total'] += stats['total']
        brain_stats[brain_name]['blocking'] += stats['blocking'] + stats['error']
        brain_stats[brain_name]['problem'] += stats['problem'] + stats['warning']
        brain_stats[brain_name]['suggestion'] += stats['suggestion'] + stats['info']
    return brain_stats


def _collect_issues_and_suggestions(runner):
    """收集问题列表和建议列表"""
    _SUGG_LEVELS = ('suggestion', 'info')
    all_issues = []   # 真正的代码问题 (blocking/error/problem/warning)
    all_suggestions = []  # 建议类 (suggestion/info)，不扣分
    for module_id, results in runner.results.items():
        for r in results:
            if getattr(r, 'status', 'active') == 'active':
                if getattr(r, 'level', '') in _SUGG_LEVELS:
                    all_suggestions.append(r)
                else:
                    all_issues.append(r)
    level_order = {'blocking': 0, 'error': 0, 'problem': 1, 'warning': 1}
    all_issues.sort(key=lambda x: level_order.get(getattr(x, 'level', 'warning'), 9))
    all_suggestions.sort(key=lambda x: getattr(x, 'rule_id', ''))
    return all_issues, all_suggestions


def _collect_passed_items(runner):
    """收集通过的检查项"""
    passed_items = []
    try:
        executed_ids = set()
        for r in runner.get_flat_results():
            rid = getattr(r, 'rule_id', '') or getattr(r, 'check_id', '') or getattr(r, 'id', '')
            executed_ids.add(rid)
        applicable_rules = [r for r in runner.rule_loader.all_rules
                           if r.is_applicable(runner.context.project_type, runner.context)]
        for rule in sorted(applicable_rules, key=lambda x: x.id):
            if rule.id not in executed_ids:
                passed_items.append(rule)
    except Exception:
        pass
    return passed_items


def _build_passed_html(passed_items):
    """构建通过项列表HTML"""
    if not passed_items:
        return ''
    cat_icons = {'bug': '🐛', 'code_smell': '💩', 'engineering_maturity': '🏗️'}
    passed_html = ''
    for rule in passed_items[:100]:
        icon = cat_icons.get(getattr(rule, 'category', ''), '📌')
        passed_html += f'''<div class="passed-item">
            <span class="passed-icon">✅</span>
            <span class="passed-id">{_esc(rule.id)}</span>
            <span class="passed-name">{_esc(rule.name)}</span>
            <span class="passed-cat">{icon} {_esc(getattr(rule, "category", ""))}</span>
        </div>'''
    return passed_html


def _build_fp_html(fp_results):
    """构建误报列表HTML"""
    if not fp_results:
        return ''
    from collections import defaultdict as _dd
    fp_by_module = _dd(list)
    for r in fp_results:
        rid = getattr(r, 'rule_id', '') or getattr(r, 'check_id', '') or ''
        mod_id = rid.split('.')[0] if '.' in rid else 'unknown'
        fp_by_module[mod_id].append(r)
    fp_html = ''
    for mod_id in sorted(fp_by_module.keys()):
        mod_fps = fp_by_module[mod_id]
        items = ''
        for r in mod_fps:
            location = getattr(r, 'location', {}) or {}
            file_info = location.get('file', '')
            line_info = location.get('line', 0)
            loc = f'{_esc(file_info)}:{line_info}' if file_info else '全局'
            fp_reason = getattr(r, 'fp_reason', '')
            rule_name = getattr(r, 'rule_name', '') or getattr(r, 'name', '') or ''
            rule_id = getattr(r, 'rule_id', '') or getattr(r, 'check_id', '') or ''
            message = getattr(r, 'message', '') or ''
            items += f'''<div class="fp-item">
                <span>{_get_level_icon(getattr(r, "level", "info"))} <strong>{_esc(rule_id)} {_esc(rule_name)}</strong>: {_esc(message[:80])} ({loc})</span>
                {f'<div class="fp-reason">过滤原因: {_esc(fp_reason)}</div>' if fp_reason else ''}
            </div>'''
        fp_html += f'''<details class="fp-section"><summary><b>模块{mod_id}</b> ({len(mod_fps)}项)</summary>{items}</details>'''
    return fp_html


def _build_llm_fp_html(llm_fp_results):
    """构建LLM非问题列表HTML"""
    if not llm_fp_results:
        return ''
    from collections import defaultdict as _dd
    llm_fp_by_module = _dd(list)
    for r in llm_fp_results:
        rid = getattr(r, 'rule_id', '') or getattr(r, 'check_id', '') or ''
        mod_id = rid.split('.')[0] if '.' in rid else 'unknown'
        llm_fp_by_module[mod_id].append(r)
    llm_fp_html = ''
    for mod_id in sorted(llm_fp_by_module.keys()):
        mod_fps = llm_fp_by_module[mod_id]
        items = ''
        for r in mod_fps:
            location = getattr(r, 'location', {}) or {}
            file_info = location.get('file', '')
            line_info = location.get('line', 0)
            loc = f'{_esc(file_info)}:{line_info}' if file_info else '全局'
            fp_reason = getattr(r, 'fp_reason', '')
            rule_name = getattr(r, 'rule_name', '') or getattr(r, 'name', '') or ''
            rule_id = getattr(r, 'rule_id', '') or getattr(r, 'check_id', '') or ''
            message = getattr(r, 'message', '') or ''
            items += f'''<div class="fp-item">
                <span>{_get_level_icon(getattr(r, "level", "info"))} <strong>{_esc(rule_id)} {_esc(rule_name)}</strong>: {_esc(message[:80])} ({loc})</span>
                {f'<div class="fp-reason">LLM判定: {_esc(fp_reason)}</div>' if fp_reason else ''}
            </div>'''
        llm_fp_html += f'''<details class="fp-section"><summary><b>模块{mod_id}</b> ({len(mod_fps)}项)</summary>{items}</details>'''
    return llm_fp_html


def _build_issue_cards(all_issues, runner):
    """构建问题详情卡片HTML"""
    issues_html = ''
    for idx, r in enumerate(all_issues):
        module_id = ''
        for mid, results in runner.results.items():
            if r in results:
                module_id = mid
                break
        brain_id = _module_to_brain(module_id) if module_id else '8'
        bname = BRAIN_NAMES.get(brain_id, '业务安全')
        issues_html += render_issue_card(r, f'issue-{idx}', bname)
    if not all_issues:
        issues_html = '<div class="empty-state">🎉 恭喜！未发现任何代码问题</div>'
    return issues_html


def _build_suggestion_cards(all_suggestions, runner):
    """构建建议类卡片HTML"""
    suggestions_html = ''
    for idx, r in enumerate(all_suggestions):
        module_id = ''
        for mid, results in runner.results.items():
            if r in results:
                module_id = mid
                break
        brain_id = _module_to_brain(module_id) if module_id else '8'
        bname = BRAIN_NAMES.get(brain_id, '业务安全')
        suggestions_html += render_issue_card(r, f'sug-{idx}', bname)
    return suggestions_html


def _build_llm_badge(llm_enabled, llm_model):
    """构建LLM增强标识"""
    if llm_enabled and llm_model:
        return f'<div class="llm-badge">🤖 LLM增强已启用 · 模型：{_esc(llm_model)}</div>'
    return ''


def _build_incremental_html(runner):
    """构建增量检查信息"""
    try:
        inc_stats = getattr(runner, '_incremental_stats', None)
        if inc_stats and inc_stats.get('mode') != 'full':
            mode_icon = '🌿' if inc_stats['mode'] == 'git' else '📦'
            return f'<div class="inc-badge">{mode_icon} 增量检查: {inc_stats["checked"]}/{inc_stats["total"]} 文件 (模式: {inc_stats["mode"]})</div>'
    except Exception:
        pass
    return ''


def generate_html_report(
    runner=None,
    output_dir: str = None,
    project_path: str = '',
    project_type: str = '',
    all_results: dict = None,
    scores: dict = None,
    theme: str = 'light',
) -> str:
    """生成HTML报告

    Args:
        runner: RuleRunner实例（新引擎）
        output_dir: 输出目录，默认output/
        project_path: 项目路径
        project_type: 项目类型
        all_results: 旧引擎的结果字典 {module_id: [RuleCheckResult]}
        scores: 旧引擎的评分字典 {total, bug, code_smell, engineering_maturity}
        theme: 主题名称 'light' / 'dark'，默认 'light'

    Returns:
        生成的HTML文件路径
    """
    # 兼容旧引擎：如果没有runner，用适配器
    if runner is None and all_results is not None and scores is not None:
        runner = _RunnerAdapter(all_results, scores, project_type)
    elif runner is None:
        _logger.warning('generate_html_report: 无runner也无all_results，跳过')
        return ''

    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'output')

    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    html_path = os.path.join(output_dir, f'qa_report_{timestamp}.html')

    # 提取数据
    scores_data = runner.calculate_scores()
    total = runner.total_checks
    active = runner.active_checks
    fp_count = runner.fp_count
    errors = runner.error_count
    warnings = runner.warning_count
    infos = runner.info_count
    # 建议类（不计分）
    suggestion_count = getattr(runner, 'suggestion_count', infos)
    # 真正的代码问题数
    problem_count = getattr(runner, 'problem_count', errors + warnings)
    llm_enabled = getattr(runner, 'llm_enabled', False)
    llm_model = getattr(runner, 'llm_model_name', '')
    llm_fp_count = getattr(runner, 'llm_fp_count', 0)
    # v3.5.1: AI二次校验统计
    ai_stats = getattr(runner, 'ai_verification_stats', {}) or {}
    ai_verified = ai_stats.get('total_checked', 0) if ai_stats.get('enabled') else 0
    # 评分备注
    scoring_note = scores_data.get('scoring_note', '基于代码问题评分，优化建议不扣分')

    # 按模块统计
    module_stats = _extract_module_stats(runner)
    # 按大脑统计
    brain_stats = _extract_brain_stats(module_stats)

    # 收集所有有效问题 / 建议
    all_issues, all_suggestions = _collect_issues_and_suggestions(runner)

    # 收集通过项
    passed_items = _collect_passed_items(runner)

    # 收集误报
    fp_results = [r for r in runner.get_flat_results()
                  if getattr(r, 'status', 'active') == 'fp']
    llm_fp_results = getattr(runner, 'llm_fp_results', [])

    # ===== 构建各部分HTML =====
    score_total = scores_data.get('total', 0)
    score_bug = scores_data.get('bug', 0)
    score_smell = scores_data.get('code_smell', 0)
    score_eng = scores_data.get('engineering_maturity', 0)

    # 问题卡片
    issues_html = _build_issue_cards(all_issues, runner)
    suggestions_html = _build_suggestion_cards(all_suggestions, runner)

    # 通过项
    passed_html = _build_passed_html(passed_items)

    # 误报列表
    fp_html = _build_fp_html(fp_results)
    llm_fp_html = _build_llm_fp_html(llm_fp_results)

    # LLM增强标识
    llm_badge = _build_llm_badge(llm_enabled, llm_model)

    # 增量检查信息
    incremental_html = _build_incremental_html(runner)

    # 组装所有body部分
    body_parts = [
        render_header(project_path, project_type, now_str, llm_badge, incremental_html),
        render_scores(score_total, score_bug, score_smell, score_eng, scoring_note),
        render_stats(errors, warnings, suggestion_count, problem_count, fp_count, total),
        render_brain_section(brain_stats),
        render_issues_section(all_issues, issues_html),
        render_suggestions_section(all_suggestions, suggestions_html),
        render_passed_section(passed_items, passed_html),
        render_fp_section(fp_count, fp_html, fp_results),
        render_llm_fp_section(llm_fp_count, llm_fp_html, llm_fp_results),
        render_ai_verified_badge(ai_verified),
        render_footer(now_str),
    ]

    # 构建完整HTML（使用模板层）
    html_content = build_full_html(project_path, now_str, body_parts, theme=theme)

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    _logger.info(f'HTML报告已生成: {html_path}')
    return html_path
