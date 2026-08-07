"""
业务流程闭环规则集 (M8)
通用业务流程检查 - 适用于所有有前端交互的项目类型
包含: 表单校验、危险操作确认、端到端流程、异常处理、登录流程、网络恢复等6项检查
"""

import re
import os
from typing import List, Dict, Any


# ===== 工具函数 =====
def _get_frontend_js_files(context) -> List[str]:
    """获取前端JS/TS文件列表，后端项目返回Python文件"""
    if not context.project_path or not os.path.isdir(context.project_path):
        return []
    if context.is_web_frontend():
        return context.find_files([".js", ".ts", ".tsx", ".jsx"])
    elif context.project_type in ("python_backend", "flask"):
        # v2.9.1: 后端项目扫描Python文件中的流程
        return context.find_files([".py"])
    else:
        return context.find_files([".js"])


# ===== 8.1 表单校验完整 =====
def check_8_1_form_validation(context) -> List[Dict]:
    """8.1 表单校验完整 - 检查提交操作是否有校验逻辑"""
    results = []
    form_submit_no_validate = []
    
    js_files = _get_frontend_js_files(context)
    if not js_files:
        results.append({
            'id': '8.1',
            'name': '表单校验完整',
            'level': 'suggestion',
            'message': '无前端代码，跳过表单校验检查',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    for f in js_files:
        content = context.safe_read(f)
        if not content:
            continue
        if 'submit' in content.lower() or 'onSubmit' in content or 'handleSubmit' in content:
            has_validate = 'validate' in content.lower() or 'check' in content.lower() or 'required' in content.lower()
            # 小程序: wx.showToast/showModal + return
            has_toast_validate = bool(re.search(
                r'wx\.(showToast|showModal)[\s\S]{0,300}?\breturn\b', content))
            # Web: toast/alert/notification + return or setError
            has_web_validate = bool(re.search(
                r'(toast|notification|message\.error|setError|alert)[\s\S]{0,300}?\breturn\b',
                content, re.IGNORECASE))
            if not has_validate and not has_toast_validate and not has_web_validate:
                basename = os.path.basename(os.path.dirname(f))
                form_submit_no_validate.append(basename)
    
    if form_submit_no_validate:
        results.append({
            'id': '8.1',
            'name': '表单校验完整',
            'level': 'problem',
            'message': f'发现 {len(form_submit_no_validate)} 个提交操作可能缺少校验（待人工验证）',
            'file': '',
            'line': 0,
            'snippet': '\n'.join(form_submit_no_validate[:5]),
            'fix': '为所有表单提交添加必填校验',
        })
    else:
        results.append({
            'id': '8.1',
            'name': '表单校验完整',
            'level': 'suggestion',
            'message': '表单校验基本覆盖（待人工验证）',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
    
    return results


# ===== 8.2 危险操作二次确认 =====
def check_8_2_dangerous_operation_confirm(context) -> List[Dict]:
    """8.2 危险操作二次确认 - 检查删除/取消等危险操作是否有确认弹窗"""
    results = []
    dangerous_ops = []
    
    js_files = _get_frontend_js_files(context)
    if not js_files:
        results.append({
            'id': '8.2',
            'name': '危险操作二次确认',
            'level': 'suggestion',
            'message': '无前端代码，跳过危险操作检查',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    dangerous_kw = re.compile(
        r'\b(delete|remove|clear|cancel|logout|删除|清除|注销|退出登录)\b', re.IGNORECASE)
    # 安全上下文模式：清理/工具类操作，不算用户面对的危险操作
    safe_ctx = re.compile(
        r'(clearTimeout|clearInterval|removeEventListener|removeListener|'
        r'removeStorage|clearStorage|removeStorageSync|clearStorageSync|'
        r'\.off\(|\.splice\(|\.shift\(|\.pop\(|Array\.from|Array\.prototype)',
        re.IGNORECASE)
    # 加密/存储工具函数特征
    crypto_storage = re.compile(
        r'(encrypt|decrypt|crypto|cipher|AES|RSA|MD5|SHA|HMAC|'
        r'setStorage|getStorage|setStorageSync|getStorageSync)',
        re.IGNORECASE)
    
    for f in js_files:
        if '/components/ec-canvas/' in f:
            continue
        # 小程序: pages/和components/; Web: app/或src/或components/
        is_ui_file = '/pages/' in f or '/components/' in f or '/app/' in f or '/src/' in f
        if not is_ui_file:
            continue
        # 排除utils/工具文件
        if '/utils/' in f or '/lib/' in f:
            continue
        content = context.safe_read(f)
        if not content:
            continue
        
        # 检查文件是否包含真正的危险操作（排除安全清理和加密/存储上下文）
        has_real_danger = False
        for m in dangerous_kw.finditer(content):
            ctx_start = max(0, m.start() - 50)
            ctx_end = min(len(content), m.end() + 50)
            ctx_str = content[ctx_start:ctx_end]
            if safe_ctx.search(ctx_str):
                continue
            if crypto_storage.search(ctx_str):
                continue
            has_real_danger = True
            break
        
        if not has_real_danger:
            continue
        
        if 'confirm' not in content and 'Dialog' not in content and 'showModal' not in content:
            try:
                dangerous_ops.append(os.path.relpath(f))
            except ValueError:
                dangerous_ops.append(f)
    
    if dangerous_ops:
        results.append({
            'id': '8.2',
            'name': '危险操作二次确认',
            'level': 'problem',
            'message': f'发现 {len(dangerous_ops)} 个危险操作可能缺少二次确认（待人工验证）',
            'file': '',
            'line': 0,
            'snippet': '\n'.join(dangerous_ops[:5]),
            'fix': '删除/取消操作添加确认弹窗',
        })
    else:
        results.append({
            'id': '8.2',
            'name': '危险操作二次确认',
            'level': 'suggestion',
            'message': '危险操作均有确认（待人工验证）',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
    
    return results


# ===== 8.3 端到端流程走通 =====
def check_8_3_end_to_end_flow(context) -> List[Dict]:
    """8.3 端到端流程走通 - 需人工验证核心业务路径代码逻辑完整性"""
    results = []
    results.append({
        'id': '8.3',
        'name': '端到端流程走通',
        'level': 'suggestion',
        'message': '需人工验证核心业务路径代码逻辑完整性',
        'file': '',
        'line': 0,
        'snippet': '',
        'fix': '执行端到端测试覆盖核心业务流程',
    })
    return results


# ===== 8.4 异常流程处理 =====
def check_8_4_exception_handling(context) -> List[Dict]:
    """8.4 异常流程处理 - 检查API调用是否有错误处理和超时兜底"""
    results = []
    missing_error_handling = []
    
    js_files = _get_frontend_js_files(context)
    if not js_files:
        results.append({
            'id': '8.4',
            'name': '异常流程处理',
            'level': 'suggestion',
            'message': '无前端代码，跳过异常流程检查',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    # 排除工具文件（底层API封装通常自己处理错误）
    js_non_utils = [f for f in js_files 
                    if os.path.basename(f) not in 
                    ("api.js", "util.js", "auth.js", "security.js", "media.js", "api.ts", "api.tsx")]
    
    for f in js_non_utils:
        content = context.safe_read(f)
        if not content:
            continue
        # 小程序: .api( / api( ; Web: fetch( / axios( / .api(
        has_api_call = bool(re.search(r'\.api\(|api\(|fetch\(|axios\(', content))
        has_error_handler = bool(re.search(r'\.catch|\.then.*err|fail\s*[:}]|onError|onFail|try\s*\{', content))
        if has_api_call and not has_error_handler:
            try:
                missing_error_handling.append(os.path.relpath(f))
            except ValueError:
                missing_error_handling.append(f)
    
    if missing_error_handling:
        results.append({
            'id': '8.4',
            'name': '异常流程处理',
            'level': 'problem',
            'message': f'发现 {len(missing_error_handling)} 个页面缺少网络错误/超时兜底',
            'file': '',
            'line': 0,
            'snippet': '\n'.join(missing_error_handling[:5]),
            'fix': '为所有API调用添加catch/fail处理和用户提示',
        })
    else:
        results.append({
            'id': '8.4',
            'name': '异常流程处理',
            'level': 'suggestion',
            'message': '异常流程处理覆盖完整',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
    
    return results


# ===== 8.5 登录→核心操作→退出 完整流程检查 =====
def check_8_5_login_core_logout_flow(context) -> List[Dict]:
    """8.5 登录→核心操作→退出 完整流程检查"""
    results = []
    issues = []
    has_login = False
    has_logout = False
    has_core_action = False
    
    js_files = _get_frontend_js_files(context)
    if not js_files:
        results.append({
            'id': '8.5',
            'name': '登录→核心操作→退出流程',
            'level': 'suggestion',
            'message': '无前端代码，跳过登录流程检查',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    for f in js_files:
        content = context.safe_read(f)
        if not content:
            continue
        
        # 登录检测
        if ('login' in content.lower() or 'signIn' in content) and \
           ('send_code' in content or 'wx.login' in content or 'phone' in content or 
            'password' in content.lower() or 'auth' in content.lower()):
            has_login = True
        # Electron IPC登录
        if re.search(r'ipcRenderer\.invoke\s*\(\s*["\'](?:login|auth|signIn)', content, re.IGNORECASE):
            has_login = True
        # v2.9.1: Python后端登录检测
        if re.search(r'def\s+(handle_)?(?:login|wx_login|send_code|auth)', content, re.IGNORECASE):
            has_login = True
        
        # 退出检测
        if 'logout' in content.lower() or '退出登录' in content or 'signOut' in content or \
           ('clearToken' in content and 'token' in content) or \
           ('removeStorageSync' in content and 'token' in content) or \
           ('localStorage.removeItem' in content and 'token' in content.lower()) or \
           ('sessionStorage.clear' in content) or \
           (re.search(r'ipcRenderer\.invoke\s*\(\s*["\'](?:logout|signOut|signout)', content, re.IGNORECASE)):
            has_logout = True
        # v2.9.1: Python后端退出检测
        if re.search(r'def\s+(handle_)?logout', content, re.IGNORECASE):
            has_logout = True
        
        # 核心操作检测
        if re.search(r'api\s*\(\s*["\']store', content) or re.search(r'api\s*\(\s*["\']review', content) or \
           re.search(r'api\s*\(\s*["\']chat', content) or \
           (re.search(r'fetch\(|axios\(', content) and re.search(r'/api/|/store|/review|/project', content)) or \
           (re.search(r'ipcRenderer\.invoke\s*\(\s*["\'](?:store|review|chat|project|api)', content, re.IGNORECASE)):
            has_core_action = True
        # v2.9.1: Python后端核心操作
        if re.search(r'@app\.route|@bp\.route|@router\.', content) and \
           re.search(r'def\s+\w+_(handler|api|view|endpoint)', content, re.IGNORECASE):
            has_core_action = True
        if re.search(r'def\s+(handle_|chat_|index_|query_)', content):
            has_core_action = True
    
    if not has_login:
        issues.append("未找到登录流程代码")
    if not has_logout:
        issues.append("未找到退出登录流程")
    if not has_core_action:
        issues.append("未找到核心业务操作")
    
    if issues:
        results.append({
            'id': '8.5',
            'name': '登录→核心操作→退出流程',
            'level': 'problem',
            'message': f'{len(issues)}个流程缺失',
            'file': '',
            'line': 0,
            'snippet': '\n'.join(issues),
            'fix': '确保完整业务流程代码存在',
        })
    else:
        results.append({
            'id': '8.5',
            'name': '登录→核心操作→退出流程',
            'level': 'suggestion',
            'message': '核心业务流程代码完整',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
    
    return results


# ===== 8.6 网络异常恢复 =====
def check_8_6_network_recovery(context) -> List[Dict]:
    """8.6 网络异常恢复 - 检查是否有超时/重试/离线提示"""
    results = []
    issues = []
    
    js_files = _get_frontend_js_files(context)
    if not js_files:
        results.append({
            'id': '8.6',
            'name': '网络异常恢复',
            'level': 'suggestion',
            'message': '无前端代码，跳过网络恢复检查',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
        return results
    
    all_content = ""
    for f in js_files:
        content = context.safe_read(f)
        if content:
            all_content += content + "\n"
    
    # 检查超时
    has_timeout = bool(re.search(r'timeout|AbortController|signal:\s*AbortSignal', all_content, re.IGNORECASE))
    has_retry = bool(re.search(r'retry|重试', all_content, re.IGNORECASE))
    has_offline = bool(re.search(r'offline|无网络|网络异常|断网|navigator\.onLine', all_content, re.IGNORECASE))
    
    if not has_timeout:
        issues.append("未检测到请求超时设置")
    if not has_offline:
        issues.append("未检测到网络异常提示")
    
    if issues:
        results.append({
            'id': '8.6',
            'name': '网络异常恢复',
            'level': 'problem',
            'message': f'{len(issues)}个网络恢复问题',
            'file': '',
            'line': 0,
            'snippet': '\n'.join(issues),
            'fix': '添加超时设置、重试机制和离线提示',
        })
    else:
        results.append({
            'id': '8.6',
            'name': '网络异常恢复',
            'level': 'suggestion',
            'message': '网络异常处理完整',
            'file': '',
            'line': 0,
            'snippet': '',
            'fix': '',
        })
    
    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': '8.1',
        'name': '表单校验完整',
        'level': 'problem',
        'category': 'business_flow',
        'module_id': '8',
        'applicable_types': ['miniprogram', 'web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查表单提交操作是否有校验逻辑，避免无效数据提交',
        'check': check_8_1_form_validation,
    },
    {
        'id': '8.2',
        'name': '危险操作二次确认',
        'level': 'problem',
        'category': 'business_flow',
        'module_id': '8',
        'applicable_types': ['miniprogram', 'web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查删除/取消/注销等危险操作是否有确认弹窗',
        'check': check_8_2_dangerous_operation_confirm,
    },
    {
        'id': '8.3',
        'name': '端到端流程走通',
        'level': 'suggestion',
        'category': 'business_flow',
        'module_id': '8',
        'applicable_types': [],
        'description': '提示需人工验证核心业务路径代码逻辑完整性',
        'check': check_8_3_end_to_end_flow,
    },
    {
        'id': '8.4',
        'name': '异常流程处理',
        'level': 'problem',
        'category': 'business_flow',
        'module_id': '8',
        'applicable_types': ['miniprogram', 'web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查API调用是否有错误处理和用户提示',
        'check': check_8_4_exception_handling,
    },
    {
        'id': '8.5',
        'name': '登录→核心操作→退出流程',
        'level': 'problem',
        'category': 'business_flow',
        'module_id': '8',
        'applicable_types': ['miniprogram', 'web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查登录、核心业务操作、退出登录的完整流程是否存在',
        'check': check_8_5_login_core_logout_flow,
    },
    {
        'id': '8.6',
        'name': '网络异常恢复',
        'level': 'problem',
        'category': 'business_flow',
        'module_id': '8',
        'applicable_types': ['miniprogram', 'web', 'mixed', 'electron', 'mixed_electron'],
        'description': '检查是否有超时设置、重试机制和离线提示',
        'check': check_8_6_network_recovery,
    },
]
