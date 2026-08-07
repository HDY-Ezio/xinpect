# -*- coding: utf-8 -*-
"""
文档与代码结构一致性校验规则集 (v5.3.0)
Brain6 AI语义审查补漏规则
包含: DOCCON-001 文档与代码结构一致性校验

注意：规则 ID 使用 DOCCON-001 而非 DOC-001，
因为 rules/common/doc_rules.py 中已占用 DOC-001 ~ DOC-005。
"""

import re
import os
import ast
from typing import List, Dict, Any, Set, Tuple


# ======================================================================
# DOCCON-001: 文档与代码结构一致性校验
# 从代码中提取结构化声明（类名、模块数等）
# 从文档中提取数量声明（"N个大脑"等）
# 对比两者是否一致
# ======================================================================

# 从 Python 代码中提取结构信息的模式
_PY_CLASS_RE = re.compile(r'^class\s+(\w+)', re.MULTILINE)
_PY_FUNC_RE = re.compile(r'^\s*def\s+(\w+)\s*\(', re.MULTILINE)
_PY_MODULE_RE = re.compile(r'^from\s+([\w.]+)\s+import', re.MULTILINE)

# 从 JS/TS 代码中提取结构信息的模式
_JS_CLASS_RE = re.compile(r'(?:class|export\s+(?:default\s+)?class)\s+(\w+)', re.MULTILINE)
_JS_FUNC_RE = re.compile(r'(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\()', re.MULTILINE)
_JS_EXPORT_RE = re.compile(r'export\s+(?:default\s+)?(?:function|class|const|let|var)\s+(\w+)', re.MULTILINE)

# 文档中数量声明的模式
_DOC_QUANTITY_PATTERNS = [
    # "N个大脑", "N 个模块", "N 个组件"
    (re.compile(r'(\d+)\s*个?\s*(大脑|模块|组件|引擎|规则|检查|brain|module|component|engine|rule|check)',
                re.IGNORECASE),
     '数量声明'),
    # "包含N项检查", "共N个规则"
    (re.compile(r'(?:包含|共有|共计|合计|总共|共计)\s*(\d+)\s*个?\s*(大脑|模块|组件|引擎|规则|检查|项|条|种|个)',
                re.IGNORECASE),
     '总数声明'),
    # "v1.0", "version 2"
    (re.compile(r'[vV](?:ersion)?\s*(\d+(?:\.\d+)*)',
                re.IGNORECASE),
     '版本号声明'),
    # "257条规则", "15+项检查"
    (re.compile(r'(\d+)\+?\s*条?\s*(规则|检查|规则集|rule|check)',
                re.IGNORECASE),
     '规则数量'),
    # "N 个文件", "N 个类", "N 个函数"
    (re.compile(r'(\d+)\s*个?\s*(文件|类|函数|方法|接口|端点|路由|file|class|function|method|api|endpoint|route)',
                re.IGNORECASE),
     '代码结构数量'),
]


def _extract_code_structure(context) -> Dict[str, Any]:
    """v4.6.1 优化：基于 context 缓存提取，避免重复 os.walk + 文件读取
    原函数接收 project_path，自己 walk 目录并 open 文件，每次调用都做完整 IO。
    改为使用 context.find_files() + context.safe_read()，全部走内存缓存。
    """
    structure = {
        'classes': set(),
        'functions': set(),
        'modules': set(),
        'py_files': 0,
        'js_files': 0,
        'total_files': 0,
        'exports': set(),
    }

    py_files = context.find_files(['.py'])
    js_files = context.find_files(['.js', '.ts', '.tsx', '.jsx'])
    
    structure['py_files'] = len(py_files)
    structure['js_files'] = len(js_files)
    structure['total_files'] = len(py_files) + len(js_files)
    
    # 限制扫描文件数（大项目避免过慢）
    max_files = 500
    
    for fpath in py_files[:max_files]:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        for m in _PY_CLASS_RE.finditer(content):
            class_name = m.group(1)
            if not class_name.startswith('_'):
                structure['classes'].add(class_name)
        
        for m in _PY_FUNC_RE.finditer(content):
            func_name = m.group(1)
            if not func_name.startswith('_'):
                structure['functions'].add(func_name)
        
        # 模块名 = 文件名（不含扩展名）
        mod_name = os.path.splitext(os.path.basename(fpath))[0]
        if mod_name != '__init__':
            structure['modules'].add(mod_name)
    
    remaining = max_files - len(py_files[:max_files])
    for fpath in js_files[:remaining]:
        content = context.safe_read(fpath)
        if not content:
            continue
        
        for m in _JS_CLASS_RE.finditer(content):
            structure['classes'].add(m.group(1))
        
        for m in _JS_FUNC_RE.finditer(content):
            func_name = m.group(1) or m.group(2)
            if func_name:
                structure['functions'].add(func_name)
        
        for m in _JS_EXPORT_RE.finditer(content):
            structure['exports'].add(m.group(1))

    return structure


def _extract_doc_claims(context) -> List[Dict[str, Any]]:
    """v4.6.1 优化：基于 context.safe_read 读取文档，避免重复 IO"""
    claims = []
    project_path = context.project_path

    if not project_path or not os.path.isdir(project_path):
        return claims

    # 扫描文档文件
    doc_files = []
    for doc_name in ['README.md', 'CHANGELOG.md', 'SKILL.md',
                     'ARCHITECTURE.md', 'DESIGN.md', 'docs']:
        doc_path = os.path.join(project_path, doc_name)
        if os.path.isfile(doc_path):
            doc_files.append(doc_path)
        elif os.path.isdir(doc_path):
            for fname in os.listdir(doc_path):
                if fname.endswith(('.md', '.rst', '.txt')):
                    doc_files.append(os.path.join(doc_path, fname))

    for doc_path in doc_files:
        content = context.safe_read(doc_path)
        if not content:
            continue

        for pattern, claim_type in _DOC_QUANTITY_PATTERNS:
            for m in pattern.finditer(content):
                raw_val = m.group(1)
                # Skip version numbers like "5.3.0" or "2.8" — they are not quantity claims
                if '.' in raw_val:
                    continue
                quantity = int(raw_val)
                category = m.group(2) if m.lastindex >= 2 else ''
                line_num = content[:m.start()].count('\n') + 1

                claims.append({
                    'doc_file': doc_path,
                    'line': line_num,
                    'quantity': quantity,
                    'category': category,
                    'type': claim_type,
                    'text': m.group(0),
                })

    return claims


def _compare_structure(
    code_structure: Dict[str, Any],
    doc_claims: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """比较代码结构和文档声明，返回不一致项"""
    inconsistencies = []

    for claim in doc_claims:
        quantity = claim['quantity']
        category = claim['category'].lower()
        doc_file = os.path.basename(claim['doc_file'])

        # 根据类别比较
        if category in ('大脑', 'brain', '引擎', 'engine'):
            # 计算代码中的引擎/大脑类数量
            brain_classes = [c for c in code_structure['classes']
                           if any(kw in c.lower() for kw in
                                  ['brain', 'engine', 'engine', 'core'])]
            actual_count = len(brain_classes)
            if actual_count > 0 and quantity != actual_count:
                inconsistencies.append({
                    'doc_file': doc_file,
                    'line': claim['line'],
                    'claim': claim['text'],
                    'claimed': quantity,
                    'actual': actual_count,
                    'category': category,
                    'detail': f"文档声明{quantity}个{category}，代码中检测到{actual_count}个",
                })

        elif category in ('模块', 'module'):
            actual_count = len(code_structure['modules'])
            if actual_count > 0 and quantity != actual_count:
                # 允许一定误差（文档可能是概括性的）
                ratio = quantity / actual_count if actual_count > 0 else 0
                if ratio < 0.5 or ratio > 2.0:
                    inconsistencies.append({
                        'doc_file': doc_file,
                        'line': claim['line'],
                        'claim': claim['text'],
                        'claimed': quantity,
                        'actual': actual_count,
                        'category': category,
                        'detail': f"文档声明{quantity}个{category}，代码中检测到{actual_count}个",
                    })

        elif category in ('规则', 'rule', '检查', 'check'):
            # 尝试从代码注释中提取实际规则数
            # 这里简化处理，只比较数量差异是否过大
            if quantity < 10:
                # 小数量声明，精确匹配
                pass  # 需要更具体的规则计数逻辑
            elif quantity > 300:
                # 大数量，允许±20% 误差
                pass

        elif category in ('文件', 'file'):
            actual_count = code_structure['total_files']
            if actual_count > 0 and quantity != actual_count:
                ratio = quantity / actual_count if actual_count > 0 else 0
                if ratio < 0.5 or ratio > 2.0:
                    inconsistencies.append({
                        'doc_file': doc_file,
                        'line': claim['line'],
                        'claim': claim['text'],
                        'claimed': quantity,
                        'actual': actual_count,
                        'category': category,
                        'detail': f"文档声明{quantity}个文件，代码中实际有{actual_count}个",
                    })

        elif category in ('类', 'class'):
            actual_count = len(code_structure['classes'])
            if actual_count > 0 and quantity != actual_count:
                ratio = quantity / actual_count if actual_count > 0 else 0
                if ratio < 0.5 or ratio > 2.0:
                    inconsistencies.append({
                        'doc_file': doc_file,
                        'line': claim['line'],
                        'claim': claim['text'],
                        'claimed': quantity,
                        'actual': actual_count,
                        'category': category,
                        'detail': f"文档声明{quantity}个类，代码中实际有{actual_count}个",
                    })

        elif category in ('函数', 'function', '方法', 'method'):
            actual_count = len(code_structure['functions'])
            if actual_count > 0 and quantity != actual_count:
                ratio = quantity / actual_count if actual_count > 0 else 0
                if ratio < 0.5 or ratio > 2.0:
                    inconsistencies.append({
                        'doc_file': doc_file,
                        'line': claim['line'],
                        'claim': claim['text'],
                        'claimed': quantity,
                        'actual': actual_count,
                        'category': category,
                        'detail': f"文档声明{quantity}个函数/方法，代码中实际有{actual_count}个",
                    })

    return inconsistencies


def check_doccon_001_doc_code_consistency(context) -> List[Dict]:
    """DOCCON-001 文档与代码结构一致性校验

    从代码中提取结构化声明（类名、模块数等），
    从文档中提取数量声明（"N个大脑"等），
    对比两者是否一致。
    """
    results = []

    project_path = context.project_path
    if not project_path or not os.path.isdir(project_path):
        return results

    # 提取代码结构
    code_structure = _extract_code_structure(context)

    # 提取文档声明
    doc_claims = _extract_doc_claims(context)

    if not doc_claims:
        # 没有数量声明，无需比较
        return results

    if code_structure['total_files'] < 3:
        # 项目太小，跳过
        return results

    # 比较
    inconsistencies = _compare_structure(code_structure, doc_claims)

    if inconsistencies:
        detail_lines = [
            f"  {ic['doc_file']}:{ic['line']} - {ic['detail']}"
            for ic in inconsistencies[:10]
        ]

        results.append({
            'id': 'DOCCON-001',
            'name': '文档与代码结构一致性',
            'level': 'warning',
            'message': f'发现{len(inconsistencies)}处文档声明与代码实际结构不一致',
            'detail': '\n'.join(detail_lines),
            'file': '',
            'line': 0,
            'fix': '更新文档中的数量声明，使其与代码实际结构保持一致',
        })

    return results


# ===== 规则定义列表 =====
RULES = [
    {
        'id': 'DOCCON-001',
        'name': '文档与代码结构一致性',
        'level': 'problem',
        'category': 'engineering_maturity',
        'module_id': '32',
        'applicable_types': [],
        'description': '从代码中提取结构化声明（类名、模块数等），从文档中提取数量声明，对比两者是否一致',
        'check': check_doccon_001_doc_code_consistency,
    },
]
