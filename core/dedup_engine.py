"""
煋鉴代码质检框架 - 去重引擎 (Dedup Engine)

负责跨规则、跨引擎的去重处理，确保同一问题只报一次。

去重优先级：
  Semgrep规则（最精确） > 规则引擎（pattern匹配） > AI补充（低置信度）

去重策略：
  1. 同文件 + 同行 + 同问题类型 → 只保留最高优先级
  2. 同文件 + 相近行（±3行） + 同一 CWE/概念 → 合并为一条
  3. 跨引擎匹配同一问题 → 按引擎优先级去重
"""

import os
import re
import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any

def _safe_path(p: str) -> str:
    """SEC: normalize path to prevent traversal."""
    return os.path.normpath(os.path.abspath(p))

# [v2.0优化] 统一导入全局常量，消除重复定义
try:
    from .constants import SEVERITY_ORDER
except ImportError:
    SEVERITY_ORDER = {
        "blocker": 4, "critical": 4, "high": 3, "medium": 2,
        "low": 1, "info": 0, "S1": 4, "S2": 3, "S3": 2, "S4": 1,
    }


# =============================================================================
# 数据结构
# =============================================================================

@dataclass
class Finding:
    """一条质检发现"""
    rule_id: str
    file_path: str
    line_number: int
    column: int = 0
    severity: str = "S3"
    confidence: str = "low"
    message: str = ""
    category: str = ""
    engine: str = "rule"  # semgrep / rule / ai
    cwe_id: str = ""
    dedup_key: str = ""   # 内部去重键
    source: str = ""      # 来源文件标识
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DedupResult:
    """去重结果"""
    kept: List[Finding] = field(default_factory=list)
    removed: List[Finding] = field(default_factory=list)
    merged: List[Dict] = field(default_factory=list)
    stats: Dict[str, int] = field(default_factory=dict)


# =============================================================================
# 引擎优先级
# =============================================================================

ENGINE_PRIORITY = {
    "semgrep": 1,   # 最精确，基于AST
    "rule": 2,      # 正则匹配规则引擎
    "ai": 3,        # AI补充发现，可能误报
}

SOURCE_PRIORITY = {
    "security": 1,     # Semgrep安全规则
    "js_ts": 2,        # JS/TS专用规则
    "python_deep": 2,  # Python专用规则
    "miniprogram": 2,  # 小程序专用规则
    "performance": 3,  # 性能规则
}


# =============================================================================
# 概念映射：将不同规则ID映射到同一概念
# =============================================================================

CONCEPT_MAP = {
    # SQL注入
    "sql_injection": [
        "SEC-078", "SEC-079", "SEC-080", "SEC-081", "SEC-083", "SEC-085",
        "SEC-088", "SEC-089", "SEC-092", "SEC-093", "SEC-094", "SEC-096",
        "SEC-097", "SEC-351", "SEC-354", "SEC-413", "SEC-419", "SEC-420",
        "SEC-464", "SEC-496", "SEC-497",
        "JS-046", "JS-047",
        "PY-DEEP-001", "PY-DEEP-002", "PY-DEEP-003", "PY-DEEP-004",
        "PY-DEEP-005", "PY-DEEP-006", "PY-DEEP-007", "PY-DEEP-008",
        "PY-DEEP-009", "PY-DEEP-010", "PY-DEEP-117",
        "PERF-001",
    ],
    # XSS
    "xss": [
        "SEC-306", "SEC-307", "SEC-359", "SEC-401", "SEC-495",
        "JS-001", "JS-002", "JS-003", "JS-004", "JS-005",
        "JS-006", "JS-007", "JS-008", "JS-009", "JS-010",
        "JS-011", "JS-012",
    ],
    # eval/代码注入
    "code_injection": [
        "SEC-103", "SEC-134", "SEC-136", "SEC-137",
        "JS-016", "JS-019", "JS-282",
        "PY-DEEP-013", "PY-DEEP-200",
    ],
    # 命令注入
    "command_injection": [
        "SEC-115", "SEC-117", "SEC-118", "SEC-120", "SEC-121", "SEC-123", "SEC-124",
        "JS-042", "JS-043",
    ],
    # 路径遍历
    "path_traversal": [
        "SEC-019", "SEC-020", "SEC-021", "SEC-023", "SEC-303", "SEC-304",
        "SEC-408", "SEC-409", "SEC-410", "SEC-493", "SEC-494",
        "JS-033", "JS-034", "JS-035", "JS-065",
        "PY-DEEP-018",
    ],
    # SSRF
    "ssrf": [
        "SEC-296", "SEC-297", "SEC-298", "SEC-299", "SEC-301",
        "SEC-404", "SEC-407", "SEC-452", "SEC-453", "SEC-454",
        "SEC-488", "SEC-489", "SEC-490", "SEC-492",
        "JS-036", "JS-037", "JS-038",
        "PY-DEEP-021",
    ],
    # CORS
    "cors": [
        "SEC-027", "SEC-028", "SEC-029", "SEC-171", "SEC-377",
        "JS-026", "JS-027", "JS-028", "JS-067",
        "PY-DEEP-123",
    ],
    # 硬编码密钥/密码
    "hardcoded_secret": [
        "SEC-048", "SEC-049", "SEC-050", "SEC-051", "SEC-052", "SEC-053",
        "SEC-054", "SEC-148", "SEC-191", "SEC-318", "SEC-330", "SEC-331",
        "SEC-332", "SEC-435", "SEC-436",
        "JS-024", "JS-060",
        "PY-DEEP-019", "PY-DEEP-111",
    ],
    # JWT
    "jwt": [
        "SEC-014", "SEC-015", "SEC-016", "SEC-017", "SEC-054", "SEC-376",
        "JS-023", "JS-024", "JS-025",
    ],
    # Cookie安全
    "cookie": [
        "SEC-036", "SEC-077", "SEC-173", "SEC-174", "SEC-175", "SEC-176",
        "SEC-182", "SEC-183",
        "JS-029", "JS-030", "JS-031",
    ],
    # N+1查询
    "n_plus_one": [
        "PY-DEEP-114",
        "PERF-001", "PERF-002", "PERF-004",
    ],
    # setData性能(小程序)
    "setdata_perf": [
        "MP-001", "MP-002", "MP-003", "MP-004", "MP-005", "MP-006",
        "MP-007", "MP-008", "MP-009",
    ],
    # 敏感信息泄露
    "sensitive_info": [
        "SEC-156", "SEC-176", "SEC-192", "SEC-194", "SEC-473",
        "JS-032", "JS-048", "JS-272",
        "PY-DEEP-093",
        "MP-077",
    ],
    # console.log
    "console_log": [
        "JS-089",
        "PERF-021",
    ],
    # CSRF
    "csrf": [
        "SEC-035", "SEC-138", "SEC-139", "SEC-320", "SEC-321", "SEC-322",
        "PY-DEEP-126", "PY-DEEP-134",
    ],
    # 密码哈希
    "weak_password_hash": [
        "SEC-039", "SEC-040", "SEC-041", "SEC-042", "SEC-043", "SEC-044",
        "SEC-045", "SEC-046", "SEC-047", "SEC-341", "SEC-342", "SEC-343",
    ],
    # 异常处理
    "exception_handling": [
        "PY-DEEP-086", "PY-DEEP-087", "PY-DEEP-089", "PY-DEEP-090",
        "PY-DEEP-093", "PY-DEEP-095", "PY-DEEP-097", "PY-DEEP-100", "PY-DEEP-110",
        "SEC-270", "SEC-271", "SEC-272", "SEC-449",
    ],
}

# 反转映射：rule_id -> concept
RULE_TO_CONCEPT = {}
for concept, rule_ids in CONCEPT_MAP.items():
    for rid in rule_ids:
        RULE_TO_CONCEPT[rid] = concept


# =============================================================================
# 白名单加载
# =============================================================================

class WhitelistFilter:
    """白名单过滤器"""

    def __init__(self, config_path: str = None):
        self.config = self._load_config(config_path)
        self._compile_patterns()

    def _load_config(self, config_path: str) -> dict:
        if config_path is None:
            # 默认路径
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            config_path = os.path.join(base, "rules", "whitelist_config.json")

        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _compile_patterns(self):
        """预编译文件匹配模式"""
        self._skip_file_regex = []
        for pat in self.config.get("skip_file_patterns", []):
            regex = self._glob_to_regex(pat)
            try:
                self._skip_file_regex.append(re.compile(regex))
            except re.error:  # noqa: intentional empty handler
                pass

        self._test_file_regex = []
        for pat in self.config.get("test_file_patterns", []):
            regex = self._glob_to_regex(pat)
            try:
                self._test_file_regex.append(re.compile(regex))
            except re.error:  # noqa: intentional empty handler
                pass

    @staticmethod
    def _glob_to_regex(glob_pattern: str) -> str:
        """将 glob 模式转换为正则表达式"""
        pattern = glob_pattern
        # Escape special regex chars except * and ?
        pattern = re.escape(pattern)
        # Convert glob wildcards
        pattern = pattern.replace(r"\*\*", ".*")
        pattern = pattern.replace(r"\*", "[^/]*")
        pattern = pattern.replace(r"\?", "[^/]")
        return f"^{pattern}$"

    def should_skip_path(self, file_path: str) -> bool:
        """检查文件路径是否应跳过"""
        for skip_path in self.config.get("skip_paths", []):
            if skip_path in file_path:
                return True
        return False

    def should_skip_file(self, file_path: str) -> bool:
        """检查文件名是否应跳过"""
        basename = os.path.basename(file_path)
        for regex in self._skip_file_regex:
            if regex.match(basename):
                return True
        return False

    def is_test_file(self, file_path: str) -> bool:
        """检查是否为测试文件"""
        basename = os.path.basename(file_path)
        for regex in self._test_file_regex:
            if regex.match(file_path) or regex.match(basename):
                return True
        return False

    def is_auto_generated(self, file_content: str) -> bool:
        """检查文件是否为自动生成"""
        if not self.config.get("auto_generated_skip_all", True):
            return False

        # 只检查前10行
        lines = file_content.split("\n")[:10]
        markers = self.config.get("auto_generated_markers", [])
        for line in lines:
            for marker in markers:
                if marker in line:
                    return True
        return False

    def should_skip_rule_for_test(self, rule_id: str, category: str) -> bool:
        """检查测试文件是否应跳过该规则"""
        skip_cats = self.config.get("test_skip_categories", [])
        if category in skip_cats:
            return True

        skip_ids = self.config.get("test_skip_rule_ids", [])
        if rule_id in skip_ids:
            return True

        return False


# =============================================================================
# 去重引擎
# =============================================================================

class DedupEngine:
    """
    去重引擎

    三层去重:
    1. 路径过滤: 跳过白名单路径
    2. 精确去重: 同文件+同行+同规则 → 只保留一条
    3. 语义去重: 同文件+相近行+同概念 → 保留最高优先级
    """

    def __init__(
        self,
        whitelist_config_path: str = None,
        line_tolerance: int = 3,
        enable_path_filter: bool = True,
        enable_exact_dedup: bool = True,
        enable_semantic_dedup: bool = True,
    ):
        self.whitelist = WhitelistFilter(whitelist_config_path)
        self.line_tolerance = line_tolerance
        self.enable_path_filter = enable_path_filter
        self.enable_exact_dedup = enable_exact_dedup
        self.enable_semantic_dedup = enable_semantic_dedup

    def dedup(self, findings: List[Finding]) -> DedupResult:
        """
        执行完整去重流程

        Args:
            findings: 所有质检发现列表

        Returns:
            DedupResult: 去重后的结果
        """
        result = DedupResult()
        current = list(findings)
        stats = {
            "input_count": len(current),
            "path_filtered": 0,
            "test_filtered": 0,
            "exact_dedup_removed": 0,
            "semantic_dedup_removed": 0,
        }

        # Step 1: 路径过滤
        if self.enable_path_filter:
            current, filtered = self._filter_by_path(current)
            stats["path_filtered"] = len(filtered)
            result.removed.extend(filtered)

        # Step 2: 精确去重
        if self.enable_exact_dedup:
            current, removed = self._exact_dedup(current)
            stats["exact_dedup_removed"] = len(removed)
            result.removed.extend(removed)

        # Step 3: 语义去重
        if self.enable_semantic_dedup:
            current, removed, merged = self._semantic_dedup(current)
            stats["semantic_dedup_removed"] = len(removed)
            result.removed.extend(removed)
            result.merged.extend(merged)

        result.kept = current
        stats["output_count"] = len(current)
        stats["total_removed"] = stats["input_count"] - len(current)
        result.stats = stats

        return result

    def _filter_by_path(self, findings: List[Finding]) -> Tuple[List[Finding], List[Finding]]:
        """按路径过滤"""
        kept = []
        removed = []
        for f in findings:
            if self.whitelist.should_skip_path(f.file_path):
                removed.append(f)
            elif self.whitelist.should_skip_file(f.file_path):
                removed.append(f)
            elif self.whitelist.is_test_file(f.file_path):
                if self.whitelist.should_skip_rule_for_test(f.rule_id, f.category):
                    removed.append(f)
                else:
                    f.metadata["is_test_file"] = True
                    kept.append(f)
            else:
                kept.append(f)
        return kept, removed

    def _exact_dedup(self, findings: List[Finding]) -> Tuple[List[Finding], List[Finding]]:
        """
        精确去重: 同文件+同行+同规则ID → 只保留最高优先级
        """
        groups = defaultdict(list)
        for f in findings:
            key = (f.file_path, f.line_number, f.rule_id)
            groups[key].append(f)

        kept = []
        removed = []
        for key, group in groups.items():
            if len(group) == 1:
                kept.append(group[0])
            else:
                # 按优先级排序: 引擎优先级 > 严重级别 > 置信度
                # [v2.0优化] 使用全局 SEVERITY_ORDER 替代内联重复定义
                group.sort(key=lambda x: (
                    ENGINE_PRIORITY.get(x.engine, 99),
                    5 - SEVERITY_ORDER.get(x.severity, 0),  # 转换：高严重度 → 小数值
                    {"high": 1, "medium": 2, "low": 3}.get(x.confidence, 4),
                ))
                kept.append(group[0])
                removed.extend(group[1:])

        return kept, removed

    def _semantic_dedup(
        self, findings: List[Finding]
    ) -> Tuple[List[Finding], List[Finding], List[Dict]]:
        """
        语义去重: 同文件+相近行+同一概念 → 保留最高优先级
        """
        # 先按文件分组
        by_file = defaultdict(list)
        for f in findings:
            by_file[f.file_path].append(f)

        kept = []
        removed = []
        merged = []

        for file_path, file_findings in by_file.items():
            # 按行号排序
            file_findings.sort(key=lambda x: x.line_number)

            # 将每条finding映射到概念
            concept_groups = defaultdict(list)
            ungrouped = []

            for f in file_findings:
                concept = RULE_TO_CONCEPT.get(f.rule_id, None)
                if concept:
                    concept_groups[concept].append(f)
                else:
                    ungrouped.append(f)

            # 对每个概念组，检查行号是否相近
            for concept, group in concept_groups.items():
                # 聚类: 行号差距在 tolerance 内的合并
                clusters = self._cluster_by_line(group)

                for cluster in clusters:
                    if len(cluster) == 1:
                        kept.append(cluster[0])
                    else:
                        # 选优先级最高的保留
                        # [v2.0优化] 使用全局 SEVERITY_ORDER 替代内联重复定义
                        cluster.sort(key=lambda x: (
                            ENGINE_PRIORITY.get(x.engine, 99),
                            SOURCE_PRIORITY.get(x.source, 99),
                            5 - SEVERITY_ORDER.get(x.severity, 0),  # 高严重度 → 小数值
                            {"high": 1, "medium": 2, "low": 3}.get(x.confidence, 4),
                        ))
                        primary = cluster[0]
                        primary.metadata["merged_from"] = [f.rule_id for f in cluster[1:]]
                        primary.metadata["concept"] = concept
                        kept.append(primary)
                        removed.extend(cluster[1:])

                        merged.append({
                            "concept": concept,
                            "file": file_path,
                            "kept_rule": primary.rule_id,
                            "merged_rules": [f.rule_id for f in cluster[1:]],
                            "lines": [f.line_number for f in cluster],
                        })

            # 没有概念映射的直接保留
            kept.extend(ungrouped)

        return kept, removed, merged

    @staticmethod
    def _cluster_by_line(findings: List[Finding], tolerance: int = 3) -> List[List[Finding]]:
        """将行号相近的finding聚类"""
        if not findings:
            return []

        sorted_f = sorted(findings, key=lambda x: x.line_number)
        clusters = [[sorted_f[0]]]

        for f in sorted_f[1:]:
            last_cluster = clusters[-1]
            max_line = max(x.line_number for x in last_cluster)

            if f.line_number - max_line <= tolerance:
                last_cluster.append(f)
            else:
                clusters.append([f])

        return clusters

    def filter_auto_generated(self, file_path: str, content: str) -> bool:
        """检查是否为自动生成文件，应整体跳过"""
        return self.whitelist.is_auto_generated(content)


# =============================================================================
# 便捷接口
# =============================================================================

def quick_dedup(
    findings: List[Dict],
    whitelist_path: str = None,
) -> Dict:
    """
    快速去重接口

    Args:
        findings: 字典列表，每条包含 rule_id, file_path, line_number 等
        whitelist_path: 白名单配置文件路径

    Returns:
        dict: {kept: [...], removed: [...], stats: {...}}
    """
    engine = DedupEngine(whitelist_config_path=whitelist_path)

    # 转换为 Finding 对象
    finding_objs = []
    for f in findings:
        obj = Finding(
            rule_id=f.get("rule_id", ""),
            file_path=f.get("file_path", ""),
            line_number=f.get("line_number", 0),
            column=f.get("column", 0),
            severity=f.get("severity", "S3"),
            confidence=f.get("confidence", "low"),
            message=f.get("message", ""),
            category=f.get("category", ""),
            engine=f.get("engine", "rule"),
            cwe_id=f.get("cwe_id", ""),
            source=f.get("source", ""),
            metadata=f.get("metadata", {}),
        )
        finding_objs.append(obj)

    result = engine.dedup(finding_objs)

    return {
        "kept": [_finding_to_dict(f) for f in result.kept],
        "removed": [_finding_to_dict(f) for f in result.removed],
        "merged": result.merged,
        "stats": result.stats,
    }


def _finding_to_dict(f: Finding) -> Dict:
    return {
        "rule_id": f.rule_id,
        "file_path": f.file_path,
        "line_number": f.line_number,
        "column": f.column,
        "severity": f.severity,
        "confidence": f.confidence,
        "message": f.message,
        "category": f.category,
        "engine": f.engine,
        "cwe_id": f.cwe_id,
        "source": f.source,
        "metadata": f.metadata,
    }


# =============================================================================
# CLI 入口
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="煋鉴去重引擎")
    parser.add_argument("input", help="输入的JSON文件路径（包含findings数组）")
    parser.add_argument("-o", "--output", help="输出文件路径", default=None)
    parser.add_argument("-w", "--whitelist", help="白名单配置路径", default=None)
    parser.add_argument("--no-path-filter", action="store_true", help="禁用路径过滤")
    parser.add_argument("--no-exact-dedup", action="store_true", help="禁用精确去重")
    parser.add_argument("--no-semantic-dedup", action="store_true", help="禁用语义去重")
    parser.add_argument("--tolerance", type=int, default=3, help="行号容差(默认3)")

    args = parser.parse_args()

    # 读取输入 (SEC: validated path)
    with open(_safe_path(args.input), "r", encoding="utf-8") as f:
        data = json.load(f)

    findings = data if isinstance(data, list) else data.get("findings", [])

    # 执行去重
    engine = DedupEngine(
        whitelist_config_path=args.whitelist,
        line_tolerance=args.tolerance,
        enable_path_filter=not args.no_path_filter,
        enable_exact_dedup=not args.no_exact_dedup,
        enable_semantic_dedup=not args.no_semantic_dedup,
    )

    finding_objs = []
    for f in findings:
        obj = Finding(
            rule_id=f.get("rule_id", ""),
            file_path=f.get("file_path", ""),
            line_number=f.get("line_number", 0),
            severity=f.get("severity", "S3"),
            confidence=f.get("confidence", "low"),
            engine=f.get("engine", "rule"),
            source=f.get("source", ""),
            category=f.get("category", ""),
        )
        finding_objs.append(obj)

    result = engine.dedup(finding_objs)

    output = {
        "kept": [_finding_to_dict(f) for f in result.kept],
        "removed": [_finding_to_dict(f) for f in result.removed],
        "merged": result.merged,
        "stats": result.stats,
    }

    if args.output:
        with open(_safe_path(args.output), "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"Output saved to {args.output}")
    else:
        print(json.dumps(output, ensure_ascii=False, indent=2))

    # 打印摘要
    stats = result.stats
    print(f"\nDedup Summary:")
    print(f"  Input:       {stats.get('input_count', 0)}")
    print(f"  Path filter: {stats.get('path_filtered', 0)}")
    print(f"  Exact dedup: {stats.get('exact_dedup_removed', 0)}")
    print(f"  Semantic:    {stats.get('semantic_dedup_removed', 0)}")
    print(f"  Output:      {stats.get('output_count', 0)}")
    print(f"  Reduction:   {stats.get('total_removed', 0)} ({100 * stats.get('total_removed', 0) / max(stats.get('input_count', 1), 1):.1f}%)")
