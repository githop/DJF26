#!/usr/bin/env python3
"""
Generate both driver sheets and daily agenda for a given date.
"""

import subprocess
import sys


def main():
    if len(sys.argv) < 2:
        print("Usage: uv run db/generate_all.py <date>")
        print("  Example: uv run db/generate_all.py '4/8'")
        print("  Example: uv run db/generate_all.py '4/8 (Wednesday)'")
        sys.exit(1)

    date = sys.argv[1]

    print(f"\n{'=' * 60}")
    print(f"Generating all documents for: {date}")
    print(f"{'=' * 60}\n")

    # Generate driver sheets
    print("→ Generating driver sheets...")
    result1 = subprocess.run(
        ["uv", "run", "db/generate_sheets.py", date], capture_output=False
    )

    print()

    # Generate agenda
    print("→ Generating daily agenda...")
    result2 = subprocess.run(
        ["uv", "run", "db/generate_agenda.py", date], capture_output=False
    )

    print(f"\n{'=' * 60}")
    if result1.returncode == 0 and result2.returncode == 0:
        print("✓ All documents generated successfully!")
    else:
        print("✗ Some errors occurred during generation.")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
