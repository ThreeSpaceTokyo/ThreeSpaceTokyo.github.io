/**
 * Mendtokyo booking worker (Cloudflare Workers, free plan).
 *
 *   GET /book?date=2026-12-02&time=14:00–16:00[&lang=en]
 *       -> finds (or creates) the Square item for that session, checks stock,
 *          creates a fresh single-use Square payment link and redirects the buyer to it.
 *          Sold out -> redirects back to the website.
 *   GET /seats
 *       -> JSON { "2026-12-02 14:00–16:00": 3, ... } live seats left for every Mendtokyo item.
 *   GET /sessions
 *       -> JSON [ {date, time, link, channel, note}, ... ] upcoming sessions read live from the schedule sheet
 *          (SHEET_CSV_URL, defaults to Aya's sheet), past dates (Tokyo) removed, sorted.
 *
 * Secrets / variables (Worker settings -> Variables and Secrets):
 *   SQUARE_ACCESS_TOKEN  (secret)   SQUARE_LOCATION_ID   SITE_URL (https://threespacetokyo.com)
 *   optional: PRICE_JPY (20000)  DEFAULT_SEATS (4)  SQUARE_ENV ("production" | "sandbox")
 *             TEMPLATE_ITEM ("Mendtokyo 12/30/2026 afternoon") - an existing Event item made by Aya in the
 *             Square Dashboard; new sessions are created as copies of it (same type, category, photo,
 *             description, taxes) with only the name and the event date/time changed.
 *   GET /inspect?name=<item name>   -> raw catalog object of an item (for checking the template).
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
      if (url.pathname === "/sessions") return json(await sessions(env), cors);
      if (url.pathname === "/inspect") return json(await inspect(env, url.searchParams.get("name") || ""), cors);
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
const ISO_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;

function sessionTimes(date, time) {        // -> [startISO, endISO] in Japan time
  const [t1, t2] = time.split(DASH);
  return [`${date}T${t1}:00+09:00`, `${date}T${t2}:00+09:00`];
}
function sameFormat(isoNew, like) {         // write isoNew in the same style as the template string
  const d = new Date(isoNew);
  if (/Z$/.test(like)) return d.toISOString().replace(/\.\d{3}Z$/, "Z");
  return isoNew;
}
async function findItemObject(sq, name) {
  const r = await sq("POST", "/catalog/search", { object_types: ["ITEM"], include_related_objects: true,
    query: { exact_query: { attribute_name: "name", attribute_value: name } } });
  const obj = (r.objects || [])[0];
  return obj ? { object: obj, related: r.related_objects || [] } : null;
}
async function inspect(env, name) {
  const sq = api(env);
  return (await findItemObject(sq, name)) || { error: "not found", name };
}

/** Create the item for a session by cloning the template item (an Event item made in the Dashboard). */
async function createItem(sq, env, date, time) {
  const name = itemName(date, time);
  const templateName = env.TEMPLATE_ITEM || "Mendtokyo 12/30/2026 afternoon";
  const found = await findItemObject(sq, templateName);
  let object;
  if (found) {
    const tpl = found.object;
    // which datetimes in the template are the event start / end?
    const stamps = [];
    (function walk(v) { if (typeof v === "string") { if (ISO_RE.test(v)) stamps.push(v); }
      else if (Array.isArray(v)) v.forEach(walk); else if (v && typeof v === "object") Object.values(v).forEach(walk); })(tpl.item_data);
    const sorted = [...new Set(stamps)].sort((x, y) => new Date(x) - new Date(y));
    const tplStart = sorted[0], tplEnd = sorted[sorted.length - 1];
    const [newStart, newEnd] = sessionTimes(date, time);
    const oldName = tpl.item_data.name;
    const rewrite = (v) => {
      if (typeof v === "string") {
        if (v === tplStart) return sameFormat(newStart, v);
        if (v === tplEnd) return sameFormat(newEnd, v);
        return v.split(oldName).join(name);
      }
      if (Array.isArray(v)) return v.map(rewrite);
      if (v && typeof v === "object") {
        const o = {};
        for (const [k, x] of Object.entries(v)) {
          if (["id", "version", "updated_at", "created_at", "catalog_v1_ids", "item_id", "uid", "sku",
               "description_plaintext", "is_deleted"].includes(k)) continue;
          o[k] = rewrite(x);
        }
        return o;
      }
      return v;
    };
    const itemData = rewrite(tpl.item_data);
    itemData.name = name;
    if (itemData.description_html) delete itemData.description;   // html is the source of truth
    itemData.variations = (tpl.item_data.variations || []).slice(0, 1).map((v, i) => {
      const vd = rewrite(v.item_variation_data || {});
      vd.item_id = "#item"; vd.track_inventory = true;
      if (!vd.price_money) vd.price_money = { amount: parseInt(env.PRICE_JPY || "20000", 10), currency: "JPY" };
      return { type: "ITEM_VARIATION", id: "#var" + i, present_at_all_locations: v.present_at_all_locations !== false, item_variation_data: vd };
    });
    object = { type: "ITEM", id: "#item", present_at_all_locations: tpl.present_at_all_locations !== false, item_data: itemData };
    if (tpl.present_at_location_ids) object.present_at_location_ids = tpl.present_at_location_ids;
  } else {
    // no template found: plain item
    object = { type: "ITEM", id: "#item", present_at_all_locations: true,
      item_data: { name, description: `Kintsugi workshop at ${VENUE}. One seat per ticket.`,
        variations: [{ type: "ITEM_VARIATION", id: "#var0", present_at_all_locations: true,
          item_variation_data: { item_id: "#item", name: "Seat", pricing_type: "FIXED_PRICING",
            price_money: { amount: parseInt(env.PRICE_JPY || "20000", 10), currency: "JPY" }, track_inventory: true } }] } };
  }
  const r = await sq("POST", "/catalog/object", { idempotency_key: crypto.randomUUID(), object });
  const variationId = r.id_mappings.find((m) => m.client_object_id === "#var0").object_id;
  await sq("POST", "/inventory/changes/batch-create", {
    idempotency_key: crypto.randomUUID(),
    changes: [{ type: "PHYSICAL_COUNT", physical_count: { catalog_object_id: variationId, state: "IN_STOCK",
      location_id: env.SQUARE_LOCATION_ID, quantity: String(env.DEFAULT_SEATS || 4), occurred_at: new Date().toISOString() } }] });
  return { name, variationId };
}

// ---------- schedule sheet ----------
const SHEET_CSV_DEFAULT = "https://docs.google.com/spreadsheets/d/1GL8YShTbRhtw0zPxlOqpVSOy6kohseQddiPT-Yw2cx0/gviz/tq?tqx=out:csv&gid=1775567458";
function parseCsv(text) {               // minimal RFC4180 parser -> array of rows
  const rows = [], row = []; let field = "", q = false, cur = [];
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) { if (c === '"') { if (text[i + 1] === '"') { field += '"'; i++; } else q = false; } else field += c; }
    else if (c === '"') q = true;
    else if (c === ",") { cur.push(field); field = ""; }
    else if (c === "\n" || c === "\r") { if (c === "\r" && text[i + 1] === "\n") i++; cur.push(field); rows.push(cur); cur = []; field = ""; }
    else field += c;
  }
  if (field.length || cur.length) { cur.push(field); rows.push(cur); }
  return rows;
}
function todayTokyo() {
  return new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Tokyo" }); // YYYY-MM-DD
}
async function sessions(env) {
  const r = await fetch(env.SHEET_CSV_URL || SHEET_CSV_DEFAULT, { cf: { cacheTtl: 60 } });
  if (!r.ok) throw new Error("sheet fetch " + r.status);
  const rows = parseCsv(await r.text());
  const header = (rows.shift() || []).map((h) => h.trim().toLowerCase());
  const col = (n) => header.indexOf(n);
  const iD = col("date"), iT = col("time"), iL = col("square_link"), iC = col("channel"), iN = col("note"), iS = col("status");
  const today = todayTokyo(), out = [], seen = new Set();
  for (const row of rows) {
    const date = (row[iD] || "").trim();
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || date < today) continue;
    const time = (row[iT] || "").trim().replace("-", DASH).replace(/\s/g, "");
    if (!time) continue;
    const status = iS >= 0 ? (row[iS] || "").trim().toLowerCase().replace(/[\s_-]/g, "") : "";
    if (status === "cancelled" || status === "canceled") continue;
    const key = date + " " + time; if (seen.has(key)) continue; seen.add(key);
    const link = iL >= 0 ? (row[iL] || "").trim() : "";
    out.push({ date, time, link: /^https:\/\//.test(link) ? link : "",
               channel: iC >= 0 && /airbnb/i.test(row[iC] || "") ? "airbnb" : "direct",
               note: iN >= 0 ? (row[iN] || "").trim() : "" });
  }
  out.sort((a, b) => (a.date + a.time).localeCompare(b.date + b.time));
  return out;
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
