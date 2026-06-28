"""
main.py — משודרג לעבוד עם Windsor (Meta + Google Ads + GA4)
ללא META_ACCESS_TOKEN — הכל דרך WINDSOR_API_KEY אחד.

הרצה:
    python main.py --mode weekly
    python main.py --mode daily
"""

import argparse
import os
from datetime import date, timedelta
from dotenv import load_dotenv

from windsor_api import WindsorClient, parse_meta_rows, parse_google_rows, parse_ga4_rows
from report import parse_all, build_report, build_flags


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--mode", type=str, default="weekly",
                        choices=["weekly", "daily"])
    args = parser.parse_args()

    load_dotenv(encoding="utf-8-sig")

    # === Windsor credentials ===
    windsor_key = os.environ["WINDSOR_API_KEY"]
    meta_account_id = os.environ.get("META_AD_ACCOUNT_ID", "")
    google_account_id = os.environ.get("GOOGLE_ADS_ACCOUNT_ID", "")
    ga4_account_id = os.environ.get("GA4_ACCOUNT_ID", "")
    account_name = os.environ.get("ACCOUNT_NAME", "הלקוח")

    client = WindsorClient(
        api_key=windsor_key,
        meta_account_id=meta_account_id,
        google_ads_account_id=google_account_id,
        ga4_account_id=ga4_account_id,
    )

    # === טווחי תאריכים ===
    today = date.today()
    current_until = today - timedelta(days=1)
    current_since = current_until - timedelta(days=args.days - 1)
    prev_until = current_since - timedelta(days=1)
    prev_since = prev_until - timedelta(days=args.days - 1)

    fmt = lambda d: d.strftime("%Y-%m-%d")
    fmt_display = lambda d: d.strftime("%d/%m/%Y")

    print(f"שולף נתונים: {fmt(current_since)} — {fmt(current_until)}")

    # === שליפת נתונים ===
    raw_meta_current = client.get_meta_campaign_data(fmt(current_since), fmt(current_until))
    raw_meta_previous = client.get_meta_campaign_data(fmt(prev_since), fmt(prev_until))

    meta_current = parse_meta_rows(raw_meta_current)
    meta_previous = parse_meta_rows(raw_meta_previous)

    # Google Ads ו-GA4 — רק אם מוגדרים
    google_data = None
    ga4_data = None

    if google_account_id:
        raw_google = client.get_google_ads_data(fmt(current_since), fmt(current_until))
        google_data = parse_google_rows(raw_google)
        print(f"Google Ads: {len(google_data)} קמפיינים")

    if ga4_account_id:
        raw_ga4 = client.get_ga4_data(fmt(current_since), fmt(current_until))
        ga4_data = parse_ga4_rows(raw_ga4)
        print(f"GA4: {ga4_data['total']['revenue']:,.0f}₪ הכנסות")

    # === בניית דוח ===
    if args.mode == "daily":
        from daily_alerts import analyze_and_alert, send_alert_email
        alerts = analyze_and_alert(meta_current, meta_previous, account_name)
        send_alert_email(alerts, account_name)

    else:
        report_md = build_report(
            meta_current, meta_previous,
            date_range=(fmt_display(current_since), fmt_display(current_until)),
            prev_date_range=(fmt_display(prev_since), fmt_display(prev_until)),
            google_data=google_data,
            ga4_data=ga4_data,
            account_name=account_name,
        )

        os.makedirs("reports", exist_ok=True)
        out_path = f"reports/report_{fmt(today)}.md"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(report_md)

        print(report_md)
        print(f"\nהדוח נשמר: {out_path}")

        report_data = {
            "date_range": (fmt_display(current_since), fmt_display(current_until)),
            "prev_date_range": (fmt_display(prev_since), fmt_display(prev_until)),
            "account_name": account_name,
            "summary": {
                "spend": sum(d["spend"] for d in meta_current.values()),
                "roas": sum(d["purchase_value"] for d in meta_current.values()) /
                        max(sum(d["spend"] for d in meta_current.values()), 0.01),
                "purchases": sum(d["purchases"] for d in meta_current.values()),
                "prev_spend": sum(d["spend"] for d in meta_previous.values()),
                "prev_roas": sum(d["purchase_value"] for d in meta_previous.values()) /
                             max(sum(d["spend"] for d in meta_previous.values()), 0.01),
            },
            "campaigns": list(meta_current.values()),
            "flags": build_flags(meta_current),
            "google_data": google_data,
            "ga4_data": ga4_data,
        }

        if (os.environ.get("GMAIL_USER") and
                os.environ.get("GMAIL_APP_PASSWORD") and
                os.environ.get("EMAIL_TO")):
            from send_email import send_report
            send_report(report_md, report_data)
        else:
            print("לא הוגדר מייל — הדוח נשמר מקומית בלבד")


if __name__ == "__main__":
    main()
