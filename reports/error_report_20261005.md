# 每日错误报告
**日期**: 2026-10-05
**生成时间**: 2026-10-06 10:40:36

## 📊 总览
- **总错误数**: 56
  - 🔴 真实API错误: 45
  - 🟡 安全扫描器探测: 11
  - 系统服务错误 (journal): 0

> 💡 安全扫描器探测（11条）已从高频错误分析中排除，这些是自动化漏洞扫描行为，404为正确响应。
- **错误类型数**: 1
- **高频错误（>=3次）**: 1
- **未解决**: 45 / **已解决**: 0

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 56 | /wp-admin,/phpmyadmin,/.amplifyrc,/appsettings.Production.json,/appsettings.D... |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| /phpmyadmin | GET | 4 | HTTP_ERROR |
| /wp-admin | GET | 4 | HTTP_ERROR |
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
| /.s3cfg | GET | 1 | HTTP_ERROR |
| /.secrets | GET | 1 | HTTP_ERROR |
| /.secrets.json | GET | 1 | HTTP_ERROR |
| /.secrets.yml | GET | 1 | HTTP_ERROR |
| /Dockerfile | GET | 1 | HTTP_ERROR |
| /_profiler/phpinfo | GET | 1 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-10-05 04:00 | 2 |
| 2026-10-05 10:00 | 2 |
| 2026-10-05 16:00 | 2 |
| 2026-10-05 18:00 | 48 |
| 2026-10-05 22:00 | 2 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（56次）
涉及端点/服务：/wp-admin,/phpmyadmin,/.amplifyrc,/appsettings.Production.json,/appsettings.Development.json,/auth.json,/.aws/config,/app.js,/appsettings.json,/.aws/credentials,/aws-exports.js,/.aws/credentials.bak,/.boto,/.claude/settings.json,/.claude/settings.local.json,/composer.json,/config/aws.yml,/config/config.js,/config.js,/config.json,/config.yaml,/credentials,/credentials.ini,/credentials.json,/.docker/config.json,/Dockerfile,/env,/env-config.js,/env.js,/env.txt,/.git-credentials,/.github/workflows/deploy.yml,/.gitlab-ci.yml,/.gitmodules,/index.js,/phpinfo,/_profiler/phpinfo,/runtime-config.js,/.s3cfg,/settings.json,/vendor/composer/installed.json,/wp-config.php.bak,/wp-content/debug.log,/secrets.ini,/.secrets,/secrets.properties,/secret.yml,/.secrets.yml,/.secrets.json,/secret.json

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 56 |

## ❌ 未解决错误详情（共45条）

### #2350 HTTP_ERROR - /.secrets
- **时间**: 2026-10-05 18:36:29
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

### #2351 HTTP_ERROR - /secrets.properties
- **时间**: 2026-10-05 18:36:29
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

### #2352 HTTP_ERROR - /secret.yml
- **时间**: 2026-10-05 18:36:29
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

### #2353 HTTP_ERROR - /.secrets.yml
- **时间**: 2026-10-05 18:36:29
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

### #2354 HTTP_ERROR - /.secrets.json
- **时间**: 2026-10-05 18:36:29
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

### #2355 HTTP_ERROR - /secret.json
- **时间**: 2026-10-05 18:36:29
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

### #2335 HTTP_ERROR - /env.txt
- **时间**: 2026-10-05 18:36:28
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

### #2336 HTTP_ERROR - /.git-credentials
- **时间**: 2026-10-05 18:36:28
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

### #2337 HTTP_ERROR - /.github/workflows/deploy.yml
- **时间**: 2026-10-05 18:36:28
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

### #2338 HTTP_ERROR - /.gitlab-ci.yml
- **时间**: 2026-10-05 18:36:28
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

### #2339 HTTP_ERROR - /.gitmodules
- **时间**: 2026-10-05 18:36:28
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

### #2340 HTTP_ERROR - /index.js
- **时间**: 2026-10-05 18:36:28
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

### #2343 HTTP_ERROR - /runtime-config.js
- **时间**: 2026-10-05 18:36:28
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

### #2344 HTTP_ERROR - /.s3cfg
- **时间**: 2026-10-05 18:36:28
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

### #2345 HTTP_ERROR - /settings.json
- **时间**: 2026-10-05 18:36:28
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

### #2346 HTTP_ERROR - /vendor/composer/installed.json
- **时间**: 2026-10-05 18:36:28
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

### #2347 HTTP_ERROR - /wp-config.php.bak
- **时间**: 2026-10-05 18:36:28
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

### #2348 HTTP_ERROR - /wp-content/debug.log
- **时间**: 2026-10-05 18:36:28
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

### #2349 HTTP_ERROR - /secrets.ini
- **时间**: 2026-10-05 18:36:28
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

### #2309 HTTP_ERROR - /appsettings.Production.json
- **时间**: 2026-10-05 18:36:27
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

...还有 25 条未解决错误

## 🛡️ 安全扫描器探测摘要（已排除，共11条）
这些是自动化漏洞扫描工具的探测行为，非真实API错误。

| 探测类型 | 次数 |
|----------|------|
| WordPress扫描探测 | 4 |
| 其他探测 | 4 |
| PHP探针 | 2 |
| 云凭证探测 | 1 |
