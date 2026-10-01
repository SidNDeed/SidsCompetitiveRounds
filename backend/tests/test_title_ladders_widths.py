"""Five-tier title ladders (board row 29): titles up to 14 characters (the
server catalogue's cap on a tier name) must reach the surfaces that show a
player's title without being cut.

* The FFA surfaces cut a title to a fixed character count: the FFA
  leaderboard row was 12 and the FFA recent-match row 14; both are 16.
* The F5 1v1 leaderboard measures the name and the title together in the
  name cell's width (LB_COL_W[2], 300 px) and elides only the title.

Every gate carries an in-memory mutation it must catch (#391).
"""
import io
import os
import re

from _cs_structure import code_of

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
TIER_NAME_CAP = 14   # the server's tier-name cap (title_ladders.catalogue_problems)
FFA_CAP = 16


def _nat():
    with io.open(os.path.join(REPO, "plugin", "NativeUI.cs"), encoding="utf-8") as fh:
        return fh.read()


FFA_SITES = {
    "the FFA recent-match row": r"\[\{FfaSafeRich\(Trunc\(player\.title,(\d+)\)\)\}\]",
    "the FFA leaderboard row": r"\[\{Trunc\(e\.title,(\d+)\)\}\]",
}


def _cap_problems(src):
    code = code_of(src)
    bad = []
    for site, pat in sorted(FFA_SITES.items()):
        caps = [int(c) for c in re.findall(pat, code)]
        if len(caps) != 1:
            bad.append((site, "found %d sites" % len(caps)))
        elif caps[0] < FFA_CAP:
            bad.append((site, caps[0]))
    return bad


def test_the_ffa_title_caps_hold_the_longest_tier_name():
    assert FFA_CAP >= TIER_NAME_CAP
    assert not _cap_problems(_nat())


def test_the_ffa_cap_gate_can_fail():
    src = _nat()
    for old, new in (("[{Trunc(e.title,16)}]", "[{Trunc(e.title,12)}]"),
                     ("[{FfaSafeRich(Trunc(player.title,16))}]", "[{FfaSafeRich(Trunc(player.title,14))}]"),
                     ("[{Trunc(e.title,16)}]", "[{e.title}]")):
        assert src.count(old) == 1, old
        assert _cap_problems(src.replace(old, new, 1)), new
