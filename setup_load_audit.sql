-- Add upsert_activo column to locales
ALTER TABLE locales ADD COLUMN IF NOT EXISTS upsert_activo BOOLEAN DEFAULT FALSE;

-- Create logs_carga table
CREATE TABLE IF NOT EXISTS logs_carga (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    fecha_hora TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    local_nombre VARCHAR(255),
    archivo VARCHAR(255),
    estado VARCHAR(50),
    mensaje TEXT,
    batch_id UUID,
    detalles JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Index for performance
CREATE INDEX IF NOT EXISTS idx_logs_carga_fecha ON logs_carga(fecha_hora);

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
