#!/usr/bin/env python3
"""Regenerate _data/mending_sessions.yml from the Mendtokyo schedule Google Sheet.

Usage: sync_sessions.py <csv_url> [output_path]
Sheet columns: date, time, location, square_link, channel, note
(older columns seats/status are tolerated and ignored, except status=cancelled).
Seats left come from Square (stock of the item behind each link) when
SQUARE_ACCESS_TOKEN / SQUARE_LOCATION_ID are set. Past dates (Tokyo) are dropped.
"""
import csv, datetime, io, json, os, re, sys, urllib.request
from zoneinfo import ZoneInfo

TOKYO = ZoneInfo("Asia/Tokyo")
HERE = os.path.dirname(os.path.abspath(__file__))

HEADER = """# Upcoming sessions for the Mendtokyo kintsugi workshop (/mendtokyo/).
#
# GENERATED FILE - do not edit by hand. Source: Aya's Google Sheet; a GitHub Action
# (.github/workflows/sync-sessions.yml) rewrites this file every hour.
#
#   date:     YYYY-MM-DD          time: shown as-is
#   location: asakusabashi | shimokitazawa   (keys defined in _data/mending_locations.yml)
#   link:     Square payment link; empty -> "Book by email" button
#   channel:  direct | airbnb     (airbnb rows show "Book on Airbnb")
#   seats:    seats left according to Square (omitted when unknown)
#   status:   open | soldout | cancelled
#   note:     optional short note shown under the date
#
# Only today's and future dates (Tokyo time) are written here; past rows stay in the sheet.

"""
VALID_CHANNEL = {"direct", "airbnb"}

def yq(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'

def location_key(text):
    t = (text or "").strip().lower()
    if not t or "asakusa" in t or "three space" in t or "tst" in t:
        return "asakusabashi"
    if "shimokita" in t or "daita" in t or "bookshop" in t or "setagaya" in t or "下北" in t:
        return "shimokitazawa"
    return None

def main():
    url = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else "_data/mending_sessions.yml"
    raw = urllib.request.urlopen(url, timeout=60).read().decode("utf-8-sig")
    today = datetime.datetime.now(TOKYO).date()
    rows, seen, problems, past = [], set(), [], 0
    for n, r in enumerate(csv.DictReader(io.StringIO(raw)), start=2):
        r = {(k or "").strip().lower(): (v or "") for k, v in r.items()}
        date = r.get("date", "").strip()
        if not date:
            continue
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            problems.append(f"row {n}: date '{date}' is not YYYY-MM-DD, skipped"); continue
        try:
            day = datetime.date.fromisoformat(date)
        except ValueError:
            problems.append(f"row {n}: date '{date}' is not a real date, skipped"); continue
        if day < today:
            past += 1; continue
        time = r.get("time", "").strip().replace("-", "–").replace(" ", "")
        if not time:
            problems.append(f"row {n}: no time, skipped"); continue
        loc = location_key(r.get("location"))
        if loc is None:
            problems.append(f"row {n}: location '{r.get('location')}' not recognised, using Asakusabashi"); loc = "asakusabashi"
        channel = r.get("channel", "direct").strip().lower() or "direct"
        if channel not in VALID_CHANNEL:
            problems.append(f"row {n}: channel '{channel}' unknown, treated as direct"); channel = "direct"
        link = (r.get("square_link") or r.get("link") or "").strip()
        if link and not link.startswith("https://"):
            problems.append(f"row {n}: link '{link}' is not https, dropped"); link = ""
        status = re.sub(r"[\s_-]", "", r.get("status", "").lower())
        status = "cancelled" if status in ("cancelled", "canceled") else "open"
        note = r.get("note", "").strip()
        key = (date, time, loc)
        if key in seen:
            problems.append(f"row {n}: duplicate of {date} {time} {loc}, skipped"); continue
        seen.add(key)
        rows.append({"date": date, "time": time, "location": loc, "link": link,
                     "channel": channel, "status": status, "note": note, "seats": None})

    # Seats left from Square
    if os.environ.get("SQUARE_ACCESS_TOKEN") and os.environ.get("SQUARE_LOCATION_ID"):
        try:
            sys.path.insert(0, HERE)
            from square_api import Square
            sq = Square()
            left = sq.seats_left_by_link([s["link"] for s in rows if s["link"]])
            by_name = sq.seats_by_session()   # fallback: items named "Mendtokyo MM/DD/YYYY ..."
            for s in rows:
                n_left = left.get(s["link"].rstrip("/")) if s["link"] else None
                if n_left is None:
                    n_left = by_name.get((s["date"], s["time"]))
                if n_left is None or s["status"] == "cancelled":
                    continue
                s["seats"] = n_left
                s["status"] = "soldout" if n_left <= 0 else "open"
                print(f"square: {s['date']} {s['time']} {s['location']}: {n_left} seat(s) left -> {s['status']}")
        except Exception as e:
            problems.append(f"Square check skipped: {e}")

    rows.sort(key=lambda s: (s["date"], s["time"], s["location"]))
    lines = []
    for s in rows:
        item = (f"- {{ date: {s['date']}, time: {yq(s['time'])}, location: {s['location']}, "
                f"link: {yq(s['link'])}, channel: {s['channel']}, status: {s['status']}")
        if s["seats"] is not None:
            item += f", seats: {s['seats']}"
        if s["note"]:
            item += f", note: {yq(s['note'])}"
        lines.append(item + " }")
    with open(out, "w", encoding="utf-8") as f:
        f.write(HEADER + "\n".join(lines) + "\n")
    print(f"{len(rows)} upcoming sessions written to {out} ({past} past dates ignored; today in Tokyo is {today})")
    for p in problems:
        print("WARNING:", p)
    if not rows and past == 0:
        print("ERROR: no valid rows found - refusing to publish an empty schedule", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
