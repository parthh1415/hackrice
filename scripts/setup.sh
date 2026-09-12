#!/usr/bin/env bash
# Everything a fresh clone needs before `python3 -m firebreak.server` works.
# Safe to re-run. Needs network only for the two installs.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> python deps"
# no --upgrade: if numpy is already there, leave whatever version alone
python3 -m pip install --quiet numpy pytest

echo "==> ui test deps (optional — skipped if node is missing)"
if command -v npm >/dev/null 2>&1; then
  npm --prefix tests/ui ci --silent
else
  echo "    no npm on PATH; tests/ui/*.js will not run. Everything else will."
fi

echo "==> python tests"
python3 -m pytest tests/ -q

cat <<'EOF'

ready.

  PYTHONPATH=src python3 -m firebreak.server                   -> localhost:8765
  FIREBREAK_DEMO=1 PYTHONPATH=src python3 -m firebreak.server  -> same, off disk
EOF
