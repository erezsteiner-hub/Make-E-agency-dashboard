"""
windsor_api.py — מחליף את meta_api.py
מושך Meta Ads + Google Ads + GA4 דרך Windsor REST API
בקריאה אחת לכל פלטפורמה, ללא טוקנים נפרדים.
"""

import os
import requests
from datetime import date, timedelta


WINDSOR_BASE = "https://connectors.windsor.ai/all"


class WindsorClient:
    def __init__(self, api_key: str, meta_account_id: str = None,
                 google_ads_account_id: str = None, ga4_account_id: str = None):
        self.api_key = api_key
        self.meta_account_id = meta_account_id
        self.google_ads_account_id = google_ads_account_id
        self.ga4_account_id = ga4_account_id

    def _fetch(self, fields: list, date_from: str, date_to: str,
               connector: str = "all", account_id: str = None) -> list:
        """שולח בקשה ל-Windsor REST API ומחזיר רשימת שורות"""
        params = {
            "api_key": self.api_key,
            "date_from": date_from,
            "date_to": date_to,
            "fields": ",".join(fields),
            "connector": connector,
        }
        if account_id:
            params["account_id"] = account_id

        resp = requests.get(WINDSOR_BASE, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", data) if isinstance(data, dict) else data

    def get_meta_campaign_data(self, date_from: str, date_to: str) -> list:
        """שולף נתוני Meta Ads ברמת קמפיין"""
        fields = [
            "date", "source", "account_name",
            "campaign", "spend", "impressions", "clicks",
            "conversions", "revenue", "ctr", "cpc",
        ]
        rows = self._fetch(fields, date_from, date_to,
                           connector="facebook", account_id=self.meta_account_id)
        return rows

    def get_google_ads_data(self, date_from: str, date_to: str) -> list:
        """שולף נתוני Google Ads ברמת קמפיין"""
        if not self.google_ads_account_id:
            return []
        fields = [
            "date", "source", "account_name",
            "campaign", "spend", "impressions", "clicks",
            "conversions", "conversions_value", "ctr", "cpc",
        ]
        rows = self._fetch(fields, date_from, date_to,
                           connector="google_ads", account_id=self.google_ads_account_id)
        return rows

    def get_ga4_data(self, date_from: str, date_to: str) -> list:
        """שולף נתוני GA4 — הכנסות אמיתיות מהאתר"""
        if not self.ga4_account_id:
            return []
        fields = [
            "date", "source", "account_name",
            "sessions", "purchase_revenue", "transactions",
            "add_to_carts", "session_default_channel_group",
        ]
        rows = self._fetch(fields, date_from, date_to,
                           connector="googleanalytics4", account_id=self.ga4_account_id)
        return rows


def parse_meta_rows(rows: list) -> dict:
    """ממיר שורות Meta ל-dict קמפיין → נתונים (תואם מבנה report.py הקיים)"""
    campaigns = {}
    for row in rows:
        name = row.get("campaign", "Unknown")
        spend = float(row.get("spend") or 0)
        revenue = float(row.get("revenue") or 0)
        conv = float(row.get("conversions") or 0)
        clicks = int(float(row.get("clicks") or 0))
        impressions = int(float(row.get("impressions") or 0))
        ctr = float(row.get("ctr") or 0)

        if name not in campaigns:
            campaigns[name] = {
                "campaign_name": name,
                "ad_name": name,
                "ad_id": name,
                "adset_name": "",
                "spend": 0, "impressions": 0, "clicks": 0,
                "purchases": 0, "purchase_value": 0,
                "ctr": 0, "frequency": 1.0, "roas": 0, "cpa": None,
            }
        campaigns[name]["spend"] += spend
        campaigns[name]["purchase_value"] += revenue
        campaigns[name]["purchases"] += conv
        campaigns[name]["clicks"] += clicks
        campaigns[name]["impressions"] += impressions
        campaigns[name]["ctr"] = ctr

    # חישוב ROAS ו-CPA
    for c in campaigns.values():
        c["roas"] = (c["purchase_value"] / c["spend"]) if c["spend"] > 0 else 0
        c["cpa"] = (c["spend"] / c["purchases"]) if c["purchases"] > 0 else None

    return campaigns


def parse_google_rows(rows: list) -> dict:
    """מסכם נתוני Google Ads לפי קמפיין"""
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


def parse_ga4_rows(rows: list) -> dict:
    """מסכם נתוני GA4 לפי ערוץ"""
    channels = {}
    total = {"revenue": 0, "transactions": 0, "sessions": 0}
    for row in rows:
        ch = row.get("session_default_channel_group", "Other")
        rev = float(row.get("purchase_revenue") or 0)
        trans = float(row.get("transactions") or 0)
        sess = float(row.get("sessions") or 0)

        if ch not in channels:
            channels[ch] = {"revenue": 0, "transactions": 0, "sessions": 0}
        channels[ch]["revenue"] += rev
        channels[ch]["transactions"] += trans
        channels[ch]["sessions"] += sess

        total["revenue"] += rev
        total["transactions"] += trans
        total["sessions"] += sess

    return {"channels": channels, "total": total}
