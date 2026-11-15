#!/usr/bin/env python3
"""Set the remaining stock (seats) of the Square item behind a payment link.

Usage: set_square_stock.py <square.link URL> <seats_left> [--apply]
Dry run by default: shows the item, its current stock and what would change.
Fails clearly if the link is not backed by an inventory-tracked catalog item
(e.g. an ad-hoc "quick" link) - such links cannot cap bookings; recreate them
with create_square_links.py instead.
"""
import datetime, os, sys, uuid
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from square_api import Square

def main():
    args = [a for a in sys.argv[1:] if a != "--apply"]
    apply = "--apply" in sys.argv
    url, seats = args[0].rstrip("/"), int(args[1])
    sq = Square()
    pl = sq.payment_links().get(url)
    if not pl or not pl.get("order_id"):
        sys.exit(f"ERROR: {url} is not a payment link of this Square account")
    order = sq.order(pl["order_id"])
    items = [li for li in order.get("line_items", []) if li.get("catalog_object_id")]
    if not items:
        sys.exit(f"ERROR: {url} is an ad-hoc link with no catalog item behind it - stock cannot be tracked. "
                 "Create a proper item + link with create_square_links.py instead.")
    var_id = items[0]["catalog_object_id"]
    name = items[0].get("name", "?")
    obj = sq.call("GET", f"/catalog/object/{var_id}").get("object", {})
    tracked = obj.get("item_variation_data", {}).get("track_inventory", False)
    current = sq.inventory_counts([var_id]).get(var_id)
    print(f"{url}: item '{name}' (variation {var_id}), inventory tracking {'ON' if tracked else 'OFF'}, "
          f"current stock {current if current is not None else 'unknown'}")
    if current == seats and tracked:
        print("Already at the requested stock - nothing to do."); return
    print(f"{'APPLY' if apply else 'DRY RUN'}: set stock to {seats}")
    if not apply:
        return
    if not tracked:
        obj["item_variation_data"]["track_inventory"] = True
        sq.call("POST", "/catalog/object", {"idempotency_key": str(uuid.uuid4()), "object": obj})
        print("Enabled inventory tracking on the variation.")
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    sq.call("POST", "/inventory/changes/batch-create", {
        "idempotency_key": str(uuid.uuid4()),
        "changes": [{"type": "PHYSICAL_COUNT", "physical_count": {
            "catalog_object_id": var_id, "state": "IN_STOCK",
            "location_id": sq.location_id, "quantity": str(seats), "occurred_at": now}}]})
    print(f"Done: stock is now {seats}.")

if __name__ == "__main__":
    main()
