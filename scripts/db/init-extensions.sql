-- Runs once, automatically, only on a fresh (empty) postgres volume — see
-- docker-entrypoint-initdb.d semantics. The first Alembic migration also issues these
-- CREATE EXTENSION statements defensively, since managed Postgres (Neon) never runs this file.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
