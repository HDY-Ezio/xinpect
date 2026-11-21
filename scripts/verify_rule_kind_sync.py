#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：官网的问题分类副本必须和扫描器原件一致。

官网 modules/rule_kind.py 是 engine/rule_taxonomy.py 的副本（网站进程不能
import 扫描器目录）。副本最大的风险是漂移：哪边改了另一处没跟上，
同一个问题在扫描结果里算「漏洞」，在报告页可能算「优化建议」。

============================================================
第一版是假绿的，记在这里免得再犯
============================================================
第一版拿 ast.literal_eval 直接抠常量。可 _BRAIN_CATEGORY 的值写的是
BUG / VULNERABILITY 这些**变量名**，literal_eval 遇到 Name 节点必然失败；
失败后代码 fallback 成字符串 "<无法静态解析>"，两边都成了同一串，于是
「比对通过」。报告里那句「一致（8 项）」也不是 8 个键，是那 8 个汉字字符
的长度——两个数字都不是真的。

现在改成：先把文件里的顶层常量求值成字典，遇到 Name 就去查这张表；
查不到直接报错，绝不再降级成字符串。解析不出来就是守卫自己坏了，
必须红，不能绿。
"""
import ast
import os
import sys

WEBSITE = os.environ.get("XINPECT_WEBSITE_ROOT", "/opt/xinpect-website")
SCANNER = os.environ.get("XINPECT_SCANNER_ROOT", "/opt/xinpect-scanner-blue")

COPY = os.path.join(WEBSITE, "modules", "rule_kind.py")
SOURCE = os.path.join(SCANNER, "engine", "rule_taxonomy.py")

WATCHED = ("_SECURITY_FAMILY_MARKERS", "_SMELL_PREFIXES", "_BRAIN_CATEGORY")


class Unevaluable(Exception):
    pass


def _eval(node, env):
    """把表达式节点求值；认不出来就抛错，不做任何降级。"""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in env:
            return env[node.id]
        raise Unevaluable("引用了未知常量 %s" % node.id)
    if isinstance(node, ast.Dict):
        out = {}
        for k, v in zip(node.keys, node.values):
            if k is None:  # {**other} 展开，不支持
                raise Unevaluable("不支持 dict 展开")
            out[_eval(k, env)] = _eval(v, env)
        return out
    if isinstance(node, ast.Tuple):
        return tuple(_eval(e, env) for e in node.elts)
    if isinstance(node, ast.List):
        return [_eval(e, env) for e in node.elts]
    if isinstance(node, ast.Set):
        return {_eval(e, env) for e in node.elts}
    raise Unevaluable("不支持的节点类型 %s" % type(node).__name__)


def load_consts(path):
    """求值顶层常量。按出现顺序推进，后面的常量能引用前面的。"""
    tree = ast.parse(open(path, encoding="utf-8").read())
    env = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            tgt = node.targets[0]
            if not isinstance(tgt, ast.Name):
                continue
            try:
                env[tgt.id] = _eval(node.value, env)
            except Unevaluable:
                # 只关心被比对的那几个；其它常量求不出来不影响
                continue
    return env


def main():
    for p in (COPY, SOURCE):
        if not os.path.exists(p):
            print("缺文件：%s" % p)
            return 1

    try:
        copy_env = load_consts(COPY)
        src_env = load_consts(SOURCE)
    except SyntaxError as exc:
        print("解析失败（语法错误）：%r" % exc)
        return 1

    problems = []
    for name in WATCHED:
        a = copy_env.get(name)
        b = src_env.get(name)
        if a is None and b is None:
            # 两边都抠不出来 = 守卫自己失效，必须红，不许当成「一致」
            problems.append("%s 两边都解析不出来，守卫失效" % name)
            continue
        if a is None:
            problems.append("官网副本里解析不出 %s" % name)
            continue
        if b is None:
            problems.append("扫描器原件里解析不出 %s" % name)
            continue
        if a != b:
            if isinstance(a, dict) and isinstance(b, dict):
                diff = {k: (a.get(k), b.get(k)) for k in set(a) | set(b)
                        if a.get(k) != b.get(k)}
                problems.append("%s 不一致，差异 %r" % (name, diff))
            elif isinstance(a, (tuple, list)) and isinstance(b, (tuple, list)):
                problems.append("%s 不一致：官网多 %r，扫描器多 %r"
                                % (name, [x for x in a if x not in b],
                                   [x for x in b if x not in a]))
            else:
                problems.append("%s 不一致：官网 %r / 扫描器 %r" % (name, a, b))
        else:
            print("  [ OK ] %-24s 一致（%d 项）" % (name, len(a)))

    if problems:
        print()
        for p in problems:
            print("  [FAIL] " + p)
        print("\n结果：%d 项漂移 —— 改一处必须同步另一处" % len(problems))
        return 1

    print("\n结果：3 个常量与扫描器原件逐项一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
