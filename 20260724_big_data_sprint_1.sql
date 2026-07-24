-- MsMall Big Data Sprint 1. Additive only: legacy malls, locales and ventas stay intact.
-- Deploy with all feature flags disabled. Enable BIG_DATA_CORE per mall when ready.

CREATE TABLE IF NOT EXISTS public.mall_feature_flags (
  mall_id uuid NOT NULL REFERENCES public.malls(id) ON DELETE CASCADE,
  feature_key text NOT NULL,
  enabled boolean NOT NULL DEFAULT false,
  config jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by uuid NULL,
  PRIMARY KEY (mall_id, feature_key),
  CONSTRAINT mall_feature_flags_key_chk CHECK (feature_key IN ('BIG_DATA_CORE', 'BIG_DATA_BENCHMARK', 'BIG_DATA_FORECAST', 'BIG_DATA_COPILOT'))
);

CREATE TABLE IF NOT EXISTS public.big_data_access_audit (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NULL,
  mall_id uuid NULL,
  allowed boolean NOT NULL,
  reason text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- The function is intentionally explicit about the current user. Backend service-role
-- endpoints pass the authenticated user id, so it also works without changing legacy RLS.
CREATE OR REPLACE FUNCTION public.validate_mall_access(current_user uuid, requested_mall_id uuid)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  allowed boolean := false;
  role_name text;
BEGIN
  SELECT lower(coalesce(role::text, '')) INTO role_name FROM public.profiles WHERE id = current_user;
  IF role_name IN ('admin', 'administrador', 'superadmin', 'super_admin') THEN
    allowed := true;
  ELSE
    SELECT EXISTS (
      SELECT 1 FROM public.usuarios_malls um
      WHERE um.usuario_id = current_user AND um.mall_id = requested_mall_id
    ) INTO allowed;
  END IF;

  INSERT INTO public.big_data_access_audit(user_id, mall_id, allowed, reason)
  VALUES (current_user, requested_mall_id, allowed,
    CASE WHEN allowed THEN 'authorized' ELSE 'mall_not_assigned' END);
  RETURN allowed;
END;
$$;

CREATE OR REPLACE FUNCTION public.is_mall_feature_enabled(requested_mall_id uuid, requested_feature text)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT coalesce((
    SELECT enabled FROM public.mall_feature_flags
    WHERE mall_id = requested_mall_id AND feature_key = requested_feature
  ), false);
$$;

CREATE TABLE IF NOT EXISTS public.commercial_taxonomy (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  mall_id uuid NOT NULL REFERENCES public.malls(id) ON DELETE CASCADE,
  parent_id uuid NULL REFERENCES public.commercial_taxonomy(id),
  level text NOT NULL CHECK (level IN ('sector', 'category', 'subcategory')),
  code text NOT NULL,
  name text NOT NULL,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (mall_id, code)
);
CREATE INDEX IF NOT EXISTS idx_commercial_taxonomy_mall_parent ON public.commercial_taxonomy(mall_id, parent_id, active);

CREATE TABLE IF NOT EXISTS public.local_commercial_classifications (
  local_id uuid PRIMARY KEY REFERENCES public.locales(id) ON DELETE CASCADE,
  sector_id uuid NULL REFERENCES public.commercial_taxonomy(id),
  category_id uuid NULL REFERENCES public.commercial_taxonomy(id),
  subcategory_id uuid NULL REFERENCES public.commercial_taxonomy(id),
  source text NOT NULL DEFAULT 'manual',
  effective_from date NOT NULL DEFAULT current_date,
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by uuid NULL
);

CREATE TABLE IF NOT EXISTS public.local_classification_history (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  local_id uuid NOT NULL REFERENCES public.locales(id) ON DELETE CASCADE,
  previous_category_id uuid NULL,
  category_id uuid NULL,
  changed_at timestamptz NOT NULL DEFAULT now(),
  changed_by uuid NULL,
  reason text NULL
);

CREATE TABLE IF NOT EXISTS public.big_data_refresh_queue (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  mall_id uuid NOT NULL REFERENCES public.malls(id) ON DELETE CASCADE,
  affected_date date NOT NULL,
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
  attempts integer NOT NULL DEFAULT 0,
  requested_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz NULL,
  completed_at timestamptz NULL,
  last_error text NULL,
  requested_by uuid NULL,
  UNIQUE (mall_id, affected_date)
);
CREATE INDEX IF NOT EXISTS idx_big_data_refresh_queue_pending ON public.big_data_refresh_queue(status, requested_at) WHERE status IN ('pending', 'failed');

CREATE TABLE IF NOT EXISTS public.big_data_watermarks (
  mall_id uuid PRIMARY KEY REFERENCES public.malls(id) ON DELETE CASCADE,
  last_processed_sale_date date NULL,
  last_successful_refresh_at timestamptz NULL,
  calculation_version text NOT NULL DEFAULT 'v1',
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.big_data_refresh_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  mall_id uuid NOT NULL REFERENCES public.malls(id) ON DELETE CASCADE,
  start_date date NOT NULL,
  end_date date NOT NULL,
  status text NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
  calculation_version text NOT NULL DEFAULT 'v1',
  records_processed bigint NOT NULL DEFAULT 0,
  duration_ms integer NULL,
  error text NULL,
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz NULL
);

CREATE TABLE IF NOT EXISTS public.big_data_daily_aggregates (
  mall_id uuid NOT NULL REFERENCES public.malls(id) ON DELETE CASCADE,
  period_date date NOT NULL,
  grain text NOT NULL CHECK (grain IN ('mall', 'local', 'category')),
  dimension_key text NOT NULL,
  local_id uuid NULL REFERENCES public.locales(id) ON DELETE CASCADE,
  category_id uuid NULL REFERENCES public.commercial_taxonomy(id) ON DELETE SET NULL,
  category_name text NULL,
  sales_net numeric(18,2) NOT NULL DEFAULT 0,
  sales_gross numeric(18,2) NOT NULL DEFAULT 0,
  taxes numeric(18,2) NOT NULL DEFAULT 0,
  transaction_count bigint NOT NULL DEFAULT 0,
  records_processed bigint NOT NULL DEFAULT 0,
  coverage_status text NOT NULL DEFAULT 'complete' CHECK (coverage_status IN ('complete', 'incomplete')),
  calculation_version text NOT NULL DEFAULT 'v1',
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (mall_id, period_date, grain, dimension_key)
);
CREATE INDEX IF NOT EXISTS idx_big_data_daily_mall_date ON public.big_data_daily_aggregates(mall_id, period_date, grain);
CREATE INDEX IF NOT EXISTS idx_big_data_daily_category_date ON public.big_data_daily_aggregates(mall_id, category_id, period_date) WHERE grain = 'category';

CREATE TABLE IF NOT EXISTS public.big_data_monthly_aggregates (
  mall_id uuid NOT NULL REFERENCES public.malls(id) ON DELETE CASCADE,
  period_month date NOT NULL,
  grain text NOT NULL CHECK (grain IN ('mall', 'local', 'category')),
  dimension_key text NOT NULL,
  local_id uuid NULL REFERENCES public.locales(id) ON DELETE CASCADE,
  category_id uuid NULL REFERENCES public.commercial_taxonomy(id) ON DELETE SET NULL,
  category_name text NULL,
  sales_net numeric(18,2) NOT NULL DEFAULT 0,
  sales_gross numeric(18,2) NOT NULL DEFAULT 0,
  taxes numeric(18,2) NOT NULL DEFAULT 0,
  transaction_count bigint NOT NULL DEFAULT 0,
  records_processed bigint NOT NULL DEFAULT 0,
  coverage_status text NOT NULL DEFAULT 'complete' CHECK (coverage_status IN ('complete', 'incomplete')),
  calculation_version text NOT NULL DEFAULT 'v1',
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (mall_id, period_month, grain, dimension_key)
);
CREATE INDEX IF NOT EXISTS idx_big_data_monthly_mall_period ON public.big_data_monthly_aggregates(mall_id, period_month, grain);

CREATE OR REPLACE FUNCTION public.enqueue_big_data_refresh()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
  changed_mall uuid := coalesce(NEW.mall_id, OLD.mall_id);
  changed_date date := coalesce(NEW.fecha, OLD.fecha);
BEGIN
  IF changed_mall IS NOT NULL AND changed_date IS NOT NULL
     AND public.is_mall_feature_enabled(changed_mall, 'BIG_DATA_CORE') THEN
    INSERT INTO public.big_data_refresh_queue(mall_id, affected_date)
    VALUES (changed_mall, changed_date)
    ON CONFLICT (mall_id, affected_date) DO UPDATE
      SET status = 'pending', requested_at = now(), last_error = NULL;
  END IF;
  RETURN coalesce(NEW, OLD);
END;
$$;

DROP TRIGGER IF EXISTS trg_enqueue_big_data_refresh ON public.ventas;
CREATE TRIGGER trg_enqueue_big_data_refresh
AFTER INSERT OR UPDATE OF total_neto, total_bruto, total_impuestos, fecha, local_id, mall_id OR DELETE ON public.ventas
FOR EACH ROW EXECUTE FUNCTION public.enqueue_big_data_refresh();

CREATE OR REPLACE FUNCTION public.refresh_big_data_aggregates(
  p_mall_id uuid, p_start_date date, p_end_date date, p_calculation_version text DEFAULT 'v1'
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  refreshed_records bigint := 0;
BEGIN
  IF p_start_date IS NULL OR p_end_date IS NULL OR p_start_date > p_end_date THEN
    RAISE EXCEPTION 'invalid refresh date range';
  END IF;

  DELETE FROM public.big_data_daily_aggregates
   WHERE mall_id = p_mall_id AND period_date BETWEEN p_start_date AND p_end_date;
  DELETE FROM public.big_data_monthly_aggregates
   WHERE mall_id = p_mall_id
     AND period_month BETWEEN date_trunc('month', p_start_date)::date AND date_trunc('month', p_end_date)::date;

  WITH base AS (
    SELECT v.fecha::date AS period_date, v.local_id, lcc.category_id,
      coalesce(ct.name, nullif(l.rubro, ''), 'Sin clasificar') AS category_name,
      coalesce(ct.id::text, 'legacy:' || coalesce(nullif(l.rubro, ''), 'sin-clasificar')) AS category_key,
      coalesce(v.total_neto, 0)::numeric AS sales_net,
      coalesce(v.total_bruto, 0)::numeric AS sales_gross,
      coalesce(v.total_impuestos, 0)::numeric AS taxes
    FROM public.ventas v
    JOIN public.locales l ON l.id = v.local_id
    LEFT JOIN public.local_commercial_classifications lcc ON lcc.local_id = l.id
    LEFT JOIN public.commercial_taxonomy ct ON ct.id = lcc.category_id
    WHERE l.mall_id = p_mall_id AND v.fecha BETWEEN p_start_date AND p_end_date
  ), rows AS (
    SELECT p_mall_id mall_id, period_date, 'mall'::text grain, 'mall'::text dimension_key,
      NULL::uuid local_id, NULL::uuid category_id, NULL::text category_name,
      sum(sales_net) sales_net, sum(sales_gross) sales_gross, sum(taxes) taxes, count(*) transaction_count, count(*) records_processed FROM base GROUP BY period_date
    UNION ALL
    SELECT p_mall_id, period_date, 'local', local_id::text, local_id, NULL, NULL,
      sum(sales_net), sum(sales_gross), sum(taxes), count(*), count(*) FROM base GROUP BY period_date, local_id
    UNION ALL
    SELECT p_mall_id, period_date, 'category', category_key, NULL, category_id, category_name,
      sum(sales_net), sum(sales_gross), sum(taxes), count(*), count(*) FROM base GROUP BY period_date, category_key, category_id, category_name
  )
  INSERT INTO public.big_data_daily_aggregates(
    mall_id, period_date, grain, dimension_key, local_id, category_id, category_name,
    sales_net, sales_gross, taxes, transaction_count, records_processed, calculation_version, updated_at
  )
  SELECT mall_id, period_date, grain, dimension_key, local_id, category_id, category_name,
    sales_net, sales_gross, taxes, transaction_count, records_processed, p_calculation_version, now()
  FROM rows;
  GET DIAGNOSTICS refreshed_records = ROW_COUNT;

  INSERT INTO public.big_data_monthly_aggregates(
    mall_id, period_month, grain, dimension_key, local_id, category_id, category_name,
    sales_net, sales_gross, taxes, transaction_count, records_processed, calculation_version, updated_at
  )
  SELECT mall_id, date_trunc('month', period_date)::date, grain, dimension_key,
    (array_agg(local_id))[1], (array_agg(category_id))[1], max(category_name),
    sum(sales_net), sum(sales_gross), sum(taxes), sum(transaction_count), sum(records_processed), p_calculation_version, now()
  FROM public.big_data_daily_aggregates
  WHERE mall_id = p_mall_id AND period_date BETWEEN p_start_date AND p_end_date
  GROUP BY mall_id, date_trunc('month', period_date)::date, grain, dimension_key;

  INSERT INTO public.big_data_watermarks(mall_id, last_processed_sale_date, last_successful_refresh_at, calculation_version, updated_at)
  VALUES (p_mall_id, p_end_date, now(), p_calculation_version, now())
  ON CONFLICT (mall_id) DO UPDATE SET
    last_processed_sale_date = greatest(coalesce(big_data_watermarks.last_processed_sale_date, excluded.last_processed_sale_date), excluded.last_processed_sale_date),
    last_successful_refresh_at = excluded.last_successful_refresh_at,
    calculation_version = excluded.calculation_version,
    updated_at = excluded.updated_at;

  RETURN jsonb_build_object('mall_id', p_mall_id, 'start_date', p_start_date, 'end_date', p_end_date, 'records_processed', refreshed_records);
END;
$$;

-- Read-only aggregate contracts used by the API. They never scan public.ventas.
CREATE OR REPLACE FUNCTION public.big_data_mall_summary(p_mall_id uuid, p_start_date date, p_end_date date)
RETURNS TABLE(sales_net numeric, sales_gross numeric, taxes numeric, transactions bigint, ticket_average numeric, updated_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT coalesce(sum(sales_net),0), coalesce(sum(sales_gross),0), coalesce(sum(taxes),0), coalesce(sum(transaction_count),0),
    case when coalesce(sum(transaction_count),0) > 0 then sum(sales_net)/sum(transaction_count) else 0 end, max(updated_at)
  FROM public.big_data_daily_aggregates
  WHERE mall_id=p_mall_id AND grain='mall' AND period_date BETWEEN p_start_date AND p_end_date;
$$;

CREATE OR REPLACE FUNCTION public.big_data_daily_evolution(p_mall_id uuid, p_start_date date, p_end_date date)
RETURNS TABLE(period_date date, sales_net numeric, transactions bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT period_date, sales_net, transaction_count FROM public.big_data_daily_aggregates
  WHERE mall_id=p_mall_id AND grain='mall' AND period_date BETWEEN p_start_date AND p_end_date ORDER BY period_date;
$$;

CREATE OR REPLACE FUNCTION public.big_data_category_distribution(p_mall_id uuid, p_start_date date, p_end_date date)
RETURNS TABLE(category_id uuid, category_name text, sales_net numeric, transactions bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT category_id, max(category_name), sum(sales_net), sum(transaction_count)
  FROM public.big_data_daily_aggregates
  WHERE mall_id=p_mall_id AND grain='category' AND period_date BETWEEN p_start_date AND p_end_date
  GROUP BY category_id, dimension_key ORDER BY sum(sales_net) DESC;
$$;
