#!/usr/bin/env python3
"""
煋鉴前端综合验证脚本
覆盖3大前端检查维度，堵住测试盲区：
  1. JS语法验证：Jinja2变量替换 + node --check
  2. 硬编码样式检测：inline style中的硬编码颜色
  3. Jinja2模板完整性：确保标签配对

用法:
  python3 validate_frontend.py               # 运行所有检查
  python3 validate_frontend.py --check js     # 只检查JS语法
  python3 validate_frontend.py --check style  # 只检查硬编码样式
  python3 validate_frontend.py --check jinja  # 只检查Jinja2完整性
  python3 validate_frontend.py --quiet        # 仅输出失败/警告项
  python3 validate_frontend.py --json         # JSON输出
"""

import re, subprocess, os, sys, glob, json, argparse
from datetime import datetime

TEMPLATE_DIR = "/opt/xinpect-website/templates"
EXCLUDE_PATTERNS = ["backup", ".bak", "_archive", "node_modules"]

# 硬编码颜色匹配模式（用于inline style检测）
HARDCODED_COLOR_RE = re.compile(
    r'(?:color|background(?:-color)?|border(?:-color)?|outline)\s*:\s*(#[0-9a-fA-F]{3,8})\b'
)

# 允许硬编码的例外颜色
ALLOWED_COLORS = {"#fff", "#ffffff", "#000", "#000000", "#transparent"}


# ============ 1. JS语法验证 ============
def replace_jinja2(js):
    """替换Jinja2模板变量为合法JS值"""
    js = re.sub(r'\{%\s*if\s+\w+\s*%\}(.*?)\{%\s*else\s*%\}(.*?)\{%\s*endif\s*%\}', r'\1', js, flags=re.DOTALL)
    js = re.sub(r'\{%\s*if\s+not\s+\w+\s*%\}(.*?)\{%\s*else\s*%\}(.*?)\{%\s*endif\s*%\}', r'\2', js, flags=re.DOTALL)
    js = re.sub(r'\{%\s*for\s+.*?\s*%\}', '', js)
    js = re.sub(r'\{%\s*endfor\s*%\}', '', js)
    js = re.sub(r"{{\s*'true'\s+if\s+\w+\s+else\s+'false'\s*}}", 'true', js)
    js = re.sub(r'{{\s*(\w+)\s+if\s+\w+\s+else\s+(\w+)\s*}}', r'\1', js)
    js = re.sub(r'{{\s*url_for\([^)]*\)\s*}}', "'/url'", js)
    js = re.sub(r'{{[^}]*}}', '0', js)
    js = re.sub(r'\{%[^%]*%\}', '', js)
    return js


def check_js_syntax(fpath):
    """验证单个HTML文件的JS语法"""
    fname = fpath.replace(TEMPLATE_DIR + "/", "")
    with open(fpath, encoding="utf-8", errors="ignore") as f:
        content = f.read()

    scripts = re.findall(r'<script[^>]*>(.*?)</script>', content, re.DOTALL)
    if not scripts:
        return {"file": fname, "check": "js_syntax", "status": "ok", "has_js": False}

    js = "\n".join(scripts)
    js = replace_jinja2(js)

    tmpf = "/tmp/js_check_%d.js" % os.getpid()
    with open(tmpf, "w", encoding="utf-8") as out:
        out.write(js)

    r = subprocess.run(["node", "--check", tmpf], capture_output=True, text=True)
    if os.path.exists(tmpf):
        os.unlink(tmpf)

    if r.returncode != 0:
        err = r.stderr.strip().split("\n")[0] if r.stderr else "unknown"
        return {"file": fname, "check": "js_syntax", "status": "fail", "has_js": True, "error": err}
    return {"file": fname, "check": "js_syntax", "status": "ok", "has_js": True}


# ============ 2. 硬编码样式检测 ============
def check_hardcoded_styles(fpath):
    """检测inline style中的硬编码颜色值"""
    fname = fpath.replace(TEMPLATE_DIR + "/", "")
    with open(fpath, encoding="utf-8", errors="ignore") as f:
        content = f.read()

    findings = []
    lines = content.split("\n")
    for lineno, line in enumerate(lines, 1):
        if "style=" not in line:
            continue

        style_match = re.search(r'style\s*=\s*["\']([^"\']*)["\']', line)
        if not style_match:
            continue
        style_val = style_match.group(1)

        for m in HARDCODED_COLOR_RE.finditer(style_val):
            color = m.group(1)
            if color.lower() in ALLOWED_COLORS:
                continue
            # 检查是否在CSS变量fallback中 var(--x, #fff) - 允许
            pre = style_val[max(0, m.start()-20):m.start()]
            if "var(" in pre:
                continue
            findings.append({
                "line": lineno,
                "color": color,
                "context": line.strip()[:120]
            })

    if findings:
        return {"file": fname, "check": "hardcoded_styles", "status": "warn", "count": len(findings), "findings": findings[:5]}
    return {"file": fname, "check": "hardcoded_styles", "status": "ok"}


# ============ 3. Jinja2模板完整性 ============
def check_jinja2(fpath):
    """检查Jinja2标签的配对完整性"""
    fname = fpath.replace(TEMPLATE_DIR + "/", "")
    with open(fpath, encoding="utf-8", errors="ignore") as f:
        content = f.read()

    errors = []
    stack = []
    open_tags = {"if", "for", "block", "macro", "call", "filter"}
    close_tags = {"endif": "if", "endfor": "for", "endblock": "block",
                  "endmacro": "macro", "endcall": "call", "endfilter": "filter"}

    tag_pattern = re.compile(r'\{%-?\s*(if|endif|for|endfor|block|endblock|macro|endmacro|call|endcall|filter|endfilter|else|elif)\b')

    for match in tag_pattern.finditer(content):
        tag = match.group(1)
        pos = match.start()
        line_no = content[:pos].count("\n") + 1

        if tag in open_tags:
            stack.append((tag, line_no))
        elif tag in close_tags:
            expected_opener = close_tags[tag]
            if stack and stack[-1][0] == expected_opener:
                stack.pop()
            elif stack:
                errors.append(f"L{line_no}: {{% {tag} %}} 期望 {{% end{stack[-1][0]} %}}(开标签L{stack[-1][1]})")
                break
            else:
                errors.append(f"L{line_no}: {{% {tag} %}} 无对应开标签")
                break

    if stack and not errors:
        tag, line_no = stack[-1]
        errors.append(f"L{line_no}: {{% {tag} %}} 未闭合")

    if errors:
        return {"file": fname, "check": "jinja2", "status": "fail", "errors": errors[:3]}
    return {"file": fname, "check": "jinja2", "status": "ok"}


# ============ 主逻辑 ============
def get_templates(path_filter=None):
    if path_filter:
        return [path_filter]
    templates = glob.glob(TEMPLATE_DIR + "/*.html") + glob.glob(TEMPLATE_DIR + "/**/*.html", recursive=True)
    templates = [t for t in templates if not any(p in t for p in EXCLUDE_PATTERNS)]
    return sorted(set(templates))


def check_style_baseline(results):
    """对比硬编码样式数量与基线"""
    baseline_file = "/opt/xinpect-website/scripts/style_baseline.json"
    try:
        with open(baseline_file) as f:
            baseline = json.load(f)
    except Exception:
        return
    
    current_total = sum(r.get("count", 0) for r in results if r["check"] == "hardcoded_styles" and r["status"] == "warn")
    baseline_total = sum(baseline["files"].values())
    
    if current_total > baseline_total:
        print(f"\n[REGRESSION] 硬编码样式从基线{baseline_total}个增加到{current_total}个（+{current_total - baseline_total}）")
        print(f"  基线日期: {baseline.get('baseline_date', 'unknown')}")
        print(f"  建议: 新增的硬编码颜色应替换为CSS变量")
    elif current_total < baseline_total:
        print(f"\n[IMPROVED] 硬编码样式从基线{baseline_total}个减少到{current_total}个（-{baseline_total - current_total}）")
    else:
        print(f"\n[OK] 硬编码样式数量持平: {current_total}个")


def run_checks(templates, checks=None, quiet=False, json_output=False):
    all_checks = checks or ["js", "style", "jinja"]
    results = []

    for fpath in templates:
        if "js" in all_checks:
            r = check_js_syntax(fpath)
            if r.get("has_js", False):
                results.append(r)
        if "style" in all_checks:
            r = check_hardcoded_styles(fpath)
            if r["status"] != "ok" or not quiet:
                results.append(r)
        if "jinja" in all_checks:
            r = check_jinja2(fpath)
            results.append(r)

    js_fails = [r for r in results if r["check"] == "js_syntax" and r["status"] == "fail"]
    style_warns = [r for r in results if r["check"] == "hardcoded_styles" and r["status"] == "warn"]
    jinja_fails = [r for r in results if r["check"] == "jinja2" and r["status"] == "fail"]

    if json_output:
        print(json.dumps({
            "timestamp": datetime.now().isoformat(),
            "total_files": len(templates),
            "js_failures": len(js_fails),
            "style_warnings": len(style_warns),
            "jinja_failures": len(jinja_fails),
            "results": results
        }, indent=2, ensure_ascii=False))
    else:
        for r in results:
            if r["status"] == "ok":
                if not quiet:
                    print(f"[OK] [{r['check']}] {r['file']}")
            elif r["status"] == "fail":
                detail = r.get("error") or (r.get("errors") or [""])[0]
                print(f"[FAIL] [{r['check']}] {r['file']}: {str(detail)[:120]}")
            elif r["status"] == "warn":
                count = r.get("count", len(r.get("findings", [])))
                print(f"[WARN] [{r['check']}] {r['file']}: {count}个硬编码颜色")

        print(f"\n=== 汇总 ===")
        print(f"JS语法: {'FAIL' if js_fails else 'PASS'} ({len(js_fails)}个错误)")
        print(f"硬编码样式: {'WARN' if style_warns else 'PASS'} ({len(style_warns)}个警告)")
        print(f"Jinja2完整性: {'FAIL' if jinja_fails else 'PASS'} ({len(jinja_fails)}个错误)")

    # 硬编码样式基线对比
    if not checks or "style" in (checks or []):
        check_style_baseline(results)
    
    if js_fails or jinja_fails:
        sys.exit(1)
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="煋鉴前端综合验证")
    parser.add_argument("--check", choices=["js", "style", "jinja"], help="只运行特定检查")
    parser.add_argument("--path", help="指定单个文件验证")
    parser.add_argument("--quiet", action="store_true", help="仅输出失败/警告")
    parser.add_argument("--json", action="store_true", help="JSON格式输出")
    args = parser.parse_args()

    checks = [args.check] if args.check else None
    templates = get_templates(args.path)

    print(f"煋鉴前端综合验证 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"模板目录: {TEMPLATE_DIR} ({len(templates)}个文件)")
    print(f"检查项: {','.join(checks) if checks else 'js+style+jinja'}")
    print()

    run_checks(templates, checks, args.quiet, args.json)


if __name__ == "__main__":
    main()
