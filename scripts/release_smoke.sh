#!/usr/bin/env bash
# Release smoke test: README developer path (non-destructive verify + version check).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== capinstall verify =="
./capinstall verify --json

echo "== capiforge version =="
capiforge --version | grep -E '^capiforge 0\.3\.0$'

echo "== bootstrap status =="
capiforge status | grep -q '"bootstrap_state": "adopted"'

echo "== unittest (quick gate) =="
python3 -m unittest discover -s tests/storage -p '*test*.py'
python3 -m unittest discover -s tests/install -p '*test*.py'

echo "OK: release smoke passed"
