"""
Git Diff增量审查规则集 (M15)
Git增量审查 - 适用于所有项目类型
包含: 变更文件提取、变更影响分析、增量安全扫描、增量API一致性、
增量前端影响、变更摘要生成等6项检查
注意：需在git仓库目录下运行，且需配置--mode diff启用
"""

import re
import os
import subprocess
from typing import List, Dict, Any
from collections import defaultdict


# ===== 工具函数 =====
def _find_git_root(context) -> str:
    """查找git仓库根目录"""
    search_paths = []
    if context.project_path and os.path.isdir(context.project_path):
        search_paths.append(context.project_path)
    if context.backend_path and os.path.isdir(context.backend_path):
        search_paths.append(context.backend_path)
    
    for sp in search_paths:
        if os.path.isdir(os.path.join(sp, ".git")):
            return sp
        # 检查父目录
        cur = sp
        for _ in range(5):
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            if os.path.isdir(os.path.join(parent, ".git")):
                return parent
            cur = parent
    
    return ""


def _get_changed_files(git_root: str, base_branch: str) -> tuple:
    """获取变更文件列表和diff内容"""
    changed_files = []
    diff_content = ""
    added = []
    modified = []
    deleted = []
    renamed = []
    
    try:
        # 获取变更文件列表
        result = subprocess.run(
            ['git', 'diff', '--name-status', f'{base_branch}...HEAD'],
            capture_output=True, text=True, timeout=30, cwd=git_root
        )
        if result.returncode != 0:
            result = subprocess.run(
                ['git', 'diff', '--name-status', f'{base_branch}', 'HEAD'],
                capture_output=True, text=True, timeout=30, cwd=git_root
            )
        
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if not line.strip():
                    continue
                parts = line.split('\t')
                status = parts[0][0] if parts else '?'
                filepath = parts[-1] if len(parts) >= 2 else ""
                full_path = os.path.join(git_root, filepath) if filepath else ""
                
                if status == 'A':
                    added.append(filepath)
                elif status == 'M':
                    modified.append(filepath)
                elif status == 'D':
                    deleted.append(filepath)
                elif status == 'R':
                    renamed.append(filepath)
                
                if full_path and os.path.isfile(full_path):
                    changed_files.append(full_path)
            
            # 获取diff内容
            diff_result = subprocess.run(
                ['git', 'diff', f'{base_branch}...HEAD', '--no-color'],
                capture_output=True, text=True, timeout=60, cwd=git_root
            )
            if diff_result.returncode == 0:
                diff_content = diff_result.stdout
    
    except (subprocess.TimeoutExpired, FileNotFoundError):  # noqa: intentional empty handler
        pass
    
    return changed_files, diff_content, added, modified, deleted, renamed


# ===== 15.1 变更文件提取 =====
def check_15_1_extract_diff(context) -> List[Dict]:
    """15.1 变更文件提取：从git diff获取变更文件列表"""
    results = []
    
    mode = context.config.get("diff_mode", "full")
    if mode != "diff":
        results.append({
            'id': '15.1',
            'name': '变更文件提取',
            'level': 'suggestion',
            'message': '非diff模式，跳过增量审查',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    git_root = _find_git_root(context)
    if not git_root:
        results.append({
            'id': '15.1',
            'name': '变更文件提取',
            'level': 'problem',
            'message': '当前目录不是git仓库，无法执行增量审查',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '在git仓库目录中运行，或使用--mode full全量扫描',
        })
        return results
    
    base_branch = context.config.get("base_branch", "main")
    changed_files, diff_content, added, modified, deleted, renamed = _get_changed_files(
        git_root, base_branch)
    
    if not changed_files:
        results.append({
            'id': '15.1',
            'name': '变更文件提取',
            'level': 'suggestion',
            'message': f'与基准分支({base_branch})无差异',
            'file': '',
            'line': 0,
            'snippet': '当前分支与基准分支代码一致，无需增量审查',
            'fix': '',
        })
        return results
    
    detail_parts = []
    if added:
        detail_parts.append(f"新增({len(added)}): " + ", ".join(added[:10]))
    if modified:
        detail_parts.append(f"修改({len(modified)}): " + ", ".join(modified[:10]))
    if deleted:
        detail_parts.append(f"删除({len(deleted)}): " + ", ".join(deleted[:10]))
    if renamed:
        detail_parts.append(f"重命名({len(renamed)}): " + ", ".join(renamed[:10]))
    
    results.append({
        'id': '15.1',
        'name': '变更文件提取',
        'level': 'suggestion',
        'message': f'检测到{len(changed_files)}个变更文件(vs {base_branch})',
        'file': '',
        'line': 0,
        'snippet': '\n'.join(detail_parts),
        'fix': '',
    })
    
    return results


# ===== 15.2 变更影响分析 =====
def check_15_2_impact_analysis(context) -> List[Dict]:
    """15.2 变更影响分析：分析变更文件影响哪些模块"""
    results = []
    
    mode = context.config.get("diff_mode", "full")
    if mode != "diff":
        results.append({
            'id': '15.2',
            'name': '变更影响分析',
            'level': 'suggestion',
            'message': '非diff模式，跳过',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    git_root = _find_git_root(context)
    if not git_root:
        results.append({
            'id': '15.2',
            'name': '变更影响分析',
            'level': 'suggestion',
            'message': '非git仓库，跳过',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    base_branch = context.config.get("base_branch", "main")
    changed_files, _, _, _, _, _ = _get_changed_files(git_root, base_branch)
    
    if not changed_files:
        results.append({
            'id': '15.2',
            'name': '变更影响分析',
            'level': 'suggestion',
            'message': '无变更文件，跳过',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    # 按文件后缀/路径匹配模块
    module_impact = defaultdict(list)
    for fpath in changed_files:
        basename = os.path.basename(fpath)
        ext = os.path.splitext(basename)[1].lower()
        rel_path = fpath
        
        # API相关文件
        if ext in ('.py',) and ('api' in rel_path.lower() or 'route' in rel_path.lower() or 'handler' in rel_path.lower()):
            module_impact["M1-API链路"].append(fpath)
            module_impact["M4-数据一致性"].append(fpath)
        # 安全相关
        if ext in ('.py', '.js', '.ts') and ('auth' in rel_path.lower() or 'login' in rel_path.lower() or 'token' in rel_path.lower() or 'security' in rel_path.lower()):
            module_impact["M3-安全审计"].append(fpath)
        # UI文件
        if ext in ('.wxml', '.wxss', '.css', '.scss', '.less', '.tsx', '.jsx'):
            module_impact["M5-UI设计"].append(fpath)
            module_impact["M12-性能资源"].append(fpath)
        # 配置文件
        if basename in ('app.json', 'project.config.json', 'package.json', 'config.py', 'settings.py', '.env', '.env.local'):
            module_impact["M7-部署就绪"].append(fpath)
        # 所有代码文件
        if ext in ('.py', '.js', '.ts', '.tsx', '.jsx', '.wxml'):
            module_impact["M6-代码质量"].append(fpath)
            module_impact["M13-错误处理"].append(fpath)
        # 测试文件
        if 'test' in basename.lower() or 'spec' in basename.lower():
            module_impact["M14-测试CI"].append(fpath)
        # 后端Python
        if ext == '.py' and 'api' not in rel_path.lower():
            module_impact["M9-架构健康"].append(fpath)
        # 导航相关
        if ext in ('.wxml', '.tsx', '.jsx') or basename == 'app.json':
            module_impact["M2-页面导航"].append(fpath)
    
    if module_impact:
        detail_lines = []
        for mod, files in sorted(module_impact.items()):
            detail_lines.append(f"{mod}: {len(files)}个文件")
        results.append({
            'id': '15.2',
            'name': '变更影响分析',
            'level': 'suggestion',
            'message': f'变更影响{len(module_impact)}个模块',
            'file': '',
            'line': 0,
            'snippet': '\n'.join(detail_lines),
            'fix': '',
        })
    else:
        results.append({
            'id': '15.2',
            'name': '变更影响分析',
            'level': 'suggestion',
            'message': '变更文件未匹配到特定模块影响',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
    
    return results


# ===== 15.3 增量安全扫描 =====
def check_15_3_security_scan(context) -> List[Dict]:
    """15.3 增量安全扫描：对变更文件执行安全相关检查"""
    results = []
    
    mode = context.config.get("diff_mode", "full")
    if mode != "diff":
        results.append({
            'id': '15.3',
            'name': '增量安全扫描',
            'level': 'suggestion',
            'message': '非diff模式，跳过',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    git_root = _find_git_root(context)
    if not git_root:
        results.append({
            'id': '15.3',
            'name': '增量安全扫描',
            'level': 'suggestion',
            'message': '非git仓库，跳过',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    base_branch = context.config.get("base_branch", "main")
    changed_files, _, _, _, _, _ = _get_changed_files(git_root, base_branch)
    
    if not changed_files:
        results.append({
            'id': '15.3',
            'name': '增量安全扫描',
            'level': 'suggestion',
            'message': '无变更文件，跳过',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    security_issues = []
    security_warnings = []
    
    # SQL注入模式
    sql_patterns = [
        (r'f["\'].*SELECT.*\{.*\}.*FROM|f["\'].*INSERT.*\{.*\}.*INTO|f["\'].*UPDATE.*\{.*\}.*SET',
         "SQL拼接风险(f-string)"),
        (r'%s.*SELECT|SELECT.*%s|%s.*INSERT|INSERT.*%s',
         "SQL拼接风险(%格式化)"),
    ]
    # XSS模式
    xss_patterns = [
        (r'v-html|dangerouslySetInnerHTML|innerHTML\s*=|\.html\s*\(',
         "潜在的XSS风险(HTML注入)"),
    ]
    # 硬编码密钥
    secret_patterns = [
        (r'(?:password|passwd|pwd|secret|token|api_key|apikey|access_key|secret_key)\s*=\s*["\'][^"\']{6,}["\']',
         "硬编码密钥/密码"),
    ]
    # 调试残留
    debug_patterns = [
        (r'debug\s*=\s*True|DEBUG\s*=\s*True|debugger|breakpoint\s*\(',
         "调试代码残留"),
    ]
    
    all_patterns = sql_patterns + xss_patterns + secret_patterns + debug_patterns
    
    for fpath in changed_files:
        if not os.path.isfile(fpath):
            continue
        ext = os.path.splitext(fpath)[1].lower()
        # 只扫描代码文件
        if ext not in ('.py', '.js', '.ts', '.tsx', '.jsx', '.wxml', '.wxss', '.html'):
            continue
        content = context.safe_read(fpath)
        if not content:
            continue
        try:
            rel_path = os.path.relpath(fpath)
        except ValueError:
            rel_path = fpath
        
        for pattern, desc in all_patterns:
            # 跳过不适用的文件类型
            if ext == '.py' and pattern in [p for p, _ in xss_patterns]:
                continue
            if ext not in ('.py',) and pattern in [p for p, _ in sql_patterns]:
                continue
            
            for m in re.finditer(pattern, content, re.IGNORECASE):
                line_num = content[:m.start()].count('\n') + 1
                line_text = content.split('\n')[line_num - 1].strip()[:80]
                # 跳过注释行
                if line_text.startswith('#') or line_text.startswith('//'):
                    continue
                # 跳过测试文件
                if 'test' in os.path.basename(fpath).lower():
                    continue
                # 检查是否从环境变量读取
                if desc == "硬编码密钥/密码":
                    ctx = content[max(0, m.start()-100):m.end()+50]
                    if 'os.environ' in ctx or 'os.getenv' in ctx or 'process.env' in ctx:
                        continue
                
                issue_entry = f"{rel_path}:{line_num} {desc}"
                security_issues.append(issue_entry)
                if "硬编码" in desc or "SQL拼接" in desc:
                    security_warnings.append(issue_entry)
                break  # 每个文件每个模式只报一次
    
    if security_warnings:
        results.append({
            'id': '15.3',
            'name': '增量安全扫描',
            'level': 'blocking',
            'message': f'发现{len(security_warnings)}个安全问题',
            'file': '',
            'line': 0,
            'snippet': '\n'.join(security_warnings[:15]),
            'fix': '修复安全漏洞：使用参数化查询、环境变量管理密钥、避免HTML注入',
        })
    elif security_issues:
        results.append({
            'id': '15.3',
            'name': '增量安全扫描',
            'level': 'problem',
            'message': f'发现{len(security_issues)}个潜在安全风险',
            'file': '',
            'line': 0,
            'snippet': '\n'.join(security_issues[:15]),
            'fix': '评估并处理安全风险',
        })
    else:
        results.append({
            'id': '15.3',
            'name': '增量安全扫描',
            'level': 'suggestion',
            'message': '变更文件未发现安全问题',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
    
    return results


# ===== 15.4 增量API一致性 =====
def check_15_4_api_consistency(context) -> List[Dict]:
    """15.4 增量API一致性：检查API路径/参数变更是否影响调用方"""
    results = []
    
    mode = context.config.get("diff_mode", "full")
    if mode != "diff":
        results.append({
            'id': '15.4',
            'name': '增量API一致性',
            'level': 'suggestion',
            'message': '非diff模式，跳过',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    git_root = _find_git_root(context)
    if not git_root:
        results.append({
            'id': '15.4',
            'name': '增量API一致性',
            'level': 'suggestion',
            'message': '非git仓库，跳过',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    base_branch = context.config.get("base_branch", "main")
    _, diff_content, _, _, _, _ = _get_changed_files(git_root, base_branch)
    
    if not diff_content:
        results.append({
            'id': '15.4',
            'name': '增量API一致性',
            'level': 'suggestion',
            'message': '无diff内容，跳过',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    api_changes = []
    
    # 查找API路径变更
    api_patterns = [
        (r'[-+].*["\']/(api/[\w/-]+)["\']', "API路径变更"),
        (r'[-+].*@(?:app\.route|router\.(?:get|post|put|delete|patch))\s*\(["\']([^"\']+)["\']', "Flask路由变更"),
        (r'[-+].*DOMAIN_ROUTES', "路由配置变更"),
    ]
    
    for pattern, desc in api_patterns:
        for m in re.finditer(pattern, diff_content):
            line = m.group(0).strip()[:100]
            prefix = line[0] if line else ''
            if prefix in ('+', '-'):
                api_changes.append(f"{desc}: {line[:80]}")
    
    # 检查函数签名变化
    sig_pattern = r'[-+]\s*def\s+(\w+)\s*\(([^)]*)\)'
    prev_sigs = {}
    curr_sigs = {}
    for m in re.finditer(sig_pattern, diff_content):
        func_name = m.group(1)
        params = m.group(2)
        line = m.group(0)
        if line.startswith('-'):
            prev_sigs[func_name] = params
        elif line.startswith('+'):
            curr_sigs[func_name] = params
    
    for func_name in set(prev_sigs.keys()) & set(curr_sigs.keys()):
        if prev_sigs[func_name] != curr_sigs[func_name]:
            api_changes.append(
                f"函数签名变更: {func_name}({prev_sigs[func_name][:50]} → {curr_sigs[func_name][:50]})")
    
    if api_changes:
        results.append({
            'id': '15.4',
            'name': '增量API一致性',
            'level': 'problem',
            'message': f'检测到{len(api_changes)}处API相关变更',
            'file': '',
            'line': 0,
            'snippet': '\n'.join(api_changes[:15]),
            'fix': '确认API变更不会破坏现有调用方，必要时更新API文档和前端调用',
        })
    else:
        results.append({
            'id': '15.4',
            'name': '增量API一致性',
            'level': 'suggestion',
            'message': '未检测到API路径/签名变更',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
    
    return results


# ===== 15.5 增量前端影响 =====
def check_15_5_frontend_impact(context) -> List[Dict]:
    """15.5 增量前端影响：检查API变更是否需要同步修改前端"""
    results = []
    
    mode = context.config.get("diff_mode", "full")
    if mode != "diff":
        results.append({
            'id': '15.5',
            'name': '增量前端影响',
            'level': 'suggestion',
            'message': '非diff模式，跳过',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    git_root = _find_git_root(context)
    if not git_root:
        results.append({
            'id': '15.5',
            'name': '增量前端影响',
            'level': 'suggestion',
            'message': '非git仓库，跳过',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    base_branch = context.config.get("base_branch", "main")
    changed_files, diff_content, _, _, _, _ = _get_changed_files(git_root, base_branch)
    
    if not changed_files:
        results.append({
            'id': '15.5',
            'name': '增量前端影响',
            'level': 'suggestion',
            'message': '无变更文件，跳过',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    frontend_impact = []
    
    # 检查后端API变更但无前端变更的情况
    backend_changed = [f for f in changed_files
                      if f.endswith('.py') and ('api' in f.lower() or 'route' in f.lower() or 'handler' in f.lower())]
    frontend_files = [f for f in changed_files
                     if f.endswith(('.js', '.ts', '.tsx', '.jsx', '.wxml', '.wxss'))]
    
    if backend_changed and not frontend_files:
        for bf in backend_changed:
            content = context.safe_read(bf)
            if content and re.search(r'DOMAIN_ROUTES|@app\.route|router\.(get|post)', content):
                try:
                    rel = os.path.relpath(bf)
                except ValueError:
                    rel = bf
                frontend_impact.append(f"后端API变更({rel})但无对应前端变更")
    
    # 检查响应格式变更
    if diff_content:
        response_changes = re.findall(r'[-+].*["\'](?:success|code|message|data|error)["\']\s*:', diff_content)
        if len(response_changes) > 2:
            frontend_impact.append(f"检测到{len(response_changes)}处响应格式变更，前端可能需要适配")
    
    # 检查枚举/常量变更
    if diff_content:
        enum_changes = re.findall(r'[-+].*(?:ENUM|STATUS|TYPE|PLAN|ROLE).*=', diff_content, re.IGNORECASE)
        if enum_changes:
            frontend_impact.append(f"检测到{len(enum_changes)}处枚举/常量变更，前端可能需要同步")
    
    if frontend_impact:
        results.append({
            'id': '15.5',
            'name': '增量前端影响',
            'level': 'problem',
            'message': f'发现{len(frontend_impact)}处前端可能需要同步修改',
            'file': '',
            'line': 0,
            'snippet': '\n'.join(frontend_impact[:10]),
            'fix': '同步修改前端代码以匹配后端变更',
        })
    else:
        results.append({
            'id': '15.5',
            'name': '增量前端影响',
            'level': 'suggestion',
            'message': '未检测到需要前端同步的变更',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
    
    return results


# ===== 15.6 变更摘要生成 =====
def check_15_6_summary(context) -> List[Dict]:
    """15.6 变更摘要生成：输出本次变更的问题摘要+风险评估"""
    results = []
    
    mode = context.config.get("diff_mode", "full")
    if mode != "diff":
        results.append({
            'id': '15.6',
            'name': '变更摘要生成',
            'level': 'suggestion',
            'message': '非diff模式，跳过',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    git_root = _find_git_root(context)
    if not git_root:
        results.append({
            'id': '15.6',
            'name': '变更摘要生成',
            'level': 'suggestion',
            'message': '非git仓库，跳过',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    base_branch = context.config.get("base_branch", "main")
    changed_files, _, _, _, _, _ = _get_changed_files(git_root, base_branch)
    
    # 汇总其他检查的结果（这里基于当前已知信息生成摘要）
    background = context.config.get("diff_background", "")
    
    summary_parts = [f"变更文件: {len(changed_files)}个"]
    if background:
        summary_parts.append(f"需求背景: {background[:100]}")
    
    results.append({
        'id': '15.6',
        'name': '变更摘要生成',
        'level': 'suggestion',
        'message': f'变更摘要: {len(changed_files)}个文件变更',
        'file': '',
        'line': 0,
        'snippet': '\n'.join(summary_parts),
        'fix': '按优先级修复阻断和警告问题',
    })
    
    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': '15.1',
        'name': '变更文件提取',
        'level': 'suggestion',
        'category': 'git_review',
        'module_id': '15',
        'applicable_types': [],
        'description': '从git diff获取变更文件列表，需配置diff_mode=diff启用',
        'check': check_15_1_extract_diff,
    },
    {
        'id': '15.2',
        'name': '变更影响分析',
        'level': 'suggestion',
        'category': 'git_review',
        'module_id': '15',
        'applicable_types': [],
        'description': '分析变更文件影响哪些QA模块',
        'check': check_15_2_impact_analysis,
    },
    {
        'id': '15.3',
        'name': '增量安全扫描',
        'level': 'blocking',
        'category': 'git_review',
        'module_id': '15',
        'applicable_types': [],
        'description': '对变更文件执行增量安全扫描，检测SQL注入、XSS、硬编码密钥等',
        'check': check_15_3_security_scan,
    },
    {
        'id': '15.4',
        'name': '增量API一致性',
        'level': 'problem',
        'category': 'git_review',
        'module_id': '15',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron'],
        'description': '检查API路径/参数变更是否影响调用方',
        'check': check_15_4_api_consistency,
    },
    {
        'id': '15.5',
        'name': '增量前端影响',
        'level': 'problem',
        'category': 'git_review',
        'module_id': '15',
        'applicable_types': ['miniprogram', 'web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查后端API变更是否需要同步修改前端代码',
        'check': check_15_5_frontend_impact,
    },
    {
        'id': '15.6',
        'name': '变更摘要生成',
        'level': 'suggestion',
        'category': 'git_review',
        'module_id': '15',
        'applicable_types': [],
        'description': '输出本次变更的问题摘要和风险评估',
        'check': check_15_6_summary,
    },
]
