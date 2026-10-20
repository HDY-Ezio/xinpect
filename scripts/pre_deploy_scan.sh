#!/bin/bash
# 煋鉴预部署自扫质量门禁 v2
set -e

SCANNER_URL='http://localhost:8620'
WEBSITE_DIR='/opt/xinpect-website'
REPORT_DIR="$WEBSITE_DIR/reports/pre_deploy"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
REPORT_FILE="$REPORT_DIR/self_scan_${TIMESTAMP}.json"

mkdir -p "$REPORT_DIR"

echo "=== 煋鉴预部署自扫 ==="
echo "时间: $TIMESTAMP"

# === 阶段0: 前端综合验证（JS语法 + Jinja2完整性） ===
echo ""
echo "=== 阶段0: 前端综合验证 ==="
python3 /opt/xinpect-website/scripts/validate_frontend.py --check js --quiet
if [ $? -ne 0 ]; then
    echo "❌ 前端JS语法验证失败，终止部署！"
    exit 1
fi
python3 /opt/xinpect-website/scripts/validate_frontend.py --check jinja --quiet
if [ $? -ne 0 ]; then
    echo "❌ Jinja2模板完整性验证失败，终止部署！"
    exit 1
fi
echo "✅ 前端验证通过"

# === 阶段1: 前端路由健康检查 ===
echo ""
echo "=== 阶段1: 前端路由健康检查 ==="
ROUTE_FAIL=0
for route in "/" "/pricing" "/login" "/help" "/health"; do
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "http://127.0.0.1:8621${route}")
    if [ "$STATUS" != "200" ]; then
        echo "❌ 路由 ${route} 返回 HTTP ${STATUS}"
        ROUTE_FAIL=1
    fi
done
if [ $ROUTE_FAIL -eq 1 ]; then
    echo "❌ 前端路由检查失败，终止部署！"
    exit 1
fi
echo "✅ 前端路由检查通过"

# === 阶段2: 后端代码自扫 ===
# 收集活跃代码文件（排除_archive、tests、__pycache__）
python3 << 'INNERPY'
import json, os

website_dir = '/opt/xinpect-website'
exclude_dirs = ['_archive', '__pycache__', 'tests', 'reports', 'scripts', 'node_modules']
code_files = {}

for root, dirs, files in os.walk(website_dir):
    dirs[:] = [d for d in dirs if d not in exclude_dirs and not d.startswith('_archive')]
    for fname in files:
        if fname.endswith('.py') and not fname.startswith('test_'):
            fpath = os.path.join(root, fname)
            rel_path = os.path.relpath(fpath, website_dir)
            try:
                with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                    code_files[rel_path] = f.read()
            except:
                pass

print(f'收集到 {len(code_files)} 个文件')

payload = {
    'code_files': code_files,
    'brains': ['1','2','3','4','5','6','7','8','9','10'],
    'config': {'scan_mode': 'full', 'is_vip': True}
}

with open('/tmp/scan_payload.json', 'w') as f:
    json.dump(payload, f)
print(f'请求体: {os.path.getsize("/tmp/scan_payload.json")} bytes')
INNERPY

# 发送扫描请求
echo "发送扫描请求..."
curl -s -X POST "$SCANNER_URL/scan" \
    -H 'Content-Type: application/json' \
    -d @/tmp/scan_payload.json \
    --max-time 300 > "$REPORT_FILE"

rm -f /tmp/scan_payload.json

# 解析结果
python3 - "$REPORT_FILE" << 'PARSEPY'
import json, sys
from collections import Counter

report_file = sys.argv[1]
data = json.load(open(report_file))
issues = data.get("issues", [])
total = data.get("total", len(issues))
severity = data.get("severity", {})

print(f"\n=== 扫描结果 ===")
print(f"总issues: {total}")
print(f"严重度: {json.dumps(severity, ensure_ascii=False)}")

cids = Counter(i.get("check_id","") for i in issues)
print(f"\nTOP10问题类型:")
for cid, cnt in cids.most_common(10):
    names = [i.get("name","") for i in issues if i.get("check_id")==cid]
    name = names[0] if names else "?"
    print(f"  {cid} ({name}): {cnt}")

critical_high = [i for i in issues if i.get("severity") in ("critical","high")]
if critical_high:
    print(f"\n❌ FAILED: {len(critical_high)} 个critical/high")
    for i in critical_high[:10]:
        print(f"  [{i.get('severity')}] {i.get('file')}:{i.get('line')} [{i.get('check_id')}] {i.get('message','')[:80]}")
    sys.exit(1)
else:
    print(f"\n✅ PASSED: 0个critical/high")
    sys.exit(0)
PARSEPY
