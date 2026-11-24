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


BULK_PREFIX = "SMTP_BULK_"


def _get_smtp_config(purpose="transactional"):
    """从环境变量读取 SMTP 配置。

    purpose 决定用哪一套凭据，两套必须物理分开：
      transactional —— 验证码、邀请、监控告警。丢了账号等于丢了找回密码的路。
      bulk          —— 群发（外联、召回）。这类邮件最容易被服务商判成骚扰，
                       一旦限流或封号，绝不能牵连事务邮件和告警通道。

    from_name 只影响收件人看到的发件人显示名（如「煋鉴 Xinpect」），
    留空则只显示邮箱地址。地址本身永远以 user 为准，不可伪装。
    """
    if purpose == "bulk":
        return {
            "host": os.environ.get(BULK_PREFIX + "HOST", ""),
            "port": int(os.environ.get(BULK_PREFIX + "PORT", "465") or 465),
            "user": os.environ.get(BULK_PREFIX + "USER", "").strip(),
            "password": os.environ.get(BULK_PREFIX + "PASSWORD", ""),
            "use_ssl": os.environ.get(BULK_PREFIX + "USE_SSL", "true").lower() == "true",
            "from_name": os.environ.get(BULK_PREFIX + "FROM_NAME", "").strip(),
        }
    return {
        "host": os.environ.get("SMTP_HOST", "smtp.163.com"),
        "port": int(os.environ.get("SMTP_PORT", "465")),
        "user": os.environ.get("SMTP_USER", ""),
        "password": os.environ.get("SMTP_PASSWORD", ""),
        "use_ssl": os.environ.get("SMTP_USE_SSL", "true").lower() == "true",
        "from_name": os.environ.get("SMTP_FROM_NAME", "").strip(),
    }


def _send_mail(to_email: str, subject: str, html_body: str,
               purpose: str = "transactional") -> bool:
    """SMTP 发送唯一出口。配置缺失或发送失败都不抛异常，返回 False。

    purpose="bulk" 时强制走独立的群发账号：拿告警账号发群发，服务商的
    限流是连坐的——那边先封群发，这边一起收不到监控告警。这条不做成
    「提醒」，做成直接拒发，因为出事的时候没有人会回来看日志。
    """
    cfg = _get_smtp_config(purpose)
    if not cfg["user"] or not cfg["password"]:
        if purpose == "bulk":
            logger.error("[邮件] 群发通道未配置（%sUSER/PASSWORD），拒绝发送："
                         "群发不许借用告警账号", BULK_PREFIX)
        else:
            logger.error("[邮件] SMTP未配置，跳过发送")
        return False
    if purpose == "bulk" and cfg["user"] == os.environ.get("SMTP_USER", "").strip():
        logger.error("[邮件] 群发通道与告警通道是同一个账号，拒绝发送"
                     "（群发被封会连带掐掉监控告警）")
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


def bulk_configured():
    """群发通道是否就绪。外联脚本发送前必须先问这一句，别等一封封失败才回来看日志。

    返回 (ok, 原因)。原因直接给人看，不写英文错误码。
    """
    cfg = _get_smtp_config("bulk")
    if not cfg["user"] or not cfg["password"]:
        return False, ("群发通道未配置：需要环境变量 %sHOST/USER/PASSWORD"
                       "（企业邮箱，与告警账号分开）" % BULK_PREFIX)
    alert = os.environ.get("SMTP_USER", "").strip()
    if alert and cfg["user"] == alert:
        return False, "群发通道与告警通道指向同一个账号，先换独立账号再发"
    return True, "ok"


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
