# 每日错误报告
**日期**: 2026-09-04
**生成时间**: 2026-09-05 10:14:10

## 📊 总览
- **总错误数**: 39
  - API/HTTP 错误: 39
  - 系统服务错误 (journal): 0
- **错误类型数**: 2
- **高频错误（>=3次）**: 1
- **未解决**: 39 / **已解决**: 0

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 37 | /,/config.xml,/database.sql,/storage/logs/laravel.log,/api/.env,/.git/HEAD,/p... |
| MethodNotAllowed | 2 | / |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| / | POST | 4 | MethodNotAllowed,HTTP_ERROR |
| /.env | GET | 4 | HTTP_ERROR |
| /.bash_history | GET | 1 | HTTP_ERROR |
| /.env.production | GET | 1 | HTTP_ERROR |
| /.git/HEAD | GET | 1 | HTTP_ERROR |
| /.npmrc | GET | 1 | HTTP_ERROR |
| /.ssh/id_ed25519 | GET | 1 | HTTP_ERROR |
| /.ssh/id_rsa | GET | 1 | HTTP_ERROR |
| /.svn/wc.db | GET | 1 | HTTP_ERROR |
| /.vscode/sftp.json | GET | 1 | HTTP_ERROR |
| /_vti_pvt/service.pwd | GET | 1 | HTTP_ERROR |
| /actuator/heapdump | GET | 1 | HTTP_ERROR |
| /api/.env | GET | 1 | HTTP_ERROR |
| /api/v1/validate/code | POST | 1 | HTTP_ERROR |
| /backup.sql | GET | 1 | HTTP_ERROR |
| /backup.tar.gz | GET | 1 | HTTP_ERROR |
| /backup.zip | GET | 1 | HTTP_ERROR |
| /config.php | GET | 1 | HTTP_ERROR |
| /config.xml | GET | 1 | HTTP_ERROR |
| /database.sql | GET | 1 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-09-04 00:00 | 2 |
| 2026-09-04 03:00 | 30 |
| 2026-09-04 05:00 | 2 |
| 2026-09-04 06:00 | 2 |
| 2026-09-04 07:00 | 2 |
| 2026-09-04 14:00 | 1 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（37次）
涉及端点/服务：/,/config.xml,/database.sql,/storage/logs/laravel.log,/api/.env,/.git/HEAD,/phpinfo.php,/.env,/user_secrets.yml,/.env.production,/server.key,/.npmrc,/.bash_history,/docker-compose.yml,/secrets.json,/.vscode/sftp.json,/dump.sql,/config.php,/backup.sql,/wp-config.php,/database_backup.sql,/.svn/wc.db,/actuator/heapdump,/backup.tar.gz,/wp-admin/setup-config.php,/_vti_pvt/service.pwd,/.ssh/id_rsa,/backup.zip,/.ssh/id_ed25519,/favicon.ico,/robots.txt,/api/v1/validate/code,/prompts/test

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 39 |

## ❌ 未解决错误详情（共39条）

### #462 HTTP_ERROR - /.env
- **时间**: 2026-09-04 14:31:05
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Sa

### #460 HTTP_ERROR - /.env
- **时间**: 2026-09-04 07:08:41
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/11.

### #461 HTTP_ERROR - /.env
- **时间**: 2026-09-04 07:08:41
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_1) AppleWebKit/603.1.10 (KHTML, like Gecko) Version/10.

### #458 HTTP_ERROR - /api/v1/validate/code
- **时间**: 2026-09-04 06:05:40
- **方式**: POST
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (compatible; credscanner-ai/1.0)

### #459 HTTP_ERROR - /prompts/test
- **时间**: 2026-09-04 06:05:40
- **方式**: POST
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (compatible; credscanner-ai/1.0)

### #457 HTTP_ERROR - /robots.txt
- **时间**: 2026-09-04 05:29:17
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.

### #456 HTTP_ERROR - /favicon.ico
- **时间**: 2026-09-04 05:20:56
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (compatible; CensysInspect/1.1; +https://about.censys.io/)

### #454 HTTP_ERROR - /backup.zip
- **时间**: 2026-09-04 03:49:07
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Go-http-client/1.1

### #455 HTTP_ERROR - /.ssh/id_ed25519
- **时间**: 2026-09-04 03:49:07
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Go-http-client/1.1

### #444 HTTP_ERROR - /config.php
- **时间**: 2026-09-04 03:49:06
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Go-http-client/1.1

### #445 HTTP_ERROR - /backup.sql
- **时间**: 2026-09-04 03:49:06
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Go-http-client/1.1

### #446 HTTP_ERROR - /wp-config.php
- **时间**: 2026-09-04 03:49:06
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Go-http-client/1.1

### #447 HTTP_ERROR - /database_backup.sql
- **时间**: 2026-09-04 03:49:06
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Go-http-client/1.1

### #448 HTTP_ERROR - /.svn/wc.db
- **时间**: 2026-09-04 03:49:06
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Go-http-client/1.1

### #449 HTTP_ERROR - /actuator/heapdump
- **时间**: 2026-09-04 03:49:06
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Go-http-client/1.1

### #450 HTTP_ERROR - /backup.tar.gz
- **时间**: 2026-09-04 03:49:06
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Go-http-client/1.1

### #451 HTTP_ERROR - /wp-admin/setup-config.php
- **时间**: 2026-09-04 03:49:06
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Go-http-client/1.1

### #452 HTTP_ERROR - /_vti_pvt/service.pwd
- **时间**: 2026-09-04 03:49:06
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Go-http-client/1.1

### #453 HTTP_ERROR - /.ssh/id_rsa
- **时间**: 2026-09-04 03:49:06
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Go-http-client/1.1

### #433 HTTP_ERROR - /phpinfo.php
- **时间**: 2026-09-04 03:49:05
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Go-http-client/1.1

...还有 19 条未解决错误
