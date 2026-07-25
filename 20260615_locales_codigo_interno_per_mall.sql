-- Permite reutilizar codigo_interno entre malls distintos.
-- Antes: codigo_interno era UNIQUE global, lo que bloqueaba cargas multi-mall con codigos 1, 2, 3, etc.
-- Ahora: la unicidad correcta es por mall_id + codigo_interno.

DO $$
DECLARE
    constraint_name text;
BEGIN
    SELECT con.conname
    INTO constraint_name
    FROM pg_constraint con
    JOIN pg_class rel ON rel.oid = con.conrelid
    JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
    WHERE nsp.nspname = 'public'
      AND rel.relname = 'locales'
      AND con.contype = 'u'
      AND (
        SELECT array_agg(att.attname::text ORDER BY cols.ord)
        FROM unnest(con.conkey) WITH ORDINALITY AS cols(attnum, ord)
        JOIN pg_attribute att ON att.attrelid = rel.oid AND att.attnum = cols.attnum
      ) = ARRAY['codigo_interno']::text[];

    IF constraint_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE public.locales DROP CONSTRAINT %I', constraint_name);
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS locales_mall_codigo_interno_key
ON public.locales (mall_id, codigo_interno)
WHERE codigo_interno IS NOT NULL;
