"""Transaction continuity of a measured position (ruling REHEARSAL-R9-A1 (B)).

A rollback harness measures a program inside ONE transaction and rolls it
back. Round 9's harnesses checked only that SOME transaction was open when
the program returned (conn.is_in_transaction()), so a program running
`...; COMMIT; BEGIN; ...` committed outside the harness and was reported as
if nothing had happened (report test_r7_ro_role_pg.py:257). This module
binds a position to the identity of its transaction instead.

start(conn), inside the harness transaction, before the program:
  * sets a position TOKEN the program cannot know (SET LOCAL of
    rf10.position to a fresh random value; transaction-local, so it ends
    with the transaction);
  * takes a transaction-level advisory lock keyed by two random integers
    (pg_advisory_xact_lock: released only when the transaction ends, never
    by pg_advisory_unlock*), the same token as other sessions can see it;
  * reads the backend's virtual transaction id (pg_locks, locktype
    virtualxid, this backend's pid): a backend's local transaction counter
    never repeats, so the same pid and vxid means the same transaction.
  * opens a savepoint (SAVEPOINT rf10_position) after the three: the
    program runs inside it.
check(conn, pos, monitor_dsn), after the program, before any harness
rollback, reads them again on the connection itself. When the transaction
is in the failed state after an error, a plain re-reading is impossible and
pg_locks cannot tell the harness transaction from another one either (an
aborted transaction block has already released its locks, the vxid lock
included, before its ROLLBACK), so check() first returns to the savepoint:
ROLLBACK TO SAVEPOINT succeeds only inside the transaction that opened it,
and restores the token while the advisory lock and the vxid stay; then it
reads again. A refused ROLLBACK TO SAVEPOINT reports 'savepoint' (the
program ended the transaction, or released the harness savepoint: reported
as an effect either way). Only a connection that can no longer run a
statement at all (closed: an ORM session commit releases a NullPool
connection) is read from a separate monitor connection, where the backend's
advisory lock and vxid lock are absent once it has gone. The position is
ADMITTED only when the token reads back unchanged and the vxid is the same;
otherwise check() names what changed ('token', 'vxid', 'savepoint'), and the
harness reports the position as ENDED, an effect, never a read and never OK.
COMMIT; BEGIN, COMMIT AND CHAIN, ROLLBACK AND CHAIN, PREPARE TRANSACTION,
ROLLBACK, END and ABORT all fail the check whatever the program does next.

Session state a program can leave behind across a commit (a plain SET, a
prepared statement, a temporary object, a session advisory lock) is
isolated by the harnesses, not measured: every harness opens a new
connection for each position and closes it after the position (the round-10
notes list each harness).

check() also returns the transaction's xid if one was assigned
(pg_current_xact_id_if_assigned): a position that wrote anything at all,
including a write no catalog reading shows (a role's stored password,
masked in pg_roles), has one.
"""

import secrets

import asyncpg

SETTING = "rf10.position"
SAVEPOINT = "rf10_position"

OPEN_SQL = ("SELECT pg_catalog.set_config('rf10.position', $1, true) AS token, "
            "pg_catalog.pg_advisory_xact_lock($2::int4, $3::int4) AS lock, "
            "pg_catalog.pg_backend_pid() AS pid")

VXID = ("(SELECT l.virtualtransaction FROM pg_catalog.pg_locks l WHERE l.locktype = 'virtualxid' "
        "AND l.pid = $1 AND l.virtualxid = l.virtualtransaction AND l.granted)")

HERE_SQL = ("SELECT pg_catalog.current_setting('rf10.position', true) AS token, %s AS vxid, "
            "pg_catalog.pg_current_xact_id_if_assigned()::text AS xid" % VXID)

MONITOR_SQL = ("SELECT %s AS vxid, "
               "(SELECT count(*) FROM pg_catalog.pg_locks l WHERE l.locktype = 'advisory' AND l.pid = $1 "
               "AND l.classid::int8 = $2 AND l.objid::int8 = $3 AND l.objsubid = 2 AND l.granted) AS token_lock, "
               "(SELECT l.transactionid::text FROM pg_catalog.pg_locks l WHERE l.locktype = 'transactionid' "
               "AND l.pid = $1 AND l.mode = 'ExclusiveLock' AND l.granted LIMIT 1) AS xid" % VXID)


class Position:
    def __init__(self, token, k1, k2, pid, vxid):
        self.token, self.k1, self.k2, self.pid, self.vxid = token, k1, k2, pid, vxid

    def __repr__(self):
        return "Position(pid=%s, vxid=%s)" % (self.pid, self.vxid)


async def start(conn):
    """Mark the position at its start, inside the harness transaction; refuses
    (AssertionError) when the connection is not inside a transaction block,
    where a transaction-local token cannot persist to the next statement."""
    token = secrets.token_hex(16)
    k1, k2 = secrets.randbelow(2 ** 31 - 2) + 1, secrets.randbelow(2 ** 31 - 2) + 1
    row = await conn.fetchrow(OPEN_SQL, token, k1, k2)
    here = await conn.fetchrow(HERE_SQL, row["pid"])
    if here["token"] != token or not here["vxid"]:
        raise AssertionError("catalog_position.start(): the connection is not inside a transaction block "
                             "(the position token did not persist to the next statement)")
    await conn.execute("SAVEPOINT " + SAVEPOINT)
    return Position(token, k1, k2, row["pid"], here["vxid"])


async def check(conn, pos, monitor_dsn):
    """{'ended': [what changed], 'xid': xid or None, 'via': 'session'|'monitor'}
    at the end of the position. 'ended' empty: the same transaction."""
    via = "session"
    try:
        here = await conn.fetchrow(HERE_SQL, pos.pid)
    except asyncpg.InFailedSQLTransactionError:
        # the program's error left a transaction in the failed state: return
        # to the harness savepoint, which only the harness transaction has
        try:
            await conn.execute("ROLLBACK TO SAVEPOINT " + SAVEPOINT)
        except asyncpg.PostgresError:
            return {"ended": ["savepoint"], "xid": None, "via": "savepoint"}
        here = await conn.fetchrow(HERE_SQL, pos.pid)
        via = "savepoint"
    except asyncpg.InterfaceError:
        # the connection was released (an ORM session commit returns it to a
        # pool that closes it): read the backend from another connection
        return await check_from(monitor_dsn, pos)
    ended = []
    if here["token"] != pos.token:
        ended.append("token")
    if here["vxid"] != pos.vxid:
        ended.append("vxid")
    return {"ended": ended, "xid": here["xid"], "via": via}


async def check_from(monitor_dsn, pos):
    """The same reading from another connection, for a measured connection
    that can no longer run a statement: the token is the advisory lock only
    the position's transaction holds, the identity its vxid lock (both absent
    once the backend has gone or its transaction has ended or aborted)."""
    m = await asyncpg.connect(monitor_dsn)
    try:
        row = await m.fetchrow(MONITOR_SQL, pos.pid, pos.k1, pos.k2)
    finally:
        await m.close()
    ended = []
    if row["token_lock"] != 1:
        ended.append("token")
    if row["vxid"] != pos.vxid:
        ended.append("vxid")
    return {"ended": ended, "xid": row["xid"], "via": "monitor"}


def ended_effect(ended):
    """The effect string a harness reports for a position whose transaction
    the program ended."""
    return "ENDED:" + ",".join(ended)
