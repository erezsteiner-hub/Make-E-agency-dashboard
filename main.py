"""
main.py — מנצח האוטומציה השבועית
שואב מ-Windsor, בונה דוח HTML מלא עם תובנות, שומר ושולח מייל.

הרצה:
    python main.py --days 7
"""

import argparse
import os
import json
from datetime import date, timedelta

from windsor_api import (
    WindsorClient, parse_meta_rows, parse_google_rows,
    parse_ga4_total, parse_ga4_channels
)
from html_report_builder import build_full_report


# ===== הגדרות חזותיות לכל לקוח =====
CLIENT_BRANDS = {
    "crazy": {
        "name": "Crazy Line", "initials": "CL", "color": "#EC0E8D", "color2": "#f43fa8",
        "font": "Rubik", "font_url": "https://fonts.googleapis.com/css2?family=Rubik:wght@400;500;600;700;800;900&display=swap",
        "bg": "#fdf5f9", "surface2": "#fce8f3", "border": "#f0d0e4",
        "text": "#1a0d14", "text2": "#5a2d47", "muted": "#a07090",
        "meta_account": "2562301110668961", "google_account": "654-753-2446", "ga4_account": "454540408",
    },
    "pretty": {
        "name": "Pretty Ballerinas", "initials": "PB", "color": "#1a1a1a", "color2": "#2d2d2d",
        "font": "Heebo", "font_url": "https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;700;800;900&display=swap",
        "bg": "#fdf9f5", "surface2": "#f5ede4", "border": "#e8d9c8",
        "text": "#1a0f0a", "text2": "#5a3d2b", "muted": "#a08070",
        "meta_account": "708681422636732", "google_account": "477-626-3831", "ga4_account": "152370243",
    },
    "annabella": {
        "name": "Annabella", "initials": "AN", "color": "#2d5a8e", "color2": "#3a70b0",
        "font": "Heebo", "font_url": "https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;700;800;900&display=swap",
        "bg": "#f4f7fb", "surface2": "#e8f0f8", "border": "#ccdaec",
        "text": "#0d1f35", "text2": "#2a4a70", "muted": "#7090b0",
        "meta_account": "1247794652730158", "google_account": "490-285-3125", "ga4_account": "354304809",
    },
    "fine": {
        "name": "Fine Rituals", "initials": "FR", "color": "#3d2b1f", "color2": "#5c4030",
        "font": "Heebo", "font_url": "https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;700;800;900&display=swap",
        "bg": "#faf7f4", "surface2": "#f0e8df", "border": "#ddd0c4",
        "text": "#1a0f08", "text2": "#5a3d28", "muted": "#9a7d68",
        "meta_account": "918073650786458", "google_account": "700-518-0619", "ga4_account": "518599842",
    },
    "laster": {
        "name": "Laster", "initials": "LS", "color": "#1c1c1c", "color2": "#333333",
        "font": "Heebo", "font_url": "https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;700;800;900&display=swap",
        "bg": "#f8f7f5", "surface2": "#f0ece4", "border": "#e0d8cc",
        "text": "#1a1a1a", "text2": "#4a4030", "muted": "#9a9080",
        "meta_account": "369761200875429", "google_account": "", "ga4_account": "315864239",
    },
    "aristo": {
        "name": "Aristo Shmat", "initials": "AS", "color": "#0d9488", "color2": "#14b8a6",
        "font": "Heebo", "font_url": "https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;700;800;900&display=swap",
        "bg": "#f3faf9", "surface2": "#e6f5f3", "border": "#c4e8e3",
        "text": "#0a201d", "text2": "#1d4d47", "muted": "#6ba39c",
        "meta_account": "265005426163824", "google_account": "377-969-5637", "ga4_account": "401528124",
    },
}


def fmt_display(d):
    return d.strftime("%d/%m/%Y")


def process_client(client_key: str, windsor: WindsorClient, days: int):
    """מעבד לקוח אחד: שואב, בונה דוח, מחזיר HTML"""
    cfg = CLIENT_BRANDS[client_key]
    today = date.today()
    current_until = today - timedelta(days=1)
    current_since = current_until - timedelta(days=days - 1)
    prev_until = current_since - timedelta(days=1)
    prev_since = prev_until - timedelta(days=days - 1)

    fmt_iso = lambda d: d.strftime("%Y-%m-%d")

    print(f"[{cfg['name']}] שולף נתונים: {fmt_iso(current_since)} - {fmt_iso(current_until)}")

    # Meta — תקופה נוכחית וקודמת
    raw_meta_curr = windsor.get_meta_campaign_data(cfg["meta_account"], fmt_iso(current_since), fmt_iso(current_until))
    raw_meta_prev = windsor.get_meta_campaign_data(cfg["meta_account"], fmt_iso(prev_since), fmt_iso(prev_until))
    meta_curr = parse_meta_rows(raw_meta_curr)
    meta_prev = parse_meta_rows(raw_meta_prev)

    # Google
    google_data = {}
    if cfg["google_account"]:
        raw_google = windsor.get_google_ads_data(cfg["google_account"], fmt_iso(current_since), fmt_iso(current_until))
        google_data = parse_google_rows(raw_google)

    # GA4
    raw_ga4_total = windsor.get_ga4_total(cfg["ga4_account"], fmt_iso(current_since), fmt_iso(current_until))
    ga4_data = parse_ga4_total(raw_ga4_total)

    raw_ga4_channels = windsor.get_ga4_channels(cfg["ga4_account"], fmt_iso(current_since), fmt_iso(current_until))
    ga4_channels = parse_ga4_channels(raw_ga4_channels)

    raw_ga4_daily = windsor.get_ga4_daily(cfg["ga4_account"], fmt_iso(current_since), fmt_iso(current_until))

    # בניית הדוח
    html = build_full_report(
        client_config=cfg,
        current=meta_curr,
        previous=meta_prev,
        google_data=google_data,
        ga4_data=ga4_data,
        ga4_channels=ga4_channels,
        ga4_daily=raw_ga4_daily,
        date_range=(fmt_display(current_since), fmt_display(current_until)),
        prev_date_range=(fmt_display(prev_since), fmt_display(prev_until)),
    )

    return html, {
        "ga4_revenue": ga4_data["total"]["revenue"],
        "meta_spend": sum(c["spend"] for c in meta_curr.values()),
        "google_spend": sum(c["spend"] for c in google_data.values()) if google_data else 0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--client", type=str, default=None, help="לקוח ספציפי, או הכל אם ריק")
    args = parser.parse_args()

    api_key = os.environ["WINDSOR_API_KEY"]
    windsor = WindsorClient(api_key)

    clients = [args.client] if args.client else list(CLIENT_BRANDS.keys())

    os.makedirs("reports_output", exist_ok=True)

    for client_key in clients:
        try:
            html, summary = process_client(client_key, windsor, args.days)

            # שמירת הדוח
            out_path = f"reports_output/{client_key}_report.html"
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"✅ [{client_key}] דוח נשמר: {out_path}")
            print(f"   GA4: {summary['ga4_revenue']:,.0f}₪ | Meta: {summary['meta_spend']:,.0f}₪ | Google: {summary['google_spend']:,.0f}₪")

            # שליחת מייל (אם מוגדר)
            email_env_key = f"EMAIL_TO_{client_key.upper()}"
            if os.environ.get("GMAIL_USER") and os.environ.get(email_env_key):
                from send_email import send_weekly_report
                send_weekly_report(html, CLIENT_BRANDS[client_key]["name"], os.environ[email_env_key])

        except Exception as e:
            print(f"❌ [{client_key}] שגיאה: {e}")
            continue

    print("\n✅ הרצה הושלמה")


if __name__ == "__main__":
    main()
