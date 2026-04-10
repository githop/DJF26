import csv
import sqlite3
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_FILE = REPO_ROOT / "db" / "master_schedule.db"

INGESTION_CONFIG = [
    {
        "csv_path": REPO_ROOT / "DJF26_ Master Schedule - locations.csv",
        "table_name": "locations",
        "skip_rows": 0,
        "primary_key": "Location Name",
    },
    {
        "csv_path": REPO_ROOT / "DJF26_ Master Schedule - Master.csv",
        "table_name": "schedule",
        "skip_rows": 4,
        "primary_key": None,
    },
    {
        "csv_path": REPO_ROOT / "DJF26_ Master Schedule - Rental Car Details.csv",
        "table_name": "rentals",
        "skip_rows": 0,
        "primary_key": "Vehicle",
    },
    {
        "csv_path": REPO_ROOT
        / "DJF26 - Project Documentation - Contact List (2026).csv",
        "table_name": "contacts",
        "skip_rows": 4,
        "primary_key": None,
    },
]


def migrate():
    # Connect to SQLite
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    for config in INGESTION_CONFIG:
        csv_file = config["csv_path"]
        table_name = config["table_name"]
        skip_rows = config["skip_rows"]

        if not csv_file.exists():
            print(f"Warning: {csv_file} does not exist. Skipping.")
            continue

        with open(csv_file, "r", encoding="utf-8") as f:
            for _ in range(skip_rows):
                next(f)

            reader = csv.DictReader(f)
            headers = [
                h for h in reader.fieldnames if h
            ]  # Filter out empty header columns

            # Create table
            columns_def = []
            for h in headers:
                col_def = f'"{h}" TEXT'
                if config.get("primary_key") == h:
                    col_def += " PRIMARY KEY"
                columns_def.append(col_def)

            columns = ", ".join(columns_def)
            cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
            cursor.execute(f"CREATE TABLE {table_name} ({columns})")

            # Insert data
            placeholders = ", ".join(["?" for _ in headers])
            query = f"INSERT INTO {table_name} VALUES ({placeholders})"

            inserted = 0
            for row in reader:
                # Only insert if the row isn't empty
                if any(row.get(h) for h in headers):
                    cursor.execute(query, [row.get(h) for h in headers])
                    inserted += 1
            print(
                f"Migrated {inserted} rows from {csv_file.name} to table '{table_name}'"
            )

    conn.commit()
    conn.close()


if __name__ == "__main__":
    migrate()
