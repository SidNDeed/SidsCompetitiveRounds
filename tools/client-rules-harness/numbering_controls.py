"""RJ-DRIFT numbering controls (design V10 section 5, "Driver" and "Controls":
V4's 23 rows, then the 14 of V5-V9).

For each control row: copy the rule files, the harness project and Main.cs to
a work directory (the tree itself is never edited, checked out or restored),
apply ONE textual edit whose anchor occurs exactly once inside the named
function, build, run, and compare the full observed FAIL set (unit ids,
ffareport checks named by their FfaReportRules.cs line at the design's pin,
walk case ids) with the row's expected set, both ways. A mutation must also
print its named failure line; its inert twin (the same line, meaning
unchanged) must print no failure at all.

Exit status: 0 only when every row matches its expected set exactly, every
mutation prints its named line and every build and run behaved as expected.
Each row's result is also compared modulo the baseline's own FAIL set, so a
case that is red before any mutation is reported once, as a baseline
exception, instead of hiding what each control does to the other cases.

Usage: python numbering_controls.py [--work DIR] [--only ID[,ID...]] [--log FILE]
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))

def _compile_set():
    """The work copy is the harness project's own compile set, read from its
    Compile items: every ../../plugin/ file and every harness-local file, plus
    the project itself. (Merge pass 7 of the v1.41.0 lane: the harness there
    compiles fourteen suites, so a fixed list of the numbering suite's seven
    rule files no longer builds.) Refuses when a required file is missing."""
    proj = os.path.join(HERE, "client-rules-harness.csproj")
    with open(proj, encoding="utf-8") as f:
        text = f.read()
    plugin, harness = [], []
    for inc in re.findall(r'<Compile Include="([^"]+)"', text):
        inc = inc.replace("\\", "/")
        if inc.startswith("../../plugin/") and "/" not in inc[len("../../plugin/"):]:
            plugin.append(inc[len("../../plugin/"):])
        elif "/" not in inc:
            harness.append(inc)
        else:
            raise ValueError("compile item outside plugin/ and the harness folder: %r" % inc)
    for need in ("FfaNumberingRules.cs", "FfaReportRules.cs"):
        if need not in plugin:
            raise ValueError("the harness project does not compile %s" % need)
    return plugin, harness + ["client-rules-harness.csproj"]


PLUGIN_FILES, HARNESS_FILES = _compile_set()

# ── case ids ────────────────────────────────────────────────────────────

ORD = ("i", "ii", "iii")


def _d(w):
    major = w[1]
    return "D12" if major == "7" else "D" + major


def walk(w, *orders):
    """walk("W3.1") -> the three ordered ids; walk("W3.1", "i", "iii") -> two;
    walk("W4.3", None) -> the single unordered id."""
    if orders == (None,):
        return ["walk-%s %s" % (_d(w), w)]
    return ["walk-%s %s(%s)" % (_d(w), w, x) for x in (orders or ORD)]


ALL_WALKS = (
    walk("W3.1") + walk("W3.2") + walk("W3.2m", None) + walk("W3.3") + walk("W3.4")
    + walk("W4.1") + walk("W4.2") + walk("W4.3", None) + walk("W4.4")
    + walk("W5.1", None) + walk("W5.2") + walk("W5.2m", None) + walk("W5.2x", None)
    + walk("W5.2f", None) + walk("W5.3") + walk("W5.4")
    + walk("W6.1") + walk("W6.2", None) + walk("W6.3q", None) + walk("W6.3n", None)
    + walk("W6.4", None) + walk("W6.5") + walk("W6.6") + walk("W6.6s", None) + walk("W6.7")
    + walk("W6.7a", None) + walk("W6.8", None) + walk("W6.8d", None) + walk("W6.9")
    + walk("W6.9p", None)
    + [w for n in range(10, 16) for w in walk("W6.%d" % n, None)]
    + [w for n in range(1, 12) for w in walk("W7.%d" % n, None)]
)
assert len(ALL_WALKS) == 77, len(ALL_WALKS)
assert len(set(ALL_WALKS)) == 77

# FfaReportRules.cs lines at the design's pin (V10: 901ed11; V4 cited 426,
# 447, 460 and 472 at 46f54d4) -> the check's name (names are stable across
# the port; line numbers are not).
FFAREPORT = {
    465: "a rollover after the freeze cannot change the key",
    487: "a later freeze cannot move a key already taken",
    502: "a seat that froze after the rollover files a different game",
    515: "a cleared snapshot files nothing",
}


def units(*ids):
    return ["U-" + i for i in ids]


def ffa(*lines):
    return ["ffareport:" + FFAREPORT[n] for n in lines]


D3_WALKS = [w for w in ALL_WALKS if not any(w.endswith(" " + x) for x in (
    "W5.1", "W6.2", "W6.3q", "W6.3n", "W6.4", "W6.12", "W6.13", "W6.14", "W7.1", "W7.2", "W7.3",
    "W7.4", "W7.6", "W7.7", "W7.9", "W7.10", "W7.11"))]
assert len(D3_WALKS) == 60, len(D3_WALKS)

C_LIVE_WALKS = (
    [x for w in ("W3.1", "W3.2", "W3.3", "W3.4", "W4.1", "W4.4", "W5.2", "W5.3", "W6.7")
     for x in walk(w, "i", "iii")]
    + walk("W3.2m", None) + walk("W5.2m", None)
    + [x for w in ("W4.2", "W5.4", "W6.1", "W6.5", "W6.9") for x in walk(w)]
    + walk("W6.9p", None) + walk("W6.11", None)
)
assert len(C_LIVE_WALKS) == 37, len(C_LIVE_WALKS)

C_STALE_WALKS = (
    [x for w in ("W3.1", "W3.2", "W3.3", "W3.4", "W4.1", "W4.2", "W4.4", "W5.2", "W5.3", "W5.4",
                 "W6.1", "W6.5", "W6.7") for x in walk(w, "ii")]
    + walk("W6.6") + walk("W6.6s", None) + walk("W6.7a", None) + walk("W6.15", None)
    + walk("W6.10", None) + walk("W6.9") + walk("W6.9p", None)
)
assert len(C_STALE_WALKS) == 24, len(C_STALE_WALKS)

# ── the rows (V10 section 5: V4's 23, then V5-V9's 14) ─────────────────
# Each: id, file, function signature text, anchor, mutation, twin,
# expected FAIL set, (case id or None, named failure substring).

NR = "FfaNumberingRules.cs"
RR = "FfaReportRules.cs"

ROWS = [
    ("C-D3", NR, "static void StartNumbers(", "roomGame = NoGame;",
     "roomGame = counter + 1;", "roomGame = -1;",
     units("START-2", "START-4", "START-6", "START-8") + D3_WALKS,
     ("walk-D3 W3.1(i)", "two numbers g4 RG{A4,B4,C1,D4}")),
    ("C-D4", NR, "static void StartNumbers(", "roomGame = NoGame;",
     "roomGame = cycleGameAtStart >= 1 ? cycleGameAtStart + 1 : NoGame;",
     "roomGame = cycleGameAtStart >= 1 ? NoGame : NoGame;",
     units("START-2", "START-4", "START-6", "START-8") + D3_WALKS,
     ("walk-D4 W4.3", "two numbers g1 RG{A1,B2,C1,D1}")),
    ("C-D5", NR, "static bool SameIncarnation(", "a != null && ReferenceEquals(a, b)",
     "a != null", "a != null && ReferenceEquals(b, a)",
     units("INC-2", "ARM-2", "ROOM-2", "ROOM-3") + walk("W4.2") + walk("W5.2m", None) + walk("W5.3")
     + walk("W5.4") + walk("W6.1") + walk("W6.5") + walk("W6.7") + walk("W6.7a", None)
     + walk("W7.8", None),
     ("walk-D5 W5.3(i)", "two numbers g4 RG{A4,B4,D4,X7}")),
    ("C-D6", NR, "static int Candidate(",
     "ticketValid && ticketGame >= 1 ? ticketGame : (readback >= 1 ? readback : NoGame)",
     "readback >= 1 ? readback : NoGame",
     "ticketGame >= 1 && ticketValid ? ticketGame : (readback >= 1 ? readback : NoGame)",
     units("CAND-1", "CAND-4") + walk("W6.4", None) + walk("W6.6s", None),
     ("walk-D6 W6.6s", "two numbers g5 RG{A4,B2,C2,D2}")),
    ("C-SNAP", NR, "static bool SnapshotArmed(", "return SameIncarnation(armedIn, room);",
     "return armedIn != null;", "return SameIncarnation(room, armedIn);",
     units("ARM-2") + walk("W4.2") + walk("W5.2m", None) + walk("W5.4") + walk("W6.1") + walk("W6.5")
     + walk("W7.8", None),
     ("walk-D6 W6.5(i)", "two numbers g4 F{A4,B4,C3,D4}")),
    ("C-HELD", NR, "static bool HeldByRoom(", "return candidate >= 1 && (masterHolds || fighterHolds);",
     "return candidate >= 1;", "return candidate >= 1 && (fighterHolds || masterHolds);",
     units("HELD-3", "HELD-6") + walk("W6.3n", None) + walk("W6.4", None) + walk("W6.6")
     + walk("W6.6s", None) + walk("W6.7a", None) + walk("W6.8d", None) + walk("W6.9")
     + walk("W6.9p", None) + walk("W6.10", None) + walk("W6.11", None) + walk("W6.15", None)
     + walk("W7.5", None),
     ("walk-D6 W6.6(i)", "provenance g4 F{A1,B1,C1,D1}")),
    ("C-ROOMHELD", NR, "static bool HeldByRoom(", "return candidate >= 1 && (masterHolds || fighterHolds);",
     "return candidate >= 1 && masterHolds;",
     "return candidate >= 1 && (masterHolds || fighterHolds || false);",
     units("HELD-2", "HELD-5") + walk("W6.8", None) + walk("W6.8d", None),
     ("walk-D6 W6.8", "EXPECTED g1 F none, expected 1")),
    ("C-UNGATE", NR, "static bool HeldByRoom(", "return candidate >= 1 && (masterHolds || fighterHolds);",
     "if (!gate) return candidate >= 1;\n            return candidate >= 1 && (masterHolds || fighterHolds);",
     "if (!gate && candidate < 0) return candidate >= 1;\n"
     "            return candidate >= 1 && (masterHolds || fighterHolds);",
     units("HELD-6") + walk("W6.3n", None) + walk("W6.4", None) + walk("W6.11", None) + walk("W6.15", None)
     + walk("W7.5", None),
     ("walk-D12 W7.5", "EXPECTED g4 F{A1,B1,C1} expected none")),
    ("C-VOID", NR, "static int WitnessAtJoin(", "return NoGame;",
     "return held;", "return -1;",
     units("WIT-3") + walk("W6.1") + walk("W7.8", None),
     ("walk-D6 W6.1(i)", "g4 E{A,B,C,D} on A,B,D: C holds none")),
    ("C-LB", NR, "static int LeaverStampSource(", "return seq;",
     "return counter;", "return seq + 0;",
     units("LB-1") + walk("W7.4", None),
     ("walk-D12 W7.4", "LEAVER g7 body lists P absent (left in g7)")),
    ("C-ARM", RR, "void Clear(object room)", "_armedIn = room;",
     "_armedIn = null;", "_armedIn = room ?? null;",
     ffa(465, 487, 502) + ALL_WALKS,
     (None, "LIVE-F g1 F none on A")),
    ("C-CAND", NR, "static int CarryAfterGameOver(", "return candidate + 1;",
     "return fieldAtCarry + 1;", "return 1 + candidate;",
     units("CARRY-5") + walk("W6.6s", None),
     ("walk-D6 W6.6s", "two numbers g5 RG{A4,B2,C2,D2}")),
    ("C-REENTRY", NR, "static bool RoomObjectChanged(", "return !SameIncarnation(lastRoom, room);",
     "return lastName != name;", "return !SameIncarnation(room, lastRoom);",
     units("ROOM-2") + walk("W4.2") + walk("W6.1") + walk("W6.5") + walk("W6.7") + walk("W6.7a", None),
     ("walk-D6 W6.7(i)", "RESET g4 C counter 4 sequence 4")),
    ("C-LIVE", NR, "static int PickIdentitySource(", "return liveGame >= 1 ? liveGame : NoGame;",
     "return counter;", "return liveGame >= 1 ? liveGame : -1;",
     units("PICK-4", "PICK-5", "PICK-6", "PICK-7") + C_LIVE_WALKS,
     ("walk-D3 W3.1(i)", "g4 CS{A4,B4,C1,D4}")),
    ("C-STALE", NR, "static bool LiveCycle(",
     "return g >= 1 && !resultPresent && !(deadlineKnown && now > deadline + 15f);",
     "return g >= 1;",
     "return !resultPresent && g >= 1 && !(deadlineKnown && now > deadline + 15f);",
     units("LIVE-2", "LIVE-3") + C_STALE_WALKS,
     ("walk-D3 W3.1(ii)", "g4 CS{A4,B4,C3,D4}")),
    ("C-GATE", NR, "static bool DriftGate(", "if (localAdvert != want) return false;",
     "", "if (want != localAdvert) return false;",
     units("GATE-2", "GATE-5") + walk("W5.2x", None) + walk("W5.2f", None) + walk("W6.3n", None)
     + walk("W6.3q", None) + walk("W6.4", None) + walk("W6.11", None) + walk("W6.12", None)
     + walk("W6.13", None) + walk("W6.15", None) + walk("W7.6", None) + walk("W7.7", None),
     ("walk-D12 W7.6", "AGREE-G g1 G{A0,B1,C0,D0}")),
    ("C-KEY", NR, "static int StagedAdvertKey(", "return RoomKey(target);",
     "return RoomKey(current);", "return RoomKey((target));",
     units("KEY-4") + ALL_WALKS,
     (None, "EXPECTED g1 advert{A,B,C,D} 1:136261 expected 1:987561")),
    ("C-LP", NR, "static int LivePointsGame(", "if (candidate >= 1) return candidate;",
     "return counter;", "if (candidate >= 1) return candidate + 0;",
     units("LP-2", "LP-3", "LP-4", "LP-5") + walk("W6.9") + walk("W6.9p", None) + walk("W6.11", None),
     ("walk-D6 W6.9(i)", "LIVE-POINTS g2 A sent 2, expected the candidate 1")),
    ("C-SETTLE", NR, "static int LivePointsGame(", "if (candidate >= 1) return candidate;",
     "if (candidate >= 1 && (held || !gate)) return candidate;",
     "if (candidate >= 1 && (held || true)) return candidate;",
     units("LP-4") + walk("W6.6") + walk("W6.6s", None) + walk("W6.7a", None) + walk("W6.8d", None)
     + walk("W6.9") + walk("W6.9p", None) + walk("W6.10", None) + walk("W6.11", None)
     + walk("W6.15", None),
     ("walk-D6 W6.8d", "SETTLE-LOCK g1 _r1 accepted, game 1 never locked")),
    ("C-FOLLOW", NR, "static bool FollowsHost(",
     "return !isMaster && masterPresent && masterWitness == NoGame && roomGame >= 1;",
     "return false;",
     "return !isMaster && masterPresent && NoGame == masterWitness && roomGame >= 1;",
     units("FOL-1") + walk("W6.9") + walk("W6.9p", None),
     ("walk-D6 W6.9(i)", "AGREE-P g2 P{A1:1,B2:1,C1:1}")),
    ("C-COMMON", NR, "static int CarryAfterGameOver(",
     "if (masterPresent && masterGame == NoGame && candidate >= 1)",
     "if (masterPresent && masterGame == NoGame && candidate >= 1 && !heldRGAtStart)",
     "if (masterPresent && masterGame == NoGame && candidate >= 1 && (heldRGAtStart || !heldRGAtStart))",
     units("CARRY-4") + walk("W6.9") + walk("W6.11", None),
     ("walk-D6 W6.9(i)", "two numbers g3 RG{A2,B3,C2}")),
    ("C-CONT", NR, "static void StartNumbers(", "prevRGHere && prevRG >= 1 && !followedPrev",
     "prevRGHere && prevRG >= 1", "prevRGHere && prevRG >= 1 && !(followedPrev)",
     units("START-8") + walk("W6.9p", None),
     ("walk-D6 W6.9p", "two numbers g3 RG{A2,B3,C2}")),
    ("C-SPEC", NR, "static string SpectatorAdvertTarget(",
     "return string.Equals(pending, join, StringComparison.Ordinal) ? join : null;",
     "return null;",
     "return string.Equals(join, pending, StringComparison.Ordinal) ? join : null;",
     units("SPEC-1") + walk("W5.1", None) + walk("W5.2") + walk("W5.2m", None) + walk("W6.6")
     + walk("W6.6s", None) + walk("W6.7a", None) + walk("W6.15", None) + walk("W7.5", None),
     ("walk-D5 W5.2(i)", "EXPECTED g4 G{A0,B0,C0,D0,S0} expected 1")),
    # V5-V9's rows (V10 section 5). A deleted line is an empty replacement.
    ("C-OPEN", NR, "static int MasterOpenerGame(",
     "if (ownGame >= 1) { cycle = ownCycle + 1; return ownGame; }",
     "", "if (1 <= ownGame) { cycle = ownCycle + 1; return ownGame; }",
     units("OPEN-4") + walk("W6.6s", None),
     ("walk-D6 W6.6s", "AGREE-P g4 P{A3:5,B1:2,C1:2,D1:2}")),
    ("C-PROMOTE", NR, "static bool ReopensOnPromotion(", "return gate && isMaster && phaseGame < 1;",
     "return false;", "return gate && isMaster && phaseGame < 1 && true;",
     units("PROM-1") + walk("W6.10", None) + walk("W6.15", None),
     ("walk-D6 W6.10", "CLOSE-SAFE g4 c1 B master without identity did not reopen")),
    ("C-KEYED", NR, "static bool KeyedReadsAllowed(", "return !gate || game >= 1;",
     "return game >= 1;", "return !gate || 1 <= game;",
     units("KEYED-3") + walk("W7.8", None),
     ("walk-D12 W7.8", "EXPECTED g4 CS none, expected 4 on C")),
    ("C-RESETG", NR, "static int CounterAfterRoomChange(", "return (gate || lastName != name) ? 0 : counter;",
     "return 0;", "return (gate || lastName != name) ? 0 : counter + 0;",
     units("RESETG-2") + walk("W7.8", None),
     ("walk-D12 W7.8", "EXPECTED g5 CS{C1} expected 5")),
    ("C-SAMEGAME", NR, "static bool EpochEvidence(",
     "return sameEpoch && ahead && (!gate || (pickGame == phaseGame && pickCycle == phaseCycle));",
     "return sameEpoch && ahead && (!gate || pickCycle == phaseCycle);",
     "return ahead && sameEpoch && (!gate || (pickGame == phaseGame && pickCycle == phaseCycle));",
     units("EVID-2") + walk("W6.11", None),
     ("walk-D6 W6.11", "SAME-GAME g2 A adopted 2:1 over 1:1")),
    ("C-EPOCH", NR, "static bool SameEpoch(", "return a != null && a == b;",
     "return a != null && b != null;", "return a != null && b == a;",
     units("EP-2", "ENV-2") + walk("W6.3q", None) + walk("W6.12", None),
     ("walk-D6 W6.12", "REPLAY B adopted 4:3 at g4.4 from picks written at g4.3")),
    ("C-OTHERS", NR, "static int EvidenceQuorum(", "int n = OthersOf(owners, local).Count;",
     "int n = owners.Count - 1;", "int n = OthersOf(owners, local).Count + 0;",
     units("QUORUM-5") + walk("W6.13", None),
     ("walk-D6 W6.13", "EXPECTED g4 F none, expected 4")),
    ("C-FINAL", NR, "static bool FinalizesAtTermination(", "return pe != null;",
     "return pe != null && applied > 0;", "return pe != null && (applied > 0 || applied <= 0);",
     units("FIN-2") + walk("W6.14", None),
     ("walk-D6 W6.14", "EPOCH g4.3 C holds the epoch of its terminated g4.2")),
    ("C-LIVEEP", NR, "static string LiveEpoch(", "if (finalized != null && finalized.Contains(e)) return null;",
     "", "if (null != finalized && finalized.Contains(e)) return null;",
     units("LEP-4") + walk("W6.14", None),
     ("walk-D6 W6.14", "EPOCH g4.3 C holds the epoch of its terminated g4.2")),
    ("C-LEGACY", NR, "static string LegacyPickValue(", "return \"\";",
     "return nonce + \":\" + game + \":\" + cycle + \":\" + card;", "return \"\" + \"\";",
     units("LEGACY-1", "LEGACY-2") + walk("W7.4", None) + walk("W7.9", None),
     ("walk-D12 W7.9", "REPLAY Z applied 3:4 at g4.1, written at g3.4")),
    ("C-HOLD", NR, "static string HeldEpoch(", "return live;",
     "return live ?? pe;", "return pe == live ? pe : live;",
     units("HE-2") + walk("W6.8d", None) + walk("W6.15", None) + walk("W7.10", None) + walk("W7.11", None),
     ("walk-D12 W7.10", "EPOCH g4.1 P holds the epoch of departed A")),
    ("C-ISSUER", NR, "static string LiveEpoch(", "if (!issuer.HasValue || issuer.Value != masterActor) return null;",
     "", "if (!issuer.HasValue || masterActor != issuer.Value) return null;",
     units("LEP-2", "LEP-6") + walk("W6.8d", None) + walk("W6.15", None) + walk("W7.11", None),
     ("walk-D6 W6.15", "EPOCH g4.3 C holds the epoch of departed A")),
    ("C-CYCLE", NR, "static bool EpochEvidence(",
     "return sameEpoch && ahead && (!gate || (pickGame == phaseGame && pickCycle == phaseCycle));",
     "return sameEpoch && ahead && (!gate || pickGame == phaseGame);",
     "return sameEpoch && ahead && (!gate || (pickCycle == phaseCycle && pickGame == phaseGame));",
     units("EVID-6") + walk("W6.15", None),
     ("walk-D6 W6.15", "SAME-CYCLE g4 B adopted 1:3 over 1:2")),
    ("C-USE", NR, "static string EpochAtUse(", "return issuer == masterActor ? pe : null;",
     "return pe;", "return masterActor == issuer ? pe : null;",
     units("USE-2", "USE-3") + walk("W7.11", None),
     ("walk-D12 W7.11", "USE g4.1 P published under the epoch of departed A")),
]
assert len(ROWS) == 37, len(ROWS)

# ── mechanics ───────────────────────────────────────────────────────────


def function_span(text, signature):
    """[start, end) of the function whose signature line contains
    `signature`: from the signature to its matching closing brace."""
    if text.count(signature) != 1:
        raise ValueError("signature %r occurs %d times" % (signature, text.count(signature)))
    s = text.index(signature)
    b = text.index("{", s)
    depth = 0
    for i in range(b, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s, i + 1
    raise ValueError("unbalanced braces after %r" % signature)


def apply_edit(path, signature, anchor, replacement):
    with open(path, "r", encoding="utf-8", newline="") as f:
        text = f.read()
    s, e = function_span(text, signature)
    body = text[s:e]
    n = body.count(anchor)
    if n != 1:
        raise ValueError("anchor %r occurs %d times inside %r (must be 1)" % (anchor, n, signature))
    nl = "\r\n" if "\r\n" in text else "\n"
    body = body.replace(anchor, replacement.replace("\n", nl))
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text[:s] + body + text[e:])


def fresh_copy(work):
    for d in ("plugin", os.path.join("tools", "client-rules-harness")):
        os.makedirs(os.path.join(work, d), exist_ok=True)
    for f in PLUGIN_FILES:
        shutil.copyfile(os.path.join(REPO, "plugin", f), os.path.join(work, "plugin", f))
    for f in HARNESS_FILES:
        shutil.copyfile(os.path.join(HERE, f), os.path.join(work, "tools", "client-rules-harness", f))


LINE = re.compile(r"^\[(?P<suite>[a-z]+)\] (?P<verdict>PASS|FAIL) (?P<rest>.*)$")


def parse(out):
    """-> (FAIL set, {case id: FAIL line}, summary line or None, threw)"""
    fails, lines, summary, threw = set(), {}, None, False
    for raw in out.splitlines():
        if raw.startswith("client-rules-harness suites="):
            summary = raw
        if "selftest THREW" in raw or "verdict=THREW" in raw:
            threw = True
        m = LINE.match(raw)
        if not m or m.group("verdict") != "FAIL":
            continue
        suite, rest = m.group("suite"), m.group("rest")
        if suite == "numbering":
            cid = rest.split(" | ", 1)[0].strip()
        elif suite == "ffareport":
            mm = re.search(r"case=(.*?)( \| |$)", rest)
            cid = "ffareport:" + (mm.group(1) if mm else rest)
        else:
            cid = suite + ":" + rest
        fails.add(cid)
        lines[cid] = raw
    return fails, lines, summary, threw


def build_and_run(work, log):
    proj = os.path.join(work, "tools", "client-rules-harness", "client-rules-harness.csproj")
    b = subprocess.run(["dotnet", "build", proj, "-c", "Release", "-t:Rebuild", "-nologo"],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    log.write(b.stdout)
    if b.returncode != 0:
        return b.returncode, None, ""
    dll = os.path.join(work, "tools", "client-rules-harness", "bin", "Release", "net10.0",
                       "client-rules-harness.dll")
    r = subprocess.run(["dotnet", dll], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return b.returncode, r.returncode, r.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default=None)
    ap.add_argument("--only", default=None)
    ap.add_argument("--log", default=None)
    args = ap.parse_args()
    work = args.work or tempfile.mkdtemp(prefix="numbering-controls-")
    os.makedirs(work, exist_ok=True)
    log = open(args.log or os.path.join(work, "numbering_controls.full.log"), "w", encoding="utf-8")
    only = set(args.only.split(",")) if args.only else None

    results = []
    ok_all = True

    def row(rid, kind, edit, expected, named):
        nonlocal ok_all
        fresh_copy(work)
        if edit is not None:
            f, sig, anchor, repl = edit
            apply_edit(os.path.join(work, "plugin", f), sig, anchor, repl)
        log.write("\n===== %s %s =====\n" % (rid, kind))
        bexit, rexit, out = build_and_run(work, log)
        log.write(out)
        if rexit is None:
            results.append((rid, kind, bexit, None, None, None, None, None, "BUILD FAILED"))
            ok_all = False
            return None
        fails, lines, summary, threw = parse(out)
        exp = set(expected)
        missing = sorted(exp - fails)
        extra = sorted(fails - exp)
        named_ok = None
        if named is not None:
            cid, text = named
            pool = [lines[c] for c in fails if c.startswith("walk-")] if cid is None else [lines.get(cid, "")]
            named_ok = any(text in l for l in pool)
        want_rexit = 0 if not exp else 1
        exact = not missing and not extra and not threw and rexit == want_rexit and named_ok is not False
        if not exact:
            ok_all = False
        results.append((rid, kind, bexit, rexit, fails, missing, extra, named_ok,
                        "EXACT" if exact else "DIFFERS"))
        return fails

    base = row("baseline", "none", None, [], None) if (only is None or "baseline" in only) else None
    base_red = set(base or [])
    for (rid, f, sig, anchor, mut, twin, expected, named) in ROWS:
        if only is not None and rid not in only:
            continue
        row(rid, "mutation", (f, sig, anchor, mut), expected, named)
        row(rid, "twin", (f, sig, anchor, twin), [], None)

    print("work=%s" % work)
    print("baseline red (reported once, excluded from the 'modulo baseline' column): %s"
          % (", ".join(sorted(base_red)) or "none"))
    print("%-11s %-8s %-5s %-5s %-6s %-9s %-7s %-30s %s" % (
        "row", "kind", "build", "run", "fails", "named", "strict", "modulo baseline", "detail"))
    for (rid, kind, bexit, rexit, fails, missing, extra, named_ok, verdict) in results:
        if fails is None:
            print("%-11s %-8s %-5s %-5s %-6s %-9s %-7s %-30s %s" % (rid, kind, bexit, "-", "-", "-", verdict, "-", ""))
            continue
        m_mod = [c for c in missing if c not in base_red]
        e_mod = [c for c in extra if c not in base_red]
        mod = "EXACT" if not m_mod and not e_mod and named_ok is not False else "DIFFERS"
        detail = []
        if missing:
            detail.append("missing=" + ";".join(missing))
        if extra:
            detail.append("extra=" + ";".join(extra))
        print("%-11s %-8s %-5s %-5s %-6s %-9s %-7s %-30s %s" % (
            rid, kind, bexit, rexit, len(fails),
            "-" if named_ok is None else ("found" if named_ok else "MISSING"),
            verdict, mod, " ".join(detail)))
    log.close()
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
