/**
 * Mendtokyo booking worker (Cloudflare Workers, free plan).
 *
 *   GET /book?date=2026-12-02&time=14:00–16:00[&lang=en]
 *       -> finds (or creates) the Square item for that session, checks stock,
 *          creates a fresh single-use Square payment link and redirects the buyer to it.
 *          Sold out -> redirects back to the website.
 *   GET /seats
 *       -> JSON { "2026-12-02 14:00–16:00": 3, ... } live seats left for every Mendtokyo item.
 *
 * Secrets / variables (Worker settings -> Variables and Secrets):
 *   SQUARE_ACCESS_TOKEN  (secret)   SQUARE_LOCATION_ID   SITE_URL (https://threespacetokyo.com)
 *   optional: PRICE_JPY (20000)  DEFAULT_SEATS (4)  SQUARE_ENV ("production" | "sandbox")
 */

const SQUARE_VERSION = "2025-01-23";
const VENUE = "Three Space Tokyo, 3-6-6 Asakusabashi, Taito-ku, Tokyo 111-0053";
const NAME_RE = /^Mendtokyo (\d{2})\/(\d{2})\/(\d{4})(?: (afternoon)| (\d{2}:\d{2})[–-](\d{2}:\d{2}))?/;

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const cors = corsHeaders(env);
    if (request.method === "OPTIONS") return new Response(null, { headers: cors });
    try {
      if (url.pathname === "/seats") return json(await seats(env), cors);
      if (url.pathname === "/book") return await book(url, env);
      return new Response("Mendtokyo booking service", { status: 200 });
    } catch (e) {
      console.log("error", e && e.stack || e);
      const lang = url.searchParams.get("lang") || "en";
      return Response.redirect(sitePage(env, lang) + "?error=1#sessions", 302);
    }
  },
};

// ---------- helpers ----------
function corsHeaders(env) {
  return { "Access-Control-Allow-Origin": env.SITE_URL || "*", "Access-Control-Allow-Methods": "GET,OPTIONS",
           "Cache-Control": "no-store", "Content-Type": "application/json; charset=utf-8" };
}
function json(obj, headers) { return new Response(JSON.stringify(obj), { headers }); }
function sitePage(env, lang) {
  const base = (env.SITE_URL || "https://threespacetokyo.com").replace(/\/$/, "");
  return base + "/mendtokyo/" + (lang && lang !== "en" ? lang + "/" : "");
}
function api(env) {
  const host = env.SQUARE_ENV === "sandbox" ? "https://connect.squareupsandbox.com" : "https://connect.squareup.com";
  return async (method, path, body) => {
    const r = await fetch(host + "/v2" + path, {
      method, headers: { "Authorization": "Bearer " + env.SQUARE_ACCESS_TOKEN, "Square-Version": SQUARE_VERSION,
                         "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(`Square ${method} ${path} -> ${r.status}: ${JSON.stringify(data).slice(0, 400)}`);
    return data;
  };
}
const pad = (n) => String(n).padStart(2, "0");
const DASH = "–";

function itemName(date, time) {           // 2026-12-02, 14:00–16:00 -> "Mendtokyo 12/02/2026 14:00–16:00"
  const [y, m, d] = date.split("-");
  return `Mendtokyo ${m}/${d}/${y} ${time.replace("-", DASH)}`;
}
function parseName(name) {                // -> { date, time } or null (also understands Aya's names)
  const m = NAME_RE.exec(name || "");
  if (!m) return null;
  const date = `${m[3]}-${m[1]}-${m[2]}`;
  const time = m[4] ? `14:00${DASH}16:00` : m[5] ? `${m[5]}${DASH}${m[6]}` : `10:00${DASH}12:00`;
  return { date, time };
}
function prettyDate(date) {
  const d = new Date(date + "T00:00:00+09:00");
  return d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", year: "numeric", timeZone: "Asia/Tokyo" });
}

// ---------- catalog ----------
async function listItems(sq, env) {
  const out = []; let cursor;
  do {
    const r = await sq("GET", "/catalog/list?types=ITEM" + (cursor ? "&cursor=" + encodeURIComponent(cursor) : ""));
    for (const o of r.objects || []) {
      const name = o.item_data && o.item_data.name;
      const v = o.item_data && o.item_data.variations && o.item_data.variations[0];
      if (name && name.startsWith("Mendtokyo ") && v) out.push({ name, itemId: o.id, variationId: v.id });
    }
    cursor = r.cursor;
  } while (cursor);
  return out;
}
async function counts(sq, env, variationIds) {
  const out = {};
  for (let i = 0; i < variationIds.length; i += 100) {
    const r = await sq("POST", "/inventory/counts/batch-retrieve",
      { catalog_object_ids: variationIds.slice(i, i + 100), location_ids: [env.SQUARE_LOCATION_ID], states: ["IN_STOCK"] });
    for (const c of r.counts || []) out[c.catalog_object_id] = parseInt(c.quantity || "0", 10);
  }
  return out;
}
async function createItem(sq, env, date, time) {
  const name = itemName(date, time);
  const r = await sq("POST", "/catalog/object", {
    idempotency_key: crypto.randomUUID(),
    object: { type: "ITEM", id: "#item", present_at_all_locations: true,
      item_data: { name, description: `Kintsugi workshop at ${VENUE}. One seat per ticket.`,
        variations: [{ type: "ITEM_VARIATION", id: "#var", present_at_all_locations: true,
          item_variation_data: { item_id: "#item", name: "Seat", pricing_type: "FIXED_PRICING",
            price_money: { amount: parseInt(env.PRICE_JPY || "20000", 10), currency: "JPY" },
            track_inventory: true, inventory_alert_type: "LOW_QUANTITY", inventory_alert_threshold: 1 } }] } } });
  const variationId = r.id_mappings.find((m) => m.client_object_id === "#var").object_id;
  await sq("POST", "/inventory/changes/batch-create", {
    idempotency_key: crypto.randomUUID(),
    changes: [{ type: "PHYSICAL_COUNT", physical_count: { catalog_object_id: variationId, state: "IN_STOCK",
      location_id: env.SQUARE_LOCATION_ID, quantity: String(env.DEFAULT_SEATS || 4), occurred_at: new Date().toISOString() } }] });
  return { name, variationId };
}

// ---------- endpoints ----------
async function seats(env) {
  const sq = api(env);
  const items = await listItems(sq, env);
  const c = await counts(sq, env, items.map((i) => i.variationId));
  const out = {};
  for (const i of items) {
    const p = parseName(i.name); if (!p) continue;
    const key = `${p.date} ${p.time}`;
    const n = c[i.variationId]; if (n === undefined) continue;
    out[key] = Math.max(out[key] || 0, n);   // if duplicates exist, show the most optimistic
  }
  return out;
}

async function book(url, env) {
  const date = url.searchParams.get("date") || "";
  const time = (url.searchParams.get("time") || "").replace("-", DASH).replace(/\s/g, "");
  const lang = url.searchParams.get("lang") || "en";
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !/^\d{2}:\d{2}–\d{2}:\d{2}$/.test(time)) {
    return new Response("bad request", { status: 400 });
  }
  const sq = api(env);
  // find the item (new naming first, then Aya's naming)
  const items = await listItems(sq, env);
  let item = items.find((i) => { const p = parseName(i.name); return p && p.date === date && p.time === time; });
  if (!item) item = await createItem(sq, env, date, time);
  const left = (await counts(sq, env, [item.variationId]))[item.variationId];
  if (left !== undefined && left <= 0) return Response.redirect(sitePage(env, lang) + "?soldout=" + date + "#sessions", 302);

  const desc = `Mendtokyo kintsugi workshop · ${prettyDate(date)}, ${time} · ${VENUE}. ` +
               `One seat per ticket. Details, what to bring and cancellation terms: ${sitePage(env, "en")}`;
  const r = await sq("POST", "/online-checkout/payment-links", {
    idempotency_key: crypto.randomUUID(),
    description: desc,
    order: { location_id: env.SQUARE_LOCATION_ID,
             line_items: [{ catalog_object_id: item.variationId, quantity: "1", note: `${prettyDate(date)}, ${time} · Asakusabashi` }] },
    checkout_options: { allow_tipping: false, ask_for_shipping_address: false, enable_coupon: false, enable_loyalty: false,
                        redirect_url: sitePage(env, "en") + "thanks/?lang=" + lang + "&d=" + date + "&t=" + encodeURIComponent(time),
                        merchant_support_email: "threespacetokyo@gmail.com" },
  });
  return Response.redirect(r.payment_link.url, 302);
}
