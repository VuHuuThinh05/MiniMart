SELECT
    n.nspname AS schema_name,
    t.relname AS table_name,
    k.conname AS constraint_name,
    CASE k.contype
        WHEN 'p' THEN 'PRIMARY KEY'
        WHEN 'f' THEN 'FOREIGN KEY'
        WHEN 'u' THEN 'UNIQUE'
        WHEN 'c' THEN 'CHECK'
        WHEN 'x' THEN 'EXCLUSION'
        ELSE k.contype::TEXT
    END AS constraint_type,
    pg_get_constraintdef(k.oid) AS definition
FROM pg_constraint k
JOIN pg_class t ON t.oid = k.conrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE n.nspname = 'dw'
ORDER BY t.relname, constraint_type, k.conname;
