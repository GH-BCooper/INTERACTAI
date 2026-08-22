"""Alembic migration runner — async (DATABASE_URL uses the asyncpg driver).

cwd is services/api here (`uv run --directory services/api alembic ...` — see Makefile), and
`prepend_sys_path = .` in alembic.ini puts that on sys.path, so `import app...` resolves the
same way it does under uvicorn's `--app-dir services/api`.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import get_settings
from app.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Integration tests point this at an ephemeral testcontainers Postgres by pre-setting
# sqlalchemy.url on the Config object before calling alembic.command.upgrade() — see
# tests/integration/conftest.py. Only fall back to app settings (and its required secrets)
# when nothing already set the URL, which is the normal `make migrate` / CLI path.
if not config.get_main_option("sqlalchemy.url"):
    settings = get_settings()
    config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
