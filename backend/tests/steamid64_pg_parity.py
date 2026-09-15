"""PostgreSQL's own answer for steamid64.individual_id_sql, over the vectors the
Python validator is tested with.

Nothing here connects anywhere. --query prints one read-only SELECT on one
line; the operator runs it through the read-only SQL verb on the primary and
saves the output; --record parses that output and writes the answer file (the
committed one is fixtures/steamid64_pg_answer.txt): a first line holding the
sha256 of the query text, then one `i|length|verdict` line per vector.
--compare exits 1 unless the recorded digest is the digest of the query this
code builds NOW, every vector came back exactly once and intact (its length),
and PostgreSQL's verdict equals both the vector's expected verdict and
steamid64.is_individual_id. test_steamid64.py runs compare on the committed
answer, so a change to the SQL text, a vector or the validator fails the suite
until the query is run on PostgreSQL again and the answer re-recorded:

    python backend/tests/steamid64_pg_parity.py --query > q.sql
    python backend/tests/steamid64_pg_parity.py --record out.txt backend/tests/fixtures/steamid64_pg_answer.txt "<where, when>"
    python backend/tests/steamid64_pg_parity.py --compare backend/tests/fixtures/steamid64_pg_answer.txt

Each vector is written as quoted runs of plain ASCII joined with chr() for
every other code point, so a terminal newline or a non-ASCII digit reaches the
server as itself; the answer carries length(v.s), so a vector that did not
arrive intact is a mismatch, never a pass."""
import hashlib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "api")))

import steamid64  # noqa: E402

ANSWER = os.path.join(HERE, "fixtures", "steamid64_pg_answer.txt")

# (text, admitted); every non-ASCII character written as an escape.
VECTORS = [
    ("76561197960265728", True),     # the lower boundary: account number 0
    ("76561202255233023", True),     # the upper boundary: account number 2**32 - 1
    ("76561197960265727", False),    # the lower neighbour (the 7656119 prefix admitted it)
    ("76561202255233024", False),    # the upper neighbour
    ("76561200000000000", True),     # past the 7656119 prefix, inside the interval
    ("76561199999999999", True),     # the prefix's last value
    ("76561198040410653", True),
    ("76561190000000001", False),    # the prefix admitted it; below the interval
    ("76561198040410653\n", False),  # a terminal newline: re's "$" matches before it
    ("76561198040410653\r\n", False),
    ("\n76561198040410653", False),
    (" 76561198040410653", False),
    ("76561198040410653 ", False),   # int() strips whitespace
    ("+76561198040410653", False),   # int() reads a sign
    ("076561198040410653", False),   # a leading zero
    ("7656119804041065", False),     # sixteen digits
    ("765611980404106530", False),   # eighteen digits
    ("76561198_040410653", False),   # int() reads underscores
    ("7656119804041065.3", False),
    ("\u0667\u0666\u0665\u0666\u0661\u0661\u0669\u0668\u0660\u0664\u0660\u0664\u0661\u0660\u0666\u0665\u0663",
     False),                         # Arabic-Indic digits: \d and int() read them
    ("\uff17\uff16\uff15\uff16\uff11\uff11\uff19\uff18\uff10\uff14\uff10\uff14\uff11\uff10\uff16\uff15\uff13",
     False),                         # fullwidth digits
    ("00000000000000000", False),
    ("99999999999999999", False),
    ("2535425419861127", False),     # an Xbox id
    ("14732509580164257529", False),  # a twenty-digit id from another platform
    ("abcd", False),
    ("", False),
]

_PLAIN = re.compile(r"[0-9A-Za-z .+_-]+")
_ROW = re.compile(r"\s*(\d+)\s*\|\s*(\d+)\s*\|\s*([tf])\s*")
_DIGEST = re.compile(r"query-sha256: ([0-9a-f]{64})")


def _literal(text):
    parts, i = [], 0
    while i < len(text):
        m = _PLAIN.match(text, i)
        if m:
            parts.append("'" + m.group(0) + "'")
            i = m.end()
        else:
            parts.append("chr(%d)" % ord(text[i]))
            i += 1
    return "(" + " || ".join(parts) + ")" if parts else "''"


def query():
    rows = ", ".join("(%d, %s)" % (i, _literal(text)) for i, (text, _) in enumerate(VECTORS))
    return ("SELECT v.i, length(v.s) AS n, %s AS ok FROM (VALUES %s) AS v(i, s) ORDER BY v.i"
            % (steamid64.individual_id_sql("v.s"), rows))


def fingerprint():
    return hashlib.sha256(query().encode("utf-8")).hexdigest()


def read(lines):
    """(recorded digest or None, {i: [(length, verdict), ...]}) out of an answer's lines. The digest
    counts only on the first line; every row line is kept, so a repeated index is visible."""
    digest, rows = None, {}
    for k, line in enumerate(lines):
        line = line.rstrip("\r\n")
        m = _DIGEST.fullmatch(line)
        if m and k == 0:
            digest = m.group(1)
            continue
        m = _ROW.fullmatch(line)
        if m:
            rows.setdefault(int(m.group(1)), []).append((int(m.group(2)), m.group(3) == "t"))
    return digest, rows


def mismatches(lines):
    digest, rows = read(lines)
    bad = []
    if digest != fingerprint():
        bad.append(("query-sha256", digest, fingerprint()))
    for i, (text, admitted) in enumerate(VECTORS):
        want = [(len(text), admitted)]
        if steamid64.is_individual_id(text) is not admitted or rows.get(i) != want:
            bad.append((i, ascii(text), want, rows.get(i)))
    for i in sorted(set(rows) - set(range(len(VECTORS)))):
        bad.append((i, "no such vector", None, rows[i]))
    return bad


def compare(path):
    with open(path, encoding="utf-8") as fh:
        bad = mismatches(fh.read().splitlines())
    print("vectors %d, mismatches %d" % (len(VECTORS), len(bad)))
    for row in bad:
        print("   ", row)
    return 1 if bad else 0


def pg_verdict(text, path=ANSWER):
    """PostgreSQL's recorded verdict for one of VECTORS, read from the answer file."""
    with open(path, encoding="utf-8") as fh:
        _, rows = read(fh.read().splitlines())
    (_, verdict), = rows[[t for t, _ in VECTORS].index(text)]
    return verdict


def record(output_path, answer_path, note):
    """Parse a psql output of --query and write the answer file, only when it compares clean."""
    with open(output_path, encoding="utf-8") as fh:
        _, rows = read(fh.read().splitlines())
    lines = ["query-sha256: " + fingerprint(), "# PostgreSQL's answer to steamid64_pg_parity.py --query: " + note]
    lines += ["%d|%d|%s" % (i, n, "t" if ok else "f") for i in sorted(rows) for n, ok in rows[i]]
    bad = mismatches(lines)
    if bad:
        print("not recorded: mismatches %d" % len(bad))
        for row in bad:
            print("   ", row)
        return 1
    with open(answer_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    print("recorded %d rows under query-sha256 %s" % (len(VECTORS), fingerprint()))
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--query"]:
        print(query())
        sys.exit(0)
    if len(sys.argv) == 3 and sys.argv[1] == "--compare":
        sys.exit(compare(sys.argv[2]))
    if len(sys.argv) == 5 and sys.argv[1] == "--record":
        sys.exit(record(sys.argv[2], sys.argv[3], sys.argv[4]))
    print(__doc__)
    sys.exit(2)
