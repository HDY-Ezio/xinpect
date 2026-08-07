# -*- coding: utf-8 -*-
"""
项目架构模式一致性检查规则集
检测同一项目中数据库连接方式不一致等问题
规则ID: PAT-001

归脑: module_id = '7'（Brain 7 架构）
"""

import re
from typing import List, Dict, Any


# ============================================================
# PAT-001: 数据库连接不一致
# ============================================================

# 连接池 / 工厂方法模式
_POOL_PATTERNS = [
    re.compile(r'get_db_conn\s*\(', re.IGNORECASE),
    re.compile(r'get_connection\s*\(', re.IGNORECASE),
    re.compile(r'get_db\s*\(', re.IGNORECASE),
    re.compile(r'ConnectionPool\s*\(', re.IGNORECASE),
    re.compile(r'create_engine\s*\(', re.IGNORECASE),  # SQLAlchemy
    re.compile(r'sessionmaker\s*\(', re.IGNORECASE),
    re.compile(r'session\s*=\s*Session\s*\(', re.IGNORECASE),
    re.compile(r'database\s*=\s*Database\s*\(', re.IGNORECASE),
    re.compile(r'get_redis\s*\(', re.IGNORECASE),
    re.compile(r'get_pool\s*\(', re.IGNORECASE),
    re.compile(r'connection_pool', re.IGNORECASE),
    re.compile(r'DBUtils|PooledDB|PersistentDB', re.IGNORECASE),
]

# 直接建连模式
_DIRECT_CONNECT_PATTERNS = [
    re.compile(r'pymysql\.connect\s*\('),
    re.compile(r'mysql\.connector\.connect\s*\('),
    re.compile(r'sqlite3\.connect\s*\('),
    re.compile(r'psycopg2\.connect\s*\('),
    re.compile(r'cx_Oracle\.connect\s*\('),
    re.compile(r'pyodbc\.connect\s*\('),
    re.compile(r'redis\.Redis\s*\('),
    re.compile(r'redis\.StrictRedis\s*\('),
    re.compile(r'MongoClient\s*\('),
]


def check_db_connection_consistency(context) -> List[Dict]:
    """PAT-001: 检测同一项目中数据库连接方式不一致"""
    results = []

    py_files = context.get_backend_py_files()
    if not py_files:
        return results

    pool_usage = []       # [(file, line_no, snippet), ...]
    direct_usage = []     # [(file, line_no, snippet), ...]

    for fpath in py_files:
        content = context.safe_read(fpath)
        if not content:
            continue

        content_lines = content.split('\n')
        seen_pool_lines = set()
        seen_direct_lines = set()

        # 检查连接池用法
        for pattern in _POOL_PATTERNS:
            for m in pattern.finditer(content):
                line_no = content[:m.start()].count('\n') + 1
                if line_no in seen_pool_lines:
                    continue
                line_text = content_lines[line_no - 1] if line_no - 1 < len(content_lines) else ""
                if line_text.strip().startswith('#'):
                    continue
                seen_pool_lines.add(line_no)
                pool_usage.append({
                    'file': fpath,
                    'line': line_no,
                    'snippet': line_text.strip()[:120],
                })

        # 检查直接建连用法
        for pattern in _DIRECT_CONNECT_PATTERNS:
            for m in pattern.finditer(content):
                line_no = content[:m.start()].count('\n') + 1
                if line_no in seen_direct_lines:
                    continue
                line_text = content_lines[line_no - 1] if line_no - 1 < len(content_lines) else ""
                if line_text.strip().startswith('#'):
                    continue
                seen_direct_lines.add(line_no)
                direct_usage.append({
                    'file': fpath,
                    'line': line_no,
                    'snippet': line_text.strip()[:120],
                })

    total_pool = len(pool_usage)
    total_direct = len(direct_usage)
    total = total_pool + total_direct

    # 如果没有混合使用，则不报告
    if total == 0 or total_pool == 0 or total_direct == 0:
        return results

    # 判断是否不一致：
    # 如果有连接池用法（>=1），同时直接建连数 >=3，认为不一致
    # 或者直接建连数 <=2 且总连接数 >5，报告不一致
    is_inconsistent = False
    if total_pool >= 1 and total_direct >= 3:
        is_inconsistent = True
    elif total_direct <= 2 and total > 5 and total_pool >= 1:
        is_inconsistent = True

    if not is_inconsistent:
        return results

    # 报告不一致，每个直接建连位置都报
    for usage in direct_usage:
        results.append({
            'id': 'PAT-001',
            'name': '架构一致性-数据库连接方式不统一',
            'level': 'warning',
            'message': (
                f'项目中存在 {total_pool} 处连接池用法 vs {total_direct} 处直接建连，'
                f'数据库连接方式不统一。建议统一使用连接池管理数据库连接。'
            ),
            'file': usage['file'],
            'line': usage['line'],
            'snippet': usage['snippet'],
            'fix': '统一使用连接池/工厂方法获取数据库连接，避免直接 connect()。\n'
                   '例如：\n'
                   '  def get_db_conn():\n'
                   '      return pool.get_conn()\n'
                   '  # 使用\n'
                   '  conn = get_db_conn()',
        })

    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'PAT-001',
        'name': '架构一致性-数据库连接方式不统一',
        'level': 'warning',
        'category': 'pattern_consistency',
        'module_id': '7',
        'applicable_types': ['python_backend', 'flask', 'mixed', 'mixed_electron', 'skill'],
        'description': '检测同一项目中混合使用连接池和直接建连，建议统一使用连接池',
        'check': check_db_connection_consistency,
    },
]
