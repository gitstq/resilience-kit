#!/usr/bin/env bash
# One-click packaging script for resilience-kit.
set -euo pipefail
cd "$(dirname "$0")"

python3 -m pip install --quiet --upgrade build
python3 -m build

echo "Artifacts written to dist/:"
ls -lh dist/
