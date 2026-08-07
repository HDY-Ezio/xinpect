"""
项目类型检测模块
从 QAContext 中抽离，负责项目类型的自动识别

设计原则：
- 所有检测函数都是纯函数，接受必要的参数（如文件读取函数）
- 保持与原 QAContext._detect_project_type_v2 完全一致的行为
"""

import os
import re


# 项目类型名称映射
PROJECT_TYPE_NAMES = {
    "miniprogram": "微信小程序",
    "web": "网页/Web应用",
    "python_backend": "Python后端(SCF)",
    "python_tool": "Python工具/框架",
    "flask": "Python后端(Flask)",
    "electron": "Electron桌面端",
    "skill": "扣子技能",
    "agent": "Agent/工作流",
    "mixed": "混合项目(前端+后端)",
    "mixed_electron": "混合项目(Electron+Python)",
    "unknown": "未知类型",
}

# 模块适用性映射: "all" = 所有类型适用; 列表 = 仅列出的类型适用
MODULE_APPLICABILITY = {
    "api_linkage": ["miniprogram", "web", "mixed", "electron", "mixed_electron"],
    "navigation": ["miniprogram", "web", "mixed", "electron", "mixed_electron"],
    "security": "all",
    "data_consistency": ["miniprogram", "web", "mixed", "electron", "mixed_electron"],
    "ui_design": ["miniprogram", "web", "mixed", "electron", "mixed_electron"],
    "code_quality": "all",
    "deploy_readiness": "all",
    "business_flow": ["miniprogram", "web", "mixed", "electron", "mixed_electron"],
    "architecture_health": "all",
    "smoke_test": "all",
    "change_impact": "all",
    "performance": ["miniprogram", "web", "mixed", "electron", "mixed_electron"],
    "error_handling": "all",
    "test_ci": "all",
    "git_diff": "all",
    "reflection": "all",
    "arch_dependency": "all",
    "ai_diagnosis": "all",
    "miniprogram_config": ["miniprogram", "mixed"],
}

# 目录排除列表（与 context 保持一致）
_DETECT_EXCLUDE_DIRS = {
    "node_modules", "miniprogram_npm", ".git", "__pycache__",
    "venv", ".venv", ".pymysql", "codeact", "archived", "ec-canvas",
    "rules", "skills", ".skills", "backups", "backup",
    "dist", "build", ".eggs", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".tox", ".nox", ".coverage", "site-packages",
    ".xinpect_cache", ".qa_history",
}
_DETECT_EXCLUDE_PREFIXES = ("backup", "bak", "_backup", "old_", ".backup")

# 预编译正则，避免每次 classify_file 都重新编译
_RE_FLASK = re.compile(
    r'from\s+flask|import\s+flask|@app\.route|Flask\s*\(__name__|flask_restful|flask_cors'
)
_RE_DJANGO = re.compile(
    r'django\.db|from\s+django|import\s+django|DJANGO_SETTINGS'
)
_RE_FASTAPI = re.compile(
    r'from\s+fastapi|import\s+fastapi|FastAPI\s*\('
)
_RE_SERVER_ENTRY = re.compile(
    r'app\.run\s*\(|uvicorn\.run|server\.listen|app\.listen'
)
_RE_CLI_ENTRY = re.compile(
    r'argparse|click\.|typer\.|def\s+main\s*\(|if\s+__name__\s*==\s*.__main__.'
)
_RE_ELECTRON_PKG = re.compile(r'["\']electron["\']')
_RE_FRONTEND_DEP = re.compile(r'"vue"|"react"|"next"|"nuxt"|"@angular')
_RE_ELECTRON_JS = re.compile(
    r'BrowserWindow|ipcMain|ipcRenderer|app\.on\s*\(|electron'
)

# 强特征文件：一出现就能大概率确定项目类型，检测到后可提前终止扫描
_STRONG_SIGNAL_FILES = frozenset({
    "SKILL.md",           # skill 项目强特征
    "project.config.json",# 小程序强特征
    "wxml.js",            # 小程序构建产物
})


def _all_py_framework_flags_set(flags: dict) -> bool:
    """判断 py 文件框架特征的 5 个标志是否都已找到

    用于提前终止后续 py 文件的内容读取，减少磁盘 IO。
    """
    return (
        flags.get("has_flask", False)
        and flags.get("has_django", False)
        and flags.get("has_fastapi", False)
        and flags.get("has_server_entry", False)
        and flags.get("has_cli_entry", False)
    )


def classify_file(filename: str, filepath: str, flags: dict, safe_read_fn=None) -> None:
    """分类单个文件，更新flags字典
    
    Args:
        filename: 文件名
        filepath: 文件完整路径
        flags: 标志位字典（会被修改）
        safe_read_fn: 安全读取文件的函数，用于检测 py 文件中的框架特征
    """
    if filename.endswith(".wxml"):
        flags["has_wxml"] = True
        flags["frontend_framework_count"] = flags.get("frontend_framework_count", 0) + 1
    elif filename.endswith((".vue",)):
        flags["has_vue"] = True
        flags["frontend_framework_count"] = flags.get("frontend_framework_count", 0) + 1
    elif filename.endswith((".tsx", ".jsx")):
        flags["has_tsx_jsx"] = True
        flags["frontend_framework_count"] = flags.get("frontend_framework_count", 0) + 1
    elif filename.endswith((".html", ".htm")):
        flags["has_html"] = True
        flags["html_count"] = flags.get("html_count", 0) + 1
    elif filename.endswith(".py"):
        flags["has_py"] = True
        flags["py_count"] = flags.get("py_count", 0) + 1
        # 性能优化：5 个 py 框架标志都已找到就不再读文件内容
        if safe_read_fn and not _all_py_framework_flags_set(flags):
            py_content = safe_read_fn(filepath)
            if not flags.get("has_flask") and _RE_FLASK.search(py_content):
                flags["has_flask"] = True
            if not flags.get("has_django") and _RE_DJANGO.search(py_content):
                flags["has_django"] = True
            if not flags.get("has_fastapi") and _RE_FASTAPI.search(py_content):
                flags["has_fastapi"] = True
            if not flags.get("has_server_entry") and _RE_SERVER_ENTRY.search(py_content):
                flags["has_server_entry"] = True
            if not flags.get("has_cli_entry") and _RE_CLI_ENTRY.search(py_content):
                flags["has_cli_entry"] = True
    elif filename == "SKILL.md":
        flags["has_skill_md"] = True
    elif filename == "app.json":
        if safe_read_fn:
            json_content = safe_read_fn(filepath)
            if '"pages"' in json_content:
                flags["has_app_json_pages"] = True
    elif filename == "package.json":
        if safe_read_fn:
            pkg_content = safe_read_fn(filepath)
            if not flags.get("has_electron") and _RE_ELECTRON_PKG.search(pkg_content):
                flags["has_electron"] = True
            # 检测前端框架依赖
            if _RE_FRONTEND_DEP.search(pkg_content):
                flags["has_frontend_framework_dep"] = True
    elif filename in ("main.js", "main.ts", "electron.js", "electron.ts") and not flags.get("has_electron"):
        if safe_read_fn:
            js_content = safe_read_fn(filepath)
            if _RE_ELECTRON_JS.search(js_content):
                flags["has_electron"] = True


def has_real_frontend(flags: dict) -> bool:
    """判断是否存在真正的前端框架文件（.vue/.tsx/.jsx/.wxml）
    
    用于区分：
    - Flask/Django 的 Jinja2 模板（.html）→ 不算前端框架
    - Vue/React 等前端框架文件（.vue/.tsx/.jsx）→ 真正的前端
    - 小程序文件（.wxml）→ 真正的前端
    """
    return (flags.get("has_wxml", False) or 
            flags.get("has_vue", False) or 
            flags.get("has_tsx_jsx", False))


def has_backend_framework(flags: dict) -> bool:
    """判断是否存在后端框架（Flask/Django/FastAPI）"""
    return (flags.get("has_flask", False) or 
            flags.get("has_django", False) or 
            flags.get("has_fastapi", False))


def resolve_project_type(flags: dict) -> str:
    """根据收集到的flags判定项目类型
    
    v3.5.1 修复：后端框架（Flask/Django/FastAPI）+ .html模板 ≠ mixed
    .html 在后端项目中通常是 Jinja2/Django Templates，不是前端框架文件。
    只有同时存在真正的前端框架文件（.vue/.tsx/.jsx/.wxml）才判定为 mixed。
    """
    if flags.get("has_skill_md"):
        return "skill"
    
    # 小程序检测
    if flags.get("has_wxml") and flags.get("has_app_json_pages"):
        return "mixed" if flags.get("has_py") else "miniprogram"
    
    # Electron 检测
    if flags.get("has_electron"):
        return "mixed_electron" if (flags.get("has_flask") or flags.get("has_py")) else "electron"
    
    has_backend_fw = has_backend_framework(flags)
    has_real_fe = has_real_frontend(flags)
    
    # .html 文件处理：区分「后端模板」和「真正的前端项目」
    if flags.get("has_html"):
        if has_backend_fw and not has_real_fe:
            # 后端框架 + 仅有 .html（Jinja2/Django模板） → 后端项目，不是 mixed
            if flags.get("has_flask"):
                return "flask"
            elif flags.get("has_django"):
                return "python_backend"
            elif flags.get("has_fastapi"):
                return "python_backend"
            else:
                return "python_backend"
        elif has_real_fe and flags.get("has_py"):
            # 有真正的前端框架文件 + 后端 → mixed
            return "mixed"
        elif has_real_fe and not flags.get("has_py"):
            # 有前端框架文件，无后端 → web
            return "web"
        else:
            # 仅 .html，无后端框架也无前端框架 → web
            return "mixed" if flags.get("has_py") else "web"
    
    # 无 .html 的情况
    if has_real_fe and flags.get("has_py"):
        # 有前端框架文件 + 后端 Python → mixed（即使没有 .html）
        return "mixed"
    if flags.get("has_flask"):
        return "flask"
    if flags.get("has_py"):
        return "python_backend" if (flags.get("has_server_entry") and not flags.get("has_cli_entry")) else "python_tool"
    
    # 仅有前端框架文件，无后端
    if has_real_fe:
        return "web"
    
    return "unknown"


def resolve_project_type_v2(flags: dict) -> str:
    """v3.5.1 改进版：带文件比例感知的类型判定（安全网）
    
    作为 resolve_project_type 的二次校验：
    如果 v1 误判为 mixed/web，但实际没有真正的前端框架文件，降级为 backend。
    """
    base = resolve_project_type(flags)
    
    # 安全网：如果判为 mixed 但实际没有真正的前端文件，降级为 backend
    if base in ("mixed", "web"):
        has_real_fe = has_real_frontend(flags)
        if not has_real_fe:
            # 没有 .vue/.tsx/.jsx/.wxml，不是真正的前端项目
            if flags.get("has_py", False):
                if flags.get("has_flask"):
                    return "flask"
                elif flags.get("has_server_entry") and not flags.get("has_cli_entry"):
                    return "python_backend"
                else:
                    return "python_backend"
            elif flags.get("has_html") and base == "web":
                # 纯 web 项目，保留
                return "web"
    return base


def _init_flags() -> dict:
    """初始化检测用的 flags 字典"""
    return {
        "has_wxml": False, "has_html": False, "has_py": False,
        "has_skill_md": False, "has_app_json_pages": False,
        "has_electron": False, "has_flask": False,
        "has_django": False, "has_fastapi": False,
        "has_vue": False, "has_tsx_jsx": False,
        "has_cli_entry": False, "has_server_entry": False,
        "frontend_framework_count": 0,
        "html_count": 0,
        "py_count": 0,
    }


def _can_skip_py_content_read(flags: dict) -> bool:
    """判断是否可以跳过 py 文件内容读取

    当项目类型已经可以确定且不依赖 py 框架特征时，无需读取 py 文件内容。
    注意：跳过 py 内容读取仅影响 verbose 输出中的 flask/django 等计数，
    不影响最终 project_type 判定结果（零行为变更）。

    目前已知的快速路径：
    - has_skill_md：SKILL.md 存在 → skill 类型，不需要 py 框架特征
    """
    # SKILL.md 是最强特征，resolve_project_type_v2 第一判断就返回 skill
    if flags.get("has_skill_md"):
        return True
    return False


def detect_project_type(project_path: str, backend_path: str = "",
                        safe_read_fn=None, verbose: bool = False) -> str:
    """检测项目类型（v2版，最完整的检测逻辑）

    性能优化：
    1. 两遍扫描：第一遍只做文件名级分类（零磁盘 IO），同时收集需要读内容的文件路径
    2. py 文件内容读取：5 个框架标志都找到后立即停止读取
    3. 强特征快速路径：检测到 SKILL.md 等强特征时跳过 py 内容读取

    Args:
        project_path: 前端/主项目路径
        backend_path: 后端项目路径
        safe_read_fn: 安全读取文件的函数（可选，传了才能检测框架特征）
        verbose: 是否输出诊断日志

    Returns:
        项目类型字符串
    """
    flags = _init_flags()

    search_paths = []
    if project_path and os.path.isdir(project_path):
        search_paths.append(project_path)
    if backend_path and backend_path != project_path and os.path.isdir(backend_path):
        search_paths.append(backend_path)

    if not search_paths:
        return "unknown"

    # 第一遍：文件名分类（零 IO），同时收集需要读内容的文件路径
    # - py_files: 待检测框架特征的 py 文件（可能提前终止读取）
    # - app_json_files, package_json_files, electron_main_files: 特殊文件列表
    py_files = []
    app_json_files = []
    package_json_files = []
    electron_main_files = []

    for search_path in search_paths:
        for root, dirs, files in os.walk(search_path):
            dirs[:] = [d for d in dirs
                       if d not in _DETECT_EXCLUDE_DIRS
                       and not d.startswith(_DETECT_EXCLUDE_PREFIXES)]
            for fname in files:
                # 跳过备份文件和编译文件
                if fname.endswith(('.bak', '.pyc', '.pyo')):
                    continue
                fpath = os.path.join(root, fname)

                # ---- 文件名级分类（只读文件名，零磁盘 IO）----
                if fname.endswith(".wxml"):
                    flags["has_wxml"] = True
                    flags["frontend_framework_count"] = flags.get("frontend_framework_count", 0) + 1
                elif fname.endswith(".vue"):
                    flags["has_vue"] = True
                    flags["frontend_framework_count"] = flags.get("frontend_framework_count", 0) + 1
                elif fname.endswith((".tsx", ".jsx")):
                    flags["has_tsx_jsx"] = True
                    flags["frontend_framework_count"] = flags.get("frontend_framework_count", 0) + 1
                elif fname.endswith((".html", ".htm")):
                    flags["has_html"] = True
                    flags["html_count"] = flags.get("html_count", 0) + 1
                elif fname.endswith(".py"):
                    flags["has_py"] = True
                    flags["py_count"] = flags.get("py_count", 0) + 1
                    if safe_read_fn and not _can_skip_py_content_read(flags):
                        py_files.append(fpath)
                elif fname == "SKILL.md":
                    flags["has_skill_md"] = True
                    # 强特征快速终止：SKILL.md → skill 类型（零行为变更）
                    # resolve_project_type_v2 第一判断就返回 skill，
                    # 直接短路返回，跳过剩余文件遍历和内容读取
                    if verbose:
                        try:
                            print(f"[项目类型] 判定为 skill，依据: py={flags.get('py_count', 0)} "
                                  f"html={flags.get('html_count', 0)} "
                                  f"vue={int(flags.get('has_vue', False))} "
                                  f"tsx_jsx={int(flags.get('has_tsx_jsx', False))} "
                                  f"wxml={int(flags.get('has_wxml', False))} "
                                  f"flask={int(flags.get('has_flask', False))} "
                                  f"django={int(flags.get('has_django', False))} "
                                  f"fastapi={int(flags.get('has_fastapi', False))} "
                                  f"electron={int(flags.get('has_electron', False))}")
                        except Exception:
                            pass
                    return "skill"
                elif fname == "app.json":
                    if safe_read_fn:
                        app_json_files.append(fpath)
                elif fname == "package.json":
                    if safe_read_fn:
                        package_json_files.append(fpath)
                elif fname in ("main.js", "main.ts", "electron.js", "electron.ts"):
                    if safe_read_fn and not flags.get("has_electron"):
                        electron_main_files.append(fpath)

    # 第二遍：按需读取文件内容（只有 safe_read_fn 存在时才执行）
    if safe_read_fn:
        # 1. 读取 app.json（检测 pages 字段）
        for fpath in app_json_files:
            json_content = safe_read_fn(fpath)
            if '"pages"' in json_content:
                flags["has_app_json_pages"] = True
                break  # 找到一个就够了

        # 2. 读取 package.json（检测 electron / 前端框架依赖）
        for fpath in package_json_files:
            pkg_content = safe_read_fn(fpath)
            if not flags.get("has_electron") and _RE_ELECTRON_PKG.search(pkg_content):
                flags["has_electron"] = True
            if _RE_FRONTEND_DEP.search(pkg_content):
                flags["has_frontend_framework_dep"] = True

        # 3. 读取 electron 主进程文件
        if not flags.get("has_electron"):
            for fpath in electron_main_files:
                js_content = safe_read_fn(fpath)
                if _RE_ELECTRON_JS.search(js_content):
                    flags["has_electron"] = True
                    break

        # 4. 读取 py 文件（检测框架特征）
        #    强特征快速路径：项目类型已可确定且不依赖 py 框架特征时，跳过 py 内容读取
        if not _can_skip_py_content_read(flags):
            for fpath in py_files:
                if _all_py_framework_flags_set(flags):
                    break
                py_content = safe_read_fn(fpath)
                if not flags.get("has_flask") and _RE_FLASK.search(py_content):
                    flags["has_flask"] = True
                if not flags.get("has_django") and _RE_DJANGO.search(py_content):
                    flags["has_django"] = True
                if not flags.get("has_fastapi") and _RE_FASTAPI.search(py_content):
                    flags["has_fastapi"] = True
                if not flags.get("has_server_entry") and _RE_SERVER_ENTRY.search(py_content):
                    flags["has_server_entry"] = True
                if not flags.get("has_cli_entry") and _RE_CLI_ENTRY.search(py_content):
                    flags["has_cli_entry"] = True

    result = resolve_project_type_v2(flags)

    # 诊断日志
    if verbose:
        try:
            print(f"[项目类型] 判定为 {result}，依据: py={flags.get('py_count', 0)} "
                  f"html={flags.get('html_count', 0)} vue={int(flags.get('has_vue', False))} "
                  f"tsx_jsx={int(flags.get('has_tsx_jsx', False))} "
                  f"wxml={int(flags.get('has_wxml', False))} "
                  f"flask={int(flags.get('has_flask', False))} "
                  f"django={int(flags.get('has_django', False))} "
                  f"fastapi={int(flags.get('has_fastapi', False))} "
                  f"electron={int(flags.get('has_electron', False))}")
        except Exception:
            pass

    return result
