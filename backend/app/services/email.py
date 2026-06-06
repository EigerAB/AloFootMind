import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings


def _send_email(to: str, subject: str, html: str, text: str) -> str | None:
    """Send an email via SMTP (Gmail/163/etc)."""
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        print(f"[EMAIL] To: {to}\nSubject: {subject}\n\n{text}")
        return "dev-email-id"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.MAIL_FROM
    msg["To"] = to
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        if settings.SMTP_PORT == 465:
            # SSL direct (e.g. 163)
            with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT) as server:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.send_message(msg)
        else:
            # STARTTLS (e.g. Gmail on 587)
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
                server.starttls()
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.send_message(msg)
        return "sent"
    except Exception as e:
        print(f"[EMAIL ERROR] Failed to send email to {to}: {e}")
        return None


def send_verification_code(email: str, code: str, lang: str = "zh") -> str | None:
    """Send email verification code. Falls back to console output for development."""
    if lang == "zh":
        subject = "AloFootMind 邮箱验证码"
        text = f"您的验证码是：{code}\n5 分钟内有效，请勿泄露给他人。"
        html = f"""
        <div style="font-family: sans-serif; padding: 20px;">
            <h2>AloFootMind 邮箱验证</h2>
            <p>您的验证码是：</p>
            <h1 style="letter-spacing: 4px; color: #16a34a;">{code}</h1>
            <p>5 分钟内有效，请勿泄露给他人。</p>
        </div>
        """
    else:
        subject = "AloFootMind Verification Code"
        text = f"Your code is: {code}\nValid for 5 minutes. Do not share it."
        html = f"""
        <div style="font-family: sans-serif; padding: 20px;">
            <h2>AloFootMind Email Verification</h2>
            <p>Your verification code:</p>
            <h1 style="letter-spacing: 4px; color: #16a34a;">{code}</h1>
            <p>Valid for 5 minutes. Do not share it.</p>
        </div>
        """
    result = _send_email(email, subject, html, text)
    if result is None:
        print(f"[DEV] Verification code for {email}: {code}")
    return result


def send_password_reset_code(email: str, code: str, lang: str = "zh") -> str | None:
    """Send password reset code. Falls back to console output for development."""
    if lang == "zh":
        subject = "AloFootMind 密码重置验证码"
        text = f"您的密码重置验证码是：{code}\n1 小时内有效。"
        html = f"""
        <div style="font-family: sans-serif; padding: 20px;">
            <h2>AloFootMind 密码重置</h2>
            <p>您的密码重置验证码是：</p>
            <h1 style="letter-spacing: 4px; color: #16a34a;">{code}</h1>
            <p>1 小时内有效。</p>
        </div>
        """
    else:
        subject = "AloFootMind Password Reset"
        text = f"Your password reset code is: {code}\nValid for 1 hour."
        html = f"""
        <div style="font-family: sans-serif; padding: 20px;">
            <h2>AloFootMind Password Reset</h2>
            <p>Your password reset code:</p>
            <h1 style="letter-spacing: 4px; color: #16a34a;">{code}</h1>
            <p>Valid for 1 hour.</p>
        </div>
        """
    result = _send_email(email, subject, html, text)
    if result is None:
        print(f"[DEV] Password reset code for {email}: {code}")
    return result
