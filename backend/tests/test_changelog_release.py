"""changelog_release reads one release's own text, and its checks can fail.

The CHANGELOG readers in test_room_region_symmetry.py,
test_h2h_pairing_and_window_latch.py, test_report_disconnect_durability.py and
test_portrait_recipe_notice.py read a claim from the release that makes it,
through changelog_release. These controls run the helper on a constructed
CHANGELOG, so they prove the reader's behaviour without depending on what the
real file says today (REHEARSAL-FOUR round 1, finding 4 and its class).
"""

import pytest

from changelog_release import (
    ChangelogError, one_bullet, release_bullets, release_section)

DOC = "\n".join([
    "# Changelog",
    "",
    "## v2.0.0 - unreleased",
    "",
    "- The widget now spins clockwise, as it always should have.",
    "",
    "## v1.0.0 - 2026-01-01",
    "",
    "**Schema changes:** none.",
    "",
    "- The widget now spins counter-clockwise.",
    "  It used to stop.",
    "- Another bullet that mentions",
    "  the widget in passing.",
    "",
    "**A heading paragraph** that is not a bullet.",
    "  An indented line after a paragraph belongs to no bullet.",
    "",
    "## v1.0 - 2025-12-01",
    "",
    "- The widget now spins clockwise.",
    "",
])


def test_a_newer_release_repeating_the_sentence_does_not_hide_this_one():
    # a first-occurrence reader lands in v2.0.0, the newest release...
    first = DOC.index("The widget now spins")
    assert first < DOC.index("## v1.0.0 ")
    # ...the release reader reads v1.0.0's own bullet
    bullet = one_bullet("1.0.0", "The widget now spins", DOC)
    assert bullet == "The widget now spins counter-clockwise. It used to stop."
    assert "as it always should have" not in bullet


def test_a_bullet_runs_over_its_indented_lines_and_stops_at_the_next():
    assert release_bullets("1.0.0", DOC) == [
        "The widget now spins counter-clockwise. It used to stop.",
        "Another bullet that mentions the widget in passing.",
    ]


def test_a_continuation_paragraph_after_a_blank_line_stays_with_its_bullet():
    """Rehearsal-four round 2, finding 10: an indented paragraph after a blank
    line is the bullet's own (Markdown renders it inside the list item), so a
    claim placed there is read with the bullet; a line at column 0 after the
    blank line still ends it."""
    text = chr(10).join([
        "## v1.40.2 (2026-08-28)", "",
        "- The region a ranked room is created in is the one both seats",
        "  measured best.", "",
        "  It no longer goes to whichever region came first alphabetically.",
        "",
        "Unrelated paragraph at column 0.",
        "- Next bullet.", ""])
    bullet = one_bullet("1.40.2", "The region a ranked room is created in", text)
    assert "came first alphabetically" in bullet, bullet
    assert "Unrelated paragraph" not in bullet, bullet
    assert release_bullets("1.40.2", text)[1] == "Next bullet."


def test_two_bullets_matching_in_the_release_raise():
    with pytest.raises(ChangelogError):
        one_bullet("1.0.0", "widget", DOC)


def test_no_bullet_matching_in_the_release_raises():
    # the phrase exists, but only in a newer release
    assert "as it always should have" in DOC
    with pytest.raises(ChangelogError):
        one_bullet("1.0.0", "as it always should have", DOC)


def test_a_phrase_split_across_a_line_wrap_is_found():
    assert one_bullet("1.0.0", "counter-clockwise.  It used\nto stop", DOC).endswith(
        "It used to stop.")


def test_the_version_is_matched_whole():
    assert release_section("1.0", DOC).splitlines()[0] == "## v1.0 - 2025-12-01"
    assert release_bullets("1.0", DOC) == ["The widget now spins clockwise."]
    with pytest.raises(ChangelogError):
        release_section("1.0.1", DOC)


def test_two_headings_for_one_version_raise():
    with pytest.raises(ChangelogError):
        release_section("1.0.0", DOC + "## v1.0.0 - again\n")


def test_the_real_file_names_each_release_the_readers_use_once():
    for version in ("1.41.0", "1.40.2"):
        assert release_section(version).startswith("## v" + version + " ")
