# Denver Jazz Fest 2026 — Driver Portal

Internal driver coordination system for the 2026 Denver Jazz Festival.

## Live Site

🌐 **https://githop.github.io/DJF26/**

## Quick Start

```bash
# Download CSVs from the shared Google Sheet, then:
./sync.sh
```

This will:
1. Pull CSV exports from `~/Downloads/`
2. Migrate to SQLite database
3. Generate driver sheets and agendas
4. Build static HTML site with clean URLs
5. Stage, commit, and push to GitHub

## URL Structure

| Page | URL |
|------|-----|
| Daily Agenda | `/agendas/4-08/` |
| Driver Shift | `/shifts/4-08/{driver-name}/van-1-shift-1/` |

## Scripts

| Script | Purpose |
|--------|---------|
| `sync.sh` | Full pipeline: CSV → DB → Markdown → HTML → Commit → Push |
| `db/migrate_csv.py` | Import CSVs into SQLite |
| `db/generate_sheets.py` | Generate driver shift sheets |
| `db/generate_agenda.py` | Generate daily GTC agendas |
| `db/build_site.py` | Convert Markdown to HTML with clean URLs |

## Project Structure

```
.
├── db/
│   ├── master_schedule.db      # SQLite database (generated)
│   ├── migrate_csv.py          # CSV → DB importer
│   ├── generate_sheets.py      # Driver sheet generator
│   ├── generate_agenda.py      # Daily agenda generator
│   └── build_site.py           # HTML site builder
├── site/                       # Built HTML (served by GitHub Pages)
├── driver-sheets/              # Markdown intermediates (ignored)
├── daily-agendas/              # Markdown intermediates (ignored)
├── sync.sh                     # Main sync script
└── README.md                   # This file
```

## Git Workflow

Only the `site/` directory and Python scripts are tracked. CSVs and generated markdown are ignored because they can be rebuilt from source.

## Troubleshooting

**GitHub Pages 404?**
- Ensure `site/` directory exists at repo root
- Check Settings → Pages → Source is set to root

**Driver not showing in URL?**
- Driver name comes from first H1 in shift markdown
- Check CSV has driver assigned to shift
