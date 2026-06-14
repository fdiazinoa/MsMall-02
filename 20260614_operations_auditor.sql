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
  priority_score integer NOT NULL DEFAULT 50
    CHECK (priority_score >= 0 AND priority_score <= 100),
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

ALTER TABLE public.operational_findings
  ADD COLUMN IF NOT EXISTS priority_score integer NOT NULL DEFAULT 50;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'operational_findings_priority_score_check'
  ) THEN
    ALTER TABLE public.operational_findings
      ADD CONSTRAINT operational_findings_priority_score_check
      CHECK (priority_score >= 0 AND priority_score <= 100);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_operational_findings_priority
  ON public.operational_findings (mall_id, priority_score DESC, detected_at DESC);

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

CREATE TABLE IF NOT EXISTS public.operations_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  mall_id uuid NOT NULL REFERENCES public.malls(id) ON DELETE CASCADE,
  local_id uuid REFERENCES public.locales(id) ON DELETE SET NULL,
  event_type text NOT NULL,
  source text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  severity text NOT NULL DEFAULT 'INFO'
    CHECK (severity IN ('INFO', 'WARNING', 'HIGH', 'CRITICAL')),
  created_at timestamptz NOT NULL DEFAULT now(),
  processed_at timestamptz,
  processing_status text NOT NULL DEFAULT 'PENDING'
    CHECK (processing_status IN ('PENDING', 'PROCESSING', 'PROCESSED', 'FAILED')),
  processing_error text
);

CREATE INDEX IF NOT EXISTS idx_operations_events_pending
  ON public.operations_events (processing_status, created_at);

CREATE INDEX IF NOT EXISTS idx_operations_events_mall_type
  ON public.operations_events (mall_id, event_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_operations_events_local
  ON public.operations_events (local_id, created_at DESC);

CREATE TABLE IF NOT EXISTS public.operations_agent_observations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  mall_id uuid NOT NULL REFERENCES public.malls(id) ON DELETE CASCADE,
  local_id uuid REFERENCES public.locales(id) ON DELETE SET NULL,
  finding_id uuid REFERENCES public.operational_findings(id) ON DELETE SET NULL,
  event_id uuid REFERENCES public.operations_events(id) ON DELETE SET NULL,
  observation_type text NOT NULL,
  observation text NOT NULL,
  conclusion text,
  recommendation text,
  confidence numeric(5, 2) NOT NULL DEFAULT 0
    CHECK (confidence >= 0 AND confidence <= 1),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_operations_agent_observations_mall
  ON public.operations_agent_observations (mall_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_operations_agent_observations_type
  ON public.operations_agent_observations (mall_id, observation_type, created_at DESC);

CREATE TABLE IF NOT EXISTS public.operational_patterns (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  mall_id uuid NOT NULL REFERENCES public.malls(id) ON DELETE CASCADE,
  local_id uuid REFERENCES public.locales(id) ON DELETE SET NULL,
  pattern_type text NOT NULL,
  pattern_name text NOT NULL,
  description text,
  occurrences integer NOT NULL DEFAULT 1,
  first_seen timestamptz NOT NULL DEFAULT now(),
  last_seen timestamptz NOT NULL DEFAULT now(),
  confidence numeric(5, 2) NOT NULL DEFAULT 0
    CHECK (confidence >= 0 AND confidence <= 1),
  status text NOT NULL DEFAULT 'ACTIVE'
    CHECK (status IN ('ACTIVE', 'RESOLVED', 'IGNORED')),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (mall_id, local_id, pattern_type, pattern_name)
);

CREATE INDEX IF NOT EXISTS idx_operational_patterns_mall_active
  ON public.operational_patterns (mall_id, status, occurrences DESC, last_seen DESC);

CREATE INDEX IF NOT EXISTS idx_operational_patterns_local
  ON public.operational_patterns (local_id, last_seen DESC);
