CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS stg;
CREATE SCHEMA IF NOT EXISTS src;
CREATE TABLE IF NOT EXISTS audit.source_file(
 file_id text PRIMARY KEY,source_name text NOT NULL,filename text NOT NULL,sha256 text NOT NULL,
 row_count bigint NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(source_name,sha256));
CREATE TABLE IF NOT EXISTS audit.batch_file(
 run_id text REFERENCES audit.runs(run_id),file_id text REFERENCES audit.source_file(file_id),
 read_count bigint NOT NULL,accepted_count bigint NOT NULL,rejected_count bigint NOT NULL,skipped_count bigint NOT NULL,
 PRIMARY KEY(run_id,file_id),CHECK(read_count=accepted_count+rejected_count+skipped_count));
CREATE TABLE IF NOT EXISTS audit.rejects(
 file_id text REFERENCES audit.source_file(file_id),source_row_no bigint,source_name text NOT NULL,
 rule_code text NOT NULL,raw_payload jsonb NOT NULL,detected_at timestamptz DEFAULT now(),
 PRIMARY KEY(file_id,source_row_no,rule_code));
CREATE TABLE IF NOT EXISTS audit.steps(
 step_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,run_id text REFERENCES audit.runs(run_id),
 step_name text NOT NULL,status text NOT NULL,started_at timestamptz DEFAULT now(),finished_at timestamptz,
 message text);
CREATE TABLE IF NOT EXISTS audit.committed_file(file_id text PRIMARY KEY REFERENCES audit.source_file(file_id),run_id text REFERENCES audit.runs(run_id));
CREATE TABLE IF NOT EXISTS audit.watermark(source_name text PRIMARY KEY,max_day integer,run_id text REFERENCES audit.runs(run_id));
CREATE TABLE IF NOT EXISTS audit.scd_events(event_id text PRIMARY KEY,household_id text NOT NULL,effective_day integer NOT NULL,payload jsonb NOT NULL,created_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS audit.product_events(event_id text PRIMARY KEY,product_id text NOT NULL,payload jsonb NOT NULL,created_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS audit.release_meta(version text PRIMARY KEY REFERENCES audit.runs(run_id),pipeline_version text,source_layer text,manifest_hash text,rule_version text);
CREATE OR REPLACE FUNCTION stg.as_bigint(v text) RETURNS bigint LANGUAGE plpgsql IMMUTABLE AS $$ BEGIN
 IF btrim(v) !~ '^[0-9]+$' THEN RETURN NULL; END IF; RETURN btrim(v)::bigint;
 EXCEPTION WHEN OTHERS THEN RETURN NULL; END $$;
CREATE OR REPLACE FUNCTION stg.as_integer(v text) RETURNS integer LANGUAGE plpgsql IMMUTABLE AS $$ BEGIN
 IF btrim(v) !~ '^[0-9]+$' THEN RETURN NULL; END IF; RETURN btrim(v)::integer;
 EXCEPTION WHEN OTHERS THEN RETURN NULL; END $$;
CREATE OR REPLACE FUNCTION stg.as_numeric(v text) RETURNS numeric LANGUAGE plpgsql IMMUTABLE AS $$ DECLARE n numeric; BEGIN
 IF btrim(v) !~ '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$' THEN RETURN NULL; END IF;
 n:=btrim(v)::numeric; IF abs(n)>=1000000000000000 THEN RETURN NULL; END IF; RETURN n;
 EXCEPTION WHEN OTHERS THEN RETURN NULL; END $$;
