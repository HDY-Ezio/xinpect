# 每日错误报告
**日期**: 2026-10-11
**生成时间**: 2026-10-12 10:41:07

## 📊 总览
- **总错误数**: 48
  - 🔴 真实API错误: 40
  - 🟡 安全扫描器探测: 8
  - 系统服务错误 (journal): 0

> 💡 安全扫描器探测（8条）已从高频错误分析中排除，这些是自动化漏洞扫描行为，404为正确响应。
- **错误类型数**: 2
- **高频错误（>=3次）**: 2
- **未解决**: 40 / **已解决**: 0

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 40 | /wp-admin,/phpmyadmin,/api/github/status,/api/github/authorize,/api/scan/gith... |
| BuildError | 8 | /api/github/callback |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| /api/github/callback | GET | 16 | BuildError,HTTP_ERROR |
| /api/dashboard/summary | GET | 4 | HTTP_ERROR |
| /phpmyadmin | GET | 4 | HTTP_ERROR |
| /wp-admin | GET | 4 | HTTP_ERROR |
| /api/github/authorize | GET | 3 | HTTP_ERROR |
| /api/github/status | GET | 3 | HTTP_ERROR |
| /api/trends | GET | 3 | HTTP_ERROR |
| /api/ci/config | GET | 2 | HTTP_ERROR |
| /api/v1/rules | GET | 2 | HTTP_ERROR |
| /api/webhook/github | POST | 2 | HTTP_ERROR |
| /api/github/authorize | HEAD | 1 | HTTP_ERROR |
| /api/github/repos | GET | 1 | HTTP_ERROR |
| /api/repos/list | GET | 1 | HTTP_ERROR |
| /api/scan/github | POST | 1 | HTTP_ERROR |
| /api/v1/feed/verify | POST | 1 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-10-11 04:00 | 2 |
| 2026-10-11 06:00 | 2 |
| 2026-10-11 09:00 | 4 |
| 2026-10-11 10:00 | 2 |
| 2026-10-11 11:00 | 18 |
| 2026-10-11 12:00 | 2 |
| 2026-10-11 13:00 | 8 |
| 2026-10-11 14:00 | 4 |
| 2026-10-11 15:00 | 2 |
| 2026-10-11 16:00 | 2 |
| 2026-10-11 22:00 | 2 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（40次）
涉及端点/服务：/wp-admin,/phpmyadmin,/api/github/status,/api/github/authorize,/api/scan/github,/api/ci/config,/api/github/callback,/api/github/repos,/api/dashboard/summary,/api/trends,/api/v1/feed/verify,/api/v1/rules,/api/webhook/github,/api/repos/list

### BuildError（8次）
涉及端点/服务：/api/github/callback

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 48 |

## ❌ 未解决错误详情（共40条）

### #3116 HTTP_ERROR - /api/webhook/github
- **时间**: 2026-10-11 15:00:14
- **方式**: POST
- **状态码**: 400
- **消息**: HTTP 400
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #3117 HTTP_ERROR - /api/repos/list
- **时间**: 2026-10-11 15:00:14
- **方式**: GET
- **状态码**: 401
- **消息**: HTTP 401
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #3115 HTTP_ERROR - /api/v1/rules
- **时间**: 2026-10-11 14:58:01
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.12

### #3114 HTTP_ERROR - /api/webhook/github
- **时间**: 2026-10-11 14:57:42
- **方式**: POST
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #3113 HTTP_ERROR - /api/ci/config
- **时间**: 2026-10-11 14:57:00
- **方式**: GET
- **状态码**: 401
- **消息**: HTTP 401
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #3112 HTTP_ERROR - /api/v1/rules
- **时间**: 2026-10-11 14:56:15
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.12

### #3111 HTTP_ERROR - /api/v1/feed/verify
- **时间**: 2026-10-11 13:54:27
- **方式**: POST
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #3109 HTTP_ERROR - /api/dashboard/summary
- **时间**: 2026-10-11 13:51:18
- **方式**: GET
- **状态码**: 401
- **消息**: HTTP 401
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #3110 HTTP_ERROR - /api/trends
- **时间**: 2026-10-11 13:51:18
- **方式**: GET
- **状态码**: 401
- **消息**: HTTP 401
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #3108 HTTP_ERROR - /api/dashboard/summary
- **时间**: 2026-10-11 13:51:12
- **方式**: GET
- **状态码**: 401
- **消息**: HTTP 401
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #3106 HTTP_ERROR - /api/trends
- **时间**: 2026-10-11 13:51:04
- **方式**: GET
- **状态码**: 401
- **消息**: HTTP 401
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #3107 HTTP_ERROR - /api/trends
- **时间**: 2026-10-11 13:51:04
- **方式**: GET
- **状态码**: 401
- **消息**: HTTP 401
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #3105 HTTP_ERROR - /api/dashboard/summary
- **时间**: 2026-10-11 13:50:56
- **方式**: GET
- **状态码**: 401
- **消息**: HTTP 401
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #3104 HTTP_ERROR - /api/dashboard/summary
- **时间**: 2026-10-11 13:50:51
- **方式**: GET
- **状态码**: 401
- **消息**: HTTP 401
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #3102 HTTP_ERROR - /api/github/status
- **时间**: 2026-10-11 12:18:56
- **方式**: GET
- **状态码**: 401
- **消息**: HTTP 401
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #3103 HTTP_ERROR - /api/github/repos
- **时间**: 2026-10-11 12:18:56
- **方式**: GET
- **状态码**: 401
- **消息**: HTTP 401
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #3100 BuildError - /api/github/callback
- **时间**: 2026-10-11 11:57:26
- **方式**: GET
- **状态码**: 500
- **消息**: Could not build url for endpoint 'dashboard'. Did you mean 'dashboard_page' instead?
- **堆栈摘要**:
```
    rv = url_adapter.build(  # type: ignore[union-attr]
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/ubuntu/.local/lib/python3.12/site-packages/werkzeug/routing/map.py", line 901, in build
    raise BuildError(endpoint, values, method, self)
werkzeug.routing.exceptions.BuildError: Could not build url for endpoint 'dashboard'. Did you mean 'dashboard_page' instead?
```
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #3101 HTTP_ERROR - /api/github/callback
- **时间**: 2026-10-11 11:57:26
- **方式**: GET
- **状态码**: 500
- **消息**: HTTP 500
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #3098 BuildError - /api/github/callback
- **时间**: 2026-10-11 11:56:41
- **方式**: GET
- **状态码**: 500
- **消息**: Could not build url for endpoint 'dashboard'. Did you mean 'dashboard_page' instead?
- **堆栈摘要**:
```
    rv = url_adapter.build(  # type: ignore[union-attr]
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/ubuntu/.local/lib/python3.12/site-packages/werkzeug/routing/map.py", line 901, in build
    raise BuildError(endpoint, values, method, self)
werkzeug.routing.exceptions.BuildError: Could not build url for endpoint 'dashboard'. Did you mean 'dashboard_page' instead?
```
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Sa

### #3099 HTTP_ERROR - /api/github/callback
- **时间**: 2026-10-11 11:56:41
- **方式**: GET
- **状态码**: 500
- **消息**: HTTP 500
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Sa

...还有 20 条未解决错误

## 🛡️ 安全扫描器探测摘要（已排除，共8条）
这些是自动化漏洞扫描工具的探测行为，非真实API错误。

| 探测类型 | 次数 |
|----------|------|
| WordPress扫描探测 | 4 |
| 其他探测 | 4 |
