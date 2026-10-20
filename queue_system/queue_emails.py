# -*- coding: utf-8 -*-
"""
煋鉴排队系统 - 邮件通知模块
三个关键节点：排队开始、即将开始、扫描完成
"""

import os
import smtplib
import ssl
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

logger = logging.getLogger("xinpect-queue-email")


def _get_smtp_config():
    """从环境变量读取SMTP配置"""
    return {
        "host": os.environ.get("SMTP_HOST", "smtp.163.com"),
        "port": int(os.environ.get("SMTP_PORT", "465")),
        "user": os.environ.get("SMTP_USER", ""),
        "password": os.environ.get("SMTP_PASSWORD", ""),
        "use_ssl": os.environ.get("SMTP_USE_SSL", "true").lower() == "true",
    }


def _send_email(to_email: str, subject: str, html_body: str) -> bool:
    """发送邮件底层函数"""
    cfg = _get_smtp_config()
    if not cfg["user"] or not cfg["password"]:
        logger.error("[排队邮件] SMTP未配置，跳过")
        return False
    if not to_email or "@" not in to_email:
        logger.warning(f"[排队邮件] 无效邮箱: {to_email}")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["user"]
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        if cfg["use_ssl"]:
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(cfg["host"], cfg["port"], context=ctx, timeout=15) as s:
                s.login(cfg["user"], cfg["password"])
                s.sendmail(cfg["user"], [to_email], msg.as_string())
        else:
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as s:
                s.starttls(context=ssl.create_default_context())
                s.login(cfg["user"], cfg["password"])
                s.sendmail(cfg["user"], [to_email], msg.as_string())
        logger.info(f"[排队邮件] 已发送至 {to_email}: {subject}")
        return True
    except Exception as e:
        logger.error(f"[排队邮件] 发送失败 to={to_email}: {e}")
        return False


def _wrap_html(title: str, content: str, color: str = "#FF6B35") -> str:
    """统一邮件模板"""
    return f'''
    <div style="font-family:'Microsoft YaHei',Arial,sans-serif;max-width:520px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">
        <div style="background:linear-gradient(135deg,{color},{color}cc);padding:28px 32px;text-align:center;">
            <h1 style="color:#fff;margin:0;font-size:22px;font-weight:600;">煋鉴 Xinpect</h1>
            <p style="color:rgba(255,255,255,0.85);margin:6px 0 0;font-size:13px;">{title}</p>
        </div>
        <div style="padding:32px;">
            {content}
        </div>
        <div style="background:#f8f9fa;padding:16px 32px;text-align:center;border-top:1px solid #eee;">
            <p style="font-size:12px;color:#aaa;margin:0;">煋鉴 Xinpect · AI代码质量审计平台</p>
        </div>
    </div>
    '''


def send_queue_enter_email(to_email: str, project_name: str, position: int, wait_seconds: int) -> bool:
    """排队开始通知"""
    wait_min = max(1, wait_seconds // 60)
    content = f'''
        <p style="font-size:15px;color:#333;margin:0 0 20px;">您好，</p>
        <p style="font-size:15px;color:#333;margin:0 0 20px;">您的项目 <strong>{project_name}</strong> 已进入扫描排队队列。</p>
        <div style="background:#f8f9fa;border:2px dashed #FF6B35;border-radius:8px;padding:20px;text-align:center;margin:24px 0;">
            <p style="margin:0 0 8px;font-size:14px;color:#666;">当前排队位置</p>
            <span style="font-size:36px;font-weight:700;color:#FF6B35;">第 {position} 位</span>
            <p style="margin:12px 0 0;font-size:14px;color:#666;">预计等待约 <strong>{wait_min} 分钟</strong></p>
        </div>
        <p style="font-size:13px;color:#888;margin:0;">排队期间您可以关闭页面，扫描完成后我们会通过邮件通知您。</p>
    '''
    return _send_email(to_email, f"煋鉴 - 您的扫描任务排队中（第{position}位）", _wrap_html("扫描排队通知", content))


def send_queue_almost_email(to_email: str, project_name: str, position: int) -> bool:
    """即将开始通知（前面只剩1-2人时）"""
    content = f'''
        <p style="font-size:15px;color:#333;margin:0 0 20px;">您好，</p>
        <p style="font-size:15px;color:#333;margin:0 0 20px;">您的项目 <strong>{project_name}</strong> 即将开始扫描！</p>
        <div style="background:#fff8f0;border:2px solid #FF6B35;border-radius:8px;padding:20px;text-align:center;margin:24px 0;">
            <span style="font-size:28px;">🚀</span>
            <p style="font-size:16px;color:#FF6B35;font-weight:600;margin:8px 0 0;">马上开始</p>
            <p style="font-size:13px;color:#888;margin:4px 0 0;">您前面还有 {position} 个任务</p>
        </div>
        <p style="font-size:13px;color:#888;margin:0;">扫描完成后您将收到结果通知邮件。</p>
    '''
    return _send_email(to_email, f"煋鉴 - 扫描即将开始", _wrap_html("即将开始扫描", content, "#e85d2a"))


def send_scan_complete_email(to_email: str, project_name: str, task_id: str, success: bool, issue_count: int = 0) -> bool:
    """扫描完成通知"""
    if success:
        color = "#4CAF50"
        icon = "✅"
        status_text = "扫描完成"
        detail = f'共发现 <strong style="color:#FF6B35;font-size:20px;">{issue_count}</strong> 个问题'
    else:
        color = "#f44336"
        icon = "❌"
        status_text = "扫描失败"
        detail = "扫描过程中遇到错误，请重新提交"

    content = f'''
        <p style="font-size:15px;color:#333;margin:0 0 20px;">您好，</p>
        <p style="font-size:15px;color:#333;margin:0 0 20px;">您的项目 <strong>{project_name}</strong> {status_text}。</p>
        <div style="background:#f8f9fa;border-radius:8px;padding:24px;text-align:center;margin:24px 0;">
            <span style="font-size:36px;">{icon}</span>
            <p style="font-size:18px;color:{color};font-weight:600;margin:8px 0;">{status_text}</p>
            <p style="font-size:14px;color:#666;margin:4px 0 0;">{detail}</p>
        </div>
        <div style="text-align:center;margin:20px 0;">
            <a href="/report/{task_id}" style="display:inline-block;background:#FF6B35;color:#fff;padding:12px 32px;border-radius:6px;text-decoration:none;font-size:14px;font-weight:500;">查看完整报告</a>
        </div>
    '''
    return _send_email(to_email, f"煋鉴 - {project_name} {status_text}", _wrap_html(status_text, content, color))
