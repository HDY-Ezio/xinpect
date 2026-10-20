# 每日错误报告
**日期**: 2026-09-02
**生成时间**: 2026-09-03 01:10:00

## 📊 总览
- **总错误数**: 6
  - API/HTTP 错误: 5
  - 系统服务错误 (journal): 1
- **错误类型数**: 2
- **高频错误（>=3次）**: 1
- **未解决**: 6 / **已解决**: 0

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 5 | /nonexistent-page-xyz,/api/v1/nonexistent,/admin/error-stats |
| JOURNAL_ERR | 1 | /xinpect-scanner |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| /admin/error-stats | GET | 3 | HTTP_ERROR |
| /api/v1/nonexistent | GET | 1 | HTTP_ERROR |
| /nonexistent-page-xyz | GET | 1 | HTTP_ERROR |
| /xinpect-scanner | JOURNAL | 1 | JOURNAL_ERR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-09-02 17:00 | 5 |
| 2026-09-02 21:00 | 1 |

## 🖥️ 系统服务错误汇总（来自 systemd journal）
| 服务 | 错误次数 | 错误类型 |
|------|----------|----------|
| xinpect-scanner | 1 | JOURNAL_ERR |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（5次）
涉及端点/服务：/nonexistent-page-xyz,/api/v1/nonexistent,/admin/error-stats

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 5 |

## ❌ 未解决错误详情（共6条）

### #6 JOURNAL_ERR - /xinpect-scanner
- **时间**: 2026-09-02 21:02:54
- **方式**: JOURNAL
- **状态码**: 300
- **消息**: Failed to start xinpect-scanner.service - Xinpect Scanner v5.13.0 - Code Quality Analysis Service (10 Engines + SCA v2).
- **来源**: systemd[1]

### #5 HTTP_ERROR - /admin/error-stats
- **时间**: 2026-09-02 17:07:06
- **方式**: GET
- **状态码**: 401
- **消息**: HTTP 401
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #3 HTTP_ERROR - /admin/error-stats
- **时间**: 2026-09-02 17:06:45
- **方式**: GET
- **状态码**: 401
- **消息**: HTTP 401
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #4 HTTP_ERROR - /admin/error-stats
- **时间**: 2026-09-02 17:06:45
- **方式**: GET
- **状态码**: 401
- **消息**: HTTP 401
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #1 HTTP_ERROR - /nonexistent-page-xyz
- **时间**: 2026-09-02 17:06:31
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #2 HTTP_ERROR - /api/v1/nonexistent
- **时间**: 2026-09-02 17:06:31
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0
