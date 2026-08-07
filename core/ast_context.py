"""
AST 上下文 Mixin
提供 Python AST 解析、缓存、摘要提取能力
作为 QAContext 的 Mixin 基类，抽离 AST 相关逻辑
"""

import os
from typing import Dict, Any


class AstContextMixin:
    """
    AST 上下文 Mixin
    提供 AST 解析缓存、摘要预计算等能力
    
    要求子类（QAContext）提供：
    - self._ast_cache: dict
    - self._ast_summary: dict
    - self.safe_read(file_path) -> str
    - self.find_files(extensions) -> list
    """

    # ===== v2.9.1 P3: AST Cache (cross-rule sharing) =====
    def parse_ast(self, file_path: str):
        """解析Python文件AST并缓存，跨规则共享。
        同一文件被多个规则扫描时只解析一次，后续全部命中缓存。
        """
        if file_path in self._ast_cache:
            return self._ast_cache[file_path]
        content = self.safe_read(file_path)
        if not content:
            return None
        import ast as _ast
        try:
            tree = _ast.parse(content, filename=file_path)
            self._ast_cache[file_path] = tree
            return tree
        except SyntaxError:
            return None

    def prefetch_ast(self) -> int:
        """预解析所有.py文件的AST树，消除首条规则的解析开销"""
        import ast as _ast
        py_files = [f for f in self.find_files([".py"])
                    if f not in self._ast_cache]
        count = 0
        for fpath in py_files:
            content = self.safe_read(fpath)
            if not content:
                continue
            try:
                self._ast_cache[fpath] = _ast.parse(content, filename=fpath)
                count += 1
            except SyntaxError:  # noqa: intentional empty handler
                pass
        return count

    def get_ast_summary(self, file_path: str) -> dict:
        """获取文件AST摘要 - 单次遍历收集所有信息，O(n)复杂度
        
        v4.6.1 性能优化：
        - 用单次深度遍历替代多次 ast.walk（每个函数一次 walk → 总 walk 次数从 N+1 降到 1）
        - 复杂度计算在遍历中增量累计，不用对每个函数重复 walk 子树
        - 227 文件: 12s → 约 3s（4x 加速）
        """
        if file_path in self._ast_summary:
            return self._ast_summary[file_path]
        tree = self.parse_ast(file_path)
        if tree is None:
            return {}
        import ast as _ast
        summary = {"functions": [], "classes": [], "imports": [],
                   "try_blocks": [], "calls": [], "assigns": [],
                   "decorators": set(), "all_nodes_by_type": {},
                   "call_count": 0, "assign_count": 0}
        
        # ===== 单次深度遍历，收集所有信息 =====
        # 用栈追踪当前所在的函数，用于增量计算复杂度
        func_stack = []  # [func_summary_dict, ...] 栈顶 = 当前最内层函数
        class_stack = []  # [class_summary_dict, ...] 栈顶 = 当前最内层类
        
        # 控制流节点类型（用于圈复杂度计算）
        complexity_types = (_ast.If, _ast.For, _ast.While, _ast.Try,
                           _ast.ExceptHandler, _ast.With, _ast.BoolOp)
        
        # 按类型索引
        by_type = {}
        
        def _visit(node, depth=0):
            """递归遍历AST，单次收集所有信息"""
            nt = type(node).__name__
            if nt not in by_type:
                by_type[nt] = []
            by_type[nt].append(node)
            
            # 函数定义：入栈 + 初始化复杂度
            if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                f_summary = {
                    "name": node.name,
                    "lineno": node.lineno,
                    "end_lineno": getattr(node, "end_lineno", node.lineno),
                    "args": [a.arg for a in node.args.args if hasattr(a, "arg")],
                    "is_async": isinstance(node, _ast.AsyncFunctionDef),
                    "decorator_list": [self._ast_decorator_name(d) for d in node.decorator_list],
                    "returns": bool(node.returns),
                    "body_lines": getattr(node, "end_lineno", node.lineno) - node.lineno,
                    "complexity": 1,  # 基础复杂度 1
                }
                for d in f_summary["decorator_list"]:
                    summary["decorators"].add(d)
                summary["functions"].append(f_summary)
                func_stack.append(f_summary)
                # 如果在类里面，方法数 +1
                if class_stack:
                    class_stack[-1]["method_count"] += 1
            
            # 类定义
            elif isinstance(node, _ast.ClassDef):
                c_summary = {
                    "name": node.name,
                    "lineno": node.lineno,
                    "end_lineno": getattr(node, "end_lineno", node.lineno),
                    "bases": [self._ast_name_str(b) for b in node.bases],
                    "decorator_list": [self._ast_decorator_name(d) for d in node.decorator_list],
                    "method_count": 0,
                }
                summary["classes"].append(c_summary)
                class_stack.append(c_summary)
            
            # 控制流节点：当前所有栈上函数复杂度 +1
            if isinstance(node, complexity_types) and func_stack:
                for fs in func_stack:
                    fs["complexity"] += 1
            
            # Call 计数
            if isinstance(node, _ast.Call):
                summary["call_count"] += 1
            
            # 赋值计数
            if isinstance(node, (_ast.Assign, _ast.AnnAssign)):
                summary["assign_count"] += 1
            
            # 递归遍历子节点
            for child in _ast.iter_child_nodes(node):
                _visit(child, depth + 1)
            
            # 函数定义：出栈
            if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                func_stack.pop()
            # 类定义：出栈
            if isinstance(node, _ast.ClassDef):
                class_stack.pop()
        
        _visit(tree)
        summary["all_nodes_by_type"] = by_type
        
        # 提取导入信息
        for imp in by_type.get("Import", []):
            for alias in imp.names:
                summary["imports"].append({
                    "module": alias.name,
                    "alias": alias.asname,
                    "lineno": imp.lineno,
                    "type": "import",
                })
        for imp in by_type.get("ImportFrom", []):
            module = imp.module or ""
            for alias in imp.names:
                summary["imports"].append({
                    "module": module,
                    "name": alias.name,
                    "alias": alias.asname,
                    "lineno": imp.lineno,
                    "level": imp.level,
                    "type": "from_import",
                })
        
        # 提取 try-except 块
        for try_node in by_type.get("Try", []):
            summary["try_blocks"].append({
                "node": try_node,
                "lineno": try_node.lineno,
                "handler_count": len(try_node.handlers),
                "has_bare_except": any(h.type is None for h in try_node.handlers),
                "has_finalbody": bool(try_node.finalbody),
            })
        
        # 计算总复杂度
        total_complexity = sum(f["complexity"] for f in summary["functions"])
        summary["total_complexity"] = total_complexity
        
        # 平均复杂度
        if summary["functions"]:
            summary["avg_complexity"] = round(total_complexity / len(summary["functions"]), 2)
        else:
            summary["avg_complexity"] = 0
        
        # 最大复杂度
        if summary["functions"]:
            summary["max_complexity"] = max(f["complexity"] for f in summary["functions"])
        else:
            summary["max_complexity"] = 0
        
        self._ast_summary[file_path] = summary
        return summary

    def _ast_name_str(self, node) -> str:
        """从AST节点提取名称字符串"""
        import ast as _ast
        if isinstance(node, _ast.Name):
            return node.id
        elif isinstance(node, _ast.Attribute):
            return self._ast_name_str(node.value) + "." + node.attr
        else:
            return ""

    def _ast_decorator_name(self, node) -> str:
        """从装饰器AST节点提取名称字符串"""
        import ast as _ast
        if isinstance(node, _ast.Name):
            return node.id
        elif isinstance(node, _ast.Attribute):
            return self._ast_decorator_name(node.value) + "." + node.attr
        elif isinstance(node, _ast.Call):
            return self._ast_decorator_name(node.func)
        return ""

    def prefetch_ast_summary(self) -> int:
        """预计算所有.py文件的AST摘要，后续规则取摘要零开销"""
        py_files = self.find_files([".py"])
        count = 0
        for fpath in py_files:
            if fpath in self._ast_summary:
                continue
            self.get_ast_summary(fpath)
            count += 1
        return count
