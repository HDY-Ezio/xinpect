"""
AI质检 P0 安全规则 - 异常安全检测 (AI-SEC)
从 security_rules.py 拆分而来，包含:
  AI-SEC-02 裸异常捕获 - Python except: / except: pass、JS空catch块
  AI-SEC-05 静默失败 - catch/except只打log不处理、错误被吞掉用户无感知
"""

import re
import os
import ast
from typing import List, Dict, Any

def _is_defensive_try(body: list) -> bool:
    """判断try块是否为防御性代码（I/O、属性访问、解析等操作的容错保护）
    宁漏勿误：是防御性代码则不标记；只有业务逻辑中的裸except才标记
    
    判断逻辑：
    - 包含I/O/文件/解析/网络调用 → 防御性
    - 包含属性访问/字典取值/getattr → 防御性
    - 纯算术/返回/简单数据处理 → 不是防御性（AI常犯的模式）
    - try块包裹整个函数体且有返回默认值 → 防御性
    """
    if not body:
        return True
    
    # 收集try块中的函数调用名称
    call_names = set()
    has_io = False
    has_attr_access = False
    has_business_logic = False
    has_control_flow = False
    has_import = False
    
    io_func_names = {
        'open', 'read', 'write', 'load', 'loads', 'dump', 'dumps',
        'parse', 'decode', 'encode', 'connect', 'send', 'recv',
        'request', 'get', 'post', 'fetch', 'read_file', 'write_file',
        'walk', 'listdir', 'glob', 'exists', 'isfile', 'isdir',
        'getsize', 'getattr', 'get', 'items', 'keys', 'values',
        'json_loads', 'yaml_load', 'safe_load', 'hasattr', 'setattr',
        'import_module', 'reload', '__import__', 'safe_read',
        'find_files', 'score_file', 'exec_module', 'spec_from_file_location',
        'module_from_spec', 'is_ops_script',
    }
    
    def _collect_calls(node):
        """递归收集函数调用名"""
        nonlocal has_io, has_attr_access, has_business_logic, has_control_flow, has_import
        
        if isinstance(node, ast.Import) or isinstance(node, ast.ImportFrom):
            has_import = True
            has_io = True  # 导入操作视为防御性
        
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                call_names.add(func.id)
                if func.id in io_func_names:
                    has_io = True
            elif isinstance(func, ast.Attribute):
                call_names.add(func.attr)
                if func.attr in io_func_names:
                    has_io = True
        
        if isinstance(node, (ast.Attribute, ast.Subscript)):
            has_attr_access = True
        
        # 算术运算才是业务逻辑特征（比较操作Compare在防御性代码中也很常见）
        if isinstance(node, (ast.BinOp, ast.UnaryOp)):
            has_business_logic = True
        
        if isinstance(node, (ast.For, ast.While, ast.If, ast.With)):
            has_control_flow = True
        
        # 递归子节点
        for child in ast.iter_child_nodes(node):
            _collect_calls(child)
    
    for stmt in body:
        _collect_calls(stmt)
    
    # 明显的I/O操作 → 防御性
    if has_io:
        return True
    
    # 有导入操作 → 防御性
    if has_import:
        return True
    
    # 只有属性访问/字典取值 → 防御性
    if has_attr_access and not has_business_logic and not has_control_flow:
        return True
    
    # 1-2条语句且没有算术运算 → 大概率是防御性代码（调用个函数、判断个条件）
    if len(body) <= 2 and not has_business_logic:
        return True
    
    # 3条以上语句且有控制流 + 有业务逻辑算术 → 可能是业务逻辑
    if has_control_flow and has_business_logic and len(body) >= 3:
        return False
    
    # 中等复杂度，没有明确业务逻辑 → 保守视为防御性（宁漏勿误）
    if len(body) <= 8:
        return True
    
    return False


def _is_defensive_except_handler(handler) -> bool:
    """判断except handler本身是否是防御性模式
    宁漏勿误：以下模式视为防御性，不标记
    - except: continue (循环中跳过错误项)
    - except: return 默认值 (函数级别的容错返回)
    """
    body = handler.body
    if not body:
        return True
    
    # except: continue → 循环中跳过失败项，典型防御模式
    if len(body) == 1 and isinstance(body[0], ast.Continue):
        return True
    
    # except: return 简单值 → 防御性返回默认值
    if len(body) == 1 and isinstance(body[0], ast.Return):
        ret = body[0]
        if ret.value is None:
            return True
        if isinstance(ret.value, ast.Constant):
            # 返回常量默认值 (0, 0.0, '', [], {}, False, None)
            return True
        if isinstance(ret.value, (ast.List, ast.Dict, ast.Set)):
            # 返回空容器
            if len(ret.value.elts if hasattr(ret.value, 'elts') else ret.value.keys) == 0:
                return True
    
    return False


def check_ai_sec_02_bare_except(context) -> List[Dict]:
    """AI-SEC-02 裸异常捕获
    AI生成代码常见问题：except: 或 except: pass 吞掉所有异常
    误报控制：排除防御性I/O、简单属性访问等合理的裸except场景
    """
    results = []
    
    py_files = [f for f in context.get_filtered_files("security") 
                if f.endswith(".py") and os.path.basename(f) != "__init__.py"]
    js_files = [f for f in context.get_filtered_files("security") if f.endswith((".js", ".ts", ".jsx", ".tsx"))]
    
    if not py_files and not js_files:
        return results
    
    issue_files = []
    
    # ===== Python 检测 =====
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        file_issues = []
        
        try:
            _sum = context.get_ast_summary(fpath)
            if not _sum:
                continue
            lines = content.split('\n')
            
            for _tb in _sum.get('try_blocks', []):
                node = _tb['node']
                for handler in node.handlers:
                    # 只检查裸except（无类型）或 except Exception: pass
                    is_bare = handler.type is None
                    is_exception_pass = (
                        isinstance(handler.type, ast.Name) 
                        and handler.type.id == 'Exception'
                        and len(handler.body) == 1 
                        and isinstance(handler.body[0], ast.Pass)
                    )
                    
                    if not is_bare and not is_exception_pass:
                        continue
                    
                    # 防御性代码判定：try块内容是防御性的 → 不标记
                    if _is_defensive_try(node.body):
                        continue
                    
                    # 防御性代码判定：except handler本身是防御性模式 → 不标记
                    if _is_defensive_except_handler(handler):
                        continue
                    
                    lineno = handler.lineno
                    
                    if is_bare:
                        has_pass = len(handler.body) == 1 and isinstance(handler.body[0], ast.Pass)
                        desc = "裸except捕获所有异常" + ("且直接pass（异常被完全吞掉）" if has_pass else "")
                    else:
                        desc = "except Exception后直接pass（异常被完全吞掉）"
                    
                    file_issues.append({
                        'line': lineno,
                        'desc': desc,
                        'snippet': lines[lineno - 1].strip() if lineno - 1 < len(lines) else "",
                    })
        except SyntaxError:
            continue
        
        if file_issues:
            rel = os.path.relpath(fpath, context.project_path or context.backend_path or ".")
            issue_files.append((rel, fpath, file_issues))
    
    # ===== JS/TS 检测 =====
    for fpath in js_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        lines = content.split('\n')
        file_issues = []
        
        # 匹配 catch {} 空catch块
        # 简化版：找catch后跟空块的模式
        catch_empty_pattern = re.compile(r'catch\s*(?:\([^)]*\))?\s*\{\s*\}', re.MULTILINE)
        
        for m in catch_empty_pattern.finditer(content):
            line_num = content[:m.start()].count('\n') + 1
            file_issues.append({
                'line': line_num,
                'desc': '空catch块（异常被完全吞掉）',
                'snippet': lines[line_num - 1].strip() if line_num - 1 < len(lines) else "",
            })
        
        if file_issues:
            rel = os.path.relpath(fpath, context.project_path or context.backend_path or ".")
            issue_files.append((rel, fpath, file_issues))
    
    if issue_files:
        total_issues = sum(len(issues) for _, _, issues in issue_files)
        
        # 生成问题详情
        detail_lines = []
        for rel, _, issues in issue_files[:10]:
            for issue in issues[:3]:
                detail_lines.append(f"{rel}:{issue['line']} - {issue['desc']}")
        
        results.append({
            'id': 'AI-SEC-02',
            'name': '裸异常捕获',
            'level': 'error',  # 高危
            'message': f'发现 {total_issues} 处裸异常捕获/空catch块（异常被吞掉）',
            'detail': '\n'.join(detail_lines),
            'file': issue_files[0][1] if issue_files else '',
            'line': issue_files[0][2][0]['line'] if issue_files and issue_files[0][2] else 0,
            'snippet': detail_lines[0] if detail_lines else '',
            'fix': '捕获具体的异常类型，记录错误日志并做适当的错误处理，不要吞掉异常',
            'category': 'ai_security',
        })
    
    return results


# ===== AI-SEC-03 危险函数 =====


def check_ai_sec_05_silent_failure(context) -> List[Dict]:
    """AI-SEC-05 静默失败检测
    AI生成代码常见：catch/except只打log不处理，错误被吞掉用户无感知
    注意：区别于AI-SEC-02（完全空/裸except），本条是有日志但无实际错误处理
    误报控制：排除防御性代码（简单try块+只打日志是合理的）
    """
    results = []
    
    py_files = [f for f in context.find_files([".py"])
                if os.path.basename(f) != "__init__.py"]
    js_files = [f for f in context.get_filtered_files("security") if f.endswith((".js", ".ts", ".jsx", ".tsx"))]
    
    if not py_files and not js_files:
        return results
    
    all_issues = []
    
    # ===== Python: 检查except块中只有log没有错误处理 =====
    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        rel = os.path.relpath(fpath, context.project_path or context.backend_path or ".")
        
        try:
            tree = context.parse_ast(fpath)
            if tree is None:
                continue
            lines = content.split('\n')
            
            for node in ast.walk(tree):
                if not isinstance(node, ast.Try):
                    continue
                
                # 跳过裸except（已由AI-SEC-02检测）
                for handler in node.handlers:
                    if handler.type is None:
                        continue
                    
                    body = handler.body
                    if not body:
                        continue
                    
                    # 检查except块中的语句
                    log_only = True
                    has_raise = False
                    has_return = False
                    
                    for stmt in body:
                        if isinstance(stmt, ast.Raise):
                            has_raise = True
                            log_only = False
                            break
                        if isinstance(stmt, ast.Return):
                            has_return = True
                            log_only = False
                            break
                        
                        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                            call = stmt.value
                            func_str = ast.unparse(call.func) if hasattr(ast, 'unparse') else ''
                            
                            is_log = any(kw in func_str.lower() 
                                        for kw in ['print', 'logger', 'logging', 'log.', 
                                                  'print(', 'console.'])
                            
                            if not is_log:
                                log_only = False
                                break
                        elif isinstance(stmt, ast.Assign):
                            log_only = False
                            break
                        elif isinstance(stmt, (ast.If, ast.For, ast.While, ast.Try, ast.With)):
                            log_only = False
                            break
                        elif isinstance(stmt, ast.Pass):
                            # pass 语句，已由AI-SEC-02处理
                            pass
                        else:
                            # 其他语句类型也认为"有处理"
                            log_only = False
                            break
                    
                    if log_only and not has_raise and not has_return:
                        # 误报控制：如果try块是简单的防御性代码，不标记
                        if _is_defensive_try(node.body):
                            continue
                        
                        lineno = handler.lineno
                        all_issues.append({
                            'file': fpath,
                            'rel': rel,
                            'line': lineno,
                            'desc': 'except块仅打印日志，无错误处理（静默失败）',
                            'snippet': lines[lineno - 1].strip() if lineno - 1 < len(lines) else "",
                            'severity': 'medium',
                        })
        except SyntaxError:
            continue
    
    # ===== JS/TS: 检查catch块中只有console.log =====
    for fpath in js_files:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        lines = content.split('\n')
        rel = os.path.relpath(fpath, context.project_path or context.backend_path or ".")
        
        # 找catch块
        catch_pattern = re.compile(r'catch\s*(?:\([^)]*\))?\s*\{', re.MULTILINE)
        
        for m in catch_pattern.finditer(content):
            start_pos = m.end() - 1  # { 的位置
            
            # 找匹配的 }
            depth = 1
            pos = start_pos + 1
            while pos < len(content) and depth > 0:
                if content[pos] == '{':
                    depth += 1
                elif content[pos] == '}':
                    depth -= 1
                pos += 1
            
            if depth > 0:
                continue
            
            block_content = content[start_pos + 1:pos - 1].strip()
            line_num = content[:m.start()].count('\n') + 1
            
            # 空catch块已由AI-SEC-02检测
            if not block_content:
                continue
            
            # 检查是否只有console.log/console.error
            # 移除所有console.*调用后看是否还有实质内容
            cleaned = re.sub(r'console\.\w+\s*\([^)]*\)\s*;?', '', block_content)
            cleaned = re.sub(r'//[^\n]*', '', cleaned)
            cleaned = re.sub(r'/\*.*?\*/', '', cleaned, flags=re.DOTALL)
            cleaned = cleaned.strip().strip(';').strip()
            
            if not cleaned:
                all_issues.append({
                    'file': fpath,
                    'rel': rel,
                    'line': line_num,
                    'desc': 'catch块仅打印日志，无错误处理（静默失败）',
                    'snippet': lines[line_num - 1].strip() if line_num - 1 < len(lines) else "",
                    'severity': 'medium',
                })
    
    if all_issues:
        total = len(all_issues)
        detail_lines = [
            f"{issue['rel']}:{issue['line']} - {issue['desc']}"
            for issue in all_issues[:15]
        ]
        
        results.append({
            'id': 'AI-SEC-05',
            'name': '静默失败检测',
            'level': 'warning',  # 中危
            'message': f'发现 {total} 处静默失败（异常仅打日志无实际处理）',
            'detail': '\n'.join(detail_lines),
            'file': all_issues[0]['file'] if all_issues else '',
            'line': all_issues[0]['line'] if all_issues else 0,
            'snippet': all_issues[0]['snippet'] if all_issues else '',
            'fix': '异常应有实际处理逻辑：抛出错误、返回错误值、触发告警等，不能仅打日志',
            'category': 'ai_security',
        })
    
    return results


# ===== 规则定义列表 =====


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'AI-SEC-02',
        'name': '裸异常捕获',
        'level': 'blocking',
        'category': 'ai_code_check',
        'module_id': 'ai_security',
        'applicable_types': [],
        'description': '检测裸except/空catch块，AI生成代码常吞掉所有异常',
        'check': check_ai_sec_02_bare_except,
    },
    {
        'id': 'AI-SEC-05',
        'name': '静默失败检测',
        'level': 'problem',
        'category': 'ai_code_check',
        'module_id': 'ai_security',
        'applicable_types': [],
        'description': '检测catch/except只打log不处理的静默失败模式',
        'check': check_ai_sec_05_silent_failure,
    },
]
