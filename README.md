# 煋鉴代码质检 · 免费版 v5.9.0

> 煋旺智能出品 · AI驱动的代码质量检测工具

[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
[![Version](https://img.shields.io/badge/version-v5.9.0-orange.svg)](https://xinpect.xingwangzhineng.com)

## 简介

煋鉴代码质检是一款 AI 驱动的代码质量检测工具，免费版提供 **7 大检测引擎**，覆盖语法格式、安全依赖、性能优化、可观测性、代码质量、架构规范、小程序专项等维度。帮助开发者在提交代码前快速发现潜在问题，提升代码质量。

**官方主页**：[xinpect.xingwangzhineng.com](https://xinpect.xingwangzhineng.com)

## 特性

- 🚀 **7 大检测引擎**：语法、安全、性能、可观测性、代码质量、架构、专项检测
- 🌐 **多语言支持**：Python / JavaScript / TypeScript / 微信小程序 / SQL / Java / Go 等
- ⚡ **并行扫描**：多进程并行架构，百万级代码秒级出结果
- 🛡️ **零依赖运行**：纯规则引擎，无需联网、无需 API Key
- 📊 **结构化输出**：标准化 JSON 结果，方便集成到 CI/CD

## 快速开始

### 安装

```bash
# 克隆仓库
git clone https://github.com/HDY-Ezio/xinpect.git
cd xinpect
```

### 使用

```python
from scripts.scan import scan_code, scan_file, scan_directory

# 扫描代码片段
result = scan_code({
    "main.py": open("main.py").read(),
    "utils.js": open("utils.js").read(),
})

# 扫描整个目录
result = scan_directory("./my_project")

# 查看结果
print(f"总分: {result['total_score']}")
print(f"问题数: {result['total_issues']}")
```

## 7 大检测引擎

| 编号 | 引擎名称 | 检测重点 |
|------|----------|----------|
| B1 | 语法格式 | Python语法错误、缩进混合、格式规范 |
| B2 | 安全与依赖 | 硬编码密钥、SQL/命令注入、裸HTTP请求、依赖安全 |
| B4 | 性能与可靠性 | N+1查询、循环内IO、sleep阻塞、长函数性能 |
| B5 | 可观测性 | 日志泄露、日志级别滥用、调试日志未关闭 |
| B6 | 代码质量 | 长函数、深层嵌套、TODO/FIXME、备份文件 |
| B7 | 架构与合规 | 路径遍历、魔数、硬编码配置、循环依赖 |
| B9 | 专项检测 | 小程序基础规范（WXML/WXSS/页面完整性） |

## 免费版 vs 专业版

| 功能 | 免费版 | 专业版 |
|------|--------|--------|
| 检测引擎数量 | 7个 | 9个 |
| B1 语法格式 | ✅ 完整 | ✅ 完整 |
| B2 安全与依赖 | 入门级 | 完整（含支付签名/越权等） |
| B3 AI语义分析 | ❌ | ✅ LLM深度分析 |
| B4 性能与可靠性 | 基础 | 完整（含并发安全等） |
| B5 可观测性 | 基础（4条） | 完整（20条） |
| B6 代码质量 | 基础 | 完整（含测试质量10条） |
| B7 架构与合规 | 基础 | 完整（含数据一致性8条） |
| B8 业务安全 | ❌ | ✅ 完整业务安全检测 |
| B9 专项检测 | 基础（小程序） | 完整（组件契约等） |
| 总规则数 | 约300条 | 1050+条 |
| AI 增强分析 | ❌ | ✅ 官网会员版 |

了解更多请访问：[xinpect.xingwangzhineng.com](https://xinpect.xingwangzhineng.com)

## 支持语言

- **Python** — 完整支持
- **JavaScript / TypeScript** — 完整支持
- **微信小程序**（.wxml/.wxss/.js/.json）— 基础规范检测
- **SQL / Java / Go / Ruby / PHP** — 基础安全检测
- **配置文件**（.yaml/.json/.env/.properties）— 安全审计
- **Dockerfile** — 容器安全基础检测

## 严重级别说明

| 级别 | 含义 | 建议处理时间 |
|------|------|-------------|
| blocker | 阻断级，必须修复 | 立即修复 |
| critical | 严重问题 | 本迭代修复 |
| high | 高危问题 | 本迭代修复 |
| medium | 中等问题 | 近期修复 |
| low | 低风险优化 | 择机优化 |
| info | 信息提示 | 了解即可 |

## 更新日志

### v5.9.0
- 新增 B5 可观测性引擎（20条规则，免费版开放4条基础规则）
- B4 性能引擎新增并发安全检测（免费版基础版）
- B6 代码质量新增测试质量检测（专业版完整）
- B7 架构引擎新增数据一致性检测（专业版完整）
- 总规则数突破 1050+ 条
- 优化并行调度架构，扫描速度提升 30%

### v5.5.1
- 新增页面入口可达性检测
- B9 专项引擎扩展
- 总规则 587 条

## 关于

煋鉴（Xinpect）由 **煋旺智能** 出品，专注于代码质量与开发者效率提升。

- 官方网站：[xinpect.xingwangzhineng.com](https://xinpect.xingwangzhineng.com)
- 问题反馈：提交 Issue
- 商务合作：contact@xingwang.ai

---

**煋旺智能** · 让代码更有质量
