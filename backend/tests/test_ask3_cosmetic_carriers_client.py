"""Ask 3: each cosmetic carrier records what it wrote, and the pick body repaints.

Source claims for the client half of the ask 3 lane (the seat-b design note
ASK3-DESIGN.md, sections 3 to 5, and the integrator's 09:57:48Z ruling). The
rules themselves are executed by the harness suite `cosmeticcarrier`
(test_client_rules_harness.py); these claims hold the wiring around them.

Each claim is a function of the plugin's source text that returns its
problems. It runs on the tree as it is (no problems), on a control (a neutral
edit: still none) and on mutants, one per route or rule it is about, each of
which must produce a problem (learning #391: a check that cannot fail proves
nothing).
"""
import re
from pathlib import Path

import pytest

from _cs_structure import mask_code, strip_comments_only

REPO = Path(__file__).resolve().parents[2]
PLUGIN = REPO / "plugin"


def _tree():
    return {p.name: p.read_text(encoding="utf-8").replace("\r\n", "\n")
            for p in sorted(PLUGIN.glob("*.cs"))}


FILES = _tree()


_MASKS = {}


def _masks(text):
    """(code mask, comments stripped) of one file's text, computed once per text.

    Both keep the text's length and newlines (the _cs_structure contract), so
    an offset found in one is an offset into the other and into the text."""
    got = _MASKS.get(text)
    if got is None:
        got = _MASKS[text] = (mask_code(text), strip_comments_only(text))
        assert len(got[0]) == len(got[1]) == len(text)
    return got


def _spans(text, sig):
    """Every block that follows `sig` in code, as (open brace, end) offsets."""
    masked = _masks(text)[0]
    out, search = [], 0
    while True:
        start = masked.find(sig, search)
        if start == -1:
            return out
        open_brace = masked.find("{", start + len(sig))
        assert open_brace != -1, "no block opens after %r" % sig
        depth = 0
        for i in range(open_brace, len(masked)):
            if masked[i] == "{":
                depth += 1
            elif masked[i] == "}":
                depth -= 1
                if depth == 0:
                    out.append((open_brace, i + 1))
                    break
        else:
            raise AssertionError("unbalanced block after %r" % sig)
        search = out[-1][1]


def _code(text, sig=None):
    """A block (or the whole text) with comments removed, literals kept."""
    stripped = _masks(text)[1]
    if sig is None:
        return stripped
    spans = _spans(text, sig)
    assert len(spans) == 1, "%d blocks follow %r" % (len(spans), sig)
    a, b = spans[0]
    return stripped[a:b]


def _expr(text, sig):
    """The expression body after `sig` (an `=>` member), up to its `;`."""
    masked, stripped = _masks(text)
    at = masked.index(sig)
    arrow = masked.index("=>", at)
    end = masked.index(";", arrow)
    return stripped[arrow + 2:end]


# -- C1: each publisher records, after its write, and nothing else records --

PUBLISHERS = {
    "Color": ("PlayerColorCosmetic.cs", "public static void PublishLocalProps()",
              "CosmeticCarrierLedger.Shared.Wrote(CosmeticCarrier.Color, CarrierValue(s));"),
    "Trail": ("TrailRenderer.cs", "public static void PublishLocalProps()",
              "CosmeticCarrierLedger.Shared.Wrote(CosmeticCarrier.Trail, CarrierValue(s));"),
    "Effect": ("PlayerEffectCosmetic.cs", "public static void PublishLocalProps()",
               "CosmeticCarrierLedger.Shared.Wrote(CosmeticCarrier.Effect, CarrierValue(s));"),
    "Nametag": ("NametagStyler.cs", "public static void PublishToPhoton()",
                "CosmeticCarrierLedger.Shared.Wrote(CosmeticCarrier.Nametag, CosmeticCarrierLedger.NametagValue(skus));"),
    "Cursor": ("CursorColorCosmetic.cs", "public static void ApplyFromStats()",
               "CosmeticCarrierLedger.Shared.Wrote(CosmeticCarrier.Cursor, CosmeticCarrierLedger.CursorValue(sku, hex));"),
}
# R1 (M1): a record follows confirmed completion only. The props publishers
# return before it when Photon refuses the write; the nametag's flag is the
# props call's own answer (or true when nothing needed writing); the cursor
# records only when Apply answers true, and Apply answers false on failure.
REFUSAL = re.compile(r"if \(!PhotonNetwork\.LocalPlayer\.SetCustomProperties\(props\)\)\s*\{[^{}]*?\breturn;\s*\}")
NAMETAG_ASSIGNS = ["bool propsWritten = false;",
                   "propsWritten = PhotonNetwork.LocalPlayer.SetCustomProperties(upd);",
                   "else propsWritten = true;"]
CURSOR_APPLY_SIG = "public static bool Apply(string sku, string hex)"


def claim_publishers_record(files):
    out = []
    for carrier, (fname, sig, record) in PUBLISHERS.items():
        body = _code(files[fname], sig)
        if body.count(record) != 1:
            out.append("%s: the publisher records %d times" % (carrier, body.count(record)))
            continue
        at = body.index(record)
        if carrier in ("Color", "Trail", "Effect"):
            refusals = list(REFUSAL.finditer(body))
            if len(refusals) != 1 or body.count("SetCustomProperties(") != 1 or refusals[0].end() > at:
                out.append("%s: the record does not follow the one write, behind its refusal's return" % carrier)
            if body.count("var s = ApiClient.CachedPlayerStats;") != 1:
                out.append("%s: the record's snapshot is not the one the write reads" % carrier)
        if carrier == "Nametag":
            assigns = re.findall(r"(?:bool |else )?propsWritten = [^;]*;", body)
            guard = body.find("if (propsWritten)")
            if assigns != NAMETAG_ASSIGNS or not (body.index(NAMETAG_ASSIGNS[1]) < guard < at):
                out.append("Nametag: the record is not behind a props write that Photon sent")
        if carrier == "Cursor":
            if not re.search(r"if \(Apply\(sku, hex\)\)\s*" + re.escape(record), body):
                out.append("Cursor: the record does not follow a completed Apply")
            apply = _code(files[fname], CURSOR_APPLY_SIG).rstrip()
            tail = apply[:-1].rstrip()
            if not tail.endswith("return false;") or apply.count("return _activeTex != null;") != 1:
                out.append("Cursor: Apply does not answer false when it did not apply")
        needle = "Wrote(CosmeticCarrier.%s," % carrier
        writers = [n for n, txt in files.items() if needle in _masks(txt)[1]]
        if writers != [fname]:
            out.append("%s: recorded from %s" % (carrier, writers))
    return out


# -- C2: each carrier's value reads exactly the fields its publisher writes --

def _fields(text):
    return sorted(set(re.findall(r"\?\.(active_\w+)", text)))


def claim_values_match_the_writes(files):
    out = []
    for carrier, (fname, sig, _r) in PUBLISHERS.items():
        wrote = _fields(_code(files[fname], sig))
        value = _fields(_expr(files[fname], "internal static string CarrierValue(ApiClient.PlayerStatsData s)"))
        if not wrote or wrote != value:
            out.append("%s: the publisher reads %s, its value %s" % (carrier, wrote, value))
    return out


# -- C3: the refresh asks the ledger, carrier by carrier, with that carrier's value --

REFRESH = [
    ("Trail", "TrailCosmetic", "TrailCosmetic.PublishLocalProps();"),
    ("Color", "PlayerColorCosmetic", "PlayerColorCosmetic.PublishLocalProps();"),
    ("Effect", "PlayerEffectCosmetic", "PlayerEffectCosmetic.PublishLocalProps();"),
    ("Cursor", "CursorColorCosmetic", "CursorColorCosmetic.ApplyFromStats();"),
    ("Nametag", "NametagStyler", "NametagStyler.PublishToPhoton();"),
]
OLD_GATE_NAMES = ("cosmeticSig", "_lastPublishedCosmeticSig", "BuildCosmeticSig", "InvalidateCosmeticSig")


def claim_refresh_asks_the_ledger(files):
    out = []
    body = _code(files["ApiClient.cs"], "public static void FetchPlayerStats(string steamId, bool force = false)")
    for need in ("var ledger = CosmeticCarrierLedger.Shared;",
                 "bool spectator = RoomActors.LocalIsSpectator;",
                 "var cached = CachedPlayerStats;"):
        if body.count(need) != 1:
            out.append("the refresh lacks %r" % need)
    for carrier, cls, call in REFRESH:
        cond = "if (ledger.Owes(CosmeticCarrier.%s, %s.CarrierValue(cached), spectator))" % (carrier, cls)
        if body.count(cond) != 1 or body.count(call) != 1:
            out.append("%s: the refresh does not ask the ledger once with its own value" % carrier)
            continue
        between = body[body.index(cond) + len(cond):body.index(call)]
        if re.sub(r"\s+", "", between) != "{try{":
            out.append("%s: its publish is not the body of its Owes test" % carrier)
    for name, text in files.items():
        code = _masks(text)[1]
        for old in OLD_GATE_NAMES:
            if re.search(r"\b%s\b" % old, code):
                out.append("%s still names %s" % (name, old))
    return out


# -- C4: every write of a carrier is its publisher's, and the clear forgets --

KEY = r'"cr_(?:pcolor|trail|effect|nametag)_\w+"'
ALLOWED = {
    "PlayerColorCosmetic.cs": "public static void PublishLocalProps()",
    "TrailRenderer.cs": "public static void PublishLocalProps()",
    "PlayerEffectCosmetic.cs": "public static void PublishLocalProps()",
    "NametagStyler.cs": "public static void PublishToPhoton()",
    "SpectatorSession.cs": "internal static bool StagePreJoinProperties(string localSteamId)",
}


def _carrier_writes(text):
    code = _masks(text)[1]
    consts = set(re.findall(r'const string (PROP_\w+)\s*=\s*' + KEY, code))
    hits = []
    for m in re.finditer(r"\[\s*(" + KEY + r"|PROP_\w+)\s*\]\s*=(?!=)", code):
        if m.group(1).startswith("PROP_") and m.group(1) not in consts:
            continue
        hits.append((m.start(), "key"))
    for m in re.finditer(r"\{\s*" + KEY + r"\s*,", code):
        hits.append((m.start(), "key"))
    for m in re.finditer(r"\bNickName\s*=(?!=)", code):
        hits.append((m.start(), "nick"))
    return code, hits


def claim_only_the_publishers_write(files):
    out = []
    for name, text in files.items():
        code, hits = _carrier_writes(text)
        spans = _spans(text, ALLOWED[name]) if name in ALLOWED else []
        for at, kind in hits:
            if any(a <= at < b for a, b in spans):
                continue
            if kind == "nick":
                end = code.index(";", at) + 1
                if re.match(r"\s*NametagStyler\.PublishToPhoton\(\);", code[end:]):
                    continue   # a repair of the raw name, re-styled and recorded at once
            line = text.count("\n", 0, at) + 1
            out.append("%s:%d writes a carrier outside its publisher" % (name, line))
    stage = _code(files["SpectatorSession.cs"], ALLOWED["SpectatorSession.cs"])
    clear = "PhotonNetwork.LocalPlayer.SetCustomProperties(props);"
    if not re.search(re.escape(clear) + r"\s*CosmeticCarrierLedger\.Shared\.ForgetRoomCarriers\(\);", stage):
        out.append("the spectator staging's clear is not followed by the ledger's forget")
    return out


# -- C5 (S2): the pick body takes the in-match bodies' property-change path --

PCC_SIG = ("public static void OnPlayerPropertiesChanged(Photon.Realtime.Player target, "
           "ExitGames.Client.Photon.Hashtable changed)")
SUB = "try { CardPickBodyTinter.OnPickerPropertiesChanged(target.ActorNumber, colourChanged); } catch { }"
PAINT_SIG = ("private static void Paint(GameObject visualizer, int pickerTeamID, int pickerID, "
             "int pickerActor, string why)")


def _in_order(body, needles):
    at = -1
    for n in needles:
        if body.count(n) != 1 or body.index(n) < at:
            return False
        at = body.index(n)
    return True


def claim_pick_body_repaints(files):
    out = []
    pcc = _code(files["PlayerColorCosmetic.cs"], PCC_SIG)
    if not _in_order(pcc, ["bool colourChanged = changed.ContainsKey(PROP_SKU) || changed.ContainsKey(PROP_COLOR);",
                           SUB, "if (!colourChanged) return;",
                           "target.ActorNumber == PhotonNetwork.LocalPlayer.ActorNumber) return;"]):
        out.append("the colour path does not hand every colour change to the pick body before its returns")
    cb = _code(files["TrailRenderer.cs"], "public void OnPlayerPropertiesUpdate(")
    if "PlayerColorCosmetic.OnPlayerPropertiesChanged(target, changedProps);" not in cb:
        out.append("the Photon callback no longer reaches the colour path")
    tin = files["Plugin.cs"]
    entry = _code(tin, "internal static void OnPickerPropertiesChanged(int actor, bool colourKeyChanged)")
    if not _in_order(entry, ["bool alive = _shownBody != null;",
                             "if (!Binding.ShouldRepaint(alive, actor, colourKeyChanged)) return;",
                             'Paint(_shownBody, _shownTeam, _shownPickerID, Binding.BoundActor, "property");']):
        out.append("the repaint entry does not ask the binding before it paints")
    show = _code(tin, "public static IEnumerator RetintAfterChildrenSpawn(")
    if not _in_order(show, ["if (!Binding.TryBind(binding, pickerActor)) yield break;", "_shownBody = visualizer;",
                            'Paint(visualizer, pickerTeamID, pickerID, pickerActor, "show");',
                            "Binding.FirstPaintFinished(binding);"]):
        out.append("the Show coroutine does not bind its own body around its first paint")
    # R1 (H2): a Show resets the binding before any return of its postfix, and
    # schedules its paint with that Show's generation; a Hide ends the binding.
    begin = _code(tin, "internal static int BeginShow()")
    if "_shownBody = null;" not in begin or "return Binding.BeginShow();" not in begin:
        out.append("a Show does not reset the binding")
    hidden = _code(tin, "internal static void OnHidden()")
    if "Binding.Hide();" not in hidden or "_shownBody = null;" not in hidden:
        out.append("a Hide does not end the binding")
    post = _code(tin, "class CardChoiceVisuals_Show_Competitive_Patch")
    sig = post.find("static void Postfix(CardChoiceVisuals __instance, int pickerID)")
    first = post.find("int tintBinding = CardPickBodyTinter.BeginShow();")
    ret = post.find("return;", sig)
    launch = re.search(r"StartCoroutine\(\s*CardPickBodyTinter\.RetintAfterChildrenSpawn\(skin, picker\.TeamID, "
                       r"pickerID, pv\.Owner\.ActorNumber, tintBinding\)\)", post)
    if not (-1 < sig < first < ret) or launch is None or launch.start() < first:
        out.append("the Show postfix does not reset the binding before its returns and schedule its paint with it")
    if "CardPickBodyTinter.OnHidden();" not in _code(tin, "class CardChoiceVisuals_Hide_PopupCarrier_Patch"):
        out.append("the Hide postfix does not end the binding")
    paint = _code(tin, PAINT_SIG)
    if not _in_order(paint, ["Color? before = _paintedCustom;",
                             "|| (before.HasValue && IsCloseHue(c, before.Value));",
                             "main.startColor = sc;",
                             "if (!MapPhysicalColorPatch.InMapTransition())",
                             "liveParticles += RecolourLiveParticles(ps, desired, looksWrong);",
                             "_paintedCustom = hasCustom ? desired : (Color?)null;"]):
        out.append("a repaint does not replace the last paint's colour, live particles included, outside the transition")
    # R1 (M2): the live particles are rewritten in place with their own alpha (#108), never cleared (#96).
    live = _code(tin, "private static int RecolourLiveParticles(ParticleSystem ps, Color desired, Func<Color, bool> looksWrong)")
    if ("_liveBuf[i].startColor = new Color32(r, g, b, cur.a);" not in live or "ps.SetParticles(_liveBuf, n);" not in live
            or any(x in live for x in (".Clear(", ".Stop(", ".Pause(", ".Simulate("))):
        out.append("the live recolour does not rewrite the particles in place with their own alpha")
    return out


# -- C6 (F2 not taken): the pick body reads the room property for every picker --

def claim_pick_reads_the_room_for_every_picker(files):
    paint = _code(files["Plugin.cs"], PAINT_SIG)
    out = []
    if 'pl.CustomProperties["cr_pcolor_color"]' not in paint:
        out.append("the pick body no longer reads the room property")
    for local in ("CachedPlayerStats", "CarrierValue(", ".IsLocal", "LocalPlayer"):
        if local in paint:
            out.append("the pick body treats the local picker apart (%s)" % local)
    return out


# -- C7 (R1 H1, M3): a spectator writes no carrier, on any route --

SPECTATOR_GUARD = "if (RoomActors.LocalIsSpectator) return;"
SPECTATOR_ROUTES = {
    "colour": ("PlayerColorCosmetic.cs", "public static void PublishLocalProps()", "SetCustomProperties(props)"),
    "trail": ("TrailRenderer.cs", "public static void PublishLocalProps()", "SetCustomProperties(props)"),
    "effect": ("PlayerEffectCosmetic.cs", "public static void PublishLocalProps()", "SetCustomProperties(props)"),
    "nametag": ("NametagStyler.cs", "public static void PublishToPhoton()", "PhotonNetwork.LocalPlayer.NickName = styled;"),
    "name repair": ("VanillaFixes.cs", "private void CheckLocalNickname()", "PhotonNetwork.NickName = persona;"),
}


def claim_spectators_write_nothing(files):
    out = []
    for route, (fname, sig, write) in SPECTATOR_ROUTES.items():
        body = _code(files[fname], sig)
        w, g = body.find(write), body.find(SPECTATOR_GUARD)
        if w == -1:
            out.append("%s: its write is not in %s" % (route, fname))
        elif g == -1 or g > w:
            out.append("%s: no spectator guard before its write" % route)
    return out


CLAIMS = {
    "publishers_record": claim_publishers_record,
    "values_match_the_writes": claim_values_match_the_writes,
    "refresh_asks_the_ledger": claim_refresh_asks_the_ledger,
    "only_the_publishers_write": claim_only_the_publishers_write,
    "pick_body_repaints": claim_pick_body_repaints,
    "pick_reads_the_room_for_every_picker": claim_pick_reads_the_room_for_every_picker,
    "spectators_write_nothing": claim_spectators_write_nothing,
}


# -- the mutants: (claim, what the mutant does, [(file, old, new), ...]) ----

def _drop(fname, line):
    return [(fname, line, "")]


REC_COLOR = "                CosmeticCarrierLedger.Shared.Wrote(CosmeticCarrier.Color, CarrierValue(s));\n"
JOIN_COLOR = "                try { PlayerColorCosmetic.PublishLocalProps(); } catch { }\n"
DIRECT = 'var h = new ExitGames.Client.Photon.Hashtable(); h["%s"] = ""; PhotonNetwork.LocalPlayer.SetCustomProperties(h);'
LOCAL_RETURN = ("            if (PhotonNetwork.LocalPlayer != null && target.ActorNumber == "
                "PhotonNetwork.LocalPlayer.ActorNumber) return;\n")

REFUSED_BLOCK = ("                if (!PhotonNetwork.LocalPlayer.SetCustomProperties(props))\n                {\n"
                 '                    Plugin.Log.LogWarning("%s Publish not sent (Photon refused it); the next refresh owes it");\n'
                 "                    return;\n                }\n")
WRITE_PROPS = "                PhotonNetwork.LocalPlayer.SetCustomProperties(props);\n"
OFFLINE_RETURN = ("                if (PhotonNetwork.OfflineMode || !PhotonNetwork.InRoom) return;\n"
                  "                var pm = PlayerManager.instance;\n")
LIVE_CALL = ("                        if (!MapPhysicalColorPatch.InMapTransition())\n"
             "                            liveParticles += RecolourLiveParticles(ps, desired, looksWrong);\n")
GUARD16 = "                if (RoomActors.LocalIsSpectator) return;\n"
REPAIR_GUARD = ("            // leaves a spectator's name as it is, as PublishToPhoton does.\n"
                "            if (RoomActors.LocalIsSpectator) return;\n")

MUTANTS = [
    # C1: one per publisher, and a record without a write
    ("publishers_record", "the colour publisher does not record", _drop("PlayerColorCosmetic.cs", REC_COLOR)),
    ("publishers_record", "the trail publisher does not record", _drop(
        "TrailRenderer.cs", "                CosmeticCarrierLedger.Shared.Wrote(CosmeticCarrier.Trail, CarrierValue(s));\n")),
    ("publishers_record", "the effect publisher does not record", _drop(
        "PlayerEffectCosmetic.cs", "                CosmeticCarrierLedger.Shared.Wrote(CosmeticCarrier.Effect, CarrierValue(s));\n")),
    ("publishers_record", "the nametag publisher does not record", _drop(
        "NametagStyler.cs", "                    CosmeticCarrierLedger.Shared.Wrote(CosmeticCarrier.Nametag, "
                            "CosmeticCarrierLedger.NametagValue(skus));\n")),
    ("publishers_record", "the nametag records though Photon refused its props write", [
        ("NametagStyler.cs", "                        propsWritten = PhotonNetwork.LocalPlayer.SetCustomProperties(upd);\n",
         "                        PhotonNetwork.LocalPlayer.SetCustomProperties(upd);\n                        propsWritten = true;\n")]),
    ("publishers_record", "the cursor does not record", _drop(
        "CursorColorCosmetic.cs", "                CosmeticCarrierLedger.Shared.Wrote(CosmeticCarrier.Cursor, "
                                  "CosmeticCarrierLedger.CursorValue(sku, hex));\n")),
    ("publishers_record", "the colour publisher records before it writes", [
        ("PlayerColorCosmetic.cs", REC_COLOR, ""),
        ("PlayerColorCosmetic.cs", "                if (!PhotonNetwork.LocalPlayer.SetCustomProperties(props))\n",
         REC_COLOR + "                if (!PhotonNetwork.LocalPlayer.SetCustomProperties(props))\n")]),
    ("publishers_record", "the room join records without writing", [
        ("GameStateWatcher.cs", JOIN_COLOR,
         JOIN_COLOR + '                CosmeticCarrierLedger.Shared.Wrote(CosmeticCarrier.Color, "");\n')]),
    # C2: a value that misses or swaps a field its publisher writes
    ("values_match_the_writes", "the trail's value leaves out the price", [
        ("TrailRenderer.cs", "TrailValue(s?.active_trail_sku, s?.active_trail_color, s?.active_trail_price ?? 0);",
         "TrailValue(s?.active_trail_sku, s?.active_trail_color, 0);")]),
    ("values_match_the_writes", "the colour's value reads the cursor's hex", [
        ("PlayerColorCosmetic.cs", "ColorValue(s?.active_player_color_sku, s?.active_player_color_hex);",
         "ColorValue(s?.active_player_color_sku, s?.active_cursor_color_hex);")]),
    ("values_match_the_writes", "the cursor's value leaves out the hex", [
        ("CursorColorCosmetic.cs", "CursorValue(s?.active_cursor_color_sku, s?.active_cursor_color_hex);",
         "CursorValue(s?.active_cursor_color_sku, null);")]),
    # C3: the refresh's decision
    ("refresh_asks_the_ledger", "the old rule: one signature, recorded by the refresh", [
        ("ApiClient.cs", "if (ledger.Owes(CosmeticCarrier.Color, PlayerColorCosmetic.CarrierValue(cached), spectator))",
         "if (cosmeticSig != _lastPublishedCosmeticSig)")]),
    ("refresh_asks_the_ledger", "a spectator's refresh publishes", [
        ("ApiClient.cs", "bool spectator = RoomActors.LocalIsSpectator;", "bool spectator = false;")]),
    ("refresh_asks_the_ledger", "the effect asks with the colour's value", [
        ("ApiClient.cs", "if (ledger.Owes(CosmeticCarrier.Effect, PlayerEffectCosmetic.CarrierValue(cached), spectator))",
         "if (ledger.Owes(CosmeticCarrier.Effect, PlayerColorCosmetic.CarrierValue(cached), spectator))")]),
    ("refresh_asks_the_ledger", "the nametag publishes outside its test", [
        ("ApiClient.cs", "                            if (ledger.Owes(CosmeticCarrier.Nametag, NametagStyler.CarrierValue(cached), "
                         "spectator))\n                            {\n                                try { NametagStyler"
                         ".PublishToPhoton(); } catch { }\n                            }\n",
         "                            try { NametagStyler.PublishToPhoton(); } catch { }\n")]),
    # C4: a mutant per route that writes a carrier without its publisher
    ("only_the_publishers_write", "the room join writes the colour directly", [
        ("GameStateWatcher.cs", JOIN_COLOR, "                try { " + DIRECT % "cr_pcolor_color" + " } catch { }\n")]),
    ("only_the_publishers_write", "the 2v2 pre-join writes the trail directly", [
        ("ApiClient.cs", 'try { TrailCosmetic.PublishLocalProps(); } catch (Exception ex) { Plugin.Log.LogWarning($"[2v2] pre-join trail',
         'try { ' + DIRECT % "cr_trail_sku" + ' } catch (Exception ex) { Plugin.Log.LogWarning($"[2v2] pre-join trail')]),
    ("only_the_publishers_write", "the 1v2 pre-join writes the colour directly", [
        ("ApiClient.cs", 'try { PlayerColorCosmetic.PublishLocalProps(); } catch (Exception ex) { Plugin.Log.LogWarning($"[1v2] pre-join pcolor',
         'try { ' + DIRECT % "cr_pcolor_sku" + ' } catch (Exception ex) { Plugin.Log.LogWarning($"[1v2] pre-join pcolor')]),
    ("only_the_publishers_write", "the FFA pre-join writes the NickName directly", [
        ("ApiClient.cs", 'try { NametagStyler.PublishToPhoton(); } catch (Exception ex) { Plugin.Log.LogWarning($"[FFA] pre-join nametag',
         'try { PhotonNetwork.LocalPlayer.NickName = ""; } catch (Exception ex) { Plugin.Log.LogWarning($"[FFA] pre-join nametag')]),
    ("only_the_publishers_write", "the shop equip writes the effect directly", [
        ("NativeUI.cs", "try { PlayerEffectCosmetic.PublishLocalProps(); } catch { }",
         "try { " + DIRECT % "cr_effect_sku" + " } catch { }")]),
    ("only_the_publishers_write", "the refresh writes the colour directly", [
        ("ApiClient.cs", "                                try { PlayerColorCosmetic.PublishLocalProps(); } catch { }\n",
         "                                try { " + DIRECT % "cr_pcolor_color" + " } catch { }\n")]),
    ("only_the_publishers_write", "the name repair leaves the raw NickName unstyled", [
        ("VanillaFixes.cs", "                NametagStyler.PublishToPhoton();\n                RefreshActorLabels(localPlayer);",
         "                RefreshActorLabels(localPlayer);")]),
    ("only_the_publishers_write", "the late nametag route writes the NickName directly", [
        ("Plugin.cs", "NametagStyler.PublishToPhoton();", 'PhotonNetwork.LocalPlayer.NickName = "";')]),
    ("only_the_publishers_write", "a new writer in another file", [
        ("TeamHoldReturn.cs", "if (PhotonNetwork.LocalPlayer != null) PhotonNetwork.LocalPlayer.SetCustomProperties(props);",
         'props["cr_trail_color"] = ""; if (PhotonNetwork.LocalPlayer != null) PhotonNetwork.LocalPlayer.SetCustomProperties(props);')]),
    ("only_the_publishers_write", "the spectator clear forgets nothing", _drop(
        "SpectatorSession.cs", "                CosmeticCarrierLedger.Shared.ForgetRoomCarriers();\n")),
    # C5 (S2): the subscription and the repaint
    ("pick_body_repaints", "the subscription is dropped", _drop("PlayerColorCosmetic.cs", "            " + SUB + "\n")),
    ("pick_body_repaints", "the subscription comes after the colour-key return", [
        ("PlayerColorCosmetic.cs", "            " + SUB + "\n            if (!colourChanged) return;\n",
         "            if (!colourChanged) return;\n            " + SUB + "\n")]),
    ("pick_body_repaints", "the subscription comes after the local-player return", [
        ("PlayerColorCosmetic.cs", "            " + SUB + "\n", ""),
        ("PlayerColorCosmetic.cs", LOCAL_RETURN, LOCAL_RETURN + "            " + SUB + "\n")]),
    ("pick_body_repaints", "the Photon callback stops before the colour path", _drop(
        "TrailRenderer.cs", "            try { PlayerColorCosmetic.OnPlayerPropertiesChanged(target, changedProps); } catch { }\n")),
    ("pick_body_repaints", "the first paint is never marked done", _drop("Plugin.cs", "            Binding.FirstPaintFinished(binding);\n")),
    ("pick_body_repaints", "the repaint skips the rule", [
        ("Plugin.cs", "            if (!Binding.ShouldRepaint(alive, actor, colourKeyChanged)) return;\n",
         "            if (!alive) return;\n")]),
    ("pick_body_repaints", "a repaint leaves the last paint's custom colour", [
        ("Plugin.cs", "\n                    || (before.HasValue && IsCloseHue(c, before.Value));", ";")]),
    # C6 (F2 not taken)
    ("pick_reads_the_room_for_every_picker", "the local picker's colour comes from the cache", [
        ("Plugin.cs", "                        if (pl == null || pl.ActorNumber != pickerActor) continue;\n",
         "                        if (pl == null || pl.ActorNumber != pickerActor) continue;\n"
         "                        if (pl.IsLocal && ApiClient.CachedPlayerStats != null) hasCustom = true;\n")]),
    # R1 (M1): a record after a refused or failed write, one per route
    ("publishers_record", "the colour publisher records after a refused write", [
        ("PlayerColorCosmetic.cs", REFUSED_BLOCK % "[PCOLOR]", WRITE_PROPS)]),
    ("publishers_record", "the trail publisher records after a refused write", [
        ("TrailRenderer.cs", REFUSED_BLOCK % "[TRAIL]", WRITE_PROPS)]),
    ("publishers_record", "the effect publisher records after a refused write", [
        ("PlayerEffectCosmetic.cs", REFUSED_BLOCK % "[EFFECT]", WRITE_PROPS)]),
    ("publishers_record", "the cursor records after a failed Apply", [
        ("CursorColorCosmetic.cs", "            if (Apply(sku, hex))\n", "            Apply(sku, hex);\n")]),
    ("publishers_record", "the cursor's Apply answers true after a failure it caught", [
        ("CursorColorCosmetic.cs", 'Apply failed: {ex.Message}"); }\n            return false;\n',
         'Apply failed: {ex.Message}"); }\n            return true;\n')]),
    ("publishers_record", "the cursor's Apply answers true without a texture", [
        ("CursorColorCosmetic.cs", "return _activeTex != null;", "return true;")]),
    # R1 (H2, M2, M3): the binding's lifecycle, the guard's polarity, the live particles
    ("pick_body_repaints", "the repaint guard's polarity is reversed", [
        ("Plugin.cs", "if (!Binding.ShouldRepaint(alive, actor, colourKeyChanged)) return;",
         "if (Binding.ShouldRepaint(alive, actor, colourKeyChanged)) return;")]),
    ("pick_body_repaints", "the Show never schedules its paint", [
        ("Plugin.cs", "                            Plugin.Instance.StartCoroutine(\n                                CardPickBodyTinter"
                      ".RetintAfterChildrenSpawn(skin, picker.TeamID, pickerID, pv.Owner.ActorNumber, tintBinding));\n", "")]),
    ("pick_body_repaints", "a Show leaves the old binding in place", [
        ("Plugin.cs", "            int tintBinding = CardPickBodyTinter.BeginShow();\n",
         "            int tintBinding = CardPickBodyTinter.Binding.BoundActor;\n")]),
    ("pick_body_repaints", "the binding resets only after the postfix's first return", [
        ("Plugin.cs", "            int tintBinding = CardPickBodyTinter.BeginShow();\n", ""),
        ("Plugin.cs", OFFLINE_RETURN, OFFLINE_RETURN + "                int tintBinding = CardPickBodyTinter.BeginShow();\n")]),
    ("pick_body_repaints", "a superseded coroutine still binds and paints", [
        ("Plugin.cs", "            if (!Binding.TryBind(binding, pickerActor)) yield break;\n",
         "            Binding.TryBind(binding, pickerActor);\n")]),
    ("pick_body_repaints", "the Hide postfix leaves the binding", [
        ("Plugin.cs", "            try { CardPickBodyTinter.OnHidden(); }\n            catch (Exception ex) { Plugin.Log.LogWarning("
                      '$"[CARDPICK-TINT] Hide reset failed: {ex.Message}"); }\n', "")]),
    ("pick_body_repaints", "a Hide resets the body but not the binding", _drop("Plugin.cs", "            Binding.Hide();\n")),
    ("pick_body_repaints", "the live particles keep the old colour", [
        ("Plugin.cs", LIVE_CALL, "")]),
    ("pick_body_repaints", "the live recolour runs inside the transition window", [
        ("Plugin.cs", LIVE_CALL, "                        liveParticles += RecolourLiveParticles(ps, desired, looksWrong);\n")]),
    ("pick_body_repaints", "the live recolour drops the particles' alpha", [
        ("Plugin.cs", "new Color32(r, g, b, cur.a);", "new Color32(r, g, b, 255);")]),
    # C7 (R1 H1, M3): a spectator guard dropped, one per route
    ("spectators_write_nothing", "the colour publisher writes for a spectator", _drop("PlayerColorCosmetic.cs", GUARD16)),
    ("spectators_write_nothing", "the trail publisher writes for a spectator", _drop("TrailRenderer.cs", GUARD16)),
    ("spectators_write_nothing", "the effect publisher writes for a spectator", _drop("PlayerEffectCosmetic.cs", GUARD16)),
    ("spectators_write_nothing", "the nametag publisher writes for a spectator", _drop("NametagStyler.cs", GUARD16)),
    ("spectators_write_nothing", "the name repair writes for a spectator", [
        ("VanillaFixes.cs", REPAIR_GUARD, "            // leaves a spectator's name as it is, as PublishToPhoton does.\n")]),
]

CONTROLS = [
    ("publishers_record", [("PlayerColorCosmetic.cs", REC_COLOR, "                // control: a neutral line\n" + REC_COLOR)]),
    ("values_match_the_writes", [("TrailRenderer.cs", "TrailValue(s?.active_trail_sku,", "TrailValue( /* control */ s?.active_trail_sku,")]),
    ("refresh_asks_the_ledger", [("ApiClient.cs", "var ledger = CosmeticCarrierLedger.Shared;",
                                  "/* control */ var ledger = CosmeticCarrierLedger.Shared;")]),
    ("only_the_publishers_write", [("GameStateWatcher.cs", JOIN_COLOR, JOIN_COLOR +
        '                if (PhotonNetwork.LocalPlayer.CustomProperties["cr_trail_sku"] == null) { }\n')]),
    ("pick_body_repaints", [("PlayerColorCosmetic.cs", "            " + SUB + "\n", "            // control\n            " + SUB + "\n")]),
    ("pick_reads_the_room_for_every_picker", [("Plugin.cs", "            Color? before = _paintedCustom;\n",
                                               "            // control: the local player is not read here\n            Color? before = _paintedCustom;\n")]),
    ("spectators_write_nothing", [("PlayerColorCosmetic.cs", GUARD16, "                // control: a neutral line\n" + GUARD16)]),
]


def _mutated(edits):
    files = dict(FILES)
    for fname, old, new in edits:
        assert files[fname].count(old) == 1, (fname, old[:90])
        files[fname] = files[fname].replace(old, new)
    return files


@pytest.mark.parametrize("name", sorted(CLAIMS))
def test_the_claim_holds_on_the_tree(name):
    assert CLAIMS[name](FILES) == []


@pytest.mark.parametrize("claim,label,edits", MUTANTS, ids=[m[1] for m in MUTANTS])
def test_each_mutant_turns_its_claim_red(claim, label, edits):
    assert CLAIMS[claim](FILES) == []
    assert CLAIMS[claim](_mutated(edits)) != [], label


@pytest.mark.parametrize("claim,edits", CONTROLS, ids=[c[0] for c in CONTROLS])
def test_each_control_leaves_its_claim_green(claim, edits):
    mutated = _mutated(edits)
    assert mutated != FILES
    assert CLAIMS[claim](mutated) == []


def test_every_claim_has_mutants_and_a_control():
    assert {m[0] for m in MUTANTS} == set(CLAIMS) == {c[0] for c in CONTROLS}
    assert len({m[1] for m in MUTANTS}) == len(MUTANTS)
