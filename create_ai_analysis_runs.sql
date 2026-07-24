CREATE TABLE IF NOT EXISTS public.ai_analysis_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    local_id UUID NOT NULL REFERENCES public.locales(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    risk_state TEXT NOT NULL,
    risk_score INTEGER NOT NULL DEFAULT 0,
    alerts_count INTEGER NOT NULL DEFAULT 0,
    trigger_source TEXT NOT NULL DEFAULT 'manual',
    detail TEXT,
    run_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

ALTER TABLE public.ai_analysis_runs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Permitir todo a todos" ON public.ai_analysis_runs;
CREATE POLICY "Permitir todo a todos"
ON public.ai_analysis_runs FOR ALL
TO public
USING (true)
WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_ai_analysis_runs_local_run_at
ON public.ai_analysis_runs (local_id, run_at DESC);
