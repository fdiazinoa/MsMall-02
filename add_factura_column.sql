-- Script para agregar la columna factura_no a la tabla ventas

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='ventas' AND column_name='factura_no') THEN
        ALTER TABLE public.ventas ADD COLUMN factura_no TEXT;
    END IF;
END$$;
