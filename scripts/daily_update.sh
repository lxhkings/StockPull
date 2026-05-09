#!/usr/bin/env bash
# daily_update.sh — cron wrapper for the daily data pipeline
#
# Usage:
#   ./scripts/daily_update.sh              # all markets
#   ./scripts/daily_update.sh cn           # CN only
#   ./scripts/daily_update.sh us hk        # US + HK
#
# Logs to logs/daily_YYYY-MM-DD.log

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

DATE_TAG=$(date +%Y-%m-%d)
LOG_FILE="$LOG_DIR/daily_${DATE_TAG}.log"

# Activate venv
source "$PROJECT_DIR/.venv/bin/activate"

MARKETS="${@:-all}"

echo "==== daily_update $(date) markets=$MARKETS ====" >> "$LOG_FILE"

cd "$PROJECT_DIR"
python -m main daily $MARKETS >> "$LOG_FILE" 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo "==== FAILED (exit $EXIT_CODE) $(date) ====" >> "$LOG_FILE"
    exit $EXIT_CODE
fi

echo "==== done $(date) ====" >> "$LOG_FILE"
