CREATE SCHEMA IF NOT EXISTS mart;
CREATE SCHEMA IF NOT EXISTS audit;
CREATE TABLE IF NOT EXISTS audit.runs(run_id text PRIMARY KEY, started_at timestamptz DEFAULT now(), finished_at timestamptz, status text, message text);
CREATE TABLE IF NOT EXISTS audit.files(run_id text, filename text, sha256 text, source_rows bigint, loaded_rows bigint);
CREATE TABLE IF NOT EXISTS audit.checks(run_id text, check_name text, severity text, observed numeric, passed boolean);
CREATE TABLE IF NOT EXISTS mart.release(singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton), version text NOT NULL, published_at timestamptz NOT NULL);

DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='minimart_reader') THEN
 CREATE ROLE minimart_reader LOGIN PASSWORD 'minimart_reader_local_2026'; END IF;
END $$;
GRANT USAGE ON SCHEMA mart,audit TO minimart_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA mart GRANT SELECT ON TABLES TO minimart_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA audit GRANT SELECT ON TABLES TO minimart_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA mart,audit TO minimart_reader;
