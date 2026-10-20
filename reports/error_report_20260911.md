# 每日错误报告
**日期**: 2026-09-11
**生成时间**: 2026-09-12 10:13:37

## 📊 总览
- **总错误数**: 151
  - 🔴 真实API错误: 135
  - 🟡 安全扫描器探测: 16
  - 系统服务错误 (journal): 0

> 💡 安全扫描器探测（16条）已从高频错误分析中排除，这些是自动化漏洞扫描行为，404为正确响应。
- **错误类型数**: 4
- **高频错误（>=3次）**: 3
- **未解决**: 135 / **已解决**: 0

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 117 | /api/v1/scan,/api/ci/config,/api/ci/scan,/.git/config,/report/share/test_toke... |
| MethodNotAllowed | 30 | /scan,/ |
| NameError | 3 | /api/ci/scan |
| OperationalError | 1 | /api/ci/scan |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| / | POST | 56 | MethodNotAllowed,HTTP_ERROR |
| /index.php | POST | 14 | HTTP_ERROR |
| /wp-json/batch/v1 | POST | 14 | HTTP_ERROR |
| /api/ci/scan | POST | 8 | NameError,HTTP_ERROR,OperationalError |
| /blog/wp-json/batch/v1 | POST | 7 | HTTP_ERROR |
| /wordpress/wp-json/batch/v1 | POST | 7 | HTTP_ERROR |
| /wp-json/Batch/v1 | POST | 7 | HTTP_ERROR |
| /wp-json/batch/v1/ | POST | 7 | HTTP_ERROR |
| /scan | GET | 4 | MethodNotAllowed,HTTP_ERROR |
| /api/ci/config | GET | 3 | HTTP_ERROR |
| /wp-json/gravitysmtp/v1/tests/mock-data | GET | 3 | HTTP_ERROR |
| /api/admin/platform-stats | GET | 2 | HTTP_ERROR |
| /api/scan/github | POST | 2 | HTTP_ERROR |
| /api/v1/scan | POST | 2 | HTTP_ERROR |
| /.git/config | GET | 1 | HTTP_ERROR |
| /api/login | POST | 1 | HTTP_ERROR |
| /index.php | GET | 1 | HTTP_ERROR |
| /livewire/update | GET | 1 | HTTP_ERROR |
| /report/share/ | GET | 1 | HTTP_ERROR |
| /report/share/test_token | GET | 1 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-09-11 02:00 | 2 |
| 2026-09-11 05:00 | 10 |
| 2026-09-11 07:00 | 4 |
| 2026-09-11 18:00 | 9 |
| 2026-09-11 19:00 | 38 |
| 2026-09-11 20:00 | 88 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（117次）
涉及端点/服务：/api/v1/scan,/api/ci/config,/api/ci/scan,/.git/config,/report/share/test_token,/report/share/,/scan,/api/scan/github,/api/admin/platform-stats,/api/login,/,/index.php,/wp-json/batch/v1,/wp-json/Batch/v1,/wp-json/batch/v1/,/blog/wp-json/batch/v1,/wordpress/wp-json/batch/v1,/wp/v2/posts/999999,/wp/v2/pages,/wp/v2/media,/wp/v2/categories,/wp/v2/tags,/wp/v2/posts/999998,/wp/v2/posts/99999,/wp/v2/posts/9999999,/wp-json/gravitysmtp/v1/tests/mock-data,/livewire/update,/signup

### MethodNotAllowed（30次）
涉及端点/服务：/scan,/

### NameError（3次）
涉及端点/服务：/api/ci/scan

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 151 |

## ❌ 未解决错误详情（共135条）

### #1456 HTTP_ERROR - /signup
- **时间**: 2026-09-11 20:03:06
- **方式**: POST
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0

### #1452 MethodNotAllowed - /
- **时间**: 2026-09-11 20:01:00
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
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0

### #1453 HTTP_ERROR - /
- **时间**: 2026-09-11 20:01:00
- **方式**: POST
- **状态码**: 405
- **消息**: HTTP 405
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0

### #1454 MethodNotAllowed - /
- **时间**: 2026-09-11 20:01:00
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
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0

### #1455 HTTP_ERROR - /
- **时间**: 2026-09-11 20:01:00
- **方式**: POST
- **状态码**: 405
- **消息**: HTTP 405
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0

### #1450 MethodNotAllowed - /
- **时间**: 2026-09-11 20:00:56
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
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0

### #1451 HTTP_ERROR - /
- **时间**: 2026-09-11 20:00:56
- **方式**: POST
- **状态码**: 405
- **消息**: HTTP 405
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0

### #1448 MethodNotAllowed - /
- **时间**: 2026-09-11 20:00:55
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
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0

### #1449 HTTP_ERROR - /
- **时间**: 2026-09-11 20:00:55
- **方式**: POST
- **状态码**: 405
- **消息**: HTTP 405
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0

### #1441 MethodNotAllowed - /
- **时间**: 2026-09-11 20:00:32
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
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0

### #1442 HTTP_ERROR - /
- **时间**: 2026-09-11 20:00:32
- **方式**: POST
- **状态码**: 405
- **消息**: HTTP 405
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0

### #1444 MethodNotAllowed - /
- **时间**: 2026-09-11 20:00:32
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
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0

### #1445 HTTP_ERROR - /
- **时间**: 2026-09-11 20:00:32
- **方式**: POST
- **状态码**: 405
- **消息**: HTTP 405
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0

### #1446 HTTP_ERROR - /livewire/update
- **时间**: 2026-09-11 20:00:32
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0

### #1447 HTTP_ERROR - /wp-json/gravitysmtp/v1/tests/mock-data
- **时间**: 2026-09-11 20:00:32
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mo

### #1440 HTTP_ERROR - /wp-json/gravitysmtp/v1/tests/mock-data
- **时间**: 2026-09-11 20:00:31
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0

### #1439 HTTP_ERROR - /wp-json/gravitysmtp/v1/tests/mock-data
- **时间**: 2026-09-11 20:00:30
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Sa

### #1437 HTTP_ERROR - /wp/v2/posts/99999
- **时间**: 2026-09-11 20:00:24
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Sa

### #1438 HTTP_ERROR - /wp/v2/posts/9999999
- **时间**: 2026-09-11 20:00:24
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Sa

### #1435 HTTP_ERROR - /wp/v2/tags
- **时间**: 2026-09-11 20:00:23
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Sa

...还有 115 条未解决错误

## 🛡️ 安全扫描器探测摘要（已排除，共16条）
这些是自动化漏洞扫描工具的探测行为，非真实API错误。

| 探测类型 | 次数 |
|----------|------|
| PHP探针 | 15 |
| Git配置探测 | 1 |
