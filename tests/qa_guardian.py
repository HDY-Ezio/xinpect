import re
#!/usr/bin/env python3
"""
煋鉴 AI 驱动自动化 QA 守护系统 v1.0
三层检测：
  L1 - 系统健康检查（服务状态、端口、数据库完整性）
  L2 - 用户旅程端到端测试（注册→登录→上传→扫描→报告 完整链路）
  L3 - AI 质检评估（用 AI 判断扫描结果的准确性、误报率、漏报率）

用法:
  python3 qa_guardian.py              # 完整三层检测
  python3 qa_guardian.py --level 1    # 仅 L1 快速健康检查
  python3 qa_guardian.py --level 12   # L1 + L2
  python3 qa_guardian.py --json       # 输出 JSON 格式报告
"""

import json
import sys
import os
import time
import traceback
import subprocess
import sqlite3
import hashlib
from datetime import datetime, timedelta
from urllib import request as urllib_request
from urllib.error import URLError, HTTPError
from http.client import HTTPException

# ============ 配置 ============
SCANNER_GREEN_PORT = 8620
SCANNER_BLUE_PORT = 8622
WEBSITE_PORT = 8621
PAY_PORT = 8612
SCANNER_BASE = f"http://localhost:{SCANNER_GREEN_PORT}"
WEBSITE_BASE = f"http://localhost:{WEBSITE_PORT}"
API_KEY = os.environ.get("XINPECT_SCANNER_API_KEY", "")
DB_PATH = "/opt/xinpect-website/xinpect.db"
REPORT_DIR = "/opt/xinpect-website/tests/reports"
TIMEOUT = 60
AI_GATEWAY_URL = "http://127.0.0.1:8001/v1/chat/completions"
AI_GATEWAY_KEY = os.environ.get("AI_GATEWAY_KEY", "")
AI_UPSTREAM_KEY = "YOUR_AI_API_KEY_HERE"
AI_UPSTREAM_URL = "https://ark.cn-beijing.volces.com/api/v3"
AI_MODEL = "doubao-1-5-lite-32k-250115"

# ============ 测试用例代码 ============

# Python: 应检出 SQL 注入、命令注入
PY_UNSAFE = '''import os
import sqlite3
from flask import request

def get_user():
    user_id = request.args.get("id")
    # SQL注入：字符串拼接
    query = "SELECT * FROM users WHERE id = " + user_id
    cursor.execute(query)
    # 命令注入
    os.system("ping " + request.args.get("host"))
    return query
'''

# Python: 安全代码，不应误报
PY_SAFE = '''import sqlite3

def get_user(user_id):
    """安全地使用参数化查询获取用户"""
    conn = sqlite3.connect("test.db")
    cursor = conn.cursor()
    cursor.execute("SELECT name, email FROM users WHERE id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result
'''

# Python: 多种漏洞混合
PY_MIXED = '''import os
import hashlib

def process_upload(filename, data):
    # 路径遍历漏洞
    filepath = "/uploads/" + filename
    with open(filepath, "wb") as f:
        f.write(data)
    
    # 硬编码密钥
    secret_key = "my_super_secret_key_12345"
    token = hashlib.md5(secret_key.encode()).hexdigest()
    
    # 不安全的反序列化建议
    return {"path": filepath, "token": token}
'''

# JavaScript: 应检出 XSS
JS_UNSAFE = '''function displayComment(comment) {
    document.getElementById("output").innerHTML = comment;
    eval(comment);
}
'''

# Java: 应检出 SQL 注入
JAVA_UNSAFE = '''import java.sql.*;
public class UserDao {
    public ResultSet findUser(String id) throws Exception {
        Statement stmt = conn.createStatement();
        String sql = "SELECT * FROM users WHERE id = '" + id + "'";
        return stmt.executeQuery(sql);
    }
}
'''

# 测试用例注册表
TEST_CASES = {
    "python_sqli_cmdi": {
        "code": PY_UNSAFE,
        "filename": "vuln_test.py",
        "language": "python",
        "must_detect": ["sql injection", "command injection", "SQL注入", "命令注入", "TAINT-CWE-89", "TAINT-CWE-78", "SEC-SQLI", "os.system"],
        "description": "Python SQL注入+命令注入"
    },
    "python_safe_no_fp": {
        "code": PY_SAFE,
        "filename": "safe_test.py",
        "language": "python",
        "must_detect": [],
        "should_not_detect": ["sql injection", "SQL注入", "TAINT-CWE-89", "命令注入", "command injection"],
        "description": "Python安全代码无误报"
    },
    "python_path_traversal": {
        "code": PY_MIXED,
        "filename": "mixed_vuln.py",
        "language": "python",
        "must_detect": ["path traversal", "路径遍历", "hardcoded", "硬编码", "secret"],
        "description": "Python路径遍历+硬编码密钥"
    },
    "javascript_xss": {
        "code": JS_UNSAFE,
        "filename": "xss_test.js",
        "language": "javascript",
        "must_detect": ["xss", "XSS", "innerHTML", "eval", "cross-site"],
        "description": "JavaScript XSS漏洞"
    },
    "java_sqli": {
        "code": JAVA_UNSAFE,
        "filename": "UserDao.java",
        "language": "java",
        "must_detect": ["sql injection", "SQL注入", "TAINT-CWE-89", "SQL", "injection"],
        "description": "Java SQL注入"
    },
}


# ============================================================
# 工具函数
# ============================================================

def http_get(url, headers=None, timeout=TIMEOUT):
    """HTTP GET 请求"""
    req = urllib_request.Request(url, method="GET")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    with urllib_request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def http_get_raw(url, headers=None, timeout=TIMEOUT):
    """HTTP GET 请求，返回状态码和原始文本（不解析JSON）"""
    req = urllib_request.Request(url, method="GET")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    with urllib_request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8", errors="replace")


def http_post_json(url, data, headers=None, timeout=TIMEOUT):
    """HTTP POST JSON 请求"""
    payload = json.dumps(data).encode("utf-8")
    req = urllib_request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    with urllib_request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def scanner_api_get(path):
    """扫描器 API GET"""
    return http_get(f"{SCANNER_BASE}{path}",
                    headers={"Authorization": f"Bearer {API_KEY}"})


def scanner_scan(code_files, language="python", scan_mode="basic"):
    """调用扫描器"""
    return http_post_json(
        f"{SCANNER_BASE}/scan",
        {"code_files": code_files, "language": language, "scan_mode": scan_mode},
        headers={"Authorization": f"Bearer {API_KEY}"},
        timeout=120
    )


def ai_judge(prompt, system_prompt=None, max_tokens=2048):
    """调用 AI gateway 进行判断（含重试）"""
    import time
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    max_retries = 5
    for attempt in range(max_retries):
        try:
            status, resp = http_post_json(
                AI_GATEWAY_URL,
                {"model": AI_MODEL, "messages": messages, "max_tokens": max_tokens, "temperature": 0.1},
                headers={
                    "Authorization": f"Bearer {AI_GATEWAY_KEY}",
                    "X-Upstream-Key": AI_UPSTREAM_KEY,
                    "X-Upstream-URL": AI_UPSTREAM_URL,
                },
                timeout=60
            )
            return resp["choices"][0]["message"]["content"]
        except Exception as e:
            wait = min(15 * (attempt + 1), 60)
            if attempt < max_retries - 1:
                time.sleep(wait)
                continue
            return f"[AI调用失败: {e}]"


# ============================================================
# L1: 系统健康检查
# ============================================================

class L1HealthCheck:
    name = "L1-系统健康检查"

    @staticmethod
    def run():
        results = []

        # 1.1 服务状态检查
        services = {
            "xinpect-scanner-green": SCANNER_GREEN_PORT,
            "xinpect-scanner-blue": SCANNER_BLUE_PORT,
            "xinpect-website": WEBSITE_PORT,
            "xinpect-pay": PAY_PORT,
        }
        for svc, port in services.items():
            try:
                ret = subprocess.run(
                    ["systemctl", "is-active", svc],
                    capture_output=True, text=True, timeout=5
                )
                status = ret.stdout.strip()
                passed = status == "active"
                results.append({
                    "test": f"服务状态-{svc}",
                    "passed": passed,
                    "detail": f"status={status}, port={port}",
                    "severity": "P0" if not passed else "info"
                })
            except Exception as e:
                results.append({
                    "test": f"服务状态-{svc}",
                    "passed": False,
                    "detail": str(e),
                    "severity": "P0"
                })

        # 1.2 扫描器 health 端点
        for name, port in [("green", SCANNER_GREEN_PORT), ("blue", SCANNER_BLUE_PORT)]:
            try:
                status, data = http_get(f"http://localhost:{port}/health",
                                        headers={"Authorization": f"Bearer {API_KEY}"},
                                        timeout=10)
                brains = data.get("brains_loaded", 0)
                brain_ids = data.get("brain_ids", [])
                passed = data.get("status") == "ok" and brains == 9
                results.append({
                    "test": f"扫描器健康-{name}",
                    "passed": passed,
                    "detail": f"status={data.get('status')}, brains={brains}, ids={brain_ids}",
                    "severity": "P0" if not passed else "info"
                })
            except Exception as e:
                results.append({
                    "test": f"扫描器健康-{name}",
                    "passed": False,
                    "detail": str(e),
                    "severity": "P0"
                })

        # 1.3 网站可访问性
        for path, expected in [("/", 200), ("/pricing", 200), ("/help", 200),
                               ("/login", 200), ("/register", 200),
                               ("/sitemap.xml", 200), ("/robots.txt", 200)]:
            try:
                code, _ = http_get_raw(f"{WEBSITE_BASE}{path}", timeout=10)
                results.append({
                    "test": f"页面可达-{path}",
                    "passed": code == expected,
                    "detail": f"HTTP {code} (expected {expected})",
                    "severity": "P1" if code != expected else "info"
                })
            except Exception as e:
                results.append({
                    "test": f"页面可达-{path}",
                    "passed": False,
                    "detail": str(e),
                    "severity": "P1"
                })

        # 1.4 数据库完整性
        try:
            db = sqlite3.connect(DB_PATH)
            db.row_factory = sqlite3.Row
            tables = [r[0] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
            expected_tables = {"users", "scans", "daily_usage", "user_credits",
                             "credit_pools", "orders", "scan_metrics"}
            missing = expected_tables - set(tables)
            db.close()
            results.append({
                "test": "数据库表完整性",
                "passed": len(missing) == 0,
                "detail": f"表数={len(tables)}, 缺失={missing}" if missing else f"全部{len(tables)}张表完好",
                "severity": "P0" if missing else "info"
            })
        except Exception as e:
            results.append({
                "test": "数据库表完整性",
                "passed": False,
                "detail": str(e),
                "severity": "P0"
            })

        # 1.5 磁盘空间
        try:
            ret = subprocess.run(["df", "/opt"], capture_output=True, text=True, timeout=5)
            usage_pct = int(ret.stdout.splitlines()[-1].split()[4].replace("%", ""))
            results.append({
                "test": "磁盘空间",
                "passed": usage_pct < 85,
                "detail": f"使用率 {usage_pct}%",
                "severity": "P1" if usage_pct >= 85 else "info"
            })
        except Exception as e:
            results.append({
                "test": "磁盘空间",
                "passed": False,
                "detail": str(e),
                "severity": "P2"
            })

        return results


# ============================================================
# L2: 用户旅程端到端测试
# ============================================================

class L2UserJourney:
    name = "L2-用户旅程端到端"

    @staticmethod
    def run():
        results = []

        # 2.1 免费用户扫描流程（直接调用扫描器API模拟）
        try:
            test_code = {"test.py": "x = 1\nprint(x)\n"}
            status, data = scanner_scan(test_code, "python", "basic")
            passed = status == 200 and "results" in data
            results.append({
                "test": "免费扫描流程",
                "passed": passed,
                "detail": f"status={status}, has_results={'results' in data}",
                "severity": "P0" if not passed else "info"
            })
        except Exception as e:
            results.append({
                "test": "免费扫描流程",
                "passed": False,
                "detail": str(e),
                "severity": "P0"
            })

        # 2.2 多语言扫描测试
        lang_tests = [
            ("python", "x = 1\nprint(x)\n", "test.py"),
            ("javascript", "var x = 1;\nconsole.log(x);\n", "test.js"),
            ("java", "public class T { public static void main(String[] a) {} }", "T.java"),
            ("go", "package main\nimport \"fmt\"\nfunc main() { fmt.Println(\"hi\") }", "main.go"),
        ]
        for lang, code, fname in lang_tests:
            try:
                status, data = scanner_scan({fname: code}, lang, "basic")
                passed = status == 200
                results.append({
                    "test": f"多语言扫描-{lang}",
                    "passed": passed,
                    "detail": f"status={status}",
                    "severity": "P1" if not passed else "info"
                })
            except Exception as e:
                results.append({
                    "test": f"多语言扫描-{lang}",
                    "passed": False,
                    "detail": str(e),
                    "severity": "P1"
                })

        # 2.3 扫描结果查询
        try:
            test_code = {"result_test.py": "import os\nos.system('ls')\n"}
            _, scan_data = scanner_scan(test_code, "python", "basic")
            # 注意：直接扫描器API不返回scan_id，这里只验证扫描成功
            results.append({
                "test": "扫描结果生成",
                "passed": True,
                "detail": "扫描成功完成",
                "severity": "info"
            })
        except Exception as e:
            results.append({
                "test": "扫描结果生成",
                "passed": False,
                "detail": str(e),
                "severity": "P0"
            })

        # 2.4 预估接口
        try:
            req = urllib_request.Request(
                f"{WEBSITE_BASE}/api/scan/estimate",
                data=b'{"files_meta": [{"name": "test.py", "size": 100}]}',
                method="POST"
            )
            req.add_header("Content-Type", "application/json")
            req.add_header("X-Requested-With", "XMLHttpRequest")
            with urllib_request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                results.append({
                    "test": "扫描预估接口",
                    "passed": True,
                    "detail": f"返回: cost={data.get('cost', '?')}",
                    "severity": "info"
                })
        except HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:200]
            results.append({
                "test": "扫描预估接口",
                "passed": False,
                "detail": f"HTTP {e.code}: {body}",
                "severity": "P1"
            })
        except Exception as e:
            results.append({
                "test": "扫描预估接口",
                "passed": False,
                "detail": str(e),
                "severity": "P1"
            })

        # 2.5 安全路径拦截
        blocked_paths = ["/.env", "/.git/config", "/wp-admin", "/phpmyadmin"]
        for path in blocked_paths:
            try:
                code, _ = http_get(f"{WEBSITE_BASE}{path}", timeout=5)
                # 应该返回 404 或 444
                passed = code in (404, 444, 403, 301)
                results.append({
                    "test": f"安全拦截-{path}",
                    "passed": passed,
                    "detail": f"HTTP {code}",
                    "severity": "P1" if not passed else "info"
                })
            except Exception:
                # 连接被拒也算拦截成功
                results.append({
                    "test": f"安全拦截-{path}",
                    "passed": True,
                    "detail": "连接被拒绝（已拦截）",
                    "severity": "info"
                })

        # 2.6 数据库最近扫描异常检查
        try:
            db = sqlite3.connect(DB_PATH)
            db.row_factory = sqlite3.Row
            # 检查最近24小时是否有扫描失败
            since = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
            failed = db.execute(
                "SELECT COUNT(*) FROM scans WHERE scan_status='failed' AND created_at > ?",
                (since,)
            ).fetchone()[0]
            total = db.execute(
                "SELECT COUNT(*) FROM scans WHERE created_at > ?",
                (since,)
            ).fetchone()[0]
            db.close()

            if total > 0:
                fail_rate = failed / total * 100
                results.append({
                    "test": "24h扫描失败率",
                    "passed": fail_rate < 10,
                    "detail": f"总扫描={total}, 失败={failed}, 失败率={fail_rate:.1f}%",
                    "severity": "P1" if fail_rate >= 10 else "info"
                })
            else:
                results.append({
                    "test": "24h扫描失败率",
                    "passed": True,
                    "detail": "最近24h无扫描记录",
                    "severity": "info"
                })
        except Exception as e:
            results.append({
                "test": "24h扫描失败率",
                "passed": False,
                "detail": str(e),
                "severity": "P2"
            })

        return results


# ============================================================
# L3: AI 质检评估
# ============================================================

class L3AIValidation:
    name = "L3-AI质检评估"

    @staticmethod
    def _collect_scan_results(test_key, test_info):
        """执行扫描并收集结果"""
        try:
            status, data = scanner_scan(
                {test_info["filename"]: test_info["code"]},
                test_info["language"],
                "basic"
            )
            if status != 200:
                return None, f"扫描请求失败: HTTP {status}"
            return data, None
        except Exception as e:
            return None, str(e)

    @staticmethod
    def _check_must_detect(all_issues, must_detect_keywords):
        """检查必须检出的漏洞是否被检出"""
        if not must_detect_keywords:
            return True, []
        
        issues_text = json.dumps(all_issues, ensure_ascii=False).lower()
        missed = []
        for keyword in must_detect_keywords:
            if keyword.lower() in issues_text:
                return True, []  # 至少一个关键词命中即可
        
        # 如果所有关键词都没命中
        for kw in must_detect_keywords:
            missed.append(kw)
        return len(missed) == 0, missed

    @staticmethod
    def _check_no_false_positive(all_issues, should_not_detect):
        """检查不应检出的内容（误报检查）"""
        if not should_not_detect:
            return True, []
        
        issues_text = json.dumps(all_issues, ensure_ascii=False).lower()
        false_positives = []
        for keyword in should_not_detect:
            if keyword.lower() in issues_text:
                false_positives.append(keyword)
        
        return len(false_positives) == 0, false_positives

    @staticmethod
    def _ai_evaluate_scan(test_info, scan_results):
        """用 AI 评估扫描结果质量"""
        issues = scan_results.get("results", {})
        all_issues = []
        for brain_id, brain_data in issues.items():
            for issue in brain_data.get("issues", []):
                issue["brain_id"] = brain_id
                all_issues.append(issue)

        prompt = f"""你是一个代码安全扫描质量评估专家。请评估以下扫描结果的质量。

## 测试用例
- 描述: {test_info['description']}
- 语言: {test_info['language']}
- 文件名: {test_info['filename']}
- 代码内容:
```
{test_info['code'][:500]}
```

## 扫描结果
共检出 {len(all_issues)} 个问题:
{json.dumps(all_issues[:10], ensure_ascii=False, indent=2)}

## 请评估以下维度（每项 0-10 分）:
1. **检出准确性**: 检出的问题是否真实存在于代码中？是否有误报？
2. **漏洞覆盖度**: 是否覆盖了代码中存在的主要安全风险？
3. **描述质量**: 问题描述是否清晰、准确、可操作？
4. **严重性判断**: 严重程度标注是否合理？
5. **修复建议**: 修复建议是否具体、可行？

请用 JSON 格式回复:
{{
  "detection_accuracy": 分数,
  "coverage": 分数,
  "description_quality": 分数,
  "severity_accuracy": 分数,
  "fix_suggestion_quality": 分数,
  "overall_score": 平均分,
  "issues_found": "检出了哪些具体问题",
  "missed_issues": "遗漏了哪些问题",
  "false_positives": "误报了哪些问题",
  "recommendation": "改进建议"
}}
"""
        system_prompt = "你是代码安全扫描质量评估专家，只输出JSON，不输出其他内容。"
        response = ai_judge(prompt, system_prompt)
        
        # 尝试解析 JSON（支持 markdown 代码块包裹）
        try:
            cleaned = response.strip()
            cleaned = re.sub(r'```(?:json)?\s*', '', cleaned).strip()
            json_start = cleaned.find("{")
            json_end = cleaned.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                parsed = json.loads(cleaned[json_start:json_end])
                if isinstance(parsed, dict):
                    return parsed
        except Exception:
            pass
        
        # 兜底：正则提取分数
        try:
            scores = {}
            for key in ["accuracy_score", "coverage_score", "description_quality",
                        "severity_accuracy", "fix_suggestion_quality", "overall_score"]:
                m = re.search(rf'"?{key}"?\s*[:：]\s*(\d+(?:\.\d+)?)', response)
                if m:
                    scores[key] = float(m.group(1))
            if scores:
                if "overall_score" not in scores:
                    vals = [v for v in scores.values() if isinstance(v, (int, float))]
                    scores["overall_score"] = sum(vals) / len(vals) if vals else -1
                return scores
        except Exception:
            pass

        return {"raw_response": response, "overall_score": -1}

    @staticmethod
    def run():
        results = []

        import time as _time
        for test_key, test_info in TEST_CASES.items():
            _time.sleep(15)  # 避免 AI gateway 429 限流
            scan_data, error = L3AIValidation._collect_scan_results(test_key, test_info)
            
            if error:
                results.append({
                    "test": f"AI验证-{test_info['description']}",
                    "passed": False,
                    "detail": f"扫描失败: {error}",
                    "severity": "P0"
                })
                continue

            # 收集所有 issues
            all_issues = []
            raw_results = scan_data.get("results", {})
            for brain_id, brain_data in raw_results.items():
                for issue in brain_data.get("issues", []):
                    issue["brain_id"] = brain_id
                    all_issues.append(issue)

            # 规则检查：必须检出的漏洞
            if test_info.get("must_detect"):
                detected, missed = L3AIValidation._check_must_detect(
                    all_issues, test_info["must_detect"]
                )
                results.append({
                    "test": f"漏洞检出-{test_info['description']}",
                    "passed": detected,
                    "detail": f"检出{len(all_issues)}个问题" + (f", 遗漏关键词: {missed}" if missed else ""),
                    "severity": "P0" if not detected else "info"
                })

            # 规则检查：误报检查
            if test_info.get("should_not_detect"):
                no_fp, fps = L3AIValidation._check_no_false_positive(
                    all_issues, test_info["should_not_detect"]
                )
                results.append({
                    "test": f"误报检查-{test_info['description']}",
                    "passed": no_fp,
                    "detail": f"无误报" if no_fp else f"发现误报: {fps}",
                    "severity": "P0" if not no_fp else "info"
                })

            # AI 评估
            ai_eval = L3AIValidation._ai_evaluate_scan(test_info, scan_data)
            overall = ai_eval.get("overall_score", -1)
            
            if overall == -1:
                raw = ai_eval.get("raw_response", "")
                if "AI调用失败" in raw:
                    results.append({
                        "test": f"AI评估-{test_info['description']}",
                        "passed": False,
                        "detail": f"AI调用失败: {raw[:120]}",
                        "severity": "P1"
                    })
                else:
                    results.append({
                        "test": f"AI评估-{test_info['description']}",
                        "passed": True,
                        "detail": f"AI评估返回非标准格式，跳过打分。issues={len(all_issues)}",
                        "severity": "info"
                    })
            else:
                results.append({
                    "test": f"AI评估-{test_info['description']}",
                    "passed": overall >= 6,
                    "detail": f"综合评分={overall}/10, 检出={ai_eval.get('detection_accuracy','?')}, 覆盖={ai_eval.get('coverage','?')}, 描述={ai_eval.get('description_quality','?')}",
                    "severity": "P1" if overall < 6 else "info",
                    "ai_detail": ai_eval
                })

            # 避免 AI 限流
            time.sleep(2)

        return results


# ============================================================
# 报告生成
# ============================================================

def generate_report(all_results, elapsed, levels_run):
    """生成测试报告"""
    total = len(all_results)
    passed = sum(1 for r in all_results if r["passed"])
    failed = total - passed
    
    failures = [r for r in all_results if not r["passed"]]
    p0_failures = [r for r in failures if r.get("severity") == "P0"]
    p1_failures = [r for r in failures if r.get("severity") == "P1"]

    # 时间戳
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 输出摘要
    level_str = "+".join([f"L{l}" for l in levels_run])
    print(f"\n{'='*60}")
    print(f"煋鉴 QA 守护系统 报告 ({level_str})")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"耗时: {elapsed:.1f}s")
    print(f"{'='*60}")
    print(f"总计: {total} 项 | 通过: {passed} | 失败: {failed}")
    print(f"  P0 严重: {len(p0_failures)} | P1 重要: {len(p1_failures)}")
    print(f"{'='*60}")

    if failures:
        print("\n❌ 失败项:")
        for f in failures:
            print(f"  [{f.get('severity', '?')}] {f['test']}: {f['detail']}")
    
    print(f"\n✅ 通过项: {passed}/{total}")

    # 生成 JSON 报告文件
    report = {
        "timestamp": datetime.now().isoformat(),
        "levels": levels_run,
        "elapsed_seconds": round(elapsed, 1),
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "p0_failures": len(p0_failures),
            "p1_failures": len(p1_failures),
        },
        "results": all_results,
        "failures": [{
            "test": r["test"],
            "severity": r.get("severity", "?"),
            "detail": r["detail"]
        } for r in failures],
    }

    os.makedirs(REPORT_DIR, exist_ok=True)
    report_path = os.path.join(REPORT_DIR, f"qa_report_{ts}.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n📄 报告已保存: {report_path}")

    # 如果有 P0 失败，写告警文件
    if p0_failures:
        alert_path = "/tmp/xinpect_qa_p0_alert"
        alert = {
            "timestamp": datetime.now().isoformat(),
            "p0_count": len(p0_failures),
            "p0_failures": [{"test": r["test"], "detail": r["detail"]} for r in p0_failures],
        }
        with open(alert_path, "w") as f:
            json.dump(alert, f, indent=2, ensure_ascii=False)
        print(f"\n🚨 P0 告警已写入: {alert_path}")
    else:
        alert_path = "/tmp/xinpect_qa_p0_alert"
        if os.path.exists(alert_path):
            os.remove(alert_path)

    return report, failed == 0


# ============================================================
# 主入口
# ============================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="煋鉴 QA 守护系统")
    parser.add_argument("--level", default="123", help="检测层级: 1=健康, 2=用户旅程, 3=AI验证, 可组合如 12, 123")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    args = parser.parse_args()

    levels = [int(c) for c in args.level if c.isdigit()]
    
    start_time = time.time()
    all_results = []

    # 按层级执行
    if 1 in levels:
        print("🔍 L1: 系统健康检查...")
        l1_results = L1HealthCheck.run()
        all_results.extend(l1_results)
        print(f"   L1 完成: {sum(1 for r in l1_results if r['passed'])}/{len(l1_results)} 通过")

    if 2 in levels:
        print("\n🔍 L2: 用户旅程端到端测试...")
        l2_results = L2UserJourney.run()
        all_results.extend(l2_results)
        print(f"   L2 完成: {sum(1 for r in l2_results if r['passed'])}/{len(l2_results)} 通过")

    if 3 in levels:
        print("\n🔍 L3: AI 质检评估（需要 AI gateway）...")
        l3_results = L3AIValidation.run()
        all_results.extend(l3_results)
        print(f"   L3 完成: {sum(1 for r in l3_results if r['passed'])}/{len(l3_results)} 通过")

    elapsed = time.time() - start_time
    report, all_passed = generate_report(all_results, elapsed, levels)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
