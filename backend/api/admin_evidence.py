"""Admin evidence report: registry, cell identity and display encoding.

Phase 1a of the admin evidence report (design V10). This module is the one
home of the report's closed key registry (`REPORT_REGISTRY`), its bounds
(`AER_CONTRACT_BOUNDS`) and display defaults (`DISPLAY_DEFAULTS`), the cell
identity (design 2.1), the provenance letters, and the one encoding boundary
every displayed string passes through (`_aer_enc`, `AER_ESC`, `AER_WIRE`,
design 2.12 and 3.3).

It imports no review module: phase 1a is structurally uncolored. Its one
database write is the route audit row (`admin_actions`, design 4.4), in its
own short transaction after the body is built.

The four report routes (R1 to R4, design 4.1) live here in `router`, which
main.py includes; `evidence_key_gate` is the outermost http middleware for
their path prefix, registered by main.py after `replica_write_gate`.
"""

from __future__ import annotations

import asyncio
import collections
import datetime as _dt
import hashlib
import hmac
import itertools
import json
import logging
import math
import os
import time
from array import array
from dataclasses import dataclass, field
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from read_gate import ReadGateRoute

# ── Bounds and display defaults ────────────────────────────────────────────
#
# Every numeric literal a report path depends on lives in one of these two
# tables (design 6.4 reads literals outside them as findings).

AER_CONTRACT_BOUNDS = {
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
    # Populations (design 2.6): the caps as lowered there, the derived-result
    # memo, the entry lifetime, the request concurrency and the memory budget.
    "POP_VALUES_MAX": 2000,
    "WIN_VALUES_MAX": 1000,
    "WIN_UNIT_DEPTH": 30,
    "WIN_DERIVED_BYTES_MAX": 2 * 1024 * 1024,
    "POP_TTL_S": 3600,
    "REPORT_INFLIGHT_MAX": 2,
    # 128 at the design; 225 from the P9 cold figure on Linux at the lane's
    # base; 245 from the re-measurement at the re-land onto main (see
    # BASE_RSS_FLOOR_MB below for both measurements and the derivation).
    "POP_MEM_BUDGET_MB": 245,
    "GAME_SETS_LIVE": 4,
    "WINDOW_SOURCES_LIVE": 8,
    # Routes (design 4.6): reports per actor per window, in process.
    "RATE_MAX": 20,
    "RATE_WINDOW_S": 600,
    "ACTOR_ID_MAX_DIGITS": 32,
    # Evidence sections (phase 2, B10): the per-statement row limits of the
    # card, combat and identity-clock reads, the contribution rows shown per
    # seat of a game, and the longest fact name.
    "SECTION_KEYS_MAX": 64,
    "SECTION_ROWS_MAX": 512,
    "SECTION_CONTRIB_MAX": 4,
    "SECTION_DAILY_ROWS_MAX": 512,
    "FACT_NAME_MAX": 48,
    # Phase 3 (B10): the stored findings listed per section of a game, the
    # rows each evidence population statement reads (one more tells a cut),
    # the evidence cells shown per window, and card_measures' fixed point
    # (W["fixed_point"], under an equality test), by which card_contrib and
    # card_player_daily store the expected counts and variances.
    "FINDINGS_MAX": 8,
    "EV_POP_ROWS_MAX": 20000,
    "EV_CELLS_MAX": 400,
    "CARD_FIXED_POINT": 1000000,
}

DISPLAY_DEFAULTS = {
    "own_games": 20,
    "pop_days": 30,
    "games": 10,
    # D4's READY_LAG_S (review_measures.py CONTRACT_BOUNDS["ready_lag_s"] at
    # the D4 round 15 pin); re-read at D4_TIP when the D4 files land.
    "lag_s": 120,
}

# ── Cell identity (design 2.1) ─────────────────────────────────────────────

PROVS = ("SELF", "PEER", "OTHER", "D:SELF", "D:PEER", "FLAG", "MEAS")
SCOPES = ("seat", "pair")
SOURCES = ("match_row", "flag_row", "card_record", "card_daily",
           "combat_contrib", "combat_player_daily")
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
class AerEntry:
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


def aer_key_id(var, prov, scope, source, coverage="na", agg="cell", stratum="na"):
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
                base.append(dict(key=aer_key_id(v.var, prov, scope, source),
                                 fam=fam.code, var=v.var, prov=prov, scope=scope,
                                 source=source, coverage="na", agg="cell",
                                 stratum="na", unit=v.unit, kind=v.kind,
                                 base=None, decl=v))
    entries = [AerEntry(ki=i, **b) for i, b in enumerate(base)]
    for b in list(entries[:len(base)]):
        if not b.ranked:
            continue
        for agg in WINDOW_AGGS:
            entries.append(AerEntry(
                ki=len(entries),
                key=aer_key_id(b.var, b.prov, b.scope, b.source, b.coverage,
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

AER_SEATS = ("p1", "p2")


def _aer_other(seat):
    return "p2" if seat == "p1" else "p1"


def _columns():
    cols = set()
    for fam in FAMILIES:
        for v in fam.variables:
            for c in (v.column if isinstance(v.column, tuple) else (v.column,)):
                if "{s}" in c:
                    cols.update(c.format(s=s) for s in AER_SEATS)
                else:
                    cols.add(c)
    return tuple(sorted(cols))


MATCH_COLUMNS = _columns()
_ROW_COLUMNS = ("m.id", "m.ended_at", "m.player1_id", "m.player2_id",
                "m.reported_by", "m.is_ranked", "m.invalidated_at",
                "m.invalidation_reason", "m.series_id")
_SELECT_LIST = ", ".join(_ROW_COLUMNS + tuple("m.%s" % c for c in MATCH_COLUMNS))


def aer_seat_of(row, account):
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


def aer_reporter_seat(row):
    rep = row.get("reported_by")
    if rep is None:
        return None
    return aer_seat_of(row, rep)


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
    return ",".join(w[2] for w in windows[:AER_CONTRACT_BOUNDS["TIMELINE_WINDOWS_MAX"]])


def _display_value(entry, raw):
    if entry.kind == "T":
        return str(raw)[:AER_CONTRACT_BOUNDS["TEXT_MAX"]]
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
    rep = aer_reporter_seat(row)
    if rep is None:
        return None, "not_recorded"
    col_seat = _aer_other(subject_seat) if decl.subject == "opposite" else subject_seat
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
    for r in flag_rows:
        out.append({"reason": _aer_enc(r["flag_reason"]),     # a display slot (2.12)
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
        return self.read > AER_CONTRACT_BOUNDS["BASELINE_SCAN"]


async def read_baseline(db, account, anchor_ended, anchor_id, covered=(), partner=None):
    """The subject's baseline rows before the anchor game (design 2.5)."""
    from sqlalchemy import text   # deferred: the registry half needs no driver

    params = {"g_ended": anchor_ended, "g_id": anchor_id,
              "covered": [c for c in covered],
              "scan": AER_CONTRACT_BOUNDS["BASELINE_SCAN"] + 1}
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
        seat = aer_seat_of(row, baseline.account)
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
    seat = aer_seat_of(row, account)
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
        seat = aer_seat_of(row, account)
        if seat is None:
            continue
        if partner is not None and aer_seat_of(row, partner) != _aer_other(seat):
            continue
        v, state = seat_value(entry, row, seat)
        if state == "ok" and v is not None:
            vals.append(v)
    return vals


def window_stat(agg, vals):
    """A window key's aggregation over its values (design 2.1), one rule for
    the display cell and the window population: `win_max` the largest,
    `win_median` the median (the mean of the middle two for an even count)."""
    if agg == "win_max":
        return max(vals)
    ordered = sorted(vals)
    mid = len(ordered) // 2
    return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2.0


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
        else:
            val, state = window_stat(agg, vals), "ok"
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


# ── Populations (design 2.6) ───────────────────────────────────────────────
#
# One statement per game-population rebuild. A MATERIALIZED CTE reads the
# window over `idx_matches_ended`; one UNION ALL branch per (ranked base key,
# subject seat) yields `(ki, val, ended_at, id, subj)`, `subj` the fact's
# canonical subject tuple as three columns (kind, account or `lo`, partner or
# `hi`). Before any bound, the complete eligible relation is checked for a
# repeated `(ki, id, subj)` (one fact per identity); then `row_number()` per
# key in `ended_at DESC, id DESC, subj` order keeps the newest `cap` values,
# `cap+1` read to tell a truncated key. `subj` is the last sort key, so a
# match's two seat facts are ordered by identity, never by value (#606).

_REP_SQL = ("CASE WHEN m.reported_by = m.player1_id THEN 'p1' "
            "WHEN m.reported_by = m.player2_id THEN 'p2' END")


def _seat_account_sql(seat):
    return "g.player1_id" if seat == "p1" else "g.player2_id"


def _applies_sql(entry, col_seat):
    """The SQL twin of `_applies`: the seat a key's value can exist at."""
    presence = entry.decl.presence
    if presence == "reporter":
        return "g.rep = '%s'" % col_seat
    if presence == "non_reporter":
        return "g.rep = '%s'" % _aer_other(col_seat)
    if presence == "by_prov":
        own = entry.prov in ("SELF", "D:SELF")
        return "g.rep = '%s'" % (col_seat if own else _aer_other(col_seat))
    raise ValueError("unknown presence %r" % presence)


def _value_sql(entry, col_seat):
    """The SQL twin of `seat_value` for a ranked key: NULL stays NULL (never
    a 0), a derived rate is unknown (NULL) when its denominator is NULL or 0."""
    col = entry.decl.column
    if isinstance(col, tuple):
        return ("CAST(g.%s AS double precision) / NULLIF(CAST(g.%s AS double precision), 0)"
                % (col[0].format(s=col_seat), col[1].format(s=col_seat)))
    return "CAST(g.%s AS double precision)" % col.format(s=col_seat)


def population_branches(entries=None, partner=False):
    """One `(ki, val, ended_at, id, sk, sa, sb)` branch per ranked base key
    and subject seat (phase 1: every fact is a seat fact `["seat",s,null]`).
    `partner` adds `po`, the other seat's account: the unit column of a
    directional pair-seat window source."""
    entries = REPORT_REGISTRY if entries is None else entries
    out = []
    for e in entries:
        if e.is_window or not e.ranked or e.source != "match_row":
            continue
        for seat in AER_SEATS:
            col_seat = _aer_other(seat) if e.decl.subject == "opposite" else seat
            val = _value_sql(e, col_seat)
            po = (", %s AS po" % _seat_account_sql(_aer_other(seat))) if partner else ""
            out.append(
                "SELECT %d AS ki, %s AS val, g.ended_at, g.id, 'seat'::text AS sk, "
                "%s AS sa, CAST(NULL AS uuid) AS sb%s FROM g WHERE %s AND %s IS NOT NULL"
                % (e.ki, val, _seat_account_sql(seat), po, _applies_sql(e, col_seat), val))
    return out


def _window_cte(ranked_only):
    """The `g` CTE both population statements share: every 1v1 game, not
    invalidated, ended within `:pop_days` days and at least `:lag_s` seconds
    ago, read once by `idx_matches_ended`."""
    return """g AS MATERIALIZED (
  SELECT m.id, m.ended_at, m.player1_id, m.player2_id, %(rep)s AS rep, %(cols)s
    FROM matches m
   WHERE m.invalidated_at IS NULL%(ranked)s
     AND m.ended_at >= now() - make_interval(days => CAST(:pop_days AS integer))
     AND m.ended_at <= now() - make_interval(secs => CAST(:lag_s AS integer)))""" % {
        "rep": _REP_SQL,
        "cols": ", ".join("m.%s" % c for c in MATCH_COLUMNS),
        "ranked": "\n     AND m.is_ranked" if ranked_only else ""}


def population_sql(branches, ranked_only=False):
    """The rebuild statement over `branches` (design 2.6, 2.9: the window by
    `idx_matches_ended`, SQL-side bound, one row per key). The identity
    check `dup` reads `f`, the complete eligible relation, never `r`'s
    bounded rows."""
    return """
WITH %(g)s,
f AS (
%(branches)s),
r AS (
  SELECT f.ki, f.val, f.ended_at, f.id, f.sk, f.sa, f.sb,
         row_number() OVER (PARTITION BY f.ki
                            ORDER BY f.ended_at DESC, f.id DESC, f.sk, f.sa, f.sb) AS rn
    FROM f),
dup AS (
  SELECT count(*) AS n FROM (
    SELECT 1 FROM f GROUP BY f.ki, f.id, f.sk, f.sa, f.sb HAVING count(*) > 1) d)
SELECT r.ki,
       array_agg(r.val ORDER BY r.val) FILTER (WHERE r.rn <= CAST(:cap AS integer)) AS vals,
       bool_or(r.rn = CAST(:cap AS integer) + 1) AS truncated,
       max(r.ended_at) FILTER (WHERE r.rn = CAST(:cap AS integer)) AS cutoff,
       (SELECT dup.n FROM dup) AS dup
  FROM r
 WHERE r.rn <= CAST(:cap AS integer) + 1
 GROUP BY r.ki
 ORDER BY r.ki""" % {"g": _window_cte(ranked_only),
                     "branches": "\n  UNION ALL\n".join("  " + b for b in branches)}


# The player basis has one unit per account: its second unit column is a
# constant, so units join on plain equality.
_NO_PARTNER = "CAST('00000000-0000-0000-0000-000000000000' AS uuid)"


def window_source_sql(branches, basis, ranked_only=False):
    """The window source statement for one basis (design 2.6). Units are
    accounts (basis `player`) or directional `(account, opponent)` pairs
    (basis `pair`, a seat key). Per key and unit the newest `:depth` values
    in `ended_at DESC, id DESC` order; units by newest game, then unit id,
    kept whole while the key's values fit `:wmax`; the crossing unit and
    every later one are dropped and the key is truncated. The identity
    check `wd` reads `u`, the complete eligible relation, before the depth,
    the crossing-unit drop and the aggregation. `branches` carry `po`."""
    if basis not in ("player", "pair"):
        raise ValueError("basis must be player or pair: %r" % (basis,))
    unit = "f.po" if basis == "pair" else _NO_PARTNER
    return """
WITH %(g)s,
f AS (
%(branches)s),
u AS (
  SELECT f.ki, f.val, f.ended_at, f.id, f.sk, f.sa, f.sb, f.sa AS ua, %(unit)s AS ub,
         row_number() OVER (PARTITION BY f.ki, f.sa, %(unit)s
                            ORDER BY f.ended_at DESC, f.id DESC) AS rn
    FROM f),
d AS (
  SELECT u.* FROM u WHERE u.rn <= CAST(:depth AS integer)),
un AS (
  SELECT d.ki, d.ua, d.ub, count(*) AS cnt, max(d.ended_at) AS ne,
         (array_agg(d.id ORDER BY d.rn))[1] AS nid
    FROM d GROUP BY d.ki, d.ua, d.ub),
uo AS (
  SELECT un.ki, un.ua, un.ub, un.cnt,
         row_number() OVER w AS uo,
         sum(un.cnt) OVER (w ROWS UNBOUNDED PRECEDING) AS cum
    FROM un
  WINDOW w AS (PARTITION BY un.ki ORDER BY un.ne DESC, un.nid DESC, un.ua, un.ub)),
k AS (
  SELECT uo.ki, uo.ua, uo.ub, uo.uo, uo.cnt FROM uo WHERE uo.cum <= CAST(:wmax AS integer)),
wd AS (
  SELECT count(*) AS n FROM (
    SELECT 1 FROM u GROUP BY u.ki, u.id, u.sk, u.sa, u.sb HAVING count(*) > 1) x),
kv AS (
  SELECT k.ki, array_agg(d.val ORDER BY k.uo, d.rn) AS vals,
         array_agg(k.cnt ORDER BY k.uo) FILTER (WHERE d.rn = 1) AS counts
    FROM k JOIN d ON d.ki = k.ki AND d.ua = k.ua AND d.ub = k.ub
   GROUP BY k.ki),
t AS (
  SELECT uo.ki, bool_or(uo.cum > CAST(:wmax AS integer)) AS truncated
    FROM uo GROUP BY uo.ki)
SELECT t.ki, kv.vals, kv.counts, t.truncated, (SELECT wd.n FROM wd) AS dup
  FROM t LEFT JOIN kv ON kv.ki = t.ki
 ORDER BY t.ki""" % {"g": _window_cte(ranked_only), "unit": unit,
                     "branches": "\n  UNION ALL\n".join("  " + b for b in branches)}


class PopulationUnavailable(Exception):
    """A population source holds two facts for one `(ki, id, subj)`, or a
    replacement found no room in the budget within the deadline: nothing
    publishes, and the route answers `503 unavailable (population)`."""
    status = 503
    detail = "unavailable (population)"


_aer_log = logging.getLogger("admin_evidence")


async def rebuild_game_population(conn, key, pop_days, lag_s, ranked_only=False,
                                  cap=None):
    """Read one game population and return `(values, truncated)`: per key an
    ascending `array('d')` of at most `cap` values and, for a truncated key,
    its cutoff. Streamed one key's row at a time. A repeated identity
    anywhere in the complete eligible relation raises PopulationUnavailable
    before anything is kept."""
    from sqlalchemy import text   # deferred: the registry half needs no driver
    cap = AER_CONTRACT_BOUNDS["POP_VALUES_MAX"] if cap is None else cap
    sql = population_sql(population_branches(), ranked_only=ranked_only)
    params = {"pop_days": pop_days, "lag_s": lag_s, "cap": cap}
    values, truncated = {}, {}
    result = await conn.stream(text(sql), params)
    async for row in result:
        if row.dup:
            raise PopulationUnavailable(
                "population %r: %d repeated (ki, id, subj) facts" % (key, row.dup))
        values[row.ki] = array("d", row.vals or ())
        if row.truncated:
            truncated[row.ki] = row.cutoff
    return values, truncated


async def rebuild_window_source(conn, key, basis, pop_days, lag_s, ranked_only=False,
                                wmax=None, depth=None):
    """Read one window source and return `(values, offsets, truncated)`: per
    key the kept units' values packed in unit order, newest first within a
    unit, in `array('d')`, the unit start offsets (and the end) in
    `array('i')`, and the truncated keys. Streamed one key's row at a time;
    a repeated identity anywhere in the complete eligible relation raises
    PopulationUnavailable before anything is kept."""
    from sqlalchemy import text
    wmax = AER_CONTRACT_BOUNDS["WIN_VALUES_MAX"] if wmax is None else wmax
    depth = AER_CONTRACT_BOUNDS["WIN_UNIT_DEPTH"] if depth is None else depth
    sql = window_source_sql(population_branches(partner=True), basis,
                            ranked_only=ranked_only)
    params = {"pop_days": pop_days, "lag_s": lag_s, "wmax": wmax, "depth": depth}
    values, offsets, truncated = {}, {}, {}
    result = await conn.stream(text(sql), params)
    async for row in result:
        if row.dup:
            raise PopulationUnavailable(
                "window source %r: %d repeated (ki, id, subj) facts" % (key, row.dup))
        values[row.ki] = array("d", row.vals or ())
        offsets[row.ki] = array("i", list(itertools.accumulate(row.counts or (), initial=0)))
        if row.truncated:
            truncated[row.ki] = True
    return values, offsets, truncated


def window_population(values, offsets, agg, n):
    """The distribution a window cell is ranked in (design 2.6): each kept
    unit's statistic over its first `n` values, units with fewer than `n`
    values excluded; ascending."""
    out = []
    for i in range(len(offsets) - 1):
        lo, hi = offsets[i], offsets[i + 1]
        if hi - lo >= n:
            out.append(window_stat(agg, values[lo:lo + n]))
    return array("d", sorted(out))


def _quantile(ordered, q):
    """Nearest-rank quantile of an ascending sequence."""
    k = max(1, int(math.ceil(q * len(ordered))))
    return ordered[k - 1]


def pop_measures(values, value):
    """`pop_rank` (the mid-rank, design 2.7), `pop_n` and the three
    percentiles of one ascending population for one value."""
    n = len(values) if values is not None else 0
    if not n:
        return {"pop_rank": None, "pop_n": 0, "pop_p50": None, "pop_p90": None,
                "pop_p99": None}
    return {"pop_rank": mid_rank(value, values) if value is not None else None,
            "pop_n": n, "pop_p50": _quantile(values, 0.5),
            "pop_p90": _quantile(values, 0.9), "pop_p99": _quantile(values, 0.99)}


@dataclass
class Generation:
    """One immutable published population; `gen` is process-monotonic."""
    key: tuple
    gen: int
    computed_at: float
    values: dict
    truncated: dict
    offsets: dict = field(default_factory=dict)
    kind: str = "game"
    leases: int = 0
    retired: bool = False

    def nbytes(self):
        """The packed bytes: values (8 B each) and unit offsets (4 B each)."""
        return (sum(len(a) * a.itemsize for a in self.values.values())
                + sum(len(a) * a.itemsize for a in self.offsets.values()))


# The design's sizing basis for the cold base RSS `B` (design 2.6); the api
# replaces it with the value it measures at startup (item 1a-4).
SIZING_BASE_RSS_MB = 80.0


def process_rss_mb(peak=False):
    """This process's resident set in MB, or its peak: VmRSS or VmHWM from
    /proc on Linux (the api container); the working set or its peak through
    psapi elsewhere (the Windows test seat), a different quantity."""
    try:
        with open("/proc/self/status", encoding="ascii") as fh:
            want = "VmHWM:" if peak else "VmRSS:"
            for line in fh:
                if line.startswith(want):
                    return int(line.split()[1]) / 1024.0
    except OSError:
        pass
    import ctypes
    from ctypes import wintypes

    class _Counters(ctypes.Structure):
        _fields_ = ([("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)]
                    + [(n, ctypes.c_size_t) for n in (
                        "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                        "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                        "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")])

    kernel32, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Counters),
                                           wintypes.DWORD]
    c = _Counters()
    c.cb = ctypes.sizeof(c)
    if not psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(c), c.cb):
        raise OSError("GetProcessMemoryInfo failed")
    return (c.PeakWorkingSetSize if peak else c.WorkingSetSize) / 1048576.0


# A measured B above this is P9 red, and the figure goes to Sid as a budget
# decision (design 2.6).
#
# P9 cold start, Linux (2026-10-17): B 160.4 MB and peak 160.5 MB on an LXC
# test seat (Python 3.12.15) in three runs, the api imported in a fresh
# interpreter with no bytecode cache, which is how the container starts: its
# image compiles nothing at build time and a deploy recreates it. The design's
# 94.7 floor and 128 budget assumed a sizing B of 80. Both bounds are
# re-derived from the measurement, each rounded up to the next multiple of 5:
#   floor   160.4 -> 165
#   budget  (B 160.4 + the 18.1 MB worst case at P 2,000, W 1,000) x 1.25
#           = 223.1 -> 225; peak x 1.25 = 200.6 is inside it.
# The worst-case cache (15,923,456 counted bytes) then fits the budget gate
# at the measured B: 225/1.25 - 160.4 - 2 = 17.6 MB.
#
# Re-measured at the re-land onto main 3fc331e2 (2026-10-30, suite seat 2,
# Python 3.12.15, the same fresh-interpreter form): B 177.5 MB and peak
# 177.6 MB, the api having grown by the identity-clock, card and combat
# evidence servers and the build manifest since the lane's base (nothing of
# this module changed). The same derivation, each rounded up to the next
# multiple of 5:
#   floor   177.5 -> 180
#   budget  (B 177.5 + 18.1) x 1.25 = 244.5 -> 245; peak x 1.25 = 222.0 is
#           inside it.
# The worst-case cache (15,923,456 counted bytes, 15.2 MB) fits the budget
# gate at the measured B: 245/1.25 - 177.5 - 2 = 16.5 MB.
BASE_RSS_FLOOR_MB = 180


def budget_bytes(base_rss_mb):
    """The cache's byte budget (design 2.6): `POP_MEM_BUDGET_MB/1.25 - B - 2` MB."""
    return int((AER_CONTRACT_BOUNDS["POP_MEM_BUDGET_MB"] / 1.25 - base_rss_mb - 2)
               * 1024 * 1024)


class PopulationCache:
    """The api process's population cache (design 2.6): generations, counted
    leases, an LRU memo of derived results keyed by (comparability key,
    source key, gen) within WIN_DERIVED_BYTES_MAX. No key carries a route
    shape. A publish retires the generation it supersedes and evicts its
    derived entries (#744); a retired generation stays counted until its last
    lease is released."""

    LIVE_MAX = {"game": "GAME_SETS_LIVE", "window": "WINDOW_SOURCES_LIVE"}

    def __init__(self, clock=None, base_rss_mb=SIZING_BASE_RSS_MB):
        self._clock = clock or time.time
        self._gen = 0
        self.live = {}
        self.retired = []
        self.memo = collections.OrderedDict()
        self.memo_bytes = 0
        self.in_progress = 0
        self.base_rss_mb = base_rss_mb
        self._released = asyncio.Event()

    @property
    def budget(self):
        return budget_bytes(self.base_rss_mb)

    def current(self, key):
        g = self.live.get(key)
        if g is None or self._clock() - g.computed_at >= AER_CONTRACT_BOUNDS["POP_TTL_S"]:
            return None
        return g

    def publish(self, key, values, truncated, offsets=None):
        """Publish a new generation for `key`; a window source passes its
        unit offsets. The superseded generation retires, and past the live
        cap of its kind the oldest other live generation of that kind does."""
        kind = "window" if offsets is not None else "game"
        self._gen += 1
        new = Generation(key=key, gen=self._gen, computed_at=self._clock(),
                         values=values, truncated=truncated, offsets=offsets or {},
                         kind=kind)
        old = self.live.get(key)
        self.live = {k: value for k, value in self.live.items() if k != key}
        self.live[key] = new
        if old is not None:
            self._retire(old)
        same = [g for g in self.live.values() if g.kind == kind]
        while len(same) > AER_CONTRACT_BOUNDS[self.LIVE_MAX[kind]]:
            oldest = same[0]
            same = same[1:]
            self.live = {k: value for k, value in self.live.items()
                         if k != oldest.key}
            self._retire(oldest)
        return new

    async def admit(self, nbytes, deadline):
        """The budget gate (design 2.6): a replacement of `nbytes`, which the
        caller already counts in `in_progress`, publishes only while
        `cache_bytes()` (live, leased-retired, memo, in-progress, so the
        replacement too) fits the budget; otherwise wait on lease releases
        until `deadline` (time.monotonic), then refuse."""
        while self.cache_bytes() > self.budget:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise PopulationUnavailable(
                    "budget: %d cached bytes (a %d-byte replacement among them) over %d"
                    % (self.cache_bytes(), nbytes, self.budget))
            released = self._released
            try:
                await asyncio.wait_for(released.wait(), remaining)
            except asyncio.TimeoutError:
                pass

    def _retire(self, g):
        g.retired = True
        kept = collections.OrderedDict()
        for mk, value in self.memo.items():
            if mk[1] == g.key and mk[2] == g.gen:
                self.memo_bytes -= value["_bytes"]
            else:
                kept[mk] = value
        self.memo = kept
        if g.leases:
            self.retired.append(g)

    def lease(self, g):
        g.leases += 1
        return g

    def release(self, g):
        g.leases -= 1
        if g.leases == 0 and g in self.retired:
            index = self.retired.index(g)
            self.retired[index:index + 1] = []
        released = self._released
        self._released = asyncio.Event()
        released.set()

    @staticmethod
    def _memo_key(comp, lease):
        return (comp, lease.key, lease.gen)

    def memo_get(self, comp, lease):
        """A derived result, only when its stored source key, gen and
        computed_at all equal the lease's; otherwise None (recompute)."""
        mk = self._memo_key(comp, lease)
        r = self.memo.get(mk)
        if r is None or (r.get("source_key"), r.get("gen"), r.get("computed_at")) != (
                lease.key, lease.gen, lease.computed_at):
            return None
        self.memo.move_to_end(mk)
        return r

    def memo_put(self, comp, lease, result, nbytes):
        mk = self._memo_key(comp, lease)
        if mk in self.memo:
            self.memo_bytes -= self.memo[mk]["_bytes"]
            self.memo = collections.OrderedDict(
                (key, value) for key, value in self.memo.items() if key != mk)
        stored = dict(result, source_key=lease.key, gen=lease.gen,
                      computed_at=lease.computed_at, _bytes=nbytes)
        self.memo[mk] = stored
        self.memo_bytes += nbytes
        if self.memo_bytes > AER_CONTRACT_BOUNDS["WIN_DERIVED_BYTES_MAX"]:
            kept = collections.OrderedDict()
            for key, value in self.memo.items():
                if self.memo_bytes > AER_CONTRACT_BOUNDS["WIN_DERIVED_BYTES_MAX"]:
                    self.memo_bytes -= value["_bytes"]
                else:
                    kept[key] = value
            self.memo = kept
        return stored

    def cache_bytes(self):
        """`_aer_cache_bytes()`: live, leased-retired, memo and in-progress."""
        return (sum(g.nbytes() for g in self.live.values())
                + sum(g.nbytes() for g in self.retired)
                + self.memo_bytes + self.in_progress)


def _packed_bytes(*maps):
    return sum(len(a) * a.itemsize for m in maps for a in m.values())


def _aer_deadline(deadline):
    if deadline is not None:
        return deadline
    return (time.monotonic() + AER_CONTRACT_BOUNDS["REPORT_DEADLINE_S"]
            - AER_CONTRACT_BOUNDS["AUDIT_RESERVE_S"])


async def _admit_and_publish(cache, key, values, truncated, offsets, t0, deadline):
    nbytes = _packed_bytes(values, offsets or {})
    cache.in_progress += nbytes
    try:
        await cache.admit(nbytes, _aer_deadline(deadline))
    except PopulationUnavailable as exc:
        _aer_log.warning("admin_evidence population unavailable: key=%r %s", key, exc)
        raise
    finally:
        cache.in_progress -= nbytes
    g = cache.publish(key, values, truncated, offsets)
    _aer_log.info("admin_evidence population rebuilt: key=%r gen=%d size=%d truncated=%s "
              "duration_ms=%d bytes=%d", key, g.gen, sum(len(a) for a in values.values()),
              sorted(truncated), int((time.monotonic() - t0) * 1000), g.nbytes())
    return g


async def refresh_game_set(cache, conn, key, pop_days, lag_s, ranked_only=False,
                           cap=None, deadline=None):
    """Rebuild and publish one game set. A refusal (a repeated identity, or
    no room in the budget by the deadline) logs one line, publishes nothing
    and raises PopulationUnavailable; the live generation stays as it was."""
    t0 = time.monotonic()
    try:
        values, truncated = await rebuild_game_population(
            conn, key, pop_days, lag_s, ranked_only=ranked_only, cap=cap)
    except PopulationUnavailable as exc:
        _aer_log.warning("admin_evidence population unavailable: key=%r %s", key, exc)
        raise
    return await _admit_and_publish(cache, key, values, truncated, None, t0, deadline)


async def refresh_window_source(cache, conn, key, basis, pop_days, lag_s,
                                ranked_only=False, wmax=None, depth=None, deadline=None):
    """Rebuild and publish one window source; refusals as `refresh_game_set`."""
    t0 = time.monotonic()
    try:
        values, offsets, truncated = await rebuild_window_source(
            conn, key, basis, pop_days, lag_s, ranked_only=ranked_only, wmax=wmax,
            depth=depth)
    except PopulationUnavailable as exc:
        _aer_log.warning("admin_evidence population unavailable: key=%r %s", key, exc)
        raise
    return await _admit_and_publish(cache, key, values, truncated, offsets, t0, deadline)


# ── Routes (design 1.2, 1.3, 4.1 to 4.6; item 1a-4) ───────────────────────
#
# Order in a served request (design 4.4): key gate (middleware), actor gate,
# parse, recovery probe, rate bound, in-flight bound and leases, reads, the
# empty-cohort check, serialization and size check, audit, return. Every
# refusal is a status with `{"detail": <word>}`; the gate's refusal is one
# fixed body for every failure class.

EVIDENCE_ROOT = "/api/v1/internal/evidence-report"
EVIDENCE_PREFIX = EVIDENCE_ROOT + "/"
REFUSED = "refused"

# Built with the read gate's route class, as main.app's own GET routes are, so
# each report route carries the gate exactly once (INTERNAL class by prefix:
# the gate refuses nothing and looks nothing up there).
router = APIRouter(prefix=EVIDENCE_ROOT, tags=["Internal"], route_class=ReadGateRoute)


def _evidence_refusal():
    """The one refusal of the key and actor gates: `403 {"detail":"refused"}`."""
    return JSONResponse(status_code=403, content={"detail": REFUSED})


def _refuse_class(cls):
    """Log the failure class once, without the actor id (design 4.2)."""
    _aer_log.info("admin_evidence refused: %s", cls)


def _key_matches(given):
    expected = os.getenv("API_SECRET_KEY", "")
    if not expected or given is None:
        return False
    return hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8"))


async def evidence_key_gate(request: Request, call_next):
    """Outermost layer for the evidence report paths (design 4.2 step 1).

    A request whose path is under `/api/v1/internal/evidence-report/` must
    carry `X-Internal-Key` equal to `API_SECRET_KEY`, and that variable must
    be set (fail closed); otherwise it gets `_evidence_refusal()` in every
    server state and for any method. It reads the path and that one header
    only and keeps no bypass list; every other path passes untouched, and a
    request with the key continues through the unchanged chain. main.py
    registers it after `replica_write_gate`, so it runs first."""
    path = request.url.path
    if path == EVIDENCE_ROOT or path.startswith(EVIDENCE_PREFIX):
        if not _key_matches(request.headers.get("X-Internal-Key")):
            _refuse_class("no_key")
            return _evidence_refusal()
    return await call_next(request)


def _aer_fail(status, word, headers=None):
    raise HTTPException(status_code=status, detail=word, headers=headers)


async def _aer_is_admin(db, steam_id):
    """The account is on the admin roster (`admin_users`, as main._is_admin):
    the one authority this report accepts (#447)."""
    from sqlalchemy import text
    row = (await db.execute(text("SELECT 1 FROM admin_users WHERE steam_id = :s"),
                            {"s": steam_id})).first()
    return row is not None


async def _evidence_gate(request, db):
    """The route seam (design 4.2 step 2, 6.2): the first statement of every
    handler, before any argument is parsed. Requires `X-Actor-Discord-Id`, 1
    to ACTOR_ID_MAX_DIGITS ASCII digits, linked to a live account, and that
    account on the admin roster; returns the account's steam id. Any failure
    is the same `403 refused`."""
    from sqlalchemy import text
    d = request.headers.get("X-Actor-Discord-Id")
    if (d is None or not 1 <= len(d) <= AER_CONTRACT_BOUNDS["ACTOR_ID_MAX_DIGITS"]
            or not d.isascii() or not d.isdigit()):
        _refuse_class("bad_actor")
        _aer_fail(403, REFUSED)
    steam = (await db.execute(text(
        "SELECT steam_id FROM players WHERE discord_id = :d AND deleted_at IS NULL"),
        {"d": d})).scalar()
    if not steam:
        _refuse_class("not_linked")
        _aer_fail(403, REFUSED)
    if not await _aer_is_admin(db, steam):
        _refuse_class("not_admin")
        _aer_fail(403, REFUSED)
    return steam


# Argument forms (design 1.2).

_AER_HEX = frozenset("0123456789abcdef")


def _aer_ident(raw):
    """`("full", 32 hex)` or `("code", 12 hex)`: lowercased, dashes stripped;
    anything else is `400 bad_argument`."""
    s = (raw or "").strip().lower().replace("-", "")
    if s and set(s) <= _AER_HEX:
        if len(s) == 32:
            return "full", s
        if len(s) == 12:
            return "code", s
    _aer_fail(400, "bad_argument")


def _aer_steam(raw):
    s = raw or ""
    lo, hi = AER_CONTRACT_BOUNDS["STEAM_ID_MIN_DIGITS"], AER_CONTRACT_BOUNDS["STEAM_ID_MAX_DIGITS"]
    if lo <= len(s) <= hi and s.isascii() and s.isdigit():
        return s
    _aer_fail(400, "bad_argument")


def _aer_int(request, name, default, lo, hi):
    raw = request.query_params.get(name)
    if raw is None:
        return default
    if not (raw.isascii() and raw.isdigit()) or not lo <= int(raw) <= hi:
        _aer_fail(400, "bad_argument (%s)" % name)
    return int(raw)


def _aer_pages(shape, c):
    """Page count for `c` selected games (design 1.2): game and series
    `ceil(c/5)`; pair and player `1 + ceil(c/5)`, page 1 the summary. Shared by
    route, bot and tests."""
    per = AER_CONTRACT_BOUNDS["PAGE_GAMES"]
    games = (c + per - 1) // per
    return games + 1 if shape in ("pair", "player") else games


def _aer_require_games(c):
    """The shared empty-cohort check (design 1.3): `404 not_found` at `c == 0`,
    before the page bound, windows, the audit and any send."""
    if c == 0:
        _aer_fail(404, "not_found")


# Selectors (design 1.3): `matches` only, in the bind form the EXPLAIN gates
# of item 1a-1 read (test_admin_evidence_explain_pg.py holds the same text).

R1_ID_SQL = """
SELECT m.id, m.ended_at FROM matches m
 WHERE m.id = CAST(:id AS uuid)"""

R1_CODE_SQL = """
SELECT m.id FROM matches m
 WHERE LEFT(REPLACE(m.id::text, '-', ''), 12) = CAST(:code AS text)
 LIMIT 2"""

R2_SERIES_ROW_SQL = """
SELECT s.id FROM ranked_series s WHERE s.id = CAST(:id AS uuid)"""

R2_GAME_SERIES_SQL = """
SELECT m.series_id FROM matches m WHERE m.id = CAST(:id AS uuid)"""

R2_SERIES_SQL = """
SELECT m.id, m.ended_at FROM matches m
 WHERE m.series_id = CAST(:sid AS uuid)
 ORDER BY m.ended_at, m.id
 LIMIT CAST(:lim AS integer)"""

R3_PAIR_SQL = """
SELECT u.id, u.ended_at FROM (
  (SELECT m.id, m.ended_at FROM matches m
    WHERE m.player1_id = CAST(:a AS uuid) AND m.player2_id = CAST(:b AS uuid)
    ORDER BY m.ended_at DESC, m.id DESC LIMIT CAST(:games AS integer))
  UNION ALL
  (SELECT m.id, m.ended_at FROM matches m
    WHERE m.player1_id = CAST(:b AS uuid) AND m.player2_id = CAST(:a AS uuid)
    ORDER BY m.ended_at DESC, m.id DESC LIMIT CAST(:games AS integer))
) u
 ORDER BY u.ended_at DESC, u.id DESC
 LIMIT CAST(:games AS integer)"""

R4_PLAYER_SQL = """
SELECT u.id, u.ended_at FROM (
  (SELECT m.id, m.ended_at FROM matches m
    WHERE m.player1_id = CAST(:s AS uuid)
    ORDER BY m.ended_at DESC, m.id DESC LIMIT CAST(:games AS integer))
  UNION ALL
  (SELECT m.id, m.ended_at FROM matches m
    WHERE m.player2_id = CAST(:s AS uuid)
    ORDER BY m.ended_at DESC, m.id DESC LIMIT CAST(:games AS integer))
) u
 ORDER BY u.ended_at DESC, u.id DESC
 LIMIT CAST(:games AS integer)"""

PLAYER_BY_STEAM_SQL = """
SELECT p.id FROM players p WHERE p.steam_id = :steam AND p.deleted_at IS NULL"""

SUBJECTS_SQL = """
SELECT p.id, p.steam_id, p.display_name FROM players p
 WHERE p.id = ANY(CAST(:ids AS uuid[]))"""

FLAGS_SQL = """
SELECT f.id, f.match_id, f.flag_reason, f.flag_details, f.reviewed_at, f.created_at
  FROM flagged_matches f
 WHERE f.match_id = ANY(CAST(:ids AS uuid[]))
 ORDER BY f.id"""

GAME_ROWS_SQL = ("SELECT %s, m.p1_rounds_won, m.p2_rounds_won, m.photon_room_id FROM matches m "
                 "WHERE m.id = ANY(CAST(:ids AS uuid[]))" % _SELECT_LIST)

AUDIT_SQL = """
INSERT INTO admin_actions (id, admin_steam_id, action, target_steam_id, target_match_id,
                           target_series_id, details, created_at)
VALUES (CAST(:id AS uuid), :admin, 'evidence_report', :t_steam, CAST(:t_match AS uuid),
        CAST(:t_series AS uuid), CAST(:details AS jsonb), now())"""


async def _aer_rows(db, sql, params):
    from sqlalchemy import text
    result = await db.execute(text(sql), params)
    return [dict(r) for r in result.mappings().all()]


async def _select_game(db, ident):
    kind, s = ident
    if kind == "full":
        rows = await _aer_rows(db, R1_ID_SQL, {"id": s})
    else:
        rows = await _aer_rows(db, R1_CODE_SQL, {"code": s})
        if len(rows) > 1:
            _aer_fail(400, "bad_argument (code ambiguous; use the full id)")
    if not rows:
        _aer_fail(404, "not_found")
    return rows[0]["id"]


async def _select_series(db, ident):
    """R2: a 32-hex value is a series id first; only with no series row is it
    resolved as a game (R1's selector) and that game's series taken."""
    kind, s = ident
    sid = None
    if kind == "full":
        if await _aer_rows(db, R2_SERIES_ROW_SQL, {"id": s}):
            sid = s
    if sid is None:
        gid = await _select_game(db, ident)
        got = await _aer_rows(db, R2_GAME_SERIES_SQL, {"id": str(gid)})
        sid = got[0]["series_id"] if got else None
        if sid is None:
            _aer_fail(404, "not_found")
    lim = AER_CONTRACT_BOUNDS["SERIES_GAMES_MAX"] + 1
    rows = await _aer_rows(db, R2_SERIES_SQL, {"sid": str(sid), "lim": lim})
    if len(rows) > AER_CONTRACT_BOUNDS["SERIES_GAMES_MAX"]:
        _aer_fail(500, "too_large")
    return sid, [r["id"] for r in rows]


async def _aer_player_id(db, steam):
    rows = await _aer_rows(db, PLAYER_BY_STEAM_SQL, {"steam": steam})
    if not rows:
        _aer_fail(404, "not_found")
    return rows[0]["id"]


# Bounds in process (design 4.6, 2.6). Plain counters, so no primitive is
# bound to one event loop.

_RATE = {}
_INFLIGHT = [0]
_REBUILDING = [False]
_POLL_S = 0.01


def _rate_charge(actor, now=None):
    """At most RATE_MAX reports per actor per RATE_WINDOW_S, after the gate;
    over it, `429 rate` with `Retry-After`."""
    now = time.monotonic() if now is None else now
    window = AER_CONTRACT_BOUNDS["RATE_WINDOW_S"]
    q = _RATE.setdefault(actor, collections.deque())
    while q and now - q[0] >= window:
        q.popleft()
    if len(q) >= AER_CONTRACT_BOUNDS["RATE_MAX"]:
        retry = max(1, int(math.ceil(window - (now - q[0]))))
        _aer_fail(429, "rate", headers={"Retry-After": str(retry)})
    q.append(now)


async def _wait_until(pred, deadline):
    while not pred():
        if time.monotonic() >= deadline:
            _aer_fail(503, "deadline")
        await asyncio.sleep(_POLL_S)


# The api's population cache (design 2.6). `B` is measured once, at the first
# report, when every import of main.py has run.
_CACHE = [None]


def _aer_cache():
    if _CACHE[0] is None:
        _CACHE[0] = PopulationCache(base_rss_mb=process_rss_mb())
    return _CACHE[0]


def _display_key():
    return ("display", "all", registry_fingerprint(), DISPLAY_DEFAULTS["pop_days"],
            DISPLAY_DEFAULTS["lag_s"])


async def _leased(cache, db, key, deadline, basis=None):
    """The current generation for `key`, rebuilt when absent or expired (one
    rebuild at a time; waiting counts against the deadline), leased."""
    g = cache.current(key)
    if g is None:
        await _wait_until(lambda: not _REBUILDING[0], deadline)
        g = cache.current(key)
        if g is None:
            _REBUILDING[0] = True
            try:
                if basis is None:
                    g = await refresh_game_set(
                        cache, db, key, DISPLAY_DEFAULTS["pop_days"],
                        DISPLAY_DEFAULTS["lag_s"], deadline=deadline)
                else:
                    g = await refresh_window_source(
                        cache, db, key, basis, DISPLAY_DEFAULTS["pop_days"],
                        DISPLAY_DEFAULTS["lag_s"], deadline=deadline)
            finally:
                _REBUILDING[0] = False
    return cache.lease(g)


def _iso(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return _dt.datetime.fromtimestamp(value, _dt.timezone.utc).isoformat()
    return value.isoformat()


def _code(match_id):
    return str(match_id).replace("-", "")[:12]


def _text(value):
    return _aer_enc((value or "")[:AER_CONTRACT_BOUNDS["TEXT_MAX"]])


def _catalog_row(entry, spread=None):
    row = {"ki": entry.ki, "key": entry.key, "base": entry.base, "fam": entry.fam,
           "unit": entry.unit, "kind": entry.kind}
    if not entry.is_window:
        spread = spread or {}
        row.update({"p50": spread.get("pop_p50"), "p90": spread.get("pop_p90"),
                    "p99": spread.get("pop_p99")})
    return row


class _Report:
    """One request's reads and leases; every lease is released by `close`."""

    def __init__(self, db, cache, deadline):
        self.db, self.cache, self.deadline = db, cache, deadline
        self.leases = []

    async def lease(self, key, basis=None):
        g = await _leased(self.cache, self.db, key, self.deadline, basis)
        self.leases.append(g)
        return g

    def close(self):
        while self.leases:
            lease = self.leases[-1]
            self.leases[-1:] = []
            self.cache.release(lease)


async def _game_rows(db, ids):
    rows = await _aer_rows(db, GAME_ROWS_SQL, {"ids": [str(i) for i in ids]})
    by_id = {str(r["id"]): r for r in rows}
    return [by_id[str(i)] for i in ids if str(i) in by_id]


async def _flag_rows(db, ids):
    out = collections.defaultdict(list)
    for r in await _aer_rows(db, FLAGS_SQL, {"ids": [str(i) for i in ids]}):
        out[str(r["match_id"])].append(r)
    return out


def _pop_fill(cell, values):
    """A ranked base key's population slots from the leased game set."""
    if cell["state"] != "ok" or values is None:
        cell.update({"pop_rank": None, "pop_n": len(values) if values is not None else 0})
        return
    pm = pop_measures(values, cell["val"])
    cell.update({"pop_rank": pm["pop_rank"], "pop_n": pm["pop_n"]})


async def _game_page(rep, games, cohort, subjects, game_set):
    db = rep.db
    flags = await _flag_rows(db, [g["id"] for g in games])
    steam_of = {str(pid): s["steam_id"] for pid, s in subjects.items()}
    index = {str(pid): s["i"] for pid, s in subjects.items()}
    steam_to_subject = {s["steam_id"]: s["i"] for s in subjects.values()}
    out = []
    for row in games:
        mid = str(row["id"])
        current = current_flags(flags.get(mid, ()))
        seats = []
        for seat in AER_SEATS:
            account = row["player1_id" if seat == "p1" else "player2_id"]
            base = await read_baseline(db, account, row["ended_at"], row["id"],
                                       covered=[str(c) for c in cohort])
            cells = game_seat_cells(row, account, current.get(steam_of.get(str(account))),
                                    base)
            for c in cells:
                e = REPORT_REGISTRY[c["ki"]]
                if e.ranked:
                    _pop_fill(c, game_set.values.get(e.ki))
            seats.append({"subject": index[str(account)],
                          "reporter": aer_reporter_seat(row) == seat,
                          "cells": [wire_row("seat", c) for c in cells]})
        inv = None
        if row.get("invalidated_at") is not None:
            inv = _text(row.get("invalidation_reason") or "")
        out.append({"match_id": mid, "code": _code(row["id"]),
                    "ended_at": _iso(row["ended_at"]), "is_ranked": bool(row["is_ranked"]),
                    "invalidated": inv,
                    "series_id": str(row["series_id"]) if row["series_id"] else None,
                    "rounds": [row["p1_rounds_won"], row["p2_rounds_won"]],
                    "seats": seats, "pair_cells": [],
                    "flags": [dict(f, created_at=_iso(f["created_at"]))
                              for f in flag_list(flags.get(mid, ()), steam_to_subject,
                                                 current)]})
    return out


async def _summary_page(rep, shape, rows, requested, subjects, accounts):
    """Page 1 of a pair or player report (design 5.5): the windows over the
    covered games and one display cell per window key of each window."""
    db = rep.db
    index = {str(pid): s["i"] for pid, s in subjects.items()}
    steam_of = {str(pid): s["steam_id"] for pid, s in subjects.items()}
    flags = await _flag_rows(db, [r["id"] for r in rows])
    if shape == "player":
        plan = [(accounts[0], None, "player")]
    else:
        plan = [(accounts[0], accounts[1], "pair"), (accounts[1], accounts[0], "pair")]
    windows, summary = [], []
    cohort = [str(r["id"]) for r in rows]
    oldest = rows[-1]
    source_basis = plan[0][2]
    source = await rep.lease(_display_key() + (source_basis,), basis=source_basis)
    win_at = source.computed_at
    for oi, (acc, partner, basis) in enumerate(plan):
        base = await read_baseline(db, acc, oldest["ended_at"], oldest["id"],
                                   covered=cohort, partner=partner)
        cells = window_cells(rows, acc, basis, base, partner)
        for cell_index, c in enumerate(cells):
            comp = c["comparability"]
            c = {key: value for key, value in c.items() if key != "comparability"}
            cells[cell_index] = c
            if c["state"] != "ok" or not c["n"]:
                continue
            w = REPORT_REGISTRY[c["ki"]]
            r = rep.cache.memo_get(comp, source)
            if r is None:
                dist = window_population(source.values.get(w.base, array("d")),
                                         source.offsets.get(w.base, array("i", [0])),
                                         w.agg.split(".")[0], c["n"])
                r = rep.cache.memo_put(comp, source, {"distribution": dist},
                                       len(dist) * 8 + 64)
            measures = pop_measures(r["distribution"], c["val"])
            for k in ("pop_rank", "pop_n", "pop_p50", "pop_p90", "pop_p99"):
                c[k] = measures[k]
        windows.append({"oi": oi, "basis": basis,
                        "subj": ["seat", index[str(acc)],
                                 index[str(partner)] if partner is not None else None],
                        "games": requested, "covered": len(rows),
                        "flag_obs": flag_obs(flags, steam_of.get(str(acc))),
                        "newest": _code(rows[0]["id"]), "oldest": _code(oldest["id"])})
        summary.append({"oi": oi, "cells": [wire_row("summary", c) for c in cells]})
    return windows, summary, win_at


# ── Evidence sections (phase 2, B10) ───────────────────────────────────────
#
# The report also reads the card-draw, combat and identity-clock evidence
# tables and shows what they store, under the stored column names (a combat
# sums entry under its stored key). Uncolored, as 1a: no class, no rank, no
# rule, and no rules revision id is shown. Each source is read inside its own
# SAVEPOINT, so a failed read leaves that section `unavailable` and the
# transaction usable for the rest of the page (a caught asyncpg error would
# otherwise end it, lesson 235).

# A page carries sections only when the caller asks for them: a 1a caller
# (an older bot) receives a body with no section key and a 1a audit row, so
# either deploy order of the api and the bot serves every page.
SECTIONS_HEADER = "X-Evidence-Sections"
SECTIONS_PHASE = "2"
SECTION_SOURCES = ("card", "combat", "identity_clock")
SECTION_STATES = ("ok", "no_record", "unavailable")
SECTION_SEAT_STATES = ("ok", "no_record", "conflict", "purged")
SECTION_SWITCHES = ("accept", "worker", "purge")
# A seat's contribution groups: `contribN.` the contributions whose stored
# match_id is the game's match (shown and totalled), `unattributedN.` the
# combat contributions under the game's identity whose stored match_id is
# not (another match's, or NULL from before migration 401: shown, in no
# total; B10-R2 H1, B10-R3 H1).
SECTION_CONTRIB_WORDS = ("contrib", "unattributed")
_CARD_COUNTERS = ("hands", "slots", "notrun_hands") + tuple(
    "%s_%s" % (m, r) for m in ("obs", "exp", "var") for r in ("common", "uncommon", "rare"))
_SECTION_SPEC = {
    "card": {"ev": "card_evidence", "games": "card_games", "contrib": "card_contrib",
             "daily": "card_player_daily", "day": "day", "by_match": True,
             "seat": ("pool_state", "deal_profile", "header_mod_version", "received_at"),
             "game": ("series_sc", "processed_at", "finalized_at", "derive_fault",
                      "fault_attempts", "parked_at", "retry_at"),
             "contrib_cols": ("deal_profile",) + _CARD_COUNTERS,
             "provenance": ("match_id",),
             "daily_cols": ("games",) + _CARD_COUNTERS},
    "combat": {"ev": "combat_evidence", "games": "combat_games", "contrib": "combat_contrib",
               "daily": "combat_player_daily", "day": "utc_day", "by_match": True,
               "seat": ("consts_version", "header_mod_version", "received_at"),
               "game": ("coverage", "records_n", "record_faults", "processed_at",
                        "finalized_at"),
               "contrib_cols": ("consts_version", "sums"),
               "provenance": ("match_id",),
               "daily_cols": ("games", "sums")},
    "identity_clock": {"ev": "identity_clock_evidence", "games": "identity_clock_games",
                       "contrib": None, "daily": None, "day": None, "by_match": False,
                       "seat": ("consts_version", "post_clock", "post_proc", "post_sw_ms",
                                "post_unity_ms", "post_photon_ts", "conn_class",
                                "conn_ranges", "received_at"),
                       "game": ("records_n", "paired_points", "processed_at", "finalized_at"),
                       "contrib_cols": (), "provenance": (), "daily_cols": ()},
}
# A stored jsonb key or a stored word shown as part of a fact name: 1 to 24
# of a-z, 0-9 and `_`. A character test, not a regular expression: importing
# `re` into this module moved the route manifest pins of eleven routes outside
# it (measured with repin_route_manifest.py). Every fact name matches
# FACT_NAME_PATTERN, the bot's `_AER_FACT_NAME`.
_FACT_KEY_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789_")
FACT_NAME_PATTERN = "[a-z0-9_.]{1,%d}" % AER_CONTRACT_BOUNDS["FACT_NAME_MAX"]


def _fact_key(word):
    return isinstance(word, str) and 0 < len(word) <= 24 and all(
        ch in _FACT_KEY_CHARS for ch in word)


def section_sql(src):
    """One source's statements. Each is keyed (an index prefix) and LIMITed
    by a bound, every bind typed by CAST; no LATERAL."""
    s = _SECTION_SPEC[src]
    out = {
        "keys": ("SELECT DISTINCT e.stable_game_key FROM %s e "
                 "WHERE e.attach_key = ANY(CAST(:rooms AS varchar[])) "
                 "AND e.seat_player_id = ANY(CAST(:pids AS uuid[])) "
                 "LIMIT CAST(:n AS integer)" % s["ev"]),
        "records": ("SELECT e.stable_game_key, e.attach_key, e.seat_player_id, "
                    "e.other_player_id, e.conflict_at, e.conflict_kind, e.lists_purged_at, %s "
                    "FROM %s e WHERE e.stable_game_key = ANY(CAST(:keys AS varchar[])) "
                    "ORDER BY e.stable_game_key, e.seat_player_id LIMIT CAST(:n AS integer)"
                    % (", ".join("e." + c for c in s["seat"]), s["ev"])),
        "games": ("SELECT g.stable_game_key, g.pair_lo, g.pair_hi, g.match_id, %s "
                  "FROM %s g WHERE g.stable_game_key = ANY(CAST(:keys AS varchar[])) "
                  "ORDER BY g.stable_game_key, g.pair_lo, g.pair_hi LIMIT CAST(:n AS integer)"
                  % (", ".join("g." + c for c in s["game"]), s["games"])),
        "switches": ("SELECT r.key, r.value FROM runtime_settings r "
                     "WHERE r.key = ANY(CAST(:keys AS varchar[])) ORDER BY r.key "
                     "LIMIT CAST(:n AS integer)"),
    }
    if s["by_match"]:
        out["by_match"] = ("SELECT g.stable_game_key FROM %s g "
                           "WHERE g.match_id = ANY(CAST(:ids AS uuid[])) "
                           "ORDER BY g.stable_game_key LIMIT CAST(:n AS integer)" % s["games"])
    if s["contrib"]:
        # the contributions stored for the page's matches, found by their own
        # match_id (ix_<contrib>_match, migration 401) whether or not a record
        # or a games row names the game (B10-R3 H2)
        out["contrib_keys"] = ("SELECT DISTINCT c.stable_game_key FROM %s c "
                               "WHERE c.match_id = ANY(CAST(:ids AS uuid[])) "
                               "ORDER BY c.stable_game_key LIMIT CAST(:n AS integer)"
                               % s["contrib"])
        out["contrib"] = (
            "SELECT c.stable_game_key, c.pair_lo, c.pair_hi, c.subject_player_id, c.source, "
            "c.coverage, c.computed_at, %s FROM %s c "
            "WHERE c.stable_game_key = ANY(CAST(:keys AS varchar[])) "
            "ORDER BY c.stable_game_key, c.pair_lo, c.pair_hi, c.subject_player_id, "
            "c.computed_at DESC, c.source LIMIT CAST(:n AS integer)"
            % (", ".join("c." + c for c in s["provenance"] + s["contrib_cols"]),
               s["contrib"]))
        out["daily"] = (
            "SELECT d.source, d.coverage, %s FROM %s d "
            "WHERE d.subject_player_id = CAST(:s AS uuid) AND d.%s >= CAST(:d0 AS date) "
            "ORDER BY d.%s DESC, d.source, d.coverage LIMIT CAST(:n AS integer)"
            % (", ".join("d." + c for c in s["daily_cols"]), s["daily"], s["day"], s["day"]))
    return out


SECTION_SQL = {src: section_sql(src) for src in SECTION_SOURCES}


def _jsonb(raw):
    """A jsonb value as a dict: a text() read returns JSONB as text."""
    if isinstance(raw, str):
        raw = json.loads(raw) if raw else {}
    return raw if isinstance(raw, dict) else {}


def _section_day0():
    """The first UTC day of the account's `pop_days` days, today included."""
    today = _dt.datetime.now(_dt.timezone.utc).date()
    return today - _dt.timedelta(days=DISPLAY_DEFAULTS["pop_days"] - 1)


async def _section_rows(db, sql, params):
    """The sections' row reader: the body of `_aer_rows`, kept as its own
    function so the privacy pass's joined summary of `_aer_rows`, whose rows
    the 1a display slots show, never takes on the sections' calling context
    (a condition on the page's game rows)."""
    from sqlalchemy import text
    result = await db.execute(text(sql), params)
    return [dict(r) for r in result.mappings().all()]


async def _section_read(db, src, games, accounts, day0, phase3=False):
    """One source's stored rows for the page's games and, on a summary page,
    the subjects' daily rows. The stable keys come from three lookups: the
    records naming a game's room and seat (`keys`), the games rows attached
    to a game's match (`by_match`), and the contributions whose stored
    match_id is a game's match (`contrib_keys`, B10-R3 H2); the records,
    games rows and contributions are then read by those keys. `truncated` is
    set when one of the capped reads (keys, by_match, contrib_keys, records,
    games, contrib, daily) returned exactly its LIMIT. The switch read is outside that rule: it asks for its three
    named keys under LIMIT 3, so three rows are every switch, never a cut."""
    sql, b = SECTION_SQL[src], AER_CONTRACT_BOUNDS
    data = {"records": [], "games": [], "contrib": [], "daily": {}, "switches": {},
            "truncated": False}
    rooms = sorted({g["room"] for g in games if g["room"]})
    pids = sorted({p for g in games for p in (g["p1"], g["p2"])})
    keys = set()
    if rooms:
        found = await _section_rows(db, sql["keys"], {"rooms": rooms, "pids": pids,
                                                  "n": b["SECTION_KEYS_MAX"]})
        keys.update(r["stable_game_key"] for r in found)
        data["truncated"] |= len(found) == b["SECTION_KEYS_MAX"]
    if "by_match" in sql:
        found = await _section_rows(db, sql["by_match"], {"ids": [g["id"] for g in games],
                                                      "n": b["SECTION_KEYS_MAX"]})
        keys.update(r["stable_game_key"] for r in found)
        data["truncated"] |= len(found) == b["SECTION_KEYS_MAX"]
    if "contrib_keys" in sql:
        found = await _section_rows(db, sql["contrib_keys"], {"ids": [g["id"] for g in games],
                                                          "n": b["SECTION_KEYS_MAX"]})
        keys.update(r["stable_game_key"] for r in found)
        data["truncated"] |= len(found) == b["SECTION_KEYS_MAX"]
    if keys:
        for part in ("records", "games") + (("contrib",) if "contrib" in sql else ()):
            rows = await _section_rows(db, sql[part], {"keys": sorted(keys),
                                                   "n": b["SECTION_ROWS_MAX"]})
            data[part] = rows
            data["truncated"] |= len(rows) == b["SECTION_ROWS_MAX"]
    if phase3:
        data["findings"], cut = await _findings_read(db, src, data, games)
        data["truncated"] |= cut
    names = ["%s_evidence_%s" % (src, w) for w in SECTION_SWITCHES]
    data["switches"] = {r["key"]: r["value"] for r in await _section_rows(
        db, sql["switches"], {"keys": names, "n": len(names)})}
    if "daily" in sql:
        for acc in accounts:
            rows = await _section_rows(db, sql["daily"], {"s": acc, "d0": day0,
                                                      "n": b["SECTION_DAILY_ROWS_MAX"]})
            data["daily"][acc] = rows
            data["truncated"] |= len(rows) == b["SECTION_DAILY_ROWS_MAX"]
    return data


async def read_sections(db, games, accounts=(), phase3=False):
    """Every source's data for `games` (`_section_games` dicts), or None for a
    source whose read failed: that section alone reads `unavailable`. With
    `phase3` each source's data also carries its stored findings
    (`_findings_read`), read inside the same savepoint."""
    day0 = _section_day0()
    out = {}
    for src in SECTION_SOURCES:
        try:
            async with db.begin_nested():
                out[src] = await _section_read(db, src, games, [str(a) for a in accounts], day0,
                                               phase3)
        except Exception as exc:  # noqa: BLE001 -- the section says so; the page answers
            _aer_log.warning("admin_evidence section %s unavailable: %s", src,
                             type(exc).__name__)
            out[src] = None
    return out


def _section_games(rows):
    return [{"id": str(r["id"]), "room": r.get("photon_room_id"),
             "p1": str(r["player1_id"]), "p2": str(r["player2_id"]),
             "ended": r.get("ended_at")} for r in rows]


def _fact(name, value):
    """One `[name, value]` fact: None stays None (not recorded), a bool is
    yes or no, a number its decimal text, a time its ISO text, text encoded
    and whole. No section value is shortened: of the text columns the
    sections show, the widest stored one is 64 characters (deal_profile,
    VARCHAR(64) in card_evidence and card_contrib, migration 370), and the
    two without a stored width (a switch's runtime_settings value, TEXT, and
    `_fault_words`' joined words) are bounded only by RESPONSE_BYTES_MAX,
    which refuses the whole report rather than cut a value."""
    if value is None:
        return [name, None]
    if isinstance(value, bool):
        return [name, "yes" if value else "no"]
    if isinstance(value, int):
        return [name, "%d" % value]
    if isinstance(value, float):
        return [name, "%r" % value]
    if isinstance(value, (_dt.datetime, _dt.date)):
        return [name, value.isoformat()]
    return [name, _section_enc("%s" % value)]


def _section_enc(value):
    """A section value's encoder: the same reversible escape as `_aer_enc`
    (test_admin_evidence_sections checks the two agree), kept as its own
    function so section values never join `_aer_enc`'s analysed summary,
    which the display slots `name`, `reason` and `invalidated` read."""
    out = []
    for ch in value:
        cp = ord(ch)
        if ch == _BACKSLASH:
            out.append(_BACKSLASH * 2)
        elif cp in AER_ESC:
            out.append("%su{%x}" % (_BACKSLASH, cp))
        else:
            out.append(ch)
    return "".join(out)


def _record_ident(row):
    """An evidence record's game identity: (stable_game_key, lo, hi), its two
    seats with the lower first, as the workers key a record (LEAST/GREATEST
    of seat_player_id and other_player_id). Records are the only rows whose
    identity is derived; a games or contribution row's is `_stored_ident`."""
    lo, hi = sorted((str(row["seat_player_id"]), str(row["other_player_id"])))
    return row["stable_game_key"], lo, hi


def _stored_ident(row):
    """A games or contribution row's identity exactly as stored:
    (stable_game_key, pair_lo, pair_hi), the tables' key prefix, never
    reordered (B10-R2 H2). The games tables require pair_lo < pair_hi; the
    contribution tables do not, so a contribution stored as (K, B, A) is
    another identity than the game's (K, A, B) and is not the game's."""
    return row["stable_game_key"], str(row["pair_lo"]), str(row["pair_hi"])


def _game_idents(data, game):
    """The identity selection of `_game_records` (its docstring states the
    rule), shared with the phase-3 findings: the game's sorted pair, room,
    the pair's records and games rows with their identities, the roomed and
    elsewhere identity sets, the selected identities and the pairing word."""
    pair = tuple(sorted((game["p1"], game["p2"])))
    room = game["room"]
    recs = [(_record_ident(r), r) for r in data["records"]]
    recs = [(i, r) for i, r in recs if i[1:] == pair]
    allrows = [(_stored_ident(g), g) for g in data["games"]]
    grows = [(i, g) for i, g in allrows if i[1:] == pair]
    attached = {i for i, g in grows
                if g["match_id"] is not None and str(g["match_id"]) == game["id"]}
    elsewhere = {i for i, g in grows
                 if g["match_id"] is not None and str(g["match_id"]) != game["id"]}
    roomed = {i for i, r in recs if r["attach_key"] == room}
    if attached:
        idents, paired = attached, "attached"
    else:
        idents = roomed - elsewhere
        paired = "waiting" if idents else None
    return pair, room, recs, grows, roomed, elsewhere, idents, paired


def _game_records(src, data, game):
    """The source's records, games rows and contributions that belong to
    `game`, associated by stored identity (stable_game_key, pair_lo,
    pair_hi) with the game's own pair, never by stable key alone (one stable
    key can carry several pairs): the identities whose games row the pairing
    worker attached to this match; when none is attached yet, the identities
    under which a record names the game's room and whose games row is not
    attached to another match (`waiting`). Of the selected identities'
    records, only those whose OWN attach key is the game's room are the
    game's (the workers' rule, seat_evidence.attached_records: a record is
    never evidence about a match its own key does not name). `other` counts
    the pair's records that are another attachment's: under a selected
    identity but naming another room, or naming this room under an identity
    whose games row is attached to another match. The contributions are
    `_game_contrib`'s: `contrib` those whose stored match_id is this match,
    under any stable key of the game's pair; `loose` the combat ones under a
    selected identity whose stored match_id is not; each seat takes those
    whose subject it is."""
    pair, room, recs, grows, roomed, elsewhere, idents, paired = _game_idents(data, game)
    rows = [g for i, g in grows if i in idents]
    shown = [r for i, r in recs if i in idents and r["attach_key"] == room]
    other = [r for i, r in recs if (i in idents and r["attach_key"] != room)
             or (i in (roomed & elsewhere) - idents and r["attach_key"] == room)]
    contrib, loose = _game_contrib(src, data, game, pair, idents)
    return paired, shown, rows, len(other), contrib, loose


def _derived_for(c, game):
    """Whether contribution row `c` stores `game`'s match as the match it
    was derived for: its match_id equals the game's id. card_contrib.match_id
    is written by card_evidence._write_contrib (370) and
    combat_contrib.match_id by combat_evidence._write_contributions (401),
    each in the INSERT that creates the row, from the match the worker
    attached in that transaction; neither worker's re-attachment of a games
    row writes it. NULL (a combat row written before 401) is no match."""
    return c["match_id"] is not None and str(c["match_id"]) == game["id"]


def _game_contrib(src, data, game, pair, idents):
    """`game`'s contributions, `(contrib, loose)`. `contrib`: every row of
    the game's exact stored pair whose stored match_id is this game's
    (`_derived_for`), whatever match the games row is attached to now and
    whether or not a record names the game; shown and totalled. `loose`
    (combat only): the rows under a selected identity whose stored match_id
    is another match's or NULL, shown under the word `unattributed` and in
    no total (B10-R3 H1: neither the games row's attachment nor a read-time
    condition establishes which match a kept row was derived for; the
    stored match_id does). Card keeps `loose` empty, as before: a card row
    of another or no match_id is not this game's. Identity-clock stores no
    contributions."""
    mine = [c for c in data["contrib"] if _stored_ident(c)[1:] == pair and _derived_for(c, game)]
    if src == "card":
        return mine, []
    held = [c for c in data["contrib"] if _stored_ident(c) in idents]
    return mine, [c for c in held if not _derived_for(c, game)]


def _seat_state(rec):
    if rec["conflict_at"] is not None or rec["conflict_kind"] is not None:
        return "conflict"
    if rec["lists_purged_at"] is not None:
        return "purged"
    return "ok"


def _sums_facts(prefix, raw):
    """A stored sums object: per admitted key its bin count and plain total,
    then the count of keys or values that are not a named list of numbers."""
    sums = _jsonb(raw)
    out, unnamed = [], 0
    for k in sorted(sums):
        v = sums[k]
        if (_fact_key(k) and isinstance(v, list) and all(
                isinstance(x, (int, float)) and not isinstance(x, bool) for x in v)):
            out += [_fact("%s%s.bins" % (prefix, k), len(v)),
                    _fact("%s%s.total" % (prefix, k), sum(v))]
        else:
            unnamed += 1
    if unnamed:
        out.append(_fact(prefix + "unnamed", unnamed))
    return out


def _contrib_facts(src, rows, word="contrib"):
    """A seat's contribution facts under one of SECTION_CONTRIB_WORDS: each
    row's group `<word><n>.`, then `<word>_more` for the rows past the cap.
    No row: `contrib=not_derived` for the attributed group, nothing for
    `unattributed`."""
    spec = _SECTION_SPEC[src]
    if spec["contrib"] is None:
        return []
    if not rows:
        return [_fact("contrib", "not_derived")] if word == "contrib" else []
    cap = AER_CONTRACT_BOUNDS["SECTION_CONTRIB_MAX"]
    out = []
    for i, c in enumerate(rows[:cap]):
        prefix = "%s%d." % (word, i + 1)
        out += [_fact(prefix + "source", c["source"]), _fact(prefix + "coverage", c["coverage"])]
        for col in spec["contrib_cols"]:
            if col == "sums":
                out += _sums_facts(prefix, c[col])
            else:
                out.append(_fact(prefix + col, c[col]))
    if rows[cap:]:
        out.append(_fact(word + "_more", len(rows[cap:])))
    return out


def _fault_words(raw):
    words = sorted(k for k in _jsonb(raw) if _fact_key(k))
    return ",".join(words) if words else "none"


def _seat_section(src, account, recs, contrib, loose=()):
    """One seat's state and facts. `contrib` and `loose` are the game's
    contributions (`_game_records`): those about `account` are shown whether
    or not the account sent a record of its own (the other seat's record can
    produce a `meas` contribution about it), `contrib`'s under `contribN.`,
    `loose`'s under `unattributedN.`. The state is the account's own record's:
    `no_record` without one, its facts then the contributions alone."""
    mine = [r for r in recs if str(r["seat_player_id"]) == account]
    about = [c for c in contrib if str(c["subject_player_id"]) == account]
    held = _contrib_facts(src, [c for c in loose if str(c["subject_player_id"]) == account],
                          "unattributed")
    if not mine:
        return "no_record", (_contrib_facts(src, about) if about else []) + held
    rec = mine[0]
    facts = [_fact("conflict_kind", rec["conflict_kind"]),
             _fact("lists_purged", rec["lists_purged_at"] is not None)]
    facts += [_fact(c, rec[c]) for c in _SECTION_SPEC[src]["seat"]]
    if mine[1:]:
        facts.append(_fact("records", len(mine)))
    facts += _contrib_facts(src, about) + held
    return _seat_state(rec), facts


def _game_facts(src, data, paired, rows, other):
    sw = data["switches"]
    facts = [_fact("paired", paired)]
    facts += [_fact(w, sw.get("%s_evidence_%s" % (src, w))) for w in SECTION_SWITCHES]
    if other:
        facts.append(_fact("other_game", other))
    if rows[1:]:
        facts.append(_fact("games_rows", len(rows)))
    if rows:
        g = rows[0]
        for c in _SECTION_SPEC[src]["game"]:
            facts.append(_fact(c, _fault_words(g[c]) if c == "record_faults" else g[c]))
    return facts


def game_section(src, data, game, index):
    """One game's section for one source (B10 phase 2): the game facts, then
    per seat (p1, p2) its state word and facts."""
    if data is None:
        return {"src": src, "state": "unavailable", "truncated": False, "game": [],
                "seats": []}
    paired, recs, rows, other, contrib, loose = _game_records(src, data, game)
    seats = []
    for account in (game["p1"], game["p2"]):
        state, facts = _seat_section(src, account, recs, contrib, loose)
        seats.append({"subject": index[account], "state": state, "facts": facts})
    return {"src": src, "state": "ok" if recs else "no_record",
            "truncated": data["truncated"], "game": _game_facts(src, data, paired, rows, other),
            "seats": seats}


def _contrib_add(src, totals, row, extra=()):
    """Add one contribution or daily row into `totals`, by stored source."""
    source = row["source"] if _fact_key(row["source"]) else "unnamed"
    if src == "card":
        for col in tuple(extra) + _CARD_COUNTERS:
            totals["%s.%s" % (source, col)] += row[col] or 0
        return
    for col in extra:
        totals["%s.%s" % (source, col)] += row[col] or 0
    for k, v in _jsonb(row["sums"]).items():
        if _fact_key(k) and isinstance(v, list) and all(
                isinstance(x, (int, float)) and not isinstance(x, bool) for x in v):
            totals["%s.%s.total" % (source, k)] += sum(v)


def _contrib_row_key(c):
    """One stored contribution row's key within a window: its stored
    identity, subject and source (combat_contrib's primary key, 390), with
    the deal profile and stored match_id where the row carries them."""
    return _stored_ident(c) + (str(c["subject_player_id"]), c["source"],
                               c.get("deal_profile"), str(c.get("match_id")))


def summary_section(src, data, games, account, oi):
    """One window subject's section over the window's covered games (B10
    phase 2): counts, contribution totals, and the account's daily totals over
    its last `pop_days` UTC days. The counts are `games` (the covered games),
    `attached` and `waiting` (the games by their pairing state, from a
    record of either seat; a game with neither, for want of records or
    because its rows are another match's, is in neither count, and no
    summary count names another match's rows: the game section's
    `other_game` does), `with_record`, `conflict` and `purged` (the account's own
    records), and on identity-clock the account's stored `post_clock` and
    `conn_class` words. The
    contribution totals add every contribution about the account that
    `_game_records` attributes to a covered game (its stored match_id is that
    game's match), with or without the account's own record; `unattributed`
    counts the distinct contributions about the account shown as
    `unattributed` on a covered game and attributed to none of the covered
    games, which no total includes (a row stored for one covered game and
    held under another's identity is in that game's total and not counted
    again here)."""
    if data is None:
        return {"oi": oi, "src": src, "state": "unavailable", "truncated": False,
                "facts": [], "days30": []}
    counts, totals = collections.Counter(), collections.Counter()
    attributed, held = set(), set()
    for game in games:
        paired, recs, _rows, _other, contrib, loose = _game_records(src, data, game)
        held.update(_contrib_row_key(c) for c in loose if str(c["subject_player_id"]) == account)
        mine = [r for r in recs if str(r["seat_player_id"]) == account]
        counts["games"] += 1
        if paired:
            counts[paired] += 1
        for c in contrib:
            if str(c["subject_player_id"]) == account:
                _contrib_add(src, totals, c)
                attributed.add(_contrib_row_key(c))
        if not mine:
            continue
        counts["with_record"] += 1
        state = _seat_state(mine[0])
        if state != "ok":
            counts[state] += 1
        if src == "identity_clock":
            for col in ("post_clock", "conn_class"):
                word = mine[0][col]
                if word and _fact_key(word):
                    counts["%s.%s" % (col, word)] += 1
    facts = [_fact(k, counts[k]) for k in ("games", "with_record", "attached", "waiting",
                                           "conflict", "purged")]
    facts += [_fact(k, counts[k]) for k in sorted(counts) if "." in k]
    if _SECTION_SPEC[src]["contrib"] is not None:
        facts += [_fact(k, totals[k]) for k in sorted(totals)] or [
            _fact("contrib", "not_derived")]
        unattributed = len(held - attributed)
        if unattributed:
            facts.append(_fact("unattributed", unattributed))
    days = []
    if _SECTION_SPEC[src]["daily"] is not None:
        daily = collections.Counter()
        for row in data["daily"].get(account, ()):
            _contrib_add(src, daily, row, ("games",))
        days = [_fact(k, daily[k]) for k in sorted(daily)] or [_fact("daily", "not_derived")]
    return {"oi": oi, "src": src, "state": "ok" if counts["with_record"] else "no_record",
            "truncated": data["truncated"], "facts": facts, "days30": days}


# ── Phase 3 (B10): stored findings and evidence ranks ─────────────────────
#
# Asked for by a second header beside SECTIONS_HEADER. A phase-2 caller (an
# older bot) sends only SECTIONS_HEADER and receives the phase-2 body and a
# phase-2 audit row; a phase-2 api ignores PHASE3_HEADER and serves phase 2,
# which the new bot decodes (both phase-3 keys are optional there). Shown as
# stored, uncolored: no class, no mark, no rule, no rules revision, and no
# finding's details object (which a rule writes).
PHASE3_HEADER = "X-Evidence-Phase"
PHASE3_VALUE = "3"
# Each source's namespace in seat_evidence_findings (scope game): the stored
# dedup key is the prefix, then `<stable_game_key>|<lo>|<hi>`, the games row's
# identity (card_evidence.game_key, combat_evidence.dedup_key,
# identity_clock_evidence.ice_dedup_key; an equality test reads all three).
FINDING_PREFIX = {"card": "card ", "combat": "combat ", "identity_clock": "identity "}
# Two reads (B10-P3-R1 H1). By stored match: every game-scope finding whose
# stored match_id is one of the page's games, in the source's namespace, by
# the partial index ix_seat_evidence_findings_game_match (migration 402):
# these are the findings a game LISTS, whichever rows of the source the page
# read. By identity: the findings under the identities the page's rows name,
# by the unique index's (scope, dedup_key) prefix: these find the findings
# under a game's identity for another or no match, which are COUNTED.
FINDINGS_MATCH_SQL = ("SELECT f.dedup_key, f.rule_id, f.scope, f.computed_at, f.flag_id, f.match_id "
                      "FROM seat_evidence_findings f WHERE f.scope = 'game' "
                      "AND f.match_id = ANY(CAST(:ids AS uuid[])) "
                      "AND starts_with(f.dedup_key, CAST(:prefix AS text)) "
                      "ORDER BY f.match_id, f.dedup_key, f.rule_id LIMIT CAST(:n AS integer)")
FINDINGS_SQL = ("SELECT f.dedup_key, f.rule_id, f.scope, f.computed_at, f.flag_id, f.match_id "
                "FROM seat_evidence_findings f WHERE f.scope = 'game' "
                "AND f.dedup_key = ANY(CAST(:keys AS varchar[])) "
                "ORDER BY f.dedup_key, f.rule_id LIMIT CAST(:n AS integer)")


def _finding_keys(src, data):
    """The dedup keys of every identity the source's rows name: each record's
    (stable key and its two seats, lower first), each games row's and each
    contribution's stored identity. Sorted."""
    idents = {_record_ident(r) for r in data["records"]}
    idents |= {_stored_ident(g) for g in data["games"]}
    idents |= {_stored_ident(c) for c in data["contrib"]}
    return sorted("%s%s|%s|%s" % ((FINDING_PREFIX[src],) + i) for i in idents)


async def _findings_read(db, src, data, games):
    """The source's stored game-scope findings for the page: those whose
    stored match_id is one of `games` (`FINDINGS_MATCH_SQL`) and those under
    the identities the source's rows name (`FINDINGS_SQL`), each read
    LIMITed by SECTION_ROWS_MAX, merged once per (dedup_key, rule_id) (the
    unique index's key within scope game). Returns `(rows, truncated)`:
    truncated when either read returned exactly its LIMIT."""
    n = AER_CONTRACT_BOUNDS["SECTION_ROWS_MAX"]
    found, cut = [], False
    ids = [g["id"] for g in games]
    if ids:
        rows = await _section_rows(db, FINDINGS_MATCH_SQL, {
            "ids": ids, "prefix": FINDING_PREFIX[src], "n": n})
        found += rows
        cut |= len(rows) == n
    keys = _finding_keys(src, data)
    if keys:
        rows = await _section_rows(db, FINDINGS_SQL, {"keys": keys, "n": n})
        found += rows
        cut |= len(rows) == n
    merged = {}
    for f in found:
        merged.setdefault((f["dedup_key"], "%s" % f["rule_id"]), f)
    return [merged[k] for k in sorted(merged)], cut


def _finding_ident(src, dedup_key):
    """A stored dedup key's (stable key, lo, hi) in the source's namespace,
    or None for a key of another namespace or form."""
    prefix = FINDING_PREFIX[src]
    if not isinstance(dedup_key, str) or not dedup_key.startswith(prefix):
        return None
    parts = dedup_key[len(prefix):].rsplit("|", 2)
    return tuple(parts) if len(parts) == 3 else None


def _game_findings(src, data, game):
    """`game`'s stored findings for the source, `(listed, other)`. Listed:
    every finding whose dedup key names the game's pair (the stored key's
    two ids equal the game's sorted pair) and whose stored match_id is this
    game's match (`_derived_for`), whatever match the games row is attached
    to now. `other` counts the findings under one of the game's selected
    identities (`_game_idents`) whose stored match_id is another match's or
    NULL: not listed on this game."""
    pair, _room, _recs, _grows, _roomed, _elsewhere, idents, _paired = _game_idents(data, game)
    listed, other = [], 0
    for f in data.get("findings", ()):
        ident = _finding_ident(src, f["dedup_key"])
        if ident is None:
            continue
        if ident[1:] == pair and _derived_for(f, game):
            listed.append(f)
        elif ident in idents:
            other += 1
    return listed, other


def _finding_row(f):
    """One listed finding as stored: rule_id, scope, computed_at, and the
    flag it was posted as (flagged_matches.id), or None when not posted."""
    return [_section_enc("%s" % f["rule_id"]), _section_enc("%s" % f["scope"]),
            _iso(f["computed_at"]), None if f["flag_id"] is None else str(f["flag_id"])]


def _finding_order(f):
    return ("%s" % f["rule_id"], "%s" % f["scope"], _iso(f["computed_at"]) or "")


def phase3_game_section(sec, src, data, game):
    """Add the phase-3 findings to one game section built by `game_section`:
    the key `findings` (at most FINDINGS_MAX rows, `_finding_row`, in rule
    order), and the game facts `findings` (the count listed or past the
    cap), `findings_more` (past the cap) and `findings_unattributed` (under
    the game's identity, another or no match). An unavailable section gets
    an empty list and no fact."""
    if data is None:
        sec["findings"] = []
        return sec
    listed, other = _game_findings(src, data, game)
    listed = sorted(listed, key=_finding_order)
    cap = AER_CONTRACT_BOUNDS["FINDINGS_MAX"]
    sec["findings"] = [_finding_row(f) for f in listed[:cap]]
    extra = [_fact("findings", len(listed))]
    if listed[cap:]:
        extra.append(_fact("findings_more", len(listed[cap:])))
    if other:
        extra.append(_fact("findings_unattributed", other))
    sec["game"] = sec["game"] + extra
    return sec


def phase3_summary_section(sec, src, data, games):
    """Add the phase-3 counts to one summary section: `findings`, the
    distinct findings listed on a covered game, and `findings_unattributed`,
    the distinct ones under a covered game's identity listed on none."""
    if data is None:
        return sec
    listed, held = set(), set()
    for game in games:
        mine, _other = _game_findings(src, data, game)
        listed.update(f["dedup_key"] + "|" + "%s" % f["rule_id"] for f in mine)
        idents = _game_idents(data, game)[6]
        for f in data.get("findings", ()):
            if _finding_ident(src, f["dedup_key"]) in idents:
                held.add(f["dedup_key"] + "|" + "%s" % f["rule_id"])
    extra = [_fact("findings", len(listed))]
    if held - listed:
        extra.append(_fact("findings_unattributed", len(held - listed)))
    sec["facts"] = sec["facts"] + extra
    return sec


# ── Phase 3b: the evidence registry, families K and X (design 2.11) ──────
#
# Public arithmetic over stored contribution and daily rows: no threshold,
# weight or rule. Family K (card draw) ranks card_contrib's counters per game
# and card_player_daily's over the account's `pop_days` days, as
# card_measures.window_row names them; family X (combat) ranks each stored
# sums set's plain total. Each ranked per-game base key has its two window
# keys (design 2.1); each also has one daily key (agg `window`). The stratum
# is family-declared (`profile`: the stored deal_profile; `consts`: the
# stored consts_version); a cell carries its stored stratum value, and no
# population pools two strata.
EV_RARITIES = ("common", "uncommon", "rare")   # card_measures.RARITIES, under an equality test
EV_CARD_VARS = (("b4.rar.hands", "count"), ("b4.rar.slots", "count"),
                ("b4.rar.notrun", "count")) + tuple(
    ("b4.rar.%s.%s" % (m, r), unit) for m, unit in (("obs", "count"), ("exp", "count"),
                                                    ("var", "count2"), ("dev", "sd"))
    for r in EV_RARITIES)
# combat_measures.contributions' sets per stored source, under an equality test.
EV_COMBAT_SETS = (("self", ("a1s", "a1p")),
                  ("meas", ("a1m", "a1n", "p3dp0", "p3an0", "p3dp1", "p3an1")))
EV_PROV = {"self": "SELF", "meas": "MEAS"}
EV_COVERAGES = ("one", "paired")
EV_SPEC = {"card": {"fam": "K", "rec": "card_record", "daily": "card_daily",
                    "stratum": "profile", "col": "deal_profile", "day_col": "deal_profile"},
           "combat": {"fam": "X", "rec": "combat_contrib", "daily": "combat_player_daily",
                      "stratum": "consts", "col": "consts_version",
                      "day_col": "consts_version"}}
EV_SOURCES = ("card", "combat")
EV_DAILY_AGG = "window"
EV_STATES = ("ok", "not_derived", "unavailable")
EV_CELL_SLOTS = ("ki", "stratum", "basis", "n", "val", "pop_rank", "pop_n", "pop_p50",
                 "pop_p90", "pop_p99")


def _ev_vars(src):
    """`(var, unit, prov)` per base variable of the source's family."""
    if src == "card":
        return [(v, unit, prov) for v, unit in EV_CARD_VARS for prov in ("SELF", "MEAS")]
    return [("%s.total" % s, "count", EV_PROV[source])
            for source, sets in EV_COMBAT_SETS for s in sets]


def _expand_evidence():
    """Families K and X expanded: per variable, provenance and coverage one
    per-game base key; then exactly two window keys per base key; then one
    daily key per base key."""
    rows = []
    for src in EV_SOURCES:
        spec = EV_SPEC[src]
        for var, unit, prov in _ev_vars(src):
            for cov in EV_COVERAGES:
                rows.append(dict(fam=spec["fam"], var=var, prov=prov, scope="seat",
                                 source=spec["rec"], coverage=cov, agg="cell",
                                 stratum=spec["stratum"], unit=unit, kind="R"))
    entries = [AerEntry(ki=i, key=aer_key_id(r["var"], r["prov"], "seat", r["source"],
                                             r["coverage"], "cell", r["stratum"]),
                        base=None, decl=None, **r) for i, r in enumerate(rows)]
    bases = list(entries)
    for b in bases:
        for agg in WINDOW_AGGS:
            wagg = "%s.%s" % (agg, b.agg)
            entries.append(AerEntry(
                ki=len(entries), key=aer_key_id(b.var, b.prov, b.scope, b.source, b.coverage,
                                                wagg, b.stratum),
                fam=b.fam, var=b.var, prov=b.prov, scope=b.scope, source=b.source,
                coverage=b.coverage, agg=wagg, stratum=b.stratum, unit=b.unit, kind=b.kind,
                base=b.ki, decl=None))
    for b in bases:
        daily = EV_SPEC["card" if b.fam == "K" else "combat"]["daily"]
        entries.append(AerEntry(
            ki=len(entries), key=aer_key_id(b.var, b.prov, b.scope, daily, b.coverage,
                                            EV_DAILY_AGG, b.stratum),
            fam=b.fam, var=b.var, prov=b.prov, scope=b.scope, source=daily,
            coverage=b.coverage, agg=EV_DAILY_AGG, stratum=b.stratum, unit=b.unit,
            kind=b.kind, base=None, decl=None, bases=("player",)))
    return tuple(entries)


EV_REGISTRY = _expand_evidence()
EV_BASE_KI = {(e.source, e.var, e.prov, e.coverage): e.ki for e in EV_REGISTRY
              if not e.is_window}


def ev_census(entries=None):
    """Per family `[base, window, daily]` counts, from the registry itself."""
    entries = EV_REGISTRY if entries is None else entries
    out = {}
    for e in entries:
        row = out.setdefault(e.fam, [0, 0, 0])
        row[1 if e.is_window else (2 if e.agg == EV_DAILY_AGG else 0)] += 1
    return out


def ev_registry_problems(entries):
    """Every way `entries` departs from `_expand_evidence()`: an omitted,
    extra or duplicated entry, `ki` not each entry's position, a base key
    without exactly its two window keys and its one daily key."""
    problems = []
    keys = [e.key for e in entries]
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    if dupes:
        problems.append("duplicated entries: %s" % ", ".join(dupes))
    want = [e.key for e in _expand_evidence()]
    if [k for k in want if k not in keys]:
        problems.append("omitted entries")
    if [k for k in keys if k not in want]:
        problems.append("entries no declaration expands to")
    for i, e in enumerate(entries):
        if e.ki != i:
            problems.append("%s: ki %d at position %d" % (e.key, e.ki, i))
    for b in entries:
        if b.is_window or b.agg != "cell":
            continue
        aggs = sorted(w.agg.split(".")[0] for w in entries if w.base == b.ki)
        if aggs != sorted(WINDOW_AGGS):
            problems.append("%s: window aggregations %r" % (b.key, aggs))
        daily = [d for d in entries if d.agg == EV_DAILY_AGG and (d.var, d.prov, d.coverage,
                                                                  d.fam) == (
            b.var, b.prov, b.coverage, b.fam)]
        if len(daily) != 1:
            problems.append("%s: %d daily keys" % (b.key, len(daily)))
    return problems


def ev_fingerprint(entries=None):
    entries = EV_REGISTRY if entries is None else entries
    return hashlib.sha256("\n".join(e.key for e in entries).encode("utf-8")).hexdigest()[:8]


def _ev_num(value):
    """A stored number as a float, or None (not recorded; never a 0)."""
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _card_values(c):
    """card_measures.window_row's measures over one row of stored counters
    (a contribution, or a sum of daily rows): the counts, and per rarity the
    observed count, the expected count and variance out of fixed point, and
    the standardized deviation (unknown when the variance is not positive).
    A row with no hand in its expectation (`hands` 0 or not recorded: every
    hand it saw was NOT-RUN) has no rarity measure at all, design 2.11's
    NOT-RUN exclusion; its counts (hands, slots, notrun) stay."""
    fix = float(AER_CONTRACT_BOUNDS["CARD_FIXED_POINT"])
    hands = _ev_num(c.get("hands"))
    out = {"b4.rar.hands": hands, "b4.rar.slots": _ev_num(c.get("slots")),
           "b4.rar.notrun": _ev_num(c.get("notrun_hands"))}
    if hands is None or hands <= 0:
        return out
    for r in EV_RARITIES:
        obs, exp, var = (_ev_num(c.get("%s_%s" % (m, r))) for m in ("obs", "exp", "var"))
        exp = None if exp is None else exp / fix
        var = None if var is None else var / fix
        out["b4.rar.obs." + r], out["b4.rar.exp." + r], out["b4.rar.var." + r] = obs, exp, var
        dev = None
        if obs is not None and exp is not None and var is not None and var > 0:
            dev = (obs - exp) / math.sqrt(var)
        out["b4.rar.dev." + r] = dev
    return out


def _combat_values(source, sums):
    """Each of the stored source's sets' plain total from a sums object; a
    set that is not a list of numbers is not recorded."""
    sets = dict(EV_COMBAT_SETS).get(source, ())
    out = {}
    for s in sets:
        v = sums.get(s)
        if isinstance(v, list) and all(
                isinstance(x, (int, float)) and not isinstance(x, bool) for x in v):
            out["%s.total" % s] = float(sum(v))
    return out


def _ev_stratum(src, row):
    value = row.get(EV_SPEC[src]["col"])
    return None if value is None else "%s" % value


def ev_row_facts(src, row, source_kind="rec"):
    """One stored row's facts `(ki, stratum, value)`: every admitted base
    key (`rec`) or daily key (`daily`) with a value. A row whose source or
    coverage word is not a registered one, or with no stratum, has none."""
    prov = EV_PROV.get(row.get("source"))
    cov = row.get("coverage")
    stratum = _ev_stratum(src, row)
    if prov is None or cov not in EV_COVERAGES or stratum is None:
        return []
    spec = EV_SPEC[src]
    values = (_card_values(row) if src == "card"
              else _combat_values(row["source"], _jsonb(row.get("sums"))))
    out = []
    for var, value in values.items():
        ki = EV_BASE_KI.get((spec["rec"], var, prov, cov))
        if ki is None or value is None:
            continue
        if source_kind == "daily":
            ki = EV_DAILY_KI[ki]
        out.append((ki, stratum, value))
    return out


def _ev_daily_map():
    """Each per-game base key's daily key."""
    out = {}
    for d in EV_REGISTRY:
        if d.agg == EV_DAILY_AGG:
            src = "card" if d.fam == "K" else "combat"
            out[EV_BASE_KI[(EV_SPEC[src]["rec"], d.var, d.prov, d.coverage)]] = d.ki
    return out


EV_DAILY_KI = _ev_daily_map()


def ev_daily_sum(src, rows):
    """A subject's daily rows summed per (source, coverage, stratum): the
    counters (card) or each set's bins (combat), and `games`."""
    groups = collections.OrderedDict()
    for row in rows:
        k = (row.get("source"), row.get("coverage"), _ev_stratum(src, row))
        g = groups.setdefault(k, {"source": k[0], "coverage": k[1],
                                  EV_SPEC[src]["col"]: row.get(EV_SPEC[src]["col"]),
                                  "games": 0, "sums": {}})
        g["games"] += row.get("games") or 0
        if src == "card":
            for col in _CARD_COUNTERS:
                v = row.get(col)
                if v is not None:
                    g[col] = g.get(col, 0) + v
        else:
            for s, v in _jsonb(row.get("sums")).items():
                if isinstance(v, list) and all(
                        isinstance(x, (int, float)) and not isinstance(x, bool) for x in v):
                    g["sums"][s] = g["sums"].get(s, []) + [sum(v)]
    return list(groups.values())


class EvidenceDuplicate(Exception):
    """Two stored facts for one `(ki, stratum, match, subject)`: no evidence
    rank publishes (design 2.6's one fact per identity)."""


def ev_population(src, pop_rows, cut=False):
    """The window population source of one family from its population rows
    (contributions whose stored match is a window game, `EV_POP_SQL`): per
    `(ki, stratum, basis)` the kept units' values newest first, packed as
    `window_source_sql` packs them (units by newest game, then unit id, kept
    whole while the key's values fit WIN_VALUES_MAX, each unit's newest
    WIN_UNIT_DEPTH values), the truncated keys, and the count of units left
    out as incomplete. A row whose stored pair is not its match's sorted
    pair, or whose subject is not one of them, is no fact. A repeated
    `(ki, stratum, match, subject)` raises EvidenceDuplicate.

    `cut`: the read stopped at its row cap. The rows are newest game first,
    so each unit holds its newest values; a unit with WIN_UNIT_DEPTH of them
    is complete for every window, and any other unit may have older values
    past the cap: it is left out whole and counted, never ranked short
    (B10-P3-R1 H3)."""
    b = AER_CONTRACT_BOUNDS
    seen = set()
    facts = []
    for row in pop_rows:
        pair = tuple(sorted((str(row["player1_id"]), str(row["player2_id"]))))
        if (str(row["pair_lo"]), str(row["pair_hi"])) != pair:
            continue
        subject = str(row["subject_player_id"])
        if subject not in pair:
            continue
        partner = pair[1] if subject == pair[0] else pair[0]
        mid = str(row["match_id"])
        for ki, stratum, value in ev_row_facts(src, row):
            ident = (ki, stratum, mid, subject)
            if ident in seen:
                raise EvidenceDuplicate("%s population: repeated fact" % src)
            seen.add(ident)
            facts.append((ki, stratum, row["ended_at"], mid, subject, partner, value))
    out, truncated, partial = {}, set(), 0
    for basis in ("player", "pair"):
        units = collections.defaultdict(list)
        for ki, stratum, ended, mid, subject, partner, value in facts:
            unit = (subject, partner if basis == "pair" else "")
            units[(ki, stratum, unit)].append((ended, mid, value))
        per_key = collections.defaultdict(list)
        for (ki, stratum, unit), vals in units.items():
            vals.sort(key=lambda t: (t[0], t[1]), reverse=True)
            if cut and len(vals) < b["WIN_UNIT_DEPTH"]:
                partial += 1
                truncated.add((ki, stratum, basis))
                continue
            vals = vals[:b["WIN_UNIT_DEPTH"]]
            per_key[(ki, stratum)].append((vals[0][0], vals[0][1], unit, vals))
        for key, us in per_key.items():
            us.sort(key=lambda u: u[2])
            us.sort(key=lambda u: (u[0], u[1]), reverse=True)
            values, offsets, total = array("d"), array("i", [0]), 0
            for _ne, _nid, _unit, vals in us:
                total += len(vals)
                if total > b["WIN_VALUES_MAX"]:
                    truncated.add(key + (basis,))
                    break
                values.extend(v for _e, _m, v in vals)
                offsets.append(len(values))
            out[key + (basis,)] = (values, offsets)
    return out, truncated, partial


def ev_daily_population(src, rows):
    """The daily population of one family: per `(daily ki, stratum)` every
    subject's summed value over its daily rows, ascending. A subject holds one
    value per key and stratum by construction (`ev_daily_sum`)."""
    by_subject = collections.defaultdict(list)
    for row in rows:
        by_subject[str(row["subject_player_id"])].append(row)
    out = collections.defaultdict(list)
    for subject in sorted(by_subject):
        for g in ev_daily_sum(src, by_subject[subject]):
            for ki, stratum, value in ev_row_facts(src, _ev_daily_row(src, g), "daily"):
                out[(ki, stratum)].append(value)
    return {k: array("d", sorted(v)) for k, v in out.items()}


def _ev_daily_row(src, g):
    """A summed daily group as a row `ev_row_facts` reads: combat sums as
    one-bin lists of each set's summed total."""
    if src == "card":
        return g
    row = dict(g)
    row["sums"] = {s: [sum(v)] for s, v in g["sums"].items()}
    return row


def ev_window_cells(src, data, games, account, basis, pops, daily_pops, days_rows=()):
    """One window subject's evidence cells for one family: per base key and
    stratum with a value on a covered game, its two window keys' cells (the
    aggregation over the covered games' attributed contributions about the
    account, newest first; comparability `(window key, basis, n)`, ranked in
    the population's units with at least `n` values; on basis `pair` the
    covered games are the pair's, so are the contributions), then per daily
    key and stratum the account's summed daily value ranked among the
    population's subjects (`days_rows`: the account's rows of EV_DAILY_SQL,
    which reads the stratum column the phase-2 daily read does not); each
    part in (key, stratum) order. Raises EvidenceDuplicate on two facts for
    one key, stratum and game."""
    vals = collections.defaultdict(list)
    for game in games:
        _paired, _recs, _rows, _other, contrib, _loose = _game_records(src, data, game)
        seen = set()
        for c in contrib:
            if str(c["subject_player_id"]) != account:
                continue
            for ki, stratum, value in ev_row_facts(src, c):
                if (ki, stratum) in seen:
                    raise EvidenceDuplicate("%s window: repeated fact" % src)
                seen.add((ki, stratum))
                vals[(ki, stratum)].append(value)
    cells = []
    for (ki, stratum) in sorted(vals, key=lambda k: (k[0], k[1])):
        vs = vals[(ki, stratum)]
        for w in (e for e in EV_REGISTRY if e.base == ki):
            agg = w.agg.split(".")[0]
            val = window_stat(agg, vs)
            source = pops.get((ki, stratum, basis))
            dist = (window_population(source[0], source[1], agg, len(vs))
                    if source is not None else array("d"))
            cells.append(_ev_cell(w.ki, stratum, basis, len(vs), val, dist))
    days = []
    for g in ev_daily_sum(src, days_rows):
        for ki, stratum, value in ev_row_facts(src, _ev_daily_row(src, g), "daily"):
            days.append(_ev_cell(ki, stratum, "player", g["games"], value,
                                 daily_pops.get((ki, stratum), array("d"))))
    return cells + sorted(days, key=lambda c: (c["ki"], c["stratum"]))


def _ev_cell(ki, stratum, basis, n, val, dist):
    pm = pop_measures(dist, val)
    return {"ki": ki, "stratum": stratum, "basis": basis, "n": n, "val": val,
            "pop_rank": pm["pop_rank"], "pop_n": pm["pop_n"], "pop_p50": pm["pop_p50"],
            "pop_p90": pm["pop_p90"], "pop_p99": pm["pop_p99"]}


def _ev_pop_sql(src):
    """The population rows of one family (design 2.6's game window: every
    game not invalidated, ended within `:pop_days` days and at least `:lag_s`
    seconds ago, by idx_matches_ended), joined to the contributions whose
    STORED match_id is a window game, read by the window's game ids through
    ix_<contrib>_match (migration 401; the id array keeps the planner on the
    index whatever its estimate of the window's size), newest game first,
    LIMITed (one more than EV_POP_ROWS_MAX tells a cut)."""
    spec = _SECTION_SPEC[src]
    return """
WITH g AS MATERIALIZED (
  SELECT m.id, m.ended_at, m.player1_id, m.player2_id
    FROM matches m
   WHERE m.invalidated_at IS NULL
     AND m.ended_at >= now() - make_interval(days => CAST(:pop_days AS integer))
     AND m.ended_at <= now() - make_interval(secs => CAST(:lag_s AS integer)))
SELECT c.match_id, g.ended_at, g.player1_id, g.player2_id, c.pair_lo, c.pair_hi,
       c.subject_player_id, c.source, c.coverage, %(cols)s
  FROM g JOIN %(contrib)s c ON c.match_id = g.id
 WHERE c.match_id = ANY(ARRAY(SELECT w.id FROM g w))
 ORDER BY g.ended_at DESC, g.id DESC, c.subject_player_id, c.source, c.coverage
 LIMIT CAST(:n AS integer)""" % {
        "cols": ", ".join("c." + c for c in spec["contrib_cols"]),
        "contrib": spec["contrib"]}


def _ev_daily_sql(src):
    """The daily rows of the population's subjects over the `pop_days` UTC
    days (the primary key's prefix: subject, day), LIMITed as EV_POP_SQL."""
    spec = _SECTION_SPEC[src]
    return ("SELECT d.subject_player_id, d.source, d.coverage, %s FROM %s d "
            "WHERE d.subject_player_id = ANY(CAST(:subjects AS uuid[])) "
            "AND d.%s >= CAST(:d0 AS date) "
            "ORDER BY d.subject_player_id, d.%s DESC, d.source, d.coverage "
            "LIMIT CAST(:n AS integer)"
            % (", ".join("d." + c for c in spec["daily_cols"] + (EV_SPEC[src]["col"],)),
               spec["daily"], spec["day"], spec["day"]))


def _ev_dup_sql(src):
    """Whether any fact identity repeats over the COMPLETE eligible relation
    (B10-P3-R1 H2): the population's own game window and join (as
    `_ev_pop_sql`), the rows `ev_population` admits (the stored pair is the
    match's sorted pair, the subject is one of the two, a registered source
    and coverage word, a stratum), grouped by (match, subject, source,
    coverage, stratum), the columns a fact identity is a function of. One
    row back means a repeat; LIMIT 1, no row cap before the grouping."""
    spec = _SECTION_SPEC[src]
    col = EV_SPEC[src]["col"]
    return """
WITH g AS MATERIALIZED (
  SELECT m.id, m.player1_id, m.player2_id
    FROM matches m
   WHERE m.invalidated_at IS NULL
     AND m.ended_at >= now() - make_interval(days => CAST(:pop_days AS integer))
     AND m.ended_at <= now() - make_interval(secs => CAST(:lag_s AS integer)))
SELECT c.match_id
  FROM g JOIN %(contrib)s c ON c.match_id = g.id
 WHERE c.match_id = ANY(ARRAY(SELECT w.id FROM g w))
   AND c.pair_lo = LEAST(g.player1_id, g.player2_id)
   AND c.pair_hi = GREATEST(g.player1_id, g.player2_id)
   AND c.subject_player_id IN (g.player1_id, g.player2_id)
   AND c.source = ANY(CAST(:sources AS text[]))
   AND c.coverage = ANY(CAST(:coverages AS text[]))
   AND c.%(col)s IS NOT NULL
 GROUP BY c.match_id, c.subject_player_id, c.source, c.coverage, c.%(col)s
HAVING count(*) > 1
 LIMIT 1""" % {"contrib": spec["contrib"], "col": col}


EV_POP_SQL = {src: _ev_pop_sql(src) for src in EV_SOURCES}
EV_DAILY_SQL = {src: _ev_daily_sql(src) for src in EV_SOURCES}
EV_DUP_SQL = {src: _ev_dup_sql(src) for src in EV_SOURCES}


def ev_complete_daily(src, rows, cap):
    """The daily rows of whole subjects only, and the count of
    (subject, source, coverage, stratum) groups left out: `rows` is one
    EV_DAILY_SQL read LIMITed at `cap` plus one, ordered by subject first, so
    when it returned more than `cap` rows only the subject of the first row
    past the cap can be cut, and every row of that subject is left out (its
    groups counted), never summed short (B10-P3-R1 H3)."""
    if len(rows) <= cap:
        return list(rows), 0
    edge = str(rows[cap]["subject_player_id"])
    kept = [r for r in rows[:cap] if str(r["subject_player_id"]) != edge]
    groups = {(r.get("source"), r.get("coverage"), _ev_stratum(src, r))
              for r in rows[:cap] if str(r["subject_player_id"]) == edge}
    return kept, len(groups)


async def read_evidence_populations(db, accounts):
    """Each family's population rows, its subjects' daily rows and the
    window accounts' own daily rows: `(pop, daily, own, rows, truncated,
    partial)`. First the repeat check over the complete eligible relation
    (`EV_DUP_SQL`; a repeat raises EvidenceDuplicate before any cap applies);
    then one statement each, LIMITed by EV_POP_ROWS_MAX plus one: a
    statement that returns the extra row is cut there, the block says
    truncated, and the subject the cut can split is left out whole
    (`ev_complete_daily`; its groups count in `partial`). `pop` keeps the
    cut flag per family (`ev_population` leaves out the units it may split)."""
    cap = AER_CONTRACT_BOUNDS["EV_POP_ROWS_MAX"]
    win = {"pop_days": DISPLAY_DEFAULTS["pop_days"], "lag_s": DISPLAY_DEFAULTS["lag_s"]}
    pop, daily, own, rows, truncated, partial = {}, {}, {}, 0, False, 0
    for src in EV_SOURCES:
        dup = await _section_rows(db, EV_DUP_SQL[src], dict(
            win, sources=sorted(EV_PROV), coverages=list(EV_COVERAGES)))
        if dup:
            raise EvidenceDuplicate("%s population: repeated fact" % src)
        got = await _section_rows(db, EV_POP_SQL[src], dict(win, n=cap + 1))
        cut = len(got) > cap
        truncated |= cut
        pop[src] = (got[:cap], cut)
        rows += len(got[:cap])
        subjects = sorted({str(r["subject_player_id"]) for r in got[:cap]}
                          | {str(a) for a in accounts})
        got = await _section_rows(db, EV_DAILY_SQL[src], {
            "subjects": subjects, "d0": _section_day0(), "n": cap + 1})
        truncated |= len(got) > cap
        daily[src], left = ev_complete_daily(src, got, cap)
        partial += left
        got = await _section_rows(db, EV_DAILY_SQL[src], {
            "subjects": sorted({str(a) for a in accounts}), "d0": _section_day0(), "n": cap + 1})
        truncated |= len(got) > cap
        own[src], left = ev_complete_daily(src, got, cap)
        partial += left
    return pop, daily, own, rows, truncated, partial


async def evidence_block(db, data, games, accounts):
    """Page 1's `evidence` (phase 3b): the families' ranks for each window
    subject. `state` is `unavailable` when a family's section data or the
    population read is unavailable or a fact repeats anywhere in the eligible
    relation, `not_derived` when no stored contribution reaches a population
    and no contribution or daily row gives a window cell, else `ok` (a
    window with daily rows alone is `ok` with daily cells only); only `ok`
    carries cells. Cells are the windows' (`ev_window_cells`), at most
    EV_CELLS_MAX per window, the rest counted in `more`. `partial` counts
    what a row cap could have cut and was left out whole: population units
    and daily (subject, source, coverage, stratum) groups."""
    block = {"state": "unavailable", "rows": 0, "truncated": False, "partial": 0,
             "fingerprint": ev_fingerprint(), "census": ev_census(), "catalog": [],
             "strata": [], "windows": [{"oi": oi, "cells": [], "more": 0}
                                       for oi in range(len(accounts))]}
    if any(data.get(src) is None for src in EV_SOURCES):
        return block
    plan = ([(str(accounts[0]), None, "player")] if len(accounts) == 1 else
            [(str(accounts[0]), str(accounts[1]), "pair"),
             (str(accounts[1]), str(accounts[0]), "pair")])
    try:
        async with db.begin_nested():
            pop, daily, own, rows, truncated, partial = await read_evidence_populations(
                db, accounts)
        sources = {}
        for src in EV_SOURCES:
            pops, cut, left = ev_population(src, *pop[src])
            truncated |= bool(cut)
            partial += left
            sources[src] = (pops, ev_daily_population(src, daily[src]))
        made = []
        for acc, _partner, basis in plan:
            cells = []
            for src in EV_SOURCES:
                mine = [r for r in own[src] if str(r["subject_player_id"]) == acc]
                cells += ev_window_cells(src, data[src], games, acc, basis, *sources[src], mine)
            made.append(cells)
    except EvidenceDuplicate as exc:
        _aer_log.warning("admin_evidence evidence ranks unavailable: %s", exc)
        return block
    except Exception as exc:  # noqa: BLE001 -- the block says so; the page answers
        _aer_log.warning("admin_evidence evidence ranks unavailable: %s", type(exc).__name__)
        return block
    block.update(rows=rows, truncated=truncated, partial=partial)
    if not rows and not any(made):
        block["state"] = "not_derived"
        return block
    block["state"] = "ok"
    strata = sorted({c["stratum"] for cells in made for c in cells})
    kis = sorted({c["ki"] for cells in made for c in cells})
    block["strata"] = [_section_enc(s) for s in strata]
    block["catalog"] = [{"ki": ki, "key": EV_REGISTRY[ki].key, "unit": EV_REGISTRY[ki].unit}
                        for ki in kis]
    cap = AER_CONTRACT_BOUNDS["EV_CELLS_MAX"]
    for oi, cells in enumerate(made):
        rows_out = [[c["ki"], strata.index(c["stratum"]), c["basis"], c["n"], c["val"],
                     c["pop_rank"], c["pop_n"], c["pop_p50"], c["pop_p90"], c["pop_p99"]]
                    for c in cells]
        block["windows"][oi] = {"oi": oi, "cells": rows_out[:cap], "more": len(rows_out[cap:])}
    return block


async def _page_sections(db, body, rows, subjects, accounts, summary_page, phase3=False):
    """Add the page's evidence sections to `body` (each game's `sections`, or
    page 1's `sections_summary`) and return the audit's state counts. With
    `phase3`, also each section's findings (`phase3_game_section`,
    `phase3_summary_section`) and page 1's `evidence` block."""
    games = _section_games(rows)
    index = {pid: s["i"] for pid, s in subjects.items()}
    if summary_page:
        data = await read_sections(db, games, accounts, phase3)
        body["sections_summary"] = [summary_section(src, data[src], games, str(acc), oi)
                                    for oi, acc in enumerate(accounts)
                                    for src in SECTION_SOURCES]
        if phase3:
            for sec in body["sections_summary"]:
                phase3_summary_section(sec, sec["src"], data[sec["src"]], games)
            body["evidence"] = await evidence_block(db, data, games, accounts)
        return section_audit(body["sections_summary"])
    data = await read_sections(db, games, (), phase3)
    by_id = {g["id"]: g for g in games}
    made = []
    for g in body["games"]:
        g["sections"] = [game_section(src, data[src], by_id[g["match_id"]], index)
                         for src in SECTION_SOURCES]
        if phase3:
            for sec in g["sections"]:
                phase3_game_section(sec, sec["src"], data[sec["src"]], by_id[g["match_id"]])
        made += g["sections"]
    return section_audit(made)


def phase3_audit(body):
    """A phase-3 page's audit additions: schema "3", the findings listed per
    source on the page, and on page 1 the evidence block's state word."""
    listed = {src: 0 for src in SECTION_SOURCES}
    for g in body.get("games", ()):
        for sec in g.get("sections", ()):
            listed[sec["src"]] += len(sec.get("findings", ()))
    out = {"schema": PHASE3_VALUE, "findings": listed}
    if "evidence" in body:
        out["evidence"] = body["evidence"]["state"]
    return out


def section_audit(sections):
    """The audit's per-source state counts of a page's sections."""
    out = {src: {} for src in SECTION_SOURCES}
    for s in sections:
        out[s["src"]][s["state"]] = out[s["src"]].get(s["state"], 0) + 1
    return out


async def _audit(db, actor, shape, target, details):
    """The one `admin_actions` row (design 4.4), in its own short transaction.
    A failed insert is `503 audit_unavailable`, no body."""
    import uuid
    from sqlalchemy import text
    try:
        await db.rollback()          # end the read transaction; nothing was written
        await db.execute(text(AUDIT_SQL), {
            "id": str(uuid.uuid4()), "admin": actor,
            "t_steam": target.get("steam"), "t_match": target.get("match"),
            "t_series": target.get("series"),
            "details": json.dumps(details, separators=(",", ":"), sort_keys=True)})
        await db.commit()
    except Exception as exc:      # any failed insert: no row, no body
        _aer_log.warning("admin_evidence audit unavailable: %s", type(exc).__name__)
        try:
            await db.rollback()
        except Exception:
            pass
        _aer_fail(503, "audit_unavailable")


def _aer_clock():
    return time.monotonic()


async def _aer_serve(shape, request, db, actor):
    """Parse, probe, bound, read, build, size-check, audit, return (design
    4.4 order); `actor` is the steam id `_evidence_gate` returned."""
    from sqlalchemy import text
    t0 = _aer_clock()
    deadline = (t0 + AER_CONTRACT_BOUNDS["REPORT_DEADLINE_S"]
                - AER_CONTRACT_BOUNDS["AUDIT_RESERVE_S"])
    gmax = AER_CONTRACT_BOUNDS["GAMES_MAX"]
    page = _aer_int(request, "page", 1, 1, 10 ** 6)
    sections_on = request.headers.get(SECTIONS_HEADER) == SECTIONS_PHASE
    phase3 = sections_on and request.headers.get(PHASE3_HEADER) == PHASE3_VALUE
    games_arg = None
    if shape in ("game", "series"):
        ident = _aer_ident(request.path_params.get("code"))
    elif shape == "pair":
        steams = (_aer_steam(request.query_params.get("a")),
                  _aer_steam(request.query_params.get("b")))
        if steams[0] == steams[1]:
            _aer_fail(400, "bad_argument")
        games_arg = _aer_int(request, "games", DISPLAY_DEFAULTS["games"],
                             AER_CONTRACT_BOUNDS["GAMES_MIN"], gmax)
    else:
        steams = (_aer_steam(request.path_params.get("steam_id")),)
        games_arg = _aer_int(request, "games", DISPLAY_DEFAULTS["games"],
                             AER_CONTRACT_BOUNDS["GAMES_MIN"], gmax)

    if (await db.execute(text("SELECT pg_is_in_recovery()"))).scalar():
        _aer_fail(409, "primary_only")
    _rate_charge(actor)
    await _wait_until(lambda: _INFLIGHT[0] < AER_CONTRACT_BOUNDS["REPORT_INFLIGHT_MAX"], deadline)
    _INFLIGHT[0] += 1
    rep = _Report(db, _aer_cache(), deadline)
    try:
        target, b_pid, accounts = {}, None, ()
        if shape == "game":
            ids = [await _select_game(db, ident)]
            target["match"] = str(ids[0])
        elif shape == "series":
            sid, ids = await _select_series(db, ident)
            target["series"] = str(sid)
        elif shape == "pair":
            accounts = (await _aer_player_id(db, steams[0]), await _aer_player_id(db, steams[1]))
            ids = [r["id"] for r in await _aer_rows(db, R3_PAIR_SQL, {
                "a": str(accounts[0]), "b": str(accounts[1]), "games": games_arg})]
            target["steam"], b_pid = steams[0], str(accounts[1])
        else:
            accounts = (await _aer_player_id(db, steams[0]),)
            ids = [r["id"] for r in await _aer_rows(db, R4_PLAYER_SQL, {
                "s": str(accounts[0]), "games": games_arg})]
            target["steam"] = steams[0]
        c = len(ids)
        _aer_require_games(c)
        pages = _aer_pages(shape, c)
        if not 1 <= page <= pages:
            _aer_fail(400, "bad_argument (page)")
        game_set = await rep.lease(_display_key())
        per = AER_CONTRACT_BOUNDS["PAGE_GAMES"]
        summary_page = shape in ("pair", "player") and page == 1
        first = (page - 2 if shape in ("pair", "player") else page - 1) * per
        page_ids = [] if summary_page else ids[first:first + per]
        rows = await _game_rows(db, ids if summary_page else page_ids)
        pids = {r[k] for r in rows for k in ("player1_id", "player2_id")} | set(accounts)
        subj_rows = await _aer_rows(db, SUBJECTS_SQL, {"ids": [str(p) for p in pids]})
        order = [str(a) for a in accounts] + sorted(
            str(p) for p in pids if str(p) not in {str(a) for a in accounts})
        by_id = {str(r["id"]): r for r in subj_rows}
        subjects = {}
        for i, pid in enumerate(order):
            r = by_id.get(pid)
            subjects[pid] = {"i": i, "steam_id": r["steam_id"] if r else None,
                             "name": _text(r["display_name"]) if r else None}
        body = {"shape": shape, "page": page, "pages": pages,
                "subjects": [{"steam_id": subjects[p]["steam_id"],
                              "name": subjects[p]["name"]} for p in order],
                "rules": {"report": "absent"},
                "population": {"key": "all", "days": DISPLAY_DEFAULTS["pop_days"],
                               "lag_s": DISPLAY_DEFAULTS["lag_s"],
                               "games": max((len(v) for v in game_set.values.values()),
                                            default=0),
                               "computed_at": _iso(game_set.computed_at),
                               "truncated": sorted(game_set.truncated)},
                "baseline": {"own_games": DISPLAY_DEFAULTS["own_games"],
                             "scan": AER_CONTRACT_BOUNDS["BASELINE_SCAN"]},
                "registry": registry_block()}
        if summary_page:
            windows, summary, win_at = await _summary_page(
                rep, shape, rows, games_arg, subjects, accounts)
            body["population"]["win_computed_at"] = _iso(win_at)
            body["catalog"] = [_catalog_row(e) for e in REPORT_REGISTRY
                               if e.is_window and e.scope == "seat"]
            body["windows"], body["summary"], body["games"] = windows, summary, []
        else:
            body["catalog"] = [_catalog_row(e, pop_measures(game_set.values.get(e.ki), None)
                                            if e.ranked else None)
                               for e in REPORT_REGISTRY if not e.is_window]
            body["games"] = await _game_page(rep, rows, ids, subjects, game_set)
        audit_sections = None
        if sections_on:
            audit_sections = await _page_sections(db, body, rows, subjects, accounts,
                                                  summary_page, phase3)
        encoded = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        if len(encoded) > AER_CONTRACT_BOUNDS["RESPONSE_BYTES_MAX"]:
            _aer_fail(500, "too_large")
        details = {"schema": SECTIONS_PHASE if sections_on else "1a", "shape": shape, "games": games_arg if games_arg else c,
                   "page": page, "pages": pages, "b_pid": b_pid,
                   "rules": dict(body["rules"]),
                   "registry": body["registry"]["fingerprint"],
                   "pop_computed_at": body["population"]["computed_at"],
                   "codes": [_code(i) for i in (page_ids or ids)], "via": "discord"}
        if sections_on:
            details["sections"] = audit_sections
        if phase3:
            details.update(phase3_audit(body))
        if _aer_clock() > deadline:
            _aer_fail(503, "deadline")
        await _audit(db, actor, shape, target, details)
        return Response(content=encoded, media_type="application/json")
    except PopulationUnavailable:
        _aer_fail(503, PopulationUnavailable.detail)
    finally:
        rep.close()
        _INFLIGHT[0] -= 1


@router.get("/game/{code}")
async def evidence_report_game(request: Request, db: AsyncSession = Depends(get_db)):
    actor = await _evidence_gate(request, db)
    return await _aer_serve("game", request, db, actor)


@router.get("/series/{code}")
async def evidence_report_series(request: Request, db: AsyncSession = Depends(get_db)):
    actor = await _evidence_gate(request, db)
    return await _aer_serve("series", request, db, actor)


@router.get("/pair")
async def evidence_report_pair(request: Request, db: AsyncSession = Depends(get_db)):
    actor = await _evidence_gate(request, db)
    return await _aer_serve("pair", request, db, actor)


@router.get("/player/{steam_id}")
async def evidence_report_player(request: Request, db: AsyncSession = Depends(get_db)):
    actor = await _evidence_gate(request, db)
    return await _aer_serve("player", request, db, actor)
