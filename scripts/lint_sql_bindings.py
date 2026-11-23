#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SQL 占位符门禁：db.execute(".. ? ..", (..)) 的 ? 个数必须等于参数个数。
本轮就是靠这类错误（入队 INSERT 加了列忘了加值）把排队打成 500 的，
加一道静态检查，避免下次再靠客户报错才发现。
"""
import ast
import sys


def const_str(node):
    """把字符串常量（含隐式拼接）还原成一个字符串"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def count_params(node):
    """参数节点：Tuple/List 直接数元素；其他（变量、生成器）返回 None 表示无法静态判定"""
    if isinstance(node, (ast.Tuple, ast.List)):
        return len(node.elts)
    return None


def main(path):
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    problems, checked = [], 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not (isinstance(fn, ast.Attribute) and fn.attr in ("execute", "executemany")):
            continue
        if len(node.args) < 2:
            continue
        sql = const_str(node.args[0])
        if sql is None:
            continue
        n_q = sql.count("?")
        if n_q == 0:
            continue
        n_p = count_params(node.args[1])
        if n_p is None:
            continue
        checked += 1
        if n_q != n_p:
            problems.append((node.lineno, n_q, n_p, sql[:90].replace("\n", " ")))
    print("检查文件: %s" % path)
    print("  可静态判定的 execute 调用: %d 处" % checked)
    if problems:
        print("  ❌ 占位符与参数不匹配:")
        for lineno, n_q, n_p, sql in problems:
            print("     行 %d: SQL 有 %d 个 ?，参数 %d 个 | %s" % (lineno, n_q, n_p, sql))
        return 1
    print("  ✅ 全部匹配")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "api_v6.py"))
