# 每日错误报告
**日期**: 2026-09-15
**生成时间**: 2026-09-16 10:18:09

## 📊 总览
- **总错误数**: 41
  - 🔴 真实API错误: 0
  - 🟡 安全扫描器探测: 41
  - 系统服务错误 (journal): 0

> 💡 安全扫描器探测（41条）已从高频错误分析中排除，这些是自动化漏洞扫描行为，404为正确响应。
- **错误类型数**: 1
- **高频错误（>=3次）**: 1
- **未解决**: 0 / **已解决**: 0

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 41 | /blog/feed/,/blog/,/blog/wp/v2/posts/999999,/blog/wp/v2/pages,/blog/wp/v2/med... |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| /blog/ | POST | 21 | HTTP_ERROR |
| /blog/ | GET | 10 | HTTP_ERROR |
| /blog/feed/ | GET | 1 | HTTP_ERROR |
| /blog/wp/v2/categories | GET | 1 | HTTP_ERROR |
| /blog/wp/v2/media | GET | 1 | HTTP_ERROR |
| /blog/wp/v2/pages | GET | 1 | HTTP_ERROR |
| /blog/wp/v2/posts/99999 | GET | 1 | HTTP_ERROR |
| /blog/wp/v2/posts/999998 | GET | 1 | HTTP_ERROR |
| /blog/wp/v2/posts/999999 | GET | 1 | HTTP_ERROR |
| /blog/wp/v2/posts/9999999 | GET | 1 | HTTP_ERROR |
| /blog/wp/v2/tags | GET | 1 | HTTP_ERROR |
| /blog/wp/v2/users | GET | 1 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-09-15 15:00 | 41 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（41次）
涉及端点/服务：/blog/feed/,/blog/,/blog/wp/v2/posts/999999,/blog/wp/v2/pages,/blog/wp/v2/media,/blog/wp/v2/categories,/blog/wp/v2/tags,/blog/wp/v2/posts/999998,/blog/wp/v2/posts/99999,/blog/wp/v2/posts/9999999,/blog/wp/v2/users

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 41 |

## ❌ 未解决错误详情（共0条）
无未解决错误 ✅

## 🛡️ 安全扫描器探测摘要（已排除，共41条）
这些是自动化漏洞扫描工具的探测行为，非真实API错误。

| 探测类型 | 次数 |
|----------|------|
| 其他探测 | 32 |
| WordPress扫描探测 | 9 |
