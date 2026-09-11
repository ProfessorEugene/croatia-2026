#!/usr/bin/env python3
"""Generate daily .md and .geojson files for the Croatia 2026 trip."""

import csv
import json
import os
from datetime import date, timedelta, datetime

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "byday")
MAPS_DIR = os.path.join(os.path.dirname(__file__), "maps")



def load_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_group_colors(travelers):
    seen = {}
    for row in travelers:
        group = row["groupName"]
        if group not in seen:
            seen[group] = row["color"]
    return seen


def parse_datetime(s):
    if not s or s.strip().upper() in ("N/A", ""):
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def maps_link(place):
    lat = place["lat"].strip()
    lon = place["lon"].strip()
    return f"https://maps.google.com/maps?q={lat},{lon}"


def generate_markdown(d, active_hotels, arrivals, departures, day_transits, places, group_colors, overview="", geojson=None):
    day_name = d.strftime("%A")
    filename_base = d.strftime("%m-%d-") + day_name
    lines = []

    lines.append(f"## {day_name} {d.isoformat()}")
    lines.append("")
    lines.append("### Daily Overview")
    lines.append("")
    lines.append(overview if overview else "_TODO_")
    lines.append("")

    lines.append("### Schedule")
    lines.append("")
    events = []
    for dt, t in arrivals:
        via = f" via flight {t['via']}" if t.get("via", "").strip() else ""
        events.append((dt, f"* {dt.strftime('%H:%M')} - {t['groupName']} arrives{via}"))
    for dt, t in departures:
        via = f" via flight {t['via']}" if t.get("via", "").strip() else ""
        events.append((dt, f"* {dt.strftime('%H:%M')} - {t['groupName']} departs{via}"))
    for t in day_transits:
        dt = datetime.strptime(f"{t['date']} {t['time']}", "%Y-%m-%d %H:%M")
        events.append((dt, f"* {t['time']} - {t['label']}"))
    events.sort(key=lambda x: x[0])
    for _, line in events:
        lines.append(line)
    if not events:
        lines.append("_No scheduled events_")
    lines.append("")

    lines.append("### Map")
    lines.append("")
    lines.append(f"[Download GeoJSON](../maps/{filename_base}.geojson)")
    lines.append("")
    lines.append("```geojson")
    lines.append(json.dumps(geojson, indent=2, ensure_ascii=False) if geojson else '{"type":"FeatureCollection","features":[]}')
    lines.append("```")
    lines.append("")

    lines.append("### Accommodations")
    lines.append("")
    for h in sorted(active_hotels, key=lambda x: x["groupName"]):
        place = places[h["placeId"]]
        name = place["name"]
        address = place["address"].strip('"')
        link = maps_link(place)
        lines.append(f"* {h['groupName']} - [{name} at {address}]({link})")
    lines.append("")

    lines.append("### Transportation")
    lines.append("")
    lines.append("* Eugene car (5 pax)")
    lines.append("* Taras car (4 pax)")
    lines.append("* Alex car (2 pax)")
    lines.append("")

    return "\n".join(lines)


def generate_geojson(d, active_hotels, places, group_colors):
    features = []
    for h in active_hotels:
        place = places[h["placeId"]]
        lat = float(place["lat"])
        lon = float(place["lon"])
        group = h["groupName"]
        checkin = h["checkinTime"]
        last_night = (date.fromisoformat(h["checkoutTime"]) - timedelta(days=1)).isoformat()
        color = group_colors.get(group, "#888888")
        features.append({
            "type": "Feature",
            "geometry": {"coordinates": [lon, lat], "type": "Point"},
            "properties": {
                "title": f"{group} Hotel",
                "type": "Hotel",
                "date-in": checkin,
                "date-out": last_night,
                "guest": group,
                "address": place["address"].strip('"'),
                "marker-color": color,
                "marker-size": "medium",
                "marker-symbol": "home",
            },
        })
    return {"type": "FeatureCollection", "features": features}


def main():
    travelers = load_csv(f"{DATA_DIR}/travelers.csv")
    group_colors = load_group_colors(travelers)
    places = {row["id"]: row for row in load_csv(f"{DATA_DIR}/places.csv")}
    hotels = load_csv(f"{DATA_DIR}/hotels.csv")
    trips = load_csv(f"{DATA_DIR}/trips.csv")
    transits = load_csv(f"{DATA_DIR}/transits.csv")
    activities = {row["date"]: row["overview"] for row in load_csv(f"{DATA_DIR}/activities.csv")}

    # Collect all dates that need files
    all_dates = set()
    for h in hotels:
        checkin = date.fromisoformat(h["checkinTime"])
        checkout = date.fromisoformat(h["checkoutTime"])
        d = checkin
        while d < checkout:
            all_dates.add(d)
            d += timedelta(days=1)
    for t in trips:
        for col in ("departureTime", "arrivalTime"):
            dt = parse_datetime(t.get(col, ""))
            if dt:
                all_dates.add(dt.date())
    for t in transits:
        all_dates.add(date.fromisoformat(t["date"]))

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(MAPS_DIR, exist_ok=True)

    for d in sorted(all_dates):
        day_name = d.strftime("%A")
        filename_base = d.strftime("%m-%d-") + day_name

        active_hotels = [
            h for h in hotels
            if date.fromisoformat(h["checkinTime"]) <= d < date.fromisoformat(h["checkoutTime"])
        ]

        arrivals, departures = [], []
        for t in trips:
            arr = parse_datetime(t.get("arrivalTime", ""))
            dep = parse_datetime(t.get("departureTime", ""))
            if arr and arr.date() == d:
                arrivals.append((arr, t))
            if dep and dep.date() == d:
                departures.append((dep, t))

        day_transits = [
            t for t in transits
            if date.fromisoformat(t["date"]) == d
        ]

        overview = activities.get(d.isoformat(), "")
        geojson = generate_geojson(d, active_hotels, places, group_colors)
        md = generate_markdown(d, active_hotels, arrivals, departures, day_transits, places, group_colors, overview, geojson)

        with open(f"{OUTPUT_DIR}/{filename_base}.md", "w", encoding="utf-8") as f:
            f.write(md)
        with open(f"{MAPS_DIR}/{filename_base}.geojson", "w", encoding="utf-8") as f:
            json.dump(geojson, f, indent=2, ensure_ascii=False)

        print(f"Generated {filename_base} ({len(active_hotels)} hotels, "
              f"{len(arrivals)} arrivals, {len(departures)} departures)")


if __name__ == "__main__":
    main()
