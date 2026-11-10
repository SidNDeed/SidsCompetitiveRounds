"""Ask 14 (the player report form): the design note's claims over the plugin's
C# sources, each pinned to the code term it names.

Same family as test_admin_menu.py (ask 15) and test_avatar_preset_picker.py
(ask 5). Every claim is a function over the sources that raises AssertionError
when the claim is false, and runs three ways: against the tree (must pass),
against an in-memory MUTATION of the tree (must red) and against an in-memory
negative CONTROL edit (must stay green). Every scope is a brace-balanced span,
never the whole file, unless the claim is a census over a file or the tree.

What a press may send and what each answer closes are EXECUTED, not read: the
client rules harness suite "playerreport", pinned case by case in
test_client_rules_harness.py. This file pins what only the Unity side can get
wrong: that the form draws through the rules and asks them before every
request, that nothing is sent except by the one press the rules allowed, that
another person's text is never drawn as rich text, that every word goes through
I18n, and that the mark which tells one sign-in from another stays in memory.
"""
import bisect
import io
import json
import os
import re
import struct
from pathlib import Path

from _cs_structure import CsParseError, mask_code, strip_comments_only

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
PLUGIN = Path(REPO) / "plugin"
BS = chr(92)

NU = "NativeUI.cs"
CU = "CompetitiveUI.cs"
PL = "Plugin.cs"
AC = "ApiClient.cs"
RL = "PlayerReportRules.cs"
UI = "PlayerReportUI.cs"
AR = "AdminMenuRules.cs"
CAT = "I18nCatalogues.cs"
GEN = "I18nSourceKeys.g.cs"
# Files outside plugin/*.cs, keyed by their repo-relative path.
PROJ = "plugin/CompetitiveRounds.csproj"
EXTRACT = "tools/i18n_extract.py"
SOURCE_JSON = "tools/i18n_source.json"
MAIN = "tools/client-rules-harness/Main.cs"
CSPROJ = "tools/client-rules-harness/client-rules-harness.csproj"
SELFTEST = "tools/client-rules-harness/PlayerReportRulesSelfTest.cs"
EXTRA = (PROJ, EXTRACT, SOURCE_JSON, MAIN, CSPROJ, SELFTEST)

_CACHE = {}


def _tree():
    if not _CACHE:
        for p in sorted(PLUGIN.glob("*.cs")):
            with io.open(str(p), encoding="utf-8") as fh:
                _CACHE[p.name] = fh.read()
        for rel in EXTRA:
            with io.open(os.path.join(REPO, rel), encoding="utf-8") as fh:
                _CACHE[rel] = fh.read()
    return dict(_CACHE)


# -- span helpers (test_admin_menu.py's, kept to this file as that file keeps its own) --

_MASK = {}
_STRIP = {}


def _memo(cache, fn, text):
    """Memoise only the tree's own file texts (identity, not equality):
    mutated copies and spans are computed fresh and never retained."""
    if not any(text is t for t in _CACHE.values()):
        return fn(text)
    k = id(text)
    if k not in cache:
        cache[k] = fn(text)
    return cache[k]


def _masked(text):
    return _memo(_MASK, mask_code, text)


def _one(text, sig, base=0, raw=False):
    """The single brace-balanced block after `sig`, over the masked text. With
    `raw` the signature is sought in the raw text (for one whose identity is a
    string literal, which the mask blanks); the braces are balanced masked."""
    masked = _masked(text)
    hay = text if raw else masked
    spans, search = [], 0
    while True:
        start = hay.find(sig, search)
        if start == -1:
            break
        ob = masked.find("{", start + len(sig))
        if ob == -1:
            raise CsParseError("no block opens after %r" % sig)
        depth, end = 0, None
        for i in range(ob, len(masked)):
            if masked[i] == "{":
                depth += 1
            elif masked[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end is None:
            raise CsParseError("unbalanced braces after %r" % sig)
        spans.append((ob, end))
        search = end
    assert len(spans) == 1, "%d blocks match %r" % (len(spans), sig)
    a, b = spans[0]
    return base + a, base + b


def _span(text, sig, within=None, raw=False):
    if within is None:
        return _one(text, sig, raw=raw)
    a, b = _one(text, within)
    return _one(text[a:b], sig, base=a, raw=raw)


def _raw(text, sig, within=None):
    a, b = _span(text, sig, within)
    return text[a:b]


def _body(text, sig, within=None):
    return _code(_raw(text, sig, within))


def _code(text):
    return _memo(_STRIP, strip_comments_only, text)


def _fold(text):
    return re.sub(r"\s+", " ", text).strip()


def _lines(code):
    """The non-empty lines of a stretch of code, each without its indent."""
    return [l.strip() for l in code.splitlines() if l.strip()]


def _call_args(text, open_idx):
    """The top-level arguments of the call whose '(' is at open_idx, raw text
    kept; strings, chars and comments are opaque, brackets track depth."""
    assert text[open_idx] == "(", text[open_idx:open_idx + 20]
    i, depth, args, cur, n = open_idx + 1, 1, [], [], len(text)
    while i < n:
        c = text[i]
        if c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                if text[j] == BS:
                    j += 1
                j += 1
            cur.append(text[i:j + 1])
            i = j + 1
            continue
        if c == "'":
            j = i + 1
            if j < n and text[j] == BS:
                j += 1
            j += 1
            cur.append(text[i:j + 1])
            i = j + 1
            continue
        if text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j == -1 else j
            cur.append(text[i:j])
            i = j
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i) + 2
            cur.append(text[i:j])
            i = j
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                args.append("".join(cur))
                return args
        if c == "," and depth == 1:
            args.append("".join(cur))
            cur = []
            i += 1
            continue
        cur.append(c)
        i += 1
    raise CsParseError("unterminated call at %d" % open_idx)


def _calls(text, name):
    """Every call `name(...)` in `text` (raw), as argument lists, in source order."""
    out, search = [], 0
    while True:
        at = text.find(name + "(", search)
        if at == -1:
            return out
        out.append(_call_args(text, at + len(name)))
        search = at + len(name)


def _literals(text):
    """Every string literal of a C# text as (index of its opening quote, its
    content). Comments and char literals are stepped over, so a quote inside
    either opens nothing. The lane's files hold no verbatim or interpolated
    string outside ApiClient.cs, of which only the arguments of log calls are
    scanned with this (R16), and those are plain literals."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j == -1 else j
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i)
            i = n if j == -1 else j + 2
            continue
        if c == "'":
            j = i + 1
            if j < n and text[j] == BS:
                j += 1
            i = j + 2
            continue
        if c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                if text[j] == BS:
                    j += 1
                j += 1
            out.append((i, text[i + 1:j]))
            i = j + 1
            continue
        i += 1
    return out


def _is_tr_argument(text, at):
    before = text[max(0, at - 10):at]
    return before.endswith("I18n.Tr(") or before.endswith("I18n.TrF(")


def _tr_keys(text):
    """The literals handed straight to I18n.Tr or I18n.TrF: the keys a file draws."""
    return set(lit for at, lit in _literals(text) if _is_tr_argument(text, at))


def _untranslated(text):
    """The literals a reader could take for words (a letter, and a capital or
    a space) that are NOT the argument of I18n.Tr or I18n.TrF."""
    out = set()
    for at, lit in _literals(text):
        if re.search("[A-Za-z]", lit) and re.search("[A-Z ]", lit) and not _is_tr_argument(text, at):
            out.add(lit)
    return out


def _sites(src, needle):
    """Where `needle` stands in the plugin's code (comments stripped), as
    {file: count}: a census over every plugin/*.cs."""
    out = {}
    for name, text in src.items():
        if "/" in name or not name.endswith(".cs") or needle not in text:
            continue
        n = _code(text).count(needle)
        if n:
            out[name] = n
    return out


# -- edit helpers (mutations and controls) ---------------------------------

def _replace(src, fname, old, new):
    s = dict(src)
    t = s[fname]
    assert t.count(old) == 1, "edit anchor %r occurs %d times in %s" % (old, t.count(old), fname)
    s[fname] = t.replace(old, new, 1)
    assert s[fname] != t
    return s


def _replace_within(src, fname, sig, old, new, within=None):
    """`_replace`, but the anchor is sought only inside the block after `sig`."""
    s = dict(src)
    t = s[fname]
    a, b = _span(t, sig, within)
    block = t[a:b]
    assert block.count(old) == 1, "edit anchor %r occurs %d times inside %r in %s" % (old, block.count(old), sig, fname)
    s[fname] = t[:a] + block.replace(old, new, 1) + t[b:]
    assert s[fname] != t
    return s


def _insert_after_open(src, fname, sig, text, within=None, raw=False):
    """Insert `text` right after the opening brace of the block after `sig`."""
    s = dict(src)
    t = s[fname]
    a, _ = _span(t, sig, within, raw=raw)
    s[fname] = t[:a + 1] + "\n" + text + "\n" + t[a + 1:]
    return s


def _check(claim, mutation, control):
    """The three-way run. A parse failure never counts as the mutation's red."""
    src = _tree()
    claim(src)
    m = mutation(src)
    assert m != src, "the mutation changed nothing"
    try:
        claim(m)
    except CsParseError as e:
        raise AssertionError("the mutation broke parsing instead of the claim: %s" % e)
    except AssertionError:
        pass
    else:
        raise AssertionError("the mutation STAYED GREEN")
    c = control(src)
    assert c != src, "the control changed nothing"
    claim(c)


def _control_comment(fname, sig, within=None, indent="            "):
    return lambda s: _insert_after_open(s, fname, sig, indent + "// control", within)


# -- the spans the claims scope on -----------------------------------------

# NativeUI.cs
STRIP = "private static void BuildUtilityStrip(Transform titleRow)"
PLACE = "private static void PlaceUtilIcon(GameObject go, float right)"
ON_BUG = "private static void OnBugIcon()"
ON_REPORT = "private static void OnReportIcon()"
BUILD = "private static GameObject BuildAdminTab(Transform parent)"
BADGE = "private static void BuildPlayerReportBadge(GameObject launcher)"
SET_BADGE = "internal static void SetPlayerReportBadge(int open)"
REFRESH_ADMIN = "private static void RefreshAdmin()"
# PlayerReportUI.cs
OPEN = "internal static void Open()"
STYLES = "private static void EnsureStyles()"
DRAW = "internal static void Draw()"
SEND = "private static void Send()"
PUMP = "internal static void Pump()"
FINISH = "private static void Finish(int status, string code, bool logStored, string carried = null)"
ADMIN_ANSWERED = "private static void AdminAnswered(int status, string code)"
LOAD_ADMIN = "private static void LoadAdmin("
COUNT = "internal static void RefreshOpenCount()"
CLOSE_REPORT = "private static void CloseReport(PlayerReportRules.Report r, string verdict)"
VIEW_LOG = "private static void ViewLog(PlayerReportRules.Report r)"
DRAW_ADMIN = "internal static void DrawAdmin()"
LINE = "private static float Line(float x, float y, float w, string label, string value)"
DETAIL = "private static void DrawDetail(PlayerReportRules.Report r, float x, float y, float w, float h, bool can)"
# PlayerReportRules.cs
CHECK = "internal static Block Check(FormState st, Game game, Other other, string reason, string details,"
APPLY = "internal static Outcome Apply(FormState st, int status, string code, bool logStored, Game game, Other other,"
BEFORE_LIST = "internal static ListState BeforeList(FormState st, string sessionKey)"
APPLY_LIST = "internal static ListState ApplyList(FormState st, int status, string code, string sessionKey)"
SIGN_IN_CLOSED = "internal static bool SignInClosed(FormState st, string sessionKey)"
CLOSE_SIGN_IN = "private static void CloseSignIn(FormState st, string sessionKey)"
BUILD_BODY = "internal static string BuildBody(string kind, string gameId, string reportedSteamId, string reason,"
# ApiClient.cs
SUBMIT = "internal static void SubmitPlayerReportBody(byte[] body, string sensitiveProbe, Action<int, string, bool, string> done)"
FETCH_REPORTS = "internal static void FetchPlayerReports(string adminSteamId, string statusFilter, int limit,"
PARSE_REPORTS = "private static List<PlayerReportRules.Report> ParsePlayerReports(string json, out int leftOut)"
FETCH_LOG = "internal static void FetchPlayerReportLog(string adminSteamId, string reportId, Action<int, string, string> done)"
CLOSE = "internal static void ClosePlayerReport(string adminSteamId, string reportId, string verdict, string note,"
# AdminMenuRules.cs, I18nCatalogues.cs, the suite
LAUNCHERS_TABLE = "internal static readonly Launcher[] Launchers = new[]"
DECL = "private static readonly Dictionary<string, string> %s = new Dictionary<string, string>"
LOCALES = ("ES", "RU", "UK", "SV")
NEW_KEYS_DECL = "internal static readonly string[] NewKeys ="
SHARED_KEYS_DECL = "internal static readonly string[] SharedKeys ="
_STR = re.compile('"((?:[^"' + BS + BS + ']|' + BS + BS + '.)*)"')
_LAUNCHER = re.compile(r'new Launcher\(\s*"([^"]+)",\s*"([^"]+)",\s*Group\.(\w+),\s*(true|false)\s*\)')


# -- R1 four icons stand inside the strip's slot --------------------------------

def _r1(src):
    nu = _code(src[NU])
    size = re.findall(r"private const float UtilIconSize = (\d+)f;", nu)
    pitch = re.findall(r"private const float UtilIconPitch = (\d+)f;", nu)
    assert len(size) == 1 and len(pitch) == 1, (size, pitch)
    size, pitch = int(size[0]), int(pitch[0])
    strip = _body(src[NU], STRIP)
    slot = re.findall(r"UIFactory\.AddLE\(utilStripGO, prefW: (\d+), flexW: 0\);", strip)
    assert len(slot) == 1, slot
    icons = [tuple(_fold(a) for a in args[1:4]) for args in _calls(strip, "UIFactory.CreateIconButton")]
    assert icons == [('"UtilMusic"', '"ic_music.png"', "UtilIconSize"), ('"UtilMail"', '"ic_mail.png"', "UtilIconSize"),
                     ('"UtilBug"', '"ic_bug.png"', "UtilIconSize"),
                     ('"UtilReport"', '"ic_report.png"', "UtilIconSize")], icons
    places = [tuple(_fold(a) for a in args) for args in _calls(strip, "PlaceUtilIcon")]
    assert places == [("utilMailIconGO", "-14f"), ("utilBugIconGO", "-14f - UtilIconPitch"),
                      ("utilReportIconGO", "-14f - 2f * UtilIconPitch"),
                      ("utilMusicIconGO", "-14f - 3f * UtilIconPitch")], places
    assert pitch > size, "the icons would overlap: pitch %d, size %d" % (pitch, size)
    # From the strip's right edge: the inset, three pitches and the last
    # icon's own width. At 40 px that is the slot to the last pixel; the
    # 36 px fallback (one constant) leaves 4 px.
    assert 14 + 3 * pitch + size <= int(slot[0]), (pitch, size, slot)
    assert "rt.sizeDelta = new Vector2(UtilIconSize, UtilIconSize);" in _body(src[NU], PLACE)


def test_r1_four_icons_stand_inside_the_strips_slot():
    _check(_r1,
           lambda s: _replace(s, NU, "private const float UtilIconPitch = 47f;", "private const float UtilIconPitch = 48f;"),
           _control_comment(NU, STRIP))


# -- R2 the report icon opens the form by the bug icon's rule --------------------

GUARD = ["if (ClickHandler.ModalBlockInput && !UtilityPopupOpen) return;", "if (UtilityPopupOpen) CloseUtilityPopup();"]


def _r2(src):
    nu = src[NU]
    bug, rep = _lines(_body(nu, ON_BUG)), _lines(_body(nu, ON_REPORT))
    assert bug[1:3] == GUARD, bug[:4]
    assert rep == ["{"] + GUARD + ['Plugin.Log.LogInfo("[UTIL-STRIP] report icon -> player report form");',
                                   "PlayerReportUI.Open();", "}"], rep
    strip = _fold(_body(nu, STRIP))
    assert ("var reportClick = utilReportIconGO.GetComponent<ClickHandler>(); "
            "if (reportClick != null) reportClick.bypassModalBlock = true;") in strip
    # The form opens from this handler and from nowhere else in the plugin.
    assert _sites(src, "PlayerReportUI.Open()") == {NU: 1}, _sites(src, "PlayerReportUI.Open()")


def test_r2_the_report_icon_opens_the_form_by_the_bug_icons_rule():
    _check(_r2,
           lambda s: _replace_within(s, NU, ON_REPORT, GUARD[0], "if (ClickHandler.ModalBlockInput) return;"),
           _control_comment(NU, ON_REPORT))


# -- R3 the form and the viewer are modals of the menu, drawn under their pickers --

def _r3(src):
    cu = _code(src[CU])
    m = re.search(r"private static bool BackdroplessModalOpen =>(.*?);", cu, re.S)
    assert m, "BackdroplessModalOpen not found"
    assert _fold(m.group(1)).endswith("|| PlayerReportUI.AnyOpen"), _fold(m.group(1))[-90:]
    ui = src[UI]
    assert "internal static bool AnyOpen { get { return _open || _adminOpen; } }" in _code(ui)
    folded = _fold(cu)
    assert ("DrawBugReportAdminViewer(); PlayerReportUI.Draw(); PlayerReportUI.DrawAdmin(); "
            "DrawLogViewerModal();") in folded
    assert folded.count("DrawLogViewerModal();") == 1 and folded.count("DrawArtistPicker();") == 1
    form, picker = folded.find("PlayerReportUI.DrawAdmin();"), folded.find("DrawArtistPicker();")
    assert 0 <= form < picker, "the list picker has to draw after the form: %r" % ((form, picker),)
    assert _sites(src, "PlayerReportUI.Draw()") == {CU: 1}, _sites(src, "PlayerReportUI.Draw()")
    assert _sites(src, "PlayerReportUI.DrawAdmin()") == {CU: 1}, _sites(src, "PlayerReportUI.DrawAdmin()")
    # Neither outlives the menu it belongs to.
    assert _lines(_body(ui, DRAW))[1:3] == ["if (!_open) return;", "if (!NativeUI.IsOpen) { _open = false; return; }"]
    assert _lines(_body(ui, DRAW_ADMIN))[1:3] == ["if (!_adminOpen) return;",
                                                  "if (!NativeUI.IsOpen) { _adminOpen = false; return; }"]


def test_r3_the_form_and_the_viewer_are_modals_of_the_menu():
    _check(_r3,
           lambda s: _replace(s, CU, "            || PlayerReportUI.AnyOpen;", "            ;"),
           lambda s: _replace(s, CU, "            PlayerReportUI.Draw();\n", "            PlayerReportUI.Draw();   // control\n"))


# -- R4 a covered form takes no press, and Send opens only when the rules say so --

_ENABLED = re.compile(r"GUI\.enabled = ([^;]+);")
_CONTROLS = ("GUI.Button", "GUI.TextArea", "GUI.TextField")
SEND_GATE = "!covered && loaded && block == PlayerReportRules.Block.None"


def _gates(body):
    """Each control drawn in `body`, in source order, with the GUI.enabled
    value that stands when it is drawn."""
    events = [(m.start(), "", _fold(m.group(1))) for m in _ENABLED.finditer(body)]
    for name in _CONTROLS:
        at = body.find(name + "(")
        while at != -1:
            events.append((at, name, ""))
            at = body.find(name + "(", at + 1)
    out, gate = [], "true"
    for at, name, value in sorted(events):
        if name:
            out.append((name, gate))
        else:
            gate = value
    return out


def _r4(src):
    draw = _body(src[UI], DRAW)
    folded = _fold(draw)
    for needle in ("bool covered = CompetitiveUI.ArtistPromptOpen || CompetitiveUI.LogViewerOpen;",
                   "if (!covered && ev != null && ev.type == EventType.KeyDown && ev.keyCode == KeyCode.Escape)",
                   "bool loaded = _list == PlayerReportRules.ListState.Loaded;",
                   "bool free = !covered && !_sending;",
                   "PlayerReportRules.Block block = PlayerReportRules.Check(_state, _game, _other, _reason, _details, "
                   "_withLog, _sending, key, out why);",
                   'I18n.Tr("Submit Report"), _buttonStyle)) Send();'):
        assert needle in folded, needle
    gates = _gates(draw)
    assert gates == [("GUI.Button", "free && loaded && _games.Count > 0"),       # the game
                     ("GUI.Button", "free && loaded && _game != null"),          # the player
                     ("GUI.Button", "free"),                                     # the reason
                     ("GUI.TextArea", "free"),                                   # what happened
                     ("GUI.Button", "free"),                                     # the log tick box
                     ("GUI.Button", "!covered"),                                 # the log preview
                     ("GUI.Button", "!covered"),                                 # Close
                     ("GUI.Button", SEND_GATE)], gates                           # Send
    # The viewer's own requests: every control that starts one is closed
    # while a request is out or after a refusal closed the viewer.
    admin = _fold(_body(src[UI], DRAW_ADMIN))
    assert "bool can = !_adminClosed && !_adminLoading && !_closing;" in admin
    assert _gates(_body(src[UI], DRAW_ADMIN)) == [("GUI.Button", "can")] * 3 + [("GUI.Button", "true")] * 2, \
        _gates(_body(src[UI], DRAW_ADMIN))


def test_r4_a_covered_form_takes_no_press_and_send_opens_only_by_the_rules():
    _check(_r4,
           lambda s: _replace_within(s, UI, DRAW, "GUI.enabled = %s;" % SEND_GATE, "GUI.enabled = !covered && loaded;"),
           _control_comment(UI, DRAW))


# -- R5 one press, one request ----------------------------------------------------

def _r5(src):
    ui = src[UI]
    send = _lines(_body(ui, SEND))
    assert send[1:7] == ["string key = SessionKeyNow();", "PlayerReportRules.Outcome why;",
                         "if (PlayerReportRules.Check(_state, _game, _other, _reason, _details, _withLog, _sending, key, out why)",
                         "!= PlayerReportRules.Block.None)", "return;",
                         "if (_job.Busy || _pending != null) return;"], send[1:7]
    callers = re.findall(r"(?<![\w.])Send\(\);", _code(ui))
    assert len(callers) == 1, "Send is called from %d places" % len(callers)
    assert _sites(src, "SubmitPlayerReportBody(") == {AC: 1, UI: 1}, _sites(src, "SubmitPlayerReportBody(")
    assert _sites(src, "FetchReportableGames(") == {AC: 1, UI: 1}, _sites(src, "FetchReportableGames(")
    assert "ApiClient.FetchReportableGames(" in _body(ui, OPEN)
    # The body goes out from the plugin's tick, after the size the server
    # reads at most, and the hand-over is the pump's last statement.
    pump = _fold(_body(ui, PUMP))
    refuse = pump.find('if (r.Body.Length > PlayerReportRules.BodyMax) { Finish(413, "body_too_large", false); return; }')
    post = pump.find("ApiClient.SubmitPlayerReportBody(r.Body, r.Probe, Finish); }")
    assert 0 <= refuse < post and post + len("ApiClient.SubmitPlayerReportBody(r.Body, r.Probe, Finish); }") == len(pump), \
        (refuse, post, len(pump))
    assert _sites(src, "PlayerReportUI.Pump()") == {PL: 1}, _sites(src, "PlayerReportUI.Pump()")
    assert "try { PlayerReportUI.Pump(); } catch { }" in _code(src[PL])
    # An answer, or none, ends the press before anything else happens.
    assert _lines(_body(ui, FINISH))[1:5] == ["Pending p = _pending;", "_pending = null;", "_sending = false;",
                                              "if (p == null) return;"], _lines(_body(ui, FINISH))[1:5]
    # The transport sends a body once: one coroutine, no loop around it.
    submit = _body(src[AC], SUBMIT)
    assert submit.count("StartCoroutine(") == 1 and submit.count("PostRequestRaw(") == 1, submit[:200]
    for loop in ("for (", "foreach (", "while ("):
        assert loop not in submit, loop


def test_r5_one_press_one_request():
    _check(_r5,
           lambda s: _replace_within(s, UI, FINISH, "if (p == null) return;", "if (p == null) return; if (status == 0) Send();"),
           _control_comment(UI, SEND))


# -- R6 the body is the rules', carries the bug form's log bundle, names no reporter --

def _r6(src):
    ui = src[UI]
    send = _fold(_body(ui, SEND))
    for needle in ("CompetitiveUI.LogBundleInputs inputs = withLog ? CompetitiveUI.CaptureLogBundleInputs() : null;",
                   "log = CompetitiveUI.ComposeLogBundle(inputs, info);",
                   "string body = PlayerReportRules.BuildBody(game.Kind, game.Id, other.SteamId, reason, details, log);",
                   "r.Body = System.Text.Encoding.UTF8.GetBytes(body);",
                   "r.Probe = ApiClient.SensitiveBodyProbe(body);"):
        assert needle in send, needle
    fields = re.findall(r'Field\(sb, "([a-z_]+)"', _body(src[RL], BUILD_BODY))
    assert fields == ["game_kind", "game_id", "reported_steam_id", "reason", "details", "log_text"], fields
    # Who reports is the session's to say: no part of the form's path reads
    # the local account's id.
    for sig in (OPEN, DRAW, SEND, PUMP, FINISH):
        body = _body(ui, sig)
        assert "LocalSteamId" not in body and "reporter" not in body.lower(), sig
    submit = _fold(_body(src[AC], SUBMIT))
    assert 'PostRequestRaw( $"{baseUrl}/api/v1/player-reports", body,' in submit, submit[:260]
    assert 'sensitiveProbe: sensitiveProbe ?? ""' in submit


def test_r6_the_body_is_the_rules_and_names_no_reporter():
    _check(_r6,
           lambda s: _replace_within(s, RL, BUILD_BODY, 'Field(sb, "reason", reason)', 'Field(sb, "reporter_steam_id", reason)'),
           _control_comment(RL, BUILD_BODY))


# -- R7 every word the lane writes goes through I18n -------------------------------

# What may stand outside I18n although it has a capital or a space: colours,
# formats, thread names, one log line and the tick box's mark.
NOT_WORDS = {
    UI: {"#88FF88", "#FFCC66", "<color=#AAAAAA>", "<color=#FFCC66>", "<color=#FFE580>", "HH:mm", "X",
         "SCR-PlayerReportBundle", "SCR-PlayerReportLog", "[PLAYER-REPORT] the report could not be built (", "no body"},
    RL: {"HTTP ", "yyyy-MM-dd'T'HH:mm:ss'Z'"},
}


def _r7(src):
    for f in (UI, RL):
        stray = _untranslated(src[f]) - NOT_WORDS[f]
        assert not stray, "%s holds text outside I18n: %r" % (f, sorted(stray))
        assert len(_tr_keys(src[f])) >= 20, "the scanner found %d keys in %s" % (len(_tr_keys(src[f])), f)


def test_r7_every_word_the_lane_writes_goes_through_i18n():
    _check(_r7,
           lambda s: _replace(s, UI, 'I18n.Tr("Preview logs")', '"Preview logs"'),
           _control_comment(UI, DRAW))


# -- R8 another person's text is never drawn as rich text --------------------------

PLAIN_STYLES = ("_plainStyle", "_areaStyle", "_selectStyle", "_fieldStyle", "_tickStyle", "_rowStyle", "_rowDimStyle",
                "_logStyle")
RICH_STYLES = ("_titleStyle", "_labelStyle", "_noteStyle", "_buttonStyle",
               '_adminFilter == "open" ? _pickedStyle : _buttonStyle',
               "_adminFilter.Length == 0 ? _pickedStyle : _buttonStyle")
_TR_CALL = re.compile(r"I18n\.Tr\(" + _STR.pattern + r"\)")
# What a rich style may draw, with T for I18n.Tr("...") and S for a literal:
# the mod's own words, and four values whose every source is pinned below.
OWN_SHAPES = ("T", "S + T + S", "_sending ? T : T", "_reason == PlayerReportRules.ReasonNeedsDetails ? T : T",
              "S + label + S", "S + note + S", "S + (good ? S : S) + S + line + S",
              "S + PlayerReportRules.VerdictQuestion(_confirm) + S")
_OWN_VALUE = re.compile(r'I18n\.Tr\("[^"]*"\)|""')


def _draws(code):
    """Every text the code draws, as (content, style): the second and the
    last argument of each IMGUI control call."""
    out = []
    for name in ("GUI.Label",) + _CONTROLS:
        for args in _calls(code, name):
            out.append((_fold(args[1]), _fold(args[-1])))
    return out


def _r8(src):
    ui = _code(src[UI])
    styles = _body(src[UI], STYLES)
    assert ui.count("richText") == styles.count("richText") and ".richText" not in ui, "a style's flag is set outside EnsureStyles"
    for name in PLAIN_STYLES:
        made = re.findall(r"%s = new GUIStyle\(([^)]*)\)\s*(\{[^}]*\})?;" % name, styles)
        assert len(made) == 1, (name, made)
        assert "richText = false" in made[0][1] or made[0][0] in PLAIN_STYLES, (name, made)
    stray = []
    for content, style in _draws(ui):
        if style in PLAIN_STYLES or (style, content) == ("GUIStyle.none", "GUIContent.none"):
            continue
        shape = _STR.sub("S", _TR_CALL.sub("T", content))
        if style not in RICH_STYLES or shape not in OWN_SHAPES:
            stray.append((content, style))
    assert not stray, "rich-text draws of text this claim does not know: %r" % stray
    # label: the detail pane's own captions.
    captions = [_fold(a[3]) for a in _calls(ui, "= Line")]
    assert len(captions) >= 7 and all(_OWN_VALUE.fullmatch(c) for c in captions), captions
    # note and line: what the rules said, and nothing a player wrote.
    assert re.findall(r"\bnote = ([^;]+);", ui) == ['_adminLoading ? I18n.Tr("Loading...") : _adminStatus'], \
        re.findall(r"\bnote = ([^;]+);", ui)
    assert re.findall(r"\bline = ([^;]+);", ui) == ["PlayerReportRules.ListText(_list, _state, _games.Count)", "_status",
                                                    "PlayerReportRules.BlockText(block, why)"], re.findall(r"\bline = ([^;]+);", ui)
    said = set(re.findall(r"\b_status = ([^;]+);", ui))
    assert said == {'""', "PlayerReportRules.AnswerText(said)"}, said
    told = set(re.findall(r"\b_adminStatus = ([^;]+);", ui))
    assert told == {'""', "said", "PlayerReportRules.AdminAnswerText(status, code)", 'I18n.Tr("Not allowed.")',
                    'I18n.Tr("Report closed.")'}, told
    assert set(re.findall(r"(?<![\w.])LoadAdmin\(([^)]*)\)", ui)) == {"", "_adminStatus", 'string said = ""'}


def test_r8_another_persons_text_is_never_drawn_as_rich_text():
    _check(_r8,
           lambda s: _replace(s, UI, "PlayerReportRules.ReportLine(r, When(r.CreatedAt)), _rowStyle);",
                              "PlayerReportRules.ReportLine(r, When(r.CreatedAt)), _labelStyle);"),
           _control_comment(UI, DRAW_ADMIN))


# -- R9 the mark that tells one sign-in from another stays in memory -----------------

# Every line of the rules file that names the mark (the state's set of
# refused marks or the parameter that carries it), in source order, with the
# function a body line stands in. One line READS the set (SignInClosed, which
# Check and BeforeList call) and one ADDS to it (CloseSignIn, which Apply and
# ApplyList call); the rest declare (ask 14 R2 H1).
MARK_RULES = (
    (None, "internal readonly HashSet<string> RefusedSignIns = new HashSet<string>(StringComparer.Ordinal);"),
    (None, SIGN_IN_CLOSED),
    (SIGN_IN_CLOSED, "return string.IsNullOrEmpty(sessionKey) || st.RefusedSignIns.Contains(sessionKey);"),
    (None, CLOSE_SIGN_IN),
    (CLOSE_SIGN_IN, "if (!string.IsNullOrEmpty(sessionKey)) st.RefusedSignIns.Add(sessionKey);"),
    (None, "bool withLog, bool sending, string sessionKey, out Outcome why)"),
    (CHECK, "if (SignInClosed(st, sessionKey)) { why = Outcome.SignIn; return Block.SignIn; }"),
    (None, "string reason, string details, bool withLog, string sessionKey)"),
    (APPLY, "case Closes.Auth: CloseSignIn(st, sessionKey); break;"),
    (None, BEFORE_LIST),
    (BEFORE_LIST, "if (SignInClosed(st, sessionKey)) return ListState.SignIn;"),
    (None, APPLY_LIST),
    (APPLY_LIST, "if (status == 401) { CloseSignIn(st, sessionKey); return ListState.SignIn; }"),
)
# Every line of the form that names the mark or the token it is made from, in
# source order: where it is made (from the token held now, and from the one a
# request carried, ask 14 R1 H1), the three places that make it fresh, the two
# answers that bring the carried token back, and the four rules it goes to.
MARK_UI = (
    "private static string SessionKeyNow()",
    "return MarkOf(ApiClient.SessionTokenToStamp());",
    "private static string MarkOf(string token)",
    "return PlayerReportRules.SessionKey(token);",
    "string key = SessionKeyNow();",                                                    # Open
    "_list = PlayerReportRules.BeforeList(_state, key);",
    "ApiClient.FetchReportableGames((status, code, games, remaining, carried) =>",
    "carried == null ? key : MarkOf(carried));",                                        # into ApplyList
    "string key = SessionKeyNow();",                                                    # Draw
    "_sending, key, out why);",
    "internal string Reason, Details, Key;",                                            # what a press was sent under
    "string key = SessionKeyNow();",                                                    # Send
    "if (PlayerReportRules.Check(_state, _game, _other, _reason, _details, _withLog, _sending, key, out why)",
    "_pending = new Pending { Game = game, Other = other, Reason = reason, Details = details, Key = key, WithLog = withLog };",
    "private static void Finish(int status, string code, bool logStored, string carried = null)",
    "carried == null ? p.Key : MarkOf(carried));",                                      # Finish, into Apply
)
_MARK_IN_RULES = re.compile(r"\b(sessionKey|RefusedSignIns)\b")
_MARK_IN_UI = re.compile(r"\b(key|Key|SessionKeyNow|SessionKey|SessionToken|sessionKey|RefusedSignIn|MarkOf|carried)\b")


def _r9(src):
    rl, ui = src[RL], src[UI]
    named = [l for l in _lines(_code(rl)) if _MARK_IN_RULES.search(l)]
    assert named == [l for _, l in MARK_RULES], named
    for sig, line in MARK_RULES:
        if sig is not None:
            assert line in _lines(_body(rl, sig)), (sig, line)
    # The set is the rules file's alone, and the rules file has no log
    # call, no file, no setting and no request to put it in.
    assert _sites(src, "RefusedSignIn") == {RL: 3}, _sites(src, "RefusedSignIn")
    for word in ("Plugin.", "System.IO", "File.", "Config", "PlayerPrefs", "UnityEngine", "ApiClient"):
        assert word not in _code(rl), "the rules file reaches %s" % word
    # The form: the mark is made from the token in one place, and every line
    # that holds it is one of these sixteen. None is a log call, a file, a
    # setting or a request, so it reaches none.
    got = [l for l in _lines(_code(ui)) if _MARK_IN_UI.search(l)]
    assert got == list(MARK_UI), got
    assert _sites(src, "PlayerReportRules.SessionKey(") == {UI: 1}, _sites(src, "PlayerReportRules.SessionKey(")
    assert _sites(src, "SessionKeyNow()") == {UI: 4}, _sites(src, "SessionKeyNow()")


def test_r9_the_sign_in_mark_stays_in_memory():
    _check(_r9,
           lambda s: _replace(s, UI, '            _status = "";\n            bool started',
                              '            Plugin.Log.LogInfo("k " + key);\n            _status = "";\n            bool started'),
           _control_comment(UI, SEND))


# -- R10 the admins' three requests ----------------------------------------------------

def _nospace(text):
    return re.sub(r"\s+", "", text)


CANON = "PlayerReportRules.AdminCanonical(adminSteamId,PlayerReportRules.%s)"
SIGNED = ((FETCH_REPORTS, CANON % "ActionList,PlayerReportRules.TargetList"),
          (FETCH_LOG, CANON % "ActionLog,reportId"),
          (CLOSE, CANON % "ActionClose,PlayerReportRules.CloseTarget(reportId,verdict)"))
ADMIN_CLOSES = "if (PlayerReportRules.AdminCloses(status)) _adminClosed = true;"


def _r10(src):
    ac, ui = src[AC], src[UI]
    # Each request is signed over its own action word, and the close's
    # signature names the report and the verdict.
    for sig, want in SIGNED:
        signs = _calls(_body(ac, sig), "ComputeAdminHmacHex")
        assert len(signs) == 1 and len(signs[0]) == 1, (sig, signs)
        assert _nospace(signs[0][0]) == want, (sig, signs[0][0])
    # A report's id reaches a URL only in the server's own form.
    assert "!PlayerReportRules.IsReportId(reportId)" in _body(ac, FETCH_LOG)
    assert "!PlayerReportRules.IsReportId(reportId)" in _body(ac, CLOSE)
    assert "!PlayerReportRules.IsVerdict(verdict)" in _body(ac, CLOSE)
    assert "if (!PlayerReportRules.IsReportId(r.Id)) { leftOut++; continue; }" in _body(ac, PARSE_REPORTS)
    # The viewer is the only caller, and each call stands behind the flag a
    # refusal sets.
    assert _sites(src, "FetchPlayerReports(") == {AC: 1, UI: 2}, _sites(src, "FetchPlayerReports(")
    assert _sites(src, "FetchPlayerReportLog(") == {AC: 1, UI: 1}, _sites(src, "FetchPlayerReportLog(")
    assert _sites(src, "ClosePlayerReport(") == {AC: 1, UI: 1}, _sites(src, "ClosePlayerReport(")
    assert _lines(_body(ui, LOAD_ADMIN))[1] == "if (_adminClosed || _adminLoading) return;"
    assert _lines(_body(ui, CLOSE_REPORT))[1] == "if (_adminClosed || _closing || r == null) return;"
    assert _lines(_body(ui, VIEW_LOG))[1] == "if (_adminClosed || _logLoading || r == null || !r.HasLog) return;"
    assert _lines(_body(ui, COUNT))[2] == ("if (!PlayerReportRules.MayAskCount(ApiClient.IsAdmin, _adminClosed, _countAsked, "
                                           "now, _countAskedAt)) return;"), _lines(_body(ui, COUNT))[:4]
    # Every answer goes through the rule that sets the flag.
    assert _code(ui).count("AdminAnswered(status, code);") == 3, _code(ui).count("AdminAnswered(status, code);")
    answered = _lines(_body(ui, ADMIN_ANSWERED))
    assert answered[1:3] == ["if (_adminClosed) return;", ADMIN_CLOSES], answered
    assert ADMIN_CLOSES in _lines(_body(ui, COUNT)), _lines(_body(ui, COUNT))
    assert _code(ui).count("_adminClosed = ") == 2, "the flag is written somewhere else"


def test_r10_the_admins_requests_are_signed_apart_and_stop_after_a_refusal():
    _check(_r10,
           lambda s: _replace_within(s, AC, FETCH_LOG, "PlayerReportRules.ActionLog", "PlayerReportRules.ActionList"),
           _control_comment(AC, FETCH_LOG))


# -- R11 a verdict is never one press ---------------------------------------------------

YES = 'if (GUI.Button(new Rect(x + w - 220, cy, 100, 26), I18n.Tr("Yes"), _buttonStyle)) CloseReport(r, _confirm);'


def _r11(src):
    ui = src[UI]
    callers = [l for l in _lines(_code(ui)) if "CloseReport(" in l]
    assert callers == [CLOSE_REPORT, YES], callers
    detail = _fold(_body(ui, DETAIL))
    ask = detail.find("if (_confirm.Length == 0) {")
    back = detail.find("GUI.enabled = true; return; }", ask)
    yes = detail.find("CloseReport(r, _confirm);")
    assert 0 <= ask < back < yes, "Yes is drawn while no verdict waits: %r" % ((ask, back, yes),)
    for needle in ('I18n.Tr("Dismiss"), _buttonStyle)) _confirm = "dismissed";',
                   'I18n.Tr("Mark Actioned"), _buttonStyle)) _confirm = "actioned";',
                   'GUI.enabled = can && r.Status == "open";',
                   "PlayerReportRules.VerdictQuestion(_confirm)"):
        assert needle in detail, needle
    # The viewer applies no sanction: closing a report is its only write.
    for other in ("Ban", "Mute", "Kick"):
        assert other not in _code(ui), other


def test_r11_a_verdict_is_never_one_press():
    _check(_r11,
           lambda s: _replace_within(s, UI, DETAIL, '_confirm = "dismissed";', 'CloseReport(r, "dismissed");'),
           _control_comment(UI, DETAIL))


# -- R12 the launcher, its badge and the one count read -----------------------------------

def _r12(src):
    nu = src[NU]
    rows = _LAUNCHER.findall(_body(src[AR], LAUNCHERS_TABLE))
    ids = [r[0] for r in rows]
    assert ("APlrRpt", "Player Reports...", "Queues", "false") in rows, rows
    assert "ABugRpt" in ids and ids.index("APlrRpt") == ids.index("ABugRpt") + 1, ids
    build = _fold(_body(nu, BUILD))
    assert 'BuildPlayerReportBadge(AdminLauncher(slots, "APlrRpt", () => PlayerReportUI.OpenAdmin()));' in build
    assert _sites(src, "PlayerReportUI.OpenAdmin()") == {NU: 1}, _sites(src, "PlayerReportUI.OpenAdmin()")
    # The count is an admin's read: asked after the tab's own admin gate,
    # from one place, and the rule decides whether it goes out (R10).
    refresh = _fold(_body(nu, REFRESH_ADMIN))
    gate, ask = refresh.find("if (!ApiClient.IsAdmin) return;"), refresh.find("PlayerReportUI.RefreshOpenCount();")
    assert 0 <= gate < ask, (gate, ask)
    assert _sites(src, "PlayerReportUI.RefreshOpenCount()") == {NU: 1}, _sites(src, "PlayerReportUI.RefreshOpenCount()")
    # The badge shows what the rule gives (digits, so no catalogue row), is
    # hidden when that is empty, belongs to the button and takes no click.
    shown = _fold(_body(nu, SET_BADGE))
    for needle in ("string t = PlayerReportRules.CountText(playerReportOpen);", "bool show = t.Length > 0;",
                   "if (playerReportBadgeGO.activeSelf != show) playerReportBadgeGO.SetActive(show);",
                   "if (show && playerReportBadgeTxt != null) UIFactory.SetTextRaw(playerReportBadgeTxt, t);"):
        assert needle in shown, needle
    badge = _fold(_body(nu, BADGE))
    for needle in ("badge.transform.SetParent(launcher.transform, false);",
                   'UIFactory.tImage.GetProperty("raycastTarget", bf)?.SetValue(bimg, false);',
                   "SetPlayerReportBadge(playerReportOpen);"):
        assert needle in badge, needle
    assert _sites(src, "SetPlayerReportBadge(") == {NU: 2, UI: 2}, _sites(src, "SetPlayerReportBadge(")


def test_r12_the_launcher_its_badge_and_the_one_count_read():
    gate = "            if (!ApiClient.IsAdmin) return;\n"
    _check(_r12,
           lambda s: _replace_within(s, NU, REFRESH_ADMIN, gate, "            PlayerReportUI.RefreshOpenCount();\n" + gate),
           _control_comment(NU, REFRESH_ADMIN))


# -- R13 the four catalogues carry every key the lane draws --------------------------------

def _lane_keys(src):
    return _tr_keys(src[RL]) | _tr_keys(src[UI]) | {"Player Reports..."}


def _r13(src):
    keys = sorted(_lane_keys(src))
    assert len(keys) >= 50, "the scanner found %d keys" % len(keys)
    missing = []
    for loc in LOCALES:
        block = _body(src[CAT], DECL % loc)
        missing += [(loc, k) for k in keys if '["%s"]' % k not in block]
    assert not missing, "catalogue rows missing: %r" % missing
    # The suite's two lists (it runs every key of the first through every
    # locale) are the rules file's own texts, no fewer and no more.
    new = set(_STR.findall(_body(src[SELFTEST], NEW_KEYS_DECL)))
    shared = set(_STR.findall(_body(src[SELFTEST], SHARED_KEYS_DECL)))
    assert new and shared and not (new & shared), sorted(new & shared)
    mine = _tr_keys(src[RL])
    assert new | shared == mine, "the suite's key lists against the rules file: %r" % sorted((new | shared) ^ mine)


def test_r13_the_four_catalogues_carry_every_key_the_lane_draws():
    _check(_r13,
           lambda s: _replace(s, CAT, '            ["Report a Player"] = "Reportar a un jugador",\n', ""),
           lambda s: _insert_after_open(s, CAT, DECL % "ES", "            // control"))


# -- R14 the extractor reads both files and the registries carry the keys ------------------

FILES_ROW = '"PlayerReportRules.cs", "PlayerReportUI.cs",'


def _r14(src):
    assert FILES_ROW in src[EXTRACT], "the two files are not in the extractor's FILES"
    strings = json.loads(src[SOURCE_JSON])["strings"]
    have = set(x if isinstance(x, str) else x.get("s", x.get("key", "")) for x in strings)
    want = _lane_keys(src)
    assert want <= have, "source strings missing: %r" % sorted(want - have)
    gone = [k for k in sorted(want) if '"%s",' % k not in src[GEN]]
    assert not gone, "I18nSourceKeys.g.cs lacks %r" % gone


def test_r14_the_extractor_reads_both_files_and_the_registries_carry_the_keys():
    _check(_r14,
           lambda s: _replace(s, EXTRACT, "    " + FILES_ROW + "\n", ""),
           lambda s: _replace(s, EXTRACT, "    " + FILES_ROW + "\n", "    " + FILES_ROW + "  # control\n"))


# -- R15 the suite is registered and compiled; the icon ships ---------------------------------

ICON_ROW = '    <EmbeddedResource Include="assets' + BS + 'ic_report.png" />\n'


def _r15(src):
    a, b = _span(src[MAIN], 'RunSuite("playerreport"', raw=True)
    main = _code(src[MAIN][a:b])
    assert "var r = PlayerReportRules.SelfTest();" in main
    assert "return new Suite(r.Passed + r.Failed, r.Failed, r.Report.ToString());" in main
    csproj = src[CSPROJ]
    assert '<Compile Include="../../plugin/PlayerReportRules.cs" />' in csproj
    assert '<Compile Include="PlayerReportRulesSelfTest.cs" />' in csproj
    assert "PlayerReportUI.cs" not in csproj, "the form needs Unity and is no rule file"
    st = _code(src[SELFTEST])
    assert "internal static SelfTestResult SelfTest()" in st
    assert "I18nCatalogues.Install();" in st
    assert ICON_ROW in src[PROJ], "ic_report.png is not an embedded resource"
    assert "PlayerReportRulesSelfTest" not in src[PROJ]


def test_r15_the_suite_is_registered_and_compiled_and_the_icon_ships():
    _check(_r15,
           lambda s: _replace(s, PROJ, ICON_ROW, ""),
           lambda s: _insert_after_open(s, MAIN, 'RunSuite("playerreport"', "                              // control", raw=True))


# -- R16 a list row left out is counted, and no log line of the admin calls carries an id ----

LEFT_OUT = "if (!PlayerReportRules.IsReportId(r.Id)) { leftOut++; continue; }"
LIST_LINE = ('Plugin.Log.LogInfo("[PLAYER-REPORT] the admin list: " + reports.Count + " rows, " + leftOut '
             '+ " left out for the form of the id");')
LOGGED_NAMES = re.compile(r"[.]Id|[bB]ody|[tT]ext|[rR]esp|[sS]team|[uU]rl|[jJ]son|[sS]ig|reportId|[nN]ote"
                          r"|Reporter|Reported|Details|[.]Message")


def _logged(body):
    """What each log call of a stretch of code is given, its string literals taken out."""
    out = []
    for kind in ("LogInfo", "LogWarning", "LogError", "LogDebug", "LogMessage"):
        for args in _calls(body, "Plugin.Log." + kind):
            said = ", ".join(args)
            for at, lit in sorted(_literals(said), reverse=True):
                said = said[:at] + said[at + len(lit) + 2:]
            out.append(_fold(said))
    return out


def _r16(src):
    ac = src[AC]
    parse, fetch = _body(ac, PARSE_REPORTS), _body(ac, FETCH_REPORTS)
    # The parser counts each row it leaves out, and counts nothing else.
    counted = [l for l in _lines(parse) if "leftOut" in l]
    assert counted == ["leftOut = 0;", LEFT_OUT], counted
    # One line per list read, after the parse and before the answer is handed on.
    lines = _lines(fetch)
    assert lines.count(LIST_LINE) == 1, [l for l in lines if "Plugin.Log" in l]
    at = lines.index(LIST_LINE)
    assert lines[at - 1] == 'if (reports == null) { done(0, "", null, 0); return; }', lines[at - 1]
    assert lines[at + 1] == 'done(200, "", reports, openTotal);', lines[at + 1]
    # No log call of the three admin requests or of the parser is given an
    # id, a Steam id, a signature, a URL, a note or the answer's text.
    said = []
    for sig in (FETCH_REPORTS, PARSE_REPORTS, FETCH_LOG, CLOSE):
        said += _logged(_raw(ac, sig))
    assert said, "no log call was read"
    assert not [x for x in said if LOGGED_NAMES.search(x)], said
    assert "+ reports.Count + + leftOut +" in said, said


def test_r16_a_list_row_left_out_is_counted_and_no_log_line_carries_an_id():
    _check(_r16,
           lambda s: _replace_within(s, AC, PARSE_REPORTS, "{ leftOut++; continue; }", "continue;"),
           _control_comment(AC, PARSE_REPORTS))


def _ihdr(name):
    with open(str(PLUGIN / "assets" / name), "rb") as fh:
        head = fh.read(29)
    assert head[:8] == b"\x89PNG\r\n\x1a\n" and head[12:16] == b"IHDR", name
    return struct.unpack(">IIBBBBB", head[16:29])   # width, height, depth, colour type, compression, filter, interlace


def test_the_report_icon_is_an_image_like_its_three_neighbours():
    """The strip tints its icons through the Image colour, so each is a
    white shape on a clear ground: 64x64, eight bits, RGBA."""
    want = _ihdr("ic_bug.png")
    assert want[:4] == (64, 64, 8, 6), want
    for name in ("ic_report.png", "ic_mail.png", "ic_music.png"):
        assert _ihdr(name) == want, (name, _ihdr(name))


# -- R17, R18 ask 14 R1's H1 and H2: the sign-in a refusal closes, and one attempt ----

GET_REQUEST = "private static IEnumerator GetRequest(string url, Action<bool, string> callback,"
POST_RAW = "private static IEnumerator PostRequestRaw(string url, byte[] bodyRaw,"
FETCH_GAMES = "internal static void FetchReportableGames(Action<int, string, List<PlayerReportRules.Game>, int, string> done)"
_CS_MEMBER = re.compile(r"^ {8}(?:internal|private|public|protected)\s+[^;{}]*?\b([A-Za-z_0-9]+)\s*\(")   # test_sept16's


def _owners(text, needle):
    """The member each code line holding `needle` stands in, in file order."""
    out, member = [], "<file scope>"
    for line in _code(text).split("\n"):
        m = _CS_MEMBER.match(line)
        if m:
            member = m.group(1)
        if needle in line:
            out.append(member)
    return out


def _r17(src):
    ac, ui = src[AC], src[UI]
    # Both transports tell their owner the token they stamped, after the
    # stamp and before the send, so a refresh in between is what they report.
    told = 'try { %s = request.GetRequestHeader("X-Session-Token") ?? ""; } catch { } try { onTokenSent(%s); } catch { }'
    for sig, name in ((GET_REQUEST, "stamped"), (POST_RAW, "carried")):
        body = _fold(_body(ac, sig))
        at = (body.find("StampVersionHeader(request);"), body.find(told % (name, name)),
              body.find("request.SendWebRequest()"))
        assert 0 <= at[0] < at[1] < at[2], (sig, at)
    # Only the form's games read and its submit ask for it, and every answer
    # each gives carries the token back (null where nothing went out).
    assert _owners(ac, "onTokenSent: ") == ["FetchReportableGames", "SubmitPlayerReportBody"], _owners(ac, "onTokenSent: ")
    for sig, gone in ((FETCH_GAMES, 'done(0, "", null, -1, null);'), (SUBMIT, 'done(0, "", false, null);')):
        body = _fold(_body(ac, sig))
        assert "onTokenSent: tok => carried = tok" in body, sig
        dones = re.findall(r"done\(([^;]*)\);", body)
        assert dones and all(d.endswith(", carried") or d.endswith(", null") for d in dones), (sig, dones)
        assert body.count(gone) == 1, (sig, gone)
    # The form keys the closure by that token; its own mark stands in only
    # when nothing went out.
    assert ("PlayerReportRules.ApplyList(_state, status, code, carried == null ? key : MarkOf(carried));"
            in _fold(_body(ui, OPEN))), "the games read closes the opening's sign-in"
    assert ("p.Reason, p.Details, p.WithLog, carried == null ? p.Key : MarkOf(carried));"
            in _fold(_body(ui, FINISH))), "the submit closes the press's sign-in"
    assert "ApiClient.SubmitPlayerReportBody(r.Body, r.Probe, Finish);" in _fold(_body(ui, PUMP))


def test_r17_a_refusal_closes_the_sign_in_the_request_carried():
    _check(_r17,
           lambda s: _replace(s, UI, "carried == null ? p.Key : MarkOf(carried));", "p.Key);"),
           _control_comment(AC, FETCH_GAMES))


# R18 reads every call of GetRequest in the plugin by what it binds, in each
# form a C# call can take: a named argument with any spacing, and a
# positional one at the parameter's place in the signature (ask 14 R2 M1).
_CALL_GET = re.compile(r"\bGetRequest\s*\(")
_NAMED_ARG = re.compile(r"^\s*([A-Za-z_][A-Za-z_0-9]*)\s*:(?!:)")
BIND_HOLD_CALL = "GetRequest(url, (ok, text) => answer(ok, text), detailedErrors: true, sessionAware: true));"


def _params(text, sig):
    """The parameter names of the declaration `sig` begins, in order; a
    generic's commas stay inside its type."""
    i = text.index("(", text.index(sig)) + 1
    depth, cur, out = 0, [], []
    while True:
        c = text[i]
        if c in "<([":
            depth += 1
        elif c in ">)]":
            if depth == 0:
                break
            depth -= 1
        if c == "," and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(c)
        i += 1
    out.append("".join(cur))
    return [p.split("=")[0].split()[-1] for p in out]


def _members(code):
    """(offset, member) at each member line of the code (_CS_MEMBER), in order."""
    out, off = [], 0
    for line in code.split("\n"):
        m = _CS_MEMBER.match(line)
        if m:
            out.append((off, m.group(1)))
        off += len(line) + 1
    return out


def _get_request_calls(src):
    """Every call of GetRequest in the plugin's code (the declaration left
    out), as (file, member, its arguments folded), in file order."""
    out = []
    for name in sorted(src):
        if "/" in name or not name.endswith(".cs"):
            continue
        text = src[name]
        masked, code = _masked(text), _code(text)
        hits = [m for m in _CALL_GET.finditer(masked)
                if not masked[max(0, m.start() - 40):m.start()].rstrip().endswith("IEnumerator")]
        if not hits:
            continue
        members = _members(code)
        offs = [o for o, _ in members]
        for m in hits:
            k = bisect.bisect_right(offs, m.start()) - 1
            out.append((name, members[k][1] if k >= 0 else "<file scope>",
                        [_fold(a) for a in _call_args(code, m.end() - 1)]))
    return out


def _binds(args, name, place):
    """What a call binds to the parameter `name` at `place`: the named
    argument's value, else the positional one at that place, else None."""
    for a in args:
        n = _NAMED_ARG.match(a)
        if n and n.group(1) == name:
            return a[n.end():].strip()
    if len(args) > place and not _NAMED_ARG.match(args[place]):
        return args[place].strip()
    return None


def _r18(src):
    ac = src[AC]
    # Off by default, so every other caller of GetRequest keeps its loop, and
    # bound to true by the form's three reads alone, whatever form the call
    # takes. The census reads every call in the plugin (over a hundred).
    assert "bool singleAttempt = false, Action<string> onTokenSent = null," in _code(ac)
    place = _params(ac, GET_REQUEST).index("singleAttempt")
    calls = _get_request_calls(src)
    assert len(calls) > 100, len(calls)
    bound = [(f, member, _binds(args, "singleAttempt", place)) for f, member, args in calls]
    bound = [b for b in bound if b[2] is not None]
    assert bound == [(AC, "FetchReportableGames", "true"), (AC, "FetchPlayerReports", "true"),
                     (AC, "FetchPlayerReportLog", "true")], bound
    # With it, the first answer leaves through the delivering branch whatever
    # the gate's verdict, and nothing reaches the retry after it.
    body = _fold(_body(ac, GET_REQUEST))
    deliver = body.find("if (rgv.Next == ReadGateRules.Next.Deliver || singleAttempt) {")
    retry = body.find("if (rgv.Next == ReadGateRules.Next.DelayRetry) yield return new WaitForSecondsRealtime((float)rgv.Delay);")
    assert 0 <= deliver < retry, (deliver, retry)
    branch = body[deliver:retry]
    assert branch.count("yield break;") == 1 and "callback(success, success" in branch, branch[:300]
    # It is read in two places: that branch, and the verdict's line (R21).
    assert body.count("singleAttempt") == 2, "singleAttempt is read in a third place"
    assert body.count("rgv = ReadGateVerdict(request, rgBody, rgAttempts, _rgTok, !singleAttempt);") == 1
    # The hold before the send is the same for every caller.
    assert body.find("yield return ReadGateHold(url, w => rgFail = w);") < body.find("StampVersionHeader(request);")


R18_MUTANTS = (
    lambda s: _replace(s, AC, "if (rgv.Next == ReadGateRules.Next.Deliver || singleAttempt)",
                       "if (rgv.Next == ReadGateRules.Next.Deliver)"),
    # another caller binds it, in each form a call can take (R2 M1)
    lambda s: _replace(s, AC, BIND_HOLD_CALL, BIND_HOLD_CALL[:-3] + ", singleAttempt:true));"),
    lambda s: _replace(s, AC, BIND_HOLD_CALL, BIND_HOLD_CALL[:-3] + ",\n                singleAttempt  :  true));"),
    lambda s: _replace(s, AC, BIND_HOLD_CALL,
                       "GetRequest(url, (ok, text) => answer(ok, text), true, true, null, null, null, null, true));"),
)


def test_r18_the_forms_three_reads_take_one_attempt_and_no_other_caller_changes():
    for mutation in R18_MUTANTS:
        _check(_r18, mutation, _control_comment(AC, GET_REQUEST))


# -- R19: the mark held now is what a request would carry -----------------------

STAMP_NOW = "internal static string SessionTokenToStamp()"
STAMP = "private static void StampVersionHeader(UnityWebRequest req)"


def _r19(src):
    ac, ui = src[AC], src[UI]
    # The form marks the sign-in it holds by the token a request would carry
    # now, by the stamp's own rule: while the transport withholds the token,
    # the mark is "", the mark a refused request reported, so Send stays closed.
    assert "{ return MarkOf(ApiClient.SessionTokenToStamp()); }" == _fold(_body(ui, "private static string SessionKeyNow()"))
    assert _fold(_body(ac, STAMP_NOW)) == (
        '{ string tok = SteamAuth.SessionToken; return !string.IsNullOrEmpty(tok)'
        ' && CredentialedTransportAllowed(baseUrl) ? tok : ""; }'), _fold(_body(ac, STAMP_NOW))
    stamp = _fold(_body(ac, STAMP))
    assert ('if (!string.IsNullOrEmpty(SteamAuth.SessionToken)) { if (CredentialedTransportAllowed(req.url))'
            ' req.SetRequestHeader("X-Session-Token", SteamAuth.SessionToken);') in stamp, stamp
    assert _sites(src, "SessionTokenToStamp()") == {AC: 1, UI: 1}, _sites(src, "SessionTokenToStamp()")


def test_r19_the_mark_held_now_is_the_token_a_request_would_carry():
    _check(_r19,
           lambda s: _replace(s, UI, "return MarkOf(ApiClient.SessionTokenToStamp());", "return MarkOf(SteamAuth.SessionToken);"),
           _control_comment(AC, STAMP_NOW))


# -- R20 ask 14 R2 H1: every refused sign-in stays refused ------------------------
#
# Answers to overlapping requests (an earlier opening's games read, a later
# one's, the submit in flight) land in any order. The H1 class: one slot that
# two closers overwrite. R20 to R25 pin each such write as add-only, guarded
# or ordered; the harness's overlap cases run the orders.

SET_LINES = ("internal readonly HashSet<string> RefusedSignIns = new HashSet<string>(StringComparer.Ordinal);",
             "return string.IsNullOrEmpty(sessionKey) || st.RefusedSignIns.Contains(sessionKey);",
             "if (!string.IsNullOrEmpty(sessionKey)) st.RefusedSignIns.Add(sessionKey);")


def _r20(src):
    rl = src[RL]
    # The form keeps every refused mark for the run, in a set: one line adds
    # to it, never an empty mark (an empty key is closed already), and one
    # line tests membership. Nothing else names it, so nothing removes one.
    named = [l for l in _lines(_code(rl)) if "RefusedSignIns" in l]
    assert named == list(SET_LINES), named
    assert _lines(_body(rl, SIGN_IN_CLOSED)) == ["{", SET_LINES[1], "}"], _lines(_body(rl, SIGN_IN_CLOSED))
    assert _lines(_body(rl, CLOSE_SIGN_IN)) == ["{", SET_LINES[2], "}"], _lines(_body(rl, CLOSE_SIGN_IN))
    assert _sites(src, "RefusedSignIns") == {RL: 3}, _sites(src, "RefusedSignIns")
    # Both closers add through it, and both checks ask it.
    assert _sites(src, "CloseSignIn(") == {RL: 3}, _sites(src, "CloseSignIn(")
    assert _sites(src, "SignInClosed(") == {RL: 3}, _sites(src, "SignInClosed(")
    assert "case Closes.Auth: CloseSignIn(st, sessionKey); break;" in _lines(_body(rl, APPLY))
    assert "if (status == 401) { CloseSignIn(st, sessionKey); return ListState.SignIn; }" in _lines(_body(rl, APPLY_LIST))
    assert "if (SignInClosed(st, sessionKey)) { why = Outcome.SignIn; return Block.SignIn; }" in _lines(_body(rl, CHECK))
    assert "if (SignInClosed(st, sessionKey)) return ListState.SignIn;" in _lines(_body(rl, BEFORE_LIST))


def test_r20_every_refused_sign_in_stays_refused():
    _check(_r20,
           lambda s: _replace(s, RL, SET_LINES[2], "st.RefusedSignIns.Clear(); " + SET_LINES[2]),
           _control_comment(RL, CLOSE_SIGN_IN))


# -- R21 ask 14 R2 L1: a read that takes one attempt says so ----------------------

RG = "ReadGateRules.cs"
VERDICT = "private static ReadGateRules.Verdict ReadGateVerdict(UnityWebRequest req, string body,"
VERDICT_LINE = "internal static string VerdictLine(Verdict v, bool retries, out bool warning)"
OTHER_VERDICT = "rgv = ReadGateVerdict(request, ReadGateBody(request, handler), rgAttempts, _rgTok);"
GET_VERDICT = "rgv = ReadGateVerdict(request, rgBody, rgAttempts, _rgTok, !singleAttempt);"


def _r21(src):
    ac, rg = src[AC], src[RG]
    # The verdict's line follows the caller's policy. GetRequest says whether
    # it retries; the other two callers keep the default, so their lines are
    # the old ones (the harness pins every line, both ways).
    assert _code(ac).count("ReadGateVerdict(") == 4, _code(ac).count("ReadGateVerdict(")
    assert _code(ac).count(OTHER_VERDICT) == 2, _code(ac).count(OTHER_VERDICT)
    assert _fold(_body(ac, GET_REQUEST)).count(GET_VERDICT) == 1
    assert "ReadGateRules.Attempts attempts, string sentToken, bool retries = true)" in _code(ac)
    # It writes the one line the rules give, and no other.
    body = _fold(_body(ac, VERDICT))
    assert "string line = ReadGateRules.VerdictLine(v, retries, out warning);" in body, body
    assert body.count("Plugin.Log.") == 2 and "[READ-GATE]" not in body, body
    # Without retries, a verdict that would retry says the answer went to its owner.
    assert _lines(_body(rg, VERDICT_LINE))[1:4] == [
        "warning = false;", "if (v.Next != Next.Deliver && !retries)",
        'return "[READ-GATE] refused (" + v.Refusal + "); one attempt, delivered to its owner without a retry";'], \
        _lines(_body(rg, VERDICT_LINE))[:5]


def test_r21_a_single_attempt_read_logs_no_retry():
    _check(_r21,
           lambda s: _replace(s, AC, GET_VERDICT, "rgv = ReadGateVerdict(request, rgBody, rgAttempts, _rgTok);"),
           _control_comment(AC, VERDICT))


# -- R22 the run's closer and the three maps close once ----------------------------

CLOSE_RUN = "private static void CloseRun(FormState st, Outcome o)"
CLOSE_ONCE = "private static void CloseOnce(Dictionary<string, Outcome> closed, string key, Outcome o)"
_MAP_USE = re.compile(r"(CloseOnce\()?\bst\.(Refused|Choices|Games)\b(\.TryGetValue\()?")


def _r22(src):
    rl = src[RL]
    # The first answer that closes the run keeps its line; a later one finds
    # it closed and changes nothing. Each map keeps the first outcome a key
    # was closed with. These two are the only writers.
    assert _lines(_body(rl, CLOSE_RUN)) == ["{", "if (st.RunClosed) return;", "st.RunClosed = true;",
                                            "st.RunOutcome = o;", "}"], _lines(_body(rl, CLOSE_RUN))
    assert _lines(_body(rl, CLOSE_ONCE)) == ["{", "if (!closed.ContainsKey(key)) closed[key] = o;", "}"], \
        _lines(_body(rl, CLOSE_ONCE))
    assert _sites(src, "RunClosed = ") == {RL: 1}, _sites(src, "RunClosed = ")
    assert _sites(src, "RunOutcome = ") == {RL: 2}, _sites(src, "RunOutcome = ")   # the field's start and CloseRun
    assert _sites(src, "CloseRun(") == {RL: 3}, _sites(src, "CloseRun(")           # Apply, ApplyList
    # Every use of a map is a read or a write through CloseOnce, one per map.
    uses = _MAP_USE.findall(_code(rl))
    assert uses and all(bool(w) != bool(r) for w, _, r in uses), uses
    assert sorted(m for w, m, _ in uses if w) == ["Choices", "Games", "Refused"], uses


def test_r22_the_run_and_each_choice_close_once():
    _check(_r22,
           lambda s: _replace_within(s, RL, CLOSE_RUN, "if (st.RunClosed) return;\n", ""),
           _control_comment(RL, CLOSE_RUN))


# -- R23 the day's count: no older read raises it ----------------------------------

NOTE_REMAINING = "internal static void NoteRemaining(FormState st, int remaining, int acceptedWhenAsked)"
_COUNT = re.compile(r"\b(Remaining|Accepted)\b")
COUNT_RULES = ("internal int Remaining = -1;", "internal int Accepted;",
               "if (remaining >= 0 && st.Accepted == acceptedWhenAsked) st.Remaining = remaining;",
               "if (st.Remaining == 0) { why = Outcome.DailyLimit; return Block.NoneLeft; }",
               "st.Accepted++;", "if (st.Remaining > 0) st.Remaining--;")
COUNT_READ = "if (status == 200) PlayerReportRules.NoteRemaining(_state, remaining, accepted);"


def _r23(src):
    rl, ui = src[RL], src[UI]
    # A games read's count stands only when the server accepted no report
    # after the read went out; each acceptance lowers the form's own count.
    got = [l for l in _lines(_code(rl)) if _COUNT.search(l)]
    assert got == list(COUNT_RULES), got
    assert _lines(_body(rl, NOTE_REMAINING)) == ["{", COUNT_RULES[2], "}"], _lines(_body(rl, NOTE_REMAINING))
    assert [l for l in _lines(_body(rl, APPLY)) if _COUNT.search(l)] == list(COUNT_RULES[4:])
    # The form takes the number of acceptances when the read goes out, and
    # only the newest opening's answer gives the count.
    assert [l for l in _lines(_code(ui)) if _COUNT.search(l)] == ["int accepted = _state.Accepted;"]
    body = _fold(_body(ui, OPEN))
    at = [body.find(x) for x in ("int accepted = _state.Accepted;", "ApiClient.FetchReportableGames(",
                                 "if (mine != _opening) return;", COUNT_READ)]
    assert 0 <= at[0] < at[1] < at[2] < at[3], at
    assert _sites(src, "NoteRemaining(") == {RL: 1, UI: 1}, _sites(src, "NoteRemaining(")


def test_r23_no_older_read_raises_the_days_count():
    for mutation in (
            lambda s: _replace(s, UI, "if (mine != _opening) return;\n                " + COUNT_READ,
                               COUNT_READ + "\n                if (mine != _opening) return;"),
            lambda s: _replace(s, RL, COUNT_RULES[2], "if (remaining >= 0) st.Remaining = remaining;")):
        _check(_r23, mutation, _control_comment(RL, NOTE_REMAINING))


# -- R24 the viewer keeps the line of the answer that closed it --------------------

STATUS_WRITES = ('private static string _adminStatus = "";',
                 '_selectedId = null; _confirm = ""; _note = ""; _adminStatus = "";',              # OpenAdmin
                 "_adminStatus = PlayerReportRules.AdminAnswerText(status, code);",                 # AdminAnswered
                 'if (!ApiClient.IsAdmin) { _adminStatus = I18n.Tr("Not allowed."); return; }',      # LoadAdmin, no request
                 "if (!_adminClosed) _adminStatus = said;",                                          # the list's answer
                 'if (!_adminClosed) _adminStatus = I18n.Tr("Report closed.");')                     # the close's answer


def _r24(src):
    ui = src[UI]
    # Once a refusal closed the viewer, no later answer writes its line:
    # AdminAnswered returns first, and the two success lines stand back.
    assert _lines(_body(ui, ADMIN_ANSWERED)) == ["{", "if (_adminClosed) return;", ADMIN_CLOSES, STATUS_WRITES[2], "}"], \
        _lines(_body(ui, ADMIN_ANSWERED))
    writes = [l for l in _lines(_code(ui)) if "_adminStatus = " in l]
    assert writes == list(STATUS_WRITES), writes
    assert STATUS_WRITES[4] in _lines(_body(ui, LOAD_ADMIN))
    assert STATUS_WRITES[5] in _lines(_body(ui, CLOSE_REPORT))


def test_r24_the_viewer_keeps_the_line_that_closed_it():
    _check(_r24,
           lambda s: _replace_within(s, UI, ADMIN_ANSWERED, "if (_adminClosed) return;\n", ""),
           _control_comment(UI, ADMIN_ANSWERED))


# -- R25 the badge shows the newest read's count -----------------------------------

NEWER = "internal static bool NewerAnswer(ref int shown, int ticket)"
BADGE_SETS = ("if (PlayerReportRules.NewerAnswer(ref _badgeShown, ticket)) NativeUI.SetPlayerReportBadge(openTotal);",
              "if (status == 200 && PlayerReportRules.NewerAnswer(ref _badgeShown, ticket)) "
              "NativeUI.SetPlayerReportBadge(openTotal);")


def _r25(src):
    rl, ui = src[RL], src[UI]
    # Two answers set the badge, the list's and the count's. Each request
    # takes its number when it is sent, and only an answer to a newer request
    # than the shown one's sets the badge.
    assert _lines(_body(rl, NEWER)) == ["{", "if (ticket <= shown) return false;", "shown = ticket;", "return true;", "}"]
    assert [l for l in _lines(_code(ui)) if "SetPlayerReportBadge(" in l] == list(BADGE_SETS)
    for sig, line in ((LOAD_ADMIN, BADGE_SETS[0]), (COUNT, BADGE_SETS[1])):
        body = _fold(_body(ui, sig))
        at = (body.find("int ticket = ++_badgeAsked;"), body.find("ApiClient.FetchPlayerReports("), body.find(line))
        assert 0 <= at[0] < at[1] < at[2] and body.count("++_badgeAsked") == 1, (sig, at)
    assert _code(ui).count("_badgeAsked") == 3 and _code(ui).count("_badgeShown") == 3
    assert _sites(src, "NewerAnswer(") == {RL: 1, UI: 2}, _sites(src, "NewerAnswer(")


def test_r25_the_badge_shows_the_newest_reads_count():
    _check(_r25,
           lambda s: _replace(s, UI, BADGE_SETS[1], "if (status == 200) NativeUI.SetPlayerReportBadge(openTotal);"),
           _control_comment(UI, COUNT))
