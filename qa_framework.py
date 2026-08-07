#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
======================================================================
[DEPRECATED / 已归档] 本文件为旧版单体引擎 (qa_framework.py, 506KB)
[SCAN_EXCLUDE] 煋鉴扫描时跳过此文件（已拆分为 brains/ + core/ 模块化架构）
======================================================================
======================================================================
自煋鉴 v2.0 章鱼架构升级后，本文件的核心功能已被 brains/core 层
模块化替代。保留此文件仅供历史参考和渐进式迁移兼容。

⚠️ 新开发请勿依赖此文件，请使用 brains/ 和 core/ 下的模块。
   - 规则引擎: brains/brain1_rule_engine.py
   - AI 引擎:  brains/brain2_ai_engine.py
   - 契约系统: core/task_contract.py
   - 结果聚合: core/result_aggregator.py
   - 全局常量: core/constants.py
======================================================================

通用软件QA验证框架 v2.0.0 - 可插拔规则引擎架构
- v2.0.0核心升级: 全新可插拔规则引擎架构(core/) + 6端173条规则(rules/) + 三大服务集成(误报过滤/深度诊断/评分)
- 向后兼容: 默认使用旧引擎(v21.x)，--use-new-engine启用v2.0新引擎
v21.0.3优化: 5.4AI复制按钮误报收紧+5.5AI头像非AI产品跳过+5.15品牌色自动检测
v21.0.2修复: 8.1/8.2启发式检测降级为代码坏味道+严重程度降为info
v21.0.1新增: Next.js/Vue项目类型识别 + 构建产物检查逻辑修正 + 误报率大幅优化
v21.0.0新增: 三大新模块(单元测试建议/代码坏味道/安全渗透验证) + 架构识别层 + 场景感知层
v20新增: AI深度诊断(M18) + 输出结构改造(按严重程度排序) + 基础规范折叠展示
v19新增: 架构依赖方向检查(M17) + 阿里"依赖必须指向稳定方向"原则落地
用法: python qa_framework.py [result_mode] [project_path] [backend_path] [config_path]
      python qa_framework.py --mode diff --base-branch main --background "需求描述"
      python qa_framework.py --use-new-engine --engine-mode hybrid  # v2.0新引擎
"""


from __future__ import annotations  # PEP 563: 延迟注解求值，支持前向引用
import asyncio
import sys
import os
import re
import json
try:
    import ui_checks
except ImportError:
    ui_checks = None
import ast
import time
import hashlib
__version__ = "1.1.3"
__old_engine_version__ = "21.0.3"  # 旧引擎历史版本号，不再变更
import subprocess
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Tuple, Optional, Any

# ===== P1根因修复: 新增两层检测架构 =====
# 确保技能根目录在sys.path中（importlib动态加载时可能缺失）
_SKILL_ROOT = os.path.dirname(os.path.abspath(__file__))
if _SKILL_ROOT not in sys.path:
    sys.path.insert(0, _SKILL_ROOT)

# ===== v1.23.0: 全局monkey-patch os.path.relpath，修复Windows跨盘符崩溃 =====
try:
    from core.utils import safe_relpath as _safe_relpath
    os.path.relpath = _safe_relpath
except ImportError:  # noqa: intentional empty handler
    pass

try:
    from core.architecture_detector import (
        detect_architecture_style, is_ops_script, get_non_ops_files,
        should_apply_ddd_rules, get_rule_strictness_level, get_applicable_checks,
        ARCH_STYLE_NAMES, OPS_SCRIPT_PATTERNS,
    )
    _HAS_ARCH_DETECTOR = True
except ImportError:
    _HAS_ARCH_DETECTOR = False

try:
    from core.context_analyzer import (
        is_mock_context, is_mock_value, analyze_sql_scene,
        analyze_file_operation_scene, detect_file_scene, detect_function_scene,
        is_safe_sensitive_line, needs_manual_verification,
        SCENE_MOCK_TEST, SCENE_HTTP_HANDLER, SCENE_EMAIL_ATTACHMENT,
        SCENE_LOCAL_FILE_READ, SCENE_OPS_PATCH, SCENE_NAMES,
    )
    _HAS_CONTEXT_ANALYZER = True
except ImportError:
    _HAS_CONTEXT_ANALYZER = False

# P1修复: 架构识别全局缓存（避免每个模块重复检测）
_ARCH_INFO_CACHE = {}

def _get_cached_arch_info(project_path, backend_path, config):
    """全局缓存的架构识别结果，按项目路径缓存"""
    cache_key = f"{project_path}|{backend_path}"
    if cache_key in _ARCH_INFO_CACHE:
        return _ARCH_INFO_CACHE[cache_key]
    
    if not _HAS_ARCH_DETECTOR:
        result = {
            "style": "unknown",
            "style_name": "未知架构",
            "confidence": 0.0,
            "skip_ddd_checks": False,
            "is_ddd": False,
            "reason": "架构识别模块不可用",
            "ops_scripts": [],
        }
    else:
        result = detect_architecture_style(project_path, backend_path, config)
    
    _ARCH_INFO_CACHE[cache_key] = result
    return result

# ===== 参数区 =====
try:
    try:
        from coze_workload_identity import requests
    except ImportError:
        from coze_workload_identity import requests
except ImportError:
    requests = None

# ===== 商业化模块：激活、License验证、付费引导 =====
import urllib.request
import urllib.error
import getpass

_COMMERCIAL_SERVER = os.environ.get("XINPECT_SERVER_URL", "https://starwang.cn")

def _validate_server_url(url: str) -> str:
    """SEC: validate server URL to prevent SSRF/path traversal."""
    import urllib.parse
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Invalid URL scheme: {parsed.scheme}")
    if not parsed.hostname:
        raise ValueError("URL missing hostname")
    return url
_CONFIG_DIR = os.path.expanduser("~/.xinpect")
_CONFIG_FILE = os.path.join(_CONFIG_DIR, "config.json")
_ACTIVATION_FAILED = False  # 全局标记：激活失败时降级为免费版

def _load_local_config():
    """读取本地激活配置文件，返回dict或None"""
    try:
        if os.path.isfile(_CONFIG_FILE):
            with open(_CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError, OSError) as e:  # noqa: intentional empty handler
        pass
    return None

def _save_local_config(data: dict):
    """保存激活配置到本地文件"""
    os.makedirs(_CONFIG_DIR, exist_ok=True)
    with open(_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def _verify_license_online(token: str) -> bool:
    """调用后端验证license是否有效"""
    try:
        payload = json.dumps({"token": token}).encode('utf-8')
        _srv = _validate_server_url(_COMMERCIAL_SERVER)
        api_req = urllib.request.Request(
            f"{_srv}/api/license/verify",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(api_req, timeout=5) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            return result.get("valid", False)
    except Exception as e:  # noqa: broad exception handling
        return False

def _activate_license(email: str, password: str) -> dict:
    """调用后端激活接口，返回包含token的dict或None"""
    try:
        payload = json.dumps({"email": email, "password": password}).encode('utf-8')
        _srv = _validate_server_url(_COMMERCIAL_SERVER)
        api_req = urllib.request.Request(
            f"{_srv}/api/auth/activate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(api_req, timeout=10) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            if result.get("token"):
                return {
                    "email": email,
                    "token": result["token"],
                    "activated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                }
            else:
                return None
    except Exception as e:  # noqa: intentional catch-all
        print(f"[商业化] 激活请求失败: {e}")
        return None

def _is_paid_user() -> bool:
    """检查当前用户是否为付费用户（有效token）"""
    config = _load_local_config()
    if not config or not config.get("token"):
        return False
    # 本地有token，在线验证（如果网络不可用则信任本地缓存）
    try:
        return _verify_license_online(config["token"])
    except Exception as e:  # noqa: broad exception handling
        # 网络不可用时信任本地缓存
        return True

def _check_and_activate():
    """
    CLI激活流程：检查本地配置 → 提示输入 → 激活 → 保存token
    激活失败时降级为免费版，返回False
    """
    global _ACTIVATION_FAILED

    # 1. 检查本地已有配置
    config = _load_local_config()
    if config and config.get("token"):
        # 已有token，尝试验证
        if _verify_license_online(config["token"]):
            if not BRIEF_MODE:
                print(f"[商业化] 已激活用户: {config.get('email', 'unknown')}")
            return True
        else:
            if not BRIEF_MODE:
                print("[商业化] 本地token已失效，请重新激活")

    # 2. 非交互式环境（如CI/CD）跳过激活提示
    if not sys.stdin.isatty():
        if not BRIEF_MODE:
            print("[商业化] 非交互式环境，跳过激活，使用免费版")
        _ACTIVATION_FAILED = True
        return False

    # 3. 提示用户输入
    print("\n" + "=" * 50)
    print("  🔓 煋鉴 Xinpect - 激活专业版")
    print("=" * 50)
    print("  输入邮箱和密码激活，或按Enter跳过使用免费版")
    print("-" * 50)

    try:
        email = input("  邮箱: ").strip()
        if not email:
            print("  ⚠️ 未输入邮箱，使用免费版运行")
            _ACTIVATION_FAILED = True
            return False

        password = getpass.getpass("  密码: ")
        if not password:
            print("  ⚠️ 未输入密码，使用免费版运行")
            _ACTIVATION_FAILED = True
            return False
    except (EOFError, KeyboardInterrupt):
        print("\n  ⚠️ 跳过激活，使用免费版运行")
        _ACTIVATION_FAILED = True
        return False

    # 4. 调用激活接口
    print("  正在激活...")
    result = _activate_license(email, password)
    if result:
        _save_local_config(result)
        print(f"  ✅ 激活成功！欢迎 {email}")
        return True
    else:
        print("  ❌ 激活失败，请检查邮箱/密码或网络连接")
        print("  ⚠️ 将以免费版继续运行（3大脑模式）")
        _ACTIVATION_FAILED = True
        return False

_UPGRADE_GUIDE = """
---
## 🔓 解锁完整能力

当前使用免费版（3大脑），解锁5大专业大脑获得：
- B4 性能分析：内存泄漏、数据库优化、算法复杂度
- B5 依赖审计：CVE漏洞、许可证合规、SBOM管理
- B6 代码质量：技术债务估算、可维护性评分
- B7 架构合规：DDD分层检查、依赖方向验证

**立即升级 →** https://starwang.cn

反馈邮箱：hdyabcd@163.com
"""

# ===== 参数默认值（importlib加载时使用，避免触发argparse副作用）=====
RESULT_MODE = "notify"
BRIEF_MODE = True  # 精简输出模式，默认开启
PROJECT_PATH = ""
BACKEND_PATH = ""
CONFIG_PATH = ""
QA_MODE = "full"
QA_BASE_BRANCH = "main"
QA_BACKGROUND = ""
QA_RULE_PATH = ""
USE_NEW_ENGINE = False
ENGINE_MODE = "hybrid"
ENABLE_FP_FILTER = True
ENABLE_DEEP_DIAGNOSIS = True
ENABLE_TELEMETRY = True
ENABLE_INCREMENTAL = False
# v1.25.0 新增：分级执行 + 缓存 + fail-fast + AI精准投放
QA_LEVEL = "standard"
NO_CACHE = False
CACHE_CLEAR = False
NO_FAIL_FAST = False
AI_FULL = False
PERF_REPORT = False
SINCE_REF = "HEAD~1"



def _handle_ecosystem_command(command: str, remaining_args: list):
    """v3.0.0: 处理生态闭环子命令"""
    if command == "rule-effectiveness":
        from core.rule_effectiveness import RuleEffectivenessTracker
        tracker = RuleEffectivenessTracker()
        days = 30
        if remaining_args:
            try:
                days = int(remaining_args[0])
            except (ValueError, IndexError):  # noqa: intentional empty handler
                pass
        report = tracker.generate_effectiveness_report(days)
        print(report)

    elif command == "scan-trend":
        from core.scan_analyzer import ScanHistoryAnalyzer
        analyzer = ScanHistoryAnalyzer()
        report = analyzer.generate_trend_report()
        print(report)

    elif command == "feedback-summary":
        from core.feedback_collector import FeedbackCollector
        collector = FeedbackCollector()
        report = collector.generate_feedback_report()
        print(report)


def _parse_and_set_args():
    """解析命令行参数并设置全局变量（仅在直接运行时执行，不影importlib加载）"""
    global RESULT_MODE, PROJECT_PATH, BACKEND_PATH, CONFIG_PATH
    global QA_MODE, QA_BASE_BRANCH, QA_BACKGROUND, QA_RULE_PATH
    global USE_NEW_ENGINE, ENGINE_MODE, ENABLE_FP_FILTER, ENABLE_DEEP_DIAGNOSIS
    global ENABLE_TELEMETRY, ENABLE_INCREMENTAL
    global QA_LEVEL, NO_CACHE, CACHE_CLEAR, NO_FAIL_FAST, AI_FULL, PERF_REPORT, SINCE_REF
    global _args

    import argparse
    _parser = argparse.ArgumentParser(description="通用软件QA验证框架")
    _parser.add_argument("result_mode", nargs="?", default="notify", help="结果模式")
    _parser.add_argument("--result_mode", dest="result_mode_flag", default=None, help="结果模式(命名参数)")
    _parser.add_argument("--project_path", default="", help="前端项目路径")
    _parser.add_argument("--backend_path", default="", help="后端代码路径")
    _parser.add_argument("--config_path", default="", help="配置文件路径")
    _parser.add_argument("--project_type", default="", help="项目类型覆盖")
    _parser.add_argument("--mode", default="full", help="审查模式: full(全量) 或 diff(增量)")
    _parser.add_argument("--base-branch", dest="base_branch", default="main", help="diff模式基准分支(默认main)")
    _parser.add_argument("--background", default="", help="需求背景描述")
    _parser.add_argument("--rule", default="", help="自定义规则文件路径")
    _parser.add_argument("--use-new-engine", dest="use_new_engine", action="store_true", default=False,
        help="v2.0新引擎: 使用可插拔规则引擎")
    _parser.add_argument("--engine-mode", dest="engine_mode", default="hybrid",
        help="新引擎运行模式: new / hybrid(默认) / old")
    _parser.add_argument("--no-fp-filter", dest="no_fp_filter", action="store_true", default=False,
        help="禁用误报过滤服务(默认启用)")
    _parser.add_argument("--no-deep-diagnosis", dest="no_deep_diagnosis", action="store_true", default=False,
        help="禁用AI深度诊断服务(默认启用,无LLM时自动跳过)")
    _parser.add_argument("--no-telemetry", dest="no_telemetry", action="store_true", default=False,
        help="禁用匿名数据上报(默认启用)")
    _parser.add_argument("--brief", dest="brief_mode", action="store_true", default=True, help="精简输出模式(默认)，只输出最终结果")
    _parser.add_argument("-v", "--verbose", dest="verbose_mode", action="store_true", default=False, help="详细输出模式，显示逐模块过程")
    _parser.add_argument("--incremental", dest="incremental", action="store_true", default=True,
        help="增量检查模式(默认开启): 仅检查变更文件，首次全量后续自动增量")
    _parser.add_argument("--no-incremental", dest="incremental", action="store_false", help="禁用增量模式，强制全量扫描")
    # v1.25.0 新增参数：分级执行 + 缓存 + fail-fast + AI精准投放
    _parser.add_argument("--level", dest="level", default="standard",
        choices=["quick", "standard", "full"],
        help="v1.25执行级别: quick(只跑规则引擎) | standard(规则+性能+依赖+UI) | full(全部5大脑)")
    _parser.add_argument("--since", dest="since", default="HEAD~1",
        help="增量对比基准（默认HEAD~1）")
    _parser.add_argument("--no-cache", dest="no_cache", action="store_true", default=False,
        help="跳过缓存，每次重新扫描")
    _parser.add_argument("--cache-clear", dest="cache_clear", action="store_true", default=False,
        help="清除所有缓存后退出")
    _parser.add_argument("--no-fail-fast", dest="no_fail_fast", action="store_true", default=False,
        help="禁用fail-fast模式（默认启用：发现blocker立即停止低优先级规则）")
    _parser.add_argument("--ai-full", dest="ai_full", action="store_true", default=False,
        help="AI全量审查（不限问题文件，默认只审查有问题文件）")
    _parser.add_argument("--perf-report", dest="perf_report", action="store_true", default=False,
        help="输出性能报告（各大脑耗时统计）")
    _args, _remaining = _parser.parse_known_args()

    RESULT_MODE = _args.result_mode_flag or _args.result_mode
    global BRIEF_MODE
    BRIEF_MODE = not _args.verbose_mode if _args.verbose_mode else _args.brief_mode

    # ===== v3.0.0: 生态闭环子命令拦截 =====
    if RESULT_MODE in ("rule-effectiveness", "scan-trend", "feedback-summary"):
        _handle_ecosystem_command(RESULT_MODE, _remaining)
        sys.exit(0)
    if RESULT_MODE.startswith(("/", ".")) and not _args.project_path:
        PROJECT_PATH = RESULT_MODE
        RESULT_MODE = "notify"
        if _remaining:
            BACKEND_PATH = _remaining[0] if len(_remaining) > 0 else ""
            CONFIG_PATH = _remaining[1] if len(_remaining) > 1 else ""
        else:
            BACKEND_PATH = ""
            CONFIG_PATH = ""
    else:
        PROJECT_PATH = _args.project_path
        BACKEND_PATH = _args.backend_path
        CONFIG_PATH = _args.config_path
        if not PROJECT_PATH and _remaining:
            PROJECT_PATH = _remaining[0] if len(_remaining) > 0 else ""
            BACKEND_PATH = _remaining[1] if len(_remaining) > 1 else (BACKEND_PATH or "")
            CONFIG_PATH = _remaining[2] if len(_remaining) > 2 else (CONFIG_PATH or "")

    QA_MODE = _args.mode
    QA_BASE_BRANCH = _args.base_branch
    QA_BACKGROUND = _args.background
    QA_RULE_PATH = _args.rule
    USE_NEW_ENGINE = _args.use_new_engine
    ENGINE_MODE = _args.engine_mode
    ENABLE_FP_FILTER = not _args.no_fp_filter
    ENABLE_DEEP_DIAGNOSIS = not _args.no_deep_diagnosis
    ENABLE_TELEMETRY = not _args.no_telemetry
    ENABLE_INCREMENTAL = _args.incremental
    QA_LEVEL = _args.level
    NO_CACHE = _args.no_cache
    CACHE_CLEAR = _args.cache_clear
    NO_FAIL_FAST = _args.no_fail_fast
    AI_FULL = _args.ai_full
    PERF_REPORT = _args.perf_report
    SINCE_REF = _args.since

    if not BRIEF_MODE:
        print(f"[参数] result_mode={RESULT_MODE}, project_path={PROJECT_PATH}")
    if not BRIEF_MODE:
        print(f"[参数] backend_path={BACKEND_PATH}, config_path={CONFIG_PATH}")
    if not BRIEF_MODE:
        print(f"[参数] mode={QA_MODE}, base_branch={QA_BASE_BRANCH}, background={QA_BACKGROUND!r}")
    if not BRIEF_MODE:
        print(f"[参数] use_new_engine={USE_NEW_ENGINE}, engine_mode={ENGINE_MODE}")
    if not BRIEF_MODE:
        print(f"[参数] fp_filter={ENABLE_FP_FILTER}, deep_diagnosis={ENABLE_DEEP_DIAGNOSIS}")
    if not BRIEF_MODE:
        print(f"[参数] telemetry={ENABLE_TELEMETRY}, incremental={ENABLE_INCREMENTAL}")

# ===== 默认配置 =====
DEFAULT_CONFIG = {
    "thresholds": {
        "nav_depth_max": 3,
        "function_lines_warning": 80,
        "function_lines_error": 150,
        "duplication_similarity": 0.8,
        "main_package_size_mb": 2,
        "total_package_size_mb": 20,
        "large_image_kb_warning": 100,
        "large_image_kb_error": 300,
        "setdata_kb_warning": 256,
        "wxml_node_warning": 200,
        "wxml_node_error": 1000,
        "concurrent_requests_warning": 5,
        "storage_mb_warning": 1,
        "code_dup_rate_max": 0.10,
        "cyclomatic_complexity_max": 15,
        "brand_colors": ["#E87722", "#FF6B35"],
        "card_border_radius": "12px",
        "brand_color": "#E87722",
        "brand_color_name": "primary",
        "min_button_height": 44,
        "min_metric_font_size": 28,
        "max_tab_count": 4,
        "indicator_style": "dots",
        "ai_avatar_type": "brand_icon",
        "forbidden_emojis": ["🤖", "💡", "📊", "📋", "🔔", "✅", "🤝", "📝", "🎯", "🔥", "💰", "📈", "🎉", "⚠️"],
        "min_body_font_size_rpx": 24,
        "spacing_system_rpx": [16, 24, 32, 40, 48, 64, 96],
        "max_spacing_values": 15,
        "min_contrast_ratio": 4.5,
        "min_contrast_large": 3.0,
        "max_no_hover_ratio": 0.5,
    },
    "exclude_dirs": ["node_modules", "miniprogram_npm", ".git", "__pycache__", "venv", "pkg", "pymysql", ".pymysql", "codeact", "ec-canvas", "tests", "test", "n8n-workflows"],
    "exclude_files": [".min.js", ".min.css", ".min.wxss"],
    "backend_exclude_files": ["b2_order_forecast.py", "d3_d9_extension.py", "check_layers.py", "create_layer.py", "create_layer2.py", "get_config.py", "update_env.py", "upload_scf.py", "upload_scf_sdk.py", "qa_framework.py", "qa_workflow.py", "ui_design_audit.py", "store_video_analysis.py", "video_content_extract.py", "meituan_food_safety_audit.py", "transcribe_audio.py"],
    "public_actions": {
        "/api/auth": ["register", "send_code", "login", "wx_login", "confirm_password", "session_ttl_options"]
    },
    "smoke_test_urls": [],
    "smoke_test_base_url": "",
    "reference_backend_path": "",
    "reference_frontend_mapping": "",
}

# ===== 项目类型检测 =====
PROJECT_TYPE_NAMES = {
    "miniprogram": "微信小程序",
    "web": "网页/Web应用",
    "python_backend": "Python后端(SCF)",
    "flask": "Python后端(Flask)",
    "electron": "Electron桌面端",
    "skill": "扣子技能",
    "agent": "Agent/工作流",
    "mixed": "混合项目(前端+后端)",
    "mixed_electron": "混合项目(Electron+Python)",
    "unknown": "未知类型",
}

# 模块适用性: "all" = 所有类型适用; 列表 = 仅列出的类型适用
MODULE_APPLICABILITY = {
    "1": ["miniprogram", "web", "mixed", "electron", "mixed_electron"],  # API链路 - 需要前端
    "2": ["miniprogram", "web", "mixed", "electron", "mixed_electron"],  # 页面导航 - 需要前端
    "3": "all",                                       # 安全审计 - 通用
    "4": ["miniprogram", "web", "mixed", "electron", "mixed_electron"],  # 数据一致性 - 需要前端+后端
    "5": ["miniprogram", "web", "mixed", "electron", "mixed_electron"],  # UI设计(28项) - 需要前端
    "6": "all",                                       # 代码质量 - 通用
    "7": "all",                                       # 部署就绪 - 通用
    "8": ["miniprogram", "web", "mixed", "electron", "mixed_electron"],  # 业务流程 - 需要前端
    "9": "all",                                       # 架构健康 - 通用
    "10": "all",                                      # 冒烟测试 - 通用(需URL)
    "11": "all",                                      # 变更影响 - 通用(需参照)
    "12": ["miniprogram", "web", "mixed", "electron", "mixed_electron"],  # 性能与资源 - 前端专项
    "13": "all",                                      # 错误处理与韧性 - 通用
    "14": "all",                                      # 测试与持续集成 - 通用
    "15": "all",                                      # Git Diff增量审查 - 通用(需git仓库)
    "16": "all",                                      # 反思验证 - 通用(AI审查模式)
    "17": "all",                                      # 架构依赖方向检查 - 通用
    "18": "all",                                      # v20: AI深度诊断 - 通用(需LLM)
    "19": ["miniprogram"],                              # 小程序配置合法性 - 仅小程序
    "20": "all",                                       # 单元测试建议 - 通用
    "21": "all",                                       # 代码坏味道检测 - 通用
    "22": "all",                                       # 安全渗透验证 - 通用
}

def detect_project_type(project_path: str, backend_path: str, override: str = "") -> str:
    """自动检测项目类型，支持手动覆盖"""
    if override and override in PROJECT_TYPE_NAMES:
        return override

    has_wxml = False
    has_html = False
    has_py = False
    has_skill_md = False
    has_app_json_pages = False
    has_electron = False
    has_flask = False
    has_nextjs = False
    has_tsx_jsx = False
    has_vue = False

    search_paths = []
    if project_path and os.path.isdir(project_path):
        search_paths.append(project_path)
    if backend_path and backend_path != project_path and os.path.isdir(backend_path):
        search_paths.append(backend_path)

    _exclude = {"node_modules", "miniprogram_npm", ".git", "__pycache__", "venv", ".pymysql", "codeact", "archived", "ec-canvas"}
    for search_path in search_paths:
        for root, dirs, files in os.walk(search_path):
            dirs[:] = [d for d in dirs if d not in _exclude]
            for f in files:
                if f.endswith(".wxml"):
                    has_wxml = True
                elif f.endswith((".html", ".htm")):
                    has_html = True
                elif f.endswith(".py"):
                    has_py = True
                    # Flask检测：检查.py文件中是否有Flask特征
                    if not has_flask:
                        content = safe_read(os.path.join(root, f))
                        if re.search(r'from\s+flask|import\s+flask|@app\.route|Flask\s*\(__name__|flask_restful|flask_cors', content):
                            has_flask = True
                elif f == "SKILL.md":
                    has_skill_md = True
                elif f == "app.json":
                    content = safe_read(os.path.join(root, f))
                    if '"pages"' in content:
                        has_app_json_pages = True
                elif f == "package.json":
                    # Electron检测：检查package.json中是否有electron依赖
                    content = safe_read(os.path.join(root, f))
                    if not has_electron:
                        if re.search(r'"electron"\s*:', content) or re.search(r'"electron"', content):
                            has_electron = True
                elif f in ("main.js", "main.ts", "electron.js", "electron.ts") and not has_electron:
                    # Electron检测：检查main.js中是否有BrowserWindow/ipcRenderer等特征
                    content = safe_read(os.path.join(root, f))
                    if re.search(r'BrowserWindow|ipcMain|ipcRenderer|app\.on\s*\(|electron', content):
                        has_electron = True
                elif f.startswith("next.config."):
                    # Next.js配置文件检测
                    has_nextjs = True
                elif f.endswith((".tsx", ".jsx")):
                    has_tsx_jsx = True
                elif f == "package.json" and not has_nextjs:
                    # Next.js/Vue框架检测
                    content = safe_read(os.path.join(root, f))
                    if re.search(r'"next"\s*:', content):
                        has_nextjs = True
                    if re.search(r'"vue"\s*:', content):
                        has_vue = True

    if has_skill_md:
        return "skill"
    if has_wxml and has_app_json_pages:
        if has_py:
            return "mixed"
        return "miniprogram"
    if has_electron:
        if has_flask or has_py:
            return "mixed_electron"
        return "electron"
    if has_html:
        if has_flask:
            return "mixed"
        if has_py:
            return "mixed"
        return "web"
    # Next.js / Vue / React 前端项目（无.html但有.tsx/.jsx+框架特征）
    if has_nextjs or has_vue:
        if has_flask or has_py:
            return "mixed"
        return "web"
    # 纯React/Vue项目（有tsx/jsx但未检测到框架配置）
    if has_tsx_jsx:
        if has_flask or has_py:
            return "mixed"
        return "web"
    if has_flask:
        return "flask"
    if has_py:
        return "python_backend"
    return "unknown"

def is_module_applicable(module_id: str, project_type: str) -> bool:
    """检查模块是否适用于当前项目类型"""
    applicable = MODULE_APPLICABILITY.get(module_id, "all")
    if applicable == "all":
        return True
    return project_type in applicable

# ===== 检查项级跳过矩阵 =====
# 精确到每个检查项编号，控制模块内部分检查项的跳过
# 格式: {项目类型: {模块ID: {检查项ID: 跳过原因}}}
# 原则: 只跳过"跑了也没意义/必然误报"的检查项，不跳过"可能有问题"的检查项
CHECK_SKIP = {
    "skill": {
        "3": {
            "3.1": "无数据库，SQL注入不适用",
            "3.3": "无Web前端，XSS不适用",
            "3.4": "无鉴权系统，鉴权绕过不适用",
            "3.5": "无Web服务，CORS/CSRF不适用",
            "3.7": "走平台工具调用，SSRF不适用",
            "3.8": "无数据操作，越权访问不适用",
            "3.9": "CLI工具，速率限制不适用",
            "3.10": "无鉴权体系，JWT不适用",
            "3.11": "无API handler，输入校验不适用",
            "3.12": "无文件上传功能",
        },
        "10": {
            "10.3": "无API服务地址，动态连通性不适用",
            "10.4": "无API服务地址，认证流程不适用",
            "10.5": "无API服务地址，业务链路不适用",
            "10.6": "非SSR应用，Hydration检查不适用",
            "10.7": "无Web服务，CORS检查不适用",
        },
        "13": {
            "13.3": "CLI工具不需要全局错误处理器",
            "13.6": "CLI工具不需要健康检查端点",
            "13.8": "CLI工具不需要标准化错误响应",
        },
    },
    "agent": {
        "3": {
            "3.1": "无数据库，SQL注入不适用",
            "3.3": "无Web前端，XSS不适用",
            "3.4": "无鉴权系统，鉴权绕过不适用",
            "3.5": "无Web服务，CORS/CSRF不适用",
            "3.7": "走平台工具调用，SSRF不适用",
            "3.8": "无数据操作，越权访问不适用",
            "3.9": "Agent工作流，速率限制不适用",
            "3.10": "无鉴权体系，JWT不适用",
            "3.11": "无API handler，输入校验不适用",
            "3.12": "无文件上传功能",
        },
        "10": {
            "10.3": "无API服务地址，动态连通性不适用",
            "10.4": "无API服务地址，认证流程不适用",
            "10.5": "无API服务地址，业务链路不适用",
            "10.6": "非SSR应用，Hydration检查不适用",
            "10.7": "无Web服务，CORS检查不适用",
        },
        "13": {
            "13.3": "Agent不需要全局错误处理器",
            "13.6": "Agent不需要健康检查端点",
            "13.8": "Agent不需要标准化错误响应",
        },
    },
    "electron": {
        "10": {
            "10.6": "Electron非SSR应用，Hydration检查不适用",
            "10.7": "Electron使用IPC通信，CORS检查不适用",
        },
    },
    "mixed_electron": {
        "10": {
            "10.6": "Electron非SSR应用，Hydration检查不适用",
        },
    },
    "flask": {
        "10": {
            "10.6": "Flask API非SSR应用，Hydration检查不适用",
        },
    },
    "python_backend": {
        "10": {
            "10.6": "SCF后端非SSR应用，Hydration检查不适用",
        },
        "13": {
            "13.6": "SCF无独立健康检查端点",
        },
    },
}

# ===== 工具函数 =====
def load_config(config_path: str) -> dict:
    if config_path and os.path.isfile(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            user_cfg = json.load(f)
        cfg = dict(DEFAULT_CONFIG)
        for k, v in user_cfg.items():
            if isinstance(v, dict) and k in cfg and isinstance(cfg[k], dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
        return cfg
    return dict(DEFAULT_CONFIG)

def safe_read(path: str) -> str:
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    except Exception as e:  # noqa: broad exception handling
        return ""

def find_files(root: str, exts: list, exclude_dirs: list, exclude_files: list) -> list:
    result = []
    if not root or not os.path.isdir(root):
        return result
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
        for fn in filenames:
            if any(fn.endswith(ef) for ef in exclude_files):
                continue
            if any(fn.endswith(ext) for ext in exts):
                result.append(os.path.join(dirpath, fn))
    return result

def severity_icon(level: str) -> str:
    return {"error": "❌", "warning": "⚠️", "info": "💡"}.get(level, "💡")

# ===== v20: 基础规范类检查项定义 =====
# 这些检查项偏代码风格/视觉规范/管理规范，不直接影响功能运行和安全性
# 在报告中会被折叠展示，不占主要篇幅


# ===== 检查结果 =====

# ===== P0重构: 检查项三分类体系 =====
# bug: 可靠性问题（功能缺陷、安全漏洞、性能问题等会导致程序出错的问题）
# code_smell: 可维护性问题（代码风格、可读性、复杂度、设计选择优化建议等）
# engineering_maturity: 工程成熟度（单元测试、CI/CD、.gitignore、文档等工程化指标）


# ===== P0重构: 项目画像模块 =====












def _get_main_backend_file(backend_path: str) -> str:
    """当backend_path是目录时，找到index_v2.py；是文件时直接返回"""
    if not backend_path:
        return ""
    if os.path.isfile(backend_path):
        return backend_path
    if os.path.isdir(backend_path):
        candidate = os.path.join(backend_path, "index_v2.py")
        if os.path.isfile(candidate):
            return candidate
    return ""

def _get_backend_content(backend_path: str) -> str:
    """读取主后端文件内容（支持目录和文件两种模式）"""
    path = _get_main_backend_file(backend_path)
    return safe_read(path) if path else ""

def _get_all_backend_py_files(backend_path: str, config: dict) -> list:
    """获取所有后端.py文件（排除pkg/pymysql/工具脚本）"""
    if not backend_path:
        return []
    exclude_files = set(config.get("backend_exclude_files", []))
    if os.path.isfile(backend_path):
        return [backend_path]
    all_files = find_files(backend_path, [".py"], config["exclude_dirs"], config["exclude_files"])
    result = []
    for f in all_files:
        basename = os.path.basename(f)
        if basename in exclude_files or basename == "__init__.py":
            continue
        result.append(f)
    return result

def _get_all_backend_content(backend_path: str, config: dict) -> str:
    """获取所有后端.py文件的合并内容"""
    parts = []
    for f in _get_all_backend_py_files(backend_path, config):
        parts.append(safe_read(f))
    return "\n".join(parts)

def _get_match_context(content, lines, match_start):
    """Get line number and surrounding context for a regex match position."""
    line_no = _line_num(content, match_start)
    cur_line = lines[line_no - 1] if line_no - 1 < len(lines) else ""
    prev_line = lines[line_no - 2] if line_no - 2 >= 0 else ""
    return line_no, cur_line, prev_line


def _line_num(content: str, pos: int) -> int:
    """根据内容位置获取行号"""
    return content[:pos].count('\n') + 1

def _skip_checks(results: list, module_name: str, check_ids: list, reason: str = "未指定项目路径，跳过") -> list:
    """跳过模块所有检查项"""
    for cid in check_ids:
        results.append(CheckResult(cid, module_name, "info", reason, "", ""))
    return results

# ===== 模块基类 =====
# BaseModule 已迁至 core/base_module.py
from core.base_module import BaseModule  # noqa: E402,F401


def _detect_backend_architecture(backend_path, config):
    """
    P2升级: 智能检测后端架构类型，返回架构信息
    支持的架构：
    - unified_entry: 统一入口模式（通配路由 + 内部action/domain分发）
    - domain_routes: DOMAIN_ROUTES字典声明式路由（多引擎架构）
    - flask_decorator: Flask @app.route装饰器路由（RESTful风格）
    - rpc: RPC风格（每个方法独立endpoint）
    - graphql: GraphQL模式（单一endpoint + query）
    - unknown: 无法识别
    """
    result = {
        "type": "unknown",
        "confidence": 0,
        "features": [],
        "unified_entry": False,
        "domains_count": 0,
        "actions_count": 0,
        "has_domain_routes": False,
        "note": ""
    }
    if not backend_path or not os.path.isdir(backend_path):
        result["note"] = "无后端代码，跳过架构检测"
        return result
    
    content = _get_backend_content(backend_path)
    all_content = _get_all_backend_content(backend_path, config)
    
    # 检测1：DOMAIN_ROUTES字典模式
    if "DOMAIN_ROUTES = {" in content or "DOMAIN_ROUTES={" in content:
        result["type"] = "domain_routes"
        result["confidence"] = 0.9
        result["features"].append("DOMAIN_ROUTES字典")
    elif "DOMAIN_ROUTES = {" in all_content or "DOMAIN_ROUTES={" in all_content:
        result["type"] = "domain_routes"
        result["confidence"] = 0.8
        result["features"].append("DOMAIN_ROUTES字典(多文件)")
    
    # 检测2：Flask装饰器路由
    flask_count = len(re.findall(r"@app\.route\(|@blueprint\.route\(", all_content))
    if flask_count > 0:
        result["features"].append(f"Flask装饰器路由({flask_count}处)")
        if result["confidence"] < 0.5:
            result["type"] = "flask_decorator"
            result["confidence"] = 0.7
    
    # 检测3：统一入口通配模式
    unified_patterns = [
        r"/api/<path:subpath>",
        r"main_handler\(",
        r"scf_event",
        r"serverless_handler",
    ]
    unified_count = 0
    for pat in unified_patterns:
        if re.search(pat, all_content):
            unified_count += 1
    if unified_count >= 2:
        result["unified_entry"] = True
        result["features"].append(f"统一入口架构({unified_count}个特征)")
        if result["confidence"] < 0.6:
            result["type"] = "unified_gateway"
            result["confidence"] = 0.75
    
    # P2升级: 统计domain和action数量
    routes = _parse_backend_routes_enhanced(backend_path, config)
    result["domains_count"] = len(routes)
    result["actions_count"] = sum(len(actions) for actions in routes.values())
    result["has_domain_routes"] = "DOMAIN_ROUTES" in all_content or "DOMAIN_ROUTES" in content
    
    if result["type"] == "domain_routes" and result["unified_entry"]:
        result["note"] = f"多引擎架构统一入口模式：{result['domains_count']}个domain，{result['actions_count']}个action，通配路由+DOMAIN_ROUTES内部分发"
    elif result["unified_entry"]:
        result["note"] = f"统一入口网关模式：{result['domains_count']}个domain，{result['actions_count']}个action，静态分析可能不完整"
    elif result["type"] == "domain_routes":
        result["note"] = f"DOMAIN_ROUTES字典模式：{result['domains_count']}个domain，{result['actions_count']}个action"
    
    return result


def _parse_backend_routes_enhanced(backend_path, config):
    """增强版后端路由解析，支持多种架构"""
    routes = {}
    if not backend_path:
        return routes
    
    content = _get_backend_content(backend_path)
    all_content = _get_all_backend_content(backend_path, config)
    
    # 方法1：DOMAIN_ROUTES字典模式
    target_content = content if "DOMAIN_ROUTES" in content else all_content
    idx = target_content.find("DOMAIN_ROUTES = {")
    if idx < 0:
        idx = target_content.find("DOMAIN_ROUTES={")
    if idx >= 0:
        brace_count = 0
        end = idx
        for i, c in enumerate(target_content[idx:], idx):
            if c == '{':
                brace_count += 1
            elif c == '}':
                brace_count -= 1
                if brace_count == 0:
                    end = i + 1
                    break
        routes_text = target_content[idx:end]
        domain_pattern = re.compile(r'"/(api/[\w-]+)"\s*:\s*{([^}]+)}', re.DOTALL)
        action_pattern = re.compile(r'"(\w+)"\s*:')
        for m in domain_pattern.finditer(routes_text):
            domain = "/" + m.group(1)
            actions_block = m.group(2)
            actions = action_pattern.findall(actions_block)
            routes[domain] = actions
    
    # 方法2：Flask装饰器路由（补充）
    if not routes:
        flask_routes = re.findall(r"@app\.route\(\s*['\"]([^'\"]+)['\"]", all_content)
        for route in flask_routes:
            if route.startswith('/api/'):
                parts = route.split('/')
                if len(parts) >= 3:
                    domain = '/' + '/'.join(parts[1:3])
                    if domain not in routes:
                        routes[domain] = []
    
    return routes


# ===== 模块1: API链路完整性 =====
def _parse_backend_routes(backend_path: str, config: dict) -> dict:
    """兼容包装：调用增强版路由解析"""
    return _parse_backend_routes_enhanced(backend_path, config)


def _parse_backend_routes_legacy(backend_path: str, config: dict) -> dict:
    routes = {}
    if not backend_path:
        return routes
    content = _get_backend_content(backend_path)
    if not content:
        return routes
    idx = content.find("DOMAIN_ROUTES = {")
    if idx < 0:
        return routes
    brace_count = 0
    end = idx
    for i, c in enumerate(content[idx:], idx):
        if c == '{':
            brace_count += 1
        elif c == '}':
            brace_count -= 1
            if brace_count == 0:
                end = i + 1
                break
    routes_text = content[idx:end]
    domain_pattern = re.compile(r'"/(api/[\w-]+)"\s*:\s*{([^}]+)}', re.DOTALL)
    action_pattern = re.compile(r'"(\w+)"\s*:')
    for m in domain_pattern.finditer(routes_text):
        domain = "/" + m.group(1)
        actions_block = m.group(2)
        actions = action_pattern.findall(actions_block)
        routes[domain] = actions
    return routes

def _parse_frontend_api_calls(project_path: str, config: dict) -> dict:
    """解析前端 api('domain', 'action') 实际调用，不从导出方法名推导路径"""
    calls = defaultdict(set)
    if not project_path or not os.path.isdir(project_path):
        return calls
    js_files = find_files(project_path, [".js"], config["exclude_dirs"], config["exclude_files"])
    for jsf in js_files:
        content = safe_read(jsf)
        # Pattern: api('domain', 'action') or api("domain", "action") with literal strings
        for m in re.finditer(r"api\(\s*['\"]([\w-]+)['\"]\s*,\s*['\"]([\w_]+)['\"]", content):
            calls["/api/" + m.group(1)].add(m.group(2))
        # Pattern: api('domain', variable) — dynamic action, register domain only
        for m in re.finditer(r"api\(\s*['\"]([\w-]+)['\"]\s*,\s*(?!['\"])([\w.]+)", content):
            domain = "/api/" + m.group(1)
            if domain not in calls:
                calls[domain] = set()  # empty set means domain is used but actions are dynamic
    return calls

def _check_audit_nearby(be_lines, idx, radius, audit_patterns):
    """检查指定行号附近是否有审计注释"""
    start = max(0, idx - radius)
    end = min(len(be_lines), idx + radius + 1)
    for check_line in be_lines[start:end]:
        for pat in audit_patterns:
            if re.search(pat, check_line, re.IGNORECASE):
                return True
    return False

def _collect_audited_handlers(be_lines):
    """收集所有有审计注释的handler函数名"""
    audited = set()
    for i, line in enumerate(be_lines):
        if re.search(r'#\s*audit:', line, re.IGNORECASE):
            for offset in range(1, 4):
                if i + offset < len(be_lines):
                    m = re.match(r'\s*def\s+(handle_\w+)', be_lines[i + offset])
                    if m:
                        audited.add(m.group(1))
    return audited

def _find_handler_def(be_lines, handler_name):
    """查找handler函数定义位置"""
    for j, def_line in enumerate(be_lines):
        if re.match(rf'\s*def\s+{re.escape(handler_name)}\s*\(', def_line):
            return j
    return -1

def _has_audit_comment(be_lines: list, action: str, radius: int = 5) -> bool:
    """检查后端代码中action定义附近是否有审计注释"""
    if not be_lines or not action:
        return False
    audit_patterns = [r'#\s*audit:', r'#\s*reserved:', r'#\s*internal:', r'#\s*预留', r'#\s*内部', r'#\s*\[B-RESERVED\]']
    audited_handlers = _collect_audited_handlers(be_lines)
    for i, line in enumerate(be_lines):
        if f'"{action}"' in line or f"'{action}'" in line:
            if _check_audit_nearby(be_lines, i, radius, audit_patterns):
                return True
            m = re.search(rf'["\']({re.escape(action)})["\']\s*:\s*["\']?(\w+)', line)
            if m:
                handler_name = m.group(2)
                if handler_name in audited_handlers:
                    return True
                j = _find_handler_def(be_lines, handler_name)
                if j >= 0 and _check_audit_nearby(be_lines, j, radius, audit_patterns):
                    return True
    return False


# =====================================

# =====================================

# =====================================


# ===== 模块5: UI设计规范 =====

def _is_dark_neutral_gray(color: str) -> bool:
    """判断是否为暗灰色系（暗色模式边框色），非品牌色误用。
    判定标准：所有RGB通道 ≤ 0x60（暗），且 max-min ≤ 0x30（中性，非高饱和度强调色）。
    覆盖 #3A3A3A, #2A2A2A, #3A3A5A, #2A3A5A 等暗灰边框色。"""
    if not color.startswith('#') or len(color) < 7:
        return False
    try:
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
    except ValueError:
        return False
    max_c = max(r, g, b)
    min_c = min(r, g, b)
    return max_c <= 0x60 and (max_c - min_c) <= 0x30


# =====================================

# =====================================

# =====================================

# ===== 模块11: 变更影响分析 =====

# ===== 模块14: 测试与持续集成 =====


# ===== 四层规则穿透配置 =====


# ===== 模块15: Git Diff增量审查 =====


# ===== 模块16: AI审查反思验证 =====


# ===== 模块17: 架构依赖方向检查 =====
# 基于"依赖必须指向稳定方向"原则（阿里语义层/整洁架构）
# 内层（领域层）不能依赖外层（基础设施层/表现层）
# 依赖只能从外向内指

# 分层目录关键词映射：层类型 -> 目录名关键词列表
ARCH_LAYER_KEYWORDS = {
    "domain": ["domain", "core", "entities", "entity", "model", "business", "domain_model", "domain_layer",
               "aggregate", "value_object", "vo", "domain_service"],
    "application": ["application", "use_case", "usecase", "app_service", "application_service",
                    "service", "dto", "command", "query"],
    "infrastructure": ["infrastructure", "infra", "repo", "repository", "dao", "data_access",
                       "persistence", "gateway", "impl", "adapter", "config", "utils", "common",
                       "external", "third_party", "integration"],
    "presentation": ["controller", "api", "routes", "route", "views", "view", "ui", "handler",
                     "endpoint", "web", "page", "pages", "frontend", "interface_adapter"],
}

# 领域层禁止的技术依赖关键词（import路径中出现即视为违规）
DOMAIN_FORBIDDEN_IMPORTS = {
    "database_orm": ["sqlalchemy", "pymysql", "psycopg", "sqlite3", "django.db", "mongoengine",
                     "pymongo", "redis", "elasticsearch", "typeorm", "prisma", "sequelize",
                     "knex", "objection", "mongoose", "drizzle",
                     "mysql2", "pg", "mongodb", "@prisma/client", "better-sqlite3", "sqlite"],
    "http_client": ["requests", "httpx", "aiohttp", "urllib", "urllib3", "http.client",
                    "axios", "fetch", "superagent", "got", "node-fetch"],
    "external_sdk": ["boto3", "aliyun", "tencentcloud", "qcloud", "coze", "openai", "anthropic",
                     "@aws-sdk", "@aliyun", "@tencentcloud", "lark", "feishu", "wechatpy",
                     "wx-sdk", "miniprogram-api-promise"],
    "web_framework": ["flask", "django", "fastapi", "tornado", "sanic", "starlette",
                      "express", "koa", "nest", "next", "nuxt", "vue", "react", "angular"],
    "ui_components": ["wxml", "wxss", "vant", "element-ui", "antd", "material-ui",
                      "tkinter", "pyqt", "pyside", "pywebview"],
    "file_io": ["shutil", "pathlib", "tempfile"],
}

# 领域层禁止的技术实现关键词（代码内容中出现即视为不纯）
DOMAIN_IMPURITY_PATTERNS = [
    # SQL操作
    (r'\b(SELECT|INSERT|UPDATE|DELETE|CREATE TABLE|ALTER TABLE|DROP TABLE|JOIN|WHERE|FROM)\b.*?[;\n]', "SQL语句"),
    (r'\bexecute\s*\(\s*["\']\s*(SELECT|INSERT|UPDATE|DELETE)', "SQL执行"),
    # 数据库操作
    (r'\b(session|db|connection|cursor)\.(query|execute|commit|rollback|close)\b', "数据库操作"),
    (r'\b\.save\s*\(\s*\)', "数据库保存"),
    # HTTP调用
    (r'\.(get|post|put|delete|patch|request)\s*\(\s*["\']https?://', "HTTP调用"),
    (r'\b(requests\.|httpx\.|axios\.)', "HTTP客户端调用"),
    (r'\bwx\.request\b', "微信HTTP请求"),
    # 文件IO
    (r'\bopen\s*\(\s*["\'].*?\.\w+["\']', "文件读写"),
    (r'\bos\.(makedirs|remove|rename|listdir|walk)\b', "文件系统操作"),
    # 外部SDK直接调用
    (r'\b(boto3|openai|anthropic)\.(client|Client|resource|api)', "外部SDK调用"),
]

# Python标准库模块（领域层可安全引用）
PYTHON_STDLIB = {
    "abc", "typing", "dataclasses", "enum", "collections", "datetime", "time", "math",
    "re", "json", "uuid", "hashlib", "base64", "decimal", "fractions", "statistics",
    "itertools", "functools", "operator", "copy", "pprint", "warnings", "contextlib",
    "dataclasses", "pathlib", "os", "sys", "io", "string", "struct", "logging",
    "email", "html", "xml", "csv", "configparser", "argparse", "unittest", "pytest",
    "asyncio", "concurrent", "threading", "multiprocessing", "queue", "subprocess",
    "socket", "ssl", "hashlib", "hmac", "secrets", "random", "bisect", "heapq",
}

# =====================================




# ===== v20: M18 AI深度诊断模块 =====


# v21 模块名称映射（含M20-M22新增模块）


# ===== v21新增: M20 单元测试建议模块 =====


# ===== v21新增: M21 代码坏味道检测模块 =====


# ===== v21新增: M22 安全渗透验证模块（基础版） =====


# ===== 生成配置模板 =====

# ===== 主流程 =====


# ================================================================
#  旧检查函数迁移（向后兼容转发导入）
#  原始实现在 legacy/checks/ 目录下
#  放置在文件末尾以避免循环导入（依赖本文件的 safe_read 等工具函数）
# ================================================================

# ================================================================
#  迁移模块转发导入（向后兼容）
#  原始实现在 core/ 和 legacy/modules/ 目录下
#  放置在文件末尾以避免循环导入
# ================================================================

# --- 工具函数（core/utils.py）---
from core.utils import safe_read, find_files, severity_icon  # noqa: E402,F401

# --- 项目画像（core/project_profiler.py）---
from core.project_profiler import (  # noqa: E402,F401
    ProjectProfile,
    _build_project_profile,
    _detect_project_maturity,
    _estimate_main_package_size,
    _estimate_total_package_size,
)

# --- 报告生成与评分（core/report_generator.py）---
from core.report_generator import (  # noqa: E402,F401
    CheckResult,
    generate_report,
    calculate_category_scores,
    get_score_level,
    _validate_and_fix_locations,
    _count_issues_and_passes,
    _is_pass_item,
    _collect_flat_results,
    _severity_rank,
    _qa_fw_classify_severity,
    get_check_category,
    is_basic_style_check,
    BASIC_STYLE_CHECKS,
    CHECK_CATEGORIES,
    CATEGORY_NAMES,
    CATEGORY_ICONS,
    MODULE_NAMES_V20,
    PROJECT_TYPE_NAMES,
)

# --- CLI 入口（cli/main.py）---
from cli.main import main, generate_config_template  # noqa: E402,F401

# --- 模块类（legacy/modules/）---
from legacy.modules.mod1_api import Module1APILinkage  # noqa: E402,F401
from legacy.modules.mod2_navigation import Module2PageNavigation  # noqa: E402,F401
from legacy.modules.mod3_security import Module3SecurityAudit  # noqa: E402,F401
from legacy.modules.mod4_data import Module4DataConsistency  # noqa: E402,F401
from legacy.modules.mod5_ui_design import Module5UIDesign  # noqa: E402,F401
from legacy.modules.mod6_quality import Module6CodeQuality  # noqa: E402,F401
from legacy.modules.mod7_deployment import Module7DeployReadiness  # noqa: E402,F401
from legacy.modules.mod8_business import Module8BusinessFlow  # noqa: E402,F401
from legacy.modules.mod11_change_impact import Module11ChangeImpact  # noqa: E402,F401
from legacy.modules.mod14_test_infra import Module14TestInfrastructure, RulePenetration  # noqa: E402,F401
from legacy.modules.mod15_git_diff import Module15GitDiffReview  # noqa: E402,F401
from legacy.modules.mod16_reflection import Module16ReflectionVerify  # noqa: E402,F401
from legacy.modules.mod17_architecture import Module17ArchitectureDependency  # noqa: E402,F401
from legacy.modules.mod18_ai_diagnosis import Module18AIDeepDiagnosis  # noqa: E402,F401
from legacy.modules.mod19_miniprogram_config import Module19MiniprogramConfig  # noqa: E402,F401
from legacy.modules.mod20_unit_test import Module20UnitTestSuggestion  # noqa: E402,F401
from legacy.modules.mod21_code_smell import Module21CodeSmellDetector  # noqa: E402,F401
from legacy.modules.mod22_penetration import Module22SecurityPenetrationVerify  # noqa: E402,F401


from legacy.checks.common import *  # noqa: E402,F401,F403
from legacy.checks.mod2_navigation import *  # noqa: E402,F401,F403
from legacy.checks.mod3_security import *  # noqa: E402,F401,F403
from legacy.checks.mod4_data import *  # noqa: E402,F401,F403
from legacy.checks.mod6_quality import *  # noqa: E402,F401,F403
from legacy.checks.mod7_deployment import *  # noqa: E402,F401,F403
from legacy.checks.mod8_business import *  # noqa: E402,F401,F403
from legacy.checks.mod17_architecture import *  # noqa: E402,F401,F403


# ===== 注入全局helper到legacy模块（解决拆分后的全局符号缺失问题） =====
# 模块类和检查函数从qa_framework.py拆分到legacy/后，
# 原来共享的全局函数/常量找不到了。统一注入确保向后兼容。
def _inject_legacy_helpers():  # noqa: E302
    import sys as _s
    # 需要注入的符号（当前模块全局作用域中的）
    _helper_names = [
        '_get_backend_content', '_get_all_backend_content', '_get_all_backend_py_files',
        '_detect_backend_architecture', '_parse_backend_routes', '_parse_frontend_api_calls',
        '_has_audit_comment', '_line_num', '_get_match_context', '_skip_checks',
        '_get_main_backend_file', '_find_handler_def', '_collect_audited_handlers',
        '_parse_backend_routes_enhanced', '_parse_backend_routes_legacy',
        'CheckResult', 'BaseModule', 'CHECK_SKIP', 'ARCH_LAYER_KEYWORDS',
        'safe_read', 'find_files', 'severity_icon',
    ]
    _helpers = {_n: globals()[_n] for _n in _helper_names if _n in globals()}
    
    # 注入到所有 legacy.modules.* 和 legacy.checks.* 模块
    for _mod_name, _mod in list(_s.modules.items()):
        if _mod_name.startswith('legacy.modules.') or _mod_name.startswith('legacy.checks.'):
            if _mod is not None:
                for _n, _v in _helpers.items():
                    if not hasattr(_mod, _n):
                        setattr(_mod, _n, _v)

_inject_legacy_helpers()
del _inject_legacy_helpers


if __name__ == "__main__":
    # ===== v3.0.0: 子命令路由 =====
    import sys as _sys
    _argv = _sys.argv[1:]
    if _argv and _argv[0] in ("rule-health", "rule_health", "rulehealth"):
        # 规则健康度检查子命令
        _project = _argv[1] if len(_argv) > 1 else "."
        _project = os.path.abspath(_project) if _project != "." else os.path.dirname(os.path.abspath(__file__))
        try:
            from core.rule_health import run_rule_health
            print(run_rule_health(_project))
        except ImportError as _e:
            print(f"[错误] 规则健康度模块加载失败: {_e}")
            _sys.exit(1)
    else:
        _parse_and_set_args()
        # 当作为脚本直接运行时（__name__ == '__main__'），
        # 确保 sys.modules 中有 'qa_framework' 条目指向当前模块，
        # 这样 cli/main.py 中 import qa_framework 就能拿到同一个模块对象，
        # 全局变量（如 _args, PROJECT_PATH 等）才能正确共享
        if 'qa_framework' not in _sys.modules:
            _sys.modules['qa_framework'] = _sys.modules['__main__']
        asyncio.run(main())


