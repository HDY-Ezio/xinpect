"""
部署就绪规则集 (M7)
部署就绪检查 - 适用于所有项目类型
包含: 配置文件完整性、环境变量、依赖清单、.gitignore等7项检查
"""

import re
import os
import json
from typing import List, Dict, Any


# ===== 7.1 配置文件完整性 =====
def check_7_1_config_completeness(context) -> List[Dict]:
    """7.1 配置文件完整性 - 检查必要的配置文件是否存在"""
    results = []
    
    if not context.project_path and not context.backend_path:
        return results
    
    check_paths = []
    if context.project_path:
        check_paths.append(context.project_path)
    if context.backend_path and context.backend_path != context.project_path:
        check_paths.append(context.backend_path)
    
    # 根据项目类型检查必要的配置文件
    required_files = {
        'miniprogram': ['app.json', 'project.config.json'],
        'web': ['package.json'],
        'python_backend': ['requirements.txt', 'config.py'],
        'python_tool': ['requirements.txt'],  # 工具/框架不强制要求config.py
        'flask': ['requirements.txt', 'config.py'],
        'electron': ['package.json'],
        'skill': ['SKILL.md'],
        'mixed': ['package.json', 'requirements.txt'],
        'mixed_electron': ['package.json', 'requirements.txt'],
    }
    
    needed = required_files.get(context.project_type, ['package.json' if context.project_path else 'requirements.txt'])
    
    missing_files = []
    for check_path in check_paths:
        for fname in needed:
            fpath = os.path.join(check_path, fname)
            if not os.path.isfile(fpath):
                # 检查是否在子目录中
                found = False
                for root, dirs, files in os.walk(check_path):
                    if fname in files:
                        found = True
                        break
                    # 限制深度
                    if root.count(os.sep) - check_path.count(os.sep) > 3:
                        break
                if not found:
                    missing_files.append(fname)
    
    if missing_files:
        results.append({
            'id': '7.1',
            'name': '配置文件完整性',
            'level': 'error',
            'message': f'缺少必要配置文件: {", ".join(missing_files)}',
            'file': '',
            'line': 0,
            'fix': '创建缺失的配置文件，确保项目结构完整',
        })
    
    return results


# ===== 7.2 .gitignore完整性 =====
def check_7_2_gitignore(context) -> List[Dict]:
    """7.2 .gitignore完整性 - 检查.gitignore是否配置了必要的忽略项"""
    results = []
    
    # 查找.gitignore文件
    gitignore_path = None
    for check_path in [context.project_path, context.backend_path]:
        if check_path:
            candidate = os.path.join(check_path, '.gitignore')
            if os.path.isfile(candidate):
                gitignore_path = candidate
                break
    
    if not gitignore_path:
        results.append({
            'id': '7.2',
            'name': '.gitignore完整性',
            'level': 'error',
            'message': '未找到.gitignore文件',
            'file': '',
            'line': 0,
            'fix': '创建.gitignore文件，忽略敏感文件和临时文件',
        })
        return results
    
    content = context.safe_read(gitignore_path)
    
    # 检查必要的忽略项
    required_patterns = {
        'node_modules': 'node_modules依赖',
        '__pycache__': 'Python缓存',
        '.env': '环境变量文件',
        '.DS_Store': 'macOS系统文件',
        '*.log': '日志文件',
        '.idea/': 'IDE配置',
        '.vscode/': 'VSCode配置',
    }
    
    missing = []
    for pattern, desc in required_patterns.items():
        if pattern not in content:
            missing.append(f'{pattern}({desc})')
    
    if missing:
        results.append({
            'id': '7.2',
            'name': '.gitignore完整性',
            'level': 'warning',
            'message': f'.gitignore缺少 {len(missing)} 项推荐忽略规则',
            'detail': '缺少: ' + ', '.join(missing[:5]),
            'file': gitignore_path,
            'line': 0,
            'fix': '在.gitignore中添加缺失的忽略项',
        })
    
    return results


# ===== 7.3 部署脚本检查 =====
def check_7_3_deploy_script(context) -> List[Dict]:
    """7.3 部署脚本检查 - 检查是否有部署相关脚本"""
    results = []
    
    check_paths = []
    if context.project_path:
        check_paths.append(context.project_path)
    if context.backend_path:
        check_paths.append(context.backend_path)
    
    deploy_patterns = [
        'Dockerfile',
        'docker-compose.yml',
        'deploy.sh',
        'Jenkinsfile',
        '.github/workflows',
        '.gitlab-ci.yml',
        'Makefile',
    ]
    
    has_deploy = False
    for check_path in check_paths:
        if not os.path.isdir(check_path):
            continue
        for pattern in deploy_patterns:
            if os.path.exists(os.path.join(check_path, pattern)):
                has_deploy = True
                break
        if has_deploy:
            break
    
    if not has_deploy and context.project_type in ('python_backend', 'flask', 'web'):
        results.append({
            'id': '7.3',
            'name': '部署脚本检查',
            'level': 'warning',
            'message': '未检测到部署脚本或CI/CD配置',
            'file': '',
            'line': 0,
            'fix': '添加Dockerfile或CI/CD配置，实现自动化部署',
        })
    
    return results


# ===== 7.4 README文档 =====
def check_7_4_readme(context) -> List[Dict]:
    """7.4 README文档 - 检查项目是否有README文档"""
    results = []
    
    check_paths = []
    if context.project_path:
        check_paths.append(context.project_path)
    if context.backend_path:
        check_paths.append(context.backend_path)
    
    has_readme = False
    readme_path = ''
    for check_path in check_paths:
        if not os.path.isdir(check_path):
            continue
        for fname in ['README.md', 'README.txt', 'README']:
            candidate = os.path.join(check_path, fname)
            if os.path.isfile(candidate):
                has_readme = True
                readme_path = candidate
                break
        if has_readme:
            break
    
    if not has_readme:
        results.append({
            'id': '7.4',
            'name': 'README文档',
            'level': 'warning',
            'message': '项目缺少README文档',
            'file': '',
            'line': 0,
            'fix': '创建README.md，包含项目介绍、安装方法、使用说明等',
        })
    else:
        # 检查README内容是否完整
        content = context.safe_read(readme_path)
        if len(content) < 200:
            results.append({
                'id': '7.4',
                'name': 'README文档',
                'level': 'info',
                'message': 'README内容较少，建议补充项目说明',
                'file': readme_path,
                'line': 0,
                'fix': '完善README文档内容',
            })
    
    return results


# ===== 7.5 环境变量完整性 =====
def check_7_5_env_vars(context) -> List[Dict]:
    """7.5 环境变量完整性 - 检查环境变量示例文件"""
    results = []
    
    check_paths = []
    if context.project_path:
        check_paths.append(context.project_path)
    if context.backend_path:
        check_paths.append(context.backend_path)
    
    has_env_example = False
    has_env_file = False
    
    for check_path in check_paths:
        if not os.path.isdir(check_path):
            continue
        if os.path.isfile(os.path.join(check_path, '.env.example')) or \
           os.path.isfile(os.path.join(check_path, '.env.template')) or \
           os.path.isfile(os.path.join(check_path, 'env.example')):
            has_env_example = True
        if os.path.isfile(os.path.join(check_path, '.env')):
            has_env_file = True
    
    if has_env_file and not has_env_example:
        results.append({
            'id': '7.5',
            'name': '环境变量完整性',
            'level': 'warning',
            'message': '有.env文件但缺少.env.example示例文件',
            'file': '',
            'line': 0,
            'fix': '创建.env.example文件，列出所有需要的环境变量（不含真实值）',
        })
    
    return results


# ===== 7.6 依赖安装检查 =====
def check_7_6_dependencies(context) -> List[Dict]:
    """7.6 依赖安装检查 - 检查依赖清单是否存在且非空
    
    v1.23.0 FP-04: 微信小程序项目跳过requirements.txt检查，
    小程序项目的依赖通过package.json管理（根目录或cloudfunctions目录）。
    """
    results = []
    
    # v1.23.0: 微信小程序项目不检查Python依赖
    is_miniprogram = getattr(context, 'project_type', '') == 'miniprogram'
    
    # 检查Python依赖（小程序项目跳过）
    py_files = context.find_files([".py"])
    if py_files and not is_miniprogram:
        has_requirements = False
        for check_path in [context.backend_path, context.project_path]:
            if check_path and os.path.isdir(check_path):
                if os.path.isfile(os.path.join(check_path, 'requirements.txt')) or \
                   os.path.isfile(os.path.join(check_path, 'pyproject.toml')) or \
                   os.path.isfile(os.path.join(check_path, 'Pipfile')):
                    has_requirements = True
                    break
        
        if not has_requirements and len(py_files) > 3:
            results.append({
                'id': '7.6',
                'name': '依赖安装检查',
                'level': 'warning',
                'message': 'Python项目缺少依赖清单文件(requirements.txt/pyproject.toml)',
                'file': '',
                'line': 0,
                'fix': '创建requirements.txt或pyproject.toml，列出所有依赖',
            })
    
    # 检查JS依赖
    js_files = context.find_files([".js", ".ts", ".tsx", ".jsx"])
    if js_files:
        has_package_json = False
        for check_path in [context.project_path, context.backend_path]:
            if check_path and os.path.isdir(check_path):
                if os.path.isfile(os.path.join(check_path, 'package.json')):
                    has_package_json = True
                    break
        
        if not has_package_json and len(js_files) > 5:
            results.append({
                'id': '7.6',
                'name': '依赖安装检查',
                'level': 'warning',
                'message': '前端项目缺少package.json依赖清单',
                'file': '',
                'line': 0,
                'fix': '创建package.json，管理项目依赖',
            })
    
    return results


# ===== 7.7 占位符/测试地址检测 =====
def check_7_7_placeholder_detection(context) -> List[Dict]:
    """7.7 占位符/测试地址检测 - 检查代码中是否存在占位符或测试地址"""
    results = []
    
    scan_exts = [".js"]
    if context.project_type in ("web", "mixed", "electron", "mixed_electron"):
        scan_exts.extend([".ts", ".tsx"])
    elif context.project_type in ("python_backend", "flask", "python_tool"):
        scan_exts = [".py"]
    
    js_files = context.find_files(scan_exts)
    # 也扫描后端py文件
    if context.backend_path and os.path.isdir(context.backend_path):
        js_files += context.find_files([".py"])
    
    # 排除配置文件和测试文件
    placeholder_skip_files = [
        '.env', '.env.example', '.env.local', '.env.development',
        'config.py', 'settings.py', 'config.json', 'qa_config.json'
    ]
    placeholder_skip_patterns = [
        'test_', '_test.py', 'test/', 'tests/', 'test_core_api'
    ]
    
    filtered_files = []
    for f in js_files:
        basename = os.path.basename(f)
        if basename in placeholder_skip_files:
            continue
        skip = False
        for pat in placeholder_skip_patterns:
            if pat in f:
                skip = True
                break
        if skip:
            continue
        filtered_files.append(f)
    
    placeholders = []
    for f in filtered_files:
        content = context.safe_read(f)
        if not content:
            continue
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('#'):
                continue
            if not re.search(r'wx0000000000000000|localhost|127\.0\.0\.1|0\.0\.0\.0|test_key|example\.com|hardcoded.*key|YOUR_API_KEY|REPLACE_ME', line, re.IGNORECASE):
                continue
            
            # wx0000占位符仅对小程序项目报告
            if re.search(r'wx0000000000000000', line) and context.project_type not in ("miniprogram", "mixed"):
                continue
            # 排除占位符UI文本
            if re.search(r'placeholderText|placeholder\s*[:=]|notePlaceholder', line):
                continue
            # 排除正则检测模式本身
            if re.search(r're\.(search|compile|match|finditer)\s*\(', line):
                continue
            # 排除多行正则模式续行
            if re.match(r"\s*r['\"]", line) and '|' in line:
                continue
            # 排除测试header值
            if re.search(r'headers\s*=\s*\{.*Origin.*localhost', line):
                continue
            # 排除比较/安全检查上下文
            if re.search(r'==\s*["\'].*(?:wx0000000000000000|0\.0\.0\.0)', line) or re.search(r'!=\s*["\'].*(?:wx0000000000000000|0\.0\.0\.0)', line):
                continue
            # 排除0.0.0.0作为IP fallback/default
            if re.search(r'"0\.0\.0\.0"', line) and re.search(r'get\(|default|fallback|or\s+["\']0\.0\.0\.0', line, re.IGNORECASE):
                continue
            # 排除IP安全校验
            if re.search(r'ip\s*(==|!=)\s*["\']0\.0\.0\.0', line, re.IGNORECASE):
                continue
            # 排除dev mode逻辑
            if re.search(r'isDevMode|is_dev_mode|dev_mode', line, re.IGNORECASE):
                continue
            # 排除os.environ.get / os.getenv默认值
            if re.search(r'os\.environ\.get\s*\(', line) or re.search(r'os\.getenv\s*\(', line):
                continue
            # 排除服务启动模式
            if re.search(r'app\.run\s*\(|server\.listen\s*\(|host\s*=\s*["\']0\.0\.0\.0["\']', line):
                continue
            # 排除安全/黑名单模式
            sec_pattern_vars = re.search(r'(SAFE_DOMAIN|BLACKLIST|PRIVATE|PATTERN|FORBIDDEN|BLOCKED|ALLOWED|WHITELIST)', line[:80], re.IGNORECASE)
            if sec_pattern_vars or ('ssrf' in line.lower()):
                continue
            # 排除列表中的正则模式元素
            stripped_indented = stripped.startswith("r'") or stripped.startswith('r"')
            has_ip_pattern = 'localhost' in line or '127.' in line or '192.168' in line or '0.0.0.0' in line
            if stripped_indented and has_ip_pattern:
                continue
            
            try:
                rel_path = os.path.relpath(f)
            except ValueError:
                rel_path = f
            placeholders.append(f"{rel_path}:{i} {line.strip()[:60]}")
    
    if placeholders:
        results.append({
            'id': '7.7',
            'name': '占位符/测试地址检测',
            'level': 'error',
            'message': f"发现 {len(placeholders)} 处疑似占位符/测试地址",
            'detail': '\n'.join(placeholders[:10]),
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '替换为生产环境变量，使用配置文件管理',
        })
    
    return results


# ===== 7.8 调试模式关闭 =====
def check_7_8_debug_mode(context) -> List[Dict]:
    """7.8 调试模式关闭 - 检查生产环境调试模式是否关闭"""
    results = []
    debug_mode = []
    
    project_path = context.project_path
    if not project_path or not os.path.isdir(project_path):
        return results
    
    # 小程序: 检查app.js和app.json
    if context.project_type in ("miniprogram", "mixed"):
        app_js = os.path.join(project_path, "app.js")
        if os.path.isfile(app_js):
            content = context.safe_read(app_js)
            if re.search(r'debug\s*:\s*true', content, re.IGNORECASE):
                debug_mode.append("app.js中debug模式开启")
        app_json = os.path.join(project_path, "app.json")
        if os.path.isfile(app_json):
            try:
                aj = json.loads(context.safe_read(app_json))
                if aj.get("debug", False):
                    debug_mode.append("app.json中debug=true")
            except Exception as e:  # noqa: broad exception handling
                pass
    
    # Web/Electron: 检查next.config和env
    if context.project_type in ("web", "mixed", "electron", "mixed_electron"):
        for nc in ("next.config.js", "next.config.ts", "next.config.mjs"):
            ncp = os.path.join(project_path, nc)
            if os.path.isfile(ncp):
                content = context.safe_read(ncp)
                if re.search(r'devIndicators|buildActivity\b', content):
                    debug_mode.append(f"{nc}中开发指示器开启")
                break
        
        env_files = [".env", ".env.local", ".env.development"]
        for ef in env_files:
            efp = os.path.join(project_path, ef)
            if os.path.isfile(efp):
                content = context.safe_read(efp)
                if re.search(r'NODE_ENV\s*=\s*development', content):
                    debug_mode.append(f"{ef}中NODE_ENV=development")
        
        # Electron: 检查devTools
        if context.project_type in ("electron", "mixed_electron"):
            all_js = context.find_files([".js", ".ts"])
            for jf in all_js:
                content = context.safe_read(jf)
                basename = os.path.basename(jf)
                if basename in ("main.js", "main.ts", "electron.js", "electron.ts", "preload.js", "preload.ts"):
                    if re.search(r'webPreferences.*devTools\s*:\s*true|openDevTools\(\)', content):
                        debug_mode.append(f"{basename}中开发工具(devTools)开启")
    
    if debug_mode:
        results.append({
            'id': '7.8',
            'name': '调试模式关闭',
            'level': 'warning',
            'message': f"发现 {len(debug_mode)} 处调试模式未关闭",
            'detail': '\n'.join(debug_mode),
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '生产环境关闭debug模式',
        })
    
    return results


# ===== 7.9 版本号一致性 =====
def check_7_9_version_consistency(context) -> List[Dict]:
    """7.9 版本号一致性 - 检查不同配置文件中版本号是否一致"""
    results = []
    
    project_path = context.project_path
    if not project_path or not os.path.isdir(project_path):
        return results
    
    version_mismatch = []
    app_ver = None
    pkg_ver = None
    
    app_json = os.path.join(project_path, "app.json")
    if os.path.isfile(app_json):
        try:
            aj = json.loads(context.safe_read(app_json))
            app_ver = aj.get("version")
        except Exception as e:  # noqa: broad exception handling
            pass
    
    package_json_path = os.path.join(project_path, "package.json")
    if os.path.isfile(package_json_path):
        try:
            pj = json.loads(context.safe_read(package_json_path))
            pkg_ver = pj.get("version")
        except Exception as e:  # noqa: broad exception handling
            pass
    
    if app_ver and pkg_ver and app_ver != pkg_ver:
        version_mismatch.append(f"app.json={app_ver} vs package.json={pkg_ver}")
    
    if version_mismatch:
        results.append({
            'id': '7.9',
            'name': '版本号一致性',
            'level': 'warning',
            'message': '版本号不一致',
            'detail': '\n'.join(version_mismatch),
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '统一app.json和package.json版本号',
        })
    
    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': '7.1',
        'name': '配置文件完整性',
        'level': 'blocking',
        'category': 'deploy',
        'module_id': '7',
        'applicable_types': [],
        'description': '检查项目必要的配置文件是否存在',
        'check': check_7_1_config_completeness,
    },
    {
        'id': '7.2',
        'name': '.gitignore完整性',
        'level': 'problem',
        'category': 'deploy',
        'module_id': '7',
        'applicable_types': [],
        'description': '检查.gitignore是否配置了必要的忽略项',
        'check': check_7_2_gitignore,
    },
    {
        'id': '7.3',
        'name': '部署脚本检查',
        'level': 'suggestion',
        'category': 'deploy',
        'module_id': '7',
        'applicable_types': ['python_backend', 'flask', 'web', 'mixed'],
        'description': '检查是否有部署脚本或CI/CD配置',
        'check': check_7_3_deploy_script,
    },
    {
        'id': '7.4',
        'name': 'README文档',
        'level': 'suggestion',
        'category': 'deploy',
        'module_id': '7',
        'applicable_types': [],
        'description': '检查项目是否有完善的README文档',
        'check': check_7_4_readme,
    },
    {
        'id': '7.5',
        'name': '环境变量完整性',
        'level': 'problem',
        'category': 'deploy',
        'module_id': '7',
        'applicable_types': [],
        'description': '检查环境变量示例文件是否存在',
        'check': check_7_5_env_vars,
    },
    {
        'id': '7.6',
        'name': '依赖安装检查',
        'level': 'problem',
        'category': 'deploy',
        'module_id': '7',
        'applicable_types': [],
        'description': '检查依赖清单是否存在且非空',
        'check': check_7_6_dependencies,
    },
    {
        'id': '7.7',
        'name': '占位符/测试地址检测',
        'level': 'blocking',
        'category': 'deploy',
        'module_id': '7',
        'applicable_types': [],
        'description': '检查代码中是否存在占位符或测试地址（localhost/硬编码key等）',
        'check': check_7_7_placeholder_detection,
    },
    {
        'id': '7.8',
        'name': '调试模式关闭',
        'level': 'problem',
        'category': 'deploy',
        'module_id': '7',
        'applicable_types': ['miniprogram', 'web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查生产环境调试模式是否关闭（debug/devTools/devIndicators）',
        'check': check_7_8_debug_mode,
    },
    {
        'id': '7.9',
        'name': '版本号一致性',
        'level': 'problem',
        'category': 'deploy',
        'module_id': '7',
        'applicable_types': ['miniprogram', 'mixed'],
        'description': '检查app.json和package.json中的版本号是否一致',
        'check': check_7_9_version_consistency,
    },
]
