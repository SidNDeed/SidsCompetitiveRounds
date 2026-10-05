#!/usr/bin/env python3
"""V11 reference model (N6 to N10): the gone rule, the boundary protocol, the fence, the
count and the exits.

Usage: python boundary_model.py
Prints one line per check and exits 0 only when every expected result holds: each correct
rule passes every fixture, and each mutant is RED on the fixture named for it while its
inert twin passes. It models the rules' decisions, not the SQL, the Photon transport or
the game; the build's own controls (S64, S66, K42, K45, K50) execute the real code.

N6 and N8: gone(seat) under V11 (a leave and a claim are triggers only; a record needs the
witness test, and a corroborated seat whose leave the server holds is labelled 'leave'),
under V10 (a leave writes by itself: the N8 mutant) and under V9 (a lone claim writes: the
N6 mutant). Fixtures: the false claim and the false leave (bound actor 7 present, every
current witness lists 7), the corroborated absence, the leave corroborated at its own
transaction, and a leave corroborated only at a later census.
N7 and N9: one boundary with a call-in master M and receivers A, B (kind s) and L (listed in
the proposal). V10's enumeration is kept as it ran; V11's adds each receiver's set before
the boundary, whether its previous pairing was with M, and a stamp from an earlier master.
The fence, the count and the exits (N10) are modelled after it.
"""
import itertools
import sys

FAIL = []


def check(name, cond):
    print("%-4s %s" % ("ok" if cond else "FAIL", name))
    if not cond:
        FAIL.append(name)


# ---------------------------------------------------------------- N6 and N8: the gone rule
def witness_test(sub, peers, now):
    """sec2 I2 (iii): >= 2 current witnesses omit the bound actor, none lists it, and the
    subject's own census, when within 10 s, does not list its own bound actor."""
    cur = [p for p in peers if p["current"] and now - p["census_at"] <= 10]
    omit = [p for p in cur if sub["bound"] not in p["lists"]]
    lists = [p for p in cur if sub["bound"] in p["lists"]]
    own_fresh = now - sub["census_at"] <= 10
    own_ok = (not own_fresh) or (sub["bound"] not in sub["lists"])
    return len(omit) >= 2 and not lists and own_ok


def gone_v11(sub, peers, now, event):
    """V11 (N8): the leave, like the claim, is a trigger; only the witness test writes."""
    if sub["gone"] is not None:
        return sub["gone"]                          # first write wins
    if event == "claim" and not (sub["claim_region"] == sub["region"] and sub["claim"] != sub["bound"]):
        return None                                 # a claim of the bound actor or of another region runs nothing
    if event in ("leave", "census", "claim"):
        if witness_test(sub, peers, now):
            return "leave" if sub.get("left") else "witness"
        return None
    return None


def gone_v10(sub, peers, now, event):              # the N8 mutant: V10's writer 5 writes on the leave alone
    if sub["gone"] is not None:
        return sub["gone"]
    if event == "leave":
        return "leave"
    if event in ("census", "claim"):
        if event == "claim" and not (sub["claim_region"] == sub["region"] and sub["claim"] != sub["bound"]):
            return None
        return "witness" if witness_test(sub, peers, now) else None
    return None


def gone_v9(sub, peers, now, event):              # the N6 mutant: V9:629, a lone claim writes
    if sub["gone"] is not None:
        return sub["gone"]
    if event == "leave":
        return "leave"
    if event == "claim" and sub["claim_region"] == sub["region"] and sub["claim"] != sub["bound"]:
        return "claim"
    if event in ("census", "claim"):
        return "witness" if witness_test(sub, peers, now) else None
    return None


def gone_no_trigger(sub, peers, now, event):      # over-correction mutant: a claim runs nothing
    if event == "claim":
        return sub["gone"]
    return gone_v11(sub, peers, now, event)


def gone_no_leave(sub, peers, now, event):        # over-correction mutant: the leave runs nothing
    if event == "leave":
        return sub["gone"]
    return gone_v11(sub, peers, now, event)


def gone_census_unlabelled(sub, peers, now, event):   # label mutant: a census ignores left_at
    got = gone_v11(sub, peers, now, event)
    return "witness" if got == "leave" and event == "census" else got


K_AT_CLAIM = 2    # a claim or a leave that lands during game 2 (games_played 1, so k = 2)
K_AT_CENSUS = 4   # the later census that corroborates a real departure lands during game 4


def settle(g, gone_game):
    """Writer 7 (d) for game g: unrated and the seat's report refused when g > gone_game."""
    if gone_game is not None and g > gone_game:
        return ("unrated", "refused")
    return ("rated", "accepted")


LISTS_7 = [{"current": True, "census_at": 98, "lists": [7, 3]}, {"current": True, "census_at": 97, "lists": [7, 4]},
           {"current": True, "census_at": 99, "lists": [7, 5]}]
OMIT_7 = [{"current": True, "census_at": 98, "lists": [3]}, {"current": True, "census_at": 97, "lists": [4]}]


def n6_fixture(kind):
    now = 100
    sub = {"bound": 7, "region": "eu", "claim": 12, "claim_region": "eu", "lists": [], "census_at": 80,
           "gone": None, "left": False}
    if kind == "false_claim":
        return sub, LISTS_7, now, "claim"
    if kind == "corroborated":
        return sub, OMIT_7, now, "claim"
    if kind == "true_leave":                        # V11: the leave's own transaction finds two witnesses omitting 7
        return dict(sub, left=True), OMIT_7, now, "leave"
    if kind == "false_leave":                       # N8: actor 7 present, listed by every current witness and itself
        return dict(sub, left=True, lists=[7, 3], census_at=99), LISTS_7, now, "leave"
    if kind == "leave_uncorroborated":              # a real leave that lands before any witness's census omits 7
        peers = [{"current": True, "census_at": 95, "lists": [7, 3]}, {"current": True, "census_at": 94, "lists": [7, 4]}]
        return dict(sub, left=True), peers, now, "leave"
    if kind == "later_census":                      # the same seat, corroborated by a census 30 s later, in game 4
        peers = [{"current": True, "census_at": 128, "lists": [3]}, {"current": True, "census_at": 127, "lists": [4]}]
        return dict(sub, left=True), peers, 130, "census"
    raise ValueError(kind)


def run_n6():
    """V10's nine N6 checks, run under V11's rule; the true leave is now a corroborated one."""
    expect = {"false_claim": None, "corroborated": "witness", "true_leave": "leave"}
    for fx, want in expect.items():
        got = gone_v11(*n6_fixture(fx))
        check("N6 V11 rule, fixture %s: gone_path %s" % (fx, got), got == want)
    got = gone_v11(*n6_fixture("false_claim"))
    rec = None if got is None else K_AT_CLAIM
    check("N6 V11 false claim: game 3 settles R %s, its report %s" % settle(3, rec),
          settle(3, rec) == ("rated", "accepted"))
    got = gone_v9(*n6_fixture("false_claim"))
    red = got is not None and settle(3, K_AT_CLAIM) == ("unrated", "refused")
    check("N6 mutant V9:629 claim path is RED on the false claim (writes %s at game %d; game 3: %s, report %s)"
          % ((got, K_AT_CLAIM) + settle(3, K_AT_CLAIM if got else None)), red)
    for fx in ("corroborated", "true_leave"):
        check("N6 twin %s passes under V11 and under the V9 mutant" % fx,
              gone_v11(*n6_fixture(fx)) == expect[fx] and gone_v9(*n6_fixture(fx)) in (expect[fx], "claim"))
    check("N6 mutant 'claim runs nothing' is RED on the corroborated twin",
          gone_no_trigger(*n6_fixture("corroborated")) != expect["corroborated"])
    check("N6 mutant 'leave runs nothing' is RED on the true-leave twin",
          gone_no_leave(*n6_fixture("true_leave")) != expect["true_leave"])


def leave_branch(started_gated, live_evidence, rule):
    """The leave route's branch: V11 reads a started gated lobby as live (N8), V10 did not."""
    live = live_evidence or (started_gated if rule == "v11" else False)
    return "live" if live else "else"


def completes(branch, departed_after, members):
    return branch == "else" and departed_after >= members - 1   # the else branch's completion at all-but-one


def run_n8():
    got = gone_v11(*n6_fixture("false_leave"))
    check("N8 V11 rule, fixture false_leave (actor 7 present): gone_trigger path=leave result=%s, no record"
          % ("witness" if got else "none"), got is None)
    rec = None if got is None else K_AT_CLAIM
    check("N8 V11 false leave: game 3 settles R %s, its report %s, the beaten counts unchanged" % settle(3, rec),
          settle(3, rec) == ("rated", "accepted"))
    got = gone_v10(*n6_fixture("false_leave"))
    check("N8 mutant V10 writer 5 (the leave writes by itself) is RED on the false leave (writes %s at game %d;"
          " game 3: %s, report %s)" % ((got, K_AT_CLAIM) + settle(3, K_AT_CLAIM if got else None)),
          got == "leave" and settle(3, K_AT_CLAIM) == ("unrated", "refused"))
    check("N8 twin: the leave corroborated at its own transaction writes 'leave' under V11 and under the V10 mutant",
          gone_v11(*n6_fixture("true_leave")) == "leave" and gone_v10(*n6_fixture("true_leave")) == "leave")
    first = gone_v11(*n6_fixture("leave_uncorroborated"))
    sub, peers, now, ev = n6_fixture("later_census")
    later = gone_v11(sub, peers, now, ev)
    check("N8 twin: a real leave not yet corroborated writes nothing (%s), and the later census writes '%s' at game %d"
          % (first, later, K_AT_CENSUS), first is None and later == "leave")
    s3, s4, s5 = settle(3, K_AT_CENSUS), settle(4, K_AT_CENSUS), settle(5, K_AT_CENSUS)
    check("N8 record at the census's game %d: game 3 %s, game 4 %s (scored as its leave), game 5 %s"
          % (K_AT_CENSUS, s3[0], s4[0], s5[0]),
          s3 == ("rated", "accepted") and s4 == ("rated", "accepted") and s5 == ("unrated", "refused"))
    check("N8 mutant 'staged game' (the record takes the leave's game %d) is RED: game 3, which the seat played, %s"
          " and its report %s" % ((K_AT_CLAIM,) + settle(3, K_AT_CLAIM)), settle(3, K_AT_CLAIM) == ("unrated", "refused"))
    check("N8 mutant 'the leave runs nothing' is RED on the corroborated-leave twin",
          gone_no_leave(*n6_fixture("true_leave")) != "leave")
    check("N8 mutant 'a census ignores left_at' is RED on the later-census twin (labels it %s)"
          % gone_census_unlabelled(sub, peers, now, ev), gone_census_unlabelled(sub, peers, now, ev) != "leave")
    v11 = leave_branch(True, False, "v11")
    v10 = leave_branch(True, False, "v10")
    check("N8 leave route on a started gated lobby between games (3 members, 1 departed): V11 takes the %s branch"
          " and completes %s; the V10 mutant takes the %s branch and completes %s (RED)"
          % (v11, completes(v11, 2, 3), v10, completes(v10, 2, 3)),
          not completes(v11, 2, 3) and completes(v10, 2, 3))
    check("N8 twin: an ungated lobby between games keeps today's branch under both (%s, %s)"
          % (leave_branch(False, False, "v11"), leave_branch(False, False, "v10")),
          leave_branch(False, False, "v11") == leave_branch(False, False, "v10") == "else")


# ---------------------------------------------------------------- N7: the boundary protocol (V10, kept as it ran)
RECV = ("A", "B", "L")
S_TIMING = ("before", "window", "beyond", "never")


def orders_for(ack_on_time, s_timing):
    """Arrival orders of P, S, C at one receiver, consistent with causality: an on-time
    acknowledgement means P arrived before the master sent S and C."""
    msgs = ["P", "S", "C"] if s_timing != "never" else ["P", "C"]
    for perm in itertools.permutations(msgs):
        if ack_on_time and (perm.index("P") > perm.index("C") or ("S" in perm and perm.index("P") > perm.index("S"))):
            continue
        if s_timing == "before" and perm.index("S") > perm.index("C"):
            continue
        if s_timing in ("window", "beyond") and perm.index("S") < perm.index("C"):
            continue
        yield perm


def receiver(perm, s_timing, stamp_n, rule, rogue=None):
    """Returns (paired_n, lag, applied_final). rule: 'v10' | 'apply_at_p' | 'no_hold' | 'rogue_ok'."""
    applied, stamp, paired, lag = 0, None, None, None
    seq = list(perm)
    if rogue is not None:
        seq.insert(rogue, "R")
    for m in seq:
        if m == "P":
            if rule == "apply_at_p":
                applied = max(applied, 1)           # V9-like: apply before the commit is known
        elif m == "R":                              # a stamp from a kind-s client that is not the master
            if rule == "rogue_ok" and paired is None and stamp is None:
                stamp = 1
        elif m == "S":
            if paired is None:
                if stamp is None:
                    stamp = stamp_n
            else:                                   # a late stamp: roll forward, never back
                if stamp_n > applied:
                    applied = stamp_n
                if lag == "timeout" and stamp_n == paired:
                    lag = None                      # consistent after all: kept_lag end why=stamp
        elif m == "C":
            if rule == "no_hold":
                if stamp is not None:
                    applied = max(applied, stamp)
                paired = applied                    # no wait for the stamp, no KEPT_LAG
                continue
            if stamp is not None:
                applied = max(applied, stamp)
                paired = applied
            elif s_timing == "window":
                applied = max(applied, stamp_n)     # the hold released by the stamp
                paired = applied
                stamp = stamp_n
            else:
                paired = applied                    # carried set, KEPT_LAG why=timeout
                lag = "timeout"
    return paired, lag, applied


def run_boundary(rule, master_rule="v10", fifo_only=False, rogue=False):
    """Enumerates every combination; returns the list of violations (by invariant)."""
    bad = {"I1": 0, "I2": 0, "I6": 0}
    runs = 0
    acks = list(itertools.product((True, False), repeat=len(RECV))) if not fifo_only else [(True,) * len(RECV)]
    stims = S_TIMING if not fifo_only else ("before",)
    for ack in acks:
        commit = all(ack) if master_rule == "v10" else True
        master_n = 1 if commit else 0
        per_recv = []
        for i, r in enumerate(RECV):
            opts = []
            for st in stims:
                for perm in orders_for(ack[i], st):
                    if fifo_only and list(perm) != ["P", "S", "C"]:
                        continue
                    rpos = range(len(perm) + 1) if rogue else [None]
                    for rp in rpos:
                        opts.append((perm, st, rp))
            per_recv.append(opts)
        for combo in itertools.product(*per_recv):
            runs += 1
            res = [receiver(p, st, master_n, rule, rp) for (p, st, rp) in combo]
            # I1: a client that pairs without KEPT_LAG differs from the master
            if any(lag is None and paired != master_n for (paired, lag, applied) in res):
                bad["I1"] += 1
            # I2: a client keeps more than the master committed
            if any(paired > master_n or applied > master_n for (paired, lag, applied) in res):
                bad["I2"] += 1
            # I6: divergence although the master did not commit
            if not all(ack) and any(paired != master_n for (paired, lag, applied) in res):
                bad["I6"] += 1
    return runs, bad


def run_n7():
    runs, bad = run_boundary("v10")
    check("N7 protocol, %d executions: I1 (no silent divergence) %d, I2 (never ahead) %d, I6 (divergence only after a commit) %d"
          % (runs, bad["I1"], bad["I2"], bad["I6"]), not any(bad.values()))
    runs, bad = run_boundary("v10", rogue=True)
    check("N7 protocol with a rogue kind-s stamp, %d executions: all invariants hold" % runs, not any(bad.values()))
    runs, bad = run_boundary("v10", fifo_only=True)
    res = [receiver(("P", "S", "C"), "before", 1, "v10") for _ in RECV]
    check("N7 twin (the premises true): every receiver pairs epoch 1 with no KEPT_LAG",
          all(r == (1, None, 1) for r in res) and not any(bad.values()))
    for mut, inv, kw in (("apply_at_p", "I2", {}), ("no_hold", "I1", {}), ("rogue_ok", "I2", {"rogue": True})):
        runs, bad = run_boundary(mut, **kw)
        check("N7 mutant %s is RED (%s violated in %d of %d executions)" % (mut, inv, bad[inv], runs), bad[inv] > 0)
        runs2, bad2 = run_boundary(mut, fifo_only=True)
        check("N7 mutant %s passes the twin (premises true): %s" % (mut, bad2), not any(bad2.values()))
    runs, bad = run_boundary("v10", master_rule="commit_without_acks")
    check("N7 mutant commit-without-every-ack is RED (I6 violated in %d of %d executions)" % (bad["I6"], runs), bad["I6"] > 0)
    runs2, bad2 = run_boundary("v10", master_rule="commit_without_acks", fifo_only=True)
    check("N7 mutant commit-without-every-ack passes the twin: %s" % bad2, not any(bad2.values()))


# ---------------------------------------------------------------- N9: V11's pairing, stamp_late and LAG_OUT
M0, NSTAR, ORPHAN_N = 1, 2, 2     # the call-in master's set before the boundary, its proposal, an orphan's commit
PRIORS = ((True, M0), (False, 0), (False, 1), (False, 2))   # (previous pairing with M, the receiver's set before)
ORPHANS = ("none", "before_c", "after_c")                   # a stamp for this (g, k) from an earlier master


def v11_options(ack_on_time):
    opts = []
    for same, c0 in PRIORS:
        for st in S_TIMING:
            for perm in orders_for(ack_on_time, st):
                late_p = perm.index("P") > perm.index("C") and st in ("beyond", "never")
                for p_in_hold in ((True, False) if late_p else (None,)):
                    for orphan in ORPHANS:
                        opts.append((same, c0, perm, st, p_in_hold, orphan))
    return opts


def recv_v11(opt, master_post, rule="v11"):
    """One receiver's point: (state, set it plays or holds, why). state 'play' or 'lag_out'."""
    same, c0, perm, st, p_in_hold, orphan = opt
    if orphan != "none" and rule in ("v10", "any_stamp"):
        return ("play", max(ORPHAN_N, c0), "conflict")    # V10: the earlier master's stamp pairs; the higher applied
    if st in ("before", "window"):                  # the call-in master's stamp pairs within the hold
        if master_post < c0 and rule in ("v10", "no_converge_down"):
            return ("play", c0, "conflict")         # V10: a stamp below keeps the set it holds and plays on
        return ("play", master_post, None)          # V11: the call-in master's set, up or down (converge)
    acked = perm.index("P") < perm.index("C") or bool(p_in_hold)
    if rule == "forfeit_all":
        return ("lag_out", c0, "timeout")
    if rule == "v10" or (rule == "play_on" and (acked or not same)):
        late = max(c0, master_post) if st == "beyond" else c0
        return ("play", late, "timeout")            # V10's KEPT_LAG: plays on, rolled forward by a later stamp
    if not acked and same:                          # undisputed: stamp_late
        if st == "beyond" and master_post != c0:
            return ("lag_out", c0, "stamp_above")   # a later valid stamp above the set: never under a compliant master
        return ("play", c0, "stamp_late")
    return ("lag_out", c0, "timeout")               # disputed: LAG_OUT for the rest of the point


def late_eligible(opt):
    same, c0, perm, st, p_in_hold, orphan = opt
    acked = perm.index("P") < perm.index("C") or bool(p_in_hold)
    return st in ("beyond", "never") and not acked and same


def run_n9_rule(rule="v11", election="v11", fifo=False):
    s = dict(runs=0, I7=0, I8=0, mass=0, outcomes=0, lag=0, needless=0, late=0, above=0, late_forfeit=0, orphan_runs=0)
    for acks in (list(itertools.product((True, False), repeat=3)) if not fifo else [(True, True, True)]):
        master_post = NSTAR if all(acks) else M0
        per = []
        for i in range(3):
            opts = [(True, M0, ("P", "S", "C"), "before", None, "none")] if fifo else v11_options(acks[i])
            per.append((opts, [recv_v11(o, master_post, rule) for o in opts]))
        for opts, res in per:
            for o, r in zip(opts, res):
                s["outcomes"] += 1
                s["lag"] += r[0] == "lag_out"
                s["needless"] += r[0] == "lag_out" and r[1] == master_post
                s["late"] += r[2] == "stamp_late"
                s["above"] += r[2] == "stamp_above"
                s["late_forfeit"] += late_eligible(o) and r[0] == "lag_out" and r[2] != "stamp_above"
        n = [len(p[0]) for p in per]
        total = n[0] * n[1] * n[2]
        s["runs"] += total
        s["orphan_runs"] += total - [sum(1 for o in p[0] if o[5] == "none") for p in per][0] * \
            [sum(1 for o in p[0] if o[5] == "none") for p in per][1] * [sum(1 for o in p[0] if o[5] == "none") for p in per][2]
        good7 = [sum(1 for r in p[1] if r[0] != "play" or r[1] == master_post) for p in per]
        s["I7"] += total - good7[0] * good7[1] * good7[2]
        lagn = [sum(1 for r in p[1] if r[0] == "lag_out") for p in per]
        s["mass"] += lagn[0] * lagn[1] * lagn[2]
        # I8: the elected reporter is level. Candidates A, then B, then M (level by definition);
        # L never (its sticky cr_late). V11 skips a candidate in LAG_OUT (cr_lag); the mutant does not.
        bad8 = 0
        for ra in per[0][1]:
            if election == "ignores_lag" or ra[0] == "play":
                bad8 += (ra[1] != master_post) * n[1] * n[2]
                continue
            bad8 += sum(1 for rb in per[1][1] if rb[0] == "play" and rb[1] != master_post) * n[2]
        s["I8"] += bad8
    return s


def run_n9():
    s = run_n9_rule()
    check("N9 V11 pairing, %d executions (%d with an earlier master's stamp): I7 (every receiver that plays the point"
          " holds the call-in master's set) %d, I8 (the elected reporter is level) %d" % (s["runs"], s["orphan_runs"], s["I7"], s["I8"]),
          s["I7"] == 0 and s["I8"] == 0)
    check("N9 V11 figures over %d receiver outcomes: LAG_OUT %d (%d with the master's own set, the needless ones),"
          " stamp_late %d, stamp_above %d, every receiver in LAG_OUT in %d executions"
          % (s["outcomes"], s["lag"], s["needless"], s["late"], s["above"], s["mass"]), s["above"] == 0)
    check("N9 V11: no receiver that sent no acknowledgement, and whose previous pairing was with the call-in master,"
          " forfeits (%d)" % s["late_forfeit"], s["late_forfeit"] == 0)
    t = run_n9_rule(fifo=True)
    check("N9 twin (the premises true): every receiver pairs epoch %d and plays; LAG_OUT %d, stamp_late %d"
          % (NSTAR, t["lag"], t["late"]), t["I7"] == 0 and t["I8"] == 0 and t["lag"] == 0 and t["late"] == 0)
    for mut, inv in (("v10", "I7"), ("play_on", "I7"), ("any_stamp", "I7"), ("no_converge_down", "I7"),
                     ("forfeit_all", "late_forfeit")):
        m = run_n9_rule(mut)
        check("N9 mutant %s is RED (%s: %d)" % (mut, inv, m[inv]), m[inv] > 0)
        t = run_n9_rule(mut, fifo=True)
        check("N9 mutant %s passes the twin (premises true): I7 %d, I8 %d, LAG_OUT %d" % (mut, t["I7"], t["I8"], t["lag"]),
              t["I7"] == 0 and t["I8"] == 0 and t["lag"] == 0)
    m = run_n9_rule("v11", election="ignores_lag")
    check("N9 mutant 'the election ignores cr_lag' is RED (I8: %d)" % m["I8"], m["I8"] > 0)
    t = run_n9_rule("v11", election="ignores_lag", fifo=True)
    check("N9 mutant 'the election ignores cr_lag' passes the twin: I8 %d" % t["I8"], t["I8"] == 0)


# ---------------------------------------------------------------- N7: the fence's bound
def fence(lands_at, rule, fence_s=3, tries=3):
    """lands_at: seconds after a try at which a SetMasterClient takes effect, keyed by try
    index, or None. Returns (end_state, seconds the fenced client held the role)."""
    t = 0
    for i in range(tries if rule == "v10" else 1):
        d = lands_at.get(i + 1) if lands_at else None
        if d is not None and d < fence_s:
            return "done", t + d
        t += fence_s
    if rule == "v10":
        return "FENCE_EXPIRED", t
    return "held", float("inf")


def run_fence():
    for lands in ({1: 0.2}, {2: 1.0}, {3: 2.9}, {}):
        st, held = fence(lands, "v10")
        check("fence V10, switch %s: %s after %.1f s (bound 9 s)" % (lands or "never", st, held), held <= 9)
    st, held = fence({}, "no_retry")
    check("fence mutant without retry or expiry is RED when the switch never lands (%s)" % st, held > 9)
    st, held = fence({1: 0.2}, "no_retry")
    check("fence mutant passes the twin (the switch lands at once): %s" % st, st == "done")


# ---------------------------------------------------------------- N7 and N9: the count
def count_client(order, rule, window):
    """order: this client's arrival order of 'X' (EVT_SCALE from M1), 'N' (M1's point latch),
    'W' (the switch to M2) and 'D' (the load, which follows the latch). window: when X
    arrives after D, whether it arrives within the load's hold. Returns (scale, lag)."""
    master, latch_master, rec, held = "M1", None, None, False

    def accept():
        if rule == "v9":
            return master == "M1"                   # V9: the current master at the dispatch only
        return master == "M1" or latch_master == "M1"   # V10: or the master at this point's latch

    for m in order:
        if m == "W":
            master = "M2"
            if rule == "v9":
                rec = None                          # V9: every master switch clears the record
        elif m == "N":
            latch_master = master
        elif m == "X":
            ok = accept()
            if held:
                if ok and window:
                    return 5, None                  # the held load takes the count
                return 0, "scale"                   # unscaled: V10 KEPT_LAG why=scale, V11 LAG_OUT
            if ok:
                rec = 5
        elif m == "D":
            if rec is not None:
                return rec, None
            if rule == "v10":
                held = True                         # the load gate holds up to ASM_STAMP_WAIT_S
                continue
            return 0, None                          # V9: unscaled, as if in agreement
    return 0, ("scale" if held else None)


def run_count():
    orders = [p for p in itertools.permutations("XNWD") if p.index("N") < p.index("D")]
    cases = [(o, w) for o in orders for w in (True, False)]
    for rule in ("v10", "v9"):
        split = 0
        for (a, wa), (b, wb) in itertools.product(cases, repeat=2):
            sa, la = count_client(a, rule, wa)
            sb, lb = count_client(b, rule, wb)
            if la is None and lb is None and sa != sb:
                split += 1
        if rule == "v10":
            check("count V10: two clients that load without KEPT_LAG load the same scale (splits: %d of %d)"
                  % (split, len(cases) ** 2), split == 0)
        else:
            check("count mutant V9 (clear at the switch, no hold) is RED (splits: %d of %d)"
                  % (split, len(cases) ** 2), split > 0)
    fifo = ("X", "N", "D", "W")
    check("count twin (send order kept, the switch after the load): V10 and V9 both scale",
          count_client(fifo, "v10", True) == (5, None) and count_client(fifo, "v9", True) == (5, None))
    # V11 (N9): a client whose load took no count sits the point out, so no playing client differs
    play_split = lag_split = 0
    lagged = sum(1 for (o, w) in cases if count_client(o, "v10", w)[1] is not None)
    for (a, wa), (b, wb) in itertools.product(cases, repeat=2):
        (sa, la), (sb, lb) = count_client(a, "v10", wa), count_client(b, "v10", wb)
        if sa != sb:
            lag_split += 1                          # V10: both play, the one in KEPT_LAG on its own scale
            if la is None and lb is None:
                play_split += 1                     # V11: only two playing clients can split
    check("count V11: the clients that play the point load the same scale (splits %d); a load without its count"
          " is LAG_OUT (%d of the %d client cases)" % (play_split, lagged, len(cases)), play_split == 0 and lagged > 0)
    check("count mutant V10 play-on (a client in the scale state plays) is RED: playing clients split in %d of %d pairs"
          % (lag_split, len(cases) ** 2), lag_split > 0)


# ---------------------------------------------------------------- N10: the exits and the room-exit hook
EXITS = (("fence_expired", True), ("fence_expired", False), ("join_timeout", True))
REAL_EXITS = (("join_timeout", False), ("start_timeout", False), ("wrong_region", False), ("asm_exit", False),
              ("quit", False))
FOUR = {"departed_ids", "gone_game", "unrated", "report_refused"}


def exit_route(why, admitted_late, rule):
    if rule == "v10":
        return "leave"                              # V10: every Exit calls FfaLeaveQueue
    if rule == "release_all":
        return "release"                            # over-correction: every exit released
    if why == "fence_expired" or (why == "join_timeout" and admitted_late):
        return "release"
    return "leave"


def route_reach(route):
    """What the route can reach for the caller's own seat on a started gated lobby."""
    if route == "release":
        return set()                                # its lease, its own queue row, released_at: nothing else
    return {"departed_ids", "gone_trigger"}         # the leave route: departed_ids, and since V11 the trigger


def room_exit(flags, rule):
    """The room-exit hook: returns whether FfaLeaveQueue runs."""
    if rule == "v11":
        if flags.get("release_room"):
            flags["release_room"] = False           # one-shot, consumed by this exit
            return False
        return True
    if rule == "ignore_flag":
        return True
    return not flags.get("release_room")            # sticky_flag: never consumed


def run_n10():
    for why, adm in EXITS:
        r = exit_route(why, adm, "v11")
        check("N10 V11 exit %s%s: %s, reaching %s of the four" % (why, " (admitted_late)" if adm else "", r,
              sorted(route_reach(r) & FOUR) or "none"), r == "release" and not (route_reach(r) & FOUR))
    check("N10 V11 twin: every real exit (%s) keeps the leave route" % ", ".join(w for w, a in REAL_EXITS),
          all(exit_route(w, a, "v11") == "leave" for w, a in REAL_EXITS))
    check("N10 mutant V10 (every Exit through FfaLeaveQueue) is RED on both protocol exits (departed_ids reached)",
          all("departed_ids" in route_reach(exit_route(w, a, "v10")) for w, a in EXITS))
    check("N10 mutant 'every exit released' is RED on the real-leave twin (a quit never reaches the leave route)",
          exit_route("quit", False, "release_all") != "leave")
    flags = {"release_room": True}
    first, second = room_exit(flags, "v11"), room_exit(flags, "v11")
    check("N10 V11 hook: the released exit skips FfaLeaveQueue (%s) and the next room exit runs it (%s)"
          % (first, second), first is False and second is True)
    check("N10 hook mutant 'the flag ignored' is RED: FfaLeaveQueue runs after the release",
          room_exit({"release_room": True}, "ignore_flag") is True)
    flags = {"release_room": True}
    room_exit(flags, "sticky_flag")
    check("N10 hook mutant 'the flag never consumed' is RED on the next real leave (FfaLeaveQueue skipped)",
          room_exit(flags, "sticky_flag") is False)


def main():
    run_n6()
    run_n8()
    run_n7()
    run_n9()
    run_fence()
    run_count()
    run_n10()
    print("boundary model: %d failure(s)" % len(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
