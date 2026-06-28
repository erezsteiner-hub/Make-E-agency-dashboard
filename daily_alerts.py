"""
daily_alerts.py — התראות יומיות לסוכנות
מנתח ביצועים יומיים ושולח התראות על חריגות
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import date


ALERT_RULES = {
    "roas_drop_threshold": 0.7,   # ירידה של 30%+ ב-ROAS → התראה
    "spend_spike_threshold": 1.5, # עלייה של 50%+ בהוצאה → התראה
    "min_spend_for_alert": 50,    # מינימום הוצאה לניתוח
}


def analyze_and_alert(current: dict, previous: dict, account_name: str) -> list:
    """מנתח נתונים יומיים ומחזיר רשימת התראות"""
    alerts = []

    for key, data in current.items():
        if data.get("spend", 0) < ALERT_RULES["min_spend_for_alert"]:
            continue

        prev = previous.get(key, {})
        prev_roas = prev.get("roas", 0)
        curr_roas = data.get("roas", 0)
        curr_spend = data.get("spend", 0)
        prev_spend = prev.get("spend", 0)

        # ירידה חדה ב-ROAS
        if prev_roas > 0 and curr_roas > 0:
            roas_ratio = curr_roas / prev_roas
            if roas_ratio < ALERT_RULES["roas_drop_threshold"]:
                alerts.append({
                    "type": "ROAS_DROP",
                    "severity": "high",
                    "campaign": data.get("campaign_name", key),
                    "message": f"ירידה ב-ROAS: {prev_roas:.2f}x → {curr_roas:.2f}x ({(roas_ratio-1)*100:.0f}%)",
                    "action": "בדוק קריאייטיב וקהל",
                })

        # עלייה חדה בהוצאה
        if prev_spend > 0 and curr_spend > 0:
            spend_ratio = curr_spend / prev_spend
            if spend_ratio > ALERT_RULES["spend_spike_threshold"]:
                alerts.append({
                    "type": "SPEND_SPIKE",
                    "severity": "medium",
                    "campaign": data.get("campaign_name", key),
                    "message": f"עלייה בהוצאה: ₪{prev_spend:.0f} → ₪{curr_spend:.0f} (+{(spend_ratio-1)*100:.0f}%)",
                    "action": "בדוק הגדרות תקציב",
                })

        # ROAS נמוך מאוד
        if curr_roas > 0 and curr_roas < 1.0 and curr_spend > 100:
            alerts.append({
                "type": "LOW_ROAS",
                "severity": "high",
                "campaign": data.get("campaign_name", key),
                "message": f"ROAS נמוך מ-1x: {curr_roas:.2f}x על ₪{curr_spend:.0f}",
                "action": "שקול עצירה מיידית",
            })

    return alerts


def send_alert_email(alerts: list, account_name: str):
    """שולח מייל התראה לסוכנות"""
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
    agency_email = os.environ.get("AGENCY_EMAIL", gmail_user)

    if not gmail_user or not gmail_password:
        print("אין הגדרות מייל — התראות:")
        for a in alerts:
            print(f"  [{a['severity'].upper()}] {a['campaign']}: {a['message']}")
        return

    if not alerts:
        print(f"אין התראות ל-{account_name} היום.")
        return

    today = date.today().strftime("%d/%m/%Y")
    subject = f"⚠️ התראות יומיות — {account_name} — {today}"

    high = [a for a in alerts if a["severity"] == "high"]
    medium = [a for a in alerts if a["severity"] == "medium"]

    rows = ""
    for a in alerts:
        color = "#fef2f2" if a["severity"] == "high" else "#fffbeb"
        icon = "🔴" if a["severity"] == "high" else "🟡"
        rows += f"""<tr style="background:{color};">
          <td style="padding:10px 16px;font-size:13px;">{icon} {a['campaign']}</td>
          <td style="padding:10px 16px;font-size:13px;">{a['message']}</td>
          <td style="padding:10px 16px;font-size:12px;color:#6b7280;">{a['action']}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<body style="font-family:Arial,sans-serif;background:#f9fafb;padding:20px;">
<div style="max-width:700px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;">
  <div style="background:#ef4444;padding:20px 24px;">
    <div style="font-size:18px;font-weight:700;color:#fff;">⚠️ התראות יומיות — {account_name}</div>
    <div style="font-size:12px;color:rgba(255,255,255,.85);margin-top:4px;">{today} · {len(high)} קריטיות · {len(medium)} בינוניות</div>
  </div>
  <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
    <tr style="background:#f3f4f6;">
      <th style="padding:10px 16px;font-size:11px;text-align:right;color:#6b7280;">קמפיין</th>
      <th style="padding:10px 16px;font-size:11px;text-align:right;color:#6b7280;">התראה</th>
      <th style="padding:10px 16px;font-size:11px;text-align:right;color:#6b7280;">פעולה מומלצת</th>
    </tr>
    {rows}
  </table>
  <div style="padding:16px 24px;font-size:11px;color:#9ca3af;border-top:1px solid #e5e7eb;">
    התראה אוטומטית · {account_name} · Windsor API
  </div>
</div>
</body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = agency_email
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, agency_email, msg.as_string())

    print(f"✅ התראות נשלחו ל-{agency_email} ({len(alerts)} התראות)")
