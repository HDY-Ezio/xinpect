# 每日错误报告
**日期**: 2026-09-26
**生成时间**: 2026-09-27 10:41:23

## 📊 总览
- **总错误数**: 28
  - 🔴 真实API错误: 20
  - 🟡 安全扫描器探测: 8
  - 系统服务错误 (journal): 0

> 💡 安全扫描器探测（8条）已从高频错误分析中排除，这些是自动化漏洞扫描行为，404为正确响应。
- **错误类型数**: 1
- **高频错误（>=3次）**: 1
- **未解决**: 1 / **已解决**: 27

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 28 | /api/scan/submit,/wp-admin,/phpmyadmin,/static/xinpect_showcase.png,/report/s... |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| /phpmyadmin | GET | 4 | HTTP_ERROR |
| /static/xinpect_showcase.png | GET | 4 | HTTP_ERROR |
| /wp-admin | GET | 4 | HTTP_ERROR |
| /api/scan/0e749813175b15d92d7de35bc6db556e/share | POST | 3 | HTTP_ERROR |
| /report/share/0b1wUxZMtlLr9O6D | GET | 3 | HTTP_ERROR |
| /api/ci/scan/ci_scan_1790424382038_3bd07defb1f6 | GET | 2 | HTTP_ERROR |
| /.aws/credentials | GET | 1 | HTTP_ERROR |
| /api/badge/15 | GET | 1 | HTTP_ERROR |
| /api/ci/scan | POST | 1 | HTTP_ERROR |
| /api/report/ci_scan_1790424382038_3bd07defb1f6 | GET | 1 | HTTP_ERROR |
| /api/scan/submit | POST | 1 | HTTP_ERROR |
| /report/share/test123 | GET | 1 | HTTP_ERROR |
| /static/ci-templates/github-actions.yml | GET | 1 | HTTP_ERROR |
| /wp-content/debug.log | GET | 1 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-09-26 01:00 | 1 |
| 2026-09-26 04:00 | 2 |
| 2026-09-26 07:00 | 8 |
| 2026-09-26 08:00 | 3 |
| 2026-09-26 10:00 | 2 |
| 2026-09-26 11:00 | 3 |
| 2026-09-26 12:00 | 5 |
| 2026-09-26 16:00 | 2 |
| 2026-09-26 22:00 | 2 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（28次）
涉及端点/服务：/api/scan/submit,/wp-admin,/phpmyadmin,/static/xinpect_showcase.png,/report/share/test123,/api/scan/0e749813175b15d92d7de35bc6db556e/share,/report/share/0b1wUxZMtlLr9O6D,/api/ci/scan,/api/badge/15,/static/ci-templates/github-actions.yml,/api/report/ci_scan_1790424382038_3bd07defb1f6,/api/ci/scan/ci_scan_1790424382038_3bd07defb1f6,/.aws/credentials,/wp-content/debug.log

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 28 |

## ❌ 未解决错误详情（共1条）

### #2047 HTTP_ERROR - /api/scan/submit
- **时间**: 2026-09-26 01:20:27
- **方式**: POST
- **状态码**: 403
- **消息**: HTTP 403
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

## 🛡️ 安全扫描器探测摘要（已排除，共8条）
这些是自动化漏洞扫描工具的探测行为，非真实API错误。

| 探测类型 | 次数 |
|----------|------|
| WordPress扫描探测 | 4 |
| 其他探测 | 4 |
