"""
agency_overview_builder.py — בונה את index.html (דשבורד סוכנות) אוטומטית
מתעדכן בכל ריצה שבועית יחד עם כל דוחות הלקוחות — ללא צורך בבקשה ידנית.
"""

import json


def roas_class(r):
    return "c-green" if r >= 4 else "c-yellow" if r >= 2 else "c-red"


def fmt(n):
    return "₪" + format(round(n or 0), ",")


def build_agency_overview(clients_summary: dict, date_range: tuple) -> str:
    """
    clients_summary: {
        "crazy": {"name": "Crazy Line", "color": "#EC0E8D", "ga4_revenue": ..., "meta_spend": ...,
                   "meta_roas": ..., "google_spend": ..., "google_roas": ...},
        ...
    }
    """
    order = ["crazy", "pretty", "annabella", "fine", "laster", "aristo"]
    order = [k for k in order if k in clients_summary]

    cards_html = ""
    for key in order:
        c = clients_summary[key]
        total_spend = c["meta_spend"] + c.get("google_spend", 0)
        blended = (c["ga4_revenue"] / total_spend) if total_spend > 0 else 0
        max_spend = max(c["meta_spend"], c.get("google_spend", 0), 1)

        cards_html += f'''<div class="client" style="border-top-color:{c["color"]}">
          <div class="client-top">
            <div class="client-name" style="color:{c["color"]}">{c["name"]}</div>
            <span class="roas-pill {roas_class(blended)}">ROAS {blended:.1f}x</span>
          </div>
          <div style="font-size:11px;color:var(--muted);font-weight:600;margin-bottom:4px">הכנסות GA4 (אתר)</div>
          <div style="font-size:20px;font-weight:800;margin-bottom:14px;color:{c["color"]}">{fmt(c["ga4_revenue"])}</div>
          <div class="pf-rows">
            <div class="pf-row"><div class="pf-tag" style="color:#0866ff">Meta</div>
              <div class="pf-bar"><div class="pf-fill" style="width:{c["meta_spend"]/max_spend*100}%;background:#0866ff"></div></div>
              <div class="pf-val">{fmt(c["meta_spend"])} · {c["meta_roas"]:.1f}x</div></div>
            <div class="pf-row"><div class="pf-tag" style="color:#ea4335">Google</div>
              <div class="pf-bar"><div class="pf-fill" style="width:{c.get("google_spend",0)/max_spend*100}%;background:#ea4335"></div></div>
              <div class="pf-val">{(fmt(c["google_spend"])+" · "+f"{c['google_roas']:.1f}x") if c.get("google_spend",0)>0 else "—"}</div></div>
          </div></div>'''

    html = f'''<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Agency Performance Dashboard</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;700;800;900&display=swap');
  :root {{
    --bg:#f5f7fb; --surface:#fff; --surface2:#f0f3f9; --border:#e4e9f2;
    --text:#1e2640; --text2:#4a5578; --muted:#8a93ad;
    --primary:#5b6ef5; --green:#10b981; --green-bg:#ecfdf5;
    --yellow:#f59e0b; --yellow-bg:#fffbeb; --red:#ef4444; --red-bg:#fef2f2;
    --radius:14px; --font:'Heebo',system-ui,sans-serif;
  }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ background:var(--bg); color:var(--text); font-family:var(--font); font-size:14px; }}
  .header {{ background:var(--surface); border-bottom:1px solid var(--border); padding:14px 28px;
    display:flex; align-items:center; justify-content:space-between; }}
  .brand {{ display:flex; align-items:center; gap:12px; }}
  .logo {{ width:38px; height:38px; background:linear-gradient(135deg,var(--primary),#7c8ef9);
    border-radius:11px; display:flex; align-items:center; justify-content:center; font-weight:800; color:#fff; }}
  .brand h1 {{ font-size:16px; font-weight:800; }}
  .brand-sub {{ font-size:11.5px; color:var(--muted); }}
  .live {{ display:flex; align-items:center; gap:6px; background:var(--green-bg); padding:6px 11px; border-radius:20px; }}
  .live-dot {{ width:7px; height:7px; border-radius:50%; background:var(--green); }}
  .live span {{ font-size:11px; color:var(--green); font-weight:700; }}
  .content {{ padding:24px 28px; max-width:1400px; margin:0 auto; }}
  .banner {{ background:#eef0fe; border:1px solid #c7d2fe; border-radius:10px; padding:10px 14px;
    font-size:12px; color:#3730a3; margin-bottom:16px; font-weight:500; }}
  .clients {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(290px,1fr)); gap:14px; }}
  .client {{ background:var(--surface); border:1px solid var(--border); border-radius:var(--radius);
    padding:19px; box-shadow:0 1px 3px rgba(0,0,0,.05); border-top:3px solid var(--primary); }}
  .client-top {{ display:flex; align-items:center; justify-content:space-between; margin-bottom:15px; }}
  .client-name {{ font-size:15px; font-weight:800; }}
  .roas-pill {{ font-size:12px; font-weight:800; padding:4px 11px; border-radius:20px; }}
  .c-green {{ background:var(--green-bg); color:var(--green); }}
  .c-yellow {{ background:var(--yellow-bg); color:var(--yellow); }}
  .c-red {{ background:var(--red-bg); color:var(--red); }}
  .pf-rows {{ display:flex; flex-direction:column; gap:9px; }}
  .pf-row {{ display:flex; align-items:center; gap:10px; }}
  .pf-tag {{ width:58px; font-size:11px; font-weight:700; flex-shrink:0; }}
  .pf-bar {{ flex:1; height:16px; background:var(--surface2); border-radius:5px; overflow:hidden; }}
  .pf-fill {{ height:100%; border-radius:5px; }}
  .pf-val {{ width:104px; font-size:11px; font-weight:700; text-align:left; flex-shrink:0; }}
  .footer {{ text-align:center; padding:24px; font-size:11.5px; color:var(--muted); }}
</style>
</head>
<body>
<div class="header">
  <div class="brand">
    <div class="logo">AP</div>
    <div><h1>Agency Performance</h1><div class="brand-sub">Meta · Google Ads · GA4 · {len(order)} לקוחות</div></div>
  </div>
  <div class="live"><div class="live-dot"></div><span>מעודכן שבועית</span></div>
</div>
<div class="content">
  <div class="banner">💡 נתוני {date_range[0]} – {date_range[1]} · עדכון אוטומטי כל יום ראשון · לנתונים חיים בזמן אמת, היכנס לדשבורד הלקוח הספציפי</div>
  <div class="clients">{cards_html}</div>
</div>
<div class="footer">Agency Performance · עדכון אוטומטי שבועי · Meta + Google Ads + GA4 דרך Windsor</div>
</body>
</html>'''
    return html
