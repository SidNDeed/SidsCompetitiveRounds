"""Board row 30b: the F5 page's IMGUI search fields stand down while the
session report is open.

The report is pure IMGUI (SessionReportView.Draw) and the page's search
fields are IMGUI drawn AFTER it in CompetitiveUI.DrawUI; IMGUI stacks by call
order, so the fields painted over the report and a focused field kept taking
keystrokes. Each field's draw function now asks
SessionReportRules.SearchFieldMayDraw(pageOpen, onItsSurface, reportOpen)
before it paints anything. The decision itself is EXECUTED by the client rules
harness (suite "sessionreport", test_client_rules_harness.py); the IMGUI
functions cannot run under a plain compiler, so this file holds the part only
the source can show: every search field's draw function asks, asks once,
passes the report's own flag, and asks before its first control - and the
census of search fields is closed, so a new field drawn without asking fails.

Each check is a function over source text, and the negative controls feed it
the same source with one guard removed or moved: a check that cannot fail is
worse than none (#342).
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
GUARD = re.compile(r"if \(!SessionReportRules\.SearchFieldMayDraw\(NativeUI\.IsOpen, [^;]*?, "
                   r"SessionReportView\.Active\)\) return;")
FIRST_CONTROL = re.compile(r"GUI\.(TextField|Label|Button|DrawTexture)\(")


def _span(src, name):
    """The body of `private static void <name>()`: from its signature to the
    next member declaration at the same indent."""
    m = re.search(r"^        private static void %s\(\)\s*$" % re.escape(name), src, re.M)
    assert m, "no %s in CompetitiveUI.cs" % name
    nxt = re.compile(r"^        (?:private|internal|public|protected)[^\n]*$|^        // ", re.M)
    end = nxt.search(src, m.end())
    return src[m.start(): end.start() if end else len(src)]


def _problems(src):
    """Every way the guard is missing or misplaced, as sentences (empty when
    the source is right)."""
    out = []
    declared = set(re.findall(r"^        private static void (Draw\w*Search)\(\)", src, re.M))
    if declared != set(FIELDS):
        out.append("the search-field census moved: %s" % sorted(declared ^ set(FIELDS)))
    for name, flag in FIELDS.items():
        if name not in declared:
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
    return out


def test_every_search_field_stands_down_under_the_report():
    src = UI.read_text(encoding="utf-8")
    assert _problems(src) == []


def test_the_report_is_drawn_before_the_page_searches():
    """Why the guard is needed at all: the draw order this file relies on.
    Should the report ever be drawn last instead, this fails and the guard's
    rationale is to be re-read, not deleted silently."""
    src = UI.read_text(encoding="utf-8")
    at = src.find("SessionReportView.Draw();")
    assert at > 0
    for name in ("DrawCompareSearch();", "DrawLeaderboardSearch();", "DrawCardStatsSearch();",
                 "DrawHistorySearch();", "DrawInfoSearch();", "DrawPickerSearch();", "DrawPlayerSearch();"):
        assert src.find(name, at) > at, name + " is no longer drawn after the report"


def test_the_rule_is_the_one_the_harness_executes():
    rules = RULES.read_text(encoding="utf-8")
    assert "internal static bool SearchFieldMayDraw(bool pageOpen, bool onItsSurface, bool reportOpen)" in rules
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
