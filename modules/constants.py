#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Xinpect - Constants & Configuration
"""


import os
import re
import io
import zipfile
import tarfile
import json
import uuid
import sqlite3
import random
import secrets
import hashlib
import logging
from datetime import datetime, timedelta
from functools import wraps

from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, jsonify, g, make_response)
from werkzeug.security import generate_password_hash, check_password_hash

HAS_REQUESTS = False
http_requests = None
try:
    import requests as http_requests
    HAS_REQUESTS = True
except ImportError:
    print("WARNING: requests 库未安装，支付功能不可用")

# ============================================================
# 配置
# ============================================================

# Project root is parent of modules/
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'xinpect.db')

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app = Flask(__name__,
            template_folder=os.path.join(_project_root, 'templates'),
            static_folder=os.path.join(_project_root, 'static'))
app.config["TEMPLATES_AUTO_RELOAD"] = True
logger = logging.getLogger("xinpect")
logger.setLevel(logging.INFO)

# 日志格式
_log_fmt = logging.Formatter(
    "[%(asctime)s] %(levelname)-7s %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# 应用日志（info+，自动轮转，最大50MB x 5份）
from logging.handlers import RotatingFileHandler
_log_dir = os.path.join(BASE_DIR, "logs")
os.makedirs(_log_dir, exist_ok=True)

_app_handler = RotatingFileHandler(
    os.path.join(_log_dir, "xinpect.log"),
    maxBytes=50*1024*1024, backupCount=5, encoding="utf-8"
)
_app_handler.setLevel(logging.INFO)
_app_handler.setFormatter(_log_fmt)
logger.addHandler(_app_handler)

# 错误日志（error+，单独文件，最大20MB x 3份）
_err_handler = RotatingFileHandler(
    os.path.join(_log_dir, "error.log"),
    maxBytes=20*1024*1024, backupCount=3, encoding="utf-8"
)
_err_handler.setLevel(logging.ERROR)
_err_handler.setFormatter(_log_fmt)
logger.addHandler(_err_handler)

# 同时输出到控制台（便于 journalctl 捕获）
_console = logging.StreamHandler()
_console.setLevel(logging.INFO)
_console.setFormatter(_log_fmt)
logger.addHandler(_console)
# ── 会话签名密钥 ────────────────────────────────────────────────
# 安全修复(2026-10-20)：删除硬编码默认值。
# 原实现 `os.environ.get('XINPECT_SECRET', 'xinpect-dev-secret-key-...')`
# 在未配置环境变量时用公开的开发密钥签名 session，任何人只要知道该字符串
# 即可伪造任意 user_id 的会话（实测可拿到管理员权限）。默认值本身就是漏洞，
# 因此这里改为「不配置就拒绝启动」，不再提供任何兜底值。
_secret_key = (os.environ.get('XINPECT_SECRET') or '').strip()
if len(_secret_key) < 32:
    raise RuntimeError(
        'XINPECT_SECRET 未配置或长度不足 32 位，拒绝启动。'
        '请在 systemd 单元 / EnvironmentFile 中设置强随机密钥'
        '（python3 -c "import secrets;print(secrets.token_hex(32))"）。'
    )
app.secret_key = _secret_key

# 会话 Cookie 加固：禁止 JS 读取、只走 HTTPS、跨站请求不携带
app.config.update(
    MAX_CONTENT_LENGTH=20 * 1024 * 1024,  # 20MB 总上传限制
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
)


# ============================================================
# 常量定义（消除魔法数字）
# ============================================================
MAX_CONTENT_SIZE_MB = 20
MAX_CONTENT_LENGTH = MAX_CONTENT_SIZE_MB * 1024 * 1024  # 20MB
MAX_FILE_SIZE_SINGLE = 10 * 1024 * 1024  # 10MB
MAX_CODE_LENGTH = 50000  # 单文件最大字符数
RESET_CODE_EXPIRY_MINUTES = 15
SCAN_TIMEOUT_SECONDS = 300
REPORT_TIMEOUT_SECONDS = 30
MENFANG_TIMEOUT_SECONDS = 5
MENFANG_PAY_TIMEOUT_SECONDS = 10
MAX_REFERRAL_ATTEMPTS = 50

# --- 推荐奖励配置 ---
REFERRAL_REGISTER_CREDITS = 30          # 推荐人和被推荐人各得30积分
# 充值奖励改为套餐总积分的1/3，见 REFERRAL_REWARD_RATIO below
REFERRAL_REWARD_RATIO = 3                # 充值奖励 = 月积分 / REFERRAL_REWARD_RATIO
# 推荐充值奖励已改为统一公式：双方各得月积分/3
# REFERRAL_REWARD_CREDITS 保留用于兼容

ESTIMATED_UNZIP_FACTOR = 5
ESTIMATED_LINE_SIZE = 50

# HTTP 状态码常量
HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_UNAUTHORIZED = 401
HTTP_PAYMENT_REQUIRED = 402
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_ENTITY_TOO_LARGE = 413
HTTP_INTERNAL_ERROR = 500
HTTP_SERVICE_UNAVAILABLE = 503

# 评分阈值
SCORE_S_THRESHOLD = 95
SCORE_A_THRESHOLD = 80
SCORE_B_THRESHOLD = 60
SCORE_C_THRESHOLD = 30
SCORE_COLOR_AMBER = 60

# 时间常量
REFERRAL_COOKIE_MAX_AGE = 30 * 24 * 3600  # 30天
DEFAULT_CREDIT_TX_LIMIT = 20
DEFAULT_SUBSCRIPTION_DAYS = 30
DEFAULT_MONTHLY_CREDITS = 300
DEFAULT_PORT = 8621
MOCK_SCAN_TIMEOUT = 5

# 评分扣分常量
DEDUCTION_PER_CRITICAL = 10
DEDUCTION_PER_HIGH = 5
DEDUCTION_PER_MEDIUM = 3
DEDUCTION_PER_LOW = 0.5
MAX_DEDUCTION_MEDIUM = 30
MAX_DEDUCTION_LOW = 20
MAX_SCORE = 100

# 验证码常量
RESET_CODE_LENGTH = 6
RESET_CODE_CHECK_LENGTH = 6

# 免费用户可用大脑ID（规范层）
FREE_BRAIN_IDS = ['1', '6', '7', '9']
FREE_BRAIN_ID_SET = {'1', '6', '7', '9'}
# 全量大脑ID
ALL_BRAIN_IDS = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '11']

# 密码最小长度
MIN_PASSWORD_LENGTH = 6

# 次卡积分映射
TOPUP_CREDITS_MAP = {
    'topup_1': 1,
    'topup_5': 5,
    'topup_10': 10,
}

# 代码文件扩展名
CODE_EXTS = {'.py', '.js', '.ts', '.tsx', '.jsx', '.java', '.go', '.cpp', '.c',
             '.h', '.cs', '.php', '.rb', '.rs', '.swift', '.kt', '.wxml', '.wxss',
             '.vue', '.html', '.htm', '.scss', '.less', '.css', '.sass',
             '.json', '.yaml', '.yml', '.toml', '.ini', '.sh', '.bash',
             '.txt', '.lua', '.scala', '.sql', '.r', '.m', '.pl', '.pm',
             '.dart', '.ex', '.exs', '.erl', '.hs', '.clj', '.elm',
             '.v', '.sv', '.vhd', '.vhdl', '.xml', '.md'}

# 压缩包过滤关键词
ARCHIVE_SKIP_DIRS = ('__pycache__', 'node_modules', '.git/',
                     'dist/', 'build/', '.venv', 'venv/',
                     '.DS_Store', 'Thumbs.db')

# 组件检测评分阈值
CC_SCORE_S = 90
CC_SCORE_A = 75
CC_SCORE_B = 60

# 代码长度限制
MAX_WXML_CODE_LENGTH = 50000

# 其他
PRINT_SEPARATOR_LEN = 50

MIN_ESTIMATED_LINES = 5
MIN_ESTIMATED_SIZE_ADDITION = 1024

# 检测服务配置
SCANNER_URL = os.environ.get('SCANNER_URL', 'http://localhost:8620/scan')
# 门房服务（支付+用户权限中心）
MENFANG_BASE_URL = os.environ.get('MENFANG_BASE_URL', 'http://127.0.0.1:8612')

# 每日检测次数限制（v5.4.3 取消免费版次数限制，让用户无门槛使用）
# 免费版无次数、无文件数限制，纯规则引擎零边际成本，用得越多越有利于转化
DAILY_LIMIT_FREE = 999999       # 未登录用户（不限制）
DAILY_LIMIT_REGISTERED = 999999  # 注册免费用户（不限制）

# ============================================================
# 积分制配置（v1.5）
# ============================================================

# 订阅档位每月积分赠送
SUBSCRIPTION_CREDITS = {
    'monthly':   {'name': '月卡',   'monthly_credits': 300,  'days': 30,  'total_credits': 300},
    'quarterly': {'name': '季卡',   'monthly_credits': 300,  'days': 90,  'total_credits': 900},
    'half_year': {'name': '半年卡', 'monthly_credits': 300,  'days': 180, 'total_credits': 1800},
    'yearly':    {'name': '年卡',   'monthly_credits': 300,  'days': 365, 'total_credits': 3600},
}

# 注册赠送积分（v1.5暂不使用，免费版纯次数限制，不送积分）
# SIGNUP_BONUS_CREDITS = 50

# 积分包商品（5档）
CREDIT_PACKS = {
    'credit-100':   {'name': '100积分',   'credits': 100,   'amount': 49,   'mf_plan': 'credit-100'},
    'credit-500':   {'name': '500积分',   'credits': 500,   'amount': 199,  'mf_plan': 'credit-500'},
    'credit-2000':  {'name': '2000积分',  'credits': 2000,  'amount': 599,  'mf_plan': 'credit-2000'},
    'credit-5000':  {'name': '5000积分',  'credits': 5000,  'amount': 1299, 'mf_plan': 'credit-5000'},
    'credit-15000': {'name': '15000积分', 'credits': 15000, 'amount': 2999, 'mf_plan': 'credit-15000'},
    'pack_100':    {'name': '100积分',   'credits': 100,   'amount': 49,   'mf_plan': 'credit-100'},
    'pack_500':    {'name': '500积分',   'credits': 500,   'amount': 199,  'mf_plan': 'credit-500'},
    'pack_2000':   {'name': '2000积分',  'credits': 2000,  'amount': 599,  'mf_plan': 'credit-2000'},
    'pack_5000':   {'name': '5000积分',  'credits': 5000,  'amount': 1299, 'mf_plan': 'credit-5000'},
    'pack_15000':  {'name': '15000积分', 'credits': 15000, 'amount': 2999, 'mf_plan': 'credit-15000'},
}

# 扫描消耗配置（v1.5 按代码行数计费，简化版）
# 定价模型：成本驱动 + 67%毛利率锁定
# 公式：总百行数 × 百行单价，不足100行按100行算（无起步费）
SCAN_COST_BASE_FEE = 0               # 起步费（积分，0=无起步费）
SCAN_COST_PER_100_LINES_BASIC = 0     # 基础版完全免费 # 基础版百行单价（规则引擎，成本极低）
SCAN_COST_PER_100_LINES_FULL = 0.3     # 完整版百行单价（AI全增强）

# ============================================================
# 9 大脑维度定义（+ 小程序专项）
# ============================================================

BRAINS = [
    {'id': '1', 'name': '语法格式', 'icon': '📐', 'desc': '检查代码语法错误、格式规范、编码风格一致性，统一团队代码风格。'},
    {'id': '2', 'name': '安全与依赖审计', 'icon': '🔒', 'desc': '检测注入攻击、硬编码密钥、敏感信息泄露等安全漏洞，同时扫描第三方依赖版本风险、许可证合规、配置文件安全。'},
    {'id': '3', 'name': 'AI语义分析', 'icon': '🧠', 'desc': '基于AST深度分析代码语义，识别未定义变量、异常静默、逻辑死代码等深层缺陷。'},
    {'id': '4', 'name': '性能与可靠性', 'icon': '⚡', 'desc': '识别性能瓶颈：低效循环、冗余计算、内存泄漏风险；新增并发安全检测，防范竞态条件与死锁。'},
    {'id': '5', 'name': '可观测性', 'icon': '📡', 'desc': '全新可观测性引擎：检测日志完整性、错误栈缺失、监控埋点遗漏、告警阈值不合理等可观测性短板。'},
    {'id': '6', 'name': '代码质量与测试', 'icon': '📊', 'desc': '圈复杂度、函数长度、重复代码、Prompt质量等可维护性指标；新增测试质量检测，覆盖测试覆盖率、断言质量、用例完整性。'},
    {'id': '7', 'name': '架构与数据合规', 'icon': '🏗', 'desc': '积木架构五大原则审计（职责清晰/函数精简/入口统一/测试完备/依赖干净）、模块耦合度、分层架构、循环依赖、接口文档完整性等架构健康度；新增数据一致性检测，校验数据流转与字段约定。'},
    {'id': '8', 'name': '业务安全', 'icon': '🛡', 'desc': '支付安全、权限绕过、数据越权、资源/操作配对、事务一致性等业务逻辑漏洞检测。'},
    {'id': '9', 'name': '专项引擎', 'icon': '🧩', 'desc': '前端组件契组合规检测 + 小程序连接完整性专项，覆盖属性约束、嵌套规则、跨文件连接核对、交互完备性等专项场景。'},
    {'id': '10', 'name': '依赖安全(SCA)', 'icon': '📦', 'desc': '第三方依赖已知漏洞(CVE)扫描、过期版本检测、许可证合规校验，覆盖npm/pip/maven/go等主流生态，防范供应链攻击。'},
    {'id': '11', 'name': 'PoC自动验证', 'icon': '🧪', 'desc': '对检出的安全漏洞自动生成PoC攻击载荷，在隔离沙箱中实弹验证漏洞真伪，输出确认/可疑/排除三级结论，降低误报。'},
]

# 三层分组 - 积木架构评级体系
TIERS = [
    {
        'key': 'spec',
        'name': '规范层',
        'subtitle': '代码骨架',
        'brain_ids': ['1', '6', '7', '9'],  # 语法格式 + 代码质量与测试 + 架构与数据合规 + 专项引擎
        'weights': {'1': 0.25, '6': 0.25, '7': 0.25, '9': 0.25},
        'desc': '代码的骨架是否规范、整洁、符合标准',
    },
    {
        'key': 'quality',
        'name': '质量层',
        'subtitle': '代码血肉',
        'brain_ids': ['3', '4', '5'],  # AI语义 + 性能与可靠性 + 可观测性
        'weights': {'3': 0.4, '4': 0.3, '5': 0.3},
        'desc': '代码的逻辑是否健壮、高效、可靠',
    },
    {
        'key': 'security',
        'name': '防护层',
        'subtitle': '代码皮肤',
        'brain_ids': ['2', '8', '10'],  # 安全与依赖审计 + 业务安全 + 依赖安全SCA
        'weights': {'2': 0.4, '8': 0.35, '10': 0.25},
        'desc': '代码的安全防护是否到位，能否抵御攻击',
    },
]
TIERS_MAP = {t['key']: t for t in TIERS}

BRAINS_MAP = {b['id']: b for b in BRAINS}



# ==================== P0: 自定义阈值配置 ====================

DEFAULT_THRESHOLDS_WEB = {
    'code_quality': {
        'max_function_lines': 50,
        'max_file_lines': 500,
        'max_function_params': 5,
        'max_nesting_depth': 4,
        'max_class_methods': 20,
    },
    'complexity': {
        'max_cyclomatic_complexity': 10,
        'max_cognitive_complexity': 15,
    },
    'architecture': {
        'warn_file_lines': 300,
        'red_file_lines': 500,
        'warn_func_lines': 50,
        'red_func_lines': 75,
        'max_module_dependencies': 10,
        'max_import_depth': 3,
    },
    'naming': {
        'min_variable_length': 2,
        'max_variable_length': 40,
        'max_function_length': 40,
    },
}

ALLOWED_THRESHOLD_KEYS = {
    'code_quality': {'max_function_lines', 'max_file_lines', 'max_function_params', 'max_nesting_depth', 'max_class_methods'},
    'complexity': {'max_cyclomatic_complexity', 'max_cognitive_complexity'},
    'architecture': {'warn_file_lines', 'red_file_lines', 'warn_func_lines', 'red_func_lines', 'max_module_dependencies', 'max_import_depth'},
    'naming': {'min_variable_length', 'max_variable_length', 'max_function_length'},
}
