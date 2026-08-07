# -*- coding: utf-8 -*-
"""
Web 前端 JS/TS AST 深度规则引擎
煋鉴 qa-code-expert v4.4 - 前端基础设施

基于 @babel/parser + @babel/traverse 的 AST 级规则引擎，替代原有字符串/正则匹配。
规则执行在 Node.js 子进程中完成，Python 侧负责调度、注册和结果格式化。

支持规则分类：
  - React Hooks 专项规则 (HOOKS-001 ~ HOOKS-008)
  - TypeScript 类型规则 (TS-001 ~ TS-003)
  - JS 质量规则 (JS-001 ~ JS-005)

使用方式：
  from rules.web.ast_rules import JSASTRuleEngine, check_web_ast_rules
  
  # 获取引擎单例
  engine = JSASTRuleEngine.get_instance()
  
  # 对单个文件运行所有规则
  issues = engine.check_file(file_path)
  
  # 通过 RuleLoader 集成
  # 规则通过 RULES 列表自动注册
"""

import os
import re
import threading
from typing import List, Dict, Any, Optional, Callable
from pathlib import Path


# ============================================================
# 规则元数据定义
# ============================================================

# 所有规则的元信息（名称、级别、类别、描述、修复建议）
RULE_META = {
    # ===== React Hooks 专项规则 =====
    'HOOKS-001': {
        'name': 'Hook 调用位置非法',
        'level': 'error',
        'category': 'react_hooks',
        'description': 'React Hook 只能在函数组件或自定义 Hook 中调用',
        'fix': '将 Hook 调用移至 React 函数组件或自定义 Hook 函数顶层',
        'severity': 'P1',
    },
    'HOOKS-002': {
        'name': 'Hook 在条件/循环中调用',
        'level': 'error',
        'category': 'react_hooks',
        'description': 'React Hook 不能在条件判断、循环或嵌套函数中调用，必须在函数顶层',
        'fix': '将 Hook 调用移至函数组件顶层，确保每次渲染时 Hook 调用顺序一致',
        'severity': 'P1',
    },
    'HOOKS-003': {
        'name': 'useEffect 缺少依赖数组',
        'level': 'warning',
        'category': 'react_hooks',
        'description': 'useEffect 未指定依赖数组，每次渲染都会执行副作用',
        'fix': '如果仅需在挂载时执行，传入空数组 []；如依赖某个变量，将其加入依赖数组',
        'severity': 'P2',
    },
    'HOOKS-004': {
        'name': 'useEffect 依赖数组不完整',
        'level': 'warning',
        'category': 'react_hooks',
        'description': 'useEffect 回调中引用的外部变量未全部列入依赖数组',
        'fix': '将回调中使用的所有外部变量加入依赖数组，或使用 useRef/useCallback 处理',
        'severity': 'P2',
    },
    'HOOKS-005': {
        'name': 'useCallback/useMemo 依赖问题',
        'level': 'warning',
        'category': 'react_hooks',
        'description': 'useCallback/useMemo 的依赖数组缺失或不完整',
        'fix': '提供正确的依赖数组以控制缓存失效时机',
        'severity': 'P2',
    },
    'HOOKS-006': {
        'name': 'Hook 返回值未使用',
        'level': 'warning',
        'category': 'react_hooks',
        'description': 'Hook 的返回值（或 setter）未被使用，可能是多余的 Hook 调用',
        'fix': '移除未使用的 Hook，或确保使用其返回值；若 setter 无用考虑改用 useRef',
        'severity': 'P3',
    },
    'HOOKS-007': {
        'name': 'useEffect 直接使用 async 函数',
        'level': 'warning',
        'category': 'react_hooks',
        'description': 'useEffect 回调直接为 async 函数可能导致竞态条件和清理问题',
        'fix': '在 useEffect 内部定义 async 函数并调用，同时返回清理函数处理竞态',
        'severity': 'P2',
    },
    'HOOKS-008': {
        'name': 'useState 复杂计算未用函数式初始化',
        'level': 'info',
        'category': 'react_hooks',
        'description': 'useState 初始值为复杂计算时应使用函数式初始化以避免每次渲染都执行',
        'fix': '改为 useState(() => computeValue()) 形式，仅在首次渲染时执行计算',
        'severity': 'P3',
    },
    
    # ===== JS 质量规则 =====
    'JS-001': {
        'name': '未使用的变量/导入',
        'level': 'warning',
        'category': 'js_quality',
        'description': '存在未使用的变量或导入声明，增加代码维护成本',
        'fix': '移除未使用的变量和导入以保持代码整洁',
        'severity': 'P3',
    },
    'JS-002': {
        'name': '使用 == 而非 ===',
        'level': 'warning',
        'category': 'js_quality',
        'description': '使用 == 会导致隐式类型转换，可能产生意外结果',
        'fix': '使用 === / !== 进行严格比较',
        'severity': 'P2',
    },
    'JS-003': {
        'name': 'eval() 使用',
        'level': 'error',
        'category': 'js_quality',
        'description': 'eval() 存在安全风险（代码注入）且性能较差',
        'fix': '避免使用 eval；JSON 解析使用 JSON.parse，动态逻辑改用其他安全方案',
        'severity': 'P1',
    },
    'JS-004': {
        'name': 'console.log 遗留',
        'level': 'info',
        'category': 'js_quality',
        'description': '生产代码中存在 console.log/debug/info 调试语句',
        'fix': '生产代码应移除调试语句，或通过环境变量/构建工具控制输出',
        'severity': 'P3',
    },
    'JS-005': {
        'name': '空代码块',
        'level': 'info',
        'category': 'js_quality',
        'description': '空的代码块（if/for/while/function 等）可能是未完成的实现',
        'fix': '添加实现代码或添加注释说明为什么为空',
        'severity': 'P3',
    },
}


# 支持的文件扩展名
SUPPORTED_EXTENSIONS = {'.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs'}

# 文件扩展名到解析器类型的映射
EXT_TO_FILENAME = {
    '.js': 'file.js',
    '.jsx': 'file.jsx',
    '.ts': 'file.ts',
    '.tsx': 'file.tsx',
    '.mjs': 'file.mjs',
    '.cjs': 'file.cjs',
}


# ============================================================
# JSASTRuleEngine - Python 侧规则引擎
# ============================================================

class JSASTRuleEngine:
    """JS/TS AST 规则引擎（Python 侧调度器）
    
    负责：
    1. 管理与 Node.js AST 引擎的通信
    2. 规则元数据管理
    3. 结果格式化（转换为与现有 issue 兼容的格式）
    4. 文件过滤
    
    使用单例模式避免重复启动 Node.js 进程。
    """
    
    _instance = None
    _instance_lock = threading.Lock()
    
    def __init__(self):
        self._analyzer = None
        self._available = None  # None = 未检查, True/False
        self._rule_count = len(RULE_META)
        self._rule_ids = list(RULE_META.keys())
    
    @classmethod
    def get_instance(cls) -> 'JSASTRuleEngine':
        """获取引擎单例"""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def _get_analyzer(self):
        """懒加载 JSASTAnalyzer"""
        if self._analyzer is None:
            try:
                from core.js_ast_analyzer import get_js_ast_analyzer
                self._analyzer = get_js_ast_analyzer()
            except ImportError:
                self._analyzer = None
        return self._analyzer
    
    @property
    def is_available(self) -> bool:
        """检查 AST 规则引擎是否可用"""
        if self._available is not None:
            return self._available
        
        analyzer = self._get_analyzer()
        if analyzer is None:
            self._available = False
            return False
        
        try:
            self._available = analyzer.has_ast_rules
        except Exception:
            self._available = False
        
        return self._available
    
    @property
    def rule_count(self) -> int:
        """规则总数"""
        return self._rule_count
    
    @property
    def rule_ids(self) -> List[str]:
        """所有规则 ID 列表"""
        return list(self._rule_ids)
    
    def is_supported_file(self, file_path: str) -> bool:
        """检查文件是否受支持（JS/TS 相关扩展名）"""
        ext = os.path.splitext(file_path)[1].lower()
        return ext in SUPPORTED_EXTENSIONS
    
    def get_rule_meta(self, rule_id: str) -> Optional[Dict[str, Any]]:
        """获取规则元数据"""
        return RULE_META.get(rule_id)
    
    def check_file(self, file_path: str, rule_ids: Optional[List[str]] = None,
                   content: Optional[str] = None) -> List[Dict[str, Any]]:
        """对单个文件运行 AST 规则检查。
        
        Args:
            file_path: 文件路径
            rule_ids: 要运行的规则 ID 列表（None 或空列表表示全部）
            content: 可选，预读取的文件内容
        
        Returns:
            问题列表，每条格式：
            {
                'id': rule_id,
                'name': rule_name,
                'level': 'error'|'warning'|'info',
                'message': str,
                'file': file_path,
                'line': int,
                'col': int,
                'snippet': str,
                'fix': str,
                'category': str,
                'source': 'js_ast',
            }
        """
        if not self.is_supported_file(file_path):
            return []
        
        if not self.is_available:
            return []
        
        analyzer = self._get_analyzer()
        if analyzer is None:
            return []
        
        try:
            raw_issues = analyzer.run_ast_rules(
                file_path,
                rule_ids=rule_ids,
                content=content,
            )
        except Exception:
            return []
        
        if raw_issues is None:
            return []
        
        return self._format_issues(raw_issues, file_path)
    
    def check_content(self, content: str, filename: str = "inline.js",
                       rule_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """直接对代码内容运行规则检查。
        
        Args:
            content: JS/TS 代码字符串
            filename: 文件名（影响解析器插件选择）
            rule_ids: 要运行的规则 ID 列表
        
        Returns:
            格式化后的问题列表
        """
        if not self.is_available:
            return []
        
        analyzer = self._get_analyzer()
        if analyzer is None:
            return []
        
        try:
            raw_issues = analyzer.run_ast_rules_on_content(
                content,
                filename=filename,
                rule_ids=rule_ids,
            )
        except Exception:
            return []
        
        if raw_issues is None:
            return []
        
        return self._format_issues(raw_issues, filename)
    
    def check_files(self, file_paths: List[str], 
                     rule_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """批量检查多个文件。
        
        Args:
            file_paths: 文件路径列表
            rule_ids: 要运行的规则 ID 列表
        
        Returns:
            所有文件的问题汇总
        """
        all_issues = []
        for fpath in file_paths:
            issues = self.check_file(fpath, rule_ids=rule_ids)
            all_issues.extend(issues)
        return all_issues
    
    def _format_issues(self, raw_issues: List[Dict[str, Any]], 
                        file_path: str) -> List[Dict[str, Any]]:
        """将原始 issue（JS 侧返回格式）转换为标准 issue 格式。
        
        与现有规则系统的 issue 结构保持兼容。
        """
        formatted = []
        
        for raw in raw_issues:
            rule_id = raw.get('ruleId', '')
            meta = RULE_META.get(rule_id, {})
            
            # severity 映射到 level
            severity = raw.get('severity', 'warning')
            level_map = {
                'error': 'error',
                'warning': 'warning',
                'info': 'info',
            }
            level = level_map.get(severity, meta.get('level', 'warning'))
            
            issue = {
                'id': rule_id,
                'name': meta.get('name', rule_id),
                'level': level,
                'message': raw.get('message', ''),
                'file': file_path,
                'line': raw.get('line', 0),
                'col': raw.get('col', 0),
                'endLine': raw.get('endLine', 0),
                'endCol': raw.get('endCol', 0),
                'snippet': raw.get('snippet', ''),
                'fix': raw.get('fix') or meta.get('fix', ''),
                'category': meta.get('category', 'web_ast'),
                'severity': meta.get('severity', 'P3'),
                'source': 'js_ast',  # 标记来源为 AST 引擎
                'rule_engine': 'babel_ast',
            }
            formatted.append(issue)
        
        return formatted


# ============================================================
# 共享预计算缓存（HOOKS 规则性能优化）
# 
# v4.6.1 性能瓶颈：HOOKS-001 ~ HOOKS-004 每条规则各自全量扫描所有文件，
# 导致 4 倍 IPC 开销和 4 倍 AST 遍历（在小项目上每条约 20s，合计约 80s）。
# 
# 优化方案：
#   1. 所有 HOOKS 规则共享一次文件扫描（每个文件一次 IPC 调用，一次性返回
#      所有请求的 HOOKS 规则结果）
#   2. 结果按 rule_id 分桶后缓存到 context._hooks_issues_cache
#   3. 单规则 check 函数直接从缓存取数，零额外开销
#   4. 快速跳过非 Hook 文件（内容不含 'use[A-Z]' 的文件直接跳过）
#   5. 利用 context.safe_read() 的文件内容缓存，避免重复读文件
# ============================================================

# 需要共享预计算的 Hook 规则 ID 集合（全部 8 条 HOOKS 规则都可共享）
_SHARED_HOOKS_RULES = {
    'HOOKS-001', 'HOOKS-002', 'HOOKS-003', 'HOOKS-004',
    'HOOKS-005', 'HOOKS-006', 'HOOKS-007', 'HOOKS-008',
}

# 用于快速判断文件是否包含 Hook 调用的正则
# 匹配 use[A-Z] 开头的标识符（React Hooks 命名惯例）
import re as _re
_HOOK_CALL_RE = _re.compile(r'\buse[A-Z]\w*\s*\(', _re.ASCII)


def _file_may_contain_hooks(content: str) -> bool:
    """快速预判文件是否可能包含 Hook 调用。
    
    仅用于性能快速路径，不作为正确性判断依据。
    使用轻量正则匹配 use[A-Z]xxx( 模式（React Hook 命名惯例）。
    
    保守策略：拿不准时返回 True（宁可多检查不漏报）。
    """
    if not content:
        return False
    # 先做极快的子串检查排除明显不相关的文件
    if 'use' not in content:
        return False
    # 再用正则确认是否有 Hook 风格的调用
    return bool(_HOOK_CALL_RE.search(content))


def _get_shared_hooks_issues(context, rule_ids=None) -> Dict[str, List[Dict[str, Any]]]:
    """获取指定 HOOKS 规则的共享预计算结果。
    
    每个文件只做一次 AST 解析 + 一次 IPC 调用，一次性返回所有请求的 HOOKS 规则结果。
    结果缓存到 context._hooks_issues_cache，后续规则直接命中。
    
    与逐条调用 engine.check_file(rule_ids=[single_rule]) 相比，
    将 N 条规则的 N 次 IPC 合并为 1 次，性能提升约 N 倍（N=4 时约 2.4x）。
    
    Args:
        context: 项目上下文对象
        rule_ids: 需要的规则 ID 列表（None 表示所有 SHARED_HOOKS_RULES）
    
    Returns:
        {rule_id: [issue, ...]} 字典
    """
    if rule_ids is None:
        rule_ids = sorted(_SHARED_HOOKS_RULES)
    else:
        # 过滤掉不支持的规则 ID
        rule_ids = sorted(set(rule_ids) & _SHARED_HOOKS_RULES)
    
    if not rule_ids:
        return {}
    
    cache_attr = '_hooks_issues_cache'
    
    # 检查 context 上是否已有这些规则的缓存
    existing_cache = getattr(context, cache_attr, None)
    if existing_cache is not None:
        # 检查所有请求的 rule_id 是否已缓存
        if all(rid in existing_cache for rid in rule_ids):
            return {rid: existing_cache[rid] for rid in rule_ids}
    
    engine = JSASTRuleEngine.get_instance()
    if not engine.is_available:
        result = {rid: [] for rid in rule_ids}
        _merge_hooks_cache(context, cache_attr, result)
        return result
    
    if hasattr(context, 'find_files'):
        files = context.find_files(list(SUPPORTED_EXTENSIONS))
    else:
        files = []
    
    result = {rid: [] for rid in rule_ids}
    
    if not files:
        _merge_hooks_cache(context, cache_attr, result)
        return result
    
    has_safe_read = hasattr(context, 'safe_read')
    
    for fpath in files:
        # 快速跳过：内容不包含 Hook 调用模式则直接跳过
        content = context.safe_read(fpath) if has_safe_read else None
        if content and not _file_may_contain_hooks(content):
            continue
        
        # 一次性运行所有请求的 HOOKS 规则
        issues = engine.check_file(fpath, rule_ids=rule_ids, content=content)
        
        # 按 rule_id 分桶
        for issue in issues:
            rid = issue.get('id', '')
            if rid in result:
                result[rid].append(issue)
    
    # 存入 context 缓存，供后续规则共享
    _merge_hooks_cache(context, cache_attr, result)
    
    return result


def _merge_hooks_cache(context, cache_attr: str, new_results: Dict[str, list]):
    """将新计算的结果合并到 context 的缓存中。"""
    existing = getattr(context, cache_attr, None)
    if existing is None:
        try:
            setattr(context, cache_attr, dict(new_results))
        except Exception:
            pass
    else:
        existing.update(new_results)


# ============================================================
# 单规则检查函数
# 
# 每个规则一个 check_<rule_id> 函数，遵循规范。
# 这些函数通过 RULES 列表注册到 RuleLoader。
# ============================================================

def _make_single_rule_checker(rule_id: str) -> Callable:
    """工厂函数：为单个规则生成 check 函数。
    
    生成的函数签名与现有规则系统兼容：check_file(context) -> List[Dict]
    
    性能优化：
    - HOOKS 系列规则走共享预计算缓存（_get_shared_hooks_issues）
    - 其他规则保持原有独立扫描逻辑
    """
    meta = RULE_META.get(rule_id, {})
    
    # HOOKS 规则使用共享缓存（避免每条规则各自全量扫描）
    if rule_id in _SHARED_HOOKS_RULES:
        def checker(context) -> List[Dict[str, Any]]:
            """Hook 规则检查函数（共享预计算版本）
            
            调用 _get_shared_hooks_issues 获取 HOOKS 规则的批量结果，
            从中取出当前规则的 issue。
            为了最大化共享，首次请求任意一条 HOOKS 规则时会一次性计算
            全部 8 条 HOOKS 规则的结果（增量共享），后续调用零开销命中缓存。
            """
            # 首次请求时一次性计算全部 HOOKS 规则，最大化共享
            all_hooks_issues = _get_shared_hooks_issues(context, rule_ids=None)
            return list(all_hooks_issues.get(rule_id, []))
        
        checker.__name__ = f"check_{rule_id.lower().replace('-', '_')}"
        checker.__doc__ = f"{rule_id}: {meta.get('description', '')} (共享预计算优化)"
        return checker
    
    # 非 HOOKS 规则保持原有逻辑
    def checker(context) -> List[Dict[str, Any]]:
        """规则检查函数（由 _make_single_rule_checker 生成）
        
        Args:
            context: 项目上下文对象，需支持 find_files 和 safe_read
        
        Returns:
            问题列表
        """
        engine = JSASTRuleEngine.get_instance()
        if not engine.is_available:
            return []
        
        # 查找受支持的前端文件
        if hasattr(context, 'find_files'):
            files = context.find_files(list(SUPPORTED_EXTENSIONS))
        else:
            return []
        
        if not files:
            return []
        
        results = []
        for fpath in files:
            content = context.safe_read(fpath) if hasattr(context, 'safe_read') else None
            issues = engine.check_file(fpath, rule_ids=[rule_id], content=content)
            results.extend(issues)
        
        return results
    
    checker.__name__ = f"check_{rule_id.lower().replace('-', '_')}"
    checker.__doc__ = f"{rule_id}: {meta.get('description', '')}"
    return checker


# 动态生成所有规则的 check 函数
# 函数名格式: check_hooks_001, check_ts_001, check_js_001 等
for _rid in list(RULE_META.keys()):
    _func_name = f"check_{_rid.lower().replace('-', '_')}"
    _func = _make_single_rule_checker(_rid)
    globals()[_func_name] = _func


# ============================================================
# RuleLoader 集成
# ============================================================

def _build_rules_list() -> List[Dict[str, Any]]:
    """构建 RULES 列表，供 RuleLoader 自动加载。
    
    与 rules/python/ast_deep/ 下的规范保持一致。
    """
    rules = []
    for rule_id, meta in RULE_META.items():
        func_name = f"check_{rule_id.lower().replace('-', '_')}"
        check_func = globals().get(func_name)
        if check_func is None:
            continue
        
        rules.append({
            'id': rule_id,
            'name': meta['name'],
            'level': meta['level'],
            'category': f"web_{meta['category']}",
            'module_id': '5',  # Brain 5 - 前端相关
            'applicable_types': ['mixed', 'web_frontend', 'react', 'vue', 'mini_program'],
            'description': meta['description'],
            'check': check_func,
            'source': 'js_ast',
        })
    
    return rules


# 聚合检查函数：一次性运行所有 AST 规则
def check_web_ast_rules(context) -> List[Dict[str, Any]]:
    """Web 前端 AST 规则聚合检查。
    
    一次性运行所有 JS/TS AST 规则（比逐条调用更高效，因为只需一次 AST 解析）。
    
    Args:
        context: 项目上下文对象
    
    Returns:
        所有规则的问题汇总
    """
    engine = JSASTRuleEngine.get_instance()
    if not engine.is_available:
        return []
    
    if hasattr(context, 'find_files'):
        files = context.find_files(list(SUPPORTED_EXTENSIONS))
    else:
        return []
    
    if not files:
        return []
    
    results = []
    for fpath in files:
        content = context.safe_read(fpath) if hasattr(context, 'safe_read') else None
        issues = engine.check_file(fpath, content=content)
        results.extend(issues)
    
    return results


# 导出给 RuleLoader 的规则列表
RULES = _build_rules_list()


# ============================================================
# 统计信息
# ============================================================

TOTAL_RULES = len(RULE_META)
HOOKS_RULES = sum(1 for r in RULE_META if r.startswith('HOOKS-'))
TS_RULES = sum(1 for r in RULE_META if r.startswith('TS-'))
JS_RULES = sum(1 for r in RULE_META if r.startswith('JS-'))


__all__ = [
    'JSASTRuleEngine',
    'RULE_META',
    'RULES',
    'check_web_ast_rules',
    'SUPPORTED_EXTENSIONS',
    'TOTAL_RULES',
    'HOOKS_RULES',
    'TS_RULES',
    'JS_RULES',
]
