"""
report.py — משודרג לעבוד עם Windsor (Meta + Google Ads + GA4)
שומר על מבנה המקורי (parse_all, build_report, build_flags)
ומוסיף Google Ads ו-GA4 לדוח.
"""

from collections import defaultdict


RULES = {
    "min_spend_for_flagging": 100,
    "low_roas_threshold": 1.5,
    "high_roas_threshold": 4.0,
    "high_frequency_threshold": 3.5,
    "budget_increase_pct": 20,
}


def parse_all(raw_rows: list) -> dict:
    """תואם למבנה המקורי — מקבל שורות Meta מעובדות מ-windsor_api"""
    return {row.get("ad_id", row.get("campaign_name", "")): row for row in raw_rows}


def pct_change(current, previous):
    if previous in (None, 0):
        return None
    return ((current - previous) / previous) * 100


def build_flags(current: dict) -> list:
    flags = []
    for ad_id, data in current.items():
        if data["spend"] < RULES["min_spend_for_flagging"]:
            continue
        if data["roas"] < RULES["low_roas_threshold"]:
            flags.append({
                "ad_name": data["campaign_name"],
                "campaign_name": data["campaign_name"],
                "type": "ROAS נמוך",
                "detail": f"ROAS={data['roas']:.2f} עם הוצאה של {data['spend']:.0f}₪",
                "suggestion": "לשקול השבתה / שינוי קריאייטיב / מיקוד מחדש",
            })
        if data["roas"] > RULES["high_roas_threshold"]:
            flags.append({
                "ad_name": data["campaign_name"],
                "campaign_name": data["campaign_name"],
                "type": "קמפיין מצטיין",
                "detail": f"ROAS={data['roas']:.2f}",
                "suggestion": f"לשקול הגדלת תקציב ב-{RULES['budget_increase_pct']}%",
            })
    return flags


def build_report(current: dict, previous: dict, date_range: tuple,
                 prev_date_range: tuple, google_data: dict = None,
                 ga4_data: dict = None, account_name: str = "הלקוח") -> str:
    """בונה דוח Markdown מלא — Meta + Google Ads + GA4"""
    lines = []
    lines.append(f"# דוח ביצועים שבועי — {account_name}")
    lines.append(f"תקופה נוכחית: {date_range[0]} עד {date_range[1]}")
    lines.append(f"תקופה קודמת: {prev_date_range[0]} עד {prev_date_range[1]}")
    lines.append("")

    # ===== GA4 — מקור האמת =====
    if ga4_data and ga4_data.get("total", {}).get("revenue", 0) > 0:
        ga4_total = ga4_data["total"]
        lines.append("## 📊 הכנסות מהאתר (GA4 — מקור האמת)")
        lines.append(f"- הכנסות כוללות: {ga4_total['revenue']:,.0f}₪")
        lines.append(f"- עסקאות: {ga4_total['transactions']:.0f}")
        lines.append(f"- סשנים: {ga4_total['sessions']:,.0f}")
        lines.append("")
        if ga4_data.get("channels"):
            lines.append("### הכנסות לפי ערוץ")
            for ch, vals in sorted(ga4_data["channels"].items(),
                                   key=lambda x: -x[1]["revenue"]):
                if vals["revenue"] > 0:
                    lines.append(f"- {ch}: {vals['revenue']:,.0f}₪ "
                                 f"({vals['transactions']:.0f} עסקאות)")
            lines.append("")

    # ===== META ADS =====
    total_spend = sum(d["spend"] for d in current.values())
    total_value = sum(d["purchase_value"] for d in current.values())
    total_purchases = sum(d["purchases"] for d in current.values())
    prev_spend = sum(d["spend"] for d in previous.values())
    prev_value = sum(d["purchase_value"] for d in previous.values())
    overall_roas = (total_value / total_spend) if total_spend > 0 else 0
    prev_roas = (prev_value / prev_spend) if prev_spend > 0 else 0

    lines.append("## 📱 Meta Ads")
    lines.append(f"- הוצאה: {total_spend:,.0f}₪ (שינוי: {_fmt_pct(pct_change(total_spend, prev_spend))})")
    lines.append(f"- ROAS: {overall_roas:.2f} (תקופה קודמת: {prev_roas:.2f})")
    lines.append(f"- רכישות: {total_purchases:.0f}")
    lines.append("")
    lines.append("### קמפיינים")
    lines.append("| קמפיין | הוצאה | ROAS | רכישות | CPA |")
    lines.append("|---|---|---|---|---|")
    for data in sorted(current.values(), key=lambda x: -x["spend"]):
        cpa_str = f"{data['cpa']:.0f}₪" if data["cpa"] else "-"
        lines.append(f"| {data['campaign_name']} | {data['spend']:,.0f}₪ | "
                     f"{data['roas']:.2f} | {data['purchases']:.0f} | {cpa_str} |")
    lines.append("")

    # ===== GOOGLE ADS =====
    if google_data:
        g_spend = sum(c["spend"] for c in google_data.values())
        g_value = sum(c["value"] for c in google_data.values())
        g_roas = (g_value / g_spend) if g_spend > 0 else 0
        lines.append("## 🔍 Google Ads")
        lines.append(f"- הוצאה: {g_spend:,.0f}₪")
        lines.append(f"- ROAS: {g_roas:.2f}")
        lines.append("")
        lines.append("| קמפיין | הוצאה | ROAS | המרות |")
        lines.append("|---|---|---|---|")
        for c in sorted(google_data.values(), key=lambda x: -x["spend"]):
            is_brand = any(k in c["name"].lower() for k in ["brand", "ברנד"])
            tag = "🏷️" if is_brand else ""
            lines.append(f"| {tag}{c['name']} | {c['spend']:,.0f}₪ | "
                         f"{c['roas']:.2f} | {c['conv']:.0f} |")
        lines.append("")

    # ===== ROAS משולב =====
    if google_data and ga4_data:
        all_spend = total_spend + sum(c["spend"] for c in google_data.values())
        ga4_rev = ga4_data["total"]["revenue"]
        blended = (ga4_rev / all_spend) if all_spend > 0 else 0
        lines.append("## 💡 ROAS משולב (GA4 ÷ סך הוצאות)")
        lines.append(f"- סך הוצאות פרסום: {all_spend:,.0f}₪")
        lines.append(f"- הכנסות GA4: {ga4_rev:,.0f}₪")
        lines.append(f"- **ROAS משולב: {blended:.2f}x**")
        lines.append("")

    # ===== המלצות =====
    flags = build_flags(current)
    lines.append("## ⚡ המלצות לפעולה")
    if not flags:
        lines.append("לא נמצאו חריגות לפי החוקים הנוכחיים.")
    else:
        for f in flags:
            lines.append(f"- **[{f['type']}]** {f['ad_name']}: "
                         f"{f['detail']} → {f['suggestion']}")

    return "\n".join(lines)


def _fmt_pct(value):
    if value is None:
        return "אין נתון להשוואה"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.1f}%"
