# 每日错误报告
**日期**: 2026-09-06
**生成时间**: 2026-09-07 10:14:55

## 📊 总览
- **总错误数**: 74
  - API/HTTP 错误: 74
  - 系统服务错误 (journal): 0
- **错误类型数**: 2
- **高频错误（>=3次）**: 1
- **未解决**: 72 / **已解决**: 2

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 72 | /api/v1/scan,/backup.tgz,/backup.rar,/backup.7z,/backups.zip,/www.zip,/www.ta... |
| MethodNotAllowed | 2 | /api/scan/estimate,/ |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| /api/scan/submit | POST | 10 | HTTP_ERROR |
| / | POST | 2 | MethodNotAllowed,HTTP_ERROR |
| /api/scan/estimate | GET | 2 | MethodNotAllowed,HTTP_ERROR |
| /api/v1/scan | POST | 2 | HTTP_ERROR |
| /1.sql | GET | 1 | HTTP_ERROR |
| /2026.zip | GET | 1 | HTTP_ERROR |
| /app.zip | GET | 1 | HTTP_ERROR |
| /backup.7z | GET | 1 | HTTP_ERROR |
| /backup.bak | GET | 1 | HTTP_ERROR |
| /backup.rar | GET | 1 | HTTP_ERROR |
| /backup.sql.gz | GET | 1 | HTTP_ERROR |
| /backup.tgz | GET | 1 | HTTP_ERROR |
| /backups.zip | GET | 1 | HTTP_ERROR |
| /backups/database.sql | GET | 1 | HTTP_ERROR |
| /bak.zip | GET | 1 | HTTP_ERROR |
| /data.bak | GET | 1 | HTTP_ERROR |
| /data.sql | GET | 1 | HTTP_ERROR |
| /data.zip | GET | 1 | HTTP_ERROR |
| /database.bak | GET | 1 | HTTP_ERROR |
| /database.sql.gz | GET | 1 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-09-06 02:00 | 60 |
| 2026-09-06 04:00 | 12 |
| 2026-09-06 15:00 | 2 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（72次）
涉及端点/服务：/api/v1/scan,/backup.tgz,/backup.rar,/backup.7z,/backups.zip,/www.zip,/www.tar.gz,/wwwroot.zip,/wwwroot.tar.gz,/htdocs.zip,/htdocs.tar.gz,/public_html.zip,/public_html.tar.gz,/web.zip,/website.zip,/site.zip,/html.zip,/app.zip,/old.zip,/bak.zip,/data.zip,/db.sql,/dump.sql,/db_backup.sql,/dbdump.sql,/mysql.sql,/mysqldump.sql,/data.sql,/users.sql,/www.sql,/site.sql,/sql.sql,/1.sql,/localhost.sql,/backup.sql.gz,/db.sql.gz,/dump.sql.gz,/database.sql.gz,/db_backup.sql.gz,/mysql.sql.gz,/database.sqlite,/db.sqlite,/backup.bak,/db.bak,/database.bak,/data.bak,/wp-content/uploads/dump.sql,/wp-content/uploads/backup.sql,/wp-content/uploads/database.sql,/wp-content/database.sql,/wp-content/mysql.sql,/backups/database.sql,/xinpect.xingwangzhineng.com.zip,/xinpect.xingwangzhineng.com.sql,/xinpect.xingwangzhineng.com_db.sql,/xinpect.zip,/xinpect.tar.gz,/xinpect.sql,/2026.zip,/api/scan/submit,/api/scan/estimate,/

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 74 |

## ❌ 未解决错误详情（共72条）

### #539 MethodNotAllowed - /
- **时间**: 2026-09-06 15:12:13
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
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Sa

### #540 HTTP_ERROR - /
- **时间**: 2026-09-06 15:12:13
- **方式**: POST
- **状态码**: 405
- **消息**: HTTP 405
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Sa

### #537 MethodNotAllowed - /api/scan/estimate
- **时间**: 2026-09-06 04:33:44
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
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Sa

### #538 HTTP_ERROR - /api/scan/estimate
- **时间**: 2026-09-06 04:33:44
- **方式**: GET
- **状态码**: 405
- **消息**: HTTP 405
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Sa

### #536 HTTP_ERROR - /api/scan/submit
- **时间**: 2026-09-06 04:26:10
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Sa

### #535 HTTP_ERROR - /api/scan/submit
- **时间**: 2026-09-06 04:24:46
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Sa

### #534 HTTP_ERROR - /api/scan/submit
- **时间**: 2026-09-06 04:24:42
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Sa

### #531 HTTP_ERROR - /api/scan/submit
- **时间**: 2026-09-06 04:23:35
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Sa

### #532 HTTP_ERROR - /api/scan/submit
- **时间**: 2026-09-06 04:23:35
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Sa

### #533 HTTP_ERROR - /api/scan/submit
- **时间**: 2026-09-06 04:23:35
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Sa

### #529 HTTP_ERROR - /api/scan/submit
- **时间**: 2026-09-06 04:23:34
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Sa

### #530 HTTP_ERROR - /api/scan/submit
- **时间**: 2026-09-06 04:23:34
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Sa

### #528 HTTP_ERROR - /api/scan/submit
- **时间**: 2026-09-06 04:23:32
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Sa

### #527 HTTP_ERROR - /api/scan/submit
- **时间**: 2026-09-06 04:23:26
- **方式**: POST
- **状态码**: 503
- **消息**: HTTP 503
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Sa

### #525 HTTP_ERROR - /xinpect.sql
- **时间**: 2026-09-06 02:27:59
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1

### #526 HTTP_ERROR - /2026.zip
- **时间**: 2026-09-06 02:27:59
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1

### #519 HTTP_ERROR - /backups/database.sql
- **时间**: 2026-09-06 02:27:58
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1

### #520 HTTP_ERROR - /xinpect.xingwangzhineng.com.zip
- **时间**: 2026-09-06 02:27:58
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1

### #521 HTTP_ERROR - /xinpect.xingwangzhineng.com.sql
- **时间**: 2026-09-06 02:27:58
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1

### #522 HTTP_ERROR - /xinpect.xingwangzhineng.com_db.sql
- **时间**: 2026-09-06 02:27:58
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1

...还有 52 条未解决错误
