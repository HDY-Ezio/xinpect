# 每日错误报告
**日期**: 2026-09-20
**生成时间**: 2026-09-21 10:15:14

## 📊 总览
- **总错误数**: 4
  - 🔴 真实API错误: 4
  - 🟡 安全扫描器探测: 0
  - 系统服务错误 (journal): 0
- **错误类型数**: 1
- **高频错误（>=3次）**: 1
- **未解决**: 4 / **已解决**: 0

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 4 | /nonexistent-page-test,/static/xinpect_showcase.png,/static/og-default.png |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| /static/og-default.png | GET | 2 | HTTP_ERROR |
| /nonexistent-page-test | GET | 1 | HTTP_ERROR |
| /static/xinpect_showcase.png | GET | 1 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-09-20 10:00 | 1 |
| 2026-09-20 14:00 | 1 |
| 2026-09-20 19:00 | 2 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（4次）
涉及端点/服务：/nonexistent-page-test,/static/xinpect_showcase.png,/static/og-default.png

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 4 |

## ❌ 未解决错误详情（共4条）

### #1923 HTTP_ERROR - /static/og-default.png
- **时间**: 2026-09-20 19:29:28
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0

### #1922 HTTP_ERROR - /static/og-default.png
- **时间**: 2026-09-20 19:29:27
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.51

### #1921 HTTP_ERROR - /static/xinpect_showcase.png
- **时间**: 2026-09-20 14:31:01
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Coze/1.1.43 Chrome/

### #1920 HTTP_ERROR - /nonexistent-page-test
- **时间**: 2026-09-20 10:27:59
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0
