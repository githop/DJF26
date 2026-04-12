#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = ["jinja2"]
# ///
"""
Generate a daily GTC agenda showing all driver shifts and GT tasks for a date.

Usage:
    uv run db/generate_agenda.py "4/8 (Wednesday)"

    # Short forms also accepted:
    uv run db/generate_agenda.py 4/8
    uv run db/generate_agenda.py "4/8"

Output: daily-agendas/Agenda M.DD.md
"""

import argparse
import re
import sqlite3
import sys
from datetime import time
from pathlib import Path

from jinja2 import Environment, StrictUndefined

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "db" / "master_schedule.db"
TEMPLATE_PATH = REPO_ROOT / "AGENDA_TEMPLATE.md"
OUTPUT_DIR = REPO_ROOT / "daily-agendas"


# ---------------------------------------------------------------------------
# Date normalisation  (mirrors generate_sheets.py)
# ---------------------------------------------------------------------------
DATE_LABELS = {
    "4/7": "4/7 (Tuesday)",
    "4/8": "4/8 (Wednesday)",
    "4/9": "4/9 (Thursday)",
    "4/10": "4/10 (Friday)",
    "4/11": "4/11 (Saturday)",
    "4/12": "4/12 (Sunday)",
}

DATE_ORDER = list(DATE_LABELS.values())


def normalise_date(raw: str) -> str:
    raw = raw.strip()
    if raw in DATE_LABELS.values():
        return raw
    base = re.sub(r"\s*\(.*\)$", "", raw).strip()
    if base in DATE_LABELS:
        return DATE_LABELS[base]
    raise ValueError(
        f"Unrecognised date '{raw}'. Expected one of: {', '.join(DATE_LABELS.keys())}"
    )


def previous_date(canonical: str) -> str | None:
    idx = DATE_ORDER.index(canonical)
    return DATE_ORDER[idx - 1] if idx > 0 else None


def next_date(canonical: str) -> str | None:
    idx = DATE_ORDER.index(canonical)
    return DATE_ORDER[idx + 1] if idx < len(DATE_ORDER) - 1 else None


def date_to_file_prefix(canonical: str) -> str:
    """'4/8 (Wednesday)' -> '4.08'"""
    base = re.sub(r"\s*\(.*\)$", "", canonical).strip()
    month, day = base.split("/")
    return f"{month}.{int(day):02d}"


# ---------------------------------------------------------------------------
# Time helpers  (mirrors generate_sheets.py)
# ---------------------------------------------------------------------------
def parse_time(s: str) -> time:
    h, m = s.strip().split(":")
    return time(int(h), int(m))


def time_in_window(t: time, start: time, end: time) -> bool:
    if start <= end:
        return start <= t <= end
    return t >= start or t <= end


def format_time_ampm(s: str) -> str:
    if not s:
        return ""
    t = parse_time(s)
    return t.strftime("%I:%M %p").lstrip("0")


# ---------------------------------------------------------------------------
# DB queries
# ---------------------------------------------------------------------------
def get_driver_shifts(conn: sqlite3.Connection, date: str) -> list[dict]:
    cur = conn.execute(
        """
        SELECT Drivers, Vehicles, Start, "End", Location, "Destination"
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
    prev = previous_date(date)
    if prev is None:
        return []
    shifts = get_driver_shifts(conn, prev)
    return [s for s in shifts if parse_time(s["End"]) < parse_time(s["Start"])]


def vehicle_matches(task_vehicles: str, shift_vehicle: str) -> bool:
    if not task_vehicles:
        return False
    return shift_vehicle in [v.strip() for v in task_vehicles.split(",")]


def get_gt_tasks(
    conn: sqlite3.Connection,
    date: str,
    vehicle: str,
    shift_start: time,
    shift_end: time,
    next_date_str: str | None = None,
) -> list[dict]:
    def fetch_rows(d: str) -> list[dict]:
        cur = conn.execute(
            """
            SELECT Start, "End", Activity, Details, Location,
                   "Destination", Pax, Notes, Vehicles
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

    if is_overnight and next_date_str:
        same_day = [
            r
            for r in rows
            if vehicle_matches(r["Vehicles"], vehicle)
            and time_in_window(parse_time(r["Start"]), shift_start, time(23, 59))
        ]
        next_rows = fetch_rows(next_date_str)
        next_day = [
            r
            for r in next_rows
            if vehicle_matches(r["Vehicles"], vehicle)
            and time_in_window(parse_time(r["Start"]), time(0, 0), shift_end)
        ]
        return same_day + next_day

    return [
        r
        for r in rows
        if vehicle_matches(r["Vehicles"], vehicle)
        and time_in_window(parse_time(r["Start"]), shift_start, shift_end)
    ]


def get_all_gt_tasks(conn: sqlite3.Connection, date: str) -> list[dict]:
    """Fetch every GT task for a date regardless of vehicle/shift assignment."""
    cur = conn.execute(
        """
        SELECT Start, "End", Activity, Details, Location,
               "Destination", Pax, Notes, Vehicles
        FROM schedule
        WHERE Date = ?
          AND Activity IN ('GT (People)', 'GT (Asset)')
        ORDER BY time(printf('%05s', Start))
        """,
        (date,),
    )
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_rental_lookup(conn: sqlite3.Connection) -> dict[str, dict[str, str]]:
    try:
        cur = conn.execute(
            'SELECT Vehicle, "License Plate Number", Color, "Make / Model" FROM rentals'
        )
        return {
            row[0]: {
                "license_plate": row[1] or "TBD",
                "color": row[2] or "TBD",
                "make_model": row[3] or "TBD",
            }
            for row in cur.fetchall()
        }
    except sqlite3.OperationalError:
        return {}


# ---------------------------------------------------------------------------
# Uncovered-task detection  (mirrors generate_sheets.py)
# ---------------------------------------------------------------------------
def find_uncovered_tasks(
    conn: sqlite3.Connection,
    date: str,
    shifts: list[dict],
    prev_overnight_shifts: list[dict],
) -> list[dict]:
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

    midnight = time(0, 0)
    uncovered = []

    for row in cur.fetchall():
        task_start, activity, details, vehicle, notes = row
        if not task_start:
            continue
        t = parse_time(task_start)
        covered = False

        for s in shifts:
            if not vehicle_matches(vehicle, s["Vehicles"]):
                continue
            if time_in_window(t, parse_time(s["Start"]), parse_time(s["End"])):
                covered = True
                break

        if not covered:
            for s in prev_overnight_shifts:
                if not vehicle_matches(vehicle, s["Vehicles"]):
                    continue
                if time_in_window(t, midnight, parse_time(s["End"])):
                    covered = True
                    break

        if not covered:
            uncovered.append(
                {
                    "start": format_time_ampm(task_start),
                    "vehicle": vehicle or "Unassigned",
                    "activity": activity,
                    "details": details or "",
                    "notes": notes or "",
                }
            )

    return uncovered


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------
def build_agenda_context(conn: sqlite3.Connection, date: str) -> dict:
    shifts = get_driver_shifts(conn, date)
    prev_overnight = get_overnight_shifts_from_prev_date(conn, date)
    nxt = next_date(date)
    rental_lookup = get_rental_lookup(conn)
    all_gt = get_all_gt_tasks(conn, date)

    # -- Vehicle summary ---------------------------------------------------
    vehicles: dict[str, dict] = {}
    vehicle_shift_counter: dict[str, int] = {}

    for shift in shifts:
        v = shift["Vehicles"]
        if v not in vehicles:
            info = rental_lookup.get(
                v, {"license_plate": "TBD", "color": "TBD", "make_model": "TBD"}
            )
            vehicles[v] = {
                "name": v,
                "make_model": info["make_model"],
                "color": info["color"],
                "license_plate": info["license_plate"],
                "shift_count": 0,
                "drivers": [],
            }
        vehicles[v]["shift_count"] += 1
        driver = shift["Drivers"] or "TBD"
        if driver not in vehicles[v]["drivers"]:
            vehicles[v]["drivers"].append(driver)

    vehicle_summary = list(vehicles.values())

    # -- Shifts with tasks, grouped by vehicle -----------------------------
    vehicle_shift_counter = {}
    shift_groups: dict[str, list[dict]] = {}

    for shift in shifts:
        v = shift["Vehicles"]
        vehicle_shift_counter[v] = vehicle_shift_counter.get(v, 0) + 1
        shift_num = vehicle_shift_counter[v]

        shift_start = parse_time(shift["Start"])
        shift_end = parse_time(shift["End"])
        tasks = get_gt_tasks(conn, date, v, shift_start, shift_end, next_date_str=nxt)

        task_rows = []
        for t in tasks:
            task_rows.append(
                {
                    "start": format_time_ampm(t["Start"]),
                    "details": t["Details"] or "",
                    "origin": t["Location"] or "",
                    "destination": t["Destination"] or "",
                    "pax": t["Pax"] or "",
                    "notes": t["Notes"] or "",
                }
            )

        # Build driver sheet filename: Shift [M.DD]-[MV#]-S#.md
        date_prefix = date_to_file_prefix(date)
        vehicle_slug = vehicle_to_slug(v)
        sheet_filename = f"Shift {date_prefix}-{vehicle_slug}-S{shift_num}.md"

        shift_entry = {
            "shift_label": f"S{shift_num}",
            "driver": shift["Drivers"] or "TBD",
            "start": format_time_ampm(shift["Start"]),
            "end": format_time_ampm(shift["End"]),
            "pickup": shift["Location"] or "TBD",
            "dropoff": shift["Destination"] or "TBD",
            "task_count": len(task_rows),
            "tasks": task_rows,
            "sheet_filename": sheet_filename,
        }

        shift_groups.setdefault(v, []).append(shift_entry)

    vehicle_blocks = []
    for v_name in vehicles:
        vehicle_blocks.append(
            {
                "name": v_name,
                "shifts": shift_groups.get(v_name, []),
            }
        )

    # -- Full timeline (all GT tasks, chronological) -----------------------
    # Build a lookup for which driver is assigned to each task
    midnight = time(0, 0)

    def find_drivers_for_task(task_start: str, task_vehicle: str) -> str:
        """Find all drivers assigned to a task based on time and vehicle(s)."""
        if not task_vehicle:
            return ""
        t = parse_time(task_start)

        # Handle multi-vehicle tasks like "Minivan 2, Minivan 3"
        vehicles = [v.strip() for v in task_vehicle.split(",")]
        matched_drivers = []

        for vehicle in vehicles:
            # Check same-date shifts
            for shift in shifts:
                if shift["Vehicles"] != vehicle:
                    continue
                if time_in_window(
                    t, parse_time(shift["Start"]), parse_time(shift["End"])
                ):
                    driver = shift["Drivers"] or ""
                    if driver and driver not in matched_drivers:
                        matched_drivers.append(driver)
                    break

            # Check overnight shifts from previous date
            for shift in prev_overnight:
                if shift["Vehicles"] != vehicle:
                    continue
                if time_in_window(t, midnight, parse_time(shift["End"])):
                    driver = shift["Drivers"] or ""
                    if driver and driver not in matched_drivers:
                        matched_drivers.append(driver)
                    break

        return ", ".join(matched_drivers) if matched_drivers else ""

    timeline = []
    for t in all_gt:
        driver = find_drivers_for_task(t["Start"], t["Vehicles"])
        timeline.append(
            {
                "start": format_time_ampm(t["Start"]),
                "vehicle": t["Vehicles"] or "Unassigned",
                "driver": driver,
                "activity": t["Activity"],
                "details": t["Details"] or "",
                "origin": t["Location"] or "",
                "destination": t["Destination"] or "",
                "pax": t["Pax"] or "",
                "notes": t["Notes"] or "",
            }
        )

    # -- Uncovered tasks ---------------------------------------------------
    uncovered = find_uncovered_tasks(conn, date, shifts, prev_overnight)

    # -- Stats -------------------------------------------------------------
    total_shifts = len(shifts)
    total_tasks = len(all_gt)
    total_vehicles = len(vehicles)

    return {
        "date": date,
        "total_vehicles": total_vehicles,
        "total_shifts": total_shifts,
        "total_tasks": total_tasks,
        "vehicle_summary": vehicle_summary,
        "vehicle_blocks": vehicle_blocks,
        "timeline": timeline,
        "uncovered": uncovered,
    }


# ---------------------------------------------------------------------------
# Filename helpers
# ---------------------------------------------------------------------------
def vehicle_to_slug(vehicle: str) -> str:
    """'Minivan 1' → 'MV1', 'Minivan 2' → 'MV2'"""
    import re

    num = re.sub(r"(?i)minivan\s*", "", vehicle).strip()
    return f"MV{num}"


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def render(context: dict, template_src: str) -> str:
    env = Environment(
        keep_trailing_newline=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    tmpl = env.from_string(template_src)
    return tmpl.render(**context)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Generate a GTC daily agenda for a date."
    )
    parser.add_argument("date", help='Date to process, e.g. "4/8" or "4/8 (Wednesday)"')
    args = parser.parse_args()

    try:
        date = normalise_date(args.date)
    except ValueError as e:
        sys.exit(str(e))

    if not DB_PATH.exists():
        sys.exit(f"Database not found at {DB_PATH}. Run: python3 db/migrate_csv.py")

    if not TEMPLATE_PATH.exists():
        sys.exit(f"Template not found at {TEMPLATE_PATH}.")

    conn = sqlite3.connect(DB_PATH)
    context = build_agenda_context(conn, date)
    conn.close()

    if context["total_shifts"] == 0:
        print(f"No driver shifts found for '{date}'.")
        return

    template_src = TEMPLATE_PATH.read_text()
    content = render(context, template_src)

    OUTPUT_DIR.mkdir(exist_ok=True)
    date_prefix = date_to_file_prefix(date)
    out_path = OUTPUT_DIR / f"Agenda {date_prefix}.md"
    out_path.write_text(content)

    print(f"Generated agenda for {date}:")
    print(f"  {out_path.relative_to(REPO_ROOT)}")
    print(
        f"  {context['total_vehicles']} vehicle(s), "
        f"{context['total_shifts']} shift(s), "
        f"{context['total_tasks']} GT task(s)"
    )
    if context["uncovered"]:
        print(
            f"  {len(context['uncovered'])} uncovered task(s) -- see agenda for details"
        )
    print()


if __name__ == "__main__":
    main()
