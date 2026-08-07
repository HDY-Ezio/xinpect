"""
行级抑制机制 (QA-NOQA) - QA质检框架v3.1

支持多种抑制方式：
1. 单行抑制：# qa-ignore: RULE_ID  或  // qa-ignore: RULE_ID
2. 块级抑制：# qa-ignore-begin / # qa-ignore-end
3. 文件级抑制：文件顶部的 # qa-ignore-file: RULE_ID1,RULE_ID2
4. 目录级抑制：.qaignore 配置文件
5. 规则级抑制：全局配置中的 skip_rules

也支持 nosonar 风格的简写：# qa-nosonar 或 // qa-nosonar

追踪规则：检测过量使用qa-ignore的情况，防止滥用
"""

import os
import re
from typing import Dict, List, Tuple, Optional, Set, Any
from dataclasses import dataclass, field


# ===== 注释符号映射（按文件扩展名） =====
COMMENT_STYLES = {
    # 单行注释
    'py': {'single': '#', 'multi_start': ('"""', "'''"), 'multi_end': ('"""', "'''")},
    'js': {'single': '//', 'multi_start': ('/*',), 'multi_end': ('*/',)},
    'jsx': {'single': '//', 'multi_start': ('/*',), 'multi_end': ('*/',)},
    'ts': {'single': '//', 'multi_start': ('/*',), 'multi_end': ('*/',)},
    'tsx': {'single': '//', 'multi_start': ('/*',), 'multi_end': ('*/',)},
    'css': {'single': None, 'multi_start': ('/*',), 'multi_end': ('*/',)},
    'scss': {'single': '//', 'multi_start': ('/*',), 'multi_end': ('*/',)},
    'less': {'single': '//', 'multi_start': ('/*',), 'multi_end': ('*/',)},
    'html': {'single': None, 'multi_start': ('<!--',), 'multi_end': ('-->',)},
    'wxml': {'single': None, 'multi_start': ('<!--',), 'multi_end': ('-->',)},
    'wxss': {'single': None, 'multi_start': ('/*',), 'multi_end': ('*/',)},
    'vue': {'single': '//', 'multi_start': ('/*', '<!--'), 'multi_end': ('*/', '-->')},
    'json': {'single': None, 'multi_start': (), 'multi_end': ()},
    'yaml': {'single': '#', 'multi_start': (), 'multi_end': ()},
    'yml': {'single': '#', 'multi_start': (), 'multi_end': ()},
    'md': {'single': None, 'multi_start': ('<!--',), 'multi_end': ('-->',)},
    'go': {'single': '//', 'multi_start': ('/*',), 'multi_end': ('*/',)},
    'java': {'single': '//', 'multi_start': ('/*',), 'multi_end': ('*/',)},
    'php': {'single': '//', 'multi_start': ('/*',), 'multi_end': ('*/',)},
}


def get_comment_style(file_path: str) -> dict:
    """根据文件扩展名获取注释风格"""
    ext = os.path.splitext(file_path)[1].lower().lstrip('.')
    return COMMENT_STYLES.get(ext, COMMENT_STYLES.get('js', {}))


@dataclass
class SuppressionResult:
    """抑制结果"""
    is_suppressed: bool = False
    suppress_type: str = ""  # line / block / file / directory / global
    suppress_rule_ids: List[str] = field(default_factory=list)  # 被抑制的规则ID列表
    reason: str = ""
    line_number: int = 0  # 抑制注释所在行


class QAIgnoreSuppressor:
    """
    QA抑制机制处理器
    
    支持的语法：
    - 单行：# qa-ignore: RULE_ID 或 // qa-ignore: RULE_ID 或 # qa-nosonar
    - 块级：# qa-ignore-begin / # qa-ignore-end
    - 文件级：# qa-ignore-file: RULE_ID1,RULE_ID2 (文件前5行内)
    - 全部抑制：# qa-ignore-all 或 # qa-ignore: all
    """

    # 匹配模式
    IGNORE_LINE_PATTERN = re.compile(
        r'(?:#|//|/\*)\s*qa[-_]?ignore\s*:\s*(.+?)\s*(?:\*/)?\s*$',
        re.IGNORECASE
    )
    NOSONAR_PATTERN = re.compile(
        r'(?:#|//|/\*)\s*qa[-_]?nosonar\b',
        re.IGNORECASE
    )
    IGNORE_BEGIN_PATTERN = re.compile(
        r'(?:#|//|/\*)\s*qa[-_]?ignore[-_]?begin\b',
        re.IGNORECASE
    )
    IGNORE_END_PATTERN = re.compile(
        r'(?:#|//|/\*)\s*qa[-_]?ignore[-_]?end\b',
        re.IGNORECASE
    )
    IGNORE_FILE_PATTERN = re.compile(
        r'(?:#|//|/\*)\s*qa[-_]?ignore[-_]?file\s*:\s*(.+?)\s*(?:\*/)?\s*$',
        re.IGNORECASE
    )
    IGNORE_ALL_PATTERN = re.compile(
        r'(?:#|//|/\*)\s*qa[-_]?ignore[-_]?all\b',
        re.IGNORECASE
    )

    def __init__(self, global_skip_rules: List[str] = None):
        self.global_skip_rules: Set[str] = set(global_skip_rules or [])
        self._directory_suppressions: Dict[str, Set[str]] = {}
        self._suppression_stats: Dict[str, int] = {}  # 统计每个文件的抑制次数

    def add_global_skip(self, rule_ids: List[str]):
        """添加全局跳过的规则"""
        self.global_skip_rules.update(rule_ids)

    def load_directory_suppressions(self, directory: str) -> Set[str]:
        """
        加载目录级抑制配置（.qaignore 文件）
        格式：每行一个规则ID，支持 # 注释
        """
        if directory in self._directory_suppressions:
            return self._directory_suppressions[directory]

        suppressions = set()
        qaignore_path = os.path.join(directory, '.qaignore')
        if os.path.isfile(qaignore_path):
            try:
                with open(qaignore_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            suppressions.add(line.strip())
            except Exception as e:  # noqa: broad exception handling
                pass

        self._directory_suppressions[directory] = suppressions
        return suppressions

    def check_suppression(self, rule_id: str, file_path: str, line_number: int,
                          file_lines: List[str] = None) -> SuppressionResult:
        """
        检查指定规则在指定行是否被抑制
        
        检查顺序（优先级从高到低）：
        1. 全局抑制
        2. 目录级抑制（.qaignore）
        3. 文件级抑制（qa-ignore-file）
        4. 块级抑制（qa-ignore-begin / qa-ignore-end）
        5. 行级抑制（qa-ignore: RULE_ID 或 qa-nosonar）
        """
        # 1. 全局抑制
        if self._is_globally_suppressed(rule_id):
            return SuppressionResult(
                is_suppressed=True,
                suppress_type="global",
                suppress_rule_ids=[rule_id],
                reason="全局配置抑制",
            )

        # 2. 目录级抑制
        if file_path:
            dir_path = os.path.dirname(file_path)
            dir_suppressions = self.load_directory_suppressions(dir_path)
            if rule_id in dir_suppressions or 'all' in dir_suppressions:
                return SuppressionResult(
                    is_suppressed=True,
                    suppress_type="directory",
                    suppress_rule_ids=[rule_id],
                    reason=f"目录级抑制（.qaignore）",
                )

        if not file_lines or not file_path:
            return SuppressionResult(is_suppressed=False)

        # 3. 文件级抑制（检查文件前5行）
        file_suppressed_ids = self._get_file_level_suppressions(file_lines)
        if file_suppressed_ids:
            if rule_id in file_suppressed_ids or 'all' in file_suppressed_ids:
                return SuppressionResult(
                    is_suppressed=True,
                    suppress_type="file",
                    suppress_rule_ids=list(file_suppressed_ids),
                    reason="文件级抑制（qa-ignore-file）",
                    line_number=1,
                )

        # 4. 块级抑制
        if self._is_in_ignore_block(line_number, file_lines):
            block_rule_ids = self._get_block_rule_ids(line_number, file_lines)
            if 'all' in block_rule_ids or rule_id in block_rule_ids or not block_rule_ids:
                return SuppressionResult(
                    is_suppressed=True,
                    suppress_type="block",
                    suppress_rule_ids=list(block_rule_ids) or ['all'],
                    reason="块级抑制（qa-ignore-begin）",
                    line_number=line_number,
                )

        # 5. 行级抑制（当前行或上一行的注释）
        line_suppressed, suppressed_ids = self._check_line_suppression(
            line_number, file_lines
        )
        if line_suppressed:
            if 'all' in suppressed_ids or rule_id in suppressed_ids or not suppressed_ids:
                return SuppressionResult(
                    is_suppressed=True,
                    suppress_type="line",
                    suppress_rule_ids=list(suppressed_ids) or ['all'],
                    reason="行级抑制（qa-ignore）",
                    line_number=line_number,
                )

        return SuppressionResult(is_suppressed=False)

    def _is_globally_suppressed(self, rule_id: str) -> bool:
        """检查是否为全局抑制的规则"""
        return rule_id in self.global_skip_rules

    def _get_file_level_suppressions(self, file_lines: List[str]) -> Set[str]:
        """获取文件级抑制的规则ID列表（检查文件前5行）"""
        suppressed_ids = set()
        for i, line in enumerate(file_lines[:5]):
            # qa-ignore-file: RULE_ID1,RULE_ID2
            m = self.IGNORE_FILE_PATTERN.search(line)
            if m:
                ids_str = m.group(1).strip()
                ids = [rid.strip() for rid in ids_str.split(',') if rid.strip()]
                suppressed_ids.update(ids)
            # qa-ignore-all
            if self.IGNORE_ALL_PATTERN.search(line):
                suppressed_ids.add('all')
        return suppressed_ids

    def _is_in_ignore_block(self, line_number: int, file_lines: List[str]) -> bool:
        """检查指定行是否在qa-ignore-begin/end块内"""
        if line_number < 1 or line_number > len(file_lines):
            return False

        depth = 0
        for i in range(line_number - 1):
            if self.IGNORE_BEGIN_PATTERN.search(file_lines[i]):
                depth += 1
            if self.IGNORE_END_PATTERN.search(file_lines[i]):
                depth = max(0, depth - 1)

        return depth > 0

    def _get_block_rule_ids(self, line_number: int, file_lines: List[str]) -> Set[str]:
        """获取当前所在ignore块中指定的规则ID列表"""
        if line_number < 1 or line_number > len(file_lines):
            return set()

        # 找到最近的begin块
        depth = 0
        last_begin_line = -1
        for i in range(line_number - 1):
            if self.IGNORE_BEGIN_PATTERN.search(file_lines[i]):
                depth += 1
                last_begin_line = i
            if self.IGNORE_END_PATTERN.search(file_lines[i]):
                depth = max(0, depth - 1)

        if depth > 0 and last_begin_line >= 0:
            # 从begin行解析规则ID
            m = self.IGNORE_LINE_PATTERN.search(file_lines[last_begin_line])
            if m:
                ids_str = m.group(1).strip()
                ids = [rid.strip() for rid in ids_str.split(',') if rid.strip()]
                return set(ids)

        return set()

    def _check_line_suppression(self, line_number: int, file_lines: List[str]) -> Tuple[bool, Set[str]]:
        """
        检查行级抑制
        返回: (is_suppressed, suppressed_rule_ids)
        """
        if line_number < 1 or line_number > len(file_lines):
            return False, set()

        suppressed_ids = set()

        # 检查当前行的行尾注释
        current_line = file_lines[line_number - 1]
        if self._line_has_suppression(current_line, suppressed_ids):
            return True, suppressed_ids

        # 检查上一行的注释（常见于代码上方写抑制注释）
        if line_number > 1:
            prev_line = file_lines[line_number - 2].strip()
            if self._is_comment_line(prev_line):
                if self._line_has_suppression(prev_line, suppressed_ids):
                    return True, suppressed_ids

        return False, set()

    def _line_has_suppression(self, line: str, suppressed_ids: Set[str]) -> bool:
        """检查单行是否包含抑制注释"""
        # qa-ignore: RULE_ID1,RULE_ID2  (支持行尾附加说明)
        m = self.IGNORE_LINE_PATTERN.search(line)
        if m:
            ids_str = m.group(1).strip()
            # 移除行尾的注释/说明（以 - 或 -- 或 # 开头的）
            # 只取逗号分隔的规则ID部分
            ids_str = re.split(r'\s+[-#]\s+', ids_str)[0]
            ids_str = ids_str.strip()
            
            if ids_str.lower() in ('all', '*', '全部'):
                suppressed_ids.add('all')
            else:
                ids = [rid.strip() for rid in ids_str.split(',') if rid.strip()]
                suppressed_ids.update(ids)
            return True

        # qa-nosonar（抑制所有规则）
        if self.NOSONAR_PATTERN.search(line):
            suppressed_ids.add('all')
            return True

        # qa-ignore-all
        if self.IGNORE_ALL_PATTERN.search(line):
            suppressed_ids.add('all')
            return True

        return False

    def _is_comment_line(self, line: str) -> bool:
        """判断行是否为注释行"""
        stripped = line.strip()
        return (
            stripped.startswith('#') or
            stripped.startswith('//') or
            stripped.startswith('/*') or
            stripped.startswith('*')
        )

    def count_suppressions_in_file(self, file_lines: List[str]) -> Dict[str, int]:
        """
        统计文件中的抑制使用情况
        返回: {total: N, line_suppressions: N, block_suppressions: N, file_level: N}
        """
        stats = {
            'total': 0,
            'line_suppressions': 0,
            'block_suppressions': 0,
            'file_level': 0,
            'suppressed_rule_ids': set(),
        }

        if not file_lines:
            return stats

        # 文件级抑制
        file_suppressions = self._get_file_level_suppressions(file_lines)
        if file_suppressions:
            stats['file_level'] = 1
            stats['total'] += 1
            stats['suppressed_rule_ids'].update(file_suppressions)

        # 逐行统计
        for line in file_lines:
            # 行级抑制
            line_ids = set()
            if self._line_has_suppression(line, line_ids):
                stats['line_suppressions'] += 1
                stats['total'] += 1
                stats['suppressed_rule_ids'].update(line_ids)

            # 块级抑制（begin）
            if self.IGNORE_BEGIN_PATTERN.search(line):
                stats['block_suppressions'] += 1
                stats['total'] += 1

        return stats

    def check_excessive_suppression(self, file_lines: List[str], file_path: str = "",
                                     threshold: int = 10) -> Tuple[bool, str]:
        """
        检测是否过量使用qa-ignore
        返回: (is_excessive, reason)
        """
        stats = self.count_suppressions_in_file(file_lines)
        total = stats['total']

        # 计算代码行数（排除空行和纯注释行）
        code_lines = sum(
            1 for line in file_lines
            if line.strip() and not self._is_comment_line(line)
        )

        if total >= threshold:
            return True, f"文件中使用了{total}处qa-ignore抑制，超过阈值{threshold}"

        if code_lines > 0 and total / code_lines > 0.05:
            return True, f"qa-ignore抑制占代码行数的{total/code_lines:.1%}，超过5%阈值"

        return False, ""


# ===== 便捷函数 =====
_suppressor_instance: Optional[QAIgnoreSuppressor] = None


def get_suppressor(global_skip_rules: List[str] = None) -> QAIgnoreSuppressor:
    """获取抑制处理器单例"""
    global _suppressor_instance
    if _suppressor_instance is None:
        _suppressor_instance = QAIgnoreSuppressor(global_skip_rules)
    elif global_skip_rules:
        _suppressor_instance.add_global_skip(global_skip_rules)
    return _suppressor_instance


def is_rule_suppressed(rule_id: str, file_path: str, line_number: int,
                       file_lines: List[str] = None,
                       global_skip_rules: List[str] = None) -> bool:
    """
    便捷函数：检查规则是否被抑制
    """
    suppressor = get_suppressor(global_skip_rules)
    result = suppressor.check_suppression(rule_id, file_path, line_number, file_lines)
    return result.is_suppressed
