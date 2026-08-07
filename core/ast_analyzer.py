"""
Python AST分析器 - QA框架P1阶段核心组件
基于Python标准库ast模块，提供代码级语义分析能力
用于替代部分纯正则匹配规则，大幅降低误报率

API:
- parse_file(file_path) -> AST树
- find_function_calls(tree, func_names) -> 函数调用位置列表
- find_string_literals(tree) -> 字符串字面量列表
- get_imports(tree) -> import语句列表
- is_in_string_literal(tree, line_num, col_offset) -> 是否在字符串内
- get_function_defs(tree) -> 函数定义列表
"""

import ast
import os
from typing import List, Dict, Tuple, Optional, Any


class ASTAnalysisError(Exception):
    """AST分析异常"""
    pass


class PythonASTAnalyzer:
    """Python AST分析器
    
    提供基于抽象语法树的代码分析能力，用于：
    1. 确认代码上下文（而非字符串/注释）
    2. 精确定位函数调用
    3. 识别import依赖
    4. 变量作用域分析
    """
    
    def __init__(self):
        self._cache = {}  # {file_path: (tree, source_lines)}
        self._parse_errors = set()  # 解析失败的文件缓存
    
    def parse_file(self, file_path: str) -> Optional[ast.AST]:
        """解析Python文件为AST树
        
        Args:
            file_path: Python文件路径
            
        Returns:
            AST树对象，解析失败返回None
        """
        if file_path in self._cache:
            return self._cache[file_path][0]
        
        if file_path in self._parse_errors:
            return None
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                source = f.read()
            tree = ast.parse(source, filename=file_path)
            lines = source.split('\n')
            self._cache[file_path] = (tree, lines)
            return tree
        except (SyntaxError, UnicodeDecodeError, OSError):
            self._parse_errors.add(file_path)
            return None
    
    def _get_source_lines(self, file_path: str) -> List[str]:
        """获取文件源码行（带缓存）"""
        if file_path in self._cache:
            return self._cache[file_path][1]
        # 触发解析以填充缓存
        self.parse_file(file_path)
        if file_path in self._cache:
            return self._cache[file_path][1]
        return []
    
    def find_function_calls(
        self,
        tree: ast.AST,
        func_names: List[str],
        file_path: str = ""
    ) -> List[Dict[str, Any]]:
        """查找指定函数名的调用位置
        
        Args:
            tree: AST树
            func_names: 要查找的函数名列表（如 ['eval', 'exec']）
            file_path: 源文件路径（用于结果中）
            
        Returns:
            函数调用信息列表，每项包含:
            - name: 函数名
            - line: 行号
            - col: 列号
            - is_method: 是否为方法调用（如 obj.func()）
            - full_name: 完整调用名（如 requests.get）
        """
        results = []
        func_name_set = set(func_names)
        
        class CallVisitor(ast.NodeVisitor):
            def visit_Call(self, node):
                func = node.func
                name = ""
                full_name = ""
                is_method = False
                
                if isinstance(func, ast.Name):
                    # 直接调用: func()
                    name = func.id
                    full_name = func.id
                elif isinstance(func, ast.Attribute):
                    # 方法调用: obj.func()
                    is_method = True
                    name = func.attr
                    # 尝试获取完整调用链
                    full_name = self._get_attr_chain(func)
                
                if name in func_name_set:
                    results.append({
                        'name': name,
                        'full_name': full_name,
                        'line': node.lineno,
                        'col': node.col_offset,
                        'is_method': is_method,
                        'file': file_path,
                        'args_count': len(node.args),
                        'has_kwargs': len(node.keywords) > 0,
                    })
                
                self.generic_visit(node)
            
            def _get_attr_chain(self, node: ast.Attribute) -> str:
                """获取属性调用链，如 requests.get.get"""
                parts = []
                current = node
                while isinstance(current, ast.Attribute):
                    parts.append(current.attr)
                    current = current.value
                if isinstance(current, ast.Name):
                    parts.append(current.id)
                return '.'.join(reversed(parts))
        
        CallVisitor().visit(tree)
        return results
    
    def find_string_literals(
        self,
        tree: ast.AST,
        file_path: str = ""
    ) -> List[Dict[str, Any]]:
        """查找所有字符串字面量的位置
        
        Args:
            tree: AST树
            file_path: 源文件路径
            
        Returns:
            字符串字面量信息列表，每项包含:
            - value: 字符串值
            - line: 起始行号
            - end_line: 结束行号
            - col: 起始列号
            - end_col: 结束列号
            - is_docstring: 是否为文档字符串
        """
        results = []
        
        class StringVisitor(ast.NodeVisitor):
            def visit_Str(self, node):
                results.append({
                    'value': node.s,
                    'line': node.lineno,
                    'end_line': getattr(node, 'end_lineno', node.lineno),
                    'col': node.col_offset,
                    'end_col': getattr(node, 'end_col_offset', node.col_offset + len(node.s)),
                    'is_docstring': False,
                    'file': file_path,
                })
                self.generic_visit(node)
            
            def visit_Constant(self, node):
                if isinstance(node.value, str):
                    # 检查是否为docstring（父节点是FunctionDef/ClassDef/Module的第一个语句）
                    is_doc = self._is_docstring(node)
                    results.append({
                        'value': node.value,
                        'line': node.lineno,
                        'end_line': getattr(node, 'end_lineno', node.lineno),
                        'col': node.col_offset,
                        'end_col': getattr(node, 'end_col_offset', node.col_offset + len(node.value)),
                        'is_docstring': is_doc,
                        'file': file_path,
                    })
                self.generic_visit(node)
            
            def _is_docstring(self, node: ast.Constant) -> bool:
                """判断是否为文档字符串"""
                # 简化判断：父节点判断需要父指针，这里通过后续处理补充
                return False
        
        StringVisitor().visit(tree)
        
        # 补充docstring判断（遍历函数/类定义的第一个语句）
        class DocstringVisitor(ast.NodeVisitor):
            def _check_docstring(self, body):
                if body and isinstance(body[0], ast.Expr):
                    val = body[0].value
                    str_val = None
                    if isinstance(val, ast.Constant) and isinstance(val.value, str):
                        str_val = val.value
                    elif isinstance(val, ast.Str):
                        str_val = val.s
                    if str_val is not None:
                        # 标记对应的字符串为docstring
                        for r in results:
                            if r['line'] == body[0].lineno and r['value'] == str_val:
                                r['is_docstring'] = True
                                break
            
            def visit_FunctionDef(self, node):
                self._check_docstring(node.body)
                self.generic_visit(node)
            
            def visit_AsyncFunctionDef(self, node):
                self._check_docstring(node.body)
                self.generic_visit(node)
            
            def visit_ClassDef(self, node):
                self._check_docstring(node.body)
                self.generic_visit(node)
            
            def visit_Module(self, node):
                self._check_docstring(node.body)
                self.generic_visit(node)
        
        DocstringVisitor().visit(tree)
        
        return results
    
    def get_imports(
        self,
        tree: ast.AST,
        file_path: str = ""
    ) -> List[Dict[str, Any]]:
        """获取所有import语句
        
        Args:
            tree: AST树
            file_path: 源文件路径
            
        Returns:
            import信息列表，每项包含:
            - module: 模块名
            - names: 导入的名称列表（from import时）
            - alias: 别名（import ... as ...）
            - line: 行号
            - is_from: 是否为from ... import ...
        """
        results = []
        
        class ImportVisitor(ast.NodeVisitor):
            def visit_Import(self, node):
                for alias in node.names:
                    results.append({
                        'module': alias.name,
                        'names': [],
                        'alias': alias.asname or alias.name,
                        'line': node.lineno,
                        'is_from': False,
                        'file': file_path,
                    })
                self.generic_visit(node)
            
            def visit_ImportFrom(self, node):
                module = node.module or ""
                names = [a.name for a in node.names]
                aliases = {a.name: a.asname for a in node.names if a.asname}
                
                results.append({
                    'module': module,
                    'names': names,
                    'alias_map': aliases,
                    'line': node.lineno,
                    'is_from': True,
                    'level': node.level,  # 相对导入级别
                    'file': file_path,
                })
                self.generic_visit(node)
        
        ImportVisitor().visit(tree)
        return results
    
    def is_in_string_literal(
        self,
        tree: ast.AST,
        line_num: int,
        col_offset: int = 0
    ) -> bool:
        """判断指定位置是否在字符串字面量内
        
        Args:
            tree: AST树
            line_num: 行号（1-based）
            col_offset: 列偏移（0-based）
            
        Returns:
            True表示在字符串字面量内
        """
        strings = self.find_string_literals(tree)
        
        for s in strings:
            start_line = s['line']
            end_line = s['end_line']
            
            if line_num < start_line or line_num > end_line:
                continue
            
            if start_line == end_line:
                # 单行字符串
                if s['col'] <= col_offset <= s['end_col']:
                    return True
            elif line_num == start_line:
                # 多行字符串的第一行
                if col_offset >= s['col']:
                    return True
            elif line_num == end_line:
                # 多行字符串的最后一行
                if col_offset <= s['end_col']:
                    return True
            else:
                # 多行字符串的中间行
                return True
        
        return False
    
    def is_in_comment(
        self,
        file_path: str,
        line_num: int
    ) -> bool:
        """判断指定行是否为注释行
        
        注意：AST不包含注释信息，需通过源码判断
        
        Args:
            file_path: 源文件路径
            line_num: 行号（1-based）
            
        Returns:
            True表示该行是注释行或注释后内容
        """
        lines = self._get_source_lines(file_path)
        if not lines or line_num < 1 or line_num > len(lines):
            return False
        
        stripped = lines[line_num - 1].strip()
        return stripped.startswith('#')
    
    def get_function_defs(
        self,
        tree: ast.AST,
        file_path: str = ""
    ) -> List[Dict[str, Any]]:
        """获取所有函数定义
        
        Args:
            tree: AST树
            file_path: 源文件路径
            
        Returns:
            函数定义信息列表
        """
        results = []
        
        class FuncDefVisitor(ast.NodeVisitor):
            def visit_FunctionDef(self, node):
                results.append({
                    'name': node.name,
                    'line': node.lineno,
                    'end_line': getattr(node, 'end_lineno', node.lineno),
                    'args_count': len(node.args.args),
                    'is_async': False,
                    'decorators': [self._get_decorator_name(d) for d in node.decorator_list],
                    'file': file_path,
                })
                self.generic_visit(node)
            
            def visit_AsyncFunctionDef(self, node):
                results.append({
                    'name': node.name,
                    'line': node.lineno,
                    'end_line': getattr(node, 'end_lineno', node.lineno),
                    'args_count': len(node.args.args),
                    'is_async': True,
                    'decorators': [self._get_decorator_name(d) for d in node.decorator_list],
                    'file': file_path,
                })
                self.generic_visit(node)
            
            def _get_decorator_name(self, node) -> str:
                if isinstance(node, ast.Name):
                    return node.id
                elif isinstance(node, ast.Attribute):
                    return self._get_attr_name(node)
                elif isinstance(node, ast.Call):
                    return self._get_decorator_name(node.func)
                return ""
            
            def _get_attr_name(self, node: ast.Attribute) -> str:
                parts = []
                current = node
                while isinstance(current, ast.Attribute):
                    parts.append(current.attr)
                    current = current.value
                if isinstance(current, ast.Name):
                    parts.append(current.id)
                return '.'.join(reversed(parts))
        
        FuncDefVisitor().visit(tree)
        return results
    
    def check_sql_injection_risk(
        self,
        tree: ast.AST,
        file_path: str = ""
    ) -> List[Dict[str, Any]]:
        """检测SQL注入风险（AST辅助版本）
        
        通过AST分析，只报告真正的代码执行上下文，
        排除字符串字面量、注释、docstring中的误报
        
        Args:
            tree: AST树
            file_path: 源文件路径
            
        Returns:
            SQL注入风险点列表
        """
        risks = []
        
        class SQLInjectionVisitor(ast.NodeVisitor):
            def visit_Call(self, node):
                func = node.func
                func_name = ""
                
                if isinstance(func, ast.Name):
                    func_name = func.id
                elif isinstance(func, ast.Attribute):
                    func_name = func.attr
                
                # 检测数据库执行函数
                db_exec_funcs = {'execute', 'executemany', 'query', 'raw', 'executescript'}
                
                if func_name.lower() in db_exec_funcs and node.args:
                    first_arg = node.args[0]
                    
                    # 参数化查询检测：如果有多个位置参数或有关键字参数，
                    # 很可能是参数化查询，风险降低
                    has_params = len(node.args) > 1 or len(node.keywords) > 0
                    
                    # 检查第一个参数是否为动态拼接的SQL
                    is_dynamic, dynamic_type = self._is_dynamic_sql(first_arg)
                    
                    if is_dynamic:
                        # 根据动态类型和是否有参数确定置信度
                        if dynamic_type in ('fstring', 'concat', 'format', 'percent') and not has_params:
                            confidence = 'high'
                            reason = '数据库查询参数为动态拼接字符串'
                        elif dynamic_type == 'variable' and not has_params:
                            confidence = 'medium'
                            reason = '数据库查询参数来自变量，需确认是否为动态拼接'
                        elif dynamic_type in ('fstring', 'concat', 'format', 'percent') and has_params:
                            # 有参数但SQL本身是动态的，仍有风险
                            confidence = 'medium'
                            reason = '数据库查询SQL为动态拼接（虽有参数仍需确认）'
                        else:
                            confidence = 'low'
                            reason = '数据库查询参数来源待确认'
                        
                        risks.append({
                            'type': 'sql_injection',
                            'func_name': func_name,
                            'line': node.lineno,
                            'col': node.col_offset,
                            'file': file_path,
                            'confidence': confidence,
                            'reason': reason,
                            'dynamic_type': dynamic_type,
                            'has_params': has_params,
                        })
                
                self.generic_visit(node)
            
            def _is_dynamic_sql(self, node: ast.AST) -> tuple:
                """判断SQL参数是否为动态拼接
                
                Returns:
                    (is_dynamic, dynamic_type)
                    dynamic_type: 'fstring' | 'concat' | 'format' | 'percent' | 'variable' | ''
                """
                # f-string: 包含变量插值
                if isinstance(node, ast.JoinedStr):
                    has_interpolation = any(
                        isinstance(v, ast.FormattedValue) for v in node.values
                    )
                    if has_interpolation:
                        return True, 'fstring'
                    return False, ''
                
                # 字符串拼接: "..." + var + "..."
                if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
                    return True, 'concat'
                
                # 百分号格式化: "..." % var
                if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
                    left_str = isinstance(node.left, ast.Constant) and isinstance(node.left.value, str)
                    if left_str:
                        return True, 'percent'
                
                # .format() 调用
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if node.func.attr == 'format':
                        return True, 'format'
                
                # 变量引用（不是字面量）
                if isinstance(node, ast.Name):
                    return True, 'variable'
                
                # 函数调用返回值
                if isinstance(node, ast.Call):
                    return True, 'variable'
                
                return False, ''
        
        SQLInjectionVisitor().visit(tree)
        return risks
    
    def check_command_injection_risk(
        self,
        tree: ast.AST,
        file_path: str = ""
    ) -> List[Dict[str, Any]]:
        """检测命令注入风险（AST辅助版本）
        
        Args:
            tree: AST树
            file_path: 源文件路径
            
        Returns:
            命令注入风险点列表
        """
        risks = []
        
        # 危险函数列表
        dangerous_funcs = {
            'os.system': 'system',
            'os.popen': 'popen',
            'subprocess.call': 'call',
            'subprocess.run': 'run',
            'subprocess.Popen': 'Popen',
            'subprocess.getoutput': 'getoutput',
            'eval': 'eval',
            'exec': 'exec',
        }
        
        class CommandInjectionVisitor(ast.NodeVisitor):
            def visit_Call(self, node):
                func = node.func
                full_name = ""
                
                if isinstance(func, ast.Name):
                    full_name = func.id
                elif isinstance(func, ast.Attribute):
                    full_name = self._get_full_name(func)
                
                # 检查是否为危险函数
                is_dangerous = False
                func_short = ""
                
                for dangerous, short_name in dangerous_funcs.items():
                    if full_name.endswith(dangerous) or full_name == short_name:
                        is_dangerous = True
                        func_short = short_name
                        break
                
                if is_dangerous and node.args:
                    first_arg = node.args[0]
                    
                    # 检查参数是否包含变量（可能用户可控）
                    has_variable = self._has_variable_input(first_arg)
                    
                    if has_variable:
                        risks.append({
                            'type': 'command_injection',
                            'func_name': full_name or func_short,
                            'line': node.lineno,
                            'col': node.col_offset,
                            'file': file_path,
                            'confidence': 'medium' if full_name else 'high',
                            'reason': f'{func_short}() 参数包含变量，可能存在命令注入风险',
                        })
                
                self.generic_visit(node)
            
            def _get_full_name(self, node: ast.Attribute) -> str:
                parts = []
                current = node
                while isinstance(current, ast.Attribute):
                    parts.append(current.attr)
                    current = current.value
                if isinstance(current, ast.Name):
                    parts.append(current.id)
                return '.'.join(reversed(parts))
            
            def _has_variable_input(self, node: ast.AST) -> bool:
                """检查参数是否包含变量输入"""
                if isinstance(node, ast.Name):
                    return True
                if isinstance(node, ast.JoinedStr):
                    return any(isinstance(v, ast.FormattedValue) for v in node.values)
                if isinstance(node, ast.BinOp):
                    return self._has_variable_input(node.left) or self._has_variable_input(node.right)
                if isinstance(node, ast.Call):
                    return True  # 函数返回值可能是动态的
                if isinstance(node, ast.Subscript):
                    return True  # 下标访问可能是动态的
                if isinstance(node, (ast.List, ast.Tuple)):
                    return any(self._has_variable_input(e) for e in node.elts)
                return False
        
        CommandInjectionVisitor().visit(tree)
        return risks
    
    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()
        self._parse_errors.clear()


# 全局单例
_analyzer = None


def get_ast_analyzer() -> PythonASTAnalyzer:
    """获取AST分析器单例"""
    global _analyzer
    if _analyzer is None:
        _analyzer = PythonASTAnalyzer()
    return _analyzer


# ===== 便捷API函数 =====

def parse_file(file_path: str) -> Optional[ast.AST]:
    """便捷API：解析Python文件"""
    return get_ast_analyzer().parse_file(file_path)


def find_function_calls(
    source: Any,
    func_names: List[str],
    file_path: str = ""
) -> List[Dict[str, Any]]:
    """便捷API：查找函数调用
    
    Args:
        source: AST树 或 文件路径字符串
        func_names: 函数名列表
        file_path: 文件路径（当source是AST树时使用）
    """
    analyzer = get_ast_analyzer()
    
    if isinstance(source, str):
        # source是文件路径
        tree = analyzer.parse_file(source)
        if tree is None:
            return []
        return analyzer.find_function_calls(tree, func_names, source)
    else:
        # source是AST树
        return analyzer.find_function_calls(source, func_names, file_path)


def find_string_literals(
    source: Any,
    file_path: str = ""
) -> List[Dict[str, Any]]:
    """便捷API：查找字符串字面量"""
    analyzer = get_ast_analyzer()
    
    if isinstance(source, str):
        tree = analyzer.parse_file(source)
        if tree is None:
            return []
        return analyzer.find_string_literals(tree, source)
    else:
        return analyzer.find_string_literals(source, file_path)


def get_imports(
    source: Any,
    file_path: str = ""
) -> List[Dict[str, Any]]:
    """便捷API：获取import语句"""
    analyzer = get_ast_analyzer()
    
    if isinstance(source, str):
        tree = analyzer.parse_file(source)
        if tree is None:
            return []
        return analyzer.get_imports(tree, source)
    else:
        return analyzer.get_imports(source, file_path)


def is_in_comment_or_string(
    file_path: str,
    line_num: int,
    col_offset: int = 0
) -> bool:
    """便捷API：判断位置是否在注释或字符串内
    
    Args:
        file_path: Python文件路径
        line_num: 行号（1-based）
        col_offset: 列偏移（0-based）
        
    Returns:
        True表示在注释或字符串字面量内
    """
    analyzer = get_ast_analyzer()
    
    # 先检查是否是注释行
    if analyzer.is_in_comment(file_path, line_num):
        return True
    
    # 再检查是否在字符串字面量内
    tree = analyzer.parse_file(file_path)
    if tree is None:
        return False  # AST解析失败时，保守返回False（不误报过滤）
    
    return analyzer.is_in_string_literal(tree, line_num, col_offset)
