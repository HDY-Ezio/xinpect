# 每日错误报告
**日期**: 2026-10-17
**生成时间**: 2026-10-18 00:01:09

## 📊 总览
- **总错误数**: 57
  - 🔴 真实API错误: 1
  - 🟡 安全扫描器探测: 56
  - 系统服务错误 (journal): 0

> 💡 安全扫描器探测（56条）已从高频错误分析中排除，这些是自动化漏洞扫描行为，404为正确响应。
- **错误类型数**: 2
- **高频错误（>=3次）**: 1
- **未解决**: 1 / **已解决**: 0

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 56 | /wp-admin,/phpmyadmin,/upload,/.claude/settings.json,/.aws/credentials.bak,/.... |
| MethodNotAllowed | 1 | /scan |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| /phpmyadmin | GET | 3 | HTTP_ERROR |
| /wp-admin | GET | 3 | HTTP_ERROR |
| /scan | GET | 2 | MethodNotAllowed,HTTP_ERROR |
| /upload | GET | 2 | HTTP_ERROR |
| /.amplifyrc | GET | 1 | HTTP_ERROR |
| /.aws/config | GET | 1 | HTTP_ERROR |
| /.aws/credentials | GET | 1 | HTTP_ERROR |
| /.aws/credentials.bak | GET | 1 | HTTP_ERROR |
| /.boto | GET | 1 | HTTP_ERROR |
| /.claude/settings.json | GET | 1 | HTTP_ERROR |
| /.claude/settings.local.json | GET | 1 | HTTP_ERROR |
| /.docker/config.json | GET | 1 | HTTP_ERROR |
| /.git-credentials | GET | 1 | HTTP_ERROR |
| /.github/workflows/deploy.yml | GET | 1 | HTTP_ERROR |
| /.gitlab-ci.yml | GET | 1 | HTTP_ERROR |
| /.gitmodules | GET | 1 | HTTP_ERROR |
| /.jwt-secret | GET | 1 | HTTP_ERROR |
| /.jwt_secret | GET | 1 | HTTP_ERROR |
| /.s3cfg | GET | 1 | HTTP_ERROR |
| /Dockerfile | GET | 1 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-10-17 04:00 | 3 |
| 2026-10-17 05:00 | 45 |
| 2026-10-17 09:00 | 1 |
| 2026-10-17 10:00 | 5 |
| 2026-10-17 13:00 | 1 |
| 2026-10-17 16:00 | 2 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（56次）
涉及端点/服务：/wp-admin,/phpmyadmin,/upload,/.claude/settings.json,/.aws/credentials.bak,/.aws/credentials,/.aws/config,/.amplifyrc,/.claude/settings.local.json,/.docker/config.json,/.boto,/.git-credentials,/.github/workflows/deploy.yml,/.gitmodules,/.gitlab-ci.yml,/Dockerfile,/_profiler/phpinfo,/.s3cfg,/app.config.js,/app.js,/appsettings.Development.json,/appsettings.Production.json,/appsettings.json,/auth.json,/aws-exports.js,/composer.json,/config.json,/config.js,/config.yaml,/config/aws.yml,/config/config.js,/credentials,/credentials.ini,/credentials.json,/env,/env.js,/env.txt,/index.js,/runtime-config.js,/settings.json,/vendor/composer/installed.json,/wp-config.php.bak,/wp-content/debug.log,/jwt.secret,/.jwt_secret,/env-config.js,/.jwt-secret,/phpinfo,/api/health,/scan,/account

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 57 |

## ❌ 未解决错误详情（共1条）

### #4004 HTTP_ERROR - /api/health
- **时间**: 2026-10-17 09:24:18
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

## 🛡️ 安全扫描器探测摘要（已排除，共56条）
这些是自动化漏洞扫描工具的探测行为，非真实API错误。

| 探测类型 | 次数 |
|----------|------|
| 其他探测 | 42 |
| 云凭证探测 | 5 |
| Git配置探测 | 4 |
| WordPress扫描探测 | 3 |
| PHP探针 | 2 |
