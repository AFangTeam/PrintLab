#!/bin/bash
set -euo pipefail
PRINTLAB_REPO=$(cd "$(dirname "$0")/.." && pwd)
cd "$PRINTLAB_REPO"
export PRINTLAB_ROOT="$PRINTLAB_REPO"
export PYTHONPATH="$PRINTLAB_REPO/Harness${PYTHONPATH:+:$PYTHONPATH}"
if [[ ! -x Runtime/venv/bin/python || ! -f Harness/studio/dist/index.html ]]; then
  echo '请先运行 bash scripts/setup.sh' >&2
  exit 1
fi
exec Runtime/venv/bin/python Harness/serve.py studio "$@"
