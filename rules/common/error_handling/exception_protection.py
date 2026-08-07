"""
错误处理与韧性规则集 - 异常防护子模块 (M13)
从 error_handling.py 拆分而来，包含:
  13.1 导入安全 - 检查导入的模块是否在依赖清单中
  13.2 未处理异常模式 - bare except、空catch、Promise无catch等
  13.3 全局错误处理器 - 应用级全局错误兜底
  13.4 关键操作保护 - 数据库/文件/网络等关键操作异常保护
  13.5 异步错误处理 - async/await、asyncio.gather错误处理
"""

import re
import os
import json
from typing import List, Dict, Any
from collections import defaultdict


# ===== 工具依赖（误报过滤增强） =====
try:
    from core.utils import is_ops_script, is_mock_context
    _HAS_UTILS = True
except ImportError:
    # 兼容旧架构的独立导入路径
    try:
        from architecture_detector import is_ops_script
        from context_analyzer import is_mock_context
        _HAS_UTILS = True
    except ImportError:
        _HAS_UTILS = False


# 敏感数据日志模式
SENSITIVE_LOG_PATTERNS = [
    r'(?:password|passwd|pwd)\s*[=:]\s*["\'][^"\']+["\']',
    r'(?:secret|api_key|apikey|api-key)\s*[=:]\s*["\'][^"\']+["\']',
    r'(?:token|authorization)\s*[=:]\s*["\'][^"\']+["\']',
    r'print\s*\(\s*f?["\'].*(?:password|secret|token|key).*["\']',
    r'console\.(log|debug|info)\s*\(.*(?:password|secret|token|key|credential).*\)',
    r'logging\.\w+\s*\(.*(?:password|secret|token|key|credential).*\)',
]

def _get_frontend_files(context) -> List[str]:
    """获取前端文件列表（根据项目类型）"""
    if not context.project_path or not os.path.isdir(context.project_path):
        return []
    if context.is_web_frontend():
        return context.find_files([".tsx", ".jsx", ".ts", ".js"])
    else:
        return context.find_files([".js", ".wxml"])


def _check_global_error_handler_exists(context, backend_files, front_files) -> bool:
    """检查是否有全局错误处理器（供13.2使用）"""
    # Python/FastAPI
    for f in backend_files:
        content = context.safe_read(f)
        if re.search(r'@app\.exception_handler|@.*\.exception_handler|add_exception_handler|errorhandler', content):
            return True
        if re.search(r'App\.onError|onError\s*[:=]', content):
            return True

    # JS/小程序
    for f in front_files:
        content = context.safe_read(f)
        if re.search(r'App\s*\(\s*\{[^}]*onError', content, re.DOTALL):
            return True
        if re.search(r'onError\s*[:=]|wx\.onError|ErrorBoundary', content):
            return True
        if re.search(r'app\.use\s*\(.*error', content, re.IGNORECASE):
            return True

    return False


# ===== 13.1 导入安全 =====


def check_13_1_import_safety(context) -> List[Dict]:
    """13.1 导入安全 - 检查导入的模块是否在依赖清单中"""
    results = []
    issues = []

    backend_files = context.get_backend_py_files()
    front_files = _get_frontend_files(context)

    # Python后端: 检查import是否在requirements.txt中
    if backend_files:
        req_path = None
        backend_base = context.backend_path
        if backend_base and os.path.isfile(backend_base):
            backend_base = os.path.dirname(backend_base)
        for candidate in ["requirements.txt", "requirements.in", "pyproject.toml", "setup.py"]:
            if backend_base:
                p = os.path.join(backend_base, candidate)
                if os.path.isfile(p):
                    req_path = p
                    break
        if req_path:
            req_content = context.safe_read(req_path)
            # 提取已声明的依赖
            declared = set()
            for line in req_content.split('\n'):
                line = line.strip()
                if line and not line.startswith('#') and not line.startswith('-'):
                    pkg = re.split(r'[<>=!\[]', line)[0].strip().lower().replace('-', '_')
                    if pkg:
                        declared.add(pkg)
            # 标准库模块白名单
            stdlib = {'os','sys','json','re','time','datetime','typing','functools','collections',
                      'io','base64','hashlib','hmac','urllib','pathlib','abc','copy','enum','math',
                      'random','string','struct','traceback','warnings','weakref','itertools',
                      'operator','contextlib','dataclasses','importlib','inspect','logging','csv',
                      'configparser','asyncio','concurrent','threading','multiprocessing','queue',
                      'socket','ssl','http','email','html','xml','xml.etree','html.parser',
                      'unittest','argparse','tempfile','shutil','subprocess','platform','locale',
                      'textwrap','unicodedata','codecs','uuid','secrets','glob','fnmatch',
                      'stat','signal','errno','warnings','types','__future__',
                      'decimal','gzip','zlib','bz2','lzma','tarfile','zipfile',
                      'cryptography','hashlib','hmac','secrets','ssl',
                      'datetime','dateutil','pytz','zoneinfo',
                      'requests','urllib3','aiohttp','httpx',
                      'pymysql','mysql','sqlalchemy','redis',
                      'numpy','pandas','scipy',
                      'jwt','jose','pyjwt',
                      'sqlite3','statistics','xml.etree'}
            declared |= stdlib

            # 添加本地模块（项目目录中的.py文件名，递归扫描子目录）
            for search_dir in ([context.project_path] if context.project_path else []) + \
                              ([context.backend_path] if context.backend_path and os.path.isdir(context.backend_path) else []):
                if os.path.isdir(search_dir):
                    for f_name in os.listdir(search_dir):
                        if f_name.endswith('.py'):
                            declared.add(f_name[:-3].lower().replace('-', '_'))
                    # 递归扫描子目录中的.py文件作为本地模块
                    for root, dirs, files in os.walk(search_dir):
                        dirs[:] = [d for d in dirs if d not in {'__pycache__', '.git', 'node_modules'}]
                        # 将子目录名也作为可导入的包名
                        for d in dirs:
                            declared.add(d.lower().replace('-', '_'))
                        for f_name in files:
                            if f_name.endswith('.py') and f_name != '__init__.py':
                                declared.add(f_name[:-3].lower().replace('-', '_'))

            # 扫描所有import
            missing = set()
            for f in backend_files:
                content = context.safe_read(f)
                for m in re.finditer(r'^\s*(?:from\s+(\S+)\s+)?import\s+(?:\(([^)]+)\)|([^\n]+))', content, re.MULTILINE):
                    module = (m.group(1) or m.group(3) or m.group(2) or '').strip().split(',')[0].strip()
                    # 处理 "import x as y" 别名，只取实际模块名
                    module = re.sub(r'\s+as\s+\w+', '', module)
                    if module:
                        top = module.split('.')[0].lower().replace('-', '_')
                        if top and top not in declared and not top.startswith('_'):
                            missing.add(top)
            if missing:
                issues.append(f"Python后端导入未声明依赖: {', '.join(sorted(missing)[:10])}")
        else:
            pass  # 没有requirements.txt不报错

    # JS/TS前端: 检查import是否在package.json中
    if front_files and context.project_path:
        pkg_path = os.path.join(context.project_path, "package.json")
        if os.path.isfile(pkg_path):
            try:
                pkg = json.loads(context.safe_read(pkg_path))
                declared_js = set()
                for key in ["dependencies", "devDependencies", "peerDependencies"]:
                    declared_js.update(pkg.get(key, {}).keys())
                # Node.js内置模块
                builtin = {'fs','path','os','http','https','url','crypto','util','events','stream',
                           'buffer','child_process','cluster','net','querystring','zlib','readline',
                           'assert','timers','worker_threads','process','console'}
                declared_js |= builtin
                missing_js = set()
                for f in front_files:
                    content = context.safe_read(f)
                    for m in re.finditer(r'(?:import\s+.*?\s+from\s+["\']([^"\']+)["\']|require\s*\(\s*["\']([^"\']+)["\']\s*\))', content):
                        mod = (m.group(1) or m.group(2) or '')
                        if mod and not mod.startswith('.') and not mod.startswith('@/') and not mod.startswith('~/'):
                            if mod.startswith('@'):
                                parts = mod.split('/')
                                top = '/'.join(parts[:2]) if len(parts) >= 2 else mod
                            else:
                                top = mod.split('/')[0]
                            if top and top not in declared_js:
                                missing_js.add(mod)
                if missing_js:
                    issues.append(f"前端导入未声明依赖: {', '.join(sorted(missing_js)[:10])}")
            except Exception as e:  # noqa: broad exception handling
                pass

    if issues:
        results.append({
            'id': '13.1',
            'name': '导入安全',
            'level': 'warning',
            'message': f"发现{len(issues)}类未声明依赖导入",
            'detail': "\n".join(issues),
            'file': '',
            'line': 0,
            'fix': '在requirements.txt/package.json中补充缺失的依赖，或在代码中移除未使用的导入',
        })

    return results


# ===== 13.2 未处理异常模式 =====


def check_13_2_unhandled_exceptions(context) -> List[Dict]:
    """13.2 未处理异常模式 - 深度分析bare except、空catch、Promise错误处理等"""
    results = []
    issues = []
    promise_with_catch = 0
    promise_without_catch = 0
    wx_request_with_fail = 0
    wx_request_without_fail = 0

    backend_files = context.get_backend_py_files()
    front_files = _get_frontend_files(context)

    # Python: bare except: 和 except Exception: 无logging
    for f in backend_files:
        content = context.safe_read(f)
        lines = content.split('\n')
        for i, line in enumerate(lines):
            stripped = line.strip()
            # bare except:
            if re.match(r'^except\s*:', stripped):
                issues.append(f"{os.path.basename(f)}:{i+1} bare except: (捕获所有异常包括SystemExit/KeyboardInterrupt)")
            # except Exception 后面紧跟pass或无操作
            elif re.match(r'^except\s+\w*(?:Error|Exception)?\s*(?:\s+as\s+\w+)?\s*:\s*$', stripped):
                exc_match = re.match(r'^except\s+(\w+)', stripped)
                exc_type = exc_match.group(1) if exc_match else ''
                if exc_type in ('ImportError', 'AttributeError', 'KeyError',
                                'ValueError', 'TypeError', 'IndexError',
                                'FileNotFoundError', 'NotImplementedError'):
                    continue
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if next_line in ('pass', ''):
                        issues.append(f"{os.path.basename(f)}:{i+1} except块为空(pass/无操作)")

    # JS/TS: 空catch块 + Promise错误处理分析
    for f in front_files:
        content = context.safe_read(f)
        rel_name = os.path.basename(f)

        # 空catch块
        for m in re.finditer(r'catch\s*\([^)]*\)\s*\{\s*\}', content):
            line_num = content[:m.start()].count('\n') + 1
            issues.append(f"{rel_name}:{line_num} 空catch块")

        # Promise .catch 模式统计
        promise_catches = len(re.findall(r'\.catch\s*\(', content))
        promise_finally = len(re.findall(r'\.finally\s*\(', content))
        promise_with_catch += promise_catches

        # Promise链但无catch（粗略统计）
        then_matches = list(re.finditer(r'\.then\s*\(', content))
        catch_matches = list(re.finditer(r'\.catch\s*\(', content))
        for tm in then_matches:
            has_following_catch = False
            for cm in catch_matches:
                if cm.start() > tm.start():
                    between = content[tm.end():cm.start()]
                    if ';' in between or re.search(r'\n\s*\w', between):
                        continue
                    has_following_catch = True
                    break
            if not has_following_catch:
                promise_without_catch += 1

        # wx.request fail回调统计
        wx_requests = re.findall(r'wx\.request\s*\(\s*\{[^}]*\}\s*\)', content, re.DOTALL)
        for req in wx_requests:
            if 'fail' in req:
                wx_request_with_fail += 1
            else:
                wx_request_without_fail += 1

    # 检查是否有全局错误处理
    has_global_handler = _check_global_error_handler_exists(context, backend_files, front_files)

    if issues:
        base_count = len(issues)

        # 如果有全局错误处理器，降低严重程度
        if has_global_handler:
            level = "info" if base_count <= 10 else "warning"
            global_note = "（已配置全局错误兜底，严重度降级）"
        else:
            level = "error" if base_count > 5 else "warning"
            global_note = ""

        detail_lines = issues[:15]

        # Promise和wx.request统计
        if promise_with_catch > 0 or promise_without_catch > 0:
            detail_lines.append(f"---")
            detail_lines.append(f"Promise统计: 有catch {promise_with_catch}个, 无catch {promise_without_catch}个")
        if wx_request_with_fail > 0 or wx_request_without_fail > 0:
            detail_lines.append(f"wx.request统计: 有fail回调 {wx_request_with_fail}个, 无fail {wx_request_without_fail}个")

        results.append({
            'id': '13.2',
            'name': '未处理异常模式',
            'level': level,
            'message': f"发现{base_count}处异常处理缺陷{global_note}",
            'detail': "\n".join(detail_lines),
            'file': '',
            'line': 0,
            'fix': 'bare except改为except Exception as e并记录日志；空catch块至少添加错误日志',
        })

    return results


# ===== 13.3 全局错误处理器 =====


def check_13_3_global_error_handler(context) -> List[Dict]:
    """13.3 全局错误处理器 - 应用级错误兜底"""
    results = []

    backend_files = context.get_backend_py_files()
    front_files = _get_frontend_files(context)

    found = False

    # Python/FastAPI: exception_handler / middleware
    for f in backend_files:
        content = context.safe_read(f)
        if re.search(r'@app\.exception_handler|@.*\.exception_handler|add_exception_handler|errorhandler|ErrorHandler', content):
            found = True
            break
        if re.search(r'except\s+Exception.*:\s*\n.*(?:return|raise).*(?:error|500|exception)', content, re.IGNORECASE):
            found = True
            break

    # JS/TS: ErrorBoundary / app.use(error) / onError
    if not found:
        for f in front_files:
            content = context.safe_read(f)
            if re.search(r'ErrorBoundary|componentDidCatch|getDerivedStateFromError', content):
                found = True
                break
            if re.search(r'app\.use\s*\(\s*\(err|error.*middleware|onError', content, re.IGNORECASE):
                found = True
                break

    # 小程序: App.onError / wx.onError
    if not found and front_files:
        for f in front_files:
            content = context.safe_read(f)
            if re.search(r'onError\s*[\(:]|wx\.onError', content):
                found = True
                break

    if not found:
        results.append({
            'id': '13.3',
            'name': '全局错误处理器',
            'level': 'warning',
            'message': '未检测到全局错误处理器，未捕获异常会导致应用崩溃或500错误',
            'file': '',
            'line': 0,
            'fix': 'Python: 添加@app.exception_handler(Exception)；React: 添加ErrorBoundary；小程序: App({onError})；Express: app.use(errorHandler)',
        })

    return results


# ===== 13.4 关键操作保护 =====


def check_13_4_critical_op_protection(context) -> List[Dict]:
    """13.4 关键操作保护 - DB/文件/网络操作缺少try-catch"""
    results = []
    issues = []

    backend_files = context.get_backend_py_files()
    front_files = _get_frontend_files(context)

    for f in backend_files:
        content = context.safe_read(f)
        lines = content.split('\n')

        # Step 1: 解析所有函数定义及其范围
        func_starts = []
        for i, line in enumerate(lines):
            m = re.match(r'^def\s+(\w+)\s*\(', line)
            if m:
                func_starts.append((i, m.group(1)))

        funcs = []  # [(name, start, end, has_try, has_db, body_text)]
        for idx, (start, name) in enumerate(func_starts):
            end = func_starts[idx + 1][0] if idx + 1 < len(func_starts) else len(lines)
            body = '\n'.join(lines[start:end])
            has_try = 'try:' in body
            has_db = bool(re.search(r'\.execute\s*\(|\.commit\s*\(|\.rollback\s*\(', body))
            funcs.append((name, start, end, has_try, has_db, body))

        func_names = {f[0] for f in funcs}

        # Step 2: 构建被保护函数集合（传递闭包）
        protected = set()
        for name, start, end, has_try, has_db, body in funcs:
            if has_try:
                for other in func_names:
                    if other != name:
                        if re.search(rf'\b{re.escape(other)}\b', body):
                            protected.add(other)

        changed = True
        while changed:
            changed = False
            for name, start, end, has_try, has_db, body in funcs:
                if name in protected:
                    for other in func_names:
                        if other not in protected and other != name:
                            if re.search(rf'\b{re.escape(other)}\b', body):
                                protected.add(other)
                                changed = True

        # Step 3: 仅对无try且未被调用链保护的函数标记DB操作
        for name, start, end, has_try, has_db, body in funcs:
            if has_try or name in protected or not has_db:
                continue
            for i in range(start, end):
                stripped = lines[i].strip()
                if re.search(r'\.execute\s*\(|\.commit\s*\(|\.rollback\s*\(', stripped):
                    issues.append(f"{os.path.basename(f)}:{i+1} [{name}] DB op not in try: {stripped[:60]}")
                elif re.search(r'open\s*\([^)]*[\'\"\"]w', stripped):
                    issues.append(f"{os.path.basename(f)}:{i+1} [{name}] file write not in try: {stripped[:60]}")

    # JS: .then()链无.catch()
    for f in front_files:
        content = context.safe_read(f)
        for m in re.finditer(r'\.then\s*\(', content):
            line_num = content[:m.start()].count('\n') + 1
            # 从.then(开始，往后找匹配的)和后续.catch()
            pos = m.end()
            depth = 1
            end_pos = pos
            while end_pos < len(content) and depth > 0:
                if content[end_pos] == '(':
                    depth += 1
                elif content[end_pos] == ')':
                    depth -= 1
                end_pos += 1
            # 检查.then(...)后面200字符内是否有.catch()
            after = content[end_pos:end_pos+200]
            if not re.search(r'\.catch\s*\(', after):
                issues.append(f"{os.path.basename(f)}:{line_num} Promise.then() no .catch()")

    if issues:
        level = "error" if len(issues) > 3 else "warning"
        results.append({
            'id': '13.4',
            'name': '关键操作保护',
            'level': level,
            'message': f"发现{len(issues)}处关键操作缺少异常保护",
            'detail': "\n".join(issues[:15]),
            'file': '',
            'line': 0,
            'fix': '数据库/文件/网络操作必须包裹在try-catch中，并记录错误日志',
        })

    return results


# ===== 13.5 异步错误处理 =====


def check_13_5_async_errors(context) -> List[Dict]:
    """13.5 异步错误处理 - 缺失await、未处理的Promise"""
    results = []
    issues = []

    backend_files = context.get_backend_py_files()
    front_files = _get_frontend_files(context)

    # Python: await不在async函数中、asyncio.gather无return_exceptions
    for f in backend_files:
        content = context.safe_read(f)
        lines = content.split('\n')
        async_funcs = set()
        for i, line in enumerate(lines):
            stripped = line.strip()
            if re.match(r'async\s+def\s+', stripped):
                async_funcs.add(i)
        # 检查asyncio.gather无return_exceptions
        for i, line in enumerate(lines):
            if 'asyncio.gather' in line and 'return_exceptions' not in line:
                issues.append(f"{os.path.basename(f)}:{i+1} asyncio.gather()未设置return_exceptions=True，单个任务异常会中断所有任务")

    # JS: async函数无try-catch、await无try-catch
    for f in front_files:
        content = context.safe_read(f)
        # async function without try-catch around await
        for m in re.finditer(r'async\s+(?:function\s+)?(\w+)?\s*\([^)]*\)\s*\{', content):
            func_start = m.end()
            # 找到函数结束的大括号
            depth = 1
            pos = func_start
            while pos < len(content) and depth > 0:
                if content[pos] == '{':
                    depth += 1
                elif content[pos] == '}':
                    depth -= 1
                pos += 1
            func_body = content[func_start:pos-1]
            if 'await ' in func_body and 'try' not in func_body and 'catch' not in func_body:
                line_num = content[:m.start()].count('\n') + 1
                func_name = m.group(1) or 'anonymous'
                issues.append(f"{os.path.basename(f)}:{line_num} async函数'{func_name}'含await但无try-catch")

    if issues:
        results.append({
            'id': '13.5',
            'name': '异步错误处理',
            'level': 'warning',
            'message': f"发现{len(issues)}处异步错误处理缺陷",
            'detail': "\n".join(issues[:10]),
            'file': '',
            'line': 0,
            'fix': 'async函数中的await应包裹try-catch；asyncio.gather设置return_exceptions=True',
        })

    return results


# ===== 13.6 健康检查端点 =====


# ===== 规则定义列表 =====
RULES = [
    {
        'id': '13.1',
        'name': '导入安全',
        'level': 'problem',
        'category': 'error_handling',
        'module_id': '13',
        'applicable_types': [],  # 所有类型适用
        'description': '检查导入的模块是否在依赖清单中（requirements.txt/package.json）',
        'check': check_13_1_import_safety,
    },
    {
        'id': '13.2',
        'name': '未处理异常模式',
        'level': 'blocking',
        'category': 'error_handling',
        'module_id': '13',
        'applicable_types': [],
        'description': '深度分析bare except、空catch、Promise无catch、wx.request无fail等异常处理缺陷',
        'check': check_13_2_unhandled_exceptions,
    },
    {
        'id': '13.3',
        'name': '全局错误处理器',
        'level': 'problem',
        'category': 'error_handling',
        'module_id': '13',
        'applicable_types': [],
        'description': '检查是否有应用级全局错误兜底处理器',
        'check': check_13_3_global_error_handler,
    },
    {
        'id': '13.4',
        'name': '关键操作保护',
        'level': 'blocking',
        'category': 'error_handling',
        'module_id': '13',
        'applicable_types': [],
        'description': '检查数据库/文件/网络等关键操作是否有try-catch异常保护',
        'check': check_13_4_critical_op_protection,
    },
    {
        'id': '13.5',
        'name': '异步错误处理',
        'level': 'problem',
        'category': 'error_handling',
        'module_id': '13',
        'applicable_types': [],
        'description': '检查异步代码中的错误处理，如async函数无try-catch、asyncio.gather无return_exceptions',
        'check': check_13_5_async_errors,
    },
]
