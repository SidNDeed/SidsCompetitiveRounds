"""Item 17, the keybind system: the source-shape half of T4 and T8, and the
catalogue half of D9. The executed halves live elsewhere: T1 is the
`keybinds` suite of tools/client-rules-harness (test_client_rules_harness.py
runs it), T2/T3 run in game on every launch and are witnessed from
LogOutput.log, T6's inventory diff is a lane run.

Every decision is taken on `_cs_structure`'s mask, so a needle inside a
comment or a string literal is never code (#342/#431/#441), and every
assertion is scoped to a METHOD SPAN resolved by signature, never file-wide
and never by line number (#432/#330: a flag names a line, the defect is a
class; a span asserted by a stale line measures whatever lives there).

The integrity property these gates hold (design 2.7, METHOD CHANGE 1/1b):
Pacifist, Immovable Object and Grounded pay gold when their flag is still
FALSE at a win, so every way the achievement path can fail must move a flag
toward ACTED. Reads are total, the gate suppresses only on a positive
not-in-combat, each union sits in its own try whose catch marks its own
predicate, and nothing paying is reachable only through Poll.
"""
from __future__ import annotations

import functools
import re
from pathlib import Path

import pytest

import _cs_structure

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PLUGIN = REPO / "plugin"
GSW = PLUGIN / "GameStateWatcher.cs"
KB = PLUGIN / "Keybinds.cs"
KBUI = PLUGIN / "NativeUI.Keybinds.cs"
CAT = PLUGIN / "I18nCatalogues.cs"
GEN = PLUGIN / "I18nSourceKeys.g.cs"

SIG = {
    "TickAchievementInput": "private static void TickAchievementInput()",
    "ReadCombatGate": "private static Gate ReadCombatGate()",
    "NoteShotFired": "private static void NoteShotFired(bool forced)",
    "MarkInputPredicatesActed": "private static void MarkInputPredicatesActed(string reason)",
    "SafeAchLog": "private static void SafeAchLog(string message)",
    "UnionActed": "private static bool UnionActed(Keybinds.Mode mode, Keybinds.Src[] union)",
    "TickInputSampling": "private static void TickInputSampling(float dt)",
    "PollAchievementState": "private static void PollAchievementState()",
    "TickFrame": "public static void TickFrame()",
    "OnMatchStarted": "private static void OnMatchStarted()",
    "ResetMatchState": "private static void ResetMatchState()",
}
ACH_PATH = ("TickAchievementInput", "ReadCombatGate", "NoteShotFired", "MarkInputPredicatesActed")
RBS_SIG = "internal static Read ReadBoundSource(Src src, Mode mode)"


@functools.lru_cache(maxsize=None)
def _src(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# The mask is a pure function of the text; a 9000-line file is masked once.
@functools.lru_cache(maxsize=64)
def mask_code(src: str) -> str:
    return _cs_structure.mask_code(src)


@functools.lru_cache(maxsize=64)
def strip_comments_only(src: str) -> str:
    return _cs_structure.strip_comments_only(src)


@functools.lru_cache(maxsize=None)
def _span(src: str, signature: str):
    """_cs_structure.method_spans over the cached mask: every block that
    follows `signature`, and exactly one is required."""
    masked = mask_code(src)
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
    """The masked body (comments and literals blanked), same offsets."""
    a, b = _span(src, signature)
    return mask_code(src)[a:b]


def _text(src: str, signature: str) -> str:
    """The body with comments removed and literals kept."""
    a, b = _span(src, signature)
    return strip_comments_only(src)[a:b]


def _gsw(name: str) -> str:
    return _code(_src(GSW), SIG[name])


def _gsw_text(name: str) -> str:
    return _text(_src(GSW), SIG[name])


def _blocks(masked: str, keyword: str):
    """(keyword_at, open_brace, close_exclusive) for every `keyword {` or
    `keyword (...) {` block in a masked span."""
    out = []
    for m in re.finditer(r"\b%s\b" % keyword, masked):
        i = m.end()
        while i < len(masked) and masked[i].isspace():
            i += 1
        if i < len(masked) and masked[i] == "(":
            depth = 0
            while i < len(masked):
                if masked[i] == "(":
                    depth += 1
                elif masked[i] == ")":
                    depth -= 1
                    if depth == 0:
                        i += 1
                        break
                i += 1
            while i < len(masked) and masked[i].isspace():
                i += 1
        if i >= len(masked) or masked[i] != "{":
            continue
        depth, j = 0, i
        while j < len(masked):
            if masked[j] == "{":
                depth += 1
            elif masked[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        out.append((m.start(), i, j + 1))
    return out


def _inside(pos: int, blocks) -> bool:
    return any(o < pos < c for _k, o, c in blocks)


def _ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


# ── T4: the advisory counters ───────────────────────────────────────────────

MOVE_LITERALS = re.compile(r"KeyCode\.(W|A|S|D|Space|UpArrow|DownArrow|LeftArrow|RightArrow)\b")


def test_t4_no_movement_literal_survives_in_the_counter_span():
    assert not MOVE_LITERALS.findall(_gsw("TickInputSampling"))


def test_t4_the_counter_span_holds_exactly_seven_bound_reads_one_per_game_row():
    body = _gsw_text("TickInputSampling")
    calls = re.findall(r"Keybinds\.ReadBoundSource\(KeybindRules\.(\w+), Keybinds\.Mode\.(\w+)\) == Read\.Down", body)
    assert len(re.findall(r"ReadBoundSource\(", body)) == 7
    assert len(calls) == 7, calls
    assert sorted(c[0] for c in calls) == sorted(
        ["MoveUp", "MoveDown", "MoveLeft", "MoveRight", "Jump", "Fire", "Block"])
    assert all(c[1] == "Edge" for c in calls)


def test_t4_the_counter_span_writes_no_achievement_flag():
    body = _gsw("TickInputSampling")
    assert not re.search(r"\bach(FiredShot|Moved|Jumped)\s*=", body)


def test_t4_the_counter_typing_guard_survives():
    body = _gsw_text("TickInputSampling")
    assert re.search(r"typingInChat\s*=\s*CompetitiveUI\.AnyChatTyping \|\| NativeUI\.IsOpen", body)
    assert re.search(r"if \(typingInChat\)", body)


# ── T4: no raw input read in the achievement path ───────────────────────────

RAW = re.compile(r"\bInput\.|\.IsPressed\b|\.WasPressed\b|\.WasReleased\b|\bGetKey(Down|Up)?\(|"
                 r"\bGetMouseButton(Down|Up)?\(|\banyKey(Down)?\b")


@pytest.mark.parametrize("name", ACH_PATH + ("UnionActed", "TickInputSampling"))
def test_t4_no_raw_input_read_in_the_achievement_path(name):
    hits = RAW.findall(_gsw(name))
    assert not hits, (name, hits)


def test_t4_raw_read_detector_negative_control():
    planted = "{ if (Input.GetKey(KeyCode.Space)) achMoved = true; }"
    assert RAW.search(mask_code(planted))


# ── T4: one writer for achFiredShot, three resets ───────────────────────────

def test_t4_exactly_one_achFiredShot_true_writer_and_it_is_in_NoteShotFired():
    src = _src(GSW)
    masked = mask_code(src)
    hits = [m.start() for m in re.finditer(r"\bachFiredShot\s*=\s*true\b", masked)]
    assert len(hits) == 1, len(hits)
    a, b = _span(src, SIG["NoteShotFired"])
    assert a < hits[0] < b


def test_t4_achFiredShot_resets_at_the_declaration_match_start_and_reset():
    src = _src(GSW)
    masked = mask_code(src)
    assert len(re.findall(r"\bachFiredShot\s*=\s*false\b", masked)) == 3
    assert re.search(r"private static bool achFiredShot = false;", masked)
    for name in ("OnMatchStarted", "ResetMatchState"):
        for flag in ("achFiredShot", "achMoved", "achJumped"):
            assert re.search(r"\b%s\s*=\s*false\s*;" % flag, _gsw(name)), (name, flag)


def test_t4_NoteShotFired_reads_the_flag_first_and_forced_once():
    body = _gsw_text("NoteShotFired")
    stmts = [s for s in _ws(body.strip("{} \r\n")).split(";") if s.strip()]
    assert stmts[0].strip() == "if (achFiredShot) return"
    assert "bool typingInChat = false" in [s.strip() for s in stmts]
    assert len(re.findall(r"\bforced\b", body)) == 1
    assert re.search(r"if \(typingInChat && !forced\) return;", body)


# ── T4: totality of the writers and the accessor ────────────────────────────

UNSAFE_CALL = re.compile(r"\b(CompetitiveUI|NativeUI|Input)\.\w+|\bPlugin\.Log\.")
TOTAL_ROUTINES = {"SafeAchLog", "NoteShotFired", "MarkInputPredicatesActed"}


def _totality(masked: str):
    tries = _blocks(masked, "try")
    bad = [m.group(0) for m in UNSAFE_CALL.finditer(masked) if not _inside(m.start(), tries)]
    calls_in_catch = []
    for _k, o, c in _blocks(masked, "catch"):
        for m in re.finditer(r"\b([A-Za-z_]\w*)\s*\(", masked[o:c]):
            if m.group(1) not in TOTAL_ROUTINES:
                calls_in_catch.append(m.group(1))
    return bad, calls_in_catch


@pytest.mark.parametrize("name", ("NoteShotFired", "MarkInputPredicatesActed", "SafeAchLog"))
def test_t4_the_writers_are_total(name):
    bad, calls_in_catch = _totality(_gsw(name))
    assert not bad, (name, bad)
    assert not calls_in_catch, (name, calls_in_catch)


def test_t4_ReadBoundSource_is_total():
    body = _code(_src(KB), RBS_SIG)
    bad, _calls = _totality(body)
    assert not bad, bad
    catches = _blocks(body, "catch")
    assert catches and all("return Read.Unreadable;" in _ws(body[o:c]) for _k, o, c in catches)
    tries = _blocks(body, "try")
    # the whole body is one try: every statement inside it
    assert len(tries) >= 1 and _ws(body[1:tries[0][0]]) == ""


def test_t4_totality_negative_control():
    hoisted = "{ if (achFiredShot) return; bool t = CompetitiveUI.AnyChatTyping; achFiredShot = true; }"
    bad, _ = _totality(mask_code(hoisted))
    assert bad == ["CompetitiveUI.AnyChatTyping"]
    bare_log = "{ try { x(); } catch { Plugin.Log.LogWarning(\"w\"); } }"
    bad, calls = _totality(mask_code(bare_log))
    assert "LogWarning" in calls


def test_t4_ReadCombatGate_is_total_and_unknown_on_failure():
    body = _gsw_text("ReadCombatGate")
    masked = _gsw("ReadCombatGate")
    tries = _blocks(masked, "try")
    assert len(tries) == 1 and _ws(masked[1:tries[0][0]]) == ""
    catches = _blocks(masked, "catch")
    assert len(catches) == 1 and _ws(body[catches[0][1]:catches[0][2]]) == "{ return Gate.Unknown; }"
    assert "if (!isTracking) return Gate.NotInCombat;" in body
    assert "if (inPickPhase) return Gate.NotInCombat;" in body
    assert "return Gate.Unknown;" in _ws(body[tries[0][1]:tries[0][2]])


# ── T4: the unions, membership and occurrence ───────────────────────────────

def _union(name: str):
    src = strip_comments_only(_src(GSW))
    m = re.search(r"private static readonly Keybinds\.Src\[\] %s =\s*\{(.*?)\};" % name, src, re.S)
    assert m, name
    terms = re.findall(r"Keybinds\.(?:Src\.(Row|Legacy|LegacyMouse)\(([^)]*)\)|(Action\w+))", m.group(1))
    out = set()
    for kind, arg, action in terms:
        out.add(action if action else "%s:%s" % (kind, arg.replace("KeybindRules.", "").replace("KeyCode.", "")))
    return out


def test_t4_fire_union_membership():
    assert _union("FireUnion") == {"Row:Fire", "LegacyMouse:0", "ActionFire"}


def test_t4_move_union_membership():
    assert _union("MoveUnion") == {
        "Row:MoveUp", "Row:MoveDown", "Row:MoveLeft", "Row:MoveRight", "Row:Jump",
        "Legacy:W", "Legacy:A", "Legacy:S", "Legacy:D", "Legacy:Space",
        "Legacy:UpArrow", "Legacy:DownArrow", "Legacy:LeftArrow", "Legacy:RightArrow",
        "ActionMove"}


def test_t4_jump_union_membership_carries_MoveUp():
    assert _union("JumpUnion") == {
        "Row:Jump", "Row:MoveUp", "Legacy:Space", "Legacy:W", "Legacy:UpArrow", "ActionJump"}


def test_t4_the_eight_bound_relations():
    rel = {(p, t) for p, u in (("achFiredShot", "FireUnion"), ("achMoved", "MoveUnion"), ("achJumped", "JumpUnion"))
           for t in _union(u) if t.startswith("Row:")}
    assert len(rel) == 8, sorted(rel)


@pytest.mark.parametrize("union", ("FireUnion", "MoveUnion", "JumpUnion"))
def test_t4_each_union_has_one_evaluation_site(union):
    masked = mask_code(_src(GSW))
    uses = [m.start() for m in re.finditer(r"\b%s\b" % union, masked)]
    assert len(uses) == 2, (union, len(uses))           # the declaration and the one site
    a, b = _span(_src(GSW), SIG["TickAchievementInput"])
    assert sum(1 for u in uses if a < u < b) == 1


def test_t4_the_fold_is_not_up_never_down():
    body = _gsw_text("UnionActed")
    assert "!= Read.Up" in body and "== Read.Down" not in body


# ── T4: containment, semantically ───────────────────────────────────────────

def _try_catch_pairs(name: str):
    masked = _gsw(name)
    text = _gsw_text(name)
    tries = _blocks(masked, "try")
    catches = _blocks(masked, "catch")
    pairs = []
    for t in tries:
        nxt = [c for c in catches if c[0] >= t[2]]
        if nxt:
            c = min(nxt, key=lambda x: x[0])
            if _ws(masked[t[2]:c[0]]) == "":
                pairs.append((_ws(text[t[1]:t[2]]), _ws(text[c[1]:c[2]])))
    return pairs


def test_t4_each_predicate_sits_in_its_own_try_whose_catch_marks_it():
    pairs = _try_catch_pairs("TickAchievementInput")
    fire = [c for t, c in pairs if "FireUnion" in t]
    move = [c for t, c in pairs if "MoveUnion" in t]
    jump = [c for t, c in pairs if "JumpUnion" in t]
    assert len(fire) == len(move) == len(jump) == 1
    assert "NoteShotFired(true);" in fire[0]
    assert "achMoved = true;" in move[0]
    assert "achJumped = true;" in jump[0]
    fire_try = [t for t, c in pairs if "FireUnion" in t][0]
    assert "NoteShotFired(false)" in fire_try and "NoteShotFired(true)" not in fire_try
    assert not any(("FireUnion" in t) + ("MoveUnion" in t) + ("JumpUnion" in t) > 1 for t, _ in pairs)


def test_t4_fire_is_evaluated_first():
    body = _gsw("TickAchievementInput")
    assert body.index("FireUnion") < body.index("MoveUnion") < body.index("JumpUnion")


def test_t4_MarkInputPredicatesActed_writes_all_three():
    body = _gsw_text("MarkInputPredicatesActed")
    for needle in ("NoteShotFired(true);", "achMoved = true;", "achJumped = true;", "SafeAchLog("):
        assert needle in body, needle


@pytest.mark.parametrize("name", ACH_PATH)
def test_t4_no_catch_in_the_achievement_path_is_empty_or_logs_bare(name):
    masked = _gsw(name)
    text = _gsw_text(name)
    for _k, o, c in _blocks(masked, "catch"):
        assert _ws(masked[o + 1:c - 1]) != "", (name, "empty catch")
        assert "Plugin.Log." not in text[o:c], (name, "bare log in a catch")


def test_t4_TickAchievementInput_is_the_first_statement_of_TickFrame():
    body = _gsw_text("TickFrame")
    first = _ws(body[1:])
    assert first.startswith(
        "try { TickAchievementInput(); } catch { MarkInputPredicatesActed(\"achievement tick threw\"); }"), first[:160]


# ── T4: reachability before logic ───────────────────────────────────────────

def test_t4_every_paying_write_is_on_the_frame_path():
    src = _src(GSW)
    masked = mask_code(src)
    allowed = [_span(src, SIG[n]) for n in ("TickAchievementInput", "NoteShotFired", "MarkInputPredicatesActed")]
    for m in re.finditer(r"\bach(FiredShot|Moved|Jumped)\s*=\s*true\b", masked):
        assert any(a < m.start() < b for a, b in allowed), src[m.start():m.start() + 40]
    assert not re.search(r"\bach(FiredShot|Moved|Jumped)\s*=", _gsw("PollAchievementState"))


@pytest.mark.parametrize("name", ACH_PATH)
def test_t4_the_achievement_path_reads_no_cached_gate(name):
    assert "LocalAliveInCombatNow" not in _gsw(name)


def test_t4_the_gate_suppresses_only_on_not_in_combat():
    body = _gsw_text("TickAchievementInput")
    assert "if (ReadCombatGate() == Gate.NotInCombat) return;" in body
    assert "Gate.InCombat" not in body


def test_t4_the_poll_path_is_belted():
    src = strip_comments_only(_src(GSW))
    for call in ("PollRoomState", "PollMatchState", "PollAchievementState"):
        assert re.search(r"try \{ %s\(\); \} catch \(Exception e\) \{ SafeAchLog\(" % call, src), call


# ── T4: the capture path holds no decision of its own ───────────────────────

def test_t4_capture_poll_delegates_every_decision():
    body = _code(_src(KB), "internal static bool PollCapture()")
    assert len(re.findall(r"KeybindRules\.CaptureGesture\(", body)) == 1
    assert len(re.findall(r"KeybindRules\.FirstHit\(", body)) == 1
    assert "KeyCode.Backspace" not in body and "KeyCode.Escape" not in body
    assert not re.search(r"\brow\s*[=!]=\s*(KeybindRules\.)?[A-Z]\w*\b", body)


# ── T8 static: the four prompt postfixes, by target ─────────────────────────

POSTFIXES = {
    "ResetMenuPatch": ("nameof(CharacterSelectionInstance.ResetMenu)", "ApplyJoin"),
    "OnEnablePatch": ('"OnEnable"', "ApplyJoin"),
    "StartPickingPatch": ("nameof(CharacterSelectionInstance.StartPicking)", "ApplyReady"),
    "ReadyUpPatch": ("nameof(CharacterSelectionInstance.ReadyUp)", "ApplyReady"),
}


@pytest.mark.parametrize("cls", sorted(POSTFIXES))
def test_t8_each_prompt_postfix_has_its_target(cls):
    src = strip_comments_only(_src(KB))
    target, apply = POSTFIXES[cls]
    m = re.search(r"\[HarmonyPatch\(typeof\(CharacterSelectionInstance\), ([^)]*\)?)\)\]\s*internal static class %s\b" % cls, src)
    assert m, cls
    assert m.group(1).strip() == target, (cls, m.group(1))
    body = _code(_src(KB), "internal static class %s" % cls)
    assert "[HarmonyPostfix]" in strip_comments_only(_src(KB))[_span(_src(KB), "internal static class %s" % cls)[0]:
                                                             _span(_src(KB), "internal static class %s" % cls)[1]]
    assert len(re.findall(r"\bApply(Join|Ready)\(", body)) == 1 and ("%s(" % apply) in body


def test_t8_join_writes_joinObj_and_ready_writes_getReadyObj():
    join = _text(_src(KB), "internal static void ApplyJoin(CharacterSelectionInstance c)")
    ready = _text(_src(KB), "internal static void ApplyReady(CharacterSelectionInstance c)")
    assert "WriteLabel(c.joinObj, NativeUI.KeybindJoinPrompt());" in join and "getReadyObj" not in join
    assert "WriteLabel(c.getReadyObj, NativeUI.KeybindReadyPrompt());" in ready and "joinObj" not in ready
    assert "if (c.isReady) { RestoreReady(c); return; }" in ready
    for body in (join, ready):
        assert "Override()" in body.split("WriteLabel")[0]


def test_t8_the_override_consults_the_rule():
    body = _text(_src(KB), "private static bool Override()")
    assert "KeybindRules.ShouldOverrideReadyPrompt(" in body


# ── D9: every string the Controls page writes is in every catalogue ─────────

TR_SITE = re.compile(r'\bI18n\.TrF?\(\s*"((?:[^"\\]|\\.)*)"')


def _unescape(s: str) -> str:
    return re.sub(r'\\(u[0-9a-fA-F]{4}|.)',
                  lambda m: chr(int(m.group(1)[1:], 16)) if m.group(1).startswith("u") else
                  {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}.get(m.group(1), m.group(1)), s)


def _kb_literals():
    src = strip_comments_only(_src(KBUI))
    return sorted({_unescape(m.group(1)) for m in TR_SITE.finditer(src)})


def _blocks_of_catalogue():
    cat = _src(CAT)
    parts = cat.split("private static readonly Dictionary<string, string> ")[1:]
    assert [p[:2] for p in parts] == ["ES", "RU", "UK", "SV"]
    out = {}
    for p in parts:
        d = {}
        for m in re.finditer(r'^            \["((?:[^"\\]|\\.)*)"\] = "((?:[^"\\]|\\.)*)",\r?$', p, re.M):
            d[_unescape(m.group(1))] = _unescape(m.group(2))
        out[p[:2]] = d
    return out


def test_d9_the_controls_page_has_strings_to_check():
    lits = _kb_literals()
    assert len(lits) >= 90, len(lits)
    for must in ("Mod controls", "Game controls", "Press a key...", "Esc cancels",
                 "Unbound", "Reset this control", "Your controls changed: {0}",
                 "The two wheels cannot take a modifier key.", "UP", "JUMP", "FIRE", "BLOCK"):
        assert must in lits, must


@pytest.mark.parametrize("loc", ["ES", "RU", "UK", "SV"])
def test_d9_every_controls_page_string_is_translated(loc):
    d = _blocks_of_catalogue()[loc]
    missing = [k for k in _kb_literals() if k not in d]
    assert not missing, missing[:10]
    for k in _kb_literals():
        ph_k = sorted(re.findall(r"\{\d+(?::[^}]*)?\}", k))
        ph_v = sorted(re.findall(r"\{\d+(?::[^}]*)?\}", d[k]))
        assert ph_k == ph_v, (loc, k, d[k])
        assert d[k].strip(), (loc, k)


def test_d9_every_controls_page_string_is_in_the_source_registry():
    gen = _src(GEN)
    for k in _kb_literals():
        esc = (k.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n"))
        assert ('"%s",' % esc) in gen, k


def test_d9_negative_control():
    d = _blocks_of_catalogue()["ES"]
    assert "Press a key... but invented" not in d
    assert "Controls" in d and "Mod controls" in d


def test_d9_the_retired_chat_header_is_gone_from_every_catalogue():
    for loc, d in _blocks_of_catalogue().items():
        assert "Chat [{0}]  \u2014  Enter to send, Esc keeps your draft, Alt switches channel" not in d, loc
        assert "Chat [{0}]  \u2014  Enter to send, Esc keeps your draft, {1} switches channel" in d, loc


# ── D2: the ChatChannel tap is read physically, not from IMGUI ──────────────

def test_d2_no_imgui_alt_tap_detector_survives():
    masked = mask_code(_src(PLUGIN / "CompetitiveUI.cs"))
    assert "chatAltHeld" not in masked and "chatAltTapClean" not in masked
    assert "KeyCode.LeftAlt" not in masked and "KeyCode.RightAlt" not in masked
    assert len(re.findall(r"Keybinds\.ChatChannelTapped\(", masked)) == 1


# ── Q1: F5 is a permanent rescue read ───────────────────────────────────────

def test_q1_f5_rescue_read_survives_beside_the_bound_menu_row():
    src = strip_comments_only(_src(PLUGIN / "Plugin.cs"))
    assert "menuF5 = Input.GetKeyDown(KeyCode.F5) && !Keybinds.CaptureOwnsInput;" in src
    assert "menuRow = Keybinds.Down(KeybindRules.MenuToggle);" in src
    assert re.search(r"if \(menuF5 \|\| menuRow\)\s*\{\s*CompetitiveUI\.ToggleOverlay\(\);", src)


# ── Fix pass 1 F2: the tap detector attributes every edge ───────────────────
# The decision lives in KeybindRules.TapDetector, which the harness executes
# (T1 cases 18 and 23, the simultaneous-edge and the Unknown legs); these
# assert the production wiring feeds it the observation it needs.

def test_f2_the_detector_is_the_harness_executed_one():
    masked = mask_code(_src(KB))
    assert not re.search(r"\bclass\s+TapDetector\b", masked)
    assert "new KeybindRules.TapDetector()" in masked
    rules = mask_code(_src(PLUGIN / "KeybindRules.cs"))
    assert len(re.findall(r"\bclass\s+TapDetector\b", rules)) == 1


def test_f2_the_chat_tap_scans_every_keycode_member():
    body = _code(_src(KB), "internal static bool ChatChannelTapped(bool chatInputOpen)")
    assert "chatTap.Step(realInput, KeyCodesFor(ChatChannel), FullKeyScan());" in _ws(body)
    assert "ScanSet()" not in body
    full = _code(_src(KB), "internal static int[] FullKeyScan()")
    assert "Enum.GetValues(typeof(KeyCode))" in full


def test_f2_the_real_input_carries_the_typed_text_channel():
    body = _text(_src(KB), "private sealed class RealInput : IFrameInput")
    assert "return Input.inputString;" in body
    assert "AnyMouseDown" not in body


def test_f2_an_unknown_edge_is_never_the_mouse():
    body = _text(_src(PLUGIN / "KeybindRules.cs"),
                 "internal static EdgeAttribution Attribute(IFrameInput io, int[] alias, int[] scan)")
    # every Unknown is set or cleared only under a named mutation
    for m in re.finditer(r"&= ~EdgeAttribution\.Unknown|& ~EdgeAttribution\.Unknown", body):
        line = body[body.rfind("\n", 0, m.start()) + 1:body.find("\n", m.end())]
        assert "Mut ==" in line, line


# ── Fix pass 1 F3: prompt overrides target keyboard surfaces only ───────────

def test_f3_the_join_override_carries_the_keyboard_surface_gate():
    join = _code(_src(KB), "internal static void ApplyJoin(CharacterSelectionInstance c)")
    head = join.split("WriteLabel")[0]
    assert "JoinSurfaceIsKeyboard(c)" in head and "Override()" in head
    gate = _code(_src(KB), "private static bool JoinSurfaceIsKeyboard(CharacterSelectionInstance c)")
    assert "KeybindRules.PromptSurfaceIsKeyboard(" in gate
    assert "GeneralInput.InputType.Controller" in gate


def test_f5_the_loader_ends_on_the_resolved_conflict_free_set():
    body = _code(_src(KB), "private static void LoadFromConfig()")
    assert len(re.findall(r"KeybindRules\.ResolveLoaded\(", body)) == 1
    assert "KeybindRules.Refuse(" not in body
    assert not re.search(r"\bbound\[i\]\s*=", body)


def test_f3_the_ready_override_keeps_its_seat_gate():
    ready = _code(_src(KB), "internal static void ApplyReady(CharacterSelectionInstance c)")
    assert "KeyboardSeat(c)" in ready.split("WriteLabel")[0]


# ── Fix pass 1 F6: an accepted change is one transaction ────────────────────
# The rollback is KeybindRules.Commit, executed by the harness (T1 case 21:
# a throw in the apply or in a config write puts every prior state back).
# These assert every writer reaches it and the apply step does not swallow.

def test_f6_every_writer_commits_through_the_transaction():
    src = _src(KB)
    write = _code(src, "internal static Refusal Write(int row, BindSource src, string via, out int other)")
    assert len(re.findall(r"\bCommitRows\(", write)) == 1
    assert "return Refusal.ApplyFailed;" in write
    assert not re.search(r"\bbound\[row\]\s*=", write)
    assert "entries[" not in write
    for sig in ("internal static Refusal ResetRow(int row)", "internal static void ResetAll()"):
        body = _code(src, sig)
        assert len(re.findall(r"\bCommitRows\(", body)) == 1, sig
        assert not re.search(r"\bbound\[[^\]]+\]\s*=", body), sig
        assert not re.search(r"\bWrite\(", body), sig
    commit = _code(src, "private static bool CommitRows(int[] rows, BindSource[] values, string via)")
    assert len(re.findall(r"KeybindRules\.Commit\(", commit)) == 1
    assert "NativeUI.KeybindApplyFailedText()" in commit
    masked = mask_code(src)
    assert len(re.findall(r"KeybindRules\.Commit\(", masked)) == 1
    assert "ReapplyAllLiveSets(" not in masked


def test_f6_the_apply_step_lets_a_throw_reach_the_commit():
    body = _code(_src(KB), "internal static void ApplyAllLiveSetsOrThrow(BindSource[] cfg)")
    assert not re.search(r"\b(try|catch)\b", body)
    store = _code(_src(KB), "private sealed class LiveStore : IBindStore")
    assert "ApplyAllLiveSetsOrThrow(b)" in store and not re.search(r"\bcatch\b", store)


def test_f6_the_failure_is_told_in_every_locale():
    key = "That change could not be applied, so every control was put back as it was."
    assert ('I18n.Tr("%s")' % key) in _src(KBUI)
    blocks = _blocks_of_catalogue()
    for loc in ("ES", "RU", "UK", "SV"):
        assert key in blocks[loc], loc


# ── Fix pass 1 F7: a mod row's mouse press ends capture with the refusal ────
# The decision is KeybindRules.CaptureTakesMouse, executed by the harness
# (T1 case 22, composed with Refuse's rule 4). These assert the poll asks it,
# a mouse press reaches the one writer, and Accept always ends the capture
# and records the refusal the pane renders.

def test_f7_the_poll_reads_the_mouse_for_every_armed_row():
    body = _code(_src(KB), "internal static bool PollCapture()")
    assert len(re.findall(r"KeybindRules\.CaptureTakesMouse\(row\)", body)) == 1
    assert "IsGameRow" not in body and "IsModRow" not in body
    assert len(re.findall(r"\bAccept\(row, KeybindRules\.MouseIndexToSource\(n\), n\)", body)) == 1


def test_f7_accept_ends_capture_and_records_the_refusal():
    body = _ws(_code(_src(KB), "private static void Accept(int row, BindSource src, int mouseButton)"))
    assert 'var r = Write(row, src, "capture", out other);' in _ws(
        _text(_src(KB), "private static void Accept(int row, BindSource src, int mouseButton)"))
    assert "captureRow = -1;" in body
    assert "LastRefusal = r;" in body
    assert "LastRefusalRow = r == Refusal.None ? -1 : row;" in body
    assert not re.search(r"\bif\b[^;]*captureRow = -1", body)
    pane = _code(_src(KBUI), "private static bool KeybindRenderPane(SettingsRowRec rec)")
    assert "KeybindRefusalText(Keybinds.LastRefusal)" in pane
    refusal = _text(_src(KBUI), "private static string KeybindRefusalText(Refusal r)")
    assert "case Refusal.MouseOnModRow:" in refusal
