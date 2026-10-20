"""邮件发送模块 - 使用SMTP发送验证码等邮件"""
import os
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

from .constants import logger


def _get_smtp_config():
    """从环境变量读取SMTP配置"""
    return {
        "host": os.environ.get("SMTP_HOST", "smtp.163.com"),
        "port": int(os.environ.get("SMTP_PORT", "465")),
        "user": os.environ.get("SMTP_USER", ""),
        "password": os.environ.get("SMTP_PASSWORD", ""),
        "use_ssl": os.environ.get("SMTP_USE_SSL", "true").lower() == "true",
    }


def send_reset_code_email(to_email: str, code: str, expire_minutes: int = 15) -> bool:
    """发送密码重置验证码邮件"""
    cfg = _get_smtp_config()
    if not cfg["user"] or not cfg["password"]:
        logger.error("[邮件] SMTP未配置，跳过发送")
        return False

    subject = "煋鉴 - 密码重置验证码"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    html_body = (
        '<div style="font-family: Microsoft YaHei,Arial,sans-serif;max-width:520px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">'
        '<div style="background:linear-gradient(135deg,#FF6B35,#ff8c5a);padding:28px 32px;text-align:center;">'
        '<h1 style="color:#fff;margin:0;font-size:22px;font-weight:600;">煋鉴 Xinpect</h1>'
        '<p style="color:rgba(255,255,255,0.85);margin:6px 0 0;font-size:13px;">AI 代码质量审计平台</p>'
        '</div>'
        '<div style="padding:32px;">'
        '<p style="font-size:15px;color:#333;margin:0 0 20px;">您好，</p>'
        '<p style="font-size:15px;color:#333;margin:0 0 20px;">我们收到了您的密码重置请求。请使用以下验证码完成操作：</p>'
        '<div style="background:#f8f9fa;border:2px dashed #FF6B35;border-radius:8px;padding:20px;text-align:center;margin:24px 0;">'
        '<span style="font-size:32px;font-weight:700;color:#FF6B35;letter-spacing:8px;">{code}</span>'
        '</div>'
        '<p style="font-size:13px;color:#888;margin:0 0 16px;">⏰ 验证码 <strong>{expire_minutes} 分钟</strong>后失效 · 生成时间 {now_str}</p>'
        '<p style="font-size:13px;color:#888;margin:0;">如非本人操作，请忽略此邮件。</p>'
        '</div>'
        '<div style="background:#f8f9fa;padding:16px 32px;text-align:center;border-top:1px solid #eee;">'
        '<p style="font-size:12px;color:#aaa;margin:0;">煋鉴 Xinpect · xinpect.com</p>'
        '</div>'
        '</div>'
    ).format(code=code, expire_minutes=expire_minutes, now_str=now_str)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["user"]
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        if cfg["use_ssl"]:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(cfg["host"], cfg["port"], context=context, timeout=15) as server:
                server.login(cfg["user"], cfg["password"])
                server.sendmail(cfg["user"], [to_email], msg.as_string())
        else:
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as server:
                server.starttls(context=ssl.create_default_context())
                server.login(cfg["user"], cfg["password"])
                server.sendmail(cfg["user"], [to_email], msg.as_string())
        logger.info("[邮件] 验证码邮件已发送至 %s", to_email)
        return True
    except Exception as e:
        logger.error("[邮件] 发送失败 to=%s: %s", to_email, e)
        return False

def send_team_invitation_email(invitee_email, team_name, inviter_name, invite_link):
    """发送团队邀请邮件"""
    subject = f'【煋鉴】{inviter_name} 邀请您加入团队「{team_name}」'
    body = f'''您好！

{inviter_name} 邀请您加入煋鉴团队「{team_name}」。

点击以下链接接受邀请：
{invite_link}

此链接24小时内有效。

煋鉴团队
'''
    try:
        send_email(invitee_email, subject, body)
        return True
    except Exception as e:
        logger.error(f'发送团队邀请邮件失败: {e}')
        return False
