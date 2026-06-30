"""
send_daily_links.py — שולח כל בוקר מייל עם לינק לדשבורד החי
לא שואב נתונים בעצמו — רק שולח לינק (הדשבורד מושך חי בעצמו כשנפתח)
"""
import os
from send_email import send_daily_live_link

GITHUB_PAGES_BASE = "https://erezsteiner-hub.github.io/Make-E-agency-dashboard"

CLIENTS = {
    "crazy": "Crazy Line",
    "pretty": "Pretty Ballerinas",
    "annabella": "Annabella",
    "fine": "Fine Rituals",
    "laster": "Laster",
    "aristo": "Aristo Shmat",
}


def main():
    for key, name in CLIENTS.items():
        email_env_key = f"EMAIL_TO_{key.upper()}"
        email_to = os.environ.get(email_env_key)
        if not email_to:
            print(f"⏭️  {name}: אין EMAIL_TO מוגדר, מדלג")
            continue

        live_url = f"{GITHUB_PAGES_BASE}/{key}_live.html"
        try:
            send_daily_live_link(name, live_url, email_to)
        except Exception as e:
            print(f"❌ {name}: שגיאה בשליחה - {e}")


if __name__ == "__main__":
    main()
