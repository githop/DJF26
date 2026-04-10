#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = ["jinja2", "markdown"]
# ///
"""
Build HTML site from generated markdown files with clean URLs.

URL structure:
    /agendas/{date}/
    /shifts/{date}/{driver-name}/{van}-{shift}/

Usage:
    uv run db/build_site.py
"""

import re
import markdown
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE_DIR = REPO_ROOT / "site"
DRIVER_SHEETS_DIR = REPO_ROOT / "driver-sheets"
AGENDAS_DIR = REPO_ROOT / "daily-agendas"

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} | DJF26 Driver Portal</title>
    <style>
        :root {{
            --bg: #0f0f0f;
            --fg: #f0f0f0;
            --accent: #ff6b35;
            --muted: #888;
            --border: #333;
            --card: #1a1a1a;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--fg);
            line-height: 1.6;
            padding: 2rem;
            max-width: 900px;
            margin: 0 auto;
        }}
        header {{
            border-bottom: 2px solid var(--accent);
            padding-bottom: 1rem;
            margin-bottom: 2rem;
        }}
        header h1 {{
            color: var(--accent);
            font-size: 1.5rem;
            text-transform: uppercase;
            letter-spacing: 0.1em;
        }}
        header p {{
            color: var(--muted);
            font-size: 0.9rem;
            margin-top: 0.5rem;
        }}
        .breadcrumb {{
            color: var(--muted);
            font-size: 0.85rem;
            margin-bottom: 1.5rem;
        }}
        .breadcrumb a {{
            color: var(--accent);
            text-decoration: none;
        }}
        .breadcrumb a:hover {{ text-decoration: underline; }}
        .content {{
            background: var(--card);
            border-radius: 8px;
            padding: 2rem;
            border: 1px solid var(--border);
        }}
        .content h1 {{
            color: var(--accent);
            font-size: 1.8rem;
            margin-bottom: 1rem;
            border-bottom: 1px solid var(--border);
            padding-bottom: 0.5rem;
        }}
        .content h2 {{
            color: var(--fg);
            font-size: 1.3rem;
            margin-top: 2rem;
            margin-bottom: 1rem;
        }}
        .content h3 {{
            color: var(--muted);
            font-size: 1.1rem;
            margin-top: 1.5rem;
            margin-bottom: 0.75rem;
        }}
        .content p {{
            margin-bottom: 1rem;
            color: var(--fg);
        }}
        .content ul, .content ol {{
            margin-left: 1.5rem;
            margin-bottom: 1rem;
        }}
        .content li {{
            margin-bottom: 0.5rem;
        }}
        .content table {{
            width: 100%;
            border-collapse: collapse;
            margin: 1.5rem 0;
            font-size: 0.9rem;
        }}
        .content th {{
            background: var(--accent);
            color: var(--bg);
            padding: 0.75rem;
            text-align: left;
            font-weight: 600;
        }}
        .content td {{
            padding: 0.75rem;
            border-bottom: 1px solid var(--border);
        }}
        .content tr:hover {{
            background: rgba(255,107,53,0.05);
        }}
        .content code {{
            background: var(--bg);
            padding: 0.2rem 0.4rem;
            border-radius: 3px;
            font-family: 'SF Mono', Monaco, monospace;
            font-size: 0.9em;
        }}
        .content pre {{
            background: var(--bg);
            padding: 1rem;
            border-radius: 6px;
            overflow-x: auto;
            border: 1px solid var(--border);
            margin-bottom: 1rem;
        }}
        .content blockquote {{
            border-left: 3px solid var(--accent);
            padding-left: 1rem;
            margin-left: 0;
            color: var(--muted);
            font-style: italic;
        }}
        .content hr {{
            border: none;
            border-top: 1px solid var(--border);
            margin: 2rem 0;
        }}
        footer {{
            margin-top: 3rem;
            padding-top: 1rem;
            border-top: 1px solid var(--border);
            color: var(--muted);
            font-size: 0.85rem;
            text-align: center;
        }}
        @media (max-width: 600px) {{
            body {{ padding: 1rem; }}
            .content {{ padding: 1rem; }}
            .content table {{
                font-size: 0.8rem;
            }}
            .content th, .content td {{
                padding: 0.5rem;
            }}
        }}
    </style>
</head>
<body>
    <header>
        <h1>🎷 Denver Jazz Fest 2026</h1>
        <p>Driver Portal • Grand Transportation Coordination</p>
    </header>
    {breadcrumb}
    <div class="content">
        {content}
    </div>
    <footer>
        <p>Generated {timestamp} • Internal Use Only</p>
    </footer>
</body>
</html>
"""

LANDING_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DJF26 Driver Portal</title>
    <style>
        :root {{
            --bg: #0f0f0f;
            --fg: #f0f0f0;
            --accent: #ff6b35;
            --muted: #888;
            --border: #333;
            --card: #1a1a1a;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--fg);
            line-height: 1.6;
            padding: 2rem;
            max-width: 1200px;
            margin: 0 auto;
        }}
        header {{
            text-align: center;
            padding: 3rem 1rem;
            border-bottom: 2px solid var(--accent);
            margin-bottom: 3rem;
        }}
        header h1 {{
            color: var(--accent);
            font-size: 2.5rem;
            text-transform: uppercase;
            letter-spacing: 0.15em;
            margin-bottom: 0.5rem;
        }}
        header p {{
            color: var(--muted);
            font-size: 1.1rem;
        }}
        .dates-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 1.5rem;
        }}
        .date-card {{
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 1.5rem;
        }}
        .date-card h2 {{
            color: var(--accent);
            font-size: 1.4rem;
            margin-bottom: 1rem;
            text-align: center;
        }}
        .date-card h3 {{
            color: var(--muted);
            font-size: 0.9rem;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            margin: 1rem 0 0.5rem 0;
        }}
        .date-card a {{
            display: block;
            padding: 0.5rem 0;
            color: var(--fg);
            text-decoration: none;
            border-bottom: 1px solid var(--border);
        }}
        .date-card a:hover {{
            color: var(--accent);
        }}
        .date-card a:last-child {{
            border-bottom: none;
        }}
        .agenda-link {{
            display: inline-block;
            background: var(--accent);
            color: var(--bg) !important;
            padding: 0.5rem 1rem;
            border-radius: 4px;
            font-weight: 600;
            margin-top: 0.5rem;
            text-align: center;
        }}
        footer {{
            margin-top: 4rem;
            padding-top: 2rem;
            border-top: 1px solid var(--border);
            color: var(--muted);
            font-size: 0.85rem;
            text-align: center;
        }}
        @media (max-width: 600px) {{
            header h1 {{ font-size: 1.8rem; }}
            body {{ padding: 1rem; }}
        }}
    </style>
</head>
<body>
    <header>
        <h1>🎷 Denver Jazz Fest 2026</h1>
        <p>Driver Portal • Grand Transportation Coordination</p>
    </header>
    <div class="dates-grid">
        {date_cards}
    </div>
    <footer>
        <p>Generated {timestamp} • Internal Use Only</p>
    </footer>
</body>
</html>
"""


def slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text.strip("-")


def extract_first_driver(drivers_text: str) -> str:
    """Extract first driver name from 'Driver Name, Other Name' format."""
    if not drivers_text:
        return "unknown"
    # Split by comma and take first, strip whitespace
    first = drivers_text.split(",")[0].strip()
    return slugify(first)


def parse_shift_filename(filename: str) -> dict | None:
    """Parse 'Shift 4.08-MV1-S1.md' into components."""
    match = re.match(r"Shift (\d+)\.(\d+)-(MV\d+)-S(\d+)\.md", filename)
    if match:
        return {
            "month": match.group(1),
            "day": match.group(2),
            "vehicle_num": match.group(3),
            "shift_num": match.group(4),
            "date_slug": f"{match.group(1)}-{match.group(2)}",
        }
    return None


def parse_agenda_filename(filename: str) -> dict | None:
    """Parse 'Agenda 4.08.md' into components."""
    match = re.match(r"Agenda (\d+)\.(\d+)\.md", filename)
    if match:
        return {
            "month": match.group(1),
            "day": match.group(2),
            "date_slug": f"{match.group(1)}-{match.group(2)}",
        }
    return None


def md_to_html(md_content: str) -> str:
    """Convert markdown to HTML."""
    return markdown.markdown(md_content, extensions=["tables", "fenced_code", "toc"])


def build_breadcrumb(path_parts: list[str]) -> str:
    """Build breadcrumb navigation."""
    if not path_parts:
        return ""

    links = ['<a href="/index.html">Home</a>']
    current_path = ""

    for i, part in enumerate(path_parts[:-1]):
        current_path += f"/{part}"
        # Capitalize and format
        label = part.replace("-", " ").title()
        links.append(f'<a href="{current_path}/index.html">{label}</a>')

    # Last part is current page (no link)
    current_label = path_parts[-1].replace("-", " ").title()
    links.append(current_label)

    return f'<div class="breadcrumb">{" / ".join(links)}</div>'


def build_site():
    """Main build function."""
    print("Building DJF26 Driver Portal...")

    # Clean and recreate site directory
    if SITE_DIR.exists():
        import shutil

        shutil.rmtree(SITE_DIR)
    SITE_DIR.mkdir(parents=True)

    # Disable Jekyll on GitHub Pages
    (SITE_DIR / ".nojekyll").touch()

    # Track all dates and their content for landing page
    dates_data: dict[str, dict] = {}

    # Process agendas first
    print("  → Processing agendas...")
    agendas_dir = SITE_DIR / "agendas"
    agendas_dir.mkdir(parents=True)

    for md_file in sorted(AGENDAS_DIR.glob("*.md")):
        parsed = parse_agenda_filename(md_file.name)
        if not parsed:
            print(f"    ⚠ Skipping {md_file.name} (unrecognized format)")
            continue

        # Create directory
        date_dir = agendas_dir / parsed["date_slug"]
        date_dir.mkdir(parents=True)

        # Read and convert
        md_content = md_file.read_text()
        html_content = md_to_html(md_content)

        # Build page
        breadcrumb = build_breadcrumb(["agendas", parsed["date_slug"]])

        title = f"Agenda {parsed['month']}.{parsed['day']}"

        page = HTML_TEMPLATE.format(
            title=title,
            breadcrumb=breadcrumb,
            content=html_content,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
        )

        (date_dir / "index.html").write_text(page)

        # Track for landing page
        date_key = parsed["date_slug"]
        if date_key not in dates_data:
            dates_data[date_key] = {
                "shifts": [],
                "agenda": f"/agendas/{parsed['date_slug']}/index.html",
                "month": parsed["month"],
                "day": parsed["day"],
            }

    # Process driver sheets
    print("  → Processing driver sheets...")
    shifts_dir = SITE_DIR / "shifts"
    shifts_dir.mkdir(parents=True)

    for md_file in sorted(DRIVER_SHEETS_DIR.glob("*.md")):
        parsed = parse_shift_filename(md_file.name)
        if not parsed:
            print(f"    ⚠ Skipping {md_file.name} (unrecognized format)")
            continue

        # Read markdown content
        md_content = md_file.read_text()

        # Extract driver name from the markdown content (first H1 title)
        driver = "unknown"
        # Look for # Driver Name - Date pattern
        driver_match = re.search(r"^#\s+(.+?)\s+-\s+\d+/\d+", md_content, re.MULTILINE)
        if driver_match:
            driver = extract_first_driver(driver_match.group(1))

        # Build URL structure: /shifts/{date}/{driver}/van-{num}-shift-{num}/
        van_slug = f"van-{parsed['vehicle_num'][2:]}"  # MV1 -> van-1
        shift_slug = f"shift-{parsed['shift_num']}"

        shift_dir = (
            shifts_dir / parsed["date_slug"] / driver / f"{van_slug}-{shift_slug}"
        )
        shift_dir.mkdir(parents=True)

        # Convert to HTML
        html_content = md_to_html(md_content)

        # Build page
        breadcrumb = build_breadcrumb(
            ["shifts", parsed["date_slug"], driver, f"{van_slug}-{shift_slug}"]
        )

        title = f"Shift {parsed['month']}.{parsed['day']} - {driver} - {van_slug}-{shift_slug}"

        page = HTML_TEMPLATE.format(
            title=title,
            breadcrumb=breadcrumb,
            content=html_content,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
        )

        (shift_dir / "index.html").write_text(page)

        # Track for landing page
        date_key = parsed["date_slug"]
        if date_key not in dates_data:
            dates_data[date_key] = {
                "shifts": [],
                "agenda": None,
                "month": parsed["month"],
                "day": parsed["day"],
            }

        dates_data[date_key]["shifts"].append(
            {
                "driver": driver,
                "van": van_slug,
                "shift": shift_slug,
                "path": f"/shifts/{parsed['date_slug']}/{driver}/{van_slug}-{shift_slug}/index.html",
            }
        )

    # Build agenda index page (/agendas/)
    print("  → Building agenda index...")
    agenda_index_content = "<h1>All Agendas</h1><ul>"
    for date_slug in sorted(dates_data.keys()):
        data = dates_data[date_slug]
        date_display = f"{data['month']}/{data['day']}"
        agenda_path = data.get("agenda", f"/agendas/{date_slug}/index.html")
        agenda_index_content += f'<li><a href="{agenda_path}">{date_display}</a></li>'
    agenda_index_content += "</ul>"

    agenda_index_page = HTML_TEMPLATE.format(
        title="All Agendas",
        breadcrumb=build_breadcrumb(["agendas"]),
        content=agenda_index_content,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )
    (agendas_dir / "index.html").write_text(agenda_index_page)

    # Build shift index page (/shifts/) and date-level indexes
    print("  → Building shift indexes...")

    # /shifts/ - list all dates
    shift_index_content = "<h1>All Shifts by Date</h1>"
    for date_slug in sorted(dates_data.keys()):
        data = dates_data[date_slug]
        date_display = f"{data['month']}/{data['day']}"
        shift_index_content += (
            f'<h2><a href="/shifts/{date_slug}/index.html">{date_display}</a></h2>'
        )

    shift_index_page = HTML_TEMPLATE.format(
        title="All Shifts",
        breadcrumb=build_breadcrumb(["shifts"]),
        content=shift_index_content,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )
    (shifts_dir / "index.html").write_text(shift_index_page)

    # /shifts/{date}/ - list all drivers for each date
    for date_slug, data in dates_data.items():
        date_display = f"{data['month']}/{data['day']}"

        # Group shifts by driver
        by_driver: dict[str, list] = {}
        for shift in data["shifts"]:
            d = shift["driver"]
            if d not in by_driver:
                by_driver[d] = []
            by_driver[d].append(shift)

        date_index_content = f"<h1>Shifts for {date_display}</h1>"
        for driver in sorted(by_driver.keys()):
            driver_display = driver.replace("-", " ").title()
            date_index_content += f"<h2>{driver_display}</h2><ul>"
            for shift in by_driver[driver]:
                label = f"{shift['van']} - {shift['shift']}"
                date_index_content += f'<li><a href="{shift["path"]}">{label}</a></li>'
            date_index_content += "</ul>"

        date_index_page = HTML_TEMPLATE.format(
            title=f"Shifts for {date_display}",
            breadcrumb=build_breadcrumb(["shifts", date_slug]),
            content=date_index_content,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
        )
        (shifts_dir / date_slug / "index.html").write_text(date_index_page)

    # Build landing page
    print("  → Building landing page...")

    date_cards = []
    for date_slug in sorted(dates_data.keys()):
        data = dates_data[date_slug]
        date_display = f"{data['month']}/{data['day']}"

        # Group shifts by driver
        by_driver: dict[str, list] = {}
        for shift in data["shifts"]:
            d = shift["driver"]
            if d not in by_driver:
                by_driver[d] = []
            by_driver[d].append(shift)

        shifts_html = ""
        for driver in sorted(by_driver.keys()):
            shifts = by_driver[driver]
            driver_display = driver.replace("-", " ").title()
            shifts_html += f"<h3>{driver_display}</h3>"
            for shift in shifts:
                label = f"{shift['van']} - {shift['shift']}"
                shifts_html += f'<a href="{shift["path"]}">{label}</a>'

        agenda_link = ""
        if data["agenda"]:
            agenda_link = (
                f'<a href="{data["agenda"]}" class="agenda-link">View Full Agenda</a>'
            )

        card = f"""
        <div class="date-card">
            <h2>{date_display}</h2>
            {agenda_link}
            {shifts_html}
        </div>
        """
        date_cards.append(card)

    landing = LANDING_TEMPLATE.format(
        date_cards="\n".join(date_cards),
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )

    (SITE_DIR / "index.html").write_text(landing)

    print(f"\n✓ Built site with {len(dates_data)} dates")
    print(f"  Output: {SITE_DIR}/")
    print(f"  To preview: python -m http.server -d site/")


if __name__ == "__main__":
    build_site()
