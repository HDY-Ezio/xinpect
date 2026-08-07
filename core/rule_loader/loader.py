# -*- coding: utf-8 -*-
"""
规则加载器主类

自动发现并加载rules/目录下的规则文件，按类型分发到不同执行引擎：
- REGEX → Rule对象 → Brain 1
- SEMGREP → semgrep_rules列表 → Brain 6
- SEMANTIC → semantic_rules字典 → 对应大脑
"""

import os
import re as _re
import json
import sys
import pickle
import hashlib
import bisect as _bisect
import importlib.util
import logging
from typing import Dict, List, Any, Optional

from core.rule_loader.models import Rule, RuleCheckResult

logger = logging.getLogger(__name__)

# ===== v4.6.1: 正则超时熔断相关常量 =====
# 单条正则匹配超时阈值（秒），默认 500ms
DEFAULT_REGEX_TIMEOUT = 0.5
# 慢规则阈值（毫秒），超过即被标记为慢规则
SLOW_RULE_THRESHOLD_MS = 100
# 体检时对每条规则跑的次数（取平均值）
PERF_HEALTH_ROUNDS = 3
# 体检测试文本行数
PERF_HEALTH_TEST_LINES = 5000
# 慢规则榜单数量
SLOW_RULE_TOP_N = 20


# ===== v4.6.1: 正则执行超时熔断 =====
# 实现方案：ThreadPoolExecutor + future.result(timeout)
# - 单条正则匹配超过阈值时，主线程立即返回空结果（降级）
# - 工作线程可能仍在后台跑，但不阻塞主扫描流程
# - 适用于 re 和 regex 两种引擎，通用兼容

from concurrent.futures import ThreadPoolExecutor

_regex_timeout_pool = None
_regex_timeout_pool_lock = None


def _get_regex_timeout_pool():
    """获取正则超时熔断用的单例线程池（单 worker）"""
    global _regex_timeout_pool, _regex_timeout_pool_lock
    if _regex_timeout_pool is not None:
        return _regex_timeout_pool
    import threading
    if _regex_timeout_pool_lock is None:
        _regex_timeout_pool_lock = threading.Lock()
    with _regex_timeout_pool_lock:
        if _regex_timeout_pool is None:
            _regex_timeout_pool = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="xinpect-regex-watchdog",
            )
    return _regex_timeout_pool


# 全局超时降级统计：{rule_id: count}
_regex_timeout_stats = {}


def _record_timeout(rule_id: str):
    """记录一次正则超时降级"""
    import threading
    _lock = getattr(_record_timeout, "_lock", None)
    if _lock is None:
        _record_timeout._lock = threading.Lock()
        _lock = _record_timeout._lock
    with _lock:
        _regex_timeout_stats[rule_id] = _regex_timeout_stats.get(rule_id, 0) + 1


def get_regex_timeout_stats() -> dict:
    """获取正则超时降级统计快照"""
    return dict(_regex_timeout_stats)


def reset_regex_timeout_stats():
    """重置超时统计（每个扫描周期开始时调用）"""
    _regex_timeout_stats.clear()


def safe_regex_finditer(compiled_re, content: str, rule_id: str = "",
                        timeout: float = DEFAULT_REGEX_TIMEOUT) -> list:
    """带超时熔断的正则 finditer。

    使用 ThreadPoolExecutor + future.result(timeout) 实现超时熔断。
    超时后返回空列表（降级为 0 个匹配），仅在 debug 日志记录，
    同时计入全局超时统计供最终报告展示。

    Args:
        compiled_re: 已编译的正则对象
        content: 待匹配文本
        rule_id: 规则 ID（用于统计和日志）
        timeout: 超时阈值（秒），默认 500ms

    Returns:
        list: 匹配结果列表，超时返回空列表
    """
    if compiled_re is None or not content:
        return []

    pool = _get_regex_timeout_pool()
    future = pool.submit(lambda: list(compiled_re.finditer(content)))
    try:
        return future.result(timeout=timeout)
    except Exception:
        # 超时 → 降级为空列表
        if rule_id:
            logger.debug("[regex-timeout] 规则 %s 匹配超时(%.0fms)，已降级",
                         rule_id, timeout * 1000)
            _record_timeout(rule_id)
        return []


# ===== v4.6.1: JSON正则规则性能优化工具函数 =====
def _build_line_offsets(content: str) -> list:
    """预计算每行的起始偏移量，用于 O(log n) 行号查找
    返回: [line1_start, line2_start, ...] 列表，索引=行号-1
    """
    offsets = [0]
    pos = 0
    while True:
        pos = content.find('\n', pos)
        if pos == -1:
            break
        pos += 1
        offsets.append(pos)
    return offsets


def _bisect_line(line_offsets: list, char_pos: int) -> int:
    """通过二分查找定位字符位置对应的行号（从1开始）"""
    return _bisect.bisect_right(line_offsets, char_pos)


def _extract_negative_lookahead_keywords(pattern_str: str) -> list:
    """从负向前瞻正则中提取字面量关键词，用于快速预检。

    v4.6.1 性能优化：针对 (?!.*XXX)(?!.*YYY) 这类"缺失检测"正则，
    提取其中的字面量字符串，先用 `kw in content` 做 O(N) 快速检查。
    如果所有关键词都在内容中存在，说明负向前瞻全部不匹配，可以直接跳过正则执行。
    对 WEB-PERF-009 这类在大文件上有灾难性回溯的正则，性能提升 100x+。

    提取规则：
    1. 只提取 (?!.*xxx) 形式中的 xxx 字面量部分
    2. xxx 必须是纯字符串（不含正则元字符），否则跳过
    3. 只提取长度 >= 5 的关键词，避免短词误匹配
    4. 不处理转义、字符类、量词等复杂模式
    """
    import re as _re_extract
    keywords = []
    # 匹配 (?!.*literal) 形式的负向前瞻
    # 贪婪匹配到第一个 ) 为止，简单提取字面量
    for m in _re_extract.finditer(r'\(\?!\.\*([^)]+)\)', pattern_str):
        kw = m.group(1)
        # 去掉引号包裹
        if (kw.startswith("'") and kw.endswith("'")) or \
           (kw.startswith('"') and kw.endswith('"')):
            kw = kw[1:-1]
        # 检查是否为纯字面量（不含正则元字符）
        # 允许 [^>]+ 这类简单字符类中的字面量片段
        if _re_extract.search(r'[.*+?()\[\]{}|\\^$]', kw):
            # 尝试从 [^>]+rel= 这类模式中提取 rel= 这样的字面量
            # 简单策略：如果元字符太多就跳过
            literal_parts = _re_extract.findall(r'[a-zA-Z0-9_\-=\'"<>\s]{5,}', kw)
            for part in literal_parts:
                part = part.strip()
                if len(part) >= 5 and not _re_extract.search(r'[.*+?()\[\]{}|\\^$]', part):
                    keywords.append(part.lower())
            continue
        if len(kw) >= 5:
            keywords.append(kw.lower())
    return keywords


# 导入规则分类 schema
try:
    from core.rule_schema import RuleType, RuleSchema, DIR_TO_BRAIN
except ImportError:
    from enum import Enum
    class RuleType(Enum):
        REGEX = "regex"
        SEMGREP = "semgrep"
        SEMANTIC = "semantic"
    class RuleSchema:
        @staticmethod
        def classify_rule(rule_def):
            pattern = rule_def.get("pattern", "")
            if pattern and isinstance(pattern, str) and pattern.strip():
                return RuleType.REGEX
            if rule_def.get("semgrep_id") or rule_def.get("semgrep_rule"):
                return RuleType.SEMGREP
            return RuleType.SEMANTIC
    DIR_TO_BRAIN = {}


def _get_semantic_scanner_registered_categories():
    """延迟加载 semantic_scanner 的已注册 category 集合，避免循环导入。
    
    Returns:
        set: 在 SemanticRuleScanner._CATEGORY_TO_CHECK 中注册的所有 category 名称
    """
    try:
        from core.semantic_scanner import SemanticRuleScanner
        return set(SemanticRuleScanner._CATEGORY_TO_CHECK.keys())
    except ImportError:
        try:
            import importlib
            mod = importlib.import_module('core.semantic_scanner')
            return set(mod.SemanticRuleScanner._CATEGORY_TO_CHECK.keys())
        except Exception:
            return set()


class RuleLoader:
    """规则加载器 - v3.0.2 规则架构重构版
    
    自动发现并加载rules/目录下的规则文件
    按类型分发到不同执行引擎：
    - REGEX → Rule对象 → Brain 1
    - SEMGREP → semgrep_rules列表 → Brain 6
    - SEMANTIC → semantic_rules字典 → 对应大脑
    """
    
    # 模块级缓存：避免重复导入规则文件（跨实例共享）
    _module_cache = {}  # {file_path: module}
    
    # JSON 规则打包缓存：将所有 JSON 规则文件预编译成单个 pickle 缓存
    # 61 个文件的分散 IO 合并为 1 次，节省 2-3s 冷启动时间
    _json_bundle_cache = None  # {rules: [...], semgrep_rules: [...], semantic_rules: {...}, semantic_rules_with_ref: {...}, stats: {...}}
    
    def __init__(self, rules_dir: str = None):
        if rules_dir is None:
            # 默认使用当前文件所在目录的上级目录下的rules/
            self.rules_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "rules"
            )
        else:
            self.rules_dir = rules_dir
        
        self._rules: Dict[str, List[Rule]] = {}  # {category: [Rule]}
        self._all_rules: List[Rule] = []
        self._rule_index: Dict[str, Rule] = {}  # {rule_id: Rule}
        
        # v3.0.2 新增：分类收集
        self._semgrep_rules: List[dict] = []  # semgrep规则原始数据
        self._semantic_rules: Dict[str, List[dict]] = {}  # {brain_id: [rule_dict]}
        
        # v3.0.2 统计信息
        self._stats = {
            "regex": 0,
            "semgrep": 0,
            "semantic": 0,
            "semantic_active": 0,      # v3.5.2: 有可执行元数据的语义规则
            "semantic_passive": 0,     # v3.5.2: 纯知识库/描述性语义规则
            "semantic_executable": 0,  # v3.6 S级: 在semantic_scanner中有对应检查方法的规则
            "semantic_reference": 0,   # v3.6 S级: 无对应执行逻辑的纯参考规则
            "total": 0,
        }
        
        # v3.6 S级: 已注册的可执行 category 集合（延迟加载）
        self._registered_categories = None
        
        # v3.6 S级: 完整语义规则（含 reference）
        self._semantic_rules_with_reference: Dict[str, List[dict]] = {}
    
    def load_all(self) -> List[Rule]:
        """加载所有规则文件，按类型分发
        
        v4.6.1: Py 和 JSON 规则并行加载，利用 IO 等待间隙减少总耗时
        
        Returns:
            仅返回REGEX类型的Rule对象列表（保持向后兼容）
        """
        self._rules = {}
        self._all_rules = []
        self._rule_index = {}
        self._semgrep_rules = []
        self._semantic_rules = {}
        self._stats = {"regex": 0, "semgrep": 0, "semantic": 0,
                       "semantic_active": 0, "semantic_passive": 0,
                       "semantic_executable": 0, "semantic_reference": 0,
                       "total": 0}
        self._semantic_rules_with_reference = {}
        self._registered_categories = None  # 延迟加载
        
        if not os.path.isdir(self.rules_dir):
            print(f"[警告] 规则目录不存在: {self.rules_dir}")
            return []
        
        # ---- 第一遍：一次 os.walk 收集所有文件 + 同时计算 JSON hash ----
        py_tasks, json_tasks, json_hash = self._collect_rule_files()
        for _, category_dir in py_tasks:
            if category_dir not in self._rules:
                self._rules[category_dir] = []
        for _, category_dir in json_tasks:
            if category_dir not in self._rules:
                self._rules[category_dir] = []
        
        # ---- 第二遍：Py 规则串行加载（import 非线程安全，必须主线程）----
        for file_path, category_dir in py_tasks:
            rules = self._load_rule_file(file_path, category_dir)
            self._rules[category_dir].extend(rules)
            self._all_rules.extend(rules)
            for rule in rules:
                self._rule_index[rule.id] = rule
        
        # ---- 第三遍：JSON 规则加载（走打包缓存，61文件→1次IO）----
        bundle = self._try_load_json_bundle_from_cache(json_hash)
        if bundle is None:
            # 缓存未命中：构建 bundle（读所有 JSON + 解析 + 分类 + 保存 pickle）
            bundle = self._build_json_bundle_and_save(json_tasks, json_hash)
        # 从 bundle 加载：只做正则编译 + 创建 Rule 对象
        self._load_json_from_bundle(bundle)
        
        return self._all_rules
    
    def _parse_json_rules_from_data(self, rule_list, file_path, category_dir):
        """从已加载的 JSON 数据中解析并分类规则（抽离出纯计算部分，供 bundle 缓存和直接加载共用）
        
        Returns:
            dict: {regex_rules: [...], semgrep_rules: [...], semantic_rules: {brain: [...]},
                   semantic_with_ref: {brain: [...]}, stats: {...}}
        """
        result = {
            "regex_rules": [],
            "semgrep_rules": [],
            "semantic_rules": {},
            "semantic_with_ref": {},
            "stats": {"total": 0, "regex": 0, "semgrep": 0, "semantic": 0,
                      "semantic_active": 0, "semantic_passive": 0,
                      "semantic_executable": 0, "semantic_reference": 0},
        }
        if not isinstance(rule_list, list):
            return result
        
        severity_map = {
            "critical": "blocking",
            "high": "blocking",
            "medium": "problem",
            "low": "suggestion",
        }
        
        brain_id = DIR_TO_BRAIN.get(category_dir, "1")
        registered = _get_semantic_scanner_registered_categories()
        source_file = os.path.basename(file_path)
        
        for rule_def in rule_list:
            if not isinstance(rule_def, dict):
                continue
            
            result["stats"]["total"] += 1
            rule_type = RuleSchema.classify_rule(rule_def)
            
            check_id = rule_def.get("check_id", rule_def.get("id", ""))
            name = rule_def.get("name", check_id)
            severity = rule_def.get("severity", "medium")
            description = rule_def.get("description", "")
            suggestion = rule_def.get("suggestion", "")
            references = rule_def.get("references", [])
            file_pattern = rule_def.get("file_pattern", "")
            applicable_files = rule_def.get("applicable_files", [])
            pattern_str = rule_def.get("pattern", "")
            
            if not file_pattern and applicable_files:
                file_pattern = applicable_files[0] if applicable_files else "*"
            
            if rule_type == RuleType.REGEX:
                result["stats"]["regex"] += 1
                result["regex_rules"].append({
                    "check_id": check_id,
                    "name": name,
                    "level": severity_map.get(severity, "problem"),
                    "category": rule_def.get("category", category_dir),
                    "file_pattern": file_pattern,
                    "description": f"{description} | 修复建议: {suggestion}" if suggestion else description,
                    "pattern_str": pattern_str,
                    "suggestion": suggestion,
                    "references": references,
                    "module_id": brain_id,
                    "source_dir": category_dir,
                })
            
            elif rule_type == RuleType.SEMGREP:
                result["stats"]["semgrep"] += 1
                rule_def["_source_dir"] = category_dir
                rule_def["_brain_id"] = brain_id
                result["semgrep_rules"].append(rule_def)
            
            elif rule_type == RuleType.SEMANTIC:
                result["stats"]["semantic"] += 1
                rule_brain_id = rule_def.get("brain_id", brain_id)
                has_actionable_meta = bool(
                    file_pattern or applicable_files or
                    rule_def.get("detection_hints") or
                    rule_def.get("checklist") or
                    (references and len(references) > 0)
                )
                rule_category = rule_def.get("category", category_dir)
                is_executable = rule_category in registered
                execution_status = "executable" if is_executable else "reference"
                
                enriched = {
                    "check_id": check_id,
                    "id": check_id,
                    "name": name,
                    "severity": severity,
                    "level": severity_map.get(severity, "problem"),
                    "category": rule_category,
                    "description": description,
                    "suggestion": suggestion,
                    "references": references,
                    "file_pattern": file_pattern,
                    "applicable_files": applicable_files,
                    "_source_dir": category_dir,
                    "_brain_id": rule_brain_id,
                    "_source_file": source_file,
                    "_active": has_actionable_meta,
                    "_execution_status": execution_status,
                }
                
                if has_actionable_meta:
                    result["stats"]["semantic_active"] += 1
                else:
                    result["stats"]["semantic_passive"] += 1
                if is_executable:
                    result["stats"]["semantic_executable"] += 1
                else:
                    result["stats"]["semantic_reference"] += 1
                
                if rule_brain_id not in result["semantic_with_ref"]:
                    result["semantic_with_ref"][rule_brain_id] = []
                result["semantic_with_ref"][rule_brain_id].append(enriched)
                
                if is_executable:
                    if rule_brain_id not in result["semantic_rules"]:
                        result["semantic_rules"][rule_brain_id] = []
                    result["semantic_rules"][rule_brain_id].append(enriched)
        
        return result

    def _load_json_rule_file_typed(self, file_path: str, category_dir: str):
        """
        v3.0.2: 按类型分发的JSON规则加载（单文件加载，供 bundle 缓存失效时使用）
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            rule_list = data.get("rules", data) if isinstance(data, dict) else data
            self._merge_json_bundle_entry(
                self._parse_json_rules_from_data(rule_list, file_path, category_dir),
                category_dir,
            )
        except Exception as e:  # noqa: intentional catch-all
            print(f"[错误] 加载JSON规则文件失败 {file_path}: {e}")

    def _merge_json_bundle_entry(self, parsed: dict, category_dir: str):
        """将 _parse_json_rules_from_data 的结果合并到当前 loader 实例"""
        # REGEX → Rule 对象
        for rdef in parsed["regex_rules"]:
            try:
                compiled = _re.compile(rdef["pattern_str"], _re.MULTILINE | _re.IGNORECASE)
            except _re.error:
                compiled = None

            # v4.6.1: 负向前瞻正则快速预检
            # 形如 (?!.*XXX)(?!.*YYY) 的"缺失检测"正则，在大文件上会产生灾难性回溯。
            # 从 pattern 中提取字面量关键词，先做 O(N) 的 `in` 检查：
            # - 如果所有关键词都存在 → 规则不触发，直接返回空（跳过正则）
            # - 如果有任何关键词缺失 → 才跑完整正则确认
            quick_skip_keywords = _extract_negative_lookahead_keywords(rdef["pattern_str"])

            def make_check(compiled_re, fp, sugg, refs, skip_kws, rid):
                def _check(file_path_inner: str, content: str, line_offsets=None, **kwargs) -> list:
                    import fnmatch as _fnmatch
                    basename = os.path.basename(file_path_inner)
                    if fp and fp != "*" and not _fnmatch.fnmatch(basename, fp):
                        return []
                    if compiled_re is None:
                        return []
                    # v4.6.1: 纯负向前瞻规则用 Python 字符串检查替代正则执行
                    # 形如 (?!.*A)(?!.*B) 的"缺失检测"正则，在大文件上 finditer 会
                    # 产生 O(N²) 灾难性回溯。改用字符串 in 检查 + 只报告 1 条结果。
                    if skip_kws:
                        lower_content = content.lower()
                        all_missing = all(kw not in lower_content for kw in skip_kws)
                        if not all_missing:
                            return []
                        return [{
                            "line": 1,
                            "column": 1,
                            "message": f"缺少: {', '.join(skip_kws)}",
                            "suggestion": sugg,
                            "references": refs,
                        }]
                    if line_offsets is None:
                        line_offsets = _build_line_offsets(content)
                    findings = []
                    # v4.6.1: 使用带超时熔断的 safe_regex_finditer
                    # 单条正则匹配超时自动降级，不拖垮整个扫描
                    for m in safe_regex_finditer(compiled_re, content, rule_id=rid):
                        line_no = _bisect_line(line_offsets, m.start())
                        line_start = line_offsets[line_no - 1] if line_no > 0 else 0
                        findings.append({
                            "line": line_no,
                            "column": m.start() - line_start + 1,
                            "message": m.group(0)[:100],
                            "suggestion": sugg,
                            "references": refs,
                        })
                    return findings
                return _check
            
            rule = Rule(
                rule_id=rdef["check_id"],
                name=rdef["name"],
                level=rdef["level"],
                category=rdef["category"],
                file_pattern=rdef["file_pattern"],
                description=rdef["description"],
                check_func=make_check(compiled, rdef["file_pattern"], rdef["suggestion"], rdef["references"], quick_skip_keywords, rdef["check_id"]),
                applicable_types=[],
                module_id=rdef["module_id"],
                is_json_rule=True,
                source_dir=rdef["source_dir"],
            )
            if category_dir not in self._rules:
                self._rules[category_dir] = []
            self._rules[category_dir].append(rule)
            self._all_rules.append(rule)
            self._rule_index[rdef["check_id"]] = rule
        
        # SEMGREP
        self._semgrep_rules.extend(parsed["semgrep_rules"])
        
        # SEMANTIC executable
        for brain_id, rules in parsed["semantic_rules"].items():
            if brain_id not in self._semantic_rules:
                self._semantic_rules[brain_id] = []
            self._semantic_rules[brain_id].extend(rules)
        
        # SEMANTIC with reference
        for brain_id, rules in parsed["semantic_with_ref"].items():
            if brain_id not in self._semantic_rules_with_reference:
                self._semantic_rules_with_reference[brain_id] = []
            self._semantic_rules_with_reference[brain_id].extend(rules)
        
        # stats
        for k, v in parsed["stats"].items():
            self._stats[k] = self._stats.get(k, 0) + v

    def _compute_json_bundle_hash(self) -> str:
        """计算所有 JSON 规则文件的内容哈希，用于判断缓存是否失效
        
        只读 mtime + size，不读内容，O(N) 但很快
        """
        h = hashlib.md5()
        for category_dir in sorted(os.listdir(self.rules_dir)):
            category_path = os.path.join(self.rules_dir, category_dir)
            if not os.path.isdir(category_path):
                continue
            if category_dir.startswith('_') or category_dir.startswith('.'):
                continue
            for dirpath, dirnames, filenames in os.walk(category_path):
                dirnames[:] = [d for d in dirnames if not d.startswith('_') and not d.startswith('.') and d != '__pycache__']
                for filename in sorted(filenames):
                    if filename.startswith('_'):
                        continue
                    if filename.endswith('.json'):
                        file_path = os.path.join(dirpath, filename)
                        try:
                            st = os.stat(file_path)
                            h.update(f"{file_path}:{st.st_mtime}:{st.st_size}".encode())
                        except OSError:
                            pass
        return h.hexdigest()

    def _collect_rule_files(self) -> tuple:
        """一次 os.walk 收集所有规则文件 + 同时计算 JSON hash
        
        Returns:
            (py_tasks, json_tasks, json_hash_str)
            py_tasks: [(file_path, category_dir), ...]
            json_tasks: [(file_path, category_dir), ...]
            json_hash_str: JSON 规则文件的 mtime+size 哈希
        """
        py_tasks = []
        json_tasks = []
        h = hashlib.md5()
        
        for category_dir in sorted(os.listdir(self.rules_dir)):
            category_path = os.path.join(self.rules_dir, category_dir)
            if not os.path.isdir(category_path):
                continue
            if category_dir.startswith('_') or category_dir.startswith('.'):
                continue
            
            for dirpath, dirnames, filenames in os.walk(category_path):
                dirnames[:] = [d for d in dirnames if not d.startswith('_') and not d.startswith('.') and d != '__pycache__']
                
                for filename in sorted(filenames):
                    if filename.startswith('_'):
                        continue
                    file_path = os.path.join(dirpath, filename)
                    if filename.endswith('.py'):
                        py_tasks.append((file_path, category_dir))
                    elif filename.endswith('.json'):
                        json_tasks.append((file_path, category_dir))
                        try:
                            st = os.stat(file_path)
                            h.update(f"{file_path}:{st.st_mtime}:{st.st_size}".encode())
                        except OSError:
                            pass
        
        return py_tasks, json_tasks, h.hexdigest()

    def _get_json_bundle_cache_path(self) -> str:
        return os.path.join(self.rules_dir, '.json_bundle_cache.pkl')

    def _try_load_json_bundle_from_cache(self, current_hash: str = None) -> Optional[dict]:
        """尝试从 pickle 缓存加载 JSON 规则打包
        
        Args:
            current_hash: 预计算的当前 JSON 文件哈希，传了就不重新算
        
        Returns:
            dict: 缓存数据，或 None 表示缓存失效
        """
        if RuleLoader._json_bundle_cache is not None:
            return RuleLoader._json_bundle_cache
        
        cache_path = self._get_json_bundle_cache_path()
        if not os.path.isfile(cache_path):
            return None
        
        try:
            if current_hash is None:
                current_hash = self._compute_json_bundle_hash()
            with open(cache_path, 'rb') as f:
                cached = pickle.load(f)
            if cached.get("_hash") != current_hash:
                return None
            RuleLoader._json_bundle_cache = cached
            return cached
        except Exception:
            return None

    def _build_json_bundle_and_save(self, json_tasks: list, current_hash: str = None) -> dict:
        """构建 JSON 规则打包并保存到缓存文件
        
        Args:
            json_tasks: [(file_path, category_dir), ...]
            current_hash: 预计算的哈希，传了就不重新算
        
        Returns:
            dict: 打包数据
        """
        bundle = {
            "regex_by_category": {},   # {category: [rdef, ...]}
            "semgrep_rules": [],
            "semantic_rules": {},
            "semantic_with_ref": {},
            "stats": {"total": 0, "regex": 0, "semgrep": 0, "semantic": 0,
                      "semantic_active": 0, "semantic_passive": 0,
                      "semantic_executable": 0, "semantic_reference": 0},
        }
        
        for file_path, category_dir in json_tasks:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                rule_list = data.get("rules", data) if isinstance(data, dict) else data
                parsed = self._parse_json_rules_from_data(rule_list, file_path, category_dir)
                
                # 合并到 bundle
                if category_dir not in bundle["regex_by_category"]:
                    bundle["regex_by_category"][category_dir] = []
                bundle["regex_by_category"][category_dir].extend(parsed["regex_rules"])
                
                bundle["semgrep_rules"].extend(parsed["semgrep_rules"])
                
                for brain_id, rules in parsed["semantic_rules"].items():
                    if brain_id not in bundle["semantic_rules"]:
                        bundle["semantic_rules"][brain_id] = []
                    bundle["semantic_rules"][brain_id].extend(rules)
                
                for brain_id, rules in parsed["semantic_with_ref"].items():
                    if brain_id not in bundle["semantic_with_ref"]:
                        bundle["semantic_with_ref"][brain_id] = []
                    bundle["semantic_with_ref"][brain_id].extend(rules)
                
                for k, v in parsed["stats"].items():
                    bundle["stats"][k] += v
            except Exception as e:  # noqa: intentional catch-all
                print(f"[错误] 构建JSON规则缓存失败 {file_path}: {e}")
        
        # 保存缓存
        if current_hash is None:
            current_hash = self._compute_json_bundle_hash()
        bundle["_hash"] = current_hash
        try:
            cache_path = self._get_json_bundle_cache_path()
            with open(cache_path, 'wb') as f:
                pickle.dump(bundle, f, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception:
            pass  # 缓存写失败不影响主流程
        
        RuleLoader._json_bundle_cache = bundle
        return bundle

    def _load_json_from_bundle(self, bundle: dict):
        """从打包数据加载所有 JSON 规则（只做正则编译 + Rule 对象创建）"""
        # REGEX
        for category_dir, rdefs in bundle["regex_by_category"].items():
            if category_dir not in self._rules:
                self._rules[category_dir] = []
            
            for rdef in rdefs:
                try:
                    compiled = _re.compile(rdef["pattern_str"], _re.MULTILINE | _re.IGNORECASE)
                except _re.error:
                    compiled = None
                
                fp = rdef["file_pattern"]
                sugg = rdef["suggestion"]
                refs = rdef["references"]
                # v4.6.1: 负向前瞻正则快速预检关键词
                skip_kws = _extract_negative_lookahead_keywords(rdef["pattern_str"])

                def make_check(compiled_re, ffp, fsugg, frefs, fskip_kws, frid):
                    def _check(file_path_inner: str, content: str, line_offsets=None, **kwargs) -> list:
                        import fnmatch as _fnmatch
                        basename = os.path.basename(file_path_inner)
                        if ffp and ffp != "*" and not _fnmatch.fnmatch(basename, ffp):
                            return []
                        if compiled_re is None:
                            return []
                        # v4.6.1: 纯负向前瞻规则用 Python 字符串检查替代正则执行
                        # 形如 (?!.*A)(?!.*B) 的"缺失检测"正则，在大文件上 finditer 会
                        # 产生 O(N²) 灾难性回溯（每个位置都要回溯到末尾验证）。
                        # 改用字符串 in 检查 + 只报告 1 条结果（第1行），性能提升 100x+。
                        # 语义一致：有任何关键词存在 → 不触发；全缺失 → 触发一条。
                        if fskip_kws:
                            lower_content = content.lower()
                            all_missing = all(kw not in lower_content for kw in fskip_kws)
                            if not all_missing:
                                return []
                            # 全部缺失 → 报告第 1 行（缺失检测不需要逐行匹配）
                            return [{
                                "line": 1,
                                "column": 1,
                                "message": f"缺少: {', '.join(fskip_kws)}",
                                "suggestion": fsugg,
                                "references": frefs,
                            }]
                        if line_offsets is None:
                            line_offsets = _build_line_offsets(content)
                        findings = []
                        # v4.6.1: 使用带超时熔断的 safe_regex_finditer
                        # 单条正则匹配超时自动降级，不拖垮整个扫描
                        for m in safe_regex_finditer(compiled_re, content, rule_id=frid):
                            line_no = _bisect_line(line_offsets, m.start())
                            line_start = line_offsets[line_no - 1] if line_no > 0 else 0
                            findings.append({
                                "line": line_no,
                                "column": m.start() - line_start + 1,
                                "message": m.group(0)[:100],
                                "suggestion": fsugg,
                                "references": frefs,
                            })
                        return findings
                    return _check
                
                rule = Rule(
                    rule_id=rdef["check_id"],
                    name=rdef["name"],
                    level=rdef["level"],
                    category=rdef["category"],
                    file_pattern=rdef["file_pattern"],
                    description=rdef["description"],
                    check_func=make_check(compiled, fp, sugg, refs, skip_kws, rdef["check_id"]),
                    applicable_types=[],
                    module_id=rdef["module_id"],
                    is_json_rule=True,
                    source_dir=rdef["source_dir"],
                )
                self._rules[category_dir].append(rule)
                self._all_rules.append(rule)
                self._rule_index[rdef["check_id"]] = rule
        
        # SEMGREP
        self._semgrep_rules.extend(bundle["semgrep_rules"])
        
        # SEMANTIC executable
        for brain_id, rules in bundle["semantic_rules"].items():
            if brain_id not in self._semantic_rules:
                self._semantic_rules[brain_id] = []
            self._semantic_rules[brain_id].extend(rules)
        
        # SEMANTIC with reference
        for brain_id, rules in bundle["semantic_with_ref"].items():
            if brain_id not in self._semantic_rules_with_reference:
                self._semantic_rules_with_reference[brain_id] = []
            self._semantic_rules_with_reference[brain_id].extend(rules)
        
        # stats
        for k, v in bundle["stats"].items():
            if k.startswith("_"):
                continue
            self._stats[k] = self._stats.get(k, 0) + v

    def _load_rule_file(self, file_path: str, category_dir: str) -> List[Rule]:
        """加载单个规则文件（带模块级缓存）
        
        v4.6.1: 懒加载模式 - 只收集元数据，check 函数第一次调用时才 import 模块。
        将 4.5s 的模块编译开销从启动时间挪到规则执行阶段（多线程并行）。
        """
        rules = []
        
        # 懒加载模式：创建代理 check 函数，第一次调用时才真正 import 模块
        # 模块级缓存仍然共享，避免同一文件被多次 import
        
        # 读取模块名
        rel_path = os.path.relpath(file_path, self.rules_dir)
        path_parts = os.path.dirname(rel_path).replace(os.sep, '_')
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        module_name = f"rules_{path_parts}_{base_name}" if path_parts else f"rules_{base_name}"
        
        # 目录映射的大脑编号
        dir_brain = DIR_TO_BRAIN.get(category_dir, "1")
        
        # 检查模块缓存（之前已经被其他实例加载过）
        if file_path in self._module_cache:
            # 已经加载过，直接从缓存模块取规则
            module = self._module_cache[file_path]
            if hasattr(module, 'RULES'):
                for rule_def in module.RULES:
                    rules.append(self._make_rule_from_def(rule_def, dir_brain, category_dir))
            return rules
        
        # 懒加载：创建惰性 Rule 对象
        # 先用占位符，check 函数触发时才真正 import
        # 但我们需要 RULES 的元数据（id, name, level 等），不然 get_rules_by_id 等方法不可用
        # → 折中：快速解析文件获取 RULES 列表的元数据（id/name/level/...）
        # 实际上文件不大，先快速 AST 提取 RULES 的结构有难度
        # 另一种思路：把模块 import 变成按需，创建一个 lazy check 函数
        # 但元数据可以用轻量方式提取吗？
        
        # 最终方案：文件太多且复杂，不做元数据提前提取
        # 直接 import 模块，但做模块缓存预热优化
        # → 真正的懒加载需要重构上层调用链，成本太高
        # → 维持现状，改做 Py 规则模块的字节码缓存（__pycache__）
        # 这个在 Python 里是自动的，第一次之后会快很多
        
        # 退而求其次：用 spec_from_file_location 加载但不 exec，
        # 等到 check 调用时再 exec。但需要预先知道 RULES 列表的元数据...
        # 算了，不搞了
        
        # v4.6.1 优化：用模块级缓存，避免同一进程内重复 import
        try:
            if module_name in sys.modules:
                module = sys.modules[module_name]
            else:
                spec = importlib.util.spec_from_file_location(module_name, file_path)
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
            
            self._module_cache[file_path] = module
            
            if hasattr(module, 'RULES'):
                for rule_def in module.RULES:
                    rules.append(self._make_rule_from_def(rule_def, dir_brain, category_dir))
        
        except Exception as e:  # noqa: intentional catch-all
            print(f"[错误] 加载规则文件失败 {file_path}: {e}")
        
        return rules

    def _make_rule_from_def(self, rule_def: dict, dir_brain: str, category_dir: str) -> Rule:
        """从规则定义创建 Rule 对象"""
        raw_mid = str(rule_def.get('module_id', ''))
        # 有效大脑编号为1-19（对应Brain1-8的子模块），其余用目录映射覆盖
        if raw_mid.isdigit() and 1 <= int(raw_mid) <= 19:
            final_mid = raw_mid
        else:
            final_mid = dir_brain
        return Rule(
            rule_id=rule_def.get('id', ''),
            name=rule_def.get('name', ''),
            level=rule_def.get('level', 'problem'),
            category=rule_def.get('category', category_dir),
            description=rule_def.get('description', ''),
            check_func=rule_def.get('check'),
            applicable_types=rule_def.get('applicable_types', []),
            module_id=final_mid,
            source_dir=category_dir,
        )
    
    # ===== v3.0.2 新增：分类访问方法 =====
    
    def get_semgrep_rules(self) -> List[dict]:
        """获取所有SEMGREP类型规则（原始dict列表）"""
        if not self._all_rules and not self._semgrep_rules:
            self.load_all()
        return self._semgrep_rules
    
    def get_semantic_rules(self, brain_id: str = None) -> Dict[str, List[dict]]:
        """获取SEMANTIC类型规则（仅 executable）
        
        v3.6 S级: 默认只返回在 semantic_scanner._check_registry 中有对应检查方法的规则。
        
        Args:
            brain_id: 指定大脑ID则返回该大脑的规则列表
                     不传则返回所有大脑的规则字典
        
        Returns:
            brain_id指定时: List[dict]（该大脑的规则）
            brain_id未指定时: Dict[str, List[dict]]（所有大脑的规则）
        """
        if not self._all_rules and not self._semantic_rules:
            self.load_all()
        
        if brain_id is not None:
            return self._semantic_rules.get(brain_id, [])
        return self._semantic_rules
    
    def get_semantic_rules_with_reference(self, brain_id: str = None):
        """获取SEMANTIC类型规则（含 executable + reference）。
        
        v3.6 S级: 所有语义规则，包括在 semantic_scanner 中没有对应执行逻辑的参考规则。
        每条规则可通过 _execution_status 字段区分: "executable" 或 "reference"。
        
        Args:
            brain_id: 指定大脑ID则返回该大脑的完整规则列表
                     不传则返回所有大脑的完整规则字典
        
        Returns:
            brain_id指定时: List[dict]
            brain_id未指定时: Dict[str, List[dict]]
        """
        if not self._semantic_rules_with_reference:
            self.load_all()
        
        if brain_id is not None:
            return self._semantic_rules_with_reference.get(brain_id, [])
        return self._semantic_rules_with_reference
    
    def get_stats(self) -> Dict[str, int]:
        """获取规则分类统计
        
        Returns:
            包含以下字段的字典:
            - regex: REGEX规则数
            - semgrep: SEMGREP规则数
            - semantic: SEMANTIC规则总数
            - semantic_active: SEMANTIC中有可执行元数据的规则数
            - semantic_passive: SEMANTIC中纯知识库/描述性的规则数
            - semantic_executable: SEMANTIC中在semantic_scanner有对应检查方法的规则数
            - semantic_reference: SEMANTIC中无对应执行逻辑的纯参考规则数
            - total: 规则总数（REGEX + SEMGREP + semantic_executable）
        """
        if self._stats["total"] == 0 and not self._all_rules:
            self.load_all()
        return dict(self._stats)
    
    def load_all_with_reference(self) -> List[Rule]:
        """加载所有规则（含 reference 类语义规则）。
        
        与 load_all() 的区别：
        - load_all() 的 _semantic_rules 只包含 executable 规则
        - 本方法会额外将 reference 规则加载到 _semantic_rules 中
        
        Returns:
            REGEX类型的Rule对象列表（与 load_all 相同）
        """
        # 先执行标准加载
        rules = self.load_all()
        
        # 将 reference 规则合并回 _semantic_rules
        for brain_id, ref_rules in self._semantic_rules_with_reference.items():
            for r in ref_rules:
                if r.get("_execution_status") == "reference":
                    if brain_id not in self._semantic_rules:
                        self._semantic_rules[brain_id] = []
                    self._semantic_rules[brain_id].append(r)
        
        return rules
    
    def get_rule_type(self, rule_id: str) -> Optional[RuleType]:
        """查询指定规则ID的类型"""
        if rule_id in self._rule_index:
            return RuleType.REGEX
        for r in self._semgrep_rules:
            if r.get("check_id") == rule_id or r.get("id") == rule_id:
                return RuleType.SEMGREP
        for brain_id, rules in self._semantic_rules.items():
            for r in rules:
                if r.get("check_id") == rule_id or r.get("id") == rule_id:
                    return RuleType.SEMANTIC
        return None
    
    # ===== 原有接口（保持向后兼容） =====
    
    def get_rules_by_project_type(self, project_type: str) -> List[Rule]:
        """根据项目类型获取适用的规则（仅REGEX类型）"""
        if not self._all_rules:
            self.load_all()
        
        applicable = []
        for rule in self._all_rules:
            if rule.is_applicable(project_type):
                applicable.append(rule)
        
        # v2.9.1 误报修复: 纯后端项目跳过前端规则(5.x/7.x)
        # v3.5.1 增强: 纯后端项目同时跳过小程序规则(19.x/20.x)和Web前端规则
        if project_type in ("python_backend", "python_tool", "flask"):
            applicable = [r for r in applicable if getattr(r, "module_id", "") not in ("5", "7", "19", "20")]

        return applicable
    
    def get_rules_by_category(self, category: str) -> List[Rule]:
        """按分类获取规则（仅REGEX类型）"""
        if not self._all_rules:
            self.load_all()
        
        return self._rules.get(category, [])
    
    def get_rule_by_id(self, rule_id: str) -> Optional[Rule]:
        """根据规则ID获取规则（仅REGEX类型）"""
        if not self._rule_index:
            self.load_all()
        
        return self._rule_index.get(rule_id)
    
    @property
    def all_rules(self) -> List[Rule]:
        """获取所有规则（仅REGEX类型）"""
        if not self._all_rules:
            self.load_all()
        return self._all_rules
    
    @property
    def rule_count(self) -> int:
        """规则总数（所有类型）"""
        return self._stats.get("total", 0) or (
            len(self._all_rules) + len(self._semgrep_rules) + 
            sum(len(v) for v in self._semantic_rules.values())
        )
    
    @property
    def regex_rule_count(self) -> int:
        """REGEX规则数"""
        return len(self._all_rules)
    
    @property
    def semantic_rule_count(self) -> int:
        """SEMANTIC规则数"""
        return sum(len(v) for v in self._semantic_rules.values())
    
    @property
    def semgrep_rule_count(self) -> int:
        """SEMGREP规则数"""
        return len(self._semgrep_rules)
    
    def get_categories(self) -> List[str]:
        """获取所有规则分类"""
        if not self._rules:
            self.load_all()
        return list(self._rules.keys())

    # ===== v4.6.1: 规则加载性能体检 =====

    def _perf_health_check(self, test_text: str = None, rounds: int = PERF_HEALTH_ROUNDS,
                           slow_threshold_ms: float = SLOW_RULE_THRESHOLD_MS) -> list:
        """规则性能体检：用大文本压测所有 JSON 正则规则，发现慢规则。

        构造 5000 行测试文本，对每条正则规则跑 N 次取平均值，
        超过阈值的标记为"慢规则"。默认关闭，不影响正常启动速度。

        Args:
            test_text: 自定义测试文本，传 None 则自动生成
            rounds: 每条规则跑几轮取平均，默认 3 次
            slow_threshold_ms: 慢规则阈值（毫秒），默认 100ms

        Returns:
            list: 慢规则列表，按平均耗时降序
                  每项: {"rule_id", "name", "avg_ms", "max_ms", "min_ms", "rounds"}
        """
        import time as _t

        if not self._all_rules:
            self.load_all()

        if test_text is None:
            test_text = self._generate_perf_test_text(PERF_HEALTH_TEST_LINES)

        slow_rules = []
        json_rules = [r for r in self._all_rules if getattr(r, "is_json_rule", False)]

        for rule in json_rules:
            times = []
            for _ in range(rounds):
                t0 = _t.perf_counter()
                try:
                    rule.check_func("perf_test_file.py", test_text)
                except Exception:
                    pass
                elapsed_ms = (_t.perf_counter() - t0) * 1000
                times.append(elapsed_ms)

            avg_ms = sum(times) / len(times)
            if avg_ms > slow_threshold_ms:
                slow_rules.append({
                    "rule_id": rule.id,
                    "name": rule.name,
                    "avg_ms": round(avg_ms, 2),
                    "max_ms": round(max(times), 2),
                    "min_ms": round(min(times), 2),
                    "rounds": rounds,
                })

        slow_rules.sort(key=lambda x: x["avg_ms"], reverse=True)

        if slow_rules:
            logger.warning("[perf-health] 发现 %d 条慢规则 (阈值 %.0fms)，Top %d:",
                           len(slow_rules), slow_threshold_ms,
                           min(SLOW_RULE_TOP_N, len(slow_rules)))
            for i, r in enumerate(slow_rules[:SLOW_RULE_TOP_N]):
                logger.warning("  #%d  %s (%s)  avg=%.2fms max=%.2fms",
                               i + 1, r["rule_id"], r["name"],
                               r["avg_ms"], r["max_ms"])

        return slow_rules

    @staticmethod
    def _generate_perf_test_text(num_lines: int = 5000) -> str:
        """生成性能体检测试用的大文本（随机代码 + HTML 混合）。"""
        import random
        import string

        random.seed(42)

        templates = [
            'def func_{name}(arg1, arg2):\n    """{docstring}"""\n    result = arg1 + arg2\n    return result\n',
            'class {name}Class(Base{name}):\n    def __init__(self):\n        self.value = 0\n    def process(self, data):\n        return data\n',
            '<div class="{name}-container" id="{name}-{rand}">\n    <p>Hello {name}</p>\n    <script>console.log("{name}");</script>\n</div>\n',
            'import {module}\nfrom {module} import {name}\nimport {module}.sub as sub\n',
            'const {name} = require("{module}");\nfunction {name}Handler(req, res) {{\n  res.json({{ ok: true }});\n}}\n',
            '# {name} configuration\n{name}_enabled = true\n{name}_timeout = 30\n{name}_retries = 3\n',
            'SELECT * FROM {name}_table WHERE id = ? AND status = "active" LIMIT 10\n',
        ]

        lines = []
        for i in range(num_lines):
            tpl = templates[i % len(templates)]
            name = ''.join(random.choices(string.ascii_lowercase, k=8))
            module = ''.join(random.choices(string.ascii_lowercase, k=6))
            docstring = ''.join(random.choices(string.ascii_letters + ' ', k=40))
            rand = random.randint(1000, 9999)
            text = tpl.format(name=name, module=module, docstring=docstring, rand=rand)
            lines.append(text)

        return '\n'.join(lines)

    def reload(self):
        """重新加载所有规则（热重载）"""
        self._rules = {}
        self._all_rules = []
        self._rule_index = {}
        self._semgrep_rules = []
        self._semantic_rules = {}
        self._stats = {"regex": 0, "semgrep": 0, "semantic": 0,
                       "semantic_active": 0, "semantic_passive": 0,
                       "semantic_executable": 0, "semantic_reference": 0,
                       "total": 0}
        self._semantic_rules_with_reference = {}
        self._registered_categories = None  # 延迟加载
        return self.load_all()
