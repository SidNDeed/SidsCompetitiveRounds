"""Admin evidence report: registry, cell identity and display encoding.

Phase 1a of the admin evidence report (design V10). This module is the one
home of the report's closed key registry (`REPORT_REGISTRY`), its bounds
(`CONTRACT_BOUNDS`) and display defaults (`DISPLAY_DEFAULTS`), the cell
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
    # Populations (design 2.6): the caps as lowered there, the derived-result
    # memo, the entry lifetime, the request concurrency and the memory budget.
    "POP_VALUES_MAX": 2000,
    "WIN_VALUES_MAX": 1000,
    "WIN_UNIT_DEPTH": 30,
    "WIN_DERIVED_BYTES_MAX": 2 * 1024 * 1024,
    "POP_TTL_S": 3600,
    "REPORT_INFLIGHT_MAX": 2,
    "POP_MEM_BUDGET_MB": 128,
    "GAME_SETS_LIVE": 4,
    "WINDOW_SOURCES_LIVE": 8,
    # Routes (design 4.6): reports per actor per window, in process.
    "RATE_MAX": 20,
    "RATE_WINDOW_S": 600,
    "ACTOR_ID_MAX_DIGITS": 32,
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
        return "g.rep = '%s'" % _other(col_seat)
    if presence == "by_prov":
        own = entry.prov in ("SELF", "D:SELF")
        return "g.rep = '%s'" % (col_seat if own else _other(col_seat))
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
        for seat in SEATS:
            col_seat = _other(seat) if e.decl.subject == "opposite" else seat
            val = _value_sql(e, col_seat)
            po = (", %s AS po" % _seat_account_sql(_other(seat))) if partner else ""
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


_log = logging.getLogger("admin_evidence")


async def rebuild_game_population(conn, key, pop_days, lag_s, ranked_only=False,
                                  cap=None):
    """Read one game population and return `(values, truncated)`: per key an
    ascending `array('d')` of at most `cap` values and, for a truncated key,
    its cutoff. Streamed one key's row at a time. A repeated identity
    anywhere in the complete eligible relation raises PopulationUnavailable
    before anything is kept."""
    from sqlalchemy import text   # deferred: the registry half needs no driver
    cap = CONTRACT_BOUNDS["POP_VALUES_MAX"] if cap is None else cap
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
    wmax = CONTRACT_BOUNDS["WIN_VALUES_MAX"] if wmax is None else wmax
    depth = CONTRACT_BOUNDS["WIN_UNIT_DEPTH"] if depth is None else depth
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


# A measured B above this misses the floor caps (P 500, W 250): P9 red, and
# the figure goes to Sid as a budget decision (design 2.6).
BASE_RSS_FLOOR_MB = 94.7


def budget_bytes(base_rss_mb):
    """The cache's byte budget (design 2.6): `128/1.25 - B - 2` MB."""
    return int((CONTRACT_BOUNDS["POP_MEM_BUDGET_MB"] / 1.25 - base_rss_mb - 2)
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
        if g is None or self._clock() - g.computed_at >= CONTRACT_BOUNDS["POP_TTL_S"]:
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
        old = self.live.pop(key, None)
        self.live[key] = new
        if old is not None:
            self._retire(old)
        same = [g for g in self.live.values() if g.kind == kind]
        while len(same) > CONTRACT_BOUNDS[self.LIVE_MAX[kind]]:
            oldest = same.pop(0)
            del self.live[oldest.key]
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
            self._released.clear()
            try:
                await asyncio.wait_for(self._released.wait(), remaining)
            except asyncio.TimeoutError:
                pass

    def _retire(self, g):
        g.retired = True
        for mk in [mk for mk in self.memo if mk[1] == g.key and mk[2] == g.gen]:
            self.memo_bytes -= self.memo.pop(mk)["_bytes"]
        if g.leases:
            self.retired.append(g)

    def lease(self, g):
        g.leases += 1
        return g

    def release(self, g):
        g.leases -= 1
        if g.leases == 0 and g in self.retired:
            self.retired.remove(g)
        self._released.set()

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
            self.memo_bytes -= self.memo.pop(mk)["_bytes"]
        stored = dict(result, source_key=lease.key, gen=lease.gen,
                      computed_at=lease.computed_at, _bytes=nbytes)
        self.memo[mk] = stored
        self.memo_bytes += nbytes
        while self.memo_bytes > CONTRACT_BOUNDS["WIN_DERIVED_BYTES_MAX"] and self.memo:
            _k, old = self.memo.popitem(last=False)
            self.memo_bytes -= old["_bytes"]
        return stored

    def cache_bytes(self):
        """`_aer_cache_bytes()`: live, leased-retired, memo and in-progress."""
        return (sum(g.nbytes() for g in self.live.values())
                + sum(g.nbytes() for g in self.retired)
                + self.memo_bytes + self.in_progress)


def _packed_bytes(*maps):
    return sum(len(a) * a.itemsize for m in maps for a in m.values())


def _deadline(deadline):
    if deadline is not None:
        return deadline
    return (time.monotonic() + CONTRACT_BOUNDS["REPORT_DEADLINE_S"]
            - CONTRACT_BOUNDS["AUDIT_RESERVE_S"])


async def _admit_and_publish(cache, key, values, truncated, offsets, t0, deadline):
    nbytes = _packed_bytes(values, offsets or {})
    cache.in_progress += nbytes
    try:
        await cache.admit(nbytes, _deadline(deadline))
    except PopulationUnavailable as exc:
        _log.warning("admin_evidence population unavailable: key=%r %s", key, exc)
        raise
    finally:
        cache.in_progress -= nbytes
    g = cache.publish(key, values, truncated, offsets)
    _log.info("admin_evidence population rebuilt: key=%r gen=%d size=%d truncated=%s "
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
        _log.warning("admin_evidence population unavailable: key=%r %s", key, exc)
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
        _log.warning("admin_evidence population unavailable: key=%r %s", key, exc)
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

router = APIRouter(prefix=EVIDENCE_ROOT, tags=["Internal"])


def _evidence_refusal():
    """The one refusal of the key and actor gates: `403 {"detail":"refused"}`."""
    return JSONResponse(status_code=403, content={"detail": REFUSED})


def _refuse_class(cls):
    """Log the failure class once, without the actor id (design 4.2)."""
    _log.info("admin_evidence refused: %s", cls)


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


def _fail(status, word, headers=None):
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
    if (d is None or not 1 <= len(d) <= CONTRACT_BOUNDS["ACTOR_ID_MAX_DIGITS"]
            or not d.isascii() or not d.isdigit()):
        _refuse_class("bad_actor")
        _fail(403, REFUSED)
    steam = (await db.execute(text(
        "SELECT steam_id FROM players WHERE discord_id = :d AND deleted_at IS NULL"),
        {"d": d})).scalar()
    if not steam:
        _refuse_class("not_linked")
        _fail(403, REFUSED)
    if not await _aer_is_admin(db, steam):
        _refuse_class("not_admin")
        _fail(403, REFUSED)
    return steam


# Argument forms (design 1.2).

_HEX = frozenset("0123456789abcdef")


def _aer_ident(raw):
    """`("full", 32 hex)` or `("code", 12 hex)`: lowercased, dashes stripped;
    anything else is `400 bad_argument`."""
    s = (raw or "").strip().lower().replace("-", "")
    if s and set(s) <= _HEX:
        if len(s) == 32:
            return "full", s
        if len(s) == 12:
            return "code", s
    _fail(400, "bad_argument")


def _aer_steam(raw):
    s = raw or ""
    lo, hi = CONTRACT_BOUNDS["STEAM_ID_MIN_DIGITS"], CONTRACT_BOUNDS["STEAM_ID_MAX_DIGITS"]
    if lo <= len(s) <= hi and s.isascii() and s.isdigit():
        return s
    _fail(400, "bad_argument")


def _aer_int(request, name, default, lo, hi):
    raw = request.query_params.get(name)
    if raw is None:
        return default
    if not (raw.isascii() and raw.isdigit()) or not lo <= int(raw) <= hi:
        _fail(400, "bad_argument (%s)" % name)
    return int(raw)


def _aer_pages(shape, c):
    """Page count for `c` selected games (design 1.2): game and series
    `ceil(c/5)`; pair and player `1 + ceil(c/5)`, page 1 the summary. Shared by
    route, bot and tests."""
    per = CONTRACT_BOUNDS["PAGE_GAMES"]
    games = (c + per - 1) // per
    return games + 1 if shape in ("pair", "player") else games


def _aer_require_games(c):
    """The shared empty-cohort check (design 1.3): `404 not_found` at `c == 0`,
    before the page bound, windows, the audit and any send."""
    if c == 0:
        _fail(404, "not_found")


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
 WHERE f.match_id = ANY(CAST(:ids AS uuid[]))"""

GAME_ROWS_SQL = ("SELECT %s, m.p1_rounds_won, m.p2_rounds_won FROM matches m "
                 "WHERE m.id = ANY(CAST(:ids AS uuid[]))" % _SELECT_LIST)

AUDIT_SQL = """
INSERT INTO admin_actions (id, admin_steam_id, action, target_steam_id, target_match_id,
                           target_series_id, details, created_at)
VALUES (CAST(:id AS uuid), :admin, 'evidence_report', :t_steam, CAST(:t_match AS uuid),
        CAST(:t_series AS uuid), CAST(:details AS jsonb), now())"""


async def _rows(db, sql, params):
    from sqlalchemy import text
    result = await db.execute(text(sql), params)
    return [dict(r) for r in result.mappings().all()]


async def _select_game(db, ident):
    kind, s = ident
    if kind == "full":
        rows = await _rows(db, R1_ID_SQL, {"id": s})
    else:
        rows = await _rows(db, R1_CODE_SQL, {"code": s})
        if len(rows) > 1:
            _fail(400, "bad_argument (code ambiguous; use the full id)")
    if not rows:
        _fail(404, "not_found")
    return rows[0]["id"]


async def _select_series(db, ident):
    """R2: a 32-hex value is a series id first; only with no series row is it
    resolved as a game (R1's selector) and that game's series taken."""
    kind, s = ident
    sid = None
    if kind == "full":
        if await _rows(db, R2_SERIES_ROW_SQL, {"id": s}):
            sid = s
    if sid is None:
        gid = await _select_game(db, ident)
        got = await _rows(db, R2_GAME_SERIES_SQL, {"id": str(gid)})
        sid = got[0]["series_id"] if got else None
        if sid is None:
            _fail(404, "not_found")
    lim = CONTRACT_BOUNDS["SERIES_GAMES_MAX"] + 1
    rows = await _rows(db, R2_SERIES_SQL, {"sid": str(sid), "lim": lim})
    if len(rows) > CONTRACT_BOUNDS["SERIES_GAMES_MAX"]:
        _fail(500, "too_large")
    return sid, [r["id"] for r in rows]


async def _player_id(db, steam):
    rows = await _rows(db, PLAYER_BY_STEAM_SQL, {"steam": steam})
    if not rows:
        _fail(404, "not_found")
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
    window = CONTRACT_BOUNDS["RATE_WINDOW_S"]
    q = _RATE.setdefault(actor, collections.deque())
    while q and now - q[0] >= window:
        q.popleft()
    if len(q) >= CONTRACT_BOUNDS["RATE_MAX"]:
        retry = max(1, int(math.ceil(window - (now - q[0]))))
        _fail(429, "rate", headers={"Retry-After": str(retry)})
    q.append(now)


async def _wait_until(pred, deadline):
    while not pred():
        if time.monotonic() >= deadline:
            _fail(503, "deadline")
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
    return _aer_enc((value or "")[:CONTRACT_BOUNDS["TEXT_MAX"]])


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
            self.cache.release(self.leases.pop())


async def _game_rows(db, ids):
    rows = await _rows(db, GAME_ROWS_SQL, {"ids": [str(i) for i in ids]})
    by_id = {str(r["id"]): r for r in rows}
    return [by_id[str(i)] for i in ids if str(i) in by_id]


async def _flag_rows(db, ids):
    out = collections.defaultdict(list)
    for r in await _rows(db, FLAGS_SQL, {"ids": [str(i) for i in ids]}):
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
        for seat in SEATS:
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
                          "reporter": reporter_seat(row) == seat,
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
    windows, summary, win_at = [], [], None
    cohort = [str(r["id"]) for r in rows]
    oldest = rows[-1]
    for oi, (acc, partner, basis) in enumerate(plan):
        source = await rep.lease(_display_key() + (basis,), basis=basis)
        win_at = source.computed_at
        base = await read_baseline(db, acc, oldest["ended_at"], oldest["id"],
                                   covered=cohort, partner=partner)
        cells = window_cells(rows, acc, basis, base, partner)
        for c in cells:
            comp = c.pop("comparability")
            if c["state"] != "ok" or not c["n"]:
                continue
            w = REPORT_REGISTRY[c["ki"]]
            r = rep.cache.memo_get(comp, source)
            if r is None:
                dist = window_population(source.values.get(w.base, array("d")),
                                         source.offsets.get(w.base, array("i", [0])),
                                         w.agg.split(".")[0], c["n"])
                r = rep.cache.memo_put(comp, source, pop_measures(dist, c["val"]),
                                       len(dist) * 8 + 64)
            for k in ("pop_rank", "pop_n", "pop_p50", "pop_p90", "pop_p99"):
                c[k] = r[k]
        windows.append({"oi": oi, "basis": basis,
                        "subj": ["seat", index[str(acc)],
                                 index[str(partner)] if partner is not None else None],
                        "games": requested, "covered": len(rows),
                        "flag_obs": flag_obs(flags, steam_of.get(str(acc))),
                        "newest": _code(rows[0]["id"]), "oldest": _code(oldest["id"])})
        summary.append({"oi": oi, "cells": [wire_row("summary", c) for c in cells]})
    return windows, summary, win_at


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
        _log.warning("admin_evidence audit unavailable: %s", type(exc).__name__)
        try:
            await db.rollback()
        except Exception:
            pass
        _fail(503, "audit_unavailable")


def _clock():
    return time.monotonic()


async def _aer_serve(shape, request, db, actor):
    """Parse, probe, bound, read, build, size-check, audit, return (design
    4.4 order); `actor` is the steam id `_evidence_gate` returned."""
    from sqlalchemy import text
    t0 = _clock()
    deadline = (t0 + CONTRACT_BOUNDS["REPORT_DEADLINE_S"]
                - CONTRACT_BOUNDS["AUDIT_RESERVE_S"])
    gmax = CONTRACT_BOUNDS["GAMES_MAX"]
    page = _aer_int(request, "page", 1, 1, 10 ** 6)
    games_arg = None
    if shape in ("game", "series"):
        ident = _aer_ident(request.path_params.get("code"))
    elif shape == "pair":
        steams = (_aer_steam(request.query_params.get("a")),
                  _aer_steam(request.query_params.get("b")))
        if steams[0] == steams[1]:
            _fail(400, "bad_argument")
        games_arg = _aer_int(request, "games", DISPLAY_DEFAULTS["games"],
                             CONTRACT_BOUNDS["GAMES_MIN"], gmax)
    else:
        steams = (_aer_steam(request.path_params.get("steam_id")),)
        games_arg = _aer_int(request, "games", DISPLAY_DEFAULTS["games"],
                             CONTRACT_BOUNDS["GAMES_MIN"], gmax)

    if (await db.execute(text("SELECT pg_is_in_recovery()"))).scalar():
        _fail(409, "primary_only")
    _rate_charge(actor)
    await _wait_until(lambda: _INFLIGHT[0] < CONTRACT_BOUNDS["REPORT_INFLIGHT_MAX"], deadline)
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
            accounts = (await _player_id(db, steams[0]), await _player_id(db, steams[1]))
            ids = [r["id"] for r in await _rows(db, R3_PAIR_SQL, {
                "a": str(accounts[0]), "b": str(accounts[1]), "games": games_arg})]
            target["steam"], b_pid = steams[0], str(accounts[1])
        else:
            accounts = (await _player_id(db, steams[0]),)
            ids = [r["id"] for r in await _rows(db, R4_PLAYER_SQL, {
                "s": str(accounts[0]), "games": games_arg})]
            target["steam"] = steams[0]
        c = len(ids)
        _aer_require_games(c)
        pages = _aer_pages(shape, c)
        if not 1 <= page <= pages:
            _fail(400, "bad_argument (page)")
        game_set = await rep.lease(_display_key())
        per = CONTRACT_BOUNDS["PAGE_GAMES"]
        summary_page = shape in ("pair", "player") and page == 1
        first = (page - 2 if shape in ("pair", "player") else page - 1) * per
        page_ids = [] if summary_page else ids[first:first + per]
        rows = await _game_rows(db, ids if summary_page else page_ids)
        pids = {r[k] for r in rows for k in ("player1_id", "player2_id")} | set(accounts)
        subj_rows = await _rows(db, SUBJECTS_SQL, {"ids": [str(p) for p in pids]})
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
                             "scan": CONTRACT_BOUNDS["BASELINE_SCAN"]},
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
        encoded = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        if len(encoded) > CONTRACT_BOUNDS["RESPONSE_BYTES_MAX"]:
            _fail(500, "too_large")
        details = {"schema": "1a", "shape": shape, "games": games_arg if games_arg else c,
                   "page": page, "pages": pages, "b_pid": b_pid,
                   "rules": dict(body["rules"]),
                   "registry": body["registry"]["fingerprint"],
                   "pop_computed_at": body["population"]["computed_at"],
                   "codes": [_code(i) for i in (page_ids or ids)], "via": "discord"}
        if _clock() > deadline:
            _fail(503, "deadline")
        await _audit(db, actor, shape, target, details)
        return Response(content=encoded, media_type="application/json")
    except PopulationUnavailable:
        _fail(503, PopulationUnavailable.detail)
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
