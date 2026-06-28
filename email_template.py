"""
email_template.py — תבנית HTML למייל שבועי
תומך בכל 5 הלקוחות עם עיצוב מקצועי
"""

def generate_html_email(report_data: dict) -> str:
    account_name = report_data.get("account_name", "הלקוח")
    date_range = report_data.get("date_range", ("", ""))
    prev_range = report_data.get("prev_date_range", ("", ""))
    summary = report_data.get("summary", {})
    campaigns = report_data.get("campaigns", [])
    flags = report_data.get("flags", [])
    google_data = report_data.get("google_data")
    ga4_data = report_data.get("ga4_data")

    spend = summary.get("spend", 0)
    roas = summary.get("roas", 0)
    purchases = summary.get("purchases", 0)
    prev_spend = summary.get("prev_spend", 0)
    prev_roas = summary.get("prev_roas", 0)

    spend_change = ((spend - prev_spend) / prev_spend * 100) if prev_spend else 0
    roas_change = ((roas - prev_roas) / prev_roas * 100) if prev_roas else 0

    def arrow(val):
        return "▲" if val >= 0 else "▼"

    def color(val):
        return "#10b981" if val >= 0 else "#ef4444"

    # GA4 section
    ga4_html = ""
    if ga4_data and ga4_data.get("total", {}).get("revenue", 0) > 0:
        t = ga4_data["total"]
        ga4_html = f"""
        <tr><td colspan="2" style="padding:16px 24px 8px;font-size:13px;font-weight:700;color:#374151;
            border-top:2px solid #f3f4f6;">📊 הכנסות מהאתר (GA4 — מקור האמת)</td></tr>
        <tr>
          <td style="padding:4px 24px;font-size:13px;color:#6b7280;">הכנסות כוללות</td>
          <td style="padding:4px 24px;font-size:13px;font-weight:700;color:#10b981;text-align:left;">
            ₪{t['revenue']:,.0f}</td>
        </tr>
        <tr>
          <td style="padding:4px 24px 16px;font-size:13px;color:#6b7280;">עסקאות</td>
          <td style="padding:4px 24px 16px;font-size:13px;font-weight:600;text-align:left;">
            {t['transactions']:.0f}</td>
        </tr>"""

    # Campaigns rows
    camp_rows = ""
    for c in sorted(campaigns, key=lambda x: -x.get("spend", 0))[:8]:
        r = c.get("roas", 0)
        rc = "#10b981" if r >= 4 else "#f59e0b" if r >= 2 else "#ef4444"
        camp_rows += f"""
        <tr style="border-top:1px solid #f3f4f6;">
          <td style="padding:10px 24px;font-size:13px;color:#374151;">{c.get('campaign_name') or c.get('name','')}</td>
          <td style="padding:10px 24px;font-size:13px;text-align:left;">
            <span style="color:#6b7280;">₪{c.get('spend',0):,.0f}</span>
            <span style="margin-right:12px;font-weight:700;color:{rc};">ROAS {r:.2f}x</span>
          </td>
        </tr>"""

    # Flags
    flags_html = ""
    if flags:
        flags_html = """<tr><td colspan="2" style="padding:16px 24px 8px;font-size:13px;font-weight:700;
            color:#374151;border-top:2px solid #f3f4f6;">⚡ המלצות לפעולה</td></tr>"""
        for f in flags[:5]:
            flags_html += f"""
            <tr><td colspan="2" style="padding:6px 24px;font-size:12px;color:#6b7280;">
              • <b style="color:#374151;">[{f['type']}]</b> {f['ad_name']}: {f['detail']} → {f['suggestion']}
            </td></tr>"""

    # Google section
    google_html = ""
    if google_data:
        g_spend = sum(c["spend"] for c in google_data.values())
        g_value = sum(c["value"] for c in google_data.values())
        g_roas = (g_value / g_spend) if g_spend > 0 else 0
        google_html = f"""
        <tr><td colspan="2" style="padding:16px 24px 8px;font-size:13px;font-weight:700;
            color:#374151;border-top:2px solid #f3f4f6;">🔍 Google Ads</td></tr>
        <tr>
          <td style="padding:4px 24px 16px;font-size:13px;color:#6b7280;">הוצאה · ROAS</td>
          <td style="padding:4px 24px 16px;font-size:13px;font-weight:700;text-align:left;">
            ₪{g_spend:,.0f} · <span style="color:#ea4335;">{g_roas:.2f}x</span></td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:'Helvetica Neue',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f9fafb;padding:32px 0;">
  <tr><td align="center">
    <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:16px;
        overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,.08);">

      <!-- HEADER -->
      <tr><td style="background:linear-gradient(135deg,#5b6ef5,#7c8ef9);padding:28px 24px;">
        <div style="font-size:22px;font-weight:800;color:#fff;letter-spacing:-.3px;">{account_name}</div>
        <div style="font-size:13px;color:rgba(255,255,255,.85);margin-top:4px;">
          דוח ביצועים שבועי · {date_range[0]} – {date_range[1]}</div>
      </td></tr>

      <!-- KPI CARDS -->
      <tr><td style="padding:20px 24px;">
        <table width="100%" cellpadding="0" cellspacing="0">
          <tr>
            <td width="33%" style="padding:4px;">
              <div style="background:#f0fdf4;border-radius:12px;padding:16px;text-align:center;">
                <div style="font-size:11px;color:#6b7280;font-weight:600;margin-bottom:6px;">הוצאות Meta</div>
                <div style="font-size:22px;font-weight:800;color:#111827;">₪{spend:,.0f}</div>
                <div style="font-size:11px;margin-top:4px;color:{color(spend_change)};">
                  {arrow(spend_change)} {abs(spend_change):.1f}% מהשבוע הקודם</div>
              </div>
            </td>
            <td width="33%" style="padding:4px;">
              <div style="background:#eff6ff;border-radius:12px;padding:16px;text-align:center;">
                <div style="font-size:11px;color:#6b7280;font-weight:600;margin-bottom:6px;">ROAS Meta</div>
                <div style="font-size:22px;font-weight:800;color:#111827;">{roas:.2f}x</div>
                <div style="font-size:11px;margin-top:4px;color:{color(roas_change)};">
                  {arrow(roas_change)} {abs(roas_change):.1f}% מהשבוע הקודם</div>
              </div>
            </td>
            <td width="33%" style="padding:4px;">
              <div style="background:#fdf4ff;border-radius:12px;padding:16px;text-align:center;">
                <div style="font-size:11px;color:#6b7280;font-weight:600;margin-bottom:6px;">רכישות</div>
                <div style="font-size:22px;font-weight:800;color:#111827;">{purchases:.0f}</div>
                <div style="font-size:11px;margin-top:4px;color:#6b7280;">
                  תקופה קודמת: {date_range[0]}</div>
              </div>
            </td>
          </tr>
        </table>
      </td></tr>

      <!-- DATA TABLE -->
      <tr><td>
        <table width="100%" cellpadding="0" cellspacing="0">
          {ga4_html}
          <tr><td colspan="2" style="padding:16px 24px 8px;font-size:13px;font-weight:700;
              color:#374151;border-top:2px solid #f3f4f6;">📱 קמפייני Meta</td></tr>
          {camp_rows}
          {google_html}
          {flags_html}
        </table>
      </td></tr>

      <!-- FOOTER -->
      <tr><td style="padding:20px 24px;background:#f9fafb;border-top:1px solid #e5e7eb;
          text-align:center;font-size:11px;color:#9ca3af;">
        דוח זה הופק אוטומטית · נתונים: Meta Ads + Google Ads + GA4 דרך Windsor
      </td></tr>

    </table>
  </td></tr>
</table>
</body></html>"""
