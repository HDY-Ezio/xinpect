#!/bin/bash
# 煋鉴全量自动化测试 v2
# 改完代码 → 跑一遍 → 全过了才算完
# 用法: bash run_all_tests.sh
# 退出码: 0=全部通过 1=有失败

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
PASS=0; FAIL=0; TOTAL=0; START=$(date +%s)
lp() { ((PASS++)); ((TOTAL++)); echo -e "  ${GREEN}✅ $1${NC}"; }
lf() { ((FAIL++)); ((TOTAL++)); echo -e "  ${RED}❌ $1${NC}${2:+: $2}${NC}"; }
sec() { echo -e "\n${CYAN}━━━ $1 ━━━${NC}"; }

echo -e "${CYAN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║  🔬 煋鉴全量自动化测试                        ║${NC}"
echo -e "${CYAN}║  $(date '+%Y-%m-%d %H:%M:%S')                        ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════╝${NC}"

# ===== 1. 服务健康 =====
sec "1/5 服务健康检查"
for svc in "蓝版扫描器:8622" "绿版扫描器:8620" "煋鉴官网:8621"; do
    name="${svc%%:*}"; port="${svc##*:}"
    CODE=$(curl -sf -o /dev/null -w "%{http_code}" "http://localhost:${port}/" -m 5 2>/dev/null || echo "000")
    if [ "$CODE" != "000" ]; then lp "$name (:${port}) HTTP $CODE"; else lf "$name (:${port})" "无响应"; fi
done
# Nginx外部
if curl -sf https://xinpect.xingwangzhineng.com/ -m 10 -o /dev/null 2>/dev/null; then
    lp "Nginx反代 (外部可达)"
else
    lf "Nginx反代" "外部不可达"
fi

# ===== 2. 后端扫描API =====
sec "2/5 后端扫描引擎"

# 语言→文件名映射
declare -A LANG_MAP=(
    [python]="test.py" [javascript]="test.js" [typescript]="test.ts" [java]="Test.java"
    [go]="test.go" [rust]="test.rs" [c]="test.c" [cpp]="test.cpp" [ruby]="test.rb"
    [php]="test.php" [swift]="test.swift" [kotlin]="Test.kt" [scala]="test.scala"
    [lua]="test.lua" [shell]="test.sh" [sql]="test.sql" [html]="test.html"
    [yaml]="test.yaml" [dockerfile]="Dockerfile" [ansible]="playbook.yml"
)
SCAN_OK=0; SCAN_FAIL=0; FAIL_LANGS=""
for lang in "${!LANG_MAP[@]}"; do
    fname="${LANG_MAP[$lang]}"
    RESULT=$(curl -sf -X POST http://localhost:8620/scan -H "Content-Type: application/json" \
        -d "{\"code_files\":{\"$fname\":\"// test code\"}}" -m 20 2>/dev/null)
    if echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if d.get('status')=='ok' else 1)" 2>/dev/null; then
        ((SCAN_OK++))
    else
        ((SCAN_FAIL++)); FAIL_LANGS="$FAIL_LANGS $lang"
    fi
done
if [ $SCAN_FAIL -eq 0 ]; then
    lp "20种语言全量扫描 ($SCAN_OK/20)"
else
    lf "语言扫描" "$SCAN_FAIL种失败:$FAIL_LANGS"
fi

# 绿版brains
BRAINS=$(curl -sf http://localhost:8620/health -m 5 | python3 -c "import sys,json; print(json.load(sys.stdin).get('brains_loaded','?'))" 2>/dev/null)
if [ "$BRAINS" = "9" ]; then lp "绿版9大引擎全部加载"
else lf "引擎加载" "brains=$BRAINS (期望9)"; fi

# 网站API
for ep_info in "队列状态:/api/queue/overview:8621" "健康检查:/health:8621"; do
    name="${ep_info%%:*}"; rest="${ep_info#*:}"; ep="${rest%%:*}"; port="${rest##*:}"
    CODE=$(curl -sf -o /dev/null -w "%{http_code}" "http://localhost:${port}${ep}" -m 5 2>/dev/null)
    if [ "$CODE" = "200" ]; then lp "$name ($ep)"; else lf "$name ($ep)" "HTTP $CODE"; fi
done

# ===== 3. 官网页面可达 =====
sec "3/5 官网页面可达性"
for page in "/" "/login" "/register" "/pricing" "/changelog" "/help" "/terms" "/component-check" "/health"; do
    CODE=$(curl -sf -o /dev/null -w "%{http_code}" "http://localhost:8621${page}" -m 5 2>/dev/null)
    if [ "$CODE" = "200" ] || [ "$CODE" = "302" ]; then lp "页面 $page"; else lf "页面 $page" "HTTP $CODE"; fi
done

# ===== 4. Playwright动态交互 =====
sec "4/5 动态前端交互（Playwright）"
if [ -f /opt/xinpect-website/scripts/dynamic_frontend_test.py ]; then
    DW_OUT=$(python3 /opt/xinpect-website/scripts/dynamic_frontend_test.py 2>&1)
    DW_EXIT=$?
    # 从JSON报告读取准确数据
    if [ -f /tmp/xinpect_full_test_report.json ]; then
        DW_P=$(python3 -c "import json; d=json.load(open('/tmp/xinpect_full_test_report.json')); print(d.get('summary',{}).get('passed',0))" 2>/dev/null)
        DW_T=$(python3 -c "import json; d=json.load(open('/tmp/xinpect_full_test_report.json')); print(d.get('summary',{}).get('total',0))" 2>/dev/null)
        DW_E=$(python3 -c "import json; d=json.load(open('/tmp/xinpect_full_test_report.json')); print(len(d.get('console_errors',[])))" 2>/dev/null)
    fi
    if [ $DW_EXIT -eq 0 ]; then
        lp "Playwright: ${DW_P:-?}/${DW_T:-?} 通过, Console错误: ${DW_E:-0}"
    else
        lf "Playwright" "${DW_P:-?}/${DW_T:-?} 通过"
        echo "$DW_OUT" | grep "❌" | head -5 | while read line; do echo "    $line"; done
    fi
else
    lf "Playwright" "脚本不存在"
fi

# ===== 5. 蓝绿一致性 =====
sec "5/5 蓝绿版一致性"
BLUE_MD5=$(md5sum /opt/xinpect-scanner-blue/rules/brain_rules_bundle.json 2>/dev/null | awk '{print $1}')
GREEN_MD5=$(md5sum /opt/xinpect-scanner-green/rules/brain_rules_bundle.json 2>/dev/null | awk '{print $1}')
if [ -n "$BLUE_MD5" ] && [ "$BLUE_MD5" = "$GREEN_MD5" ]; then lp "规则包MD5一致"; else lf "规则包MD5" "蓝≠绿"; fi

BLUE_B8=$(md5sum /opt/xinpect-scanner-blue/engine/e2_security/_b8_impl.py 2>/dev/null | awk '{print $1}')
GREEN_B8=$(md5sum /opt/xinpect-scanner-green/engine/e2_security/_b8_impl.py 2>/dev/null | awk '{print $1}')
if [ -n "$BLUE_B8" ] && [ "$BLUE_B8" = "$GREEN_B8" ]; then lp "B8引擎MD5一致"; else lf "B8引擎MD5" "蓝≠绿"; fi

# 规则条数
RULE_COUNT=$(python3 -c "import json; d=json.load(open('/opt/xinpect-scanner-green/rules/brain_rules_bundle.json')); print(sum(len(v) for v in d.values() if isinstance(v,list)))" 2>/dev/null || echo "?")
if [ "$RULE_COUNT" != "?" ] && [ "$RULE_COUNT" -gt 10000 ] 2>/dev/null; then
    lp "规则总数: $RULE_COUNT 条"
else
    lf "规则总数" "$RULE_COUNT (期望>10000)"
fi

# ===== 汇总 =====
ELAPSED=$(( $(date +%s) - START ))
echo ""
if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  ✅ 全部通过！ $PASS/$TOTAL 项 · ${ELAPSED}秒              ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
else
    echo -e "${RED}╔══════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║  ❌ $FAIL 项失败！ $PASS/$TOTAL 通过 · ${ELAPSED}秒           ║${NC}"
    echo -e "${RED}╚══════════════════════════════════════════════╝${NC}"
fi

# 保存报告
mkdir -p /opt/xinpect-website/scripts/reports
cat > /opt/xinpect-website/scripts/reports/test_summary_$(date +%Y%m%d_%H%M%S).json << EOF
{"timestamp":"$(date -Iseconds)","passed":$PASS,"failed":$FAIL,"total":$TOTAL,"elapsed":$ELAPSED,"ok":$([ $FAIL -eq 0 ] && echo true || echo false)}
EOF

exit $([ $FAIL -eq 0 ] && echo 0 || echo 1)
