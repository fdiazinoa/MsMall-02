
-- Create ENUMs for AI module
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tipo_alerta_ai') THEN
        CREATE TYPE public.tipo_alerta_ai AS ENUM ('BAJA_ANOMALA', 'TENDENCIA_NEGATIVA', 'COMPORTAMIENTO_ATIPICO');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'nivel_riesgo_ai') THEN
        CREATE TYPE public.nivel_riesgo_ai AS ENUM ('ALTO', 'MEDIO', 'BAJO');
    END IF;
END$$;

-- Create intelligent alerts table
CREATE TABLE IF NOT EXISTS public.alertas_inteligentes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    local_id UUID REFERENCES public.locales(id) ON DELETE CASCADE,
    fecha_detectada DATE DEFAULT CURRENT_DATE,
    tipo_alerta public.tipo_alerta_ai NOT NULL,
    nivel_riesgo public.nivel_riesgo_ai NOT NULL,
    mensaje TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Enable RLS
ALTER TABLE public.alertas_inteligentes ENABLE ROW LEVEL SECURITY;

-- Policies (Public for now to facilitate development/testing)
DROP POLICY IF EXISTS "Permitir todo a todos" ON public.alertas_inteligentes;
CREATE POLICY "Permitir todo a todos" 
ON public.alertas_inteligentes FOR ALL 
TO public 
USING (true)
WITH CHECK (true);

-- Index for performance
CREATE INDEX IF NOT EXISTS idx_alertas_local_fecha ON alertas_inteligentes(local_id, fecha_detectada);
