#!/usr/bin/env python3
"""Create Square catalog items + payment links for sessions that have no link yet,
and write each new link back into the schedule Google Sheet.

Usage: create_square_links.py <csv_url> [--apply] [--price 20000]
Default is a DRY RUN that only prints what would be created.

Seats per new item: 4 at Asakusabashi, 2 at Shimokitazawa (Lynh teaches there without
an assistant). Override per location with env SEATS_ASAKUSABASHI / SEATS_SHIMOKITAZAWA.

Write-back to the sheet needs env GOOGLE_SERVICE_ACCOUNT_JSON (a service-account key
whose email has Editor access to the sheet) and GSHEET_ID (defaults to the Mendtokyo
sheet). Without it, links are kept in _data/mending_square_links.json and printed.
"""
import csv, datetime, io, json, os, re, sys, urllib.request
from zoneinfo import ZoneInfo
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from square_api import Square, session_item_name
from sync_sessions import location_key

DEFAULT_SEATS = {"asakusabashi": int(os.environ.get("SEATS_ASAKUSABASHI", 4)),
                 "shimokitazawa": int(os.environ.get("SEATS_SHIMOKITAZAWA", 2))}
SHEET_ID = os.environ.get("GSHEET_ID", "1GL8YShTbRhtw0zPxlOqpVSOy6kohseQddiPT-Yw2cx0")
SHEET_TAB = os.environ.get("GSHEET_TAB", "Untitled")


def sheet_writer():
    """Return a function write(row_number, link) or None if no Google credentials."""
    key = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not key:
        return None
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError:
        print("WARNING: google-api-python-client not installed; cannot write to the sheet")
        return None
    creds = service_account.Credentials.from_service_account_info(
        json.loads(key), scopes=["https://www.googleapis.com/auth/spreadsheets"])
    svc = build("sheets", "v4", credentials=creds, cache_discovery=False).spreadsheets().values()
    header = svc.get(spreadsheetId=SHEET_ID, range=f"{SHEET_TAB}!1:1").execute().get("values", [[]])[0]
    header = [h.strip().lower() for h in header]
    col = header.index("square_link") if "square_link" in header else None
    if col is None:
        print("WARNING: no 'square_link' column in the sheet header; cannot write back")
        return None
    col_letter = chr(ord("A") + col)
    i_date, i_time = header.index("date"), header.index("time")
    i_loc = header.index("location") if "location" in header else None

    def write(_csv_row, link, d, t, loc):
        # find the sheet row by content (CSV row numbers can drift if there are blank rows)
        grid = svc.get(spreadsheetId=SHEET_ID, range=f"{SHEET_TAB}!A2:Z200").execute().get("values", [])
        for i, row in enumerate(grid, start=2):
            row = row + [""] * (len(header) - len(row))
            if row[i_date].strip() != d or row[i_time].strip().replace("-", "\u2013").replace(" ", "") != t:
                continue
            if i_loc is not None and (location_key(row[i_loc]) or "asakusabashi") != loc:
                continue
            if row[col].strip():
                return i  # already filled
            svc.update(spreadsheetId=SHEET_ID, range=f"{SHEET_TAB}!{col_letter}{i}",
                       valueInputOption="RAW", body={"values": [[link]]}).execute()
            return i
        raise RuntimeError(f"row for {d} {t} {loc} not found in the sheet")
    return write


def main():
    args = sys.argv[1:]
    apply = "--apply" in args
    price = int(args[args.index("--price") + 1]) if "--price" in args else 20000
    url = args[0]
    store = "_data/mending_square_links.json"
    links = json.load(open(store, encoding="utf-8")) if os.path.exists(store) else {}
    today = datetime.datetime.now(ZoneInfo("Asia/Tokyo")).date()
    raw = urllib.request.urlopen(url, timeout=60).read().decode("utf-8-sig")
    todo = []  # (sheet_row_number, date, time, loc)
    for n, r in enumerate(csv.DictReader(io.StringIO(raw)), start=2):
        r = {(k or "").strip().lower(): (v or "") for k, v in r.items()}
        d = r.get("date", "").strip(); t = r.get("time", "").strip().replace("-", "–").replace(" ", "")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) or not t:
            continue
        try:
            if datetime.date.fromisoformat(d) < today:
                continue
        except ValueError:
            continue
        loc = location_key(r.get("location")) or "asakusabashi"
        if r.get("square_link", "").strip():
            continue
        if links.get(f"{d} {t} {loc}"):
            # created earlier but not yet in the sheet: try to write it again
            todo.append((n, d, t, loc, links[f"{d} {t} {loc}"])); continue
        if r.get("status", "").strip().lower() in ("cancelled", "canceled"):
            continue
        todo.append((n, d, t, loc, None))
    if not todo:
        print("Nothing to create: every upcoming session already has a link."); return
    print(("APPLY" if apply else "DRY RUN") + f": {len(todo)} session(s) without a link in the sheet")
    sq = Square() if apply else None
    write = sheet_writer() if apply else None
    if apply and write is None:
        print("NOTE: no Google credentials - links will be saved to the repo and printed; paste them into the sheet.")
    for n, d, t, loc, existing in todo:
        seats = DEFAULT_SEATS.get(loc, 4)
        name = session_item_name(d, t, loc)
        if existing:
            print(f"  row {n}: {d} {t} {loc} -> link already created earlier: {existing}")
            link = existing
        else:
            print(f"  row {n}: {d} {t} {loc} -> item \"{name}\", ¥{price:,}, stock {seats}")
            if not apply:
                continue
            var_id = sq.create_session_item(name, price, seats)
            link = sq.create_payment_link(var_id, description=f"Mendtokyo kintsugi workshop, {d} {t} ({loc})")
            links[f"{d} {t} {loc}"] = link
            json.dump(links, open(store, "w", encoding="utf-8"), indent=1, ensure_ascii=False, sort_keys=True)
            print(f"     created {link}")
        if apply and write:
            try:
                i = write(n, link, d, t, loc); print(f"     written to sheet row {i}")
            except Exception as e:
                print(f"     WARNING: could not write to sheet row {n}: {e}")

if __name__ == "__main__":
    main()
