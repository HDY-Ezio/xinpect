# 每日错误报告
**日期**: 2026-10-19
**生成时间**: 2026-10-20 10:28:58

## 📊 总览
- **总错误数**: 201
  - 🔴 真实API错误: 91
  - 🟡 安全扫描器探测: 110
  - 系统服务错误 (journal): 0

> 💡 安全扫描器探测（110条）已从高频错误分析中排除，这些是自动化漏洞扫描行为，404为正确响应。
- **错误类型数**: 6
- **高频错误（>=3次）**: 4
- **未解决**: 91 / **已解决**: 0

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 146 | /api/session/properties,/wp-admin,/phpmyadmin,/report.html,/dashboard.html,/a... |
| click_no_response | 46 | https://xinpect.xingwangzhineng.com/dashboard/scans,https://xinpect.xingwangz... |
| promise_error | 3 | https://xinpect.xingwangzhineng.com/dashboard/gates |
| MethodNotAllowed | 3 | /scan,/api/admin/license/create |
| OperationalError | 2 | /api/admin/licenses |
| network_error | 1 | https://xinpect.xingwangzhineng.com/dashboard/scans |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| https://xinpect.xingwangzhineng.com/dashboard/scans | REPORT | 25 | network_error,click_no_response |
| https://xinpect.xingwangzhineng.com/dashboard/gates | REPORT | 9 | promise_error,click_no_response |
| /api/v1/scan | POST | 6 | HTTP_ERROR |
| https://xinpect.xingwangzhineng.com/dashboard | REPORT | 6 | click_no_response |
| https://xinpect.xingwangzhineng.com/dashboard/overview | REPORT | 6 | click_no_response |
| /blog/ | GET | 5 | HTTP_ERROR |
| /site/ | GET | 5 | HTTP_ERROR |
| /api/admin/licenses | GET | 4 | OperationalError,HTTP_ERROR |
| /api/session/properties | GET | 4 | HTTP_ERROR |
| /cms/ | GET | 4 | HTTP_ERROR |
| /news/ | GET | 4 | HTTP_ERROR |
| /phpmyadmin | GET | 4 | HTTP_ERROR |
| /press/ | GET | 4 | HTTP_ERROR |
| /scan | GET | 4 | MethodNotAllowed,HTTP_ERROR |
| /wp-admin | GET | 4 | HTTP_ERROR |
| /api/admin/monitoring | GET | 3 | HTTP_ERROR |
| /report.html | GET | 3 | HTTP_ERROR |
| /admin | GET | 2 | HTTP_ERROR |
| /api/admin/license/create | GET | 2 | MethodNotAllowed,HTTP_ERROR |
| /api/gates | GET | 2 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-10-19 01:00 | 8 |
| 2026-10-19 03:00 | 2 |
| 2026-10-19 04:00 | 19 |
| 2026-10-19 05:00 | 6 |
| 2026-10-19 06:00 | 11 |
| 2026-10-19 08:00 | 6 |
| 2026-10-19 09:00 | 7 |
| 2026-10-19 10:00 | 6 |
| 2026-10-19 13:00 | 3 |
| 2026-10-19 14:00 | 97 |
| 2026-10-19 15:00 | 1 |
| 2026-10-19 16:00 | 15 |
| 2026-10-19 19:00 | 4 |
| 2026-10-19 20:00 | 12 |
| 2026-10-19 21:00 | 2 |
| 2026-10-19 22:00 | 2 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（146次）
涉及端点/服务：/api/session/properties,/wp-admin,/phpmyadmin,/report.html,/dashboard.html,/audit,/scan,/my-detections,/api/v1/scan,/upload,/api/,/healthz,/blog/,/site/,/news/,/cms/,/press/,/report/<script>alert('xss')</script>,/nonexistent_page_12345,/api/scan/status/nonexistent_scan_id_12345,/api/scan/estimate,/api/thresholds,/api/gates,/api/trends,/api/user/onboarding/status,/etc/passwd,/modules/constants.py,/api/admin/monitoring,/api/admin/platform-stats,/api/admin/announcements,/.amplifyrc,/.docker/config.json,/.aws/credentials,/.aws/config,/.aws/credentials.bak,/.boto,/.claude/settings.local.json,/.claude/settings.json,/.git-credentials,/.github/workflows/deploy.yml,/Dockerfile,/_profiler/phpinfo,/app.config.js,/app.js,/appsettings.Development.json,/auth.json,/appsettings.json,/.gitmodules,/composer.json,/.s3cfg,/config.js,/.gitlab-ci.yml,/config.json,/config.yaml,/config/aws.yml,/config/config.js,/credentials,/appsettings.Production.json,/credentials.ini,/credentials.json,/env.js,/env,/env.txt,/index.js,/env-config.js,/phpinfo,/runtime-config.js,/settings.json,/aws-exports.js,/vendor/composer/installed.json,/pythonanywhere.json,/sandbox.json,/coder.json,/wp-config.php.bak,/wp-content/debug.log,/replit.nix,/api/report-error,/api,/api/health,/admin,/package.json,/server-status,/api/scan/submit,/report/share/abc,/login,/report/d24f02d6598575ec02df3db72f99369d,/api/scan/status/d24f02d6598575ec02df3db72f99369d,/report/share/xyz,/history,/这是网站账号：hdyabcd@163.com密码：1234q5q6,/api/admin/licenses,/api/admin/users,/api/admin/license/create,/api/scan/status/c0966157595442cf842649ae521e52ba,/report/c0966157595442cf842649ae521e52ba,/report/de1a2770c48a98bd484ddf9ba381d0a7

### click_no_response（46次）
涉及端点/服务：https://xinpect.xingwangzhineng.com/dashboard/scans,https://xinpect.xingwangzhineng.com/dashboard/gates,https://xinpect.xingwangzhineng.com/dashboard/alerts,https://xinpect.xingwangzhineng.com/dashboard/thresholds,https://xinpect.xingwangzhineng.com/dashboard/overview,https://xinpect.xingwangzhineng.com/dashboard,https://xinpect.xingwangzhineng.com/dashboard/api-keys

### promise_error（3次）
涉及端点/服务：https://xinpect.xingwangzhineng.com/dashboard/gates

### MethodNotAllowed（3次）
涉及端点/服务：/scan,/api/admin/license/create

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 151 |

## ❌ 未解决错误详情（共91条）

### #4393 HTTP_ERROR - /api/session/properties
- **时间**: 2026-10-19 21:31:51
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: metabase-cve-2026-72898-detect/1.0 (benign detection probes only)

### #4392 HTTP_ERROR - /api/session/properties
- **时间**: 2026-10-19 21:31:51
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: metabase-cve-2026-72898-detect/1.0 (benign detection probes only)

### #4389 HTTP_ERROR - /api/scan/status/c0966157595442cf842649ae521e52ba
- **时间**: 2026-10-19 20:23:19
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/8.21.0

### #4388 HTTP_ERROR - /api/admin/license/create
- **时间**: 2026-10-19 20:20:58
- **方式**: GET
- **状态码**: 405
- **消息**: HTTP 405
- **IP**: 127.0.0.1
- **来源**: curl/8.21.0

### #4387 MethodNotAllowed - /api/admin/license/create
- **时间**: 2026-10-19 20:20:58
- **方式**: GET
- **状态码**: 405
- **消息**: 405 Method Not Allowed: The method is not allowed for the requested URL.
- **堆栈摘要**:
```
    result = self.url_adapter.match(return_rule=True)  # type: ignore
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/ubuntu/.local/lib/python3.12/site-packages/werkzeug/routing/map.py", line 624, in match
    raise MethodNotAllowed(valid_methods=list(e.have_match_for)) from None
werkzeug.exceptions.MethodNotAllowed: 405 Method Not Allowed: The method is not allowed for the requested URL.
```
- **IP**: 127.0.0.1
- **来源**: curl/8.21.0

### #4386 HTTP_ERROR - /api/admin/licenses
- **时间**: 2026-10-19 20:20:57
- **方式**: GET
- **状态码**: 500
- **消息**: HTTP 500
- **IP**: 127.0.0.1
- **来源**: curl/8.21.0

### #4385 OperationalError - /api/admin/licenses
- **时间**: 2026-10-19 20:20:57
- **方式**: GET
- **状态码**: 500
- **消息**: no such column: is_admin
- **堆栈摘要**:
```
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/xinpect-website/modules/license.py", line 216, in admin_list_licenses
    user = db.execute("SELECT is_admin FROM users WHERE id=?", (user_id,)).fetchone()
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
sqlite3.OperationalError: no such column: is_admin
```
- **IP**: 127.0.0.1
- **来源**: curl/8.21.0

### #4384 HTTP_ERROR - /api/admin/users
- **时间**: 2026-10-19 20:20:31
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/8.21.0

### #4382 HTTP_ERROR - /api/admin/licenses
- **时间**: 2026-10-19 20:20:30
- **方式**: GET
- **状态码**: 500
- **消息**: HTTP 500
- **IP**: 127.0.0.1
- **来源**: curl/8.21.0

### #4381 OperationalError - /api/admin/licenses
- **时间**: 2026-10-19 20:20:30
- **方式**: GET
- **状态码**: 500
- **消息**: no such column: is_admin
- **堆栈摘要**:
```
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/xinpect-website/modules/license.py", line 216, in admin_list_licenses
    user = db.execute("SELECT is_admin FROM users WHERE id=?", (user_id,)).fetchone()
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
sqlite3.OperationalError: no such column: is_admin
```
- **IP**: 127.0.0.1
- **来源**: curl/8.21.0

### #4374 HTTP_ERROR - /api/scan/status/d24f02d6598575ec02df3db72f99369d
- **时间**: 2026-10-19 16:50:57
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/8.21.0

### #4369 HTTP_ERROR - /api/scan/submit
- **时间**: 2026-10-19 16:36:48
- **方式**: POST
- **状态码**: 400
- **消息**: HTTP 400
- **IP**: 127.0.0.1
- **来源**: curl/8.21.0

### #4365 HTTP_ERROR - /api/health
- **时间**: 2026-10-19 16:31:37
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/8.21.0

### #4363 HTTP_ERROR - /api/report-error
- **时间**: 2026-10-19 16:20:54
- **方式**: POST
- **状态码**: 400
- **消息**: HTTP 400
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #4360 HTTP_ERROR - /api/v1/scan
- **时间**: 2026-10-19 15:39:46
- **方式**: POST
- **状态码**: 403
- **消息**: HTTP 403
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #4311 HTTP_ERROR - /api/user/onboarding/status
- **时间**: 2026-10-19 14:48:41
- **方式**: GET
- **状态码**: 401
- **消息**: HTTP 401
- **IP**: 127.0.0.1
- **来源**: python-requests/2.34.2

### #4310 HTTP_ERROR - /api/trends
- **时间**: 2026-10-19 14:48:41
- **方式**: GET
- **状态码**: 401
- **消息**: HTTP 401
- **IP**: 127.0.0.1
- **来源**: python-requests/2.34.2

### #4309 HTTP_ERROR - /api/gates
- **时间**: 2026-10-19 14:48:41
- **方式**: GET
- **状态码**: 401
- **消息**: HTTP 401
- **IP**: 127.0.0.1
- **来源**: python-requests/2.34.2

### #4308 HTTP_ERROR - /api/thresholds
- **时间**: 2026-10-19 14:48:41
- **方式**: GET
- **状态码**: 401
- **消息**: HTTP 401
- **IP**: 127.0.0.1
- **来源**: python-requests/2.34.2

### #4307 HTTP_ERROR - /api/scan/estimate
- **时间**: 2026-10-19 14:48:41
- **方式**: POST
- **状态码**: 403
- **消息**: HTTP 403
- **IP**: 127.0.0.1
- **来源**: python-requests/2.34.2

...还有 71 条未解决错误

## 🛡️ 安全扫描器探测摘要（已排除，共110条）
这些是自动化漏洞扫描工具的探测行为，非真实API错误。

| 探测类型 | 次数 |
|----------|------|
| 其他探测 | 95 |
| 云凭证探测 | 5 |
| WordPress扫描探测 | 4 |
| Git配置探测 | 4 |
| PHP探针 | 2 |
