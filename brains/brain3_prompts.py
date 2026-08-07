# -*- coding: utf-8 -*-
"""
大脑3 LLM Prompt模板系统（v2.0）
煋鉴(Xinpect) - Brain 3 AI语义分析引擎

设计原则：
1. 领域分离：4大分析领域各自独立的prompt模板
2. 语言感知：根据文件类型注入语言上下文
3. 输出统一：所有模板输出严格JSON，与BrainIssue结构兼容
4. 成本控制：单次请求token上限、文件分片、去重机制
5. 降级友好：无API Key时完全跳过，不影响静态规则结果

四大分析领域：
- LOGIC: 逻辑漏洞检测（条件判断、边界情况、状态一致性）
- DESIGN: 设计缺陷识别（耦合度、职责划分、抽象合理性）
- BIZ: 业务逻辑审查（流程断裂、数据一致性、并发安全）
- INTENT: 代码意图理解（注释不符、命名误导、隐藏副作用）

静态规则：200条规则覆盖8个子领域（SEM-001~SEM-200）
- logic_pattern_rules.json    → 逻辑模式
- dead_code_rules.json        → 死代码
- exception_handling_rules.json → 异常处理
- hardcoded_secrets_rules.json → 硬编码密钥
- inconsistent_return_rules.json → 返回值一致性
- callback_nesting_rules.json → 回调嵌套
- null_safety_rules.json      → 空安全
- unused_code_rules.json      → 未使用代码

LLM增强层在静态规则之上，发现正则/AST无法捕捉的深层语义问题。
"""

import os
import json
import logging
from typing import List, Dict, Optional, Tuple, Any

logger = logging.getLogger(__name__)


# =====================================================================
#  常量与配置
# =====================================================================

# 分析领域定义
ANALYSIS_DOMAINS = {
    "LOGIC": {
        "label": "逻辑漏洞检测",
        "check_id_prefix": "B3-LLM-LOG",
        "description": "条件判断错误、边界情况遗漏、状态不一致、逻辑分支缺失",
    },
    "DESIGN": {
        "label": "设计缺陷识别",
        "check_id_prefix": "B3-LLM-DSN",
        "description": "过度耦合、职责不清、抽象不当、违反SOLID原则",
    },
    "BIZ": {
        "label": "业务逻辑审查",
        "check_id_prefix": "B3-LLM-BIZ",
        "description": "流程断裂、数据不一致、并发问题、事务安全",
    },
    "INTENT": {
        "label": "代码意图理解",
        "check_id_prefix": "B3-LLM-INT",
        "description": "实现与注释不符、命名误导、隐藏副作用、隐含假设",
    },
}

# 严重性映射（LLM输出 → 系统内部）
SEVERITY_MAP = {
    "critical": "blocker",
    "blocker": "blocker",
    "major": "high",
    "high": "high",
    "minor": "medium",
    "medium": "medium",
    "info": "low",
    "low": "low",
}

# 单次LLM请求的最大文件内容字符数（控制成本）
MAX_CODE_CHARS_PER_REQUEST = 8000

# 单次LLM请求的最大文件数
MAX_FILES_PER_REQUEST = 5

# 上下文窗口行数（问题行前后）
CONTEXT_LINES = 15


# =====================================================================
#  语言上下文定义
# =====================================================================

# 根据文件扩展名确定编程语言及特有关注点
LANGUAGE_CONTEXT = {
    ".py": {
        "lang": "Python",
        "paradigm": "动态类型、GIL、鸭子类型",
        "pitfalls": [
            "可变默认参数（def f(lst=[])）",
            "全局变量与闭包陷阱",
            "GIL对多线程的影响",
            "__eq__ vs __is__ 混淆",
            "生成器耗尽未处理",
            "循环导入",
        ],
        "async_note": "asyncio事件循环、await遗漏",
    },
    ".js": {
        "lang": "JavaScript",
        "paradigm": "动态类型、原型链、单线程事件循环",
        "pitfalls": [
            "隐式类型转换（== vs ===）",
            "this指向丢失",
            "闭包变量捕获（循环中的var vs let）",
            "Promise未处理rejection",
            "原型链污染",
            "浮点精度（0.1 + 0.2）",
        ],
        "async_note": "回调地狱、async/await错误处理",
    },
    ".ts": {
        "lang": "TypeScript",
        "paradigm": "静态类型、泛型、接口",
        "pitfalls": [
            "any类型滥用（等同于无类型）",
            "非空断言（!）掩盖空值风险",
            "类型断言（as）绕过类型检查",
            "enum值与运行时不一致",
            "泛型约束缺失导致运行时错误",
        ],
        "async_note": "Promise类型推断、async返回值",
    },
    ".tsx": {
        "lang": "TypeScript/React",
        "paradigm": "组件化、JSX、Hooks",
        "pitfalls": [
            "useEffect依赖数组不完整",
            "useState异步更新（旧闭包引用）",
            "key属性缺失或不稳定",
            "useRef替代state导致不重渲染",
            "事件处理函数未稳定引用",
        ],
        "async_note": "useEffect清理函数、Suspense边界",
    },
    ".jsx": {
        "lang": "JavaScript/React",
        "paradigm": "组件化、JSX、Hooks",
        "pitfalls": [
            "useEffect依赖数组不完整",
            "useState闭包陈旧值",
            "key属性使用index",
            "内存泄漏（未取消订阅/定时器）",
            "不必要的重渲染（对象引用变化）",
        ],
        "async_note": "useEffect副作用清理",
    },
    ".vue": {
        "lang": "Vue (JavaScript/TypeScript)",
        "paradigm": "响应式、组合式/选项式API",
        "pitfalls": [
            "响应式丢失（解构props破坏响应性）",
            "watchEffect依赖追踪不完整",
            "onMounted中直接访问DOM（SSR不兼容）",
            "computed的getter有副作用",
            "v-for无唯一key",
        ],
        "async_note": "异步组件、Suspense",
    },
    ".java": {
        "lang": "Java",
        "paradigm": "静态强类型、JVM、面向对象",
        "pitfalls": [
            "空指针（NPE）",
            "字符串用==比较（应用equals）",
            "资源未关闭（try-with-resources缺失）",
            "并发集合的线程安全",
            "hashCode与equals不一致",
        ],
        "async_note": "线程池管理、CompletableFuture异常处理",
    },
    ".go": {
        "lang": "Go",
        "paradigm": "静态类型、goroutine、接口组合",
        "pitfalls": [
            "goroutine泄漏（无退出机制）",
            "defer在循环中的陷阱",
            "切片append共享底层数组",
            "interface nil判断（typed nil）",
            "map并发读写",
        ],
        "async_note": "channel死锁、context取消传播",
    },
    ".wxml": {
        "lang": "微信小程序WXML",
        "paradigm": "模板引擎、数据绑定、组件化",
        "pitfalls": [
            "数据绑定路径错误",
            "条件渲染(wx:if)与列表(wx:for)嵌套问题",
            "事件绑定参数传递",
            "setData性能（频繁/大数据量调用）",
            "组件生命周期与页面生命周期不同步",
        ],
        "async_note": "异步API回调、云函数超时",
    },
    ".wxss": {
        "lang": "微信小程序WXSS",
        "paradigm": "rpx单位、样式隔离",
        "pitfalls": [
            "rpx在不同设备的适配差异",
            "样式优先级覆盖",
            "组件样式穿透问题",
        ],
        "async_note": "",
    },
}


def detect_language(file_path: str) -> Dict:
    """根据文件路径检测编程语言上下文"""
    ext = os.path.splitext(file_path)[1].lower()
    default_ctx = {
        "lang": "Unknown",
        "paradigm": "",
        "pitfalls": [],
        "async_note": "",
    }
    return LANGUAGE_CONTEXT.get(ext, default_ctx)


# =====================================================================
#  System Prompt模板
# =====================================================================

SYSTEM_PROMPT_BASE = """你是煋鉴(Xinpect)代码审查系统的AI语义分析大脑（Brain 3）。
你是一位资深代码审查专家，专注于发现规则引擎无法捕捉的深层语义问题。

## 你的分析原则
1. **精准性**：只报告确信度高的真实问题，严禁误报
2. **可操作性**：每个问题必须给出具体的修复建议（含代码示例）
3. **上下文感知**：理解代码的业务意图，不脱离上下文机械检查
4. **成本意识**：只报告真正影响代码质量的问题，不报风格偏好

## 输出格式要求
严格返回JSON数组，每个元素包含以下字段：
```json
{
  "check_id": "检查项ID（格式见下文）",
  "severity": "critical|major|minor|info",
  "file": "文件相对路径",
  "line": 行号（整数，0表示文件级别问题）,
  "message": "问题描述（一句话，不超过80字）",
  "suggestion": "修复建议（含代码示例，不超过200字）",
  "confidence": 置信度（0.0-1.0）,
  "category": "问题分类标签（如：null_safety, race_condition, logic_error等）"
}
```

## 检查项ID格式
- 逻辑漏洞: B3-LLM-LOG-001, B3-LLM-LOG-002, ...
- 设计缺陷: B3-LLM-DSN-001, B3-LLM-DSN-002, ...
- 业务逻辑: B3-LLM-BIZ-001, B3-LLM-BIZ-002, ...
- 代码意图: B3-LLM-INT-001, B3-LLM-INT-002, ...

## 严重性标准
- critical: 会导致程序崩溃、数据丢失或安全漏洞
- major: 会导致功能异常或性能严重下降
- minor: 代码质量问题，不影响功能但影响可维护性
- info: 改进建议，非问题

## 禁止事项
- 禁止报告已有静态规则覆盖的问题（如硬编码密钥、空catch块等基础问题）
- 禁止报告代码风格问题（命名、缩进、空格）
- 禁止对没有读取到代码的文件做推测性分析
- 如果没有发现问题，返回空数组 []

只返回JSON数组，不要任何解释文字、markdown标记或代码围栏。"""


# =====================================================================
#  领域专用Prompt模板
# =====================================================================

DOMAIN_PROMPTS = {
    "LOGIC": {
        "system_addition": """## 本次任务：逻辑漏洞检测

你需要重点关注以下逻辑层面的问题：

### 1. 条件判断错误
- 条件表达式逻辑与注释/变量名描述不一致
- 短路求值导致的意外行为（如 a && a.b()，a可能为null）
- 条件分支遗漏（if-else未覆盖所有情况）
- 冗余/矛盾的条件判断

### 2. 边界情况遗漏
- 数组/列表未检查空或越界
- 数值计算未处理溢出、NaN、Infinity
- 字符串操作未处理空字符串、null、undefined
- 日期/时间边界（闰年、时区、夏令时）

### 3. 状态不一致
- 多个关联变量更新不同步
- 状态机转换遗漏非法状态
- 缓存与源数据过期不同步
- 数据库事务中间状态暴露

### 4. 类型相关逻辑错误
- 隐式类型转换导致条件判断错误
- 浮点比较（0.1 + 0.2 !== 0.3）
- 引用相等 vs 值相等混淆

**注意**：只报告有代码证据的逻辑问题，不要凭猜测报告。""",

        "user_template": """请分析以下{lang}代码，重点检查逻辑漏洞。

{lang_context}

## 代码内容

{code_blocks}

请返回发现的问题JSON数组。如果没有发现逻辑漏洞，返回空数组 []。""",
    },

    "DESIGN": {
        "system_addition": """## 本次任务：设计缺陷识别

你需要重点关注以下设计层面的问题：

### 1. 过度耦合
- 模块间直接依赖实现而非接口
- 数据流路径不清晰（跨层调用、全局状态污染）
- 循环依赖（A引用B，B引用A）

### 2. 职责不清
- 单个函数/类承担过多职责（>50行的函数尤其注意）
- 业务逻辑与基础设施代码混在一起
- 数据转换/校验/业务规则混杂在同一方法

### 3. 抽象不当
- 过度抽象（简单场景引入不必要的工厂/策略/装饰器）
- 抽象不足（大量重复代码未提取公共逻辑）
- 接口/协议设计不合理（参数过多、返回值不明确）

### 4. 架构反模式
- 上帝对象（一个类/文件承担几乎所有功能）
- 贫血模型（业务逻辑全在service层，model只有getter/setter）
- 回调地狱（嵌套层级>3层的异步调用）

**注意**：设计问题需要结合项目规模判断，小项目的"反模式"可能完全合理。""",

        "user_template": """请分析以下{lang}代码，重点检查设计缺陷。

{lang_context}

## 代码内容

{code_blocks}

请返回发现的设计问题JSON数组。如果没有发现设计缺陷，返回空数组 []。""",
    },

    "BIZ": {
        "system_addition": """## 本次任务：业务逻辑审查

你需要重点关注以下业务逻辑层面的问题：

### 1. 流程断裂
- 业务操作步骤间缺少必要的校验/确认
- 错误处理路径未考虑用户体验（直接抛出原始错误）
- 状态流转不完整（如订单状态从"待支付"直接跳到"已完成"）

### 2. 数据一致性
- 读写操作间缺少事务保护
- 并发写入时的竞态条件（如库存超卖、余额透支）
- 数据迁移/更新时部分失败未回滚
- 缓存写入与数据库写入的时序问题

### 3. 并发与竞态
- 共享资源无锁保护
- 事件监听器重复注册
- 防抖/节流缺失导致的重复提交
- WebSocket/长连接断开重连未处理

### 4. 边界业务场景
- 支付/退款流程的幂等性
- 批量操作的原子性
- 超时处理（网络请求、异步任务）
- 用户并发操作（双击提交、重复点击）

**注意**：业务逻辑问题需要结合上下文理解，如果代码片段不足以判断业务场景，请说明并返回空。""",

        "user_template": """请分析以下{lang}代码，重点检查业务逻辑问题。

{lang_context}

## 代码内容

{code_blocks}

请返回发现的业务逻辑问题JSON数组。如果没有发现业务逻辑问题，返回空数组 []。""",
    },

    "INTENT": {
        "system_addition": """## 本次任务：代码意图理解

你需要重点关注代码实现与其意图的不一致：

### 1. 实现与注释不符
- 函数/方法的实际行为与注释描述不一致
- TODO/FIXME/HACK标注的问题未处理
- JSDoc/docstring的参数说明与实际签名不匹配
- 过时的注释（代码已改但注释未更新）

### 2. 命名误导
- 函数名暗示的行为与实际行为不一致（如名为getUser但实际会创建用户）
- 变量名暗示的类型与实际类型不一致
- 布尔变量名非问句形式导致语义歧义

### 3. 隐藏副作用
- 看似只读的操作实际修改了全局状态/入参
- getter方法中执行了IO操作
- 属性访问器触发了复杂计算
- 初始化代码在模块加载时执行了意外操作

### 4. 隐含假设
- 代码假设数据格式但未验证（如假设API返回固定结构）
- 依赖特定执行顺序但未显式保证
- 假设环境变量/配置项存在但未做fallback
- 依赖特定时区/编码/locale

**注意**：意图问题需要有明确的代码证据（注释、命名、函数签名），不要凭感觉报告。""",

        "user_template": """请分析以下{lang}代码，重点检查代码意图与实现的一致性。

{lang_context}

## 代码内容

{code_blocks}

请返回发现的意图不一致问题JSON数组。如果没有发现问题，返回空数组 []。""",
    },
}


# =====================================================================
#  Prompt构建器
# =====================================================================

class PromptBuilder:
    """动态构建LLM prompt的构建器

    职责：
    1. 根据分析领域选择对应的prompt模板
    2. 根据文件类型注入语言上下文
    3. 将代码内容嵌入模板
    4. 控制token消耗（截断过长代码）
    """

    def __init__(self, project_path: str = ""):
        self.project_path = project_path
        self._counter = {domain: 0 for domain in ANALYSIS_DOMAINS}

    def build_messages(
        self,
        domain: str,
        code_blocks: List[Dict[str, str]],
        project_context: str = "",
    ) -> List[Dict[str, str]]:
        """构建完整的LLM消息列表

        Args:
            domain: 分析领域（LOGIC/DESIGN/BIZ/INTENT）
            code_blocks: 代码块列表，每项 {"file": 相对路径, "content": 代码内容, "line": 起始行号}
            project_context: 项目上下文描述（如框架信息、目录结构摘要）

        Returns:
            [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
        """
        if domain not in DOMAIN_PROMPTS:
            raise ValueError(f"未知分析领域: {domain}")

        # 检测主要语言
        primary_lang = self._detect_primary_language(code_blocks)

        # 构建system prompt
        system_content = SYSTEM_PROMPT_BASE
        system_content += "\n\n" + DOMAIN_PROMPTS[domain]["system_addition"]

        # 如果有项目上下文，附加
        if project_context:
            system_content += f"\n\n## 项目上下文\n{project_context}"

        # 构建user prompt
        code_text = self._format_code_blocks(code_blocks)
        lang_context = self._build_lang_context(primary_lang)

        user_content = DOMAIN_PROMPTS[domain]["user_template"].format(
            lang=primary_lang.get("lang", "Unknown"),
            lang_context=lang_context,
            code_blocks=code_text,
        )

        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ]

    def _detect_primary_language(self, code_blocks: List[Dict]) -> Dict:
        """从代码块中检测主要编程语言"""
        lang_count: Dict[str, int] = {}
        for block in code_blocks:
            file_path = block.get("file", "")
            ctx = detect_language(file_path)
            lang = ctx["lang"]
            lang_count[lang] = lang_count.get(lang, 0) + len(block.get("content", ""))

        if not lang_count:
            return LANGUAGE_CONTEXT.get(".js", {})

        # 选择代码量最大的语言
        primary = max(lang_count, key=lang_count.get)
        # 找到对应的完整上下文
        for ext, ctx in LANGUAGE_CONTEXT.items():
            if ctx["lang"] == primary:
                return ctx
        return {"lang": primary, "paradigm": "", "pitfalls": [], "async_note": ""}

    def _build_lang_context(self, lang_ctx: Dict) -> str:
        """构建语言上下文描述"""
        parts = []
        if lang_ctx.get("lang"):
            parts.append(f"**语言**: {lang_ctx['lang']}")
        if lang_ctx.get("paradigm"):
            parts.append(f"**特性**: {lang_ctx['paradigm']}")
        if lang_ctx.get("pitfalls"):
            pitfalls = "、".join(lang_ctx["pitfalls"][:4])  # 最多列4个
            parts.append(f"**常见陷阱**: {pitfalls}")
        if lang_ctx.get("async_note"):
            parts.append(f"**异步注意**: {lang_ctx['async_note']}")

        return "\n".join(parts) if parts else ""

    def _format_code_blocks(self, code_blocks: List[Dict]) -> str:
        """格式化代码块，控制总字符数"""
        parts = []
        total_chars = 0

        for block in code_blocks:
            file_path = block.get("file", "unknown")
            content = block.get("content", "")
            start_line = block.get("line", 1)

            # 截断过长内容
            if total_chars + len(content) > MAX_CODE_CHARS_PER_REQUEST:
                remaining = MAX_CODE_CHARS_PER_REQUEST - total_chars
                if remaining > 500:
                    content = content[:remaining] + "\n... [内容已截断，为控制成本]"
                else:
                    break

            parts.append(f"### 文件: {file_path} (从第{start_line}行开始)\n```")
            parts.append(content)
            parts.append("```")
            total_chars += len(content)

        return "\n".join(parts)

    def next_check_id(self, domain: str) -> str:
        """生成下一个check_id"""
        self._counter[domain] = self._counter.get(domain, 0) + 1
        prefix = ANALYSIS_DOMAINS[domain]["check_id_prefix"]
        return f"{prefix}-{self._counter[domain]:03d}"


# =====================================================================
#  LLM语义分析器
# =====================================================================

class LLMSemanticAnalyzer:
    """Brain 3的LLM语义分析协调器

    职责：
    1. 收集项目代码文件
    2. 按领域分批调用LLM分析
    3. 解析LLM返回的JSON结果
    4. 与静态规则结果合并去重
    5. 生成统一的BrainIssue列表

    降级机制：
    - 无API Key → 返回空列表，完全依赖静态规则
    - LLM调用失败 → 返回空列表 + 记录日志，不影响整体流程
    - JSON解析失败 → 跳过该批次，继续下一批次
    """

    # 要跳过的目录
    _SKIP_DIRS = {
        "node_modules", ".git", "__pycache__", ".venv", "venv",
        "dist", "build", "target", ".next", ".nuxt", "vendor",
        "backups", "backup", "site-packages", ".ruff_cache",
        ".mypy_cache", ".pytest_cache", ".tox", "output",
        ".xinpect_cache", ".qa_history",
    }
    _SKIP_PREFIXES = ("backup", "bak", "_backup", "old_", ".backup")

    # 支持的源码扩展名
    _CODE_EXTS = {
        ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go",
        ".rb", ".php", ".vue", ".wxml", ".wxss",
    }

    # 单文件最大读取行数
    _MAX_FILE_LINES = 300  # v4.2.2: 500→300 减少LLM输入体积

    # 最大文件数
    _MAX_FILES = 20  # v4.2.2: 50→20 控制LLM总输入量

    # 总字符预算（v4.2.2新增：防止18万字符塞爆LLM）
    _MAX_TOTAL_CHARS = 40000

    def __init__(self, config: dict, project_path: str):
        self.config = config
        self.project_path = project_path
        self.prompt_builder = PromptBuilder(project_path)
        self._llm = None

    def _get_llm(self):
        """延迟获取LLM客户端"""
        if self._llm is None:
            try:
                from core.llm_client import create_llm_client
                self._llm = create_llm_client(self.config, "brain3")
            except (ImportError, Exception) as e:
                logger.warning(f"Brain3 LLM客户端创建失败: {e}")
                return None
        return self._llm

    def analyze(
        self,
        domains: Optional[List[str]] = None,
        existing_issues: Optional[List] = None,
    ) -> List[Dict]:
        """执行LLM语义分析

        Args:
            domains: 要执行的分析领域列表，None表示全部4个领域
            existing_issues: 已有的静态规则结果（用于去重）

        Returns:
            与BrainIssue兼容的字典列表
        """
        llm = self._get_llm()
        if not llm or not llm.is_available:
            logger.info("Brain3 LLM不可用，跳过语义分析")
            return []

        if domains is None:
            domains = list(ANALYSIS_DOMAINS.keys())

        # 收集代码文件
        code_files = self._collect_code_files()
        if not code_files:
            return []

        # 构建项目上下文
        project_context = self._build_project_context(code_files)

        # 按领域逐个分析
        all_issues = []
        for domain in domains:
            try:
                issues = self._analyze_domain(llm, domain, code_files, project_context)
                all_issues.extend(issues)
            except Exception as e:  # noqa: intentional catch-all
                logger.warning(f"Brain3 领域{domain}分析失败: {e}")
                continue

        # 与静态规则结果去重
        if existing_issues:
            all_issues = self._deduplicate(all_issues, existing_issues)

        return all_issues

    def _analyze_domain(
        self,
        llm,
        domain: str,
        code_files: List[Dict],
        project_context: str,
    ) -> List[Dict]:
        """对单个领域执行LLM分析"""
        all_issues = []

        # 按MAX_FILES_PER_REQUEST分批
        for i in range(0, len(code_files), MAX_FILES_PER_REQUEST):
            batch = code_files[i:i + MAX_FILES_PER_REQUEST]

            # 构建prompt
            messages = self.prompt_builder.build_messages(
                domain=domain,
                code_blocks=batch,
                project_context=project_context,
            )

            # 调用LLM
            try:
                response = llm.chat_json(
                    messages=messages,
                    temperature=0.15,
                    timeout=30,
                )
            except Exception as e:  # noqa: intentional catch-all
                logger.warning(f"Brain3 LLM调用失败(domain={domain}): {e}")
                continue

            if not response or not isinstance(response, list):
                continue

            # 解析响应
            for item in response:
                issue = self._parse_llm_issue(item, domain)
                if issue:
                    # 过滤低置信度
                    confidence = item.get("confidence", 0.5)
                    if confidence >= 0.6:
                        all_issues.append(issue)

        return all_issues

    def _parse_llm_issue(self, item: Dict, domain: str) -> Optional[Dict]:
        """将LLM返回的单个item解析为标准issue字典"""
        try:
            # 提取字段
            raw_severity = item.get("severity", "minor")
            severity = SEVERITY_MAP.get(raw_severity.lower(), "medium")

            # 生成check_id（如果LLM没有提供正确的格式）
            check_id = item.get("check_id", "")
            if not check_id or not check_id.startswith("B3-LLM-"):
                check_id = self.prompt_builder.next_check_id(domain)

            file_path = item.get("file", "")
            line = item.get("line", 0)
            if not isinstance(line, int):
                line = 0

            message = item.get("message", "")
            if not message:
                return None

            suggestion = item.get("suggestion", "")
            category = item.get("category", domain.lower())

            return {
                "check_id": check_id,
                "name": message[:40],
                "severity": severity,
                "file": file_path,
                "line": line,
                "message": message,
                "suggestion": suggestion,
                "_category": category,
                "_confidence": item.get("confidence", 0.5),
                "_source": "llm",
            }

        except Exception as e:  # noqa: intentional catch-all
            logger.debug(f"Brain3 解析LLM issue失败: {e}, item={item}")
            return None

    def _collect_code_files(self) -> List[Dict]:
        """收集项目中的代码文件内容"""
        files = []
        count = 0
        total_chars = 0

        for root, dirs, filenames in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if d not in self._SKIP_DIRS 
                       and not d.startswith(".")
                       and not d.startswith(self._SKIP_PREFIXES)]

            for fname in filenames:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in self._CODE_EXTS:
                    continue

                fpath = os.path.join(root, fname)
                rel_path = os.path.relpath(fpath, self.project_path)

                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()

                    # 截断过长的文件
                    if len(lines) > self._MAX_FILE_LINES:
                        content = "".join(lines[:self._MAX_FILE_LINES])
                        content += f"\n// ... [文件截断，共{len(lines)}行，仅分析前{self._MAX_FILE_LINES}行]"
                    else:
                        content = "".join(lines)

                    # 跳过空文件
                    if not content.strip():
                        continue

                    # v4.2.2: 总字符预算控制，超出则停止收集
                    total_chars += len(content)
                    if total_chars > self._MAX_TOTAL_CHARS:
                        break

                    files.append({
                        "file": rel_path,
                        "content": content,
                        "line": 1,
                    })
                    count += 1
                    if count >= self._MAX_FILES:
                        return files

                except (OSError, IOError):
                    continue

        return files

    def _build_project_context(self, code_files: List[Dict]) -> str:
        """构建项目上下文摘要"""
        if not code_files:
            return ""

        # 统计文件类型
        ext_count: Dict[str, int] = {}
        for f in code_files:
            ext = os.path.splitext(f["file"])[1].lower()
            ext_count[ext] = ext_count.get(ext, 0) + 1

        # 构建摘要
        parts = [f"项目包含{len(code_files)}个源码文件："]
        for ext, cnt in sorted(ext_count.items(), key=lambda x: -x[1])[:5]:
            lang = LANGUAGE_CONTEXT.get(ext, {}).get("lang", ext)
            parts.append(f"- {lang}: {cnt}个文件")

        # 检测框架（简单启发式）
        frameworks = self._detect_frameworks(code_files)
        if frameworks:
            parts.append(f"\n检测到框架/库: {', '.join(frameworks)}")

        return "\n".join(parts)

    def _detect_frameworks(self, code_files: List[Dict]) -> List[str]:
        """简单检测项目使用的框架"""
        frameworks = set()
        file_paths = [f["file"] for f in code_files]
        all_content = " ".join(f.get("content", "")[:500] for f in code_files[:10])

        # 文件路径线索
        if any("pages/" in p for p in file_paths) and any(p.endswith(".wxml") for p in file_paths):
            frameworks.add("微信小程序")
        if any("components/" in p for p in file_paths):
            if any(p.endswith(".vue") for p in file_paths):
                frameworks.add("Vue")
            elif any(".tsx" in p or ".jsx" in p for p in file_paths):
                frameworks.add("React")

        # 内容线索
        if "import React" in all_content or "from 'react'" in all_content:
            frameworks.add("React")
        if "import { ref" in all_content or "import { onMounted" in all_content:
            frameworks.add("Vue3 Composition API")
        if "from 'django'" in all_content or "DJANGO_SETTINGS" in all_content:
            frameworks.add("Django")
        if "from flask" in all_content.lower():
            frameworks.add("Flask")
        if "fastapi" in all_content.lower():
            frameworks.add("FastAPI")
        if "express" in all_content.lower() and ("require('express')" in all_content or "from 'express'" in all_content):
            frameworks.add("Express")
        if "springframework" in all_content.lower():
            frameworks.add("Spring")

        return list(frameworks)[:5]

    def _deduplicate(
        self,
        llm_issues: List[Dict],
        existing_issues: List,
    ) -> List[Dict]:
        """去除LLM结果与静态规则结果的重复

        去重策略：
        1. 相同文件 + 相同行号（±2行容差）→ 视为重复
        2. 相同check_id → 视为重复
        3. 消息相似度极高（包含关系）→ 视为重复
        """
        if not existing_issues:
            return llm_issues

        # 构建已有issue的索引
        existing_index = set()
        existing_by_file_line: List[Tuple[str, int, str]] = []

        for iss in existing_issues:
            file_path = iss.file if hasattr(iss, "file") else iss.get("file", "")
            line = iss.line if hasattr(iss, "line") else iss.get("line", 0)
            message = iss.message if hasattr(iss, "message") else iss.get("message", "")
            check_id = iss.check_id if hasattr(iss, "check_id") else iss.get("check_id", "")

            existing_index.add(check_id)
            existing_by_file_line.append((file_path, line, message))

        deduplicated = []
        for issue in llm_issues:
            file_path = issue.get("file", "")
            line = issue.get("line", 0)
            message = issue.get("message", "")
            check_id = issue.get("check_id", "")

            # 检查check_id重复
            if check_id in existing_index:
                continue

            # 检查文件+行号重复（±2行容差）
            is_dup = False
            for ex_file, ex_line, ex_msg in existing_by_file_line:
                if file_path == ex_file and abs(line - ex_line) <= 2:
                    # 行号相近，检查消息是否有包含关系
                    if message and ex_msg:
                        short_msg = message[:20]
                        if short_msg in ex_msg or ex_msg[:20] in message:
                            is_dup = True
                            break
                    else:
                        is_dup = True
                        break

            if not is_dup:
                deduplicated.append(issue)

        return deduplicated


# =====================================================================
#  多领域批量分析器（支持并行/串行策略）
# =====================================================================

class MultiDomainAnalyzer:
    """多领域批量分析协调器

    支持两种策略：
    - serial: 串行执行各领域（默认，成本低）
    - parallel: 并行执行各领域（速度快，但LLM并发可能限流）
    """

    def __init__(self, config: dict, project_path: str):
        self.config = config
        self.project_path = project_path

    def run(
        self,
        domains: Optional[List[str]] = None,
        existing_issues: Optional[List] = None,
        strategy: str = "serial",
    ) -> List[Dict]:
        """执行多领域分析

        Args:
            domains: 分析领域列表，None=全部
            existing_issues: 已有静态规则结果
            strategy: "serial" 或 "parallel"

        Returns:
            去重后的issue字典列表
        """
        analyzer = LLMSemanticAnalyzer(self.config, self.project_path)

        if strategy == "parallel":
            return self._run_parallel(analyzer, domains, existing_issues)
        else:
            return analyzer.analyze(domains, existing_issues)

    def _run_parallel(
        self,
        analyzer: LLMSemanticAnalyzer,
        domains: Optional[List[str]],
        existing_issues: Optional[List],
    ) -> List[Dict]:
        """并行执行各领域分析"""
        import concurrent.futures

        if domains is None:
            domains = list(ANALYSIS_DOMAINS.keys())

        all_issues = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(domains)) as executor:
            futures = {}
            for domain in domains:
                future = executor.submit(
                    analyzer._analyze_domain,
                    analyzer._get_llm(),
                    domain,
                    analyzer._collect_code_files(),
                    analyzer._build_project_context(analyzer._collect_code_files()),
                )
                futures[future] = domain

            for future in concurrent.futures.as_completed(futures):
                domain = futures[future]
                try:
                    issues = future.result()
                    all_issues.extend(issues)
                except Exception as e:  # noqa: intentional catch-all
                    logger.warning(f"Brain3 并行分析领域{domain}失败: {e}")

        # 去重
        if existing_issues:
            all_issues = analyzer._deduplicate(all_issues, existing_issues)

        return all_issues


# =====================================================================
#  便捷函数
# =====================================================================

def create_llm_analyzer(config: dict, project_path: str) -> Optional[LLMSemanticAnalyzer]:
    """创建LLM语义分析器（如果LLM可用）

    Returns:
        LLMSemanticAnalyzer实例，LLM不可用时返回None
    """
    analyzer = LLMSemanticAnalyzer(config, project_path)
    llm = analyzer._get_llm()
    if not llm or not llm.is_available:
        return None
    return analyzer


def build_semantic_prompt(
    domain: str,
    code_blocks: List[Dict[str, str]],
    project_context: str = "",
) -> List[Dict[str, str]]:
    """便捷函数：快速构建prompt消息列表

    Args:
        domain: 分析领域（LOGIC/DESIGN/BIZ/INTENT）
        code_blocks: [{"file": "path/to/file.py", "content": "...", "line": 1}]
        project_context: 项目上下文描述

    Returns:
        [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
    """
    builder = PromptBuilder()
    return builder.build_messages(domain, code_blocks, project_context)


def get_supported_domains() -> List[str]:
    """获取所有支持的分析领域"""
    return list(ANALYSIS_DOMAINS.keys())


def get_domain_info(domain: str) -> Dict:
    """获取领域详细信息"""
    return ANALYSIS_DOMAINS.get(domain, {})
