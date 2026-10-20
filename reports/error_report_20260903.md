# 每日错误报告
**日期**: 2026-09-03
**生成时间**: 2026-09-04 10:14:22

## 📊 总览
- **总错误数**: 412
  - API/HTTP 错误: 412
  - 系统服务错误 (journal): 0
- **错误类型数**: 5
- **高频错误（>=3次）**: 4
- **未解决**: 412 / **已解决**: 0

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 361 | /robots.txt,/api/v1/scan,/login,/favicon.ico,/dashboard,/api/referral/info,/.... |
| AttributeError | 21 | /login,/api/referral/info,/dashboard/account |
| NameError | 17 | /api/v1/scan,/login,/dashboard,/api/announcement/read/1,/dashboard/account |
| MethodNotAllowed | 11 | /dashboard,/ |
| IntegrityError | 2 | /api/alerts/1 |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| /api/v1/scan | POST | 34 | HTTP_ERROR,NameError |
| /login | POST | 24 | AttributeError,HTTP_ERROR,NameError |
| /dashboard/account | GET | 22 | NameError,HTTP_ERROR,AttributeError |
| /api/referral/info | GET | 12 | AttributeError,HTTP_ERROR |
| /dashboard | POST | 12 | MethodNotAllowed,HTTP_ERROR |
| / | POST | 10 | MethodNotAllowed,HTTP_ERROR |
| /api/trends | GET | 6 | HTTP_ERROR |
| /.git/config | GET | 4 | HTTP_ERROR |
| /api/alerts/1 | DELETE | 4 | IntegrityError,HTTP_ERROR |
| /dashboard | GET | 4 | NameError,HTTP_ERROR |
| /robots.txt | GET | 3 | HTTP_ERROR |
| /.env | GET | 2 | HTTP_ERROR |
| /.env.production | GET | 2 | HTTP_ERROR |
| /api/announcement/read/1 | POST | 2 | NameError,HTTP_ERROR |
| /auth/login | POST | 2 | HTTP_ERROR |
| /favicon.ico | GET | 2 | HTTP_ERROR |
| /.aws/credentials | GET | 1 | HTTP_ERROR |
| /.env.backup | GET | 1 | HTTP_ERROR |
| /.env.backup1 | GET | 1 | HTTP_ERROR |
| /.env.backup2 | GET | 1 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-09-03 00:00 | 1 |
| 2026-09-03 01:00 | 20 |
| 2026-09-03 02:00 | 38 |
| 2026-09-03 03:00 | 5 |
| 2026-09-03 04:00 | 1 |
| 2026-09-03 05:00 | 1 |
| 2026-09-03 07:00 | 264 |
| 2026-09-03 09:00 | 5 |
| 2026-09-03 10:00 | 2 |
| 2026-09-03 12:00 | 3 |
| 2026-09-03 13:00 | 5 |
| 2026-09-03 14:00 | 1 |
| 2026-09-03 15:00 | 2 |
| 2026-09-03 16:00 | 23 |
| 2026-09-03 17:00 | 35 |
| 2026-09-03 18:00 | 2 |
| 2026-09-03 22:00 | 4 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（361次）
涉及端点/服务：/robots.txt,/api/v1/scan,/login,/favicon.ico,/dashboard,/api/referral/info,/.git/config,/,/.env,/.env.local,/.env.production,/.env.staging,/.env.development,/.env.test,/.env.remote,/.env.bak,/.env.backup,/.env.save,/.env.old,/.env.sample,/.env.example,/.env.dev,/.env.prod,/.env.stage,/.env.ci,/.env.docker,/.env.live,/.env.preprod,/.env.uat,/.env.dist,/.env.swp,/.env~,/.env1,/.env2,/.env_copy,/.env.txt,/.env.json,/.env.yaml,/.env.yml,/app/.env,/apps/.env,/api/.env,/web/.env,/site/.env,/public/.env,/admin/.env,/backend/.env,/server/.env,/frontend/.env,/src/.env,/core/.env,/core/app/.env,/config/.env,/private/.env,/application/.env,/bootstrap/.env,/database/.env,/storage/.env,/var/www/.env,/var/www/html/.env,/current/.env,/release/.env,/releases/.env,/shared/.env,/deploy/.env,/build/.env,/dist/.env,/public_html/.env,/htdocs/.env,/www/.env,/html/.env,/live/.env,/prod/.env,/dev/.env,/staging/.env,/opt/.env,/laravel/.env,/symfony/.env,/wordpress/.env,/wp/.env,/cms/.env,/drupal/.env,/joomla/.env,/magento/.env,/shopify/.env,/prestashop/.env,/codeigniter/.env,/cakephp/.env,/zend/.env,/yii/.env,/laravel5/.env,/v1/.env,/v2/.env,/v3/.env,/api/v1/.env,/api/v2/.env,/rest/.env,/graphql/.env,/gateway/.env,/microservice/.env,/service/.env,/api/v3/.env,/api/dev/.env,/api/staging/.env,/vendor/.env,/lib/.env,/resources/.env,/assets/.env,/uploads/.env,/internal/.env,/tools/.env,/scripts/.env,/bin/.env,/sbin/.env,/local/.env,/portal/.env,/panel/.env,/crm/.env,/erp/.env,/shop/.env,/store/.env,/saas/.env,/client/.env,/project/.env,/admin-panel/.env,/control-panel/.env,/user-panel/.env,/node/.env,/express/.env,/next/.env,/nuxt/.env,/nest/.env,/react/.env,/vue/.env,/angular/.env,/svelte/.env,/vite/.env,/backup/.env,/backups/.env,/old/.env,/tmp/.env,/temp/.env,/lab/.env,/cronlab/.env,/cron/.env,/en/.env,/administrator/.env,/psnlink/.env,/exapi/.env,/sitemaps/.env,/.env.backup1,/.env.backup2,/logs/.env,/cache/.env,/mailer/.env,/mail/.env,/email/.env,/smtp/.env,/mailing/.env,/notifications/.env,/notify/.env,/sender/.env,/campaign/.env,/newsletter/.env,/ses/.env,/sendgrid/.env,/sparkpost/.env,/postmark/.env,/mailgun/.env,/mandrill/.env,/mailjet/.env,/brevo/.env,/transactional/.env,/bulk/.env,/aws/.env,/azure/.env,/gcp/.env,/cloud/.env,/infrastructure/.env,/docker/.env,/k8s/.env,/kubernetes/.env,/terraform/.env,/ansible/.env,/.git/.env,/ci/.env,/cd/.env,/jenkins/.env,/gitlab/.env,/github/.env,/actions/.env,/circleci/.env,/travis/.env,/buildkite/.env,/mysql/.env,/postgres/.env,/mongodb/.env,/redis/.env,/elasticsearch/.env,/rabbitmq/.env,/kafka/.env,/queue/.env,/worker/.env,/job/.env,/test/.env,/qa/.env,/preview/.env,/beta/.env,/uat/.env,/stage/.env,/development/.env,/production/.env,/config/app/.env,/phpinfo.php,/info.php,/php.php,/i.php,/pi.php,/pinfo.php,/test.php,/phpinfo,/p.php,/debug.php,/admin/phpinfo.php,/test/phpinfo.php,/dev/phpinfo.php,/old/phpinfo.php,/tmp/phpinfo.php,/public/phpinfo.php,/info,/php-info.php,/phpversion.php,/_phpinfo.php,/old_phpinfo.php,/server-info.php,/server-status.php,/_profiler/phpinfo,/_environment,/webroot/index.php/_environment,/mail/phpinfo.php,/cpanel/phpinfo.php,/hosting/phpinfo.php,/webmail/phpinfo.php,/smtp/phpinfo.php,/phpinfo.php.bak,/phpinfo.php.old,/phpinfo.php~,/info.php.bak,/phpinfo.php.save,/staging/phpinfo.php,/beta/phpinfo.php,/uat/phpinfo.php,/qa/phpinfo.php,/preview/phpinfo.php,/www/phpinfo.php,/htdocs/phpinfo.php,/public_html/phpinfo.php,/site/phpinfo.php,/docs/phpinfo.php,/wp-admin/phpinfo.php,/administrator/phpinfo.php,/core/phpinfo.php,/includes/phpinfo.php,/docs,/about,/contact,/scan,/wp-login.php,/wp-json/,/api/announcement/read/1,/api/admin/announcements,/dashboard/account,/api/trends,/api/trends/summary,/api/trends/brain,/api/scan,/api/alerts/1,/auth/login,/api/scan/list,/api/login,/.aws/credentials,/aws.env

### AttributeError（21次）
涉及端点/服务：/login,/api/referral/info,/dashboard/account

### NameError（17次）
涉及端点/服务：/api/v1/scan,/login,/dashboard,/api/announcement/read/1,/dashboard/account

### MethodNotAllowed（11次）
涉及端点/服务：/dashboard,/

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 412 |

## ❌ 未解决错误详情（共412条）

### #420 HTTP_ERROR - /.env
- **时间**: 2026-09-03 22:55:44
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:134.0) Gecko/20100101 Firefox/134.0

### #421 HTTP_ERROR - /.aws/credentials
- **时间**: 2026-09-03 22:55:44
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (ZZ; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36

### #422 HTTP_ERROR - /.env.production
- **时间**: 2026-09-03 22:55:44
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.

### #423 HTTP_ERROR - /aws.env
- **时间**: 2026-09-03 22:55:44
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (CentOS; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/53

### #418 HTTP_ERROR - /.git/config
- **时间**: 2026-09-03 18:05:16
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (X11; CrOS x86_64 14816.131.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 S

### #419 HTTP_ERROR - /.git/config
- **时间**: 2026-09-03 18:05:16
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 6.2; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0

### #416 MethodNotAllowed - /dashboard
- **时间**: 2026-09-03 17:45:34
- **方式**: POST
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
- **来源**: curl/8.5.0

### #417 HTTP_ERROR - /dashboard
- **时间**: 2026-09-03 17:45:34
- **方式**: POST
- **状态码**: 405
- **消息**: HTTP 405
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

### #414 AttributeError - /dashboard/account
- **时间**: 2026-09-03 17:43:00
- **方式**: GET
- **状态码**: 500
- **消息**: 'sqlite3.Row' object has no attribute 'get'
- **堆栈摘要**:
```
                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/xinpect-website/modules/referral.py", line 42, in ensure_user_referral_code
    if user.get('referral_code'):
       ^^^^^^^^
AttributeError: 'sqlite3.Row' object has no attribute 'get'
```
- **IP**: 127.0.0.1
- **来源**: Werkzeug/3.1.8

### #415 HTTP_ERROR - /dashboard/account
- **时间**: 2026-09-03 17:43:00
- **方式**: GET
- **状态码**: 500
- **消息**: HTTP 500
- **IP**: 127.0.0.1
- **来源**: Werkzeug/3.1.8

### #412 AttributeError - /dashboard/account
- **时间**: 2026-09-03 17:42:50
- **方式**: GET
- **状态码**: 500
- **消息**: 'sqlite3.Row' object has no attribute 'get'
- **堆栈摘要**:
```
                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/xinpect-website/modules/referral.py", line 42, in ensure_user_referral_code
    if user.get('referral_code'):
       ^^^^^^^^
AttributeError: 'sqlite3.Row' object has no attribute 'get'
```
- **IP**: 127.0.0.1
- **来源**: Werkzeug/3.1.8

### #413 HTTP_ERROR - /dashboard/account
- **时间**: 2026-09-03 17:42:50
- **方式**: GET
- **状态码**: 500
- **消息**: HTTP 500
- **IP**: 127.0.0.1
- **来源**: Werkzeug/3.1.8

### #410 AttributeError - /dashboard/account
- **时间**: 2026-09-03 17:42:03
- **方式**: GET
- **状态码**: 500
- **消息**: 'sqlite3.Row' object has no attribute 'get'
- **堆栈摘要**:
```
                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/xinpect-website/modules/referral.py", line 42, in ensure_user_referral_code
    if user.get('referral_code'):
       ^^^^^^^^
AttributeError: 'sqlite3.Row' object has no attribute 'get'
```
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Sa

### #411 HTTP_ERROR - /dashboard/account
- **时间**: 2026-09-03 17:42:03
- **方式**: GET
- **状态码**: 500
- **消息**: HTTP 500
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Sa

### #408 AttributeError - /dashboard/account
- **时间**: 2026-09-03 17:42:00
- **方式**: GET
- **状态码**: 500
- **消息**: 'sqlite3.Row' object has no attribute 'get'
- **堆栈摘要**:
```
                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/xinpect-website/modules/referral.py", line 42, in ensure_user_referral_code
    if user.get('referral_code'):
       ^^^^^^^^
AttributeError: 'sqlite3.Row' object has no attribute 'get'
```
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Sa

### #409 HTTP_ERROR - /dashboard/account
- **时间**: 2026-09-03 17:42:00
- **方式**: GET
- **状态码**: 500
- **消息**: HTTP 500
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Sa

### #405 AttributeError - /dashboard/account
- **时间**: 2026-09-03 17:41:40
- **方式**: GET
- **状态码**: 500
- **消息**: 'sqlite3.Row' object has no attribute 'get'
- **堆栈摘要**:
```
                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/xinpect-website/modules/referral.py", line 42, in ensure_user_referral_code
    if user.get('referral_code'):
       ^^^^^^^^
AttributeError: 'sqlite3.Row' object has no attribute 'get'
```
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Sa

### #406 HTTP_ERROR - /dashboard/account
- **时间**: 2026-09-03 17:41:40
- **方式**: GET
- **状态码**: 500
- **消息**: HTTP 500
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Sa

### #407 HTTP_ERROR - /favicon.ico
- **时间**: 2026-09-03 17:41:40
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Sa

### #403 AttributeError - /dashboard/account
- **时间**: 2026-09-03 17:33:51
- **方式**: GET
- **状态码**: 500
- **消息**: 'sqlite3.Row' object has no attribute 'get'
- **堆栈摘要**:
```
                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/xinpect-website/modules/referral.py", line 42, in ensure_user_referral_code
    if user.get('referral_code'):
       ^^^^^^^^
AttributeError: 'sqlite3.Row' object has no attribute 'get'
```
- **IP**: 127.0.0.1
- **来源**: curl/8.5.0

...还有 392 条未解决错误
