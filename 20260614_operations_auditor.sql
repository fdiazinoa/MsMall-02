CREATE TABLE IF NOT EXISTS public.operational_findings (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  mall_id uuid NOT NULL REFERENCES public.malls(id) ON DELETE CASCADE,
  local_id uuid REFERENCES public.locales(id) ON DELETE SET NULL,
  local_name text,
  type text NOT NULL,
  severity text NOT NULL DEFAULT 'INFO'
    CHECK (severity IN ('INFO', 'WARNING', 'HIGH', 'CRITICAL')),
  title text NOT NULL,
  description text NOT NULL,
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  root_cause text,
  recommendation text,
  confidence numeric(5, 2) NOT NULL DEFAULT 0
    CHECK (confidence >= 0 AND confidence <= 1),
  status text NOT NULL DEFAULT 'OPEN'
    CHECK (status IN ('OPEN', 'ACKNOWLEDGED', 'RESOLVED', 'IGNORED')),
  source text NOT NULL
    CHECK (source IN ('FTP', 'SFTP', 'WEBSERVICE', 'WORKER', 'SALES_AUDIT', 'MISSING_DAYS')),
  detected_at timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz,
  assigned_to text,
  notified_to text[],
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  fingerprint text NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (mall_id, fingerprint)
);

CREATE INDEX IF NOT EXISTS idx_operational_findings_mall_status
  ON public.operational_findings (mall_id, status, detected_at DESC);

CREATE INDEX IF NOT EXISTS idx_operational_findings_mall_severity
  ON public.operational_findings (mall_id, severity, detected_at DESC);

CREATE INDEX IF NOT EXISTS idx_operational_findings_local
  ON public.operational_findings (local_id, detected_at DESC);

CREATE INDEX IF NOT EXISTS idx_operational_findings_source
  ON public.operational_findings (mall_id, source, detected_at DESC);

CREATE TABLE IF NOT EXISTS public.operations_auditor_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  mall_id uuid NOT NULL REFERENCES public.malls(id) ON DELETE CASCADE,
  status text NOT NULL DEFAULT 'completed'
    CHECK (status IN ('running', 'completed', 'completed_with_errors', 'failed')),
  started_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  duration_ms integer NOT NULL DEFAULT 0,
  findings_created integer NOT NULL DEFAULT 0,
  findings_updated integer NOT NULL DEFAULT 0,
  errors jsonb NOT NULL DEFAULT '[]'::jsonb,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by text
);

CREATE INDEX IF NOT EXISTS idx_operations_auditor_runs_mall_started
  ON public.operations_auditor_runs (mall_id, started_at DESC);
