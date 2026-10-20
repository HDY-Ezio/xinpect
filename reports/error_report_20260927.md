# 每日错误报告
**日期**: 2026-09-27
**生成时间**: 2026-09-28 10:40:32

## 📊 总览
- **总错误数**: 22
  - 🔴 真实API错误: 4
  - 🟡 安全扫描器探测: 18
  - 系统服务错误 (journal): 0

> 💡 安全扫描器探测（18条）已从高频错误分析中排除，这些是自动化漏洞扫描行为，404为正确响应。
- **错误类型数**: 1
- **高频错误（>=3次）**: 1
- **未解决**: 2 / **已解决**: 4

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 22 | /wp-admin,/phpmyadmin,/phpinfo,/info,/_profiler/phpinfo,/_environment,/webroo... |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| /phpmyadmin | GET | 4 | HTTP_ERROR |
| /wp-admin | GET | 4 | HTTP_ERROR |
| /blog/ | GET | 2 | HTTP_ERROR |
| /_environment | GET | 1 | HTTP_ERROR |
| /_profiler/phpinfo | GET | 1 | HTTP_ERROR |
| /blog/robots.txt | GET | 1 | HTTP_ERROR |
| /component | GET | 1 | HTTP_ERROR |
| /info | GET | 1 | HTTP_ERROR |
| /info.php.bak | GET | 1 | HTTP_ERROR |
| /phpinfo | GET | 1 | HTTP_ERROR |
| /phpinfo.php.bak | GET | 1 | HTTP_ERROR |
| /phpinfo.php.old | GET | 1 | HTTP_ERROR |
| /phpinfo.php.save | GET | 1 | HTTP_ERROR |
| /phpinfo.php~ | GET | 1 | HTTP_ERROR |
| /webroot/index.php/_environment | GET | 1 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-09-27 04:00 | 2 |
| 2026-09-27 05:00 | 10 |
| 2026-09-27 10:00 | 2 |
| 2026-09-27 16:00 | 3 |
| 2026-09-27 20:00 | 3 |
| 2026-09-27 22:00 | 2 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（22次）
涉及端点/服务：/wp-admin,/phpmyadmin,/phpinfo,/info,/_profiler/phpinfo,/_environment,/webroot/index.php/_environment,/phpinfo.php.bak,/phpinfo.php.old,/phpinfo.php~,/info.php.bak,/phpinfo.php.save,/component,/blog/robots.txt,/blog/

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 22 |

## ❌ 未解决错误详情（共2条）

### #2085 HTTP_ERROR - /info.php.bak
- **时间**: 2026-09-27 05:15:33
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Sa

### #2078 HTTP_ERROR - /info
- **时间**: 2026-09-27 05:15:25
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Sa

## 🛡️ 安全扫描器探测摘要（已排除，共18条）
这些是自动化漏洞扫描工具的探测行为，非真实API错误。

| 探测类型 | 次数 |
|----------|------|
| 其他探测 | 8 |
| PHP探针 | 6 |
| WordPress扫描探测 | 4 |
