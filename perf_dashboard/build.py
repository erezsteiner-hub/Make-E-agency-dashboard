#!/usr/bin/env python3
"""MAKE-E performance dashboard v2 – long history, ranges, Meta drill-down, weekly products.
Usage: python3 build.py config.json
"""
import json, sys, collections, datetime as dt

cfg = json.load(open(sys.argv[1]))
D = dt.date.fromisoformat
F = cfg["files"]
rows = lambda p: json.load(open(p))["data"]
start, asof = D(cfg["start"]), D(cfg["asof"])          # asof = today (partial) or last full day
partial = cfg.get("partial_today", False)
days = [(start + dt.timedelta(i)).isoformat() for i in range((asof - start).days + 1)]
DI = {d: i for i, d in enumerate(days)}

# ---- GA4 daily (+ last year) ----
g = {x["date"][:10]: x for x in rows(F["ga4_daily"])}
def ly(d):
    try:
        return D(d).replace(year=D(d).year - 1).isoformat()
    except ValueError:
        return None
num = lambda v: v or 0

# ---- Meta (Windsor ad level daily) ----
fx = cfg.get("meta_fx", 1)
camps, sets, ads = {}, {}, {}
mrows = []
mDay = collections.defaultdict(float)
for x in rows(F["meta_ad_daily"]):
    d = x["date"][:10]
    if d not in DI:
        continue
    s = num(x["spend"]) * fx
    p = num(x.get("actions_omni_purchase"))
    if s <= 0 and not p:
        continue
    camps[x["campaign_id"]] = x["campaign"]
    sets[x["adset_id"]] = [x["adset_name"], x["campaign_id"]]
    ads[x["ad_id"]] = [x["ad_name"], x["adset_id"]]
    mDay[d] += s
    mrows.append([DI[d], x["ad_id"], round(s, 2), int(num(x.get("impressions"))),
                  int(num(x.get("outbound_clicks_outbound_click"))), round(p, 2),
                  round(num(x.get("action_values_omni_purchase")) * fx, 2)])

# ---- Google daily ----
gcamps, grows = {}, []
gDay = collections.defaultdict(float)
for x in rows(F["google_daily"]):
    d = x["date"][:10]
    if d not in DI or not (x.get("cost") or x.get("conversions")):
        continue
    cid = str(x["campaign_id"])
    gcamps[cid] = x["campaign"]
    gDay[d] += num(x["cost"])
    grows.append([DI[d], cid, round(num(x["cost"]), 2), int(num(x["clicks"])),
                  round(num(x["conversions"]), 2), round(num(x["conversions_value"]), 2)])

# ---- GA4 revenue by paid campaign (matched by campaign name) ----
gm, mm = cfg.get("google_medium", "google / cpc"), set(cfg.get("meta_mediums", ["fb / paid", "ig / paid"]))
mByName = collections.defaultdict(list)
for k, v in camps.items():
    mByName[v].append(k)
gByName = collections.defaultdict(list)
for k, v in gcamps.items():
    gByName[v].append(k)
mga, gga = collections.defaultdict(lambda: [0, 0]), collections.defaultdict(lambda: [0, 0])
unmatched = collections.defaultdict(float)
for x in rows(F["ga4_paid"]):
    d = x["date"][:10]
    if d not in DI:
        continue
    sm, cn = x["session_source_medium"], str(x["campaign"])
    anym = cfg.get("match_any_medium")
    if sm in mm or (anym and sm != gm and (cn in mByName or cn in camps)):
        tgt, ids = mga, mByName.get(cn) or ([cn] if cn in camps else None)
    elif sm == gm or (anym and (cn in gByName or cn in gcamps)):
        tgt, ids = gga, gByName.get(cn) or ([cn] if cn in gcamps else None)
    else:
        tgt, ids = None, None
    if tgt is None:
        continue
    if not ids:
        unmatched[sm + " | " + cn] += num(x["totalrevenue"])
        continue
    o = tgt[(DI[d], ids[0])]
    o[0] += num(x["totalrevenue"]); o[1] += num(x["transactions"])
pack = lambda t: [[k[0], k[1], round(v[0], 2), int(v[1])] for k, v in t.items() if v[0] or v[1]]

# ---- daily site rows ----
drows = []
for d in days:
    x = g.get(d, {})
    l = g.get(ly(d)) if ly(d) else None
    drows.append(dict(d=d, rev=round(num(x.get("totalrevenue"))), ord=int(num(x.get("transactions"))),
                      ses=int(num(x.get("sessions"))), pv=int(num(x.get("items_viewed"))),
                      atc=int(num(x.get("add_to_carts"))), co=int(num(x.get("checkouts"))),
                      meta=round(mDay[d], 2), goo=round(gDay[d], 2),
                      lyRev=round(num(l.get("totalrevenue"))) if l else None,
                      srev=(cfg.get("store_daily") or {}).get(d, {}).get("rev"), sord=(cfg.get("store_daily") or {}).get(d, {}).get("ord")))

# ---- products: weekly (GA4 weeks start Sunday) + daily ----
names, nidx, cats, cidx = [], {}, [], {}
def ii(n):
    if n not in nidx:
        nidx[n] = len(names); names.append(n)
    return nidx[n]
def ci(c):
    c = c or "ללא קטגוריה"
    if c not in cidx:
        cidx[c] = len(cats); cats.append(c)
    return cidx[c]
itemCat = {}
def wstart(yw):
    y, w = int(yw[:4]), int(yw[4:])
    j1 = dt.date(y, 1, 1)
    first_sun = j1 + dt.timedelta((6 - j1.weekday()) % 7)  # first Sunday on/after Jan 1
    if first_sun == j1:
        return j1 + dt.timedelta(7 * (w - 1))
    return j1 if w == 1 else first_sun + dt.timedelta(7 * (w - 2))
wk = []
for f in F["items_weekly"]:
    wk += rows(f)
wk = [x for x in wk if wstart(x["year_week"]) <= asof]
wlist = sorted({x["year_week"] for x in wk})
weeks = []
for w in wlist:
    s = wstart(w); e = min(s + dt.timedelta(6), asof)
    weeks.append(dict(w=w, s=s.isoformat(), e=e.isoformat(), partial=(s + dt.timedelta(6)) > asof or (partial and e == asof)))
WI = {w: i for i, w in enumerate(wlist)}
def irow(i, x):
    n = x["item_name"]
    if not n or n == "(not set)":
        return None
    k = ii(n); itemCat.setdefault(k, ci(x.get("item_category")))
    return [i, k, int(num(x["items_viewed"])), int(num(x["items_added_to_cart"])), int(num(x["items_purchased"])),
            round(num(x["item_revenue"]), 2)]
witems = [r for r in (irow(WI[x["year_week"]], x) for x in wk) if r]
dl = sorted({x["date"][:10] for x in rows(F["items_daily"]) if x["date"][:10] <= asof.isoformat()})
DLI = {d: i for i, d in enumerate(dl)}
ditems = [r for r in (irow(DLI[x["date"][:10]], x) for x in rows(F["items_daily"]) if x["date"][:10] in DLI) if r and (r[2] >= 1 or r[4] > 0)]


# ---- ChatGPT Ads (OpenAI export CSV + GA4 by campaign) ----
chat = None
if cfg.get("chatgpt"):
    import csv
    gg = {}
    for x in rows(cfg["chatgpt"]["ga4"]):   # Windsor GA4: date, campaign, sessions, engaged_sessions, add_to_carts, transactions, totalrevenue
        k = f'{x["date"][:10]}|{x["campaign"]}'
        o = gg.setdefault(k, [0, 0, 0, 0, 0])
        for j, f in enumerate(["sessions", "engaged_sessions", "add_to_carts", "transactions", "totalrevenue"]):
            o[j] += num(x.get(f))
    crow, cnames = [], {}
    seen = set()
    src = (rows(cfg["chatgpt"]["rows"]) if cfg["chatgpt"].get("rows")
           else csv.DictReader(open(cfg["chatgpt"]["csv"], encoding="utf-8-sig")))
    for x in src:
        d = x["date"]
        if d not in DI:
            continue
        cid = x["campaign_id"]; cnames[cid] = x["campaign_name"]
        ga = gg.get(f"{d}|{x['campaign_name']}", [0, 0, 0, 0, 0]); seen.add(f"{d}|{x['campaign_name']}")
        crow.append([DI[d], cid, round(float(x["spend"]), 2), int(x["impressions"]), int(x["clicks"]), int(float(x["conversions"]))] + ga)
    byname = {v: k for k, v in cnames.items()}
    for k, ga in gg.items():   # GA4 sessions on days without spend rows
        d, n = k.split("|", 1)
        if k not in seen and d in DI and n in byname:
            crow.append([DI[d], byname[n], 0, 0, 0, 0] + ga)
    chat = dict(camps=cnames, rows=crow, note=cfg["chatgpt"].get("note"))

out = dict(chatgpt=chat, client=cfg["client"], updated=cfg["updated"], asof=asof.isoformat(), partialToday=partial,
           targets={k: v for k, v in (cfg.get("targets") or {}).items() if v}, mtdNew=cfg.get("mtd_new"),
           store=cfg.get("store"), storeMtd=cfg.get("store_mtd"), storeDailyNote=cfg.get("store_daily_note"), days=drows,
           meta=dict(camps=camps, sets=sets, ads=ads, rows=mrows, ga=pack(mga)),
           google=dict(camps=gcamps, rows=grows, ga=pack(gga)),
           items=dict(names=names, cat=[itemCat[i] for i in range(len(names))], cats=cats,
                      weeks=weeks, rows=witems, days=dl, drows=ditems))
t = open(cfg["template"]).read()
title = f'{cfg["client"]["name"]} · מדד ביצועים'
html = t.replace("__TITLE__", title).replace("__DATA__", json.dumps(out, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"))
open(cfg["out"], "w").write(html)
first = asof.replace(day=1).isoformat()
full = [x for x in drows if x["d"] >= first and (x["d"] < asof.isoformat() or not partial)]
print(json.dumps(dict(out=cfg["out"], kb=len(html) // 1024, days=len(drows), meta_rows=len(mrows), ads=len(ads),
                      google_rows=len(grows), item_rows=len(witems), weeks=[w["s"] for w in weeks][:2] + ["…", weeks[-1]["s"]],
                      mtd_rev=sum(x["rev"] for x in full), mtd_meta=round(sum(x["meta"] for x in full)),
                      mtd_google=round(sum(x["goo"] for x in full)),
                      unmatched_ga4_paid=round(sum(unmatched.values())),
                      top_unmatched=sorted(unmatched.items(), key=lambda kv: -kv[1])[:5]), ensure_ascii=False))
