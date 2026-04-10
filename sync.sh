#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║         DJF26 Sync & Generate Pipeline             ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════╝${NC}"
echo

# Step 1: Check for new CSVs in Downloads
echo -e "${YELLOW}📥 Step 1: Checking for new CSVs in Downloads...${NC}"

CSV_UPDATED=false
CSV_FILES=(
    "DJF26_ Master Schedule - Master.csv"
    "DJF26_ Master Schedule - locations.csv"
    "DJF26_ Master Schedule - Rental Car Details.csv"
    "DJF26 - Project Documentation - Contact List (2026).csv"
)

for file in "${CSV_FILES[@]}"; do
    downloads_path="$HOME/Downloads/$file"
    repo_path="$SCRIPT_DIR/$file"
    
    if [ -f "$downloads_path" ]; then
        # Check if file is different from current
        if [ ! -f "$repo_path" ] || ! diff -q "$downloads_path" "$repo_path" > /dev/null 2>&1; then
            echo -e "  ${GREEN}✓${NC} New/updated: $file"
            mv "$downloads_path" "$repo_path"
            CSV_UPDATED=true
        else
            echo -e "  ${YELLOW}→${NC} No changes: $file (removing from Downloads)"
            rm "$downloads_path"
        fi
    fi
done

if [ "$CSV_UPDATED" = false ]; then
    echo -e "  ${YELLOW}→ No new CSVs found in Downloads${NC}"
fi

echo

# Step 2: Run database migration
echo -e "${YELLOW}🗄️  Step 2: Migrating CSVs to SQLite...${NC}"
uv run db/migrate_csv.py
echo

# Step 3: Generate assets for active dates
echo -e "${YELLOW}📄 Step 3: Generating driver sheets and agendas...${NC}"

# Get unique dates from schedule that have GT tasks
DATES=$(sqlite3 db/master_schedule.db "
SELECT DISTINCT Date FROM schedule 
WHERE Activity IN ('GT (People)', 'GT (Asset)', 'Staff: Driver', 'Driver Volunteer Shift')
AND Date IS NOT NULL
ORDER BY Date
" 2>/dev/null || true)

if [ -z "$DATES" ]; then
    echo -e "  ${YELLOW}→ No active dates found with GT tasks${NC}"
else
    GENERATED_COUNT=0
    while IFS= read -r date; do
        if [ -n "$date" ]; then
            # Extract date portion (e.g., "4/8" from "4/8 (Wednesday)")
            date_short=$(echo "$date" | sed -E 's/^([0-9]+\/[0-9]+).*/\1/')
            
            echo -e "  ${BLUE}→${NC} Processing $date..."
            
            # Generate driver sheets
            uv run db/generate_sheets.py "$date_short" 2>/dev/null || true
            
            # Generate agenda  
            uv run db/generate_agenda.py "$date_short" 2>/dev/null || true
            
            GENERATED_COUNT=$((GENERATED_COUNT + 1))
        fi
    done <<< "$DATES"
    
    echo -e "  ${GREEN}✓ Generated assets for $GENERATED_COUNT dates${NC}"
fi

echo

# Step 4: Build HTML site
echo -e "${YELLOW}🔨 Step 4: Building HTML site...${NC}"
uv run db/build_site.py
echo

# Step 5: Check git status and commit
echo -e "${YELLOW}📦 Step 5: Git staging and commit...${NC}"

# Check if there are changes to commit
if git diff --quiet HEAD && git diff --cached --quiet HEAD; then
    echo -e "  ${YELLOW}→ No changes to commit${NC}"
else
    # Stage all changes
    git add -A
    
    # Generate commit message with timestamp and summary
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M')
    
    # Count changes
    CSV_CHANGES=$(git diff --cached --name-only | grep -c '\.csv$' 2>/dev/null || echo 0)
    MD_CHANGES=$(git diff --cached --name-only | grep -c '\.md$' 2>/dev/null || echo 0)
    DB_CHANGES=$(git diff --cached --name-only | grep -c '\.db$' 2>/dev/null || echo 0)
    HTML_CHANGES=$(git diff --cached --name-only | grep 'docs/' 2>/dev/null | wc -l | tr -d ' ')
    
    COMMIT_MSG="Sync: $TIMESTAMP"
    
    if [ "$CSV_CHANGES" -gt 0 ]; then
        COMMIT_MSG="$COMMIT_MSG | CSVs: $CSV_CHANGES"
    fi
    if [ "$MD_CHANGES" -gt 0 ]; then
        COMMIT_MSG="$COMMIT_MSG | Sheets: $MD_CHANGES"
    fi
    if [ "$HTML_CHANGES" -gt 0 ]; then
        COMMIT_MSG="$COMMIT_MSG | HTML: $HTML_CHANGES"
    fi
    if [ "$DB_CHANGES" -gt 0 ]; then
        COMMIT_MSG="$COMMIT_MSG | DB"
    fi
    
    git commit -m "$COMMIT_MSG"
    echo -e "  ${GREEN}✓ Committed: $COMMIT_MSG${NC}"
fi

echo

# Step 6: Push to remote
echo -e "${YELLOW}🚀 Step 6: Pushing to remote...${NC}"

if git rev-parse --abbrev-ref @{upstream} > /dev/null 2>&1; then
    git push
    echo -e "  ${GREEN}✓ Pushed to $(git rev-parse --abbrev-ref @{upstream})${NC}"
else
    echo -e "  ${YELLOW}→ No upstream branch configured, skipping push${NC}"
fi

echo

echo -e "${GREEN}╔════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              ✓ Sync Complete!                      ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════╝${NC}"
