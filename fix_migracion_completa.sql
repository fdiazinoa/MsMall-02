-- COSOLIDATED MIGRATION SCRIPT FOR WORKER FEATURES
-- Run this to ensure all columns and tables exist for the import worker.

-- 1. Create system_health table (Heartbeat)
CREATE TABLE IF NOT EXISTS public.system_health (
    key TEXT PRIMARY KEY,
    value TEXT,
    last_update TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);

-- 2. Add columns to 'locales' for Concurrency & Circuit Breaker
DO $$
BEGIN
    -- Add processing_status
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='locales' AND column_name='processing_status') THEN
        ALTER TABLE public.locales ADD COLUMN processing_status TEXT DEFAULT 'IDLE';
    END IF;

    -- Add processing_started_at
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='locales' AND column_name='processing_started_at') THEN
        ALTER TABLE public.locales ADD COLUMN processing_started_at TEXT;
    END IF;

    -- Add consecutive_failures
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='locales' AND column_name='consecutive_failures') THEN
        ALTER TABLE public.locales ADD COLUMN consecutive_failures INTEGER DEFAULT 0;
    END IF;
END $$;

-- 3. Update NULL statuses to 'IDLE' to ensure they are picked up by the worker
UPDATE public.locales 
SET processing_status = 'IDLE' 
WHERE processing_status IS NULL;

-- 4. Enable RLS on system_health (Optional, mostly for safety)
ALTER TABLE public.system_health ENABLE ROW LEVEL SECURITY;

-- 5. Open access policy for system_health (since worker uses Service Role, but frontend needs read)
DROP POLICY IF EXISTS "Public Read Health" ON public.system_health;
CREATE POLICY "Public Read Health" ON public.system_health FOR SELECT USING (true);

-- 6. Grant permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON public.system_health TO anon, authenticated, service_role;
