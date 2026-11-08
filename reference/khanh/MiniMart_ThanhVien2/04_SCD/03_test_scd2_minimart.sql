BEGIN;

DO $$
BEGIN
    IF current_database() <> 'minimart_dw' THEN
        RAISE EXCEPTION 'Bạn cần mở Query Tool tại database minimart_dw!';
    END IF;
    IF to_regclass('dw.dim_household') IS NULL THEN
        RAISE EXCEPTION 'Chưa có bảng dw.dim_household; hãy chạy DDL Chương 2 trước.';
    END IF;
END $$;

DROP TABLE IF EXISTS pg_temp.household_scd2_fixture;
CREATE TEMP TABLE household_scd2_fixture
    (LIKE dw.dim_household INCLUDING ALL)
    ON COMMIT PRESERVE ROWS;

INSERT INTO household_scd2_fixture
(household_id, income_desc, effective_from_day, effective_to_day, is_current, change_reason)
VALUES ('DEMO_HH_SCD2_001', 'MUC_A', 0, NULL, TRUE, 'Initial load');

UPDATE household_scd2_fixture
SET effective_to_day = 100, is_current = FALSE
WHERE household_id = 'DEMO_HH_SCD2_001' AND is_current = TRUE;

INSERT INTO household_scd2_fixture
(household_id, income_desc, effective_from_day, effective_to_day, is_current, change_reason)
VALUES ('DEMO_HH_SCD2_001', 'MUC_C', 100, NULL, TRUE, 'Normal change at DAY 100');

UPDATE household_scd2_fixture
SET effective_to_day = 95
WHERE household_id = 'DEMO_HH_SCD2_001'
  AND effective_from_day = 0 AND effective_to_day = 100 AND is_current = FALSE;

INSERT INTO household_scd2_fixture
(household_id, income_desc, effective_from_day, effective_to_day, is_current, change_reason)
VALUES ('DEMO_HH_SCD2_001', 'MUC_B', 95, 100, FALSE, 'Late arrival with effective DAY 95');

DO $$
DECLARE
    n_ver INTEGER;
    n_current INTEGER;
    n_overlap INTEGER;
    n_bad_day INTEGER;
BEGIN
    SELECT COUNT(*), COUNT(*) FILTER (WHERE is_current)
    INTO n_ver, n_current
    FROM household_scd2_fixture
    WHERE household_id = 'DEMO_HH_SCD2_001';

    SELECT COUNT(*) INTO n_overlap
    FROM household_scd2_fixture a
    JOIN household_scd2_fixture b
      ON a.household_id = b.household_id
     AND a.household_key < b.household_key
     AND a.effective_from_day < COALESCE(b.effective_to_day, 2147483647)
     AND b.effective_from_day < COALESCE(a.effective_to_day, 2147483647)
    WHERE a.household_id = 'DEMO_HH_SCD2_001';

    WITH expected(day_no, income_expected) AS (
        VALUES (90, 'MUC_A'), (95, 'MUC_B'), (100, 'MUC_C')
    ), comparisons AS (
        SELECT e.day_no,
               COUNT(h.household_key) AS matched_rows,
               MAX(h.income_desc) AS actual_income,
               MAX(e.income_expected) AS income_expected
        FROM expected e
        LEFT JOIN household_scd2_fixture h
          ON h.household_id = 'DEMO_HH_SCD2_001'
         AND e.day_no >= h.effective_from_day
         AND (h.effective_to_day IS NULL OR e.day_no < h.effective_to_day)
        GROUP BY e.day_no
    )
    SELECT COUNT(*) INTO n_bad_day
    FROM comparisons
    WHERE matched_rows <> 1 OR actual_income IS DISTINCT FROM income_expected;

    IF n_ver <> 3 OR n_current <> 1 OR n_overlap <> 0 OR n_bad_day <> 0 THEN
        RAISE EXCEPTION
          'SCD2 FAIL: versions %, current %, overlaps %, incorrect DAYs %',
           n_ver, n_current, n_overlap, n_bad_day;
    END IF;
END $$;

COMMIT;

WITH expected(day_no, expected_income) AS (
    VALUES (90, 'MUC_A'), (95, 'MUC_B'), (100, 'MUC_C')
)
SELECT e.day_no AS source_day,
       e.expected_income,
       h.income_desc AS actual_income,
       h.effective_from_day,
       h.effective_to_day,
       h.is_current,
       CASE WHEN h.income_desc = e.expected_income THEN 'PASS' ELSE 'FAIL' END AS result
FROM expected e
LEFT JOIN household_scd2_fixture h
  ON h.household_id = 'DEMO_HH_SCD2_001'
 AND e.day_no >= h.effective_from_day
 AND (h.effective_to_day IS NULL OR e.day_no < h.effective_to_day)
ORDER BY e.day_no;
