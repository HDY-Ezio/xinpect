#!/usr/bin/env python3
"""
煋鉴关键业务链路监控（服务器端独立版）
检查3条关键链路 + 前端错误聚合
异常时发送邮件告警，全部正常静默。
"""

import json
import os
import smtplib
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta
from email.mime.text import MIMEText

# 配置
DB_PATH = '/opt/xinpect-website/xinpect.db'
STATE_FILE = '/opt/xinpect-website/critical_path_state.json'
ADMIN_EMAIL = 'hdyabcd@163.com'
SMTP_SERVER = 'smtp.163.com'
SMTP_PORT = 465
SMTP_USER = 'hdyabcd@163.com'
SMTP_PASS = os.environ.get('SMTP_PASSWORD', '')

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {'last_check_time': '', 'last_alerts': {}}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def _log(msg):
    """所有日志都带时间戳。

    以前每行只有内容没有时间：2026-11-14 那条 11:30 的告警，事后想确认
    「到底几点响的、邮件几点发出去的」，只能翻系统日志拼。一行时间戳就够的事。
    """
    print('%s %s' % (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), msg), flush=True)


def send_alert(subject, body):
    """发送邮件告警"""
    try:
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['Subject'] = f'[煋鉴告警] {subject}'
        msg['From'] = SMTP_USER
        msg['To'] = ADMIN_EMAIL
        
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=30) as server:  # 2026-10-23 修复：加超时防SMTP挂死
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        _log(f'[ALERT] {subject}')
    except Exception as e:
        _log(f'[ERROR] 发送告警邮件失败: {e}')

def check_systemd_service(service_name):
    """检查 systemd 服务状态"""
    try:
        result = subprocess.run(
            ['systemctl', 'is-active', service_name],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip()
    except Exception:
        return 'unknown'

def check_port(port):
    """检查端口是否监听"""
    try:
        result = subprocess.run(
            ['ss', '-tlnp'],
            capture_output=True, text=True, timeout=5
        )
        return f':{port} ' in result.stdout
    except Exception:
        return False

def check_http(url, timeout=5):
    """检查 HTTP 端点"""
    try:
        result = subprocess.run(
            ['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', '--max-time', str(timeout), url],
            capture_output=True, text=True, timeout=timeout+2
        )
        return result.stdout.strip()
    except Exception:
        return '000'


# 官网健康检查的耐心（秒）。必须「健康接口自己的预算 + 余量」之后才放弃：
# 健康接口内部探引擎最多 1.2 秒，页面本身几十毫秒，10 秒足够拿到真实答案。
# 2026-11-14 11:30 与 11:45 两次 P0 误报就是耐心给少了：健康接口探引擎花 5 秒，
# 这里 curl 也只等 5 秒，两边同时到期 → 报「官网挂了 HTTP 000」，
# 而同一秒官网的新日志里每个页面都是 200。
WEBSITE_HEALTH_TIMEOUT = 10
WEBSITE_HEALTH_RETRY_TIMEOUT = 20


def check_http_detailed(url, first_timeout=WEBSITE_HEALTH_TIMEOUT,
                        retry_timeout=WEBSITE_HEALTH_RETRY_TIMEOUT):
    """探测端点，返回每次尝试的 {code, elapsed, body}；000 必须再探一次。

    000 不等于「网站挂了」——curl 超时、连不上，返回的都是 000。
    这两种情况只能靠再探一次分开：真挂了两枪都打不响，只是慢第二枪就过了。
    只探一次就把「忙」写成「死」，正是误报的来源。
    """
    attempts = []
    for budget in (first_timeout, retry_timeout):
        t0 = time.time()
        body, code = '', '000'
        try:
            r = subprocess.run(
                ['curl', '-s', '-w', '\n%{http_code}', '--max-time', str(budget), url],
                capture_output=True, text=True, timeout=budget + 2
            )
            raw = (r.stdout or '').rstrip('\n')
            body, _, tail = raw.rpartition('\n')
            code = tail.strip() or '000'
        except Exception:
            pass
        attempts.append({'code': code, 'elapsed': round(time.time() - t0, 2), 'body': body})
        if code != '000':
            break
    return attempts


def describe_health(attempts, label='官网'):
    """把探测结果翻译成一句能照着干活的话。"""
    last = attempts[-1]
    if last['code'] == '000':
        spent = ' / '.join('%ss' % a['elapsed'] for a in attempts)
        return '%s连续 %d 次打不通（各等 %s，不是慢，是没响应）' % (
            label, len(attempts), spent)
    detail = ''
    try:
        data = json.loads(last['body'])
        bits = []
        if data.get('status'):
            bits.append('status=%s' % data['status'])
        scanner = data.get('scanner') or {}
        if scanner.get('status'):
            bits.append('引擎=%s' % scanner['status'])
        bits.append('在途任务=%s' % data.get('active_scans', 0))
        detail = '（%s，耗时 %ss）' % ('，'.join(bits), last['elapsed'])
    except (ValueError, TypeError):
        pass
    return '%s HTTP %s%s' % (label, last['code'], detail)


def check_http_json(url, timeout=5):
    """检查 HTTP 端点并返回解析后的 JSON（异常返回 None）"""
    try:
        result = subprocess.run(
            ['curl', '-s', '--max-time', str(timeout), url],
            capture_output=True, text=True, timeout=timeout+2
        )
        return json.loads(result.stdout)
    except Exception:
        return None

def check_db_query(query, expected_value=None):
    """执行数据库查询"""
    try:
        db = sqlite3.connect(DB_PATH, timeout=5)
        cursor = db.execute(query)
        result = cursor.fetchone()
        db.close()
        if expected_value is not None:
            return result[0] == expected_value if result else False
        return result[0] if result else None
    except Exception as e:
        _log(f'[DB ERROR] {query[:50]}... : {e}')
        return None

def should_alert(alert_key, state):
    """检查是否应该告警（10分钟内去重）"""
    last_alerts = state.get('last_alerts', {})
    last_time = last_alerts.get(alert_key)
    if not last_time:
        return True
    try:
        last_dt = datetime.fromisoformat(last_time)
        return (datetime.now() - last_dt).total_seconds() > 600  # 10分钟
    except Exception:
        return True

QA_RESULT_FILE = '/opt/xinpect-website/tests/reports/last_result.json'
QA_RESULT_MAX_AGE = 8 * 3600


def check_selfcheck_result(path=QA_RESULT_FILE, now=None):
    """全站自检的最近结论。返回告警清单（空 = 正常）。

    为什么算「关键链路」：自检里挂的是付费履约、切片并发、续费累加、退款回写
    这些真会亏钱或坑客户的东西。红着没人看，等于没检查。
    """
    now = time.time() if now is None else now
    try:
        if not os.path.exists(path):
            return ['全站自检从没留下结论（last_result.json 不存在）']
        with open(path) as f:
            d = json.load(f)
        age = now - float(d.get('epoch') or os.path.getmtime(path))
        if age > QA_RESULT_MAX_AGE:
            return ['全站自检已 %.1f 小时没有新结论（应每 6 小时一次）' % (age / 3600)]
        if not d.get('ok'):
            bad = sorted(k for k, v in (d.get('rc') or {}).items() if v)
            return ['全站自检失败：%s' % ('、'.join(bad) + ' 段不通过' if bad else '原因未知')]
        return []
    except Exception as e:
        return ['全站自检结论读不出来（%s）' % str(e)[:60]]


COS_BACKUP_RECORD = '/opt/xinpect-website/tests/reports/last_cos_backup.json'
RESTORE_RECORD = '/opt/xinpect-website/tests/reports/last_restore_check.json'
COS_BACKUP_MAX_AGE = 26 * 3600
RESTORE_MAX_AGE = 8 * 24 * 3600


def check_offsite_backup(backup_record=COS_BACKUP_RECORD,
                         restore_record=RESTORE_RECORD, now=None):
    """云上那份备份还在不在、能不能还原。返回告警清单（空 = 正常）。

    这里只看本机记录，不发网络请求 —— 监控每 15 分钟一次，不该被外网抖动拖住。
    真的「云上还在不在」由 QA 守卫每天几次去问云（tests/test_offsite_backup.py）。
    """
    now = time.time() if now is None else now
    out = []

    try:
        if not os.path.exists(backup_record):
            out.append('云上备份从没成功过（没有上传记录）')
        else:
            with open(backup_record) as f:
                d = json.load(f)
            age = now - float(d.get('epoch') or 0)
            if age > COS_BACKUP_MAX_AGE:
                out.append('云上备份已 %.1f 小时没更新（应每天一次）' % (age / 3600))
            local = d.get('local_file') or ''
            if not local or not os.path.exists(local):
                out.append('云上备份对应的本地文件不见了: %s' % local)
            elif os.path.getsize(local) != d.get('size'):
                out.append('云上备份记录的大小与本地文件对不上')
    except Exception as e:
        out.append('云上备份记录读不出来（%s）' % str(e)[:60])

    try:
        if not os.path.exists(restore_record):
            out.append('云上备份还没做过恢复演练（无法证明能还原）')
        else:
            with open(restore_record) as f:
                d = json.load(f)
            age = now - float(d.get('epoch') or 0)
            if age > RESTORE_MAX_AGE:
                out.append('云上备份已 %.1f 天没做恢复演练（应每周一次）' % (age / 86400))
            elif not d.get('ok'):
                out.append('上次云上恢复演练没通过: %s' % '；'.join(d.get('detail') or [])[:120])
    except Exception as e:
        out.append('恢复演练记录读不出来（%s）' % str(e)[:60])

    return out


def main():
    state = load_state()
    alerts = []
    
    # 1. 扫描链路
    scanner_status = check_systemd_service('xinpect-scanner-green.service')
    port_8620_ok = check_port(8620)
    scanner_health = check_http('http://127.0.0.1:8620/health')
    scan_errors = check_db_query(
        "SELECT COUNT(*) FROM error_logs WHERE method='REPORT' AND error_type LIKE '%scan%' AND timestamp >= datetime('now', '-30 minutes')"
    ) or 0
    
    if scanner_status != 'active':
        alerts.append(f'扫描引擎服务异常: {scanner_status}')
    if not port_8620_ok:
        alerts.append('扫描引擎端口 8620 未监听')
    if scanner_health not in ['200', '000']:  # 000 表示没有该端点，不算异常
        alerts.append(f'扫描引擎健康检查失败: HTTP {scanner_health}')
    if scan_errors > 0:
        alerts.append(f'扫描相关错误: {scan_errors} 条（5分钟内）')
    
    # 2. 付费链路
    website_status = check_systemd_service('xinpect-website.service')
    website_attempts = check_http_detailed('http://127.0.0.1:8621/health')
    website_health = website_attempts[-1]['code']
    pay_errors = check_db_query(
        "SELECT COUNT(*) FROM error_logs WHERE method='REPORT' AND (error_type LIKE '%pay%' OR error_type LIKE '%credit%' OR endpoint LIKE '%pay%') AND timestamp >= datetime('now', '-30 minutes')"
    ) or 0
    
    if website_status != 'active':
        alerts.append(f'官网服务异常: {website_status}')
    if website_health != '200':
        alerts.append('官网健康检查失败: ' + describe_health(website_attempts))
    if pay_errors > 0:
        alerts.append(f'支付相关错误: {pay_errors} 条（5分钟内）')
    
    # 3. 积分链路
    credits_ok = check_db_query('SELECT 1 FROM user_credits LIMIT 1', 1)
    credit_errors = check_db_query(
        "SELECT COUNT(*) FROM error_logs WHERE method='REPORT' AND (error_type LIKE '%credit%' OR error_type LIKE '%transaction%') AND timestamp >= datetime('now', '-30 minutes')"
    ) or 0
    
    if not credits_ok:
        alerts.append('积分系统数据库异常')
    if credit_errors > 0:
        alerts.append(f'积分相关错误: {credit_errors} 条（5分钟内）')
    
    # 4. 前端错误聚合
    try:
        db = sqlite3.connect(DB_PATH, timeout=5)
        # click_no_response是启发式检测误报率高，阈值提高到5
        cursor = db.execute(
            """SELECT endpoint, error_type, COUNT(*) as cnt FROM error_logs 
               WHERE method='REPORT' AND timestamp >= datetime('now', '-30 minutes')
               GROUP BY endpoint, error_type
               HAVING (error_type = 'click_no_response' AND COUNT(*) >= 5)
                   OR (error_type != 'click_no_response' AND COUNT(*) >= 2)"""
        )
        frontend_errors = cursor.fetchall()
        db.close()
        
        for endpoint, error_type, count in frontend_errors:
            alerts.append(f'🔥 前端错误聚合: {endpoint} ({error_type}) x{count}')
    except Exception as e:
        _log(f'[ERROR] 查询前端错误聚合失败: {e}')
    
    # 5. 前端路由主动健康检查
    try:
        import urllib.request
        critical_routes = [
            ("/", "首页"),
            ("/pricing", "定价页"),
            ("/login", "登录页"),
        ]
        for path, name in critical_routes:
            try:
                req = urllib.request.Request(f"http://127.0.0.1:8621{path}", method="GET")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status != 200:
                        alerts.append(f"前端路由异常: {name}({path}) HTTP {resp.status}")
            except urllib.error.HTTPError as e:
                if e.code >= 500:
                    alerts.append(f"前端路由错误: {name}({path}) HTTP {e.code}")
            except Exception as e:
                alerts.append(f"前端路由不可达: {name}({path}) {str(e)[:60]}")
    except Exception as e:
        _log(f"[ERROR] 前端路由检查失败: {e}")
    
    # 6. 数据库完整性检查
    try:
        db = sqlite3.connect(DB_PATH, timeout=5)
        result = db.execute("PRAGMA integrity_check").fetchone()
        db.close()
        if result[0] != 'ok':
            alerts.append(f'⚠️ 数据库完整性异常: {result[0]}')
    except Exception as e:
        alerts.append(f'⚠️ 数据库连接失败: {str(e)[:80]}')
    
    # 7. 备份有效性检查（每天检查一次最新备份是否存在且非空）
    import glob as glob_mod
    try:
        backup_dir = '/opt/xinpect-website/backups/database'
        backups = sorted(glob_mod.glob(os.path.join(backup_dir, '*.db.gz')))
        if not backups:
            # 也检查直接sql文件
            backups = sorted(glob_mod.glob(os.path.join(backup_dir, '*.db')))
        if backups:
            latest = backups[-1]
            size = os.path.getsize(latest)
            if size < 1000:  # 小于1KB可能是空备份
                alerts.append(f'⚠️ 数据库备份异常: {os.path.basename(latest)} 仅{size}字节')
        else:
            alerts.append('⚠️ 未找到数据库备份文件')
    except Exception as e:
        _log(f'[WARN] 备份检查失败: {e}')
    
    # 8. 门房支付链路（独立于官网，此前监控盲区 → 支付断4天无人发现）
    menfang_status = check_systemd_service('xinpect-pay.service')
    menfang_port_ok = check_port(8765)
    menfang_health = check_http_json('http://127.0.0.1:8765/api/health')
    menfang_pay_health = check_http_json('http://127.0.0.1:8765/api/pay/health')

    if menfang_status != 'active':
        alerts.append(f'门房服务异常: {menfang_status}')
    if not menfang_port_ok:
        alerts.append('门房端口 8765 未监听')
    if menfang_health is None:
        alerts.append('门房健康检查不可达: /api/health')
    elif menfang_health.get('status') != 'ok':
        alerts.append(f"门房健康状态异常: {menfang_health.get('status')}")
    elif not menfang_health.get('wechat_pay_configured'):
        alerts.append('门房微信支付配置失效: wechat_pay_configured=false（私钥/证书异常）')
    if menfang_pay_health is None:
        alerts.append('门房支付模块不可达: /api/pay/health')
    elif menfang_pay_health.get('status') not in ('ok',):
        alerts.append(f"门房支付数据库异常: {menfang_pay_health.get('status')}")

    # 9. 全站自检的最近结论（自检红了没人看，等于没检查）
    alerts.extend(check_selfcheck_result())
    alerts.extend(check_offsite_backup())

    # 更新状态
    state['last_check_time'] = datetime.now().isoformat()
    
    if alerts:
        # 有异常，检查是否需要告警
        alert_keys = [a[:50] for a in alerts]
        new_alerts = [a for a, k in zip(alerts, alert_keys) if should_alert(k, state)]
        
        if new_alerts:
            # 更新告警时间戳
            for k in alert_keys:
                state['last_alerts'][k] = datetime.now().isoformat()
            
            # 发送告警邮件
            body = '煋鉴关键链路监控告警\n\n'
            body += '检查时间: ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + '\n\n'
            body += '异常项:\n'
            for i, alert in enumerate(alerts, 1):
                body += f'{i}. {alert}\n'
            body += '\n请立即检查并处理。\n'
            
            # 告警分级：服务不可用/端口/健康/数据库/支付/积分=P0；前端路由/备份=P2；其余=P1
            _allt = ' '.join(alerts)
            if any(k in _allt for k in ['服务异常','端口','健康检查失败','数据库','支付','积分','扫描引擎','门房']):
                _level = 'P0'
            elif any(k in _allt for k in ['前端','路由','备份']):
                _level = 'P2'
            else:
                _level = 'P1'
            send_alert(f'[{_level}] 发现 {len(alerts)} 项异常（{"P0=5分钟内响应" if _level=="P0" else ("P2=工作时间处理" if _level=="P2" else "P1=1小时内响应")}）', body)
        else:
            _log('[OK] 有异常但10分钟内已告警过，跳过')
    else:
        _log('[OK] ALL CLEAR - 所有链路正常')
    
    save_state(state)

if __name__ == '__main__':
    main()
