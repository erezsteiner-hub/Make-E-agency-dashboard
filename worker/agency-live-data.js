/**
 * agency-live-data — Cloudflare Worker
 * מושך נתונים חיים מ-Windsor (Meta + Google Ads + GA4 + Shopify) לכל טווח תאריכים
 *
 * Environment Variables (Settings → Variables):
 *   WINDSOR_API_KEY  - ה-API key מ-Windsor
 *   KLAVIYO_API_KEY  - Private API key של קלאביו (Read-only) — כרגע רק לאנאבלה
 *   KLAVIYO_CACHE    - (אופציונלי) KV binding לשמירת תוצאות קלאביו בין קריאות
 *
 * שימוש מהדשבורד:
 *   https://YOUR-WORKER.workers.dev/?client=crazy&from=2026-05-28&to=2026-06-26
 *
 * ChatGPT Ads (OpenAI Ads): לקוח עם שדה chatgpt מקבל בלוק "chatgpt" — נמשך ישירות מ-api.ads.openai.com
 *   (לא דרך Windsor). מפתח API לכל חשבון פרסום, כ-Secret ב-Worker:
 *     OPENAI_ADS_KEY_ANNABELLA, OPENAI_ADS_KEY_PRETTY
 *   אין מפתח / שגיאה → אין בלוק chatgpt, ושאר הדשבורד לא מושפע. סכומים מומרים לש"ח (fx_rate בתשובה).
 *   אבחון: ?client=pretty&from=..&to=..&debug=chatgpt
 *
 * Shopify: לקוח עם שדה shopify מקבל גם בלוק "shopify" בתשובה (הכנסות/הזמנות/יחידות/מוצרים).
 * לקוח בלי shopify — התשובה זהה לגמרי למה שהייתה (GA4 בלבד).
 *
 * 2026-11-02: Meta עמיד ליום אחרון חסר — כש-Windsor מחזיר שגיאה על היום האחרון בטווח (בדרך כלל "היום",
 * "incomplete time-series data"), מושכים את הטווח בלי היום הזה ומנסים את היום לבד. אם גם הוא נכשל — מדלגים
 * עליו ומסמנים meta_partial, במקום שכל נתוני מטא ייעלמו (0) מהדשבורד.
 */

// מיפוי לקוחות → חשבונות בכל פלטפורמה
const CLIENTS = {
  crazy:     { name: "Crazy Line",        meta: "2562301110668961", google: "654-753-2446", ga4: "454540408" },
  pretty:    { name: "Pretty Ballerinas", meta: "708681422636732",  google: "477-626-3831", ga4: "152370243", chatgpt: { keyEnv: "OPENAI_ADS_KEY_PRETTY" } },
  annabella: { name: "Annabella",         meta: "1247794652730158", google: "490-285-3125", ga4: "354304809", shopify: "annabellapump.myshopify.com", klaviyo: { keyEnv: "KLAVIYO_API_KEY" }, chatgpt: { keyEnv: "OPENAI_ADS_KEY_ANNABELLA" } },
  fine:      { name: "Fine Rituals",      meta: "918073650786458",  google: "700-518-0619", ga4: "518599842" },
  laster:    { name: "Laster",            meta: "369761200875429",  google: "",             ga4: "315864239" },
  aristo:    { name: "Aristo Shmat",      meta: "265005426163824",  google: "377-969-5637", ga4: "401528124" },
    pablo:    { name: "PABLO",           meta: "661581863643798",  google: "178-480-5862",  ga4: "554232841", shopify: "nwxiec-eq.myshopify.com" },
};

const WINDSOR_BASE = "https://connectors.windsor.ai/all";

export default {
  async fetch(request, env) {
    // CORS headers — מאפשר לדשבורד לקרוא ל-Worker
    const cors = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    };
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: cors });
    }

    const url = new URL(request.url);
    const clientKey = url.searchParams.get("client");
    const from = url.searchParams.get("from");
    const to = url.searchParams.get("to");

    if (!clientKey || !CLIENTS[clientKey]) {
      return json({ error: "client לא תקין" }, 400, cors);
    }
    if (!from || !to) {
      return json({ error: "חסרים תאריכים (from / to)" }, 400, cors);
    }

    const client = CLIENTS[clientKey];
    const apiKey = env.WINDSOR_API_KEY;

    // אבחון קלאביו: ?client=annabella&from=..&to=..&debug=klaviyo — מחזיר נתונים גולמיים בלי מטמון (ללא פרטים אישיים)
    if (url.searchParams.get("debug") === "klaviyo" && client.klaviyo) {
      try { return json(await klaviyoDebug(env, client.klaviyo, from, to), 200, cors); }
      catch (e) { return json({ error: e.message }, 200, cors); }
    }

    // אבחון ChatGPT Ads: תשובות גולמיות מ-OpenAI (בלי המפתח)
    if (url.searchParams.get("debug") === "chatgpt" && client.chatgpt) {
      try { return json(await fetchChatGPT(env, client.chatgpt, from, to, true), 200, cors); }
      catch (e) { return json({ error: e.message }, 200, cors); }
    }

    try {
      // ── שליפת המקורות במקביל (עם טיפול בכשלים חלקיים) ──
      const results = await Promise.allSettled([
        fetchMeta(env, apiKey, client.meta, from, to),
        client.google ? fetchGoogle(apiKey, client.google, from, to) : Promise.resolve([]),
        fetchGA4Total(apiKey, client.ga4, from, to),
        fetchGA4Channels(apiKey, client.ga4, from, to),
        fetchGA4Daily(apiKey, client.ga4, from, to),
        fetchGA4Products(apiKey, client.ga4, from, to),
        fetchGA4Campaigns(apiKey, client.ga4, from, to),
        fetchGA4NewVsReturning(apiKey, client.ga4, from, to),
        fetchMetaCreatives(env, apiKey, client.meta, from, to),
        client.shopify ? fetchShopifyOrders(apiKey, client.shopify, from, to) : Promise.resolve([]),
        client.shopify ? fetchShopifyProducts(apiKey, client.shopify, from, to) : Promise.resolve([]),
        client.shopify ? fetchShopifyNewVsReturning(apiKey, client.shopify, from, to) : Promise.resolve([]),
        client.shopify ? fetchShopifyDiscounts(apiKey, client.shopify, from, to) : Promise.resolve([]),
        client.shopify ? fetchShopifySources(apiKey, client.shopify, from, to) : Promise.resolve([]),
        client.klaviyo ? fetchKlaviyo(env, clientKey, client.klaviyo, from, to) : Promise.resolve(null),
        client.chatgpt ? fetchChatGPT(env, client.chatgpt, from, to) : Promise.resolve(null),
      ]);

      const errors = results.filter(r => r.status === "rejected").map(r => r.reason.message);
      const [metaData, googleData, ga4Data, ga4Channels, ga4Daily, ga4Products, ga4Campaigns, ga4NewReturning, metaCreatives, shopifyOrders, shopifyProducts, shopifyNewReturning, shopifyDiscounts, shopifySources] = results.map(r =>
        r.status === "fulfilled" ? r.value : []
      );

      const result = processData(client, metaData, googleData, ga4Data, ga4Channels, ga4Daily, from, to, ga4Products, ga4Campaigns, ga4NewReturning, metaCreatives);
      // Shopify — רק ללקוחות עם חנות מחוברת; אם השליפה נכשלה לא מוסיפים בלוק והדשבורד נשאר על GA4
      if (client.shopify && results[9].status === "fulfilled") {
        result.shopify = processShopify(shopifyOrders, results[10].status === "fulfilled" ? shopifyProducts : [],
          results[11].status === "fulfilled" ? shopifyNewReturning : null);
        if (results[12].status === "fulfilled") {
          result.shopify.discount_codes = summarizeShopifyDiscounts(shopifyDiscounts);
          result.shopify.discount_codes.total_orders = result.shopify.orders;
        }
        if (results[13].status === "fulfilled") result.shopify.order_sources = summarizeShopifySources(shopifySources);
        // שופיפיי מחזיר היסטוריה רק מ-60 יום לפני החיבור. אם הטווח מתחיל לפני שיש נתונים — הנתונים חלקיים,
        // ולכן לא שולחים בלוק shopify והדשבורד מציג את הטווח הזה מ-GA4 (במקום הכנסות חסרות)
        const firstDate = (shopifyOrders || []).map(r => String(r.date || "").slice(0, 10)).filter(Boolean).sort()[0];
        if (firstDate && (Date.parse(firstDate) - Date.parse(from)) / 86400000 > 3) {
          result.shopify_coverage = { from: firstDate, partial: true };
          delete result.shopify;
        }
      }
      // Klaviyo — רק ללקוחות עם klaviyo; כשל לא מפיל את שאר הדשבורד
      // מציגים את הסקשן רק כשיש בקלאביו פעילות בפועל — אחרת הדשבורד לא מציג אפסים ללקוח
      const kv = results[14].status === "fulfilled" ? results[14].value : null;
      if (client.klaviyo && kv && (kv.orders > 0 || kv.recipients > 0 || (kv.list?.subscribed || 0) > 0)) result.klaviyo = kv;
      // ChatGPT Ads — רק כשיש מפתח והוצאה בטווח; נכנס לסך ההוצאה ול-ROAS המשולב
      if (client.chatgpt) {
        const cg = results[15];
        if (cg.status === "fulfilled" && cg.value && (cg.value.spend > 0 || cg.value.impressions > 0)) {
          result.chatgpt = cg.value;
          const ga4Rev = result.ga4?.revenue || 0;
          const tot = (result.meta?.spend || 0) + (result.google?.spend || 0) + cg.value.spend;
          result.blended_roas = tot > 0 ? +(ga4Rev / tot).toFixed(1) : 0;
        } else if (cg.status === "rejected") {
          const i = errors.indexOf(cg.reason.message); if (i >= 0) errors.splice(i, 1);
          errors.push(`ChatGPT Ads: ${cg.reason.message}`);
        }
      }
      // מקור נתוני מטא + בדיקת תקינות: הוצאה 0 עם רכישות = נתון חסר אצל הספק
      result.meta_source = results[0].status === "fulfilled" ? (results[0].value.source || "windsor") : "error";
      // יום אחרון שלא הצליח לרדת מ-Windsor (בדרך כלל "היום", נתונים חלקיים) — שאר הטווח תקין
      const skipped = [...new Set([...(results[0].status === "fulfilled" ? results[0].value.skipped_days || [] : []),
        ...(results[8].status === "fulfilled" ? results[8].value.skipped_days || [] : [])])].sort();
      if (skipped.length) {
        result.meta_partial = { skipped_days: skipped, message: "Windsor could not return Meta data for these days (usually today, incomplete). The rest of the range is complete." };
        errors.push(`Meta partial: skipped ${skipped.join(", ")} (Windsor incomplete data)`);
      }
      // בדיקה יומית: יום עם רכישות אבל בלי הוצאה = נתון חסר אצל Windsor
      if (results[0].status === "fulfilled") {
        const byDay = {};
        for (const r of results[0].value) {
          const d = String(r.date || "").slice(0, 10); if (!d) continue;
          byDay[d] ||= { spend: 0, purch: 0 };
          byDay[d].spend += num(r.spend); byDay[d].purch += num(r.actions_omni_purchase);
        }
        const bad = Object.entries(byDay).filter(([, v]) => v.spend === 0 && v.purch > 0).map(([d]) => d).sort();
        if (bad.length) result.meta_data_issue = { days: bad, message: "Meta spend missing in source data for these days" };
      }
      if (errors.length > 0) result.warnings = errors;
      return json(result, 200, cors);

    } catch (err) {
      return json({ error: err.message, stack: err.stack }, 500, cors);
    }
  },
};

// ── Windsor fetchers ──
async function windsorFetch(apiKey, connector, accountId, fields, from, to, retries = 2, extraFilter = null) {
  const params = new URLSearchParams({
    api_key: apiKey,
    date_from: from,
    date_to: to,
    fields: fields.join(","),
  });
  if (accountId && connector !== "googleanalytics4") {
    params.set("filter", JSON.stringify(extraFilter
      ? [["account_id", "eq", accountId], "and", extraFilter]
      : [["account_id", "eq", accountId]]));
  }

  // שימוש ב-endpoint ספציפי לכל פלטפורמה (לא ב-/all שמערבב הכל)
  const url = `https://connectors.windsor.ai/${connector}?${params}`;
  const TIMEOUT_MS = 25000;

  let lastError;
  for (let attempt = 0; attempt <= retries; attempt++) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);
    try {
      const res = await fetch(url, { signal: controller.signal });
      clearTimeout(timeoutId);
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`Windsor ${connector} HTTP ${res.status}: ${text.slice(0,200)}`);
      }
      const data = await res.json();
      return data.data || data || [];
    } catch (err) {
      clearTimeout(timeoutId);
      lastError = err.name === "AbortError"
        ? new Error(`Windsor ${connector} timeout (${TIMEOUT_MS/1000}s)`)
        : new Error(`Windsor ${connector} failed: ${err.message}`);
      if (attempt < retries) { await new Promise(r => setTimeout(r, 1500 * (attempt + 1))); continue; } // ניסיון נוסף אחרי המתנה קצרה (תקלות 500 זמניות של Windsor)
    }
  }
  throw lastError;
}

// ── Meta: שליפה עמידה ליום אחרון חסר ──
// Windsor מחזיר לפעמים HTTP 400 "incomplete time-series data" על היום האחרון בטווח (בדרך כלל היום הנוכחי),
// וזה מפיל את כל השאילתה. במקרה כזה: מושכים את הטווח בלי היום האחרון, ומנסים את היום האחרון לבד.
// אם היום האחרון עדיין נכשל — מדלגים עליו ומחזירים אותו ב-skipped_days. אם גם הטווח בלעדיו נכשל — זורקים שגיאה כרגיל.
async function windsorFetchMetaSafe(apiKey, accountId, fields, from, to) {
  try {
    const rows = await windsorFetch(apiKey, "facebook", accountId, fields, from, to);
    return { rows, skipped: [] };
  } catch (err) {
    if (from >= to) throw err;
    const prev = prevDay(to);
    const rows = await windsorFetch(apiKey, "facebook", accountId, fields, from, prev, 1);
    try {
      const last = await windsorFetch(apiKey, "facebook", accountId, fields, to, to, 1);
      return { rows: [...(rows || []), ...(last || [])], skipped: [] };
    } catch (e2) {
      return { rows: rows || [], skipped: [to] };
    }
  }
}

function prevDay(d) {
  const t = new Date(d + "T00:00:00Z");
  t.setUTCDate(t.getUTCDate() - 1);
  return t.toISOString().slice(0, 10);
}

// ── Meta (Windsor) ──
// חשוב: Windsor שומר מטמון לפי צירוף השדות. צירוף של הוצאה+רכישות באותה שאילתה החזיר בחלק מהחשבונות
// הוצאה 0 לימים שלמים. לכן מושכים שתי שאילתות נפרדות (הוצאה/קליקים/חשיפות, ורכישות/ערך), ברמה יומית,
// ומאחדים כאן לפי תאריך+קמפיין. שתי השאילתות נבדקו מול מנהל המודעות ותואמות.
function mergeMetaRows(spendRows, purchRows, keyField) {
  const map = new Map();
  const keyOf = r => `${String(r.date || "").slice(0, 10)}|${r[keyField] ?? ""}`;
  for (const r of spendRows) {
    const k = keyOf(r); const m = map.get(k);
    if (m) { m.spend = num(m.spend) + num(r.spend); m.clicks = num(m.clicks) + num(r.clicks); m.impressions = num(m.impressions) + num(r.impressions); }
    else map.set(k, { ...r, actions_omni_purchase: 0, action_values_omni_purchase: 0 });
  }
  for (const r of purchRows) {
    const k = keyOf(r); let m = map.get(k);
    if (!m) { m = { ...r, spend: 0, clicks: 0, impressions: 0, actions_omni_purchase: 0, action_values_omni_purchase: 0 }; map.set(k, m); }
    m.actions_omni_purchase = num(m.actions_omni_purchase) + num(r.actions_omni_purchase);
    m.action_values_omni_purchase = num(m.action_values_omni_purchase) + num(r.action_values_omni_purchase);
  }
  return [...map.values()];
}

// מאחד את שתי השאילתות; אם יום דולג באחת מהן — מסירים אותו גם מהשנייה, כדי שלא תהיה הוצאה בלי רכישות (או להפך)
function mergeMetaSafe(spendRes, purchRes, accountId, keyField) {
  const skipped = [...new Set([...spendRes.skipped, ...purchRes.skipped])];
  const drop = rows => skipped.length ? (rows || []).filter(r => !skipped.includes(String(r.date || "").slice(0, 10))) : (rows || []);
  const rows = mergeMetaRows(drop(safetyFilterByAccount(spendRes.rows, accountId)), drop(safetyFilterByAccount(purchRes.rows, accountId)), keyField);
  rows.skipped_days = skipped;
  return rows;
}

async function fetchMeta(env, apiKey, accountId, from, to) {
  const [spendRes, purchRes] = await Promise.all([
    windsorFetchMetaSafe(apiKey, accountId, ["account_id", "date", "campaign", "spend", "clicks", "impressions"], from, to),
    windsorFetchMetaSafe(apiKey, accountId, ["account_id", "date", "campaign", "actions_omni_purchase", "action_values_omni_purchase"], from, to),
  ]);
  const rows = mergeMetaSafe(spendRes, purchRes, accountId, "campaign");
  rows.source = "windsor_split";
  return rows;
}

// ביצועי קריאייטיב — אותה שיטה (שתי שאילתות, איחוד לפי תאריך+מודעה)
async function fetchMetaCreatives(env, apiKey, accountId, from, to) {
  const [spendRes, purchRes] = await Promise.all([
    windsorFetchMetaSafe(apiKey, accountId, ["account_id", "date", "ad_id", "ad_name", "thumbnail_url", "spend"], from, to),
    windsorFetchMetaSafe(apiKey, accountId, ["account_id", "date", "ad_id", "actions_omni_purchase", "action_values_omni_purchase"], from, to),
  ]);
  return mergeMetaSafe(spendRes, purchRes, accountId, "ad_id");
}

async function fetchGoogle(apiKey, accountId, from, to) {
  const rows = await windsorFetch(apiKey, "google_ads", accountId,
    ["account_id", "campaign", "spend", "clicks", "conversions", "conversions_value"], from, to);
  return safetyFilterByAccount(rows, accountId);
}

// סינון בטיחות בצד הלקוח — גיבוי למקרה שהפילטר בצד השרת לא תפס
function safetyFilterByAccount(rows, accountId) {
  if (!accountId || !Array.isArray(rows)) return rows;
  const normalize = s => String(s || "").replace(/[^0-9]/g, "");
  const target = normalize(accountId);
  const filtered = rows.filter(r => normalize(r.account_id) === target);
  // אם הסינון מחק הכל (כי account_id חסר בתשובה), נחזיר את המקור כדי לא לאבד דאטה
  return filtered.length > 0 ? filtered : rows;
}

async function fetchGA4Total(apiKey, accountId, from, to) {
  const rows = await windsorFetch(apiKey, "googleanalytics4", accountId,
    ["account_id", "sessions", "purchase_revenue", "transactions", "add_to_carts", "checkouts", "totalusers"], from, to);
  return safetyFilterByAccount(rows, accountId);
}

async function fetchGA4Channels(apiKey, accountId, from, to) {
  const rows = await windsorFetch(apiKey, "googleanalytics4", accountId,
    ["account_id", "session_default_channel_group", "purchase_revenue", "transactions"], from, to);
  return safetyFilterByAccount(rows, accountId);
}

async function fetchGA4Daily(apiKey, accountId, from, to) {
  const rows = await windsorFetch(apiKey, "googleanalytics4", accountId,
    ["account_id", "date", "purchase_revenue", "sessions"], from, to);
  return safetyFilterByAccount(rows, accountId);
}

// דוח 1 חדש — טופ מוצרים נמכרים (Best Seller)
async function fetchGA4Products(apiKey, accountId, from, to) {
  const rows = await windsorFetch(apiKey, "googleanalytics4", accountId,
    ["account_id", "item_name", "item_revenue", "items_purchased"], from, to);
  return safetyFilterByAccount(rows, accountId);
}

// דוח 2 חדש — טופ קמפיינים לפי GA4
async function fetchGA4Campaigns(apiKey, accountId, from, to) {
  const rows = await windsorFetch(apiKey, "googleanalytics4", accountId,
    ["account_id", "campaign_name", "purchase_revenue", "transactions", "sessions"], from, to);
  return safetyFilterByAccount(rows, accountId);
}

// דוח חדש 3 — לקוחות חדשים מול חוזרים
async function fetchGA4NewVsReturning(apiKey, accountId, from, to) {
  const rows = await windsorFetch(apiKey, "googleanalytics4", accountId,
    ["account_id", "new_vs_returning", "sessions", "totalusers", "purchase_revenue", "transactions"], from, to);
  return safetyFilterByAccount(rows, accountId);
}

// ── Shopify (מקור אמת להכנסות / הזמנות / יחידות) ──
async function fetchShopifyOrders(apiKey, shop, from, to) {
  const rows = await windsorFetch(apiKey, "shopify", shop,
    ["account_id", "date", "order_count", "order_total_price", "order_total_price_amount"], from, to);
  return filterByShop(rows, shop);
}

async function fetchShopifyProducts(apiKey, shop, from, to) {
  const rows = await windsorFetch(apiKey, "shopify", shop,
    ["account_id", "line_item__title", "line_item__quantity", "line_item__price"], from, to);
  return filterByShop(rows, shop);
}

// לקוח חדש/חוזר לפי היסטוריית ההזמנות שלו בחנות (מדויק יותר מ-GA4 שמזהה לפי דפדפן)
async function fetchShopifyNewVsReturning(apiKey, shop, from, to) {
  const rows = await windsorFetch(apiKey, "shopify", shop,
    ["account_id", "order_new_or_returning_customer", "order_count", "order_total_price", "order_total_price_amount"], from, to);
  return filterByShop(rows, shop);
}

// קודי הנחה — ברמת שורת מוצר, כמו דוח ההנחות של שופיפיי (Analytics › Discounts)
async function fetchShopifyDiscounts(apiKey, shop, from, to) {
  const fields = ["account_id", "date", "order_id", "order_discount_codes", "order_taxes_included",
    "line_item__id", "line_item__price", "line_item__quantity", "line_item__discount_allocations_obj",
    "line_item__tax_lines_obj", "line_item__refunds_subtotal", "line_item__refunds_total_tax"];
  let rows;
  try {
    rows = await windsorFetch(apiKey, "shopify", shop, fields, from, to, 1, ["order_discount_codes", "neq", ""]);
  } catch (e) {
    rows = await windsorFetch(apiKey, "shopify", shop, fields, from, to); // בלי הפילטר הנוסף
  }
  return filterByShop(rows, shop);
}

// מקור ההזמנה לפי שופיפיי (הביקור האחרון של הלקוח לפני הרכישה)
async function fetchShopifySources(apiKey, shop, from, to) {
  const rows = await windsorFetch(apiKey, "shopify", shop,
    ["account_id", "order_customer_last_visit_utm_source", "order_customer_last_visit_source", "order_count", "order_total_price", "order_total_price_amount"], from, to);
  return filterByShop(rows, shop);
}

// ברוטו = לפני החזרות (order_total_price_amount), נטו = אחרי החזרות (order_total_price)
function grossOf(row) {
  const g = parseFloat(row.order_total_price_amount);
  return isNaN(g) ? num(row.order_total_price) : g;
}

function filterByShop(rows, shop) {
  if (!Array.isArray(rows)) return [];
  const target = String(shop).toLowerCase();
  return rows.filter(r => !r.account_id || String(r.account_id).toLowerCase() === target);
}

function processShopify(orders, products, newReturning) {
  let revenue = 0, gross = 0, orderCount = 0;
  const dailyMap = {};
  for (const row of (orders || [])) {
    const rev = num(row.order_total_price), grs = grossOf(row), cnt = num(row.order_count);
    revenue += rev; gross += grs; orderCount += cnt;
    const d = String(row.date || "").slice(5, 10); // MM-DD
    if (!d) continue;
    if (!dailyMap[d]) dailyMap[d] = { rev: 0, gross: 0, orders: 0 };
    dailyMap[d].rev += rev;
    dailyMap[d].gross += grs;
    dailyMap[d].orders += cnt;
  }
  const dates = Object.keys(dailyMap).sort();

  const productMap = {};
  let units = 0;
  for (const row of (products || [])) {
    const name = row.line_item__title;
    const qty = num(row.line_item__quantity);
    units += qty;
    if (!name) continue;
    if (!productMap[name]) productMap[name] = { name, revenue: 0, qty: 0 };
    productMap[name].revenue += num(row.line_item__price) * qty;
    productMap[name].qty += qty;
  }
  const topProducts = Object.values(productMap)
    .filter(p => p.qty > 0)
    .sort((a, b) => b.revenue - a.revenue)
    .slice(0, 10)
    .map(p => ({ name: p.name, revenue: Math.round(p.revenue), qty: Math.round(p.qty) }));

  return {
    revenue: Math.round(revenue),            // נטו — אחרי החזרות
    gross_revenue: Math.round(gross),        // ברוטו — לפני החזרות
    returns: Math.round(Math.max(0, gross - revenue)),
    orders: Math.round(orderCount),
    units: Math.round(units),
    aov: orderCount > 0 ? Math.round(revenue / orderCount) : 0,
    daily: {
      dates,
      revenue: dates.map(d => Math.round(dailyMap[d].rev)),
      gross: dates.map(d => Math.round(dailyMap[d].gross)),
      orders: dates.map(d => Math.round(dailyMap[d].orders)),
    },
    top_products: topProducts,
    new_vs_returning: summarizeShopifyNewReturning(newReturning),
  };
}

function summarizeShopifyNewReturning(rows) {
  if (!Array.isArray(rows) || rows.length === 0) return null;
  const out = { new: { orders: 0, revenue: 0 }, returning: { orders: 0, revenue: 0 } };
  for (const row of rows) {
    const t = String(row.order_new_or_returning_customer || "").toLowerCase();
    const target = t === "new" ? out.new : t === "returning" ? out.returning : null;
    if (!target) continue;
    target.orders += num(row.order_count);
    target.revenue += num(row.order_total_price);
    target.gross = (target.gross || 0) + grossOf(row);
  }
  if (out.new.orders + out.returning.orders === 0) return null;
  for (const k of ["new", "returning"]) {
    out[k].orders = Math.round(out[k].orders);
    out[k].revenue = Math.round(out[k].revenue);
    out[k].gross = Math.round(out[k].gross || 0);
  }
  return out;
}

// קודי הנחה — אותן הגדרות כמו דוח ההנחות של שופיפיי (לפני מע"מ):
//   Gross sales  = מחיר שורות המוצר שקיבלו את ההנחה, לפני ההנחה
//   Sales reversals = החזרות על השורות האלה (בהזמנות מהתקופה)
//   Net sales    = Gross − הנחות − החזרות
//   Total sales  = Net + מע"מ
// הזמנה עם כמה קודים נספרת תחת כל אחד מהם. קודים פנימיים (Replace / CustomerSupport) נכללים.
function parseObj(v) {
  if (Array.isArray(v)) return v;
  if (typeof v === "string" && v.trim().startsWith("[")) { try { return JSON.parse(v); } catch (e) {} }
  return [];
}
const r2 = x => Math.round(x * 100) / 100;

function summarizeShopifyDiscounts(rows) {
  const map = {};
  const summary = { orders: new Set(), gross: 0, reversals: 0, net: 0, tax: 0 };
  const get = code => (map[code] ||= { code, orders: new Set(), gross: 0, reversals: 0, net: 0, tax: 0 });

  for (const row of (rows || [])) {
    const codes = [...new Set(String(row.order_discount_codes || "").split(/[;,]/).map(c => c.trim()).filter(Boolean))];
    if (!codes.length || row.line_item__id == null || row.line_item__id === "") continue;
    for (const c of codes) get(c).orders.add(String(row.order_id));
    summary.orders.add(String(row.order_id));

    const allocs = parseObj(row.line_item__discount_allocations_obj);
    if (!allocs.length) continue;
    const amounts = allocs.map(a => num(a?.allocatedAmountSet?.shopMoney?.amount));
    const discTotal = amounts.reduce((x, y) => x + y, 0);
    const lineTotal = num(row.line_item__price) * num(row.line_item__quantity);
    const after = lineTotal - discTotal;
    const tax = parseObj(row.line_item__tax_lines_obj).reduce((x, t) => x + num(t?.priceSet?.shopMoney?.amount), 0);
    const included = row.order_taxes_included === true || String(row.order_taxes_included).toLowerCase() === "true";

    let gross, net;
    if (included) {
      net = after - tax;
      gross = after > 0.005 ? r2(lineTotal * net / after) : lineTotal;
    } else {
      net = after;
      gross = lineTotal;
    }
    const refTax = num(row.line_item__refunds_total_tax);
    const reversal = Math.max(0, num(row.line_item__refunds_subtotal) - (included ? refTax : 0));
    const lineTax = included ? tax - refTax : tax;

    summary.gross += gross; summary.reversals += reversal; summary.net += net - reversal; summary.tax += lineTax;
    allocs.forEach((a, i) => {
      const idx = a?.discountApplication?.index ?? 0;
      const code = codes[idx] !== undefined ? codes[idx] : codes[0];
      const share = discTotal > 0 ? amounts[i] / discTotal : 1 / allocs.length;
      const t = get(code);
      t.gross += gross * share; t.reversals += reversal * share; t.net += (net - reversal) * share; t.tax += lineTax * share;
    });
  }

  const fmt = t => ({
    code: t.code, orders: t.orders.size,
    gross: r2(t.gross), reversals: r2(-t.reversals), net: r2(t.net), total: r2(t.net + t.tax),
    revenue: r2(t.net), // תאימות לאחור לדשבורדים אחרים
  });
  const codes = Object.values(map).map(fmt).sort((a, b) => b.net - a.net || b.orders - a.orders || a.code.localeCompare(b.code));
  return {
    basis: "shopify_analytics_discounts",
    orders_with_code: summary.orders.size,
    summary: { orders: summary.orders.size, gross: r2(summary.gross), reversals: r2(-summary.reversals), net: r2(summary.net), total: r2(summary.net + summary.tax) },
    codes,
  };
}

// מיפוי מקור ביקור → ערוץ (Meta / Google / TikTok / Email / Direct / Other / Unknown)
function classifyShopifySource(utm, src) {
  const u = String(utm || "").toLowerCase().trim();
  const s = String(src || "").toLowerCase().trim();
  if (/^(ig|fb|facebook|instagram|meta)/.test(u) || /facebook|instagram/.test(s)) return "Meta";
  if (u.includes("google") || s.includes("google")) return "Google";
  if (u.includes("tiktok") || s.includes("tiktok")) return "TikTok";
  if (/mail|klaviyo|newsletter|sms/.test(u)) return "Email/SMS";
  if (u) return "Other";
  if (s === "direct") return "Direct";
  if (!s || s === "an unknown source") return "Unknown";
  return "Other";
}

function summarizeShopifySources(rows) {
  const map = {};
  for (const row of (rows || [])) {
    const ch = classifyShopifySource(row.order_customer_last_visit_utm_source, row.order_customer_last_visit_source);
    if (!map[ch]) map[ch] = { channel: ch, orders: 0, revenue: 0, gross: 0 };
    map[ch].orders += num(row.order_count);
    map[ch].revenue += num(row.order_total_price);
    map[ch].gross += grossOf(row);
  }
  return Object.values(map)
    .filter(c => c.orders > 0)
    .sort((a, b) => b.gross - a.gross)
    .map(c => ({ channel: c.channel, orders: Math.round(c.orders), revenue: Math.round(c.revenue), gross: Math.round(c.gross) }));
}

// ── Klaviyo (דיוור: הכנסה מקמפיינים ו-Flows, צמיחת רשימה, "חזר למלאי") ──
// משיכה ישירה מה-API של קלאביו. ה-Reporting API של קלאביו מוגבל מאוד (בערך 2 קריאות לדקה, 225 ליום),
// לכן התוצאה נשמרת בזיכרון (ובאופציה ב-KV) לכמה שעות לכל טווח תאריכים.
const KLAVIYO_BASE = "https://a.klaviyo.com/api";
const KLAVIYO_REVISION = "2025-01-15";
const KLAVIYO_TTL_SEC = 3 * 60 * 60; // 3 שעות
const KLAVIYO_TZ = "+03:00";
const klaviyoMemCache = new Map();

async function fetchKlaviyo(env, clientKey, cfg, from, to) {
  const key = env[cfg.keyEnv];
  if (!key) throw new Error(`Klaviyo: missing secret ${cfg.keyEnv}`);

  const cacheKey = `klaviyo:${clientKey}:${from}:${to}`;
  const mem = klaviyoMemCache.get(cacheKey);
  if (mem && mem.exp > Date.now()) return mem.data;
  if (env.KLAVIYO_CACHE) {
    try {
      const kv = await env.KLAVIYO_CACHE.get(cacheKey, "json");
      if (kv) { klaviyoMemCache.set(cacheKey, { data: kv, exp: Date.now() + KLAVIYO_TTL_SEC * 1000 }); return kv; }
    } catch (e) { /* ממשיכים בלי KV */ }
  }

  const k = (path, opts = {}) => klaviyoRequest(key, path, opts);
  const metrics = await klaviyoMetricIds(k);
  if (!metrics.placedOrderAll.length) throw new Error("Klaviyo: 'Placed Order' metric not found");

  const timeframe = { start: `${from}T00:00:00${KLAVIYO_TZ}`, end: `${to}T23:59:59${KLAVIYO_TZ}` };
  const stats = ["recipients", "delivered", "opens_unique", "clicks_unique", "conversions", "conversion_value", "unsubscribes"];

  // דוחות הקמפיינים וה-Flows מוגבלים לקריאה אחת בשנייה, לכן ברצף עם הפסקה קצרה
  const report = (type, metricId) => k(`/${type}s/`, { method: "POST", body: { data: { type,
    attributes: { statistics: stats, timeframe, conversion_metric_id: metricId } } } });
  const aggsP = klaviyoListAggregates(k, metrics, from, to);

  // לא כל מטריקת "Placed Order" תומכת בדוחות ערך — מנסים לפי הסדר עד שאחת עובדת
  let convMetric = null, campRes = null;
  const tried = [];
  for (const cand of metrics.placedOrderAll) {
    const [r] = await Promise.allSettled([report("campaign-values-report", cand.id)]);
    if (r.status === "fulfilled") { convMetric = cand.id; campRes = r; break; }
    tried.push(`${cand.id}(${cand.integration || "?"})`);
    campRes = r;
    if (!/conversion metric/i.test(r.reason?.message || "")) break; // שגיאה אחרת (למשל rate limit) — לא ממשיכים לנסות
    await new Promise(res => setTimeout(res, 1100));
  }
  let campaigns, flows, flowRes, aggs, source = "reports";
  if (convMetric) {
    await new Promise(r => setTimeout(r, 1100));
    [flowRes, aggs] = await Promise.allSettled([report("flow-values-report", convMetric), aggsP]);
    if (campRes.status === "rejected" && flowRes.status === "rejected") throw campRes.reason;
    campaigns = campRes.status === "fulfilled" ? groupKlaviyoRows(campRes.value, "campaign_id") : [];
    flows = flowRes.status === "fulfilled" ? groupKlaviyoRows(flowRes.value, "flow_id") : [];
  } else {
    // דרך חלופית: הזמנות והכנסה ישירות מאירועי ההזמנה ומהשיוך שלהם לקמפיין/Flow
    if (!/conversion metric/i.test(campRes?.reason?.message || "")) throw campRes.reason;
    source = "events";
    const fb = await Promise.allSettled([klaviyoAttributionFromEvents(k, metrics, from, to), aggsP]);
    if (fb[0].status === "rejected") throw new Error(`Klaviyo fallback failed (tried ${tried.join(", ")}): ${fb[0].reason?.message || ""}`.slice(0, 400));
    ({ campaigns, flows } = fb[0].value);
    flowRes = { status: "fulfilled" };
    aggs = fb[1];
  }

  // שמות — רק למה שמוצג (טופ 10), כדי לחסוך קריאות
  campaigns.sort((a, b) => b.revenue - a.revenue || b.recipients - a.recipients);
  flows.sort((a, b) => b.revenue - a.revenue || b.recipients - a.recipients);
  const topCampaigns = campaigns.slice(0, 10), topFlows = flows.slice(0, 10);
  const nameJobs = [
    ...topCampaigns.map(c => async () => {
      try {
        const r = await k(`/campaigns/${c.id}/?fields[campaign]=name,send_time`);
        c.name = r?.data?.attributes?.name || c.id;
        c.send_time = r?.data?.attributes?.send_time || null;
      } catch (e) {
        // במסלול האירועים המזהה יכול להיות של הודעת הקמפיין ולא של הקמפיין עצמו
        const r = await k(`/campaign-messages/${c.id}/?include=campaign&fields[campaign]=name,send_time`);
        const camp = (r?.included || []).find(x => x.type === "campaign");
        c.name = camp?.attributes?.name || c.id;
        c.send_time = camp?.attributes?.send_time || null;
      }
    }),
    ...topFlows.map(f => async () => {
      const r = await k(`/flows/${f.id}/?fields[flow]=name,status`);
      f.name = r?.data?.attributes?.name || f.id;
      f.status = r?.data?.attributes?.status || null;
    }),
  ];
  for (let i = 0; i < nameJobs.length; i += 3) {
    await Promise.allSettled(nameJobs.slice(i, i + 3).map(j => j()));
  }

  const sum = (arr, f) => arr.reduce((a, x) => a + (x[f] || 0), 0);
  const campRev = sum(campaigns, "revenue"), flowRev = sum(flows, "revenue");
  const a = aggs.status === "fulfilled" ? aggs.value : {};
  const round = x => ({ ...x, revenue: Math.round(x.revenue) });

  const data = {
    revenue: Math.round(campRev + flowRev),
    campaign_revenue: Math.round(campRev),
    flow_revenue: Math.round(flowRev),
    orders: Math.round(sum(campaigns, "orders") + sum(flows, "orders")),
    campaigns_sent: campaigns.length,
    recipients: Math.round(sum(campaigns, "recipients")),
    campaigns: topCampaigns.map(round),
    flows: topFlows.map(round),
    list: { subscribed: a.subscribed ?? null, unsubscribed: a.unsubscribed ?? null },
    back_in_stock: a.backInStock || null, // 0 לא מוצג
    updated_at: new Date().toISOString(),
    partial: (source === "reports" && (campRes.status === "rejected" || flowRes.status === "rejected")) || aggs.status === "rejected",
    source,
  };

  if (data.orders > 0 || data.recipients > 0) klaviyoMemCache.set(cacheKey, { data, exp: Date.now() + KLAVIYO_TTL_SEC * 1000 });
  if (env.KLAVIYO_CACHE && !data.partial && (data.orders > 0 || data.recipients > 0)) {
    try { await env.KLAVIYO_CACHE.put(cacheKey, JSON.stringify(data), { expirationTtl: KLAVIYO_TTL_SEC }); } catch (e) {}
  }
  return data;
}

async function klaviyoRequest(key, path, { method = "GET", body } = {}, attempt = 0) {
  const res = await fetch(KLAVIYO_BASE + path, {
    method,
    headers: {
      Authorization: `Klaviyo-API-Key ${key}`,
      revision: KLAVIYO_REVISION,
      accept: "application/vnd.api+json",
      ...(body ? { "content-type": "application/vnd.api+json" } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  // קלאביו מגביל קצב — על 429 מחכים ומנסים שוב (עד 3 פעמים)
  if (res.status === 429 && attempt < 3) {
    const wait = Math.min(5, Math.max(1, parseFloat(res.headers.get("retry-after")) || attempt + 1));
    await new Promise(r => setTimeout(r, wait * 1000));
    return klaviyoRequest(key, path, { method, body }, attempt + 1);
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Klaviyo ${path.split("?")[0]} HTTP ${res.status}: ${text.slice(0, 200)}`);
  }
  return res.json();
}

// מזהי המטריקות לפי שם (שופיפיי + שיווק)
async function klaviyoMetricIds(k) {
  const want = {
    placedOrder: "Placed Order",
    subscribed: "Subscribed to Email Marketing",
    unsubscribed: "Unsubscribed from Email Marketing",
    backInStock: "Subscribed to Back in Stock",
    receivedEmail: "Received Email",
    clickedEmail: "Clicked Email",
  };
  const found = { placedOrderAll: [] };
  let url = "/metrics/?fields[metric]=name,integration";
  for (let page = 0; url && page < 5; page++) {
    const r = await k(url);
    for (const m of (r.data || [])) {
      const name = m.attributes?.name;
      if (name === want.placedOrder) {
        const integ = m.attributes?.integration?.name || "";
        found.placedOrderAll.push({ id: m.id, integration: integ, shopify: /shopify/i.test(integ) });
      }
      for (const [k2, label] of Object.entries(want)) {
        if (name !== label) continue;
        // ל-Placed Order מעדיפים את זה שמגיע משופיפיי
        const isShopify = /shopify/i.test(m.attributes?.integration?.name || "");
        if (!found[k2] || (k2 === "placedOrder" && isShopify)) found[k2] = m.id;
      }
    }
    const next = r.links?.next;
    url = next ? next.replace(KLAVIYO_BASE, "") : null;
  }
  // שופיפיי קודם, אחר כך השאר
  found.placedOrderAll.sort((a, b) => (b.shopify ? 1 : 0) - (a.shopify ? 1 : 0));
  return found;
}

// ספירות לתקופה: נרשמים, הסרות, הרשמות "חזר למלאי"
async function klaviyoListAggregates(k, metrics, from, to) {
  const count = async id => {
    if (!id) return null;
    const r = await k("/metric-aggregates/", { method: "POST", body: { data: { type: "metric-aggregate", attributes: {
      metric_id: id, measurements: ["count"], interval: "month",
      filter: [`greater-or-equal(datetime,${from}T00:00:00${KLAVIYO_TZ})`, `less-than(datetime,${nextDay(to)}T00:00:00${KLAVIYO_TZ})`],
      timezone: "Asia/Jerusalem",
    } } } });
    const series = r?.data?.attributes?.data?.[0]?.measurements?.count || [];
    return Math.round(series.reduce((a, x) => a + (x || 0), 0));
  };
  const [subscribed, unsubscribed, backInStock] = await Promise.all([
    count(metrics.subscribed), count(metrics.unsubscribed), count(metrics.backInStock),
  ]);
  return { subscribed, unsubscribed, backInStock };
}

async function klaviyoDebug(env, cfg, from, to) {
  const k = (path, opts = {}) => klaviyoRequest(env[cfg.keyEnv], path, opts);
  const out = { metrics: [] };
  let url = "/metrics/?fields[metric]=name,integration";
  for (let page = 0; url && page < 5; page++) {
    const r = await k(url);
    for (const m of (r.data || [])) out.metrics.push(`${m.id} | ${m.attributes?.name} | ${m.attributes?.integration?.name || ""}`);
    url = r.links?.next ? r.links.next.replace(KLAVIYO_BASE, "") : null;
  }
  const ids = await klaviyoMetricIds(k);
  out.resolved = ids;
  const po = ids.placedOrderAll[0]?.id;
  const filter = [`greater-or-equal(datetime,${from}T00:00:00${KLAVIYO_TZ})`, `less-than(datetime,${nextDay(to)}T00:00:00${KLAVIYO_TZ})`];
  const agg = async (id, by, measurements) => {
    try {
      const r = await k("/metric-aggregates/", { method: "POST", body: { data: { type: "metric-aggregate", attributes: {
        metric_id: id, measurements, interval: "month", filter, timezone: "Asia/Jerusalem", ...(by ? { by } : {}) } } } });
      const rows = r?.data?.attributes?.data || [];
      return { dates: r?.data?.attributes?.dates, rows: rows.length, sample: rows.slice(0, 8) };
    } catch (e) { return { error: e.message }; }
  };
  if (po) {
    out.placed_total = await agg(po, null, ["count", "sum_value"]);
    out.placed_by_attr = await agg(po, ["$attributed_flow", "$attributed_message"], ["count", "sum_value"]);
    out.placed_by_channel = await agg(po, ["$attributed_channel"], ["count", "sum_value"]);
  }
  if (ids.receivedEmail) out.received_by = await agg(ids.receivedEmail, ["$flow", "$message"], ["count"]);
  try {
    const c = await k("/campaigns/?filter=equals(messages.channel,'email')&fields[campaign]=name,send_time,status&sort=-created_at");
    out.recent_email_campaigns = (c.data || []).slice(0, 5).map(x => `${x.id} | ${x.attributes?.name} | ${x.attributes?.status} | ${x.attributes?.send_time}`);
  } catch (e) { out.recent_email_campaigns = e.message; }
  try {
    const f = await k("/flows/?fields[flow]=name,status");
    out.flows = (f.data || []).slice(0, 15).map(x => `${x.id} | ${x.attributes?.name} | ${x.attributes?.status}`);
  } catch (e) { out.flows = e.message; }
  return out;
}

// אגרגציה של מטריקה לפי מאפיינים (למשל שיוך לקמפיין/Flow) — מחזיר מפה dimensions→{count,sum}
async function klaviyoAggregateBy(k, metricId, by, measurements, from, to) {
  const r = await k("/metric-aggregates/", { method: "POST", body: { data: { type: "metric-aggregate", attributes: {
    metric_id: metricId, measurements, by, interval: "month",
    filter: [`greater-or-equal(datetime,${from}T00:00:00${KLAVIYO_TZ})`, `less-than(datetime,${nextDay(to)}T00:00:00${KLAVIYO_TZ})`],
    timezone: "Asia/Jerusalem",
  } } } });
  return (r?.data?.attributes?.data || []).map(row => {
    const out = { dims: row.dimensions || [] };
    for (const m of measurements) out[m] = (row.measurements?.[m] || []).reduce((a, x) => a + (x || 0), 0);
    return out;
  });
}

async function klaviyoAttributionFromEvents(k, metrics, from, to) {
  const ids = metrics.placedOrderAll.map(c => c.id);
  const flowMap = {}, campMap = {};
  const blank = id => ({ id, name: id, channel: "email", recipients: 0, delivered: 0, opens: 0, clicks: 0, orders: 0, revenue: 0, unsubscribes: 0 });
  const add = (map, id, f, v) => { if (!id) return; if (!map[id]) map[id] = blank(id); map[id][f] += v; };

  // הזמנות + הכנסה לפי שיוך
  let orderRows = null, lastErr;
  for (const id of ids) {
    try { orderRows = await klaviyoAggregateBy(k, id, ["$attributed_flow", "$attributed_message"], ["count", "sum_value"], from, to); break; }
    catch (e) { lastErr = e; }
  }
  if (!orderRows) throw lastErr || new Error("no order data");
  for (const r of orderRows) {
    const [flow, msg] = r.dims;
    if (flow) { add(flowMap, flow, "orders", r.count); add(flowMap, flow, "revenue", r.sum_value); }
    else if (msg) { add(campMap, msg, "orders", r.count); add(campMap, msg, "revenue", r.sum_value); }
  }

  // נמענים והקלקות (אימייל בלבד) — אם נכשל, נשארים עם הכנסות בלבד
  const engagement = async (metricId, field) => {
    if (!metricId) return;
    const rows = await klaviyoAggregateBy(k, metricId, ["$flow", "$message"], ["count"], from, to);
    for (const r of rows) {
      const [flow, msg] = r.dims;
      if (flow) add(flowMap, flow, field, r.count);
      else if (msg) add(campMap, msg, field, r.count);
    }
  };
  await Promise.allSettled([engagement(metrics.receivedEmail, "recipients"), engagement(metrics.clickedEmail, "clicks")]);

  const finish = m => Object.values(m).map(x => ({
    ...x, delivered: x.recipients,
    click_rate: x.recipients > 0 ? +(x.clicks / x.recipients * 100).toFixed(2) : 0,
    rev_per_recipient: x.recipients > 0 ? +(x.revenue / x.recipients).toFixed(2) : 0,
  })).filter(x => x.orders > 0 || x.recipients > 0);
  return { campaigns: finish(campMap), flows: finish(flowMap) };
}

function nextDay(d) {
  const t = new Date(d + "T00:00:00Z");
  t.setUTCDate(t.getUTCDate() + 1);
  return t.toISOString().slice(0, 10);
}

// איחוד שורות הדוח לפי קמפיין/Flow (הדוח מפצל לפי הודעה וערוץ)
function groupKlaviyoRows(res, idField) {
  const map = {};
  for (const row of (res?.data?.attributes?.results || [])) {
    const id = row.groupings?.[idField];
    if (!id) continue;
    const st = row.statistics || {};
    const ch = row.groupings?.send_channel || "email";
    if (!map[id]) map[id] = { id, name: id, channel: ch, recipients: 0, delivered: 0, opens: 0, clicks: 0, orders: 0, revenue: 0, unsubscribes: 0 };
    const m = map[id];
    if (m.channel !== ch) m.channel = "multi";
    m.recipients += num(st.recipients);
    m.delivered += num(st.delivered);
    m.opens += num(st.opens_unique);
    m.clicks += num(st.clicks_unique);
    m.orders += num(st.conversions);
    m.revenue += num(st.conversion_value);
    m.unsubscribes += num(st.unsubscribes);
  }
  return Object.values(map).map(m => ({
    ...m,
    click_rate: m.delivered > 0 ? +(m.clicks / m.delivered * 100).toFixed(2) : 0,
    rev_per_recipient: m.recipients > 0 ? +(m.revenue / m.recipients).toFixed(2) : 0,
  }));
}

// ── עיבוד נתונים ──
function processData(client, meta, google, ga4, channels, daily, from, to, ga4Products, ga4Campaigns, ga4NewReturning, metaCreatives) {
  // GA4 totals
  let ga4Rev = 0, ga4Trans = 0, ga4Sessions = 0, ga4Atc = 0, ga4Checkouts = 0;
  for (const row of ga4) {
    ga4Rev += num(row.purchase_revenue);
    ga4Trans += num(row.transactions);
    ga4Sessions += num(row.sessions);
    ga4Atc += num(row.add_to_carts);
    ga4Checkouts += num(row.checkouts);
  }

  // Meta aggregation by campaign
  const metaCampaigns = {};
  let metaSpend = 0, metaValue = 0, metaPurch = 0;
  for (const row of meta) {
    const name = row.campaign || "Unknown";
    const spend = num(row.spend), rev = num(row.action_values_omni_purchase), conv = num(row.actions_omni_purchase);
    if (!metaCampaigns[name]) metaCampaigns[name] = { name, spend: 0, value: 0, purch: 0 };
    metaCampaigns[name].spend += spend;
    metaCampaigns[name].value += rev;
    metaCampaigns[name].purch += conv;
    metaSpend += spend; metaValue += rev; metaPurch += conv;
  }
  const metaList = Object.values(metaCampaigns)
    .filter(c => c.spend > 0)
    .map(c => ({ ...c, roas: c.spend > 0 ? c.value / c.spend : 0 }))
    .sort((a, b) => b.spend - a.spend).slice(0, 10);

  // Google aggregation + brand/nonbrand
  const googleCampaigns = {};
  let gSpend = 0, gValue = 0, brandSpend = 0, brandVal = 0, nonbrandSpend = 0, nonbrandVal = 0;
  for (const row of google) {
    const name = row.campaign || "Unknown";
    const spend = num(row.spend), val = num(row.conversions_value);
    const isBrand = /brand|ברנד/i.test(name);
    if (!googleCampaigns[name]) googleCampaigns[name] = { name, spend: 0, value: 0, type: isBrand ? "brand" : "nonbrand" };
    googleCampaigns[name].spend += spend;
    googleCampaigns[name].value += val;
    gSpend += spend; gValue += val;
    if (isBrand) { brandSpend += spend; brandVal += val; }
    else { nonbrandSpend += spend; nonbrandVal += val; }
  }
  const googleList = Object.values(googleCampaigns)
    .filter(c => c.spend > 0)
    .map(c => ({ ...c, roas: c.spend > 0 ? c.value / c.spend : 0 }))
    .sort((a, b) => b.spend - a.spend);

  // Channels
  const channelMap = {};
  for (const row of channels) {
    const ch = row.session_default_channel_group || "Other";
    channelMap[ch] = (channelMap[ch] || 0) + num(row.purchase_revenue);
  }

  // Daily series
  const dailyMap = {};
  for (const row of daily) {
    const d = (row.date || "").slice(5); // MM-DD
    if (!dailyMap[d]) dailyMap[d] = { rev: 0, sessions: 0 };
    dailyMap[d].rev += num(row.purchase_revenue);
    dailyMap[d].sessions += num(row.sessions);
  }
  const dates = Object.keys(dailyMap).sort();
  const dailyRev = dates.map(d => Math.round(dailyMap[d].rev));
  const dailySessions = dates.map(d => Math.round(dailyMap[d].sessions));

  // ── דוח 1: טופ 10 מוצרים (Best Seller) ──
  const productMap = {};
  for (const row of (ga4Products || [])) {
    const name = row.item_name;
    if (!name || name === "(not set)") continue;
    const rev = num(row.item_revenue), qty = num(row.items_purchased);
    if (!productMap[name]) productMap[name] = { name, revenue: 0, qty: 0 };
    productMap[name].revenue += rev;
    productMap[name].qty += qty;
  }
  const topProducts = Object.values(productMap)
    .filter(p => p.revenue > 0)
    .sort((a, b) => b.revenue - a.revenue)
    .slice(0, 10)
    .map(p => ({ name: p.name, revenue: Math.round(p.revenue), qty: Math.round(p.qty) }));

  // ── דוח 2: טופ 10 קמפיינים לפי GA4 ──
  // סינון ערכים טכניים שאינם קמפיינים אמיתיים
  const EXCLUDE_CAMPAIGNS = new Set(["(not set)", "(organic)", "(direct)", "(referral)",
    "(cross-network)", "(ai-assistant)", "(other)", "direct", "", "{{campaign.name}}"]);
  const campaignMap = {};
  for (const row of (ga4Campaigns || [])) {
    const name = row.campaign_name;
    if (!name || EXCLUDE_CAMPAIGNS.has(name)) continue;
    const rev = num(row.purchase_revenue), trans = num(row.transactions), sess = num(row.sessions);
    if (!campaignMap[name]) campaignMap[name] = { name, revenue: 0, transactions: 0, sessions: 0 };
    campaignMap[name].revenue += rev;
    campaignMap[name].transactions += trans;
    campaignMap[name].sessions += sess;
  }
  const topCampaigns = Object.values(campaignMap)
    .filter(c => c.revenue > 0)
    .sort((a, b) => b.revenue - a.revenue)
    .slice(0, 10)
    .map(c => ({ name: c.name, revenue: Math.round(c.revenue),
                 transactions: Math.round(c.transactions), sessions: Math.round(c.sessions) }));

  const totalSpend = metaSpend + gSpend;

  // ── דוח חדש 3: לקוחות חדשים מול חוזרים ──
  let newUsers = { sessions: 0, users: 0, revenue: 0, transactions: 0 };
  let returningUsers = { sessions: 0, users: 0, revenue: 0, transactions: 0 };
  for (const row of (ga4NewReturning || [])) {
    const type = (row.new_vs_returning || "").toLowerCase();
    const target = type === "new" ? newUsers : type === "returning" ? returningUsers : null;
    if (!target) continue;
    target.sessions += num(row.sessions);
    target.users += num(row.totalusers);
    target.revenue += num(row.purchase_revenue);
    target.transactions += num(row.transactions);
  }
  const hasNewReturningData = (newUsers.sessions + returningUsers.sessions) > 0;

  // ── ביצועי קריאייטיב (Meta) — קיבוץ לפי ad_id ייחודי, לא לפי שם (שמות עלולים לחזור על עצמם) ──
  const creativeMap = {};
  for (const row of (metaCreatives || [])) {
    const id = row.ad_id;
    const name = row.ad_name;
    if (!id || !name) continue;
    const spend = num(row.spend);
    const thumb = row.thumbnail_url || "";
    if (!creativeMap[id]) creativeMap[id] = { name, thumbnail: thumb, spend: 0, value: 0, purch: 0 };
    creativeMap[id].spend += spend;
    creativeMap[id].value += num(row.action_values_omni_purchase);
    creativeMap[id].purch += num(row.actions_omni_purchase);
    if (!creativeMap[id].thumbnail && thumb) creativeMap[id].thumbnail = thumb;
  }
  const topCreatives = Object.values(creativeMap)
    .filter(c => c.spend > 0)
    .map(c => ({ ...c, spend: +c.spend.toFixed(2), value: +c.value.toFixed(2),
                 roas: c.spend > 0 ? +(c.value / c.spend).toFixed(2) : 0 }))
    .sort((a, b) => b.spend - a.spend)
    .slice(0, 15);

  return {
    client: client.name,
    period: { from, to },
    ga4: { revenue: Math.round(ga4Rev), transactions: ga4Trans, sessions: ga4Sessions, atc: ga4Atc, checkouts: ga4Checkouts },
    meta: { spend: +metaSpend.toFixed(2), value: +metaValue.toFixed(2), purch: metaPurch,
            roas: metaSpend > 0 ? +(metaValue / metaSpend).toFixed(2) : 0 },
    google: { spend: Math.round(gSpend), value: Math.round(gValue),
              roas: gSpend > 0 ? +(gValue / gSpend).toFixed(2) : 0,
              brand: { spend: Math.round(brandSpend), value: Math.round(brandVal), roas: brandSpend > 0 ? +(brandVal / brandSpend).toFixed(1) : 0 },
              nonbrand: { spend: Math.round(nonbrandSpend), value: Math.round(nonbrandVal), roas: nonbrandSpend > 0 ? +(nonbrandVal / nonbrandSpend).toFixed(2) : 0 } },
    blended_roas: totalSpend > 0 ? +(ga4Rev / totalSpend).toFixed(1) : 0,
    meta_campaigns: metaList,
    google_campaigns: googleList,
    channels: channelMap,
    daily: { dates, revenue: dailyRev, sessions: dailySessions },
    top_products: topProducts,
    top_campaigns: topCampaigns,
    new_vs_returning: hasNewReturningData ? {
      new: { sessions: Math.round(newUsers.sessions), users: Math.round(newUsers.users), revenue: Math.round(newUsers.revenue), transactions: Math.round(newUsers.transactions) },
      returning: { sessions: Math.round(returningUsers.sessions), users: Math.round(returningUsers.users), revenue: Math.round(returningUsers.revenue), transactions: Math.round(returningUsers.transactions) },
    } : null,
    top_creatives: topCreatives,
  };
}

function num(v) { return parseFloat(v) || 0; }

function json(obj, status, cors) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json;charset=UTF-8", ...cors },
  });
}

// ── ChatGPT Ads (OpenAI Ads API) ──
const OPENAI_ADS_BASE = "https://api.ads.openai.com/v1";
const CHATGPT_TZ = "Asia/Jerusalem";
const CHATGPT_BASE_FIELDS = ["campaign_id", "campaign_name", "spend", "impressions", "clicks"];
const CHATGPT_CONV_FIELDS = ["conversions", "order_created_attributed_sales", "order_created_attributed_sales_currency"];

async function openaiAdsGet(key, path, params) {
  const qs = new URLSearchParams();
  for (const [k, v] of params) qs.append(k, v);
  const res = await fetch(`${OPENAI_ADS_BASE}${path}${params.length ? "?" + qs.toString() : ""}`, {
    headers: { Authorization: `Bearer ${key}`, Accept: "application/json" },
  });
  const text = await res.text();
  let body; try { body = JSON.parse(text); } catch { body = { raw: text.slice(0, 500) }; }
  if (!res.ok) {
    const msg = body?.error?.message || body?.message || body?.raw || `HTTP ${res.status}`;
    const err = new Error(`OpenAI Ads ${res.status}: ${msg}`); err.status = res.status; err.body = body; throw err;
  }
  return body;
}

async function chatgptInsights(key, from, to, fields) {
  const rows = [];
  let after = null;
  for (let page = 0; page < 10; page++) {
    const params = [
      ["aggregation_level", "campaign"],
      ["time_granularity", "none"],
      ["time_ranges[]", JSON.stringify({ type: "date_range", since: from, until: to, timezone: CHATGPT_TZ })],
      ["limit", "2000"],
      ...fields.map(f => ["fields[]", f]),
    ];
    if (after) params.push(["after", after]);
    const body = await openaiAdsGet(key, "/ad_account/insights", params);
    rows.push(...(body.data || []));
    if (!body.has_more || !body.last_id) break;
    after = body.last_id;
  }
  return rows;
}

const fxCache = new Map();
async function toIlsRate(cur) {
  cur = String(cur || "ILS").toUpperCase();
  if (cur === "ILS") return 1;
  const c = fxCache.get(cur);
  if (c && c.exp > Date.now()) return c.rate;
  for (const u of [`https://open.er-api.com/v6/latest/${cur}`, `https://api.exchangerate-api.com/v4/latest/${cur}`]) {
    try {
      const j = await (await fetch(u)).json();
      const rate = +(j.rates?.ILS);
      if (rate > 0) { fxCache.set(cur, { rate, exp: Date.now() + 6 * 3600 * 1000 }); return rate; }
    } catch (e) { /* ננסה את המקור הבא */ }
  }
  throw new Error(`no FX rate for ${cur}→ILS`);
}

async function fetchChatGPT(env, cfg, from, to, debug = false) {
  const key = env[cfg.keyEnv];
  if (!key) { if (debug) return { error: `missing secret ${cfg.keyEnv}` }; return null; }

  const account = await openaiAdsGet(key, "/ad_account", []).catch(e => ({ _error: e.message }));
  let rows, convAvailable = true, convError = null;
  try {
    rows = await chatgptInsights(key, from, to, [...CHATGPT_BASE_FIELDS, ...CHATGPT_CONV_FIELDS]);
  } catch (e) {
    // בלי המרות מוגדרות (פיקסל) ייתכן ששדות ההמרה נדחים — מושכים רק הוצאה/חשיפות/קליקים
    if (e.status !== 400 && e.status !== 422) throw e;
    convAvailable = false; convError = e.message;
    rows = await chatgptInsights(key, from, to, CHATGPT_BASE_FIELDS);
  }

  if (debug) {
    return { account: account._error ? { error: account._error } : account, conversions_available: convAvailable,
             conversions_error: convError, rows_count: rows.length, rows: rows.slice(0, 20) };
  }

  const currency = String(account.currency || account.account_currency || account.currency_code ||
    rows.find(r => r.order_created_attributed_sales_currency)?.order_created_attributed_sales_currency || "ILS").toUpperCase();
  const fx = await toIlsRate(currency);

  const camps = {};
  for (const r of rows) {
    const id = r.campaign_id || r.campaign_name || "?";
    const c = camps[id] ||= { name: r.campaign_name || id, spend: 0, value: 0, purch: 0, clicks: 0, impressions: 0 };
    c.spend += num(r.spend); c.clicks += num(r.clicks); c.impressions += num(r.impressions);
    c.purch += num(r.conversions);
    if (r.order_created_attributed_sales != null) {
      const vCur = String(r.order_created_attributed_sales_currency || currency).toUpperCase();
      c.value += num(r.order_created_attributed_sales) * (vCur === currency ? fx : await toIlsRate(vCur)) / fx;
    }
  }
  const list = Object.values(camps).map(c => ({
    name: c.name, spend: r2(c.spend * fx), value: convAvailable ? r2(c.value * fx) : null, purch: convAvailable ? Math.round(c.purch) : null,
    clicks: Math.round(c.clicks), impressions: Math.round(c.impressions),
    roas: convAvailable && c.spend > 0 ? r2(c.value / c.spend) : 0,
  })).filter(c => c.spend > 0 || c.impressions > 0).sort((a, b) => b.spend - a.spend);

  const t = list.reduce((a, c) => ({ spend: a.spend + c.spend, value: a.value + (c.value || 0), purch: a.purch + (c.purch || 0),
    clicks: a.clicks + c.clicks, impressions: a.impressions + c.impressions }), { spend: 0, value: 0, purch: 0, clicks: 0, impressions: 0 });

  return {
    spend: r2(t.spend), value: convAvailable ? r2(t.value) : null, purch: convAvailable ? t.purch : null,
    roas: convAvailable && t.spend > 0 ? r2(t.value / t.spend) : 0,
    clicks: t.clicks, impressions: t.impressions,
    ctr: t.impressions > 0 ? +(t.clicks / t.impressions * 100).toFixed(2) : 0,
    cpc: t.clicks > 0 ? r2(t.spend / t.clicks) : 0,
    conversions_available: convAvailable,
    currency_original: currency, fx_rate: fx,
    campaigns: list,
  };
}
