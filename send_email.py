"""
send_email.py — שליחת הדוח השבועי המעוצב במייל
"""
import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import date


def send_weekly_report(html_content: str, client_name: str, email_to: str):
    gmail_user = os.environ["GMAIL_USER"]
    gmail_password = os.environ["GMAIL_APP_PASSWORD"]

    today = date.today().strftime("%d/%m/%Y")
    subject = f"דוח ביצועים שבועי — {client_name} — {today}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = email_to
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, email_to, msg.as_string())

    print(f"   ✉️  נשלח ל-{email_to}")


def send_daily_live_link(client_name: str, live_url: str, email_to: str):
    """שולח מייל יומי עם לינק לדשבורד החי"""
    gmail_user = os.environ["GMAIL_USER"]
    gmail_password = os.environ["GMAIL_APP_PASSWORD"]

    today = date.today().strftime("%d/%m/%Y")
    subject = f"📊 דשבורד חי — {client_name} — {today}"

    html = f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<body style="font-family:Arial,sans-serif;background:#f9fafb;padding:20px;">
<div style="max-width:500px;margin:0 auto;background:#fff;border-radius:16px;padding:32px;text-align:center;">
  <div style="font-size:20px;font-weight:700;color:#1e2640;margin-bottom:8px;">{client_name}</div>
  <div style="font-size:13px;color:#6b7280;margin-bottom:24px;">דשבורד הביצועים החי שלך מוכן</div>
  <a href="{live_url}" style="display:inline-block;background:#5b6ef5;color:#fff;text-decoration:none;
     padding:14px 32px;border-radius:10px;font-weight:700;font-size:14px;">צפה בדשבורד החי</a>
  <div style="font-size:11px;color:#9ca3af;margin-top:24px;">{today} · נתונים חיים מ-Meta, Google Ads ו-GA4</div>
</div>
</body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = email_to
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, email_to, msg.as_string())

    print(f"   ✉️  לינק חי נשלח ל-{email_to}")
