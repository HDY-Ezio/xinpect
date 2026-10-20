# 每日错误报告
**日期**: 2026-09-19
**生成时间**: 2026-09-20 10:13:46

## 📊 总览
- **总错误数**: 25
  - 🔴 真实API错误: 25
  - 🟡 安全扫描器探测: 0
  - 系统服务错误 (journal): 0
- **错误类型数**: 1
- **高频错误（>=3次）**: 1
- **未解决**: 25 / **已解决**: 0

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 25 | /api/v1/scan,/static/xinpect_showcase.png,/api/v1/register,/register |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| /static/xinpect_showcase.png | GET | 21 | HTTP_ERROR |
| /api/v1/register | POST | 2 | HTTP_ERROR |
| /api/v1/scan | POST | 1 | HTTP_ERROR |
| /register | POST | 1 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-09-19 02:00 | 1 |
| 2026-09-19 05:00 | 20 |
| 2026-09-19 06:00 | 1 |
| 2026-09-19 12:00 | 3 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（25次）
涉及端点/服务：/api/v1/scan,/static/xinpect_showcase.png,/api/v1/register,/register

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 25 |

## ❌ 未解决错误详情（共25条）

### #1919 HTTP_ERROR - /register
- **时间**: 2026-09-19 12:25:21
- **方式**: POST
- **状态码**: 403
- **消息**: HTTP 403
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #1918 HTTP_ERROR - /api/v1/register
- **时间**: 2026-09-19 12:24:44
- **方式**: POST
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #1917 HTTP_ERROR - /api/v1/register
- **时间**: 2026-09-19 12:24:19
- **方式**: POST
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #1916 HTTP_ERROR - /static/xinpect_showcase.png
- **时间**: 2026-09-19 06:03:16
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: ChildProcess TCS/undefined

### #1915 HTTP_ERROR - /static/xinpect_showcase.png
- **时间**: 2026-09-19 05:54:55
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) TCS/5.1.1 Chrome/13

### #1912 HTTP_ERROR - /static/xinpect_showcase.png
- **时间**: 2026-09-19 05:52:43
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Sa

### #1913 HTTP_ERROR - /static/xinpect_showcase.png
- **时间**: 2026-09-19 05:52:43
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4

### #1914 HTTP_ERROR - /static/xinpect_showcase.png
- **时间**: 2026-09-19 05:52:43
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4

### #1911 HTTP_ERROR - /static/xinpect_showcase.png
- **时间**: 2026-09-19 05:52:34
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: safe_mind

### #1910 HTTP_ERROR - /static/xinpect_showcase.png
- **时间**: 2026-09-19 05:52:31
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: safe_mind

### #1909 HTTP_ERROR - /static/xinpect_showcase.png
- **时间**: 2026-09-19 05:52:06
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: safe_mind

### #1908 HTTP_ERROR - /static/xinpect_showcase.png
- **时间**: 2026-09-19 05:52:03
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: safe_mind

### #1907 HTTP_ERROR - /static/xinpect_showcase.png
- **时间**: 2026-09-19 05:51:50
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: safe_mind

### #1906 HTTP_ERROR - /static/xinpect_showcase.png
- **时间**: 2026-09-19 05:51:48
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: safe_mind

### #1905 HTTP_ERROR - /static/xinpect_showcase.png
- **时间**: 2026-09-19 05:51:35
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: safe_mind

### #1904 HTTP_ERROR - /static/xinpect_showcase.png
- **时间**: 2026-09-19 05:51:30
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: safe_mind

### #1903 HTTP_ERROR - /static/xinpect_showcase.png
- **时间**: 2026-09-19 05:51:29
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: python/gevent-http-client-1.3.1

### #1902 HTTP_ERROR - /static/xinpect_showcase.png
- **时间**: 2026-09-19 05:50:56
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: python/gevent-http-client-1.3.1

### #1900 HTTP_ERROR - /static/xinpect_showcase.png
- **时间**: 2026-09-19 05:50:48
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4

### #1901 HTTP_ERROR - /static/xinpect_showcase.png
- **时间**: 2026-09-19 05:50:48
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4

...还有 5 条未解决错误
