"""The second, independent method for what each card measure reads: run the
measures and watch. It shares no code with card_read_sets (the static
analysis): it never parses card_measures.py, it imports and RUNS it.

  1. A recording view. Each stored record is wrapped so that every
     coverage-bearing field the measure code touches is logged: a top-level
     key of the record (a fact-certified list, the first-phase order, the
     loss and fault bits, the profile carrying the semantics word), a key
     of the stated omission counts, and the slot list and spawn list of
     every hand entry.
  2. Perturbation. For each coverage fact, the data that fact certifies is
     changed the ways the fact allows (a list trimmed at either end or
     emptied, a hand entry's slot or spawn list trimmed or emptied, a
     first-phase held list absent, the loss, fault or first bit set,
     the semantics word changed, the first-phase order reversed, the
     omission count stated), one record of the game at a time, and every
     measure is recomputed. DYN(m) is the set of facts whose change moved
     m's value on a row present in both runs (rows keyed by identity:
     recorder, phase, deal, role and occurrence; windows by contribution
     class).
  3. The gate is taken out, exactly the three exclusions the static method
     states: _gate does nothing, covered() is true, and every record states
     every fact whole, so a value can only move through the measure code.
  4. Branch coverage of the measure functions under the fixture set, from
     the interpreter's own branch events (sys.monitoring): every
     conditional jump and loop test in the code of every function of the
     view section of card_measures and every function those call, with each
     arm that never ran listed.

The fixtures: the full game paired with its mirror (Same Cards off, a
report), game two under Same Cards on, the same with the rule off and
unknown, each client fixture alone (full, cut, first phase lost, over the
cap), and the full game with no weights, no census, no report and the loss
bit set."""

import copy
import dis
import inspect
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
for p in (API, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import card_measures as cm  # noqa: E402
import card_revision_kit as k  # noqa: E402

FACTS = tuple(cm.COVER)
LIST_FACTS = ("cards", "held0", "ph", "hd", "ap")
SL, SP = 6, 8                    # the slot and spawn lists' positions in a hand entry (the wire order)
SEM = 7                          # the semantics word's position in the profile (the wire order)


# -- 1. the recording view -------------------------------------------------------------

class _Logged(dict):
    """A dict that logs every key read, and a read of the whole as '*'."""

    def __init__(self, d, log, tag):
        super().__init__(d)
        self._log, self._tag = log, tag

    def __getitem__(self, key):
        self._log.add((self._tag, key))
        return super().__getitem__(key)

    def get(self, key, default=None):
        self._log.add((self._tag, key))
        return super().get(key, default)

    def __iter__(self):
        self._log.add((self._tag, "*"))
        return super().__iter__()

    def items(self):
        self._log.add((self._tag, "*"))
        return super().items()

    def values(self):
        self._log.add((self._tag, "*"))
        return super().values()

    def __deepcopy__(self, memo):
        return {kk: copy.deepcopy(v, memo) for kk, v in dict.items(self)}


class _LoggedList(list):
    """A list that logs any read of it."""

    def __init__(self, items, log, tag):
        super().__init__(items)
        self._log, self._tag = log, tag

    def _hit(self):
        self._log.add((self._tag, "*"))

    def __getitem__(self, i):
        self._hit()
        return super().__getitem__(i)

    def __iter__(self):
        self._hit()
        return super().__iter__()

    def __len__(self):
        self._hit()
        return super().__len__()

    def __contains__(self, x):
        self._hit()
        return super().__contains__(x)

    def __deepcopy__(self, memo):
        return [copy.deepcopy(v, memo) for v in list.__iter__(self)]


def recording(rec, log):
    """The record as the view sees it, logging every coverage-bearing touch."""
    r = dict(rec)
    r["omit"] = _Logged(rec["omit"], log, "omit")
    hd = []
    for e in rec["hd"]:
        e = list(e)
        e[SL] = _LoggedList(e[SL], log, "sl")
        e[SP] = _LoggedList(e[SP], log, "sp")
        hd.append(e)
    r["hd"] = hd
    return _Logged(r, log, "rec")


def touched_facts(log):
    """The coverage facts a touch log names."""
    out = set()
    for tag, key in log:
        if tag in ("sl", "sp"):
            out.add(tag)
        elif tag == "omit" and key in FACTS:
            out.add(key)
        elif tag == "rec":
            if key in LIST_FACTS:
                out.add(key)
            elif key == "po":
                out.add("first")
            elif key == "inc":
                out |= {"whole", "first"}
            elif key == "prof":
                out.add("whole")
            elif key == "omit":
                pass
            elif key == "*":
                out |= set(LIST_FACTS) | {"whole", "first"}
    return out


# -- 2. perturbations -----------------------------------------------------------------

ENDS = ("first", "last", "all")          # trimmed at the first entry, at the last, emptied


def _trim(lst, end):
    if not lst:
        return None
    if end == "all":
        return []
    return lst[1:] if end == "first" else lst[:-1]


def perturbations(rec):
    """(fact, label, the record changed, the hand changed or None) for every
    way each fact's data can change; a change that does not apply to this
    record is left out. A slot or spawn list is changed ONE HAND AND ONE
    ENTRY AT A TIME (each entry removed alone, then the list emptied), so two
    hands changed alike can never cancel in a measure that compares them;
    the hand changed is named by its (phase, deal)."""
    out = []

    def add(fact, label, edit, where=None):
        r = copy.deepcopy(rec)
        if edit(r) is not False:
            out.append((fact, label, r, where))

    add("whole", "lost bit", lambda r: r.__setitem__("inc", r["inc"] | cm.INC["lost"]))
    add("whole", "fault bit", lambda r: r.__setitem__("inc", r["inc"] | cm.INC["fault"]))

    def sem(r):
        prof = list(r["prof"])
        prof[SEM] = "not-a-semantics-word"
        r["prof"] = prof
    add("whole", "semantics word", sem)
    add("first", "first bit", lambda r: r.__setitem__("inc", r["inc"] | cm.INC["first"]))

    def po_rev(r):
        if len(r["po"]) < 2:
            return False
        r["po"] = list(reversed(r["po"]))
    add("first", "order reversed", po_rev)
    for fact in ("cards", "ph", "hd", "ap"):
        for end in ENDS:
            def lst(r, fact=fact, end=end):
                t = _trim(r[fact], end)
                if t is None:
                    return False
                r[fact] = t
            add(fact, "trimmed at the %s entry" % end, lst)
    for role in range(cm.WIDTH["roles"]):
        for end in ENDS:
            def held(r, role=role, end=end):
                h = r["held0"][role]
                t = _trim(h, end) if h is not None else None
                if t is None:
                    return False
                r["held0"][role] = t
            add("held0", "role %d trimmed at the %s entry" % (role, end), held)

        def held_none(r, role=role):
            if r["held0"][role] is None:
                return False
            r["held0"][role] = None
        add("held0", "role %d absent" % role, held_none)
    for fact, pos in (("sl", SL), ("sp", SP)):
        for h, e0 in enumerate(rec["hd"]):
            where = (e0[0], e0[1])
            for j in range(len(e0[pos])):
                def one(r, h=h, pos=pos, j=j):
                    lst = list(r["hd"][h][pos])
                    del lst[j]
                    r["hd"][h][pos] = lst
                add(fact, "hand %d entry %d removed" % (h, j), one, where)
            if e0[pos]:
                def empty(r, h=h, pos=pos):
                    r["hd"][h][pos] = []
                add(fact, "hand %d emptied" % h, empty, where)
    for fact in cm.W["omit_keys"]:
        def stated(r, fact=fact):
            r["omit"][fact] = [1, 1] if isinstance(r["omit"][fact], list) else 1
        add(fact, "omission stated", stated)
    return out


# -- 3. the ungated run ----------------------------------------------------------------

class Ungated:
    """The measures with the gate taken out (the static method's three
    exclusions): restored on exit."""

    def __enter__(self):
        self.saved = (cm._gate, cm.covered, cm.RecFacts.__init__)
        init = cm.RecFacts.__init__

        def whole(self_, *a, **kw):
            init(self_, *a, **kw)
            self_.ok = {key: True for key in self_.ok}
        cm._gate = lambda row, ok: None
        cm.covered = lambda ok, needs: True
        cm.RecFacts.__init__ = whole
        return self

    def __exit__(self, *exc):
        cm._gate, cm.covered, cm.RecFacts.__init__ = self.saved
        return False


def _occ(keys):
    seen, out = {}, []
    for key in keys:
        seen[key] = seen.get(key, 0) + 1
        out.append(key + (seen[key],))
    return out


def rows(v):
    """Every measure row of a view and its windows, keyed by identity."""
    out = {}
    hk = _occ([("hand", m["recorder"], m["o"], m["k"], m["w"]) for _r, m in v["hands"]])
    out.update(zip(hk, [r for r, _m in v["hands"]]))
    pk = _occ([("phase", m["recorder"], m["o"], m["w"]) for _r, m in v["phases"]])
    out.update(zip(pk, [r for r, _m in v["phases"]]))
    for r, m in v["records"]:
        out[("record", m["recorder"])] = r
    qk = _occ([("pair", m["dealer"], m["o"], m["k"]) for _r, m in v["pairs"]])
    out.update(zip(qk, [r for r, _m in v["pairs"]]))
    out[("game",)] = v["game"]
    for c in cm.contributions(v):
        agg = dict(c, games=1)
        out[("window", c["recorder"], c["subject"], c["source"], c["coverage"], c["profile"])] = \
            cm.window_row(agg)
    return out


def _view(records, reg, sc, weights, report):
    return k.view(records, reg, sc, weights, report)


# -- 4. the fixtures -------------------------------------------------------------------

def _picked(rec, role):
    names = {c[0]: c[1] for c in rec["cards"]}
    return [names[e[6][e[9]]] for e in rec["hd"] if e[2] == role and e[9] >= 0]


def _fixture(name):
    c = k.fixture_census(name)
    return k.on_census(k.fixture_record(name), c), c


def fixtures():
    """(name, records, registry, Same Cards, weights, report)."""
    out = []
    rec = k.default_record()
    other = k.mirror(rec)
    full_c = k.fixture_census("full_game")
    report = {"a": _picked(rec, 0), "b": _picked(rec, 1)}
    out.append(("full paired, off, report", [("a", "b", rec), ("b", "a", other)], [full_c], "off",
                k.WEIGHTS, report))
    g2, g2c = _fixture("game2_held_samecards")
    for sc in ("on", "off", None):
        out.append(("game two paired, Same Cards %s" % sc, [("a", "b", g2), ("b", "a", copy.deepcopy(g2))],
                    [g2c], sc, k.WEIGHTS, None))
    for name in ("full_game", "cut_left", "first_phase_lost", "over_cap", "game2_held_samecards"):
        r, c = _fixture(name)
        out.append(("%s alone" % name, [("a", "b", r)], [c], "off", k.WEIGHTS, {"a": [], "b": []}))
    out.append(("full alone, no weights", [("a", "b", rec)], [full_c], "off", None, report))
    out.append(("full alone, no census", [("a", "b", rec)], [], "off", k.WEIGHTS, report))
    out.append(("full alone, no report", [("a", "b", rec)], [full_c], None, k.WEIGHTS, None))
    lossy = copy.deepcopy(rec)
    lossy["inc"] |= cm.INC["lost"]
    out.append(("full paired, loss bit", [("a", "b", lossy), ("b", "a", other)], [full_c], "off",
                k.WEIGHTS, report))
    return out


# -- the method ------------------------------------------------------------------------

def _differs(a, b):
    return type(a) is not type(b) or a != b


class Result:
    """What the dynamic method saw: DYN per measure (a value moved on a row
    present in both runs); per measure the facts whose change only added or
    removed rows carrying it; the measures that held a value (not None) on
    some base row; the facts the recording view saw touched; the
    perturbations that raised; the runs made."""

    def __init__(self):
        names = [n for ns in cm.MEASURES.values() for n in ns]
        self.dyn = {n: set() for n in names}
        self.rowset = {n: set() for n in names}
        self.valued = set()
        self.touched, self.raised, self.runs = set(), [], 0
        # one-hand perturbations: (fixture, record, label) -> the row keys whose
        # values moved, and the rows each may move (_reach)
        self.moved, self.outside = {}, []


def _reach(key, where):
    """Whether a one-hand change at `where` (phase, deal) may move row `key`:
    that deal's hand rows in either record, its pair row, every record row,
    the game row and every window."""
    kind = key[0]
    if kind == "hand":
        return (key[2], key[3]) == where
    if kind == "pair":
        return (key[2], key[3]) == where
    return kind in ("record", "game", "window")


def dynamic_reads(fx=None):
    res = Result()
    with Ungated():
        for fname, records, reg, sc, weights, report in (fx if fx is not None else fixtures()):
            log = set()
            base_recs = [(s, o, recording(r, log)) for s, o, r in records]
            base = rows(_view(base_recs, reg, sc, weights, report))
            res.runs += 1
            res.touched |= touched_facts(log)
            for row in base.values():
                res.valued |= {n for n, v in row.items() if v is not None}
            for i, (s, o, r) in enumerate(records):
                for fact, label, changed, where in perturbations(r):
                    recs = list(records)
                    recs[i] = (s, o, changed)
                    try:
                        got = rows(_view(recs, reg, sc, weights, report))
                    except Exception as exc:            # listed, never counted as a read
                        res.raised.append((fname, i, fact, label, type(exc).__name__))
                        continue
                    res.runs += 1
                    moved = set()
                    for key in base.keys() & got.keys():
                        a, b = base[key], got[key]
                        for name in a:
                            if name in b and _differs(a[name], b[name]):
                                res.dyn[name].add(fact)
                                moved.add(key)
                    if where is not None:
                        res.moved[(fname, i, label, fact)] = moved
                        res.outside += [(fname, i, label, key) for key in sorted(moved, key=str)
                                        if not _reach(key, where)]
                    for key in base.keys() ^ got.keys():
                        for name in (base.get(key) or got.get(key)):
                            res.rowset[name].add(fact)
    return res


# -- branch coverage -------------------------------------------------------------------

TOOL = 4


def _codes(co):
    yield co
    for c in co.co_consts:
        if isinstance(c, types.CodeType):
            yield from _codes(c)


def module_functions():
    """Every function and method card_measures defines, with whether it lies
    in the view section (from RecFacts to the end of window_row)."""
    lo = inspect.getsourcelines(cm.RecFacts)[1]
    src, start = inspect.getsourcelines(cm.window_row)
    hi = start + len(src)
    out = []
    for name, obj in vars(cm).items():
        if inspect.isfunction(obj) and obj.__module__ == cm.__name__:
            out.append((name, obj.__code__))
        elif inspect.isclass(obj) and obj.__module__ == cm.__name__:
            for mname, m in vars(obj).items():
                if inspect.isfunction(m):
                    out.append(("%s.%s" % (name, mname), m.__code__))
    return [(n, co, lo <= co.co_firstlineno < hi) for n, co in out]


def _branch_sites(co):
    """(offset, line, arm names, the next instruction's offset, the
    instruction) of every conditional jump and loop test in one code object.
    The arms: for a loop test 'body' (the next item, the fall-through) and
    'exit'; for a jump 'fall' (the condition did not jump) and 'jump'."""
    out = []
    ins = list(dis.get_instructions(co))
    for i, x in enumerate(ins):
        if x.opname.startswith("POP_JUMP_IF") or x.opname == "FOR_ITER":
            nxt = ins[i + 1].offset if i + 1 < len(ins) else None
            arms = ("body", "exit") if x.opname == "FOR_ITER" else ("fall", "jump")
            out.append((x.offset, x.positions.lineno if x.positions else None, arms, nxt, x))
    return out


def _numbered(codes, measured):
    """Every site of the measured functions with its identity (function,
    line, n): n numbers the sites of one line of one function in code
    order."""
    nth = {}
    for c, fname in sorted(codes.items(), key=lambda kv: (kv[1], kv[0].co_firstlineno, kv[0].co_name)):
        if fname not in measured:
            continue
        for offset, line, arms, nxt, ins in _branch_sites(c):
            n = nth[(fname, line)] = nth.get((fname, line), 0) + 1
            yield fname, line, n, c, offset, arms, nxt, ins


# What each arm of a jump means, by the jump's kind: (fall, jump).
_MEANS = {"POP_JUMP_IF_FALSE": ("true", "false"), "POP_JUMP_IF_TRUE": ("false", "true"),
          "POP_JUMP_IF_NONE": ("not None", "None"), "POP_JUMP_IF_NOT_NONE": ("None", "not None")}


def describe(unexercised):
    """For each unexercised arm (branch_coverage's identities): (function,
    line, n, arm, what never happened, the source the site tests)."""
    lines = inspect.getsource(cm).splitlines()
    codes = {}
    for fname, co, _in_view in module_functions():
        for c in _codes(co):
            codes[c] = fname
    want = {(f, ln, n): arm for f, ln, n, arm in unexercised}
    out = []
    for fname, line, n, _c, _off, arms, _nxt, ins in _numbered(codes, {f for f, _l, _n in want}):
        if (fname, line, n) not in want:
            continue
        arm = want[(fname, line, n)]
        p = ins.positions
        if p and p.lineno == p.end_lineno:
            src = lines[p.lineno - 1][p.col_offset:p.end_col_offset]
        elif p:
            src = " ".join(x.strip() for x in lines[p.lineno - 1:p.end_lineno])
        else:
            src = ""
        if ins.opname == "FOR_ITER":
            never = {"body": "a turn of the loop", "exit": "the loop ran out",
                     "both": "the loop was reached"}[arm]
        else:
            fall, jump = _MEANS.get(ins.opname, ("fall", "jump"))
            never = {"fall": "tested " + fall, "jump": "tested " + jump, "both": "the test was reached"}[arm]
        out.append((fname, line, n, arm, ins.opname, never, src))
    return out


def branch_coverage(run):
    """Run `run()` with branch and call events on every function of
    card_measures; the measure functions are the view section and every
    function the run called. Return (functions, arms taken, arms total,
    unexercised [(function, line, n, the arm that never ran)]): n numbers the
    sites of one line of one function in code order, the arm is one of
    _branch_sites' names, or 'both'."""
    mon = sys.monitoring
    seen, called = {}, set()
    codes, section = {}, set()
    for fname, co, in_view in module_functions():
        if in_view:
            section.add(fname)
        for c in _codes(co):
            codes[c] = fname

    def on_branch(code, offset, dest):
        if code in codes:
            seen.setdefault((code, offset), set()).add(dest)

    def on_start(code, offset):
        if code in codes:
            called.add(codes[code])

    mon.use_tool_id(TOOL, "card-branch")
    try:
        mon.register_callback(TOOL, mon.events.BRANCH, on_branch)
        mon.register_callback(TOOL, mon.events.PY_START, on_start)
        for c in codes:
            mon.set_local_events(TOOL, c, mon.events.BRANCH | mon.events.PY_START)
        run()
    finally:
        for c in codes:
            mon.set_local_events(TOOL, c, 0)
        mon.register_callback(TOOL, mon.events.BRANCH, None)
        mon.register_callback(TOOL, mon.events.PY_START, None)
        mon.free_tool_id(TOOL)
    measured = section | called
    total = taken = 0
    unexercised = []
    for fname, line, n, c, offset, arms, nxt, _ins in _numbered(codes, measured):
        dests = seen.get((c, offset), set())
        got = len(dests)
        total += 2
        taken += min(got, 2)
        if got == 0:
            unexercised.append((fname, line, n, "both"))
        elif got == 1:
            unexercised.append((fname, line, n, arms[1] if nxt in dests else arms[0]))
    return len(measured), taken, total, sorted(unexercised, key=str)


def measured():
    """The dynamic method with its branch coverage: (Result, functions, arms
    taken, arms total, unexercised). The fixtures are built before the
    branch events start, so the coverage is of the measure run alone."""
    fx = fixtures()
    out = {}
    fns, taken, total, missing = branch_coverage(lambda: out.setdefault("r", dynamic_reads(fx)))
    return out["r"], fns, taken, total, missing


if __name__ == "__main__":
    res, fns, taken, total, missing = measured()
    print("dynamic: %d runs, facts touched %s, perturbations raised %d"
          % (res.runs, sorted(res.touched), len(res.raised)))
    print("dynamic pairs %d over %d measures" % (sum(len(v) for v in res.dyn.values()), len(res.dyn)))
    print("branch arms %d of %d in %d functions; unexercised %d" % (taken, total, fns, len(missing)))
    for fname, line, n, arm in missing:
        print("  unexercised: %s line %s site %d, the %s arm" % (fname, line, n, arm))
