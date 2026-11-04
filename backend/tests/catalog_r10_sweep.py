"""The round-10 sweep by class (ruling REHEARSAL-R9-A1 (E)) over the four
files of the catalog lane: every line of each class, counted per file. The
counts are frozen in FROZEN; test_r7_catalog_diff_pg.py
test_r10_sweep_counts asserts them, so a new site of a class fails until
it is fixed or held with a reason (the round-10 notes list every site and
its disposition, and the sweep log names each line).

  presence     a check that SOME transaction is open (round 9's form; the
               harnesses now bind each position to its transaction:
               catalog_position)
  explanation  a place where a raw row is accounted for by an object change
               (catalog_all.unexplained: bound to identity and changed
               columns since round 10)
  shared       a filter on a shared catalog (RESTRICT and its complement,
               outside(); the role settings of every database)
"""

import os
import re

FILES = ("catalog_all.py", "catalog_diff.py", "test_r7_catalog_diff_pg.py", "test_r7_ro_role_pg.py")

CLASSES = {
    "presence": re.compile(r"\bis_in_transaction\(|\bin_transaction\(|_harness_open\(|still_open"),
    "explanation": re.compile(r"\bok = (bool|any|verdict|\(key)|return bool\(ids & |names <= renamed"
                              r"|EXPLAINS\.get\(|IN_PLACE\.get\("),
    "shared": re.compile(r"\{me\}|\{db\}|setdatabase|subdbid|IS NOT TRUE|outside=True"),
}

# (class, file): number of lines, at the round-10 tip
FROZEN = {
    ("presence", "catalog_all.py"): 0, ("presence", "catalog_diff.py"): 1,
    ("presence", "test_r7_catalog_diff_pg.py"): 1, ("presence", "test_r7_ro_role_pg.py"): 1,
    ("explanation", "catalog_all.py"): 10, ("explanation", "catalog_diff.py"): 0,
    ("explanation", "test_r7_catalog_diff_pg.py"): 0, ("explanation", "test_r7_ro_role_pg.py"): 0,
    ("shared", "catalog_all.py"): 17, ("shared", "catalog_diff.py"): 1,
    ("shared", "test_r7_catalog_diff_pg.py"): 8, ("shared", "test_r7_ro_role_pg.py"): 2,
}


def sweep(root):
    """{(class, file): [(line number, text)]} over FILES under root."""
    out = {}
    for f in FILES:
        with open(os.path.join(root, f), encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        for name, rx in CLASSES.items():
            out[(name, f)] = [(i + 1, t.strip()) for i, t in enumerate(lines) if rx.search(t)]
    return out
