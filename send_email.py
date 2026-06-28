"""
send_email.py — שליחת דוח שבועי במייל
תומך בשם לקוח דינמי דרך ACCOUNT_NAME
"""
import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import date


def send_report(report_md: str, report_data: dict = None):
    gmail_user = os.environ["GMAIL_USER"]
    gmail_password = os.environ["GMAIL_APP_PASSWORD"]
    email_to = os.environ["EMAIL_TO"]
    account_name = os.environ.get("ACCOUNT_NAME", "הלקוח")

    today = date.today().strftime("%d/%m/%Y")
    subject = f"דוח ביצועים שבועי — {account_name} — {today}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = email_to
    msg.attach(MIMEText(report_md, "plain", "utf-8"))

    if report_data:
        try:
            from email_template import generate_html_email
            html = generate_html_email(report_data)
            msg.attach(MIMEText(html, "html", "utf-8"))
        except ImportError:
            pass  # email_template אופציונלי

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, email_to, msg.as_string())

    print(f"✅ נשלח ל-{email_to} | {account_name}")
