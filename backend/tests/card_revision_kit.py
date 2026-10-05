"""Card draw evidence: fixtures, censuses and SYNTHETIC revisions for the
public tests.

Every rule value here is SYNTHETIC: chosen to exercise the machinery, visibly
arbitrary, and unrelated to any revision a server runs. The client's committed
fixtures (fixtures/card_evidence, copied byte for byte from the client lane)
are the record layout's ground truth; a census here is built to describe
their pool so the measures that need one can run.
"""

import copy
import hashlib
import hmac
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import card_evidence as ce  # noqa: E402
import card_measures as cm  # noqa: E402
import review_rules as rr  # noqa: E402

FIX = os.path.join(HERE, "fixtures", "card_evidence")
FIXTURE_KEY = "fixture-key-not-a-secret"
KEY = "test-hmac-key-card-evidence"
GAME_SHA = "c" * 64
FIX_SEAT, FIX_OTHER = "76500000000000001", "76500000000000002"

# Synthetic ids and values (visibly arbitrary).
ID_DUP = "r0000c001"
ID_HELD = "r0000c002"
ID_PICKER = "r0000c003"
ID_PAIR = "r0000c004"
ID_WIN = "r0000c005"
ID_NOTE = "r0000c006"
ID_SC = "r0000c007"
ID_CONFLICT = "r0000c008"
ID_PICKS = "r0000c009"
WEIGHTS = {"common": 13, "uncommon": 5, "rare": 2}
WINDOW = {"window_days": 9}
DUP_AT = 0.37


def cases():
    with open(os.path.join(FIX, "cases.txt"), encoding="ascii") as f:
        return f.read().split()


def fixture(name, part):
    """The raw bytes of one committed fixture file."""
    with open(os.path.join(FIX, "%s.%s" % (name, part)), "rb") as f:
        return f.read()


def fixture_record(name) -> dict:
    return json.loads(fixture(name, "record.txt").decode("ascii"))


def fixture_input(name) -> dict:
    return json.loads(fixture(name, "input.json").decode("ascii"))


# -- the reference budgeter (the client's Budget, restated) -------------------------

def budget(rec: dict, limit=None) -> str:
    """The client's budgeter over an untrimmed record: while the text is over
    the cap, among ap, cards, held0 (both lists together), ph and hd with a
    removable entry, the one with the most entries (ties: that order) loses
    its LAST removable entry (cards: the last one nothing still names; held0:
    the other seat's list first); `omit` counts each removal."""
    limit = cm.W["record_max_bytes"] if limit is None else limit
    out = copy.deepcopy(rec)
    om = out["omit"]

    def refs():
        n = {}
        for e in out["hd"]:
            for x in e[6] + e[8]:
                if x >= 0:
                    n[x] = n.get(x, 0) + 1
        for lst in out["held0"]:
            for x in lst or []:
                if x >= 0:
                    n[x] = n.get(x, 0) + 1
        for a in out["ap"]:
            if a[1] >= 0:
                n[a[1]] = n.get(a[1], 0) + 1
        return n

    while len(cm.dumps(out)) > limit:
        r = refs()
        free = next((i for i in range(len(out["cards"]) - 1, -1, -1) if r.get(out["cards"][i][0], 0) <= 0), -1)
        h0, h1 = out["held0"]
        held = (len(h0) if h0 is not None else 0) + (len(h1) if h1 is not None else 0)
        counts = [len(out["ap"]), len(out["cards"]) if free >= 0 else -1, held, len(out["ph"]), len(out["hd"])]
        pick = -1
        for i, c in enumerate(counts):
            if c > 0 and (pick < 0 or c > counts[pick]):
                pick = i
        assert pick >= 0, "the fixed fields alone exceed the limit"
        if pick == 0:
            out["ap"].pop()
            om["ap"] += 1
        elif pick == 1:
            out["cards"].pop(free)
            om["cards"] += 1
        elif pick == 2:
            if h1:
                h1.pop()
                om["held0"][1] += 1
            else:
                h0.pop()
                om["held0"][0] += 1
        elif pick == 3:
            out["ph"].pop()
            om["ph"] += 1
        else:
            out["hd"].pop()
            om["hd"] += 1
    return cm.dumps(out)


# -- envelopes ---------------------------------------------------------------------

def envelope(record, *, seat=FIX_SEAT, other=FIX_OTHER, stable="ranked_card_000001", rounds=5,
             key=KEY) -> dict:
    text = record if isinstance(record, str) else cm.dumps(record)
    attach = "%s_r%d" % (stable, rounds)
    env = {"seat": seat, "other": other, "stable": stable, "attach": attach,
           "record_text": text, "record_bytes": text.encode("ascii")}
    return {"contract": 2, "seat_steam_id": seat, "other_steam_id": other,
            "stable_game_key": stable, "attach_key": attach, "record": text,
            "sig": hmac.new(key.encode(), ce.record_canonical(env).encode(), hashlib.sha256).hexdigest()}


# -- censuses -------------------------------------------------------------------------

def census_cards(count, names=None, rarity=None, multi=1, cats=None, black=None, lock=None):
    """A pool of `count` cards: name CardN (or names[ix]), rarity ix mod three
    (or rarity[ix]), allowMultiple `multi`, and per-index categories,
    blacklists and gun locks from the dicts given."""
    out = []
    for ix in range(count):
        out.append([(names or {}).get(ix, "Card%d" % ix),
                    (rarity or {}).get(ix, ix % len(cm.RARITIES)),
                    multi if not isinstance(multi, dict) else multi.get(ix, 1),
                    (cats or {}).get(ix), (black or {}).get(ix), (lock or {}).get(ix, 0)])
    return out


def census_dump(cards, slots=5, game_sha=GAME_SHA, state="ok"):
    text = cm.dumps({"census": 1, "cards": cards})
    return {"census_version": 1, "digest": cm.census_digest(text), "card_count": len(cards),
            "slot_count": slots, "game_dll": [game_sha if state == "ok" else "", state],
            "census_text": text}


def census(cards, slots=5, game_sha=GAME_SHA):
    return cm.census_from_dump(census_dump(cards, slots, game_sha))


def on_census(rec, c) -> dict:
    """The record, naming census `c` as its pool."""
    out = copy.deepcopy(rec)
    out["pool"] = [c.count, c.digest, "ok"]
    return out


def fixture_census(name, names=None, rarity=None, **attrs):
    """A census describing a fixture's pool: its record's card names and
    rarities (from the untrimmed input) at their indexes, with `names` and
    `rarity` overriding single indexes."""
    inp = fixture_input(name)
    nm = {c[0]: c[1] for c in inp["cards"]}
    nm.update(names or {})
    ra = {c[0]: c[2] for c in inp["cards"] if 0 <= c[2] < len(cm.RARITIES)}
    ra.update(rarity or {})
    return census(census_cards(inp["pool"][0], names=nm, rarity=ra, **attrs), slots=inp["ns"])


def renamed(rec, names):
    """The record with some of its `cards` entries renamed (index -> name)."""
    out = copy.deepcopy(rec)
    out["cards"] = [[c[0], names.get(c[0], c[1]), c[2]] for c in out["cards"]]
    return out


def mirror(rec):
    """The other seat's record of the same game, all-vanilla deals: roles
    swapped, the measured hands now own (no engine slot), the own ones now
    measured (source unknown)."""
    r = copy.deepcopy(rec)
    flip = lambda w: 1 - w if w in (0, 1) else w  # noqa: E731
    r["po"] = [flip(x) for x in r["po"]]
    r["held0"] = [r["held0"][1], r["held0"][0]]
    r["ph"] = [[e[0], flip(e[1]), e[2], e[4], e[3], e[5], e[6]] for e in r["ph"]]
    for e, mine in zip(r["hd"], rec["hd"]):
        e[2], e[3] = flip(e[2]), flip(e[3])
        e[12], e[13], e[16] = -1, -1, -1
        if mine[2] == 1:
            e[12], e[16] = 0, 0
    r["ap"] = [[flip(a[0]), a[1], a[2], a[3]] for a in r["ap"]]
    return r


def family(weights, *recs) -> dict:
    """A weights family naming each record's own deal profile."""
    return {cm.deal_profile(r): dict(weights) for r in recs}


def view(records, registry=None, sc=None, weights=None, report=None):
    """card_view over [(seat, other, rec), ...] with a registry of censuses.
    `weights` is a family (deal profile -> weight set), or one weight set,
    which this helper gives to every record's own profile (the tests that
    are about profiles pass a family)."""
    reg = {c.digest: c for c in (registry or [])}
    rows = [{"seat": s, "other": o, "rec": r, "conflict": False} for s, o, r in records]
    if weights is not None and set(weights) == set(cm.RARITIES):
        weights = family(weights, *[r for _s, _o, r in records])
    return cm.card_view(rows, reg, sc, weights, report)


def default_record():
    """The full game on its own census: the record the live cases store."""
    return on_census(fixture_record("full_game"), fixture_census("full_game"))


def default_profiles():
    return [cm.deal_profile(default_record())]


def hand(v, phase, recorder=None):
    return next(r for r, m in v["hands"] if r["b4.hand.phase"] == phase
                and (recorder is None or r["b4.hand.recorder"] == recorder))


# -- synthetic revisions ------------------------------------------------------------------

def M(name):
    return {"m": name}


def V(v):
    return {"v": v}


def cmp(a, rel, b):
    return {"op": "op.cmp", "args": {"a": a, "rel": rel, "b": b}}


def card_doc(post=False, post_since=None, weights=True, window=True, dup_at=DUP_AT, drop=(),
             conflict=False, picks=False):
    """A card-only draft with synthetic values. `weights`: True gives the
    synthetic weight set to the default profiles; a dict is the family as
    given. `dup_at` moves the dup rule's synthetic value, `drop` leaves rule
    ids out, `conflict` and `picks` add a flag rule on the record's conflict
    marker and on the report surplus."""
    params = {}
    if weights is True:
        params[cm.WEIGHTS] = {p: dict(WEIGHTS) for p in default_profiles()}
    elif weights:
        params[cm.WEIGHTS] = weights
    if window:
        params[cm.WINDOW] = dict(WINDOW)

    def rule(rid, subject, when, show, line, effect="flag"):
        return {"id": rid, "scope": "card", "subject": subject, "effect": effect, "post": post,
                "post_since": post_since, "when": when, "show": show, "line": line}
    extra = []
    if conflict:
        extra.append(rule(ID_CONFLICT, "card.record", cmp(M("b4.rec.conflict"), "gt", V(0.37)),
                          [["rec", "b4.rec.index"]], "synthetic conflict {rec}"))
    if picks:
        extra.append(rule(ID_PICKS, "card.record", cmp(M("b4.report.picks.self.rep"), "gt", V(0.37)),
                          [["rep", "b4.report.picks.self.rep"]], "synthetic picks {rep}"))
    doc = {
        "format": 1, "nonce": "", "vocabulary": [], "closure": {}, "measure_params": params,
        "rules": [
            rule(ID_DUP, "card.hand", cmp(M("b4.hand.dup"), "gt", V(dup_at)),
                 [["dup", "b4.hand.dup"], ["phase", "b4.hand.phase"]], "synthetic dup {dup} at {phase}"),
            rule(ID_HELD, "card.hand", cmp(M("b4.hand.heldrej"), "gt", V(0.37)),
                 [["held", "b4.hand.heldrej"]], "synthetic held {held}"),
            rule(ID_PICKER, "card.phase", cmp(M("b4.ph.picker"), "gt", V(0.37)),
                 [["phase", "b4.ph.phase"]], "synthetic picker at {phase}"),
            rule(ID_PAIR, "card.pair", cmp(M("b4.pair.slot"), "gt", V(0.37)),
                 [["slots", "b4.pair.slot"]], "synthetic pair {slots}"),
            rule(ID_WIN, "card.window", cmp(M("b4.rar.hands"), "gt", V(0.37)),
                 [["hands", "b4.rar.hands"], ["games", "b4.rar.games"]],
                 "synthetic window {hands} over {games}"),
            rule(ID_SC, "card.game", cmp(M("b4.sc.norule"), "gt", V(0.37)),
                 [["n", "b4.sc.norule"]], "synthetic sc {n}"),
            rule(ID_NOTE, "card.record", cmp(M("b4.rec.conflict"), "gt", V(0.37)),
                 [["rec", "b4.rec.index"]], "synthetic note {rec}", effect="note"),
        ] + extra,
    }
    doc["rules"] = [r for r in doc["rules"] if r["id"] not in drop]
    return doc


def card_case(records, fire, census_dumps=(), sc=None, windows=()):
    """One self-test case: records are (seat, other, rec dict)."""
    return {"card": {"census": list(census_dumps),
                     "records": [{"seat": s, "other": o, "record": cm.dumps(r), "conflict": False}
                                 for s, o, r in records],
                     "sc": sc, "windows": list(windows)},
            "fire": sorted(fire)}


def dup_record():
    rec = fixture_record("full_game")
    rec["hd"][0][6] = [0, 1, 2, 3, 0]          # a repeated slot
    return rec


def quiet_card_cases():
    full = fixture_record("full_game")
    return [card_case([("a", "b", full)], []),
            card_case([("a", "b", dup_record())], [ID_DUP])]


def build_card_revision(tmp, doc=None, cases=None, name="card"):
    store = os.path.join(str(tmp), "store")
    os.makedirs(store, exist_ok=True)
    draft = os.path.join(str(tmp), name)
    os.makedirs(draft, exist_ok=True)
    with open(os.path.join(draft, "rules.json"), "w", encoding="utf-8") as f:
        json.dump(card_doc() if doc is None else doc, f)
    with open(os.path.join(draft, "selftest.json"), "w", encoding="utf-8") as f:
        json.dump({"cases": quiet_card_cases() if cases is None else cases}, f)
    return store, rr.build_revision(draft, store, "synthetic")


def load(store, rev):
    rs = rr.load_dir(os.path.join(store, "rules-" + rev))
    return rr.State(rs.rev, rs)
