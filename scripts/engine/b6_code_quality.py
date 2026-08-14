# -*- coding: utf-8 -*-
"""
B6: 代码质量引擎（免费版）
- 规则 bundle 正则扫描
- Python/JS 复杂度检测（长函数、深层嵌套、重复代码）
- 命名规范、文档质量检测
- 【付费版】Prompt质量检测
- 【付费版】JSON校验缺失检测
- 【付费版】Prompt质量规则检测
- 备份/垃圾文件检测（GEN-BAK-FILES）：项目级垃圾文件清理提醒
- 【付费版】测试质量检测（10条规则）
"""

import os
import re
from typing import Dict, List


def scan(code_files: Dict[str, str], config: dict = None) -> List[Dict]:
    """B6 代码质量扫描入口（免费版）"""
    if config is None:
        config = {}

    issues = _custom_checks(code_files)
    return issues


def _custom_checks(code_files: Dict[str, str]) -> List[Dict]:
    """B6 专用手写检测逻辑"""
    issues = []

    # 项目级规则（先执行，基于整个 code_files 统计）
    issues.extend(_check_backup_files(code_files))

    # 项目级：集成测试缺失检测（测试质量规则 10）
    # 集成测试检测为付费版功能

    for filepath, content in code_files.items():
        if not content:
            continue
        ext = os.path.splitext(filepath)[1].lower()
        lines = content.split("\n")

        if ext == ".py":
            issues.extend(_check_python_quality(filepath, content, lines))
            # Prompt 示例数据检测（Python 特有，且需要 AST 分析字符串）
            # Prompt质量检测为付费版功能
            # Prompt 质量规则检测（Python 特有）
            # Prompt质量检测为付费版功能
            # JSON 输入校验缺失检测（Python 后端接口）
            # JSON校验检测为付费版功能
            # 测试质量检测（Python 测试文件）
            # 测试质量检测为付费版功能
        elif ext in (".js", ".jsx", ".ts", ".tsx"):
            issues.extend(_check_js_quality(filepath, content, lines))
            # 测试质量检测（JS 测试文件）
            # 测试质量检测为付费版功能

        # 通用检测
        issues.extend(_check_general_quality(filepath, content, lines))

    return issues


def _check_python_quality(filepath: str, content: str, lines: List[str]) -> List[Dict]:
    issues = []

    # 关键操作异常路径缺少错误日志
            # 错误日志检测为付费版功能

    # 检测长函数
    func_start = None
    func_name = None
    func_indent = None

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        current_indent = len(line) - len(stripped)

        if stripped.startswith("def ") and stripped != "def ":
            # 先检查上一个函数
            if func_start is not None and func_name:
                func_length = i - 1 - func_start
                if func_length > 100:
                    issues.append({
                        "check_id": "QUAL-PY-001",
                        "name": "函数过长",
                        "severity": "low",
                        "file": filepath,
                        "line": func_start,
                        "message": f"函数 '{func_name}' 过长（约{func_length}行），超过100行阈值",
                        "suggestion": "将函数拆分为多个职责单一的小函数，每个函数控制在30行以内",
                    })
            func_start = i
            func_name = stripped.split("(")[0].replace("def ", "").strip()
            func_indent = current_indent

    # 最后一个函数
    if func_start is not None and func_name:
        func_length = len(lines) - func_start
        if func_length > 100:
            issues.append({
                "check_id": "QUAL-PY-001",
                "name": "函数过长",
                "severity": "medium",
                "file": filepath,
                "line": func_start,
                "message": f"函数 '{func_name}' 过长（约{func_length}行），超过100行阈值",
                "suggestion": "将函数拆分为多个职责单一的小函数，每个函数控制在30行以内",
            })

    # 检测深层嵌套（跳过字符串和注释内容）
    max_indent = 0
    max_indent_line = 0
    in_multiline_str = False  # 三引号字符串状态
    str_char = None           # 当前字符串引号类型

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # 处理多行字符串状态
        if in_multiline_str:
            # 检查是否结束（三引号闭合）
            if str_char and (str_char * 3) in stripped:
                in_multiline_str = False
                str_char = None
            # 字符串内的行不参与嵌套计算
            continue

        # 跳过单行注释
        if stripped.startswith('#'):
            continue

        # 检查是否开始三引号字符串（行首的三引号）
        import re
        triple_match = re.match(r'^\s*(\'\'\'|""")', line)
        if triple_match:
            quote = triple_match.group(1)[0]
            # 检查是否在同一行结束
            rest = line[triple_match.end():]
            if (quote * 3) not in rest:
                # 多行字符串开始
                in_multiline_str = True
                str_char = quote
            # 单行三引号字符串也跳过
            continue

        # 跳过纯空行
        if not stripped:
            continue

        # 真实代码行，统计缩进
        indent = len(line) - len(line.lstrip())
        if indent > max_indent:
            max_indent = indent
            max_indent_line = i

    # 每层4空格，8层就是 32 空格
    if max_indent > 32:
        depth = max_indent // 4
        issues.append({
            "check_id": "QUAL-PY-002",
            "name": "深层嵌套",
            "severity": "medium",
            "file": filepath,
            "line": max_indent_line,
            "message": f"代码嵌套过深（约{depth}层），增加理解和维护成本",
            "suggestion": "使用早返回（guard clause）、提取函数或简化条件逻辑减少嵌套",
        })

    # 检测类名命名规范
    class_matches = re.findall(r"class\s+([a-z][a-zA-Z0-9_]*)\s*[:\(]", content)
    for class_name in class_matches[:3]:  # 最多报3个
        issues.append({
            "check_id": "QUAL-PY-003",
            "name": "类名不符合规范",
            "severity": "low",
            "file": filepath,
            "line": 1,
            "message": f"类名 '{class_name}' 不符合 Python PEP 8 的 CapWords 命名规范",
            "suggestion": "将类名改为大驼峰形式（PascalCase），首字母大写",
        })

    # 检测公共函数缺少文档字符串
    # 只在有一定规模的文件中检查，且跳过特殊方法和简单函数
    public_funcs_without_doc = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        # 只匹配函数定义（方法或顶层函数）
        if stripped.startswith("def ") or stripped.startswith("async def "):
            # 提取函数名
            prefix_len = 4 if stripped.startswith("def ") else 10
            func_def = stripped[prefix_len:]
            func_name = func_def.split("(")[0].strip()

            # 跳过私有函数（_开头）
            if func_name.startswith("_"):
                continue

            # 跳过 dunder 方法（魔术方法，如 __init__, __str__, __repr__ 等）
            if func_name.startswith("__") and func_name.endswith("__"):
                continue

            # 跳过 property 装饰器的方法
            has_property_decorator = False
            for j in range(i - 1, max(i - 5, -1), -1):
                prev_stripped = lines[j].strip()
                if prev_stripped.startswith("@property") or ".setter" in prev_stripped:
                    has_property_decorator = True
                    break
                if prev_stripped.startswith("@"):
                    continue
                break
            if has_property_decorator:
                continue

            # 检查下一行是否有 docstring
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                triple_dq = chr(34)*3
                triple_sq = chr(39)*3
                has_doc = next_line.startswith(triple_dq) or next_line.startswith(triple_sq)
                if not has_doc:
                    # 简单函数（1-2行函数体）不报
                    func_body_lines = 0
                    func_indent = len(line) - len(line.lstrip())
                    for j in range(i + 1, min(i + 5, len(lines))):
                        body_line = lines[j]
                        body_stripped = body_line.strip()
                        if not body_stripped or body_stripped.startswith("#"):
                            continue
                        body_indent = len(body_line) - len(body_line.lstrip())
                        if body_indent <= func_indent and body_stripped:
                            break
                        func_body_lines += 1
                    if func_body_lines <= 2:
                        continue

                    public_funcs_without_doc.append((i + 1, func_name))

    # 只有当缺少文档的公共函数 >= 2 个时才报（避免小文件过度打扰），最多报1个
    if len(public_funcs_without_doc) >= 2:
        line_no, func_name = public_funcs_without_doc[0]
        issues.append({
            "check_id": "QUAL-PY-004",
            "name": "公共函数缺少文档",
            "severity": "info",
            "file": filepath,
            "line": line_no,
            "message": f"公共函数 {func_name} 缺少 docstring 文档说明（共{len(public_funcs_without_doc)}个）",
            "suggestion": "添加文档字符串说明函数功能、参数和返回值",
        })

    return issues


def _check_js_quality(filepath: str, content: str, lines: List[str]) -> List[Dict]:
    issues = []

    # var 声明
    var_count = len(re.findall(r'\bvar\s+\w+', content))
    if var_count > 0:
        issues.append({
            "check_id": "QUAL-JS-001",
            "name": "使用var声明变量",
            "severity": "low",
            "file": filepath,
            "line": 1,
            "message": f"使用 var 声明变量（{var_count}处），存在变量提升和作用域问题",
            "suggestion": "使用 let 或 const 替代 var，const 优先",
        })

    # == 而非 ===
    eq_matches = re.findall(r'[^=!]==[^=]', content)
    if len(eq_matches) > 3:
        issues.append({
            "check_id": "QUAL-JS-002",
            "name": "使用==而非===",
            "severity": "low",
            "file": filepath,
            "line": 1,
            "message": f"使用 == 进行比较（{len(eq_matches)}处），可能导致隐式类型转换问题",
            "suggestion": "使用 === 和 !== 进行严格相等比较",
        })

    # console.log 残留
    console_count = len(re.findall(r'console\.(log|warn|error|debug)', content))
    if console_count > 5:
        issues.append({
            "check_id": "QUAL-JS-003",
            "name": "过多调试输出",
            "severity": "info",
            "file": filepath,
            "line": 1,
            "message": f"文件中有 {console_count} 处 console.* 调试输出，生产环境应清理",
            "suggestion": "移除调试输出，或使用专用日志库并设置生产级别",
        })

    return issues


def _check_general_quality(filepath: str, content: str, lines: List[str]) -> List[Dict]:
    issues = []

    # TODO/FIXME 标记（只匹配注释中的，避免误报CSS类名、变量名等）
    todo_count = 0
    fixme_count = 0
    # 先判断是否为注释上下文：
    # - 行首注释: //, /*, *, #, --, <!--, ///, /**
    # - 行尾注释: // xxx, /* xxx */
    comment_indicators = ['//', '/*', '# ', '-- ', '<!--', '///', '/**']
    for line in lines:
        stripped = line.strip()
        # 找到注释开始的位置
        comment_start = -1
        for ind in comment_indicators:
            idx = line.find(ind)
            if idx >= 0 and (comment_start == -1 or idx < comment_start):
                comment_start = idx
        # 没有注释就跳过（避免CSS类名.todo{}、变量名todoList等误报）
        if comment_start == -1:
            continue
        # 只在注释部分搜索
        comment_part = line[comment_start:]
        if re.search(r'TODO[\s:]', comment_part, re.IGNORECASE):
            todo_count += 1
        if re.search(r'FIXME[\s:]', comment_part, re.IGNORECASE):
            fixme_count += 1

    if todo_count > 0:
        issues.append({
            "check_id": "QUAL-GEN-001",
            "name": "待办事项(TODO)",
            "severity": "info",
            "file": filepath,
            "line": 1,
            "message": f"代码中有 {todo_count} 处 TODO 标记，需跟进完成",
            "suggestion": "定期清理 TODO，将重要任务加入任务管理系统",
        })

    if fixme_count > 0:
        issues.append({
            "check_id": "QUAL-GEN-002",
            "name": "待修复标记(FIXME)",
            "severity": "low",
            "file": filepath,
            "line": 1,
            "message": f"代码中有 {fixme_count} 处 FIXME 标记，已知问题需修复",
            "suggestion": "优先修复 FIXME 标记的问题，避免技术债积累",
        })

    # 大文件行数
    if len(lines) > 500:
        issues.append({
            "check_id": "QUAL-GEN-003",
            "name": "文件过大",
            "severity": "low",
            "file": filepath,
            "line": 1,
            "message": f"文件过大（{len(lines)}行），超过500行建议拆分",
            "suggestion": "按功能模块拆分为多个文件，降低单文件复杂度",
        })

    return issues


def _check_hidden_critical_op_no_error_log(filepath: str, content: str, lines: List[str]) -> List[Dict]:    # 错误日志检测为付费版功能
    """检测关键操作函数异常路径缺少错误日志（HIDDEN-LOG-001）

    检测逻辑：
    - 识别文件中的关键操作函数（函数名含：pay/payment/delete/remove/permission/auth/
      export/transfer/refund 等高风险关键词）
    - 检查这些函数的异常路径（try-except 的 except 块、if error/if not success 分支）：
      - 是否有 logging.error / logger.error / logger.exception / logging.warning
        等错误级别日志
      - 如果异常路径上只有：print / logging.info / pass / 静默返回 → 报 low

    误报控制：
    - 只对明显是业务关键操作的函数检测（函数名匹配高风险关键词）
    - except 块里有 raise 的不报（异常被往上抛了，由上层处理）
    - 简单工具函数（函数体<5行）不报
    - 有异常抛出（raise）或返回错误码/False的，根据情况放宽
    - 测试文件、脚本文件宽松处理
    - 只要异常路径中存在 error/warning/exception 级别的日志调用即不报
    """
    issues = []
    import ast as _ast

    try:
        tree = _ast.parse(content, filename=filepath)
    except SyntaxError:
        return issues  # 语法错误由 B1 报告

    # 高风险函数名关键词（小写匹配）
    critical_keywords = (
        "pay", "payment", "refund", "transfer", "withdraw", "deduct",
        "delete", "remove", "destroy", "purge",
        "permission", "authorize", "auth", "grant", "revoke",
        "export", "import_data", "batch_", "sync_",
        "send_email", "send_sms", "notify", "push",
        "charge", "settle", "reconcile",
    )

    def _is_critical_function(func_name: str) -> bool:
        """判断函数名是否包含关键操作关键词"""
        name_lower = func_name.lower()
        for kw in critical_keywords:
            if kw in name_lower:
                return True
        return False

    def _has_error_log(body_stmts) -> bool:
        """检查语句块中是否有错误级别日志（error/warning/exception/critical）"""
        for stmt in _ast.walk(_ast.Module(body=body_stmts, type_ignores=[])):
            if isinstance(stmt, _ast.Call):
                if isinstance(stmt.func, _ast.Attribute):
                    attr = stmt.func.attr.lower()
                    if attr in ("error", "exception", "critical", "fatal", "warning", "warn"):
                        # 进一步确认是日志相关调用（logger.* 或 logging.*）
                        # 但为了降低漏报，只要方法名匹配就认为是错误日志
                        return True
        return False

    def _has_raise(body_stmts) -> bool:
        """检查语句块中是否有 raise 语句"""
        for stmt in _ast.walk(_ast.Module(body=body_stmts, type_ignores=[])):
            if isinstance(stmt, _ast.Raise):
                return True
        return False

    def _is_silent_or_info_only(body_stmts) -> bool:
        """检查异常路径是否只有 info/print/pass/静默返回（没有错误日志也没有raise）"""
        if _has_error_log(body_stmts):
            return False
        if _has_raise(body_stmts):
            return False
        # 既没有错误日志也没有抛出异常 → 视为静默或低级别处理
        # 排除空 body（不可能）
        if not body_stmts:
            return False
        return True

    def _count_body_lines(node_body, func_lineno) -> int:
        """粗略统计函数体行数"""
        last_line = func_lineno
        for stmt in _ast.walk(_ast.Module(body=node_body, type_ignores=[])):
            if hasattr(stmt, "lineno") and stmt.lineno > last_line:
                last_line = stmt.lineno
        return last_line - func_lineno + 1

    class CriticalOpLogVisitor(_ast.NodeVisitor):
        def __init__(self):
            self.findings = []  # (func_name, lineno, path_type)

        def visit_FunctionDef(self, node):
            # 只检查关键操作函数
            if not _is_critical_function(node.name):
                self.generic_visit(node)
                return

            # 简单小函数（<5行）不报，通常是简单封装
            body_lines = _count_body_lines(node.body, node.lineno)
            if body_lines < 5:
                self.generic_visit(node)
                return

            # 检查函数内的所有 try-except 结构
            for stmt in _ast.walk(node):
                if isinstance(stmt, _ast.Try):
                    for handler in stmt.handlers:
                        if _is_silent_or_info_only(handler.body):
                            # 误报控制：如果 except 块有 return (某个错误值) 也考虑放宽
                            # 但 return None / return 静默返回仍然要报
                            has_return = any(
                                isinstance(s, _ast.Return) for s in _ast.walk(
                                    _ast.Module(body=handler.body, type_ignores=[])
                                )
                            )
                            # 如果 return 了有意义的值（如 False/错误码/错误对象），
                            # 且函数名不是特别关键，就不报
                            # 这里保守一点：只对 pay/refund/transfer/delete 这类
                            # 最高风险关键词强制报
                            high_risk_keywords = (
                                "pay", "payment", "refund", "transfer",
                                "delete", "remove",
                            )
                            name_lower = node.name.lower()
                            is_high_risk = any(
                                kw in name_lower for kw in high_risk_keywords
                            )

                            if is_high_risk or not has_return:
                                path_type = "except块"
                                self.findings.append(
                                    (node.name, handler.lineno, path_type)
                                )

            # 检查 if 分支中的错误处理模式（if not success / if error 等）
            # 这部分用 AST 较复杂，保守实现：扫描 if 语句的 test 表达式
            for stmt in _ast.walk(node):
                if isinstance(stmt, _ast.If):
                    # 检查 if 的 test 是否涉及 error/fail/success/valid 等判断
                    error_indicators = ("error", "fail", "failed", "err", "invalid",
                                        "not_ok", "not_success", "not_ok", "is_error")
                    test_str = _ast.dump(stmt.test).lower()
                    is_error_branch = any(ind in test_str for ind in error_indicators)
                    # 同时检查 "not success" / "not valid" 等否定式成功判断
                    not_success_patterns = ("notsuccess", "not_ok", "not_valid",
                                            "not_status", "unexpect")
                    is_error_branch = is_error_branch or any(
                        p in test_str for p in not_success_patterns
                    )

                    if is_error_branch and _is_silent_or_info_only(stmt.body):
                        # 只对高风险函数报 if 分支的问题（减少误报）
                        high_risk_keywords = (
                            "pay", "payment", "refund", "transfer", "delete",
                        )
                        name_lower = node.name.lower()
                        is_high_risk = any(
                            kw in name_lower for kw in high_risk_keywords
                        )
                        if is_high_risk:
                            path_type = "错误分支"
                            self.findings.append(
                                (node.name, stmt.lineno, path_type)
                            )

            self.generic_visit(node)

    visitor = CriticalOpLogVisitor()
    visitor.visit(tree)

    # 去重：同一函数可能有多个异常路径有问题，最多报2个
    reported_funcs = {}  # func_name -> count
    for func_name, lineno, path_type in visitor.findings:
        if func_name in reported_funcs and reported_funcs[func_name] >= 2:
            continue
        issues.append({
            "check_id": "HIDDEN-LOG-001",
            "name": "关键操作异常路径缺少错误日志",
            "severity": "low",
            "file": filepath,
            "line": lineno,
            "message": (f"关键操作函数 '{func_name}' 的{path_type}中缺少错误级别日志"
                        f"（error/warning/exception），"
                        f"异常发生时可能无法被监控系统感知"),
            "suggestion": "在异常路径中添加 logging.error 或 logger.exception 记录错误详情，便于线上问题排查和监控告警",
        })
        if func_name not in reported_funcs:
            reported_funcs[func_name] = 1
        else:
            reported_funcs[func_name] += 1

    return issues


# ============================================================
# 规则 2: Prompt/人设示例数据检测 (PY-PROMPT-SAMPLE-DATA)
# ============================================================

# persona / system prompt 相关的变量名关键词
_PROMPT_VAR_KEYWORDS = (
    "persona", "system_prompt", "system_message",
    "prompt_template", "prompt_text", "ai_prompt",
    "bot_prompt", "assistant_prompt", "character_prompt",
    "role_description", "role_setting", "char_setting",
    "prompt_content", "base_prompt", "main_prompt",
    "agent_prompt", "instruction",
)

# 示例/占位/假数据关键词（中英文）
_SAMPLE_DATA_KEYWORDS = (
    # 中文示例关键词
    "示例门店", "示例名称", "测试数据", "测试门店", "测试用户",
    "示例地址", "示例电话", "示例店铺", "示例公司", "示例产品",
    "示例数据", "演示数据", "样例数据", "占位数据",
    # 英文示例关键词
    "example store", "example name", "example address",
    "demo data", "sample data", "test data", "dummy data",
    "example_data", "sample_store", "test_store",
    # 典型的占位假数据
    "张三", "李四", "王五", "赵六",
    "北京市朝阳区", "上海市浦东新区",
    "13800138000", "13800000000",
    "示例", "测试用例",
)

# 疑似硬编码业务数据的模式（在 prompt 上下文中出现具体业务实体）
# 注意：排除模板占位符 {{ xxx }} / <%= xxx %> / {xxx} 等形式
_BUSINESS_ENTITY_PATTERNS = [
    # 店名/公司名模式：前面有至少2个汉字+店/公司等后缀
    # 排除"门店信息"、"店铺介绍"等非具体店名的情况
    (r'[\u4e00-\u9fa5A-Za-z0-9]{2,}(?:店|公司|餐厅|火锅|烧烤|奶茶|咖啡|超市|商场|酒店|宾馆)(?![\u4e00-\u9fa5]*信息|[\u4e00-\u9fa5]*介绍|[\u4e00-\u9fa5]*说明|[\u4e00-\u9fa5]*列表)',
     "具体的门店/公司名称"),
    # 地址模式："地址：xxx省/市/区/路xxx号" 等具体地址结构
    (r'(?:地址|位置|地点)\s*[:：]\s*[\u4e00-\u9fa50-9]{5,}(?:省|市|区|路|街|号|弄|巷)',
     "具体的地址信息"),
    # 电话模式：完整的11位手机号
    (r'(?:电话|手机|联系方式|tel|phone)\s*[:：]?\s*1[3-9]\d{9}\b',
     "具体的电话号码"),
]


# 备份/垃圾文件后缀模式（匹配文件名末尾）
_BACKUP_SUFFIX_PATTERNS = [
    # .bak 系列
    r'\.bak$',
    r'\.bak_',
    r'\.backup$',
    r'\.backup_',
    # 临时文件
    r'\.tmp$',
    r'\.temp$',
    r'\.swp$',
    r'\.swo$',
    # 旧版本
    r'\.old$',
    r'\.orig$',
    # Vim 备份
    r'~$',
]

# 精确文件名匹配（不分路径，只看 basename）
_BACKUP_EXACT_FILENAMES = {
    '.DS_Store',
    'Thumbs.db',
    'desktop.ini',
}

# 阈值：超过多少个才报告
_BACKUP_THRESHOLD = 3
# 最多列出示例文件数
_BACKUP_MAX_EXAMPLES = 5


def _check_backup_files(code_files: Dict[str, str]) -> List[Dict]:
    """检测项目中的备份/垃圾文件

    检测逻辑：
    1. 扫描所有文件路径
    2. 匹配备份/垃圾文件模式（.bak/.tmp/.old/.swp/~ 等）
    3. 统计数量，超过阈值才报告（避免少量备份文件误报）
    4. 列出前N个示例文件路径

    告警级别：low（代码卫生问题，量大时提示）
    """
    issues = []

    backup_files = []

    for filepath in code_files.keys():
        basename = os.path.basename(filepath)
        basename_lower = basename.lower()

        # 精确匹配（如 .DS_Store, Thumbs.db）
        if basename in _BACKUP_EXACT_FILENAMES or basename_lower in _BACKUP_EXACT_FILENAMES:
            backup_files.append(filepath)
            continue

        # 后缀模式匹配
        is_backup = False
        for pattern in _BACKUP_SUFFIX_PATTERNS:
            if re.search(pattern, basename_lower):
                is_backup = True
                break

        if is_backup:
            backup_files.append(filepath)

    # 超过阈值才报告
    if len(backup_files) >= _BACKUP_THRESHOLD:
        examples = backup_files[:_BACKUP_MAX_EXAMPLES]
        examples_str = "\n".join(f"  - {p}" for p in examples)
        more_count = len(backup_files) - _BACKUP_MAX_EXAMPLES
        if more_count > 0:
            examples_str += f"\n  ... 等{more_count}个更多文件"

        # 取第一个文件作为 issue 的 file 字段（项目级规则，用第一个代表性文件）
        first_file = backup_files[0]

        issues.append({
            "check_id": "QUAL-BAK-FILES",
            "name": "备份/垃圾文件泛滥",
            "severity": "low",
            "file": first_file,
            "line": 1,
            "message": (
                f"项目中发现 {len(backup_files)} 个备份/垃圾文件，"
                f"可能导致仓库膨胀、敏感信息泄露或被误加载。\n"
                f"示例文件：\n{examples_str}"
            ),
            "suggestion": (
                "清理 .bak/.tmp/.old/.swp 等备份文件；"
                "在 .gitignore 中添加备份文件模式；"
                "使用版本管理工具替代手动备份"
            ),
        })

    return issues


# ============================================================
# 测试质量检测（QUAL-TEST-* 系列，共 10 条规则）
# ============================================================
#
# 规则列表：
#   QUAL-TEST-NO-ASSERT        测试用例无断言（high）
#   QUAL-TEST-MOCK-OVERUSE     Mock过度使用（medium）
#   QUAL-TEST-HARDCODE         测试数据硬编码不规范（low）
#   QUAL-TEST-HAPPY-PATH       只测正常路径不测异常（medium）
#   QUAL-TEST-NAMING           测试命名混乱（low）
#   QUAL-TEST-DUPLICATE        测试用例重复（low）
#   QUAL-TEST-BOUNDARY         边界条件缺失（medium）
#   QUAL-TEST-NO-TEARDOWN      测试资源未清理（medium）
#   QUAL-TEST-SLOW-NO-MARK     慢测试无标记（low）— Python
#   QUAL-TEST-INTEGRATION-MISS 集成测试缺失（medium）— 项目级
#
# 设计原则：宁漏勿误，保守检测，误报控制严格。
# ============================================================

# 测试文件路径/文件名识别关键词
_TEST_DIR_KEYWORDS = ("tests", "test", "__tests__", "spec", "specs")
_TEST_BASENAME_PATTERNS = (
    r"^test_",     # test_xxx.py  test_xxx.js
    r"_test\.py$", # xxx_test.py
    r"\.test\.",   # xxx.test.js  xxx.test.ts
    r"\.spec\.",   # xxx.spec.js  xxx.spec.ts
)

# 断言关键词（多种测试框架通用）
_ASSERT_KEYWORDS = (
    # Python
    "assert", "self.assert", "self.fail(",
    "pytest.raises", "pytest.warns", "pytest.fail",
    # JS (Jest / Mocha / Chai / Vitest)
    "expect(", ".toBe(", ".toEqual(", ".toStrictEqual(",
    ".toThrow(", ".toMatch(", ".toHaveLength(",
    "should.", "chai.assert", "assert.",
    "fail(",
)

# 无效断言（恒真式）的模式
_TRIVIAL_ASSERT_PATTERNS = [
    # Python
    r"assert\s+True\b",
    r"assert\s+1\s*==\s*1\b",
    r"assert\s+True\s+is\s+True\b",
    r"assert\s+not\s+False\b",
    r"self\.assertTrue\s*\(\s*True\s*\)",
    # JS
    r"expect\s*\(\s*1\s*\)\s*\.\s*toBe\s*\(\s*1\s*\)",
    r"expect\s*\(\s*true\s*\)\s*\.\s*toBe\s*\(\s*true\s*\)",
    r"expect\s*\(\s*true\s*\)\s*\.\s*toBeTruthy\s*\(\s*\)",
    r"expect\s*\(\s*"".*?""\s*\)\s*\.\s*toBeTruthy\s*\(\s*\)",
    r"assert\s*\.\s*isTrue\s*\(\s*true\s*\)",
]

