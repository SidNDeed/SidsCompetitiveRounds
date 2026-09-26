"""The tree-movement check in conftest.py, checked.

conftest's `_source_stamps` exists so a suite that reads SOURCE can say when
the source moved under it. It reports; it never fails a run. That makes it the
exact shape of a guard that can rot silently: a narrowed walk produces the
same clean output as a tree nobody touched, and the output is "nothing to
report" either way.

So the walk's COVERAGE is asserted here instead, one named input class at a
time. The list is not decorative -- every entry is a file class that some gate
in this suite actually reads:

  * api modules              `inspect.getsource`, the AST walkers
  * test modules             the self-referential gates (janitor walker, the
                             hook-coverage scanner)
  * SQL migrations           every "the migration asserts X" test
  * tools/*.py and its JSON  the theme generator and the i18n source
  * renderer JSON assets     face layout, catalogue
  * plugin/*.cs              the client-contract checks
  * backend/discord_bot.py   sits directly in backend/, not in a subtree

An earlier version globbed `*.py` non-recursively over three directories, so
everything below the first two lines was unwatched while the check reported
clean.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import conftest as ct  # noqa: E402

REPO = Path(__file__).resolve().parents[2]

# (a file that must be stamped, why it is in the walk). Each is a real input,
# named by path rather than by pattern, so a suffix list that quietly drops
# one is a failure here rather than a silence.
REQUIRED = [
    (REPO / "backend" / "api" / "main.py", "the module every source gate reads"),
    (REPO / "backend" / "api" / "title_ladders.py", "an api module in the walk's root"),
    (REPO / "backend" / "tests" / "conftest.py", "the test tree reads its own source"),
    (REPO / "backend" / "sql" / "331_animal_title_ladders.sql",
     "migrations: every 'the migration says X' assertion reads one"),
    (REPO / "backend" / "sql" / "333_pc_card_themes.sql", "ditto"),
    (REPO / "tools" / "rounds_card_themes.py",
     "the theme generator, run and parsed by test_pc_card_themes"),
    (REPO / "tools" / "i18n_source.json", "JSON under tools/"),
    (REPO / "backend" / "api" / "assets" / "pc" / "face_layout_v1.json",
     "the renderer's layout, read by the face tests"),
    (REPO / "plugin" / "PlayerCardsUI.cs",
     "plugin sources, read by the client-contract checks"),
    (REPO / "backend" / "discord_bot.py",
     "a file directly in backend/, in no subtree"),
]


@pytest.fixture(scope="module")
def stamps():
    return ct._source_stamps()


@pytest.mark.parametrize("path,why", REQUIRED, ids=[p.name for p, _ in REQUIRED])
def test_the_walk_reaches(path, why, stamps):
    if not path.exists():
        pytest.skip("%s is not in this checkout" % path.name)
    assert str(path) in stamps, (
        "conftest's tree-movement walk does not stamp %s (%s). A change to it "
        "during a run would move the tree under every source-reading gate and "
        "this check would still report nothing." % (path, why))


def test_the_walk_is_recursive():
    """Nested modules, not just the top level of each root."""
    stamps = ct._source_stamps()
    nested = [p for p in stamps
              if (os.sep + "assets" + os.sep) in p or (os.sep + "pc" + os.sep) in p]
    assert nested, (
        "nothing below a first-level directory was stamped, so the walk is "
        "still non-recursive")


def test_the_walk_prunes_bytecode_and_git():
    """`__pycache__` churns on its own during a run. Stamping it would make
    the check report a moved tree on every second run -- a guard that cries
    wolf is turned off, which is the same outcome as one that is dead."""
    stamps = ct._source_stamps()
    noisy = [p for p in stamps if "__pycache__" in p or (os.sep + ".git" + os.sep) in p]
    assert not noisy, noisy


def test_a_changed_file_is_actually_detected(tmp_path, monkeypatch):
    """The negative control: the comparison must be able to say MOVED.

    Without this, every assertion above is about a dictionary's keys and none
    of them about the check doing its job.
    """
    root = tmp_path / "fake_api"
    (root / "nested").mkdir(parents=True)
    target = root / "nested" / "thing.py"
    target.write_text("x = 1\n", encoding="utf-8")

    monkeypatch.setattr(ct, "_SOURCE_TREES", ((root, (".py",)),))
    monkeypatch.setattr(ct, "_SOURCE_FILES_IN", ())

    before = ct._source_stamps()
    assert str(target) in before, before

    # Same LENGTH, different content: the splice this check exists to catch.
    target.write_text("x = 2\n", encoding="utf-8")
    after = ct._source_stamps()
    assert after[str(target)] != before[str(target)], (
        "a same-length content change was not detected -- the stamp is behaving "
        "like a size or an mtime rather than a digest")


def test_one_pass_stays_affordable():
    """The number the removed comment used to assert, measured instead.

    A ceiling rather than an equality: the walk is meant to grow with the
    repo. It is here so that adding a directory of binaries to one of the
    roots shows up as a failing test rather than as two slow passes per run
    that nobody attributes.
    """
    stamps = ct._source_stamps()
    total = sum(size for size, _digest in stamps.values())
    assert total < 40 * 1024 * 1024, (
        "one tree-movement pass now reads %.1f MiB across %d files, and it runs "
        "twice per session" % (total / 1048576.0, len(stamps)))


def test_font_binaries_are_out_of_the_walk():
    """The one deliberate exclusion, asserted so it stays deliberate.

    29 MiB of fonts that no gate reads, twice per run. What IS watched is the
    lock file that says which fonts are meant to be there.
    """
    stamps = ct._source_stamps()
    fonts = [p for p in stamps if p.endswith((".ttf", ".otf"))]
    assert not fonts, fonts
    lock = REPO / "backend" / "api" / "assets" / "fonts" / "fonts.lock.json"
    if lock.exists():
        assert str(lock) in stamps, (
            "fonts are excluded from the walk AND their lock file is not "
            "stamped, so a font change during a run is invisible either way")
