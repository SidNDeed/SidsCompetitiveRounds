"""Item 17 fix pass 2 (round-2 findings M1, M2, M3): the production wiring
of the mechanisms the harness executes. The decisions themselves run in
tools/client-rules-harness (the keybinds suite's T1 cases 25-29 and the
keybindfix2 suite, which also runs on the reviewed pin); these gates assert
that the plugin feeds them and acts on them.

Every decision is taken on `_cs_structure`'s mask or comment strip and
scoped to a span resolved by signature, never file-wide and never by line
number (#432/#330).
"""
from __future__ import annotations

import functools
import re
from pathlib import Path

import _cs_structure

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PLUGIN = REPO / "plugin"
KB = PLUGIN / "Keybinds.cs"
RULES = PLUGIN / "KeybindRules.cs"


@functools.lru_cache(maxsize=None)
def _src(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@functools.lru_cache(maxsize=64)
def _mask(src: str) -> str:
    return _cs_structure.mask_code(src)


@functools.lru_cache(maxsize=64)
def _strip(src: str) -> str:
    return _cs_structure.strip_comments_only(src)


def _span(src: str, signature: str):
    """The one block that follows `signature` in the mask."""
    masked = _mask(src)
    spans, search = [], 0
    while True:
        start = masked.find(signature, search)
        if start == -1:
            break
        open_brace = masked.find("{", start + len(signature))
        assert open_brace != -1, signature
        depth, end = 0, None
        for i in range(open_brace, len(masked)):
            if masked[i] == "{":
                depth += 1
            elif masked[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        assert end is not None, "unbalanced after %r" % signature
        spans.append((open_brace, end))
        search = end
    assert len(spans) == 1, "%r resolved to %d bodies" % (signature, len(spans))
    return spans[0]


def _code(src: str, signature: str) -> str:
    a, b = _span(src, signature)
    return _mask(src)[a:b]


def _text(src: str, signature: str) -> str:
    a, b = _span(src, signature)
    return _strip(src)[a:b]


def _ws(s: str) -> str:
    return re.sub(r"\s+", " ", s)


# -- M1 (round-2 F2; round-3 F2, fix pass 3): the independent keyboard ------
# channel. Fix pass 3 replaced the once-a-frame GetKeyboardState latch by an
# event accumulator: the platform's key-down messages are counted as they are
# delivered and drained once a frame. The attribution itself is executed by
# the harness (keybindfix3 suite); these gates assert the production feed.

ATTR3 = "internal static EdgeAttribution Attribute(IFrameInput io, int[] alias, int[] scan)"
ATTR4 = "internal static EdgeAttribution Attribute(IFrameInput io, int[] alias, int[] scan, out int namedKeyboard)"


def test_m1_the_frame_source_carries_the_independent_keyboard_channel():
    body = _ws(_text(_src(RULES), "internal interface IFrameInput"))
    assert "int KeyboardEdges();" in body


def test_m1_the_attribution_reads_the_source_before_its_early_return():
    src = _src(RULES)
    # fix pass 3 keeps the three-argument form as a wrapper of the form that
    # also returns the named-key count; the attribution is the body with the read
    body = _ws(_text(src, ATTR4 if ATTR4 in _mask(src) else ATTR3))
    assert body.count("io.KeyboardEdges()") == 1
    read = body.index("io.KeyboardEdges()")
    early = re.search(r"if \(!any && !typed && kb <= 0\) (\{ namedKeyboard = named; )?return a;", body)
    assert early is not None
    assert read < early.start()
    # the comparison is independent of the mouse: no Mouse term on its line
    assert "if (kb > named) a |= EdgeAttribution.Unknown;" in body
    assert "if (kb < 0 && (a & EdgeAttribution.Mouse) != 0) a |= EdgeAttribution.Unknown;" in body
    # every keyboard KeyCode the scan names is counted, the alias's included
    assert body.count("if (IsKeyboardCode(c)) named++;") == 2


def test_m1_the_real_input_reads_the_event_accumulator():
    body = _ws(_text(_src(KB), "private sealed class RealInput : IFrameInput"))
    assert "public int KeyboardEdges() { return KeyboardEvents.EdgesThisFrame(); }" in body


_STATE_READS = ("GetKeyboardState", "GetAsyncKeyState", "GetKeyState")


def test_m1_the_keyboard_channel_is_an_event_accumulator_never_a_key_state_snapshot():
    # no read of key STATE anywhere in the keybind code: a once-a-frame copy
    # of key state cannot show a key that went down and up between two copies,
    # and its low bit is meaningless for a non-toggle key (round 3, F2)
    for path in (KB, RULES):
        code = _strip(_src(path))
        for api in _STATE_READS:
            assert re.search(r"\b%s\b" % api, code) is None, "%s reads key state (%s)" % (path.name, api)
    acc = _ws(_text(_src(RULES), "internal sealed class KeyEventAccumulator"))
    # a press is counted from the key-down message, once; an auto-repeat is no edge
    down = _ws(_text(_src(RULES), "internal void KeyDown(int vk, bool repeat)"))
    assert down.index("if (repeat) return;") < down.index("pending++;")
    assert down.count("pending++;") == 1
    up = _ws(_text(_src(RULES), "internal void KeyUp(int vk)"))
    assert "pending" not in up
    # drained once a frame: a second read in the frame repeats the count
    drain = _ws(_text(_src(RULES), "internal int DrainForFrame(int frame)"))
    assert drain.index("if (unavailable) return -1;") < drain.index("if (frame == drainedFrame) return drained;")
    assert drain.index("if (frame == drainedFrame) return drained;") < drain.index("drained = pending;")
    assert drain.index("drained = pending;") < drain.index("pending = 0;")
    assert "byte[]" not in acc and "bool[]" not in acc
    # the production feed: the hook hands every removed key-down message to
    # the accumulator with its previous-key-state bit, every key-up as a release
    hook = _ws(_text(_src(KB), "private static IntPtr OnMessage(int code, IntPtr wParam, IntPtr lParam)"))
    assert "if (code == HC_ACTION && wParam.ToInt64() == PM_REMOVE && lParam != IntPtr.Zero)" in hook
    assert ("if (msg == WM_KEYDOWN || msg == WM_SYSKEYDOWN) Accumulator.KeyDown(vk, (flags & 0x40000000L) != 0);"
            " else Accumulator.KeyUp(vk);") in hook
    edges = _ws(_text(_src(KB), "internal static int EdgesThisFrame()"))
    assert edges.count("Accumulator.DrainForFrame(f)") == 1
    inst = _ws(_text(_src(KB), "private static void EnsureInstalled()"))
    assert "hook = SetWindowsHookEx(WH_GETMESSAGE, proc, IntPtr.Zero, GetCurrentThreadId());" in inst
    cls = _ws(_text(_src(KB), "internal static class KeyboardEvents"))
    assert "private const int WH_GETMESSAGE = 3, HC_ACTION = 0, PM_REMOVE = 1;" in cls
    assert "private const int WM_KEYDOWN = 0x0100, WM_KEYUP = 0x0101, WM_SYSKEYDOWN = 0x0104, WM_SYSKEYUP = 0x0105;" in cls


def test_m1_the_hook_only_counts_and_always_passes_the_message_on():
    hook = _ws(_code(_src(KB), "private static IntPtr OnMessage(int code, IntPtr wParam, IntPtr lParam)"))
    # one return, the next hook's answer: the message is never consumed or changed
    assert hook.count("return ") == 1
    assert hook.rstrip(" }").endswith("return CallNextHookEx(hook, code, wParam, lParam);")
    assert "Marshal.Write" not in hook


def test_m1_a_source_that_cannot_be_read_or_stays_silent_is_conservative():
    inst = _ws(_code(_src(KB), "private static void EnsureInstalled()"))
    # an install that fails or throws makes the source unavailable (-1)
    assert inst.count("Accumulator.MarkUnavailable();") == 2
    acc_cor = _ws(_code(_src(RULES), "internal void Corroborate(int namedKeyboard)"))
    assert "if (unavailable || EverDelivered || namedKeyboard <= 0) return;" in acc_cor
    assert "if (++silentFrames >= 2) unavailable = true;" in acc_cor


def test_m1_the_chat_tap_drains_the_accumulator_on_every_call():
    body = _code(_src(KB), "internal static bool ChatChannelTapped(bool chatInputOpen)")
    first = body.index("KeyboardEvents.EdgesThisFrame();")
    assert first < body.index("if (CaptureOwnsInput)")
    assert first < body.index("if (!chatInputOpen)")
    # the liveness check reads the step's own evidence, after the step
    step = body.index("chatTap.Step(realInput, KeyCodesFor(ChatChannel), FullKeyScan())")
    assert step < body.index("KeyboardEvents.Corroborate(chatTap.LastNamedKeyboard);")


# -- M2 (round-2 F4; round-3 F3, fix pass 3): built help surfaces repaint ----
# after a binding revision, and a revision is marked painted only after its
# repaint completed. The gate's decisions (stamp after the render, a throw
# stays due, blank, log once) are executed by the harness (keybindfix3 suite);
# these assert the production order.

NUI = PLUGIN / "NativeUI.cs"
NUIS = PLUGIN / "NativeUI.Settings.cs"
NUIK = PLUGIN / "NativeUI.Keybinds.cs"
REPAINT = "internal bool Repaint(int revision, Action render, Action blank, Action<string> log)"


def _call_args(body: str, call: str) -> str:
    """The argument text of the one `call(` in body, by parenthesis depth."""
    assert body.count(call) == 1, (call, body.count(call))
    a = body.index(call) + len(call)
    depth = 1
    for i in range(a, len(body)):
        if body[i] == "(":
            depth += 1
        elif body[i] == ")":
            depth -= 1
            if depth == 0:
                return body[a:i]
    raise AssertionError("unbalanced %s" % call)


def test_m2_the_article_revision_is_stamped_only_after_the_render_completes():
    # round 3, F3: a revision stamped before the render is red here
    body = _ws(_code(_src(NUI), "private static void SelectInfoArticle(string key)"))
    assert "infoKbGate.Painted(" not in body
    args = _call_args(body, "infoKbGate.Repaint(")
    # the title, the body text and the keyboard guide are the gate's render
    for step in ("UIFactory.SetTextRaw(infoTitleTxt, art.Title());", "RenderInfoBody(art);", "KbBlankInfoArticle"):
        assert step in args, step
    gate = _ws(_code(_src(RULES), REPAINT))
    assert gate.count("Painted(revision);") == 1
    assert gate.index("render();") < gate.index("catch (Exception e)") < gate.index("return false;") \
        < gate.index("Painted(revision);")


def test_m2_a_repaint_that_threw_stays_due_shows_nothing_and_logs_once():
    gate = _ws(_code(_src(RULES), REPAINT))
    catch = gate[gate.index("catch (Exception e)"):gate.index("return false;")]
    assert "failed = true;" in catch and "blank();" in catch
    assert "logged.Add(what)" in catch
    assert "(failed || (painted && paintedAt != revision))" in _ws(_code(_src(RULES), "internal bool Due(int revision)"))
    assert "failed = false;" in _ws(_code(_src(RULES), "internal void Painted(int revision)"))
    blank = _ws(_text(_src(NUIK), "private static void KbBlankInfoArticle()"))
    for step in ('UIFactory.SetTextRaw(infoBodyTxt, "");', 'UIFactory.SetTextRaw(infoTitleTxt, "");',
                 "UnityEngine.Object.Destroy(g);", "infoBodyExtraGOs.Clear();"):
        assert step in blank, step


def test_m2_returning_to_the_info_tab_repaints_before_it_is_shown():
    body = re.sub(r"\s+", "", _code(_src(NUI), "private static void SwitchTab(int idx)"))
    shown = body.index("tabPanels[i].SetActive(i==idx);")
    repaint = body.index("if(idx==TAB_INFO){try{KbRepaintInfoIfDue();}")
    assert shown < repaint


def test_m2_the_info_tab_repaints_while_it_is_up():
    body = _ws(_code(_src(NUI), "public static void Tick()"))
    assert "if (currentTab == TAB_INFO) { try { KbRepaintInfoIfDue(); }" in body


def test_m2_a_due_revision_rerenders_the_selected_article():
    body = _ws(_code(_src(NUIK), "private static void KbRepaintInfoIfDue()"))
    assert body.index("if (!infoKbGate.Due(Keybinds.Revision)) return;") < body.index("SelectInfoArticle(key);")
    assert "string key = infoSelectedKey;" in body


def test_m2_the_language_note_repaints_before_it_is_shown():
    show = _code(_src(NUIS), "private static void SettingsShowExtras(string key)")
    assert show.index("KbRepaintLangNoteIfDue();") < show.index("SettingsSetActive(setExtraLangNote")
    # fix pass 3: built empty, then painted through the gate - the revision is
    # stamped only after the text is set, at the build and at every repaint
    build = _ws(_text(_src(NUI), "private static void BuildSettingsPaneTexts(Transform extras)"))
    assert "setLangNoteGate.Painted(" not in build
    assert build.index('var note = UIFactory.CreateText("SLangChatNote", extras, "",') < build.index("setLangNoteTxt = note;")
    assert "UIFactory.SetTextRaw(note, LangChatNoteText())" in _call_args(build, "setLangNoteGate.Repaint(")
    rep = _ws(_text(_src(NUIK), "private static void KbRepaintLangNoteIfDue()"))
    assert "if (setLangNoteTxt == null || !setLangNoteGate.Due(Keybinds.Revision)) return;" in rep
    assert "setLangNoteGate.Painted(" not in rep
    assert "UIFactory.SetTextRaw(setLangNoteTxt, LangChatNoteText())" in _call_args(rep, "setLangNoteGate.Repaint(")


# -- M3 (round-2 F6): success only when every store agrees ---------------------
# The decision (pre-check, read-backs, verified rollback) is KeybindRules.Commit,
# executed by the harness (T1 cases 21 and 27-29, and the keybindfix2 suite's
# M3 cases). These assert the live store feeds it truthfully and that the one
# writer tells the player what is true for each outcome.

CAT = PLUGIN / "I18nCatalogues.cs"
NOT_SAVED = "That control could not be saved to your settings, so nothing was changed."
RESTORE_UNVERIFIED = ("That change could not be applied, and some controls could not be put back as "
                      "they were. Restart the game before you play.")


def _unescape(s: str) -> str:
    return re.sub(r'\\(u[0-9a-fA-F]{4}|.)',
                  lambda m: chr(int(m.group(1)[1:], 16)) if m.group(1).startswith("u") else
                  {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}.get(m.group(1), m.group(1)), s)


def _catalogue_blocks():
    parts = _src(CAT).split("private static readonly Dictionary<string, string> ")[1:]
    assert [p[:2] for p in parts] == ["ES", "RU", "UK", "SV"]
    out = {}
    for p in parts:
        out[p[:2]] = {_unescape(m.group(1)): _unescape(m.group(2)) for m in re.finditer(
            r'^            \["((?:[^"\\]|\\.)*)"\] = "((?:[^"\\]|\\.)*)",\r?$', p, re.M)}
    return out


def _segment(body: str, start: str, ends) -> str:
    a = body.index(start)
    b = min([body.index(e, a + len(start)) for e in ends if e in body[a + len(start):]] or [len(body)])
    return body[a:b]


def test_m3_the_live_store_has_no_silent_write():
    store = _ws(_text(_src(KB), "private sealed class LiveStore : IBindStore"))
    assert "public string ReadEntry(int row) { return entries[row] != null ? entries[row].Value : null; }" in store
    write = _ws(_text(_src(KB), "public void WriteEntry(int row, string token)"))
    # a row without an entry throws; the value is set only past that check
    assert write.index('if (entries[row] == null) throw new InvalidOperationException("no config entry for "') \
        < write.index("entries[row].Value = token;")
    assert "public string VerifyLive(BindSource[] b) { return VerifyAllLiveSets(b); }" in store


def test_m3_every_applied_action_is_read_back():
    src = _src(KB)
    applied = re.findall(r"ApplyAction\(set\.(\w+), cfg\[(\w+)\]\)",
                         _code(src, "private static void ApplyGameBindings(PlayerActions set, BindSource[] cfg, MappingState st)"))
    verified = re.findall(r"VerifyAction\(s\.(\w+), cfg\[(\w+)\], (\w+)\)",
                          _code(src, "internal static string VerifyAllLiveSets(BindSource[] cfg)"))
    assert len(applied) == 7
    assert sorted(applied) == sorted((a, c) for a, c, _ in verified)
    assert all(c == r for _, c, r in verified), verified


def test_m3_the_read_back_asks_inputcontrol_whether_each_source_is_bound():
    body = _ws(_code(_src(KB), "private static string VerifyAction(PlayerAction a, BindSource want, int row)"))
    assert "var desired = MakeSource(want);" in body
    assert "if (desired != null && !a.HasBinding(desired))" in body
    assert "foreach (var b in a.UnfilteredBindings)" in body
    assert "if (!(b is KeyBindingSource) && !(b is MouseBindingSource)) continue;" in body
    assert "if (desired != null && b.Equals(desired)) continue;" in body
    assert "if (a.HasBinding(b)) return" in body
    verify = _ws(_code(_src(KB), "internal static string VerifyAllLiveSets(BindSource[] cfg)"))
    assert "if (!live.Ready) return null;" in verify


def test_m3_the_one_writer_tells_what_is_true_for_each_outcome():
    rules = _ws(_code(_src(RULES), "internal enum CommitOutcome"))
    # the default branch below is Partial only while the outcome has four values
    assert rules.strip() == "{ Committed, Refused, RolledBack, Partial }", rules
    body = _ws(_code(_src(KB), "private static Refusal CommitRows(int[] rows, BindSource[] values, string via)"))
    assert body.count("KeybindRules.Commit(bound, rows, values, liveStore, out failure, out notRestored);") == 1
    stops = ("case CommitOutcome.", "default:")
    refused = _segment(body, "case CommitOutcome.Refused:", stops)
    assert "NativeUI.KeybindNotSavedText()" in refused and "return Refusal.NotSaved;" in refused
    rolled = _segment(body, "case CommitOutcome.RolledBack:", stops)
    assert "NativeUI.KeybindApplyFailedText()" in rolled and "return Refusal.ApplyFailed;" in rolled
    partial = _segment(body, "default:", ("foreach (int r in rows)",))
    assert "NativeUI.KeybindRestoreUnverifiedText()" in partial and "return Refusal.RestoreUnverified;" in partial
    assert "case CommitOutcome.Committed: break;" in body
    tail = body[body.index("foreach (int r in rows)"):]
    assert "announceOwed[r] = true;" in tail and tail.rstrip(" }").endswith("return Refusal.None;")


def test_m3_the_pane_names_each_new_refusal():
    body = _ws(_code(_src(NUIK), "private static string KeybindRefusalText(Refusal r)"))
    assert "case Refusal.NotSaved: return KeybindNotSavedText();" in body
    assert "case Refusal.RestoreUnverified: return KeybindRestoreUnverifiedText();" in body


def test_m3_the_new_outcomes_are_told_in_every_locale():
    blocks = _catalogue_blocks()
    for key, sig in ((NOT_SAVED, "internal static string KeybindNotSavedText()"),
                     (RESTORE_UNVERIFIED, "internal static string KeybindRestoreUnverifiedText()")):
        assert ('I18n.Tr("%s")' % key) in _text(_src(NUIK), sig), sig
        for loc in ("ES", "RU", "UK", "SV"):
            assert blocks[loc].get(key), (loc, key)
            assert blocks[loc][key] != key, (loc, key)
