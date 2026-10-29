"""Public vocabulary for the identity, clock and connection evidence record.

Descriptive measures only. Each one says what a stored record (or two, of one
game and one seat pair) states or what the server measured: a count, a stated
build against a registry, a stamp difference, a clock rate fitted against the
api's own receive clock, the connection class the api stored. None of them
opens anything. Whether a measure becomes a review item, at which value, over
which window, with which minimum sample and with which words is decided only
by a rule in the private rules revision (review_rules); every such value
reaches a measure as a parameter of that revision, never from this file.

Provenance, per measure family (never merged):
  SELF-STATED          the recording seat about itself (check runs, survey,
                       digests, owners, its own per point timings, its send
                       configuration);
  OTHER-SEAT-MEASURED  the recording seat about the other seat, from the other
                       seat's own messages (cadence, stated intervals, game
                       clock, per point arrival, call names);
  SERVER-OBSERVED      what the api saw at the post (the version header, the
                       connection class);
  SERVER-MEASURED      the clock fit of a seat's readings against the api's
                       receive clock across that seat's own posts.

A check run that threw is `not_run` and is counted as such; no measure here
infers a passing check from anything else (capability keys included).

Field order of every positional wire list lives in ICM_FIELDS; the wire
checks (identity_clock_evidence) read the same names.
"""

from __future__ import annotations

from fractions import Fraction

import review_measures as rm

# Unit scales and enumerations of the public wire (pinned by value in the
# review guard): units are conversions, codes are the wire's own words.
ICM_UNITS = {"ppm": 1000000, "cppm": 100, "s_ms": 1000}
ICM_CODES = {"pass": 0, "finding": 1, "not_run": 2,
             "ok": 0, "no_file": 1, "read_failed": 2, "not_yet": 3,
             "origin_game": 0, "origin_core": 1, "origin_plugins": 2, "origin_patchers": 3,
             "origin_other": 4, "origin_none": 5, "origin_unreadable": 6,
             "boot": 0, "start": 1, "pick": 2, "over": 3,
             "unknown": -1}
# The game's own move rules (decompiled game code, a fact of the game): each
# frame advances the move by at most this step, and the body is held at the
# target for this many frames before release.
ICM_GAME = {"move_step_ms": 20, "hold_frames": 10}

ICM_FIELDS = {
    "proc": ("proc_id", "boots", "runs", "findings", "not_run"),
    "chk": ("moment", "ordinal", "t_ms", "outcome", "n_plugins", "n_asm", "n_foreign"),
    "asm_n": ("total", "dynamic", "added", "removed"),
    "asm": ("name", "version", "origin"),
    "gdig": ("file_id", "sha256", "state", "size"),
    "aload": ("loaded_origin", "mvid_loaded", "disk_state", "mvid_disk"),
    "ldir_part": ("state", "files", "truncated", "list"),
    "ldir_entry": ("name", "sha256"),
    "hp_all": ("patched", "owners_n", "owners"),
    "hp": ("method_id", "prefix", "postfix", "transpiler", "finalizer", "owners"),
    "rpc_o": ("name", "n"),
    "send_cfg": ("send_start", "ser_start", "send_end", "ser_end", "changes"),
    "gclk": ("rate_cppm", "pairs", "span_ms"),
    "tdg": ("n", "sat", "bins"),
    "cad_b": ("bucket", "batches", "gap_med_ms", "td_med_ms", "td_sat"),
    "pt_s": ("pt", "ps", "ps_age", "map_wait", "rel", "mv_frames", "mv_ft_max_us", "mv_t",
             "in_first", "shot_first", "th_ms", "wall_ms"),
    "pt_o": ("pt", "ps", "ps_age", "tgt", "dist_start", "inpos", "inpos_arr", "n_pk", "gap_max",
             "td_max", "td_sat", "in_first", "in_first_arr", "move_first", "move_first_arr",
             "aim_first", "shot_first", "shot_first_arr", "end", "pub_fps"),
    "unpair": ("no_stamp", "over_cap"),
    "cost": ("collector", "calls", "faults", "us_total", "us_max"),
}

ICM_SUBJECTS = ("ic.seat", "ic.point")
ICM_CLOCKS = ("sw", "unity", "photon")


def icm_named(kind, entry) -> dict:
    """One positional wire entry as a dict of its field names."""
    return dict(zip(ICM_FIELDS[kind], entry))


def icm_known(v):
    """A non-negative wire field, or None where the wire states unknown."""
    if v is None or v < 0:
        return None
    return v


# -- the clock fit (SERVER-MEASURED) --------------------------------------------

def icm_unwrap(raw: list) -> list:
    """Photon server stamps (wrapping signed int) as a running unwrapped series."""
    if not raw:
        return []
    out = [raw[0]]
    for prev, cur in zip(raw, raw[1:]):
        out.append(out[-1] + rm.wrap_diff(cur, prev))
    return out


def icm_fit(xs: list, ys: list):
    """Least squares of a seat's readings `ys` against the api's receive times
    `xs` (both milliseconds). Returns (rate_ppm, err_ppm, points, span_ms) with
    rate the slope minus one in parts per million and err the residual spread
    over the span in the same unit; None when the points cannot define a slope
    (fewer than two, or no span)."""
    n = len(xs)
    if not xs[1:] or len(ys) != n:
        return None
    x0, y0 = xs[0], ys[0]
    dx = [x - x0 for x in xs]
    dy = [y - y0 for y in ys]
    span = max(dx) - min(dx)
    sx, sy = sum(dx), sum(dy)
    sxx = sum(x * x for x in dx)
    sxy = sum(x * y for x, y in zip(dx, dy))
    den = n * sxx - sx * sx
    if span <= 0 or den == 0:
        return None
    slope = Fraction(n * sxy - sx * sy, den)
    icpt = Fraction(sy, n) - slope * Fraction(sx, n)
    res = [y - (icpt + slope * x) for x, y in zip(dx, dy)]
    ppm = ICM_UNITS["ppm"]
    rate = float((slope - 1) * ppm)
    err = float((max(res) - min(res)) / span * ppm)
    return rate, err, n, span


def icm_fit_all(samples: list) -> dict:
    """samples: [(received_ms, sw_ms, unity_ms, photon_ts)] of one seat process,
    in receive order. One fit per clock."""
    xs = [s[0] for s in samples]
    cols = list(zip(*[s[1:] for s in samples])) if samples else [[], [], []]
    sw, unity, photon = (list(c) for c in cols)
    return {"sw": icm_fit(xs, sw), "unity": icm_fit(xs, unity),
            "photon": icm_fit(xs, icm_unwrap(photon))}


# -- subjects -------------------------------------------------------------------

class IcCtx:
    """One subject: a seat record (`r`, `other`) or one point (`own`, `seen`).
    `i` is the memo key, unique within one evaluation."""

    __slots__ = ("i", "r", "other", "regs", "own", "seen", "seat")

    def __init__(self, i, r=None, other=None, regs=None, own=None, seen=None, seat=None):
        self.i = i
        self.r = r
        self.other = other
        self.regs = regs
        self.own = own
        self.seen = seen
        self.seat = seat


def icm_points_by_ps(rec, kind) -> dict:
    """The point entries of one list keyed by point-start stamp; a stamp that
    occurs twice is ambiguous and keyed to None (never paired)."""
    out = {}
    for e in rec.get(kind) or []:
        d = icm_named(kind, e)
        out[d["ps"]] = None if d["ps"] in out else d
    return out


def icm_subjects(records: list, regs: dict) -> dict:
    """The subject rows one evaluation ranges over. A point row is about one
    seat: its own statement (`own`, from its pt_s) beside the other seat's
    observation of it (`seen`, from the other record's pt_o) at the same
    point-start stamp. With one record, the rows hold only what that record
    has (the other seat's own statements are unavailable)."""
    by_seat = {r["seat"]: r for r in records}
    seats, points = [], []
    for idx, r in enumerate(records):
        other = by_seat.get(r["other"])
        seats.append(IcCtx(("seat", idx), r=r, other=other, regs=regs, seat=idx))
    for idx, r in enumerate(records):
        own = icm_points_by_ps(r["rec"], "pt_s")
        other = by_seat.get(r["other"])
        seen = icm_points_by_ps(other["rec"], "pt_o") if other is not None else {}
        for ps in sorted(set(own) | set(seen)):
            o, s = own.get(ps), seen.get(ps)
            if o is None and s is None:
                continue
            points.append(IcCtx(("point", idx, ps), own=o, seen=s, regs=regs, seat=idx))
    for idx, r in enumerate(records):
        if r["other"] in by_seat:
            continue
        for ps, d in sorted(icm_points_by_ps(r["rec"], "pt_o").items()):
            if d is None:
                continue
            points.append(IcCtx(("about_other", idx, ps), own=None, seen=d, regs=regs,
                                seat=None))
    return {"ic.seat": seats, "ic.point": points}


def icm_pair_view(records: list, regs: dict) -> dict:
    """What the admin read and the worker's pairing count show: per seat the
    point rows, own and seen side by side, with the paired differences each
    pair measure computes at the reference rung the record itself carries
    first (rung choice for review is a parameter of the revision)."""
    subj = icm_subjects(records, regs)
    rows = []
    for ctx in subj["ic.point"]:
        rows.append({"seat": ctx.seat, "ps": (ctx.own or ctx.seen or {}).get("ps"),
                     "own": ctx.own, "seen": ctx.seen,
                     "paired": ctx.own is not None and ctx.seen is not None})
    return {"points": rows, "paired": sum(1 for r in rows if r["paired"]),
            "seats": len(subj["ic.seat"])}


# -- seat measures (SELF-STATED unless named otherwise) ------------------------

def _seat(name, family=None):
    return rm.measure("ic.seat." + name, "ic.seat", family)


def _chk(ctx):
    return [icm_named("chk", e) for e in ctx.r["rec"]["chk"]]


@_seat("index")
def icm_seat_index(ctx, p):
    return ctx.seat


@_seat("record_conflict")
def icm_seat_conflict(ctx, p):
    return bool(ctx.r["conflict"])


@_seat("build_registered")
def icm_seat_build_registered(ctx, p):
    """The seat record's stated tuple (version, variant, commit, dll digest)
    against the registered release set; unknown without a seat record."""
    b = ctx.r.get("seat_build")
    return None if b is None else tuple(b) in ctx.regs["release"]


@_seat("build_source")
def icm_seat_build_source(ctx, p):
    """The registry source (`release` or `beta`) the stated tuple was
    registered under; unknown without a seat record or an unregistered tuple."""
    b = ctx.r.get("seat_build")
    return None if b is None else ctx.regs["release"].get(tuple(b))


@_seat("build_header_match")
def icm_seat_header_match(ctx, p):
    """SERVER-OBSERVED header against the stated build version (both are the
    seat's own statements); unknown when either is missing."""
    b, hv = ctx.r.get("seat_build"), ctx.r.get("header_version")
    return None if b is None or hv is None else hv == b[0]


@_seat("build_relayed_match")
def icm_seat_relayed_match(ctx, p):
    """The build the OTHER seat relayed for this seat (its own property, a
    second channel) against this seat's stated tuple; unknown without both."""
    b, rel = ctx.r.get("seat_build"), ctx.r.get("relayed_build")
    if b is None or not rel:
        return None
    return rel == "|".join(b[:-1])


@_seat("chk_runs")
def icm_chk_runs(ctx, p):
    return len(_chk(ctx))


@_seat("chk_findings")
def icm_chk_findings(ctx, p):
    return sum(1 for e in _chk(ctx) if e["outcome"] == ICM_CODES["finding"])


@_seat("chk_not_run")
def icm_chk_not_run(ctx, p):
    return sum(1 for e in _chk(ctx) if e["outcome"] == ICM_CODES["not_run"])


@_seat("chk_boots")
def icm_chk_boots(ctx, p):
    return sum(1 for e in _chk(ctx) if e["moment"] == ICM_CODES["boot"])


@_seat("chk_first_change_moment")
def icm_chk_first_change(ctx, p):
    """The moment of the first run whose outcome differs from the run before
    it, in recorded order; unknown when no outcome changed."""
    runs = _chk(ctx)
    for prev, cur in zip(runs, runs[1:]):
        if cur["outcome"] != prev["outcome"]:
            return cur["moment"]
    return None


@_seat("proc_not_run_total")
def icm_proc_not_run(ctx, p):
    return icm_named("proc", ctx.r["rec"]["proc"])["not_run"]


@_seat("proc_findings_total")
def icm_proc_findings(ctx, p):
    return icm_named("proc", ctx.r["rec"]["proc"])["findings"]


@_seat("plug_count")
def icm_plug_count(ctx, p):
    return len(ctx.r["rec"]["plug"])


@_seat("plug_names")
def icm_plug_names(ctx, p):
    return sorted(ctx.r["rec"]["plug"])


@_seat("asm_total")
def icm_asm_total(ctx, p):
    return icm_named("asm_n", ctx.r["rec"]["asm_n"])["total"]


@_seat("asm_dynamic")
def icm_asm_dynamic(ctx, p):
    return icm_named("asm_n", ctx.r["rec"]["asm_n"])["dynamic"]


@_seat("asm_added")
def icm_asm_added(ctx, p):
    return icm_named("asm_n", ctx.r["rec"]["asm_n"])["added"]


@_seat("asm_removed")
def icm_asm_removed(ctx, p):
    return icm_named("asm_n", ctx.r["rec"]["asm_n"])["removed"]


def _origin_count(ctx, code):
    if ctx.r["rec"].get("asm") is None:
        return None
    return sum(1 for e in ctx.r["rec"]["asm"] if icm_named("asm", e)["origin"] == code)


@_seat("asm_origin_other")
def icm_asm_origin_other(ctx, p):
    return _origin_count(ctx, ICM_CODES["origin_other"])


@_seat("asm_origin_none")
def icm_asm_origin_none(ctx, p):
    return _origin_count(ctx, ICM_CODES["origin_none"])


@_seat("asm_origin_unreadable")
def icm_asm_origin_unreadable(ctx, p):
    return _origin_count(ctx, ICM_CODES["origin_unreadable"])


@_seat("asm_names")
def icm_asm_names(ctx, p):
    if ctx.r["rec"].get("asm") is None:
        return None
    return sorted({icm_named("asm", e)["name"] for e in ctx.r["rec"]["asm"]})


@_seat("asm_omitted")
def icm_asm_omitted(ctx, p):
    return ctx.r["rec"]["omit"]["asm"]


def _gdig(ctx):
    return [icm_named("gdig", e) for e in ctx.r["rec"]["gdig"]]


@_seat("gdig_listed")
def icm_gdig_listed(ctx, p):
    return len(_gdig(ctx))


@_seat("gdig_ok")
def icm_gdig_ok(ctx, p):
    return sum(1 for e in _gdig(ctx) if e["state"] == ICM_CODES["ok"])


@_seat("gdig_not_ok")
def icm_gdig_not_ok(ctx, p):
    return sum(1 for e in _gdig(ctx) if e["state"] != ICM_CODES["ok"])


@_seat("gdig_unregistered")
def icm_gdig_unregistered(ctx, p):
    """Digests read (state ok) whose (file id, digest) pair is in no row of the
    game-file registry. Which registry rows count for a review is private."""
    return sum(1 for e in _gdig(ctx) if e["state"] == ICM_CODES["ok"]
               and (e["file_id"], e["sha256"]) not in ctx.regs["game_files"])


@_seat("aload_disk_state")
def icm_aload_disk_state(ctx, p):
    return icm_named("aload", ctx.r["rec"]["aload"])["disk_state"]


@_seat("aload_mvid_differs")
def icm_aload_mvid_differs(ctx, p):
    """The loaded module's version id against the one read from disk; unknown
    unless the disk read completed and the loaded id was read."""
    a = icm_named("aload", ctx.r["rec"]["aload"])
    if a["disk_state"] != ICM_CODES["ok"] or not a["mvid_loaded"]:
        return None
    return a["mvid_loaded"] != a["mvid_disk"]


def _ldir(ctx, part):
    if ctx.r["rec"].get("ldir") is None:
        return None
    return icm_named("ldir_part", ctx.r["rec"]["ldir"][part])


@_seat("ldir_plugins_state")
def icm_ldir_plugins_state(ctx, p):
    d = _ldir(ctx, "plugins")
    return None if d is None else d["state"]


@_seat("ldir_plugins_files")
def icm_ldir_plugins_files(ctx, p):
    """The file count of a completed survey; unknown for any other state, so an
    incomplete survey never reads as an empty folder."""
    d = _ldir(ctx, "plugins")
    return None if d is None or d["state"] != ICM_CODES["ok"] else d["files"]


@_seat("ldir_patchers_state")
def icm_ldir_patchers_state(ctx, p):
    d = _ldir(ctx, "patchers")
    return None if d is None else d["state"]


@_seat("ldir_patchers_files")
def icm_ldir_patchers_files(ctx, p):
    d = _ldir(ctx, "patchers")
    return None if d is None or d["state"] != ICM_CODES["ok"] else d["files"]


@_seat("ldir_truncated")
def icm_ldir_truncated(ctx, p):
    a, b = _ldir(ctx, "plugins"), _ldir(ctx, "patchers")
    if a is None or b is None:
        return None
    return bool(a["truncated"] or b["truncated"])


@_seat("hp_foreign_methods")
def icm_hp_foreign(ctx, p):
    if ctx.r["rec"].get("hp") is None:
        return None
    return sum(1 for e in ctx.r["rec"]["hp"] if icm_named("hp", e)["owners"])


@_seat("hp_owner_names")
def icm_hp_owner_names(ctx, p):
    if ctx.r["rec"].get("hp") is None:
        return None
    return sorted({o for e in ctx.r["rec"]["hp"] for o in icm_named("hp", e)["owners"]})


@_seat("hp_all_patched")
def icm_hp_all_patched(ctx, p):
    return icm_named("hp_all", ctx.r["rec"]["hp_all"])["patched"]


@_seat("hp_all_owner_names")
def icm_hp_all_owner_names(ctx, p):
    return sorted(icm_named("hp_all", ctx.r["rec"]["hp_all"])["owners"])


@_seat("rpc_names")
def icm_rpc_names(ctx, p):
    """OTHER-SEAT-MEASURED: the call names this seat received from the other
    seat (a statement about the other seat's sending code's behaviour)."""
    if ctx.r["rec"].get("rpc_o") is None:
        return None
    return sorted({icm_named("rpc_o", e)["name"] for e in ctx.r["rec"]["rpc_o"]})


@_seat("rpc_total")
def icm_rpc_total(ctx, p):
    if ctx.r["rec"].get("rpc_o") is None:
        return None
    return sum(icm_named("rpc_o", e)["n"] for e in ctx.r["rec"]["rpc_o"])


@_seat("send_cfg_changes")
def icm_send_cfg_changes(ctx, p):
    return icm_named("send_cfg", ctx.r["rec"]["send_cfg"])["changes"]


@_seat("ser_rate_start")
def icm_ser_rate_start(ctx, p):
    return icm_named("send_cfg", ctx.r["rec"]["send_cfg"])["ser_start"]


@_seat("ser_rate_end")
def icm_ser_rate_end(ctx, p):
    return icm_named("send_cfg", ctx.r["rec"]["send_cfg"])["ser_end"]


def _gclk(ctx):
    g = icm_named("gclk", ctx.r["rec"]["gclk"])
    return None if g["pairs"] == 0 else g


@_seat("gclk_rate_ppm")
def icm_gclk_rate(ctx, p):
    """OTHER-SEAT-MEASURED: the other seat's stated game time against this
    seat's own stopwatch over moving packages, parts per million."""
    g = _gclk(ctx)
    return None if g is None else g["rate_cppm"] / ICM_UNITS["cppm"]


@_seat("gclk_pairs")
def icm_gclk_pairs(ctx, p):
    return icm_named("gclk", ctx.r["rec"]["gclk"])["pairs"]


@_seat("gclk_span_ms")
def icm_gclk_span(ctx, p):
    return icm_named("gclk", ctx.r["rec"]["gclk"])["span_ms"]


@_seat("tdg_n")
def icm_tdg_n(ctx, p):
    return icm_named("tdg", ctx.r["rec"]["tdg"])["n"]


@_seat("tdg_sat")
def icm_tdg_sat(ctx, p):
    return icm_named("tdg", ctx.r["rec"]["tdg"])["sat"]


rm._param_family("params.ic_tdg", ("cut_bin",))
rm._param_family("params.ic_cad", ("window",))
rm._param_family("params.ic_fit", ("min_points", "min_span_ms"))
rm._param_family("params.ic_point", ("rung",))


@_seat("tdg_unexplained_share", "params.ic_tdg")
def icm_tdg_unexplained(ctx, p):
    """OTHER-SEAT-MEASURED: the share of packages whose stamp gap minus their
    stated interval falls at or above the revision's cut bin (gap the sender's
    own interval does not explain); unknown with no packages."""
    t = icm_named("tdg", ctx.r["rec"]["tdg"])
    total = sum(t["bins"])
    if total == 0:
        return None
    cut = int(p["cut_bin"])
    return sum(t["bins"][cut:]) / total


@_seat("cad_step_ratio", "params.ic_cad")
def icm_cad_step_ratio(ctx, p):
    s = icm_cad_step(ctx, p)
    return None if s is None else s[1]


@_seat("cad_step_bucket", "params.ic_cad")
def icm_cad_step_bucket(ctx, p):
    s = icm_cad_step(ctx, p)
    return None if s is None else s[0]


def icm_cad_step(ctx, p):
    """OTHER-SEAT-MEASURED: the largest ratio between the median of bucket
    median gaps in the window before a bucket and in the window from it, and
    the bucket where it occurs; unknown without two full windows."""
    if ctx.r["rec"].get("cad_b") is None:
        return None
    w = int(p["window"])
    rows = [icm_named("cad_b", e) for e in ctx.r["rec"]["cad_b"]]
    gaps = [(r["bucket"], r["gap_med_ms"]) for r in rows if r["gap_med_ms"] > 0]
    best = None
    for k in range(w, len(gaps) - w + 1):
        a = rm.median([g for _b, g in gaps[k - w:k]])
        b = rm.median([g for _b, g in gaps[k:k + w]])
        if not a or not b:
            continue
        ratio = max(a, b) / min(a, b)
        if best is None or ratio > best[1]:
            best = (gaps[k][0], ratio)
    return best


def _fit(ctx, clock):
    f = (ctx.r.get("fit") or {}).get(clock)
    return f


def _fit_gated(ctx, clock, p):
    f = _fit(ctx, clock)
    if f is None or f[2] < p["min_points"] or f[3] < p["min_span_ms"]:
        return None
    return f


def _fit_measures(clock):
    @_seat("fit_%s_ppm" % clock, "params.ic_fit")
    def rate(ctx, p):
        f = _fit_gated(ctx, clock, p)
        return None if f is None else f[0]

    @_seat("fit_%s_err_ppm" % clock, "params.ic_fit")
    def err(ctx, p):
        f = _fit_gated(ctx, clock, p)
        return None if f is None else f[1]

    @_seat("fit_%s_points" % clock)
    def points(ctx, p):
        f = _fit(ctx, clock)
        return None if f is None else f[2]

    @_seat("fit_%s_span_ms" % clock)
    def span(ctx, p):
        f = _fit(ctx, clock)
        return None if f is None else f[3]

    return rate, err, points, span


ICM_FIT_ENTRIES = tuple(_fit_measures(c) for c in ICM_CLOCKS)


@_seat("chain_other_game_ppm", "params.ic_fit")
def icm_chain_other_game(ctx, p):
    """The other seat's game clock against server time, without the other
    seat's own readings: this record's measurement of the other seat's game
    clock against this seat's stopwatch, composed with this seat's
    stopwatch against the api's clock (SERVER-MEASURED)."""
    g, f = _gclk(ctx), _fit_gated(ctx, "sw", p)
    if g is None or f is None:
        return None
    ppm = ICM_UNITS["ppm"]
    a = Fraction(g["rate_cppm"], ICM_UNITS["cppm"]) / ppm
    b = Fraction(f[0]) / ppm
    return float(((1 + a) * (1 + b) - 1) * ppm)


@_seat("post_clock")
def icm_post_clock(ctx, p):
    """SERVER-OBSERVED: the state of the clock header at the first post of
    this record (ok, absent, malformed, other_proc)."""
    return ctx.r.get("post_clock")


@_seat("conn_class")
def icm_conn_class(ctx, p):
    """SERVER-OBSERVED: the class of the api path at the evidence post, from
    the offline range list (a note for a reviewer, never a decision)."""
    return ctx.r.get("conn_class")


@_seat("conn_ranges")
def icm_conn_ranges(ctx, p):
    return ctx.r.get("conn_ranges")


@_seat("points_unpaired")
def icm_points_unpaired(ctx, p):
    return icm_named("unpair", ctx.r["rec"]["unpair"])["no_stamp"]


@_seat("points_over_cap")
def icm_points_over_cap(ctx, p):
    return icm_named("unpair", ctx.r["rec"]["unpair"])["over_cap"]


@_seat("cost_faults")
def icm_cost_faults(ctx, p):
    return sum(icm_named("cost", e)["faults"] for e in ctx.r["rec"]["cost"])


@_seat("omitted")
def icm_omitted(ctx, p):
    return sum(ctx.r["rec"]["omit"].values())


# -- point measures --------------------------------------------------------------

def _pt(name, family=None):
    return rm.measure("ic.point." + name, "ic.point", family)


def icm_rung(seen, p):
    """The other seat's in-position stamp at the revision's rung; unknown when
    the rung is outside the recorded ladder or was not met."""
    if seen is None:
        return None
    rung = int(p["rung"])
    if rung < 0 or rung >= len(seen["inpos"]):
        return None
    return icm_known(seen["inpos"][rung])


def _own_at_ps(own, field):
    """A self-stated elapsed time on the stamp origin of the point start: the
    seat's own receipt age of the point start plus the elapsed time it states
    from its own execution of that start."""
    if own is None:
        return None
    v = icm_known(own[field])
    return None if v is None else own["ps_age"] + v


def _diff(a, b):
    return None if a is None or b is None else a - b


@_pt("seat")
def icm_pt_seat(ctx, p):
    return ctx.seat


@_pt("index")
def icm_pt_index(ctx, p):
    return (ctx.own or ctx.seen)["pt"]


@_pt("paired")
def icm_pt_paired(ctx, p):
    return ctx.own is not None and ctx.seen is not None


@_pt("release_seen_minus_stated", "params.ic_point")
def icm_pt_release_pair(ctx, p):
    """In position as the other seat saw it against release as this seat
    states it, both on the point-start origin."""
    return _diff(icm_rung(ctx.seen, p), _own_at_ps(ctx.own, "rel"))


@_pt("input_seen_minus_stated")
def icm_pt_input_pair(ctx, p):
    return _diff(None if ctx.seen is None else icm_known(ctx.seen["in_first"]),
                 _own_at_ps(ctx.own, "in_first"))


@_pt("shot_seen_minus_stated")
def icm_pt_shot_pair(ctx, p):
    return _diff(None if ctx.seen is None else icm_known(ctx.seen["shot_first"]),
                 _own_at_ps(ctx.own, "shot_first"))


@_pt("inpos_expected")
def icm_pt_inpos_expected(ctx, p):
    """The on-time expectation for this seat's arrival: its own receipt age of
    the point start, plus the move the game runs at this seat's frame
    interval (the curve duration this seat states, stretched when a frame is
    longer than the game's per-frame step) plus the hold frames. The frame
    interval is the frame rate this seat published (relayed); with none
    published the expectation is unknown (a serialization interval is never
    used as a frame interval)."""
    if ctx.own is None or ctx.seen is None:
        return None
    fps, mv = icm_known(ctx.seen["pub_fps"]), icm_known(ctx.own["mv_t"])
    if not fps or mv is None:
        return None
    frame = Fraction(ICM_UNITS["s_ms"], fps)
    step = ICM_GAME["move_step_ms"]
    frames = -(-mv // step)
    move = max(Fraction(mv), frames * frame)
    return float(ctx.own["ps_age"] + move + ICM_GAME["hold_frames"] * frame)


@_pt("inpos_late", "params.ic_point")
def icm_pt_inpos_late(ctx, p):
    exp = icm_pt_inpos_expected(ctx, p)
    seen = icm_rung(ctx.seen, p)
    return None if exp is None or seen is None else seen - exp


@_pt("input_after_inpos", "params.ic_point")
def icm_pt_still(ctx, p):
    """OTHER-SEAT-MEASURED, sender clock: first input after in position."""
    if ctx.seen is None:
        return None
    return _diff(icm_known(ctx.seen["in_first"]), icm_rung(ctx.seen, p))


@_pt("move_after_inpos", "params.ic_point")
def icm_pt_move_still(ctx, p):
    """OTHER-SEAT-MEASURED, sender clock: first observed movement after in
    position (movement, not input: input held into a wall does not move)."""
    if ctx.seen is None:
        return None
    return _diff(icm_known(ctx.seen["move_first"]), icm_rung(ctx.seen, p))


def _seen_field(name):
    @_pt("seen_" + name)
    def f(ctx, p):
        return None if ctx.seen is None else icm_known(ctx.seen[name])
    return f


def _own_field(name):
    @_pt("own_" + name)
    def f(ctx, p):
        return None if ctx.own is None else icm_known(ctx.own[name])
    return f


ICM_SEEN_ENTRIES = tuple(_seen_field(n) for n in (
    "aim_first", "shot_first", "in_first", "move_first", "td_max", "td_sat", "gap_max", "n_pk",
    "dist_start", "pub_fps"))
ICM_OWN_ENTRIES = tuple(_own_field(n) for n in (
    "map_wait", "rel", "mv_frames", "mv_ft_max_us", "mv_t"))


@_pt("seen_ps_age")
def icm_pt_seen_ps_age(ctx, p):
    return None if ctx.seen is None else ctx.seen["ps_age"]


@_pt("own_ps_age")
def icm_pt_own_ps_age(ctx, p):
    return None if ctx.own is None else ctx.own["ps_age"]


@_pt("input_arrival_lag")
def icm_pt_input_arrival(ctx, p):
    """OTHER-SEAT-MEASURED: arrival of the first input against its sender
    stamp, both from the point start (mixes the two seats' clocks)."""
    if ctx.seen is None:
        return None
    return _diff(icm_known(ctx.seen["in_first_arr"]), icm_known(ctx.seen["in_first"]))


@_pt("wall_minus_game")
def icm_pt_wall_minus_game(ctx, p):
    if ctx.own is None:
        return None
    return _diff(icm_known(ctx.own["wall_ms"]), icm_known(ctx.own["th_ms"]))


# -- operators --------------------------------------------------------------------

@rm.operator("op.ic_any_outside", (("a", "expr"), ("set", "list")))
def icm_op_any_outside(a, values):
    """Whether any member of a list measure is outside a named list (the named
    list is the revision's); unknown when the measure is unknown."""
    if a is None:
        return None
    allowed = set(values)
    return any(x not in allowed for x in a)
