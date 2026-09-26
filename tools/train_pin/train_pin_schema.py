"""R9 method change: validate every review summary in a pin against the schema that makes it safe.

WHY THIS FILE EXISTS
--------------------
Rounds 4 to 8 shipped a review bundle whose privacy rested on REMOVING things
from free text: a redaction door in the tool, and a census scanner over the
finished bundle. Both are deny-lists over an open set. Each round closed the
paths it had found and the round after found a sibling of one of them.

So the artifact changed. The pin carries no transcript of a live run. It
carries one document per artifact, against a FIXED schema that has no FREE
string type. That is a bound, not a proof (round 9, H3): an integer, a pytest
node name and a 40-hex value are still rendered text, and a sensitive value can
be spelled in any of them. Since round 10 every rendered field of every summary
is needle-scanned before it enters a pin (`train_pin_needles.field_findings`,
called by `assemble_pin.py`, which refuses to write the document on one finding);
the no-free-string rule below is defence in depth.

That claim is worth exactly as much as the check behind it, and a document
checked only by the program that wrote it is checked by nothing. The train
refuses to RENDER a document its own schema forbids; this file asks the same
question again, of the files that actually arrived in the pin, from its OWN
copy of every table below -- not an import of the train's. The round's harness
compares the two copies and records the verdict in the MUTATIONS document
(`schema_agreement`), and compares this file's synthetic vocabulary with the
one the tests module exports (`vocabulary_agreement`).

WHAT THE SCHEMA IS
------------------
* Six artifacts. PLAN, CHECK, VERIFY and SNAPSHOT are rendered by the train's
  `review-summary`; TESTS and MUTATIONS by the round's harness, from the same
  tree.
* An ENUMERATED key set per artifact: a document carries exactly its
  artifact's keys. An unknown key is refused whatever its form and whatever its
  value; a missing key is refused by name. A key the run never reached is
  present and reads UNRECORDED.
* Every key has a TYPE, and every type is closed:
    WORD       a member of the closed vocabulary below -- NOT "an upper-case
               word": an upper-cased machine or group name has the shape of a
               word and is refused because it is not one of these
    INT        an integer (`true` and `false` are not integers here)
    SHA40      a 40-hex object id            SHA7   a 7-hex object id
    UTC        YYYY-MM-DDTHH:MM:SS+00:00
    DECLARED   one of the four sanctioned identifiers, spelled exactly
    NODE       backend/tests/test_<name>.py::test_<name>       (TESTS only)
    CONTROL    R<round>_<finding>, e.g. R8_A1A                 (MUTATIONS only)
    EXCEPTION  one of a closed list of exception TYPE names    (MUTATIONS only)
    TOKEN      one token of a control's message: a member of the synthetic
               vocabulary, a vocabulary word, an integer or a sanctioned
               identifier                                      (MUTATIONS only)
    {a, b}     a per-key enumeration
* A row section is a list of objects whose keys are exactly the section's.
* And, said by name although no type admits one: any hex run of 32 or more
  characters that is not a value typed SHA40 in the same document is refused.
  A machine fingerprint is a persistent machine identifier.

    python train_pin_schema.py <pin-dir>            # the six summary-*.json in it
    python train_pin_schema.py <file.json> [...]    # named documents
    python train_pin_schema.py --self-test          # the controls, with exit codes

Exit 0 when every document validates, 1 when any does not, 2 on a usage error.
"""
import io
import json
import os
import re
import sys

SCHEMA = "SCR_TRAIN_REVIEW_SUMMARY"
VERSION = 1
UNRECORDED = "UNRECORDED"
TRAIN_ARTIFACTS = ("PLAN", "CHECK", "VERIFY", "SNAPSHOT")
HARNESS_ARTIFACTS = ("TESTS", "MUTATIONS")
ARTIFACTS = TRAIN_ARTIFACTS + HARNESS_ARTIFACTS
# The file each artifact travels in, inside a pin.
PIN_FILES = {a: "summary-%s.json" % a.lower() for a in ARTIFACTS}

SANCTIONED = (
    "competitive-rounds.duckdns.org",   # the public service hostname
    "192.168.72.199",                   # the primary backend
    "192.168.72.90",                    # the standby, which serves the routed reads
    "192.168.72.102",                   # the edge
)

# ---------------------------------------------------------------------------
# The closed vocabulary. A copy of the train's fixed words, its phases and its
# batches, plus the words the harness documents use. Closed: a word not in it
# is refused whatever its shape.
FIXED_WORDS = frozenset((
    "ABSENT", "ANSWERED", "BOX", "CHECK", "COMPLETED", "DISTINCT", "DROPPED", "EDGE",
    "GATE", "HOSTNAME", "MATCH", "MISMATCH", "MISSING", "NEW", "NO", "NONE",
    "NOT_SELECTED", "NO_MIGRATION", "OLD", "ONE_PROCESS", "OTHER", "PLAN", "PLANNED",
    "PRESENT", "PRIMARY", "PROVENANCE", "RAN", "RECORDED", "REFUSED", "SECTION",
    "SKIPPED", "SNAPSHOT", "STANDBY", "UNKNOWN", "UNRECORDED", "VERIFY", "YES",
    # R9-M3: an attempt that did not reach its end; R9-L5: a success word no GO run earned
    "ATTEMPTED", "UNBACKED",
))
PHASE_WORDS = frozenset(("SNAPSHOT", "PRECURSOR", "DEPLOY_PRECURSOR", "SCHEMA", "CODE",
                         "I18N", "BOT", "VERIFY"))
BATCH_WORDS = frozenset(("AUTOLOG_HOTFIX", "BUG392_MERGE", "BUG392_SERVER", "REJOIN_PHASE_A",
                         "SEPT10_BATCH", "SEPT12_GACHA", "SEPT14_GACHA", "SEPT6_TRIAGE"))
TEST_OUTCOMES = frozenset(("PASSED", "FAILED", "ERROR", "SKIPPED"))
ARM_WORDS = frozenset(("MUTANT", "TWIN"))
VERDICT_WORDS = frozenset(("RED", "GREEN"))
OBSERVED_WORDS = VERDICT_WORDS | frozenset(("NOT_APPLIED", "UNCOMPILABLE"))
RESTORE_WORDS = frozenset(("EQUAL", "UNEQUAL"))
MESSAGE_WORDS = frozenset(("INCLUDED", "WITHHELD", "NONE"))
AGREEMENT_WORDS = frozenset(("MATCH", "MISMATCH"))
HARNESS_WORDS = (frozenset(HARNESS_ARTIFACTS) | TEST_OUTCOMES | ARM_WORDS | OBSERVED_WORDS
                 | RESTORE_WORDS | MESSAGE_WORDS)
WORDS = FIXED_WORDS | PHASE_WORDS | BATCH_WORDS | HARNESS_WORDS | frozenset((SCHEMA,))

# The synthetic vocabulary: the tests module's own fixture values, exported
# there as SYNTHETIC_VOCABULARY. A copy, compared with the export by the
# harness. Every one is a documentation value -- the a-controller family,
# RFC 5737 space, and the two batch names the fixtures select.
SYNTHETIC_VOCABULARY = frozenset((
    "a-controller", "a-group", "a-primary-group", "a-standby-group",
    "/srv/a-play-dir/playbooks", "a-machine", "a-sibling", "192.0.2.17",
    "a-different-controller", "a-second-group", "a-later-controller", "a-node",
    "a-group-2", "bug392-merge", "sept14-gacha",
))

# A Python exception TYPE -- the class, never its message -- from a closed
# list. NONE is a control whose test passed; UNPARSED a failure whose type the
# harness could not read, which is said rather than guessed.
EXCEPTIONS = frozenset((
    "NONE", "UNPARSED", "AssertionError", "Fail", "Failed", "AttributeError", "TypeError",
    "KeyError", "ValueError", "IndexError", "NameError", "SyntaxError", "RuntimeError",
    "SystemExit", "OSError", "FileNotFoundError", "PermissionError", "ImportError",
    "ModuleNotFoundError", "UnicodeDecodeError", "UnicodeEncodeError", "StopIteration",
    "ZeroDivisionError", "RecursionError", "NotImplementedError", "JSONDecodeError",
    "CalledProcessError", "TimeoutExpired", "UnboundLocalError",
))

# ---------------------------------------------------------------------------
# The types.
T_WORD, T_INT, T_SHA40, T_SHA7, T_UTC, T_DECLARED = (
    "WORD", "INT", "SHA40", "SHA7", "UTC", "DECLARED")
T_NODE, T_CONTROL, T_EXCEPTION, T_TOKEN = "NODE", "CONTROL", "EXCEPTION", "TOKEN"

SHA40 = re.compile(r"\A[0-9a-f]{40}\Z")
SHA7 = re.compile(r"\A[0-9a-f]{7}\Z")
UTC = re.compile(r"\A[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\+00:00\Z")
# A pytest node id: THE tests file's directory, a test module, a test name. A
# drive letter, a backslash, a `..` segment and any other directory all fail.
NODE = re.compile(r"\Abackend/tests/test_[a-z0-9_]+\.py::test_[A-Za-z0-9_]+\Z")
# A control id: the round, then the finding it controls -- a letter, up to two
# digits and one letter. Nothing longer, so it cannot spell a name.
CONTROL = re.compile(r"\AR[0-9]{1,2}_[A-Z][0-9]{0,2}[A-Z]?\Z")
# Any hex run long enough to be a digest.
HEXRUN = re.compile(r"(?<![0-9A-Za-z])[0-9a-f]{32,}(?![0-9A-Za-z])")

_W, _I, _D, _U = (T_WORD,), (T_INT,), (T_DECLARED,), (T_UTC,)
_OID = (T_SHA40, T_WORD)


def one_of(words):
    """A per-key enumeration, as a type alternative."""
    return (frozenset(words),)


# ---------------------------------------------------------------------------
# The key sets. The four train artifacts: a copy of the train's own tables.
TRAIN_HEAD = {"schema": _W, "version": _I, "generated_utc": _U, "batch": _W,
              "artifact": _W, "reviewed_tip": _OID, "main_expected": _OID,
              "main_now": _OID, "branch_tip": _OID, "migrations": _I}
_BOX = {"selector": _W, "endpoint": _D}
_COUNTS = {"tables": _I, "expect_tables": _I, "columns": _I, "expect_columns": _I,
           "indexes": _I, "expect_indexes": _I}
SINGLES = {
    "PLAN": {"outcome": _W, "refused_at": _W, "exit_code": _I, "provenance": _W,
             "refusal_class": _W, "snapshot_mechanism": _W},
    "CHECK": {"ahead": _I, "state_keys": _I, "verified": _W, "snapshot": _W,
              "snapshot_name": _W, "snapshot_batch": _W, "snapshot_endpoint": _W,
              "snapshot_fingerprint": _W, "snapshot_minted": _W, "seat_bindings": _I,
              "code_sha": _OID, "code_deployed": _W, "pre_code_old_build": _W, "bot": _W,
              "schema_phase": _W, "deploy_precursor": _W, "i18n": _W, "repairs": _I},
    "VERIFY": {"bot": _W, "edge": _D, "edge_smoke": _I, "code_sha": _OID,
               "code_sha_provenance": _W, "both_boxes": _W, "fingerprint": _W,
               "state_written": _W, "verified": _W},
    "SNAPSHOT": {"dropped": _I, "names": _I, "usable": _W, "endpoint": _W,
                 "fingerprint": _W, "listing_rc": _I, "readings_agree": _W, "outcome": _W},
    # The two the harness renders.
    "TESTS": {"collected": _I, "passed": _I, "failed": _I, "errors": _I, "skipped": _I},
    "MUTATIONS": {"control_count": _I, "arms": _I, "mutant_red": _I, "twin_green": _I,
                  "restores_equal": _I, "problems": _I,
                  "final_restore": one_of(RESTORE_WORDS),
                  "vocabulary_control": one_of(MESSAGE_WORDS),
                  "vocabulary_twin": one_of(MESSAGE_WORDS),
                  "vocabulary_agreement": one_of(AGREEMENT_WORDS),
                  "schema_agreement": one_of(AGREEMENT_WORDS)},
}
ROWS = {
    "PLAN": {"phases": {"name": _W, "disposition": _W, "reason": _W}},
    "CHECK": {"boxes": dict(_BOX, mod_version=_W, control=_W, build=_W, marker=_W,
                            readings=_I, **_COUNTS)},
    "VERIFY": {"boxes": dict(_BOX, smoke=_I, control=_W, build=_W, readings=_I),
               "schema_counts": dict(_BOX, **_COUNTS),
               "shas": dict(_BOX, deployed_sha=(T_SHA40,), box_sha=(T_SHA40,),
                            sha_reading=_W)},
    "SNAPSHOT": {"records": {"kind": _W, "fields": _I}},
    "TESTS": {"tests": {"node": (T_NODE,), "outcome": one_of(TEST_OUTCOMES)}},
    "MUTATIONS": {
        "controls": {"id": (T_CONTROL,), "kind": one_of(ARM_WORDS),
                     "expected": one_of(VERDICT_WORDS), "observed": one_of(OBSERVED_WORDS),
                     "restore": one_of(RESTORE_WORDS), "exception": (T_EXCEPTION,),
                     "message": one_of(MESSAGE_WORDS), "tokens": _I},
        # An INCLUDED message travels as its tokens, one row each, every one
        # of them typed. There is no row for a WITHHELD one.
        "messages": {"id": (T_CONTROL,), "kind": one_of(ARM_WORDS), "position": _I,
                     "token": (T_TOKEN,)},
    },
}
HARNESS_HEAD = {"schema": _W, "version": _I, "generated_utc": _U, "batch": _W,
                "artifact": _W, "base": (T_SHA40,), "tests_tip": (T_SHA40,)}


def head_for(artifact):
    return TRAIN_HEAD if artifact in TRAIN_ARTIFACTS else HARNESS_HEAD


_TYPE_WORDS = {T_WORD: "a member of the closed vocabulary", T_INT: "an integer",
               T_SHA40: "a 40-character object id", T_SHA7: "a 7-character object id",
               T_UTC: "a UTC instant", T_DECLARED: "one of the four sanctioned identifiers",
               T_NODE: "a test node id in the tests directory",
               T_CONTROL: "a control id", T_EXCEPTION: "an exception type from the closed list",
               T_TOKEN: "a synthetic-vocabulary token"}


def of_type(value, kind):
    """True when `value` is a member of the one type `kind`."""
    if isinstance(value, bool):
        return False
    if kind == T_INT:
        return isinstance(value, int)
    if kind == T_TOKEN and isinstance(value, int):
        return True
    if not isinstance(value, str):
        return False
    if isinstance(kind, frozenset):
        return value in kind
    if kind == T_WORD:
        return value in WORDS
    if kind == T_SHA40:
        return bool(SHA40.match(value))
    if kind == T_SHA7:
        return bool(SHA7.match(value))
    if kind == T_UTC:
        return bool(UTC.match(value))
    if kind == T_DECLARED:
        return value in SANCTIONED
    if kind == T_NODE:
        return bool(NODE.match(value))
    if kind == T_CONTROL:
        return bool(CONTROL.match(value))
    if kind == T_EXCEPTION:
        return value in EXCEPTIONS
    if kind == T_TOKEN:
        return value in SYNTHETIC_VOCABULARY or value in WORDS or value in SANCTIONED
    return False


def _describe(kind):
    if isinstance(kind, frozenset):
        return "one of %s" % ", ".join(sorted(kind))
    return _TYPE_WORDS[kind]


def scalar_problem(value, types):
    """Why `value` is not a member of any of `types`, or None.

    UNRECORDED is a member of every key's type: it is the word for a key the
    run did not reach, and the key is still present."""
    if isinstance(value, bool):
        return "not a value type (a boolean)"
    if value is None:
        return "not a value type (null)"
    if isinstance(value, (list, dict)):
        return "not a value type (a %s)" % type(value).__name__
    if value == UNRECORDED:
        return None
    if any(of_type(value, kind) for kind in types):
        return None
    return "not a value of its type (%s)" % " or ".join(_describe(k) for k in types)


def _typed_object_ids(doc, artifact):
    """Every value this document carries at a key TYPED as a 40-hex object id."""
    found = set()
    singles = dict(head_for(artifact), **SINGLES[artifact])
    for key, types in singles.items():
        if T_SHA40 in types and isinstance(doc.get(key), str) and SHA40.match(doc[key]):
            found.add(doc[key])
    for key, spec in ROWS[artifact].items():
        for row in doc.get(key) or []:
            if not isinstance(row, dict):
                continue
            for rkey, types in spec.items():
                v = row.get(rkey)
                if T_SHA40 in types and isinstance(v, str) and SHA40.match(v):
                    found.add(v)
    return found


def document_problems(doc):
    """Every reason `doc` is not a summary this schema admits."""
    if not isinstance(doc, dict):
        return ["the summary is not an object"]
    out = []
    if doc.get("schema") != SCHEMA:
        out.append("the document does not carry this schema's name")
    if doc.get("version") != VERSION:
        out.append("the document does not carry this schema's version")
    artifact = doc.get("artifact")
    if artifact not in ARTIFACTS:
        out.append("the document names no artifact this schema defines")
        return out
    singles = dict(head_for(artifact), **SINGLES[artifact])
    rows = ROWS[artifact]
    for key in sorted(doc):
        if key not in singles and key not in rows:
            out.append("the key %r is not a key this schema defines for a %s document"
                       % (key, artifact))
    for key in sorted(set(singles) | set(rows)):
        if key not in doc:
            out.append("the %s document is missing the key %r" % (artifact, key))
    for key in sorted(singles):
        if key in doc:
            bad = scalar_problem(doc[key], singles[key])
            if bad:
                out.append("%r is %s" % (key, bad))
    for key in sorted(rows):
        if key not in doc:
            continue
        spec = rows[key]
        value = doc[key]
        if not isinstance(value, list):
            out.append("the %r section is not a list of rows" % (key,))
            continue
        for i, row in enumerate(value):
            if not isinstance(row, dict):
                out.append("row %d of %r is not an object" % (i, key))
                continue
            for rkey in sorted(row):
                if rkey not in spec:
                    out.append("the key %r in row %d of %r is not a key this schema defines "
                               "for that section" % (rkey, i, key))
            for rkey in sorted(spec):
                if rkey not in row:
                    out.append("row %d of %r is missing the key %r" % (i, key, rkey))
                    continue
                bad = scalar_problem(row[rkey], spec[rkey])
                if bad:
                    out.append("%r in row %d of %r is %s" % (rkey, i, key, bad))
    # ...and the one class said by name although no type admits it: a digest
    # that is not a value this document types as an object id.
    declared = _typed_object_ids(doc, artifact)
    for run in sorted(set(HEXRUN.findall(json.dumps(doc)))):
        if run not in declared:
            out.append("the document carries a %d-character hex token that is not a value it "
                       "types as an object id -- a machine fingerprint is a persistent "
                       "machine identifier and may not travel in a bundle" % len(run))
    return out


def check_file(path):
    """(problems, [artifact names]) for one JSON file."""
    try:
        with io.open(path, encoding="utf-8") as fh:
            loaded = json.load(fh)
    except (IOError, OSError) as e:
        return ["could not be read: %s" % type(e).__name__], []
    except ValueError:
        return ["is not JSON"], []
    docs = loaded if isinstance(loaded, list) else [loaded]
    problems, names = [], []
    for i, doc in enumerate(docs):
        for p in document_problems(doc):
            problems.append("document %d: %s" % (i, p))
        names.append(doc.get("artifact") if isinstance(doc, dict) else None)
    return problems, names


def pin_problems(pin):
    """Whole-pin questions: every artifact present exactly once, in its own file."""
    out = []
    present = sorted(n for n in os.listdir(pin) if n.startswith("summary") and
                     n.endswith(".json"))
    for name in present:
        if name not in PIN_FILES.values():
            out.append("%s is a summary file this schema does not name" % name)
    for artifact, name in sorted(PIN_FILES.items()):
        path = os.path.join(pin, name)
        if not os.path.isfile(path):
            out.append("the pin carries no %s document (%s is absent)" % (artifact, name))
            continue
        _p, names = check_file(path)
        if names != [artifact]:
            out.append("%s must carry exactly one %s document" % (name, artifact))
    return out


# ---------------------------------------------------------------------------
# The controls.

def _filled(artifact, **values):
    """A document of `artifact` with every key present."""
    doc = {"schema": SCHEMA, "version": VERSION, "artifact": artifact,
           "generated_utc": "2026-09-23T05:00:00+00:00", "batch": "BUG392_MERGE"}
    for key, types in dict(head_for(artifact), **SINGLES[artifact]).items():
        doc.setdefault(key, UNRECORDED)
    for key in ROWS[artifact]:
        doc.setdefault(key, [])
    if artifact in HARNESS_ARTIFACTS:
        doc["base"] = "0" * 40
        doc["tests_tip"] = "1" * 40
    doc.update(values)
    return doc


def self_test():
    """The controls, each named, each with its verdict printed."""
    rows = []

    def arm(name, doc, expect_red):
        problems = document_problems(doc)
        red = bool(problems)
        rows.append((name, "RED" if red else "GREEN", "RED" if expect_red else "GREEN",
                     "PASS" if red == expect_red else "FAIL",
                     problems[0] if problems else ""))

    plan = _filled("PLAN", outcome="COMPLETED", provenance="MATCH", exit_code=0,
                   reviewed_tip="0" * 40, migrations=0,
                   phases=[{"name": "SNAPSHOT", "disposition": "SKIPPED",
                            "reason": "NO_MIGRATION"}])
    arm("a real PLAN shape, every key present", plan, False)
    arm("UNRECORDED in every key a run did not reach", _filled("PLAN"), False)
    arm("a planted free-text value", dict(plan, outcome="the play said a-machine"), True)
    arm("a planted unknown key, of the key form, with a good value",
        dict(plan, note="PRESENT"), True)
    arm("a planted key of the wrong form", dict(plan, **{"Note": "PRESENT"}), True)
    arm("an upper-case word outside the closed vocabulary",
        dict(plan, outcome="AN_INVENTORY_GROUP"), True)
    arm("a number where a word is typed", dict(plan, outcome=7), True)
    arm("a word where a number is typed", dict(plan, exit_code="YES"), True)
    arm("a planted 64-hex token", dict(plan, refused_at="a" * 64), True)
    arm("a planted 32-hex token in a row",
        dict(plan, phases=[{"name": "CODE", "disposition": "RAN", "reason": "b" * 32}]), True)
    missing = dict(plan)
    del missing["outcome"]
    arm("a missing key", missing, True)
    arm("a missing key in a row",
        dict(plan, phases=[{"name": "CODE", "disposition": "RAN"}]), True)
    arm("an unknown key in a row",
        dict(plan, phases=[{"name": "CODE", "disposition": "RAN", "reason": "NONE",
                            "note": "PRESENT"}]), True)
    arm("a planted boolean", dict(plan, outcome=True), True)
    arm("a planted null", dict(plan, outcome=None), True)
    arm("a planted nested object", dict(plan, outcome={"controller": "a-controller"}), True)
    arm("a row that is not an object", dict(plan, phases=["SNAPSHOT"]), True)
    arm("a section that is not a list", dict(plan, phases="SNAPSHOT"), True)
    arm("a wrong schema name", dict(plan, schema="SOMETHING_ELSE"), True)
    arm("a wrong version", dict(plan, version=99), True)
    arm("an undeclared artifact", dict(plan, artifact="OTHER"), True)
    verify = _filled("VERIFY", edge="competitive-rounds.duckdns.org", edge_smoke=200)
    arm("a sanctioned identifier at a DECLARED key", verify, False)
    arm("an undeclared address at a DECLARED key", dict(verify, edge="203.0.113.7"), True)
    arm("a sanctioned identifier at a WORD key", dict(verify, bot="192.168.72.90"), True)
    arm("an object id at a key typed as one",
        dict(verify, code_sha="0" * 40,
             shas=[{"selector": "PRIMARY", "endpoint": "192.168.72.199",
                    "deployed_sha": "0" * 40, "box_sha": "0" * 40,
                    "sha_reading": "MATCH"}]), False)
    tests_doc = _filled("TESTS", collected=1, passed=1, failed=0, errors=0, skipped=0,
                        tests=[{"node": "backend/tests/test_pc_steam_server.py::test_a",
                                "outcome": "PASSED"}])
    arm("a TESTS document with a node id", tests_doc, False)
    for label, node in (("a drive letter", "C:/x/backend/tests/test_a.py::test_a"),
                        ("a parent segment", "backend/tests/../test_a.py::test_a"),
                        ("a backslash", "backend\\tests\\test_a.py::test_a"),
                        ("another directory", "scripts/deploy/test_a.py::test_a")):
        arm("a node id carrying %s" % label,
            dict(tests_doc, tests=[{"node": node, "outcome": "PASSED"}]), True)
    arm("a node id outside its own artifact",
        dict(plan, phases=[{"name": "backend/tests/test_a.py::test_a",
                            "disposition": "RAN", "reason": "NONE"}]), True)
    arm("a test outcome outside its enumeration",
        dict(tests_doc, tests=[{"node": "backend/tests/test_a.py::test_a",
                                "outcome": "MATCH"}]), True)
    control = {"id": "R8_H2A", "kind": "MUTANT", "expected": "RED", "observed": "RED",
               "restore": "EQUAL", "exception": "AssertionError", "message": "INCLUDED",
               "tokens": 2}
    mut_doc = _filled("MUTATIONS", control_count=1, arms=2, mutant_red=1, twin_green=1,
                      restores_equal=2, problems=0, final_restore="EQUAL",
                      vocabulary_control="WITHHELD", vocabulary_twin="INCLUDED",
                      vocabulary_agreement="MATCH", schema_agreement="MATCH",
                      controls=[control],
                      messages=[{"id": "R8_H2A", "kind": "MUTANT", "position": 0,
                                 "token": "a-machine"},
                                {"id": "R8_H2A", "kind": "MUTANT", "position": 1,
                                 "token": 3}])
    arm("a MUTATIONS document with an included message", mut_doc, False)
    arm("an exception TYPE carrying its message",
        dict(mut_doc, controls=[dict(control, exception="AssertionError: a-machine")]), True)
    arm("an exception type outside the closed list",
        dict(mut_doc, controls=[dict(control, exception="SomeHostError")]), True)
    arm("a control id that could spell a name",
        dict(mut_doc, controls=[dict(control, id="R8_SCRBOX")]), True)
    arm("a message token outside the synthetic vocabulary",
        dict(mut_doc, messages=[{"id": "R8_H2A", "kind": "MUTANT", "position": 0,
                                 "token": "somewhere"}]), True)
    arm("a message token that is a 64-hex run",
        dict(mut_doc, messages=[{"id": "R8_H2A", "kind": "MUTANT", "position": 0,
                                 "token": "c" * 64}]), True)
    arm("an exception type outside its own artifact",
        dict(plan, phases=[{"name": "CODE", "disposition": "RAN",
                            "reason": "AssertionError"}]), True)
    width = max(len(r[0]) for r in rows)
    for name, got, want, verdict, why in rows:
        print("  %-*s  got %-5s want %-5s  %s%s"
              % (width, name, got, want, verdict, ("  -- " + why) if why else ""))
    failed = [r for r in rows if r[3] == "FAIL"]
    reds = len([r for r in rows if r[2] == "RED"])
    print("\n  %d control(s): %d want RED, %d want GREEN; %d failed"
          % (len(rows), reds, len(rows) - reds, len(failed)))
    return 1 if failed else 0


def main(argv):
    if not argv:
        print(__doc__.strip().splitlines()[-4].strip())
        return 2
    if argv[0] == "--self-test":
        return self_test()
    rc = 0
    total_docs = 0
    for target in argv:
        if not os.path.exists(target):
            print("!! %s: does not exist" % os.path.basename(target))
            rc = 1
            continue
        if os.path.isdir(target):
            whole = pin_problems(target)
            for p in whole:
                print("!! %s" % p)
            if whole:
                rc = 1
            files = [os.path.join(target, n) for n in sorted(PIN_FILES.values())
                     if os.path.isfile(os.path.join(target, n))]
            if not files:
                print("!! no summary documents found -- a validator with nothing to check is "
                      "a check that cannot fail")
                rc = 1
                continue
        else:
            files = [target]
        for path in files:
            problems, names = check_file(path)
            total_docs += len(names)
            if problems:
                rc = 1
                print("!! %s (%d document(s))" % (os.path.basename(path), len(names)))
                for p in problems:
                    print("     %s" % p)
            else:
                print("OK %s: %d document(s) validate (%s)"
                      % (os.path.basename(path), len(names), ", ".join(map(str, names))))
    print("\nTOTAL %d document(s), %s" % (total_docs, "REFUSED" if rc else "all valid"))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
