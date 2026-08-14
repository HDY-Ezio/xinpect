---
name: xinpect-code-review-free
slug: xinpect-code-review-free
displayName: 煋鉴代码质检
description: AI驱动的代码质量检测工具，免费版支持Python/JavaScript/TypeScript/微信小程序等多语言，覆盖语法格式、安全依赖、性能优化、可观测性、代码质量、架构规范、专项检测7大引擎。当用户需要代码审查、代码质量检测、代码扫描、代码规范检查、安全审计、性能优化建议时触发。
version: 5.9.0
category: 代码质量
author: 煋旺智能
trigger: 当用户需要代码审查、代码质量检测、代码扫描、代码规范检查、安全审计、性能优化建议，或提到"代码质检"、"代码review"、"代码检查"、"代码分析"、"scan code"、"code review"、"quality check"时触发
---

# 煋鉴代码质检 · 免费版 v5.9.0

> AI 驱动的代码质量检测工具，7 大检测引擎，多语言支持

**开发者**：煋旺智能  
**官方主页**：xinpect.xingwangzhineng.com  
**版本**：v5.9.0 免费版

## 技能介绍

煋鉴代码质检是一款 AI 驱动的代码质量检测工具，免费版提供 **7 大检测引擎**，覆盖语法格式、安全依赖、性能优化、可观测性、代码质量、架构规范、小程序专项等维度。帮助开发者在提交代码前快速发现潜在问题，提升代码质量。

**免费版** 为入门级检测，覆盖最常见的代码质量问题。更深度的检测能力（AI语义分析、业务安全、测试质量、数据一致性等）在专业版中提供。

## 支持语言

- **Python** — 完整支持
- **JavaScript / TypeScript** — 完整支持
- **微信小程序**（.wxml/.wxss/.js/.json）— 基础规范检测
- **SQL / Java / Go / Ruby / PHP** — 基础安全检测
- **配置文件**（.yaml/.json/.env/.properties）— 安全审计
- **Dockerfile** — 容器安全基础检测

## 9 大检测引擎说明

| 引擎 | 名称 | 免费版 | 说明 |
|------|------|--------|------|
| B1 | 语法格式 | ✅ 完整 | Python语法检查、缩进规范、格式规范 |
| B2 | 安全与依赖 | ✅ 入门 | 硬编码密钥、SQL注入、命令注入、裸HTTP请求、基础依赖漏洞 |
| B3 | AI语义分析 | ❌ 付费 | 基于LLM的深度语义理解与逻辑缺陷检测 |
| B4 | 性能与可靠性 | ✅ 基础 | N+1查询、循环内IO、sleep阻塞、字符串拼接 |
| B5 | 可观测性 | ✅ 基础 | 日志泄露敏感信息、日志级别滥用、debug未关闭 |
| B6 | 代码质量 | ✅ 基础 | 长函数、深层嵌套、TODO/FIXME、备份文件 |
| B7 | 架构与合规 | ✅ 基础 | 路径遍历、魔数、硬编码配置、循环依赖 |
| B8 | 业务安全 | ❌ 付费 | 支付安全、越权检测、业务逻辑漏洞 |
| B9 | 专项检测 | ✅ 基础 | 小程序基础规范（WXML/WXSS/页面完整性） |

## 使用方式

### 方式一：传入代码内容

```python
from scripts.scan import scan_code

result = scan_code({
    "main.py": """
import os
password = "123456"

def hello():
    print("hello world")
""",
    "utils.js": "// TODO: implement this\nfunction foo() { console.log('debug'); }",
})
```

### 方式二：扫描单个文件

```python
from scripts.scan import scan_file

result = scan_file("/path/to/your/code.py")
```

### 方式三：扫描整个目录

```python
from scripts.scan import scan_directory

result = scan_directory("/path/to/your/project")
```

## 返回格式说明

```json
{
  "total_score": 85,
  "status": "pass",
  "total_elapsed": 2.5,
  "brain_count": 7,
  "total_issues": 12,
  "version": "5.9.0",
  "edition": "free",
  "brains": {
    "1": {
      "id": "1",
      "name": "语法格式",
      "score": 100,
      "status": "pass",
      "issues": [],
      "summary": "语法格式检测通过，未发现问题",
      "elapsed": 0.1
    }
  },
  "all_issues": [
    {
      "check_id": "SEC-AUTH-001",
      "name": "硬编码密码",
      "severity": "blocker",
      "file": "main.py",
      "line": 3,
      "message": "检测到硬编码密码，代码中不应硬编码敏感凭据",
      "suggestion": "使用环境变量或密钥管理服务存储敏感信息"
    }
  ]
}
```

### 字段说明

- **total_score**: 总评分（0-100），各大脑得分的平均值
- **status**: `pass`（≥60分）或 `fail`（<60分）
- **brain_count**: 实际执行的大脑数量
- **total_issues**: 发现的问题总数
- **brains**: 各引擎详细结果
  - **score**: 该引擎得分（0-100）
  - **status**: `pass` / `fail` / `error` / `timeout`
  - **issues**: 问题列表
  - **summary**: 检测摘要
  - **elapsed**: 耗时（秒）
- **all_issues**: 所有问题汇总

### 问题严重级别

| 级别 | 扣分 | 说明 |
|------|------|------|
| blocker / critical | 10分/个 | 必须修复的严重问题 |
| high | 5分/个 | 高危问题，建议尽快修复 |
| medium | 3分/个，上限30分 | 中等问题，建议修复 |
| low / info | 0.5分/个，上限20分 | 低风险，优化建议 |

## 评分规则

1. 每个引擎独立评分，初始 100 分
2. 按问题严重级别扣分
3. 总分为各引擎得分的平均值（异常/跳过的引擎不计入）
4. 总分 ≥ 60 为通过，< 60 为未通过

## 版本信息

- **版本**: v5.9.0（免费版）
- **开发者**: 煋旺智能
- **官方主页**: xinpect.xingwangzhineng.com

## 专业版说明

免费版为入门级检测，适合个人开发者日常代码自查。专业版提供更完整的检测能力：

| 能力 | 免费版 | 专业版 |
|------|--------|--------|
| 检测引擎 | 7 个 | 9 个 |
| 规则数量 | 约 300 条 | 1050+ 条 |
| AI 语义分析 | ❌ | ✅ |
| 业务安全检测 | ❌ | ✅ |
| 并发安全检测 | 基础 | 完整 |
| 测试质量评估 | ❌ | ✅ |
| 数据一致性检测 | ❌ | ✅ |
| 可观测性检测 | 基础 | 完整 20 条 |

了解更多请访问官方主页：xinpect.xingwangzhineng.com
