"""Synthetic review rules revisions for the public tests.

Every value here is SYNTHETIC: chosen to exercise the machinery, visibly
arbitrary, and unrelated to any revision a server runs. A test builds a
draft with these helpers, turns it into an immutable revision with
review_rules.build (the seat's own tool), and points a temporary review root
at it.
"""

import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import review_rules as rr  # noqa: E402
import seat_evidence_fixtures as fx  # noqa: E402

A, B = "seat-a", "seat-b"
MATCH = {"id": "match-x", "player1_id": A, "player2_id": B, "p1_rounds_won": 5, "p2_rounds_won": 3}

ID_PUB = "r0000a001"
ID_GAP = "r0000a002"
ID_NOT_GAP = "r0000a003"
ID_NOTE = "r0000a004"
ID_STEP = "r0000a005"


def M(name):
    return {"m": name}


def V(v):
    return {"v": v}


def cmp(a, rel, b):
    return {"op": "op.cmp", "args": {"a": a, "rel": rel, "b": b}}


def synthetic_doc():
    """A draft with synthetic values: a one-record rule, a two-seat rule and
    its negation, a note, and one sitting rule."""
    gap = cmp({"abs": {"sub": [M("seat.decided_hits"), M("seat.other_received_hits")]}}, "gt", V(7))
    return {
        "format": 1, "nonce": "", "vocabulary": [], "closure": {},
        "measure_params": {
            "params.case_table": {"pair_lo_ms": -77, "pair_hi_ms": 777, "late_margin_ms": 111,
                                  "window_ms": 222},
            "params.one_record": {"due_margin_ms": 33, "due_hi_ms": 333, "edge_span_ms": 444,
                                  "own_window_ms": 222},
            "params.age_sum": {"budget_slack_ms": 17},
            "params.blocks_missing": {"in_flight_ms": 1777},
        },
        "rules": [
            {"id": ID_PUB, "scope": "game", "subject": "seat", "effect": "flag", "post": False,
             "post_since": None,
             "when": cmp(M("seat.published_hits"), "gt", {"add": [M("seat.observed_hits"), V(11)]}),
             "show": [["published", "seat.published_hits"], ["observed", "seat.observed_hits"],
                      ["seat", "seat.index"]],
             "line": "synthetic published {published} over observed {observed} (seat {seat})"},
            {"id": ID_GAP, "scope": "game", "subject": "seat", "effect": "flag", "post": False,
             "post_since": None, "when": gap,
             "show": [["decided", "seat.decided_hits"], ["received", "seat.other_received_hits"]],
             "line": "synthetic gap {decided} against {received}"},
            {"id": ID_NOT_GAP, "scope": "game", "subject": "seat", "effect": "flag", "post": False,
             "post_since": None, "when": {"not": copy.deepcopy(gap)},
             "show": [["decided", "seat.decided_hits"]],
             "line": "synthetic no gap {decided}"},
            {"id": ID_NOTE, "scope": "game", "subject": "seat", "effect": "note", "post": False,
             "post_since": None, "when": {"op": "op.truth", "args": {"a": M("seat.record_conflict")}},
             "show": [["seat", "seat.index"]], "line": "synthetic note seat {seat}"},
            {"id": ID_STEP, "scope": "sitting", "effect": "flag", "post": False, "post_since": None,
             "sitting": {"op": "sitting.step_ratio", "args": {
                 "num": "reporter.observed_batches", "den": "row.duration_s",
                 "filters": ["pop.reporter_is_player"], "window_days": 9, "min_den": 17,
                 "pre_rows": 2, "post_rows": 2, "low": 0.41, "high": 2.3}},
             "show": [["d", "d"], ["steps", "steps"], ["lo", "min_ratio"], ["hi", "max_ratio"]],
             "line": "synthetic step {d}: {steps} ({lo:2}..{hi:2})"},
        ],
    }


def rec(**over):
    return fx.base_record(**over)


def game(ra=None, rb=None, *, one_sided=False, conflict=(False, False), match=MATCH):
    ra = rec() if ra is None else ra
    rb = rec(rounds=[3, 5]) if rb is None else rb
    records = [{"seat": A, "other": B, "rec": ra, "header_version": "1.41.0",
                "conflict": conflict[0]}]
    if not one_sided:
        records.append({"seat": B, "other": A, "rec": rb, "header_version": "1.41.0",
                        "conflict": conflict[1]})
    return records


def registry_of(records):
    return {(r["rec"]["build"][0], r["rec"]["build"][1], r["rec"]["build"][2], r["rec"]["dll"][0])
            for r in records}


def case(records, fire, match=MATCH):
    return {"records": records, "match": match,
            "registry": [list(t) for t in sorted(registry_of(records))], "fire": sorted(fire)}


def quiet_cases():
    """Self-test cases consistent with synthetic_doc: a quiet game fires only
    the negation; a large two-seat gap on one seat fires the gap rule there
    (and the negation on the other seat)."""
    ra = rec(dec=[40, 2])
    return [case(game(), [ID_NOT_GAP]),
            case(game(ra), [ID_GAP, ID_NOT_GAP])]


def write_draft(path, doc=None, cases=None):
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, "rules.json"), "w", encoding="utf-8") as f:
        json.dump(synthetic_doc() if doc is None else doc, f)
    with open(os.path.join(path, "selftest.json"), "w", encoding="utf-8") as f:
        json.dump({"cases": quiet_cases() if cases is None else cases}, f)
    return path


def build_revision(tmp, doc=None, cases=None, name="draft"):
    """A built revision in <tmp>/store. Returns (store, rev)."""
    store = os.path.join(str(tmp), "store")
    os.makedirs(store, exist_ok=True)
    draft = write_draft(os.path.join(str(tmp), name), doc, cases)
    return store, rr.build_revision(draft, store, "synthetic")


def point(root, target):
    """The `current` pointer as a one-line file (portable; a relative link is
    the other accepted form)."""
    with open(os.path.join(root, rr.POINTER), "w", encoding="ascii") as f:
        f.write(target + "\n")


def reseal(rdir):
    """Recompute REVISION and rename the directory after an edit, so a test's
    change reaches the check it targets instead of the digest refusal."""
    files = {}
    for name in ("rules.json", "selftest.json"):
        with open(os.path.join(rdir, name), "rb") as f:
            files[name] = f.read()
    ddir = os.path.join(rdir, "data")
    if os.path.isdir(ddir):
        for dn in sorted(os.listdir(ddir)):
            with open(os.path.join(ddir, dn), "rb") as f:
                files["data/" + dn] = f.read()
    digest = rr.revision_digest(files)
    with open(os.path.join(rdir, "REVISION"), "wb") as f:
        f.write((digest + "\n").encode())
    new = os.path.join(os.path.dirname(rdir), "rules-" + digest[:12])
    os.rename(rdir, new)
    return new, digest[:12]
