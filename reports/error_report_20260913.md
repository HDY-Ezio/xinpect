# 每日错误报告
**日期**: 2026-09-13
**生成时间**: 2026-09-14 10:27:53

## 📊 总览
- **总错误数**: 216
  - 🔴 真实API错误: 38
  - 🟡 安全扫描器探测: 178
  - 系统服务错误 (journal): 0

> 💡 安全扫描器探测（178条）已从高频错误分析中排除，这些是自动化漏洞扫描行为，404为正确响应。
- **错误类型数**: 2
- **高频错误（>=3次）**: 2
- **未解决**: 0 / **已解决**: 216

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 196 | /,/en,/.well-known/security.txt,/index.php,/wp-json/batch/v1,/wp-json/Batch/v... |
| MethodNotAllowed | 20 | /,/dashboard |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| / | POST | 36 | MethodNotAllowed,HTTP_ERROR |
| /wp/ | POST | 21 | HTTP_ERROR |
| /wp/index.php | POST | 14 | HTTP_ERROR |
| /wordpress/ | POST | 12 | HTTP_ERROR |
| /wp/ | GET | 9 | HTTP_ERROR |
| /wordpress/index.php | POST | 8 | HTTP_ERROR |
| /wp//wp-json/batch/v1 | POST | 7 | HTTP_ERROR |
| /wp/blog/wp-json/batch/v1 | POST | 7 | HTTP_ERROR |
| /wp/wordpress/wp-json/batch/v1 | POST | 7 | HTTP_ERROR |
| /wp/wp-json/Batch/v1 | POST | 7 | HTTP_ERROR |
| /wp/wp-json/batch/v1 | POST | 7 | HTTP_ERROR |
| /wp/wp-json/batch/v1/ | POST | 7 | HTTP_ERROR |
| /index.php | POST | 6 | HTTP_ERROR |
| /wp-json/batch/v1 | POST | 6 | HTTP_ERROR |
| /wordpress/wp-json/batch/v1 | POST | 5 | HTTP_ERROR |
| /dashboard | POST | 4 | MethodNotAllowed,HTTP_ERROR |
| /signin | POST | 4 | HTTP_ERROR |
| /api/auth/signin | POST | 3 | HTTP_ERROR |
| /wordpress//wp-json/batch/v1 | POST | 3 | HTTP_ERROR |
| /wordpress/blog/wp-json/batch/v1 | POST | 3 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-09-13 11:00 | 4 |
| 2026-09-13 12:00 | 1 |
| 2026-09-13 20:00 | 210 |
| 2026-09-13 21:00 | 1 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（196次）
涉及端点/服务：/,/en,/.well-known/security.txt,/index.php,/wp-json/batch/v1,/wp-json/Batch/v1,/wp-json/batch/v1/,/blog/wp-json/batch/v1,/wordpress/wp-json/batch/v1,/wp-json/gravitysmtp/v1/tests/mock-data,/livewire/update,/signin,/api/auth/signin,/dashboard,/wp/index.php,/wp/,/wp/wp-json/batch/v1,/wp/wp-json/Batch/v1,/wp//wp-json/batch/v1,/wp/wp-json/batch/v1/,/wp/blog/wp-json/batch/v1,/wp/wordpress/wp-json/batch/v1,/wp/wp/v2/posts/999999,/wp/wp/v2/pages,/wp/wp/v2/media,/wp/wp/v2/categories,/wp/wp/v2/tags,/wp/wp/v2/posts/999998,/wp/wp/v2/posts/99999,/wp/wp/v2/posts/9999999,/wp/wp/v2/users,/wordpress/index.php,/wordpress/,/wordpress/wp-json/Batch/v1,/wordpress//wp-json/batch/v1,/wordpress/wp-json/batch/v1/,/wordpress/blog/wp-json/batch/v1,/wordpress/wordpress/wp-json/batch/v1

### MethodNotAllowed（20次）
涉及端点/服务：/,/dashboard

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 216 |

## ❌ 未解决错误详情（共0条）
无未解决错误 ✅

## 🛡️ 安全扫描器探测摘要（已排除，共178条）
这些是自动化漏洞扫描工具的探测行为，非真实API错误。

| 探测类型 | 次数 |
|----------|------|
| WordPress扫描探测 | 135 |
| PHP探针 | 30 |
| 其他探测 | 12 |
| 企业扫描器探测 | 1 |
