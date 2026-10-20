# 每日错误报告
**日期**: 2026-09-08
**生成时间**: 2026-09-09 10:14:19

## 📊 总览
- **总错误数**: 14
  - 🔴 真实API错误: 14
  - 🟡 安全扫描器探测: 0
  - 系统服务错误 (journal): 0
- **错误类型数**: 1
- **高频错误（>=3次）**: 1
- **未解决**: 14 / **已解决**: 0

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 14 | /favicon.png,/nonexistent-page-test,/api/pay/create,/appsettings.json |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| /api/pay/create | POST | 9 | HTTP_ERROR |
| /favicon.png | GET | 3 | HTTP_ERROR |
| /appsettings.json | GET | 1 | HTTP_ERROR |
| /nonexistent-page-test | GET | 1 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-09-08 05:00 | 4 |
| 2026-09-08 11:00 | 9 |
| 2026-09-08 18:00 | 1 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（14次）
涉及端点/服务：/favicon.png,/nonexistent-page-test,/api/pay/create,/appsettings.json

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 14 |

## ❌ 未解决错误详情（共14条）

### #829 HTTP_ERROR - /appsettings.json
- **时间**: 2026-09-08 18:01:14
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Sa

### #828 HTTP_ERROR - /api/pay/create
- **时间**: 2026-09-08 11:09:16
- **方式**: POST
- **状态码**: 400
- **消息**: HTTP 400
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Sa

### #827 HTTP_ERROR - /api/pay/create
- **时间**: 2026-09-08 11:09:13
- **方式**: POST
- **状态码**: 400
- **消息**: HTTP 400
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Sa

### #826 HTTP_ERROR - /api/pay/create
- **时间**: 2026-09-08 11:09:11
- **方式**: POST
- **状态码**: 400
- **消息**: HTTP 400
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Sa

### #825 HTTP_ERROR - /api/pay/create
- **时间**: 2026-09-08 11:09:09
- **方式**: POST
- **状态码**: 400
- **消息**: HTTP 400
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Sa

### #824 HTTP_ERROR - /api/pay/create
- **时间**: 2026-09-08 11:07:15
- **方式**: POST
- **状态码**: 400
- **消息**: HTTP 400
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Sa

### #823 HTTP_ERROR - /api/pay/create
- **时间**: 2026-09-08 11:05:21
- **方式**: POST
- **状态码**: 400
- **消息**: HTTP 400
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Sa

### #822 HTTP_ERROR - /api/pay/create
- **时间**: 2026-09-08 11:05:13
- **方式**: POST
- **状态码**: 400
- **消息**: HTTP 400
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Sa

### #821 HTTP_ERROR - /api/pay/create
- **时间**: 2026-09-08 11:04:58
- **方式**: POST
- **状态码**: 400
- **消息**: HTTP 400
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Sa

### #820 HTTP_ERROR - /api/pay/create
- **时间**: 2026-09-08 11:04:50
- **方式**: POST
- **状态码**: 400
- **消息**: HTTP 400
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Sa

### #819 HTTP_ERROR - /favicon.png
- **时间**: 2026-09-08 05:39:57
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: okhttp/5.3.0

### #818 HTTP_ERROR - /nonexistent-page-test
- **时间**: 2026-09-08 05:33:00
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.3

### #817 HTTP_ERROR - /favicon.png
- **时间**: 2026-09-08 05:27:55
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: okhttp/5.3.0

### #816 HTTP_ERROR - /favicon.png
- **时间**: 2026-09-08 05:15:55
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: okhttp/5.3.0
