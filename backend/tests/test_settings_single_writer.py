"""One writer per setting on the settings page (item 13, design section 2.1).

Design 2.1: the cycler, the hotkey, the typed widget and the bulk reset are
callers of ONE writer, so they cannot drift apart. Round 1 kept a second
writer per setting: each row's own switch assigned its ConfigEntry inline,
while a named writer existed only for the per-tab reset (review round 1,
LOW-1). The gates below keep it one writer. Every decision is taken on
`_cs_structure`'s mask, so a needle inside a comment or a string is never
code (#342/#431/#441):

1. No settings row's handler writes a ConfigEntry. Every typed row
   constructor call in the plugin tree (SettingsSwitch / SettingsSegmented /
   SettingsSlider / SettingsDropdown, and the performance rows' AddPerfRow)
   holds no `.Value =` assignment. The same calls READ `.Value` in their
   getters, and a comparison is not an assignment.
2. Every bulk-reset row's handler calls the writer its reset calls, taken
   from SettingsDescriptorWriters.InvokeReset (never listed here), with the
   same patch id where the writer takes one.
3. Across the whole plugin tree, every direct write of a setting's entry sits
   inside that setting's writer, or inside one of the named exceptions: the
   one-time config migrations in the Plugin class's Awake (they run before any
   writer's effect exists), the heavy-font weight self-test (bug 159's lever,
   which suspends saving and puts the value back), and the settings drive
   harness's T4 prompt route, which clears the stored language so the
   first-run prompt shows and puts the value back afterwards.
4. A local alias of an entry (`var e = Plugin.X;`) and a ConfigEntry
   parameter are never written through, so gate 3's by-name scan cannot be
   walked around.
"""
from __future__ import annotations

import functools
import re
from pathlib import Path

import pytest

from _cs_structure import CsParseError, mask_code, strip_comments_only

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PLUGIN = REPO / "plugin"
WRITERS_G = PLUGIN / "SettingsDescriptorWriters.g.cs"

ROW_CALL = re.compile(r"\b(SettingsSwitch|SettingsSegmented|SettingsSlider|SettingsDropdown|AddPerfRow)\s*\(")
ASSIGN = re.compile(r"\.Value\s*=(?![=>])")
LITERAL = re.compile(r'"((?:[^"\\]|\\.)*)"')

# Each setting's ONE writer: the entry it stores -> (file, enclosing class or
# None for the file's only match, writer signature).
OWNER = {
    "ShowRegionPing": ("NativeUI.cs", None, "internal static void SetShowRegionPing(bool on)"),
    "LagNoticesEnabled": ("LagNotices.cs", "class LagNotices", "internal static void SetEnabled(bool on)"),
    "ShowInputOverlay": ("NativeUI.cs", None, "internal static void SetShowInputOverlay(bool on)"),
    "ShowBlockDebug": ("NativeUI.cs", None, "internal static void SetShowBlockDebug(bool on)"),
    "ShowNotifications": ("NativeUI.cs", None, "internal static void SetShowNotifications(bool on)"),
    "MuteAudioInBackground": ("NativeUI.cs", None, "internal static void SetMuteAudioInBackground(bool on)"),
    "MusicCreditToast": ("NativeUI.cs", None, "internal static void SetMusicCreditToast(bool on)"),
    "ShowTrails": ("TrailRenderer.cs", "class TrailCosmetic", "internal static void SetShowTrails(bool on)"),
    "ShowPlayerColors": ("PlayerColorCosmetic.cs", "class PlayerColorCosmetic", "internal static void SetShowPlayerColors(bool on)"),
    "AnimatedCosmetics": ("PlayerEffectCosmetic.cs", "class PlayerEffectCosmetic", "internal static void SetAnimatedCosmetics(bool on)"),
    "ChromaticAberrationEnabled": ("Plugin.cs", "class ChromaticAberrationSetting", "internal static void Set(bool on)"),
    "MapLightingEnabled": ("Plugin.cs", "class RenderPerfSettings", "internal static void SetLighting(bool on)"),
    "MapShadowsEnabled": ("Plugin.cs", "class RenderPerfSettings", "internal static void SetShadows(bool on)"),
    "ShowFps": ("NativeUI.cs", None, "internal static void SetShowFps(bool on)"),
    "CapFpsUnfocused": ("NativeUI.cs", None, "internal static void SetCapFpsUnfocused(bool on)"),
    "DeepIdleUnfocused": ("NativeUI.cs", None, "internal static void SetDeepIdleUnfocused(bool on)"),
    "PerfOptimizations": ("PerfPatches.cs", None, "internal static void SetPatch(string id, bool value)"),
    "PerfStunPlayerNullGuard": ("PerfPatches.cs", None, "internal static void SetPatch(string id, bool value)"),
    "PerfDespawnOffscreenBullets": ("PerfPatches.cs", None, "internal static void SetPatch(string id, bool value)"),
    "PerfSwallowHitSoundNREs": ("PerfPatches.cs", None, "internal static void SetPatch(string id, bool value)"),
    "PerfSwallowEdgeBounceNREs": ("PerfPatches.cs", None, "internal static void SetPatch(string id, bool value)"),
    "PerfSkipMenuUpdateInMatch": ("PerfPatches.cs", None, "internal static void SetPatch(string id, bool value)"),
    "PerfBulletHitParticleCap": ("PerfPatches.cs", None, "internal static void SetPatch(string id, bool value)"),
    "PerfClampObjectPoolInit": ("PerfPatches.cs", None, "internal static void SetPatch(string id, bool value)"),
    "ShowInactiveOnBoards": ("NativeUI.cs", None, "internal static void SetShowInactiveOnBoards(bool on)"),
    "AutoLogUploadEnabled": ("AutoLogUpload.cs", "class AutoLogUpload", "internal static void SetEnabled(bool on)"),
    "DataConsent": ("NativeUI.Settings.cs", "class ConsentSetting", "internal static void Set(bool granted)"),
    "MenuMusicMode": ("NativeUI.cs", None, "internal static void SetMenuMusicMode(string id)"),
    "ModLanguage": ("NativeUI.cs", None, "internal static void SetModLanguage(string id)"),
    "UiDateFormat": ("NativeUI.cs", None, "internal static void SetUiDateFormat(string id)"),
    "UiHeavyFont": ("NativeUI.cs", None, "internal static void SetUiHeavyFont(bool on)"),
    "ShowIngameChat": ("CompetitiveUI.cs", None, "internal static void SetChatOverlayMode(ChatOverlayMode next)"),
    "ChatOverlaySeconds": ("Plugin.cs", "class Plugin : BaseUnityPlugin", "public static void SetChatOverlaySeconds(float s)"),
    "BloomStrength": ("Plugin.cs", "class BloomStrengthSetting", "internal static void Set(string level)"),
    "ScreenShakeStrength": ("PerfPatches.cs", "class ScreenshakerDisablePatch", "internal static void Set(string level)"),
}

# The only other places a setting's entry may be written, each with its reason.
AWAKE = ("Plugin.cs", "class Plugin : BaseUnityPlugin", "private void Awake()",
         "a one-time config migration under its own marker, before any writer's effect exists")
EXCEPTIONS = {
    "MuteAudioInBackground": [AWAKE],
    "PerfDespawnOffscreenBullets": [AWAKE],
    "MenuMusicMode": [AWAKE],
    "ScreenShakeStrength": [AWAKE],
    "UiHeavyFont": [("NativeUI.cs", None, "internal static int WeightSelfTest(Action<string> log, out int fail)",
                     "bug 159's weight self-test: saving is suspended and the player's value put back")],
    "ModLanguage": [("NativeUI.SettingsDrive.cs", None, "private static void DrvClearStoredLanguage()",
                     "the drive harness's T4 prompt route: the stored language cleared so the first-run prompt shows"),
                    ("NativeUI.SettingsDrive.cs", None, "private static void DrvPutBackStoredLanguage(string saved)",
                     "the drive harness's T4 prompt route: the stored language put back as T4 found it")],
}


@functools.lru_cache(maxsize=None)
def _text(name: str) -> str:
    return (PLUGIN / name).read_text(encoding="utf-8")


@functools.lru_cache(maxsize=None)
def _masked(name: str) -> str:
    return mask_code(_text(name))


@functools.lru_cache(maxsize=None)
def _literal(name: str) -> str:
    return strip_comments_only(_text(name))


def _files(needle) -> list:
    """The plugin files whose RAW text holds the needle: a superset of the
    files whose masked text does, so nothing the masked scan would find is
    skipped by the prefilter."""
    return [p.name for p in sorted(PLUGIN.glob("*.cs")) if needle.search(_text(p.name))]


def _line(name: str, i: int) -> int:
    return _text(name).count("\n", 0, i) + 1


def _blocks(masked: str, signature: str, lo: int = 0, hi: int = None) -> list:
    """Every brace-balanced block following `signature` inside [lo, hi), the
    same walk as _cs_structure.method_spans, run on the cached mask."""
    hi = len(masked) if hi is None else hi
    out, search = [], lo
    while True:
        start = masked.find(signature, search, hi)
        if start == -1:
            return out
        brace = masked.find("{", start + len(signature), hi)
        if brace == -1:
            raise CsParseError("no block opens after %r" % signature)
        depth = 0
        for i in range(brace, hi):
            if masked[i] == "{":
                depth += 1
            elif masked[i] == "}":
                depth -= 1
                if depth == 0:
                    out.append((brace, i + 1))
                    break
        else:
            raise CsParseError("unbalanced braces after %r" % signature)
        search = out[-1][1]


@functools.lru_cache(maxsize=None)
def _span(name: str, klass, signature: str) -> tuple:
    """The ONE block of `signature` in `name` (inside `klass` when named)."""
    masked = _masked(name)
    lo, hi = 0, len(masked)
    if klass is not None:
        classes = _blocks(masked, klass)
        if len(classes) != 1:
            raise CsParseError("%d blocks match %r in %s" % (len(classes), klass, name))
        lo, hi = classes[0]
    found = _blocks(masked, signature, lo, hi)
    if len(found) != 1:
        raise CsParseError("%d blocks match %r in %s%s" % (
            len(found), signature, name, " (" + klass + ")" if klass else ""))
    return found[0]


def _close(masked: str, brace: int) -> int:
    """One past the brace that closes the block opening at `brace`."""
    depth = 0
    for i in range(brace, len(masked)):
        if masked[i] == "{":
            depth += 1
        elif masked[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    raise CsParseError("unbalanced braces from offset %d" % brace)


def _enclosing_block(masked: str, i: int) -> tuple:
    """The innermost brace block holding offset i."""
    depth = 0
    for j in range(i - 1, -1, -1):
        if masked[j] == "}":
            depth += 1
        elif masked[j] == "{":
            if depth == 0:
                return j, _close(masked, j)
            depth -= 1
    raise CsParseError("offset %d is in no block" % i)


def _is_definition(masked: str, start: int) -> bool:
    """A constructor's own declaration (or the perf rows' local function),
    not a call: only modifiers and a type precede the name on its line."""
    head = masked[masked.rfind("\n", 0, start) + 1:start].strip()
    return bool(head) and re.fullmatch(r"[\w<>\[\], ]+", head) is not None \
        and "return" not in head.split()


def _row_calls() -> dict:
    """{row key: (file, line, call with literals, masked call)} for every typed
    row constructor call in the plugin tree. The perf rows are keyed
    "SPerf_<id>" from their AddPerfRow("<id>", ...) calls; AddPerfRow's own
    SettingsSwitch("SPerf_" + id, ...) builds no key of its own."""
    rows = {}
    for name in _files(ROW_CALL):
        lit, masked = _literal(name), _masked(name)
        for m in ROW_CALL.finditer(masked):
            if _is_definition(masked, m.start()):
                continue
            depth, i = 0, m.end() - 1
            while i < len(masked):
                if masked[i] == "(":
                    depth += 1
                elif masked[i] == ")":
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            else:
                raise CsParseError("unterminated %s call in %s" % (m.group(1), name))
            call_lit, call_masked = lit[m.start():i + 1], masked[m.start():i + 1]
            first = LITERAL.search(call_lit)
            if first is None:
                raise CsParseError("%s call without a key literal at %s:%d" % (
                    m.group(1), name, _line(name, m.start())))
            if call_lit[first.end():].lstrip().startswith("+"):
                continue   # AddPerfRow's own body: "SPerf_" + id
            key = ("SPerf_" + first.group(1)) if m.group(1) == "AddPerfRow" else first.group(1)
            if key in rows:
                raise CsParseError("two constructor calls for row %r (%s:%d and %s:%d)" % (
                    key, rows[key][0], rows[key][1], name, _line(name, m.start())))
            rows[key] = (name, _line(name, m.start()), call_lit, call_masked)
    return rows


def _reset_writers() -> dict:
    """{row key: (writer token the handler must call, patch-id literal or None)}
    from InvokeReset. NativeUI's own writers are called unqualified inside
    NativeUI; any other writer is matched by its last two name parts."""
    src = strip_comments_only(WRITERS_G.read_text(encoding="utf-8"))
    body = src[src.index("internal static bool InvokeReset(string key)"):]
    body = body[:body.index("default: return false;")]
    out = {}
    for key, dotted, args in re.findall(r'case "(\w+)": ([\w.]+)\(([^()]*)\); return true;', body):
        parts = dotted.split(".")
        token = parts[-1] if parts[0] == "NativeUI" and len(parts) == 2 else ".".join(parts[-2:])
        arg = LITERAL.match(args.split(",")[0].strip()) if "," in args else None
        out[key] = (token, arg.group(1) if arg else None)
    if len(out) != body.count('case "'):
        raise CsParseError("InvokeReset has %d cases but %d parsed" % (body.count('case "'), len(out)))
    return out


ROWS = _row_calls()
RESETS = _reset_writers()
WRITE_FILES = _files(re.compile(r"\b(" + "|".join(OWNER) + r")\.Value\b"))


def test_the_scans_are_not_vacuous():
    """Every bulk-reset row is found as a constructor call, and the scan sees
    the page's switch, segmented, slider and dropdown rows."""
    missing = sorted(set(RESETS) - set(ROWS))
    assert not missing, "bulk-reset rows with no constructor call found: %s" % missing
    assert len(RESETS) >= 33, "InvokeReset parsed to %d rows" % len(RESETS)
    assert len(ROWS) >= 45, "only %d row constructor calls found" % len(ROWS)
    kinds = {ROW_CALL.match(c).group(1) for _, _, _, c in ROWS.values()}
    assert kinds == {"SettingsSwitch", "SettingsSegmented", "SettingsSlider", "SettingsDropdown", "AddPerfRow"}, kinds


@pytest.mark.parametrize("key", sorted(ROWS))
def test_row_handler_writes_no_config_entry(key):
    name, line, _, call_masked = ROWS[key]
    hit = ASSIGN.search(call_masked)
    assert hit is None, (
        "row %s (%s:%d) assigns a ConfigEntry in its own handler; it must call the "
        "setting's writer instead: %r" % (
            key, name, line, call_masked[max(0, hit.start() - 60):hit.end() + 20].strip()))


@pytest.mark.parametrize("key", sorted(RESETS))
def test_bulk_row_calls_the_writer_its_reset_calls(key):
    token, patch_id = RESETS[key]
    name, line, call_lit, call_masked = ROWS[key]
    assert re.search(r"(?<!\w)" + re.escape(token) + r"\s*\(", call_masked), (
        "row %s (%s:%d) never calls %s, the writer its reset calls" % (key, name, line, token))
    if patch_id is not None:
        assert re.search(re.escape(token) + r'\s*\(\s*"' + re.escape(patch_id) + '"', call_lit), (
            "row %s (%s:%d) calls %s without its id %r" % (key, name, line, token, patch_id))


def test_every_entry_a_row_reads_has_an_owner():
    """A row added later whose getter reads an entry this file does not own
    fails here, so gate 3 can never silently skip a new setting."""
    read = set()
    for _, _, _, call_masked in ROWS.values():
        read.update(re.findall(r"\bPlugin\.(\w+)\.Value\b", call_masked))
    assert len(read) >= 30, "row getters read only %d entries: the scan is broken" % len(read)
    unowned = sorted(read - set(OWNER))
    assert not unowned, "entries read by settings rows with no owning writer listed: %s" % unowned


@pytest.mark.parametrize("entry", sorted(OWNER))
def test_entry_is_written_only_by_its_writer(entry):
    ofile, oclass, osig = OWNER[entry]
    owner = _span(ofile, oclass, osig)
    allowed = [(ofile, owner)] + [(f, _span(f, k, s)) for f, k, s, _ in EXCEPTIONS.get(entry, [])]
    rx = re.compile(r"\b" + re.escape(entry) + r"\.Value\s*=(?![=>])")
    owner_writes, stray = 0, []
    for name in WRITE_FILES:
        for hit in rx.finditer(_masked(name)):
            i = hit.start()
            if name == ofile and owner[0] <= i < owner[1]:
                owner_writes += 1
            elif not any(f == name and a <= i < b for f, (a, b) in allowed):
                stray.append("%s:%d" % (name, _line(name, i)))
    assert owner_writes >= 1, "%s's writer %s (%s) writes no %s.Value" % (entry, osig, ofile, entry)
    assert not stray, "%s is written outside its one writer (%s): %s" % (entry, osig, ", ".join(stray))


def test_no_alias_or_entry_parameter_is_written_through():
    alias = re.compile(r"\b(\w+)\s*=\s*(?:[\w.]*\.)?Plugin\.(" + "|".join(OWNER) + r")\s*;")
    param = re.compile(r"\(([^()]*,\s*)?(?:BepInEx\.Configuration\.)?ConfigEntry<[^<>]+>\s+(\w+)[^()]*\)\s*\{")
    seen, bad = 0, []
    for name in _files(re.compile(r"Plugin\.(" + "|".join(OWNER) + r")\s*;|ConfigEntry<")):
        masked = _masked(name)
        for m in alias.finditer(masked):
            seen += 1
            a, b = _enclosing_block(masked, m.start())   # a local's scope is its block
            for w in re.finditer(r"\b" + re.escape(m.group(1)) + r"\.Value\s*=(?![=>])", masked[a:b]):
                bad.append("%s:%d (alias %s of %s)" % (name, _line(name, a + w.start()), m.group(1), m.group(2)))
        for m in param.finditer(masked):
            seen += 1
            a = m.end() - 1
            b = _close(masked, a)
            for w in re.finditer(r"\b" + re.escape(m.group(2)) + r"\.Value\s*=(?![=>])", masked[a:b]):
                bad.append("%s:%d (parameter %s)" % (name, _line(name, a + w.start()), m.group(2)))
    assert seen >= 3, "only %d aliases/parameters seen: the scan is broken" % seen
    assert not bad, "an entry is written through an alias or parameter: %s" % bad
