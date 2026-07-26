-- Dashboard BI v2: aggregate the complete dashboard contract in one database call.
-- The function remains internal to the Railway backend (service_role only).

create or replace function public.get_dashboard_kpis_v2(
  p_mall_id uuid,
  p_start_date date,
  p_end_date date
)
returns jsonb
language sql
stable
security invoker
set search_path = ''
as $function$
with allowed_locales as (
  select
    l.id,
    coalesce(nullif(btrim(l.nombre), ''), 'Local sin nombre') as local_name,
    coalesce(nullif(btrim(l.tipo_negocio), ''), 'Sin tipo de negocio') as business_type,
    coalesce(nullif(btrim(l.rubro), ''), 'Sin rubro') as rubro
  from public.locales l
  where l.mall_id = p_mall_id
),
filtered_sales as materialized (
  select
    al.id as local_id,
    al.local_name,
    al.business_type,
    al.rubro,
    v.fecha,
    coalesce(v.total_bruto, 0)::numeric as total_bruto,
    coalesce(v.total_neto, 0)::numeric as total_neto
  from allowed_locales al
  join public.ventas v on v.local_id = al.id
  where v.fecha between p_start_date and p_end_date
),
store_dimension_totals as (
  select
    fs.local_id,
    fs.local_name,
    fs.business_type,
    fs.rubro,
    sum(fs.total_bruto) as total_bruto,
    sum(fs.total_neto) as total_neto,
    count(*)::bigint as transactions
  from filtered_sales fs
  group by fs.local_id, fs.local_name, fs.business_type, fs.rubro
),
store_name_totals as (
  select
    sdt.local_name,
    sum(sdt.total_bruto) as total_bruto,
    sum(sdt.total_neto) as total_neto,
    sum(sdt.transactions)::bigint as transactions
  from store_dimension_totals sdt
  group by sdt.local_name
),
day_totals as (
  select
    fs.fecha,
    sum(fs.total_bruto) as total_bruto
  from filtered_sales fs
  group by fs.fecha
),
business_store_totals as (
  select
    sdt.business_type as segment,
    sdt.local_name,
    sum(sdt.total_bruto) as total_bruto,
    sum(sdt.total_neto) as total_neto,
    sum(sdt.transactions)::bigint as transactions
  from store_dimension_totals sdt
  group by sdt.business_type, sdt.local_name
),
business_ranked as (
  select
    bst.*,
    sum(bst.total_bruto) over (partition by bst.segment) as segment_total,
    row_number() over (
      partition by bst.segment
      order by bst.total_bruto desc, bst.local_name
    ) as position
  from business_store_totals bst
),
business_segments as (
  select
    br.segment,
    max(br.segment_total) as total_bruto,
    jsonb_agg(
      jsonb_build_object(
        'name', br.local_name,
        'total', br.total_bruto,
        'total_neto', br.total_neto,
        'transacciones', br.transactions,
        'ticket_promedio', case when br.transactions > 0 then br.total_bruto / br.transactions else 0 end,
        'participacion', case when br.segment_total > 0 then br.total_bruto * 100 / br.segment_total else 0 end
      )
      order by br.total_bruto desc, br.local_name
    ) filter (where br.position <= 10) as top_stores
  from business_ranked br
  group by br.segment
),
rubro_store_totals as (
  select
    sdt.rubro as segment,
    sdt.local_name,
    sum(sdt.total_bruto) as total_bruto,
    sum(sdt.total_neto) as total_neto,
    sum(sdt.transactions)::bigint as transactions
  from store_dimension_totals sdt
  group by sdt.rubro, sdt.local_name
),
rubro_ranked as (
  select
    rst.*,
    sum(rst.total_bruto) over (partition by rst.segment) as segment_total,
    row_number() over (
      partition by rst.segment
      order by rst.total_bruto desc, rst.local_name
    ) as position
  from rubro_store_totals rst
),
rubro_segments as (
  select
    rr.segment,
    max(rr.segment_total) as total_bruto,
    jsonb_agg(
      jsonb_build_object(
        'name', rr.local_name,
        'total', rr.total_bruto,
        'total_neto', rr.total_neto,
        'transacciones', rr.transactions,
        'ticket_promedio', case when rr.transactions > 0 then rr.total_bruto / rr.transactions else 0 end,
        'participacion', case when rr.segment_total > 0 then rr.total_bruto * 100 / rr.segment_total else 0 end
      )
      order by rr.total_bruto desc, rr.local_name
    ) filter (where rr.position <= 10) as top_stores
  from rubro_ranked rr
  group by rr.segment
),
kpis as (
  select
    coalesce(sum(snt.total_bruto), 0) as total_bruto,
    coalesce(sum(snt.total_neto), 0) as total_neto,
    coalesce(sum(snt.transactions), 0)::bigint as transactions
  from store_name_totals snt
)
select jsonb_build_object(
  'ventas_totales_bruto', k.total_bruto,
  'ventas_totales_neto', k.total_neto,
  'transacciones', k.transactions,
  'ticket_promedio', case when k.transactions > 0 then k.total_bruto / k.transactions else 0 end,
  'variacion_ventas', 0,
  'top_locales', coalesce((
    select jsonb_agg(
      jsonb_build_object('name', ranked.local_name, 'total', ranked.total_bruto)
      order by ranked.total_bruto desc, ranked.local_name
    )
    from (
      select snt.local_name, snt.total_bruto
      from store_name_totals snt
      order by snt.total_bruto desc, snt.local_name
      limit 5
    ) ranked
  ), '[]'::jsonb),
  'ventas_por_dia', coalesce((
    select jsonb_agg(
      jsonb_build_object('fecha', to_char(dt.fecha, 'YYYY-MM-DD'), 'total', dt.total_bruto)
      order by dt.fecha
    )
    from day_totals dt
  ), '[]'::jsonb),
  'ventas_por_tipo_negocio', coalesce((
    select jsonb_agg(
      jsonb_build_object('name', bs.segment, 'value', bs.total_bruto)
      order by bs.total_bruto desc, bs.segment
    )
    from business_segments bs
  ), '[]'::jsonb),
  'ventas_por_rubro', coalesce((
    select jsonb_agg(
      jsonb_build_object('name', rs.segment, 'value', rs.total_bruto)
      order by rs.total_bruto desc, rs.segment
    )
    from rubro_segments rs
  ), '[]'::jsonb),
  'ventas_por_tipo_negocio_top_locales', coalesce((
    select jsonb_object_agg(bs.segment, bs.top_stores)
    from business_segments bs
  ), '{}'::jsonb),
  'ventas_por_rubro_top_locales', coalesce((
    select jsonb_object_agg(rs.segment, rs.top_stores)
    from rubro_segments rs
  ), '{}'::jsonb),
  'ventas_por_tienda_completo', coalesce((
    select jsonb_object_agg(snt.local_name, snt.total_bruto)
    from store_name_totals snt
  ), '{}'::jsonb)
)
from kpis k;
$function$;

revoke all on function public.get_dashboard_kpis_v2(uuid, date, date) from public;
revoke all on function public.get_dashboard_kpis_v2(uuid, date, date) from anon;
revoke all on function public.get_dashboard_kpis_v2(uuid, date, date) from authenticated;
grant execute on function public.get_dashboard_kpis_v2(uuid, date, date) to service_role;

comment on function public.get_dashboard_kpis_v2(uuid, date, date) is
  'Returns the complete Dashboard BI payload in one aggregate query for the Railway backend.';
