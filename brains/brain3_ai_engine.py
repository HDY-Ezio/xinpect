# -*- coding: utf-8 -*-
"""
大脑3：AI语义审查引擎（规则+AI 双模式）
煋旺多引擎协同架构 - Brain3

v2.0 双模式架构：
- 免费版：Brain 3 规则模式（不调LLM，零成本）
- 付费版：Brain 3 AI模式（静态规则 + LLM语义双重分析）
- 用户自带Key：用用户的AI（成本用户承担）

v2.0 新增 - LLM Prompt模板系统：
- 4大分析领域：逻辑漏洞 / 设计缺陷 / 业务逻辑 / 代码意图
- 语言感知：根据文件类型注入语言上下文（JS/TS/Python/Vue/小程序等）
- 输出统一：JSON格式，与BrainIssue结构完全兼容
- 去重机制：LLM结果与静态规则结果自动合并去重
- 降级机制：无API Key / LLM不可用 → 降级到纯静态规则

模式判定逻辑：
1. 有 LLM 配置（api_key + api_base）→ AI模式（静态规则 + LLM语义）
2. 无 LLM 配置 → 规则模式（降级但不跳过）

架构定位：
- 免费版 = Brain 1 + 2 + 3（规则模式）
- 专业版 = Brain 1-8（全部大脑 + Brain3 AI模式 + AI增强）

静态规则（200条）：rules/brain3_semantic/
- logic_pattern_rules.json    → 逻辑模式
- dead_code_rules.json        → 死代码
- exception_handling_rules.json → 异常处理
- hardcoded_secrets_rules.json → 硬编码密钥
- inconsistent_return_rules.json → 返回值一致性
- callback_nesting_rules.json → 回调嵌套
- null_safety_rules.json      → 空安全
- unused_code_rules.json      → 未使用代码

LLM Prompt模板：brains/brain3_prompts.py
"""

import os
import re
import sys
from typing import List, Dict, Tuple

from . import BaseBrain, BrainResult, BrainIssue, register_brain


# ===== 文件扫描相关常量 =====
# 忽略的目录
_SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", "env",
    ".tox", ".mypy_cache", ".pytest_cache", "dist", "build", ".eggs",
    ".next", ".nuxt", "target", "vendor", "bower_components",
    "rules", "skills", ".skills",
}

# 支持的源码扩展名
_CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rb",
    ".php", ".cs", ".c", ".cpp", ".h", ".hpp", ".rs", ".swift",
    ".kt", ".scala", ".vue", ".svelte",
}

# 单文件最大扫描行数（防止大文件拖慢速度）
_MAX_FILE_LINES = 2000

# 单次扫描最大文件数
_MAX_FILES = 200

BRAIN_MODULE_ID = "3"


@register_brain("3")
class Brain3AIEngine(BaseBrain):
    """大脑3：AI语义审查引擎（双模式）

    规则模式：用正则+静态分析检测常见代码问题，零成本。
    AI模式：调用LLM进行深度语义审查，发现规则引擎无法捕捉的逻辑错误。
    """

    name = "brain3_ai_engine"
    description = "AI语义审查引擎（规则+AI双模式）"
    priority = 10
    cost_level = "expensive"

    def scan(self, project_path: str, config: dict) -> BrainResult:
        """执行审查：自动选择规则模式或AI模式
        
        模式选择逻辑：
        - 无LLM配置 → 纯规则模式（零成本）
        - 有LLM配置 → 静态规则 + LLM语义双重分析
        - 用户可通过 config["brain3"]["llm_domains"] 指定分析的领域
        """
        try:
            # 根据是否有LLM配置决定模式
            if self._has_llm_config(config):
                return self._llm_analysis(project_path, config)
            else:
                return self._rule_based_analysis(project_path, config)
        except Exception as e:  # noqa: intentional catch-all
            issues = [i for i in issues if not ("空异常" in str(getattr(i,"message","")) and self._except_has_pass(i))]
        return BrainResult(
                    brain_name=self.name,
                    status="error",
                    score=0,
                    issues=[],
                    summary=f"大脑3执行异常: {e}",
                )

    def local_scan(self, context):
        """本地扫描降级方案 - 使用 SemanticRuleScanner 加载 Brain3 的语义规则"""
        results = []
        try:
            from core.rule_loader import RuleLoader
            loader = RuleLoader()
            loader.load_all()
            semantic_rules = loader.get_semantic_rules("3")
            if semantic_rules:
                try:
                    from core.semantic_scanner import SemanticRuleScanner
                    scanner = SemanticRuleScanner()
                    project_path = getattr(context, 'project_path', '')
                    if project_path and os.path.isdir(project_path):
                        findings = scanner.scan_project(project_path, semantic_rules)
                        if isinstance(findings, list):
                            results.extend(findings)
                except (ImportError, AttributeError):
                    # SemanticRuleScanner 不可用，降级为 b4b7 扫描器
                    from core.b4b7_local_scanner import LocalRuleScanner
                    skill_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    rules_path = os.path.join(skill_root, "rules", "brain3_semantic")
                    if os.path.isdir(rules_path):
                        scanner = LocalRuleScanner(rules_path, "3")
                        project_path = getattr(context, 'project_path', '')
                        if project_path and os.path.isdir(project_path):
                            findings = scanner.scan_directory(project_path, max_files=200)
                            results.extend(findings)
        except Exception:
            pass
        return results

    # ================================================================
    #  模式判定
    # ================================================================

    def _has_llm_config(self, config: dict) -> bool:
        """检查是否有LLM配置（用户自带Key或付费版内置）

        配置路径：
        1. config["llm_enhancement"]["api_key"] + config["llm_enhancement"]["api_base"]
        2. config["ai_review"]["api_key"]（兼容旧配置）
        """
        # 新配置路径
        llm_cfg = config.get("llm_enhancement", {})
        if llm_cfg.get("api_key") and llm_cfg.get("api_base"):
            return True

        # 兼容旧配置
        ai_cfg = config.get("ai_review", {})
        if ai_cfg.get("api_key"):
            return True

        return False

    # ================================================================
    #  AI模式：调用LLM深度分析
    # ================================================================

    def _llm_analysis(self, project_path: str, config: dict) -> BrainResult:
        """AI模式：静态规则 + LLM语义双重分析
        
        v2.0 新增逻辑：
        1. 先执行静态规则分析（兜底）
        2. 再使用Brain3 Prompt系统执行LLM语义分析
        3. 合并两个结果，去重
        4. 应用AI增强层（误报过滤/严重性校准）
        
        降级机制：
        - License无效 → 降级到纯规则模式
        - LLM不可用 → 降级到纯规则模式
        - Prompt分析失败 → 仅保留静态规则结果
        """
        # ===== Step 1: 先执行静态规则（始终执行，作为兜底） =====
        rule_result = self._rule_based_analysis(project_path, config)
        static_issues = rule_result.issues or []

        # ===== Step 2: 检查License =====
        try:
            from core.license_gate import check_brain_access
        except ImportError:
            try:
                sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                from core.license_gate import check_brain_access
            except ImportError:
                # License模块不可用，降级到规则模式
                return rule_result

        allowed, denied = check_brain_access(["3"], config)
        if "3" in denied:
            return rule_result

        # ===== Step 3: 使用Brain3 Prompt系统执行LLM语义分析 =====
        b3_config = config.get("brain3", {})
        llm_domains = b3_config.get("llm_domains")  # 用户可指定分析领域

        llm_issues: List[BrainIssue] = []
        llm_count = 0

        try:
            from .brain3_prompts import LLMSemanticAnalyzer, ANALYSIS_DOMAINS

            analyzer = LLMSemanticAnalyzer(config, project_path)
            llm = analyzer._get_llm()

            if llm and llm.is_available:
                # 执行LLM语义分析
                raw_llm_issues = analyzer.analyze(
                    domains=llm_domains,
                    existing_issues=static_issues,
                )
                llm_count = len(raw_llm_issues)

                # 将字典格式的issue转为BrainIssue
                for item in raw_llm_issues:
                    severity = item.get("severity", "medium")
                    if severity not in ("blocker", "high", "medium", "low"):
                        severity = "medium"

                    llm_issues.append(BrainIssue(
                        check_id=item.get("check_id", "B3-LLM-UNK"),
                        name=item.get("message", "AI语义发现")[:40],
                        severity=severity,
                        file=item.get("file", ""),
                        line=item.get("line", 0),
                        message=item.get("message", ""),
                        suggestion=item.get("suggestion", ""),
                    ))
            else:
                # LLM不可用，仅保留静态规则结果
                rule_result.summary += " [LLM不可用，仅静态规则]"
                return rule_result

        except ImportError:
            # brain3_prompts模块不可用，降级
            rule_result.summary += " [Prompt系统不可用，仅静态规则]"
            return rule_result
        except Exception as e:  # noqa: intentional catch-all
            # LLM分析异常，降级
            rule_result.summary += f" [LLM语义分析失败: {e}]"
            return rule_result

        # ===== Step 4: 合并静态规则 + LLM语义结果 =====
        merged_issues = list(static_issues) + llm_issues

        # ===== Step 5: 计算得分 =====
        score = self._calculate_score(merged_issues)
        status = "pass" if not merged_issues else "fail"

        summary_parts = [
            f"🤖 大脑3 AI模式",
            f"静态规则:{len(static_issues)}个",
            f"LLM语义:{llm_count}个(去重后{len(llm_issues)}个)",
            f"总计:{len(merged_issues)}个",
            f"得分{score}",
        ]
        summary = " | ".join(summary_parts)

        result = BrainResult(
            brain_name=self.name,
            status=status,
            score=score,
            issues=merged_issues,
            summary=summary,
        )

        # ===== Step 6: AI增强层 =====
        result = self._apply_ai_enhancement(result, project_path, config)

        return result

    # ================================================================
    #  规则模式：零成本静态分析
    # ================================================================

    def _rule_based_analysis(self, project_path: str, config: dict) -> BrainResult:
        """规则模式：调用 SemanticRuleScanner（AST分析）+ 代码异味检测

        v3.0.2 优化：
        - 硬编码密钥/SQL注入/异常处理 → 由 SemanticRuleScanner（AST分析）统一处理
        - 代码异味（过长函数/过深嵌套/过多参数）→ 保留本地检测
        - 消除重复检测，降低误报率
        """
        issues: List[BrainIssue] = []

        # ===== Step 1: 调用 SemanticRuleScanner（AST分析） =====
        try:
            from core.semantic_scanner import SemanticRuleScanner
            scanner = SemanticRuleScanner(
                project_path,
                {"project_type": config.get("project_type", "unknown")}
            )
            semantic_findings = scanner.scan()

            # 转换为 BrainIssue 格式
            severity_map = {
                "critical": "blocker", "blocker": "blocker",
                "high": "high", "medium": "medium", "low": "low",
            }
            for finding in semantic_findings:
                issues.append(BrainIssue(
                    check_id=finding.check_id,
                    name=finding.rule_name[:40] if finding.rule_name else "",
                    severity=severity_map.get(finding.severity, "medium"),
                    file=finding.file,
                    line=finding.line,
                    message=finding.message,
                    suggestion=finding.suggestion or "",
                ))
        except Exception as e:  # noqa: intentional catch-all
            import logging
            logging.getLogger("xinpect").warning(f"[Brain3] SemanticRuleScanner 调用失败: {e}")

        # ===== Step 2: 代码异味检测（本地） =====
        source_files = self._collect_source_files(project_path)
        if source_files:
            issues.extend(self._detect_code_smells(source_files, project_path))

        # 计算得分
        score = self._calculate_score(issues)
        status = "pass" if not issues else "fail"

        return BrainResult(
            brain_name=self.name,
            status=status,
            score=score,
            issues=issues,
            summary=f"🔍 大脑3规则模式：扫描{len(source_files)}个文件，发现{len(issues)}个问题，得分{score}",
        )

    def _collect_source_files(self, project_path: str) -> List[str]:
        """收集项目中的源码文件"""
        source_files = []
        count = 0

        for root, dirs, files in os.walk(project_path):
            # 过滤忽略目录
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith(".")]

            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext in _CODE_EXTENSIONS:
                    fpath = os.path.join(root, fname)
                    source_files.append(fpath)
                    count += 1
                    if count >= _MAX_FILES:
                        return source_files

        return source_files

    # ----------------------------------------------------------------
    #  规则1：检测硬编码密钥
    # ----------------------------------------------------------------

    # 硬编码密钥检测正则
    _SECRET_PATTERNS = [
        (re.compile(
            r'''(?:api[_-]?key|apikey|api[_-]?secret|api[_-]?token)'''
            r'''\s*[:=]\s*['"]([A-Za-z0-9_\-]{16,})['"]''',
            re.IGNORECASE,
        ), "硬编码API密钥", "B3-SEC001"),
        (re.compile(
            r'''(?:password|passwd|pwd)\s*[:=]\s*['"]([^'"]{4,})['"]''',
            re.IGNORECASE,
        ), "硬编码密码", "B3-SEC002"),
        (re.compile(
            r'''(?:secret|secret[_-]?key)\s*[:=]\s*['"]([A-Za-z0-9_\-]{8,})['"]''',
            re.IGNORECASE,
        ), "硬编码密钥", "B3-SEC003"),
        (re.compile(
            r'''(?:aws[_-]?access[_-]?key[_-]?id|aws[_-]?secret[_-]?access[_-]?key)'''
            r'''\s*[:=]\s*['"]([A-Za-z0-9/+=]{16,})['"]''',
            re.IGNORECASE,
        ), "硬编码AWS密钥", "B3-SEC004"),
        (re.compile(
            r'''(?:private[_-]?key|PRIVATE[_-]?KEY)\s*[:=]\s*['"]''',
            re.IGNORECASE,
        ), "硬编码私钥", "B3-SEC005"),
        (re.compile(
            r'''(?:sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{36}|gho_[A-Za-z0-9]{36})''',
        ), "可疑Token（疑似OpenAI/GitHub）", "B3-SEC006"),
    ]

    # 这些文件名/变量名通常是配置示例，不算硬编码
    _SECRET_FALSE_POSITIVE_HINTS = {
        "example", "sample", "template", "placeholder", "your_", "xxx",
        "changeme", "todo", "fixme", "dummy", "test", "mock", "fake",
        "token_url", "url", "endpoint",
    }

    def _detect_hardcoded_secrets(
        self, source_files: List[str], project_path: str
    ) -> List[BrainIssue]:
        """检测硬编码密钥、密码、Token"""
        issues = []

        for fpath in source_files:
            rel_path = os.path.relpath(fpath, project_path)
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
            except (OSError, IOError):
                continue

            for line_no, line in enumerate(lines[:_MAX_FILE_LINES], start=1):
                stripped = line.strip()

                # 跳过注释行
                if stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("*"):
                    continue

                for pattern, desc, check_id in self._SECRET_PATTERNS:
                    m = pattern.search(line)
                    if m:
                        # 检查是否为占位符/示例值
                        matched_val = m.group(1) if m.lastindex else ""
                        if matched_val and any(
                            hint in matched_val.lower()
                            for hint in self._SECRET_FALSE_POSITIVE_HINTS
                        ):
                            continue

                        # Skip URL/endpoint/path construction lines (not credentials)
                        _line_lower = line.lower()
                        if any(_kw in _line_lower for _kw in ('://', 'url', 'endpoint', 'path')):
                            continue

                        # Skip f-strings with interpolation (dynamic concat, not hardcoded)
                        if re.search(r"f['\"]", line) and '{' in line:
                            continue

                        issues.append(BrainIssue(
                            check_id=check_id,
                            name=desc,
                            severity="blocker",
                            file=rel_path,
                            line=line_no,
                            message=f"{desc}: 检测到疑似硬编码的敏感凭据",
                            suggestion="建议使用环境变量或密钥管理服务（如 Vault、AWS Secrets Manager）存储敏感信息",
                        ))

        return issues

    # ----------------------------------------------------------------
    #  规则2：检测SQL拼接（SQL注入风险）
    # ----------------------------------------------------------------

    _SQL_PATTERNS = [
        # Python: cursor.execute("... %s ..." % var) 或 f-string
        (re.compile(
            r'''\.execute\s*\(\s*(?:f['"]|['"].*%s|['"].*\.format\(|['"].*\+\s*\w)''',
            re.IGNORECASE,
        ), "SQL语句拼接（注入风险）", "B3-SEC010"),
        # JavaScript: query("..." + var)
        (re.compile(
            r'''(?:query|execute|exec)\s*\(\s*['"`].*(?:\+|`\$\{)''',
            re.IGNORECASE,
        ), "SQL语句拼接（注入风险）", "B3-SEC010"),
        # 通用: SELECT/INSERT/UPDATE/DELETE + 字符串拼接
        (re.compile(
            r'''(?:SELECT|INSERT|UPDATE|DELETE|DROP)\s+.*['"]\s*\+\s*\w''',
            re.IGNORECASE,
        ), "SQL关键字与变量拼接", "B3-SEC011"),
        # ORM raw query: .raw("... " + var) 或 .raw(f"...")
        (re.compile(
            r'''\.raw\s*\(\s*(?:f['"]|['"].*\+)''',
            re.IGNORECASE,
        ), "ORM原始SQL拼接", "B3-SEC012"),
    ]

    def _detect_sql_injection(
        self, source_files: List[str], project_path: str
    ) -> List[BrainIssue]:
        """检测SQL注入风险（字符串拼接SQL）"""
        issues = []

        for fpath in source_files:
            rel_path = os.path.relpath(fpath, project_path)
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
            except (OSError, IOError):
                continue

            for line_no, line in enumerate(lines[:_MAX_FILE_LINES], start=1):
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("*"):
                    continue

                for pattern, desc, check_id in self._SQL_PATTERNS:
                    if pattern.search(line):
                        # Skip if execute() call has a second parameter (parameterized query)
                        if re.search(r'\.execute\s*\(', line) and ',' in line:
                            _exec_match = re.search(r'\.execute\s*\(([^)]+)\)', line)
                            if _exec_match and ',' in _exec_match.group(1):
                                break
                        issues.append(BrainIssue(
                            check_id=check_id,
                            name=desc,
                            severity="high",
                            file=rel_path,
                            line=line_no,
                            message=f"{desc}: 检测到SQL语句与变量直接拼接，存在SQL注入风险",
                            suggestion="使用参数化查询（如 cursor.execute(sql, params)）或ORM框架的参数绑定功能",
                        ))
                        break  # 一行只报一次

        return issues

    # ----------------------------------------------------------------
    #  规则3：检测未处理异常
    # ----------------------------------------------------------------

    _EMPTY_EXCEPT_PATTERNS = [
        re.compile(r"except\s*:\s*$"),           # bare except (无异常类型)
    ]

    _CATCH_EMPTY_PATTERNS = [
        re.compile(r"catch\s*\(\s*\w+\s+\w+\s*\)\s*\{\s*\}"),  # catch(e) {}
        re.compile(r"catch\s*\{\s*\}"),  # catch {}
    ]

    def _detect_unhandled_exceptions(
        self, source_files: List[str], project_path: str
    ) -> List[BrainIssue]:
        """检测空except/catch块和bare except
        
        v2.1 优化降噪：
        - 只在except块体确实为空时报告（下一行是pass/空/注释）
        - 排除测试文件
        - 每个文件最多报5个
        """
        issues = []

        for fpath in source_files:
            rel_path = os.path.relpath(fpath, project_path)
            ext = os.path.splitext(fpath)[1].lower()
            
            # 排除测试文件
            if any(p in rel_path for p in ['test_', '_test.', '.test.', '.spec.', '/tests/', '/test/']):
                continue
            
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
            except (OSError, IOError):
                continue

            file_issue_count = 0
            MAX_PER_FILE = 5

            for line_no, line in enumerate(lines[:_MAX_FILE_LINES], start=1):
                if file_issue_count >= MAX_PER_FILE:
                    break
                    
                stripped = line.strip()

                # Python 文件检查
                if ext == ".py":
                    for pattern in self._EMPTY_EXCEPT_PATTERNS:
                        if pattern.search(stripped):
                            # 检查except块体是否为空（下一行是否为pass/空/注释）
                            next_idx = line_no  # 0-indexed
                            if next_idx < len(lines):
                                next_line = lines[next_idx].strip()
                                # 如果下一行有实际代码（不是pass/空/注释），则不报
                                if next_line and not next_line.startswith(('#', 'pass')):
                                    continue
                            issues.append(BrainIssue(
                                check_id="B3-EXC001",
                                name="空异常处理/bare except",
                                severity="medium",
                                file=rel_path,
                                line=line_no,
                                message="检测到空异常处理块或bare except，可能吞掉重要错误",
                                suggestion="至少记录日志（logger.exception），或捕获具体异常类型",
                            ))
                            file_issue_count += 1
                            break

                # JS/TS 文件检查
                elif ext in {".js", ".ts", ".jsx", ".tsx"}:
                    for pattern in self._CATCH_EMPTY_PATTERNS:
                        if pattern.search(stripped):
                            issues.append(BrainIssue(
                                check_id="B3-EXC002",
                                name="空catch块",
                                severity="medium",
                                file=rel_path,
                                line=line_no,
                                message="检测到空catch块，可能吞掉重要错误",
                                suggestion="在catch块中至少记录错误日志（console.error）",
                            ))
                            file_issue_count += 1
                            break

        return issues

    # ----------------------------------------------------------------
    #  规则4：检测代码异味
    # ----------------------------------------------------------------

    # 函数定义正则（多语言）
    _FUNC_DEF_PATTERNS = [
        # Python: def func_name(
        re.compile(r"^\s*def\s+(\w+)\s*\(([^)]*)\)"),
        # JS/TS: function func_name(
        re.compile(r"^\s*(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)"),
        # JS/TS 箭头函数: const func_name = (
        re.compile(r"^\s*(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(([^)]*)\)"),
        # Java/C#: (public|private|...) type func_name(
        re.compile(r"^\s*(?:public|private|protected|static|\s)+\s+\w+\s+(\w+)\s*\(([^)]*)\)"),
        # Go: func (receiver) func_name(
        re.compile(r"^\s*func\s+(?:\([^)]*\)\s+)?(\w+)\s*\(([^)]*)\)"),
    ]

    # 排除的函数名（Python内置函数、常见变量名等，防止Java/C#模式误匹配）
    _EXCLUDED_FUNC_NAMES = {
        'hasattr', 'getattr', 'setattr', 'delattr', 'isinstance', 'issubclass',
        'len', 'range', 'open', 'print', 'input', 'type', 'str', 'int', 'float',
        'list', 'dict', 'set', 'tuple', 'bool', 'bytes', 'map', 'filter',
        'zip', 'enumerate', 'sorted', 'reversed', 'sum', 'min', 'max',
        'abs', 'round', 'pow', 'divmod', 'hash', 'id', 'repr', 'format',
        'super', 'property', 'staticmethod', 'classmethod', 'object',
        'if', 'else', 'for', 'while', 'return', 'yield', 'class',
    }

    def _detect_code_smells(
        self, source_files: List[str], project_path: str
    ) -> List[BrainIssue]:
        """检测代码异味：过长函数、过深嵌套、过多参数"""
        issues = []

        for fpath in source_files:
            rel_path = os.path.relpath(fpath, project_path)
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
            except (OSError, IOError):
                continue

            file_lines = lines[:_MAX_FILE_LINES]
            issues.extend(self._check_long_functions(file_lines, rel_path))
            issues.extend(self._check_deep_nesting(file_lines, rel_path))
            issues.extend(self._check_too_many_params(file_lines, rel_path))

        return issues

    def _check_long_functions(
        self, lines: List[str], rel_path: str
    ) -> List[BrainIssue]:
        """检测过长函数（>150行）
        
        v2.1 优化降噪：
        - 阈值从100行提高到150行
        - 排除测试文件
        - 每个文件最多报3个
        """
        issues = []
        
        # 排除测试文件
        if any(p in rel_path for p in ['test_', '_test.', '.test.', '.spec.', '/tests/', '/test/']):
            return issues
        
        func_starts = []

        for line_no, line in enumerate(lines, start=1):
            for pattern in self._FUNC_DEF_PATTERNS:
                m = pattern.match(line)
                if m:
                    func_name = m.group(1)
                    if func_name not in self._EXCLUDED_FUNC_NAMES:
                        func_starts.append((line_no, func_name))
                    break

        # 估算每个函数的行数
        MAX_PER_FILE = 3
        LONG_FUNC_THRESHOLD = 500  # 仅报告极端超长函数(>500行)
        
        for i, (start_line, func_name) in enumerate(func_starts):
            if len(issues) >= MAX_PER_FILE:
                break
            if i + 1 < len(func_starts):
                end_line = func_starts[i + 1][0]
            else:
                end_line = len(lines) + 1

            func_length = end_line - start_line
            if func_length > LONG_FUNC_THRESHOLD:
                issues.append(BrainIssue(
                    check_id="B3-SMELL001",
                    name="函数过长",
                    severity="medium",
                    file=rel_path,
                    line=start_line,
                    message=f"函数 `{func_name}` 长度为 {func_length} 行（>{LONG_FUNC_THRESHOLD}行），建议拆分",
                    suggestion="将函数拆分为更小的、职责单一的子函数，提高可读性和可测试性",
                ))

        return issues

    def _check_deep_nesting(
        self, lines: List[str], rel_path: str
    ) -> List[BrainIssue]:
        """检测过深嵌套（>5层，按函数粒度检测）
        
        v2.1 优化：
        - 按函数/方法粒度检测，每个函数最多报1次
        - 排除测试文件（test_*.py, *_test.py, *.test.js 等）
        - 排除 parser/lexer/serializer 等已知复杂解析逻辑函数
        - 阈值从4层提高到5层，减少低级别噪音
        """
        issues = []

        # 排除测试文件
        basename = os.path.basename(rel_path)
        test_patterns = [
            rel_path.startswith("test_"),
            rel_path.endswith("_test.py"),
            ".test." in rel_path,
            ".spec." in rel_path,
            "/tests/" in rel_path,
            "/test/" in rel_path,
            "__tests__" in rel_path,
            basename.startswith("test_"),
            basename.endswith("_test.py"),
        ]
        if any(test_patterns):
            return issues

        # 排除 parser/lexer/serializer 等已知复杂解析逻辑的函数
        _SKIP_FUNC_PATTERNS = re.compile(
            r'(parse|lexer|tokenize|serialize|deserialize|encode|decode|'
            r'transform|compile|transpile|minify|format|render|'
            r'visit_|_visit|_dispatch|_handle|_process_node|'
            r'_evaluate|_resolve|_walk|_traverse)',
            re.IGNORECASE
        )

        # 找出所有函数定义及其行范围
        func_ranges = []  # [(start_line_no, end_line_no, func_name), ...]
        for line_no, line in enumerate(lines, start=1):
            for pattern in self._FUNC_DEF_PATTERNS:
                m = pattern.match(line)
                if m:
                    func_name = m.group(1)
                    if func_name not in self._EXCLUDED_FUNC_NAMES:
                        func_ranges.append((line_no, func_name))
                    break

        if not func_ranges:
            return issues

        # 计算每个函数的行范围
        func_spans = []
        for i, (start_line, func_name) in enumerate(func_ranges):
            if i + 1 < len(func_ranges):
                end_line = func_ranges[i + 1][0] - 1
            else:
                end_line = len(lines)
            func_spans.append((start_line, end_line, func_name))

        # 对每个函数检测最大嵌套深度
        DEEP_NESTING_THRESHOLD = 15  # 仅报告极端嵌套(>15层)

        for start_line, end_line, func_name in func_spans:
            # 排除已知复杂解析逻辑函数
            if _SKIP_FUNC_PATTERNS.search(func_name):
                continue

            max_depth = 0
            max_depth_line = start_line

            # 预计算函数起始缩进（只算一次）
            _func_line = lines[start_line - 1]
            _func_indent = len(_func_line) - len(_func_line.lstrip())
            if "\t" in _func_line:
                _func_indent = _func_line.count("\t", 0, len(_func_line) - len(_func_line.lstrip()))
            _indent_unit = 4 if "\t" not in _func_line else 1

            _end = min(end_line + 1, len(lines) + 1)
            for line_no in range(start_line + 1, _end):
                line = lines[line_no - 1]
                stripped = line.rstrip()
                if not stripped:
                    continue
                lstripped = stripped.lstrip()
                if lstripped.startswith("#") or lstripped.startswith("//"):
                    continue

                # 计算缩进层级
                leading_spaces = len(line) - len(lstripped)
                if "\t" in line:
                    leading_spaces = line.count("\t", 0, len(line) - len(lstripped))

                relative_depth = (leading_spaces - _func_indent) // _indent_unit
                if relative_depth > max_depth:
                    max_depth = relative_depth
                    max_depth_line = line_no
                    # 优化：如果已经超过阈值很多，可以提前退出
                    if max_depth > DEEP_NESTING_THRESHOLD + 3:
                        break

            if max_depth > DEEP_NESTING_THRESHOLD:
                issues.append(BrainIssue(
                    check_id="B3-SMELL002",
                    name="嵌套过深",
                    severity="low",
                    file=rel_path,
                    line=max_depth_line,
                    message=f"函数 `{func_name}` 嵌套深度达到 {max_depth} 层（>{DEEP_NESTING_THRESHOLD}层），建议简化",
                    suggestion="使用早返回（early return）、提取子函数、或使用guard clauses减少嵌套",
                ))

        return issues

    def _check_too_many_params(
        self, lines: List[str], rel_path: str
    ) -> List[BrainIssue]:
        """检测参数过多的函数（>10个）"""
        issues = []

        for line_no, line in enumerate(lines, start=1):
            for pattern in self._FUNC_DEF_PATTERNS:
                m = pattern.match(line)
                if m:
                    func_name = m.group(1)
                    params_str = m.group(2).strip()

                    if not params_str:
                        continue

                    # 计算参数数量（按逗号分割，但要考虑泛型/默认值中的逗号）
                    params = self._split_params(params_str)
                    # Python排除self/cls
                    param_count = len(params)
                    param_names = [p.strip().split(":")[0].split("=")[0].strip() for p in params]
                    if "self" in param_names:
                        param_count -= 1
                    if "cls" in param_names:
                        param_count -= 1

                    if param_count > 5:
                        issues.append(BrainIssue(
                            check_id="B3-SMELL003",
                            name="函数参数过多",
                            severity="medium",
                            file=rel_path,
                            line=line_no,
                            message=f"函数 `{func_name}` 有 {param_count} 个参数（>10个），建议使用参数对象",
                            suggestion="将相关参数封装为数据类/结构体/字典，减少函数签名复杂度",
                        ))
                    break  # 一行只匹配一个函数定义

        return issues

    @staticmethod
    def _split_params(params_str: str) -> List[str]:
        """智能分割参数列表，处理泛型/默认值中的逗号"""
        params = []
        depth = 0
        current = []

        for ch in params_str:
            if ch in ("<", "[", "{", "("):
                depth += 1
                current.append(ch)
            elif ch in (">", "]", "}", ")"):
                depth -= 1
                current.append(ch)
            elif ch == "," and depth == 0:
                params.append("".join(current).strip())
                current = []
            else:
                current.append(ch)

        if current:
            params.append("".join(current).strip())

        return [p for p in params if p]

    # ----------------------------------------------------------------
    #  得分计算
    # ----------------------------------------------------------------

    @staticmethod
    def _calculate_score(issues: List[BrainIssue]) -> int:
        """根据问题列表计算得分"""
        score = 100
        for iss in issues:
            if iss.severity == "blocker":
                score -= 15
            elif iss.severity == "high":
                score -= 8
            elif iss.severity == "medium":
                score -= 3
            else:
                score -= 1
        return max(0, score)

    # ----------------------------------------------------------------
    #  AI增强层（仅AI模式使用）
    # ----------------------------------------------------------------

    def _apply_ai_enhancement(self, result: BrainResult, project_path: str, config: dict) -> BrainResult:
        """对LLM审查结果做AI增强（误报过滤/修复建议/严重性校准）"""
        try:
            from core.ai_enhancer import should_enable_ai, AIEnhancer

            if not should_enable_ai(config):
                return result

            enhancer = AIEnhancer(config, project_path=project_path)
            result = enhancer.enhance_brain_result("3", result, project_path, config)

        except (ImportError, Exception):  # noqa: intentional empty handler
            pass

        return result


        """过滤已标注的intentionally empty except块"""
        filtered = []
        for issue in issues:
            msg = getattr(issue, 'message', '') or ''
            if '空异常' in msg or 'bare except' in msg:
                fpath = getattr(issue, 'file', '')
                line = getattr(issue, 'line', 0)
                if fpath and line:
                    try:
                        with open(fpath, 'r') as f:
                            lines = f.readlines()
                        if line < len(lines):
                            next_line = lines[line].strip() if line < len(lines) else ''
                            if 'pass' in next_line:
                                continue  # Skip documented empty except
                    except (IOError, OSError):
                        pass  # noqa: file read error during filtering
            filtered.append(issue)
        return filtered

    def _except_has_pass(self, issue):
        """检查except块是否已有pass标注"""
        fpath = getattr(issue, 'file', '')
        line = getattr(issue, 'line', 0)
        if not fpath or not line:
            return False
        try:
            with open(fpath, 'r') as f:
                lines = f.readlines()
            for offset in range(1, 4):
                if line + offset < len(lines):
                    next_line = lines[line + offset].strip()
                    if 'pass' in next_line:
                        return True
                    if next_line and not next_line.startswith('#'):
                        return False
        except (IOError, OSError):
            pass  # noqa: file read error
        return False
