#!/usr/bin/env bash
# =============================================================================
# 煋鉴 测试覆盖率基线检查（P1-6，初期"只警告不阻断"）
# 当前引擎代码覆盖率基线极低(0.26%, 93632行仅覆盖246行,集中在Rust规则校验)。
# 策略：不追求一步到80%，只要求覆盖率"不低于基线、只升不降"；
#       每次发布跑一次，结果留痕，趋势下行时提示补单测，成熟后再升级为阻断。
# 用法: coverage_baseline.sh <scanner_dir>
# 退出码：恒为0（只观测不拦截）；结果写 /opt/xinpect-website/ops/coverage_trend.log
# =============================================================================
set -u
DIR="${1:-/opt/xinpect-scanner-blue}"
V=/home/ubuntu/xinpect_ops_venv/bin
CF=/tmp/cov_gate_$$
TREND=/opt/xinpect-website/ops/coverage_trend.log
BASELINE_PCT=0.26          # 2026-10-22 建立的基线（行覆盖率%），只升不降

cd "$DIR/tests" || { echo "tests 目录不存在: $DIR/tests"; exit 0; }
sudo -H -u ubuntu env PYTHONPATH="$DIR" COVERAGE_FILE="$CF" \
  "$V/coverage" run --source="$DIR/engine" -m pytest -q >/dev/null 2>&1
sudo -H -u ubuntu "$V/coverage" json --data-file="$CF" -o "${CF}.json" >/dev/null 2>&1
PCT=$(sudo -H -u ubuntu /usr/bin/python3 -c "import json;print(round(json.load(open('${CF}.json'))['totals']['percent_covered'],2))" 2>/dev/null)
sudo -H -u ubuntu rm -f "$CF" "${CF}.json"

TS=$(date '+%Y-%m-%d %H:%M:%S')
[ -z "$PCT" ] && PCT="0"
# 用 python 做浮点比较
FLAG=$(python3 -c "print('OK' if float('$PCT')>=float('$BASELINE_PCT') else 'DOWN')")
LINE="[$TS] side=$DIR engine行覆盖率=${PCT}% 基线=${BASELINE_PCT}% -> $FLAG"
echo "$LINE"
echo "$LINE" | sudo tee -a "$TREND" >/dev/null

if [ "$FLAG" = "DOWN" ]; then
  echo "  ⚠ 覆盖率低于基线（只警告不阻断）。请为本次变更补引擎单元测试；连续下行需排期补债。"
fi
echo "  说明：基线阶段只要求不下降；新增/修改的引擎核心逻辑建议同步加单测，成熟后升级为门禁硬卡。"
exit 0
