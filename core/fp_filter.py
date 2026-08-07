"""
误报过滤器
对检查结果进行二次过滤去重

从 runner.py 拆出，职责：
  - FalsePositiveFilter: 对规则检查结果做误报判定与去重
    - 服务层误报过滤（敏感信息 / SQL注入 / 文件上传等）
    - 内置启发式误报规则（命名缩写 / 中文注释 / TODO-ISSUE / TYPE_CHECKING）
    - 结果去重（同 rule_id + file + line）
"""

import os
import re
import logging
from typing import Dict, List, Tuple, Optional

from .rule_loader import RuleCheckResult

logger = logging.getLogger(__name__)


# ====================================================================
# 服务层延迟导入
# ====================================================================

def _import_services():
    """延迟导入服务层，避免循环导入"""
    try:
        import importlib
        services_pkg = importlib.import_module("..services", __name__)
        return services_pkg
    except (ImportError, ValueError):
        try:
            import sys
            parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            import services
            return services
        except ImportError:
            return None


_SERVICES = _import_services()


def _get_fp_service(mode: str = "quick", config: dict = None):
    """获取误报过滤服务实例"""
    if _SERVICES and hasattr(_SERVICES, 'get_fp_service'):
        return _SERVICES.get_fp_service(mode, config)
    return None


# ====================================================================
# FalsePositiveFilter
# ====================================================================

class FalsePositiveFilter:
    """误报过滤器，对检查结果进行二次过滤去重"""

    def __init__(self, context, fp_mode: str = "quick"):
        self.context = context
        self._fp_mode = fp_mode
        self._fp_service = None

        # 统计
        self.fp_stats: Dict = {"total": 0, "filtered": 0, "by_rule": {}}

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    def apply_filter(self, results: Dict[str, List[RuleCheckResult]]) -> None:
        """应用误报过滤器（服务层集成）"""
        fp_service = self._get_fp_service_instance()
        if not fp_service:
            return

        total = 0
        filtered = 0

        for module_id, module_results in results.items():
            for result in module_results:
                total += 1
                is_fp, reason = self._check_false_positive(fp_service, result)
                if is_fp:
                    filtered += 1
                    result.status = "fp"
                    result.fp_reason = reason
                    rule_id = result.rule_id
                    self.fp_stats["by_rule"][rule_id] = self.fp_stats["by_rule"].get(rule_id, 0) + 1

        self.fp_stats["total"] = total
        self.fp_stats["filtered"] = filtered

    def dedup_results(self, results: Dict[str, List[RuleCheckResult]]) -> None:
        """v1.23.0: 结果去重 - 同(rule_id + file + line)只保留一条"""
        seen = set()
        for module_id, module_results in results.items():
            deduped = []
            for r in module_results:
                if getattr(r, 'status', 'active') != 'active':
                    deduped.append(r)
                    continue
                file_path = r.location.get('file', '') if r.location else ''
                line = r.location.get('line', 0) if r.location else 0
                key = (r.rule_id, file_path, line)
                if key in seen:
                    r.status = 'fp'
                    r.fp_reason = '重复条目已去重'
                else:
                    seen.add(key)
                deduped.append(r)
            results[module_id] = deduped

    # ------------------------------------------------------------------
    # 内部：误报判定
    # ------------------------------------------------------------------

    def _check_false_positive(self, fp_service, result: RuleCheckResult) -> Tuple[bool, str]:
        """判断单个检查结果是否为误报，返回 (is_fp, reason)"""
        rule_id = result.rule_id
        location = result.location or {}
        file_path = location.get("file", "")
        snippet = location.get("snippet", "") or result.message or ""

        # ---- 安全类检查（M3）----
        if rule_id.startswith("3."):
            if rule_id in ("3.2", "3.3"):
                is_safe, reason = fp_service.is_safe_sensitive_line(
                    line=snippet, context_lines=[], file_path=file_path,
                )
                if is_safe:
                    return True, f"误报过滤（敏感信息）: {reason}"

            elif rule_id == "3.1":
                analysis = fp_service.analyze_sql_scene(
                    sql_line=snippet, context_lines=[], full_file_content="",
                )
                if analysis.get("is_structural") and analysis.get("confidence", 0) >= 0.7:
                    return True, f"误报过滤（SQL注入）: {analysis.get('reason', '结构拼接')}"

            elif rule_id == "3.12":
                analysis = fp_service.analyze_file_scene(
                    file_path=file_path,
                    line_content=snippet,
                    context_lines=[],
                    function_name="",
                    file_basename=os.path.basename(file_path) if file_path else "",
                )
                if not analysis.get("is_user_upload") and analysis.get("confidence", 0) >= 0.6:
                    return True, f"误报过滤（文件上传）: {analysis.get('reason', '非用户上传场景')}"

        # ---- v3.5.2 扩展误报过滤器 ----

        # 1. 命名规范类：常见缩写/行业术语不算命名违规
        if rule_id.startswith("NAME-") or rule_id.startswith("5.1") or rule_id.startswith("5.2"):
            COMMON_ABBREVIATIONS = {
                'URL', 'API', 'HTTP', 'HTTPS', 'ID', 'DB', 'SQL', 'HTML', 'CSS',
                'JSON', 'XML', 'YAML', 'CSV', 'IO', 'OS', 'CPU', 'GPU', 'RAM',
                'TCP', 'UDP', 'DNS', 'SSH', 'SSL', 'TLS', 'JWT', 'OAuth',
                'SDK', 'CLI', 'GUI', 'REST', 'GraphQL', 'CRUD', 'MVC', 'MVP',
                'VM', 'CI', 'CD', 'AC', 'DC', 'HTML5', 'ES6', 'TS', 'JS',
                'UTF', 'ASCII', 'UUID', 'URI', 'FTP', 'SMTP', 'IMAP',
                'AWS', 'GCP', 'NFC', 'BLE', 'USB', 'HDMI', 'VGA',
                'PNG', 'JPG', 'GIF', 'SVG', 'PDF', 'EOF', 'NULL', 'NAN',
                'OK', 'NG', 'TODO', 'FIXME', 'HACK', 'NOTE', 'INFO',
                'MAX', 'MIN', 'AVG', 'SUM', 'CNT', 'LEN', 'TMP', 'SRC',
                'DST', 'BUF', 'ERR', 'MSG', 'REQ', 'RES', 'CTX', 'CFG',
                'ENV', 'DEV', 'PROD', 'STG', 'AUTH', 'PERM',
            }
            name_match = re.search(r'[`"\'](\w+)[`"\']', snippet)
            if name_match:
                flagged_name = name_match.group(1)
                if flagged_name.upper() in COMMON_ABBREVIATIONS:
                    return True, f"误报过滤（命名规范）: '{flagged_name}' 是常见行业缩写/术语"
            for abbr in COMMON_ABBREVIATIONS:
                if abbr in snippet.upper():
                    name_match2 = re.search(rf'\b{abbr}\b', snippet, re.IGNORECASE)
                    if name_match2:
                        return True, f"误报过滤（命名规范）: '{abbr}' 是常见行业缩写/术语"

        # 2. 注释语言类：项目主要使用中文注释时，不告警"缺少英文注释"
        if rule_id.startswith("DOC-") or rule_id.startswith("6."):
            msg_lower = (result.message or "").lower()
            if 'english' in msg_lower or '英文' in msg_lower or '英文注释' in msg_lower:
                try:
                    code_extensions = ['.py', '.js', '.ts', '.tsx', '.jsx', '.java', '.go']
                    chinese_comment_count = 0
                    total_comment_count = 0
                    checked_files = 0
                    for ext in code_extensions:
                        if checked_files >= 30:
                            break
                        for fpath in self.context.find_files([ext])[:10]:
                            content = self.context.safe_read(fpath)
                            if not content:
                                continue
                            checked_files += 1
                            for line in content.split('\n'):
                                stripped = line.strip()
                                if stripped.startswith('#') or stripped.startswith('//'):
                                    total_comment_count += 1
                                    if re.search(r'[\u4e00-\u9fff]', stripped):
                                        chinese_comment_count += 1
                    if total_comment_count > 5 and chinese_comment_count / total_comment_count > 0.5:
                        return True, "误报过滤（注释语言）: 项目主要使用中文注释，不要求英文注释"
                except Exception:  # noqa: intentional catch-all
                    pass

        # 3. TODO/FIXME 类：关联了 issue 编号的 TODO 降低严重度为 info
        if rule_id.startswith("14.") or 'TODO' in rule_id or 'FIXME' in rule_id:
            msg = result.message or ''
            snippet_text = location.get("snippet", "") or ""
            combined = msg + " " + snippet_text
            if re.search(r'(?:TODO|FIXME|HACK)\s*[#(\-]\s*#?\d+', combined, re.IGNORECASE) or \
               re.search(r'issue\s*#?\s*\d+', combined, re.IGNORECASE):
                result.level = "info"
                return False, ""  # 不过滤，但已降级

        # 4. 导入未使用类：TYPE_CHECKING 块中的 import 不算未使用
        if 'import' in rule_id.lower() or rule_id.startswith("DEAD-00") or rule_id.startswith("6."):
            msg = (result.message or "").lower()
            if 'import' in msg and ('unused' in msg or '未使用' in msg or '未引用' in msg):
                if file_path:
                    try:
                        file_content = self.context.safe_read(file_path)
                        if file_content:
                            line_num = location.get("line", 0)
                            if line_num > 0:
                                lines = file_content.split('\n')
                                in_type_checking = False
                                for check_line_idx in range(min(line_num - 1, len(lines) - 1), -1, -1):
                                    check_line = lines[check_line_idx]
                                    if 'TYPE_CHECKING' in check_line:
                                        in_type_checking = True
                                        break
                                    stripped_check = check_line.strip()
                                    if stripped_check and not stripped_check.startswith('#') and \
                                       not stripped_check.startswith('if') and \
                                       not stripped_check.startswith('from') and \
                                       not stripped_check.startswith('import') and \
                                       not check_line.startswith(' ') and not check_line.startswith('\t'):
                                        break
                                if in_type_checking:
                                    return True, "误报过滤（导入未使用）: import在 TYPE_CHECKING 块中，仅用于类型检查"
                    except Exception:  # noqa: intentional catch-all
                        pass

        # 保守策略：默认不过滤
        return False, ""

    # ------------------------------------------------------------------
    # 内部：服务实例
    # ------------------------------------------------------------------

    def _get_fp_service_instance(self):
        """获取误报过滤服务实例（懒加载）"""
        if self._fp_service is None:
            cfg = getattr(self.context, 'config', None)
            self._fp_service = _get_fp_service(mode=self._fp_mode, config=cfg)
        return self._fp_service
