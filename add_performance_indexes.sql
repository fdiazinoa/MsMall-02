-- Performance indexes for MsMall growth scenarios
-- Focus: dashboard KPIs, insights ranking/heatmap, tenant-scoped queries.

DO $$
BEGIN
  -- 1) Core ventas access patterns
  -- Dashboard: WHERE mall_id = ? AND fecha BETWEEN ? AND ?
  IF to_regclass('public.ventas') IS NOT NULL THEN
    CREATE INDEX IF NOT EXISTS idx_ventas_mall_fecha
      ON public.ventas (mall_id, fecha);

    -- Ranking/joins by local within tenant/date windows
    CREATE INDEX IF NOT EXISTS idx_ventas_mall_local_fecha
      ON public.ventas (mall_id, local_id, fecha);

    -- Store-level insights and drilldowns
    CREATE INDEX IF NOT EXISTS idx_ventas_local_fecha
      ON public.ventas (local_id, fecha);

    -- Heatmap endpoint
    IF EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'ventas'
        AND column_name = 'hora_transaccion'
    ) THEN
      CREATE INDEX IF NOT EXISTS idx_ventas_local_hora
        ON public.ventas (local_id, hora_transaccion);
    END IF;
  END IF;

  -- 2) Tenant and lookup helpers
  IF to_regclass('public.locales') IS NOT NULL THEN
    CREATE INDEX IF NOT EXISTS idx_locales_mall
      ON public.locales (mall_id);
  END IF;

  IF to_regclass('public.usuarios_malls') IS NOT NULL THEN
    CREATE INDEX IF NOT EXISTS idx_usuarios_malls_user_mall
      ON public.usuarios_malls (usuario_id, mall_id);
  END IF;

  -- 3) Insights support
  IF to_regclass('public.alertas_inteligentes') IS NOT NULL THEN
    CREATE INDEX IF NOT EXISTS idx_alertas_local_created
      ON public.alertas_inteligentes (local_id, created_at DESC);
  END IF;
END
$$;
