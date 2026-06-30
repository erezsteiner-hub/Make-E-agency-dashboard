"""
insights_generator.py — מייצר תובנות אוטומטיות (ללא תלות ב-AI)
לוגיקת תבניות מבוססת חוקים — עקבית, חינמית, אוטומטית לחלוטין.
"""


def generate_insights(current: dict, previous: dict, google_data: dict = None,
                       google_previous: dict = None, ga4_data: dict = None,
                       ga4_previous: dict = None) -> list:
    """
    מייצר רשימת תובנות מקצועיות (ללא רגש) על בסיס כללים.
    מחזיר: [{"type": "red"|"yellow"|"green"|"blue", "title": str, "body": str}]
    """
    insights = []

    # ===== חישובי בסיס =====
    total_spend = sum(d["spend"] for d in current.values())
    total_value = sum(d["purchase_value"] for d in current.values())
    overall_roas = (total_value / total_spend) if total_spend > 0 else 0

    prev_spend = sum(d["spend"] for d in previous.values()) if previous else 0
    prev_value = sum(d["purchase_value"] for d in previous.values()) if previous else 0
    prev_roas = (prev_value / prev_spend) if prev_spend > 0 else 0

    # ===== 1. קמפיינים מפסידים (ROAS < 1.5, spend > 500) =====
    losing = [c for c in current.values() if c["spend"] > 500 and c["roas"] < 1.5]
    if losing:
        total_waste = sum(c["spend"] for c in losing)
        names = ", ".join(c["campaign_name"] for c in losing[:3])
        insights.append({
            "type": "red",
            "title": "קמפיינים בתשואה נמוכה:",
            "body": f"{names} — סך הוצאה {total_waste:,.0f}₪ עם ROAS ממוצע מתחת ל-1.5x. "
                    f"מומלץ לבחון עצירה או אופטימיזציה."
        })

    # ===== 2. קמפיינים מצטיינים (ROAS > 8, spend > 500) =====
    winning = sorted([c for c in current.values() if c["spend"] > 500 and c["roas"] > 8],
                      key=lambda x: -x["roas"])
    if winning:
        top = winning[0]
        insights.append({
            "type": "blue",
            "title": "הזדמנות הגדלת תקציב:",
            "body": f"{top['campaign_name']} מציג ROAS {top['roas']:.1f}x על הוצאה של "
                    f"{top['spend']:,.0f}₪. מומלץ לבחון הגדלת תקציב של 15-20%."
        })

    # ===== 3. השוואת ROAS לתקופה קודמת =====
    if prev_roas > 0:
        roas_change = ((overall_roas - prev_roas) / prev_roas) * 100
        if roas_change <= -15:
            insights.append({
                "type": "red",
                "title": "ירידה משמעותית ב-ROAS:",
                "body": f"ROAS ירד מ-{prev_roas:.1f}x ל-{overall_roas:.1f}x "
                        f"({roas_change:+.1f}%) לעומת התקופה הקודמת."
            })
        elif roas_change >= 15:
            insights.append({
                "type": "green",
                "title": "שיפור ב-ROAS:",
                "body": f"ROAS עלה מ-{prev_roas:.1f}x ל-{overall_roas:.1f}x "
                        f"({roas_change:+.1f}%) לעומת התקופה הקודמת."
            })

    # ===== 4. השוואת הוצאות =====
    if prev_spend > 0:
        spend_change = ((total_spend - prev_spend) / prev_spend) * 100
        if abs(spend_change) >= 25:
            direction = "עלייה" if spend_change > 0 else "ירידה"
            insights.append({
                "type": "yellow",
                "title": f"{direction} משמעותית בהוצאות:",
                "body": f"הוצאות פרסום {direction} ב-{abs(spend_change):.1f}% "
                        f"לעומת התקופה הקודמת ({prev_spend:,.0f}₪ → {total_spend:,.0f}₪)."
            })

    # ===== 5. Google Brand vs Non-Brand =====
    if google_data:
        g_spend = sum(c["spend"] for c in google_data.values())
        brand_campaigns = [c for c in google_data.values()
                           if any(k in c["name"].lower() for k in ["brand", "ברנד"])]
        nonbrand_campaigns = [c for c in google_data.values()
                              if not any(k in c["name"].lower() for k in ["brand", "ברנד"])]

        if brand_campaigns:
            b_spend = sum(c["spend"] for c in brand_campaigns)
            b_value = sum(c["value"] for c in brand_campaigns)
            b_roas = (b_value / b_spend) if b_spend > 0 else 0
            if b_roas > 30:
                insights.append({
                    "type": "blue",
                    "title": "ביקוש מותג גבוה:",
                    "body": f"קמפייני Brand ב-Google מציגים ROAS {b_roas:.0f}x. "
                            f"מומלץ לבחון הרחבה מבוקרת לתפיסת ביקוש נוסף."
                })
        elif g_spend > 0:
            insights.append({
                "type": "blue",
                "title": "חסר קמפיין Brand:",
                "body": "אין קמפיין Brand פעיל ב-Google Ads. הוספתו עשויה לתפוס "
                        "ביקוש מותג קיים בעלות נמוכה יחסית."
            })

    # ===== 6. GA4 funnel — שיעור המרה נמוך =====
    if ga4_data:
        sessions = ga4_data.get("total", {}).get("sessions", 0)
        transactions = ga4_data.get("total", {}).get("transactions", 0)
        if sessions > 1000:
            cr = (transactions / sessions) * 100
            if cr < 1.0:
                insights.append({
                    "type": "yellow",
                    "title": "שיעור המרה נמוך:",
                    "body": f"שיעור המרה עומד על {cr:.2f}% ({transactions:.0f} עסקאות "
                            f"מתוך {sessions:,.0f} סשנים). מומלץ לבחון את חוויית המשתמש "
                            f"ותהליך ה-Checkout."
                })

    # ===== 7. ROAS משולב מול יעד דינמי (ברירת מחדל: ROAS ממוצע + 20%) =====
    if not insights:
        insights.append({
            "type": "blue",
            "title": "ביצועים יציבים:",
            "body": f"ROAS משולב {overall_roas:.1f}x ללא חריגות משמעותיות בתקופה זו."
        })

    return insights[:5]  # מקסימום 5 תובנות


def generate_period_comparison(current: dict, previous: dict, ga4_data: dict = None,
                                ga4_previous: dict = None) -> dict:
    """מייצר נתוני השוואה לתקופה קודמת לתצוגה ב-HTML"""
    total_spend = sum(d["spend"] for d in current.values())
    total_value = sum(d["purchase_value"] for d in current.values())
    total_purchases = sum(d["purchases"] for d in current.values())
    overall_roas = (total_value / total_spend) if total_spend > 0 else 0

    prev_spend = sum(d["spend"] for d in previous.values()) if previous else 0
    prev_value = sum(d["purchase_value"] for d in previous.values()) if previous else 0
    prev_purchases = sum(d["purchases"] for d in previous.values()) if previous else 0
    prev_roas = (prev_value / prev_spend) if prev_spend > 0 else 0

    def pct(curr, prev):
        if not prev:
            return None
        return ((curr - prev) / prev) * 100

    return {
        "spend": {"current": total_spend, "previous": prev_spend, "change": pct(total_spend, prev_spend)},
        "roas": {"current": overall_roas, "previous": prev_roas, "change": pct(overall_roas, prev_roas)},
        "purchases": {"current": total_purchases, "previous": prev_purchases, "change": pct(total_purchases, prev_purchases)},
    }
