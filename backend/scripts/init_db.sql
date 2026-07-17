-- Runs once on first PostgreSQL container start.
-- Application tables are created by SQLAlchemy at API startup; this script only
-- enables the extensions the blueprint relies on so a production deployment can
-- migrate the JSON embedding columns to native pgvector columns later.
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;
