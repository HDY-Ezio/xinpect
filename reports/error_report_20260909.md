# 每日错误报告
**日期**: 2026-09-09
**生成时间**: 2026-09-10 10:14:16

## 📊 总览
- **总错误数**: 216
  - 🔴 真实API错误: 216
  - 🟡 安全扫描器探测: 0
  - 系统服务错误 (journal): 0
- **错误类型数**: 2
- **高频错误（>=3次）**: 1
- **未解决**: 216 / **已解决**: 0

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 214 | /api/pay/create,/api/credits/packages,/api/scan/health,/api/scan/estimate,/ap... |
| MethodNotAllowed | 2 | /api/scan/submit,/scan |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| /api/v1/scan | POST | 160 | HTTP_ERROR |
| /api/scan/estimate | POST | 20 | HTTP_ERROR |
| /api/pay/create | POST | 9 | HTTP_ERROR |
| /api/scan/submit | POST | 8 | HTTP_ERROR |
| /about | GET | 2 | HTTP_ERROR |
| /api/scan/submit | GET | 2 | MethodNotAllowed,HTTP_ERROR |
| /docs | GET | 2 | HTTP_ERROR |
| /results | GET | 2 | HTTP_ERROR |
| /scan | GET | 2 | MethodNotAllowed,HTTP_ERROR |
| /api/alerts | GET | 1 | HTTP_ERROR |
| /api/credits/packages | GET | 1 | HTTP_ERROR |
| /api/scan/health | GET | 1 | HTTP_ERROR |
| /api/scan/list | GET | 1 | HTTP_ERROR |
| /api/stats | GET | 1 | HTTP_ERROR |
| /config.json | GET | 1 | HTTP_ERROR |
| /profile | GET | 1 | HTTP_ERROR |
| /scanner | GET | 1 | HTTP_ERROR |
| /settings | GET | 1 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-09-09 00:00 | 3 |
| 2026-09-09 01:00 | 2 |
| 2026-09-09 03:00 | 1 |
| 2026-09-09 04:00 | 8 |
| 2026-09-09 06:00 | 12 |
| 2026-09-09 07:00 | 21 |
| 2026-09-09 08:00 | 28 |
| 2026-09-09 09:00 | 4 |
| 2026-09-09 10:00 | 24 |
| 2026-09-09 11:00 | 9 |
| 2026-09-09 12:00 | 6 |
| 2026-09-09 13:00 | 6 |
| 2026-09-09 15:00 | 2 |
| 2026-09-09 16:00 | 21 |
| 2026-09-09 17:00 | 21 |
| 2026-09-09 18:00 | 15 |
| 2026-09-09 19:00 | 28 |
| 2026-09-09 20:00 | 5 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（214次）
涉及端点/服务：/api/pay/create,/api/credits/packages,/api/scan/health,/api/scan/estimate,/api/scan/list,/api/alerts,/api/scan/submit,/api/v1/scan,/config.json,/scanner,/about,/docs,/results,/scan,/settings,/profile,/api/stats

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 216 |

## ❌ 未解决错误详情（共216条）

### #1045 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-09-09 20:23:28
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.9

### #1044 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-09-09 20:18:17
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.9

### #1043 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-09-09 20:12:45
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.9

### #1042 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-09-09 20:07:14
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.9

### #1041 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-09-09 20:01:53
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.9

### #1040 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-09-09 19:56:59
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.9

### #1039 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-09-09 19:56:43
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.9

### #1038 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-09-09 19:51:28
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.9

### #1037 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-09-09 19:46:38
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.9

### #1036 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-09-09 19:46:08
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.9

### #1035 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-09-09 19:40:57
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.9

### #1034 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-09-09 19:36:38
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.9

### #1033 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-09-09 19:35:17
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.9

### #1032 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-09-09 19:31:27
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.9

### #1031 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-09-09 19:29:46
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.9

### #1030 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-09-09 19:25:47
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.9

### #1029 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-09-09 19:24:25
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.9

### #1028 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-09-09 19:20:16
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.9

### #1027 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-09-09 19:19:15
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.9

### #1019 MethodNotAllowed - /scan
- **时间**: 2026-09-09 19:15:49
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
- **来源**: curl/8.5.0

...还有 196 条未解决错误
