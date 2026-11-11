#!/usr/bin/env python3
"""
MAKE-E performance dashboards (מדד ביצועים) – scheduled build for client links.

Runs in GitHub Actions 3x/day:
  1. pulls Windsor (Meta, Google Ads, GA4, Shopify) incrementally into a local cache (actions/cache keeps it)
  2. builds each client's page with build.py + template.html (same as the performance-dashboard skill)
  3. gzips + encrypts each page with a key derived from the client's secret token (AES-256-GCM)
     and writes out/d/<id>.bin  – the file is public, its content is unreadable without the token
  4. emails the client links to GMAIL_USER whenever a link changes (first run / version bump)

The token is HMAC(secret, client|version); secret = DASH_SECRET (if set) else WINDSOR_API_KEY.
A client only ever receives its own token, which only decrypts its own file.

Usage: python3 pipeline.py [--clients crazy,pablo] [--out ../_dash_out] [--cache ../_dash_cache]
"""
import argparse, base64, collections, datetime as dt, gzip, hashlib, hmac, json, os, re, smtplib, subprocess, sys, time
from email.mime.text import MIMEText
from zoneinfo import ZoneInfo

import threading
from concurrent.futures import ThreadPoolExecutor

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
WINDSOR = "https://connectors.windsor.ai"
WORKER = "https://agency-live-data.erezsteiner.workers.dev"
LOADER_URL = "https://erezsteiner-hub.github.io/Make-E-agency-dashboard/r/"
IL = ZoneInfo("Asia/Jerusalem")
API_KEY = os.environ.get("WINDSOR_API_KEY", "")
LOG = {"errors": [], "steps": [], "deferred": 0}
DEADLINE = [time.time() + 45 * 60]          # stop back-filling history after this; the rest comes next run
SEM = threading.Semaphore(8)               # max concurrent Windsor requests


def clean(msg):
    """Never let the API key reach logs / status files."""
    s = str(msg)
    if API_KEY:
        s = s.replace(API_KEY, "***")
    return re.sub(r"api_key=[^&\s]+", "api_key=***", s)[:400]


def log(step, **kw):
    kw["step"] = step
    LOG["steps"].append(kw)
    print(json.dumps(kw, ensure_ascii=False), flush=True)


def err(where, e):
    LOG["errors"].append({"where": where, "error": clean(e)})
    print("ERROR", where, clean(e), file=sys.stderr, flush=True)


# ───────────────────────── Windsor ─────────────────────────
def windsor(connector, fields, d1, d2, account=None, extra=None, retries=3, timeout=300):
    params = {"api_key": API_KEY, "date_from": str(d1), "date_to": str(d2), "fields": ",".join(fields)}
    flt = []
    if account and connector != "googleanalytics4":
        flt = [["account_id", "eq", account]]
    if extra:
        flt = [flt[0], "and", extra] if flt else [extra]
    if flt:
        params["filter"] = json.dumps(flt)
    if account:
        params["select_accounts"] = str(account)
    last = None
    for a in range(retries):
        try:
            with SEM:
                r = requests.get(f"{WINDSOR}/{connector}", params=params, timeout=timeout)
            if r.status_code >= 400:
                raise RuntimeError(f"{connector} HTTP {r.status_code}: {r.text[:200]}")
            j = r.json()
            rows = j.get("data", j) if isinstance(j, dict) else j
            if not isinstance(rows, list):
                raise RuntimeError(f"{connector}: unexpected response {str(j)[:200]}")
            if account:
                digits = re.sub(r"[^0-9]", "", str(account))
                numeric = digits == re.sub(r"[^0-9a-z]", "", str(account).lower())
                norm = (lambda v: re.sub(r"[^0-9]", "", str(v))) if numeric else (lambda v: str(v).lower())
                tgt = digits if numeric else str(account).lower()
                rows = [x for x in rows if "account_id" not in x or norm(x["account_id"]) == tgt]
            return rows
        except Exception as e:  # noqa: BLE001 – retry any transport / Windsor error
            last = e
            time.sleep(4 * (a + 1))
    raise RuntimeError(clean(last))


def windsor_meta_safe(fields, d1, d2, account):
    """Meta sometimes fails on the last (incomplete) day – pull without it and try it alone."""
    try:
        return windsor("facebook", fields, d1, d2, account)
    except Exception:
        if d1 >= d2:
            raise
        rows = windsor("facebook", fields, d1, d2 - dt.timedelta(1), account, retries=2)
        try:
            rows += windsor("facebook", fields, d2, d2, account, retries=1)
        except Exception as e:  # noqa: BLE001
            err(f"meta last day {d2}", e)
        return rows


# ───────────────────────── cache (date → rows) ─────────────────────────
class Cache:
    def __init__(self, root, key):
        self.path = os.path.join(root, key + ".json")
        self.d = json.load(open(self.path)) if os.path.exists(self.path) else {}

    def missing(self, d1, d2, refresh_from):
        """Date ranges to (re)pull: anything not cached, plus everything from refresh_from on."""
        days, cur = [], d1
        while cur <= d2:
            if str(cur) not in self.d or cur >= refresh_from:
                days.append(cur)
            cur += dt.timedelta(1)
        # group consecutive days into ranges, ≤ 31 days each
        out = []
        for x in days:
            if out and (x - out[-1][1]).days == 1 and (x - out[-1][0]).days < 31:
                out[-1][1] = x
            else:
                out.append([x, x])
        return out

    def put(self, d1, d2, rows, keyf=lambda r: str(r.get("date", ""))[:10]):
        cur = d1
        while cur <= d2:
            self.d[str(cur)] = []
            cur += dt.timedelta(1)
        for r in rows:
            k = keyf(r)
            if k in self.d:
                self.d[k].append(r)

    def covered_from(self, asof):
        """First day of the unbroken cached run ending at asof."""
        cur = asof
        while str(cur - dt.timedelta(1)) in self.d:
            cur -= dt.timedelta(1)
        return cur

    def rows(self, d1, d2):
        return [r for k, v in sorted(self.d.items()) if str(d1) <= k <= str(d2) for r in v]

    def save(self):
        json.dump(self.d, open(self.path, "w"), ensure_ascii=False, separators=(",", ":"))


def sync(cache, d1, d2, refresh_from, pull, label):
    for a, b in sorted(cache.missing(d1, d2, refresh_from), reverse=True):     # newest first
        if b < refresh_from and time.time() > DEADLINE[0]:
            LOG["deferred"] += 1
            continue
        try:
            cache.put(a, b, pull(a, b))
        except Exception as e:  # noqa: BLE001 – one failed chunk must not kill the client
            err(f"{label} {a}..{b}", e)
    cache.save()


# ───────────────────────── per-source pulls ─────────────────────────
def meta_ads(c, a, b):
    """Two pulls (spend vs purchases) merged by date+ad – Windsor returns wrong spend when combined."""
    s = windsor_meta_safe(["date", "account_id", "campaign_id", "campaign", "adset_id", "adset_name", "ad_id", "ad_name",
                           "spend", "impressions", "outbound_clicks_outbound_click"], a, b, c["meta"])
    p = windsor_meta_safe(["date", "account_id", "campaign_id", "campaign", "adset_id", "adset_name", "ad_id", "ad_name",
                           "actions_omni_purchase", "action_values_omni_purchase"], a, b, c["meta"])
    m = {}
    for r in s:
        k = (str(r["date"])[:10], str(r["ad_id"]))
        m[k] = dict(r, actions_omni_purchase=0, action_values_omni_purchase=0)
    for r in p:
        k = (str(r["date"])[:10], str(r["ad_id"]))
        o = m.setdefault(k, dict(r, spend=0, impressions=0, outbound_clicks_outbound_click=0))
        o["actions_omni_purchase"] = r.get("actions_omni_purchase") or 0
        o["action_values_omni_purchase"] = r.get("action_values_omni_purchase") or 0
    return [x for x in m.values() if (x.get("spend") or 0) > 0 or (x.get("actions_omni_purchase") or 0) > 0]


def meta_account(c, a, b):
    return windsor_meta_safe(["date", "account_id", "spend"], a, b, c["meta"])


def google_daily(c, a, b):
    return windsor("google_ads", ["date", "account_id", "campaign_id", "campaign", "cost", "clicks", "conversions",
                                  "conversions_value"], a, b, c["google"])


def ga4(fields, extra=None):
    return lambda c, a, b: windsor("googleanalytics4", ["account_id"] + fields, a, b, c["ga4"], extra)


GA4_DAILY = ga4(["date", "sessions", "totalrevenue", "transactions", "add_to_carts", "checkouts", "items_viewed"])
GA4_PAID = ga4(["date", "session_source_medium", "campaign", "totalrevenue", "transactions"], ["campaign", "ncontains", "("])
GA4_OPENAI = ga4(["date", "session_source_medium", "campaign", "sessions", "engaged_sessions", "add_to_carts", "transactions",
                  "totalrevenue"], [["session_source_medium", "contains", "openai"], "or", ["session_source_medium", "contains", "chatgpt"]])
ITEM_F = ["item_name", "item_category", "items_viewed", "items_added_to_cart", "items_checked_out", "items_purchased", "item_revenue"]
ITEM_FILTER = [["items_viewed", "gte", 5], "or", ["items_purchased", "gt", 0]]


def shopify_daily(c, a, b):
    rows = windsor("shopify", ["date", "account_id", "order_count", "order_total_price"], a, b, c["shopify"])
    return [r for r in rows if str(r.get("account_id", c["shopify"])).lower() == c["shopify"].lower()]


def chatgpt_day(c, a, b):
    """OpenAI Ads via the existing agency-live-data Worker (keys live there). One day per call."""
    out, cur = [], a
    while cur <= b:
        r = requests.get(WORKER, params={"client": c["chatgpt_worker"], "from": str(cur), "to": str(cur), "debug": "chatgpt"},
                         timeout=60)
        j = r.json()
        if "error" in j:
            raise RuntimeError(j["error"])
        cur_code = str((j.get("account") or {}).get("currency") or "ILS").upper()
        fx = c.get("_fx", 1) if cur_code == "USD" else 1
        for x in j.get("rows") or []:
            out.append({"date": str(cur), "campaign_id": str(x.get("campaign_id") or x.get("campaign_name")),
                        "campaign_name": x.get("campaign_name") or "?", "spend": float(x.get("spend") or 0) * fx,
                        "impressions": int(float(x.get("impressions") or 0)), "clicks": int(float(x.get("clicks") or 0)),
                        "conversions": float(x.get("conversions") or 0)})
        cur += dt.timedelta(1)
    return out


def usd_ils():
    try:
        j = requests.get("https://api.frankfurter.app/latest", params={"from": "USD", "to": "ILS"}, timeout=20).json()
        return float(j["rates"]["ILS"])
    except Exception as e:  # noqa: BLE001
        err("fx", e)
        return 3.15


# ───────────────────────── GA4 weeks (Sun–Sat) ─────────────────────────
def week_start(d):
    return d - dt.timedelta((d.weekday() + 1) % 7)


# ───────────────────────── crypto ─────────────────────────
def token_for(secret, key, v):
    return base64.urlsafe_b64encode(hmac.new(secret.encode(), f"perf|{key}|{v}".encode(), hashlib.sha256).digest()[:18]).decode()


def file_id(token):
    return hashlib.sha256(("id|" + token).encode()).hexdigest()[:24]


def encrypt(html, token):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key = hashlib.sha256(("key|" + token).encode()).digest()
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, gzip.compress(html.encode("utf-8"), 9), None)


# ───────────────────────── main ─────────────────────────
def run_client(key, c, args, now):
    W = os.path.join(args.work, key)
    os.makedirs(W, exist_ok=True)
    C = os.path.join(args.cache, key)
    os.makedirs(C, exist_ok=True)
    today = now.date()
    partial = now.hour >= 10                      # 13:00 / 19:00 runs include today (partial); 07:00 run → up to yesterday
    asof = today if partial else today - dt.timedelta(1)
    start = asof - dt.timedelta(365)
    refresh = asof - dt.timedelta(7 if now.weekday() != 6 or now.hour >= 10 else 35)   # Sunday morning: refresh 5 weeks
    files = {}

    def cached(name, d1, pull):
        ca = Cache(C, name)
        sync(ca, d1, asof, refresh, lambda a, b: pull(c, a, b), f"{key}/{name}")
        path = os.path.join(W, name + ".json")
        json.dump({"data": ca.rows(d1, asof)}, open(path, "w"), ensure_ascii=False)
        return path, ca

    jobs = {"ga4_daily": (start - dt.timedelta(366), GA4_DAILY), "ga4_paid": (start, GA4_PAID),
            "google_daily": (start, google_daily), "meta_ad_daily": (start, meta_ads)}
    if c.get("shopify"):
        jobs["shopify_daily"] = (start, shopify_daily)
    with ThreadPoolExecutor(len(jobs)) as ex:
        fut = {n: ex.submit(cached, n, d, f) for n, (d, f) in jobs.items()}
        got = {n: f.result() for n, f in fut.items()}
    for n in ("ga4_daily", "ga4_paid", "google_daily", "meta_ad_daily"):
        files[n] = got[n][0]
    meta_c = got["meta_ad_daily"][1]
    # history shown = what is fully cached for the paid channels (back-fill continues next runs)
    start = max(start, meta_c.covered_from(asof), got["google_daily"][1].covered_from(asof), got["ga4_paid"][1].covered_from(asof))
    # client with a short history (e.g. GA4 / ads started recently): begin at the first day with any data
    g4 = got["ga4_daily"][1]
    first = min([k for k, v in g4.d.items() if k >= str(start) and any(float(r.get("sessions") or 0) > 0 for r in v)] +
                [k for k, v in meta_c.d.items() if k >= str(start) and v] + [str(asof)])
    start = max(start, dt.date.fromisoformat(first))

    # check: ad-level spend vs account-level spend (last 14 days)
    try:
        acc = meta_account(c, asof - dt.timedelta(13), asof)
        a_sp = sum(float(x.get("spend") or 0) for x in acc)
        ad_sp = sum(float(x.get("spend") or 0) for x in meta_c.rows(asof - dt.timedelta(13), asof))
        log("meta_check", client=key, account=round(a_sp), ads=round(ad_sp))
        if a_sp and abs(ad_sp / a_sp - 1) > 0.02:
            err(f"{key}/meta_check", f"ad-level spend {ad_sp:.0f} vs account {a_sp:.0f}")
    except Exception as e:  # noqa: BLE001
        err(f"{key}/meta_check", e)

    # products – weekly (cache per week) + daily
    ws_last = week_start(asof)
    weeks = [ws_last - dt.timedelta(7 * i) for i in range(52, -1, -1)]
    wc = Cache(C, "items_weekly")
    for ws in reversed(weeks):
        we = min(ws + dt.timedelta(6), asof)
        k = str(ws)
        if k in wc.d and we < refresh and ws != ws_last:
            continue
        if k not in wc.d and we < refresh and time.time() > DEADLINE[0]:
            LOG["deferred"] += 1
            continue
        try:
            rows = windsor("googleanalytics4", ["account_id", "year_week"] + ITEM_F, ws, we, c["ga4"], ITEM_FILTER)
            wc.d[k] = rows
        except Exception as e:  # noqa: BLE001
            err(f"{key}/items {ws}", e)
    wc.d = {k: v for k, v in wc.d.items() if k >= str(weeks[0])}
    wc.save()
    have = list(weeks)
    while have and str(have[0]) not in wc.d:
        have.pop(0)
    weeks = have
    files["items_weekly"] = []
    for i, ws in enumerate(weeks):
        p = os.path.join(W, f"items_w{i}.json")
        # GA4 may split a Sun–Sat week across two year_week values at New Year – normalise to the week's own label
        rows = wc.d.get(str(ws), [])
        yw = None
        if rows:
            yw = max(collections.Counter(r["year_week"] for r in rows).items(), key=lambda kv: kv[1])[0]
            rows = [dict(r, year_week=yw) for r in rows]
        json.dump({"data": rows}, open(p, "w"), ensure_ascii=False)
        files["items_weekly"].append(p)
    try:
        di = windsor("googleanalytics4", ["account_id", "date"] + ITEM_F, asof - dt.timedelta(7), asof, c["ga4"], ITEM_FILTER)
    except Exception as e:  # noqa: BLE001
        err(f"{key}/items_daily", e)
        di = []
    files["items_daily"] = os.path.join(W, "items_daily.json")
    json.dump({"data": di}, open(files["items_daily"], "w"), ensure_ascii=False)

    cfg = {"client": {k: c[k] for k in ("name", "name_en", "domain") if c.get(k)},
           "start": str(start), "asof": str(asof), "partial_today": partial, "updated": now.strftime("%Y-%m-%dT%H:%M"),
           "files": files, "google_medium": "google / cpc", "meta_mediums": ["fb / paid", "ig / paid", "facebook / paid",
                                                                           "instagram / paid", "facebook / meta", "meta / paid"],
           "match_any_medium": True, "meta_fx": c.get("_fx", 1),
           "template": os.path.join(HERE, "template.html"), "out": os.path.join(W, "page.html")}
    cfg["client"]["month"] = f'{["ינואר","פברואר","מרץ","אפריל","מאי","יוני","יולי","אוגוסט","ספטמבר","אוקטובר","נובמבר","דצמבר"][asof.month-1]} {asof.year}'

    # new customers MTD vs same days last year (GA4)
    try:
        m1 = asof.replace(day=1)
        cur = windsor("googleanalytics4", ["account_id", "first_time_purchasers"], m1, asof, c["ga4"])
        try:
            ly1, ly2 = m1.replace(year=m1.year - 1), asof.replace(year=asof.year - 1)
        except ValueError:
            ly1, ly2 = m1.replace(year=m1.year - 1), asof.replace(year=asof.year - 1, day=28)
        ly = windsor("googleanalytics4", ["account_id", "first_time_purchasers"], ly1, ly2, c["ga4"])
        sc = sum(float(x.get("first_time_purchasers") or 0) for x in cur)
        sl = sum(float(x.get("first_time_purchasers") or 0) for x in ly)
        if sc:
            cfg["mtd_new"] = {"cur": round(sc), **({"ly": round(sl)} if sl else {})}
    except Exception as e:  # noqa: BLE001
        err(f"{key}/new_customers", e)

    # Shopify → store revenue (net after refunds). Only days Shopify actually covers.
    if c.get("shopify"):
        p = got["shopify_daily"][0]
        days = collections.defaultdict(lambda: {"rev": 0.0, "ord": 0})
        for r in json.load(open(p))["data"]:
            d = days[str(r["date"])[:10]]
            d["rev"] += float(r.get("order_total_price") or 0)
            d["ord"] += int(float(r.get("order_count") or 0))
        if days:
            first = min(days)
            sd = {k: {"rev": round(v["rev"]), "ord": v["ord"]} for k, v in days.items()}
            # fill zero days inside coverage so a day without orders shows 0, not "no data"
            cur = dt.date.fromisoformat(first)
            while cur <= asof:
                sd.setdefault(str(cur), {"rev": 0, "ord": 0})
                cur += dt.timedelta(1)
            cfg["store_daily"] = sd
            cfg["store_daily_note"] = "הזמנות בשופיפיי, נטו אחרי החזרות"
            cfg["store_label"] = "שופיפיי"
            m1 = str(asof.replace(day=1))
            last_full = str(asof - dt.timedelta(1)) if partial else str(asof)
            if first <= m1:
                mt = [v for k, v in sd.items() if m1 <= k <= last_full]
                cfg["store_mtd"] = {"rev": sum(x["rev"] for x in mt), "ord": sum(x["ord"] for x in mt),
                                    "note": "הזמנות בשופיפיי"}

    # ChatGPT – only shown when there is spend in the data
    if c.get("chatgpt_worker"):
        cp, cc = cached("chatgpt", max(start, dt.date(2026, 9, 1)), chatgpt_day)
        gp, _ = cached("ga4_openai", max(start, dt.date(2026, 9, 1)), GA4_OPENAI)
        if any(float(r.get("spend") or 0) > 0 for r in json.load(open(cp))["data"]):
            cfg["chatgpt"] = {"rows": cp, "ga4": gp}

    cp = os.path.join(W, "config.json")
    json.dump(cfg, open(cp, "w"), ensure_ascii=False, indent=1)
    res = subprocess.run([sys.executable, os.path.join(HERE, "build.py"), cp], capture_output=True, text=True)
    if res.returncode:
        raise RuntimeError("build failed: " + res.stderr[-600:])
    summary = json.loads(res.stdout.strip().splitlines()[-1])
    log("built", client=key, kb=summary["kb"], days=summary["days"], ads=summary["ads"], meta_rows=summary["meta_rows"],
        google_rows=summary["google_rows"], item_rows=summary["item_rows"], unmatched_ga4_paid_share=None,
        store=bool(cfg.get("store_daily")), chatgpt=bool(cfg.get("chatgpt")), partial=partial)
    return open(cfg["out"]).read(), summary


def send_links(links, changed):
    user, pw = os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_APP_PASSWORD")
    if not (user and pw):
        err("email", "GMAIL_USER / GMAIL_APP_PASSWORD missing – links not sent")
        return
    rows = "".join(f'<tr><td style="padding:6px 10px"><b>{n}</b>{" · חדש" if k in changed else ""}</td>'
                   f'<td style="padding:6px 10px;direction:ltr"><a href="{u}">{u}</a></td></tr>' for k, (n, u) in links.items())
    body = (f'<div dir="rtl" style="font-family:Arial,sans-serif">'
            f'<p>הקישורים לדשבורד מדד ביצועים של כל לקוח. כל קישור פותח רק את הלקוח שלו, ומתעדכן ב-07:00, 13:00 ו-19:00.</p>'
            f'<table style="border-collapse:collapse">{rows}</table>'
            f'<p style="color:#666;font-size:12px">לניתוק לקוח: להעלות את v שלו ב-perf_dashboard/clients.json – הקישור הישן מפסיק לעבוד '
            f'וקישור חדש יישלח לכאן. אל תעביר קישור של לקוח אחד ללקוח אחר.</p></div>')
    msg = MIMEText(body, "html", "utf-8")
    msg["Subject"] = "קישורי מדד ביצועים ללקוחות – MAKE-E"
    msg["From"] = user
    msg["To"] = user
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(user, pw)
        s.sendmail(user, [user], msg.as_string())
    log("email_sent", to="GMAIL_USER", clients=sorted(changed))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clients", default="")
    ap.add_argument("--out", default=os.path.join(HERE, "..", "_dash_out"))
    ap.add_argument("--cache", default=os.path.join(HERE, "..", "_dash_cache"))
    ap.add_argument("--work", default=os.path.join(HERE, "..", "_dash_work"))
    ap.add_argument("--no-email", action="store_true")
    ap.add_argument("--budget", type=float, default=45, help="minutes for history back-fill")
    args = ap.parse_args()
    DEADLINE[0] = time.time() + args.budget * 60
    for p in (args.out, args.cache, args.work, os.path.join(args.out, "d")):
        os.makedirs(p, exist_ok=True)
    secret = os.environ.get("DASH_SECRET") or API_KEY
    if not API_KEY or not secret:
        sys.exit("WINDSOR_API_KEY missing")
    conf = json.load(open(os.path.join(HERE, "clients.json")))["clients"]
    keys = [k for k in conf if not args.clients or k in args.clients.split(",")]
    now = dt.datetime.now(IL)
    fx = usd_ils()
    prev = {}
    sp = os.path.join(args.out, "status.json")
    if os.path.exists(sp):
        try:
            prev = json.load(open(sp)).get("ids", {})
        except Exception:  # noqa: BLE001
            prev = {}
    ids, links, changed, built = {}, {}, set(), {}
    def one(k):
        c = dict(conf[k])
        c["_fx"] = fx if c.get("meta_currency") == "USD" else 1
        tok = token_for(secret, k, c.get("v", 1))
        fid = file_id(tok)
        ids[k] = fid
        links[k] = (c["name"], LOADER_URL + "#" + tok)
        if prev.get(k) != fid:
            changed.add(k)
        try:
            html, summ = run_client(k, c, args, now)
            open(os.path.join(args.out, "d", fid + ".bin"), "wb").write(encrypt(html, tok))
            built[k] = {"kb": summ["kb"], "days": summ["days"]}
        except Exception as e:  # noqa: BLE001 – keep the previous file for this client
            err(f"{k}/build", e)

    with ThreadPoolExecutor(len(keys)) as ex:
        list(ex.map(one, keys))
    # remove files of revoked links
    keep = {v + ".bin" for v in ids.values()} | {v + ".bin" for k, v in prev.items() if k not in ids}
    for f in os.listdir(os.path.join(args.out, "d")):
        if f not in keep:
            os.remove(os.path.join(args.out, "d", f))
    status = {"updated": now.isoformat(timespec="minutes"), "ids": {**prev, **ids}, "built": built,
              "deferred_chunks": LOG["deferred"],
              "errors": LOG["errors"][:50], "fx_usd_ils": round(fx, 4)}
    json.dump(status, open(sp, "w"), ensure_ascii=False, indent=1)
    if changed and not args.no_email:
        try:
            send_links({k: links[k] for k in keys}, changed)
        except Exception as e:  # noqa: BLE001
            err("email", e)
            status["ids"] = {**prev, **{k: v for k, v in ids.items() if k not in changed}}   # retry email next run
            status["errors"] = LOG["errors"][:50]
            json.dump(status, open(sp, "w"), ensure_ascii=False, indent=1)
    if not built:
        sys.exit("no client built")


if __name__ == "__main__":
    main()
