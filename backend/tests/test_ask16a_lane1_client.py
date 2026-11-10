"""Ask 16(a) lane 1: the bounded deal (R4) and the clamp table (D2), client half.

The deal's decisions are pure (plugin/BoundedDealRules.cs) and run in the client
rules harness as suite `dealbound`, with a mutant per rule. The clamp table and its
rules (plugin/LimitlessBounds.cs) run as suite `limitbounds`. This file pins both
suites by their case names; checks that the C# table is exactly what
tools/limitless-census/gen_bounds.py generates from the census beside it, so no
number in it is typed; and pins the Unity-side lines of the deal as source claims,
each with mutants that turn it red and a control that leaves it green.

The clamps act only in a limitless game, which lane 2's record defines: lane 1 lands
the table and the rule, and nothing calls them yet. The deal runs in a game only
while every fighter advertises cr_deal1 (the WeaponCooldownReset quorum), and an
offline game is one client.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

from _cs_structure import mask_code, strip_comments_only
from test_client_rules_harness import _suites, harness_run  # noqa: F401  (the module fixture)

REPO = Path(__file__).resolve().parents[2]
PLUGIN = REPO / "plugin"
CENSUS = REPO / "tools" / "limitless-census"
HARNESS = REPO / "tools" / "client-rules-harness"


def _read(path):
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def _generator():
    spec = importlib.util.spec_from_file_location("gen_bounds", CENSUS / "gen_bounds.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


GEN = _generator()
TABLE = GEN.generate(json.loads(_read(CENSUS / "census.json")))


def _lines(text, prefix):
    return [line.strip() for line in text.split("\n") if line.strip().startswith(prefix)]


def _expected(t, qualifier=""):
    ranges, caps = GEN.csharp(t)
    fix = lambda line: line.strip().replace("new Range(", "new %sRange(" % qualifier).replace(
        "new Cap(", "new %sCap(" % qualifier)
    return [fix(x) for x in ranges[1:]], [fix(x) for x in caps[1:]]


# -- D2: the table is the generator's output --------------------------------

def test_the_clamp_table_is_the_generators_output():
    """plugin/LimitlessBounds.cs holds the generator's ranges and caps, line for
    line and in order, with its K and its bullet bound."""
    src = _read(PLUGIN / "LimitlessBounds.cs")
    ranges, caps = _expected(TABLE)
    assert (len(ranges), len(caps)) == (21, 8)
    assert _lines(src, "new Range(") == ranges
    assert _lines(src, "new Cap(") == caps
    assert "internal const int K = %d;" % TABLE["K"] in src
    assert "internal const int BulletsPerTrigger = %d;" % TABLE["bullets"] in src


def test_the_harness_pins_the_generators_table_and_digest():
    """The limitbounds suite's pinned copy is the generator's too, and its pinned
    digest is the generator's digest of that table."""
    cases = _read(HARNESS / "LimitlessBoundsCases.cs")
    ranges, caps = _expected(TABLE, "LimitlessBounds.")
    assert _lines(cases, "new LimitlessBounds.Range(") == ranges
    assert _lines(cases, "new LimitlessBounds.Cap(") == caps
    assert 'private const string PinnedDigest = "%s";' % TABLE["digest"] in cases


def test_control_another_k_gives_another_table():
    """Control: the comparisons above can fail. K = 4 gives other bounds and
    another digest."""
    other = GEN.generate(json.loads(_read(CENSUS / "census.json")), 4)
    ranges, _ = _expected(other)
    assert _lines(_read(PLUGIN / "LimitlessBounds.cs"), "new Range(") != ranges
    assert other["digest"] != TABLE["digest"]


def test_no_shipped_card_adds_jumps():
    """Jumps carry no cap because no shipped card adds one (csm.numberOfJumps)."""
    assert TABLE["jumps_added_by"] == []
    assert not any(c[0].endswith("numberOfJumps") for c in TABLE["caps"])


# -- the two harness suites, by name -----------------------------------------

DEAL_RULES = (
    "first slot: vanilla checks nothing",
    "second slot: the same pool is checked",
    "one acceptable card: vanilla's draw runs",
    "the held rule alone: relax held",
    "the in-hand rule alone: relax held and hand",
    "the gun lock alone: only the last level",
    "the blacklist alone: only the last level",
    "held is relaxed before in-hand",
    "the blacklist is kept while a held, in-hand card remains",
    "the gun lock is kept while a held, in-hand card remains",
    "a weight-0 card is never counted",
    "control: the same card at weight 1 is counted",
    "nothing drawable",
    "a null pool at a later slot",
    "pick: roll 0 takes the first admitted card",
    "pick: roll 1 takes the last admitted card",
    "pick: vanilla's weights, 0.70 of 10+4 is the first",
    "pick: vanilla's weights, 0.75 of 10+4 is the second",
    "pick: a weight-0 card is never picked",
    "pick: a NaN roll reads as 0",
    "pick: no pick at the vanilla level",
    "pick: never a card the level refuses, over 101 rolls",
)
DEAL_MUTANTS = (
    "the first slot is checked", "a weight-0 card is counted", "in-hand is relaxed before held",
    "the blacklist is relaxed early", "the gun lock is relaxed early", "vanilla's draw always runs",
    "the pick ignores the level", "the pick ignores the roll",
)
LIMIT_RULES = (
    "NaN reads as the floor", "+Infinity reads as the ceiling", "-Infinity reads as the floor",
    "below the floor reads as the floor", "above the ceiling reads as the ceiling",
    "inside the band is unchanged", "both ends are inside", "a zeroed field keeps 0 as its floor",
    "a count above its cap reads as the cap", "a count at or under its cap is unchanged",
    "bursts give way: 21 projectiles, 15 bursts", "bursts give way: 10 projectiles, 9 bursts",
    "at the bound nothing gives: 9 projectiles, 9 bursts", "one projectile keeps its bursts",
    "no bursts is one volley",
)
LIMIT_MUTANTS = ("NaN passes through", "no ceiling", "no floor", "no cap", "bursts never give way")


def _caught(names):
    return tuple("mutant (%s) is caught by its named cases" % m for m in names)


DEAL_CASES = tuple("real: " + n for n in DEAL_RULES) + _caught(DEAL_MUTANTS)
LIMIT_CASES = (
    ("the table has the tool's 21 ranges and 8 caps",)
    + tuple("range %s is the census tool's" % r[0] for r in TABLE["ranges"])
    + tuple("cap %s is the census tool's" % c[0] for c in TABLE["caps"])
    + ("every base lies inside its band", "the digest is the census tool's",
       "the version is the protocol and the digest",
       "every single-bound change, K and the bullet bound move the digest")
    + tuple("real: " + n for n in LIMIT_RULES) + _caught(LIMIT_MUTANTS))


@pytest.mark.parametrize("suite,cases", [("dealbound", DEAL_CASES), ("limitbounds", LIMIT_CASES)],
                         ids=["dealbound", "limitbounds"])
def test_the_lane1_suite_ran_exactly_its_cases_and_passed(harness_run, suite, cases):
    """Each suite ran exactly these cases, every one printed PASS, and each mutant
    turned its named cases red (#391)."""
    suites = _suites(harness_run)
    assert suite in suites, harness_run.stdout[-4000:]
    run, fail, verdict = suites[suite]
    assert (run, fail, verdict) == (len(cases), 0, "PASS"), harness_run.stdout[-4000:]
    printed = re.findall(r"^\[%s\] (PASS|FAIL) \| case=([^|]+?) \|" % suite, harness_run.stdout, re.M)
    assert sorted(name for _, name in printed) == sorted(cases), printed
    assert {v for v, _ in printed} == {"PASS"}, printed


# -- R4: the deal's Unity-side lines, as source claims -----------------------

FILES = {p.name: _read(p) for p in sorted(PLUGIN.glob("*.cs"))}
_MASKS = {}


def _masks(text):
    got = _MASKS.get(text)
    if got is None:
        got = _MASKS[text] = (mask_code(text), strip_comments_only(text))
        assert len(got[0]) == len(got[1]) == len(text)
    return got


def _code(text, sig=None):
    """A block (or the whole text) with comments removed, literals kept."""
    masked, stripped = _masks(text)
    if sig is None:
        return stripped
    start = masked.find(sig)
    assert start != -1 and masked.find(sig, start + 1) == -1, "one %r" % sig
    open_brace = masked.find("{", start + len(sig))
    depth = 0
    for i in range(open_brace, len(masked)):
        depth += {"{": 1, "}": -1}.get(masked[i], 0)
        if depth == 0:
            return stripped[open_brace:i + 1]
    raise AssertionError("unbalanced block after %r" % sig)


def _in_order(body, needles):
    at = -1
    for n in needles:
        if body.count(n) != 1 or body.index(n) < at:
            return False
        at = body.index(n)
    return True


PREFIX_SIG = "private static bool BeforeSpawnUniqueCard("
TRY_SIG = "internal static bool TrySpawnBounded("
APPLY_SIG = "internal static bool ShouldApply()"
STAGE_SIG = "internal static void StageCapability(string source)"


def claim_the_prefix_defers(files):
    """SpawnUniqueCard's prefix runs at Priority.Low, after Same Cards (Normal);
    its first statement leaves a slot an earlier prefix dealt; it skips vanilla's
    body only after it dealt the slot and set the result."""
    out = []
    text = files["BoundedDeal.cs"]
    if ('[HarmonyPatch(typeof(CardChoice), "SpawnUniqueCard")]\n    [HarmonyPriority(Priority.Low)]'
            not in _code(text)):
        out.append("the patch is not SpawnUniqueCard at Priority.Low")
    body = _code(text, PREFIX_SIG)
    first = body.lstrip("{ \n").split("\n", 1)[0].strip()
    if first != "if (!__runOriginal) return true;":
        out.append("the first statement is %r" % first)
    if body.count("return false;") != 1 or not _in_order(body, [
            "if (BoundedDeal.TrySpawnBounded(__instance, pos, rot, out dealt))",
            "__result = dealt;", "return false;"]):
        out.append("vanilla is skipped other than after a dealt slot")
    if not body.rstrip("} \n").endswith("return true;"):
        out.append("the fall-through does not run vanilla")
    return out


def claim_the_deal_gates_in_order(files):
    """TrySpawnBounded leaves the first slot, an unset picker and a pick another
    client owns to vanilla (vanilla's own Pick gate); then the rules decide; then
    the room's quorum; only then the pick, by vanilla's weights."""
    body = _code(files["BoundedDeal.cs"], TRY_SIG)
    ok = _in_order(body, [
        "if (handCount <= 0) return false;",
        "if (choice.pickrID < 0) return false;",
        "|| !owner.data.view.IsMine) return false;",
        "var answer = BoundedDealRules.Decide(handCount, pool);",
        "if (answer == BoundedDealRules.Answer.Vanilla || answer == BoundedDealRules.Answer.NothingDrawable)",
        "if (!ShouldApply()) return false;",
        "int index = BoundedDealRules.Pick(answer, pool, UnityEngine.Random.value);",
        "if (index < 0) return false;",
        "var obj = choice.Spawn(source.gameObject, pos, rot);"])
    return [] if ok else ["the gates are missing or out of order"]


def claim_the_room_quorum(files):
    """ShouldApply needs the attached patch, then an offline game or a room
    whose every fighter advertises cr_deal1; a fault keeps vanilla's deal."""
    body = _code(files["BoundedDeal.cs"], APPLY_SIG)
    out = []
    if not _in_order(body, ["if (Plugin.modDisabled || !PatchesLive) return false;",
                            "if (!PhotonNetwork.InRoom) return false;",
                            "bool all = AllFightersCapable(out fighters, out missing);", "return all;"]):
        out.append("the quorum's tests are missing or out of order")
    catch = body[body.index("catch (Exception ex)"):]
    if "return false;" not in catch or "return true;" in catch:
        out.append("a fault applies the deal")
    return out


def claim_the_capability_is_staged_out_of_room(files):
    """cr_deal1 is written only outside a room (the WeaponCooldownReset rule):
    staged at the tick and before a join, revoked with the others, its verdict
    reset at a room change, and reported among the peers' value keys."""
    out = []
    body = _code(files["BoundedDeal.cs"], STAGE_SIG)
    room = body.index("if (PhotonNetwork.InRoom)")
    block = body[room:body.index("}", room)]
    if "return;" not in block or body.find("SetCustomProperties(") < room:
        out.append("the stage writes in a room")
    plugin, fixes = _code(files["Plugin.cs"]), _code(files["VanillaFixes.cs"])
    for needle in ('try { BoundedDeal.StageCapability("tick"); } catch { }',
                   "try { BoundedDeal.RevokeCapability(); } catch { }",
                   "try { BoundedDeal.ResetForRoomChange(); } catch { }"):
        if plugin.count(needle) != 1:
            out.append("Plugin.cs lacks " + needle)
    if fixes.count('BoundedDeal.StageCapability("pre-join");') != 1:
        out.append("no pre-join stage")
    if '"cr_deal1"' not in _code(files["PeerBuildCore.cs"]):
        out.append("peers do not report cr_deal1")
    return out


PIP_SIG = "private static bool BeforeGetPointPos("
PIP_GUARD = "if (parent == null || (rounds >= 0 && rounds < parent.childCount)) return true;"


def claim_the_pips_clamp(files):
    """GetPointPos's prefix leaves every in-range call to vanilla before it writes
    a result, and answers past the pips with the nearest pip, never a child
    beyond the last."""
    out = []
    text = files["RoundPipClamp.cs"]
    if '[HarmonyPatch(typeof(RoundCounter), "GetPointPos")]' not in _code(text):
        out.append("the patch is not RoundCounter.GetPointPos")
    body = _code(text, PIP_SIG)
    first = body.lstrip("{ \n").split("\n", 1)[0].strip()
    if first != "if (!__runOriginal) return true;":
        out.append("the first statement is %r" % first)
    if not _in_order(body, [PIP_GUARD, "parent.GetChild(rounds < 0 ? 0 : count - 1)", "return false;"]):
        out.append("an in-range call does not reach vanilla first, or the answer is not the nearest pip")
    guard = body.find(PIP_GUARD)
    if body.count("__result =") != 1 or guard == -1 or body.find("__result =") < guard:
        out.append("a result is written before the in-range test")
    return out
CLAIMS = {
    "prefix_defers": claim_the_prefix_defers,
    "deal_gates": claim_the_deal_gates_in_order,
    "room_quorum": claim_the_room_quorum,
    "staged_out_of_room": claim_the_capability_is_staged_out_of_room,
    "pips_clamp": claim_the_pips_clamp,
}

BD = "BoundedDeal.cs"
PIPS = "RoundPipClamp.cs"
RUN_ORIGINAL = "            if (!__runOriginal) return true;   // an earlier prefix has dealt this slot\n"
QUORUM = "            if (!ShouldApply()) return false;   // a mixed room keeps vanilla's deal, as today\n"
DEALT = ("                    __result = dealt;\n                    return false;\n                }\n            }\n"
         '            catch (Exception ex) { VanillaFixSupport.LogError("BoundedDeal", ex); }\n            return true;\n')
REFUSE_IN_ROOM = ('                        + source + ") - an in-room write is the racy path this protocol forbids");\n'
                  "                    return;\n")


def _drop(fname, line):
    return [(fname, line, "")]


MUTANTS = [
    ("prefix_defers", "the prefix runs ahead of Same Cards",
     [(BD, "    [HarmonyPriority(Priority.Low)]\n", "    [HarmonyPriority(Priority.First)]\n")]),
    ("prefix_defers", "the prefix deals over an earlier prefix's slot", _drop(BD, RUN_ORIGINAL)),
    ("prefix_defers", "the prefix skips vanilla when it dealt nothing",
     [(BD, DEALT, DEALT[:-len("            return true;\n")] + "            return false;\n")]),
    ("prefix_defers", "the prefix skips vanilla without the dealt card",
     _drop(BD, "                    __result = dealt;\n")),
    ("deal_gates", "the first slot is bounded", _drop(BD, "            if (handCount <= 0) return false;\n")),
    ("deal_gates", "a pick another client owns is dealt here",
     [(BD, "|| !owner.data.view.IsMine) return false;", ") return false;")]),
    ("deal_gates", "vanilla's level is dealt here",
     [(BD, "if (answer == BoundedDealRules.Answer.Vanilla || answer == BoundedDealRules.Answer.NothingDrawable)",
       "if (answer == BoundedDealRules.Answer.NothingDrawable)")]),
    ("deal_gates", "a mixed room gets the bounded deal", _drop(BD, QUORUM)),
    ("deal_gates", "the quorum is read after the pick",
     [(BD, QUORUM, ""), (BD, "            if (index < 0) return false;\n",
                         "            if (index < 0) return false;\n" + QUORUM)]),
    ("room_quorum", "a client without the attached patch applies",
     [(BD, "if (Plugin.modDisabled || !PatchesLive) return false;", "if (Plugin.modDisabled) return false;")]),
    ("room_quorum", "the quorum is not read", [(BD, "                return all;\n", "                return true;\n")]),
    ("room_quorum", "a fault applies the deal",
     [(BD, 'VanillaFixSupport.LogError("BoundedDeal", ex);\n                return false;',
       'VanillaFixSupport.LogError("BoundedDeal", ex);\n                return true;')]),
    ("staged_out_of_room", "the capability is written in a room",
     [(BD, REFUSE_IN_ROOM, REFUSE_IN_ROOM[:-len("                    return;\n")])]),
    ("staged_out_of_room", "the tick never stages",
     _drop("Plugin.cs", '            try { BoundedDeal.StageCapability("tick"); } catch { }\n')),
    ("staged_out_of_room", "nothing revokes the capability",
     _drop("Plugin.cs", "                        try { BoundedDeal.RevokeCapability(); } catch { }\n")),
    ("staged_out_of_room", "a room change keeps the old verdict",
     _drop("Plugin.cs", "            try { BoundedDeal.ResetForRoomChange(); } catch { }\n")),
    ("staged_out_of_room", "no stage before a join",
     _drop("VanillaFixes.cs", '                BoundedDeal.StageCapability("pre-join");\n')),
    ("staged_out_of_room", "peers do not report cr_deal1",
     [("PeerBuildCore.cs", '"cr_dc3", "cr_deal1", ', '"cr_dc3", ')]),
    ("pips_clamp", "the prefix overrides a call another prefix answered",
     _drop(PIPS, "            if (!__runOriginal) return true;   // an earlier prefix has answered\n")),
    ("pips_clamp", "every call answers the last pip", [(PIPS, PIP_GUARD, "if (parent == null) return true;")]),
    ("pips_clamp", "the last in-range pip is clamped",
     [(PIPS, "rounds < parent.childCount)) return true;", "rounds < parent.childCount - 1)) return true;")]),
    ("pips_clamp", "the answer indexes past the last pip",
     [(PIPS, "parent.GetChild(rounds < 0 ? 0 : count - 1)", "parent.GetChild(rounds < 0 ? 0 : count)")]),
]

NEUTRAL = "            // control: a neutral line\n"
CONTROLS = [
    ("prefix_defers", [(BD, RUN_ORIGINAL, NEUTRAL + RUN_ORIGINAL)]),
    ("deal_gates", [(BD, QUORUM, NEUTRAL + QUORUM)]),
    ("room_quorum", [(BD, "                return all;\n", NEUTRAL + "                return all;\n")]),
    ("staged_out_of_room", [("Plugin.cs", '            try { BoundedDeal.StageCapability("tick"); } catch { }\n',
                             NEUTRAL + '            try { BoundedDeal.StageCapability("tick"); } catch { }\n')]),
    ("pips_clamp", [(PIPS, "                if (__instance == null) return true;\n",
                     NEUTRAL + "                if (__instance == null) return true;\n")]),
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
