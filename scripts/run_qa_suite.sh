#!/bin/bash
# ============================================================================
# 煋鉴 QA 巡检 + 扩展测试 统一入口（2026-11-03 交接整改）
#
# 为什么要有这个脚本（三个根因，写在这里免得下次再踩）：
#   1. 两段任务都要 /etc/xinpect/website.env 里的 XINPECT_SECRET，
#      裸跑 python 会直接 RuntimeError 拒绝启动 -> 环境变量只在这里 source 一次
#   2. 原来 crontab 用 && 串联，巡检一有 P0（退出码非零）扩展测试就永不执行，
#      extended_tests.log 一直是空文件 —— 这里改成顺序执行，互不影响
#   3. 之前机器上根本没装 pytest，`python3 -m pytest` 直接报错，所以改成
#      先做可用性检查，缺依赖时明确报出来，而不是静默失败
# ============================================================================
set -uo pipefail

APP=/opt/xinpect-website
REPORTS="$APP/tests/reports"
cd "$APP" || exit 1
mkdir -p "$REPORTS"

set -a
# shellcheck disable=SC1091
. /etc/xinpect/website.env
set +a

# ---- 6m. 分享报告页守卫（2026-11-09）----
# 分享页是站里唯一的深色版面，以前没有令牌可用，做的时候自己抄了一套 Tailwind Slate：
# 72 分那个大数字、问题总数、页脚链接在卡片上只有 1.52:1，次要文字一律 3.73:1——
# 不是不好看，是根本看不见，整页发灰发糊。重做后颜色全部来自 tokens.css 的
# --color-dark-* / *-on-dark。守卫查四件事：模板无裸色值、不引用按值生成的字面量
# 变量、引用的变量都真有定义、真渲染下屏幕与打印态对比度都 >= 4.5:1。
# 自带造坏自检；藏守卫即套件不能绿。
SHARE_GUARD=/opt/xinpect-website/tests/verify_share_page.py
if [ -f "$SHARE_GUARD" ]; then
    echo "[$(date '+%F %T')] 分享报告页守卫开始"
    env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "$SHARE_GUARD" 2>&1 | tee -a "$REPORTS/extended_tests.log"
    _sharerc=${PIPESTATUS[0]}
    [ "$_sharerc" -ne 0 ] && COST_RC=1
    env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "$SHARE_GUARD" --self-test 2>&1 | tee -a "$REPORTS/extended_tests.log"
    _sharesrc=${PIPESTATUS[0]}
    [ "$_sharesrc" -ne 0 ] && COST_RC=1
    echo "[$(date '+%F %T')] 分享报告页守卫结束 rc=$_sharerc 自检 rc=$_sharesrc"
else
    echo "[$(date '+%F %T')] ❌ 分享报告页守卫缺失，套件不能绿: $SHARE_GUARD" | tee -a "$REPORTS/extended_tests.log"
    COST_RC=1
fi

# ---- 6n. 浅底版面层级守卫（2026-11-09）----
# 全站以前只有一个 --color-bg-primary，它同时当「页面底色」和「白字颜色」，
# 页面白、卡片也白，卡片只能靠一条 1.17:1 的边撑着，人眼看到的就是平。
# 本轮把面拆成 页面/卡片/内嵌 三级 + 投影，并把白字改走 --color-text-inverse。
# 守卫查四件事：令牌齐且三级分得开、模板里不许再有裸色值、
# 一个令牌不许再当两个意思、真渲染下卡片浮得起且卡片上的字都 >= 4.5:1。
# 自带 10 类造坏自检；藏守卫即套件不能绿。
SURFACE_GUARD=/opt/xinpect-website/tests/verify_surfaces.py
if [ -f "$SURFACE_GUARD" ]; then
    echo "[$(date '+%F %T')] 浅底版面守卫开始"
    env XP_SITE=/opt/xinpect-website XP_BASE=http://127.0.0.1:8621 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "$SURFACE_GUARD" 2>&1 | tee -a "$REPORTS/extended_tests.log"
    _surfrc=${PIPESTATUS[0]}
    [ "$_surfrc" -ne 0 ] && COST_RC=1
    env XP_SITE=/opt/xinpect-website XP_BASE=http://127.0.0.1:8621 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "$SURFACE_GUARD" --self-test 2>&1 | tee -a "$REPORTS/extended_tests.log"
    _surfsrc=${PIPESTATUS[0]}
    [ "$_surfsrc" -ne 0 ] && COST_RC=1
    echo "[$(date '+%F %T')] 浅底版面守卫结束 rc=$_surfrc 自检 rc=$_surfsrc"
else
    echo "[$(date '+%F %T')] ❌ 浅底版面守卫缺失，套件不能绿: $SURFACE_GUARD" | tee -a "$REPORTS/extended_tests.log"
    COST_RC=1
fi

# ---- 6o. 徽章接口守卫（2026-11-09）----
# /api/badge/<scan_id>.svg 是给 GitHub README 贴分数用的，以前没有任何守卫。
# 三档用了 #4c1 / #FF6B35 / #e05d44，白字压在上面只有 2.12 / 2.84 / 3.61 ——
# 绿色那档等于看不见；而且 scan 查不到时返回「0 需改进」，
# 把「没有这条记录」说成「评测过、极差」。
# 现在三档色值一律从 tokens.css 取（不在这里写第二份色表），
# 判据：三档白字 >= 4.5:1、三档颜色互不相同、色值必须在 tokens 里、
# 查不到的 scan 写「未知」不冒充等级。自带造坏自检；藏守卫即套件不能绿。
BADGE_GUARD=/opt/xinpect-website/tests/verify_badge.py
if [ -f "$BADGE_GUARD" ]; then
    echo "[$(date '+%F %T')] 徽章接口守卫开始"
    env XP_SITE=/opt/xinpect-website XP_BASE=http://127.0.0.1:8621 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "$BADGE_GUARD" 2>&1 | tee -a "$REPORTS/extended_tests.log"
    _badgerc=${PIPESTATUS[0]}
    [ "$_badgerc" -ne 0 ] && COST_RC=1
    env XP_SITE=/opt/xinpect-website XP_BASE=http://127.0.0.1:8621 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "$BADGE_GUARD" --self-test 2>&1 | tee -a "$REPORTS/extended_tests.log"
    _badgesrc=${PIPESTATUS[0]}
    [ "$_badgesrc" -ne 0 ] && COST_RC=1
    echo "[$(date '+%F %T')] 徽章接口守卫结束 rc=$_badgerc 自检 rc=$_badgesrc"
else
    echo "[$(date '+%F %T')] ❌ 徽章接口守卫缺失，套件不能绿: $BADGE_GUARD" | tee -a "$REPORTS/extended_tests.log"
    COST_RC=1
fi


# ---- 6p. 配色门禁（2026-11-09）----
# 两条腿，都是老板拍板的：
#   ① 装饰性的东西（会员徽章、描边、分隔线、页脚）走金/银，别再抄 Tailwind 橙；
#   ② 带含义的东西（严重度、状态、等级、评分档位）必须还是红绿黄，
#      不许为了"统一色调"把语义色也换成金属色（老板原话：不差这一点颜色）。
# 判据：
#   · 模板/样式/脚本里不许出现色相 20-70 的橙黄裸色；
#   · 不许引用 --color-v-<橙黄> 这种按值变量（要橙黄就引语义令牌）；
#   · 金属令牌必须存在且真被引用；
#   · 语义色令牌（red/warning/success + 四档严重度 + 配套淡底）必须存在且真被引用；
#   · 语义类选择器（severity/status/grade/trend/risk）上不许出现金属色；
#   · 注释里的旧色值不算用法；读不到的文件直接判红，不算通过。
# 自带造坏自检；藏守卫即套件不能绿。
METAL_GUARD=/opt/xinpect-website/tests/verify_metal_palette.py
if [ -f "$METAL_GUARD" ]; then
    echo "[$(date '+%F %T')] 金属色门禁开始"
    env XP_SITE=/opt/xinpect-website PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "$METAL_GUARD" 2>&1 | tee -a "$REPORTS/extended_tests.log"
    _metalrc=${PIPESTATUS[0]}
    [ "$_metalrc" -ne 0 ] && COST_RC=1
    env XP_SITE=/opt/xinpect-website PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "$METAL_GUARD" --self-test 2>&1 | tee -a "$REPORTS/extended_tests.log"
    _metalsrc=${PIPESTATUS[0]}
    [ "$_metalsrc" -ne 0 ] && COST_RC=1
    echo "[$(date '+%F %T')] 金属色门禁结束 rc=$_metalrc 自检 rc=$_metalsrc"
else
    echo "[$(date '+%F %T')] ❌ 金属色门禁缺失，套件不能绿: $METAL_GUARD" | tee -a "$REPORTS/extended_tests.log"
    COST_RC=1
fi


echo "=========================================================="
echo "[$(date '+%F %T')] QA 套件开始"

# ---- 1. 巡检 ----
/usr/bin/python3 -u tests/qa_guardian.py --level 123
QA_RC=$?
echo "[$(date '+%F %T')] QA 巡检结束 rc=$QA_RC"

# ---- 2. 扩展测试（无论巡检结果如何都跑）----
if ! /usr/bin/python3 -c "import pytest" 2>/dev/null; then
    echo "[$(date '+%F %T')] ❌ pytest 不可用，扩展测试跳过（先装 python3-pytest）" | tee -a "$REPORTS/extended_tests.log"
    # 留存守卫自带 __main__，不依赖 pytest，单独跑一遍
    PY_RC=0
    # 逐条累积退出码：以前这里串跑 28 条只取最后一条的 PIPESTATUS，
    # 前面坏了也照样绿（2026-11-23 修）。
    for _t in \
        test_retention.py \
        test_beian.py \
        test_free_try_funnel.py \
        test_lang_detect.py \
        test_funnel_analytics.py \
        test_try_quota.py \
        test_engine_coverage.py \
        test_bb_dimension.py \
        test_scoring_single_source.py \
        test_retired_rules_gate.py \
        test_rule_semantic_gate.py \
        test_membership_reminder.py \
        test_membership_renewal.py \
        test_paid_fulfillment.py \
        test_scan_cache_retention.py \
        test_cron_jobs_liveness.py \
        test_selfcheck_alerts.py \
        test_offsite_backup.py \
        test_uptime_watchdog.py \
        test_payment_reconcile.py \
        test_scan_cost_report.py \
        test_health_check_budget.py \
        test_scan_chunk_yield.py \
        test_dispatcher_import_safety.py \
        test_template_attr_blocks.py \
        test_narrow_toolbar_wrap.py \
        test_no_db_dumps_tracked.py \
        test_repo_secrets_guard.py \
        test_brain_label_alias.py \
        test_grade_risk_cap.py \
        test_style_not_scored.py \
        test_outbound_numbers.py \
        test_nav_single_source.py \
        test_safe_write_contract.py \
        test_scenario_checklist.py \
        test_report_export.py \
        test_upgrade_url_is_reachable.py \
        test_dashboard_mobile.py \
        test_mobile_responsive.py \
        test_qa_mount_completeness.py
    do
        /usr/bin/python3 "tests/$_t" 2>&1 | tee -a "$REPORTS/extended_tests.log"
        [ "${PIPESTATUS[0]}" -ne 0 ] && PY_RC=1
    done

else
    /usr/bin/python3 -m pytest \
        tests/test_business_logic.py \
        tests/test_consistency.py \
        tests/test_security_extended.py \
        tests/test_retention.py \
        tests/test_beian.py \
        tests/test_free_try_funnel.py \
        tests/test_lang_detect.py \
        tests/test_funnel_analytics.py \
        tests/test_try_quota.py \
        tests/test_engine_coverage.py \
        tests/test_category_dimension.py \
        tests/test_bb_dimension.py \
        tests/test_report_dimensions.py \
        tests/test_scoring_single_source.py \
        tests/test_retired_rules_gate.py \
        tests/test_rule_semantic_gate.py \
        tests/test_dashboard_mobile.py \
        tests/test_mobile_responsive.py \
        tests/test_membership_reminder.py \
        tests/test_membership_renewal.py \
        tests/test_paid_fulfillment.py \
        tests/test_scan_cache_retention.py \
        tests/test_cron_jobs_liveness.py \
        tests/test_selfcheck_alerts.py \
        tests/test_offsite_backup.py \
        tests/test_uptime_watchdog.py \
        tests/test_payment_reconcile.py \
        tests/test_health_check_budget.py \
        tests/test_scan_chunk_yield.py \
        tests/test_dispatcher_import_safety.py \
        tests/test_scan_cost_report.py \
        tests/test_template_attr_blocks.py \
        tests/test_narrow_toolbar_wrap.py \
        tests/test_no_db_dumps_tracked.py \
        tests/test_repo_secrets_guard.py \
        tests/test_brain_label_alias.py \
        tests/test_grade_risk_cap.py \
        tests/test_style_not_scored.py \
        tests/test_outbound_numbers.py \
        tests/test_nav_single_source.py \
        tests/test_safe_write_contract.py \
        tests/test_scenario_checklist.py \
        tests/test_report_export.py \
        tests/test_upgrade_url_is_reachable.py \
        tests/test_qa_mount_completeness.py \
        -q --tb=line 2>&1 | tee -a "$REPORTS/extended_tests.log"
    PY_RC=${PIPESTATUS[0]}
fi

# ---- 扫描成本守卫造坏自检（2026-11-17）----
# 为什么单开：pytest 只跑 test_ 函数，不会跑 --self-test。守卫如果自己不会红，
# 那它绿着也说明不了任何事。这一段故意把窗口上限/阈值改坏，确认对应测试真能抓住。
SCAN_COST_GUARD=/opt/xinpect-website/tests/test_scan_cost_report.py
if [ -f "$SCAN_COST_GUARD" ]; then
    /usr/bin/python3 "$SCAN_COST_GUARD" --self-test 2>&1 | tee -a "$REPORTS/extended_tests.log"
    _scrc=${PIPESTATUS[0]}
    [ "$_scrc" -ne 0 ] && COST_RC=1
    echo "[$(date '+%F %T')] 扫描成本守卫造坏自检 rc=$_scrc"
else
    echo "[$(date '+%F %T')] ❌ 扫描成本守卫缺失: $SCAN_COST_GUARD" | tee -a "$REPORTS/extended_tests.log"
    COST_RC=1
fi

# ---- 模板属性块守卫造坏自检（2026-11-17）----
# 报告页把整段 <script> 显示成了页面文字：标题块被写成了跨 105 行的大块，
# 母版又把标题块塞进 og:title 的 content 属性，引号一断源码就掉进正文。
# 这一段故意复刻那种写法，确认守卫真的会红。
TPL_GUARD=/opt/xinpect-website/tests/test_template_attr_blocks.py
if [ -f "$TPL_GUARD" ]; then
    /usr/bin/python3 "$TPL_GUARD" --self-test 2>&1 | tee -a "$REPORTS/extended_tests.log"
    _tplrc=${PIPESTATUS[0]}
    [ "$_tplrc" -ne 0 ] && COST_RC=1
    echo "[$(date '+%F %T')] 模板属性块守卫造坏自检 rc=$_tplrc"
else
    echo "[$(date '+%F %T')] ❌ 模板属性块守卫缺失: $TPL_GUARD" | tee -a "$REPORTS/extended_tests.log"
    COST_RC=1
fi

# ---- 工具条换行守卫造坏自检（2026-11-17）----
# 报告页「问题筛选」一行 9 个按钮没有 flex-wrap，390 宽手机上右边两个被裁掉，
# 而页面主体 overflow-x: clip，连横滑都滑不出来。这一段复刻那种写法，确认能判红。
TOOLBAR_GUARD=/opt/xinpect-website/tests/test_narrow_toolbar_wrap.py
if [ -f "$TOOLBAR_GUARD" ]; then
    /usr/bin/python3 "$TOOLBAR_GUARD" --self-test 2>&1 | tee -a "$REPORTS/extended_tests.log"
    _tbrc=${PIPESTATUS[0]}
    [ "$_tbrc" -ne 0 ] && COST_RC=1
    echo "[$(date '+%F %T')] 工具条换行守卫造坏自检 rc=$_tbrc"
else
    echo "[$(date '+%F %T')] ❌ 工具条换行守卫缺失: $TOOLBAR_GUARD" | tee -a "$REPORTS/extended_tests.log"
    COST_RC=1
fi
# ---- 访客口径守卫 + 造坏自检（2026-11-18）----
# 背景：报表上每天 1000~2000 个「独立访客」，同期真人扫描为 0。
# 查出来两件事：①我们自己的监控/守卫脚本（UA 以 xinpect- / xp- 开头）
# 没有命中爬虫正则，被算成了人；②漏洞扫描器打 /.env、/.git/config 这类
# 路径产生的 404，被当成了「访问了一个页面」。
# 两条加起来让「访客数」虚高 7 倍（1567 -> 218）。这个数字错了，
# 后面所有「有没有人来」「转化好不好」的判断都建在假数据上。
VISITOR_GUARD=/opt/xinpect-website/tests/verify_visitor_scope.py
VISITOR_SELFTEST=/opt/xinpect-website/tests/verify_visitor_scope_selftest.py
if [ -f "$VISITOR_GUARD" ] && [ -f "$VISITOR_SELFTEST" ]; then
    env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "$VISITOR_GUARD" 2>&1 | tee -a "$REPORTS/extended_tests.log"
    _vrc=${PIPESTATUS[0]}
    [ "$_vrc" -ne 0 ] && COST_RC=1
    echo "[$(date '+%F %T')] 访客口径守卫结束 rc=$_vrc"

    env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "$VISITOR_SELFTEST" 2>&1 | tee -a "$REPORTS/extended_tests.log"
    _vsrc=${PIPESTATUS[0]}
    [ "$_vsrc" -ne 0 ] && COST_RC=1
    echo "[$(date '+%F %T')] 访客口径造坏自检结束 rc=$_vsrc"
else
    echo "[$(date '+%F %T')] ❌ 访客口径守卫或自检缺失，套件不能绿" | tee -a "$REPORTS/extended_tests.log"
    COST_RC=1
fi

# ---- 3. 引擎侧分类守卫（2026-11-04）----
# 为什么要单开一段：官网 pytest 以 xinpect-web 跑，读不到 /opt/xinpect-scanner-green
# （属主 xinpect-scan），跨用户断言放 pytest 里只能 skip。E2 安全引擎产出的问题
# 必须 100% 归 security —— 这条钉不牢，报告就会重新出现「安全满分 + 越权高危」。
if [ -f /opt/xinpect-scanner-green/verify_category_output.py ]; then
    echo "[$(date '+%F %T')] 分类守卫开始"
    sudo -u xinpect-scan env PYTHONDONTWRITEBYTECODE=1 \
        /usr/bin/python3 /opt/xinpect-scanner-green/verify_category_output.py \
        2>&1 | tee -a "$REPORTS/extended_tests.log"
    CAT_RC=${PIPESTATUS[0]}
    echo "[$(date '+%F %T')] 分类守卫结束 rc=$CAT_RC"
else
    CAT_RC=0
fi

# ---- 4. 引擎侧跨文件污点 + 方言 + 误报证据守卫（2026-11-05，7 个，含能力台账）----
# 跨文件污点只在 green 上跑（属主 xinpect-scan）；这两个守卫挂了说明
# 「分层项目的注入又漏了」或「AI 又会凭没证据判误报」，都属于不能静默的问题。
ENG_RC=0
for _guard in verify_py_cross_taint.py verify_cross_file_taint.py verify_dart_taint.py verify_dialect_keys.py verify_cross_process_recall.py verify_fp_filter_evidence.py verify_e2_capability_wiring.py verify_file_batch_enhance.py verify_scan_budget.py verify_jev_batch_arbitration.py verify_tpm_limiter.py; do
    if [ -f "/opt/xinpect-scanner-green/tests/$_guard" ]; then
        echo "[$(date '+%F %T')] 引擎守卫 $_guard 开始"
        sudo -u xinpect-scan env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "/opt/xinpect-scanner-green/tests/$_guard" \
            2>&1 | tee -a "$REPORTS/extended_tests.log"
        _rc=${PIPESTATUS[0]}
        [ "$_rc" -ne 0 ] && ENG_RC=1
        echo "[$(date '+%F %T')] 引擎守卫 $_guard 结束 rc=$_rc"
    else
        echo "[$(date '+%F %T')] 引擎守卫 $_guard 缺失，套件不能绿" | tee -a "$REPORTS/extended_tests.log"
        ENG_RC=1
    fi
done

# ---- 4b. AI 增强「按文件批量」造坏自检（2026-11-18）----
# 改这块的动机是把「一条问题问两次 AI」压成「一个文件的一批问题问一次」。
# 省钱本身不是判据，判据是省完不能漏件、不能把判定标准改松：
# 模型少返回一条必须回退重问（不许静默当没问题）、dismissed 置信度不足必须降 review、
# 跨文件证据的 dismissed 必须降 review、阈值不许在两条链路上各写一份。
# 这一段把实现逐个改坏，确认守卫每次都判红；守卫自己瞎了比守卫失败更危险。
BATCH_SELFTEST=/opt/xinpect-scanner-green/tests/verify_file_batch_enhance_selftest.py
if [ -f "$BATCH_SELFTEST" ]; then
    echo "[$(date '+%F %T')] AI 批量增强造坏自检开始"
    env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "$BATCH_SELFTEST" 2>&1 | tee -a "$REPORTS/extended_tests.log"
    _bsrc=${PIPESTATUS[0]}
    [ "$_bsrc" -ne 0 ] && ENG_RC=1
    echo "[$(date '+%F %T')] AI 批量增强造坏自检结束 rc=$_bsrc"
else
    echo "[$(date '+%F %T')] ❌ AI 批量增强造坏自检缺失，套件不能绿: $BATCH_SELFTEST" | tee -a "$REPORTS/extended_tests.log"
    ENG_RC=1
fi

# ---- 4c. 扫描工期的造坏自检（2026-11-18）----
# 4 段里的 verify_scan_budget.py 钉的是「一次扫描必须有工期」：
# 判定类提问 30 秒、生成类 120 秒、预算用完一次请求都不发、上游连续不回话就熔断、
# 阶段超时就降级出报告而不是陪着一直等。这一段把实现逐个改坏，确认守卫都判红。
# 背景：11-18 一次 VIP 扫描在仲裁上卡了 22 分钟，期间所有用户被 503 挡回。
BUDGET_SELFTEST=/opt/xinpect-scanner-green/tests/verify_scan_budget_selftest.py
if [ -f "$BUDGET_SELFTEST" ]; then
    echo "[$(date '+%F %T')] 扫描工期造坏自检开始"
    env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "$BUDGET_SELFTEST" 2>&1 | tee -a "$REPORTS/extended_tests.log"
    _sbrc=${PIPESTATUS[0]}
    [ "$_sbrc" -ne 0 ] && ENG_RC=1
    echo "[$(date '+%F %T')] 扫描工期造坏自检结束 rc=$_sbrc"
else
    echo "[$(date '+%F %T')] ❌ 扫描工期造坏自检缺失，套件不能绿: $BUDGET_SELFTEST" | tee -a "$REPORTS/extended_tests.log"
    ENG_RC=1
fi

# ---- 4d. 仲裁合批的造坏自检（2026-11-18）----
# 4 段里的 verify_jev_batch_arbitration.py 钉的是「合批之后结论不变」：
# 调用次数必须按「批数×温度」走（不是条数×温度）、每条问题仍拿满每个温度各一票、
# 共识算法只有一份（单条与批量对同一批票给同一个数）、漏返回的必须退回单条问、
# 解析失败不许凭空补值、预算用完必须往上抛、连续不回话必须熔断。
# 背景：11-18 实测 40 次调用里全是「同一份判定规则发了 20 遍」。
JEV_BATCH_SELFTEST=/opt/xinpect-scanner-green/tests/verify_jev_batch_selftest.py
if [ -f "$JEV_BATCH_SELFTEST" ]; then
    echo "[$(date '+%F %T')] 仲裁合批造坏自检开始"
    env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "$JEV_BATCH_SELFTEST" 2>&1 | tee -a "$REPORTS/extended_tests.log"
    _jbrc=${PIPESTATUS[0]}
    [ "$_jbrc" -ne 0 ] && ENG_RC=1
    echo "[$(date '+%F %T')] 仲裁合批造坏自检结束 rc=$_jbrc"
else
    echo "[$(date '+%F %T')] ❌ 仲裁合批造坏自检缺失，套件不能绿: $JEV_BATCH_SELFTEST" | tee -a "$REPORTS/extended_tests.log"
    ENG_RC=1
fi

echo "[$(date '+%F %T')] 扩展测试结束 rc=$PY_RC"

# ---- 4e. 每分钟 token 额度的造坏自检（2026-11-18）----
# 背景：429 报的是 ModelAccountFlexTpmRateLimitExceeded，上游限的是
# 「每分钟 token」，而我们的限速器数的是「每分钟 30 次」。合批之后单次
# 调用从 280 token 涨到两三千，30 次 = 9 万 token/分钟 —— 次数没超，
# token 早超了，限速器等于不存在。实测撞线那一刻记了 41067 token。
# 这一段把实现改回数次数 / 丢请求 / 额度乱填，确认守卫每次都判红。
TPM_SELFTEST=/opt/xinpect-scanner-green/tests/verify_tpm_limiter_selftest.py
if [ -f "$TPM_SELFTEST" ]; then
    echo "[$(date +%F\ %T)] 每分钟额度造坏自检开始"
    env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "$TPM_SELFTEST" 2>&1 | tee -a "$REPORTS/extended_tests.log"
    _tprc=${PIPESTATUS[0]}
    [ "$_tprc" -ne 0 ] && ENG_RC=1
    echo "[$(date +%F\ %T)] 每分钟额度造坏自检结束 rc=$_tprc"
else
    echo "[$(date +%F\ %T)] ❌ 每分钟额度造坏自检缺失，套件不能绿: $TPM_SELFTEST" | tee -a "$REPORTS/extended_tests.log"
    ENG_RC=1
fi

# ---- 5. 基准诚实性守卫（2026-11-04）----
# 旧基准脚本标题写绿版实际打蓝版、state 复用导致「一次没扫也出 100 分」。
# 这一段钉住：唯一入口在、历史脚本全失效、结果文件自带端口与实扫数。
BEN_RC=0
if [ -f /home/ubuntu/BenchmarkJava/verify_benchmark_entry.py ]; then
    echo "[$(date '+%F %T')] 基准诚实性守卫开始"
    /usr/bin/python3 /home/ubuntu/BenchmarkJava/verify_benchmark_entry.py \
        2>&1 | tee -a "$REPORTS/extended_tests.log"
    BEN_RC=${PIPESTATUS[0]}
    echo "[$(date '+%F %T')] 基准诚实性守卫结束 rc=$BEN_RC"
fi

# ---- 6. 成本告警可判定守卫（2026-11-05）----
# 网关告警以前「有记录≠送达」：邮件发失败只写一条 warning，运维看不到；
# 且只报原价（含缓存折算），与火山账期扣款对不上。这一段钉住台账与送达状态。
# 守卫要读 /home/ubuntu/ai-cost-optimizer（属主 ubuntu），必须 root 跑，
# 不能塞进第 4 段那个 sudo -u xinpect-scan 的循环。
# 这里只能初始化，不能写死 0：6m/6n/6o 跑在本行之前，
# 写死会把它们判红的结果静默清零，套件照样报 cost=0（假绿）。
COST_RC=${COST_RC:-0}
COST_GUARD=/opt/xinpect-scanner-green/tests/verify_cost_alert_ledger.py
if [ -f "$COST_GUARD" ]; then
    echo "[$(date '+%F %T')] 成本告警守卫开始"
    env PYTHONDONTWRITEBYTECODE=1 COSTVALVE_ROOT=/home/ubuntu/ai-cost-optimizer \
        /usr/bin/python3 "$COST_GUARD" 2>&1 | tee -a "$REPORTS/extended_tests.log"
    COST_RC=${PIPESTATUS[0]}
    echo "[$(date '+%F %T')] 成本告警守卫结束 rc=$COST_RC"
else
    echo "[$(date '+%F %T')] ❌ 成本告警守卫缺失，套件不能绿: $COST_GUARD" | tee -a "$REPORTS/extended_tests.log"
    COST_RC=1
fi

# ---- 6b. 节能阀逃生门可判定守卫（2026-11-05）----
# 主站以前「网关一失败就静默直连」，日志会轮转、网关账本只统计经网关的请求，
# 于是「多少流量绕过节能阀」永远不可判定，直到火山账单出来才发现。
# 守卫只读源码 + 临时台账，绝不创建生产台账文件，必须 root 跑。
BYPASS_GUARD=/opt/xinpect-website/tests/verify_bypass_ledger.py
if [ -f "$BYPASS_GUARD" ]; then
    echo "[$(date '+%F %T')] 节能阀逃生门守卫开始"
    env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "$BYPASS_GUARD" 2>&1 | tee -a "$REPORTS/extended_tests.log"
    _brc=${PIPESTATUS[0]}
    [ "$_brc" -ne 0 ] && COST_RC=1
    echo "[$(date '+%F %T')] 节能阀逃生门守卫结束 rc=$_brc"
else
    echo "[$(date '+%F %T')] ❌ 逃生门守卫缺失，套件不能绿: $BYPASS_GUARD" | tee -a "$REPORTS/extended_tests.log"
    COST_RC=1
fi

# ---- 6c. 进度条真实性守卫（2026-11-05）----
# 上传页原先每 0.35 秒随机加百分比、编 11 条阶段；用户看到的只是装样子。
# 守卫读源码 + 数据库列，并自带 --self-test 造坏副本确认自己会判红。
PROGRESS_GUARD=/opt/xinpect-website/tests/verify_scan_progress_truth.py
if [ -f "$PROGRESS_GUARD" ]; then
    echo "[$(date '+%F %T')] 进度真实性守卫开始"
    env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "$PROGRESS_GUARD" 2>&1 | tee -a "$REPORTS/extended_tests.log"
    _prc=${PIPESTATUS[0]}
    [ "$_prc" -ne 0 ] && COST_RC=1
    env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "$PROGRESS_GUARD" --self-test 2>&1 | tee -a "$REPORTS/extended_tests.log"
    _src=${PIPESTATUS[0]}
    [ "$_src" -ne 0 ] && COST_RC=1
    echo "[$(date '+%F %T')] 进度真实性守卫结束 rc=$_prc 自检 rc=$_src"
else
    echo "[$(date '+%F %T')] ❌ 进度真实性守卫缺失，套件不能绿: $PROGRESS_GUARD" | tee -a "$REPORTS/extended_tests.log"
    COST_RC=1
fi

# ---- 6d. 官网 UI 验收门禁（2026-11-06，Hallmark 当尺子不当装修队）----
# sloplint 一次报 791 条 FAIL，大半是英文落地页口味和中文误判；拿总数当 KPI 会逼人改歪品牌。
# 这一段只判 design.md + hallmark_floor_gates.json 认可的门禁是否 0 命中，且检查器版本固定。
# 守卫自带 --self-test 造坏副本确认自己会判红；藏守卫即套件不能绿。
UI_GUARD=/opt/xinpect-website/tests/verify_hallmark_floor.py
if [ -f "$UI_GUARD" ]; then
    echo "[$(date '+%F %T')] 官网 UI 门禁守卫开始"
    env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "$UI_GUARD" 2>&1 | tee -a "$REPORTS/extended_tests.log"
    _uirc=${PIPESTATUS[0]}
    [ "$_uirc" -ne 0 ] && COST_RC=1
    env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "$UI_GUARD" --self-test 2>&1 | tee -a "$REPORTS/extended_tests.log"
    _uisrc=${PIPESTATUS[0]}
    [ "$_uisrc" -ne 0 ] && COST_RC=1
    echo "[$(date '+%F %T')] 官网 UI 门禁守卫结束 rc=$_uirc 自检 rc=$_uisrc"
else
    echo "[$(date '+%F %T')] ❌ 官网 UI 门禁守卫缺失，套件不能绿: $UI_GUARD" | tee -a "$REPORTS/extended_tests.log"
    COST_RC=1
fi

# ---- 6e. 后端名字完整性守卫（2026-11-06）----
# 管理员错误统计页曾因漏导入 datetime 一打开就 500；同类问题全站共 6 处，
# 分散在 app.py / email_sender.py / helpers.py / referral.py。
# 守卫用固定版检查器扫全站源码 + 真实以管理员身份打开该页 + 对齐邮件函数签名；
# 自带 --self-test 造坏副本确认会判红；藏守卫即套件不能绿。
BACKEND_GUARD=/opt/xinpect-website/tests/verify_backend_names.py
if [ -f "$BACKEND_GUARD" ]; then
    echo "[$(date '+%F %T')] 后端名字完整性守卫开始"
    env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "$BACKEND_GUARD" 2>&1 | tee -a "$REPORTS/extended_tests.log"
    _bgrc=${PIPESTATUS[0]}
    [ "$_bgrc" -ne 0 ] && COST_RC=1
    env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "$BACKEND_GUARD" --self-test 2>&1 | tee -a "$REPORTS/extended_tests.log"
    _bgsrc=${PIPESTATUS[0]}
    [ "$_bgsrc" -ne 0 ] && COST_RC=1
    echo "[$(date '+%F %T')] 后端名字完整性守卫结束 rc=$_bgrc 自检 rc=$_bgsrc"
else
    echo "[$(date '+%F %T')] ❌ 后端名字完整性守卫缺失，套件不能绿: $BACKEND_GUARD" | tee -a "$REPORTS/extended_tests.log"
    COST_RC=1
fi

# ---- 6f. 颜色真值与真渲染守卫（2026-11-08）----
# 11-06 收敛颜色时把 style.css 的 :root 定义写成了 `--x: var(--x)` 自引用，
# 后加载把 tokens.css 的真值覆盖掉，首页以外的内页整片失色。
# 之前的回归只查「页面打得开、字在不在」，查不出「人眼看到什么颜色」——这里补上：
# 静态查变量依赖图 + 无头浏览器取真实计算色值；守卫自带造坏自检，藏守卫即套件不能绿。
CSS_GUARD=/opt/xinpect-website/tests/verify_css_tokens.py
if [ -f "$CSS_GUARD" ]; then
    echo "[$(date '+%F %T')] 颜色真值守卫开始"
    env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "$CSS_GUARD" 2>&1 | tee -a "$REPORTS/extended_tests.log"
    _cssrc=${PIPESTATUS[0]}
    [ "$_cssrc" -ne 0 ] && COST_RC=1
    env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "$CSS_GUARD" --self-test 2>&1 | tee -a "$REPORTS/extended_tests.log"
    _csssrc=${PIPESTATUS[0]}
    [ "$_csssrc" -ne 0 ] && COST_RC=1
    echo "[$(date '+%F %T')] 颜色真值守卫结束 rc=$_cssrc 自检 rc=$_csssrc"
else
    echo "[$(date '+%F %T')] ❌ 颜色真值守卫缺失，套件不能绿: $CSS_GUARD" | tee -a "$REPORTS/extended_tests.log"
    COST_RC=1
fi

# ---- 6g. 冷光质感与装饰色红线守卫（2026-11-08）----
# 用户 10-26 定的五行配色红线：藏青/白银蓝打底，装饰忌红橙（火克金）、忌土黄（土克水）；
# 报错红叉 / 警告黄叹号是提醒不是装饰，保留。真浏览器验按钮在 1080x640 等真人视口
# 完整落首屏、对比度 >= 4.5:1、装饰层不挡点击；守卫自带造坏自检，藏守卫即套件不能绿。
COOL_GUARD=/opt/xinpect-website/tests/verify_cool_palette.py
if [ -f "$COOL_GUARD" ]; then
    echo "[$(date '+%F %T')] 冷光质感守卫开始"
    env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "$COOL_GUARD" 2>&1 | tee -a "$REPORTS/extended_tests.log"
    _coolrc=${PIPESTATUS[0]}
    [ "$_coolrc" -ne 0 ] && COST_RC=1
    env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "$COOL_GUARD" --self-test 2>&1 | tee -a "$REPORTS/extended_tests.log"
    _coolsrc=${PIPESTATUS[0]}
    [ "$_coolsrc" -ne 0 ] && COST_RC=1
    echo "[$(date '+%F %T')] 冷光质感守卫结束 rc=$_coolrc 自检 rc=$_coolsrc"
else
    echo "[$(date '+%F %T')] ❌ 冷光质感守卫缺失，套件不能绿: $COOL_GUARD" | tee -a "$REPORTS/extended_tests.log"
    COST_RC=1
fi

# ---- 6h. 官网元素一致性守卫（2026-11-08）----
# 导航清单唯一依据 + 真请求 404 检查 + 语言数唯一 + 装饰暖色按语义分类 +
# 匿名首屏无老用户横幅 + 属主按服务身份 + 造坏自检。藏守卫即套件不能绿。
SITE_GUARD=/opt/xinpect-website/tests/verify_site_consistency.py
if [ -f "$SITE_GUARD" ]; then
    echo "[$(date '+%F %T')] 元素一致性守卫开始"
    env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "$SITE_GUARD" 2>&1 | tee -a "$REPORTS/extended_tests.log"
    _siterc=${PIPESTATUS[0]}
    [ "$_siterc" -ne 0 ] && COST_RC=1
    env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "$SITE_GUARD" --self-test 2>&1 | tee -a "$REPORTS/extended_tests.log"
    _sitesrc=${PIPESTATUS[0]}
    [ "$_sitesrc" -ne 0 ] && COST_RC=1
    echo "[$(date '+%F %T')] 元素一致性守卫结束 rc=$_siterc 自检 rc=$_sitesrc"
else
    echo "[$(date '+%F %T')] ❌ 元素一致性守卫缺失，套件不能绿: $SITE_GUARD" | tee -a "$REPORTS/extended_tests.log"
    COST_RC=1
fi

# ---- 6i. 点击响应真值守卫（2026-11-08）----
# 旧版用「页面上有没有几个 loading/弹窗 class」判点击有没有响应，还挂了一串按钮例外；
# 试扫换成新组件后，成功的扫描被报成 click_no_response，错误日志全是假警。
# 这里用真浏览器跑多种场景：真没动静必须报，按钮文字/节点/网址/网络有变化不许报。
CLICK_GUARD=/opt/xinpect-website/tests/verify_click_response.py
if [ -f "$CLICK_GUARD" ]; then
    echo "[$(date '+%F %T')] 点击响应守卫开始"
    env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "$CLICK_GUARD" 2>&1 | tee -a "$REPORTS/extended_tests.log"
    _clickrc=${PIPESTATUS[0]}
    [ "$_clickrc" -ne 0 ] && COST_RC=1
    env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "$CLICK_GUARD" --self-test 2>&1 | tee -a "$REPORTS/extended_tests.log"
    _clicksrc=${PIPESTATUS[0]}
    [ "$_clicksrc" -ne 0 ] && COST_RC=1
    echo "[$(date '+%F %T')] 点击响应守卫结束 rc=$_clickrc 自检 rc=$_clicksrc"
else
    echo "[$(date '+%F %T')] ❌ 点击响应守卫缺失，套件不能绿: $CLICK_GUARD" | tee -a "$REPORTS/extended_tests.log"
    COST_RC=1
fi

# ---- 6j. 整站文件指纹守卫（2026-11-08）----
# 之前的污染（对外说明、博客正文、两个模板被写回旧内容）靠人眼偶然发现，写入方查不到。
# 现在把整站交付文件的 md5 收进唯一基线，每次 QA 按同一口径重算：
# 新增 / 删除 / 内容变化一律判红；正规上线必须走 --update 重签基线并留追加日志。
FP_GUARD=/opt/xinpect-website/tests/verify_site_fingerprint.py
if [ -f "$FP_GUARD" ]; then
    echo "[$(date '+%F %T')] 整站文件指纹守卫开始"
    env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "$FP_GUARD" 2>&1 | tee -a "$REPORTS/extended_tests.log"
    _fprc=${PIPESTATUS[0]}
    [ "$_fprc" -ne 0 ] && COST_RC=1
    env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "$FP_GUARD" --self-test 2>&1 | tee -a "$REPORTS/extended_tests.log"
    _fpsrc=${PIPESTATUS[0]}
    [ "$_fpsrc" -ne 0 ] && COST_RC=1
    echo "[$(date '+%F %T')] 整站文件指纹守卫结束 rc=$_fprc 自检 rc=$_fpsrc"
else
    echo "[$(date '+%F %T')] ❌ 整站文件指纹守卫缺失，套件不能绿: $FP_GUARD" | tee -a "$REPORTS/extended_tests.log"
    COST_RC=1
fi

# ---- 6k. 引擎数量对外口径守卫（2026-11-08）----
# 页面写「7 大规则引擎」、控制台 overview 写「8 大」，靠人记谁对谁错迟早再漂移。
# 守卫不手抄正确数字：从运行时 BRAIN_MODULES 的 eN_ 前缀去重推导出引擎数，
# 再拿事实源、官网 BRAINS、全站对外文案逐条对账；把数字一起改掉也骗不过运行时代码。
ENGINE_GUARD=/opt/xinpect-website/tests/verify_engine_claims.py
if [ -f "$ENGINE_GUARD" ]; then
    echo "[$(date '+%F %T')] 引擎口径守卫开始"
    env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "$ENGINE_GUARD" 2>&1 | tee -a "$REPORTS/extended_tests.log"
    _engrc=${PIPESTATUS[0]}
    [ "$_engrc" -ne 0 ] && COST_RC=1
    env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "$ENGINE_GUARD" --self-test 2>&1 | tee -a "$REPORTS/extended_tests.log"
    _engsrc=${PIPESTATUS[0]}
    [ "$_engsrc" -ne 0 ] && COST_RC=1
    echo "[$(date '+%F %T')] 引擎口径守卫结束 rc=$_engrc 自检 rc=$_engsrc"
else
    echo "[$(date '+%F %T')] ❌ 引擎口径守卫缺失，套件不能绿: $ENGINE_GUARD" | tee -a "$REPORTS/extended_tests.log"
    COST_RC=1
fi

# ---- 6l. 转化链路与报告样例守卫（2026-11-08）----
# 报告样例的数字必须来自生产扫描器真跑，页面不许手抄；入口必须真发 HTTP 请求可达。
GROWTH_GUARD=/opt/xinpect-website/tests/verify_growth_funnel.py
if [ -f "$GROWTH_GUARD" ]; then
    echo "[$(date '+%F %T')] 转化链路守卫开始"
    env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "$GROWTH_GUARD" 2>&1 | tee -a "$REPORTS/extended_tests.log"
    _growthrc=${PIPESTATUS[0]}
    [ "$_growthrc" -ne 0 ] && COST_RC=1
    env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "$GROWTH_GUARD" --self-test 2>&1 | tee -a "$REPORTS/extended_tests.log"
    _growthsrc=${PIPESTATUS[0]}
    [ "$_growthsrc" -ne 0 ] && COST_RC=1
    echo "[$(date '+%F %T')] 转化链路守卫结束 rc=$_growthrc 自检 rc=$_growthsrc"
else
    echo "[$(date '+%F %T')] ❌ 转化链路守卫缺失，套件不能绿: $GROWTH_GUARD" | tee -a "$REPORTS/extended_tests.log"
    COST_RC=1
fi

# ---- 6m. 技能付费网关守卫（payserver · 2026-11-14 恢复 PDF 通道时补）----
# 这个通道上次停掉的真实原因不是「服务坏了」，而是「坏了没人知道」：收了 1.49 元、
# 履约代码缺 engine.b10_sca，躺了几个月没人发现。恢复之后必须让每一轮套件都真的
# 跑一遍「下单 → 支付 → 履约 → 退款回写」的账本逻辑，否则下次坏掉还是没人知道。
PAY_RC=0
if ss -lntH 2>/dev/null | grep -q '127.0.0.1:8010'; then
    echo "[$(date '+%F %T')] 技能付费网关守卫开始"
    sudo -u ubuntu bash -c 'cd /home/ubuntu/payserver && /usr/bin/python3 -m pytest tests/test_payflow.py tests/test_refund_reconcile.py -q --tb=line' 2>&1 | tee -a "$REPORTS/extended_tests.log"
    PAY_RC=${PIPESTATUS[0]}
    echo "[$(date '+%F %T')] 技能付费网关守卫结束 rc=$PAY_RC"
else
    echo "[$(date '+%F %T')] ❌ 技能付费网关没在跑（8010 无监听），套件不能绿" | tee -a "$REPORTS/extended_tests.log"
    PAY_RC=1
fi

echo "=========================================================="

# 六段各自的退出码都要算进来：之前只算 QA_RC/PY_RC，分类守卫和引擎守卫
# 失败了套件照样 exit 0 —— 绿着红掉，比没有守卫更危险。
if [ "$QA_RC" -ne 0 ] || [ "$PY_RC" -ne 0 ] || [ "$CAT_RC" -ne 0 ] || [ "$ENG_RC" -ne 0 ] || [ "$BEN_RC" -ne 0 ] || [ "$COST_RC" -ne 0 ] || [ "${PAY_RC:-0}" -ne 0 ]; then
    echo "❌ 套件失败: qa=$QA_RC pytest=$PY_RC category=$CAT_RC engine=$ENG_RC bench=$BEN_RC cost=$COST_RC pay=${PAY_RC:-0}"
    # 结论必须落成文件：只写 cron.log，等于没人知道（监控每 15 分钟读这个文件）
    /usr/bin/python3 /opt/xinpect-website/scripts/record_qa_result.py fail \
        qa=$QA_RC pytest=$PY_RC category=$CAT_RC engine=$ENG_RC \
        bench=$BEN_RC cost=$COST_RC pay=${PAY_RC:-0} || true
    exit 1
fi
# 成功也要留一行。此前成功时一行都不打，crontab 日志里和「脚本崩在半路」
# 长得一模一样 —— 排查的人只能靠猜。
echo "✅ 套件通过: qa=0 pytest=0 category=0 engine=0 bench=0 cost=0 pay=0"
/usr/bin/python3 /opt/xinpect-website/scripts/record_qa_result.py ok \
    qa=0 pytest=0 category=0 engine=0 bench=0 cost=0 pay=0 || true
exit 0
