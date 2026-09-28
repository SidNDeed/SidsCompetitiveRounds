"""Board row 30b: the F5 page's own IMGUI stands down while the session
report is open.

The report is pure IMGUI (SessionReportView.Draw). The page's search fields,
and the first-timer ranked callout that points at a page button, are IMGUI
drawn AFTER it in CompetitiveUI.DrawUI; IMGUI stacks by call order, so they
painted over the report and a focused field kept taking keystrokes. The FFA
and 1v2 tabs' row hover tooltips are page IMGUI too, painted from their tabs'
own behaviours (FfaRecentGraphDrawer, OneVTwoHoverDrawer): Unity orders one
behaviour's OnGUI against another's by GUI.depth, not by DrawUI's call order,
and those two ask to be on top. Each of those draw functions now asks
SessionReportRules.PageElementMayDraw(pageOpen, onItsSurface, reportOpen)
before it paints anything. The decision itself is EXECUTED by the client rules
harness (suite "sessionreport", test_client_rules_harness.py); the IMGUI
functions cannot run under a plain compiler, so this file holds the part only
the source can show: every page element's draw function asks, asks once,
passes the report's own flag, and asks before it paints.

Three censuses are closed, so a new element drawn without asking fails: the
page's search fields (every Draw*Search); every draw DrawUI makes after the
report - each is either a page element above or an ON_TOP entry, which says
why it belongs on top of the report (a modal, a toast, an alert strip); and
every behaviour under plugin/ with its own OnGUI - each is a tab tooltip,
which asks the rule for its own tab, or a NOT_PAGE entry, which says why it
is not page IMGUI.

Each check is a function over source text, and the negative controls feed it
the same source with one guard removed or moved, or one draw or behaviour
added or taken away: a check that cannot fail is worse than none (#342).
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PLUGIN = REPO / "plugin"
UI = PLUGIN / "CompetitiveUI.cs"
RULES = PLUGIN / "SessionReportRules.cs"

# the search fields, with the focus flag each one resets first (None: the
# admin player search is a modal with no chat-mutex flag)
FIELDS = {
    "DrawCompareSearch": "compareSearchFocused",
    "DrawPickerSearch": "pickerSearchFocused",
    "DrawLeaderboardSearch": "lbSearchFocused",
    "DrawCardStatsSearch": "cardStatsSearchFocused",
    "DrawInfoSearch": "infoSearchFocused",
    "DrawHistorySearch": "histSearchFocused",
    "DrawPlayerSearch": None,
}
# the page's other IMGUI drawn after the report: the first-timer callout above
# the Search Ranked button (display only, so there is no focus flag)
CALLOUTS = {
    "DrawRankedHintCallout": None,
}
PAGE = dict(FIELDS, **CALLOUTS)
# every other draw DrawUI makes after the report, and why it sits on top of it
ON_TOP = {
    "DrawMapColorToast": "a short toast naming the map skin the player just cycled to",
    "DrawCustomBetPrompt": "a modal the player opened",
    "DrawLfpPrompt": "a modal the player opened",
    "DrawArtistInput": "a modal the player opened",
    "DrawArtistPicker": "a modal the player opened",
    "MailUI.DrawImgui": "the mail popup's own fields (no report is drawn under a popup) and its report modal",
    "DrawCosmeticTestPreview": "an admin modal",
    "DrawCosmeticReview": "an admin modal",
    "DrawCosmeticReleaseQueue": "an admin modal",
    "DrawFlagEvidence": "an admin modal",
    "DrawLeaverBanner": "an alert strip: a player left",
    "DrawTournamentBanner": "an alert strip: a tournament match",
    "DrawRoomRulesBanner": "the in-room card-rule strip",
    "DrawConsentModal": "the consent modal, drawn last on purpose",
}
# every behaviour with its own OnGUI. A tab tooltip names the draw its OnGUI
# calls (in NativeUI.cs) and the tab it serves; every other one says why it is
# not page IMGUI.
TOOLTIPS = {
    "FfaRecentGraphDrawer": ("DrawFfaRecentHoverGraph", 12),
    "OneVTwoHoverDrawer": ("DrawOvtRecentHover", 11),
}
NOT_PAGE = {
    "CompetitiveRoundsBehaviour": "the root (Plugin.cs): its OnGUI is DrawUI, which draws the report",
    "ShieldProbe": "a dev self-test (the ladder popup's shield probe): it synthesizes input events and logs, and paints nothing",
}
GUARD = re.compile(r"if \(!SessionReportRules\.PageElementMayDraw\(NativeUI\.IsOpen, [^;]*?, "
                   r"SessionReportView\.Active\)\) return;")
TOOLTIP_GUARD = re.compile(r"if\(!SessionReportRules\.PageElementMayDraw\(isOpen,currentTab==(\d+),"
                           r"SessionReportView\.Active\)\|\|CompetitiveUI\.PageImguiHidden\)return;")
FIRST_CONTROL = re.compile(r"GUI\.(TextField|Label|Button|DrawTexture)\(")
FIRST_PAINT = re.compile(r"\b(?:DrawFfaCardsTooltip|DrawFfaTimelineGraph|DrawWideTooltip)\(|\bGUI\.\w+\(")
REPORT_CALL = "SessionReportView.Draw();"
MEMBER_END = re.compile(r"^        (?:private|internal|public|protected)[^\n]*$|^        // ", re.M)
ONGUI = re.compile(r"^( *)[\w ]*?\bvoid\s+OnGUI\s*\(", re.M)
CLASS = re.compile(r"^( *)(?:\w+ )*class (\w+)", re.M)


def _member(src, signature, where="CompetitiveUI.cs"):
    """The body of the member whose declaration line matches `signature`:
    from that line to the next member declaration at the same indent."""
    m = re.search(r"^        %s\s*$" % signature, src, re.M)
    assert m, "no %s in %s" % (signature, where)
    end = MEMBER_END.search(src, m.end())
    return src[m.start(): end.start() if end else len(src)]


def _span(src, name):
    return _member(src, r"private static void %s\(\)" % re.escape(name))


def _drawn_after_report(src):
    """Every Draw call DrawUI makes after the report's own, in order, line
    comments stripped first (a commented-out call is not a draw)."""
    body = re.sub(r"//[^\n]*", "", _member(src, r"public static void DrawUI\(\)"))
    at = body.find(REPORT_CALL)
    assert at > 0, "DrawUI no longer draws the report"
    return re.findall(r"\b((?:\w+\.)?Draw\w*)\(", body[at + len(REPORT_CALL):])


def _problems(src):
    """Every way a guard is missing or misplaced, or a census has moved, as
    sentences (empty when the source is right)."""
    out = []
    declared = set(re.findall(r"^        private static void (Draw\w*Search)\(\)", src, re.M))
    if declared != set(FIELDS):
        out.append("the search-field census moved: %s" % sorted(declared ^ set(FIELDS)))
    for name, flag in PAGE.items():
        if name in FIELDS and name not in declared:
            continue
        body = _span(src, name)
        guards = list(GUARD.finditer(body))
        if len(guards) != 1:
            out.append("%s asks %d times" % (name, len(guards)))
            continue
        ctl = FIRST_CONTROL.search(body)
        if ctl is None or ctl.start() < guards[0].start():
            out.append("%s paints before it asks" % name)
        if flag is not None:
            reset = body.find(flag + " = false;")
            if reset < 0 or reset > guards[0].start():
                out.append("%s does not reset %s before it asks" % (name, flag))
    after = _drawn_after_report(src)
    loose = sorted(set(after) - set(PAGE) - set(ON_TOP))
    if loose:
        out.append("unclassified IMGUI draw after the report: %s" % loose)
    gone = sorted((set(PAGE) | set(ON_TOP)) - set(after))
    if gone:
        out.append("no longer drawn after the report: %s" % gone)
    return out


def _plugin_sources():
    """Every C# source under plugin/ except build output, by its path under
    plugin/, as text."""
    out = {}
    for path in sorted(PLUGIN.rglob("*.cs")):
        rel = path.relative_to(PLUGIN).as_posix()
        if rel.split("/")[0] in ("bin", "obj"):
            continue
        out[rel] = path.read_text(encoding="utf-8")
    return out


def _ongui_owners(sources):
    """{class: [the text of each OnGUI it declares, to its first closing
    brace]} over every source. An OnGUI's owner is the nearest class declared
    above it at a smaller indent (None when there is none)."""
    owners = {}
    for src in sources.values():
        for m in ONGUI.finditer(src):
            indent = len(m.group(1))
            owner = None
            for c in CLASS.finditer(src, 0, m.start()):
                if len(c.group(1)) < indent:
                    owner = c.group(2)
            owners.setdefault(owner, []).append(src[m.start(): src.find("}", m.end()) + 1])
    return owners


def _behaviour_problems(sources):
    """Every way the census of behaviours with their own OnGUI has moved, or
    a tab tooltip's guard is missing or misplaced, as sentences (empty when
    the sources are right)."""
    out = []
    owners = _ongui_owners(sources)
    if None in owners:
        out.append("an OnGUI outside any class")
    named = set(owners) - {None}
    loose = sorted(named - set(TOOLTIPS) - set(NOT_PAGE))
    if loose:
        out.append("unclassified OnGUI behaviour: %s" % loose)
    gone = sorted((set(TOOLTIPS) | set(NOT_PAGE)) - named)
    if gone:
        out.append("no longer an OnGUI behaviour: %s" % gone)
    native = sources["NativeUI.cs"]
    for cls, (draw, tab) in sorted(TOOLTIPS.items()):
        if cls not in named:
            continue
        if not any(re.search(r"\b%s\(\);" % draw, text) for text in owners[cls]):
            out.append("%s's OnGUI no longer calls %s" % (cls, draw))
        body = _member(native, r"private static void %s\(\)" % draw, "NativeUI.cs")
        guards = list(TOOLTIP_GUARD.finditer(body))
        if len(guards) != 1:
            out.append("%s asks %d times" % (draw, len(guards)))
            continue
        if guards[0].group(1) != str(tab):
            out.append("%s asks for tab %s, not %d" % (draw, guards[0].group(1), tab))
        paint = FIRST_PAINT.search(body)
        if paint is None:
            out.append("%s no longer paints" % draw)
        elif paint.start() < guards[0].start():
            out.append("%s paints before it asks" % draw)
    return out


def test_every_page_element_stands_down_under_the_report():
    src = UI.read_text(encoding="utf-8")
    assert _problems(src) == []


def test_every_tab_tooltip_stands_down_under_the_report():
    assert _behaviour_problems(_plugin_sources()) == []


def test_the_report_is_drawn_before_the_page_elements():
    """Why the guard is needed at all: the draw order this file relies on.
    Should the report ever be drawn last instead, this fails and the guard's
    rationale is to be re-read, not deleted silently."""
    src = UI.read_text(encoding="utf-8")
    at = src.find(REPORT_CALL)
    assert at > 0
    for name in ("DrawCompareSearch();", "DrawLeaderboardSearch();", "DrawCardStatsSearch();",
                 "DrawHistorySearch();", "DrawInfoSearch();", "DrawPickerSearch();", "DrawPlayerSearch();",
                 "DrawRankedHintCallout();"):
        assert src.find(name, at) > at, name + " is no longer drawn after the report"


def test_the_rule_is_the_one_the_harness_executes():
    rules = RULES.read_text(encoding="utf-8")
    assert "internal static bool PageElementMayDraw(bool pageOpen, bool onItsSurface, bool reportOpen)" in rules
    assert "=> pageOpen && onItsSurface && !reportOpen;" in rules


# -- negative controls: the checker reds on each defect it claims to catch ----

def _mutate(src, name, fn):
    body = _span(src, name)
    return src.replace(body, fn(body), 1)


def test_control_a_removed_guard_is_caught():
    src = UI.read_text(encoding="utf-8")
    bad = _mutate(src, "DrawHistorySearch", lambda b: GUARD.sub("", b, count=1))
    assert _problems(bad) == ["DrawHistorySearch asks 0 times"]


def test_control_a_guard_after_the_first_control_is_caught():
    src = UI.read_text(encoding="utf-8")

    def move(b):
        # the guard moves to just AFTER the field has painted
        g = GUARD.search(b).group(0)
        b = b.replace(g, "", 1)
        at = "string next = GUI.TextField(fieldRect, cur, compareSearchStyle);"
        assert b.count(at) == 1
        return b.replace(at, at + "\n                " + g, 1)
    bad = _mutate(src, "DrawCompareSearch", move)
    assert _problems(bad) == ["DrawCompareSearch paints before it asks"]


def test_control_a_guard_on_another_flag_is_caught():
    src = UI.read_text(encoding="utf-8")
    bad = _mutate(src, "DrawInfoSearch", lambda b: b.replace("SessionReportView.Active)) return;",
                                                              "NativeUI.PickerOpen)) return;", 1))
    assert _problems(bad) == ["DrawInfoSearch asks 0 times"]


def test_control_a_new_unguarded_field_is_caught():
    src = UI.read_text(encoding="utf-8")
    bad = src.replace("        private static void DrawInfoSearch()",
                      "        private static void DrawNewSearch()\n        {\n            GUI.TextField(r, s);\n        }\n\n"
                      "        private static void DrawInfoSearch()", 1)
    assert _problems(bad) == ["the search-field census moved: ['DrawNewSearch']"]


def test_control_the_callout_back_on_its_old_gate_is_caught():
    """The callout's gate as it stood before this row reached it: the page
    open and the hint wanted, the report not asked."""
    src = UI.read_text(encoding="utf-8")
    bad = _mutate(src, "DrawRankedHintCallout",
                  lambda b: GUARD.sub("if (!NativeUI.IsOpen || !NativeUI.RankedHintActive) return;", b, count=1))
    assert _problems(bad) == ["DrawRankedHintCallout asks 0 times"]


def test_control_an_unclassified_draw_after_the_report_is_caught():
    src = UI.read_text(encoding="utf-8")
    at = "            DrawTournamentBanner();\n            DrawRoomRulesBanner();"
    assert src.count(at) == 1
    bad = src.replace(at, at + "\n            DrawNewPageBadge();", 1)
    assert _problems(bad) == ["unclassified IMGUI draw after the report: ['DrawNewPageBadge']"]


def test_control_a_draw_gone_from_after_the_report_is_caught():
    src = UI.read_text(encoding="utf-8")
    at = "            DrawTournamentBanner();\n            DrawRoomRulesBanner();"
    assert src.count(at) == 1
    bad = src.replace(at, "            DrawRoomRulesBanner();", 1)
    assert _problems(bad) == ["no longer drawn after the report: ['DrawTournamentBanner']"]


def _native(fn):
    """The plugin's sources with NativeUI.cs passed through fn."""
    sources = _plugin_sources()
    sources["NativeUI.cs"] = fn(sources["NativeUI.cs"])
    return sources


def _swap_tooltip_guard(native, draw, new):
    body = _member(native, r"private static void %s\(\)" % draw, "NativeUI.cs")
    assert len(TOOLTIP_GUARD.findall(body)) == 1
    return native.replace(body, TOOLTIP_GUARD.sub(lambda m: new, body, count=1), 1)


def test_control_a_tooltip_back_on_its_old_gate_is_caught():
    """The FFA tooltip's gate as it stood before this row reached it: the
    page open, its tab showing and no popup up, the report not asked."""
    bad = _native(lambda n: _swap_tooltip_guard(
        n, "DrawFfaRecentHoverGraph", "if(!isOpen||currentTab!=12||CompetitiveUI.PageImguiHidden)return;"))
    assert _behaviour_problems(bad) == ["DrawFfaRecentHoverGraph asks 0 times"]


def test_control_a_tooltip_asking_for_another_tab_is_caught():
    bad = _native(lambda n: _swap_tooltip_guard(
        n, "DrawOvtRecentHover",
        "if(!SessionReportRules.PageElementMayDraw(isOpen,currentTab==12,SessionReportView.Active)"
        "||CompetitiveUI.PageImguiHidden)return;"))
    assert _behaviour_problems(bad) == ["DrawOvtRecentHover asks for tab 12, not 11"]


def test_control_a_tooltip_painting_before_it_asks_is_caught():
    def move(n):
        body = _member(n, r"private static void DrawOvtRecentHover\(\)", "NativeUI.cs")
        guard = TOOLTIP_GUARD.search(body).group(0)
        at = "try{GUI.depth=-20000;DrawWideTooltip(tip,mouse,470f);}"
        assert body.count(at) == 1
        return n.replace(body, body.replace(guard, "", 1).replace(at, at + guard, 1), 1)
    assert _behaviour_problems(_native(move)) == ["DrawOvtRecentHover paints before it asks"]


def test_control_a_tooltip_that_no_longer_paints_is_caught():
    def mute(n):
        body = _member(n, r"private static void DrawOvtRecentHover\(\)", "NativeUI.cs")
        at = "DrawWideTooltip(tip,mouse,470f);"
        assert body.count(at) == 1
        return n.replace(body, body.replace(at, "", 1), 1)
    assert _behaviour_problems(_native(mute)) == ["DrawOvtRecentHover no longer paints"]


def test_control_a_tooltip_behaviour_calling_another_draw_is_caught():
    def swap(n):
        at = "private void OnGUI() { DrawFfaRecentHoverGraph(); }"
        assert n.count(at) == 1
        return n.replace(at, "private void OnGUI() { DrawFfaRecentHoverGraphV2(); }", 1)
    assert _behaviour_problems(_native(swap)) == [
        "FfaRecentGraphDrawer's OnGUI no longer calls DrawFfaRecentHoverGraph"]


def test_control_an_unclassified_ongui_behaviour_is_caught():
    """A new behaviour with its own OnGUI, declared in a spacing the census
    must still see."""
    at = "        private sealed class OneVTwoHoverDrawer : MonoBehaviour\n"

    def add(n):
        assert n.count(at) == 1
        return n.replace(at, "        private sealed class NewTabDrawer : MonoBehaviour\n        {\n"
                             "            protected virtual void OnGUI ( ) { DrawNewTabHover(); }\n"
                             "        }\n" + at, 1)
    assert _behaviour_problems(_native(add)) == ["unclassified OnGUI behaviour: ['NewTabDrawer']"]


def test_control_an_ongui_behaviour_gone_is_caught():
    at = "            private void OnGUI() { DrawOvtRecentHover(); }\n"

    def drop(n):
        assert n.count(at) == 1
        return n.replace(at, "", 1)
    assert _behaviour_problems(_native(drop)) == ["no longer an OnGUI behaviour: ['OneVTwoHoverDrawer']"]


def test_control_an_ongui_outside_any_class_is_caught():
    sources = _plugin_sources()
    sources["Stray.cs"] = "void OnGUI() { }\n"
    assert _behaviour_problems(sources) == ["an OnGUI outside any class"]
