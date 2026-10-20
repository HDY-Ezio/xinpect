#!/usr/bin/env python3
"""
煋鉴前端JS语法验证脚本
在部署前/部署后验证所有HTML模板中的JavaScript语法正确性
防止Jinja2模板中的JS语法错误导致页面功能失效

用法:
  python3 validate_js_syntax.py              # 验证所有模板
  python3 validate_js_syntax.py --path xxx   # 验证指定文件
  python3 validate_js_syntax.py --quiet      # 静默模式(仅输出失败)
"""

import re, subprocess, os, sys, glob, json, argparse
from datetime import datetime

TEMPLATE_DIR = "/opt/xinpect-website/templates"
EXCLUDE_PATTERNS = ["backup", ".bak"]

def replace_jinja2(js):
    """精确替换Jinja2模板变量为合法JS值"""
    # {% if X %}A{% else %}B{% endif %} -> A
    js = re.sub(r"\{%\s*if\s+\w+\s*%\}(.*?)\{%\s*else\s*%\}(.*?)\{%\s*endif\s*%\}", r"\1", js, flags=re.DOTALL)
    js = re.sub(r"\{%\s*if\s+not\s+\w+\s*%\}(.*?)\{%\s*else\s*%\}(.*?)\{%\s*endif\s*%\}", r"\2", js, flags=re.DOTALL)
    js = re.sub(r"\{%\s*for\s+.*?\s*%\}", "", js)
    js = re.sub(r"\{%\s*endfor\s*%\}", "", js)
    js = re.sub(r"{{\s*.true.\s+if\s+\w+\s+else\s+.false.\s*}}", "true", js)
    js = re.sub(r"{{\s*(\w+)\s+if\s+\w+\s+else\s+(\w+)\s*}}", r"\1", js)
    js = re.sub(r"{{\s*url_for\([^)]*\)\s*}}", "/url", js)
    js = re.sub(r"{{[^}]*}}", "0", js)
    js = re.sub(r"\{%[^%]*%\}", "", js)
    return js

def validate_file(fpath):
    """验证单个HTML文件的JS语法"""
    fname = fpath.replace(TEMPLATE_DIR + "/", "")
    with open(fpath) as f:
        content = f.read()
    
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", content, re.DOTALL)
    if not scripts:
        return {"file": fname, "status": "ok", "has_js": False}
    
    js = "\n".join(scripts)
    js = replace_jinja2(js)
    
    tmpf = "/tmp/js_check_%d.js" % os.getpid()
    with open(tmpf, "w") as out:
        out.write(js)
    
    r = subprocess.run(["node", "--check", tmpf], capture_output=True, text=True)
    if os.path.exists(tmpf):
        os.unlink(tmpf)
    
    if r.returncode != 0:
        err = r.stderr.strip().split("\n")[0] if r.stderr else "unknown"
        return {"file": fname, "status": "fail", "has_js": True, "error": err}
    return {"file": fname, "status": "ok", "has_js": True}

def main():
    parser = argparse.ArgumentParser(description="Validate JS syntax in HTML templates")
    parser.add_argument("--path", help="Specific file to validate")
    parser.add_argument("--quiet", action="store_true", help="Only show failures")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()
    
    if args.path:
        templates = [args.path]
    else:
        templates = glob.glob(TEMPLATE_DIR + "/*.html") + glob.glob(TEMPLATE_DIR + "/dashboard/*.html")
        templates = [t for t in templates if not any(p in t for p in EXCLUDE_PATTERNS)]
    
    results = []
    for fpath in sorted(templates):
        result = validate_file(fpath)
        results.append(result)
        if not args.quiet and not args.json:
            status = "OK" if result["status"] == "ok" else "FAIL"
            if result.get("has_js", False):
                detail = "" if result["status"] == "ok" else " - " + result.get("error", "")[:100]
                print("[%s] %s%s" % (status, result["file"], detail))
    
    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    
    failures = [r for r in results if r["status"] == "fail"]
    if failures:
        print("\n%d files FAILED JS syntax validation" % len(failures), file=sys.stderr)
        sys.exit(1)
    else:
        js_count = sum(1 for r in results if r.get("has_js", False))
        if not args.quiet and not args.json:
            print("\nAll %d templates with JS passed syntax validation" % js_count)
        sys.exit(0)

if __name__ == "__main__":
    main()
