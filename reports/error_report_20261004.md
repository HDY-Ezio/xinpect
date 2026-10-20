# 每日错误报告
**日期**: 2026-10-04
**生成时间**: 2026-10-05 10:39:36

## 📊 总览
- **总错误数**: 17
  - 🔴 真实API错误: 11
  - 🟡 安全扫描器探测: 6
  - 系统服务错误 (journal): 0

> 💡 安全扫描器探测（6条）已从高频错误分析中排除，这些是自动化漏洞扫描行为，404为正确响应。
- **错误类型数**: 1
- **高频错误（>=3次）**: 1
- **未解决**: 11 / **已解决**: 0

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 17 | /api/session/properties,/wp-admin,/phpmyadmin,/auth/login,/api/scan/upload,/a... |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| /api/scan/estimate | POST | 5 | HTTP_ERROR |
| /phpmyadmin | GET | 3 | HTTP_ERROR |
| /wp-admin | GET | 3 | HTTP_ERROR |
| /api/scan/submit | POST | 2 | HTTP_ERROR |
| /api/scan/upload | POST | 1 | HTTP_ERROR |
| /api/session/properties | GET | 1 | HTTP_ERROR |
| /auth/login | GET | 1 | HTTP_ERROR |
| /health | GET | 1 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-10-04 00:00 | 1 |
| 2026-10-04 04:00 | 2 |
| 2026-10-04 10:00 | 2 |
| 2026-10-04 15:00 | 9 |
| 2026-10-04 16:00 | 2 |
| 2026-10-04 21:00 | 1 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（17次）
涉及端点/服务：/api/session/properties,/wp-admin,/phpmyadmin,/auth/login,/api/scan/upload,/api/scan/estimate,/api/scan/submit,/health

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 17 |

## ❌ 未解决错误详情（共11条）

### #2301 HTTP_ERROR - /health
- **时间**: 2026-10-04 21:33:04
- **方式**: GET
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.12

### #2298 HTTP_ERROR - /api/scan/estimate
- **时间**: 2026-10-04 15:58:32
- **方式**: POST
- **状态码**: 403
- **消息**: HTTP 403
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #2297 HTTP_ERROR - /api/scan/submit
- **时间**: 2026-10-04 15:56:14
- **方式**: POST
- **状态码**: 400
- **消息**: HTTP 400
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #2296 HTTP_ERROR - /api/scan/submit
- **时间**: 2026-10-04 15:54:40
- **方式**: POST
- **状态码**: 400
- **消息**: HTTP 400
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #2295 HTTP_ERROR - /api/scan/estimate
- **时间**: 2026-10-04 15:54:16
- **方式**: POST
- **状态码**: 403
- **消息**: HTTP 403
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #2294 HTTP_ERROR - /api/scan/estimate
- **时间**: 2026-10-04 15:52:04
- **方式**: POST
- **状态码**: 403
- **消息**: HTTP 403
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #2293 HTTP_ERROR - /api/scan/estimate
- **时间**: 2026-10-04 15:51:30
- **方式**: POST
- **状态码**: 403
- **消息**: HTTP 403
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #2291 HTTP_ERROR - /api/scan/upload
- **时间**: 2026-10-04 15:50:21
- **方式**: POST
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #2292 HTTP_ERROR - /api/scan/estimate
- **时间**: 2026-10-04 15:50:21
- **方式**: POST
- **状态码**: 403
- **消息**: HTTP 403
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #2290 HTTP_ERROR - /auth/login
- **时间**: 2026-10-04 15:14:39
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #2285 HTTP_ERROR - /api/session/properties
- **时间**: 2026-10-04 00:51:00
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: metabase-cve-2026-72898-detect/1.0 (benign detection probes only)

## 🛡️ 安全扫描器探测摘要（已排除，共6条）
这些是自动化漏洞扫描工具的探测行为，非真实API错误。

| 探测类型 | 次数 |
|----------|------|
| WordPress扫描探测 | 3 |
| 其他探测 | 3 |
