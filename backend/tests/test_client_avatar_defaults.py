"""Item 19 (two default avatars by queue kind): design section 5.2's source
claims S1-S26, each pinned to the code term it names, and the i18n catalogue
obligation of section 2.10 (gate part 3).

Same family as test_client_r3_claims.py. Every claim is a function over the
plugin's C# sources that raises AssertionError when the claim is false. Each
claim runs three ways: against the tree (must pass), against an in-memory
MUTATION of the tree (must red), and against an in-memory negative CONTROL
edit (must stay green) - so a claim that cannot fail, or that fails on any
edit at all, is caught here rather than trusted (#391, #342). Every scope is a
brace-balanced span (#432), never the whole file, unless the claim is a
census across files.

Adaptations to this lane, recorded in ai-collab/v1410/ITEM19-BUILD-NOTES.md:
- S15: item 17's Keybinds registry is not on this lane, so item 19 has no swap
  reader; the claim is "no key read at all in either new file, and the
  behaviour's Update keeps exactly its one shipped GetKeyDown".
- S10: the one PublishLocal call sits in Apply, the design's "apply".
- S11/S19/S23: the decision half is split from the reading half
  (AvatarDefaultRules.cs is pure), so the read-side terms are checked in
  ReadFacing / ReadLoader and the comparison terms in the pure methods.
- S21 reads the local decompile (gitignored); set SCR_DECOMPILED_DIR to it.
"""
import hashlib
import io
import json
import os
import re
from pathlib import Path

import pytest

from _cs_structure import CsParseError, mask_code, method_spans, strip_comments_only

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
PLUGIN = Path(REPO) / "plugin"

AD = "AvatarDefaults.cs"
AR = "AvatarDefaultRules.cs"
PL = "Plugin.cs"
NU = "NativeUI.cs"
PR = "PortraitRender.cs"
CAT = "I18nCatalogues.cs"
NEW_FILES = (AD, AR)

_CACHE = {}


def _tree():
    if not _CACHE:
        for p in sorted(PLUGIN.glob("*.cs")):
            with io.open(str(p), encoding="utf-8") as fh:
                _CACHE[p.name] = fh.read()
    return dict(_CACHE)


# -- span helpers ---------------------------------------------------------

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


def _one(text, sig, base=0):
    """The single block after `sig` - method_spans' walk over a memoised
    mask (the plugin's big files are masked once per distinct text, not once
    per lookup; the claims run each file through ~80 lookups)."""
    masked = _masked(text)
    spans, search = [], 0
    while True:
        start = masked.find(sig, search)
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


def _span(text, sig, within=None):
    """(start, end) of the block after `sig`, optionally inside the block
    after `within` (a class), as offsets into `text`."""
    if within is None:
        return _one(text, sig)
    a, b = _one(text, within)
    return _one(text[a:b], sig, base=a)


def _body(text, sig, within=None):
    a, b = _span(text, sig, within)
    return _code(text[a:b])


def _code(text):
    return _memo(_STRIP, strip_comments_only, text)


def _count(src, files, term):
    return sum(_code(src[f]).count(term) for f in files)


# -- edit helpers (mutations and controls) ---------------------------------

def _replace(src, fname, old, new):
    s = dict(src)
    t = s[fname]
    assert t.count(old) == 1, "edit anchor %r occurs %d times in %s" % (old, t.count(old), fname)
    s[fname] = t.replace(old, new, 1)
    assert s[fname] != t
    return s


def _insert_after_open(src, fname, sig, text, within=None):
    """Insert `text` right after the opening brace of the block after `sig`."""
    s = dict(src)
    t = s[fname]
    a, _ = _span(t, sig, within)
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


# -- the rows the claims scope on -------------------------------------------

EVAL = "AvatarDefaults.Evaluate("
BEH = "public class CompetitiveRoundsBehaviour : MonoBehaviour"
CB = {
    "joined": "public void OnJoinedRoom()",
    "entered": "public void OnPlayerEnteredRoom(Photon.Realtime.Player p)",
    "props": "public void OnPlayerPropertiesUpdate(Photon.Realtime.Player target, ExitGames.Client.Photon.Hashtable changedProps)",
    "left": "public void OnLeftRoom()",
    "disconnected": "public void OnDisconnected(Photon.Realtime.DisconnectCause cause)",
    "playerleft": "public void OnPlayerLeftRoom(Photon.Realtime.Player p)",
    "roomprops": "public void OnRoomPropertiesUpdate(ExitGames.Client.Photon.Hashtable propertiesThatChanged)",
}
CALL = {
    "joined": 'AvatarDefaults.Evaluate("E2-joined");',
    "entered": 'AvatarDefaults.Evaluate("E3-entered");',
    "props": 'AvatarDefaults.Evaluate("E4-props");',
    "left": 'AvatarDefaults.Evaluate("E6-left");',
    "disconnected": 'AvatarDefaults.Evaluate("E7-disconnect");',
    "playerleft": 'AvatarDefaults.Evaluate("E11-left");',
    "roomprops": 'AvatarDefaults.Evaluate("E12-roomprops");',
}


def _drop(src, fname, stmt):
    return _replace(src, fname, stmt, "")


# S1 ------------------------------------------------------------------------

def _s1(src):
    t = src[AD]
    body = _body(t, "private static void Prefix()", "class AvatarCreatePlayerPatch")
    assert body.count(EVAL) == 1
    assert "return false" not in body and "bool Prefix" not in _code(t)
    m = re.search(r"\[HarmonyPatch\(typeof\(PlayerAssigner\), \"CreatePlayer\"\)\]\s*"
                  r"\[HarmonyPriority\(Priority\.VeryHigh\)\]\s*internal static class AvatarCreatePlayerPatch\b",
                  _code(t))
    assert m, "the CreatePlayer prefix lost its VeryHigh priority"


def test_s1_the_spawn_prefix_evaluates_first_and_never_skips_the_original():
    _check(_s1,
           lambda s: _drop(s, AD, 'AvatarDefaults.Evaluate("E5-spawn");'),
           lambda s: _insert_after_open(s, AD, "private static void Prefix()", "            // unrelated note",
                                        "class AvatarCreatePlayerPatch"))


def test_s1_a_return_false_path_reds():
    m = _replace(_tree(), AD, 'AvatarDefaults.Evaluate("E5-spawn");', 'AvatarDefaults.Evaluate("E5-spawn"); return false;')
    with pytest.raises(AssertionError):
        _s1(m)


# S2 ------------------------------------------------------------------------

CP_ATTR = '[HarmonyPatch(typeof(PlayerAssigner), "CreatePlayer")]'


def _s2(src):
    n = sum(_code(t).count(CP_ATTR) for t in src.values())
    assert n == 4, "CreatePlayer patch census is %d, expected 4 (#352)" % n


def test_s2_the_create_player_patch_census_is_four():
    _check(_s2,
           lambda s: _replace(s, AD, "internal static class AvatarCreatePlayerPatch",
                              "internal static class AvatarCreatePlayerPatch2 { }\n    " + CP_ATTR
                              + "\n    internal static class AvatarCreatePlayerPatch"),
           lambda s: _replace(s, AD, "internal static class AvatarCreatePlayerPatch",
                              "internal static class AvatarSpawnPatch"))


# S3 / S4 / S5 ---------------------------------------------------------------

def _s3(src):
    t = src[AD]
    assert '[HarmonyPatch(typeof(CharacterCreatorHandler), "LoadFaces")]' in _code(t)
    assert _body(t, "private static void Postfix()", "class AvatarLoadFacesPatch").count(EVAL) == 1


def _cut_class(src, fname, attr, cls):
    t = src[fname]
    i = t.index(attr)
    a, b = _span(t, "internal static class " + cls)
    s = dict(src)
    s[fname] = t[:i] + t[b:]
    return s


def test_s3_the_load_faces_postfix_evaluates():
    _check(_s3,
           lambda s: _cut_class(s, AD, '[HarmonyPatch(typeof(CharacterCreatorHandler), "LoadFaces")]', "AvatarLoadFacesPatch"),
           lambda s: _replace(s, AD, "/// whose process was killed mid-room restores its own face here.",
                              "/// whose process was killed restores its own face here."))


def _s4(src):
    body = _body(src[AD], "private static void Postfix()", "class AvatarLoadFacesPatch")
    logs = re.findall(r'Plugin\.Log\.LogInfo\("\[AVATAR\] ', body)
    assert len(logs) == 1, "the launch postfix must log one positive line (#83)"


def test_s4_the_load_faces_postfix_logs_a_positive_line():
    _check(_s4,
           lambda s: _replace(s, AD, 'Plugin.Log.LogInfo("[AVATAR] LoadFaces postfix attached; launch evaluation (home "',
                              'string unused = ("[AVATAR] LoadFaces postfix attached; launch evaluation (home "'),
           lambda s: _replace(s, AD, "LoadFaces postfix attached; launch evaluation", "LoadFaces postfix ran; launch evaluation"))


def _s5(src):
    t = src[AD]
    assert '[HarmonyPatch(typeof(CharacterCreatorHandler), "SelectFace")]' in _code(t)
    assert _body(t, "private static void Postfix(int faceID)", "class AvatarSelectFacePatch").count(EVAL) == 1


def test_s5_the_select_face_postfix_evaluates():
    _check(_s5,
           lambda s: _cut_class(s, AD, '[HarmonyPatch(typeof(CharacterCreatorHandler), "SelectFace")]', "AvatarSelectFacePatch"),
           lambda s: _replace(s, AD, "/// of selectedFaceID; only faceID 0 is this seat's own selection",
                              "/// of selectedFaceID; faceID 0 alone is this seat's own selection"))


# S6 / S7 / S24 --------------------------------------------------------------

def _evaluates(src, edge):
    body = _body(src[PL], CB[edge])
    assert body.count(EVAL) == 1, "%s calls the evaluator %d times" % (edge, body.count(EVAL))
    return body


def _s6(src):
    for edge in ("left", "disconnected"):
        body = _evaluates(src, edge)
        before = body[:body.index(EVAL)]
        assert "InRoom" not in before, "%s: the evaluator call sits behind an InRoom test" % edge


def _wrap_in_inroom(src, edge):
    return _replace(src, PL, CALL[edge], "if (PhotonNetwork.InRoom) " + CALL[edge])


def test_s6_the_leave_edges_are_not_behind_an_in_room_test():
    _check(_s6, lambda s: _wrap_in_inroom(s, "left"), lambda s: _wrap_in_inroom(s, "joined"))


def test_s6_the_disconnect_edge_is_not_behind_an_in_room_test():
    _check(_s6, lambda s: _wrap_in_inroom(s, "disconnected"), lambda s: _wrap_in_inroom(s, "joined"))


@pytest.mark.parametrize("edge,other", [("joined", "entered"), ("entered", "joined"), ("props", "joined"),
                                        ("playerleft", "roomprops"), ("roomprops", "playerleft")])
def test_s7_s24_each_room_edge_evaluates_and_reds_only_its_own_row(edge, other):
    _check(lambda s: _evaluates(s, edge),
           lambda s: _drop(s, PL, CALL[edge]),
           lambda s: _drop(s, PL, CALL[other]))


# S8 ------------------------------------------------------------------------

ROWS = {"auto": ('"SAvAuto"', "avatarAutoTxt =", "AvatarDefaults.SetAuto(", "internal static void SetAuto(bool on)", 'Evaluate("E8-auto");'),
        "mod": ('"SAvMod"', "avatarModTxt =", "AvatarDefaults.SetModded(", "internal static void SetModded(int slot)", 'Evaluate("E8-modded");'),
        "van": ('"SAvVan"', "avatarVanTxt =", "AvatarDefaults.SetVanilla(", "internal static void SetVanilla(int slot)", 'Evaluate("E8-vanilla");')}


def _s8(src, row):
    key, end, setter, sig, _ = ROWS[row]
    t = src[NU]
    assert t.count(key + ", I18n.Tr(") == 1
    i = t.index(key + ", I18n.Tr(")
    j = t.index(end, i)
    assert _code(t[i:j]).count(setter) == 1, "the %s row's callback does not call its writer" % row
    assert _body(src[AD], sig, "internal static class AvatarDefaults").count("Evaluate(") == 1


@pytest.mark.parametrize("row,other", [("auto", "mod"), ("mod", "van"), ("van", "auto")])
def test_s8_each_settings_row_is_edge_e8(row, other):
    _check(lambda s: _s8(s, row),
           lambda s: _drop(s, AD, ROWS[row][4]),
           lambda s: _drop(s, AD, ROWS[other][4]))


# S9 / S10 / S13 / S25 (the apply) -------------------------------------------

APPLY = "private static void Apply(int slot, string tag)"
ADC = "internal static class AvatarDefaults"


def _s9(src):
    body = _body(src[AD], APPLY, ADC)
    assert body.count("hit.ClickButton();") == 1 and body.count("cch.SelectFace(0, face, slot);") == 1
    for f in NEW_FILES:
        assert 'PlayerPrefs.SetInt("SelectedFace' not in _code(src[f])


def test_s9_the_apply_goes_through_click_button():
    _check(_s9,
           lambda s: _replace(s, AD, "hit.ClickButton();", "hit.myFace.ToString();"),
           lambda s: _replace(s, AD, "/// ClickButton passes that id to SelectFace)", "/// the portrait passes that id to SelectFace)"))


def test_s9_no_selected_face_prefs_write():
    m = _insert_after_open(_tree(), AD, APPLY, '            PlayerPrefs.SetInt("SelectedFace0", slot);', ADC)
    with pytest.raises(AssertionError):
        _s9(m)


def _s10(src):
    assert _body(src[AD], APPLY, ADC).count("FacePublisher.PublishLocal();") == 1


def test_s10_the_apply_publishes_the_carrier_once():
    _check(_s10,
           lambda s: _drop(s, AD, "FacePublisher.PublishLocal();"),
           lambda s: _drop(s, AD, "CharacterCreatorPortrait hit = null;"))


def _s13(src, part):
    body = _body(src[AD], APPLY, ADC)
    term = {"send": "FaceResync.TrySendLocalFace(", "equip": "EquipFace("}[part]
    assert body.count(term) == 1, "%s occurs %d times in the apply" % (term, body.count(term))


@pytest.mark.parametrize("part,other", [("send", "equip"), ("equip", "send")])
def test_s13_the_apply_informs_the_others_and_equips_the_local_body(part, other):
    stmt = {"send": 'FaceResync.TrySendLocalFace("AVATAR");', "equip": "if (eq != null) eq.EquipFace(face);"}
    _check(lambda s: _s13(s, part), lambda s: _drop(s, AD, stmt[part]), lambda s: _drop(s, AD, stmt[other]))


def _s25(src, part):
    t = src[AD]
    if part == "resolver":
        assert _code(t).count("playerId == -1") == 1
        assert _body(t, "internal static List<CharacterCreatorPortrait> MenuPortraits()", ADC).count("playerId == -1") == 1
        assert _code(t).count("ClickButton(") == 1
        assert _body(t, APPLY, ADC).count("ClickButton(") == 1
    else:
        body = _body(t, "private static void Postfix(int faceID)", "class AvatarSelectFacePatch")
        assert re.search(r"if \(faceID != 0\) return;", body), "the own-selection filter is gone"


@pytest.mark.parametrize("part,other", [("resolver", "filter"), ("filter", "resolver")])
def test_s25_the_apply_cannot_address_another_local_players_grid(part, other):
    cut = {"resolver": lambda s: _drop(s, AD, ".Where(x => x.playerId == -1)"),
           "filter": lambda s: _drop(s, AD, "if (faceID != 0) return;")}
    _check(lambda s: _s25(s, part), cut[part], cut[other])


# S11 / S12 / S14 (the carrier and the send) --------------------------------

def _s11(src):
    for f in NEW_FILES:
        c = _code(src[f])
        assert "SetCustomProperties" not in c, f
        assert '"cr_face"' not in c, f
    assert _count(src, NEW_FILES, "PROP_FACE") == 1
    read = _body(src[AD], "private static AvatarFacingIn ReadFacing()", ADC)
    assert "FaceKey = FacePublisher.PROP_FACE" in read, "PROP_FACE is not the read-side key name"
    cms = _body(src[AR], "internal virtual bool CarriesModSignature(IList<string> keys, string faceKey)")
    assert "k == faceKey" in cms, "the per-actor test no longer skips the carrier key"


def test_s11_item_19_writes_no_carrier_key():
    _check(_s11,
           lambda s: _insert_after_open(s, AD, APPLY,
                                        "            PhotonNetwork.LocalPlayer.SetCustomProperties(new ExitGames.Client.Photon.Hashtable { { FacePublisher.PROP_FACE, null } });", ADC),
           lambda s: _insert_after_open(s, AD, "internal static void Tick()", "            FacePublisher.PublishLocal();", ADC))


def _s12(src):
    n = sum(len(re.findall(r"\bFacePublisher\.PublishLocal\s*\(", _code(t))) for t in src.values())
    assert n == 4, "FacePublisher.PublishLocal has %d call sites, expected 4" % n


def test_s12_publish_local_has_four_call_sites():
    _check(_s12,
           lambda s: _insert_after_open(s, AD, "internal static void Tick()", "            FacePublisher.PublishLocal();", ADC),
           lambda s: _insert_after_open(s, AD, "internal static void Tick()", "            TrailCosmetic.PublishLocalProps();", ADC))


def _s14(src):
    body = _body(src[PL], "internal static bool TrySendLocalFace(string tag)", "internal static class FaceResync")
    assert body.count("RpcTarget.Others") == 1 and "RpcTarget.All" not in body


def test_s14_the_face_resend_targets_the_others():
    _check(_s14,
           lambda s: _replace(s, PL, 'lp.data.view.RPC("RPCA_SetFace", RpcTarget.Others,', 'lp.data.view.RPC("RPCA_SetFace", RpcTarget.All,'),
           lambda s: _insert_after_open(s, PL, CB["joined"], "            var unrelatedTarget = RpcTarget.All;"))


# S15 (adapted: no swap reader on this lane) ---------------------------------

def _s15(src):
    for f in NEW_FILES:
        c = _code(src[f])
        assert "KeyCode." not in c and "Input.GetKeyDown(" not in c and "Keybinds" not in c, f
    upd = _body(src[PL], "private void Update()", BEH)
    assert upd.count("Input.GetKeyDown(") == 1, "the behaviour's Update reads %d keys" % upd.count("Input.GetKeyDown(")


def test_s15_item_19_binds_no_key():
    _check(_s15,
           lambda s: _replace(s, PL, "try { AvatarDefaults.Tick(); } catch { }",
                              "try { AvatarDefaults.Tick(); } catch { }\n            if (Input.GetKeyDown(KeyCode.F6)) { }"),
           lambda s: _replace(s, AD, "// The four ring sprites", "// (no KeyCode.F6 here) The four ring sprites"))


# S16 / S23 (the facing) ------------------------------------------------------

FACING = "internal virtual AvatarFacing FacingOf(AvatarFacingIn f)"
READF = "private static AvatarFacingIn ReadFacing()"


def _s16(src):
    assert _body(src[AR], FACING).count("EveryOtherFighterIsModded(") == 1
    for f in NEW_FILES:
        assert "OpponentHasMod" not in _code(src[f]), f


def test_s16_the_every_quantifier_and_not_the_any():
    _check(_s16,
           lambda s: _replace(s, AR, "return EveryOtherFighterIsModded(others, f.FaceKey)", "return OpponentHasMod(others, f.FaceKey)"),
           lambda s: _replace(s, AR, "var others = f.OtherFighterKeys;", "var otherKeys = f.OtherFighterKeys; var others = otherKeys;"))


ALLOWED_FACING_TERMS = {"PhotonNetwork.InRoom", "PhotonNetwork.OfflineMode", "RoomActors.LocalIsSpectator",
                        "PhotonNetwork.CurrentRoom", "CompetitiveRoomDetect.IsModIssuedRoom",
                        "RoomActors.ActiveFighters", "FacePublisher.PROP_FACE"}


def _s23(src):
    for f in NEW_FILES:
        c = _code(src[f])
        assert "InVanillaQuickmatch" not in c and "m_searchingType" not in c, f
    read = _body(src[AD], READF, ADC)
    named = set(re.findall(r"\b[A-Z]\w*\.[A-Z]\w*", read))
    assert named <= ALLOWED_FACING_TERMS, "the facing reads a per-seat term: %s" % sorted(named - ALLOWED_FACING_TERMS)
    assert "CompetitiveRoomDetect.IsModIssuedRoom" in named and "RoomActors.ActiveFighters" in named


def test_s23_no_per_seat_term_decides_a_facing():
    _check(_s23,
           lambda s: _replace(s, AD, "f.LocalIsSpectator = RoomActors.LocalIsSpectator;",
                              "f.LocalIsSpectator = RoomActors.LocalIsSpectator || Plugin.InVanillaQuickmatch();"),
           lambda s: _replace(s, AD, "// The four ring sprites", "// (InVanillaQuickmatch is never read) The four ring sprites"))


# S17 (the ring tick runs with the overlay closed) ---------------------------

TICK = "try { AvatarDefaults.Tick(); } catch { }"


def _s17(src):
    n = sum(_code(t).count("AvatarDefaults.Tick()") for t in src.values())
    assert n == 1
    assert _body(src[PL], "private void Update()", BEH).count("AvatarDefaults.Tick()") == 1


def test_s17_the_ring_repaint_runs_with_the_overlay_closed():
    def mutate(s):
        # after the guard, not after the opening brace: there it would still
        # run with the page closed and could not red (design S17)
        s = _drop(s, PL, TICK)
        t = s[NU]
        a, b = _span(t, "public static void Tick()")
        seg = t[a:b]
        guard = "if(!isOpen||!pageBuilt)return;"
        assert seg.count(guard) == 1
        s = dict(s)
        s[NU] = t[:a] + seg.replace(guard, guard + " " + TICK) + t[b:]
        return s

    def control(s):
        s = _drop(s, PL, TICK)
        return _insert_after_open(s, PL, "private void Update()", "            " + TICK, BEH)
    _check(_s17, mutate, control)


# S18 (one Follow helper) ------------------------------------------------------

FOLLOW = "else f = AvatarDefaults.FaceForFollow();"
BARE = "else if (cch.selectedPlayerFaces != null && cch.selectedPlayerFaces.Length > 0) f = cch.selectedPlayerFaces[0];"


def _s18(src):
    for sig in ("private static string LiveInputsKey()", "private static Inputs Capture(int preset)"):
        body = _body(src[PR], sig)
        assert body.count("AvatarDefaults.FaceForFollow()") == 1, sig
        assert "selectedPlayerFaces[0]" not in body, sig


def test_s18_portrait_render_resolves_follow_through_one_helper():
    def mutate(s):
        t = s[PR]
        a, b = _span(t, "private static Inputs Capture(int preset)")
        seg = t[a:b]
        assert seg.count(FOLLOW) == 1
        s = dict(s)
        s[PR] = t[:a] + seg.replace(FOLLOW, BARE) + t[b:]
        return s
    _check(_s18, mutate,
           lambda s: _insert_after_open(s, PR, "private static PlayerFace PickFace(int preset, StringBuilder rep)",
                                        "            var unrelated = CharacterCreatorHandler.instance.selectedPlayerFaces[0];"))


# S19 (vanilla-clean is base-loader resolvability) ---------------------------

CLEAN = "internal virtual bool VanillaClean(AvatarFaceIds fc, AvatarLoaderView l)"
LOADER = "private static AvatarLoaderView ReadLoader()"


def _s19(src):
    for f in NEW_FILES:
        assert "CUSTOM_ID_BASE" not in _code(src[f]), f
    r = _body(src[AD], LOADER, ADC)
    for term in ("CharacterCreatorItemLoader.instance", "L.eyes", "L.mouths", "L.accessories"):
        assert term in r, term
    c = _body(src[AR], CLEAN)
    for term in ("l.Eyes", "l.Mouths", "l.Accessories", "ResolvesOnABaseSeat("):
        assert term in c, term


def test_s19_vanilla_clean_is_resolvability_not_a_threshold():
    _check(_s19,
           lambda s: _replace(s, AR, "if (l == null) return false;",
                              "if (l == null || fc.Eye >= CharacterCreatorItemLoader.CUSTOM_ID_BASE) return false;"),
           lambda s: _replace(s, AD, "var L = CharacterCreatorItemLoader.instance;",
                              "var L = CharacterCreatorItemLoader.instance; var unusedLoaderName = L;"))


# S20 (no latch, no stored shown-face) ---------------------------------------

def _class_fields(text):
    """{type name: [field statements]} for every class/struct in `text`,
    read at the type's own brace depth (nested bodies skipped)."""
    masked = mask_code(text)
    out = {}
    for m in re.finditer(r"\b(class|struct)\s+(\w+)", masked):
        name = m.group(2)
        ob = masked.find("{", m.end())
        if ob == -1:
            continue
        depth, buf, stmts, i = 0, [], [], ob
        while i < len(masked):
            ch = masked[i]
            if ch == "{":
                depth += 1
                if depth == 2:
                    header = "".join(buf).strip()
                    # an auto-property is state too; a method, a nested type or
                    # an initializer body is not a field
                    if "(" not in header and not re.search(r"\b(class|struct|enum)\b", header) and "=" not in header:
                        stmts.append(header + " {property}")
                    buf = []
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
                if depth == 1:
                    buf = []
            elif depth == 1:
                buf.append(ch)
                if ch == ";":
                    st = " ".join("".join(buf).split())
                    buf = []
                    # an expression-bodied member or a method declaration is not
                    # a field; no `continue` here, which would skip the `i += 1`
                    # below and re-read this ';' as a statement of its own
                    p, e = st.find("("), st.find("=")
                    is_member = "=>" in st or (p != -1 and (e == -1 or p < e))
                    if not is_member:
                        stmts.append(st)
            i += 1
        out.setdefault(name, []).extend(stmts)
    return out


CARRIERS = {"AvatarFaceIds", "AvatarLoaderView", "AvatarSetting", "AvatarLivenessIn",
            "AvatarFacingIn", "AvatarEvalIn", "AvatarDecision"}


def _s20(src):
    fd = _class_fields(src[AD])
    state = [st for st in fd["AvatarDefaults"] if " const " not in " " + st]
    assert state == ["private static Sprite ringGold, ringBlue, ringBoth, ringRed;",
                     "private static bool ringsBuilt;"], state
    for patch in ("AvatarLoadFacesPatch", "AvatarSelectFacePatch", "AvatarCreatePlayerPatch"):
        assert fd[patch] == [], (patch, fd[patch])
    fr = _class_fields(src[AR])
    assert fr["AvatarRules"] == [], fr["AvatarRules"]
    assert set(fr) == CARRIERS | {"AvatarRules"}, sorted(fr)
    for name in CARRIERS:
        for st in fr[name]:
            assert "static" not in st.split(), (name, st)
    # the only persisted item-19 state: four config entries, one of them Home
    for f in NEW_FILES:
        c = _code(src[f])
        assert "PlayerPrefs." not in c and "Config.Bind(" not in c, f
    binds = re.findall(r"\b(Avatar\w+) = Config\.Bind\(", _code(src[PL]))
    assert sorted(binds) == ["AvatarAutoSwitch", "AvatarHomeSlot", "AvatarModdedPreset", "AvatarVanillaPreset"], binds


def test_s20_there_is_no_latch_and_no_stored_shown_face():
    _check(_s20,
           lambda s: _replace(s, AD, "private static bool ringsBuilt;", "private static bool ringsBuilt;\n        private static bool _switchedThisRoom;"),
           lambda s: _insert_after_open(s, AD, "internal static void Tick()", "            bool _switchedThisRoom = false;", ADC))


def test_s20_a_static_in_the_rules_reds():
    m = _insert_after_open(_tree(), AR, "internal class AvatarRules", "        private static int lastApplied;")
    with pytest.raises(AssertionError):
        _s20(m)


# S21 (the decompiled spans the design rests on) -----------------------------

DECOMPILED = [
    ("CharacterCreatorItemLoader.cs", 22, 36, "421b9423b583c87cb5fe42f91647ace6dde7ebe9f8da65bd5aaa2c4ab43acd1f"),
    ("CharacterCreatorItemEquipper.cs", 64, 94, "77b32efbc742d6f9285d248190b4e2905cedb992b2da86362bacd59d1cdeb301"),
    ("CardChoiceVisuals.cs", 123, 127, "63b6b158bcea239608f1b0edbcd2f48f644e0973f3857485d3e1e6da88add0df"),
    # Item 19 fix pass 1 (M11): the PlayerFace persistence proof the design's
    # round-1 M11 closure rests on (twelve keys per slot): LoadFace and SaveFace.
    ("PlayerFace.cs", 23, 37, "9b494c26368d35d5beae100248148a6c2fcb34946d8ed851f0310b5e5a80a1b4"),
    ("PlayerFace.cs", 39, 54, "4bb696a16552c987474f14ea76d31ddb7ad6a2ac928225f033021b6d65987d69"),
]


def _decompiled_dir():
    d = os.environ.get("SCR_DECOMPILED_DIR") or os.path.join(REPO, "logs-snapshot", "decompiled", "full")
    return d if os.path.isdir(d) else None


def _span_hash(lines, a, b):
    return hashlib.sha256(b"\n".join(lines[a - 1:b])).hexdigest()


@pytest.mark.parametrize("fname,a,b,want", DECOMPILED, ids=["%s:%d-%d" % (f, a, b) for f, a, b, _ in DECOMPILED])
def test_s21_the_decompiled_spans_are_what_the_design_records(fname, a, b, want):
    d = _decompiled_dir()
    if d is None:
        pytest.skip("the decompile is local-only; set SCR_DECOMPILED_DIR")
    with open(os.path.join(d, fname), "rb") as fh:
        lines = fh.read().split(b"\n")
    assert _span_hash(lines, a, b) == want
    # mutation: one line inside the span changes the hash
    inside = list(lines)
    inside[a] = inside[a] + b" "
    assert _span_hash(inside, a, b) != want
    # control: the neighbouring line just outside it does not
    outside = list(lines)
    outside[b] = outside[b] + b" "
    assert _span_hash(outside, a, b) == want


# S22 (the durable capture) ---------------------------------------------------

def _s22(src):
    """Fix pass 1 (M8): one info line in the evaluator, built by the pure
    formatter the harness replays (case M8), logged for every applied change
    AND for every classification on a room edge, before the no-apply return."""
    body = _body(src[AD], "internal static void Evaluate(string tag)", ADC)
    # fix pass 2: the evaluator carries two info lines, the classification
    # line and the deferred-restoration line (H9/M3); exactly one of each
    logs = [m.start() for m in re.finditer(r"Plugin\.Log\.LogInfo\(rules\.ClassificationLine\(", body)]
    assert len(logs) == 1, "the evaluator has %d classification lines" % len(logs)
    assert len(re.findall(r"Plugin\.Log\.LogInfo\(", body)) == 2, "an info line other than the two named ones"
    stmt = body[logs[0]:body.index(";", logs[0])]
    assert "rules.ClassificationLine(tag, d, OtherFighterCount(f)" in stmt, stmt
    # fix pass 2 (M8): BOTH arms of the guard, read from the production
    # statement itself, immediately before the line
    guard = body.rfind("if (", 0, logs[0])
    assert body[guard:logs[0]].strip() == "if (d.Apply >= 0 || rules.LogsClassification(tag))", \
        "the classification line's guard is %r" % body[guard:logs[0]].strip()
    assert body.index("if (d.Apply < 0) return;") > logs[0], "the line is logged only after an apply"
    fmt = _body(src[AR], "internal virtual string ClassificationLine(")
    for term in ('" (facing "', '", nominee "', '", other fighters "', "d.Facing", "d.Nominee", "otherFighters"):
        assert term in fmt, term
    edges = _body(src[AR], "internal virtual bool LogsClassification(string tag)")
    for e in ('"E2-"', '"E3-"', '"E6-"', '"E7-"', '"E11-"'):
        assert e in edges, e
    for e in ('"E5-"', '"E4-"', '"E9-"'):
        assert e not in edges, e


def test_s22_the_evaluator_logs_each_applied_change():
    _check(_s22,
           lambda s: _replace(s, AD, "if (d.Apply >= 0 || rules.LogsClassification(tag))", "if (d.Apply >= 0)"),
           lambda s: _replace(s, AR, '" kept slot "', '" held slot "'))


def test_s22_the_applied_arm_of_the_guard_reds():
    # fix pass 2 (M8): the round 2 controls stayed green with this arm removed
    _check(_s22,
           lambda s: _replace(s, AD, "if (d.Apply >= 0 || rules.LogsClassification(tag))", "if (rules.LogsClassification(tag))"),
           lambda s: _replace(s, AR, '" applied slot "', '" applied preset slot "'))


def test_s22_the_line_names_the_other_fighter_count():
    _check(_s22,
           lambda s: _replace(s, AR, '+ ", other fighters " + otherFighters', '+ ""'),
           lambda s: _replace(s, AR, '+ ", issued room " +', '+ ", issued " +'))


# S27 (fix pass 1, H3): one publish-or-clear helper behind all four callers --

FP = "internal static class FacePublisher"
PUB = "public static FaceCarrierAction PublishLocal(out string published)"   # fix pass 2: the body behind both overloads


def _s27(src):
    body = _body(src[PL], PUB, FP)
    assert not re.search(r"\breturn\s*;", mask_code(body)), "PublishLocal still has a bare return"
    assert body.count("new AvatarRules().CarrierAction(") == 1
    a, b = _one(body, "if (action == FaceCarrierAction.Clear)")
    clear = body[a:b]
    for term in ("[PROP_FACE] = null;", "SetCustomProperties(clear)", "return action;"):
        assert term in clear, term
    assert body.count("SetCustomProperties(") == 2, "a third carrier write"
    car = _body(src[AR], "internal virtual FaceCarrierAction CarrierAction(")
    assert re.search(r"if \(!facesListed \|\| !face0\.Present \|\| face0\.AllZero\) return FaceCarrierAction\.Clear;", car), car


def test_s27_a_definitive_decline_clears_the_carrier():
    _check(_s27,
           lambda s: _drop(s, PL, "PhotonNetwork.LocalPlayer.SetCustomProperties(clear);"),
           lambda s: _replace(s, PL, "cleared the face carrier (", "removed the face carrier ("))


def test_s27_the_round_1_decline_shape_reds():
    _check(_s27,
           lambda s: _replace(s, AR, "face0.AllZero) return FaceCarrierAction.Clear;", "face0.AllZero) return FaceCarrierAction.Keep;"),
           lambda s: _replace(s, AR, "if (spectator || !handlerReady || !localPlayerReady) return FaceCarrierAction.Keep;",
                              "if (!handlerReady || !localPlayerReady || spectator) return FaceCarrierAction.Keep;"))


# S28 (fix pass 1, BR-M1): every Harmony body is one exception boundary ------

HOOKS = {"E1": ("AvatarLoadFacesPatch", "private static void Postfix()"),
         "E9": ("AvatarSelectFacePatch", "private static void Postfix(int faceID)"),
         "E5": ("AvatarCreatePlayerPatch", "private static void Prefix()")}


def _match_brace(masked, ob):
    depth = 0
    for i in range(ob, len(masked)):
        if masked[i] == "{":
            depth += 1
        elif masked[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    raise CsParseError("unbalanced braces")


def _s28(src, hook):
    cls, sig = HOOKS[hook]
    body = _body(src[AD], sig, "class " + cls)
    inner = body.strip()[1:-1]
    m = mask_code(inner)
    i = len(m) - len(m.lstrip())
    assert m[i:i + 3] == "try", "%s: the body is not one exception boundary" % hook
    e = _match_brace(m, m.index("{", i))
    c = re.match(r"\s*catch\s*\(\s*Exception\s+\w+\s*\)\s*\{", m[e:])
    assert c, "%s: no catch (Exception) right after the try" % hook
    cs = e + c.end() - 1
    ce = _match_brace(m, cs)
    assert m[ce:].strip() == "", "%s: a statement outside the boundary" % hook
    catch_code = inner[cs:ce]
    assert "AvatarDefaults.Warn(" in catch_code and "Plugin.Log." not in catch_code, catch_code
    warn = _body(src[AD], "internal static void Warn(string msg)", ADC)
    assert "Plugin.Log?.LogWarning(msg)" in warn and re.search(r"catch\s*\{\s*\}", warn), warn


@pytest.mark.parametrize("hook,other", [("E1", "E9"), ("E9", "E5"), ("E5", "E1")])
def test_s28_each_hook_body_is_one_exception_boundary(hook, other):
    cls, sig = HOOKS[hook]
    _check(lambda s: _s28(s, hook),
           lambda s: _insert_after_open(s, AD, sig, "            AvatarDefaults.Tick();", "class " + cls),
           lambda s: _replace(s, AD, "[AVATAR] %s" % {"E1": "E1-launch hook failed: ", "E9": "E9-select hook failed: ",
                                                       "E5": "E5-spawn hook failed: "}[other],
                              "[AVATAR] %s" % {"E1": "E1-launch hook threw: ", "E9": "E9-select hook threw: ",
                                               "E5": "E5-spawn hook threw: "}[other]))


def test_s28_a_catch_that_logs_through_the_bare_logger_reds():
    m = _replace(_tree(), AD, 'AvatarDefaults.Warn("[AVATAR] E5-spawn hook failed: " + ex.Message);',
                 "Plugin.Log.LogWarning(ex.Message);")
    with pytest.raises(AssertionError):
        _s28(m, "E5")


# S29 (fix pass 1, BR-H1 and BR-M4): capability first, provenance never decides

def _s29(src):
    body = _body(src[AR], FACING)
    assert "ModIssuedRoom" not in mask_code(body), "the room's provenance decides a facing"
    room = body.index("if (!f.InRoom || f.OfflineMode) return AvatarFacing.Undecided;")
    unread = body.index("if (f.Unreadable) return AvatarFacing.Vanilla;")
    assert room < unread, "unreadability is consulted before an online room is established"
    assert "others.Count == 0) return AvatarFacing.Undecided;" in body
    census = _body(src[AR], "internal virtual AvatarFacing Census(AvatarLivenessIn l, AvatarFacingIn f)")
    assert census.index("if (!f.InRoom && !f.Unreadable) return FacingOf(f);") < census.index("if (Live(l))"), \
        "a confirmed exit no longer outranks liveness (H9)"


def test_s29_provenance_never_decides_the_facing():
    _check(_s29,
           lambda s: _replace(s, AR, "            var others = f.OtherFighterKeys;",
                              "            if (f.ModIssuedRoom) return AvatarFacing.Modded;\n            var others = f.OtherFighterKeys;"),
           lambda s: _replace(s, AR, "/// <summary>Term (2), capability first", "/// <summary>Term (2), the capability first"))


def test_s29_unreadability_after_the_room_and_the_exit_before_liveness():
    _check(_s29,
           lambda s: _replace(s, AR, "            if (!f.InRoom || f.OfflineMode) return AvatarFacing.Undecided;\n            if (f.Unreadable) return AvatarFacing.Vanilla;",
                              "            if (f.Unreadable) return AvatarFacing.Vanilla;\n            if (!f.InRoom || f.OfflineMode) return AvatarFacing.Undecided;"),
           lambda s: _replace(s, AR, "            if (f.LocalIsSpectator) return AvatarFacing.Undecided;\n            if (!f.RoomExists) return AvatarFacing.Undecided;",
                              "            if (!f.RoomExists) return AvatarFacing.Undecided;\n            if (f.LocalIsSpectator) return AvatarFacing.Undecided;"))


def test_s29_the_liveness_first_census_reds():
    m = _replace(_tree(), AR, "            if (!f.InRoom && !f.Unreadable) return FacingOf(f);\n            if (Live(l)) return AvatarFacing.Locked;",
                 "            if (Live(l)) return AvatarFacing.Locked;\n            if (!f.InRoom && !f.Unreadable) return FacingOf(f);")
    with pytest.raises(AssertionError):
        _s29(m)


# S30 (fix pass 1, M11 and L1): the exact assignment the nametag citation names

NT = "NametagStyler.cs"


def _s30(src):
    lines = src[NT].split("\n")
    assert lines[421].strip() == "string styled = Wrap(_baseName, skus);", "line 422: %r" % lines[421]
    assert lines[422].strip() == "", "line 423: %r" % lines[422]
    assert lines[425].strip() == "PhotonNetwork.LocalPlayer.NickName = styled;", "line 426: %r" % lines[425]


def test_s30_the_broadcast_assignment_is_at_the_cited_line():
    _check(_s30,
           lambda s: _replace(s, NT, "                string styled = Wrap(_baseName, skus);",
                              "\n                string styled = Wrap(_baseName, skus);"),
           lambda s: _replace(s, NT, "// keep fresh if Steam persona changed", "// keep it fresh if the Steam persona changed"))


# S31 (fix pass 1, M11): the refusal citation, by meaning not by line count --

TWO_V_TWO = "class PlayerAssigner_CreatePlayer_2v2_Patch"
REFUSAL = "if (__instance.hasCreatedLocalPlayer) return false;"
TEAM_EXIT = "if (slot < 0) return true;"


def _s31(src):
    t = src[PL]
    a, b = _span(t, TWO_V_TWO)
    seg = _code(t[a:b])
    assert seg.count(REFUSAL) == 1, "the already-spawned refusal occurs %d times" % seg.count(REFUSAL)
    assert seg.count(TEAM_EXIT) == 1
    between = seg[seg.index(TEAM_EXIT) + len(TEAM_EXIT):seg.index(REFUSAL)]
    assert between.strip() == "", "the refusal is no longer the statement after the team-mode exit"


def test_s31_the_already_spawned_refusal_is_where_the_design_cites_it():
    _check(_s31,
           lambda s: _replace(s, PL, REFUSAL + "     // already done", "// already done"),
           lambda s: _replace(s, PL, REFUSAL + "     // already done", REFUSAL + "     // done already"))


# S32 (fix pass 1, L1): the dual ring, the hybrid ring, the recovery text -----

RING = "private static Sprite RingSprite(string name, Color outer, Color inner)"
ENSURE = "private static void EnsureRings()"
UNUSABLE = "private static string UnusableMessage(AvatarUnusable u)"


def _s32(src, part):
    t = src[AD]
    if part == "ring":
        assert "px[y * size + x] = edge < 3 ? outer : edge < 6 ? inner : clear;" in _body(t, RING, ADC)
    elif part == "hybrid":
        body = _body(t, ENSURE, ADC)
        for stmt in ('ringGold = RingSprite("CR_AvRingGold", gold, gold);', 'ringBlue = RingSprite("CR_AvRingBlue", blue, blue);',
                     'ringBoth = RingSprite("CR_AvRingBoth", gold, blue);', 'ringRed = RingSprite("CR_AvRingRed", red, red);'):
            assert stmt in body, stmt
        assert "(isM && isV) ? ringBoth" in _body(t, "private static void PaintRings()", ADC)
    else:
        assert 'return first + "\\n" + RecoveryInstruction();' in _body(t, UNUSABLE, ADC)


@pytest.mark.parametrize("part,old,new,sig", [
    ("ring", "edge < 6 ? inner : clear", "edge < 6 ? outer : clear", RING),
    ("hybrid", 'RingSprite("CR_AvRingBoth", gold, blue)', 'RingSprite("CR_AvRingBoth", gold, gold)', ENSURE),
    ("recovery", 'return first + "\\n" + RecoveryInstruction();', "return first;", UNUSABLE),
])
def test_s32_each_low_closure_has_its_own_pair(part, old, new, sig):
    _check(lambda s: _s32(s, part),
           lambda s: _replace(s, AD, old, new),
           lambda s: _insert_after_open(s, AD, sig, "            // an unrelated note", ADC))


# S26 (one announcer) ---------------------------------------------------------

ANN = "private static void Announce(string msg)"


def _s26(src):
    assert _count(src, NEW_FILES, "CompetitiveUI.ShowNotification(") == 1
    assert _count(src, NEW_FILES, "CompetitiveUI.IsShowing(") == 1
    body = _body(src[AD], ANN, ADC)
    assert body.count("CompetitiveUI.ShowNotification(") == 1 and body.count("CompetitiveUI.IsShowing(") == 1


def test_s26_one_announcer():
    _check(_s26,
           lambda s: _replace(s, AD, "if (d.Apply < 0) return;", "if (d.Apply < 0) return;\n                CompetitiveUI.ShowNotification(\"x\", Color.white, 5f);"),
           lambda s: _replace(s, AD, "if (d.Apply < 0) return;", "if (d.Apply < 0) return;\n                Announce(RecoveryInstruction());"))


# The gate: the swap rule exists in the pure half and has no plugin caller ---

def test_the_swap_rule_has_no_caller_until_item_17_lands():
    src = _tree()
    for t in (src[AD], src[PL], src[NU]):
        c = _code(t)
        assert "SwapPermitted(" not in c and "SwapTarget(" not in c


# S33 (fix pass 2, H3): no pass rereads the cache it has just published to ----
#
# PUN updates the local player's cached properties only on the server's echo
# (learning #428), so a method that publishes the carrier and then reads
# cr_face from the cache in the same pass reads the PREVIOUS face. The sweep
# covers every method that calls FacePublisher.PublishLocal (the four sites
# S12 counts) and counts each cache read after the publish; a read handed to
# AvatarRules.PopupFace as its remote-picker reader is the one exemption, and
# the rule itself must answer a local picker without calling that reader.

POPUP = "static void Postfix(CardChoiceVisuals __instance, int pickerID)"
_METHOD_HEAD = re.compile(r"^(?:\[[^\]]*\]\s*)*(?:(?:public|private|internal|protected|static|override|virtual|async|unsafe)\s+)+"
                          r"[\w<>\[\],.?]+(?:\s*<[^>]*>)?\s+\w+\s*\(.*\)$", re.S)
_CACHE_READS = ("ReadCarrier(", "TryReadAndApply(", "CustomProperties[PROP_FACE]", 'CustomProperties["cr_face"]',
                "CustomProperties[FacePublisher.PROP_FACE]")


def _enclosing_method(masked, i):
    """(open, close) of the innermost METHOD block around offset i: walk out
    brace by brace, and take the first block whose head (the text back to the
    previous ; { or }) is a member declaration with modifiers and a parameter
    list - so if/foreach/try blocks and lambdas are walked past."""
    depth, j = 0, i
    while j > 0:
        j -= 1
        ch = masked[j]
        if ch == "}":
            depth += 1
        elif ch == "{":
            if depth:
                depth -= 1
                continue
            k = max(masked.rfind(";", 0, j), masked.rfind("{", 0, j), masked.rfind("}", 0, j))
            if _METHOD_HEAD.match(masked[k + 1:j].strip()):
                d2 = 0
                for e in range(j, len(masked)):
                    if masked[e] == "{":
                        d2 += 1
                    elif masked[e] == "}":
                        d2 -= 1
                        if d2 == 0:
                            return j, e + 1
                return None
    return None


def _call_spans(code, name):
    """(open, close) of every `name(` argument list in code."""
    out = []
    for m in re.finditer(re.escape(name) + r"\(", code):
        depth, j = 0, m.end() - 1
        for k in range(j, len(code)):
            if code[k] == "(":
                depth += 1
            elif code[k] == ")":
                depth -= 1
                if depth == 0:
                    out.append((j, k + 1))
                    break
    return out


def _s33(src):
    sites, rereads = 0, []
    for fname, text in sorted(src.items()):
        masked = _masked(text)
        for m in re.finditer(r"\bFacePublisher\.PublishLocal\s*\(", masked):
            sites += 1
            span = _enclosing_method(masked, m.start())
            assert span is not None, "%s: no enclosing method for the publish at %d" % (fname, m.start())
            a, b = span
            code = _code(text[a:b])
            at = code.find("FacePublisher.PublishLocal", 0)
            exempt = _call_spans(code, ".PopupFace")
            for term in _CACHE_READS:
                for r in re.finditer(re.escape(term), code):
                    if r.start() < at:
                        continue
                    if any(x < r.start() < y for x, y in exempt):
                        continue
                    line = text[:a + r.start()].count("\n") + 1
                    rereads.append("%s:%d %s after the publish (the cache still holds the previous face)" % (fname, line, term))
    assert sites == 4, "%d PublishLocal sites swept, expected 4" % sites
    assert not rereads, "reread-after-publish: %d site(s): %s" % (len(rereads), "; ".join(rereads))
    body = _body(src[PL], POPUP, "class CardChoiceVisuals_Show_Competitive_Patch")
    m = re.search(r"FacePublisher\.PublishLocal\(out (\w+)\)", body)
    assert m, "the popup does not take the value it publishes"
    assert re.search(r"\.PopupFace\(picker\.IsLocal, \w+, %s,\s*\(\) => FacePublisher\.ReadCarrier\(" % m.group(1), body), \
        "the popup does not hand its published value to PopupFace"
    rule = _body(src[AR], "internal virtual string PopupFace(")
    local = rule.index("if (pickerIsLocal) return published == FaceCarrierAction.Publish ? publishedValue : null;")
    assert rule.find("readCarrier()") > local, "the rule calls the reader before answering a local picker"
    return sites, len(rereads)


def test_s33_no_pass_rereads_the_carrier_it_published():
    _check(_s33,
           lambda s: _replace(s, PL, "string popupFace = new AvatarRules().PopupFace(picker.IsLocal, carrier, freshFace,\n"
                                     "                    () => FacePublisher.ReadCarrier(pickerActor));",
                              "string popupFace = FacePublisher.ReadCarrier(pickerActor);"),
           lambda s: _replace(s, PL, '"the value this pass published"', '"the value published this pass"'))


def test_s33_a_local_arm_that_calls_the_reader_reds():
    _check(_s33,
           lambda s: _replace(s, AR, "if (pickerIsLocal) return published == FaceCarrierAction.Publish ? publishedValue : null;",
                              "if (pickerIsLocal && readCarrier != null) return readCarrier();\n"
                              "            if (pickerIsLocal) return published == FaceCarrierAction.Publish ? publishedValue : null;"),
           lambda s: _replace(s, AR, "return readCarrier != null ? readCarrier() : null;",
                              "return readCarrier == null ? null : readCarrier();"))


# S35 (fix pass 2, H6 M8 BR-M4 L1 H9 M3): the production probe ----------------
#
# tools/item19-controls/prodprobe compiles THIS tree's plugin/AvatarDefaults.cs
# and plugin/AvatarDefaultRules.cs, unedited, against stand-ins for the game,
# and drives the real evaluator; each id is one behaviour read at the sink a
# player would see. item19_controls.py mutates the production expressions
# (each liveness assignment, both log-guard arms, the staged room read, the
# sprite and announcement sinks, the deferred restoration) and requires this
# test to go red on each and stay green on a neighbouring twin.

PRODPROBE = Path(REPO) / "tools" / "item19-controls" / "prodprobe"
PRODPROBE_IDS = ("H6a", "H6b", "H6c", "H9c", "H9s", "M3t", "BRM4", "M8apply", "M8room", "L1sprite", "L1announce")


def _dotnet():
    import shutil
    found = shutil.which("dotnet")
    if found:
        return found
    candidate = Path(os.path.expanduser("~")) / ".dotnet" / "dotnet.exe"
    return str(candidate) if candidate.exists() else None


@pytest.fixture(scope="module")
def prodprobe(tmp_path_factory):
    import shutil
    import subprocess
    dotnet = _dotnet()
    if dotnet is None:
        pytest.skip("dotnet CLI not on this machine")
    d = tmp_path_factory.mktemp("prodprobe")
    for f in ("Stubs.cs", "ProdProbe.cs", "item19-prodprobe.csproj"):
        shutil.copyfile(str(PRODPROBE / f), str(d / f))
    for f in (AD, AR):
        shutil.copyfile(str(PLUGIN / f), str(d / f))
    b = subprocess.run([dotnet, "build", str(d / "item19-prodprobe.csproj"), "-c", "Release", "-nologo", "-v", "q"],
                       capture_output=True, text=True, timeout=600)
    assert b.returncode == 0, "the production probe did not build:\n" + b.stdout[-4000:] + b.stderr[-2000:]
    dll = d / "bin" / "Release" / "net10.0" / "item19-prodprobe.dll"
    r = subprocess.run([dotnet, str(dll)], capture_output=True, text=True, timeout=300)
    lines = {}
    for line in r.stdout.splitlines():
        m = re.match(r"PROBE (\S+) (PASS|FAIL) \| (.*)$", line)
        if m:
            lines[m.group(1)] = (m.group(2), m.group(3))
    return lines, r.stdout


def test_s35_the_production_probe_reports_every_id(prodprobe):
    lines, out = prodprobe
    assert sorted(lines) == sorted(PRODPROBE_IDS), "probe ids %s\n%s" % (sorted(lines), out[-3000:])


@pytest.mark.parametrize("pid", PRODPROBE_IDS)
def test_s35_the_production_evaluator_holds(prodprobe, pid):
    lines, out = prodprobe
    assert pid in lines, "the probe did not report %s\n%s" % (pid, out[-3000:])
    verdict, detail = lines[pid]
    assert verdict == "PASS", "%s: %s" % (pid, detail)


# i18n gate part 3 (design 2.10): 25 new keys (the two swap refusals are not on
# this lane) plus the reused "Preset {0}" carry es/ru/uk/sv drafts -----------

ITEM19_LITERALS = [
    "Avatar auto-switch: <color=#88CCFF>ON</color>",
    "Avatar auto-switch: <color=#88CCFF>OFF</color>",
    "Modded avatar: <color=#88CCFF>{0}</color>",
    "Vanilla avatar: <color=#88CCFF>{0}</color>",
    "Modded avatar",
    "Vanilla avatar",
    "Not set",
    "Preset {0} — has items an unmodded player cannot see",
    "No preset is free of modded items yet.",
    "Avatar defaults",
    "Gold ring: your modded default",
    "Blue ring: your vanilla default",
    "Both rings: this preset is both of your defaults",
    "Red ring: this preset has items an unmodded player cannot see, so it cannot be your vanilla default",
    "Switched to your vanilla avatar for this room.",
    "Switched back to your modded avatar.",
    "Your vanilla avatar preset has items an unmodded player cannot see, so your avatar was not switched.",
    "That preset has never been customised, so your avatar was not switched.",
    "To make a preset an unmodded opponent can see: open the character menu, choose an empty preset, and build the face from base-game eyes, mouths and details only.",
    "Modded eyes, mouths and details are drawn by the mod. A player without the mod sees an empty slot where each one should be. This picks the plain preset for you in games where that would happen, and gives you your own face back when you leave.",
    "The preset you wear everywhere the mod is running: ranked, 2v2, 1v2, FFA and private games where everyone has the mod.",
    "The preset you wear in Quick Match and in any game where somebody does not have the mod. Only presets a base-game player's own game can load are offered here, because those are the only ones an unmodded opponent can actually see. To make a preset an unmodded opponent can see: open the character menu, choose an empty preset, and build the face from base-game eyes, mouths and details only.",
    "keeps a modded avatar out of games where it renders with holes",
    "any preset; this is the one you wear everywhere else",
    "only presets an unmodded opponent's own loader can resolve are visible to them",
]
REUSED = "Preset {0}"
_ENTRY = re.compile(r'\[("(?:[^"\\]|\\.)*")\]\s*=\s*("(?:[^"\\]|\\.)*")')


def _catalogues(text):
    out = {}
    for loc in ("ES", "RU", "UK", "SV"):
        a, b = _one(text, "private static readonly Dictionary<string, string> %s = new Dictionary<string, string>" % loc)
        d = {}
        for m in _ENTRY.finditer(text[a:b]):
            d[json.loads(m.group(1))] = json.loads(m.group(2))
        out[loc] = d
    return out


def _part3(src, keys):
    cats = _catalogues(src[CAT])
    for loc, d in cats.items():
        for k in keys:
            assert d.get(k), "%s has no %s draft for %r" % (CAT, loc, k[:60])


def test_i18n_every_item_19_literal_is_a_harvested_source_key():
    with io.open(os.path.join(REPO, "tools", "i18n_source.json"), encoding="utf-8") as fh:
        strings = set(json.load(fh)["strings"])
    missing = [k for k in ITEM19_LITERALS + [REUSED] if k not in strings]
    assert not missing, missing
    assert len(set(ITEM19_LITERALS)) == 25


def test_i18n_part_3_every_key_carries_four_drafts():
    keys = ITEM19_LITERALS + [REUSED]

    def strip_drafts(s, key):
        t = s[CAT]
        lit = re.escape(json.dumps(key, ensure_ascii=True).replace("\\u2014", "\\u2014"))
        t2, n = re.subn(r"\n[ \t]*\[" + lit + r"\][^\n]*", "", t)
        assert n == 4, (key, n)
        s = dict(s)
        s[CAT] = t2
        return s
    # control key: one item 19 does not consume
    _check(lambda s: _part3(s, keys),
           lambda s: strip_drafts(s, REUSED),
           lambda s: strip_drafts(s, "A player joined the match"))
