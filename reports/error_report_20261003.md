# 每日错误报告
**日期**: 2026-10-03
**生成时间**: 2026-10-04 10:40:33

## 📊 总览
- **总错误数**: 97
  - 🔴 真实API错误: 81
  - 🟡 安全扫描器探测: 16
  - 系统服务错误 (journal): 0

> 💡 安全扫描器探测（16条）已从高频错误分析中排除，这些是自动化漏洞扫描行为，404为正确响应。
- **错误类型数**: 1
- **高频错误（>=3次）**: 1
- **未解决**: 80 / **已解决**: 1

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 97 | /api/v1/scan,/wp-admin,/phpmyadmin,/wp-config.php.bak,/vendor/composer/instal... |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| /phpmyadmin | GET | 4 | HTTP_ERROR |
| /wp-admin | GET | 4 | HTTP_ERROR |
| /.amplifyrc | GET | 2 | HTTP_ERROR |
| /.anthropic/config.json | GET | 2 | HTTP_ERROR |
| /.aws/config | GET | 2 | HTTP_ERROR |
| /.aws/credentials | GET | 2 | HTTP_ERROR |
| /.aws/credentials.bak | GET | 2 | HTTP_ERROR |
| /.boto | GET | 2 | HTTP_ERROR |
| /.claude/settings.json | GET | 2 | HTTP_ERROR |
| /.claude/settings.local.json | GET | 2 | HTTP_ERROR |
| /.config/gcloud/application_default_credentials.json | GET | 2 | HTTP_ERROR |
| /.docker/config.json | GET | 2 | HTTP_ERROR |
| /.docker/secrets.json | GET | 2 | HTTP_ERROR |
| /.git-credentials | GET | 2 | HTTP_ERROR |
| /.github/workflows/deploy.yml | GET | 2 | HTTP_ERROR |
| /.gitlab-ci.yml | GET | 2 | HTTP_ERROR |
| /.gitmodules | GET | 2 | HTTP_ERROR |
| /.s3cfg | GET | 2 | HTTP_ERROR |
| /Dockerfile | GET | 2 | HTTP_ERROR |
| /_profiler/phpinfo | GET | 2 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-10-03 02:00 | 1 |
| 2026-10-03 04:00 | 2 |
| 2026-10-03 06:00 | 44 |
| 2026-10-03 07:00 | 44 |
| 2026-10-03 10:00 | 2 |
| 2026-10-03 16:00 | 2 |
| 2026-10-03 22:00 | 2 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（97次）
涉及端点/服务：/api/v1/scan,/wp-admin,/phpmyadmin,/wp-config.php.bak,/vendor/composer/installed.json,/settings.json,/wp-content/debug.log,/phpinfo,/index.js,/env.js,/env-config.js,/env,/credentials.json,/credentials.ini,/credentials,/runtime-config.js,/config/config.js,/config/aws.yml,/config.yaml,/config.json,/composer.json,/aws-exports.js,/auth.json,/appsettings.json,/appsettings.Production.json,/appsettings.Development.json,/env.txt,/app.js,/_profiler/phpinfo,/Dockerfile,/.gitmodules,/.gitlab-ci.yml,/.git-credentials,/config.js,/.docker/secrets.json,/.docker/config.json,/.s3cfg,/.github/workflows/deploy.yml,/.config/gcloud/application_default_credentials.json,/.claude/settings.local.json,/.claude/settings.json,/.aws/credentials.bak,/.boto,/.aws/config,/.anthropic/config.json,/.amplifyrc,/.aws/credentials

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 97 |

## ❌ 未解决错误详情（共80条）

### #2267 HTTP_ERROR - /appsettings.Production.json
- **时间**: 2026-10-03 07:27:12
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

### #2268 HTTP_ERROR - /.docker/secrets.json
- **时间**: 2026-10-03 07:27:12
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

### #2269 HTTP_ERROR - /.docker/config.json
- **时间**: 2026-10-03 07:27:12
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

### #2271 HTTP_ERROR - /.claude/settings.local.json
- **时间**: 2026-10-03 07:27:12
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

### #2272 HTTP_ERROR - /.claude/settings.json
- **时间**: 2026-10-03 07:27:12
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

### #2273 HTTP_ERROR - /.boto
- **时间**: 2026-10-03 07:27:12
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

### #2274 HTTP_ERROR - /.aws/credentials.bak
- **时间**: 2026-10-03 07:27:12
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

### #2275 HTTP_ERROR - /.aws/credentials
- **时间**: 2026-10-03 07:27:12
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

### #2276 HTTP_ERROR - /.aws/config
- **时间**: 2026-10-03 07:27:12
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

### #2277 HTTP_ERROR - /.anthropic/config.json
- **时间**: 2026-10-03 07:27:12
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

### #2278 HTTP_ERROR - /.amplifyrc
- **时间**: 2026-10-03 07:27:12
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

### #2245 HTTP_ERROR - /credentials.ini
- **时间**: 2026-10-03 07:27:11
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

### #2246 HTTP_ERROR - /credentials
- **时间**: 2026-10-03 07:27:11
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

### #2247 HTTP_ERROR - /config/aws.yml
- **时间**: 2026-10-03 07:27:11
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

### #2248 HTTP_ERROR - /config/config.js
- **时间**: 2026-10-03 07:27:11
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

### #2249 HTTP_ERROR - /config.yaml
- **时间**: 2026-10-03 07:27:11
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

### #2250 HTTP_ERROR - /config.json
- **时间**: 2026-10-03 07:27:11
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

### #2251 HTTP_ERROR - /config.js
- **时间**: 2026-10-03 07:27:11
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

### #2253 HTTP_ERROR - /composer.json
- **时间**: 2026-10-03 07:27:11
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

### #2254 HTTP_ERROR - /aws-exports.js
- **时间**: 2026-10-03 07:27:11
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

...还有 60 条未解决错误

## 🛡️ 安全扫描器探测摘要（已排除，共16条）
这些是自动化漏洞扫描工具的探测行为，非真实API错误。

| 探测类型 | 次数 |
|----------|------|
| WordPress扫描探测 | 4 |
| 其他探测 | 4 |
| PHP探针 | 4 |
| 云凭证探测 | 4 |
