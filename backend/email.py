import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

SMTP_HOST     = os.environ.get("SMTP_HOST", "")
SMTP_PORT     = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER     = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
EMAIL_FROM    = os.environ.get("EMAIL_FROM", SMTP_USER)
FRONTEND_URL  = os.environ.get("FRONTEND_URL", "http://localhost:3000")


def email_configured() -> bool:
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD)


def send_password_reset(to_email: str, token: str) -> None:
    if not email_configured():
        # Dev fallback — print to console so dev can test without SMTP
        print(f"[DEV] Password reset link: {FRONTEND_URL}/reset-password?token={token}")
        return

    reset_url = f"{FRONTEND_URL}/reset-password?token={token}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Reset your Codgen password"
    msg["From"]    = EMAIL_FROM
    msg["To"]      = to_email

    text = f"Reset your password: {reset_url}\n\nThis link expires in 1 hour."
    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:auto;padding:32px">
      <h2 style="color:#d9ff00;background:#050505;padding:16px;border-radius:8px;text-align:center">
        Codgen
      </h2>
      <p>Click the button below to reset your password. The link expires in <strong>1 hour</strong>.</p>
      <a href="{reset_url}"
         style="display:block;background:#d9ff00;color:#000;font-weight:900;text-align:center;
                padding:14px;border-radius:8px;text-decoration:none;margin:24px 0">
        Reset Password
      </a>
      <p style="color:#888;font-size:12px">If you didn't request this, ignore this email.</p>
    </div>
    """

    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(EMAIL_FROM, to_email, msg.as_string())
