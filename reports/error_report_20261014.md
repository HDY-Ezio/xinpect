# 每日错误报告
**日期**: 2026-10-14
**生成时间**: 2026-10-15 10:41:14

## 📊 总览
- **总错误数**: 120
  - 🔴 真实API错误: 15
  - 🟡 安全扫描器探测: 105
  - 系统服务错误 (journal): 0

> 💡 安全扫描器探测（105条）已从高频错误分析中排除，这些是自动化漏洞扫描行为，404为正确响应。
- **错误类型数**: 5
- **高频错误（>=3次）**: 3
- **未解决**: 15 / **已解决**: 0

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 107 | /wp-admin,/phpmyadmin,/scan,/upload,/plugins/editors/jce/jce.xml,/media/syste... |
| click_no_response | 6 | https://xinpect.xingwangzhineng.com/register,https://xinpect.xingwangzhineng.... |
| UndefinedError | 5 | /dashboard/credits |
| api_error | 1 | https://xinpect.xingwangzhineng.com/dashboard/thresholds |
| UnboundLocalError | 1 | /api/thresholds |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| /upload | GET | 50 | HTTP_ERROR |
| /dashboard/credits | GET | 10 | UndefinedError,HTTP_ERROR |
| /api | GET | 8 | HTTP_ERROR |
| /api/health | GET | 4 | HTTP_ERROR |
| /phpmyadmin | GET | 4 | HTTP_ERROR |
| /this-page-does-not-exist-12345 | GET | 4 | HTTP_ERROR |
| /wp-admin | GET | 4 | HTTP_ERROR |
| https://xinpect.xingwangzhineng.com/register | REPORT | 4 | click_no_response |
| /nonexistent-page | GET | 3 | HTTP_ERROR |
| /about | GET | 2 | HTTP_ERROR |
| /api-docs | GET | 2 | HTTP_ERROR |
| /api/thresholds | POST | 2 | UnboundLocalError,HTTP_ERROR |
| /contact | GET | 2 | HTTP_ERROR |
| /features | GET | 2 | HTTP_ERROR |
| /help/api | GET | 2 | HTTP_ERROR |
| /product | GET | 2 | HTTP_ERROR |
| /support | GET | 2 | HTTP_ERROR |
| https://xinpect.xingwangzhineng.com/login | REPORT | 2 | click_no_response |
| /api/ci/config | POST | 1 | HTTP_ERROR |
| /api/dashboard/credits | GET | 1 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-10-14 04:00 | 2 |
| 2026-10-14 10:00 | 3 |
| 2026-10-14 12:00 | 1 |
| 2026-10-14 13:00 | 4 |
| 2026-10-14 16:00 | 2 |
| 2026-10-14 17:00 | 11 |
| 2026-10-14 18:00 | 5 |
| 2026-10-14 19:00 | 27 |
| 2026-10-14 21:00 | 1 |
| 2026-10-14 22:00 | 64 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（107次）
涉及端点/服务：/wp-admin,/phpmyadmin,/scan,/upload,/plugins/editors/jce/jce.xml,/media/system/js/core.js,/media/jui/js/bootstrap.min.js,/media/vendor/jquery/js/jquery.min.js,/api/ci/config,/api/thresholds,/dashboard/credits,/api/dashboard/credits,/api-docs,/docs,/api,/help/api,/contact,/about,/support,/product,/features,/nonexistent-page,/pdf,/this-page-does-not-exist-12345,/api/health

### click_no_response（6次）
涉及端点/服务：https://xinpect.xingwangzhineng.com/register,https://xinpect.xingwangzhineng.com/login

### UndefinedError（5次）
涉及端点/服务：/dashboard/credits

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 113 |

## ❌ 未解决错误详情（共15条）

### #3405 click_no_response - https://xinpect.xingwangzhineng.com/login
- **时间**: 2026-10-14 22:26:34
- **方式**: REPORT
- **状态码**: None
- **消息**: 点击元素无响应: BUTTON "登录"
- **来源**: Chrome / Linux x86_64

### #3400 HTTP_ERROR - /api/health
- **时间**: 2026-10-14 22:25:42
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/145.0.7632.6 S

### #3392 click_no_response - https://xinpect.xingwangzhineng.com/register
- **时间**: 2026-10-14 22:25:16
- **方式**: REPORT
- **状态码**: None
- **消息**: 点击元素无响应: BUTTON "注册"
- **来源**: Chrome / Linux x86_64

### #3388 click_no_response - https://xinpect.xingwangzhineng.com/login
- **时间**: 2026-10-14 22:23:49
- **方式**: REPORT
- **状态码**: None
- **消息**: 点击元素无响应: BUTTON "登录"
- **来源**: Chrome / Linux x86_64

### #3383 HTTP_ERROR - /api/health
- **时间**: 2026-10-14 22:22:56
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/145.0.7632.6 S

### #3375 click_no_response - https://xinpect.xingwangzhineng.com/register
- **时间**: 2026-10-14 22:21:41
- **方式**: REPORT
- **状态码**: None
- **消息**: 点击元素无响应: BUTTON "注册"
- **来源**: Chrome / Linux x86_64

### #3370 HTTP_ERROR - /api/health
- **时间**: 2026-10-14 22:20:37
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/145.0.7632.6 S

### #3362 click_no_response - https://xinpect.xingwangzhineng.com/register
- **时间**: 2026-10-14 22:19:23
- **方式**: REPORT
- **状态码**: None
- **消息**: 点击元素无响应: BUTTON "注册"
- **来源**: Chrome / Linux x86_64

### #3357 HTTP_ERROR - /api/health
- **时间**: 2026-10-14 22:18:05
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/145.0.7632.6 S

### #3348 click_no_response - https://xinpect.xingwangzhineng.com/register
- **时间**: 2026-10-14 22:16:46
- **方式**: REPORT
- **状态码**: None
- **消息**: 点击元素无响应: BUTTON "注册"
- **来源**: Chrome / Linux x86_64

### #3312 HTTP_ERROR - /api/dashboard/credits
- **时间**: 2026-10-14 18:22:34
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.

### #3303 UnboundLocalError - /api/thresholds
- **时间**: 2026-10-14 17:08:11
- **方式**: POST
- **状态码**: 500
- **消息**: cannot access local variable 'cleaned' where it is not associated with a value
- **堆栈摘要**:
```
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/xinpect-website/modules/scan.py", line 1322, in api_save_thresholds
    cleaned['_disabled_rules'] = [r for r in disabled_rules if isinstance(r, str) and len(r) < 100][:50]
    ^^^^^^^
UnboundLocalError: cannot access local variable 'cleaned' where it is not associated with a value
```
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.3

### #3304 HTTP_ERROR - /api/thresholds
- **时间**: 2026-10-14 17:08:11
- **方式**: POST
- **状态码**: 500
- **消息**: HTTP 500
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.3

### #3305 api_error - https://xinpect.xingwangzhineng.com/dashboard/thresholds
- **时间**: 2026-10-14 17:08:11
- **方式**: REPORT
- **状态码**: None
- **消息**: API请求失败 [500]: /api/thresholds
- **堆栈摘要**:
```
Status: 500 INTERNAL SERVER ERROR
```
- **来源**: Chrome / Linux x86_64

### #3302 HTTP_ERROR - /api/ci/config
- **时间**: 2026-10-14 17:06:24
- **方式**: POST
- **状态码**: 401
- **消息**: HTTP 401
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.3

## 🛡️ 安全扫描器探测摘要（已排除，共105条）
这些是自动化漏洞扫描工具的探测行为，非真实API错误。

| 探测类型 | 次数 |
|----------|------|
| 其他探测 | 101 |
| WordPress扫描探测 | 4 |
