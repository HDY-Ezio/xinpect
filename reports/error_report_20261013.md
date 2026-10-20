# 每日错误报告
**日期**: 2026-10-13
**生成时间**: 2026-10-14 10:43:02

## 📊 总览
- **总错误数**: 99
  - 🔴 真实API错误: 33
  - 🟡 安全扫描器探测: 66
  - 系统服务错误 (journal): 0

> 💡 安全扫描器探测（66条）已从高频错误分析中排除，这些是自动化漏洞扫描行为，404为正确响应。
- **错误类型数**: 4
- **高频错误（>=3次）**: 3
- **未解决**: 33 / **已解决**: 0

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 70 | /api/health,/wp-admin,/phpmyadmin,/api/recharge/packages,/health,/debug/defau... |
| click_no_response | 16 | https://xinpect.xingwangzhineng.com/dashboard/api-keys,https://xinpect.xingwa... |
| js_error | 11 | https://xinpect.xingwangzhineng.com/dashboard/ci-setup |
| NameError | 2 | /api/recharge/packages |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| https://xinpect.xingwangzhineng.com/dashboard/ci-setup | REPORT | 21 | click_no_response,js_error |
| /api/recharge/packages | GET | 4 | NameError,HTTP_ERROR |
| /phpmyadmin | GET | 4 | HTTP_ERROR |
| /wp-admin | GET | 4 | HTTP_ERROR |
| /upload | GET | 3 | HTTP_ERROR |
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
| /Dockerfile | GET | 1 | HTTP_ERROR |
| /_ignition/execute-solution | GET | 1 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-10-13 01:00 | 1 |
| 2026-10-13 04:00 | 2 |
| 2026-10-13 05:00 | 7 |
| 2026-10-13 06:00 | 7 |
| 2026-10-13 07:00 | 16 |
| 2026-10-13 09:00 | 10 |
| 2026-10-13 10:00 | 50 |
| 2026-10-13 11:00 | 1 |
| 2026-10-13 16:00 | 2 |
| 2026-10-13 18:00 | 1 |
| 2026-10-13 22:00 | 2 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（70次）
涉及端点/服务：/api/health,/wp-admin,/phpmyadmin,/api/recharge/packages,/health,/debug/default/index,/demo,/vendor/laravel-filemanager/js/script.js,/blog,/new,/public/vendor/laravel-filemanager/js/script.js,/_ignition/execute-solution,/upload,/.amplifyrc,/.aws/credentials,/.claude/settings.json,/.aws/credentials.bak,/.claude/settings.local.json,/.docker/config.json,/.boto,/.aws/config,/.git-credentials,/.github/workflows/deploy.yml,/.gitlab-ci.yml,/.gitmodules,/.s3cfg,/Dockerfile,/_profiler/phpinfo,/app.config.js,/app.js,/appsettings.Development.json,/appsettings.Production.json,/appsettings.json,/auth.json,/aws-exports.js,/composer.json,/config.js,/config/aws.yml,/config/config.js,/credentials,/credentials.ini,/credentials.json,/env,/env.js,/env-config.js,/env.txt,/config.json,/index.js,/config.yaml,/phpinfo,/runtime-config.js,/settings.json,/vendor/composer/installed.json,/wp-config.php.bak,/wp-content/debug.log,/config/environments/environment.ts,/next.config.ts,/nuxt.config.mjs,/gatsby-config.js,/angular.json,/svelte.config.ts

### click_no_response（16次）
涉及端点/服务：https://xinpect.xingwangzhineng.com/dashboard/api-keys,https://xinpect.xingwangzhineng.com/dashboard/benchmark,https://xinpect.xingwangzhineng.com/dashboard/versions,https://xinpect.xingwangzhineng.com/dashboard/ci-setup,https://xinpect.xingwangzhineng.com/dashboard,https://xinpect.xingwangzhineng.com/dashboard/overview,https://xinpect.xingwangzhineng.com/dashboard/scans

### js_error（11次）
涉及端点/服务：https://xinpect.xingwangzhineng.com/dashboard/ci-setup

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 72 |

## ❌ 未解决错误详情（共33条）

### #3224 click_no_response - https://xinpect.xingwangzhineng.com/dashboard/scans
- **时间**: 2026-10-13 09:10:39
- **方式**: REPORT
- **状态码**: None
- **消息**: 点击元素无响应: BUTTON "对比"
- **来源**: Chrome / Win32

### #3223 click_no_response - https://xinpect.xingwangzhineng.com/dashboard/overview
- **时间**: 2026-10-13 09:10:21
- **方式**: REPORT
- **状态码**: None
- **消息**: 点击元素无响应: BUTTON#btn-30d "30天"
- **来源**: Chrome / Win32

### #3222 click_no_response - https://xinpect.xingwangzhineng.com/dashboard/ci-setup
- **时间**: 2026-10-13 07:48:25
- **方式**: REPORT
- **状态码**: None
- **消息**: 点击元素无响应: DIV "🆓
                    免费扫描
  "
- **来源**: Chrome / Win32

### #3221 click_no_response - https://xinpect.xingwangzhineng.com/dashboard/ci-setup
- **时间**: 2026-10-13 07:46:10
- **方式**: REPORT
- **状态码**: None
- **消息**: 点击元素无响应: DIV "🔬
                    深度扫描
  "
- **来源**: Chrome / Win32

### #3220 js_error - https://xinpect.xingwangzhineng.com/dashboard/ci-setup
- **时间**: 2026-10-13 07:46:05
- **方式**: REPORT
- **状态码**: None
- **消息**: Uncaught ReferenceError: selectMode is not defined at https://xinpect.xingwangzhineng.com/dashboard/ci-setup:670
- **堆栈摘要**:
```
ReferenceError: selectMode is not defined
    at HTMLDivElement.onclick (https://xinpect.xingwangzhineng.com/dashboard/ci-setup:670:86)
```
- **来源**: Chrome / Win32

### #3219 click_no_response - https://xinpect.xingwangzhineng.com/dashboard
- **时间**: 2026-10-13 07:45:59
- **方式**: REPORT
- **状态码**: None
- **消息**: 点击元素无响应: DIV "🔌
                    开发集成
  "
- **来源**: Chrome / Win32

### #3218 click_no_response - https://xinpect.xingwangzhineng.com/dashboard/ci-setup
- **时间**: 2026-10-13 07:45:33
- **方式**: REPORT
- **状态码**: None
- **消息**: 点击元素无响应: DIV "🔬
                    深度扫描
  "
- **来源**: Chrome / Win32

### #3217 js_error - https://xinpect.xingwangzhineng.com/dashboard/ci-setup
- **时间**: 2026-10-13 07:45:31
- **方式**: REPORT
- **状态码**: None
- **消息**: Uncaught ReferenceError: updateThreshold is not defined at https://xinpect.xingwangzhineng.com/dashboard/ci-setup:707
- **堆栈摘要**:
```
ReferenceError: updateThreshold is not defined
    at HTMLInputElement.oninput (https://xinpect.xingwangzhineng.com/dashboard/ci-setup:707:150)
```
- **来源**: Chrome / Win32

### #3216 js_error - https://xinpect.xingwangzhineng.com/dashboard/ci-setup
- **时间**: 2026-10-13 07:45:27
- **方式**: REPORT
- **状态码**: None
- **消息**: Uncaught ReferenceError: selectMode is not defined at https://xinpect.xingwangzhineng.com/dashboard/ci-setup:670
- **堆栈摘要**:
```
ReferenceError: selectMode is not defined
    at HTMLDivElement.onclick (https://xinpect.xingwangzhineng.com/dashboard/ci-setup:670:86)
```
- **来源**: Chrome / Win32

### #3215 click_no_response - https://xinpect.xingwangzhineng.com/dashboard/ci-setup
- **时间**: 2026-10-13 07:45:22
- **方式**: REPORT
- **状态码**: None
- **消息**: 点击元素无响应: DIV "🔬
                    深度扫描
  "
- **来源**: Chrome / Win32

### #3214 js_error - https://xinpect.xingwangzhineng.com/dashboard/ci-setup
- **时间**: 2026-10-13 07:45:19
- **方式**: REPORT
- **状态码**: None
- **消息**: Uncaught ReferenceError: updateThreshold is not defined at https://xinpect.xingwangzhineng.com/dashboard/ci-setup:707
- **堆栈摘要**:
```
ReferenceError: updateThreshold is not defined
    at HTMLInputElement.oninput (https://xinpect.xingwangzhineng.com/dashboard/ci-setup:707:150)
```
- **来源**: Chrome / Win32

### #3213 js_error - https://xinpect.xingwangzhineng.com/dashboard/ci-setup
- **时间**: 2026-10-13 07:45:16
- **方式**: REPORT
- **状态码**: None
- **消息**: Uncaught ReferenceError: selectMode is not defined at https://xinpect.xingwangzhineng.com/dashboard/ci-setup:670
- **堆栈摘要**:
```
ReferenceError: selectMode is not defined
    at HTMLDivElement.onclick (https://xinpect.xingwangzhineng.com/dashboard/ci-setup:670:86)
```
- **来源**: Chrome / Win32

### #3212 click_no_response - https://xinpect.xingwangzhineng.com/dashboard/ci-setup
- **时间**: 2026-10-13 07:42:19
- **方式**: REPORT
- **状态码**: None
- **消息**: 点击元素无响应: DIV "⚡
                    快速扫描
   "
- **来源**: Chrome / Win32

### #3211 js_error - https://xinpect.xingwangzhineng.com/dashboard/ci-setup
- **时间**: 2026-10-13 07:42:14
- **方式**: REPORT
- **状态码**: None
- **消息**: Uncaught ReferenceError: selectMode is not defined at https://xinpect.xingwangzhineng.com/dashboard/ci-setup:677
- **堆栈摘要**:
```
ReferenceError: selectMode is not defined
    at HTMLDivElement.onclick (https://xinpect.xingwangzhineng.com/dashboard/ci-setup:677:88)
```
- **来源**: Chrome / Win32

### #3210 js_error - https://xinpect.xingwangzhineng.com/dashboard/ci-setup
- **时间**: 2026-10-13 07:41:46
- **方式**: REPORT
- **状态码**: None
- **消息**: Uncaught ReferenceError: updateThreshold is not defined at https://xinpect.xingwangzhineng.com/dashboard/ci-setup:707
- **堆栈摘要**:
```
ReferenceError: updateThreshold is not defined
    at HTMLInputElement.oninput (https://xinpect.xingwangzhineng.com/dashboard/ci-setup:707:150)
```
- **来源**: Chrome / Win32

### #3209 click_no_response - https://xinpect.xingwangzhineng.com/dashboard/ci-setup
- **时间**: 2026-10-13 07:41:39
- **方式**: REPORT
- **状态码**: None
- **消息**: 点击元素无响应: DIV "⚡
                    快速扫描
   "
- **来源**: Chrome / Win32

### #3208 js_error - https://xinpect.xingwangzhineng.com/dashboard/ci-setup
- **时间**: 2026-10-13 07:41:38
- **方式**: REPORT
- **状态码**: None
- **消息**: Uncaught ReferenceError: updateThreshold is not defined at https://xinpect.xingwangzhineng.com/dashboard/ci-setup:707
- **堆栈摘要**:
```
ReferenceError: updateThreshold is not defined
    at HTMLInputElement.oninput (https://xinpect.xingwangzhineng.com/dashboard/ci-setup:707:150)
```
- **来源**: Chrome / Win32

### #3207 js_error - https://xinpect.xingwangzhineng.com/dashboard/ci-setup
- **时间**: 2026-10-13 07:41:25
- **方式**: REPORT
- **状态码**: None
- **消息**: Uncaught ReferenceError: selectMode is not defined at https://xinpect.xingwangzhineng.com/dashboard/ci-setup:670
- **堆栈摘要**:
```
ReferenceError: selectMode is not defined
    at HTMLDivElement.onclick (https://xinpect.xingwangzhineng.com/dashboard/ci-setup:670:86)
```
- **来源**: Chrome / Win32

### #3206 click_no_response - https://xinpect.xingwangzhineng.com/dashboard/ci-setup
- **时间**: 2026-10-13 06:04:27
- **方式**: REPORT
- **状态码**: None
- **消息**: 点击元素无响应: DIV "🔬
                    深度扫描
  "
- **来源**: Chrome / Win32

### #3205 click_no_response - https://xinpect.xingwangzhineng.com/dashboard/ci-setup
- **时间**: 2026-10-13 06:04:12
- **方式**: REPORT
- **状态码**: None
- **消息**: 点击元素无响应: DIV "🧠
                    智能扫描
  "
- **来源**: Chrome / Win32

...还有 13 条未解决错误

## 🛡️ 安全扫描器探测摘要（已排除，共66条）
这些是自动化漏洞扫描工具的探测行为，非真实API错误。

| 探测类型 | 次数 |
|----------|------|
| 其他探测 | 51 |
| 云凭证探测 | 5 |
| WordPress扫描探测 | 4 |
| Git配置探测 | 4 |
| PHP探针 | 2 |
