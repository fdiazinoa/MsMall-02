-- Historical commercial classifications for Big Data.
-- This migration is additive. It runs only when a category maintenance record
-- changes; it never adds a trigger to public.ventas.

ALTER TABLE public.local_classification_history
  ADD COLUMN IF NOT EXISTS effective_from date NULL;

UPDATE public.local_classification_history
SET effective_from = changed_at::date
WHERE effective_from IS NULL;

CREATE INDEX IF NOT EXISTS idx_local_classification_history_effective
  ON public.local_classification_history(local_id, effective_from DESC, changed_at DESC);

-- Queue only the sale days whose category can change. The existing
-- (local_id, fecha) index keeps this bounded to a maintenance operation, not
-- to the high-volume sale ingestion trigger.
CREATE OR REPLACE FUNCTION public.enqueue_big_data_reclassification(
  p_local_id uuid,
  p_effective_from date
)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_mall_id uuid;
  v_start_date date := coalesce(p_effective_from, current_date);
  v_rows integer := 0;
BEGIN
  SELECT mall_id INTO v_mall_id FROM public.locales WHERE id = p_local_id;
  IF v_mall_id IS NULL
     OR NOT public.is_mall_feature_enabled(v_mall_id, 'BIG_DATA_CORE') THEN
    RETURN 0;
  END IF;

  INSERT INTO public.big_data_refresh_queue(mall_id, affected_date)
  SELECT v_mall_id, sale_day
  FROM (
    SELECT DISTINCT v.fecha::date AS sale_day
    FROM public.ventas v
    WHERE v.local_id = p_local_id
      AND v.fecha >= v_start_date
  ) affected_days
  ON CONFLICT (mall_id, affected_date) DO UPDATE
  SET status = 'pending', requested_at = now(), started_at = NULL,
      completed_at = NULL, last_error = NULL, claim_token = NULL;

  GET DIAGNOSTICS v_rows = ROW_COUNT;
  RETURN v_rows;
END;
$$;

REVOKE ALL ON FUNCTION public.enqueue_big_data_reclassification(uuid, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.enqueue_big_data_reclassification(uuid, date) TO service_role;

CREATE OR REPLACE FUNCTION public.maintain_local_classification_history()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_local_id uuid;
  v_previous_category uuid;
  v_category uuid;
  v_history_effective_from date;
  v_rebuild_start date;
BEGIN
  IF TG_OP = 'INSERT' THEN
    v_local_id := NEW.local_id;
    v_previous_category := NULL;
    v_category := NEW.category_id;
    v_history_effective_from := NEW.effective_from;
    v_rebuild_start := NEW.effective_from;
  ELSIF TG_OP = 'UPDATE' THEN
    IF NEW.category_id IS NOT DISTINCT FROM OLD.category_id
       AND NEW.effective_from IS NOT DISTINCT FROM OLD.effective_from THEN
      RETURN NEW;
    END IF;
    v_local_id := NEW.local_id;
    v_previous_category := OLD.category_id;
    v_category := NEW.category_id;
    v_history_effective_from := NEW.effective_from;
    v_rebuild_start := least(OLD.effective_from, NEW.effective_from);
  ELSE
    v_local_id := OLD.local_id;
    v_previous_category := OLD.category_id;
    v_category := NULL;
    v_history_effective_from := OLD.effective_from;
    v_rebuild_start := OLD.effective_from;
  END IF;

  -- Existing classifications predate this migration. Preserve their prior
  -- effective assignment once, so a later change does not retroactively move
  -- sale days before the new effective date into the rubro fallback.
  IF TG_OP IN ('UPDATE', 'DELETE') AND v_previous_category IS NOT NULL THEN
    INSERT INTO public.local_classification_history(
      local_id, previous_category_id, category_id, effective_from, changed_at, reason
    )
    SELECT v_local_id, NULL, v_previous_category,
      coalesce(OLD.effective_from, current_date), now(), 'classification_baseline'
    WHERE NOT EXISTS (
      SELECT 1
      FROM public.local_classification_history h
      WHERE h.local_id = v_local_id
        AND h.category_id IS NOT DISTINCT FROM v_previous_category
        AND h.effective_from = coalesce(OLD.effective_from, current_date)
    );
  END IF;

  INSERT INTO public.local_classification_history(
    local_id, previous_category_id, category_id, effective_from, changed_at, reason
  ) VALUES (
    v_local_id, v_previous_category, v_category,
    coalesce(v_history_effective_from, current_date), now(), 'classification_maintenance'
  );

  PERFORM public.enqueue_big_data_reclassification(
    v_local_id, coalesce(v_rebuild_start, current_date)
  );

  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION public.maintain_local_classification_history() FROM PUBLIC;

DROP TRIGGER IF EXISTS trg_maintain_local_classification_history
  ON public.local_commercial_classifications;
CREATE TRIGGER trg_maintain_local_classification_history
AFTER INSERT OR UPDATE OF category_id, effective_from OR DELETE
ON public.local_commercial_classifications
FOR EACH ROW EXECUTE FUNCTION public.maintain_local_classification_history();

-- Resolve exactly one category for each sale day. The latest classification
-- effective on that day wins; periods before the first historical assignment
-- keep the existing rubro fallback instead of being retroactively moved.
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
    SELECT v.fecha::date AS period_date, v.local_id,
      coalesce(history.category_id,
        CASE WHEN lcc.effective_from <= v.fecha THEN lcc.category_id END
      ) AS category_id,
      coalesce(history_category.name,
        CASE WHEN lcc.effective_from <= v.fecha THEN current_category.name END,
        nullif(l.rubro, ''), 'Sin clasificar'
      ) AS category_name,
      coalesce(history.category_id::text,
        CASE WHEN lcc.effective_from <= v.fecha THEN current_category.id::text END,
        'legacy:' || coalesce(nullif(l.rubro, ''), 'sin-clasificar')
      ) AS category_key,
      coalesce(v.total_neto, 0)::numeric AS sales_net,
      coalesce(v.total_bruto, 0)::numeric AS sales_gross,
      coalesce(v.total_impuestos, 0)::numeric AS taxes
    FROM public.ventas v
    JOIN public.locales l ON l.id = v.local_id
    LEFT JOIN public.local_commercial_classifications lcc ON lcc.local_id = l.id
    LEFT JOIN LATERAL (
      SELECT h.category_id
      FROM public.local_classification_history h
      WHERE h.local_id = l.id
        AND coalesce(h.effective_from, h.changed_at::date) <= v.fecha
      ORDER BY coalesce(h.effective_from, h.changed_at::date) DESC, h.changed_at DESC
      LIMIT 1
    ) history ON true
    LEFT JOIN public.commercial_taxonomy history_category ON history_category.id = history.category_id
    LEFT JOIN public.commercial_taxonomy current_category ON current_category.id = lcc.category_id
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
