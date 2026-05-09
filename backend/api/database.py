"""
Database connection management for Competitive ROUNDS API.
Uses SQLAlchemy async with asyncpg for PostgreSQL.
"""

import os

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


async def get_db():
    """FastAPI dependency that yields a database session."""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
