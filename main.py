"""
main.py — מנצח האוטומציה השבועית
שואב מ-Windsor, בונה דוח HTML מלא עם תובנות, שומר ושולח מייל.

הרצה:
    python main.py --days 7
"""

import argparse
import os
import json
import calendar
from datetime import date, timedelta

from windsor_api import (
    WindsorClient, parse_meta_rows, parse_google_rows,
    parse_ga4_total, parse_ga4_channels, parse_ga4_products, parse_ga4_campaigns, parse_ga4_new_vs_returning
)
from html_report_builder import build_full_report
from agency_overview_builder import build_agency_overview
from brand_assets import CLIENT_LOGOS, AGENCY_LOGO


def compute_date_windows(days=7):
    """
    מחשב את חלונות הזמן לדוח.
    רגיל: שבוע נוכחי (7 ימים שהסתיימו אתמול) מול אותם תאריכים חודש קודם.
    סוף חודש: אם הריצה היא ביום ראשון האחרון של החודש → סיכום חודשי מלא
              (החודש הנוכחי מול החודש הקודם).
    מחזיר: (current_until, current_since, prev_until, prev_since, is_monthly)
    """
    today = date.today()

    # בדיקה אם זה הדוח האחרון של החודש:
    # ריצה שבועית היא ביום ראשון. אם בתוך 7 הימים הבאים מתחלף החודש → זה הראשון האחרון בחודש.
    next_week = today + timedelta(days=7)
    is_last_sunday_of_month = (next_week.month != today.month)

    if is_last_sunday_of_month:
        # סיכום חודשי: כל החודש הנוכחי מול החודש הקודם
        first_of_this_month = today.replace(day=1)
        last_day_this = calendar.monthrange(today.year, today.month)[1]
        current_since = first_of_this_month
        current_until = today.replace(day=last_day_this)

        # חודש קודם
        prev_month_last = first_of_this_month - timedelta(days=1)
        prev_since = prev_month_last.replace(day=1)
        prev_until = prev_month_last
        return current_until, current_since, prev_until, prev_since, True

    # שבועי רגיל: 7 ימים שהסתיימו אתמול
    current_until = today - timedelta(days=1)
    current_since = current_until - timedelta(days=days - 1)

    # השוואה: אותם תאריכים בדיוק חודש קודם
    prev_until = shift_month_back(current_until)
    prev_since = shift_month_back(current_since)
    return current_until, current_since, prev_until, prev_since, False


def shift_month_back(d):
    """מחזיר את אותו יום בחודש הקודם (עם טיפול בחודשים קצרים)"""
    month = d.month - 1 or 12
    year = d.year if d.month > 1 else d.year - 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(d.day, last_day)
    return date(year, month, day)


# ===== הגדרות חזותיות לכל לקוח =====
CLIENT_BRANDS = {
    "crazy": {
        "name": "Crazy Line", "initials": "CL", "color": "#000000", "color2": "#2d2d2d",
        "font": "Rubik", "font_url": "https://fonts.googleapis.com/css2?family=Rubik:wght@400;500;600;700;800;900&display=swap",
        "bg": "#f7f7f7", "surface2": "#ececec", "border": "#e2e2e2",
        "text": "#111111", "text2": "#333333", "muted": "#777777",
        "meta_account": "2562301110668961", "google_account": "654-753-2446", "ga4_account": "454540408",
    },
    "pretty": {
        "name": "Pretty Ballerinas", "initials": "PB", "color": "#EC0E8D", "color2": "#f43fa8",
        "font": "Heebo", "font_url": "https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;700;800;900&display=swap",
        "bg": "#fdf5f9", "surface2": "#fce8f3", "border": "#f0d0e4",
        "text": "#1a0d14", "text2": "#5a2d47", "muted": "#a07090",
        "meta_account": "708681422636732", "google_account": "477-626-3831", "ga4_account": "152370243",
    },
    "annabella": {
        "name": "Annabella", "initials": "AN", "color": "#EC0E8D", "color2": "#f43fa8",
        "font": "Heebo", "font_url": "https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;700;800;900&display=swap",
        "bg": "#fdf5f9", "surface2": "#fce8f3", "border": "#f0d0e4",
        "text": "#1a0d14", "text2": "#5a2d47", "muted": "#a07090",
        "meta_account": "1247794652730158", "google_account": "490-285-3125", "ga4_account": "354304809",
    },
    "fine": {
        "name": "Fine Rituals", "initials": "FR", "color": "#000000", "color2": "#2d2d2d",
        "font": "Heebo", "font_url": "https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;700;800;900&display=swap",
        "bg": "#f7f7f7", "surface2": "#ececec", "border": "#e2e2e2",
        "text": "#111111", "text2": "#333333", "muted": "#777777",
        "meta_account": "918073650786458", "google_account": "700-518-0619", "ga4_account": "518599842",
    },
    "laster": {
        "name": "Laster", "initials": "LS", "color": "#000000", "color2": "#2d2d2d",
        "font": "Heebo", "font_url": "https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;700;800;900&display=swap",
        "bg": "#f7f7f7", "surface2": "#ececec", "border": "#e2e2e2",
        "text": "#111111", "text2": "#333333", "muted": "#777777",
        "meta_account": "369761200875429", "google_account": "", "ga4_account": "315864239",
    },
    "aristo": {
        "name": "Aristo Shmat", "initials": "AS", "color": "#000000", "color2": "#2d2d2d",
        "font": "Heebo", "font_url": "https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;700;800;900&display=swap",
        "bg": "#f7f7f7", "surface2": "#ececec", "border": "#e2e2e2",
        "text": "#111111", "text2": "#333333", "muted": "#777777",
        "meta_account": "265005426163824", "google_account": "377-969-5637", "ga4_account": "401528124",
    },
}


def fmt_display(d):
    return d.strftime("%d/%m/%Y")


def process_client(client_key: str, windsor: WindsorClient, days: int):
    """מעבד לקוח אחד: שואב, בונה דוח, מחזיר HTML"""
    cfg = dict(CLIENT_BRANDS[client_key])
    cfg["logo_data_uri"] = CLIENT_LOGOS.get(client_key, "")
    cfg["agency_logo_data_uri"] = AGENCY_LOGO
    cfg["logo_style_override"] = "max-width:600px;height:60px;" if client_key == "fine" else ""
    fmt_iso = lambda d: d.strftime("%Y-%m-%d")

    # ── חישוב חלון הזמן ──
    # ברירת מחדל: שבוע נוכחי (7 ימים שהסתיימו אתמול)
    # השוואה: אותם תאריכים בדיוק חודש קודם
    current_until, current_since, prev_until, prev_since, is_monthly = compute_date_windows(days)

    label = "סיכום חודשי" if is_monthly else "דוח שבועי"
    print(f"[{cfg['name']}] {label}: {fmt_iso(current_since)} - {fmt_iso(current_until)} "
          f"(השוואה: {fmt_iso(prev_since)} - {fmt_iso(prev_until)})")

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

    # דוחות חדשים: Best Seller + טופ קמפיינים GA4
    raw_ga4_products = windsor.get_ga4_products(cfg["ga4_account"], fmt_iso(current_since), fmt_iso(current_until))
    top_products = parse_ga4_products(raw_ga4_products)

    raw_ga4_campaigns = windsor.get_ga4_campaigns(cfg["ga4_account"], fmt_iso(current_since), fmt_iso(current_until))
    top_campaigns = parse_ga4_campaigns(raw_ga4_campaigns)

    # דוח חדש: לקוחות חדשים מול חוזרים
    raw_ga4_new_returning = windsor.get_ga4_new_vs_returning(cfg["ga4_account"], fmt_iso(current_since), fmt_iso(current_until))
    new_vs_returning = parse_ga4_new_vs_returning(raw_ga4_new_returning)

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
        top_products=top_products,
        top_campaigns=top_campaigns,
        is_monthly=is_monthly,
        new_vs_returning=new_vs_returning,
    )

    return html, {
        "ga4_revenue": ga4_data["total"]["revenue"],
        "meta_spend": sum(c["spend"] for c in meta_curr.values()),
        "meta_roas": (sum(c["purchase_value"] for c in meta_curr.values()) /
                      sum(c["spend"] for c in meta_curr.values())) if sum(c["spend"] for c in meta_curr.values()) > 0 else 0,
        "google_spend": sum(c["spend"] for c in google_data.values()) if google_data else 0,
        "google_roas": (sum(c["value"] for c in google_data.values()) /
                        sum(c["spend"] for c in google_data.values())) if google_data and sum(c["spend"] for c in google_data.values()) > 0 else 0,
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

    agency_summary = {}
    today = date.today()
    current_until = today - timedelta(days=1)
    current_since = current_until - timedelta(days=args.days - 1)

    for client_key in clients:
        try:
            html, summary = process_client(client_key, windsor, args.days)

            # שמירת הדוח
            out_path = f"reports_output/{client_key}_report.html"
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"✅ [{client_key}] דוח נשמר: {out_path}")
            print(f"   GA4: {summary['ga4_revenue']:,.0f}₪ | Meta: {summary['meta_spend']:,.0f}₪ | Google: {summary['google_spend']:,.0f}₪")

            # איסוף נתונים לדשבורד הסוכנות
            cfg = CLIENT_BRANDS[client_key]
            agency_summary[client_key] = {
                "name": cfg["name"], "color": cfg["color"],
                "ga4_revenue": summary["ga4_revenue"],
                "meta_spend": summary["meta_spend"],
                "meta_roas": summary.get("meta_roas", 0),
                "google_spend": summary["google_spend"],
                "google_roas": summary.get("google_roas", 0),
            }

            # שליחת מייל (אם מוגדר)
            email_env_key = f"EMAIL_TO_{client_key.upper()}"
            if os.environ.get("GMAIL_USER") and os.environ.get(email_env_key):
                from send_email import send_weekly_report
                send_weekly_report(html, CLIENT_BRANDS[client_key]["name"], os.environ[email_env_key])

        except Exception as e:
            print(f"❌ [{client_key}] שגיאה: {e}")
            continue

    # בניית דשבורד הסוכנות (index.html) — אוטומטית, ללא בקשה
    if agency_summary:
        try:
            prev_until = current_since - timedelta(days=1)
            prev_since = prev_until - timedelta(days=args.days - 1)
            overview_html = build_agency_overview(
                agency_summary,
                date_range=(fmt_display(current_since), fmt_display(current_until)),
            )
            with open("reports_output/index.html", "w", encoding="utf-8") as f:
                f.write(overview_html)
            print(f"✅ [agency] דשבורד סוכנות עודכן: reports_output/index.html")
        except Exception as e:
            print(f"❌ [agency overview] שגיאה: {e}")

    print("\n✅ הרצה הושלמה")


if __name__ == "__main__":
    main()
