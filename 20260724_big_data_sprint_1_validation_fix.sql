-- Validation correction for Big Data Sprint 1.
-- Safe to run after 20260724_big_data_sprint_1.sql.

ALTER TABLE public.big_data_refresh_queue
  ADD COLUMN IF NOT EXISTS claim_token uuid NULL;

CREATE INDEX IF NOT EXISTS idx_big_data_refresh_queue_claim
  ON public.big_data_refresh_queue(status, started_at)
  WHERE status = 'processing';

-- Claim rows atomically. A stalled worker can be retried after fifteen minutes;
-- SKIP LOCKED prevents two workers from receiving the same work.
CREATE OR REPLACE FUNCTION public.claim_big_data_refresh_queue(p_limit integer DEFAULT 50)
RETURNS TABLE(id uuid, mall_id uuid, affected_date date, attempts integer, claim_token uuid)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  RETURN QUERY
  WITH candidates AS (
    SELECT q.id FROM public.big_data_refresh_queue q
    WHERE q.status IN ('pending', 'failed')
       OR (q.status = 'processing' AND q.started_at < now() - interval '15 minutes')
    ORDER BY q.affected_date, q.requested_at
    LIMIT greatest(p_limit, 1)
    FOR UPDATE SKIP LOCKED
  )
  UPDATE public.big_data_refresh_queue q
  SET status = 'processing', attempts = q.attempts + 1, started_at = now(),
      claim_token = gen_random_uuid(), last_error = NULL
  FROM candidates c
  WHERE q.id = c.id
  RETURNING q.id, q.mall_id, q.affected_date, q.attempts, q.claim_token;
END;
$$;

-- Requeue both source and destination periods for corrections. Clearing the
-- claim token prevents a concurrent worker from completing newer pending work.
CREATE OR REPLACE FUNCTION public.enqueue_big_data_refresh()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  IF TG_OP = 'UPDATE'
     AND (OLD.mall_id IS DISTINCT FROM NEW.mall_id OR OLD.fecha IS DISTINCT FROM NEW.fecha) THEN
    IF OLD.mall_id IS NOT NULL AND OLD.fecha IS NOT NULL
       AND public.is_mall_feature_enabled(OLD.mall_id, 'BIG_DATA_CORE') THEN
      INSERT INTO public.big_data_refresh_queue(mall_id, affected_date)
      VALUES (OLD.mall_id, OLD.fecha)
      ON CONFLICT (mall_id, affected_date) DO UPDATE
      SET status = 'pending', requested_at = now(), last_error = NULL, claim_token = NULL;
    END IF;
  END IF;

  IF TG_OP = 'DELETE' THEN
    IF OLD.mall_id IS NOT NULL AND OLD.fecha IS NOT NULL
       AND public.is_mall_feature_enabled(OLD.mall_id, 'BIG_DATA_CORE') THEN
      INSERT INTO public.big_data_refresh_queue(mall_id, affected_date)
      VALUES (OLD.mall_id, OLD.fecha)
      ON CONFLICT (mall_id, affected_date) DO UPDATE
      SET status = 'pending', requested_at = now(), last_error = NULL, claim_token = NULL;
    END IF;
    RETURN OLD;
  END IF;

  IF NEW.mall_id IS NOT NULL AND NEW.fecha IS NOT NULL
     AND public.is_mall_feature_enabled(NEW.mall_id, 'BIG_DATA_CORE') THEN
    INSERT INTO public.big_data_refresh_queue(mall_id, affected_date)
    VALUES (NEW.mall_id, NEW.fecha)
    ON CONFLICT (mall_id, affected_date) DO UPDATE
    SET status = 'pending', requested_at = now(), last_error = NULL, claim_token = NULL;
  END IF;
  RETURN NEW;
END;
$$;

-- Do not delete a full month and rebuild only the corrected days. Every daily
-- row in each affected month must participate in its monthly total.
CREATE OR REPLACE FUNCTION public.refresh_big_data_aggregates(
  p_mall_id uuid, p_start_date date, p_end_date date, p_calculation_version text DEFAULT 'v1'
)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
  refreshed_records bigint := 0;
  affected_month_start date := date_trunc('month', p_start_date)::date;
  affected_month_end date := date_trunc('month', p_end_date)::date;
BEGIN
  IF p_start_date IS NULL OR p_end_date IS NULL OR p_start_date > p_end_date THEN
    RAISE EXCEPTION 'invalid refresh date range';
  END IF;

  DELETE FROM public.big_data_daily_aggregates
   WHERE mall_id = p_mall_id AND period_date BETWEEN p_start_date AND p_end_date;
  DELETE FROM public.big_data_monthly_aggregates
   WHERE mall_id = p_mall_id AND period_month BETWEEN affected_month_start AND affected_month_end;

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
  WHERE mall_id = p_mall_id
    AND period_date >= affected_month_start
    AND period_date < (affected_month_end + interval '1 month')::date
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
