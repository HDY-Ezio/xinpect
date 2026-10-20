# 每日错误报告
**日期**: 2026-09-05
**生成时间**: 2026-09-06 10:13:57

## 📊 总览
- **总错误数**: 4
  - API/HTTP 错误: 4
  - 系统服务错误 (journal): 0
- **错误类型数**: 2
- **高频错误（>=3次）**: 1
- **未解决**: 3 / **已解决**: 1

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 3 | /robots.txt,/api/v1/scan,/wp-config.php-backup |
| MethodNotAllowed | 1 | /api/v1/scan |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| /api/v1/scan | GET | 2 | MethodNotAllowed,HTTP_ERROR |
| /robots.txt | GET | 1 | HTTP_ERROR |
| /wp-config.php-backup | GET | 1 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-09-05 00:00 | 1 |
| 2026-09-05 02:00 | 2 |
| 2026-09-05 07:00 | 1 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（3次）
涉及端点/服务：/robots.txt,/api/v1/scan,/wp-config.php-backup

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 4 |

## ❌ 未解决错误详情（共3条）

### #466 HTTP_ERROR - /wp-config.php-backup
- **时间**: 2026-09-05 07:29:34
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.

### #464 MethodNotAllowed - /api/v1/scan
- **时间**: 2026-09-05 02:19:02
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

### #465 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-09-05 02:19:02
- **方式**: GET
- **状态码**: 405
- **消息**: HTTP 405
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0
