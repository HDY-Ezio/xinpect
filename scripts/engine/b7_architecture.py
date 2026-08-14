# -*- coding: utf-8 -*-
"""
B7: 架构与数据合规检查引擎
- 规则 bundle 正则扫描
- 模块依赖图分析（循环依赖检测）
- 分层架构违规检测
- API返回结构一致性检测
- Flask路由冲突检测
- WebSocket连接超时清理机制检测
- 数据一致性检测（事务/幂等/软删除/约束/外键/级联/枚举/校验一致性）

P2 规则：
- ARCH-API-DOC: 接口契约文档完整性检测（路由函数docstring覆盖率）
- ARCH-DATA-*: 数据一致性相关规则（事务、幂等、软删除、约束等）
"""

import re
from collections import defaultdict
from typing import Dict, List

_scanner = None


# 降级相关关键词（用于隐藏bug检测中的降级路径识别）
_DEGRADATION_KEYWORDS = (
    "degraded", "degrade", "degradation", "fallback",
    "降级", "容灾", "兜底",
)

# 监控/告警相关关键词
_MONITORING_KEYWORDS = (
    "monitor", "alarm", "alert", "metric", "counter",
    "监控", "告警", "报警", "打点", "指标",
)

# 配置文件命名模式
_CONFIG_FILE_PATTERNS = {
    "config.py", "settings.py", "configs.py", "conf.py",
    "config.yaml", "config.yml", "settings.yaml", "settings.yml",
    "app.yaml", "app.yml", "application.yaml", "application.yml",
    ".env", "env.example",
}

# API文档文件模式
_API_DOC_FILE_PATTERNS = (
    "api.md", "README.md", "api_doc.md", "apidoc.md",
    "swagger.yaml", "swagger.yml", "openapi.yaml", "openapi.yml",
)

# 入口文件模式
_ENTRY_FILE_PATTERNS = (
    "main.py", "app.py", "server.py", "wsgi.py", "asgi.py",
    "__main__.py", "manage.py", "run.py",
)


def _get_scanner():
    global _scanner
    if _scanner is None:
        _scanner = RuleBundleScanner("7")
    return _scanner


def scan(code_files: Dict[str, str], config: dict = None) -> List[Dict]:
    """B7 架构合规检查入口（免费版）"""
    if config is None:
        config = {}

    issues = _architecture_checks(code_files)
    return issues


def _architecture_checks(code_files: Dict[str, str]) -> List[Dict]:
    """架构层面的检测"""
    issues = []

    # 构建依赖图
    dep_graph = _build_dependency_graph(code_files)

    # 循环依赖检测
    cycles = _detect_cycles(dep_graph)
    for cycle in cycles[:5]:  # 最多报告5个
        issues.append({
            "check_id": "ARCH-DEP-001",
            "name": "循环依赖",
            "severity": "high",
            "file": cycle[0] if cycle else "",
            "line": 1,
            "message": f"检测到模块循环依赖: {' -> '.join(cycle)}",
            "suggestion": "重构代码打破循环依赖：引入接口层、使用依赖注入、或提取公共模块",
        })

    # 分层违规检测
    layer_issues = _check_layer_violations(code_files)
    issues.extend(layer_issues)

    # 全局状态检测
    state_issues = _check_global_state(code_files)
    issues.extend(state_issues)

    # 隐藏bug检测：模块文件存在但未注册导入
    hidden_mod_issues = _check_hidden_unregistered_modules(code_files)
    issues.extend(hidden_mod_issues)

    # 隐藏bug检测：多层分发别名不一致
    hidden_route_issues = _check_hidden_route_alias_mismatch(code_files)
    issues.extend(hidden_route_issues)

    # 隐藏bug检测：降级路径缺少监控/计数/告警
    hidden_deg_mon_issues = _check_hidden_degraded_no_monitoring(code_files)
    issues.extend(hidden_deg_mon_issues)

    # 隐藏bug检测：可选依赖加载状态无启动汇总
    hidden_deg_summary_issues = _check_hidden_optional_deps_no_summary(code_files)
    issues.extend(hidden_deg_summary_issues)

    # 隐藏bug检测：配置项定义了但未使用
    hidden_config_unused_issues = _check_hidden_config_unused(code_files)
    issues.extend(hidden_config_unused_issues)

    # 隐藏bug检测：代码使用了配置key但配置文件未定义
    hidden_config_undefined_issues = _check_hidden_config_undefined(code_files)
    issues.extend(hidden_config_undefined_issues)

    # 隐藏bug检测：文档声明接口与实际路由不匹配
    hidden_doc_route_issues = _check_hidden_doc_route_mismatch(code_files)
    issues.extend(hidden_doc_route_issues)

    # 隐藏bug检测：分发key与目标函数命名不匹配
    hidden_path_issues = _check_hidden_path_key_value_mismatch(code_files)
    issues.extend(hidden_path_issues)

    # 隐藏bug检测：降级覆盖率统计（信息性）
    hidden_deg_coverage_issues = _check_hidden_degraded_coverage_stats(code_files)
    issues.extend(hidden_deg_coverage_issues)

    # 隐藏bug检测：配置开关与代码if判断双向对账
    hidden_config_switch_issues = _check_hidden_config_switch_reconcile(code_files)
    issues.extend(hidden_config_switch_issues)

    # 隐藏bug检测：事件发布无失败重试/死信队列
    hidden_event_issues = _check_hidden_event_no_retry_dlq(code_files)
    issues.extend(hidden_event_issues)

    # API返回结构一致性检测
    api_consistency_issues = _check_api_return_consistency(code_files)
    issues.extend(api_consistency_issues)

    # Flask路由冲突检测
    flask_route_issues = _check_flask_route_conflict(code_files)
    issues.extend(flask_route_issues)

    # WebSocket连接超时清理机制检测
    ws_timeout_issues = _check_ws_timeout_cleanup(code_files)
    issues.extend(ws_timeout_issues)

    # 接口契约文档完整性检测
    api_doc_issues = _check_api_doc_coverage(code_files)
    issues.extend(api_doc_issues)

    # 数据一致性检测为付费版功能

    # 数据一致性检测为付费版功能

    # 数据一致性检测为付费版功能

    # 数据一致性检测为付费版功能

    # 数据一致性检测为付费版功能

    # 数据一致性检测为付费版功能

    # 数据一致性检测为付费版功能

    # 数据一致性检测为付费版功能

    return issues


def _build_dependency_graph(code_files: Dict[str, str]) -> Dict[str, List[str]]:
    """构建模块依赖图"""
    deps = defaultdict(set)

    for filepath, content in code_files.items():
        if not content or not filepath.endswith(".py"):
            continue

        # Python imports
        lines = content.split("\n")
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                continue

            # from X import Y
            m = re.match(r"^from\s+([\w\.]+)\s+import", stripped)
            if m:
                module = m.group(1)
                # 只记录项目内相对导入或项目内模块
                if not module.startswith("."):
                    # 排除标准库（简单判断：如果模块名太短或者是常见库则跳过）
                    if module in ("os", "sys", "re", "json", "time", "datetime",
                                  "collections", "typing", "logging", "math",
                                  "random", "pathlib", "io", "abc", "enum",
                                  "subprocess", "threading", "multiprocessing",
                                  "concurrent", "asyncio", "unittest", "pytest"):
                        continue
                deps[filepath].add(module)
                continue

            # import X
            m = re.match(r"^import\s+([\w\.]+)", stripped)
            if m:
                module = m.group(1)
                if module in ("os", "sys", "re", "json", "time", "datetime",
                              "collections", "typing", "logging", "math",
                              "random", "pathlib", "io", "abc", "enum",
                              "subprocess", "threading", "multiprocessing",
                              "concurrent", "asyncio", "unittest", "pytest"):
                    continue
                deps[filepath].add(module)

    # 转换为 dict of lists
    return {k: list(v) for k, v in deps.items()}


def _detect_cycles(deps: Dict[str, List[str]]) -> List[List[str]]:
    """检测循环依赖（DFS）"""
    cycles = []
    visited_global = set()

    def dfs(node, path, visited_path):
        if node in visited_path:
            cycle_start = path.index(node)
            cycle = path[cycle_start:] + [node]
            cycles.append(cycle)
            return
        if node in visited_global:
            return

        visited_global.add(node)
        visited_path.add(node)
        path.append(node)

        for neighbor in deps.get(node, []):
            dfs(neighbor, path[:], visited_path.copy())

    for node in deps:
        if node not in visited_global:
            dfs(node, [], set())

    # 去重
    unique_cycles = []
    seen = set()
    for cycle in cycles:
        # 规范化：循环起点设为字母序最小的节点
        core = cycle[:-1]
        if not core:
            continue
        min_idx = core.index(min(core))
        normalized = tuple(core[min_idx:] + core[:min_idx])
        if normalized not in seen:
            seen.add(normalized)
            unique_cycles.append(list(normalized) + [normalized[0]])

    return unique_cycles


def _check_layer_violations(code_files: Dict[str, str]) -> List[Dict]:
    """检测分层架构违规"""
    issues = []

    # 层级定义（从上层到下层）
    layers = {
        "controller": ["controller", "handler", "api", "view", "route", "endpoint"],
        "service": ["service", "usecase", "use_case", "business", "manager"],
        "repository": ["repository", "repo", "dao", "store", "datasource"],
        "model": ["model", "entity", "domain", "bean", "dto", "po", "vo"],
    }

    # 反向依赖规则：下层不应依赖上层
    layer_order = ["controller", "service", "repository", "model"]

    for filepath, code_content in code_files.items():
        filepath_lower = filepath.lower()
        if not filepath_lower.endswith((".py", ".js", ".ts", ".java", ".go")):
            continue

        # 从文件路径中提取路径组件（目录+文件名主体）
        # 用 / 和 \ 分割，再去掉扩展名，得到用于匹配的词元列表
        import os as _os
        path_no_ext = filepath_lower.rsplit(".", 1)[0]
        # 按路径分隔符和下划线分割，得到词元集合
        import re as _re
        path_tokens = set(_re.split(r'[\/_.\-]+', path_no_ext))
        # 也保留目录部分的路径片段（如 models/ 目录）
        dir_tokens = set()
        dir_parts = _re.split(r'[\/]+', filepath_lower)
        for part in dir_parts[:-1]:  # 排除文件名本身
            if part:
                dir_tokens.add(part)
                dir_tokens.update(_re.split(r'[_.\-]+', part))

        # 确定文件所属层级 - 用词元边界匹配（避免子串误匹配）
        file_layer = None
        for layer, keywords in layers.items():
            for kw in keywords:
                if kw in path_tokens or kw in dir_tokens:
                    file_layer = layer
                    break
            if file_layer:
                break

        if not file_layer:
            continue

        file_layer_idx = layer_order.index(file_layer) if file_layer in layer_order else -1
        if file_layer_idx == -1:
            continue

        # 检查是否依赖了上层（反向依赖）
        content_lower = code_content.lower()
        # 提取所有 import 语句中的模块名
        import_modules = set()
        for line in content_lower.split("\n"):
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                continue
            # from X import Y
            m = _re.match(r'^from\s+([\w\.]+)\s+import', stripped)
            if m:
                import_modules.add(m.group(1))
                continue
            # import X
            m = _re.match(r'^import\s+([\w\.]+)', stripped)
            if m:
                import_modules.add(m.group(1))

        for i in range(file_layer_idx):
            upper_layer = layer_order[i]
            upper_keywords = layers[upper_layer]
            for kw in upper_keywords:
                # 检查 import 模块名中是否存在该层级关键词（以词元边界匹配）
                found = False
                for mod in import_modules:
                    # 将模块路径按 . 拆分，检查每个组件是否等于关键词
                    components = mod.split(".")
                    if kw in components:
                        found = True
                        break
                if found:
                    issues.append({
                        "check_id": "ARCH-LAY-001",
                        "name": "分层违规-反向依赖",
                        "severity": "medium",
                        "file": filepath,
                        "line": 1,
                        "message": f"{file_layer}层依赖了{upper_layer}层（{kw}），违反分层架构原则",
                        "suggestion": "遵循依赖倒置原则，下层不应感知上层；使用接口/事件解耦",
                    })
                    break

    # 去重
    seen = set()
    unique_issues = []
    for iss in issues:
        key = (iss["check_id"], iss["file"])
        if key not in seen:
            seen.add(key)
            unique_issues.append(iss)

    return unique_issues


def _check_global_state(code_files: Dict[str, str]) -> List[Dict]:
    """检测全局状态滥用"""
    issues = []

    for filepath, content in code_files.items():
        if not filepath.endswith(".py"):
            continue

        lines = content.split("\n")
        global_decls = 0
        _mutable_globals = 0

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("global "):
                global_decls += 1
            # 模块级可变对象（list/dict/set）
            if re.match(r'^\w+\s*=\s*[\{\[]', stripped) and not stripped.startswith("_"):
                _mutable_globals += 1

        if global_decls > 3:
            issues.append({
                "check_id": "ARCH-STATE-001",
                "name": "过多全局变量",
                "severity": "medium",
                "file": filepath,
                "line": 1,
                "message": f"文件中有 {global_decls} 处 global 声明，全局状态增加调试和并发难度",
                "suggestion": "使用类封装状态，或通过依赖注入传递，避免全局可变状态",
            })

    return issues


# ---------------------------------------------------------------------------
# 隐藏Bug检测规则
# ---------------------------------------------------------------------------

# 工具类文件名关键词（用于排除误报）
_UTIL_FILE_KEYWORDS = ("util", "helper", "base", "mixin", "common", "tools")

# 模块目录关键词
_MODULE_DIR_KEYWORDS = (
    "handlers", "controllers", "modules", "plugins", "blueprints",
)

# 注册清单变量名模式
_REGISTRY_VAR_PATTERNS = (
    "_handler_modules", "_MODULES", "INSTALLED_APPS",
    "REGISTERED_MODULES", "BLUEPRINTS", "PLUGINS", "ROUTES",
)


def _is_util_file(filename: str) -> bool:
    """判断文件名是否为工具类文件（用于排除未注册模块的误报）"""
    name_lower = filename.lower()
    for kw in _UTIL_FILE_KEYWORDS:
        if kw in name_lower:
            return True
    return False


def _extract_registry_names(content: str) -> List[str]:
    """从文件内容中提取注册清单中的模块名列表

    识别模式：形如 `VAR_NAME = [ ... ]` 的列表字面量，
    列表元素为字符串字面量或模块导入对象。
    """
    registry_names = []

    for var_name in _REGISTRY_VAR_PATTERNS:
        # 匹配 var_name = [ ... ] （支持跨行）
        pattern = re.compile(
            rf'{re.escape(var_name)}\s*=\s*\[(.*?)\]',
            re.DOTALL
        )
        match = pattern.search(content)
        if not match:
            continue

        list_body = match.group(1)
        # 提取字符串字面量（支持单引号/双引号）
        str_matches = re.findall(r'[\'"]([^\'"]+)[\'"]', list_body)
        if str_matches:
            registry_names.extend(str_matches)
            continue

        # 如果没有字符串，尝试提取模块对象导入名
        # 例如: from .handlers import user_handler, auth_handler
        # 列表里是: user_handler, auth_handler
        # 直接按逗号分割，去掉空白和注释
        items = []
        for item in list_body.split(","):
            item = item.strip()
            if not item or item.startswith("#"):
                continue
            # 去掉行内注释
            if "#" in item:
                item = item.split("#")[0].strip()
            # 如果是简单标识符（不含.的纯名称）
            if re.match(r'^[a-zA-Z_]\w*$', item):
                items.append(item)
        if items:
            registry_names.extend(items)

    return registry_names


def _check_hidden_unregistered_modules(code_files: Dict[str, str]) -> List[Dict]:
    """HIDDEN-MOD-001 模块文件存在但未注册导入

    扫描 handlers / controllers / modules / plugins / blueprints 等目录下的 .py 文件，
    与注册清单（_handler_modules / _MODULES / INSTALLED_APPS 等）对账，
    找出目录里有但清单里没有的模块。
    """
    issues = []

    # 按目录分组收集模块文件
    # key: 目录路径（相对于项目根，如 "handlers" 或 "app/modules"）
    # value: list of 模块文件名（不含扩展名）
    dir_modules: Dict[str, List[str]] = defaultdict(list)
    # 目录对应的注册文件路径
    dir_registry_files: Dict[str, List[str]] = defaultdict(list)

    for filepath in code_files:
        if not filepath.endswith(".py"):
            continue

        # 分离目录和文件名
        parts = filepath.replace("\\", "/").rsplit("/", 1)
        if len(parts) == 1:
            continue  # 根目录文件跳过
        dir_path = parts[0]
        filename = parts[1]

        # 判断目录是否为模块目录
        dir_lower = dir_path.lower()
        dir_tokens = set(re.split(r'[\/_.\-]+', dir_lower))
        is_module_dir = False
        matched_dir_name = ""
        for kw in _MODULE_DIR_KEYWORDS:
            if kw in dir_tokens:
                is_module_dir = True
                matched_dir_name = kw
                break

        if not is_module_dir:
            # 不是模块目录，检查是否为注册文件所在目录的同级
            # （注册文件可能在 modules/ 目录本身）
            continue

        # 收集该目录下的 .py 模块文件（排除 __init__.py 和 _ 开头的文件）
        if filename == "__init__.py" or filename.startswith("_"):
            # 可能是注册文件，记录下来
            if filename == "__init__.py" or filename in (
                "registry.py", "manager.py", "main.py"
            ):
                dir_registry_files[dir_path].append(filepath)
            continue

        if _is_util_file(filename):
            continue

        module_name = filename[:-3]  # 去掉 .py
        dir_modules[dir_path].append(module_name)

    # 也检查模块目录下的 registry/manager/main.py 作为注册文件
    for filepath in code_files:
        if not filepath.endswith(".py"):
            continue
        parts = filepath.replace("\\", "/").rsplit("/", 1)
        if len(parts) == 1:
            continue
        dir_path = parts[0]
        filename = parts[1]

        if filename in ("registry.py", "manager.py", "main.py"):
            # 检查目录是否为模块目录
            dir_lower = dir_path.lower()
            dir_tokens = set(re.split(r'[\/_.\-]+', dir_lower))
            for kw in _MODULE_DIR_KEYWORDS:
                if kw in dir_tokens:
                    if filepath not in dir_registry_files[dir_path]:
                        dir_registry_files[dir_path].append(filepath)
                    break

    # 对每个模块目录，找到注册文件并对账
    for dir_path, module_names in dir_modules.items():
        # 找注册文件
        registry_files = dir_registry_files.get(dir_path, [])
        if not registry_files:
            # 如果目录里没有 __init__.py 等注册文件，跳过（避免误报）
            continue

        # 从所有注册文件中提取已注册的模块名
        registered_names = set()
        for reg_file in registry_files:
            content = code_files.get(reg_file, "")
            if not content:
                continue
            names = _extract_registry_names(content)
            for n in names:
                # 可能是带路径的模块名（如 "handlers.user"），取最后一段
                base_name = n.rsplit(".", 1)[-1]
                registered_names.add(base_name)
                # 也可能整个就是模块名
                registered_names.add(n)

        if not registered_names:
            # 没有找到任何注册清单变量，跳过（避免误报）
            continue

        # 对账：目录里有但注册清单里没有
        for mod_name in module_names:
            if mod_name in registered_names:
                continue
            # 检查是否有 snake_case / 驼峰 等变体匹配
            found_variant = False
            for reg_name in registered_names:
                if reg_name.lower().replace("_", "") == mod_name.lower().replace("_", ""):
                    found_variant = True
                    break
            if found_variant:
                continue

            # 找到未注册的模块
            module_file = f"{dir_path}/{mod_name}.py"
            issues.append({
                "check_id": "HIDDEN-MOD-001",
                "name": "模块文件存在但未注册导入",
                "severity": "high",
                "file": module_file,
                "line": 1,
                "message": (
                    f"模块文件 '{mod_name}.py' 存在于 {dir_path} 目录，"
                    f"但未在注册清单中登记，对应的接口/功能将不可用"
                ),
                "suggestion": "在模块注册清单中添加该模块，或确认是否为废弃文件",
            })

    return issues


def _check_hidden_route_alias_mismatch(code_files: Dict[str, str]) -> List[Dict]:
    """HIDDEN-ROUTE-001 多层分发别名不一致

    识别两层分发模式：
    - 外层：模块顶层的路由表/动作映射字典（如 _ROUTE_MAP = {"remove": handle_delete, ...}）
    - 内层：handler函数内部又有 if/elif 按 sub_action 分发，或内部 dispatch 字典

    对比外层映射 key（别名）与内层分发 key（真实动作名），
    找出外层有但内层没有的 key → 别名无效。
    """
    import re as _re

    issues = []

    # 外层路由映射字典的变量名模式
    outer_map_var_patterns = (
        "_ROUTE_MAP", "route_map", "action_map", "_ACTION_MAP",
        "handler_map", "_HANDLER_MAP", "dispatch_map", "_DISPATCH_MAP",
    )

    for filepath, content in code_files.items():
        if not filepath.endswith(".py") or not content:
            continue

        # ---- 前置：收集模块顶层定义的所有函数名 ----
        top_level_funcs = set()
        for fm in _re.finditer(r'^(def\s+\w+\s*\()', content, _re.MULTILINE):
            # 检查缩进：模块顶层 def 没有缩进
            pos = fm.start()
            line_start = content.rfind("\n", 0, pos) + 1
            indent = pos - line_start
            if indent == 0:
                func_name = _re.match(r'def\s+(\w+)', fm.group(1)).group(1)
                top_level_funcs.add(func_name)

        if not top_level_funcs:
            continue

        # ---- 第1步：识别模块顶层的外层路由映射字典 ----
        outer_aliases = {}  # key: 别名, value: (行号, handler函数名)

        for var_name in outer_map_var_patterns:
            # 精确匹配：行首（顶格）开始的变量赋值
            # 使用 ^ 锚定行首，确保是模块顶层定义
            pattern = _re.compile(
                rf'^{re.escape(var_name)}\s*=\s*\{{(.*?)\n\}}',
                _re.MULTILINE | _re.DOTALL
            )
            match = pattern.search(content)
            if not match:
                continue

            dict_body = match.group(1)
            start_pos = match.start()
            start_line = content[:start_pos].count("\n") + 1

            # ---- 验证：字典值中至少有一个引用了模块顶层函数 ----
            # 提取每行的值部分，检查是否包含顶层函数名
            has_real_handler_ref = False
            for line in dict_body.split("\n"):
                stripped = line.strip().rstrip(",")
                # 格式: "key": value 或 'key': value
                m = _re.match(r'[\'"]([^\'"]+)[\'"]\s*:\s*(.+)', stripped)
                if m:
                    val = m.group(2).strip()
                    # 值是裸函数名引用（不是字符串、不是调用、不是lambda）
                    if _re.match(r'^[a-zA-Z_]\w*$', val) and val in top_level_funcs:
                        has_real_handler_ref = True
                        break

            if not has_real_handler_ref:
                # 字典里没有真实函数引用，可能是示例代码或配置字典，跳过
                continue

            # 提取所有 key
            key_matches = _re.findall(
                r'[\'"]([^\'"]+)[\'"]\s*:',
                dict_body
            )
            for i, key in enumerate(key_matches):
                key_pos_in_body = dict_body.find(f"'{key}':")
                if key_pos_in_body == -1:
                    key_pos_in_body = dict_body.find(f'"{key}":')
                if key_pos_in_body >= 0:
                    line_offset = dict_body[:key_pos_in_body].count("\n")
                else:
                    line_offset = 0
                outer_aliases[key] = start_line + line_offset

            # 找到一个就够了
            break

        if not outer_aliases:
            continue

        # ---- 第2步：识别内层分发逻辑 ----
        inner_actions = set()
        handler_func_name = None

        func_pattern = _re.compile(r'^def\s+(\w+)\s*\(', _re.MULTILINE)
        func_matches = list(func_pattern.finditer(content))

        for i, fm in enumerate(func_matches):
            func_name = fm.group(1)
            func_start = fm.start()
            func_end = func_matches[i + 1].start() if i + 1 < len(func_matches) else len(content)
            func_body = content[func_start:func_end]

            # 检查该函数是否为外层路由映射中引用的 handler
            is_handler = False
            for var_name in outer_map_var_patterns:
                pattern = _re.compile(
                    rf'^{re.escape(var_name)}\s*=\s*\{{.*?{re.escape(func_name)}.*?\n\}}',
                    _re.MULTILINE | _re.DOTALL
                )
                if pattern.search(content):
                    is_handler = True
                    break

            if not is_handler:
                if not _re.search(r'(handler|handle|dispatch|action|route)', func_name, _re.I):
                    continue

            # ---- 在函数体内找内层分发 ----
            # 模式A: if/elif 按 action/sub_action/cmd 分发
            if_pattern = _re.compile(
                r'(?:if|elif)\s+(?:sub_action|action|cmd|command|op|operation)\s*==\s*[\'"]([^\'"]+)[\'"]',
                _re.IGNORECASE
            )
            for m in if_pattern.finditer(func_body):
                inner_actions.add(m.group(1))

            # 模式B: 内部 dispatch 字典
            inner_dispatch_pattern = _re.compile(
                r'(?:dispatch|_dispatch|inner_map|_inner_map|action_dispatch)\s*=\s*\{(.*?)\}',
                _re.DOTALL
            )
            for m in inner_dispatch_pattern.finditer(func_body):
                dict_body_inner = m.group(1)
                inner_keys = _re.findall(r'[\'"]([^\'"]+)[\'"]\s*:', dict_body_inner)
                inner_actions.update(inner_keys)

            if inner_actions:
                handler_func_name = func_name
                break

        if not inner_actions:
            continue

        # ---- 第3步：对比外层别名与内层动作名 ----
        for alias, line_no in outer_aliases.items():
            if alias in inner_actions:
                continue
            found_variant = False
            for inner in inner_actions:
                if alias.lower().replace("_", "").replace("-", "") == inner.lower().replace("_", "").replace("-", ""):
                    found_variant = True
                    break
            if found_variant:
                continue

            issues.append({
                "check_id": "HIDDEN-ROUTE-001",
                "name": "多层分发别名不一致",
                "severity": "medium",
                "file": filepath,
                "line": line_no,
                "message": (
                    f"动作别名 '{alias}' 在外层路由映射中定义，"
                    f"但内层 handler 不识别该别名，请求将返回404或走默认分支"
                ),
                "suggestion": "在内层分发逻辑中添加别名映射，或统一在最外层做别名转换",
            })

    return issues

def _check_hidden_degraded_no_monitoring(code_files: Dict[str, str]) -> List[Dict]:
    """HIDDEN-DEG-002 降级路径缺少监控/计数/告警

    检测逻辑：
    - 扫描文件中所有降级关键词所在的代码行（degraded/fallback/降级）
    - 检查降级路径附近（前后10行内）是否有监控/计数/告警调用
      （logging.warning/logger.error/counter.inc/metrics.increment/告警 等）
    - 如果降级路径只是静默return或只打印了info/debug日志，
      没有任何告警/计数/错误日志 → 报警
    - 排除注释和docstring中的降级讨论
    """
    issues = []

    # 仅在 Python 文件中检测
    for filepath, content in code_files.items():
        if not filepath.endswith(".py") or not content:
            continue

        lines = content.split("\n")
        # 先用全文件判断是否有降级关键词，快速跳过
        has_deg = False
        for kw in _DEGRADATION_KEYWORDS:
            if kw in content:
                has_deg = True
                break
        if not has_deg:
            continue

        # 收集有效代码行（排除纯注释行、docstring内的行）
        # 简化处理：排除以 # 开头的行；docstring 用三引号状态机粗略跳过
        in_docstring = False
        code_line_indices = []  # 有效代码行的行号（0-based）
        for idx, line in enumerate(lines):
            stripped = line.strip()

            # 处理docstring边界
            # 只计算独立的三引号行/起始行
            triple_count = stripped.count('"""') + stripped.count("'''")
            if triple_count > 0 and not stripped.startswith("#"):
                if in_docstring:
                    # 结束docstring
                    if triple_count % 2 == 1:
                        in_docstring = False
                    # 偶数说明在同一行开始并结束，仍然在docstring外
                else:
                    if triple_count % 2 == 1:
                        in_docstring = True
                    # 偶数对：在同一行开始并结束，不影响
                continue  # docstring行不当作代码行

            if in_docstring:
                continue

            if stripped.startswith("#") or not stripped:
                continue

            code_line_indices.append(idx)

        # 遍历有效代码行，找降级关键词所在行
        deg_line_indices = set()
        for idx in code_line_indices:
            line = lines[idx]
            for kw in _DEGRADATION_KEYWORDS:
                if kw in line:
                    deg_line_indices.add(idx)
                    break

        if not deg_line_indices:
            continue

        # 对每个降级行，检查前后10行内是否有监控/告警/计数
        # 先合并相近的降级行，避免重复报（同一块降级逻辑只报一次）
        sorted_deg_lines = sorted(deg_line_indices)
        merged_blocks = []  # list of (start_line, end_line)
        current_start = sorted_deg_lines[0]
        current_end = sorted_deg_lines[0]

        for line_no in sorted_deg_lines[1:]:
            if line_no - current_end <= 5:  # 5行内视为同一块
                current_end = line_no
            else:
                merged_blocks.append((current_start, current_end))
                current_start = line_no
                current_end = line_no
        merged_blocks.append((current_start, current_end))

        for block_start, block_end in merged_blocks:
            # 扩展窗口：前后各10行（但以文件边界为限）
            window_start = max(0, block_start - 10)
            window_end = min(len(lines) - 1, block_end + 10)

            has_monitoring = False
            for w_idx in range(window_start, window_end + 1):
                if w_idx not in set(code_line_indices):
                    continue  # 只看有效代码行
                wline = lines[w_idx]
                for mkw in _MONITORING_KEYWORDS:
                    if mkw in wline:
                        has_monitoring = True
                        break
                if has_monitoring:
                    break

            if not has_monitoring:
                # 再排除：如果降级只是在注释含义上的讨论（如函数名里带fallback但函数体有监控）
                # 已经通过 code_line_indices 排除了纯注释行，这里基本都是代码

                # 排除：只是定义了变量名/函数名包含降级词，但不是实际执行降级的路径
                # 简单启发：该行必须有 return / pass / raise / 赋值 等执行语义
                # （如果仅仅是函数定义行 def xxx_degrade(): 则不算）
                block_has_exec = False
                for idx in range(block_start, block_end + 1):
                    line = lines[idx].strip()
                    if (line.startswith("return") or
                        line.startswith("raise ") or
                        line == "pass" or
                        "= True" in line or
                        "= False" in line or
                        "= None" in line or
                        "= []" in line or
                        "= {}" in line or
                        line.startswith("if ") or
                        line.startswith("elif ")):
                        block_has_exec = True
                        break
                if not block_has_exec:
                    # 可能只是函数定义/类定义行包含了关键词，跳过
                    continue

                report_line = block_start + 1  # 转1-based
                issues.append({
                    "check_id": "HIDDEN-DEG-002",
                    "name": "降级路径缺少监控告警",
                    "severity": "medium",
                    "file": filepath,
                    "line": report_line,
                    "message": (
                        f"检测到降级路径（含降级关键词），但前后10行内没有任何"
                        f"监控告警/计数/错误日志，降级发生时将无法被感知"
                    ),
                    "suggestion": (
                        "在降级路径中添加 logging.warning/error 或 metrics.counter.inc "
                        "等监控埋点，确保降级可观测、可告警"
                    ),
                })

    return issues


def _check_hidden_optional_deps_no_summary(code_files: Dict[str, str]) -> List[Dict]:
    """HIDDEN-DEG-003 启动时可选依赖加载状态无汇总

    检测逻辑（project级）：
    - 识别项目中的可选依赖降级点（try-except ImportError 模式）
    - 检查项目入口文件（main.py/app.py/__init__.py/run.py 等）是否有
      "可选依赖加载状态汇总打印"——即启动时统一打印哪些模块加载成功、哪些失败降级
    - 如果全是分散的 try-except，启动时不统一打印汇总 → 报 low
    """
    issues = []

    # 第1步：统计项目中所有 try-except ImportError 的可选依赖降级点
    optional_dep_sites = []  # list of (filepath, line_no)
    for filepath, content in code_files.items():
        if not filepath.endswith(".py") or not content:
            continue
        lines = content.split("\n")
        in_try = False
        try_start_line = -1
        for idx, line in enumerate(lines):
            stripped = line.strip()
            # 匹配 try: 或 try 加注释
            if re.match(r'^try\s*:?\s*(#.*)?$', stripped):
                in_try = True
                try_start_line = idx
                continue
            if in_try:
                # 匹配 except ImportError 或 except ModuleNotFoundError
                if re.match(r'^except\s+(ImportError|ModuleNotFoundError)', stripped):
                    # 这是一个可选依赖降级点
                    optional_dep_sites.append((filepath, try_start_line + 1))
                    in_try = False
                elif stripped.startswith("except "):
                    in_try = False
                elif re.match(r'^(def |class |if |for |while )', stripped) and not stripped.startswith("    "):
                    # 离开缩进块
                    in_try = False

    if not optional_dep_sites:
        # 项目没有可选依赖降级点，无需检测
        return issues

    # 第2步：找入口文件，检查是否有"可选依赖加载状态汇总打印"
    entry_files = []
    for filepath in code_files:
        basename = filepath.replace("\\", "/").rsplit("/", 1)[-1]
        if basename in _ENTRY_FILE_PATTERNS:
            entry_files.append(filepath)

    if not entry_files:
        return issues

    has_summary = False
    for entry_file in entry_files:
        content = code_files.get(entry_file, "")
        if not content:
            continue
        # 检查是否有汇总打印的迹象
        # 模式1: 打印/记录 "加载状态"、"可选依赖"、"loaded"、"available" 等汇总词
        # 模式2: 有一个专门的函数/方法打印依赖状态
        summary_patterns = (
            r"可选依赖.*(加载|状态|汇总|结果)",
            r"(依赖|模块).*(加载|导入).*(状态|汇总|结果)",
            r"loaded.*optional|optional.*loaded",
            r"依赖.*(成功|失败).*(数|个|统计)",
            r"print.*(加载|import|依赖).*(状态|汇总)",
            r"logger.*(依赖|模块).*(加载|状态)",
            r"summary.*depend",
            r"depend.*summary",
        )
        for pat in summary_patterns:
            if re.search(pat, content, re.IGNORECASE):
                has_summary = True
                break
        if has_summary:
            break

    if not has_summary and len(optional_dep_sites) >= 2:
        # 至少2处分散的可选依赖降级，且入口没有汇总打印 → 报low
        first_site_file, first_site_line = optional_dep_sites[0]
        issues.append({
            "check_id": "HIDDEN-DEG-003",
            "name": "可选依赖加载状态无启动汇总",
            "severity": "low",
            "file": first_site_file,
            "line": first_site_line,
            "message": (
                f"项目中有 {len(optional_dep_sites)} 处可选依赖降级（try-except ImportError），"
                f"但入口文件未在启动时统一打印各依赖的加载状态汇总，"
                f"线上环境哪些模块降级了难以排查"
            ),
            "suggestion": (
                "在应用启动入口统一收集并打印可选依赖加载状态，"
                "例如：打印 [OK] xxx 模块加载成功 / [WARN] yyy 模块未安装，已降级"
            ),
        })

    return issues


def _extract_config_keys_from_py(content: str) -> Dict[str, int]:
    """从Python配置文件中提取配置项key

    识别模式：
    - KEY = value （模块级常量赋值，全大写或驼峰）
    - "key": value （字典字面量中的key）
    - 排除明显的函数参数、局部变量等
    """
    keys: Dict[str, int] = {}  # key -> line_no (1-based)
    lines = content.split("\n")

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue

        # 模式1: 模块级常量赋值（行首无缩进，左部为变量名 = 值）
        # 排除 class / def / if / for / while / with / try / import / from 等语句
        if re.match(r'^[A-Z_][A-Z0-9_]*\s*=\s*', stripped):
            # 全大写的常量，很可能是配置项
            m = re.match(r'^([A-Z_][A-Z0-9_]*)\s*=', stripped)
            if m:
                key = m.group(1)
                # 排除特殊变量
                if key not in ("__all__", "__version__", "__author__",
                               "__name__", "__file__", "__doc__"):
                    keys[key] = idx + 1
                    continue

        # 模式2: 驼峰/小驼峰的配置变量（如 DEBUG = True 已在上面匹配）
        # 也匹配 config_dict["KEY"] = value 类的字典赋值（跳过，太复杂）

    # 模式3: 字典字面量中的配置key（如 _CONFIG = {"KEY": value, ...}）
    # 匹配配置字典变量
    dict_pattern = re.compile(
        r'(?:CONFIG|_CONFIG|config_dict|settings_dict|APP_CONFIG)\s*=\s*\{(.*?)\}',
        re.DOTALL
    )
    for m in dict_pattern.finditer(content):
        dict_body = m.group(1)
        start_pos = m.start()
        start_line = content[:start_pos].count("\n") + 1
        key_matches = re.findall(r'[\'"]([^\'"]+)[\'"]\s*:', dict_body)
        for i, k in enumerate(key_matches):
            # 粗略估计行号
            key_pos_in_body = dict_body.find(f"'{k}':")
            if key_pos_in_body == -1:
                key_pos_in_body = dict_body.find(f'"{k}":')
            line_offset = dict_body[:max(0, key_pos_in_body)].count("\n") if key_pos_in_body >= 0 else 0
            keys[k] = start_line + line_offset

    return keys


def _extract_config_keys_from_yaml(content: str) -> Dict[str, int]:
    """从YAML配置文件中提取顶层配置项key"""
    keys: Dict[str, int] = {}
    lines = content.split("\n")

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        # YAML 顶层 key: value
        if not line.startswith(" ") and not line.startswith("\t"):
            m = re.match(r'^([\w\-\.]+)\s*:', stripped)
            if m:
                key = m.group(1)
                keys[key] = idx + 1

    return keys


def _extract_config_keys_from_env(content: str) -> Dict[str, int]:
    """从.env配置文件中提取配置项key"""
    keys: Dict[str, int] = {}
    lines = content.split("\n")

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        # KEY=value 或 KEY="value"
        m = re.match(r'^([A-Z_][A-Z0-9_]*)\s*=', stripped)
        if m:
            keys[m.group(1)] = idx + 1

    return keys


def _find_config_files(code_files: Dict[str, str]) -> Dict[str, str]:
    """从文件集合中筛选配置文件，返回 {filepath: content}"""
    config_files = {}
    for filepath, content in code_files.items():
        basename = filepath.replace("\\", "/").rsplit("/", 1)[-1]
        if basename in _CONFIG_FILE_PATTERNS:
            config_files[filepath] = content
            continue
        # 也匹配 config/ 目录下的文件
        parts = filepath.replace("\\", "/").split("/")
        if "config" in parts or "configs" in parts or "settings" in parts:
            if filepath.endswith((".py", ".yaml", ".yml", ".env")):
                config_files[filepath] = content
                continue
    return config_files


def _collect_all_used_config_keys(code_files: Dict[str, str]) -> Dict[str, List[tuple]]:
    """收集所有代码文件中使用的配置key

    识别模式：
    - config.get("key", ...) / config.get("key")
    - settings.KEY  / config.KEY
    - os.getenv("KEY", ...) / os.environ["KEY"]
    - CONFIG["key"] / settings["key"]
    - from config import KEY （导入的变量也视为使用）

    返回: {key: [(file, line), ...]}
    """
    used_keys: Dict[str, List[tuple]] = defaultdict(list)

    for filepath, content in code_files.items():
        if not filepath.endswith(".py") or not content:
            continue

        lines = content.split("\n")
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue

            # 模式1: config.get("key") / settings.get("key") / cfg.get("key")
            for m in re.finditer(
                r'(?:config|cfg|settings|conf|app_config)\.get\s*\(\s*[\'"]([^\'"]+)[\'"]',
                line, re.IGNORECASE
            ):
                key = m.group(1)
                used_keys[key].append((filepath, idx + 1))

            # 模式2: os.getenv("KEY") / os.environ.get("KEY")
            for m in re.finditer(
                r'os\.(?:getenv|environ\.get)\s*\(\s*[\'"]([^\'"]+)[\'"]',
                line
            ):
                key = m.group(1)
                used_keys[key].append((filepath, idx + 1))

            # 模式3: os.environ["KEY"] / CONFIG["key"] / settings["key"]
            for m in re.finditer(
                r'(?:os\.environ|CONFIG|settings|config)\[["\']([^"\']+)["\']\]',
                line
            ):
                key = m.group(1)
                used_keys[key].append((filepath, idx + 1))

            # 模式4: settings.KEY / config.KEY（属性访问）
            # 只匹配明显是配置对象的属性访问（后面跟着赋值/调用/返回等）
            for m in re.finditer(
                r'\b(?:settings|config|cfg|conf)\.([A-Z_][A-Z0-9_]*)\b',
                line
            ):
                key = m.group(1)
                # 排除方法调用（如 config.get, config.items 等）
                if key in ("get", "items", "keys", "values", "setdefault",
                           "update", "pop", "copy", "clear", "fromkeys"):
                    continue
                used_keys[key].append((filepath, idx + 1))

            # 模式5: from config import KEY / from settings import KEY
            m = re.match(r'^from\s+(?:[\w\.]*config[\w\.]*|[\w\.]*settings[\w\.]*)\s+import\s+(.+)', stripped)
            if m:
                import_part = m.group(1)
                # 提取导入的变量名
                for imp in import_part.split(","):
                    imp = imp.strip()
                    if imp.startswith("#"):
                        break
                    # 处理 as 别名
                    if " as " in imp:
                        imp = imp.split(" as ")[0].strip()
                    # 只提取看起来像常量的（大写+下划线）
                    if re.match(r'^[A-Z_][A-Z0-9_]*$', imp):
                        used_keys[imp].append((filepath, idx + 1))

    return used_keys


def _check_hidden_config_unused(code_files: Dict[str, str]) -> List[Dict]:
    """HIDDEN-CONFIG-001 配置项定义了但代码中未使用

    检测逻辑：
    - 扫描配置文件中所有配置项key
    - 全局搜索这些配置key是否在其他.py文件中被引用
    - 找出"配置文件中定义了但代码中从未被使用"的死配置 → 报medium
    - 排除明显的配置基类/默认值/注释行
    """
    issues = []

    # 第1步：找出所有配置文件，并提取配置key
    config_files = _find_config_files(code_files)
    if not config_files:
        return issues

    defined_keys: Dict[str, Dict] = {}  # key -> {"file": ..., "line": ...}
    for cfg_file, content in config_files.items():
        if cfg_file.endswith(".py"):
            keys = _extract_config_keys_from_py(content)
        elif cfg_file.endswith((".yaml", ".yml")):
            keys = _extract_config_keys_from_yaml(content)
        elif cfg_file.endswith(".env"):
            keys = _extract_config_keys_from_env(content)
        else:
            continue

        for key, line_no in keys.items():
            # 如果同一个key在多个文件中定义，保留第一个
            if key not in defined_keys:
                defined_keys[key] = {"file": cfg_file, "line": line_no}

    if not defined_keys:
        return issues

    # 第2步：收集所有代码中使用的配置key
    used_keys = _collect_all_used_config_keys(code_files)

    # 第3步：找出定义了但未使用的key
    for key, info in defined_keys.items():
        # 先精确匹配
        if key in used_keys:
            continue

        # 再做大小写不敏感匹配（有的代码用小写属性访问）
        found_variant = False
        for used_key in used_keys:
            if used_key.lower() == key.lower():
                found_variant = True
                break
        if found_variant:
            continue

        # 排除常见的非业务配置项（减少误报）
        exclude_prefixes = (
            "__",  # Python内置变量
            "SECRET_", "PASSWORD", "TOKEN",  # 敏感配置可能只在部署时注入
        )
        skip = False
        for prefix in exclude_prefixes:
            if key.startswith(prefix):
                skip = True
                break
        if skip:
            continue

        # 排除只有1个字符的（不可能是配置项）
        if len(key) <= 1:
            continue

        issues.append({
            "check_id": "HIDDEN-CONFIG-001",
            "name": "配置项定义但未使用",
            "severity": "medium",
            "file": info["file"],
            "line": info["line"],
            "message": (
                f"配置项 '{key}' 在配置文件中定义，但代码中未被引用，"
                f"可能是废弃配置或遗漏了使用逻辑"
            ),
            "suggestion": "确认该配置项是否仍在使用，废弃的配置应及时清理，避免维护困惑",
        })

    return issues


def _check_hidden_config_undefined(code_files: Dict[str, str]) -> List[Dict]:
    """HIDDEN-CONFIG-002 代码中使用了配置key但配置文件未定义

    检测逻辑：
    - 收集代码中所有 config.get / settings.XXX / os.getenv / CONFIG["key"] 的key
    - 跟配置文件/环境变量定义比对
    - 找出"代码在用但配置文件里没定义"的key → 报high
    - 排除动态拼接的key（变量作为key的情况）
    """
    issues = []

    # 第1步：找出所有配置文件，并提取配置key
    config_files = _find_config_files(code_files)
    if not config_files:
        return issues

    defined_keys: Dict[str, str] = {}  # key -> filepath
    for cfg_file, content in config_files.items():
        if cfg_file.endswith(".py"):
            keys = _extract_config_keys_from_py(content)
        elif cfg_file.endswith((".yaml", ".yml")):
            keys = _extract_config_keys_from_yaml(content)
        elif cfg_file.endswith(".env"):
            keys = _extract_config_keys_from_env(content)
        else:
            continue

        for key in keys:
            if key not in defined_keys:
                defined_keys[key] = cfg_file
            # 大小写不敏感的也加入（方便匹配）
            defined_keys[key.lower()] = cfg_file

    if not defined_keys:
        return issues

    # 第2步：收集所有代码中使用的配置key
    used_keys = _collect_all_used_config_keys(code_files)

    if not used_keys:
        return issues

    # 第3步：找出使用了但未定义的key
    # 去重：同一个key只报一次，报第一个使用位置
    reported = set()
    for key, locations in used_keys.items():
        # 精确匹配
        if key in defined_keys:
            continue
        # 大小写不敏感匹配
        if key.lower() in defined_keys:
            continue

        # 排除动态拼接的key（heuristic: 如果key看起来像变量名/太短则排除）
        # 但 _collect_all_used_config_keys 已经只提取字符串字面量，
        # 所以这里的key都是硬编码的字符串常量

        # 排除太短的key（可能是误匹配）
        if len(key) <= 2:
            continue

        # 排除明显不是配置项的（单字母、纯数字等）
        if re.match(r'^[0-9]+$', key):
            continue

        # 排除每个项目都会有的通用环境变量（减少误报）
        common_env_vars = (
            "PATH", "HOME", "USER", "PWD", "SHELL", "LANG",
            "TERM", "EDITOR", "TZ", "HOSTNAME",
        )
        if key.upper() in common_env_vars:
            continue

        if key in reported:
            continue
        reported.add(key)

        first_file, first_line = locations[0]
        issues.append({
            "check_id": "HIDDEN-CONFIG-002",
            "name": "代码使用的配置项未在配置文件定义",
            "severity": "high",
            "file": first_file,
            "line": first_line,
            "message": (
                f"代码中使用了配置项 '{key}'，但在配置文件中未找到对应定义，"
                f"运行时将返回 None 或默认值，可能导致功能异常或静默降级"
            ),
            "suggestion": (
                "在配置文件中补充该配置项的定义及默认值，"
                "或确认代码中是否误写了配置key名称"
            ),
        })

    return issues


def _extract_routes_from_code(code_files: Dict[str, str]) -> Dict[str, Dict]:
    """从代码中提取实际注册的路由

    识别模式：
    - @app.route("/path") / @blueprint.route("/path")
    - @router.add("/path") / @router.get("/path") 等
    - add_url_rule("/path", ...)
    - Router().add_route("/path", ...)

    返回: {path: {"file": ..., "line": ..., "methods": [...]}}
    """
    routes: Dict[str, Dict] = {}

    for filepath, content in code_files.items():
        if not filepath.endswith(".py") or not content:
            continue

        lines = content.split("\n")

        for idx, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            path = None
            methods = []

            # 模式1: @xxx.route("/path", methods=["GET", "POST"])
            m = re.search(
                r'@[\w\.]+\.route\s*\(\s*[\'"]([^\'"]+)[\'"]',
                stripped
            )
            if m:
                path = m.group(1)
                # 提取methods
                mm = re.search(r'methods\s*=\s*\[([^\]]*)\]', stripped)
                if mm:
                    methods = re.findall(r'[\'"]([^\'"]+)[\'"]', mm.group(1))
                else:
                    methods = ["GET"]  # Flask默认

            # 模式2: @xxx.get("/path") / @xxx.post("/path") 等
            if not path:
                m = re.search(
                    r'@[\w\.]+\.(get|post|put|delete|patch|head|options)\s*\(\s*[\'"]([^\'"]+)[\'"]',
                    stripped, re.IGNORECASE
                )
                if m:
                    methods = [m.group(1).upper()]
                    path = m.group(2)

            # 模式3: add_url_rule("/path", ...)
            if not path:
                m = re.search(
                    r'\.add_url_rule\s*\(\s*[\'"]([^\'"]+)[\'"]',
                    stripped
                )
                if m:
                    path = m.group(1)

            # 模式4: router.add("/path", ...) / app.add_route(...)
            if not path:
                m = re.search(
                    r'(?:router|app|api)\.(?:add|add_route|register)\s*\(\s*[\'"]([^\'"]+)[\'"]',
                    stripped, re.IGNORECASE
                )
                if m:
                    path = m.group(1)

            if path and path.startswith(("/", "{", "<")):
                # 规范化path（去掉末尾的/）
                norm_path = path.rstrip("/") if path != "/" else "/"
                if norm_path not in routes:
                    routes[norm_path] = {
                        "file": filepath,
                        "line": idx + 1,
                        "methods": set(methods) if methods else set(),
                    }
                else:
                    if methods:
                        routes[norm_path]["methods"].update(methods)

    return routes


def _extract_routes_from_docs(code_files: Dict[str, str]) -> Dict[str, Dict]:
    """从文档文件中提取声明的API接口

    识别模式：
    - Markdown表格/列表中的接口：`GET /api/v1/xxx`、`POST /xxx`
    - OpenAPI/Swagger格式的paths字段
    - 代码块中的curl命令

    返回: {path: {"file": ..., "line": ..., "methods": set(...)}}
    """
    doc_routes: Dict[str, Dict] = {}

    for filepath, content in code_files.items():
        if not content:
            continue

        basename = filepath.replace("\\", "/").rsplit("/", 1)[-1]

        # 判断是否为API文档文件
        is_doc = False
        for pat in _API_DOC_FILE_PATTERNS:
            if basename.lower() == pat.lower():
                is_doc = True
                break
        if not is_doc:
            # 也检查 docs/ 或 doc/ 目录下的 .md 文件
            parts = filepath.replace("\\", "/").split("/")
            if ("docs" in parts or "doc" in parts) and filepath.endswith(".md"):
                is_doc = True
        if not is_doc:
            continue

        lines = content.split("\n")

        # OpenAPI/Swagger YAML/JSON格式
        if filepath.endswith((".yaml", ".yml", ".json")) and (
            "openapi" in content.lower() or "swagger" in content.lower() or "paths:" in content
        ):
            # 提取 paths 下的路径
            # 简单正则匹配 YAML 格式:  /path: 然后下面是  get:/post: 等
            in_paths = False
            current_path = None
            path_indent = -1

            for idx, line in enumerate(lines):
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue

                # 进入paths段
                if re.match(r'^paths\s*:\s*$', stripped):
                    in_paths = True
                    continue
                if in_paths:
                    # 检测路径行（以 / 开头，顶层缩进）
                    indent = len(line) - len(line.lstrip())
                    if stripped.startswith("/") and stripped.endswith(":"):
                        if path_indent == -1 or indent <= path_indent:
                            current_path = stripped.rstrip(":").strip()
                            path_indent = indent
                            if current_path not in doc_routes:
                                doc_routes[current_path] = {
                                    "file": filepath,
                                    "line": idx + 1,
                                    "methods": set(),
                                }
                        continue
                    # 检测方法行（get:/post:等，比路径更深一层缩进）
                    if current_path and indent > path_indent:
                        method_match = re.match(
                            r'^(get|post|put|delete|patch|head|options)\s*:',
                            stripped, re.IGNORECASE
                        )
                        if method_match:
                            method = method_match.group(1).upper()
                            doc_routes[current_path]["methods"].add(method)
                            continue
                    # 离开paths段（遇到同级或更高级的key）
                    if indent <= path_indent and not stripped.startswith("/"):
                        current_path = None
            continue

        # Markdown/纯文本格式：提取 `METHOD /path` 模式
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue

            # 匹配模式: GET /api/xxx, POST /v1/xxx 等
            # 支持反引号包裹: `GET /api/xxx`
            # 支持markdown列表: - GET /api/xxx
            patterns = [
                r'\b(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+(/[^\s`\|\)\]]*)',
                r'`(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+(/[^`]+)`',
            ]
            for pat in patterns:
                for m in re.finditer(pat, stripped, re.IGNORECASE):
                    method = m.group(1).upper()
                    path = m.group(2).rstrip("。，,.;:")
                    # 过滤掉非API路径（如 http:// 开头的完整URL，或太简单的 /）
                    if path.startswith("http"):
                        continue
                    if len(path) < 2:
                        continue
                    # 规范化
                    norm_path = path.rstrip("/") if path != "/" else "/"
                    if norm_path not in doc_routes:
                        doc_routes[norm_path] = {
                            "file": filepath,
                            "line": idx + 1,
                            "methods": set(),
                        }
                    doc_routes[norm_path]["methods"].add(method)

    return doc_routes


def _check_hidden_doc_route_mismatch(code_files: Dict[str, str]) -> List[Dict]:
    """HIDDEN-ROUTE-002 文档声明的接口 vs 实际路由不匹配

    检测逻辑（project级）：
    - 扫描项目中的API文档文件（README.md、swagger、openapi.yaml等），
      提取其中声明的接口路径
    - 扫描代码中实际注册的路由（@app.route / @blueprint.route / add_url_rule 等）
    - 对比两个集合，找出：
      - 文档有但代码没有的接口（文档骗人）
      - 代码有但文档没有的接口（暗门接口/文档遗漏）
    - 如果项目没有找到明显的API文档文件，跳过此规则不报错
    """
    issues = []

    # 第1步：从文档中提取声明的接口
    doc_routes = _extract_routes_from_docs(code_files)
    if not doc_routes:
        # 没有找到API文档，跳过（避免误报）
        return issues

    # 第2步：从代码中提取实际注册的路由
    code_routes = _extract_routes_from_code(code_files)
    if not code_routes:
        # 没有找到路由注册（可能不是Web项目），跳过
        return issues

    # 第3步：对比

    # 3.1 文档有但代码没有（文档骗人）
    for path, info in doc_routes.items():
        if path in code_routes:
            continue
        # 尝试做路径参数匹配（文档可能用 {id} 代码用 <id> 或反之）
        # 将两种参数格式统一替换为占位符再比较
        def normalize_path_params(p: str) -> str:
            # 替换 <xxx> / <int:xxx> / {xxx} / :xxx 为统一占位符
            p = re.sub(r'<[^>]+>', '{param}', p)
            p = re.sub(r'\{[^}]+\}', '{param}', p)
            p = re.sub(r':\w+', '{param}', p)
            return p

        norm_doc_path = normalize_path_params(path)
        found_match = False
        for code_path in code_routes:
            if normalize_path_params(code_path) == norm_doc_path:
                found_match = True
                break
        if found_match:
            continue

        # 过滤掉明显不是API的路径（如只是文档中提到的URL示例）
        # 启发：路径至少包含 /api/ 或 /v1/ 等特征，或以 /api 开头
        if not (path.startswith("/api") or "/api/" in path or
                re.search(r'/v\d+/', path) or path.startswith("/v")):
            # 只有当项目代码中的路由也大多是API风格时才报
            # 如果代码路由大多是 /api/xxx 风格，则文档中不以/api开头的也可能是简写
            code_api_ratio = sum(
                1 for cp in code_routes if cp.startswith("/api") or "/api/" in cp
            ) / len(code_routes) if code_routes else 0
            if code_api_ratio < 0.5:
                # 代码中API风格的也不多，可能不是Web API项目，跳过
                continue

        issues.append({
            "check_id": "HIDDEN-ROUTE-002",
            "name": "文档声明接口但代码未实现",
            "severity": "high",
            "file": info["file"],
            "line": info["line"],
            "message": (
                f"文档中声明了接口 {path}，但代码中未找到对应路由注册，"
                f"属于文档承诺但实际不存在的接口"
            ),
            "suggestion": "在代码中实现该接口路由，或更新文档移除未实现的接口声明",
        })

    # 3.2 代码有但文档没有（暗门接口/文档遗漏）
    for path, info in code_routes.items():
        if path in doc_routes:
            continue

        # 同样做路径参数规范化匹配
        def normalize_path_params(p: str) -> str:
            p = re.sub(r'<[^>]+>', '{param}', p)
            p = re.sub(r'\{[^}]+\}', '{param}', p)
            p = re.sub(r':\w+', '{param}', p)
            return p

        norm_code_path = normalize_path_params(path)
        found_match = False
        for doc_path in doc_routes:
            if normalize_path_params(doc_path) == norm_code_path:
                found_match = True
                break
        if found_match:
            continue

        # 过滤掉静态资源、健康检查等常见的无需文档的路径
        skip_patterns = (
            "/static", "/favicon.ico", "/health", "/healthz",
            "/ping", "/metrics", "/docs", "/swagger", "/openapi",
            "/redoc", "/",
        )
        skip = False
        for sp in skip_patterns:
            if path == sp or path.startswith(sp + "/"):
                skip = True
                break
        if skip:
            continue

        # 只报告明显是业务接口的路径（含/api/或/vN/前缀）
        if not (path.startswith("/api") or "/api/" in path or
                re.search(r'/v\d+/', path) or path.startswith("/v")):
            continue

        issues.append({
            "check_id": "HIDDEN-ROUTE-002",
            "name": "代码有接口但文档未声明",
            "severity": "high",
            "file": info["file"],
            "line": info["line"],
            "message": (
                f"代码中注册了路由 {path}，但文档中未声明该接口，"
                f"属于文档遗漏或未公开的暗门接口"
            ),
            "suggestion": "在API文档中补充该接口的说明，或确认是否为不应暴露的内部接口",
        })

    return issues


# ---------------------------------------------------------------------------
# 隐藏Bug检测规则 - 路径命名不匹配 / 降级覆盖率 / 开关对账 / 事件发布裸发
# ---------------------------------------------------------------------------

# 常见同义词对（用于PATH-001误报控制，key和value的核心词若为同义词则不报）
_COMMON_ACTION_SYNONYMS = {
    # add / create / insert / new / submit / post
    "add": {"add", "create", "insert", "new", "put", "submit", "post"},
    "create": {"add", "create", "insert", "new", "put", "submit", "post", "make", "build"},
    "insert": {"add", "create", "insert", "new", "submit", "post"},
    "new": {"add", "create", "insert", "new", "submit"},
    "submit": {"add", "create", "insert", "new", "post", "submit"},
    "post": {"add", "create", "insert", "submit", "post"},
    # delete / remove / destroy / drop
    "delete": {"delete", "remove", "destroy", "drop", "del", "rm"},
    "remove": {"delete", "remove", "destroy", "drop", "del", "rm"},
    "destroy": {"delete", "remove", "destroy"},
    "drop": {"delete", "remove", "drop"},
    # update / modify / edit / set / change
    "update": {"update", "modify", "edit", "set", "change", "patch", "put"},
    "modify": {"update", "modify", "edit", "change"},
    "edit": {"update", "modify", "edit", "change"},
    "set": {"update", "set", "change"},
    # get / query / fetch / list / read / show / view
    "get": {"get", "query", "fetch", "list", "read", "show", "view", "retrieve", "find", "search"},
    "query": {"get", "query", "fetch", "list", "search", "find"},
    "fetch": {"get", "query", "fetch", "retrieve"},
    "list": {"get", "query", "list", "all"},
    "read": {"get", "read", "view", "show"},
    "search": {"get", "query", "search", "find"},
    "find": {"get", "query", "find", "search"},
    # user / account
    "user": {"user", "account"},
    "account": {"user", "account"},
    # init / initialize / setup
    "init": {"init", "initialize", "setup", "start"},
    "initialize": {"init", "initialize", "setup"},
    "setup": {"init", "setup", "initialize"},
    # stop / shutdown / exit / close
    "stop": {"stop", "shutdown", "exit", "close", "quit", "terminate"},
    "shutdown": {"stop", "shutdown", "exit", "close"},
    "exit": {"stop", "exit", "quit", "close"},
    # send / publish / emit / dispatch / notify
    "send": {"send", "publish", "emit", "dispatch", "notify", "post"},
    "publish": {"send", "publish", "emit", "dispatch"},
    "emit": {"send", "emit", "publish", "dispatch"},
    "dispatch": {"send", "dispatch", "emit", "route"},
    # login / signin / auth
    "login": {"login", "signin", "sign_in", "auth", "authenticate"},
    "signin": {"login", "signin", "auth"},
    "auth": {"login", "auth", "authenticate", "permission"},
    # logout / signout
    "logout": {"logout", "signout", "sign_out"},
    "signout": {"logout", "signout"},
    # config / setting / option
    "config": {"config", "setting", "settings", "option", "configuration"},
    "setting": {"config", "setting", "settings", "option"},
    "settings": {"config", "setting", "settings", "option"},
    # info / detail
    "info": {"info", "detail", "details"},
    "detail": {"info", "detail", "details"},
    "details": {"info", "detail", "details"},
}

# 开关/Feature Flag 关键词（用于CONFIG-003识别开关型配置）
_FEATURE_FLAG_KEYWORDS = (
    "enable", "enabled", "disable", "disabled",
    "flag", "flags", "toggle", "toggles",
    "feature", "switch", "on", "off",
    "开关", "启用", "禁用", "开启", "关闭",
)

# 开关/Feature Flag 相关的if判断模式
_FEATURE_FLAG_IF_PATTERNS = (
    # if config.ENABLE_XXX / if settings.XXX_ENABLED
    r'\b(?:config|cfg|settings|conf)\.([A-Z_]*(?:ENABLE|DISABLE|FLAG|TOGGLE|FEATURE|SWITCH)[A-Z0-9_]*)\b',
    # if ENABLE_XXX / if XXX_ENABLED （全局配置常量）
    r'\b([A-Z_]*(?:ENABLE|DISABLE|FLAG|TOGGLE|FEATURE|SWITCH)[A-Z0-9_]*)\b',
)

# MQ/事件库关键词（用于EVENT-001识别明确的MQ场景）
_MQ_LIBRARY_KEYWORDS = (
    "pika", "kombu", "celery", "redis", "kafka",
    "confluent_kafka", "kafka_python", "kafka-python",
    "rabbitmq", "amqp", "mqtt", "nats",
    "producer", "consumer", "broker",
)

# 事件发布方法名（用于EVENT-001识别发布点）
_EVENT_PUBLISH_METHODS = (
    "publish", "basic_publish", "send_event", "emit", "dispatch",
    "mq_send", "send_mq", "producer.send", "producer.publish",
    "send_message", "post_event", "fire_event",
    "push_event", "broadcast", "produce",
    "send",  # catch-all，但仅在MQ文件中检测
)

# 重试/死信/失败处理关键词（EVENT-001的安全信号）
_EVENT_RELIABILITY_KEYWORDS = (
    "retry", "重试", "max_retry", "retry_count", "retry_times",
    "dead_letter", "dlq", "死信", "dead_letter_exchange", "dead_letter_routing_key",
    "on_failure", "failure_callback", "失败回调", "补偿", "compensate",
    "try:", "except ",
    "retry_policy", "backoff",
)

# 路由/分发表 变量名模式（PATH-001）
_ROUTE_DISPATCH_MAP_PATTERNS = (
    "_ROUTE_MAP", "route_map", "action_map", "_ACTION_MAP",
    "handler_map", "_HANDLER_MAP", "dispatch_map", "_DISPATCH_MAP",
    "url_map", "_URL_MAP", "endpoint_map", "_ENDPOINT_MAP",
    "api_map", "_API_MAP", "view_map", "_VIEW_MAP",
    "router_map", "_ROUTER_MAP", "PATH_MAP", "_PATH_MAP",
    "MODULE_MAP", "module_map", "plugin_map", "_PLUGIN_MAP",
)


def _extract_words_from_name(name: str) -> set:
    """从一个标识符（函数名/key名/文件名）中提取词元集合

    支持 snake_case、camelCase、PascalCase 的拆分。
    全部转为小写。
    """
    name = name.strip()
    if not name:
        return set()

    # 先按分隔符拆分
    parts = re.split(r'[_\-\./]+', name)
    words = set()
    for part in parts:
        if not part:
            continue
        # 驼峰拆分: CamelCase / camelCase / camel2Case
        # 先在大写字母前加空格
        sub = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', part)
        sub = re.sub(r'([a-z\d])([A-Z])', r'\1_\2', sub)
        for w in re.split(r'[_\s]+', sub):
            w_lower = w.lower()
            if w_lower:
                words.add(w_lower)
    return words


def _words_are_synonyms(word_a: str, word_b: str) -> bool:
    """判断两个词是否为常见同义词（PATH-001误报控制）"""
    if word_a == word_b:
        return True
    syn_set = _COMMON_ACTION_SYNONYMS.get(word_a, set())
    return word_b in syn_set


def _key_value_words_match(key_words: set, value_words: set) -> bool:
    """判断key的词集合与value的词集合是否有足够的共享词根

    为了保守（宁可不报不误报），只要满足以下任一条件即认为"匹配"：
    - 两个集合有交集（完全相同的词）
    - 每个key中的业务核心词（排除常见通用词）都能在value中找到同义词
    """
    # 完全交集
    if key_words & value_words:
        return True

    # 排除常见通用词后的核心词比对
    generic_words = {
        "the", "a", "an", "is", "are", "to", "of", "in", "on", "for",
        "with", "by", "from", "at", "as", "and", "or", "not",
        # 编程常见通用词
        "handler", "handle", "controller", "view", "api", "endpoint",
        "action", "route", "path", "url", "func", "function", "method",
        "do", "run", "exec", "execute", "call", "invoke",
        "init",
        "data", "info", "item", "obj", "object", "val", "value",
        "req", "request", "resp", "response", "result", "res",
    }

    key_core = key_words - generic_words
    value_core = value_words - generic_words

    if not key_core or not value_core:
        # 核心词为空，说明都是通用词，不算不匹配
        return True

    # 检查是否存在同义词对（保守策略：只要有一对核心词是同义词，就算语义关联）
    # 典型场景：submit -> create_order（submit与create同义），list -> get_users（list与get同义）
    has_synonym_pair = False
    for kw in key_core:
        for vw in value_core:
            if _words_are_synonyms(kw, vw):
                has_synonym_pair = True
                break
        if has_synonym_pair:
            break

    if has_synonym_pair:
        return True

    # 检查：value的每个核心词，是否在key中能找到同义词？
    # （反过来也检查，双向确认）
    # 全匹配是更严格的标准，仅作为兜底
    all_value_match = True
    for vw in value_core:
        found = False
        for kw in key_core:
            if _words_are_synonyms(kw, vw):
                found = True
                break
        if not found:
            all_value_match = False
            break

    all_key_match = True
    for kw in key_core:
        found = False
        for vw in value_core:
            if _words_are_synonyms(kw, vw):
                found = True
                break
        if not found:
            all_key_match = False
            break

    # 只要有一个方向全部匹配上，就认为语义一致（不算不匹配）
    if all_key_match or all_value_match:
        return True

    return False


def _check_hidden_path_key_value_mismatch(code_files: Dict[str, str]) -> List[Dict]:
    """HIDDEN-PATH-001 调用方key与被调方path/函数命名不匹配

    检测逻辑（保守版，宁可不报也不误报）：
    - 识别文件中的"路由映射/分发字典"（变量名匹配 *_MAP / *_ROUTES 等）
    - 对比字典的key（字符串字面量）与对应的value（函数名/模块名），
      检查是否存在"key里的核心业务词在value里完全找不到，且不是同义词"的情况
    - 只报"明显不匹配"：key和value完全没有共享词根，且核心业务词无法通过同义词关联
    - 排除：单字key、纯数字key、通用词key、明显的别名映射场景

    严重度：high（但触发条件极严格，误报率压到最低）
    """
    issues = []

    for filepath, content in code_files.items():
        if not filepath.endswith(".py") or not content:
            continue

        # 快速跳过：文件中没有路由映射类变量
        has_map = False
        for pat in _ROUTE_DISPATCH_MAP_PATTERNS:
            if pat in content:
                has_map = True
                break
        if not has_map:
            continue

        lines = content.split("\n")

        for var_name in _ROUTE_DISPATCH_MAP_PATTERNS:
            # 匹配 var_name = { ... } （支持跨行）
            # 用非贪婪匹配+正确括号平衡可能复杂，这里用简单模式：
            # 从 var_name = { 开始，找到匹配的结束 }
            pattern = re.compile(
                rf'{re.escape(var_name)}\s*=\s*\{{',
            )
            match = pattern.search(content)
            if not match:
                continue

            start_pos = match.end() - 1  # { 的位置
            start_line = content[:start_pos].count("\n") + 1

            # 找到匹配的闭合 } （简单括号计数，忽略字符串中的{}）
            # 简化：假设字典内没有嵌套字典（路由映射通常是单层的）
            # 如果有嵌套，找到第一个 } 就会停，可能不准确；
            # 为了保守，我们用更简单的方式：从 { 开始逐字符计数
            brace_count = 0
            in_string = False
            string_char = None
            dict_body = ""
            end_pos = -1

            for i in range(start_pos, len(content)):
                c = content[i]
                if in_string:
                    if c == string_char and content[i - 1] != "\\":
                        in_string = False
                    continue
                if c in ('"', "'"):
                    in_string = True
                    string_char = c
                    continue
                if c == "{":
                    brace_count += 1
                    if brace_count == 1:
                        dict_body_start = i + 1
                elif c == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        end_pos = i
                        dict_body = content[dict_body_start:i]
                        break

            if end_pos == -1 or not dict_body:
                continue

            # 提取所有 "key": value 对
            # 匹配 "key": func_name 或 'key': func_name
            kv_pattern = re.compile(
                r'[\'"]([^\'"]+)[\'"]\s*:\s*([A-Za-z_]\w*)',
            )

            for kv_match in kv_pattern.finditer(dict_body):
                key = kv_match.group(1)
                value_name = kv_match.group(2)

                # 排除：value是 None / True / False / 数字等
                if value_name in ("None", "True", "False"):
                    continue

                # 排除：key太短（1-2个字符），可能是状态码等
                if len(key) <= 2:
                    continue

                # 排除：key看起来像URL路径（含 / 的），这是路由path而非别名
                if "/" in key:
                    continue

                # 排除：纯数字key
                if re.match(r'^\d+$', key):
                    continue

                # 提取词元
                key_words = _extract_words_from_name(key)
                value_words = _extract_words_from_name(value_name)

                if not key_words or not value_words:
                    continue

                # 检查是否匹配（有共享词根 / 同义词）
                if _key_value_words_match(key_words, value_words):
                    continue

                # 计算行号
                key_pos_in_body = kv_match.start()
                line_offset = dict_body[:key_pos_in_body].count("\n")
                line_no = start_line + line_offset

                issues.append({
                    "check_id": "HIDDEN-PATH-001",
                    "name": "分发key与目标函数命名不匹配",
                    "severity": "high",
                    "file": filepath,
                    "line": line_no,
                    "message": (
                        f"分发表中 key='{key}' 映射到函数 '{value_name}'，"
                        f"二者命名无共享词根且非同义关系，"
                        f"可能是映射错误（404风险）或命名不一致"
                    ),
                    "suggestion": (
                        "确认该映射是否正确；若为有意的别名映射，建议统一命名风格"
                        "或添加注释说明别名关系，避免维护误解"
                    ),
                })

            # 一个变量名匹配到一个字典就够了，不再尝试其他
            break

    # 去重（同一文件同一行的重复报告）
    seen = set()
    unique_issues = []
    for iss in issues:
        key = (iss["check_id"], iss["file"], iss["line"], iss["message"])
        if key not in seen:
            seen.add(key)
            unique_issues.append(iss)

    return unique_issues


def _check_hidden_degraded_coverage_stats(code_files: Dict[str, str]) -> List[Dict]:
    """HIDDEN-DEG-004 降级覆盖率统计（信息性，low）

    项目级统计：扫描整个项目的降级点，输出一份降级覆盖率统计报告：
    - 总共有多少个降级点
    - 分布在哪些模块
    - 哪些有监控告警
    - 哪些完全静默

    这是一条"信息性"规则，不报警（报low提示），输出统计摘要。
    """
    issues = []

    # 收集所有降级点及其监控状态
    # list of dict: {"file": ..., "line": ..., "has_monitoring": bool}
    degradation_sites = []
    module_distribution = defaultdict(int)  # 模块 -> 降级点数量

    for filepath, content in code_files.items():
        if not filepath.endswith(".py") or not content:
            continue

        # 快速跳过
        has_deg = False
        for kw in _DEGRADATION_KEYWORDS:
            if kw in content:
                has_deg = True
                break
        if not has_deg:
            continue

        lines = content.split("\n")

        # 排除纯注释行和docstring
        in_docstring = False
        code_line_indices = []
        for idx, line in enumerate(lines):
            stripped = line.strip()
            triple_count = stripped.count('"""') + stripped.count("'''")
            if triple_count > 0 and not stripped.startswith("#"):
                if in_docstring:
                    if triple_count % 2 == 1:
                        in_docstring = False
                else:
                    if triple_count % 2 == 1:
                        in_docstring = True
                continue
            if in_docstring:
                continue
            if stripped.startswith("#") or not stripped:
                continue
            code_line_indices.append(idx)

        code_line_set = set(code_line_indices)

        # 找降级关键词所在行
        deg_line_indices = set()
        for idx in code_line_indices:
            line = lines[idx]
            for kw in _DEGRADATION_KEYWORDS:
                if kw in line:
                    deg_line_indices.add(idx)
                    break

        if not deg_line_indices:
            continue

        # 合并相近降级行为块
        sorted_deg_lines = sorted(deg_line_indices)
        merged_blocks = []
        current_start = sorted_deg_lines[0]
        current_end = sorted_deg_lines[0]

        for line_no in sorted_deg_lines[1:]:
            if line_no - current_end <= 5:
                current_end = line_no
            else:
                merged_blocks.append((current_start, current_end))
                current_start = line_no
                current_end = line_no
        merged_blocks.append((current_start, current_end))

        # 提取模块名（目录/文件名前缀）
        parts = filepath.replace("\\", "/").split("/")
        if len(parts) >= 2:
            module_name = "/".join(parts[-2:])  # 最后两级
        else:
            module_name = parts[0] if parts else filepath

        for block_start, block_end in merged_blocks:
            # 检查是否有可执行语义（排除纯函数定义行）
            block_has_exec = False
            for idx in range(block_start, block_end + 1):
                if idx not in code_line_set:
                    continue
                line = lines[idx].strip()
                if (line.startswith("return") or
                    line.startswith("raise ") or
                    line == "pass" or
                    "= True" in line or
                    "= False" in line or
                    "= None" in line or
                    "= []" in line or
                    "= {}" in line or
                    line.startswith("if ") or
                    line.startswith("elif ")):
                    block_has_exec = True
                    break
            if not block_has_exec:
                continue

            # 检查前后10行内是否有监控/告警
            window_start = max(0, block_start - 10)
            window_end = min(len(lines) - 1, block_end + 10)

            has_monitoring = False
            for w_idx in range(window_start, window_end + 1):
                if w_idx not in code_line_set:
                    continue
                wline = lines[w_idx]
                for mkw in _MONITORING_KEYWORDS:
                    if mkw in wline:
                        has_monitoring = True
                        break
                if has_monitoring:
                    break

            degradation_sites.append({
                "file": filepath,
                "line": block_start + 1,
                "has_monitoring": has_monitoring,
            })
            module_distribution[module_name] += 1

    if not degradation_sites:
        # 项目中没有降级点，不输出统计
        return issues

    total = len(degradation_sites)
    monitored = sum(1 for d in degradation_sites if d["has_monitoring"])
    silent = total - monitored

    # 按模块排序（降级点多的排前面）
    sorted_modules = sorted(
        module_distribution.items(),
        key=lambda x: x[1],
        reverse=True
    )
    top_modules = sorted_modules[:5]  # 取前5个模块
    module_str = ", ".join(f"{m}({c})" for m, c in top_modules)
    if len(sorted_modules) > 5:
        module_str += f" ...（共{len(sorted_modules)}个模块）"

    # 找第一个静默降级点作为报告锚点
    first_silent = None
    for d in degradation_sites:
        if not d["has_monitoring"]:
            first_silent = d
            break

    # 如果所有降级点都有监控，用第一个作为锚点
    anchor = first_silent if first_silent else degradation_sites[0]

    monitored_ratio = (monitored / total * 100) if total > 0 else 0

    issues.append({
        "check_id": "HIDDEN-DEG-004",
        "name": "降级覆盖率统计",
        "severity": "low",
        "file": anchor["file"],
        "line": anchor["line"],
        "message": (
            f"项目共 {total} 个降级点，其中 {monitored} 个有监控告警"
            f"（覆盖率 {monitored_ratio:.0f}%），{silent} 个完全静默；"
            f"分布模块：{module_str}"
        ),
        "suggestion": (
            "建议为静默降级点补充监控埋点（logging.warning/metrics计数），"
            "确保降级可观测、可告警；覆盖率目标建议达到100%"
        ),
    })

    return issues


def _is_feature_flag_key(key: str) -> bool:
    """判断一个配置key是否为开关/Feature Flag类型

    含 enable/disable/flag/toggle/feature/switch/on/off/开关 等关键词。
    """
    key_lower = key.lower()
    # 替换下划线/连字符方便匹配
    key_norm = key_lower.replace("_", "").replace("-", "")
    for kw in _FEATURE_FLAG_KEYWORDS:
        kw_norm = kw.replace("_", "")
        if kw_norm in key_norm:
            return True
    return False


def _collect_feature_flag_ifs(code_files: Dict[str, str]) -> Dict[str, List[tuple]]:
    """收集代码中所有开关型if判断的配置key

    识别模式：
    - if config.ENABLE_XXX / if settings.XXX_ENABLED
    - if cfg.FEATURE_XXX / if conf.DISABLE_YYY
    - if ENABLE_XXX （全局常量）
    - if config.get("ENABLE_XXX") / if config["ENABLE_XXX"]

    返回: {key: [(file, line), ...]}
    """
    used_keys: Dict[str, List[tuple]] = defaultdict(list)

    for filepath, content in code_files.items():
        if not filepath.endswith(".py") or not content:
            continue

        lines = content.split("\n")
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                continue

            # 只看 if / elif / while 条件行（条件判断行）
            if not re.match(r'^(if|elif|while)\s+', stripped):
                continue

            found_keys = []

            # 模式1: config.ENABLE_XXX / settings.XXX_ENABLED
            for m in re.finditer(
                r'\b(?:config|cfg|settings|conf|app_config)\.([A-Z_][A-Z0-9_]*)\b',
                stripped,
            ):
                key = m.group(1)
                # 排除方法名
                if key in ("get", "items", "keys", "values", "setdefault",
                           "update", "pop", "copy", "clear", "fromkeys"):
                    continue
                if _is_feature_flag_key(key):
                    found_keys.append(key)

            # 模式2: config.get("ENABLE_XXX") / config["ENABLE_XXX"]
            for m in re.finditer(
                r'(?:config|cfg|settings|conf)\.(?:get|__getitem__)\s*\(\s*[\'"]([^\'"]+)[\'"]',
                stripped, re.IGNORECASE,
            ):
                key = m.group(1)
                if _is_feature_flag_key(key):
                    found_keys.append(key)

            # 模式3: CONFIG["ENABLE_XXX"] / settings["ENABLE_XXX"]
            for m in re.finditer(
                r'(?:CONFIG|settings|config)\[["\']([^"\']+)["\']\]',
                stripped,
            ):
                key = m.group(1)
                if _is_feature_flag_key(key):
                    found_keys.append(key)

            # 模式4: 全大写的开关常量（if ENABLE_FEATURE_X:）
            # 仅在 if 语句开头匹配独立的全大写标识符
            for m in re.finditer(
                r'\b([A-Z_][A-Z0-9_]*)\b',
                stripped,
            ):
                key = m.group(1)
                # 排除太短的、Python关键字、常见变量
                if len(key) < 4:
                    continue
                if key in ("TRUE", "FALSE", "NONE", "AND", "OR", "NOT",
                           "IF", "ELIF", "ELSE", "FOR", "WHILE", "IN",
                           "IS", "NOT", "RETURN", "BREAK", "CONTINUE",
                           "PASS", "RAISE", "TRY", "EXCEPT", "FINALLY"):
                    continue
                if _is_feature_flag_key(key):
                    found_keys.append(key)

            for key in found_keys:
                used_keys[key].append((filepath, idx + 1))

    return used_keys


def _check_hidden_config_switch_reconcile(code_files: Dict[str, str]) -> List[Dict]:
    """HIDDEN-CONFIG-003 配置开关 vs 代码if判断点 双向对账

    检测逻辑：
    - 识别feature flag/开关类配置（配置项名含 enable/disable/flag/toggle/feature/开关 等）
    - 检查代码中对应的if判断点：
      - 配置有开关但代码中没有条件判断（死开关）
      - 代码有开关判断但配置中无定义（悬空开关）
    - 报 medium

    与CONFIG-001/002的区别：专门针对"开关型配置"做精确的if判断对账，
    而不是泛泛的"是否使用"。
    """
    issues = []

    # 第1步：找配置文件，提取所有开关型配置key
    config_files = _find_config_files(code_files)
    if not config_files:
        return issues

    defined_switch_keys: Dict[str, Dict] = {}  # key -> {"file": ..., "line": ...}
    for cfg_file, content in config_files.items():
        if cfg_file.endswith(".py"):
            keys = _extract_config_keys_from_py(content)
        elif cfg_file.endswith((".yaml", ".yml")):
            keys = _extract_config_keys_from_yaml(content)
        elif cfg_file.endswith(".env"):
            keys = _extract_config_keys_from_env(content)
        else:
            continue

        for key, line_no in keys.items():
            if not _is_feature_flag_key(key):
                continue
            if key not in defined_switch_keys:
                defined_switch_keys[key] = {"file": cfg_file, "line": line_no}

    # 第2步：收集代码中所有开关型if判断
    code_switch_ifs = _collect_feature_flag_ifs(code_files)

    # 第3步：双向对账

    # 3.1 配置有开关，但代码中没有对应的if判断（死开关）
    for key, info in defined_switch_keys.items():
        # 精确匹配
        if key in code_switch_ifs:
            continue
        # 大小写不敏感匹配
        found_variant = False
        for code_key in code_switch_ifs:
            if code_key.lower() == key.lower():
                found_variant = True
                break
        if found_variant:
            continue

        # 排除明显非业务的开关
        if key.startswith("__"):
            continue
        if len(key) <= 2:
            continue

        issues.append({
            "check_id": "HIDDEN-CONFIG-003",
            "name": "配置开关未被代码使用（死开关）",
            "severity": "medium",
            "file": info["file"],
            "line": info["line"],
            "message": (
                f"开关型配置项 '{key}' 在配置文件中定义，"
                f"但代码中未找到对应的 if 判断，该开关可能已废弃（死开关）"
            ),
            "suggestion": (
                "确认该开关是否仍在使用；若已废弃应及时清理，"
                "避免维护人员误以为开关仍在控制某项功能"
            ),
        })

    # 3.2 代码中有开关判断，但配置文件中未定义（悬空开关）
    reported = set()
    for key, locations in code_switch_ifs.items():
        # 精确匹配
        if key in defined_switch_keys:
            continue
        # 大小写不敏感匹配
        found_def = False
        for def_key in defined_switch_keys:
            if def_key.lower() == key.lower():
                found_def = True
                break
        if found_def:
            continue

        # 排除太短/动态key
        if len(key) <= 2:
            continue
        if re.match(r'^[0-9]+$', key):
            continue

        if key in reported:
            continue
        reported.add(key)

        first_file, first_line = locations[0]
        issues.append({
            "check_id": "HIDDEN-CONFIG-003",
            "name": "代码开关判断无对应配置定义（悬空开关）",
            "severity": "medium",
            "file": first_file,
            "line": first_line,
            "message": (
                f"代码中有针对开关 '{key}' 的条件判断，"
                f"但配置文件中未找到对应开关的定义，"
                f"该判断可能始终为False（或依赖默认值），功能可能未生效"
            ),
            "suggestion": (
                "在配置文件中补充该开关的定义及默认值，"
                "或确认代码中的开关判断是否为遗留代码"
            ),
        })

    return issues


def _check_hidden_event_no_retry_dlq(code_files: Dict[str, str]) -> List[Dict]:
    """HIDDEN-EVENT-001 事件发布无失败重试/死信队列

    检测逻辑：
    - 识别事件/消息发布点：
      publish/send_event/emit/dispatch/mq_send/producer.send 等
      且文件中导入了 MQ 库（pika/kafka/redis/celery 等）
    - 检查发布点附近（前后20行）：
      - 有没有 try-except 重试机制（retry/重试）
      - 有没有死信队列配置（dead_letter/dlq/死信）
      - 有没有失败回调/补偿机制
    - 如果事件发布完全"裸发" → 报 medium

    误报控制：
    - 只对明确的MQ/事件发布场景检测（需要import了MQ库）
    - 简单的观察者模式/本地事件总线不报
    - 已有 try-except 异常处理的不报
    """
    issues = []

    # 先收集所有 import 了 MQ 库的文件
    mq_files = {}  # filepath -> content
    for filepath, content in code_files.items():
        if not filepath.endswith(".py") or not content:
            continue

        # 检查是否导入了MQ库
        has_mq_import = False
        for mq_kw in _MQ_LIBRARY_KEYWORDS:
            # 匹配 import pika / from kafka import / import redis 等
            pattern = re.compile(
                rf'(?:^from\s+[\w\.]*{re.escape(mq_kw)}[\w\.]*\s+import|'
                rf'^import\s+[\w\.]*{re.escape(mq_kw)}[\w\.]*)',
                re.IGNORECASE | re.MULTILINE,
            )
            if pattern.search(content):
                has_mq_import = True
                break

        # 也检查：文件中是否有明确的MQ客户端对象
        if not has_mq_import:
            explicit_mq_patterns = (
                r'\bproducer\s*=',
                r'\bkafka\s*=',
                r'\brabbitmq\s*=',
                r'\bConsumer\s*\(',
                r'\bProducer\s*\(',
            )
            for pat in explicit_mq_patterns:
                if re.search(pat, content):
                    has_mq_import = True
                    break

        if has_mq_import:
            mq_files[filepath] = content

    if not mq_files:
        # 项目中没有MQ库，跳过
        return issues

    # 对每个MQ相关文件，找发布点并检查可靠性
    for filepath, content in mq_files.items():
        lines = content.split("\n")

        # 排除纯注释/docstring行
        in_docstring = False
        code_line_indices = []
        for idx, line in enumerate(lines):
            stripped = line.strip()
            triple_count = stripped.count('"""') + stripped.count("'''")
            if triple_count > 0 and not stripped.startswith("#"):
                if in_docstring:
                    if triple_count % 2 == 1:
                        in_docstring = False
                else:
                    if triple_count % 2 == 1:
                        in_docstring = True
                continue
            if in_docstring:
                continue
            if stripped.startswith("#") or not stripped:
                continue
            code_line_indices.append(idx)

        code_line_set = set(code_line_indices)

        # 找事件发布点
        publish_line_indices = []
        for idx in code_line_indices:
            line = lines[idx]
            for method in _EVENT_PUBLISH_METHODS:
                # 匹配方法调用：方法名后面跟括号
                # 方法名前可以是 . 或 _ （如 .publish( / basic_publish( / _send_event(）
                pattern = re.compile(
                    rf'(?:[._]|^){re.escape(method)}\s*\(',
                )
                if pattern.search(line):
                    publish_line_indices.append(idx)
                    break

        if not publish_line_indices:
            continue

        # 合并相近的发布点（同一函数/同一块的多个发布）
        sorted_pub_lines = sorted(publish_line_indices)
        merged_blocks = []
        current_start = sorted_pub_lines[0]
        current_end = sorted_pub_lines[0]

        for line_no in sorted_pub_lines[1:]:
            if line_no - current_end <= 5:
                current_end = line_no
            else:
                merged_blocks.append((current_start, current_end))
                current_start = line_no
                current_end = line_no
        merged_blocks.append((current_start, current_end))

        # 对每个发布块，检查前后20行的可靠性机制
        for block_start, block_end in merged_blocks:
            window_start = max(0, block_start - 20)
            window_end = min(len(lines) - 1, block_end + 20)

            has_retry = False
            has_dlq = False
            has_fail_handler = False
            has_try_except = False

            for w_idx in range(window_start, window_end + 1):
                if w_idx not in code_line_set:
                    continue
                wline = lines[w_idx].strip()

                # 重试机制
                if not has_retry:
                    retry_signals = (
                        "retry", "重试", "max_retry", "retry_count",
                        "retry_times", "retry_policy", "backoff",
                        "while True:",  # 无限重试循环
                        "for .*retry",  # for retry in range(3)
                    )
                    for sig in retry_signals:
                        if sig in wline.lower():
                            has_retry = True
                            break

                # 死信队列
                if not has_dlq:
                    dlq_signals = (
                        "dead_letter", "dlq", "死信",
                        "dead_letter_exchange", "dead_letter_routing_key",
                        "dead letter",
                    )
                    for sig in dlq_signals:
                        if sig in wline.lower():
                            has_dlq = True
                            break

                # 失败回调/补偿
                if not has_fail_handler:
                    fail_signals = (
                        "on_failure", "failure_callback", "失败回调",
                        "补偿", "compensate", "fallback",
                        "failover", "失败处理",
                    )
                    for sig in fail_signals:
                        if sig in wline.lower():
                            has_fail_handler = True
                            break

                # try-except
                if not has_try_except:
                    if (wline.startswith("try:") or
                        wline.startswith("try ") or
                        wline.startswith("except ")):
                        has_try_except = True

            # 如果什么都没有 → 裸发，报medium
            if not (has_retry or has_dlq or has_fail_handler or has_try_except):
                report_line = block_start + 1
                issues.append({
                    "check_id": "HIDDEN-EVENT-001",
                    "name": "事件发布无失败重试/死信队列",
                    "severity": "medium",
                    "file": filepath,
                    "line": report_line,
                    "message": (
                        f"检测到MQ/事件发布操作，但前后20行内没有发现"
                        f"重试机制、死信队列配置、失败回调或try-except异常处理，"
                        f"发布失败时消息可能丢失且无法感知"
                    ),
                    "suggestion": (
                        "为事件发布添加可靠性保障：1）添加 try-except 异常捕获；"
                        "2）配置重试机制（指数退避）；3）配置死信队列确保消息不丢失；"
                        "4）发布失败时记录错误日志或触发告警"
                    ),
                })

    return issues


# ============================================================
# ARCH-API-CONSISTENCY: API返回结构一致性检测
# ============================================================

# 统一响应包装函数名模式
_RESPONSE_WRAPPER_NAMES = (
    "success", "fail", "error", "response", "common_response",
    "make_response", "result", "api_response", "json_response",
    "ok", "err", "wrap_response", "build_response",
    "返回成功", "返回失败", "统一响应",
)


def _check_api_return_consistency(code_files: Dict[str, str]) -> List[Dict]:
    """ARCH-API-CONSISTENCY API返回结构一致性检测

    检测逻辑：
    1. 扫描所有路由处理函数（Flask: @app.route/@blueprint.route, FastAPI: @app.get/post等）
    2. 提取每个路由函数的返回模式：
       - jsonify() / JSONResponse 的字段结构
       - return dict 的字段结构
       - 统一响应包装函数的调用（如 success()/fail()/response() 等）
    3. 对比所有接口的返回结构，找出不一致的地方

    简化实现（v1版本）：
    - 如果项目中大部分路由都调用同一个响应函数，少数直接返回dict/jsonify的，
      报告为"未使用统一响应包装"
    - 如果没有统一响应包装，检测命名风格：同一项目中同时存在驼峰字段和下划线
      字段的接口返回 → 报告字段命名风格不一致

    告警级别：low
    """
    issues = []

    # 收集所有路由函数的返回模式
    route_returns = []  # list of {file, line, wrapper, has_jsonify, has_dict_return, fields}

    for filepath, content in code_files.items():
        if not filepath.endswith(".py") or not content:
            continue

        lines = content.split("\n")

        # 找到所有路由装饰器的行号
        route_decorator_lines = []
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            # @xxx.route(...) 或 @xxx.get/post/put/delete(...)
            if re.match(r'@[\w\.]+\.(route|get|post|put|delete|patch)\s*\(', stripped, re.I):
                route_decorator_lines.append(idx)

        if not route_decorator_lines:
            continue

        # 对每个路由装饰器，找下面的def函数，然后分析函数体中的返回
        for deco_idx in route_decorator_lines:
            # 找下一个def行
            func_start = None
            for j in range(deco_idx + 1, min(deco_idx + 10, len(lines))):
                if lines[j].strip().startswith("def "):
                    func_start = j
                    break

            if func_start is None:
                continue

            # 找函数结束位置（通过缩进判断）
            func_line = lines[func_start]
            indent = len(func_line) - len(func_line.lstrip())
            func_body_start = func_start + 1
            func_body_end = len(lines) - 1

            for j in range(func_body_start, len(lines)):
                line = lines[j]
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                cur_indent = len(line) - len(line.lstrip())
                if cur_indent <= indent and j > func_start:
                    func_body_end = j - 1
                    break

            # 分析函数体中的返回语句
            body_lines = lines[func_body_start:func_body_end + 1]
            body_text = "\n".join(body_lines)

            info = {
                "file": filepath,
                "line": deco_idx + 1,
                "wrappers": set(),  # 使用的响应包装函数名
                "has_jsonify": False,
                "has_json_response": False,
                "dict_fields": set(),  # 直接return dict的字段名
                "has_raw_return": False,  # 是否有直接返回（非包装函数）
            }

            for bline in body_lines:
                bstripped = bline.strip()
                if not bstripped or bstripped.startswith("#"):
                    continue

                # 检测包装函数调用: return xxx( / return await xxx(
                m = re.search(r'return\s+(?:await\s+)?(\w+)\s*\(', bstripped)
                if m:
                    func_name = m.group(1)
                    # 判断是否为常见的响应包装函数名
                    if func_name.lower() in _RESPONSE_WRAPPER_NAMES:
                        info["wrappers"].add(func_name)
                    elif func_name in ("jsonify", "JSONResponse"):
                        info["has_jsonify"] = True
                    elif func_name in ("dict",):
                        pass  # 下面单独处理
                    else:
                        # 不是已知包装，也不是jsonify，当作原始返回
                        info["has_raw_return"] = True

                # 检测 jsonify 调用，并从中提取字段
                if re.search(r'\bjsonify\s*\(', bstripped):
                    info["has_jsonify"] = True
                    # 处理单行jsonify({...})的情况
                    jsonify_match = re.search(r'\bjsonify\s*\((.*?)\)\s*$', bstripped)
                    if jsonify_match:
                        jsonify_arg = jsonify_match.group(1)
                        dict_keys = re.findall(r'[\'"](\w+)[\'"]\s*:', jsonify_arg)
                        if dict_keys:
                            info["dict_fields"].update(dict_keys)
                    # 跨行的情况在下面的dict字段提取中处理

                # 检测 JSONResponse 并提取字段
                if re.search(r'\bJSONResponse\s*\(', bstripped):
                    info["has_json_response"] = True
                    json_resp_match = re.search(r'\bJSONResponse\s*\((.*?)\)\s*$', bstripped)
                    if json_resp_match:
                        json_arg = json_resp_match.group(1)
                        dict_keys = re.findall(r'[\'"](\w+)[\'"]\s*:', json_arg)
                        if dict_keys:
                            info["dict_fields"].update(dict_keys)

                # 检测 return { 形式的dict返回（包括jsonify({的跨行情况）
                if re.search(r'(return|jsonify\(|JSONResponse\().*\{', bstripped):
                    if 'jsonify' in bstripped or 'JSONResponse' in bstripped:
                        info["has_raw_return"] = False  # 是包装函数调用
                    else:
                        info["has_raw_return"] = True
                    # 尝试提取字段名
                    # 先尝试从当前行提取
                    dict_match = re.search(r'\{([^}]*)\}', bstripped)
                    if dict_match:
                        dict_content = dict_match.group(1)
                        keys = re.findall(r'[\'"](\w+)[\'"]\s*:', dict_content)
                        info["dict_fields"].update(keys)
                    else:
                        # 跨行dict：从当前行的{开始，找下一个}所在行
                        # 简单处理：在后续行中收集key
                        brace_count = bstripped.count('{') - bstripped.count('}')
                        if brace_count > 0:
                            # 提取当前行的key
                            keys_on_line = re.findall(r'[\'"](\w+)[\'"]\s*:', bstripped)
                            info["dict_fields"].update(keys_on_line)
                            # 继续找后面的行
                            body_idx = body_lines.index(bline) if bline in body_lines else 0
                            for next_line in body_lines[body_idx + 1:body_idx + 10]:
                                next_stripped = next_line.strip()
                                if not next_stripped or next_stripped.startswith("#"):
                                    continue
                                brace_count += next_stripped.count('{') - next_stripped.count('}')
                                keys_on_line = re.findall(r'[\'"](\w+)[\'"]\s*:', next_stripped)
                                info["dict_fields"].update(keys_on_line)
                                if brace_count <= 0:
                                    break

            # 只有能确认是路由函数的才记录
            if (info["wrappers"] or info["has_jsonify"] or
                    info["has_json_response"] or info["has_raw_return"] or
                    info["dict_fields"]):
                route_returns.append(info)

    if not route_returns:
        return issues

    total_routes = len(route_returns)

    # ---------- 检测1: 统一响应包装函数的使用情况 ----------
    # 统计使用各种包装函数的路由数量
    wrapper_usage = defaultdict(int)
    raw_return_routes = []
    for rr in route_returns:
        if rr["wrappers"]:
            for w in rr["wrappers"]:
                wrapper_usage[w] += 1
        else:
            raw_return_routes.append(rr)

    # 如果存在一个主流包装函数（被超过50%的路由使用），但还有部分路由没用
    if wrapper_usage:
        dominant_wrapper = max(wrapper_usage, key=wrapper_usage.get)
        dominant_count = wrapper_usage[dominant_wrapper]
        dominant_ratio = dominant_count / total_routes

        if dominant_ratio >= 0.5 and raw_return_routes:
            # 有统一的响应包装，但部分接口没使用
            for rr in raw_return_routes:
                issues.append({
                    "check_id": "ARCH-API-CONSISTENCY",
                    "name": "API未使用统一响应包装",
                    "severity": "low",
                    "file": rr["file"],
                    "line": rr["line"],
                    "message": (
                        f"项目中 {dominant_count}/{total_routes} 个接口"
                        f"使用统一响应函数 `{dominant_wrapper}()`，"
                        f"但该接口直接返回原始数据（dict/jsonify），"
                        f"返回结构可能与其他接口不一致"
                    ),
                    "suggestion": (
                        f"使用统一响应包装函数 `{dominant_wrapper}()` 返回数据，"
                        f"确保所有接口返回结构一致（如 code/data/msg 格式）"
                    ),
                })

    # ---------- 检测2: 字段命名风格不一致（驼峰 vs 下划线） ----------
    # 收集所有dict返回的字段
    all_snake_case = set()
    all_camel_case = set()

    for rr in route_returns:
        for field in rr["dict_fields"]:
            if "_" in field and field == field.lower():
                all_snake_case.add(field)
            elif re.search(r'[a-z][A-Z]', field):
                all_camel_case.add(field)

    # 如果同时存在两种命名风格
    if all_snake_case and all_camel_case:
        # 找第一个有混合命名的文件作为报告点
        report_file = ""
        report_line = 1
        for rr in route_returns:
            has_snake = any("_" in f and f == f.lower() for f in rr["dict_fields"])
            has_camel = any(re.search(r'[a-z][A-Z]', f) for f in rr["dict_fields"])
            if has_snake or has_camel:
                report_file = rr["file"]
                report_line = rr["line"]
                break

        if report_file:
            issues.append({
                "check_id": "ARCH-API-CONSISTENCY",
                "name": "API返回字段命名风格不一致",
                "severity": "low",
                "file": report_file,
                "line": report_line,
                "message": (
                    f"检测到接口返回字段同时使用驼峰命名和下划线命名两种风格。"
                    f"驼峰字段示例: {', '.join(sorted(all_camel_case)[:3])}；"
                    f"下划线段字段示例: {', '.join(sorted(all_snake_case)[:3])}。"
                    f"命名风格不统一会增加前后端联调成本和出错概率"
                ),
                "suggestion": (
                    "统一API返回字段的命名风格，建议全项目使用同一种风格"
                    "（推荐下划线 snake_case 与 Python 代码风格一致，"
                    "或全部使用驼峰 camelCase 与前端风格一致）"
                ),
            })

    return issues


# ============================================================
# ARCH-FLASK-ROUTE-CONFLICT: Flask路由冲突检测
# ============================================================


def _check_flask_route_conflict(code_files: Dict[str, str]) -> List[Dict]:
    """ARCH-FLASK-ROUTE-CONFLICT Flask蓝图路由冲突检测

    检测逻辑：
    1. 扫描Flask蓝图注册代码：app.register_blueprint(bp, url_prefix='/xxx')
    2. 扫描蓝图内部的路由定义：@bp.route('/yyy')
    3. 检查蓝图内的路由路径是否以url_prefix开头
       （如果是，说明路径会重复，如prefix='/schedule' + route='/schedule/list'
       → 实际路径变成/schedule/schedule/list）

    告警级别：medium
    """
    issues = []

    # 步骤1: 收集所有蓝图注册信息
    # { blueprint_var_name: {url_prefix, file, line} }
    blueprint_registrations = {}

    for filepath, content in code_files.items():
        if not filepath.endswith(".py") or not content:
            continue

        lines = content.split("\n")
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            # 匹配: app.register_blueprint(bp_name, url_prefix='/xxx')
            # 或: app.register_blueprint(bp_name, url_prefix="/xxx")
            m = re.search(
                r'(?:[\w\.]+\.)?register_blueprint\s*\(\s*(\w+)\s*[,)]',
                stripped
            )
            if m:
                bp_name = m.group(1)
                # 提取 url_prefix
                prefix_match = re.search(
                    r'url_prefix\s*=\s*[\'"]([^\'"]+)[\'"]',
                    stripped
                )
                url_prefix = prefix_match.group(1) if prefix_match else ""

                if url_prefix:  # 只有指定了url_prefix的才检测
                    # 规范化：确保不以/结尾
                    url_prefix = url_prefix.rstrip("/")
                    blueprint_registrations[bp_name] = {
                        "url_prefix": url_prefix,
                        "file": filepath,
                        "line": idx + 1,
                    }

    # 步骤2: 扫描每个蓝图内部的路由定义
    # 先找蓝图定义的文件
    if blueprint_registrations:
        for bp_name, reg_info in blueprint_registrations.items():
            url_prefix = reg_info["url_prefix"]
            prefix_with_slash = url_prefix + "/"  # 如 /schedule/

            # 在所有文件中找该蓝图的路由定义
            for filepath, content in code_files.items():
                if not filepath.endswith(".py") or not content:
                    continue

                lines = content.split("\n")
                for idx, line in enumerate(lines):
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#"):
                        continue

                    # 匹配: @bp_name.route('/xxx')
                    # 蓝图变量名可能和注册时的不同（导入时可能重命名），
                    # 所以我们也匹配通用模式 + 检查文件中是否有该蓝图变量
                    route_match = re.match(
                        r'@(\w+)\.route\s*\(\s*[\'"]([^\'"]+)[\'"]',
                        stripped
                    )
                    if route_match:
                        var_name = route_match.group(1)
                        route_path = route_match.group(2)

                        # 判断这个变量是否是我们关注的蓝图
                        # 方式：变量名直接匹配，或文件中有 Blueprint( 赋值
                        is_target_bp = False
                        if var_name == bp_name:
                            is_target_bp = True
                        else:
                            # 检查文件中是否有该变量的蓝图定义/导入
                            # 简单模式：xxx = Blueprint( 或 from xxx import bp as yyy
                            bp_def_pattern = re.compile(
                                rf'{re.escape(var_name)}\s*=\s*Blueprint\s*\(',
                                re.MULTILINE
                            )
                            if bp_def_pattern.search(content):
                                # 这个变量是一个蓝图，但可能不是注册的那个
                                # 只有变量名匹配才算（简单版本）
                                pass

                        if is_target_bp and route_path.startswith(prefix_with_slash):
                            # 路由路径以 url_prefix/ 开头，会导致路径重复
                            full_path = url_prefix + route_path
                            issues.append({
                                "check_id": "ARCH-FLASK-ROUTE-CONFLICT",
                                "name": "Flask蓝图路由路径重复",
                                "severity": "medium",
                                "file": filepath,
                                "line": idx + 1,
                                "message": (
                                    f"蓝图 `{bp_name}` 的 url_prefix 为 `{url_prefix}`，"
                                    f"但内部路由路径 `{route_path}` 以 `{prefix_with_slash}` 开头，"
                                    f"拼接后实际路径为 `{full_path}`，"
                                    f"前缀重复会导致接口404或路径不符合预期"
                                ),
                                "suggestion": (
                                    f"蓝图内部路由应写相对路径，去掉重复的前缀。"
                                    f"将 `{route_path}` 改为 "
                                    f"`{route_path[len(url_prefix):]}` 即可"
                                ),
                            })

    # 步骤3: 检测同一文件中直接注册的重复路径（@app.route重复注册）
    # 收集所有 app.route 的路径
    app_routes = defaultdict(list)  # path -> list of (file, line)
    for filepath, content in code_files.items():
        if not filepath.endswith(".py") or not content:
            continue

        lines = content.split("\n")
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            # @app.route('/path')  - 直接app上的路由
            m = re.match(r'@app\.route\s*\(\s*[\'"]([^\'"]+)[\'"]', stripped)
            if m:
                path = m.group(1)
                norm_path = path.rstrip("/") if path != "/" else "/"
                app_routes[norm_path].append((filepath, idx + 1))

    for path, occurrences in app_routes.items():
        if len(occurrences) > 1:
            first_file, first_line = occurrences[0]
            other_info = "; ".join(
                f"{f}:{l}" for f, l in occurrences[1:]
            )
            issues.append({
                "check_id": "ARCH-FLASK-ROUTE-CONFLICT",
                "name": "Flask路由重复注册",
                "severity": "medium",
                "file": first_file,
                "line": first_line,
                "message": (
                    f"路径 `{path}` 被重复注册了 {len(occurrences)} 次 "
                    f"（其他位置: {other_info}），后注册的会覆盖先注册的，"
                    f"可能导致部分接口无法访问"
                ),
                "suggestion": (
                    "检查重复注册的路由，合并或删除冗余定义，"
                    "确保每个路径只注册一次"
                ),
            })

    return issues


# ============================================================
# ARCH-WS-TIMEOUT: WebSocket连接超时清理机制检测
# ============================================================


def _check_ws_timeout_cleanup(code_files: Dict[str, str]) -> List[Dict]:
    """ARCH-WS-TIMEOUT WebSocket连接超时清理机制检测

    检测逻辑：
    扫描WebSocket相关代码，检测：
    1. 是否有心跳检测机制（ping/pong、heartbeat）
    2. 是否有超时断开逻辑（timeout、idle_timeout等）
    3. 连接断开时是否有清理逻辑（资源释放、状态更新、扣费等）
    4. 是否有异常断开的处理（try-finally、on_close回调）

    告警级别：
    - 完全没有心跳/超时/清理 → high
    - 有心跳但没有超时断开 → medium
    - 有超时但断开时没有资源清理 → low
    - 都有 → 不报告
    """
    issues = []

    # WebSocket相关关键词（用于判断项目是否有WebSocket代码）
    ws_import_keywords = (
        "websocket", "WebSocket", "flask-socketio", "flask_socketio",
        "socketio", "SocketIO", "fastapi.WebSocket",
        "websockets", "aiowebsocket", "django-channels",
    )

    ws_code_keywords = (
        "websocket", "WebSocket", "ws.connect", "socketio",
        "on_connect", "on_disconnect", "on_close",
        "websocket.accept", "websocket.receive", "websocket.send",
    )

    # 先判断项目中是否有WebSocket代码
    has_ws_project = False
    ws_files = {}  # filepath -> content

    for filepath, content in code_files.items():
        if not filepath.endswith(".py") or not content:
            continue

        content_lower = content.lower()
        is_ws_file = False

        # 检查import
        for kw in ws_import_keywords:
            kw_lower = kw.lower()
            if re.search(rf'(?:from|import)\s+[\w\.]*{kw_lower}[\w\.]*', content_lower):
                is_ws_file = True
                break

        # 检查WebSocket关键函数调用
        if not is_ws_file:
            for kw in ws_code_keywords:
                kw_lower = kw.lower()
                if kw_lower in content_lower:
                    # 再确认一下是websocket相关的代码而不是巧合
                    if re.search(r'\b(websocket|socketio|on_connect|on_disconnect)\b', content_lower):
                        is_ws_file = True
                        break

        if is_ws_file:
            ws_files[filepath] = content
            has_ws_project = True

    if not has_ws_project:
        # 项目中没有WebSocket代码，跳过
        return issues

    # 检测各种机制
    has_heartbeat = False
    has_timeout = False
    has_cleanup = False
    has_try_finally = False
    has_on_close = False

    # 心跳/保活关键词
    heartbeat_signals = (
        "ping", "pong", "heartbeat", "心跳", "keep_alive", "keepalive",
        "ping_interval", "ping_timeout", "heart_beat",
    )

    # 超时断开关键词
    timeout_signals = (
        "timeout", "idle_timeout", "idleTimeout", "connect_timeout",
        "connection_timeout", "max_idle", "disconnect_timeout",
        "超时", "空闲超时", "断开",
    )

    # 清理逻辑关键词
    cleanup_signals = (
        "cleanup", "clean_up", "release", "dispose", "close_connection",
        "remove_connection", "del connection", "pop connection",
        "状态更新", "扣费", "停止计时", "释放资源",
        "connection.close", "ws.close",
    )

    for filepath, content in ws_files.items():
        lines = content.split("\n")
        # 生成去掉注释的代码行列表和全文
        code_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            # 去掉行尾注释
            code_part = re.sub(r'#.*$', '', line)
            if code_part.strip():
                code_lines.append(code_part)
        code_content_lower = "\n".join(code_lines).lower()

        # 检测心跳 - 在非注释代码中查找
        for sig in heartbeat_signals:
            if sig.lower() in code_content_lower:
                has_heartbeat = True
                break

        # 检测超时 - 需要有实际的超时参数设置，不是注释
        for sig in timeout_signals:
            if sig.lower() in code_content_lower:
                # 进一步验证：不是出现在字符串字面量中（简单判断）
                # 比如 timeout= 或 TIMEOUT = 这样的赋值模式更可信
                pattern = re.compile(
                    rf'(?:{re.escape(sig.lower())}\s*=|'
                    rf'{re.escape(sig.lower())}\s*:)',
                    re.IGNORECASE
                )
                if pattern.search(code_content_lower):
                    has_timeout = True
                    break
                # 也接受 wait_for / settimeout 等函数调用
                if 'wait_for' in code_content_lower or 'settimeout' in code_content_lower:
                    has_timeout = True
                    break

        # 检测 on_close / disconnect 处理
        if re.search(r'on_close|on_disconnect|disconnect_handler|handle_disconnect', code_content_lower):
            has_on_close = True

        # 检测 try-finally 模式
        # 找 websocket 处理函数附近的 try-finally
        for idx, line in enumerate(lines):
            stripped = line.strip()
            # 匹配多种WebSocket入口模式
            if re.search(
                r'(websocket\.accept|websocket\.recv|ws\.connect|'
                r'socketio\.on\s*\(\s*[\'"]connect|async def\s+\w*(connect|websocket|ws)\w*)',
                stripped, re.I
            ):
                # 检查附近50行内的try和finally
                window_start = max(0, idx - 5)
                window_end = min(len(lines), idx + 60)
                window_text = "\n".join(lines[window_start:window_end]).lower()
                if "try:" in window_text and "finally:" in window_text:
                    has_try_finally = True
                    # 检查finally块中是否有清理操作
                    finally_idx = None
                    for j in range(window_start, window_end):
                        if lines[j].strip().lower().startswith("finally:"):
                            finally_idx = j
                            break
                    if finally_idx:
                        # 检查finally块内的清理操作
                        finally_indent = len(lines[finally_idx]) - len(lines[finally_idx].lstrip())
                        for j in range(finally_idx + 1, min(finally_idx + 20, len(lines))):
                            fline = lines[j]
                            fstripped = fline.strip()
                            if not fstripped or fstripped.startswith("#"):
                                continue
                            cur_indent = len(fline) - len(fline.lstrip())
                            if cur_indent <= finally_indent:
                                break
                            # 检查清理信号
                            for sig in cleanup_signals:
                                if sig.lower() in fstripped.lower():
                                    has_cleanup = True
                                    break
                            # 也检查常见的连接/资源清理模式
                            # 注意：单纯的 task.cancel() 不算，必须是连接/状态/资源级别的清理
                            if not has_cleanup:
                                cleanup_patterns = (
                                    r'del\s+\w*(?:connection|conn|ws|socket|user|client)',
                                    r'\.remove\s*\(\s*.*(?:connection|conn|ws|socket|user|client)',
                                    r'\.discard\s*\(\s*.*(?:connection|conn|ws|socket|user|client)',
                                    r'\.pop\s*\(\s*.*(?:connection|conn|ws|socket|user|client)',
                                    r'(?:connection|conn|ws|socket)\.close\s*\(',
                                    r'update.*(?:status|state).*(?:offline|close|disconnect)',
                                    r'stop.*(?:charg|fee|billing|计时|扣费)',
                                    r'释放.*(?:资源|连接|资源)',
                                    r'(?:connections|clients|sessions)\.',
                                )
                                for pat in cleanup_patterns:
                                    if re.search(pat, fstripped, re.I):
                                        has_cleanup = True
                                        break
                            if has_cleanup:
                                break
                break

        # 检测清理逻辑（需要在断开处理附近）
        # 找 on_close / on_disconnect 函数定义
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if re.search(r'(def\s+\w*(close|disconnect|cleanup)\w*|on_close|on_disconnect)', stripped, re.I):
                # 检查该函数中是否有清理逻辑
                # 简单检查：函数体内是否有清理关键词
                func_start = idx
                func_line = lines[idx] if stripped.startswith("def ") else None
                if func_line:
                    indent = len(func_line) - len(func_line.lstrip())
                    for j in range(idx + 1, min(idx + 30, len(lines))):
                        cline = lines[j]
                        cstripped = cline.strip()
                        if not cstripped or cstripped.startswith("#"):
                            continue
                        cur_indent = len(cline) - len(cline.lstrip())
                        if cur_indent <= indent:
                            break
                        for sig in cleanup_signals:
                            if sig.lower() in cstripped.lower():
                                has_cleanup = True
                                break
                        if has_cleanup:
                            break
                if has_cleanup:
                    break

        # 另外：如果在 disconnect 事件处理器中有内容，也算有清理
        if not has_cleanup:
            if re.search(r'(on\s*\(\s*[\'"]disconnect[\'"]|on_disconnect)', code_content_lower):
                # 简单认为如果有on_disconnect处理，就算有清理机制
                has_cleanup = True

    # 找一个WebSocket相关文件作为报告点
    report_file = sorted(ws_files.keys())[0] if ws_files else ""
    # 找第一行WebSocket相关代码作为行号
    report_line = 1
    if report_file:
        content = ws_files[report_file]
        for idx, line in enumerate(content.split("\n"), 1):
            if re.search(r'(websocket|WebSocket|socketio|on_connect)', line, re.I):
                report_line = idx
                break

    # 根据缺失程度决定告警级别
    missing_items = []
    if not has_heartbeat:
        missing_items.append("心跳检测机制（ping/pong/heartbeat）")
    if not has_timeout:
        missing_items.append("超时断开逻辑（timeout/idle_timeout）")
    if not has_cleanup and not has_on_close and not has_try_finally:
        missing_items.append("连接断开清理逻辑（资源释放/状态更新）")

    if not missing_items:
        # 所有机制都有，不报
        return issues

    # 判断严重程度
    missing_count = len(missing_items)
    if missing_count >= 3:
        severity = "high"
        desc = "完全缺失"
    elif missing_count == 2:
        severity = "medium"
        desc = "部分缺失"
    else:
        severity = "low"
        desc = "有所欠缺"

    issues.append({
        "check_id": "ARCH-WS-TIMEOUT",
        "name": "WebSocket连接超时清理机制检测",
        "severity": severity,
        "file": report_file,
        "line": report_line,
        "message": (
            f"检测到项目中存在WebSocket相关代码，但{desc}以下保障机制："
            f"{'; '.join(missing_items)}。"
            f"僵死连接不清理会导致资源泄漏、状态不一致、"
            f"用户异常断网后通话连接一直挂着导致计费错误等问题"
        ),
        "suggestion": (
            "为WebSocket连接添加完整的可靠性保障："
            "1）实现心跳检测（ping/pong机制）；"
            "2）设置空闲超时自动断开（如30s无消息则断开）；"
            "3）在on_close/on_disconnect或try-finally中"
            "执行资源清理（释放连接、更新状态、停止扣费等）"
        ),
    })

    return issues

# ============================================================
# ARCH-API-DOC: 接口契约文档完整性检测
# ============================================================


def _check_api_doc_coverage(code_files: Dict[str, str]) -> List[Dict]:
    """ARCH-API-DOC 接口契约文档完整性检测

    检测逻辑（简化版）：
    1. 扫描所有 Flask/FastAPI 路由函数
    2. 检查路由函数是否有 docstring（文档字符串）
    3. 检查 docstring 长度是否 > 30 字符（太短的不算有效文档）
    4. 统计覆盖率：有文档的路由 / 总路由数
    5. 如果覆盖率低于阈值（60%），报告"接口文档覆盖率不足"

    不报告的情况：
    - 路由函数有 docstring 且长度 > 30 字符
    - 内部路由（healthcheck、static）排除
    - 项目路由太少（< 5个）不报告

    告警级别：low（架构治理类）
    """
    import ast as _ast
    import os as _os

    issues = []

    # 收集所有路由函数信息
    # (filepath, line, func_name, route_path, has_doc, doc_len)
    all_routes = []

    # 内部/健康检查路由关键词（排除用）
    internal_route_keywords = (
        "health", "healthcheck", "health_check", "healthz", "ping",
        "static", "favicon", "metrics", "monitor", "alive", "ready",
    )

    def _is_internal_route(route_path: str, func_name: str) -> bool:
        """判断是否为内部路由（应排除统计）"""
        path_lower = route_path.lower()
        name_lower = func_name.lower()
        for kw in internal_route_keywords:
            if kw in path_lower or kw in name_lower:
                return True
        return False

    def _extract_docstring(node) -> str:
        """从函数/类节点提取 docstring"""
        if (node.body and isinstance(node.body[0], _ast.Expr) and
                isinstance(node.body[0].value, _ast.Constant) and
                isinstance(node.body[0].value.value, str)):
            return node.body[0].value.value
        return ""

    def _is_route_decorator(decorator) -> tuple:
        """判断装饰器是否为路由装饰器

        返回: (is_route, route_path, method)
        """
        is_route = False
        route_path = ""
        method = ""

        # @app.route("/xxx") / @router.get("/xxx") 等 Call 形式
        if isinstance(decorator, _ast.Call):
            if isinstance(decorator.func, _ast.Attribute):
                attr = decorator.func.attr.lower()
                if attr in ("route", "get", "post", "put", "delete", "patch",
                            "options", "head"):
                    is_route = True
                    method = attr
                    # 提取第一个字符串参数作为路径
                    if decorator.args:
                        first_arg = decorator.args[0]
                        if isinstance(first_arg, _ast.Constant) and isinstance(first_arg.value, str):
                            route_path = first_arg.value

        # @app.route （不带括号，较少见）
        elif isinstance(decorator, _ast.Attribute):
            attr = decorator.attr.lower()
            if attr in ("route", "get", "post", "put", "delete", "patch"):
                is_route = True
                method = attr

        return is_route, route_path, method

    for filepath, content in code_files.items():
        if not filepath.endswith(".py") or not content:
            continue

        # 跳过测试文件
        basename = _os.path.basename(filepath)
        dir_parts = filepath.replace("\\", "/").split("/")
        is_test_file = (
            basename.startswith("test_")
            or basename.endswith("_test.py")
            or "tests" in dir_parts
            or "test" in dir_parts
        )
        if is_test_file:
            continue

        # 跳过配置/脚本文件
        if basename in ("config.py", "settings.py", "manage.py", "conftest.py",
                        "__init__.py", "setup.py"):
            continue

        try:
            tree = _ast.parse(content, filename=filepath)
        except SyntaxError:
            continue

        # 遍历函数定义，检查装饰器
        for node in _ast.walk(tree):
            if not isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                continue

            # 检查装饰器中是否有路由装饰器
            has_route_decorator = False
            route_path = ""
            route_method = ""

            for decorator in node.decorator_list:
                is_route, path, method = _is_route_decorator(decorator)
                if is_route:
                    has_route_decorator = True
                    route_path = path
                    route_method = method
                    break

            if not has_route_decorator:
                continue

            # 排除内部路由
            if _is_internal_route(route_path, node.name):
                continue

            # 获取 docstring
            docstring = _extract_docstring(node)
            doc_len = len(docstring.strip()) if docstring else 0

            all_routes.append({
                "file": filepath,
                "line": node.lineno,
                "func_name": node.name,
                "route_path": route_path,
                "method": route_method,
                "has_doc": doc_len > 30,
                "doc_len": doc_len,
            })

    # 路由太少的项目不报告（避免误报）
    if len(all_routes) < 5:
        return issues

    # 计算覆盖率
    total_routes = len(all_routes)
    documented_routes = sum(1 for r in all_routes if r["has_doc"])
    coverage = documented_routes / total_routes if total_routes > 0 else 1.0

    # 覆盖率 >= 60% 不报
    if coverage >= 0.6:
        return issues

    # 找出缺少文档的路由
    undocumented = [r for r in all_routes if not r["has_doc"]]

    # 取前 10 个作为示例
    top_missing = undocumented[:10]
    missing_detail = "; ".join(
        f"{r['func_name']}({r['method'] or 'route'} {r['route_path']})"
        for r in top_missing
    )
    if len(undocumented) > 10:
        missing_detail += f" 等{len(undocumented)}个"

    # 找第一个缺少文档的路由作为报告点
    first_missing = undocumented[0] if undocumented else all_routes[0]

    issues.append({
        "check_id": "ARCH-API-DOC",
        "name": "接口文档覆盖率不足",
        "severity": "low",
        "file": first_missing["file"],
        "line": first_missing["line"],
        "message": (
            f"接口文档覆盖率为 {documented_routes}/{total_routes} "
            f"（{coverage*100:.0f}%），低于60%阈值。"
            f"缺少文档的路由: {missing_detail}。"
            f"缺少统一的接口契约文档会增加前后端联调成本，"
            f"也不利于接口版本管理和第三方对接"
        ),
        "suggestion": (
            "为所有接口路由函数添加规范的 docstring 文档，"
            "包含：接口功能说明、请求参数说明（类型、是否必填）、"
            "返回值结构说明、异常/错误码说明。"
            "推荐使用 Swagger/OpenAPI 或 Pydantic + FastAPI 自动生成接口文档"
        ),
    })

    return issues


# ===========================================================================
# ============ 数据一致性检测 (Data Consistency Checks) ====================
# ===========================================================================
# 规则前缀: ARCH-DATA-
# 设计原则: 宁漏勿误，检测逻辑保守，避免误报
# ===========================================================================


# --- 数据一致性: 关键词与模式常量 ---

# 数据库写操作关键字
_SQL_WRITE_KEYWORDS = ("INSERT", "UPDATE", "DELETE", "INSERT INTO", "UPDATE ", "DELETE FROM")

# 事务相关关键字（Python/JS）
_TRANSACTION_KEYWORDS = (
    "BEGIN", "COMMIT", "ROLLBACK",
    "transaction", "atomic", "db.session.commit",
    "with transaction", "with atomic",
    "start_transaction", "beginTransaction",
)

# 关键业务接口关键词（幂等检测用）
_IDEMPOTENT_API_KEYWORDS = (
    "pay", "payment", "order", "transfer", "refund",
    "withdraw", "create_order", "place_order",
    "settle", "charge", "deduct",
)

# 幂等字段关键词（仅代码标识符，不含中文词避免注释误匹配）
_IDEMPOTENCY_FIELD_KEYWORDS = (
    "idempotency_key", "idempotent_key", "request_id",
    "unique_id", "biz_no", "biz_id", "out_trade_no",
    "idempotency_token", "idem_key",
)

# 软删除字段名
_SOFT_DELETE_FIELDS = ("is_deleted", "deleted_at", "soft_delete", "delete_time", "deleted")

# 应当唯一的字段名
_UNIQUE_FIELD_CANDIDATES = (
    "email", "username", "order_no", "order_id",
    "user_name", "mobile", "phone", "account",
    "transaction_id", "trade_no", "biz_no",
    "serial_no", "uuid",
)

# 应当非空的字段名
_NOT_NULL_FIELD_CANDIDATES = (
    "id", "created_at", "create_time", "updated_at",
    "update_time", "status", "is_deleted",
)

# 外键字段名模式
_FOREIGN_KEY_FIELD_PATTERNS = (
    r"\w+_id\b",  # xxx_id 形式
)

# 核心业务表（级联删除风险评估用）
_CORE_BUSINESS_TABLES = (
    "user", "order", "account", "payment", "transaction",
    "product", "goods", "member",
)

# 枚举变量名模式
_ENUM_VAR_NAME_PATTERNS = (
    r"(?:STATUS|STATUS_TYPE|status_type|STATUS_LIST|status_list|"
    r"TYPE|type_list|TYPE_LIST|STATE|state_list|STATE_LIST|"
    r"STATUS_CHOICES|choices|CHOICES|ENUM|enum_list)",
)


def _extract_frontend_form_fields(content: str, filepath: str) -> set:
    """从前端文件中提取表单校验字段名（保守提取）"""
    fields = set()

    # 匹配 v-model / v-bind / name 属性中的字段名
    vmodel_pattern = re.compile(r"v-model[=:]+['\"]?(\w+)['\"]?", re.IGNORECASE)
    for m in vmodel_pattern.finditer(content):
        field = m.group(1).strip()
        if field and len(field) < 50 and not field.startswith("$"):
            fields.add(field.lower())

    # 匹配 form validation 相关的字段
    # 如: rules: { name: [{ required: true }], email: [...] }
    rules_pattern = re.compile(r"(\w+)\s*:\s*\[.*?(?:required|max|min|pattern)", re.IGNORECASE)
    for m in rules_pattern.finditer(content):
        field = m.group(1).strip()
        if field and len(field) < 50 and field not in ("rules", "form", "model"):
            fields.add(field.lower())

    # 匹配 <input name="xxx" required> / maxlength 等
    input_pattern = re.compile(
        r'<(?:input|select|textarea)[^>]*\bname\s*=\s*["\'](\w+)["\'][^>]*(?:required|maxlength|minlength)',
        re.IGNORECASE
    )
    for m in input_pattern.finditer(content):
        field = m.group(1).strip()
        if field and len(field) < 50:
            fields.add(field.lower())

    return fields


def _extract_backend_validation_fields(content: str, filepath: str) -> set:
    """从后端文件中提取接口校验字段名（保守提取）"""
    fields = set()

    if filepath.endswith(".py"):
        # Pydantic / Marshmallow 字段定义
        # 匹配: field_name: type = Field(...) 或 field_name = Column(...)
        field_pattern = re.compile(
            r"(\w+)\s*:\s*\w+.*?=\s*(?:Field|Column|Schema\.fields?)\s*\(",
            re.IGNORECASE
        )
        for m in field_pattern.finditer(content):
            field = m.group(1).strip()
            if field and len(field) < 50 and not field.startswith("_"):
                fields.add(field.lower())

        # WTForms: StringField("xxx", [validators.DataRequired()])
        wtf_pattern = re.compile(
            r"(\w+)\s*=\s*(?:StringField|IntegerField|BooleanField|DateField|FormField)\s*\(",
            re.IGNORECASE
        )
        for m in wtf_pattern.finditer(content):
            field = m.group(1).strip()
            if field and len(field) < 50:
                fields.add(field.lower())

    elif filepath.endswith(".java"):
        # Java: @NotBlank / @NotNull 等注解
        java_pattern = re.compile(
            r'@(?:NotNull|NotBlank|NotEmpty|Size|Min|Max|Pattern).*?\n\s*(?:private\s+)?\w+\s+(\w+)\s*;',
            re.IGNORECASE | re.DOTALL
        )
        for m in java_pattern.finditer(content):
            field = m.group(1).strip()
            if field and len(field) < 50:
                fields.add(field.lower())

    return fields


def _extract_function_ranges(content: str, is_python: bool) -> List[tuple]:
    """辅助：提取函数/方法的名称与行号范围

    返回: [(func_name, start_line_idx, end_line_idx, indent), ...]
    """
    lines = content.split("\n")
    funcs = []

    if is_python:
        # Python: 通过缩进判断函数范围
        current_func = None
        current_start = 0
        current_indent = 0

        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            indent = len(line) - len(line.lstrip())

            # 检测函数定义
            func_match = re.match(r"(?:async\s+)?def\s+(\w+)\s*\(", stripped)
            if func_match:
                # 保存上一个函数
                if current_func is not None:
                    funcs.append((current_func, current_start, i, current_indent))
                current_func = func_match.group(1)
                current_start = i
                current_indent = indent
                continue

            # 如果当前在函数内，且缩进级别回到或小于函数定义缩进，说明函数结束
            if current_func is not None and indent <= current_indent and stripped:
                funcs.append((current_func, current_start, i, current_indent))
                current_func = None

        # 文件结束时处理最后一个函数
        if current_func is not None:
            funcs.append((current_func, current_start, len(lines), current_indent))

    else:
        # JS/TS: 通过大括号判断函数范围
        func_pattern = re.compile(
            r"(?:(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(|"
            r"(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>\s*\{|"
            r"(\w+)\s*:\s*(?:async\s+)?function\s*\(|"
            r"(?:async\s+)?(\w+)\s*\([^)]*\)\s*\{)"
        )

        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith("//"):
                continue

            m = func_pattern.match(stripped)
            if m:
                func_name = (
                    m.group(1) or m.group(2) or m.group(3) or m.group(4)
                )
                if not func_name:
                    continue

                # 统计大括号找到函数结束
                depth = 0
                end_line = i
                found_open = False
                for j in range(i, min(i + 100, len(lines))):
                    for ch in lines[j]:
                        if ch == "{":
                            depth += 1
                            found_open = True
                        elif ch == "}":
                            depth -= 1
                    if found_open and depth == 0:
                        end_line = j
                        break
                    end_line = j

                if found_open:
                    funcs.append((func_name, i, end_line, 0))

    return funcs
