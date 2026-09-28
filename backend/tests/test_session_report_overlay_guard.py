"""Board row 30b: the F5 page's own IMGUI stands down while the session
report is open.

The report is pure IMGUI (SessionReportView.Draw). The page's search fields,
and the first-timer ranked callout that points at a page button, are IMGUI
drawn AFTER it in CompetitiveUI.DrawUI; IMGUI stacks by call order, so they
painted over the report and a focused field kept taking keystrokes. Each of
those draw functions now asks
SessionReportRules.PageElementMayDraw(pageOpen, onItsSurface, reportOpen)
before it paints anything. The decision itself is EXECUTED by the client rules
harness (suite "sessionreport", test_client_rules_harness.py); the IMGUI
functions cannot run under a plain compiler, so this file holds the part only
the source can show: every page element's draw function asks, asks once,
passes the report's own flag, and asks before its first control.

Two censuses are closed, so a new element drawn without asking fails: the
page's search fields (every Draw*Search), and every draw DrawUI makes after
the report - each is either a page element above or an ON_TOP entry, which
says why it belongs on top of the report (a modal, a toast, an alert strip).

Each check is a function over source text, and the negative controls feed it
the same source with one guard removed or moved, or one draw added or taken
away: a check that cannot fail is worse than none (#342).
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
UI = REPO / "plugin" / "CompetitiveUI.cs"
RULES = REPO / "plugin" / "SessionReportRules.cs"

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
GUARD = re.compile(r"if \(!SessionReportRules\.PageElementMayDraw\(NativeUI\.IsOpen, [^;]*?, "
                   r"SessionReportView\.Active\)\) return;")
FIRST_CONTROL = re.compile(r"GUI\.(TextField|Label|Button|DrawTexture)\(")
REPORT_CALL = "SessionReportView.Draw();"
MEMBER_END = re.compile(r"^        (?:private|internal|public|protected)[^\n]*$|^        // ", re.M)


def _member(src, signature):
    """The body of the member whose declaration line matches `signature`:
    from that line to the next member declaration at the same indent."""
    m = re.search(r"^        %s\s*$" % signature, src, re.M)
    assert m, "no %s in CompetitiveUI.cs" % signature
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


def test_every_page_element_stands_down_under_the_report():
    src = UI.read_text(encoding="utf-8")
    assert _problems(src) == []


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
