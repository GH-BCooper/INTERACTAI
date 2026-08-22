"""Integration test fixtures — real Postgres via testcontainers, never mocked (CLAUDE.md §7:
"Never mock the thing under test. Mock the network; use real audio.").

`db_session` is transactional and rolled back per test: each test runs inside an outer
transaction that is always rolled back in teardown, even if the test code itself commits —
SQLAlchemy 2.0's documented `join_transaction_mode="create_savepoint"` pattern.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, create_async_engine
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

API_DIR = Path(__file__).resolve().parents[2] / "services" / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))


def _run_migrations(database_url: str) -> None:
    # alembic/env.py does `from app.core.config import ...` — a bare import, correct for its
    # normal invocation (`uv run --directory services/api alembic ...`, cwd on sys.path via
    # `prepend_sys_path = .`). Called in-process from here instead, services/api needs to be
    # on sys.path for that same bare import to resolve (handled at module scope above).
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")


@pytest_asyncio.fixture(scope="session")
async def db_engine() -> AsyncGenerator[AsyncEngine]:
    with PostgresContainer("pgvector/pgvector:pg16", driver="asyncpg") as pg:
        url = pg.get_connection_url()
        # alembic/env.py itself calls asyncio.run(...); doing that from inside a thread with
        # no event loop of its own avoids "asyncio.run() cannot be called from a running
        # event loop" against pytest-asyncio's already-running loop here.
        await asyncio.to_thread(_run_migrations, url)
        engine = create_async_engine(url)
        yield engine
        await engine.dispose()


@pytest_asyncio.fixture
async def db_connection(db_engine: AsyncEngine) -> AsyncGenerator[AsyncConnection]:
    async with db_engine.connect() as conn:
        await conn.begin()
        try:
            yield conn
        finally:
            await conn.rollback()


@pytest_asyncio.fixture
async def db_session(db_connection: AsyncConnection) -> AsyncGenerator[AsyncSession]:
    # expire_on_commit=False matches services/api/app/core/db.py's sessionmaker — without it,
    # `await db_session.commit()` expires every attribute, and the next *synchronous* access
    # (e.g. `user.id`) tries an implicit lazy-reload that can't work in async SQLAlchemy
    # (docs/phase-0-LEARN.md §4.3: "In async SQLAlchemy, lazy loading is not available").
    session = AsyncSession(
        bind=db_connection, join_transaction_mode="create_savepoint", expire_on_commit=False
    )
    try:
        yield session
    finally:
        await session.close()


@pytest_asyncio.fixture(scope="session")
async def redis_url() -> AsyncGenerator[str]:
    with RedisContainer("redis:7-alpine") as rc:
        host = rc.get_container_host_ip()
        port = rc.get_exposed_port(6379)
        yield f"redis://{host}:{port}/0"


@pytest_asyncio.fixture
async def redis_client(redis_url: str) -> AsyncGenerator[Redis]:
    client: Redis = Redis.from_url(redis_url, decode_responses=True)
    await client.flushdb()  # each test starts with a clean keyspace (rate limits, jtis, state)
    try:
        yield client
    finally:
        await client.aclose()


@pytest_asyncio.fixture
async def app_client(
    db_connection: AsyncConnection, redis_client: Redis
) -> AsyncGenerator[AsyncClient]:
    """The real FastAPI app, ASGI-mounted, with get_db/get_redis overridden to the per-test
    testcontainers-backed connection and client. Everything else (JWT/WS-token secrets, TTLs)
    comes from the real .env — those aren't what's under test here.

    A fresh AsyncSession per request (bound to the same `db_connection` the test's own
    `db_session` fixture shares), matching how the real `get_db` dependency behaves — reusing
    one AsyncSession object across the test coroutine *and* concurrent ASGI request handling
    trips SQLAlchemy's async/greenlet bridging (MissingGreenlet). Both sessions see the same
    uncommitted data because they share the connection, not because they're the same object.
    """
    from app.core.db import get_db
    from app.core.redis_client import get_redis
    from app.main import app

    async def _override_get_db() -> AsyncGenerator[AsyncSession]:
        async with AsyncSession(
            bind=db_connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        ) as session:
            yield session

    async def _override_get_redis() -> AsyncGenerator[Redis]:
        yield redis_client

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_redis] = _override_get_redis
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def seeded_content(db_session: AsyncSession) -> dict[str, dict[str, object]]:
    """The real content/{personas,rubrics,scenarios}/*.yaml, loaded via the same upsert code
    `make seed` uses — not a hand-rolled test copy — into the transactional `db_session`, so
    it's automatically rolled back with everything else at the end of the test.
    """
    from scripts.seed import _load_yaml, _upsert_personas, _upsert_rubrics, _upsert_scenarios

    personas = _load_yaml("personas")
    rubrics = _load_yaml("rubrics")
    scenarios = _load_yaml("scenarios")

    persona_ids = await _upsert_personas(db_session, personas)
    rubric_ids = await _upsert_rubrics(db_session, rubrics)
    await _upsert_scenarios(db_session, scenarios, persona_ids, rubric_ids)
    await db_session.flush()

    return {"persona_ids": persona_ids, "rubric_ids": rubric_ids}


@pytest_asyncio.fixture
async def authed_client(
    app_client: AsyncClient, db_session: AsyncSession
) -> AsyncGenerator[AsyncClient]:
    """`app_client` with a valid Authorization header for a fresh user — bypasses the OAuth
    dance itself (not automatable without a browser; see test_auth_and_sessions.py) while
    still exercising the real JWT issuance/validation path.
    """
    from app.core.security import create_access_token
    from app.models import User

    user = User(email="authed-fixture-user@example.com")
    db_session.add(user)
    await db_session.flush()

    token = create_access_token(str(user.id))
    app_client.headers["Authorization"] = f"Bearer {token}"
    app_client.headers["X-Test-User-Id"] = str(user.id)  # convenience for assertions
    yield app_client
