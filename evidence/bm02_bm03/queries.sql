-- plain
SELECT sum(sales_value) FROM bench.design_plain WHERE store_key=7 AND source_day BETWEEN 85 AND 112;
-- partitioned
SELECT sum(sales_value) FROM bench.design_partitioned WHERE store_key=7 AND source_day BETWEEN 85 AND 112;
-- single_index
SELECT sum(sales_value) FROM bench.design_single WHERE store_key=7 AND source_day BETWEEN 85 AND 112;
-- composite_index
SELECT sum(sales_value) FROM bench.design_composite WHERE store_key=7 AND source_day BETWEEN 85 AND 112;