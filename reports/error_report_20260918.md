# 每日错误报告
**日期**: 2026-09-18
**生成时间**: 2026-09-19 10:14:10

## 📊 总览
- **总错误数**: 87
  - 🔴 真实API错误: 18
  - 🟡 安全扫描器探测: 69
  - 系统服务错误 (journal): 0

> 💡 安全扫描器探测（69条）已从高频错误分析中排除，这些是自动化漏洞扫描行为，404为正确响应。
- **错误类型数**: 1
- **高频错误（>=3次）**: 1
- **未解决**: 18 / **已解决**: 0

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 87 | /blog/feed/,/blog/,/blog/wp/v2/posts/999999,/phpinfo,/info,/_profiler/phpinfo... |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| /blog/ | POST | 21 | HTTP_ERROR |
| /.config/gcloud/application_default_credentials.json | GET | 2 | HTTP_ERROR |
| /_environment | GET | 2 | HTTP_ERROR |
| /_profiler/phpinfo | GET | 2 | HTTP_ERROR |
| /api/users | GET | 2 | HTTP_ERROR |
| /application_default_credentials.json | GET | 2 | HTTP_ERROR |
| /blog/ | GET | 2 | HTTP_ERROR |
| /credentials.json | GET | 2 | HTTP_ERROR |
| /firebase-adminsdk.json | GET | 2 | HTTP_ERROR |
| /firebase-key.json | GET | 2 | HTTP_ERROR |
| /gcp-credentials.json | GET | 2 | HTTP_ERROR |
| /gcp-key.json | GET | 2 | HTTP_ERROR |
| /gcp-sa.json | GET | 2 | HTTP_ERROR |
| /google-credentials.json | GET | 2 | HTTP_ERROR |
| /google-key.json | GET | 2 | HTTP_ERROR |
| /info | GET | 2 | HTTP_ERROR |
| /info.php.bak | GET | 2 | HTTP_ERROR |
| /key.json | GET | 2 | HTTP_ERROR |
| /keyfile.json | GET | 2 | HTTP_ERROR |
| /phpinfo | GET | 2 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-09-18 04:00 | 25 |
| 2026-09-18 10:00 | 24 |
| 2026-09-18 12:00 | 24 |
| 2026-09-18 13:00 | 14 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（87次）
涉及端点/服务：/blog/feed/,/blog/,/blog/wp/v2/posts/999999,/phpinfo,/info,/_profiler/phpinfo,/_environment,/webroot/index.php/_environment,/phpinfo.php.bak,/phpinfo.php.old,/phpinfo.php~,/info.php.bak,/phpinfo.php.save,/service-account.json,/sa.json,/gcp-key.json,/gcp-credentials.json,/gcp-sa.json,/credentials.json,/google-credentials.json,/google-key.json,/.config/gcloud/application_default_credentials.json,/application_default_credentials.json,/key.json,/keyfile.json,/firebase-adminsdk.json,/firebase-key.json,/feed/,/web/wp-includes/wlwmanifest.xml,/2020/wp-includes/wlwmanifest.xml,/2019/wp-includes/wlwmanifest.xml,/2021/wp-includes/wlwmanifest.xml,/shop/wp-includes/wlwmanifest.xml,/wp1/wp-includes/wlwmanifest.xml,/test/wp-includes/wlwmanifest.xml,/site/wp-includes/wlwmanifest.xml,/cms/wp-includes/wlwmanifest.xml,/changelog,/updates,/api/users

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 87 |

## ❌ 未解决错误详情（共18条）

### #1894 HTTP_ERROR - /api/users
- **时间**: 2026-09-18 13:53:32
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/7.81.0

### #1893 HTTP_ERROR - /api/users
- **时间**: 2026-09-18 13:53:23
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/7.81.0

### #1891 HTTP_ERROR - /changelog
- **时间**: 2026-09-18 13:28:54
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/7.81.0

### #1892 HTTP_ERROR - /updates
- **时间**: 2026-09-18 13:28:54
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/7.81.0

### #1889 HTTP_ERROR - /site/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-18 13:07:34
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.69

### #1890 HTTP_ERROR - /cms/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-18 13:07:34
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.69

### #1886 HTTP_ERROR - /shop/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-18 13:07:33
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.69

### #1887 HTTP_ERROR - /wp1/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-18 13:07:33
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.69

### #1888 HTTP_ERROR - /test/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-18 13:07:33
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.69

### #1883 HTTP_ERROR - /2020/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-18 13:07:32
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.69

### #1884 HTTP_ERROR - /2019/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-18 13:07:32
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.69

### #1885 HTTP_ERROR - /2021/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-18 13:07:32
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.69

### #1882 HTTP_ERROR - /web/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-18 13:07:31
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.69

### #1881 HTTP_ERROR - /feed/
- **时间**: 2026-09-18 13:07:30
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.69

### #1865 HTTP_ERROR - /info.php.bak
- **时间**: 2026-09-18 12:27:05
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.

### #1858 HTTP_ERROR - /info
- **时间**: 2026-09-18 12:26:59
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.

### #1841 HTTP_ERROR - /info.php.bak
- **时间**: 2026-09-18 10:38:32
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.

### #1834 HTTP_ERROR - /info
- **时间**: 2026-09-18 10:38:27
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.

## 🛡️ 安全扫描器探测摘要（已排除，共69条）
这些是自动化漏洞扫描工具的探测行为，非真实API错误。

| 探测类型 | 次数 |
|----------|------|
| 其他探测 | 28 |
| 云凭证探测 | 28 |
| PHP探针 | 12 |
| WordPress扫描探测 | 1 |
