"""架构规则共享工具模块
集中管理架构分层检测、文件收集、导入提取、纯净度检查等共享能力
供 arch_layering.py 和 arch_dependency.py 共用，避免重复实现与重复计算

性能优化点：
1. 统一使用 context._all_walk_cache / context.find_files，避免重复 os.walk
2. 模块级 imports 缓存（基于 context），多条规则共享
3. 预编译所有正则表达式
4. 统一的分层检测缓存，两个模块共享
5. 领域层接口检测缓存
"""

import re
import os
from typing import List, Dict, Any, Tuple

# ===== 常量 =====
_default_exclude_dirs = {
    '__pycache__', '.git', 'node_modules', '.venv', 'venv',
    'miniprogram_npm', '.pymysql', 'ec-canvas', '.mypy_cache',
    '.pytest_cache', '.ruff_cache', 'dist', 'build', '.eggs',
    'rules', 'skills', '.skills', 'backups', 'backup',
    '.tox', '.nox', '.coverage', 'site-packages',
    '.xinpect_cache', '.qa_history',
}

_ARCH_LAYER_KEYWORDS = {
    "presentation": {"controllers", "handlers", "api", "routes", "views",
                     "routers", "endpoints", "resources", "web", "http",
                     "interface", "adapter", "delivery", "presentation"},
    "application": {"services", "usecases", "use_cases", "service",
                    "application", "app", "command", "query", "cqrs"},
    "domain": {"domain", "models", "entities", "entity", "aggregate",
               "value_objects", "repository", "repositories", "domain_model",
               "core", "business", "biz"},
    "infrastructure": {"infrastructure", "infra", "dao", "repository_impl",
                       "persistence", "db", "database", "data_access",
                       "external", "third_party", "gateway", "providers"},
}

# 领域层禁止导入的技术依赖
_DOMAIN_FORBIDDEN_IMPORTS = {
    "database_orm": ["sqlalchemy", "pymysql", "psycopg", "sqlite3", "django.db", "mongoengine",
                     "pymongo", "redis", "elasticsearch", "typeorm", "prisma", "sequelize",
                     "knex", "objection", "mongoose", "drizzle",
                     "mysql2", "pg", "mongodb", "@prisma/client", "better-sqlite3", "sqlite"],
    "http_client": ["requests", "httpx", "aiohttp", "urllib", "urllib3", "http.client",
                    "axios", "fetch", "superagent", "got", "node-fetch"],
    "external_sdk": ["boto3", "aliyun", "tencentcloud", "qcloud", "coze", "openai", "anthropic",
                     "@aws-sdk", "@aliyun", "@tencentcloud", "lark", "feishu", "wechatpy",
                     "wx-sdk", "miniprogram-api-promise"],
    "web_framework": ["flask", "django", "fastapi", "tornado", "sanic", "starlette",
                      "express", "koa", "nest", "next", "nuxt", "vue", "react", "angular"],
    "ui_components": ["wxml", "wxss", "vant", "element-ui", "antd", "material-ui",
                      "tkinter", "pyqt", "pyside", "pywebview"],
    "file_io": ["shutil", "tempfile"],
}

# Python标准库（领域层可安全引用）
_PYTHON_STDLIB = {
    "abc", "typing", "dataclasses", "enum", "collections", "datetime", "time", "math",
    "re", "json", "uuid", "hashlib", "base64", "decimal", "fractions", "statistics",
    "itertools", "functools", "operator", "copy", "pprint", "warnings", "contextlib",
    "pathlib", "os", "sys", "io", "string", "struct", "logging",
    "email", "html", "xml", "csv", "configparser", "argparse", "unittest", "pytest",
    "asyncio", "concurrent", "threading", "multiprocessing", "queue", "subprocess",
    "socket", "ssl", "hmac", "secrets", "random", "bisect", "heapq",
}

# ===== 预编译正则 =====
# 领域层禁止的技术实现关键词
_DOMAIN_IMPURITY_PATTERNS = [
    (re.compile(r'\b(SELECT|INSERT|UPDATE|DELETE|CREATE TABLE|ALTER TABLE|DROP TABLE|JOIN|WHERE|FROM)\b.*?[;\n]', re.IGNORECASE), "SQL语句"),
    (re.compile(r'\bexecute\s*\(\s*["\']\s*(SELECT|INSERT|UPDATE|DELETE)', re.IGNORECASE), "SQL执行"),
    (re.compile(r'\b(session|db|connection|cursor)\.(query|execute|commit|rollback|close)\b', re.IGNORECASE), "数据库操作"),
    (re.compile(r'\b\.save\s*\(\s*\)', re.IGNORECASE), "数据库保存"),
    (re.compile(r'\.(get|post|put|delete|patch|request)\s*\(\s*["\']https?://', re.IGNORECASE), "HTTP调用"),
    (re.compile(r'\b(requests\.|httpx\.|axios\.)', re.IGNORECASE), "HTTP客户端调用"),
    (re.compile(r'\bwx\.request\b', re.IGNORECASE), "微信HTTP请求"),
    (re.compile(r'\bopen\s*\(\s*["\'].*?\.\w+["\']', re.IGNORECASE), "文件读写"),
    (re.compile(r'\bos\.(makedirs|remove|rename|listdir|walk)\b', re.IGNORECASE), "文件系统操作"),
    (re.compile(r'\b(boto3|openai|anthropic)\.(client|Client|resource|api)', re.IGNORECASE), "外部SDK调用"),
]

# 导入语句匹配（JS/TS）
_JS_IMPORT_RE = re.compile(r'^import\s+.*?\s+from\s+["\']([^"\']+)["\']')
_JS_REQUIRE_RE = re.compile(r'.*?\brequire\s*\(\s*["\']([^"\']+)["\']\s*\)')

# 导入语句匹配（Python 正则回退路径）
_PY_IMPORT_RE = re.compile(r'^import\s+([\w.]+)')
_PY_FROM_RE = re.compile(r'^from\s+([\w.]+)\s+import')

# 预编译分层关键词匹配模式（用于 import 中的分层检测）
_LAYER_KW_PATTERNS = {}
for _layer_name, _kws in _ARCH_LAYER_KEYWORDS.items():
    _LAYER_KW_PATTERNS[_layer_name] = [
        (kw.lower(), re.compile(r'(^|[\./])' + re.escape(kw.lower()) + r'([\./]|$)'))
        for kw in _kws
    ]

# 预编译相对导入分层关键词匹配（路径分隔符用 /）
_LAYER_KW_REL_PATTERNS = {}
for _layer_name, _kws in _ARCH_LAYER_KEYWORDS.items():
    _LAYER_KW_REL_PATTERNS[_layer_name] = [
        (kw.lower(), re.compile(r'(^|[/])' + re.escape(kw.lower()) + r'([/]|$)'))
        for kw in _kws
    ]

# 预编译禁止技术依赖匹配（一次性建表，O(1) 前缀/后缀查找）
# 思路：将 forbidden list 转为 set 用于精确匹配，另外用 dict 做前缀索引
_FORBIDDEN_EXACT = {}  # module_lower -> (category, forbidden)
_FORBIDDEN_PREFIXES = {}  # prefix -> (category, forbidden)  以 "." 或 "/" 结尾的前缀
for _cat, _flist in _DOMAIN_FORBIDDEN_IMPORTS.items():
    for _f in _flist:
        _fl = _f.lower()
        _FORBIDDEN_EXACT[_fl] = (_cat, _f)
        # 常见前缀形式
        _FORBIDDEN_PREFIXES[_fl + "."] = (_cat, _f)
        _FORBIDDEN_PREFIXES[_fl + "/"] = (_cat, _f)

# 接口/抽象类命名匹配
_INTERFACE_NAME_RE = re.compile(r'(Interface|Abstract|Base|Repository|Port|Gateway)$')
_IMPL_BASE_RE = re.compile(r'(Repository|Gateway|Port|Dao)$')
_TS_INTERFACE_RE = re.compile(r'\b(interface|abstract\s+class)\s+(\w+)')
_TS_IMPL_RE = re.compile(r'class\s+(\w+)\s+(?:implements|extends)\s+([\w<>,\s]+)')

# 配置模块名
_CONFIG_NAMES = {'config', 'settings', 'conf', 'cfg', 'constants', 'configs', 'setting'}

# JS/TS 文件扩展名
_JS_EXTS = (".js", ".ts", ".jsx", ".tsx")
_CODE_EXTS = [".py", ".js", ".ts", ".jsx", ".tsx"]
_JS_INDEX_EXTS = ["/index.ts", "/index.tsx", "/index.js", "/index.jsx"]
_JS_FILE_EXTS = [".ts", ".tsx", ".js", ".jsx"]


# ===== 缓存 key 辅助函数 =====
def _cache_key(context):
    """生成基于 context 的缓存 key"""
    return id(context)


# ===== 架构分层检测 =====
_arch_layers_cache = {}  # cache_key -> layers dict

# 文件路径集合缓存（用于 O(1) 判断文件是否存在，避免 os.path.isfile 磁盘IO）
_file_path_set_cache = {}  # cache_key -> set of normalized file paths

# 文件→所属层映射缓存（用于 O(1) 判断文件属于哪一层）
_file_layer_map_cache = {}  # cache_key -> {file_path_norm: layer_name}


def _get_file_path_set(context):
    """获取项目所有文件的规范化路径集合（基于 walk 缓存，O(1) 查找）"""
    ckey = _cache_key(context)
    if ckey in _file_path_set_cache:
        return _file_path_set_cache[ckey]
    
    context._ensure_walk_cache()
    fset = set()
    for fpath, rel, f in context._all_walk_cache:
        fset.add(os.path.normpath(fpath))
    _file_path_set_cache[ckey] = fset
    return fset


def _build_file_layer_map(context, layers):
    """构建文件→层映射表，O(1) 查询文件所属层
    
    避免每次 get_file_layer 都遍历所有层的所有目录做前缀匹配
    """
    ckey = _cache_key(context)
    if ckey in _file_layer_map_cache:
        return _file_layer_map_cache[ckey]
    
    context._ensure_walk_cache()
    
    # 规范化各层目录
    norm_layer_dirs = {}
    for layer, dirs in layers.items():
        norm_layer_dirs[layer] = [os.path.normpath(d) for d in dirs]
    
    file_layer_map = {}
    for fpath, rel, f in context._all_walk_cache:
        if not any(fpath.endswith(ext) for ext in _CODE_EXTS):
            continue
        fpath_norm = os.path.normpath(fpath)
        for layer, ndirs in norm_layer_dirs.items():
            for d in ndirs:
                if fpath_norm.startswith(d + os.sep) or fpath_norm == d:
                    file_layer_map[fpath_norm] = layer
                    break
            if fpath_norm in file_layer_map:
                break
    
    _file_layer_map_cache[ckey] = file_layer_map
    return file_layer_map


def detect_arch_layers(context):
    """检测项目中的架构分层目录结构
    
    优化：基于 context._all_walk_cache 过滤，避免重复 os.walk
    返回: {layer_name: [完整目录路径列表]}
    
    零行为变更：与原始 os.walk 版本结果完全一致
    - 只在 search_path 范围内搜索目录（不向上扩散）
    - 排除目录与原始 _default_exclude_dirs 保持一致
    """
    ckey = _cache_key(context)
    if ckey in _arch_layers_cache:
        return _arch_layers_cache[ckey]

    layers = {k: [] for k in _ARCH_LAYER_KEYWORDS}
    
    # 确保 walk 缓存就绪
    context._ensure_walk_cache()
    
    search_paths = []
    if context.project_path and os.path.isdir(context.project_path):
        search_paths.append(os.path.normpath(context.project_path))
    if context.backend_path and context.backend_path != context.project_path and os.path.isdir(context.backend_path):
        search_paths.append(os.path.normpath(context.backend_path))
    
    # 从 walk 缓存中提取所有目录（仅在 search_paths 范围内）
    # walk_cache 元素是 (fpath, rel, filename)
    dirs_seen = set()
    for fpath, rel, f in context._all_walk_cache:
        # 找到对应的 search_path
        fpath_norm = os.path.normpath(fpath)
        for sp in search_paths:
            if fpath_norm.startswith(sp + os.sep) or fpath_norm == sp:
                # 提取该文件下的所有中间目录，都在 sp 范围内
                dir_path = os.path.dirname(fpath_norm)
                while dir_path and dir_path != sp and dir_path.startswith(sp + os.sep):
                    if dir_path not in dirs_seen:
                        dirs_seen.add(dir_path)
                    dir_path = os.path.dirname(dir_path)
                break
    
    # 对每个目录检查是否匹配分层关键词（与原逻辑完全一致）
    for d in dirs_seen:
        basename = os.path.basename(d)
        if not basename:
            continue
        d_lower = basename.lower().replace("-", "_")
        for layer, keywords in _ARCH_LAYER_KEYWORDS.items():
            for kw in keywords:
                if d_lower == kw or d_lower.endswith("_" + kw) or d_lower.startswith(kw + "_"):
                    if d not in layers[layer]:
                        layers[layer].append(d)
                    break
    
    _arch_layers_cache[ckey] = layers
    return layers


# ===== 分层文件收集 =====
_layer_files_cache = {}  # cache_key -> {layer: [file_paths]}

def get_layer_files(context, layers, layer_name):
    """获取指定层的所有源文件
    
    优化：基于 context walk 缓存过滤，避免每层都 os.walk
    """
    ckey = _cache_key(context)
    if ckey not in _layer_files_cache:
        _layer_files_cache[ckey] = {}
    
    if layer_name in _layer_files_cache[ckey]:
        return _layer_files_cache[ckey][layer_name]
    
    layer_dirs = layers.get(layer_name, [])
    if not layer_dirs:
        _layer_files_cache[ckey][layer_name] = []
        return []
    
    # 规范化目录
    norm_dirs = [os.path.normpath(d) + os.sep for d in layer_dirs]
    norm_dirs_eq = [os.path.normpath(d) for d in layer_dirs]
    
    exclude_files = set(context.config.get("exclude_files", []))
    
    result = []
    for fpath, rel, f in context._all_walk_cache:
        if f in exclude_files:
            continue
        if not any(fpath.endswith(ext) for ext in _CODE_EXTS):
            continue
        fpath_norm = os.path.normpath(fpath)
        # 判断是否在该层目录下
        for d in norm_dirs:
            if fpath_norm.startswith(d):
                result.append(fpath)
                break
        else:
            for d in norm_dirs_eq:
                if fpath_norm == d:
                    result.append(fpath)
                    break
    
    _layer_files_cache[ckey][layer_name] = result
    return result


# ===== 文件分层判断 =====
def get_file_layer(file_path, layers, context=None):
    """判断文件属于哪一架构层
    
    优化：优先使用 file_layer_map 缓存，O(1) 查找
    若未提供 context 则回退到原始遍历方式
    """
    file_path_norm = os.path.normpath(file_path)
    
    if context is not None:
        try:
            layer_map = _build_file_layer_map(context, layers)
            if file_path_norm in layer_map:
                return layer_map[file_path_norm]
            return None
        except Exception:
            pass
    
    # 回退路径（保持零行为变更）
    for layer, dirs in layers.items():
        for d in dirs:
            d_norm = os.path.normpath(d)
            if file_path_norm.startswith(d_norm + os.sep) or file_path_norm == d_norm:
                return layer
    return None


# ===== 导入提取 =====
_imports_cache = {}  # cache_key -> {file_path: [(lineno, module, kind), ...]}

def _extract_py_imports_cached(file_path, context):
    """提取Python文件中的import语句（优先用AST摘要缓存）"""
    results = []
    try:
        _sum = context.get_ast_summary(file_path)
        if not _sum:
            return results
        for _imp in _sum.get('imports', []):
            kind = "from" if _imp.get('from') or _imp.get('type') == 'from_import' else "import"
            results.append((_imp['lineno'], _imp['module'], kind))
    except Exception:
        # 回退到正则
        content = context.safe_read(file_path)
        if not content:
            return results
        lines = content.split("\n")
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            m = _PY_IMPORT_RE.match(stripped)
            if m:
                results.append((i, m.group(1), "import"))
            m = _PY_FROM_RE.match(stripped)
            if m:
                results.append((i, m.group(1), "from"))
    return results


def _extract_js_imports_cached(file_path, context):
    """提取JS/TS文件中的import/require语句"""
    results = []
    content = context.safe_read(file_path)
    if not content:
        return results
    lines = content.split("\n")
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        m = _JS_IMPORT_RE.match(stripped)
        if m:
            results.append((i, m.group(1), "import"))
            continue
        m = _JS_REQUIRE_RE.match(stripped)
        if m:
            results.append((i, m.group(1), "require"))
            continue
    return results


def extract_imports(file_path, context):
    """根据文件类型提取import语句（带 context 级缓存）"""
    ckey = _cache_key(context)
    if ckey not in _imports_cache:
        _imports_cache[ckey] = {}
    
    cache = _imports_cache[ckey]
    if file_path in cache:
        return cache[file_path]
    
    if file_path.endswith(".py"):
        results = _extract_py_imports_cached(file_path, context)
    elif file_path.endswith(_JS_EXTS):
        results = _extract_js_imports_cached(file_path, context)
    else:
        results = []
    
    cache[file_path] = results
    return results


# ===== 辅助函数 =====
def is_relative_import(module_path):
    """判断是否为相对导入"""
    return module_path.startswith(".") or module_path.startswith("/")


def is_config_import(module_path):
    """判断导入是否为配置模块"""
    module_lower = module_path.lower().lstrip('.')
    top_module = module_lower.split('.')[0].split('/')[0]
    if top_module in _CONFIG_NAMES:
        return True
    for cfg_name in _CONFIG_NAMES:
        if module_lower == cfg_name or module_lower.startswith(cfg_name + '.') or module_lower.startswith(cfg_name + '/'):
            return True
    return False


def resolve_relative_import(file_path, module_path, context):
    """解析相对导入的目标路径
    
    优化：优先使用 walk 缓存的文件集合做 O(1) 查找，避免 os.path.isfile 磁盘IO
    """
    file_dir = os.path.dirname(file_path)
    is_js_file = file_path.endswith(_JS_EXTS)
    is_py_file = file_path.endswith(".py")

    if is_js_file and (module_path.startswith("./") or module_path.startswith("../") or module_path.startswith("/")):
        target = os.path.normpath(os.path.join(file_dir, module_path))
        # 优先用缓存集合查找（内存中 O(1)）
        try:
            fset = _get_file_path_set(context)
            for ext in _JS_FILE_EXTS + _JS_INDEX_EXTS:
                candidate = os.path.normpath(target + ext)
                if candidate in fset:
                    return candidate
            return None
        except Exception:
            # 回退到磁盘检查
            for ext in _JS_FILE_EXTS + _JS_INDEX_EXTS:
                if os.path.isfile(target + ext):
                    return target + ext
            return None

    if is_py_file and module_path.startswith("."):
        level = 0
        for c in module_path:
            if c == ".":
                level += 1
            else:
                break
        remainder = module_path[level:]
        current = file_dir
        for _ in range(level - 1):
            current = os.path.dirname(current)
        if remainder:
            target = os.path.join(current, remainder.replace(".", os.sep))
        else:
            target = current
        
        # 优先用缓存集合查找
        try:
            fset = _get_file_path_set(context)
            candidate_py = os.path.normpath(target + ".py")
            if candidate_py in fset:
                return candidate_py
            candidate_init = os.path.normpath(os.path.join(target, "__init__.py"))
            if candidate_init in fset:
                return candidate_init
            return None
        except Exception:
            # 回退到磁盘检查
            if os.path.isfile(target + ".py"):
                return target + ".py"
            if os.path.isfile(os.path.join(target, "__init__.py")):
                return os.path.join(target, "__init__.py")
            return None

    return None


# ===== 禁止导入检测 =====
def is_forbidden_domain_import(module_path, file_path, layers, context):
    """判断领域层文件中的导入是否违规
    
    优化：预编译正则 + 哈希表精确匹配，避免嵌套循环 re.search
    返回: (是否违规, 违规类型, 说明)
    """
    module_lower = module_path.lower()

    # 配置文件导入属于正常依赖
    if is_config_import(module_path):
        return False, "", ""

    # 检查是否是向基础设施层/表现层的反向依赖
    if is_relative_import(module_path):
        target_file = resolve_relative_import(file_path, module_path, context)
        if target_file:
            target_layer = get_file_layer(target_file, layers, context)
            if target_layer in ("infrastructure", "presentation"):
                return True, "reverse_dependency", f"领域层依赖{target_layer}层: {module_path}"
        else:
            module_norm = module_path.replace("\\", "/").lower()
            for layer in ("infrastructure", "presentation"):
                for kw, pattern in _LAYER_KW_REL_PATTERNS[layer]:
                    if pattern.search(module_norm):
                        return True, "reverse_dependency", f"领域层依赖{layer}层: {module_path}"
    else:
        for layer in ("infrastructure", "presentation"):
            for kw, pattern in _LAYER_KW_PATTERNS[layer]:
                if pattern.search(module_lower):
                    return True, "reverse_dependency", f"领域层依赖{layer}层: {module_path}"

    # 检查是否导入了禁止的技术依赖（优化：先精确匹配，再前缀匹配）
    if module_lower in _FORBIDDEN_EXACT:
        cat, _ = _FORBIDDEN_EXACT[module_lower]
        return True, "tech_detail", f"领域层导入技术细节({cat}): {module_path}"
    
    for prefix, (cat, _) in _FORBIDDEN_PREFIXES.items():
        if module_lower.startswith(prefix):
            return True, "tech_detail", f"领域层导入技术细节({cat}): {module_path}"
        # 后缀匹配: module.endswith("/" + forbidden) 或 module.endswith("." + forbidden)
        # 也检查中间包含: "/" + forbidden + "/" in module
        if "/" in module_lower and (module_lower.endswith(prefix.replace(".", "/").rstrip("/")) or 
                                     "/" + prefix.rstrip(".").rstrip("/") + "/" in module_lower):
            # 验证完整匹配
            f_name = prefix.rstrip(".").rstrip("/")
            if (module_lower.endswith("/" + f_name) or 
                "/" + f_name + "/" in module_lower or
                module_lower.endswith("." + f_name)):
                return True, "tech_detail", f"领域层导入技术细节({cat}): {module_path}"

    return False, "", ""


# ===== 领域纯净度检查 =====
def check_domain_purity(file_path, context):
    """检查领域层文件的纯净度
    返回: [(行号, 违规类型, 匹配文本)] 列表
    """
    issues = []
    content = context.safe_read(file_path)
    if not content:
        return issues
    lines = content.split("\n")
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("*"):
            continue
        if stripped.startswith("import ") or stripped.startswith("from ") or stripped.startswith("const "):
            # 注意：原逻辑用 re.match 匹配 const...= require(，这里保守处理
            if "require(" in stripped:
                pass  # 继续检查
            else:
                if stripped.startswith("import ") or stripped.startswith("from "):
                    continue
        for pattern, label in _DOMAIN_IMPURITY_PATTERNS:
            if pattern.search(line):
                snippet = stripped[:100]
                issues.append((i, label, snippet))
                break
    return issues


# ===== 领域接口检测 =====
_domain_interfaces_cache = {}  # cache_key -> {file_path: (has_interface, [names])}

def has_domain_interface(file_path, context):
    """检查文件中是否有领域层接口/抽象类定义（带缓存）
    返回: (是否有接口定义, 接口名称列表)
    """
    ckey = _cache_key(context)
    if ckey not in _domain_interfaces_cache:
        _domain_interfaces_cache[ckey] = {}
    
    cache = _domain_interfaces_cache[ckey]
    if file_path in cache:
        return cache[file_path]
    
    interfaces = []
    content = context.safe_read(file_path)
    if not content:
        result = (False, interfaces)
        cache[file_path] = result
        return result
    
    if file_path.endswith(".py"):
        try:
            _sum = context.get_ast_summary(file_path)
            if _sum:
                for _cls in _sum.get('classes', []):
                    bases = _cls['bases']
                    cls_name = _cls['name']
                    if any("ABC" in b for b in bases) or _INTERFACE_NAME_RE.search(cls_name) or any(
                        _INTERFACE_NAME_RE.search(b) for b in bases
                    ):
                        interfaces.append(cls_name)
        except Exception:
            pass
    elif file_path.endswith((".ts", ".tsx")):
        for m in _TS_INTERFACE_RE.finditer(content):
            name = m.group(2)
            if re.search(r'(Repository|Port|Gateway|Service|Interface)$', name):
                interfaces.append(name)
    
    result = (len(interfaces) > 0, interfaces)
    cache[file_path] = result
    return result


# ===== 基础设施层实现检测 =====
def get_infra_implementations(file_path, context):
    """获取基础设施层文件中的实现类信息
    返回: [f"{rel_path}: {cls_name} 继承 {base}"]
    """
    results = []
    content = context.safe_read(file_path)
    if not content:
        return results
    
    if file_path.endswith(".py"):
        try:
            _sum = context.get_ast_summary(file_path)
            if _sum:
                for _cls in _sum.get('classes', []):
                    for base in _cls['bases']:
                        if _IMPL_BASE_RE.search(base):
                            results.append(f"{_cls['name']} 继承 {base}")
        except Exception:
            pass
    elif file_path.endswith((".ts", ".js", ".tsx", ".jsx")):
        for m in _TS_IMPL_RE.finditer(content):
            cls_name = m.group(1)
            bases_str = m.group(2)
            if _IMPL_BASE_RE.search(bases_str):
                results.append(f"{cls_name} 实现 {bases_str.strip()}")
    return results


# ===== 相对路径 =====
def relpath(file_path, project_path, backend_path):
    """计算相对于项目根目录的路径"""
    for base in [project_path, backend_path]:
        if base and file_path.startswith(base):
            rp = os.path.relpath(file_path, base)
            if not rp.startswith(".."):
                return rp
    return file_path
