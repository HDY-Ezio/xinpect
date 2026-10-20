# 每日错误报告
**日期**: 2026-09-17
**生成时间**: 2026-09-18 10:14:24

## 📊 总览
- **总错误数**: 25
  - 🔴 真实API错误: 3
  - 🟡 安全扫描器探测: 22
  - 系统服务错误 (journal): 0

> 💡 安全扫描器探测（22条）已从高频错误分析中排除，这些是自动化漏洞扫描行为，404为正确响应。
- **错误类型数**: 1
- **高频错误（>=3次）**: 1
- **未解决**: 3 / **已解决**: 0

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 25 | /license.txt,/phpinfo,/info,/_profiler/phpinfo,/_environment,/webroot/index.p... |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| /.config/gcloud/application_default_credentials.json | GET | 1 | HTTP_ERROR |
| /_environment | GET | 1 | HTTP_ERROR |
| /_profiler/phpinfo | GET | 1 | HTTP_ERROR |
| /application_default_credentials.json | GET | 1 | HTTP_ERROR |
| /credentials.json | GET | 1 | HTTP_ERROR |
| /firebase-adminsdk.json | GET | 1 | HTTP_ERROR |
| /firebase-key.json | GET | 1 | HTTP_ERROR |
| /gcp-credentials.json | GET | 1 | HTTP_ERROR |
| /gcp-key.json | GET | 1 | HTTP_ERROR |
| /gcp-sa.json | GET | 1 | HTTP_ERROR |
| /google-credentials.json | GET | 1 | HTTP_ERROR |
| /google-key.json | GET | 1 | HTTP_ERROR |
| /info | GET | 1 | HTTP_ERROR |
| /info.php.bak | GET | 1 | HTTP_ERROR |
| /key.json | GET | 1 | HTTP_ERROR |
| /keyfile.json | GET | 1 | HTTP_ERROR |
| /license.txt | GET | 1 | HTTP_ERROR |
| /phpinfo | GET | 1 | HTTP_ERROR |
| /phpinfo.php.bak | GET | 1 | HTTP_ERROR |
| /phpinfo.php.old | GET | 1 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-09-17 09:00 | 1 |
| 2026-09-17 10:00 | 24 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（25次）
涉及端点/服务：/license.txt,/phpinfo,/info,/_profiler/phpinfo,/_environment,/webroot/index.php/_environment,/phpinfo.php.bak,/phpinfo.php.old,/phpinfo.php~,/info.php.bak,/phpinfo.php.save,/service-account.json,/sa.json,/gcp-key.json,/gcp-credentials.json,/gcp-sa.json,/credentials.json,/google-credentials.json,/google-key.json,/.config/gcloud/application_default_credentials.json,/application_default_credentials.json,/key.json,/keyfile.json,/firebase-adminsdk.json,/firebase-key.json

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 25 |

## ❌ 未解决错误详情（共3条）

### #1792 HTTP_ERROR - /info.php.bak
- **时间**: 2026-09-17 10:23:51
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.

### #1785 HTTP_ERROR - /info
- **时间**: 2026-09-17 10:23:46
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.

### #1783 HTTP_ERROR - /license.txt
- **时间**: 2026-09-17 09:22:13
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0

## 🛡️ 安全扫描器探测摘要（已排除，共22条）
这些是自动化漏洞扫描工具的探测行为，非真实API错误。

| 探测类型 | 次数 |
|----------|------|
| 云凭证探测 | 14 |
| PHP探针 | 6 |
| 其他探测 | 2 |
