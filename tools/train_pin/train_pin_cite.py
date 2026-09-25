"""R8-L3: check every citation a review pin's notes make, against the pin itself.

A citation is a claim that a line of a pinned file says something. The notes of
earlier rounds cited `file:line` and nothing checked either half, so a line
number drifted with an edit and the prose went on asserting what the line no
longer said. This checker makes each citation carry its evidence and then
looks for that evidence where the citation says it is.

THE TWO FORMS A CITATION MAY TAKE
---------------------------------
1.  A line of a pinned file, with the text that line carries:

        `FILE:LINE` `TEXT`          or        `FILE:FIRST-LAST` `TEXT`

    FILE is a file of the pin (a bare name, no directory), LINE counts from 1,
    and TEXT -- a code span directly after the citation -- must occur verbatim
    on that line, or on one line of the range.

2.  A field of one of the pin's schema-rendered summaries, with its value:

        `summary-ARTIFACT.json#PATH` `VALUE`

    PATH is a key of the document, or SECTION[SELECT].KEY for a row, where
    SELECT is a row index or one or more FIELD=WORD pairs joined by commas
    (the ONE row whose fields all hold those words; none or two is a
    failure). A dot inside the brackets is part of the word, so a test's
    node id selects its row. VALUE must equal the field's value (an
    integer is compared as its digits).

Anything in the notes that LOOKS like the first form -- a name with an
extension, a colon and a number -- and is not followed by its TEXT is a BARE
citation, and a bare citation is a failure: a citation nothing checks is the
defect this file exists to remove. A citation of a file the pin does not
carry is a failure too.

USAGE
-----
    python train_pin_cite.py <pin> <notes-file-in-pin> [--write]
    python train_pin_cite.py --self-test

`--write` writes `notes-citation-check.log` into the pin. Exit 0 only when
every citation was found and none is bare; 1 otherwise; 2 on a usage error.
The self-test plants each kind of failure beside a correct citation of each
form and requires every planted failure to be caught and every correct
citation to pass.
"""
import io
import json
import os
import re
import shutil
import sys
import tempfile

NL = chr(10)

LINE_CITE = re.compile(r"`([A-Za-z0-9_.-]+[.][A-Za-z0-9]+):([0-9]+)(?:-([0-9]+))?`"
                       r"(?:[ ]+`([^`]+)`)?")
FIELD_CITE = re.compile(r"`(summary-[a-z]+[.]json)#([^`]+)`(?:[ ]+`([^`]*)`)?")
# Anything shaped like a line citation, backticked or not. Every one of these
# must be the start of a checked LINE_CITE.
LOOKS_LIKE = re.compile(r"([A-Za-z0-9_-]+(?:[.][A-Za-z0-9_-]+)*[.][A-Za-z0-9]+):([0-9]+)")
STEP = re.compile(r"\A([A-Za-z0-9_]+)(?:\[(.+)\])?\Z")


def _steps(path):
    """PATH split on the dots that are outside brackets."""
    out, depth, cur = [], 0, ""
    for ch in path:
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        if ch == "." and depth == 0:
            out.append(cur)
            cur = ""
            continue
        cur += ch
    out.append(cur)
    return out


def _lines(path):
    return io.open(path, encoding="utf-8", errors="replace").read().split(NL)


def _field(doc, path):
    """The value at PATH in a summary document, or raise KeyError with why."""
    here = doc
    for part in _steps(path):
        m = STEP.match(part)
        if not m:
            raise KeyError("the path step %r is not KEY or KEY[SELECT]" % part)
        key, select = m.group(1), m.group(2)
        if not isinstance(here, dict) or key not in here:
            raise KeyError("no key %r" % key)
        here = here[key]
        if select is None:
            continue
        if not isinstance(here, list):
            raise KeyError("%r is not a section of rows" % key)
        if select.isdigit():
            if int(select) >= len(here):
                raise KeyError("%r has %d row(s)" % (key, len(here)))
            here = here[int(select)]
            continue
        pairs = [p.split("=", 1) for p in select.split(",")]
        if any(len(p) != 2 or not p[0] for p in pairs):
            raise KeyError("the selector %r is not an index or FIELD=WORD pairs" % select)
        rows = [r for r in here if isinstance(r, dict)
                and all(str(r.get(f)) == w for f, w in pairs)]
        if len(rows) != 1:
            raise KeyError("%d row(s) of %r match %s, not one" % (len(rows), key, select))
        here = rows[0]
    return here


def check(pin, notes):
    """(lines of the log, failures) for every citation in `notes` against `pin`."""
    text = io.open(notes, encoding="utf-8").read()
    files = set(os.listdir(pin))
    out, failures = [], 0
    complete = []  # the spans of citations that carry their text
    line_n = field_n = 0
    for m in LINE_CITE.finditer(text):
        name, first, last, want = m.group(1), int(m.group(2)), m.group(3), m.group(4)
        if want is not None:
            complete.append((m.start(), m.end()))
        last = int(last) if last else first
        where = "%s:%d%s" % (name, first, ("-%d" % last) if last != first else "")
        line_n += 1
        if want is None:
            continue  # counted as BARE below, with every other unchecked shape
        if name not in files:
            out.append("MISSING   %-40s the pin carries no file of that name" % where)
            failures += 1
            continue
        lines = _lines(os.path.join(pin, name))
        if first < 1 or last < first or last > len(lines):
            out.append("NO LINE   %-40s the file has %d line(s)" % (where, len(lines)))
            failures += 1
            continue
        if any(want in lines[i - 1] for i in range(first, last + 1)):
            out.append("FOUND     %-40s `%s`" % (where, want))
        else:
            out.append("NOT FOUND %-40s `%s` is not on the cited line(s)" % (where, want))
            failures += 1
    for m in LOOKS_LIKE.finditer(text):
        if any(a <= m.start() < b for a, b in complete):
            continue
        out.append("BARE      %-40s a citation with no text beside it, which nothing can check"
                   % m.group(0))
        failures += 1
    for m in FIELD_CITE.finditer(text):
        name, path, want = m.group(1), m.group(2), m.group(3)
        where = "%s#%s" % (name, path)
        field_n += 1
        if want is None:
            out.append("BARE      %-40s a field citation with no value beside it" % where)
            failures += 1
            continue
        if name not in files:
            out.append("MISSING   %-40s the pin carries no document of that name" % where)
            failures += 1
            continue
        try:
            got = _field(json.loads(io.open(os.path.join(pin, name), encoding="utf-8").read()),
                         path)
        except (KeyError, ValueError) as e:
            out.append("NO FIELD  %-40s %s" % (where, e))
            failures += 1
            continue
        if isinstance(got, (dict, list)):
            out.append("NOT FOUND %-40s the path names a %s, not a value"
                       % (where, type(got).__name__))
            failures += 1
        elif str(got) == want:
            out.append("FOUND     %-40s `%s`" % (where, want))
        else:
            out.append("NOT FOUND %-40s the document says `%s`, the notes say `%s`"
                       % (where, got, want))
            failures += 1
    head = ["# NOTES CITATION CHECK (R8-L3). Every `FILE:LINE` citation in the notes",
            "# must carry the text that line says, and every summary-field citation the",
            "# value the document holds; both are looked up in THIS pin. A citation",
            "# with nothing beside it is BARE and fails.",
            "",
            "notes: %s" % os.path.basename(notes),
            "line citations: %d   field citations: %d" % (line_n, field_n),
            ""]
    tail = ["", "CITATIONS FAILED: %d" % failures]
    return head + out + tail, failures


def self_test():
    """Each kind of failure planted beside a correct citation of each form."""
    tmp = tempfile.mkdtemp(prefix="cite-self-test-")
    try:
        io.open(os.path.join(tmp, "code.py"), "w", encoding="utf-8").write(
            NL.join(["def f():", "    return 1", "", "x = f()"]) + NL)
        io.open(os.path.join(tmp, "summary-check.json"), "w", encoding="utf-8").write(
            json.dumps({"outcome": "COMPLETED", "count": 3,
                        "boxes": [{"box": "PRIMARY", "build": "NEW"},
                                  {"box": "STANDBY", "build": "NEW"}],
                        "tests": [{"node": "backend/tests/test_x.py::test_a",
                                   "outcome": "PASSED"}],
                        "controls": [{"id": "R9_D4", "kind": "MUTANT", "observed": "RED"},
                                     {"id": "R9_D4", "kind": "TWIN",
                                      "observed": "GREEN"}]}))
        cases = (
            ("correct line", "`code.py:2` `return 1`", 0),
            ("correct range", "`code.py:1-4` `x = f()`", 0),
            ("correct field", "`summary-check.json#outcome` `COMPLETED`", 0),
            ("correct row field", "`summary-check.json#boxes[box=STANDBY].build` `NEW`", 0),
            ("correct integer", "`summary-check.json#count` `3`", 0),
            ("correct node row",
             "`summary-check.json#tests[node=backend/tests/test_x.py::test_a].outcome` "
             "`PASSED`", 0),
            ("correct pair row",
             "`summary-check.json#controls[id=R9_D4,kind=TWIN].observed` `GREEN`", 0),
            ("citation inside text", "`code.py:4` `x = f()` names code.py:4 again", 1),
            ("quoted shape inside a checked text",
             "`code.py:2` `return 1` then `code.py:4` `x = f()`", 0),
            ("wrong line", "`code.py:1` `return 1`", 1),
            ("line out of range", "`code.py:9` `return 1`", 1),
            ("bare backticked", "`code.py:2` and then prose", 1),
            ("bare plain", "see code.py:2 for it", 1),
            ("missing file", "`other.py:2` `return 1`", 1),
            ("wrong field value", "`summary-check.json#outcome` `REFUSED`", 1),
            ("absent field", "`summary-check.json#nothing` `NEW`", 1),
            ("ambiguous row", "`summary-check.json#boxes[build=NEW].box` `PRIMARY`", 1),
            ("ambiguous pair row",
             "`summary-check.json#controls[id=R9_D4].observed` `RED`", 1),
            ("wrong pair row",
             "`summary-check.json#controls[id=R9_D4,kind=MUTANT].observed` `GREEN`", 1),
            ("bare field", "`summary-check.json#outcome` and then prose", 1),
        )
        bad = 0
        for name, line, want in cases:
            notes = os.path.join(tmp, "notes.md")
            io.open(notes, "w", encoding="utf-8").write(line + NL)
            _out, failures = check(tmp, notes)
            got = 1 if failures else 0
            verdict = "ok" if got == want else "WRONG"
            bad += verdict != "ok"
            print("%-20s want %-5s got %-5s %s" % (name, "RED" if want else "GREEN",
                                                   "RED" if got else "GREEN", verdict))
        print("self-test: %d case(s), %d wrong" % (len(cases), bad))
        return 1 if bad else 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    argv = sys.argv[1:]
    if argv == ["--self-test"]:
        return self_test()
    if len(argv) not in (2, 3) or (len(argv) == 3 and argv[2] != "--write"):
        print(__doc__)
        return 2
    pin, notes = argv[0], os.path.join(argv[0], argv[1])
    lines, failures = check(pin, notes)
    text = NL.join(lines) + NL
    if len(argv) == 3:
        io.open(os.path.join(pin, "notes-citation-check.log"), "w", encoding="utf-8",
                newline="").write(text)
    sys.stdout.write(text)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
