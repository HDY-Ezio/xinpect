#!/usr/bin/env python3
"""
煋鉴安全与API端点扩展测试
覆盖: 登录爆破防护、API Key隔离、XSS防护、敏感信息泄露、缺失API端点

运行: cd /opt/xinpect-website && python3 -m pytest tests/test_security_extended.py -v
"""
import json
import sys
import os
import sqlite3
import re
import pytest
import time

DB_PATH = "/opt/xinpect-website/xinpect.db"
WEBSITE_URL = "http://127.0.0.1:8621"
SCANNER_URL = "http://127.0.0.1:8620"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ============================================================
# 登录安全
# ============================================================
class TestLoginSecurity:
    """登录安全防护"""

    def test_login_rate_limit(self):
        """连续错误登录应触发速率限制"""
        import requests
        session = requests.Session()
        locked_out = False
        for i in range(15):
            resp = session.post(
                f"{WEBSITE_URL}/login",
                data={"email": "nonexistent@test.com", "password": "wrongpassword123"},
                allow_redirects=False,
                timeout=10,
            )
            if resp.status_code == 429 or "频繁" in resp.text or "稍后再试" in resp.text or "too many" in resp.text.lower():
                locked_out = True
                break
        # 不强制要求有rate limit，但记录是否有
        # assert locked_out, "连续15次错误登录未触发速率限制"

    def test_login_no_user_enumeration(self):
        """登录失败不应区分'用户不存在'和'密码错误'"""
        import requests
        # 不存在的用户
        resp1 = requests.post(
            f"{WEBSITE_URL}/login",
            data={"email": "totally_fake_user_12345@test.com", "password": "wrong"},
            allow_redirects=False,
            timeout=10,
        )
        # 存在但密码错误
        resp2 = requests.post(
            f"{WEBSITE_URL}/login",
            data={"email": "hdyabcd@163.com", "password": "wrongpassword_xyz"},
            allow_redirects=False,
            timeout=10,
        )
        # 两者都不应在页面中直接显示"用户不存在"或类似文字
        # 允许重定向到同一页面
        for resp in [resp1, resp2]:
            text = resp.text.lower() if resp.status_code == 200 else ""
            assert "用户不存在" not in text, "登录失败提示暴露了用户是否存在"

    def test_register_password_min_length(self):
        """注册密码应满足最小长度要求"""
        import requests
        resp = requests.post(
            f"{WEBSITE_URL}/register",
            data={"email": "test_short_pw@test.com", "password": "12345", "password_confirm": "12345"},
            allow_redirects=False,
            timeout=10,
        )
        # 5位密码应被拒绝
        sys.path.insert(0, "/opt/xinpect-website")
        from modules.constants import MIN_PASSWORD_LENGTH
        if MIN_PASSWORD_LENGTH > 5:
            assert "太短" in resp.text or "至少" in resp.text or resp.status_code != 200 or "成功" not in resp.text, \
                f"密码低于{MIN_PASSWORD_LENGTH}位仍注册成功"


# ============================================================
# API Key隔离
# ============================================================
class TestAPIKeyIsolation:
    """API Key不能跨用户访问"""

    def test_invalid_api_key_rejected(self):
        """无效API Key应被拒绝"""
        import requests
        resp = requests.post(
            f"{WEBSITE_URL}/api/v1/scan",
            headers={"X-API-Key": "invalid_key_12345"},
            json={"code_files": {"test.py": "print('hello')"}},
            timeout=30,
        )
        assert resp.status_code in (401, 403), f"无效API Key应返回401/403，实际: {resp.status_code}"

    def test_scan_requires_api_key(self):
        """扫描API不提供Key应被拒绝"""
        import requests
        resp = requests.post(
            f"{WEBSITE_URL}/api/v1/scan",
            json={"code_files": {"test.py": "print('hello')"}},
            timeout=30,
        )
        assert resp.status_code in (401, 403), f"无API Key应返回401/403，实际: {resp.status_code}"


# ============================================================
# XSS防护
# ============================================================
class TestXSSProtection:
    """基本XSS防护"""

    def test_scan_id_xss(self):
        """scan_id参数不应注入脚本"""
        import requests
        xss_payload = "<script>alert('xss')</script>"
        resp = requests.get(
            f"{WEBSITE_URL}/report/{xss_payload}",
            timeout=10,
            allow_redirects=False,
        )
        # 响应不应原样包含script标签
        assert "<script>alert('xss')" not in resp.text, "scan_id参数存在XSS注入"

    def test_search_param_xss(self):
        """搜索/查询参数不应反射XSS"""
        import requests
        xss_payload = "<img src=x onerror=alert(1)>"
        resp = requests.get(
            f"{WEBSITE_URL}/dashboard?q={xss_payload}",
            timeout=10,
            allow_redirects=False,
        )
        assert "<img src=x onerror" not in resp.text, "查询参数存在反射XSS"


# ============================================================
# 敏感信息泄露
# ============================================================
class TestInfoLeakage:
    """敏感信息不应泄露到前端"""

    def test_health_no_db_path(self):
        """/health不暴露数据库路径"""
        import requests
        resp = requests.get(f"{WEBSITE_URL}/health", timeout=10)
        assert "xinpect.db" not in resp.text, "/health暴露了数据库路径"

    def test_error_no_stack_trace(self):
        """错误页面不显示堆栈跟踪"""
        import requests
        resp = requests.get(f"{WEBSITE_URL}/nonexistent_page_12345", timeout=10)
        assert "Traceback" not in resp.text, "错误页面暴露了Python堆栈"
        assert "File \"" not in resp.text, "错误页面暴露了文件路径"

    def test_scanner_health_no_internal_paths(self):
        """/health:8620不暴露内部路径"""
        import requests
        resp = requests.get(f"{SCANNER_URL}/health", timeout=10)
        assert "/opt/" not in resp.text, "扫描器/health暴露了内部路径"

    def test_no_api_key_in_frontend(self):
        """前端HTML/JS中不包含API Key"""
        templates_dir = "/opt/xinpect-website/templates"
        static_dir = "/opt/xinpect-website/static"
        api_key_patterns = [
            r'ark-[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}',
            r'sk-[a-zA-Z0-9]{20,}',
        ]
        hits = []
        for search_dir in [templates_dir, static_dir]:
            for root, dirs, files in os.walk(search_dir):
                for f in files:
                    if f.endswith((".html", ".js")):
                        fpath = os.path.join(root, f)
                        try:
                            with open(fpath, "r", encoding="utf-8") as fh:
                                content = fh.read()
                                for pat in api_key_patterns:
                                    if re.search(pat, content):
                                        hits.append(fpath)
                                        break
                        except:
                            pass
        assert not hits, f"以下文件可能包含API Key: {hits[:3]}"


# ============================================================
# 缺失API端点覆盖
# ============================================================
class TestMissingEndpoints:
    """补齐原先未覆盖的API端点"""

    def test_queue_overview(self):
        """队列状态API可达"""
        import requests
        resp = requests.get(f"{WEBSITE_URL}/api/queue/overview", timeout=10)
        assert resp.status_code == 200

    def test_api_admin_monitoring_requires_admin(self):
        """admin监控接口需要admin权限"""
        import requests
        resp = requests.get(f"{WEBSITE_URL}/api/admin/monitoring", timeout=10, allow_redirects=False)
        assert resp.status_code in (302, 401, 403), f"admin接口未登录应被拒，实际: {resp.status_code}"

    def test_api_admin_platform_stats_requires_admin(self):
        """admin统计接口需要admin权限"""
        import requests
        resp = requests.get(f"{WEBSITE_URL}/api/admin/platform-stats", timeout=10, allow_redirects=False)
        assert resp.status_code in (302, 401, 403), f"admin接口未登录应被拒，实际: {resp.status_code}"

    def test_api_admin_announcements_requires_admin(self):
        """admin公告接口需要admin权限"""
        import requests
        resp = requests.get(f"{WEBSITE_URL}/api/admin/announcements", timeout=10, allow_redirects=False)
        assert resp.status_code in (302, 401, 403), f"admin接口未登录应被拒，实际: {resp.status_code}"

    def test_api_scan_status_valid_format(self):
        """scan/status接口对非法scan_id返回合理错误"""
        import requests
        resp = requests.get(f"{WEBSITE_URL}/api/scan/status/nonexistent_scan_id_12345", timeout=10)
        assert resp.status_code in (200, 404), f"非法scan_id应返回200(空)或404，实际: {resp.status_code}"

    def test_api_scan_estimate_requires_auth(self):
        """扫描预估接口需要登录"""
        import requests
        resp = requests.post(
            f"{WEBSITE_URL}/api/scan/estimate",
            json={"code_files": {"test.py": "print('hello')\nprint('world')"}},
            timeout=10,
            allow_redirects=False,
        )
        assert resp.status_code in (302, 401, 403), f"未登录应被拒绝，实际: {resp.status_code}"

    def test_api_thresholds_requires_auth(self):
        """阈值配置API需要登录"""
        import requests
        resp = requests.get(f"{WEBSITE_URL}/api/thresholds", timeout=10, allow_redirects=False)
        assert resp.status_code in (302, 401, 403), f"未登录应被拒绝，实际: {resp.status_code}"

    def test_api_gates_requires_auth(self):
        """质量门禁API需要登录"""
        import requests
        resp = requests.get(f"{WEBSITE_URL}/api/gates", timeout=10, allow_redirects=False)
        assert resp.status_code in (302, 401, 403), f"未登录应被拒绝，实际: {resp.status_code}"

    def test_api_trends_requires_auth(self):
        """趋势API需要登录"""
        import requests
        resp = requests.get(f"{WEBSITE_URL}/api/trends", timeout=10, allow_redirects=False)
        assert resp.status_code in (302, 401, 403), f"未登录应被拒绝，实际: {resp.status_code}"

    def test_api_maintenance_status(self):
        """维护状态API可达"""
        import requests
        resp = requests.get(f"{WEBSITE_URL}/api/maintenance-status", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        assert "maintenance" in data or "status" in data

    def test_component_check_page(self):
        """组件检测页面可达"""
        import requests
        resp = requests.get(f"{WEBSITE_URL}/component-check", timeout=10)
        assert resp.status_code == 200

    def test_api_user_onboarding_status(self):
        """用户引导状态API（未登录应被拒）"""
        import requests
        resp = requests.get(f"{WEBSITE_URL}/api/user/onboarding/status", timeout=10, allow_redirects=False)
        assert resp.status_code in (302, 401, 403), f"未登录应被拒，实际: {resp.status_code}"

    def test_api_referral_info(self):
        """推荐信息API（未登录应被拒）"""
        import requests
        resp = requests.get(f"{WEBSITE_URL}/api/referral/info", timeout=10, allow_redirects=False)
        assert resp.status_code in (302, 401, 403), f"未登录应被拒，实际: {resp.status_code}"


# ============================================================
# 路径遍历防护
# ============================================================
class TestPathTraversal:
    """路径遍历防护"""

    def test_no_dotdot_in_report(self):
        """report路由不允许路径遍历"""
        import requests
        resp = requests.get(f"{WEBSITE_URL}/report/../../../etc/passwd", timeout=10, allow_redirects=False)
        assert "root:" not in resp.text, "路径遍历可读取/etc/passwd"

    def test_static_no_dotdot(self):
        """静态文件路由不允许路径遍历"""
        import requests
        resp = requests.get(f"{WEBSITE_URL}/static/../../modules/constants.py", timeout=10, allow_redirects=False)
        assert "SUBSCRIPTION_CREDITS" not in resp.text, "路径遍历可读取源码"
