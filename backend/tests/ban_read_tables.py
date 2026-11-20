"""The tables the ban read needs, for a test database that builds its own
narrow table list.

Bans part 2a put a read of player_bans on the path of every state-changing
route (main._is_banned behind the soft session check, the ban gate
main._ban_lock_and_gate, the report refusals). A test database built from a
hand-picked list of tables that calls such a route must carry player_bans,
and admin_users, which player_bans.banned_by_steam_id references. The
tables come from the model metadata (models.AdminUser, models.PlayerBan),
never from a CREATE typed by hand in a test:

  * with_ban_read_tables(tables) for a builder that runs
    models.Base.metadata.create_all(tables=[...]);
  * ban_read_ddl(schema=None) for a builder that runs SQL text: the CREATE
    TABLE and CREATE INDEX statements compiled for PostgreSQL from the same
    metadata, in creation order, each table qualified by `schema` when given;
  * BAN_READ_DROP_ORDER for a builder that drops its tables by name first.

test_ban_read_table_census.py checks, in both directions, that every test
file which builds its own table list and calls a function of main that
reaches the ban read uses this module, and that no file uses it otherwise.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
for _p in (API, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from sqlalchemy import MetaData  # noqa: E402
from sqlalchemy.dialects import postgresql  # noqa: E402
from sqlalchemy.schema import CreateIndex, CreateTable  # noqa: E402

import models  # noqa: E402

BAN_READ_TABLES = (models.AdminUser.__table__, models.PlayerBan.__table__)
BAN_READ_TABLE_NAMES = tuple(t.name for t in BAN_READ_TABLES)
BAN_READ_DROP_ORDER = tuple(reversed(BAN_READ_TABLE_NAMES))


def with_ban_read_tables(tables):
    """`tables` (a create_all list) with the ban read's tables added."""
    out = list(tables)
    for t in BAN_READ_TABLES:
        if t not in out:
            out.append(t)
    return out


def ban_read_ddl(schema=None, include_admin_users=True):
    """CREATE TABLE (then CREATE INDEX) of each ban read table, compiled for
    PostgreSQL from the model metadata; qualified by `schema` when given.
    include_admin_users=False for a builder whose own list already creates
    admin_users (player_bans' reference then resolves to that table)."""
    md = MetaData()
    tables = [t.to_metadata(md, schema=schema) for t in BAN_READ_TABLES]
    if not include_admin_users:
        tables = [t for t in tables if t.name != "admin_users"]
    dialect = postgresql.dialect()
    out = []
    for t in tables:
        out.append(str(CreateTable(t).compile(dialect=dialect)).strip())
        for ix in sorted(t.indexes, key=lambda i: i.name or ""):
            out.append(str(CreateIndex(ix).compile(dialect=dialect)).strip())
    return out
