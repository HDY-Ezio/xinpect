# 每日错误报告
**日期**: 2026-09-12
**生成时间**: 2026-09-13 10:13:44

## 📊 总览
- **总错误数**: 18
  - 🔴 真实API错误: 17
  - 🟡 安全扫描器探测: 1
  - 系统服务错误 (journal): 0

> 💡 安全扫描器探测（1条）已从高频错误分析中排除，这些是自动化漏洞扫描行为，404为正确响应。
- **错误类型数**: 1
- **高频错误（>=3次）**: 1
- **未解决**: 17 / **已解决**: 0

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 18 | /wp-includes/wlwmanifest.xml,/xmlrpc.php,/blog/wp-includes/wlwmanifest.xml,/w... |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| /2018/wp-includes/wlwmanifest.xml | GET | 1 | HTTP_ERROR |
| /2019/wp-includes/wlwmanifest.xml | GET | 1 | HTTP_ERROR |
| /blog/wp-includes/wlwmanifest.xml | GET | 1 | HTTP_ERROR |
| /cms/wp-includes/wlwmanifest.xml | GET | 1 | HTTP_ERROR |
| /media/wp-includes/wlwmanifest.xml | GET | 1 | HTTP_ERROR |
| /news/wp-includes/wlwmanifest.xml | GET | 1 | HTTP_ERROR |
| /shop/wp-includes/wlwmanifest.xml | GET | 1 | HTTP_ERROR |
| /site/wp-includes/wlwmanifest.xml | GET | 1 | HTTP_ERROR |
| /sito/wp-includes/wlwmanifest.xml | GET | 1 | HTTP_ERROR |
| /test/wp-includes/wlwmanifest.xml | GET | 1 | HTTP_ERROR |
| /web/wp-includes/wlwmanifest.xml | GET | 1 | HTTP_ERROR |
| /website/wp-includes/wlwmanifest.xml | GET | 1 | HTTP_ERROR |
| /wordpress/wp-includes/wlwmanifest.xml | GET | 1 | HTTP_ERROR |
| /wp-includes/wlwmanifest.xml | GET | 1 | HTTP_ERROR |
| /wp/wp-includes/wlwmanifest.xml | GET | 1 | HTTP_ERROR |
| /wp1/wp-includes/wlwmanifest.xml | GET | 1 | HTTP_ERROR |
| /wp2/wp-includes/wlwmanifest.xml | GET | 1 | HTTP_ERROR |
| /xmlrpc.php | GET | 1 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-09-12 10:00 | 18 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（18次）
涉及端点/服务：/wp-includes/wlwmanifest.xml,/xmlrpc.php,/blog/wp-includes/wlwmanifest.xml,/web/wp-includes/wlwmanifest.xml,/wordpress/wp-includes/wlwmanifest.xml,/website/wp-includes/wlwmanifest.xml,/wp/wp-includes/wlwmanifest.xml,/news/wp-includes/wlwmanifest.xml,/2018/wp-includes/wlwmanifest.xml,/2019/wp-includes/wlwmanifest.xml,/shop/wp-includes/wlwmanifest.xml,/wp1/wp-includes/wlwmanifest.xml,/test/wp-includes/wlwmanifest.xml,/media/wp-includes/wlwmanifest.xml,/wp2/wp-includes/wlwmanifest.xml,/site/wp-includes/wlwmanifest.xml,/cms/wp-includes/wlwmanifest.xml,/sito/wp-includes/wlwmanifest.xml

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 18 |

## ❌ 未解决错误详情（共17条）

### #1473 HTTP_ERROR - /cms/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-12 10:31:50
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.10

### #1474 HTTP_ERROR - /sito/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-12 10:31:50
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.10

### #1470 HTTP_ERROR - /media/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-12 10:31:49
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.10

### #1471 HTTP_ERROR - /wp2/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-12 10:31:49
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.10

### #1472 HTTP_ERROR - /site/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-12 10:31:49
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.10

### #1466 HTTP_ERROR - /2019/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-12 10:31:48
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.10

### #1467 HTTP_ERROR - /shop/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-12 10:31:48
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.10

### #1468 HTTP_ERROR - /wp1/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-12 10:31:48
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.10

### #1469 HTTP_ERROR - /test/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-12 10:31:48
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.10

### #1462 HTTP_ERROR - /website/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-12 10:31:47
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.10

### #1463 HTTP_ERROR - /wp/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-12 10:31:47
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.10

### #1464 HTTP_ERROR - /news/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-12 10:31:47
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.10

### #1465 HTTP_ERROR - /2018/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-12 10:31:47
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.10

### #1459 HTTP_ERROR - /blog/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-12 10:31:46
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.10

### #1460 HTTP_ERROR - /web/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-12 10:31:46
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.10

### #1461 HTTP_ERROR - /wordpress/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-12 10:31:46
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.10

### #1457 HTTP_ERROR - /wp-includes/wlwmanifest.xml
- **时间**: 2026-09-12 10:31:45
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.10

## 🛡️ 安全扫描器探测摘要（已排除，共1条）
这些是自动化漏洞扫描工具的探测行为，非真实API错误。

| 探测类型 | 次数 |
|----------|------|
| PHP探针 | 1 |
