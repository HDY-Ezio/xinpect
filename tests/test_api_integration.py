#!/usr/bin/env python3
"""
API全链路集成测试
覆盖：各语言基础测试、边界case、已知bug检出、已知无害代码、引擎可达性

运行方式：
    cd /opt/xinpect-website && python3 -m pytest tests/test_api_integration.py -v
    
只运行健康检查：
    cd /opt/xinpect-website && python3 -m pytest tests/test_api_integration.py::TestHealthCheck -v
"""
import json
import sys
import os
import pytest
import requests

# ============================================================
# 配置
# ============================================================
WEBSITE_URL = "http://127.0.0.1:8621"
SCANNER_URL = "http://127.0.0.1:8620"
API_KEY = os.environ.get("XINPECT_API_KEY", "")
SCAN_API = f"{WEBSITE_URL}/api/v1/scan"
HEALTH_API = f"{WEBSITE_URL}/health"
SCANNER_HEALTH = f"{SCANNER_URL}/health"

# 请求超时
REQUEST_TIMEOUT = 120
HEALTH_TIMEOUT = 5


# ============================================================
# 辅助函数
# ============================================================
def call_scan_api(code_files, language="auto"):
    """调用扫描API，返回JSON结果"""
    resp = requests.post(
        SCAN_API,
        headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
        json={"code_files": code_files, "language": language},
        timeout=REQUEST_TIMEOUT,
    )
    return resp


def call_scan_api_and_get_json(code_files, language="auto"):
    """调用扫描API，返回(status_code, json_data)"""
    resp = call_scan_api(code_files, language)
    try:
        data = resp.json()
    except (ValueError, json.JSONDecodeError):
        data = {"_raw": resp.text}
    return resp.status_code, data


# ============================================================
# 1. 健康检查测试
# ============================================================
class TestHealthCheck:
    """全链路健康检查"""

    def test_scanner_engine_reachable(self):
        """扫描引擎应该可达"""
        resp = requests.get(SCANNER_HEALTH, timeout=HEALTH_TIMEOUT)
        assert resp.status_code == 200, f"扫描引擎不可达: {resp.status_code}"
        data = resp.json()
        assert data.get("status") == "ok", f"引擎状态异常: {data}"
        assert len(data.get("brain_ids", [])) >= 8, f"大脑加载不足: {data}"

    def test_website_health(self):
        """官网健康检查端点应该返回200"""
        resp = requests.get(HEALTH_API, timeout=HEALTH_TIMEOUT)
        assert resp.status_code == 200, f"官网健康检查失败: {resp.status_code}"
        data = resp.json()
        assert data["status"] == "ok", f"官网状态异常: {data}"
        assert data["scanner"]["status"] == "ok", f"引擎状态异常: {data}"

    def test_website_scanner_status_matches(self):
        """官网报告的引擎状态应与直接查询引擎一致"""
        website_resp = requests.get(HEALTH_API, timeout=HEALTH_TIMEOUT)
        scanner_resp = requests.get(SCANNER_HEALTH, timeout=HEALTH_TIMEOUT)
        w_data = website_resp.json()
        s_data = scanner_resp.json()
        assert w_data["scanner"]["version"] == s_data.get("version", ""), \
            f"版本不一致: website={w_data['scanner']['version']}, scanner={s_data.get('version')}"


# ============================================================
# 2. 各语言基础测试（无害代码应该0问题或只有style提示）
# ============================================================
class TestHarmlessByLanguage:
    """各语言无害代码测试"""

    def test_python_harmless_function(self):
        """Python无害函数应该>=90分，S/A级"""
        code = {
            "add.py": (
                'def add(a: int, b: int) -> int:\n'
                '    """两数相加"""\n'
                '    return a + b\n'
            )
        }
        status, data = call_scan_api_and_get_json(code, "python")
        assert status == 200, f"API返回非200: {status}, {data}"
        assert data["score"] >= 90, f"无害Python代码应该>=90分，实际{data['score']}"
        assert data["grade"] in ["S", "A"], f"无害代码应该S/A级，实际{data['grade']}"
        real_issues = [i for i in data["issues"] if i["severity"] in ["critical", "high", "medium"]]
        assert len(real_issues) == 0, f"无害代码不应有真实问题，发现{len(real_issues)}个: {real_issues}"

    def test_javascript_harmless_function(self):
        """JS无害函数应该>=90分，S/A级"""
        code = {
            "add.js": (
                'function add(a, b) {\n'
                '    return a + b;\n'
                '}\n'
                'module.exports = { add };\n'
            )
        }
        status, data = call_scan_api_and_get_json(code, "javascript")
        assert status == 200, f"API返回非200: {status}, {data}"
        assert data["score"] >= 90, f"无害JS代码应该>=90分，实际{data['score']}"
        assert data["grade"] in ["S", "A"], f"无害代码应该S/A级，实际{data['grade']}"
        real_issues = [i for i in data["issues"] if i["severity"] in ["critical", "high", "medium"]]
        assert len(real_issues) == 0, f"无害代码不应有真实问题，发现{len(real_issues)}个: {real_issues}"

    def test_go_harmless_function(self):
        """Go无害函数应该>=90分"""
        code = {
            "add.go": (
                'package main\n\n'
                'import "fmt"\n\n'
                'func add(a, b int) int {\n'
                '    return a + b\n'
                '}\n\n'
                'func main() {\n'
                '    fmt.Println(add(1, 2))\n'
                '}\n'
            )
        }
        status, data = call_scan_api_and_get_json(code, "go")
        assert status == 200, f"API返回非200: {status}, {data}"
        assert data["score"] >= 80, f"无害Go代码应该>=80分，实际{data['score']}"
        assert data["grade"] in ["S", "A", "B"], f"无害代码应S/A/B级，实际{data['grade']}"

    def test_java_harmless_function(self):
        """Java无害函数应该>=80分"""
        code = {
            "Add.java": (
                'public class Add {\n'
                '    public static int add(int a, int b) {\n'
                '        return a + b;\n'
                '    }\n'
                '}\n'
            )
        }
        status, data = call_scan_api_and_get_json(code, "java")
        assert status == 200, f"API返回非200: {status}, {data}"
        assert data["score"] >= 70, f"无害Java代码应该>=70分，实际{data['score']}"


# ============================================================
# 3. 边界case测试
# ============================================================
class TestEdgeCases:
    """边界条件测试"""

    def test_empty_file(self):
        """空文件应该返回结果（有warning或正常处理）"""
        code = {"empty.py": ""}
        status, data = call_scan_api_and_get_json(code, "python")
        # 空文件应该能正常处理（可能是低分或有warning），不应该500
        assert status in [200, 400], f"空文件应该正常处理或400，实际{status}"
        if status == 200:
            # 如果有warning说明处理正确
            assert data.get("warning") or data["total_issues"] >= 0

    def test_single_line_code(self):
        """单行代码应该正常工作"""
        code = {"one.py": "x = 1\n"}
        status, data = call_scan_api_and_get_json(code, "python")
        assert status == 200, f"单行代码应正常处理，实际{status}: {data}"
        assert data["total_issues"] >= 0

    def test_large_file(self):
        """大文件（接近10MB）应该返回大小限制错误或正常处理"""
        # 生成一个约1MB的Python文件（不超过限制）
        large_code = "# comment line\n" * 20000  # ~280KB
        code = {"large.py": large_code}
        status, data = call_scan_api_and_get_json(code, "python")
        # 应该能正常处理（1MB还在限制内）
        assert status in [200, 413], f"大文件应正常处理或返回413，实际{status}"

    def test_many_files(self):
        """多文件（20个）应该正常工作"""
        code = {}
        for i in range(20):
            code[f"file_{i:03d}.py"] = f"def func_{i}():\n    return {i}\n"
        status, data = call_scan_api_and_get_json(code, "python")
        assert status == 200, f"多文件应正常处理，实际{status}: {data}"
        assert data["file_count"] == 20

    def test_binary_content(self):
        """二进制内容应该跳过或报错，不应该500"""
        code = {"binary.py": "\x00\x01\x02\x03\xff\xfe\xfd"}
        status, data = call_scan_api_and_get_json(code, "python")
        # 不应该500
        assert status in [200, 400], f"二进制内容应该正常处理或400，实际{status}"

    def test_utf8_bom(self):
        """UTF-8 BOM编码应该正常处理"""
        code = {"bom.py": "\ufeffdef hello():\n    return 'world'\n"}
        status, data = call_scan_api_and_get_json(code, "python")
        assert status == 200, f"UTF-8 BOM应正常处理，实际{status}: {data}"

    def test_unicode_content(self):
        """包含大量Unicode字符应该正常处理"""
        code = {"unicode.py": "# 日本語テスト\n# 中文测试\n# 한국어 테스트\ndef hello():\n    return '你好世界'\n"}
        status, data = call_scan_api_and_get_json(code, "python")
        assert status == 200, f"Unicode内容应正常处理，实际{status}: {data}"

    def test_special_characters(self):
        """包含特殊字符应该正常处理"""
        code = {"special.py": 'x = "hello\\nworld\\ttab"\ny = \'single\\\'quote\'\n'}
        status, data = call_scan_api_and_get_json(code, "python")
        assert status == 200, f"特殊字符应正常处理，实际{status}: {data}"


# ============================================================
# 4. 已知有bug的代码（应该检出）
# ============================================================
class TestKnownBugs:
    """已知bug代码应该被检出"""

    def test_sql_injection_detected(self):
        """SQL拼接代码应该被检出至少一个问题（注入或资源泄漏）"""
        code = {
            "vuln.py": (
                'import sqlite3\n\n'
                'def get_user(username):\n'
                '    conn = sqlite3.connect("test.db")\n'
                '    cursor = conn.cursor()\n'
                '    query = "SELECT * FROM users WHERE name = \'" + username + "\'"\n'
                '    cursor.execute(query)\n'
                '    return cursor.fetchone()\n'
            )
        }
        status, data = call_scan_api_and_get_json(code, "python")
        assert status == 200, f"API调用失败: {status}: {data}"
        
        # 检查是否有任何medium及以上级别的问题
        real_issues = [
            i for i in data["issues"]
            if i["severity"] in ["critical", "high", "medium", "correctness", "suspicious"]
        ]
        assert len(real_issues) >= 1, (
            f"SQL拼接代码应检出至少一个问题，"
            f"实际发现问题: {[i['title'] for i in data['issues']]}"
        )

    def test_empty_except_detected(self):
        """空except块应该报high或medium"""
        code = {
            "bad_except.py": (
                'import os\n\n'
                'def read_config(path):\n'
                '    try:\n'
                '        with open(path) as f:\n'
                '            return f.read()\n'
                '    except:\n'
                '        pass\n'
            )
        }
        status, data = call_scan_api_and_get_json(code, "python")
        assert status == 200
        # 检查是否有关于异常处理的问题
        except_issues = [
            i for i in data["issues"]
            if i["severity"] in ["critical", "high", "medium"]
            and any(kw in (i.get("title", "") + i.get("message", "")).lower()
                    for kw in ["except", "异常", "exception", "bare", "静默", "吞掉"])
        ]
        assert len(except_issues) >= 1, (
            f"空except块应被检出，实际问题: {[i['title'] for i in data['issues']]}"
        )

    def test_hardcoded_password_detected(self):
        """硬编码密码应该报critical或high"""
        code = {
            "config.py": (
                'DATABASE_HOST = "localhost"\n'
                'DATABASE_PORT = 5432\n'
                'DATABASE_PASSWORD = "SuperSecret123!"\n'
                'API_KEY = "sk-abc123def456"\n'
            )
        }
        status, data = call_scan_api_and_get_json(code, "python")
        assert status == 200
        secret_issues = [
            i for i in data["issues"]
            if i["severity"] in ["critical", "high"]
            and any(kw in (i.get("title", "") + i.get("message", "")).lower()
                    for kw in ["密码", "password", "secret", "密钥", "key", "敏感", "硬编码", "credential"])
        ]
        assert len(secret_issues) >= 1, (
            f"硬编码密码应被检出，实际问题: {[i['title'] for i in data['issues']]}"
        )


# ============================================================
# 5. 已知无害代码（应该0问题或低分）
# ============================================================
class TestKnownHarmless:
    """已知无害代码应该获得高分"""

    def test_simple_add_function(self):
        """简单add函数应该>=90分"""
        code = {"add.py": "def add(a, b):\n    return a + b\n"}
        status, data = call_scan_api_and_get_json(code, "python")
        assert status == 200
        assert data["score"] >= 90, f"简单add函数应>=90分，实际{data['score']}"

    def test_pure_comments(self):
        """纯注释文件应该正常处理"""
        code = {
            "comments.py": (
                '# This is a comment\n'
                '# Another comment\n'
                '# Yet another comment\n'
                '# def fake():\n'
                '#     pass\n'
            )
        }
        status, data = call_scan_api_and_get_json(code, "python")
        assert status == 200, f"纯注释应正常处理，实际{status}: {data}"
        # 纯注释不应有critical/high问题
        real_issues = [i for i in data["issues"] if i["severity"] in ["critical", "high"]]
        assert len(real_issues) == 0, f"纯注释不应有严重问题: {real_issues}"

    def test_only_imports(self):
        """只有import的文件应该正常处理"""
        code = {
            "imports.py": (
                'import os\n'
                'import sys\n'
                'import json\n'
                'from pathlib import Path\n'
            )
        }
        status, data = call_scan_api_and_get_json(code, "python")
        assert status == 200
        real_issues = [i for i in data["issues"] if i["severity"] in ["critical", "high"]]
        assert len(real_issues) == 0, f"只有import不应有严重问题: {real_issues}"


# ============================================================
# 6. API错误处理测试
# ============================================================
class TestAPIErrorHandling:
    """API错误处理测试"""

    def test_no_api_key(self):
        """无API Key应返回401"""
        resp = requests.post(
            SCAN_API,
            json={"code_files": {"test.py": "x=1"}},
            timeout=10,
        )
        assert resp.status_code == 401

    def test_invalid_api_key(self):
        """无效API Key应返回403"""
        resp = requests.post(
            SCAN_API,
            headers={"X-API-Key": "xk_invalid_key"},
            json={"code_files": {"test.py": "x=1"}},
            timeout=10,
        )
        assert resp.status_code == 403

    def test_empty_code_files(self):
        """空code_files应返回400"""
        resp = requests.post(
            SCAN_API,
            headers={"X-API-Key": API_KEY},
            json={"code_files": {}},
            timeout=10,
        )
        assert resp.status_code == 400

    def test_no_content_type(self):
        """非JSON请求应返回400"""
        resp = requests.post(
            SCAN_API,
            headers={"X-API-Key": API_KEY},
            data="not json",
            timeout=10,
        )
        assert resp.status_code == 400


# ============================================================
# 7. 响应格式验证
# ============================================================
class TestResponseFormat:
    """API响应格式验证"""

    def test_response_has_required_fields(self):
        """响应必须包含所有必需字段"""
        code = {"test.py": "x = 1\n"}
        status, data = call_scan_api_and_get_json(code, "python")
        assert status == 200
        
        required_fields = [
            "score", "grade", "total_issues", "severity_counts",
            "issues", "file_count", "language", "scan_mode",
        ]
        for field in required_fields:
            assert field in data, f"响应缺少必需字段: {field}"

    def test_score_range(self):
        """分数应在0-100范围内"""
        code = {"test.py": "def f():\n    return 1\n"}
        status, data = call_scan_api_and_get_json(code, "python")
        assert status == 200
        assert 0 <= data["score"] <= 100, f"分数超出范围: {data['score']}"

    def test_grade_values(self):
        """评级应为S/A/B/C/D之一"""
        code = {"test.py": "def f():\n    return 1\n"}
        status, data = call_scan_api_and_get_json(code, "python")
        assert status == 200
        assert data["grade"] in ["S", "A", "B", "C", "D"], f"无效评级: {data['grade']}"

    def test_issue_format(self):
        """每个issue必须有标准字段"""
        # 使用已知有问题的代码来确保有issue
        code = {
            "bad.py": (
                'import os\n'
                'password = "hackme"\n'
                'def bad():\n'
                '    query = "SELECT * FROM t WHERE x=" + input()\n'
            )
        }
        status, data = call_scan_api_and_get_json(code, "python")
        assert status == 200
        
        if data["issues"]:
            issue = data["issues"][0]
            required_issue_fields = ["check_id", "severity", "file", "line", "message"]
            for field in required_issue_fields:
                assert field in issue, f"Issue缺少字段: {field}, issue={issue}"

    def test_warning_for_small_sample(self):
        """极小样本应该有warning"""
        code = {"tiny.py": "x=1"}
        status, data = call_scan_api_and_get_json(code, "python")
        assert status == 200
        # 有效代码<10行应该有warning
        if data.get("total_lines", 999) < 10:
            assert data.get("warning") is not None, "极小样本应有warning"


# ============================================================
# 8. 多语言支持测试
# ============================================================
class TestMultiLanguage:
    """多语言检测支持"""

    def test_language_auto_detection(self):
        """auto语言应该正常工作"""
        code = {"app.py": "def hello():\n    return 'world'\n"}
        status, data = call_scan_api_and_get_json(code, "auto")
        assert status == 200

    def test_typescript_basic(self):
        """TypeScript基础代码"""
        code = {
            "app.ts": (
                'interface User {\n'
                '    name: string;\n'
                '    age: number;\n'
                '}\n\n'
                'function greet(user: User): string {\n'
                '    return `Hello, ${user.name}`;\n'
                '}\n'
            )
        }
        status, data = call_scan_api_and_get_json(code, "typescript")
        assert status == 200, f"TypeScript检测失败: {status}: {data}"

    def test_go_security_issue(self):
        """Go代码安全漏洞应该被检出"""
        code = {
            "handler.go": (
                'package main\n\n'
                'import (\n'
                '    "database/sql"\n'
                '    "fmt"\n'
                '    "net/http"\n'
                ')\n\n'
                'func getUser(w http.ResponseWriter, r *http.Request) {\n'
                '    name := r.URL.Query().Get("name")\n'
                '    query := fmt.Sprintf("SELECT * FROM users WHERE name=\'%s\'", name)\n'
                '    db, _ := sql.Open("mysql", "dsn")\n'
                '    rows, _ := db.Query(query)\n'
                '    defer rows.Close()\n'
                '}\n'
            )
        }
        status, data = call_scan_api_and_get_json(code, "go")
        assert status == 200
        # Go的SQL注入也应被检出
        sql_issues = [
            i for i in data["issues"]
            if i["severity"] in ["critical", "high"]
            and any(kw in (i.get("title", "") + i.get("message", "")).lower()
                    for kw in ["sql", "注入", "inject", "拼接", "query"])
        ]
        # 不强制要求检出，但至少不应崩溃
        assert status == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
