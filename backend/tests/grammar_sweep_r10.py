"""The (E) sweep of round 10 child gr (ruling REHEARSAL-R9-A1): the three
operations of the class "a check bound to presence where it must be bound
to identity", grepped over the files the child owns, with every hit's
disposition in RF/r10/gr/NOTES-r10-gr.md and the frozen counts here; the
a1 test asserts the counts, so a new site of any operation fails it until
it is listed and judged.

Operations (a regular expression each, read line by line, comment-only
lines skipped):
  receiver  a receiver trusted by a test: the census's frozen receivers and
            their checks, the receiver-class identity, the session-root
            predicates of the shared visitor;
  compare   a comparison-shape admission or an exemption keyed on a
            constant: every reading of a Compare node, every `.value is
            None` test of a constant, the TEXT exemption, the census's
            pinned exemptions;
  byname    a callee accepted by NAME: every call of a resolver method that
            answers by spelling, the frozen callee table, the pure tables,
            and the gate's named sets.
"""
import re

FILES = ("resolution_sites.py", "closed_walk.py", "shape_grammar.py",
         "grammar_shapes_gate.py", "grammar_providers.py",
         "test_a1_identity_formation.py", "test_match_hold_admission_gate_pg.py")
OPS = {
    "receiver": re.compile(
        r"_RECEIVER\[|RESOLVER_RECEIVERS\[|\.attr == \"b\"|func\.id == cls"
        r"|def (is_root|session_root_ok|is_session|session_value)\b"
        r"|_resolver_construction\(|_top_binder\(tree, cls\)"),
    "compare": re.compile(
        r"\b_?ast\.Compare\b|\.value is None\b|_plain_text\(|_CENSUS_EXEMPT\b"),
    "byname": re.compile(
        r"\.(listed|named|spelled|spelled_any|spelled_once|spelled_in"
        r"|namedtuple_class|callee|opaque_callee|_module_object)\("
        r"|_frozen_callee\(|\bpure_(calls|awaits)\b|_REFUSAL_EXCEPTIONS"
        r"|_HOLD_REPLAYS"),
}
# The counts at the round-10 tip, (operation, file): hits.
COUNTS = {
    ("byname", "closed_walk.py"): 23,
    ("byname", "resolution_sites.py"): 3,
    ("byname", "test_a1_identity_formation.py"): 38,
    ("byname", "test_match_hold_admission_gate_pg.py"): 23,
    ("compare", "closed_walk.py"): 1,
    ("compare", "resolution_sites.py"): 8,
    ("compare", "test_a1_identity_formation.py"): 5,
    ("compare", "test_match_hold_admission_gate_pg.py"): 3,
    ("receiver", "closed_walk.py"): 5,
    ("receiver", "resolution_sites.py"): 14,
}


def sweep(root):
    """([(operation, file, line, text)], {(operation, file): hits}) over
    FILES under directory `root` (backend/tests)."""
    hits, counts = [], {}
    for f in FILES:
        with open(f"{root}/{f}", encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        for i, line in enumerate(lines, 1):
            if line.lstrip().startswith("#"):
                continue
            for op, rx in OPS.items():
                k = len(rx.findall(line))
                if k:
                    counts[(op, f)] = counts.get((op, f), 0) + k
                    hits.append((op, f, i, line.strip()))
    return hits, counts
