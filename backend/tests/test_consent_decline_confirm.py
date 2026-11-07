"""Ask item 12 (7 Nov 2026): the first-run consent modal's red warning line and
the confirmation on Decline.

The modal is IMGUI and cannot run here, so these are source-shape gates on
plugin/CompetitiveUI.cs. Every structural decision is taken on
`_cs_structure`'s mask, so a needle inside a comment or a string is never
code (#342/#431/#441):

1. `ConsentSetting.Set(false)` is called exactly once in the file, inside
   DrawConsentDeclineConfirm, inside the block guarded by the "Decline anyway"
   button and the Decline route's ClickGuard key. The file's only other
   consent write is Allow's `ConsentSetting.Set(true)`, unchanged.
2. The first page's "Decline (offline mode)" button writes nothing: its block
   opens the confirmation (the only place the flag turns true) and holds no
   ConsentSetting call and no `.Value =`.
3. "Back" writes nothing and closes the confirmation.
4. DrawConsentModal draws the warning key in the red warning style, after the
   body and before the buttons; DrawConsentDeclineConfirm draws the question
   key and both button keys.
5. The confirmation is never sticky: it is cleared where the modal starts
   fresh (EnsureConsentBlocker, once it builds the blocker), where the modal
   closes (DestroyConsentBlocker), and when the active scene is no longer the
   one it opened in. DrawConsentModal reaches it only after its own
   DataConsentAsked early return, and the confirmation returns early on
   DataConsentAsked as well.
6. Every new key is registered (tools/i18n_source.json and the generated
   plugin/I18nSourceKeys.g.cs) and has a row in each bundled catalogue.

The controls at the bottom run the same gates on mutated copies of the source,
one per route (learning #391): the warning line gone, Decline writing at once,
Back writing denied, and the confirmation sticky across a scene change.
"""
from __future__ import annotations

import functools
import json
import re
from pathlib import Path

from _cs_structure import mask_code, strip_comments_only

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PLUGIN = REPO / "plugin"
UI = PLUGIN / "CompetitiveUI.cs"

WARNING = ("Without data consent the mod will not work properly: the leaderboard, ranked matchmaking, "
           "chat, player cards and bug reports with logs all stop working.")
QUESTION = ("Decline data consent? The mod will run offline: no leaderboard, no ranked matchmaking, "
            "no chat, no player cards. You can allow it later in F5 → Settings → Privacy & account.")
DECLINE_ANYWAY = "Decline anyway"
BACK = "Back"
NEW_KEYS = (WARNING, QUESTION, DECLINE_ANYWAY)

MODAL = "private static void DrawConsentModal()"
CONFIRM = "private static void DrawConsentDeclineConfirm(Texture2D bg)"
ENSURE = "private static void EnsureConsentBlocker()"
DESTROY = "private static void DestroyConsentBlocker()"
ANYWAY_IF = "if (anyway && ClickGuard.Claim(consentDeclineClickKey))"
BACK_IF = "else if (back && ClickGuard.Claim(consentDeclineClickKey))"
DECLINE_IF = re.compile(r"if \(GUI\.Button\([^;{}]*\bdeclineLabel\)\s*&& ClickGuard\.Claim\(consentDeclineClickKey\)\)")
SET_FALSE = "ConsentSetting.Set(false)"
SET_ANY = "ConsentSetting.Set("
ASSIGN = re.compile(r"\.Value\s*=(?![=>])")
FLAG_TRUE = re.compile(r"\bconsentDeclineConfirmOpen\s*=\s*true\s*;")
FLAG_FALSE = re.compile(r"\bconsentDeclineConfirmOpen\s*=\s*false\s*;")
# CONSENT-R1 LOW-1: Allow's write is pinned to its button block, and the Decline and Back
# blocks may not reach the writer indirectly (a method group, a delegate, reflection, the
# consent hook or the flag) any more than directly.
ALLOW_IF = re.compile(r"if \(GUI\.Button\([^;{}]*\ballowLabel\)\)")
SET_TRUE = "ConsentSetting.Set(true)"
SET_TOKEN = re.compile(r"\bConsentSetting\.Set\b")
INDIRECT = re.compile(r"\bConsentSetting\b|\bOnConsentChanged\b|\bDataConsentAsked\s*=(?!=)|\bInvoke\(|"
                      r"\bGetMethod\(|\bDataConsent\b")
DRAW_UI = "public static void DrawUI()"


def _block_from(masked: str, at: int) -> tuple:
    """(open, close_exclusive) of the brace block that opens first at or after
    `at`, walked on the mask."""
    open_brace = masked.find("{", at)
    assert open_brace != -1, "no block opens after offset %d" % at
    depth = 0
    for i in range(open_brace, len(masked)):
        if masked[i] == "{":
            depth += 1
        elif masked[i] == "}":
            depth -= 1
            if depth == 0:
                return open_brace, i + 1
    raise AssertionError("unbalanced braces after offset %d" % at)


def _span(masked: str, signature: str) -> tuple:
    at = masked.find(signature)
    assert at != -1, "not found: %r" % signature
    assert masked.find(signature, at + len(signature)) == -1, "found twice: %r" % signature
    return _block_from(masked, at + len(signature))


def findings(src: str) -> list:
    """Every gate above that the source fails, as one line each; [] = clean."""
    out = []
    masked = mask_code(src)
    literal = strip_comments_only(src)

    def span(signature, lo=0, hi=None):
        hi = len(masked) if hi is None else hi
        at = masked.find(signature, lo, hi)
        if at == -1:
            return None
        if masked.find(signature, at + len(signature), hi) != -1:
            out.append("found twice: %r" % signature)
        return _block_from(masked, at + len(signature))

    modal = span(MODAL)
    confirm = span(CONFIRM)
    if modal is None or confirm is None:
        return out + ["DrawConsentModal or DrawConsentDeclineConfirm is missing"]

    # 1. the one denied write, and where it sits
    sets_false = [m.start() for m in re.finditer(re.escape(SET_FALSE), masked)]
    if len(sets_false) != 1:
        out.append("ConsentSetting.Set(false) occurs %d times in CompetitiveUI.cs, not once" % len(sets_false))
    sets_any = len(re.findall(re.escape(SET_ANY), masked))
    if sets_any != 2:
        out.append("CompetitiveUI.cs calls ConsentSetting.Set %d times; Allow and Decline anyway are the two" % sets_any)
    tokens = len(SET_TOKEN.findall(masked))
    if tokens != 2:
        out.append("ConsentSetting.Set is named %d times in CompetitiveUI.cs (calls or method groups), not twice" % tokens)
    sets_true = [m.start() for m in re.finditer(re.escape(SET_TRUE), masked)]
    if len(sets_true) != 1:
        out.append("ConsentSetting.Set(true) occurs %d times in CompetitiveUI.cs, not once" % len(sets_true))
    allow = ALLOW_IF.search(masked, modal[0], modal[1])
    if allow is None:
        out.append("DrawConsentModal has no Allow button block")
    else:
        lo, hi = _block_from(masked, allow.end())
        if not any(lo < s < hi for s in sets_true):
            out.append("ConsentSetting.Set(true) is not inside the Allow button block")
    anyway = span(ANYWAY_IF, *confirm)
    if anyway is None:
        out.append("DrawConsentDeclineConfirm has no 'Decline anyway' block on the Decline ClickGuard key")
    elif not any(anyway[0] < s < anyway[1] for s in sets_false):
        out.append("ConsentSetting.Set(false) is not inside the 'Decline anyway' block")
    confirm_lit = literal[confirm[0]:confirm[1]]
    if 'string declineAnywayLabel = I18n.Tr("%s");' % DECLINE_ANYWAY not in confirm_lit:
        out.append("the 'Decline anyway' label is not its own key")
    if not re.search(r"bool anyway = GUI\.Button\([^;]*\bdeclineAnywayLabel\);", confirm_lit):
        out.append("'anyway' is not the 'Decline anyway' button")

    # 2. the first page's Decline writes nothing
    modal_masked = masked[modal[0]:modal[1]]
    if SET_FALSE in modal_masked:
        out.append("DrawConsentModal itself writes denied")
    m = DECLINE_IF.search(masked, modal[0], modal[1])
    if m is None:
        out.append("DrawConsentModal has no Decline button block on the Decline ClickGuard key")
    else:
        lo, hi = _block_from(masked, m.end())
        block = masked[lo:hi]
        if SET_ANY in block or ASSIGN.search(block) or INDIRECT.search(block):
            out.append("the Decline button writes the consent row")
        if not FLAG_TRUE.search(block):
            out.append("the Decline button does not open the confirmation")
    if len(FLAG_TRUE.findall(masked)) != 1:
        out.append("the confirmation flag is set true in %d places, not only by Decline" % len(FLAG_TRUE.findall(masked)))

    # 3. Back writes nothing
    back = span(BACK_IF, *confirm)
    if back is None:
        out.append("DrawConsentDeclineConfirm has no 'Back' block on the Decline ClickGuard key")
    else:
        block = masked[back[0]:back[1]]
        if SET_ANY in block or ASSIGN.search(block) or INDIRECT.search(block):
            out.append("'Back' writes the consent row")
        if not FLAG_FALSE.search(block):
            out.append("'Back' does not close the confirmation")
    if 'string backLabel = I18n.Tr("%s");' % BACK not in confirm_lit:
        out.append("the 'Back' label is not its own key")
    if not re.search(r"bool back = GUI\.Button\([^;]*\bbackLabel\);", confirm_lit):
        out.append("'back' is not the 'Back' button")

    # 4. the warning line and the question
    modal_lit = literal[modal[0]:modal[1]]
    if 'string warning = I18n.Tr("%s");' % WARNING not in modal_lit:
        out.append("DrawConsentModal does not translate the warning key")
    body_at = modal_lit.find(", body, consentBodyStyle);")
    warn_at = modal_lit.find(", warning, consentWarnStyle);")
    button_at = modal_lit.find("GUI.Button(")
    if warn_at == -1:
        out.append("DrawConsentModal does not draw the warning in the warning style")
    elif not (0 <= body_at < warn_at < button_at):
        out.append("the warning is not drawn after the body and before the buttons")
    red = re.search(r"consentWarnStyle\.normal\.textColor = new Color\(1f, (0\.\d+)f, (0\.\d+)f\);", literal)
    if red is None or not (float(red.group(1)) < 0.6 and float(red.group(2)) < 0.6):
        out.append("the warning style is not the mod's error red")
    if 'I18n.Tr("%s")' % QUESTION not in confirm_lit:
        out.append("DrawConsentDeclineConfirm does not translate the question key")

    # 5. never sticky; early returns
    if not modal_masked.lstrip("{ \r\n\t").startswith("if (Plugin.DataConsentAsked)"):
        out.append("DrawConsentModal does not start with its DataConsentAsked early return")
    if not masked[confirm[0]:confirm[1]].lstrip("{ \r\n\t").startswith("if (Plugin.DataConsentAsked)"):
        out.append("DrawConsentDeclineConfirm does not start with a DataConsentAsked early return")
    gate = span("if (consentDeclineConfirmOpen)", *modal)
    if gate is None or "DrawConsentDeclineConfirm(bg);" not in masked[gate[0]:gate[1]] \
            or "return;" not in masked[gate[0]:gate[1]]:
        out.append("DrawConsentModal does not hand the whole draw to the confirmation while it is open")
    if len(re.findall(r"\bDrawConsentDeclineConfirm\(", masked)) != 2:
        out.append("DrawConsentDeclineConfirm is called from somewhere other than DrawConsentModal")
    if not re.search(r"if \(consentDeclineConfirmOpen && consentDeclineConfirmScene != ConsentSceneHandle\(\)\)\s*"
                     r"consentDeclineConfirmOpen = false;", modal_masked):
        out.append("a scene change does not send the modal back to its first page")
    ensure = span(ENSURE)
    if ensure is None:
        out.append("EnsureConsentBlocker is missing")
    else:
        e = masked[ensure[0]:ensure[1]]
        ret = e.find("if (consentBlockerGO != null) return;")
        reset = FLAG_FALSE.search(e)
        if ret == -1 or reset is None or reset.start() < ret:
            out.append("building the blocker does not open the modal on its first page")
    destroy = span(DESTROY)
    if destroy is None or not FLAG_FALSE.search(masked[destroy[0]:destroy[1]]):
        out.append("closing the modal does not clear the confirmation")

    # 6. the consent modal is DrawUI's last draw (LOW-1: the overlay guard describes it, this enforces it)
    draw_ui = span(DRAW_UI)
    if draw_ui is None:
        out.append("DrawUI is missing")
    elif not re.search(r"DrawConsentModal\(\);\s*\}\s*$", literal[draw_ui[0]:draw_ui[1]]):
        out.append("DrawConsentModal is not the last statement of DrawUI")
    return out


@functools.lru_cache(maxsize=None)
def _ui() -> str:
    return UI.read_text(encoding="utf-8")


def test_the_consent_modal_warns_and_decline_asks_first():
    assert findings(_ui()) == []


def test_every_new_consent_key_is_registered_and_in_every_catalogue():
    registry = json.loads((REPO / "tools" / "i18n_source.json").read_text(encoding="utf-8"))
    keys_g = (PLUGIN / "I18nSourceKeys.g.cs").read_text(encoding="utf-8")
    catalogues = (PLUGIN / "I18nCatalogues.cs").read_text(encoding="utf-8")
    for key in NEW_KEYS + (BACK,):
        assert key in registry["strings"], key
        assert '\n            "%s",' % key in keys_g.replace("\r\n", "\n"), key
        assert catalogues.count('["%s"] = "' % key) == 4, key


# ── controls: one mutant per route, each must turn the gate red ─────────────

def _mutant(old: str, new: str) -> str:
    src = _ui()
    assert src.count(old) == 1, old
    return src.replace(old, new)


def _red(src: str, needle: str) -> None:
    got = findings(src)
    assert any(needle in f for f in got), got


def test_control_the_warning_line_removed_is_caught():
    src = _ui()
    line = re.search(r"\n[ \t]*GUI\.Label\([^\n]*, warning, consentWarnStyle\);", src)
    assert line
    _red(src[:line.start()] + src[line.end():], "does not draw the warning")


def test_control_decline_writing_at_once_is_caught():
    _red(_mutant("consentDeclineConfirmOpen = true;", "ConsentSetting.Set(false);"),
         "the Decline button writes the consent row")


def test_control_back_writing_denied_is_caught():
    src = _ui()
    m = re.search(re.escape(BACK_IF) + r"\s*\{", src)
    assert m
    _red(src[:m.end()] + " ConsentSetting.Set(false); " + src[m.end():], "'Back' writes the consent row")


def test_control_back_writing_the_row_directly_is_caught():
    src = _ui()
    m = re.search(re.escape(BACK_IF) + r"\s*\{", src)
    assert m
    _red(src[:m.end()] + ' Plugin.DataConsent.Value = "denied"; ' + src[m.end():], "'Back' writes the consent row")


def test_control_a_sticky_confirmation_is_caught():
    src = _ui()
    m = re.search(r"if \(consentDeclineConfirmOpen && consentDeclineConfirmScene != ConsentSceneHandle\(\)\)\s*"
                  r"consentDeclineConfirmOpen = false;", src)
    assert m
    _red(src[:m.start()] + src[m.end():], "a scene change does not send the modal back")


# CONSENT-R1 LOW-1 controls: the writer reached around its guards, and a draw after the consent modal.
def test_control_allow_writing_outside_its_button_is_caught():
    src = _ui()
    allow = re.search(r"\n[ \t]*if \(GUI\.Button\([^\n]*\ballowLabel\)\)", src)
    assert allow
    m = re.search(r"\n([ \t]*)ConsentSetting\.Set\(true\);[^\n]*", src)
    assert m and allow.start() < m.start()
    moved = (src[:allow.start()] + "\n" + m.group(1) + "ConsentSetting.Set(true);"
             + src[allow.start():m.start()] + src[m.end():])
    _red(moved, "not inside the Allow button block")


def test_control_a_method_group_on_back_is_caught():
    src = _ui()
    m = re.search(re.escape(BACK_IF) + r"\s*\{", src)
    assert m
    _red(src[:m.end()] + " System.Action<bool> write = ConsentSetting.Set; write(false); " + src[m.end():],
         "'Back' writes the consent row")


def test_control_a_reflection_call_on_decline_is_caught():
    _red(_mutant("consentDeclineConfirmOpen = true;",
                 "consentDeclineConfirmOpen = true; "
                 "typeof(ConsentSetting).GetMethod(\"Set\").Invoke(null, new object[] { false });"),
         "the Decline button writes the consent row")


def test_control_a_draw_after_the_consent_modal_is_caught():
    _red(_mutant("            DrawConsentModal();\n        }",
                 "            DrawConsentModal();\n            DrawLeaverBanner();\n        }"),
         "not the last statement of DrawUI")
