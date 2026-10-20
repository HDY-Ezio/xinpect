# 每日错误报告
**日期**: 2026-10-07
**生成时间**: 2026-10-08 10:41:36

## 📊 总览
- **总错误数**: 540
  - 🔴 真实API错误: 517
  - 🟡 安全扫描器探测: 23
  - 系统服务错误 (journal): 0

> 💡 安全扫描器探测（23条）已从高频错误分析中排除，这些是自动化漏洞扫描行为，404为正确响应。
- **错误类型数**: 1
- **高频错误（>=3次）**: 1
- **未解决**: 517 / **已解决**: 0

## 📋 错误类型分布
| 类型 | 次数 | 涉及端点/服务 |
|------|------|---------------|
| HTTP_ERROR | 540 | /kxs-1791333700268947164-nonexistent,/.circleci/config.yml,/.travis.yml,/.dro... |

## 🔥 高频出错端点/服务 TOP 10
| 端点/服务 | 方法 | 次数 | 错误类型 |
|-----------|------|------|----------|
| /config.json | GET | 4 | HTTP_ERROR |
| /phpmyadmin | GET | 4 | HTTP_ERROR |
| /wp-admin | GET | 4 | HTTP_ERROR |
| /.aws/credentials | GET | 3 | HTTP_ERROR |
| /.boto | GET | 3 | HTTP_ERROR |
| /api/session/properties | GET | 3 | HTTP_ERROR |
| /credentials | GET | 3 | HTTP_ERROR |
| /docker-compose.yaml | GET | 3 | HTTP_ERROR |
| /favicon.png | GET | 3 | HTTP_ERROR |
| /pages/about.html | GET | 3 | HTTP_ERROR |
| /web.config | GET | 3 | HTTP_ERROR |
| /.aws/config | GET | 2 | HTTP_ERROR |
| /.circleci/config.yml | GET | 2 | HTTP_ERROR |
| /.drone.yml | GET | 2 | HTTP_ERROR |
| /.hg/dirstate | GET | 2 | HTTP_ERROR |
| /.hg/requires | GET | 2 | HTTP_ERROR |
| /.hg/store/requires | GET | 2 | HTTP_ERROR |
| /.netrc | GET | 2 | HTTP_ERROR |
| /.s3cfg | GET | 2 | HTTP_ERROR |
| /.travis.yml | GET | 2 | HTTP_ERROR |

## 📈 错误时间分布（按小时）
| 时间 | 错误数 |
|------|--------|
| 2026-10-07 00:00 | 237 |
| 2026-10-07 01:00 | 1 |
| 2026-10-07 03:00 | 10 |
| 2026-10-07 04:00 | 2 |
| 2026-10-07 06:00 | 1 |
| 2026-10-07 08:00 | 14 |
| 2026-10-07 10:00 | 2 |
| 2026-10-07 13:00 | 2 |
| 2026-10-07 16:00 | 11 |
| 2026-10-07 19:00 | 254 |
| 2026-10-07 20:00 | 4 |
| 2026-10-07 22:00 | 2 |

## 🚨 高频错误（需要优先修复）

### HTTP_ERROR（540次）
涉及端点/服务：/kxs-1791333700268947164-nonexistent,/.circleci/config.yml,/.travis.yml,/.drone.yml,/bitbucket-pipelines.yml,/azure-pipelines.yml,/.zsh_history,/root/.bash_history,/root/.zsh_history,/home/user/.bash_history,/.netrc,/.profile,/root/.bashrc,/root/.netrc,/.pypirc,/root/.npmrc,/.zshrc,/.bashrc,/deploy.sh,/root/.profile,/build.sh,/ecosystem.config.js,/deploy.json,/ci.sh,/ecosystem.config.json,/scripts/deploy.sh,/package.json,/app/package.json,/package-lock.json,/npm-shrinkwrap.json,/app/package-lock.json,/backend/package.json,/frontend/package.json,/frontend/package-lock.json,/web/package.json,/backend/package-lock.json,/server/package.json,/api/package.json,/old/package.json,/backup/package.json,/config.js,/env.js,/js/config.js,/settings.js,/app/env.js,/env.json,/js/env.js,/static/config.js,/js/settings.js,/assets/env.js,/static/env.js,/assets/config.js,/app/config.js,/config/env.js,/config/config.js,/website.tar.gz,/web.tar.gz,/website.zip,/html.tar.gz,/htdocs.tar.gz,/public_html.tar.gz,/wp-content.zip,/wordpress.tar.gz,/wp-content.tar.gz,/wp.tar.gz,/uploads.zip,/data.zip,/export.zip,/files.zip,/content.zip,/dist.zip,/release.zip,/src.zip,/code.zip,/build.zip,/source.zip,/project.zip,/app.tar.gz,/backend.zip,/demo.zip,/new.zip,/test.zip,/api.zip,/admin.zip,/backup.tgz,/site.tar.bz2,/backup.tar.bz2,/db.tar.bz2,/backup.tbz2,/backups/backup.zip,/backups/site.zip,/backups/db.sql,/backup/site.zip,/backup/backup.zip,/backup/db.sql,/bak/backup.zip,/bak/site.zip,/old/site.zip,/old/backup.zip,/tmp/backup.zip,/dump/db.sql,/backup.tar,/backup.rar,/www.zip,/backup.7z,/site.tar.gz,/web.zip,/public_html.zip,/site.zip,/www.tar.gz,/public.zip,/html.zip,/wordpress.zip,/htdocs.zip,/old.zip,/archive.zip,/app.zip,/wp.zip,/wwwroot.zip,/db.zip,/db.tar.gz,/dump.sql,/db.sql,/mysql.sql,/site.sql,/data.sql,/wordpress.sql,/index.php.bak,/index.php.save,/index.php.txt,/.index.php.swp,/index.php.orig,/index.php.old,/.config.php.swp,/functions.php.bak,/database.php.bak,/db.php.bak,/config.inc.php.bak,/settings.php.bak,/index.php~,/wp-config.php.bak,/wp-config.php~,/.s3cfg,/configuration.php.bak,/auth.json,/.composer/auth.json,/.config/composer/auth.json,/.config/gh/hosts.yml,/serverless.yml,/docker-compose.yaml,/compose.yml,/compose.yaml,/docker-compose.production.yml,/docker-compose.prod.yml,/.aws/credentials,/.aws/config,/credentials,/.boto,/.config/aws/credentials,/config.json,/database.yml,/config/app.json,/api/appsettings.json,/appsettings.json,/appsettings.Production.json,/appsettings.Development.json,/config/secrets.yml,/config/aws.json,/parameters.yml,/app/config/parameters.yml,/config/parameters.yml,/config/packages/mailer.yaml,/web.config,/secrets.yml,/config/application.yml,/appsettings.Staging.json,/database.yaml,/xinpect.xingwangzhineng.com.zip,/xinpect.xingwangzhineng.com.tar.gz,/xinpect.xingwangzhineng.com.tar,/xinpect.xingwangzhineng.com.sql,/xinpect.xingwangzhineng.com.rar,/xinpect.xingwangzhineng.com.7z,/xinpect.zip,/xinpect.tar.gz,/xinpect.sql,/xinpect.tar,/xinpect.rar,/xinpect.7z,/.svn/entries,/.hg/requires,/.hg/store/requires,/.hg/dirstate,/api/session/properties,/wp-admin,/phpmyadmin,/wp-includes/wlwmanifest.xml,/blog/wp-includes/wlwmanifest.xml,/web/wp-includes/wlwmanifest.xml,/website/wp-includes/wlwmanifest.xml,/news/wp-includes/wlwmanifest.xml,/2020/wp-includes/wlwmanifest.xml,/2019/wp-includes/wlwmanifest.xml,/shop/wp-includes/wlwmanifest.xml,/wp1/wp-includes/wlwmanifest.xml,/test/wp-includes/wlwmanifest.xml,/wp2/wp-includes/wlwmanifest.xml,/site/wp-includes/wlwmanifest.xml,/cms/wp-includes/wlwmanifest.xml,/sito/wp-includes/wlwmanifest.xml,/health,/pages/about.html,/pages/product.html,/pages/pricing.html,/favicon.png,/.auth.json,/.azure-pipelines.yml,/.config/gcloud/configurations/config_default,/.config/gcloud/access_tokens.db,/.config/sftp.json,/.dockercfg,/.credentials,/.config/gcloud/credentials.db,/.docker/config.json,/.composer-auth.json,/.circleci/ssh-config,/.esmtprc,/.gem/credentials,/.git-credentials,/.gem/credentials.yaml,/.gitlab-ci.yml,/.lesshst,/.ksh_history,/.gitlab-ci/variables.yml,/.node_repl_history,/.m2/settings.xml,/.nuget/packages.config,/.pgpass,/.irb_history,/.mysql_history,/.msmtprc,/.postgresql_history,/.nuget/nuget.config,/.my.cnf,/.pry_history,/.wget-hsts,/.python_history,/.sqlite_history,/NuGet.Config,/.wgetrc,/.psql_history,/__ENV.js,/.sh_history,/.viminfo,/Properties/launchSettings.json,/GoogleService-Info.plist,/_config.yml,/_netrc,/access_tokens.db,/actuator/conditions,/actuator/caches,/actuator/beans,/actuator/logfile,/admin/auth.json,/actuator/jolokia,/actuator/env,/actuator/loggers,/actuator/threaddump,/actuator/startup,/actuator/configprops,/actuator/mappings,/actuator/httptrace,/actuator/loggingConfig,/actuator/httpexchanges,/android/app/google-services.json,/api/auth.json,/api/postman.json,/app/auth.json,/app/config/pimcore/google-api-private-key.json,/app/etc/local.xml.additional,/app/etc/local.xml,/application.yaml,/app/google-services.json,/app/settings.py,/app/config/parameters.yml.dist,/application.properties,/application.yml,/assets/auth.json,/artemis/actuator/env,/assets/credentials.json,/assets/other/service-account-credentials.json,/backup/auth.json,/client_secrets.json,/backup/config.xml,/cloud-config.txt,/cloud-config.yml,/backup/ovh-backups.json,/backups/auth.json,/collections/postman.json,/conf/settings.xml,/config.php.bak,/config.php.save,/config.properties,/config.php.old,/config.properties.bak,/config.yaml,/config.php.dist,/config.php.txt,/config.yml,/config/auth.json,/config/database.yml,/config/initializers/secret_token.rb,/config/ovh-backups.json,/config/storage.yml,/credentials.json,/config/settings.yml,/credentials.db,/credentials/auth.json,/core-cloud-config.yml,/configurations/config_default,/database_credentials.inc,/data/auth.json,/deployment-config.json,/django/settings.py,/docs/postman.json,/env-config.js,/env.dev.js,/env.development.js,/env.test.js,/env.production.js,/env.prod.js,/google-services.json,/google-api-private-key.json,/host.json,/launchSettings.json,/message-api/actuator/env,/keycloak.json,/node_repl_history,/nuget.config,/packages.config,/parameters.yml.dist,/pimcore/app/config/pimcore/google-api-private-key.json,/oauth-credentials.json,/ovh-backups.json,/postman.json,/postman_collection.json,/psql_history,/public/auth.json,/gitlab-ci.yml,/public/config.js,/railsapp/config/storage.yml,/redmine/config/initializers/secret_token.rb,/ruby/config/storage.yml,/s3cmd.ini,/redmine/config/settings.yml,/redmine/config/secrets.yml,/search/token.json,/secret.json,/secret_token.rb,/service-account-credentials.json,/serviceAccountCredentials.json,/settings.json,/settings.php.dist,/settings.php.old,/settings.php.save,/settings.yml,/settings.php.txt,/sftp-config.json,/sftp.json,/settings/settings.py,/settings.py,/settings.xml,/sites/default/settings.php.bak,/sites/default/settings.php.old,/sites/default/settings.php.orig,/sites/default/settings.php.save,/src/auth.json,/storage.yml,/storage/ovh-backups.json,/test/config/secrets.yml,/store/app/etc/local.xml,/user_secrets.yml.old,/token.json,/web/auth.json,/web/settings/settings.py,/wgetrc,/vendor/webmozart/assert/.composer-auth.json,/wp-config.php.old,/wp-config.php.save,/www/auth.json,/ws-config.json,/appveyor.yml,/.buildkite/pipeline.yml,/buildkite.yml,/circle.yml,/Jenkinsfile,/jenkins.yaml,/.semaphore/semaphore.yml,/wercker.yml,/codeship-services.yml,/codeship-steps.yml,/bamboo.yml,/bitrise.yml,/.github/workflows/build.yml,/.github/workflows/deploy.yml,/.github/workflows/main.yml,/.github/workflows/ci.yml,/terraform.tfvars,/terraform.tfstate,/terraform.tfstate.backup,/secrets.tfvars,/credentials.tfvars,/variables.tfvars,/serverless.yaml,/docker-compose.override.yml,/docker-compose.local.yml,/src/config.js,/config.toml,/settings.toml,/config.ini,/credentials.yml,/secrets.properties,/credentials.yaml,/application-secrets.yml,/application-secrets.properties,/db_dump.sql,/mysql_dump.sql,/actuator/trace,/dump.sql.bak,/backup.sql.bak,/public/env.js

## 🌐 错误来源 IP TOP 10
| IP地址 | 错误次数 |
|--------|----------|
| 127.0.0.1 | 540 |

## ❌ 未解决错误详情（共517条）

### #2921 HTTP_ERROR - /config.json
- **时间**: 2026-10-07 20:46:40
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_7_0) AppleWebKit/535.11 (KHTML, like Gecko) Chrome/17.0.96

### #2920 HTTP_ERROR - /config.json
- **时间**: 2026-10-07 20:34:50
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_7_0) AppleWebKit/535.11 (KHTML, like Gecko) Chrome/17.0.96

### #2919 HTTP_ERROR - /favicon.png
- **时间**: 2026-10-07 20:23:50
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: okhttp/5.3.0

### #2918 HTTP_ERROR - /favicon.png
- **时间**: 2026-10-07 20:03:46
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: okhttp/5.3.0

### #2916 HTTP_ERROR - /site.sql
- **时间**: 2026-10-07 19:09:23
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Sa

### #2917 HTTP_ERROR - /public/env.js
- **时间**: 2026-10-07 19:09:23
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.3

### #2915 HTTP_ERROR - /backup.sql.bak
- **时间**: 2026-10-07 19:09:22
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.

### #2912 HTTP_ERROR - /actuator/trace
- **时间**: 2026-10-07 19:09:21
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.3

### #2913 HTTP_ERROR - /data.sql
- **时间**: 2026-10-07 19:09:21
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.3

### #2910 HTTP_ERROR - /mysql.sql
- **时间**: 2026-10-07 19:09:20
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.3

### #2911 HTTP_ERROR - /mysql_dump.sql
- **时间**: 2026-10-07 19:09:20
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.3

### #2908 HTTP_ERROR - /db.sql
- **时间**: 2026-10-07 19:09:19
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.3

### #2909 HTTP_ERROR - /db_dump.sql
- **时间**: 2026-10-07 19:09:19
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.

### #2904 HTTP_ERROR - /application-secrets.yml
- **时间**: 2026-10-07 19:09:18
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.

### #2905 HTTP_ERROR - /compose.yml
- **时间**: 2026-10-07 19:09:18
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.

### #2907 HTTP_ERROR - /application-secrets.properties
- **时间**: 2026-10-07 19:09:18
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.3

### #2902 HTTP_ERROR - /secrets.properties
- **时间**: 2026-10-07 19:09:17
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.3

### #2903 HTTP_ERROR - /credentials.yaml
- **时间**: 2026-10-07 19:09:17
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Sa

### #2901 HTTP_ERROR - /credentials.yml
- **时间**: 2026-10-07 19:09:16
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.3

### #2900 HTTP_ERROR - /config.ini
- **时间**: 2026-10-07 19:09:15
- **方式**: GET
- **状态码**: 404
- **消息**: HTTP 404
- **IP**: 127.0.0.1
- **来源**: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.3

...还有 497 条未解决错误

## 🛡️ 安全扫描器探测摘要（已排除，共23条）
这些是自动化漏洞扫描工具的探测行为，非真实API错误。

| 探测类型 | 次数 |
|----------|------|
| 其他探测 | 10 |
| 云凭证探测 | 9 |
| WordPress扫描探测 | 4 |
