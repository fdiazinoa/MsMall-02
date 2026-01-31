
-- Add detalles column to logs_carga to store line-level errors
ALTER TABLE logs_carga ADD COLUMN IF NOT EXISTS detalles JSONB DEFAULT '[]'::jsonb;
