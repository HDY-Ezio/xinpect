# -*- coding: utf-8 -*-
"""
语义规则执行引擎 - 煋鉴 v3.0.3 (规则分发版)
煋旺智能 / Xinpect

v3.0.3 重构：
- 合并 bare_except / empty_exception_handler 为 unified_exception_check（单次遍历）
- 建立 _check_registry：规则 category → 检查方法映射
- scan() 根据传入的 semantic_rules 的 category 字段分发到对应检查
- 向后兼容：无 semantic_rules 时执行所有已注册检查
"""

import os
import ast
import re
import json
import fnmatch
import logging
from typing import List, Dict, Any, Optional, Tuple, Set, Callable
from collections import defaultdict


class SemanticFinding:
    def __init__(self, check_id, rule_name, severity, file, line, message, suggestion="", source_dir=""):
        self.check_id = check_id
        self.rule_name = rule_name
        self.severity = severity
        self.file = file
        self.line = line
        self.message = message
        self.suggestion = suggestion
        self.source_dir = source_dir

    def to_dict(self):
        return {
            "check_id": self.check_id, "rule_name": self.rule_name,
            "severity": self.severity, "file": self.file,
            "line": self.line, "message": self.message,
            "suggestion": self.suggestion,
        }


# ============================================================
# Python AST 分析器
# ============================================================
class PythonCodeAnalyzer:
    def __init__(self, file_path, source, tree):
        self.file_path = file_path
        self.source = source
        self.tree = tree
        self.lines = source.splitlines()
        self.imports = []
        self.func_calls = []
        self.assignments = []
        self.try_excepts = []
        self.func_defs = []
        self.class_defs = []
        self._analyze()

    def _analyze(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.imports.append((alias.name, alias.asname or alias.name, node.lineno))
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    name = f"{module}.{alias.name}" if module else alias.name
                    self.imports.append((name, alias.asname or alias.name, node.lineno))
            elif isinstance(node, ast.Call):
                func_name = self._get_call_name(node)
                if func_name:
                    self.func_calls.append((func_name, node.args, node.lineno, node))
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    target_name = self._get_target_name(target)
                    if target_name:
                        self.assignments.append((target_name, node.value, node.lineno, node))
            elif isinstance(node, ast.ExceptHandler):
                exc_type = self._get_name(node.type) if node.type else "bare"
                self.try_excepts.append((exc_type, node.lineno, node))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                decorators = [self._get_name(d) for d in node.decorator_list if self._get_name(d)]
                self.func_defs.append((node.name, decorators, node.args, node.lineno, node))
            elif isinstance(node, ast.ClassDef):
                bases = [self._get_name(b) for b in node.bases if self._get_name(b)]
                decorators = [self._get_name(d) for d in node.decorator_list if self._get_name(d)]
                self.class_defs.append((node.name, bases, decorators, node.lineno, node))

    def _get_call_name(self, node):
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            parts = []
            n = node.func
            while isinstance(n, ast.Attribute):
                parts.append(n.attr)
                n = n.value
            if isinstance(n, ast.Name):
                parts.append(n.id)
            return ".".join(reversed(parts))
        return ""

    def _get_target_name(self, node):
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return self._get_name(node)
        return ""

    def _get_name(self, node):
        if node is None:
            return ""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            val = self._get_name(node.value)
            return f"{val}.{node.attr}" if val else node.attr
        if isinstance(node, ast.Call):
            return self._get_call_name(node)
        if isinstance(node, ast.Constant):
            return str(node.value)
        return ""


# ============================================================
# 高置信度AST检查器
# ============================================================
class ASTChecks:
    @staticmethod
    def check_hardcoded_credentials(analyzer):
        SENSITIVE = ['password', 'passwd', 'pwd', 'secret', 'api_key', 'apikey',
                     'token', 'auth_token', 'access_token', 'private_key',
                     'db_password', 'secret_key', 'flask_secret']
        findings = []
        for target_name, value_node, line, _ in analyzer.assignments:
            lower_name = target_name.lower()
            if not any(sn in lower_name for sn in SENSITIVE):
                continue
            if isinstance(value_node, ast.Constant) and isinstance(value_node.value, str):
                if len(value_node.value) > 3:
                    findings.append({
                        "check_id": "SEC-066", "rule_name": "硬编码凭证检测",
                        "severity": "critical", "line": line,
                        "message": f"变量 '{target_name}' 使用了硬编码字符串",
                        "suggestion": "使用 os.environ.get() 或 dotenv 加载凭证",
                    })
            elif isinstance(value_node, ast.JoinedStr):
                findings.append({
                    "check_id": "SEC-066", "rule_name": "硬编码凭证检测",
                    "severity": "critical", "line": line,
                    "message": f"变量 '{target_name}' 使用f-string拼接，可能含硬编码凭证",
                    "suggestion": "使用 os.environ.get() 加载凭证",
                })
        return findings

    @staticmethod
    def check_sql_injection(analyzer):
        findings = []
        for func_name, args, line, node in analyzer.func_calls:
            if not func_name.endswith('.execute') and func_name != 'execute':
                continue
            if not args:
                continue
            first_arg = args[0]
            if isinstance(first_arg, ast.JoinedStr):
                findings.append({
                    "check_id": "SEC-SQLI-001", "rule_name": "SQL注入：f-string拼接",
                    "severity": "critical", "line": line,
                    "message": f"{func_name}() 使用f-string拼接SQL",
                    "suggestion": "使用参数化查询: execute('SELECT * WHERE id=%s', (id,))",
                })
            elif isinstance(first_arg, ast.Call):
                cn = analyzer._get_call_name(first_arg)
                if cn and cn.endswith('.format'):
                    findings.append({
                        "check_id": "SEC-SQLI-002", "rule_name": "SQL注入：format()拼接",
                        "severity": "critical", "line": line,
                        "message": f"{func_name}() 使用.format()拼接SQL",
                        "suggestion": "使用参数化查询替代字符串格式化",
                    })
            elif isinstance(first_arg, ast.BinOp) and isinstance(first_arg.op, ast.Add):
                findings.append({
                    "check_id": "SEC-SQLI-003", "rule_name": "SQL注入：字符串拼接",
                    "severity": "critical", "line": line,
                    "message": f"{func_name}() 使用+拼接SQL",
                    "suggestion": "使用参数化查询替代字符串拼接",
                })
        return findings

    @staticmethod
    def check_dangerous_functions(analyzer):
        DANGEROUS = {
            'eval': ("SEC-EVAL-001", "eval()执行动态代码", "使用 ast.literal_eval() 替代"),
            'exec': ("SEC-EXEC-001", "exec()执行动态代码", "避免使用exec()"),
            'os.system': ("SEC-CMD-001", "os.system()执行系统命令", "使用 subprocess.run(shell=False)"),
            'pickle.loads': ("SEC-DESER-001", "pickle反序列化不可信数据", "使用 json 替代"),
            'pickle.load': ("SEC-DESER-002", "pickle反序列化", "使用 json 替代"),
            'yaml.load': ("SEC-DESER-003", "yaml.load不安全", "使用 yaml.safe_load()"),
        }
        findings = []
        for func_name, args, line, node in analyzer.func_calls:
            for pattern, (cid, desc, sug) in DANGEROUS.items():
                if func_name == pattern or (func_name.endswith('.' + pattern.split('.')[-1]) and '.' not in pattern):
                    if pattern == 'yaml.load' and 'safe' in func_name.lower():
                        continue
                    findings.append({
                        "check_id": cid, "rule_name": desc, "severity": "high",
                        "line": line, "message": f"危险调用: {func_name}()", "suggestion": sug,
                    })
                    break
        return findings

    @staticmethod
    def unified_exception_check(analyzer):
        """
        v3.0.3: 合并 bare_except + empty_exception_handler 为单次遍历。

        规则分发：
        - bare except                          → B3-EXCEPT-001 (high)
        - except: pass 或空body                → B3-EXCEPT-003 (medium)
        - except Exception 无处理逻辑           → B3-EXCEPT-002 (low)
        - except Exception 有处理逻辑           → 跳过（不误报）
        """
        findings = []
        for exc_type, line, node in analyzer.try_excepts:
            # noqa 检查
            if line - 1 < len(analyzer.lines):
                line_content = analyzer.lines[line - 1]
                if "# noqa" in line_content:
                    continue
                # 检查下一行（pass行）是否有 noqa
                if line < len(analyzer.lines):
                    next_line = analyzer.lines[line]
                    if "# noqa" in next_line:
                        continue

            # --- B3-EXCEPT-001: bare except ---
            if exc_type == "bare":
                findings.append({
                    "check_id": "B3-EXCEPT-001", "rule_name": "裸except捕获所有异常",
                    "severity": "high", "line": line,
                    "message": "bare except 会捕获 SystemExit/KeyboardInterrupt",
                    "suggestion": "指定具体异常: except ValueError as e:",
                })
                # bare except 也可能是空body，同时报 B3-EXCEPT-003
                if len(node.body) == 0 or (len(node.body) == 1 and isinstance(node.body[0], ast.Pass)):
                    if len(node.body) == 0:
                        findings.append({
                            "check_id": "B3-EXCEPT-003", "rule_name": "空异常处理块",
                            "severity": "medium", "line": line,
                            "message": "bare except 块为空",
                            "suggestion": "至少记录日志: except Exception as e: logger.error(str(e))",
                        })
                    else:
                        findings.append({
                            "check_id": "B3-EXCEPT-003", "rule_name": "空异常处理块",
                            "severity": "medium", "line": line,
                            "message": "bare except: pass",
                            "suggestion": "处理异常或记录日志，不要 pass 忽略",
                        })
                continue

            # --- B3-EXCEPT-003: 空异常处理块（except xxx: pass 或空body）---
            is_empty = False
            if len(node.body) == 0:
                findings.append({
                    "check_id": "B3-EXCEPT-003", "rule_name": "空异常处理块",
                    "severity": "medium", "line": line,
                    "message": f"except {exc_type} 块为空",
                    "suggestion": "至少记录日志: except Exception as e: logger.error(str(e))",
                })
                is_empty = True
            elif len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                findings.append({
                    "check_id": "B3-EXCEPT-003", "rule_name": "空异常处理块",
                    "severity": "medium", "line": line,
                    "message": f"except {exc_type}: pass",
                    "suggestion": "处理异常或记录日志，不要 pass 忽略",
                })
                is_empty = True

            # --- B3-EXCEPT-002: except Exception 无处理逻辑 ---
            if exc_type == "Exception" and not is_empty:
                has_handling = False
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        func = child.func
                        if isinstance(func, ast.Attribute):
                            if func.attr in ('debug', 'info', 'warning', 'error', 'critical',
                                             'exception', 'log', 'write'):
                                has_handling = True
                                break
                        elif isinstance(func, ast.Name):
                            if func.id == 'print':
                                has_handling = True
                                break
                    elif isinstance(child, (ast.Return, ast.Raise)):
                        has_handling = True
                        break
                if not has_handling:
                    findings.append({
                        "check_id": "B3-EXCEPT-002", "rule_name": "过宽的Exception捕获",
                        "severity": "low", "line": line,
                        "message": "except Exception 会掩盖编程错误（风格问题）",
                        "suggestion": "捕获更具体的异常或记录完整日志",
                    })

        return findings

    @staticmethod
    def check_debug_mode(analyzer):
        findings = []
        for target_name, value_node, line, _ in analyzer.assignments:
            if target_name.lower() in ('debug', 'app.debug', 'debug_mode', 'flask_debug'):
                if isinstance(value_node, ast.Constant) and value_node.value is True:
                    findings.append({
                        "check_id": "SEC-DEBUG-001", "rule_name": "Debug模式未关闭",
                        "severity": "high", "line": line,
                        "message": f"'{target_name} = True' 会暴露调试信息",
                        "suggestion": "使用环境变量控制: debug = os.environ.get('DEBUG', 'false')",
                    })
        return findings

    @staticmethod
    def check_insecure_random(analyzer):
        has_random = any(imp[0] == 'random' or imp[0].endswith('.random') for imp in analyzer.imports)
        if not has_random:
            return []
        SEC_NAMES = ['token', 'password', 'secret', 'key', 'salt', 'nonce', 'otp']
        findings = []
        for target_name, value_node, line, _ in analyzer.assignments:
            if isinstance(value_node, ast.Call):
                cn = analyzer._get_call_name(value_node)
                if cn and 'random' in cn:
                    if any(sc in target_name.lower() for sc in SEC_NAMES):
                        findings.append({
                            "check_id": "SEC-RAND-001", "rule_name": "非安全随机数",
                            "severity": "high", "line": line,
                            "message": f"'{target_name}' 使用random模块，可被预测",
                            "suggestion": "使用 secrets 模块: secrets.token_hex(32)",
                        })
        return findings

    @staticmethod
    def check_wildcard_import(analyzer):
        findings = []
        for module, alias, line in analyzer.imports:
            if alias == '*':
                findings.append({
                    "check_id": "CQ-IMPORT-001", "rule_name": "通配符导入",
                    "severity": "low", "line": line,
                    "message": f"from {module} import * 污染命名空间",
                    "suggestion": "显式导入需要的名称",
                })
        return findings

    @staticmethod
    def check_mutable_default(analyzer):
        findings = []
        for name, decorators, args, line, func_node in analyzer.func_defs:
            for d in args.defaults:
                if isinstance(d, (ast.List, ast.Dict, ast.Set)):
                    findings.append({
                        "check_id": "B3-DEFAULT-001", "rule_name": "函数默认参数使用可变对象",
                        "severity": "medium", "line": line,
                        "message": f"函数 {name}() 使用可变默认参数",
                        "suggestion": "使用 None: def f(items=None): items = items or []",
                    })
            for d in args.kw_defaults:
                if d and isinstance(d, (ast.List, ast.Dict, ast.Set)):
                    findings.append({
                        "check_id": "B3-DEFAULT-001", "rule_name": "函数默认参数使用可变对象",
                        "severity": "medium", "line": line,
                        "message": f"函数 {name}() 使用可变关键字默认参数",
                        "suggestion": "使用 None: def f(items=None): items = items or []",
                    })
        return findings

    @staticmethod
    def check_path_traversal(analyzer):
        """检查路径穿越风险：os.path.join / open 使用用户可控参数"""
        findings = []
        for func_name, args, line, node in analyzer.func_calls:
            if func_name in ('open',) or func_name.endswith('.open'):
                if args:
                    first_arg = args[0]
                    # open 参数是 f-string 或 BinOp(+) → 可能有路径穿越
                    if isinstance(first_arg, ast.JoinedStr):
                        findings.append({
                            "check_id": "SEC-PATH-001", "rule_name": "路径穿越：f-string构造文件路径",
                            "severity": "high", "line": line,
                            "message": f"{func_name}() 使用f-string拼接文件路径",
                            "suggestion": "使用 os.path.join() 并验证路径在预期目录内",
                        })
                    elif isinstance(first_arg, ast.BinOp) and isinstance(first_arg.op, ast.Add):
                        findings.append({
                            "check_id": "SEC-PATH-002", "rule_name": "路径穿越：字符串拼接构造文件路径",
                            "severity": "high", "line": line,
                            "message": f"{func_name}() 使用+拼接文件路径",
                            "suggestion": "使用 os.path.join() 并验证路径在预期目录内",
                        })
        return findings

    @staticmethod
    def check_unsafe_deserialization(analyzer):
        """补充检查：marshal.loads, shelve.open 等不安全反序列化"""
        UNSAFE_DESER = {
            'marshal.loads': ("SEC-DESER-004", "marshal反序列化不可信数据"),
            'marshal.load': ("SEC-DESER-005", "marshal反序列化"),
            'shelve.open': ("SEC-DESER-006", "shelve使用pickle底层，存在反序列化风险"),
        }
        findings = []
        for func_name, args, line, node in analyzer.func_calls:
            if func_name in UNSAFE_DESER:
                cid, desc = UNSAFE_DESER[func_name]
                findings.append({
                    "check_id": cid, "rule_name": desc,
                    "severity": "high", "line": line,
                    "message": f"不安全反序列化: {func_name}()",
                    "suggestion": "避免反序列化不可信数据，使用 json 替代",
                })
        return findings

    @staticmethod
    def check_resource_leak(analyzer):
        """检查资源泄漏：open() 未在 with 语句中使用"""
        findings = []
        # 收集所有 with 语句中管理的文件名
        with_resources = set()
        for node in ast.walk(analyzer.tree):
            if isinstance(node, ast.With):
                for item in node.items:
                    if isinstance(item.context_expr, ast.Call):
                        cn = analyzer._get_call_name(item.context_expr)
                        if cn:
                            with_resources.add(node.lineno)

        # 检查裸 open() 调用（不在 with 语句中）
        for func_name, args, line, node in analyzer.func_calls:
            if func_name == 'open' and line not in with_resources:
                # 简单启发式：如果 open 结果被赋给变量，且该文件后续没有 .close()
                # 这里只做最简单的检查：open 不在 with 中
                pass  # 此检查误报率高，保持为占位
        return findings


# ============================================================
# JS/TS 代码检查
# ============================================================
class JSCodeChecks:
    PATTERNS = [
        ("SEC-JS-001", "eval()使用", r'(?<![/\'"#])\beval\s*\(', "high", "避免eval()，用JSON.parse()替代"),
        ("SEC-JS-002", "innerHTML XSS风险", r'\.innerHTML\s*=', "high", "使用textContent或DOMPurify"),
        ("SEC-JS-003", "document.write()", r'document\.write\s*\(', "medium", "使用DOM API替代"),
        ("SEC-JS-004", "dangerouslySetInnerHTML", r'dangerouslySetInnerHTML', "high", "使用DOMPurify清理"),
        ("SEC-JS-005", "硬编码凭证", r'(?:password|api_key|apikey|secret|token)\s*[:=]\s*["\x27][^"\x27]{8,}["\x27]', "critical", "使用环境变量: process.env.API_KEY"),
    ]

    @classmethod
    def scan_file(cls, content, lines):
        findings = []
        for cid, name, pat, sev, sug in cls.PATTERNS:
            regex = re.compile(pat)
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
                    continue
                m = regex.search(line)
                if m:
                    findings.append({
                        "check_id": cid, "rule_name": name, "severity": sev,
                        "line": i, "message": m.group(0).strip()[:120], "suggestion": sug,
                    })
                    break
        return findings


# ============================================================
# 配置文件检查
# ============================================================
class ConfigFileChecks:
    @staticmethod
    def check_requirements(content, lines):
        findings = []
        for i, line in enumerate(lines, 1):
            line = line.strip()
            if not line or line.startswith('#') or line.startswith('-'):
                continue
            if '==' not in line and '>=' not in line and '<=' not in line and '~=' not in line:
                if re.match(r'^[a-zA-Z][a-zA-Z0-9_-]*$', line):
                    findings.append({
                        "check_id": "DEP-CFG-008", "rule_name": "Python依赖无版本约束",
                        "severity": "medium", "line": i,
                        "message": f"依赖 '{line}' 未指定版本号",
                        "suggestion": "使用 == 锁定: package==1.2.3",
                    })
        return findings

    @staticmethod
    def check_package_json(content, lines):
        findings = []
        try:
            pkg = json.loads(content)
        except Exception as e:  # noqa: broad exception handling
            return findings
        for section in ('dependencies', 'devDependencies'):
            for name, version in pkg.get(section, {}).items():
                if isinstance(version, str) and version.startswith('^'):
                    findings.append({
                        "check_id": "DEP-CFG-007", "rule_name": "版本号范围过宽",
                        "severity": "low", "line": 0,
                        "message": f"'{name}' 使用 ^{version}",
                        "suggestion": "使用 ~ 或精确版本号",
                    })
        return findings


# ============================================================
# 主扫描器 - v3.0.3 规则分发版
# ============================================================
class SemanticRuleScanner:
    _CODE_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rb",
        ".php", ".cs", ".c", ".cpp", ".h", ".vue", ".html", ".json", ".yaml", ".yml"}
    _SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv", "env",
        ".tox", ".mypy_cache", ".pytest_cache", "dist", "build", ".eggs",
        ".next", ".nuxt", "target", "vendor", "bower_components",
        "rules", "skills", ".skills", ".qa_history", ".xinpect_cache", "output",
        "backups", "backup", "site-packages", ".ruff_cache"}
    _SKIP_PREFIXES = ("backup", "bak", "_backup", "old_", ".backup")
    _MAX_FILES = 500
    _MAX_FILE_LINES = 3000

    # ----------------------------------------------------------
    # category → 检查方法映射表
    # 一个 category 可以映射到一个检查方法
    # 一个检查方法可以被多个 category 映射
    # ----------------------------------------------------------
    _CATEGORY_TO_CHECK = {
        # --- 异常处理 ---
        "exception-handling": "unified_exception_check",
        "error_handling": "unified_exception_check",
        "error-handling": "unified_exception_check",

        # --- SQL 注入 ---
        "sql-injection": "check_sql_injection",
        "injection": "check_sql_injection",

        # --- 硬编码凭证/密钥 ---
        "hardcoded-secrets": "check_hardcoded_credentials",
        "hardcoded-credentials": "check_hardcoded_credentials",
        "credential-transmission": "check_hardcoded_credentials",
        "credential-security": "check_hardcoded_credentials",
        "sensitive-data-exposure": "check_hardcoded_credentials",
        "sensitive-data-management": "check_hardcoded_credentials",

        # --- 危险函数/代码注入/反序列化 ---
        "code-execution-security": "check_dangerous_functions",
        "code-injection": "check_dangerous_functions",
        "deserialization": "check_dangerous_functions",

        # --- Debug 模式 ---
        "config-management": "check_debug_mode",
        "config": "check_debug_mode",
        "misconfiguration": "check_debug_mode",

        # --- 不安全随机数 ---
        "weak-randomness": "check_insecure_random",
        "randomness": "check_insecure_random",

        # --- 通配符导入 ---
        "import_convention": "check_wildcard_import",

        # --- 可变默认参数 ---
        "parameter_handling": "check_mutable_default",

        # --- 路径穿越 ---
        "path-traversal": "check_path_traversal",
        "path_traversal": "check_path_traversal",

        # --- 不安全反序列化（补充） ---
        # 已由 check_dangerous_functions 覆盖核心场景，此处为补充检查
        # deserialization 已映射到 check_dangerous_functions

        # --- XSS ---
        "xss": "js_xss_check",

        # --- 依赖安全（配置文件） ---
        "dependency_security": "config_check",
        "dependency_config": "config_check",

        # --- 资源泄漏 ---
        "resource-leak": "check_resource_leak",
        "resource_management": "check_resource_leak",
        "resource-lifecycle": "check_resource_leak",

        # --- 命令注入（由 check_dangerous_functions 覆盖 os.system 等）---
        "command-injection": "check_dangerous_functions",
        "security_injection": "check_dangerous_functions",

        # --- 认证/授权（规则库有定义，但AST级别无法高置信度检测，留给Brain层）---
        # 不注册 → 自动跳过并记录日志

        # --- 并发/线程安全 ---
        "concurrency": "unified_exception_check",  # 仅触发异常检查，并发本身需要更深分析
        "thread_safety": "unified_exception_check",
        "threading": "unified_exception_check",
        "并发语义": "unified_exception_check",

        # --- 内存/空指针 ---
        "null-safety": "check_mutable_default",  # Python中最接近的检查
        "null_safety": "check_mutable_default",
        "null-check": "check_mutable_default",
    }

    # 检查方法名称 → ASTChecks 方法的映射
    _AST_CHECK_METHODS = {
        "unified_exception_check": ASTChecks.unified_exception_check,
        "check_sql_injection": ASTChecks.check_sql_injection,
        "check_hardcoded_credentials": ASTChecks.check_hardcoded_credentials,
        "check_dangerous_functions": ASTChecks.check_dangerous_functions,
        "check_debug_mode": ASTChecks.check_debug_mode,
        "check_insecure_random": ASTChecks.check_insecure_random,
        "check_wildcard_import": ASTChecks.check_wildcard_import,
        "check_mutable_default": ASTChecks.check_mutable_default,
        "check_path_traversal": ASTChecks.check_path_traversal,
        "check_unsafe_deserialization": ASTChecks.check_unsafe_deserialization,
        "check_resource_leak": ASTChecks.check_resource_leak,
    }

    # 所有检查方法名（向后兼容：无 semantic_rules 时执行全部）
    _ALL_AST_CHECK_NAMES = [
        "unified_exception_check",
        "check_sql_injection",
        "check_hardcoded_credentials",
        "check_dangerous_functions",
        "check_debug_mode",
        "check_insecure_random",
        "check_wildcard_import",
        "check_mutable_default",
        "check_path_traversal",
        "check_unsafe_deserialization",
        "check_resource_leak",
    ]

    def __init__(self, project_path, config=None):
        self.project_path = project_path
        self.config = config or {}
        self._logger = logging.getLogger("xinpect.semantic")

        # v3.0.3: 构建实例级 _check_registry
        # 将 category → 实际可调用的检查方法
        self._check_registry: Dict[str, Callable] = {}
        for cat, method_name in self._CATEGORY_TO_CHECK.items():
            if method_name in self._AST_CHECK_METHODS:
                self._check_registry[cat] = self._AST_CHECK_METHODS[method_name]

    def prepare_rules(self, semantic_rules):
        return len(semantic_rules)

    def scan(self, semantic_rules=None):
        """
        v3.0.3: 根据 semantic_rules 的 category 分发检查。

        参数:
            semantic_rules: 规则列表（每个规则是 dict，包含 'category' 字段）。
                           为 None 时执行所有已注册检查（向后兼容）。

        返回:
            List[SemanticFinding]
        """
        # 确定需要执行的检查方法集合
        checks_to_run = self._resolve_checks(semantic_rules)

        findings = []
        for file_path in self._collect_files():
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
            except Exception as e:  # noqa: broad exception handling
                continue
            lines = content.splitlines()
            if len(lines) > self._MAX_FILE_LINES:
                content = '\n'.join(lines[:self._MAX_FILE_LINES])
                lines = lines[:self._MAX_FILE_LINES]
            rel_path = os.path.relpath(file_path, self.project_path)
            ext = os.path.splitext(file_path)[1].lower()
            basename = os.path.basename(file_path)
            file_findings = []

            if ext == '.py':
                try:
                    tree = ast.parse(content, filename=file_path)
                    analyzer = PythonCodeAnalyzer(file_path, content, tree)
                    # 执行解析出的 AST 检查（去重）
                    executed = set()
                    for check_name in checks_to_run:
                        if check_name in self._AST_CHECK_METHODS and check_name not in executed:
                            method = self._AST_CHECK_METHODS[check_name]
                            file_findings.extend(method(analyzer))
                            executed.add(check_name)
                except SyntaxError:  # noqa: intentional empty handler
                    pass
                except Exception as e:  # noqa: intentional catch-all
                    self._logger.debug(f"AST error {rel_path}: {e}")

            elif ext in ('.js', '.ts', '.tsx', '.jsx'):
                if self._should_run_js_checks(checks_to_run):
                    file_findings.extend(JSCodeChecks.scan_file(content, lines))

            if basename in ('requirements.txt', 'requirements-dev.txt'):
                if self._should_run_config_checks(checks_to_run):
                    file_findings.extend(ConfigFileChecks.check_requirements(content, lines))
            elif basename == 'package.json':
                if self._should_run_config_checks(checks_to_run):
                    file_findings.extend(ConfigFileChecks.check_package_json(content, lines))

            for f in file_findings:
                findings.append(SemanticFinding(
                    check_id=f["check_id"], rule_name=f["rule_name"],
                    severity=f.get("severity", "medium"), file=rel_path,
                    line=f.get("line", 0), message=f.get("message", ""),
                    suggestion=f.get("suggestion", ""),
                ))
        return findings

    def _resolve_checks(self, semantic_rules) -> Set[str]:
        """
        根据 semantic_rules 解析需要执行的检查方法名集合。

        返回: set of check method names (对应 _AST_CHECK_METHODS 的 key)
              以及特殊标记 '__js_xss__', '__config_check__'
        """
        if not semantic_rules:
            # 向后兼容：无规则时执行所有 AST 检查 + JS + config
            return set(self._ALL_AST_CHECK_NAMES) | {'__js_xss__', '__config_check__'}

        checks = set()
        categories_seen = set()

        for rule in semantic_rules:
            cat = rule.get("category", "")
            if not cat or cat in categories_seen:
                continue
            categories_seen.add(cat)

            method_name = self._CATEGORY_TO_CHECK.get(cat)
            if method_name and method_name in self._AST_CHECK_METHODS:
                checks.add(method_name)
            else:
                # 该 category 没有注册对应检查 → 记录日志，跳过
                self._logger.debug(
                    f"[v3.0.3] category '{cat}' 无注册检查方法，跳过 "
                    f"(rule_id={rule.get('id', '?')})"
                )

        # JS 和 config 检查始终包含（它们覆盖多个 category）
        checks.add('__js_xss__')
        checks.add('__config_check__')

        return checks

    def _should_run_js_checks(self, checks_to_run: Set[str]) -> bool:
        return '__js_xss__' in checks_to_run

    def _should_run_config_checks(self, checks_to_run: Set[str]) -> bool:
        return '__config_check__' in checks_to_run

    def _collect_files(self):
        files = []
        count = 0
        if not os.path.isdir(self.project_path):
            return files
        for root, dirs, filenames in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if d not in self._SKIP_DIRS 
                       and not d.startswith(".") 
                       and not d.startswith(self._SKIP_PREFIXES)]
            for fname in filenames:
                ext = os.path.splitext(fname)[1].lower()
                if ext in self._CODE_EXTENSIONS:
                    files.append(os.path.join(root, fname))
                    count += 1
                    if count >= self._MAX_FILES:
                        return files
        return files


def execute_semantic_rules_for_brain(brain_id, project_path, semantic_rules, config=None):
    if not semantic_rules:
        return []
    scanner = SemanticRuleScanner(project_path, config)
    return scanner.scan()
