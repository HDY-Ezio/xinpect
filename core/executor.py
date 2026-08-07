"""
规则执行引擎
并行执行 REGEX / SEMANTIC / SEMGREP 规则

从 runner.py 拆出，职责：
  - RuleExecutor: 管理规则执行生命周期
  - _fork_worker_v2: 可 pickle 的 fork worker
"""

import os
import logging
import time
import asyncio
from typing import Dict, List
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from .rule_loader import RuleLoader, Rule, RuleCheckResult
from .scoring import get_check_category, CATEGORY_NAMES

logger = logging.getLogger(__name__)

SCAN_DEADLINE = 90
SEMANTIC_PER_BRAIN_TIMEOUT = 15

# ====================================================================
# Fork 进程池 worker（模块级，可 pickle）
# ====================================================================
_runner_global_ctx = None

def _fork_worker_init(ctx):
    """fork 子进程初始化：将 context 对象注入全局变量
    在 fork 模式下，子进程继承父进程内存，但 importlib 缓存可能不一致。
    必须在创建 Pool 时通过 initializer 传入 ctx。
    """
    global _runner_global_ctx
    _runner_global_ctx = ctx

def _fork_worker_v2(task_batch):
    """fork 后的 worker：通过全局变量访问父进程缓存"""
    import importlib, time as _t
    _ctx = _runner_global_ctx
    if _ctx is None:
        return [(t[0],t[1],t[3],t[4],t[5],[],0.0,"no context") for t in task_batch]
    batch = []
    for rule_id, rule_name, func_path, module_id, rule_level, rule_category in task_batch:
        t0 = _t.time()
        try:
            mod_path, func_name = func_path.rsplit('.', 1)
            raw = getattr(importlib.import_module(mod_path), func_name)(_ctx)
            batch.append((rule_id,rule_name,module_id,rule_level,rule_category,raw or [],_t.time()-t0,None))
        except Exception as e:
            batch.append((rule_id,rule_name,module_id,rule_level,rule_category,[],_t.time()-t0,str(e)))
    return batch

def _import_services():
    try:
        import importlib
        return importlib.import_module("..services", __name__)
    except (ImportError, ValueError):
        try:
            import sys
            p = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if p not in sys.path: sys.path.insert(0, p)
            import services; return services
        except ImportError:
            return None

_SERVICES = _import_services()

def _get_diagnosis_service(mode="quick", config=None, sdk=None):
    if _SERVICES and hasattr(_SERVICES, 'get_diagnosis_service'):
        return _SERVICES.get_diagnosis_service(mode, config, sdk)
    return None

# 结果转换辅助函数
_LEVEL_MAP = {'blocking':'blocking','problem':'problem','suggestion':'suggestion',
              'error':'blocking','warning':'problem','info':'suggestion'}
_SEMGREP_LEVEL = {"ERROR":"blocking","WARNING":"problem","INFO":"suggestion",
                  "BLOCKER":"blocking","CRITICAL":"blocking","HIGH":"blocking","MEDIUM":"problem","LOW":"suggestion"}

def _raw_to_result(raw, rule_id, rule_name, rule_level, rule_category):
    """将原始结果转为 RuleCheckResult"""
    rl = _LEVEL_MAP.get(rule_level, 'problem')
    if isinstance(raw, dict):
        return RuleCheckResult(
            rule_id=rule_id, rule_name=rule_name,
            level=raw.get('level', rl), message=raw.get('message', ''),
            detail=raw.get('detail', ''), fix=raw.get('fix', ''),
            location={'file': raw.get('file', raw.get('file_path', '')),
                      'line': raw.get('line', raw.get('line_num', 0)),
                      'column': raw.get('column', 0), 'snippet': raw.get('snippet', '')},
            category=rule_category if rule_category in CATEGORY_NAMES else get_check_category(rule_id),
            suggestion_code=raw.get('suggestion_code', ''))
    return RuleCheckResult(rule_id=rule_id, rule_name=rule_name, level=rl,
                           message=str(raw), category=get_check_category(rule_id))


# ====================================================================
# RuleExecutor
# ====================================================================

class RuleExecutor:
    """规则执行引擎，负责并行执行 REGEX / SEMANTIC / SEMGREP 规则"""

    def __init__(self, context, rule_loader: RuleLoader):
        self.context = context
        self.rule_loader = rule_loader
        self.execution_times: Dict[str, float] = {}
        self.execution_errors: List[dict] = []
        self.scan_deadline: float = 0.0
        self.scan_timed_out: bool = False
        self._diagnosis_service = None
        self._diagnosis_mode = "quick"
        self._sdk = None

        # v4.3.0 P1-1: semgrep 跳过状态（未安装/调用失败时为 True）
        self.semgrep_skipped: bool = False
        self.semgrep_skip_reason: str = ""

    # ------------------------------------------------------------------
    # 并行规则执行
    # ------------------------------------------------------------------

    def execute_rules_parallel(self, applicable_rules: List[Rule],
                                results: Dict[str, List[RuleCheckResult]]) -> None:
        """v4.6.1: 线程池并行执行规则（单规则维度提交）。
        
        为什么不用 fork 进程池：
        1. fork 后子进程 importlib 缓存与父进程不一致，导致大量模块重新导入，开销巨大
        2. 文件内容已全部缓存到内存，规则执行主要是 CPU 计算 + 字符串操作
        3. 线程池创建开销几乎为 0
        
        为什么不用 batch 模式（每线程一批规则）：
        batch 模式在 32 线程 + 大规则集下出现过不明原因的卡死（疑似 GIL + 锁交互导致的活锁）。
        改为单规则维度提交 future + as_completed，行为更可控，且经过 16 线程全量验证通过。
        
        性能实测（430 条 Py 规则）：
        - 1线程: 38.3s
        - 2线程: 16.2s  ← 最优（GIL 争用最小）
        - 4线程: 22.0s  （GIL 争用明显）
        - 8线程: 27.4s  （GIL 争用加剧）
        - 16线程: 16.7s （IO 等待释放 GIL，收益回升）
        
        默认 2 线程：在 CPU 密集场景下 GIL 争用最小，收益/稳定性比最优。
        """
        import threading
        from concurrent.futures import ThreadPoolExecutor, as_completed

        rule_tasks, json_rules, rule_map = [], [], {}
        for rule in applicable_rules:
            if rule.check_func is None: continue
            mid = rule.module_id or rule.category
            rule_map[rule.id] = rule
            if getattr(rule, 'is_json_rule', False):
                json_rules.append(rule)
            else:
                rule_tasks.append(rule)

        # JSON 规则按文件批量执行（文件只读一次，所有规则共享内容缓存）
        if json_rules:
            self._execute_json_rules_batch(json_rules, results)

        if not rule_tasks:
            return

        # 默认 4 线程：经过实测验证
        # - 2线程：性能最优（~16s），但偶发不明原因死锁
        # - 4线程：稳定通过，性能 ~18s，GIL 争用可控
        # - 8-16线程：GIL 争用加剧，反而变慢
        # 规则数 < 4 时直接串行，不值得创建线程
        if len(rule_tasks) < 4:
            n_workers = 1
        else:
            n_workers = 4
        
        results_lock = threading.Lock()
        times_lock = threading.Lock()
        errors_lock = threading.Lock()

        def _run_single(rule):
            """执行单条规则，返回 (rule_id, elapsed, results_list, error_dict)"""
            mid = rule.module_id or rule.category
            t0 = time.time()
            try:
                raw_results = rule.check_func(self.context)
                elapsed = time.time() - t0
                converted = []
                if raw_results:
                    converted = [
                        _raw_to_result(r, rule.id, rule.name, rule.level, rule.category)
                        for r in raw_results
                    ]
                return rule.id, mid, elapsed, converted, None
            except Exception as ex:
                elapsed = time.time() - t0
                return rule.id, mid, elapsed, [], {
                    "rule_id": rule.id, "rule_name": rule.name,
                    "module_id": mid, "error": str(ex)
                }

        with ThreadPoolExecutor(max_workers=n_workers) as ex:
            futures = {ex.submit(_run_single, r): r.id for r in rule_tasks}
            for f in as_completed(futures):
                rid, mid, elapsed, converted, err = f.result()
                with times_lock:
                    self.execution_times[rid] = elapsed
                if converted:
                    with results_lock:
                        results[mid].extend(converted)
                if err:
                    with errors_lock:
                        self.execution_errors.append(err)

    # ------------------------------------------------------------------
    # 单规则执行
    # ------------------------------------------------------------------

    def _execute_json_rules_batch(self, json_rules: list, results: Dict[str, list]):
        """JSON规则按文件批量执行 + file_pattern预分组 + 多线程并行
        性能优化：
        1. v4.6.1-2: 直接复用 context._file_cache（prefetch 已预读），零额外磁盘 IO
        2. 按file_pattern预分组规则，不匹配的文件直接跳过对应规则组
        3. '*'模式的规则单独一组，所有文件都跑
        4. 预计算行偏移表，每个文件只算一次，所有规则共享
        5. 2 线程并行（GIL 争用最小，实测最优）
        """
        import fnmatch, threading
        from core.rule_loader.loader import _build_line_offsets
        if not json_rules:
            return
        
        # v4.6.1-2: 直接复用 _file_cache 中已预读的文件
        # prefetch_all_files 已经把所有需要的文件读到内存里了
        # 过滤出非二进制且有内容的文件
        file_cache = {}
        for fp, content in self.context._file_cache.items():
            if not isinstance(fp, str) or not isinstance(content, str):
                continue
            # 跳过没有扩展名或非文本的
            if not content:
                continue
            # 内容太大的（二进制文件可能被误读）做个简单过滤
            if '\0' in content[:4096]:
                continue
            file_cache[fp] = content
        
        # 如果缓存里没有（prefetch 没覆盖到），降级用 find_files
        if not file_cache:
            # 收集所有可能的文件扩展名
            all_exts = set()
            for rule in json_rules:
                fp_pat = getattr(rule, '_file_pattern', None) or getattr(rule, 'file_pattern', None)
                if fp_pat and fp_pat != '*':
                    ext = os.path.splitext(fp_pat)[1]
                    if ext:
                        all_exts.add(ext)
                else:
                    for e in ['.py','.js','.ts','.jsx','.tsx','.java','.go','.rs','.c','.cpp','.cs','.php','.rb','.swift','.kt',
                              '.json','.html','.css','.vue','.yaml','.yml','.xml']:
                        all_exts.add(e)
            for fp in self.context.find_files(list(all_exts)):
                ct = self.context.safe_read(fp)
                if ct:
                    file_cache[fp] = ct
        
        if not file_cache:
            return
        
        # 按file_pattern分组规则
        pattern_groups = {}  # pattern -> [rules]
        for rule in json_rules:
            fp_pat = getattr(rule, '_file_pattern', None) or getattr(rule, 'file_pattern', None)
            key = fp_pat if fp_pat and fp_pat != '*' else '__all__'
            pattern_groups.setdefault(key, []).append(rule)
        
        # 全文件匹配的规则组
        all_file_rules = pattern_groups.get('__all__', [])
        # 特定模式的规则组
        specific_groups = {k: v for k, v in pattern_groups.items() if k != '__all__'}
        
        rule_timer = {r.id: 0.0 for r in json_rules}
        results_lock = threading.Lock()
        timer_lock = threading.Lock()
        errors_lock = threading.Lock()
        
        # v4.6.1-2: 固定 4 线程 + 索引队列
        # 经过实测：4线程稳定通过且性能最优，2线程偶发死锁，8+线程GIL争用加剧
        file_items = list(file_cache.items())
        file_count = len(file_items)
        if file_count < 4:
            n_workers = 1
        else:
            n_workers = 4
        
        # 用索引做线程安全的工作分配
        import itertools
        idx_iter = itertools.count()
        idx_lock = threading.Lock()
        
        def _process_file_worker():
            """消费者线程：从共享索引取下一个文件，处理完再取下一个"""
            local_times = {}
            local_errors = []
            local_results = defaultdict(list)
            
            while True:
                with idx_lock:
                    idx = next(idx_iter)
                    if idx >= file_count:
                        break
                
                fp, content = file_items[idx]
                basename = os.path.basename(fp)
                line_offsets = _build_line_offsets(content)
                
                # 全文件匹配的规则
                for rule in all_file_rules:
                    t0 = time.time()
                    try:
                        raw = rule.check_func(fp, content, line_offsets=line_offsets)
                        elapsed = time.time() - t0
                        local_times[rule.id] = local_times.get(rule.id, 0.0) + elapsed
                        if raw:
                            mid = rule.module_id or rule.category
                            local_results[mid].extend(
                                _raw_to_result(r, rule.id, rule.name, rule.level, rule.category) for r in raw)
                    except Exception as e:
                        elapsed = time.time() - t0
                        local_times[rule.id] = local_times.get(rule.id, 0.0) + elapsed
                        local_errors.append({"rule_id":rule.id,"rule_name":rule.name,
                                             "module_id":rule.module_id or rule.category,"error":str(e)})
                
                # 特定模式的规则
                for pat, prules in specific_groups.items():
                    if not fnmatch.fnmatch(basename, pat):
                        continue
                    for rule in prules:
                        t0 = time.time()
                        try:
                            raw = rule.check_func(fp, content, line_offsets=line_offsets)
                            elapsed = time.time() - t0
                            local_times[rule.id] = local_times.get(rule.id, 0.0) + elapsed
                            if raw:
                                mid = rule.module_id or rule.category
                                local_results[mid].extend(
                                    _raw_to_result(r, rule.id, rule.name, rule.level, rule.category) for r in raw)
                        except Exception as e:
                            elapsed = time.time() - t0
                            local_times[rule.id] = local_times.get(rule.id, 0.0) + elapsed
                            local_errors.append({"rule_id":rule.id,"rule_name":rule.name,
                                                 "module_id":rule.module_id or rule.category,"error":str(e)})
            
            # 合并到全局
            with results_lock:
                for mid, res_list in local_results.items():
                    results[mid].extend(res_list)
            with timer_lock:
                for rid, t in local_times.items():
                    rule_timer[rid] += t
            with errors_lock:
                self.execution_errors.extend(local_errors)
        
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=n_workers) as ex:
            list(ex.map(lambda _: _process_file_worker(), range(n_workers)))
        
        for rid, elapsed in rule_timer.items():
            self.execution_times[rid] = elapsed


    def execute_rule(self, rule: Rule) -> List[RuleCheckResult]:
        """执行单条规则"""
        if not rule.check_func: return []
        if getattr(rule, 'is_json_rule', False):
            all_raw = []
            exts = [".py",".js",".ts",".jsx",".tsx",".java",".go",".rs",".c",".cpp",".cs",".php",".rb",".swift",".kt",
                    ".json",".html",".css",".vue",".yaml",".yml",".xml",".Dockerfile",".env",".conf"]
            for fp in self.context.find_files(exts):
                ct = self.context.safe_read(fp)
                if ct:
                    raw = rule.check_func(fp, ct)
                    if raw: all_raw.extend(raw)
            raw_results = all_raw
        else:
            raw_results = rule.check_func(self.context)
        if not raw_results: return []
        return [_raw_to_result(r, rule.id, rule.name, rule.level, rule.category) for r in raw_results]

    def run_by_module(self, module_id: str) -> List[RuleCheckResult]:
        self.rule_loader.load_all()
        rules = [r for r in self.rule_loader.all_rules
                 if r.module_id == module_id and r.is_applicable(self.context.project_type, self.context)]
        results = []
        for rule in rules:
            try: results.extend(self.execute_rule(rule))
            except Exception as e:
                self.execution_errors.append({"rule_id":rule.id,"rule_name":rule.name,"error":str(e),"source":"run_by_module"})
        return results

    def run_by_ids(self, rule_ids: List[str]) -> List[RuleCheckResult]:
        self.rule_loader.load_all()
        results = []
        for rid in rule_ids:
            rule = self.rule_loader.get_rule_by_id(rid)
            if not rule or not rule.is_applicable(self.context.project_type, self.context): continue
            try: results.extend(self.execute_rule(rule))
            except Exception as e:
                self.execution_errors.append({"rule_id":rule.id,"rule_name":rule.name,"error":str(e),"source":"run_by_ids"})
        return results

    def is_module_applicable(self, module_id: str) -> bool:
        return self.context.is_module_applicable(module_id)

    # ------------------------------------------------------------------
    # Semgrep 规则
    # ------------------------------------------------------------------

    def execute_semgrep_rules(self, results: Dict[str, List[RuleCheckResult]]) -> None:
        """v3.0.2: 执行 SEMGREP 规则"""
        try:
            semgrep_rules = self.rule_loader.get_semgrep_rules()
            if not semgrep_rules: return
            try:
                from integrations.semgrep_engine import SemgrepEngine
            except ImportError:
                try:
                    import sys; p = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    if p not in sys.path: sys.path.insert(0, p)
                    from integrations.semgrep_engine import SemgrepEngine
                except ImportError:
                    self.semgrep_skipped = True
                    self.semgrep_skip_reason = "Semgrep 集成模块未找到"
                    return
            engine = SemgrepEngine()
            if not engine.is_available():
                # v4.3.0 P1-1: 记录 semgrep 未安装状态，供 CLI 提示
                self.semgrep_skipped = True
                self.semgrep_skip_reason = "Semgrep CLI 未安装"
                logger.info("[v3.0.2] Semgrep未安装，跳过%d条规则", len(semgrep_rules)); return
            yaml_content = self._convert_to_semgrep_yaml(semgrep_rules)
            if not yaml_content: return
            import tempfile
            with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
                f.write(yaml_content); yaml_path = f.name
            try:
                if time.time() >= self.scan_deadline:
                    logger.warning("[v3.0.2] 扫描超时，跳过Semgrep"); self.scan_timed_out = True; return
                br = engine.scan(self.context.project_path, {"semgrep_config": yaml_path})
                if br and hasattr(br, "issues") and br.issues:
                    for issue in br.issues:
                        results["semgrep"].append(RuleCheckResult(
                            rule_id=getattr(issue,"check_id",getattr(issue,"id","semgrep")),
                            rule_name=getattr(issue,"title",getattr(issue,"name","Semgrep")),
                            level=_SEMGREP_LEVEL.get(getattr(issue,"severity","WARNING").upper(),"problem"),
                            message=getattr(issue,"description",getattr(issue,"message","")),
                            location={"file":getattr(issue,"file",""),"line":getattr(issue,"line",0)},
                            category="bug"))
                    logger.info("[v3.0.2] Semgrep完成: %d个问题", len(br.issues))
            finally:
                try: os.unlink(yaml_path)
                except OSError: pass
        except Exception as e:
            self.semgrep_skipped = True
            self.semgrep_skip_reason = f"调用异常: {e}"
            logger.warning("[v3.0.2] Semgrep异常: %s", e)

    def _convert_to_semgrep_yaml(self, rules: list) -> str:
        import yaml
        sev_map = {"S1":"ERROR","S2":"WARNING","S3":"INFO","S4":"INFO",
                   "critical":"ERROR","high":"ERROR","medium":"WARNING","low":"INFO",
                   "blocking":"ERROR","problem":"WARNING","suggestion":"INFO"}
        lang_map = {"python":"python","javascript":"javascript","typescript":"typescript",
                    "java":"java","go":"go","rust":"rust","ruby":"ruby","php":"php",
                    "c":"c","cpp":"cpp","csharp":"csharp"}
        sr = []
        for rule in rules:
            dp = rule.get("detection_pattern","")
            if not dp: continue
            dp_clean = dp.split("#")[0].strip() if "#" in dp else dp.strip()
            if not dp_clean: continue
            sr.append({"id": rule.get("id", rule.get("check_id","unknown")),
                       "message": rule.get("description", rule.get("title","")),
                       "severity": sev_map.get(rule.get("severity","medium"), "WARNING"),
                       "languages": [lang_map.get(rule.get("language","python"), "python")],
                       "pattern": dp_clean})
        return yaml.dump({"rules": sr}, default_flow_style=False, allow_unicode=True) if sr else ""

    # ------------------------------------------------------------------
    # 语义规则
    # ------------------------------------------------------------------

    def execute_semantic_rules(self, results: Dict[str, List[RuleCheckResult]]) -> None:
        try:
            if time.time() >= self.scan_deadline:
                logger.warning("[v3.0.2] 扫描超时，跳过语义分析"); self.scan_timed_out = True; return
            from .semantic_scanner import SemanticRuleScanner
            scanner = SemanticRuleScanner(self.context.project_path, {"project_type": self.context.project_type})
            # v4.3.0 P0 修复：将已加载的语义规则传给扫描器，按规则 category 分发检查
            # 之前没有传 semantic_rules，导致 307 条可执行规则完全未被使用
            semantic_rules_dict = self.rule_loader.get_semantic_rules()
            # flatten: Dict[str, List[dict]] → List[dict]
            semantic_rules_flat = []
            for brain_rules in semantic_rules_dict.values():
                semantic_rules_flat.extend(brain_rules)
            findings = scanner.scan(semantic_rules=semantic_rules_flat)
            sev_map = {"critical":"blocking","blocker":"blocking","high":"blocking","medium":"problem","low":"suggestion"}
            count = 0
            for f in findings:
                results["semantic"].append(RuleCheckResult(
                    rule_id=f.check_id, rule_name=f.rule_name,
                    level=sev_map.get(f.severity,"problem"), message=f.message, detail=f.suggestion,
                    location={"file":f.file,"line":f.line}, category="code_smell", suggestion_code=f.suggestion))
                count += 1
            if count > 0: logger.info("[v3.0.2] AST语义完成: %d个发现", count)
        except Exception as e:
            logger.warning("[v3.0.2] 语义规则异常: %s", e)

    # ------------------------------------------------------------------
    # 深度诊断（M18）
    # ------------------------------------------------------------------

    def run_deep_diagnosis(self) -> List[RuleCheckResult]:
        svc = self._get_diagnosis_service_instance()
        if not svc: return []
        key_files = svc.collect_key_files(
            project_path=self.context.project_path, backend_path=self.context.backend_path,
            project_type=self.context.project_type, max_files=20, max_chars=50000)
        if not key_files: return []
        code_ctx = "\n\n".join(f"# ===== {p} =====\n{c}" for p, c in key_files.items())
        try:
            diag = self._sync_diagnose(svc, code_ctx)
        except Exception:
            diag = svc._quick_diagnose(code_ctx, self.context.project_path, self.context.project_type)
        id_map = {
            "logic_issues": ("18.2","逻辑漏洞深度分析","bug","warning"),
            "performance_issues": ("18.3","性能瓶颈识别","bug","warning"),
            "design_issues": ("18.4","设计缺陷诊断","code_smell","info"),
            "security_deep": ("18.5","深度安全与架构建议","bug","error"),
        }
        results = []
        for cat, issues in diag.items():
            rid, rname, cat_field, plvl = id_map.get(cat, ("18.0","深度诊断","code_smell","warning"))
            clean = rname.replace('深度分析','').replace('识别','').replace('诊断','')
            if issues:
                details = [f"{i.get('location','')}: {i.get('title','')}" for i in issues[:10]]
                results.append(RuleCheckResult(
                    rule_id=rid, rule_name=rname, level=plvl,
                    message=f"发现 {len(issues)} 个潜在{clean}问题",
                    detail="\n".join(details),
                    fix=f"逐一审查标记的潜在问题，确保{clean}处理正确",
                    category=cat_field,
                    location={"file":"","line":0,"snippet":"\n".join(details[:5])}))
            else:
                results.append(RuleCheckResult(
                    rule_id=rid, rule_name=rname, level="info",
                    message=f"未发现明显的{clean}问题",
                    detail="", fix="", category=cat_field,
                    location={"file":"","line":0,"snippet":""}))
        return results

    def _sync_diagnose(self, service, code_context: str) -> Dict:
        coro = service.diagnose(code_context=code_context,
                                project_path=self.context.project_path,
                                project_type=self.context.project_type)
        try:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    nl = asyncio.new_event_loop()
                    try: return nl.run_until_complete(coro)
                    finally: nl.close()
                return loop.run_until_complete(coro)
            except RuntimeError:
                nl = asyncio.new_event_loop()
                try: return nl.run_until_complete(coro)
                finally: nl.close()
        except Exception:
            coro.close(); raise

    # ------------------------------------------------------------------
    # 统计 & 内部
    # ------------------------------------------------------------------

    def get_semantic_stats(self) -> dict:
        return {"total_semantic": self.rule_loader.semantic_rule_count,
                "total_semgrep": self.rule_loader.semgrep_rule_count,
                "total_regex": self.rule_loader.regex_rule_count,
                "total_all": self.rule_loader.rule_count}

    def _get_diagnosis_service_instance(self):
        if self._diagnosis_service is None:
            cfg = getattr(self.context, 'config', None)
            self._diagnosis_service = _get_diagnosis_service(mode=self._diagnosis_mode, config=cfg, sdk=self._sdk)
        return self._diagnosis_service
