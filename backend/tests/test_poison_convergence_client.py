"""Client source checks for poison convergence v3 (bugs 406/407).

The pure decisions -- life epoch, ledger, catch-up, claims, activation -- are
EXECUTED by tools/tests/poison-ledger over plugin/PoisonLedgerCore.cs (one
mutant and one control per case). What is checked here is the wiring a
harness cannot reach: where the capability is staged and read, where the
claim is raised and accepted, what the correction funnel may call, which
predicates are shared with the DoDamage prefixes, where the catch-up is
flushed, that every v3-only message is addressed to named actors (A2b: an
actor not yet seen to join is never an addressee), that rooms are never
closed, that every join, leave and cr_pois3 change reaches the gate, that the
two evidence tags are used nowhere else and carry no account identity, that
activation, acceptance and replay are bound to the point epoch (V4 B1/B3),
that an unstamped boundary breaks the held records (V4 B4), and that every
hook the lane adds or changes contains its own faults (V4 B7).

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
PL = "Plugin.cs"
CORE = "PoisonLedgerCore.cs"


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
    assert "return _act.Evaluate(Fighters(), HasCap3, NowMs(), _ledger.PointEpoch, out why);" in on, \
        "the gate is not the activation rule over the fighters and cr_pois3"
    fighters = _code(_member(src[PS], "private static int[] Fighters("))
    assert "RoomActors.ActiveFighters()" in fighters, "the activation roster is not the scored fighters"
    stage = _member(src[PS], "internal static void StageCapability(")
    assert '"); v3 can activate in an open room: "' in stage, "the boot line does not say whether v3 can activate"
    for pre in ("if (!V3PatchesLive)", "if (Plugin.modDisabled)", "if (_epochBroken)"):
        assert pre in on, "the gate lost " + pre


def check_rooms_stay_open(src):
    ps = _code(src[PS])
    assert not re.search(r"\.IsOpen\s*=", ps), "PoisonSync writes the room's open flag"
    assert "V3WitnessCloseRoom" not in src[PS], "the room-closing witness lever is back"
    on = _code(_member(src[PS], "internal static bool V3On("))
    assert "IsOpen" not in on, "the gate reads the room's open flag"


V3_KINDS = ("TypeClaim", "TypeSummary", "TypeActivate", "TypeAck", "TypeLife")
V3_BUILDERS = ("V3Wire.Claim(", "V3Wire.Summary(", "V3Wire.Activate(", "V3Wire.Ack(", "V3Wire.Life(")


def check_targeted_sends(src):
    ps = _code(src[PS])
    raise_to = _member(ps, "private static bool RaiseTo(")
    assert "object[] payload, int[] targets)" in raise_to, "RaiseTo is not addressed"
    assert "if (targets == null || targets.Length == 0) return false;" in raise_to
    assert "new RaiseEventOptions { TargetActors = targets };" in raise_to, "RaiseTo is not addressed to named actors"
    assert "ReceiverGroup" not in raise_to and "Receivers" not in raise_to, "RaiseTo can reach a receiver group"
    for kind in V3_KINDS:
        assert not re.search(r"\{\s*%s, Protocol," % kind, ps), kind + " is built outside V3Wire"
        assert "private const byte %s = V3Wire.%s;" % (kind, kind) in ps, kind + " is not V3Wire's"
    for builder in V3_BUILDERS:
        uses = [m.start() for m in re.finditer(re.escape(builder), ps)]
        assert len(uses) == 1, "%s is used %d times" % (builder, len(uses))
        assert ps[uses[0] - 8:uses[0]] == "RaiseTo(", builder + " is not sent through RaiseTo"
    assert "RaiseTo(V3Wire.Activate(aid, fighters, point), to);" in ps
    assert "int[] to = V3Targets.Capable(PresentActors(), HasCap3);" in ps
    assert "RaiseTo(V3Wire.Ack(aid, sender), V3Targets.Capable(PresentActors(), HasCap3));" in \
        _member(ps, "private static void OnActivate(")
    assert "int[] lifeTargets = v3 ? _act.AckedPresent(presentAtStart) : null;" in ps
    assert "RaiseTo(V3Wire.Life(viewId, stream, epoch), lifeTargets)" in ps
    send = _member(ps, "private static bool SendSummary(")
    assert "if (d == null || to == null || to.Length == 0) return false;" in send
    assert len(re.findall(r"\bSendSummary\(k, ", ps)) == 2, "a summary goes somewhere other than the close or a replay"
    assert "int[] to = PointRetainer.CloseTargets(k, PresentActors(), LocalActor());" in _member(ps, "private static void CloseV3(")
    assert "SendSummary(k, new[] { actor })" in _member(ps, "private static void ReplayTo(")
    arm = _member(ps, "private static int ShooterArm(")
    assert "bool ownerAcked = owner > 0 && _act.IsAcked(owner);" in arm
    assert "(byte)Math.Min(nPoison, 255), ep), new[] { owner });" in arm
    assert "c.SenderAcked = _act.IsAcked(sender);" in _member(ps, "private static void OnClaim(")


def check_room_events_reach_the_gate(src):
    pl = _code(src[PL])
    for sig, call in (("public void OnPlayerEnteredRoom(", 'PoisonSync.V3RoomEvent("player-entered", p);'),
                      ("public void OnPlayerLeftRoom(", 'PoisonSync.V3RoomEvent("player-left", p);'),
                      ("public void OnPlayerPropertiesUpdate(", "PoisonSync.V3PropsChanged(target, changedProps);")):
        body = _member(pl, sig)
        assert call in body, sig + " does not reach the v3 gate"
        first_return = body.find("return")
        assert first_return < 0 or body.index(call) < first_return, sig + " can return before the v3 hook"
    props = _code(_member(src[PS], "internal static void V3PropsChanged("))
    assert "changed.ContainsKey(CapabilityPropV3)" in props
    ev = _code(_member(src[PS], "internal static void V3RoomEvent("))
    assert "_act.OnRoomEvent(why);" in ev


# -- the claim (A5, A6, A8, A9) ---------------------------------------------------

def check_claim_only_from_entered_poison(src):
    ps = _code(src[PS])
    assert ps.count("V3Wire.Claim(") == 1, "the claim is raised in more than one place"
    arm = _member(src[PS], "private static int ShooterArm(")
    assert "V3Wire.Claim(" in arm, "the claim is not raised by ShooterArm"
    assert len(re.findall(r"\bShooterArm\(ph, pv, vv\)", ps)) == 1, "ShooterArm has another caller"
    effect = _code(_member(src[PS], "private static void ArmEffect("))
    assert "armed = ShooterArm(ph, pv, vv);" in effect
    assert len(re.findall(r"\bArmEffect\(", ps)) == 2, "ArmEffect has a caller other than the poison prefix"
    assert "ArmEffect(ph, pv, vv, hit);" in _code(_member(src[PS], "internal static bool PoisonEffectEnter("))
    assert "if (f == null || !f.LocalOnly || vv.IsMine) return;" in effect, \
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
    ps = _code(src[PS])
    on = _code(_member(src[PS], "private static void OnClaim("))
    assert "}, claimId => StartClaim(claimId, vv, poisons));" in on, "a started claim is not started by StartClaim"
    rcv = _code(_member(src[CORE], "internal void Receive("))
    decide = rcv.index("string result = Handle(sender, claimId, nowMs, () =>")
    gate = rcv.index('outcome = result == "started" ? start(claimId) : RecvOutcome(sender, result);')
    assert decide < gate, "a claim can start poison before the victim's decision"
    assert rcv.count("start(") == 1, "a claim can start other than on Handle's \"started\""
    assert "DoHitEffect(" not in on
    assert len(re.findall(r"\bStartClaim\(", ps)) == 2, "StartClaim has another caller"
    start = _code(_member(src[PS], "private static string StartClaim("))
    assert start.index("_claimStartDepth++;") < start.index("c.DoHitEffect(hit);")
    assert start.count("DoHitEffect(") == 1
    enter = _code(_member(src[PS], "internal static bool PoisonEffectEnter("))
    assert "if (vv.IsMine && pv != null && !pv.IsMine && _claimStartDepth == 0)" in enter
    assert "return _claims.TryStart(ph.GetInstanceID(), vv.ViewID, StartPath.Broadcast);" in enter, \
        "the broadcast path does not share the claim's TryStart"
    assert "return HookGuard.Prefix(" in enter and "ex => PrefixFaultDecision(ex)," in enter, \
        "the start decision is not the guarded prefix's own"


def check_every_arm_one_terminal_line(src):
    ps = _code(src[PS])
    arm = _code(_member(src[PS], "private static int ShooterArm("))
    assert arm.count("Plugin.Log.LogInfo(") == 1, "an arm has other than one line"
    assert "try { Plugin.Log.LogInfo(ClaimLine.Arm(LocalActor(), claimId, projView, victimView, outcome)); } catch { }" in arm
    assert arm.count("return") == 1 and arm.rstrip("} \n").endswith("return claimId;"), "an arm can leave before its line"
    assert "catch (Exception ex)" in arm and 'outcome = ClaimLine.Outcome(fault);' in arm, "a faulting arm has no line"
    # fix pass 2 (M1, M2): the received claim's line is ClaimCore.Receive's, written by DrainClaimLines
    on = _code(_member(src[PS], "private static void OnClaim("))
    assert "_claims.Receive(sender, a, NowMs(), c =>" in on and "DrainClaimLines();" in on
    assert "return" not in on and "Plugin.Log" not in on, "OnClaim can leave before, or write beside, its line"
    assert on.index("_claims.Receive(") < on.index("DrainClaimLines();")
    drain = _code(_member(src[PS], "private static void DrainClaimLines("))
    assert "foreach (string line in _claims.Lines) Plugin.Log.LogInfo(line);" in drain
    rcv = _code(_member(src[CORE], "internal void Receive("))
    assert rcv.count("Lines.Add(") == 1, "an admitted claim has other than one line"
    assert rcv.rstrip("} \n").endswith("Lines.Add(ClaimLine.Recv(sender, claimId, proj, victim, outcome));"), \
        "the line is not Receive's last step"
    assert rcv.replace("return c;", "").count("return") == 1, "a claim can leave Receive before its line"
    assert rcv.lstrip().split("{", 1)[1].lstrip().startswith(
        "if (!AdmitRate(sender, nowMs)) { Refuse(sender, nowMs, a); return; }"), "work precedes the rate admission"
    assert 'outcome = ClaimLine.Outcome("malformed");' in rcv, "a malformed claim has no line"
    assert 'catch (Exception ex) { outcome = ClaimLine.Outcome("fault:" + ex.GetType().Name); }' in rcv
    for gone in ("ClaimDropLine", "_claimDropLines", "_claimDropSuppressed", "ClaimDropLineCap"):
        assert gone not in ps, "a per-line cap can drop a claim's tuple: " + gone


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
    assert "() => !healthRemoval || !RefusesNow()," in esk, "EndScreenKill's prefix does not use RefusesNow"
    live = _code(_member(src[PS], "private static bool LiveReplica("))
    assert "EndScreenKillPatch.RefusesNow()" in live, "the live-replica test is not EndScreenKill's own condition"
    assert "if (!cd.isPlaying || cd.dead || hh.isRespawning) return false;" in live


# -- the epoch and the catch-up (A1, A4) -------------------------------------------

def check_epoch_wire(src):
    dot = _code(_member(src[PS], "internal static IEnumerator AuthoritativeDot("))
    headers = re.findall(r"TypeHeader, Protocol,(.*?)\}\);", dot, re.S)
    assert len(headers) == 1, "more than one header form"
    assert headers[0].rstrip().endswith("attackerId, lethal, (byte)damageSource, blocked, _nextSeq++"), \
        "the header is not today's 15 elements"
    assert dot.index("V3Wire.Life(") < dot.index("TypeHeader, Protocol,"), "LIFE is not raised before the header"
    assert "bool v3 = V3On(out v3Why);" in dot and "if (v3 && !_ledger.FenceOf(viewId, out epoch)) v3 = false;" in dot
    assert "if (v3 && !_ledger.InPoint(epoch)) v3 = false;" in dot, "the victim stamps a life outside its point"
    assert "if (!_ledger.AdmitV3Stream(now, now + span)) v3 = false;" in dot
    assert dot.count("CloseV3(openKey);") == 3, "a stream exit sends no catch-up"
    ev = _code(_member(src[PS], "private static void OnEvent("))
    assert "if (_inbox.Take(viewId, streamId, out epoch) && AcceptNewV3(epoch))" in ev
    assert "if (kind == TypeLife) { OnLife(e.Sender, a); return; }" in ev
    life = _code(_member(src[PS], "private static void OnLife("))
    assert "view.Owner.ActorNumber != sender) return;" in life, "a LIFE message is taken from someone other than the owner"
    summ = _code(_member(src[PS], "private static void OnSummaryV3("))
    assert "if (_streams.ContainsKey(StreamKey(viewId, streamId))) return;" in summ, \
        "a stream handled by today's path can be caught up on top"
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
    assert "HookGuard.Run(() => PoisonSync.FlushOpenV3(id));" in revive, "Revive stops the streams without their catch-up"
    for name, body in (("RPCA_Die_Phoenix", phoenix), ("RPCA_Die", death)):
        assert "if (v != null) PoisonSync.FlushOpenV3(v.ViewID);" in body, name + " stops the streams without their catch-up"
    assert src[PS].count('[HarmonyPatch(typeof(HealthHandler), "RPCA_Die")]\n    internal static class PoisonDeathFlushPatch') == 1
    assert revive.index("PoisonSync.FlushOpenV3(id)") < revive.index("PoisonSync.OnLocalRevive(id)")


# -- evidence (A8) -------------------------------------------------------------------

def check_evidence_tags(src):
    for tag in ("[POISON-LEDGER]", "[POISON-CLAIM]"):
        users = sorted(n for n, s in src.items() if tag in s)
        assert set(users) <= {PS, CORE}, "%s is used outside the poison files: %s" % (tag, users)
    # the v3 shell: from its first declaration to the tick-sound section after it
    ps = _code(src[PS])
    v3 = ps[ps.index("private const byte TypeClaim = V3Wire.TypeClaim;"):ps.index("private static System.Reflection.MethodInfo _playMi;")]
    for body in (v3, _code(src[CORE])):
        for ident in ("NickName", "UserId", "SteamId", "steamId", "SteamID", "GetSteamID", "DisplayName"):
            assert ident not in body, "the v3 code reads an account identity: " + ident
    v3line = _code(_member(src[PS], "private static void V3Line("))
    assert "if (_v3LogLines >= V3LineCap) return;" in v3line, "the state lines are unbounded"


# -- V4: the point epoch, the replay, the unstamped boundary, the SILENT arm --------

def check_point_binding(src):
    ps = _code(src[PS])
    acc = _code(_member(src[PS], "private static bool AcceptNewV3("))
    assert "if (_epochBroken) return false;" in acc
    assert "return _act.AcceptsAt(point) && _ledger.InPoint(life);" in acc, "a record is accepted outside the acknowledged point"
    assert ps.count("AcceptNewV3(") == 3, "AcceptNewV3 is not the one rule for both new-record paths"
    summ = _code(_member(src[PS], "private static void OnSummaryV3("))
    assert "&& (TodayPathHeld(viewId, streamId) || !AcceptNewV3(epoch))) return;" in summ
    act = _code(_member(src[PS], "private static void OnActivate("))
    assert "if (a.Length < 6 ||" in act and "(bool)a[5] ? LifeEpoch.At((int)a[4]) : default(LifeEpoch);" in act
    assert act.index("_ledger.AdoptPoint(point.Ts);") < act.index("_act.ShouldAck(Fighters(), HasCap3, _ledger.PointEpoch)")
    assert "if (sent) _act.NoteSelfAck();" in act, "acceptance is not tied to this seat's own ack"
    up = _code(_member(src[PS], "private static void V3Upkeep("))
    assert "LifeEpoch point = _ledger.PointEpoch;" in up
    nb = _code(_member(src[PS], "internal static void NotePointBoundary("))
    assert "if (PhotonNetwork.IsMasterClient) _v3RetakeDue = true;" in nb


def check_replay_wiring(src):
    ack = _code(_member(src[PS], "private static void OnAck("))
    assert "if (_act.OnAck(sender, (int)a[3], (int)a[2])) ReplayTo(sender);" in ack, "a late acknowledger gets no replay"
    rp = _code(_member(src[PS], "private static void ReplayTo("))
    assert "if (_epochBroken || actor == self) return;" in rp
    assert "if (!_act.BoundTo(point)) return;" in rp, "a replay goes out under an activation of another point"
    assert "else { PointRetainer.Unmark(k, actor); failed++; }" in rp, "a failed replay leaves the actor marked"
    dot = _code(_member(src[PS], "internal static IEnumerator AuthoritativeDot("))
    assert "ov = _retainer.Begin(viewId, stream, _ledger.PointEpoch, epoch, lifeTargets, presentAtStart," in dot
    assert "if (ov == null) v3 = false;" in dot and "var send = new StreamSend(viewId, ov);" in dot
    assert "if (!send.AfterLife(_retainer, lifeSent))" in dot, "a stream whose LIFE failed stays retained"
    assert "send.AfterTick(tick, blocked, sent);" in dot, "the retained state names ticks that did not go out"
    hdr = _code(_member(src[PS], "private static void OnEvent("))
    assert hdr.index("NoteTodayPath(viewId, streamId);") < hdr.index("int reviveTs;"), "today's header is not recorded"
    rev = _code(_member(src[PS], "internal static void OnLocalRevive("))
    assert "try { ForgetTodayPath(viewId); } catch { }" in rev


def check_unstamped_break(src):
    eb = _code(_member(src[PS], "private static void EpochBroken("))
    assert "try { _ledger.Break(view); _inbox.Clear(); DrainRetired(); } catch { }" in eb
    assert eb.index("_ledger.Break(view);") < eb.index("if (_epochBroken) return;"), \
        "a later unstamped boundary does not break its view's held records"
    ps = _code(src[PS])
    assert 'EpochBroken("point-over without its RPC stamp", -1);' in ps
    assert 'EpochBroken("Phoenix without its RPC stamp", v != null ? v.ViewID : -1);' in ps
    # the declaration and the seven fence-failure sites check_fence_failure_retires names
    assert len(re.findall(r"\bEpochBroken\(", ps)) == 8


# -- fix pass 2 -----------------------------------------------------------------------

def check_header_failure_retires(src):
    """H1 and the send sweep: a stream whose header was not sent, or whose
    seat retired it, sends nothing more -- no tick, no summary, no replay."""
    dot = _code(_member(src[PS], "internal static IEnumerator AuthoritativeDot("))
    assert "if (!send.AfterHeader(_retainer, sent)) _openV3.Remove(openKey);" in dot, "a failed header is not retired"
    assert dot.index("if (!send.MaySendTick)") < dot.index("damageDealt += dpt;") < dot.index("sent = Raise("), \
        "a retired stream can raise another tick"
    stop = dot[dot.index("if (!send.MaySendTick)"):dot.index("damageDealt += dpt;")]
    assert "yield break;" in stop and "CloseV3(" not in stop, "a retired stream is closed with a summary"
    close = _code(_member(src[PS], "private static void CloseV3("))
    assert "if (k == null || s.Retired) return;" in close, "a retired stream gets a summary"
    eb = _code(_member(src[PS], "private static void EpochBroken("))
    assert eb.index('RetireOpenV3(view, "epoch-broken");') < eb.index("if (_epochBroken) return;"), \
        "an unrecorded fence leaves this seat's own open streams sending"
    reset = _code(_member(src[PS], "private static void ResetForRoomExit("))
    assert reset.index('RetireOpenV3(-1, "room-exit");') < reset.index("_openV3.Clear();")


FENCE_FINALIZERS = (
    ("PointEndEvidencePatch", "private static Exception Threw(Exception __exception)",
     'if (__exception != null) PoisonSync.FenceNotRecorded("point-over threw");'),
    ("PoisonReviveFencePatch", "private static Exception Threw(HealthHandler __instance, Exception __exception)",
     'if (__exception != null) PoisonSync.FenceNotRecorded("revive threw", __instance);'),
    ("PoisonPhoenixBoundaryPatch", "private static Exception Threw(HealthHandler __instance, Exception __exception)",
     'if (__exception != null) PoisonSync.FenceNotRecorded("Phoenix threw", __instance);'),
)


def check_fence_failure_retires(src):
    """H2: a fence this seat could not record -- no stamp, a fault while
    recording it, a view lookup fault, or the fenced method throwing --
    retires every possibly ended v3 state before next-life health moves."""
    ps = _code(src[PS])
    nb = _code(_member(src[PS], "internal static void NotePointBoundary("))
    assert "recorded = _ledger.Fence(-1, () =>" in nb
    assert 'if (!stamped) EpochBroken("point-over without its RPC stamp", -1);' in nb
    assert 'else EpochBroken("point-over fence not recorded: fault", -1);' in nb
    ph = _code(_member(src[PS], "internal static void NotePhoenixBoundary("))
    assert "recorded = _ledger.Fence(vid, () =>" in ph
    assert 'if (!looked) EpochBroken("Phoenix fence not recorded: view lookup fault", -1);' in ph
    rev = _code(_member(src[PS], "internal static void OnLocalRevive("))
    assert "recorded = _ledger.Fence(viewId, () => { _ledger.OnRevive(viewId); return true; });" in rev
    assert 'if (!recorded) EpochBroken("revive fence not recorded: fault", viewId);' in rev
    assert rev.index("_ledger.Fence(") < rev.index("EpochBroken(") < rev.index("ForgetTodayPath(")
    for sig in ("internal static void FenceNotRecorded(string why, HealthHandler hh)",
                "internal static void FenceNotRecorded(string why)"):
        assert "EpochBroken(why, " in _code(_member(src[PS], sig))
    after = _code(_member(src[PS], "private static void AfterRevive("))
    assert 'if (id == -2) PoisonSync.FenceNotRecorded("revive fence not recorded: view lookup fault");' in after
    assert after.index("int id = -2;") < after.index("id == -2") < after.index("if (id < 0) return;")
    for cls, sig, line in FENCE_FINALIZERS:
        body = _member(_member(ps, "internal static class " + cls), sig)
        assert "[HarmonyFinalizer]" in _member(ps, "internal static class " + cls), cls + " has no finalizer"
        assert line in body, cls + ": a throwing method leaves its fence unrecorded and nothing retired"
        assert "return __exception;" in body


# V3PatchesLive must name exactly the patches v3 depends on, derived from the
# code: every Harmony patch class whose body calls PoisonSync, or whose member
# PoisonSync calls. A class here is a candidate whose absence changes nothing
# v3 applies, with the reason.
V3_EXEMPT = {
    "PoisonGhostPatch": "returns before acting for every capable victim (PoisonSync.CapableVictim), "
                        "and v3 streams exist only for capable victims",
    "StaleProjectileSweepPatch": "NoteRoundBoundary feeds ShadowDot's silence-report window only; no health",
    "EndScreenKillPatch": "v3 reads RefusesNow() as a state predicate (LiveReplica keeps a fighter's regular "
                          "tick out of the refusal window); its prefix's attachment does not change that read",
}


CLASS_DECL = re.compile(r"^( *)(?:(?:internal|public|private)\s+)?(?:(?:static|sealed|partial)\s+)*class\s+(\w+)\b", re.M)


def _classes(text):
    """{name: (attributes above it, body)} for every class declared in the
    text; a class ends at the first line holding only its own indentation
    and a closing brace (the plugin's layout)."""
    out = {}
    for m in CLASS_DECL.finditer(text):
        ind = m.group(1)
        end = text.find("\n" + ind + "}", m.end())
        assert end > 0, "no end for class " + m.group(2)
        prev = text.rfind("\n" + ind + "}", 0, m.start())
        out[m.group(2)] = (text[max(prev, 0):m.start()], text[m.start():end + len(ind) + 2])
    return out


def _v3_dependencies(src):
    """The Harmony patch classes v3 depends on, from the code: every patch
    class whose body calls PoisonSync, or whose member PoisonSync calls."""
    ps_body = _classes(_code(src[PS]))["PoisonSync"][1]
    deps = {}
    for f in sorted(src):
        text = _code(src[f])
        if "class " not in text:
            continue
        for name, (head, body) in _classes(text).items():
            if name == "PoisonSync" or "[HarmonyPatch" not in head + body:
                continue
            if "PoisonSync." in body or re.search(r"\b%s\.\w+" % re.escape(name), ps_body):
                deps[name] = body
    return deps


def _v3_term(name, body):
    cleanup = body[body.index("[HarmonyCleanup]"):] if "[HarmonyCleanup]" in body else ""
    m = re.findall(r"PoisonSync\.(\w+) = true;", cleanup)
    if m:
        assert re.search(r"if \(exception == null\)\s*\{?\s*PoisonSync\.%s = true;" % m[0], cleanup), \
            name + " records its flag on a failed attachment"
        assert len(m) == 1, name + " sets more than one v3 flag"
        return m[0]
    m = re.findall(r'return VanillaFixSupport\.Cleanup\("(\w+)", exception\);', body)
    assert len(m) == 1, name + " is a v3 dependency whose attachment nothing records"
    return 'VanillaFixSupport.IsAttached("%s")' % m[0]


def check_v3_live_names_every_dependency(src):
    deps = _v3_dependencies(src)
    for name in V3_EXEMPT:
        assert name in deps, "a stale exemption: " + name
    want = {_v3_term(n, b): n for n, b in deps.items() if n not in V3_EXEMPT}
    live = _code(_member(src[PS], "internal static bool V3PatchesLive"))
    terms = [t.strip() for t in live[live.index("return ") + 7:live.index(";")].split("&&")]
    assert sorted(terms) == sorted(want), "V3PatchesLive names %s; v3 depends on %s" % (sorted(terms), sorted(want))
    ps = _code(src[PS])
    missing = _code(_member(src[PS], "private static string V3PatchesMissing("))
    for t in terms:
        if not t.startswith("VanillaFixSupport."):
            assert ps.count("PoisonSync.%s = true;" % t) == 1, t + " is not set by exactly one cleanup"
        assert "if (!%s) m.Add(" % t in missing, "the boot line does not name a missing " + t
    stage = _member(src[PS], "internal static void StageCapability(")
    assert '"; v3 patches missing: " + V3PatchesMissing()' in stage, "a failed v3 attachment is not seen"


def check_claim_dispatch_terminal(src):
    """M1: every current-protocol claim the dispatcher receives reaches
    OnClaim, a truncated one included (ClaimCore.Receive gives it its line)."""
    ev = _code(_member(src[PS], "private static void OnEvent("))
    head = ev[:ev.index("if (kind == TypeClaim) { OnClaim(e.Sender, a); return; }")]
    exits = [" ".join(l.split()) for l in head.splitlines() if "return" in l]
    assert exits == ["if (e.Code != EventCode) return;", "if (a == null || a.Length < 2) return;",
                     "if (!(a[0] is byte) || !(a[1] is byte)) return;", "if ((byte)a[1] != Protocol) return;"], \
        "a claim can leave the dispatcher before OnClaim: %s" % exits


CLAIM_LINE_CAPS = ("if (_skipLines < 20)", "if (_prefixFaults <= 20)")


def check_claim_evidence_bounded(src):
    """Fix pass 3 (M2): a started claim's child faults and streams are folded
    into its one bounded outcome (ClaimLine.Started), and every other
    [POISON-CLAIM] line the shell writes itself sits under a per-room cap."""
    start = _code(_member(src[PS], "private static string StartClaim("))
    assert "Plugin.Log" not in start, "a started claim writes a line beside its own"
    assert 'catch (Exception ex) { threw++; NoteFirstFault("child", ex); }' in start
    assert "return ClaimLine.Started(_nextStream - first, first, children, threw, contained, firstFault);" in start
    assert "catch (Exception ex) { return ClaimLine.StartFault(ex.GetType().Name); }" in start
    assert "StringBuilder" not in start and "Append(" not in start, "a started claim lists its streams"
    ps = _code(src[PS])
    uses = [m.start() for m in re.finditer(re.escape('"[POISON-CLAIM]'), ps)]
    assert len(uses) == len(CLAIM_LINE_CAPS), "%d shell-written claim lines" % len(uses)
    for i, cap in zip(uses, CLAIM_LINE_CAPS):
        assert cap in ps[max(0, i - 300):i], "a shell-written claim line is not under its cap " + cap
    reset = _code(_member(src[PS], "private static void ResetForRoomExit("))
    assert "_skipLines = 0;" in reset and "_prefixFaults = 0;" in reset


# check_claim_evidence_bounded: one mutation per bounded structure (each red).
CLAIM_EVIDENCE_MUTANTS = {
    "per-child-line": (PS, 'catch (Exception ex) { threw++; NoteFirstFault("child", ex); }',
                       'catch (Exception ex) { threw++; Plugin.Log.LogWarning("[POISON-CLAIM] start threw c=" + claimId + ": " + ex.Message); }'),
    "prefix-fault-uncapped": (PS, "if (_prefixFaults <= 20)", "if (_prefixFaults >= 0)"),
    "skip-uncapped": (PS, "if (_skipLines < 20)", "if (_skipLines >= 0)"),
    "stream-list": (PS, "return ClaimLine.Started(_nextStream - first, first, children, threw, contained, firstFault);",
                    "var sb = new System.Text.StringBuilder();\n            for (int s = first; s < _nextStream; s++) sb.Append('s').Append(s);\n"
                    "            return \"started streams=\" + sb;"),
}


def check_claim_start_faults_attributed(src):
    """Fix pass 4 (M2): every fault contained inside a claim's own start --
    a child's prefix (HookGuard.Prefix's onFault and the patch's own catch),
    the DOT scheduler's catch, a stream's or tick sound's first coroutine
    step -- is counted on that claim's one line (ClaimStartFault) and writes
    no line of its own; outside a claim's start each keeps its own evidence."""
    ps = _code(src[PS])
    csf = _code(_member(src[PS], "internal static bool ClaimStartFault("))
    assert "if (_claimStartDepth <= 0) return false;" in csf, "a fault outside a claim's start is swallowed"
    assert "_startContained++;" in csf and "NoteFirstFault(where, ex);" in csf
    pfd = _code(_member(src[PS], "internal static bool PrefixFaultDecision("))
    assert 'if (ClaimStartFault("prefix", ex)) return run;' in pfd, "a claim's prefix fault is not the claim's"
    assert pfd.index('if (ClaimStartFault("prefix", ex)) return run;') < pfd.index("_prefixFaults++;"), \
        "a claim's prefix fault writes the room line"
    enter = _code(_member(src[PS], "internal static bool PoisonEffectEnter("))
    assert "ex => PrefixFaultDecision(ex)," in enter
    assert "if (_claimStartDepth > 0) return;" in enter and \
        enter.index("if (_claimStartDepth > 0) return;") < enter.index("if (_skipLines < 20)"), \
        "a skip inside a claim's start writes the room skip line"
    arm = _code(_member(_member(ps, "internal static class PoisonArmPatch"), "private static bool Prefix("))
    assert "catch (Exception ex) { return PoisonSync.PrefixFaultDecision(ex); }" in arm
    sched = _code(_member(_member(ps, "internal static class PoisonDotSchedulerPatch"), "private static bool Prefix("))
    assert 'try { claims = PoisonSync.ClaimStartFault("scheduler", ex); } catch { }' in sched
    assert 'if (!claims) Plugin.Log.LogError("[POISON-SYNC] scheduler failed' in sched, \
        "the scheduler's fault inside a claim's start writes a line of its own"
    assert sched.count("StartCoroutine(") == 3, "a coroutine the scheduler starts is not swept"
    assert "StartCoroutine(PoisonSync.ClaimContained(PoisonSync.AuthoritativeDot(" in sched, "a stream's first step is not contained"
    assert "StartCoroutine(PoisonSync.ClaimContained(PoisonSync.LocalTickSound(" in sched, "a tick sound's first step is not contained"
    assert "StartCoroutine(PoisonSync.ShadowDot(" in sched   # a replica's observer: never inside a claim's start (victim is mine)
    steps = _code(_member(src[PS], "private static IEnumerator StartContained("))
    assert "if (!ClaimStartFault(where, ex)) UnityEngine.Debug.LogException(ex);" in steps
    start = _code(_member(src[PS], "private static string StartClaim("))
    assert "contained = _startContained;" in start and "firstFault = _startFirstFault;" in start, \
        "the claim's line does not carry its contained faults"
    assert "_startContained = 0;" in start and \
        start.index("_startContained = 0;") < start.index("_claimStartDepth++;"), "a start's count is not its own"
    flat = " ".join(ps.split())
    raise_lines = flat.count('"[POISON-AUTH] raise threw: "')
    assert raise_lines == 2 and flat.count(
        'if (!ClaimStartFault("raise", ex)) Plugin.Log.LogWarning("[POISON-AUTH] raise threw: "') == raise_lines, \
        "a send fault inside a claim's start writes a line of its own"


# check_claim_start_faults_attributed: one mutation per contained-fault path (each red).
CLAIM_START_FAULT_MUTANTS = {
    "outside-swallowed": (PS, "            if (_claimStartDepth <= 0) return false;\n            _startContained++;",
                          "            _startContained++;"),
    "prefix-room-line": (PS, '                if (ClaimStartFault("prefix", ex)) return run;\n', ""),
    "skip-line-in-start": (PS, "                        if (_claimStartDepth > 0) return;\n                        if (_skipLines < 20)",
                           "                        if (_skipLines < 20)"),
    "arm-catch-unattributed": (PS, "catch (Exception ex) { return PoisonSync.PrefixFaultDecision(ex); }",
                               "catch { return PoisonSync.PrefixFaultDecision(null); }"),
    "scheduler-room-line": (PS, 'if (!claims) Plugin.Log.LogError("[POISON-SYNC] scheduler failed',
                            'Plugin.Log.LogError("[POISON-SYNC] scheduler failed'),
    "stream-uncontained": (PS, "StartCoroutine(PoisonSync.ClaimContained(PoisonSync.AuthoritativeDot(",
                           "StartCoroutine(PoisonSync.Identity(PoisonSync.AuthoritativeDot("),
    "sound-uncontained": (PS, "StartCoroutine(PoisonSync.ClaimContained(PoisonSync.LocalTickSound(",
                          "StartCoroutine(PoisonSync.Identity(PoisonSync.LocalTickSound("),
    "step-fault-logged": (PS, "if (!ClaimStartFault(where, ex)) UnityEngine.Debug.LogException(ex);",
                          "UnityEngine.Debug.LogException(ex);"),
    "contained-not-carried": (PS, "contained = _startContained;", "contained = 0;"),
    "raise-room-line": (PS, "        private static bool Raise(object[] payload)",
                        '        private static void RaiseNote(Exception ex) { Plugin.Log.LogWarning("[POISON-AUTH] raise threw: " + ex.Message); }\n'
                        "        private static bool Raise(object[] payload)"),
}


def check_silent_arm(src):
    shadow = _code(_member(src[PS], "internal static IEnumerator ShadowDot("))
    assert '" arm=" + SilentArm.Label(armClaim)' in shadow, "the SILENT line does not name its arm"
    assert "broadcast-or-direct" not in shadow
    effect = _code(_member(src[PS], "private static void ArmEffect("))
    assert effect.index("if (_claimStartDepth > 0) return;") < effect.index("_currentArmClaim = SilentArm.Broadcast;")


CHECKS = {f.__name__: f for f in (
    check_staged_together, check_gate_reads_raw_cap, check_rooms_stay_open, check_targeted_sends,
    check_room_events_reach_the_gate,
    check_claim_only_from_entered_poison, check_claim_decided_before_start, check_every_arm_one_terminal_line,
    check_funnel_is_closed, check_shared_predicates, check_epoch_wire, check_flush_on_every_stop,
    check_evidence_tags, check_point_binding, check_replay_wiring, check_unstamped_break, check_silent_arm,
    check_header_failure_retires, check_fence_failure_retires, check_v3_live_names_every_dependency,
    check_claim_dispatch_terminal, check_claim_evidence_bounded, check_claim_start_faults_attributed,
)}

# (check, file, old, new): one named mutation per check that must turn it red.
MUTANTS = {
    "check_staged_together": (PS, "                    { CapabilityPropV3, v3 }\n", ""),
    "check_gate_reads_raw_cap": (PS, "v is int && (int)v == CapabilityValue", "v != null"),
    "check_rooms_stay_open": (PS, "                _v3RetakeDue = false;\n                _lastActivateSent",
                              "                PhotonNetwork.CurrentRoom.IsOpen = false;\n                _v3RetakeDue = false;\n                _lastActivateSent"),
    "check_targeted_sends": (PS, "new RaiseEventOptions { TargetActors = targets };",
                             "new RaiseEventOptions { Receivers = ReceiverGroup.All };"),
    "check_room_events_reach_the_gate": (PL, '            try { PoisonSync.V3RoomEvent("player-left", p); } catch { }\n', ""),
    "check_claim_only_from_entered_poison": (PS, "if (f == null || !f.LocalOnly || vv.IsMine) return;",
                                             "if (f == null || vv.IsMine) return;"),
    "check_claim_decided_before_start": (PS, "return _claims.TryStart(ph.GetInstanceID(), vv.ViewID, StartPath.Broadcast);",
                                         "return true;"),
    "check_every_arm_one_terminal_line": (CORE, 'outcome = ClaimLine.Outcome("malformed");', "return;"),
    "check_funnel_is_closed": (PS, "            if (DamageRulesGate.Refuses(hh, FindPlayer(rec.AttackerId))) return;\n",
                               "            hh.DoDamage(Vector2.zero, Vector2.zero, Color.white);\n"),
    "check_shared_predicates": (PS, "if (!RoomActors.LocalIsSpectator && EndScreenKillPatch.RefusesNow()) return false;",
                                "if (!RoomActors.LocalIsSpectator && !GameManager.instance.battleOngoing) return false;"),
    "check_epoch_wire": (PS, "attackerId, lethal, (byte)damageSource, blocked, _nextSeq++\n                    });",
                         "attackerId, lethal, (byte)damageSource, blocked, _nextSeq++, epoch.Ts, epoch.Set\n                    });"),
    "check_flush_on_every_stop": (PS, "                if (v != null) PoisonSync.FlushOpenV3(v.ViewID);\n            });\n        }",
                                  "            });\n        }"),
    "check_evidence_tags": (PS, "foreach (string line in _claims.Lines) Plugin.Log.LogInfo(line);",
                            "foreach (string line in _claims.Lines) Plugin.Log.LogInfo(line + PhotonNetwork.LocalPlayer.NickName);"),
    "check_point_binding": (PS, "if (_inbox.Take(viewId, streamId, out epoch) && AcceptNewV3(epoch))",
                            "if (_inbox.Take(viewId, streamId, out epoch))"),
    "check_replay_wiring": (PS, "if (_act.OnAck(sender, (int)a[3], (int)a[2])) ReplayTo(sender);",
                            "_act.OnAck(sender, (int)a[3], (int)a[2]);"),
    "check_unstamped_break": (PS, "            try { _ledger.Break(view); _inbox.Clear(); DrainRetired(); } catch { }\n            if (_epochBroken) return;\n",
                              "            if (_epochBroken) return;\n            try { _ledger.Break(view); _inbox.Clear(); DrainRetired(); } catch { }\n"),
    "check_silent_arm": (PS, '" arm=" + SilentArm.Label(armClaim)', '(armClaim > 0 ? " arm=local-only c=" + armClaim : " arm=broadcast-or-direct")'),
    "check_header_failure_retires": (PS, "if (!send.AfterHeader(_retainer, sent)) _openV3.Remove(openKey);",
                                     "send.AfterTick(0, blocked, sent);"),
    "check_fence_failure_retires": (PS, 'if (__exception != null) PoisonSync.FenceNotRecorded("point-over threw");',
                                    "if (__exception != null) { }"),
    "check_v3_live_names_every_dependency": (PS, "                    && ReviveFenceLive\n", ""),
    "check_claim_dispatch_terminal": (PS, "if (a == null || a.Length < 2) return;", "if (a == null || a.Length < 4) return;"),
    "check_claim_evidence_bounded": CLAIM_EVIDENCE_MUTANTS["per-child-line"],
    "check_claim_start_faults_attributed": CLAIM_START_FAULT_MUTANTS["prefix-room-line"],
}

# check_v3_live_names_every_dependency: one mutation per term of V3PatchesLive
# (each must turn it red), plus a patch that newly calls PoisonSync (the derived
# set grows) and a dependency whose cleanup records nothing.
V3_LIVE_MUTANTS = {
    "PatchesLive": (PS, "return PatchesLive\n                    && RpcStampLive", "return RpcStampLive"),
    "RpcStampLive": (PS, "                    && RpcStampLive\n", ""),
    "HitBracketLive": (PS, "                    && HitBracketLive\n", ""),
    "PoisonArmLive": (PS, "                    && PoisonArmLive\n", ""),
    "PhoenixBoundaryLive": (PS, "                    && PhoenixBoundaryLive\n", ""),
    "DeathFlushLive": (PS, "                    && DeathFlushLive\n", ""),
    "PointBoundaryLive": (PS, "                    && PointBoundaryLive\n", ""),
    "ReviveFenceLive": (PS, "                    && ReviveFenceLive\n", ""),
    "DamageRulesGate": (PS, "                    && ReviveFenceLive\n                    && VanillaFixSupport.IsAttached(\"DamageRulesGate\");",
                        "                    && ReviveFenceLive;"),
    "new-dependency": (PS, "        private static void Before() { PointEvidence.SawBefore(); }",
                       "        private static void Before() { PointEvidence.SawBefore(); PoisonSync.NoteRoundBoundary(); }"),
    "unrecorded-attach": (PS, "            if (exception == null) PoisonSync.PointBoundaryLive = true;\n", ""),
    "missing-not-named": (PS, '            if (!ReviveFenceLive) m.Add("PoisonReviveFence");\n', ""),
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


@pytest.mark.parametrize("which", sorted(CLAIM_EVIDENCE_MUTANTS))
def test_claim_evidence_turns_red(which):
    src = _normal(_load())
    with pytest.raises(AssertionError):
        check_claim_evidence_bounded(_mutate(src, CLAIM_EVIDENCE_MUTANTS[which]))
    check_claim_evidence_bounded(_mutate(src, CONTROL))


@pytest.mark.parametrize("which", sorted(CLAIM_START_FAULT_MUTANTS))
def test_claim_start_faults_turn_red(which):
    src = _normal(_load())
    with pytest.raises(AssertionError):
        check_claim_start_faults_attributed(_mutate(src, CLAIM_START_FAULT_MUTANTS[which]))
    check_claim_start_faults_attributed(_mutate(src, CONTROL))


@pytest.mark.parametrize("term", sorted(V3_LIVE_MUTANTS))
def test_v3_live_turns_red(term):
    src = _normal(_load())
    with pytest.raises(AssertionError):
        check_v3_live_names_every_dependency(_mutate(src, V3_LIVE_MUTANTS[term]))
    check_v3_live_names_every_dependency(_mutate(src, CONTROL))


# -- V4 B7: every hook and callback the poison lane adds or changes contains its own faults --
#
# A hook body may hold only guarded statements: a HookGuard.Run/Prefix call,
# or a try with a catch whose body cannot throw, plus the trivial assignments
# HOOK_ALLOWED names. A decision-bearing prefix additionally takes its
# decision in one place (HOOK_REQUIRED) and holds no try that a later fault
# could reverse (HOOK_FORBIDDEN). HookGuard itself is executed with throwing
# bodies by the harness (refused_start_stands, phoenix_postfix_contained,
# prefix_fault_no_second_stream). Each hook below has its own mutant.

HOOKS = {
    "PoisonReviveFencePatch.AfterRevive": (PS, None, "private static void AfterRevive(HealthHandler __instance)"),
    "PointEndEvidencePatch.After": (PS, "internal static class PointEndEvidencePatch",
                                    "private static void After(GM_ArmsRace __instance)"),
    "PoisonRpcStampPatch.Prefix": (PS, None,
                                   "private static void Prefix(ExitGames.Client.Photon.Hashtable __0, out Frame __state)"),
    "PoisonRpcStampPatch.Finalizer": (PS, None, "private static Exception Finalizer(Frame __state, Exception __exception)"),
    "PoisonPhoenixBoundaryPatch.After": (PS, "internal static class PoisonPhoenixBoundaryPatch",
                                         "private static void After(HealthHandler __instance)"),
    "PoisonDeathFlushPatch.After": (PS, "internal static class PoisonDeathFlushPatch",
                                    "private static void After(HealthHandler __instance)"),
    "PoisonHitBracketPatch.Prefix": (PS, None, "private static void Prefix(ProjectileHit __instance)"),
    "PoisonHitBracketPatch.Finalizer": (PS, None,
                                        "private static Exception Finalizer(ProjectileHit __instance, Exception __exception)"),
    "PoisonArmPatch.Prefix": (PS, None, "private static bool Prefix(RayHitPoison __instance, HitInfo hit, out int __state)"),
    "PoisonArmPatch.Finalizer": (PS, None, "private static Exception Finalizer(int __state, Exception __exception)"),
    "PoisonSync.PoisonEffectEnter": (PS, None, "internal static bool PoisonEffectEnter("),
    "PoisonSync.OnEvent": (PS, None, "private static void OnEvent("),
    "PoisonSync.Tick": (PS, None, "internal static void Tick()"),
    "PoisonSync.V3Upkeep": (PS, None, "private static void V3Upkeep("),
    "PoisonSync.FillPendingAll": (PS, None, "private static void FillPendingAll("),
    "PoisonSync.V3RoomEvent": (PS, None, "internal static void V3RoomEvent("),
    "PoisonSync.V3PropsChanged": (PS, None, "internal static void V3PropsChanged("),
    "EndScreenKillPatch.BeforeTransitionDamage": (VF, None, "private static bool BeforeTransitionDamage("),
    # fix pass 2 (H2): the fence finalizers
    "PointEndEvidencePatch.Threw": (PS, "internal static class PointEndEvidencePatch",
                                    "private static Exception Threw(Exception __exception)"),
    "PoisonReviveFencePatch.Threw": (PS, "internal static class PoisonReviveFencePatch",
                                     "private static Exception Threw(HealthHandler __instance, Exception __exception)"),
    "PoisonPhoenixBoundaryPatch.Threw": (PS, "internal static class PoisonPhoenixBoundaryPatch",
                                         "private static Exception Threw(HealthHandler __instance, Exception __exception)"),
}

HOOK_ALLOWED = (
    "int id = -1;", "int id = -2;", "if (id < 0) return;", "return __exception;", "__state = 0;", "__state = _cur;",
    "var f = new Frame();", "_cur = f;", "_cur = __state;", "if (e.Code != EventCode) return;",
    "prevArm = _currentArmClaim;", "ProjectileHit ph = null;", "PhotonView pv = null, vv = null;",
)

HOOK_REQUIRED = {
    "PoisonArmPatch.Prefix": ("try { return PoisonSync.PoisonEffectEnter(__instance, hit, out __state); }",
                              "catch (Exception ex) { return PoisonSync.PrefixFaultDecision(ex); }"),
    "PoisonSync.PoisonEffectEnter": ("return HookGuard.Prefix(", "ex => PrefixFaultDecision(ex),"),
    "EndScreenKillPatch.BeforeTransitionDamage": ("return HookGuard.Prefix(", "() => !healthRemoval || !RefusesNow(),"),
}

HOOK_FORBIDDEN = {
    "PoisonSync.PoisonEffectEnter": ("try",),
    "EndScreenKillPatch.BeforeTransitionDamage": ("try",),
}

PLUGIN_CALLBACKS = {
    "Plugin.OnPlayerEnteredRoom": 'try { PoisonSync.V3RoomEvent("player-entered", p); } catch { }',
    "Plugin.OnPlayerLeftRoom": 'try { PoisonSync.V3RoomEvent("player-left", p); } catch { }',
    "Plugin.OnPlayerPropertiesUpdate": "try { PoisonSync.V3PropsChanged(target, changedProps); } catch { }",
}

ALL_HOOKS = sorted(list(HOOKS) + list(PLUGIN_CALLBACKS))


def _close(text, i, open_ch, close_ch):
    """Index just past the bracket that closes the one at text[i]."""
    assert text[i] == open_ch, "expected %r at %d" % (open_ch, i)
    depth, j, in_str = 0, i, False
    while j < len(text):
        c = text[j]
        if in_str:
            if c == "\\":
                j += 2
                continue
            if c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    raise AssertionError("unbalanced %r" % open_ch)


def _skip_ws(text, i):
    while i < len(text) and text[i].isspace():
        i += 1
    return i


def _unguarded(body):
    """Top-level statements of the hook body that are neither guarded nor
    named by HOOK_ALLOWED."""
    inner = body[body.index("{") + 1:body.rindex("}")]
    out, i = [], 0
    while True:
        i = _skip_ws(inner, i)
        if i >= len(inner):
            return out
        m = re.match(r"(return )?HookGuard\.(Run|Prefix)\(", inner[i:])
        if m:
            j = _close(inner, i + m.end() - 1, "(", ")")
            assert inner[j] == ";", "a guard call is not a statement"
            i = j + 1
            continue
        if re.match(r"try\b", inner[i:]):
            j = _close(inner, _skip_ws(inner, i + 3), "{", "}")
            k = _skip_ws(inner, j)
            assert inner.startswith("catch", k), "a try without a catch"
            k = _skip_ws(inner, k + 5)
            if inner[k] == "(":
                k = _skip_ws(inner, _close(inner, k, "(", ")"))
            i = _close(inner, k, "{", "}")
            continue
        j = inner.index(";", i)
        stmt = " ".join(inner[i:j + 1].split())
        if stmt not in HOOK_ALLOWED:
            out.append(stmt)
        i = j + 1


def _hook_body(src, name):
    f, cls, sig = HOOKS[name]
    text = _code(src[f])
    if cls:
        text = _member(text, cls)
    return _member(text, sig)


def check_hook(src, name):
    if name in PLUGIN_CALLBACKS:
        line = PLUGIN_CALLBACKS[name]
        call = line[len("try { "):-len(" } catch { }")]
        pl = _code(src[PL])
        assert pl.count(call) == 1, name + ": the call occurs %d times" % pl.count(call)
        assert pl.count(line) == 1, name + " calls PoisonSync outside its own try"
        return
    body = _hook_body(src, name)
    flat = " ".join(body.split())
    assert not re.search(r"\bthrow\b", body), name + " can throw"
    bad = _unguarded(body)
    assert not bad, name + " runs unguarded: " + " | ".join(bad)
    for need in HOOK_REQUIRED.get(name, ()):
        assert need in flat, name + " lacks " + need
    for no in HOOK_FORBIDDEN.get(name, ()):
        assert not re.search(r"\b%s\b" % no, body), name + " holds a " + no + " a later fault could reverse"


# (file, old, new): one mutation per hook that must turn its check red.
HOOK_MUTANTS = {
    "PoisonReviveFencePatch.AfterRevive": (PS, "HookGuard.Run(() => PoisonSync.OnLocalRevive(id));",
                                           "PoisonSync.OnLocalRevive(id);"),
    "PointEndEvidencePatch.After": (PS, "HookGuard.Run(() => PoisonSync.NotePointBoundary(__instance));",
                                    "PoisonSync.NotePointBoundary(__instance);"),
    "PoisonRpcStampPatch.Prefix": (PS, "            catch { }\n            _cur = f;", "            catch { throw; }\n            _cur = f;"),
    "PoisonRpcStampPatch.Finalizer": (PS, "            _cur = __state;\n            return __exception;",
                                      "            _cur = __state;\n            PoisonSync.NotePhoenixBoundary(null);\n            return __exception;"),
    "PoisonPhoenixBoundaryPatch.After": (PS, "HookGuard.Run(() => PoisonSync.NotePhoenixBoundary(__instance));",
                                         "PoisonSync.NotePhoenixBoundary(__instance);"),
    "PoisonDeathFlushPatch.After": (PS, "                if (v != null) PoisonSync.FlushOpenV3(v.ViewID);\n            });\n        }",
                                    "                if (v != null) PoisonSync.FlushOpenV3(v.ViewID);\n            });\n            PoisonSync.FlushOpenV3(-1);\n        }"),
    "PoisonHitBracketPatch.Prefix": (PS, "{ HookGuard.Run(() => PoisonSync.HitEnter(__instance)); }",
                                     "{ PoisonSync.HitEnter(__instance); }"),
    "PoisonHitBracketPatch.Finalizer": (PS, "HookGuard.Run(() => PoisonSync.HitExit(__instance));",
                                        "PoisonSync.HitExit(__instance);"),
    "PoisonArmPatch.Prefix": (PS, "catch (Exception ex) { return PoisonSync.PrefixFaultDecision(ex); }", "catch { return true; }"),
    "PoisonArmPatch.Finalizer": (PS, "HookGuard.Run(() => PoisonSync.PoisonEffectExit(__state));",
                                 "PoisonSync.PoisonEffectExit(__state);"),
    "PoisonSync.PoisonEffectEnter": (PS, "            prevArm = _currentArmClaim;\n",
                                     "            prevArm = _currentArmClaim;\n            ArmEffect(null, null, null, hit);\n"),
    "PoisonSync.OnEvent": (PS, "            if (e.Code != EventCode) return;\n            try",
                           "            if (e.Code != EventCode) return;\n            V3Upkeep();\n            try"),
    "PoisonSync.Tick": (PS, "        internal static void Tick()\n        {\n            try",
                        "        internal static void Tick()\n        {\n            FillPendingAll();\n            try"),
    "PoisonSync.V3Upkeep": (PS, "        private static void V3Upkeep()\n        {\n            try",
                            "        private static void V3Upkeep()\n        {\n            FillPendingAll();\n            try"),
    "PoisonSync.FillPendingAll": (PS, "        private static void FillPendingAll()\n        {\n            try",
                                  "        private static void FillPendingAll()\n        {\n            DrainRetired();\n            try"),
    "PoisonSync.V3RoomEvent": (PS, "        internal static void V3RoomEvent(string kind, Photon.Realtime.Player p)\n        {\n            try",
                               "        internal static void V3RoomEvent(string kind, Photon.Realtime.Player p)\n        {\n            _act.OnRoomEvent(kind);\n            try"),
    "PoisonSync.V3PropsChanged": (PS, "            try\n            {\n                if (changed != null && changed.ContainsKey(CapabilityPropV3))",
                                  "            V3RoomEvent(\"cap-change\", target);\n            try\n            {\n                if (changed != null && changed.ContainsKey(CapabilityPropV3))"),
    # the M6 shape: a try whose catch returns true, around a diagnostic written after the refusal
    "EndScreenKillPatch.BeforeTransitionDamage": (
        VF, "            return HookGuard.Prefix(\n                () => !healthRemoval || !RefusesNow(),",
        "            try { if (healthRemoval && RefusesNow()) { VanillaFixSupport.DiagLimited(\"k\", \"m\", 20); return false; } }\n"
        "            catch { return true; }\n"
        "            return HookGuard.Prefix(\n                () => !healthRemoval || !RefusesNow(),"),
    "PointEndEvidencePatch.Threw": (
        PS, 'HookGuard.Run(() => { if (__exception != null) PoisonSync.FenceNotRecorded("point-over threw"); });',
        'if (__exception != null) PoisonSync.FenceNotRecorded("point-over threw");'),
    "PoisonReviveFencePatch.Threw": (
        PS, 'HookGuard.Run(() => { if (__exception != null) PoisonSync.FenceNotRecorded("revive threw", __instance); });',
        'if (__exception != null) PoisonSync.FenceNotRecorded("revive threw", __instance);'),
    "PoisonPhoenixBoundaryPatch.Threw": (
        PS, 'HookGuard.Run(() => { if (__exception != null) PoisonSync.FenceNotRecorded("Phoenix threw", __instance); });',
        'if (__exception != null) PoisonSync.FenceNotRecorded("Phoenix threw", __instance);'),
    "Plugin.OnPlayerEnteredRoom": (PL, '            try { PoisonSync.V3RoomEvent("player-entered", p); } catch { }\n',
                                   '            PoisonSync.V3RoomEvent("player-entered", p);\n'),
    "Plugin.OnPlayerLeftRoom": (PL, '            try { PoisonSync.V3RoomEvent("player-left", p); } catch { }\n',
                                '            PoisonSync.V3RoomEvent("player-left", p);\n'),
    "Plugin.OnPlayerPropertiesUpdate": (PL, "            try { PoisonSync.V3PropsChanged(target, changedProps); } catch { }\n",
                                        "            PoisonSync.V3PropsChanged(target, changedProps);\n"),
}


@pytest.mark.parametrize("name", ALL_HOOKS)
def test_hook_contains_faults(name):
    check_hook(_normal(_load()), name)


@pytest.mark.parametrize("name", ALL_HOOKS)
def test_hook_check_turns_red(name):
    src = _normal(_load())
    assert set(HOOK_MUTANTS) == set(ALL_HOOKS), "a hook has no mutant"
    with pytest.raises(AssertionError):
        check_hook(_mutate(src, HOOK_MUTANTS[name]), name)
    check_hook(_mutate(src, CONTROL), name)
