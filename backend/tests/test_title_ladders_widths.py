"""Five-tier title ladders (board row 29): titles up to 14 characters (the
server catalogue's cap on a tier name) must reach the surfaces that show a
player's title without being cut.

* The FFA surfaces cut a title to a fixed character count: the FFA
  leaderboard row was 12 and the FFA recent-match row 14; both are 16.
* The F5 1v1 leaderboard measures the name and the title together in the
  name cell's width (LB_COL_W[2], 300 px) and elides only the title; the
  FFA leaderboard does the same in its 220 px cell (FFA_LB_COL_W[1]).

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
    "the FFA leaderboard row":
        r"LbTitleSpan\(row\.txtName,nameDisplay,Trunc\(e\.title,(\d+)\),col,FFA_LB_COL_W\[1\],false\)",
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
    for old, new in (("Trunc(e.title,16),col,FFA_LB_COL_W[1]", "Trunc(e.title,12),col,FFA_LB_COL_W[1]"),
                     ("[{FfaSafeRich(Trunc(player.title,16))}]", "[{FfaSafeRich(Trunc(player.title,14))}]"),
                     ("LbTitleSpan(row.txtName,nameDisplay,Trunc(e.title,16),col,FFA_LB_COL_W[1],false)",
                      "$\" <color={col}>[{Trunc(e.title,16)}]</color>\"")):
        assert src.count(old) == 1, old
        assert _cap_problems(src.replace(old, new, 1)), new


# ── the F5 1v1 board: measured, and only the title elided ────────────────

LB = "private static void RefreshLeaderboard()"
SPAN = "private static string LbTitleSpan(object cell,string name,string title,string col,float width,bool bold=true)"
CALL = "_lbName=_lbName+LbTitleSpan(row.txtName,_lbName,e.title,_tc,LB_COL_W[2]);"


def _flat(t):
    return " ".join(t.split())


def _f5_problems(src):
    bad = []
    body = code_of(src, LB)
    if body.count(CALL) != 1:
        bad.append("the plain-title branch does not call LbTitleSpan once")
    if "[{e.title}]" in body:
        bad.append("a raw title is appended to the name cell")
    if "LB_COL_W={40,40,300," not in code_of(src).replace(" ", ""):
        bad.append("the name column is not the 300 px cell")
    span = _flat(code_of(src, SPAN))
    for need in ("float w=UIFactory.MeasureTextWidth(cell,name+full);",
                 "if(w<=0f||w<=limit)return full;",
                 "if(UIFactory.MeasureTextWidth(cell,name+cut)<=limit)return cut;",
                 "string cut=open+title.Substring(0,n).TrimEnd()+\"..\"+close;",
                 "n>=Math.Max(1,TITLE_MIN_VISIBLE-2);n--",
                 'return "";'):
        if need not in span:
            bad.append("LbTitleSpan lacks %r" % need)
    if "string full=open+title+close;" not in span:
        bad.append("the whole span is not the one the cuts are built from")
    if "name.Substring" in span or "Trunc(name" in span:
        bad.append("LbTitleSpan cuts the name")
    return bad


def test_the_f5_cell_measures_name_and_title_and_elides_only_the_title():
    assert not _f5_problems(_nat())


F5_MUTATIONS = [
    ("the raw append comes back", CALL,
     '_lbName=$"{_lbName} <b><color={_tc}>[{e.title}]</color></b>";'),
    ("the title measured alone", "float w=UIFactory.MeasureTextWidth(cell,name+full);",
     "float w=UIFactory.MeasureTextWidth(cell,full);"),
    ("an unmeasurable cell drops the title", "if(w<=0f||w<=limit)return full;",
     "if(w<=limit&&w>0f)return full;"),
    ("cuts are never measured", "if(UIFactory.MeasureTextWidth(cell,name+cut)<=limit)return cut;",
     "return cut;"),
    ("a one-letter stub is shown", "n>=Math.Max(1,TITLE_MIN_VISIBLE-2);n--", "n>=1;n--"),
]


def test_the_f5_gate_can_fail():
    src = _nat()
    for name, old, new in F5_MUTATIONS:
        assert src.count(old) == 1, (name, old)
        assert _f5_problems(src.replace(old, new, 1)), name
