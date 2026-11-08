SELECT
    c.table_schema,
    c.table_name,
    c.ordinal_position,
    c.column_name,
    c.data_type,
    c.udt_name,
    c.character_maximum_length,
    c.numeric_precision,
    c.numeric_scale,
    c.is_nullable,
    c.column_default,
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM pg_constraint k
            JOIN pg_class t ON t.oid = k.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            JOIN pg_attribute a ON a.attrelid = t.oid
            WHERE n.nspname = c.table_schema
              AND t.relname = c.table_name
              AND a.attname = c.column_name
              AND k.contype = 'p'
              AND a.attnum = ANY(k.conkey)
        ) THEN 'YES' ELSE 'NO'
    END AS is_primary_key,
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM pg_constraint k
            JOIN pg_class t ON t.oid = k.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            JOIN pg_attribute a ON a.attrelid = t.oid
            WHERE n.nspname = c.table_schema
              AND t.relname = c.table_name
              AND a.attname = c.column_name
              AND k.contype = 'f'
              AND a.attnum = ANY(k.conkey)
        ) THEN 'YES' ELSE 'NO'
    END AS is_foreign_key
FROM information_schema.columns c
WHERE c.table_schema = 'dw'
ORDER BY c.table_name, c.ordinal_position;
