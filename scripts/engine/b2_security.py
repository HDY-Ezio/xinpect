# -*- coding: utf-8 -*-
"""
B2: 安全与依赖审计引擎（免费版）
- 入门级安全检测
- 硬编码密钥/密码检测
- SQL注入/XSS/命令注入检测
- 反序列化漏洞检测
- 裸外发检测（SEC-HTTP-UNSAFE-CLIENT）：检测未走统一安全HTTP客户端的直接requests/httpx调用
- 【付费版】支付签名安全检测等深度检测
- 依赖安全审计（DEP-SEC-xxx）：已知漏洞依赖、版本锁定检测
- 配置安全审计（CFG-SEC-xxx）：硬编码密钥、调试模式等
- Dockerfile安全（DEP-DOCKER-xxx）：root用户、latest标签等

修复 v4.6.1 Bug 1: name '_HAS_CONTEXT_ANALYZER' is not defined
原因：全局变量未初始化
修复：使用模块级变量显式初始化

修复 v4.6.1 Bug 2: name 'hashlib' is not defined
原因：import 位置不对或遗漏
修复：在文件顶部统一导入 hashlib

【免费版说明】
本引擎为入门级安全检测，覆盖最常见的安全问题。
深度安全检测（支付签名安全、越权检测、业务逻辑漏洞等）为付费版功能。
"""

import os
import re
from typing import Dict, List

# Bug 1 修复：显式初始化全局变量，避免 undefined
_HAS_CONTEXT_ANALYZER = False





def scan(code_files: Dict[str, str], config: dict = None) -> List[Dict]:
    """B2 安全与依赖审计扫描入口"""
    if config is None:
        config = {}

    issues = []

    # ===== 手写安全检测 =====
    for filepath, content in code_files.items():
        if not content:
            continue
        ext = os.path.splitext(filepath)[1].lower()
        filename = os.path.basename(filepath).lower()

        lines = content.split("\n")

        # --- 代码文件安全检查 ---
        if ext in (".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go",
                   ".rb", ".php", ".sql"):
            # 通用安全检查
            issues.extend(_check_hardcoded_secrets(filepath, content, lines))
            issues.extend(_check_injection(filepath, content, lines, ext))

            # Python 特定安全
            if ext == ".py":
                issues.extend(_check_python_security(filepath, content, lines))
                # 支付签名安全检测为付费版功能

            # JS/TS 特定安全
            if ext in (".js", ".jsx", ".ts", ".tsx"):
                issues.extend(_check_js_security(filepath, content, lines))

        # --- 配置文件安全检查 ---
        if ext in (".yaml", ".yml", ".json", ".env", ".conf", ".properties"):
            issues.extend(_check_config_security(filepath, content, lines))

        # --- 依赖文件安全检查（原B5）---
        if filename in ("requirements.txt", "pipfile", "pyproject.toml", "package.json", "gemfile"):
            issues.extend(_check_dependencies(filepath, content, filename))

        # --- 配置文件扩展安全检查（原B5 CFG-SEC-xxx，更全面的敏感信息检测）---
        if (filename.startswith(".env") or
                filename in ("config.py", "settings.py", "config.json", "application.yaml",
                             "application.yml", "appsettings.json")):
            issues.extend(_check_deps_config_security(filepath, content))

        # --- Dockerfile 安全检查（原B5）---
        if filename == "dockerfile":
            issues.extend(_check_dockerfile_security(filepath, content))

    # 裸外发检测：需要跨文件分析（先找安全HTTP客户端，再找裸调用）
    issues.extend(_check_unsafe_http_client(code_files))

    # 去重
    seen = set()
    unique_issues = []
    for iss in issues:
        key = (iss["check_id"], iss["file"], iss["line"])
        if key not in seen:
            seen.add(key)
            unique_issues.append(iss)

    return unique_issues


def _check_hardcoded_secrets(filepath: str, content: str, lines: List[str]) -> List[Dict]:
    """硬编码密钥/密码检测"""
    issues = []

    secret_patterns = [
        (r'(?i)(?:password|passwd|pwd)\s*[:=]\s*["\']([^"\']{6,})["\']',
         "SEC-AUTH-001", "硬编码密码", "blocker"),
        (r'(?i)(?:api[_-]?key|apikey)\s*[:=]\s*["\']([A-Za-z0-9_\-]{10,})["\']',
         "SEC-AUTH-002", "硬编码API密钥", "critical"),
        (r'(?i)(?:secret|secret[_-]?key|private[_-]?key)\s*[:=]\s*["\']([A-Za-z0-9_\-\/+]{15,})["\']',
         "SEC-AUTH-003", "硬编码密钥", "critical"),
        (r'(?i)(?:token|access[_-]?token)\s*[:=]\s*["\']([A-Za-z0-9_\-\.]{20,})["\']',
         "SEC-AUTH-004", "硬编码Token", "high"),
        (r'AKIA[0-9A-Z]{16}',
         "SEC-AUTH-005", "AWS Access Key", "blocker"),
        (r'(?i)ghp_[A-Za-z0-9]{36}',
         "SEC-AUTH-006", "GitHub Personal Token", "blocker"),
    ]

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # 跳过注释行和示例
        if stripped.startswith(("#", "//", "/*", "*", ";")):
            continue
        if "example" in stripped.lower() or "test" in stripped.lower():
            if "xxx" in stripped.lower() or "your_" in stripped.lower() or "xxxx" in stripped.lower():
                continue

        for pattern, check_id, name, severity in secret_patterns:
            if re.search(pattern, line):
                # 排除占位符（xxxx, *, 123456等）
                match = re.search(pattern, line)
                if match:
                    value = match.group(1) if match.groups() else match.group(0)
                    if value and re.match(r'^[xX\*\-]+$', value):
                        continue
                    if value and len(set(value)) <= 3:
                        continue

                issues.append({
                    "check_id": check_id,
                    "name": name,
                    "severity": severity,
                    "file": filepath,
                    "line": i,
                    "message": f"检测到{name}，代码中不应硬编码敏感凭据",
                    "suggestion": "使用环境变量或密钥管理服务存储敏感信息，代码中只保留引用",
                })
                break  # 每行最多报一个密钥类问题

    return issues


def _check_injection(filepath: str, content: str, lines: List[str], ext: str) -> List[Dict]:
    """注入类漏洞检测（SQL/命令/代码注入）"""
    issues = []

    # SQL 注入 - Python 文件走文件级分析（支持参数化安全模式排除）
    if ext == ".py":
        sql_issues = _check_sql_injection_python(filepath, content, lines)
        issues.extend(sql_issues)
    else:
        # 非 Python 文件保持行级正则
        sql_patterns = [
            (r'f["\'][^"\']*\b(?:SELECT|INSERT|UPDATE|DELETE|DROP|UNION)\b',
             "SEC-INJ-001", "SQL注入风险(f-string拼接)", "blocker"),
            (r'["\'][^"\']*\b(?:SELECT|INSERT|UPDATE|DELETE)\b.*["\']\s*%\s*',
             "SEC-INJ-002", "SQL注入风险(%格式化)", "blocker"),
            (r'["\'][^"\']*\b(?:SELECT|INSERT|UPDATE|DELETE)\b.*["\']\s*\.format\(',
             "SEC-INJ-003", "SQL注入风险(.format拼接)", "blocker"),
            (r'execute\s*\(\s*f["\']',
             "SEC-INJ-004", "SQL注入风险(execute + f-string)", "blocker"),
        ]

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith(("#", "//")):
                continue

            for pattern, check_id, name, severity in sql_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    issues.append({
                        "check_id": check_id,
                        "name": name,
                        "severity": severity,
                        "file": filepath,
                        "line": i,
                        "message": "使用字符串拼接构造 SQL 查询，存在 SQL 注入风险",
                        "suggestion": "使用参数化查询（ORM/prepare statement），禁止字符串拼接 SQL",
                    })
                    break

    # 命令注入
    cmd_patterns = [
        (r'os\.system\s*\(\s*f["\']',
         "SEC-CMD-001", "命令注入风险(os.system + f-string)", "blocker"),
        (r'subprocess\.(?:call|run|Popen)\s*\([^)]*shell\s*=\s*True',
         "SEC-CMD-002", "命令注入风险(shell=True)", "critical"),
        (r'eval\s*\(\s*(?:request|req|input|params)',
         "SEC-CMD-003", "代码注入风险(eval用户输入)", "blocker"),
        (r'exec\s*\(\s*(?:request|req|input|params)',
         "SEC-CMD-004", "代码注入风险(exec用户输入)", "blocker"),
    ]

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith(("#", "//")):
            continue

        for pattern, check_id, name, severity in cmd_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                issues.append({
                    "check_id": check_id,
                    "name": name,
                    "severity": severity,
                    "file": filepath,
                    "line": i,
                    "message": "用户可控数据传入命令执行函数，存在命令/代码注入风险",
                    "suggestion": "避免使用 shell=True；使用参数列表而非字符串；对用户输入做严格白名单校验",
                })
                break

    return issues


def _check_sql_injection_python(filepath: str, content: str, lines: List[str]) -> List[Dict]:
    """Python SQL 注入检测（文件级分析）

    核心改进：区分「不安全的拼接」与「安全的动态 SQL 构建」
    - 安全模式1：execute 调用带有 params 参数（第二个参数是 tuple/list/dict）
    - 安全模式2：f-string 中插入的是全大写常量（TABLE_/FIELD_ 等命名约定）
    - 安全模式3：拼接的是 WHERE/ORDER BY 等 SQL 片段，且后续 execute 有 params
    """
    issues = []
    import re as _re

    # 第一步：收集所有 execute 调用及其参数情况
    # key: sql变量名, value: (行号, 是否有params)
    safe_sql_vars = set()  # 使用了参数化查询的SQL变量名
    execute_lines = set()  # execute 调用所在行号

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue

        # 匹配 cursor.execute(sql_var, params) / db.execute(sql, (...)) 等
        # 判断 execute 调用是否有第二个参数
        exec_match = _re.search(
            r'(?:\.execute|executemany)\s*\(\s*([\w\.]+)\s*,',
            stripped
        )
        if exec_match:
            sql_var = exec_match.group(1)
            # 有第二个参数 → 大概率是参数化查询
            # 进一步判断：第二个参数不是字符串/数字字面量
            after_comma = stripped[exec_match.end():].strip()
            # 如果第二参数以括号/方括号/变量名开头（不是引号），视为有params
            if after_comma and not after_comma.startswith(('"', "'")):
                base_var = sql_var.split(".")[0] if "." in sql_var else sql_var
                safe_sql_vars.add(base_var)
                execute_lines.add(i)
                continue

        # 匹配 execute(sql, params) 中sql是裸变量的情况
        exec_match2 = _re.search(
            r'(?:\.execute|executemany)\s*\(\s*(\w+)\s*,\s*(\w+)',
            stripped
        )
        if exec_match2:
            sql_var = exec_match2.group(1)
            second_arg = exec_match2.group(2)
            # 如果第二参数是变量/tuple/list/dict，视为参数化
            if not _re.match(r'^(True|False|None|\d+|["\'])', second_arg):
                safe_sql_vars.add(sql_var)
                execute_lines.add(i)
                continue

        # 匹配 execute(f"...", params) 内联 f-string + params 形式
        exec_match3 = _re.search(
            r'(?:\.execute|executemany)\s*\(\s*f["\'].*?["\']\s*,\s*(\w+)',
            stripped
        )
        if exec_match3:
            second_arg = exec_match3.group(1)
            if not _re.match(r'^(True|False|None|\d+|["\'])$', second_arg):
                execute_lines.add(i)
                continue

    # 第二步：收集模块级常量（全大写命名的字符串）
    # 用于判断 f-string 中插入的是否为常量
    module_constants = set()
    for line in lines:
        stripped = line.strip()
        # 匹配 TABLE_XXX = "xxx" / FIELD_YYY = 'yyy' 等模块级常量
        const_match = _re.match(r'^([A-Z][A-Z0-9_]*)\s*=\s*["\']', stripped)
        if const_match:
            module_constants.add(const_match.group(1))

    # 第三步：逐行检测 SQL 拼接，排除安全模式
    sql_concat_patterns = [
        (_re.compile(r'f["\'][^"\']*\b(?:SELECT|INSERT|UPDATE|DELETE|DROP|UNION)\b', _re.IGNORECASE),
         "SEC-INJ-001", "SQL注入风险(f-string拼接)", "blocker"),
        (_re.compile(r'["\'][^"\']*\b(?:SELECT|INSERT|UPDATE|DELETE)\b.*["\']\s*%\s*', _re.IGNORECASE),
         "SEC-INJ-002", "SQL注入风险(%格式化)", "blocker"),
        (_re.compile(r'["\'][^"\']*\b(?:SELECT|INSERT|UPDATE|DELETE)\b.*["\']\s*\.format\(', _re.IGNORECASE),
         "SEC-INJ-003", "SQL注入风险(.format拼接)", "blocker"),
        (_re.compile(r'execute\s*\(\s*f["\']', _re.IGNORECASE),
         "SEC-INJ-004", "SQL注入风险(execute + f-string)", "blocker"),
    ]

    # 按函数分组：识别当前所在函数，检查函数内是否有安全execute
    # 简化版：向前看 30 行，向后看 30 行内是否有 execute 带 params
    def _has_safe_execute_nearby(line_idx: int, sql_var_guess: str = "") -> bool:
        """检查附近（前后30行）是否有带 params 的 execute 调用"""
        start = max(0, line_idx - 30)
        end = min(len(lines), line_idx + 30)
        for j in range(start, end):
            if (j + 1) in execute_lines:
                # 进一步确认：附近的 execute 中是否引用了相关变量
                # 如果能猜到变量名则验证，否则只要附近有安全execute就降低置信度
                if sql_var_guess:
                    line_text = lines[j]
                    if sql_var_guess in line_text:
                        return True
                else:
                    return True
        return False

    def _is_constant_fstring(line_text: str) -> bool:
        """判断 f-string 中插入的是否全部为模块级常量"""
        # 提取 f-string 中所有 {...} 表达式
        fstring_match = _re.findall(r'\{([^}]+)\}', line_text)
        if not fstring_match:
            return False
        for expr in fstring_match:
            expr = expr.strip()
            # 排除方法调用、属性访问、运算符
            if _re.search(r'[().+\-*/%=<>!&|]', expr):
                return False
            # 如果是纯变量名，检查是否为模块常量
            if _re.match(r'^[A-Z_][A-Z0-9_]*$', expr):
                if expr in module_constants:
                    continue
                # 全大写命名约定，即使不在常量列表中也大概率是常量
                if len(expr) >= 4 and expr.isupper():
                    continue
            return False
        return True

    def _extract_sql_var_name(line_text: str) -> str:
        """从赋值行中提取SQL变量名：sql = f"SELECT ..." → "sql" """
        m = _re.match(r'(\w+)\s*=\s*[fF]?["\']', line_text.strip())
        if m:
            return m.group(1)
        return ""

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue

        # 排除 docstring 行
        if _re.match(r'^["\']{3}', stripped):
            continue
        # 排除纯字符串行（message/suggestion 等字典值）
        if _re.match(r'^["\'].*["\']\s*,?$', stripped):
            continue

        for pattern, check_id, name, severity in sql_concat_patterns:
            if not pattern.search(line):
                continue

            # 安全排除1：f-string 中全是常量
            if check_id == "SEC-INJ-001" and _is_constant_fstring(line):
                break

            # 安全排除2：附近有带 params 的 execute 调用（参数化查询）
            sql_var = _extract_sql_var_name(line)
            if _has_safe_execute_nearby(i - 1, sql_var):
                # 有参数化查询 → 降为 info 级别提示，不阻断
                issues.append({
                    "check_id": check_id,
                    "name": name + "（参数化模式）",
                    "severity": "low",
                    "file": filepath,
                    "line": i,
                    "message": (
                        "使用字符串拼接构造 SQL，但检测到后续调用使用了参数化查询（params），"
                        "风险相对较低；仍建议避免拼接表名/字段名，确保白名单校验"
                    ),
                    "suggestion": (
                        "表名/字段名使用白名单校验，数据值通过 %s 占位符参数化传递；"
                        "尽量避免动态拼接 SQL"
                    ),
                })
                break

            # 安全排除2.5：execute(f"...", params) 内联 f-string + params 形式
            # 一行内同时有 execute + f-string + params 参数
            if check_id in ("SEC-INJ-001", "SEC-INJ-004"):
                if _re.search(r'(?:\.execute|executemany)\s*\(\s*f["\'].*?["\']\s*,\s*[\(\[\w]', stripped):
                    issues.append({
                        "check_id": check_id,
                        "name": name + "（参数化模式）",
                        "severity": "low",
                        "file": filepath,
                        "line": i,
                        "message": "execute 内联 f-string 构造 SQL，但已传 params 参数，需确认所有值均参数化",
                        "suggestion": "确保所有用户输入通过 params 传递，避免直接拼接到 SQL 中；表名/字段名建议白名单校验",
                    })
                    break

            # 安全排除3：execute 内部 f-string，但紧跟 params
            if check_id == "SEC-INJ-004":
                # execute(f"...", params) 形式（params可以是变量、tuple、list）
                if _re.search(r'execute\s*\(\s*f["\'].*?["\']\s*,\s*[\(\[\w]', stripped):
                    issues.append({
                        "check_id": check_id,
                        "name": name + "（参数化模式）",
                        "severity": "low",
                        "file": filepath,
                        "line": i,
                        "message": "execute 内联 f-string 构造 SQL，但已传 params 参数，需确认所有值均参数化",
                        "suggestion": "确保所有用户输入通过 params 传递，避免直接拼接到 SQL 中",
                    })
                    break

            issues.append({
                "check_id": check_id,
                "name": name,
                "severity": severity,
                "file": filepath,
                "line": i,
                "message": "使用字符串拼接构造 SQL 查询，存在 SQL 注入风险",
                "suggestion": "使用参数化查询（ORM/prepare statement），禁止字符串拼接 SQL",
            })
            break

    return issues


def _check_python_security(filepath: str, content: str, lines: List[str]) -> List[Dict]:
    """Python 特定安全问题"""
    issues = []

    def _is_string_literal_line(s: str) -> bool:
        # 判断一行是不是主要由字符串字面量组成（检测代码的 message/suggestion 等特征）
        s = s.strip()
        # 以引号开头，或者像字典 value: "xxx",
        import re as _re
        # 行里有冒号+引号的字典模式: "key": "yaml.load()",
        if _re.match(r'^["\']?\w+["\']?\s*:\s*["\'].*["\']\s*,?$', s):
            return True
        # 纯字符串赋值: msg = "pickle.load xxx"
        if _re.match(r'^\w+\s*=\s*["\'].*["\']$', s):
            return True
        # 整行在字符串里（双引号包裹，没有函数调用痕迹）
        if _re.match(r'^["\'].*["\']\s*,?$', s):
            return True
        return False


    # pickle 反序列化
    # 排除字符串字面量中的匹配（避免自检悖论：检测代码自身包含特征码字符串）
    _pickle_re = re.compile(r'(?<!["\'\w])pickle\.load[a-z]*\s*\(')
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if _is_string_literal_line(stripped):
            continue
        if _pickle_re.search(stripped):
            # 排除检测代码特征行：in line / in content / .join 等说明是字符串匹配
            if 'in line' in stripped or 'in content' in stripped or '.join' in stripped:
                continue
            issues.append({
                "check_id": "SEC-PY-001",
                "name": "不安全反序列化(pickle)",
                "severity": "critical",
                "file": filepath,
                "line": i,
                "message": "pickle.load() 反序列化不可信数据可导致远程代码执行",
                "suggestion": "使用 JSON 替代 pickle；必须使用时覆盖 Unpickler.find_class 限制可反序列化的类",
            })
            break

    # yaml.load 不带 safe
    _yaml_re = re.compile(r'yaml\.load\s*\(')
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if "safe_load" in stripped:
            continue
        if _is_string_literal_line(stripped):
            continue
        if _yaml_re.search(stripped) and "Loader=" not in stripped:
            # 排除检测代码自身的特征码字符串
            if 'in line' in stripped or 'in content' in stripped or '.join' in stripped:
                continue
            issues.append({
                "check_id": "SEC-PY-002",
                "name": "不安全YAML解析",
                "severity": "high",
                "file": filepath,
                "line": i,
                "message": "yaml.load() 默认可实例化任意对象，存在反序列化漏洞",
                "suggestion": "使用 yaml.safe_load() 替代 yaml.load()",
            })
            break

    # 调试模式
    # 需要同时满足：有 Flask 导入 + 有 debug=True 代码调用（排除字符串字面量）
    _debug_re = re.compile(r'(app|application)\.debug\s*=\s*True|debug\s*=\s*True')
    if "Flask" in content:
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if _is_string_literal_line(stripped):
                continue
            if _debug_re.search(stripped):
                # 排除检测代码自身
                if 'in line' in stripped or 'in content' in stripped:
                    continue
                issues.append({
                    "check_id": "SEC-PY-003",
                    "name": "调试模式开启",
                    "severity": "high",
                    "file": filepath,
                    "line": i,
                    "message": "Flask 调试模式开启，生产环境会暴露交互式调试器和敏感信息",
                    "suggestion": "生产环境关闭 debug 模式，通过环境变量控制",
                })
                break

    # md5/sha1 用于加密
    weak_hash_patterns = [
        ("hashlib.md5(", "SEC-PY-010", "弱哈希算法MD5", "medium"),
        ("hashlib.sha1(", "SEC-PY-011", "弱哈希算法SHA1", "medium"),
    ]
    for pattern, check_id, name, severity in weak_hash_patterns:
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if _is_string_literal_line(stripped):
                continue
            if pattern in strip_string_content(line):
                # 判断是否是加密场景（非完整性校验）
                if "password" in line.lower() or "encrypt" in line.lower() or "crypto" in line.lower():
                    issues.append({
                        "check_id": check_id,
                        "name": name,
                        "severity": "high",
                        "file": filepath,
                        "line": i,
                        "message": f"使用 {name.split('算法')[1]} 做密码加密，算法已被破解",
                        "suggestion": "使用 bcrypt/argon2/scrypt 等专门的密码哈希算法",
                    })
                else:
                    issues.append({
                        "check_id": check_id,
                        "name": name,
                        "severity": severity,
                        "file": filepath,
                        "line": i,
                        "message": f"使用 {name.split('算法')[1]}，碰撞攻击已可行",
                        "suggestion": "如用于安全性要求高的场景，改用 SHA-256 或更强的算法",
                    })
                break

    return issues


def _check_js_security(filepath: str, content: str, lines: List[str]) -> List[Dict]:
    """JS/TS 特定安全问题"""
    issues = []

    # innerHTML / dangerouslySetInnerHTML
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("//"):
            continue
        if "innerHTML" in line or "dangerouslySetInnerHTML" in line:
            issues.append({
                "check_id": "SEC-JS-001",
                "name": "XSS风险(innerHTML)",
                "severity": "high",
                "file": filepath,
                "line": i,
                "message": "使用 innerHTML/dangerouslySetInnerHTML 插入动态内容，存在 XSS 风险",
                "suggestion": "使用 textContent 或框架的安全渲染机制；如必须使用 HTML 内容先做净化(DOMPurify)",
            })
            break

    # eval
    eval_count = sum(1 for line in lines if "eval(" in line and not line.strip().startswith("//"))
    if eval_count > 0:
        issues.append({
            "check_id": "SEC-JS-002",
            "name": "eval使用",
            "severity": "high",
            "file": filepath,
            "line": 1,
            "message": f"使用了 eval() ({eval_count}处)，可导致代码注入和XSS",
            "suggestion": "避免使用 eval，使用 JSON.parse 解析 JSON，用 Function 构造器替代",
        })

    # localStorage 存敏感数据
    if "localStorage.setItem" in content:
        for i, line in enumerate(lines, 1):
            if "localStorage.setItem" in line and ("token" in line.lower() or "password" in line.lower()):
                issues.append({
                    "check_id": "SEC-JS-003",
                    "name": "敏感数据存localStorage",
                    "severity": "medium",
                    "file": filepath,
                    "line": i,
                    "message": "敏感数据(token/password)存储在 localStorage，易被 XSS 窃取",
                    "suggestion": "使用 HttpOnly Cookie 存储敏感凭据，localStorage 仅存非敏感数据",
                })
                break

    return issues


def _check_config_security(filepath: str, content: str, lines: List[str]) -> List[Dict]:
    """配置文件安全检查"""
    issues = []

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith(";"):
            continue

        # 调试模式
        if re.match(r'^DEBUG\s*[:=]\s*true', stripped, re.IGNORECASE):
            issues.append({
                "check_id": "SEC-CFG-001",
                "name": "调试模式开启",
                "severity": "high",
                "file": filepath,
                "line": i,
                "message": "配置文件中调试模式开启，生产环境会暴露敏感信息",
                "suggestion": "生产环境关闭调试模式，通过环境变量区分开发/生产",
            })

    return issues
def strip_string_content(line: str) -> str:
    """剥离行内字符串内容，用空格替换，避免正则匹配到字符串字面量。"""
    result = []
    i = 0
    in_str = False
    str_char = None
    while i < len(line):
        ch = line[i]
        if not in_str:
            if ch == '"' or ch == "'":
                if i + 2 < len(line) and line[i:i+3] == ch * 3:
                    # 三引号整行返回，由上层处理
                    return line
                in_str = True
                str_char = ch
                result.append(ch)
            else:
                result.append(ch)
            i += 1
        else:
            if ch == '\\' and i + 1 < len(line):
                result.append('  ')
                i += 2
                continue
            if ch == str_char:
                in_str = False
                str_char = None
                result.append(ch)
            else:
                result.append(' ')
            i += 1
    return ''.join(result)




# ===================== 规则：裸外发检测 =====================

# 安全HTTP客户端的特征关键词（函数名/类名/文件名）
# 必须明确暗示"安全"或"HTTP客户端封装"用途
_SAFE_HTTP_NAME_PATTERNS = [
    # 安全 + HTTP 相关命名
    re.compile(r'(?i)(safe|secure).*(http|request|client|api)'),
    re.compile(r'(?i)(http|request|api).*(safe|secure|client|utils|helper)'),
    # 明确的HTTP客户端封装命名
    re.compile(r'(?i)^http_?client$'),
    re.compile(r'(?i)^api_?client$'),
    re.compile(r'(?i)^safe_?request$'),
    re.compile(r'(?i)^secure_?request$'),
    re.compile(r'(?i)^httpx_?client$'),
]

# 安全防护特征关键词（函数体内明确存在的安全防护逻辑）
# 注意：timeout/verify 是普通HTTP调用的常见参数，不能作为"安全封装"的判定依据
_SAFE_HTTP_PROTECTION_PATTERNS = [
    re.compile(r'(?i)(whitelist|white_list|allow_list|allowlist)'),
    re.compile(r'(?i)(ssrf|ssrf_protect|ssrf_check)'),
    re.compile(r'(?i)(domain_?check|check_?domain|validate_?domain)'),
    re.compile(r'(?i)(url_?validate|validate_?url|url_?parse.*hostname)'),
    re.compile(r'(?i)(risk|danger|malicious).*(url|domain)'),
]

# requests/httpx 直接调用的正则
_HTTP_DIRECT_CALL_PATTERNS = [
    re.compile(r'(?<!\w)(?:requests|httpx)\s*\.\s*(?:get|post|put|delete|patch|head|options|request)\s*\('),
    re.compile(r'httpx\.Client\s*\('),
    re.compile(r'httpx\.AsyncClient\s*\('),
]


def _name_matches_safe_http(name: str) -> bool:
    """判断名称（函数名/类名/文件名）是否暗示安全HTTP客户端"""
    return any(p.search(name) for p in _SAFE_HTTP_NAME_PATTERNS)


def _has_ssrf_protection(lines: List[str]) -> bool:
    """判断函数体/代码块内是否有明确的SSRF防护逻辑"""
    text = '\n'.join(lines)
    return any(p.search(text) for p in _SAFE_HTTP_PROTECTION_PATTERNS)


def _iter_python_functions(lines: List[str]):
    """
    迭代Python文件中的函数定义，yield (函数名, 起始行号, 结束行号, 缩进前缀, 所属类名)
    简化但相对可靠的实现：基于缩进级别判断函数范围
    """
    current_class = None
    class_indent = ''
    current_func = None
    func_name = ''
    func_start = -1
    func_indent = ''

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        # 类定义
        class_match = re.match(r'^(\s*)class\s+(\w+)', line)
        if class_match:
            # 结束当前函数
            if current_func:
                yield func_name, func_start, i - 1, func_indent, current_class
                current_func = None
            current_class = class_match.group(2)
            class_indent = class_match.group(1)
            continue

        # 函数定义
        func_match = re.match(r'^(\s*)def\s+(\w+)\s*\(', line)
        if func_match:
            # 结束上一个函数
            if current_func:
                yield func_name, func_start, i - 1, func_indent, current_class

            func_indent = func_match.group(1)
            func_name = func_match.group(2)
            func_start = i
            current_func = func_name
            continue

        # 跳过装饰器/空行/注释
        if stripped.startswith('@') or stripped.startswith('#'):
            continue

        # 判断函数是否结束（遇到比函数缩进更浅的非空、非装饰器代码）
        if current_func and i > func_start:
            line_indent = len(line) - len(line.lstrip())
            func_indent_len = len(func_indent)
            if line_indent <= func_indent_len and stripped:
                yield func_name, func_start, i - 1, func_indent, current_class
                current_func = None
                # 如果缩进等于类缩进或更浅，说明类也可能结束
                if current_class and line_indent <= len(class_indent):
                    current_class = None

    # 收尾
    if current_func:
        yield func_name, func_start, len(lines) - 1, func_indent, current_class


def _detect_safe_http_clients(code_files: Dict[str, str]) -> Dict[str, dict]:
    """
    扫描所有Python文件，识别统一的安全HTTP客户端封装。

    判定规则（任一满足即视为安全封装）：
    1. 函数/类名明确暗示"安全HTTP客户端"（如safe_request、SecureHttpClient等），且内部有requests/httpx调用
    2. 文件名明确暗示HTTP工具（如http_utils.py、safe_http.py等），且内部函数包含requests/httpx调用 + SSRF防护逻辑
    3. 函数体内明确包含SSRF防护逻辑（白名单校验、域名检查等），且函数名包含http/request/client

    返回 dict: { 文件路径: {"functions": set(函数名), "classes": set(类名)} }
    """
    safe_clients = {}

    for filepath, content in code_files.items():
        if not filepath.endswith('.py'):
            continue
        if not content:
            continue
        lines = content.split('\n')

        filename = os.path.basename(filepath)
        filename_safe = _name_matches_safe_http(filename)

        file_functions = set()
        file_classes = set()

        for func_name, start, end, indent, cls_name in _iter_python_functions(lines):
            func_body = lines[start:end+1]

            # 判断函数体内是否有 requests/httpx 调用
            has_http_call = False
            for pat in _HTTP_DIRECT_CALL_PATTERNS:
                if any(pat.search(line) for line in func_body):
                    has_http_call = True
                    break

            if not has_http_call:
                continue

            # 判定1：函数名明确暗示安全HTTP
            name_safe = _name_matches_safe_http(func_name)

            # 判定2：类名暗示安全HTTP客户端
            cls_safe = cls_name and _name_matches_safe_http(cls_name)

            # 判定3：文件是HTTP工具文件 + 函数体内有SSRF防护
            body_has_protection = _has_ssrf_protection(func_body)
            file_tool_safe = filename_safe and body_has_protection

            # 判定4：函数体内有SSRF防护 + 函数名包含http/request/api/client
            body_protection_safe = body_has_protection and re.search(
                r'(?i)(http|request|api|client|fetch|call)', func_name
            )

            if name_safe or cls_safe or file_tool_safe or body_protection_safe:
                # 只将明确的安全函数/类加入集合
                # 类内的通用方法名（get/post等）不加入全局安全函数集合，
                # 因为会导致 requests.get() 被误判为安全调用
                # 类内方法的安全排除通过"在安全封装文件内部"机制实现
                if not cls_name:
                    # 独立函数才加入函数集合
                    file_functions.add(func_name)
                if cls_name:
                    file_classes.add(cls_name)

        if file_functions or file_classes:
            safe_clients[filepath] = {
                "functions": file_functions,
                "classes": file_classes,
            }

    return safe_clients


def _check_unsafe_http_client(code_files: Dict[str, str]) -> List[Dict]:
    """
    裸外发检测（SEC-HTTP-UNSAFE-CLIENT）
    - 如果项目存在统一安全HTTP客户端封装，则检测直接调用requests/httpx的地方
    - 封装函数内部的调用不计入
    - 如果项目没有统一封装，不报告（避免误报）
    """
    issues = []

    # 第一步：识别所有安全HTTP客户端
    safe_clients = _detect_safe_http_clients(code_files)
    if not safe_clients:
        # 没有安全封装，不报告（宁漏报不误报）
        return issues

    # 收集安全封装文件中的安全函数/类方法行范围
    safe_func_ranges = {}  # {filepath: [(start, end, func_name), ...]}
    for fpath, info in safe_clients.items():
        if fpath not in code_files:
            continue
        lines = code_files[fpath].split('\n')
        ranges = []
        for func_name, start, end, indent, cls_name in _iter_python_functions(lines):
            # 独立安全函数 → 加入排除范围
            if func_name in info["functions"]:
                ranges.append((start, end, func_name))
            # 安全类中的所有方法 → 全部加入排除范围（类内封装调用）
            elif cls_name and cls_name in info["classes"]:
                ranges.append((start, end, func_name))
        safe_func_ranges[fpath] = ranges

    # 第二步：扫描所有Python文件，找直接的requests/httpx调用
    for filepath, content in code_files.items():
        if not filepath.endswith('.py'):
            continue
        if not content:
            continue
        lines = content.split('\n')

        # 追踪当前所在函数
        current_func_name = None
        func_start = -1
        func_end = -1
        func_iter = _iter_python_functions(lines)
        func_list = list(func_iter)

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue

            # 跳过字符串字面量行
            if re.match(r'^["\'].*["\']\s*,?$', stripped):
                continue

            # 跳过import语句
            if stripped.startswith('import ') or stripped.startswith('from '):
                continue

            # 跳过docstring
            if stripped.startswith('"""') or stripped.startswith("'''"):
                continue

            # 找到当前行所在函数
            current_func = None
            for fname, fstart, fend, findent, fcls in func_list:
                if fstart <= i - 1 <= fend:
                    current_func = fname
                    break

            # 检测直接调用
            direct_call_match = None
            for pat in _HTTP_DIRECT_CALL_PATTERNS:
                m = pat.search(stripped)
                if m:
                    direct_call_match = m
                    break

            if not direct_call_match:
                continue

            call_text = direct_call_match.group(0).strip()

            # 排除情况1：在安全客户端文件的封装函数内部
            if filepath in safe_func_ranges:
                in_safe_func = False
                for start, end, fname in safe_func_ranges[filepath]:
                    if start <= i - 1 <= end:
                        in_safe_func = True
                        break
                if in_safe_func:
                    continue

            # 排除情况2：这是调用安全封装函数（如 client.safe_get(...) 或 safe_request(...)）
            # 判断当前行是否包含安全函数/类的调用
            is_safe_caller = False
            for fpath, info in safe_clients.items():
                # 检查安全函数调用
                for sname in info["functions"]:
                    # 直接调用安全函数名（from xxx import safe_request 后直接调用）
                    # 安全函数名通常比较独特，不会和requests.get等内置调用冲突
                    if re.search(r'(?<!\w)' + re.escape(sname) + r'\s*\(', stripped) and 'def ' not in stripped:
                        is_safe_caller = True
                        break
                    # 对象方法调用：xxx.safe_request(...)
                    if re.search(r'\.' + re.escape(sname) + r'\s*\(', stripped):
                        is_safe_caller = True
                        break
                if is_safe_caller:
                    break
                # 检查安全类的实例化调用（如 SafeHttpClient()）
                for cname in info["classes"]:
                    if re.search(r'(?<!\w)' + re.escape(cname) + r'\s*\(', stripped):
                        is_safe_caller = True
                        break
                if is_safe_caller:
                    break
            if is_safe_caller:
                continue

            # 计算列号
            col = line.find(call_text.split('(')[0]) + 1
            if col < 1:
                col = 1

            func_info = current_func if current_func else "模块级"
            issues.append({
                "check_id": "SEC-HTTP-UNSAFE-CLIENT",
                "name": "裸外发请求(未走安全HTTP客户端)",
                "severity": "medium",
                "file": filepath,
                "line": i,
                "column": col,
                "message": (
                    f"函数「{func_info}」中直接调用 {call_text.split('(')[0]}()，"
                    f"未经过统一安全HTTP客户端封装，存在SSRF/超时失控风险"
                ),
                "suggestion": (
                    "使用项目内统一的安全HTTP客户端（含SSRF防护、域名白名单、超时控制），"
                    "禁止直接调用 requests/httpx 发起外部请求"
                ),
            })

    return issues


# ===================== 规则：支付签名安全检测 =====================

# 支付相关关键词
_PAYMENT_KEYWORDS = [
    'pay', 'payment', 'wechat', 'wxpay', 'weixin', 'alipay',
    'sign', 'verify', 'callback', 'notify', 'refund',
]


def _is_payment_related(filepath: str, content: str, lines: List[str]) -> bool:
    """判断文件/代码是否与支付相关"""
    # 文件名包含支付关键词
    filename = os.path.basename(filepath).lower()
    for kw in _PAYMENT_KEYWORDS:
        if kw in filename:
            return True

    # 文件内容中包含支付类名/函数名
    content_lower = content.lower()
    payment_indicators = [
        'wechatpay', 'wx_pay', 'alipay', 'ali_pay',
        'payment', 'pay_sign', 'pay_verify',
        'notify_url', 'callback_url', 'pay_callback',
        'rsa_sign', 'rsa_verify',
    ]
    for ind in payment_indicators:
        if ind in content_lower:
            return True

    return False


# 原 B5 依赖与配置审计（合并进 B2 安全与依赖审计）
# ============================================================

def _check_dependencies(filepath: str, content: str, filename: str) -> List[Dict]:
    """依赖安全检查（原 B5 DEP-SEC-xxx）"""
    issues = []

    # 已知漏洞依赖（示例集合，实际应对接漏洞数据库）
    vulnerable_packages = {
        "requests==2.25.0": "CVE-2023-32681",
        "requests==2.25.1": "CVE-2023-32681",
        "django==2.2.": "CVE-2023-36053",
        "flask==1.0.": "CVE-2023-30861",
        "lodash": "CVE-2021-23337",
        "express<4.18": "CVE-2022-24999",
    }

    for pkg_pattern, cve in vulnerable_packages.items():
        if pkg_pattern in content:
            issues.append({
                "check_id": "DEP-SEC-001",
                "name": "已知漏洞依赖",
                "severity": "high",
                "file": filepath,
                "line": 1,
                "message": f"检测到可能存在已知漏洞的依赖包: {pkg_pattern} ({cve})",
                "suggestion": "升级到最新安全版本，使用 pip-audit / npm audit 扫描全量依赖",
            })

    # 未锁定版本（requirements.txt）
    if filename == "requirements.txt":
        for i, line in enumerate(content.split("\n"), 1):
            line_stripped = line.strip()
            if not line_stripped or line_stripped.startswith("#") or line_stripped.startswith("-"):
                continue
            if "==" not in line_stripped and ">=" not in line_stripped and "~=" not in line_stripped:
                if not line_stripped.startswith("git+") and not line_stripped.startswith("http"):
                    issues.append({
                        "check_id": "DEP-SEC-002",
                        "name": "未锁定依赖版本",
                        "severity": "medium",
                        "file": filepath,
                        "line": i,
                        "message": f"依赖 '{line_stripped}' 未锁定具体版本，可能引入不可预期的变更",
                        "suggestion": "使用 == 锁定精确版本，或使用 pip-tools/poetry 管理依赖",
                    })
                    break  # 只报告一次，避免刷屏

    # package.json 中未锁定版本
    if filename == "package.json":
        if '"~' in content or '"^' in content:
            issues.append({
                "check_id": "DEP-SEC-003",
                "name": "依赖版本范围过宽",
                "severity": "low",
                "file": filepath,
                "line": 1,
                "message": "package.json 中使用 ~ 或 ^ 版本范围，可能自动升级到未测试版本",
                "suggestion": "使用 package-lock.json 或 yarn.lock 锁定完整依赖树",
            })

    return issues


def _check_deps_config_security(filepath: str, content: str) -> List[Dict]:
    """配置文件安全检测（原 B5 CFG-SEC-xxx，更全面的敏感信息正则）"""
    issues = []

    sensitive_patterns = [
        (r"password\s*[:=]\s*['\"][^'\"]{3,}['\"]", "硬编码密码", "high"),
        (r"secret\s*[:=]\s*['\"][^'\"]{3,}['\"]", "硬编码密钥", "high"),
        (r"api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9_\-]{10,}['\"]", "硬编码API密钥", "high"),
        (r"token\s*[:=]\s*['\"][A-Za-z0-9_\-]{20,}['\"]", "硬编码Token", "high"),
        (r"DEBUG\s*=\s*True", "调试模式开启", "high"),
        (r"debug:\s*true", "调试模式开启", "high"),
        (r"ALLOWED_HOSTS\s*=\s*\[\s*['\"]\*['\"]", "允许所有Host", "medium"),
    ]

    lines = content.split("\n")
    for pattern, desc, severity in sensitive_patterns:
        for i, line in enumerate(lines, 1):
            if re.search(pattern, line, re.IGNORECASE):
                # 跳过注释行
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith("//") or stripped.startswith(";"):
                    continue
                issues.append({
                    "check_id": "CFG-SEC-001",
                    "name": desc,
                    "severity": severity,
                    "file": filepath,
                    "line": i,
                    "message": f"配置文件中检测到{desc}，存在安全风险",
                    "suggestion": "使用环境变量或密钥管理服务（Vault/AWS Secrets Manager）存储敏感信息",
                })
                break  # 每个模式只报告一次

    return issues


def _check_dockerfile_security(filepath: str, content: str) -> List[Dict]:
    """Dockerfile 安全检测（原 B5 DEP-DOCKER-xxx）"""
    issues = []
    lines = content.split("\n")

    # 使用 root 用户
    has_user = any("USER " in line and not line.strip().startswith("#") for line in lines)
    if not has_user:
        issues.append({
            "check_id": "DEP-DOCKER-001",
            "name": "容器以root运行",
            "severity": "high",
            "file": filepath,
            "line": 1,
            "message": "Dockerfile 中未指定 USER 指令，容器默认以 root 用户运行，安全风险高",
            "suggestion": "创建非 root 用户并使用 USER 指令切换，遵循最小权限原则",
        })

    # latest 标签
    for i, line in enumerate(lines, 1):
        if line.strip().startswith("FROM ") and ":latest" in line:
            issues.append({
                "check_id": "DEP-DOCKER-002",
                "name": "使用latest镜像标签",
                "severity": "medium",
                "file": filepath,
                "line": i,
                "message": "使用 :latest 标签的基础镜像，构建不可复现，可能引入未测试的变更",
                "suggestion": "使用具体版本号或digest锁定基础镜像版本",
            })
            break

    return issues
