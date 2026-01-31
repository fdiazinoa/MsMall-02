
-- NUCLEAR FIX: Recreate logs_carga table to ensure schema is correct
DROP TABLE IF EXISTS logs_carga;

CREATE TABLE logs_carga (
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
CREATE INDEX idx_logs_carga_fecha ON logs_carga(fecha_hora);

-- Enable RLS
ALTER TABLE logs_carga ENABLE ROW LEVEL SECURITY;

-- Policies for logs_carga (Public for now to avoid auth issues during testing)
DROP POLICY IF EXISTS "Permitir todo a todos" ON logs_carga;
CREATE POLICY "Permitir todo a todos" 
ON logs_carga FOR ALL 
TO public 
USING (true)
WITH CHECK (true);
