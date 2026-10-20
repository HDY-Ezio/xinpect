# 每日错误报告
**日期**: 2026-09-10
**生成时间**: 2026-09-11 10:14:03

## 📊 总览
- **总错误数**: 260
  - 🔴 真实API错误: 98
  - 🟡 安全扫描器探测: 162
  - 系统服务错误 (journal): 0

> 💡 安全扫描器探测（162条）已从高频错误分析中排除，这些是自动化漏洞扫描行为，404为正确响应。
- **错误类型数**: 3
- **高频错误（>=3次）**: 2
- **未解决**: 98 / **已解决**: 0

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 254 | /,/.git/config,/.env.local,/.env.staging,/.env.development,/.env.test,/.env.r... |
| MethodNotAllowed | 5 | /,/api/pay/create |
| AttributeError | 1 | /dashboard/scans |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| /api/v1/scan | POST | 44 | HTTP_ERROR |
| / | POST | 8 | MethodNotAllowed,HTTP_ERROR |
| /.env.local | GET | 2 | HTTP_ERROR |
| /.git/config | GET | 2 | HTTP_ERROR |
| /admin | GET | 2 | HTTP_ERROR |
| /api/health | GET | 2 | HTTP_ERROR |
| /api/pay/create | GET | 2 | MethodNotAllowed,HTTP_ERROR |
| /api/v1/estimate | POST | 2 | HTTP_ERROR |
| /dashboard/scans | GET | 2 | AttributeError,HTTP_ERROR |
| /.env.backup | GET | 1 | HTTP_ERROR |
| /.env.bak | GET | 1 | HTTP_ERROR |
| /.env.ci | GET | 1 | HTTP_ERROR |
| /.env.dev | GET | 1 | HTTP_ERROR |
| /.env.development | GET | 1 | HTTP_ERROR |
| /.env.dist | GET | 1 | HTTP_ERROR |
| /.env.docker | GET | 1 | HTTP_ERROR |
| /.env.example | GET | 1 | HTTP_ERROR |
| /.env.live | GET | 1 | HTTP_ERROR |
| /.env.old | GET | 1 | HTTP_ERROR |
| /.env.preprod | GET | 1 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-09-10 00:00 | 169 |
| 2026-09-10 02:00 | 1 |
| 2026-09-10 05:00 | 5 |
| 2026-09-10 06:00 | 18 |
| 2026-09-10 07:00 | 11 |
| 2026-09-10 08:00 | 18 |
| 2026-09-10 10:00 | 19 |
| 2026-09-10 11:00 | 1 |
| 2026-09-10 12:00 | 18 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（254次）
涉及端点/服务：/,/.git/config,/.env.local,/.env.staging,/.env.development,/.env.test,/.env.remote,/.env.bak,/.env.backup,/.env.save,/.env.old,/.env.sample,/.env.example,/.env.dev,/.env.prod,/.env.stage,/.env.ci,/.env.docker,/.env.live,/.env.preprod,/.env.uat,/.env.dist,/.env.swp,/.env~,/app/.env,/apps/.env,/api/.env,/web/.env,/site/.env,/public/.env,/admin/.env,/backend/.env,/server/.env,/frontend/.env,/src/.env,/core/.env,/core/app/.env,/core/Database/.env,/config/.env,/private/.env,/current/.env,/release/.env,/releases/.env,/shared/.env,/deploy/.env,/build/.env,/dist/.env,/public_html/.env,/htdocs/.env,/www/.env,/html/.env,/live/.env,/prod/.env,/dev/.env,/staging/.env,/laravel/.env,/symfony/.env,/wordpress/.env,/wp/.env,/cms/.env,/drupal/.env,/joomla/.env,/magento/.env,/shopify/.env,/prestashop/.env,/v1/.env,/v2/.env,/v3/.env,/api/v1/.env,/api/v2/.env,/rest/.env,/graphql/.env,/gateway/.env,/microservice/.env,/service/.env,/vendor/.env,/lib/.env,/database/.env,/resources/.env,/storage/.env,/assets/.env,/uploads/.env,/internal/.env,/tools/.env,/scripts/.env,/portal/.env,/panel/.env,/crm/.env,/erp/.env,/shop/.env,/store/.env,/saas/.env,/client/.env,/project/.env,/node/.env,/express/.env,/next/.env,/nuxt/.env,/nest/.env,/backup/.env,/backups/.env,/old/.env,/tmp/.env,/temp/.env,/lab/.env,/cronlab/.env,/cron/.env,/en/.env,/administrator/.env,/psnlink/.env,/exapi/.env,/sitemaps/.env,/mailer/.env,/mail/.env,/email/.env,/smtp/.env,/mailing/.env,/notifications/.env,/notify/.env,/sender/.env,/campaign/.env,/newsletter/.env,/ses/.env,/sendgrid/.env,/sparkpost/.env,/postmark/.env,/mailgun/.env,/mandrill/.env,/mailjet/.env,/brevo/.env,/transactional/.env,/bulk/.env,/info.php,/php.php,/i.php,/pi.php,/pinfo.php,/test.php,/phpinfo,/p.php,/debug.php,/admin/phpinfo.php,/test/phpinfo.php,/dev/phpinfo.php,/old/phpinfo.php,/tmp/phpinfo.php,/public/phpinfo.php,/info,/php-info.php,/phpversion.php,/_phpinfo.php,/old_phpinfo.php,/server-info.php,/server-status.php,/_profiler/phpinfo,/_environment,/webroot/index.php/_environment,/mail/phpinfo.php,/cpanel/phpinfo.php,/hosting/phpinfo.php,/webmail/phpinfo.php,/smtp/phpinfo.php,/api/scan/estimate,/api/v1/scan,/api/pay/create,/api/v1/estimate,/dashboard/scans,/api/users/stats,/api/overview,/api/dashboard,/api/admin,/api/scan/history,/api/stats,/api/today,/api/monitor,/api/announcements,/api/register,/api/admin/stats,/api/users/count,/api/scans/today,/api/monitor/daily,/admin,/api/health,/api/v1/stats,/static/js/' + safeQrUrl + ',/wp-includes/wlwmanifest.xml,/xmlrpc.php,/blog/wp-includes/wlwmanifest.xml,/web/wp-includes/wlwmanifest.xml,/wordpress/wp-includes/wlwmanifest.xml,/website/wp-includes/wlwmanifest.xml,/wp/wp-includes/wlwmanifest.xml,/news/wp-includes/wlwmanifest.xml,/2018/wp-includes/wlwmanifest.xml,/2019/wp-includes/wlwmanifest.xml,/shop/wp-includes/wlwmanifest.xml,/wp1/wp-includes/wlwmanifest.xml,/test/wp-includes/wlwmanifest.xml,/media/wp-includes/wlwmanifest.xml,/wp2/wp-includes/wlwmanifest.xml,/site/wp-includes/wlwmanifest.xml,/cms/wp-includes/wlwmanifest.xml,/sito/wp-includes/wlwmanifest.xml

### MethodNotAllowed（5次）
涉及端点/服务：/,/api/pay/create

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 260 |

## ❌ 未解决错误详情（共98条）

### #1305 HTTP_ERROR - /sito/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-10 12:36:55
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.10

### #1303 HTTP_ERROR - /site/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-10 12:36:54
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.10

### #1304 HTTP_ERROR - /cms/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-10 12:36:54
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.10

### #1302 HTTP_ERROR - /wp2/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-10 12:36:25
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.10

### #1301 HTTP_ERROR - /media/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-10 12:36:24
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.10

### #1298 HTTP_ERROR - /shop/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-10 12:35:54
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.10

### #1299 HTTP_ERROR - /wp1/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-10 12:35:54
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.10

### #1300 HTTP_ERROR - /test/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-10 12:35:54
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.10

### #1294 HTTP_ERROR - /wp/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-10 12:35:53
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.10

### #1295 HTTP_ERROR - /news/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-10 12:35:53
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.10

### #1296 HTTP_ERROR - /2018/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-10 12:35:53
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.10

### #1297 HTTP_ERROR - /2019/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-10 12:35:53
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.10

### #1292 HTTP_ERROR - /wordpress/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-10 12:35:52
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.10

### #1293 HTTP_ERROR - /website/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-10 12:35:52
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.10

### #1290 HTTP_ERROR - /blog/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-10 12:35:51
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.10

### #1291 HTTP_ERROR - /web/wp-includes/wlwmanifest.xml
- **时间**: 2026-09-10 12:35:51
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.10

### #1288 HTTP_ERROR - /wp-includes/wlwmanifest.xml
- **时间**: 2026-09-10 12:35:50
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.10

### #1287 HTTP_ERROR - /api/health
- **时间**: 2026-09-10 11:54:23
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #1286 HTTP_ERROR - /static/js/' + safeQrUrl + '
- **时间**: 2026-09-10 10:38:52
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.4; +https://openai.com/gptbo

### #1285 HTTP_ERROR - /admin
- **时间**: 2026-09-10 10:28:12
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: curl/7.81.0

...还有 78 条未解决错误

## 🛡️ 安全扫描器探测摘要（已排除，共162条）
这些是自动化漏洞扫描工具的探测行为，非真实API错误。

| 探测类型 | 次数 |
|----------|------|
| .env文件探测 | 130 |
| PHP探针 | 28 |
| Git配置探测 | 2 |
| 其他探测 | 2 |
