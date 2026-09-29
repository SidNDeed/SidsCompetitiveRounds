"""A colon-prefixed token inside a SQL comment is a BIND PARAMETER.

SQLAlchemy's text() scans the entire string for bind names and does not skip
`--` comments. So a review citation written as a colon followed by a number,
sitting in a comment inside a SQL literal, silently becomes a required bind
that no caller supplies -- and EVERY execute of that statement raises
InvalidRequestError before touching the database.

This is not hypothetical. `_RANKED_CANDIDATE_SQL` in main.py carried exactly
that for the life of the A1 round-2 merge: one citation in one comment, and
ranked 1v1 discovery could not run at all. The statement compiled fine; it
failed at parameter construction, which is why nothing static caught it.

The defect is a CLASS, not a line (#432), so this sweeps every SQL-looking
string constant in the backend rather than pinning the one that bit us. The
detector is compared against a comment-stripped copy of the same literal, so
it cannot be fooled by a legitimate bind that merely happens to appear near a
comment.
"""
import ast
import io
import re
from pathlib import Path

import pytest
from sqlalchemy import text

BACKEND = Path(__file__).resolve().parents[1]
MODULES = [
    BACKEND / "api" / "main.py",
    BACKEND / "api" / "tournaments.py",
    BACKEND / "api" / "models.py",
    BACKEND / "api" / "schemas.py",
]

SQL_HINT = re.compile(
    r"\b(SELECT|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|WITH\s+\w+\s+AS)\b",
    re.IGNORECASE,
)
LINE_COMMENT = re.compile(r"--[^\n]*")


def _strip_sql_comments(sql):
    """Remove `--` line comments. Block comments are not used in this repo's
    literals; if that changes, this needs /* */ handling too."""
    return LINE_COMMENT.sub("", sql)


def _binds(sql):
    try:
        return set(text(sql)._bindparams.keys())
    except Exception:
        # A literal text() itself refuses is a different problem and not this
        # test's subject; skip rather than fail for the wrong reason.
        return None


def _sql_constants(path):
    """(lineno, value) for every string constant that looks like SQL."""
    with io.open(path, "r", encoding="utf-8", newline="") as handle:
        src = handle.read()
    tree = ast.parse(src)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if SQL_HINT.search(node.value) and "--" in node.value:
                out.append((node.lineno, node.value))
    return out


def _phantoms(sql):
    """Bind names that exist ONLY because of a comment."""
    full = _binds(sql)
    bare = _binds(_strip_sql_comments(sql))
    if full is None or bare is None:
        return set()
    return full - bare


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_no_sql_literal_takes_a_bind_from_a_comment(path):
    if not path.exists():
        pytest.skip("%s is not present" % path.name)
    offenders = []
    for lineno, sql in _sql_constants(path):
        phantom = _phantoms(sql)
        if phantom:
            offenders.append((lineno, sorted(phantom)))
    assert not offenders, (
        "%s: SQL literal(s) whose comments introduce bind parameters. "
        "Remove the colon from the citation. Sites (line, phantom binds): %r"
        % (path.name, offenders)
    )


def test_the_detector_can_fail():
    """Negative control (#391). A detector that cannot fail is decoration.

    This is the real defect, reduced: a citation with a leading colon inside a
    comment, in an otherwise ordinary statement.
    """
    bad = "SELECT 1 FROM players\n-- see review MEDIUM :16675\nWHERE id = :pid"
    assert _phantoms(bad) == {"16675"}, "the sweep would not have caught the real defect"

    good = "SELECT 1 FROM players\n-- see review MEDIUM 16675\nWHERE id = :pid"
    assert _phantoms(good) == set(), "the sweep flags a comment that is actually fine"

    # A genuine bind must never be mistaken for a phantom just because a
    # comment sits beside it.
    beside = "SELECT 1 FROM players\n-- ordinary note\nWHERE id = :pid AND x = :y"
    assert _phantoms(beside) == set()
    assert _binds(beside) == {"pid", "y"}


def test_the_ranked_discovery_predicate_can_actually_build_its_parameters():
    """The specific regression, end to end through the execution path.

    construct_params is what SQLAlchemy calls to build driver arguments, and it
    is where the phantom bind raised. Compiling alone did NOT reveal it.
    """
    import main
    from sqlalchemy.dialects import postgresql

    compiled = text(main._RANKED_CANDIDATE_SQL).compile(dialect=postgresql.dialect())
    params = compiled.construct_params({
        "my_rating": 1500.0,
        "my_uncapped": 1500.0,
        "only": False,
        "pid": "00000000-0000-0000-0000-000000000000",
        "rmax": 1600,
        "rmin": 1400,
        "service_ids": [],
    })
    assert not any(key.isdigit() for key in params), (
        "a numeric bind name means a review citation leaked back into a comment: %r"
        % sorted(params)
    )
