"""Shared import paths for backend contract tests.

The production modules intentionally use flat imports (``from models import``),
so tests mirror the process layout used by uvicorn and the Discord bot.
"""

from pathlib import Path
import sys

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = BACKEND_ROOT / "api"

for path in (str(API_ROOT), str(BACKEND_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)


# Record which test files pytest actually COLLECTED, before any -k/-m
# deselection runs. test_collection_manifest.py compares this against the
# files on disk to catch a test file that exists but contributes nothing.
# Reading session.items instead would see the post-deselection list, so a
# `-k something` run would report every other file as uncollected.
COLLECTED_FILES_KEY = "scr_collected_test_files"


# tryfirst via the DECORATOR, not a `.tryfirst = True` attribute: the attribute
# form raises PytestRemovedIn10Warning and stops working in pytest 10, at which
# point this hook would quietly run AFTER -k deselection and the manifest guard
# would silently start comparing against a filtered list.
@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(session, config, items):  # noqa: D401
    """Stash the full collected file set, before -k/-m deselection runs."""
    names = set()
    for item in items:
        try:
            names.add(Path(str(item.fspath)).name)
        except Exception:  # pragma: no cover - pytest version differences
            continue
    setattr(config, COLLECTED_FILES_KEY, names)

