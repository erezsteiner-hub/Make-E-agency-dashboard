"""
html_report_builder.py — בונה את דוח ה-HTML המעוצב (כמו crazy_report.html)
באופן אוטומטי מלא, כולל גרפים, תובנות והשוואות.
"""

import json
from insights_generator import generate_insights, generate_period_comparison


CHANNEL_COLORS = {
    "Paid Search": "#ea4335", "חיפוש בתשלום": "#ea4335",
    "Paid Social": "#0866ff", "סושיאל בתשלום": "#0866ff",
    "Paid Shopping": "#34a853", "שופינג בתשלום": "#34a853",
    "Organic Search": "#10b981", "חיפוש אורגני": "#10b981",
    "Organic Social": "#8b5cf6", "סושיאל אורגני": "#8b5cf6",
    "Organic Shopping": "#059669", "שופינג אורגני": "#059669",
    "Direct": "#6b7280", "ישיר": "#6b7280",
    "Email": "#f59e0b", "אימייל": "#f59e0b",
    "SMS": "#ec4899", "Referral": "#06b6d4", "הפניות": "#06b6d4",
    "Cross-network": "#a78bfa", "Unassigned": "#cbd5e1",
}

TYPE_ICONS = {"green": "🏆", "red": "⚠️", "yellow": "📊", "blue": "💡"}


def fmt(n):
    return "₪" + format(round(n or 0), ",")


def fmt_pct(v):
    if v is None:
        return "אין נתון להשוואה"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.1f}%"


def roas_class(r):
    return "c-green" if r >= 4 else "c-yellow" if r >= 2 else "c-red"


def build_full_report(client_config: dict, current: dict, previous: dict,
                       google_data: dict, ga4_data: dict, ga4_channels: dict,
                       ga4_daily: list, date_range: tuple, prev_date_range: tuple) -> str:
    """
    בונה דוח HTML מלא ומעוצב — KPIs, גרפים, Brand/Non-Brand, תובנות, השוואה.
    client_config: {"name", "color", "color2", "font", "font_url", "bg", "surface2", "border", "text", "text2", "muted", "logo"}
    """
    name = client_config["name"]
    color = client_config["color"]
    color2 = client_config["color2"]
    font = client_config["font"]
    font_url = client_config["font_url"]

    # ===== חישובים =====
    total_spend = sum(d["spend"] for d in current.values())
    total_value = sum(d["purchase_value"] for d in current.values())
    total_purchases = sum(d["purchases"] for d in current.values())
    google_spend = sum(c["spend"] for c in google_data.values()) if google_data else 0
    google_value = sum(c["value"] for c in google_data.values()) if google_data else 0
    google_roas = (google_value / google_spend) if google_spend > 0 else 0
    meta_roas = (total_value / total_spend) if total_spend > 0 else 0

    ga4_total = ga4_data.get("total", {}) if ga4_data else {}
    ga4_revenue = ga4_total.get("revenue", 0)
    ga4_transactions = ga4_total.get("transactions", 0)
    ga4_sessions = ga4_total.get("sessions", 0)
    ga4_atc = ga4_total.get("atc", 0)

    all_spend = total_spend + google_spend
    blended_roas = (ga4_revenue / all_spend) if all_spend > 0 else 0
    cr = (ga4_transactions / ga4_sessions * 100) if ga4_sessions > 0 else 0

    # ===== תובנות + השוואה (אוטומטי) =====
    insights = generate_insights(current, previous, google_data, None, ga4_data, None)
    comparison = generate_period_comparison(current, previous, ga4_data, None)

    # ===== Brand/Non-Brand =====
    brand_spend = brand_value = nonbrand_spend = nonbrand_value = 0
    if google_data:
        for c in google_data.values():
            is_brand = any(k in c["name"].lower() for k in ["brand", "ברנד"])
            if is_brand:
                brand_spend += c["spend"]; brand_value += c["value"]
            else:
                nonbrand_spend += c["spend"]; nonbrand_value += c["value"]
    brand_roas = (brand_value / brand_spend) if brand_spend > 0 else 0
    nonbrand_roas = (nonbrand_value / nonbrand_spend) if nonbrand_spend > 0 else 0

    bn_html = ""
    if google_spend > 0:
        bn_html = f'''<div class="sec">🏷️ Google Ads — Brand מול Non-Brand</div>
        <div class="bn-grid">
          <div class="bn-card bn-brand"><div class="bn-tag">🟣 Brand</div>
            <div class="bn-roas">{f"{brand_roas:.1f}x" if brand_spend > 0 else "—"}</div>
            <div class="bn-detail">{f"{fmt(brand_spend)} → {fmt(brand_value)}" if brand_spend > 0 else "אין קמפיין Brand"}</div></div>
          <div class="bn-card bn-nonbrand"><div class="bn-tag">🔵 Non-Brand</div>
            <div class="bn-roas">{nonbrand_roas:.1f}x</div>
            <div class="bn-detail">{fmt(nonbrand_spend)} → {fmt(nonbrand_value)}</div></div>
        </div>'''

    # ===== ערוצים =====
    channels = ga4_channels.get("channels", {}) if ga4_channels else {}
    ch_sorted = sorted(channels.items(), key=lambda x: -x[1]["revenue"]) if channels else []
    ch_max = ch_sorted[0][1]["revenue"] if ch_sorted else 1
    ch_html = ""
    for ch_name, vals in ch_sorted:
        if vals["revenue"] <= 0:
            continue
        col = CHANNEL_COLORS.get(ch_name, "#94a3b8")
        w = vals["revenue"] / ch_max * 100
        ch_html += f'''<div class="ch-row"><div class="ch-name">{ch_name}</div>
          <div class="ch-track"><div class="ch-fill" style="width:{w}%;background:{col}"></div></div>
          <div class="ch-val">{fmt(vals["revenue"])}</div></div>'''

    # ===== טבלת Meta =====
    meta_rows = ""
    for c in sorted(current.values(), key=lambda x: -x["spend"])[:12]:
        meta_rows += f'''<tr><td>{c["campaign_name"]}</td><td class="num">{fmt(c["spend"])}</td>
          <td><span class="chip {roas_class(c["roas"])}">{c["roas"]:.2f}x</span></td>
          <td class="num">{c["purchases"]:.0f}</td></tr>'''

    # ===== טבלת Google =====
    google_section = ""
    if google_data:
        g_rows = ""
        for c in sorted(google_data.values(), key=lambda x: -x["spend"]):
            is_brand = any(k in c["name"].lower() for k in ["brand", "ברנד"])
            tag = "Brand" if is_brand else "Non-Brand"
            tcls = "tag-brand" if is_brand else "tag-nonbrand"
            g_rows += f'''<tr><td>{c["name"]}</td><td><span class="tag {tcls}">{tag}</span></td>
              <td class="num">{fmt(c["spend"])}</td><td><span class="chip {roas_class(c["roas"])}">{c["roas"]:.1f}x</span></td></tr>'''
        google_section = f'''<div class="sec">📋 קמפייני Google Ads</div>
        <div class="tbl-card"><div class="tbl-scroll"><table>
          <thead><tr><th>קמפיין</th><th>סוג</th><th>הוצאה</th><th>ROAS</th></tr></thead>
          <tbody>{g_rows}</tbody></table></div></div>'''

    # ===== סיכום תקופה (אוטומטי, מבוסס תבנית) =====
    summary_text = (
        f"בתקופה {date_range[0]}–{date_range[1]} הושקעו <strong>{fmt(all_spend)}</strong> "
        f"בפרסום (Meta + Google). הכנסות האתר לפי GA4 עמדו על <strong>{fmt(ga4_revenue)}</strong> "
        f"— ROAS משולב של <strong>{blended_roas:.1f}x</strong>. "
        f"ב-Meta, ROAS עמד על {meta_roas:.1f}x. "
        + (f"ב-Google, ROAS עמד על {google_roas:.1f}x." if google_spend > 0 else "")
    )

    # ===== כרטיסי השוואה =====
    def comp_card(label, curr_fmt, prev_fmt, change):
        color_style = "color:#10b981" if (change or 0) >= 0 else "color:#ef4444"
        return f'''<div class="card" style="text-align:center">
      <div style="font-size:11px;color:var(--muted);font-weight:600;margin-bottom:6px">{label}</div>
      <div style="font-size:20px;font-weight:800">{curr_fmt}</div>
      <div style="font-size:12px;color:var(--muted);margin-top:4px">תקופה קודמת: {prev_fmt}</div>
      <div style="font-size:11px;font-weight:700;margin-top:4px;{color_style}">{fmt_pct(change)}</div>
    </div>'''

    compare_html = (
        comp_card("הוצאות פרסום", fmt(comparison["spend"]["current"]), fmt(comparison["spend"]["previous"]), comparison["spend"]["change"]) +
        comp_card("ROAS", f"{comparison['roas']['current']:.1f}x", f"{comparison['roas']['previous']:.1f}x", comparison["roas"]["change"]) +
        comp_card("רכישות", f"{comparison['purchases']['current']:.0f}", f"{comparison['purchases']['previous']:.0f}", comparison["purchases"]["change"])
    )

    # ===== תובנות =====
    insights_html = ""
    for ins in insights:
        icon = TYPE_ICONS.get(ins["type"], "💡")
        insights_html += f'<div class="alert a-{ins["type"]}">{icon} <div><b>{ins["title"]}</b> {ins["body"]}</div></div>\n'

    # ===== Daily chart data =====
    daily_dates = [d.get("date", "")[-5:] for d in ga4_daily] if ga4_daily else []
    daily_revenue = [d.get("purchase_revenue", 0) for d in ga4_daily] if ga4_daily else []

    html = f'''<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{name} — דוח ביצועים</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  @import url('{font_url}');
  :root {{
    --bg:{client_config["bg"]}; --surface:#fff; --surface2:{client_config["surface2"]}; --border:{client_config["border"]};
    --text:{client_config["text"]}; --text2:{client_config["text2"]}; --muted:{client_config["muted"]};
    --green:#10b981; --green-bg:#ecfdf5; --yellow:#f59e0b; --yellow-bg:#fffbeb;
    --red:#ef4444; --red-bg:#fef2f2; --blue:#5b6ef5; --blue-bg:#eef0fe;
    --brand:#7c3aed; --nonbrand:#06b6d4; --client:{color}; --client2:{color2};
    --radius:16px; --font:'{font}',system-ui,sans-serif;
  }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ background:var(--bg); color:var(--text); font-family:var(--font); font-size:14px; line-height:1.5; }}
  .hero {{ background:linear-gradient(135deg,var(--client),var(--client2)); padding:32px; color:#fff; position:relative; overflow:hidden; }}
  .hero-top {{ display:flex; align-items:center; gap:16px; margin-bottom:24px; position:relative; z-index:2; }}
  .hero-logo {{ width:54px; height:54px; background:rgba(255,255,255,.2); border:2px solid rgba(255,255,255,.4); border-radius:14px; display:flex; align-items:center; justify-content:center; font-weight:800; font-size:20px; }}
  .hero h1 {{ font-size:24px; font-weight:800; letter-spacing:-.5px; }}
  .hero-sub {{ font-size:13px; opacity:.9; margin-top:2px; }}
  .hero-stats {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:14px; }}
  .hs {{ background:rgba(255,255,255,.15); border:1px solid rgba(255,255,255,.2); border-radius:14px; padding:16px 18px; }}
  .hs-label {{ font-size:11.5px; opacity:.85; font-weight:600; margin-bottom:6px; }}
  .hs-val {{ font-size:26px; font-weight:800; letter-spacing:-.8px; }}
  .hs-sub {{ font-size:11px; opacity:.8; margin-top:5px; }}
  .wrap {{ max-width:1200px; margin:0 auto; padding:26px 32px; }}
  .sec {{ font-size:13px; font-weight:700; color:var(--text2); text-transform:uppercase; letter-spacing:.5px; margin:30px 0 15px; }}
  .sec:first-child {{ margin-top:0; }}
  .card {{ background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); padding:22px; box-shadow:0 1px 3px rgba(0,0,0,.05); }}
  .grid-2 {{ display:grid; grid-template-columns:1.6fr 1fr; gap:16px; }}
  @media(max-width:820px){{ .grid-2 {{ grid-template-columns:1fr; }} }}
  .chart-box {{ position:relative; height:280px; }}
  .chart-box.sm {{ height:240px; }}
  .bn-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; max-width:560px; }}
  .bn-card {{ background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); padding:18px 20px; border-right:4px solid; }}
  .bn-brand {{ border-right-color:var(--brand); }} .bn-nonbrand {{ border-right-color:var(--nonbrand); }}
  .bn-tag {{ font-size:12px; font-weight:700; margin-bottom:8px; }}
  .bn-brand .bn-tag {{ color:var(--brand); }} .bn-nonbrand .bn-tag {{ color:var(--nonbrand); }}
  .bn-roas {{ font-size:30px; font-weight:800; }}
  .bn-brand .bn-roas {{ color:var(--brand); }} .bn-nonbrand .bn-roas {{ color:var(--nonbrand); }}
  .bn-detail {{ font-size:12px; color:var(--muted); margin-top:6px; font-weight:600; }}
  .ch-row {{ display:flex; align-items:center; gap:12px; margin-bottom:12px; }}
  .ch-name {{ width:115px; font-size:12px; font-weight:600; flex-shrink:0; }}
  .ch-track {{ flex:1; height:20px; background:var(--surface2); border-radius:6px; overflow:hidden; }}
  .ch-fill {{ height:100%; border-radius:6px; }}
  .ch-val {{ width:95px; font-size:11.5px; font-weight:700; text-align:left; }}
  .tbl-card {{ background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); overflow:hidden; }}
  .tbl-scroll {{ overflow-x:auto; }}
  table {{ width:100%; border-collapse:collapse; min-width:420px; }}
  th {{ background:var(--surface2); padding:12px 15px; font-size:11px; color:var(--text2); font-weight:700; text-align:right; }}
  td {{ padding:11px 15px; border-top:1px solid var(--border); font-size:13px; }}
  .num {{ font-variant-numeric:tabular-nums; font-weight:600; }}
  .chip {{ display:inline-block; font-size:11px; font-weight:700; padding:3px 9px; border-radius:6px; }}
  .c-green {{ background:var(--green-bg); color:var(--green); }} .c-yellow {{ background:var(--yellow-bg); color:var(--yellow); }} .c-red {{ background:var(--red-bg); color:var(--red); }}
  .tag {{ display:inline-block; padding:3px 9px; border-radius:6px; font-size:11px; font-weight:700; }}
  .tag-brand {{ background:#7c3aed18; color:var(--brand); }} .tag-nonbrand {{ background:#06b6d418; color:var(--nonbrand); }}
  .alert {{ border-radius:12px; padding:14px 16px; font-size:13px; line-height:1.55; margin-bottom:11px; display:flex; gap:11px; }}
  .a-red {{ background:var(--red-bg); border:1px solid #fecaca; color:#991b1b; }}
  .a-yellow {{ background:var(--yellow-bg); border:1px solid #fde68a; color:#92400e; }}
  .a-green {{ background:var(--green-bg); border:1px solid #a7f3d0; color:#065f46; }}
  .a-blue {{ background:var(--blue-bg); border:1px solid #c7d2fe; color:#3730a3; }}
  .footer {{ text-align:center; padding:26px; font-size:11.5px; color:var(--muted); border-top:1px solid var(--border); margin-top:36px; }}
</style>
</head>
<body>
<div class="hero">
  <div class="hero-top">
    <div class="hero-logo">{client_config.get("initials", "")}</div>
    <div><h1>{name}</h1><div class="hero-sub">דוח ביצועים שבועי · Meta · Google Ads · GA4 · {date_range[0]} – {date_range[1]}</div></div>
  </div>
  <div class="hero-stats">
    <div class="hs"><div class="hs-label">הכנסות מהאתר (GA4)</div><div class="hs-val">{fmt(ga4_revenue)}</div><div class="hs-sub">{ga4_transactions:.0f} עסקאות</div></div>
    <div class="hs"><div class="hs-label">סך הוצאות פרסום</div><div class="hs-val">{fmt(all_spend)}</div><div class="hs-sub">Meta + Google</div></div>
    <div class="hs"><div class="hs-label">ROAS משולב</div><div class="hs-val">{blended_roas:.1f}x</div><div class="hs-sub">הכנסות ÷ הוצאות</div></div>
    <div class="hs"><div class="hs-label">סשנים</div><div class="hs-val">{ga4_sessions/1000:.1f}K</div><div class="hs-sub">{cr:.2f}% המרה</div></div>
  </div>
</div>

<div class="wrap">
  <div class="sec">📝 סיכום תקופה</div>
  <div class="card" style="margin-bottom:20px;line-height:1.8">{summary_text}</div>

  <div class="sec">📊 השוואה לתקופה קודמת ({prev_date_range[0]}–{prev_date_range[1]})</div>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:20px">{compare_html}</div>

  <div class="sec">📈 מגמת ביצועים יומית</div>
  <div class="card"><div class="chart-box"><canvas id="trendChart"></canvas></div></div>

  {bn_html}

  <div class="sec">💰 הכנסות לפי ערוץ (GA4)</div>
  <div class="card">{ch_html}</div>

  <div class="sec">📋 קמפייני Meta מובילים</div>
  <div class="tbl-card"><div class="tbl-scroll"><table>
    <thead><tr><th>קמפיין</th><th>הוצאה</th><th>ROAS</th><th>רכישות</th></tr></thead>
    <tbody>{meta_rows}</tbody></table></div></div>

  {google_section}

  <div class="sec">🎯 תובנות והמלצות</div>
  {insights_html}
</div>

<div class="footer">{name} · דוח אוטומטי שבועי · Meta + Google Ads + GA4 דרך Windsor</div>

<script>
new Chart(document.getElementById('trendChart'), {{
  type:'line',
  data:{{labels:{json.dumps(daily_dates)},datasets:[{{label:'הכנסות GA4',data:{json.dumps(daily_revenue)},
    borderColor:'{color}',backgroundColor:'{color}1a',borderWidth:2.5,tension:0.35,pointRadius:0,fill:true}}]}},
  options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}},
    tooltip:{{rtl:true,callbacks:{{label:c=>'₪'+c.parsed.y.toLocaleString()}}}}}},
    scales:{{y:{{position:'right',ticks:{{callback:v=>'₪'+(v/1000).toFixed(0)+'K'}}}},x:{{grid:{{display:false}}}}}}}}
}});
</script>
</body>
</html>'''
    return html
