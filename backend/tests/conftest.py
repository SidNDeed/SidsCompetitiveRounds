"""Shared import paths for backend contract tests.

The production modules intentionally use flat imports (``from models import``),
so tests mirror the process layout used by uvicorn and the Discord bot.
"""

from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = BACKEND_ROOT / "api"

for path in (str(API_ROOT), str(BACKEND_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

