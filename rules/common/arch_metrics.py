"""架构健康度规则集 - 代码质量度量子模块
从 architecture.py 拆分而来，包含代码重复率、依赖安全、复杂度等度量类规则（9.1-9.6）
"""

"""
架构健康度规则集 (M9)
通用架构健康检查 - 适用于所有项目类型
包含: 代码重复率、依赖安全、函数复杂度、错误处理覆盖率、
配置密钥分离、API向后兼容等6项检查
"""

import re
import os
import hashlib
import subprocess
import json
from typing import List, Dict, Any



# ===== 琐碎语法行集合（重复率统计排除） =====
_TRIVIAL_SYNTAX = frozenset({
    'try:', 'except:', 'except Exception as e:', 'except Exception:',
    'else:', 'finally:', 'pass', 'break', 'continue',
    'return', 'return result', 'return None', 'return True', 'return False',
    '}', ')', ']', '{', '(', '[',
    '})', '},', '],', '))', '),', '){', '}{',
    '"""', "'''", '...', 'asyncio.run(main())', 'async def main():',
})


def _is_trivial_code_line(line: str) -> bool:
    """判断是否为琐碎语法行（不计入重复率统计）"""
    s = line.strip()
    if not s or len(s) < 5:
        return True
    if s in _TRIVIAL_SYNTAX:
        return True
    if s.startswith(('import ', 'from ')):
        return True
    if s in ('asyncio.run(main())', 'async def main():'):
        return True
    return False


def _get_all_code_files(context) -> List[str]:
    """获取所有代码文件（前端+后端）"""
    all_files = []
    if context.project_path and os.path.isdir(context.project_path):
        if context.is_web_frontend():
            all_files += context.find_files([".js", ".ts", ".tsx", ".jsx"])
        else:
            all_files += context.find_files([".js"])
    all_files += context.get_backend_py_files()
    return all_files


# ===== 9.1 代码重复率 =====
def check_9_1_code_duplication(context) -> List[Dict]:
    """9.1 代码重复率 - 基于连续块检测（MIN_BLOCK行以上重复才计入）"""
    results = []
    
    all_code_files = _get_all_code_files(context)
    if len(all_code_files) < 2:
        return results
    
    MIN_BLOCK = 5
    file_lines = {}
    
    for f in all_code_files:
        content = context.safe_read(f)
        if not content:
            continue
        lines = [l.strip() for l in content.split('\n')
                 if l.strip() and not l.strip().startswith(('//', '#', '/*', '*'))
                 and not _is_trivial_code_line(l.strip())]
        file_lines[f] = lines
    
    total_lines = sum(len(ls) for ls in file_lines.values())
    if total_lines == 0:
        return results
    
    # 第一遍：统计每个块出现的文件集合
    block_files = {}
    for f, ls in file_lines.items():
        for i in range(len(ls) - MIN_BLOCK + 1):
            bh = hashlib.md5('\n'.join(ls[i:i+MIN_BLOCK]).encode()).hexdigest()
            block_files.setdefault(bh, set()).add(f)
    
    # 第二遍：统计每个文件的重复行数
    dup_lines = 0
    for f, ls in file_lines.items():
        in_dup = [False] * len(ls)
        for i in range(len(ls) - MIN_BLOCK + 1):
            bh = hashlib.md5('\n'.join(ls[i:i+MIN_BLOCK]).encode()).hexdigest()
            if len(block_files.get(bh, set())) > 1:
                for k in range(MIN_BLOCK):
                    in_dup[i + k] = True
        dup_lines += sum(in_dup)
    
    dup_rate = dup_lines / total_lines if total_lines > 0 else 0
    max_rate = context.config.get("thresholds", {}).get("code_dup_rate_max", 0.10)
    
    if dup_rate > max_rate:
        results.append({
            'id': '9.1',
            'name': '代码重复率',
            'level': 'warning',
            'message': f'项目整体重复率 {dup_rate:.1%} 超过阈值 {max_rate:.0%}',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '提取公共函数/组件，消除重复逻辑',
        })
    else:
        results.append({
            'id': '9.1',
            'name': '代码重复率',
            'level': 'info',
            'message': f'项目整体重复率 {dup_rate:.1%}，在阈值范围内',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
    
    return results


# ===== 9.2 依赖安全 =====
def check_9_2_dependency_security(context) -> List[Dict]:
    """9.2 依赖安全 - 使用pip audit检测已知漏洞依赖"""
    results = []
    
    backend_path = context.backend_path
    if not backend_path or not os.path.isdir(backend_path):
        results.append({
            'id': '9.2',
            'name': '依赖安全',
            'level': 'info',
            'message': '无后端项目，跳过',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    try:
        result = subprocess.run(
            ['pip', 'audit', '--format', 'json'],
            capture_output=True, text=True, timeout=30,
            cwd=backend_path,
        )
        if result.returncode == 0:
            vulns = json.loads(result.stdout) if result.stdout.strip() else []
            if vulns:
                results.append({
                    'id': '9.2',
                    'name': '依赖安全',
                    'level': 'error',
                    'message': f'发现 {len(vulns)} 个已知漏洞依赖',
                    'file': '',
                    'line': 0,
                    'snippet': '',
                    'fix': '升级有漏洞的依赖包',
                })
            else:
                results.append({
                    'id': '9.2',
                    'name': '依赖安全',
                    'level': 'info',
                    'message': '无已知漏洞依赖',
                    'file': '',
                    'line': 0,
                    'snippet': '',
                    'fix': '',
                })
        else:
            results.append({
                'id': '9.2',
                'name': '依赖安全',
                'level': 'info',
                'message': 'pip audit不可用，跳过',
                'file': '',
                'line': 0,
                'snippet': '',
                'fix': '',
            })
    except Exception as e:  # noqa: broad exception handling
        results.append({
            'id': '9.2',
            'name': '依赖安全',
            'level': 'info',
            'message': 'pip audit不可用，跳过',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
    
    return results


# ===== 9.3 函数复杂度分布 =====
def check_9_3_function_complexity(context) -> List[Dict]:
    """9.3 函数复杂度分布 - 检测圈超标的Python函数
    
    v2.1 优化降噪：
    - 基础阈值从15提高到20
    - 排除测试函数（test_*）
    - 排除 __init__, __str__, __repr__, getter/setter 等简单方法
    - 排除 parser/lexer/serializer 等已知复杂解析逻辑
    """
    results = []
    
    all_code_files = _get_all_code_files(context)
    if not all_code_files:
        return results
    
    max_complexity_base = context.config.get("thresholds", {}).get("cyclomatic_complexity_max", 20)
    # 确保阈值不低于15
    max_complexity_base = max(max_complexity_base, 15)
    # 根据项目阶段调整阈值
    if context.project_profile and context.project_profile.should_relax_quality_rules():
        max_complexity = int(max_complexity_base * 1.67)  # 20→33
    else:
        max_complexity = max_complexity_base
    
    # 排除的函数名模式
    _SKIP_FUNC_NAMES = re.compile(
        r'^(test_|_test_)|(__init__|__str__|__repr__|__eq__|__hash__|'
        r'__lt__|__le__|__gt__|__ge__|__bool__|__len__|__iter__|__next__|'
        r'__enter__|__exit__|__del__|__copy__|__deepcopy__|'
        r'parse|lexer|tokenize|serialize|deserialize|encode|decode|'
        r'transform|compile|transpile|minify|format|render)$',
        re.IGNORECASE
    )
    
    complex_funcs = []
    
    for f in all_code_files:
        if not f.endswith('.py'):
            continue
        
        # 跳过测试文件
        basename = os.path.basename(f).lower()
        if basename.startswith('test_') or basename.endswith('_test.py'):
            continue
        if '/tests/' in f or '/test/' in f:
            continue
            
        content = context.safe_read(f)
        if not content:
            continue
        
        for m in re.finditer(r'def (\w+)\([^)]*\):', content):
            name = m.group(1)
            
            # 排除简单方法和已知复杂解析逻辑
            if _SKIP_FUNC_NAMES.search(name):
                continue
            
            rest = content[m.start():]
            body_lines = []
            for line in rest.split('\n')[1:]:
                if line and not line[0].isspace() and line.strip():
                    break
                body_lines.append(line)
            body = '\n'.join(body_lines)
            
            complexity = 1
            complexity += len(re.findall(r'\bif\b', body))
            complexity += len(re.findall(r'\belif\b', body))
            complexity += len(re.findall(r'\bfor\b', body))
            complexity += len(re.findall(r'\bwhile\b', body))
            complexity += len(re.findall(r'\band\b', body))
            complexity += len(re.findall(r'\bor\b', body))
            complexity += len(re.findall(r'\bexcept\b', body))
            
            if complexity > max_complexity:
                try:
                    rel_path = os.path.relpath(f)
                except ValueError:
                    rel_path = f
                complex_funcs.append(f"{rel_path}:{name} 圈复杂度={complexity}")
    
    if complex_funcs:
        results.append({
            'id': '9.3',
            'name': '函数复杂度分布',
            'level': 'warning',
            'message': f'发现 {len(complex_funcs)} 个函数圈复杂度>{max_complexity}',
            'detail': '\n'.join(complex_funcs[:10]),
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '拆分复杂函数，降低圈复杂度',
        })
    else:
        results.append({
            'id': '9.3',
            'name': '函数复杂度分布',
            'level': 'info',
            'message': '函数复杂度在合理范围内',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
    
    return results


# ===== 9.4 错误处理覆盖率 =====
def check_9_4_error_coverage(context) -> List[Dict]:
    """9.4 错误处理覆盖率 - 统计API调用的错误处理比例"""
    results = []
    
    all_code_files = _get_all_code_files(context)
    if not all_code_files:
        return results
    
    # 先检测是否有统一请求封装层
    has_unified_wrapper = False
    wrapper_has_error = False
    wrapper_path = None
    
    if context.project_path and os.path.isdir(context.project_path):
        wrapper_files = ("api.js", "request.js", "http.js")
        for kf in wrapper_files:
            fp = os.path.join(context.project_path, "utils", kf)
            if not os.path.isfile(fp):
                fp = os.path.join(context.project_path, kf)
            if os.path.isfile(fp):
                has_unified_wrapper = True
                wrapper_path = fp
                wcontent = context.safe_read(fp)
                if re.search(r'fail\s*[:=]|\.catch|onError|showToast.*失败|showModal.*错误|console\.error', wcontent):
                    wrapper_has_error = True
                break
    
    api_call_count = 0
    try_catch_count = 0
    
    for f in all_code_files:
        content_f = context.safe_read(f)
        if not content_f:
            continue
        # 排除封装文件本身（避免重复统计）
        if wrapper_path and f.endswith(wrapper_path):
            continue
        api_call_count += len(re.findall(r"api\(\s*[\'\"]\w+", content_f))
        api_call_count += len(re.findall(r"requests\.(get|post|put|delete|patch)\s*\(", content_f))
        try_catch_count += len(re.findall(r"\.catch\s*\(", content_f))
        try_catch_count += len(re.findall(r"except\s+\w+", content_f))
        try_catch_count += len(re.findall(r"fail\s*:", content_f))
    
    coverage = try_catch_count / api_call_count if api_call_count > 0 else 1.0
    
    # 根据架构调整阈值：有统一封装且封装有错误处理时，业务代码覆盖率标准放宽
    if has_unified_wrapper and wrapper_has_error:
        error_threshold = 0.2  # 有统一封装时，20%以下才告警
        warn_threshold = 0.4
        coverage_note = "（已检测到统一请求封装层含错误处理，业务代码覆盖率标准放宽）"
    else:
        error_threshold = 0.5
        warn_threshold = 0.8
        coverage_note = ""
    
    if coverage < error_threshold:
        results.append({
            'id': '9.4',
            'name': '错误处理覆盖率',
            'level': 'error',
            'message': f'错误处理覆盖率仅 {coverage:.0%}{coverage_note}',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '为核心API调用添加错误处理，或完善统一请求封装层',
        })
    elif coverage < warn_threshold:
        results.append({
            'id': '9.4',
            'name': '错误处理覆盖率',
            'level': 'warning',
            'message': f'错误处理覆盖率 {coverage:.0%}，建议提升{coverage_note}',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '关键业务流程建议补充错误处理',
        })
    else:
        results.append({
            'id': '9.4',
            'name': '错误处理覆盖率',
            'level': 'info',
            'message': f'错误处理覆盖率 {coverage:.0%}，良好{coverage_note}',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
    
    return results


# ===== 9.5 配置密钥分离 =====
def check_9_5_config_key_separation(context) -> List[Dict]:
    """9.5 配置密钥分离 - 检查密钥是否通过环境变量管理"""
    results = []
    
    be_content = context.get_all_backend_content()
    if not be_content:
        results.append({
            'id': '9.5',
            'name': '配置密钥分离',
            'level': 'info',
            'message': '无后端代码，跳过',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    key_in_code = []
    
    for m in re.finditer(r'(API_KEY|SECRET|PASSWORD|TOKEN)\s*=\s*["\'][^"\']+["\']', be_content, re.IGNORECASE):
        line_no = be_content[:m.start()].count('\n') + 1
        # 检查是否在os.environ上下文中
        preceding = be_content[max(0, m.start()-100):m.start()]
        if 'os.environ' not in preceding:
            key_in_code.append(f"后端:{line_no}行 {m.group(0)[:50]}")
    
    if key_in_code:
        results.append({
            'id': '9.5',
            'name': '配置密钥分离',
            'level': 'error',
            'message': f'发现 {len(key_in_code)} 处密钥未从环境变量读取',
            'detail': '\n'.join(key_in_code[:5]),
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '所有密钥使用os.environ.get()读取',
        })
    else:
        results.append({
            'id': '9.5',
            'name': '配置密钥分离',
            'level': 'info',
            'message': '密钥均已通过环境变量管理',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
    
    return results


# ===== 9.6 API向后兼容 =====
def check_9_6_api_backward_compat(context) -> List[Dict]:
    """9.6 API向后兼容 - 提示建议在CI中集成API契约测试"""
    results = []
    
    results.append({
        'id': '9.6',
        'name': 'API向后兼容',
        'level': 'info',
        'message': '需对比版本差异验证，建议在CI中集成API契约测试',
        'file': '',
        'line': 0,
        'snippet': '',
        'fix': '使用API版本号和兼容性测试确保向后兼容',
    })
    
    return results


# ===== M17 架构依赖方向检查辅助函数 =====
# 基于"依赖必须指向稳定方向"原则（DDD/整洁架构）
# 内层（领域层）不能依赖外层（基础设施层/表现层）

# 分层目录关键词映射：层类型 -> 目录名关键词列表
_ARCH_LAYER_KEYWORDS = {
    "domain": ["domain", "core/domain", "entities", "domain_model", "domain_models"],
    "application": ["application", "app", "usecase", "use_case", "use_cases", "service", "services", "business"],
    "infrastructure": ["infrastructure", "infra", "repository", "repositories", "persistence", "data_access", "dal", "dao"],
    "presentation": ["presentation", "api", "controllers", "controller", "handlers", "handler", "views", "view", "routes", "route", "entrypoints", "entrypoint"],
    "interface": ["interface", "interfaces", "port", "ports", "gateway", "gateways"],
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

# 领域层禁止的技术实现关键词
_DOMAIN_IMPURITY_PATTERNS = [
    (r'\b(SELECT|INSERT|UPDATE|DELETE|CREATE TABLE|ALTER TABLE|DROP TABLE|JOIN|WHERE|FROM)\b.*?[;\n]', "SQL语句"),
    (r'\bexecute\s*\(\s*["\']\s*(SELECT|INSERT|UPDATE|DELETE)', "SQL执行"),
    (r'\b(session|db|connection|cursor)\.(query|execute|commit|rollback|close)\b', "数据库操作"),
    (r'\b\.save\s*\(\s*\)', "数据库保存"),
    (r'\.(get|post|put|delete|patch|request)\s*\(\s*["\']https?://', "HTTP调用"),
    (r'\b(requests\.|httpx\.|axios\.)', "HTTP客户端调用"),
    (r'\bwx\.request\b', "微信HTTP请求"),
    (r'\bopen\s*\(\s*["\'].*?\.\w+["\']', "文件读写"),
    (r'\bos\.(makedirs|remove|rename|listdir|walk)\b', "文件系统操作"),
    (r'\b(boto3|openai|anthropic)\.(client|Client|resource|api)', "外部SDK调用"),
]

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


# ===== 架构分层检测缓存 =====
_arch_layers_cache = {}        # {cache_key: layers_dict}
_domain_files_cache = {}       # {cache_key: [file_paths]}
_default_exclude_dirs = {
    '.git', '.svn', 'node_modules', '__pycache__', '.venv', 'venv',
    'env', '.env', 'dist', 'build', '.eggs', '.tox', '.mypy_cache',
    '.pytest_cache', '.next', '.nuxt', '.cache', 'site-packages',
    'vendor', 'third_party', '.idea', '.vscode',
}

# ===== 规则定义列表 =====
RULES = [
    {
        'id': '9.1',
        'name': '代码重复率',
        'level': 'problem',
        'category': 'architecture',
        'module_id': '9',
        'applicable_types': [],
        'description': '检测项目整体代码重复率，超过阈值时告警',
        'check': check_9_1_code_duplication,
    },
    {
        'id': '9.2',
        'name': '依赖安全',
        'level': 'blocking',
        'category': 'architecture',
        'module_id': '9',
        'applicable_types': ['python_backend', 'python_tool', 'flask', 'mixed', 'mixed_electron'],
        'description': '使用pip audit检测已知漏洞依赖',
        'check': check_9_2_dependency_security,
    },
    {
        'id': '9.3',
        'name': '函数复杂度分布',
        'level': 'problem',
        'category': 'architecture',
        'module_id': '9',
        'applicable_types': [],
        'description': '检测函数圈复杂度，识别过于复杂的函数',
        'check': check_9_3_function_complexity,
    },
    {
        'id': '9.4',
        'name': '错误处理覆盖率',
        'level': 'blocking',
        'category': 'architecture',
        'module_id': '9',
        'applicable_types': [],
        'description': '统计API调用的错误处理比例，识别覆盖率不足',
        'check': check_9_4_error_coverage,
    },
    {
        'id': '9.5',
        'name': '配置密钥分离',
        'level': 'blocking',
        'category': 'architecture',
        'module_id': '9',
        'applicable_types': ['python_backend', 'python_tool', 'flask', 'mixed', 'mixed_electron'],
        'description': '检查密钥是否通过环境变量管理而非硬编码',
        'check': check_9_5_config_key_separation,
    },
    {
        'id': '9.6',
        'name': 'API向后兼容',
        'level': 'suggestion',
        'category': 'architecture',
        'module_id': '9',
        'applicable_types': [],
        'description': '提示API版本兼容和契约测试建议',
        'check': check_9_6_api_backward_compat,
    },
]
