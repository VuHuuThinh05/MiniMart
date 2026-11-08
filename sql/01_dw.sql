

CREATE SCHEMA IF NOT EXISTS dw;

CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE IF NOT EXISTS dw.dim_day (
    day_key           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_day        INTEGER NOT NULL UNIQUE CHECK (source_day >= 0),
    calendar_date     DATE,
    notes             TEXT
);

CREATE TABLE IF NOT EXISTS dw.dim_week (
    week_key          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_week_no    INTEGER NOT NULL UNIQUE CHECK (source_week_no >= 0),
    calendar_start    DATE,
    calendar_end      DATE,
    CHECK (calendar_end IS NULL OR calendar_start IS NULL OR calendar_end >= calendar_start)
);

CREATE TABLE IF NOT EXISTS dw.dim_store (
    store_key         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    store_id          TEXT NOT NULL UNIQUE,
    store_name        TEXT,
    notes             TEXT
);

CREATE TABLE IF NOT EXISTS dw.dim_product (
    product_key           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id            TEXT NOT NULL UNIQUE,
    manufacturer          TEXT,
    department            TEXT,
    brand                 TEXT,
    commodity_desc        TEXT,
    sub_commodity_desc    TEXT,
    curr_size_of_product  TEXT,
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dw.dim_household (
    household_key        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    household_id         TEXT NOT NULL,
    has_demographics     BOOLEAN NOT NULL DEFAULT FALSE,
    age_desc             TEXT,
    marital_status_code  TEXT,
    income_desc          TEXT,
    homeowner_desc       TEXT,
    hh_comp_desc         TEXT,
    household_size_desc  TEXT,
    kid_category_desc    TEXT,
    effective_from_day   INTEGER NOT NULL DEFAULT 0 CHECK (effective_from_day >= 0),
    effective_to_day     INTEGER,
    is_current           BOOLEAN NOT NULL DEFAULT TRUE,
    change_reason        TEXT,
    UNIQUE (household_id, effective_from_day),
    CHECK (effective_to_day IS NULL OR effective_to_day > effective_from_day),
    CHECK ((is_current AND effective_to_day IS NULL) OR
           (NOT is_current AND effective_to_day IS NOT NULL))
);
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'dw.dim_household'::regclass AND conname = 'ex_dim_household_no_overlap') THEN
        ALTER TABLE dw.dim_household
        ADD CONSTRAINT ex_dim_household_no_overlap
        EXCLUDE USING gist (household_id WITH =, int4range(effective_from_day, effective_to_day, '[)') WITH &&);
    END IF;
END $$;

ALTER TABLE dw.dim_household ADD COLUMN IF NOT EXISTS has_demographics BOOLEAN NOT NULL DEFAULT FALSE;

CREATE UNIQUE INDEX IF NOT EXISTS ux_dim_household_one_current
    ON dw.dim_household (household_id) WHERE is_current;
CREATE INDEX IF NOT EXISTS ix_dim_household_lookup
    ON dw.dim_household (household_id, effective_from_day, effective_to_day);

CREATE TABLE IF NOT EXISTS dw.dim_campaign (
    campaign_key   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    campaign_id    TEXT NOT NULL UNIQUE,
    description    TEXT,
    start_day      INTEGER,
    end_day        INTEGER,
    CHECK (start_day IS NULL OR start_day >= 0),
    CHECK (end_day IS NULL OR end_day >= 0),
    CHECK (start_day IS NULL OR end_day IS NULL OR end_day >= start_day)
);

CREATE TABLE IF NOT EXISTS dw.dim_coupon (
    coupon_key     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    campaign_key   BIGINT NOT NULL REFERENCES dw.dim_campaign(campaign_key),
    coupon_upc     TEXT NOT NULL,
    UNIQUE (campaign_key, coupon_upc),
    UNIQUE (coupon_key, campaign_key)
);

CREATE TABLE IF NOT EXISTS dw.bridge_coupon_product (
    coupon_key     BIGINT NOT NULL REFERENCES dw.dim_coupon(coupon_key),
    product_key    BIGINT NOT NULL REFERENCES dw.dim_product(product_key),
    PRIMARY KEY (coupon_key, product_key)
);
CREATE INDEX IF NOT EXISTS ix_bridge_coupon_product_product
    ON dw.bridge_coupon_product(product_key);

CREATE TABLE IF NOT EXISTS dw.fact_sales (
    sales_key          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    file_id            TEXT NOT NULL,
    source_row_no      BIGINT NOT NULL CHECK (source_row_no >= 0),
    household_key      BIGINT NOT NULL REFERENCES dw.dim_household(household_key),
    household_id       TEXT NOT NULL,
    product_key        BIGINT NOT NULL REFERENCES dw.dim_product(product_key),
    store_key          BIGINT NOT NULL REFERENCES dw.dim_store(store_key),
    day_key            BIGINT NOT NULL REFERENCES dw.dim_day(day_key),
    week_key           BIGINT NOT NULL REFERENCES dw.dim_week(week_key),
    source_day         INTEGER NOT NULL CHECK (source_day >= 0),
    source_week_no     INTEGER NOT NULL CHECK (source_week_no >= 0),
    basket_id          TEXT NOT NULL,
    basket_key         TEXT NOT NULL,
    trans_time         TEXT,
    quantity           NUMERIC(18,3),
    sales_value        NUMERIC(18,2),
    retail_disc        NUMERIC(18,2),
    coupon_disc        NUMERIC(18,2),
    coupon_match_disc  NUMERIC(18,2),
    UNIQUE (file_id, source_row_no)
);
CREATE INDEX IF NOT EXISTS ix_fact_sales_store_day
    ON dw.fact_sales(store_key, source_day);
CREATE INDEX IF NOT EXISTS ix_fact_sales_household_day
    ON dw.fact_sales(household_id, source_day);
CREATE INDEX IF NOT EXISTS ix_fact_sales_product_week
    ON dw.fact_sales(product_key, week_key);
CREATE INDEX IF NOT EXISTS ix_fact_sales_basket
    ON dw.fact_sales(basket_key);

CREATE TABLE IF NOT EXISTS dw.fact_campaign_contact (
    campaign_contact_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    file_id              TEXT NOT NULL,
    source_row_no        BIGINT NOT NULL CHECK (source_row_no >= 0),
    household_key        BIGINT NOT NULL REFERENCES dw.dim_household(household_key),
    household_id         TEXT NOT NULL,
    campaign_key         BIGINT NOT NULL REFERENCES dw.dim_campaign(campaign_key),
    UNIQUE (household_id, campaign_key),
    UNIQUE (file_id, source_row_no)
);
CREATE INDEX IF NOT EXISTS ix_fact_contact_campaign
    ON dw.fact_campaign_contact(campaign_key);

CREATE TABLE IF NOT EXISTS dw.fact_coupon_redemption (
    redemption_key   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    file_id          TEXT NOT NULL,
    source_row_no    BIGINT NOT NULL CHECK (source_row_no >= 0),
    household_key    BIGINT NOT NULL REFERENCES dw.dim_household(household_key),
    household_id     TEXT NOT NULL,
    day_key          BIGINT NOT NULL REFERENCES dw.dim_day(day_key),
    source_day       INTEGER NOT NULL CHECK (source_day >= 0),
    campaign_key     BIGINT NOT NULL REFERENCES dw.dim_campaign(campaign_key),
    coupon_key       BIGINT NOT NULL,
    FOREIGN KEY (coupon_key, campaign_key)
        REFERENCES dw.dim_coupon(coupon_key, campaign_key),
    UNIQUE (file_id, source_row_no)
);
CREATE INDEX IF NOT EXISTS ix_fact_redemption_campaign_day
    ON dw.fact_coupon_redemption(campaign_key, source_day);
CREATE INDEX IF NOT EXISTS ix_fact_redemption_household
    ON dw.fact_coupon_redemption(household_id);

CREATE TABLE IF NOT EXISTS dw.fact_promotion (
    promotion_key       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_key         BIGINT NOT NULL REFERENCES dw.dim_product(product_key),
    store_key           BIGINT NOT NULL REFERENCES dw.dim_store(store_key),
    week_key            BIGINT NOT NULL REFERENCES dw.dim_week(week_key),
    display_code        TEXT NOT NULL,
    mailer_code         TEXT NOT NULL,
    has_display         BOOLEAN,
    has_mailer          BOOLEAN,
    source_row_count    BIGINT NOT NULL DEFAULT 1 CHECK (source_row_count >= 1),
    UNIQUE (product_key, store_key, week_key, display_code, mailer_code)
);
CREATE INDEX IF NOT EXISTS ix_fact_promotion_product_store_week
    ON dw.fact_promotion(product_key, store_key, week_key);

