"""Shared import paths for backend contract tests.

The production modules intentionally use flat imports (``from models import``),
so tests mirror the process layout used by uvicorn and the Discord bot.
"""

from pathlib import Path
import hashlib
import os
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

REPO_ROOT = BACKEND_ROOT.parent
SQL_ROOT = BACKEND_ROOT / "sql"
TOOLS_ROOT = REPO_ROOT / "tools"
ASSETS_ROOT = API_ROOT / "assets"
PLUGIN_ROOT = REPO_ROOT / "plugin"

# WHAT A SOURCE-READING GATE IN THIS SUITE CAN ACTUALLY REACH, which is a much
# larger set than `backend/**/*.py`. The gates in this repo read, between them:
# api and test modules (`inspect.getsource`, AST walks), the SQL migrations
# (every "the migration says X" assertion), `tools/*.py` and its JSON (the
# theme generator, the i18n source), the renderer's JSON assets and fonts
# (face layout, catalogue, the font lock), and `plugin/*.cs` (the client-side
# contract checks). An earlier version of this walk globbed `*.py`
# NON-recursively over three directories, so a change to any of the rest moved
# the tree under a running suite and this check reported nothing -- a guard
# that cannot fail over most of what it claims to watch (#342/#441).
#
# Directories are walked RECURSIVELY and filtered by suffix; `__pycache__` and
# `.git` are pruned because neither is an input any gate reads and both churn
# on their own during a run, which would make the report cry wolf.
#
# FONT BINARIES ARE DELIBERATELY OUT. The two font files alone are 29 MiB, no
# gate reads a font's BYTES, and the set of fonts that is meant to be present
# is pinned by `fonts.lock.json` -- which IS stamped, so a font swapped under
# a running suite still shows up as a moved lock file. Adding 29 MiB to two
# passes per session to watch something nothing reads is how a diagnostic
# becomes the reason people turn diagnostics off. Card PNGs stay: the face
# tests load them.
_SOURCE_TREES = (
    (API_ROOT, (".py", ".json")),
    (TESTS_ROOT, (".py", ".json")),
    (SQL_ROOT, (".sql",)),
    (TOOLS_ROOT, (".py", ".json")),
    (ASSETS_ROOT, (".json", ".png")),
    (PLUGIN_ROOT, (".cs",)),
)
# Files sitting directly in backend/ (discord_bot.py, Dockerfile.bot, the
# compose file) rather than in one of the trees above.
_SOURCE_FILES_IN = ((BACKEND_ROOT, (".py", ".yml", ".sql")),)
_PRUNED_DIRS = {"__pycache__", ".git", ".pytest_cache", "node_modules", "bin", "obj"}

_TREE_STAMPS = pytest.StashKey[object]()


def _source_stamps() -> dict[str, tuple[int, str]]:
    """(size, content digest) for every input a source-reading gate can reach.

    CONTENT, not mtime: the edit this exists to catch is a comment splice, and
    a splice can preserve the byte count and land inside one timestamp tick.

    The volume is deliberately NOT asserted in this comment. An earlier
    version put a number here ("roughly 20 MB per pass") that was about three
    times the truth, and the set has since widened, so any number written down
    is a claim that rots. `test_conftest_tree_walk.py` measures it instead and
    fails if a pass grows past a stated ceiling -- a number that is checked
    rather than one that is asserted in prose.
    """
    stamps: dict[str, tuple[int, str]] = {}

    def _stamp(path):
        try:
            data = path.read_bytes()
        except OSError:                # deleted or locked mid-walk
            return
        stamps[str(path)] = (len(data), hashlib.blake2b(data, digest_size=16).hexdigest())

    for root, suffixes in _SOURCE_FILES_IN:
        try:
            entries = sorted(root.iterdir())
        except OSError:
            continue
        for path in entries:
            if path.is_file() and path.suffix in suffixes:
                _stamp(path)

    for root, suffixes in _SOURCE_TREES:
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d not in _PRUNED_DIRS)
            base = Path(dirpath)
            for name in sorted(filenames):
                path = base / name
                if path.suffix in suffixes:
                    _stamp(path)
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

