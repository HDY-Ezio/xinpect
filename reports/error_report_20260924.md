# 每日错误报告
**日期**: 2026-09-24
**生成时间**: 2026-09-25 10:18:51

## 📊 总览
- **总错误数**: 11
  - 🔴 真实API错误: 3
  - 🟡 安全扫描器探测: 8
  - 系统服务错误 (journal): 0

> 💡 安全扫描器探测（8条）已从高频错误分析中排除，这些是自动化漏洞扫描行为，404为正确响应。
- **错误类型数**: 1
- **高频错误（>=3次）**: 1
- **未解决**: 3 / **已解决**: 0

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 11 | /wp-admin,/phpmyadmin,/data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/... |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| /phpmyadmin | GET | 4 | HTTP_ERROR |
| /wp-admin | GET | 4 | HTTP_ERROR |
| /api/session/properties | GET | 2 | HTTP_ERROR |
| /data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect width='100' height='100' rx='20' fill='#0EA5E9'/><text x='50' y='68' font-size='50' text-anchor='middle' fill='white' font-weight='bold' font-family='Arial'>X</text></svg> | GET | 1 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-09-24 04:00 | 2 |
| 2026-09-24 10:00 | 2 |
| 2026-09-24 15:00 | 1 |
| 2026-09-24 16:00 | 2 |
| 2026-09-24 22:00 | 4 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（11次）
涉及端点/服务：/wp-admin,/phpmyadmin,/data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect width='100' height='100' rx='20' fill='#0EA5E9'/><text x='50' y='68' font-size='50' text-anchor='middle' fill='white' font-weight='bold' font-family='Arial'>X</text></svg>,/api/session/properties

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 11 |

## ❌ 未解决错误详情（共3条）

### #2017 HTTP_ERROR - /api/session/properties
- **时间**: 2026-09-24 22:26:58
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: metabase-cve-2026-72898-detect/1.0 (benign detection probes only)

### #2018 HTTP_ERROR - /api/session/properties
- **时间**: 2026-09-24 22:26:58
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: metabase-cve-2026-72898-detect/1.0 (benign detection probes only)

### #2012 HTTP_ERROR - /data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect width='100' height='100' rx='20' fill='#0EA5E9'/><text x='50' y='68' font-size='50' text-anchor='middle' fill='white' font-weight='bold' font-family='Arial'>X</text></svg>
- **时间**: 2026-09-24 15:04:12
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Scrapy/2.17.0 (+https://scrapy.org)

## 🛡️ 安全扫描器探测摘要（已排除，共8条）
这些是自动化漏洞扫描工具的探测行为，非真实API错误。

| 探测类型 | 次数 |
|----------|------|
| WordPress扫描探测 | 4 |
| 其他探测 | 4 |
