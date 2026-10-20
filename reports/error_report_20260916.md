# 每日错误报告
**日期**: 2026-09-16
**生成时间**: 2026-09-17 10:14:02

## 📊 总览
- **总错误数**: 16
  - 🔴 真实API错误: 14
  - 🟡 安全扫描器探测: 2
  - 系统服务错误 (journal): 0

> 💡 安全扫描器探测（2条）已从高频错误分析中排除，这些是自动化漏洞扫描行为，404为正确响应。
- **错误类型数**: 2
- **高频错误（>=3次）**: 2
- **未解决**: 14 / **已解决**: 0

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 12 | /blog/,/blog/wp/v2/users,/report/0e749813175b15d92d7de35bc6db556e,/api/admin/... |
| UndefinedError | 4 | /report/0e749813175b15d92d7de35bc6db556e |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| /report/0e749813175b15d92d7de35bc6db556e | GET | 8 | UndefinedError,HTTP_ERROR |
| /api/v1/scan | POST | 2 | HTTP_ERROR |
| /api/admin/monitoring | GET | 1 | HTTP_ERROR |
| /api/admin/platform-stats | GET | 1 | HTTP_ERROR |
| /api/scan/list | GET | 1 | HTTP_ERROR |
| /api/scan/result | GET | 1 | HTTP_ERROR |
| /blog/ | GET | 1 | HTTP_ERROR |
| /blog/wp/v2/users | GET | 1 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-09-16 02:00 | 2 |
| 2026-09-16 05:00 | 8 |
| 2026-09-16 08:00 | 4 |
| 2026-09-16 09:00 | 2 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（12次）
涉及端点/服务：/blog/,/blog/wp/v2/users,/report/0e749813175b15d92d7de35bc6db556e,/api/admin/monitoring,/api/admin/platform-stats,/api/scan/result,/api/scan/list,/api/v1/scan

### UndefinedError（4次）
涉及端点/服务：/report/0e749813175b15d92d7de35bc6db556e

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 16 |

## ❌ 未解决错误详情（共14条）

### #1782 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-09-16 09:25:51
- **方式**: POST
- **状态码**: 400
- **消息**: HTTP 400
- **IP**: 127.0.0.1
- **来源**: curl/7.81.0

### #1781 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-09-16 09:25:44
- **方式**: POST
- **状态码**: 400
- **消息**: HTTP 400
- **IP**: 127.0.0.1
- **来源**: curl/7.81.0

### #1780 HTTP_ERROR - /api/scan/list
- **时间**: 2026-09-16 08:12:32
- **方式**: GET
- **状态码**: 401
- **消息**: HTTP 401
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #1779 HTTP_ERROR - /api/scan/result
- **时间**: 2026-09-16 08:08:55
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #1777 HTTP_ERROR - /api/admin/monitoring
- **时间**: 2026-09-16 08:08:18
- **方式**: GET
- **状态码**: 401
- **消息**: HTTP 401
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #1778 HTTP_ERROR - /api/admin/platform-stats
- **时间**: 2026-09-16 08:08:18
- **方式**: GET
- **状态码**: 401
- **消息**: HTTP 401
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #1775 UndefinedError - /report/0e749813175b15d92d7de35bc6db556e
- **时间**: 2026-09-16 05:08:09
- **方式**: GET
- **状态码**: 500
- **消息**: 'repr' is undefined
- **堆栈摘要**:
```
    ^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/dist-packages/jinja2/utils.py", line 92, in from_obj
    if hasattr(obj, "jinja_pass_arg"):
       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
jinja2.exceptions.UndefinedError: 'repr' is undefined
```
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #1776 HTTP_ERROR - /report/0e749813175b15d92d7de35bc6db556e
- **时间**: 2026-09-16 05:08:09
- **方式**: GET
- **状态码**: 500
- **消息**: HTTP 500
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #1773 UndefinedError - /report/0e749813175b15d92d7de35bc6db556e
- **时间**: 2026-09-16 05:07:49
- **方式**: GET
- **状态码**: 500
- **消息**: 'repr' is undefined
- **堆栈摘要**:
```
    ^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/dist-packages/jinja2/utils.py", line 92, in from_obj
    if hasattr(obj, "jinja_pass_arg"):
       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
jinja2.exceptions.UndefinedError: 'repr' is undefined
```
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #1774 HTTP_ERROR - /report/0e749813175b15d92d7de35bc6db556e
- **时间**: 2026-09-16 05:07:49
- **方式**: GET
- **状态码**: 500
- **消息**: HTTP 500
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #1771 UndefinedError - /report/0e749813175b15d92d7de35bc6db556e
- **时间**: 2026-09-16 05:07:19
- **方式**: GET
- **状态码**: 500
- **消息**: 'repr' is undefined
- **堆栈摘要**:
```
    ^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/dist-packages/jinja2/utils.py", line 92, in from_obj
    if hasattr(obj, "jinja_pass_arg"):
       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
jinja2.exceptions.UndefinedError: 'repr' is undefined
```
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Sa

### #1772 HTTP_ERROR - /report/0e749813175b15d92d7de35bc6db556e
- **时间**: 2026-09-16 05:07:19
- **方式**: GET
- **状态码**: 500
- **消息**: HTTP 500
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Sa

### #1769 UndefinedError - /report/0e749813175b15d92d7de35bc6db556e
- **时间**: 2026-09-16 05:07:17
- **方式**: GET
- **状态码**: 500
- **消息**: 'repr' is undefined
- **堆栈摘要**:
```
    ^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/dist-packages/jinja2/utils.py", line 92, in from_obj
    if hasattr(obj, "jinja_pass_arg"):
       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
jinja2.exceptions.UndefinedError: 'repr' is undefined
```
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Sa

### #1770 HTTP_ERROR - /report/0e749813175b15d92d7de35bc6db556e
- **时间**: 2026-09-16 05:07:17
- **方式**: GET
- **状态码**: 500
- **消息**: HTTP 500
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Sa

## 🛡️ 安全扫描器探测摘要（已排除，共2条）
这些是自动化漏洞扫描工具的探测行为，非真实API错误。

| 探测类型 | 次数 |
|----------|------|
| 其他探测 | 1 |
| WordPress扫描探测 | 1 |
