
-- NUCLEAR FIX: Recreate logs_carga table to ensure schema is correct
DROP TABLE IF EXISTS logs_carga;

CREATE TABLE logs_carga (
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
CREATE INDEX idx_logs_carga_fecha ON logs_carga(fecha_hora);
CREATE INDEX idx_logs_carga_mall_fecha ON logs_carga(mall_id, fecha_hora DESC);
CREATE INDEX idx_logs_carga_local_fecha ON logs_carga(local_id, fecha_hora DESC);

-- Enable RLS
ALTER TABLE logs_carga ENABLE ROW LEVEL SECURITY;

-- Policies for logs_carga (Public for now to avoid auth issues during testing)
DROP POLICY IF EXISTS "Permitir todo a todos" ON logs_carga;
CREATE POLICY "Permitir todo a todos" 
ON logs_carga FOR ALL 
TO public 
USING (true)
WITH CHECK (true);
