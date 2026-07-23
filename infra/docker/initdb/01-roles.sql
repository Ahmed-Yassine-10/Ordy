-- Runs once on first Postgres init. Creates the two Ordy roles:
--   ordy_app       — the application role. Subject to RLS (no BYPASSRLS).
--   ordy_migrator  — owns the schema, runs migrations. Bypasses RLS for DDL/seed.
-- The RLS invariant (doc 06 §4, doc 08 §3) depends on the app NEVER connecting as an
-- owner/superuser role.

CREATE ROLE ordy_app LOGIN PASSWORD 'ordy_app_pw' NOSUPERUSER NOCREATEDB NOBYPASSRLS;
-- The migrator owns the schema AND holds BYPASSRLS so that SECURITY DEFINER helper
-- functions (app_is_member, app_api_key_candidates) can read across tenants without
-- tripping the FORCE'd policies. The app role never gets BYPASSRLS.
CREATE ROLE ordy_migrator LOGIN PASSWORD 'ordy_migrator_pw' NOSUPERUSER CREATEDB BYPASSRLS;

GRANT ALL PRIVILEGES ON DATABASE ordy TO ordy_migrator;

-- ordy_migrator owns the public schema so Alembic can manage objects.
ALTER SCHEMA public OWNER TO ordy_migrator;
GRANT USAGE ON SCHEMA public TO ordy_app;

-- Default privileges: objects created by the migrator are usable by the app.
ALTER DEFAULT PRIVILEGES FOR ROLE ordy_migrator IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ordy_app;
ALTER DEFAULT PRIVILEGES FOR ROLE ordy_migrator IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO ordy_app;

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
