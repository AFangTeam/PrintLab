"""Compatibility entry point. Prefer printlab history-recover; defaults to dry-run."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from printlab.cli import main

if __name__ == '__main__':
    sys.exit(main(['history-recover', *sys.argv[1:]]))
