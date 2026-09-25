CREATE OR REPLACE FUNCTION public.audit_sales_summary(p_mall_id uuid, p_start date, p_end date, p_local_id uuid DEFAULT NULL)
RETURNS TABLE(local_id uuid, local_nombre text, mall_nombre text, total_bruto numeric, total_impuestos numeric, total_neto numeric)
LANGUAGE sql STABLE SECURITY INVOKER SET search_path = public
AS $$
  WITH amounts AS (
    SELECT v.local_id, coalesce(v.total_bruto,0)::numeric AS bruto,
      coalesce(v.total_impuestos,0)::numeric AS impuestos, coalesce(v.total_neto,0)::numeric AS neto
    FROM public.ventas v
    WHERE v.mall_id=p_mall_id AND v.fecha BETWEEN p_start AND p_end
      AND (p_local_id IS NULL OR v.local_id=p_local_id)
  ), normalized AS (
    SELECT a.*, abs(bruto-(neto+impuestos)) + 0.05 < abs(neto-(bruto+impuestos)) AS swapped
    FROM amounts a
  ), totals AS (
    SELECT n.local_id,
      sum(CASE WHEN swapped THEN neto ELSE bruto END) AS bruto,
      sum(impuestos) AS impuestos,
      sum(CASE WHEN swapped THEN bruto ELSE neto END) AS neto
    FROM normalized n GROUP BY n.local_id
  )
  SELECT l.id,l.nombre::text,m.nombre::text,coalesce(t.bruto,0),coalesce(t.impuestos,0),coalesce(t.neto,0)
  FROM public.locales l JOIN public.malls m ON m.id=l.mall_id
  LEFT JOIN totals t ON t.local_id=l.id
  WHERE l.mall_id=p_mall_id AND (p_local_id IS NULL OR l.id=p_local_id)
  ORDER BY l.nombre,l.id;
$$;
REVOKE ALL ON FUNCTION public.audit_sales_summary(uuid,date,date,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.audit_sales_summary(uuid,date,date,uuid) TO service_role;
NOTIFY pgrst, 'reload schema';
