#!/usr/bin/env python3
"""Regenerate _data/mending_sessions.yml from the Mendtokyo schedule Google Sheet.

Usage: sync_sessions.py <csv_url> [output_path]
Reads the sheet as CSV (columns: date, time, seats, status, square_link, channel, note),
validates rows, drops duplicates, sorts by date/time and writes the YAML the page reads.
Exits 0 whether or not anything changed; the workflow decides whether to commit.
"""
import csv, datetime, io, re, sys, urllib.request

HEADER = """# Upcoming sessions for the Mendtokyo kintsugi workshop (/mendtokyo/).
#
# GENERATED FILE - do not edit by hand. The source is Aya's Google Sheet
# "Mending Workshop - sessions & Square links"; a GitHub Action
# (.github/workflows/sync-sessions.yml) rewrites this file from it every hour.
#
#   date:    YYYY-MM-DD        time: shown as-is
#   status:  open | soldout | cancelled   (soldout/cancelled replace the button with a label)
#   link:    Square checkout link; empty -> "Book by email" button
#   channel: direct | airbnb   (airbnb rows show "Book on Airbnb")
#   note:    optional short note shown under the date
#
# Past dates are hidden by the page automatically.

"""
VALID_STATUS = {"open", "few", "soldout", "cancelled"}
VALID_CHANNEL = {"direct", "airbnb"}

def yq(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'

def main():
    url = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else "_data/mending_sessions.yml"
    raw = urllib.request.urlopen(url, timeout=60).read().decode("utf-8-sig")
    rows, seen, problems = [], set(), []
    for n, r in enumerate(csv.DictReader(io.StringIO(raw)), start=2):
        date = (r.get("date") or "").strip()
        if not date:
            continue  # blank row or the how-to block
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            problems.append(f"row {n}: date '{date}' is not YYYY-MM-DD, skipped"); continue
        try:
            datetime.date.fromisoformat(date)
        except ValueError:
            problems.append(f"row {n}: date '{date}' is not a real date, skipped"); continue
        time = (r.get("time") or "").strip().replace("-", "–").replace(" ", "")
        if not time:
            problems.append(f"row {n}: no time, skipped"); continue
        status = re.sub(r"[\s_-]", "", (r.get("status") or "open").strip().lower()) or "open"
        if status not in VALID_STATUS:
            problems.append(f"row {n}: status '{status}' unknown, treated as open"); status = "open"
        channel = (r.get("channel") or "direct").strip().lower() or "direct"
        if channel not in VALID_CHANNEL:
            problems.append(f"row {n}: channel '{channel}' unknown, treated as direct"); channel = "direct"
        link = (r.get("square_link") or "").strip()
        if link and not link.startswith("https://"):
            problems.append(f"row {n}: link '{link}' is not https, dropped"); link = ""
        note = (r.get("note") or "").strip()
        key = (date, time)
        if key in seen:
            problems.append(f"row {n}: duplicate of {date} {time}, skipped"); continue
        seen.add(key)
        rows.append((date, time, status, link, channel, note))
    rows.sort()
    lines = []
    for date, time, status, link, channel, note in rows:
        item = f"- {{ date: {date}, time: {yq(time)}, status: {status}, link: {yq(link)}, channel: {channel}"
        if note:
            item += f", note: {yq(note)}"
        lines.append(item + " }")
    with open(out, "w", encoding="utf-8") as f:
        f.write(HEADER + "\n".join(lines) + "\n")
    print(f"{len(rows)} sessions written to {out}")
    for p in problems:
        print("WARNING:", p)
    if not rows:
        print("ERROR: no valid rows found - refusing to publish an empty schedule", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
