"""Shared import paths for backend contract tests.

The production modules intentionally use flat imports (``from models import``),
so tests mirror the process layout used by uvicorn and the Discord bot.
"""

from pathlib import Path
import hashlib
import sys

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = BACKEND_ROOT / "api"
TESTS_ROOT = Path(__file__).resolve().parent

for path in (str(API_ROOT), str(BACKEND_ROOT), str(TESTS_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)


# ── The tree this run is reading ─────────────────────────────────────────
#
# Several gates in this suite read SOURCE, and `inspect.getsource` resolves
# the line numbers recorded when a module was IMPORTED against the file as it
# is WHEN THE ASSERTION RUNS. Edit a module while its own suite is in flight
# -- another session working in the same worktree is enough -- and those gates
# compare real text against text from a different part of the file. The
# failures that come back are confident and specific, and they quote symbols
# the test never mentions (#676).
#
# What makes the class expensive is that it survives both disproofs anyone
# reaches for. Re-running the same ordering passes, which reads as "flaky".
# Re-running a DIFFERENT ordering also passes, which reads as "order-dependent,
# now fixed". Neither is true and both are reassuring. Freezing the tree is the
# only thing that discriminates, and nobody freezes a tree without already
# suspecting this -- so the run says it rather than waiting to be asked.
#
# This reports; it does not fail. A suite must not go red because someone
# saved a file, and a run whose numbers are worth quoting is a standing-start
# run on a tree nobody is touching.

_SOURCE_ROOTS = (API_ROOT, BACKEND_ROOT, TESTS_ROOT)
_TREE_STAMPS = pytest.StashKey[object]()


def _source_stamps() -> dict[str, tuple[int, str]]:
    """(size, content digest) for every module a source-reading gate can reach.

    CONTENT, not mtime: the edit this exists to catch is a comment splice, and
    a splice can preserve the byte count and land inside one timestamp tick.
    Roughly 20 MB to read, twice per run."""
    stamps: dict[str, tuple[int, str]] = {}
    for root in _SOURCE_ROOTS:
        try:
            paths = sorted(root.glob("*.py"))
        except OSError:
            continue
        for path in paths:
            try:
                data = path.read_bytes()
            except OSError:            # deleted or locked mid-walk
                continue
            stamps[str(path)] = (len(data), hashlib.blake2b(data, digest_size=16).hexdigest())
    return stamps


def pytest_configure(config):
    # Nothing here may fail a run. pytest turns an exception raised in
    # configure into an internal error that reports no tests at all, and a
    # diagnostic that can do that is worse than no diagnostic. The failure is
    # kept rather than swallowed, so the summary can say the check is not
    # armed -- a guard that is silently dead reads exactly like one that passed.
    try:
        config.stash[_TREE_STAMPS] = _source_stamps()
    except Exception as exc:           # noqa: BLE001 - reported, never raised
        config.stash[_TREE_STAMPS] = exc


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    # Not dispatched under `--no-summary`, with the terminal plugin disabled,
    # or on an internal error. Such a run goes without the check rather than
    # getting a wrong answer from it.
    try:
        before = config.stash.get(_TREE_STAMPS, None)
        if isinstance(before, Exception):
            terminalreporter.write_line(
                f"(tree-movement check was not armed: {before!r})")
            return
        if not before:
            return
        after = _source_stamps()
        moved = sorted(name for name in set(before) | set(after)
                       if before.get(name) != after.get(name))
        if not moved:
            return
        terminalreporter.write_sep("=", "TREE MOVED DURING THIS RUN", red=True)
        terminalreporter.write_line(
            "These files changed on disk while the suite was running. Any assertion "
            "that reads source may have been compared against the wrong lines, and "
            "a green result certifies nothing about the tree as it now stands. "
            "Re-run from a standing start before quoting these numbers:"
        )
        for name in moved:
            terminalreporter.write_line(f"  {name}")
    except Exception as exc:           # noqa: BLE001 - reported, never raised
        try:
            terminalreporter.write_line(f"(tree-movement check did not run: {exc!r})")
        except Exception:
            pass


@pytest.fixture(autouse=True)
def _pc_card_themes_loaded():
    """Production loads the card -> ink map once at startup and every face
    route refuses while it is empty, because that colour is part of
    `face_rev`. A test process never runs that startup, so it stands in here
    -- from the migration's own rows, not from a literal.

    Only when `main` is already imported: this is autouse, and importing a
    3 MB module for tests that do not touch it would cost every run."""
    main = sys.modules.get("main")
    if main is None or not hasattr(main, "_PC_CARD_THEMES"):
        yield
        return
    from pc_themes_data import rgb_map
    before = dict(main._PC_CARD_THEMES)
    main._PC_CARD_THEMES.clear()
    main._PC_CARD_THEMES.update(rgb_map())
    try:
        yield
    finally:
        main._PC_CARD_THEMES.clear()
        main._PC_CARD_THEMES.update(before)

