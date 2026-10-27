"""Client source checks, merge pass 5 of the 1.41.0 beta lane.

1. The seven evidence lines a player can dispute ship in every client build:
   [POISON-LATE], [HP-POINT-END], [SAW-POINT], [HIT-RECV], [SHOT-OBS],
   [BLOCK-MISS] and [PEER-BUILD]. Each is emitted from code that no setting,
   no dev lever and no room-kind check stands in front of: the Harmony
   classes that drive the first six are applied by Plugin's per-class loop
   with no filter, and [PEER-BUILD] runs from the always-on tick ABOVE the
   modDisabled return. What the functions on each path may still test is the
   data itself (was anything counted, is the victim the local player), never
   a configuration.

2. [PEER-BUILD]: one line per remote seat per room join, and again when the
   values it states change. The line lists every key the seat published and
   prints the value of only the build statement (cr_build) and the plugin's
   capability keys, which this file holds equal to the CapabilityProp
   constants. No account id or display name is read into the line. The pure
   half (PeerBuildCore.cs) is executed by tools/tests/hit-evidence-client
   (case peer and the peer_* mutants).
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugin"
POISON = PLUGIN / "PoisonSync.cs"
HIT = PLUGIN / "HitEvidence.cs"
HITCORE = PLUGIN / "HitEvidenceCore.cs"
PEER = PLUGIN / "PeerBuild.cs"
PEERCORE = PLUGIN / "PeerBuildCore.cs"
MAIN = PLUGIN / "Plugin.cs"

TAGS = ["[POISON-LATE]", "[HP-POINT-END]", "[SAW-POINT]", "[HIT-RECV]", "[SHOT-OBS]", "[BLOCK-MISS]", "[PEER-BUILD]"]

# What a gate in front of an evidence line would read: a room-kind check, a
# ranked/competitive test, a setting (Plugin.<Name>.Value or any Config
# access), a dev lever, the room rules, or the mod's own disabled flag.
GATE = re.compile(
    r"IsCompetitiveRoom|IsRanked|InRanked|RoomRules|Plugin\.[A-Z]\w*\.Value|ConfigEntry|\bConfig\.|"
    r"Lever|DevMode|IsDev|modDisabled|#if|LocalIsSpectator\s*\)\s*return")


def _read(path):
    return path.read_text(encoding="utf-8")


def _member(src, signature):
    """The member whose declaration starts with `signature`, to its matching
    brace. The signature must occur once."""
    assert src.count(signature) == 1, "%r occurs %d times" % (signature, src.count(signature))
    start = src.index(signature)
    i = src.index("{", start)
    depth = 0
    while i < len(src):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
        i += 1
    raise AssertionError("no end for %r" % signature)


def _code(text):
    """The text without // comments, so a comment that names a gate is not a gate."""
    return "\n".join(line.split("//", 1)[0] for line in text.splitlines())


# -- 1. no gate in front of any of the seven lines -----------------------------

def test_each_tag_is_written_by_one_file_only():
    owners = {"[POISON-LATE]": POISON, "[HP-POINT-END]": POISON, "[SAW-POINT]": POISON,
              "[HIT-RECV]": HITCORE, "[SHOT-OBS]": HITCORE, "[BLOCK-MISS]": HITCORE, "[PEER-BUILD]": PEERCORE}
    for tag in TAGS:
        users = [p.name for p in sorted(PLUGIN.glob("*.cs")) if tag in _code(_read(p))]
        assert users == [owners[tag].name], "%s is written by %s" % (tag, users)


def test_the_harmony_loop_applies_every_patch_class_unfiltered():
    src = _read(MAIN)
    loop = src[src.index("foreach (var type in Assembly.GetExecutingAssembly().GetTypes())"):]
    loop = loop[:loop.index('Log.LogInfo($"[HARMONY] Patches applied')]
    body = _code(loop)
    assert body.count("continue;") == 1 and "if (attrs == null || attrs.Length == 0) continue;" in body, \
        "the patch loop skips a class for a reason other than having no [HarmonyPatch]"
    assert "HarmonyInstance.CreateClassProcessor(type).Patch();" in body
    assert not GATE.search(body), GATE.search(body).group(0)


def test_the_six_beta_bug_lines_have_no_gate_in_front():
    poison = _read(POISON)
    hit = _read(HIT)
    # The emitting members and the members that feed them on every seat.
    paths = [
        (poison, "private static void NoteSilence("),
        (poison, "private static void NoteVerdictAfterSilence("),
        (poison, "internal static void ReportUnansweredSilences("),
        (poison, "internal static void PointEnd()"),
        (poison, "internal static void SawBefore()"),
        (poison, "internal static void SawAfter()"),
        (poison, "internal static void GameOverCheck("),
        (poison, "internal static class SawPointEvidencePatch"),
        (poison, "internal static class PointEndEvidencePatch"),
        (hit, "internal static void NoteDamage("),
        (hit, "internal static void NoteForce("),
        (hit, "internal static void NoteDot("),
        (hit, "internal static void NoteBlock("),
        (hit, "internal static void NoteSpawn("),
        (hit, "internal static void NoteImpact("),
        (hit, "internal static void PointEnd(int point)"),
        (hit, "internal static void GameEnd(int point)"),
        (hit, "internal static class HitEvidence_ExecuteRpcPatch"),
        (hit, "internal static class HitEvidence_StartGamePatch"),
    ]
    for src, sig in paths:
        body = _code(_member(src, sig))
        m = GATE.search(body)
        assert m is None, "%s has a gate: %s" % (sig, m.group(0))
    # Every patch class that feeds them is a [HarmonyPatch], so the loop above applies it.
    for src, names in ((poison, ["SawPointEvidencePatch", "PointEndEvidencePatch"]),
                       (hit, ["HitEvidence_ExecuteRpcPatch", "HitEvidence_DamagePatch", "HitEvidence_ForcePatch",
                              "HitEvidence_DotPatch", "HitEvidence_BlockPatch", "HitEvidence_SpawnAmmoPatch",
                              "HitEvidence_SpawnNoAmmoPatch", "HitEvidence_SpawnSeparatePatch",
                              "HitEvidence_ImpactPatch", "HitEvidence_StartGamePatch",
                              "HitEvidence_FfaDoStartGamePatch"])):
        for n in names:
            head = src[:src.index("internal static class " + n)]
            assert head.rstrip().splitlines()[-1].lstrip().startswith("[HarmonyPatch"), n + " is not a [HarmonyPatch] class"


# -- 2. [PEER-BUILD] -----------------------------------------------------------

def test_peer_build_runs_from_the_always_on_tick_above_the_disabled_return():
    # The always-on tick is the Update that runs the fps tick first (Plugin.cs
    # has three Update methods; this one is the persistent loop's).
    src = _read(MAIN)
    sig = "private void Update()\n        {\n            // Aug 6 item 8 / Aug 7 item 2: the fps tick runs BEFORE the"
    src = src.replace("\r\n", "\n")
    update = _code(_member(src, sig))
    assert "TickUnfocusedFpsCap();" in update
    call = 'try { PeerBuild.StageBuildProp("tick"); PeerBuild.Tick(); } catch { }'
    assert update.count(call) == 1, "the [PEER-BUILD] tick is not wired once"
    assert update.index(call) < update.index("if (Plugin.modDisabled) return;"), \
        "the [PEER-BUILD] tick sits below the modDisabled return"
    # Nothing returns between the top of Update and the call.
    assert "return" not in update[:update.index(call)]
    # The tick itself reads no configuration and no room kind.
    tick = _code(_member(_read(PEER), "internal static void Tick()"))
    m = GATE.search(tick)
    assert m is None, "PeerBuild.Tick has a gate: " + m.group(0)
    stage = _code(_member(_read(PEER), "internal static void StageBuildProp("))
    m = GATE.search(stage)
    assert m is None, "StageBuildProp has a gate: " + m.group(0)


def test_peer_build_prints_once_per_seat_per_room_and_again_on_change():
    tick = _code(_member(_read(PEER), "internal static void Tick()"))
    assert "PhotonNetwork.PlayerListOthers" in tick, "the line is not per remote seat"
    leave = tick[tick.index("if (!PhotonNetwork.InRoom"):tick.index("float now")]
    assert "_printed.Clear();" in leave, "leaving a room does not forget what was printed"
    assert "if (room != _room) { _printed.Clear(); _room = room; }" in tick, "a new room does not reprint"
    assert "string values = PeerBuildCore.Values(props);" in tick
    assert "if (_printed.TryGetValue(p.ActorNumber, out last) && last == values) continue;" in tick, \
        "the line is not deduplicated by its values"
    assert tick.count("Plugin.Log.") == 1 and "Plugin.Log.LogInfo(PeerBuildCore.Line(p.ActorNumber, props));" in tick


def test_peer_build_value_keys_are_the_build_statement_and_the_capability_keys():
    # Merge pass 6 (R-L1): every cr_ constant whose NAME says capability,
    # spelled Capability (CapabilityPropV3 included) or _CAP_ (the shared game
    # token's GAME_TOKEN_CAP_PROP_KEY), whatever follows it in the name.
    caps = set()
    for p in PLUGIN.glob("*.cs"):
        for m in re.finditer(r'const string \w*(?:Capability|_CAP_)\w* = "(cr_\w+)"', _code(_read(p))):
            caps.add(m.group(1))
    assert len(caps) >= 11, caps
    assert {"cr_pois3", "cr_game_token_v"} <= caps, caps
    core = _code(_read(PEERCORE))
    block = core[core.index("internal static readonly string[] ValueKeys ="):]
    block = block[:block.index("};")]
    listed = re.findall(r'"(cr_\w+)"', block)
    assert "BuildProp," in block and 'internal const string BuildProp = "cr_build";' in core
    assert sorted(listed) == sorted(caps), "ValueKeys %s != capability keys %s" % (sorted(listed), sorted(caps))
    assert len(listed) == len(set(listed))


def test_peer_build_reads_no_account_identity():
    for p in (PEER, PEERCORE):
        code = _code(_read(p))
        for word in ("NickName", "UserId", "u_id", "SteamId", "LocalSteamId", "MatchTracker"):
            assert word not in code, "%s reads %s" % (p.name, word)
    # The only value the Unity half reads per key is handed to the core, which
    # prints values of ValueKeys alone (executed by the harness case peer).
    core = _code(_member(_read(PEERCORE), "internal static string Line("))
    assert "props.TryGetValue" not in core and "kv.Value" not in core, "Line reads a value outside Values()"
