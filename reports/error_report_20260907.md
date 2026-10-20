# 每日错误报告
**日期**: 2026-09-07
**生成时间**: 2026-09-08 10:19:16

## 📊 总览
- **总错误数**: 275
  - 🔴 真实API错误: 11
  - 🟡 安全扫描器探测: 264
  - 系统服务错误 (journal): 0

> 💡 安全扫描器探测（264条）已从高频错误分析中排除，这些是自动化漏洞扫描行为，404为正确响应。
- **错误类型数**: 2
- **高频错误（>=3次）**: 2
- **未解决**: 0 / **已解决**: 275

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 271 | /,/.git/config,/.env.local,/.env.staging,/.env.development,/.env.test,/.env.r... |
| MethodNotAllowed | 4 | / |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| / | POST | 8 | MethodNotAllowed,HTTP_ERROR |
| /.config/gcloud/application_default_credentials.json | GET | 1 | HTTP_ERROR |
| /.env.backup | GET | 1 | HTTP_ERROR |
| /.env.backup1 | GET | 1 | HTTP_ERROR |
| /.env.backup2 | GET | 1 | HTTP_ERROR |
| /.env.bak | GET | 1 | HTTP_ERROR |
| /.env.ci | GET | 1 | HTTP_ERROR |
| /.env.dev | GET | 1 | HTTP_ERROR |
| /.env.development | GET | 1 | HTTP_ERROR |
| /.env.dist | GET | 1 | HTTP_ERROR |
| /.env.docker | GET | 1 | HTTP_ERROR |
| /.env.example | GET | 1 | HTTP_ERROR |
| /.env.json | GET | 1 | HTTP_ERROR |
| /.env.live | GET | 1 | HTTP_ERROR |
| /.env.local | GET | 1 | HTTP_ERROR |
| /.env.old | GET | 1 | HTTP_ERROR |
| /.env.preprod | GET | 1 | HTTP_ERROR |
| /.env.prod | GET | 1 | HTTP_ERROR |
| /.env.remote | GET | 1 | HTTP_ERROR |
| /.env.sample | GET | 1 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-09-07 03:00 | 275 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（271次）
涉及端点/服务：/,/.git/config,/.env.local,/.env.staging,/.env.development,/.env.test,/.env.remote,/.env.bak,/.env.backup,/.env.save,/.env.old,/.env.sample,/.env.example,/.env.dev,/.env.prod,/.env.stage,/.env.ci,/.env.docker,/.env.live,/.env.preprod,/.env.uat,/.env.dist,/.env.swp,/.env~,/.env1,/.env2,/.env_copy,/.env.txt,/.env.json,/.env.yaml,/.env.yml,/app/.env,/apps/.env,/api/.env,/web/.env,/site/.env,/public/.env,/admin/.env,/backend/.env,/server/.env,/frontend/.env,/src/.env,/core/.env,/core/app/.env,/config/.env,/private/.env,/application/.env,/bootstrap/.env,/database/.env,/storage/.env,/var/www/.env,/var/www/html/.env,/current/.env,/release/.env,/releases/.env,/shared/.env,/deploy/.env,/build/.env,/dist/.env,/public_html/.env,/htdocs/.env,/www/.env,/html/.env,/live/.env,/prod/.env,/dev/.env,/staging/.env,/opt/.env,/laravel/.env,/symfony/.env,/wordpress/.env,/wp/.env,/cms/.env,/drupal/.env,/joomla/.env,/magento/.env,/shopify/.env,/prestashop/.env,/codeigniter/.env,/cakephp/.env,/zend/.env,/yii/.env,/laravel5/.env,/v1/.env,/v2/.env,/v3/.env,/api/v1/.env,/api/v2/.env,/rest/.env,/graphql/.env,/gateway/.env,/microservice/.env,/service/.env,/api/v3/.env,/api/dev/.env,/api/staging/.env,/vendor/.env,/lib/.env,/resources/.env,/assets/.env,/uploads/.env,/internal/.env,/tools/.env,/scripts/.env,/bin/.env,/sbin/.env,/local/.env,/portal/.env,/panel/.env,/crm/.env,/erp/.env,/shop/.env,/store/.env,/saas/.env,/client/.env,/project/.env,/admin-panel/.env,/control-panel/.env,/user-panel/.env,/node/.env,/express/.env,/next/.env,/nuxt/.env,/nest/.env,/react/.env,/vue/.env,/angular/.env,/svelte/.env,/vite/.env,/backup/.env,/backups/.env,/old/.env,/tmp/.env,/temp/.env,/lab/.env,/cronlab/.env,/cron/.env,/en/.env,/administrator/.env,/psnlink/.env,/exapi/.env,/sitemaps/.env,/.env.backup1,/.env.backup2,/logs/.env,/cache/.env,/mailer/.env,/mail/.env,/email/.env,/smtp/.env,/mailing/.env,/notifications/.env,/notify/.env,/sender/.env,/campaign/.env,/newsletter/.env,/ses/.env,/sendgrid/.env,/sparkpost/.env,/postmark/.env,/mailgun/.env,/mandrill/.env,/mailjet/.env,/brevo/.env,/transactional/.env,/bulk/.env,/aws/.env,/azure/.env,/gcp/.env,/cloud/.env,/infrastructure/.env,/docker/.env,/k8s/.env,/kubernetes/.env,/terraform/.env,/ansible/.env,/.git/.env,/ci/.env,/cd/.env,/jenkins/.env,/gitlab/.env,/github/.env,/actions/.env,/circleci/.env,/travis/.env,/buildkite/.env,/mysql/.env,/postgres/.env,/mongodb/.env,/redis/.env,/elasticsearch/.env,/rabbitmq/.env,/kafka/.env,/queue/.env,/worker/.env,/job/.env,/test/.env,/qa/.env,/preview/.env,/beta/.env,/uat/.env,/stage/.env,/development/.env,/production/.env,/config/app/.env,/info.php,/php.php,/i.php,/pi.php,/pinfo.php,/test.php,/phpinfo,/p.php,/debug.php,/admin/phpinfo.php,/test/phpinfo.php,/dev/phpinfo.php,/old/phpinfo.php,/tmp/phpinfo.php,/public/phpinfo.php,/info,/php-info.php,/phpversion.php,/_phpinfo.php,/old_phpinfo.php,/server-info.php,/server-status.php,/_profiler/phpinfo,/_environment,/webroot/index.php/_environment,/mail/phpinfo.php,/cpanel/phpinfo.php,/hosting/phpinfo.php,/webmail/phpinfo.php,/smtp/phpinfo.php,/phpinfo.php.bak,/phpinfo.php.old,/phpinfo.php~,/info.php.bak,/phpinfo.php.save,/staging/phpinfo.php,/beta/phpinfo.php,/uat/phpinfo.php,/qa/phpinfo.php,/preview/phpinfo.php,/www/phpinfo.php,/htdocs/phpinfo.php,/public_html/phpinfo.php,/site/phpinfo.php,/docs/phpinfo.php,/wp-admin/phpinfo.php,/administrator/phpinfo.php,/core/phpinfo.php,/includes/phpinfo.php,/service-account.json,/sa.json,/gcp-key.json,/gcp-credentials.json,/gcp-sa.json,/credentials.json,/google-credentials.json,/google-key.json,/.config/gcloud/application_default_credentials.json,/application_default_credentials.json,/key.json,/keyfile.json,/firebase-adminsdk.json,/firebase-key.json

### MethodNotAllowed（4次）
涉及端点/服务：/

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 275 |

## ❌ 未解决错误详情（共0条）
无未解决错误 ✅

## 🛡️ 安全扫描器探测摘要（已排除，共264条）
这些是自动化漏洞扫描工具的探测行为，非真实API错误。

| 探测类型 | 次数 |
|----------|------|
| .env文件探测 | 202 |
| PHP探针 | 45 |
| 云凭证探测 | 14 |
| 其他探测 | 2 |
| Git配置探测 | 1 |
