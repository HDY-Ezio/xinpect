<div align="center">

# 🔥 煋鉴 Xinpect

### 不是又一个 Linter。是你的 AI 代码安全官。

**3 大脑本地核心 · 1000+ 条规则 · 14 种语言 · 3 秒出报告**

[![Rules](https://img.shields.io/badge/规则-1000%2B-orange?style=for-the-badge)]()
[![Brains](https://img.shields.io/badge/大脑-3%20核心-blue?style=for-the-badge)]()
[![Languages](https://img.shields.io/badge/语言-14%2B-green?style=for-the-badge)]()
[![Speed](https://img.shields.io/badge/扫描-3%20秒-red?style=for-the-badge)]()
[![FP Rate](https://img.shields.io/badge/误报率-%E2%89%880%25-purple?style=for-the-badge)]()

[快速开始](#-快速开始) · [核心特性](#-核心特性) · [支持语言](#-支持的语言与框架)

</div>

---

## 市面上的工具在干什么？

ESLint 查语法。Semgrep 查漏洞。SonarQube 查复杂度。

**每个工具只看一个维度。** 你得装 3 个工具，看 3 份报告，自己拼全貌。

## 煋鉴做了什么不一样的事？

**3 个 AI 大脑同时扫描你的代码**，每个大脑专注一个维度，3 秒后给你一份完整报告——编码规范、安全漏洞、语义缺陷，一次扫描全出来。

不是规则匹配。**是真正的 AST 级语义分析 + LLM 深度推理。**

```
你的代码
  │
  ├─→ 🧠 Brain 1 ── 规则引擎：编码规范 / 格式校验 / 常见错误
  ├─→ 🛡️ Brain 2 ── 安全扫描：SQL注入 / XSS / 硬编码密钥 / SSRF
  └─→ 🤖 Brain 3 ── AI语义：上下文理解 / 逻辑缺陷 / 死代码
  │
  ▼
  一份报告。全部问题。按严重程度排序。附带修复方案。
```

## 数字说话

| 指标 | 煋鉴基础版 | 传统工具 |
|------|-----------|----------|
| 检测维度 | **3 个并行** | 1 个 |
| 规则数量 | **1,000+** | 100-500 |
| 分析深度 | **AST 语义级** | 正则/模式匹配 |
| 误报率 | **≈ 0%** | 30-60% |
| 扫描速度 | **3-10 秒** | 分钟级 |
| 增量扫描 | ✅ 只扫改动部分 | ❌ 全量重扫 |
| AI 分析建议 | ✅ 自动生成 | ❌ 仅提示 |

> **误报率 ≈ 0%** 不是营销话术。我们从 92% 的误报率一路优化到接近 0——通过三层防幻觉防御体系：规则白名单 → AST 上下文校验 → LLM 二次确认。每一条报出来的问题，都值得你修。

## 支持的语言与框架

**Python · JavaScript · TypeScript · Java · Go · PHP · C# · Swift · Kotlin · Dart**

**微信小程序（WXML/WXSS）· Vue · React Native · Flutter · Electron**

> 不是"能打开文件"那种支持。是针对每种语言的 AST 结构、生态惯例、常见陷阱做的**专项规则集**。

## 🚀 快速开始

### 1. 安装

```bash
pip install -r requirements.txt
```

### 2. CLI 一览

```bash
# 查看版本
./xinpect version

# 查看帮助
./xinpect help

# 查看所有可用规则
./xinpect rules
./xinpect rules --lang python         # 按语言筛选
./xinpect rules --level high          # 按严重级别筛选
./xinpect rules --keyword sql         # 关键词搜索

# 运行扫描
./xinpect scan --path /your/project/path
```

### 3. 运行扫描（开箱即用，无需配置）

```bash
./xinpect scan --path /your/project/path
```

Brain 1-3 直接可用。不需要 API Key，不需要注册，不需要付费。

## 📁 项目结构

```
xinpect/
├── brains/                     # 3 大脑引擎
│   ├── brain1_rule_engine.py       # 规则引擎（本地）
│   ├── brain2_security_engine.py   # 安全扫描（本地）
│   └── brain3_ai_engine.py         # AI 语义分析（本地）
├── core/                       # 核心调度
│   ├── runner.py                   # 并行扫描调度器
│   ├── ast_analyzer.py             # AST 分析引擎
│   ├── semantic_scanner.py         # 语义扫描器
│   └── ...
├── rules/                      # 1000+ 检测规则
│   ├── brain2_security/            # 安全规则集
│   ├── brain3_semantic/            # 语义规则集
│   ├── python/                     # Python 专属规则
│   ├── web/                        # Web 安全规则
│   └── common/                     # 通用规则
├── cli/                        # 命令行入口
├── scripts/                    # 工具脚本
├── tests/                      # 测试套件
└── qa_framework.py             # 主入口
```

## 🛡️ 三层防幻觉体系

这是煋鉴误报率接近 0% 的秘密：

```
第一层：规则白名单
  └─ 已知的框架特定写法（如 Django ORM、Vue 响应式）自动放行

第二层：AST 上下文校验
  └─ 不是看到 "eval" 就报警。分析完整 AST 上下文，判断是否真的危险

第三层：LLM 二次确认
  └─ 对第一、二层无法确定的问题，调用 LLM 做最终判断
  └─ 内置防幻觉 Prompt：要求 LLM 引用具体代码行作为证据
```

> 传统工具的误报让你开始忽略报告。煋鉴报出来的每一条，都是真问题。

## 💡 关于本版本

您正在使用煋鉴基础版（Lite），包含 B1~B3 三个本地核心引擎，可以帮您发现语法错误、低级安全漏洞和规范问题。

但还有以下维度未覆盖：

- 📊 性能问题（死循环、内存泄漏、低效查询…）
- 📦 依赖漏洞（第三方包 CVE 风险…）
- 🧩 代码质量（复杂度、重复率、可维护性…）
- 🏗️ 架构设计（分层合理性、耦合度、模块化…）
- 🔒 业务安全（越权、注入、数据泄露…）

完整 8 维度检测请前往 [煋鉴官网](https://xinpect.xingwangzhineng.com) 获取。

## 📜 License

本项目采用 AGPL-3.0 协议。详见 [LICENSE](./LICENSE)

---

<div align="center">

**煋旺智能**

*代码质量不是检查出来的，是设计出来的。煋鉴帮你看见盲区。*

</div>
