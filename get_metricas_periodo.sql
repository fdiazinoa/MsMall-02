-- Function to get metrics for a specific period grouped by store
CREATE OR REPLACE FUNCTION public.get_metricas_periodo(
    mall_id_param UUID,
    fecha_inicio_param DATE,
    fecha_fin_param DATE
)
RETURNS TABLE (
    local_id UUID,
    local_nombre TEXT,
    rubro TEXT,
    total_neto NUMERIC,
    total_bruto NUMERIC,
    transacciones BIGINT,
    ticket_promedio NUMERIC
) 
LANGUAGE sql
STABLE
SECURITY INVOKER
AS $$
    SELECT 
        l.id as local_id,
        l.nombre as local_nombre,
        l.rubro,
        COALESCE(SUM(v.total_neto), 0)::NUMERIC as total_neto,
        COALESCE(SUM(v.total_bruto), 0)::NUMERIC as total_bruto,
        COUNT(v.id)::BIGINT as transacciones,
        CASE 
            WHEN COUNT(v.id) > 0 THEN (SUM(v.total_neto) / COUNT(v.id))::NUMERIC 
            ELSE 0 
        END as ticket_promedio
    FROM public.locales l
    LEFT JOIN public.ventas v ON l.id = v.local_id
        AND v.fecha >= fecha_inicio_param
        AND v.fecha <= fecha_fin_param
    WHERE l.mall_id = mall_id_param
    GROUP BY l.id, l.nombre, l.rubro;
$$;
