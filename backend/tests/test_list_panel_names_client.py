"""Report 3 (2026-09-30): every player name a list panel paints passes the one sanitiser.

The Recent Ranked Series panel's page 1 rendered blank: the page is ONE TMP text
element, and page 1 held a display name ending in U+13171, a supplementary-plane
character no font in the chain carries. The fix is a class: every player-name
string that reaches a TMP element in the list panels goes through
NativeUI.Nm (UnicodeFallback.SafeName over NameGlyphs.Safe) or through
FfaSafeRich, whose glyph pass is the same NameGlyphs code. The rules themselves
are EXECUTED by tools/client-rules-harness (suite nameglyphs, with U+13171, a
supplementary-plane emoji and the raw name as the negative control); these gates
are the structural half: the chain is wired, and no swept panel paints a name
field raw.

The sweep reads each panel method's text with comments removed and string
literals KEPT (an interpolation hole is inside a literal), per learnings
#342/#431/#441. Each gate has an in-memory mutation control that must turn it
red, and the pre-fix tree (69e23991) is run through the same findings() by the
fix sitting's revert control (logged, not pinned here).
"""
from __future__ import annotations

import functools
import re
from pathlib import Path

import pytest

from _cs_structure import mask_code, strip_comments_only

PLUGIN = Path(__file__).resolve().parents[2] / "plugin"
NATIVE = "NativeUI.cs"
FALLBACK = "UnicodeFallback.cs"
GLYPHS = "NameGlyphs.cs"

# (panel, method signature) -- the sweep table of the fix sitting's notes.
PANELS = [
    ("recent series, 1v1 rows and bets", "private static void RefreshRecentSeries()"),
    ("recent series, 2v2/1v2/FFA rows and bets",
     "private static string BuildMultimodeSeriesLine(ApiClient.MultimodeSeriesEntry m,string myName)"),
    ("recent series, 1v2 panel", "private static string BuildOvtRecentRowText("),
    ("leaderboard rows and the selected player", "private static void RefreshLeaderboard()"),
    ("FFA leaderboard rows", "private static void RefreshFfaTab()"),
    ("1v2 role boards", "private static void FillOvtRoleBoard("),
    ("achievement leaderboards", "private static void RefreshAchievements()"),
    ("live games, 1v1 header", "private static void ApplyHeaderRow(GameObject row, ApiClient.ActiveSeriesEntry s)"),
    ("live games, 1v1 bet row", "private static void ApplyBetRow(GameObject row, ApiClient.ActiveSeriesEntry s, bool betOnP1)"),
    ("live games, 2v2 header", "private static void ApplyTeamHeaderRow(GameObject row, ApiClient.ActiveTeamSeriesEntry s)"),
    ("live games, 2v2 bet row", "private static void ApplyTeamBetRow(GameObject row, ApiClient.ActiveTeamSeriesEntry s, int team)"),
    ("live games, spectate rows", "private static void ApplySpectateLiveRow(GameObject row, ApiClient.SpectateGameInfo g)"),
    ("live games, 1v2 list", "private static void RenderOvtLiveGames()"),
    ("1v2 queue duo line", "private static void RefreshOneVTwoTab()"),
    ("bets ledger", "private static void RefreshMyBetsLedger()"),
    ("compare picker", "private static void RefreshCompare()"),
    ("compare graph legend", "private static void BuildCompareGraph(bool ffa = false)"),
    ("compare bar chart", "private static void BuildCompareBarChart(string metricName)"),
    ("compare achievement grid", "private static void BuildCompareAchievementGrid(List<int> idxs, float W, float H)"),
    ("compare pie", "private static void BuildComparePieChart(List<int> idxs, float W, float H)"),
    ("compare generic pie", "private static void BuildCompareGenericPie(List<int> idxs, float W, float H, string metricName)"),
    ("compare similar players", "private static void BuildCompareSimilarPanel(List<int> idxs, float W, float H)"),
    ("compare card grid", "private static void BuildCompareCardGrid(string metricName)"),
    ("compare metric table", "private static void BuildCompareMetricTable()"),
]

# A name field: an expression ending in name / Name / names / label / Fit, optionally
# member-accessed (s.p1_name, ps.display_name, duo[0].display_name, g.names, wName,
# leftFit -- FitLabelPair's output is two joined player names).
NAME_EXPR = r"[\w.\[\]?]*?(?:display_name|names?|Name|label|Fit)\b"
RAW_TRUNC = re.compile(r"(?<![\w.])Trunc\(\s*(" + NAME_EXPR + r")(?:\s*\?\?\s*\"[^\"]*\")?\s*,")
RAW_HOLE = re.compile(r"\{\s*(" + NAME_EXPR + r")\s*\}")
WRAPPED_BY = ("Nm(", "FfaSafeRich(", "FitLabel(", "InactiveName(")
# Expressions the patterns match that are not player names, each with where it goes.
# Each must still occur (a stale exemption is a finding, not a silent pass).
NOT_PLAYER_NAMES = {
    ("FillOvtRoleBoard", "container.name"): "the pooled row's GameObject name (CreateText's first argument), never painted",
}


@functools.lru_cache(maxsize=None)
def _read_all() -> tuple:
    return tuple((p.name, p.read_text(encoding="utf-8")) for p in sorted(PLUGIN.glob("*.cs")))


def _sources() -> dict:
    return dict(_read_all())


@functools.lru_cache(maxsize=16)
def _views(src: str) -> tuple:
    """(mask, comments-stripped) of one file, computed once; both keep offsets."""
    return mask_code(src), strip_comments_only(src)


@functools.lru_cache(maxsize=512)
def _code(src: str, signature: str) -> str:
    """The one block `signature` opens, comments removed and literals kept.

    The signature and the braces are found on the MASK (a brace in a literal is
    not structure); the text is cut from the comments-stripped view at the same
    offsets. Exactly one match, or the assertion is about an accident.
    """
    masked, code = _views(src)
    at = masked.find(signature)
    if at < 0:
        raise AssertionError("signature not found: %r" % signature)
    if masked.find(signature, at + 1) >= 0:
        raise AssertionError("more than one block matches %r" % signature)
    open_brace = masked.find("{", at + len(signature))
    depth = 0
    for i in range(open_brace, len(masked)):
        if masked[i] == "{":
            depth += 1
        elif masked[i] == "}":
            depth -= 1
            if depth == 0:
                return code[open_brace:i + 1]
    raise AssertionError("unbalanced block after %r" % signature)


def _wrapped(code: str, at: int) -> bool:
    """The match at `at` sits directly inside one of the sanitising calls."""
    head = code[max(0, at - 16):at]
    return any(head.endswith(w) for w in WRAPPED_BY)


def _sanitised_locals(code: str) -> set:
    """Locals whose declaration's initialiser runs a sanitiser in this block
    (ApplyBetRow's `name`, RefreshLeaderboard's `_lbName`, ApplyTeamBetRow's
    `sideName`, a team colour name through FfaSafeRich)."""
    return {m.group(1) for m in re.finditer(r"\bstring\s+(\w+)\s*=([^;]*);", code)
            if "Nm(" in m.group(2) or "FfaSafeRich(" in m.group(2)}


def findings(sources: dict) -> list:
    out = []
    native = sources[NATIVE]
    # A. the chain: Nm -> UnicodeFallback.SafeName -> NameGlyphs.Safe; FfaSafeRich -> SafeGlyphs -> Glyphs.
    try:
        nm = _code(native, "private static string Nm(string s,int max)")
        nm1 = _code(native, "private static string Nm(string s)")
        if "UnicodeFallback.SafeName(" not in nm or "UnicodeFallback.SafeName(" not in nm1:
            out.append("A: Nm does not call UnicodeFallback.SafeName")
        rich = _code(native, "private static string FfaSafeRich(string value)")
        if "UnicodeFallback.SafeGlyphs(" not in rich:
            out.append("A: FfaSafeRich does not call UnicodeFallback.SafeGlyphs")
        fb = sources[FALLBACK]
        if "NameGlyphs.Safe(s, CanRender)" not in _code(fb, "internal static string SafeName(string s)"):
            out.append("A: UnicodeFallback.SafeName does not run NameGlyphs.Safe over CanRender")
        if "NameGlyphs.Glyphs(s, CanRender)" not in _code(fb, "internal static string SafeGlyphs(string s)"):
            out.append("A: UnicodeFallback.SafeGlyphs does not run NameGlyphs.Glyphs over CanRender")
        trunc = _code(native, "private static string Trunc(string s,int max)")
        if "char.IsHighSurrogate(" not in trunc:
            out.append("A: NativeUI.Trunc can cut a surrogate pair in half")
    except AssertionError as e:
        out.append("A: " + str(e))
    # B. the sweep: no swept panel paints a name field raw.
    for panel, sig in PANELS:
        try:
            code = _code(native, sig)
        except AssertionError as e:
            out.append("B: %s: %s" % (panel, e))
            continue
        ok_locals = _sanitised_locals(code)
        method = sig.split("(")[0].split()[-1]
        for (where, expr), _why in NOT_PLAYER_NAMES.items():
            if where == method and expr not in code:
                out.append("B: the exemption %r no longer occurs in %s" % (expr, method))
        for rx in (RAW_TRUNC, RAW_HOLE):
            for m in rx.finditer(code):
                expr = m.group(1)
                if expr in ok_locals or _wrapped(code, m.start()) or (method, expr) in NOT_PLAYER_NAMES:
                    continue
                out.append("B: %s paints %r raw (%s)" % (panel, m.group(0), sig.split("(")[0].split()[-1]))
    return out


def test_every_list_panel_name_passes_the_one_sanitiser():
    got = findings(_sources())
    assert got == [], "\n".join(got)


def _mutate(name: str, old: str, new: str) -> dict:
    src = _sources()
    assert src[name].count(old) == 1, "mutation anchor %r occurs %d times in %s" % (old, src[name].count(old), name)
    src[name] = src[name].replace(old, new)
    return src


MUTANTS = [
    ("recent_1v1_names_raw", NATIVE, "string wNameT=Nm(wName,16), lNameT=Nm(lName,16);",
     "string wNameT=Trunc(wName,16), lNameT=Trunc(lName,16);", "B:"),
    ("recent_bettor_raw", NATIVE, 'Nm(b.bettor_name ?? "?", 14)', 'Trunc(b.bettor_name ?? "?", 14)', "B:"),
    ("multimode_labels_raw", NATIVE, "{Nm(leftFit)}", "{leftFit}", "B:"),
    ("leaderboard_row_raw", NATIVE, "InactiveName(Nm(e.display_name,20),e.inactive)",
     "(Trunc(e.display_name,20))", "B:"),
    ("bets_ledger_raw", NATIVE, "on {Nm(b.bet_on_name)} vs {Nm(b.vs_name)} - LOST", "on {b.bet_on_name} vs {b.vs_name} - LOST", "B:"),
    ("compare_table_raw", NATIVE, '<b>{Nm(ps.display_name)}</b></color>  ");', '<b>{ps.display_name}</b></color>  ");', "B:"),
    ("ffa_rich_without_glyphs", NATIVE, "return UnicodeFallback.SafeGlyphs(sb.ToString())", "return (sb.ToString())", "A:"),
    ("nm_skips_the_sanitiser", NATIVE, "private static string Nm(string s,int max){return UnicodeFallback.SafeName(Trunc(s??\"\",max));}",
     "private static string Nm(string s,int max){return Trunc(s??\"\",max);}", "A:"),
    ("trunc_cuts_pairs", NATIVE, "if(char.IsHighSurrogate(s[cut-1]))cut--;", "", "A:"),
]


@pytest.mark.parametrize("label,name,old,new,prefix", MUTANTS, ids=[m[0] for m in MUTANTS])
def test_each_mutation_is_caught(label, name, old, new, prefix):
    got = findings(_mutate(name, old, new))
    assert any(f.startswith(prefix) for f in got), "mutant %s not caught: %r" % (label, got)
