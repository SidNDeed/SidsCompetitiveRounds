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

engine = create_async_engine(DATABASE_URL, echo=False, pool_size=10, max_overflow=5)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    """FastAPI dependency that yields a database session."""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
