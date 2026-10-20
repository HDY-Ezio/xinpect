# 每日错误报告
**日期**: 2026-10-06
**生成时间**: 2026-10-07 10:40:23

## 📊 总览
- **总错误数**: 26
  - 🔴 真实API错误: 18
  - 🟡 安全扫描器探测: 8
  - 系统服务错误 (journal): 0

> 💡 安全扫描器探测（8条）已从高频错误分析中排除，这些是自动化漏洞扫描行为，404为正确响应。
- **错误类型数**: 1
- **高频错误（>=3次）**: 1
- **未解决**: 18 / **已解决**: 0

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 26 | /wp-admin,/phpmyadmin,/report/,/wp-config.php.bak,/wp-config.php.save,/wp-con... |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| /phpmyadmin | GET | 4 | HTTP_ERROR |
| /wp-admin | GET | 4 | HTTP_ERROR |
| /.github/copilot-instructions.md | GET | 1 | HTTP_ERROR |
| /AGENTS.md | GET | 1 | HTTP_ERROR |
| /CLAUDE.md | GET | 1 | HTTP_ERROR |
| /README.md | GET | 1 | HTTP_ERROR |
| /api/config | GET | 1 | HTTP_ERROR |
| /api/orders/list | GET | 1 | HTTP_ERROR |
| /api/scan/list | GET | 1 | HTTP_ERROR |
| /api/scan/test_scan_id/false-positive | POST | 1 | HTTP_ERROR |
| /api/vip/check | GET | 1 | HTTP_ERROR |
| /api/vip/plans | GET | 1 | HTTP_ERROR |
| /config.js | GET | 1 | HTTP_ERROR |
| /config.json | GET | 1 | HTTP_ERROR |
| /config.php.bak | GET | 1 | HTTP_ERROR |
| /js/env.js | GET | 1 | HTTP_ERROR |
| /report/ | GET | 1 | HTTP_ERROR |
| /wp-config.php.bak | GET | 1 | HTTP_ERROR |
| /wp-config.php.old | GET | 1 | HTTP_ERROR |
| /wp-config.php.save | GET | 1 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-10-06 04:00 | 2 |
| 2026-10-06 10:00 | 2 |
| 2026-10-06 11:00 | 5 |
| 2026-10-06 15:00 | 1 |
| 2026-10-06 16:00 | 6 |
| 2026-10-06 20:00 | 8 |
| 2026-10-06 22:00 | 2 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（26次）
涉及端点/服务：/wp-admin,/phpmyadmin,/report/,/wp-config.php.bak,/wp-config.php.save,/wp-config.php.old,/config.php.bak,/api/scan/test_scan_id/false-positive,/api/vip/check,/api/vip/plans,/api/orders/list,/api/scan/list,/README.md,/js/env.js,/config.js,/AGENTS.md,/CLAUDE.md,/api/config,/.github/copilot-instructions.md,/config.json

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 26 |

## ❌ 未解决错误详情（共18条）

### #2374 HTTP_ERROR - /README.md
- **时间**: 2026-10-06 20:57:36
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Sa

### #2375 HTTP_ERROR - /js/env.js
- **时间**: 2026-10-06 20:57:36
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Sa

### #2376 HTTP_ERROR - /config.js
- **时间**: 2026-10-06 20:57:36
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Sa

### #2377 HTTP_ERROR - /AGENTS.md
- **时间**: 2026-10-06 20:57:36
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Sa

### #2378 HTTP_ERROR - /CLAUDE.md
- **时间**: 2026-10-06 20:57:36
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Sa

### #2379 HTTP_ERROR - /api/config
- **时间**: 2026-10-06 20:57:36
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Sa

### #2380 HTTP_ERROR - /.github/copilot-instructions.md
- **时间**: 2026-10-06 20:57:36
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Sa

### #2381 HTTP_ERROR - /config.json
- **时间**: 2026-10-06 20:57:36
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Sa

### #2370 HTTP_ERROR - /api/vip/check
- **时间**: 2026-10-06 16:02:31
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: python-requests/2.34.2

### #2371 HTTP_ERROR - /api/vip/plans
- **时间**: 2026-10-06 16:02:31
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: python-requests/2.34.2

### #2372 HTTP_ERROR - /api/orders/list
- **时间**: 2026-10-06 16:02:31
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: python-requests/2.34.2

### #2373 HTTP_ERROR - /api/scan/list
- **时间**: 2026-10-06 16:02:31
- **方式**: GET
- **状态码**: 401
- **消息**: HTTP 401
- **IP**: 127.0.0.1
- **来源**: python-requests/2.34.2

### #2367 HTTP_ERROR - /api/scan/test_scan_id/false-positive
- **时间**: 2026-10-06 15:05:54
- **方式**: POST
- **状态码**: 401
- **消息**: HTTP 401
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #2366 HTTP_ERROR - /config.php.bak
- **时间**: 2026-10-06 11:48:47
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 6.3; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Saf

### #2363 HTTP_ERROR - /wp-config.php.bak
- **时间**: 2026-10-06 11:48:46
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 6.3; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Saf

### #2364 HTTP_ERROR - /wp-config.php.save
- **时间**: 2026-10-06 11:48:46
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 6.3; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Saf

### #2365 HTTP_ERROR - /wp-config.php.old
- **时间**: 2026-10-06 11:48:46
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 6.3; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Saf

### #2362 HTTP_ERROR - /report/
- **时间**: 2026-10-06 11:06:25
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Sa

## 🛡️ 安全扫描器探测摘要（已排除，共8条）
这些是自动化漏洞扫描工具的探测行为，非真实API错误。

| 探测类型 | 次数 |
|----------|------|
| WordPress扫描探测 | 4 |
| 其他探测 | 4 |
