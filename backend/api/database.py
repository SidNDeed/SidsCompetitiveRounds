"""
Database connection management for Competitive ROUNDS API.
Uses SQLAlchemy async with asyncpg for PostgreSQL.
"""

import os
from contextlib import contextmanager
from contextvars import ContextVar

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://comp_rounds:changeme@localhost:5432/competitive_rounds",
)

# Pool sizing: under load (queue polls every 2s × 60 active testers + the
# match-submit / live-bets / leaderboard routes overlapping) the prior
# 10 + 5 ceiling was getting brushed during peak Saturday playtests. Bumped
# 10 -> 20 / overflow 5 -> 10 (total 30 concurrent connections), and added
# a 30s pool_timeout so a request that can't get a connection in time
# raises 503 cleanly instead of hanging the worker. pool_pre_ping=True
# silently drops dead conns from the postgres side (idle timeouts /
# restarts) before they get handed out.
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=20,
    max_overflow=10,
    pool_timeout=30,
    pool_pre_ping=True,
    pool_recycle=1800,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# A RESERVED pool for the two bot requests that END a writer's wait for the
# Discord lines in flight naming a player -- the delivery-lease release and the
# events ack (main.py, review r10): whatever the main pool's state (every
# connection held by requests queued behind a draining identity lock in the
# rare overlap), an ADMITTED release never waits behind another checkout of
# this pool and never reaches its timeout: main.py's _pc_release_slot admits
# exactly RELEASE_POOL_SIZE + RELEASE_POOL_OVERFLOW of these requests at once
# (review r12), the rest wait at the slot holding nothing. What admission
# does not remove (review r13): a connection's own validation -- pool_pre_ping,
# a pool_recycle, a reconnection after an invalidation -- can still delay an
# admitted request or fail it. The writer's wait ends within the lease's
# own life plus 5 s (65 s from its start), plus the one reading or sleep in
# flight then and the event loop's scheduling delay (main.py's
# _pc_lease_drain, r14); a release that lands earlier ends the wait
# earlier. Sized for the bot's concurrency: one events poller and a few
# commands at once.
RELEASE_POOL_SIZE = 3
RELEASE_POOL_OVERFLOW = 2
release_engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=RELEASE_POOL_SIZE,
    max_overflow=RELEASE_POOL_OVERFLOW,
    pool_timeout=30,
    pool_pre_ping=True,
    pool_recycle=1800,
)

release_session = async_sessionmaker(release_engine, class_=AsyncSession, expire_on_commit=False)


# ── The post-COMMIT seal (quarantine triage, RJ-TRIAGE C9) ─────────────────
# The quarantine triage routes (main.py, _triage_read_txn) read in ONE
# READ ONLY transaction and then build their response from values copied out
# of it. While this variable is set -- armed by that primitive once its COMMIT,
# or its ROLLBACK attempt, is over, until the response is built -- the listener
# below refuses every statement executed through EITHER engine before it is
# sent. That covers the request's own session (its next execute would begin a
# new transaction, outside READ ONLY), a helper that opens its own session
# with async_session, and the reserved pool. It sees only statements executed
# through an engine (before_cursor_execute): the pool's pre-ping on checkout
# is not one of them and is still sent. The variable is context-local, so it
# seals the task that armed it. Only post_commit_seal sets the variable and
# only the triage primitive calls it, so no other caller's behaviour changes.
_post_commit_seal: ContextVar = ContextVar("scr_post_commit_seal", default=None)

# How many statements the seal has refused in this process; the triage
# controls assert it stays 0 on every route they run.
post_commit_seal_stats = {"refused": 0}


class PostCommitSealed(RuntimeError):
    """A statement was issued after a triage read transaction had ended."""


@contextmanager
def post_commit_seal(owner: str):
    """Seal both engines for the body of the with-block, then unseal through
    the token, whether the body returns or raises."""
    token = _post_commit_seal.set(owner)
    try:
        yield
    finally:
        _post_commit_seal.reset(token)


def _refuse_sealed_statement(conn, cursor, statement, parameters, context, executemany):
    owner = _post_commit_seal.get()
    if owner is not None:
        post_commit_seal_stats["refused"] += 1
        first = (statement or "").split(None, 1)[:1]
        raise PostCommitSealed(
            f"{owner}: a statement ({first[0] if first else 'empty'}) was issued after "
            "the read transaction ended; it was not sent")


for _sealed_engine in (engine, release_engine):
    event.listen(_sealed_engine.sync_engine, "before_cursor_execute", _refuse_sealed_statement)


async def get_release_db():
    """FastAPI dependency: a session on the reserved pool (the lease release, the ack)."""
    async with release_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_db():
    """FastAPI dependency that yields a database session."""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
