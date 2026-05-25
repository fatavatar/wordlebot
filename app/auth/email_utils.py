import secrets
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.config import Config


def generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def send_auth_code(to_email: str, code: str, cfg: Config) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Your Wordle Tournament login code"
    msg["From"] = cfg.EMAIL_SENDER
    msg["To"] = to_email

    plain = f"Your Wordle Tournament login code is: {code}\n\nThis code expires in {cfg.AUTH_CODE_TTL_MIN} minutes.\n\nIf you didn't request this, you can safely ignore it."
    html = f"""
<html><body style="font-family:'Helvetica Neue',Arial,sans-serif;background:#fff;color:#1a1a1b;max-width:480px;margin:40px auto;padding:24px">
  <div style="border-bottom:2px solid #1a1a1b;padding-bottom:12px;margin-bottom:24px">
    <h1 style="margin:0;font-size:20px;letter-spacing:0.1em;text-transform:uppercase">Wordle Tournament</h1>
  </div>
  <p>Your login code is:</p>
  <div style="font-size:42px;font-weight:700;letter-spacing:0.2em;text-align:center;padding:24px;background:#f6f7f8;border-radius:4px;margin:16px 0">{code}</div>
  <p style="color:#787c7e;font-size:14px">Expires in {cfg.AUTH_CODE_TTL_MIN} minutes. If you didn't request this, ignore this email.</p>
</body></html>
"""

    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    context = ssl.create_default_context()
    with smtplib.SMTP(cfg.SMTP_HOST, cfg.SMTP_PORT) as server:
        if cfg.SMTP_TLS:
            server.starttls(context=context)
        server.login(cfg.SMTP_USERNAME, cfg.SMTP_PASSWORD)
        server.sendmail(cfg.EMAIL_SENDER, to_email, msg.as_string())
