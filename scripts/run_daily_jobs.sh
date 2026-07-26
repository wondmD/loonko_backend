#!/usr/bin/env bash
# Daily farm maintenance: refresh due alerts + husbandry tasks.
# Install with cron, e.g. daily at 06:00:
#   0 6 * * * /home/wondm/Documents/DFT/dft_backend/scripts/run_daily_jobs.sh >> /tmp/dft-daily.log 2>&1
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# Prefer project venv if present
if [[ -x "$ROOT/../myenv/bin/python" ]]; then
  PYTHON="$ROOT/../myenv/bin/python"
elif [[ -x "$ROOT/../.venv/bin/python" ]]; then
  PYTHON="$ROOT/../.venv/bin/python"
else
  PYTHON="${PYTHON:-python3}"
fi
cd "$ROOT"
"$PYTHON" manage.py generate_alerts
"$PYTHON" manage.py sync_husbandry
echo "DFT daily jobs finished at $(date -Is)"
