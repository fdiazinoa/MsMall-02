-- MsMall Big Data Sprint 2.
-- Additive migration. It does not enable any feature and does not modify Legacy
-- projections, ventas, importers or reports.

BEGIN;

-- Capabilities remain absent/false until explicitly enabled for an individual mall.
ALTER TABLE public.mall_feature_flags
  DROP CONSTRAINT IF EXISTS mall_feature_flags_key_chk;
ALTER TABLE public.mall_feature_flags
  ADD CONSTRAINT mall_feature_flags_key_chk CHECK (
    feature_key IN (
      'BIG_DATA_CORE',
      'BIG_DATA_BENCHMARK',
      'BIG_DATA_FORECAST',
      'BIG_DATA_OPERATIONS',
      'BIG_DATA_COPILOT'
    )
  );

-- Existing operational entities remain the official model. These columns add
-- concurrency, retry and user-attention metadata without creating parallel concepts.
ALTER TABLE IF EXISTS public.operations_events
  ADD COLUMN IF NOT EXISTS claim_token uuid,
  ADD COLUMN IF NOT EXISTS claimed_at timestamptz,
  ADD COLUMN IF NOT EXISTS attempts integer NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS fingerprint text;

ALTER TABLE IF EXISTS public.operational_findings
  ADD COLUMN IF NOT EXISTS reviewed_at timestamptz,
  ADD COLUMN IF NOT EXISTS reviewed_by uuid,
  ADD COLUMN IF NOT EXISTS resolved_by uuid,
  ADD COLUMN IF NOT EXISTS comments jsonb NOT NULL DEFAULT '[]'::jsonb;

-- The anomaly detector persists actionable findings using this source.  Keep the
-- existing Legacy origins and extend the closed list additively so a Sprint 2
-- run cannot fail after it has calculated a valid result.
ALTER TABLE IF EXISTS public.operational_findings
  DROP CONSTRAINT IF EXISTS operational_findings_source_check;
ALTER TABLE IF EXISTS public.operational_findings
  ADD CONSTRAINT operational_findings_source_check CHECK (
    source IN (
      'FTP',
      'SFTP',
      'WEBSERVICE',
      'WORKER',
      'SALES_AUDIT',
      'MISSING_DAYS',
      'BIG_DATA_ANOMALY'
    )
  );

CREATE UNIQUE INDEX IF NOT EXISTS uq_operational_findings_mall_fingerprint
  ON public.operational_findings(mall_id, fingerprint);

CREATE INDEX IF NOT EXISTS idx_operations_events_claimable
  ON public.operations_events(processing_status, created_at)
  WHERE processing_status IN ('PENDING', 'FAILED', 'PROCESSING');
CREATE UNIQUE INDEX IF NOT EXISTS uq_operations_events_mall_fingerprint
  ON public.operations_events(mall_id, fingerprint);

CREATE TABLE IF NOT EXISTS public.big_data_operations_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  mall_id uuid NULL REFERENCES public.malls(id) ON DELETE CASCADE,
  job_type text NOT NULL CHECK (
    job_type IN ('ANOMALY_DETECTION', 'OBSERVATION_GENERATION', 'PATTERN_UPDATE')
  ),
  period_start date NULL,
  period_end date NULL,
  status text NOT NULL CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
  attempts integer NOT NULL DEFAULT 1,
  items_generated integer NOT NULL DEFAULT 0,
  duration_ms integer NULL,
  error text NULL,
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz NULL
);
CREATE INDEX IF NOT EXISTS idx_big_data_operations_runs_mall_started
  ON public.big_data_operations_runs(mall_id, started_at DESC);

-- One database statement owns each event. PROCESSING rows older than the bounded
-- timeout are recoverable after a worker crash or deployment restart.
CREATE OR REPLACE FUNCTION public.claim_operations_events(
  p_limit integer DEFAULT 25,
  p_timeout_minutes integer DEFAULT 15
)
RETURNS SETOF public.operations_events
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  RETURN QUERY
  WITH candidates AS (
    SELECT event.id
    FROM public.operations_events event
    JOIN public.mall_feature_flags core
      ON core.mall_id = event.mall_id
     AND core.feature_key = 'BIG_DATA_CORE'
     AND core.enabled = true
    JOIN public.mall_feature_flags operations
      ON operations.mall_id = event.mall_id
     AND operations.feature_key = 'BIG_DATA_OPERATIONS'
     AND operations.enabled = true
    WHERE
      event.processing_status IN ('PENDING', 'FAILED')
      OR (
        event.processing_status = 'PROCESSING'
        AND event.claimed_at < now() - make_interval(mins => greatest(1, least(p_timeout_minutes, 120)))
      )
    ORDER BY
      CASE event.severity
        WHEN 'CRITICAL' THEN 0
        WHEN 'HIGH' THEN 1
        WHEN 'WARNING' THEN 2
        ELSE 3
      END,
      event.created_at
    FOR UPDATE OF event SKIP LOCKED
    LIMIT greatest(1, least(p_limit, 100))
  )
  UPDATE public.operations_events event
  SET processing_status = 'PROCESSING',
      claim_token = gen_random_uuid(),
      claimed_at = now(),
      attempts = coalesce(event.attempts, 0) + 1,
      processing_error = NULL
  FROM candidates
  WHERE event.id = candidates.id
  RETURNING event.*;
END;
$$;

REVOKE ALL ON FUNCTION public.claim_operations_events(integer, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.claim_operations_events(integer, integer) FROM anon;
REVOKE ALL ON FUNCTION public.claim_operations_events(integer, integer) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.claim_operations_events(integer, integer) TO service_role;

-- Direct client access is not required; authenticated API contracts apply mall
-- authorization and feature checks. The service role is the only worker writer.
ALTER TABLE public.big_data_operations_runs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.big_data_operations_runs FROM anon, authenticated;
GRANT ALL ON public.big_data_operations_runs TO service_role;

COMMENT ON TABLE public.operations_events IS
  'Immutable operational facts; processing metadata records consumer state.';
COMMENT ON TABLE public.operational_findings IS
  'Actionable and idempotent conditions identified by mall-scoped fingerprint.';
COMMENT ON TABLE public.operations_agent_observations IS
  'Deterministic explanations derived from events or findings.';
COMMENT ON TABLE public.operational_patterns IS
  'Historically recurring behavior, not an individual alert.';
COMMENT ON TABLE public.alertas_inteligentes IS
  'Legacy presentation/notification channel; not the source of operational findings.';
COMMENT ON TABLE public.big_data_operations_runs IS
  'Execution telemetry for deferred Big Data operational jobs.';

COMMIT;
