# 每日错误报告
**日期**: 2026-10-09
**生成时间**: 2026-10-10 10:53:04

## 📊 总览
- **总错误数**: 72
  - 🔴 真实API错误: 1
  - 🟡 安全扫描器探测: 71
  - 系统服务错误 (journal): 0

> 💡 安全扫描器探测（71条）已从高频错误分析中排除，这些是自动化漏洞扫描行为，404为正确响应。
- **错误类型数**: 1
- **高频错误（>=3次）**: 1
- **未解决**: 1 / **已解决**: 0

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 72 | /wp-admin,/phpmyadmin,/api/scan/submit,/.amplifyrc,/.aws/credentials.bak,/.aw... |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| /phpmyadmin | GET | 4 | HTTP_ERROR |
| /wp-admin | GET | 4 | HTTP_ERROR |
| /_profiler/phpinfo | GET | 2 | HTTP_ERROR |
| /credentials.json | GET | 2 | HTTP_ERROR |
| /phpinfo | GET | 2 | HTTP_ERROR |
| /.amplifyrc | GET | 1 | HTTP_ERROR |
| /.aws/config | GET | 1 | HTTP_ERROR |
| /.aws/credentials | GET | 1 | HTTP_ERROR |
| /.aws/credentials.bak | GET | 1 | HTTP_ERROR |
| /.config/gcloud/application_default_credentials.json | GET | 1 | HTTP_ERROR |
| /.git-credentials | GET | 1 | HTTP_ERROR |
| /.github/workflows/deploy.yml | GET | 1 | HTTP_ERROR |
| /.gitlab-ci.yml | GET | 1 | HTTP_ERROR |
| /.gitmodules | GET | 1 | HTTP_ERROR |
| /.s3cfg | GET | 1 | HTTP_ERROR |
| /Dockerfile | GET | 1 | HTTP_ERROR |
| /_environment | GET | 1 | HTTP_ERROR |
| /api/scan/submit | POST | 1 | HTTP_ERROR |
| /app.config.js | GET | 1 | HTTP_ERROR |
| /app.js | GET | 1 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-10-09 04:00 | 2 |
| 2026-10-09 05:00 | 1 |
| 2026-10-09 08:00 | 38 |
| 2026-10-09 09:00 | 1 |
| 2026-10-09 10:00 | 2 |
| 2026-10-09 16:00 | 2 |
| 2026-10-09 20:00 | 24 |
| 2026-10-09 22:00 | 2 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（72次）
涉及端点/服务：/wp-admin,/phpmyadmin,/api/scan/submit,/.amplifyrc,/.aws/credentials.bak,/.aws/config,/.aws/credentials,/.git-credentials,/.github/workflows/deploy.yml,/.gitlab-ci.yml,/.gitmodules,/.s3cfg,/Dockerfile,/_profiler/phpinfo,/app.config.js,/app.js,/appsettings.Development.json,/appsettings.Production.json,/aws-exports.js,/appsettings.json,/auth.json,/composer.json,/config.json,/config.js,/config.yaml,/credentials,/config/aws.yml,/config/config.js,/credentials.ini,/credentials.json,/env,/env.txt,/env-config.js,/env.js,/index.js,/runtime-config.js,/settings.json,/vendor/composer/installed.json,/wp-config.php.bak,/wp-content/debug.log,/phpinfo,/security.txt,/info,/_environment,/webroot/index.php/_environment,/phpinfo.php.bak,/phpinfo.php.old,/phpinfo.php~,/info.php.bak,/phpinfo.php.save,/service-account.json,/sa.json,/gcp-key.json,/gcp-credentials.json,/gcp-sa.json,/google-credentials.json,/google-key.json,/.config/gcloud/application_default_credentials.json,/application_default_credentials.json,/key.json,/keyfile.json,/firebase-adminsdk.json,/firebase-key.json

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 72 |

## ❌ 未解决错误详情（共1条）

### #2950 HTTP_ERROR - /api/scan/submit
- **时间**: 2026-10-09 05:34:54
- **方式**: POST
- **状态码**: 403
- **消息**: HTTP 403
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

## 🛡️ 安全扫描器探测摘要（已排除，共71条）
这些是自动化漏洞扫描工具的探测行为，非真实API错误。

| 探测类型 | 次数 |
|----------|------|
| 其他探测 | 36 |
| 云凭证探测 | 19 |
| PHP探针 | 8 |
| WordPress扫描探测 | 4 |
| Git配置探测 | 4 |
