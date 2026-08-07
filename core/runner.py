"""
规则扫描协调器
从 v1.0 的 1946 行上帝类重构为模块化架构。

子模块：executor.RuleExecutor | scoring.ScoringEngine | fp_filter.FalsePositiveFilter | llm_bridge.LLMBridge

v4.2 新增能力层：
  - rule_pruner.RulePruner: 规则智能裁剪（语言/框架感知）
  - incremental_scanner.IncrementalScanner: 增量扫描引擎（结果缓存）
"""
import os, logging, time
from typing import Dict, List, Optional
from collections import defaultdict
from .context import QAContext
from .rule_loader import RuleLoader, Rule, RuleCheckResult
from .telemetry import create_telemetry_service
from .executor import RuleExecutor, SCAN_DEADLINE
from .scoring import (ScoringEngine, CHECK_CATEGORIES, CATEGORY_NAMES, CATEGORY_ICONS,
                      normalize_level, get_check_category, classify_severity)
from .fp_filter import FalsePositiveFilter
from .llm_bridge import LLMBridge

logger = logging.getLogger(__name__)
_log_xinpect = logging.getLogger("xinpect")


def _deduct_credits(context, results, email="", srv="", tkn=""):
    email = email or os.environ.get('XINPECT_USER_EMAIL', '')
    if not email: return
    srv = srv or os.environ.get('XINPECT_SERVER_URL', os.environ.get('MENFANG_URL', 'https://xinpect.xingwangzhineng.com'))
    tkn = tkn or os.environ.get('MENFANG_TOKEN', '')
    total, bd = 0, []
    try:
        from .cost_manager import CostManager
        cm = CostManager(project_id=context.project_path or "default")
        if hasattr(cm, '_records') and cm._records:
            for r in cm._records[-20:]:
                if hasattr(r,'extra') and 'credit_info' in r.extra:
                    ci = r.extra['credit_info']; total += ci.get('credits',0)
                    bd.append({'brain_id':r.brain_id,'model':ci.get('model',''),'credits':ci.get('credits',0),
                               'prompt_tokens':ci.get('prompt_tokens',0),'completion_tokens':ci.get('completion_tokens',0)})
    except Exception: pass
    if total <= 0: total = max(10, len([m for m,rl in (results or{}).items() if rl]) * 15)
    try:
        try: from coze_workload_identity import requests as _rq
        except ImportError: from coze_workload_identity import requests as _rq
        resp = _rq.post(f"{srv}/api/credits/deduct",
            json={"email":email,"credits":total,"reason":"煋鉴AI代码审查",
                  "scan_id":f"local_{int(time.time())}",
                  "brain_id":",".join([d.get("brain_id","") for d in bd[:3]]),
                  "model":bd[0].get("model","") if bd else "",
                  "prompt_tokens":sum(d.get("prompt_tokens",0) for d in bd),
                  "completion_tokens":sum(d.get("completion_tokens",0) for d in bd),"project":"xinpect"},
            headers={"Content-Type":"application/json","Authorization":f"Bearer {tkn}" if tkn else ""}, timeout=10)
        if resp.status_code == 200:
            _log_xinpect.info(f"[积分] 消耗{total}, 剩余{resp.json().get('balance',0)}")
    except Exception as e: _log_xinpect.debug(f"[积分] 异常: {e}")


class RuleRunner:
    """规则扫描协调器 — 组织各子模块完成完整扫描
    
    v4.2 新增能力层：
      - rule_pruner: 规则智能裁剪（语言/框架感知，默认开启）
      - incremental_scanner: 增量扫描引擎（结果缓存，默认开启）
    """
    def __init__(self, context=None, rule_loader=None, rules_dir=None,
                 enable_fp_filter=True, enable_deep_diagnosis=True, enable_telemetry=True,
                 fp_mode="quick", diagnosis_mode="quick", scoring_mode="quick", sdk=None,
                 enable_llm_enhancement=None, incremental=True,
                 enable_rule_pruning=True, force_full_scan=False):
        self.context = context or QAContext()
        self.rule_loader = rule_loader or RuleLoader(rules_dir)
        self.enable_fp_filter, self.enable_deep_diagnosis = enable_fp_filter, enable_deep_diagnosis
        self.fp_mode, self.diagnosis_mode, self.scoring_mode = fp_mode, diagnosis_mode, scoring_mode
        self.sdk = sdk
        self._results: Dict[str, List[RuleCheckResult]] = defaultdict(list)
        self._remote_engine_url = self._remote_engine_token = None
        self._telemetry = create_telemetry_service(config=self.context.config, cli_disabled=not enable_telemetry)
        self.incremental = incremental
        self._incremental_checker = None
        self._incremental_stats = {"mode":"full","total":0,"checked":0}

        # v4.2: 规则裁剪引擎（默认开启）
        self.enable_rule_pruning = enable_rule_pruning
        self._rule_pruner = None  # 延迟初始化（需要先加载规则）

        # v4.2: 增量扫描引擎（结果缓存，默认开启）
        # force_full_scan=True 时跳过增量扫描，强制全量
        self.force_full_scan = force_full_scan
        self._inc_scanner = None
        self._inc_scan_stats: dict = {}

        # 子模块
        self.executor = RuleExecutor(context=self.context, rule_loader=self.rule_loader)
        self.executor._diagnosis_mode = diagnosis_mode; self.executor._sdk = sdk
        self.scorer = ScoringEngine(context=self.context, scoring_mode=scoring_mode)
        self.fp_filter = FalsePositiveFilter(context=self.context, fp_mode=fp_mode)
        self.llm = LLMBridge(config=self.context.config)
        self.llm.init(enable_override=enable_llm_enhancement, results_ref=self._results)

    def set_remote_engine(self, url, token=""): self._remote_engine_url, self._remote_engine_token = url, token

    # ---- 核心编排 ----
    def run_all(self) -> Dict[str, List[RuleCheckResult]]:
        self.executor.scan_deadline = time.time() + SCAN_DEADLINE; self.executor.scan_timed_out = False
        self._telemetry.start_timer(); self.rule_loader.load_all()

        # v4.2: 规则智能裁剪（加载完规则后执行）
        rules = self._get_pruned_rules()

        self._setup_incremental()
        self._setup_incremental_scanner()

        exts = [".py",".js",".ts",".jsx",".tsx",".wxml",".wxss",".json",".html",".css",
                ".scss",".less",".sass",".vue",".java",".go",".rs",".c",".cpp",".cs",
                ".php",".rb",".swift",".kt"]
        if len(self.context.find_files(exts)) > 200:
            heavy = {"AI-SPEC-01","AI-SPEC-02","AI-SPEC-03","AI-SPEC-04","AI-QUAL-01","AI-QUAL-02",
                     "AI-QUAL-03","AI-QUAL-04","DOCCON-001","DOCCON-002","DOCCON-003","DEAD-001","DEAD-002","GH-SEC-001"}
            rules = [r for r in rules if r.id not in heavy]; self.context._MAX_SCAN_FILES = 200
        # v4.6.1: 只预热代码类文件（Python/JS/TS/JSON等规则高频访问的）
        # 文档/报告类文件按需读取，避免大文件预加载拖慢启动
        prefetch_exts = [".py", ".js", ".ts", ".jsx", ".tsx", ".wxml", ".wxss",
                         ".json", ".yaml", ".yml", ".toml", ".ini", ".env", ".conf"]
        self.context.prefetch_all_files(prefetch_exts)
        # v4.6.1: 预计算 AST 摘要（比单纯预解析 AST 树更有用，规则直接查缓存）
        self.context.prefetch_ast_summary()
        # v4.6.1: 预热 JS AST analyzer（Node.js 子进程启动慢，提前启动避免规则执行时阻塞）
        # 多线程并行执行时，多条规则同时首次访问 JSASTAnalyzer 会全部阻塞在初始化上
        # 提前初始化一次，所有规则共享同一个 Node.js 子进程
        # 注意：必须访问 is_available 属性才会真正触发 _ensure_process() 启动 Node.js
        js_files = self.context.find_files([".js", ".ts", ".jsx", ".tsx", ".wxml"])
        if js_files:
            try:
                from core.js_ast_analyzer import get_js_ast_analyzer
                analyzer = get_js_ast_analyzer()
                _ = analyzer.is_available  # 触发 Node.js 子进程启动
            except Exception:
                pass  # JS AST 不可用时降级，不影响主流程

        # v4.6.1: 预热幻觉依赖检测缓存（PyPI/NPM/本地包列表 + 项目import预查）
        # 预热阶段把所有网络/磁盘IO干完，规则执行时100%内存命中，彻底解决多线程卡死问题
        # 10秒预算，超时自动降级为「假设存在」，不影响扫描主流程
        try:
            from rules.common.ai_quality.hallucination import prewarm_hallucination_caches
            prewarm_hallucination_caches(self.context)
        except Exception:
            pass

        # v4.2: 增量模式下，只扫描变化的文件（大幅提速）
        if self._inc_scanner and not self.force_full_scan:
            all_scan_files = self._get_all_scan_files()
            changed_files, unchanged_files = self._inc_scanner.get_changed_files(all_scan_files)
            self._inc_scan_stats.update({
                "total_files": len(all_scan_files),
                "changed_files": len(changed_files),
                "unchanged_files": len(unchanged_files),
            })
            if changed_files and len(changed_files) < len(all_scan_files):
                # 有变化文件且比全量少 → 增量扫描
                # 临时设置增量文件列表，让扫描引擎只扫这些
                orig_incremental_files = self.context.incremental_files
                self.context.incremental_files = set(changed_files)
                try:
                    res = defaultdict(list)
                    self.executor.execute_rules_parallel(rules, res)
                    self.executor.execute_semgrep_rules(res)
                    self.executor.execute_semantic_rules(res)
                finally:
                    self.context.incremental_files = orig_incremental_files
                # 合并未变文件的缓存结果
                self._merge_cached_results(res)
                # 记录本次扫描的文件（缓存更新在后面统一做）
                self._scanned_files_for_update = changed_files
            else:
                # 全量扫描（首次或全部变化）
                res = defaultdict(list)
                self.executor.execute_rules_parallel(rules, res)
                self.executor.execute_semgrep_rules(res)
                self.executor.execute_semantic_rules(res)
                self._inc_scan_stats["mode"] = "full"
                self._scanned_files_for_update = all_scan_files
        else:
            res = defaultdict(list)
            self.executor.execute_rules_parallel(rules, res)
            self.executor.execute_semgrep_rules(res)
            self.executor.execute_semantic_rules(res)
            self._scanned_files_for_update = self._get_all_scan_files()
        if self.enable_deep_diagnosis and self.executor.is_module_applicable("18"):
            try:
                d = self.executor.run_deep_diagnosis()
                if d: res["18"] = [r for r in res.get("18",[]) if r.rule_id=="18.1"] + d
            except Exception as e:
                self.executor.execution_errors.append({"rule_id":"18.0","rule_name":"AI深度诊断","error":str(e),"source":"deep_diagnosis"})
        if self.enable_fp_filter: self.fp_filter.apply_filter(res)
        self.fp_filter.dedup_results(res)

        self._results = res; self.llm._results = self._results
        self.llm.apply_enhancement(getattr(self.context,'project_path',''), getattr(self.context,'backend_path',''))

        # v4.2.1: 统一在FP过滤后、LLM增强后更新增量扫描缓存
        scanned = getattr(self, '_scanned_files_for_update', None)
        if scanned is not None:
            self._update_incremental_cache(res, scanned_files=scanned)

        self._report_telemetry()
        if self.incremental and self._incremental_checker:
            try:
                cf = list(self.context.incremental_files or [])
                if cf: self._incremental_checker.update_cache_after_check(cf)
            except Exception: pass
        self._save_trend(); self._deduct_credits(); return res

    # ---- 委托 ----
    def run_by_module(self, mid): return self.executor.run_by_module(mid)
    def run_by_ids(self, ids): return self.executor.run_by_ids(ids)
    def get_semantic_stats(self): return self.executor.get_semantic_stats()
    def calculate_scores(self, cfg=None): return self.scorer.calculate_scores(self.get_flat_results(), cfg)
    def get_flat_results(self):
        f = []
        for v in self._results.values(): f.extend(v)
        return f
    def get_results_by_level(self, l): return [r for r in self.get_flat_results() if r.level == l]
    def get_results_by_category(self, c): return [r for r in self.get_flat_results() if r.category == c]

    # ---- Properties ----
    @property
    def results(self): return self._results
    @property
    def active_results(self):
        a = defaultdict(list)
        for m, rl in self._results.items(): a[m].extend(r for r in rl if getattr(r,'status','active')=='active')
        return a
    @property
    def fp_results(self):
        f = defaultdict(list)
        for m, rl in self._results.items(): f[m].extend(r for r in rl if getattr(r,'status','active')=='fp')
        return f
    @property
    def total_checks(self): return sum(len(v) for v in self._results.values())
    @property
    def active_checks(self): return sum(1 for r in self.get_flat_results() if getattr(r,'status','active')=='active')
    @property
    def fp_count(self): return sum(1 for r in self.get_flat_results() if getattr(r,'status','active')=='fp')
    @property
    def error_count(self): return sum(1 for r in self.get_flat_results() if normalize_level(r.level)=="error" and getattr(r,'status','active')=='active')
    @property
    def warning_count(self): return sum(1 for r in self.get_flat_results() if normalize_level(r.level)=="warning" and getattr(r,'status','active')=='active')
    @property
    def info_count(self): return sum(1 for r in self.get_flat_results() if normalize_level(r.level)=="info" and getattr(r,'status','active')=='active')
    @property
    def suggestion_count(self):
        """建议类总数 (suggestion + info)，不计入问题、不扣分"""
        from .scoring import _is_suggestion_level
        return sum(1 for r in self.get_flat_results()
                   if _is_suggestion_level(getattr(r,'level','')) and getattr(r,'status','active')=='active')
    @property
    def problem_count(self):
        """真正的代码问题总数 = 阻断 + 警告，即 blocking/error + problem/warning"""
        return self.error_count + self.warning_count
    @property
    def fp_stats(self): return dict(self.fp_filter.fp_stats)
    @property
    def llm_enabled(self): return self.llm.enabled
    @property
    def llm_model_name(self): return self.llm.model_name
    @property
    def llm_fp_count(self): return self.llm.fp_count
    @property
    def llm_fp_results(self): return self.llm.fp_results
    @property
    def llm_stats(self): return self.llm.stats
    @property
    def ai_verification_stats(self): return self.llm.ai_verification_stats

    # ---- v4.2: 规则智能裁剪 ----

    def _get_pruned_rules(self) -> List[Rule]:
        """获取裁剪后的规则列表（REGEX类型）

        v4.2: 如果启用了规则裁剪，则在加载完规则后裁剪；
        否则直接返回原规则（保持向后兼容）。
        """
        raw_rules = self.rule_loader.get_rules_by_project_type(self.context.project_type)

        if not self.enable_rule_pruning:
            return raw_rules

        try:
            from .rule_pruner import RulePruner
            self._rule_pruner = RulePruner(context=self.context)
            pruned = self._rule_pruner.prune(raw_rules)

            # 同时裁剪 semgrep 和 semantic 规则（直接修改rule_loader的内部缓存）
            # 注意：这里用临时裁剪，不修改原loader（保持get_semgrep_rules/get_semantic_rules返回完整结果）
            # 改为在executor层面裁剪
            self._prune_executor_rules()

            return pruned
        except Exception as e:
            logger.warning("[RulePruner] 裁剪失败，回退到全量规则: %s", e)
            return raw_rules

    def _prune_executor_rules(self):
        """在 executor 执行 semgrep/semantic 规则前做裁剪

        通过给 executor 打补丁的方式，在不修改 executor 源码的前提下
        实现 semgrep 和 semantic 规则的裁剪。
        """
        if not self._rule_pruner:
            return

        # 保存原始方法引用
        if not hasattr(self.executor, '_orig_execute_semgrep_rules'):
            self.executor._orig_execute_semgrep_rules = self.executor.execute_semgrep_rules
            self.executor._orig_execute_semantic_rules = self.executor.execute_semantic_rules

        pruner = self._rule_pruner
        orig_semgrep = self.executor._orig_execute_semgrep_rules
        orig_semantic = self.executor._orig_execute_semantic_rules
        loader = self.rule_loader

        def _patched_semgrep(results):
            """先裁剪再执行 semgrep 规则"""
            try:
                all_semgrep = loader.get_semgrep_rules()
                pruned_semgrep = pruner.prune_semgrep_rules(all_semgrep)
                # 临时替换
                orig_list = loader._semgrep_rules
                loader._semgrep_rules = pruned_semgrep
                try:
                    orig_semgrep(results)
                finally:
                    loader._semgrep_rules = orig_list
            except Exception as e:
                logger.warning("[RulePruner] semgrep裁剪执行失败，回退: %s", e)
                orig_semgrep(results)

        def _patched_semantic(results):
            """先裁剪再执行 semantic 规则"""
            try:
                all_semantic = loader.get_semantic_rules()
                pruned_semantic = pruner.prune_semantic_rules(all_semantic)
                # 临时替换
                orig_dict = loader._semantic_rules
                loader._semantic_rules = pruned_semantic
                try:
                    orig_semantic(results)
                finally:
                    loader._semantic_rules = orig_dict
            except Exception as e:
                logger.warning("[RulePruner] semantic裁剪执行失败，回退: %s", e)
                orig_semantic(results)

        # 替换方法
        import types
        self.executor.execute_semgrep_rules = types.MethodType(
            lambda self_, res: _patched_semgrep(res), self.executor)
        self.executor.execute_semantic_rules = types.MethodType(
            lambda self_, res: _patched_semantic(res), self.executor)

    def get_prune_stats(self) -> dict:
        """获取规则裁剪统计信息"""
        if self._rule_pruner:
            return self._rule_pruner.get_prune_stats()
        return {"enabled": self.enable_rule_pruning, "not_applied": True}

    # ---- v4.2: 增量扫描引擎（结果缓存） ----

    def _setup_incremental_scanner(self):
        """初始化增量扫描引擎（v4.2新增）

        与 v3.5 的 _setup_incremental（文件变更检测）不同，
        本引擎提供完整的结果缓存能力。
        """
        if self.force_full_scan or not self.incremental or not self.context.project_path:
            self._inc_scanner = None
            self._inc_scan_stats = {"mode": "full", "reason": "disabled"}
            return

        try:
            from .incremental_scanner import IncrementalScanner
            self._inc_scanner = IncrementalScanner(
                project_path=self.context.project_path,
                rules_dir=getattr(self.rule_loader, 'rules_dir', None),
                enabled=True,
            )
        except Exception as e:
            logger.warning("[IncrementalScanner] 初始化失败: %s", e)
            self._inc_scanner = None
            self._inc_scan_stats = {"mode": "full", "error": str(e)}

    def _get_all_scan_files(self) -> List[str]:
        """获取所有需要扫描的文件路径"""
        exts = [".py", ".js", ".ts", ".jsx", ".tsx", ".wxml", ".wxss",
                ".json", ".html", ".css", ".scss", ".less", ".sass",
                ".vue", ".java", ".go", ".rs", ".c", ".cpp", ".cs",
                ".php", ".rb", ".swift", ".kt"]
        return self.context.find_files(exts)

    def _merge_cached_results(self, results: Dict[str, List[RuleCheckResult]]):
        """将未变文件的缓存结果合并到当前结果中

        v4.2: 从增量扫描缓存中读取未变文件的上次结果，
        合并到本次扫描结果中，保证结果完整性。
        """
        if not self._inc_scanner:
            return

        try:
            all_files = self._get_all_scan_files()
            changed, unchanged = self._inc_scanner.get_changed_files(all_files)

            if not unchanged:
                return  # 没有未变文件，无需合并

            # 获取缓存结果（按模块分组）
            cached_by_module = self._inc_scanner.get_cached_results_by_module(unchanged)

            if not cached_by_module:
                return

            # 将缓存结果转换为 RuleCheckResult 并合并
            merged_count = 0
            for module_id, result_dicts in cached_by_module.items():
                for rd in result_dicts:
                    try:
                        result = RuleCheckResult(
                            rule_id=rd.get("id", rd.get("rule_id", "")),
                            rule_name=rd.get("name", rd.get("rule_name", "")),
                            level=rd.get("level", "problem"),
                            message=rd.get("message", ""),
                            detail=rd.get("detail", ""),
                            fix=rd.get("fix", ""),
                            location=rd.get("location", {}),
                            category=rd.get("category", ""),
                            status=rd.get("status", "active"),
                            fp_reason=rd.get("fp_reason", ""),
                            suggestion_code=rd.get("suggestion_code", ""),
                        )
                        results[module_id].append(result)
                        merged_count += 1
                    except Exception:
                        continue

            self._inc_scan_stats = {
                "mode": "incremental",
                "total_files": len(all_files),
                "changed_files": len(changed),
                "unchanged_files": len(unchanged),
                "cached_results_merged": merged_count,
                "cache_hit_rate": len(unchanged) / len(all_files) if all_files else 0,
            }
            logger.info("[IncrementalScanner] 合并缓存结果: %d 个未变文件, 合并 %d 条结果",
                        len(unchanged), merged_count)

        except Exception as e:
            logger.warning("[IncrementalScanner] 合并缓存结果失败: %s", e)
            self._inc_scan_stats = {"mode": "full", "merge_error": str(e)}

    def _update_incremental_cache(self, results: Dict[str, List[RuleCheckResult]], scanned_files: List[str] = None):
        """更新增量扫描缓存

        v4.2.1: 不再重复调用 get_changed_files（避免hash被覆盖导致缓存不更新）
        直接传入本次实际扫描的文件列表。
        """
        if not self._inc_scanner:
            return

        try:
            if scanned_files is None:
                scanned_files = self._get_all_scan_files()

            if not scanned_files:
                return

            # 更新所有扫描过的文件缓存
            self._inc_scanner.update_cache_from_results(
                results_by_module=results,
                all_scanned_files=scanned_files,
            )

            logger.info("[IncrementalScanner] 缓存已更新: %d 个扫描文件", len(scanned_files))
        except Exception as e:
            logger.warning("[IncrementalScanner] 更新缓存失败: %s", e)

    def get_incremental_scan_stats(self) -> dict:
        """获取增量扫描统计信息"""
        if self._inc_scanner:
            base = self._inc_scanner.get_stats()
            base.update(self._inc_scan_stats)
            return base
        return dict(self._inc_scan_stats) if self._inc_scan_stats else {"mode": "full"}

    # ---- 编排辅助 ----
    def _setup_incremental(self):
        if not self.incremental or not self.context.project_path: return
        try:
            from .incremental import get_incremental_checker
            self._incremental_checker = get_incremental_checker(self.context.project_path, enabled=True)
            af = self.context.find_files([".py",".js",".ts",".jsx",".tsx",".wxml",".wxss",".json",".html",".css",".vue"])
            ch, tot, mode = self._incremental_checker.get_changed_files(af)
            self.context.incremental_files = set(ch) if ch else set()
            self._incremental_stats = {"mode":mode,"total":tot,"checked":len(ch)}
        except Exception: self.incremental = False; self._incremental_stats = {"mode":"full","total":0,"checked":0}

    def _report_telemetry(self):
        try:
            if not self._telemetry.should_report(): return
            tid = set()
            for mr in self._results.values():
                for r in mr:
                    if getattr(r,'status','active')=='active' and r.rule_id: tid.add(r.rule_id)
            self._telemetry.report_on_finish(project_type=self.context.project_type,
                total_rules_loaded=len(self.rule_loader.all_rules), triggered_rule_ids=sorted(tid),
                blocking_count=self.error_count, warning_count=self.warning_count,
                info_count=self.info_count, total_score=self.calculate_scores().get('total',0), engine_mode="new")
        except Exception: pass

    def _save_trend(self):
        if not self.context.project_path: return
        try:
            from .trend_tracker import get_trend_tracker
            get_trend_tracker(self.context.project_path).save_snapshot(
                scores=self.calculate_scores(),
                issue_stats={"total":self.active_checks,"errors":self.error_count,"warnings":self.warning_count,
                             "infos":self.info_count,"fp_count":self.fp_count},
                project_type=self.context.project_type, incremental_info=getattr(self,'_incremental_stats',None))
        except Exception: pass

    def _deduct_credits(self):
        _deduct_credits(self.context, self._results,
                        getattr(self,'_user_email',''), getattr(self,'_menfang_url',''), getattr(self,'_menfang_token',''))
