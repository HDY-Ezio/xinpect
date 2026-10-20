# 每日错误报告
**日期**: 2026-09-21
**生成时间**: 2026-09-22 10:15:18

## 📊 总览
- **总错误数**: 29
  - 🔴 真实API错误: 29
  - 🟡 安全扫描器探测: 0
  - 系统服务错误 (journal): 0
- **错误类型数**: 2
- **高频错误（>=3次）**: 1
- **未解决**: 29 / **已解决**: 0

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 28 | /api/health,/api/scan/status/test,/api/scoring/rules,/api/component-check,/ap... |
| MethodNotAllowed | 1 | /api/component-check |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| /wp-admin | GET | 6 | HTTP_ERROR |
| /phpmyadmin | GET | 5 | HTTP_ERROR |
| /api/component-check | GET | 2 | MethodNotAllowed,HTTP_ERROR |
| /api/component-check | POST | 2 | HTTP_ERROR |
| /api/scan/github | POST | 2 | HTTP_ERROR |
| /api/scoring/rules | GET | 2 | HTTP_ERROR |
| /api/health | GET | 1 | HTTP_ERROR |
| /api/pay/check | GET | 1 | HTTP_ERROR |
| /api/pay/create-order | GET | 1 | HTTP_ERROR |
| /api/pay/create-order | POST | 1 | HTTP_ERROR |
| /api/scan/status | GET | 1 | HTTP_ERROR |
| /api/scan/status/test | GET | 1 | HTTP_ERROR |
| /api/scan/status/test123 | GET | 1 | HTTP_ERROR |
| /api/user/info | GET | 1 | HTTP_ERROR |
| /nonexistent | GET | 1 | HTTP_ERROR |
| /nonexistent-page | GET | 1 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-09-21 12:00 | 19 |
| 2026-09-21 13:00 | 6 |
| 2026-09-21 16:00 | 2 |
| 2026-09-21 22:00 | 2 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（28次）
涉及端点/服务：/api/health,/api/scan/status/test,/api/scoring/rules,/api/component-check,/api/pay/create-order,/api/pay/check,/api/scan/status,/api/user/info,/nonexistent,/nonexistent-page,/wp-admin,/api/scan/github,/api/scan/status/test123,/phpmyadmin

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 29 |

## ❌ 未解决错误详情（共29条）

### #1951 HTTP_ERROR - /wp-admin
- **时间**: 2026-09-21 22:00:02
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.12

### #1952 HTTP_ERROR - /phpmyadmin
- **时间**: 2026-09-21 22:00:02
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.12

### #1949 HTTP_ERROR - /wp-admin
- **时间**: 2026-09-21 16:00:03
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.12

### #1950 HTTP_ERROR - /phpmyadmin
- **时间**: 2026-09-21 16:00:03
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.12

### #1947 HTTP_ERROR - /wp-admin
- **时间**: 2026-09-21 13:39:42
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.12

### #1948 HTTP_ERROR - /phpmyadmin
- **时间**: 2026-09-21 13:39:42
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.12

### #1945 HTTP_ERROR - /wp-admin
- **时间**: 2026-09-21 13:27:05
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.12

### #1946 HTTP_ERROR - /phpmyadmin
- **时间**: 2026-09-21 13:27:05
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.12

### #1943 HTTP_ERROR - /wp-admin
- **时间**: 2026-09-21 13:26:33
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.12

### #1944 HTTP_ERROR - /phpmyadmin
- **时间**: 2026-09-21 13:26:33
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Python-urllib/3.12

### #1942 HTTP_ERROR - /api/scan/github
- **时间**: 2026-09-21 12:55:47
- **方式**: POST
- **状态码**: 401
- **消息**: HTTP 401
- **IP**: 127.0.0.1
- **来源**: curl/7.81.0

### #1941 HTTP_ERROR - /api/scan/status/test123
- **时间**: 2026-09-21 12:55:04
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/7.81.0

### #1940 HTTP_ERROR - /api/scan/github
- **时间**: 2026-09-21 12:52:30
- **方式**: POST
- **状态码**: 401
- **消息**: HTTP 401
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #1939 HTTP_ERROR - /api/component-check
- **时间**: 2026-09-21 12:52:15
- **方式**: POST
- **状态码**: 401
- **消息**: HTTP 401
- **IP**: 127.0.0.1
- **来源**: python-requests/2.34.2

### #1937 HTTP_ERROR - /nonexistent-page
- **时间**: 2026-09-21 12:51:00
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Werkzeug/3.1.8

### #1938 HTTP_ERROR - /wp-admin
- **时间**: 2026-09-21 12:51:00
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Werkzeug/3.1.8

### #1935 HTTP_ERROR - /api/user/info
- **时间**: 2026-09-21 12:47:18
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #1936 HTTP_ERROR - /nonexistent
- **时间**: 2026-09-21 12:47:18
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #1934 HTTP_ERROR - /api/scan/status
- **时间**: 2026-09-21 12:47:17
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #1932 HTTP_ERROR - /api/component-check
- **时间**: 2026-09-21 12:47:16
- **方式**: POST
- **状态码**: 401
- **消息**: HTTP 401
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

...还有 9 条未解决错误
