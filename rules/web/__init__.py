"""
web规则集
"""

from . import ast_rules

# v4.4 JS/TS AST 规则数量
AST_RULE_COUNT = getattr(ast_rules, 'TOTAL_RULES', 0)
