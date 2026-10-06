"""Synthetic combat records for the public tests (combat contract one).

Every record here is SYNTHETIC: built field by field in the test tree, with no
recording, no real game data and no player identity. Seats are 16-digit
numbers no Steam account has. The review's own case (A24) and its variants
are written out by hand, every total and cycle summary beside the shots it
follows from, so the server's rebuild is checked against numbers the test
states rather than against itself.
"""

import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))

import combat_evidence as ce  # noqa: E402
import combat_measures as cm  # noqa: E402

SEAT_A = "1000000000000601"
SEAT_B = "1000000000000602"
SEAT_C = "1000000000000603"
SEAT_D = "1000000000000604"
KEY = "test-hmac-key-combat-evidence"
FIXTURE_DIR = os.path.join(HERE, "fixtures", "combat_evidence")

W = cm.W
SPEC = cm.SPEC
FL = W["fl"]
END = W["end"]
GAP_NONE = W["gap_none"]


def _zero(lo, hi):
    return 0 if lo <= 0 <= hi else lo


def _zero_row(fields):
    return [_zero(f[1], f[2]) for f in fields]


def named_row(key, **vals):
    """A fixed row of `key` from field names; unnamed fields are zero (or
    their lowest bound when zero is outside it)."""
    fields = cm._fields(SPEC[key])
    if SPEC[key][0] == "groups":
        fields = SPEC[key][3]
    row = _zero_row(fields)
    names = [f[0] for f in fields]
    for k, v in vals.items():
        row[names.index(k)] = v
    return row


def empty_record(consts=1):
    """A valid record with nothing in it: no shot, no block, no point."""
    out = {}
    for k, s in W["spec"]:
        kind = s[0]
        if k == "schema":
            out[k] = W["schema"]
        elif k == "consts":
            out[k] = consts
        elif k == "frame_p50_us":
            out[k] = 16667
        elif k == "l_hat":
            out[k] = -1
        elif kind == "int":
            out[k] = _zero(s[1], s[2])
        elif kind == "enum":
            out[k] = s[1][0]
        elif kind == "row":
            out[k] = _zero_row(s[1])
        elif kind == "rows":
            out[k] = [_zero_row(s[2]) for _i in range(s[1])]
        elif kind == "hist":
            out[k] = [0] * s[1]
        elif kind in ("list", "groups"):
            out[k] = []
        else:
            out[k] = {o: 0 for o in cm.OMIT_KEYS}
    for side in ("s", "o"):
        out["tot_" + side] = named_row("tot_" + side, gap_minus_rexp_min=GAP_NONE)
    return out


def gun(pt=0, mag=3, rexp=1500, **over):
    vals = dict(pt=pt, mag=mag, rt=1500, rta=0, rtm=1000, rexp=rexp, mult=1000, cexp=300,
                nproj=1, bursts=1, tmpl=1)
    vals["as"] = 300
    vals.update(over)
    return named_row("gun_s", **vals)


def point(pt=0, **over):
    vals = dict(pt=pt, ps=0, real=60000, game=51000, srv=51000, frames=3600, slow=0, ramp=0,
                clamp=0, dt_med_us=16667, dt_max_us=21000, base=850)
    vals.update(over)
    return named_row("tb", **vals)


def tb_tot_of(points):
    T = cm.TB
    return named_row("tb_tot", real=sum(p[T["real"]] for p in points),
                     game=sum(p[T["game"]] for p in points), srv=sum(p[T["srv"]] for p in points),
                     frames=sum(p[T["frames"]] for p in points),
                     slow=sum(p[T["slow"]] for p in points), ramp=sum(p[T["ramp"]] for p in points),
                     clamp=sum(p[T["clamp"]] for p in points), base_changes=0, points=len(points))


def hdr(s0, pid0, n, *, pt=0, end=END["timer"], src=0, amt=-1, st_end=0, rl=(1500, 1500, 1600),
        rg=0, nrg=0):
    return [s0, pid0, n, pt, end, src, amt, st_end, rl[0], rl[1], rl[2], rg, nrg]


# A shot entry's `counter` (the design's `rc`) is the gun's reload counter
# before the shot while it is reloading, and -1 when it is not (combat fix
# pass 5, F1): every synthetic non-reloading shot below carries this value.
NOT_RELOADING = -1


def own_shot(dpid, dt, ammo, rl, counter, rep=0, since=-1, fl=FL["use_ammo"]):
    return [dpid, dt, ammo, rl, counter, rep, since, fl]


def copy_shot(dpid, dt, ammo, rl, counter, am=35):
    return [dpid, dt, ammo, rl, counter, am]


def regen(k, amt, st, gaps=(150, 150, 160)):
    return [k, amt, st, gaps[0], gaps[1], gaps[2]]


def cx(s0, units, vol, mag, regen_units, exh, in_rl, tail, gaps, rexp, end, why):
    return [s0, units, vol, mag, regen_units, exh, in_rl, tail, gaps[0], gaps[1], gaps[2], rexp,
            end, why]


def tot(**vals):
    base = dict(gap_minus_rexp_min=GAP_NONE)
    base.update(vals)
    return named_row("tot_s", **base)


# -- the review's case (A24): four single-projectile volleys, magazine three ----------

S0, PID0 = 10000, 700
A24_WHY_OWN = W["why"]["over_mag"] | W["why"]["in_reload"] | W["why"]["short_gap"] \
    | W["why"]["gate_reloading"]
A24_WHY_COPY = W["why"]["over_mag"] | W["why"]["in_reload"] | W["why"]["short_gap"]


def a24_pair(variant="base"):
    """(owner record, measuring record) of the review's case. The owner is
    seat A, whose gun has magazine 3 and reload 1500 ms; seat B measured it.
    One cycle, four single-projectile volleys 200 ms apart, the fourth after
    exhaustion and inside the reload.

    Variants:
      regen    the owner's fourth entry has ammo 1 and is not reloading, and
               the owner's group lists a one-unit regeneration before it that
               the measuring seat's copy does not (M5);
      trimmed  the measuring record's group was removed by the budgeter
               (`omit.sh_o` 1); its cycle summary is kept;
      short    the measuring record's group lists three of its four shots;
      mixed    the measuring record is of measurement version 2 (M2)."""
    owner, meas = empty_record(), empty_record(2 if variant == "mixed" else 1)
    for r in (owner, meas):
        r["tb"] = [point()]
        r["tb_tot"] = tb_tot_of(r["tb"])
    owner["gun_s"] = [gun()]
    meas["gun_o"] = [gun()]
    regens = []
    fourth_own = own_shot(1, 200, 0, 1, 100, fl=FL["use_ammo"] | FL["reloading"])
    if variant == "regen":
        regens = [regen(3, 1, S0 + 550)]
        fourth_own = own_shot(1, 200, 1, 0, NOT_RELOADING)
    owner["sh_s"] = [[hdr(S0, PID0, 4, st_end=S0 + 1900, rg=len(regens), nrg=len(regens)),
                      [own_shot(0, 0, 3, 0, NOT_RELOADING), own_shot(1, 200, 2, 0, NOT_RELOADING),
                       own_shot(1, 200, 1, 0, NOT_RELOADING), fourth_own], regens]]
    copy_entries = [copy_shot(0, 0, 3, 0, NOT_RELOADING), copy_shot(1, 200, 2, 0, NOT_RELOADING),
                    copy_shot(1, 200, 1, 0, NOT_RELOADING), copy_shot(1, 200, 0, 1, 100)]
    if variant == "short":
        copy_entries = copy_entries[:3]
    meas["sh_o"] = [[hdr(S0, PID0, 4, st_end=S0 + 1900), copy_entries, []]]
    if variant == "trimmed":
        meas["sh_o"] = []
        meas["omit"]["sh_o"] = 1
    # Hand-computed accounting (A24): exhaustion at the third shot (400 ms
    # after the first), the fourth shot 200 ms later is the first volley after
    # exhaustion, no tail, one projectile while reloading.
    if variant == "regen":
        own_why = W["why"]["short_gap"]
        owner["cx_s"] = [cx(S0, 4, 4, 3, 1, 400, 0, 0, (200, -1, -1), 1500, END["timer"], own_why)]
        owner["tot_s"] = tot(cycles=1, volleys=4, units=4, gate=4, emit=4, why_short_gap=1,
                             gap_minus_rexp_min=200 - 1500, cx_n=1, cx_volleys=4, cx_units=4)
    else:
        owner["cx_s"] = [cx(S0, 4, 4, 3, 0, 400, 1, 0, (200, -1, -1), 1500, END["timer"],
                            A24_WHY_OWN)]
        owner["tot_s"] = tot(cycles=1, volleys=4, units=4, gate=4, emit=4, inits_rl=1,
                             why_over_mag=1, why_in_reload=1, why_short_gap=1,
                             why_gate_reloading=1, sum_excess=1, gap_minus_rexp_min=200 - 1500,
                             cx_n=1, cx_volleys=4, cx_units=4)
    meas["cx_o"] = [cx(S0, 4, 4, 3, 0, 400, 1, 0, (200, -1, -1), 1500, END["timer"], A24_WHY_COPY)]
    meas["tot_o"] = tot(cycles=1, volleys=4, units=4, atk_msg=4, inits_rl=1, why_over_mag=1,
                        why_in_reload=1, why_short_gap=1, sum_excess=1,
                        gap_minus_rexp_min=200 - 1500, cx_n=1, cx_volleys=4, cx_units=4)
    return owner, meas


def records(owner=None, meas=None, a=SEAT_A, b=SEAT_B):
    """The pair_view input of one game: the owner's record from seat `a`, the
    measuring record from seat `b` (either may be None)."""
    out = []
    if owner is not None:
        out.append({"seat": a, "other": b, "rec": owner})
    if meas is not None:
        out.append({"seat": b, "other": a, "rec": meas})
    return out


# -- generated games (totals derived from the rebuild, for the bulk fixtures) -------

def cycle_group(s0, pid0, n, mag=3, *, side="s", step=200, reload_after=True):
    """One over-magazine cycle of `n` single-projectile volleys."""
    entries = []
    ammo = mag
    for j in range(n):
        rl = 1 if (reload_after and ammo <= 0) else 0
        counter = step * j if rl else NOT_RELOADING
        if side == "s":
            entries.append(own_shot(0 if j == 0 else 1, 0 if j == 0 else step, ammo, rl, counter,
                                    fl=FL["use_ammo"] | (FL["reloading"] if rl else 0)))
        else:
            entries.append(copy_shot(0 if j == 0 else 1, 0 if j == 0 else step, ammo, rl, counter))
        ammo -= 1
    return [hdr(s0, pid0, n, st_end=s0 + 1900), entries, []]


def finish(rec, side):
    """Totals and cycle summaries of one gun from the record's own groups,
    the way the client fills them (cycle summaries for the first 24 cycles
    whose reason bits are not zero; the rest counted in `omit`)."""
    cycles = cm.rebuild_side(rec, side)
    qual = [c for c in cycles if c["why"]]
    cap = SPEC["cx_" + side][1]
    rec["cx_" + side] = [cx(c["s0"], c["units"], c["vol"], c["mag"], c["regen"], c["exh"],
                            c["in_rl"], c["tail"], c["gaps"], c["rexp"], c["end"], c["why"])
                         for c in qual[:cap]]
    rec["omit"]["cx_" + side] = max(0, len(qual) - cap)
    firsts = [s for c in cycles for s in c["shots"] if s["first_of_emission"]]
    vals = dict(cycles=len(cycles), volleys=sum(c["vol"] for c in cycles),
                units=sum(c["units"] for c in cycles), sum_excess=sum(c["excess"] for c in cycles),
                cx_n=len(qual), cx_volleys=sum(c["vol"] for c in qual),
                cx_units=sum(c["units"] for c in qual),
                inits_rl=sum(c["in_rl"] for c in cycles))
    for name, bit in W["why"].items():
        vals["why_" + name] = sum(1 for c in cycles if c["why"] & bit)
    if side == "s":
        vals["emit"] = len(firsts)
        vals["gate"] = sum(1 for s in firsts if s["rep"] == 0)
    else:
        vals["atk_msg"] = len(firsts)
    gaps = [c["gaps"][0] - c["rexp"] for c in cycles if c["gaps"] and c["gaps"][0] >= 0]
    vals["gap_minus_rexp_min"] = min(gaps) if gaps else GAP_NONE
    rec["tot_" + side] = tot(**vals)
    return rec


def many_cycles(n_cycles, shots_per_cycle=4, side="s"):
    """One record whose gun (own when side "s", the copy when "o") fired
    `n_cycles` over-magazine cycles."""
    rec = empty_record()
    rec["tb"] = [point()]
    rec["tb_tot"] = tb_tot_of(rec["tb"])
    rec["gun_" + side] = [gun()]
    rec["sh_" + side] = [cycle_group(S0 + 10000 * i, PID0 + 100 * i, shots_per_cycle, side=side)
                         for i in range(n_cycles)]
    return finish(rec, side)


# -- the addendum sections (R1 push, R2 owner velocity changes, R3 hit chain, R5 deaths) --

CAPS_ALL = sum(W["caps"].values())
HIT = (9, 4100, 0)               # projectile id, init stamp, contact ordinal


def push_row(key="push_s", hit=HIT, tc=4300, fx_=-120000, fy_=35000, mass=20000,
             vb=(0, 0), va=(-600, 175), pb=(150000, -2000), pa=(149990, -1997)):
    return named_row(key, pid=hit[0], s_init=hit[1], cord=hit[2], tc=tc, fx=fx_, fy=fy_, mass=mass,
                     vbx=vb[0], vby=vb[1], vax=va[0], vay=va[1], pbx=pb[0], pby=pb[1],
                     pax=pa[0], pay=pa[1])


def r_sections_pair(variant="base"):
    """(victim, shooter) records with every addendum section filled. Seat A
    is hit by seat B's reflected projectile, is pushed, and dies at the left
    boundary; seat B's projectile retargeted once on a target bounce.

    Variants: `uncapped` the shooter's record did not fill the push and
    chain sections (its room lacked the capability); `pushed_more` the
    shooter's copy of the push carries a different force."""
    victim, shooter = empty_record(), empty_record()
    victim["caps"] = CAPS_ALL
    shooter["caps"] = CAPS_ALL if variant != "uncapped" else W["caps"]["vchg"] | W["caps"]["death"]
    victim["push_s"] = [push_row()]
    if variant != "uncapped":
        f = -150000 if variant == "pushed_more" else -120000
        shooter["push_o"] = [push_row("push_o", fx_=f)]
        shooter["ch_o"] = [named_row("ch_o", pid=HIT[0], s_init=HIT[1], cord=HIT[2], t_dec=4290,
                                     t_msg=4291, t_dmg=4292)]
    victim["ch_s"] = [named_row("ch_s", pid=HIT[0], s_init=HIT[1], cord=HIT[2], t_rcv=4340,
                                t_dmg_rcv=4341, t_hp=4358, t_frame=4375, hp_d=-25)]
    shooter["vchg"] = [named_row("vchg", pid=HIT[0], s_init=HIT[1], stamp=4200,
                                 cause=W["cause"]["surface"] | W["cause"]["retarget"],
                                 ovx=0, ovy=-8000, nvx=-8000, nvy=0)]
    shooter["bsel"] = [named_row("bsel", pid=HIT[0], s_init=HIT[1], stamp=4200,
                                 target=W["bounce_target"]["other"], d_self=900, los_self=1,
                                 d_other=1400, los_other=1)]
    # The victim's measured target bounce of the shooter's projectile: the
    # same event identity as the owner's selection (projectile id, init
    # stamp, the stamp the new velocity was sent under).
    victim["p3tb"] = [named_row("p3tb", pid=HIT[0], s_init=HIT[1], s_rel=4200, gap=110,
                                has_retarget=1, ang_to_me=40)]
    # Its whole-game count of measured target bounces, which the list matches.
    victim["p3n"][cm.IX["p3n"]["target"]] = len(victim["p3tb"])
    death = named_row("bd_s", ord=0, stamp=5100, cause=W["death_cause"]["out_of_bounds"],
                      edge=W["edge"]["left"], px=-4000, py=300, vx=-900, vy=50,
                      h1_pid=HIT[0], h1_s_init=HIT[1], h1_cord=HIT[2], h1_age=800,
                      h2_pid=-1, h2_cord=-1, h2_age=-1, h3_pid=-1, h3_cord=-1, h3_age=-1)
    victim["bd_s"] = [death]
    seen = list(death)
    seen[cm.IX["bd_s"]["px"]] = -3990
    shooter["bd_o"] = [seen]
    victim["r_tot"] = named_row("r_tot", push_own=1, chain_own=1, death_own=1)
    shooter["r_tot"] = named_row("r_tot", push_other=len(shooter["push_o"]), vchg=1, bsel=1,
                                 chain_other=len(shooter["ch_o"]), death_other=1)
    return victim, shooter


A1_FIXTURE_DIR = os.path.join(HERE, "fixtures", "combat_evidence_a1")
# The amended records the client lane committed at 5969a3b5 (its scenario run,
# both seats), carried byte for byte. They are REVISION 1 of the amendment
# (seven cost_a1 rows, no widened list), which a revision 2 server refuses;
# `rev2` builds the synthetic revision 2 records the tests read from them.
A1_FIXTURES = ("seat1.rec.txt", "seat2.rec.txt")


def widen(rec):
    """`rec`'s rows of the four widened lists given their revision 2 fields
    (in place, returned), each new field at its none value: no force stamp
    (-1) on a chain row, three empty force slots on a death row. A row
    already at its amended width is left as it is."""
    for key, extra in cm.WA["widened"]:
        base = len(cm.SPEC[key][3])
        none = (list(cm.FORCE_EMPTY) * cm.FORCE_SLOTS if key in cm.DEATH_LISTS
                else [cm.WA["chain_none"]] * len(extra))
        rec[key] = [list(r) + none if len(r) == base else list(r) for r in rec[key]]
    return rec


def rev2(rec):
    """A SYNTHETIC revision 2 record from a revision 1 one (a copy): the
    eighth cost_a1 row (G1, zero cost) appended and the widened lists'
    rows given their new fields at their none values."""
    out = json.loads(json.dumps(rec))
    if len(out[cm.COST_A1_KEY]) == cm.WA["cost_rows"] - 1:
        out[cm.COST_A1_KEY].append([0, 0, 0, 0])
    return widen(out)


def amend(rec, rx=True, **drop):
    """`rec` as an amended record (in place, returned): the amendment bit,
    the reaction bit when `rx`, the loss counters named in `drop` (others
    zero), totals that agree with the lists as they stand, zero added cost,
    and the widened lists' rows at their revision 2 width (`widen`)."""
    widen(rec)
    rec["caps"] |= cm.CAPS_AMEND | (cm.CAPS_RX if rx else 0)
    rec[cm.DROP_KEY] = [drop.pop(f, 0) for f in cm.DROP_FIELDS]
    assert not drop, drop
    totals = {f: 0 for f in cm.TOTAL_FIELDS}
    for key, field in cm.WA["counted"]:
        totals[field] = len(rec[key]) + rec["omit"][key]
    rec[cm.TOTAL_KEY] = [totals[f] for f in cm.TOTAL_FIELDS]
    rec[cm.COST_A1_KEY] = [[0, 0, 0, 0] for _i in range(cm.WA["cost_rows"])]
    return rec


def max_width_protected(n_groups=4):
    """A record whose never-trimmed part is at its widest (cm.max_width_record,
    omit counts left room to grow at the same width), with `n_groups`
    widest-possible protected cycle groups per gun: every group named by a
    kept cycle summary."""
    rec = cm.max_width_record()
    rec["omit"] = {k: 9990000 for k in cm.OMIT_KEYS}
    lo = SPEC["cx_s"][3][0][1]
    for side in ("s", "o"):
        for i, e in enumerate(rec["cx_" + side]):
            e[cm.CX["s0"]] = lo + i
        groups = []
        for i in range(n_groups):
            g = cm.max_width_group("sh_" + side)
            g[0][cm.HDR["s0"]] = lo + i
            # Each widest shot is a RELOADING one (the same width as 0): its
            # widest counter is then a reload counter, as the design requires
            # of any shot whose counter is not -1 (combat fix pass 5, F1).
            for e in g[1]:
                e[cm.SHOT[side]["reloading"]] = 1
            groups.append(g)
        rec["sh_" + side] = groups
    return rec


def over_cap_pair(n_cycles=25, shots=32):
    """(owner, measuring) records of one gun that fired `n_cycles`
    over-magazine cycles of `shots` volleys: both far over the record bound."""
    owner = many_cycles(n_cycles, shots, side="s")
    meas = many_cycles(n_cycles, shots, side="o")
    return owner, meas


INTEGRATOR_CASES = (
    ("straight", {"x": 1.5, "y": -2.25, "vx": 55.5, "vy": -3.25},
     [0.016, 0.017, 0.033, 0.016, 0.0167],
     {"gravity": 0.0, "drag": 0.0, "drag_min": 0.0, "mult": 1.0, "sim": 1.0, "allow_stop": False,
      "sim_gravity": 1}),
    ("drag", {"x": 0.0, "y": 0.0, "vx": 80.0, "vy": 12.5},
     [0.016, 0.017, 0.033, 0.016, 0.0167, 0.05, 0.016],
     {"gravity": 0.0, "drag": 0.7, "drag_min": 1.0, "mult": 1.0, "sim": 1.0, "allow_stop": False,
      "sim_gravity": 1}),
    ("gravity_drag_mult", {"x": -4.0, "y": 3.0, "vx": 40.0, "vy": 20.0},
     [0.016, 0.017, 0.033, 0.016, 0.0167, 0.05, 0.016],
     {"gravity": 30.0, "drag": 0.35, "drag_min": 1.0, "mult": 0.75, "sim": 1.25,
      "allow_stop": False, "sim_gravity": 0}),
)
TURN_PER_FRAME = 0.002

# The steering references' canonical cases. Homing: (name, state, target,
# frames, prm, sync_every); the frames mix lengths under and over the move
# step's clamp, and drag runs throughout. Target bounce: (name, state at the
# contact, surface normal, target or None, the measuring seat's position,
# frames after the contact, prm).
HOMING_PRM = {"gravity": 0.0, "drag": 0.35, "drag_min": 1.0, "mult": 1.0, "sim": 1.0,
              "allow_stop": False, "sim_gravity": 0, "amount": 1.0, "scaling_drag": 1.0,
              "h_drag": 1.0, "force": 55.0}
HOMING_FRAMES = [0.016, 0.017, 0.033, 0.016, 0.0167, 0.05, 0.016, 0.017, 0.016, 0.0167, 0.033,
                 0.016]
HOMING_CASES = (
    ("homing_in_cone", {"x": 0.0, "y": 0.0, "vx": 50.0, "vy": 5.0}, (20.0, 8.0),
     HOMING_FRAMES, HOMING_PRM, 3),
    ("homing_out_of_cone", {"x": 0.0, "y": 0.0, "vx": 50.0, "vy": 5.0}, (-20.0, 8.0),
     HOMING_FRAMES, HOMING_PRM, 3),
)
BOUNCE_PRM = {"gravity": 30.0, "speed_m": 1.0}
BOUNCE_FRAMES = [0.016, 0.017, 0.033, 0.016, 0.0167, 0.05, 0.016]
BOUNCE_CASES = (
    ("bounce_to_target", {"x": 0.0, "y": 0.0, "vx": 30.0, "vy": -40.0}, (0.0, 1.0), (12.0, 3.0),
     (12.0, 3.0), BOUNCE_FRAMES, BOUNCE_PRM),
    ("bounce_no_target", {"x": 0.0, "y": 0.0, "vx": 30.0, "vy": -40.0}, (0.0, 1.0), None,
     (12.0, 3.0), BOUNCE_FRAMES, BOUNCE_PRM),
)


def _hex_state(st):
    return {k: float.hex(cm.f32(st[k])) for k in ("x", "y", "vx", "vy")}


def steering_set():
    """The steering references' exact encoded outputs: per homing case the
    owner's sync packages and the encoded `p3ht` entry, beside the entry of
    the same trace with a turn the homing code does not make added each
    frame (the mutant); per target-bounce case the encoded `p3tb` fields and
    the new velocity, beside the same bounce sent without its wait."""
    out = {"homing": [], "bounce": []}
    for name, state, target, frames, prm, every in HOMING_CASES:
        packs = cm.homing_trace(state, target, frames, prm, every)
        turned = cm.homing_trace(state, target, frames, prm, every, TURN_PER_FRAME)
        out["homing"].append({
            "name": name, "state": state, "target": list(target), "frames": frames, "prm": prm,
            "sync_every": every,
            "packages": [[float.hex(t), _hex_state(st)] for t, st in packs],
            "entry": cm.homing_entry(1, 0, packs, prm),
            "turn_per_frame": TURN_PER_FRAME,
            "mutant_entry": cm.homing_entry(1, 0, turned, prm)})
    for name, state, normal, target, me, frames, prm in BOUNCE_CASES:
        got = cm.target_bounce(state, normal, target, me, frames, prm)
        early = cm.target_bounce(state, normal, target, me, frames, prm, wait_s=0.0)
        enc = {k: got[k] for k in ("gap", "has_retarget", "ang_to_me")}
        out["bounce"].append({
            "name": name, "state": state, "normal": list(normal),
            "target": list(target) if target is not None else None, "me": list(me),
            "frames": frames, "prm": prm, "entry": enc,
            "velocity": {"vx": float.hex(got["vx"]), "vy": float.hex(got["vy"])},
            "mutant_entry": {k: early[k] for k in ("gap", "has_retarget", "ang_to_me")}})
    return out


def integrator_set():
    """The reference integrator's exact outputs (single-precision values as
    float.hex) and the encoded residual of the unchanged control and of the
    turn mutant against the unsteered prediction."""
    out = []
    for name, state, frames, prm in INTEGRATOR_CASES:
        pred = cm.integrate(state, frames, prm)
        control = cm.trace(state, frames, prm)
        mutant = cm.trace(state, frames, prm, TURN_PER_FRAME)
        out.append({"name": name, "state": state, "frames": frames, "prm": prm,
                    "pred": {k: float.hex(v) for k, v in pred.items()},
                    "control_residual": cm.residual(pred, control),
                    "turn_per_frame": TURN_PER_FRAME,
                    "mutant_residual": cm.residual(pred, mutant)})
    return out


def sign_set():
    """Signing canonical and signature of fixed envelopes (the client signs
    the same canonical under the same key)."""
    out = []
    for stable, rounds, text in (("ranked_cev_000001", 8, cm.budget_record(a24_pair()[0])),
                                 ("room_cev_sign_0002", 13, cm.budget_record(empty_record()))):
        env = {"seat": SEAT_A, "other": SEAT_B, "stable": stable,
               "attach": "%s_r%d" % (stable, rounds), "record_text": text,
               "record_bytes": text.encode("ascii")}
        out.append({"seat": SEAT_A, "other": SEAT_B, "stable": stable, "attach": env["attach"],
                    "record_sha256": hashlib.sha256(env["record_bytes"]).hexdigest(),
                    "key": KEY, "canonical": ce.record_canonical(env),
                    "sig": ce.record_sign(KEY, env)})
    return out


def budget_inputs():
    """Name -> unbudgeted record: the budgeter's canonical inputs."""
    a24o, a24m = a24_pair()
    rgo, _rgm = a24_pair("regen")
    oco, ocm = over_cap_pair()
    rv, rsh = r_sections_pair()
    return {"a24_owner": a24o, "a24_meas": a24m, "a24_regen_owner": rgo, "empty": empty_record(),
            "r_sections_victim": rv, "r_sections_shooter": rsh,
            "m6_25_cycles": many_cycles(25), "over_cap_owner": oco, "over_cap_meas": ocm,
            "max_width_protected": max_width_protected()}


def canonical_set():
    """File name -> bytes of the whole canonical fixture set under
    fixtures/combat_evidence: per budget input its record (.in.json, the
    layout's key order, no whitespace) and the budgeter's output (.out.txt);
    the signing set; the integrator set."""
    files = {}
    for name, rec in budget_inputs().items():
        files[name + ".in.json"] = cm.dumps(rec).encode("ascii")
        files[name + ".out.txt"] = cm.budget_record(rec).encode("ascii")
    files["sign.json"] = (json.dumps(sign_set(), indent=1, sort_keys=True) + "\n").encode("ascii")
    files["integrator.json"] = (json.dumps(integrator_set(), indent=1, sort_keys=True)
                                + "\n").encode("ascii")
    files["byte_proof.json"] = (json.dumps(cm.byte_proof(), indent=1, sort_keys=True)
                                + "\n").encode("ascii")
    files["steering.json"] = (json.dumps(steering_set(), indent=1, sort_keys=True)
                              + "\n").encode("ascii")
    return files


def validate_dir(path):
    """The on-disk byte-identity check of a canonical fixture directory:
    the names of every file that is missing, extra or not byte-identical to
    the generator's output (empty when the directory is canonical). Each
    budget input is also re-budgeted from the bytes on disk and compared with
    its output file on disk."""
    files = canonical_set()
    bad = set()
    names = set(os.listdir(path))
    bad |= names ^ set(files)
    for name, data in files.items():
        if name not in names:
            continue
        with open(os.path.join(path, name), "rb") as f:
            if f.read() != data:
                bad.add(name)
        if name.endswith(".in.json"):
            out_name = name[:-len(".in.json")] + ".out.txt"
            try:
                with open(os.path.join(path, name), "rb") as f:
                    rec = json.loads(f.read().decode("ascii"))
                with open(os.path.join(path, out_name), "rb") as f:
                    if cm.budget_record(rec).encode("ascii") != f.read():
                        bad.add(out_name)
            except (OSError, ValueError, KeyError, TypeError, cm.Refusal):
                bad.add(name)
    return sorted(bad)


def write_canonical():
    os.makedirs(FIXTURE_DIR, exist_ok=True)
    for name, data in canonical_set().items():
        with open(os.path.join(FIXTURE_DIR, name), "wb") as f:
            f.write(data)


# -- envelopes --------------------------------------------------------------------

def envelope(rec, *, seat=SEAT_A, other=SEAT_B, stable="ranked_cev_000001", rounds=8, key=KEY,
             text=None):
    record_text = text if text is not None else cm.budget_record(rec)
    env = {"seat": seat, "other": other, "stable": stable, "attach": "%s_r%d" % (stable, rounds),
           "record_text": record_text, "record_bytes": record_text.encode("ascii")}
    return {"contract": W["contract"], "seat_steam_id": seat, "other_steam_id": other,
            "stable_game_key": stable, "attach_key": env["attach"], "record": record_text,
            "sig": ce.record_sign(key, env)}


def clone(rec):
    return json.loads(json.dumps(rec))


if __name__ == "__main__":
    write_canonical()
