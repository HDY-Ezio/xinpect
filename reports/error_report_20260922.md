# 每日错误报告
**日期**: 2026-09-22
**生成时间**: 2026-09-23 10:23:26

## 📊 总览
- **总错误数**: 45
  - 🔴 真实API错误: 6
  - 🟡 安全扫描器探测: 39
  - 系统服务错误 (journal): 0

> 💡 安全扫描器探测（39条）已从高频错误分析中排除，这些是自动化漏洞扫描行为，404为正确响应。
- **错误类型数**: 1
- **高频错误（>=3次）**: 1
- **未解决**: 0 / **已解决**: 45

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 45 | /config.json,/dump.sql,/wp-admin,/phpmyadmin,/api/generate-key,/phpinfo,/info... |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| /phpmyadmin | GET | 8 | HTTP_ERROR |
| /wp-admin | GET | 8 | HTTP_ERROR |
| /pdf-pro/health | GET | 2 | HTTP_ERROR |
| /.config/gcloud/application_default_credentials.json | GET | 1 | HTTP_ERROR |
| /_environment | GET | 1 | HTTP_ERROR |
| /_profiler/phpinfo | GET | 1 | HTTP_ERROR |
| /api/generate-key | POST | 1 | HTTP_ERROR |
| /application_default_credentials.json | GET | 1 | HTTP_ERROR |
| /config.json | GET | 1 | HTTP_ERROR |
| /credentials.json | GET | 1 | HTTP_ERROR |
| /dump.sql | GET | 1 | HTTP_ERROR |
| /firebase-adminsdk.json | GET | 1 | HTTP_ERROR |
| /firebase-key.json | GET | 1 | HTTP_ERROR |
| /gcp-credentials.json | GET | 1 | HTTP_ERROR |
| /gcp-key.json | GET | 1 | HTTP_ERROR |
| /gcp-sa.json | GET | 1 | HTTP_ERROR |
| /google-credentials.json | GET | 1 | HTTP_ERROR |
| /google-key.json | GET | 1 | HTTP_ERROR |
| /info | GET | 1 | HTTP_ERROR |
| /info.php.bak | GET | 1 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-09-22 01:00 | 2 |
| 2026-09-22 04:00 | 2 |
| 2026-09-22 07:00 | 25 |
| 2026-09-22 08:00 | 4 |
| 2026-09-22 09:00 | 6 |
| 2026-09-22 10:00 | 2 |
| 2026-09-22 16:00 | 2 |
| 2026-09-22 22:00 | 2 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（45次）
涉及端点/服务：/config.json,/dump.sql,/wp-admin,/phpmyadmin,/api/generate-key,/phpinfo,/info,/_profiler/phpinfo,/_environment,/webroot/index.php/_environment,/phpinfo.php.bak,/phpinfo.php.old,/phpinfo.php~,/info.php.bak,/phpinfo.php.save,/service-account.json,/sa.json,/gcp-key.json,/gcp-credentials.json,/gcp-sa.json,/credentials.json,/google-credentials.json,/google-key.json,/.config/gcloud/application_default_credentials.json,/application_default_credentials.json,/key.json,/keyfile.json,/firebase-adminsdk.json,/firebase-key.json,/pdf-pro/health

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 45 |

## ❌ 未解决错误详情（共0条）
无未解决错误 ✅

## 🛡️ 安全扫描器探测摘要（已排除，共39条）
这些是自动化漏洞扫描工具的探测行为，非真实API错误。

| 探测类型 | 次数 |
|----------|------|
| 云凭证探测 | 14 |
| 其他探测 | 11 |
| WordPress扫描探测 | 8 |
| PHP探针 | 6 |
