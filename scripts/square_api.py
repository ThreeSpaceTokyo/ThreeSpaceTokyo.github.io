"""Minimal Square API client (stdlib only) for the Mendtokyo workshop.

Used by sync_sessions.py (read remaining stock -> sold-out status) and
create_square_links.py (create one catalog item + payment link per session).
Credentials come from the environment: SQUARE_ACCESS_TOKEN, SQUARE_LOCATION_ID.
"""
import datetime, json, os, re, urllib.error, urllib.request, uuid

API = "https://connect.squareup.com/v2"
VERSION = "2025-01-23"


class Square:
    def __init__(self, token=None, location_id=None):
        self.token = token or os.environ.get("SQUARE_ACCESS_TOKEN", "")
        self.location_id = location_id or os.environ.get("SQUARE_LOCATION_ID", "")
        if not self.token or not self.location_id:
            raise RuntimeError("SQUARE_ACCESS_TOKEN and SQUARE_LOCATION_ID must be set")

    def call(self, method, path, body=None):
        req = urllib.request.Request(API + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None)
        req.add_header("Authorization", "Bearer " + self.token)
        req.add_header("Square-Version", VERSION)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            raise RuntimeError(f"Square {method} {path} -> {e.code}: {detail[:500]}") from None

    # ---- reading -------------------------------------------------------
    def payment_links(self):
        """All payment links in the account, keyed by their short URL."""
        out, cursor = {}, None
        while True:
            q = f"?limit=100" + (f"&cursor={cursor}" if cursor else "")
            r = self.call("GET", "/online-checkout/payment-links" + q)
            for pl in r.get("payment_links", []):
                for key in ("url", "long_url"):
                    if pl.get(key):
                        out[pl[key].rstrip("/")] = pl
            cursor = r.get("cursor")
            if not cursor:
                return out

    def order(self, order_id):
        return self.call("GET", f"/orders/{order_id}").get("order", {})

    def inventory_counts(self, variation_ids):
        """{variation_id: remaining IN_STOCK quantity (int)}"""
        out = {}
        ids = list(variation_ids)
        for i in range(0, len(ids), 100):
            body = {"catalog_object_ids": ids[i:i + 100], "location_ids": [self.location_id],
                    "states": ["IN_STOCK"]}
            r = self.call("POST", "/inventory/counts/batch-retrieve", body)
            for c in r.get("counts", []):
                if c.get("state") == "IN_STOCK":
                    out[c["catalog_object_id"]] = int(float(c.get("quantity", "0")))
        return out

    def seats_left_by_link(self, links):
        """For each square.link URL, remaining stock of the item behind it.
        Returns {url: int or None} - None when the link is not a tracked catalog item."""
        links = [l.rstrip("/") for l in links if "square.link" in l]
        if not links:
            return {}
        all_links = self.payment_links()
        link_to_var = {}
        for url in links:
            pl = all_links.get(url)
            if not pl or not pl.get("order_id"):
                link_to_var[url] = None; continue
            items = self.order(pl["order_id"]).get("line_items", [])
            var_ids = [li["catalog_object_id"] for li in items if li.get("catalog_object_id")]
            link_to_var[url] = var_ids[0] if var_ids else None
        counts = self.inventory_counts({v for v in link_to_var.values() if v})
        return {url: (counts.get(v) if v else None) for url, v in link_to_var.items()}

    # ---- creating ------------------------------------------------------
    def create_session_item(self, name, price_jpy, seats):
        """Create a catalog item with one tracked variation and set its stock. Returns variation id."""
        body = {"idempotency_key": str(uuid.uuid4()),
                "object": {"type": "ITEM", "id": "#item", "present_at_all_locations": True,
                           "item_data": {"name": name,
                                         "variations": [{"type": "ITEM_VARIATION", "id": "#var",
                                                         "present_at_all_locations": True,
                                                         "item_variation_data": {
                                                             "item_id": "#item", "name": "Seat",
                                                             "pricing_type": "FIXED_PRICING",
                                                             "price_money": {"amount": int(price_jpy), "currency": "JPY"},
                                                             "track_inventory": True,
                                                             "inventory_alert_type": "LOW_QUANTITY",
                                                             "inventory_alert_threshold": 1}}]}}}
        r = self.call("POST", "/catalog/object", body)
        var_id = next(m["object_id"] for m in r["id_mappings"] if m["client_object_id"] == "#var")
        now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.call("POST", "/inventory/changes/batch-create", {
            "idempotency_key": str(uuid.uuid4()),
            "changes": [{"type": "PHYSICAL_COUNT", "physical_count": {
                "catalog_object_id": var_id, "state": "IN_STOCK",
                "location_id": self.location_id, "quantity": str(int(seats)), "occurred_at": now}}]})
        return var_id

    def create_payment_link(self, variation_id, description=None):
        body = {"idempotency_key": str(uuid.uuid4()),
                "order": {"location_id": self.location_id,
                          "line_items": [{"catalog_object_id": variation_id, "quantity": "1"}]},
                "checkout_options": {"allow_tipping": False, "ask_for_shipping_address": False,
                                     "enable_coupon": False, "enable_loyalty": False}}
        if description:
            body["description"] = description
        r = self.call("POST", "/online-checkout/payment-links", body)
        return r["payment_link"]["url"]


def session_item_name(date_iso, time_str, location="asakusabashi"):
    """Match Aya's naming: 'Mendtokyo 12/02/2026' (morning) / 'Mendtokyo 12/02/2026 afternoon',
    with the venue appended when it is not Asakusabashi."""
    y, m, d = date_iso.split("-")
    start = int(re.match(r"\s*(\d{1,2})", time_str).group(1))
    name = f"Mendtokyo {m}/{d}/{y}" + (" afternoon" if start >= 12 else "")
    if location and location != "asakusabashi":
        name += " " + location.capitalize()
    return name
