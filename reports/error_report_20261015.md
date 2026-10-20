# 每日错误报告
**日期**: 2026-10-15
**生成时间**: 2026-10-16 10:41:35

## 📊 总览
- **总错误数**: 156
  - 🔴 真实API错误: 126
  - 🟡 安全扫描器探测: 30
  - 系统服务错误 (journal): 0

> 💡 安全扫描器探测（30条）已从高频错误分析中排除，这些是自动化漏洞扫描行为，404为正确响应。
- **错误类型数**: 4
- **高频错误（>=3次）**: 3
- **未解决**: 126 / **已解决**: 0

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 145 | /upload,/api/scan/status,/api/scan/submit,/api/queue/submit,/api/login,/queue... |
| OperationalError | 6 | /api/ci/scan |
| UndefinedError | 3 | /report/ci_scan_1792059007996_1a5417616571 |
| TemplateNotFound | 2 | /queue/status |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| /api/ci/scan | POST | 24 | HTTP_ERROR,OperationalError |
| /api/dashboard/summary | GET | 18 | HTTP_ERROR |
| /api/scan/config | GET | 18 | HTTP_ERROR |
| /api/repos/list | GET | 13 | HTTP_ERROR |
| /api/v1/config | GET | 10 | HTTP_ERROR |
| /api/ci/config | GET | 8 | HTTP_ERROR |
| /report/ci_scan_1792059007996_1a5417616571 | GET | 6 | UndefinedError,HTTP_ERROR |
| /upload | GET | 6 | HTTP_ERROR |
| /phpmyadmin | GET | 4 | HTTP_ERROR |
| /queue/status | GET | 4 | TemplateNotFound,HTTP_ERROR |
| /wp-admin | GET | 4 | HTTP_ERROR |
| /api/account/credits | GET | 3 | HTTP_ERROR |
| /api/credits | GET | 3 | HTTP_ERROR |
| /api/scan/status | GET | 3 | HTTP_ERROR |
| /api/v1/account/balance | GET | 3 | HTTP_ERROR |
| /api/v1/credit/balance | GET | 3 | HTTP_ERROR |
| /api/v1/credits | GET | 3 | HTTP_ERROR |
| /api/config | GET | 2 | HTTP_ERROR |
| /api/feedback | POST | 2 | HTTP_ERROR |
| /api/queue/submit | POST | 2 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-10-15 00:00 | 17 |
| 2026-10-15 01:00 | 1 |
| 2026-10-15 03:00 | 37 |
| 2026-10-15 04:00 | 2 |
| 2026-10-15 07:00 | 30 |
| 2026-10-15 09:00 | 18 |
| 2026-10-15 10:00 | 13 |
| 2026-10-15 12:00 | 21 |
| 2026-10-15 16:00 | 2 |
| 2026-10-15 20:00 | 8 |
| 2026-10-15 21:00 | 5 |
| 2026-10-15 22:00 | 2 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（145次）
涉及端点/服务：/upload,/api/scan/status,/api/scan/submit,/api/queue/submit,/api/login,/queue/status,/api/scan/config,/scan,/api/dashboard/summary,/api/repos/list,/api/ci/scan,/api/v1/config,/api/config,/wp-admin,/phpmyadmin,/ci/api/webhooks,/api/ci/config,/api/results/ci_scan_1792057623103_1a5417616571,/api/results/ci_scan_1792058061685_1a5417616571,/api/ci/scan/ci_scan_1792058990595_1a5417616571,/api/v1/credits,/api/credits,/api/v1/credit/balance,/api/account/credits,/api/v1/account/balance,/api/v1/account/status,/api/health,/api/feedback,/report/ci_scan_1792059007996_1a5417616571,/api/user/onboarding/status,/api/user/api-usage/quota,/team

### OperationalError（6次）
涉及端点/服务：/api/ci/scan

### UndefinedError（3次）
涉及端点/服务：/report/ci_scan_1792059007996_1a5417616571

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 156 |

## ❌ 未解决错误详情（共126条）

### #3558 HTTP_ERROR - /api/feedback
- **时间**: 2026-10-15 21:34:51
- **方式**: POST
- **状态码**: 403
- **消息**: HTTP 403
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #3559 HTTP_ERROR - /api/user/onboarding/status
- **时间**: 2026-10-15 21:34:51
- **方式**: GET
- **状态码**: 401
- **消息**: HTTP 401
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #3560 HTTP_ERROR - /api/user/api-usage/quota
- **时间**: 2026-10-15 21:34:51
- **方式**: GET
- **状态码**: 401
- **消息**: HTTP 401
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #3551 HTTP_ERROR - /api/feedback
- **时间**: 2026-10-15 20:56:11
- **方式**: POST
- **状态码**: 403
- **消息**: HTTP 403
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #3550 HTTP_ERROR - /api/health
- **时间**: 2026-10-15 20:00:40
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #3540 HTTP_ERROR - /api/dashboard/summary
- **时间**: 2026-10-15 12:13:28
- **方式**: GET
- **状态码**: 401
- **消息**: HTTP 401
- **IP**: 127.0.0.1
- **来源**: python-requests/2.34.2

### #3541 HTTP_ERROR - /api/dashboard/summary
- **时间**: 2026-10-15 12:13:28
- **方式**: GET
- **状态码**: 401
- **消息**: HTTP 401
- **IP**: 127.0.0.1
- **来源**: python-requests/2.34.2

### #3542 HTTP_ERROR - /api/v1/credits
- **时间**: 2026-10-15 12:13:28
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: python-requests/2.34.2

### #3543 HTTP_ERROR - /api/credits
- **时间**: 2026-10-15 12:13:28
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: python-requests/2.34.2

### #3544 HTTP_ERROR - /api/v1/credit/balance
- **时间**: 2026-10-15 12:13:28
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: python-requests/2.34.2

### #3545 HTTP_ERROR - /api/account/credits
- **时间**: 2026-10-15 12:13:28
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: python-requests/2.34.2

### #3546 HTTP_ERROR - /api/v1/account/balance
- **时间**: 2026-10-15 12:13:28
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: python-requests/2.34.2

### #3547 HTTP_ERROR - /api/v1/account/status
- **时间**: 2026-10-15 12:13:28
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: python-requests/2.34.2

### #3532 HTTP_ERROR - /api/dashboard/summary
- **时间**: 2026-10-15 12:08:45
- **方式**: GET
- **状态码**: 401
- **消息**: HTTP 401
- **IP**: 127.0.0.1
- **来源**: python-requests/2.34.2

### #3533 HTTP_ERROR - /api/dashboard/summary
- **时间**: 2026-10-15 12:08:45
- **方式**: GET
- **状态码**: 401
- **消息**: HTTP 401
- **IP**: 127.0.0.1
- **来源**: python-requests/2.34.2

### #3534 HTTP_ERROR - /api/v1/credits
- **时间**: 2026-10-15 12:08:45
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: python-requests/2.34.2

### #3535 HTTP_ERROR - /api/credits
- **时间**: 2026-10-15 12:08:45
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: python-requests/2.34.2

### #3536 HTTP_ERROR - /api/v1/credit/balance
- **时间**: 2026-10-15 12:08:45
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: python-requests/2.34.2

### #3537 HTTP_ERROR - /api/account/credits
- **时间**: 2026-10-15 12:08:45
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: python-requests/2.34.2

### #3538 HTTP_ERROR - /api/v1/account/balance
- **时间**: 2026-10-15 12:08:45
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: python-requests/2.34.2

...还有 106 条未解决错误

## 🛡️ 安全扫描器探测摘要（已排除，共30条）
这些是自动化漏洞扫描工具的探测行为，非真实API错误。

| 探测类型 | 次数 |
|----------|------|
| 其他探测 | 26 |
| WordPress扫描探测 | 4 |
