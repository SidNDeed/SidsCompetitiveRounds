"""The server's other readers of the SteamID64 rule (v4.13): the display-name
cleanup and the bug-log scrubber used the 7656119 prefix, which admits ids below
the public individual interval and misses every account numbered 2,039,734,272
or higher. Both now call steamid64.is_individual_id; the client's copy of the
name rule (GameStateWatcher.IsPlaceholderName) is not part of this change."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "api")))

import main  # noqa: E402

LO, HI, HIGH = "76561197960265728", "76561202255233023", "76561200000000000"   # both boundaries, past the prefix
BELOW, ABOVE, PREFIX_BELOW = "76561197960265727", "76561202255233024", "76561190000000001"
OWN = "76561198040410653"
ARABIC_TAIL = "7656119" + "\u0668\u0660\u0664\u0660\u0664\u0661\u0660\u0666\u0665\u0663"   # str.isdigit() is True


def test_a_display_name_that_is_a_steam_id_is_no_name():
    """_clean_display_name answers None for a name that is itself a public individual SteamID64, whoever's it
    is, after the strip; every seventeen-digit name outside the interval is a name like any other."""
    for sid in (LO, HI, HIGH, "76561198720512419", " " + HIGH + "\n"):
        assert main._clean_display_name(sid, OWN) is None, ascii(sid)
    for name in (BELOW, ABOVE, PREFIX_BELOW, ARABIC_TAIL, "12345678901234567", "7656119804041065"):
        assert main._clean_display_name(name, OWN) == name, ascii(name)
    assert main._clean_display_name(OWN, OWN) is None and main._clean_display_name("  ", OWN) is None


def test_the_bug_log_scrubber_collects_and_redacts_exactly_the_steam_ids(monkeypatch):
    """Stage one collects each distinct id in first-seen order, and only ids: a seventeen-digit run outside the
    interval is not sent to the deletion probe and does not use up its cap. Stage two redacts the ids the probe
    returned, wherever they stand alone, and nothing else."""
    body = (f"boot {BELOW} lo={LO} {'1' * 17} x{HIGH} {HIGH}\n{ABOVE} {PREFIX_BELOW} {HI} {ARABIC_TAIL} "
            f"1{LO} {LO}")
    out, counts, ids = main._scrub_pass_one(body)
    assert ids == [LO, HIGH, HI] and out == body and counts["deleted_steam_id"] == 0
    monkeypatch.setattr(main, "_BUG_LOG_STEAMID_PROBE_MAX", 2)
    assert main._scrub_pass_one(body)[2] == [LO, HIGH]
    redacted = main._scrub_pass_two(out, {LO, HIGH}, counts)
    assert redacted == (f"boot {BELOW} lo=[DELETED-USER] {'1' * 17} x{HIGH} [DELETED-USER]\n{ABOVE} {PREFIX_BELOW} "
                        f"{HI} {ARABIC_TAIL} 1{LO} [DELETED-USER]")
    assert counts["deleted_steam_id"] == 3
