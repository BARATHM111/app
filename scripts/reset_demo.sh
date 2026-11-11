#!/usr/bin/env bash
# Reset the BarterX demo to its clean pre-trade state (idempotent, touches demo data only).
set -euo pipefail
cd "$(dirname "$0")/../backend"
python seed.py
