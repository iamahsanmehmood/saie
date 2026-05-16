"""Test config: ensure src/ is importable as a package root for tests."""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
