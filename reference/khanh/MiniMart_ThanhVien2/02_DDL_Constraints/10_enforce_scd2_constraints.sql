CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE dw.dim_household
    ADD COLUMN IF NOT EXISTS has_demographics BOOLEAN NOT NULL DEFAULT FALSE;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'dw.dim_household'::regclass
          AND conname = 'ex_dim_household_no_overlap'
    ) THEN
        ALTER TABLE dw.dim_household
        ADD CONSTRAINT ex_dim_household_no_overlap
        EXCLUDE USING gist (
            household_id WITH =,
            int4range(effective_from_day, effective_to_day, '[)') WITH &&
        );
    END IF;
END $$;
