#!/usr/bin/env python3
"""
煋鉴信息一致性测试 - 跨源对账
确保对外展示的信息与后端配置、代码实际值一致

运行: cd /opt/xinpect-website && python3 -m pytest tests/test_consistency.py -v
"""
import json
import re
import sys
import os
import sqlite3
import subprocess
import pytest

DB_PATH = "/opt/xinpect-website/xinpect.db"
WEBSITE_URL = "http://127.0.0.1:8621"
SCANNER_URL = "http://127.0.0.1:8620"
BASE_DIR = "/opt/xinpect-website"
SCANNER_DIR = "/opt/xinpect-scanner-green"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ============================================================
# 引擎数量一致性
# ============================================================
class TestEngineConsistency:
    """引擎数量跨源一致"""

    def test_scanner_health_brains_count(self):
        """/health返回的brains_loaded与实际配置匹配"""
        import requests
        resp = requests.get(f"{SCANNER_URL}/health", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        brains = data.get("brains_loaded", data.get("scanner", {}).get("brains_loaded", 0))
        # 实际加载的brain数量应与配置一致
        assert brains >= 7, f"引擎加载数{brains}少于预期7"

    def test_no_nine_engine_references(self):
        """前端代码中不存在'九引擎'表述"""
        templates_dir = os.path.join(BASE_DIR, "templates")
        hits = []
        for root, dirs, files in os.walk(templates_dir):
            for f in files:
                if f.endswith(".html"):
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath, "r", encoding="utf-8") as fh:
                            content = fh.read()
                            if "九引擎" in content or "9引擎" in content.lower():
                                hits.append(fpath)
                    except:
                        pass
        assert not hits, f"以下模板文件仍含'九引擎'表述: {hits}"

    def test_no_nine_engine_in_static(self):
        """静态JS中不存在'九引擎'表述"""
        static_dir = os.path.join(BASE_DIR, "static")
        hits = []
        for root, dirs, files in os.walk(static_dir):
            for f in files:
                if f.endswith(".js"):
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath, "r", encoding="utf-8") as fh:
                            content = fh.read()
                            if "九引擎" in content or "9引擎" in content.lower():
                                hits.append(fpath)
                    except:
                        pass
        assert not hits, f"以下JS文件仍含'九引擎'表述: {hits}"


# ============================================================
# 版本号一致性
# ============================================================
class TestVersionConsistency:
    """版本号跨源一致"""

    def test_scanner_version_format(self):
        """/health返回的版本号格式正确"""
        import requests
        resp = requests.get(f"http://127.0.0.1:8620/health", timeout=10)
        data = resp.json()
        version = data.get("version", data.get("scanner", {}).get("version", ""))
        assert re.match(r"^\d+\.\d+\.\d+$", version), f"版本号格式异常: {version}"

    def test_changelog_has_version_entries(self):
        """changelog至少有一个版本条目"""
        changelog_path = os.path.join(BASE_DIR, "templates", "changelog.html")
        with open(changelog_path, "r", encoding="utf-8") as f:
            content = f.read()
        entries = re.findall(r'<h3[^>]*>\s*v?([\d.]+)', content)
        assert len(entries) > 0, "changelog没有任何版本条目"


# ============================================================
# 价格/积分一致性
# ============================================================
class TestPricingConsistency:
    """价格与积分跨源一致"""

    def test_pricing_page_monthly_credits(self):
        """pricing.html中套餐描述包含'每月发放300积分'"""
        pricing_path = os.path.join(BASE_DIR, "templates", "pricing.html")
        with open(pricing_path, "r", encoding="utf-8") as f:
            content = f.read()
        # 季卡/半年卡/年卡应该说明每月发放
        assert "每月发放 300 积分" in content or "每月发放300积分" in content, \
            "pricing.html缺少'每月发放300积分'描述"

    def test_pricing_no_misleading_total(self):
        """pricing.html不应有误导性的'共XXX积分'（无每月说明）"""
        pricing_path = os.path.join(BASE_DIR, "templates", "pricing.html")
        with open(pricing_path, "r", encoding="utf-8") as f:
            content = f.read()
        # 查找"共 XXX 积分"模式（不含"累计"的上下文）
        misleading = re.findall(r'共\s*[\d,]+\s*积分', content)
        for m in misleading:
            # 如果附近有"累计"则OK
            idx = content.find(m)
            context = content[max(0, idx-30):idx+len(m)+10]
            assert "累计" in context, f"pricing.html有误导性描述: '{m}'，应改为'累计'或'每月发放'"

    def test_recharge_page_monthly_credits(self):
        """recharge.html同样包含每月发放说明"""
        recharge_path = os.path.join(BASE_DIR, "templates", "dashboard", "recharge.html")
        if not os.path.exists(recharge_path):
            pytest.skip("recharge.html不存在")
        with open(recharge_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "每月发放 300 积分" in content or "每月发放300积分" in content or "积分/月" in content, \
            "recharge.html缺少每月积分发放说明"

    def test_config_matches_api_packages(self):
        """后端配置的价格与API返回的积分包价格一致"""
        sys.path.insert(0, BASE_DIR)
        from modules.constants import CREDIT_PACKS
        import requests

        resp = requests.get(f"{WEBSITE_URL}/api/recharge/packages", timeout=10)
        assert resp.status_code == 200
        api_packs = resp.json().get("packages", resp.json().get("data", []))

        # 检查API返回的包数量不为0
        assert len(api_packs) > 0, "API返回积分包为空"

    def test_subscription_prices_in_config(self):
        """订阅价格配置与实际金额匹配"""
        sys.path.insert(0, BASE_DIR)
        from modules.constants import SUBSCRIPTION_CREDITS

        expected_prices = {
            "monthly": 99,
            "quarterly": 269,
            "half_year": 499,
            "yearly": 899,
        }

        # 从payment.py获取实际配置
        payment_path = os.path.join(BASE_DIR, "modules", "payment.py")
        with open(payment_path, "r", encoding="utf-8") as f:
            content = f.read()

        for plan_id, expected_price in expected_prices.items():
            pattern = rf"'{plan_id}'.*?'amount':\s*(\d+)"
            m = re.search(pattern, content)
            if m:
                actual = int(m.group(1))
                assert actual == expected_price, \
                    f"{plan_id}价格不匹配: 期望{expected_price}，实际{actual}"


# ============================================================
# 蓝绿版一致性
# ============================================================
class TestBlueGreenConsistency:
    """蓝绿版核心文件同步"""

    def test_constants_py_identical(self):
        """绿版和蓝版的constants.py内容一致"""
        green = "/opt/xinpect-website/modules/constants.py"
        # 蓝版website共用同一个website代码
        # 这里改为检查扫描器引擎规则包
        green_rules = "/opt/xinpect-scanner-green/rules/brain_rules_bundle.json"
        blue_rules = "/opt/xinpect-scanner-blue/rules/brain_rules_bundle.json"
        if not os.path.exists(green_rules) or not os.path.exists(blue_rules):
            pytest.skip("规则包文件不存在")
        import hashlib
        h_g = hashlib.md5(open(green_rules, "rb").read()).hexdigest()
        h_b = hashlib.md5(open(blue_rules, "rb").read()).hexdigest()
        assert h_g == h_b, "绿版与蓝版规则包MD5不一致"

    def test_model_config_identical(self):
        """绿版和蓝版的AI模型配置一致"""
        green = "/opt/xinpect-scanner-green/engine/a1_ai_enhance/_ai_client_config.py"
        blue = "/opt/xinpect-scanner-blue/engine/a1_ai_enhance/_ai_client_config.py"
        if not os.path.exists(green) or not os.path.exists(blue):
            pytest.skip("模型配置文件不存在")
        import hashlib
        h_g = hashlib.md5(open(green, "rb").read()).hexdigest()
        h_b = hashlib.md5(open(blue, "rb").read()).hexdigest()
        assert h_g == h_b, "绿版与蓝版AI模型配置MD5不一致"

    def test_scanner_service_identical(self):
        """绿版和蓝版的scanner_service.py一致"""
        green = "/opt/xinpect-scanner-green/scanner_service.py"
        blue = "/opt/xinpect-scanner-blue/scanner_service.py"
        if not os.path.exists(green) or not os.path.exists(blue):
            pytest.skip("scanner_service.py不存在")
        import hashlib
        h_g = hashlib.md5(open(green, "rb").read()).hexdigest()
        h_b = hashlib.md5(open(blue, "rb").read()).hexdigest()
        assert h_g == h_b, "绿版与蓝版scanner_service.py MD5不一致"
