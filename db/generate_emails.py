#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = ["markdown"]
# ///
"""
Generate driver email files for a given date.

Usage:
    uv run db/generate_emails.py "4/8"
    uv run db/generate_emails.py "4/8 (Wednesday)"

Reads shift sheets from driver-sheets/ and generates email files in emails/.
Run generate_sheets.py first to create the shift sheets.
"""

import argparse
import re
import sqlite3
import sys
from pathlib import Path

import markdown

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "db" / "master_schedule.db"
SHEET_DIR = REPO_ROOT / "driver-sheets"
EMAIL_DIR = REPO_ROOT / "emails"

PARKING_LINK = "https://docs.google.com/document/d/1uiPNSprNHtB5df02xG6g0HuZuNMYXbDCk9x9cK8R08g/edit?usp=sharing"

CC_ADDRESSES = [
    "adi@denverjazz.org",
    "colinswihart@denverjazz.org",
]

DATE_LABELS = {
    "4/7": "4/7 (Tuesday)",
    "4/8": "4/8 (Wednesday)",
    "4/9": "4/9 (Thursday)",
    "4/10": "4/10 (Friday)",
    "4/11": "4/11 (Saturday)",
    "4/12": "4/12 (Sunday)",
}

DAY_ABBREV = {
    "Tuesday": "Tue",
    "Wednesday": "Wed",
    "Thursday": "Thu",
    "Friday": "Fri",
    "Saturday": "Sat",
    "Sunday": "Sun",
}


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


def date_to_file_prefix(canonical: str) -> str:
    base = re.sub(r"\s*\(.*\)$", "", canonical).strip()
    month, day = base.split("/")
    return f"{month}.{int(day):02d}"


def extract_day_of_week(canonical: str) -> str:
    m = re.search(r"\((\w+)\)", canonical)
    return m.group(1) if m else ""


def ordinal(n: int) -> str:
    if 11 <= n <= 13:
        return f"{n}th"
    return f"{n}{['th', 'st', 'nd', 'rd', 'th', 'th', 'th', 'th', 'th', 'th'][n % 10]}"


def get_driver_email_lookup(conn: sqlite3.Connection) -> dict[str, str]:
    """
    Build a full name → email map for drivers from the contacts table.
    Prefers the Volunteer/Ground Transportation role entry if duplicates exist.
    """
    cur = conn.execute(
        """
        SELECT "Full Name", Email, "Role "
        FROM contacts
        WHERE Email IS NOT NULL AND Email != ''
        ORDER BY
            CASE WHEN "Role " LIKE '%Ground Transportation%' THEN 0 ELSE 1 END
        """
    )
    lookup: dict[str, str] = {}
    for full_name, email, _role in cur.fetchall():
        name = (full_name or "").strip()
        if name and name not in lookup:
            lookup[name] = email.strip()
    return lookup


def parse_sheet(path: Path) -> dict:
    """Parse a generated shift sheet markdown file."""
    text = path.read_text()
    lines = text.splitlines()

    # Driver name from first heading: # Mario Rivera - 4/8 (Wednesday)
    driver = ""
    m = re.match(r"^#\s+(.+?)\s*-\s*\d+/\d+", lines[0])
    if m:
        driver = m.group(1).strip()

    # Shift time from second heading: ## 9:00 AM - 3:00 PM
    shift_start = shift_end = ""
    for line in lines:
        m = re.match(r"^##\s+(.+?)\s*-\s*(.+)$", line)
        if m:
            shift_start = m.group(1).strip()
            shift_end = m.group(2).strip()
            break

    # Vehicle line: Minivan 1 - Black Chrysler Pacifica - TMO-S1G
    vehicle = ""
    vehicle_detail = ""
    for line in lines:
        m = re.match(r"^(Minivan \d+)\s*-\s*(.+)$", line)
        if m:
            vehicle = m.group(1)
            vehicle_detail = m.group(2).strip()
            break

    # Count tasks (### headings)
    task_count = sum(1 for line in lines if re.match(r"^###\s+", line))

    return {
        "driver": driver,
        "first_name": driver.split()[0] if driver else "",
        "shift_start": shift_start,
        "shift_end": shift_end,
        "vehicle": vehicle,
        "vehicle_detail": vehicle_detail,
        "task_count": task_count,
        "content": text,
    }


HTML_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: sans-serif; max-width: 720px; margin: 2em auto; line-height: 1.5; }}
  .meta {{ background: #f5f5f5; border: 1px solid #ddd; padding: 12px 16px;
           border-radius: 6px; margin-bottom: 24px; font-size: 14px; }}
  .meta strong {{ display: inline-block; width: 60px; }}
  h1 {{ font-size: 1.4em; }}
  h2 {{ font-size: 1.2em; }}
  h3 {{ font-size: 1.05em; }}
  hr {{ border: none; border-top: 1px solid #ccc; margin: 24px 0; }}
  a {{ color: #1a73e8; }}
</style>
</head>
<body>
<div class="meta">
  <strong>To:</strong> {to}<br>
  <strong>CC:</strong> {cc}<br>
  <strong>Subject:</strong> {subject}
</div>
{body_html}
</body>
</html>"""


def md_to_html(md_text: str) -> str:
    """Convert markdown to HTML."""
    return markdown.markdown(md_text, extensions=["sane_lists"])


def generate_email(
    info: dict, canonical_date: str, driver_email: str
) -> tuple[str, str]:
    """Generate email subject and HTML body for a driver shift."""
    day_of_week = extract_day_of_week(canonical_date)
    day_abbrev = DAY_ABBREV.get(day_of_week, day_of_week[:3])
    base_date = re.sub(r"\s*\(.*\)$", "", canonical_date).strip()
    day_num = int(base_date.split("/")[1])

    subject = (
        f"Your Driver Shift - {day_abbrev} {base_date} "
        f"({info['shift_start']} - {info['shift_end']}) - {info['vehicle']}"
    )

    cc_line = ", ".join(CC_ADDRESSES)

    # Vehicle description for body
    if info["vehicle_detail"] and "TBD" not in info["vehicle_detail"]:
        vehicle_desc = f"**{info['vehicle']}** ({info['vehicle_detail']})"
    else:
        vehicle_desc = f"**{info['vehicle']}**"

    body_md = (
        f"Hi {info['first_name']},\n"
        f"\n"
        f"You're driving {vehicle_desc} on "
        f"**{day_of_week}, April {ordinal(day_num)}** "
        f"from **{info['shift_start']} \u2013 {info['shift_end']}**.\n"
        f"\n"
        f"**Pickup/Dropoff:** Warwick Hotel\n"
        f"\n"
        f"You have **{info['task_count']} tasks** \u2014 see your full shift "
        f"sheet below for all details, addresses, phone numbers, and timing.\n"
        f"\n"
        f"**Important:** Review the [parking process]({PARKING_LINK}) "
        f"before your shift.\n"
        f"\n"
        f"Questions? Call Tom at 513-675-4467 or Adi at 917-494-2896.\n"
        f"\n"
        f"---\n"
        f"\n"
        f"{info['content']}"
    )

    body_html = md_to_html(body_md)

    html = HTML_TEMPLATE.format(
        to=driver_email,
        cc=cc_line,
        subject=subject,
        body_html=body_html,
    )

    return subject, html


def main():
    parser = argparse.ArgumentParser(
        description="Generate driver email files for a date."
    )
    parser.add_argument("date", help='Date to process, e.g. "4/8" or "4/8 (Wednesday)"')
    args = parser.parse_args()

    try:
        date = normalise_date(args.date)
    except ValueError as e:
        sys.exit(str(e))

    prefix = date_to_file_prefix(date)

    sheets = sorted(SHEET_DIR.glob(f"Shift {prefix}-*.md"))
    if not sheets:
        sys.exit(f"No shift sheets found for {date}. Run generate_sheets.py first.")

    conn = sqlite3.connect(DB_PATH)
    email_lookup = get_driver_email_lookup(conn)
    conn.close()

    EMAIL_DIR.mkdir(exist_ok=True)

    # Clean old email files for this date
    for old in EMAIL_DIR.glob(f"email-{prefix}-*.html"):
        old.unlink()

    generated = []
    for sheet_path in sheets:
        info = parse_sheet(sheet_path)
        driver_email = email_lookup.get(info["driver"], "")
        if not driver_email:
            print(f"⚠  No email found for {info['driver']}", file=sys.stderr)

        subject, html = generate_email(info, date, driver_email)

        # Shift 4.08-MV1-S1.md → email-4.08-MV1-S1-mario.html
        stem = sheet_path.stem.replace("Shift ", "")
        first_name = info["first_name"].lower()
        email_fname = f"email-{stem}-{first_name}.html"

        out_path = EMAIL_DIR / email_fname
        out_path.write_text(html)
        generated.append((email_fname, info["driver"], driver_email, subject))

    print(f"Generated {len(generated)} email(s) for {date}:\n")
    for fname, driver, email, subject in generated:
        print(f"  emails/{fname}")
        print(f"    To: {driver} <{email}>")
        print(f"    CC: {', '.join(CC_ADDRESSES)}")
        print(f"    Subject: {subject}")
        print()


if __name__ == "__main__":
    main()
