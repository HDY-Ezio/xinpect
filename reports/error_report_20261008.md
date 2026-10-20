# 每日错误报告
**日期**: 2026-10-08
**生成时间**: 2026-10-09 10:40:44

## 📊 总览
- **总错误数**: 24
  - 🔴 真实API错误: 16
  - 🟡 安全扫描器探测: 8
  - 系统服务错误 (journal): 0

> 💡 安全扫描器探测（8条）已从高频错误分析中排除，这些是自动化漏洞扫描行为，404为正确响应。
- **错误类型数**: 2
- **高频错误（>=3次）**: 1
- **未解决**: 16 / **已解决**: 0

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 23 | /wp-admin,/phpmyadmin,/api/auth/register,/api/auth/login,/scan/async,/api/reg... |
| MethodNotAllowed | 1 | /scan |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| /phpmyadmin | GET | 4 | HTTP_ERROR |
| /wp-admin | GET | 4 | HTTP_ERROR |
| /favicon.png | GET | 2 | HTTP_ERROR |
| /scan | GET | 2 | MethodNotAllowed,HTTP_ERROR |
| /api | GET | 1 | HTTP_ERROR |
| /api/ | GET | 1 | HTTP_ERROR |
| /api/auth/login | POST | 1 | HTTP_ERROR |
| /api/auth/register | POST | 1 | HTTP_ERROR |
| /api/health | GET | 1 | HTTP_ERROR |
| /api/register | GET | 1 | HTTP_ERROR |
| /api/v1/scan | POST | 1 | HTTP_ERROR |
| /auth/register | GET | 1 | HTTP_ERROR |
| /docs | GET | 1 | HTTP_ERROR |
| /openapi.json | GET | 1 | HTTP_ERROR |
| /scan | POST | 1 | HTTP_ERROR |
| /scan/async | POST | 1 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-10-08 04:00 | 2 |
| 2026-10-08 05:00 | 5 |
| 2026-10-08 10:00 | 2 |
| 2026-10-08 15:00 | 9 |
| 2026-10-08 16:00 | 2 |
| 2026-10-08 17:00 | 1 |
| 2026-10-08 18:00 | 1 |
| 2026-10-08 22:00 | 2 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（23次）
涉及端点/服务：/wp-admin,/phpmyadmin,/api/auth/register,/api/auth/login,/scan/async,/api/register,/auth/register,/api,/api/,/api/health,/scan,/docs,/openapi.json,/api/v1/scan,/favicon.png

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 24 |

## ❌ 未解决错误详情（共16条）

### #2945 HTTP_ERROR - /favicon.png
- **时间**: 2026-10-08 18:09:14
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: okhttp/5.3.0

### #2944 HTTP_ERROR - /favicon.png
- **时间**: 2026-10-08 17:35:36
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: okhttp/5.3.0

### #2941 HTTP_ERROR - /scan
- **时间**: 2026-10-08 15:14:07
- **方式**: POST
- **状态码**: 403
- **消息**: HTTP 403
- **IP**: 127.0.0.1
- **来源**: curl/8.21.0

### #2940 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-10-08 15:14:06
- **方式**: POST
- **状态码**: 401
- **消息**: HTTP 401
- **IP**: 127.0.0.1
- **来源**: curl/8.21.0

### #2938 HTTP_ERROR - /docs
- **时间**: 2026-10-08 15:13:45
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/8.21.0

### #2939 HTTP_ERROR - /openapi.json
- **时间**: 2026-10-08 15:13:45
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/8.21.0

### #2936 MethodNotAllowed - /scan
- **时间**: 2026-10-08 15:13:44
- **方式**: GET
- **状态码**: 405
- **消息**: 405 Method Not Allowed: The method is not allowed for the requested URL.
- **堆栈摘要**:
```
    result = self.url_adapter.match(return_rule=True)  # type: ignore
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/ubuntu/.local/lib/python3.12/site-packages/werkzeug/routing/map.py", line 624, in match
    raise MethodNotAllowed(valid_methods=list(e.have_match_for)) from None
werkzeug.exceptions.MethodNotAllowed: 405 Method Not Allowed: The method is not allowed for the requested URL.
```
- **IP**: 127.0.0.1
- **来源**: curl/8.21.0

### #2937 HTTP_ERROR - /scan
- **时间**: 2026-10-08 15:13:44
- **方式**: GET
- **状态码**: 405
- **消息**: HTTP 405
- **IP**: 127.0.0.1
- **来源**: curl/8.21.0

### #2935 HTTP_ERROR - /api/health
- **时间**: 2026-10-08 15:13:41
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/8.21.0

### #2933 HTTP_ERROR - /api
- **时间**: 2026-10-08 15:13:40
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/8.21.0

### #2934 HTTP_ERROR - /api/
- **时间**: 2026-10-08 15:13:40
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/8.21.0

### #2930 HTTP_ERROR - /auth/register
- **时间**: 2026-10-08 05:05:49
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #2929 HTTP_ERROR - /api/register
- **时间**: 2026-10-08 05:05:48
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #2927 HTTP_ERROR - /api/auth/login
- **时间**: 2026-10-08 05:05:21
- **方式**: POST
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #2928 HTTP_ERROR - /scan/async
- **时间**: 2026-10-08 05:05:21
- **方式**: POST
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #2926 HTTP_ERROR - /api/auth/register
- **时间**: 2026-10-08 05:05:20
- **方式**: POST
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

## 🛡️ 安全扫描器探测摘要（已排除，共8条）
这些是自动化漏洞扫描工具的探测行为，非真实API错误。

| 探测类型 | 次数 |
|----------|------|
| WordPress扫描探测 | 4 |
| 其他探测 | 4 |
