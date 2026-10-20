# 每日错误报告
**日期**: 2026-09-30
**生成时间**: 2026-10-01 10:42:11

## 📊 总览
- **总错误数**: 20
  - 🔴 真实API错误: 12
  - 🟡 安全扫描器探测: 8
  - 系统服务错误 (journal): 0

> 💡 安全扫描器探测（8条）已从高频错误分析中排除，这些是自动化漏洞扫描行为，404为正确响应。
- **错误类型数**: 1
- **高频错误（>=3次）**: 1
- **未解决**: 0 / **已解决**: 20

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 20 | /wp-admin,/phpmyadmin,/api/admin/announcement,/api-docs,/api/announcements,/a... |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| /phpmyadmin | GET | 4 | HTTP_ERROR |
| /wp-admin | GET | 4 | HTTP_ERROR |
| /api/announcements | GET | 3 | HTTP_ERROR |
| /api-docs | GET | 2 | HTTP_ERROR |
| /api/admin/announcement | POST | 1 | HTTP_ERROR |
| /api/auth/login | POST | 1 | HTTP_ERROR |
| /api/ci/ | GET | 1 | HTTP_ERROR |
| /api/scan | POST | 1 | HTTP_ERROR |
| /api/scan/estimate | POST | 1 | HTTP_ERROR |
| /api/scan/submit | POST | 1 | HTTP_ERROR |
| /health | GET | 1 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-09-30 04:00 | 2 |
| 2026-09-30 08:00 | 11 |
| 2026-09-30 10:00 | 2 |
| 2026-09-30 16:00 | 3 |
| 2026-09-30 22:00 | 2 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（20次）
涉及端点/服务：/wp-admin,/phpmyadmin,/api/admin/announcement,/api-docs,/api/announcements,/api/ci/,/api/scan,/api/scan/submit,/api/scan/estimate,/api/auth/login,/health

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 20 |

## ❌ 未解决错误详情（共0条）
无未解决错误 ✅

## 🛡️ 安全扫描器探测摘要（已排除，共8条）
这些是自动化漏洞扫描工具的探测行为，非真实API错误。

| 探测类型 | 次数 |
|----------|------|
| WordPress扫描探测 | 4 |
| 其他探测 | 4 |
