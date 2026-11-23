"""邮件发送模块 - 使用 SMTP 发送验证码、团队邀请等邮件。

SMTP 发送只有一个出口 _send_mail()：业务函数只负责写信件内容，
不再各自调用一个不存在的发信函数。签名以 modules/team.py 的真实调用为准。
"""
import os
import smtplib
import ssl
import html as _html
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from datetime import datetime

from .constants import logger, SMTP_TIMEOUT_SECONDS


def _get_smtp_config():
    """从环境变量读取SMTP配置

    from_name 只影响收件人看到的发件人显示名（如「煋鉴 Xinpect」），
    留空则只显示邮箱地址。地址本身永远以 user 为准，不可伪装。
    """
    return {
        "host": os.environ.get("SMTP_HOST", "smtp.163.com"),
        "port": int(os.environ.get("SMTP_PORT", "465")),
        "user": os.environ.get("SMTP_USER", ""),
        "password": os.environ.get("SMTP_PASSWORD", ""),
        "use_ssl": os.environ.get("SMTP_USE_SSL", "true").lower() == "true",
        "from_name": os.environ.get("SMTP_FROM_NAME", "").strip(),
    }


def _send_mail(to_email: str, subject: str, html_body: str) -> bool:
    """SMTP 发送唯一出口。配置缺失或发送失败都不抛异常，返回 False。"""
    cfg = _get_smtp_config()
    if not cfg["user"] or not cfg["password"]:
        logger.error("[邮件] SMTP未配置，跳过发送")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = (formataddr((cfg["from_name"], cfg["user"]))
                    if cfg.get("from_name") else cfg["user"])
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        if cfg["use_ssl"]:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(cfg["host"], cfg["port"], context=context, timeout=SMTP_TIMEOUT_SECONDS) as server:
                server.login(cfg["user"], cfg["password"])
                server.sendmail(cfg["user"], [to_email], msg.as_string())
        else:
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=SMTP_TIMEOUT_SECONDS) as server:
                server.starttls(context=ssl.create_default_context())
                server.login(cfg["user"], cfg["password"])
                server.sendmail(cfg["user"], [to_email], msg.as_string())
        logger.info("[邮件] 已发送至 %s: %s", to_email, subject)
        return True
    except Exception as e:
        logger.exception("[邮件] 发送失败 to=%s: %s", to_email, e)
        return False


def send_reset_code_email(to_email: str, code: str, expire_minutes: int = 15) -> bool:
    """发送密码重置验证码邮件"""
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
        '<p style="font-size:13px;color:#888;margin:0 0 16px;">验证码 <strong>{expire_minutes} 分钟</strong>后失效 · 生成时间 {now_str}</p>'
        '<p style="font-size:13px;color:#888;margin:0;">如非本人操作，请忽略此邮件。</p>'
        '</div>'
        '<div style="background:#f8f9fa;padding:16px 32px;text-align:center;border-top:1px solid #eee;">'
        '<p style="font-size:12px;color:#aaa;margin:0;">煋鉴 Xinpect · xinpect.com</p>'
        '</div>'
        '</div>'
    ).format(code=_html.escape(str(code)), expire_minutes=expire_minutes, now_str=now_str)
    return _send_mail(to_email, subject, html_body)


def send_team_invitation_email(to_email, team_name, inviter_email, invite_url, expire_days=7):
    """发送团队邀请邮件。参数名与 modules/team.py 的真实调用保持一致。"""
    subject = '【煋鉴】%s 邀请您加入团队「%s」' % (inviter_email, team_name)
    html_body = (
        '<div style="font-family: Microsoft YaHei,Arial,sans-serif;max-width:520px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">'
        '<div style="background:linear-gradient(135deg,#FF6B35,#ff8c5a);padding:28px 32px;text-align:center;">'
        '<h1 style="color:#fff;margin:0;font-size:22px;font-weight:600;">煋鉴 Xinpect</h1>'
        '<p style="color:rgba(255,255,255,0.85);margin:6px 0 0;font-size:13px;">AI 代码质量审计平台</p>'
        '</div>'
        '<div style="padding:32px;">'
        '<p style="font-size:15px;color:#333;margin:0 0 20px;">您好，</p>'
        '<p style="font-size:15px;color:#333;margin:0 0 20px;">{inviter} 邀请您加入煋鉴团队「{team}」。</p>'
        '<p style="font-size:15px;color:#333;margin:0 0 12px;">点击以下链接接受邀请：</p>'
        '<p style="font-size:14px;margin:0 0 20px;word-break:break-all;"><a href="{url}">{url}</a></p>'
        '<p style="font-size:13px;color:#888;margin:0;">此链接 {days} 天内有效。如非本人操作，请忽略此邮件。</p>'
        '</div>'
        '<div style="background:#f8f9fa;padding:16px 32px;text-align:center;border-top:1px solid #eee;">'
        '<p style="font-size:12px;color:#aaa;margin:0;">煋鉴 Xinpect · xinpect.com</p>'
        '</div>'
        '</div>'
    ).format(
        inviter=_html.escape(str(inviter_email)),
        team=_html.escape(str(team_name)),
        url=_html.escape(str(invite_url)),
        days=expire_days,
    )
    return _send_mail(to_email, subject, html_body)
