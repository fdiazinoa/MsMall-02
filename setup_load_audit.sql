-- Add upsert_activo column to locales
ALTER TABLE locales ADD COLUMN IF NOT EXISTS upsert_activo BOOLEAN DEFAULT FALSE;

-- Create logs_carga table
CREATE TABLE IF NOT EXISTS logs_carga (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    fecha_hora TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    mall_id UUID,
    mall_nombre VARCHAR(255),
    local_id UUID,
    local_nombre VARCHAR(255),
    archivo VARCHAR(255),
    estado VARCHAR(50),
    canal VARCHAR(50),
    mensaje TEXT,
    batch_id TEXT,
    records_processed INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    detalles JSONB DEFAULT '[]'::jsonb,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Index for performance
CREATE INDEX IF NOT EXISTS idx_logs_carga_fecha ON logs_carga(fecha_hora);
CREATE INDEX IF NOT EXISTS idx_logs_carga_mall_fecha ON logs_carga(mall_id, fecha_hora DESC);
CREATE INDEX IF NOT EXISTS idx_logs_carga_local_fecha ON logs_carga(local_id, fecha_hora DESC);

-- Enable RLS
ALTER TABLE logs_carga ENABLE ROW LEVEL SECURITY;

-- Policies for logs_carga
DROP POLICY IF EXISTS "Permitir lectura a usuarios autenticados" ON logs_carga;
CREATE POLICY "Permitir lectura a usuarios autenticados" 
ON logs_carga FOR SELECT 
TO authenticated 
USING (true);

DROP POLICY IF EXISTS "Permitir inserción a usuarios autenticados" ON logs_carga;
CREATE POLICY "Permitir inserción a usuarios autenticados" 
ON logs_carga FOR INSERT 
TO authenticated 
WITH CHECK (true);

DROP POLICY IF EXISTS "Permitir borrado a usuarios autenticados" ON logs_carga;
CREATE POLICY "Permitir borrado a usuarios autenticados" 
ON logs_carga FOR DELETE 
TO authenticated 
USING (true);
