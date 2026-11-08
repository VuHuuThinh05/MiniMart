SELECT 'BM02' AS benchmark,
       model AS configuration,
       run_no,
       execution_ms,
       plan->0->'Plan'->>'Node Type' AS root_node,
       plan->0->'Plan'->>'Actual Rows' AS actual_rows,
       plan AS plan_json
FROM bench.bm02_runs
UNION ALL
SELECT 'BM03', model, run_no, execution_ms,
       plan->0->'Plan'->>'Node Type',
       plan->0->'Plan'->>'Actual Rows',
       plan
FROM bench.bm03_runs
ORDER BY benchmark, configuration, run_no;
