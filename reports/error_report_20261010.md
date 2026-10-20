# 每日错误报告
**日期**: 2026-10-10
**生成时间**: 2026-10-11 10:40:15

## 📊 总览
- **总错误数**: 54
  - 🔴 真实API错误: 0
  - 🟡 安全扫描器探测: 54
  - 系统服务错误 (journal): 0

> 💡 安全扫描器探测（54条）已从高频错误分析中排除，这些是自动化漏洞扫描行为，404为正确响应。
- **错误类型数**: 1
- **高频错误（>=3次）**: 1
- **未解决**: 0 / **已解决**: 0

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 54 | /wp-admin,/phpmyadmin,/.amplifyrc,/.aws/config,/.docker/config.json,/.claude/... |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| /phpmyadmin | GET | 4 | HTTP_ERROR |
| /wp-admin | GET | 4 | HTTP_ERROR |
| /.amplifyrc | GET | 1 | HTTP_ERROR |
| /.aws/config | GET | 1 | HTTP_ERROR |
| /.aws/credentials | GET | 1 | HTTP_ERROR |
| /.aws/credentials.bak | GET | 1 | HTTP_ERROR |
| /.azure/profiles.xml | GET | 1 | HTTP_ERROR |
| /.boto | GET | 1 | HTTP_ERROR |
| /.claude/settings.json | GET | 1 | HTTP_ERROR |
| /.claude/settings.local.json | GET | 1 | HTTP_ERROR |
| /.docker/config.json | GET | 1 | HTTP_ERROR |
| /.git-credentials | GET | 1 | HTTP_ERROR |
| /.github/workflows/deploy.yml | GET | 1 | HTTP_ERROR |
| /.gitlab-ci.yml | GET | 1 | HTTP_ERROR |
| /.gitmodules | GET | 1 | HTTP_ERROR |
| /.s3cfg | GET | 1 | HTTP_ERROR |
| /.terraform.d/credentials.tfrc.json | GET | 1 | HTTP_ERROR |
| /Dockerfile | GET | 1 | HTTP_ERROR |
| /_profiler/phpinfo | GET | 1 | HTTP_ERROR |
| /app.config.js | GET | 1 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-10-10 04:00 | 2 |
| 2026-10-10 10:00 | 2 |
| 2026-10-10 16:00 | 2 |
| 2026-10-10 19:00 | 46 |
| 2026-10-10 22:00 | 2 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（54次）
涉及端点/服务：/wp-admin,/phpmyadmin,/.amplifyrc,/.aws/config,/.docker/config.json,/.claude/settings.json,/.claude/settings.local.json,/.boto,/.aws/credentials.bak,/.aws/credentials,/.git-credentials,/.github/workflows/deploy.yml,/.gitlab-ci.yml,/.gitmodules,/.s3cfg,/Dockerfile,/_profiler/phpinfo,/app.config.js,/app.js,/appsettings.Development.json,/appsettings.Production.json,/appsettings.json,/auth.json,/aws-exports.js,/composer.json,/config.js,/config.yaml,/config.json,/config/aws.yml,/config/config.js,/credentials,/credentials.ini,/credentials.json,/env,/env-config.js,/env.js,/env.txt,/index.js,/phpinfo,/runtime-config.js,/settings.json,/vendor/composer/installed.json,/wp-config.php.bak,/wp-content/debug.log,/.azure/profiles.xml,/.terraform.d/credentials.tfrc.json,/glitchtip.json,/honeybadger.json

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 54 |

## ❌ 未解决错误详情（共0条）
无未解决错误 ✅

## 🛡️ 安全扫描器探测摘要（已排除，共54条）
这些是自动化漏洞扫描工具的探测行为，非真实API错误。

| 探测类型 | 次数 |
|----------|------|
| 其他探测 | 38 |
| 云凭证探测 | 6 |
| WordPress扫描探测 | 4 |
| Git配置探测 | 4 |
| PHP探针 | 2 |
