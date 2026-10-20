# 每日错误报告
**日期**: 2026-10-16
**生成时间**: 2026-10-17 00:00:40

## 📊 总览
- **总错误数**: 71
  - 🔴 真实API错误: 33
  - 🟡 安全扫描器探测: 38
  - 系统服务错误 (journal): 0

> 💡 安全扫描器探测（38条）已从高频错误分析中排除，这些是自动化漏洞扫描行为，404为正确响应。
- **错误类型数**: 3
- **高频错误（>=3次）**: 3
- **未解决**: 33 / **已解决**: 0

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 63 | /api/v1/scan,/dashboard/credits,/report.html,/home.html,/upload,/report,/scan... |
| UndefinedError | 5 | /dashboard/credits |
| MethodNotAllowed | 3 | /scan |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| /api/v1/scan | POST | 21 | HTTP_ERROR |
| /dashboard/credits | GET | 10 | UndefinedError,HTTP_ERROR |
| /scan | GET | 6 | MethodNotAllowed,HTTP_ERROR |
| /upload | GET | 4 | HTTP_ERROR |
| /scan | POST | 3 | HTTP_ERROR |
| /api/health | GET | 2 | HTTP_ERROR |
| /api/rules | GET | 2 | HTTP_ERROR |
| /scan/status/76f647500581bf221e872c39a95e6a2b | GET | 2 | HTTP_ERROR |
| /about | GET | 1 | HTTP_ERROR |
| /api/languages | GET | 1 | HTTP_ERROR |
| /api/scan/detail/76f647500581bf221e872c39a95e6a2b | GET | 1 | HTTP_ERROR |
| /api/scan/result/76f647500581bf221e872c39a95e6a2b | GET | 1 | HTTP_ERROR |
| /api/scan/status/ | GET | 1 | HTTP_ERROR |
| /api/scanner/health | GET | 1 | HTTP_ERROR |
| /api/stats | GET | 1 | HTTP_ERROR |
| /api/v1/health | GET | 1 | HTTP_ERROR |
| /api/v1/scan/result/76f647500581bf221e872c39a95e6a2b | GET | 1 | HTTP_ERROR |
| /home.html | GET | 1 | HTTP_ERROR |
| /phpmyadmin | GET | 1 | HTTP_ERROR |
| /report | GET | 1 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-10-16 08:00 | 19 |
| 2026-10-16 09:00 | 12 |
| 2026-10-16 10:00 | 1 |
| 2026-10-16 11:00 | 1 |
| 2026-10-16 12:00 | 4 |
| 2026-10-16 13:00 | 1 |
| 2026-10-16 14:00 | 4 |
| 2026-10-16 15:00 | 27 |
| 2026-10-16 16:00 | 2 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（63次）
涉及端点/服务：/api/v1/scan,/dashboard/credits,/report.html,/home.html,/upload,/report,/scan,/result,/settings,/api/health,/scanner,/scanner/health,/api/scanner/health,/v1/health,/api/v1/health,/about,/api/languages,/api/rules,/api/stats,/scan/status/76f647500581bf221e872c39a95e6a2b,/scan/result/76f647500581bf221e872c39a95e6a2b,/scan/76f647500581bf221e872c39a95e6a2b,/api/scan/detail/76f647500581bf221e872c39a95e6a2b,/api/scan/result/76f647500581bf221e872c39a95e6a2b,/api/v1/scan/result/76f647500581bf221e872c39a95e6a2b,/api/scan/status/,/wp-admin,/phpmyadmin

### UndefinedError（5次）
涉及端点/服务：/dashboard/credits

### MethodNotAllowed（3次）
涉及端点/服务：/scan

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 71 |

## ❌ 未解决错误详情（共33条）

### #3795 HTTP_ERROR - /api/scan/status/
- **时间**: 2026-10-16 15:51:37
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/7.81.0

### #3794 HTTP_ERROR - /api/rules
- **时间**: 2026-10-16 15:51:12
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: python-requests/2.34.2

### #3792 HTTP_ERROR - /api/v1/scan/result/76f647500581bf221e872c39a95e6a2b
- **时间**: 2026-10-16 15:49:06
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/7.81.0

### #3790 HTTP_ERROR - /api/scan/detail/76f647500581bf221e872c39a95e6a2b
- **时间**: 2026-10-16 15:49:05
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/7.81.0

### #3791 HTTP_ERROR - /api/scan/result/76f647500581bf221e872c39a95e6a2b
- **时间**: 2026-10-16 15:49:05
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/7.81.0

### #3781 HTTP_ERROR - /api/languages
- **时间**: 2026-10-16 15:13:53
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/7.81.0

### #3782 HTTP_ERROR - /api/rules
- **时间**: 2026-10-16 15:13:53
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/7.81.0

### #3783 HTTP_ERROR - /api/stats
- **时间**: 2026-10-16 15:13:53
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/7.81.0

### #3779 HTTP_ERROR - /api/health
- **时间**: 2026-10-16 15:13:52
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/7.81.0

### #3774 HTTP_ERROR - /api/scanner/health
- **时间**: 2026-10-16 15:13:21
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/7.81.0

### #3776 HTTP_ERROR - /api/v1/health
- **时间**: 2026-10-16 15:13:21
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/7.81.0

### #3769 HTTP_ERROR - /api/health
- **时间**: 2026-10-16 15:13:12
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/7.81.0

### #3740 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-10-16 09:59:23
- **方式**: POST
- **状态码**: 400
- **消息**: HTTP 400
- **IP**: 127.0.0.1
- **来源**: curl/8.7.1

### #3739 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-10-16 09:59:18
- **方式**: POST
- **状态码**: 400
- **消息**: HTTP 400
- **IP**: 127.0.0.1
- **来源**: curl/8.7.1

### #3733 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-10-16 09:29:59
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.10

### #3732 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-10-16 09:29:52
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.10

### #3730 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-10-16 09:29:45
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.10

### #3727 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-10-16 09:29:09
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.10

### #3726 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-10-16 09:29:01
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.10

### #3725 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-10-16 09:28:56
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.10

...还有 13 条未解决错误

## 🛡️ 安全扫描器探测摘要（已排除，共38条）
这些是自动化漏洞扫描工具的探测行为，非真实API错误。

| 探测类型 | 次数 |
|----------|------|
| 其他探测 | 37 |
| WordPress扫描探测 | 1 |
