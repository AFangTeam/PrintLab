#!/bin/bash
set -euo pipefail
PRINTLAB_REPO=$(cd "$(dirname "$0")/.." && pwd)
cd "$PRINTLAB_REPO"
if [[ "$(uname -s)" != "Darwin" ]]; then
  echo '首版安装入口面向 macOS。' >&2
  exit 1
fi
PRINTLAB_PYTHON=${PRINTLAB_PYTHON:-python3}
"$PRINTLAB_PYTHON" -c 'import sys; assert sys.version_info >= (3, 11), "需要 Python 3.11 或更新版本"'
command -v npm >/dev/null || { echo '请先安装 Node.js 22 LTS（含 npm）。' >&2; exit 1; }
node -e 'if (Number(process.versions.node.split(".")[0]) < 22) { throw new Error("需要 Node.js 22 或更新版本") }'
if [[ ! -x Runtime/venv/bin/python ]]; then
  "$PRINTLAB_PYTHON" -m venv Runtime/venv
fi
Runtime/venv/bin/python -m pip install -e './Harness[test]'
(cd Harness/studio && npm ci && npm run build)
Runtime/venv/bin/python scripts/init_workspace.py
printf '\n安装完成。运行 bash scripts/start.sh，在浏览器打开 http://127.0.0.1:8018 。\n'
