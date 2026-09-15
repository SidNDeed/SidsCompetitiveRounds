"""The server's other readers of the SteamID64 rule (v4.13): the display-name
cleanup and the bug-log scrubber used the 7656119 prefix, which admits ids below
the public individual interval and misses every account numbered 2,039,734,272
or higher. Both now call steamid64.is_individual_id; the client's copy of the
name rule (GameStateWatcher.IsPlaceholderName) is not part of this change."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "api")))

import main  # noqa: E402
from steamid64_pg_parity import VECTORS  # noqa: E402

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
    # ...and over every spelling steamid64_pg_parity holds the validator and PostgreSQL to, not a hand-picked
    # few. The name is stripped before the rule reads it, so a spelling that differs from a public individual
    # SteamID64 only in surrounding whitespace IS that id and is no name. A rule drifting to the form, a prefix
    # or the interval alone answers one of the 27 wrong.
    caller = "76561198720512419"   # not one of the vectors, so the "same as the caller's own id" branch never answers
    admitted = {text for text, ok in VECTORS if ok}
    for text, _ in VECTORS:
        stripped = text.strip()
        want = None if (not stripped or stripped in admitted) else stripped
        assert main._clean_display_name(text, caller) == want, ascii(text)


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


def test_the_scrubber_probes_and_redacts_exactly_the_ids_the_shared_rule_admits():
    """The same two stages over every spelling steamid64_pg_parity holds the validator and PostgreSQL to, not a
    hand-picked few. Only a seventeen-ASCII-digit run bounded by non-word characters or the text's ends is
    a candidate at all (_SCRUB_STEAMID_RE); of the candidates, stage one collects exactly the ids the rule
    admits, in
    first-seen order, and stage two redacts those and leaves every refused seventeen-digit spelling standing
    where it is.

    The bound: this node pins the PREFIX the rule keys on -- the 7656119 prefix rule flips four of the 27 and
    fails here. It cannot see a drift in the FORM: dropping the length check flips one vector,
    "076561198040410653", and eighteen digits carry no internal word boundary, so the candidate expression never
    offers it and the node stays green."""
    body = " ".join(text for text, _ in VECTORS)
    out, counts, ids = main._scrub_pass_one(body)
    assert ids == [text for text, ok in VECTORS if ok] and out == body
    assert counts["deleted_steam_id"] == 0
    redacted = main._scrub_pass_two(out, set(ids), counts)
    for text, ok in VECTORS:
        if not ok and len(text) == 17 and text.isascii() and text.isdigit():
            assert text in redacted, ascii(text)
    assert redacted.count("[DELETED-USER]") == counts["deleted_steam_id"] >= len(ids)
