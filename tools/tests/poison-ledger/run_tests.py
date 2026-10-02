"""Poison convergence v3 harness: build the cases over the REAL
plugin/PoisonLedgerCore.cs, run them, then build mutated COPIES (work/,
CoreSource override -- the tracked file is never written) and require each
mutant's target case to FAIL and its named control case to PASS. Every case
has its own mutant. Exit 0 only when everything holds.

    python tools/tests/poison-ledger/run_tests.py
"""
import hashlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
PROJ = os.path.join(HERE, "PoisonLedgerTests.csproj")
CORE = os.path.join(REPO, "plugin", "PoisonLedgerCore.cs")
WORK = os.path.join(HERE, "work")

DEDUP = "if (r.Committed.Contains(k) || r.Blocked.Contains(k) || r.Applied.Contains(k)) { r.Duplicates++; return; }"
BLOCKED = "if (blocked) { r.Blocked.Add(k); return; }          // consumed, as today"
NEXT = "if (cls == LifeClass.Next) { r.Pending.Add(k); return; }"
APPLY = "r.Applied.Add(k);\n            try { ap.Regular(r, k); } catch { r.Exceptions++; }"
SUMMARY_SKIP = "if (r.Committed.Contains(k) || r.Blocked.Contains(k) || r.Applied.Contains(k)) continue;"
BROADCAST_RULE = "return path == StartPath.Broadcast && had == StartPath.Broadcast;"
SEND_RATE = "if (_sendTimes.Count >= ClaimsPerRollingSecond) return \"rate\";"
CREATE_GATE = "if (_broken || CountForView(view) >= HeldCeilingPerView) return null;"
EXACT = ("if (f.Length != _roster.Length) return false;\n"
         "            for (int i = 0; i < f.Length; i++) if (f[i] != _roster[i] || !cap3(f[i])) return false;")

# (name, old text, new text, target case, control case). Each old text must
# occur exactly once in the shipped file; one mutant per case.
MUTANTS = [
    # V2 cases 1-26
    ("verdict_no_dedup", DEDUP, "if (r.Blocked.Contains(k)) { r.Duplicates++; return; }", "dup_verdict", "wrap"),
    ("header_overwrites", "else r.Duplicates++;",
     "else { r = Create(view, stream, s, payload); if (r == null) return null; }", "dup_header", "out_of_order"),
    ("seq_high_water", BLOCKED,
     "foreach (int a in r.Applied) if (a > k) { r.Duplicates++; return; }\n            " + BLOCKED,
     "out_of_order", "dup_verdict"),
    ("blocked_goes_pending", BLOCKED, "if (blocked) { r.Blocked.Add(k); r.Pending.Add(k); return; }",
     "blocked_never_filled", "rule_refusal_consumed"),
    ("next_dropped", NEXT, "if (cls == LifeClass.Next) return;",
     "slow_seat_header_before_revive", "slow_seat_header_after_revive"),
    ("fence_ignored", "bool fenceAtB = l.FenceState == 2 && l.Fence == b;", "bool fenceAtB = false;",
     "slow_seat_header_after_revive", "late_joiner_unset"),
    ("revive_keeps_stale", "foreach (var r in stale) Retire(r, \"revive\");", "",
     "stale_tail_after_revive", "next_deferred"),
    ("ending_filled", "Classify(view, r.Life) == LifeClass.Current) mine.Add(r);",
     "(Classify(view, r.Life) == LifeClass.Current || Classify(view, r.Life) == LifeClass.Ending)) mine.Add(r);",
     "ending_window", "wrap"),
    ("next_applied_live", NEXT, "", "next_deferred", "slow_seat_header_after_revive"),
    ("phoenix_room_wide", "l.Phoenix = ts; l.HasPhoenix = true; }",
     "l.Phoenix = ts; l.HasPhoenix = true; NotePointBoundary(ts); }", "phoenix", "wrap"),
    ("ending_as_stale", "return LifeClass.Ending;", "return LifeClass.Stale;",
     "spurious_point_over", "late_joiner_unset"),
    ("revive_retires_current", "if (r.View == view && Classify(view, r.Life) == LifeClass.Stale) stale.Add(r);",
     "if (r.View == view) stale.Add(r);", "multi_revive_one_boundary", "late_joiner_unset"),
    ("no_boundary_next", "if (!BoundaryFor(view, out b)) return LifeClass.Current;",
     "if (!BoundaryFor(view, out b)) return LifeClass.Next;", "late_joiner_unset", "wrap"),
    ("stamp_compare_plain", "{ unchecked { return (a - b) > 0; } }", "{ return a > b; }", "wrap", "dup_verdict"),
    ("newer_epoch_ending", "if (s.Set && After(s.Ts, b)) return LifeClass.Next;", "",
     "late_boundary_converges", "late_joiner_unset"),
    ("retry_after_exception", APPLY,
     "try { ap.Regular(r, k); r.Applied.Add(k); } catch { r.Exceptions++; r.Pending.Add(k); }",
     "exception_at_most_once", "dup_verdict"),
    ("corrective_not_consumed", "r.Pending.Remove(k);", "", "rule_refusal_consumed", "dup_verdict"),
    ("tick_range_unbounded", "if (k < 0 || k >= MaxTick) { r.OutOfRange++; return; }",
     "if (k < 0) { r.OutOfRange++; return; }", "index_range", "dup_verdict"),
    ("inbox_not_consumed", "_byKey.Remove(k);\n            return true;", "return true;",
     "life_message_required", "dup_verdict"),
    ("fill_regular", "try { ap.Corrective(r, k); }", "try { ap.Regular(r, k); }", "two_seat_convergence", "dup_verdict"),
    ("claim_no_highwater",
     "if (_highWater.TryGetValue(sender, out hw) && !PoisonLedgerCore.After(claimId, hw)) return \"dup\";",
     "", "claim_starts_once", "claim_not_owner"),
    ("broadcast_beats_claim", BROADCAST_RULE, "return path == StartPath.Broadcast;",
     "claim_then_broadcast", "broadcast_repeat_allowed"),
    ("claim_no_fence",
     "if (!f.VictimFenceKnown || !f.ShooterEpoch.SameAs(f.VictimEpoch)) return \"fence\";", "",
     "claim_previous_life", "claim_not_owner"),
    ("claim_no_owner_check", "if (f.ProjOwner != f.Sender) return \"not-owner\";", "",
     "claim_not_owner", "claim_starts_once"),
    ("claim_live_unchecked", "if (!f.Live) return \"not-live\";", "", "claim_not_live", "claim_not_owner"),
    # A1: catch-up and the room-common epoch
    ("summary_blocked_as_committed", "bool c = Bit(committed, k), bl = Bit(blocked, k);",
     "bool c = Bit(committed, k) || Bit(blocked, k), bl = false;", "summary_late_joiner", "dup_header"),
    ("summary_no_stale_check",
     "if (Classify(view, r.Life) == LifeClass.Stale) { Retire(r, \"stale-verdict\"); return r; }", "",
     "summary_older_epoch_refused", "summary_late_joiner"),
    ("summary_ignores_applied", SUMMARY_SKIP, "if (r.Blocked.Contains(k)) continue;",
     "summary_idempotent", "summary_late_joiner"),
    ("boundary_last_arrival", "if (_hasPoint && !After(ts, _point)) { if (ts == _point) _pointAdopted = false; return; }",
     "", "boundary_stamp_order_independent", "late_joiner_unset"),
    # A2b: activation over the acknowledged fighters; rooms stay open
    ("ack_count_any", "if (acked < _roster.Length)", "if (acked == 0)",
     "activation_requires_all_acks", "activation_master_only"),
    ("event_not_sticky", "internal void OnRoomEvent(string why) { Kill(why); }",
     "internal void OnRoomEvent(string why) { }", "activation_killed_by_room_event", "activation_requires_all_acks"),
    ("cap_not_checked",
     "if (!cap3(a)) { Kill(\"cap-missing actor=\" + a); why = \"cap-missing actor=\" + a; return false; }",
     "{ }", "activation_cap_missing", "activation_master_only"),
    ("targets_ignore_cap", "if (present != null) foreach (int a in present) if (cap3(a)) r.Add(a);",
     "if (present != null) foreach (int a in present) r.Add(a);", "join_unseen_old_spectator",
     "activation_requires_all_acks"),
    ("ack_subset", EXACT, "foreach (int x in f) if (Array.IndexOf(_roster, x) < 0 || !cap3(x)) return false;",
     "ack_requires_exact_roster", "activation_cap_missing"),
    ("activate_any_sender", "if (sender != currentMaster || fighters == null || fighters.Length == 0) return false;",
     "if (fighters == null || fighters.Length == 0) return false;", "activation_master_only",
     "activation_requires_all_acks"),
    ("ack_timeout_off",
     "if (nowMs - _receivedMs >= AckTimeoutMs) { Kill(\"ack-timeout\"); why = \"killed:\" + _killWhy; return false; }",
     "", "activation_ack_timeout", "activation_master_only"),
    ("offer_ignores_cap", "foreach (int a in fighters) if (!cap3(a)) return false;", "",
     "join_unseen_old_fighter", "join_unseen_new_fighter"),
    ("acks_survive_reactivation", "_acks.Clear();\n            _killed = false; _killWhy = null;\n            _receivedMs",
     "_killed = false; _killWhy = null;\n            _receivedMs", "join_unseen_new_fighter", "activation_master_only"),
    ("roster_compare_subset", "if (fighters == null || !SameSet(fighters, _roster)) {", "if (fighters == null) {",
     "fighter_leave", "activation_requires_all_acks"),
    ("ack_ignores_cap", "if (f[i] != _roster[i] || !cap3(f[i])) return false;", "if (f[i] != _roster[i]) return false;",
     "property_flip", "activation_requires_all_acks"),
    ("ack_ignores_aid", "if (_roster == null || master != _master || aid != _aid) return false;",
     "if (_roster == null || master != _master) return false;", "readmission", "activation_master_only"),
    ("close_targets_ignore_holders", "if (a != self && k.Holders.Contains(a) && !r.Contains(a)) r.Add(a);",
     "if (a != self && !r.Contains(a)) r.Add(a);", "join_during_active_stream", "late_acker_replay"),
    ("replay_ignores_present_at_start",
     "return k.PresentAtStart == null || Array.IndexOf(k.PresentAtStart, actor) < 0;", "return true;",
     "today_path_seat_not_caught_up", "join_during_active_stream"),
    ("owner_ack_unchecked", "if (!ownerAcked) return \"owner-not-acked\";", "",
     "claim_owner_not_acked", "sender_pair_marked"),
    ("sender_ack_unchecked", "if (!f.SenderAcked) return \"sender-not-acked\";", "",
     "claim_sender_not_acked", "claim_not_owner"),
    # A3: the funnel
    ("summary_applies_regular", "r.Pending.Add(k);\n                r.CatchUp++;",
     "r.Applied.Add(k); ap.Regular(r, k);\n                r.CatchUp++;", "catchup_never_regular", "dup_verdict"),
    # A4: bounds
    ("no_ceiling", CREATE_GATE, "if (_broken) return null;", "ceiling_refuses_new", "two_seat_convergence"),
    ("admission_unbounded", "if (_openUntil.Count >= MaxOpenV3StreamsPerVictim) return false;", "",
     "victim_admission_bound", "wrap"),
    # A5: durable claim results, one TryStart
    ("highwater_not_advanced", "_highWater[sender] = claimId;", "",
     "claim_rate_refusal_durable", "claim_not_owner"),
    ("claim_ignores_tried_start",
     "if (!TryStart(f.ProjInstance, f.VictimView, StartPath.Claim)) return _saturated ? \"start-refused\" : \"dup-broadcast\";",
     "TryStart(f.ProjInstance, f.VictimView, StartPath.Claim);", "broadcast_then_claim", "claim_then_broadcast"),
    ("broadcast_once", BROADCAST_RULE, "return false;", "broadcast_repeat_allowed", "claim_then_broadcast"),
    # A6: sender-side limits
    ("pair_not_marked", "if (_sentPairs.Contains(key)) return \"pair-marked\";", "",
     "sender_pair_marked", "sender_rate_32"),
    ("sender_rate_off", SEND_RATE, "", "sender_rate_32", "sender_pair_marked"),
    ("rate_unmarks_pair", SEND_RATE,
     "if (_sendTimes.Count >= ClaimsPerRollingSecond) { _sentPairs.Remove(key); return \"rate\"; }",
     "sender_no_retry_after_fail", "sender_pair_marked"),
    # V4 (fix pass 1): F1 retained state, replay, the point-bound activation
    ("replay_ignores_holders", "if (k.Holders.Contains(actor)) return false;", "",
     "late_acker_replay", "today_path_seat_not_caught_up"),
    ("no_point_adoption", "_point = ts; _hasPoint = true; _pointAdopted = true;", "",
     "no_boundary_seat_adopts", "late_joiner_unset"),
    ("no_life_adoption", "if (!_pointAdopted || !s.Set || !InPoint(s)) return;", "return;",
     "joiner_takes_owner_life", "late_joiner_unset"),
    ("replay_any_life", "if (!v.Point.SameAs(point) || !v.Life.SameAs(currentLife)) return r;", "",
     "retained_current_life_only", "late_acker_replay"),
    ("retained_unbounded", "if (v.Streams.Count >= MaxKeptPerLife) return null;", "",
     "retained_bounded", "late_acker_replay"),
    ("kept_ticks_unbounded", "if (tick < 0 || tick >= PoisonLedgerCore.MaxTick) return;", "",
     "retained_ticks_bounded", "late_acker_replay"),
    ("accept_any_point", "return _hasAckedPoint && _ackedPoint.SameAs(point);", "return _hasAckedPoint;",
     "accept_bound_to_point", "ack_bound_to_point"),
    ("ack_any_point", "if (!point.SameAs(_epoch)) return false;", "",
     "ack_bound_to_point", "accept_bound_to_point"),
    # F2: an unstamped boundary
    ("break_keeps_held", "foreach (var r in gone) Retire(r, \"epoch-broken\");", "",
     "unstamped_boundary_retires", "broken_refuses_later"),
    ("broken_admits", CREATE_GATE, "if (CountForView(view) >= HeldCeilingPerView) return null;",
     "broken_refuses_later", "unstamped_boundary_retires"),
    # F3: no eviction
    ("evict_at_ceiling", CREATE_GATE,
     "if (_broken) return null;\n            if (CountForView(view) >= HeldCeilingPerView) "
     "foreach (var o in _recs.Values) if (o.View == view) { Retire(o, \"evict\"); break; }",
     "held_never_evicted", "two_seat_convergence"),
    # F4: durable marks and starts
    ("pairs_expire", "if (_sentPairs.Count >= PairCap) return \"pair-cap\";",
     "if (_sentPairs.Count >= PairCap) _sentPairs.Clear();", "pair_marks_durable", "sender_pair_marked"),
    ("starts_expire", "if (_started.Count >= StartedCap) { _saturated = true; return true; }",
     "if (_started.Count >= StartedCap) _started.Clear();", "start_durable", "broadcast_then_claim"),
    # F5: the id is consumed before any lookup
    ("collect_before_admit",
     "string dup = Admit(sender, claimId, nowMs, out overRate);\n            if (dup != null) return dup;\n"
     "            try { facts = collect(); }\n            catch (Exception ex) { return \"fault:\" + ex.GetType().Name; }",
     "try { facts = collect(); }\n            catch (Exception ex) { return \"fault:\" + ex.GetType().Name; }\n"
     "            string dup = Admit(sender, claimId, nowMs, out overRate);\n            if (dup != null) return dup;",
     "claim_fault_terminal", "claim_starts_once"),
    # F6: the traffic terms are the payloads' sizes
    ("wire_activate_short", "return new object[] { TypeActivate, Protocol, aid, fighters, point.Ts, point.Set };",
     "return new object[] { TypeActivate, Protocol, aid, fighters, point.Ts };", "traffic_formula", "dup_verdict"),
    # F7: every result named
    ("outcome_unnamed", "return \"drop reason=\" + (string.IsNullOrEmpty(result) ? \"unnamed\" : result);",
     "return \"drop\";", "claim_terminal_every_path", "claim_fault_terminal"),
    # F8: hooks contain their own faults
    ("after_fault_runs", "if (after != null) { try { after(run); } catch { } }",
     "if (after != null) { try { after(run); } catch { run = true; } }", "refused_start_stands",
     "phoenix_postfix_contained"),
    ("run_rethrows", "try { body(); } catch { }", "body();", "phoenix_postfix_contained", "refused_start_stands"),
    ("fault_runs_always", "if (_claimStarts > 0) return false;", "", "prefix_fault_no_second_stream",
     "start_durable"),
    # F9: the SILENT arm
    ("label_merged", "return arm == Broadcast ? \"broadcast\" : \"direct\";", "return \"broadcast-or-direct\";",
     "silent_arm_label", "dup_verdict"),
    # F10: the point boundary invalidates
    ("point_unchecked",
     "if (!point.SameAs(_epoch)) { Kill(\"point-boundary\"); why = \"killed:\" + _killWhy; return false; }", "",
     "retake_invalidates", "activation_requires_all_acks"),
]


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def build(tag, core):
    out = os.path.join(WORK, tag)
    cmd = ["dotnet", "build", PROJ, "-c", "Release", "-nologo", "-v", "q",
           "-p:IntermediateOutputPath=" + os.path.join(out, "obj") + os.sep,
           "-p:OutDir=" + os.path.join(out, "bin") + os.sep,
           "-p:CoreSource=" + core]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-3000:], r.stderr[-2000:])
        return None
    return os.path.join(out, "bin", "PoisonLedgerTests.dll")


def run(dll, cases=()):
    r = subprocess.run(["dotnet", dll] + list(cases), capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def main():
    only = sys.argv[1:]
    os.makedirs(WORK, exist_ok=True)
    head = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    print("commit", head)
    before = sha(CORE)
    print("plugin/PoisonLedgerCore.cs sha256", before)
    ok = True

    targets = [m[3] for m in MUTANTS]
    names = [m[0] for m in MUTANTS]
    if len(set(targets)) != len(targets) or len(set(names)) != len(names):
        print("BAD mutant table: a case or a name appears twice")
        ok = False

    dll = build("base", CORE)
    if dll is None:
        print("BUILD FAILED (base)")
        return 1
    rc, out = run(dll)
    print(out)
    ok = ok and rc == 0
    cases = [l.split()[1] for l in out.splitlines() if l.startswith(("PASS ", "FAIL "))]
    missing = sorted(set(cases) - set(targets))
    if missing:
        print("BAD: cases without their own mutant:", ", ".join(missing))
        ok = False

    raw = open(CORE, "rb").read().decode("utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    caught = 0
    run_set = [m for m in MUTANTS if not only or m[0] in only]
    for name, old, new, target, control in run_set:
        o, n = old.replace("\n", nl), new.replace("\n", nl)
        count = raw.count(o)
        if count != 1:
            print("BAD mutant %s: anchor occurs %d times" % (name, count))
            ok = False
            continue
        path = os.path.join(WORK, "mut_" + name + ".cs")
        open(path, "wb").write(raw.replace(o, n).encode("utf-8"))
        mdll = build("mut_" + name, path)
        if mdll is None:
            print("BAD mutant %s: does not build" % name)
            ok = False
            continue
        trc, _ = run(mdll, [target])
        crc, _ = run(mdll, [control])
        hit = trc != 0 and crc == 0
        caught += hit
        ok = ok and hit
        print("%s mutant %s: target %s=%s; control %s=%s" % (
            "CAUGHT" if hit else "MISSED", name, target, "FAIL" if trc else "PASS", control, "PASS" if crc == 0 else "FAIL"))
    print("mutants: %d of %d caught" % (caught, len(run_set)))
    after = sha(CORE)
    print("plugin/PoisonLedgerCore.cs sha256 after", after)
    print("tracked file unchanged:", after == before)
    ok = ok and after == before
    print("RESULT", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
