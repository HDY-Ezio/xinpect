# 煋鉴规则目录组织规范

> 版本: v4.3.0 | 最后更新: 2026-08

## 目录结构

```
rules/
├── _reference/                 # 🔍 参考规则（不加载，仅作知识库查阅）
│   ├── semantic/               #   语义参考规则（1082 条，无对应 AST 检查方法）
│   │   ├── brain2_security/
│   │   ├── brain3_semantic/
│   │   ├── brain7_architecture/
│   │   ├── kotlin/
│   │   └── swift/
│   ├── cpp/                    #   C++ 语言参考规则
│   ├── csharp/                 #   C# 语言参考规则
│   ├── go/                     #   Go 语言参考规则
│   ├── java/                   #   Java 语言参考规则
│   ├── php/                    #   PHP 语言参考规则
│   ├── ruby/                   #   Ruby 语言参考规则
│   └── rust/                   #   Rust 语言参考规则
│
├── common/                    # 通用规则（跨语言/跨框架）
├── brain2_security/           # Brain 2 - 安全审计规则
├── brain3_semantic/           # Brain 3 - AI语义分析规则
├── brain4_performance/        # Brain 4 - 性能优化规则
├── brain5_deps/               # Brain 5 - 依赖审计规则
├── brain6_code_quality/       # Brain 6 - 代码质量规则
├── brain7_architecture/       # Brain 7 - 架构健康规则
├── security/                  # 安全相关补充规则 → Brain 2
├── performance/               # 性能相关补充规则 → Brain 4
├── async_concurrency/         # 异步并发规则 → Brain 3
├── config_deploy/             # 配置部署规则 → Brain 5
├── ci_cd/                     # CI/CD规则 → Brain 2
├── error_quality/             # 错误处理质量规则 → Brain 3
├── web/                       # Web前端规则 → Brain 1
├── python/                    # Python语言规则 → Brain 1
├── java/ go/ rust/ ...        # 其他语言规则 → Brain 1
└── README.md                  # 本文件
```

> **重要**：`_` 开头的目录会被规则加载器自动跳过。
> `_reference/` 下的规则仅作文档/知识库使用，不参与实际扫描。

## 可执行规则 vs 参考规则

### 可执行规则（可执行目录下）

| 类型 | 数量 | 说明 |
|------|------|------|
| REGEX（Python + JSON） | ~1130 条 | 正则/代码匹配规则，由 Brain 1 规则引擎执行 |
| SEMGREP | 500 条 | AST 安全规则，需要安装 semgrep CLI |
| SEMANTIC | 307 条 | 语义分析规则，由 `semantic_scanner` 执行 |
| **合计** | **~1936 条** | 实际可运行的规则总数 |

### 参考规则（`_reference/` 下）

| 类型 | 数量 | 说明 |
|------|------|------|
| 语义参考规则 | 1082 条 | 纯描述性语义规则，category 不在 `semantic_scanner._CATEGORY_TO_CHECK` 中 |
| 语言参考规则 | ~81 条 | Java/Go/Rust/C++/C#/PHP/Ruby 等语言的规则描述 |

### 分类依据

规则加载器使用以下逻辑判断语义规则是否可执行：

1. 读取 `core/semantic_scanner.py` 中的 `_CATEGORY_TO_CHECK` 映射表
2. 如果规则的 `category` 字段在映射表中 → `executable`（可执行）
3. 否则 → `reference`（参考，仅作知识库）

### 为什么分开放

- **口径清晰**：对外宣称的"X条规则"明确是可执行的数量
- **加载性能**：避免加载 1000+ 条无法执行的规则拖慢启动
- **维护方便**：参考规则可随时补充，不影响可执行规则计数
- **向后兼容**：`get_semantic_rules_with_reference()` 仍可获取全部语义规则

## 分类维度

### 主维度：执行引擎类型（由 rule_loader 自动分类）

规则加载器 (`core/rule_loader.py`) 使用 `os.walk` 递归遍历所有子目录，
通过 `RuleSchema.classify_rule()` 自动将每条规则分类到对应执行引擎：

| 引擎类型 | 判定条件 | 执行路径 |
|---------|---------|---------|
| **REGEX** | 规则含可执行 `pattern` 字段 | Rule对象 → Brain 1 规则引擎 |
| **SEMGREP** | 规则含 `semgrep_id` / `detection_pattern` / ID以`-semg`结尾 | semgrep_rules列表 → Brain 6 Semgrep引擎 |
| **SEMANTIC** | 以上均不满足（纯语义描述规则） | semantic_rules字典 → 对应大脑知识库 |

### 次维度：领域（通过 module_id 和 category 字段体现）

每条 Python 规则在 `RULES` 列表中声明 `module_id`（数字），对应大脑编号：

| module_id | 大脑 | 说明 |
|-----------|------|------|
| 1-2 | Brain 1 | 规则引擎（通用匹配） |
| 3 | Brain 2 | 安全审计 |
| 4-5 | Brain 3 | AI语义分析 |
| 6-7 | Brain 4 | 性能优化 |
| 8-9 | Brain 5 | 依赖审计 |
| 10-12 | Brain 6 | 代码质量 |
| 13-16 | Brain 7 | 架构健康 |
| 17-19 | Brain 8 | 业务安全 |
| 20+ | 扩展模块 | 补充规则（仍按数字归类） |

JSON 规则通过 `DIR_TO_BRAIN` 映射表（见 `core/rule_schema.py`）确定目标大脑。

## 新规则编写规范

1. **每条规则必须有明确的 `module_id`**，且必须为数字字符串（如 `'3'`, `'12'`），
   禁止使用文字描述（如 `'security'`, `'performance'`）。

2. **禁止使用 `supplementary` 命名**：
   - ❌ `supplementary_rules.py`、`supplementary_rules_2.py`
   - ✅ 按领域命名，如 `naming_convention_rules.py`、`error_handling_rules.py`

3. **放置位置**：将新规则文件放在最相关的领域目录下。
   - 跨领域通用规则 → `common/`
   - 安全相关 → `brain2_security/` 或 `security/`
   - 性能相关 → `brain4_performance/` 或 `performance/`
   - 语言特定 → 对应语言目录（`python/`、`java/` 等）

4. **Python 规则文件格式**：

```python
RULES = [
    {
        'id': 'SEC-EXT-010',
        'name': '规则名称',
        'level': 'warning',  # blocking / problem / suggestion
        'category': 'security_extension',
        'module_id': '3',  # 必须为数字字符串
        'applicable_types': [],  # 空列表表示所有项目类型适用
        'description': '规则描述',
        'check': check_function,
    },
]
```

5. **JSON 规则文件格式**：

```json
{
  "rules": [
    {
      "check_id": "SEC-001",
      "name": "规则名称",
      "severity": "medium",
      "pattern": "正则表达式（REGEX类）或留空（SEMANTIC类）",
      "description": "规则描述",
      "suggestion": "修复建议",
      "brain_id": "2"
    }
  ]
}
```

## 统计查看

```bash
# 查看规则加载统计
cd <project_root>
PYTHONPATH=. python3 -c "
from core.rule_loader import RuleLoader
loader = RuleLoader()
rules = loader.load_all()
print(f'Total: {len(rules)}')
print(f'Stats: {loader.get_stats()}')
"
```
