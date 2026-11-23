#!/usr/bin/env bash
# =============================================================================
# 煋鉴 发布质量门禁（Release Quality Gate） — 蓝版→绿版合入前必须 100% 通过
# 对标大厂 CI Quality Gate：任何一项 FAIL 立即中止，禁止合入生产。
# 用法: ./release_gate.sh [blue|green] [flaky轮数]   默认 blue / 3 轮
# 退出码: 0=全部通过可合入;  1=门禁拦截(禁止合入)
# 自己用自己：关4用煋鉴自身扫描煋鉴代码,接口层错误即阻断。
# =============================================================================
set -u
SIDE="${1:-blue}"
FLAKY_ROUNDS="${2:-3}"
case "$SIDE" in
  blue)  DIR=/opt/xinpect-scanner-blue;  PORT=8622 ;;
  green) DIR=/opt/xinpect-scanner-green; PORT=8620 ;;
  *) echo "用法: $0 [blue|green] [轮数]"; exit 1 ;;
esac
# 凭据不入库：优先环境变量，其次仓库外的 /etc/xinpect/monitor.key
if [ -n "${XINPECT_API_KEY:-}" ]; then
  API_KEY="$XINPECT_API_KEY"
elif [ -r /etc/xinpect/monitor.key ]; then
  API_KEY="$(tr -d '\r\n' < /etc/xinpect/monitor.key)"
else
  echo "缺少扫描器 API 凭据：设置 XINPECT_API_KEY，或写入 /etc/xinpect/monitor.key（权限 640 root:ubuntu）" >&2
  exit 1
fi
ADV="/opt/xinpect-website/monitoring/adversarial/adversarial_selfcheck.py"
FLAKY="/opt/xinpect-website/ops/flaky_guard.py"
PASS=0; FAIL=0
ok(){   printf "  \033[0;32m✅ PASS\033[0m %s\n" "$1"; PASS=$((PASS+1)); }
bad(){  printf "  \033[0;31m❌ FAIL\033[0m %s\n" "$1"; FAIL=$((FAIL+1)); }

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  煋鉴发布质量门禁 — 目标: $SIDE ($DIR:$PORT)"
echo "╚══════════════════════════════════════════════════════════╝"

# ── 关1：单元测试全绿（在 tests/ 跑，pytest.ini 排除归档）──────────────────────
echo "【关1】单元测试必须全绿"
if sudo -H -u ubuntu bash -c "cd '$DIR/tests' && PYTHONPATH='$DIR' /usr/bin/python3 -m pytest -q" >/tmp/gate_pytest.log 2>&1; then
  N=$(grep -oE '[0-9]+ passed' /tmp/gate_pytest.log | tail -1)
  ok "pytest 全绿（$N）"
else
  bad "pytest 存在失败/错误，见 /tmp/gate_pytest.log"; tail -5 /tmp/gate_pytest.log | sed 's/^/      /'
fi

# ── 关2：Flaky 守门（连跑 N 轮，跨轮不一致即拦截）────────────────────────────
echo "【关2】Flaky 守门（连跑 $FLAKY_ROUNDS 轮，必须稳定）"
if /usr/bin/python3 "$FLAKY" "$DIR" "$FLAKY_ROUNDS" >/tmp/gate_flaky.log 2>&1; then
  ok "无 flaky 用例（$FLAKY_ROUNDS 轮稳定）"
else
  bad "存在 flaky/稳定失败用例"; grep -E '⚠|✗|FLAKY|失败' /tmp/gate_flaky.log | sed 's/^/      /'
fi

# ── 关3：7 引擎可加载、scan 齐备、零 import error ─────────────────────────────
echo "【关3】7 引擎模块可加载、scan 齐备、零 import 错误"
ENG_OUT=$(sudo -H -u xinpect-scan /usr/bin/python3 - "$DIR" <<'PYEOF'
import importlib, sys
sys.path.insert(1, sys.argv[1])
mods=[("1","engine.e1_syntax"),("2","engine.e2_security"),("3","engine.e3_performance"),
      ("4","engine.e4_quality"),("5","engine.e5_architecture"),("6","engine.e6_component"),
      ("7","engine.e7_ai_health")]
bad=[]
for b,m in mods:
    try:
        mod=importlib.import_module(m)
        if not hasattr(mod,"scan"): bad.append(f"{m}:no-scan")
    except Exception as e:
        bad.append(f"{m}:{type(e).__name__}:{str(e)[:40]}")
print("OK" if not bad else "BAD "+";".join(bad))
PYEOF
)
if [ "$ENG_OUT" = "OK" ]; then ok "7 引擎全部可加载且 scan 齐备"; else bad "引擎问题: ${ENG_OUT#BAD }"; fi

# ── 关4：自己用自己——煋鉴扫描自身核心源码，接口层零错误 ────────────────────────
echo "【关4】煋鉴自扫自身核心源码：接口零错误"
SELF_OUT=$(/usr/bin/python3 - "$DIR" "$API_KEY" "$PORT" <<'PYEOF'
import sys,json,urllib.request,uuid,os
dir_path,key,port=sys.argv[1],sys.argv[2],sys.argv[3]
pyfiles=[]
for root,_,fs in os.walk(os.path.join(dir_path,"engine")):
    if "__pycache__" in root: continue
    for f in fs:
        if f.endswith(".py") and not f.startswith("test"):
            pyfiles.append(os.path.join(root,f))
pyfiles=pyfiles[:12]
files=[]
for p in pyfiles:
    try: files.append({"filename":"selfcheck_"+uuid.uuid4().hex[:6]+".py",
                       "content":open(p,encoding="utf-8",errors="ignore").read()})
    except Exception: pass
if not files: print("NOFILES"); sys.exit(0)
req=urllib.request.Request(f"http://127.0.0.1:{port}/scan/batch",
    data=json.dumps({"files":files,"scan_mode":"quick"}).encode(),
    headers={"Content-Type":"application/json","X-API-Key":key})
try:
    r=json.loads(urllib.request.urlopen(req,timeout=240).read())
except Exception as e:
    print(f"REQFAIL {e}"); sys.exit(0)
errs=sum(1 for fr in r.get("file_results",[]) if fr.get("status")=="error" or fr.get("error"))
print("SELF_OK" if errs==0 else f"SELF_BAD {errs}个扫描请求失败")
PYEOF
)
if [ "$SELF_OUT" = "SELF_OK" ]; then ok "自扫核心源码接口零错误"; else bad "$SELF_OUT"; fi

# ── 关5：生产对抗性自检——黄金样本漏报0、误报0 ───────────────────────────────
echo "【关5】对抗性自检：7 恶意全检出 + 3 干净零误报"
if /usr/bin/python3 "$ADV" >/tmp/gate_adv.log 2>&1; then
  ok "黄金样本漏报0/误报0"
else
  bad "对抗性自检未过（有漏报或误报）"; tail -3 /tmp/gate_adv.log | sed 's/^/      /'
fi

# ── 关6：health 200 + 规则包完整（11376）──────────────────────────────────────
echo "【关6】服务健康 + 规则包完整"
CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 "http://127.0.0.1:$PORT/health")
[ "$CODE" = "200" ] && ok "$SIDE :$PORT /health=200" || bad "$SIDE :$PORT /health=$CODE"
RULES=$(/usr/bin/python3 - "$DIR" <<'PYEOF'
import json,sys,os
p=os.path.join(sys.argv[1],"rules","brain_rules_bundle.json")
try:
    b=json.load(open(p)); print(sum(len(v) for v in b.values() if isinstance(v,list)))
except Exception: print("0")
PYEOF
)
[ "$RULES" = "11376" ] && ok "规则包完整 11376 条" || bad "规则数异常: $RULES (应为11376)"

# ── 关7：覆盖率基线（观测项，只警告不阻断，不计入 FAIL）────────────────────────
echo "【关7】引擎测试覆盖率基线（观测项·只警告不阻断）"
COVS=/opt/xinpect-website/ops/coverage_baseline.sh
if [ -x "$COVS" ]; then
  bash "$COVS" "$DIR" | sed "s/^/      /"
else
  echo "      （coverage_baseline.sh 缺失，跳过）"
fi

# ── 汇总 ─────────────────────────────────────────────────────────────────────
echo "──────────────────────────────────────────────────────────"
if [ "$FAIL" -eq 0 ]; then
  printf "\033[1;32m✅ 门禁全部通过（%d/%d）：可以合入生产。\033[0m\n" "$PASS" "$((PASS+FAIL))"
  exit 0
else
  printf "\033[1;31m❌ 门禁拦截：%d 项失败 / %d 项通过。禁止合入，先修复。\033[0m\n" "$FAIL" "$PASS"
  exit 1
fi
