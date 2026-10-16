"""Admin evidence report: registry, cell identity and display encoding.

Phase 1a of the admin evidence report (design V10). This module is the one
home of the report's closed key registry (`REPORT_REGISTRY`), its bounds
(`CONTRACT_BOUNDS`) and display defaults (`DISPLAY_DEFAULTS`), the cell
identity (design 2.1), the provenance letters, and the one encoding boundary
every displayed string passes through (`_aer_enc`, `AER_ESC`, `AER_WIRE`,
design 2.12 and 3.3).

It imports no review module: phase 1a is structurally uncolored. Nothing here
writes to the database.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Optional

# ── Bounds and display defaults ────────────────────────────────────────────
#
# Every numeric literal a report path depends on lives in one of these two
# tables (design 6.4 reads literals outside them as findings).

CONTRACT_BOUNDS = {
    "GAMES_MIN": 1,
    "GAMES_MAX": 30,
    "PAGE_GAMES": 5,
    "SERIES_GAMES_MAX": 10,
    "BASELINE_SCAN": 500,
    "REPORT_DEADLINE_S": 10,
    "AUDIT_RESERVE_S": 1,
    "RESPONSE_BYTES_MAX": 262144,
    "TEXT_MAX": 48,
    "TIMELINE_WINDOWS_MAX": 12,
    "STEAM_ID_MIN_DIGITS": 15,
    "STEAM_ID_MAX_DIGITS": 20,
}

DISPLAY_DEFAULTS = {
    "own_games": 20,
    "pop_days": 30,
    "games": 10,
}

# ── Cell identity (design 2.1) ─────────────────────────────────────────────

PROVS = ("SELF", "PEER", "OTHER", "D:SELF", "D:PEER", "FLAG", "MEAS")
SCOPES = ("seat", "pair")
SOURCES = ("match_row", "flag_row", "card_record", "card_daily",
           "combat_contrib", "combat_daily")
COVERAGES = ("na", "one", "paired")
KINDS = ("R", "T", "D")
WINDOW_AGGS = ("win_median", "win_max")

# Provenance letters as rendered (design 5.6): `D` for both derived forms.
PROV_LETTER = {"SELF": "S", "PEER": "P", "OTHER": "O", "D:SELF": "D",
               "D:PEER": "D", "FLAG": "F", "MEAS": "M"}


def seat_subject(account, partner=None):
    """`["seat",s,p]`: one account; partner only on basis `pair`."""
    return ("seat", account, partner)


def pair_subject(a, b):
    """`["pair",lo,hi]` in canonical order (`lo` the lower `players.id`)."""
    lo, hi = sorted((a, b), key=str)
    return ("pair", lo, hi)


def game_occurrence(match_id):
    return "game:%s" % match_id


def window_occurrence(oi):
    return "window:%d" % oi


def cell_identity(occurrence, subject, key):
    """The complete identity `(occurrence,subject,key)`; never a bare index."""
    if subject[0] not in SCOPES or len(subject) != 3:
        raise ValueError("subject must be a tagged tuple: %r" % (subject,))
    return (occurrence, tuple(subject), key)


# ── Registry (design 2.10) ─────────────────────────────────────────────────


@dataclass(frozen=True)
class Var:
    """One base variable as its family declares it.

    `provs` lists the provenances the variable carries, each one base key.
    `column` is the per-seat column template (`{s}` is `p1` or `p2`), or a
    seatless column for the reporter's local macro values, or a pair of
    columns for a derived rate. `subject` is `same` (the column's own seat),
    `opposite` (the other seat) or `pair` (pair-global, only when the family
    declares the variable pair-global). `presence` names the seat a key's
    value can exist at: `reporter`, `non_reporter` or `by_prov` (SELF at the
    reporter, PEER at the other seat). `flag_field` names the
    `flag_details` field of the FLAG key.
    """
    var: str
    unit: str
    kind: str
    provs: tuple
    column: object
    subject: str = "same"
    presence: str = "reporter"
    flag_field: Optional[str] = None
    source: str = "match_row"


@dataclass(frozen=True)
class Family:
    code: str
    name: str
    variables: tuple
    pair_global: frozenset = frozenset()


SP = ("SELF", "PEER")

FAMILIES = (
    Family("M", "macro input", (
        Var("macro.suspect_s", "seconds", "R", ("SELF", "FLAG"),
            "local_macro_suspect_seconds", flag_field="macro_suspect_seconds"),
        Var("macro.peak_kps", "keys/s", "R", ("SELF", "FLAG"),
            "local_macro_peak_kps", flag_field="peak_keys_per_second"),
        Var("macro.peak_cps", "clicks/s", "R", ("SELF", "FLAG"),
            "local_macro_peak_cps", flag_field="peak_clicks_per_second"),
        Var("macro.peak_eps", "events/s", "R", ("SELF", "FLAG"),
            "local_macro_peak_eps", flag_field="peak_events_per_second"),
        Var("macro.timeline", "second:keys:clicks", "D", ("SELF", "FLAG"),
            "local_macro_timeline", flag_field="suspect_windows"),
        Var("macro.keys", "count", "R", SP, "{s}_keys_pressed", presence="by_prov"),
        Var("macro.active_s", "seconds", "R", SP, "{s}_active_seconds",
            presence="by_prov"),
        Var("macro.key_rate", "keys/s", "R", ("D:SELF", "D:PEER"),
            ("{s}_keys_pressed", "{s}_active_seconds"), presence="by_prov"),
    )),
    Family("N", "network writer", tuple(
        Var("net.%s" % name, unit, kind, ("SELF",), "{s}_net_%s" % name)
        for name, unit, kind in (
            ("writes", "count", "R"), ("unchanged", "count", "R"),
            ("move_raise_attempted", "count", "R"),
            ("move_raise_accepted", "count", "R"),
            ("resent_reliable", "count", "R"), ("discarded", "count", "R"),
            ("crc_loss", "count", "R"), ("queued_out_max", "count", "R"),
            ("queued_in_max", "count", "R"), ("fragment_cmds", "count", "R"),
            ("view_update_faults", "count", "R"), ("hitch50", "count", "R"),
            ("hitch200", "count", "R"), ("worst_frame_ms", "ms", "R"),
            ("worst_frame_tags", "text", "T")))),
    Family("O", "observer gaps", tuple(
        Var("obs.%s" % name, unit, "R", ("OTHER",), "{s}_obs_%s" % name,
            subject="opposite", presence="reporter")
        for name, unit in (
            ("gap300", "count"), ("gap750", "count"), ("gap1500", "count"),
            ("excess150", "count"), ("payload_equal_gaps", "count"),
            ("receiver_frame_gaps", "count"), ("phoenix_intervals", "count"),
            ("batches", "count"), ("max_gap_ms", "ms"),
            ("max_excess_ms", "ms")))),
    Family("C", "connection and frame", (
        Var("conn.recv_gaps", "count", "R", SP, "{s}_recv_gap_count", presence="by_prov"),
        Var("conn.recv_gap_max_ms", "ms", "R", ("SELF",), "{s}_recv_gap_max_ms"),
        Var("conn.hb_gaps", "count", "R", ("OTHER",), "{s}_hb_gap_count",
            presence="non_reporter"),
        Var("conn.ping_avg", "ms", "R", SP, "{s}_ping_avg", presence="by_prov"),
        Var("conn.ping_max", "ms", "R", ("SELF",), "{s}_ping_max"),
        Var("conn.fps_avg", "frames/s", "R", SP, "{s}_fps_avg", presence="by_prov"),
        Var("conn.freezes", "count", "R", SP, "{s}_freeze_count", presence="by_prov"),
        Var("conn.freezes_focused", "count", "R", SP, "{s}_freeze_focused_count",
            presence="by_prov"),
        Var("conn.freeze_total_s", "seconds", "R", ("SELF",), "{s}_freeze_total_sec"),
        Var("conn.fps_timeline", "text", "D", SP, "{s}_fps_timeline", presence="by_prov"),
        Var("conn.ping_timeline", "text", "D", SP, "{s}_ping_timeline",
            presence="by_prov"),
    )),
)


@dataclass(frozen=True)
class Entry:
    """One catalog entry: a base key (`base is None`) or a window key."""
    ki: int
    key: str
    fam: str
    var: str
    prov: str
    scope: str
    source: str
    coverage: str
    agg: str
    stratum: str
    unit: str
    kind: str
    base: Optional[int]
    decl: Optional[Var]
    bases: tuple = ("player", "pair")

    @property
    def ranked(self):
        """Ranked: numeric kind R and not FLAG (design 2.1, 2.10)."""
        return self.kind == "R" and self.prov != "FLAG"

    @property
    def is_window(self):
        return self.base is not None


def key_id(var, prov, scope, source, coverage="na", agg="cell", stratum="na"):
    """Canonical key id `var|prov|scope|source|coverage|agg|stratum`."""
    return "|".join((var, prov, scope, source, coverage, agg, stratum))


def _expand(families):
    """Every family's declarations expanded into base keys, then exactly two
    window keys per ranked non-FLAG base key (design 2.1, 2.10)."""
    base = []
    for fam in families:
        for v in fam.variables:
            if v.subject == "pair" and v.var not in fam.pair_global:
                raise ValueError("%s: pair subject not declared pair-global by "
                                 "family %s" % (v.var, fam.code))
            scope = "pair" if v.subject == "pair" else "seat"
            for prov in v.provs:
                source = "flag_row" if prov == "FLAG" else v.source
                base.append(dict(key=key_id(v.var, prov, scope, source),
                                 fam=fam.code, var=v.var, prov=prov, scope=scope,
                                 source=source, coverage="na", agg="cell",
                                 stratum="na", unit=v.unit, kind=v.kind,
                                 base=None, decl=v))
    entries = [Entry(ki=i, **b) for i, b in enumerate(base)]
    for b in list(entries[:len(base)]):
        if not b.ranked:
            continue
        for agg in WINDOW_AGGS:
            entries.append(Entry(
                ki=len(entries),
                key=key_id(b.var, b.prov, b.scope, b.source, b.coverage,
                           "%s.%s" % (agg, b.agg), b.stratum),
                fam=b.fam, var=b.var, prov=b.prov, scope=b.scope,
                source=b.source, coverage=b.coverage,
                agg="%s.%s" % (agg, b.agg), stratum=b.stratum, unit=b.unit,
                kind=b.kind, base=b.ki, decl=b.decl,
                bases=("pair",) if b.scope == "pair" else ("player", "pair")))
    return tuple(entries)


REPORT_REGISTRY = _expand(FAMILIES)
REGISTRY_BY_KEY = {e.key: e for e in REPORT_REGISTRY}


def registry_census(entries=None):
    """Per family `[base, window]` counts, from the registry itself; every
    count the report shows comes from here (design 2.10)."""
    entries = REPORT_REGISTRY if entries is None else entries
    out = {}
    for e in entries:
        pair = out.setdefault(e.fam, [0, 0])
        pair[1 if e.is_window else 0] += 1
    return out


def registry_totals(entries=None):
    census = registry_census(entries)
    base = sum(b for b, _w in census.values())
    window = sum(w for _b, w in census.values())
    return {"base": base, "window": window, "entries": base + window}


def registry_fingerprint(entries=None):
    entries = REPORT_REGISTRY if entries is None else entries
    digest = hashlib.sha256("\n".join(e.key for e in entries).encode("utf-8"))
    return digest.hexdigest()[:8]


def registry_block(entries=None):
    """The response's `registry` object (design 4.5): fingerprint and the
    per-family `[base, window]` census, both computed from the registry."""
    return {"fingerprint": registry_fingerprint(entries),
            "census": registry_census(entries)}


def comparability_key(window_key, basis, n):
    """A window cell's comparability key `(window key,basis,n)` (design 2.1):
    summaries at different `games` or bases never share a key, population,
    spread or cache entry."""
    if basis not in ("player", "pair"):
        raise ValueError("basis must be player or pair: %r" % (basis,))
    return (window_key, basis, int(n))


def registry_problems(entries, families):
    """Every way `entries` departs from the expansion of `families` (P21):
    an omitted, extra or duplicated entry, a window key count other than two
    per ranked non-FLAG base key, a missing aggregation, a pair subject no
    family declares, a pair-global window key at basis `player`, and `ki`
    that is not each entry's position."""
    problems = []
    keys = [e.key for e in entries]
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    if dupes:
        problems.append("duplicated entries: %s" % ", ".join(dupes))
    try:
        want = [e.key for e in _expand(families)]
    except ValueError as ex:
        problems.append(str(ex))
        want = []
    missing = [k for k in want if k not in keys]
    extra = [k for k in keys if k not in want]
    if missing:
        problems.append("omitted entries: %s" % ", ".join(missing))
    if extra:
        problems.append("entries no declaration expands to: %s" % ", ".join(extra))
    declared_pair = {(f.code, v) for f in families for v in f.pair_global}
    for i, e in enumerate(entries):
        if e.ki != i:
            problems.append("%s: ki %d at position %d" % (e.key, e.ki, i))
        if e.scope == "pair" and (e.fam, e.var) not in declared_pair:
            problems.append("%s: pair subject not declared pair-global" % e.key)
        if e.is_window and e.scope == "pair" and "player" in e.bases:
            problems.append("%s: pair-global window key at basis player" % e.key)
    for b in entries:
        if b.is_window or not b.ranked:
            continue
        aggs = sorted(w.agg.split(".")[0] for w in entries if w.base == b.ki)
        if aggs != sorted(WINDOW_AGGS):
            problems.append("%s: window aggregations %r" % (b.key, aggs))
    for w in entries:
        if w.is_window:
            base = entries[w.base] if 0 <= w.base < len(entries) else None
            if base is None or base.is_window or not base.ranked:
                problems.append("%s: window key over a non-ranked base" % w.key)
    return problems


# ── Display encoding (design 2.12, 3.3) ────────────────────────────────────


def _escaped_set():
    cps = set(range(0x00, 0x20)) | {0x7F} | set(range(0x80, 0xA0))   # Unicode Cc
    cps |= {0x2028, 0x2029}
    cps |= {0x061C, 0x200E, 0x200F}                                  # Bidi_Control
    cps |= set(range(0x202A, 0x202F)) | set(range(0x2066, 0x206A))
    cps.add(0x60)                                                     # backtick
    return frozenset(cps)


AER_ESC = _escaped_set()

_BACKSLASH = chr(0x5C)


def _aer_enc(value):
    """The one writer of a display slot: doubles the backslash and writes
    each escaped-set code point as backslash, `u{<hex>}`, reversibly. Stored
    bytes are unchanged; only the displayed copy is encoded."""
    if value is None:
        return None
    out = []
    for ch in str(value):
        cp = ord(ch)
        if ch == _BACKSLASH:
            out.append(_BACKSLASH * 2)
        elif cp in AER_ESC:
            out.append("%su{%x}" % (_BACKSLASH, cp))
        else:
            out.append(ch)
    return "".join(out)


def _aer_dec(text):
    """Inverse of `_aer_enc` (tests and the round-trip checks)."""
    if text is None:
        return None
    out = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch != _BACKSLASH:
            out.append(ch)
            i += 1
            continue
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if nxt == _BACKSLASH:
            out.append(_BACKSLASH)
            i += 2
        elif nxt == "u" and text[i + 2:i + 3] == "{":
            end = text.index("}", i + 3)
            out.append(chr(int(text[i + 3:end], 16)))
            i = end + 1
        else:
            raise ValueError("not an encoded display string at %d" % i)
    return "".join(out)


# Phase 1a's closed cell slot tables (design 4.5): no `cls`, no `mark`.
# Duplicated verbatim in discord_bot.py under an equality test (design 3.3).
AER_WIRE = {
    "1a": {
        "summary": ("ki", "n", "val", "own_mean", "own_median", "own_n",
                    "own_state", "pop_rank", "pop_n", "pop_p50", "pop_p90",
                    "pop_p99", "state"),
        "seat": ("ki", "val", "own_mean", "own_n", "own_state", "own_rank",
                 "pop_rank", "pop_n", "state"),
        "pair": ("ki", "val", "own_mean", "own_n", "own_state", "own_rank",
                 "pop_rank", "pop_n", "state"),
    },
}

CELL_STATES = ("ok", "not_recorded", "unknown", "flag_only", "not_run")
OWN_STATES = ("complete", "partial", "truncated", "none")


def wire_row(table, cell, phase="1a"):
    """One cell as its phase's slot array; `val` of a text or display key is
    written through `_aer_enc` here and nowhere else."""
    out = []
    for slot in AER_WIRE[phase][table]:
        v = cell.get(slot)
        if slot == "val" and isinstance(v, str):
            v = _aer_enc(v)
        out.append(v)
    return out


# ── Cell data (design 2.3 to 2.5, 2.7 display half) ────────────────────────

SEATS = ("p1", "p2")


def _other(seat):
    return "p2" if seat == "p1" else "p1"


def _columns():
    cols = set()
    for fam in FAMILIES:
        for v in fam.variables:
            for c in (v.column if isinstance(v.column, tuple) else (v.column,)):
                if "{s}" in c:
                    cols.update(c.format(s=s) for s in SEATS)
                else:
                    cols.add(c)
    return tuple(sorted(cols))


MATCH_COLUMNS = _columns()
_ROW_COLUMNS = ("m.id", "m.ended_at", "m.player1_id", "m.player2_id",
                "m.reported_by", "m.is_ranked", "m.invalidated_at",
                "m.invalidation_reason", "m.series_id")
_SELECT_LIST = ", ".join(_ROW_COLUMNS + tuple("m.%s" % c for c in MATCH_COLUMNS))


def seat_of(row, account):
    """`p1`/`p2` for the account in this game, else None (compared as text:
    the driver's UUID type and the caller's need not be one class)."""
    if account is None:
        return None
    acc = str(account)
    if str(row["player1_id"]) == acc:
        return "p1"
    if str(row["player2_id"]) == acc:
        return "p2"
    return None


def reporter_seat(row):
    rep = row.get("reported_by")
    if rep is None:
        return None
    return seat_of(row, rep)


def _timeline_display(text):
    """`macro.timeline`: at most TIMELINE_WINDOWS_MAX `second:keys:clicks`
    windows, highest key rate first (design 2.10); unparsable items dropped."""
    windows = []
    for pos, item in enumerate(str(text).split(",")):
        parts = item.strip().split(":")
        if len(parts) != 3 or not all(p.strip().lstrip("-").isdigit() for p in parts):
            continue
        windows.append((-int(parts[1]), pos, item.strip()))
    windows.sort()
    return ",".join(w[2] for w in windows[:CONTRACT_BOUNDS["TIMELINE_WINDOWS_MAX"]])


def _display_value(entry, raw):
    if entry.kind == "T":
        return str(raw)[:CONTRACT_BOUNDS["TEXT_MAX"]]
    if entry.kind == "D":
        if entry.var == "macro.timeline":
            return _timeline_display(raw)
        return str(raw)
    return raw


def _applies(entry, col_seat, rep):
    presence = entry.decl.presence
    if presence == "reporter":
        return col_seat == rep
    if presence == "non_reporter":
        return col_seat != rep
    if presence == "by_prov":
        return (col_seat == rep) == (entry.prov in ("SELF", "D:SELF"))
    raise ValueError("unknown presence %r" % presence)


def seat_value(entry, row, subject_seat, current_flag=None):
    """`(value, state)` of a base key for the subject at `subject_seat`.

    NULL is `not_recorded`, never zero (design 2.3, P2). A key whose value can
    only exist at the other seat (a reporter-only column at the non-reporter,
    a PEER relay at the reporter) is `not_recorded` at this seat. FLAG values
    come only from the subject's current `suspected_macro` row (2.4)."""
    decl = entry.decl
    if entry.prov == "FLAG":
        if not current_flag:
            return None, "not_recorded"
        raw = (current_flag.get("details") or {}).get(decl.flag_field)
        if raw is None or raw == "":
            return None, "not_recorded"
        return _display_value(entry, raw), "flag_only"
    rep = reporter_seat(row)
    if rep is None:
        return None, "not_recorded"
    col_seat = _other(subject_seat) if decl.subject == "opposite" else subject_seat
    if not _applies(entry, col_seat, rep):
        return None, "not_recorded"
    if isinstance(decl.column, tuple):
        num = row.get(decl.column[0].format(s=col_seat))
        den = row.get(decl.column[1].format(s=col_seat))
        if num is None:
            return None, "not_recorded"
        if den is None or den == 0:
            return None, "unknown"
        return float(num) / float(den), "ok"
    raw = row.get(decl.column.format(s=col_seat))
    if raw is None:
        return None, "not_recorded"
    return _display_value(entry, raw), "ok"


# FLAG rows: the write path's current-record ordering (main.py, the signed
# sampler route): unreviewed first, then newest; a reviewed row with a
# successor (`supersedes_reviewed_flag_id`) yields the successor.

def _details(row):
    """A row's `flag_details` as a dict: a text() read returns JSONB as text."""
    raw = row["flag_details"]
    if isinstance(raw, str):
        raw = json.loads(raw) if raw else {}
    return raw if isinstance(raw, dict) else {}


def _flag_subject_steam(details):
    details = details or {}
    return details.get("suspect_steam") or details.get("reporter_steam")


def current_flags(flag_rows, reason="suspected_macro"):
    """`{subject steam: current row}` for one game's rows of `reason`."""
    by_subject = {}
    for r in flag_rows:
        if r["flag_reason"] != reason:
            continue
        by_subject.setdefault(_flag_subject_steam(_details(r)), []).append(r)
    out = {}
    for steam, rows in by_subject.items():
        if steam is None:
            continue
        rows = sorted(rows, key=lambda r: (r["reviewed_at"] is None, r["created_at"]),
                      reverse=True)
        chosen = rows[0]
        for _ in range(len(rows)):
            succ = [r for r in rows
                    if _details(r).get("supersedes_reviewed_flag_id")
                    == str(chosen["id"])]
            if not succ:
                break
            chosen = max(succ, key=lambda r: r["created_at"])
        out[steam] = {"id": chosen["id"], "details": _details(chosen)}
    return out


def flag_list(flag_rows, steam_to_subject, current):
    """Every row for the game, current or not, unmerged (design 2.4)."""
    current_ids = {c["id"] for c in current.values()}
    out = []
    for r in sorted(flag_rows, key=lambda r: (r["created_at"], str(r["id"]))):
        out.append({"reason": r["flag_reason"],
                    "subject": steam_to_subject.get(_flag_subject_steam(_details(r))),
                    "reviewed": r["reviewed_at"] is not None,
                    "current": r["id"] in current_ids,
                    "created_at": r["created_at"]})
    return out


def flag_obs(games_flag_rows, steam, reason="suspected_macro"):
    """A seat window's `flag_obs`: distinct `(match, subject)` FLAG
    observations over its covered games, never rows (design 2.4).
    `games_flag_rows` is `{match id: that game's flag rows}`."""
    seen = set()
    for mid, rows in games_flag_rows.items():
        for r in rows:
            if r["flag_reason"] == reason and _flag_subject_steam(_details(r)) == steam:
                seen.add((mid, steam))
    return len(seen)


# ── Own baseline (design 2.5) ──────────────────────────────────────────────
#
# One read per subject: the subject's eligible games strictly before the
# anchor (`(ended_at, id)` order), not invalidated, covered games excluded
# (display only), BASELINE_SCAN+1 rows at most per branch through the order
# indexes of migration 377. Player basis: both seats of the account. Pair
# basis: the account's games with the partner, both orientations.

SEAT_BASELINE_SQL = """
SELECT u.* FROM (
  (SELECT %(cols)s FROM matches m
    WHERE m.player1_id = CAST(:s AS uuid) AND m.invalidated_at IS NULL
      AND (m.ended_at, m.id) < (CAST(:g_ended AS timestamptz), CAST(:g_id AS uuid))
      AND m.id <> ALL(CAST(:covered AS uuid[]))
    ORDER BY m.ended_at DESC, m.id DESC LIMIT CAST(:scan AS integer))
  UNION ALL
  (SELECT %(cols)s FROM matches m
    WHERE m.player2_id = CAST(:s AS uuid) AND m.invalidated_at IS NULL
      AND (m.ended_at, m.id) < (CAST(:g_ended AS timestamptz), CAST(:g_id AS uuid))
      AND m.id <> ALL(CAST(:covered AS uuid[]))
    ORDER BY m.ended_at DESC, m.id DESC LIMIT CAST(:scan AS integer))
) u
 ORDER BY u.ended_at DESC, u.id DESC
 LIMIT CAST(:scan AS integer)""" % {"cols": _SELECT_LIST}

PAIR_BASELINE_SQL = """
SELECT u.* FROM (
  (SELECT %(cols)s FROM matches m
    WHERE m.player1_id = CAST(:a AS uuid) AND m.player2_id = CAST(:b AS uuid)
      AND m.invalidated_at IS NULL
      AND (m.ended_at, m.id) < (CAST(:g_ended AS timestamptz), CAST(:g_id AS uuid))
      AND m.id <> ALL(CAST(:covered AS uuid[]))
    ORDER BY m.ended_at DESC, m.id DESC LIMIT CAST(:scan AS integer))
  UNION ALL
  (SELECT %(cols)s FROM matches m
    WHERE m.player1_id = CAST(:b AS uuid) AND m.player2_id = CAST(:a AS uuid)
      AND m.invalidated_at IS NULL
      AND (m.ended_at, m.id) < (CAST(:g_ended AS timestamptz), CAST(:g_id AS uuid))
      AND m.id <> ALL(CAST(:covered AS uuid[]))
    ORDER BY m.ended_at DESC, m.id DESC LIMIT CAST(:scan AS integer))
) u
 ORDER BY u.ended_at DESC, u.id DESC
 LIMIT CAST(:scan AS integer)""" % {"cols": _SELECT_LIST}


@dataclass(frozen=True)
class Baseline:
    """One subject's baseline read: the rows (newest first) and how many."""
    account: object
    rows: tuple
    read: int

    @property
    def truncated_read(self):
        return self.read > CONTRACT_BOUNDS["BASELINE_SCAN"]


async def read_baseline(db, account, anchor_ended, anchor_id, covered=(), partner=None):
    """The subject's baseline rows before the anchor game (design 2.5)."""
    from sqlalchemy import text   # deferred: the registry half needs no driver

    params = {"g_ended": anchor_ended, "g_id": anchor_id,
              "covered": [c for c in covered],
              "scan": CONTRACT_BOUNDS["BASELINE_SCAN"] + 1}
    if partner is None:
        params["s"] = account
        sql = SEAT_BASELINE_SQL
    else:
        params["a"], params["b"] = account, partner
        sql = PAIR_BASELINE_SQL
    result = await db.execute(text(sql), params)
    rows = tuple(dict(r) for r in result.mappings().all())
    return Baseline(account=account, rows=rows, read=len(rows))


def mid_rank(value, values):
    """`(count below + half the count equal) / n`, in [0, 1] (design 2.7)."""
    if value is None or not values:
        return None
    below = sum(1 for v in values if v < value)
    equal = sum(1 for v in values if v == value)
    return (below + 0.5 * equal) / len(values)


def own_measures(entry, baseline, value=None):
    """Display own measures of a ranked base key for the baseline's subject:
    the newest `own_games` non-NULL values (design 2.5); `truncated` makes
    them unknown, never `n=0`."""
    want = DISPLAY_DEFAULTS["own_games"]
    vals = []
    for row in baseline.rows:
        seat = seat_of(row, baseline.account)
        if seat is None:
            continue
        v, state = seat_value(entry, row, seat)
        if state == "ok" and v is not None:
            vals.append(v)
            if len(vals) == want:
                break
    if len(vals) == want:
        state = "complete"
    elif baseline.truncated_read:
        return {"own_mean": None, "own_median": None, "own_n": None,
                "own_state": "truncated", "own_rank": None, "_values": None}
    elif vals:
        state = "partial"
    else:
        state = "none"
    n = len(vals)
    ordered = sorted(vals)
    if n:
        mid = n // 2
        median = ordered[mid] if n % 2 else (ordered[mid - 1] + ordered[mid]) / 2.0
        mean = sum(vals) / float(n)
    else:
        median = mean = None
    return {"own_mean": mean, "own_median": median, "own_n": n, "own_state": state,
            "own_rank": mid_rank(value, vals), "_values": tuple(vals)}


def game_seat_cells(row, account, current_flag, baseline):
    """Every base key's cell for one seat of one game (design 2.1, 4.5):
    value, state and the display own measures; population slots stay empty
    until the population half (1a-3)."""
    seat = seat_of(row, account)
    if seat is None:
        raise ValueError("account did not play this game")
    cells = []
    for e in REPORT_REGISTRY:
        if e.is_window:
            continue
        val, state = seat_value(e, row, seat, current_flag)
        cell = {"ki": e.ki, "val": val, "state": state, "pop_rank": None,
                "pop_n": None, "own_mean": None, "own_n": None,
                "own_state": "none", "own_rank": None}
        if e.ranked and baseline is not None:
            own = own_measures(e, baseline, val if state == "ok" else None)
            cell.update({k: own[k] for k in ("own_mean", "own_n", "own_state", "own_rank")})
        cells.append(cell)
    return cells


def window_values(entry, rows, account, partner=None):
    """A seat window's displayed values of a base key over its covered games
    (newest first), one per game the subject played (with the partner on
    basis `pair`)."""
    vals = []
    for row in rows:
        seat = seat_of(row, account)
        if seat is None:
            continue
        if partner is not None and seat_of(row, partner) != _other(seat):
            continue
        v, state = seat_value(entry, row, seat)
        if state == "ok" and v is not None:
            vals.append(v)
    return vals


def window_cells(rows, account, basis, baseline, partner=None):
    """One display cell per window key of seat scope (design 5.5): the
    aggregation over the covered games, its `n`, and the base key's own
    measures anchored at the window's oldest game."""
    out = []
    for w in REPORT_REGISTRY:
        if not w.is_window or w.scope != "seat" or basis not in w.bases:
            continue
        base = REPORT_REGISTRY[w.base]
        vals = window_values(base, rows, account, partner)
        agg = w.agg.split(".")[0]
        if not vals:
            val, state = None, "not_recorded"
        elif agg == "win_max":
            val, state = max(vals), "ok"
        else:
            ordered = sorted(vals)
            mid = len(ordered) // 2
            val = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2.0
            state = "ok"
        cell = {"ki": w.ki, "n": len(vals), "val": val, "state": state,
                "comparability": comparability_key(w.key, basis, len(vals)),
                "pop_rank": None, "pop_n": None, "pop_p50": None, "pop_p90": None,
                "pop_p99": None}
        own = own_measures(base, baseline) if baseline is not None else None
        if own is not None:
            cell.update({k: own[k] for k in ("own_mean", "own_median", "own_n", "own_state")})
        else:
            cell.update({"own_mean": None, "own_median": None, "own_n": None,
                         "own_state": "none"})
        out.append(cell)
    return out


def match_row_select(where):
    """A `matches` read selecting every column the registry names."""
    return "SELECT %s FROM matches m WHERE %s" % (_SELECT_LIST, where)
