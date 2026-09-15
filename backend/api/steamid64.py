"""The public individual SteamID64 domain: one rule, read by Python and written
into SQL from the same two constants.

A SteamID64 packs universe (8 bits), account type (4 bits), instance (20 bits)
and account number (32 bits). A public individual account is universe 1,
type 1, instance 1 -- 0x0110000100000000 -- plus its account number, so the
domain is the closed interval [INDIVIDUAL_MIN, INDIVIDUAL_MAX]. Every value in
it is seventeen decimal digits, so "seventeen ASCII digits whose value lies in
the interval" admits the canonical spelling of each member and nothing else:
no sign, no whitespace, no leading zero, no terminal newline, no non-ASCII
digit. A 7656119 prefix is not this rule: it admits values below the interval
and refuses every account numbered 2,039,734,272 or higher.

Standard library only, so main.py can build SQL from it whether or not the
Pillow-dependent modules import."""
import re

INDIVIDUAL_MIN = 0x0110000100000000               # 76561197960265728: account number 0
INDIVIDUAL_MAX = INDIVIDUAL_MIN + 0xFFFFFFFF      # 76561202255233023: account number 2**32 - 1
_DIGITS17 = re.compile(r"[0-9]{17}")
_COLUMN = re.compile(r"[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)?")


def is_individual_id(value) -> bool:
    """True exactly when value is the canonical decimal text of a public
    individual SteamID64. fullmatch, never match with "$" (which also matches
    before a terminal newline); [0-9], never \\d (which admits every Unicode
    decimal digit, and int() reads those)."""
    return (isinstance(value, str) and _DIGITS17.fullmatch(value) is not None
            and INDIVIDUAL_MIN <= int(value) <= INDIVIDUAL_MAX)


def individual_id_sql(column: str) -> str:
    """The same rule as a PostgreSQL boolean expression over one column
    reference. The CASE is load-bearing: PostgreSQL does not promise to
    evaluate AND's operands in order, and the cast raises on text that is not
    an integer, so the cast sits in the THEN branch and runs only for a value
    of seventeen ASCII digits, which always fits bigint. The comparison is
    numeric, so no collation is involved. `column` is spliced into the SQL
    text as it is, so it must be a plain lower-case column reference
    (`name` or `alias.name`); anything else raises ValueError rather than
    reaching the statement. What PostgreSQL makes of this text is not
    something a Python test can see: backend/tests/steamid64_pg_parity.py
    builds a query from it over the shared vectors, the answer PostgreSQL gave
    is committed in backend/tests/fixtures/steamid64_pg_answer.txt under the
    sha256 of that query, and test_steamid64.py fails when this text, the
    vectors or the validator no longer match that answer."""
    if not isinstance(column, str) or _COLUMN.fullmatch(column) is None:
        raise ValueError("column")
    return (f"(CASE WHEN {column} ~ '^[0-9]{{17}}$' "
            f"THEN CAST({column} AS bigint) BETWEEN {INDIVIDUAL_MIN:d} AND {INDIVIDUAL_MAX:d} "
            f"ELSE false END)")
