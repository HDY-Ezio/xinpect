# -*- coding: utf-8 -*-
"""
危险函数调用 AST 深度检测规则集
对应 bandit B301-B320 系列 + 扩展

检测原理：
- 遍历 AST Call 节点，精确匹配危险函数/方法名及参数
- 通过参数值判断是否为危险用法（如 subprocess shell=True、yaml.load 无SafeLoader）
- AST 精准定位，避免纯字符串匹配误报

规则ID: PYAST059 - PYAST070
"""

import ast
import re
from typing import List, Dict, Any, Optional


def _parse_ast_safe(filepath: str, content: str) -> Optional[ast.Module]:
    """安全解析AST，语法错误返回None"""
    try:
        return ast.parse(content, filename=filepath)
    except SyntaxError:
        return None


def _is_const_str(node: ast.AST) -> Optional[str]:
    """提取字符串常量值"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _is_const_true(node: ast.AST) -> bool:
    """判断是否为 True 常量"""
    return isinstance(node, ast.Constant) and node.value is True


def _is_const_false(node: ast.AST) -> bool:
    """判断是否为 False 常量"""
    return isinstance(node, ast.Constant) and node.value is False


def _get_kwarg(node: ast.Call, name: str) -> Optional[ast.AST]:
    """获取Call节点的关键字参数值"""
    for kw in node.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _get_line_text(content_lines: List[str], lineno: int) -> str:
    """安全获取行文本"""
    if not lineno or lineno - 1 >= len(content_lines):
        return ""
    return content_lines[lineno - 1].strip()[:120]


def check_pickle_deserialization_ast(context) -> List[Dict]:
    """
    PYAST059 - pickle/marshal/shelve 反序列化检测（对应 bandit B301/B302）
    
    检测原理：检测 pickle.load(s)、marshal.load(s)、shelve.open 等危险反序列化函数调用。
    反序列化不受信任的数据可导致任意代码执行(RCE)。
    
    风险等级：P0 (高危)
    修复建议：使用 JSON 等安全序列化格式；若必须使用 pickle，确保数据来源可信。
    """
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    # 危险函数映射: (模块名.函数名, 描述)
    dangerous_deserializers = [
        ('pickle.load', 'pickle.load() — 反序列化不受信数据可导致RCE'),
        ('pickle.loads', 'pickle.loads() — 反序列化不受信数据可导致RCE'),
        ('pickle.Unpickler', 'pickle.Unpickler — 反序列化不受信数据可导致RCE'),
        ('marshal.load', 'marshal.load() — 反序列化不受信数据可导致RCE'),
        ('marshal.loads', 'marshal.loads() — 反序列化不受信数据可导致RCE'),
        ('shelve.open', 'shelve.open() — 使用pickle反序列化，存在RCE风险'),
        ('shelve.DbfilenameShelf', 'shelve.DbfilenameShelf — 使用pickle反序列化'),
        ('dill.load', 'dill.load() — 扩展版pickle，RCE风险'),
        ('dill.loads', 'dill.loads() — 扩展版pickle，RCE风险'),
    ]
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        content_lines = content.split('\n')
        
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            
            attr = node.func
            if not isinstance(attr.value, ast.Name):
                continue
            
            full_name = f"{attr.value.id}.{attr.attr}"
            
            for danger_name, desc in dangerous_deserializers:
                if full_name == danger_name:
                    results.append({
                        'id': 'PYAST059',
                        'name': '危险反序列化函数检测',
                        'level': 'blocking',
                        'category': 'dangerous_functions',
                        'message': desc,
                        'file': fpath,
                        'line': node.lineno,
                        'snippet': _get_line_text(content_lines, node.lineno),
                        'fix': '使用 JSON 替代 pickle/marshal/shelve；若必须使用，确保数据来源完全可信',
                    })
                    break
            
            # 检测 __import__('pickle').loads 等动态导入调用
            # (复杂情况，暂不处理)
    
    return results


def check_yaml_unsafe_load_ast(context) -> List[Dict]:
    """
    PYAST060 - yaml.load 无 SafeLoader 检测（对应 bandit B506）
    
    检测原理：检测 yaml.load() 调用，检查是否传入 Loader=yaml.SafeLoader 或
    使用 yaml.safe_load()。无SafeLoader时可导致RCE。
    
    风险等级：P0 (高危)
    修复建议：使用 yaml.safe_load() 或显式指定 Loader=yaml.SafeLoader。
    """
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        content_lines = content.split('\n')
        
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            
            attr = node.func
            if not isinstance(attr.value, ast.Name):
                continue
            
            module_name = attr.value.id
            method_name = attr.attr
            
            if module_name != 'yaml':
                continue
            
            # yaml.load() — 检查是否有安全的Loader
            if method_name == 'load':
                has_safe_loader = False
                
                # 检查 Loader 关键字参数
                loader_kw = _get_kwarg(node, 'Loader')
                if loader_kw:
                    if isinstance(loader_kw, ast.Attribute):
                        if loader_kw.attr == 'SafeLoader':
                            has_safe_loader = True
                        elif loader_kw.attr == 'CSafeLoader':
                            has_safe_loader = True
                    elif isinstance(loader_kw, ast.Name):
                        if loader_kw.id in ('SafeLoader', 'CSafeLoader'):
                            has_safe_loader = True
                
                # 检查位置参数第二个是否为 SafeLoader
                if not has_safe_loader and len(node.args) >= 2:
                    loader_arg = node.args[1]
                    if isinstance(loader_arg, ast.Attribute) and loader_arg.attr in ('SafeLoader', 'CSafeLoader'):
                        has_safe_loader = True
                    elif isinstance(loader_arg, ast.Name) and loader_arg.id in ('SafeLoader', 'CSafeLoader'):
                        has_safe_loader = True
                
                if not has_safe_loader:
                    results.append({
                        'id': 'PYAST060',
                        'name': 'yaml.load不安全反序列化检测',
                        'level': 'blocking',
                        'category': 'dangerous_functions',
                        'message': 'yaml.load() 未使用 SafeLoader，反序列化不受信YAML可导致RCE',
                        'file': fpath,
                        'line': node.lineno,
                        'snippet': _get_line_text(content_lines, node.lineno),
                        'fix': '使用 yaml.safe_load() 或 yaml.load(data, Loader=yaml.SafeLoader)',
                    })
            
            # yaml.full_load() / yaml.unsafe_load() 也有风险
            elif method_name in ('full_load', 'unsafe_load'):
                risk_level = 'blocking' if method_name == 'unsafe_load' else 'problem'
                results.append({
                    'id': 'PYAST060',
                    'name': 'yaml.load不安全反序列化检测',
                    'level': risk_level,
                    'category': 'dangerous_functions',
                    'message': f'yaml.{method_name}() 存在反序列化RCE风险',
                    'file': fpath,
                    'line': node.lineno,
                    'snippet': _get_line_text(content_lines, node.lineno),
                    'fix': '使用 yaml.safe_load() 替代',
                })
    
    return results


def check_eval_exec_ast(context) -> List[Dict]:
    """
    PYAST061 - eval/exec 动态执行检测（对应 bandit B307）
    
    检测原理：检测 eval()、exec()、compile() 函数调用，动态执行用户可控的代码
    可导致任意代码执行。
    
    风险等级：P0 (高危)
    修复建议：避免使用 eval/exec；使用 ast.literal_eval 解析数据结构。
    """
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    dangerous_funcs = {
        'eval': 'eval() — 动态执行任意代码，存在RCE风险',
        'exec': 'exec() — 动态执行任意代码，存在RCE风险',
        'execfile': 'execfile() — Python2遗留函数，动态执行文件代码',
    }
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        content_lines = content.split('\n')
        
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            
            func = node.func
            func_name = None
            if isinstance(func, ast.Name):
                func_name = func.id
            elif isinstance(func, ast.Attribute):
                # 跳过模块方法调用，只检测内置形式
                continue
            
            if func_name in dangerous_funcs:
                # 检查参数是否为常量字符串（如果是固定常量则风险较低但仍不推荐）
                # 但 bandit 对所有 eval/exec 都报，我们也保持一致
                arg_is_const = bool(node.args and _is_const_str(node.args[0]) is not None)
                level = 'problem' if arg_is_const else 'blocking'
                
                results.append({
                    'id': 'PYAST061',
                    'name': 'eval/exec动态执行检测',
                    'level': level,
                    'category': 'dangerous_functions',
                    'message': dangerous_funcs[func_name],
                    'file': fpath,
                    'line': node.lineno,
                    'snippet': _get_line_text(content_lines, node.lineno),
                    'fix': '使用 ast.literal_eval() 安全解析数据，避免使用 eval/exec',
                })
    
    return results


def check_subprocess_shell_ast(context) -> List[Dict]:
    """
    PYAST062 - subprocess shell=True 命令注入检测（对应 bandit B404/B602-B607）
    
    检测原理：检测 subprocess 系列函数调用（run/Popen/call/check_call等），
    检查 shell=True 参数。shell=True 时命令字符串可能被注入。
    
    风险等级：P0 (高危)
    修复建议：使用 shell=False（默认）并传入命令列表，如 subprocess.run(["ls", "-l"])。
    """
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    subprocess_funcs = {
        'run', 'Popen', 'call', 'check_call', 'check_output',
        'getoutput', 'getstatusoutput',
    }
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        content_lines = content.split('\n')
        
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            
            attr = node.func
            if not isinstance(attr.value, ast.Name):
                continue
            
            if attr.value.id != 'subprocess':
                continue
            if attr.attr not in subprocess_funcs:
                continue
            
            # 检查 shell=True
            shell_kw = _get_kwarg(node, 'shell')
            if shell_kw and _is_const_true(shell_kw):
                results.append({
                    'id': 'PYAST062',
                    'name': 'subprocess shell=True命令注入检测',
                    'level': 'blocking',
                    'category': 'dangerous_functions',
                    'message': f'subprocess.{attr.attr}(shell=True) 存在命令注入风险',
                    'file': fpath,
                    'line': node.lineno,
                    'snippet': _get_line_text(content_lines, node.lineno),
                    'fix': '移除 shell=True，使用命令列表形式：subprocess.run(["cmd", "arg1", "arg2"])',
                })
            
            # 即使 shell=False，如果第一个参数是字符串而非列表且包含shell元字符也提示
            # (为减少误报，暂只检测 shell=True)
    
    # 同时检测 os.system / os.popen (B605/B606)
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        content_lines = content.split('\n')
        
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            
            attr = node.func
            if not isinstance(attr.value, ast.Name):
                continue
            
            if attr.value.id != 'os':
                continue
            
            if attr.attr in ('system', 'popen', 'popen2', 'popen3', 'popen4'):
                results.append({
                    'id': 'PYAST062',
                    'name': 'subprocess shell=True命令注入检测',
                    'level': 'blocking',
                    'category': 'dangerous_functions',
                    'message': f'os.{attr.attr}() 存在命令注入风险',
                    'file': fpath,
                    'line': node.lineno,
                    'snippet': _get_line_text(content_lines, node.lineno),
                    'fix': '使用 subprocess.run(["cmd", "arg"], shell=False) 替代',
                })
    
    return results


def check_paramiko_missing_host_key_ast(context) -> List[Dict]:
    """
    PYAST063 - paramiko 主机密钥验证关闭检测（对应 bandit B507）
    
    检测原理：检测 paramiko SSHClient 调用 set_missing_host_key_policy() 时设置
    AutoAddPolicy 或 WarningPolicy，相当于禁用主机密钥验证，易受中间人攻击。
    
    风险等级：P1 (中危)
    修复建议：使用 RejectPolicy（默认）或显式配置 known_hosts。
    """
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    unsafe_policies = ('AutoAddPolicy', 'WarningPolicy', 'AutoAdd')
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        content_lines = content.split('\n')
        
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            
            if node.func.attr != 'set_missing_host_key_policy':
                continue
            
            if not node.args:
                continue
            
            arg = node.args[0]
            policy_name = None
            
            if isinstance(arg, ast.Call):
                # paramiko.AutoAddPolicy()
                if isinstance(arg.func, ast.Attribute):
                    policy_name = arg.func.attr
                elif isinstance(arg.func, ast.Name):
                    policy_name = arg.func.id
            elif isinstance(arg, ast.Name):
                policy_name = arg.id
            
            if policy_name and policy_name in unsafe_policies:
                results.append({
                    'id': 'PYAST063',
                    'name': 'paramiko主机密钥验证关闭检测',
                    'level': 'problem',
                    'category': 'dangerous_functions',
                    'message': f'paramiko 使用 {policy_name}，关闭主机密钥验证，存在中间人攻击风险',
                    'file': fpath,
                    'line': node.lineno,
                    'snippet': _get_line_text(content_lines, node.lineno),
                    'fix': '使用 RejectPolicy 并配置 known_hosts：client.load_system_host_keys()',
                })
    
    return results


def check_requests_ssl_verify_false_ast(context) -> List[Dict]:
    """
    PYAST064 - SSL证书验证关闭检测（对应 bandit B308-B310 / B501）
    
    检测原理：检测 requests 库函数调用中 verify=False 参数，以及 ssl._create_unverified_context。
    关闭 SSL 验证使通信易受中间人攻击。
    
    风险等级：P1 (中危)
    修复建议：移除 verify=False，配置正确的 CA 证书；内部服务使用自签证书时指定 verify=cert_path。
    """
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    requests_methods = {
        'get', 'post', 'put', 'delete', 'patch', 'head', 'options', 'request'
    }
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        content_lines = content.split('\n')
        
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            
            func = node.func
            
            # requests.get/post/...(verify=False)
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                if func.value.id == 'requests' and func.attr in requests_methods:
                    verify_kw = _get_kwarg(node, 'verify')
                    if verify_kw and _is_const_false(verify_kw):
                        results.append({
                            'id': 'PYAST064',
                            'name': 'SSL证书验证关闭检测',
                            'level': 'problem',
                            'category': 'dangerous_functions',
                            'message': f'requests.{func.attr}(verify=False) 关闭SSL证书验证，存在中间人攻击风险',
                            'file': fpath,
                            'line': node.lineno,
                            'snippet': _get_line_text(content_lines, node.lineno),
                            'fix': '移除 verify=False；自签证书场景使用 verify="/path/to/ca.pem"',
                        })
            
            # Session 类的 verify 属性设置
            # s.verify = False 形式
            # (在 Assign 中检测)
        
        # 检测 ssl._create_unverified_context()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            attr = node.func
            if not isinstance(attr.value, ast.Name):
                continue
            if attr.value.id == 'ssl' and attr.attr == '_create_unverified_context':
                results.append({
                    'id': 'PYAST064',
                    'name': 'SSL证书验证关闭检测',
                    'level': 'problem',
                    'category': 'dangerous_functions',
                    'message': 'ssl._create_unverified_context() 关闭SSL证书验证',
                    'file': fpath,
                    'line': node.lineno,
                    'snippet': _get_line_text(content_lines, node.lineno),
                    'fix': '使用默认 ssl.create_default_context()，配置正确的证书验证',
                })
    
    return results


def check_chmod_unsafe_ast(context) -> List[Dict]:
    """
    PYAST065 - 危险 chmod 权限设置检测（对应 bandit B606）
    
    检测原理：检测 os.chmod / pathlib.Path.chmod 调用，检查权限模式是否包含
    其他用户可写（0oXX2/0oXX6/0oXX7 等）或全局可执行等危险权限。
    
    风险等级：P1 (中危)
    修复建议：收紧文件权限，遵循最小权限原则（如 0o600/0o700）。
    """
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        content_lines = content.split('\n')
        
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            
            func = node.func
            is_chmod_call = False
            
            # os.chmod(path, mode)
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                if func.value.id == 'os' and func.attr == 'chmod':
                    is_chmod_call = True
            
            # Path.chmod(mode)
            if isinstance(func, ast.Attribute) and func.attr == 'chmod':
                # 不一定是pathlib，但chmod方法名比较独特
                if not isinstance(func.value, ast.Name):
                    is_chmod_call = True
            
            if not is_chmod_call:
                continue
            
            # 获取 mode 参数（通常是最后一个位置参数或 mode= 关键字）
            mode_arg = _get_kwarg(node, 'mode')
            if mode_arg is None and len(node.args) >= 2:
                mode_arg = node.args[1]
            elif mode_arg is None and len(node.args) >= 1 and isinstance(func, ast.Attribute) and func.attr == 'chmod' and not isinstance(func.value, ast.Name):
                # Path.chmod(mode) — 第一个参数就是 mode
                mode_arg = node.args[0]
            
            if mode_arg is None:
                continue
            
            # 检测常量数字权限
            if isinstance(mode_arg, ast.Constant) and isinstance(mode_arg.value, int):
                mode = mode_arg.value
                # 其他用户可写（other write）: mode & 0o002
                others_writable = mode & 0o002
                # 其他用户可读可写: mode & 0o006
                # 全局可执行且可写: 
                
                if others_writable:
                    results.append({
                        'id': 'PYAST065',
                        'name': '危险chmod权限设置检测',
                        'level': 'problem',
                        'category': 'dangerous_functions',
                        'message': f'chmod 权限 {oct(mode)} 包含其他用户可写权限，存在权限提升风险',
                        'file': fpath,
                        'line': node.lineno,
                        'snippet': _get_line_text(content_lines, node.lineno),
                        'fix': '收紧文件权限，使用最小权限原则，如 0o600/0o700/0o755',
                    })
            
            # 检测 stat.S_IWOTH 等
            elif isinstance(mode_arg, ast.BinOp):
                # stat.S_IRWXU | stat.S_IRWXO 等组合，保守检测 S_IWOTH
                mode_src = ast.dump(mode_arg)
                if 'IWOTH' in mode_src:
                    results.append({
                        'id': 'PYAST065',
                        'name': '危险chmod权限设置检测',
                        'level': 'problem',
                        'category': 'dangerous_functions',
                        'message': 'chmod 使用 S_IWOTH 设置其他用户可写权限',
                        'file': fpath,
                        'line': node.lineno,
                        'snippet': _get_line_text(content_lines, node.lineno),
                        'fix': '移除其他用户可写权限，遵循最小权限原则',
                    })
    
    return results


def check_template_ssti_ast(context) -> List[Dict]:
    """
    PYAST066 - 模板注入 SSTI 检测（对应 bandit B702）
    
    检测原理：检测 Mako/Jinja2 模板渲染中使用用户可控的字符串作为模板内容。
    匹配模式：
      - jinja2.Template(user_input)  （模块属性形式）
      - mako.template.Template(user_input)  （嵌套模块形式）
      - from mako.template import Template; Template(user_input)  （直接导入形式，需配合导入检测）
    第一个参数非字符串常量时判定为动态模板，存在 SSTI 风险。
    
    风险等级：P0 (高危)
    修复建议：使用模板文件而非字符串模板，避免动态模板拼接；严格过滤用户输入。
    """
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        content_lines = content.split('\n')
        
        # 收集从模板模块直接导入的 Template 类名（from xxx import Template）
        template_import_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module_name = node.module or ''
                is_template_module = any(
                    module_name.startswith(p)
                    for p in ('jinja2', 'mako', 'django.template', 'mako.template')
                )
                if is_template_module:
                    for alias in node.names:
                        if alias.name in ('Template', 'Environment'):
                            template_import_names.add(alias.asname or alias.name)
        
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            
            if not node.args:
                continue
            
            first_arg = node.args[0]
            # 第一个参数是纯字符串常量 → 安全（静态模板字符串）
            is_dynamic = not (
                isinstance(first_arg, ast.Constant) and
                isinstance(getattr(first_arg, 'value', None), str)
            )
            # f-string / %拼接 / +拼接 都是动态
            if isinstance(first_arg, ast.JoinedStr):
                is_dynamic = True
            if isinstance(first_arg, ast.BinOp):
                is_dynamic = True
            
            if not is_dynamic:
                continue
            
            func = node.func
            is_template_engine = False
            engine_name = "模板"
            
            # 形式1: xxx.Template(...)  模块属性形式
            if isinstance(func, ast.Attribute) and func.attr == 'Template':
                module_part = func.value
                
                # jinja2.Template / mako.Template
                if isinstance(module_part, ast.Name):
                    if module_part.id in ('jinja2', 'mako'):
                        is_template_engine = True
                        engine_name = module_part.id
                
                # mako.template.Template / django.template.Template
                elif isinstance(module_part, ast.Attribute):
                    if module_part.attr in ('template', 'Template'):
                        if isinstance(module_part.value, ast.Name):
                            if module_part.value.id in ('mako', 'django', 'jinja2'):
                                is_template_engine = True
                                engine_name = f"{module_part.value.id}.{module_part.attr}"
            
            # 形式2: Template(...)  直接导入形式（from mako.template import Template）
            elif isinstance(func, ast.Name):
                if func.id in template_import_names:
                    is_template_engine = True
                    engine_name = func.id
            
            if is_template_engine:
                results.append({
                    'id': 'PYAST066',
                    'name': '模板注入SSTI检测',
                    'level': 'blocking',
                    'category': 'dangerous_functions',
                    'message': f'{engine_name}.Template 使用动态内容构造模板，存在SSTI（服务端模板注入）风险',
                    'file': fpath,
                    'line': node.lineno,
                    'snippet': _get_line_text(content_lines, node.lineno),
                    'fix': '使用模板文件渲染，避免用用户输入构造模板字符串；启用自动转义',
                })
    
    return results


def check_xml_xxe_ast(context) -> List[Dict]:
    """
    PYAST067 - XML 外部实体注入 XXE 检测（对应 bandit B405-B410）
    
    检测原理：检测 xml.etree / xml.sax / xml.dom / lxml 等 XML 解析器的使用，
    检查是否禁用了外部实体解析。未禁用 XXE 可能导致任意文件读取或 SSRF。
    支持以下调用形式：
      - xml.etree.ElementTree.parse(data)
      - import xml.etree.ElementTree as ET; ET.parse(data)
      - from xml.etree import ElementTree; ElementTree.fromstring(data)
      - lxml.etree.parse(data) / from lxml import etree; etree.parse(data)
    
    风险等级：P0 (高危)
    修复建议：使用 defusedxml 库，或显式禁用外部实体解析（resolve_entities=False 等）。
    """
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    xml_methods = {'parse', 'fromstring', 'parseString', 'XML', 'make_parser'}
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        content_lines = content.split('\n')
        
        # 收集 XML 模块别名
        xml_aliases = set()  # 存储被识别为XML模块的别名
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name
                    # xml.etree.ElementTree, xml.sax, xml.dom.minidom, lxml.etree 等
                    if ('xml' in name.split('.') or 'lxml' in name.split('.')):
                        if any(kw in name for kw in ('etree', 'sax', 'dom', 'minidom', 'pulldom')):
                            xml_aliases.add(alias.asname or name.split('.')[-1])
                            xml_aliases.add(alias.asname or name)
            
            elif isinstance(node, ast.ImportFrom):
                module_name = node.module or ''
                is_xml_module = (
                    'xml' in module_name.split('.') or 
                    'lxml' in module_name.split('.')
                )
                if is_xml_module:
                    for alias in node.names:
                        if alias.name in xml_methods or alias.name in ('ElementTree',):
                            xml_aliases.add(alias.asname or alias.name)
                        # from lxml import etree
                        if alias.name in ('etree', 'sax', 'dom'):
                            xml_aliases.add(alias.asname or alias.name)
        
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            
            attr = node.func
            method_name = attr.attr
            
            if method_name not in xml_methods:
                continue
            
            # 构建模块链名
            module_chain = []
            current = attr.value
            depth = 0
            while isinstance(current, ast.Attribute) and depth < 3:
                module_chain.insert(0, current.attr)
                current = current.value
                depth += 1
            if isinstance(current, ast.Name):
                module_chain.insert(0, current.id)
            
            full_module = '.'.join(module_chain)
            base_name = current.id if isinstance(current, ast.Name) else full_module
            
            # 判断是否为 XML 解析相关
            is_xml_related = False
            parser_desc = f'{full_module}.{method_name}'
            
            # 方式1：完整模块名包含 xml/lxml
            if 'xml' in full_module.lower() or 'lxml' in full_module.lower():
                is_xml_related = True
            
            # 方式2：基名是已识别的 XML 模块别名
            if base_name in xml_aliases:
                is_xml_related = True
            
            if not is_xml_related:
                continue
            
            # 检查是否设置了禁用外部实体的参数
            has_xxe_protection = False
            
            # 检查 lxml / etree 的 no_network / resolve_entities 参数
            for kw in node.keywords:
                if kw.arg in ('resolve_entities', 'no_network', 'load_dtd'):
                    if isinstance(kw.value, ast.Constant):
                        if kw.arg == 'resolve_entities' and kw.value.value is False:
                            has_xxe_protection = True
                        elif kw.arg == 'no_network' and kw.value.value is True:
                            has_xxe_protection = True
                        elif kw.arg == 'load_dtd' and kw.value.value is False:
                            has_xxe_protection = True
            
            if not has_xxe_protection:
                results.append({
                    'id': 'PYAST067',
                    'name': 'XML外部实体注入XXE检测',
                    'level': 'blocking',
                    'category': 'dangerous_functions',
                    'message': f'{parser_desc} 未禁用外部实体解析，存在XXE注入风险',
                    'file': fpath,
                    'line': node.lineno,
                    'snippet': _get_line_text(content_lines, node.lineno),
                    'fix': '使用 defusedxml 库，或显式设置 resolve_entities=False / no_network=True',
                })
    
    return results


def check_hashlib_weak_ast(context) -> List[Dict]:
    """
    PYAST068 - 弱哈希算法用于安全场景检测（对应 bandit B303/B304 / B324）
    
    检测原理：检测 hashlib 中 MD5/SHA1 等弱哈希函数的使用。MD5/SHA1 已被破解，
    不应用于密码存储或数字签名等安全场景。
    
    风险等级：P1 (中危 — 视场景而定)
    修复建议：安全场景使用 SHA-256/SHA-3 或 bcrypt/argon2 等强哈希算法。
    """
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    weak_algorithms = {'md5', 'sha1', 'md4'}
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        content_lines = content.split('\n')
        
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            
            func = node.func
            
            # hashlib.md5() / hashlib.sha1()
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                if func.value.id == 'hashlib' and func.attr in weak_algorithms:
                    results.append({
                        'id': 'PYAST068',
                        'name': '弱哈希算法检测',
                        'level': 'warning',
                        'category': 'dangerous_functions',
                        'message': f'hashlib.{func.attr}() 使用弱哈希算法，不应用于密码存储或安全场景',
                        'file': fpath,
                        'line': node.lineno,
                        'snippet': _get_line_text(content_lines, node.lineno),
                        'fix': '安全场景使用 SHA-256/SHA-3；密码存储使用 bcrypt/argon2/scrypt',
                    })
            
            # hashlib.new('md5')
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                if func.value.id == 'hashlib' and func.attr == 'new' and node.args:
                    algo_name = _is_const_str(node.args[0])
                    if algo_name and algo_name.lower() in weak_algorithms:
                        results.append({
                            'id': 'PYAST068',
                            'name': '弱哈希算法检测',
                            'level': 'warning',
                            'category': 'dangerous_functions',
                            'message': f'hashlib.new("{algo_name}") 使用弱哈希算法',
                            'file': fpath,
                            'line': node.lineno,
                            'snippet': _get_line_text(content_lines, node.lineno),
                            'fix': '安全场景使用 SHA-256/SHA-3；密码存储使用 bcrypt/argon2/scrypt',
                        })
            
            # crypt.cipher 中的弱加密
            # (可选扩展)
    
    return results


def check_unsafe_random_ast(context) -> List[Dict]:
    """
    PYAST069 - 不安全的随机数生成检测（对应 bandit B311）
    
    检测原理：检测 random 模块的随机数生成函数用于安全/密码场景。random 模块
    使用 Mersenne Twister，输出可预测，不应用于密码/安全场景。
    
    风险等级：P1 (中危)
    修复建议：安全场景使用 secrets 模块或 os.urandom()。
    """
    results = []
    
    py_files = context.get_backend_py_files()
    if not py_files:
        return results
    
    random_funcs = {
        'random': 'random.random() 输出可预测，不应用于安全场景',
        'randint': 'random.randint() 输出可预测，不应用于安全场景',
        'choice': 'random.choice() 输出可预测，不应用于安全场景',
        'choices': 'random.choices() 输出可预测，不应用于安全场景',
        'randrange': 'random.randrange() 输出可预测，不应用于安全场景',
        'uniform': 'random.uniform() 输出可预测，不应用于安全场景',
        'sample': 'random.sample() 输出可预测，不应用于安全场景',
        'shuffle': 'random.shuffle() 输出可预测，不应用于安全场景',
    }
    
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        tree = _parse_ast_safe(fpath, content)
        if tree is None:
            continue
        
        content_lines = content.split('\n')
        
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            
            attr = node.func
            if not isinstance(attr.value, ast.Name):
                continue
            
            if attr.value.id != 'random':
                continue
            if attr.attr not in random_funcs:
                continue
            
            results.append({
                'id': 'PYAST069',
                'name': '不安全随机数生成检测',
                'level': 'warning',
                'category': 'dangerous_functions',
                'message': random_funcs[attr.attr],
                'file': fpath,
                'line': node.lineno,
                'snippet': _get_line_text(content_lines, node.lineno),
                'fix': '安全场景使用 secrets 模块：secrets.choice() / secrets.token_hex()',
            })
    
    return results


def check_marshal_shelve_ast(context) -> List[Dict]:
    """
    PYAST070 - marshal/shelve 危险函数（对应 bandit B302）
    
    注：此规则已合并入 PYAST059，本ID保留作为别名。
    实际检测逻辑在 check_pickle_deserialization_ast 中。
    
    为保持规则ID连续，此处保留空检查函数占位。
    """
    # 已合并到 PYAST059，避免重复
    return []


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'PYAST059',
        'name': '危险反序列化函数检测',
        'level': 'blocking',
        'category': 'security_dangerous_functions',
        'module_id': '8',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测 pickle/marshal/shelve/dill 等危险反序列化函数调用（B301/B302）',
        'check': check_pickle_deserialization_ast,
    },
    {
        'id': 'PYAST060',
        'name': 'yaml.load不安全反序列化检测',
        'level': 'blocking',
        'category': 'security_dangerous_functions',
        'module_id': '8',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测 yaml.load 未使用 SafeLoader 的RCE风险（B506）',
        'check': check_yaml_unsafe_load_ast,
    },
    {
        'id': 'PYAST061',
        'name': 'eval/exec动态执行检测',
        'level': 'blocking',
        'category': 'security_dangerous_functions',
        'module_id': '8',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测 eval/exec/execfile 动态代码执行调用（B307）',
        'check': check_eval_exec_ast,
    },
    {
        'id': 'PYAST062',
        'name': 'subprocess shell=True命令注入检测',
        'level': 'blocking',
        'category': 'security_dangerous_functions',
        'module_id': '8',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测 subprocess shell=True 及 os.system/popen 命令注入风险（B404/B602-B607）',
        'check': check_subprocess_shell_ast,
    },
    {
        'id': 'PYAST063',
        'name': 'paramiko主机密钥验证关闭检测',
        'level': 'problem',
        'category': 'security_dangerous_functions',
        'module_id': '8',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测 paramiko AutoAddPolicy/WarningPolicy 关闭主机密钥验证（B507）',
        'check': check_paramiko_missing_host_key_ast,
    },
    {
        'id': 'PYAST064',
        'name': 'SSL证书验证关闭检测',
        'level': 'problem',
        'category': 'security_dangerous_functions',
        'module_id': '8',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测 requests verify=False 及 ssl._create_unverified_context（B308-B310/B501）',
        'check': check_requests_ssl_verify_false_ast,
    },
    {
        'id': 'PYAST065',
        'name': '危险chmod权限设置检测',
        'level': 'problem',
        'category': 'security_dangerous_functions',
        'module_id': '8',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测 chmod 设置其他用户可写等危险权限（B606）',
        'check': check_chmod_unsafe_ast,
    },
    {
        'id': 'PYAST066',
        'name': '模板注入SSTI检测',
        'level': 'blocking',
        'category': 'security_dangerous_functions',
        'module_id': '8',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测 Jinja2/Mako 动态模板构造的SSTI风险（B702）',
        'check': check_template_ssti_ast,
    },
    {
        'id': 'PYAST067',
        'name': 'XML外部实体注入XXE检测',
        'level': 'blocking',
        'category': 'security_dangerous_functions',
        'module_id': '8',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测 xml.etree/xml.sax/lxml 未禁用外部实体的XXE风险（B405-B410）',
        'check': check_xml_xxe_ast,
    },
    {
        'id': 'PYAST068',
        'name': '弱哈希算法检测',
        'level': 'warning',
        'category': 'security_dangerous_functions',
        'module_id': '8',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测 hashlib MD5/SHA1 等弱哈希算法用于安全场景（B303/B304/B324）',
        'check': check_hashlib_weak_ast,
    },
    {
        'id': 'PYAST069',
        'name': '不安全随机数生成检测',
        'level': 'warning',
        'category': 'security_dangerous_functions',
        'module_id': '8',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测 random 模块用于安全场景的可预测随机数（B311）',
        'check': check_unsafe_random_ast,
    },
]

# 供 RuleLoader 发现
ALL_RULES = RULES
