"""
Git规范规则集 (v5.2.0)
检测Git工程规范问题 - 适用于所有项目类型
包含: .gitignore缺失、敏感文件提交、大文件入库、二进制文件、
合并冲突标记等5项检查
"""

import re
import os
from typing import List, Dict, Any


# ===== GIT-001 .gitignore缺失 =====
def check_git_001_gitignore(context) -> List[Dict]:
    """GIT-001 .gitignore缺失 - 项目无.gitignore"""
    results = []

    # Check if project has .gitignore
    search_paths = []
    if context.project_path and os.path.isdir(context.project_path):
        search_paths.append(context.project_path)
    if context.backend_path and os.path.isdir(context.backend_path):
        search_paths.append(context.backend_path)

    has_gitignore = False
    for sp in search_paths:
        # Check in current and parent directories
        cur = sp
        for _ in range(3):
            gitignore_path = os.path.join(cur, '.gitignore')
            if os.path.isfile(gitignore_path):
                has_gitignore = True
                break
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
        if has_gitignore:
            break

    if not has_gitignore:
        # Check if it's actually a git repo
        is_git_repo = False
        for sp in search_paths:
            cur = sp
            for _ in range(3):
                if os.path.isdir(os.path.join(cur, '.git')):
                    is_git_repo = True
                    break
                parent = os.path.dirname(cur)
                if parent == cur:
                    break
                cur = parent
            if is_git_repo:
                break

        if is_git_repo:
            results.append({
                'id': 'GIT-001',
                'name': '.gitignore缺失',
                'level': 'warning',
                'message': '项目是Git仓库但缺少.gitignore文件',
                'detail': '缺少.gitignore可能导致不必要的文件被提交到版本库',
                'file': '',
                'line': 0,
                'fix': '创建.gitignore文件，忽略node_modules/、__pycache__/、.env、dist/等',
            })

    return results


# ===== GIT-002 敏感文件提交 =====
def check_git_002_sensitive_files(context) -> List[Dict]:
    """GIT-002 敏感文件提交 - .env/key.pem等被追踪"""
    results = []

    sensitive_patterns = [
        r'\.env(?:\.local|\.production|\.staging)?$',
        r'\.pem$', r'\.key$', r'\.p12$', r'\.pfx$',
        r'\.keystore$', r'\.jks$',
        r'id_rsa', r'id_ed25519',
        r'\.secret$',
        r'credentials\.json$',
        r'service.?account.*\.json$',
        r'\.aws/credentials',
        r'\.htpasswd$',
    ]

    # Look for sensitive files (使用已缓存的文件列表，避免重复os.walk)
    all_files_list = context.find_files([""])  # 空扩展名匹配所有文件
    sensitive_files = []
    for fpath in all_files_list:
        fname = os.path.basename(fpath)
        for pattern in sensitive_patterns:
            if re.search(pattern, fname, re.IGNORECASE):
                sensitive_files.append((fpath, fname))
                break

    if sensitive_files:
        detail = '\n'.join(
            f"  {n}"
            for _, n in sensitive_files[:8]
        )
        results.append({
            'id': 'GIT-002',
            'name': '敏感文件提交',
            'level': 'blocking',
            'message': f'发现{len(sensitive_files)}个敏感文件可能被提交',
            'detail': detail,
            'file': sensitive_files[0][0],
            'line': 0,
            'fix': '将敏感文件添加到.gitignore，使用环境变量管理密钥，已提交的密钥需要轮换',
        })

    return results


# ===== GIT-003 大文件入库 =====
def check_git_003_large_files(context) -> List[Dict]:
    """GIT-003 大文件入库 - 单文件>1MB"""
    results = []
    max_size_mb = context.project_profile.get_adjusted_threshold('max_file_size_mb', 1)
    max_size_bytes = max_size_mb * 1024 * 1024
    large_files = []

    search_paths = []
    if context.project_path and os.path.isdir(context.project_path):
        search_paths.append(context.project_path)
    if context.backend_path and os.path.isdir(context.backend_path):
        search_paths.append(context.backend_path)

    all_files_with_size = context.get_all_files_with_size()
    for fpath, size in all_files_with_size:
        if size > max_size_bytes:
            fname = os.path.basename(fpath)
            size_mb = size / (1024 * 1024)
            large_files.append((fpath, fname, size_mb))

    if large_files:
        large_files.sort(key=lambda x: x[2], reverse=True)
        detail = '\n'.join(
            f"  {n}: {s:.1f}MB"
            for _, n, s in large_files[:5]
        )
        results.append({
            'id': 'GIT-003',
            'name': '大文件入库',
            'level': 'warning',
            'message': f'发现{len(large_files)}个文件超过{max_size_mb}MB',
            'detail': detail,
            'file': large_files[0][0],
            'line': 0,
            'fix': '使用Git LFS管理大文件，或将大文件存储在对象存储(OSS/S3)中',
        })

    return results


# ===== GIT-004 二进制文件提交 =====
def check_git_004_binary_files(context) -> List[Dict]:
    """GIT-004 二进制文件提交 - 图片/视频等不应入库"""
    results = []

    binary_extensions = {
        '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.svg', '.webp',
        '.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv',
        '.mp3', '.wav', '.ogg', '.aac', '.flac',
        '.zip', '.rar', '.7z', '.tar', '.gz',
        '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
        '.exe', '.dll', '.so', '.dylib',
        '.psd', '.ai', '.sketch', '.fig',
    }

    binary_files = []
    search_paths = []
    if context.project_path and os.path.isdir(context.project_path):
        search_paths.append(context.project_path)

    all_files_with_size = context.get_all_files_with_size()
    for fpath, size in all_files_with_size:
        fname = os.path.basename(fpath)
        ext = os.path.splitext(fname)[1].lower()
        if ext in binary_extensions:
            if size > 50 * 1024:  # >50KB
                binary_files.append((fpath, fname, size / 1024))

    if binary_files:
        binary_files.sort(key=lambda x: x[2], reverse=True)
        detail = '\n'.join(
            f"  {n}: {s:.0f}KB"
            for _, n, s in binary_files[:8]
        )
        results.append({
            'id': 'GIT-004',
            'name': '二进制文件提交',
            'level': 'warning',
            'message': f'发现{len(binary_files)}个二进制文件(>50KB)不应入库',
            'detail': detail,
            'file': binary_files[0][0],
            'line': 0,
            'fix': '将二进制资源存储在CDN或对象存储中，使用Git LFS或assets/目录管理',
        })

    return results


# ===== GIT-005 合并冲突标记 =====
def check_git_005_merge_conflicts(context) -> List[Dict]:
    """GIT-005 合并冲突标记 - 代码中残留合并冲突标记

    修复：要求三个标记（<<<<<<<、=======、>>>>>>>）同时存在才报警，
    且 ======= 必须恰好7个等号（排除文档分隔符 ===============）。
    """
    results = []
    code_files = context.find_files([".js", ".ts", ".py", ".tsx", ".jsx", ".html", ".css", ".json"])
    issues = []

    # 精确的冲突标记模式（行首 + 恰好7个字符 + 空格/行尾）
    open_pat  = re.compile(r'^<{7}(?:\s|$)', re.MULTILINE)
    sep_pat   = re.compile(r'^={7}$', re.MULTILINE)          # 恰好7个=，排除16+个的分隔符
    close_pat = re.compile(r'^>{7}(?:\s|$)', re.MULTILINE)

    for fpath in code_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        # 快速预检：三个标记必须同时存在才算冲突
        has_open  = open_pat.search(content)
        has_close = close_pat.search(content)
        if not (has_open and has_close):
            continue

        # 找到所有冲突标记行
        for pat in [open_pat, sep_pat, close_pat]:
            for m in pat.finditer(content):
                line_num = content[:m.start()].count('\n') + 1
                line_text = content.split('\n')[line_num - 1].strip()
                issues.append((fpath, line_num, line_text[:30]))

    if issues:
        detail = '\n'.join(
            f"  {os.path.basename(f)}:{l} {t}"
            for f, l, t in issues[:8]
        )
        results.append({
            'id': 'GIT-005',
            'name': '合并冲突标记',
            'level': 'blocking',
            'message': f'发现{len(issues)}处未解决的合并冲突标记',
            'detail': detail,
            'file': issues[0][0],
            'line': issues[0][1],
            'fix': '解决所有合并冲突，删除冲突标记(<<<<<<<, =======, >>>>>>>)后提交',
        })

    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'GIT-001',
        'name': '.gitignore缺失',
        'level': 'warning',
        'category': 'git_convention',
        'module_id': '29',
        'applicable_types': [],
        'description': '检查项目是否有.gitignore文件',
        'check': check_git_001_gitignore,
    },
    {
        'id': 'GIT-002',
        'name': '敏感文件提交',
        'level': 'blocking',
        'category': 'git_convention',
        'module_id': '29',
        'applicable_types': [],
        'description': '检查.env/key.pem等敏感文件是否被追踪',
        'check': check_git_002_sensitive_files,
    },
    {
        'id': 'GIT-003',
        'name': '大文件入库',
        'level': 'warning',
        'category': 'git_convention',
        'module_id': '29',
        'applicable_types': [],
        'description': '检查单文件是否>1MB',
        'check': check_git_003_large_files,
    },
    {
        'id': 'GIT-004',
        'name': '二进制文件提交',
        'level': 'warning',
        'category': 'git_convention',
        'module_id': '29',
        'applicable_types': [],
        'description': '检查图片/视频等二进制文件是否入库',
        'check': check_git_004_binary_files,
    },
    {
        'id': 'GIT-005',
        'name': '合并冲突标记',
        'level': 'blocking',
        'category': 'git_convention',
        'module_id': '29',
        'applicable_types': [],
        'description': '检查代码中是否残留合并冲突标记',
        'check': check_git_005_merge_conflicts,
    },
]
