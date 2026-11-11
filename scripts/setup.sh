#!/bin/bash
set -euo pipefail
PRINTLAB_REPO=$(cd "$(dirname "$0")/.." && pwd)
export PYTHONUTF8=1
exec "${PRINTLAB_PYTHON:-python3}" -X utf8 "$PRINTLAB_REPO/scripts/setup.py"
