# -*- coding: utf-8 -*-
"""
Python AST深度规则集
煋鉴 qa-code-expert - Python后端深度检查

包含9大模块、60+条AST级规则：
- sql_safety: SQL安全分析 (PYAST001-PYAST008)
- concurrency_safety: 并发安全分析 (PYAST009-PYAST016)
- orm_antipatterns: ORM反模式检测 (PYAST017-PYAST024)
- memory_leaks: 内存泄漏检测 (PYAST025-PYAST032)
- async_safety: 异步安全分析 (PYAST033-PYAST040)
- resource_management: 资源管理检查 (PYAST041-PYAST048)
- resource_lifecycle: 资源生命周期检查 (PYAST049-PYAST051)
- hardcoded_secrets: 硬编码凭据与调试语句 (PYAST052-PYAST058)
- dangerous_functions: 危险函数调用安全 (PYAST059-PYAST069)
"""

from . import sql_safety
from . import concurrency_safety
from . import orm_antipatterns
from . import memory_leaks
from . import async_safety
from . import resource_management
from . import resource_lifecycle
from . import hardcoded_secrets
from . import dangerous_functions


# 所有AST深度规则模块
AST_DEEP_MODULES = [
    sql_safety,
    concurrency_safety,
    orm_antipatterns,
    memory_leaks,
    async_safety,
    resource_management,
    resource_lifecycle,
    hardcoded_secrets,
    dangerous_functions,
]


def get_all_rules():
    """获取所有AST深度规则"""
    all_rules = []
    for module in AST_DEEP_MODULES:
        if hasattr(module, 'RULES'):
            all_rules.extend(module.RULES)
    return all_rules


def get_rule_ids():
    """获取所有规则ID"""
    return [rule['id'] for rule in get_all_rules()]


# 规则总数
TOTAL_RULES = len(get_all_rules())
