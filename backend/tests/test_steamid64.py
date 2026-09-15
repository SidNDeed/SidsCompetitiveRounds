"""The public individual SteamID64 domain (v4.13, review r14): one validator for
Python, the same rule written into SQL from the same two constants, and
PostgreSQL's own answer for that SQL committed beside the tests.
steamid64_pg_parity.py holds the shared vectors, builds the query and reads
the answer."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "api")))

import pytest  # noqa: E402

import steamid64  # noqa: E402
import steamid64_pg_parity as parity  # noqa: E402
from steamid64_pg_parity import VECTORS  # noqa: E402


def test_the_interval_is_the_public_individual_account_space():
    # universe 1 (bits 56-63), type individual (bits 52-55), instance 1 (bits 32-51), account number 0..2**32-1
    assert steamid64.INDIVIDUAL_MIN == 76561197960265728 == (1 << 56) | (1 << 52) | (1 << 32)
    assert steamid64.INDIVIDUAL_MAX == 76561202255233023 == steamid64.INDIVIDUAL_MIN + 2 ** 32 - 1
    assert len(str(steamid64.INDIVIDUAL_MIN)) == len(str(steamid64.INDIVIDUAL_MAX)) == 17


def test_the_validator_admits_exactly_the_interval():
    assert sum(1 for _, admitted in VECTORS if admitted) == 5 and len(VECTORS) == 27
    for text, admitted in VECTORS:
        assert steamid64.is_individual_id(text) is admitted, ascii(text)
    for other in (None, 76561198040410653, b"76561198040410653", ["76561198040410653"]):
        assert steamid64.is_individual_id(other) is False, repr(other)


def test_the_sql_is_written_from_the_constants_for_a_column_reference_only():
    # The readable form. What PostgreSQL makes of it is the next test's business: this pin can be edited
    # along with the SQL, the committed answer's digest cannot.
    assert steamid64.individual_id_sql("p.steam_id") == (
        "(CASE WHEN p.steam_id ~ '^[0-9]{17}$' "
        "THEN CAST(p.steam_id AS bigint) BETWEEN 76561197960265728 AND 76561202255233023 ELSE false END)")
    for bad in ("", "p.steam_id; SELECT 1", "'76561198040410653'", "p.steam_id)", "P.steam_id", None, 7):
        with pytest.raises(ValueError):
            steamid64.individual_id_sql(bad)


def test_postgresql_answered_this_exact_query_with_the_validators_verdicts(tmp_path):
    """The committed answer (fixtures/steamid64_pg_answer.txt) was recorded under the sha256 of the query this
    code builds now -- the generated SQL and every vector -- and PostgreSQL's verdict on each of the 27 vectors,
    which arrived intact, equals the vector's expected verdict and is_individual_id's. A change to the SQL text,
    a vector or the validator fails here until the query is run on PostgreSQL again and the answer re-recorded
    (steamid64_pg_parity.py --query, then --record)."""
    assert parity.compare(parity.ANSWER) == 0
    with open(parity.ANSWER, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    assert lines[0] == "query-sha256: " + parity.fingerprint()
    # every refusal compare owes, each on a copy that differs from the committed answer in one way
    variants = {
        "recorded for another query": ["query-sha256: " + "0" * 64] + lines[1:],
        "the digest not on the first line": lines[1:2] + lines[:1] + lines[2:],
        "one verdict differs": [("7|17|t" if line == "7|17|f" else line) for line in lines],
        "a vector arrived altered": [("8|17|f" if line == "8|18|f" else line) for line in lines],
        "a row missing": [line for line in lines if line != "26|0|f"],
        "a row twice": lines + ["3|17|f"],
        "a row for no vector": lines + ["27|1|f"],
    }
    for name, variant in variants.items():
        assert variant != lines, name
        path = tmp_path / "answer.txt"
        path.write_text("\n".join(variant) + "\n", encoding="utf-8")
        assert parity.compare(str(path)) == 1, name
