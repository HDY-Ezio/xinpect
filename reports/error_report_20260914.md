# 每日错误报告
**日期**: 2026-09-14
**生成时间**: 2026-09-15 10:15:28

## 📊 总览
- **总错误数**: 35
  - 🔴 真实API错误: 20
  - 🟡 安全扫描器探测: 15
  - 系统服务错误 (journal): 0

> 💡 安全扫描器探测（15条）已从高频错误分析中排除，这些是自动化漏洞扫描行为，404为正确响应。
- **错误类型数**: 2
- **高频错误（>=3次）**: 2
- **未解决**: 20 / **已解决**: 0

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 24 | /dashboard,/signin,/api/v1/status,/api/v1/scan,/register,/api/session/properties |
| MethodNotAllowed | 11 | /,/dashboard |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| /dashboard | POST | 10 | MethodNotAllowed,HTTP_ERROR |
| /api/v1/scan | POST | 9 | HTTP_ERROR |
| / | POST | 6 | MethodNotAllowed |
| /signin | POST | 5 | HTTP_ERROR |
| /api/session/properties | GET | 3 | HTTP_ERROR |
| /api/v1/status | GET | 1 | HTTP_ERROR |
| /register | POST | 1 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-09-14 02:00 | 22 |
| 2026-09-14 05:00 | 4 |
| 2026-09-14 06:00 | 5 |
| 2026-09-14 17:00 | 1 |
| 2026-09-14 18:00 | 3 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（24次）
涉及端点/服务：/dashboard,/signin,/api/v1/status,/api/v1/scan,/register,/api/session/properties

### MethodNotAllowed（11次）
涉及端点/服务：/,/dashboard

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 35 |

## ❌ 未解决错误详情（共20条）

### #1725 HTTP_ERROR - /api/session/properties
- **时间**: 2026-09-14 18:56:10
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: metabase-cve-2026-72898-detect/1.0 (benign detection probes only)

### #1724 HTTP_ERROR - /api/session/properties
- **时间**: 2026-09-14 18:50:59
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: metabase-cve-2026-72898-detect/1.0 (benign detection probes only)

### #1723 HTTP_ERROR - /api/session/properties
- **时间**: 2026-09-14 18:50:58
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: metabase-cve-2026-72898-detect/1.0 (benign detection probes only)

### #1722 HTTP_ERROR - /register
- **时间**: 2026-09-14 17:12:11
- **方式**: POST
- **状态码**: 403
- **消息**: HTTP 403
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #1721 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-09-14 06:45:37
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.9

### #1720 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-09-14 06:40:06
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.9

### #1719 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-09-14 06:34:45
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.9

### #1718 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-09-14 06:29:34
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.9

### #1717 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-09-14 06:04:23
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.9

### #1716 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-09-14 05:58:52
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.9

### #1715 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-09-14 05:53:31
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.9

### #1713 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-09-14 05:48:20
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.9

### #1714 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-09-14 05:48:20
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.9

### #1712 HTTP_ERROR - /api/v1/status
- **时间**: 2026-09-14 02:25:47
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #1695 MethodNotAllowed - /
- **时间**: 2026-09-14 02:23:14
- **方式**: POST
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
- **来源**: curl/8.5.0

### #1696 MethodNotAllowed - /
- **时间**: 2026-09-14 02:23:14
- **方式**: POST
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
- **来源**: curl/8.5.0

### #1692 MethodNotAllowed - /
- **时间**: 2026-09-14 02:23:13
- **方式**: POST
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
- **来源**: curl/8.5.0

### #1693 MethodNotAllowed - /
- **时间**: 2026-09-14 02:23:13
- **方式**: POST
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
- **来源**: curl/8.5.0

### #1694 MethodNotAllowed - /
- **时间**: 2026-09-14 02:23:13
- **方式**: POST
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
- **来源**: curl/8.5.0

### #1691 MethodNotAllowed - /
- **时间**: 2026-09-14 02:22:41
- **方式**: POST
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
- **来源**: curl/8.5.0

## 🛡️ 安全扫描器探测摘要（已排除，共15条）
这些是自动化漏洞扫描工具的探测行为，非真实API错误。

| 探测类型 | 次数 |
|----------|------|
| 其他探测 | 15 |
