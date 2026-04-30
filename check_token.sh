#!/bin/bash
# Scans the most recent main.py run in cron.log for OAuth refresh failures.
# If detected, pings ntfy so the user knows to re-auth.
set -euo pipefail

LOG=/home/s206r/projects/rykailabs/apple_purchases/data/cron.log
TOPIC=$(grep '^NTFY_TOPIC=' /home/s206r/projects/rykailabs/apple_purchases/.env | cut -d= -f2)

# Pull the tail of the most recent run: everything after the last "Syncing" line.
LAST_RUN=$(awk '/Syncing Apple receipt emails/{buf=""} {buf=buf"\n"$0} END{print buf}' "$LOG")

if echo "$LAST_RUN" | grep -qE 'invalid_grant|RefreshError'; then
  curl -s -H "Priority: high" -H "Title: Apple token revoked" \
    -d "Gmail OAuth refresh failed in last cron run. Run: cd ~/projects/rykailabs/apple_purchases && .venv/bin/python auth.py (or use portal venv). Likely cause: OAuth client still in Testing mode in Google Cloud Console (7-day refresh token expiry)." \
    "https://ntfy.sh/$TOPIC" > /dev/null
fi
