"""The v1.41.0 notes say every stored card picture is redrawn once. Pin why.

A CHANGELOG line is a claim (#302), and this one rests on three facts in the
client, each checked here so the line cannot outlive them:

  * the portrait descriptor the client builds carries the render recipe
    (`"|r=" + RECIPE`), so a recipe bump changes every descriptor;
  * the client redraws when the stored descriptor differs from the one it
    wants (`me.portrait_descriptor == want` is the only "picture current"
    exit), and that comparison runs on a Player Cards visit;
  * RECIPE is 4 in this release -- a picture stored by any earlier build
    carries r=2 or r=3 and so cannot match.

Control: each assertion names a literal the claim depends on; remove the
recipe from the descriptor, or let the visit treat any stored picture as
current, and the notice becomes false and this test goes red.
"""
import re
from pathlib import Path

from changelog_release import one_bullet

REPO = Path(__file__).resolve().parents[2]
PORTRAIT = (REPO / "plugin" / "PortraitRender.cs").read_text(encoding="utf-8")
CHANGELOG = (REPO / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")


def test_the_recipe_is_part_of_every_descriptor():
    assert re.search(r'\+\s*"\|g="\s*\+\s*GameTag\(\)\s*\+\s*"\|r="\s*\+\s*RECIPE;', PORTRAIT)


def test_the_release_recipe_is_four():
    assert re.findall(r"internal const int RECIPE = (\d+);", PORTRAIT) == ["4"]


def test_a_stored_picture_is_current_only_when_its_descriptor_matches():
    assert PORTRAIT.count("me.portrait_descriptor == want") == 1
    assert 'LastResult = "picture current";' in PORTRAIT


def test_the_notes_say_so_under_v1410():
    # The v1.41.0 bullet itself, not everything above v1.40.3: once a newer
    # release sits above v1.41.0, its prose would satisfy a reader of that
    # whole head while v1.41.0's own bullet said something else (the class of
    # REHEARSAL-FOUR round 1, finding 4).
    bullet = one_bullet("1.41.0", "every stored card picture is out of date", CHANGELOG)
    assert "the first time you open Player Cards on this version" in bullet
