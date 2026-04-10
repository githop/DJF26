#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = ["jinja2"]
# ///
"""
Generate driver sheets for a given date.

Usage:
    uv run db/generate_sheets.py "4/8 (Wednesday)"

    # Short forms also accepted:
    uv run db/generate_sheets.py 4/8
    uv run db/generate_sheets.py "4/8"

Output: driver-sheets/[m-d]-[firstname]-[lastname].md
"""

import argparse
import re
import sqlite3
import sys
import urllib.parse
from datetime import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "db" / "master_schedule.db"
TEMPLATE_PATH = REPO_ROOT / "TEMPLATE.md"
OUTPUT_DIR = REPO_ROOT / "driver-sheets"

# Location name used to detect airport pickup/dropoff tasks
AIRPORT_LOCATION = "Denver Airport"

# Airport door numbers by airline
# Format: "Airline Code": "Door ### (East/West)"
AIRPORT_DOORS = {
    "AA": "Door 613 (East)",  # American Airlines
    "WN": "Door 609 (East)",  # Southwest Airlines
    "UA": "Door 610 (West)",  # United Airlines
    "DL": "Door 608 (West)",  # Delta Airlines
}


# ---------------------------------------------------------------------------
# Date normalisation
# ---------------------------------------------------------------------------
DATE_LABELS = {
    "4/7": "4/7 (Tuesday)",
    "4/8": "4/8 (Wednesday)",
    "4/9": "4/9 (Thursday)",
    "4/10": "4/10 (Friday)",
    "4/11": "4/11 (Saturday)",
    "4/12": "4/12 (Sunday)",
}

# Ordered list of canonical date strings, used to look up the previous date.
DATE_ORDER = list(DATE_LABELS.values())


def normalise_date(raw: str) -> str:
    """Accept '4/8', '4/8 (Wednesday)', etc. and return the canonical DB form."""
    raw = raw.strip()
    if raw in DATE_LABELS.values():
        return raw
    # strip any parenthetical suffix and try the lookup
    base = re.sub(r"\s*\(.*\)$", "", raw).strip()
    if base in DATE_LABELS:
        return DATE_LABELS[base]
    raise ValueError(
        f"Unrecognised date '{raw}'. Expected one of: {', '.join(DATE_LABELS.keys())}"
    )


def previous_date(canonical: str) -> str | None:
    """Return the canonical date string for the day before, or None if first day."""
    idx = DATE_ORDER.index(canonical)
    return DATE_ORDER[idx - 1] if idx > 0 else None


def next_date(canonical: str) -> str | None:
    """Return the canonical date string for the day after, or None if last day."""
    idx = DATE_ORDER.index(canonical)
    return DATE_ORDER[idx + 1] if idx < len(DATE_ORDER) - 1 else None


def date_to_file_prefix(canonical: str) -> str:
    """'4/8 (Wednesday)' → '4.08'"""
    base = re.sub(r"\s*\(.*\)$", "", canonical).strip()  # '4/8'
    month, day = base.split("/")
    return f"{month}.{int(day):02d}"


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------
def parse_time(s: str) -> time:
    """Parse un-padded time string like '8:30' or '21:30'."""
    h, m = s.strip().split(":")
    return time(int(h), int(m))


def time_in_window(t: time, start: time, end: time) -> bool:
    """
    Return True if t falls within [start, end].
    Handles overnight windows where end < start (e.g. 21:30 – 01:30).
    """
    if start <= end:
        return start <= t <= end
    # overnight: t is in window if it's after start OR before/at end
    return t >= start or t <= end


def format_time_ampm(s: str) -> str:
    """Format time string like '8:30' or '15:00' to '8:30 AM' or '3:00 PM'."""
    if not s:
        return ""
    t = parse_time(s)
    # %I is 0-padded (e.g. 08:30 AM), strip leading zero
    return t.strftime("%I:%M %p").lstrip("0")


# ---------------------------------------------------------------------------
# DB queries
# ---------------------------------------------------------------------------
def get_driver_shifts(conn: sqlite3.Connection, date: str) -> list[dict]:
    cur = conn.execute(
        """
        SELECT Drivers, Vehicles, Start, "End", Location, "Location Destination"
        FROM schedule
        WHERE Date = ?
          AND Activity IN ('Staff: Driver', 'Driver Volunteer Shift')
        ORDER BY Vehicles, time(printf('%05s', Start))
        """,
        (date,),
    )
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_overnight_shifts_from_prev_date(
    conn: sqlite3.Connection, date: str
) -> list[dict]:
    """
    Return any shifts from the previous calendar date whose End < Start
    (i.e. they cross midnight into `date`).
    """
    prev = previous_date(date)
    if prev is None:
        return []
    shifts = get_driver_shifts(conn, prev)
    return [s for s in shifts if parse_time(s["End"]) < parse_time(s["Start"])]


def vehicle_matches(task_vehicles: str, shift_vehicle: str) -> bool:
    """
    Return True if shift_vehicle appears in the task's Vehicles field.
    Handles multi-vehicle tasks like 'Minivan 1, Minivan 2'.
    """
    if not task_vehicles:
        return False
    return shift_vehicle in [v.strip() for v in task_vehicles.split(",")]


def get_gt_tasks(
    conn: sqlite3.Connection,
    date: str,
    vehicle: str,
    shift_start: time,
    shift_end: time,
    next_date: str | None = None,
) -> list[dict]:
    """
    Fetch GT (People) and GT (Asset) rows for the vehicle on the date,
    then filter to the shift window in Python (handles overnight correctly).
    Supports multi-vehicle tasks (Vehicles = 'Minivan 1, Minivan 2').

    For overnight shifts (shift_end < shift_start), pass next_date to also
    pull post-midnight tasks stored under the following calendar date.
    """

    def fetch_rows(d: str) -> list[dict]:
        cur = conn.execute(
            """
            SELECT Start, "End", Activity, Details, Location,
                   "Location Destination", Pax, Notes, Vehicles
            FROM schedule
            WHERE Date = ?
              AND Activity IN ('GT (People)', 'GT (Asset)')
            ORDER BY time(printf('%05s', Start))
            """,
            (d,),
        )
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    rows = fetch_rows(date)

    is_overnight = shift_end < shift_start
    if is_overnight and next_date:
        midnight = time(0, 0)
        # Same-date portion: shift_start → midnight
        same_day = [
            r
            for r in rows
            if vehicle_matches(r["Vehicles"], vehicle)
            and time_in_window(parse_time(r["Start"]), shift_start, time(23, 59))
        ]
        # Next-date portion: midnight → shift_end
        next_rows = fetch_rows(next_date)
        next_day = [
            r
            for r in next_rows
            if vehicle_matches(r["Vehicles"], vehicle)
            and time_in_window(parse_time(r["Start"]), midnight, shift_end)
        ]
        return same_day + next_day

    return [
        r
        for r in rows
        if vehicle_matches(r["Vehicles"], vehicle)
        and time_in_window(parse_time(r["Start"]), shift_start, shift_end)
    ]


def get_flight_lookup(conn: sqlite3.Connection, date: str) -> list[dict]:
    """
    Return all Flight rows for the date as a list of dicts with keys:
      - names: list of lowercase passenger names parsed from Details
      - flight_num: e.g. 'UA 2187', or '' if not present
      - details: raw Details string
    """
    cur = conn.execute(
        """
        SELECT Details FROM schedule
        WHERE Date = ? AND Activity = 'Flight'
        """,
        (date,),
    )
    flight_num_re = re.compile(r"\(([A-Z]{2}\s*\d+)\)")
    results = []
    for (details,) in cur.fetchall():
        # Names appear before the first verb ('arrive', 'depart', etc.)
        name_part = re.split(
            r"\s+(?:arrives?|departs?)\b", details, flags=re.IGNORECASE
        )[0]
        names = [n.strip().lower() for n in name_part.split(",") if n.strip()]
        m = flight_num_re.search(details)
        results.append(
            {
                "names": names,
                "flight_num": m.group(1) if m else "",
                "details": details,
            }
        )
    return results


def get_door_for_flight(flight_num: str) -> str:
    """
    Extract airline code from flight number and return the pickup door.
    Returns empty string if no match found.
    """
    if not flight_num:
        return ""
    # Match 2-letter airline code at the start of flight number
    match = re.match(r"^([A-Z]{2})", flight_num)
    if match:
        airline_code = match.group(1)
        return AIRPORT_DOORS.get(airline_code, "")
    return ""


def find_flight_for_task(gt_details: str, flight_rows: list[dict]) -> str:
    """
    Given a GT Details string like 'Transfer Rodney Whitaker, Michael Dease to hotel',
    extract the first passenger name and look it up in the flight rows.
    Returns the flight number string, or '' if not found / not applicable.
    """
    # Strip leading verb phrase to get to the names
    name_part = re.sub(
        r"^(?:Transfer|Lobby Call:|Pickup:?)", "", gt_details, flags=re.IGNORECASE
    )
    # Take everything up to 'to hotel', 'to venue', 'travel to', etc.
    name_part = re.split(r"\s+(?:to\s+\w|travel)", name_part, flags=re.IGNORECASE)[0]
    # First name is the first comma-delimited or "and"-delimited token
    # Handle both "Name1, Name2" and "Name1 and Name2" formats
    first_name = (
        re.split(r",|\s+and\s+", name_part, flags=re.IGNORECASE)[0].strip().lower()
    )
    if not first_name:
        return ""
    for row in flight_rows:
        if any(first_name in n for n in row["names"]):
            return row["flight_num"]
    return ""
    for row in flight_rows:
        if any(first_name in n for n in row["names"]):
            return row["flight_num"]
    return ""


def get_address_lookup(conn: sqlite3.Connection) -> dict[str, dict[str, str]]:
    """
    Build a location-name → {address, phone} map from the locations table.
    """
    try:
        cur = conn.execute(
            """
            SELECT "Location Name", Address, Phone
            FROM locations
            """
        )
        return {
            row[0]: {"address": row[1] or "", "phone": row[2] or ""}
            for row in cur.fetchall()
        }
    except sqlite3.OperationalError:
        # Fallback if the locations table doesn't exist yet (e.g., migration hasn't run)
        return {}


def get_rental_lookup(conn: sqlite3.Connection) -> dict[str, dict[str, str]]:
    """
    Build a vehicle -> {license_plate, color, make_model} map from the rentals table.
    """
    try:
        cur = conn.execute(
            """
            SELECT Vehicle, "Car Type", "License Plate Number", Color
            FROM rentals
            """
        )
        return {
            row[0]: {
                "make_model": row[1] or "TBD",
                "license_plate": row[2] or "TBD",
                "color": row[3] or "TBD",
            }
            for row in cur.fetchall()
        }
    except sqlite3.OperationalError:
        return {}


def get_contact_lookups(
    conn: sqlite3.Connection,
) -> tuple[dict[str, dict], dict[str, dict]]:
    """
    Builds two lookups:
    1. full_name_lookup: lowercase full name -> {name, phone}
    2. first_name_lookup: lowercase unique first name -> {name, phone}
       (Only includes first names that map to exactly one person in the contacts list)
    """
    try:
        cur = conn.execute(
            """
            SELECT 
                COALESCE(NULLIF("Full Name", ''), "First Name" || ' ' || "Last Name"), 
                "First Name",
                Cell
            FROM contacts
            """
        )

        full_name_lookup = {}
        first_names = {}

        for row in cur.fetchall():
            full_name = (row[0] or "").strip()
            first_name = (row[1] or "").strip()
            phone = (row[2] or "").strip()

            if not phone:
                phone = "Unknown"

            info = {"name": full_name, "phone": phone}

            if full_name:
                full_name_lookup[full_name.lower()] = info

            if first_name:
                first_names.setdefault(first_name.lower(), []).append(info)

        first_name_lookup = {
            fname: infos[0] for fname, infos in first_names.items() if len(infos) == 1
        }

        return full_name_lookup, first_name_lookup
    except sqlite3.OperationalError:
        return {}, {}


# ---------------------------------------------------------------------------
# Passenger name extraction
# ---------------------------------------------------------------------------
def extract_passenger_names(details: str) -> list[str]:
    """
    Extract passenger names from a GT task Details string.

    Examples:
    - "Transfer Rodney Whitaker to hotel" -> ["Rodney Whitaker"]
    - "Lobby Call: Randy Napoleon travels to venue" -> ["Randy Napoleon"]
    - "Transfer Rodney Whitaker, Michael Dease to hotel" -> ["Rodney Whitaker", "Michael Dease"]
    - "Pickup: Orrin Evans, Robert Hurst and Marvin Smith" -> ["Orrin Evans", "Robert Hurst", "Marvin Smith"]
    """
    if not details:
        return []

    # Remove leading verb phrases
    name_part = re.sub(
        r"^(?:Transfer|Lobby Call:?|Pickup:?|Asset Drop Off)\s*",
        "",
        details,
        flags=re.IGNORECASE,
    )

    # Split on "to hotel", "to venue", "travels to", etc. to get just the names
    name_part = re.split(
        r"\s+(?:to\s+\w|travels|travel|from|departs|arrives)",
        name_part,
        flags=re.IGNORECASE,
    )[0]

    # Split on commas and "and" to get individual names
    names = re.split(r",|\s+and\s+", name_part, flags=re.IGNORECASE)

    # Clean up and filter empty names
    return [n.strip() for n in names if n.strip()]


def generate_pickup_message(
    driver_name: str,
    vehicle_color: str,
    make_model: str,
    license_plate: str,
    door: str,
) -> str:
    """
    Generate the airport pickup message template with driver and vehicle info.
    """
    return (
        f"Hi, it's {driver_name}. I'm a Denver Jazz Fest driver and will pick you up "
        f"and take you to your hotel. Once you've collected your bags, please meet me on "
        f"the 6th floor (departures level). I'm in a {vehicle_color} {make_model}, "
        f"license plate #{license_plate}. Please text me when you have collected your bags, "
        f"and I will pick you up near {door}, 5-10 minutes later."
    )


def find_contact_for_name(
    name: str,
    full_name_lookup: dict[str, dict],
    first_name_lookup: dict[str, dict],
) -> dict | None:
    """
    Find contact info for a passenger name.
    Tries full name match first, then fuzzy matching, then first name match.
    """
    name_lower = name.lower().strip()
    if not name_lower:
        return None

    # Try exact full name match
    if name_lower in full_name_lookup:
        return full_name_lookup[name_lower]

    # Split input name into parts
    name_parts = name_lower.split()
    first_name = name_parts[0] if name_parts else ""
    last_name = name_parts[-1] if len(name_parts) > 1 else ""

    # Try fuzzy matching: same/similar first name + same/similar last name
    best_match = None
    best_score = 0

    for full_name, info in full_name_lookup.items():
        contact_parts = full_name.split()
        contact_first = contact_parts[0] if contact_parts else ""
        contact_last = contact_parts[-1] if len(contact_parts) > 1 else ""

        score = 0

        # First name match (exact or similar, like Elizabeth/Elisabeth)
        if first_name == contact_first:
            score += 10
        elif (
            first_name
            and contact_first
            and len(first_name) > 2
            and len(contact_first) > 2
        ):
            # Check for similar first names (e.g., Elizabeth vs Elisabeth, Jon vs John)
            if (
                first_name in contact_first
                or contact_first in first_name
                or first_name[0] == contact_first[0]
            ):  # Same first letter
                # Calculate similarity
                common = set(first_name) & set(contact_first)
                total = set(first_name) | set(contact_first)
                if total and len(common) / len(total) > 0.7:  # 70% character overlap
                    score += 7

        # Last name match (exact or similar)
        if last_name and contact_last:
            if last_name == contact_last:
                score += 10
            elif last_name in contact_last or contact_last in last_name:
                score += 5
            else:
                # Check for typos/similar last names (e.g., Smith vs Smyth)
                common = set(last_name) & set(contact_last)
                total = set(last_name) | set(contact_last)
                if total and len(common) / len(total) > 0.8:  # 80% character overlap
                    score += 3

        if score > best_score:
            best_score = score
            best_match = info

    # Require at least similar first name + exact last name match
    # (e.g., Elizabeth Oei -> Elisabeth Oei should score 7 + 10 = 17)
    if best_score >= 12:
        return best_match

    # Try matching by first name only (if unique in contacts)
    # Also try similar first names
    for fn_key, info in first_name_lookup.items():
        if first_name == fn_key:
            return info
        # Check for similar spellings
        if len(first_name) > 2 and len(fn_key) > 2:
            if first_name[0] == fn_key[0]:  # Same first letter
                common = set(first_name) & set(fn_key)
                total = set(first_name) | set(fn_key)
                if total and len(common) / len(total) > 0.8:
                    return info

    # Try partial full name match (substring)
    for full_name, info in full_name_lookup.items():
        if name_lower in full_name or full_name in name_lower:
            return info

    return None

    # Try exact full name match
    if name_lower in full_name_lookup:
        return full_name_lookup[name_lower]

    # Split input name into parts
    name_parts = name_lower.split()
    first_name = name_parts[0] if name_parts else ""
    last_name = name_parts[-1] if len(name_parts) > 1 else ""

    # Try fuzzy matching: same first name + same/similar last name
    best_match = None
    best_score = 0

    for full_name, info in full_name_lookup.items():
        contact_parts = full_name.split()
        contact_first = contact_parts[0] if contact_parts else ""
        contact_last = contact_parts[-1] if len(contact_parts) > 1 else ""

        score = 0

        # First name match (exact or very similar)
        if first_name == contact_first:
            score += 10
        elif (
            first_name
            and contact_first
            and (
                first_name[0] == contact_first[0]
                and len(first_name) > 2
                and len(contact_first) > 2
                and (first_name in contact_first or contact_first in first_name)
            )
        ):
            # Similar first names (e.g., Elizabeth vs Elisabeth)
            score += 8

        # Last name match (exact or similar)
        if last_name and contact_last:
            if last_name == contact_last:
                score += 10
            elif last_name in contact_last or contact_last in last_name:
                score += 5

        if score > best_score:
            best_score = score
            best_match = info

    # Require at least a first name match + partial last name match
    if best_score >= 15:
        return best_match

    # Try matching by first name only (if unique)
    if first_name in first_name_lookup:
        return first_name_lookup[first_name]

    # Try partial full name match (substring)
    for full_name, info in full_name_lookup.items():
        if name_lower in full_name or full_name in name_lower:
            return info

    return None


# ---------------------------------------------------------------------------
# Sheet builder
# ---------------------------------------------------------------------------
def build_sheet(
    shift: dict,
    tasks: list[dict],
    address_lookup: dict[str, dict[str, str]],
    flight_rows: list[dict],
    rental_lookup: dict[str, dict[str, str]],
    contact_lookups: tuple[dict[str, dict], dict[str, dict]],
    date: str,
) -> dict:
    """Assemble the template context for one driver shift."""

    # --- tasks list --------------------------------------------------------
    full_name_lookup, first_name_lookup = contact_lookups
    driver_name = shift["Drivers"] or ""
    vehicle = shift["Vehicles"] or ""
    vehicle_info = rental_lookup.get(
        vehicle, {"license_plate": "TBD", "color": "TBD", "make_model": "TBD"}
    )

    # Collect all pickup messages for this shift
    all_pickup_messages = []

    task_rows = []
    for t in tasks:
        is_airport_task = (
            t["Location"] == AIRPORT_LOCATION
            or t["Location Destination"] == AIRPORT_LOCATION
        )
        flight = (
            find_flight_for_task(t["Details"] or "", flight_rows)
            if is_airport_task
            else ""
        )
        door = get_door_for_flight(flight) if flight else ""

        # Generate pickup messages for airport pickups (when location is airport = pickup)
        if is_airport_task and t["Location"] == AIRPORT_LOCATION:
            passenger_names = extract_passenger_names(t["Details"] or "")
            message_template = generate_pickup_message(
                driver_name,
                vehicle_info["color"],
                vehicle_info["make_model"],
                vehicle_info["license_plate"],
                door or "TBD",
            )

            for passenger in passenger_names:
                contact = find_contact_for_name(
                    passenger, full_name_lookup, first_name_lookup
                )
                all_pickup_messages.append(
                    {
                        "passenger": contact["name"] if contact else passenger,
                        "phone": contact["phone"] if contact else "Unknown",
                        "time": format_time_ampm(t["Start"]),
                        "message": message_template,
                    }
                )

        assigned_vehicles = [
            v.strip() for v in (t["Vehicles"] or "").split(",") if v.strip()
        ]
        shared_with = [v for v in assigned_vehicles if v != vehicle]

        task_rows.append(
            {
                "start": format_time_ampm(t["Start"]),
                "activity": t["Activity"],
                "details": t["Details"] or "",
                "location": t["Location"] or "",
                "destination": t["Location Destination"] or "",
                "notes": t["Notes"] or "",
                "is_airport_pickup": is_airport_task,
                "flight": flight,
                "door": door,
                "shared_with": shared_with,
            }
        )

    # --- unique locations (origins + destinations) -------------------------
    seen = {}
    for t in tasks:
        for loc in (t["Location"], t["Location Destination"]):
            if loc and loc not in seen:
                seen[loc] = address_lookup.get(loc, {"address": "", "phone": ""})

    location_rows = []
    for name, info in seen.items():
        addr = info["address"]
        phone = info["phone"]
        maps_link = (
            f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(addr)}"
            if addr
            else ""
        )
        location_rows.append(
            {"name": name, "address": addr, "phone": phone, "maps_link": maps_link}
        )

    # --- unique contacts (passengers only) -----------------------------
    seen_contacts = {}

    for t in tasks:
        # Extract passenger names from task details
        passenger_names = extract_passenger_names(t["Details"] or "")

        for passenger in passenger_names:
            contact = find_contact_for_name(
                passenger, full_name_lookup, first_name_lookup
            )
            if contact:
                full_name_key = contact["name"].lower()
                if full_name_key not in seen_contacts:
                    tel_link = (
                        "tel:" + re.sub(r"[^\d+]", "", contact["phone"])
                        if contact["phone"] and contact["phone"] != "Unknown"
                        else ""
                    )
                    seen_contacts[full_name_key] = {
                        "name": contact["name"],
                        "phone": contact["phone"],
                        "tel_link": tel_link,
                    }

    contact_rows = list(seen_contacts.values())

    return {
        "date": date,
        "driver": shift["Drivers"] or "",
        "vehicle": vehicle,
        "make_model": vehicle_info["make_model"],
        "license_plate": vehicle_info["license_plate"],
        "vehicle_color": vehicle_info["color"],
        "shift_start": format_time_ampm(shift["Start"]),
        "shift_end": format_time_ampm(shift["End"]),
        "pickup_location": shift["Location"] or "TBD",
        "dropoff_location": shift["Location Destination"] or "TBD",
        "tasks": task_rows,
        "locations": location_rows,
        "contacts": contact_rows,
        "pickup_messages": all_pickup_messages,
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def render(context: dict, template_src: str) -> str:
    try:
        from jinja2 import Environment, StrictUndefined
    except ImportError:
        sys.exit(
            "jinja2 is required. Install it with:\n"
            "    pip install jinja2\n"
            "or:  pip3 install jinja2"
        )

    env = Environment(
        keep_trailing_newline=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    tmpl = env.from_string(template_src)
    return tmpl.render(**context)


# ---------------------------------------------------------------------------
# Output filename
# ---------------------------------------------------------------------------
def vehicle_to_slug(vehicle: str) -> str:
    """'Minivan 1' → 'MV1', 'Minivan 2' → 'MV2'"""
    # Strip 'Minivan ' prefix and any surrounding whitespace
    num = re.sub(r"(?i)minivan\s*", "", vehicle).strip()
    return f"MV{num}"


def output_filename(date_prefix: str, vehicle: str, shift_num: int) -> str:
    """
    '4.08', 'Minivan 1', 2 → 'Shift 4.08-MV1-S2.md'
    """
    mv = vehicle_to_slug(vehicle)
    return f"Shift {date_prefix}-{mv}-S{shift_num}.md"


# ---------------------------------------------------------------------------
# Flags / warnings
# ---------------------------------------------------------------------------
def check_uncovered_tasks(
    conn: sqlite3.Connection,
    date: str,
    shifts: list[dict],
    prev_overnight_shifts: list[dict],
) -> None:
    """Warn about GT tasks that don't fall inside any driver shift window.

    Also checks overnight shifts from the previous calendar date, which may
    cover early-morning tasks stored under `date`.
    """
    cur = conn.execute(
        """
        SELECT Start, Activity, Details, Vehicles, Notes
        FROM schedule
        WHERE Date = ?
          AND Activity IN ('GT (People)', 'GT (Asset)')
        ORDER BY Vehicles, time(printf('%05s', Start))
        """,
        (date,),
    )
    all_tasks = cur.fetchall()

    midnight = time(0, 0)

    uncovered = []
    for row in all_tasks:
        task_start, activity, details, vehicle, notes = row
        t = parse_time(task_start)
        covered = False

        # Check same-date shifts
        for s in shifts:
            if not vehicle_matches(vehicle, s["Vehicles"]):
                continue
            if time_in_window(t, parse_time(s["Start"]), parse_time(s["End"])):
                covered = True
                break

        # Check overnight shifts that started on the previous date
        if not covered:
            for s in prev_overnight_shifts:
                if not vehicle_matches(vehicle, s["Vehicles"]):
                    continue
                # Post-midnight tail runs from 0:00 to shift end
                if time_in_window(t, midnight, parse_time(s["End"])):
                    covered = True
                    break

        if not covered:
            uncovered.append((task_start, vehicle, activity, details, notes))

    if uncovered:
        print("\n⚠  Uncovered GT tasks (outside all shift windows):")
        for task_start, vehicle, activity, details, notes in uncovered:
            note_str = f"  [{notes}]" if notes else ""
            print(f"   {task_start}  {vehicle}  {activity}  {details}{note_str}")
        print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Generate driver sheets for a date.")
    parser.add_argument("date", help='Date to process, e.g. "4/8" or "4/8 (Wednesday)"')
    args = parser.parse_args()

    try:
        date = normalise_date(args.date)
    except ValueError as e:
        sys.exit(str(e))

    date_prefix = date_to_file_prefix(date)
    template_src = TEMPLATE_PATH.read_text()
    OUTPUT_DIR.mkdir(exist_ok=True)

    conn = sqlite3.connect(DB_PATH)

    shifts = get_driver_shifts(conn, date)
    if not shifts:
        sys.exit(f"No driver shifts found for '{date}'.")

    prev_overnight_shifts = get_overnight_shifts_from_prev_date(conn, date)
    nxt = next_date(date)

    address_lookup = get_address_lookup(conn)
    flight_rows = get_flight_lookup(conn, date)
    rental_lookup = get_rental_lookup(conn)
    contact_lookups = get_contact_lookups(conn)

    # Track shift count per vehicle to assign S1, S2, ...
    vehicle_shift_counter: dict[str, int] = {}

    generated = []
    for shift in shifts:
        vehicle = shift["Vehicles"]
        vehicle_shift_counter[vehicle] = vehicle_shift_counter.get(vehicle, 0) + 1
        shift_num = vehicle_shift_counter[vehicle]

        shift_start = parse_time(shift["Start"])
        shift_end = parse_time(shift["End"])

        tasks = get_gt_tasks(conn, date, vehicle, shift_start, shift_end, next_date=nxt)
        context = build_sheet(
            shift,
            tasks,
            address_lookup,
            flight_rows,
            rental_lookup,
            contact_lookups,
            date,
        )

        content = render(context, template_src)

        fname = output_filename(date_prefix, vehicle, shift_num)
        out_path = OUTPUT_DIR / fname
        out_path.write_text(content)
        generated.append(
            (
                fname,
                shift["Drivers"],
                vehicle,
                shift["Start"],
                shift["End"],
                len(tasks),
            )
        )

    check_uncovered_tasks(conn, date, shifts, prev_overnight_shifts)
    conn.close()

    print(f"Generated {len(generated)} sheet(s) for {date}:\n")
    for fname, driver, vehicle, start, end, n_tasks in generated:
        print(
            f"  driver-sheets/{fname}  ({driver}, {vehicle}, {start}–{end}, {n_tasks} task(s))"
        )
    print()


if __name__ == "__main__":
    main()
