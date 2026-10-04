"""Card draw evidence, the public description of what card records say.

A seat's card record lists every hand dealt in the pick phases of one ranked
game as that seat saw it: its own hands (SELF) and, from the game's own spawn
and end-pick messages, the other seat's hands (MEAS). This module holds:

  * the record layout the client emits (CARD_WIRE, pinned by digest in the
    no-tunables guard) and the checker the route applies;
  * the census layout of a registered card pool and its checker;
  * the deal-profile identity a record carries;
  * the view: every hand, phase, record, pair of hands and game as rows of
    public measures, each one a count or a stated value. A measure whose
    inputs were not captured whole, were trimmed, or need a census that is
    not registered for the record's own game build is unknown (None): it
    never fires and is counted as not run;
  * the rarity expectation of a hand under weights a revision supplies.

Nothing here decides anything. Which measure opens a review item, at what
value, over which window and with what words is a rules revision that is
not part of this repository (review_rules). The weights are the
`params.card_weights` family of that revision and the window is
`params.card_window`; without them no expectation and no window is computed.
"""

from __future__ import annotations

import hashlib
import json
import math
import re

import review_measures as rm

# The client's record layout (plugin/CardDrawEvidenceCore.cs at the client
# lane's fixture tip): field bounds, list caps, enum codes and words. Pinned
# by the sha256 of repr(ast.literal_eval(value)) in review_guard.PINNED_SHA:
# a value changed here changes the digest, and the guard refuses it.
CARD_WIRE = {
    "contract": 2,
    "schema": 1,
    "record_max_bytes": 8192,
    "hourly_cap": 40,
    "prefix": "card-evidence:v1:",
    "keys": ("schema", "g", "end", "ns", "pool", "prof", "po", "sc", "inc", "cards", "held0",
             "ph", "hd", "ap", "apx", "tot", "cost", "omit"),
    "optional": ("end",),
    "end_kinds": ("left", "other_left", "lost", "closing"),
    "omit_keys": ("cards", "held0", "ph", "hd", "ap", "sl", "sp"),
    "omit_pair": "held0",
    "caps": {"sl": 16, "sp": 16, "hd": 40, "ph": 40, "ap": 64, "cards": 128, "held": 64,
             "po": 8, "name": 64, "rules": 32, "semantics": 16},
    "big": 10000000,
    "g_max": 9999,
    "ns_max": 99,
    "ix_max": 9999,
    "ord_max": 999,
    "picks": (-9, 99),
    "rounds_max": 99,
    "src_max": 1073741823,
    "src_slots": 30,
    "int32": (-2147483648, 2147483647),
    "hex_len": 64,
    "pool_states": ("ok", "collision", "changed", "not_run"),
    "hash_states": ("ok", "no_location", "read_failed"),
    "build_caps": (16, 16, 12),
    "semantics": ("cd-sem:2",),
    "inc": {"first": 1, "lost": 2, "fault": 4, "all": 7},
    "pk_none": -2,
    "gen": {"unknown": -1, "vanilla": 0, "opening": 1, "later": 2},
    "sc_verdict": (-1, 2),
    "widths": {"pool": 3, "prof": 9, "sc": 2, "card": 3, "held0": 2, "ph": 7, "hd": 18, "ap": 4,
               "apx": 2, "tot": 7, "roles": 2, "cost": 5, "collectors": 6, "census": 6},
    "census_version": 1,
    "dump_keys": ("census_version", "digest", "card_count", "slot_count", "game_dll", "census_text"),
    "rarities": ("common", "uncommon", "rare"),
    "fixed_point": 1000000,
    "players": 2,
    "bit_base": 2,
    "words": {"ok": "ok", "not_run": "not_run", "self": "self", "meas": "meas", "one": "one",
              "paired": "paired", "on": "on", "off": "off"},
}

W = CARD_WIRE
CAPS = W["caps"]
WIDTH = W["widths"]
WORD = W["words"]
GEN = W["gen"]
INC = W["inc"]
RARITIES = W["rarities"]
I32_LO, I32_HI = W["int32"]

CARD_SUBJECTS = ("card.hand", "card.phase", "card.record", "card.game", "card.pair", "card.window")
# The two measure-parameter families a revision may supply: the per-rarity
# weights the expectation uses, and the window the daily sums are read over.
WEIGHTS = "params.card_weights"
WINDOW = "params.card_window"
WINDOW_KEY = "window_days"
WINDOW_SUBJECT = CARD_SUBJECTS[-1]

_HEX = re.compile(r"[\da-f]+", re.ASCII)
_BUILD_PART = re.compile(r"[A-Za-z\d._+\-]*", re.ASCII)
_PRINTABLE = re.compile(r"[ !#-\[\]-~]*")


class Refusal(Exception):
    """A record or census outside the layout; `field` names what failed."""

    def __init__(self, field: str):
        super().__init__(field)
        self.field = field


# -- the record checker ----------------------------------------------------------

def _hex64(v) -> bool:
    """A full sha256 digest in lowercase hex."""
    return isinstance(v, str) and len(v) == W["hex_len"] and _HEX.fullmatch(v) is not None


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _rng(v, lo, hi) -> bool:
    return _int(v) and lo <= v <= hi


def _ints(v, width, lo, hi) -> bool:
    return isinstance(v, list) and len(v) == width and all(_rng(x, lo, hi) for x in v)


def _ix_list(v, cap) -> bool:
    return isinstance(v, list) and len(v) <= cap and all(_rng(x, -1, W["ix_max"]) for x in v)


def _hash_pair(sha, state) -> bool:
    if not isinstance(sha, str) or state not in W["hash_states"]:
        return False
    if state == WORD["ok"]:
        return _hex64(sha)
    return not sha


def _printable(v, cap) -> bool:
    return isinstance(v, str) and len(v) <= cap and _PRINTABLE.fullmatch(v) is not None


def _check_hd(e) -> bool:
    if not isinstance(e, list) or len(e) != WIDTH["hd"]:
        return False
    o, k, w, wp, an, n, sl, sp_n, sp, pk, pi, ds, src, sq, vid, gl, gen, hn = e
    big, om = W["big"], W["ord_max"]
    return (_rng(o, 0, om) and _rng(k, 0, om) and _rng(w, -1, 1) and _rng(wp, -1, 1)
            and _rng(an, -1, big) and _rng(n, 0, big) and _ix_list(sl, CAPS["sl"])
            and _rng(sp_n, 0, big) and _ix_list(sp, CAPS["sp"]) and _rng(pk, W["pk_none"], om)
            and _rng(pi, -1, om) and _rng(ds, -1, 1) and _rng(src, -1, W["src_max"])
            and _rng(sq, -1, I32_HI) and _rng(vid, -1, I32_HI) and _rng(gl, -1, 1)
            and _rng(gen, GEN["unknown"], GEN["later"]) and _rng(hn, -1, big))


def _f_schema(v):
    return _int(v) and v == W["schema"]


def _f_g(v):
    return _rng(v, 0, W["g_max"])


def _f_end(v):
    return v in W["end_kinds"]


def _f_ns(v):
    return _rng(v, 0, W["ns_max"])


def _f_pool(v):
    if not isinstance(v, list) or len(v) != WIDTH["pool"]:
        return False
    count, digest, state = v
    if not _rng(count, 0, W["ix_max"]) or not isinstance(digest, str):
        return False
    if state not in W["pool_states"]:
        return False
    if not digest:
        return state == WORD["not_run"]
    return _hex64(digest)


def _f_prof(v):
    if not isinstance(v, list) or len(v) != WIDTH["prof"]:
        return False
    gsha, gst, msha, mst, b_ver, b_var, b_commit, sem, rules = v
    parts = (b_ver, b_var, b_commit)
    return (_hash_pair(gsha, gst) and _hash_pair(msha, mst)
            and all(isinstance(p, str) and len(p) <= cap and _BUILD_PART.fullmatch(p) is not None
                    for p, cap in zip(parts, W["build_caps"]))
            and _printable(sem, CAPS["semantics"]) and _printable(rules, CAPS["rules"]))


def _f_po(v):
    return isinstance(v, list) and len(v) <= CAPS["po"] and all(_rng(x, -1, 1) for x in v)


def _f_sc(v):
    lo, hi = W["sc_verdict"]
    return (isinstance(v, list) and len(v) == WIDTH["sc"] and _rng(v[0], -1, 1)
            and _rng(v[-1], lo, hi))


def _f_inc(v):
    return _rng(v, 0, INC["all"])


def _f_cards(v):
    if not isinstance(v, list) or len(v) > CAPS["cards"]:
        return False
    last = -1
    for c in v:
        if not isinstance(c, list) or len(c) != WIDTH["card"]:
            return False
        ix, name, rar = c
        if not _rng(ix, 0, W["ix_max"]) or ix <= last:
            return False
        if not isinstance(name, str) or len(name) > CAPS["name"] or not _rng(rar, I32_LO, I32_HI):
            return False
        last = ix
    return True


def _f_held0(v):
    return (isinstance(v, list) and len(v) == WIDTH["held0"]
            and all(x is None or _ix_list(x, CAPS["held"]) for x in v))


def _f_ph(v):
    if not isinstance(v, list) or len(v) > CAPS["ph"]:
        return False
    om, (plo, phi), rmax = W["ord_max"], W["picks"], W["rounds_max"]
    for e in v:
        if not isinstance(e, list) or len(e) != WIDTH["ph"]:
            return False
        o, w, picks, rs_, ro, nd, done = e
        if not (_rng(o, 0, om) and _rng(w, -1, 1) and _rng(picks, plo, phi) and _rng(rs_, 0, rmax)
                and _rng(ro, 0, rmax) and _rng(nd, 0, om) and _rng(done, 0, 1)):
            return False
    return True


def _f_hd(v):
    return isinstance(v, list) and len(v) <= CAPS["hd"] and all(_check_hd(e) for e in v)


def _f_ap(v):
    if not isinstance(v, list) or len(v) > CAPS["ap"]:
        return False
    for e in v:
        if not isinstance(e, list) or len(e) != WIDTH["ap"]:
            return False
        w, ix, kind, vid = e
        if not (_rng(w, -1, 1) and _rng(ix, -1, W["ix_max"]) and _rng(kind, 0, 1)
                and _rng(vid, -1, I32_HI)):
            return False
    return True


def _f_apx(v):
    return _ints(v, WIDTH["apx"], 0, W["big"])


def _f_tot(v):
    return (isinstance(v, list) and len(v) == WIDTH["roles"]
            and all(_ints(x, WIDTH["tot"], 0, W["big"]) for x in v))


def _f_cost(v):
    return (isinstance(v, list) and len(v) == WIDTH["collectors"]
            and all(_ints(x, WIDTH["cost"], 0, W["big"]) for x in v))


def _f_omit(v):
    if not isinstance(v, dict) or list(v.keys()) != list(W["omit_keys"]):
        return False
    return all(_ints(x, WIDTH["held0"], 0, W["big"]) if isinstance(x, list) else _rng(x, 0, W["big"])
               for x in v.values()) and isinstance(v[W["omit_pair"]], list)


# One checker per record key (dispatch by the layout's own key; no key is
# compared against a word here).
_FIELD = {"schema": _f_schema, "g": _f_g, "end": _f_end, "ns": _f_ns, "pool": _f_pool,
          "prof": _f_prof, "po": _f_po, "sc": _f_sc, "inc": _f_inc, "cards": _f_cards,
          "held0": _f_held0, "ph": _f_ph, "hd": _f_hd, "ap": _f_ap, "apx": _f_apx, "tot": _f_tot,
          "cost": _f_cost, "omit": _f_omit}


def record_keys(rec) -> list:
    return [k for k in W["keys"] if k not in W["optional"] or k in rec]


def _refs(rec) -> set:
    out = set()
    for e in rec["hd"]:
        _o, _k, _w, _wp, _an, _n, sl, _spn, sp, *_rest = e
        out.update(x for x in sl if x >= 0)
        out.update(x for x in sp if x >= 0)
    for lst in rec["held0"]:
        if lst is not None:
            out.update(x for x in lst if x >= 0)
    for _w, ix, _kind, _vid in rec["ap"]:
        if ix >= 0:
            out.add(ix)
    return out


def check_record(rec) -> None:
    """Raise Refusal(<key>) for the first key outside its bound, a key set or
    order other than the layout's, a referenced pool index the `cards` list
    does not name, or a record whose first phase was not captured but which
    still carries the lists only that phase reads."""
    if not isinstance(rec, dict):
        raise Refusal("record")
    keys = list(rec.keys())
    want = record_keys(rec)
    if keys != want:
        missing = [k for k in want if k not in rec]
        extra = [k for k in keys if k not in W["keys"]]
        raise Refusal((missing or extra or ["key_order"])[0])
    for key in want:
        if not _FIELD[key](rec[key]):
            raise Refusal(key)
    named = {c[0] for c in rec["cards"]}
    if not _refs(rec) <= named:
        raise Refusal("cards_named")
    if rec["inc"] & INC["first"] and (rec["po"] or any(x is not None for x in rec["held0"])):
        raise Refusal("inc_first")


def _refuse_number(_text):
    raise Refusal("record_number")


def parse_record_text(text: str) -> dict:
    """The record text as a dict, checked. Floats and non-finite constants
    are refused; integers only."""
    try:
        rec = json.loads(text, parse_float=_refuse_number, parse_constant=_refuse_number)
    except Refusal:
        raise
    except ValueError:
        raise Refusal("record_json")
    check_record(rec)
    return rec


def dumps(obj) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=True)


# -- the census of a registered pool ------------------------------------------------

def _names_or_null(v) -> bool:
    return v is None or (isinstance(v, list) and all(x is None or isinstance(x, str) for x in v))


def check_census_text(text) -> list:
    """The census text a reference seat dumped: canonical JSON with arrays
    preserved, one entry per pool card in pool order. Returns the card list;
    raises Refusal when the text is not exactly its own canonical form, so two
    different pools can never share one text."""
    if not isinstance(text, str) or not text.isascii():
        raise Refusal("census_text")
    try:
        doc = json.loads(text, parse_float=_refuse_number, parse_constant=_refuse_number)
    except Refusal:
        raise
    except ValueError:
        raise Refusal("census_json")
    if not isinstance(doc, dict) or list(doc.keys()) != ["census", "cards"]:
        raise Refusal("census_keys")
    if not _int(doc["census"]) or doc["census"] != W["census_version"]:
        raise Refusal("census_version")
    cards = doc["cards"]
    if not isinstance(cards, list) or len(cards) > W["ix_max"]:
        raise Refusal("census_cards")
    for c in cards:
        if not isinstance(c, list) or len(c) != WIDTH["census"]:
            raise Refusal("census_card")
        name, rar, multi, cats, black, lock = c
        if (not isinstance(name, str) or not _rng(rar, I32_LO, I32_HI) or not _rng(multi, 0, 1)
                or not _names_or_null(cats) or not _names_or_null(black) or not _rng(lock, 0, 1)):
            raise Refusal("census_card")
    if dumps(doc) != text:
        raise Refusal("census_canonical")
    return cards


def census_digest(text: str) -> str:
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def census_from_dump(doc):
    """A census dump file as a reference seat writes it, checked whole: its
    stated digest must be the digest of its own census text, its card count
    the text's card count, and the game build it was read on hashed."""
    if not isinstance(doc, dict) or list(doc.keys()) != list(W["dump_keys"]):
        raise Refusal("dump_keys")
    if not _int(doc["census_version"]) or doc["census_version"] != W["census_version"]:
        raise Refusal("census_version")
    cards = check_census_text(doc["census_text"])
    digest = census_digest(doc["census_text"])
    if doc["digest"] != digest:
        raise Refusal("digest")
    if not _int(doc["card_count"]) or doc["card_count"] != len(cards):
        raise Refusal("card_count")
    if not _rng(doc["slot_count"], 0, W["ns_max"]):
        raise Refusal("slot_count")
    dll = doc["game_dll"]
    if (not isinstance(dll, list) or len(dll) != WIDTH["held0"] or dll[-1] != WORD["ok"]
            or not _hash_pair(dll[0], dll[-1])):
        raise Refusal("game_dll")
    return Census(digest, cards, doc["slot_count"], dll[0])


def deal_profile(rec) -> str:
    """The record's own deal identity: the full sha256 over its nine profile
    entries, its pool digest and its slot count. Contributions are keyed by
    this AND the rules revision that weighed them."""
    return hashlib.sha256(dumps([rec["prof"], rec["pool"][1], rec["ns"]]).encode("ascii")).hexdigest()


# -- the view ----------------------------------------------------------------------

def _bits(mask, width) -> list:
    out = []
    for _ in range(width):
        mask, r = divmod(mask, W["bit_base"])
        out.append(r)
    return out


class Census:
    """A registered census as the view reads it."""

    __slots__ = ("digest", "cards", "count", "slots", "game_sha", "by_name", "supported")

    def __init__(self, digest, cards, slots, game_sha):
        self.digest = digest
        self.cards = cards
        self.count = len(cards)
        self.slots = slots
        self.game_sha = game_sha
        self.by_name = {}
        for ix, c in enumerate(cards):
            self.by_name.setdefault(c[0], ix)
        self.supported = all(0 <= c[1] < len(RARITIES) for c in cards)

    def name(self, ix):
        return self.cards[ix][0]


class RecFacts:
    """One stored record and what the view may rely on in it."""

    def __init__(self, i, r, registry):
        rec = r["rec"]
        self.i = i
        self.rec = rec
        self.seat = r["seat"]
        self.other = r["other"]
        self.conflict = bool(r.get("conflict"))
        self.omit = rec["omit"]
        inc = rec["inc"]
        self.sem_ok = rec["prof"][7] in W["semantics"]
        self.lossy = bool(inc & INC["lost"]) or bool(inc & INC["fault"]) or not self.sem_ok
        self.first_lost = bool(inc & INC["first"])
        self.names = {c[0]: c[1] for c in rec["cards"]}
        self.rars = {c[0]: c[-1] for c in rec["cards"]}
        count, digest, state = rec["pool"]
        gsha, gstate = rec["prof"][0], rec["prof"][1]
        self.digest = digest
        self.registered = bool(digest) and digest in registry
        c = registry.get(digest) if digest else None
        self.census = (c if c is not None and state == WORD["ok"] and gstate == WORD["ok"]
                       and c.game_sha == gsha and c.count == count else None)
        self.hd_ok = self.omit["hd"] == 0 and not self.lossy
        self.ph_ok = self.omit["ph"] == 0 and not self.lossy
        self.ap_ok = self.omit["ap"] == 0 and self.omit["cards"] == 0 and not self.lossy
        held_omit = self.omit["held0"]
        self.held_ok = [not self.first_lost and rec["held0"][r_] is not None and held_omit[r_] == 0
                        for r_ in range(WIDTH["roles"])]
        self.apps = [[ix for w, ix, _k, _v in rec["ap"] if w == r_] for r_ in range(WIDTH["roles"])]
        self.ap_unknown = any(w < 0 for w, _ix, _k, _v in rec["ap"])

    def player(self, role):
        if role == 0:
            return self.seat
        if role == 1:
            return self.other
        return None

    def role_of(self, player):
        if player == self.seat:
            return 0
        if player == self.other:
            return 1
        return None

    def held_at(self, role, an, hn):
        """The held set (pool indexes) of `role` at a deal: the first-phase
        list plus the first `an` completed applications. Unknown when either
        input was not captured whole, or when it disagrees with the held
        count the seat read at the deal."""
        if role is None or not self.held_ok[role] or not self.ap_ok or self.ap_unknown or an < 0:
            return None
        apps = self.apps[role]
        if an > len(apps):
            return None
        held = list(self.rec["held0"][role]) + apps[:an]
        if any(x < 0 for x in held):
            return None
        if hn >= 0 and hn != len(held):
            return None
        return held


def _hand_fields(e):
    o, k, w, wp, an, n, sl, sp_n, sp, pk, pi, ds, src, sq, vid, gl, gen, hn = e
    return {"o": o, "k": k, "w": w, "wp": wp, "an": an, "n": n, "sl": sl, "sp_n": sp_n, "sp": sp,
            "pk": pk, "pi": pi, "ds": ds, "src": src, "sq": sq, "vid": vid, "gl": gl, "gen": gen,
            "hn": hn}


def _rejects_vanilla(census, cand, held, gl):
    """The game's held-card rule for a slot after the first: a held card's
    blacklist names a category of the candidate; the candidate is not
    allowMultiple and a held card has its name; or both the candidate's gun
    and the picker's gun lock to default. None when the lock clause is
    needed and the gun bit was not read."""
    c = census.cards[cand]
    if _blacklisted(census, c, held):
        return True
    if not c[2] and any(census.cards[h][0] == c[0] for h in held):
        return True
    if c[-1]:
        if gl < 0:
            return None
        return gl == 1
    return False


def _rejects_local(census, cand, held, gl):
    """The shared-sequence engine's local legality for a later draw: the
    blacklist and the gun-lock clauses only, on every slot."""
    c = census.cards[cand]
    if _blacklisted(census, c, held):
        return True
    if c[-1]:
        if gl < 0:
            return None
        return gl == 1
    return False


def _blacklisted(census, c, held) -> bool:
    cats = c[3]
    if not cats:
        return False
    names = {x for x in cats if x is not None}
    for h in held:
        black = census.cards[h][4]
        if black and any(b is not None and b in names for b in black):
            return True
    return False


def _gen_slots(f, dealer_self, series_sc):
    """Per slot: the generation that produced it (vanilla, opening, later),
    or None when it is not known. A SELF hand reads its own recorded source;
    a MEAS hand reads the dealer's own SELF entry when the dealer's record is
    present and pairs, else the series row (off: every slot vanilla)."""
    src_hand = f if f["w"] == 0 else dealer_self
    if src_hand is not None:
        src, gen = src_hand["src"], src_hand["gen"]
        if src < 0:
            return None
        bits = _bits(src, len(f["sl"]))
        if any(bits) and gen not in (GEN["opening"], GEN["later"]):
            return None
        return [gen if b else GEN["vanilla"] for b in bits]
    if series_sc == WORD["off"]:
        return [GEN["vanilla"]] * len(f["sl"])
    return None


def _heldrej(census, sl, held, gl, gens):
    count = 0
    for j, ix in enumerate(sl):
        g = gens[j]
        if g == GEN["opening"]:
            continue
        if g == GEN["later"]:
            r = _rejects_local(census, ix, held, gl)
        elif j == 0:
            continue
        else:
            r = _rejects_vanilla(census, ix, held, gl)
        if r is None:
            return None
        if r:
            count += 1
    return count


def expectation(census, sl, held, gl, weights):
    """Per rarity, (observed, expected, variance) over the slots of one hand
    dealt by the game's own draw: each slot's probability of a rarity is the
    weight of the allowed cards of that rarity over the weight of every
    allowed card, the allowed set being the pool for the first slot and, for
    a later slot, the pool minus the earlier slots' cards minus the cards the
    held-card rule rejects. Returns None when any slot's allowed weight is
    not positive or the lock clause is needed without the gun bit."""
    if weights is None or not census.supported:
        return None
    wv = [weights[r] for r in RARITIES]
    obs = [0] * len(RARITIES)
    exp = [0.0] * len(RARITIES)
    var = [0.0] * len(RARITIES)
    for j, ix in enumerate(sl):
        earlier = set(sl[:j])
        per = [0.0] * len(RARITIES)
        for cand, c in enumerate(census.cards):
            if cand in earlier:
                continue
            if j > 0:
                r = _rejects_vanilla(census, cand, held, gl)
                if r is None:
                    return None
                if r:
                    continue
            per[c[1]] += wv[c[1]]
        total = sum(per)
        if total <= 0:
            return None
        obs[census.cards[ix][1]] += 1
        for r in range(len(RARITIES)):
            p = per[r] / total
            exp[r] += p
            var[r] += p * (1 - p)
    return obs, exp, var


HAND_RULES = ("b4.hand.size", "b4.hand.unres", "b4.hand.notpool", "b4.hand.dup",
              "b4.hand.heldrej", "b4.hand.w0", "b4.hand.spx", "b4.hand.spo")
PICK_RULES = ("b4.pick.out", "b4.pick.slot", "b4.pick.who")
PHASE_RULES = ("b4.ph.dvp", "b4.ph.picker", "b4.ph.notdone")


def _hand_row(rf, f, other_rf, dealer_self, series_sc, weights):
    """One hand entry of one record, as measures."""
    rec = rf.rec
    n, sl, w = f["n"], f["sl"], f["w"]
    complete = len(sl) == n and not rf.lossy
    resolved = complete and all(x >= 0 for x in sl)
    row = {"b4.hand.recorder": rf.i, "b4.hand.meas": None if w < 0 else w, "b4.hand.phase": f["o"],
           "b4.hand.deal": f["k"], "b4.hand.n": n, "b4.hand.n_exp": rec["ns"]}
    # the census that describes this hand: the recorder's own, when it is the
    # dealer's pool (the dealer's stated digest, or every slot resolved here)
    census = rf.census
    if w == 1 and census is not None:
        if other_rf is not None:
            if other_rf.digest != rf.digest:
                census = None
        elif not resolved:
            census = None
    if w < 0:
        census = None
    row["b4.hand.n_reg"] = census.slots if census is not None else None
    row["b4.hand.size"] = None if rf.lossy else int(n != rec["ns"])
    row["b4.hand.unres"] = sum(1 for x in sl if x < 0) if complete else None
    row["b4.hand.dup"] = (sum(1 for j, x in enumerate(sl) if x in sl[:j]) if resolved else None)
    if census is not None and complete:
        row["b4.hand.notpool"] = sum(
            1 for x in sl if x >= 0 and (x >= census.count or rf.names.get(x) != census.name(x)[:CAPS["name"]]
                                         or rf.rars.get(x) != census.cards[x][1]))
    else:
        row["b4.hand.notpool"] = None
    # slots of a rarity the revision's weights never deal (no weights, a pool
    # with a rarity outside the three, or a slot outside the pool: unknown)
    row["b4.hand.w0"] = (sum(1 for x in sl if weights[RARITIES[census.cards[x][1]]] <= 0)
                         if weights is not None and census is not None and census.supported
                         and resolved and row["b4.hand.notpool"] == 0 else None)
    held = rf.held_at(w if w >= 0 else None, f["an"], f["hn"])
    gens = _gen_slots(f, dealer_self, series_sc)
    if (census is not None and resolved and held is not None and gens is not None
            and row["b4.hand.notpool"] == 0):
        row["b4.hand.heldrej"] = _heldrej(census, sl, held, f["gl"], gens)
    else:
        row["b4.hand.heldrej"] = None
    row["b4.hand.spx"] = None if rf.lossy else f["sp_n"] - n
    row["b4.hand.spo"] = None if rf.lossy else int(bool(f["sp"]))
    row["b4.hand.ds0"] = None if f["ds"] < 0 or rf.lossy else int(f["ds"] == 0)
    pk, pi, vid, wp = f["pk"], f["pi"], f["vid"], f["wp"]
    row["b4.pick.out"] = None if rf.lossy else int(pi < 0 and vid >= 0)
    row["b4.pick.slot"] = None if rf.lossy else int(pk >= 0 and pk != pi)
    row["b4.pick.who"] = None if (wp < 0 or w < 0 or rf.lossy) else int(wp != w)
    row["b4.hand.picked"] = None if rf.lossy else int(pk != W["pk_none"])
    row["b4.hand.notrun"] = sum(1 for k in HAND_RULES if row[k] is None)
    vanilla = gens is not None and all(g == GEN["vanilla"] for g in gens)
    eligible = (census is not None and resolved and held is not None and vanilla
                and all(row[k] == 0 for k in HAND_RULES))
    exp = expectation(census, sl, held, f["gl"], weights) if eligible else None
    row["b4.hand.eligible"] = int(exp is not None)
    meta = {"recorder": rf.seat, "dealer": rf.player(w), "w": w, "o": f["o"], "k": f["k"], "n": n,
            "exp": exp, "vid": f["vid"], "profile": deal_profile(rec), "census": census,
            "held": held, "gens": gens}
    return row, meta


def _phase_rows(rf):
    rows = []
    ph = rf.rec["ph"]
    by_o = {e[0]: e for e in ph}
    po = rf.rec["po"]
    po_ok = (not rf.first_lost and len(po) == W["players"] and sorted(po) == list(range(W["players"])))
    for idx, e in enumerate(ph):
        o, w, picks, rs, ro, nd, done = e
        row = {"b4.ph.recorder": rf.i, "b4.ph.phase": o, "b4.ph.role": w,
               "b4.ph.last": int(idx == len(ph) - 1)}
        row["b4.ph.dvp"] = None if rf.lossy else nd - picks
        row["b4.ph.notdone"] = None if rf.lossy else int(not done and idx != len(ph) - 1)
        picker = None
        if not rf.lossy and w >= 0:
            if o < W["players"]:
                if po_ok:
                    picker = int(w != po[o])
            else:
                prev = by_o.get(o - 1)
                if prev is not None:
                    drs, dro = rs - prev[3], ro - prev[4]
                    if drs == 1 and dro == 0:
                        picker = int(w != 1)
                    elif drs == 0 and dro == 1:
                        picker = int(w != 0)
        row["b4.ph.picker"] = picker
        rows.append((row, {"recorder": rf.seat, "o": o, "w": w}))
    return rows


def _record_row(rf, hand_rows, series_sc):
    rec = rf.rec
    row = {"b4.rec.index": rf.i, "b4.rec.inc": rec["inc"], "b4.rec.conflict": int(rf.conflict),
           "b4.rec.unreg": None if not rf.digest else int(not rf.registered),
           "b4.rec.census": int(rf.census is not None),
           "b4.rec.hands": len(hand_rows), "b4.rec.cut": int(len(rec) != len(W["keys"]) - len(W["optional"])),
           "b4.rec.notrun_hands": sum(1 for h in hand_rows if h["b4.hand.notrun"])}
    if rf.ap_ok and rf.hd_ok and not rf.ap_unknown:
        picked = {(e[2], e[14]) for e in rec["hd"] if e[9] >= 0 and e[14] >= 0}
        row["b4.app.unpaired"] = sum(1 for w, _ix, kind, vid in rec["ap"]
                                     if kind == 0 and (w, vid) not in picked)
    else:
        row["b4.app.unpaired"] = None
    row["b4.app.offline"] = sum(1 for e in rec["ap"] if e[2] == 1) if rf.ap_ok else None
    rule = rec["sc"][0]
    if series_sc is None or rule < 0:
        row["b4.sc.rule"] = None
    else:
        row["b4.sc.rule"] = int(rule != int(series_sc == WORD["on"]))
    return row


def _pair_name(rf, ix):
    return rf.names.get(ix)


def _slot_diff(a_rf, a_sl, b_rf, b_sl):
    if any(x < 0 for x in a_sl) or any(x < 0 for x in b_sl):
        return None
    diff = abs(len(a_sl) - len(b_sl))
    for x, y in zip(a_sl, b_sl):
        if _pair_name(a_rf, x) != _pair_name(b_rf, y):
            diff += 1
    return diff


def _held_names(rf, held):
    return None if held is None else sorted(rf.names.get(h, "") for h in held)


def _locally_rejected(census, name, held, gl, earlier):
    """Whether the shared-sequence engine's local legality would refuse the
    card `name` for a player holding `held`: unknown card, a card already in
    the hand, or the blacklist and lock clauses."""
    cand = census.by_name.get(name)
    if cand is None:
        return None
    if cand in earlier:
        return True
    return _rejects_local(census, cand, held, gl)


def card_view(records, registry, series_sc=None, weights=None) -> dict:
    """Every row the card rules and the admin read see for one game: hands,
    phases, records, pairs of hands, the game. `records` are dicts with
    seat, other, rec and conflict; `registry` maps a pool digest to a Census;
    `series_sc` is the series row's frozen Same Cards rule (on, off or None
    when unknown); `weights` the revision's weight family (None: no
    expectation)."""
    facts = [RecFacts(i, r, registry) for i, r in enumerate(records)]
    by_seat = {rf.seat: rf for rf in facts}
    two = len(facts) == W["players"] and all(rf.other in by_seat for rf in facts)
    hands, phases, recs, pairs = [], [], [], []
    self_entries = {}
    for rf in facts:
        for e in rf.rec["hd"]:
            f = _hand_fields(e)
            if f["w"] == 0 and f["vid"] >= 0:
                self_entries[(rf.seat, f["o"], f["k"], f["vid"])] = f
    per_rec_rows = []
    for rf in facts:
        other_rf = by_seat.get(rf.other) if two else None
        rows = []
        for e in rf.rec["hd"]:
            f = _hand_fields(e)
            dealer_self = None
            if f["w"] == 1 and other_rf is not None and f["vid"] >= 0:
                dealer_self = self_entries.get((rf.other, f["o"], f["k"], f["vid"]))
            row, meta = _hand_row(rf, f, other_rf if f["w"] == 1 else None, dealer_self, series_sc,
                                  weights)
            rows.append((row, meta))
        hands.extend(rows)
        per_rec_rows.append(rows)
        phases.extend(_phase_rows(rf))
    for rf, rows in zip(facts, per_rec_rows):
        recs.append((_record_row(rf, [r for r, _m in rows], series_sc), {"recorder": rf.seat}))
    game = {"b4.game.records": len(facts), "b4.game.paired": int(two)}
    if two:
        a, b = facts
        ha = {(m["dealer"], m["o"], m["k"]): (r, m) for r, m in per_rec_rows[0] if m["dealer"]}
        hb = {(m["dealer"], m["o"], m["k"]): (r, m) for r, m in per_rec_rows[1] if m["dealer"]}
        paired, unpaired = 0, 0
        for key in sorted(set(ha) | set(hb), key=str):
            x, y = ha.get(key), hb.get(key)
            if x is None or y is None or x[1]["vid"] < 0 or x[1]["vid"] != y[1]["vid"]:
                unpaired += 1
                continue
            paired += 1
            ea = next(_hand_fields(e) for e in a.rec["hd"]
                      if (a.player(e[2]), e[0], e[1]) == key)
            eb = next(_hand_fields(e) for e in b.rec["hd"]
                      if (b.player(e[2]), e[0], e[1]) == key)
            complete = (len(ea["sl"]) == ea["n"] and len(eb["sl"]) == eb["n"]
                        and not a.lossy and not b.lossy)
            prow = {"b4.pair.phase": key[1], "b4.pair.deal": key[2]}
            prow["b4.pair.slot"] = _slot_diff(a, ea["sl"], b, eb["sl"]) if complete else None
            if a.lossy or b.lossy:
                prow["b4.pair.pick"] = None
            else:
                pa = _pair_name(a, ea["sl"][ea["pk"]]) if 0 <= ea["pk"] < len(ea["sl"]) else None
                pb = _pair_name(b, eb["sl"][eb["pk"]]) if 0 <= eb["pk"] < len(eb["sl"]) else None
                prow["b4.pair.pick"] = int(ea["pk"] != eb["pk"] or pa != pb)
            prow["b4.pair.spawn"] = None if (a.lossy or b.lossy) else int(ea["sp_n"] != eb["sp_n"])
            na, nb = _held_names(a, x[1]["held"]), _held_names(b, y[1]["held"])
            prow["b4.pair.held"] = None if na is None or nb is None else int(na != nb)
            pairs.append((prow, {"dealer": key[0], "o": key[1], "k": key[2]}))
        complete = a.hd_ok and b.hd_ok
        game["b4.pair.n"] = paired
        game["b4.pair.unpair"] = unpaired if complete else None
    else:
        game["b4.pair.n"] = None
        game["b4.pair.unpair"] = None
    game.update(_same_cards(facts, per_rec_rows, two, series_sc))
    return {"hands": hands, "phases": phases, "records": recs, "pairs": pairs, "game": game,
            "two": two, "facts": facts}


def _own_hands(rf, rows, gen):
    out = []
    for row, meta in rows:
        e = next(_hand_fields(x) for x in rf.rec["hd"] if x[0] == meta["o"] and x[1] == meta["k"]
                 and x[2] == meta["w"])
        if e["w"] == 0 and e["gen"] == gen and e["src"] > 0:
            out.append((e, meta))
    return out


def _same_cards(facts, per_rec_rows, two, series_sc) -> dict:
    """The Same Cards measures against the series row's frozen rule: shared
    slots stated under an off rule, opening hands that differ where both were
    served by the shared sequence, and later shared draws that differ where
    the local legality would not have substituted."""
    out = {"b4.sc.norule": None, "b4.sc.open": None, "b4.sc.k": None}
    if series_sc is None:
        return out
    if series_sc == WORD["off"]:
        stated, unknown = 0, False
        for rf in facts:
            for e in rf.rec["hd"]:
                f = _hand_fields(e)
                if f["w"] != 0:
                    continue
                if f["src"] < 0:
                    unknown = True
                else:
                    stated += sum(_bits(f["src"], len(f["sl"])))
        out["b4.sc.norule"] = None if unknown else stated
        return out
    out["b4.sc.norule"] = 0
    if not two or any(rf.lossy for rf in facts):
        return out
    a, b = facts
    oa = _own_hands(a, per_rec_rows[0], GEN["opening"])
    ob = _own_hands(b, per_rec_rows[1], GEN["opening"])
    if oa and ob:
        diff = 0
        ea, eb = oa[0][0], ob[0][0]
        if any(x < 0 for x in ea["sl"]) or any(x < 0 for x in eb["sl"]):
            diff = None
        else:
            ba, bb = _bits(ea["src"], len(ea["sl"])), _bits(eb["src"], len(eb["sl"]))
            for j in range(min(len(ea["sl"]), len(eb["sl"]))):
                if ba[j] and bb[j] and a.names.get(ea["sl"][j]) != b.names.get(eb["sl"][j]):
                    diff += 1
        out["b4.sc.open"] = diff
    la = _own_hands(a, per_rec_rows[0], GEN["later"])
    lb = {e["sq"]: (e, m) for e, m in _own_hands(b, per_rec_rows[1], GEN["later"]) if e["sq"] > 0}
    total = 0
    for ea, ma in la:
        hit = lb.get(ea["sq"])
        if hit is None:
            continue
        eb, mb = hit
        if (a.census is None or b.census is None or ma["held"] is None or mb["held"] is None
                or any(x < 0 for x in ea["sl"]) or any(x < 0 for x in eb["sl"])):
            return dict(out, **{"b4.sc.k": None})
        ba, bb = _bits(ea["src"], len(ea["sl"])), _bits(eb["src"], len(eb["sl"]))
        for j in range(min(len(ea["sl"]), len(eb["sl"]))):
            if not (ba[j] and bb[j]):
                continue
            na, nb = a.names.get(ea["sl"][j]), b.names.get(eb["sl"][j])
            if na == nb:
                continue
            ra = _locally_rejected(a.census, nb, ma["held"], ea["gl"], set(ea["sl"][:j]))
            rb = _locally_rejected(b.census, na, mb["held"], eb["gl"], set(eb["sl"][:j]))
            if ra is None or rb is None:
                return dict(out, **{"b4.sc.k": None})
            if not ra and not rb:
                total += 1
    out["b4.sc.k"] = total
    return out


# -- contributions and the window ------------------------------------------------------

def contributions(view, weights) -> list:
    """Per recorder and dealer: hands and slots that entered the expectation,
    hands that could not (not run), and per rarity the observed count and the
    fixed-point expected count and variance. Source is SELF for the
    recorder's own hands and MEAS for the other seat's; coverage is paired
    when both records name each other. Empty without weights."""
    if weights is None:
        return []
    fix = W["fixed_point"]
    coverage = WORD["paired"] if view["two"] else WORD["one"]
    out = {}
    for row, meta in view["hands"]:
        if meta["dealer"] is None:
            continue
        source = WORD["self"] if meta["w"] == 0 else WORD["meas"]
        key = (meta["recorder"], meta["dealer"], source, meta["profile"])
        c = out.setdefault(key, {"recorder": meta["recorder"], "subject": meta["dealer"],
                                 "source": source, "coverage": coverage, "profile": meta["profile"],
                                 "hands": 0, "slots": 0, "notrun_hands": 0,
                                 "obs": [0] * len(RARITIES), "exp": [0] * len(RARITIES),
                                 "var": [0] * len(RARITIES)})
        if meta["exp"] is None:
            c["notrun_hands"] += 1
            continue
        obs, exp, var = meta["exp"]
        c["hands"] += 1
        c["slots"] += meta["n"]
        for r in range(len(RARITIES)):
            c["obs"][r] += obs[r]
            c["exp"][r] += int(round(exp[r] * fix))
            c["var"][r] += int(round(var[r] * fix))
    return [out[k] for k in sorted(out, key=str)]


def window_row(agg) -> dict:
    """A window's sums (from the daily rows) as measures. Expected counts and
    variances arrive in fixed point."""
    fix = W["fixed_point"]
    row = {"b4.rar.games": agg["games"], "b4.rar.hands": agg["hands"], "b4.rar.slots": agg["slots"],
           "b4.rar.notrun": agg["notrun_hands"], "b4.rar.meas": int(agg["source"] == WORD["meas"]),
           "b4.rar.paired": int(agg["coverage"] == WORD["paired"])}
    for r, name in enumerate(RARITIES):
        obs = agg["obs"][r]
        exp = agg["exp"][r] / fix
        var = agg["var"][r] / fix
        row["b4.rar.obs." + name] = obs
        row["b4.rar.exp." + name] = exp
        row["b4.rar.var." + name] = var
        row["b4.rar.dev." + name] = (obs - exp) / math.sqrt(var) if var > 0 else None
    return row


# -- the vocabulary -----------------------------------------------------------------

class CardCtx:
    """One row of one card subject; `i` keys the evaluator's memo."""

    __slots__ = ("i", "row")

    def __init__(self, i, row):
        self.i = i
        self.row = row


def card_subjects(view, windows=()) -> dict:
    out = {s: [] for s in CARD_SUBJECTS}
    for name, rows in (("card.hand", view.get("hands", ())), ("card.phase", view.get("phases", ())),
                       ("card.record", view.get("records", ())), ("card.pair", view.get("pairs", ()))):
        out[name] = [CardCtx((name, j), r) for j, (r, _m) in enumerate(rows)]
    if view.get("game") is not None:
        out["card.game"] = [CardCtx(("card.game", 0), view["game"])]
    out["card.window"] = [CardCtx(("card.window", j), w) for j, w in enumerate(windows)]
    return out


MEASURES = {
    "card.hand": ("b4.hand.recorder", "b4.hand.meas", "b4.hand.phase", "b4.hand.deal",
                  "b4.hand.n", "b4.hand.n_exp", "b4.hand.n_reg") + HAND_RULES
                 + ("b4.hand.ds0",) + PICK_RULES + ("b4.hand.picked", "b4.hand.notrun", "b4.hand.eligible"),
    "card.phase": ("b4.ph.recorder", "b4.ph.phase", "b4.ph.role", "b4.ph.last") + PHASE_RULES,
    "card.record": ("b4.rec.index", "b4.rec.inc", "b4.rec.conflict", "b4.rec.unreg",
                    "b4.rec.census", "b4.rec.hands", "b4.rec.cut", "b4.rec.notrun_hands", "b4.app.unpaired",
                    "b4.app.offline", "b4.sc.rule"),
    "card.game": ("b4.game.records", "b4.game.paired", "b4.pair.n", "b4.pair.unpair",
                  "b4.sc.norule", "b4.sc.open", "b4.sc.k"),
    "card.pair": ("b4.pair.phase", "b4.pair.deal", "b4.pair.slot", "b4.pair.pick",
                  "b4.pair.spawn", "b4.pair.held"),
    "card.window": ("b4.rar.games", "b4.rar.hands", "b4.rar.slots", "b4.rar.notrun",
                    "b4.rar.meas", "b4.rar.paired")
                   + tuple("b4.rar." + part + "." + name for part in ("obs", "exp", "var", "dev")
                           for name in RARITIES),
}


def _reader(name):
    def read(ctx, p):
        return ctx.row.get(name)
    return read


def _register_card_vocabulary():
    for subject, names in MEASURES.items():
        for name in names:
            rm._register(rm.Entry("measure", name, (_reader(name),), subject=subject))
    rm._register(rm.Entry("params", WEIGHTS, data=list(RARITIES)))
    rm._register(rm.Entry("params", WINDOW, data=[WINDOW_KEY]))


if not any(e.subject in CARD_SUBJECTS for e in list(rm.REGISTRY.values())):
    _register_card_vocabulary()
