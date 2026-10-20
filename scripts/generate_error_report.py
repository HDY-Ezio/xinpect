#!/usr/bin/env python3
"""生成每日错误报告 - 煋鉴 Xinpect 故障巡检系统
包含：
1. Flask API 层的 HTTP 错误和异常
2. 所有 systemd 服务的 journal 错误
"""

import sqlite3
import re
import json
from datetime import datetime, timedelta
from pathlib import Path


# ===== 安全扫描器探测模式识别 =====
SCANNER_PATTERNS = [
    r'\.env[\.\w]*$',
    r'phpinfo',
    r'\.php$',
    r'/\.git/',
    r'credentials\.json$',
    r'service-account\.json$',
    r'firebase.*\.json$',
    r'gcp.*\.json$',
    r'google-.*\.json$',
    r'/key\.json$',
    r'/keyfile\.json$',
    r'/sa\.json$',
    r'application_default_credentials',
    # WordPress全面探测（含/wp/, /wordpress/, /wp-json/全部子路径）
    r'^/wp(/|$)',
    r'^/wordpress(/|$)',
    r'/wp-json/',  # 匹配任意位置的/wp-json/（含/blog/wp-json/等）
    r'/wp/v2/',  # WordPress REST API v2（含/blog/wp/v2/等）
    r'/blog/feed/',  # WordPress RSS feed
    r'/blog/wp-admin/',  # WordPress后台（/blog/前缀）
    r'/blog/wp-login',  # WordPress登录（/blog/前缀）
    r'/blog/xmlrpc',  # WordPress XML-RPC（/blog/前缀）
    r'^/blog/$',  # WordPress博客根路径探测
    r'/wp-admin',  # WordPress后台探测（含无尾斜杠）
    r'/phpmyadmin',  # phpMyAdmin探测
    r'/dump\.sql',  # 数据库dump探测
    r'/wp-login',
    r'/administrator/',
    r'/xmlrpc\.php',
    # Laravel/PHP框架探测
    r'/livewire/',
    r'/_profiler/',
    r'/_environment',
    r'/server-status',
    r'/server-info',
    # 常见CMS扫描
    r'/joomla',
    r'/drupal',
    r'/magento',
    r'^/(signin|dashboard)(/|$)',
    r'^/api/auth/signin',
    r'\.well-known/security\.txt',
    # === 2026-10-10 扩充：覆盖近期扫描器新路径 ===
    # 云凭证/配置文件探测
    r'/\.aws/',
    r'/\.docker/',
    r'/\.kube/',
    r'/\.npmrc',
    r'/\.pypirc',
    r'/\.htaccess',
    r'/\.htpasswd',
    r'/\.DS_Store',
    r'/\.env\.local',
    r'/\.env\.backup',
    r'/\.gitlab-ci',
    r'/\.circleci/',
    # 配置文件探测
    r'/config\.(json|toml|yml|yaml)$',
    r'/credentials\.(yml|yaml|json)$',
    r'/secrets\.(properties|yml|yaml|json)$',
    # 数据库备份探测
    r'\.(sql|sql\.bak)(\.gz|\.zip|\.tar)?$',
    r'/(db|mysql|site|backup|dump|database)\.(sql|bak|gz|zip|tar)$',
    # Docker/CI 探测
    r'/docker-compose(\.ya?ml)?$',
    r'/Dockerfile',
    # 框架/后台探测
    r'/actuator/',
    r'/console',
    r'/manager/',
    r'/remote/logincheck',
    r'/developmentserver',
    # .git 深度探测
    r'/\.git/(HEAD|config|objects|refs)',
    # 隐藏文件/目录探测
    r'/\.amplifyrc', r'/\.s3cfg', r'/\.github/', r'/\.gitmodules',
    r'/\.git-credentials',
    # JS/JSON 配置文件探测
    r'/(appsettings|app\.config|appsettings\.Development|appsettings\.Production)\.(json|js)$',
    r'/(config|env|env-config|env\.txt|aws-exports|runtime-config|index)\.js$',
    r'/(settings|auth|composer)\.json$',
    r'/config/(aws\.yml|config\.js)$',
    r'/vendor/composer/',
    r'/security\.txt$',
    r'/aws-exports\.js$',
    # 根目录敏感路径
    r'^/(phpinfo|info|env|env\.txt)$',
    r'/wp-content/',
]

# 已知扫描器User-Agent关键词
SCANNER_UA_PATTERNS = [
    'WordPress/',  # WordPress自身UA（cron/pingback探测）
    'Palo Alto', 'Cortex Xpanse',
    'Nmap', 'Nikto', 'Acunetix', 'Nessus', 'BurpSuite',
    'ZmEu', 'masscan', 'nuclei',
]

def is_scanner_probe(endpoint, user_agent=None, ip_address=None):
    """判断是否为安全扫描器探测行为"""
    if not endpoint:
        return False
    # 1. 已知扫描器模式匹配
    for pattern in SCANNER_PATTERNS:
        if re.search(pattern, endpoint, re.IGNORECASE):
            return True
    # 2. 检查User-Agent是否为已知扫描器
    if user_agent:
        ua_lower = user_agent.lower()
        for ua_pattern in SCANNER_UA_PATTERNS:
            if ua_pattern.lower() in ua_lower:
                return True
    # 3. 兜底规则：非API路径 + 代理来源 = 扫描器探测
    # 正常业务请求都是 /api/ 开头，其他根路径的 GET 请求几乎全是扫描器
    if endpoint and not endpoint.startswith('/api/') and ip_address == '127.0.0.1':
        # 排除合法的非API路径（如 /health, /static/ 等）
        legitimate_paths = ['/health', '/static/', '/favicon', '/robots.txt', '/sitemap']
        if not any(endpoint.startswith(lp) for lp in legitimate_paths):
            return True
    return False

DB_PATH = "/opt/xinpect-website/xinpect.db"
REPORT_DIR = Path("/opt/xinpect-website/reports")


def generate_daily_report(target_date=None):
    """生成指定日期的错误报告，默认昨天"""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    if target_date is None:
        yesterday = datetime.now() - timedelta(days=1)
    else:
        yesterday = datetime.strptime(target_date, "%Y-%m-%d")

    since = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
    until = yesterday.replace(hour=23, minute=59, second=59)

    since_str = since.strftime("%Y-%m-%d %H:%M:%S")
    until_str = until.strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # ===== 全局统计 =====
    total = conn.execute(
        "SELECT COUNT(*) FROM error_logs WHERE timestamp BETWEEN ? AND ?",
        (since_str, until_str),
    ).fetchone()[0]

    # 扫描器探测 vs 真实错误分类
    all_rows_for_class = conn.execute(
        "SELECT endpoint, user_agent, ip_address FROM error_logs WHERE timestamp BETWEEN ? AND ?",
        (since_str, until_str),
    ).fetchall()
    scanner_count = sum(1 for r in all_rows_for_class if is_scanner_probe(r[0], r[1], r[2] if len(r) > 2 else None))
    real_count = total - scanner_count

    # 区分 API 错误 vs 系统服务错误
    api_total = conn.execute(
        """SELECT COUNT(*) FROM error_logs 
           WHERE timestamp BETWEEN ? AND ? AND error_type NOT LIKE 'JOURNAL_%'""",
        (since_str, until_str),
    ).fetchone()[0]

    journal_total = conn.execute(
        """SELECT COUNT(*) FROM error_logs 
           WHERE timestamp BETWEEN ? AND ? AND error_type LIKE 'JOURNAL_%'""",
        (since_str, until_str),
    ).fetchone()[0]

    # 按类型分组
    by_type = conn.execute(
        """SELECT error_type, COUNT(*) as count,
               GROUP_CONCAT(DISTINCT endpoint) as endpoints
        FROM error_logs 
        WHERE timestamp BETWEEN ? AND ?
        GROUP BY error_type
        ORDER BY count DESC""",
        (since_str, until_str),
    ).fetchall()

    # 按端点/服务分组
    by_endpoint = conn.execute(
        """SELECT endpoint, method, COUNT(*) as count,
               GROUP_CONCAT(DISTINCT error_type) as error_types
        FROM error_logs 
        WHERE timestamp BETWEEN ? AND ?
        GROUP BY endpoint, method
        ORDER BY count DESC
        LIMIT 20""",
        (since_str, until_str),
    ).fetchall()

    # 高频错误（出现>=3次）
    frequent = [row for row in by_type if row["count"] >= 3]

    # 未解决的错误（排除扫描器）
    all_unresolved_raw = conn.execute(
        """SELECT * FROM error_logs 
        WHERE resolved = 0 AND timestamp BETWEEN ? AND ?
        ORDER BY timestamp DESC""",
        (since_str, until_str),
    ).fetchall()
    unresolved = [r for r in all_unresolved_raw if not is_scanner_probe(r["endpoint"], r["user_agent"], r["ip_address"])]

    # 已解决的错误
    resolved = conn.execute(
        """SELECT COUNT(*) FROM error_logs 
        WHERE resolved = 1 AND timestamp BETWEEN ? AND ?""",
        (since_str, until_str),
    ).fetchone()[0]

    # ===== 系统服务错误专项统计 =====
    journal_by_service = conn.execute(
        """SELECT endpoint as service, COUNT(*) as count,
               GROUP_CONCAT(DISTINCT error_type) as error_types
        FROM error_logs 
        WHERE timestamp BETWEEN ? AND ? AND method = 'JOURNAL'
        GROUP BY endpoint
        ORDER BY count DESC""",
        (since_str, until_str),
    ).fetchall()

    # ===== 按小时分布 =====
    hourly = conn.execute(
        """SELECT substr(timestamp, 1, 13) as hour, COUNT(*) as count
        FROM error_logs 
        WHERE timestamp BETWEEN ? AND ?
        GROUP BY hour
        ORDER BY hour""",
        (since_str, until_str),
    ).fetchall()

    # IP维度统计
    by_ip = conn.execute(
        """SELECT ip_address, COUNT(*) as count
        FROM error_logs 
        WHERE timestamp BETWEEN ? AND ? AND ip_address IS NOT NULL
        GROUP BY ip_address
        ORDER BY count DESC
        LIMIT 10""",
        (since_str, until_str),
    ).fetchall()

    # 预计算扫描器分类（在关闭连接前）
    scanner_categories = {}
    if scanner_count > 0:
        all_scanner_eps = conn.execute(
            "SELECT endpoint, user_agent, ip_address FROM error_logs WHERE timestamp BETWEEN ? AND ?",
            (since_str, until_str),
        ).fetchall()
        for r in all_scanner_eps:
            ep = r[0] or ''
            ua = r[1] or ''
            ip = r[2] if len(r) > 2 else None
            if is_scanner_probe(ep, ua, ip):
                if '.env' in ep:
                    cat = '.env文件探测'
                elif 'phpinfo' in ep or ep.endswith('.php'):
                    cat = 'PHP探针'
                elif '.git' in ep:
                    cat = 'Git配置探测'
                elif any(kw in ep.lower() for kw in ['credential', 'firebase', 'gcp', 'google-key', 'key.json', 'keyfile', 'sa.json', 'service-account']):
                    cat = '云凭证探测'
                elif any(kw in ep.lower() for kw in ['wp-admin', 'wp-login', 'administrator', '/wp/', '/wp-json', '/wordpress/']):
                    cat = 'WordPress扫描探测'
                elif 'palo alto' in ua.lower() or 'cortex' in ua.lower():
                    cat = '企业扫描器探测'
                else:
                    cat = '其他探测'
                scanner_categories[cat] = scanner_categories.get(cat, 0) + 1

    conn.close()

    # ===== 生成报告 =====
    L = []  # report lines
    L.append(f"# 每日错误报告")
    L.append(f"**日期**: {yesterday.strftime('%Y-%m-%d')}")
    L.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    L.append("")

    # 总览
    L.append("## 📊 总览")
    L.append(f"- **总错误数**: {total}")
    L.append(f"  - 🔴 真实API错误: {real_count}")
    L.append(f"  - 🟡 安全扫描器探测: {scanner_count}")
    L.append(f"  - 系统服务错误 (journal): {journal_total}")
    if scanner_count > 0:
        L.append("")
        L.append(f"> 💡 安全扫描器探测（{scanner_count}条）已从高频错误分析中排除，这些是自动化漏洞扫描行为，404为正确响应。")
    L.append(f"- **错误类型数**: {len(by_type)}")
    L.append(f"- **高频错误（>=3次）**: {len(frequent)}")
    L.append(f"- **未解决**: {len(unresolved)} / **已解决**: {resolved}")
    L.append("")

    # 错误类型分布
    L.append("## 📋 错误类型分布")
    L.append("| 类型 | 次数 | 涉及端点/服务 |")
    L.append("|------|------|---------------|")
    for row in by_type:
        endpoints = row["endpoints"] or "N/A"
        # 简化显示
        if len(endpoints) > 80:
            endpoints = endpoints[:77] + "..."
        L.append(f"| {row['error_type']} | {row['count']} | {endpoints} |")
    L.append("")

    # 高频端点/服务
    L.append("## 🔥 高频出错端点/服务 TOP 10")
    L.append("| 端点/服务 | 方法 | 次数 | 错误类型 |")
    L.append("|-----------|------|------|----------|")
    for row in by_endpoint:
        L.append(f"| {row['endpoint']} | {row['method']} | {row['count']} | {row['error_types']} |")
    L.append("")

    # 按小时分布
    if hourly:
        L.append("## 📈 错误时间分布（按小时）")
        L.append("| 时间 | 错误数 |")
        L.append("|------|--------|")
        for row in hourly:
            L.append(f"| {row['hour']}:00 | {row['count']} |")
        L.append("")

    # ===== 系统服务错误专项 =====
    if journal_by_service:
        L.append("## 🖥️ 系统服务错误汇总（来自 systemd journal）")
        L.append("| 服务 | 错误次数 | 错误类型 |")
        L.append("|------|----------|----------|")
        for row in journal_by_service:
            svc_name = row["service"].lstrip("/")
            L.append(f"| {svc_name} | {row['count']} | {row['error_types']} |")
        L.append("")

    # 高频错误
    L.append("## 🚨 高频错误（需要优先修复）")
    if frequent:
        for row in frequent:
            L.append(f"")
            L.append(f"### {row['error_type']}（{row['count']}次）")
            L.append(f"涉及端点/服务：{row['endpoints']}")
    else:
        L.append("无高频错误 ✅")
    L.append("")

    # IP维度分析（仅API错误）
    api_ips = [row for row in by_ip if row["ip_address"]]
    if api_ips:
        L.append("## 🌐 错误来源 IP TOP 10")
        L.append("| IP地址 | 错误次数 |")
        L.append("|--------|----------|")
        for row in api_ips:
            L.append(f"| {row['ip_address']} | {row['count']} |")
        L.append("")

    # 未解决错误详情
    L.append(f"## ❌ 未解决错误详情（共{len(unresolved)}条）")
    if unresolved:
        for i, row in enumerate(unresolved[:20]):
            svc = row["endpoint"]
            method = row["method"]
            L.append(f"")
            L.append(f"### #{row['id']} {row['error_type']} - {svc}")
            L.append(f"- **时间**: {row['timestamp']}")
            L.append(f"- **方式**: {method}")
            L.append(f"- **状态码**: {row['response_status']}")
            L.append(f"- **消息**: {(row['error_message'] or '')[:300]}")
            if row["stack_trace"]:
                stack_lines = (row["stack_trace"] or "").strip().split("\n")
                tail = stack_lines[-5:] if len(stack_lines) > 5 else stack_lines
                L.append(f"- **堆栈摘要**:")
                L.append("```")
                for sl in tail:
                    L.append(sl[:250])
                L.append("```")
            if row["ip_address"]:
                L.append(f"- **IP**: {row['ip_address']}")
            if row["user_agent"]:
                L.append(f"- **来源**: {row['user_agent'][:100]}")

        if len(unresolved) > 20:
            L.append(f"\n...还有 {len(unresolved) - 20} 条未解决错误")
    else:
        L.append("无未解决错误 ✅")

    # 扫描器探测摘要
    if scanner_count > 0:
        L.append("")
        L.append(f"## 🛡️ 安全扫描器探测摘要（已排除，共{scanner_count}条）")
        L.append("这些是自动化漏洞扫描工具的探测行为，非真实API错误。")
        L.append("")
        L.append("| 探测类型 | 次数 |")
        L.append("|----------|------|")
        for cat, cnt in sorted(scanner_categories.items(), key=lambda x: -x[1]):
            L.append(f"| {cat} | {cnt} |")
    report_text = "\n".join(L) + "\n"

    # 保存报告
    report_file = REPORT_DIR / f"error_report_{yesterday.strftime('%Y%m%d')}.md"
    report_file.write_text(report_text, encoding="utf-8")

    # 输出摘要
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 报告已生成：{report_file}")
    print(f"  总错误: {total} (真实: {real_count}, 扫描器: {scanner_count}, 系统服务: {journal_total})")
    print(f"  错误类型: {len(by_type)}")
    print(f"  高频错误: {len(frequent)}")
    print(f"  未解决: {len(unresolved)}")

    return str(report_file), total, len(frequent)


if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else None
    generate_daily_report(target)
