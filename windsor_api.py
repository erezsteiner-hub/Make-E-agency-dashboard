"""
windsor_api.py — שליפת נתונים מ-Windsor REST API
תוקן עם הפרמטרים הנכונים שגילינו:
- endpoint ספציפי לכל connector (לא /all)
- filter=[["account_id","eq",ID]] לסינון לפי חשבון (לא account_id ישירות)
- GA4 דורש סינון בצד הלקוח (לא תומך ב-filter על account_id בשרת)
"""

import requests
from datetime import date, timedelta
import json


WINDSOR_BASE = "https://connectors.windsor.ai"


class WindsorClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def _fetch(self, connector: str, fields: list, date_from: str, date_to: str,
               account_id: str = None, use_server_filter: bool = True, retries: int = 2) -> list:
        params = {
            "api_key": self.api_key,
            "date_from": date_from,
            "date_to": date_to,
            "fields": ",".join(fields),
        }
        if account_id and use_server_filter:
            params["filter"] = json.dumps([["account_id", "eq", account_id]])

        url = f"{WINDSOR_BASE}/{connector}"

        last_error = None
        for attempt in range(retries + 1):
            try:
                resp = requests.get(url, params=params, timeout=60)
                resp.raise_for_status()
                data = resp.json()
                rows = data.get("data", data) if isinstance(data, dict) else data

                # סינון בטיחות בצד הלקוח
                if account_id:
                    target = "".join(c for c in str(account_id) if c.isdigit())
                    filtered = [r for r in rows if "".join(c for c in str(r.get("account_id", "")) if c.isdigit()) == target]
                    if filtered:
                        return filtered
                return rows
            except requests.exceptions.RequestException as e:
                last_error = e
                if attempt < retries:
                    continue
        raise last_error

    def get_meta_campaign_data(self, account_id: str, date_from: str, date_to: str) -> list:
        return self._fetch("facebook",
            ["account_id", "campaign", "spend", "impressions", "clicks",
             "actions_omni_purchase", "action_values_omni_purchase"],
            date_from, date_to, account_id)

    def get_google_ads_data(self, account_id: str, date_from: str, date_to: str) -> list:
        if not account_id:
            return []
        return self._fetch("google_ads",
            ["account_id", "campaign", "spend", "clicks", "conversions", "conversions_value"],
            date_from, date_to, account_id)

    def get_ga4_total(self, account_id: str, date_from: str, date_to: str) -> list:
        if not account_id:
            return []
        return self._fetch("googleanalytics4",
            ["account_id", "sessions", "purchase_revenue", "transactions", "add_to_carts", "checkouts", "totalusers"],
            date_from, date_to, account_id, use_server_filter=False)

    def get_ga4_channels(self, account_id: str, date_from: str, date_to: str) -> list:
        if not account_id:
            return []
        return self._fetch("googleanalytics4",
            ["account_id", "session_default_channel_group", "purchase_revenue", "transactions"],
            date_from, date_to, account_id, use_server_filter=False)

    def get_ga4_daily(self, account_id: str, date_from: str, date_to: str) -> list:
        if not account_id:
            return []
        return self._fetch("googleanalytics4",
            ["account_id", "date", "purchase_revenue", "sessions"],
            date_from, date_to, account_id, use_server_filter=False)

    def get_ga4_products(self, account_id: str, date_from: str, date_to: str) -> list:
        """דוח Best Seller — טופ מוצרים נמכרים"""
        if not account_id:
            return []
        return self._fetch("googleanalytics4",
            ["account_id", "item_name", "item_revenue", "items_purchased"],
            date_from, date_to, account_id, use_server_filter=False)

    def get_ga4_campaigns(self, account_id: str, date_from: str, date_to: str) -> list:
        """דוח טופ קמפיינים לפי GA4"""
        if not account_id:
            return []
        return self._fetch("googleanalytics4",
            ["account_id", "campaign_name", "purchase_revenue", "transactions", "sessions"],
            date_from, date_to, account_id, use_server_filter=False)

    def get_ga4_new_vs_returning(self, account_id: str, date_from: str, date_to: str) -> list:
        """לקוחות חדשים מול חוזרים"""
        if not account_id:
            return []
        return self._fetch("googleanalytics4",
            ["account_id", "new_vs_returning", "sessions", "totalusers", "purchase_revenue", "transactions"],
            date_from, date_to, account_id, use_server_filter=False)


def parse_meta_rows(rows: list) -> dict:
    """ממיר שורות Meta ל-dict קמפיין -> נתונים מעובדים"""
    campaigns = {}
    for row in rows:
        name = row.get("campaign", "Unknown")
        spend = float(row.get("spend") or 0)
        revenue = float(row.get("action_values_omni_purchase") or 0)
        purch = float(row.get("actions_omni_purchase") or 0)

        if name not in campaigns:
            campaigns[name] = {
                "campaign_name": name, "spend": 0, "purchase_value": 0, "purchases": 0,
            }
        campaigns[name]["spend"] += spend
        campaigns[name]["purchase_value"] += revenue
        campaigns[name]["purchases"] += purch

    for c in campaigns.values():
        c["roas"] = (c["purchase_value"] / c["spend"]) if c["spend"] > 0 else 0
        c["cpa"] = (c["spend"] / c["purchases"]) if c["purchases"] > 0 else None

    return campaigns


def parse_google_rows(rows: list) -> dict:
    campaigns = {}
    for row in rows:
        name = row.get("campaign", "Unknown")
        spend = float(row.get("spend") or 0)
        value = float(row.get("conversions_value") or 0)
        conv = float(row.get("conversions") or 0)

        if name not in campaigns:
            campaigns[name] = {"name": name, "spend": 0, "value": 0, "conv": 0}
        campaigns[name]["spend"] += spend
        campaigns[name]["value"] += value
        campaigns[name]["conv"] += conv

    for c in campaigns.values():
        c["roas"] = (c["value"] / c["spend"]) if c["spend"] > 0 else 0

    return campaigns


def parse_ga4_total(rows: list) -> dict:
    total = {"revenue": 0, "transactions": 0, "sessions": 0, "atc": 0, "checkouts": 0}
    for row in rows:
        total["revenue"] += float(row.get("purchase_revenue") or 0)
        total["transactions"] += float(row.get("transactions") or 0)
        total["sessions"] += float(row.get("sessions") or 0)
        total["atc"] += float(row.get("add_to_carts") or 0)
        total["checkouts"] += float(row.get("checkouts") or 0)
    return {"total": total}


def parse_ga4_channels(rows: list) -> dict:
    channels = {}
    for row in rows:
        ch = row.get("session_default_channel_group", "Other")
        rev = float(row.get("purchase_revenue") or 0)
        trans = float(row.get("transactions") or 0)
        if ch not in channels:
            channels[ch] = {"revenue": 0, "transactions": 0}
        channels[ch]["revenue"] += rev
        channels[ch]["transactions"] += trans
    return {"channels": channels}


def parse_ga4_products(rows: list, top_n: int = 10) -> list:
    """טופ מוצרים לפי הכנסה (Best Seller)"""
    products = {}
    for row in rows:
        name = row.get("item_name")
        if not name or name == "(not set)":
            continue
        rev = float(row.get("item_revenue") or 0)
        qty = float(row.get("items_purchased") or 0)
        if name not in products:
            products[name] = {"name": name, "revenue": 0, "qty": 0}
        products[name]["revenue"] += rev
        products[name]["qty"] += qty
    ranked = sorted([p for p in products.values() if p["revenue"] > 0],
                    key=lambda x: -x["revenue"])[:top_n]
    return ranked


# ערכים טכניים שאינם קמפיינים אמיתיים
_EXCLUDE_CAMPAIGNS = {"(not set)", "(organic)", "(direct)", "(referral)",
                      "(cross-network)", "(ai-assistant)", "(other)", "direct", "",
                      "{{campaign.name}}"}


def parse_ga4_campaigns(rows: list, top_n: int = 10) -> list:
    """טופ קמפיינים לפי הכנסה ב-GA4"""
    campaigns = {}
    for row in rows:
        name = row.get("campaign_name")
        if not name or name in _EXCLUDE_CAMPAIGNS:
            continue
        rev = float(row.get("purchase_revenue") or 0)
        trans = float(row.get("transactions") or 0)
        sess = float(row.get("sessions") or 0)
        if name not in campaigns:
            campaigns[name] = {"name": name, "revenue": 0, "transactions": 0, "sessions": 0}
        campaigns[name]["revenue"] += rev
        campaigns[name]["transactions"] += trans
        campaigns[name]["sessions"] += sess
    ranked = sorted([c for c in campaigns.values() if c["revenue"] > 0],
                    key=lambda x: -x["revenue"])[:top_n]
    return ranked


def parse_ga4_new_vs_returning(rows: list) -> dict:
    """מפרק לקוחות חדשים מול חוזרים. מחזיר None אם אין נתונים (fallback עדין)."""
    new_data = {"sessions": 0, "users": 0, "revenue": 0, "transactions": 0}
    returning_data = {"sessions": 0, "users": 0, "revenue": 0, "transactions": 0}
    for row in rows:
        type_val = str(row.get("new_vs_returning") or "").lower()
        target = new_data if type_val == "new" else returning_data if type_val == "returning" else None
        if target is None:
            continue
        target["sessions"] += float(row.get("sessions") or 0)
        target["users"] += float(row.get("totalusers") or 0)
        target["revenue"] += float(row.get("purchase_revenue") or 0)
        target["transactions"] += float(row.get("transactions") or 0)

    if (new_data["sessions"] + returning_data["sessions"]) <= 0:
        return None
    return {"new": new_data, "returning": returning_data}
