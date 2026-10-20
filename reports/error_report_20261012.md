# 每日错误报告
**日期**: 2026-10-12
**生成时间**: 2026-10-13 10:40:05

## 📊 总览
- **总错误数**: 68
  - 🔴 真实API错误: 10
  - 🟡 安全扫描器探测: 58
  - 系统服务错误 (journal): 0

> 💡 安全扫描器探测（58条）已从高频错误分析中排除，这些是自动化漏洞扫描行为，404为正确响应。
- **错误类型数**: 2
- **高频错误（>=3次）**: 1
- **未解决**: 10 / **已解决**: 0

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 67 | /.amplifyrc,/.aws/credentials.bak,/.claude/settings.local.json,/.aws/credenti... |
| test_error | 1 | /test |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| /phpmyadmin | GET | 4 | HTTP_ERROR |
| /wp-admin | GET | 4 | HTTP_ERROR |
| /api/recharge/packages | GET | 2 | HTTP_ERROR |
| /xinpect/api/scan/order | GET | 2 | HTTP_ERROR |
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
| /.pg_service.conf | GET | 1 | HTTP_ERROR |
| /.psqlrc | GET | 1 | HTTP_ERROR |
| /.s3cfg | GET | 1 | HTTP_ERROR |
| /Dockerfile | GET | 1 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-10-12 00:00 | 46 |
| 2026-10-12 01:00 | 1 |
| 2026-10-12 03:00 | 3 |
| 2026-10-12 04:00 | 2 |
| 2026-10-12 05:00 | 1 |
| 2026-10-12 10:00 | 4 |
| 2026-10-12 11:00 | 7 |
| 2026-10-12 16:00 | 2 |
| 2026-10-12 22:00 | 2 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（67次）
涉及端点/服务：/.amplifyrc,/.aws/credentials.bak,/.claude/settings.local.json,/.aws/credentials,/.docker/config.json,/.claude/settings.json,/.boto,/.aws/config,/.git-credentials,/.github/workflows/deploy.yml,/.gitlab-ci.yml,/.gitmodules,/.s3cfg,/Dockerfile,/_profiler/phpinfo,/app.config.js,/app.js,/appsettings.Development.json,/appsettings.Production.json,/appsettings.json,/auth.json,/aws-exports.js,/composer.json,/config.js,/config.json,/config/aws.yml,/config.yaml,/config/config.js,/credentials,/credentials.json,/credentials.ini,/env,/env-config.js,/env.js,/env.txt,/index.js,/phpinfo,/runtime-config.js,/settings.json,/vendor/composer/installed.json,/wp-config.php.bak,/wp-content/debug.log,/my.cnf,/my.ini,/.pg_service.conf,/.psqlrc,/api/health,/xinpect/api/scan/order,/xinpect/api/scan,/wp-admin,/phpmyadmin,/xinpect/api/scan/health,/api/report-error,/api/recharge/packages,/api/credits/balance,/api/payment,/api/recharge,/api/user/credits,/api/order

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 67 |

## ❌ 未解决错误详情（共10条）

### #3181 HTTP_ERROR - /api/credits/balance
- **时间**: 2026-10-12 11:05:50
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #3182 HTTP_ERROR - /api/payment
- **时间**: 2026-10-12 11:05:50
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #3183 HTTP_ERROR - /api/recharge
- **时间**: 2026-10-12 11:05:50
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #3184 HTTP_ERROR - /api/user/credits
- **时间**: 2026-10-12 11:05:50
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #3185 HTTP_ERROR - /api/order
- **时间**: 2026-10-12 11:05:50
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #3180 HTTP_ERROR - /api/recharge/packages
- **时间**: 2026-10-12 11:05:42
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #3179 HTTP_ERROR - /api/recharge/packages
- **时间**: 2026-10-12 11:05:41
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #3178 test_error - /test
- **时间**: 2026-10-12 10:45:20
- **方式**: REPORT
- **状态码**: None
- **消息**: 接口连通性测试
- **堆栈摘要**:
```
test
```
- **来源**: Chrome

### #3177 HTTP_ERROR - /api/report-error
- **时间**: 2026-10-12 10:44:06
- **方式**: POST
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #3168 HTTP_ERROR - /api/health
- **时间**: 2026-10-12 01:06:41
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/7.81.0

## 🛡️ 安全扫描器探测摘要（已排除，共58条）
这些是自动化漏洞扫描工具的探测行为，非真实API错误。

| 探测类型 | 次数 |
|----------|------|
| 其他探测 | 43 |
| 云凭证探测 | 5 |
| Git配置探测 | 4 |
| WordPress扫描探测 | 4 |
| PHP探针 | 2 |
