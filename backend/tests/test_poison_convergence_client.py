"""Client source checks for poison convergence v3 (bugs 406/407).

The pure decisions -- life epoch, ledger, catch-up, claims, activation -- are
EXECUTED by tools/tests/poison-ledger over plugin/PoisonLedgerCore.cs (one
mutant and one control per case). What is checked here is the wiring a
harness cannot reach: where the capability is staged and read, where the
claim is raised and accepted, what the correction funnel may call, which
predicates are shared with the DoDamage prefixes, where the catch-up is
flushed, and that the two evidence tags are used nowhere else and carry no
account identity.

Each check is a function over the source text. test_checks_hold runs them
on the tree; test_each_check_turns_red runs each on an in-memory copy with
one named mutation (it must fail) and one named control mutation elsewhere
(it must still pass). No file is written.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugin"


def _load():
    return {p.name: p.read_text(encoding="utf-8") for p in PLUGIN.glob("*.cs")}


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
    """The text with // comments removed (string literals kept)."""
    return "\n".join(re.sub(r"//.*$", "", l) for l in text.splitlines())


PS = "PoisonSync.cs"
VF = "VanillaFixes.cs"


# -- the capability and the gate (A2) -------------------------------------------

def check_staged_together(src):
    stage = _member(src[PS], "internal static void StageCapability(")
    head = "local.SetCustomProperties(new ExitGames.Client.Photon.Hashtable"
    assert stage.count(head) == 1, "not one pre-join write"
    body = stage[stage.index(head):]
    body = body[:body.index("});")]
    assert "{ CapabilityProp, CapabilityValue }" in body and "{ CapabilityPropV3, v3 }" in body, \
        "cr_pois2 and cr_pois3 are not staged in one hashtable"
    assert "int v3 = V3PatchesLive ? CapabilityValue : 0;" in stage, "cr_pois3 is not tied to every v3 patch"
    live = _code(src[PS])
    m = re.search(r"internal static bool V3PatchesLive\s*\{\s*get\s*\{\s*return ([^;]*);", live)
    assert m, "no V3PatchesLive"
    for flag in ("PatchesLive", "RpcStampLive", "HitBracketLive", "PoisonArmLive", "PhoenixBoundaryLive",
                 "DeathFlushLive"):
        assert re.search(r"\b%s\b" % flag, m.group(1)), "V3PatchesLive ignores " + flag
        if flag != "PatchesLive":
            assert live.count("PoisonSync.%s = true;" % flag) == 1, flag + " is not set by exactly one cleanup"


def check_gate_reads_raw_cap(src):
    cap = _code(_member(src[PS], "private static bool HasCap3("))
    assert "PhotonNetwork.PlayerList" in cap, "the gate does not read the replicated actor list"
    assert "TryGetValue(CapabilityPropV3, out v)" in cap and "v is int && (int)v == CapabilityValue" in cap, \
        "the gate does not require integer cr_pois3=1"
    on = _code(_member(src[PS], "internal static bool V3On("))
    assert "_act.Evaluate(!PhotonNetwork.CurrentRoom.IsOpen, PresentActors(), HasCap3, NowMs(), out why)" in on, \
        "the gate is not the activation rule over the room's open flag, every present actor and cr_pois3"
    for pre in ("if (!V3PatchesLive)", "if (Plugin.modDisabled)", "if (_epochBroken)"):
        assert pre in on, "the gate lost " + pre


def check_only_witness_closes(src):
    hits = [(n, m.start()) for n, s in src.items() for m in re.finditer(r"\.IsOpen\s*=\s*false", _code(s))]
    ps_hits = [h for h in hits if h[0] == PS]
    assert len(ps_hits) == 1, "PoisonSync writes the room's open flag %d times" % len(ps_hits)
    lever = _member(src[PS], "private static void WitnessLever(")
    assert "room.IsOpen = false;" in lever, "the room is closed outside the witness lever"
    assert 'cf.Bind("Poison", "V3WitnessCloseRoom", false,' in lever, "the witness lever is not default off"
    assert "if (_witnessLever == null || !_witnessLever.Value) return;" in lever


# -- the claim (A5, A6, A8, A9) ---------------------------------------------------

def check_claim_only_from_entered_poison(src):
    ps = _code(src[PS])
    assert ps.count("TypeClaim, Protocol,") == 1, "the claim is raised in more than one place"
    arm = _member(src[PS], "private static int ShooterArm(")
    assert "TypeClaim, Protocol," in arm, "the claim is not raised by ShooterArm"
    assert len(re.findall(r"\bShooterArm\(ph, pv, vv\)", ps)) == 1, "ShooterArm has another caller"
    enter = _code(_member(src[PS], "internal static bool PoisonEffectEnter("))
    assert "armed = ShooterArm(ph, pv, vv);" in enter
    assert "if (f == null || !f.LocalOnly || vv.IsMine) return true;" in enter, \
        "the arm is not limited to a hit this seat ran without broadcasting"
    patch = _member(src[PS], "internal static class PoisonArmPatch")
    assert src[PS].count('[HarmonyPatch(typeof(RayHitPoison), "DoHitEffect")]\n    internal static class PoisonArmPatch') == 1, \
        "the arm is not RayHitPoison.DoHitEffect's own prefix"
    assert "return PoisonSync.PoisonEffectEnter(__instance, hit, out __state);" in patch
    hit = _code(_member(src[PS], "internal static void HitEnter("))
    assert "f.LocalOnly = ph != null && ph.view != null && ph.view.IsMine && !ph.sendCollisions;" in hit, \
        "local-only is not the shooter seat's unbroadcast hit (ProjectileHit.cs:187)"
    assert src[PS].count('[HarmonyPatch(typeof(ProjectileHit), "Hit")]\n    internal static class PoisonHitBracketPatch') == 1


def check_claim_decided_before_start(src):
    on = _code(_member(src[PS], "private static void OnClaim("))
    decide = on.index("string result = _claims.VictimDecide(f);")
    gate = on.index("if (result != \"started\")")
    depth = on.index("_claimStartDepth++;")
    start = on.index("c.DoHitEffect(hit);")
    assert decide < gate < depth < start, "a claim can start poison before the victim's decision"
    assert on.count("DoHitEffect(") == 1
    enter = _code(_member(src[PS], "internal static bool PoisonEffectEnter("))
    assert "if (vv.IsMine && pv != null && !pv.IsMine && _claimStartDepth == 0)" in enter
    assert "if (_claims.TryStart(ph.GetInstanceID(), vv.ViewID, StartPath.Broadcast)) return true;" in enter, \
        "the broadcast path does not share the claim's TryStart"


def check_every_arm_one_terminal_line(src):
    arm = _code(_member(src[PS], "private static int ShooterArm("))
    assert arm.count("Plugin.Log.LogInfo(") == 2, "an arm has other than one line per outcome"
    assert 'if (drop != null) { Plugin.Log.LogInfo(head + "drop reason=" + drop); return claimId; }' in arm
    assert 'Plugin.Log.LogInfo(head + (sent ? "sent" : "send-failed"));' in arm
    for field in ('"[POISON-CLAIM] arm from=" + LocalActor()', '" c=" + claimId', '" proj=" + projView',
                  '" victim=" + vv.ViewID'):
        assert field in arm, "the arm line lacks " + field
    on = _code(_member(src[PS], "private static void OnClaim("))
    assert 'ClaimDropLine(head + "drop reason=" + result); return;' in on
    assert 'Plugin.Log.LogInfo(head + "started streams="' in on


# -- the funnel and the shared predicates (A3) ------------------------------------

FUNNEL_FORBIDDEN = (".DoDamage(", "CallTakeDamage(", "TakeDamageOverTime(", ".RPC(", "RaiseEvent(", "RaiseTo(",
                    ".Heal(", "Revive(", "RPCA_", "StopAllCoroutines(", "Instantiate(", "health +=",
                    "DealtDamage", "WasDealtDamage")


def check_funnel_is_closed(src):
    f = _code(_member(src[PS], "private static void ApplyCorrective("))
    for bad in FUNNEL_FORBIDDEN:
        assert bad not in f, "the correction funnel calls " + bad
    assert "if (DamageRulesGate.Refuses(hh, FindPlayer(rec.AttackerId))) return;" in f, \
        "the funnel does not consume what DoDamage's own rule refuses"
    assert "float floor = pre < 1f ? pre : 1f;" in f and "cd.health = nh < floor ? floor : nh;" in f, \
        "the funnel can lower health past min(health, 1)"
    assert len(re.findall(r"cd\.health\s*=", f)) == 1
    ap = _code(_member(src[PS], "private sealed class LedgerApplier"))
    assert "ApplyCorrective(view, rec);" in ap and "ApplyCommitted(view, rec, r.View, r.Stream, tick, true);" in ap


def check_shared_predicates(src):
    vf = _code(src[VF])
    refuses = _member(vf, "internal static bool Refuses(")
    assert "return !BeforeDoDamage(victim, damagingPlayer);" in refuses, "Refuses is not the DoDamage prefix"
    esk = _member(vf, "private static bool BeforeTransitionDamage(")
    assert "if (!RefusesNow()) return true;" in esk, "EndScreenKill's prefix does not use RefusesNow"
    live = _code(_member(src[PS], "private static bool LiveReplica("))
    assert "EndScreenKillPatch.RefusesNow()" in live, "the live-replica test is not EndScreenKill's own condition"
    assert "if (!cd.isPlaying || cd.dead || hh.isRespawning) return false;" in live


# -- the epoch and the catch-up (A1, A4) -------------------------------------------

def check_epoch_wire(src):
    dot = _code(_member(src[PS], "internal static IEnumerator AuthoritativeDot("))
    assert "attackerId, lethal, (byte)damageSource, blocked, _nextSeq++,\n                        epoch.Ts, epoch.Set" in dot, \
        "the v3 header is not today's 15 elements followed by the epoch"
    assert "bool v3 = V3On(out v3Why);" in dot and "if (v3 && !_ledger.FenceOf(viewId, out epoch)) v3 = false;" in dot
    assert "if (!_ledger.AdmitV3Stream(now, now + span)) v3 = false;" in dot
    assert dot.count("CloseV3(openKey);") == 3, "a stream exit sends no catch-up"
    ev = _code(_member(src[PS], "private static void OnEvent("))
    assert "if (!_epochBroken && PoisonLedgerCore.TryV3Epoch(a.Length," in ev
    assert "else if (kind == TypeSummary) { if (a.Length < 18) return; }" in ev
    # the stamp: PUN's own RPC send stamp, read in ExecuteRpc for the view the RPC targets
    stamp = _member(src[PS], "internal static class PoisonRpcStampPatch")
    assert "__0.TryGetValue((byte)0, out v) && v is int" in stamp and "__0.TryGetValue((byte)2, out t) && t is int" in stamp
    assert "return _cur.Has && _cur.View == viewId;" in stamp


def check_flush_on_every_stop(src):
    ps = _code(src[PS])
    revive = _member(ps, "private static void AfterRevive(")
    phoenix = _member(ps, "internal static class PoisonPhoenixBoundaryPatch")
    death = _member(ps, "internal static class PoisonDeathFlushPatch")
    for name, body in (("Revive", revive), ("RPCA_Die_Phoenix", phoenix), ("RPCA_Die", death)):
        assert "PoisonSync.FlushOpenV3(v.ViewID);" in body, name + " stops the streams without their catch-up"
    assert src[PS].count('[HarmonyPatch(typeof(HealthHandler), "RPCA_Die")]\n    internal static class PoisonDeathFlushPatch') == 1
    assert revive.index("PoisonSync.FlushOpenV3(v.ViewID);") < revive.index("PoisonSync.OnLocalRevive(v.ViewID);")


# -- evidence (A8) -------------------------------------------------------------------

def check_evidence_tags(src):
    for tag in ("[POISON-LEDGER]", "[POISON-CLAIM]"):
        users = sorted(n for n, s in src.items() if tag in s)
        assert users == [PS], "%s is used outside PoisonSync.cs: %s" % (tag, users)
    # the v3 shell: from its first declaration to the tick-sound section after it
    ps = _code(src[PS])
    v3 = ps[ps.index("private const byte TypeClaim = 2;"):ps.index("private static System.Reflection.MethodInfo _playMi;")]
    for ident in ("NickName", "UserId", "SteamId", "steamId", "SteamID", "GetSteamID", "DisplayName"):
        assert ident not in v3, "the v3 shell reads an account identity: " + ident
    v3line = _code(_member(src[PS], "private static void V3Line("))
    assert "if (_v3LogLines >= V3LineCap) return;" in v3line, "the state lines are unbounded"
    drop = _code(_member(src[PS], "private static void ClaimDropLine("))
    assert "if (_claimDropLines < ClaimDropLineCap)" in drop, "the victim's drop lines are unbounded"


CHECKS = {f.__name__: f for f in (
    check_staged_together, check_gate_reads_raw_cap, check_only_witness_closes,
    check_claim_only_from_entered_poison, check_claim_decided_before_start, check_every_arm_one_terminal_line,
    check_funnel_is_closed, check_shared_predicates, check_epoch_wire, check_flush_on_every_stop,
    check_evidence_tags,
)}

# (check, file, old, new): one named mutation per check that must turn it red.
MUTANTS = {
    "check_staged_together": (PS, "                    { CapabilityPropV3, v3 }\n", ""),
    "check_gate_reads_raw_cap": (PS, "v is int && (int)v == CapabilityValue", "v != null"),
    "check_only_witness_closes": (PS, "V3WitnessCloseRoom\", false,", "V3WitnessCloseRoom\", true,"),
    "check_claim_only_from_entered_poison": (PS, "if (f == null || !f.LocalOnly || vv.IsMine) return true;",
                                             "if (f == null || vv.IsMine) return true;"),
    "check_claim_decided_before_start": (PS, "if (_claims.TryStart(ph.GetInstanceID(), vv.ViewID, StartPath.Broadcast)) return true;",
                                         "return true;"),
    "check_every_arm_one_terminal_line": (PS, 'Plugin.Log.LogInfo(head + (sent ? "sent" : "send-failed"));', ""),
    "check_funnel_is_closed": (PS, "            if (DamageRulesGate.Refuses(hh, FindPlayer(rec.AttackerId))) return;\n",
                               "            hh.DoDamage(Vector2.zero, Vector2.zero, Color.white);\n"),
    "check_shared_predicates": (PS, "if (!RoomActors.LocalIsSpectator && EndScreenKillPatch.RefusesNow()) return false;",
                                "if (!RoomActors.LocalIsSpectator && !GameManager.instance.battleOngoing) return false;"),
    "check_epoch_wire": (PS, "if (data.dead || !data.isPlaying) { CloseV3(openKey); yield break; }",
                         "if (data.dead || !data.isPlaying) { yield break; }"),
    "check_flush_on_every_stop": (PS, "                if (v != null) PoisonSync.FlushOpenV3(v.ViewID);\n            }\n            catch { }",
                                  "            }\n            catch { }"),
    "check_evidence_tags": (PS, 'string head = "[POISON-CLAIM] recv from=" + sender',
                            'string head = "[POISON-CLAIM] recv from=" + PhotonNetwork.LocalPlayer.NickName'),
}

# One control mutation, far from every check's anchors: every check stays green.
CONTROL = (PS, "// ── Tick sound ──", "// ── Tick sound (control) ──")


def _mutate(src, spec):
    name, old, new = spec
    assert src[name].count(old) == 1, "mutation anchor occurs %d times: %r" % (src[name].count(old), old[:60])
    out = dict(src)
    out[name] = src[name].replace(old, new)
    return out


def _normal(src):
    return {k: v.replace("\r\n", "\n") for k, v in src.items()}


@pytest.mark.parametrize("name", sorted(CHECKS))
def test_checks_hold(name):
    CHECKS[name](_normal(_load()))


@pytest.mark.parametrize("name", sorted(CHECKS))
def test_each_check_turns_red(name):
    src = _normal(_load())
    assert set(MUTANTS) == set(CHECKS), "a check has no mutant"
    mutant = _mutate(src, MUTANTS[name])
    control = _mutate(src, CONTROL)
    with pytest.raises(AssertionError):
        CHECKS[name](mutant)
    CHECKS[name](control)
