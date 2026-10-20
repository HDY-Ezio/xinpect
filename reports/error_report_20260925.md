# 每日错误报告
**日期**: 2026-09-25
**生成时间**: 2026-09-26 10:18:42

## 📊 总览
- **总错误数**: 28
  - 🔴 真实API错误: 12
  - 🟡 安全扫描器探测: 16
  - 系统服务错误 (journal): 0

> 💡 安全扫描器探测（16条）已从高频错误分析中排除，这些是自动化漏洞扫描行为，404为正确响应。
- **错误类型数**: 1
- **高频错误（>=3次）**: 1
- **未解决**: 12 / **已解决**: 0

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 28 | /open/visitors/info/gets,/api/checkCleanIp,/open/,/enhancecp,/wp-admin,/phpmy... |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| /phpmyadmin | GET | 4 | HTTP_ERROR |
| /static/xinpect_showcase.png | GET | 4 | HTTP_ERROR |
| /wp-admin | GET | 4 | HTTP_ERROR |
| /_ignition/execute-solution | GET | 2 | HTTP_ERROR |
| /_environment | GET | 1 | HTTP_ERROR |
| /_profiler/phpinfo | GET | 1 | HTTP_ERROR |
| /api/checkCleanIp | GET | 1 | HTTP_ERROR |
| /enhancecp | GET | 1 | HTTP_ERROR |
| /info | GET | 1 | HTTP_ERROR |
| /info.php.bak | GET | 1 | HTTP_ERROR |
| /open/ | GET | 1 | HTTP_ERROR |
| /open/visitors/info/gets | GET | 1 | HTTP_ERROR |
| /phpinfo | GET | 1 | HTTP_ERROR |
| /phpinfo.php.bak | GET | 1 | HTTP_ERROR |
| /phpinfo.php.old | GET | 1 | HTTP_ERROR |
| /phpinfo.php.save | GET | 1 | HTTP_ERROR |
| /phpinfo.php~ | GET | 1 | HTTP_ERROR |
| /webroot/index.php/_environment | GET | 1 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-09-25 02:00 | 3 |
| 2026-09-25 03:00 | 1 |
| 2026-09-25 04:00 | 2 |
| 2026-09-25 06:00 | 10 |
| 2026-09-25 07:00 | 2 |
| 2026-09-25 08:00 | 2 |
| 2026-09-25 10:00 | 2 |
| 2026-09-25 16:00 | 2 |
| 2026-09-25 21:00 | 2 |
| 2026-09-25 22:00 | 2 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（28次）
涉及端点/服务：/open/visitors/info/gets,/api/checkCleanIp,/open/,/enhancecp,/wp-admin,/phpmyadmin,/phpinfo,/info,/_profiler/phpinfo,/_environment,/webroot/index.php/_environment,/phpinfo.php.bak,/phpinfo.php.old,/phpinfo.php~,/info.php.bak,/phpinfo.php.save,/static/xinpect_showcase.png,/_ignition/execute-solution

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 28 |

## ❌ 未解决错误详情（共12条）

### #2044 HTTP_ERROR - /_ignition/execute-solution
- **时间**: 2026-09-25 21:19:39
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Fedora; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/53

### #2043 HTTP_ERROR - /_ignition/execute-solution
- **时间**: 2026-09-25 21:12:44
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Fedora; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/53

### #2038 HTTP_ERROR - /static/xinpect_showcase.png
- **时间**: 2026-09-25 08:12:06
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Sa

### #2037 HTTP_ERROR - /static/xinpect_showcase.png
- **时间**: 2026-09-25 08:11:08
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Sa

### #2036 HTTP_ERROR - /static/xinpect_showcase.png
- **时间**: 2026-09-25 07:58:17
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Sa

### #2035 HTTP_ERROR - /static/xinpect_showcase.png
- **时间**: 2026-09-25 07:52:06
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Sa

### #2033 HTTP_ERROR - /info.php.bak
- **时间**: 2026-09-25 06:06:51
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.3

### #2026 HTTP_ERROR - /info
- **时间**: 2026-09-25 06:06:43
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.3

### #2022 HTTP_ERROR - /enhancecp
- **时间**: 2026-09-25 03:59:38
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (compatible; wpbot/1.4; +https://forms.gle/ajBaxygz9jSR8p8G9)

### #2019 HTTP_ERROR - /open/visitors/info/gets
- **时间**: 2026-09-25 02:29:08
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Vers

### #2020 HTTP_ERROR - /api/checkCleanIp
- **时间**: 2026-09-25 02:29:08
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Vers

### #2021 HTTP_ERROR - /open/
- **时间**: 2026-09-25 02:29:08
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Vers

## 🛡️ 安全扫描器探测摘要（已排除，共16条）
这些是自动化漏洞扫描工具的探测行为，非真实API错误。

| 探测类型 | 次数 |
|----------|------|
| 其他探测 | 6 |
| PHP探针 | 6 |
| WordPress扫描探测 | 4 |
