# AGENTS.md - Denver Jazz Fest 2026

## Overview

**Database**: `db/master_schedule.db` (SQLite)  
**Table**: `schedule`  
**Key columns**: Date, Start, End, Activity, Details, Location, Location Address, Location Destination, Pax, Vehicles, Drivers, Notes

If the CSV has been updated, refresh the database: `python3 db/migrate_csv.py`

## Generating Driver Sheets

```bash
uv run db/generate_sheets.py "4/8"
# or with full label:
uv run db/generate_sheets.py "4/8 (Wednesday)"
```

**Output directory:** `driver-sheets/`  
**File naming:** `Shift [M.DD]-[MV#]-S#.md` (e.g. `Shift 4.08-MV1-S1.md`)

- Shift numbers (`S1`, `S2`, ...) are assigned chronologically per vehicle.
- Existing files for the date are always overwritten.
- After generation, the script prints a warning for any GT tasks that fall outside all defined shift windows (e.g. `Don's Car` tasks, `Adi to do` tasks).

### Manual DB queries (for reference / debugging)

**IMPORTANT: Time Comparison Gotcha**

`Start` times are stored as un-padded strings (e.g., `8:30` not `08:30`). Simple string comparison will fail for single-digit hours — `'8:30' > '15:00'` is true lexicographically. Always use:

```sql
time(printf('%05s', Start))
```

Find all driver shifts for a date:

```bash
sqlite3 db/master_schedule.db "
SELECT Drivers, Vehicles, Start, \"End\"
FROM schedule
WHERE Date = '4/8 (Wednesday)'
  AND Activity IN ('Staff: Driver', 'Driver Volunteer Shift')
ORDER BY Vehicles, time(printf('%05s', Start))"
```

Find GT tasks for a shift:

```bash
sqlite3 db/master_schedule.db "
SELECT gt.Start, gt.Activity, gt.Details, gt.Location, gt.\"Location Destination\", gt.Pax, gt.Notes
FROM schedule gt
WHERE gt.Date = '4/8 (Wednesday)'
  AND gt.Activity IN ('GT (People)', 'GT (Asset)')
  AND gt.Vehicles = 'Minivan 1'
  AND time(printf('%05s', gt.Start)) >= time('08:30')
  AND time(printf('%05s', gt.Start)) < time('15:00')
ORDER BY time(printf('%05s', gt.Start))"
```

Find flight info for a date:

```bash
sqlite3 db/master_schedule.db "
SELECT Start, Details FROM schedule
WHERE Date = '4/8 (Wednesday)' AND Activity = 'Flight'
ORDER BY time(printf('%05s', Start))"
```

## Generating Daily Agenda (GTC Overview)

```bash
uv run db/generate_agenda.py "4/8"
# or with full label:
uv run db/generate_agenda.py "4/8 (Wednesday)"
```

**Output directory:** `daily-agendas/`  
**File naming:** `Agenda M.DD.md` (e.g. `Agenda 4.08.md`)

The agenda is a single-page overview for the Grand Transport Coordinator that includes:

- **Vehicle Summary** — which vehicles are active, shift counts, and assigned drivers
- **Shift Overview** — each shift grouped by vehicle with a table of GT tasks
- **Full Timeline** — every GT task for the day in chronological order across all vehicles
- **Uncovered Tasks** — GT tasks that fall outside all defined shift windows (e.g. `Don's Car`, `Adi to do`)

## Airport Pickup Messages

The driver sheets now automatically generate personalized text messages for airport pickups. For each passenger being picked up from Denver Airport, the sheet includes a pre-written message that drivers can copy and send:

> Hi, it's [Driver Name]. I'm a Denver Jazz Fest driver and will pick you up and take you to your hotel. Once you've collected your bags, please meet me on the 6th floor (departures level). I'm in a [color] [car model], license plate #[license plate]. Please text me when you have collected your bags, and I will pick you up near [Door Number], 5-10 minutes later.

The message is automatically populated with:
- Driver name from the shift assignment
- Vehicle color, make/model, and license plate from the rentals table
- Door number and side (East/West) based on the airline code from the flight lookup
- Each passenger gets their own message line with their name

## Tips

- Use `Details` as the authoritative description of who is being transported. Do **not** use `Artist/Group` — it refers to the act/billing, not the individuals in the vehicle.
- Always double-quote column names with spaces: `"Location Address"`, `"Location Destination"`, `"Artist/Group"`
- After generating all files, flag any GT tasks whose `Start` falls outside all defined shift windows, and any tasks handled outside the driver system (e.g., "Adi to do", personal cars)

## File Structure

```
.
├── AGENTS.md                           # This file
├── TEMPLATE.md                         # Jinja2 driver sheet template
├── AGENDA_TEMPLATE.md                  # Jinja2 daily agenda template
├── DJF26_ Master Schedule - Master.csv # Source data
├── db/
│   ├── master_schedule.db              # SQLite database (generated)
│   ├── migrate_csv.py                  # CSV → DB migration script
│   ├── generate_sheets.py              # Driver sheet generation script
│   └── generate_agenda.py              # GTC daily agenda generation script
├── driver-sheets/                      # Generated driver sheets
│   └── Shift [M.DD]-[MV#]-S#.md
└── daily-agendas/                      # Generated GTC daily agendas
    └── Agenda M.DD.md
```
