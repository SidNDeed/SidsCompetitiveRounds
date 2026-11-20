"""Bans part 2a (FIX-3 section 3): one definition of a fresh lobby member for
every mode. FFA_LOBBY_MEMBER_FRESH_SQL is an alias of LOBBY_MEMBER_FRESH_SQL
(the shared leave core reads the lobby one for every mode), so the two can
never disagree. Read from main.py's syntax tree: a retyped literal, even an
equal one, is refused (planted control)."""
import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))

import main  # noqa: E402

MAIN_PY = os.path.join(HERE, "..", "api", "main.py")


def _assignments(src, name):
    return [n.value for n in ast.parse(src).body
            if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in n.targets)]


def _is_alias(src):
    vals = _assignments(src, "FFA_LOBBY_MEMBER_FRESH_SQL")
    return len(vals) == 1 and isinstance(vals[0], ast.Name) and vals[0].id == "LOBBY_MEMBER_FRESH_SQL"


def test_the_ffa_fresh_rule_is_the_lobby_one():
    with open(MAIN_PY, encoding="utf-8") as fh:
        src = fh.read()
    assert _is_alias(src)
    assert len(_assignments(src, "LOBBY_MEMBER_FRESH_SQL")) == 1
    assert main.FFA_LOBBY_MEMBER_FRESH_SQL == main.LOBBY_MEMBER_FRESH_SQL


def test_planted_retyped_literal_is_refused():
    planted = ('LOBBY_MEMBER_FRESH_SQL = "last_polled > clock_timestamp() - INTERVAL \'75 seconds\'"\n'
               'FFA_LOBBY_MEMBER_FRESH_SQL = "last_polled > clock_timestamp() - INTERVAL \'75 seconds\'"\n')
    assert not _is_alias(planted)
